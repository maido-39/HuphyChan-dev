"""Create a mesh-refinement twin of an existing link case, to test one hot spot.

convergence.py can only classify a link that has been solved at two or more hot-spot
element sizes. Seven links currently carry a `필렛?(미증명)` label - they look like
geometric singularities (point maximum far above the allowable, field p99 comfortably
under it, yield exceeded on well under 1 % of nodes) but there is no second mesh to prove
it. This builds that second mesh.

The twin is the SAME case with one change: a refinement sphere centred on the recorded
worst node, at a much smaller local element size. Everything else - loads, constraints,
ties, revision - is copied, so any change in the answer is attributable to the mesh.

Every edit asserts its anchor: the base link must exist, the variant must not already
exist, and the hot spot must land inside the part's bounding box (a typo in the
coordinate would otherwise produce a refinement sphere in empty space and a variant that
silently reproduces the coarse answer).

Usage:
  make_refine_variant.py L6_pelvis L6f_pelvis_peakfine --h=2.0 --r=14 [--max-nodes=520000]
  make_refine_variant.py --auto        # every 필렛?(미증명) link, from verdicts.json
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SPECS = f'{HERE}/link_specs.json'
W = '/home/syaro/pyg_fea/work'
# base link -> (variant name, local element size mm, sphere radius mm)
AUTO = {
    'L6_pelvis': ('L6f_pelvis_peakfine', 2.0, 14.0),
    'L6c_pelvis_nomotor': ('L6cf_pelvis_nomotor_fine', 2.0, 14.0),
    'L3c_thigh_nomotor': ('L3cf_thigh_nomotor_fine', 1.5, 12.0),
    'L1g_foot_corner': ('L1gf_foot_corner_fine', 1.5, 12.0),
    'L2c_shin_nomotor': ('L2cf_shin_nomotor_fine', 1.5, 12.0),
    'L5c_hip_nomotor': ('L5cf_hip_nomotor_fine', 1.4, 16.0),
    'L5e_hip_elastic': ('L5ef_hip_elastic_fine', 1.4, 16.0),
}


def min_node_distance(link, xyz):
    """Distance from a point to the nearest node of a solved mesh, or None if absent."""
    p = f'{W}/{link}/{link}_mesh.inp'
    if not os.path.exists(p):
        return None
    pts, on = [], False
    with open(p) as fh:
        for ln in fh:
            if ln.startswith('*'):
                on = ln.upper().startswith('*NODE')
                continue
            if on:
                v = ln.split(',')
                if len(v) >= 4:
                    try:
                        pts.append((float(v[1]), float(v[2]), float(v[3])))
                    except ValueError:
                        pass
    if not pts:
        return None
    return float(np.linalg.norm(np.asarray(pts) - np.asarray(xyz), axis=1).min())


def hotspot(link):
    """The worst design node the campaign recorded for this link."""
    f = f'{W}/{link}/envelope_P99.json'
    assert os.path.exists(f), f'{link}: no envelope_P99.json - solve the base case first'
    d = json.load(open(f))
    xyz = d.get('argmax_xyz')
    assert xyz and len(xyz) == 3, f'{link}: envelope has no argmax_xyz to centre on'
    return [float(v) for v in xyz], d


def make(base, variant, h, r, max_nodes, specs):
    assert base in specs, f'base link {base!r} not in link_specs.json'
    assert variant not in specs, f'variant {variant!r} already exists - pick another name'
    xyz, env = hotspot(base)

    spec = json.loads(json.dumps(specs[base]))            # deep copy
    mesh = spec['mesh']
    old_h = min((b[4] for b in mesh.get('refine', [])), default=mesh.get('size_far'))
    assert h < old_h, (f'{variant}: local size {h} is not finer than the base {old_h} - '
                       'a refinement twin has to refine')

    # The sphere has to sit ON the part, or it refines empty space and the twin silently
    # reproduces the coarse answer. Check against the solved mesh itself, which is
    # authoritative - an earlier version checked distance to the existing refine boxes and
    # wrongly rejected L1g, whose worst node is at the HEEL while every refine box is at
    # the toe.
    ref = mesh.setdefault('refine', [])
    d = min_node_distance(base, xyz)
    assert d is None or d < 1.0, (
        f'{variant}: hot spot {xyz} is {d:.1f} mm from the nearest mesh node of {base} - '
        'that coordinate is not on the part, check it before spending a solve on it')
    ref.append([xyz[0], xyz[1], xyz[2], r, h])
    mesh['max_nodes'] = max_nodes
    mesh['auto_refine'] = False
    spec['_refines'] = base
    spec['_note'] = (f'mesh-refinement twin of {base}: same case, hot spot at {xyz} '
                     f'refined from h {old_h} to {h} mm. Built to decide whether that '
                     f"link's point maximum is a geometric singularity.")
    specs[variant] = spec
    print(f'{variant:28s} <- {base:22s} hot spot {xyz}  h {old_h} -> {h} mm, sphere r {r}')
    return variant


def main():
    specs = json.load(open(SPECS))
    n0 = len(specs)
    made = []
    if '--auto' in sys.argv:
        mx = int(next((a.split('=')[1] for a in sys.argv
                       if a.startswith('--max-nodes=')), 520000))
        for base, (variant, h, r) in AUTO.items():
            if variant in specs:
                print(f'{variant:28s} exists - skipped')
                continue
            try:
                made.append(make(base, variant, h, r, mx, specs))
            except AssertionError as e:                    # noqa: PERF203
                print(f'  SKIP {variant}: {e}')
    else:
        args = [a for a in sys.argv[1:] if not a.startswith('--')]
        assert len(args) == 2, __doc__
        h = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--h=')), 2.0))
        r = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--r=')), 14.0))
        mx = int(next((a.split('=')[1] for a in sys.argv
                       if a.startswith('--max-nodes=')), 520000))
        made.append(make(args[0], args[1], h, r, mx, specs))

    if not made:
        print('nothing to do')
        return
    assert len(specs) == n0 + len(made), 'spec count did not grow by the number made'
    json.dump(specs, open(SPECS, 'w'), indent=1)
    print(f'\n{len(made)} variant(s) written to link_specs.json: {", ".join(made)}')
    print('run them with: tools/fea/autorun.sh   (or run_link_env.py <name> directly)')


if __name__ == '__main__':
    main()
