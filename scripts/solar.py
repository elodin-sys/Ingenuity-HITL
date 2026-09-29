"""Approximate Mars sunlight from archived UTC/LTST and G-to-SITE orientation.

NASA GISS Mars24 B1–B5, D1, D5–D6; not a SPICE or radiometric solution.
Latitude is a regional approximation (18.5 deg planetographic), not a rover fix.
"""

import math
import xml.etree.ElementTree as ET
from datetime import datetime

SOURCE = "https://www.giss.nasa.gov/tools/mars24/help/algorithm.html"


def sin(degrees):
    return math.sin(math.radians(degrees))


def cos(degrees):
    return math.cos(math.radians(degrees))


def declination(unix, tt_minus_utc=69.184):
    d = 2440587.5 + (unix + tt_minus_utc) / 86400 - 2451545
    mean = 19.3871 + 0.52402073 * d
    perturbers = (
        (0.0071, 2.2353, 49.409),
        (0.0057, 2.7543, 168.173),
        (0.0039, 1.1177, 191.837),
        (0.0037, 15.7866, 21.736),
        (0.0021, 2.1354, 15.704),
        (0.0020, 2.4694, 95.528),
        (0.0018, 32.8493, 49.095),
    )
    center = (10.691 + 3e-7 * d) * sin(mean)
    center += sum(a * sin(n * mean) for n, a in ((2, 0.623), (3, 0.050), (4, 0.005), (5, 0.0005)))
    center += sum(a * cos(0.985626 * d / tau + phase) for a, tau, phase in perturbers)
    ls = (270.3871 + 0.524038496 * d + center) % 360
    return math.degrees(math.asin(0.42565 * sin(ls))) + 0.25 * sin(ls)


def local_sun(unix, ltst_hours, latitude=18.5):
    delta = declination(unix)
    hour = 15 * (ltst_hours - 12)
    north = sin(delta) * cos(latitude) - cos(delta) * sin(latitude) * cos(hour)
    east = -cos(delta) * sin(hour)
    up = sin(delta) * sin(latitude) + cos(delta) * cos(latitude) * cos(hour)
    return (
        (north, east, -up),
        math.degrees(math.asin(up)),
        math.degrees(math.atan2(east, north)) % 360,
    )


def rotate(q, v):
    w, x, y, z = q
    u = (x, y, z)
    dot = sum(a * b for a, b in zip(u, v))
    cross = (y * v[2] - z * v[1], z * v[0] - x * v[2], x * v[1] - y * v[0])
    return tuple(2 * dot * a + (2 * w * w - 1) * b + 2 * w * c for a, b, c in zip(u, v, cross))


def from_label(path):
    root = ET.parse(path).getroot()
    utc = root.findtext(".//{*}start_date_time")
    if not 2021 <= datetime.fromisoformat(utc).year <= 2024:
        raise ValueError("Solar time offset only verified for Ingenuity mission years")
    ltst = root.findtext(".//{*}local_true_solar_time")
    h, m, s = map(float, ltst.split(":"))
    vector, elevation, azimuth = local_sun(
        datetime.fromisoformat(utc).timestamp(), h + m / 60 + s / 3600
    )
    nodes = [
        n
        for n in root.findall(".//{*}Coordinate_Space_Definition")
        if n.findtext(
            "{*}Coordinate_Space_Present/{*}Coordinate_Space_Indexed/{*}coordinate_space_frame_type"
        )
        == "HELI_G_FRAME"
    ]
    if len(nodes) != 1:
        raise ValueError("Need one ground-to-site orientation for sunlight")
    node = nodes[0]
    if (
        node.findtext(
            "{*}Coordinate_Space_Reference/{*}Coordinate_Space_Indexed/{*}coordinate_space_frame_type"
        )
        != "SITE_FRAME"
    ):
        raise ValueError("Sunlight requires a geographic SITE parent")
    qnode = node.find("{*}Quaternion_Plus_Direction")
    if qnode.findtext("{*}rotation_direction") != "Forward":
        raise ValueError("Unsupported ground-to-site rotation")
    q = [float(qnode.findtext("{*}" + key)) for key in ("qcos", "qsin1", "qsin2", "qsin3")]
    norm = math.sqrt(sum(v * v for v in q))
    if abs(norm - 1) > 1e-5:
        raise ValueError("Ground-to-site quaternion is not unit")
    q = [v / norm for v in q]
    gx, gy, gz = rotate((q[0], -q[1], -q[2], -q[3]), vector)
    return {
        "utc": utc,
        "ltst": ltst,
        "elevation_deg": elevation,
        "azimuth_from_north_deg": azimuth,
        "direction_local_z_up": [gx, -gy, -gz],
        "g_to_site_wxyz": q,
        "label": path.name,
    }


def lighting(paths):
    samples = sorted((from_label(path) for path in paths), key=lambda row: row["utc"])
    if not samples:
        raise ValueError("No labels available to establish sunlight")
    chosen = samples[len(samples) // 2]
    deviations = [
        math.degrees(
            math.acos(
                max(
                    -1,
                    min(
                        1,
                        sum(
                            a * b
                            for a, b in zip(
                                chosen["direction_local_z_up"], row["direction_local_z_up"]
                            )
                        ),
                    ),
                )
            )
        )
        for row in samples
    ]
    return {
        "method": "Mars24 approximation + archived LTST + inverse G-to-SITE rotation",
        "source": SOURCE,
        "latitude_planetographic_deg": 18.5,
        "latitude_note": "Approximate Jezero latitude; not per-flight geolocation",
        "radiometry": "Illustrative illuminance and dust/ambient; not measured irradiance",
        "static_direction": chosen,
        "max_sample_direction_deviation_deg": max(deviations),
        "samples": samples,
    }
