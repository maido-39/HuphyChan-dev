"""Export the pygmalion MJCF models (serial RP / closed-loop AB) for the collision web viewer.

For each model: body tree (parent, pos, quat), hinge joints (body, axis, pos, range), geoms per
body (capsule / box / mesh, size, pos, quat, group -> visual | collision | hull), decimated
visual/hull meshes as binary STL (meshes/), contact-exclude pairs, plus for the loop model a
closure-consistent AB trajectory (cranks servoed in plain MuJoCo: pitch sweep, roll sweep,
circle; qpos of every joint at 25 Hz) so the viewer can PLAY the mechanism instead of posing
passive joints by hand. Arms welded abducted 15 deg as in training (docs/92 s7).

    mujoco-sim/mjlab/.venv/bin/python3 tools/collision_viewer/build_data.py
"""
import json, os
import numpy as np, mujoco, trimesh

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XMLS = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls'
OUT = f'{REPO}/tools/collision_viewer'
MODELS = {'RP (serial ankle)': 'pygmalion_v3_printed', 'AB (closed-loop ankle)': 'pygmalion_v3_printed_loop'}
FACES = 12000
KP, KD = 22.3, 1.41


def load(tag, servos=False):
    spec = mujoco.MjSpec.from_file(f'{XMLS}/{tag}.xml')
    for j in list(spec.joints):
        if j.name.endswith('_shoulder_roll_joint'):
            ax = np.asarray(j.axis, float); ax /= np.linalg.norm(ax); h = np.radians(-15) / 2
            q = np.array([np.cos(h), *(np.sin(h) * ax)]); b = j.parent
            w1, x1, y1, z1 = np.asarray(b.quat, float); w2, x2, y2, z2 = q
            b.quat = [w1*w2 - x1*x2 - y1*y2 - z1*z2, w1*x2 + x1*w2 + y1*z2 - z1*y2, w1*y2 - x1*z2 + y1*w2 + z1*x2, w1*z2 + x1*y2 - y1*x2 + z1*w2]
        if j.name in ('waist_yaw_joint', 'L_shoulder_pitch_joint', 'R_shoulder_pitch_joint', 'L_shoulder_roll_joint', 'R_shoulder_roll_joint'):
            spec.delete(j)
    for ex in list(spec.excludes):
        if 'arm' in ex.bodyname1 + ex.bodyname2 and 'hip' in ex.bodyname1 + ex.bodyname2:
            spec.delete(ex)
    if servos:
        spec.option.timestep = 0.001; spec.option.gravity[:] = 0
        for s in 'LR':
            for t in 'AB':
                a = spec.add_actuator(); a.name = f'{s}_crank_{t}_servo'; a.trntype = mujoco.mjtTrn.mjTRN_JOINT
                a.target = f'{s}_crank_{t}_joint'; a.gaintype = mujoco.mjtGain.mjGAIN_FIXED; a.biastype = mujoco.mjtBias.mjBIAS_AFFINE
                a.gainprm[0] = KP; a.biasprm[1] = -KP; a.biasprm[2] = -KD; a.forcerange[:] = [-60, 60]; a.forcelimited = True
        hold = [j for j in spec.joints if j.type == mujoco.mjtJoint.mjJNT_HINGE and not any(k in j.name for k in ('crank', 'rod', 'ankle'))]
        return spec.compile(), [j.name for j in hold]
    return spec.compile(), []


def export_mesh(m, mid, done):
    name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, mid)
    fn = f'{name}.stl'
    if fn in done:
        return fn
    V = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]]
    F = m.mesh_face[m.mesh_faceadr[mid]:m.mesh_faceadr[mid] + m.mesh_facenum[mid]]
    tm = trimesh.Trimesh(V, F, process=False)
    if len(tm.faces) > FACES:
        try:
            tm = tm.simplify_quadric_decimation(face_count=FACES)
        except Exception as e:  # noqa: BLE001
            print('  decimation failed', name, e)
    tm.export(f'{OUT}/meshes/{fn}')
    done.add(fn)
    return fn


