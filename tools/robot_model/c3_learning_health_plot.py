"""Is c3 learning healthy? PPO diagnostics + gait-quality drift, both arms (docs/97)."""
import glob, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tensorboard.backend.event_processing import event_accumulator as ea

RUNS = {'AB': 'logs/rsl_rl/pygmalion_velocity/2026-08-24_03-22-35_ankleAB_c3',
        'RP': 'logs/rsl_rl/pygmalion_velocity/2026-08-24_03-22-58_ankleRP_c3'}
OUT = '/home/syaro/MikuchanRemote/Human-Pygmalion/docs/img/c3_learning_health.png'
C = {'AB': '#f0961e', 'RP': '#2f9dff'}
BOUNDS = {'vx 1.2': 4000, 'vx 1.6': 8000, 'DR start': 10000, 'vx 2.0': 12000}
PANELS = [
    ('Policy/mean_std', 'exploration sigma  (RISING, no annealing)', None),
    ('Loss/entropy', 'policy entropy  (1.2 -> 4.4)', None),
    ('Loss/learning_rate', 'adaptive LR (KL target 0.01)', None),
    ('Loss/value', 'value loss', None),
    ('Episode_Reward/track_linear_velocity', 'track_linear_velocity  (flat inside each stage)', 2.0),
    ('Episode_Reward/track_lin_vel_progress', 'track_lin_vel_progress  (only rising term)', None),
    ('Episode_Reward/action_rate_l2', 'action_rate_l2  (largest penalty, worsening)', None),
    ('Metrics/slip_velocity_mean', 'foot slip  (0.085 -> 0.165, 2x)', None),
    ('Metrics/contact_force_excess_mean', 'contact force over the 420 N cap', None),
    ('Episode_Reward/dof_pos_limits', 'dof_pos_limits penalty  (growing)', None),
    ('Episode_Termination/low_base', 'low_base terminations  (falls stay 0)', None),
    ('Curriculum/dr_levels/dr_factor', 'DR factor  (10k -> 20k ramp)', None),
]


def load(d):
    acc = ea.EventAccumulator(sorted(glob.glob(f'{d}/events.out.tfevents.*'))[0], size_guidance={'scalars': 0})
    acc.Reload()
    return acc


A = {k: load(v) for k, v in RUNS.items()}
fig, axes = plt.subplots(3, 4, figsize=(19, 9.5)); axes = axes.ravel()
for ax, (tag, title, hline) in zip(axes, PANELS):
    for k, acc in A.items():
        if tag not in acc.Tags()['scalars']: continue
        s = acc.Scalars(tag)
        st = np.array([x.step for x in s], float); v = np.array([x.value for x in s], float)
        w = 25
        sm = np.convolve(v, np.ones(w) / w, 'valid')
        ax.plot(st[w - 1:], sm, color=C[k], lw=1.4, label=k)
    for b, i in BOUNDS.items():
        ax.axvline(i, color='0.75', lw=0.9, ls='--')
        if ax is axes[0]: ax.text(i, ax.get_ylim()[1], b, fontsize=7, rotation=90, va='top', ha='right', color='0.4')
    if hline: ax.axhline(hline, color='0.5', lw=0.8, ls=':')
    ax.set_title(title, fontsize=10); ax.grid(alpha=.25); ax.tick_params(labelsize=8)
axes[0].legend(fontsize=9, loc='lower right')
fig.suptitle('ankle c3 learning health — warm start 3100, both arms, dashed = curriculum / DR boundary', fontsize=13)
fig.tight_layout(); fig.savefig(OUT, dpi=115, bbox_inches='tight'); print('wrote', OUT)
