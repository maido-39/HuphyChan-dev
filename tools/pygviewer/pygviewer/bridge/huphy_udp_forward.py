"""huphy_udp_forward.py — forward HUPHY UDP telemetry into the LIVE viewer.

The `bridge huphy` CLI owns its own SimCore; this one instead converts HUPHY's JSON lines
(``{limb}/{motor}/{field}``) with the same ``HuphyBridge`` + joint map and pushes the
canonical ``JointState`` to the running viewer's ``WS /ws/in`` so the dashboard's
``real_replay`` mode and the plots show the real motor.

    .venv/bin/python3 -m tools.pygviewer.pygviewer.bridge.huphy_udp_forward \
        --listen 0.0.0.0:9870 --ws ws://127.0.0.1:8095/ws/in \
        --map tools/pygviewer/pygviewer/bridge/joint_map_bench.json --variant LegOnly-AB

Read-only with respect to the robot: it never sends anything toward HUPHY.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
import time

from ..contract import load_contract
from .. import CACHE_DIR
from .huphy_udp import HuphyBridge, JointMap


async def run(args) -> int:
  import websockets  # in the mjlab venv

  c = load_contract(args.cache, args.variant)
  bridge = HuphyBridge(c, JointMap(args.map) if args.map else JointMap())
  host, port = args.listen.rsplit(":", 1)
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  sock.bind((host, int(port)))
  sock.setblocking(False)
  loop = asyncio.get_running_loop()
  n_rx = n_tx = n_err = 0
  t_report = time.time()
  print(f"[fwd] listening UDP {args.listen} -> {args.ws}  (map={args.map or 'default'})", flush=True)
  async with websockets.connect(args.ws, max_size=2**20) as ws:
    while True:
      try:
        data = await asyncio.wait_for(loop.sock_recv(sock, 4096), timeout=1.0)
      except asyncio.TimeoutError:
        data = None
      if data:
        n_rx += 1
        try:
          payload = json.loads(data.decode("utf-8"))
          js = bridge.parse_fast(payload)
        except Exception as exc:  # malformed packet: count, keep going
          n_err += 1
          if n_err <= 5:
            print(f"[fwd] parse error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
          js = None
        if js is not None:
          await ws.send(js.model_dump_json())
          n_tx += 1
      if time.time() - t_report >= 5.0:
        print(f"[fwd] rx {n_rx} tx {n_tx} err {n_err}", flush=True)
        t_report = time.time()


def main(argv=None) -> int:
  ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--listen", default="0.0.0.0:9870")
  ap.add_argument("--ws", default="ws://127.0.0.1:8095/ws/in")
  ap.add_argument("--map", default=None, help="joint map JSON (default: joint_map_huphy.json)")
  ap.add_argument("--variant", default="LegOnly-AB")
  ap.add_argument("--cache", default=CACHE_DIR)
  args = ap.parse_args(argv)
  try:
    return asyncio.run(run(args))
  except KeyboardInterrupt:
    return 0


if __name__ == "__main__":
  raise SystemExit(main())
