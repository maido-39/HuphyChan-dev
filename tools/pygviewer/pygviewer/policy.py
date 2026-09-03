"""Policy inference for the viewer: ONNX (default) or the .pt through mjlab (opt-in).

Three parts, and the split matters:

``ObsBuilder``   turns simulator state into the actor observation.  It is DATA-DRIVEN from
                 the policy contract's ``obs_terms`` - term order, joint subsets, history
                 length and which sensor feeds which slot all come from what the env
                 resolved at bake time.  Nothing here hardcodes "45" or "gyro first".  The
                 builder is proven against ``<name>.obs_parity.npz``, 40 consecutive control
                 steps of the real env, in ``tests/test_obs_order.py``.
``OnnxPolicy``   onnxruntime CPU session.  Input ``obs`` (1, obs_dim), output ``actions``.
``TorchPolicy``  loads the .pt through mjlab's runner.  Costs ~11 s and ~1.3 GB because it
                 has to build an env to construct the runner, so the UI warns first.

Action to target is the trainer's own expression (mjlab BaseAction.process_actions +
JointPositionAction):

    target = clip(raw_action * action_scale + default_q,  safe_clip_lo, safe_clip_hi)

with ``raw_action`` first clamped to +-``clip_actions`` by the vec-env wrapper.  The
observation's ``actions`` slot carries the RAW action, before scale and offset - that is
deliberate in the env config and getting it wrong is invisible until the gait is subtly
wrong, so the parity test covers it.
"""

from __future__ import annotations

from collections import deque

import numpy as np


class PolicyContractMismatch(RuntimeError):
  """Raised when a policy is asked to drive a model it was not trained on."""


