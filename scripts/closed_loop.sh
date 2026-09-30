#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-sitl}"
if [[ "$mode" != sitl && "$mode" != pi ]]; then echo 'Usage: closed_loop.sh [sitl|pi]' >&2; exit 2; fi
mkdir -p runs
recording="${INGENUITY_DB_PATH:-runs/fsw-flight59-$(date -u +%Y%m%dT%H%M%SZ)}"
editor="${ELODIN_BIN:-elodin}"
database="${ELODIN_DB_BIN:-elodin-db}"
uv run scripts/prepare_assets.py
uv run scripts/split_rotors.py
children=()
cleanup() { for pid in "${children[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT
trap 'exit 130' INT TERM
if [[ "$mode" == pi ]]; then
  ./scripts/deploy_controller.sh
  ./scripts/controller_pi.sh > runs/fsw-controller.log 2>&1 &
  children+=("$!")
  address=127.0.0.1:12360
else
  cargo build --manifest-path controller/Cargo.toml
  controller/target/debug/ingenuity-fsw > runs/fsw-controller.log 2>&1 &
  children+=("$!")
  address=127.0.0.1:12359
fi
uv run python - "$address" <<'PY'
import socket,sys,time
host,port=sys.argv[1].split(':')
for attempt in range(100):
    try:
        with socket.create_connection((host,int(port)),timeout=.2): break
    except OSError: time.sleep(.1)
else: raise SystemExit('Controller did not start; see runs/fsw-controller.log')
PY
kill -0 "${children[0]}"
uv run --with elodin==0.19.2 sim/main.py --controller "$address" --realtime \
  --startup-delay 15 --db "$recording" > runs/fsw-sim.log 2>&1 &
plant=$!
children+=("$plant")
uv run python - <<'PY'
import socket,time
for attempt in range(300):
    try:
        with socket.create_connection(('127.0.0.1',2240),timeout=.2): break
    except OSError: time.sleep(.1)
else: raise SystemExit('Plant DB did not start; see runs/fsw-sim.log')
PY
kill -0 "$plant"
uv run scripts/configure_scene.py --port 2240 --schematic schematics/closed-loop.kdl
"$database" lua config/fsw_labels.lua
"$editor" render-server --addr 127.0.0.1:2240 > runs/fsw-render.log 2>&1 &
renderer=$!
children+=("$renderer")
"$editor" editor 127.0.0.1:2240 --kdl "$PWD/assets/schematics/closed-loop.kdl" > runs/fsw-editor.log 2>&1 &
viewer=$!
children+=("$viewer")
wait "$plant"
kill "$renderer" 2>/dev/null || true
wait "$renderer" 2>/dev/null || true
# Reopen the completed native DB so the Editor can keep replaying it.
"$database" run 127.0.0.1:2240 "$recording" --log-level warn > runs/fsw-db.log 2>&1 &
children+=("$!")
echo "Closed-loop flight complete: $recording. Close the Editor to finish."
wait "$viewer"
