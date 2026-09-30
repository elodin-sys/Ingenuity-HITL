# ingenuity-elodin

Independent application intended for an Elodin Systems repository. Use installed
`elodin` and `elodin-db` binaries. Do not add a source/workspace dependency on the
Elodin monorepo or build Elodin here. Run development commands from this repo root
inside `nix develop`; use `uv` for Python. Pi deployment is a production runtime
using isolated uv and system Python, without Nix or the Elodin SDK.

Do not commit. Preserve raw sources and checksums. Never relabel reconstructed
states, theoretical outputs, or Perseverance MEDA samples as Ingenuity flight
telemetry. Keep time systems, frames, SI units and missing-data flags explicit.
Do not claim HITL closed-loop validation for one-way hardware replay.