# --------------------------------------------------------------------------- obs
class ObsBuilder:
  def __init__(self, model_contract, policy_contract: dict | None = None):
    self.mc = model_contract
    raw = model_contract.raw
    self.terms = (policy_contract or {}).get("obs_terms") or raw["obs_layout"]
    self.obs_dim = (policy_contract or {}).get("obs_dim") or raw["obs_dim"]
    self.joint_names = raw["joint_names"]
    self._sensors = {k.split("/")[-1]: (v["adr"], v["dim"]) for k, v in raw["sensors"].items()}
    self._full_sensor_key = {k.split("/")[-1]: k for k in raw["sensors"]}
    self.history_length = max(
      (int(t.get("history_length") or 0) for t in self.terms), default=0
    )
    # per-term precomputed index vectors
    self._plan = []
    for t in self.terms:
      func = t["func"]
      jn = t.get("joint_names")
      entry = dict(name=t["name"], func=func, history=int(t.get("history_length") or 0))
      if jn:
        entry["joint_names"] = list(jn)
        entry["idx"] = np.array([self.joint_names.index(n) for n in jn])
        entry["default"] = np.array([raw["default_q"][n] for n in jn])
      sn = t.get("sensor_name") or (t.get("params", {}) or {}).get("sensor_name")
      if sn:
        key = str(sn).split("/")[-1]
        if key not in self._sensors:
          raise KeyError(f"observation term {t['name']!r} wants sensor {sn!r}, not in contract")
        entry["sensor"] = self._sensors[key]
      self._plan.append(entry)
    dims = self.describe()
    if sum(d["dim"] for d in dims) != self.obs_dim:
      raise ValueError(
        f"observation layout sums to {sum(d['dim'] for d in dims)} but the contract says "
        f"{self.obs_dim}: {dims}"
      )

  def describe(self) -> list[dict]:
    out, off = [], 0
    for e in self._plan:
      if e["func"] in ("builtin_sensor", "projected_gravity_from_sensor"):
        n = e["sensor"][1]
      elif e["func"] in ("joint_pos_rel", "joint_vel_rel"):
        n = len(e["idx"]) * max(e["history"], 1)
      elif e["func"] == "last_action":
        n = len(self.mc.raw["action_joint_names"])
      elif e["func"] == "generated_commands":
        n = 3
      else:
        raise NotImplementedError(f"observation term func {e['func']!r} is not implemented")
      out.append(dict(name=e["name"], func=e["func"], dim=n, offset=off))
      off += n
    return out

  def _sim_term(self, e: dict, q_history, qd, sensordata, last_action, cmd) -> np.ndarray:
    """The sim-only value for one obs term - the body of the old ``build()``, factored out
    so ``build_shadow`` can fall back to exactly this per term rather than re-deriving it."""
    f = e["func"]
    if f == "builtin_sensor":
      a, n = e["sensor"]
      return np.asarray(sensordata[a : a + n], dtype=np.float64)
    if f == "projected_gravity_from_sensor":
      a, n = e["sensor"]
      return -np.asarray(sensordata[a : a + n], dtype=np.float64)
    if f == "joint_pos_rel":
      h = max(e["history"], 1)
      frames = list(q_history)[-h:]
      while len(frames) < h:  # backfill, exactly like the env's CircularBuffer does
        frames.insert(0, frames[0])
      parts = [np.asarray(fr, dtype=np.float64)[e["idx"]] - e["default"] for fr in frames]
      return np.concatenate(parts)
    if f == "joint_vel_rel":
      return np.asarray(qd, dtype=np.float64)[e["idx"]]
    if f == "last_action":
      return np.asarray(last_action, dtype=np.float64)
    if f == "generated_commands":
      return np.asarray(cmd, dtype=np.float64).reshape(3)
    raise NotImplementedError(f)

  def build(
    self,
    q_history: "deque[np.ndarray] | list[np.ndarray]",
    qd: np.ndarray,
    sensordata: np.ndarray,
    last_action: np.ndarray,
    cmd,
  ) -> np.ndarray:
    """``q_history`` is chronological, oldest first, each entry the FULL joint vector."""
    parts = [self._sim_term(e, q_history, qd, sensordata, last_action, cmd) for e in self._plan]
    obs = np.concatenate(parts)
    if obs.shape[0] != self.obs_dim:
      raise ValueError(f"built {obs.shape[0]}-D observation, contract wants {self.obs_dim}")
    return obs.astype(np.float32)

  def build_shadow(
    self,
    mux: "ObsSourceMux",
    sim: dict,
    real,
    real_q_history: "deque[dict[str, float]] | list[dict[str, float]]",
  ) -> tuple[np.ndarray, dict[str, str], list[str]]:
    """Per-TERM sim/real mux for ``policy_shadow`` (design doc R10 - the action this produces
    is for display/plot/record only; nothing here, or anywhere in this module, sends it
    anywhere real).

    ``sim`` is ``dict(q_history=, qd=, sensordata=, last_action=, cmd=)`` - the same inputs
    ``build()`` takes, kept as a dict because not every term needs every one of them.
    ``real`` is a ``telemetry.RealState``. ``real_q_history`` is a SEPARATE, purely-real
    rolling buffer of ``{joint_name: q}`` dicts (never interleaved with ``sim["q_history"]``'s
    sim frames within one term's window - R3/design item 1's "single-sourced per source").

    A term whose mux says ``real`` but whose real data is missing or older than
    ``mux.max_age_s`` falls back to sim for THAT TERM ONLY and is recorded in the returned
    warnings list - it is never silently fed a stale number.
    """
    parts: list[np.ndarray] = []
    effective: dict[str, str] = {}
    warnings: list[str] = []
    for e in self._plan:
      name = e["name"]
      want = mux.sources.get(name, "sim")
      val = None
      if want == "real":
        val = self._real_term(e, real, real_q_history, mux.max_age_s)
        if val is None:
          warnings.append(f"{name}: real requested but stale/missing (>{mux.max_age_s}s) - fell back to sim")
      if val is None:
        val = self._sim_term(
          e, sim["q_history"], sim["qd"], sim["sensordata"], sim["last_action"], sim["cmd"]
        )
        effective[name] = "sim"
      else:
        effective[name] = "real"
      parts.append(val)
    obs = np.concatenate(parts)
    if obs.shape[0] != self.obs_dim:
      raise ValueError(f"built {obs.shape[0]}-D observation, contract wants {self.obs_dim}")
    return obs.astype(np.float32), effective, warnings

  def _real_term(self, e: dict, real, real_q_history, max_age_s: float) -> np.ndarray | None:
    """The real-sourced value for one term, or ``None`` if it is missing/stale (caller falls
    back to sim). Each branch checks its OWN freshness clock - gyro/gravity share the IMU
    stamp, q-history shares the joint-telemetry stamp, last_action/cmd share the PolicyIO
    stamp - because these are genuinely different wire messages that can arrive at different
    rates from a real host."""
    f = e["func"]
    if f == "builtin_sensor":
      imu = real.imu
      age = real.imu_age_s()
      if imu is None or age is None or age > max_age_s:
        return None
      v = imu.get("gyro_rad_s")
      if v is None:
        return None
      n = e["sensor"][1]
      return np.asarray(v[:n], dtype=np.float64)
    if f == "projected_gravity_from_sensor":
      imu = real.imu
      age = real.imu_age_s()
      if imu is None or age is None or age > max_age_s:
        return None
      v = imu.get("gravity_b")
      return None if v is None else np.asarray(v, dtype=np.float64)
    if f == "joint_pos_rel":
      age = real.age_s()
      if age is None or age > max_age_s:
        return None
      names = e["joint_names"]
      h = max(e["history"], 1)
      frames = list(real_q_history)[-h:]
      if not frames or any(fr.get(n) is None for fr in frames for n in names):
        return None
      while len(frames) < h:
        frames.insert(0, frames[0])
      parts = [np.array([fr[n] for n in names], dtype=np.float64) - e["default"] for fr in frames]
      return np.concatenate(parts)
    if f == "last_action":
      age = real.policy_io_age_s()
      pio = real.policy_io
      if pio is None or age is None or age > max_age_s:
        return None
      act = pio.get("action")
      if act is None or len(act) != len(self.mc.raw["action_joint_names"]):
        return None
      return np.asarray(act, dtype=np.float64)
    if f == "generated_commands":
      age = real.policy_io_age_s()
      pio = real.policy_io
      if pio is None or age is None or age > max_age_s:
        return None
      c = pio.get("cmd")
      return None if c is None else np.asarray(c, dtype=np.float64).reshape(3)
    return None  # joint_vel_rel and anything future: no real source defined yet


