"""Replay measured MEDA data in table 74; retain SCLK and wind validity."""

import argparse
import csv
import json
import math
import socket
import struct
import time
from pathlib import Path

from replay import HEADER

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2250)
    parser.add_argument("--speed", type=float, default=1)
    args = parser.parse_args()
    if not math.isfinite(args.speed) or args.speed <= 0:
        parser.error("--speed must be finite and positive")
    with (ROOT / "data/derived/meda_sol58.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    first = float(rows[0]["sclk_s"])
    epoch = time.time_ns() // 1000
    start = time.monotonic()
    with socket.create_connection((args.host, args.port), timeout=10) as connection:
        for row in rows:
            sclk = float(row["sclk_s"])
            elapsed = sclk - first
            time.sleep(max(0, start + elapsed / args.speed - time.monotonic()))
            # NaN explicitly represents missing wind; validity is also transmitted.
            wind = float(row["wind_mps"]) if row["wind_valid"] == "1" else math.nan
            data = struct.pack(
                "<q6d",
                epoch + round(elapsed * 1e6),
                elapsed,
                sclk,
                float(row["pressure_pa"]),
                float(row["ats_local_temp1_k"]),
                wind,
                float(row["wind_valid"]),
            )
            connection.sendall(HEADER.pack(4 + len(data), 1, 74, 0) + data)
    print(json.dumps({"meda_measured_rows": len(rows), "source_duration_s": sclk - first}))


if __name__ == "__main__":
    main()
