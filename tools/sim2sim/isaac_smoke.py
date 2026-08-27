"""IsaacSim reachability check.

Kit redirects stdout into its own log sink, so print() from inside a SimulationApp session is
not reliably visible. Everything that matters is written to a JSON file instead - the same
pattern every later sim2sim script here should use.
"""
import json
import os

os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
OUT = '/home/syaro/pyg_fea/work/isaac_smoke.json'
res = {'ok': False}
try:
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    import omni.usd
    from pxr import Usd, UsdPhysics, UsdGeom
    ctx = omni.usd.get_context()
    ctx.new_stage()
    stage = ctx.get_stage()
    UsdGeom.Xform.Define(stage, '/World')
    scene = UsdPhysics.Scene.Define(stage, '/World/physicsScene')
    res.update(ok=True, usd_version=str(Usd.GetVersion()),
               stage=bool(stage), prims=[p.GetPath().pathString for p in stage.Traverse()],
               physics_scene=bool(scene))
    # SimulationApp.close() hard-exits the process - nothing after it runs, so the result has
    # to be on disk BEFORE closing. Learned the hard way: the first version wrote after close()
    # and produced no file at all despite a clean startup/shutdown in the log.
    json.dump(res, open(OUT, 'w'), indent=1)
    app.close()
except Exception as e:                      # record the failure rather than losing it to the sink
    res.update(ok=False, error=f'{type(e).__name__}: {e}')
    json.dump(res, open(OUT, 'w'), indent=1)
