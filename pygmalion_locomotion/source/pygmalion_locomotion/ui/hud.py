# -*- coding: utf-8 -*-
"""In-sim HUD overlay for keyboard teleop — TIME-SERIES plots (omni.ui).

Per joint: a scrolling line plot of torque utilization (|tau| / motor-peak, in %) over the last
~few seconds, with horizontal reference lines at rated (33%, green) / 80% / peak (100%, red) and a
live value label colored by safety (green<rated, yellow>=rated, orange>=80%peak, red>=peak).
Foot GRF and base reaction are also plotted over time [N].

Guarded: headless (no GUI) = silent no-op; any omni.ui hiccup in update() is swallowed so it can
never crash the sim loop. Logging via WrenchLogger is independent.
"""

from __future__ import annotations

from collections import deque
import numpy as np

try:
    import omni.ui as ui
    _HAS_UI = True
except Exception:  # noqa: BLE001
    _HAS_UI = False

try:
    from isaacsim.util.debug_draw import _debug_draw
    _HAS_DRAW = True
except Exception:  # noqa: BLE001
    _HAS_DRAW = False

# colors (omni.ui = 0xAABBGGRR)
C_GREEN  = 0xFF40C040
C_YELLOW = 0xFF30D0D0
C_ORANGE = 0xFF1090F0
C_RED    = 0xFF3030E0
C_BG     = 0xFF1A1A1A
C_BLUE   = 0xFFE0A030
N_HIST   = 200          # samples kept (~4 s at 50 Hz)
SCALE    = 1.2          # plot y-max = 120% of peak
PLOT_H   = 46           # px per joint plot
FORCE_REF = 780.0       # N, plot y-max for GRF (~1.5x body weight)


def _short(name: str) -> str:
    s = "R" if name.startswith("R") else ("L" if name.startswith("L") else "")
    b = name.lower()
    for k, v in (("hip_pitch", "hip_p"), ("hip_roll", "hip_r"), ("hip_yaw", "hip_y"),
                 ("knee", "knee"), ("ankle_pitch", "ank_p"), ("ankle_roll", "ank_r"), ("toe", "toe")):
        if k in b:
            return f"{s} {v}"
    return name[:5]


