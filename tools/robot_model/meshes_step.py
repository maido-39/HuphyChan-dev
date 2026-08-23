"""Visual and collision meshes per rigid body, from the CAD STEP, already in link frames.

Every STEP solid is surface-meshed with gmsh (OCC kernel), sorted into the same rigid
bodies as massprops_step.py, moved into that body's LINK FRAME (origin at its joint point,
axes turned from the CAD convention to the simulator's: x forward, y left, z up, metres)
and written as STL:

  meshes/<body>.stl          visual, all solids of the body incl. motor placeholders
  meshes/<body>_hull.stl     collision, convex hull of the structural solids
  meshes/R_<body>.stl        the mirrored right leg (y -> -y, winding flipped)

Link frames (CAD mm): pelvis (0, 70, 60); hip_pitch/hip_roll/thigh at the hip point
(-123.7, 70, 60) - the three hip axes are concurrent there; shin at the knee
(-123.7, 115, -310); ankle/foot at (-123.7, 145, -800). CAD -> sim is a +90 deg turn
about z: sim = (-y_cad, x_cad, z_cad).

The push rods belong to no single body in a serial-ankle model; they are drawn on the
shin so the mechanism stays visible, and flagged as visual-only.

Usage: meshes_step.py [--size=8]   (mjlab .venv python; writes assets/pygmalion_v2/meshes)
"""
import json
import os
import sys

import numpy as np
import gmsh
import trimesh

STEPS = '/home/syaro/pyg_fea/steps'
OUT = '/home/syaro/MikuchanRemote/Human-Pygmalion/pygmalion_locomotion/assets/pygmalion_v2/meshes'
ANKLE_Z = -800.0
HIP = np.array([-123.7, 70.0, 60.0])
ORIGIN = {'pelvis': np.array([0.0, 70.0, 60.0]), 'hip_pitch_link': HIP, 'hip_roll_link': HIP,
          'thigh': HIP, 'shin': np.array([-123.7, 115.0, -310.0]),
          'ankle_pitch_link': np.array([-123.7, 145.0, ANKLE_Z]),
          'foot': np.array([-123.7, 145.0, ANKLE_Z])}
R_SIM = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])   # cad -> sim
GROUP_BODY = {'L6_pelvis': 'pelvis', 'L5_hip_pitchroll': 'hip_pitch_link',
              'L4_hip_yaw': 'hip_roll_link', 'L3_thigh': 'thigh', 'L2_shin': 'shin'}
JMC = {'A': ([-83.7, 205.7, -523.2], [-86.2, 195.0, -810.0]),
       'B': ([-163.7, 208.0, -616.0], [-161.2, 195.0, -810.0])}


def solid_meshes(step, size):
    """[(Trimesh in CAD mm, com)] one per solid of the STEP."""
    gmsh.model.add(os.path.basename(step))
    gmsh.model.occ.importShapes(step)
    gmsh.model.occ.synchronize()
    gmsh.option.setNumber('Mesh.MeshSizeMax', size)
    gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 14)
    gmsh.option.setNumber('Mesh.MeshSizeMin', size / 6)
    gmsh.model.mesh.generate(2)
    tags, coords, _ = gmsh.model.mesh.getNodes()
    xyz = np.asarray(coords).reshape(-1, 3)
    idx = {int(t): i for i, t in enumerate(tags)}
    out = []
    for dim, vol in gmsh.model.getEntities(3):
        faces = gmsh.model.getBoundary([(3, vol)], oriented=False, recursive=False)
        tris = []
        for fd, ft in faces:
            et, etags, nodes = gmsh.model.mesh.getElements(2, ft)
            for t, n in zip(et, nodes):
                if t == 2:   # 3-node triangles
                    tris.append(np.asarray(n).reshape(-1, 3))
        if not tris:
            continue
        T = np.vstack(tris)
        Ti = np.vectorize(idx.get)(T)
        m = trimesh.Trimesh(xyz, Ti, process=True)
        m.remove_unreferenced_vertices()
        trimesh.repair.fix_normals(m)
        com = m.center_mass if m.is_watertight else m.centroid
        out.append((m, np.asarray(com)))
    gmsh.model.remove()
    return out


