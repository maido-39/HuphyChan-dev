"""Export the full viewer field set for every solved link - no re-solve.

The campaign only carried von Mises into the viewer, which is the one field a
post-processor must have and the only one it had. This reads the unit results that
are already on disk and writes, per link, the fields an FEA post-processor is
normally expected to show:

  envelope   vM_env  - worst von Mises over the 2^n sign combinations (the design field)
             SF      - yield / vM_env, the safety-factor field
  governing  vM, S1, S3, Sxx..Szx, U (vector) - the single signed load case that
             load case  produces the global peak, so the deformed shape and the
                        principal directions belong to one real solution rather
                        than a per-node mixture
  geometry   keepout - node sits in a bearing seat / bolt pad / joint bore, i.e.
                       material the lightweighting study may not remove

Node order matches femlib.export_viewer_case (sorted surface node ids), so the
arrays line up with the setup payload the viewer already loads.

Usage: export_fields.py [LINK ...]
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import envelope as E  # noqa: E402
import femlib as F  # noqa: E402

W = '/home/syaro/pyg_fea/work'
STEPS = '/home/syaro/pyg_fea/steps'
YIELD = 276.0


def keepout_mask(link, spec, P):
    """Nodes inside a joint seat, bearing seat or bolt pad - never removable."""
    zones = []
    env = spec['envelope']
    for blk in list(env.get('fix', [])) + list(env.get('points', [])):
        if blk.get('type') == 'bolt_pads':
            for q in blk['points']:
                zones.append((np.asarray(q, float), 9.0))
        elif blk.get('ctr'):
            zones.append((np.asarray(blk['ctr'], float), float(blk.get('r', 10)) + 12.0))
    jf = f"{STEPS}/link_{spec.get('geometry_of', link)}_joints.json"
    if os.path.exists(jf):
        J = json.load(open(jf))
        for b in J.get('detected_bolts', []):
            zones.append((np.asarray(b['head_point'], float), 9.0))
        for b in J.get('bearings', []):
            for s in b.get('seats', []):
                zones.append((np.asarray(s['loc'], float), (s.get('r') or 20) + 10.0))
    m = np.zeros(len(P), bool)
    for c, r in zones:
        m |= np.linalg.norm(P - c, axis=1) < r
    return m


def one(link, specs):
    d = f'{W}/{link}'
    res = f'{d}/envelope_P99.json'
    if not os.path.exists(res):
        return f'{link}: no result'
    env = json.load(open(res))
    comps = env.get('comps') or ['Fx', 'Fy', 'Fz']
    frds = [f'{d}/{link}_u{c}.frd' for c in comps]
    if not all(os.path.exists(x) for x in frds):
        return f'{link}: unit results pruned - cannot export fields'
    nodes, elems, _ = F.parse_inp(f'{d}/{link}_mesh.inp')
    tris = [tri for (_, _, tri) in F.boundary_faces(elems).values()]
    used = sorted({t for tri in tris for t in tri})
    idx = {n: k for k, n in enumerate(used)}

    US, UU, ids = [], [], None
    for f in frds:
        coords, blocks = F.parse_frd(f)
        S = [x for nm, x in blocks if nm == 'STRESS'][-1]
        U = [x for nm, x in blocks if nm == 'DISP'][-1]
        ids = sorted(S)
        US.append(np.array([S[i] for i in ids]))
        UU.append(np.array([U.get(i, (0, 0, 0)) for i in ids]))
    mags = [env['magnitudes'][c] for c in comps]
    comb = E.combine(US, mags, comps=comps)

    # restrict everything to the surface nodes, in viewer order
    pos = {n: k for k, n in enumerate(ids)}
    sel = np.array([pos[n] for n in used if n in pos])
    keep = [n for n in used if n in pos]
    if len(keep) != len(used):
        return f'{link}: {len(used) - len(keep)} surface nodes missing from the results'

    vm_env = comb['vm_max'][sel]
    # the single signed case that produces the global peak
    gsign = comb['signs'][comb['sign_idx'][int(comb['vm_max'].argmax())]]
    scale = np.array([mags[i] / (1.0 if comps[i] == 'Gbody'
                                 else (E.UNIT_F if comps[i][0] == 'F' else E.UNIT_M))
                      for i in range(len(comps))])
    Sg = np.tensordot(gsign * scale, np.array(US), axes=(0, 0))[sel]
    Ug = np.tensordot(gsign * scale, np.array(UU), axes=(0, 0))[sel]
    sxx, syy, szz, sxy, syz, szx = Sg.T
    vm_g = F.von_mises(Sg)
    P1 = np.zeros(len(sel))
    P3 = np.zeros(len(sel))
    for k in range(len(sel)):
        T = np.array([[sxx[k], sxy[k], szx[k]],
                      [sxy[k], syy[k], syz[k]],
                      [szx[k], syz[k], szz[k]]])
        ev = np.linalg.eigvalsh(T)
        P1[k], P3[k] = ev[2], ev[0]

    P = np.array([nodes[n] for n in used])
    ko = keepout_mask(link, specs[link], P)
    r = lambda a, n=2: [round(float(v), n) for v in a]        # noqa: E731
    out = dict(
        link=link, n=len(used), governing_signs=dict(zip(comps, gsign.tolist())),
        fields=dict(vM_env=r(vm_env), SF=r(YIELD / np.maximum(vm_env, 1e-6), 3),
                    vM=r(vm_g), S1=r(P1), S3=r(P3),
                    Sxx=r(sxx), Syy=r(syy), Szz=r(szz),
                    Sxy=r(sxy), Syz=r(syz), Szx=r(szx),
                    # the model is in mm with E in MPa, so CalculiX returns mm directly
                    U_mag=r(np.linalg.norm(Ug, axis=1), 4),
                    Ux=r(Ug[:, 0], 4), Uy=r(Ug[:, 1], 4), Uz=r(Ug[:, 2], 4)),
        disp=[[round(float(v), 4) for v in q] for q in Ug],          # mm, for the deformed shape
        keepout=[int(b) for b in ko])
    json.dump(out, open(f'{d}/fields.json', 'w'), separators=(',', ':'))
    return (f"{link}: {len(used)} surface nodes, envelope max {vm_env.max():.1f} MPa, "
            f"governing case max {vm_g.max():.1f} MPa, peak displacement "
            f"{np.linalg.norm(Ug, axis=1).max():.3f} mm, "
            f"{int(ko.sum())} nodes in keep-outs "
            f"-> {os.path.getsize(f'{d}/fields.json') / 1e6:.1f} MB")


def main():
    specs = json.load(open(f'{HERE}/link_specs.json'))
    links = sys.argv[1:] or sorted(os.path.basename(os.path.dirname(f))
                                   for f in glob.glob(f'{W}/*/envelope_P99.json'))
    for L in links:
        try:
            print(one(L, specs), flush=True)
        except Exception as e:                       # one bad link must not stop the rest
            print(f'{L}: FAILED {e.__class__.__name__}: {e}', flush=True)


if __name__ == '__main__':
    main()
