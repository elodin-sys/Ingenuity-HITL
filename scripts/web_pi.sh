#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
remote="${INGENUITY_PI_HOST:-ingenuity-pi}"
./scripts/deploy_controller.sh
ssh -n -o IgnoreUnknown=UseKeychain "$remote" 'mkdir -p ~/Ingenuity-HITL/web/dist ~/Ingenuity-HITL/bench'
rsync -az -e 'ssh -o IgnoreUnknown=UseKeychain' web/dist/ "$remote:Ingenuity-HITL/web/dist/"
rsync -az -e 'ssh -o IgnoreUnknown=UseKeychain' bench/server.py "$remote:Ingenuity-HITL/bench/"
ssh -n -o IgnoreUnknown=UseKeychain "$remote" 'cd ~/Ingenuity-HITL && python3 -c '\''from pathlib import Path; import secrets; p=Path(".tools/web-bridge-token"); p.parent.mkdir(exist_ok=True); p.touch(mode=0o600,exist_ok=True); p.write_text(p.read_text() or secrets.token_urlsafe(32)); p.chmod(0o600)'\'''
mkdir -p .tools
rsync -az -e 'ssh -o IgnoreUnknown=UseKeychain' "$remote:Ingenuity-HITL/.tools/web-bridge-token" .tools/web-bridge-token
chmod 600 .tools/web-bridge-token
echo 'Pi control desk will be available at http://127.0.0.1:8089'
exec ssh -n -o IgnoreUnknown=UseKeychain -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 \
  -L 8089:127.0.0.1:8089 -L 12460:127.0.0.1:12459 "$remote" '
set -eu
cd ~/Ingenuity-HITL
mkdir -p runs
python3 bench/server.py > runs/web-server.log 2>&1 &
web=$!
controller/target/release/ingenuity-fsw 127.0.0.1:12459 config/flight59-profile.csv runs/web-controls.txt > runs/web-fsw.log 2>&1 &
fsw=$!
trap '\''kill "$web" "$fsw" 2>/dev/null || true'\'' EXIT HUP INT TERM
wait "$fsw"
'
