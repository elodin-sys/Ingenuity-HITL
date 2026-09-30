"""Split existing NASA meshes for modeled contra-rotation; no geometry changes."""

import copy
import json
import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rotate(q, v):
    x, y, z, w = q
    a, b, c = v
    tx, ty, tz = 2 * (y * c - z * b), 2 * (z * a - x * c), 2 * (x * b - y * a)
    return [
        a + w * tx + y * tz - z * ty,
        b + w * ty + z * tx - x * tz,
        c + w * tz + x * ty - y * tx,
    ]


def transform(node, point):
    q = node.get("rotation", [0, 0, 0, 1])
    norm = math.sqrt(sum(x * x for x in q))
    v = rotate([x / norm for x in q], [a * b for a, b in zip(point, node.get("scale", [1, 1, 1]))])
    return [a + b for a, b in zip(v, node.get("translation", [0, 0, 0]))]


def main():
    path = ROOT / "assets/models/ingenuity.glb"
    raw = path.read_bytes()
    length = struct.unpack_from("<I", raw, 12)[0]
    original = json.loads(raw[20 : 20 + length])
    tail = raw[20 + length :]

    def write(doc, name):
        encoded = json.dumps(doc, separators=(",", ":")).encode()
        encoded += b" " * (-len(encoded) % 4)
        (path.parent / name).write_bytes(
            struct.pack("<4sII", b"glTF", 2, 20 + len(encoded) + len(tail))
            + struct.pack("<II", len(encoded), 0x4E4F534A)
            + encoded
            + tail
        )

    nodes = original["nodes"]
    indices = {n.get("name"): i for i, n in enumerate(nodes)}
    bus = indices["bus"]
    root = original["scenes"][0]["nodes"][0]
    rotors = [indices["rotors_01"], indices["rotors_02"]]
    doc = copy.deepcopy(original)
    doc["nodes"][bus]["children"] = [i for i in nodes[bus]["children"] if i not in rotors]
    write(doc, "ingenuity_body.glb")
    pivots = []
    for i, rotor in enumerate(rotors):
        pivot = transform(nodes[root], transform(nodes[bus], nodes[rotor]["translation"]))
        pivots.append(pivot)
        doc = copy.deepcopy(original)
        doc["nodes"][bus].pop("mesh", None)
        doc["nodes"][bus]["children"] = [rotor]
        doc["nodes"].append({"children": [root], "translation": [-x for x in pivot]})
        doc["scenes"][0]["nodes"] = [len(doc["nodes"]) - 1]
        write(doc, f"ingenuity_rotor_{i}.glb")
    # Runtime metadata stays ignored along with the generated GLBs.
    (ROOT / "runs").mkdir(exist_ok=True)
    (ROOT / "runs/rotor-pivots.json").write_text(json.dumps(pivots) + "\n")
    print("Prepared body and two centered rotor meshes", pivots)


if __name__ == "__main__":
    main()
