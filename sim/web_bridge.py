"""Best-effort web telemetry outside the synchronous flight-control loop."""

import base64
import json
import struct
import threading
import time
import zlib
from pathlib import Path
from urllib.request import Request, urlopen


def latest_camera(db):
    log = Path(db) / "msgs/34774"
    with (log / "offsets").open("rb") as stream:
        committed, _ = struct.unpack("<QQ", stream.read(16))
        if committed < 32:
            return None
        stream.seek(committed - 16)
        length, prefix, segment, offset = struct.unpack("<I4sII", stream.read(16))
    if length != 640 * 480:
        return None
    with (log / ("data_log" if segment == 0 else f"data_log.{segment}")).open("rb") as stream:
        committed, _ = struct.unpack("<QQ", stream.read(16))
        if 16 + offset + length > committed:
            return None
        stream.seek(16 + offset)
        frame = stream.read(length)
    if frame[:4] != prefix:
        return None

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 640, 480, 8, 0, 0, 0, 0))
    png += chunk(
        b"IDAT", zlib.compress(b"".join(b"\0" + frame[y * 640 : (y + 1) * 640] for y in range(480)))
    )
    return png + chunk(b"IEND", b"")


class WebBridge:
    def __init__(self, url, token_file, db):
        self.url = url.rstrip("/") + "/api/bridge"
        self.token = Path(token_file).read_text().strip()
        self.db = db
        self.lock = threading.Lock()
        self.sample = None
        self.wind = 0.0
        self.updated = -1e9
        self.event_id = 0
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def publish(self, sample):
        with self.lock:
            self.sample = dict(sample)

    def controls(self):
        with self.lock:
            return (self.wind if time.monotonic() - self.updated < 2 else 0.0, self.event_id)

    def close(self):
        self.stop.set()
        self.worker.join(timeout=2)

    def run(self):
        camera_at = -1e9
        while not self.stop.wait(0.1):
            with self.lock:
                sample = self.sample
            if sample is None:
                continue
            payload = {"sample": sample}
            if time.monotonic() - camera_at > 0.5:
                camera_at = time.monotonic()
                try:
                    frame = latest_camera(self.db)
                    if frame:
                        payload["frame"] = base64.b64encode(frame).decode()
                except (OSError, ValueError, struct.error):
                    pass
            try:
                request = Request(
                    self.url,
                    json.dumps(payload, allow_nan=False).encode(),
                    {"Content-Type": "application/json", "Authorization": "Bearer " + self.token},
                )
                with urlopen(request, timeout=0.8) as response:
                    value = json.loads(response.read(4096))
                wind = float(value["controls"]["wind"])
                if not -60 <= wind <= 60:
                    continue
                with self.lock:
                    self.wind = wind
                    self.event_id = int(value["event_id"])
                    self.updated = time.monotonic()
            except (OSError, ValueError, KeyError):
                pass  # A web outage must never block or replace the Rust FSW.
