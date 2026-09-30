//! Demonstration Flight 59 controller. No NASA state replay or plant dynamics here.
#![forbid(unsafe_code)]
use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::time::Duration;

const G: f64 = 3.72076;

struct Controller {
    profile: Vec<(f64, f64)>,
    previous: Option<(u64, f64)>,
    z: f64,
    vz: f64,
    xy: [f64; 2],
    integral: f64,
    landed: bool,
}

impl Controller {
    fn new(profile: Vec<(f64, f64)>) -> Self {
        Self {
            profile,
            previous: None,
            z: 0.0,
            vz: 0.0,
            xy: [0.0; 2],
            integral: 0.0,
            landed: false,
        }
    }

    fn reference(&self, t: f64) -> (f64, f64) {
        for p in self.profile.windows(2) {
            if t < p[1].0 {
                let v = (p[1].1 - p[0].1) / (p[1].0 - p[0].0);
                return (p[0].1 + v * (t - p[0].0).max(0.0), v);
            }
        }
        (0.0, 0.0)
    }

    // Measurements: time, range altitude, AHRS roll/pitch/yaw, gyro xyz,
    // optical-flow horizontal velocity xy, vertical acceleration, valid flag.
    // AHRS and optical flow are explicit sensor surrogates, not vision software.
    fn step(&mut self, seq: u64, s: &[f64]) -> Result<[f64; 9], &'static str> {
        if s.len() != 12 || s.iter().any(|x| !x.is_finite()) || s[11] != 1.0 || s[1] < -0.1 {
            return Err("invalid sensor packet");
        }
        let t = s[0];
        let dt = match self.previous {
            Some((previous_seq, previous_t)) => {
                if seq != previous_seq + 1 || t <= previous_t || t - previous_t > 0.1 {
                    return Err("nonsequential or stale sensor packet");
                }
                t - previous_t
            }
            None => {
                self.z = s[1];
                0.01
            }
        };
        self.previous = Some((seq, t));
        self.vz += s[10] * dt;
        self.z += self.vz * dt;
        let residual = s[1] - self.z;
        self.z += 0.22 * residual;
        self.vz += 0.025 * residual / dt;
        for axis in 0..2 {
            self.xy[axis] += s[8 + axis] * dt;
        }
        let (target, climb) = self.reference(t);
        let end = self.profile[self.profile.len() - 2].0;
        if t > end && self.z < 0.45 && self.vz.abs() < 0.2 {
            self.landed = true;
        }
        let phase = if self.landed {
            4.0
        } else if t < 2.0 {
            0.0
        } else if climb > 0.01 {
            1.0
        } else if climb < -0.01 {
            3.0
        } else {
            2.0
        };
        let error = target - self.z;
        if !self.landed && t >= 2.0 {
            self.integral = (self.integral + error * dt).clamp(-1.0, 1.0);
        }
        let acceleration = 2.0 * error + 2.5 * (climb - self.vz) + 0.5 * self.integral;
        let tilt_factor = (s[2].cos() * s[3].cos()).max(0.7);
        let collective = if self.landed || t < 2.0 {
            0.0
        } else {
            ((G + acceleration) / (2.0 * G * tilt_factor)).clamp(0.0, 1.0)
        };
        let ax = (-0.6 * self.xy[0] - 1.2 * s[8]).clamp(-0.7, 0.7);
        let ay = (-0.6 * self.xy[1] - 1.2 * s[9]).clamp(-0.7, 0.7);
        let roll_target = -ay / G;
        let pitch_target = ax / G;
        let roll = ((0.10 * (roll_target - s[2]) - 0.045 * s[5]) / 0.04).clamp(-1.0, 1.0);
        let pitch = ((0.10 * (pitch_target - s[3]) - 0.045 * s[6]) / 0.04).clamp(-1.0, 1.0);
        let yaw = ((-0.08 * s[4] - 0.04 * s[7]) / 0.03).clamp(-1.0, 1.0);
        Ok([
            collective,
            roll,
            pitch,
            yaw,
            phase,
            self.z,
            self.vz,
            target,
            self.integral,
        ])
    }
}

fn serve(
    mut socket: TcpStream,
    profile: Vec<(f64, f64)>,
) -> Result<(), Box<dyn std::error::Error>> {
    socket.set_read_timeout(Some(Duration::from_secs(60)))?;
    socket.set_write_timeout(Some(Duration::from_secs(2)))?;
    socket.set_nodelay(true)?;
    let mut reader = BufReader::new(socket.try_clone()?);
    let mut controller = Controller::new(profile);
    loop {
        // Fixed upper bound prevents unbounded line accumulation.
        let mut line = String::new();
        use std::io::Read;
        let count = reader.by_ref().take(2048).read_line(&mut line)?;
        if count == 0 {
            return Ok(());
        }
        if !line.ends_with('\n') {
            return Err("oversized sensor packet".into());
        }
        let mut fields = line.split_whitespace();
        let seq: u64 = fields.next().ok_or("missing sequence")?.parse()?;
        let sensor: Vec<f64> = fields.map(str::parse).collect::<Result<_, _>>()?;
        match controller.step(seq, &sensor) {
            Ok(command) => {
                let values = command
                    .iter()
                    .map(|value| format!("{value:.12}"))
                    .collect::<Vec<_>>()
                    .join(" ");
                socket.write_all(format!("{seq} {values}\n").as_bytes())?;
                socket.set_read_timeout(Some(Duration::from_secs(5)))?;
            }
            Err(reason) => {
                writeln!(socket, "ERR {reason}")?;
                return Err(reason.into());
            }
        }
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    let addr = args.get(1).map(String::as_str).unwrap_or("127.0.0.1:12359");
    let path = args
        .get(2)
        .map(String::as_str)
        .unwrap_or("config/flight59-profile.csv");
    let mut profile = Vec::new();
    for line in std::fs::read_to_string(path)?.lines().skip(1) {
        let (t, z) = line.split_once(',').ok_or("invalid profile")?;
        profile.push((t.parse::<f64>()?, z.parse::<f64>()?));
    }
    if profile.len() < 2
        || profile
            .iter()
            .any(|(t, z)| !t.is_finite() || !z.is_finite() || *t < 0.0 || *z < 0.0)
        || profile.windows(2).any(|p| p[1].0 <= p[0].0)
    {
        return Err("invalid mission profile".into());
    }
    eprintln!("Flight 59 demonstration FSW listening on {addr}");
    for stream in TcpListener::bind(addr)?.incoming() {
        if let Err(error) = serve(stream?, profile.clone()) {
            eprintln!("FSW session stopped: {error}");
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn sensor(t: f64, z: f64) -> [f64; 12] {
        [t, z, 0., 0., 0., 0., 0., 0., 0., 0., 0., 1.]
    }
    #[test]
    fn hover_and_disturbance() {
        let mut c = Controller::new(vec![(0., 4.), (10., 4.)]);
        assert!((c.step(0, &sensor(3., 4.)).unwrap()[0] - 0.5).abs() < 1e-9);
        assert!(c.step(1, &sensor(3.01, 3.9)).unwrap()[0] > 0.5);
    }
    #[test]
    fn stale_and_invalid_are_rejected() {
        let mut c = Controller::new(vec![(0., 0.), (10., 0.)]);
        c.step(0, &sensor(0., 0.)).unwrap();
        assert!(c.step(0, &sensor(0.01, 0.)).is_err());
        assert!(c.step(1, &sensor(0.2, 0.)).is_err());
        assert!(c.step(1, &sensor(0.01, f64::NAN)).is_err());
    }
}
