# Ingenuity-HITL

Replay NASA Ingenuity navigation data from a Raspberry Pi into native Elodin DB
and the Elodin Editor. This standalone application is intended for an Elodin
Systems repository. It uses installed binaries, without building or depending on
the Elodin source tree.

The default workshop demonstrates **Flight 59, sol 915, 16 September 2023**:
one chase viewport, a simulated downward Navcam, cyan NASA trajectory, orange
best-fit Monte Carlo trajectory, and numeric monitors underneath.

## Closed-loop Flight 59 development

A new mode now separates the Python Elodin plant in [`sim/`](sim/) from the
Rust controller in [`controller/`](controller/). It keeps Flight 59 as its
mission and NASA comparison reference. See the [architecture diagram](docs/ARCHITECTURE.md)
and [run instructions and model limits](docs/CLOSED_LOOP.md).
The original `workshop.sh` remains the archived replay mode described below.

### Processing steps and where they run

- **NASA reference — Mac:** load the measured Flight 59 trajectory, displayed in cyan.
- **Physics simulation — Mac, [`sim/`](sim/):** simulate the helicopter, Martian atmosphere, motors, and ground contact with Elodin.
- **Simulated sensors — Mac:** generate noisy altitude, attitude, and motion measurements, then send them to the Raspberry Pi.
- **Flight software — Raspberry Pi, [`controller/`](controller/):** the Rust program estimates the helicopter's state, follows the Flight 59 mission targets, and computes flight commands.
- **Command application — Mac:** apply the received commands to the simulated actuators, calculate the next vehicle state, and send new measurements back to the Pi. **This feedback loop runs throughout the flight.**
- **Recording — Elodin DB on Mac:** record simulated states, commands, estimates, and the NASA reference.
- **Visualization — Editor on Mac:** display the NASA trajectory in cyan, the Pi-controlled simulated trajectory in orange, their separation, spinning rotors, and the onboard camera view.
- **Monte Carlo — Mac:** repeat flights while varying pressure, temperature, wind, and sensor noise, using the same Rust controller. Select the best result based on reference-trajectory error and landing criteria. **Live winner visualization in the Editor remains to be integrated into this new mode.**

The Rust controller is demonstration flight software, not NASA's flight software.
The simulated sensors and camera are model outputs, not archived measurements.

## Data and coverage

