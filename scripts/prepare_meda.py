"""Keep measured MEDA channels separate from reconstructed Ingenuity states."""

import csv
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(pattern):
    (path,) = (ROOT / "data/raw").glob(pattern)
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def valid(text, low, high):
    try:
        value = float(text)
        return value if math.isfinite(value) and low <= value <= high else None
    except (ValueError, TypeError):
        return None


def lmst_seconds(text):
    hour, minute, second = map(float, text.split("M")[1].split(":"))
    return hour * 3600 + minute * 60 + second


def main():
    pressure = read("*DER_PS*.CSV")
    ats = {float(row["SCLK"]): row for row in read("*CAL_ATS*.CSV")}
    wind = {float(row["SCLK"]): row for row in read("*DER_WS*.CSV")}
    rows = []
    # ±5 LMST minutes around the NASA reported minute 12:33; NOT exact takeoff.
    center = 12 * 3600 + 33 * 60
    for row in pressure:
        lmst = lmst_seconds(row["LMST"])
        if abs(lmst - center) > 300:
            continue
        sclk = float(row["SCLK"])
        p = valid(row["PRESSURE"], 100, 1500)
        # Exact SCLK match, no interpolation across instrument gaps.
        temp = valid(ats.get(sclk, {}).get("ATS_LOCAL_TEMP1"), 100, 350)
        wind_row = wind.get(sclk, {})
        speed = valid(wind_row.get("HORIZONTAL_WIND_SPEED"), 0, 100)
        if wind_row.get("ROVER_STILL") != "1":
            speed = None
        if p is None or temp is None:
            continue
        rows.append(
            {
                "sclk_s": sclk,
                "lmst": row["LMST"],
                "pressure_pa": p,
                "ats_local_temp1_k": temp,
                "wind_mps": speed,
                "wind_valid": int(speed is not None),
            }
        )
    if not rows:
        raise ValueError("No coincident MEDA pressure / ATS samples in selected interval")
    with (ROOT / "data/derived/meda_sol58.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "rows": len(rows),
        "start_lmst": rows[0]["lmst"],
        "end_lmst": rows[-1]["lmst"],
        "source_sclk_start_s": rows[0]["sclk_s"],
        "source_sclk_end_s": rows[-1]["sclk_s"],
        "pressure_median_pa": statistics.median(row["pressure_pa"] for row in rows),
        "ats_local_temp1_median_k": statistics.median(row["ats_local_temp1_k"] for row in rows),
        "valid_wind_rows": sum(row["wind_valid"] for row in rows),
        "notes": [
            "Perseverance MEDA, NOT sensors on Ingenuity",
            "ATS_LOCAL_TEMP1 is local sensor temperature, not an asserted ambient retrieval",
            "Missing/999999999 wind values excluded; only ROVER_STILL=1",
            "LMST minute approximation; no exact alignment to Ingenuity flight data",
            "SCLK differences are seconds; LMST seconds are not used as SI elapsed time",
        ],
    }
    (ROOT / "data/derived/meda_sol58.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
