"""Deterministic illustrative regolith, not surveyed Jezero terrain. No dependencies."""

import argparse
import json
import math
import random
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def surface(x, y, ripple=False):
    micro = 0.012 * math.sin(x * 3.1 + y * 0.7) * math.sin(y * 2.3)
    if not ripple:
        return micro + 0.025
    # Descriptive dimensions from Jackson et al. 2025, section 2.3.6.
    # Crest is G z=0. Orientation/length/shape are illustrative, not a DEM.
    cross = (0.5 + 0.5 * math.cos(math.pi * x / 3)) if abs(x) < 3 else 0.0
    along = math.exp(-((y / 10) ** 4))
    return -1 + cross * along + micro


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flight59", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets/models")
    args = parser.parse_args()
    rng = random.Random(58)
    vertices, normals, colors, indices = [], [], [], []
    size, step = 161, 0.25
    for j in range(size):
        for i in range(size):
            x, y = (i - 80) * step, (j - 80) * step
            z = surface(x, y, args.flight59)
            vertices.extend((x, y, z))
            nx = -(surface(x + 0.01, y, args.flight59) - surface(x - 0.01, y, args.flight59)) / 0.02
            ny = -(surface(x, y + 0.01, args.flight59) - surface(x, y - 0.01, args.flight59)) / 0.02
            length = math.sqrt(nx * nx + ny * ny + 1)
            normals.extend((nx / length, ny / length, 1 / length))
            shade = rng.uniform(0.65, 1.15) + 0.12 * math.sin(x * 1.7 + y * 0.4)
            blend = max(0, min(1, (20 - max(abs(x), abs(y))) / 5))
            shade = 1 + (shade - 1) * blend
            colors.extend((0.42 * shade, 0.22 * shade, 0.115 * shade, 1))
            if i < size - 1 and j < size - 1:
                k = j * size + i
                indices.extend((k, k + 1, k + size + 1, k, k + size + 1, k + size))
    # Small faceted basalt fragments provide close-range optical-flow features.
    for _ in range(1800):
        x, y = rng.uniform(-19.8, 19.8), rng.uniform(-19.8, 19.8)
        radius = rng.uniform(0.025, 0.18)
        height = radius * rng.uniform(0.3, 1)
        base = surface(x, y, args.flight59) + 0.015
        ring = [
            (x + radius * math.cos(i * math.tau / 6), y + radius * math.sin(i * math.tau / 6), base)
            for i in range(6)
        ]
        top = (x + radius * 0.1, y, height + base)
        for i in range(6):
            triangle = [ring[i], ring[(i + 1) % 6], top]
            u = [b - a for a, b in zip(triangle[0], triangle[1])]
            v = [b - a for a, b in zip(triangle[0], triangle[2])]
            normal = [
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            ]
            length = math.sqrt(sum(n * n for n in normal))
            shade = rng.uniform(0.13, 0.27)
            for point in triangle:
                indices.append(len(vertices) // 3)
                vertices.extend(point)
                normals.extend(n / length for n in normal)
                colors.extend((shade * 1.2, shade, shade * 0.85, 1))
    binary = bytearray()
    views, accessors = [], []
    for values, count, kind, code, components in (
        (vertices, len(vertices) // 3, "VEC3", "f", 5126),
        (normals, len(normals) // 3, "VEC3", "f", 5126),
        (colors, len(colors) // 4, "VEC4", "f", 5126),
        (indices, len(indices), "SCALAR", "I", 5125),
    ):
        block = struct.pack("<" + str(len(values)) + code, *values)
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(block)})
        binary.extend(block)
        accessors.append(
            {
                "bufferView": len(views) - 1,
                "componentType": components,
                "count": count,
                "type": kind,
            }
        )
    accessors[0].update(
        min=[min(vertices[i::3]) for i in range(3)], max=[max(vertices[i::3]) for i in range(3)]
    )
    doc = {
        "asset": {"version": "2.0", "generator": "Ingenuity-HITL / illustrative regolith"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2},
                        "indices": 3,
                        "material": 0,
                    }
                ]
            }
        ],
        "materials": [
            {
                "pbrMetallicRoughness": {
                    "baseColorFactor": [1, 1, 1, 1],
                    "metallicFactor": 0,
                    "roughnessFactor": 1,
                }
            }
        ],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    description = json.dumps(doc, separators=(",", ":")).encode()
    description += b" " * (-len(description) % 4)
    out = struct.pack("<4sII", b"glTF", 2, 28 + len(description) + len(binary))
    out += struct.pack("<II", len(description), 0x4E4F534A) + description
    out += struct.pack("<II", len(binary), 0x004E4942) + binary
    filename = "mars_flight59_terrain.glb" if args.flight59 else "mars_close_terrain.glb"
    path = args.output_dir / filename
    path.write_bytes(out)
    print(f"{path.name}: {len(out):,} bytes")


if __name__ == "__main__":
    main()
