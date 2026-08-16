"""Merge per-link setup JSONs into the viewer payload.

Reads ~/pyg_fea/work/<link>/setup_<link>.json (+ envelope_<stat>.json and the
envelope viewer case if solved) and writes
tools/wrench_studio/static/link_setup_data.json as {links: {link: {stat: setup}}}.

Decimates the surface mesh for links whose surface is huge, so the viewer stays
responsive (structure display only -- numbers always come from the full model).
"""
import glob
import hashlib
import json
import os

import numpy as np

STATIC = '/home/syaro/MikuchanRemote/Human-Pygmalion/tools/wrench_studio/static'
TARGET = f'{STATIC}/link_setup_data.json'          # legacy single payload
INDEX = f'{STATIC}/link_setup_index.json'          # index + per-link files (mobile)
WORK = '/home/syaro/pyg_fea/work'
MAX_TRIS = 90_000


def decimate(s):
    """Keep every k-th triangle (and its nodes) if the surface is too big."""
    if len(s['tris']) <= MAX_TRIS:
        return s
    k = len(s['tris']) // MAX_TRIS + 1
    tris = s['tris'][::k]
    used = sorted({i for t in tris for i in t})
    ridx = {n: j for j, n in enumerate(used)}
    keep = set(used)
    out = dict(s)
    out['nodes'] = [s['nodes'][i] for i in used]
    out['tris'] = [[ridx[a], ridx[b], ridx[c]] for a, b, c in tris]
    out['fixed'] = [ridx[i] for i in s['fixed'] if i in keep]
    out['load_points'] = [dict(p, nids=[ridx[i] for i in p['nids'] if i in keep])
                          for p in s['load_points']]
    if s.get('result_vM'):
        out['result_vM'] = [s['result_vM'][i] for i in used]
    out['_decimated'] = k
    return out


def main():
    links = {}
    for f in sorted(glob.glob(f'{WORK}/*/setup_*.json')):
        s = json.load(open(f))
        link, stat = s['link'], s.get('stat', 'P99')
        # motors: the actuators that belong to this link (spec list first, then
        # any proxy whose envelope falls inside the link's bounding box)
        try:
            specs = json.load(open('/home/syaro/MikuchanRemote/Human-Pygmalion/'
                                   'tools/fea/link_specs.json'))
            prox = json.load(open('/home/syaro/pyg_fea/steps/actuator_proxies.json'))
            want = list(specs.get(link, {}).get('actuators', []))
            P0 = np.array(s['nodes'], float)
            lo0, hi0 = P0.min(0) - 90.0, P0.max(0) + 90.0
            for k, v in prox.items():
                if k in want:
                    continue
                c = np.asarray(v['ctr'], float)
                if np.all(c >= lo0) and np.all(c <= hi0):
                    want.append(k)
            s['actuators'] = [dict(prox[k], name=k) for k in want if k in prox]
        except Exception as e:              # never let the viewer payload fail on this
            s['actuators'] = []
            print('   (actuator attach skipped:', e, ')')
        jf = f'/home/syaro/pyg_fea/steps/link_{link}_joints.json'
        if os.path.exists(jf):
            j = json.load(open(jf))
            s['bolts'] = j.get('detected_bolts', [])
            s['bearings'] = j.get('bearings', s.get('bearings', []))
        # A result counts only if it came from the CURRENT spec. Stale artefacts of
        # a superseded run made the viewer announce L4 as "solved, 1.0 MPa, SF 288"
        # - the very short-circuited result the analysis had already rejected.
        env = f'{os.path.dirname(f)}/envelope_{stat}.json'
        fresh = False
        if os.path.exists(env):
            ed = json.load(open(env))
            try:
                spec_all = json.load(open(os.path.join(os.path.dirname(
                    os.path.abspath(__file__)), 'link_specs.json')))
                h = hashlib.sha1(json.dumps(spec_all[link], sort_keys=True)
                                 .encode()).hexdigest()[:12]
                fresh = ed.get('spec_hash') == h
            except Exception:
                fresh = False
            if fresh:
                s['envelope'] = ed
            else:
                s['stale_result'] = True
        elif stat == 'P99':
            s['stale_result'] = True
        # which motors the SOLVER actually carried (rigid bodies), vs CAD-only ones
        try:
            spec_all = json.load(open(os.path.join(os.path.dirname(
                os.path.abspath(__file__)), 'link_specs.json')))
            sp = spec_all[link]
            act = sp.get('actuators', sp['envelope'].get('actuators'))
            s['motors_in_analysis'] = ([a.get('name') for a in act]
                                       if isinstance(act, list) else 'auto')
        except Exception:
            s['motors_in_analysis'] = 'auto'
        case = f'{os.path.dirname(f)}/case_{link}_env.json'
        if fresh and os.path.exists(case) and not s.get('result_vM'):
            c = json.load(open(case))
            k = next(iter(c))
            if len(c[k]['nodes']) == len(s['nodes']):
                s['result_vM'] = c[k]['fields']['vM']
        # only show fasteners/bearings that belong to the ANALYSED geometry: a
        # CAD sub-assembly can be wider than the link subset that was meshed
        P = np.array(s['nodes'], float)
        lo, hi = P.min(0) - 25.0, P.max(0) + 25.0
        def inside(pt):
            q = np.asarray(pt, float)
            return bool(np.all(q >= lo) and np.all(q <= hi))
        nb = len(s.get('bolts', []))
        s['bolts'] = [b for b in s.get('bolts', []) if inside(b['head_point'])]
        s['bolts_outside_subset'] = nb - len(s['bolts'])
        nr = len(s.get('bearings', []))
        s['bearings'] = [b for b in s.get('bearings', []) if inside(b['centre'])]
        s['bearings_outside_subset'] = nr - len(s['bearings'])
        s = decimate(s)
        links.setdefault(link, {})[stat] = s
        print(f"{link:18s} {stat:5s} tris {len(s['tris']):6d} fixed {len(s['fixed']):5d} "
              f"loaded {sum(len(p['nids']) for p in s['load_points']):5d} "
              f"screws {len(s.get('screws', [])):3d} bolts {len(s.get('bolts', [])):3d} "
              f"bearings {len(s.get('bearings', [])):2d} motors {len(s.get('actuators', [])):1d} "
              f"{'RESULT' if s.get('result_vM') else 'setup-only'}"
              f"{' (decimated x%d)' % s['_decimated'] if s.get('_decimated') else ''}")
    json.dump(dict(links=links), open(TARGET, 'w'), separators=(',', ':'))
    print(f'\n{len(links)} links -> {TARGET} ({os.path.getsize(TARGET)/1e6:.1f} MB)')

    # per-link files + index: a phone should not parse the whole body at once
    idx = {}
    for link, stats in links.items():
        f = f'link_setup_{link}.json'
        json.dump(stats, open(f'{STATIC}/{f}', 'w'), separators=(',', ':'))
        any_s = next(iter(stats.values()))
        idx[link] = dict(file=f, stats=sorted(stats),
                         joint=any_s.get('joint'), tris=len(any_s['tris']),
                         nodes=len(any_s['nodes']),
                         bolts=len(any_s.get('bolts', [])),
                         bearings=len(any_s.get('bearings', [])),
                         size_mb=round(os.path.getsize(f'{STATIC}/{f}') / 1e6, 2),
                         solved=bool(any_s.get('result_vM')),
                         stale=bool(any_s.get('stale_result')))
        print(f'   {f}: {idx[link]["size_mb"]} MB')
    json.dump(dict(links=idx), open(INDEX, 'w'), indent=1)
    print(f'index -> {INDEX}')


if __name__ == '__main__':
    main()
