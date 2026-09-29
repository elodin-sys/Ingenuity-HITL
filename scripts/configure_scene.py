"""Configure native DB metadata with the installed Impeller SetDbConfig protocol."""

import argparse
import json
import socket
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def string(value):
    value = value.encode("utf-8")
    return varint(len(value)) + value


def config_packet(metadata):
    # Postcard SetDbConfig { recording: None, metadata: HashMap<String,String> }.
    payload = b"\0" + varint(len(metadata))
    payload += b"".join(string(key) + string(value) for key, value in metadata.items())
    # PacketTy::Msg = 0; well-known ID [224,19].
    return struct.pack("<IBBBB", 4 + len(payload), 0, 224, 19, 0) + payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2250)
    args = parser.parse_args()
    cameras = json.loads((ROOT / "config/cameras.json").read_text())
    selected = ROOT / "config/selection.json"
    schematic = "schematics/main.kdl"
    if selected.exists():
        dataset = json.loads(selected.read_text())
        direction = dataset["lighting"]["static_direction"]["direction_local_z_up"]
        for camera in cameras:
            camera["environment"]["sun"]["direction"] = direction
        schematic = "schematics/selected.kdl"
    metadata = {"sensor_cameras": json.dumps(cameras), "schematic.active": schematic}
    with socket.create_connection((args.host, args.port), timeout=10) as connection:
        connection.sendall(config_packet(metadata))
    print("Registered simulated 640x480 gray8 navigation camera and active schematic")


if __name__ == "__main__":
    main()
