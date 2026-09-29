"""Reproducible atmospheric sensitivity campaign; not a calibration claim."""

import argparse
import csv
import json
import math
import random
from pathlib import Path

from model import hover

ROOT = Path(__file__).resolve().parents[1]


def run(config):
    count = config["runs"]
    if not isinstance(count, int) or count < 2:
        raise ValueError("runs must be an integer >= 2")
    rng = random.Random(config["seed"])
    keys = ("pressure_pa", "temperature_k", "wind_mps", "drag_area_m2")
    samples = {}
    for key in keys:
        low, high = config[key]
        if not (math.isfinite(low) and math.isfinite(high) and low < high):
            raise ValueError(f"Invalid range: {key}")
        # Stratified Latin hypercube, independent permutations per parameter.
        values = [low + (high - low) * (i + rng.random()) / count for i in range(count)]
        rng.shuffle(values)
        samples[key] = values
    rows = []
    for i in range(count):
        params = {key: samples[key][i] for key in keys}
        rows.append({"run": i, **params, **hover(**params)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/atmosphere.json")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/atmosphere")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    rows = run(config)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "samples.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "config": config,
        "interpretation": "Sensitivity only. No measured-flight residual or best-fit claim.",
    }
    for key in ("density_kgm3", "ideal_hover_power_w", "trim_thrust_n", "trim_tilt_deg"):
        values = sorted(row[key] for row in rows)
        report[key] = {
            name: values[round(q * (len(values) - 1))]
            for name, q in [("p05", 0.05), ("p50", 0.5), ("p95", 0.95)]
        }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
