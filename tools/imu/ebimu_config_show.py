#!/usr/bin/env python3
"""Read EBIMU configuration using HUPHY's existing ``<cfg>`` protocol table.

This is the pyserial-free equivalent of HUPHY's ``huphy-imu show`` for a host
where HUPHY's optional IMU dependency is absent.  ``<cfg>`` only queries
settings.  The required ``>`` resume byte is sent in ``finally`` so streaming
cannot be accidentally left stopped.  No persistent sensor setting is changed.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import sys
import termios
import time
from pathlib import Path


def _open(port: str, baudrate: int) -> int:
    baud_flag = getattr(termios, f"B{baudrate}", None)
    if baud_flag is None:
        raise ValueError(f"Unsupported baudrate {baudrate}")
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    attrs[0] = attrs[1] = attrs[3] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[4] = attrs[5] = baud_flag
    attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return fd


def _drain(fd: int, seconds: float) -> str:
    chunks: list[bytes] = []
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        readable, _, _ = select.select([fd], [], [], remaining)
        if readable:
            chunks.append(os.read(fd, 4096))
    return b"".join(chunks).decode("utf-8", errors="ignore")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--huphy-root", type=Path, required=True)
    parser.add_argument("--port", default="/dev/ebimu")
    parser.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()
    source = args.huphy_root / "src"
    if not (source / "huphy/sensors/ebimu/commands.py").is_file():
        raise SystemExit(f"HUPHY commands not found below {source}")
    sys.path.insert(0, str(source))
    from huphy.sensors.ebimu import commands

    fd = _open(args.port, args.baudrate)
    try:
        termios.tcflush(fd, termios.TCIFLUSH)
        os.write(fd, commands.QUERY_CONFIG.encode("ascii"))
        text = _drain(fd, 2.0)
    finally:
        # Required by EBIMU after <cfg>; this resumes output and changes nothing.
        os.write(fd, commands.CONFIG_RESUME.encode("ascii"))
        _drain(fd, 0.5)
        os.close(fd)
    settings = commands.parse_config("\n".join(line for line in text.splitlines() if not line.startswith("*")))
    result = {
        "port": args.port,
        "baudrate": args.baudrate,
        "settings": settings,
        "output": commands.output_from_config(settings),
        "detail": commands.describe(settings),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if settings else 1


if __name__ == "__main__":
    raise SystemExit(main())
