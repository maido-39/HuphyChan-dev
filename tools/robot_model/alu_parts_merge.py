"""Put every part mesh into ONE key space, whatever it was fetched by.

Meshes arrive from two places - solids matched out of the STEP export, and bodies pulled
straight from Fusion - and each numbered them its own way, so a key from one file means a
different part in the other. Rather than trust either numbering, every mesh is re-identified
the same way the STEP match works: by its VOLUME and its centroid in assembly coordinates,
against what Fusion reports for that body. A mesh that matches nothing is dropped rather than
guessed at.

Fusion's own geometry wins where both sources have a part: the STEP export is one revision
behind and several brackets changed shape by 13-35 % of their volume between them.

Usage: alu_parts_merge.py   (mjlab .venv python)
"""
import json
import os

import numpy as np
import trimesh

SRC = '/home/syaro/pyg_fea/fusion/alu_parts'
OUT = f'{SRC}/all_meshes.npz'
VOL_TOL, COM_TOL = 0.02, 3.0        # relative, mm


def load(name):
    p = f'{SRC}/{name}'
    if not os.path.exists(p):
        return {}
    z = np.load(p)
    out = {}
    for k in z.files:
        if k.endswith('|v'):
            key = k.split('|')[0]
            out[key] = (np.asarray(z[k], float), np.asarray(z[f'{key}|f'], int))
    return out


def main():
    meta = json.load(open(f'{SRC}/index.json'))
    by_key = {r['key']: r for r in meta}
    merged, report = {}, []
    # Fusion last so it overwrites the STEP where both have the part
    for src_name, tag in (('step_meshes.npz', 'STEP'), ('meshes.npz', 'Fusion')):
        pool = load(src_name)
        for _, (V, F) in pool.items():
            m = trimesh.Trimesh(V, F, process=True)
            vol = abs(m.volume) / 1000.0 if m.is_watertight else 0.0
            com = np.asarray(m.center_mass if m.is_watertight else m.centroid)
            best, bd = None, None
            for r in meta:
                if vol <= 0:
                    break
                dv = abs(vol - r['vol']) / max(r['vol'], 1e-9)
                dc = float(np.linalg.norm(com - np.array(r['com_mm'])))
                if dv < VOL_TOL and dc < COM_TOL and (bd is None or dc < bd):
                    best, bd = r['key'], dc
            if best is None:
                report.append((tag, None, round(vol, 3)))
                continue
            merged[f'{best}|v'] = V
            merged[f'{best}|f'] = F
            by_key[best]['mesh_src'] = tag
            report.append((tag, best, round(bd, 3)))

    np.savez_compressed(OUT, **merged)
    for r in meta:
        r.pop('img', None)
    json.dump(meta, open(f'{SRC}/index.json', 'w'), indent=1, ensure_ascii=False)
    have = {k.split('|')[0] for k in merged}
    from collections import Counter
    c = Counter(r.get('mesh_src', 'none') for r in meta)
    print(f'{len(have)}/{len(meta)} parts have a mesh   ' +
          '  '.join(f'{k}: {v}' for k, v in c.items()))
    bad = [x for x in report if x[1] is None]
    if bad:
        print(f'{len(bad)} meshes matched no body and were dropped')
    print('\nstill missing a picture:')
    for r in meta:
        if 'mesh_src' not in r:
            print(f"   {r['link'][:20]:20s} {r['occ'].split(':')[0][:26]:26s} "
                  f"{r['body'][:22]:22s} {r['mass_g']:7.2f} g")
    print(f'-> {OUT}')


if __name__ == '__main__':
    main()
