"""Reward-hacking / gait-degeneration check for a checkpoint (docs/reward_research/2026-08-24_soft_landing_impact).
Runs measure_loads on 0 / 0.4 / 0.8 m/s (8 s each) and reports per command: tracking |vx err|, contact duty,
flight fraction (both feet off), mean swing (air) time, strides/s, stride length, swing apex height, foot slip
speed in stance, ankle pitch range, standing foot motion, low_base steps, plus the 50 Hz GRFc p99.
  PYG_... env as training; .venv/bin/python3 hack_check.py <run_dir> <ckpt> <tag>
"""
import sys, os, json, numpy as np
D, CK, TAG = sys.argv[1:4]; OUT = '/home/syaro/pyg_fea/work/hack_check'; os.makedirs(OUT, exist_ok=True)
sys.argv = ['measure_loads.py', '--run-dir', D, '--checkpoint', CK, '--tag', TAG, '--device', 'cpu', '--steps-per-cmd', '400', '--warmup', '100', '--out-dir', OUT]
sys.path.insert(0, 'analysis'); import measure_loads
measure_loads.COMMAND_SCHEDULE = [(0.0, 0.0, 0.0), (0.4, 0.0, 0.0), (0.8, 0.0, 0.0)]
measure_loads.main()
d = np.load(f'{OUT}/{TAG}.npz'); DT = 0.02; BW = 347.0
import mujoco
m = mujoco.MjModel.from_binary_path(f'{OUT}/{TAG}_model.mjb'); md = mujoco.MjData(m)
fid = {s: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f'robot/{s}_foot_link') for s in 'LR'}
res = {}
for cmd in (0.0, 0.4, 0.8):
    mk = np.abs(d['cmd_vx'] - cmd) < 1e-6; mk[:50] = False; idx = np.where(mk)[0]
    fz = {s: d[f'GRFc_{s}_foot_link_z'][idx] for s in 'LR'}; on = {s: fz[s] > 0.05 * BW for s in 'LR'}
    # foot positions from qpos replay
    fp = {s: [] for s in 'LR'}
    for i in idx:
        md.qpos[:] = d['qpos_full'][i]; mujoco.mj_kinematics(m, md)
        for s in 'LR': fp[s].append(md.xpos[fid[s]].copy())
    fp = {s: np.array(v) for s, v in fp.items()}
    r = {}
    r['vx_err'] = float(np.mean(np.abs(d['base_vx'][idx] - cmd)))
    r['contact_duty'] = float(np.mean([on[s].mean() for s in 'LR']))
    r['flight_frac'] = float(np.mean(~on['L'] & ~on['R']))
    swings = []; strides = []; apex = []
    for s in 'LR':
        o = on[s].astype(int); starts = np.where(np.diff(o) == -1)[0] + 1; ends = np.where(np.diff(o) == 1)[0] + 1
        for a in starts:
            b = ends[ends > a]
            if len(b): b = b[0]; swings.append((b - a) * DT); strides.append(float(np.linalg.norm(fp[s][b, :2] - fp[s][a, :2]))); apex.append(float(fp[s][a:b, 2].max() - fp[s][a, 2]))
    r['swing_time'] = float(np.mean(swings)) if swings else 0.0; r['strides_per_s'] = len(swings) / (len(idx) * DT) if swings else 0.0
    r['stride_len'] = float(np.mean(strides)) if strides else 0.0; r['swing_apex'] = float(np.mean(apex)) if apex else 0.0
    sl = []
    for s in 'LR':
        v = np.linalg.norm(np.diff(fp[s][:, :2], axis=0) / DT, axis=1); sl.append(v[on[s][1:]].mean() if on[s][1:].any() else 0.0)
    r['stance_slip'] = float(np.mean(sl))
    r['foot_motion'] = float(np.mean([np.linalg.norm(np.diff(fp[s], axis=0) / DT, axis=1).mean() for s in 'LR']))
    r['ankle_pitch_rng'] = float(np.degrees(np.percentile(d['qpos_L_ankle_pitch_joint'][idx], 95) - np.percentile(d['qpos_L_ankle_pitch_joint'][idx], 5)))
    r['grfc_p99_BW'] = float(max(np.percentile(fz[s], 99) for s in 'LR') / BW); r['low_base'] = int((d['base_height'][idx] < 0.45).sum())
    res[str(cmd)] = r
json.dump(dict(tag=TAG, ckpt=os.path.basename(CK), res=res), open(f'{OUT}/{TAG}_hack.json', 'w'), indent=1)
print('HACK', json.dumps(dict(tag=TAG, res=res)))
