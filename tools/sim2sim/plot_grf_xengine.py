"""Draw the Isaac-vs-MuJoCo landing comparison: the same gait, a different contact model.

Three panels, because the claim has three parts and a table alone hides the shape of it:
  (a) every detected strike from both engines, aligned on touchdown, one faint line each,
      with the median trace on top - this is where the difference is visible as a SPIKE
      sitting on top of an otherwise identical stance.
  (b) peak force per strike, as distributions.
  (c) loading rate per strike, as distributions.

  python3 tools/sim2sim/plot_grf_xengine.py
"""
import json
import os

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

WORK = '/home/syaro/pyg_fea/work'
ISAAC_NPZ = f'{WORK}/isaac_grf_pygmalion_v3_printed_traces.npz'
ISAAC_JSON = f'{WORK}/isaac_grf_pygmalion_v3_printed.json'
MJ_NPZ = f'{WORK}/impact_multi_nodr/bundleD1_RP_raw.npz'
OUT = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img/xengine_grf_isaac_vs_mujoco.png'
HI, LO = 0.25, 0.05
PRE, POST = 0.02, 0.12          # seconds of trace kept around each touchdown, for the plot


def strikes(F, dt):
    """Same Schmitt-trigger detector as impact_probe_multi / isaac_grf_rollout."""
    off_min, win = int(0.08 / dt), int(0.06 / dt)
    onsets, peaks, rates = [], [], []
    for e in range(F.shape[1]):
        for k in range(F.shape[2]):
            f = F[:, e, k]
            armed, off_run = True, off_min
            for t in range(len(f)):
                if f[t] < LO:
                    off_run += 1
                    if off_run >= off_min:
                        armed = True
                else:
                    if armed and f[t] > HI:
                        armed, off_run = False, 0
                        t0 = t
                        while t0 > 0 and f[t0 - 1] >= LO:
                            t0 -= 1
                        w = f[t0:t0 + win]
                        if len(w) >= 4:
                            onsets.append((e, k, t0))
                            peaks.append(float(w.max()))
                            rates.append(float(np.max(np.diff(w)) / dt))
                    off_run = 0
    return onsets, np.array(peaks), np.array(rates)


def windows(F, dt, onsets):
    a, b = int(PRE / dt), int(POST / dt)
    out = []
    for e, k, t0 in onsets:
        if t0 - a < 0 or t0 + b > F.shape[0]:
            continue
        out.append(F[t0 - a:t0 + b, e, k])
    return np.array(out), (np.arange(-a, b) * dt * 1000.0)


di = np.load(ISAAC_NPZ)
res = json.load(open(ISAAC_JSON))
dt_i = float(di['dt'])
w0 = int(float(di['warm_s']) / dt_i)
Fi = di['F_BW'][w0:][:, None, :].astype(np.float64)
dm = np.load(MJ_NPZ)
dt_m = float(dm['dt'])
Fm = dm['F'].astype(np.float64)

oi, pi, ri = strikes(Fi, dt_i)
om, pm, rm = strikes(Fm, dt_m)
Wi, ti = windows(Fi, dt_i, oi)
Wm, tm = windows(Fm, dt_m, om)

C_I, C_M = '#c0392b', '#2471a3'
fig = plt.figure(figsize=(13.5, 4.6))
gs = fig.add_gridspec(1, 3, width_ratios=[1.9, 1, 1], wspace=0.28)

ax = fig.add_subplot(gs[0, 0])
for W, c in ((Wm, C_M), (Wi, C_I)):
    for row in W[:: max(1, len(W) // 120)]:
        ax.plot(tm if c == C_M else ti, row, color=c, alpha=0.10, lw=0.7)
ax.plot(tm, np.median(Wm, axis=0), color=C_M, lw=2.6,
        label=f'MuJoCo  ({len(pm)} strikes, {len(Wm)} drawn)')
ax.plot(ti, np.median(Wi, axis=0), color=C_I, lw=2.6,
        label=f'IsaacSim / PhysX  ({len(pi)} strikes, {len(Wi)} drawn)')
ax.annotate('PhysX: one 5 ms sample,\nthen a rebound dip',
            xy=(0, float(np.median(Wi, axis=0).max())), xytext=(26, 3.15),
            fontsize=8.5, color=C_I,
            arrowprops=dict(arrowstyle='->', color=C_I, lw=1.0))
ax.annotate('MuJoCo: 20 ms rise', xy=(12, 1.22), xytext=(46, 1.75),
            fontsize=8.5, color=C_M,
            arrowprops=dict(arrowstyle='->', color=C_M, lw=1.0))
ax.axvline(0, color='0.5', lw=0.8, ls='--')
ax.axhline(1.0, color='0.5', lw=0.8, ls=':')
ax.text(POST * 1000 * 0.99, 1.03, 'body weight', ha='right', va='bottom',
        fontsize=8, color='0.4')
ax.set_xlabel('time from foot touchdown [ms]')
ax.set_ylabel('ground force under one foot [body weights]')
ax.set_title('(a) Same stance, different impact spike', fontsize=11, loc='left')
ax.legend(frameon=False, fontsize=9, loc='upper right')
ax.set_xlim(ti[0], ti[-1])
ax.spines[['top', 'right']].set_visible(False)


def dist(ax, a, b, title, unit):
    parts = ax.violinplot([b, a], positions=[0, 1], showextrema=False, widths=0.75)
    for pc, c in zip(parts['bodies'], (C_M, C_I)):
        pc.set_facecolor(c); pc.set_alpha(0.35); pc.set_edgecolor(c)
    ax.boxplot([b, a], positions=[0, 1], widths=0.16, showfliers=False,
               medianprops=dict(color='k', lw=1.6),
               boxprops=dict(color='0.3'), whiskerprops=dict(color='0.3'),
               capprops=dict(color='0.3'))
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi + 0.20 * (hi - lo))     # headroom so the labels clear the violins
    for x, v, c in ((0, b, C_M), (1, a, C_I)):
        ax.text(x, ax.get_ylim()[1], f'median {np.median(v):.3g}', ha='center', va='top',
                fontsize=9, color=c, fontweight='bold')
    ax.set_xticks([0, 1]); ax.set_xticklabels(['MuJoCo', 'PhysX'])
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel(unit)
    ax.set_title(title, fontsize=11, loc='left')
    ax.spines[['top', 'right']].set_visible(False)


dist(fig.add_subplot(gs[0, 1]), pi, pm,
     f'(b) Peak force  x{np.median(pi)/np.median(pm):.2f}', 'peak [body weights]')
dist(fig.add_subplot(gs[0, 2]), ri, rm,
     f'(c) Loading rate  x{np.median(ri)/np.median(rm):.2f}', 'rate [body weights / s]')

fig.suptitle('Foot-strike load, same policy at 1.6 m/s, same 35.35 kg robot, same detector'
             f'   -   MuJoCo soft contact (20 ms time constant) vs PhysX rigid contact'
             f'   -   mean support 1.00 BW both engines',
             fontsize=10.5, y=1.0)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig.savefig(OUT, dpi=140, bbox_inches='tight')
print('wrote', OUT)
print(f'isaac peak med {np.median(pi):.3f} rate {np.median(ri):.1f} n={len(pi)}')
print(f'mujoco peak med {np.median(pm):.3f} rate {np.median(rm):.1f} n={len(pm)}')
