"""viser UI: 3D scene (mjviser) + the control panel.

Panel folders: Model / Base / Joints / Plots / Status.

Two rules the panel follows everywhere:
  * every number shown for a joint comes from the CONTRACT (default, clip window, travel
    sign, mirrored flag) or from the model's own state - never from a regex over the name;
  * a GUI callback only enqueues a ``Command``.  It never touches MjData.  The sim thread
    owns the model.

Mirror handling: on the v30 build the two legs have opposite joint axes for the knee, the
hips, the cranks and the ankle roll.  ``+0.35 rad`` therefore means flexion on the left leg
and extension on the right.  Every mirrored joint's readout carries a second number,
``phys``, which is ``travel_sign * q`` - the same physical motion reads the same on both
legs.  The slider stays in raw q, because that is what the API, the policy and the
telemetry all speak.
"""

from __future__ import annotations

import math
import threading
import time

import numpy as np
import viser
from mjviser import ViserMujocoScene

from . import CACHE_DIR, VARIANTS
from .contract import list_baked, load_contract

PLOT_WINDOW_S = 10.0
PLOT_HZ = 50.0
PLOT_PUSH_HZ = 10.0
RENDER_HZ = 30.0
READOUT_HZ = 10.0
MAX_CHANNELS = 8

_COLORS = [
  "#4c78a8", "#f58518", "#54a24b", "#e45756",
  "#72b7b2", "#b279a2", "#eeca3b", "#9d755d",
]


class RingPlot:
  """Fixed-size circular buffer, one row per channel.  Never grows."""

  def __init__(self, channels: list[str], n: int):
    self.channels = channels
    self.n = n
    self.t = np.zeros(n)
    self.y = np.zeros((len(channels), n))
    self.i = 0
    self.filled = 0
    self._idx = {c: k for k, c in enumerate(channels)}

  def push(self, t: float, values: dict[str, float]) -> None:
    self.t[self.i] = t
    for c, v in values.items():
      self.y[self._idx[c], self.i] = v
    self.i = (self.i + 1) % self.n
    self.filled = min(self.filled + 1, self.n)

  def view(self, chans: list[str]):
    if self.filled == 0:
      return None
    order = np.arange(self.i - self.filled, self.i) % self.n
    return self.t[order], [self.y[self._idx[c]][order] for c in chans]


def build_ui(core, host: str, port: int, freshness: dict, base: str = "free") -> viser.ViserServer:
  server = viser.ViserServer(host=host, port=port, label="Pygmalion sim<->real viewer")
  state = {"core": core, "scene": None, "stop": False, "freshness": freshness, "base": base}
  _mount(server, state)

  def render_loop():
    last_r = last_p = last_o = 0.0
    while not state["stop"]:
      now = time.perf_counter()
      c = state["core"]
      if now - last_r >= 1.0 / RENDER_HZ:
        try:
          state["scene"].update_from_mjdata(c.d)
        except Exception:
          pass
        last_r = now
      if now - last_o >= 1.0 / READOUT_HZ:
        try:
          state["readout"]()
        except Exception:
          pass
        last_o = now
      if now - last_p >= 1.0 / PLOT_PUSH_HZ:
        try:
          state["push_plot"]()
        except Exception:
          pass
        last_p = now
      time.sleep(0.005)

  t = threading.Thread(target=render_loop, name="pygviewer-ui", daemon=True)
  t.start()
  state["thread"] = t
  return server


