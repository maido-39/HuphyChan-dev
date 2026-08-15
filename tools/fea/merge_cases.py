"""Merge per-link viewer cases into tools/wrench_studio/static/fea_data.json.

Usage: merge_cases.py <case_json> [<case_json> ...]
Each input is {case_key: {nodes, disp, tris, fields, desc}} as written by
femlib.export_viewer_case. Existing keys are overwritten; others preserved.
"""
import json
import os
import sys

TARGET = ('/home/syaro/MikuchanRemote/Human-Pygmalion/tools/wrench_studio/'
          'static/fea_data.json')


def main(paths):
    data = json.load(open(TARGET)) if os.path.exists(TARGET) else {}
    before = set(data)
    for p in paths:
        d = json.load(open(p))
        # accept either {key: case} or a bare case (named after the file)
        if 'nodes' in d and 'fields' in d:
            d = {os.path.basename(p).replace('case_', '').replace('.json', ''): d}
        for k, v in d.items():
            n = len(v['nodes'])
            assert n and len(v['fields']['vM']) == n, f'{p}:{k} field/node mismatch'
            data[k] = v
            print(f"  {'update' if k in before else 'add   '} {k}: {n} nodes, "
                  f"{len(v['tris'])} tris, max vM {max(v['fields']['vM']):.1f}")
    json.dump(data, open(TARGET, 'w'), separators=(',', ':'))
    print(f'{len(data)} cases, {os.path.getsize(TARGET)/1e6:.1f} MB -> {TARGET}')
    print('cases:', ', '.join(sorted(data)))


if __name__ == '__main__':
    main(sys.argv[1:])
