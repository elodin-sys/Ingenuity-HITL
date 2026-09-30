//! Raspberry Pi / local SITL executable for the Flight 59 demonstration controller.
#![forbid(unsafe_code)]
mod transport;
use std::net::TcpListener;
use transport::serve;

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
        if let Err(error) = serve(stream?, profile.clone(), args.get(3).map(String::as_str)) {
            eprintln!("FSW session stopped: {error}");
        }
    }
    Ok(())
}
