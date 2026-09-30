"""Run independent closed-loop flights through the SAME external Rust controller.

The winning fit is conditional on Flight 59, not independent validation.
Run inside the simulation environment with a local controller already listening.
"""

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=59)
    parser.add_argument("--controller", default="127.0.0.1:12359")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/fsw-campaign")
    args = parser.parse_args()
    if args.runs < 1 or args.output.exists():
        parser.error("Use a positive run count and a new output directory")
    args.output.mkdir(parents=True)
    rng = np.random.default_rng(args.seed)
    archive = list(csv.DictReader((ROOT / "data/derived/sol00915.csv").open()))
    offset = json.loads((ROOT / "config/flight59-profile.json").read_text())["archive_offset_s"]
    times = np.array([float(row["time_s"]) + offset for row in archive])
    truth = np.array([[float(row[k]) for k in ("x_m", "y_m", "z_m")] for row in archive])
    results = []
    for index in range(args.runs):
        params = {
            "pressure": float(rng.uniform(600, 800)),
            "temperature": float(rng.uniform(190, 250)),
            "wind": float(rng.uniform(-8, 8)),
        }
        db = args.output / f"flight-{index:03}"
        command = [
            sys.executable,
            str(ROOT / "sim/main.py"),
            "--controller",
            args.controller,
            "--db",
            str(db),
            "--db-addr",
            "127.0.0.1:2280",
            "--seed",
            str(args.seed + index),
        ]
        for key, value in params.items():
            command += ["--" + key, str(value)]
        with db.with_suffix(".log").open("w") as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        record = {"index": index, "parameters": params, "seed": args.seed + index, "passed": False}
        if result.returncode == 0:
            samples = json.loads(db.with_suffix(".json").read_text())["samples"]
            t = [s["time_s"] for s in samples]
            positions = np.array(
                [np.interp(times, t, [s[k] for s in samples]) for k in ("x_m", "y_m", "z_m")]
            ).T
            error = math.sqrt(float(np.mean(np.sum((positions - truth) ** 2, axis=1))))
            passed = samples[-1]["phase"] == 4 and samples[-1]["collective"] == 0
            passed &= max(s["tilt_rad"] for s in samples) < 0.35
            record.update(passed=bool(passed), position_rmse_m=error, recording=str(db))
        results.append(record)
        passed_runs = [r for r in results if r["passed"]]
        best = min(passed_runs, key=lambda r: r["position_rmse_m"]) if passed_runs else None
        (args.output / "campaign.json").write_text(
            json.dumps(
                {
                    "results": results,
                    "winner": best,
                    "meaning": "Same external FSW per trial; conditional fit scored at original NASA timestamps",
                },
                indent=2,
            )
            + "\n"
        )
        print(json.dumps({"completed": index + 1, "result": record, "best": best}), flush=True)
    if not any(r["passed"] for r in results):
        raise SystemExit("No run passed the landing/tilt gates")


if __name__ == "__main__":
    main()
