# Mission view

Default: one large chase viewport, titled **Mars 2020 · Ingenuity · Flight 59 · Sol 915**,
with a visible simulated Navcam panel on its right. Dataset selection updates the title.
Underneath: native numeric monitors for archive time, NASA S2 height, model-to-
reference distance, best-fit RMSE, Monte Carlo candidate count and winner ID.
Cyan and orange 3-D lines show archived positions and the best-so-far model
respectively. The Pi evaluates 1000 candidates during playback and updates the
winner after every calculation; it does not change NASA samples. The orange
history preserves the model active at each instant instead of rewriting the past.
The main viewport includes the orientation cube. Trails have a constant 4-pixel
screen width, with bright cyan/amber past segments and translucent future
segments. The small amber sphere marks the best modeled position; it is not
another spacecraft. Its radius is a display choice and has no physical meaning.

Display poses use linear position interpolation and shortest-arc quaternion SLERP
at 30 Hz between 180 archived observations, without extrapolation. The untouched
archive poses remain in `helicam.*`; interpolation is in `display.*`. Flight 59's
archive begins during ascent and ends during descent; touchdown is not rendered.

The NASA model is converted to core glTF, rotated from Y-up to Z-up and centered
approximately on its electronics body. This is a visual alignment, not a surveyed
S2 IMU-to-body calibration. No rotor RPM is inferred from these labels.

## Terrain and Mars assets

The original Mars ascent workshop's procedural distant terrain is stored as a
lossless gzip source and unpacked locally. The launch deck, tower, pipes and other
launch equipment are excluded. The unused Viking/USGS/ASU globe is not distributed;
the default has a single local view.

The same seamless procedural regolith texture is mapped in world meters across
the 50 km terrain and close surface. Small faceted rocks provide image features.
Large decorative basalt boulders are excluded from the scene. The surface is
illustrative, not a Jezero DEM. Sun direction is now estimated from the source
time and frame orientation; intensity and ambient light remain illustrative.
Flight 59 takes off from a megaripple described as about 1 m high and 6 m wide
in [Jackson et al. 2025](https://doi.org/10.3847/PSJ/ad8b41), section 2.3.6.
The default mesh represents that class of feature with its crest at G z=0 and
the surrounding plain at z=−1 m. Its orientation, length, exact profile, stones
and microtexture are illustrative. This is not a surveyed takeoff patch.
Terrain affects rendering only and is not used for flight calibration.

For a fresh clone, run `uv run scripts/prepare_assets.py`; it verifies the exact
validated asset bytes. No GLBs belong in Git.

To regenerate close detail: `uv run scripts/build_close_terrain.py`, then
`uv run scripts/texture_terrain.py`. The latter applies the same texture to the
vendored distant terrain. Repeated texture application is idempotent. Use
`build_close_terrain.py --flight59` for the megaripple mesh; apply the shared
texture with the helper in `texture_terrain.py`.

## Simulated navigation images

`scripts/sensors.sh` starts the native Elodin render-server. DB metadata in
`config/cameras.json` defines a downward camera: 640×480 pixels, gray8, target
10 frames/s of source time. The renderer may emit fewer frames if GPU processing
falls behind; recorded frame timestamps are authoritative. It needs live replay
to render the whole sequence; starting it after replay does not backfill a movie.

The 82.1204-degree vertical field of view is a **linearized pinhole approximation**
from the first label's CAHV vectors, using
`f_y = sqrt(V·V - (A·V)^2/(A·A))` and `2 atan(240/f_y)`.
The source labels identify their CAHVORE calibration as `SYNTHETIC`. Distortion,
rolling exposure, navigation processing and exact S2-to-camera extrinsics are not
reproduced. The 0.14 m downward offset is illustrative. The image format and
downward viewing direction follow the NASA camera SIS.

Frames are stored as `navcam.gray` messages and shown in the right-hand panel.
They are **rendered images**, not downlinked NASA photographs. The helicopter
is included in the sensor scene so it can cast a shadow. A separate overhead
viewport is not part of this layout.

## Sun and shadow

`scripts/solar.py` implements the NASA GISS [Mars24 equations](https://www.giss.nasa.gov/tools/mars24/help/algorithm.html).
It uses each label's acquisition UTC and local true solar time, an approximate
18.5° planetographic Jezero latitude, and the archived G-to-SITE quaternion.
The Camera SIS §20 defines SITE as north/east/down and G as a takeoff-local frame;
the inverse quaternion maps sunlight into G, then Rx(pi) maps it into display axes.
No Earth ephemeris or present-day replay timestamp is used for sunlight.

For flight 1, the chosen mid-sequence sample gives elevation 83.85° and azimuth
220.63° clockwise from north. On a horizontal plane, a point 3 m above ground casts
its shadow about 0.32 m away. The direction varies by at most 0.11° from this
fixed direction across the 15 observations. Both cameras use the same vector.
Inputs, vectors and angular variation are in `data/derived/sol00058_lighting.json`.

For Flight 59, the mid-sequence solar elevation is approximately 82.233° and
azimuth 62.832° clockwise from north. The fixed direction differs from the
per-label directions by at most 0.271°. See `data/derived/sol00915_lighting.json`.

This is an approximate geometric reconstruction, not SPICE, measured solar
irradiance, a calibrated optical shadow, or per-flight geolocation. The selected
dataset uses its own archived time/orientation and records its angular variation;
the current renderer holds the selected mid-sequence sun direction constant.
Uncertainty from regional latitude, frame estimates, approximate mesh alignment,
terrain and render shadow resolution limits comparison with real photographs.
