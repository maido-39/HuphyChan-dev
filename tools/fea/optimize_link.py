"""Evolutionary lightweighting with the load path kept intact and re-verified at every step.

The first lightweighting pass was wrong and the 3D view showed it: thresholding the
stress field left 40-60 DISCONNECTED islands per link with no component joining the
fixed interface to the loaded one. Material at low stress is often low-stress because
its neighbours are stiff; delete it and the load has nowhere to go.

This does it properly (BESO-style, so every step is verified rather than assumed):

  1. solve the current element set  ->  directional envelope  ->  design stress
  2. protect keep-outs (bearing seats, bolt pads, joint bores) and the interfaces
  3. remove the lowest-stress REMOVE_FRAC of the remaining volume
  4. repair the load path: keep only the connected component that contains BOTH the
     fixed nodes and the loaded nodes; anything that falls off is put back only if it
     is needed to keep that component whole
  5. re-solve and check the safety factor. Stop when the target SF would be violated
     and roll back to the last verified-good iteration.

The result is a shape with a measured safety factor, not a stress map. Motors are left
out (the conservative half of the bracket, §22.3 of docs/77).

Usage: optimize_link.py <LINK> [--target-sf 2.0] [--iters 6] [--frac 0.12]
"""
import json
import os
import shutil
import sys
import time
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import envelope as E  # noqa: E402
import femlib as F  # noqa: E402
from assembly_check import pad_backing  # noqa: E402
from rejudge import deck_node_sets  # noqa: E402

W = '/home/syaro/pyg_fea/work'
YIELD = 276.0


def keepout_elements(link, spec, cen):
    zones = []
    env = spec['envelope']
    for blk in list(env.get('fix', [])) + list(env.get('points', [])):
        if blk.get('type') == 'bolt_pads':
            for q in blk['points']:
                zones.append((np.asarray(q, float), 11.0))
        elif blk.get('ctr'):
            zones.append((np.asarray(blk['ctr'], float), float(blk.get('r', 10)) + 14.0))
    jf = f"/home/syaro/pyg_fea/steps/link_{spec.get('geometry_of', link)}_joints.json"
    if os.path.exists(jf):
        J = json.load(open(jf))
        for b in J.get('detected_bolts', []):
            zones.append((np.asarray(b['head_point'], float), 10.0))
        for b in J.get('bearings', []):
            for s in b.get('seats', []):
                zones.append((np.asarray(s['loc'], float), (s.get('r') or 20) + 12.0))
    m = np.zeros(len(cen), bool)
    for c, r in zones:
        m |= np.linalg.norm(cen - c, axis=1) < r
    return m


def tie_pairs(src_inp):
    """Node pairs joined by *EQUATION - bolted bodies are tied, not fused.

    Element face-adjacency alone reports them as separate structures, which is how the
    first connectivity audit over-counted the number of disconnected pieces.
    """
    txt = open(src_inp).read().splitlines()
    pairs, i = [], 0
    while i < len(txt):
        if txt[i].strip().upper().startswith('*EQUATION'):
            j = i + 2
            body = []
            while j < len(txt) and not txt[j].strip().startswith('*'):
                body.append(txt[j])
                j += 1
            nds = [int(x.strip()) for ln in body for k, x in enumerate(ln.split(','))
                   if k % 3 == 0 and x.strip().isdigit()]
            for a in range(0, len(nds) - 1, 2):
                pairs.append((nds[a], nds[a + 1]))
            i = j
            continue
        i += 1
    return pairs


def face_adjacency(eids, elems, ties=()):
    face = {}
    for e in eids:
        c = elems[e][:4]
        for k in range(4):
            face.setdefault(tuple(sorted(c[:k] + c[k + 1:])), []).append(e)
    adj = {e: set() for e in eids}
    for es in face.values():
        for a in es:
            for b in es:
                if a != b:
                    adj[a].add(b)
    if ties:
        of = {}
        act = set(eids)
        for e in eids:
            for n in elems[e]:
                of.setdefault(n, []).append(e)
        for a, b in ties:
            for ea in of.get(a, ()):
                for eb in of.get(b, ()):
                    if ea in act and eb in act and ea != eb:
                        adj[ea].add(eb)
                        adj[eb].add(ea)
    return adj


def main_component(active, elems, fix, load, ties=()):
    """The connected piece that carries load from the constrained end to the loaded end."""
    adj = face_adjacency(active, elems, ties)
    seen, comps = set(), []
    for e in active:
        if e in seen:
            continue
        q, cur = deque([e]), []
        seen.add(e)
        while q:
            x = q.popleft()
            cur.append(x)
            for y in adj[x]:
                if y not in seen:
                    seen.add(y)
                    q.append(y)
        comps.append(cur)
    comps.sort(key=len, reverse=True)
    for c in comps:
        nds = {n for e in c for n in elems[e]}
        if (nds & fix) and (nds & load):
            return c, len(comps)
    return (comps[0] if comps else []), len(comps)


