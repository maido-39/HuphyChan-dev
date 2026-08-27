"""Exercise upper_meshes_fusion.py against a fake connector - no Fusion, no CAD PC.

The thing worth testing is not the geometry, it is the promise: a run that fails partway
through must leave the asset directory exactly as it found it. That promise is only ever
tested by a failure, and a failure against the live document costs an add-in restart, so the
connector is faked here instead - it answers the same scripts, truncates payloads above a
configurable ceiling the way the real one does, and can be told to drop a body.

Four cases, each asserting on the live directory afterwards:

  1. clean run              - all four rigid bodies publish, byte-for-byte what was staged
  2. truncating connector   - the slice re-sizes itself from the payload that came back short
  3. cut mid-base64-quantum - an undecodable payload is treated as a short one, not a failure
  4. one body unreachable   - the run aborts and the directory is untouched, to the byte

Run it after any change to the fetch or publish path:

    mujoco-sim/mjlab/.venv/bin/python3 tools/robot_model/upper_meshes_selftest.py
"""
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import upper_meshes_fusion as U  # noqa: E402


class FakeFusion:
    """Answers the two scripts the fetcher sends, with the real one's failure modes.

    `cap` is the base64 length above which a payload comes back truncated - the connector
    does that silently, which is why the fetcher length-checks every slice. `drop` names a
    body that raises, standing in for any per-body failure.
    """

    def __init__(self, cap=10 ** 9, drop=None, tris=(700, 300, 1500, 400)):
        self.cap, self.drop, self.calls = cap, drop, 0
        # one synthetic body per group filter, sized differently so the slicing has work to do
        self.bodies = {}
        for (body, (_, want)), n in zip(U.GROUPS.items(), tris):
            for k, w in enumerate(want):
                path = f'/Joints_UpperBody:1/{w}/Body{k}:1'
                m = self._sphere(n + 100 * k)
                self.bodies[path] = (f'{body}_b{k}', m)

    @staticmethod
    def _sphere(ntri):
        """A closed surface with a predictable triangle count, in Fusion's centimetres."""
        import trimesh
        s = trimesh.creation.icosphere(subdivisions=2, radius=3.0)
        s = s.subdivide() if len(s.faces) < ntri else s
        return s

    def host_alive(self):
        return True

    def printed(self, src):
        self.calls += 1
        if 'json.dumps(out)' in src:                       # LIST_SCRIPT
            want = json.loads(re.search(r'for w in (\[.*?\])', src, re.S).group(1))
            out = [[p, 0, self.bodies[p][0]] for p in self.bodies
                   if any(w in p for w in want)]
            return json.dumps(sorted(out))
        target = json.loads(re.search(r'q == (".*?")', src).group(1))
        name, mesh = self.bodies[target]
        if name == self.drop:
            raise RuntimeError('simulated body failure')
        verts = np.asarray(mesh.vertices, dtype='<f4').ravel()
        idx = np.asarray(mesh.faces, dtype='<u4').ravel()
        what = json.loads(re.search(r'if (".*?") == "meta"', src).group(1))
        if what == 'meta':
            return f'{len(verts)} {len(idx)}'
        start, count = (int(x) for x in
                        re.search(r'src\[(\d+):\d+ \+ (\d+)\]', src).groups())
        part = (verts if what == 'v' else idx)[start:start + count]
        txt = base64.b64encode(part.tobytes()).decode()
        return txt[:self.cap] if len(txt) > self.cap else txt


def _prev_stl(name):
    """A valid but obviously-different STL, so 'the directory is untouched' is checked
    against something a real reader would accept, not against a blob of junk bytes."""
    import trimesh
    m = trimesh.creation.box(extents=(0.01, 0.02, 0.03))
    m.apply_translation([len(name) * 1e-3, 0, 0])
    return trimesh.exchange.stl.export_stl(m)


def digest(d, names):
    return {n: hashlib.sha256(open(f'{d}/{n}', 'rb').read()).hexdigest()
            for n in names if os.path.exists(f'{d}/{n}')}


def case(label, fake, chunk, expect_ok, seed_names):
    """Run main() once against `fake` with the asset dir redirected to a temp copy."""
    live = tempfile.mkdtemp(prefix='live_')
    backups = tempfile.mkdtemp(prefix='backup_')
    for n in seed_names:                                   # a previous generation on disk
        open(f'{live}/{n}', 'wb').write(_prev_stl(n))
    before = digest(live, seed_names)
    U.OUT, U.BACKUP_ROOT = live, backups
    U.M.printed, U.M.host_alive, U.M.connect = fake.printed, fake.host_alive, lambda: None
    argv = sys.argv
    sys.argv = ['x', '--chunk', str(chunk)]
    ok, err = True, ''
    try:
        U.main()
    except BaseException as e:                             # noqa: BLE001
        ok, err = False, f'{type(e).__name__}: {e}'
    finally:
        sys.argv = argv
    after = digest(live, seed_names)
    names = U.files_of(U.GROUPS)
    published = [n for n in names if os.path.exists(f'{live}/{n}')]
    if expect_ok:
        assert ok, f'{label}: run failed - {err}'
        assert len(published) == len(names), f'{label}: only {len(published)}/{len(names)} written'
        assert all(os.path.getsize(f'{live}/{n}') > 84 for n in names), f'{label}: empty STL'
        assert after != before, f'{label}: nothing was replaced'
        kept = os.listdir(backups)
        assert kept, f'{label}: no backup of the replaced set'
        print(f'  {label:34s} OK   {len(names)} meshes published, {fake.calls:4d} calls, '
              f'backup {kept[0]}')
    else:
        assert not ok, f'{label}: expected the run to abort, it did not'
        assert after == before, (f'{label}: THE ASSET DIRECTORY WAS MODIFIED BY A FAILED RUN '
                                 f'- this is the bug the staging directory exists to prevent')
        assert set(published) == set(seed_names), f'{label}: stray files {published}'
        assert not os.listdir(backups), f'{label}: took a backup for a run that never published'
        print(f'  {label:34s} OK   aborted, {len(seed_names)} live meshes byte-identical')
    shutil.rmtree(live, ignore_errors=True)
    shutil.rmtree(backups, ignore_errors=True)


def main():
    names = U.files_of(U.GROUPS)
    print(f'upper_meshes_fusion self-test - {len(names)} meshes, {len(U.GROUPS)} rigid bodies')
    case('clean run', FakeFusion(), 16000, True, names)
    # 4 kB of base64 is 3 kB of binary, 768 floats: forces several halvings from chunk=16000
    case('connector truncates above 4 kB', FakeFusion(cap=4096), 16000, True, names)
    # 5000 is not a multiple of 4, so the payload is cut mid-base64-quantum too
    case('truncation cuts mid-base64', FakeFusion(cap=5000), 16000, True, names)
    case('one body unreachable', FakeFusion(drop='arm_b0'), 16000, False, names)
    print('all four cases pass')


if __name__ == '__main__':
    main()
