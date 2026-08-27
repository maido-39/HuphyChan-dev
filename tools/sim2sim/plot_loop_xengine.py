"""One figure for the closed-loop cross-engine static check: agreement, drift, and the loop's share.

Three panels, because three different things had to be true at once and a table hides which one
failed: (left) the torque each engine says every motor needs, (middle) how far apart the two points
each loop-closure joint is supposed to hold together actually drifted, (right) the part of the
answer that only exists because of the loop - how much of the crank torque is the crank's own
weight versus foot load arriving through the rods.

  mujoco-sim/mjlab/.venv/bin/python3 tools/sim2sim/plot_loop_xengine.py
"""
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

V = json.load(open('/home/syaro/pyg_fea/work/xengine_loop_verdict.json'))
REF = json.load(open('/home/syaro/pyg_fea/work/xengine_loop_mujoco.json'))
OUT = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img/xengine_loop_static.png'

ph = V['phases']['motors']
rows = ph['rows']
short = [r['joint'].replace('_joint', '').replace('shoulder', 'sh') for r in rows]
iso = np.array([r['isaac'] for r in rows])
mj = np.array([r['mujoco'] for r in rows])

fig, ax = plt.subplots(1, 3, figsize=(15, 4.6), gridspec_kw={'width_ratios': [2.2, 1, 1.1]})

y = np.arange(len(rows))
ax[0].barh(y - 0.2, mj, 0.4, label='MuJoCo (constrained statics)', color='#3c6e9f')
ax[0].barh(y + 0.2, iso, 0.4, label='IsaacSim (settled PD effort)', color='#d1743a')
ax[0].set_yticks(y); ax[0].set_yticklabels(short, fontsize=8)
ax[0].invert_yaxis(); ax[0].axvline(0, color='k', lw=0.6)
ax[0].set_xlabel('gravity-hold torque [N·m]')
ax[0].set_title(f"Motors-only hold: max diff {ph['max_diff_Nm']*1e3:.1f} mN·m "
                f"({ph['worst_joint'].replace('_joint','')})", fontsize=10)
ax[0].legend(fontsize=8, loc='lower right')
ax[0].grid(axis='x', alpha=0.3)

d = V['phases']['motors']['loop_drift_mm_isaac']
names = list(d)
ax[1].bar(range(len(names)), [d[k] for k in names], color='#5a9367')
ax[1].axhline(1.0, color='#b3402f', ls='--', lw=1.2, label='1 mm acceptance')
ax[1].set_xticks(range(len(names)))
ax[1].set_xticklabels([n.replace('_loop', '') for n in names], fontsize=8)
ax[1].set_ylabel('anchor separation [mm]')
ax[1].set_yscale('log')
ax[1].set_title('Loop-closure drift in PhysX', fontsize=10)
fk = V['phases']['motors'].get('ankle_from_cranks', {}).get('isaac_minus_mujoco_rad', {})
if fk:
    worst = max(abs(v) for k, v in fk.items() if 'ankle' in k)
    ax[1].text(0.5, 0.42, f'free ankle lands within\n{worst*1e6:.0f} µrad of MuJoCo\nfor the same crank angles',
               transform=ax[1].transAxes, ha='center', fontsize=8,
               bbox=dict(boxstyle='round', fc='#eef4ee', ec='#5a9367'))
ax[1].legend(fontsize=8)
ax[1].grid(axis='y', alpha=0.3)

cranks = [r for r in rows if 'crank' in r['joint']]
bias = REF['bias_Nm']
cn = [c['joint'].replace('_joint', '') for c in cranks]
own = np.array([bias[c['joint']] for c in cranks])          # crank+rod subtree weight alone
tot = np.array([c['mujoco'] for c in cranks])               # what the motor really holds
x = np.arange(len(cn))
ax[2].bar(x - 0.2, own, 0.4, label='own subtree weight (qfrc_bias)', color='#8c8c8c')
ax[2].bar(x + 0.2, tot, 0.4, label='actual motor torque (via loop)', color='#3c6e9f')
ax[2].set_xticks(x); ax[2].set_xticklabels(cn, fontsize=8, rotation=20)
ax[2].set_ylabel('torque [N·m]')
ax[2].set_title('Why qfrc_bias alone is wrong on a loop', fontsize=10)
ax[2].legend(fontsize=8)
ax[2].grid(axis='y', alpha=0.3)

fig.suptitle('Closed-loop (2-RSU) ankle: MuJoCo vs IsaacSim static validation, same bent pose, base welded',
             fontsize=11)
fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig(OUT, dpi=140)
print('->', OUT)
