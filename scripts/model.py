"""Low-order atmosphere/hover theory. Not Ingenuity's flight dynamics model."""

import math

MARS_G = 3.72076
CO2_R = 188.92  # J/(kg K), pure CO2 approximation; Mars mixture differs slightly.
MASS_KG = 1.8
RADIUS_M = 0.6


def hover(pressure_pa, temperature_k, wind_mps=0.0, drag_area_m2=0.03):
    if not all(math.isfinite(x) for x in (pressure_pa, temperature_k, wind_mps, drag_area_m2)):
        raise ValueError("Model inputs must be finite")
    if pressure_pa <= 0 or temperature_k <= 0 or wind_mps < 0 or drag_area_m2 < 0:
        raise ValueError("Invalid atmospheric inputs")
    density = pressure_pa / (CO2_R * temperature_k)
    weight = MASS_KG * MARS_G
    drag = 0.5 * density * drag_area_m2 * wind_mps**2
    thrust = math.hypot(weight, drag)
    # Shared coaxial disk area, NOT twice the disk area. Hover lower bound only:
    # excludes profile power, coaxial interference, motor losses, ground effect.
    power = weight**1.5 / math.sqrt(2 * density * math.pi * RADIUS_M**2)
    return {
        "density_kgm3": density,
        "ideal_hover_power_w": power,
        "trim_thrust_n": thrust,
        "trim_tilt_deg": math.degrees(math.atan2(drag, weight)),
    }


def reference(t):
    """Reconstructed 39.1 s flight: 3 m hover for 30 s; ramps are assumptions."""
    ramp = (39.1 - 30) / 2
    if t <= 0 or t >= 39.1:
        return 0.0, 0.0
    if t < ramp:
        u = t / ramp
        return 3 * (3 * u * u - 2 * u**3), 18 * u * (1 - u) / ramp
    if t > 39.1 - ramp:
        z, speed = reference(39.1 - t)
        return z, -speed
    return 3.0, 0.0
