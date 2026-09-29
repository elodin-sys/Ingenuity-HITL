#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
npx --yes --package=node@22 --package=@gltf-transform/cli@4.5.1 gltf-transform png \
  data/raw/ingenuity-nasa-original.glb assets/models/ingenuity.glb --formats '*'
uv run scripts/align_model.py
