"""Invariant-violation gate on a load-measurement npz (reward-hack / degenerate-
gait detector).  Red-team item #2, docs/research_raw/2026-08-28_redteam_load_study.md
(§2, §7 row 2).

A load number is only physically real if the rollout it came from obeys a handful
of contact/actuator invariants.  This is a STANDING, AUTOMATED check meant to run
as the final stage of every load-measurement pass (measure_v2s1.sh stage e) so a
mis-stated load (contact-detection bug, missing foot channel, un-clamped motor,
or a policy balancing on a toe edge to game the reward) is caught before the
numbers are trusted.

Four invariants, computed on a measure_loads / measure_full npz:

  1. VERTICAL IMPULSE BALANCE  (hard)
       window-mean of total vertical contact GRF must equal body weight m*g
       (the robot neither sinks nor launches on average -- impulse-momentum
       theorem over the measured window).  Generalises the 200 Hz probe's
       "mean support 1.000 BW" identity.  FLAG if |mean(sum Fz)/(m*g) - 1| > tol.

  2. CoP WITHIN THE SUPPORT POLYGON  (soft, + edge-pinning warning)
       centre of pressure under each stance foot must lie within that foot's
       contact geometry; a CoP outside the foot, or pinned at the toe/heel edge
       while loaded, means the contact model is unphysical or the foot is being
       used as a pivot that mis-states load.  The npz stores NO per-contact
       positions/forces and NO qvel, only aggregate per-foot GRFc + qpos_full,
       so the contact GEOMETRY is recomputed with a light static mj_forward on a
       subsample (positions exact; the force weighting is quasi-static -- stated
       in the report).  The dynamic per-foot load used to gate "stance" is the
       real GRFc from the npz.

  3. FRICTION CONE  (hard)
       horizontal contact GRF <= mu * vertical GRF, per foot (mu from the model's
       foot-terrain contact).  A sustained breach means the policy relies on
       un-physical grip and mis-states ankle shear.  FLAG if the loaded-stance
       breach fraction exceeds a threshold.

  4. TORQUE vs T-N ENVELOPE  (hard)
       measured joint/crank torque at its measured speed must sit inside the
       RobStride T-N curve (we clamp in training; a measurement with the clamp
       off or a mapping bug would breach).  Reuses motor_specs.py.  AB-aware:
       sizes the two RS03 CRANKS (tau_*_crank_A/B) for the loop ankle, direct
       ankle_pitch/roll for serial/RP -- same detection as actuator_eval.

Prints a PASS/FLAG table with the numeric margin on each invariant and exits
non-zero if any HARD invariant is violated.  CPU-only npz post-processing.

Usage:
    invariant_gate.py NPZ [--model MJB] [--mass KG] [--mu MU]
                          [--subsample N] [--json OUT] [-v]
      NPZ         analysis/out/<tag>.npz from measure_loads/measure_full
      --model     compiled model (default: sibling <tag>_model.mjb); gives mass,
                  gravity, foot geometry and friction
      --mass/--mu overrides if the .mjb is unavailable
      --subsample frames for the CoP contact recompute (default 2000)
      --json      also write the machine-readable verdict here
    exit 0 = all hard invariants pass, 1 = a hard invariant flagged, 2 = error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# motor_specs lives in the mjlab analysis dir (same import style as actuator_eval)
_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]  # tools/robot_model/loop_tests -> repo
_ANALYSIS = REPO / "mujoco-sim" / "mjlab" / "analysis"
sys.path.insert(0, str(_ANALYSIS))
import motor_specs as ms  # noqa: E402

RAD2RPM = 60.0 / (2.0 * np.pi)

# ---- tolerances (documented; tune here, one place) -------------------------
IMPULSE_TOL = 0.05  # inv1 HARD: |mean support / BW - 1| flag threshold
IMPULSE_INFO = 0.02  # inv1 INFO: tighter band worth noting
FRICTION_MARGIN = 0.05  # inv3: allow mu*(1+margin) numerical slack before a breach
FRICTION_BREACH_FRAC = 0.01  # inv3 HARD: loaded-stance breach fraction that flags
TN_BREACH_FRAC = 0.01  # inv4 HARD: T-N out-of-envelope fraction that flags (per motor)
COP_OUTSIDE_FRAC = 0.05  # inv2 sanity: CoP-outside-polygon fraction worth noting
SPAN_COLLAPSE_FRAC = (
  0.35  # inv2: fore-aft contact span < this * foot length = edge-pivot
)
TOE_PIVOT_FRAC = 0.25  # inv2 WARN: loaded frames pivoting on the TOE edge (suspicious)
STANCE_BW_FRAC = 0.10  # a foot is "loaded stance" when its GRFc_z > this * BW
COP_INSIDE_TOL = 0.010  # m: slack on the foot footprint for the inside test

# leg joints that carry a real motor, per model family.  AB (loop) ankle DoFs are
# driven through the two RS03 cranks -- their direct-ankle tau is ~0, so size the
# cranks (matches actuator_eval._is_ab / AB_JOINTS).
SERIAL_JOINTS = [
  "hip_pitch",
  "hip_roll",
  "hip_yaw",
  "knee",
  "ankle_pitch",
  "ankle_roll",
]
AB_JOINTS = ["hip_pitch", "hip_roll", "hip_yaw", "knee", "crank_A", "crank_B"]
JMOTOR = {**ms.JOINT_MOTOR, "crank_A": "RS03", "crank_B": "RS03"}


# ============================================================ helpers
def _is_ab(d) -> bool:
  return "tau_L_crank_A_joint" in getattr(d, "files", d)


def _load_model(mjb: Path):
  try:
    import mujoco
  except ImportError:
    return None, None
  if not mjb.exists():
    return None, None
  m = mujoco.MjModel.from_binary_path(str(mjb))
  return m, mujoco


def _foot_bodies(m, mujoco):
  out = {}
  for s in ("L", "R"):
    bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"robot/{s}_foot_link")
    if bid >= 0:
      out[s] = bid
  return out


def _foot_footprint(m, mujoco, bid):
  """Union AABB (x,y) of the foot body's COLLIDABLE geoms in body-local frame.
  Returns (xmin, xmax, ymin, ymax) or None."""
  xs, ys = [], []
  for g in range(m.ngeom):
    if m.geom_bodyid[g] != bid:
      continue
    if m.geom_contype[g] == 0 and m.geom_conaffinity[g] == 0:
      continue  # visual-only geom
    p = m.geom_pos[g]
    sz = m.geom_size[g]
    # box (type 6) uses half-sizes on x,y; mesh/others: fall back to size[:2]
    hx = float(sz[0]) if sz[0] > 0 else 0.0
    hy = float(sz[1]) if sz[1] > 0 else 0.0
    xs += [float(p[0]) - hx, float(p[0]) + hx]
    ys += [float(p[1]) - hy, float(p[1]) + hy]
  if not xs:
    return None
  return (min(xs), max(xs), min(ys), max(ys))


# ============================================================ invariant 1
def inv_vertical_impulse(d, bw):
  """Window-mean of total vertical contact GRF vs body weight."""

  # prefer contact-only GRFc (cfrc_ext is contaminated by loop constraint forces
  # in the AB model); fall back to GRF for serial models lacking GRFc.
  def foot_fz(s):
    for k in (f"GRFc_{s}_foot_link_z", f"GRF_{s}_foot_link_z"):
      if k in d.files:
        return d[k], k.split("_")[0]
    return None, None

  zL, srcL = foot_fz("L")
  zR, srcR = foot_fz("R")
  if zL is None or zR is None:
    return dict(
      name="vertical_impulse", ok=None, hard=True, note="no foot GRF columns in npz"
    )
  src = srcL
  tot = np.asarray(zL) + np.asarray(zR)
  mean_support = float(tot.mean())
  ratio = mean_support / bw
  dev = abs(ratio - 1.0)
  ok = dev <= IMPULSE_TOL
  # per-command-block spread (worst block) if cmd columns are present -> catches
  # a single accelerating/sinking block hidden inside a balanced window.
  worst = None
  if all(c in d.files for c in ("cmd_vx", "cmd_vy", "cmd_wz")):
    key = np.stack([d["cmd_vx"], d["cmd_vy"], d["cmd_wz"]], axis=1)
    # block boundaries = where the command changes
    chg = np.any(np.diff(key, axis=0) != 0.0, axis=1)
    bounds = [0, *(np.where(chg)[0] + 1).tolist(), len(tot)]
    devs = []
    for a, b in zip(bounds[:-1], bounds[1:]):
      if b - a >= 50:  # ignore tiny transient blocks
        devs.append(abs(tot[a:b].mean() / bw - 1.0))
    if devs:
      worst = float(max(devs))
  # secondary (info): net horizontal GRF impulse ~ 0 at steady state
  ap = None
  kx = [f"GRFc_{s}_foot_link_x" for s in "LR"]
  if all(k in d.files for k in kx):
    totx = d[kx[0]] + d[kx[1]]
    ap = float(totx.mean() / bw)  # mean net fore/lateral force / BW
  return dict(
    name="vertical_impulse",
    ok=ok,
    hard=True,
    src=src,
    mean_support_N=mean_support,
    bw_N=bw,
    ratio=ratio,
    dev=dev,
    worst_block_dev=worst,
    ap_mean_over_bw=ap,
    tol=IMPULSE_TOL,
    info_band=IMPULSE_INFO,
  )


# ============================================================ invariant 3
def inv_friction_cone(d, mu, bw):
  """Per-foot horizontal GRF <= mu * vertical GRF over loaded-stance samples."""

  def foot_xyz(s):
    pre = "GRFc" if f"GRFc_{s}_foot_link_z" in d.files else "GRF"
    try:
      return (
        d[f"{pre}_{s}_foot_link_x"],
        d[f"{pre}_{s}_foot_link_y"],
        d[f"{pre}_{s}_foot_link_z"],
        pre,
      )
    except KeyError:
      return None

  per = {}
  worst_frac = 0.0
  stance_thr = STANCE_BW_FRAC * bw
  lim = mu * (1.0 + FRICTION_MARGIN)
  src = None
  for s in ("L", "R"):
    got = foot_xyz(s)
    if got is None:
      continue
    fx, fy, fz, src = got
    fx, fy, fz = np.asarray(fx), np.asarray(fy), np.asarray(fz)
    stance = fz > stance_thr
    n = int(stance.sum())
    if n == 0:
      per[s] = dict(n_stance=0, breach_frac=0.0, ratio_p99=0.0, ratio_max=0.0)
      continue
    horiz = np.hypot(fx[stance], fy[stance])
    ratio = horiz / np.clip(fz[stance], 1e-6, None)  # effective friction demand
    breach = ratio > lim
    bf = float(breach.mean())
    per[s] = dict(
      n_stance=n,
      breach_frac=bf,
      ratio_p99=float(np.percentile(ratio, 99)),
      ratio_max=float(ratio.max()),
    )
    worst_frac = max(worst_frac, bf)
  ok = worst_frac <= FRICTION_BREACH_FRAC
  return dict(
    name="friction_cone",
    ok=ok,
    hard=True,
    mu=mu,
    src=src,
    limit_with_margin=lim,
    worst_breach_frac=worst_frac,
    per_foot=per,
    thr=FRICTION_BREACH_FRAC,
  )


# ============================================================ invariant 4
def inv_tn_envelope(d):
  """|tau| at |speed| inside the RobStride T-N envelope, per leg motor.
  RAW torque (the training clamp acts on the sim actuator torque, not the
  sim->real x1.15 sizing uplift), AB-aware (cranks vs direct ankle)."""
  joints = AB_JOINTS if _is_ab(d) else SERIAL_JOINTS
  rows = []
  worst_frac = 0.0
  for j in joints:
    mid = JMOTOR.get(j)
    if mid is None:
      continue
    try:
      tau = np.concatenate([d[f"tau_{s}_{j}_joint"] for s in "LR"])
      omg = np.concatenate([d[f"omega_{s}_{j}_joint"] for s in "LR"])
    except KeyError:
      continue
    atau = np.abs(tau)
    rpm = np.abs(omg) * RAD2RPM
    env = ms.tn_torque_limit(mid, rpm)  # max envelope torque at |speed|
    out = atau > env
    frac = float(out.mean())
    # by how much the worst breach overshoots the envelope
    over = atau - env
    over_max = float(over.max())
    rows.append(
      dict(
        joint=j,
        motor=mid,
        peak_Nm=float(atau.max()),
        spd_p99_rpm=float(np.percentile(rpm, 99)),
        out_frac=frac,
        over_max_Nm=over_max,
        rated=ms.MOTORS[mid]["rated"],
        peak=ms.MOTORS[mid]["peak"],
      )
    )
    worst_frac = max(worst_frac, frac)
  ok = worst_frac <= TN_BREACH_FRAC
  return dict(
    name="tn_envelope",
    ok=ok,
    hard=True,
    worst_out_frac=worst_frac,
    rows=rows,
    thr=TN_BREACH_FRAC,
    is_ab=_is_ab(d),
  )


# ============================================================ invariant 2
def inv_cop_polygon(d, m, mujoco, bw, subsample):
  """CoP inside the per-foot support polygon + toe/heel edge-pinning warning.

  Recomputes contact GEOMETRY from qpos_full with a static mj_forward on a
  subsample (contact positions are exact for the pose; the normal-force
  weighting is quasi-static because the npz stores no per-contact force or
  qvel).  'Loaded stance' is decided from the real GRFc_z in the npz."""
  if m is None or mujoco is None:
    return dict(
      name="cop_polygon",
      ok=None,
      hard=False,
      note="no compiled model (.mjb) -> cannot recompute contacts",
    )
  if "qpos_full" not in d.files:
    return dict(
      name="cop_polygon",
      ok=None,
      hard=False,
      note="npz lacks qpos_full -> cannot recompute contacts",
    )
  qpos_full = d["qpos_full"]
  N = qpos_full.shape[0]
  feet = _foot_bodies(m, mujoco)
  if not feet:
    return dict(name="cop_polygon", ok=None, hard=False, note="no foot bodies")
  footprint = {s: _foot_footprint(m, mujoco, bid) for s, bid in feet.items()}

  # real per-foot vertical load from the npz -> which frames are loaded stance
  def gz(s):
    for k in (f"GRFc_{s}_foot_link_z", f"GRF_{s}_foot_link_z"):
      if k in d.files:
        return np.asarray(d[k])
    return np.zeros(N)

  load = {s: gz(s) for s in feet}
  stance_thr = STANCE_BW_FRAC * bw

  # subsample: uniform coverage + always include the highest-GRF frames (worst
  # case), so edge-pinning at peak load is never missed.
  idx = set(np.linspace(0, N - 1, min(subsample, N)).astype(int).tolist())
  tot = sum(load.values())
  idx |= set(np.argsort(tot)[-min(200, N) :].tolist())
  idx = sorted(idx)

  md = mujoco.MjData(m)
  mu_samples = []
  stats = {
    s: dict(
      n=0, outside=0, collapse=0, toe=0, heel=0, no_contact=0, norm_x=[], span_frac=[]
    )
    for s in feet
  }
  for i in idx:
    md.qpos[:] = qpos_full[i]
    mujoco.mj_forward(m, md)
    f6 = np.zeros(6)
    for s, bid in feet.items():
      if load[s][i] <= stance_thr:
        continue
      stats[s]["n"] += 1
      pts, w = [], []
      for ci in range(md.ncon):
        c = md.contact[ci]
        b1 = m.geom_bodyid[c.geom1]
        b2 = m.geom_bodyid[c.geom2]
        if bid not in (b1, b2):
          continue
        other = b2 if b1 == bid else b1
        if other == bid:  # self contact -> skip
          continue
        mujoco.mj_contactForce(m, md, ci, f6)
        fn = float(f6[0])  # normal force magnitude
        if fn <= 0:
          continue
        mu_samples.append(float(c.friction[0]))
        pts.append(np.array(c.pos))
        w.append(fn)
      if not pts:
        stats[s]["no_contact"] += 1
        continue
      P = np.array(pts)
      w = np.array(w)
      # quasi-static force-weighted CoP (positions exact; weights from a
      # static solve since the npz stores no per-contact force/qvel).
      cop_w = (P * w[:, None]).sum(0) / w.sum()
      R = md.xmat[bid].reshape(3, 3)
      p0 = md.xpos[bid]
      cop_b = R.T @ (cop_w - p0)  # CoP in foot-local frame
      Pb = (R.T @ (P - p0).T).T  # contact points, foot-local
      fp = footprint[s]
      if fp is None:
        continue
      xmin, xmax, ymin, ymax = fp
      # (a) sanity: CoP inside the foot footprint (x,y). Near-tautological
      #     for a convex foot -- catches a genuinely misattributed contact.
      inside = (
        xmin - COP_INSIDE_TOL <= cop_b[0] <= xmax + COP_INSIDE_TOL
        and ymin - COP_INSIDE_TOL <= cop_b[1] <= ymax + COP_INSIDE_TOL
      )
      if not inside:
        stats[s]["outside"] += 1
      # (b) foot-flat / edge-pivot: the FORE-AFT contact span (exact geometry,
      #     force-independent). A collapsed span = only the heel edge OR only
      #     the toe edge touches -> the foot is pivoting on an edge and the
      #     ankle must hold a large moment. Lateral (y) is ignored: the box
      #     collision geom only ever contacts at its y-corners, so a y-based
      #     edge test is a geometry artifact, not a real signal.
      xc = 0.5 * (xmin + xmax)
      sx = max(0.5 * (xmax - xmin), 1e-6)
      nx = (cop_b[0] - xc) / sx  # normalised fore-aft [-1,1]
      stats[s]["norm_x"].append(nx)
      span_frac = float(np.ptp(Pb[:, 0])) / (xmax - xmin)
      stats[s]["span_frac"].append(span_frac)
      if span_frac < SPAN_COLLAPSE_FRAC:  # collapsed to one edge
        stats[s]["collapse"] += 1
        # heel (patch centre toward xmin) vs toe (toward xmax)
        if float(np.median(Pb[:, 0])) > xc:
          stats[s]["toe"] += 1
        else:
          stats[s]["heel"] += 1

  mu_used = float(np.median(mu_samples)) if mu_samples else None
  per = {}
  worst_out = 0.0
  worst_toe = 0.0
  for s, st in stats.items():
    n = st["n"]
    if n == 0:
      per[s] = dict(n_stance=0)
      continue
    out_frac = st["outside"] / n
    toe_frac = st["toe"] / n
    per[s] = dict(
      n_stance=n,
      outside_frac=out_frac,
      edge_pivot_frac=st["collapse"] / n,  # heel-only OR toe-only
      toe_pivot_frac=toe_frac,  # the suspicious one
      heel_pivot_frac=st["heel"] / n,  # heel-strike, normal
      no_contact_frac=st["no_contact"] / n,
      cop_normx_median=float(np.median(st["norm_x"])) if st["norm_x"] else None,
      span_frac_median=float(np.median(st["span_frac"])) if st["span_frac"] else None,
      footprint_len_x_m=(footprint[s][1] - footprint[s][0]) if footprint[s] else None,
    )
    worst_out = max(worst_out, out_frac)
    worst_toe = max(worst_toe, toe_frac)
  # SOFT invariant: a true dynamic force-weighted CoP is not reconstructable from
  # stored npz columns (no per-contact force/qvel), so this proxy never drives the
  # exit code. It reports the CoP-inside sanity + the fore-aft foot-flatness that
  # implements "no toe-only-with-huge-moment".
  return dict(
    name="cop_polygon",
    ok=(worst_out <= COP_OUTSIDE_FRAC),
    hard=False,
    quasi_static=True,
    mu_from_contacts=mu_used,
    worst_outside_frac=worst_out,
    worst_toe_pivot_frac=worst_toe,
    toe_warn=worst_toe > TOE_PIVOT_FRAC,
    n_frames=len(idx),
    per_foot=per,
    thr=COP_OUTSIDE_FRAC,
  )


# ============================================================ report
def _fmt_pct(x):
  return "n/a" if x is None else f"{100 * x:.2f}%"


def run(npz_path: Path, mjb: Path | None, mass, mu, subsample, jsonout, verbose):
  d = np.load(npz_path, allow_pickle=True)
  ab = _is_ab(d)
  mjb = mjb or npz_path.with_name(npz_path.stem + "_model.mjb")
  m, mujoco = _load_model(mjb)
  g = 9.81
  if m is not None:
    g = float(abs(m.opt.gravity[2]))
    model_mass = float(m.body_mass.sum())
  else:
    model_mass = None
  if mass is None:
    mass = model_mass
  if mass is None:
    print("!! no mass: pass --mass or provide the compiled .mjb", file=sys.stderr)
    return 2
  bw = mass * g

  # friction: explicit override > from-contacts (filled by inv2) > model geoms
  inv2 = inv_cop_polygon(d, m, mujoco, bw, subsample)
  mu_contacts = inv2.get("mu_from_contacts")
  if mu is None:
    mu = mu_contacts
  if mu is None and m is not None:
    # MuJoCo combines pair friction by elementwise max; take max over the foot
    # collision geoms and the world/terrain geom.
    foot_mu, world_mu = [], []
    for g_ in range(m.ngeom):
      if m.geom_contype[g_] == 0 and m.geom_conaffinity[g_] == 0:
        continue
      bid = m.geom_bodyid[g_]
      nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, bid) or ""
      if "foot" in nm.lower():
        foot_mu.append(float(m.geom_friction[g_][0]))
      elif bid == 0:
        world_mu.append(float(m.geom_friction[g_][0]))
    if foot_mu and world_mu:
      mu = max(max(foot_mu), max(world_mu))
  if mu is None:
    mu = 1.0  # documented project default

  inv1 = inv_vertical_impulse(d, bw)
  inv3 = inv_friction_cone(d, mu, bw)
  inv4 = inv_tn_envelope(d)
  results = [inv1, inv2, inv3, inv4]

  # ---- table -------------------------------------------------------------
  print("=" * 78)
  print(f"INVARIANT GATE  {npz_path.name}")
  print(
    f"  model={'AB loop (RS03 cranks)' if ab else 'serial/RP'}  "
    f"mass={mass:.3f} kg  g={g:.2f}  BW={bw:.1f} N  mu={mu:.3f}"
    f"{'' if mu_contacts is None else ' (from contacts)'}"
  )
  print(f"  N={len(d['time'])} samples  dt={float(np.median(np.diff(d['time']))):.3f}s")
  print("=" * 78)
  hdr = f"{'invariant':<20} {'type':<5} {'verdict':<7} margin"
  print(hdr)
  print("-" * 78)

  def verdict(r):
    if r["ok"] is None:
      return "SKIP"
    return "PASS" if r["ok"] else "FLAG"

  # inv1
  if inv1["ok"] is None:
    print(f"{'1 vert-impulse':<20} {'HARD':<5} {'SKIP':<7} {inv1.get('note', '')}")
  else:
    wb = inv1["worst_block_dev"]
    print(
      f"{'1 vert-impulse':<20} {'HARD':<5} {verdict(inv1):<7} "
      f"support {inv1['ratio']:.4f} BW (dev {100 * inv1['dev']:.2f}%, "
      f"tol {100 * inv1['tol']:.0f}%)"
      + (f"; worst-block dev {100 * wb:.2f}%" if wb is not None else "")
      + (
        f"; AP mean {inv1['ap_mean_over_bw']:+.3f} BW"
        if inv1["ap_mean_over_bw"] is not None
        else ""
      )
    )
  # inv2 (SOFT -- reported, never gates the exit code; see function docstring)
  if inv2["ok"] is None:
    print(f"{'2 CoP/support':<20} {'SOFT':<5} {'SKIP':<7} {inv2.get('note', '')}")
  else:
    tw = " TOE-PIVOT WARN" if inv2["toe_warn"] else ""
    v2 = "ok" if inv2["ok"] else "note"
    print(
      f"{'2 CoP/support':<20} {'SOFT':<5} {v2:<7} "
      f"outside {_fmt_pct(inv2['worst_outside_frac'])}, "
      f"toe-pivot {_fmt_pct(inv2['worst_toe_pivot_frac'])}{tw}  [quasi-static]"
    )
  # inv3
  if inv3["ok"] is None:
    print(f"{'3 friction-cone':<20} {'HARD':<5} {'SKIP':<7} {inv3.get('note', '')}")
  else:
    print(
      f"{'3 friction-cone':<20} {'HARD':<5} {verdict(inv3):<7} "
      f"breach {_fmt_pct(inv3['worst_breach_frac'])} of stance "
      f"(mu*{1 + FRICTION_MARGIN:.2f}={inv3['limit_with_margin']:.2f}, "
      f"tol {100 * inv3['thr']:.0f}%)"
    )
  # inv4
  if inv4["ok"] is None:
    print(f"{'4 T-N envelope':<20} {'HARD':<5} {'SKIP':<7} {inv4.get('note', '')}")
  else:
    badm = max(inv4["rows"], key=lambda r: r["out_frac"]) if inv4["rows"] else None
    extra = (
      f"worst {badm['joint']}({badm['motor']}) {_fmt_pct(badm['out_frac'])}"
      if badm
      else ""
    )
    print(
      f"{'4 T-N envelope':<20} {'HARD':<5} {verdict(inv4):<7} "
      f"out {_fmt_pct(inv4['worst_out_frac'])} (tol {100 * inv4['thr']:.0f}%); {extra}"
    )
  print("-" * 78)

  # ---- per-invariant detail ---------------------------------------------
  if verbose:
    print(
      "\n[inv2 CoP per foot]  (quasi-static contact recompute, "
      f"{inv2.get('n_frames', '?')} frames)"
    )
    for s, p in inv2.get("per_foot", {}).items():
      if p.get("n_stance", 0) == 0:
        print(f"  {s}: no loaded-stance frames")
        continue
      print(
        f"  {s}: stance={p['n_stance']} outside={_fmt_pct(p['outside_frac'])} "
        f"edge-pivot={_fmt_pct(p['edge_pivot_frac'])} "
        f"(toe={_fmt_pct(p['toe_pivot_frac'])} heel={_fmt_pct(p['heel_pivot_frac'])}) "
        f"cop_x_med={p['cop_normx_median']:+.2f} "
        f"span={100 * p['span_frac_median']:.0f}% "
        f"of {p['footprint_len_x_m'] * 1000:.0f}mm"
      )
    print("\n[inv3 friction per foot]")
    for s, p in inv3.get("per_foot", {}).items():
      if p["n_stance"] == 0:
        print(f"  {s}: no stance")
        continue
      print(
        f"  {s}: stance={p['n_stance']} breach={_fmt_pct(p['breach_frac'])} "
        f"ratio p99={p['ratio_p99']:.3f} max={p['ratio_max']:.3f}"
      )
    print("\n[inv4 T-N per motor]")
    for r in inv4.get("rows", []):
      print(
        f"  {r['joint']:<10} {r['motor']}  peak={r['peak_Nm']:6.1f}Nm "
        f"(rated {r['rated']:.0f}/peak {r['peak']:.0f}) "
        f"spd_p99={r['spd_p99_rpm']:.0f}rpm out={_fmt_pct(r['out_frac'])} "
        f"over_max={r['over_max_Nm']:+.1f}Nm"
      )

  # ---- verdict -----------------------------------------------------------
  hard_flags = [r["name"] for r in results if r["hard"] and r["ok"] is False]
  soft_warn = []
  if inv2.get("toe_warn"):
    soft_warn.append("CoP toe-pivot")
  if inv2.get("ok") is False:
    soft_warn.append("CoP outside footprint")
  print()
  if hard_flags:
    print(f"VERDICT: FLAG  -- hard invariant(s) violated: {', '.join(hard_flags)}")
  else:
    print("VERDICT: PASS  -- all hard invariants within tolerance")
  if soft_warn:
    print(f"         soft warnings: {', '.join(soft_warn)}")
  skipped = [r["name"] for r in results if r["ok"] is None]
  if skipped:
    print(f"         skipped (insufficient data): {', '.join(skipped)}")

  if jsonout:
    Path(jsonout).write_text(
      json.dumps(
        dict(
          npz=str(npz_path),
          model_ab=ab,
          mass=mass,
          g=g,
          bw=bw,
          mu=mu,
          hard_flags=hard_flags,
          soft_warn=soft_warn,
          skipped=skipped,
          invariants=results,
        ),
        indent=2,
        default=float,
      )
    )
    print(f"         json -> {jsonout}")

  return 1 if hard_flags else 0


def main():
  ap = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  ap.add_argument("npz", type=Path)
  ap.add_argument(
    "--model",
    type=Path,
    default=None,
    help="compiled .mjb (default: sibling <tag>_model.mjb)",
  )
  ap.add_argument("--mass", type=float, default=None)
  ap.add_argument("--mu", type=float, default=None)
  ap.add_argument("--subsample", type=int, default=2000)
  ap.add_argument("--json", type=Path, default=None)
  ap.add_argument("-v", "--verbose", action="store_true")
  a = ap.parse_args()
  if not a.npz.exists():
    print(f"!! npz not found: {a.npz}", file=sys.stderr)
    sys.exit(2)
  try:
    rc = run(a.npz, a.model, a.mass, a.mu, a.subsample, a.json, a.verbose)
  except Exception as e:  # loud, never abort caller
    import traceback

    traceback.print_exc()
    print(f"!! invariant_gate error: {e}", file=sys.stderr)
    sys.exit(2)
  sys.exit(rc)


if __name__ == "__main__":
  main()
