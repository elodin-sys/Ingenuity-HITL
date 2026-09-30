import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
from server import Bench


class WebBenchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 0.0
        self.bench = Bench("test-token", Path(self.temp.name) / "controls", lambda: self.now)
        self.sample = {"time_s": 1, "sequence": 100, "wind_mps": 0, "stiffness": 1, "damping": 1}
        self.bench.publish({"sample": self.sample})

    def test_one_operator_and_expiry(self):
        lease = self.bench.claim()["lease"]
        with self.assertRaises(PermissionError):
            self.bench.claim()
        self.bench.change({"lease": lease, "values": {"stiffness": 1.4}})
        self.assertEqual(self.bench.control_file.read_text().strip(), "1.4 1.0")
        self.now = 31
        self.bench.housekeeping()
        self.assertIsNone(self.bench.lease)
        self.assertEqual(self.bench.controls["stiffness"], 1)

    def test_bounds_and_no_arbitrary_commands(self):
        lease = self.bench.claim()["lease"]
        for values in ({"wind": 61}, {"wind": float("nan")}, {"wind": True}, {"collective": 1}):
            with self.assertRaises(ValueError):
                self.bench.change({"lease": lease, "values": values})
        with self.assertRaises(PermissionError):
            self.bench.change({"lease": "someone-else", "values": {"wind": 2}})

    def test_gust_ends_without_browser_heartbeat(self):
        lease = self.bench.claim()["lease"]
        self.bench.gust({"lease": lease})
        self.assertEqual(self.bench.controls["wind"], 60)
        self.now = 12.0
        self.bench.housekeeping()
        self.assertEqual(self.bench.controls["wind"], 60)
        self.bench.publish({"sample": {**self.sample, "time_s": 9.01}})
        self.assertEqual(self.bench.controls["wind"], 0)

    def test_applied_requires_controller_acknowledgement(self):
        lease = self.bench.claim()["lease"]
        self.bench.change({"lease": lease, "values": {"stiffness": 1.4}})
        self.bench.publish({"sample": self.sample})
        self.assertEqual(self.bench.acknowledged, 0)
        self.bench.publish({"sample": {**self.sample, "stiffness": 1.4}})
        self.assertEqual(self.bench.acknowledged, self.bench.request_id)
        json.dumps(self.bench.snapshot(), allow_nan=False)

    def test_stale_bench_cannot_be_claimed(self):
        self.now = 2.1
        self.assertFalse(self.bench.snapshot()["online"])
        with self.assertRaises(ValueError):
            self.bench.claim()


if __name__ == "__main__":
    unittest.main()
