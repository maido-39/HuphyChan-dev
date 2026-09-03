"""FastAPI surface, in the same process as the sim thread (default :8095, docs at /docs).

P0/P1 implements: ``GET /status``, ``GET /contract``, ``GET /snapshot``, ``POST /target``,
``POST /ankle``, ``POST /base``, ``POST /mode``, ``POST /reset`` and ``WS /ws/out``.
P2 adds: ``POST /policy/load``, ``GET /policy/list``, ``POST /policy/unload``,
``POST /policy/cmd``, ``GET /policy/io``, ``POST /obs_source`` (per-term switch; ``real``
answers 501 until the P3 bridge exists), ``GET|POST /gains`` and ``POST /mode`` with
``policy_sim``/``policy_shadow``. Everything else in ``schema.py`` is documented but answers
501 with the phase that owns it, so a client author can see the whole contract today and
code against it.

The WebSocket is **latest-only**: it samples the current snapshot at the requested rate and
never queues.  A slow consumer sees a lower frame rate, it does not make the process grow.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from . import __version__
from .schema import (
  AnkleTargetIn,
  CmdIn,
  PolicyIO,
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

  @app.post(
    "/mode",
    summary="Run mode: idle|manual|policy_sim|policy_shadow now; replay modes are P3/P4",
  )
  def post_mode(body: ModeIn):
    """``policy_sim``/``policy_shadow`` need a policy loaded first (``POST /policy/load``) -
    checked here synchronously so the caller gets an immediate 409 rather than a silent
    failure on the sim thread, which only ever sees commands through the async queue."""
    if body.mode in ("real_replay", "file_replay"):
      raise HTTPException(501, f"mode {body.mode!r} needs the P3/P4 telemetry bridge (see API.md)")
    if body.mode.startswith("policy") and core.policy is None:
      raise HTTPException(409, f"mode {body.mode!r} needs a policy loaded first (POST /policy/load)")
    core.submit({"op": "mode", "value": body.mode})
    return {"ok": True}

  @app.post("/policy/load", summary="Load a baked policy (onnx=, or pt= for a direct .pt)")
  def post_policy_load(body: PolicyLoadIn):
    """Refuses a policy whose ``model_contract_sha`` is not this model's, and one whose
    default pose differs by more than 1e-4 rad (the default pose IS the action offset)."""
    from .policy import PolicyContractMismatch

    pc = None
    onnx = body.onnx
    if body.name:
      p = Path(core.c.path).parent / f"{body.name}.policy_contract.json"
      if not p.exists():
        raise HTTPException(404, f"no baked policy contract named {body.name!r} ({p})")
      pc = json.loads(p.read_text())
      onnx = onnx or pc["onnx"]
    elif onnx:
      p = Path(onnx).with_suffix("").with_suffix(".policy_contract.json")
      cand = Path(str(onnx)[: -len(".onnx")] + ".policy_contract.json")
      if cand.exists():
        pc = json.loads(cand.read_text())
    if pc is None and not body.allow_uncontracted:
      raise HTTPException(
        400,
        "no policy contract found next to that file. A policy without a contract cannot be "
        "checked against this model; pass allow_uncontracted=true only for a throwaway test.",
      )
    try:
      info = core.load_policy(onnx=onnx, pt=body.pt, policy_contract=pc)
    except PolicyContractMismatch as exc:
      raise HTTPException(409, str(exc))
    except (ValueError, KeyError, FileNotFoundError) as exc:
      raise HTTPException(400, f"{type(exc).__name__}: {exc}")
    return info

  @app.get("/policy/list", summary="Baked policies available for this model variant")
  def get_policy_list():
    out = []
    for p in sorted(Path(core.c.path).parent.glob("*.policy_contract.json")):
      c = json.loads(p.read_text())
      out.append(
        dict(
          name=c["name"],
          variant=c["variant"],
          checkpoint=c["checkpoint"],
          obs_dim=c["obs_dim"],
          compatible=c.get("model_contract_sha") == core.c.contract_sha,
          model_contract_sha=c.get("model_contract_sha"),
        )
      )
    return out

  @app.post("/policy/unload", summary="Drop the loaded policy and fall back to manual")
  def post_policy_unload():
    core.clear_policy()
    return {"ok": True}

  @app.post("/policy/cmd", summary="Velocity command [vx, vy, wz] for the policy")
  def post_policy_cmd(body: CmdIn):
    core.submit({"op": "cmd", "value": [body.vx, body.vy, body.wz]})
    return {"ok": True}

  @app.get("/policy/io", response_model=PolicyIO, summary="Latest observation/action")
  def get_policy_io():
    s = core.snapshot()
    p = s.get("policy")
    if not p:
      raise HTTPException(409, "no policy loaded")
    seq["n"] += 1
    return PolicyIO(
      t_ns=time.monotonic_ns(),
      seq=seq["n"],
      src="policy",
      contract_hash=core.c.contract_sha,
      obs=p["obs"] or [],
      obs_sources=p["obs_sources"],
      action=p["action"],
      target=p["target"],
      cmd=p["cmd"],
    )

  @app.post("/obs_source", summary="Per observation TERM: sim or real")
  def post_obs_source(body: ObsSourceIn):
    if core.obs_mux is None:
      raise HTTPException(409, "no policy loaded; there are no observation terms to route")
    try:
      core.obs_mux.set(body.sources)
    except NotImplementedError as exc:
      raise HTTPException(501, str(exc))
    except (KeyError, ValueError) as exc:
      raise HTTPException(400, str(exc))
    return {"sources": core.obs_mux.sources, "mask": "".join(core.obs_mux.mask())}

  @app.get("/gains", summary="Current PD gains, with the training values alongside")
  def get_gains():
    return {"source": core.gains_source, "gains": core.gains_table()}

  @app.post("/gains", summary="Switch the PD source (train|real) and/or override per joint")
  def post_gains(body: GainsIn):
    try:
      table = core.set_gains(body.source, body.overrides)
    except (RuntimeError, KeyError, ValueError) as exc:
      raise HTTPException(400, str(exc))
    return {"source": core.gains_source, "gains": table}

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
    """Stream ``JointState`` / ``Status`` / ``PolicyIO``, coalesced to ``?hz=``.

    ``types=`` selects which (default ``JointState,Status``); ``hz`` is 1-100, default 30.
    Latest-only: a slow consumer sees fewer frames, never a backlog."""
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
        if "PolicyIO" in types and core.snapshot().get("policy"):
          await ws.send_text(get_policy_io().model_dump_json())
        await asyncio.sleep(1.0 / hz)
    except (WebSocketDisconnect, RuntimeError):
      return

  @app.websocket("/ws/in")
  async def ws_in(ws: WebSocket):
    await ws.accept()
    await ws.send_text(json.dumps({"error": "/ws/in is P3 (telemetry ingest); see API.md"}))
    await ws.close()

  return app
