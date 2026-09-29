"""Fetch immutable source bytes; record origin, UTC retrieval and SHA256."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from datasets import download

ROOT = Path(__file__).resolve().parents[1]
PDS = "https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/"
SOURCES = {
    "data/raw/Mars2020_Camera_SIS.pdf": "https://pds-imaging.jpl.nasa.gov/documentation/Mars2020_Camera_SIS.pdf",
    "data/raw/ingenuity-nasa-original.glb": "https://assets.science.nasa.gov/content/dam/science/cds/3d/resources/model/ingenuity-mars-helicopter/Ingenuity%20Mars%20Helicopter.glb",
    "data/raw/flight-log.pdf": "https://science.nasa.gov/wp-content/uploads/2024/06/ingenuity-helicopter-flight-log.pdf",
}
for collection, stem in [
    ("calibrated", "WE__0058___________CAL_PS__________________P02"),
    ("calibrated", "WE__0058___________CAL_ATS_________________P01"),
    ("derived", "WE__0058___________DER_PS__________________P01"),
    ("derived", "WE__0058___________DER_WS__________________P02"),
]:
    for ext in ("CSV", "xml"):
        name = f"{stem}.{ext}"
        SOURCES[f"data/raw/{name}"] = f"{PDS}data_{collection}_env/sol_0000_0089/sol_0058/{name}"

HELICAM = "https://planetarydata.jpl.nasa.gov/img/data/mars2020/mars2020_helicam/data/sol/00058/ids/edr/heli/"


def main():
    manifest_path = ROOT / "data/sources.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    index_path = ROOT / "data/raw/helicam-sol58-index.html"
    download(HELICAM, index_path)
    SOURCES["data/raw/helicam-sol58-index.html"] = HELICAM
    names = sorted(set(re.findall(r'href="(HNM_[^"/]+EDR[^"/]+\.xml)"', index_path.read_text())))
    if not names:
        raise ValueError("No HeliCam NAV EDR labels discovered")
    for name in names:
        SOURCES[f"data/raw/helicam/{name}"] = HELICAM + name
    for relative, url in SOURCES.items():
        path = ROOT / relative
        download(url, path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        previous = manifest.get(relative)
        if previous and previous["sha256"] != digest:
            raise ValueError(f"Source changed: {relative}; inspect before updating provenance")
        manifest[relative] = previous or {
            "url": url,
            "sha256": digest,
            "bytes": path.stat().st_size,
            "retrieved_utc": datetime.now(UTC).isoformat(),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(relative, path.stat().st_size, flush=True)


if __name__ == "__main__":
    main()
