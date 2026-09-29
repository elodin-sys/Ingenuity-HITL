"""Extract archived navigation states from HeliCam image labels, without smoothing."""

import csv
import json
import math
import xml.etree.ElementTree as ET
from datetime import datetime
from itertools import pairwise
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
    "raw_qx",
    "raw_qy",
    "raw_qz",
    "raw_qw",
    "raw_x_m",
    "raw_y_m",
    "raw_z_m",
    "sclk_s",
    "source_unix_s",
)


def reference_frame(root, node):
    """Resolve either PDS inline coordinates or a local definition reference."""
    reference = node.find("{*}Coordinate_Space_Reference")
    if reference is None:
        raise ValueError("Missing coordinate-space reference")
    indexed = reference.find("{*}Coordinate_Space_Indexed")
    if indexed is not None:
        return indexed
    local = reference.find("{*}Local_Internal_Reference")
    if (
        local is None
        or local.findtext("{*}local_reference_type") != "to_reference_coordinate_space"
    ):
        raise ValueError("Unsupported coordinate-space reference")
    identifier = local.findtext("{*}local_identifier_reference")
    definitions = [
        item
        for item in root.findall(".//{*}Coordinate_Space_Definition")
        if identifier in [name.text for name in item.findall("{*}local_identifier")]
    ]
    if len(definitions) != 1:
        raise ValueError("Unresolved or ambiguous coordinate-space reference")
    return definitions[0].find("{*}Coordinate_Space_Present/{*}Coordinate_Space_Indexed")


def extract(path, expected_flight=1):
    root = ET.parse(path).getroot()
    candidates = [
        node
        for node in root.findall(".//{*}Coordinate_Space_Definition")
        if node.findtext(
            "{*}Coordinate_Space_Present/{*}Coordinate_Space_Indexed/{*}coordinate_space_frame_type"
        )
        == "HELI_S2_FRAME"
    ]
    if len(candidates) != 1:
        raise ValueError(f"Expected one HELI_S2_FRAME: {path}")
    node = candidates[0]
    indexed = node.find("{*}Coordinate_Space_Present/{*}Coordinate_Space_Indexed")
    if indexed.findtext("{*}solution_id") != "TELEMETRY":
        raise ValueError("Require TELEMETRY solution")
    indices = {
        item.findtext("{*}index_id"): item.findtext("{*}index_value_number")
        for item in indexed.findall("{*}Coordinate_Space_Index")
    }
    flight = int(indices["FLIGHT"])
    if flight < 1 or (expected_flight is not None and flight != expected_flight):
        raise ValueError("Unexpected flight index")
    parent = reference_frame(root, node)
    if parent is None or parent.findtext("{*}coordinate_space_frame_type") != "HELI_G_FRAME":
        raise ValueError("Unexpected parent frame")
    parent_indices = {
        item.findtext("{*}index_id"): item.findtext("{*}index_value_number")
        for item in parent.findall("{*}Coordinate_Space_Index")
    }
    # Early labels spell the HELI_G reference index SITE, while the actual
    # ground-frame definition correctly spells the same index FLIGHT.
    parent_flight = parent_indices.get("FLIGHT", parent_indices.get("SITE", -1))
    ground_definitions = [
        item.find("{*}Coordinate_Space_Present/{*}Coordinate_Space_Indexed")
        for item in root.findall(".//{*}Coordinate_Space_Definition")
        if item.findtext(
            "{*}Coordinate_Space_Present/{*}Coordinate_Space_Indexed/{*}coordinate_space_frame_type"
        )
        == "HELI_G_FRAME"
    ]
    ground_indices = [
        item.findtext("{*}index_value_number")
        for definition in ground_definitions
        for item in definition.findall("{*}Coordinate_Space_Index")
        if item.findtext("{*}index_id") == "FLIGHT"
    ]
    if int(parent_flight) != flight or ground_indices != [str(flight)]:
        raise ValueError("S2 and ground frames belong to different flights")
    offset = node.find("{*}Vector_Origin_Offset")
    position = [float(offset.findtext("{*}" + axis + "_position")) for axis in ("x", "y", "z")]
    if any(child.attrib.get("unit") != "m" for child in offset):
        raise ValueError("Position units must be meters")
    quaternion = node.find("{*}Quaternion_Plus_Direction")
    if quaternion.findtext("{*}rotation_direction") != "Forward":
        raise ValueError("Only forward frame transforms supported")
    w, x, y, z = [
        float(quaternion.findtext("{*}" + key)) for key in ("qcos", "qsin1", "qsin2", "qsin3")
    ]
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if abs(norm - 1) > 1e-5:
        raise ValueError("Non-unit source quaternion")
    # Display frame U = Rx(pi) G: X forward-at-start, Y left, Z up.
    # This rotates the reference frame only; no claim of S2-to-body calibration.
    display_q = [w / norm, -z / norm, y / norm, -x / norm]
    display_pos = [position[0], -position[1], -position[2]]
    utc = root.findtext(".//{*}start_date_time")
    unix = datetime.fromisoformat(utc).timestamp()
    sclk = root.findtext(".//{*}spacecraft_clock_start")
    if sclk is None:
        raise ValueError("Missing spacecraft clock")
    # PDS label uses a decimal seconds count, retaining its fractional precision.
    return {
        "utc": utc,
        "unix": unix,
        "sclk": float(sclk),
        "display": display_q + display_pos,
        "raw": [x, y, z, w] + position,
        "label": path.name,
        "flight": flight,
    }


def main():
    records = sorted(
        (extract(path) for path in (ROOT / "data/raw/helicam").glob("*.xml")),
        key=lambda row: row["unix"],
    )
    if len(records) < 2:
        raise ValueError("Need at least two archive states")
    if any(b["unix"] <= a["unix"] for a, b in pairwise(records)):
        raise ValueError("Duplicate or reversed observation times")
    with (ROOT / "data/derived/flight01_helicam.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        for row in records:
            writer.writerow(
                [
                    row["unix"] - records[0]["unix"],
                    *row["display"],
                    *row["raw"],
                    row["sclk"],
                    row["unix"],
                ]
            )
    report = {
        "source_kind": "archived_navigation_state_at_image_acquisition",
        "measured_high_rate_flight_log": False,
        "rows": len(records),
        "start_utc": records[0]["utc"],
        "end_utc": records[-1]["utc"],
        "duration_s": records[-1]["unix"] - records[0]["unix"],
        "source_frame": "HELI_S2_FRAME relative to HELI_G_FRAME, solution TELEMETRY",
        "display_frame": "Rx(pi) * HELI_G, local Z-up; not geographically ENU",
        "quaternion_display": "Rx(pi) * Q_S2_to_G, normalized; xyzw",
        "max_s2_height_m": max(row["display"][-1] for row in records),
        "notes": [
            "Pose is the IMU S2 origin and sensing axes, not calibrated GLB body pose",
            "No interpolation, invented samples, or historical endpoint padding",
            "Includes post-landing estimates which drift: do not treat these as physical motion",
            "First image occurs during ascent; elapsed zero is first image, not liftoff",
            "HELI_M is static in these labels; it is not used as moving vehicle truth",
        ],
        "labels": [row["label"] for row in records],
    }
    (ROOT / "data/derived/flight01_helicam.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "labels"}, indent=2))


if __name__ == "__main__":
    main()
