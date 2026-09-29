"""Export one recorded gray8 frame without a GUI. Reads the native append-log format."""

import argparse
import json
import struct
import zlib
from pathlib import Path


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", type=Path)
    parser.add_argument("--output", type=Path, default=Path("runs/navcam.png"))
    parser.add_argument("--index", type=int, help="Default: middle recorded frame")
    # Native msg_id("navcam.gray"). The ID is independent of the database path.
    parser.add_argument("--message-id", type=int, default=34774)
    args = parser.parse_args()
    log = args.db / "msgs" / str(args.message_id)
    with (log / "timestamps").open("rb") as stream:
        committed, _ = struct.unpack("<QQ", stream.read(16))
        count = (committed - 16) // 8
        if not count or committed > 16 + 8 * 10_000_000:
            raise ValueError("Empty or unsupported camera timestamp log")
        index = args.index if args.index is not None else count // 2
        if not 0 <= index < count:
            raise ValueError("Frame index out of range")
        stream.seek(16 + 8 * index)
        timestamp = struct.unpack("<q", stream.read(8))[0]
    with (log / "offsets").open("rb") as stream:
        committed, _ = struct.unpack("<QQ", stream.read(16))
        if 16 + 16 * (index + 1) > committed:
            raise ValueError("Incomplete frame offset")
        stream.seek(16 + 16 * index)
        length, prefix, segment, offset = struct.unpack("<I4sII", stream.read(16))
    if length != 640 * 480:
        raise ValueError("Expected a 640x480 gray8 frame")
    path = log / ("data_log" if segment == 0 else f"data_log.{segment}")
    with path.open("rb") as stream:
        committed, _ = struct.unpack("<QQ", stream.read(16))
        if 16 + offset + length > committed:
            raise ValueError("Incomplete camera payload")
        stream.seek(16 + offset)
        frame = stream.read(length)
    if frame[:4] != prefix:
        raise ValueError("Unsupported append-log offset layout")
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 640, 480, 8, 0, 0, 0, 0))
    png += chunk(
        b"IDAT", zlib.compress(b"".join(b"\0" + frame[y * 640 : (y + 1) * 640] for y in range(480)))
    )
    png += chunk(b"IEND", b"")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(png)
    report = {
        "recorded_frames": count,
        "index": index,
        "timestamp_us": timestamp,
        "width": 640,
        "height": 480,
        "format": "gray8",
        "pixel_min": min(frame),
        "pixel_max": max(frame),
        "source": "native Elodin simulated navigation camera; not a NASA image",
    }
    args.output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
