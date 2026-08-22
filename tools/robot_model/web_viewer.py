"""Web viewer for the v2 robot - joints on sliders, mass properties on demand.

viser serves a three.js scene over HTTP; every mesh MuJoCo loads is shown at its FK pose,
so what you inspect is exactly what the simulator uses: visual meshes, the collision
primitives (green, translucent), the optional convex hulls, and the analytic motor
cylinders. Sliders drive qpos through mj_forward - no dynamics, pure kinematics - with
the base held at the validated standing height.

Panels:
  Joints     one slider per joint (deg, real ranges), HOME / KNEES-BENT / zero presets,
             L/R mirror-link checkbox (drive both legs together)
  Show       visual / collision / hull / motors toggles
  Body info  pick a body -> mass, COM (link frame), principal inertia from the model,
             plus the CAD-side numbers from robot_massprops_step.json

Usage:  web_viewer.py [--port=8890]   (mjlab venv; serves on 0.0.0.0)
"""
import json
import sys

import numpy as np
import mujoco
import trimesh
import viser

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
XML = f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/pygmalion_v2.xml'
MP = '/home/syaro/pyg_fea/fusion/robot_massprops_fusion.json'
STAND_Z = 0.903
JOINTS = [f'{s}_{j}_joint' for s in 'LR'
          for j in ('hip_pitch', 'hip_roll', 'hip_yaw', 'knee', 'ankle_pitch', 'ankle_roll')]
BENT = {'hip_pitch': -0.32, 'knee': -0.67, 'ankle_pitch': 0.36}


def local_primitive(m, g):
    """Trimesh of a non-mesh geom in its local frame (z = geom axis)."""
    t = m.geom_type[g]
    r = float(m.geom_size[g][0])
    if t == mujoco.mjtGeom.mjGEOM_CAPSULE:
        h = float(m.geom_size[g][1])
        cap = trimesh.creation.capsule(height=2 * h, radius=r, count=[12, 12])
        cap.apply_translation([0, 0, -cap.bounds.mean(0)[2]])
        return cap
    if t == mujoco.mjtGeom.mjGEOM_SPHERE:
        return trimesh.creation.icosphere(subdivisions=2, radius=r)
    if t == mujoco.mjtGeom.mjGEOM_CYLINDER:
        return trimesh.creation.cylinder(radius=r, height=2 * float(m.geom_size[g][1]), sections=24)
    if t == mujoco.mjtGeom.mjGEOM_BOX:
        return trimesh.creation.box(extents=2 * np.array(m.geom_size[g][:3]))
    return None