def model_data(tag, done):
    m, hold = load(tag)
    bn = lambda i: mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i)
    bodies = []
    for b in range(m.nbody):
        bodies.append(dict(id=b, name=bn(b), parent=int(m.body_parentid[b]), pos=m.body_pos[b].round(6).tolist(), quat=m.body_quat[b].round(6).tolist(),
                           mass=round(float(m.body_mass[b]), 4), geoms=[]))
    for g in range(m.ngeom):
        grp = int(m.geom_group[g]); t = int(m.geom_type[g])
        kind = 'visual' if grp == 2 else 'collision' if grp == 3 else 'hull' if grp == 4 else 'other'
        if kind == 'other' and t != mujoco.mjtGeom.mjGEOM_MESH:
            kind = 'collision' if m.geom_contype[g] else 'other'
        gd = dict(name=mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or f'geom{g}', kind=kind, type={2: 'sphere', 3: 'capsule', 5: 'cylinder', 6: 'box', 7: 'mesh'}.get(t, str(t)),
                  size=m.geom_size[g].round(6).tolist(), pos=m.geom_pos[g].round(6).tolist(), quat=m.geom_quat[g].round(6).tolist(), rgba=m.geom_rgba[g].round(3).tolist(),
                  contype=int(m.geom_contype[g]))
        if t == mujoco.mjtGeom.mjGEOM_MESH:
            gd['mesh'] = export_mesh(m, int(m.geom_dataid[g]), done)
        bodies[int(m.geom_bodyid[g])]['geoms'].append(gd)
    joints = []
    for j in range(m.njnt):
        if m.jnt_type[j] != mujoco.mjtJoint.mjJNT_HINGE:
            continue
        joints.append(dict(name=mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j), body=int(m.jnt_bodyid[j]), axis=m.jnt_axis[j].round(6).tolist(), pos=m.jnt_pos[j].round(6).tolist(),
                           range=(m.jnt_range[j].round(5).tolist() if m.jnt_limited[j] else [-3.1416, 3.1416]), limited=bool(m.jnt_limited[j]), qadr=int(m.jnt_qposadr[j])))
    sites = [dict(name=mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_SITE, s), body=int(m.site_bodyid[s]), pos=m.site_pos[s].round(6).tolist(), size=float(m.site_size[s][0])) for s in range(m.nsite) if m.site_group[s] == 5]
    excludes = [[bn(m.exclude_signature[i] >> 16), bn(m.exclude_signature[i] & 0xFFFF)] for i in range(m.nexclude)]
    eqs = []
    for e in range(m.neq):
        if m.eq_type[e] == mujoco.mjtEq.mjEQ_CONNECT:
            eqs.append(dict(site1=mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_SITE, m.eq_obj1id[e]), site2=mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_SITE, m.eq_obj2id[e])))
    d = dict(tag=tag, bodies=bodies, joints=joints, sites=sites, excludes=excludes, connects=eqs, nq=int(m.nq), total_mass=round(float(m.body_subtreemass[1]), 3))
    # standing height
    dd = mujoco.MjData(m); dd.qpos[:] = m.qpos0; dd.qpos[3] = 1; mujoco.mj_kinematics(m, dd)
    d['foot_z_at_origin'] = float(min(dd.geom_xpos[g][2] - m.geom_size[g][2] for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX))
    return d


def ab_trajectory():
    m, hold = load('pygmalion_v3_printed_loop', servos=True); d = mujoco.MjData(m)
    d.qpos[:] = m.qpos0; d.qpos[3] = 1
    aid = {(s, t): mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, f'{s}_crank_{t}_servo') for s in 'LR' for t in 'AB'}
    hid = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n) for n in hold]
    T = 3.0; fps = 25; steps = 40
    phases = [('pitch', lambda t: ((np.radians(30) * np.sin(2 * np.pi * t / T),) * 2)),
              ('roll', lambda t: (np.radians(14) * np.sin(2 * np.pi * t / T), -np.radians(14) * np.sin(2 * np.pi * t / T))),
              ('circle', lambda t: (np.radians(25) * np.sin(2 * np.pi * t / T) + np.radians(12) * np.cos(2 * np.pi * t / T), np.radians(25) * np.sin(2 * np.pi * t / T) - np.radians(12) * np.cos(2 * np.pi * t / T)))]
    jn = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j) for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE]
    jq = [int(m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n)]) for n in jn]
    frames, labels = [], []
    for lab, fn in phases:
        for k in range(int(T * fps)):
            cA, cB = fn(k / fps)
            for _ in range(steps):
                d.qpos[:7] = [0, 0, 0, 1, 0, 0, 0]; d.qvel[:6] = 0
                for j in hid:
                    d.qfrc_applied[m.jnt_dofadr[j]] = -300 * d.qpos[m.jnt_qposadr[j]] - 6 * d.qvel[m.jnt_dofadr[j]]
                for s in 'LR':
                    d.ctrl[aid[(s, 'A')]] = cA; d.ctrl[aid[(s, 'B')]] = cB
                mujoco.mj_step(m, d)
            frames.append([round(float(d.qpos[q]), 5) for q in jq]); labels.append(lab)
    return dict(joints=jn, fps=fps, frames=frames, labels=labels)


def main():
    done = set()
    bent = json.load(open(f'{REPO}/pygmalion_locomotion/assets/pygmalion_v2/pygmalion_v3_printed_loop_bent.json'))['joint_pos']
    data = {'models': {k: model_data(v, done) for k, v in MODELS.items()}, 'ab_trajectory': ab_trajectory(), 'bent': bent}
    json.dump(data, open(f'{OUT}/robot.json', 'w'))
    tot = sum(os.path.getsize(f'{OUT}/meshes/{f}') for f in done) / 1e6
    print(f'-> {OUT}/robot.json  meshes {len(done)} files {tot:.1f} MB  trajectory {len(data["ab_trajectory"]["frames"])} frames')


if __name__ == '__main__':
    main()
