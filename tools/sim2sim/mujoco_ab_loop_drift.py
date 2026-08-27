"""The MuJoCo half of the loop-drift question: how far does the closure open while WALKING?

The static cross-engine note measured 0.0003 mm at rest, which is the wrong load case - the
interesting one is the landing impact. The Isaac side of that measurement means nothing without
its MuJoCo twin, because MuJoCo's `<equality><connect>` is not a hard constraint either: it is a
soft constraint with `solref/solimp`, and the v3 loop XML deliberately stiffens it
(solimp 0.999 0.9999 1e-4) precisely because the default was too soft (docs/91 s4).

So this runs the SAME policy in plain MuJoCo, with the same PD + T-N clamp the mjlab actuator
applies (motor-type actuators: mjlab computes the torque in Python and writes it to ctrl, so
reproducing it here is a transcription, not a reimplementation of a solver), and records the
site-to-site distance of all four closures every physics substep - the same quantity, computed
the same way, as the Isaac script's `loop_drift_mm`.

  PYG_V2=1 PYG_ANKLE_MODE=AB PYG_INIT_BENT=1 PYG_INIT_MID=1 PYG_ARM_ABD_DEG=15 PYG_TN=1 \\
  PYG_MOTOR_MEAS=1 CUDA_VISIBLE_DEVICES="" mujoco-sim/mjlab/.venv/bin/python3 \\
      tools/sim2sim/mujoco_ab_loop_drift.py [seconds]
"""
import json
import os
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import onnxruntime as rt

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
sys.path.insert(0, f'{REPO}/tools/sim2sim')
CONTRACT = '/home/syaro/pyg_fea/work/ab_policy_contract.json'
ONNX = (f'{REPO}/mujoco-sim/mjlab/logs/rsl_rl/pygmalion_velocity/'
        '2026-08-26_15-02-37_bundleD1_AB/2026-08-26_15-02-37_bundleD1_AB.onnx')
MJCF = (f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/'
        'pygmalion_v3_printed_loop.xml')
OUT = '/home/syaro/pyg_fea/work/ab_rollout/mujoco_ab_loop_drift.json'
SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
CMD = [1.6, 0.0, 0.0]
WARM = 3.0

C = json.load(open(CONTRACT))
act_names, obs_names = C['action_joint_names'], C['obs_joint_names']
q0_all = C['default_q']
kp = np.array([C['gains_sw'][n]['kp'] for n in act_names])
kd = np.array([C['gains_sw'][n]['kd'] for n in act_names])
frc = np.array([abs(C['gains'][n]['forcerange'][1]) for n in act_names])
tn_w = {f: np.array([w for w, _ in p]) for f, p in C['tn_curves'].items()}
tn_t = {f: np.array([t for _, t in p]) for f, p in C['tn_curves'].items()}
fam_of = [C['joint_family'][n] for n in act_names]
scale = 0.25
decim, dt_phys, dt_ctrl = C['decimation'], C['physics_dt'], C['step_dt']

# THE MODEL MUST COME FROM THE ENV, not from get_spec().compile(). Measured, not assumed:
# the raw spec has nu=0 (mjlab attaches the actuators from the EntityCfg), timestep 0.002
# (the env overrides it to 0.005), no collision config on the feet, and - fatally - NO FLOOR,
# so the robot free-falls from 0.9 m to 0.39 m in 0.8 s and every statistic is taken on an
# empty window. Building the env is 40 s and gives the exact model the policy trained in.
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa: F401
_cfg = load_env_cfg('Mjlab-Velocity-Flat-Pygmalion', play=True)
_cfg.scene.num_envs = 1
_env = ManagerBasedRlEnv(cfg=_cfg, device='cpu')
m = _env.sim.mj_model
d = mujoco.MjData(m)
if abs(float(m.opt.timestep) - dt_phys) > 1e-12:
    raise SystemExit(f'env timestep {m.opt.timestep} != contract {dt_phys}')
PFX = 'robot/'


def _jid(name):
    return m.joint(PFX + name) if PFX + name in [m.joint(i).name for i in range(m.njnt)] \
        else m.joint(name)

# the four closures, and the sites they hold together
con = ET.parse(MJCF).getroot()
pairs = [(c.get('name'), c.get('site1'), c.get('site2'))
         for eq in con.iter('equality') for c in eq.findall('connect')]
sid = {}
for nm, s1, s2 in pairs:
    for s in (s1, s2):
        i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, PFX + s)
        if i < 0:
            i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, s)
        if i < 0:
            raise SystemExit(f'site {s} not in the env model')
        sid[s] = i

jadr = {}
for jn in C['joint_names']:
    j = _jid(jn)
    jadr[jn] = (m.jnt_qposadr[j.id], m.jnt_dofadr[j.id])
