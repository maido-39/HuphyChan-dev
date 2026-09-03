"""The simulation thread: plain MuJoCo + numpy, no mjlab, no torch.

Runs the baked model at the training rates (physics 200 Hz, control 50 Hz) and drives the
actuated joints with **the same torque expression the trainer uses**:

    raw = clip(kp * (q_target - q) - kd * qdot,  -effort, +effort)
    tau = tn_clamp(raw, qdot)              # measured T-N curve, speed-dependent ceiling
    qfrc_applied[dof] = tau

written straight into ``qfrc_applied`` on the 12 motor DOFs.  That is the identical operator
to the model's motor-type actuators (gain 1, contract ``gainprm [1,0,0]``), and it is what
``tools/sim2sim/mujoco_ab_loop_drift.py`` validated - so a number read here is comparable to
a number read in training, not merely similar.

Closed-loop (AB) note: the crank target is only ever reached through the PD.  Snapping a
crank's ``qpos`` tears the four ``equality/connect`` closures open and MuJoCo answers with
QACC NaN (documented in ``tools/viewer/mjcf_joint_viewer.py``).  There is no code path here
that writes a crank qpos outside a reset.

Threading contract: this object owns MjData.  Callers never touch it; they push ``Command``
dicts into a queue and read the latest ``Snapshot`` (a plain dict).  Nothing is buffered:
a viewer that falls behind loses frames, it does not grow memory.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Any, Callable

import mujoco
import numpy as np

from .contract import ModelContract

BASE_MODES = ("free", "fixed", "pivot")


def quat_mul(a, b):
  w1, x1, y1, z1 = a
  w2, x2, y2, z2 = b
  return np.array(
    [
      w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
      w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
      w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
      w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ]
  )


def rpy_to_quat(r, p, y):
  cr, sr = math.cos(r / 2), math.sin(r / 2)
  cp, sp = math.cos(p / 2), math.sin(p / 2)
  cy, sy = math.cos(y / 2), math.sin(y / 2)
  return np.array(
    [
      cr * cp * cy + sr * sp * sy,
      sr * cp * cy - cr * sp * sy,
      cr * sp * cy + sr * cp * sy,
      cr * cp * sy - sr * sp * cy,
    ]
  )


def quat_to_rpy(q):
  w, x, y, z = q
  sinr = 2 * (w * x + y * z)
  cosr = 1 - 2 * (x * x + y * y)
  roll = math.atan2(sinr, cosr)
  sinp = 2 * (w * y - z * x)
  pitch = math.copysign(math.pi / 2, sinp) if abs(sinp) >= 1 else math.asin(sinp)
  siny = 2 * (w * z + x * y)
  cosy = 1 - 2 * (y * y + z * z)
  return roll, pitch, math.atan2(siny, cosy)


class AnkleInverse:
  """(ankle pitch, roll) -> (crank A, crank B).  AB build only.

  Primary method ``envelope``: bilinear interpolation of the ``crank_rad`` grid in
  ``ankle_rp_envelope.json`` (17 pitch x 9 roll nodes per leg), then the PER-LEG SIGN MAP the
  bake fitted.  That map is not cosmetic - the grid was solved on
  ``pygmalion_v3_printed_loop`` and the v30 generator re-signed the crank joint axes, so the
  raw grid pair lands the foot 0.36 rad (20.7 deg) away.  With the fitted map (L: A -> -A,
  R: B -> -B) the residual over the probe set is 0.011 rad.

  Fallback method ``linear``: crank = neutral + J^-1 (target - neutral), from the 2x2
  Jacobian the bake measured on this model.  Only used when the grid fit fails; valid near
  the neutral pose and labelled as such in the UI.

  Either way this produces a COMMAND.  The angle displayed as the ankle's actual value is
  always the model's own qpos, so a residual shows up as target-vs-actual, never as a
  wrong readout.
  """

  def __init__(self, contract_raw: dict):
    import json

    meta = contract_raw["ankle_inverse"]
    self.method = meta.get("method", "envelope")
    self.tag = meta.get("envelope_tag")
    self.worst_residual_rad = meta.get("worst_residual_rad")
    env = json.loads(open(meta["source"]).read())
    self.pitch = np.radians(np.asarray(env["grid"]["pitch_deg"], dtype=float))
    self.roll = np.radians(np.asarray(env["grid"]["roll_deg"], dtype=float))
    self.sign_map = meta.get("sign_map") or {}
    from scipy.interpolate import RegularGridInterpolator

    self._interp = {
      s: RegularGridInterpolator(
        (self.pitch, self.roll),
        np.asarray(env["legs"][s]["crank_rad"], dtype=float),
        bounds_error=False,
        fill_value=None,
      )
      for s in ("L", "R")
    }
    tr = contract_raw.get("loop_transmission") or {}
    self._lin = {
      s: dict(
        neutral=np.radians(
          [tr[s]["neutral_deg"]["crank_A"], tr[s]["neutral_deg"]["crank_B"]]
        ),
        origin=np.radians([tr[s]["neutral_deg"]["pitch"], tr[s]["neutral_deg"]["roll"]]),
        J_inv=np.asarray(tr[s]["J_inv"], dtype=float),
      )
      for s in ("L", "R")
      if s in tr and tr[s].get("J_inv")
    }

  def bounds(self) -> tuple[tuple[float, float], tuple[float, float]]:
    return (float(self.pitch[0]), float(self.pitch[-1])), (float(self.roll[0]), float(self.roll[-1]))

  def __call__(self, side: str, pitch: float, roll: float) -> tuple[float, float]:
    p = float(np.clip(pitch, self.pitch[0], self.pitch[-1]))
    r = float(np.clip(roll, self.roll[0], self.roll[-1]))
    if self.method == "linear":
      L = self._lin[side]
      d = np.array([p, r]) - L["origin"]
      # J_inv is in degrees-per-degree, which is dimensionless, so it applies to radians too
      a, b = L["neutral"] + L["J_inv"] @ d
      return float(a), float(b)
    a, b = self._interp[side](np.array([[p, r]]))[0]
    sm = self.sign_map.get(side) or {}
    if sm.get("swap_AB"):
      a, b = b, a
    return float(a) * float(sm.get("sign_A", 1)), float(b) * float(sm.get("sign_B", 1))


class SimCore:
  def __init__(
    self,
    contract: ModelContract,
    mjb: str | None = None,
    realtime: bool = True,
    max_catchup: int = 8,
  ):
    self.c = contract
    self.m = mujoco.MjModel.from_binary_path(str(mjb or contract.mjb_path))
    self.d = mujoco.MjData(self.m)
    self.realtime = realtime
    self.max_catchup = max_catchup

    r = contract.raw
    self.dt = float(self.m.opt.timestep)
    self.decimation = int(r["decimation"])
    self.names: list[str] = list(r["joint_names"])
    self.act_names: list[str] = list(r["action_joint_names"])

    jid = {n: self.m.joint(f"robot/{n}").id for n in self.names}
    self.qadr = {n: int(self.m.jnt_qposadr[jid[n]]) for n in self.names}
    self.dadr = {n: int(self.m.jnt_dofadr[jid[n]]) for n in self.names}
    self.a_q = np.array([self.qadr[n] for n in self.act_names])
    self.a_d = np.array([self.dadr[n] for n in self.act_names])
    self.all_q = np.array([self.qadr[n] for n in self.names])
    self.all_d = np.array([self.dadr[n] for n in self.names])

    self.kp = np.array([r["gains"][n]["kp"] for n in self.act_names])
    self.kd = np.array([r["gains"][n]["kd"] for n in self.act_names])
    self.eff = np.array([r["gains"][n]["effort"] for n in self.act_names])
    fam = [r["joint_family"][n] for n in self.act_names]
    self._tn_w = [np.asarray([p[0] for p in r["tn_curves"][f]]) for f in fam]
    self._tn_t = [np.asarray([p[1] for p in r["tn_curves"][f]]) for f in fam]
    self._tn_peak = np.array([t[0] for t in self._tn_t])

    self.default_q = np.array([r["default_q"][n] for n in self.act_names])
    self.clip_lo = np.array([contract.clip(n)[0] for n in self.act_names])
    self.clip_hi = np.array([contract.clip(n)[1] for n in self.act_names])

    self.free_adr = int(self.m.jnt_qposadr[0])
    a = r["anchor_eq_ids"]
    self.eq_weld = int(a["weld"])
    self.eq_pivot = int(a["connect"])
    self.mocap_id = int(a["mocap_id"])
    self.base_bid = int(a["base_body_id"])
    self.floor_gid = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_GEOM, r["floor_geom"])
    self._floor_con = (
      int(self.m.geom_contype[self.floor_gid]),
      int(self.m.geom_conaffinity[self.floor_gid]),
    )

    s = r["sensors"]
    self._sensor = {
      k: (v["adr"], v["dim"])
      for k, v in s.items()
      if k.split("/")[-1] in ("imu_ang_vel", "imu_lin_vel", "imu_lin_acc", "imu_upvector")
    }

    self.ankle_inverse: AnkleInverse | None = None
    if r.get("ankle_inverse"):
      self.ankle_inverse = AnkleInverse(r)

    # ------------------------------------------------------------------ state
    self.target = self.default_q.copy()
    self.base_mode = "free"
    self.base_pos = np.array([0.0, 0.0, float(r["spawn_base_z"])])
    self.base_quat = np.array([1.0, 0.0, 0.0, 0.0])
    self.pivot_offset = np.zeros(3)
    self.ground = True
    self.mode = "idle"

    self._cmds: deque = deque(maxlen=512)
    self._lock = threading.Lock()
    self._snap: dict[str, Any] = {}
    self._thread: threading.Thread | None = None
    self._running = False
    self._stats = dict(phys_steps=0, ctrl_ticks=0, drops=0, phys_hz=0.0, ctrl_hz=0.0, t_wall=0.0)
    self._hooks: list[Callable[[dict], None]] = []

    self.reset("knees_bent")
    self._publish()

  # ------------------------------------------------------------------ public API
  def submit(self, cmd: dict) -> None:
    with self._lock:
      self._cmds.append(cmd)

  def snapshot(self) -> dict:
    with self._lock:
      return self._snap

  def add_hook(self, fn: Callable[[dict], None]) -> None:
    """Called with each new snapshot on the sim thread.  Must be fast and must not block."""
    self._hooks.append(fn)

  def start(self) -> None:
    if self._running:
      return
    self._running = True
    self._thread = threading.Thread(target=self._loop, name="pygviewer-sim", daemon=True)
    self._thread.start()

  def stop(self) -> None:
    self._running = False
    if self._thread is not None:
      self._thread.join(timeout=2.0)
      self._thread = None

  # ------------------------------------------------------------------ mechanics
  def reset(self, keyframe: str = "knees_bent") -> None:
    kf = self.c.raw["keyframes"][keyframe]
    mujoco.mj_resetData(self.m, self.d)
    if kf.get("qpos"):
      self.d.qpos[:] = np.asarray(kf["qpos"])
    else:
      self.d.qpos[:] = self.m.qpos0
      for n, q in kf["joint_pos"].items():
        self.d.qpos[self.qadr[n]] = float(q)
    # A reset is a reset: the base goes back to the keyframe's own pose in every mode, and
    # the anchor follows it.  (Leaving the anchor where it was made "reset to home" drop the
    # robot from whatever height the previous mode had parked it at.)
    self.base_pos = np.array([0.0, 0.0, float(kf["base_z"])])
    self.base_quat = np.array([1.0, 0.0, 0.0, 0.0])
    self.d.qpos[self.free_adr : self.free_adr + 3] = self.base_pos
    self.d.qpos[self.free_adr + 3 : self.free_adr + 7] = self.base_quat
    self.d.qvel[:] = 0.0
    self.d.qfrc_applied[:] = 0.0
    self.target = np.array([self.d.qpos[i] for i in self.a_q])
    self._apply_base_mode(snap=True)
    self._apply_ground()
    mujoco.mj_forward(self.m, self.d)

  def _apply_ground(self) -> None:
    ct, ca = self._floor_con if self.ground else (0, 0)
    self.m.geom_contype[self.floor_gid] = ct
    self.m.geom_conaffinity[self.floor_gid] = ca

  def _apply_base_mode(self, snap: bool = False) -> None:
    """Activate the right equality and, when asked, put the base exactly where it belongs.

    ``snap`` is used on a mode change: without it the constraint has to drag the base into
    place, which is a violent kick for a 23 kg robot standing on a hard floor.
    """
    self.d.mocap_pos[self.mocap_id] = self.base_pos
    self.d.mocap_quat[self.mocap_id] = self.base_quat
    self.m.eq_data[self.eq_pivot, 0:3] = self.pivot_offset
    self.d.eq_active[self.eq_weld] = 1 if self.base_mode == "fixed" else 0
    self.d.eq_active[self.eq_pivot] = 1 if self.base_mode == "pivot" else 0
    if not snap or self.base_mode == "free":
      return
    if self.base_mode == "fixed":
      self.d.qpos[self.free_adr : self.free_adr + 3] = self.base_pos
      self.d.qpos[self.free_adr + 3 : self.free_adr + 7] = self.base_quat
    else:  # pivot: keep the CURRENT orientation, move the body so the pivot point lands
      q = self.d.qpos[self.free_adr + 3 : self.free_adr + 7].copy()
      R = np.zeros(9)
      mujoco.mju_quat2Mat(R, q)
      self.d.qpos[self.free_adr : self.free_adr + 3] = self.base_pos - R.reshape(3, 3) @ self.pivot_offset
    self.d.qvel[0:6] = 0.0
    mujoco.mj_forward(self.m, self.d)

  def set_base(
    self,
    mode: str | None = None,
    pos=None,
    quat=None,
    rpy=None,
    height: float | None = None,
    pivot_offset=None,
    ground: bool | None = None,
  ) -> None:
    changed_mode = mode is not None and mode != self.base_mode
    if mode is not None:
      if mode not in BASE_MODES:
        raise ValueError(f"base mode must be one of {BASE_MODES}, got {mode!r}")
      self.base_mode = mode
    if pos is not None:
      self.base_pos = np.asarray(pos, dtype=float).copy()
    if height is not None:
      self.base_pos[2] = float(height)
    if quat is not None:
      q = np.asarray(quat, dtype=float)
      self.base_quat = q / np.linalg.norm(q)
    if rpy is not None:
      self.base_quat = rpy_to_quat(*[float(v) for v in rpy])
    if pivot_offset is not None:
      self.pivot_offset = np.asarray(pivot_offset, dtype=float).copy()
    if ground is not None:
      self.ground = bool(ground)
      self._apply_ground()
    self._apply_base_mode(snap=changed_mode or pos is not None or quat is not None or rpy is not None or height is not None)

  def set_target(self, values: dict[str, float]) -> None:
    for n, q in values.items():
      if n not in self.act_names:
        raise KeyError(f"{n!r} is not an actuated joint of {self.c.variant}")
      i = self.act_names.index(n)
      self.target[i] = float(np.clip(q, self.clip_lo[i], self.clip_hi[i]))

  def set_ankle(self, side: str, pitch: float, roll: float) -> dict:
    """AB only: command the ankle in FOOT space, through the crank inverse grid."""
    if self.ankle_inverse is None:
      raise RuntimeError(f"{self.c.variant} has no crank inverse (RP drives the ankle directly)")
    a, b = self.ankle_inverse(side, pitch, roll)
    self.set_target({f"{side}_crank_A_joint": a, f"{side}_crank_B_joint": b})
    return {"crank_A": a, "crank_B": b}

  # ------------------------------------------------------------------ inner loop
  def _tn_clamp(self, tau: np.ndarray, omega: np.ndarray) -> np.ndarray:
    for i in range(tau.shape[0]):
      w = omega[i]
      if w >= 0:
        hi = float(np.interp(w, self._tn_w[i], self._tn_t[i]))
        lo = -self._tn_peak[i]
      else:
        hi = self._tn_peak[i]
        lo = -float(np.interp(-w, self._tn_w[i], self._tn_t[i]))
      if tau[i] > hi:
        tau[i] = hi
      elif tau[i] < lo:
        tau[i] = lo
    return tau

  def _substep(self) -> None:
    q = self.d.qpos[self.a_q]
    qv = self.d.qvel[self.a_d]
    raw = np.clip(self.kp * (self.target - q) - self.kd * qv, -self.eff, self.eff)
    tau = self._tn_clamp(raw, qv)
    self.d.qfrc_applied[:] = 0.0
    self.d.qfrc_applied[self.a_d] = tau
    self._tau = tau
    mujoco.mj_step(self.m, self.d)
    if self.base_mode != "free":
      # keep the anchor exactly where the user put it (mocap bodies never integrate, but a
      # /base command may have landed mid-substep)
      self.d.mocap_pos[self.mocap_id] = self.base_pos
      self.d.mocap_quat[self.mocap_id] = self.base_quat

  def _drain(self) -> None:
    with self._lock:
      cmds = list(self._cmds)
      self._cmds.clear()
    for cmd in cmds:
      try:
        self._apply_cmd(cmd)
      except Exception as exc:  # a bad command must never kill the sim thread
        self._last_error = f"{type(exc).__name__}: {exc}"

  def _apply_cmd(self, cmd: dict) -> None:
    op = cmd.get("op")
    if op == "target":
      self.set_target(cmd["values"])
    elif op == "ankle":
      self.set_ankle(cmd["side"], float(cmd["pitch"]), float(cmd["roll"]))
    elif op == "base":
      self.set_base(**{k: v for k, v in cmd.items() if k != "op"})
    elif op == "reset":
      self.reset(cmd.get("keyframe", "knees_bent"))
    elif op == "mode":
      self.mode = cmd["value"]
    else:
      raise ValueError(f"unknown command op {op!r}")

  def _loop(self) -> None:
    t0 = time.perf_counter()
    step_i = 0
    last_rate = t0
    ps0 = cs0 = 0
    while self._running:
      if self.realtime:
        now = time.perf_counter()
        due = int((now - t0) / self.dt) - step_i
        if due <= 0:
          time.sleep(self.dt / 4)
          continue
        if due > self.max_catchup:
          self._stats["drops"] += due - self.max_catchup
          step_i += due - self.max_catchup
          due = self.max_catchup
      else:
        due = self.decimation
      for _ in range(due):
        if step_i % self.decimation == 0:
          self._drain()
          self._stats["ctrl_ticks"] += 1
        self._substep()
        step_i += 1
        self._stats["phys_steps"] += 1
      self._publish()
      now = time.perf_counter()
      if now - last_rate >= 0.5:
        self._stats["phys_hz"] = (self._stats["phys_steps"] - ps0) / (now - last_rate)
        self._stats["ctrl_hz"] = (self._stats["ctrl_ticks"] - cs0) / (now - last_rate)
        ps0, cs0, last_rate = self._stats["phys_steps"], self._stats["ctrl_ticks"], now
      self._stats["t_wall"] = now - t0

  # ------------------------------------------------------------------ snapshot
  def _publish(self) -> None:
    d, m = self.d, self.m
    q_all = d.qpos[self.all_q]
    qd_all = d.qvel[self.all_d]
    base_pos = d.qpos[self.free_adr : self.free_adr + 3]
    base_quat = d.qpos[self.free_adr + 3 : self.free_adr + 7]
    sens = {}
    for k, (adr, dim) in self._sensor.items():
      sens[k.split("/")[-1]] = [float(x) for x in d.sensordata[adr : adr + dim]]
    snap = dict(
      t=float(d.time),
      wall=time.time(),
      variant=self.c.variant,
      mode=self.mode,
      joint_names=self.names,
      q=[float(x) for x in q_all],
      qd=[float(x) for x in qd_all],
      act_names=self.act_names,
      tau=[float(x) for x in getattr(self, "_tau", np.zeros(len(self.act_names)))],
      target=[float(x) for x in self.target],
      base=dict(
        mode=self.base_mode,
        pos=[float(x) for x in base_pos],
        quat=[float(x) for x in base_quat],
        rpy=[float(v) for v in quat_to_rpy(base_quat)],
        cmd_pos=[float(x) for x in self.base_pos],
        cmd_quat=[float(x) for x in self.base_quat],
        pivot_offset=[float(x) for x in self.pivot_offset],
        ground=self.ground,
      ),
      imu=sens,
      rates=dict(
        phys_hz=round(self._stats["phys_hz"], 1),
        ctrl_hz=round(self._stats["ctrl_hz"], 1),
        drops=int(self._stats["drops"]),
        phys_steps=int(self._stats["phys_steps"]),
      ),
      warnings=self._warnings(q_all),
    )
    if self.c.is_loop:
      snap["ankle_derived"] = {
        s: dict(
          pitch=float(d.qpos[self.qadr[f"{s}_ankle_pitch_joint"]]),
          roll=float(d.qpos[self.qadr[f"{s}_ankle_roll_joint"]]),
        )
        for s in ("L", "R")
        if f"{s}_ankle_pitch_joint" in self.qadr
      }
      snap["closure_mm"] = self.closure_mm()
    with self._lock:
      self._snap = snap
    for h in self._hooks:
      try:
        h(snap)
      except Exception:
        pass

  def _warnings(self, q_all) -> list[str]:
    w = []
    if not np.all(np.isfinite(q_all)):
      w.append("NON-FINITE qpos - the model has blown up; reset")
    err = getattr(self, "_last_error", None)
    if err:
      w.append(f"last command rejected: {err}")
    return w

  def closure_mm(self) -> float:
    worst = 0.0
    for s in "LR":
      for t in "AB":
        i1 = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_SITE, f"robot/{s}_rod_{t}_end")
        i2 = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_SITE, f"robot/{s}_ball_{t}")
        if i1 < 0 or i2 < 0:
          continue
        worst = max(worst, float(np.linalg.norm(self.d.site_xpos[i1] - self.d.site_xpos[i2])) * 1e3)
    return round(worst * 1.0, 6)

  # ------------------------------------------------------------------ headless
  def run_blocking(self, seconds: float) -> dict:
    """Step for ``seconds`` of wall clock in this thread (tests, --headless)."""
    self._running = True
    t0 = time.perf_counter()
    try:
      self._loop_until(lambda: time.perf_counter() - t0 >= seconds)
    finally:
      self._running = False
    return self.snapshot()

  def _loop_until(self, done) -> None:
    t0 = time.perf_counter()
    step_i = 0
    while self._running and not done():
      if self.realtime:
        now = time.perf_counter()
        due = int((now - t0) / self.dt) - step_i
        if due <= 0:
          time.sleep(self.dt / 4)
          continue
        if due > self.max_catchup:
          self._stats["drops"] += due - self.max_catchup
          step_i += due - self.max_catchup
          due = self.max_catchup
      else:
        due = self.decimation
      for _ in range(due):
        if step_i % self.decimation == 0:
          self._drain()
          self._stats["ctrl_ticks"] += 1
        self._substep()
        step_i += 1
        self._stats["phys_steps"] += 1
      self._publish()
      el = time.perf_counter() - t0
      self._stats["phys_hz"] = self._stats["phys_steps"] / max(el, 1e-9)
      self._stats["ctrl_hz"] = self._stats["ctrl_ticks"] / max(el, 1e-9)
      self._stats["t_wall"] = el

  def step_n(self, n: int) -> None:
    """Step ``n`` physics substeps as fast as possible (tests only, no pacing)."""
    for k in range(n):
      if k % self.decimation == 0:
        self._drain()
      self._substep()
    self._publish()
