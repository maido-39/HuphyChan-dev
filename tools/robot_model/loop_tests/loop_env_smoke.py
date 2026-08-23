"""mjlab smoke test for PYG_ANKLE_LOOP: env builds, closure holds under mujoco_warp,
robot stands under zero action, crank actions move the passive ankle."""
import os, time, torch, numpy as np
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa
dev = "cpu"
cfg = load_env_cfg("Mjlab-Velocity-Flat-Pygmalion", play=True)
cfg.scene.num_envs = 4
env = ManagerBasedRlEnv(cfg=cfg, device=dev)
robot = env.scene["robot"]
print("obs actor", env.observation_manager.group_obs_dim, "action", env.action_manager.total_action_dim)
jn = list(robot.joint_names)
act_names = env.action_manager.get_term("joint_pos")._target_names if hasattr(env.action_manager.get_term("joint_pos"), "_target_names") else None
print("actuated order", act_names)
ji = {n: i for i, n in enumerate(jn)}
m = env.sim.mj_model; d = env.sim.data
def closure_mm():
    # distance between the connect sites, per equality
    out = []
    for k in range(m.neq):
        s1, s2 = m.eq_obj1id[k], m.eq_obj2id[k]
        p = d.site_xpos[0]
        out.append(float(torch.linalg.norm(p[s1] - p[s2]) * 1000))
    return max(out)
obs, _ = env.reset()
z0 = float(robot.data.root_link_pos_w[0, 2])
print("reset base z %.3f closure %.3f mm" % (z0, closure_mm()))
a = torch.zeros(4, env.action_manager.total_action_dim, device=dev)
t0 = time.time()
for i in range(100):
    env.step(a)
print("100 zero-action steps (2 s): base z %.3f closure %.3f mm  %.1f steps/s" % (
    float(robot.data.root_link_pos_w[0, 2]), closure_mm(), 100 / (time.time() - t0)))
# crank action -> ankle response (co-act = pitch, differential = roll)
ia = act_names.index("L_crank_A_joint"); ib = act_names.index("L_crank_B_joint")
q = lambda n: float(robot.data.joint_pos[0, ji[n]])
for label, sa, sb in (("co-act +", 1, 1), ("co-act -", -1, -1), ("diff +", 1, -1), ("diff -", -1, 1)):
    a[:] = 0; a[:, ia] = 0.8 * sa; a[:, ib] = 0.8 * sb     # 0.8 * 0.25 rad = 11.5 deg crank
    for i in range(50): env.step(a)
    print("%-9s crank A %+6.1f B %+6.1f -> ankle pitch %+6.1f roll %+6.1f deg | base z %.3f closure %.3f mm" % (
        label, np.degrees(q("L_crank_A_joint")), np.degrees(q("L_crank_B_joint")),
        np.degrees(q("L_ankle_pitch_joint")), np.degrees(q("L_ankle_roll_joint")),
        float(robot.data.root_link_pos_w[0, 2]), closure_mm()))
# reward terms evaluate without shape errors
env.step(torch.zeros_like(a))
print("reward terms:", [k for k in env.reward_manager.active_terms][:20], "...")
print("thermal rated vec:", getattr(env, "_thermal_rated_vec", None))
env.close(); print("OK")
