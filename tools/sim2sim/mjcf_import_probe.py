"""Five-minute empirical check: does IsaacSim's MJCF importer survive our closed-loop XML?

The research note predicted a hard failure from source reading alone: `LoadEqualityConnect()` does
`std::string(c->Attribute("body1"))` with no null check, and our `<connect>` tags use the modern
`site1`/`site2` form, so `Attribute("body1")` returns nullptr and `std::string(nullptr)` is
undefined behaviour. A prediction from reading someone else's source is not a measurement, and this
one is cheap to settle, so it gets settled.

Static corroboration first, no app needed - `strings` on the SHIPPED plugin of this exact install
(2.5.8) lists `body1`, `body2`, `anchor`, `connect`, `equality` and contains no `site1`/`site2` at
all. This run is the dynamic half.

Expect one of: a segfault that takes the process out (prediction confirmed), an exception, or a
successful import - in which case check whether the loop joints actually arrived, because silently
dropping the equality section looks identical to success from the outside.

  OMNI_KIT_ACCEPT_EULA=YES ~/isaacsim_venv/bin/python3 tools/sim2sim/mjcf_import_probe.py
"""
import json
import os

os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
REPO = '/home/syaro/MikuchanRemote/Human-Pygmalion'
MJCF = (f'{REPO}/mujoco-sim/mjlab/src/mjlab/asset_zoo/robots/pygmalion/xmls/'
        'pygmalion_v4_printed_loop.xml')
OUT = '/home/syaro/pyg_fea/usd/probe_mjcf_import.usd'
RES = '/home/syaro/pyg_fea/work/mjcf_import_probe.json'

# written up front: if the process dies mid-import there is no `except` that can record it, and
# the file left on disk is then itself the evidence of where it stopped.
res = {'ok': False, 'stage': 'not_started', 'mjcf': MJCF,
       'note': 'if stage is still "importing" the process died inside the importer'}
json.dump(res, open(RES, 'w'), indent=1)

try:
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})

    import omni.kit.commands
    from isaacsim.asset.importer.mjcf import _mjcf
    from pxr import Usd, UsdPhysics

    cfg = _mjcf.ImportConfig()
    cfg.set_fix_base(False)
    cfg.set_make_default_prim(True)
    cfg.set_import_inertia_tensor(True)

    res['stage'] = 'importing'
    json.dump(res, open(RES, 'w'), indent=1)

    status = omni.kit.commands.execute(
        "MJCFCreateAsset", mjcf_path=MJCF, import_config=cfg, prim_path='/probe', dest_path=OUT)
    res['stage'] = 'imported'
    res['import_status'] = str(status)

    if os.path.exists(OUT):
        stage = Usd.Stage.Open(OUT)
        excluded, joints = [], []
        for p in stage.Traverse():
            if p.IsA(UsdPhysics.Joint) or p.HasAPI(UsdPhysics.ArticulationRootAPI):
                joints.append(p.GetPath().pathString)
            a = p.GetAttribute('physics:excludeFromArticulation')
            if a and a.Get():
                excluded.append(p.GetPath().pathString)
        res.update(n_prims_jointish=len(joints), excluded_from_articulation=excluded,
                   has_loop_joints_scope=any('/loop_joints' in j for j in joints))
    res['ok'] = True
except BaseException as e:
    import traceback
    res.update(ok=False, error=f'{type(e).__name__}: {e}', tb=traceback.format_exc()[-2000:])

json.dump(res, open(RES, 'w'), indent=1)
print(json.dumps(res, indent=1))
try:
    app.close()
except Exception:
    pass
