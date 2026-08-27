"""What each PhysX knob did to the foot-strike load, drawn rather than tabulated.

Three panels, because the sweep has three findings and a table hides two of them:
  (a) the median strike waveform - MuJoCo, the PhysX baseline (32/1 iterations, the value
      the URDF importer wrote), and the PhysX setting that matches it (4/8). The gap was
      never the stance; it was a one-sample spike sitting on top of an identical stance.
  (b) every single-knob arm as a ratio to MuJoCo, peak and loading rate side by side. One
      bar pair moves; the rest do not.
  (c) the solver-iteration map: peak and rate ratio against position-iteration count at
      fixed velocity-iteration count. Position count sets the RATE, velocity count sets
      the PEAK, and the two lines cross MuJoCo's 1.0 in different places.

  python3 tools/sim2sim/plot_contact_sweep.py
"""
import json
import os

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SW = '/home/syaro/pyg_fea/work/contact_sweep'
MJ_NPZ = '/home/syaro/pyg_fea/work/impact_multi_nodr/bundleD1_RP_raw.npz'
OUT = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img/xengine_contact_sweep.png'
HI, LO = 0.25, 0.05
PRE, POST = 0.02, 0.12
MJ_PEAK, MJ_RATE = 1.2526234984397888, 64.46443200111389


def strikes(F, dt):
    off_min, win = int(0.08 / dt), int(0.06 / dt)
    onsets = []
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
                        if len(f[t0:t0 + win]) >= 4:
                            onsets.append((e, k, t0))
                    off_run = 0
    return onsets


def median_window(F, dt):
    a, b = int(PRE / dt), int(POST / dt)
    out = [F[t0 - a:t0 + b, e, k] for e, k, t0 in strikes(F, dt)
           if t0 - a >= 0 and t0 + b <= F.shape[0]]
    return np.median(np.array(out), axis=0), np.arange(-a, b) * dt * 1000.0


def isaac_window(tag):
    d = np.load(f'{SW}/isaac_grf_pygmalion_v3_printed_{tag}_traces.npz')
    dt = float(d['dt'])
    w0 = int(float(d['warm_s']) / dt)
    return median_window(d['F_BW'][w0:][:, None, :].astype(np.float64), dt)


rows = {r['tag']: r for r in json.load(open(f'{SW}/table.json'))}
dm = np.load(MJ_NPZ)
mw, mt = median_window(dm['F'].astype(np.float64), float(dm['dt']))

C_M, C_B, C_F = '#2471a3', '#c0392b', '#1e8449'
fig = plt.figure(figsize=(15.5, 4.8))
gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 1.5, 1.15], wspace=0.30)

# ---- (a) waveforms -----------------------------------------------------------------------
ax = fig.add_subplot(gs[0, 0])
bw, bt = isaac_window('base')
fw, ft = isaac_window('b7_pos4vel8')
ax.plot(mt, mw, color=C_M, lw=2.6, label='MuJoCo (reference)')
ax.plot(bt, bw, color=C_B, lw=2.2, label='PhysX 32/1 iters (as imported)')
ax.plot(ft, fw, color=C_F, lw=2.2, ls='--', label='PhysX 4/8 iters (matched)')
ax.axvline(0, color='0.5', lw=0.8, ls='--')
ax.axhline(1.0, color='0.5', lw=0.8, ls=':')
ax.text(POST * 1000 * 0.99, 1.03, 'body weight', ha='right', va='bottom', fontsize=8,
        color='0.4')
ax.set_xlabel('time from touchdown [ms]')
ax.set_ylabel('ground force under one foot [BW]')
ax.set_title('(a) Median foot strike', fontsize=11, loc='left')
ax.legend(frameon=False, fontsize=8.5, loc='upper right', borderaxespad=0.2)
ax.annotate('rigid-contact spike:\none 5 ms sample, then a rebound dip',
            xy=(1, float(bw.max()) * 0.97), xytext=(30, 1.62), fontsize=8, color=C_B,
            arrowprops=dict(arrowstyle='->', color=C_B, lw=1.0))
ax.set_xlim(bt[0], bt[-1])
ax.spines[['top', 'right']].set_visible(False)

