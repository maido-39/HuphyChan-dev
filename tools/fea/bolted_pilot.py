"""Bolted-joint pilot: foot clevis + JS6 ball + 2 flange spacers + M6 bolt,
with thread TIE, thermal bolt pretension and frictional contact.

Why: the bonded/bearing screening models cannot see bolt bending and hole
edge-contact — the red-team's residual risk on the clevis (docs/77 §9 item 5).
This deck is the reference recipe for every bolted hotspot in the campaign.

Measured stack (Ankle2Feet.step, anchor A, bolt axis x at y=195.5 z=-810):
  tap block r2.52 x[-103.1,-88.1] (15 mm M6 thread) | flangeA [-88.10,-84.60]
  | ball bore r3 [-83.74,-76.46] | flangeB [-75.60,-72.10] | outer ear r3
  [-72.10,-68.10] (4 mm) | head outside.
Bolt built as: thread tip r2.5 x[-96,-88.1] + shank r3 [-88.1,-68.1]
  + head r5 [-68.1,-65.1].

Run: .venv/bin/python3 tools/fea/bolted_pilot.py [DT]
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import femlib as F  # noqa: E402

W = '/home/syaro/pyg_fea/work/bolted'
os.makedirs(W, exist_ok=True)
STEP = '/home/syaro/MikuchanRemote/Human-Pygmalion/refs/Huphy_1.0_STEP/Ankle2Feet.step'
AXY, AXZ = 195.5, -810.0
BALL_C = np.array([-80.10, AXY, AXZ])
BALL_R = 6.364
F_LC3 = np.array([-169.8, -481.8, 1116.2])       # measured worst-frame rod force
DT = float(sys.argv[1]) if len(sys.argv) > 1 else -235.0   # bolt cooldown -> preload
# Preload ceiling: this design taps straight into 6061-T6 (no nuts), so the
# aluminium internal thread - not the screw - sets the limit.
#   F_strip = 0.6*pi*D*L_e*0.577*sigma_y ;  usable = F_strip / 2
# M6 x 15 mm engagement here: 0.6*pi*6*15*159 = 27.0 kN -> 13.5 kN usable,
# so the ~7 kN target used below is inside the aluminium capacity.

PARTS = {'pillow': 'AnkleFeetPillowAB', 'ball': 'Inner Ball',
         'flangeA': '20deg_flangeA', 'flangeB': '20deg_flangeB'}


def build():
    sol = F.load_solids(STEP, min_vol_cm3=0.02)
    pick = {}
    pick['pillow'] = [s for s in sol if s['name'] == PARTS['pillow']][0]
    near = lambda s: abs(s['com'][0] - BALL_C[0]) < 12 and abs(s['com'][2] - AXZ) < 12
    pick['ball'] = [s for s in sol if s['name'] == 'Inner Ball' and near(s)][0]
    for k in ('flangeA', 'flangeB'):
        pick[k] = [s for s in sol if s['name'] == PARTS[k] and near(s)][0]
    for k, v in pick.items():
        print(f"  {k:8s} {v['vol_cm3']:6.2f} cm3  x[{v['bmin'][0]:.2f},{v['bmax'][0]:.2f}]")
    for k, v in pick.items():
        F.write_step([v], f'{W}/p_{k}.step')

    import gmsh
    gmsh.initialize()
    gmsh.option.setNumber('General.Terminal', 0)
    gmsh.model.add('bolted')
    vol = {}
    for k in pick:
        tags = gmsh.model.occ.importShapes(f'{W}/p_{k}.step')
        vol[k] = [t[1] for t in tags if t[0] == 3]
    b1 = gmsh.model.occ.addCylinder(-96.0, AXY, AXZ, 7.9, 0, 0, 2.5)
    b2 = gmsh.model.occ.addCylinder(-88.1, AXY, AXZ, 20.0, 0, 0, 3.0)
    b3 = gmsh.model.occ.addCylinder(-68.1, AXY, AXZ, 3.0, 0, 0, 5.0)
    bolt, _ = gmsh.model.occ.fuse([(3, b1)], [(3, b2), (3, b3)])
    vol['bolt'] = [t[1] for t in bolt if t[0] == 3]
    gmsh.model.occ.synchronize()
    for i, (k, vt) in enumerate(vol.items()):
        gmsh.model.addPhysicalGroup(3, vt, i + 1, name=k)
    f1 = gmsh.model.mesh.field.add('Ball')
    for k, v in [('Radius', 24.), ('VIn', 1.1), ('VOut', 3.6),
                 ('XCenter', BALL_C[0]), ('YCenter', AXY), ('ZCenter', AXZ)]:
        gmsh.model.mesh.field.setNumber(f1, k, v)
    f2 = gmsh.model.mesh.field.add('Ball')
    for k, v in [('Radius', 12.), ('VIn', 0.6), ('VOut', 3.6),
                 ('XCenter', BALL_C[0]), ('YCenter', AXY), ('ZCenter', AXZ)]:
        gmsh.model.mesh.field.setNumber(f2, k, v)
    fm = gmsh.model.mesh.field.add('Min')
    gmsh.model.mesh.field.setNumbers(fm, 'FieldsList', [f1, f2])
    gmsh.model.mesh.field.setAsBackgroundMesh(fm)
    gmsh.option.setNumber('Mesh.MeshSizeFromPoints', 0)
    gmsh.option.setNumber('Mesh.MeshSizeFromCurvature', 0)
    gmsh.option.setNumber('Mesh.OptimizeNetgen', 1)
    gmsh.option.setNumber('Mesh.SecondOrderLinear', 1)
    gmsh.model.mesh.generate(3)
    gmsh.model.mesh.setOrder(2)
    gmsh.write(f'{W}/bolted_mesh.inp')
    gmsh.finalize()
    return pick


def part_of_elset(nodes, elems, elsets):
    """gmsh writes VOLUMEn elsets; map them back to parts by x-extent."""
    out = {}
    for k, eids in elsets.items():
        P = np.array([nodes[n] for e in eids for n in elems[e][:4]])
        mn, mx = P.min(0), P.max(0)
        span = mx[0] - mn[0]
        if span > 100:
            out['pillow'] = k
        elif mn[0] < -95.5 and mx[0] > -66:
            out['bolt'] = k
        elif abs(mn[0] + 86.46) < 0.4:
            out['ball'] = k
        elif abs(mn[0] + 88.10) < 0.4:
            out['flangeA'] = k
        elif abs(mn[0] + 75.60) < 0.4:
            out['flangeB'] = k
    # the ball's meshed extent is the sphere, not its bbox -> assign by elimination
    left = [k for k in elsets if k not in out.values()]
    need = [p for p in ('pillow', 'ball', 'flangeA', 'flangeB', 'bolt') if p not in out]
    if len(left) == 1 and len(need) == 1:
        out[need[0]] = left[0]
    return out


def main():
    build()
    nodes, elems, elsets = F.parse_inp(f'{W}/bolted_mesh.inp')
    SET = part_of_elset(nodes, elems, elsets)
    assert len(SET) == 5, SET
    print('elsets ->', SET)
    NP = {k: sorted({n for e in elsets[v] for n in elems[e]}) for k, v in SET.items()}
    BF = {k: F.boundary_faces(elems, elsets[v]) for k, v in SET.items()}

    def faces(part, pred):
        s = F.sel_faces(BF[part], nodes, pred)
        assert len(s) > 3, part
        return s

    rax = lambda p: np.hypot(p[1] - AXY, p[2] - AXZ)
    tol = 0.06
    surf = {
        'earO_bore':  faces('pillow', lambda p: -72.16 <= p[0] <= -68.04 and abs(rax(p) - 3.0) < 0.2),
        'earO_out':   faces('pillow', lambda p: abs(p[0] + 68.10) < tol and rax(p) < 8.6),
        'earO_in':    faces('pillow', lambda p: abs(p[0] + 72.10) < tol and rax(p) < 8.6),
        'block_face': faces('pillow', lambda p: abs(p[0] + 88.10) < tol and rax(p) < 8.6),
        'block_tap':  faces('pillow', lambda p: -96.6 <= p[0] <= -88.0 and abs(rax(p) - 2.52) < 0.2),
        'bolt_shank': faces('bolt',   lambda p: -88.2 <= p[0] <= -68.0 and abs(rax(p) - 3.0) < 0.1),
        'bolt_tip':   faces('bolt',   lambda p: p[0] <= -88.0 and abs(rax(p) - 2.5) < 0.1),
        'bolt_headu': faces('bolt',   lambda p: abs(p[0] + 68.10) < tol and 3.05 < rax(p) < 5.05),
        'ball_bore':  faces('ball',   lambda p: abs(rax(p) - 3.0) < 0.15),
        'flA_bore':   faces('flangeA', lambda p: abs(rax(p) - 3.0) < 0.15 or abs(rax(p) - 3.9) < 0.15),
        'flB_bore':   faces('flangeB', lambda p: abs(rax(p) - 3.0) < 0.15 or abs(rax(p) - 3.9) < 0.15),
        'flA_face':   faces('flangeA', lambda p: abs(p[0] + 88.10) < tol),
        'flB_face':   faces('flangeB', lambda p: abs(p[0] + 72.10) < tol),
    }
    for k, v in surf.items():
        print(f'  surf {k}: {len(v)}')

    # cosine ball load along the measured rod force
    Fh = F_LC3 / np.linalg.norm(F_LC3)
    bs = sorted({n for tri in BF['ball'] for n in tri
                 if abs(np.linalg.norm(nodes[n] - BALL_C) - BALL_R) < 0.12})
    wts = {}
    for n in bs:
        nh = (nodes[n] - BALL_C) / np.linalg.norm(nodes[n] - BALL_C)
        w = float(nh @ Fh)
        if w > 0:
            wts[n] = w
    tot = sum(wts.values())
    cload = {n: F_LC3 * (w / tot) for n, w in wts.items()}
    fix = sorted(n for n in NP['pillow'] if abs(nodes[n][2] + 835.0) < 0.06)
    print(f'ball load nodes {len(wts)}/{len(bs)}, fixed {len(fix)}, '
          f'sum {np.round(sum(cload.values()), 1)} (target {F_LC3})')

    def wl(f, items, per=8):
        for i in range(0, len(items), per):
            f.write(','.join(str(v) for v in items[i:i + per]) + ',\n')

    with open(f'{W}/bolted.inp', 'w') as f:
        f.write('*NODE, NSET=NALL\n')
        for nid in sorted(nodes):
            x, y, z = nodes[nid]
            f.write(f'{nid}, {x:.6f}, {y:.6f}, {z:.6f}\n')
        for k, es in SET.items():
            f.write(f'*ELEMENT, TYPE=C3D10, ELSET=E{k.upper()}\n')
            for e in elsets[es]:
                c = elems[e]
                f.write(f'{e}, ' + ', '.join(map(str, c[:6])) + ',\n  '
                        + ', '.join(map(str, c[6:])) + '\n')
        f.write('*ELSET, ELSET=EALU\nEPILLOW,\n')
        f.write('*ELSET, ELSET=ESTEEL\nEBALL,EFLANGEA,EFLANGEB,\n')
        for k in SET:
            f.write(f'*NSET, NSET=N{k.upper()}\n')
            wl(f, NP[k])
        f.write('*NSET, NSET=FIX\n')
        wl(f, fix)
        for k, fl in surf.items():
            f.write(f'*SURFACE, NAME={k}, TYPE=ELEMENT\n')
            for e, fi in fl:
                f.write(f'{e}, S{fi}\n')
        f.write(f"""*MATERIAL, NAME=ALU
