"""Discover NASA HeliCam NAV archives, prepare a selected sol, and choose a replay."""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from prepare_helicam import COLUMNS, extract
from solar import lighting

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/catalog.json"
API = "https://pds-imaging.jpl.nasa.gov/api"
QUERY = {
    "bool": {
        "filter": [
            {"term": {"bundle_id": "mars2020_helicam"}},
            {"term": {"collection_id": "data"}},
            {"wildcard": {"archive.name": "HNM*EDR*.xml"}},
        ]
    }
}


def download(url, path):
    """Use system trust on macOS; never disable certificate verification."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        curl = "/usr/bin/curl" if sys.platform == "darwin" else "curl"
        subprocess.run(
            [
                curl,
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--retry",
                "2",
                "--max-time",
                "90",
                url,
                "-o",
                str(temporary),
            ],
            check=True,
        )
        temporary.replace(path)
    return {
        "url": url,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "retrieved_utc": datetime.now(UTC).isoformat(),
    }


def search(query, path):
    url = (
        API
        + "/search/atlas/_search?"
        + urlencode({"source": json.dumps(query), "source_content_type": "application/json"})
    )
    provenance = download(url, path)
    result = json.loads(path.read_text())
    if result.get("timed_out") or result.get("_shards", {}).get("failed", 0):
        raise ValueError("Incomplete PDS search; retain the previous catalog")
    return result, provenance


def refresh():
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    query = {
        "size": 0,
        "track_total_hits": True,
        "query": QUERY,
        "aggs": {
            "sols": {
                "terms": {"field": "archive.parent_uri", "size": 512},
                "aggs": {
                    "sample": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"archive.name": "asc"}],
                            "_source": ["uri", "archive.name"],
                        }
                    }
                },
            }
        },
    }
    result, provenance = search(query, ROOT / f"data/raw/catalog/{stamp}.json")
    aggregation = result["aggregations"]["sols"]
    if aggregation["sum_other_doc_count"] or aggregation["doc_count_error_upper_bound"]:
        raise ValueError("Truncated catalog; increase the aggregation limit")
    entries = []
    for bucket in aggregation["buckets"]:
        parent = bucket["key"]
        match = re.search(r"/data/sol/(\d{5})/ids/edr/heli$", parent)
        if not match:
            continue
        sol = int(match[1])
        sample = bucket["sample"]["hits"]["hits"][0]["_source"]
        flight = re.search(r"_N(\d{3})\d{4}HELI", sample["archive"]["name"])
        entries.append(
            {
                "id": f"sol{sol:05d}",
                "sol": sol,
                "flight_hint": int(flight[1]) if flight else None,
                "labels": bucket["doc_count"],
                "parent_uri": parent,
                "sample_uri": sample["uri"],
                "kind": "archived_navigation_at_image_acquisition",
                "status": "indexed; pose validation occurs on preparation",
            }
        )
    entries.sort(key=lambda item: item["sol"])
    record = {
        "source": API,
        "retrieved_utc": datetime.now(UTC).isoformat(),
        "inventory_provenance": provenance,
        "entries": entries,
        "scope": "All NAV EDR XML sol groups indexed in this PDS Atlas snapshot; not full flight logs",
    }
    CATALOG.write_text(json.dumps(record, indent=2) + "\n")
    print(f"{len(entries)} sol groups indexed from NASA PDS Atlas", file=sys.stderr)


def entries():
    if not CATALOG.exists():
        refresh()
    return json.loads(CATALOG.read_text())["entries"]


def prepared_path(identifier):
    if identifier == "sol00058" and not (ROOT / "data/derived/sol00058.json").exists():
        return ROOT / "data/derived/flight01_helicam.json"
    if not re.fullmatch(r"sol\d{5}", identifier):
        raise ValueError("Dataset ID must be solNNNNN")
    return ROOT / f"data/derived/{identifier}.json"


def prepare(identifier):
    existing = prepared_path(identifier)
    if existing.exists():
        metadata = json.loads(existing.read_text())
        raw_folder = ROOT / f"data/raw/datasets/{identifier}"
        if identifier == "sol00058" or (
            metadata.get("sources")
            and all((raw_folder / name).exists() for name in metadata["sources"])
        ):
            return existing
    entry = next((item for item in entries() if item["id"] == identifier), None)
    if entry is None:
        raise ValueError(f"Unknown dataset {identifier}; refresh the catalog")
    query = {
        "size": 10000,
        "track_total_hits": True,
        "query": {
            "bool": {"filter": [QUERY, {"term": {"archive.parent_uri": entry["parent_uri"]}}]}
        },
        "_source": ["uri", "archive.name", "release_id", "archive.md5"],
        "sort": [{"archive.name": "asc"}],
    }
    folder = ROOT / f"data/raw/datasets/{identifier}"
    result, inventory_provenance = search(query, folder / "release-index.json")
    hits = result["hits"]
    if hits["total"]["relation"] != "eq" or hits["total"]["value"] != len(hits["hits"]):
        raise ValueError("Truncated product list; refusing an incomplete import")

    def retrieve(hit):
        source = hit["_source"]
        name = source["archive"]["name"]
        if not re.fullmatch(r"HNM_[A-Za-z0-9_]+\.xml", name):
            raise ValueError("Unexpected source filename")
        path = folder / name
        release = source.get("release_id")
        suffix = f"::{release}" if release is not None else ""
        provenance = download(API + "/data/" + source["uri"] + suffix, path)
        expected_md5 = source["archive"].get("md5")
        if expected_md5 and hashlib.md5(path.read_bytes()).hexdigest() != expected_md5:
            raise ValueError("PDS product differs from indexed checksum")
        record = extract(path, expected_flight=None)
        return record, provenance

    print(
        f"Downloading and checking {len(hits['hits'])} labels for {identifier}...", file=sys.stderr
    )
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(retrieve, hits["hits"]))
    records = {}
    duplicates = []
    for record, _ in results:
        if record["unix"] in records:
            old = records[record["unix"]]
            if old["raw"] != record["raw"] or old["flight"] != record["flight"]:
                raise ValueError("Conflicting poses at the same acquisition time")
            duplicates.append(old["label"])
        records[record["unix"]] = record
    ordered = sorted(records.values(), key=lambda item: item["unix"])
    if len(ordered) < 2 or len({r["flight"] for r in ordered}) != 1:
        raise ValueError("Replay requires >=2 observations from one flight frame")
    gaps = [b["unix"] - a["unix"] for a, b in zip(ordered, ordered[1:])]
    # Large observation gaps are retained, but display interpolation is disabled across them.
    report = {
        "id": identifier,
        "sol": entry["sol"],
        "flight": ordered[0]["flight"],
        "source_kind": "archived_navigation_state_at_image_acquisition",
        "measured_high_rate_flight_log": False,
        "rows": len(ordered),
        "start_utc": ordered[0]["utc"],
        "end_utc": ordered[-1]["utc"],
        "duration_s": ordered[-1]["unix"] - ordered[0]["unix"],
        "largest_gap_s": max(gaps),
        "duplicate_products": duplicates,
        "csv": f"data/derived/{identifier}.csv",
        "meda_csv": None,
        "inventory_provenance": inventory_provenance,
        "sources": {record["label"]: provenance for record, provenance in results},
        "notes": [
            "S2 IMU navigation estimates, not calibrated mesh body pose",
            "May include stationary captures and post-landing drift",
            "No MEDA from another sol is substituted",
            "No display interpolation across observation gaps greater than 10 s",
        ],
    }
    with (ROOT / report["csv"]).open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        for record in ordered:
            writer.writerow(
                [
                    record["unix"] - ordered[0]["unix"],
                    *record["display"],
                    *record["raw"],
                    record["sclk"],
                    record["unix"],
                ]
            )
    existing.write_text(json.dumps(report, indent=2) + "\n")
    return existing


def select(identifier=None):
    if identifier is None:
        choices = [item for item in entries() if (item["flight_hint"] or 0) > 0]
        print("NASA HeliCam — poses de navigation archivées (pas des logs 500 Hz)", file=sys.stderr)
        for index, item in enumerate(choices, 1):
            ready = prepared_path(item["id"]).exists()
            print(
                f"{index:3}. Sol {item['sol']:04} · vol indicatif {item['flight_hint']:02} · "
                f"{item['labels']:4} labels · {'prêt' if ready else 'à télécharger'}",
                file=sys.stderr,
            )
        response = input("Numéro du jeu (Entrée = sol 58 / vol 1) : ").strip()
        if not response:
            identifier = "sol00058"
        elif response.isdigit() and 1 <= int(response) <= len(choices):
            identifier = choices[int(response) - 1]["id"]
        else:
            raise ValueError("Invalid dataset selection")
    path = prepare(identifier)
    metadata = json.loads(path.read_text())
    if identifier == "sol00058":
        metadata.update(
            id=identifier,
            sol=58,
            flight=1,
            csv="data/derived/flight01_helicam.csv",
            meda_csv="data/derived/meda_sol58.csv",
        )
    metadata["interpolation_max_gap_s"] = 10
    if metadata.get("flight") == 59:
        with (ROOT / metadata["csv"]).open() as stream:
            poses = list(csv.DictReader(stream))
        metadata["coverage"] = {
            "liftoff_observed": False,
            "touchdown_observed": False,
            "first_s2_height_m": float(poses[0]["z_m"]),
            "last_s2_height_m": float(poses[-1]["z_m"]),
            "note": "Archive starts during ascent and ends during descent; no endpoint padding",
        }
    solar_path = ROOT / f"data/derived/{identifier}_lighting.json"
    if not solar_path.exists():
        folder = (
            ROOT / "data/raw/helicam"
            if identifier == "sol00058"
            else ROOT / f"data/raw/datasets/{identifier}"
        )
        solar_path.write_text(json.dumps(lighting(folder.glob("*.xml")), indent=2) + "\n")
    metadata["lighting"] = json.loads(solar_path.read_text())
    direction = metadata["lighting"]["static_direction"]["direction_local_z_up"]
    schematic = (ROOT / "assets/schematics/main.kdl").read_text()
    schematic = re.sub(
        r"MARS 2020 · INGENUITY · FLIGHT \d+ · SOL \d+",
        f"MARS 2020 · INGENUITY · FLIGHT {metadata['flight']:02} · SOL {metadata['sol']}",
        schematic,
    )
    if metadata.get("flight") != 59:
        schematic = schematic.replace("mars_flight59_terrain.glb", "mars_close_terrain.glb")
        schematic = schematic.replace('"(0,0,0,1,0,0,-0.4)"', '"(0,0,0,1,0,0,0.6)"')
        schematic = re.sub(r"line_3d best\.world_pos[^}]+}\n", "", schematic)
        schematic = re.sub(r"object_3d[^\n]*best\.world_pos[^}]+}\n}", "", schematic)
        schematic = schematic.replace(
            'component_name="comparison.error" name="ORANGE MODEL · GAP / m"',
            'component_name="helicam.sclk" name="SOURCE CLOCK / s"',
        )
        schematic = schematic.replace(
            'component_name="comparison.rmse" name="BEST MC · FIT RMSE / m"',
            'component_name="mc.power_p50" name="HOVER MODEL MEDIAN / W"',
        )
        schematic = schematic.replace(
            'component_name="comparison.draws"', 'component_name="mc.draws"'
        )
    schematic = re.sub(
        r'sun direction="[^"]+"',
        'sun direction="(' + ",".join(f"{v:.10f}" for v in direction) + ')"',
        schematic,
    )
    (ROOT / "assets/schematics/selected.kdl").write_text(schematic)
    (ROOT / "config/selection.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(
        f"Selected flight {metadata['flight']}, sol {metadata['sol']}: {metadata['rows']} archive states",
        file=sys.stderr,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["list", "refresh", "prepare", "select"])
    parser.add_argument("dataset", nargs="?")
    args = parser.parse_args()
    if args.command == "refresh":
        refresh()
    elif args.command == "list":
        for item in entries():
            print(
                f"{item['id']}  flight~{str(item['flight_hint']):>2}  {item['labels']:4} labels  "
                f"{'ready' if prepared_path(item['id']).exists() else 'download'}"
            )
    elif args.command == "prepare":
        if not args.dataset:
            parser.error("prepare requires solNNNNN")
        print(prepare(args.dataset))
    else:
        select(args.dataset)


if __name__ == "__main__":
    main()
