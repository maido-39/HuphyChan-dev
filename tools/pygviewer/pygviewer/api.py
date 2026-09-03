"""FastAPI surface, in the same process as the sim thread (default :8095, docs at /docs).

P0/P1 implements: ``GET /status``, ``GET /contract``, ``GET /snapshot``, ``POST /target``,
``POST /ankle``, ``POST /base``, ``POST /mode``, ``POST /reset`` and ``WS /ws/out``.
Everything else in ``schema.py`` is documented but answers 501 with the phase that owns it,
so a client author can see the whole contract today and code against it.

The WebSocket is **latest-only**: it samples the current snapshot at the requested rate and
never queues.  A slow consumer sees a lower frame rate, it does not make the process grow.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from . import __version__
from .schema import (
  AnkleTargetIn,
  BaseIn,
  BaseState,
  ContractOut,
  GainsIn,
  JointState,
  ModeIn,
  ObsSourceIn,
  PolicyLoadIn,
  Rates,
  ResetIn,
  Status,
  TargetIn,
  WIRE_VERSION,
)

_NOT_YET = {
  "/policy/load": "P2",
  "/policy/cmd": "P2",
  "/gains": "P2",
  "/obs_source": "P4",
  "/script/run": "P4",
  "/record/start": "P3",
  "/record/stop": "P3",
  "/ws/in": "P3",
}


def rss_mb() -> float | None:
  try:
    with open("/proc/self/statm") as f:
      return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6
  except Exception:
    return None


def build_app(core, freshness: dict) -> FastAPI:
  app = FastAPI(
    title="pygviewer",
    version=__version__,
    description=(
      "Pygmalion Sim<->Real viewer control API. Canonical joint names are the SIM names; "
      "all angles are radians, all torques N*m. Endpoints marked 501 are defined in the "
      "wire schema and implemented in a later phase - see tools/pygviewer/API.md."
    ),
  )
  seq = {"n": 0}

  def _status() -> Status:
    s = core.snapshot()
    seq["n"] += 1
    return Status(
      t_ns=time.monotonic_ns(),
      seq=seq["n"],
      contract_hash=core.c.contract_sha,
      variant=core.c.variant,
      mode=s.get("mode", "idle"),
      sim_time_s=s.get("t", 0.0),
      rates=Rates(**s.get("rates", {})),
      base=BaseState(**s.get("base", {})),
      contract_stale=bool(freshness.get("stale")),
      contract_checks=freshness.get("checks", {}),
      warnings=s.get("warnings", []),
      rss_mb=round(rss_mb() or 0.0, 1),
    )

  def _joint_state() -> JointState:
    s = core.snapshot()
    seq["n"] += 1
    names = s["act_names"]
    idx = [s["joint_names"].index(n) for n in names]
    return JointState(
      t_ns=time.monotonic_ns(),
      seq=seq["n"],
      src="sim",
      contract_hash=core.c.contract_sha,
      joint_names=names,
      q=[s["q"][i] for i in idx],
      qd=[s["qd"][i] for i in idx],
      tau_est=s["tau"],
      target=s["target"],
      gains={n: core.c.gains(n) for n in names},
      ankle_derived=s.get("ankle_derived"),
    )

  @app.get("/status", response_model=Status, summary="Rates, base state, contract freshness")
  def get_status():
    return _status()

  @app.get("/contract", response_model=ContractOut, summary="The full baked model contract")
  def get_contract():
    return ContractOut(contract=core.c.raw, freshness=freshness)

  @app.get("/snapshot", summary="Latest raw simulator snapshot (all joints, IMU, base)")
  def get_snapshot():
    return JSONResponse(core.snapshot())

  @app.get("/joints", response_model=JointState, summary="Canonical JointState, one shot")
  def get_joints():
    return _joint_state()

  @app.post("/target", summary="Set joint position targets (rad); values are clamped to safe_clip")
  def post_target(body: TargetIn):
    unknown = [n for n in body.values if n not in core.act_names]
    if unknown:
      raise HTTPException(400, f"not actuated joints of {core.c.variant}: {unknown}")
    core.submit({"op": "target", "values": body.values})
    return {"ok": True, "clamped_to": {n: list(core.c.clip(n)) for n in body.values}}

  @app.post("/ankle", summary="AB only: command the ankle in foot space (pitch/roll -> cranks)")
  def post_ankle(body: AnkleTargetIn):
    if core.ankle_inverse is None:
      raise HTTPException(409, f"{core.c.variant} drives the ankle directly; use /target")
    core.submit({"op": "ankle", "side": body.side, "pitch": body.pitch, "roll": body.roll})
    return {"ok": True, "note": core.c.raw["ankle_inverse"]["caveat"]}

  @app.post("/base", summary="Base anchor: mode free|fixed|pivot, pose, height, pivot point, ground")
  def post_base(body: BaseIn):
    cmd = {"op": "base", **{k: v for k, v in body.model_dump().items() if v is not None}}
    core.submit(cmd)
    return {"ok": True}

  @app.post("/reset", summary="Reset to a contract keyframe")
  def post_reset(body: ResetIn):
    core.submit({"op": "reset", "keyframe": body.keyframe})
    return {"ok": True}

  @app.post("/mode", summary="Run mode; idle|manual now, the rest are later phases")
  def post_mode(body: ModeIn):
    if body.mode not in ("idle", "manual"):
      raise HTTPException(501, f"mode {body.mode!r} is not implemented in P1 (see API.md)")
    core.submit({"op": "mode", "value": body.mode})
    return {"ok": True}

  for path, phase in _NOT_YET.items():
    if path.startswith("/ws"):
      continue

    def _stub(_p=path, _ph=phase):
      raise HTTPException(501, f"{_p} is defined in schema.py and implemented in {_ph}")

    app.add_api_route(
      path, _stub, methods=["POST"], summary=f"NOT IMPLEMENTED ({phase}) - schema is defined"
    )

  # keep the request models referenced so they appear in the OpenAPI schema
  @app.get("/schema/deferred", summary="Request models for the endpoints that answer 501")
  def deferred_models():
    return {
      "GainsIn": GainsIn.model_json_schema(),
      "ObsSourceIn": ObsSourceIn.model_json_schema(),
      "PolicyLoadIn": PolicyLoadIn.model_json_schema(),
      "wire_version": WIRE_VERSION,
      "phases": _NOT_YET,
    }

  @app.websocket("/ws/out")
  async def ws_out(ws: WebSocket):
    """Stream ``JointState`` + ``Status``, coalesced to ``?hz=`` (default 30, max 100)."""
    await ws.accept()
    hz = float(ws.query_params.get("hz", 30))
    hz = max(1.0, min(hz, 100.0))
    types = set((ws.query_params.get("types") or "JointState,Status").split(","))
    try:
      while True:
        if "JointState" in types:
          await ws.send_text(_joint_state().model_dump_json())
        if "Status" in types:
          await ws.send_text(_status().model_dump_json())
        await asyncio.sleep(1.0 / hz)
    except (WebSocketDisconnect, RuntimeError):
      return

  @app.websocket("/ws/in")
  async def ws_in(ws: WebSocket):
    await ws.accept()
    await ws.send_text(json.dumps({"error": "/ws/in is P3 (telemetry ingest); see API.md"}))
    await ws.close()

  return app
