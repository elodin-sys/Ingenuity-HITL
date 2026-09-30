"""Flight 59 demonstration plant; feedback control lives in the external Rust process.

Run from repository root: uv run --with elodin==0.19.2 sim/main.py
This is a reduced-order helicopter model, not NASA's validated flight dynamics.
"""

import argparse
import csv
import json
import math
import socket
import sys
import time
from pathlib import Path
from typing import Annotated

import elodin as el
import jax
import jax.numpy as jnp
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DT = 0.01
G = 3.72076
MASS = 1.8
GROUND = 0.35  # Illustrative S2/body ground clearance, not a surveyed extrinsic.
Command = Annotated[
    jax.Array,
    el.Component(
        "command",
        el.ComponentType(el.PrimitiveType.F64, (9,)),
        metadata={"external_control": "true"},
    ),
]
Actuator = Annotated[
    jax.Array, el.Component("actuator", el.ComponentType(el.PrimitiveType.F64, (4,)))
]
Rotor = Annotated[jax.Array, el.Component("rotor", el.ComponentType(el.PrimitiveType.F64, (2,)))]

ReferencePose = Annotated[
    jax.Array,
    el.Component(
        "referencepose",
        el.ComponentType(el.PrimitiveType.F64, (7,)),
        metadata={"external_control": "true"},
    ),
]
TopPose = Annotated[
    jax.Array,
    el.Component(
        "toppose",
        el.ComponentType(el.PrimitiveType.F64, (7,)),
        metadata={"external_control": "true"},
    ),
]
BottomPose = Annotated[
    jax.Array,
    el.Component(
        "bottompose",
        el.ComponentType(el.PrimitiveType.F64, (7,)),
        metadata={"external_control": "true"},
    ),
]


@el.dataclass
class Vehicle(el.Archetype):
    command: Command
    actuator: Actuator
    rotor: Rotor
    referencepose: ReferencePose
    toppose: TopPose
    bottompose: BottomPose


Elapsed = Annotated[
    jax.Array,
    el.Component(
        "elapsed",
        el.ComponentType.F64,
        metadata={"external_control": "true", "element_names": "Mission / s"},
    ),
]
Height = Annotated[
    jax.Array,
    el.Component(
        "height",
        el.ComponentType.F64,
        metadata={"external_control": "true", "element_names": "SIM S2 / m"},
    ),
]
Target = Annotated[
    jax.Array,
    el.Component(
        "target",
        el.ComponentType.F64,
        metadata={"external_control": "true", "element_names": "FSW target / m"},
    ),
]
Gap = Annotated[
    jax.Array,
    el.Component(
        "gap",
        el.ComponentType.F64,
        metadata={"external_control": "true", "element_names": "NASA gap / m"},
    ),
]
Phase = Annotated[
    jax.Array,
    el.Component(
        "phase",
        el.ComponentType.F64,
        metadata={"external_control": "true", "element_names": "FSW phase (0-4)"},
    ),
]
Collective = Annotated[
    jax.Array,
    el.Component(
        "collective",
        el.ComponentType.F64,
        metadata={"external_control": "true", "element_names": "Collective (0-1)"},
    ),
]
Rpm = Annotated[
    jax.Array,
    el.Component(
        "rpm",
        el.ComponentType.F64,
        metadata={"external_control": "true", "element_names": "Rotor / RPM"},
    ),
]


@el.dataclass
class Diagnostics(el.Archetype):
    elapsed: Elapsed
    height: Height
    target: Target
    gap: Gap
    phase: Phase
    collective: Collective
    rpm: Rpm


