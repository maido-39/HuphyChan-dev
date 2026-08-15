"""femlib smoke test / regression: foot clevis (AnkleFeetPillowAB) under the
measured LC3 rod forces with cosine bearing loads on the JS6 bores.

Reference (docs/77 §9, red-team bearing model on the pre-update geometry):
bore peak ~194 MPa, artifact-filtered ~133 MPa. New CAD geometry differs, so
this checks the PIPELINE, not an exact number.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import femlib as F  # noqa: E402

W = '/home/syaro/pyg_fea/work/smoke'
os.makedirs(W, exist_ok=True)
STEP = '/home/syaro/MikuchanRemote/Human-Pygmalion/refs/Huphy_1.0_STEP/Ankle2Feet.step'
AXY, AXZ = 195.5, -810.0
ANC_A = np.array([-80.10, AXY, AXZ])
ANC_B = np.array([-167.30, AXY, AXZ])
F_A = np.array([-169.8, -481.8, 1116.2])
F_B = np.array([-103.7, -320.9, 805.4])

sol = F.load_solids(STEP, min_vol_cm3=1.0)
pil = [s for s in sol if s['name'] == 'AnkleFeetPillowAB']
assert len(pil) == 1, [s['name'] for s in sol]
print(f"clevis: {pil[0]['vol_cm3']} cm3  bbox z {pil[0]['bmin'][2]:.1f}..{pil[0]['bmax'][2]:.1f}")
sp = F.write_step(pil, f'{W}/clevis.step')

m = F.mesh_assembly(sp, f'{W}/clevis_mesh.inp', size_far=3.0,
                    refine=[(ANC_A[0], AXY, AXZ, 18., 0.9), (ANC_B[0], AXY, AXZ, 18., 0.9)])
print('mesh nodes', m['nodes'])
nodes, elems, elsets = F.parse_inp(f'{W}/clevis_mesh.inp')
allel = sorted(elems)
elsets = {'EPART': allel}
bf = F.boundary_faces(elems)
surf_nids = sorted({n for tri in bf for n in tri})

cloads = {}
for anc, Fv, tag in [(ANC_A, F_A, 'A'), (ANC_B, F_B, 'B')]:
    # both ears of this anchor: r3 bore nodes within +-12 mm of the anchor in x
    pred = F.cyl_pred('x', anc, 3.0, rtol=0.35, span=(anc[0] - 12, anc[0] + 12))
    nids = [n for n in surf_nids if pred(nodes[n])]
    print(f'  anchor {tag}: {len(nids)} bore nodes')
    assert len(nids) > 20
    for nid, f in F.bearing_load(nodes, nids, 'x', anc, Fv).items():
        cloads[nid] = cloads.get(nid, np.zeros(3)) + f

zmin = min(nodes[n][2] for n in nodes)
fix = F.sel_nodes(nodes, nodes, F.plane_pred('z', zmin, tol=0.06))
print(f'fixed {len(fix)} nodes at z={zmin:.1f}; total applied '
      f'{np.round(sum(cloads.values()), 1)} N (expect {np.round(F_A + F_B, 1)})')

F.write_deck(f'{W}/clevis.inp', nodes, elems, elsets, {'EPART': F.AL}, fix, cloads)
r = F.run_ccx(W, 'clevis', threads=6, timeout=3000)
print('solve ok', r['ok'], r['errors'][:3])
s = F.summarize(f'{W}/clevis.frd', load_nids=list(cloads), yield_=276.0)
for k, v in s.items():
    print(f'  {k}: {v}')
print(F.export_viewer_case(f'{W}/clevis.frd', f'{W}/clevis_mesh.inp', f'{W}/case_clevis.json',
                           'smoke: foot clevis, LC3 measured rod forces, cosine bearing bores',
                           case_key='smoke_clevis'))