# --------------------------------------------------------------------------- policies
class OnnxPolicy:
  name = "onnx"

  def __init__(self, onnx_path: str, contract: dict | None = None):
    import onnxruntime as rt

    self.path = onnx_path
    self.contract = contract or {}
    so = rt.SessionOptions()
    so.intra_op_num_threads = 1  # a GPU trainer owns the machine; do not fan out
    so.inter_op_num_threads = 1
    self.sess = rt.InferenceSession(onnx_path, so, providers=["CPUExecutionProvider"])
    self.input_name = self.sess.get_inputs()[0].name
    self.obs_dim = int(self.sess.get_inputs()[0].shape[-1])
    self.action_dim = int(self.sess.get_outputs()[0].shape[-1])

  def __call__(self, obs: np.ndarray) -> np.ndarray:
    x = np.asarray(obs, dtype=np.float32).reshape(1, -1)
    return self.sess.run(None, {self.input_name: x})[0].reshape(-1)


class TorchPolicy:
  """Direct .pt load.  Builds an mjlab env to construct the runner: slow and heavy."""

  name = "torch"

  def __init__(self, pt_path: str, variant: str, init_bent: bool = True):
    from dataclasses import asdict

    import torch
    from tensordict import TensorDict

    from .bake import TASK, variant_env
    import os

    os.environ.update(variant_env(variant, init_bent=init_bent))
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    import mjlab.tasks  # noqa: F401
    from mjlab.envs import ManagerBasedRlEnv
    from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
    from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

    cfg = load_env_cfg(TASK, play=True)
    cfg.scene.num_envs = 1
    self._env = ManagerBasedRlEnv(cfg=cfg, device="cpu")
    rl_cfg = load_rl_cfg(TASK)
    envw = RslRlVecEnvWrapper(self._env, clip_actions=rl_cfg.clip_actions)
    runner = (load_runner_cls(TASK) or MjlabOnPolicyRunner)(envw, asdict(rl_cfg), device="cpu")
    runner.load(pt_path, load_cfg={"actor": True}, strict=True, map_location="cpu")
    self._policy = runner.get_inference_policy(device="cpu")
    self._group = (
      self._policy.obs_groups[0] if getattr(self._policy, "obs_groups", None) else "actor"
    )
    self._torch, self._TD = torch, TensorDict
    self.path = pt_path
    self.obs_dim = int(self._env.observation_manager.group_obs_dim["actor"][0])
    self.action_dim = len(self._env.action_manager._terms["joint_pos"]._target_names)

  def __call__(self, obs: np.ndarray) -> np.ndarray:
    t = self._torch.from_numpy(np.asarray(obs, dtype=np.float32).reshape(1, -1))
    with self._torch.no_grad():
      a = self._policy(self._TD({self._group: t}, batch_size=[1]))
    return a.cpu().numpy().reshape(-1)


