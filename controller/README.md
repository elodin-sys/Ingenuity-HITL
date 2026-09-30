# Flight software — Raspberry Pi

This Rust crate is the external flight controller. It has no Elodin, Python,
NASA archive, or plant-dynamics dependency.

- `src/lib.rs`: navigation estimates, mission phase and feedback control. Takes
  timestamped noisy sensor measurements and produces bounded actuator commands.
- `src/transport.rs`: Linux TCP adapter, packet bounds and connection timeouts.
- `src/main.rs`: loads the frozen mission targets and starts the server.

The Mac sends measurements; it does not calculate the flight-control commands.
The same control library runs on the Pi for HITL and on the Mac for SITL.
Only `config/flight59-profile.csv` is deployed as the mission plan, not the NASA
navigation archive. See [the full boundary and diagram](../docs/ARCHITECTURE.md).

From the repository root inside `nix develop`:

```sh
cargo test --manifest-path controller/Cargo.toml
export INGENUITY_PI_HOST=your-ssh-alias
./scripts/deploy_controller.sh
./scripts/controller_pi.sh
```

This is demonstration flight software on Linux, not NASA software or a
flight-qualified embedded stack. AHRS and optical flow are supplied as sensor
surrogates; raw IMU fusion and camera-based navigation are not implemented.
