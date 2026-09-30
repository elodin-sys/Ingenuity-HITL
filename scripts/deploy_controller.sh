#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
remote="${INGENUITY_PI_HOST:-ingenuity-pi}"
ssh -n -o IgnoreUnknown=UseKeychain "$remote" 'mkdir -p ~/Ingenuity-HITL/config'
rsync -az -e 'ssh -o IgnoreUnknown=UseKeychain' --exclude target controller "$remote:Ingenuity-HITL/"
rsync -az -e 'ssh -o IgnoreUnknown=UseKeychain' config/flight59-profile.csv "$remote:Ingenuity-HITL/config/"
ssh -n -o IgnoreUnknown=UseKeychain "$remote" 'set -eu
cd ~/Ingenuity-HITL
export CARGO_HOME="$HOME/Ingenuity-HITL/.tools/cargo"
export RUSTUP_HOME="$HOME/Ingenuity-HITL/.tools/rustup"
mkdir -p .tools
if [ ! -x "$CARGO_HOME/bin/cargo" ]; then
  curl --proto =https --tlsv1.2 -fsS https://sh.rustup.rs -o .tools/rustup-init.sh
  sh .tools/rustup-init.sh -y --no-modify-path --profile minimal --default-toolchain 1.90.0
fi
"$CARGO_HOME/bin/cargo" test --manifest-path controller/Cargo.toml
"$CARGO_HOME/bin/cargo" build --release --manifest-path controller/Cargo.toml'
