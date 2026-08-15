"""Run a link's DIRECTIONAL LOAD ENVELOPE: six unit cases + 64 sign combos.

Also exports a setup JSON (mesh surface, fixed nodes, load nodes/vectors,
screws, bearings) for the 3-D setup viewer, so the boundary conditions and
loads of every link can be inspected visually.

Usage: run_link_env.py <LINK> [--peak]
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import femlib as F          # noqa: E402
import envelope as E        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = '/home/syaro/pyg_fea/steps'
WORK = '/home/syaro/pyg_fea/work'
LOADS = json.load(open(f'{HERE}/loads.json'))


def sel_bore(nodes, surf, s):
    """Node set of a load/BC region: a bore/seat cylinder or a planar patch."""
    if s.get('type') == 'plane':
        p = F.plane_pred(s['axis'], s['value'], tol=s.get('tol', 0.3),
                         box={k: tuple(v) for k, v in s.get('box', {}).items()})
    else:
        p = F.cyl_pred(s['axis'], s['ctr'], s['r'], rtol=s.get('rtol', 0.6), span=s.get('span'))
    n = [i for i in surf if p(nodes[i])]
    if len(n) < 12:
        raise SystemExit(f'selection too small ({len(n)}): {s}')
    return n


def main():
    link = sys.argv[1]
    stat = 'peak' if '--peak' in sys.argv else 'P99'
    setup_only = '--setup-only' in sys.argv
    factor = 1.0 if stat == 'peak' else 1.25
    spec = json.load(open(f'{HERE}/link_specs.json'))[link]
    W = f'{WORK}/{link}'
    os.makedirs(W, exist_ok=True)
    step = f'{STEPS}/link_{link}.step'
    if spec.get('subset'):
        sols = F.load_solids(step, min_vol_cm3=spec['subset'].get('min_vol_cm3', 0.0))
        keep = [s for i, s in enumerate(sols) if i in set(spec['subset']['indices'])]
        step = F.write_step(keep, f'{W}/{link}_subset.step')
    mesh_inp = f'{W}/{link}_mesh.inp'
    if not os.path.exists(mesh_inp):
        t0 = time.time()
        m = F.mesh_assembly(step, mesh_inp, size_far=spec['mesh']['size_far'],
                            refine=[tuple(r) for r in spec['mesh'].get('refine', [])])
        print(f"mesh {m['nodes']} nodes in {time.time() - t0:.0f}s", flush=True)
    nodes, elems, elsets = F.parse_inp(mesh_inp)
    elsets = {k: v for k, v in elsets.items() if v}
    bf = F.boundary_faces(elems)
    tris = [t for (_, _, t) in bf.values()]
    surf = sorted({n for tri in bf for n in tri})
    print(f'{len(nodes)} nodes / {len(elems)} elems / {len(surf)} surface nodes', flush=True)

    env_spec = spec['envelope']
    # ---- fixed set
    fix = []
    for B in env_spec['fix']:
        if B['type'] == 'plane':
            pred = F.plane_pred(B['axis'], B['value'], tol=B.get('tol', 0.2),
                                box={k: tuple(v) for k, v in B.get('box', {}).items()})
            fix += [n for n in surf if pred(nodes[n])]
        else:
            fix += sel_bore(nodes, surf, B)
    fix = sorted(set(fix))
    print(f'fixed nodes {len(fix)} ({env_spec["fix_desc"]})', flush=True)

    # ---- load points and their node sets
    pts = env_spec['points']
    for p in pts:
        p['nids'] = sel_bore(nodes, surf, p)
        print(f"  load point {p['name']}: {len(p['nids'])} nodes "
              f"({'plane patch' if p.get('type') == 'plane' else 'seat r' + str(p.get('r'))})",
              flush=True)

    if setup_only:
        # export BC/load/fastener setup without solving (visualisation pass)
        idx0 = {n: k for k, n in enumerate(sorted({t for tri in tris for t in tri}))}
        used0 = sorted(idx0)
        jf0 = f'{STEPS}/link_{link}_joints.json'
        joints0 = json.load(open(jf0)) if os.path.exists(jf0) else {}
        d0 = LOADS[env_spec['joint']][stat]
        setup0 = dict(link=link,
                      nodes=[[round(float(v), 2) for v in nodes[n]] for n in used0],
                      tris=[[idx0[a], idx0[b], idx0[c]] for a, b, c in tris],
                      fixed=[idx0[n] for n in fix if n in idx0],
                      fix_desc=env_spec['fix_desc'],
                      load_points=[dict(name=p['name'], ctr=p.get('ctr', [0, 0, 0]),
                                        axis=p.get('axis', 'z'), r=p.get('r', 10),
                                        nids=[idx0[n] for n in p['nids'] if n in idx0],
                                        share=p.get('share', 1.0)) for p in pts],
                      joint=env_spec['joint'], stat=stat, factor=factor,
                      magnitudes={c: round(d0[c] * factor, 1) for c in E.COMPS},
                      screws=joints0.get('screws', []), bearings=joints0.get('bearings', []),
                      envelope={})
        json.dump(setup0, open(f'{W}/setup_{link}.json', 'w'), separators=(',', ':'))
        print(f'setup-only: wrote setup_{link}.json ({len(used0)} surface nodes, '
              f'{len(setup0["fixed"])} fixed, {sum(len(p["nids"]) for p in setup0["load_points"])} loaded)')
        return

    # ---- six unit cases (each: all points loaded in that component)
    #
    # Bearing-pair statics (fixed 2026-08-15): a joint carried by TWO bearings
    # reacts a transverse moment as a FORCE COUPLE across the pair, not as a
    # local moment on each ring -- applying 239 N*m locally to a 22 mm 6900 seat
    # produced a bogus 475 MPa. The moment about the joint axis is the drive
    # torque and is delivered by the actuator path (pushrods here), so it is not
    # re-applied at the seats; `axial_moment` records what happens to it.
    pair = env_spec.get('pair_axis')
    pattern = env_spec.get('pattern')          # RBE3-style split over all attachments
    # default: forces + the measured motor torque about the joint axis only
    # (docs/64 transverse moment columns are reference-point contaminated)
    mode = env_spec.get('moment_mode', 'geometry')
    comps = list(E.COMPS_F) if mode == 'geometry' else list(E.COMPS)
    axial = env_spec.get('axial_torque_Nm')
    if mode == 'geometry' and axial:
        comps.append('Maxial')
    unit_stress = []
    load_nids = sorted({n for p in pts for n in p['nids']})
    axmap = {'x': 0, 'y': 1, 'z': 2}
    if pair:
        ai = axmap[pair]
        ctrs = np.array([p['ctr'] for p in pts], float)
        jc = np.array(env_spec.get('joint_centre', ctrs.mean(0)), float)
        span = float(abs(ctrs[0][ai] - ctrs[-1][ai]))
        print(f'bearing pair on {pair}-axis: spacing {span:.1f} mm, centre {jc.tolist()}',
              flush=True)
    if pattern:
        jc_p = np.array(env_spec.get('joint_centre', [0, 0, 0]), float)
        pp = np.array([p['ctr'] for p in pts], float)
        print(f'wrench pattern: {len(pts)} attachments, span '
              f'{np.round(pp.max(0) - pp.min(0), 1)} mm about {jc_p.tolist()}', flush=True)
    for k, comp in enumerate(comps):
        job = f'{link}_u{comp}'
        cl = {}
        if pattern:
            Fv = np.zeros(3); Mv = np.zeros(3)
            if comp.startswith('F'):
                Fv['xyz'.index(comp[1])] = E.UNIT_F
            elif comp == 'Maxial':
                Mv[axmap[env_spec['joint_axis']]] = E.UNIT_M * 1000.0
            else:
                Mv['xyz'.index(comp[1])] = E.UNIT_M * 1000.0
            fs = F.distribute_wrench([p['ctr'] for p in pts], jc_p, Fv, Mv)
            for p, fv in zip(pts, fs):
                d = F.bearing_load(nodes, p['nids'], p['axis'], p['ctr'], fv)
                for n, f in d.items():
                    cl[n] = cl.get(n, np.zeros(3)) + f
        elif pair and k >= 3:
            mi = k - 3
            if mi == ai:
                # drive torque about the joint axis: carried by the actuator path
                for p in pts:
                    d = F.moment_load(nodes, p['nids'], p['ctr'],
                                      np.eye(3)[mi] * E.UNIT_M * 1000.0 / len(pts))
                    for n, f in d.items():
                        cl[n] = cl.get(n, np.zeros(3)) + f
            else:
                # transverse moment -> force couple across the two seats
                Fmag = E.UNIT_M * 1000.0 / max(span, 1e-6)      # N
                dirv = np.cross(np.eye(3)[mi], np.eye(3)[ai])
                dirv = dirv / (np.linalg.norm(dirv) or 1.0)
                for p in pts:
                    sgn = 1.0 if (np.asarray(p['ctr'], float)[ai] > jc[ai]) else -1.0
                    d = F.bearing_load(nodes, p['nids'], p['axis'], p['ctr'],
                                       dirv * Fmag * sgn)
                    for n, f in d.items():
                        cl[n] = cl.get(n, np.zeros(3)) + f
        else:
            for p in pts:
                share = p.get('share', 1.0)
                if k < 3:
                    Fv = np.zeros(3)
                    Fv[k] = E.UNIT_F * share
                    if p.get('type') == 'plane':      # flat interface: uniform traction
                        d = {n: Fv / len(p['nids']) for n in p['nids']}
                    else:
                        d = F.bearing_load(nodes, p['nids'], p['axis'], p['ctr'], Fv)
                else:
                    Mv = np.zeros(3)
                    Mv[k - 3] = E.UNIT_M * 1000.0 * share      # N*m -> N*mm
                    d = F.moment_load(nodes, p['nids'], p['ctr'], Mv)
                for n, f in d.items():
                    cl[n] = cl.get(n, np.zeros(3)) + f
        if not os.path.exists(f'{W}/{job}.frd'):
            F.write_deck(f'{W}/{job}.inp', nodes, elems, elsets,
                         {e: F.AL for e in elsets}, fix, cl)
            t0 = time.time()
            r = F.run_ccx(W, job, threads=spec.get('threads', 6))
            print(f'  unit {comp}: solve ok={r["ok"]} in {time.time() - t0:.0f}s '
                  f'{r["errors"][:1]}', flush=True)
            if not r['ok']:
                raise SystemExit(f'unit case {comp} failed: {r["errors"][:3]}')
        coords, blocks = F.parse_frd(f'{W}/{job}.frd')
        S = [d for nm, d in blocks if nm == 'STRESS'][-1]
        ids = sorted(S)
        unit_stress.append(np.array([S[i] for i in ids]))
    ids = np.array(ids)
    P = np.array([coords[i] for i in ids])

    # ---- envelope over sign combinations
    mags = []
    j = env_spec['joint']
    d = LOADS[j][stat]
    for c in comps:
        mags.append(axial if c == 'Maxial' else d[c] * factor)
    env = E.combine(unit_stress, mags, comps=comps)
    summ = E.summarize(env, P, ids, load_nids=load_nids)
    summ.update(link=link, joint=j, stat=stat, factor=factor,
                pair_axis=env_spec.get('pair_axis'),
                comps=comps,
                moment_model=(('forces + measured motor torque about the joint axis; '
                               'transverse bending is generated by the geometry '
                               '(docs/64 moment columns are reference-point contaminated, '
                               'SS8i) | ' if mode == 'geometry' else '') +
                              'wrench distributed over all real attachments '
                              '(RBE3-like least-norm split: bearings + rod anchors)'
                              if env_spec.get('pattern') else
                              'transverse moments as a force couple across the bearing '
                              'pair; axial moment = drive torque via the actuator path'
                              if env_spec.get('pair_axis') else
                              'moments applied locally at the single seat (conservative)'),
                magnitudes=dict(zip(comps, [round(m, 1) for m in mags])),
                mesh_nodes=len(nodes), n_fixed=len(fix), n_loaded=len(load_nids))
    print('\nENVELOPE ' + json.dumps(summ, indent=1), flush=True)
    json.dump(summ, open(f'{W}/envelope_{stat}.json', 'w'), indent=1)

    # ---- viewer case (envelope field) + setup JSON
    idx = {n: k for k, n in enumerate(ids)}
    used = sorted({t for tri in tris for t in tri if t in idx})
    ridx = {n: k for k, n in enumerate(used)}
    vm = env['vm_max']
    case = dict(nodes=[[round(float(v), 2) for v in nodes[n]] for n in used],
                disp=[[0.0, 0.0, 0.0] for _ in used],
                tris=[[ridx[a], ridx[b], ridx[c]] for a, b, c in tris
                      if a in ridx and b in ridx and c in ridx],
                fields=dict(vM=[round(float(vm[idx[n]]), 2) for n in used]),
                desc=f'{link} {j} {stat}x{factor} directional envelope (64 sign combos): '
                     f'max {summ["max_vM"]:.1f} MPa, filtered '
                     f'{summ.get("max_vM_filtered", float("nan")):.1f} MPa')
    json.dump({f'{link}_env_{stat}': case}, open(f'{W}/case_{link}_env.json', 'w'),
              separators=(',', ':'))

    jf = f'{STEPS}/link_{link}_joints.json'
    joints = json.load(open(jf)) if os.path.exists(jf) else {}
    setup = dict(link=link,
                 nodes=[[round(float(v), 2) for v in nodes[n]] for n in used],
                 tris=case['tris'],
                 fixed=[ridx[n] for n in fix if n in ridx],
                 fix_desc=env_spec['fix_desc'],
                 load_points=[dict(name=p['name'], ctr=p.get('ctr', [0, 0, 0]),
                                   axis=p.get('axis', 'z'), r=p.get('r', 10),
                                   nids=[ridx[n] for n in p['nids'] if n in ridx],
                                   share=p.get('share', 1.0)) for p in pts],
                 joint=j, stat=stat, factor=factor,
                 magnitudes=summ['magnitudes'],
                 screws=joints.get('screws', []), bearings=joints.get('bearings', []),
                 envelope=summ)
    json.dump(setup, open(f'{W}/setup_{link}.json', 'w'), separators=(',', ':'))
    print(f'wrote setup_{link}.json ({len(used)} surf nodes) and case_{link}_env.json')


if __name__ == '__main__':
    main()
