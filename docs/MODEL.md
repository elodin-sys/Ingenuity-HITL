# Physics, Monte Carlo and next milestones

## Flight 59 trajectory comparison

The default computes 1000 translational (3-DOF) candidates on the Raspberry
Pi during replay, using Python's standard library. This is an application-level
Monte Carlo campaign, not the Elodin CLI campaign runner. Seed 59 is fixed.
The best trajectory is selected by 3-D position RMSE at the **180 original image
acquisition times**. All observations have equal weight, including the short
high-cadence burst near the end. Interpolated samples are never scored as new
measurements. The replay contains an interpolated reference/model pair with
identical timestamps and a Euclidean separation monitor. One candidate is
computed at each scheduled event, distributed across the 137.735 s interval.
After every calculation, the lowest-RMSE candidate among the completed prefix
becomes the current winner. The count and winner ID are integer DB channels.
This is paced computation over a known historical dataset, not causal onboard
estimation: each candidate is scored against the complete archived flight.

The model integrates position and velocity under Mars gravity, vector thrust
with a first-order lag, and quadratic drag relative to a constant horizontal
wind. A PD position/velocity controller tracks a vertical stair-step reference
and holds the horizontal G origin. Thrust is bounded by twice nominal weight.
The initial position is observed; initial velocity is a first finite difference.
Integration uses semi-implicit Euler at 0.05 s, with a 0.025 s convergence check.
No attitude, rotor RPM, motor, battery or inflow state is predicted.

Reference plateau heights come from Jackson et al. (2025), section 2.3.6.
Transition times are **inferred from midpoint crossings in this same archive**,
with 0.75 m/s ramps. The final reference ends at the last observation, still
3.280 m above the G origin. This is a conditional calibration, not an independent
prediction or a reconstruction of historical guidance commands.

Uniform exploratory priors are declared in `scripts/trajectory_monte_carlo.py`:
pressure 600–800 Pa, temperature 190–250 K, each horizontal wind component
−12–12 m/s, effective CdA 0.01–0.06 m², plus controller gains, thrust lag/gain and
reference timing shift. Density is p/(R_CO2 T). These bounds are assumptions;
the fitted parameters are not recovered Martian weather. Pressure, temperature,
drag and wind are not separately identifiable from this trajectory. Rotor lateral
aerodynamics and spatially varying winds are absent.

The Pi saves every candidate's parameters/score, the best integrated trajectory,
median/worst RMSE, reference schedule, and source hash. Every improvement retains
its full candidate path and the replay time when it became the winner. The
workshop recalculates the campaign on every replay. `calibrate_trajectory.py`
remains a separate optional offline calculation with a source/model-hash cache;
the live replay does not read that cache.

The orange line records the best-so-far position at each display time. When the
winner changes, subsequent points use the new path; earlier points preserve what
was displayed then. Thus this history can contain changes of model and is not a
single candidate's full trajectory. Timeline future segments are future recorded
display points, not a new forecast. Each final candidate path is saved separately.

An orange sphere marks the current winner's position: its identity quaternion is a marker
convention, not a modeled attitude. The real helicopter uses archived attitudes.
No orange marker or trajectory overlay is rendered into the simulated Navcam.

## Earlier hover sensitivity model

The optional original model is a transparent hover calculation:

- `rho = p / (R_CO2 T)`, R_CO2 = 188.92 J/(kg K), a pure-CO2 approximation.
- `weight = m g`, m = 1.8 kg, g = 3.72076 m/s².
- `A = pi R²`, R = 0.6 m. Coaxial rotors share one projected disk area.
- Ideal induced hover power `P_i = weight^(3/2) / sqrt(2 rho A)`.
- Illustrative body drag `D = 0.5 rho CdA wind²`.
- Trim thrust `sqrt(weight² + D²)` and tilt `atan(D/weight)`.

The NASA [spacecraft description](https://www.jpl.nasa.gov/news/press_kits/ingenuity/landing/mission/spacecraft/)
supports vehicle mass and dimensions. Disk theory here omits profile power, rotor
inflow dynamics, coaxial interference, ground effect, motor losses and control
response. CdA is an exploratory effective parameter, not a measured Ingenuity
coefficient. The tilt model is especially incomplete because rotor aerodynamics
also produce lateral forces/moments. It must not be used to claim recovered winds.

`monte_carlo.py` uses Latin hypercube sampling, a fixed seed, and reports empirical
5/50/95 percentiles. The bounds are assumptions and the percentiles are not
confidence intervals. This is not yet an Elodin `monte-carlo` campaign or a 6DOF
simulation. No controller or historical actuator inputs are implied.

## Calibration plan

1. Validate S2-to-mechanical transform and time correlation; obtain full-rate
   attitude, velocity, IMU, RPM, collective/cyclic and quality data. Keep the
   original bytes and labels. Reject navigation-invalid / post-landing windows.
2. Join calibrated MEDA ambient retrievals and their quality flags. Quantify the
   spatial separation from the helicopter. Use correlated pressure/temperature
   priors; derive density. Do not fit pressure, temperature, density, thrust gain
   and drag simultaneously from altitude alone: the problem is unidentifiable.
3. Implement translational + attitude dynamics, rotor thrust/inflow response and
   ground effect using published engineering models. Overlay an archive replay
   entity and simulated entity with clearly distinct channels.
4. Hold out complete flights/windows. Score position, attitude geodesic angle,
   velocity and power residuals against measured channels only. Use uncertainty-
   weighted residuals, fixed seeds, paired scenarios and bootstrap/holdout checks.
   Report worst cases and distributions, not just the best run.
5. Put the controller on the Pi and the plant on the host. Specify step/sequence
   IDs, sensor and command packets, clock semantics, timeout/watchdog and latency
   budget. Measure p50/p95/p99 latency and dropped/late steps. The current reliable
   one-way replay does not exercise a closed-loop controller or validate GNC.

A future Elodin CLI campaign can orchestrate these experiments using installed
binaries. Neither fitting reconstructed data nor matching a nominal hover profile
would constitute validation of the real helicopter.
