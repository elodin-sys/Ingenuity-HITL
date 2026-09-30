# Flight 59 closed-loop demonstration

This mode is under development. It is newly written demonstration FSW, not NASA
code. The archived Flight 59 replay remains available via `scripts/workshop.sh`.

See [the architecture diagram](ARCHITECTURE.md#reading-the-two-trajectories):
cyan is the measured NASA reference, orange is the simulated vehicle controlled
by Rust on the Pi. Commands feed the next step of the same running plant.

The ground process runs `sim/main.py` using the released Elodin Python SDK 0.19.2.
The Rust executable `controller/src/main.rs` runs the mission state machine,
range/acceleration altitude estimator, horizontal dead reckoning and feedback
control. There are no Rust dependencies and no Elodin source dependency.

## Mission

`config/flight59-profile.csv` is a frozen mission plan. Its plateau sequence is
4.25, 8.25, 12.25, 16.25, 20.25 m and back down. Intermediate transition timing
is inferred from the Flight 59 observations. Startup, complete takeoff and final
touchdown are modeled additions. `flight59-profile.json` records the alignment
offset between simulated mission time and the first NASA observation.

## One-command launcher

With the installed `elodin` and `elodin-db` on PATH (or explicit `ELODIN_BIN` and
`ELODIN_DB_BIN` overrides), run `./scripts/closed_loop.sh sitl` or
`./scripts/closed_loop.sh pi`. The latter uses `INGENUITY_PI_HOST`. It starts the
controller, plant, native renderer and Editor; it then reopens the recording for
playback. Ports 2240–2242 and the chosen controller port must be free.

## Local SITL

From the repository root inside `nix develop`, with Rust installed:

```sh
uv run scripts/prepare_assets.py
uv run scripts/split_rotors.py
cargo build --manifest-path controller/Cargo.toml
# Terminal 1:
controller/target/debug/ingenuity-fsw
# Terminal 2, fresh DB path each run:
uv run --with elodin==0.19.2 sim/main.py --db runs/flight59-sitl
```

## Pi controller

```sh
export INGENUITY_PI_HOST=your-ssh-alias
./scripts/deploy_controller.sh
# Terminal 1: controller on Pi, encrypted two-way TCP tunnel
./scripts/controller_pi.sh
# Terminal 2: plant on ground computer
uv run --with elodin==0.19.2 sim/main.py --controller 127.0.0.1:12360 \
  --realtime --db runs/flight59-pi
```

The Pi needs ARM64 Linux, a C linker, curl and SSH. The deployment script installs
a project-local Rust 1.90.0 toolchain without changing the shell profile.
The plant runs at 100 Hz in simulation time. Lockstep waits for each controller
reply; network latency can make hardware runs slower than real time. This is not
a hard real-time scheduler or evidence of flight qualification.

## Protocol and failure behavior

One bounded UTF-8 line per sensor packet: sequence, simulation time, range height,
AHRS roll/pitch/yaw, gyro xyz, optical-flow velocity xy, vertical acceleration,
valid flag. One reply: matching sequence, collective, roll/pitch/yaw commands,
mission phase, estimated height and vertical speed, target height, integrator.
Commands are normalized and bounded. Phase codes: 0 startup, 1 ascent, 2 hover,
3 descent, 4 landed. The controller restarts its state for each connection.

The plant rejects missing, invalid or mismatched replies and aborts the run after
the transport timeout. It does not continue under an internal Python controller.
This bench fail-stop policy is not an aircraft emergency-landing strategy.

## Model limitations

The plant uses Elodin rigid-body integration with assumed diagonal inertia,
gravity, density-dependent thrust, quadratic drag, first-order actuators and a
simple ground contact constraint. Normalized cyclic/yaw commands map to assumed
body moments. Rotor RPM ramps toward an assumed 2400 RPM, then decays after the
landed command; collective changes thrust at approximately constant RPM. These
are reduced-order constitutive assumptions, not measured Ingenuity actuator maps.

Range, AHRS, optical-flow velocity and compensated acceleration are noisy sensor
surrogates. The FSW is not yet performing raw IMU fusion or image-based optical
flow. The camera is a rendering output and is not fed to a vision algorithm.
The rotor meshes rotate at modeled physical phase; video sampling may alias that
motion. No archival RPM or actuator commands are claimed.

The NASA reference is displayed only over its observed interval; its missing
ground endpoints must not be manufactured. Ground clearance, terrain detail and
camera extrinsics remain illustrative as documented in `VISUALS.md`.

## Monte Carlo with actual FSW

Start the local controller, then run:

```sh
uv run --with elodin==0.19.2 monte-carlo/run.py --runs 5 --output runs/fsw-campaign
```

Each trial uses a fresh controller session and full Elodin simulation. It samples
assumed pressure, temperature and horizontal wind; noise seeds vary too. The
campaign checks landing, zero final collective and a tilt limit, then ranks the
qualified runs by 3-D position RMSE evaluated at the original NASA timestamps.
`campaign.json` updates after each completed run. This new campaign does not yet
replace the in-Editor live calibration from archive replay mode.

## Initial verification

A full Pi-controlled run recorded 15,367 steps, reached the landed state with
zero collective, and recorded 1,143 native simulated camera frames. With the
renderer and Editor active, measured throughput was about 81 steps per wall-clock
second for the 100 Hz simulation. This verifies the feedback path and recorded
output, not a real-time deadline or physical Ingenuity model validation.

Three local-controller Monte Carlo trials reached the landing criteria; the best
3-D position RMSE against the 180 archived samples was approximately 0.285 m.
This is a conditional fit to this flight with assumed dynamics and sensor models.
The standalone launcher remains to be tested end to end; these initial runs used
its component commands separately.
