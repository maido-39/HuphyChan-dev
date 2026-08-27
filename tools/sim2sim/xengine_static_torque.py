"""Cross-engine static gravity check - MuJoCo side.

Both engines hold the SAME pose with the base welded in the air and report the torque each
joint needs to resist gravity. If masses, COMs and kinematics agree, these torques agree;
if the shoulder rework or the URDF->USD conversion lost mass somewhere, they cannot.
MuJoCo side: qfrc_bias at qvel=0 IS the gravity load (no velocity terms).
"""
import json

import mujoco
import numpy as np

X = ('/home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab/src/mjlab/'
     'asset_zoo/robots/pygmalion/xmls/pygmalion_v4_printed.xml')
POSE = {  # a bent, asymmetric pose so every joint sees a moment arm
    'L_hip_pitch_joint': -0.30, 'R_hip_pitch_joint': -0.20,
    'L_hip_roll_joint': 0.10, 'R_hip_roll_joint': -0.05,
    'L_hip_yaw_joint': 0.15, 'R_hip_yaw_joint': -0.10,
    'L_knee_joint': -0.60, 'R_knee_joint': -0.40,
    'L_ankle_pitch_joint': -0.20, 'R_ankle_pitch_joint': -0.10,
    'L_ankle_roll_joint': 0.08, 'R_ankle_roll_joint': -0.06,
    'waist_yaw_joint': 0.20,
    'L_shoulder_pitch_joint': -0.50, 'R_shoulder_pitch_joint': -0.30,
    'L_shoulder_roll_joint': 0.12, 'R_shoulder_roll_joint': -0.15,
}

m = mujoco.MjModel.from_xml_path(X)
d = mujoco.MjData(m)
d.qpos[0:3] = [0, 0, 1.0]
d.qpos[3:7] = [1, 0, 0, 0]
for jn, q in POSE.items():
    d.qpos[m.jnt_qposadr[m.joint(jn).id]] = q
d.qvel[:] = 0
mujoco.mj_forward(m, d)

out = {'pose': POSE, 'gravity_torque_Nm': {}}
for jn in POSE:
    dof = m.jnt_dofadr[m.joint(jn).id]
    out['gravity_torque_Nm'][jn] = round(float(d.qfrc_bias[dof]), 4)
out['total_mass'] = round(float(m.body_mass.sum()), 4)
json.dump(out, open('/home/syaro/pyg_fea/work/xengine_mujoco.json', 'w'), indent=1)
print(json.dumps(out['gravity_torque_Nm'], indent=1))