*ELASTIC
{F.AL['E']}, {F.AL['nu']}
*MATERIAL, NAME=STEEL
*ELASTIC
210000., 0.30
*MATERIAL, NAME=BOLTSTEEL
*ELASTIC
210000., 0.30
*EXPANSION
1.2E-5
*SOLID SECTION, ELSET=EALU, MATERIAL=ALU
*SOLID SECTION, ELSET=ESTEEL, MATERIAL=STEEL
*SOLID SECTION, ELSET=EBOLT, MATERIAL=BOLTSTEEL
*INITIAL CONDITIONS, TYPE=TEMPERATURE
NALL, 0.
""")
        for nm, sl, ma in [('T_THREAD', 'block_tap', 'bolt_tip'),
                           ('T_BALL', 'ball_bore', 'bolt_shank'),
                           ('T_FLA', 'flA_bore', 'bolt_shank'),
                           ('T_FLB', 'flB_bore', 'bolt_shank')]:
            f.write(f'*TIE, NAME={nm}, POSITION TOLERANCE=0.8\n{sl}, {ma}\n')
        f.write("""*SURFACE INTERACTION, NAME=SI1
*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR
5.E5
*FRICTION
0.15, 5.E4
""")
        for sl, ma in [('earO_bore', 'bolt_shank'), ('bolt_headu', 'earO_out'),
                       ('flB_face', 'earO_in'), ('flA_face', 'block_face')]:
            f.write(f'*CONTACT PAIR, INTERACTION=SI1, TYPE=NODE TO SURFACE\n{sl}, {ma}\n')
        f.write('*BOUNDARY\nFIX, 1, 3\n')
        f.write(f'*STEP\n*STATIC\n0.25, 1.0\n*TEMPERATURE\nNBOLT, {DT}\n'
                '*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n')
        f.write(f'*STEP\n*STATIC\n0.2, 1.0\n*TEMPERATURE\nNBOLT, {DT}\n*CLOAD\n')
        for n, v in sorted(cload.items()):
            for k in range(3):
                f.write(f'{n}, {k + 1}, {v[k]:.5f}\n')
        f.write('*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n')
    print('deck', os.path.getsize(f'{W}/bolted.inp') / 1e6, 'MB; solving...')
    r = F.run_ccx(W, 'bolted', threads=6, timeout=None)
    print('ok', r['ok'], r['errors'][:5])


if __name__ == '__main__':
    main()
