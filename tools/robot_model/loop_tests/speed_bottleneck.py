"""Where does Metrics/twist/error_vel_xy come from? Decompose the tracking error by command
type and check what saturates (T-N torque roll-off, joint speed, stance duty).

The training metric is mean ||cmd_xy - v_xy|| over a uniform command box that includes
lateral +-1.0 m/s (never curriculum-ramped) and vx up to the current curriculum max, so a
single number hides which command is unreachable. This replays ONE checkpoint over a set of
held commands (15 s dwell each, docs rule) and reports, per command: achieved vx/vy, the
error the training metric would see, contact duty / strides, and per-joint utilisation
against the measured 48 V T-N curve (torque at the current speed) and the no-load speed.

  PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_SOFT_LANDING=1 PYG_ANKLE_MODE=AB \
  CUDA_VISIBLE_DEVICES="" .venv/bin/python3 ../../tools/robot_model/loop_tests/speed_bottleneck.py <run_dir> <ckpt> <tag>
"""
import os, sys, json
import numpy as np

D, CK, TAG = sys.argv[1:4]
OUT = '/home/syaro/pyg_fea/work/speed_bottleneck'; os.makedirs(OUT, exist_ok=True)
DWELL = 750                                   # 15 s at 50 Hz
CMDS = [(0.8, 0.0, 0.0), (1.2, 0.0, 0.0), (1.6, 0.0, 0.0), (-1.2, 0.0, 0.0),
        (0.0, 0.8, 0.0), (0.8, 0.8, 0.0), (0.8, 0.0, 1.0)]
sys.argv = ['measure_loads.py', '--run-dir', D, '--checkpoint', CK, '--tag', TAG, '--device', 'cpu',
            '--steps-per-cmd', str(DWELL), '--warmup', '150', '--out-dir', OUT]
sys.path.insert(0, 'analysis'); import measure_loads  # noqa: E402
measure_loads.COMMAND_SCHEDULE = CMDS
measure_loads.main()

import mujoco  # noqa: E402
from mjlab.asset_zoo.robots.pygmalion.pygmalion_constants import tn_curve, MOTOR_MEAS  # noqa: E402

d = np.load(f'{OUT}/{TAG}.npz'); BW = 346.8
m = mujoco.MjModel.from_binary_path(f'{OUT}/{TAG}_model.mjb')
# which motor family drives which joint (same map the constants use)
FAM = {'hip_pitch': 'RS04', 'hip_roll': 'RS04', 'hip_yaw': 'RS04', 'knee': 'RS04',
       'ankle_pitch': 'RS03', 'ankle_roll': 'RS03', 'crank_A': 'RS03', 'crank_B': 'RS03'}
curves = {f: np.array(tn_curve(f)) for f in set(FAM.values())}


def tn(f, w):
    c = curves[f]
    return np.interp(np.abs(w), c[:, 0], c[:, 1], left=c[0, 1], right=0.0)


joints = sorted({k[4:] for k in d.files if k.startswith('tau_') and 'rod' not in k})
res = {}
for n, (cx, cy, wz) in enumerate(CMDS):
    lo = n * DWELL + 60; hi = (n + 1) * DWELL          # drop the command-change transient
    sl = slice(lo, hi)
    vx, vy = d['base_vx'][sl], d['base_vy'][sl]
    err = float(np.mean(np.hypot(vx - cx, vy - cy)))
    on = {s: d[f'GRFc_{s}_foot_link_z'][sl] > 0.05 * BW for s in 'LR'}
    duty = float(np.mean([on[s].mean() for s in 'LR']))
    strides = float(np.mean([np.sum(np.diff(on[s].astype(int)) == 1) for s in 'LR']) / (len(vx) * 0.02))
    util = {}
    for j in joints:
        fam = next((f for k, f in FAM.items() if k in j), None)
        if fam is None: continue
        t = np.abs(d[f'tau_{j}'][sl]); w = np.abs(d[f'omega_{j}'][sl])
        lim = tn(fam, w)
        util[j] = dict(tau_p95=float(np.percentile(t, 95)),
                       util_p95=float(np.percentile(t / np.maximum(lim, 1e-6), 95)),
                       sat_frac=float(np.mean(t >= 0.9 * np.maximum(lim, 1e-6))),
                       w_p95=float(np.percentile(w, 95)),
                       w_frac_noload=float(np.percentile(w, 95) / (curves[fam][-1, 0])))
    top = sorted(util.items(), key=lambda kv: -kv[1]['sat_frac'])[:4]
    res[f'{cx},{cy},{wz}'] = dict(cmd=[cx, cy, wz], vx=float(np.mean(vx)), vy=float(np.mean(vy)),
                                  err_vel_xy=err, duty=duty, strides_per_s=strides,
                                  reach_frac=float(np.mean(vx) / cx) if abs(cx) > 1e-6 else None,
                                  top_saturating=[(k, round(v['sat_frac'], 3), round(v['util_p95'], 2),
                                                   round(v['w_frac_noload'], 2)) for k, v in top])
json.dump(res, open(f'{OUT}/{TAG}_bottleneck.json', 'w'), indent=1)
print('BOTTLENECK', json.dumps(res))
