# Source inventory and interpretation

| Source | Retrieved material | What it supports |
|---|---|---|
| [PDS HeliCam bundle, DOI 10.17189/1522845](https://pds.nasa.gov/ds-view/pds/viewBundle.jsp?identifier=urn:nasa:pds:mars2020_helicam&version=11.0) | 15 flight-1 NAV EDR XML labels | Archived S2-in-G navigation pose, image acquisition time, SCLK |
| [Flight-1 archive directory](https://planetarydata.jpl.nasa.gov/img/data/mars2020/mars2020_helicam/data/sol/00058/ids/edr/heli/) | Source listing plus XML labels | Product selection and reproducibility |
| [Camera SIS](https://pds-imaging.jpl.nasa.gov/documentation/Mars2020_Camera_SIS.pdf) | Version 3.1 PDF | Sections 20.9 and 20.11: frame conventions and quaternion transforms |
| [MEDA archive](https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html) | Sol-58 calibrated pressure/ATS, derived pressure/wind and XML labels | Atmospheric measurements at Perseverance, not onboard Ingenuity |
| [NASA model](https://science.nasa.gov/3d-resources/ingenuity-mars-helicopter/) | Original GLB and decoded derivative | Visual model; credit NASA / Brian E. Kumanchik |
| [NASA flight log](https://science.nasa.gov/wp-content/uploads/2024/06/ingenuity-helicopter-flight-log.pdf) | PDF | Flight summaries, not sample-by-sample telemetry |
| [NASA first-flight account](https://science.nasa.gov/photojournal/perseverances-mastcam-z-video-of-ingenuitys-first-full-flight/) | Linked reference | 39.1 s duration, 3 m hover, 30 s hover for the optional reconstruction |
| [Jackson et al., 2025](https://doi.org/10.3847/PSJ/ad8b41) | Linked research reference | Attitude-based winds; describes 500 Hz data for flights 1–5, 59 and 61 |
| [In-flight system identification](https://ntrs.nasa.gov/citations/20250010356) | Linked research reference | Flights 68–69 as future system identification targets |

## HeliCam extraction

We select NAV (`HNM`) EDR XML labels once per image, avoiding duplicate ECM/FDR/RDR
representations. The solution must be `TELEMETRY`, flight index 1, S2 parent G,
forward quaternion rotation, metre offsets, and approximately unit quaternion.
The raw source quaternion is scalar first; the derived CSV stores xyzw explicitly.

The camera SIS defines G as ground-fixed, Z-down, with X along the pre-flight
vehicle forward direction. It is **not north-aligned**. The display mapping is
`U = Rx(pi) G`: position `(x, -y, -z)` and quaternion `Rx(pi) * Q_S2_to_G`.
This is a proper rotation (determinant +1), not a handedness-changing reflection.
We normalize only the displayed quaternion; source numbers are also transmitted.

S2 is an IMU frame. The SIS recommends mechanical M for general vehicle geometry,
but M is static in these particular labels. We do not use it to fabricate motion
or infer an unavailable IMU mounting calibration. Mesh position/orientation are
therefore illustrative. Recorded S2 heights are not automatically terrain AGL or
center-of-mass altitude. Post-landing drift is retained and documented.

## MEDA cleaning and clocks

Derived PS supplies the selected pressure retrieval. `ATS_LOCAL_TEMP1` is used as
a **local sensor temperature**, not an ambient-air retrieval; pressure-sensor
THERMOCAP temperatures would be inappropriate atmospheric temperatures. Pressure
and ATS are paired only at exactly matching SCLK values. Missing values and the
wind sentinel 999999999 are removed; wind requires ROVER_STILL=1. Missing wind is
represented by NaN and a separate validity channel on the wire.

The initial weather window is ±5 local-mean-solar minutes around 12:33 LMST.
Elapsed SI seconds come from SCLK differences, never by equating LMST seconds to
Earth seconds. The default archive replay selects MEDA samples between the first
and last camera SCLK and schedules them on that common mission-clock basis.
This aligns timestamps, **not locations**: rover and helicopter winds need not
match. Original image UTC is retained as a separate channel.

## Outstanding data acquisition

Full 500 Hz navigation/IMU/actuator logs, rotor speed, collective/cyclic commands,
electrical power and engineering validity flags are still missing. HeliCam labels
are useful sparse navigation samples, but do not supply these missing channels.
A future data request should specify flights 1–5, 59, 61, 68–69; units, frames,
clock correlations, calibration, quality flags and redistribution permission.
No request has been sent to researchers.

## Flight 59 — current workshop dataset

NASA PDS Mars 2020 HeliCam, DOI [10.17189/1522845](https://doi.org/10.17189/1522845),
sol 00915 / Flight 59. Use the
[official archive explorer](https://pds-imaging.jpl.nasa.gov/beta/archive-explorer?bundle=mars2020_helicam&instrument=helicam&mission=mars_2020).
The 180 HNM NAV EDR XML labels in release 9 contain S2 navigation estimates from
2023-09-16T19:30:29.100465Z to 19:32:46.835804Z (137.735339 s).
The largest inter-observation gap is 0.801535 s. All indexed MD5 hashes were
checked; source URLs and SHA256 hashes are in `data/derived/sol00915.json`.
These later products resolve the G parent via local XML references; early
products instead embed the reference coordinates. Both forms are checked.

The first and last S2 heights are 0.546751 m and 3.280313 m. The files therefore
exclude liftoff and touchdown. The five color-camera EDR acquisitions on this
sol fall inside the same interval and do not extend the endpoint coverage.
Other NAV products are processed versions of those acquisitions. No 500 Hz log
has been downloaded, and no final landing samples are invented.

The published study [Jackson et al. 2025, PSJ 6:21](https://doi.org/10.3847/PSJ/ad8b41)
describes Flight 59's altitude plateaus and its megaripple takeoff site in section
2.3.6. Its 500 Hz input data are distinct from the image-label archive used here.
The [published paper PDF](https://helda.helsinki.fi/server/api/core/bitstreams/74f04848-4264-49e3-8aa2-6ebe75834630/content)
is a source for the descriptive terrain dimensions and plateau heights, not a
machine-readable telemetry download.
