# Tested binary setup

## Official release v0.19.2

The official [v0.19.2 release](https://github.com/elodin-sys/elodin/releases/tag/v0.19.2)
was tested on 2026-09-29 on macOS arm64 with a Raspberry Pi 5 sender. Both
`elodin` and `elodin-db` report `0.19.2+dd5b6ad`. Download archive SHA256 checks
passed. No source build or workshop patch was applied to these binaries.

A complete Flight 59 replay from the Pi at 2x transport speed preserved all 180
NASA samples and 4134 display/model poses; all 1000 Monte Carlo trials matched
the recorded winner history. The native renderer recorded 1037 gray8 frames.
The official Editor displayed the helicopter, terrain, both trajectories, cube,
monitors and recorded downward camera after reopening the recording.

The isolated test restarted the renderer after metadata registration and reopened
the Editor after ingestion; it is not a clean-machine validation of the default
one-command live startup. Initial live viewing showed a pre-data timeline and no
video. Other operating systems have not been tested.

Use separately extracted release binaries via `ELODIN_BIN` and `ELODIN_DB_BIN`.
Explicit overrides take precedence over any older `.tools/` binaries.
Release checksums are recorded in `release-v0.19.2-provenance.json`.

## Earlier development build


Validated on macOS arm64 with Raspberry Pi 5 / aarch64 Raspberry Pi OS:

| Program | Tested version |
|---|---|
| Editor and native sensor renderer | `elodin 0.19.3-alpha.0+d24b7193c.dirty` |
| Database | `elodin-db 0.19.2-alpha.0+ff26c97e1.dirty` |
| Pi runtime | isolated uv `0.12.20`, system Python |

The Editor binary was reused from the earlier Mars workshop and copied to local
`.tools/elodin`. It includes that workshop's rendering fixes (notably viewport
tracking without the view cube, sensor rendering and per-camera visibility).
Base revision: `d24b7193cbdd05d264a1b04f7a85214de0037843`.
Renderer patch SHA256:
`c86d146dc5029b4d2a0a23cf9c5fc5f08b829cb004d1591b16d8861436547199`.

This project **did not build or modify Elodin**. The tested binary is a local
development build, not a claim of compatibility with every published release.
The official release test above now establishes that a special workshop build
is not required for the tested recording and rendering features. Binary hashes for this session
are recorded in `binary-provenance.json`; binaries themselves are ignored.

Scripts select `ELODIN_BIN` when set, then local `.tools/elodin` when present,
then `elodin` on PATH. The DB selects `ELODIN_DB_BIN`, then local `.tools/elodin-db`,
then `elodin-db` on PATH. There is no hardcoded
dependency on a neighboring source checkout. The host GPU does the rendering;
the Pi runs only standard-library Python replay and the sensitivity campaign.

`flake.nix` supplies development tools, not Elodin. After cloning, run `nix develop`
from the Git repository root. Do not use a generic `path:.` flake over a directory
containing large local DB recordings: that can copy ignored runtime files into
the Nix input tree.
