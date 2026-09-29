import json
import math
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from replay_helicam import data_path
from solar import declination, lighting, rotate
from visual_pose import interpolate


class ScienceSelectionTests(unittest.TestCase):
    def test_mars24_published_declination_benchmarks(self):
        # NASA GISS published examples; independent reference values.
        for utc, expected in [
            ("2000-01-06T00:00:00+00:00", -25.22825),
            ("2004-01-03T13:46:31+00:00", -13.42065),
        ]:
            value = declination(datetime.fromisoformat(utc).timestamp(), 64.184)
            # Published examples and revised coefficients differ below 0.001 deg.
            self.assertAlmostEqual(value, expected, delta=0.001)

    def test_sun_frame_inverse_and_shadow(self):
        path = ROOT / "data/derived/sol00058_lighting.json"
        report = json.loads(path.read_text())
        for row in report["samples"]:
            x, y, z = row["direction_local_z_up"]
            north, east, down = rotate(row["g_to_site_wxyz"], (x, -y, -z))
            azimuth = math.degrees(math.atan2(east, north)) % 360
            self.assertAlmostEqual(azimuth, row["azimuth_from_north_deg"])
            self.assertAlmostEqual(math.degrees(math.asin(-down)), row["elevation_deg"])
            shadow_offset = 3 * math.hypot(x, y) / z
            self.assertGreater(shadow_offset, 0.30)
            self.assertLess(shadow_offset, 0.34)
        self.assertEqual(report, lighting((ROOT / "data/raw/helicam").glob("*.xml")))

    def test_large_observation_gaps_are_not_filled(self):
        rows = [
            (0, 0, 0, 0, 1, 0, 0, 3),
            (2, 0, 0, 0, 1, 1, 0, 3),
            (10000, 0, 0, 0, 1, 2, 0, 3),
            (10002, 0, 0, 0, 1, 3, 0, 3),
        ]
        result = list(interpolate(rows))
        self.assertLess(len(result), 130)
        self.assertFalse(any(2 < t < 10000 for t, _ in result))
        self.assertEqual(result[-1], (10002, tuple(rows[-1][1:])))

    def test_replay_path_cannot_escape_derived_data(self):
        for path in ("/etc/passwd", "data/derived/../../../.ssh/config"):
            with self.assertRaises(ValueError):
                data_path(path)

    def test_second_flight_has_no_substituted_weather(self):
        metadata = json.loads((ROOT / "data/derived/sol00061.json").read_text())
        self.assertEqual(metadata["flight"], 2)
        self.assertIsNone(metadata["meda_csv"])
        self.assertEqual(metadata["rows"], 17)


if __name__ == "__main__":
    unittest.main()
