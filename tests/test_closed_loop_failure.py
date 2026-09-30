"""Run with: uv run --with elodin==0.19.2 python -m unittest discover -s tests."""

import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("elodin"), "requires the Elodin SDK")
class ControllerFailureTest(unittest.TestCase):
    def test_disconnect_cancels_the_run(self):
        with socket.socket() as listener, tempfile.TemporaryDirectory() as directory:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(20)
            controller_port = listener.getsockname()[1]

            def reply_then_disconnect():
                connection, _ = listener.accept()
                with connection, connection.makefile("rb") as reader:
                    connection.settimeout(10)
                    for _ in range(4):
                        sequence = reader.readline().split()[0].decode()
                        connection.sendall(f"{sequence} 0 0 0 0 0 0.35 0 0 0\n".encode())

            worker = threading.Thread(target=reply_then_disconnect, daemon=True)
            worker.start()
            recording = Path(directory) / "flight"
            # Reserve an available listener number for this isolated SDK run.
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                db_port = probe.getsockname()[1]
            result = subprocess.run(
                [
                    sys.executable,
                    "sim/main.py",
                    "--controller",
                    f"127.0.0.1:{controller_port}",
                    "--db-addr",
                    f"127.0.0.1:{db_port}",
                    "--duration",
                    "2",
                    "--db",
                    str(recording),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=40,
            )
            worker.join(timeout=2)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Closed-loop simulation stopped", result.stderr)
            samples = json.loads(recording.with_suffix(".json").read_text())["samples"]
            self.assertEqual(len(samples), 4)
            # Before the fix the SDK silently integrated all 200 requested steps.
            self.assertNotIn("simulation cycles:  100", result.stdout)


if __name__ == "__main__":
    unittest.main()
