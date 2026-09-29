import csv
import hashlib
import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from live_monte_carlo import Campaign
from model import CO2_R, MARS_G, MASS_KG, hover, reference
from monte_carlo import run
from prepare_helicam import extract
from replay import COLUMNS, HEADER, PAYLOAD, load_rows, packet
from visual_pose import interpolate, slerp


class PipelineTests(unittest.TestCase):
    def test_incremental_campaign_matches_recorded_samples_and_stops_at_target(self):
        config = json.loads((ROOT / "config/atmosphere.json").read_text())
        config["runs"] = 23
        first, second = Campaign(config), Campaign(config)
        for expected in (10, 20, 23, 23):
            result = first.advance()
            self.assertEqual(result, second.advance())
            self.assertEqual(result[0], expected)
            self.assertAlmostEqual(result[1], expected / 23)
            for start, key in ((2, "density_kgm3"), (5, "ideal_hover_power_w")):
                values = sorted(row[key] for row in first.samples)
                self.assertEqual(
                    result[start : start + 3],
                    tuple(values[round(q * (len(values) - 1))] for q in (0.05, 0.5, 0.95)),
                )

    def test_sources_match_downloaded_checksums(self):
        for relative, record in json.loads((ROOT / "data/sources.json").read_text()).items():
            self.assertEqual(
                hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), record["sha256"]
            )

    def test_native_wire_timestamp_and_pose_layout(self):
        row = load_rows(ROOT / "data/derived/flight01_reconstructed.csv")[250]
        message = packet(row, 123456000000)
        length, kind, identifier, request = HEADER.unpack_from(message)
        self.assertEqual((length, kind, identifier, request), (124, 1, 73, 0))
        stamp, *values = PAYLOAD.unpack(message[8:])
        self.assertEqual(stamp, 123461000000)
        self.assertEqual(values[1:8], [0, 0, 0, 1, 0, 0, 3])

    def test_bad_time_and_quaternion_are_rejected(self):
        good = list(load_rows(ROOT / "data/derived/flight01_reconstructed.csv")[0])
        for rows in ([good, good], [[*good[:4], 2, *good[5:]]]):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "invalid.csv"
                with path.open("w", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(COLUMNS)
                    writer.writerows(rows)
                with self.assertRaises(ValueError):
                    load_rows(path)

    def test_hover_balance_and_density_scaling(self):
        nominal = hover(700, 230)
        dense = hover(1400, 230)
        self.assertAlmostEqual(nominal["density_kgm3"], 700 / (CO2_R * 230))
        self.assertAlmostEqual(nominal["trim_thrust_n"], MASS_KG * MARS_G)
        self.assertEqual(nominal["trim_tilt_deg"], 0)
        self.assertAlmostEqual(
            dense["ideal_hover_power_w"] / nominal["ideal_hover_power_w"], 1 / math.sqrt(2)
        )
        for p in (0, -1, math.nan):
            with self.assertRaises(ValueError):
                hover(p, 230)

    def test_reference_endpoints_and_smooth_ascent(self):
        self.assertEqual(reference(0), (0, 0))
        self.assertEqual(reference(39.1), (0, 0))
        self.assertEqual(reference(10), (3, 0))
        h = 1e-5
        _, velocity = reference(2)
        self.assertAlmostEqual(
            (reference(2 + h)[0] - reference(2 - h)[0]) / (2 * h), velocity, places=7
        )

    def test_monte_carlo_reproducible(self):
        config = json.loads((ROOT / "config/atmosphere.json").read_text())
        config["runs"] = 30
        self.assertEqual(run(config), run(config))
        for row in run(config):
            self.assertGreater(row["ideal_hover_power_w"], 0)
            self.assertGreaterEqual(row["trim_thrust_n"], MASS_KG * MARS_G)

    def test_glb_container_and_no_unsupported_compression(self):
        data = (ROOT / "assets/models/ingenuity.glb").read_bytes()
        magic, version, length = struct.unpack_from("<4sII", data)
        self.assertEqual((magic, version, length), (b"glTF", 2, len(data)))
        count, kind = struct.unpack_from("<II", data, 12)
        self.assertEqual(kind, 0x4E4F534A)
        gltf = json.loads(data[20 : 20 + count])
        unsupported = {
            "KHR_draco_mesh_compression",
            "EXT_meshopt_compression",
            "KHR_mesh_quantization",
            "KHR_texture_basisu",
            "EXT_texture_webp",
            "EXT_mesh_gpu_instancing",
        }
        self.assertFalse(set(gltf.get("extensionsUsed", [])) & unsupported)
        self.assertTrue(
            all(image.get("mimeType") in {"image/png", "image/jpeg"} for image in gltf["images"])
        )
        provenance = json.loads((ROOT / "assets/models/PROVENANCE.json").read_text())
        self.assertEqual(hashlib.sha256(data).hexdigest(), provenance["output_sha256"])

    def test_archive_is_moving_s2_and_reference_rotation_preserves_distance(self):
        records = sorted(
            (extract(path) for path in (ROOT / "data/raw/helicam").glob("*.xml")),
            key=lambda row: row["unix"],
        )
        self.assertEqual(len(records), 15)
        self.assertAlmostEqual(max(row["display"][-1] for row in records), 3.2535007, places=5)
        for record in records:
            self.assertAlmostEqual(
                sum(v * v for v in record["display"][4:]), sum(v * v for v in record["raw"][4:])
            )
            self.assertAlmostEqual(record["display"][-1], -record["raw"][-1])

    def test_interpolation_shortest_arc_and_no_extrapolation(self):
        self.assertEqual(slerp((0, 0, 0, 1), (0, 0, 0, -1), 0.5), (0, 0, 0, 1))
        rows = [(0, 0, 0, 0, 1, 0, 0, 2), (1.01, 0, 0, 1, 0, 1, 0, 3)]
        display = list(interpolate(rows))
        self.assertEqual(display[0], (0, (0, 0, 0, 1, 0, 0, 2)))
        self.assertEqual(display[-1][0], 1.01)
        self.assertEqual(display[-1][1][-3:], (1, 0, 3))
        for elapsed, pose in display:
            self.assertLessEqual(elapsed, 1.01)
            self.assertAlmostEqual(sum(v * v for v in pose[:4]), 1)

    def test_meda_missing_values_never_become_weather(self):
        with (ROOT / "data/derived/meda_sol58.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 616)
        self.assertEqual(sum(row["wind_valid"] == "1" for row in rows), 602)
        for row in rows:
            self.assertTrue(0 < float(row["pressure_pa"]) < 2000)
            self.assertTrue(100 < float(row["ats_local_temp1_k"]) < 400)
            if row["wind_valid"] == "1":
                self.assertLess(float(row["wind_mps"]), 100)
            else:
                self.assertEqual(row["wind_mps"], "")


if __name__ == "__main__":
    unittest.main()
