"""huphy_udp_forward.py — forward HUPHY UDP telemetry into the LIVE viewer.

The `bridge huphy` CLI owns its own SimCore; this one instead converts HUPHY's JSON lines
(``{limb}/{motor}/{field}``) with the same ``HuphyBridge`` + joint map and pushes the
canonical ``JointState`` to the running viewer's ``WS /ws/in`` so the dashboard's
``real_replay`` mode and the plots show the real motor.

    .venv/bin/python3 -m tools.pygviewer.pygviewer.bridge.huphy_udp_forward \
        --listen 0.0.0.0:9870 --ws ws://127.0.0.1:8095/ws/in \
        --map tools/pygviewer/pygviewer/bridge/joint_map_bench.json --variant LegOnly-AB

Read-only with respect to the robot: it never sends anything toward HUPHY.

**Bug fixed 2026-09-04** (found forwarding real telemetry: ~60s in, the client raised
``ConnectionClosedError: sent 1011 (internal error) keepalive ping timeout`` and the viewer's
telemetry age grew unbounded until an external respawn loop restarted it). Root cause,
confirmed with a standalone repro against the live dashboard: this client only ever called
``ws.send()`` and NEVER ``ws.recv()`` - ``/ws/in`` acks every accepted frame with
``{"ok": true, "seq": ...}``, and the ``websockets`` library queues unread INCOMING messages
internally; once that queue fills (default ``max_queue``, reached in under a second at 50 Hz),
the client's OWN reader task stalls and stops processing ANY further incoming bytes -
including the PONG replies to this client's own keepalive PINGs. The client then times itself
out and closes the connection - from the outside this looks exactly like "the server hung",
but it is a stalled READ side on this client caused by an un-drained receive queue, not a
server-side stall (measured: a client that sends but never receives disconnects this way in
~14s at ping_interval=ping_timeout=2s; one that drains the queue via a background reader task
ran the same test past 90s at real 20s/20s defaults with zero disconnects). Fixed by running a
background task that continuously drains (and logs) whatever the server sends back, plus an
outer reconnect loop as a second line of defense against a real network/server hiccup - this
also means an external supervisor (``fwd_supervisor.sh``) is no longer required for THIS
failure mode, though keeping one running costs nothing.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import socket
import sys
import time

from ..contract import load_contract
from .. import CACHE_DIR
from .huphy_udp import HuphyBridge, JointMap


async def _drain_replies(ws, stats: dict) -> None:
  """Read (and discard, except for logging server-reported errors) everything ``/ws/in``
  sends back. This is NOT optional bookkeeping - see the module docstring's 2026-09-04 bug
  note: a websocket client that only ever sends and never receives eventually stalls its own
  reader once the unread-message queue fills, which then also stops it from seeing PONG
  replies to its own keepalive pings and it self-disconnects. Runs as a background task for
  the lifetime of one connection; ``ws.__aiter__`` ends cleanly when the connection closes."""
  async for raw in ws:
    stats["acked"] += 1
    try:
      obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
      continue
    if isinstance(obj, dict) and obj.get("error"):
      stats["errors"] += 1
      if stats["errors"] <= 5:
        print(f"[fwd] server reported: {obj['error']}", file=sys.stderr, flush=True)


async def _forward_until_disconnected(sock, bridge, ws, counters: dict) -> None:
  loop = asyncio.get_running_loop()
  stats = {"acked": 0, "errors": 0}
  drain_task = asyncio.create_task(_drain_replies(ws, stats))
  t_report = time.time()
  try:
    while True:
      try:
        data = await asyncio.wait_for(loop.sock_recv(sock, 4096), timeout=1.0)
      except asyncio.TimeoutError:
        data = None
      if data:
        counters["rx"] += 1
        try:
          payload = json.loads(data.decode("utf-8"))
          js = bridge.parse_fast(payload)
        except Exception as exc:  # malformed packet: count, keep going
          counters["err"] += 1
          if counters["err"] <= 5:
            print(f"[fwd] parse error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
          js = None
        if js is not None:
          await ws.send(js.model_dump_json())
          counters["tx"] += 1
      if time.time() - t_report >= 5.0:
        print(
          f"[fwd] rx {counters['rx']} tx {counters['tx']} err {counters['err']} "
          f"acked {stats['acked']} server_errors {stats['errors']}",
          flush=True,
        )
        t_report = time.time()
  finally:
    drain_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
      await drain_task


async def run(args) -> int:
  import websockets  # in the mjlab venv

  c = load_contract(args.cache, args.variant)
  bridge = HuphyBridge(c, JointMap(args.map) if args.map else JointMap())
  host, port = args.listen.rsplit(":", 1)
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  sock.bind((host, int(port)))
  sock.setblocking(False)
  counters = {"rx": 0, "tx": 0, "err": 0}
  n_reconnects = 0
  backoff_s = 1.0
  print(f"[fwd] listening UDP {args.listen} -> {args.ws}  (map={args.map or 'default'})", flush=True)
  # Outer reconnect loop: a second line of defense (module docstring item 2) for an ACTUAL
  # network/server interruption - the queue-drain fix above is what stops the SELF-INFLICTED
  # disconnect from happening at all, this is for everything else (server restart, LAN blip).
  while True:
    try:
      async with websockets.connect(args.ws, max_size=2**20) as ws:
        if n_reconnects:
          print(f"[fwd] reconnected to {args.ws} (attempt {n_reconnects})", flush=True)
        backoff_s = 1.0
        await _forward_until_disconnected(sock, bridge, ws, counters)
    except (websockets.exceptions.ConnectionClosed, OSError) as exc:
      n_reconnects += 1
      print(
        f"[fwd] websocket disconnected ({type(exc).__name__}: {exc}) - "
        f"reconnecting in {backoff_s:.1f}s (attempt {n_reconnects})",
        file=sys.stderr, flush=True,
      )
      await asyncio.sleep(backoff_s)
      backoff_s = min(backoff_s * 2.0, 30.0)


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
