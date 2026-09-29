"""Create a clearly labelled reconstruction, NEVER substitute for flight telemetry."""

import csv
import json
from pathlib import Path

from model import hover, reference
from replay import COLUMNS

ROOT = Path(__file__).resolve().parents[1]


def main():
    # Explicit illustrative atmosphere, replaced only after MEDA quality/time checks.
    p, temperature = 700.0, 230.0
    theory = hover(p, temperature)
    output = ROOT / "data/derived/flight01_reconstructed.csv"
    with output.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        for tick in range(1956):  # 50 Hz; includes exact endpoint 39.1 s
            t = tick / 50
            z, speed = reference(t)
            writer.writerow(
                (
                    t,
                    0,
                    0,
                    0,
                    1,
                    0,
                    0,
                    z,
                    speed,
                    p,
                    temperature,
                    theory["density_kgm3"],
                    theory["ideal_hover_power_w"],
                    1,
                )
            )
    output.with_suffix(".json").write_text(
        json.dumps(
            {
                "source_kind": "reconstructed",
                "measured_flight_telemetry": False,
                "anchors": {"duration_s": 39.1, "hover_altitude_m": 3, "hover_duration_s": 30},
                "source": "https://science.nasa.gov/photojournal/perseverances-mastcam-z-video-of-ingenuitys-first-full-flight/",
                "assumptions": [
                    "symmetric smoothstep ascent/descent",
                    "zero horizontal motion",
                    "identity attitude (historical yaw maneuver omitted)",
                    "700 Pa and 230 K illustrative atmosphere, not MEDA measurements",
                ],
                "frame": "local ENU, meters; quaternion xyzw",
                "time": "elapsed SI seconds, epoch assigned at replay; no claimed historical UTC precision",
            },
            indent=2,
        )
        + "\n"
    )
    print(output)


if __name__ == "__main__":
    main()