# --------------------------------------------------------------------------- mux
class ObsSourceMux:
  """Per observation TERM, where its value SHOULD come from.

  ``sources`` is the request (what the operator asked for); ``effective`` (set by
  ``SimCore`` after each ``build_shadow`` call) is what was ACTUALLY used that tick - the two
  differ exactly when a term asked for ``real`` but the real data was missing or older than
  ``max_age_s`` (design item 1's staleness guard: never silently feed the policy a stale
  number, always fall back to sim and say so).  ``policy_sim`` mode ignores this entirely
  (every term is sim); only ``policy_shadow`` reads it, through ``ObsBuilder.build_shadow``.
  """

  SOURCES = ("sim", "real")

  def __init__(self, term_names: list[str], max_age_s: float = 0.1):
    self.sources = {n: "sim" for n in term_names}
    self.effective: dict[str, str] = {n: "sim" for n in term_names}
    self.warnings: list[str] = []
    self.max_age_s = max_age_s

  def set(self, mapping: dict[str, str]) -> None:
    for k, v in mapping.items():
      if k not in self.sources:
        raise KeyError(f"unknown observation term {k!r}; have {list(self.sources)}")
      if v not in self.SOURCES:
        raise ValueError(f"source must be one of {self.SOURCES}, got {v!r}")
      self.sources[k] = v

  def mask(self) -> list[str]:
    """Requested mask ('R'/'S' per term, in term order)."""
    return [("R" if s == "real" else "S") for s in self.sources.values()]

  def effective_mask(self) -> list[str]:
    """Actually-used mask - identical to ``mask()`` outside policy_shadow, since only
    ``build_shadow`` ever sets ``effective`` to anything but the request."""
    return [("R" if s == "real" else "S") for s in self.effective.values()]


# --------------------------------------------------------------------------- glue
def action_to_target(
  action: np.ndarray, default_q: np.ndarray, scale: np.ndarray, clip_lo, clip_hi, clip_actions
) -> tuple[np.ndarray, np.ndarray]:
  """Returns (raw action after the vec-env clamp, joint position target)."""
  raw = np.asarray(action, dtype=np.float64)
  if clip_actions is not None:
    raw = np.clip(raw, -float(clip_actions), float(clip_actions))
  return raw, np.clip(raw * scale + default_q, clip_lo, clip_hi)


def check_compatible(policy_contract: dict, model_contract) -> None:
  """Refuse a policy that was not trained on this model, or whose default pose differs.

  Loading a v4 policy onto a v2 model has already happened once on this project.  The sha
  check makes it impossible; the default-pose check catches the subtler case where the same
  model was baked under different PYG_* toggles, because the default pose IS the action
  offset - a mismatch silently biases every joint target.
  """
  want = policy_contract.get("model_contract_sha")
  if want != model_contract.contract_sha:
    raise PolicyContractMismatch(
      f"policy was baked against model contract {str(want)[:12]} but the loaded model is "
      f"{model_contract.contract_sha[:12]} ({model_contract.variant}). Re-bake the policy "
      f"for this variant, or load the matching model."
    )
  bad = []
  for n, v in policy_contract.get("default_q", {}).items():
    if n in model_contract.raw["default_q"]:
      d = abs(float(v) - float(model_contract.raw["default_q"][n]))
      if d > 1e-4:
        bad.append((n, round(d, 6)))
  if bad:
    raise PolicyContractMismatch(
      f"default pose differs from the policy's by more than 1e-4 rad: {bad}. The default "
      f"pose is the action offset, so every target would be biased."
    )
