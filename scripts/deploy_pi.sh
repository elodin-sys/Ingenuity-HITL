#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
remote="${INGENUITY_PI_HOST:-ingenuity-pi}"
ssh -o IgnoreUnknown=UseKeychain -n "$remote" 'mkdir -p ~/Ingenuity-HITL'
rsync -az -e 'ssh -o IgnoreUnknown=UseKeychain' --exclude .git --exclude .venv --exclude runs --exclude __pycache__ \
  --exclude '.tools' --exclude '.env*' --exclude assets --exclude asset-sources --exclude data/raw ./ "$remote:Ingenuity-HITL/"
# Runtime tool isolated to this project. Pi production runtime needs no Nix/SDK.
ssh -o IgnoreUnknown=UseKeychain -n "$remote" 'set -eu; cd ~/Ingenuity-HITL; mkdir -p .tools;
if [ ! -x .tools/uv ]; then
  curl -fL --retry 2 https://github.com/astral-sh/uv/releases/download/0.12.20/uv-aarch64-unknown-linux-gnu.tar.gz -o .tools/uv.tar.gz
  tar -xzf .tools/uv.tar.gz -C .tools --strip-components=1
fi
.tools/uv run --no-project --python /usr/bin/python3 scripts/replay_helicam.py --dry-run'
