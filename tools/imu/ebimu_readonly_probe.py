#!/usr/bin/env python3
"""Read-only EBIMU logger using HUPHY's existing packet decoder.

This tool never sends a command to the sensor.  It opens the already configured
serial stream, timestamps each arriving line on the host, and writes samples plus
a compact summary useful for the simulation sensor model.

Example (after ``huphy-imu show`` has revealed the active output layout):
  python3 ebimu_readonly_probe.py --huphy-root ~/HUPHY --port /dev/ebimu \
    --output quat,gyro,accel,dist,temp,time --seconds 300 --label level_still
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import select
import statistics
import sys
import termios
import time
from pathlib import Path
from typing import Iterable, Sequence


def _percentile(values: Sequence[float], percent: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    at = (len(ordered) - 1) * percent / 100.0
    lo, hi = math.floor(at), math.ceil(at)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (at - lo)


def _stats(values: Iterable[float]) -> dict[str, float | int | None]:
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--huphy-root", required=True, type=Path, help="HUPHY checkout; only its existing decoder is imported")
    parser.add_argument("--port", default="/dev/ebimu")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--output", required=True, help="Comma-separated active EBIMU fields from `huphy-imu show`")
    parser.add_argument("--seconds", type=float, default=300.0)
    parser.add_argument("--warmup-seconds", type=float, default=1.0)
    parser.add_argument("--label", required=True, help="Motion condition written into metadata")
    parser.add_argument("--out-dir", type=Path, default=Path("ebimu_probe"))
    return parser


class _NativeSerial:
    """Small read-only serial adapter for hosts without pyserial.

    It configures only the host tty line discipline and never writes to its file
    descriptor.  EBIMU persistent settings remain untouched.
    """

    def __init__(self, port: str, baudrate: int, timeout: float) -> None:
        baud_flag = getattr(termios, f"B{baudrate}", None)
        if baud_flag is None:
            raise ValueError(f"Unsupported native tty baudrate: {baudrate}")
        self._fd = os.open(port, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        self.timeout = timeout
        self._pending = bytearray()
        attrs = termios.tcgetattr(self._fd)
        attrs[0] = 0  # input flags
        attrs[1] = 0  # output flags
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0  # local flags: raw mode
        attrs[4] = baud_flag
        attrs[5] = baud_flag
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self._fd, termios.TCSANOW, attrs)

    def reset_input_buffer(self) -> None:
        termios.tcflush(self._fd, termios.TCIFLUSH)
        self._pending.clear()

    def readline(self) -> bytes:
        deadline = time.monotonic() + self.timeout
        while True:
            newline = self._pending.find(b"\n")
            if newline >= 0:
                line = bytes(self._pending[: newline + 1])
                del self._pending[: newline + 1]
                return line
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return b""
            readable, _, _ = select.select([self._fd], [], [], remaining)
            if not readable:
                return b""
            try:
                chunk = os.read(self._fd, 4096)
            except BlockingIOError:
                continue
            if not chunk:
                return b""
            self._pending.extend(chunk)

    def close(self) -> None:
        os.close(self._fd)


def main() -> int:
    args = _parser().parse_args()
    source = args.huphy_root / "src"
    if not (source / "huphy" / "sensors" / "ebimu" / "protocol.py").is_file():
        raise SystemExit(f"HUPHY decoder not found below {source}")
    sys.path.insert(0, str(source))

    from huphy.sensors.ebimu import commands, protocol

    output = tuple(item.strip() for item in args.output.split(",") if item.strip())
    commands.validate(output)
    expected_fields = commands.field_count(output)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = time.strftime("%Y%m%dT%H%M%S") + "_" + args.label
    csv_path = args.out_dir / f"{stem}.csv"
    summary_path = args.out_dir / f"{stem}_summary.json"

    columns = [
        "host_monotonic_ns", "host_dt_ms", "sensor_ms", "sensor_dt_ms",
        "gravity_x", "gravity_y", "gravity_z", "gravity_norm",
        "gyro_x_dps", "gyro_y_dps", "gyro_z_dps",
        "accel_x_mps2", "accel_y_mps2", "accel_z_mps2",
        "qw", "qx", "qy", "qz", "roll_deg", "pitch_deg", "yaw_deg", "temp_c",
    ]
    valid = invalid = 0
    host_dts: list[float] = []
    sensor_dts: list[float] = []
    gravity_norm_errors: list[float] = []
    gyro: list[list[float]] = [[], [], []]
    accel: list[list[float]] = [[], [], []]
    gravity: list[list[float]] = [[], [], []]
    temperature: list[float] = []
    previous_host_ns: int | None = None
    previous_sensor_ms: float | None = None

    try:
        try:
            import serial
        except ImportError:
            stream = _NativeSerial(args.port, args.baudrate, timeout=0.25)
            transport = "native-read-only"
        else:
            stream = serial.Serial(port=args.port, baudrate=args.baudrate, timeout=0.25)
            transport = "pyserial"
    except Exception as exc:
        raise SystemExit(f"Cannot open {args.port} at {args.baudrate}: {exc}") from exc

    # This clears only host-side buffered old data; it does not transmit to EBIMU.
    stream.reset_input_buffer()
    warmup_deadline = time.monotonic() + args.warmup_seconds
    deadline = warmup_deadline + args.seconds
    try:
        with csv_path.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=columns)
            writer.writeheader()
            while time.monotonic() < deadline:
                raw = stream.readline()
                arrival_ns = time.monotonic_ns()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore").strip()
                state = protocol.decode(line, output, stamp=arrival_ns / 1e9)
                if state is None:
                    invalid += 1
                    continue
                if time.monotonic() < warmup_deadline:
                    continue

                valid += 1
                host_dt = None if previous_host_ns is None else (arrival_ns - previous_host_ns) / 1e6
                previous_host_ns = arrival_ns
                sensor_ms = state.extra.get("sensor_ms", -1.0)
                sensor_dt = None
                if sensor_ms >= 0 and previous_sensor_ms is not None:
                    delta = sensor_ms - previous_sensor_ms
                    # EBIMU timestamp rollover and reset are not timing samples.
                    if 0.0 < delta < 10_000.0:
                        sensor_dt = delta
                if sensor_ms >= 0:
                    previous_sensor_ms = sensor_ms
                if host_dt is not None:
                    host_dts.append(host_dt)
                if sensor_dt is not None:
                    sensor_dts.append(sensor_dt)

                g = state.gravity
                w = state.gyro_dps
                a = state.accel_mps2
                norm = math.sqrt(sum(value * value for value in g))
                gravity_norm_errors.append(abs(norm - 1.0))
                for index in range(3):
                    gravity[index].append(g[index])
                    gyro[index].append(w[index])
                    accel[index].append(a[index])
                if "temp" in state.extra:
                    temperature.append(state.extra["temp"])
                writer.writerow({
                    "host_monotonic_ns": arrival_ns,
                    "host_dt_ms": host_dt,
                    "sensor_ms": sensor_ms,
                    "sensor_dt_ms": sensor_dt,
                    "gravity_x": g[0], "gravity_y": g[1], "gravity_z": g[2], "gravity_norm": norm,
                    "gyro_x_dps": w[0], "gyro_y_dps": w[1], "gyro_z_dps": w[2],
                    "accel_x_mps2": a[0], "accel_y_mps2": a[1], "accel_z_mps2": a[2],
                    "qw": state.extra.get("qw"), "qx": state.extra.get("qx"),
                    "qy": state.extra.get("qy"), "qz": state.extra.get("qz"),
                    "roll_deg": state.extra.get("roll"), "pitch_deg": state.extra.get("pitch"),
                    "yaw_deg": state.extra.get("yaw"), "temp_c": state.extra.get("temp"),
                })
    finally:
        stream.close()

    nominal_sensor_dt = _percentile(sensor_dts, 50)
    inferred_missing = 0
    if nominal_sensor_dt and nominal_sensor_dt > 0:
        inferred_missing = sum(max(0, round(delta / nominal_sensor_dt) - 1) for delta in sensor_dts)
    summary = {
        "label": args.label,
        "port": args.port,
        "baudrate": args.baudrate,
        "transport": transport,
        "output": output,
        "expected_field_count": expected_fields,
        "measurement_seconds": args.seconds,
        "valid_packets": valid,
        "invalid_lines": invalid,
        "inferred_sensor_packets_missing": inferred_missing,
        "host_arrival_dt_ms": _stats(host_dts),
        "sensor_dt_ms": _stats(sensor_dts),
        "gravity_norm_error": _stats(gravity_norm_errors),
        "gravity": {axis: _stats(gravity[index]) for index, axis in enumerate(("x", "y", "z"))},
        "gyro_dps": {axis: _stats(gyro[index]) for index, axis in enumerate(("x", "y", "z"))},
        "accel_mps2": {axis: _stats(accel[index]) for index, axis in enumerate(("x", "y", "z"))},
        "temperature_c": _stats(temperature),
        "csv": str(csv_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"samples: {csv_path}")
    print(f"summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