def to_link(m, origin):
    v = (m.vertices - origin) @ R_SIM.T / 1000.0
    return trimesh.Trimesh(v, m.faces.copy(), process=False)


def mirror_y(m):
    v = m.vertices.copy()
    v[:, 1] *= -1
    return trimesh.Trimesh(v, m.faces[:, [0, 2, 1]].copy(), process=False)


LOOP_PTS = '/home/syaro/pyg_fea/fusion/ankle_loop_points_v3_printed.json'
# STEP-revision (0814) anchors used only to RECOGNISE which solids are the cranks: the motor
# axis point and the crank pin of each crank. The frames the meshes are written in come
# from the export copy (LOOP_PTS), like everything else in the loop model.
STEP_CRANK = {'A': ([-138.9, 145.0, -500.0], [-83.7, 205.7, -523.2]),
              'B': ([-108.4, 145.0, -600.0], [-163.7, 208.0, -616.0])}


def loop_meshes(size):
    """crank_A/B.stl in the crank frame (origin on the motor axis), rod_A/B.stl in the rod frame
    (origin at the crank pin), and shin_noloop.stl / foot_noloop.stl without them."""
    import json
    pts = json.load(open(LOOP_PTS))
    gmsh.initialize()
    gmsh.option.setNumber('General.Terminal', 0)
    parts = {'crank_A': [], 'crank_B': [], 'rod_A': [], 'rod_B': [], 'shin': [], 'foot': []}
    for m, com in solid_meshes(f'{STEPS}/link_L1_ankle_foot.step', size):
        vol = abs(m.volume) / 1000.0 if m.is_watertight else 0.0
        rod = next((t for t, (u, d) in JMC.items()
                    if np.linalg.norm(com - (np.array(u) + np.array(d)) / 2) < 1.5), None)
        if rod:
            parts[f'rod_{rod}'].append(m)
            continue
        crank = None
        for t, (mo, pin) in STEP_CRANK.items():
            mo, pin = np.array(mo), np.array(pin)
            seg = pin - mo
            u = np.clip(np.dot(com - mo, seg) / np.dot(seg, seg), 0, 1)
            if np.linalg.norm(com - (mo + u * seg)) < 45.0 and vol < 60.0 and com[2] > ANKLE_Z + 100:
                crank = t
        if crank:
            parts[f'crank_{crank}'].append(m)
        elif com[2] <= ANKLE_Z + 0.5:
            parts['foot'].append(m)
        else:
            parts['shin'].append(m)
    # the shin proper lives in the L2 STEP; the ankle STEP only holds what sits around the joint
    for m, com in solid_meshes(f'{STEPS}/link_L2_shin.step', size):
        parts['shin'].append(m)
    gmsh.finalize()
    frames = {'crank_A': np.array(pts['A']['motor']), 'crank_B': np.array(pts['B']['motor']),
              'rod_A': np.array(pts['A']['pin']), 'rod_B': np.array(pts['B']['pin']),
              'shin': ORIGIN['shin'], 'foot': ORIGIN['foot']}
    for k, ms in parts.items():
        if not ms:
            print(f'  !! no solids for {k}')
            continue
        vis = trimesh.util.concatenate([to_link(m, frames[k]) for m in ms])
        name = k if k.startswith(('crank', 'rod')) else f'{k}_noloop'
        vis.export(f'{OUT}/{name}.stl')
        mirror_y(vis).export(f'{OUT}/R_{name}.stl')
        if not k.startswith(('crank', 'rod')):
            vis.convex_hull.export(f'{OUT}/{name}_hull.stl')
            mirror_y(vis.convex_hull).export(f'{OUT}/R_{name}_hull.stl')
        b = vis.bounds
        print(f'  {name:14s} {len(ms):3d} solids  {len(vis.faces):6d} faces  bbox {np.round(b[1] - b[0], 3)} m')