# ---- (b) one knob at a time --------------------------------------------------------------
ax = fig.add_subplot(gs[0, 1])
arms = [('base', 'baseline 32/1'), ('e_bounce02', 'bounce thr. 0.2'),
        ('c_offsets', 'contact offset 5 mm'), ('c0_deinst', 'de-instance (control)'),
        ('a_maxdepen1', 'max depen. vel 1.0'), ('d0_footmat', 'explicit foot material'),
        ('d_compliant', 'compliant contact'), ('b_iters84', 'solver iters 8/4')]
x = np.arange(len(arms))
pk = [rows[t]['peak'] / MJ_PEAK for t, _ in arms]
rt = [rows[t]['rate'] / MJ_RATE for t, _ in arms]
ax.bar(x - 0.19, pk, 0.36, color=C_B, alpha=0.85, label='peak force / MuJoCo')
ax.bar(x + 0.19, rt, 0.36, color='#d68910', alpha=0.85, label='loading rate / MuJoCo')
for xi, (a, b) in enumerate(zip(pk, rt)):
    ax.text(xi - 0.19, a + 0.05, f'{a:.2f}', ha='center', fontsize=8, color=C_B)
    ax.text(xi + 0.19, b + 0.05, f'{b:.2f}', ha='center', fontsize=8, color='#a0640a')
ax.axhline(1.0, color=C_M, lw=1.4)
ax.text(len(arms) - 0.4, 1.05, 'MuJoCo = 1.0', color=C_M, fontsize=8.5, ha='right')
ax.set_xticks(x)
ax.set_xticklabels([n for _, n in arms], fontsize=8, rotation=22, ha='right')
ax.set_ylabel('ratio to MuJoCo')
ax.set_title('(b) One knob at a time - only the solver moves', fontsize=11, loc='left')
ax.legend(frameon=False, fontsize=8.5, loc='upper left')
ax.spines[['top', 'right']].set_visible(False)

# ---- (c) the iteration map ---------------------------------------------------------------
ax = fig.add_subplot(gs[0, 2])
v4 = [('b6_pos1vel4', 1), ('b5_pos2vel4', 2), ('b3_pos4vel4', 4), ('b_iters84', 8),
      ('b4_pos16vel4', 16), ('b2_pos32vel4', 32)]
v1 = [('b1_pos8vel1', 8), ('base', 32)]
v8 = [('b7_pos4vel8', 4), ('b9_pos8vel8', 8)]
for grp, ls, mk, lab in ((v4, '-', 'o', 'velocity iters = 4'),
                         (v8, '--', 's', 'velocity iters = 8'),
                         (v1, ':', '^', 'velocity iters = 1')):
    xs = [n for _, n in grp]
    ax.plot(xs, [rows[t]['rate'] / MJ_RATE for t, _ in grp], ls + mk, color='#d68910',
            lw=1.8, ms=5, label=f'rate, {lab}')
    ax.plot(xs, [rows[t]['peak'] / MJ_PEAK for t, _ in grp], ls + mk, color=C_B,
            lw=1.8, ms=5, label=f'peak, {lab}')
ax.axhline(1.0, color=C_M, lw=1.4)
ax.set_xscale('log', base=2)
ax.set_xticks([1, 2, 4, 8, 16, 32])
ax.set_xticklabels([1, 2, 4, 8, 16, 32])
ax.set_xlabel('solver POSITION iteration count')
ax.set_ylabel('ratio to MuJoCo')
ax.set_title('(c) Position count sets the rate,\n     velocity count sets the peak',
             fontsize=11, loc='left')
ax.legend(frameon=False, fontsize=7.5, ncol=1, loc='upper left')
ax.spines[['top', 'right']].set_visible(False)

fig.suptitle('PhysX contact/solver sweep against MuJoCo - bundleD1_RP at 1.6 m/s, '
             'v3_printed (35.35 kg), 45 s per arm, one knob at a time.  '
             'Every arm holds mean support at 1.000 BW and none fell.',
             fontsize=10.5, y=1.02)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig.savefig(OUT, dpi=140, bbox_inches='tight')
print('wrote', OUT)
