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
    """Node set of a load/BC region: bore/seat cylinder, planar patch, or the
    annular pads under a set of screw heads (the real bolted footprint)."""
    if s.get('type') == 'bolt_pads':
        ai = {'x': 0, 'y': 1, 'z': 2}[s['axis']]
        oi = [i for i in range(3) if i != ai]
        rp, dep = float(s.get('r_pad', 4.0)), float(s.get('depth', 2.0))
        pts = [np.asarray(q, float) for q in s['points']]
        out = []
        for n in surf:
            v = nodes[n]
            for q in pts:
                if abs(v[ai] - q[ai]) <= dep and \
                   np.hypot(v[oi[0]] - q[oi[0]], v[oi[1]] - q[oi[1]]) <= rp:
                    out.append(n)
                    break
        if len(out) < 12:
            raise SystemExit(f'bolt_pads selection too small ({len(out)}): {s.get("_desc", s)}')
        return out
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
    # per-link lock: two runs of the same link share job names and the same
    # envelope_*.json, so an overlapping stale run silently overwrites the good
    # result (2026-08-15: a 6-component run finished after the 4-component one
    # and left 589 MPa on disk where the correct answer was 127 MPa).
    import fcntl
    lockf = open(f'/tmp/pyg_link_{link}.lock', 'w')
    try:
        fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(f'another run for {link} is active - refusing to share its work dir')
    stat = 'peak' if '--peak' in sys.argv else 'P99'
    setup_only = '--setup-only' in sys.argv
    factor = 1.0 if stat == 'peak' else 1.25
    spec = json.load(open(f'{HERE}/link_specs.json'))[link]
    import hashlib
    spec_hash = hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
    W = f'{WORK}/{link}'
    os.makedirs(W, exist_ok=True)
    # a link may be analysed under more than one load case (the foot is loaded
    # at the heel and again at the forefoot); the extra entry names the same CAD
    geo = spec.get('geometry_of', link)
    step = f'{STEPS}/link_{geo}.step'
    if spec.get('subset'):
        sols = F.load_solids(step, min_vol_cm3=spec['subset'].get('min_vol_cm3', 0.0))
        keep = [s for i, s in enumerate(sols) if i in set(spec['subset']['indices'])]
        step = F.write_step(keep, f'{W}/{link}_subset.step')
        if spec['mesh'].get('repair_overlaps'):
            step, ncut = F.resolve_overlaps(step, f'{W}/{link}_repaired.step')
            print(f'   geometry repair: {ncut} interpenetrations cut', flush=True)
        print(f'subset: {len(keep)}/{len(sols)} solids, '
              f'{sum(s["vol_cm3"] for s in keep):.1f} cm3', flush=True)
    mesh_inp = f'{W}/{link}_mesh.inp'
    # actuator bodies are structural members of the link: their housings are
    # bolted into the load path, so they must be meshed with it
    steps = [step]
    # Actuators are structural: their housings close the load path between links.
    # The real RS03/RS04 solids carry ~3600 faces each and take >15 min just to
    # tessellate, so they enter as measured-envelope CYLINDER PROXIES (same OD,
    # length and position; aluminium stiffness = the softer, load-shedding
    # choice, so the link itself is judged conservatively). Bolt-level detail at
    # the flange is a separate submodel, not part of the screening.
    # Motors: modelled as RIGID BODIES on their mounting flanges with the motor
    # mass at a reference node (femlib.rigid_motor). Meshing the real housings or
    # even envelope cylinders was unsolvable (527k nodes / 1031 MPCs); a housing
    # is far stiffer than the bracket anyway, so a rigid flange + point mass is
    # both cheaper and the standard treatment. Their weight enters through the
    # gravity/inertia unit case, their torque through the axial-moment case.
    motors = []
    PJ = f'{STEPS}/actuator_proxies.json'
    if spec.get('actuators') and os.path.exists(PJ):
        allp = json.load(open(PJ))
        motors = [dict(allp[a], name=a) for a in spec['actuators'] if a in allp]
        print('motors (rigid + point mass): ' + ', '.join(
            f"{m['name'].replace('robstride_','')} {m.get('mass_kg', 1.5)} kg" for m in motors),
            flush=True)
    # a link may declare its own budget: L3 only meshes at all near 21.6 mm, so
    # blindly coarsening it to fit the global budget just walked it into the
    # PLC errors it had already failed on
    MAX_NODES = int(spec['mesh'].get('max_nodes')
                    or os.environ.get('PYG_MAX_NODES', 420000))
    if not os.path.exists(mesh_inp):
        size = spec['mesh']['size_far']
        ref = [tuple(r) for r in spec['mesh'].get('refine', [])]
        # make sure the fix/load interfaces themselves are resolved: a bolt pad
        # that only catches a handful of nodes carries the whole reaction and
        # produces a fake 300 MPa spike (L2, 2026-08-16)
        # Keep this gentle: 60 fine balls on a big link made gmsh's size field so
        # ragged that HXT and Delaunay both failed on geometry that meshes fine
        # with the plain spec (L3, 2026-08-16). Refine enough to resolve a pad,
        # no more, and cap the count.
        fine = max(2.5, min(6.0, size / 3.0))
        cap = 16 if size > 12 else (24 if size > 10 else 40)
        auto = []
        for blk in ([] if spec['mesh'].get('auto_refine') is False else
                    list(spec['envelope'].get('fix', [])) + list(spec['envelope'].get('points', []))):
            if blk.get('type') == 'bolt_pads':
                for q_ in blk['points']:
                    auto.append((q_[0], q_[1], q_[2], 14.0, fine))
            elif blk.get('type') == 'bore' and blk.get('ctr'):
                auto.append((blk['ctr'][0], blk['ctr'][1], blk['ctr'][2],
                             float(blk.get('r', 10)) + 12.0, fine))
        if spec['mesh'].get('auto_refine') is False:
            print('   auto-refine disabled for this link (it destabilised the mesher)',
                  flush=True)
        if auto:
            ref = ref + auto[:cap]
            print(f'   auto-refine at {len(auto[:cap])} BC features (size {fine:.1f} mm)',
                  flush=True)
        for attempt in range(4):
            t0 = time.time()
            m = F.mesh_assembly(steps, mesh_inp, size_far=size, refine=ref,
                                fragment=spec['mesh'].get('fragment', True),
                                curv=spec['mesh'].get('curv'))
            print(f"mesh {m['nodes']} nodes in {time.time() - t0:.0f}s "
                  f"(size_far {size})", flush=True)
            if m['nodes'] <= MAX_NODES:
                break
            if attempt == 3:        # keep the last mesh: deleting it left the
                print(f'   still over budget at {m["nodes"]} nodes - proceeding '
                      'with the coarsest mesh', flush=True)   # run with no mesh file at all
                break
            # Relax the refinement balls FIRST and only then the global size:
            # they dominate the node count on a big link, and the global size is
            # the parameter that decides whether the geometry meshes at all
            # (L3 meshes at 21.6 mm and throws PLC errors when coarsened).
            if attempt < 2 and ref:
                ref = [(x, y, z, r * 0.7, sz * 1.45) for (x, y, z, r, sz) in ref]
                print(f'   over the {MAX_NODES} node budget - relaxing the local '
                      f'refinement, keeping size_far at {size:.1f} mm', flush=True)
            else:
                size *= 1.35
                ref = [(x, y, z, r * 0.85, sz * 1.35) for (x, y, z, r, sz) in ref]
                print(f'   over the {MAX_NODES} node budget - remeshing at {size:.1f} mm',
                      flush=True)
            os.remove(mesh_inp)
        spec['mesh']['size_far'] = round(size, 2)
        spec['mesh']['refine'] = [[x, y, z, r, round(sz, 2)] for (x, y, z, r, sz) in ref]
        allspec = json.load(open(f'{HERE}/link_specs.json'))
        allspec[link]['mesh'] = spec['mesh']
        json.dump(allspec, open(f'{HERE}/link_specs.json', 'w'), indent=1)
        spec_hash = hashlib.sha1(
            json.dumps(allspec[link], sort_keys=True).encode()).hexdigest()[:12]
    if not os.path.exists(mesh_inp):
        raise SystemExit('mesh file missing after the meshing stage - see the log above')
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

    # ---- motors: flange node sets, reference nodes, point masses
    tie_txt = ''            # deck fragment: motor rigid bodies + component ties
    mot_txt, mot_nodes, mot_mass = '', {}, {}
    # CalculiX refuses a node that sits in a *RIGID BODY and in an *EQUATION at
    # the same time ("dof ... to a rigid body is detected in another equation"),
    # which killed every L2 solve. Track rigid membership and keep the ties off.
    rigid_nodes = set()
    if motors:
        nid0 = max(nodes) + 1
        for k, m in enumerate(motors):
            ax = {'x': 0, 'y': 1, 'z': 2}[m['axis']]
            c = np.asarray(m['ctr'], float)
            # prefer the real bolt pattern of this actuator (detected bolts whose
            # parts/links name it); a fat cylindrical grab rigidified 15,040 nodes
            # of the thigh on the first try, which is neither physical nor solvable
            jf = f'{STEPS}/link_{geo}_joints.json'
            pads = []
            if os.path.exists(jf):
                short = m['name'].replace('robstride_', '')
                for b_ in json.load(open(jf)).get('detected_bolts', []):
                    tag = ' '.join(str(v) for v in (b_.get('links') or [])) + ' ' + \
                          ' '.join(str(v) for v in (b_.get('parts') or {}).values())
                    if short in tag.lower():
                        pads.append((np.asarray(b_['head_point'], float),
                                     np.asarray(b_['axis'], float)))
            fixset = set(fix)
            flange = []
            if pads:
                for n in surf:
                    if n in fixset:
                        continue
                    v = nodes[n]
                    for q, qa in pads:
                        d = v - q
                        if abs(float(d @ qa)) < 6.0 and \
                           np.linalg.norm(d - (d @ qa) * qa) < 6.0:
                            flange.append(n)
                            break
            if len(flange) < 20:      # fallback: thin annulus at the housing face
                flange = [n for n in surf
                          if n not in fixset
                          and abs(abs(nodes[n][ax] - c[ax]) - m['len'] / 2) < 4.0
                          and np.linalg.norm(np.delete(nodes[n] - c, ax)) < m['r'] + 4.0]
            if len(flange) > 1200:    # keep the rigid patch modest
                flange = flange[::max(1, len(flange) // 1200)]
            flange = [n for n in flange if n not in rigid_nodes]   # one body per node
            if fix:
                fp = np.array([nodes[n] for n in fix])
                flange = [n for n in flange
                          if float(np.linalg.norm(fp - nodes[n], axis=1).min()) > 15.0]
            if len(flange) < 20:
                print(f"   WARNING: motor {m['name']} found only {len(flange)} flange nodes "
                      '- check the proxy placement', flush=True)
                continue
            ref = nid0 + k
            mot_nodes[ref] = c
            mot_mass[ref] = m.get('mass_kg', 1.5) / 1000.0        # tonne
            rigid_nodes.update(flange)
            mot_txt += F.rigid_motor(nodes, flange, ref, str(k))
            print(f"   motor {m['name'].replace('robstride_','')}: {len(flange)} flange nodes, "
                  f"ref node {ref}, {m.get('mass_kg', 1.5)} kg", flush=True)
    tie_txt += mot_txt

    # bolted bodies come out as separate mesh components -> tie them at the
    # flange contact, otherwise the floating body makes the solve singular
    comps_e = F.components(elems)
    print(f'mesh connectivity: {len(comps_e)} component(s) {[len(c) for c in comps_e[:4]]}',
          flush=True)
    bridged = set()
    for txt_i in mot_txt.split('*NSET, NSET=NMOT')[1:]:
        body = txt_i.split('*RIGID BODY')[0]
        for tok in body.replace('\n', ',').split(','):
            tok = tok.strip()
            if tok.isdigit():
                bridged.add(int(tok))
    # Components must be joined like the real assembly: a chain. Tying every
    # component to the LARGEST one failed on L4, where the two side plates are
    # 53.5 mm apart but each sits 0.05 mm from the bottom plate between them.
    # Grow a connected set instead, always tying the next-nearest component to
    # whatever is already connected.
    joined = set(comps_e[0])
    pending = list(comps_e[1:])
    guard = 0
    while pending and guard < 40:
        guard += 1
        best = None
        for idx, c in enumerate(pending):
            for g in (3.0, 6.0, 12.0, 25.0, 40.0):
                txt, n = F.node_pair_equations(nodes, elems, joined, c, gap=g,
                                               exclude=set(fix) | rigid_nodes)
                if n:
                    best = (idx, txt, n, g)
                    break
            if best:
                break
        if best is None:
            # nothing reachable by proximity: a rigid motor housing bolted across
            # both bodies also holds a component in place
            held = [k for k, c in enumerate(pending)
                    if {nd for e_ in c for nd in elems[e_]} & (rigid_nodes | bridged)]
            if held:
                k = held[0]
                print(f'   a {len(pending[k])}-element body is held by a rigid motor '
                      'housing bolted across the joint', flush=True)
                joined |= set(pending.pop(k))
                continue
            raise SystemExit(f'{len(pending)} component(s) cannot be joined to the '
                             'assembly (nothing within 40 mm) - check the geometry')
        idx, txt, n, g = best
        tie_txt += txt
        joined |= set(pending[idx])
        print(f'   joined a {len(pending[idx])}-element body with {n} node-pair MPCs '
              f'(gap {g:.0f} mm)', flush=True)
        pending.pop(idx)

    # ---- load points and their node sets
    pts = env_spec['points']
    for p in pts:
        p['nids'] = sel_bore(nodes, surf, p)
        # If a load region sits inside a motor's rigid housing, pushing on those
        # nodes just feeds the rigid body and the structure sees almost nothing
        # (L4: 836 N applied, 0.96 MPa peak). The physical statement is that the
        # load arrives THROUGH the actuator, so apply it at that housing's
        # reference node and let the rigid body spread it into the flange.
        inside_rigid = [n for n in p['nids'] if n in rigid_nodes]
        if mot_nodes and len(inside_rigid) > 0.5 * len(p['nids']):
            near = min(mot_nodes, key=lambda r: float(np.linalg.norm(
                np.asarray(mot_nodes[r], float) - np.mean([nodes[n] for n in p['nids']], axis=0))))
            p['nids'] = [near]
            p['_via_motor_ref'] = near
            print(f"   load point '{p['name'][:40]}' is inside a rigid housing -> "
                  f'applied at motor reference node {near}', flush=True)
        if 'ctr' not in p:      # plane patch / bolt pads: centroid of the region
            p['ctr'] = [float(v) for v in np.mean(
                [nodes[n] if n in nodes else mot_nodes[n] for n in p['nids']], axis=0)]
            p['_ctr_from'] = 'node centroid'
        print(f"  load point {p['name']}: {len(p['nids'])} nodes "
              f"({'plane patch' if p.get('type') == 'plane' else 'seat r' + str(p.get('r'))})",
              flush=True)

    if setup_only:
        # export BC/load/fastener setup without solving (visualisation pass)
        idx0 = {n: k for k, n in enumerate(sorted({t for tri in tris for t in tri}))}
        used0 = sorted(idx0)
        jf0 = f'{STEPS}/link_{geo}_joints.json'
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
    gfac = env_spec.get('inertia_g', 3.0)      # +-3 g envelope on self weight
    if gfac:
        comps.append('Gbody')
    unit_stress = []
    load_nids = sorted({n for p in pts for n in p['nids'] if n in nodes})
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
        cl, mom_extra = {}, {}
        if comp == 'Gbody':
            pass          # body load goes into the deck as *DLOAD GRAV, not CLOAD
        elif pattern:
            Fv = np.zeros(3); Mv = np.zeros(3)
            if comp.startswith('F'):
                Fv['xyz'.index(comp[1])] = E.UNIT_F
            elif comp == 'Maxial':
                Mv[axmap[env_spec['joint_axis']]] = E.UNIT_M * 1000.0
            else:
                Mv['xyz'.index(comp[1])] = E.UNIT_M * 1000.0
            # Statics transport: the joint wrench is defined at the joint centre,
            # but it is handed over at attachment regions that can be far away
            # (the shin's ankle bolt circle is 200 mm from the ankle centre). Each
            # region takes its share of the force PLUS the moment that share
            # generates about it: M_i = w_i*M + (c - p_i) x (w_i*F). Summed back
            # this reproduces (F, M) exactly, and unlike a least-norm split it
            # works for one, two or many attachments.
            w = np.array([len(p['nids']) for p in pts], float)
            w = w / w.sum()
            for p, wi in zip(pts, w):
                pc = np.asarray(p['ctr'], float)
                Fi = Fv * wi
                Mi = Mv * wi + np.cross(jc_p - pc, Fi)
                if np.linalg.norm(Fi) > 0:
                    if p.get('_via_motor_ref') or p.get('type') in ('plane', 'bolt_pads'):
                        d = {n: Fi / len(p['nids']) for n in p['nids']}
                    else:
                        d = F.bearing_load(nodes, p['nids'], p['axis'], pc, Fi)
                    for n, f in d.items():
                        cl[n] = cl.get(n, np.zeros(3)) + f
                if np.linalg.norm(Mi) > 0:
                    if p.get('_via_motor_ref'):
                        # moment straight onto the rigid reference node
                        d = {}
                        cl_m = cl.setdefault(p['nids'][0], np.zeros(3))
                        mom_extra.setdefault(p['nids'][0], np.zeros(3))
                        mom_extra[p['nids'][0]] += Mi
                    else:
                        d = F.moment_load(nodes, p['nids'], pc, Mi)
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
                    if p.get('type') in ('plane', 'bolt_pads'):   # flat/bolted interface
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
            grav = None
            if comp == 'Gbody':
                grav = (0.0, 0.0, -9810.0)                  # 1 g, -z
                for ref, mt in mot_mass.items():            # motor weight
                    cl[ref] = np.array([0.0, 0.0, -mt * 9810.0])
            extra_cl = ''
            for nid, mv in mom_extra.items():
                for k3 in range(3):
                    if abs(mv[k3]) > 1e-9:
                        extra_cl += f'{nid}, {k3 + 4}, {mv[k3]:.6f}\n'
            F.write_deck(f'{W}/{job}.inp', nodes, elems, elsets,
                         {e: F.AL for e in elsets}, fix, cl, extra=tie_txt,
                         gravity=grav, extra_nodes=mot_nodes, extra_cload=extra_cl)
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
    d = LOADS[j][stat] if j in LOADS else {}
    for c in comps:
        ovr = env_spec.get('magnitudes_N') or {}
        if c in ovr:
            mags.append(float(ovr[c]))
        elif c == 'Maxial':
            mags.append(axial)
        elif c == 'Gbody':
            mags.append(gfac)                # unit solve = 1 g; envelope covers +-gfac g
        else:
            mags.append(d[c] * factor)
    env = E.combine(unit_stress, mags, comps=comps)
    summ = E.summarize(env, P, ids, load_nids=load_nids, fix_nids=fix)
    summ.update(spec_hash=spec_hash,
                link=link, joint=j, stat=stat, factor=factor,
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
    Fapplied = float(np.linalg.norm([summ['magnitudes'].get(c, 0.0) for c in ('Fx', 'Fy', 'Fz')]))
    if summ['max_vM'] < 3.0 and Fapplied > 100.0:
        raise SystemExit(
            f"implausible result: {Fapplied:.0f} N applied but peak stress is only "
            f"{summ['max_vM']:.2f} MPa - the load path is short-circuited (a rigid body or "
            'tie probably spans load and fix); not writing this result')
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

    jf = f'{STEPS}/link_{geo}_joints.json'
    joints = json.load(open(jf)) if os.path.exists(jf) else {}
    setup = dict(link=link,
                 nodes=[[round(float(v), 2) for v in nodes[n]] for n in used],
                 tris=case['tris'],
                 fixed=[ridx[n] for n in fix if n in ridx],
                 fix_desc=env_spec['fix_desc'],
                 load_points=[dict(name=p['name'], ctr=p.get('ctr', [0, 0, 0]),
                                   axis=p.get('axis', 'z'), r=p.get('r', 10),
                                   via_motor_ref=bool(p.get('_via_motor_ref')),
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
