"""Dump the AB (closed-loop ankle) policy's port contract, in ONE pass.

The RP contract was built by four incremental patches, and each pass rewrote the whole file -
so a field added by one pass vanished when an earlier pass was re-run (the gains_sw incident,
docs/sim2sim/2026-08-27_xengine_dynamic_rollout.md). This script writes every field at once.

What is different about AB, and why the RP contract cannot simply be renamed:
  * the ACTION space is hips + knees + CRANKS. The ankle pitch/roll hinges have no motor at
    all; they are dragged by the two push rods.
  * the OBSERVED joint set is NOT the action set. It is hips + knees + cranks + ankles (16),
    because the hardware can compute the ankle angles from the crank encoders through the
    mechanism, so the pose reward keeps shaping the foot. obs = 3+3+16+16+12+3 = 53, not the
    45 of a serial robot.
  * there are 29 DOFs in the model, not 12: 8 rod universal hinges close the loop. Every one
    of them needs its armature/damping/frictionloss, and every one of them must be written on
    reset (IsaacLab #1250: setting only the driven subset tears the closure open).

Run with the same toggles the policy trained under (run_landing_bundle_test.sh AB):
  PYG_V2=1 PYG_ANKLE_MODE=AB PYG_INIT_BENT=1 PYG_INIT_MID=1 PYG_ARM_ABD_DEG=15
  PYG_TN=1 PYG_MOTOR_MEAS=1
  mujoco-sim/mjlab/.venv/bin/python3 tools/sim2sim/dump_contract_ab.py
"""
import json
import os

import numpy as np
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa: F401

OUT = '/home/syaro/pyg_fea/work/ab_policy_contract.json'

cfg = load_env_cfg('Mjlab-Velocity-Flat-Pygmalion', play=True)
cfg.scene.num_envs = 1
env = ManagerBasedRlEnv(cfg=cfg, device='cpu')
robot = env.scene['robot']
m = env.sim.mj_model

names = list(robot.joint_names)                 # every DOF, model order
default_q = np.asarray(robot.data.default_joint_pos[0]).flatten()

# --- action order: the action term's own resolved target list, not the model order ----------
term = env.action_manager._terms['joint_pos']
act_names = list(term._target_names)
scale = term.cfg.scale
scale_val = (float(scale) if isinstance(scale, (int, float))
             else {k: float(v) for k, v in scale.items()})

# --- observation order: resolve the obs term's asset_cfg against the scene ------------------
obs_term = env.observation_manager._group_obs_term_cfgs['actor'][
    env.observation_manager._group_obs_term_names['actor'].index('joint_pos')]
acfg = obs_term.params['asset_cfg']
obs_ids = acfg.joint_ids
if isinstance(obs_ids, slice):
    obs_names = names[obs_ids]
else:
    obs_names = [names[i] for i in obs_ids]

# --- gains: the PD lives in the mjlab actuator objects (the T-N clamp path), not mjModel ----
import re
gains_sw, fam_of = {}, {}
for act in robot.actuators:
    pats = list(getattr(act.cfg, 'target_names_expr', []))
    kp = np.asarray(act.stiffness).flatten()
    kd = np.asarray(act.damping).flatten()
    matched = [n for n in names if any(re.fullmatch(p, n) for p in pats)]
    for k, jn in enumerate(matched):
        gains_sw[jn] = dict(kp=round(float(kp[k] if kp.size > 1 else kp[0]), 4),
                            kd=round(float(kd[k] if kd.size > 1 else kd[0]), 4))

gains = {}
for jn in names:
    jid = m.joint(f'robot/{jn}').id
    for a in range(m.nu):
        if m.actuator_trnid[a, 0] == jid:
            gains[jn] = dict(forcerange=[round(float(x), 3) for x in m.actuator_forcerange[a]],
                             gainprm=[round(float(x), 4) for x in m.actuator_gainprm[a, :3]],
                             biasprm=[round(float(x), 4) for x in m.actuator_biasprm[a, :3]])
            break