**180 archived navigation states over 137.735 seconds** come from NASA's
[Mars 2020 HeliCam archive](https://pds-imaging.jpl.nasa.gov/beta/archive-explorer?bundle=mars2020_helicam&instrument=helicam&mission=mars_2020).
The PDS bundle DOI is [10.17189/1522845](https://doi.org/10.17189/1522845).
These are S2 IMU position/attitude estimates with the TELEMETRY solution,
sampled when navigation images were acquired. They are **not a 500 Hz flight log**.

Coverage is 2023-09-16 19:30:29.100465–19:32:46.835804 UTC. The first S2 height
is 0.547 m and the last is 3.280 m above the local G origin. The ascent, five
altitude plateaus up to approximately 20 m, and most of the descent are present.
**Liftoff and touchdown are not observed in these files.** The replay stops at
the last observation; no synthetic ground endpoints are added. The published
study used high-rate telemetry, but a public download of that telemetry has not
been located. We cannot yet provide a fully measured ground-to-ground replay.

Every raw label and its download URL/checksum is retained. Derived CSV and
provenance: [sol00915.csv](data/derived/sol00915.csv),
[sol00915.json](data/derived/sol00915.json). Raw downloads are ignored by Git;
they can be fetched again with the preparation command below. PDS release IDs
are part of download URLs, and indexed MD5 plus recorded SHA256 protect imports.

The display reference frame is Rx(pi) * HELI_G: forward-at-start / left / up,
not geographic ENU. Source quaternions, positions and clocks remain separate DB
channels. The NASA GLB's IMU-to-body alignment is illustrative. No weather from
another sol is substituted for Flight 59.

## What the archive replay Editor shows

- **Cyan:** original archived positions connected by straight segments. The
  helicopter moves using position interpolation and shortest-arc attitude SLERP.
- **Orange:** the best candidate found so far. The Pi computes 1000 seeded
  Monte Carlo trajectories **during playback**, comparing a new candidate at
  each calculation. The sphere marks the current winner's position. Its trail
  records the winner active at each instant; previous points are not rewritten.
  This model does not predict attitude. Model and archive share the same clock.
- **Monitors:** archive elapsed seconds, S2 height, current 3-D model/reference
  distance, current best calibration RMSE, evaluated candidate count and winner ID.
- **Navcam:** native simulated 640×480 gray8 images, target 10 FPS. These are
  rendered images, not NASA photographs. Camera calibration is approximate.
- **Ground:** a procedural megaripple based on the published takeoff-site
  description (about 1 m high, 6 m wide), with continuous regolith treatment and
  small stones. Its exact shape/orientation is not a measured Jezero DEM.
- **Sun:** approximate Mars24 direction from archived UTC/LTST and G-to-SITE
  rotation. Brightness and atmospheric scattering remain illustrative.

See [visual interpretation](docs/VISUALS.md) and [model limitations](docs/MODEL.md).
The Monte Carlo result is a conditional calibration on this same flight, not
an independently validated flight-dynamics model or recovered historical weather.
In archive replay mode, the Pi performs hardware replay; this is not closed-loop
HITL validation. The separate closed-loop mode is described above.

## Run

Run development commands from this repository root inside `nix develop`, using
`uv` for Python. Install native `elodin` and `elodin-db` binaries separately;
see [tested binaries](docs/BINARIES.md). The optional local `.tools/elodin` and
`.tools/elodin-db` are used when present. `ELODIN_BIN` and `ELODIN_DB_BIN` override
them. No SDK or numerical dependency is needed on the Pi.

Configure your own SSH alias using [Pi access](docs/RASPBERRY_PI.md). Credentials
and machine-specific access remain outside this repository.

```sh
nix develop
export INGENUITY_PI_HOST=ingenuity-pi
# Fetch source labels when regenerating/verifying data:
uv run scripts/datasets.py prepare sol00915
# First setup: download/convert the NASA model and regenerate local terrain:
uv run scripts/prepare_assets.py
# Select Flight 59, deploy, start DB + renderer + Editor, replay with live MC:
./scripts/workshop.sh
```

The launcher uses a fresh recording directory. Keep the Editor open to inspect
the timeline after playback. Close it or stop the launcher to stop its children.
Assets are ingested once into each new recording; old recordings retain their
original assets.

```text
Pi source CSV + incremental seeded 3-DOF campaign
    → native Impeller TCP over SSH reverse tunnel
    → ground Elodin DB :2250 → Editor
                            → assets HTTP :2251
                            → native render-server → navcam.gray → DB
```

The tunnel maps Pi localhost:12250 to ground localhost:2250. The DB listens only
on localhost. Replay timestamps are rebased to the current time; original source
timestamps are preserved as channels. TCP replay is not a hard real-time test.
The Pi application lives in `~/Ingenuity-HITL`; other Pi applications are untouched.

Individual launcher stages are `ground.sh`, `sensors.sh`, `editor.sh`, and
`pi_replay.sh` under `scripts/`. The Pi saves complete trajectory campaign results
to `~/Ingenuity-HITL/runs/trajectory-monte-carlo.json`.

## Verify and explore

```sh
uv run scripts/replay_helicam.py --dry-run
uv run -m unittest discover -s tests -v
ruff check scripts tests
ruff format --check scripts tests
uv run scripts/export_navcam.py runs/YOUR-RECORDING --output runs/navcam.png
```

Raw-source tests require the NASA downloads. The older Flight 1/MEDA tests also
require `uv run scripts/fetch_sources.py`. Native DB export verification and
current results are documented in [verification](docs/VERIFICATION.md).

The 76-sol archive catalogue and selector remain available for later exploration:

```sh
uv run scripts/datasets.py list
uv run scripts/datasets.py refresh
uv run scripts/datasets.py select   # Interactive menu
./scripts/workshop.sh sol00061      # Another validated dataset
```

Only Flight 59 currently has the trajectory calibration. Other flights use the
earlier hover sensitivity calculation; their original sparse observations remain
separate from interpolated display states. Interpolation stops across gaps above
10 seconds. See [sources](docs/SOURCES.md) and [wire protocol](docs/PROTOCOL.md).

The optional `monte_carlo.py` is a separate ideal-hover sensitivity experiment.
The reconstructed Flight 1 transport profile in `prepare_demo.py`/`replay.py`
is explicitly synthetic and is never the default replay.

## Small repository

Runtime GLBs are ignored by Git. `prepare_assets.py` regenerates the Flight 59 close
terrain, unpacks the losslessly compressed distant and legacy close terrains, and downloads the
NASA helicopter (about 2 MB) before converting it to editor-compatible core glTF.
The first conversion uses Node/npm and pinned glTF Transform 4.5.1; subsequent
launches reuse local assets. `ground.sh` prepares missing assets automatically.
Original and final asset SHA256 checksums must match the recorded provenance.
No mesh simplification or texture quality reduction is applied.

The unused Mars globe is not distributed. Git LFS is not required. The Pi receives
scripts and flight data, excluding terrain, models and raw downloads. Runtime
assets, binaries, package caches and DB recordings still consume local disk space;
they are separate from the small Git repository.

## Publication

Source attribution is separate from the application's license. An application
license has not yet been selected. See [publication notes](docs/PUBLISHING.md).
