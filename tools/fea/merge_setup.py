"""Merge per-link setup JSONs into the viewer payload.

Reads ~/pyg_fea/work/<link>/setup_<link>.json (+ envelope_<stat>.json and the
envelope viewer case if solved) and writes
tools/wrench_studio/static/link_setup_data.json as {links: {link: {stat: setup}}}.

Decimates the surface mesh for links whose surface is huge, so the viewer stays
responsive (structure display only -- numbers always come from the full model).
"""
import glob
import json
import os

TARGET = ('/home/syaro/MikuchanRemote/Human-Pygmalion/tools/wrench_studio/'
          'static/link_setup_data.json')
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
        jf = f'/home/syaro/pyg_fea/steps/link_{link}_joints.json'
        if os.path.exists(jf):
            j = json.load(open(jf))
            s['bolts'] = j.get('detected_bolts', [])
            s['bearings'] = j.get('bearings', s.get('bearings', []))
        env = f'{os.path.dirname(f)}/envelope_{stat}.json'
        if os.path.exists(env):
            s['envelope'] = json.load(open(env))
        case = f'{os.path.dirname(f)}/case_{link}_env.json'
        if os.path.exists(case) and not s.get('result_vM'):
            c = json.load(open(case))
            k = next(iter(c))
            if len(c[k]['nodes']) == len(s['nodes']):
                s['result_vM'] = c[k]['fields']['vM']
        s = decimate(s)
        links.setdefault(link, {})[stat] = s
        print(f"{link:18s} {stat:5s} tris {len(s['tris']):6d} fixed {len(s['fixed']):5d} "
              f"loaded {sum(len(p['nids']) for p in s['load_points']):5d} "
              f"screws {len(s.get('screws', [])):3d} bolts {len(s.get('bolts', [])):3d} "
              f"bearings {len(s.get('bearings', [])):2d} "
              f"{'RESULT' if s.get('result_vM') else 'setup-only'}"
              f"{' (decimated x%d)' % s['_decimated'] if s.get('_decimated') else ''}")
    json.dump(dict(links=links), open(TARGET, 'w'), separators=(',', ':'))
    print(f'\n{len(links)} links -> {TARGET} ({os.path.getsize(TARGET)/1e6:.1f} MB)')


if __name__ == '__main__':
    main()
