import os, torch, numpy as np
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa
cfg = load_env_cfg("Mjlab-Velocity-Flat-Pygmalion", play=True); cfg.scene.num_envs = 1; cfg.events.pop("push_robot", None)
env = ManagerBasedRlEnv(cfg=cfg, device="cpu"); robot = env.scene["robot"]; m = env.sim.mj_model; d = env.sim.data
ji = {n: i for i, n in enumerate(robot.joint_names)}
def closure(): p = d.site_xpos[0]; return max(float(torch.linalg.norm(p[m.eq_obj1id[k]] - p[m.eq_obj2id[k]]) * 1000) for k in range(m.neq))
env.reset()
q = robot.data.joint_pos[0]
print("reset: closure %.3f mm  L crank A %+.1f ankle pitch %+.1f knee %+.1f deg  base z %.3f" % (closure(), np.degrees(q[ji["L_crank_A_joint"]]), np.degrees(q[ji["L_ankle_pitch_joint"]]), np.degrees(q[ji["L_knee_joint"]]), float(robot.data.root_link_pos_w[0, 2])))
a = torch.zeros(1, env.action_manager.total_action_dim)
for i in range(10): env.step(a)
q = robot.data.joint_pos[0]
print("after 0.2 s: closure %.3f mm  ankle pitch %+.1f deg  base z %.3f" % (closure(), np.degrees(q[ji["L_ankle_pitch_joint"]]), float(robot.data.root_link_pos_w[0, 2])))
env.close()
