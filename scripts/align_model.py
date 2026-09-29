"""Apply an explicit display-only alignment to a decoded NASA GLB."""

import hashlib
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def align(path):
    data = path.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20 : 20 + length])
    name = "NASA Y-up to workshop Z-up; illustrative IMU alignment"
    rotation = [math.sqrt(0.5), 0, 0, math.sqrt(0.5)]
    translation = [0, 0, -0.192481545]
    if not any(node.get("name") == name for node in doc["nodes"]):
        doc["nodes"].append(
            {
                "name": name,
                "children": doc["scenes"][0]["nodes"],
                "rotation": rotation,
                "translation": translation,
            }
        )
        doc["scenes"][0]["nodes"] = [len(doc["nodes"]) - 1]
        encoded = json.dumps(doc, separators=(",", ":")).encode()
        encoded += b" " * (-len(encoded) % 4)
        tail = data[20 + length :]
        path.write_bytes(
            struct.pack("<4sII", b"glTF", 2, 20 + len(encoded) + len(tail))
            + struct.pack("<II", len(encoded), 0x4E4F534A)
            + encoded
            + tail
        )


def main():
    path = ROOT / "assets/models/ingenuity.glb"
    align(path)
    rotation = [math.sqrt(0.5), 0, 0, math.sqrt(0.5)]
    translation = [0, 0, -0.192481545]
    provenance = path.parent / "PROVENANCE.json"
    record = json.loads(provenance.read_text())
    record["visual_alignment"] = {
        "rotation_xyzw": rotation,
        "translation_m": translation,
        "calibrated": False,
    }
    record["output_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    provenance.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
