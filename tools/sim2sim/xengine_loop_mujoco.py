"""Cross-engine static gravity check for the CLOSED-LOOP (AB) ankle - MuJoCo side.

The serial twin of this script (`xengine_static_torque.py`) could stop at `qfrc_bias`, because in a
tree every joint's gravity load is its own subtree's weight and nothing else. A closed loop breaks
that: the foot hangs off two rods, so the crank motors carry foot load that never appears in the
crank's own subtree bias, and the passive ankle pitch/roll joints carry no motor at all. Two
different questions therefore have two different answers, and both are computed here:

  A. "every joint is held by its own servo"  -> tau = qfrc_bias, loop force zero.       (`bias`)
  B. "only the 17 real motors are held, the  -> solve  tau_act + J_c^T lam = qfrc_bias  (`static`)
      rods/U-joints/ankle joints are free"      for the 17 motor torques and 12 loop forces.

B is the physical machine; A is what a naive port of the serial script would report. Reporting only
A on a loop model quietly attributes the whole foot load to nobody.

Two modes:
  (no args)            solve the loop-consistent pose for the shared bent pose, write the reference
  --at <isaac.json>    re-evaluate both references at the pose IsaacSim actually reached

Run with the mjlab venv:  mujoco-sim/mjlab/.venv/bin/python3 tools/sim2sim/xengine_loop_mujoco.py
"""
import json
import sys

import mujoco
import numpy as np

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
X = (f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/'
     'pygmalion_v4_printed_loop.xml')
SERIAL_POSE = '/home/syaro/pyg_fea/work/xengine_mujoco.json'
OUT = '/home/syaro/pyg_fea/work/xengine_loop_mujoco.json'

# the 17 real motors of the AB robot: the serial 17 minus the 4 ankle joints (now passive,
# driven through the rods) plus the 4 ankle cranks that replaced them.
ACTUATED = [
    'L_hip_pitch_joint', 'L_hip_roll_joint', 'L_hip_yaw_joint', 'L_knee_joint',
    'R_hip_pitch_joint', 'R_hip_roll_joint', 'R_hip_yaw_joint', 'R_knee_joint',
    'L_crank_A_joint', 'L_crank_B_joint', 'R_crank_A_joint', 'R_crank_B_joint',
    'waist_yaw_joint',
    'L_shoulder_pitch_joint', 'L_shoulder_roll_joint',
    'R_shoulder_pitch_joint', 'R_shoulder_roll_joint',
]
# one entry per <equality><connect>: (rod-side site, foot-side site, the 3 joints that move the rod)
LOOPS = [
    ('L_rod_A_end', 'L_ball_A', ['L_crank_A_joint', 'L_rod_A_u1', 'L_rod_A_u2']),
    ('L_rod_B_end', 'L_ball_B', ['L_crank_B_joint', 'L_rod_B_u1', 'L_rod_B_u2']),
    ('R_rod_A_end', 'R_ball_A', ['R_crank_A_joint', 'R_rod_A_u1', 'R_rod_A_u2']),
    ('R_rod_B_end', 'R_ball_B', ['R_crank_B_joint', 'R_rod_B_u1', 'R_rod_B_u2']),
]


def load():
    m = mujoco.MjModel.from_xml_path(X)
    d = mujoco.MjData(m)
    d.qpos[0:3] = [0, 0, 1.0]
    d.qpos[3:7] = [1, 0, 0, 0]
    d.qvel[:] = 0
    return m, d


def qadr(m, jn):
    return m.jnt_qposadr[m.joint(jn).id]


def dofadr(m, jn):
    return m.jnt_dofadr[m.joint(jn).id]


def set_pose(m, d, pose):
    for jn, q in pose.items():
        d.qpos[qadr(m, jn)] = q
    mujoco.mj_forward(m, d)


def gap(m, d, s1, s2):
    """world-space separation of the two sites a <connect> ties together."""
    return d.site_xpos[m.site(s1).id] - d.site_xpos[m.site(s2).id]


def close_loops(m, d):
    """Newton-solve each rod's 3 joint angles so its end site lands on its foot ball site.

    Three unknowns, three equations per rod, and the rods are independent of each other once the
    leg pose is fixed - so this is four small square solves, not one big optimisation.
    """
    info = []
    for s_rod, s_ball, joints in LOOPS:
        idx = [qadr(m, j) for j in joints]
        for _ in range(80):
            r = gap(m, d, s_rod, s_ball)
            if np.linalg.norm(r) < 1e-12:
                break
            J = np.zeros((3, 3))
            for k, ia in enumerate(idx):                      # finite-difference Jacobian:
                h, q0 = 1e-6, d.qpos[ia]                      # 3 columns, cheaper than mj_jac
                d.qpos[ia] = q0 + h                           # bookkeeping for two site frames
                mujoco.mj_forward(m, d)
                J[:, k] = (gap(m, d, s_rod, s_ball) - r) / h
                d.qpos[ia] = q0
            step = np.linalg.lstsq(J, -r, rcond=None)[0]
            step = np.clip(step, -0.3, 0.3)                   # keep the first iterations sane
            for k, ia in enumerate(idx):
                d.qpos[ia] += step[k]
            mujoco.mj_forward(m, d)
        info.append({'loop': s_rod, 'residual_mm': float(np.linalg.norm(gap(m, d, s_rod, s_ball)) * 1e3),
                     'q': {j: float(d.qpos[qadr(m, j)]) for j in joints}})
    return info


