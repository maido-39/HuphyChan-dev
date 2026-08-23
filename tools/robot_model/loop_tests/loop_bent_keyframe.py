"""Solve the loop-consistent bent keyframe: hip -0.32 / knee -0.67 / ankle_pitch +0.36 (the
KNEES_BENT pose) -> crank and rod angles that close the loop at that ankle pose. Plain MuJoCo,
root welded, cranks servoed by PD, ankle driven by a temporary stiff PD to the target."""
import sys, json, numpy as np, mujoco
sys.path.insert(0, '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/robot_model')
import loop_ankle_verify as LV
m = LV.load('pygmalion_v3_printed_loop', weld_shin=False, floor=False)
d = mujoco.MjData(m)
# weld the root: easiest = put the robot high and zero gravity
m.opt.gravity[:] = 0
LV.home(m, d, 1.5)
tgt = {'hip_pitch': -0.32, 'knee': -0.67, 'ankle_pitch': 0.36}
for s in 'LR':
    for k, v in tgt.items():
        d.qpos[LV.jid(m, f'{s}_{k}_joint')] = v
# servo: cranks via ctrl; pull the ankle to the target with qfrc_applied PD, iterate the crank target
aids = {n: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, n) for n in [a for a in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_ACTUATOR, i) for i in range(m.nu))]}
print('actuators', list(aids))
def step(n, crank):
    for _ in range(n):
        for s in 'LR':
            for t in 'AB':
                j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'{s}_crank_{t}_joint')
                qa = m.jnt_qposadr[j]; va = m.jnt_dofadr[j]
                d.qfrc_applied[va] = 22.3 * (crank[s] - d.qpos[qa]) - 1.41 * d.qvel[va]
            for k, v in tgt.items():
                j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'{s}_{k}_joint')
                qa = m.jnt_qposadr[j]; va = m.jnt_dofadr[j]
                d.qfrc_applied[va] = 400 * (v - d.qpos[qa]) - 8 * d.qvel[va]
            j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'{s}_hip_roll_joint'); d.qfrc_applied[m.jnt_dofadr[j]] = -400 * d.qpos[m.jnt_qposadr[j]]
            j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'{s}_hip_yaw_joint'); d.qfrc_applied[m.jnt_dofadr[j]] = -400 * d.qpos[m.jnt_qposadr[j]]
        mujoco.mj_step(m, d)
crank = {'L': -0.36 / 1.22, 'R': -0.36 / 1.22}
for it in range(30):
    step(1500, crank)
    for s in 'LR':
        p = d.qpos[LV.jid(m, f'{s}_ankle_pitch_joint')]
        crank[s] += (0.36 - p) / -1.22 * 2.0
    if it % 5 == 4 or it == 29:
        print(f'iter {it}: ' + '  '.join(f'{s}: ankle pitch {np.degrees(d.qpos[LV.jid(m, f"{s}_ankle_pitch_joint")]):+.2f} roll {np.degrees(d.qpos[LV.jid(m, f"{s}_ankle_roll_joint")]):+.2f} crankA {np.degrees(d.qpos[LV.jid(m, f"{s}_crank_A_joint")]):+.2f} closure {LV.closure_err(m, d, s) * 1000:.3f} mm' for s in 'LR'))
out = {}
for s in 'LR':
    for n in ('crank_A_joint', 'rod_A_u1', 'rod_A_u2', 'crank_B_joint', 'rod_B_u1', 'rod_B_u2', 'ankle_pitch_joint', 'ankle_roll_joint', 'hip_pitch_joint', 'knee_joint'):
        out[f'{s}_{n}'] = round(float(d.qpos[LV.jid(m, f'{s}_{n}')]), 5)
cl = max(LV.closure_err(m, d, s) for s in 'LR')
res = dict(pose='KNEES_BENT (hip_pitch -0.32, knee -0.67, ankle_pitch +0.36)', closure_mm=round(cl * 1000, 4), joint_pos=out)
json.dump(res, open('/home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion/assets/pygmalion_v2/pygmalion_v3_printed_loop_bent.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