def main():
    port = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--port=')), 8890))
    m = mujoco.MjModel.from_xml_path(XML)
    d = mujoco.MjData(m)
    mp = json.load(open(MP))
    server = viser.ViserServer(host='0.0.0.0', port=port, label='Pygmalion v2')
    server.scene.add_grid('/ground', width=4, height=4, cell_size=0.25, plane='xy')
    cm_colors = [(int(255 * a), int(255 * b), int(255 * c)) for a, b, c in
                 [(0.55, 0.63, 0.80), (0.99, 0.55, 0.38), (0.55, 0.85, 0.55), (0.91, 0.54, 0.76),
                  (0.65, 0.81, 0.89), (0.99, 0.75, 0.44), (0.70, 0.87, 0.54), (0.98, 0.60, 0.60),
                  (0.79, 0.70, 0.84), (0.85, 0.85, 0.55), (0.70, 0.70, 0.70), (0.60, 0.80, 0.85),
                  (0.85, 0.65, 0.55), (0.75, 0.75, 0.90)]]
    handles = []          # (geom id, handle)
    groups = {'visual': [], 'collision': [], 'hull': [], 'motor': []}
    for g in range(m.ngeom):
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) or f'geom{g}'
        body = m.geom_bodyid[g]
        if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH:
            mid = m.geom_dataid[g]
            a, n = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
            fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
            V, F = m.mesh_vert[a:a + n], m.mesh_face[fa:fa + fn]
            grp = 'hull' if name.endswith('_hull') else 'visual'
            col = (40, 90, 200) if grp == 'hull' else cm_colors[body % len(cm_colors)]
            h = server.scene.add_mesh_simple(f'/robot/{grp}/{name}', V, F, color=col,
                                             opacity=0.25 if grp == 'hull' else 1.0,
                                             visible=grp == 'visual')
        else:
            tm = local_primitive(m, g)
            if tm is None or body == 0:
                continue
            grp = 'motor' if 'motor' in name else 'collision'
            col = (40, 40, 45) if grp == 'motor' else (60, 170, 90)
            h = server.scene.add_mesh_simple(f'/robot/{grp}/{name}', tm.vertices, tm.faces,
                                             color=col, opacity=1.0 if grp == 'motor' else 0.35,
                                             visible=grp == 'motor')
        handles.append((g, h))
        groups[grp].append(h)

    def refresh():
        mujoco.mj_forward(m, d)
        for g, h in handles:
            q = np.zeros(4)
            mujoco.mju_mat2Quat(q, d.geom_xmat[g])
            h.position = tuple(d.geom_xpos[g])
            h.wxyz = tuple(q)

    def set_pose(vals):
        d.qpos[:] = 0
        d.qpos[2] = STAND_Z
        d.qpos[3] = 1.0
        for jn, v in vals.items():
            jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn)
            d.qpos[m.jnt_qposadr[jid]] = v
        refresh()

    sliders = {}
    with server.gui.add_folder('Joints (deg)'):
        mirror = server.gui.add_checkbox('L/R link', initial_value=False)
        for jn in JOINTS:
            jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jn)
            lo, hi = np.degrees(m.jnt_range[jid])
            s = server.gui.add_slider(jn.replace('_joint', ''), min=round(lo, 1),
                                      max=round(hi, 1), step=0.5, initial_value=0.0)
            sliders[jn] = s

            def cb(_, jn=jn, s=s):
                if mirror.value:
                    other = ('R' + jn[1:]) if jn.startswith('L') else ('L' + jn[1:])
                    if other in sliders and abs(sliders[other].value - s.value) > 1e-9:
                        sliders[other].value = s.value
                set_pose({k: np.radians(v.value) for k, v in sliders.items()})
            s.on_update(cb)
        with server.gui.add_folder('Presets'):
            def preset(vals):
                for jn, s in sliders.items():
                    base = jn.rsplit('_joint', 1)[0][2:]
                    s.value = float(np.degrees(vals.get(base, 0.0)))
                set_pose({k: np.radians(v.value) for k, v in sliders.items()})
            b0 = server.gui.add_button('HOME (all zero)')
            b0.on_click(lambda _: preset({}))
            b1 = server.gui.add_button('KNEES BENT (init keyframe)')
            b1.on_click(lambda _: preset(BENT))
    with server.gui.add_folder('Show'):
        for grp, label, init in (('visual', 'visual meshes', True), ('collision', 'collision primitives', False),
                                 ('hull', 'convex hulls', False), ('motor', 'motor cylinders', True)):
            cb2 = server.gui.add_checkbox(label, initial_value=init)

            def tog(_, grp=grp, cb2=cb2):
                for h in groups[grp]:
                    h.visible = cb2.value
            cb2.on_update(tog)
    with server.gui.add_folder('Body info'):
        names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b) for b in range(1, m.nbody)]
        dd = server.gui.add_dropdown('body', options=names, initial_value='base_link')
        info = server.gui.add_markdown('select a body')

        def show(_=None):
            b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, dd.value)
            txt = (f'**{dd.value}**\n\n'
                   f'- mass **{m.body_mass[b]:.3f} kg** · subtree {m.body_subtreemass[b]:.3f} kg\n'
                   f'- COM (link frame) [{m.body_ipos[b][0]:+.4f}, {m.body_ipos[b][1]:+.4f}, {m.body_ipos[b][2]:+.4f}] m\n'
                   f'- principal inertia [{m.body_inertia[b][0]:.4g}, {m.body_inertia[b][1]:.4g}, {m.body_inertia[b][2]:.4g}] kg m²\n')
            key = dd.value.replace('L_', '').replace('R_', '').replace('thigh_link', 'thigh').replace('shin_link', 'shin').replace('foot_link', 'foot')
            if key in mp['bodies']:
                cad = mp['bodies'][key]
                txt += (f'\nCAD(Fusion): mass {cad["mass"]:.3f} kg · {cad.get("n", cad.get("n_parts", 0))} bodies · '
                        f'principal [{cad["principal"][0]:.0f}, {cad["principal"][1]:.0f}, {cad["principal"][2]:.0f}] kg mm²')
            info.content = txt
        dd.on_update(show)
        show()
    server.gui.add_markdown(
        f'**Pygmalion v2** — total **{m.body_subtreemass[1]:.2f} kg**, standing base z {STAND_Z} m. '
        f'Meshes/inertia from the CAD STEP (docs/87). Knee stop −120°, ankle pitch −50/+30.')
    set_pose({})
    print(f'viser up on 0.0.0.0:{port}', flush=True)
    import time
    while True:
        time.sleep(3600)


if __name__ == '__main__':
    main()
