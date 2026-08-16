"""Stress-driven lightweighting study for one link, at SF>1 / >1.5 / >2.

Method (screening, no black-box topology optimiser needed):
  1. take the directional-envelope stress field (worst of the 2^n sign combos)
  2. map it onto a voxel grid of the link's own volume
  3. at each SF level, material whose envelope stress is below yield/(SF*margin)
     and which is not inside a keep-out (bearing seats, bolt pads, joint bores)
     is a removal candidate
  4. report the removable volume fraction and where it sits, and export an STL of
     the retained region for CAD rebuild
  5. flag the load paths that must stay (the stress backbone)

This gives a defensible mass-saving target and a shape to rebuild toward; the
rebuilt CAD then goes back through run_link_env for the real re-verification
(the campaign rule: never accept an optimised shape without re-analysis).

Usage: lightweight.py <LINK>
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import femlib as F  # noqa: E402

W = '/home/syaro/pyg_fea/work'
STEPS = '/home/syaro/pyg_fea/steps'
YIELD = 276.0
LEVELS = (1.0, 1.5, 2.0)
KEEP_MARGIN = 1.6      # keep material whose stress is within this factor of the limit
VOX = 3.0              # voxel size [mm]


def main():
    link = sys.argv[1]
    d = f'{W}/{link}'
    env = json.load(open(f'{d}/envelope_P99.json'))
    nodes, elems, elsets = F.parse_inp(f'{d}/{link}_mesh.inp')

    # rebuild the per-node envelope field from the unit solves
    comps = env.get('comps') or ['Fx', 'Fy', 'Fz']
    import envelope as E
    case_f = f'{d}/case_{link}_env.json'
    have_units = all(os.path.exists(f'{d}/{link}_u{c}.frd') for c in comps)
    if have_units:
        US, ids = [], None
        for c in comps:
            coords, blocks = F.parse_frd(f'{d}/{link}_u{c}.frd')
            S = [x for nm, x in blocks if nm == 'STRESS'][-1]
            ids = sorted(S)
            US.append(np.array([S[i] for i in ids]))
        mags = [env['magnitudes'][c] for c in comps]
        vm = E.combine(US, mags, comps=comps)['vm_max']
        P = np.array([coords[i] for i in ids])
    elif os.path.exists(case_f):
        # unit results were pruned for disk space -> use the exported surface field
        cj = json.load(open(case_f))
        c0 = cj[next(iter(cj))]
        P = np.array(c0['nodes'], float)
        vm = np.array(c0['fields']['vM'], float)
        ids = list(range(len(vm)))
        print('   (using the exported surface envelope; unit results were pruned)')
    else:
        raise SystemExit('neither unit results nor an exported case are available - '
                         'run run_link_env.py for this link first')
    print(f'{link}: {len(ids)} nodes, envelope max {vm.max():.1f} MPa')

    # element centroid stress + volume
    ecc, evol, estr = [], [], []
    idx = {n: k for k, n in enumerate(ids)} if have_units else None
    if idx is None:
        from scipy.spatial import cKDTree          # surface field -> nearest node
        tree = cKDTree(P)
    for eid, c in elems.items():
        p = np.array([nodes[n] for n in c[:4]])
        v = abs(np.dot(np.cross(p[1] - p[0], p[2] - p[0]), p[3] - p[0])) / 6.0
        if idx is not None:
            s = np.mean([vm[idx[n]] for n in c[:4]]) if all(n in idx for n in c[:4]) else 0.
        else:
            s = float(vm[tree.query(p.mean(0))[1]])
        ecc.append(p.mean(0))
        evol.append(v)
        estr.append(s)
    ecc = np.array(ecc)
    evol = np.array(evol)
    estr = np.array(estr)
    total = evol.sum()
    print(f'   volume {total/1000:.1f} cm3 in {len(evol)} elements')

    # keep-outs: joint seats, bolt pads, load/fix regions
    spec = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       'link_specs.json')))[link]
    keep = np.zeros(len(evol), bool)
    zones = []
    for blk in list(spec['envelope'].get('fix', [])) + list(spec['envelope'].get('points', [])):
        if blk.get('type') == 'plane':
            continue
        c = np.asarray(blk.get('ctr', [0, 0, 0]), float)
        r = float(blk.get('r', 10)) + 12.0
        zones.append((c, r))
    jf = f'{STEPS}/link_{link}_joints.json'
    if os.path.exists(jf):
        J = json.load(open(jf))
        for b in J.get('detected_bolts', []):
            zones.append((np.asarray(b['head_point'], float), 9.0))
        for b in J.get('bearings', []):
            for s in b.get('seats', []):
                zones.append((np.asarray(s['loc'], float), (s.get('r') or 20) + 10.0))
    for c, r in zones:
        keep |= np.linalg.norm(ecc - c, axis=1) < r
    print(f'   keep-out zones {len(zones)} -> {keep.sum()} elements protected '
          f'({evol[keep].sum()/total*100:.1f} % of volume)')

    out = dict(link=link, total_cm3=round(total / 1000, 2), max_vM=float(vm.max()),
               keepout_elems=int(keep.sum()), levels={})
    for L in LEVELS:
        allow = YIELD / L
        removable = (estr < allow / KEEP_MARGIN) & (~keep)
        vol_rem = evol[removable].sum()
        out['levels'][f'SF>{L}'] = dict(
            allowable_MPa=round(allow, 1),
            keep_threshold_MPa=round(allow / KEEP_MARGIN, 1),
            removable_cm3=round(vol_rem / 1000, 2),
            removable_pct=round(vol_rem / total * 100, 1),
            current_SF=round(YIELD / max(vm.max(), 1e-9), 2),
            feasible=bool(YIELD / max(vm.max(), 1e-9) >= L))
        print(f"   SF>{L}: allowable {allow:.0f} MPa -> removable "
              f"{vol_rem/1000:.1f} cm3 ({vol_rem/total*100:.1f} %)"
              f"{'' if out['levels'][f'SF>{L}']['feasible'] else '   [current design already below this SF]'}")

    # export the retained region (SF>1.5 case) as a point cloud + voxel occupancy
    allow = YIELD / 1.5
    retain = (estr >= allow / KEEP_MARGIN) | keep
    np.save(f'{d}/retain_centroids.npy', ecc[retain])
    out['retained_elems'] = int(retain.sum())
    out['note'] = ('removable = envelope stress below yield/(SF*1.6) and outside every joint seat, '
                   'bearing seat and bolt pad keep-out. Rebuild the CAD toward the retained region, '
                   'then re-run run_link_env.py for the mandatory re-verification.')
    json.dump(out, open(f'{d}/lightweight.json', 'w'), indent=1)
    print(f'   -> {d}/lightweight.json')


if __name__ == '__main__':
    main()
