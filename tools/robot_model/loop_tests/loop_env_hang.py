"""mjlab loop ankle: hanging test (root pinned in the air each step) -> clean crank->ankle map,
plus standing sag comparison. Run with PYG_ANKLE_LOOP=1 or without (serial)."""
import os, time, torch, numpy as np
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa
dev = "cpu"; loop = bool(os.environ.get("PYG_ANKLE_LOOP"))
cfg = load_env_cfg("Mjlab-Velocity-Flat-Pygmalion", play=True)
cfg.scene.num_envs = 2
cfg.events.pop("push_robot", None)
env = ManagerBasedRlEnv(cfg=cfg, device=dev)
robot = env.scene["robot"]
print("MODE", "loop" if loop else "serial", "| obs", dict(env.observation_manager.group_obs_dim), "| action dim", env.action_manager.total_action_dim)
term = env.action_manager.get_term("joint_pos"); act_names = list(term._target_names)
print("action order", act_names)
jn = list(robot.joint_names); ji = {n: i for i, n in enumerate(jn)}
m = env.sim.mj_model; d = env.sim.data
def closure_mm():
    if m.neq == 0: return 0.0
    p = d.site_xpos[0]
    return max(float(torch.linalg.norm(p[m.eq_obj1id[k]] - p[m.eq_obj2id[k]]) * 1000) for k in range(m.neq))
obs, _ = env.reset()
a = torch.zeros(2, env.action_manager.total_action_dim, device=dev)
z0 = float(robot.data.root_link_pos_w[0, 2])
for i in range(100): env.step(a)
print("standing: base z %.4f -> %.4f after 2 s (sag %.1f mm) closure %.3f mm" % (
    z0, float(robot.data.root_link_pos_w[0, 2]), (z0 - float(robot.data.root_link_pos_w[0, 2])) * 1000, closure_mm()))
# hang: pin the root 1.5 m up every step
def pin():
    st = robot.data.default_root_state.clone(); st[:, 2] = 1.5; st[:, 7:] = 0
    robot.write_root_state_to_sim(st)
q = lambda n: float(robot.data.joint_pos[0, ji[n]])
if loop:
    ia = act_names.index("L_crank_A_joint"); ib = act_names.index("L_crank_B_joint")
    cases = (("co-act +", 1, 1), ("co-act -", -1, -1), ("diff +", 1, -1), ("diff -", -1, 1), ("A only +", 1, 0), ("B only +", 0, 1))
else:
    ia = act_names.index("L_ankle_pitch_joint"); ib = act_names.index("L_ankle_roll_joint")
    cases = (("pitch +", 1, 0), ("pitch -", -1, 0), ("roll +", 0, 1), ("roll -", 0, -1))
print("hanging (root pinned at z=1.5): action 0.8 = 0.20 rad = 11.5 deg target")
for label, sa, sb in cases:
    a[:] = 0; a[:, ia] = 0.8 * sa; a[:, ib] = 0.8 * sb
    for i in range(60):
        pin(); env.step(a)
    if loop:
        print("%-9s crank A %+6.1f B %+6.1f -> ankle pitch %+6.1f roll %+6.1f deg  closure %.3f mm" % (
            label, np.degrees(q("L_crank_A_joint")), np.degrees(q("L_crank_B_joint")),
            np.degrees(q("L_ankle_pitch_joint")), np.degrees(q("L_ankle_roll_joint")), closure_mm()))
    else:
        print("%-9s ankle pitch %+6.1f roll %+6.1f deg" % (label, np.degrees(q("L_ankle_pitch_joint")), np.degrees(q("L_ankle_roll_joint"))))
env.close(); print("OK")
