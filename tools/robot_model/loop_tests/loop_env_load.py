"""Hanging loop ankle under an external foot torque: how much of the deflection is servo
compliance (expected, same as serial) vs constraint compliance (closure error)."""
import os, torch, numpy as np, mujoco
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa
dev = "cpu"; loop = bool(os.environ.get("PYG_ANKLE_LOOP"))
cfg = load_env_cfg("Mjlab-Velocity-Flat-Pygmalion", play=True)
cfg.scene.num_envs = 1; cfg.events.pop("push_robot", None)
env = ManagerBasedRlEnv(cfg=cfg, device=dev)
robot = env.scene["robot"]; jn = list(robot.joint_names); ji = {n: i for i, n in enumerate(jn)}
m = env.sim.mj_model; d = env.sim.data
foot = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "L_foot_link")
def closure_mm():
    if m.neq == 0: return 0.0
    p = d.site_xpos[0]
    return max(float(torch.linalg.norm(p[m.eq_obj1id[k]] - p[m.eq_obj2id[k]]) * 1000) for k in range(m.neq))
env.reset(); a = torch.zeros(1, env.action_manager.total_action_dim, device=dev)
def pin():
    st = robot.data.default_root_state.clone(); st[:, 2] = 1.5; st[:, 7:] = 0
    robot.write_root_state_to_sim(st)
q = lambda n: float(robot.data.joint_pos[0, ji[n]])
print("MODE", "loop" if loop else "serial", "refsafe_off", bool(m.opt.disableflags & 1<<6) if False else int(m.opt.disableflags), "dt", m.opt.timestep, "eq solref", m.eq_solref[0] if m.neq else None, "solimp", m.eq_solimp[0] if m.neq else None)
for tau in (0.0, 10.0, 20.0, 40.0):
    for i in range(80):
        pin()
        bi = list(robot.body_names).index("L_foot_link")
        F = torch.zeros(1, 1, 3); T = torch.zeros(1, 1, 3); T[0, 0, 1] = tau   # world Y = ankle pitch axis
        robot.write_external_wrench_to_sim(F, T, body_ids=[bi])
        env.step(a)
    print("foot torque %5.1f Nm: ankle pitch %+6.2f deg roll %+5.2f  crank A %+6.2f B %+6.2f deg  closure %.3f mm" % (
        tau, np.degrees(q("L_ankle_pitch_joint")), np.degrees(q("L_ankle_roll_joint")),
        np.degrees(q("L_crank_A_joint")) if loop else 0, np.degrees(q("L_crank_B_joint")) if loop else 0, closure_mm()))
env.close()