def solve_set(link, wd, tag, nodes, elems, active, fix, cloads, mags, comps_names, gvec,
              src_deck=None):
    """Solve the unit cases on the current element set; return the envelope summary."""
    els = {'EALL': list(active)}
    used = {n for e in active for n in elems[e]}
    eq_txt = ''
    if src_deck:
        eq_txt, kept, dropped = carry_equations(src_deck, used)
    US, ids, coords = [], None, None
    for c in comps_names:
        job = f'{tag}_{c}'
        cl = {} if c == 'Gbody' else {n: v for n, v in cloads[c].items() if n in used}
        F.write_deck(f'{wd}/{job}.inp', nodes, elems, els, {'EALL': F.AL},
                     sorted(fix & used), cl, gravity=(gvec if c == 'Gbody' else None),
                     extra=eq_txt)
        ok = F.run_ccx(wd, job, timeout=5400)
        if not ok:
            return None
        crd, blocks = F.parse_frd(f'{wd}/{job}.frd')
        S = [x for nm, x in blocks if nm == 'STRESS'][-1]
        ids = sorted(S)
        coords = crd
        US.append(np.array([S[i] for i in ids]))
    env = E.combine(US, mags, comps=comps_names)
    P = [coords[i] for i in ids]
    summ = E.summarize(env, P, ids, load_nids=sorted({n for v in cloads.values() for n in v}),
                       fix_nids=sorted(fix))
    return dict(summ=summ, vm=env['vm_max'], ids=ids)


def carry_equations(src_inp, keep_nodes):
    """Bring the *EQUATION ties across, dropping any whose nodes were removed.

    Without them the bolted bodies of a link are separate solids: the first attempt
    solved a shin whose knee flange was attached to nothing and reported 3037 MPa.
    """
    txt = open(src_inp).read().splitlines()
    out, i, kept, dropped = [], 0, 0, 0
    while i < len(txt):
        if txt[i].strip().upper().startswith('*EQUATION'):
            j = i + 1
            if j >= len(txt):
                break
            nterm = txt[j].strip()
            body, j2 = [], j + 1
            while j2 < len(txt) and not txt[j2].strip().startswith('*'):
                body.append(txt[j2])
                j2 += 1
            nds = [int(x.strip()) for ln in body for k, x in enumerate(ln.split(','))
                   if k % 3 == 0 and x.strip().isdigit()]
            if nds and all(n in keep_nodes for n in nds):
                out += ['*EQUATION', nterm] + body
                kept += 1
            else:
                dropped += 1
            i = j2
            continue
        i += 1
    return '\n'.join(out) + ('\n' if out else ''), kept, dropped


