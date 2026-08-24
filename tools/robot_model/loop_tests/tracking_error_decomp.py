"""Reproduce the training metric Metrics/twist/error_vel_xy offline and split it into
TRANSIENT (just after a command change) vs STEADY-STATE, and by command type.

Training samples a new command every 3-8 s from the curriculum box and averages
||cmd_xy - v_xy|| over the whole window, so a slow acceleration response inflates the
number even when the held-command tracking is good. Here: 24 random commands from the
current box, 5.5 s each (the training mean), long warm-up so the robot is already walking.

  PYG_... as training; .venv/bin/python3 tracking_error_decomp.py <run_dir> <ckpt> <tag> [vxmax]
"""
import os, sys, json
import numpy as np

D, CK, TAG = sys.argv[1:4]
VXMAX = float(sys.argv[4]) if len(sys.argv) > 4 else 1.6
OUT = '/home/syaro/pyg_fea/work/track_decomp'; os.makedirs(OUT, exist_ok=True)
DW = 275                                        # 5.5 s at 50 Hz = mean training window
rng = np.random.default_rng(0)
cmds = []
for k in range(24):
    if k % 10 == 3:                             # 10 % standing envs, as in training
        cmds.append((0.0, 0.0, 0.0)); continue
    cmds.append((float(rng.uniform(-VXMAX, VXMAX)), float(rng.uniform(-1.0, 1.0)), float(rng.uniform(-1.0, 1.0))))

sys.argv = ['measure_loads.py', '--run-dir', D, '--checkpoint', CK, '--tag', TAG, '--device', 'cpu',
            '--steps-per-cmd', str(DW), '--warmup', '400', '--out-dir', OUT]
sys.path.insert(0, 'analysis'); import measure_loads  # noqa: E402
measure_loads.COMMAND_SCHEDULE = cmds
measure_loads.main()

d = np.load(f'{OUT}/{TAG}.npz')
vx, vy = d['base_vx'], d['base_vy']
err = np.full(len(vx), np.nan); age = np.zeros(len(vx))
rows = []
for n, (cx, cy, wz) in enumerate(cmds):
    sl = slice(n * DW, (n + 1) * DW)
    e = np.hypot(vx[sl] - cx, vy[sl] - cy)
    err[sl] = e; age[sl] = np.arange(len(e)) * 0.02
    rows.append(dict(cmd=[round(cx, 2), round(cy, 2), round(wz, 2)], mag=float(np.hypot(cx, cy)),
                     err_window=float(e.mean()), err_first2s=float(e[:100].mean()), err_after2s=float(e[100:].mean()),
                     vx=float(vx[sl].mean()), vy=float(vy[sl].mean())))
res = dict(
    err_all=float(np.nanmean(err)),
    err_by_age={f'{a}-{a+1}s': float(np.nanmean(err[(age >= a) & (age < a + 1)])) for a in range(6)},
    err_first2s=float(np.nanmean(err[age < 2])), err_after2s=float(np.nanmean(err[age >= 2])),
    frac_time_first2s=float(np.mean(age < 2)),
    err_by_mag={b: float(np.nanmean([r['err_after2s'] for r in rows if lo <= r['mag'] < hi]) if any(lo <= r['mag'] < hi for r in rows) else np.nan)
                for b, (lo, hi) in {'0-0.5': (0, .5), '0.5-1.0': (.5, 1.), '1.0-1.5': (1., 1.5), '1.5+': (1.5, 9)}.items()},
    windows=rows)
json.dump(res, open(f'{OUT}/{TAG}_decomp.json', 'w'), indent=1)
print('DECOMP', json.dumps({k: v for k, v in res.items() if k != 'windows'}))
