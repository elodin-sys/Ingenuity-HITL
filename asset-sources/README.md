# Lossless terrain sources

These gzip files reproduce the existing distant and legacy close terrain GLBs
byte for byte. SHA256, source descriptions and attribution remain in
`assets/PROVENANCE.json`. They use ordinary Git, without LFS.

The Flight 59 close terrain is generated from its Python recipe instead.
Ingenuity is fetched from NASA and converted locally; its original and resulting
hashes are verified. The unused Mars globe is not included.

Run `uv run scripts/prepare_assets.py` inside `nix develop` to prepare assets.
Runtime GLBs are ignored. Do not force-add them.
