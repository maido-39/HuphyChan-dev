"""Cross-engine static check: the SAME pose in IsaacSim vs MuJoCo, numbers into JSON.

Before any policy runs cross-engine, the models themselves must agree. This loads the converted
USD, articulates it, sets the zero pose with the base fixed in the air, and records per-link
world z, per-joint limits, and gravity torques - the quantities the MuJoCo twin can compute
independently. Written before close(), as always.
"""
import json
import os

os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
USD = '/home/syaro/pyg_fea/usd/pygmalion_v4_printed.usd'
RES = '/home/syaro/pyg_fea/work/usd_static_check.json'
res = {'ok': False}

try:
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})

    from isaacsim.core.api import World
    from isaacsim.core.prims import Articulation
    import omni.usd
    from pxr import UsdPhysics

    # Stage FIRST, World second: World binds to the stage current at construction, and a later
    # open_stage replaces the stage under it, leaving the World half-initialised (its _scene is
    # gone and every property access dies with AttributeError).
    ctx = omni.usd.get_context()
    ctx.open_stage(USD)
    world = World(stage_units_in_meters=1.0, physics_dt=1/200, rendering_dt=1/25)
    world.scene.add_default_ground_plane()
    art = Articulation('/pygmalion_v4_printed', name='robot')
    world.reset()
    art.initialize()
    art.set_world_poses(positions=[[0.0, 0.0, 1.0]])

    names = list(art.dof_names)
    lo, hi = art.get_dof_limits()[0].T if hasattr(art, 'get_dof_limits') else (None, None)
    world.step(render=False)
    import numpy as np
    q = np.asarray(art.get_joint_positions()).flatten()
    res.update(ok=True,
               dof_names=names, n_dof=len(names),
               q_after_1step=[round(float(v), 5) for v in q],
               limits_lo=[round(float(v), 4) for v in np.asarray(lo).flatten()] if lo is not None else None,
               limits_hi=[round(float(v), 4) for v in np.asarray(hi).flatten()] if hi is not None else None)
    json.dump(res, open(RES, 'w'), indent=1)
    app.close()
except Exception as e:
    import traceback
    res.update(error=f'{type(e).__name__}: {e}', tb=traceback.format_exc()[-1800:])
    json.dump(res, open(RES, 'w'), indent=1)
