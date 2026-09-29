"""Display interpolation only: never replaces archived navigation measurements."""

import math


def slerp(a, b, fraction):
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0:
        b = tuple(-v for v in b)
        dot = -dot
    dot = min(1.0, max(-1.0, dot))
    if dot > 0.9995:
        q = [(1 - fraction) * x + fraction * y for x, y in zip(a, b)]
    else:
        angle = math.acos(dot)
        q = [
            (math.sin((1 - fraction) * angle) * x + math.sin(fraction * angle) * y)
            / math.sin(angle)
            for x, y in zip(a, b)
        ]
    norm = math.sqrt(sum(v * v for v in q))
    return tuple(v / norm for v in q)


def interpolate(rows, fps=30, max_gap=10):
    """SLERP attitudes + linear positions; no extrapolation or invented endpoint."""
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be positive")
    if not math.isfinite(max_gap) or max_gap <= 0:
        raise ValueError("max_gap must be positive")
    for a, b in zip(rows, rows[1:]):
        if b[0] <= a[0]:
            raise ValueError("Observation times must increase")
        if b[0] - a[0] > max_gap:
            # Preserve source time; no synthetic flight across missing observations.
            yield a[0], tuple(a[1:8])
            continue
        for index in range(math.ceil(a[0] * fps), math.ceil(b[0] * fps)):
            elapsed = index / fps
            fraction = (elapsed - a[0]) / (b[0] - a[0])
            q = slerp(a[1:5], b[1:5], fraction)
            xyz = tuple(x + fraction * (y - x) for x, y in zip(a[5:8], b[5:8]))
            yield elapsed, (*q, *xyz)
    yield rows[-1][0], tuple(rows[-1][1:8])