# --------------------------------------------------------------------------- panel
def _mount(server: viser.ViserServer, state: dict) -> None:
  core = state["core"]
  c = core.c
  gui = server.gui
  state["scene"] = ViserMujocoScene(server, core.m, num_envs=1)
  state["scene"].update_from_mjdata(core.d)

  # ------------------------------------------------------------------ Model
  with gui.add_folder("Model"):
    baked = list_baked(CACHE_DIR) or [c.variant]
    dd = gui.add_dropdown("variant", tuple(baked), initial_value=c.variant)
    stale = "STALE" if state["freshness"].get("stale") else "fresh"
    gui.add_markdown(
      f"**{c.variant}** &nbsp; `{c.contract_sha[:12]}` &nbsp; ({stale})\n\n"
      f"{c.raw['total_mass_kg']} kg &middot; nu {c.raw['nu']} &middot; "
      f"{c.raw['n_dof']} joints &middot; physics {1 / c.raw['physics_dt']:.0f} Hz / "
      f"control {1 / c.raw['step_dt']:.0f} Hz\n\n"
      f"xml `{c.raw['model_xml'].split('/')[-1]}`  \n"
      f"mjlab `{c.raw['mjlab_git']}` &middot; baked {c.raw['bake_utc']}"
    )
    reload_btn = gui.add_button("load variant")

    @reload_btn.on_click
    def _(_evt):
      want = dd.value
      if want == state["core"].c.variant:
        return
      _swap_variant(server, state, want)

  # ------------------------------------------------------------------ Base
  with gui.add_folder("Base link"):
    gui.add_markdown(
      "`free` gravity only &middot; `fixed` welded to the anchor &middot; "
      "`pivot` the offset point is held, rotation free.\n\n"
      "**Gravity is never modified by any of these.**"
    )
    mode = gui.add_dropdown(
      "mode", ("free", "fixed", "pivot"), initial_value=state.get("base", core.base_mode)
    )
    px = gui.add_number("anchor x [m]", initial_value=0.0, step=0.005)
    py = gui.add_number("anchor y [m]", initial_value=0.0, step=0.005)
    height = gui.add_slider(
      "height z [m]", min=0.0, max=1.6, step=0.005, initial_value=float(core.base_pos[2])
    )
    roll = gui.add_slider("roll [deg]", min=-90, max=90, step=0.5, initial_value=0.0)
    pitch = gui.add_slider("pitch [deg]", min=-90, max=90, step=0.5, initial_value=0.0)
    yaw = gui.add_slider("yaw [deg]", min=-180, max=180, step=0.5, initial_value=0.0)
    ox = gui.add_number("pivot offset x [m]", initial_value=0.0, step=0.005)
    oy = gui.add_number("pivot offset y [m]", initial_value=0.0, step=0.005)
    oz = gui.add_number("pivot offset z [m]", initial_value=0.0, step=0.005)
    ground = gui.add_checkbox("ground contact", initial_value=True)
    kf = gui.add_button_group("reset to (also restores the base pose)",
                              ("home", "knees_bent"))

  def push_base(_evt=None):
    state["core"].submit(
      {
        "op": "base",
        "mode": mode.value,
        "pos": [px.value, py.value, height.value],
        "rpy": [math.radians(roll.value), math.radians(pitch.value), math.radians(yaw.value)],
        "pivot_offset": [ox.value, oy.value, oz.value],
        "ground": ground.value,
      }
    )

  for h in (mode, px, py, height, roll, pitch, yaw, ox, oy, oz, ground):
    h.on_update(push_base)

  @kf.on_click
  def _(_evt):
    state["core"].submit({"op": "reset", "keyframe": kf.value})

  # ------------------------------------------------------------------ Joints
  sliders: dict[str, tuple] = {}
  readouts: dict[str, object] = {}
  guard = {"busy": False}

  def send(name: str, v: float):
    if guard["busy"]:
      return
    state["core"].submit({"op": "target", "values": {name: float(v)}})

  with gui.add_folder("Joints (targets, rad)"):
    gui.add_markdown(
      "Slider range = the contract's `safe_clip` (centre &plusmn; 0.5&middot;range&middot;"
      "factor) - the same clamp the trainer applies to a policy target. `phys` on a mirrored "
      "joint is `travel_sign &times; q`, so both legs read alike."
    )
    for n in c.action_joint_names:
      lo, hi = c.clip(n)
      d0 = c.default_q(n)
      row = gui.add_slider(
        n.replace("_joint", ""),
        min=round(lo, 4),
        max=round(hi, 4),
        step=0.002,
        initial_value=float(np.clip(d0, lo, hi)),
      )
      num = gui.add_number(f"{n.replace('_joint', '')} =", initial_value=float(d0), step=0.002)
      txt = gui.add_text(f"{n.replace('_joint', '')} state", initial_value="", disabled=True)
      sliders[n] = (row, num)
      readouts[n] = txt

      def _mk(nn, rr, nn2):
        @rr.on_update
        def _(_evt):
          guard["busy"] = True
          nn2.value = rr.value
          guard["busy"] = False
          send(nn, rr.value)

        @nn2.on_update
        def _(_evt):
          lo2, hi2 = c.clip(nn)
          v = float(np.clip(nn2.value, lo2, hi2))
          guard["busy"] = True
          rr.value = v
          guard["busy"] = False
          send(nn, v)

      _mk(n, row, num)

    home_btn = gui.add_button("targets -> default pose")

    @home_btn.on_click
    def _(_evt):
      vals = {n: c.default_q(n) for n in c.action_joint_names}
      state["core"].submit({"op": "target", "values": vals})
      guard["busy"] = True
      for n, (r, nu) in sliders.items():
        lo2, hi2 = c.clip(n)
        r.value = float(np.clip(vals[n], lo2, hi2))
        nu.value = vals[n]
      guard["busy"] = False

  # ------------------------------------------------------------------ Ankle (AB)
  ankle_ctl = {}
  if core.ankle_inverse is not None:
    meta = c.raw["ankle_inverse"]
    (pl, ph), (rl, rh) = core.ankle_inverse.bounds()
    with gui.add_folder("Ankle foot-space (AB)"):
      gui.add_markdown(
        f"method **{meta['method']}** from `{meta['envelope_tag']}`, per-leg sign map fitted "
        f"at bake, worst probe residual **{meta['worst_residual_rad']} rad**.\n\n"
        "These sliders command the two CRANKS through the inverse. The pitch/roll shown in "
        "Status is the model's own state, so any inverse error shows as target-vs-actual."
      )
      for s in ("L", "R"):
        sp = gui.add_slider(
          f"{s} ankle pitch [rad]", min=round(pl, 3), max=round(ph, 3), step=0.005,
          initial_value=0.0,
        )
        sr = gui.add_slider(
          f"{s} ankle roll [rad]", min=round(rl, 3), max=round(rh, 3), step=0.005,
          initial_value=0.0,
        )
        ankle_ctl[s] = (sp, sr)

        def _mk_ankle(side, a, b):
          def _cb(_evt):
            state["core"].submit(
              {"op": "ankle", "side": side, "pitch": a.value, "roll": b.value}
            )
            cr = state["core"].ankle_inverse(side, a.value, b.value)
            guard["busy"] = True
            for jn, v in zip((f"{side}_crank_A_joint", f"{side}_crank_B_joint"), cr):
              if jn in sliders:
                lo2, hi2 = c.clip(jn)
                sliders[jn][0].value = float(np.clip(v, lo2, hi2))
                sliders[jn][1].value = float(v)
            guard["busy"] = False

          a.on_update(_cb)
          b.on_update(_cb)

        _mk_ankle(s, sp, sr)

  # ------------------------------------------------------------------ Plots
  chan_names = []
  for n in c.action_joint_names:
    chan_names += [f"{n}|q", f"{n}|target", f"{n}|tau"]
  ring = RingPlot(chan_names, int(PLOT_WINDOW_S * PLOT_HZ))
  sel_joint: dict[str, object] = {}
  with gui.add_folder("Plots"):
    gui.add_markdown(
      f"ring buffer {PLOT_WINDOW_S:.0f} s @ {PLOT_HZ:.0f} Hz, pushed at {PLOT_PUSH_HZ:.0f} Hz, "
      f"max {MAX_CHANNELS} channels. Nothing accumulates."
    )
    sig_q = gui.add_checkbox("q", initial_value=True)
    sig_t = gui.add_checkbox("target", initial_value=True)
    sig_u = gui.add_checkbox("tau [N*m]", initial_value=False)
    with gui.add_folder("joints", expand_by_default=False):
      for n in c.action_joint_names:
        sel_joint[n] = gui.add_checkbox(
          n.replace("_joint", ""), initial_value=(n == c.action_joint_names[3])
        )
    warn = gui.add_markdown("")
    plot = gui.add_uplot(
      data=(np.zeros(2), np.zeros(2)),
      series=(
        {"label": "t [s]"},
        {"label": "-", "stroke": _COLORS[0]},
      ),
      title="joint traces",
      aspect=1.4,
    )

  def selected_channels() -> list[str]:
    sigs = [s for s, on in (("q", sig_q.value), ("target", sig_t.value), ("tau", sig_u.value)) if on]
    out = [f"{n}|{s}" for n in c.action_joint_names if sel_joint[n].value for s in sigs]
    return out[:MAX_CHANNELS], len(out)

  def push_plot():
    chans, total = selected_channels()
    warn.content = (
      f"showing {len(chans)} of {total} selected channels (cap {MAX_CHANNELS})"
      if total > MAX_CHANNELS
      else ""
    )
    if not chans:
      return
    v = ring.view(chans)
    if v is None:
      return
    t, ys = v
    plot.data = (t, *ys)
    plot.series = (
      {"label": "t [s]"},
      *(
        {"label": ch.replace("_joint", ""), "stroke": _COLORS[k % len(_COLORS)]}
        for k, ch in enumerate(chans)
      ),
    )

  state["push_plot"] = push_plot

  # ------------------------------------------------------------------ Status
  with gui.add_folder("Status"):
    status_md = gui.add_markdown("")

  jc = c.raw["joint_contract"]

  def readout():
    s = state["core"].snapshot()
    if not s:
      return
    qi = {n: i for i, n in enumerate(s["joint_names"])}
    for k, n in enumerate(s["act_names"]):
      q = s["q"][qi[n]]
      tau = s["tau"][k]
      tgt = s["target"][k]
      extra = ""
      if jc[n]["mirrored"] and jc[n]["travel_sign"]:
        extra = f"  phys {jc[n]['travel_sign'] * q:+.3f}"
      if n in readouts:
        readouts[n].value = f"q {q:+.3f}  tgt {tgt:+.3f}  tau {tau:+7.2f}{extra}"
    b = s["base"]
    lines = [
      f"**{s['variant']}**  mode `{s['mode']}`  sim t {s['t']:.2f} s",
      "",
      f"physics **{s['rates']['phys_hz']:.0f} Hz**  control **{s['rates']['ctrl_hz']:.0f} Hz**  "
      f"drops {s['rates']['drops']}",
      "",
      f"base `{b['mode']}` pos ({b['pos'][0]:+.3f}, {b['pos'][1]:+.3f}, {b['pos'][2]:+.3f}) "
      f"rpy ({math.degrees(b['rpy'][0]):+.1f}, {math.degrees(b['rpy'][1]):+.1f}, "
      f"{math.degrees(b['rpy'][2]):+.1f}) deg  ground {'on' if b['ground'] else 'OFF'}",
    ]
    if "ankle_derived" in s:
      ad = " ".join(
        f"{k}: pitch {v['pitch']:+.3f} roll {v['roll']:+.3f}" for k, v in s["ankle_derived"].items()
      )
      lines += ["", f"ankle (model state) {ad}", f"loop closure {s['closure_mm']:.4f} mm"]
    if s.get("imu"):
      g = s["imu"].get("imu_upvector")
      w = s["imu"].get("imu_ang_vel")
      if g and w:
        lines += [
          "",
          f"imu up ({g[0]:+.3f}, {g[1]:+.3f}, {g[2]:+.3f})  gyro "
          f"({w[0]:+.2f}, {w[1]:+.2f}, {w[2]:+.2f}) rad/s",
        ]
    from .api import rss_mb

    lines += ["", f"RSS {rss_mb():.0f} MB"]
    if s.get("warnings"):
      lines += ["", "**" + " / ".join(s["warnings"]) + "**"]
    status_md.content = "\n".join(lines)

  state["readout"] = readout

  # -------------------------------------------------- sim hook -> ring buffer
  last = {"t": -1.0}

  def hook(snap: dict):
    if snap["t"] - last["t"] < 1.0 / PLOT_HZ:
      return
    last["t"] = snap["t"]
    qi = {n: i for i, n in enumerate(snap["joint_names"])}
    vals = {}
    for k, n in enumerate(snap["act_names"]):
      vals[f"{n}|q"] = snap["q"][qi[n]]
      vals[f"{n}|target"] = snap["target"][k]
      vals[f"{n}|tau"] = snap["tau"][k]
    ring.push(snap["t"], vals)

  core.add_hook(hook)
  state["ring"] = ring


def _swap_variant(server: viser.ViserServer, state: dict, want: str) -> None:
  """Tear the whole panel down and rebuild it on another baked model."""
  from .sim_core import SimCore

  old = state["core"]
  old.stop()
  c = load_contract(CACHE_DIR, want)
  new = SimCore(c)
  server.scene.reset()
  server.gui.reset()
  state["core"] = new
  state["freshness"] = c.freshness()
  _mount(server, state)
  new.start()
