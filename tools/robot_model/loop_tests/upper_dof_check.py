"""Verify the upper-body joints (waist yaw + shoulder pitch/roll x2) before they get welded shut.

The user's instruction was "update mass and inertia, bring the joints alive and verify, then
freeze them". PYG_UPPER_DOF=1 already frees them in pygmalion_constants; this checks that the
freed model is actually sound - joints present with sane ranges, actuators attached, and the
arms settle under gravity instead of exploding - so that welding them again is a choice rather
than a way of hiding a broken sub-model.

A trained leg policy CANNOT be run here: freeing the upper body adds 5 actuators, so the action
dimension no longer matches. This is a model check, deliberately.
"""
import os
import numpy as np
import torch
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa

UPPER = ("waist_yaw_joint", "L_shoulder_pitch_joint", "R_shoulder_pitch_joint",
         "L_shoulder_roll_joint", "R_shoulder_roll_joint")

cfg = load_env_cfg('Mjlab-Velocity-Flat-Pygmalion', play=True)
cfg.scene.num_envs = 4
cfg.events.pop('push_robot', None)
env = ManagerBasedRlEnv(cfg=cfg, device='cpu')
robot = env.scene['robot']
names = list(robot.joint_names)
m = env.sim.mj_model

print(f'upper DOF freed: {os.environ.get("PYG_UPPER_DOF", "0")}')
print(f'model: {m.nbody} bodies, {m.njnt} joints, {m.nu} actuators, nq={m.nq} nv={m.nv}')
print(f'total mass: {m.body_mass.sum():.3f} kg')
print(f'articulated joints seen by the entity: {len(names)}')
present = [j for j in UPPER if j in names]
print(f'upper joints present: {present if present else "NONE (welded)"}')
for j in present:
    i = names.index(j)
    lo, hi = robot.data.joint_pos_limits[0, i].tolist()
    print(f'   {j:26s} range {np.degrees(lo):+7.1f} .. {np.degrees(hi):+7.1f} deg')
act = [m.actuator(k).name for k in range(m.nu)]
print(f'actuators on upper joints: {[a for a in act if any(u.split("_joint")[0] in a for u in UPPER)] or "none"}')

# Settle under gravity, stepping the SIM directly rather than env.step: with the upper body
# freed the action space is 17, but several velocity-task reward terms carry per-joint vectors
# sized for the 12-DOF leg model (variable_posture raises
# "size of tensor a (17) must match tensor b (12)"). That is a task-side gap, not a model
# defect, and this check is about the model - so the task layer is bypassed here and the gap
# is reported separately.
env.reset()
z0 = robot.data.root_link_pos_w[:, 2].clone()
qmax = 0.0
idx = [names.index(j) for j in present] if present else []
for _ in range(200):
    env.sim.step()
    if idx:
        qmax = max(qmax, float(robot.data.joint_pos[:, idx].abs().max()))
z1 = robot.data.root_link_pos_w[:, 2]
print(f'after 200 zero-action steps: base height {z0.mean():.3f} -> {z1.mean():.3f} m, '
      f'finite={bool(torch.isfinite(z1).all())}')
if present:
    print(f'max |upper joint angle| reached: {np.degrees(qmax):.1f} deg')
os._exit(0)
