"""Give the 3D-printed structural parts their real density in the URDF-export copy.

The leg was printed in PLA, not machined in 6061, and the survey in docs/89 measured how
much lighter: 0.329 of the aluminium CAD mass on the confident set (sd 0.033), with
per-part ratios where a part was actually weighed. This writes that into the CAD so the
mass properties - and therefore the URDF - come out at the mass the robot really has.

Per body under Joints_UnderBody whose material is Aluminum 6061:
  * weighed, confident     -> density = (its own v5 ratio) x 2.70  (geometry may have changed
                              between v5 and this revision, so the RATIO transfers, not the gram)
  * not weighed, or the reading was flagged uncertain -> density = 0.329 x 2.70 = 0.888 g/cm3
  * Arm_A / Arm_B          -> untouched: the push rods are machined aluminium
  * CenterPin_RS03         -> untouched: 0.4 g pins
Hidden bodies are included - the light bulb is a view state, and in this document every
group but the ankle is switched off. The SHOULDER was added to scope on 2026-08-26 on the
user's word that "apart from the bearings it is all printed"; its reworked bodies arrive on
generic 'Steel', not aluminium, so the material filter accepts that too. The torso stays out
(the user said to ignore the torso rework). Each body gets its own copied material so nothing else in
the document shifts.

Usage: set_printed_density.py [--apply]     (dry run by default; Fusion MCP reachable,
       the URDF-export copy must be the ACTIVE document - this refuses to touch any other)
"""
import json
import os
import sys

sys.path.insert(0, '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/fusion')
import mcp_client as M  # noqa: E402

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
MEAS = f'{REPO}/tools/robot_model/alu_parts_measured.json'
STATS = f'{REPO}/tools/robot_model/alu_parts_ratio_stats.json'
V5 = '/home/syaro/pyg_fea/fusion/alu_parts_v5/index.json'
PLAN_OUT = '/home/syaro/pyg_fea/fusion/printed_density_plan.json'
AL = 2.70
EXPORT_DOC_PREFIX = '260819_HumanMesh_wUpper_URDFexport'
KEEP_AL = ('Arm_A', 'Arm_B')
SKIP_OCC = ('CenterPin', 'NoSim', 'DR2020', 'DF2020')
# The shoulder subtrees added to scope on 2026-08-26. Torso2ShoulderP is NOT here: it sits at
# the torso/shoulder interface and the torso rework is out of scope by user instruction.
# Shoulder-Roll2Yaw-dummy is included even though its light bulb is off - in this document a
# light bulb is a view state (massprops_fusion.py s"hidden"), and the bbox shows it is the
# yoke whose side plates straddle the DR2020 extrusion and carry the 6810ZZ. Real hardware.
SHOULDER_SUBTREES = ('Shoulder-Pitch2Roll', 'Shoulder-Roll2Yaw-dummy', 'DummyHand')
# a light bulb that is off is a VIEW state, not a design decision (docs/88 s4b): in this
# document every group but the ankle happens to be switched off. Only alternative-design
# branches are excluded.
ALT_BRANCH = ('NotUse', 'fullDoF', 'REF', 'NoSim')

LIST = r'''
import adsk.core, adsk.fusion
def run(_c: str):
    app = adsk.core.Application.get()
    d = adsk.fusion.Design.cast(app.activeProduct)
    root = d.rootComponent
    out = []
    stack = [(root.occurrences.item(i), "", True) for i in range(root.occurrences.count)]
    while stack:
        o, path, live = stack.pop()
        live = live and o.isLightBulbOn
        p = path + "/" + o.name
        for i in range(o.bRepBodies.count):
            b = o.bRepBodies.item(i)
            mat = b.material.name if b.material else "?"
            pr = b.physicalProperties
            out.append([p + "::" + b.name, o.name, b.name, mat, round(pr.mass * 1000, 3),
                        round(pr.volume, 4), bool(live and b.isLightBulbOn)])
        for i in range(o.childOccurrences.count):
            stack.append((o.childOccurrences.item(i), p, live))
    emit({"doc": app.activeDocument.name, "bodies": out})
'''

APPLY = r'''
import adsk.core, adsk.fusion
PLAN = __PLAN__          # path -> [density_g_cm3, material name]
def run(_c: str):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    existing = {}
    for i in range(des.materials.count):
        m = des.materials.item(i)
        existing[m.name] = m
    stack = [(root.occurrences.item(i), "") for i in range(root.occurrences.count)]
    while stack:
        o, path = stack.pop()
        p = path + "/" + o.name
        for i in range(o.bRepBodies.count):
            b = o.bRepBodies.item(i)
            key = p + "::" + b.name
            if key in PLAN:
                dens, name = PLAN[key]
                name = name[:120]
                mat = existing.get(name)
                if mat is None:
                    mat = des.materials.addByCopy(b.material, name)
                    existing[name] = mat
                b.material = mat                # PLA -> PLA with a new density is a new copy
                for pid in ("structural_Density", "thermal_Density"):
                    pr = mat.materialProperties.itemById(pid)
                    if pr is not None:
                        pr.value = dens * 1000.0          # kg/m3
        # the first version of this script forgot this line, visited only the root
        # occurrences, matched nothing, and reported success
        for i in range(o.childOccurrences.count):
            stack.append((o.childOccurrences.item(i), p))
    return                   # a normal end keeps the edits; an exception rolls them back
'''


