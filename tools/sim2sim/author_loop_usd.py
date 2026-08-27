"""Close the 2-RSU ankle loops in USD, the way PhysX actually allows it.

URDF is a tree, so the importer can only ever give us the ankle's SKELETON: cranks and rods hang
off the shin as dead-end branches with their far ends floating. This script adds the four joints
that turn that skeleton into the real mechanism - one `UsdPhysicsSphericalJoint` per MuJoCo
`<equality><connect>`, each carrying `physics:excludeFromArticulation = true`.

Why that flag rather than an ordinary joint: a PhysX articulation must be a kinetic tree, and its
reduced-coordinate solver cannot represent a cycle at all. Marking a joint excluded hands it to the
ordinary maximal-coordinate rigid-body solver instead, where it acts purely as a spatial
constraint - which is exactly what our rod-end ball joints are. This is Isaac Sim's own documented
"Rig Closed-Loop Structures" procedure and, per its source, precisely what the MJCF importer emits
internally for a single `connect` per body pair. So the file it writes is not a workaround shape;
it is the shape the toolchain itself would produce.

Anchors come from the MJCF rather than being retyped: each `connect` names two sites, and a site's
`pos` is already expressed in its parent body's frame - the same frame the URDF importer gives the
matching USD link (verified: the importer writes joint `localPos0` = URDF origin in the parent link
frame, `localPos1` = 0, i.e. link frames survive the conversion untouched). So the MJCF site
positions drop straight into `localPos0`/`localPos1` with no transform at all.

Pure `pxr` - no SimulationApp, no GPU. The USD libraries ship inside the isaacsim wheel, so if
`pxr` is not importable the script re-execs itself with that path wired up.

  python3 tools/sim2sim/author_loop_usd.py [usd] [mjcf] [--out other.usd]

Idempotent: re-running rewrites the same four prims and deletes any stale ones.
"""
import glob
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
USD = '/home/syaro/pyg_fea/usd/pygmalion_v4_printed_loop.usd'
MJCF = (f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/'
        'pygmalion_v4_printed_loop.xml')
# PYG_LOOP_RES lets a second model (v3 vs v4) keep its own record instead of
# silently overwriting the first one's - the two loop USDs are built from
# different URDFs and their anchor tables are not interchangeable.
RES = os.environ.get('PYG_LOOP_RES', '/home/syaro/pyg_fea/work/author_loop_usd.json')
VENV = '/home/syaro/isaacsim_venv'


def bootstrap_pxr():
    """Make `pxr` importable without booting Kit, by re-execing with the isaacsim USD libs."""
    try:
        import pxr  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get('_PYG_PXR_BOOTSTRAPPED'):
        sys.exit('pxr still not importable after bootstrap - check the isaacsim install')
    cache = f'{VENV}/lib/python3.11/site-packages/isaacsim/extscache'
    libs = sorted(glob.glob(f'{cache}/omni.usd.libs-*'))
    if not libs:
        sys.exit(f'no omni.usd.libs in {cache}')
    u = libs[-1]
    # libpython3.11.so.1.0 lives with the interpreter, not with the wheel; the USD python
    # bindings dlopen it by soname and fail with a bare ImportError if it is not on the path.
    pylib = glob.glob('/home/syaro/.local/share/uv/python/cpython-3.11*/lib')
    env = dict(os.environ)
    env['PYTHONPATH'] = u + os.pathsep + env.get('PYTHONPATH', '')
    env['LD_LIBRARY_PATH'] = os.pathsep.join(
        [f'{u}/bin', f'{u}/lib'] + pylib + [env.get('LD_LIBRARY_PATH', '')])
    env['_PYG_PXR_BOOTSTRAPPED'] = '1'
    os.execve(f'{VENV}/bin/python3', [f'{VENV}/bin/python3', os.path.abspath(__file__)] + sys.argv[1:], env)


def read_connects(mjcf):
    """Every <equality><connect> as (name, body_a, pos_a, body_b, pos_b), anchors in body frames."""
    root = ET.parse(mjcf).getroot()
    site_owner = {}                                   # site name -> (body name, local pos)
    def walk(body):
        for child in body:
            if child.tag == 'site' and 'name' in child.attrib:
                pos = [float(v) for v in child.get('pos', '0 0 0').split()]
                site_owner[child.get('name')] = (body.get('name'), pos)
            elif child.tag == 'body':
                walk(child)
    for wb in root.iter('worldbody'):
        walk(wb)

    out = []
    for eq in root.iter('equality'):
        for c in eq.findall('connect'):
            s1, s2 = c.get('site1'), c.get('site2')
            if s1 is None or s2 is None:
                raise SystemExit(f'connect {c.get("name")} uses the legacy body/anchor form; '
                                 'this script reads the site1/site2 form')
            b1, p1 = site_owner[s1]
            b2, p2 = site_owner[s2]
            out.append({'name': c.get('name'), 'site1': s1, 'site2': s2,
                        'body0': b1, 'localPos0': p1, 'body1': b2, 'localPos1': p2})
    return out


