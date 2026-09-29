#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Reverse forwarding makes Pi localhost:12250 reach ground localhost:2250.
# No unauthenticated DB listener is exposed to the LAN.
exec ssh -n -o IgnoreUnknown=UseKeychain -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 \
  -R 12250:127.0.0.1:2250 "${INGENUITY_PI_HOST:-ingenuity-pi}" \
  'cd ~/Ingenuity-HITL && .tools/uv run --no-project --python /usr/bin/python3 scripts/replay_helicam.py --port 12250'
