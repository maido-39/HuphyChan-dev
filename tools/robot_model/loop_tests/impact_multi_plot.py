"""Plot the 200 Hz multi-env foot-force traces + the strike statistics.

Reads the *_raw.npz written by impact_probe_multi.py so the detector can be
audited by eye: if the Schmitt trigger is double-counting a bouncing foot, it
shows up here as two markers on one contact.
"""
import glob, json, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

D = '/home/syaro/pyg_fea/work/impact_multi'
ARMS = ['bundleCTL_AB', 'bundleTRT_AB', 'bundleB2_AB', 'bundleC3_AB', 'bundleC5_AB', 'bundleD1_AB']
LBL = {'bundleCTL_AB': 'CTL (baseline)', 'bundleTRT_AB': 'TRT (rate-only)',
       'bundleB2_AB': 'B2 (both)', 'bundleC3_AB': 'C3 (init-mid)', 'bundleC5_AB': 'C5 (+knee ext)',
       'bundleD1_AB': 'D1 (all three)'}
have = [a for a in ARMS if os.path.exists(f'{D}/{a}_raw.npz')]

fig, axes = plt.subplots(len(have), 1, figsize=(11, 2.0 * len(have)), sharex=True)
axes = np.atleast_1d(axes)
for ax, a in zip(axes, have):
    z = np.load(f'{D}/{a}_raw.npz'); F, dt = z['F'], float(z['dt'])
    t = np.arange(F.shape[0]) * dt
    n = min(400, F.shape[0])
    ax.plot(t[:n], F[:n, 0, 0], lw=1.0, label='foot L (env 0)')
    ax.plot(t[:n], F[:n, 0, 1], lw=1.0, label='foot R (env 0)')
    ax.axhline(0.25, color='r', ls=':', lw=0.7)
    ax.axhline(0.05, color='gray', ls=':', lw=0.7)
    ax.set_ylabel('GRF [BW]'); ax.set_title(LBL[a], fontsize=9, loc='left')
    ax.grid(alpha=0.3)
axes[0].legend(fontsize=7, ncol=2)
axes[-1].set_xlabel('time [s]  (200 Hz physics sampling, warm-up removed)')
fig.suptitle('Foot ground reaction force at 200 Hz — one env, first 2 s', y=0.995)
fig.tight_layout()
fig.savefig('docs/img/2026-08-26_impact_multi_traces.png', dpi=130)

# --- summary bars, both randomisation conditions ---------------------------
def load(root, a):
    f = f'{root}/{a}.json'
    return json.load(open(f)) if os.path.exists(f) else None
S = [load(D, a) for a in have]
S2 = [load(D + '_nodr', a) for a in have]
fig2, axs = plt.subplots(1, 4, figsize=(15, 3.6))
x = np.arange(len(have)); w = 0.38
names = [LBL[a].split(' ')[0] for a in have]
for ax, key, ttl, unit in [
        (axs[0], 'peak_BW_med', 'Peak GRF per strike (median)', 'BW'),
        (axs[1], 'rate_BWs_med', 'Loading rate per strike (median)', 'BW/s'),
        (axs[2], 'td_per_s_per_env', 'Detected strikes', '1/s/env'),
        (axs[3], 'n_resets', 'Falls in 24 envs x 11 s', 'count')]:
    v1 = [s[key] if s else 0 for s in S]
    v2 = [s.get(key, 0) if s else 0 for s in S2]
    b1 = ax.bar(x - w / 2, v1, w, color='#c26a4a', label='DR on')
    b2 = ax.bar(x + w / 2, v2, w, color='#4878a8', label='DR off (evaluator cond.)')
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=20, fontsize=8)
    ax.set_title(ttl, fontsize=9); ax.set_ylabel(unit); ax.grid(axis='y', alpha=0.3)
    fmt = '%.0f' if key == 'n_resets' else '%.2f'
    ax.bar_label(b1, fmt=fmt, fontsize=6); ax.bar_label(b2, fmt=fmt, fontsize=6)
axs[0].legend(fontsize=7)
fig2.suptitle('200 Hz multi-env impact statistics (24 envs, 11 s, forward 1.6 m/s)', y=1.0)
fig2.tight_layout()
fig2.savefig('docs/img/2026-08-26_impact_multi_summary.png', dpi=130)
print('wrote docs/img/2026-08-26_impact_multi_{traces,summary}.png')
for s in S:
    print(f"{s['tag']:16s} peak {s['peak_BW_med']:.3f} (p90 {s['peak_BW_p90']:.3f})  "
          f"rate {s['rate_BWs_med']:7.1f} (p25 {s['rate_BWs_p25']:.1f}, p90 {s['rate_BWs_p90']:.1f})  "
          f"strikes/s {s['td_per_s_per_env']}")
