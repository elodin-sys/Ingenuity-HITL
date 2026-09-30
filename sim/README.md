# Simulation — Mac

`main.py` runs the Elodin physics plant: rigid-body motion, Mars gravity and
atmosphere, actuator response, ground contact and noisy simulated sensors.
It sends sensor packets to the external Rust controller, waits for a matching
command reply, and applies that command in the next physics step.

The simulator owns physical truth. The controller receives only the documented
sensor measurements and its frozen mission targets. NASA Flight 59 states are
loaded on the Mac for visualization and scoring, never streamed as commands.
There is no local Python flight controller; a missing controller reply stops
the run. The simulated camera is displayed but is not an input to a vision FSW.

From the repository root inside `nix develop`, after starting the Pi controller:

```sh
uv run --with elodin==0.19.2 sim/main.py --controller 127.0.0.1:12360 \
  --realtime --db runs/flight59-pi
```

Use a new DB path per run. See [complete setup](../docs/CLOSED_LOOP.md) and
[the feedback-loop diagram](../docs/ARCHITECTURE.md).
