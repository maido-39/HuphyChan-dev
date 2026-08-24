"""Per-reward-term trend analysis for the ankle A/B runs.

Pulls every Episode_Reward/* (and the diagnostic Metrics/*, Curriculum/*) series from the
TensorBoard event files of both arms, then for each term reports: current value, share of
the positive/negative budget, the change across each curriculum boundary, and the trend
over the last 2k iterations (linear fit). Produces a grid figure + a markdown table.

  .venv/bin/python3 ../../tools/robot_model/reward_trend_report.py
"""
import glob, json, os
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tensorboard.backend.event_processing import event_accumulator as ea

RUNS = {'AB': 'logs/rsl_rl/pygmalion_velocity/2026-08-24_03-22-35_ankleAB_c3',
        'RP': 'logs/rsl_rl/pygmalion_velocity/2026-08-24_03-22-58_ankleRP_c3'}
OUT_PNG = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img/c3_reward_trends.png'
OUT_MD = '/home/syaro/pyg_fea/work/c3_reward_trends.md'
# curriculum boundaries in ITERATIONS (warm start was at 3100)
BOUNDS = {'vx 1.2': 4000, 'vx 1.6': 8000, 'DR ramp': 10000, 'vx 2.0': 12000}
C = {'AB': '#f0961e', 'RP': '#2f9dff'}


def load(run_dir):
    out = {}
    for f in sorted(glob.glob(f'{run_dir}/events.out.tfevents.*')):
        acc = ea.EventAccumulator(f, size_guidance={'scalars': 0}); acc.Reload()
        for t in acc.Tags()['scalars']:
            s = acc.Scalars(t)
            st = np.array([x.step for x in s], float); v = np.array([x.value for x in s], float)
            if t in out:
                out[t] = (np.concatenate([out[t][0], st]), np.concatenate([out[t][1], v]))
            else:
                out[t] = (st, v)
    return out


def at(series, it, w=100):
    st, v = series
    m = np.abs(st - it) <= w
    return float(np.mean(v[m])) if m.any() else float('nan')


def slope_per_1k(series, lo, hi):
    st, v = series
    m = (st >= lo) & (st <= hi)
    if m.sum() < 10: return float('nan')
    return float(np.polyfit(st[m], v[m], 1)[0] * 1000)


D = {k: load(v) for k, v in RUNS.items()}
terms = sorted({t for d in D.values() for t in d if t.startswith('Episode_Reward/')})
last = int(min(D[a]['Episode_Reward/track_linear_velocity'][0].max() for a in D))
rows = []
for t in terms:
    name = t.split('/', 1)[1]
    r = {'term': name}
    for a in D:
        if t not in D[a]: continue
        s = D[a][t]
        r[f'{a}_now'] = at(s, last)
        r[f'{a}_3200'] = at(s, 3200)
        r[f'{a}_slope'] = slope_per_1k(s, max(3100, last - 2000), last)
        for bn, bi in BOUNDS.items():
            if bi < last - 150:
                r[f'{a}_d_{bn}'] = at(s, bi + 400) - at(s, bi - 400)
    rows.append(r)
pos = sum(max(r.get('AB_now', 0), 0) for r in rows); neg = sum(min(r.get('AB_now', 0), 0) for r in rows)
for r in rows:
    v = r.get('AB_now', 0)
    r['share'] = v / (pos if v > 0 else -neg) * 100 if (pos and neg) else float('nan')
rows.sort(key=lambda r: -abs(r.get('AB_now', 0)))

with open(OUT_MD, 'w') as f:
    f.write(f'| term | AB now | RP now | AB @3200 | AB slope /1k | share % | ' +
            ' | '.join(f'AB Δ{b}' for b in BOUNDS if BOUNDS[b] < last - 150) + ' |\n')
    f.write('|---' * (6 + sum(1 for b in BOUNDS if BOUNDS[b] < last - 150)) + '|\n')
    for r in rows:
        cells = [r['term'], f"{r.get('AB_now', float('nan')):+.3f}", f"{r.get('RP_now', float('nan')):+.3f}",
                 f"{r.get('AB_3200', float('nan')):+.3f}", f"{r.get('AB_slope', float('nan')):+.4f}",
                 f"{r.get('share', float('nan')):.1f}"]
        cells += [f"{r.get(f'AB_d_{b}', float('nan')):+.3f}" for b in BOUNDS if BOUNDS[b] < last - 150]
        f.write('| ' + ' | '.join(cells) + ' |\n')

n = len(terms); cols = 4; rowsn = int(np.ceil((n + 4) / cols))
fig, axes = plt.subplots(rowsn, cols, figsize=(4.2 * cols, 2.5 * rowsn))
axes = axes.ravel()
extra = ['Metrics/twist/error_vel_xy', 'Metrics/foot_impact_vel_mean',
         'Curriculum/dr_levels/dr_factor', 'Policy/mean_noise_std']
for i, t in enumerate(terms + extra):
    ax = axes[i]
    for a in D:
        if t not in D[a]: continue
        st, v = D[a][t]
        k = max(1, len(v) // 400)
        ax.plot(st[::k], np.convolve(v, np.ones(20) / 20, 'same')[::k], color=C[a], lw=1.2, label=a)
    for bn, bi in BOUNDS.items():
        if bi <= last: ax.axvline(bi, color='0.7', lw=0.8, ls='--')
    ax.set_title(t.split('/', 1)[1] if '/' in t else t, fontsize=9)
    ax.tick_params(labelsize=7); ax.grid(alpha=.2)
    if i == 0: ax.legend(fontsize=7)
for j in range(len(terms) + len(extra), len(axes)): axes[j].axis('off')
fig.suptitle(f'ankle c3 reward-term trends, warm start 3100 -> iter {last} (dashed = curriculum boundary)', fontsize=12)
fig.tight_layout(); fig.savefig(OUT_PNG, dpi=110, bbox_inches='tight')
print('wrote', OUT_PNG, 'and', OUT_MD, '| last iter', last)
