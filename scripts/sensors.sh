#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run scripts/configure_scene.py
binary="${ELODIN_BIN:-elodin}"
if [[ -z "${ELODIN_BIN:-}" && -x .tools/elodin ]]; then binary="$PWD/.tools/elodin"; fi
exec "$binary" render-server --addr 127.0.0.1:2250
