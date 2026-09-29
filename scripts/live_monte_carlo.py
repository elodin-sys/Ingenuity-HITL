"""Incremental atmospheric sensitivity, evaluated on the sender during replay."""

import math
import random

from model import hover


class Campaign:
    def __init__(self, config):
        self.config = config
        self.rng = random.Random(config["seed"])
        self.target = config["runs"]
        if not isinstance(self.target, int) or self.target < 2:
            raise ValueError("runs must be an integer >= 2")
        self.keys = ("pressure_pa", "temperature_k", "wind_mps", "drag_area_m2")
        for key in self.keys:
            low, high = config[key]
            if not (math.isfinite(low) and math.isfinite(high) and low < high):
                raise ValueError(f"Invalid range: {key}")
        self.samples = []

    def advance(self, batch=10):
        if batch < 1:
            raise ValueError("batch must be positive")
        for _ in range(min(batch, self.target - len(self.samples))):
            inputs = {key: self.rng.uniform(*self.config[key]) for key in self.keys}
            self.samples.append({**inputs, **hover(**inputs)})
        percentiles = []
        for key in ("density_kgm3", "ideal_hover_power_w"):
            ordered = sorted(row[key] for row in self.samples)
            percentiles.extend(ordered[round(q * (len(ordered) - 1))] for q in (0.05, 0.5, 0.95))
        return (len(self.samples), len(self.samples) / self.target, *percentiles)
