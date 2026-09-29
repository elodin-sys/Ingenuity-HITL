"""Seeded 3-DOF calibration against Flight 59's archived positions.

This is a conditional fit with an inferred reference schedule, not recovered
flight software, a wind measurement, or independent predictive validation.
"""

import bisect
import hashlib
import math
import random
import statistics

G = 3.72076
MASS = 1.8
R_CO2 = 188.92
BOUNDS = {
    "pressure_pa": (600, 800),
    "temperature_k": (190, 250),
    "wind_x_mps": (-12, 12),
    "wind_y_mps": (-12, 12),
    "cd_area_m2": (0.01, 0.06),
    "position_gain_s2": (1.5, 5.0),
    "velocity_gain_s": (1.8, 4.0),
    "thrust_lag_s": (0.08, 0.35),
    "thrust_gain": (0.96, 1.04),
    "reference_shift_s": (-0.6, 0.6),
}


def reference_schedule(rows):
    """Paper plateau heights; transition timing inferred from midpoint crossings."""
    heights = [4.25, 8.25, 12.25, 16.25, 20.25, 16.25, 12.25, 8.25, 4.25]
    speed = 0.75
    knots = [(0.0, rows[0][7]), ((heights[0] - rows[0][7]) / speed, heights[0])]
    after = knots[-1][0]
    for old, new in zip(heights, heights[1:]):
        midpoint = (old + new) / 2
        direction = 1 if new > old else -1
        crossing = None
        for a, b in zip(rows, rows[1:]):
            if b[0] <= after:
                continue
            if direction * (a[7] - midpoint) <= 0 < direction * (b[7] - midpoint):
                crossing = a[0] + (b[0] - a[0]) * (midpoint - a[7]) / (b[7] - a[7])
                break
        if crossing is None:
            raise ValueError("Flight 59 reference plateau sequence is not covered")
        half = abs(new - old) / (2 * speed)
        knots.extend(((crossing - half, old), (crossing + half, new)))
        after = crossing + half
    # The archive stops during the final descent. End the inferred reference at
    # that observation, without adding an unobserved touchdown.
    last = rows[-1]
    knots.extend(((last[0] - (4.25 - last[7]) / speed, 4.25), (last[0], last[7])))
    if any(b[0] <= a[0] for a, b in zip(knots, knots[1:])):
        raise ValueError("Non-monotonic inferred guidance schedule")
    return knots


def reference_at(knots, t):
    if t <= knots[0][0]:
        return knots[0][1], 0.0
    for a, b in zip(knots, knots[1:]):
        if t < b[0]:
            velocity = (b[1] - a[1]) / (b[0] - a[0])
            return a[1] + velocity * (t - a[0]), velocity
    return knots[-1][1], 0.0


def simulate(rows, knots, params, dt=0.05):
    """PD station keeping, vector thrust lag, gravity and relative-air drag."""
    if dt <= 0 or dt > 0.1:
        raise ValueError("Use an integration step in (0, 0.1] seconds")
    position = list(rows[0][5:8])
    # Initial speed is a finite difference of the first two observations.
    velocity = [(b - a) / (rows[1][0] - rows[0][0]) for a, b in zip(rows[0][5:8], rows[1][5:8])]
    thrust = [0.0, 0.0, MASS * G]
    density = params["pressure_pa"] / (R_CO2 * params["temperature_k"])
    wind = (params["wind_x_mps"], params["wind_y_mps"], 0.0)
    drag_factor = 0.5 * density * params["cd_area_m2"] / MASS
    gain_p, gain_v = params["position_gain_s2"], params["velocity_gain_s"]
    path = [(0.0, *position)]
    t = 0.0
    while t < rows[-1][0] - 1e-10:
        step = min(dt, rows[-1][0] - t)
        height, climb = reference_at(knots, t - params["reference_shift_s"])
        target, target_velocity = (0.0, 0.0, height), (0.0, 0.0, climb)
        alpha = -math.expm1(-step / params["thrust_lag_s"])
        command = [
            MASS * (gain_p * (r - p) + gain_v * (vr - v) + (G if axis == 2 else 0))
            for axis, (r, p, vr, v) in enumerate(zip(target, position, target_velocity, velocity))
        ]
        command[2] = max(0.0, command[2])
        magnitude = math.sqrt(sum(v * v for v in command))
        scale = min(1.0, 2 * MASS * G / max(magnitude, 1e-12))
        relative = [v - w for v, w in zip(velocity, wind)]
        airspeed = math.sqrt(sum(v * v for v in relative))
        for axis in range(3):
            thrust[axis] += alpha * (command[axis] * scale * params["thrust_gain"] - thrust[axis])
            acceleration = thrust[axis] / MASS - drag_factor * airspeed * relative[axis]
            if axis == 2:
                acceleration -= G
            velocity[axis] += acceleration * step
            position[axis] += velocity[axis] * step
        t += step
        path.append((t, *position))
    return path


