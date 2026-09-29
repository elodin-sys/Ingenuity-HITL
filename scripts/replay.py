"""Replay an SI CSV over native Impeller TCP, with source timestamps preserved.

Register config/telemetry.lua on the DB before connecting. No Elodin SDK needed.
"""

import argparse
import csv
import json
import math
import socket
import struct
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = (
    "time_s",
    "qx",
    "qy",
    "qz",
    "qw",
    "x_m",
    "y_m",
    "z_m",
    "vertical_speed_mps",
    "pressure_pa",
    "temperature_k",
    "density_kgm3",
    "ideal_hover_power_w",
    "source_kind",
)
TABLE_ID = 73
PAYLOAD = struct.Struct("<q14d")
HEADER = struct.Struct("<IBHB")


def load_rows(path):
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError(f"Expected CSV columns {COLUMNS}")
        rows = [tuple(float(row[key]) for key in COLUMNS) for row in reader]
    if not rows:
        raise ValueError("Empty replay")
    previous = -math.inf
    for row in rows:
        if not all(math.isfinite(value) for value in row):
            raise ValueError("Nonfinite telemetry")
        if row[0] < 0 or row[0] <= previous:
            raise ValueError("Time must be nonnegative and strictly increasing")
        if abs(sum(value * value for value in row[1:5]) - 1) > 1e-6:
            raise ValueError("Quaternion must have unit norm")
        if row[9] <= 0 or row[10] <= 0 or row[11] <= 0:
            raise ValueError("Pressure, temperature and density must be positive")
        if row[13] not in (0, 1):
            raise ValueError("source_kind: 0=measured, 1=reconstructed")
        previous = row[0]
    return rows


def packet(row, epoch_us):
    payload = PAYLOAD.pack(epoch_us + round(row[0] * 1e6), *row)
    return HEADER.pack(4 + len(payload), 1, TABLE_ID, 0) + payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv", type=Path, default=ROOT / "data/derived/flight01_reconstructed.csv"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2250)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument(
        "--epoch-us", type=int, help="DB epoch; default is current time. Mission time is separate."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.speed) or args.speed <= 0:
        parser.error("--speed must be finite and positive")
    rows = load_rows(args.csv)
    summary = {
        "rows": len(rows),
        "mission_duration_s": rows[-1][0] - rows[0][0],
        "reconstructed_rows": sum(row[-1] == 1 for row in rows),
    }
    if args.dry_run:
        print(json.dumps(summary))
        return
    epoch = args.epoch_us if args.epoch_us is not None else time.time_ns() // 1000
    max_lateness = 0.0
    with socket.create_connection((args.host, args.port), timeout=10) as connection:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        start = time.monotonic()
        for row in rows:
            target = start + (row[0] - rows[0][0]) / args.speed
            time.sleep(max(0, target - time.monotonic()))
            max_lateness = max(max_lateness, time.monotonic() - target)
            connection.sendall(packet(row, epoch))
    summary.update(epoch_us=epoch, max_send_lateness_ms=1000 * max_lateness)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
