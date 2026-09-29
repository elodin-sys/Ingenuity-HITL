# Local validation — 2026-09-29

## Current Flight 59 replay — live Monte Carlo

Flight 59 / sol 915 ran from the Raspberry Pi through native Elodin DB and Editor.
The corrected layout was visually inspected: chase camera, two 3-D trajectories,
orange modeled-position marker, simulated downward Navcam, orientation cube,
thicker cyan/amber trails, and labeled monitors with integer trial/winner IDs.

| Channel group | Verified result |
|---|---|
| NASA navigation | 180 poses over 137.735339 s; all 17 source fields preserved exactly |
| Archive timing | Acquisition intervals preserved to microsecond rounding |
| Display and best model | 4134 paired timestamps; every pose and error checked against the source/Pi result |
| Trajectory Monte Carlo | 1000 seeded Pi evaluations during playback; 7 successive leaders; final winner 867, calibration RMSE 0.268557784984 m |
| Native navigation camera | 1369 recorded gray8 images, 640×480, target 10 FPS |
| Weather | No measurements from another sol substituted |

The campaign's best score was checked against all 1000 candidate scores and
recomputed from its integrated trajectory at the original acquisition times.
The Euler-step convergence test compares 0.05 s against 0.025 s integration.
All 21 unit tests and Ruff checks pass, including both early inline PDS frame
references and the later local-reference form, JSON trajectory round trips,
and best-so-far selection at every completed campaign prefix. Native exports
verify the candidate count, winner ID, active trajectory and RMSE at every display
timestamp, not only the final result. Prior orange points retain their historical
winner; they are not replaced retroactively by the final candidate.

The source starts at S2 height 0.547 m and ends at 3.280 m: **neither liftoff nor
touchdown is present**. The terrain is a descriptive megaripple reconstruction,
not measured topography. The orange curve is a conditional fit on the same data,
not independent validation. No high-rate engineering log has been obtained.

Local artifacts: `runs/live-mc-verification.json`, `runs/live-mc-export/`,
`runs/live-mc-pi.json`, `runs/live-mc-navcam.png`, and
`runs/editor-flight59-live-mc.png`. The recording is `runs/workshop-20260929T213605Z`.
These bulky/local artifacts are ignored by Git. Reproduce with:

```sh
elodin-db export runs/YOUR-RECORDING -o runs/flight59-export --format csv --flatten --mono-us
scp YOUR-SSH-ALIAS:Ingenuity-HITL/runs/trajectory-monte-carlo.json runs/flight59-pi-monte-carlo.json
uv run scripts/verify_recording.py runs/flight59-export runs/flight59-pi-monte-carlo.json
uv run scripts/export_navcam.py runs/YOUR-RECORDING --output runs/flight59-navcam.png
```

## Earlier Flight 1 baseline

The Raspberry Pi replayed flight 1 through an SSH reverse tunnel into the native
Elodin DB. The native Editor displayed one chase viewport and the live campaign
curves. No SDK simulation or Elodin source rebuild was involved.

| Channel group | Verified result |
|---|---|
| Archived navigation | 15 poses, exact floating-point round trip |
| Coincident MEDA | 51 pressure/temperature/wind samples |
| Display interpolation | 1534 poses over 51.086615 s |
| Live sensitivity | 100 progress updates, 1000 Pi model evaluations |
| Native navigation camera | 1482 recorded gray8 images at 640×480 |

Final DB density/power percentiles match the campaign's saved Pi samples to
floating-point precision. Native DB CSV exports were used for verification,
not just the sender's exit status. One camera frame was decoded with payload
length/prefix checks and visually inspected. The chase view, NASA model orientation,
continuous ground treatment, mission title and graph layout were inspected in the
running Editor. Recorded image rate depends on GPU throughput; 30 Hz is a target.

16 unit tests pass, including source checksums, archive frame conversion, missing
weather values, quaternion interpolation, packet layout, model invariants and
incremental campaign reproducibility. Ruff lint and formatting checks pass.
The standalone Nix development shell was also evaluated successfully.

The follow-up visual pass added the visible simulated camera, removed decorative
large boulders, replaced striped regolith with seamless nondirectional noise,
and framed the helicopter together with its shadow. Sun direction is derived
from archived UTC/LTST and G-to-SITE rotation using Mars24, rather than chosen
for lighting composition. It is an approximation at a regional Jezero latitude.
Published Mars24 declination examples agree within 0.001 degree; frame inversion
and the expected 0.32 m shadow offset at 3 m altitude are tested.

The 76-sol NASA Atlas catalogue and the selection/deployment flow were exercised.
Flight 2 / sol 61 prepares 17 source states and 1886 display states over 62.824683 s,
with zero substituted sol-58 MEDA samples. The complete launcher was tested with
flight 1 on the Pi, including native sensor images and visible Editor curves.
The current binary uses low-resolution shadow maps: the shadow is visible in
both views, but its soft silhouette is not suitable for calibrated image matching.

Reproduce recording verification (use a fresh DB for a single replay):

```sh
elodin-db export runs/YOUR-RECORDING -o runs/export --format csv --flatten --mono-us
scp YOUR-SSH-ALIAS:Ingenuity-HITL/runs/live-monte-carlo.json runs/pi-monte-carlo.json
uv run scripts/verify_recording.py runs/export runs/pi-monte-carlo.json
uv run scripts/export_navcam.py runs/YOUR-RECORDING --output runs/navcam.png
```

Local reports, recordings and screenshots live under ignored `runs/`. Source
checksum/frame-extraction tests require `scripts/fetch_sources.py` first when
starting from a fresh clone without raw downloads. None of these checks establishes
closed-loop HITL validation or flight-dynamics calibration.

## Official v0.19.2 compatibility check (2026-09-29)

Both binaries were downloaded from the official release and checked against
published archive SHA256 values. Pi replay at 2x completed all 180 source states,
4134 display/model states and 1000 trials. The native export passed
`verify_recording.py`, preserving every source field and the complete winner
history. Native camera export found 1037 640x480 gray8 frames.

The official Editor visibly displayed terrain, helicopter, cyan/orange trails,
cube, monitors and recorded Navcam after reopening the completed recording.
The renderer was restarted after metadata registration during the isolated
test. This validates the components and recording replay, not yet a fresh-machine
one-command startup or every supported platform. Evidence is under ignored
`runs/release-v0.19.2-*`; hashes are in `release-v0.19.2-provenance.json`.
