"""Stream real archive navigation states at the original sparse observation cadence."""

import argparse
import csv
import json
import math
import socket
import struct
import time
from itertools import pairwise
from pathlib import Path

from configure_scene import config_packet
from live_monte_carlo import Campaign
from prepare_helicam import COLUMNS
from replay import HEADER
from trajectory_monte_carlo import LiveCampaign
from trajectory_monte_carlo import at as model_at
from visual_pose import interpolate

ROOT = Path(__file__).resolve().parents[1]


def selection():
    path = ROOT / "config/selection.json"
    if path.exists():
        return json.loads(path.read_text())
    return {
        "id": "sol00915",
        "flight": 59,
        "sol": 915,
        "csv": "data/derived/sol00915.csv",
        "meda_csv": None,
        "interpolation_max_gap_s": 10,
    }


def data_path(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT / "data/derived"):
        raise ValueError("Replay files must be inside data/derived")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2250)
    parser.add_argument("--speed", type=float, default=1)
    parser.add_argument(
        "--without-meda", action="store_true", help="Omit coincident Perseverance weather"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--without-monte-carlo", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.speed) or args.speed <= 0:
        parser.error("--speed must be finite and positive")
    selected = selection()
    with data_path(selected["csv"]).open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError("HeliCam CSV schema mismatch")
        rows = [tuple(float(row[name]) for name in COLUMNS) for row in reader]
    if len(rows) < 2 or not all(math.isfinite(v) for row in rows for v in row):
        raise ValueError("Invalid archive data")
    if rows[0][0] != 0 or any(b[0] <= a[0] for a, b in pairwise(rows)):
        raise ValueError("Archive times must start at zero and increase")
    summary = {
        "dataset": selected["id"],
        "archive_pose_rows": len(rows),
        "source_duration_s": rows[-1][0],
    }
    comparison = None
    if selected.get("flight") == 59 and not args.without_monte_carlo:
        comparison = LiveCampaign(rows, data_path(selected["csv"]).read_bytes())
        summary["trajectory_monte_carlo_draws"] = comparison.target
    epoch = time.time_ns() // 1000
    events = []
    for row in rows:
        payload = struct.pack("<q17d", epoch + round(row[0] * 1e6), *row)
        events.append((row[0], HEADER.pack(4 + len(payload), 1, 75, 0) + payload))
    meda_count = 0
    if not args.without_meda and selected.get("meda_csv"):
        with data_path(selected["meda_csv"]).open(newline="") as stream:
            for row in csv.DictReader(stream):
                sclk = float(row["sclk_s"])
                if not rows[0][15] <= sclk <= rows[-1][15]:
                    continue
                elapsed = sclk - rows[0][15]
                wind = float(row["wind_mps"]) if row["wind_valid"] == "1" else math.nan
                payload = struct.pack(
                    "<q6d",
                    epoch + round(elapsed * 1e6),
                    elapsed,
                    sclk,
                    float(row["pressure_pa"]),
                    float(row["ats_local_temp1_k"]),
                    wind,
                    float(row["wind_valid"]),
                )
                events.append((elapsed, HEADER.pack(4 + len(payload), 1, 74, 0) + payload))
                meda_count += 1
    summary["coincident_meda_rows"] = meda_count
    display_count = 0
    for elapsed, pose in interpolate(rows, max_gap=selected.get("interpolation_max_gap_s", 10)):
        payload = struct.pack("<q8d", epoch + round(elapsed * 1e6), elapsed, *pose)
        events.append((elapsed, HEADER.pack(4 + len(payload), 1, 76, 0) + payload))
        if comparison:
            # A pose tuple schedules a comparison against the current winner.
            events.append((elapsed, pose))
        display_count += 1
    summary["interpolated_display_rows"] = display_count
    campaign = None
    if comparison:
        for index in range(comparison.target):
            events.append((index * rows[-1][0] / (comparison.target - 1), None))
    if not args.without_monte_carlo and selected.get("flight") != 59:
        campaign = Campaign(json.loads((ROOT / "config/atmosphere.json").read_text()))
        updates = math.ceil(campaign.target / 10)
        for index in range(updates):
            # None is a scheduled calculation, not a precomputed result packet.
            events.append((index * rows[-1][0] / (updates - 1), None))
        summary["live_monte_carlo_draws"] = campaign.target
        summary["live_monte_carlo_updates"] = updates
    if args.dry_run:
        print(json.dumps(summary))
        return
    with socket.create_connection((args.host, args.port), timeout=10) as connection:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        connection.sendall(config_packet({"time.start_timestamp": str(epoch)}))
        start = time.monotonic()
        for elapsed, payload in sorted(events, key=lambda item: (item[0], item[1] is not None)):
            time.sleep(max(0, start + elapsed / args.speed - time.monotonic()))
            if payload is None:
                if comparison:
                    comparison.advance(elapsed)
                    if len(comparison.samples) % 100 == 0:
                        print(
                            f"MC {len(comparison.samples)}/1000 · winner {comparison.best['draw']} · RMSE {comparison.best['rmse_m']:.3f} m",
                            flush=True,
                        )
                    continue
                result = campaign.advance()
                data = struct.pack("<q9d", epoch + round(elapsed * 1e6), elapsed, *result)
                payload = HEADER.pack(4 + len(data), 1, 77, 0) + data
            elif isinstance(payload, tuple):
                modeled = model_at(comparison.path, elapsed)
                delta = tuple(p - q for p, q in zip(modeled, payload[4:]))
                data = struct.pack(
                    "<q13dQQ",
                    epoch + round(elapsed * 1e6),
                    elapsed,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                    *modeled,
                    *delta,
                    math.sqrt(sum(v * v for v in delta)),
                    comparison.best["rmse_m"],
                    len(comparison.samples),
                    comparison.best["draw"],
                )
                payload = HEADER.pack(4 + len(data), 1, 78, 0) + data
            connection.sendall(payload)
    if comparison:
        output = ROOT / "runs"
        output.mkdir(exist_ok=True)
        result = comparison.report()
        result["execution"] = "One candidate computed per scheduled event during telemetry replay"
        result["display_semantics"] = (
            "Orange history follows the best-so-far position at each display time; past points are not rewritten when a new winner appears"
        )
        (output / "trajectory-monte-carlo.json").write_text(json.dumps(result, indent=2) + "\n")
        summary["best_position_rmse_m"] = comparison.best["rmse_m"]
        summary["winner_changes"] = len(comparison.winners)
    if campaign:
        output = ROOT / "runs"
        output.mkdir(exist_ok=True)
        (output / "live-monte-carlo.json").write_text(
            json.dumps(
                {
                    "method": "seeded independent uniform draws; incremental calculation during replay",
                    "meaning": "Sensitivity of ideal hover theory, not flight-validated uncertainty",
                    "config": campaign.config,
                    "samples": campaign.samples,
                },
                indent=2,
            )
            + "\n"
        )
    print(json.dumps({**summary, "replay_epoch_us": epoch}))


if __name__ == "__main__":
    main()
