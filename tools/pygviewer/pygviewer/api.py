"""FastAPI surface, in the same process as the sim thread (default :8095, docs at /docs).

P0/P1 implements: ``GET /status``, ``GET /contract``, ``GET /snapshot``, ``POST /target``,
``POST /ankle``, ``POST /base``, ``POST /mode``, ``POST /reset`` and ``WS /ws/out``.
P2 adds: ``POST /policy/load``, ``GET /policy/list``, ``POST /policy/unload``,
``POST /policy/cmd``, ``GET /policy/io``, ``POST /obs_source`` (per-term switch),
``GET|POST /gains`` and ``POST /mode`` with ``policy_sim``. P3 adds: ``WS /ws/in``
(JointState/ImuState ingest into ``core.real``), ``POST /record/{start,stop}``,
``POST /replay/{load,seek,speed}`` and ``POST /mode`` with ``real_replay``/``file_replay``.
P4 adds: ``POST /mode`` with ``policy_shadow`` (per-term sim/real obs mux, action never
transmitted - see ``policy.ObsBuilder.build_shadow``), ``POST /obs_source`` accepting
``real`` for real, ``POST /policy/shadow_follow``, ``POST /script/{run,stop}`` and
``WS /ws/in`` also accepting ``PolicyIO`` (a real host's own obs/action/cmd, the only source
for the shadow mux's last_action/cmd terms).

The WebSocket is **latest-only**: it samples the current snapshot at the requested rate and
never queues.  A slow consumer sees a lower frame rate, it does not make the process grow.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from . import scenario
from .schema import (
  AnkleTargetIn,
  CmdIn,
  PolicyIO,
  BaseIn,
  BaseState,
  ContractOut,
  GainsIn,
  ImuState,
  JointState,
  ModeIn,
  ObsSourceIn,
  PolicyLoadIn,
  PresetApplyIn,
  PresetSaveIn,
  Rates,
  ResetIn,
  ScriptRunIn,
  ShadowFollowIn,
  Status,
  TargetIn,
  ScenarioApplyIn,
  TxConfigIn,
  TxEnableIn,
  WIRE_VERSION,
  validate_joint_names,
)
from .hw_sync import SYNC_STALE_SKIP_S, HwSyncNotReady
from .tx import TxNotAllowed

_NOT_YET: dict[str, str] = {}

STATIC_DIR = Path(__file__).parent / "static"
MOCKUPS_DIR = Path(__file__).parent.parent / "mockups"
PRESETS_DIR = Path(__file__).parent.parent / "presets"
_BUILTIN_PRESET_NAMES = ("train", "real")


def _read_side_mapping_verified() -> bool | None:
  """UI v2 top-bar badge: the bridge's DEFAULT joint map's own flag, read once at process
  start (it is a static hardware-bringup fact for the life of a run, not a live signal).
  Imports ``DEFAULT_MAP_PATH`` from the bridge rather than hardcoding a filename here, so this
  always tracks whichever map ``bridge/huphy_udp.py`` actually defaults to - biped's
  ``joint_map_biped.json`` since 2026-09-04 (docs/121 section 12), not the legacy
  ``joint_map_huphy.json`` this used to point at directly."""
  try:
    from .bridge.huphy_udp import DEFAULT_MAP_PATH
    return bool(json.loads(DEFAULT_MAP_PATH.read_text())["side_mapping_verified"])
  except Exception:
    return None


def _safe_preset_name(name: str) -> str:
  safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_")
  if not safe:
    raise HTTPException(400, "preset name must contain at least one alphanumeric/-/_ character")
  if safe in _BUILTIN_PRESET_NAMES:
    raise HTTPException(400, f"{safe!r} is a built-in preset name (train/real); choose another")
  return safe


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
  side_mapping_verified = _read_side_mapping_verified()

  @app.exception_handler(RequestValidationError)
  async def _on_validation_error(_request, exc: RequestValidationError):
    """FastAPI's default 422 handler echoes ``ctx["input"]``/``ctx["error"]`` from
    pydantic's error dicts verbatim - for a rejected NaN/inf ``POST /target`` those are a
    non-JSON-serializable ``float`` and a raw ``ValueError`` object respectively
    (Starlette's ``JSONResponse`` enforces strict RFC JSON, ``allow_nan=False``, and neither
    survives its encoder), which without this turns a clean 422 rejection into an opaque 500
    (ROM clip task, 2026-09-04 - caught by ``tests/test_rom_clip.py`` sending a real NaN
    through the actual HTTP layer, not just unit-testing the validator in isolation). Only
    the plain-string ``loc``/``msg``/``type`` fields are echoed back - never the raw
    offending value or exception object, so this handler can never itself fail to
    serialize regardless of what triggered the error."""
    detail = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
              for e in exc.errors()]
    _record_nonfinite_rejections(_request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": detail})

  _NONFINITE_JOINTS_RE = re.compile(r"joint\(s\) \[(.*?)\]")

  def _record_nonfinite_rejections(path: str, errors: list[dict]) -> None:
    """A2 (item 3): a NaN/inf ``POST /target``/``/ankle`` is already rejected with a 422
    (ROM clip task, 2026-09-04) - this ALSO drops one ``side="send"`` violation record per
    named joint, since "a caller tried to send a non-finite value" is exactly the kind of
    thing the red panel should show, not just a one-off HTTP error a caller might not even
    be looking at. Never re-raises: a bug here must not turn a clean 422 into a 500.
    ``TargetIn._finite_only`` validates the WHOLE ``values`` dict at once and names the
    offending joints inside its own message (see schema.py) - the joint names are parsed out
    of that message rather than re-deriving them, so this stays correct if the validator's
    wording ever changes shape without silently going wrong; a message that does not match
    the expected shape falls back to the field's own ``loc`` (works for the ankle case,
    where pitch/roll validates per-scalar-field)."""
    if path not in ("/target", "/ankle"):
      return
    for e in errors:
      msg = e.get("msg", "")
      if "non-finite" not in msg:
        continue
      m = _NONFINITE_JOINTS_RE.search(msg)
      if m:
        names = [tok.strip(" '\"") for tok in m.group(1).split(",") if tok.strip()]
      else:
        loc = e.get("loc", [])
        names = [str(loc[-1])] if loc else ["?"]
      for n in names:
        core.violations.record(
          side="send", joint=n, value=None, src="send",
          extra={"rejected": "non-finite (NaN/inf)", "path": path},
        )

  def _sim_imu(s: dict) -> dict | None:
    """UI v2: the sim's own {gyro_rad_s, gravity_b}, from the same sensors ObsBuilder reads
    (imu_ang_vel, -imu_upvector) - so the IMU 3D widget and the Obs tab agree with the policy
    by construction, not by re-deriving the math a second time in this function."""
    raw = s.get("imu") or {}
    gyro = raw.get("imu_ang_vel")
    up = raw.get("imu_upvector")
    if gyro is None and up is None:
      return None
    return dict(
      gyro_rad_s=gyro,
      gravity_b=([-float(x) for x in up] if up is not None else None),
    )

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
      string=s.get("string"),
      contract_stale=bool(freshness.get("stale")),
      contract_checks=freshness.get("checks", {}),
      telemetry=dict(
        s.get("telemetry", {}),
        sign_sanity=s.get("sign_sanity", {}),
        **({"replay": s["replay"]} if "replay" in s else {}),
        **({"script": s["script"]} if "script" in s else {}),
      ),
      warnings=s.get("warnings", []),
      rss_mb=round(rss_mb() or 0.0, 1),
      imu=_sim_imu(s),
      side_mapping_verified=side_mapping_verified,
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
      run_id=s.get("script_run_id"),
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
    """``set_target``'s clip (``np.clip`` against the contract's ``safe_clip``) is a pure,
    deterministic function of the request - computed here synchronously, not read back off
    the sim thread, so the response is honest about what will actually be applied even
    though ``core.submit`` only queues the command for the next control tick (ROM clip task,
    2026-09-04: the old response echoed the clip RANGE only, never the applied value, so a
    caller could not tell a clamp had even happened)."""
    unknown = [n for n in body.values if n not in core.act_names]
    if unknown:
      raise HTTPException(400, f"not actuated joints of {core.c.variant}: {unknown}")
    clip_range = {n: list(core.c.clip(n)) for n in body.values}
    applied = {n: min(max(v, clip_range[n][0]), clip_range[n][1]) for n, v in body.values.items()}
    core.submit({"op": "target", "values": body.values})
    return {"ok": True, "requested": body.values, "applied": applied, "clip_range": clip_range}

  @app.post("/ankle", summary="AB only: command the ankle in foot space (pitch/roll -> cranks)")
  def post_ankle(body: AnkleTargetIn):
    """Mirrors ``/target``'s requested/applied honesty (ROM clip task, 2026-09-04): the
    foot-space request is converted to raw crank angles by ``ankle_inverse`` (unclamped,
    same as ``set_ankle``), then the SAME synchronous clip ``set_ankle``'s ``set_target``
    call will apply is computed here so the response never has to wait on the sim thread."""
    if core.ankle_inverse is None:
      raise HTTPException(409, f"{core.c.variant} drives the ankle directly; use /target")
    a, b = core.ankle_inverse(body.side, body.pitch, body.roll)
    names = (f"{body.side}_crank_A_joint", f"{body.side}_crank_B_joint")
    clip_range = {n: list(core.c.clip(n)) for n in names}
    requested = dict(zip(names, (a, b)))
    applied = {n: min(max(v, clip_range[n][0]), clip_range[n][1]) for n, v in requested.items()}
    core.submit({"op": "ankle", "side": body.side, "pitch": body.pitch, "roll": body.roll})
    return {
      "ok": True,
      "requested": requested,
      "applied": applied,
      "clip_range": clip_range,
      "note": core.c.raw["ankle_inverse"]["caveat"],
    }

  @app.post(
    "/base",
    summary="Base anchor: mode free|fixed|pivot|string, pose, height, pivot/hook point, ground",
  )
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
    summary="Run mode: idle|manual|policy_sim|policy_shadow|real_replay|file_replay",
  )
  def post_mode(body: ModeIn):
    """``policy_sim``/``policy_shadow`` need a policy loaded first (``POST /policy/load``);
    ``file_replay`` needs a recording loaded first (``POST /replay/load``). Checked here
    synchronously so the caller gets an immediate 409 rather than a silent failure on the
    sim thread, which only ever sees commands through the async queue."""
    if body.mode.startswith("policy") and core.policy is None:
      raise HTTPException(409, f"mode {body.mode!r} needs a policy loaded first (POST /policy/load)")
    if body.mode == "file_replay" and core.replayer is None:
      raise HTTPException(409, "mode 'file_replay' needs a recording loaded first (POST /replay/load)")
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
    except (KeyError, ValueError) as exc:
      raise HTTPException(400, str(exc))
    return {"sources": core.obs_mux.sources, "mask": "".join(core.obs_mux.mask())}

  @app.post("/script/run", summary="Play a scripts/*.json target-q sequence in manual mode")
  def post_script_run(body: ScriptRunIn):
    try:
      return core.run_script(body.path, body.run_id)
    except FileNotFoundError as exc:
      raise HTTPException(404, str(exc))
    except (KeyError, ValueError, RuntimeError) as exc:
      raise HTTPException(400, str(exc))

  @app.post("/script/stop", summary="Stop the running target-q sequence")
  def post_script_stop():
    try:
      return core.stop_script()
    except RuntimeError as exc:
      raise HTTPException(409, str(exc))

  @app.post("/policy/shadow_follow", summary="policy_shadow only: let the shadow action drive the LOCAL sim")
  def post_shadow_follow(body: ShadowFollowIn):
    """Affects nothing but this process's own sim step - the shadow action is never sent
    anywhere real (design doc R10; there is no code path in this codebase that could)."""
    core.submit({"op": "shadow_follow", "value": body.enabled})
    return {"ok": True}

  @app.post("/record/start", summary="Start streaming JointState to a jsonl.gz recording")
  def post_record_start(body: dict | None = None):
    path = (body or {}).get("path") if body else None
    try:
      return core.start_recording(path)
    except RuntimeError as exc:
      raise HTTPException(409, str(exc))

  @app.post("/record/stop", summary="Stop the current recording; returns path and line count")
  def post_record_stop():
    try:
      return core.stop_recording()
    except RuntimeError as exc:
      raise HTTPException(409, str(exc))

  @app.post("/replay/load", summary="Load a jsonl.gz recording for mode=file_replay")
  def post_replay_load(body: dict):
    path = body.get("path")
    if not path:
      raise HTTPException(400, "body needs {'path': '...'}")
    try:
      return core.load_replay(path)
    except (FileNotFoundError, ValueError) as exc:
      raise HTTPException(400, f"{type(exc).__name__}: {exc}")

  @app.post("/replay/seek", summary="Seek the loaded recording to a fraction [0,1]")
  def post_replay_seek(body: dict):
    if core.replayer is None:
      raise HTTPException(409, "no recording loaded")
    core.submit({"op": "replay_seek", "frac": float(body.get("frac", 0.0))})
    return {"ok": True}

  @app.post("/replay/speed", summary="Set the loaded recording's playback speed multiplier")
  def post_replay_speed(body: dict):
    if core.replayer is None:
      raise HTTPException(409, "no recording loaded")
    core.submit({"op": "replay_speed", "speed": float(body.get("speed", 1.0))})
    return {"ok": True}

  @app.get("/gains", summary="Current PD gains, with the training values alongside")
  def get_gains():
    return {"source": core.gains_source, "gains": core.gains_table()}

  @app.post("/gains", summary="Switch the PD source (train|real) and/or override per joint")
  def post_gains(body: GainsIn):
    try:
      table = core.set_gains(body.source, body.overrides, body.clear_overrides)
    except (RuntimeError, KeyError, ValueError) as exc:
      raise HTTPException(400, str(exc))
    return {"source": core.gains_source, "gains": table}

  @app.post("/tx/config", summary="UI v2 TX: (re)configure the TxClient - host/port/enable/kp_max/kd_max/ttl_ms")
  def post_tx_config(body: TxConfigIn):
    """Refused (409) while armed - ``POST /tx/disarm`` first, so the wire format (which
    joints this client will ever send) never changes mid-stream."""
    unknown = [n for n in body.enable if n not in core.act_names]
    if unknown:
      raise HTTPException(400, f"not actuated joints of {core.c.variant}: {unknown}")
    try:
      core.tx.configure(
        body.host, body.port, body.enable, kp_max=body.kp_max, kd_max=body.kd_max, ttl_ms=body.ttl_ms
      )
    except TxNotAllowed as exc:
      raise HTTPException(409, str(exc))
    # Sync-before-arm gate (hw_sync.py, docs/123 section 10.2): a reconfigure can change which
    # joints TX will ever send - an old sync computed against a different enable list must not
    # silently keep covering the new one.
    core.hw_sync.invalidate("TX reconfigured (POST /tx/config)")
    return core.tx.status()

  @app.post("/tx/enable", summary="UI v2 TX stage 1: turn the TX panel on/off (needs POST /tx/config first)")
  def post_tx_enable(body: TxEnableIn):
    try:
      core.tx.set_enabled(body.on)
    except TxNotAllowed as exc:
      raise HTTPException(409, str(exc))
    return core.tx.status()

  def _target_and_real_now() -> tuple[dict[str, float], dict[str, float | None]]:
    """The current manual target and the current live real value, per actuated joint - the
    SAME thread-safe read every other endpoint already uses (``core.snapshot()`` /
    ``core.real.snapshot_joints()``), never the raw ``core.target`` array from this (API)
    thread. Shared by ``POST /sync_from_real``, ``POST /tx/arm`` and ``GET /tx/status`` so the
    three never disagree about what "now" means."""
    s = core.snapshot()
    target_now = dict(zip(s["act_names"], s["target"]))
    real_snap = core.real.snapshot_joints()
    real_now = {n: real_snap[n]["q"] for n in core.act_names}
    return target_now, real_now

  @app.post(
    "/sync_from_real",
    summary="Set every fresh real-telemetry joint's manual target = its live measured value",
  )
  def post_sync_from_real():
    """The fix for a real near-miss (docs/123 section 10.2): a manual target left over far
    from where the real joint actually sits is exactly what ``POST /tx/arm`` now refuses to
    send until this has been called - see ``hw_sync.py``'s module docstring for the incident
    and the full state machine.

    Refuses (409) only when there has NEVER been any real telemetry on this process at all
    (``core.real.rx_count == 0``) - a genuinely empty stream, not merely "most joints have no
    data" (the bench today: 1 of 12 joints wired up is a normal, syncable state, not an
    error). Every OTHER outcome is reported honestly rather than silently smoothed over:
    a joint with no data, stale data (older than 0.5s) or a non-finite sample is named in
    ``skipped`` with its reason; a synced value outside the contract's safe_clip is named in
    ``clipped`` with the raw value, the applied (clamped) value and the range - sim cannot
    reproduce a real pose outside its own command window, and this must never be hidden.

    A joint that HAS carried at least one HUPHY diag field (temp/age/ack/miss) but whose
    ``GET /health`` verdict is currently ``"dead"`` while its position field is still fresh
    (age <= 0.5s) is skipped as ``"no real data (motor not responding)"`` rather than synced -
    2026-09-04 bench finding: a physically disconnected motor still occupies a slot in every
    50 Hz JointState frame and reports ``q=0.0``, indistinguishable from a real value by
    itself; only the robot's own diag fields (ack/miss/motor_age_ms) say the motor never
    answered. Syncing that phantom 0.0 as a real target would arm TX with a command to a
    joint that was never actually measured. A joint that has NEVER carried any field at all
    (this process's own reception, not just diag) still gets the plain ``"no real data"``
    reason, unchanged - that case has nothing diag-based to distinguish it by.
    """
    if not core.real.rx_count:
      raise HTTPException(
        409,
        "no real telemetry has ever been received on this process (rx_count=0) - connect a "
        "receiver/bridge or bench transmitter over WS /ws/in before syncing",
      )
    target_before, _ = _target_and_real_now()
    real_snap = core.real.snapshot_joints()
    joints_health = core.real.health(expected_period_s=core.dt * core.decimation)["joints"]
    synced: dict[str, float] = {}
    real_at_sync: dict[str, float] = {}
    clip_ranges: dict[str, tuple[float, float]] = {}
    clipped: dict[str, dict] = {}
    skipped: dict[str, str] = {}
    for n in core.act_names:
      age = core.real.joint_age_s(n)
      jh = joints_health.get(n, {})
      if jh.get("diag") and jh.get("state") == "dead" and age is not None and age <= SYNC_STALE_SKIP_S:
        skipped[n] = "no real data (motor not responding)"
        continue
      q = real_snap.get(n, {}).get("q")
      if q is None:
        skipped[n] = "no real data"
        continue
      if not math.isfinite(q):
        skipped[n] = "nan"
        continue
      if age is None or age > SYNC_STALE_SKIP_S:
        skipped[n] = "stale"
        continue
      lo, hi = core.c.clip(n)
      applied = min(max(q, lo), hi)
      if applied != q:
        clipped[n] = {"real": q, "applied": applied, "range": [lo, hi]}
      synced[n] = applied
      real_at_sync[n] = q
      clip_ranges[n] = (lo, hi)
    max_delta_before = max(
      (abs(synced[n] - target_before.get(n, synced[n])) for n in synced), default=0.0
    )
    if synced:
      core.submit({"op": "target", "values": synced})
    sync_token = core.hw_sync.record_sync(synced, real_at_sync, clip_ranges, core.c.contract_sha)
    return {
      "synced": synced,
      "clipped": clipped,
      "skipped": skipped,
      "max_delta_before": max_delta_before,
      "sync_token": sync_token,
      "t": time.time(),
    }

  @app.post("/tx/arm", summary="UI v2 TX stage 2: arm hardware transmit - manual mode only")
  def post_tx_arm():
    """Refuses (409) unless stage 1 is enabled AND the sim is in ``manual`` mode (design item
    2: policy output must never be transmittable), AND (docs/123 section 10.2) a valid
    ``POST /sync_from_real`` covers every joint TX is configured to send - see
    ``hw_sync.HwSyncState.check_arm_ready`` for the exact rule and ``hw_sync.py``'s module
    docstring for why this exists.

    Check order matters: TX's OWN preconditions (configured, enabled, mode) are checked
    FIRST via ``check_armable`` (no side effects) so "you haven't configured TX yet" always
    surfaces before "you haven't synced yet" even when both would fail - the more
    fundamental setup step should be the one an operator sees. Only once those pass is the
    sync gate checked, and only once THAT passes does this actually arm.

    The response's ``sync.clip_warnings`` (2026-09-04 bench fix) lists every synced joint
    whose real pose sat outside the model's safe_clip range at sync time - arming moves it,
    and the warning names the real position, the model range, and the exact travel distance
    BEFORE the packet goes out, rather than an operator discovering it from the robot. This
    never blocks the arm (see ``hw_sync.HwSyncState.clip_warnings``'s docstring)."""
    try:
      core.tx.check_armable(core.mode)
    except TxNotAllowed as exc:
      raise HTTPException(409, str(exc))
    ages = {n: core.real.joint_age_s(n) for n in core.act_names}
    core.hw_sync.refresh_staleness(ages, core.c.contract_sha)
    target_now, real_now = _target_and_real_now()
    try:
      core.hw_sync.check_arm_ready(core.tx.enabled_motors, target_now, real_now)
    except HwSyncNotReady as exc:
      raise HTTPException(409, str(exc))
    try:
      core.tx.arm(core.mode)
    except TxNotAllowed as exc:
      raise HTTPException(409, str(exc))
    result = core.tx.status()
    result["sync"] = core.hw_sync.status(target_now, real_now)
    return result

  @app.post("/tx/disarm", summary="UI v2 TX: disarm")
  def post_tx_disarm():
    core.tx.disarm(reason="operator")
    return core.tx.status()

  @app.post("/tx/heartbeat", summary="UI v2 TX: keyboard dead-man keep-alive (Space, held, ~100ms cadence)")
  def post_tx_heartbeat():
    try:
      core.tx.heartbeat()
    except TxNotAllowed as exc:
      raise HTTPException(409, str(exc))
    return {"ok": True}

  @app.get(
    "/tx/status",
    summary="UI v2 TX: armed/sending/enable/last_seq/rate/deadman_age/rejected_count + sync gate",
  )
  def get_tx_status():
    """``sync`` (hw_sync.HwSyncState.status, docs/123 section 10.2) is refreshed for
    staleness on every call, so a client polling only this endpoint sees an invalidated sync
    (e.g. telemetry that quietly went stale) at most one poll late - never has to separately
    poll ``GET /health`` to notice."""
    ages = {n: core.real.joint_age_s(n) for n in core.act_names}
    core.hw_sync.refresh_staleness(ages, core.c.contract_sha)
    target_now, real_now = _target_and_real_now()
    st = core.tx.status()
    st["sync"] = core.hw_sync.status(target_now, real_now)
    return st

  @app.get(
    "/scenario",
    summary="What the current setup is called, or what stands between it and a name",
  )
  def get_scenario():
    """The name is COMPUTED from three axes, never stored: the run mode, whether TX is armed,
    and which program the robot reports. All three have to match a recipe exactly - see
    ``scenario.py``. The third axis is a measurement with an age, so it becomes "unknown" on
    its own when the robot stops talking rather than lingering as the last thing an operator
    asserted."""
    age = None
    if core.real.prog_t is not None:
      age = round(time.monotonic() - core.real.prog_t, 3)
    return scenario.status(
      mode=core.mode,
      tx_armed=bool(core.tx.armed),
      reported_id=core.real.prog_id,
      age_s=age,
    )

  @app.post(
    "/scenario/apply",
    summary="Set the two axes the viewer owns (mode, TX arm) toward a named setup",
  )
  def post_scenario_apply(body: ScenarioApplyIn):
    """Deliberately does NOT touch the robot-side program.

    Pressing a button in the viewer cannot make the robot be running something else, and a
    control that quietly restarts a robot program over SSH - one that turns torque on - is
    not a thing a UI should do on one click. The response carries what the operator still has
    to do by hand, and ``/scenario`` will confirm it once the robot says so itself.

    Arming is never done here either: reaching the one setup that drives hardware still goes
    through sync -> arm -> dead-man, unchanged.
    """
    sc = scenario.BY_KEY.get(body.key)
    if sc is None:
      raise HTTPException(404, f"모르는 조합: {body.key}")
    if not sc.available:
      raise HTTPException(409, f"{sc.name_ko}: {sc.unavailable_reason}")
    done, todo = [], []
    if core.mode != sc.mode:
      # Same preconditions POST /mode enforces - checked here rather than duplicated, so a
      # scenario button can never reach a mode the mode control itself would have refused.
      if sc.mode.startswith("policy") and core.policy is None:
        raise HTTPException(409, f"'{sc.mode}' 모드는 정책을 먼저 불러와야 합니다 "
                                 f"(POST /policy/load)")
      if sc.mode == "file_replay" and core.replayer is None:
        raise HTTPException(409, "'file_replay' 모드는 기록을 먼저 불러와야 합니다")
      core.submit({"op": "mode", "value": sc.mode})
      done.append(f"화면 모드를 '{sc.mode}' 로 바꿨습니다")
    if not sc.tx_armed and core.tx.armed:
      core.tx.disarm(reason=f"scenario {sc.key}")
      done.append("전송 무장을 해제했습니다")
    elif sc.tx_armed and not core.tx.armed:
      todo.append("전송을 무장하세요 — 실물로 나가는 전환이라 자동으로 하지 않습니다 "
                  "(0. 실물에서 값 가져오기 → 3. ARM → 스페이스)")
    if core.real.prog_id != sc.program:
      need = scenario.PROGRAMS[sc.program]
      todo.append(f"로봇에서 '{need['name']}' 를 실행하세요 ({need['label']})")
    return {"ok": True, "key": sc.key, "done": done, "todo": todo,
            "scenario": get_scenario()}

  @app.get("/presets", summary="UI v2: gains presets - built-in train/real + custom *.json")
  def get_presets():
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    custom = []
    for p in sorted(PRESETS_DIR.glob("*.json")):
      try:
        obj = json.loads(p.read_text())
        custom.append({"name": obj.get("name", p.stem), "gains": obj.get("gains", {})})
      except (json.JSONDecodeError, OSError):
        continue
    return {
      "builtin": {
        "train": "this model contract's own kp/kd - what the policy was optimised against",
        "real": "HUPHY robot_v1.0.yaml start point, uniform kp=10 kd=1 on every actuated joint",
      },
      "custom": custom,
    }

  @app.post("/presets", summary="UI v2: save a named custom gains preset")
  def post_presets_save(body: PresetSaveIn):
    unknown = [n for n in body.gains if n not in core.act_names]
    if unknown:
      raise HTTPException(400, f"not actuated joints of {core.c.variant}: {unknown}")
    safe = _safe_preset_name(body.name)
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    path = PRESETS_DIR / f"{safe}.json"
    path.write_text(json.dumps({"name": body.name, "gains": body.gains}, indent=2))
    return {"ok": True, "path": str(path)}

  @app.post("/presets/apply", summary="UI v2: apply a preset (train|real|custom name) via POST /gains semantics")
  def post_presets_apply(body: PresetApplyIn):
    if body.name == "train":
      table = core.set_gains(source="train", clear_overrides=True)
      return {"source": core.gains_source, "gains": table}
    if body.name == "real":
      overrides = {n: {"kp": 10.0, "kd": 1.0} for n in core.act_names}
      table = core.set_gains(overrides=overrides)
      return {"source": core.gains_source, "gains": table}
    safe = _safe_preset_name(body.name)
    path = PRESETS_DIR / f"{safe}.json"
    if not path.exists():
      raise HTTPException(404, f"no custom preset named {body.name!r} ({path})")
    obj = json.loads(path.read_text())
    try:
      table = core.set_gains(overrides=obj.get("gains", {}))
    except (KeyError, ValueError) as exc:
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

  @app.get(
    "/violations",
    summary="A2: ROM/torque violation records - recv, recv_torque, sim_actuator, send",
  )
  def get_violations(limit: int = 100, side: str | None = None):
    """``limit`` caps how many of the most recent (optionally ``side``-filtered) records
    come back; the ring buffer itself holds at most 200 total, across every side (see
    ``violations.py``). Each record gets an ``age_s`` computed at request time (``t_mono`` is
    this process's own monotonic clock, not portable to a client on its own)."""
    now = time.monotonic()
    recs = core.violations.list(limit=limit, side=side)
    for r in recs:
      r["age_s"] = round(now - r["t_mono"], 3)
    return {
      "records": recs,
      "by_joint": core.violations.counts_by_joint(),
      "total": core.violations.total_count(),
    }

  @app.post(
    "/violations/clear",
    summary="A2: clear the violation ring buffer and every cumulative count",
  )
  def post_violations_clear():
    core.violations.clear()
    return {"ok": True}

  @app.get(
    "/health",
    summary="Motor health (2026-09-04): is the real robot actually responding, per motor",
  )
  def get_health():
    """``link`` mirrors the same rx-rate/age/seq-gap numbers ``GET /status``'s
    ``telemetry`` already carries (this is not a second source of truth, just a
    convenience so a caller watching only motor health does not also have to poll
    ``/status``). ``joints`` is per-actuated-joint: ``state`` (ok/warn/dead - see
    ``telemetry.RealState.health``), this process's own reception age, the robot's
    self-reported ``motor_age_ms``/``ack``/``miss``/``temp_c`` (``None`` when this joint has
    never carried a diag field at all - ``diag`` says so explicitly, never silently treated
    as healthy), and the last position received."""
    rs = core.real.status()
    h = core.real.health(expected_period_s=core.dt * core.decimation)
    return {
      "link": dict(
        connected=bool(rs["rx_count"]),
        rx_hz=rs["rx_hz"],
        age_s=rs["age_s"],
        seq_gaps=rs["seq_gaps"],
        last_seq=core.real.last_seq,
      ),
      "joints": h["joints"],
      "summary": h["summary"],
    }

  def _real_joint_state() -> JointState | None:
    """UI v2: the RECEIVED (real) side of the same canonical JointState, for the dashboard's
    plot overlay - only ever sent when something has actually arrived over ``/ws/in`` (a
    dummy transmitter, a bridge, or a real host), so a disconnected real side costs this
    endpoint nothing. Reuses the JointState schema as-is (src='real'); it is not a new wire
    shape, just a second populated instance of the existing one."""
    if not core.real.rx_count:
      return None
    s = core.real.snapshot_joints()
    names = list(s.keys())
    seq["n"] += 1
    return JointState(
      t_ns=time.monotonic_ns(),
      seq=seq["n"],
      src="real",
      contract_hash=core.c.contract_sha,
      joint_names=names,
      q=[s[n]["q"] for n in names],
      qd=[s[n]["qd"] for n in names],
      tau_est=[s[n]["tau"] for n in names],
      target=[s[n]["target"] for n in names],
      ankle_derived=dict(core.real.ankle_derived) or None,
    )

  @app.websocket("/ws/out")
  async def ws_out(ws: WebSocket):
    """Stream ``JointState`` / ``Status`` / ``PolicyIO``, coalesced to ``?hz=``.

    ``types=`` selects which (default ``JointState,Status``); ``hz`` is 1-100, default 30.
    Latest-only: a slow consumer sees fewer frames, never a backlog. UI v2: whenever
    ``JointState`` is requested AND real telemetry has arrived at least once, a SECOND
    ``JointState`` frame (``src='real'``) follows the sim one every tick - the dashboard's
    plot ring buffer tells sim/real apart by that field, exactly like every other consumer
    of this schema already does."""
    await ws.accept()
    hz = float(ws.query_params.get("hz", 30))
    hz = max(1.0, min(hz, 100.0))
    types = set((ws.query_params.get("types") or "JointState,Status").split(","))
    try:
      while True:
        if "JointState" in types:
          await ws.send_text(_joint_state().model_dump_json())
          real = _real_joint_state()
          if real is not None:
            await ws.send_text(real.model_dump_json())
        if "Status" in types:
          await ws.send_text(_status().model_dump_json())
        if "PolicyIO" in types and core.snapshot().get("policy"):
          await ws.send_text(get_policy_io().model_dump_json())
        await asyncio.sleep(1.0 / hz)
    except (WebSocketDisconnect, RuntimeError):
      return

  # ------------------------------------------------------------- UI v2 dashboard (layout B)
  app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
  # Read-only mount so clickable UI mockups (layout_*, scenario_*) can be reviewed in a
  # browser the same way the real dashboard is served, without touching dashboard.{js,html}.
  if MOCKUPS_DIR.is_dir():
    app.mount("/mockups", StaticFiles(directory=str(MOCKUPS_DIR)), name="mockups")

  @app.get("/", include_in_schema=False)
  def get_dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html")

  @app.get("/dash", include_in_schema=False)
  def get_dashboard_alias():
    return FileResponse(STATIC_DIR / "dashboard.html")

  @app.websocket("/ws/in")
  async def ws_in(ws: WebSocket):
    """Receive JointState/ImuState/PolicyIO (schema.py wire format), one JSON object per
    text frame. ``PolicyIO`` (P4) is a real host's OWN obs/action/cmd - the only source the
    shadow obs mux has for its last_action/generated_commands terms, since there is no other
    wire concept of "what velocity was the robot actually commanded".

    Every accepted message gets ``{"ok": true, "seq": ...}`` back; a bad one gets
    ``{"error": "..."}`` and the connection stays open - one malformed frame from a dummy
    transmitter or a real host must not tear down the whole telemetry session (R3/R5).

    **A client MUST read these replies, even if it does not care about them** (2026-09-04
    bug, found forwarding real telemetry - see ``bridge/huphy_udp_forward.py``'s module
    docstring for the full story and measured numbers). A send-only websocket CLIENT that
    never calls ``recv()``/iterates the connection lets its OWN receive queue fill with these
    acks; once full, most websocket libraries (including the ``websockets`` package this
    repo's own clients use) stop reading the socket AT ALL - including the PONG replies to
    the client's own keepalive PINGs - and the client silently times itself out and
    disconnects with ``ConnectionClosedError: sent 1011 (internal error) keepalive ping
    timeout`` after roughly a minute at default ping settings. This looks exactly like a
    server hang from the outside; it is not one (confirmed: this handler kept accepting and
    acking a 50 Hz stream for 180+s straight against a client that actually drained its
    queue, with a real background physics thread running concurrently). Both first-party
    clients (``bridge/huphy_udp_forward.py``, ``bridge/dummy_tx.py``) run a background task
    that drains every reply - copy that pattern in any new client, do not just ``send()``."""
    await ws.accept()
    try:
      while True:
        text = await ws.receive_text()
        try:
          obj = json.loads(text)
        except json.JSONDecodeError as exc:
          await ws.send_text(json.dumps({"error": f"invalid JSON: {exc}"}))
          continue
        typ = obj.get("type") if isinstance(obj, dict) else None
        try:
          if typ == "JointState":
            msg = JointState.model_validate(obj)
            unknown = validate_joint_names(msg.joint_names, core.act_names)
            if unknown:
              await ws.send_text(json.dumps({"error": f"unknown joints: {unknown}"}))
              continue
            core.real.ingest_joint_state(msg)
          elif typ == "ImuState":
            core.real.ingest_imu_state(ImuState.model_validate(obj))
          elif typ == "PolicyIO":
            core.real.ingest_policy_io(PolicyIO.model_validate(obj))
          else:
            await ws.send_text(
              json.dumps({"error": f"/ws/in accepts JointState/ImuState/PolicyIO, not {typ!r}"})
            )
            continue
          await ws.send_text(json.dumps({"ok": True, "seq": obj.get("seq")}))
        except Exception as exc:  # a bad frame must never take the socket down
          await ws.send_text(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
    except WebSocketDisconnect:
      return

  return app