def main():
    apply = '--apply' in sys.argv
    meas = json.load(open(MEAS))
    v5 = json.load(open(V5))
    mean_ratio = json.load(open(STATS))['confident']['mean']
    ratio_by_body = {}
    for e in meas['entries']:
        if e['g'] is None:
            continue
        rows = [r for r in v5 if r['body'] == e['body']]
        if len(rows) != 1:
            continue
        ratio_by_body[e['body']] = dict(ratio=e['g'] / rows[0]['mass_g'], conf=e['conf'],
                                        g=e['g'], v5_al=rows[0]['mass_g'])

    M.connect()
    L = M.script(LIST)
    assert L['doc'].startswith(EXPORT_DOC_PREFIX), \
        f"active document is {L['doc']!r}, not the URDF-export copy - refusing"
    plan, rows = {}, []
    for path, occ, body, mat, m_g, vol, live in L['bodies']:
        # aluminium bodies get converted; bodies already on a PLA material are RE-planned, so a
        # changed measurement moves them (a new 'PLA <body> <density>' material is made when
        # the value changed, the existing one reused when not) - the first version skipped
        # them and was a no-op on any copy that had been converted once
        # SCOPE (2026-08-26, user: "apart from the bearings the shoulder is all printed"):
        # the leg, plus the reworked shoulder under Joints_UpperBody. The torso is still
        # excluded - the user said to ignore the torso rework.
        in_leg = path.startswith('/Joints_UnderBody')
        in_shoulder = any(t in path for t in SHOULDER_SUBTREES)
        if not (in_leg or in_shoulder):
            continue
        # MATERIAL: the v22 shoulder bodies came in as generic 'Steel' (7.850), not aluminium -
        # the document default, not a design intent (the same group was Aluminum 6061 on
        # 08-22, and the geometry is 3 mm caps and 6 mm plates). Accepting only 'Alumin' here
        # would make this script run clean and change nothing on the shoulder.
        if not ('Alumin' in mat or mat.startswith('PLA ') or mat.strip() == 'Steel'):
            continue
        if any(t in path for t in ALT_BRANCH):
            continue
        if body in KEEP_AL or any(s in occ for s in SKIP_OCC):
            continue
        # 'what it weighs at aluminium' is the reference the measured RATIO multiplies. For a
        # body sitting on Steel (or an earlier PLA copy) the CAD gram figure is the wrong
        # reference, so it is recomputed from the volume.
        al_g = m_g if 'Alumin' in mat else vol * AL
        r = ratio_by_body.get(body)
        # a part's own ratio is used only when its reading AND its match are confident;
        # an orange (low) reading such as SupportB's 0.465 would put a density above PLA
        # itself into the CAD, so those fall back to the confident-set mean
        if r and r['conf'] not in ('high', 'med'):
            r = None
        ratio = r['ratio'] if r else mean_ratio
        dens = ratio * AL
        name = f'PLA {body} {dens:.3f}'
        plan[path] = [round(dens, 4), name]
        cur = m_g / vol
        if abs(cur - dens) < 0.01 * dens:
            continue                                             # already at this density
        rows.append(dict(path=path, body=body, vol=vol, al_g=al_g, ratio=round(ratio, 4),
                         dens=round(dens, 4), new_g=round(vol * dens, 2), was_g=round(m_g, 2),
                         src=('measured ' + r['conf']) if r else 'mean'))
    json.dump(dict(doc=L['doc'], mean_ratio=mean_ratio, rows=rows), open(PLAN_OUT, 'w'),
              indent=1, ensure_ascii=False)
    print(f"document: {L['doc']}")
    print(f"{'body':28s} {'Al g':>7s} {'ratio':>6s} {'g/cm3':>6s} {'new g':>7s}  source")
    for r in sorted(rows, key=lambda x: -x['al_g']):
        print(f"{r['body'][:28]:28s} {r['al_g']:7.1f} {r['ratio']:6.3f} {r['dens']:6.3f} "
              f"{r['new_g']:7.1f}  {r['src']}")
    tot_al = sum(r['al_g'] for r in rows)
    tot_new = sum(r['new_g'] for r in rows)
    print(f"\n{len(rows)} bodies to change (ONE side of the leg + pelvis as modelled): "
          f"{tot_al / 1000:.3f} kg at aluminium -> {tot_new / 1000:.3f} kg printed  "
          f"({len([r for r in rows if r['src'] != 'mean'])} with their own measured ratio); "
          f"bodies already at their planned density are not listed")
    if not apply:
        print('DRY RUN - pass --apply')
        return
    if not plan:
        print('nothing to apply - every body is already at its planned density')
        return
    # the connector silently skips scripts above 4 KiB, so the plan goes over in batches
    items = list(plan.items())
    batch, n_calls = [], 0
    for k, v in items + [(None, None)]:
        trial = dict(batch + ([(k, v)] if k else []))
        src = APPLY.replace('__PLAN__', json.dumps(trial))
        if k is not None and len(src.encode()) < 3500:
            batch.append((k, v))
            continue
        if batch:
            M.run_script(APPLY.replace('__PLAN__', json.dumps(dict(batch))))
            n_calls += 1
        batch = [(k, v)] if k else []
    print(f'applied in {n_calls} batches')
    L2 = M.script(LIST)
    after = {b[0]: b for b in L2['bodies']}
    bad = [(p, after[p][3], after[p][4]) for p in plan
           if abs(after[p][4] - plan[p][0] * after[p][5]) > 0.05]
    print(f"applied: {len(plan) - len(bad)}/{len(plan)} bodies at the planned density")
    for p, mat, g in bad[:10]:
        print(f"   NOT applied: {p[-50:]}  mat={mat} {g:.1f} g")
    assert not bad, 'the document did not keep every density edit'
    M.run_script('''
import adsk.core
def run(_c: str):
    app = adsk.core.Application.get()
    app.activeDocument.save("printed-part densities from the v5 ratio survey (docs/89)")
''')
    print('saved.')


if __name__ == '__main__':
    main()
