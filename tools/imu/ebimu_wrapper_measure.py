#!/usr/bin/env python3
"""Read-only stationary EBIMU measurement using HUPHY's actual deployment
wrapper (huphy.sensors.ebimu.imu.EbimuImu), not a standalone probe.

Polls EbimuImu.read() at a fixed host rate to capture what a real control
loop would see: staleness (age of the cached state at poll time), the
consumer-visible update rate, and the wrapper's own dropped-line counter.
It never calls anything in commissioning.py and never writes to the port --
EbimuImu.connect()/read() only reads.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
from pathlib import Path


def _percentile(values, percent):
    if not values:
        return None
    ordered = sorted(values)
    at = (len(ordered) - 1) * percent / 100.0
    lo, hi = math.floor(at), math.ceil(at)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (at - lo)


def _stats(values):
    series = list(values)
    if not series:
        return {"count": 0, "mean": None, "std": None, "p50": None, "p95": None, "min": None, "max": None}
    return {
        "count": len(series),
        "mean": statistics.fmean(series),
        "std": statistics.stdev(series) if len(series) > 1 else 0.0,
        "p50": _percentile(series, 50),
        "p95": _percentile(series, 95),
        "min": min(series),
        "max": max(series),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--huphy-src", required=True, type=Path)
    p.add_argument("--pydeps", required=True, type=Path, help="dir containing vendored serial/ package")
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baudrate", type=int, default=115200)
    p.add_argument("--output", required=True)
    p.add_argument("--seconds", type=float, default=120.0)
    p.add_argument("--poll-hz", type=float, default=1000.0)
    p.add_argument("--warmup-seconds", type=float, default=1.0)
    p.add_argument("--label", required=True)
    p.add_argument("--out-dir", type=Path, default=Path("."))
    args = p.parse_args()

    sys.path.insert(0, str(args.pydeps))
    sys.path.insert(0, str(args.huphy_src))
    from huphy.sensors.ebimu.imu import EbimuImu  # noqa: E402

    output = tuple(x.strip() for x in args.output.split(",") if x.strip())
    imu = EbimuImu("probe", args.port, baudrate=args.baudrate, output=output)
    imu.connect()
    try:
        time.sleep(args.warmup_seconds)

        args.out_dir.mkdir(parents=True, exist_ok=True)
        stem = time.strftime("%Y%m%dT%H%M%S") + "_" + args.label
        csv_path = args.out_dir / f"{stem}.csv"
        summary_path = args.out_dir / f"{stem}_summary.json"

        columns = [
            "poll_monotonic", "state_stamp", "age_ms", "sensor_ms",
            "is_valid", "changed",
            "gravity_x", "gravity_y", "gravity_z", "gravity_norm",
            "gyro_x_dps", "gyro_y_dps", "gyro_z_dps",
            "accel_x_mps2", "accel_y_mps2", "accel_z_mps2", "temp_c",
        ]

        poll_period = 1.0 / args.poll_hz
        deadline = time.monotonic() + args.seconds

        polls = 0
        last_stamp = None
        change_dts = []  # consumer-visible sensor packet dt (dedup by stamp)
        sensor_dts = []  # sensor_ms-derived dt (dedup by stamp)
        ages_ms = []
        gravity_norm_errors = []
        gyro = [[], [], []]
        accel = [[], [], []]
        gravity = [[], [], []]
        temperature = []
        last_sensor_ms = None
        first_stamp_time = None
        last_change_host_time = None

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            while time.monotonic() < deadline:
                poll_t = time.monotonic()
                state = imu.read()
                changed = (last_stamp is None) or (state.stamp != last_stamp)
                age_ms = (poll_t - state.stamp) * 1000.0 if state.is_valid else None

                polls += 1
                if state.is_valid and age_ms is not None:
                    ages_ms.append(age_ms)

                if changed and state.is_valid:
                    if last_change_host_time is not None:
                        change_dts.append((poll_t - last_change_host_time) * 1000.0)
                    last_change_host_time = poll_t
                    last_stamp = state.stamp

                    sensor_ms = state.extra.get("sensor_ms", -1.0)
                    if sensor_ms >= 0 and last_sensor_ms is not None:
                        delta = sensor_ms - last_sensor_ms
                        if 0.0 < delta < 10_000.0:
                            sensor_dts.append(delta)
                    if sensor_ms >= 0:
                        last_sensor_ms = sensor_ms

                    g = state.gravity
                    w = state.gyro_dps
                    a = state.accel_mps2
                    norm = math.sqrt(sum(v * v for v in g))
                    gravity_norm_errors.append(abs(norm - 1.0))
                    for i in range(3):
                        gravity[i].append(g[i])
                        gyro[i].append(w[i])
                        accel[i].append(a[i])
                    if "temp" in state.extra:
                        temperature.append(state.extra["temp"])

                    writer.writerow({
                        "poll_monotonic": poll_t, "state_stamp": state.stamp,
                        "age_ms": age_ms, "sensor_ms": state.extra.get("sensor_ms"),
                        "is_valid": state.is_valid, "changed": changed,
                        "gravity_x": g[0], "gravity_y": g[1], "gravity_z": g[2], "gravity_norm": norm,
                        "gyro_x_dps": w[0], "gyro_y_dps": w[1], "gyro_z_dps": w[2],
                        "accel_x_mps2": a[0], "accel_y_mps2": a[1], "accel_z_mps2": a[2],
                        "temp_c": state.extra.get("temp"),
                    })

                sleep_for = poll_period - (time.monotonic() - poll_t)
                if sleep_for > 0:
                    time.sleep(sleep_for)

        nominal_dt = _percentile(sensor_dts, 50)
        inferred_missing = 0
        if nominal_dt and nominal_dt > 0:
            inferred_missing = sum(max(0, round(d / nominal_dt) - 1) for d in sensor_dts)

        summary = {
            "label": args.label,
            "port": args.port,
            "baudrate": args.baudrate,
            "wrapper": "huphy.sensors.ebimu.imu.EbimuImu (deployment class, not a standalone probe)",
            "output": output,
            "poll_hz_requested": args.poll_hz,
            "measurement_seconds": args.seconds,
            "host_polls": polls,
            "unique_packets_seen": len(change_dts) + 1 if change_dts else (1 if last_stamp is not None else 0),
            "wrapper_dropped_lines": imu.dropped,
            "inferred_sensor_packets_missing": inferred_missing,
            "consumer_visible_packet_dt_ms": _stats(change_dts),
            "sensor_dt_ms": _stats(sensor_dts),
            "staleness_age_ms": _stats(ages_ms),
            "gravity_norm_error": _stats(gravity_norm_errors),
            "gravity": {axis: _stats(gravity[i]) for i, axis in enumerate(("x", "y", "z"))},
            "gyro_dps": {axis: _stats(gyro[i]) for i, axis in enumerate(("x", "y", "z"))},
            "accel_mps2": {axis: _stats(accel[i]) for i, axis in enumerate(("x", "y", "z"))},
            "temperature_c": _stats(temperature),
            "csv": str(csv_path),
        }
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"samples: {csv_path}")
        print(f"summary: {summary_path}")
    finally:
        imu.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
