#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run scripts/prepare_assets.py
mkdir -p runs
export INGENUITY_DB_ADDR=127.0.0.1:2250
binary="${ELODIN_DB_BIN:-elodin-db}"
if [[ -z "${ELODIN_DB_BIN:-}" && -x .tools/elodin-db ]]; then binary="$PWD/.tools/elodin-db"; fi
recording="${INGENUITY_DB_PATH:-runs/workshop-db}"
configuration=()
# Existing recordings retain their original schemas as well as their assets.
if [[ ! -f "$recording/db_state" ]]; then configuration=(--config config/telemetry.lua); fi
exec "$binary" run "$INGENUITY_DB_ADDR" "$recording" \
  --assets assets "${configuration[@]}" --log-level warn
