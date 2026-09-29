"""Verify an exported Pi recording against the source rows and saved live campaign."""

import argparse
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path

from trajectory_monte_carlo import at, score
from visual_pose import interpolate

ROOT = Path(__file__).resolve().parents[1]


def verify_trajectory(rows, campaign):
    source = (ROOT / "data/derived/sol00915.csv").read_bytes()
    if hashlib.sha256(source).hexdigest() != campaign["source_csv_sha256"]:
        raise ValueError("Campaign used another archive CSV")
    truth = [tuple(map(float, row)) for row in list(csv.reader(source.decode().splitlines()))[1:]]
    samples = campaign["samples"]
    if len(samples) != 1000 or campaign["best"]["rmse_m"] != min(r["rmse_m"] for r in samples):
        raise ValueError("Best candidate does not match all 1000 scored candidates")
    if score(truth, campaign["path"]) != campaign["best"]["rmse_m"]:
        raise ValueError("Saved path does not produce its reported RMSE")
    archive = rows("helicam.world_pos")
    raw = rows("helicam.raw_s2_in_g")
    elapsed = rows("helicam.elapsed")
    clocks = rows("helicam.sclk")
    utc = rows("helicam.source_unix")
    if any(len(r) != len(truth) for r in (archive, raw, elapsed, clocks, utc)):
        raise ValueError("Source row count changed in the native DB")
    epoch = int(archive[0]["time_us"])
    for index, source_row in enumerate(truth):
        pose = archive[index]
        if int(pose["time_us"]) != epoch + round(source_row[0] * 1e6):
            raise ValueError("Archive acquisition intervals changed")
        for name, suffixes, expected, record in (
            ("helicam.world_pos", ("q0", "q1", "q2", "q3", "x", "y", "z"), source_row[1:8], pose),
            (
                "helicam.raw_s2_in_g",
                ("qx", "qy", "qz", "qw", "x", "y", "z"),
                source_row[8:15],
                raw[index],
            ),
        ):
            if [float(record[name + "_" + s]) for s in suffixes] != list(expected):
                raise ValueError(f"NASA pose values changed in {name}")
        if [
            float(elapsed[index]["helicam.elapsed"]),
            float(clocks[index]["helicam.sclk"]),
            float(utc[index]["helicam.source_unix"]),
        ] != [source_row[0], source_row[15], source_row[16]]:
            raise ValueError("Original source clocks changed")
    display, best, distance = (
        rows("display.world_pos"),
        rows("best.world_pos"),
        rows("comparison.error"),
    )
    expected_display = list(interpolate(truth))
    if (
        len(display) != len(best)
        or len(best) != len(distance)
        or len(display) != len(expected_display)
    ):
        raise ValueError("Display and model streams differ in length")
    live = "execution" in campaign
    winners = campaign.get("winners", [])
    updates = [i * truth[-1][0] / 999 for i in range(1000)]
    counts, identifiers, errors = (
        rows("comparison.draws"),
        rows("comparison.winner") if live else [],
        rows("comparison.rmse"),
    )
    for index, (d, b, e, (t, p)) in enumerate(zip(display, best, distance, expected_display)):
        if d["time_us"] != b["time_us"] or b["time_us"] != e["time_us"]:
            raise ValueError("Model/reference timestamps differ")
        actual = [
            float(d["display.world_pos_" + s]) for s in ("q0", "q1", "q2", "q3", "x", "y", "z")
        ]
        if actual != list(p):
            raise ValueError("Display interpolation differs")
        predicted = [float(b["best.world_pos_" + s]) for s in ("x", "y", "z")]
        winner = next((w for w in reversed(winners) if w["elapsed_s"] <= t), None) if live else None
        expected_path = winner["path"] if winner else campaign["path"]
        if predicted != list(at(expected_path, t)):
            raise ValueError("DB best model differs from the saved Pi trajectory")
        if live:
            if int(counts[index]["comparison.draws"]) != bisect.bisect_right(updates, t):
                raise ValueError("Candidate count does not track actual scheduled calculations")
            if int(identifiers[index]["comparison.winner"]) != winner["draw"]:
                raise ValueError("Displayed winner identifier differs")
            if float(errors[index]["comparison.rmse"]) != winner["rmse_m"]:
                raise ValueError("RMSE does not follow the current winner")
        if not math.isclose(
            float(e["comparison.error"]), math.dist(p[4:], predicted), abs_tol=1e-13
        ):
            raise ValueError("Displayed separation is incorrect")
    if float(rows("comparison.rmse")[-1]["comparison.rmse"]) != campaign["best"]["rmse_m"]:
        raise ValueError("Displayed RMSE differs")
    return {
        "dataset": "sol00915",
        "archive_rows": len(truth),
        "display_and_model_rows": len(display),
        "duration_s": truth[-1][0],
        "source_csv_sha256": campaign["source_csv_sha256"],
        "candidate_count": len(samples),
        "winner_changes": len(winners) if live else None,
        "best_position_rmse_m": campaign["best"]["rmse_m"],
        "archive_roundtrip": "All 17 source fields preserved exactly; timestamp intervals match to microsecond rounding",
        "comparison": "Every native DB modeled position and separation matches the Pi winner active at that time",
        "coverage": "Liftoff and touchdown are outside this archive",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/verification.json")
    args = parser.parse_args()

    def rows(name):
        with (args.export / (name + ".csv")).open() as stream:
            return list(csv.DictReader(stream))

    campaign = json.loads(args.campaign.read_text())
    if campaign.get("dataset") == "sol00915":
        report = verify_trajectory(rows, campaign)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        return
    report = {}
    for name, expected in [
        ("helicam.world_pos", 15),
        ("display.world_pos", 1534),
        ("meda.pressure", 51),
        ("mc.draws", 100),
    ]:
        actual = rows(name)
        if len(actual) != expected:
            raise ValueError(f"{name}: expected {expected} rows, got {len(actual)}")
        report[name] = {
            "rows": len(actual),
            "duration_us": int(actual[-1]["time_us"]) - int(actual[0]["time_us"]),
        }
    with (ROOT / "data/derived/flight01_helicam.csv").open() as stream:
        source = list(csv.DictReader(stream))
    for actual, truth in zip(rows("helicam.world_pos"), source):
        for target, field in zip(
            ["q0", "q1", "q2", "q3", "x", "y", "z"], ["qx", "qy", "qz", "qw", "x_m", "y_m", "z_m"]
        ):
            if float(actual["helicam.world_pos_" + target]) != float(truth[field]):
                raise ValueError(f"Archive pose differs: {field}")
    campaign = json.loads(args.campaign.read_text())
    if len(campaign["samples"]) != 1000:
        raise ValueError("Expected 1000 saved Pi model evaluations")
    for prefix, key in [("density", "density_kgm3"), ("power", "ideal_hover_power_w")]:
        values = sorted(row[key] for row in campaign["samples"])
        for suffix, quantile in [("p05", 0.05), ("p50", 0.5), ("p95", 0.95)]:
            name = f"mc.{prefix}_{suffix}"
            actual = float(rows(name)[-1][name])
            if not math.isclose(actual, values[round(quantile * 999)], rel_tol=1e-14):
                raise ValueError(f"Campaign percentile differs: {name}")
    report["archive_pose_roundtrip"] = "Exact floating-point values preserved"
    report["monte_carlo"] = "1000 Pi evaluations; final DB percentiles match saved Pi samples"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