def main():
    size = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--size=')), 8))
    if '--loop' in sys.argv:
        os.makedirs(OUT, exist_ok=True)
        loop_meshes(size)
        return
    os.makedirs(OUT, exist_ok=True)
    gmsh.initialize()
    gmsh.option.setNumber('General.Terminal', 0)
    bodies = {b: {'visual': [], 'hull': []} for b in ORIGIN}
    log = []
    for grp, body in GROUP_BODY.items():
        for m, com in solid_meshes(f'{STEPS}/link_{grp}.step', size):
            b = body
            vol = abs(m.volume) / 1000.0 if m.is_watertight else 0.0
            # same re-bookings as massprops_step.py (bolt patterns, red team 2026-08-20)
            if grp == 'L3_thigh' and 65 < vol < 75 and np.linalg.norm(com - [-123.7, 70.0, -100.2]) < 3:
                b = 'hip_roll_link'
            if grp == 'L5_hip_pitchroll' and 35 < vol < 45 and np.linalg.norm(com - [-56.3, 72.7, 79.8]) < 3:
                b = 'pelvis'
                # the pelvis STEP is left-sided: the right housing is the x-mirror
                mm = m.copy()
                mm.vertices[:, 0] *= -1
                mm.faces = mm.faces[:, [0, 2, 1]]
                bodies['pelvis']['visual'].append(mm)
                bodies['pelvis']['hull'].append(mm)
            bodies[b]['visual'].append(m)
            bodies[b]['hull'].append(m)
        log.append(f'{grp} -> {body}')
        print(log[-1], flush=True)
    for m, com in solid_meshes(f'{STEPS}/link_L1_ankle_foot.step', size):
        rod = any(np.linalg.norm(com - (np.array(u) + np.array(d)) / 2) < 1.5 for u, d in JMC.values())
        if rod:
            bodies['shin']['visual'].append(m)                    # visual only
        elif com[2] <= ANKLE_Z + 0.5:
            bodies['foot']['visual'].append(m)
            bodies['foot']['hull'].append(m)
        else:
            bodies['shin']['visual'].append(m)
            bodies['shin']['hull'].append(m)
    print('L1_ankle_foot -> foot / shin(fork, cranks, rods)', flush=True)
    # The actuator placeholders are NOT meshed: gmsh spends minutes per solid on their
    # fine features and the model only needs their envelope - build_robot.py draws them as
    # analytic cylinders from the measured axis/radius/length (massprops_step.py).
    gmsh.finalize()

    stats = {}
    for body, d in bodies.items():
        if not d['visual']:
            continue
        vis = trimesh.util.concatenate([to_link(m, ORIGIN[body]) for m in d['visual']])
        hull = trimesh.util.concatenate([to_link(m, ORIGIN[body]) for m in d['hull']]).convex_hull
        vis.export(f'{OUT}/{body}.stl')
        hull.export(f'{OUT}/{body}_hull.stl')
        if body != 'pelvis':
            mirror_y(vis).export(f'{OUT}/R_{body}.stl')
            mirror_y(hull).export(f'{OUT}/R_{body}_hull.stl')
        b = vis.bounds
        stats[body] = dict(faces=int(len(vis.faces)), hull_faces=int(len(hull.faces)),
                           bbox_min=b[0].round(4).tolist(), bbox_max=b[1].round(4).tolist(),
                           hull_volume_cm3=round(float(hull.volume) * 1e6, 1))
        print(f"{body:16s} {len(vis.faces):7d} faces · hull {len(hull.faces):5d} · "
              f"bbox {np.round(b[1]-b[0], 3)} m", flush=True)
    json.dump(dict(origins_cad_mm={k: v.tolist() for k, v in ORIGIN.items()},
                   R_sim_from_cad=R_SIM.tolist(), stats=stats, size_mm=size),
              open(f'{OUT}/meshes.json', 'w'), indent=1)
    print(f'-> {OUT}')


if __name__ == '__main__':
    main()
