//! Linux bench transport; replace this adapter for a different target.
use ingenuity_fsw::Controller;
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::time::Duration;

pub(crate) fn serve(
    mut socket: TcpStream,
    profile: Vec<(f64, f64)>,
    controls: Option<&str>,
) -> Result<(), Box<dyn std::error::Error>> {
    socket.set_read_timeout(Some(Duration::from_secs(60)))?;
    socket.set_write_timeout(Some(Duration::from_secs(2)))?;
    socket.set_nodelay(true)?;
    let mut reader = BufReader::new(socket.try_clone()?);
    let mut controller = Controller::new(profile);
    let mut tuning = [1.0, 1.0];
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
        if seq.is_multiple_of(10) {
            if let Some(path) = controls {
                // Atomic file written by the Pi web service. Expire tuning if
                // the service stops refreshing its heartbeat for 3 seconds.
                tuning = read_tuning(path).unwrap_or([1.0, 1.0]);
                controller.set_gains(tuning[0], tuning[1])?;
            }
        }
        match controller.step(seq, &sensor) {
            Ok(command) => {
                let values = command
                    .iter()
                    .map(|value| format!("{value:.12}"))
                    .collect::<Vec<_>>()
                    .join(" ");
                let suffix = if controls.is_some() {
                    format!(" {} {}", tuning[0], tuning[1])
                } else {
                    String::new()
                };
                socket.write_all(format!("{seq} {values}{suffix}\n").as_bytes())?;
                socket.set_read_timeout(Some(Duration::from_secs(5)))?;
            }
            Err(reason) => {
                writeln!(socket, "ERR {reason}")?;
                return Err(reason.into());
            }
        }
    }
}

fn read_tuning(path: &str) -> Option<[f64; 2]> {
    use std::io::Read;
    let file = std::fs::File::open(path).ok()?;
    if file.metadata().ok()?.modified().ok()?.elapsed().ok()? > Duration::from_secs(3) {
        return None;
    }
    let mut text = String::new();
    file.take(128).read_to_string(&mut text).ok()?;
    let values: Vec<f64> = text
        .split_whitespace()
        .map(str::parse)
        .collect::<Result<_, _>>()
        .ok()?;
    match values.as_slice() {
        [p, d] if (0.2..=2.0).contains(p) && (0.6..=1.6).contains(d) => Some([*p, *d]),
        _ => None,
    }
}
