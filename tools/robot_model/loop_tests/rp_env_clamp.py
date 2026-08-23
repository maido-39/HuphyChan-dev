"""RP mode: env builds; hanging, an external foot torque drives the ankle PD into the
clamp; the APPLIED ankle torque must satisfy |M(q) tau| <= peak in crank space."""
import json, os, torch, numpy as np
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa
dev = os.environ.get("DEV", "cuda:0" if torch.cuda.is_available() else "cpu")
cfg = load_env_cfg("Mjlab-Velocity-Flat-Pygmalion", play=True)
cfg.scene.num_envs = 4; cfg.events.pop("push_robot", None)
env = ManagerBasedRlEnv(cfg=cfg, device=dev)
robot = env.scene["robot"]; jn = list(robot.joint_names); ji = {n: i for i, n in enumerate(jn)}
m = env.sim.mj_model
print("obs", dict(env.observation_manager.group_obs_dim), "action", env.action_manager.total_action_dim)
print("ankle joints armature/damping/frictionloss:", [(n, round(float(m.dof_armature[m.jnt_dofadr[i]]), 5), round(float(m.dof_damping[m.jnt_dofadr[i]]), 4), round(float(m.dof_frictionloss[m.jnt_dofadr[i]]), 4)) for i, n in [(mujoco_id, n) for n in ("L_ankle_pitch_joint", "L_ankle_roll_joint", "L_knee_joint", "L_hip_yaw_joint") for mujoco_id in [__import__("mujoco").mj_name2id(m, __import__("mujoco").mjtObj.mjOBJ_JOINT, n)]]])
act = [a for a in robot.actuators if "ankle" in a._target_names[0]][0]
print("ankle actuator:", type(act).__name__, act._target_names, "peak", getattr(act, "peak", None))
env_j = json.load(open(os.environ["ENVJ"])); Lg = env_j["legs"]["L"]
pa = np.radians(env_j["grid"]["pitch_deg"]); ra = np.radians(env_j["grid"]["roll_deg"])
def Mq(p, r):
    i = int(np.clip(np.argmin(abs(pa - p)), 0, len(pa) - 1)); j = int(np.clip(np.argmin(abs(ra - r)), 0, len(ra) - 1))
    return np.array(Lg["M"][i][j])
env.reset(); a = torch.zeros(4, env.action_manager.total_action_dim, device=dev)
bi = list(robot.body_names).index("L_foot_link")
def pin():
    st = robot.data.default_root_state.clone(); st[:, 2] = 1.5; st[:, 7:] = 0
    robot.write_root_state_to_sim(st)
af_idx = [i for i, n in enumerate(act._target_names)]
print("applied ankle torque vs crank-space clamp (peak %.0f):" % act.peak)
worst = 0.0
for tq in ((0, 0), (30, 0), (80, 0), (200, 0), (0, 40), (0, 120), (120, 80), (-200, -150), (150, -150)):
    for i in range(60):
        pin()
        F = torch.zeros(4, 1, 3, device=dev); T = torch.zeros(4, 1, 3, device=dev); T[:, 0, 1] = tq[0]; T[:, 0, 0] = -tq[1]
        robot.write_external_wrench_to_sim(F, T, body_ids=[bi]); env.step(a)
    q = robot.data.joint_pos[0]; p, r = float(q[ji["L_ankle_pitch_joint"]]), float(q[ji["L_ankle_roll_joint"]])
    f = robot.data.actuator_force[0].cpu().numpy()
    names = list(robot.actuators[0]._target_names)  # placeholder
    # actuator_force is in ctrl order: build name->force via entity
    allnames = []
    for A in robot.actuators: allnames += list(A._target_names)
    fa = dict(zip(allnames, f))
    tau = np.array([fa["L_ankle_pitch_joint"], fa["L_ankle_roll_joint"]])
    tc = Mq(p, r) @ tau
    worst = max(worst, abs(tc).max())
    print("  ext (%5.0f,%5.0f) -> pose p %+6.1f r %+6.1f deg | applied ankle tau (%6.1f, %6.1f) | crank tau (%6.1f, %6.1f)" % (tq[0], tq[1], np.degrees(p), np.degrees(r), tau[0], tau[1], tc[0], tc[1]))
print("worst |crank tau| = %.2f (limit %.0f) -> %s" % (worst, act.peak, "OK" if worst <= act.peak * 1.02 else "VIOLATION"))
env.close()
