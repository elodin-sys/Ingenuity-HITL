#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p runs
editor="${ELODIN_BIN:-elodin}"
recording="${INGENUITY_DB_PATH:-runs/web-flight59-$(date -u +%Y%m%dT%H%M%SZ)}"
uv run scripts/prepare_assets.py
uv run scripts/split_rotors.py
children=()
cleanup() { for child in "${children[@]}"; do kill "$child" 2>/dev/null || true; done; }
trap cleanup EXIT
trap 'exit 130' INT TERM
uv run python - <<'PY'
import socket
for port in (8089, 12460, 2270, 2271, 2272):
    with socket.socket() as s:
        try: s.bind(('127.0.0.1',port))
        except OSError: raise SystemExit(f'Port {port} is occupied. Stop the previous web bench first.')
PY
./scripts/web_pi.sh > runs/web-pi-launch.log 2>&1 &
children+=("$!")
uv run python - <<'PY'
import time
from urllib.request import urlopen
for _ in range(600):
    try:
        with urlopen('http://127.0.0.1:8089/api/state',timeout=.3): break
    except OSError: time.sleep(.2)
else: raise SystemExit('Pi web server did not start; see runs/web-pi-launch.log')
PY
uv run --with elodin==0.19.2 sim/main.py --controller 127.0.0.1:12460 --hardware raspberry \
  --web-url http://127.0.0.1:8089 --db-addr 127.0.0.1:2270 --realtime --startup-delay 12 \
  --db "$recording" > runs/web-sim.log 2>&1 &
plant=$!
children+=("$plant")
uv run python - <<'PY'
import socket,time
for _ in range(200):
    try:
        with socket.create_connection(('127.0.0.1',2270),timeout=.2): break
    except OSError: time.sleep(.1)
else: raise SystemExit('Simulation did not start; see runs/web-sim.log')
PY
uv run scripts/configure_scene.py --port 2270 --schematic schematics/closed-loop.kdl
"$editor" render-server --addr 127.0.0.1:2270 > runs/web-render.log 2>&1 &
children+=("$!")
echo 'Open http://127.0.0.1:8089, take control, and turn the knobs.'
echo 'For the native Editor, connect it separately to 127.0.0.1:2270.'
wait "$plant"
echo "Flight complete: $recording. The web page is now in replay mode. Press Ctrl-C to stop."
wait "${children[0]}"
