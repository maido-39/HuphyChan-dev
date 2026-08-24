"""Quantitative 1:1 companion to the AB/RP comparison videos (same npz, same clock).

Four rows for the 0.8 m/s block: contact timeline (gait diagram), L ankle pitch angle,
L vertical contact-only GRF in body weights, and base vx vs command.
  .venv/bin/python3 ../../tools/robot_model/abrp_gait_compare_plot.py [tag]
"""
import sys, numpy as np, mujoco
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

TAG = sys.argv[1] if len(sys.argv) > 1 else 'g8000'
SRC = '/home/syaro/pyg_fea/work/hack_check'
OUT = f'/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img/abrp_gait_compare_{TAG}.png'
DT, BW = 0.02, 346.8
C = {'AB': '#f0961e', 'RP': '#2f9dff'}

d, ank = {}, {}
for a in ('AB', 'RP'):
    d[a] = np.load(f'{SRC}/ankle{a}_c3_{TAG}.npz')
    m = mujoco.MjModel.from_binary_path(f'{SRC}/ankle{a}_c3_{TAG}_model.mjb')
    adr = {s: m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'robot/{s}_ankle_pitch_joint')] for s in 'LR'}
    ank[a] = {s: np.degrees(d[a]['qpos_full'][:, adr[s]]) for s in 'LR'}
    del m

blk = np.where(np.abs(d['AB']['cmd_vx'] - 0.8) < 1e-6)[0]
blk = blk[blk > blk[0] + 25]                      # drop the command-change transient
t = (blk - blk[0]) * DT
fig, ax = plt.subplots(4, 1, figsize=(13, 11), sharex=True,
                       gridspec_kw=dict(height_ratios=[1.1, 1, 1, 1], hspace=0.16))

# (1) gait diagram
for r, a in enumerate(('AB', 'RP')):
    for k, s in enumerate('LR'):
        on = d[a][f'GRFc_{s}_foot_link_z'][blk] > 0.05 * BW
        y = 3 - (2 * r + k)
        ax[0].fill_between(t, y - 0.35, y + 0.35, where=on, color=C[a], alpha=0.85, lw=0, step='mid')
        ax[0].text(-0.12, y, f'{a} {s}', ha='right', va='center', fontsize=10, color=C[a], fontweight='bold')
ax[0].set_ylim(-0.7, 3.7); ax[0].set_yticks([]); ax[0].set_xlim(-1.05, t[-1])
ax[0].set_title(f'AB (closed-loop crank ankle) vs RP (serial + envelope clamp) - same policy stack, iter 8000, 0.8 m/s command', fontsize=12)

# (2) ankle pitch
for a in ('AB', 'RP'):
    ax[1].plot(t, ank[a]['L'][blk], color=C[a], lw=1.6, label=f'{a}  range {np.ptp(ank[a]["L"][blk]):.1f} deg')
ax[1].set_ylabel('L ankle pitch [deg]'); ax[1].legend(loc='upper right', fontsize=9)

# (3) vertical GRF
for a in ('AB', 'RP'):
    g = d[a]['GRFc_L_foot_link_z'][blk] / BW
    st = g > 0.4                                   # mid-stance only, skip touchdown/lift-off
    rip = float(np.std(np.diff(g[st])))            # step-to-step ripple = contact chatter
    ax[2].plot(t, g, color=C[a], lw=1.4, label=f'{a}  p99 {np.percentile(g, 99):.2f} BW,  stance ripple {rip:.3f}')
ax[2].axhline(1.0, color='0.6', lw=0.8, ls='--'); ax[2].set_ylabel('L vertical GRF [BW]')
ax[2].legend(loc='upper right', fontsize=9)

# (4) tracking
ax[3].plot(t, np.full_like(t, 0.8), color='0.4', lw=1.2, ls='--', label='command 0.8')
for a in ('AB', 'RP'):
    v = d[a]['base_vx'][blk]
    ax[3].plot(t, v, color=C[a], lw=1.4, label=f'{a}  mean err {np.mean(np.abs(v - 0.8)):+.3f}')
ax[3].set_ylabel('base vx [m/s]'); ax[3].set_xlabel('time [s]'); ax[3].legend(loc='lower right', fontsize=9)
for x in ax: x.grid(alpha=0.25)
fig.savefig(OUT, dpi=125, bbox_inches='tight')
print('wrote', OUT)
