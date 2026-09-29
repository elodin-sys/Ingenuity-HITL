#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p runs
export INGENUITY_DB_PATH="${INGENUITY_DB_PATH:-runs/workshop-$(date -u +%Y%m%dT%H%M%SZ)}"
if [[ -e "$INGENUITY_DB_PATH/db_state" ]]; then
  echo "Use a fresh INGENUITY_DB_PATH for a new replay; this recording already exists." >&2
  exit 1
fi
children=()
uv run python - <<'PY'
import socket
with socket.socket() as probe:
    probe.settimeout(.2)
    if probe.connect_ex(('127.0.0.1', 2250)) == 0:
        raise SystemExit('Port 2250 is already in use; stop that session before starting another.')
PY
if [[ $# -gt 0 ]]; then
  uv run scripts/datasets.py select "$1"
else
  uv run scripts/datasets.py select sol00915
fi
uv run scripts/prepare_assets.py
./scripts/deploy_pi.sh
cleanup() {
  for pid in "${children[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 130' INT TERM
./scripts/ground.sh > runs/ground.log 2>&1 &
children+=("$!")
uv run python - <<'PY'
import socket
import time
for attempt in range(50):
    try:
        with socket.create_connection(('127.0.0.1', 2250), timeout=.2):
            break
    except OSError:
        time.sleep(.1)
else:
    raise SystemExit('Ground DB did not start; inspect runs/ground.log')
PY
# Do not connect a replay to somebody else's already-running DB.
kill -0 "${children[0]}"
./scripts/sensors.sh > runs/sensors.log 2>&1 &
children+=("$!")
./scripts/editor.sh > runs/editor.log 2>&1 &
children+=("$!")
sleep 5
./scripts/pi_replay.sh &
children+=("$!")
wait "${children[3]}"
echo "Replay complete: $INGENUITY_DB_PATH. Use the Editor timeline; Ctrl-C stops this session."
wait "${children[2]}"
