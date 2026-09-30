"""Pi-hosted web controls and telemetry relay. Standard library only; no physics here."""

import argparse
import base64
import hmac
import json
import math
import secrets
import threading
import time
from collections import deque
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DEFAULT = {"wind": 0.0, "stiffness": 1.0, "damping": 1.0}
LIMITS = {"wind": (-60.0, 60.0), "stiffness": (0.2, 2.0), "damping": (0.6, 1.6)}


class Bench:
    def __init__(self, token, control_file, clock=time.monotonic):
        self.token, self.control_file, self.clock = token, Path(control_file), clock
        self.lock = threading.RLock()
        self.controls = dict(DEFAULT)
        self.lease, self.expires = None, 0
        self.last_bridge = -1e9
        self.sequence = 0
        self.latest = None
        self.frame = None
        self.events = deque(maxlen=30)
        self.last_change = -1e9
        self.gust_until = 0
        self.request_id, self.acknowledged = 0, 0
        self.control_file.parent.mkdir(parents=True, exist_ok=True)

    def event(self, text):
        self.sequence += 1
        self.events.append({"id": self.sequence, "text": text})

    def housekeeping(self):
        with self.lock:
            if self.gust_until and self.latest and self.latest["time_s"] >= self.gust_until:
                self.gust_until = 0
                self.controls["wind"] = 0.0
                self.event("Gust ended. Wind returns to zero.")
            if self.lease and self.clock() >= self.expires:
                self.lease = None
                self.controls = dict(DEFAULT)
                self.gust_until = 0
                self.event("Control session expired. Nominal settings restored.")
            # Rust consumes only these bounded numbers, never a browser command.
            target = self.control_file.with_suffix(".tmp")
            target.write_text(f"{self.controls['stiffness']} {self.controls['damping']}\n")
            target.replace(self.control_file)

    def claim(self, supplied=None):
        with self.lock:
            self.housekeeping()
            if self.clock() - self.last_bridge > 2:
                raise ValueError("Bench offline. Controls are unavailable during replay.")
            if self.lease and supplied != self.lease:
                raise PermissionError("Another visitor has control.")
            if not self.lease:
                self.lease = secrets.token_urlsafe(24)
                self.event("A visitor took control.")
            self.expires = self.clock() + 30
            return {"lease": self.lease, "expires_in_s": 30}

    def change(self, payload):
        with self.lock:
            self.housekeeping()
            if not self.lease or payload.get("lease") != self.lease:
                raise PermissionError("Take control before changing a setting.")
            if self.clock() - self.last_bridge > 2:
                raise ValueError("Bench offline")
            if self.clock() - self.last_change < 0.1:
                raise ValueError("Wait briefly before changing another setting.")
            values = payload.get("values", {})
            if not isinstance(values, dict) or not values or set(values) - set(LIMITS):
                raise ValueError("Unknown control")
            for key, value in values.items():
                lo, hi = LIMITS[key]
                if (
                    type(value) not in (float, int)
                    or not math.isfinite(value)
                    or not lo <= value <= hi
                ):
                    raise ValueError(f"{key} must be between {lo} and {hi}")
            self.controls.update(values)
            if "wind" in values:
                self.gust_until = 0
            self.last_change = self.clock()
            self.expires = self.clock() + 30
            self.event("Requested: " + ", ".join(f"{k} {v:g}" for k, v in values.items()))
            self.request_id = self.sequence
            self.housekeeping()
            return {"requested": self.controls, "event_id": self.sequence}

    def gust(self, payload):
        with self.lock:
            result = self.change({"lease": payload.get("lease"), "values": {"wind": 60.0}})
            self.gust_until = self.latest["time_s"] + 8
            self.event(
                "Severe synthetic gust: 60 m/s for 8 simulation seconds; not reconstructed Mars weather."
            )
            return result

    def publish(self, payload):
        with self.lock:
            sample = payload.get("sample")
            if not isinstance(sample, dict) or not isinstance(sample.get("time_s"), (int, float)):
                raise ValueError("Missing telemetry sample")
            if self.latest and sample["time_s"] < self.latest["time_s"]:
                self.frame = None
                self.event("New flight recording started.")
            self.latest = sample
            self.last_bridge = self.clock()
            if self.request_id != self.acknowledged and all(
                abs(sample.get(field, -999) - self.controls[key]) < tolerance
                for field, key, tolerance in (
                    ("wind_mps", "wind", 0.25),
                    ("stiffness", "stiffness", 0.001),
                    ("damping", "damping", 0.001),
                )
            ):
                self.acknowledged = self.request_id
                self.event(f"Applied settings confirmed at step {sample.get('sequence', '?')}.")
            if payload.get("frame"):
                frame = base64.b64decode(payload["frame"], validate=True)
                if not frame.startswith(b"\x89PNG\r\n\x1a\n") or len(frame) > 400_000:
                    raise ValueError("Invalid camera frame")
                self.frame = frame
            self.housekeeping()
            return {"controls": self.controls, "event_id": self.sequence}

    def snapshot(self):
        with self.lock:
            self.housekeeping()
            age = self.clock() - self.last_bridge
            return {
                "online": age < 2,
                "age_s": round(age, 2) if self.latest else None,
                "occupied": self.lease is not None,
                "gust_remaining_s": max(0, self.gust_until - self.latest["time_s"])
                if self.gust_until and self.latest
                else 0,
                "controls": dict(self.controls),
                "sample": self.latest,
                "events": list(self.events),
                "camera": self.frame is not None and age < 2,
            }