class Hud:
    def __init__(self, joint_names, foot_names, effort_limits=None, title="Pygmalion HUD"):
        # show the actuated joints (skip passive toe in the plots)
        self.joint_names = [n for n in joint_names if "toe" not in n.lower()]
        self.foot_names = list(foot_names)
        self.peak = effort_limits or {n: 120.0 for n in self.joint_names}
        self.body_weight = 520.0
        self._hist = {n: deque([0.0] * N_HIST, maxlen=N_HIST) for n in self.joint_names}
        self._fhist = {n: deque([0.0] * N_HIST, maxlen=N_HIST) for n in self.foot_names}
        self._plot = {}     # joint -> ui.Plot
        self._val = {}      # joint -> Label
        self._fplot = {}    # foot -> ui.Plot
        self._fval = {}
        self._labels = {}
        self._window = None
        self._draw = _debug_draw.acquire_debug_draw_interface() if _HAS_DRAW else None
        if _HAS_UI:
            try:
                self._build()
            except Exception as exc:  # noqa: BLE001
                print(f"[HUD] build failed (continuing without HUD): {exc}")
                self._window = None

    def _color(self, util):  # util = |tau|/peak
        if util < 1 / 3.0:  return C_GREEN
        if util < 0.8:      return C_YELLOW
        if util < 1.0:      return C_ORANGE
        return C_RED

    def _ref_lines(self):
        # horizontal reference lines over a plot (0..120% scale): peak(100) red, 80 orange, rated(33) green
        with ui.VStack():
            ui.Spacer(height=ui.Fraction(SCALE * 100 - 100))    # 120 -> 100
            ui.Rectangle(height=ui.Pixel(1), style={"background_color": C_RED})
            ui.Spacer(height=ui.Fraction(20))                   # 100 -> 80
            ui.Rectangle(height=ui.Pixel(1), style={"background_color": C_ORANGE})
            ui.Spacer(height=ui.Fraction(80 - 100 / 3.0))       # 80 -> 33
            ui.Rectangle(height=ui.Pixel(1), style={"background_color": C_GREEN})
            ui.Spacer(height=ui.Fraction(100 / 3.0))            # 33 -> 0

    def _build(self):
        self._window = ui.Window("Pygmalion HUD", width=560, height=640)
        with self._window.frame:
            with ui.VStack(spacing=3):
                self._labels["cmd"] = ui.Label("cmd: -", style={"font_size": 15})
                self._labels["state"] = ui.Label("state: -", style={"font_size": 12})
                ui.Label("Joint torque util% over time   (red=peak  orange=80%  green=rated line)",
                         style={"font_size": 11})
                for n in self.joint_names:
                    with ui.HStack(height=PLOT_H, spacing=4):
                        ui.Label(_short(n), width=56, style={"font_size": 11})
                        with ui.ZStack():
                            ui.Rectangle(style={"background_color": C_BG})
                            self._plot[n] = ui.Plot(ui.Type.LINE, 0.0, SCALE * 100.0,
                                                    *list(self._hist[n]),
                                                    style={"color": C_GREEN, "background_color": 0x00000000})
                            self._ref_lines()
                        self._val[n] = ui.Label("0%", width=80, style={"font_size": 12})
                ui.Separator()
                ui.Label("Foot GRF & base reaction over time [N]", style={"font_size": 11})
                for n in self.foot_names:
                    with ui.HStack(height=40, spacing=4):
                        ui.Label(f"{_short(n)}", width=56, style={"font_size": 11})
                        with ui.ZStack():
                            ui.Rectangle(style={"background_color": C_BG})
                            self._fplot[n] = ui.Plot(ui.Type.LINE, 0.0, FORCE_REF, *list(self._fhist[n]),
                                                     style={"color": C_BLUE, "background_color": 0x00000000})
                        self._fval[n] = ui.Label("0 N", width=80, style={"font_size": 12})
                with ui.HStack(height=18):
                    self._labels["base_reac"] = ui.Label("base reaction: 0 N", style={"font_size": 12})

    # ------------------------------------------------------------------ update
    def update(self, command=None, summary=None, base_reaction=None, mass_total=None,
               foot_positions=None, foot_force_vecs=None):
        if _HAS_UI and self._window is not None:
            try:
                self._update_ui(command, summary, base_reaction, mass_total)
            except Exception:  # noqa: BLE001 - never crash the sim loop
                pass
        if self._draw is not None and foot_positions is not None and foot_force_vecs is not None:
            try:
                self._draw.clear_lines()
                starts, ends, colors, widths = [], [], [], []
                for p, f in zip(foot_positions, foot_force_vecs):
                    p = np.asarray(p, dtype=float); f = np.asarray(f, dtype=float) * 0.002
                    starts.append(tuple(p)); ends.append(tuple(p + f))
                    colors.append((0.1, 1.0, 0.2, 1.0)); widths.append(3.0)
                if starts:
                    self._draw.draw_lines(starts, ends, colors, widths)
            except Exception:  # noqa: BLE001
                pass

    def _update_ui(self, command, summary, base_reaction, mass_total):
        if command is not None:
            c = np.asarray(command).reshape(-1)
            self._labels["cmd"].text = f"cmd  vx={c[0]:+.2f}  vy={c[1]:+.2f}  wz={c[2]:+.2f}"
        if summary is not None:
            bh = summary.get("base_height", 0.0)
            mt = f"{mass_total:.1f}" if mass_total is not None else "?"
            self._labels["state"].text = f"base_h={bh:.3f} m    mass={mt} kg"
            for n, tau in summary.get("joint_torque", {}).items():
                if n not in self._plot:
                    continue
                peak = self.peak.get(n, 120.0)
                util = abs(float(tau)) / peak if peak > 0 else 0.0
                self._hist[n].append(util * 100.0)
                self._plot[n].set_data(*list(self._hist[n]))
                col = self._color(util)
                self._plot[n].set_style({"color": col, "background_color": 0x00000000})
                self._val[n].text = f"{util*100:4.0f}%  {tau:+6.1f}"
                self._val[n].set_style({"font_size": 12, "color": col})
            for n, g in summary.get("foot_grf", {}).items():
                if n in self._fplot:
                    self._fhist[n].append(float(g))
                    self._fplot[n].set_data(*list(self._fhist[n]))
                    self._fval[n].text = f"{g:6.0f} N"
        if base_reaction is not None:
            self._labels["base_reac"].text = f"base reaction (root->world): {base_reaction:7.0f} N"
