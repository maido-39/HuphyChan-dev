"""Run the load cases of one link from a spec in tools/fea/link_specs.json.

Joint modelling (see xcaf_links.py header for why):
  * loads and supports act on the real bearing SEAT cylinders located by
    assign_bearings.py, spread over the loaded arc (femlib.bearing_load)
  * actuator/mating-face reactions act on the real screw washer footprints
    (femlib.washer_footprints), never on a whole face
  * CAD screws and rolling elements are NOT meshed (bonding them would create
    rigid threads / rigid ball lumps)

Usage: run_link.py <LINK> [case ...]
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import femlib as F  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = '/home/syaro/pyg_fea/steps'
WORK = '/home/syaro/pyg_fea/work'
LOADS = json.load(open(f'{HERE}/loads.json'))


def sel_bore(nodes, surf, spec):
    """Nodes on a seat/bore cylinder: {axis, ctr, r, span, rtol}."""
    p = F.cyl_pred(spec['axis'], spec['ctr'], spec['r'],
                   rtol=spec.get('rtol', 0.6), span=spec.get('span'))
    n = [i for i in surf if p(nodes[i])]
    if len(n) < 12:
        raise SystemExit(f'bore selection too small ({len(n)}): {spec}')
    return n


def wrench(joint, kind, factor):
    d = LOADS[joint][kind]
    return (np.array([d['Fx'], d['Fy'], d['Fz']]) * factor,
            np.array([d['Mx'], d['My'], d['Mz']]) * factor)


def main():
    link = sys.argv[1]
    only = set(sys.argv[2:])
    spec = json.load(open(f'{HERE}/link_specs.json'))[link]
    W = f'{WORK}/{link}'
    os.makedirs(W, exist_ok=True)
    step = f'{STEPS}/link_{link}.step'
    mesh_inp = f'{W}/{link}_mesh.inp'

    # optional physical subset: a CAD sub-assembly can span more than one
    # kinematic link (Ankle2Feet holds foot + shin plates + cranks + rods).
    # Meshing only the link's own solids also avoids fragment blowing up on the
    # concentric rod-end shell/bushing/ball stack.
    sub = spec.get('subset')
    if sub:
        sols = F.load_solids(step, min_vol_cm3=sub.get('min_vol_cm3', 0.0))
        keep = [s for i, s in enumerate(sols) if i in set(sub['indices'])] \
            if 'indices' in sub else \
            [s for s in sols if sub.get('zmax', 1e9) >= s['bmax'][2] >= sub.get('zmin', -1e9)]
        print('subset:', [(round(s['vol_cm3'], 1), [round(v) for v in s['com']]) for s in keep])
        step = F.write_step(keep, f'{W}/{link}_subset.step')

    if not os.path.exists(mesh_inp):
        t0 = time.time()
        m = F.mesh_assembly(step, mesh_inp, size_far=spec['mesh']['size_far'],
                            refine=[tuple(r) for r in spec['mesh'].get('refine', [])])
        print(f"mesh: {m['nodes']} nodes in {time.time()-t0:.0f}s", flush=True)
    nodes, elems, elsets = F.parse_inp(mesh_inp)
    elsets = {k: v for k, v in elsets.items() if v}
    print(f'{len(nodes)} nodes, {len(elems)} elems, {len(elsets)} volumes', flush=True)
    bf = F.boundary_faces(elems)
    surf = sorted({n for tri in bf for n in tri})

    out = {}
    for case in spec['cases']:
        if only and case['name'] not in only:
            continue
        job = f"{link}_{case['name']}"
        cload, tags = {}, []

        def add(d):
            for n, f in d.items():
                cload[n] = cload.get(n, np.zeros(3)) + np.asarray(f, float)

        for L in case['loads']:
            nids = sel_bore(nodes, surf, L)
            if L['kind'] == 'wrench':
                Fv, Mv = wrench(L['joint'], L['stat'], L.get('factor', 1.0))
                Fv = Fv * np.array(L.get('fsign', [1, 1, 1]))
                Mv = Mv * np.array(L.get('msign', [1, 1, 1]))
                if L.get('force', True):
                    add(F.bearing_load(nodes, nids, L['axis'], L['ctr'], Fv))
                if L.get('moment', True):
                    add(F.moment_load(nodes, nids, L['ctr'], Mv))
                tags.append(f"{L['joint']}/{L['stat']}x{L.get('factor',1)} F{np.round(Fv,0)} M{np.round(Mv,0)} on r{L['r']} {L['axis']}-seat @{L['ctr']} ({len(nids)}n)")
            elif L['kind'] == 'force':
                add(F.bearing_load(nodes, nids, L['axis'], L['ctr'], np.array(L['F'])))
                tags.append(f"F{L['F']} on r{L['r']} {L['axis']}-seat @{L['ctr']} ({len(nids)}n)")
            elif L['kind'] == 'moment':
                add(F.moment_load(nodes, nids, L['ctr'], np.array(L['M'])))
                tags.append(f"M{L['M']} on r{L['r']} {L['axis']}-seat @{L['ctr']} ({len(nids)}n)")
        for P in case.get('patch_loads', []):     # planar patch (e.g. GRF on the sole)
            pred = F.plane_pred(P['axis'], P['value'], tol=P.get('tol', 0.2),
                                box={k: tuple(v) for k, v in P.get('box', {}).items()})
            nids = [n for n in surf if pred(nodes[n])]
            if len(nids) < 10:
                raise SystemExit(f'patch too small ({len(nids)}): {P}')
            Fv = np.array(P['F'], float)
            for n in nids:
                cload[n] = cload.get(n, np.zeros(3)) + Fv / len(nids)
            tags.append(f"patch F{P['F']} on {P['axis']}={P['value']} ({len(nids)}n)")

        fix = []
        for B in case['fix']:
            if B['type'] == 'plane':
                pred = F.plane_pred(B['axis'], B['value'], tol=B.get('tol', 0.2),
                                    box={k: tuple(v) for k, v in B.get('box', {}).items()})
                fix += [n for n in surf if pred(nodes[n])]
            elif B['type'] == 'bore':
                fix += sel_bore(nodes, surf, B)
        fix = sorted(set(fix))
        if len(fix) < 20:
            raise SystemExit(f'fix set too small: {len(fix)}')
        tot = np.round(sum(cload.values()), 1)
        print(f'\n[{job}] {len(cload)} loaded nodes, sum F = {tot} N; {len(fix)} fixed', flush=True)
        for t in tags:
            print('   +', t, flush=True)

        F.write_deck(f'{W}/{job}.inp', nodes, elems, elsets,
                     {k: F.AL for k in elsets}, fix, cload)
        t0 = time.time()
        r = F.run_ccx(W, job, threads=spec.get('threads', 6))
        print(f'   solve ok={r["ok"]} in {time.time()-t0:.0f}s {r["errors"][:2]}', flush=True)
        if not r['ok']:
            out[case['name']] = dict(error=r['errors'][:5] or 'no frd')
            continue
        s = F.summarize(f'{W}/{job}.frd', load_nids=list(cload), yield_=276.0,
                        sf_load=1.0)   # the load factor is already in the case
        s['applied_sum_N'] = [float(v) for v in tot]
        out[case['name']] = s
        print('   ' + json.dumps(s), flush=True)

    json.dump(out, open(f'{W}/results.json', 'w'), indent=1)
    best = max((k for k in out if 'max_vM' in out[k]), key=lambda k: out[k]['max_vM'], default=None)
    if best:
        F.export_viewer_case(f'{W}/{link}_{best}.frd', mesh_inp, f'{W}/case_{link}.json',
                             f'{link} {best}: ' + spec['cases'][0].get('desc', ''),
                             case_key=f'{link}_{best}')
        print(f'\nworst case {best}: {out[best]["max_vM"]:.1f} MPa -> viewer case written')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
