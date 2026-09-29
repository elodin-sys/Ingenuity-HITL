"""Apply one repeating regolith texture to both near and distant procedural terrain."""

import hashlib
import json
import random
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def texture():
    rng = random.Random(20210419)
    size = 512
    scanlines = bytearray()
    grids = [
        (n, amplitude, [rng.uniform(-1, 1) for _ in range(n * n)])
        for n, amplitude in ((4, 12), (16, 13), (64, 8))
    ]
    for y in range(size):
        scanlines.append(0)
        for x in range(size):
            # Seamless random value noise, without artificial directional stripes.
            brightness = 205 + rng.uniform(-9, 9)
            for n, amplitude, grid in grids:
                u, v = x * n / size, y * n / size
                i, j = int(u), int(v)
                u, v = u - i, v - j
                u, v = u * u * (3 - 2 * u), v * v * (3 - 2 * v)
                a, b = grid[j * n + i], grid[j * n + (i + 1) % n]
                c, d = grid[((j + 1) % n) * n + i], grid[((j + 1) % n) * n + (i + 1) % n]
                brightness += amplitude * (
                    (1 - v) * ((1 - u) * a + u * b) + v * ((1 - u) * c + u * d)
                )
            scanlines.append(round(max(0, min(255, brightness))))
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(scanlines))
        + png_chunk(b"IEND", b"")
    )


def apply(path, image, distant=False):
    raw = path.read_bytes()
    length = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20 : 20 + length])
    if doc.get("extras", {}).get("ingenuity_regolith_texture") == 2:
        return
    binary = bytearray(raw[28 + length :])

    def view(data):
        binary.extend(b"\0" * (-len(binary) % 4))
        doc["bufferViews"].append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)})
        binary.extend(data)
        return len(doc["bufferViews"]) - 1

    primitive = doc["meshes"][0]["primitives"][0]
    accessor = doc["accessors"][primitive["attributes"]["POSITION"]]
    buffer = doc["bufferViews"][accessor["bufferView"]]
    if accessor["componentType"] != 5126 or accessor["type"] != "VEC3":
        raise ValueError("Expected uncompressed float32 terrain positions")
    offset = buffer.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = buffer.get("byteStride", 12)
    uv = []
    for index in range(accessor["count"]):
        x, y, _ = struct.unpack_from("<3f", binary, offset + stride * index)
        uv.extend((x / 4, y / 4))
    doc["accessors"].append(
        {
            "bufferView": view(struct.pack("<" + str(len(uv)) + "f", *uv)),
            "componentType": 5126,
            "count": accessor["count"],
            "type": "VEC2",
        }
    )
    primitive["attributes"]["TEXCOORD_0"] = len(doc["accessors"]) - 1
    images = doc.setdefault("images", [])
    images.append({"bufferView": view(image), "mimeType": "image/png"})
    samplers = doc.setdefault("samplers", [])
    samplers.append({"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})
    textures = doc.setdefault("textures", [])
    textures.append({"source": len(images) - 1, "sampler": len(samplers) - 1})
    material = doc["materials"][primitive["material"]]["pbrMetallicRoughness"]
    material["baseColorTexture"] = {"index": len(textures) - 1}
    if distant:
        primitive["attributes"].pop("COLOR_0", None)
        material["baseColorFactor"] = [0.42, 0.22, 0.115, 1]
    doc.setdefault("extras", {})["ingenuity_regolith_texture"] = 2
    binary.extend(b"\0" * (-len(binary) % 4))
    doc["buffers"][0]["byteLength"] = len(binary)
    encoded = json.dumps(doc, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, 28 + len(encoded) + len(binary))
        + struct.pack("<II", len(encoded), 0x4E4F534A)
        + encoded
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )


def main():
    image = texture()
    apply(ROOT / "assets/models/mars_terrain.glb", image, distant=True)
    apply(ROOT / "assets/models/mars_close_terrain.glb", image)
    provenance_path = ROOT / "assets/PROVENANCE.json"
    provenance = json.loads(provenance_path.read_text())
    for name in ("mars_terrain.glb", "mars_close_terrain.glb"):
        data = (ROOT / "assets/models" / name).read_bytes()
        provenance[name].update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