def main():
    bootstrap_pxr()
    from pxr import Gf, Sdf, Usd, UsdPhysics

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    usd_in = args[0] if args else USD
    mjcf = args[1] if len(args) > 1 else MJCF
    usd_out = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else usd_in
    res = {'ok': False, 'usd_in': usd_in, 'usd_out': usd_out, 'mjcf': mjcf}

    try:
        if os.path.abspath(usd_out) != os.path.abspath(usd_in):
            # the importer writes a thin wrapper whose payloads are RELATIVE paths into
            # ./configuration/, so a copy only stays resolvable inside the same directory.
            if os.path.dirname(os.path.abspath(usd_out)) != os.path.dirname(os.path.abspath(usd_in)):
                raise RuntimeError('--out must sit in the same directory as the input USD: '
                                   'its layer references ./configuration/ relatively')
            shutil.copyfile(usd_in, usd_out)

        connects = read_connects(mjcf)
        stage = Usd.Stage.Open(usd_out)
        root = stage.GetDefaultPrim()
        if not root:
            raise RuntimeError('stage has no default prim')
        rootp = root.GetPath().pathString

        bodies = {p.GetName(): p.GetPath().pathString for p in stage.Traverse()
                  if p.HasAPI(UsdPhysics.RigidBodyAPI)}
        missing = sorted({c[k] for c in connects for k in ('body0', 'body1')} - set(bodies))
        if missing:
            raise RuntimeError(f'USD has no rigid body for: {missing} - wrong URDF imported?')

        scope = f'{rootp}/loop_joints'                 # the path the MJCF importer itself uses
        stage.DefinePrim(scope, 'Scope')
        authored = []
        for c in connects:
            path = f'{scope}/{c["name"]}'
            j = UsdPhysics.SphericalJoint.Define(stage, path)
            j.CreateBody0Rel().SetTargets([Sdf.Path(bodies[c['body0']])])
            j.CreateBody1Rel().SetTargets([Sdf.Path(bodies[c['body1']])])
            j.CreateLocalPos0Attr().Set(Gf.Vec3f(*c['localPos0']))
            j.CreateLocalPos1Attr().Set(Gf.Vec3f(*c['localPos1']))
            j.CreateLocalRot0Attr().Set(Gf.Quatf(1, 0, 0, 0))
            j.CreateLocalRot1Attr().Set(Gf.Quatf(1, 0, 0, 0))
            j.CreateAxisAttr().Set('X')
            j.CreateConeAngle0LimitAttr().Set(-1.0)   # -1 = unlimited: a free ball joint. A loop
            j.CreateConeAngle1LimitAttr().Set(-1.0)   # closure must have no limit, drive or
            j.CreateJointEnabledAttr().Set(True)      # resistance - it is a spatial constraint,
            j.CreateCollisionEnabledAttr().Set(False)  # and any stiffness here fights the solver.
            j.CreateExcludeFromArticulationAttr().Set(True)   # <- the whole point
            authored.append({**c, 'prim': path, 'body0_prim': bodies[c['body0']],
                             'body1_prim': bodies[c['body1']]})

        keep = {c['name'] for c in connects}
        stale = [p.GetPath().pathString for p in stage.GetPrimAtPath(scope).GetChildren()
                 if p.GetName() not in keep]
        for s in stale:
            stage.RemovePrim(s)

        # A maximal-coordinate joint is solved at LOWER priority than the articulation, so it is
        # where error accumulates; the velocity pass at the importer default of 1 is what lets a
        # closed loop buzz. Cheap insurance, authored once here rather than per run script.
        for p in stage.Traverse():
            if p.HasAPI(UsdPhysics.ArticulationRootAPI):
                a = p.GetAttribute('physxArticulation:solverVelocityIterationCount')
                if a and (a.Get() or 0) < 4:
                    a.Set(4)
                    res['bumped_velocity_iterations_on'] = p.GetPath().pathString

        stage.GetRootLayer().Save()
        res.update(ok=True, n_loop_joints=len(authored), removed_stale=stale,
                   root_prim=rootp, joints=authored,
                   usd_bytes=os.path.getsize(usd_out))
    except Exception as e:
        import traceback
        res.update(ok=False, error=f'{type(e).__name__}: {e}', tb=traceback.format_exc()[-1500:])

    os.makedirs(os.path.dirname(RES), exist_ok=True)
    json.dump(res, open(RES, 'w'), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != 'joints'}, indent=1))
    for j in res.get('joints', []):
        print(f"  {j['name']:10s} {j['body0']:12s} {j['localPos0']}  <->  "
              f"{j['body1']:12s} {j['localPos1']}")
    sys.exit(0 if res['ok'] else 1)


if __name__ == '__main__':
    main()
