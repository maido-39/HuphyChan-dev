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
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
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
  WIRE_VERSION,
  validate_joint_names,
)

_NOT_YET: dict[str, str] = {}

STATIC_DIR = Path(__file__).parent / "static"
PRESETS_DIR = Path(__file__).parent.parent / "presets"
_BUILTIN_PRESET_NAMES = ("train", "real")


def _read_side_mapping_verified() -> bool | None:
  """UI v2 top-bar badge: ``bridge/joint_map_huphy.json``'s own flag, read once at process
  start (it is a static hardware-bringup fact for the life of a run, not a live signal)."""
  try:
    p = Path(__file__).parent / "bridge" / "joint_map_huphy.json"
    return bool(json.loads(p.read_text())["side_mapping_verified"])
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
    transmitter or a real host must not tear down the whole telemetry session (R3/R5)."""
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
