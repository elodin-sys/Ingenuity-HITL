# Preparing an Elodin Systems repository

This is an independent application. It consumes Elodin binaries and speaks the
native DB protocol; it does not import, link, or build the Elodin source tree.
The publication target is the public `elodin-sys/Ingenuity-HITL` repository.

Publication and maintenance notes:

1. The application license has not yet been selected; add the chosen license
   before presenting the code as freely reusable open-source software.
   Do not infer a code license from NASA's asset availability. Imported Mars
   assets and the GLB need their source and attribution notices retained.
2. Use the official v0.19.2 binary pair tested on macOS arm64, as documented
   with checksums in `docs/BINARIES.md`. Validate the one-command startup on a
   clean machine before promising a fully reproducible installation. `.tools/` is local and ignored; binaries are
   installed separately, never silently rebuilt from a neighboring checkout.
3. Keep generated/downloaded GLBs ignored. The two vendored binary sources are
   `asset-sources/*.glb.gz` (lossless, about 4.39 MB total). The NASA model is
   fetched with a pinned checksum, and Flight 59 terrain is generated on setup.
   No Git LFS is needed. Do not force-add `.tools/`, raw downloads, runtime assets
   or recordings. Preserve NASA attribution and the asset provenance manifests.
4. Follow `docs/RASPBERRY_PI.md` for the user's own Pi.
   Keep `.env.local`, private keys and passwords outside version
   control. The public template contains placeholders, not access credentials.
5. Run the checks and a Pi-to-DB replay described in the README, confirm the
   single-viewport layout and record an example. Review the final diff and files
   to be staged before the developer commits and pushes.

The current scientific milestone is archived navigation replay and conditional
Monte Carlo trajectory calibration on the same flight. It does not establish
independent model validation or closed-loop HITL validation. That distinction must stay visible in the public README.