# per leg: what the loop determines once the two cranks are fixed - the foot's two rotations
# and the four rod U-joint angles. Six unknowns, six constraint equations, one solution.
DRIVEN_BY_LOOP = {
    'L': (['L_ankle_pitch_joint', 'L_ankle_roll_joint',
           'L_rod_A_u1', 'L_rod_A_u2', 'L_rod_B_u1', 'L_rod_B_u2'],
          [('L_rod_A_end', 'L_ball_A'), ('L_rod_B_end', 'L_ball_B')]),
    'R': (['R_ankle_pitch_joint', 'R_ankle_roll_joint',
           'R_rod_A_u1', 'R_rod_A_u2', 'R_rod_B_u1', 'R_rod_B_u2'],
          [('R_rod_A_end', 'R_ball_A'), ('R_rod_B_end', 'R_ball_B')]),
}


def ankle_from_cranks(m, d):
    """Solve where the loop PUTS the foot, given the crank angles currently in qpos.

    This is the geometry check that a torque table cannot make: if the USD anchors were even
    slightly wrong, IsaacSim's freely-hanging ankle would settle somewhere MuJoCo's loop does not
    put it, while both engines' torque numbers stayed perfectly self-consistent.
    """
    out = {}
    for leg, (unknowns, pairs) in DRIVEN_BY_LOOP.items():
        idx = [qadr(m, j) for j in unknowns]
        for _ in range(120):
            r = np.concatenate([gap(m, d, a, b) for a, b in pairs])
            if np.linalg.norm(r) < 1e-13:
                break
            J = np.zeros((6, 6))
            for k, ia in enumerate(idx):
                h, q0 = 1e-6, d.qpos[ia]
                d.qpos[ia] = q0 + h
                mujoco.mj_forward(m, d)
                J[:, k] = (np.concatenate([gap(m, d, a, b) for a, b in pairs]) - r) / h
                d.qpos[ia] = q0
            mujoco.mj_forward(m, d)
            step = np.clip(np.linalg.lstsq(J, -r, rcond=None)[0], -0.3, 0.3)
            for k, ia in enumerate(idx):
                d.qpos[ia] += step[k]
            mujoco.mj_forward(m, d)
        out.update({j: float(d.qpos[qadr(m, j)]) for j in unknowns})
        out[f'{leg}_residual_mm'] = float(np.linalg.norm(
            np.concatenate([gap(m, d, a, b) for a, b in pairs])) * 1e3)
    return out


def loop_jacobian(m, d):
    """d(site1 - site2)/dq for every connect, stacked: the 12 x nv constraint Jacobian."""
    rows = []
    for s_rod, s_ball, _ in LOOPS:
        J1, J2 = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        mujoco.mj_jacSite(m, d, J1, None, m.site(s_rod).id)
        mujoco.mj_jacSite(m, d, J2, None, m.site(s_ball).id)
        rows.append(J1 - J2)
    return np.vstack(rows)


def references(m, d):
    """Both static answers at the current pose, plus how well the loop is actually closed."""
    mujoco.mj_forward(m, d)
    joint_dofs = [dofadr(m, m.joint(i).name) for i in range(m.njnt)
                  if m.jnt_type[i] != mujoco.mjtJoint.mjJNT_FREE]
    names = [m.joint(i).name for i in range(m.njnt) if m.jnt_type[i] != mujoco.mjtJoint.mjJNT_FREE]
    bias = d.qfrc_bias[joint_dofs]

    Jc = loop_jacobian(m, d)[:, joint_dofs]                   # 12 x 29
    n_act = len(ACTUATED)
    A = np.zeros((len(joint_dofs), n_act + Jc.shape[0]))
    for k, jn in enumerate(ACTUATED):
        A[names.index(jn), k] = 1.0
    A[:, n_act:] = Jc.T
    x, *_ = np.linalg.lstsq(A, bias, rcond=None)              # square (29 x 29) in practice
    resid = float(np.max(np.abs(A @ x - bias)))

    return {
        'bias_Nm': {jn: round(float(bias[names.index(jn)]), 4) for jn in names},
        'static_motor_Nm': {jn: round(float(x[k]), 4) for k, jn in enumerate(ACTUATED)},
        'loop_force_N': [round(float(v), 4) for v in x[n_act:]],
        'static_solve_residual_Nm': resid,
        'A_cond': float(np.linalg.cond(A)),
        'loop_gap_mm': {s1: round(float(np.linalg.norm(gap(m, d, s1, s2)) * 1e3), 6)
                        for s1, s2, _ in LOOPS},
        'pose': {jn: round(float(d.qpos[qadr(m, jn)]), 6) for jn in names},
    }


def main():
    m, d = load()
    serial = json.load(open(SERIAL_POSE))

    if '--at' in sys.argv:
        reached = json.load(open(sys.argv[sys.argv.index('--at') + 1]))
        pose = reached['q_reached'] if 'q_reached' in reached else reached
        set_pose(m, d, pose)
        out = references(m, d)
        out['mode'] = 'at-isaac-reached-pose'
        dst = '/home/syaro/pyg_fea/work/xengine_loop_compare.json'
    else:
        set_pose(m, d, serial['pose'])                        # the shared bent pose, ankles included
        out = {'closure': close_loops(m, d)}
        out.update(references(m, d))
        out['mode'] = 'commanded-pose'
        out['total_mass'] = round(float(m.body_mass.sum()), 4)
        out['actuated'] = ACTUATED
        dst = OUT

    json.dump(out, open(dst, 'w'), indent=1)
    print(f'-> {dst}')
    print('loop gap (mm):', out['loop_gap_mm'])
    print('static solve residual (Nm):', round(out['static_solve_residual_Nm'], 9),
          ' cond(A):', round(out['A_cond'], 1))
    for jn in ACTUATED:
        print(f"  {jn:26s} bias {out['bias_Nm'][jn]:9.4f}   motor {out['static_motor_Nm'][jn]:9.4f}")


if __name__ == '__main__':
    main()
