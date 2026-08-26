"""How the load distribution moved as the HARDWARE changed, generation by generation.

Same measurement protocol every time (measure_full 15 s dwell, whole training box), so the
clouds are comparable. Each generation is a different machine, not a different policy tweak:

  gen21p2   2026-07-13  aluminium v2 frame, SERIAL ankle, catalogue motor params
  p2b_v2    2026-07-16  same frame, hip-geometry variant
  ankleAB   2026-08-26  PRINTED v3 frame, 2-RSU CLOSED-LOOP ankle, measured motors + T-N clamp
  ankleRP   2026-08-26  printed v3 frame, serial-ankle control of the same envelope

Panels: torque-speed cloud per joint (the design chart's underlying scatter), and the
distribution shift as CDFs so a change of frame/actuator is readable as a curve moving.
  .venv/bin/python3 ../../tools/robot_model/hw_generation_scatter.py
"""
import os
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img'
GENS = [
    ('gen21p2_fc', 'gen2.1 (Al frame, serial ankle)', '#7a7a85'),
    ('p2b_v2_fc', 'p2b v2 (Al frame, hip variant)', '#9c6b3f'),
    ('ankleRP_c3_fc', 'c3 RP (printed v3, serial ctrl)', '#2f9dff'),
    ('ankleAB_c3_fc', 'c3 AB (printed v3, 2-RSU loop)', '#f0961e'),
]
JOINTS = ['hip_pitch', 'hip_roll', 'hip_yaw', 'knee']      # 전 세대 공통 관절만
RATED = {'hip_pitch': 40., 'hip_roll': 40., 'hip_yaw': 20., 'knee': 40.}


def load(tag):
    p = f'analysis/out/{tag}.npz'
    if not os.path.exists(p):
        return None
    return np.load(p, allow_pickle=True)


fig, ax = plt.subplots(2, len(JOINTS), figsize=(5.0 * len(JOINTS), 8.6))
stats = {}
for gi, (tag, label, col) in enumerate(GENS):
    d = load(tag)
    if d is None:
        print('skip', tag); continue
    for ji, j in enumerate(JOINTS):
        tau = np.concatenate([d[f'tau_{s}_{j}_joint'] for s in 'LR' if f'tau_{s}_{j}_joint' in d.files])
        om = np.concatenate([d[f'omega_{s}_{j}_joint'] for s in 'LR' if f'omega_{s}_{j}_joint' in d.files])
        if not len(tau): continue
        k = max(1, len(tau) // 4000)
        ax[0, ji].scatter(om[::k], tau[::k], s=1.2, alpha=.16, color=col, linewidths=0,
                          label=label if ji == 0 else None)
        a = np.abs(tau); xs = np.sort(a); ys = np.arange(1, len(xs) + 1) / len(xs)
        kk = max(1, len(xs) // 2000)
        ax[1, ji].plot(xs[::kk], ys[::kk], color=col, lw=1.8, label=label if ji == 0 else None)
        stats.setdefault(j, {})[label] = (float(np.sqrt((tau ** 2).mean())),
                                          float(np.percentile(a, 99)), float(a.max()),
                                          float(np.percentile(np.abs(om), 99)))
for ji, j in enumerate(JOINTS):
    ax[0, ji].set_title(f'{j}  — torque vs speed', fontsize=11)
    ax[0, ji].set_xlabel('joint speed [rad/s]'); ax[0, ji].grid(alpha=.25)
    ax[1, ji].axvline(RATED[j], color='k', ls='--', lw=1)
    ax[1, ji].text(RATED[j], 0.05, ' rated', fontsize=8)
    ax[1, ji].set_xlabel('|torque| [N·m]'); ax[1, ji].set_xscale('log'); ax[1, ji].grid(alpha=.25)
ax[0, 0].set_ylabel('joint torque [N·m]'); ax[1, 0].set_ylabel('CDF')
ax[0, 0].legend(fontsize=8, markerscale=8, loc='upper right')
fig.suptitle('Load distribution across hardware generations — same 15 s-dwell protocol, whole command box', fontsize=13)
fig.tight_layout(); fig.savefig(f'{OUT}/hw_generation_scatter.png', dpi=115, bbox_inches='tight')
print('wrote', f'{OUT}/hw_generation_scatter.png')

print(f"\n{'joint':11s}{'generation':34s}{'RMS':>8s}{'p99':>8s}{'max':>8s}{'ω p99':>8s}")
for j in JOINTS:
    for lab, v in stats.get(j, {}).items():
        print(f'{j:11s}{lab:34s}{v[0]:8.1f}{v[1]:8.1f}{v[2]:8.1f}{v[3]:8.1f}')