def handler(bench, directory, origins):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def allowed(self):
            origin = self.headers.get("Origin")
            return not origin or origin in origins or origin == f"http://{self.headers.get('Host')}"

        def end_headers(self):
            origin = self.headers.get("Origin")
            if origin and self.allowed():
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def send_json(self, value, status=200):
            body = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            if not self.allowed():
                return self.send_json({"error": "Origin not allowed"}, 403)
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/state":
                return self.send_json(bench.snapshot())
            if path == "/api/camera":
                with bench.lock:
                    frame = bench.frame
                if not frame:
                    return self.send_json({"error": "No camera frame"}, 404)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(frame)))
                self.end_headers()
                self.wfile.write(frame)
                return
            if path.startswith("/api/"):
                return self.send_json({"error": "Not found"}, 404)
            return super().do_GET()

        def do_POST(self):
            if not self.allowed():
                return self.send_json({"error": "Origin not allowed"}, 403)
            path = urlparse(self.path).path
            if path == "/api/bridge" and not hmac.compare_digest(
                self.headers.get("Authorization", ""), "Bearer " + bench.token
            ):
                return self.send_json({"error": "Bridge authentication required"}, 403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= (600_000 if path == "/api/bridge" else 4096):
                    raise ValueError("Request too large or empty")
                self.connection.settimeout(3)
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object")
                if path == "/api/lease":
                    result = bench.claim(payload.get("lease"))
                elif path == "/api/controls":
                    result = bench.change(payload)
                elif path == "/api/gust":
                    result = bench.gust(payload)
                elif path == "/api/release":
                    with bench.lock:
                        if not bench.lease or payload.get("lease") != bench.lease:
                            raise PermissionError("Not your session")
                        bench.expires = 0
                        bench.housekeeping()
                    result = {"released": True}
                elif path == "/api/bridge":
                    result = bench.publish(payload)
                else:
                    return self.send_json({"error": "Not found"}, 404)
                return self.send_json(result)
            except PermissionError as error:
                return self.send_json({"error": str(error)}, 409)
            except (ValueError, TypeError, OSError) as error:
                return self.send_json({"error": str(error)}, 400)

        def log_message(self, *args):
            pass  # Do not log session credentials or high-rate telemetry requests.

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8089)
    parser.add_argument("--token-file", type=Path, default=Path(".tools/web-bridge-token"))
    parser.add_argument("--controls", type=Path, default=Path("runs/web-controls.txt"))
    parser.add_argument("--origin", action="append", default=[])
    args = parser.parse_args()
    if not args.token_file.exists():
        args.token_file.parent.mkdir(parents=True, exist_ok=True)
        args.token_file.touch(mode=0o600)
        args.token_file.write_text(secrets.token_urlsafe(32))
    bench = Bench(args.token_file.read_text().strip(), args.controls)
    stopped = threading.Event()

    def heartbeat():
        while not stopped.wait(0.5):
            bench.housekeeping()

    bench.housekeeping()
    threading.Thread(target=heartbeat, daemon=True).start()
    root = Path(__file__).resolve().parents[1] / "web/dist"
    server = ThreadingHTTPServer((args.bind, args.port), handler(bench, root, args.origin))
    print(f"Pi control desk: http://{args.bind}:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        stopped.set()
        server.server_close()


if __name__ == "__main__":
    main()