def at(path, t):
    """Interpolate only within the integrated interval."""
    if t < path[0][0] - 1e-8 or t > path[-1][0] + 1e-8:
        raise ValueError("Cannot extrapolate a model outside the archived interval")
    index = min(len(path) - 1, max(1, bisect.bisect_left(path, t, key=lambda row: row[0])))
    a, b = path[index - 1], path[index]
    f = (t - a[0]) / (b[0] - a[0])
    return tuple(x + f * (y - x) for x, y in zip(a[1:], b[1:]))


def score(rows, path):
    """Position RMSE at original acquisition times, never at interpolated truth."""
    return math.sqrt(
        sum(sum((p - q) ** 2 for p, q in zip(at(path, r[0]), r[5:8])) for r in rows) / len(rows)
    )


class LiveCampaign:
    """One actual candidate evaluation per call; keep the best-so-far path."""

    def __init__(self, rows, source_bytes, draws=1000, seed=59):
        if draws < 1:
            raise ValueError("Need at least one Monte Carlo draw")
        self.rows, self.source_bytes, self.target, self.seed = rows, source_bytes, draws, seed
        self.rng = random.Random(seed)
        self.knots = reference_schedule(rows)
        self.samples, self.winners = [], []
        self.best, self.path = None, None

    def advance(self, elapsed=0.0):
        if len(self.samples) >= self.target:
            raise ValueError("Campaign already complete")
        params = {key: self.rng.uniform(*bounds) for key, bounds in BOUNDS.items()}
        path = simulate(self.rows, self.knots, params)
        result = {
            "draw": len(self.samples) + 1,
            "rmse_m": score(self.rows, path),
            "parameters": params,
        }
        self.samples.append(result)
        if self.best is None or result["rmse_m"] < self.best["rmse_m"]:
            self.best, self.path = result, path
            self.winners.append(
                {
                    "elapsed_s": elapsed,
                    "draw": result["draw"],
                    "rmse_m": result["rmse_m"],
                    "path": path,
                }
            )
        return self.best

    def report(self):
        return report(
            self.rows,
            self.source_bytes,
            self.samples,
            self.best,
            self.path,
            self.knots,
            self.seed,
            self.winners,
        )


def campaign(rows, source_bytes, draws=1000, seed=59, progress=None):
    live = LiveCampaign(rows, source_bytes, draws, seed)
    for index in range(draws):
        live.advance(index * rows[-1][0] / max(1, draws - 1))
        if progress and ((index + 1) % 100 == 0 or index == draws - 1):
            progress(index + 1, live.best["rmse_m"])
    return live.report()


def report(rows, source_bytes, samples, best, best_path, knots, seed, winners):
    residuals = [math.dist(at(best_path, row[0]), row[5:8]) for row in rows]
    report = {
        "dataset": "sol00915",
        "source_csv_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "meaning": "Conditional 3-DOF calibration; inferred guidance; not independent validation",
        "seed": seed,
        "draws": len(samples),
        "winners": winners,
        "integration_step_s": 0.05,
        "scoring": "Equal-weight 3-D position RMSE at the 180 archived acquisition times",
        "attitude": "Not modeled; best.world_pos orientation is identity for a spherical marker",
        "bounds": BOUNDS,
        "reference_knots_s_m": knots,
        "reference_note": "Published plateau heights; timing inferred from this same archive; 0.75 m/s ramps",
        "best": best,
        "median_rmse_m": statistics.median(r["rmse_m"] for r in samples),
        "worst_rmse_m": max(r["rmse_m"] for r in samples),
        "best_max_error_m": max(residuals),
        "samples": samples,
        "path": best_path,
    }
    return report
