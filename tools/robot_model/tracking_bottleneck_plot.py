"""Where the training metric error_vel_xy comes from (docs/96). Four panels:
 A  error vs time since the command changed (deterministic vs training exploration noise)
 B  error vs command magnitude (steady-state part only)
 C  held-command speed capability, AB vs RP (15 s dwell each)
 D  actuator utilisation against the measured 48 V T-N curve at each held command
"""
import json, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

W1 = '/home/syaro/pyg_fea/work/track_decomp'; W2 = '/home/syaro/pyg_fea/work/speed_bottleneck'
OUT = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img/tracking_bottleneck_9500.png'
det = json.load(open(f'{W1}/ankleAB_c3_dec9500_decomp.json'))
noi = json.load(open(f'{W1}/ankleAB_c3_dec9500noise_decomp.json'))
bn = {a: json.load(open(f'{W2}/ankle{a}_c3_bneck9500_bottleneck.json')) for a in ('AB', 'RP')}
C = {'AB': '#f0961e', 'RP': '#2f9dff'}
fig, ax = plt.subplots(2, 2, figsize=(14, 9)); ax = ax.ravel()

# A - transient
ages = list(det['err_by_age']); x = np.arange(len(ages))
ax[0].bar(x - 0.2, [det['err_by_age'][a] for a in ages], 0.4, color='#7a7a85', label='deterministic (deployment)')
ax[0].bar(x + 0.2, [noi['err_by_age'][a] for a in ages], 0.4, color='#c0392b', label='+ exploration noise (training)')
ax[0].axhline(0.69, color='k', ls='--', lw=1.2); ax[0].text(0.6, 0.70, 'training metric 0.69 (also has obs noise + episode resets)', fontsize=9)
ax[0].set_ylim(0, 0.78)
ax[0].set_xticks(x); ax[0].set_xticklabels(ages); ax[0].set_xlabel('time since the command changed')
ax[0].set_ylabel('|cmd - v| xy  [m/s]'); ax[0].set_title('A. the first second after every command change costs 3x')
ax[0].legend(fontsize=9); ax[0].grid(alpha=.25, axis='y')

# B - by command magnitude
mags = list(det['err_by_mag']); x = np.arange(len(mags))
ax[1].bar(x - 0.2, [det['err_by_mag'][m] for m in mags], 0.4, color='#7a7a85', label='deterministic')
ax[1].bar(x + 0.2, [noi['err_by_mag'][m] for m in mags], 0.4, color='#c0392b', label='+ exploration noise')
ax[1].set_xticks(x); ax[1].set_xticklabels(mags); ax[1].set_xlabel('command magnitude |cmd_xy| [m/s]')
ax[1].set_ylabel('steady-state |cmd - v| [m/s]'); ax[1].set_title('B. the error lives in the corner of the command box')
ax[1].legend(fontsize=9); ax[1].grid(alpha=.25, axis='y')

# C - capability
labels = ['+0.8', '+1.2', '+1.6', '-1.2', 'lat 0.8', 'diag', '0.8+yaw']
keys = list(bn['AB'])
x = np.arange(len(keys))
for j, a in enumerate(('AB', 'RP')):
    reach = []
    for k in keys:
        v = bn[a][k]; cx, cy, _ = v['cmd']
        mag = np.hypot(cx, cy); got = np.hypot(v['vx'], v['vy'])
        reach.append(got / mag if mag > 1e-6 else np.nan)
    ax[2].bar(x + (j - 0.5) * 0.4, reach, 0.4, color=C[a], label=a)
ax[2].axhline(1.0, color='k', ls='--', lw=1)
ax[2].set_xticks(x); ax[2].set_xticklabels(labels); ax[2].set_ylabel('achieved / commanded speed')
ax[2].annotate('AB +0.8 = first block,\nstill accelerating from the reset', xy=(0, 0.74), xytext=(0.15, 0.35), fontsize=8,
               arrowprops=dict(arrowstyle='->', lw=0.8))
ax[2].set_title('C. held-command capability (15 s dwell, deterministic)'); ax[2].legend(fontsize=9); ax[2].grid(alpha=.25, axis='y')

# D - actuator utilisation vs T-N
for j, a in enumerate(('AB', 'RP')):
    u = []
    for k in keys:
        tops = bn[a][k]['top_saturating']
        u.append(max(t[2] for t in tops))          # util_p95 of the most loaded joint
    ax[3].bar(x + (j - 0.5) * 0.4, u, 0.4, color=C[a], label=f'{a}  (most loaded joint)')
ax[3].axhline(1.0, color='#c0392b', ls='--', lw=1.2); ax[3].text(0.1, 1.03, 'T-N limit', color='#c0392b', fontsize=9)
ax[3].set_xticks(x); ax[3].set_xticklabels(labels); ax[3].set_ylabel('torque p95 / T-N limit at that speed')
ax[3].set_title('D. RP ankle pitch reaches the motor curve, AB cranks do not'); ax[3].legend(fontsize=9); ax[3].grid(alpha=.25, axis='y')

fig.suptitle('Where Metrics/twist/error_vel_xy = 0.69 comes from (ankle AB/RP c3, model_9500)', fontsize=13)
fig.tight_layout(); fig.savefig(OUT, dpi=125, bbox_inches='tight'); print('wrote', OUT)