def main():
    link = sys.argv[1]
    target = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--target-sf=')), 2.0))
    iters = int(next((a.split('=')[1] for a in sys.argv if a.startswith('--iters=')), 6))
    frac = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--frac=')), 0.12))
    # Which stress the target is measured on. The point maximum is a mesh-dependent
    # singularity on most of these links (the foot's peak went 197->242->323 MPa under
    # refinement while its field held at 93), so gating removal on it froze the optimiser
    # at iteration 0. `--criterion=p99` judges the FIELD, which is what the verdicts use.
    crit = next((a.split('=')[1] for a in sys.argv if a.startswith('--criterion=')), 'max')

    specs = json.load(open(f'{HERE}/link_specs.json'))
    spec = specs[link]
    d = f'{W}/{link}'
    envres = json.load(open(f'{d}/envelope_P99.json'))
    comps_names = envres['comps']
    mags = [envres['magnitudes'][c] for c in comps_names]
    nodes, elems, _ = F.parse_inp(f'{d}/{link}_mesh.inp')

    # boundary conditions and unit loads straight from the verified decks
    fix, load = deck_node_sets(f'{d}/{link}_u{comps_names[0]}.inp')
    cloads = {}
    for c in comps_names:
        cl = {}
        cur = None
        for ln in open(f'{d}/{link}_u{c}.inp'):
            t = ln.strip()
            if t.startswith('*'):
                cur = 'CLOAD' if t.upper().startswith('*CLOAD') else None
                continue
            if cur == 'CLOAD' and t:
                p = [x.strip() for x in t.split(',')]
                if len(p) >= 3 and p[0].isdigit():
                    n, dof, v = int(p[0]), int(p[1]), float(p[2])
                    if dof <= 3 and n in nodes:
                        q = list(cl.get(n, (0.0, 0.0, 0.0)))
                        q[dof - 1] += v
                        cl[n] = tuple(q)
        cloads[c] = cl
    applied = {c: sum(abs(v) for q in cl.values() for v in q) for c, cl in cloads.items()}
    dead = [c for c, a in applied.items() if a < 1.0 and c != 'Gbody']
    if dead:
        raise SystemExit(
            f'{link}: unit case(s) {dead} put their load on a node that is not part of the '
            'structure (a motor reference node). Optimise the *_nomotor variant of this link '
            'instead, where the wrench enters through the real bolt pads.')
    ties = tie_pairs(f'{d}/{link}_u{comps_names[0]}.inp')
    print(f'  {len(ties)} MPC tie pairs carried into the connectivity model', flush=True)
    gfac = float(spec['envelope'].get('inertia_g', 3.0))
    gvec = (0.0, 0.0, -9810.0)

    wd = f'{d}/opt'
    shutil.rmtree(wd, ignore_errors=True)
    os.makedirs(wd, exist_ok=True)

    eids = list(elems)
    cen = np.array([np.mean([nodes[n] for n in elems[e][:4]], axis=0) for e in eids])
    vol = np.array([abs(np.linalg.det(np.array([nodes[n] for n in elems[e][1:4]])
                                      - np.array(nodes[elems[e][0]]))) / 6.0 for e in eids])
    protected = keepout_elements(link, spec, cen)
    # the interface elements themselves are never candidates
    for k, e in enumerate(eids):
        if (set(elems[e]) & fix) or (set(elems[e]) & load):
            protected[k] = True
    pos = {e: k for k, e in enumerate(eids)}
    active = list(eids)
    # the manufacturing model: 3-axis milling in up to six setups unless told otherwise
    mach_axes = next((a.split('=')[1] for a in sys.argv if a.startswith('--axes=')), 'xyz')
    tool_r = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--tool-r=')), 3.0))
    MACH = None
    if '--no-machining' not in sys.argv:
        from machinable import Machinability
        MACH = Machinability(cen, vol, axes=mach_axes, tool_r=tool_r)
        print(f'  machinability ON: {MACH.report(range(len(eids)))}', flush=True)
    else:
        print('  machinability OFF - result will not be millable', flush=True)
    V0 = vol.sum()
    print(f'{link}: {len(eids)} elements, {V0/1000:.1f} cm3, '
          f'{int(protected.sum())} protected, target SF>{target} on the '
          f'{"field p99" if crit == "p99" else "point maximum"}', flush=True)

    history, best = [], None
    for it in range(iters + 1):
        t0 = time.time()
        r = solve_set(link, wd, f'it{it}', nodes, elems, active, fix, cloads, mags,
                      comps_names, tuple(g * gfac for g in gvec),
                      src_deck=f'{d}/{link}_u{comps_names[0]}.inp')
        if r is None:
            print(f'  iter {it}: solve failed - stopping', flush=True)
            break
        des = (r['summ']['p99_vM'] if crit == 'p99'
               else r['summ'].get('max_vM_design', r['summ']['max_vM']))
        sf = YIELD / des
        vnow = vol[[pos[e] for e in active]].sum()
        print(f'  iter {it}: {len(active):6d} elems, {vnow/1000:6.1f} cm3 '
              f'({100*vnow/V0:5.1f} %), design {des:6.1f} MPa, SF {sf:5.2f}  '
              f'[{time.time()-t0:.0f}s]', flush=True)
        history.append(dict(iter=it, elements=len(active), volume_cm3=round(vnow / 1000, 1),
                            volume_pct=round(100 * vnow / V0, 1), design_MPa=round(des, 1),
                            SF=round(sf, 2)))
        if sf < target:
            print('  target violated - keeping the previous iteration', flush=True)
            break
        best = dict(active=list(active), sf=sf, vol=vnow, iter=it)
        if it == iters:
            break
        # remove the least-stressed unprotected material, then repair the load path
        idx = {n: k for k, n in enumerate(r['ids'])}
        est = np.array([np.mean([r['vm'][idx[n]] for n in elems[e][:4] if n in idx] or [0.0])
                        for e in active])
        # Sensitivity filter: removing on the raw element value produces a checkerboard
        # and shatters the part (iteration 1 of the first attempt lost 60 % of the model
        # to the connectivity repair). Averaging over a radius is the standard fix.
        from scipy.spatial import cKDTree
        ca = cen[[pos[e] for e in active]]
        rad_f = 2.5 * float(np.mean([np.cbrt(vol[pos[e]] * 6) for e in active[:2000]]))
        tree = cKDTree(ca)
        est = np.array([est[nb].mean() for nb in tree.query_ball_point(ca, rad_f)])
        cand = np.array([not protected[pos[e]] for e in active])
        order = np.argsort(np.where(cand, est, np.inf))
        # Adaptive step: a thin-walled link cannot give up 10 % of its volume without
        # punching through a wall (L4 lost 59 % of the model to orphaning at frac 0.10).
        # Halve the bite until the removal trims instead of shattering.
        step, taken = frac, None
        while step >= 0.008:
            target_cut = step * vnow
            cut, acc = set(), 0.0
            for k in order:
                if not cand[k] or acc >= target_cut:
                    break
                cut.add(active[k])
                acc += vol[pos[active[k]]]
            # MACHINABILITY. These links are milled, so a cutter has to reach every gram
            # from outside along a straight line with a finite radius. Without this the
            # optimiser hollows the interior - a shape only a printer can make. Filtering
            # here rather than in the ordering keeps the stress ranking intact and simply
            # drops the picks a tool could not have taken at this stage of the cut.
            if MACH is not None:
                idx_act = [pos[e] for e in active]
                idx_cut = [pos[e] for e in cut]
                allowed = MACH.can_remove(idx_act, idx_cut)
                cut = {e for e in cut if pos[e] in allowed}
                acc = sum(vol[pos[e]] for e in cut)
            kept = [e for e in active if e not in cut]
            comp, ncomp = main_component(kept, elems, fix, load, ties)
            lost_vol = vol[[pos[e] for e in kept if e not in set(comp)]].sum()
            if lost_vol <= 0.25 * max(acc, 1e-9):
                taken = (cut, acc, comp, ncomp, lost_vol, step)
                break
            print(f'    step {100*step:.1f} % would orphan {lost_vol/1000:.1f} cm3 '
                  f'(vs {acc/1000:.1f} cm3 removed) - halving', flush=True)
            step /= 2.0
        if taken is None:
            print('    even a 0.8 % bite shatters this part: it is already a thin-walled shell, '
                  'so further mass has to come out as CAD pockets or a thinner wall, not as '
                  'element deletion', flush=True)
            break
        cut, acc, comp, ncomp, lost_vol, step = taken
        # A shape is only acceptable if it can still be BOLTED. Stress alone would happily
        # leave a pad floating on a skin: check that every bolt pad keeps its backing metal
        # before the step is accepted (the assembly loop the user asked for).
        pb = pad_backing(link, spec, nodes, elems, comp)
        bad = [q for q in pb if not q['ok']]
        if bad:
            print(f'    rejected: {len(bad)} bolt pad(s) would lose their backing metal '
                  f'(min {min(q["backing_mm"] for q in pb):.1f} mm) - the part would pass the '
                  'stress check and be unbuildable', flush=True)
            break
        print(f'    removed {len(cut)} elems ({acc/1000:.1f} cm3, step {100*step:.1f} %); '
              f'{len(kept)-len(comp)} orphaned elems ({lost_vol/1000:.1f} cm3) dropped '
              f'from {ncomp} pieces; bolt-pad backing min '
              f'{min([q["backing_mm"] for q in pb] or [99]):.1f} mm', flush=True)
        active = comp

    out = dict(link=link, target_SF=target, criterion=crit,
               V0_cm3=round(V0 / 1000, 1), history=history)
    if best:
        out['final'] = dict(iter=best['iter'], SF=round(best['sf'], 2),
                            volume_cm3=round(best['vol'] / 1000, 1),
                            volume_pct=round(100 * best['vol'] / V0, 1),
                            removed_pct=round(100 * (1 - best['vol'] / V0), 1))
        # export the verified shape
        cen_k = cen[[pos[e] for e in best['active']]]
        from lightweight import write_voxel_stl
        write_voxel_stl(cen_k, f'{d}/{link}_optimised_SF{target}.stl', 3.0)
        out['stl'] = f'{d}/{link}_optimised_SF{target}.stl'
        # The retained ELEMENT ids, so a viewer can shade exactly what survived instead of
        # falling back on a plain stress threshold. Without this the only record of the
        # result was a voxel STL, and the viewer kept showing the retracted threshold study.
        out['retained_elements'] = [int(e) for e in best['active']]
        assert len(out['retained_elements']) == len(best['active']), 'retained set lost'
    json.dump(out, open(f'{d}/optimise.json', 'w'), indent=1)
    print(json.dumps(out.get('final', {}), indent=1))
    print(f'-> {d}/optimise.json')


if __name__ == '__main__':
    main()
