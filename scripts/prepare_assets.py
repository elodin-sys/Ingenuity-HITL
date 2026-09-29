"""Materialize ignored runtime GLBs; preserve the validated workshop asset bytes."""

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from align_model import align
from texture_terrain import apply, texture

ROOT = Path(__file__).resolve().parents[1]


def checked(data, digest, label):
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Checksum mismatch: {label}; source or conversion changed")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets/models")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "assets/PROVENANCE.json").read_text())
    names = (
        "mars_terrain.glb",
        "mars_close_terrain.glb",
        "mars_flight59_terrain.glb",
        "ingenuity.glb",
    )
    # A temporary sibling makes installation atomic on the destination filesystem.
    with tempfile.TemporaryDirectory(dir=args.output_dir) as staging:
        stage = Path(staging)
        image = None
        for name in names:
            target = args.output_dir / name
            digest = manifest[name]["sha256"]
            if target.exists():
                checked(target.read_bytes(), digest, name)
                continue
            output = stage / name
            if name in ("mars_terrain.glb", "mars_close_terrain.glb"):
                output.write_bytes(
                    gzip.decompress((ROOT / "asset-sources" / (name + ".gz")).read_bytes())
                )
            elif name.startswith("mars_"):
                command = [
                    sys.executable,
                    str(ROOT / "scripts/build_close_terrain.py"),
                    "--output-dir",
                    str(stage),
                ]
                if "flight59" in name:
                    command.append("--flight59")
                subprocess.run(command, check=True)
                if image is None:
                    image = texture()
                apply(output, image)
            else:
                relative = "data/raw/ingenuity-nasa-original.glb"
                source = json.loads((ROOT / "data/sources.json").read_text())[relative]
                cached = ROOT / relative
                if cached.exists():
                    data = cached.read_bytes()
                else:
                    with urllib.request.urlopen(source["url"], timeout=120) as response:
                        data = response.read()
                original = stage / "original.glb"
                original.write_bytes(checked(data, source["sha256"], "NASA original"))
                subprocess.run(
                    [
                        "npx",
                        "--yes",
                        "--package=node@22",
                        "--package=@gltf-transform/cli@4.5.1",
                        "gltf-transform",
                        "png",
                        str(original),
                        str(output),
                        "--formats",
                        "*",
                    ],
                    check=True,
                )
                align(output)
            checked(output.read_bytes(), digest, name)
            output.replace(target)
            print(f"Prepared {name}", flush=True)
    print("Runtime assets verified.")


if __name__ == "__main__":
    main()
