"""Convert the Pygmalion URDF to USD so the same robot can be loaded in IsaacSim.

Cross-engine comparison only means something if BOTH engines are given the same robot, so this
converts the serial (RP) URDF - the closed-loop AB variant cannot be expressed in URDF at all,
since URDF is a tree and the 2-RSU ankle is a loop.

Results are written to a JSON file BEFORE SimulationApp.close(), because close() hard-exits the
process and Kit swallows stdout - a script that reports after closing produces nothing while
logging a perfectly clean startup and shutdown.

  OMNI_KIT_ACCEPT_EULA=YES ~/isaacsim_venv/bin/python3 tools/sim2sim/urdf_to_usd.py [urdf] [out.usd]
"""
import json
import os
import sys

os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
URDF = sys.argv[1] if len(sys.argv) > 1 else \
    f'{REPO}/pygmalion_locomotion/assets/pygmalion_v2/pygmalion_v4_printed.urdf'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/home/syaro/pyg_fea/usd/pygmalion_v4_printed.usd'
RES = sys.argv[3] if len(sys.argv) > 3 else '/home/syaro/pyg_fea/work/urdf_to_usd.json'
# a 3rd arg keeps a second model's result from silently overwriting the first's - the
# default path is shared, so back-to-back conversions used to leave only the last one.
res = {'ok': False, 'urdf': URDF, 'usd': OUT}

try:
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})

    import omni.kit.commands
    from isaacsim.asset.importer.urdf import _urdf
    from pxr import Usd, UsdPhysics

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cfg = _urdf.ImportConfig()
    cfg.merge_fixed_joints = False        # keep every link: we compare per-link masses
    cfg.fix_base = False                  # floating base, like the MuJoCo model
    cfg.make_default_prim = True
    cfg.self_collision = False
    cfg.distance_scale = 1.0              # URDF is metres, so is USD here
    cfg.density = 0.0                     # use the URDF's own inertials, do not re-derive

    status, robot_path = omni.kit.commands.execute(
        "URDFParseAndImportFile", urdf_path=URDF, import_config=cfg, dest_path=OUT)
    res['import_status'] = bool(status)
    res['robot_prim'] = str(robot_path)

    stage = Usd.Stage.Open(OUT)
    links, joints, mass = [], [], 0.0
    for p in stage.Traverse():
        if p.HasAPI(UsdPhysics.RigidBodyAPI):
            links.append(p.GetPath().pathString)
        if p.HasAPI(UsdPhysics.MassAPI):
            m = UsdPhysics.MassAPI(p).GetMassAttr().Get()
            if m:
                mass += float(m)
        if p.IsA(UsdPhysics.RevoluteJoint):
            joints.append(p.GetName())
    res.update(ok=True, n_links=len(links), n_revolute=len(joints),
               total_mass_kg=round(mass, 4), joints=sorted(joints),
               usd_bytes=os.path.getsize(OUT) if os.path.exists(OUT) else 0)
    json.dump(res, open(RES, 'w'), indent=1)
    app.close()
except Exception as e:
    import traceback
    res.update(ok=False, error=f'{type(e).__name__}: {e}', tb=traceback.format_exc()[-1500:])
    json.dump(res, open(RES, 'w'), indent=1)