# get_spec() carries the ROBOT, not the actuators - mjlab attaches those from the EntityCfg at
# env build time. The 12 are motor-type with gain 1 (contract: gainprm [1,0,0]), so writing the
# torque into qfrc_applied on the same DOF is the identical operator, and it needs no actuator.
a_qpos = np.array([jadr[n][0] for n in act_names])
a_dof = np.array([jadr[n][1] for n in act_names])
o_qpos = np.array([jadr[n][0] for n in obs_names])
o_dof = np.array([jadr[n][1] for n in obs_names])
q0_act = np.array([q0_all[n] for n in act_names])
q0_obs = np.array([q0_all[n] for n in obs_names])


def tn_clamp(tau, omega):
    out = np.empty_like(tau)
    for i, fam in enumerate(fam_of):
        peak = tn_t[fam][0]
        hi = np.interp(omega[i], tn_w[fam], tn_t[fam]) if omega[i] >= 0 else peak
        lo = -(np.interp(-omega[i], tn_w[fam], tn_t[fam]) if omega[i] < 0 else peak)
        out[i] = min(max(tau[i], lo), hi)
    return out


def quat_rot_inv(q, v):
    w, x, y, z = q
    u = np.array([x, y, z])
    return v + 2.0 * np.cross(u, np.cross(u, v) - w * v)


mujoco.mj_resetData(m, d)
d.qpos[:] = m.qpos0
for jn, q in q0_all.items():
    d.qpos[jadr[jn][0]] = q
_free = [j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE]
if len(_free) != 1:
    raise SystemExit(f'expected exactly one free joint, found {len(_free)}')
_fa = m.jnt_qposadr[_free[0]]
d.qpos[_fa:_fa + 3] = [0.0, 0.0, C['spawn_base_z']]
d.qpos[_fa + 3:_fa + 7] = [1.0, 0.0, 0.0, 0.0]
mujoco.mj_forward(m, d)

gyro = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SENSOR, PFX + 'imu_ang_vel')
if gyro < 0:
    gyro = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SENSOR, 'imu_ang_vel')
g_adr = m.sensor_adr[gyro]
sess = rt.InferenceSession(ONNX)
last_act = np.zeros(12, dtype=np.float32)
g_w = np.array([0.0, 0.0, -1.0])
D, VX, BZ = [], [], []
fell = False

for k in range(int(SECONDS / dt_ctrl)):
    quat = d.qpos[_fa + 3:_fa + 7].copy()
    ang_b = d.sensordata[g_adr:g_adr + 3].copy()
    grav_b = quat_rot_inv(quat, g_w)
    q_rel = d.qpos[o_qpos] - q0_obs
    cmd_now = [CMD[0] * min(1.0, k * dt_ctrl / 2.0), CMD[1], CMD[2]]
    obs = np.concatenate([ang_b, grav_b, q_rel, d.qvel[o_dof], last_act,
                          cmd_now]).astype(np.float32)
    act = sess.run(None, {'obs': obs.reshape(1, -1)})[0].flatten()
    last_act = act.copy()
    q_t = q0_act + scale * act
    for _ in range(decim):
        raw = np.clip(kp * (q_t - d.qpos[a_qpos]) - kd * d.qvel[a_dof], -frc, frc)
        d.qfrc_applied[:] = 0.0
        d.qfrc_applied[a_dof] = tn_clamp(raw, d.qvel[a_dof])
        mujoco.mj_step(m, d)
        D.append([np.linalg.norm(d.site_xpos[sid[s1]] - d.site_xpos[sid[s2]]) * 1e3
                  for _, s1, s2 in pairs])
    VX.append(float(quat_rot_inv(d.qpos[_fa + 3:_fa + 7], d.qvel[0:3])[0]))
    BZ.append(float(d.qpos[_fa + 2]))
    if d.qpos[_fa + 2] < 0.45:
        fell = True
        break

D = np.asarray(D)
w0 = int(WARM / dt_phys)
Dw = D[w0:]
vx = np.array(VX[int(2.0 / dt_ctrl):])
out = dict(
    engine='MuJoCo (plain, mjlab-compiled v3 loop model)', seconds=len(VX) * dt_ctrl,
    fell=fell, vx_mean=float(vx.mean()), vx_err=float(np.mean(np.abs(vx - CMD[0]))),
    base_z_mean=float(np.mean(BZ)), total_mass_kg=round(float(m.body_mass.sum()), 5),
    timestep=float(m.opt.timestep), solver=int(m.opt.solver), solver_iterations=int(m.opt.iterations),
    solref=[float(x) for x in m.eq_solref[0]], solimp=[float(x) for x in m.eq_solimp[0]],
    loop_drift_mm=dict(
        per_joint={nm: dict(mean=round(float(Dw[:, i].mean()), 6),
                            p99=round(float(np.percentile(Dw[:, i], 99)), 6),
                            max=round(float(Dw[:, i].max()), 6))
                   for i, (nm, _, _) in enumerate(pairs)},
        all_mean=round(float(Dw.mean()), 6), all_p99=round(float(np.percentile(Dw, 99)), 6),
        all_max=round(float(Dw.max()), 6)),
    torque_path='qfrc_applied on the 12 motor DOFs (motor actuator, gain 1)',
    note='site-to-site distance of each <connect>, every physics substep, warm-up cut')
json.dump(out, open(OUT, 'w'), indent=1)
print(json.dumps(out, indent=1))
