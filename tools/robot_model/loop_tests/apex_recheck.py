"""Independent re-check of swing apex at ONE held command (no preceding blocks).

hack_check runs 0 -> 0.4 -> 0.8 back to back with no reset, so a stalled mode at one
command carries into the next. This runs a single command from a fresh warm-up, which is
the honest test of the soft-landing swing-height threshold (docs/95 §7).
  PYG_... as training; .venv/bin/python3 apex_recheck.py <run_dir> <ckpt> <tag> [vx]
"""
import sys, os, json, numpy as np
D, CK, TAG = sys.argv[1:4]
VX = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8
OUT = '/home/syaro/pyg_fea/work/apex_recheck'; os.makedirs(OUT, exist_ok=True)
sys.argv = ['measure_loads.py', '--run-dir', D, '--checkpoint', CK, '--tag', TAG, '--device', 'cpu',
            '--steps-per-cmd', '750', '--warmup', '250', '--out-dir', OUT]
sys.path.insert(0, 'analysis'); import measure_loads
measure_loads.COMMAND_SCHEDULE = [(VX, 0.0, 0.0)]
measure_loads.main()
import mujoco
d = np.load(f'{OUT}/{TAG}.npz'); BW = 346.8
m = mujoco.MjModel.from_binary_path(f'{OUT}/{TAG}_model.mjb'); md = mujoco.MjData(m)
fid = {s: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f'robot/{s}_foot_link') for s in 'LR'}
idx = np.arange(60, len(d['cmd_vx']))
fp = {s: [] for s in 'LR'}
for i in idx:
    md.qpos[:] = d['qpos_full'][i]; mujoco.mj_kinematics(m, md)
    for s in 'LR': fp[s].append(md.xpos[fid[s]][2])
on = {s: d[f'GRFc_{s}_foot_link_z'][idx] > 0.05 * BW for s in 'LR'}
apex, apex_lo = [], []
for s in 'LR':
    z = np.array(fp[s]); air = ~on[s]
    e = np.diff(air.astype(int)); starts = np.where(e == 1)[0] + 1; ends = np.where(e == -1)[0] + 1
    for a in starts:
        b = ends[ends > a]
        if len(b):
            apex.append(float(z[a:b[0]].max() - z[on[s]].mean()))     # vs mean stance height
            apex_lo.append(float(z[a:b[0]].max() - z[a]))             # hack_check definition (vs lift-off)
r = dict(tag=TAG, vx=VX, n_swings=len(apex), apex_mean=float(np.mean(apex)) if apex else 0.0,
         apex_liftoff=float(np.mean(apex_lo)) if apex_lo else 0.0,  # same definition as hack_check
         apex_p90=float(np.percentile(apex, 90)) if apex else 0.0,
         duty=float(np.mean([on[s].mean() for s in 'LR'])),
         vx_err=float(np.mean(np.abs(d['base_vx'][idx] - VX))),
         strides_per_s=float(np.mean([np.sum(np.diff(on[s].astype(int)) == 1) for s in 'LR']) / (len(idx) * 0.02)))
json.dump(r, open(f'{OUT}/{TAG}.json', 'w'), indent=1); print('APEX', json.dumps(r))