def systems(density, wind):
    @el.map
    def actuator(command: Command, state: Actuator, rotor: Rotor) -> tuple[Actuator, Rotor]:
        # Simple first-order collective/cyclic response; coefficients are priors.
        state = state + (command[:4] - state) * (1 - jnp.exp(-DT / 0.12))
        target_rpm = jnp.where(command[4] == 4.0, 0.0, 2400.0)
        rpm = rotor[0] + (target_rpm - rotor[0]) * (1 - jnp.exp(-DT / 0.5))
        phase = jnp.mod(rotor[1] + rpm * (2 * jnp.pi / 60) * DT, 2 * jnp.pi)
        return state, jnp.array([rpm, phase])

    @el.map
    def forces(pos: el.WorldPos, vel: el.WorldVel, state: Actuator, rotor: Rotor) -> el.Force:
        q = pos.angular()
        thrust = (
            2 * MASS * G * state[0] * density / (700 / (188.92 * 220)) * (rotor[0] / 2400.0) ** 2
        )
        relative = vel.linear() - jnp.array(wind)
        drag = -0.5 * density * 0.03 * jnp.linalg.norm(relative) * relative
        body_rate = q.inverse() @ vel.angular()
        torque = jnp.array([0.04, 0.04, 0.03]) * state[1:4] - 0.004 * body_rate
        return el.SpatialForce(
            linear=q @ jnp.array([0.0, 0.0, thrust]) + drag + jnp.array([0.0, 0.0, -MASS * G]),
            torque=q @ torque,
        )

    @el.map
    def contact(pos: el.WorldPos, vel: el.WorldVel) -> tuple[el.WorldPos, el.WorldVel]:
        p = pos.linear()
        grounded = p[2] < GROUND
        p = p.at[2].set(jnp.maximum(p[2], GROUND))
        v = jnp.where(
            grounded, jnp.array([0.0, 0.0, jnp.maximum(vel.linear()[2], 0.0)]), vel.linear()
        )
        return el.SpatialTransform(angular=pos.angular(), linear=p), el.SpatialMotion(
            angular=jnp.where(grounded, jnp.zeros(3), vel.angular()), linear=v
        )

    return actuator | el.six_dof(sys=forces, time_step=DT) | contact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller", default="127.0.0.1:12359")
    parser.add_argument("--duration", type=float)
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--startup-delay", type=float, default=0)
    parser.add_argument("--pressure", type=float, default=700.0)
    parser.add_argument("--temperature", type=float, default=220.0)
    parser.add_argument("--wind", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=59)
    parser.add_argument("--db", default="runs/closed-loop-flight59")
    parser.add_argument("--backend", default="cranelift")
    parser.add_argument("--db-addr", default="127.0.0.1:2240")
    args = parser.parse_args()
    sys.argv = [sys.argv[0], "run", args.db_addr]
    if Path(args.db).exists():
        parser.error("Choose a fresh --db directory for each flight")
    profile = json.loads((ROOT / "config/flight59-profile.json").read_text())
    duration = args.duration or profile["duration_s"] + 2
    host, port = args.controller.rsplit(":", 1)
    world = el.World()
    world.spawn(
        [
            el.Body(
                world_pos=el.SpatialTransform(linear=jnp.array([0.0, 0.0, GROUND])),
                inertia=el.SpatialInertia(mass=MASS, inertia=jnp.array([0.02, 0.02, 0.035])),
            ),
            Vehicle(
                command=jnp.zeros(9),
                actuator=jnp.zeros(4),
                rotor=jnp.zeros(2),
                referencepose=jnp.full(7, jnp.nan),
                toppose=jnp.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]),
                bottompose=jnp.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]),
            ),
        ],
        name="display",
    )

    @el.dataclass
    class PoseOnly(el.Archetype):
        world_pos: el.WorldPos

    world.spawn(
        Diagnostics(
            **{
                name: jnp.array(0.0)
                for name in ("elapsed", "height", "target", "gap", "phase", "collective", "rpm")
            }
        ),
        name="mission",
    )
    # The reference ghost has no actuator component, so forces/physics must not
    # integrate it. Its displayed pose is explicitly reset from archive samples.
    rng = np.random.default_rng(args.seed)
    rows = list(csv.DictReader((ROOT / "data/derived/sol00915.csv").open()))
    archive_t = np.array([float(row["time_s"]) for row in rows])
    archive_p = np.array(
        [[float(row[k]) for k in ("qx", "qy", "qz", "qw", "x_m", "y_m", "z_m")] for row in rows]
    )
    records = []
    previous_vz = 0.0
    start = None
    rotor_pivots = json.loads((ROOT / "runs/rotor-pivots.json").read_text())
    with socket.create_connection((host, int(port)), timeout=5) as connection:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        reader = connection.makefile("rb")

        def step(tick, ctx):
            nonlocal previous_vz, start
            t = tick * DT
            if start is None:
                time.sleep(args.startup_delay)
                start = time.monotonic()
            if args.realtime:
                time.sleep(max(0, start + t - time.monotonic()))
            values = ctx.component_batch_operation(
                reads=["display.world_pos", "display.world_vel", "display.rotor"]
            )
            pose = np.asarray(values["display.world_pos"]).reshape(-1)
            vel = np.asarray(values["display.world_vel"]).reshape(-1)
            x, y, z, w = pose[:4]
            roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
            pitch = math.asin(np.clip(2 * (w * y - z * x), -1, 1))
            yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
            inverse_q = np.r_[-pose[:3], pose[3]]
            body_rate = vel[:3] + 2 * np.cross(
                inverse_q[:3], np.cross(inverse_q[:3], vel[:3]) + inverse_q[3] * vel[:3]
            )
            # Sensor surrogate boundaries: noisy range, AHRS, optical flow and
            # gravity-compensated acceleration. No truth pose is sent to FSW.
            measured = [
                t,
                pose[6] + rng.normal(0, 0.005),
                roll + rng.normal(0, 0.0005),
                pitch + rng.normal(0, 0.0005),
                yaw + rng.normal(0, 0.0005),
                *(body_rate + rng.normal(0, 0.0005, 3)),
                *(vel[3:5] + rng.normal(0, 0.005, 2)),
                (vel[5] - previous_vz) / DT + rng.normal(0, 0.01),
                1.0,
            ]
            previous_vz = vel[5]
            connection.sendall((str(tick) + " " + " ".join(map(str, measured)) + "\n").encode())
            reply = reader.readline(2048).decode().split()
            if len(reply) != 10 or reply[0] != str(tick):
                raise RuntimeError(f"Controller failed or sequence mismatch: {reply[:2]}")
            command = np.array(list(map(float, reply[1:])))
            if (
                not np.isfinite(command).all()
                or not 0 <= command[0] <= 1
                or np.any(np.abs(command[1:4]) > 1)
            ):
                raise RuntimeError("Invalid actuator commands")
            archive_time = t - profile["archive_offset_s"]
            # Only compare within observed coverage; no NASA ground endpoints.
            observed = archive_t[0] <= archive_time <= archive_t[-1]
            reference = np.array(
                [np.interp(archive_time, archive_t, archive_p[:, i]) for i in range(7)]
            )
            reference[:4] /= np.linalg.norm(reference[:4])
            writes = {"display.command": command}
            diagnostic = {
                "elapsed": t,
                "height": pose[6],
                "target": command[7],
                "gap": np.linalg.norm(pose[4:] - reference[4:]) if observed else float("nan"),
                "phase": command[4],
                "collective": command[0],
                "rpm": np.asarray(values["display.rotor"]).reshape(-1)[0],
            }
            writes.update({"mission." + k: np.array([v]) for k, v in diagnostic.items()})
            writes["display.referencepose"] = reference if observed else np.full(7, np.nan)
            # Publish two rigid rotor transforms driven by physical model phase.
            phase = float(np.asarray(values["display.rotor"]).reshape(-1)[1])

            def rotate(q, vector):
                return vector + 2 * np.cross(q[:3], np.cross(q[:3], vector) + q[3] * vector)

            for name, pivot, sign in zip(
                ("display.toppose", "display.bottompose"), rotor_pivots, (1, -1)
            ):
                sin, cos = math.sin(sign * phase / 2), math.cos(sign * phase / 2)
                rotor_q = np.array(
                    [x * cos + y * sin, y * cos - x * sin, z * cos + w * sin, w * cos - z * sin]
                )
                writes[name] = np.r_[rotor_q, pose[4:] + rotate(pose[:4], np.array(pivot))]
            ctx.component_batch_operation(writes=writes)
            if tick % 1000 == 0:
                print(f"FSW t={t:.1f}s height={pose[6]:.2f}m phase={command[4]:.0f}", flush=True)
            records.append(
                {
                    "time_s": t,
                    "x_m": float(pose[4]),
                    "y_m": float(pose[5]),
                    "tilt_rad": float(math.hypot(roll, pitch)),
                    "z_m": float(pose[6]),
                    "vz_mps": float(vel[5]),
                    "collective": float(command[0]),
                    "phase": int(command[4]),
                    "target_m": float(command[7]),
                    "observed": bool(observed),
                    "reference_error_m": float(np.linalg.norm(pose[4:] - reference[4:]))
                    if observed
                    else None,
                }
            )

        try:
            world.run(
                systems(args.pressure / (188.92 * args.temperature), (args.wind, 0.0, 0.0)),
                simulation_rate=1 / DT,
                max_ticks=round(duration / DT),
                post_step=step,
                db_path=args.db,
                interactive=False,
                backend=args.backend,
                log_level="warn",
            )
        finally:
            if records:
                output = Path(args.db).with_suffix(".json")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps(
                        {
                            "mode": "closed-loop demonstration",
                            "seed": args.seed,
                            "samples": records,
                        },
                        indent=2,
                    )
                    + "\n"
                )
    print(json.dumps({"samples": len(records), "last": records[-1]}))


if __name__ == "__main__":
    main()
