"""Prepare a reproducible trajectory campaign on the Pi before the viewer starts."""

import csv
import hashlib
import json
from pathlib import Path

from trajectory_monte_carlo import campaign

ROOT = Path(__file__).resolve().parents[1]


def calibrated(source):
    output = ROOT / "runs/trajectory-monte-carlo.json"
    source_hash = hashlib.sha256(source).hexdigest()
    model_hash = hashlib.sha256(
        (ROOT / "scripts/trajectory_monte_carlo.py").read_bytes()
    ).hexdigest()
    if output.exists():
        previous = json.loads(output.read_text())
        if (
            previous.get("source_csv_sha256") == source_hash
            and previous.get("model_source_sha256") == model_hash
            and previous.get("seed") == 59
            and previous.get("draws") == 1000
        ):
            print("Using the matching 1000-candidate Pi calibration cache", flush=True)
            return previous
    rows = [tuple(map(float, row)) for row in list(csv.reader(source.decode().splitlines()))[1:]]
    result = campaign(
        rows,
        source,
        progress=lambda count, error: print(
            f"MC {count}/1000 · best position RMSE {error:.3f} m", flush=True
        ),
    )
    result["model_source_sha256"] = model_hash
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix(".part")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(output)
    return result


def main():
    selected = json.loads((ROOT / "config/selection.json").read_text())
    if selected.get("id") == "sol00915":
        calibrated((ROOT / "data/derived/sol00915.csv").read_bytes())


if __name__ == "__main__":
    main()
