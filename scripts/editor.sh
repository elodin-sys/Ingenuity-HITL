#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
binary="${ELODIN_BIN:-elodin}"
if [[ -z "${ELODIN_BIN:-}" && -x .tools/elodin ]]; then binary="$PWD/.tools/elodin"; fi
schematic=main.kdl
if [[ -f config/selection.json && -f assets/schematics/selected.kdl ]]; then schematic=selected.kdl; fi
exec "$binary" editor 127.0.0.1:2250 --kdl "$PWD/assets/schematics/$schematic"
