import csv
import json
import math
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_helicam import extract
from trajectory_monte_carlo import (
    BOUNDS,
    LiveCampaign,
    at,
    campaign,
    reference_schedule,
    score,
    simulate,
)


class Flight59(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "data/derived/sol00915.csv").read_bytes()
        cls.rows = [
            tuple(map(float, row)) for row in list(csv.reader(cls.source.decode().splitlines()))[1:]
        ]

    def test_archived_transforms_and_endpoint_coverage(self):
        metadata = json.loads((ROOT / "data/derived/sol00915.json").read_text())
        records = sorted(
            (
                extract(ROOT / "data/raw/datasets/sol00915" / name, 59)
                for name in metadata["sources"]
            ),
            key=lambda r: r["unix"],
        )
        self.assertEqual(len(records), 180)
        for record, row in zip(records, self.rows):
            self.assertEqual(tuple(record["display"]), row[1:8])
            self.assertEqual(tuple(record["raw"]), row[8:15])
        self.assertGreater(self.rows[0][7], 0.5)
        self.assertGreater(self.rows[-1][7], 3)
        self.assertAlmostEqual(self.rows[-1][0], 137.7353389263153)

    def test_local_reference_cannot_silently_change_parent(self):
        path = next((ROOT / "data/raw/datasets/sol00915").glob("*.xml"))
        tree = ET.parse(path)
        for node in tree.findall(".//{*}local_identifier_reference"):
            if node.text == "HELI_G_FRAME_59":
                node.text = "MISSING_FRAME"
        with tempfile.TemporaryDirectory() as folder:
            mutated = Path(folder) / "bad.xml"
            tree.write(mutated)
            with self.assertRaisesRegex(ValueError, "Unresolved"):
                extract(mutated, 59)

    def test_physical_hover_equilibrium(self):
        rows = [(0, 0, 0, 0, 1, 0, 0, 4), (10, 0, 0, 0, 1, 0, 0, 4)]
        params = {k: sum(v) / 2 for k, v in BOUNDS.items()}
        params.update(wind_x_mps=0, wind_y_mps=0, thrust_gain=1, reference_shift_s=0)
        path = simulate(rows, [(0, 4), (10, 4)], params)
        self.assertEqual(score(rows, path), 0)
        with self.assertRaises(ValueError):
            at(path, 11)

    def test_seeded_selection_and_integration_convergence(self):
        a = campaign(self.rows, self.source, draws=12)
        b = campaign(self.rows, self.source, draws=12)
        self.assertEqual(a["best"], b["best"])
        self.assertEqual(a["best"]["rmse_m"], min(r["rmse_m"] for r in a["samples"]))
        self.assertEqual(a["best"]["rmse_m"], score(self.rows, a["path"]))
        self.assertEqual(score(self.rows, json.loads(json.dumps(a))["path"]), a["best"]["rmse_m"])
        fine = simulate(self.rows, reference_schedule(self.rows), a["best"]["parameters"], dt=0.025)
        rms_difference = math.sqrt(
            sum(math.dist(at(fine, r[0]), at(a["path"], r[0])) ** 2 for r in self.rows)
            / len(self.rows)
        )
        self.assertLess(rms_difference, 0.025)

    def test_live_winner_is_best_of_every_completed_prefix(self):
        live = LiveCampaign(self.rows, self.source, draws=12)
        for index in range(12):
            live.advance(index)
            self.assertEqual(len(live.samples), index + 1)
            self.assertEqual(live.best["rmse_m"], min(r["rmse_m"] for r in live.samples))
            self.assertEqual(score(self.rows, live.path), live.best["rmse_m"])
        self.assertEqual(live.best, campaign(self.rows, self.source, draws=12)["best"])
        with self.assertRaisesRegex(ValueError, "complete"):
            live.advance(12)


if __name__ == "__main__":
    unittest.main()