# --- per-DOF armature / damping / frictionloss for ALL 29, URDF cannot carry any of them ----
dofp = {}
for jn in names:
    dof = m.jnt_dofadr[m.joint(f'robot/{jn}').id]
    dofp[jn] = dict(armature=round(float(m.dof_armature[dof]), 8),
                    damping=round(float(m.dof_damping[dof]), 8),
                    frictionloss=round(float(m.dof_frictionloss[dof]), 8))

# --- T-N curves, exactly as pygmalion_constants builds them (rad/s, no-load point appended) -
from mjlab.asset_zoo.robots.pygmalion import pygmalion_constants as PC
tn = {f: [[round(float(w), 4), round(float(t), 3)] for w, t in PC.tn_curve(f)]
      for f in ('RS03', 'RS04')}
for jn in act_names:
    fam_of[jn] = 'RS03' if ('crank' in jn or 'hip_yaw' in jn) else 'RS04'

# --- spawn height: the lowest point of the two sole boxes at the init pose ------------------
# mjlab spawns from the keyframe, but the keyframe z is the CAD standing height; what Isaac
# needs is the height that puts the soles exactly on the plane in THIS pose (the 0.42 s fall
# in the RP port was this number being guessed).
import mujoco
d = mujoco.MjData(m)
d.qpos[:] = m.qpos0
qadr = {jn: m.jnt_qposadr[m.joint(f'robot/{jn}').id] for jn in names}
for jn, q in zip(names, default_q):
    d.qpos[qadr[jn]] = q
base_free = m.jnt_qposadr[0]
d.qpos[base_free:base_free + 3] = [0.0, 0.0, 1.0]
d.qpos[base_free + 3:base_free + 7] = [1.0, 0.0, 0.0, 0.0]
mujoco.mj_forward(m, d)
zmin = 1e9
sole = []
for g in range(m.ngeom):
    gname = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g)
    if gname is None or 'foot' not in gname or 'collision' not in gname:
        continue
    if m.geom_type[g] != mujoco.mjtGeom.mjGEOM_BOX:
        continue
    p = d.geom_xpos[g]
    R = d.geom_xmat[g].reshape(3, 3)
    s = m.geom_size[g]
    corners = np.array([[sx * s[0], sy * s[1], sz * s[2]]
                        for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    z = (p + corners @ R.T)[:, 2].min()
    sole.append([gname, round(float(z), 6)])
    zmin = min(zmin, float(z))
spawn_z = round(1.0 - zmin, 6)

out = dict(
    model_xml=str(PC.PYG_XML),
    ankle_mode=PC.ANKLE_MODE,
    total_mass_kg=round(float(m.body_mass.sum()), 5),
    n_dof=len(names),
    joint_names=names,
    action_joint_names=act_names,
    obs_joint_names=obs_names,
    obs_dim=3 + 3 + 2 * len(obs_names) + len(act_names) + 3,
    default_q={n: round(float(q), 6) for n, q in zip(names, default_q)},
    action_scale=scale_val,
    use_default_offset=bool(term.cfg.offset == 0.0 or getattr(term.cfg, 'use_default_offset', True)),
    decimation=int(env.cfg.decimation),
    physics_dt=float(m.opt.timestep),
    step_dt=float(env.step_dt),
    gains=gains,
    gains_sw=gains_sw,
    dof_props=dofp,
    joint_family=fam_of,
    tn_curves=tn,
    spawn_base_z=spawn_z,
    sole_min_z_at_base1m=sole,
    keyframe_base_z=float(cfg.scene.entities['robot'].init_state.pos[2]),
    env_toggles={k: v for k, v in os.environ.items() if k.startswith('PYG_')},
)
json.dump(out, open(OUT, 'w'), indent=1)
print('AB_CONTRACT_OK', OUT)
print(' n_dof          ', out['n_dof'])
print(' actions        ', len(act_names), act_names)
print(' obs joints     ', len(obs_names), obs_names)
print(' obs_dim        ', out['obs_dim'])
print(' mass kg        ', out['total_mass_kg'])
print(' spawn_base_z   ', spawn_z, ' keyframe z', out['keyframe_base_z'])
print(' passive dofs   ', [n for n in names if n not in act_names])
