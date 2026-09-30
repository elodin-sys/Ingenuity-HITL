# Archived Flight 59 replay

The established entry point remains `scripts/workshop.sh` for compatibility.
Its sender (`scripts/replay_helicam.py`) publishes archived navigation samples;
its Monte Carlo calibration is in `scripts/trajectory_monte_carlo.py`.
These are reference and analysis tools, not flight software.

The new external Rust flight software lives in `controller/`, and its Elodin
plant is in `sim/`. See `docs/ARCHITECTURE.md` for the boundary.
