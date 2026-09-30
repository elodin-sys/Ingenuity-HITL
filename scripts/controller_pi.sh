#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec ssh -n -o IgnoreUnknown=UseKeychain -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 \
  -L 12360:127.0.0.1:12359 "${INGENUITY_PI_HOST:-ingenuity-pi}" \
  'cd ~/Ingenuity-HITL && exec controller/target/release/ingenuity-fsw 127.0.0.1:12359 config/flight59-profile.csv'
