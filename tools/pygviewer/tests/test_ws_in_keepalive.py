"""Regression test for the 2026-09-04 ``/ws/in`` keepalive-timeout bug, found forwarding real
HUPHY telemetry (``bridge/huphy_udp_forward.py``'s own module docstring has the full story):
a websocket CLIENT that only ever calls ``ws.send()`` and never ``ws.recv()`` eventually
stalls its own reader - ``/ws/in`` acks every accepted frame with ``{"ok": true, "seq": ...}``
and the ``websockets`` library queues unread INCOMING messages internally; once that queue
fills (reached in well under a second at 50 Hz), the reader stops processing ANY further
incoming bytes, including the PONG replies to the client's own keepalive PINGs, and the
client self-disconnects with ``ConnectionClosedError: sent 1011 (internal error) keepalive
ping timeout``. Confirmed NOT a server-side stall (see below).

This needs a REAL running server + a REAL asyncio websocket client - FastAPI/Starlette's
synchronous ``TestClient`` websocket support is an in-memory simulation that never exercises
actual ping/pong timing, so it cannot catch or verify this. This spins up the actual uvicorn
app on an ephemeral port, the same approach ``pygviewer/__main__.py`` itself uses.

Ping interval/timeout are shortened here (not the real 20s/20s default) purely so the test
runs in seconds, not minutes - the failure is about ping CYCLES elapsing while the reader is
stalled, not about the specific number 20. A live, real-timing confirmation (ping 20s/20s,
against the actual running dashboard process): a client that drains its queue ran past 180s
with zero disconnects; one that does not (the pre-fix ``huphy_udp_forward.py``/``dummy_tx.py``
pattern) disconnected at ~40s with the exact error text above - see the session report for
those numbers, not repeated here to keep this suite fast.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn

from pygviewer import CACHE_DIR
from pygviewer.api import build_app
from pygviewer.contract import load_contract
from pygviewer.sim_core import SimCore

websockets = pytest.importorskip("websockets")

VARIANT = "LegOnly-AB"
FAST_PING_S = 0.4  # short enough that a stalled reader misses a pong within a couple of seconds


def _free_port() -> int:
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.bind(("127.0.0.1", 0))
  port = s.getsockname()[1]
  s.close()
  return port


@pytest.fixture(scope="module")
def live_server():
  """A real uvicorn instance of the actual app, in a background thread - the exact shape
  ``pygviewer/__main__.py`` runs in production, on an ephemeral port so this test never
  competes with a real viewer (or another test run) on :8095."""
  core = SimCore(load_contract(CACHE_DIR, VARIANT), realtime=True)
  core.reset("knees_bent")
  core.start()  # a real background physics thread - the same GIL/lock contention a real
  # deployment has, so this test cannot pass "by accident" just because nothing else is
  # competing for the event loop.
  app = build_app(core, core.c.freshness())
  port = _free_port()
  cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
  server = uvicorn.Server(cfg)
  thread = threading.Thread(target=server.run, daemon=True)
  thread.start()
  t0 = time.monotonic()
  while not server.started and time.monotonic() - t0 < 10.0:
    time.sleep(0.02)
  assert server.started, "uvicorn did not report started within 10s"
  try:
    yield port, core
  finally:
    server.should_exit = True
    thread.join(timeout=5.0)
    core.stop()


async def _joint_state_msg(core, seq: int) -> str:
  names = core.act_names
  q = [float(core.d.qpos[core.a_q[i]]) for i in range(len(names))]
  return json.dumps(dict(
    v=1, type="JointState", t_ns=time.monotonic_ns(), seq=seq, src="real",
    contract_hash=None, joint_names=names, q=q,
  ))


async def _flood_and_drain(port: int, core, duration_s: float, drain: bool) -> dict:
  """Sends JointState at 50 Hz for ``duration_s``; if ``drain`` is True, a background task
  reads (and discards) every reply - the actual fix under test. Returns what happened."""
  result = {"disconnected_at": None, "error": None, "sent": 0, "acked": 0}

  async def _reader(ws):
    async for _raw in ws:
      result["acked"] += 1

  t0 = time.monotonic()
  async with websockets.connect(
    f"ws://127.0.0.1:{port}/ws/in", ping_interval=FAST_PING_S, ping_timeout=FAST_PING_S,
  ) as ws:
    reader_task = asyncio.create_task(_reader(ws)) if drain else None
    try:
      seq = 0
      while time.monotonic() - t0 < duration_s:
        seq += 1
        try:
          await ws.send(await _joint_state_msg(core, seq))
          result["sent"] = seq
        except websockets.exceptions.ConnectionClosed as exc:
          result["disconnected_at"] = time.monotonic() - t0
          result["error"] = f"{type(exc).__name__}: {exc}"
          return result
        await asyncio.sleep(0.02)  # 50 Hz
    finally:
      if reader_task is not None:
        reader_task.cancel()
        try:
          await reader_task
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
          pass
  return result


def test_draining_client_survives_50hz_streaming_well_past_the_stall_window(live_server):
  """The FIX under test: a client that drains its inbound queue must not be disconnected by
  its own stalled reader, no matter how long it streams. Runs well past the number of ping
  cycles that killed the non-draining client below (>= 20 cycles at FAST_PING_S vs the <=3
  cycles that were enough to kill an un-drained one)."""
  port, core = live_server
  duration_s = FAST_PING_S * 20  # comfortably past the failure window measured below
  result = asyncio.run(_flood_and_drain(port, core, duration_s, drain=True))
  assert result["error"] is None, f"draining client was disconnected: {result}"
  assert result["sent"] > 0
  assert result["acked"] > 0  # actually exercised the read path, not a no-op


def test_non_draining_client_reproduces_the_original_bug(live_server):
  """Negative control: proves this test harness is actually sensitive to the bug (a suite
  that never fails on the broken pattern would not have caught this in the first place, and
  would not catch a regression back to it). Mirrors the OLD huphy_udp_forward.py/dummy_tx.py
  pattern - send-only, no drain."""
  port, core = live_server
  result = asyncio.run(_flood_and_drain(port, core, duration_s=FAST_PING_S * 20, drain=False))
  assert result["error"] is not None, (
    "expected the send-only (non-draining) client to reproduce the keepalive-timeout "
    "disconnect - if this now passes, either the bug is gone for a different reason or "
    "this test stopped being sensitive to it; investigate before assuming a fix"
  )
  assert "1011" in result["error"] or "keepalive" in result["error"].lower(), result["error"]
