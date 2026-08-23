"""Unit check of AnkleRpActuator._clip_effort against a numpy re-implementation, and the
joint params actually compiled into the model in RP mode."""
import json, os, torch, numpy as np, mujoco
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa
dev = "cuda:0" if torch.cuda.is_available() else "cpu"
cfg = load_env_cfg("Mjlab-Velocity-Flat-Pygmalion", play=True); cfg.scene.num_envs = 2; cfg.events.pop("push_robot", None)
env = ManagerBasedRlEnv(cfg=cfg, device=dev); robot = env.scene["robot"]; m = env.sim.mj_model
for n in ("L_ankle_pitch_joint", "L_ankle_roll_joint", "R_ankle_roll_joint", "L_knee_joint", "L_hip_pitch_joint", "L_hip_yaw_joint"):
    j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "robot/" + n); assert j >= 0, n; a = m.jnt_dofadr[j]
    print("%-22s armature %.5f damping %.4f frictionloss %.4f" % (n, m.dof_armature[a], m.dof_damping[a], m.dof_frictionloss[a]))
act = [a for a in robot.actuators if "ankle" in a._target_names[0]][0]
E = json.load(open(act.cfg.envelope_json)); pa = np.radians(E["grid"]["pitch_deg"]); ra = np.radians(E["grid"]["roll_deg"])
def interp(tab, p, r):
    fp = np.clip((p - pa[0]) / (pa[-1] - pa[0]) * (len(pa) - 1), 0, len(pa) - 1 - 1e-6); fr = np.clip((r - ra[0]) / (ra[-1] - ra[0]) * (len(ra) - 1), 0, len(ra) - 1 - 1e-6)
    i, j = int(fp), int(fr); wp, wr = fp - i, fr - j; T = np.array(tab)
    return (1 - wp) * (1 - wr) * T[i, j] + wp * (1 - wr) * T[i + 1, j] + (1 - wp) * wr * T[i, j + 1] + wp * wr * T[i + 1, j + 1]
PEAK = float(act.t_tab[0]) if hasattr(act, "t_tab") else act.peak
rng = np.random.default_rng(0); worst_err = 0; worst_c = 0
names = list(act._target_names)
for trial in range(200):
    p = rng.uniform(-0.9, 0.55, 2); r = rng.uniform(-0.36, 0.36, 2)    # a bit beyond the grid -> clamped lookup
    tau_in = rng.uniform(-250, 250, (2, 4))
    pos = torch.zeros(2, 4, device=dev)
    for k, s in enumerate("LR"):
        pos[:, names.index(f"{s}_ankle_pitch_joint")] = float(p[k]); pos[:, names.index(f"{s}_ankle_roll_joint")] = float(r[k])
    act._pos = pos; act._vel = torch.zeros_like(pos)
    out = act._clip_effort(torch.tensor(tau_in, dtype=torch.float32, device=dev)).cpu().numpy()
    for k, s in enumerate("LR"):
        ip, ir = names.index(f"{s}_ankle_pitch_joint"), names.index(f"{s}_ankle_roll_joint")
        Lg = E["legs"][s]; M = interp(Lg["M"], p[k], r[k]); JT = interp(Lg["JcT"], p[k], r[k])
        Mi = np.linalg.inv(JT)
        ref = JT @ np.clip(Mi @ tau_in[0, [ip, ir]], -PEAK, PEAK)
        worst_err = max(worst_err, abs(out[0, [ip, ir]] - ref).max())
        worst_c = max(worst_c, abs(Mi @ out[0, [ip, ir]]).max())
print("clip vs numpy reference: worst |diff| %.4f N*m ; worst crank torque after clamp %.2f (limit 60) -> %s" % (worst_err, worst_c, "OK" if worst_err < 1e-2 and worst_c <= PEAK + 0.01 else "FAIL"))
# a saturating pose: pitch -50 deg, demand (+300, 0) -> should land on the parallelogram boundary
act._pos = torch.tensor([[np.radians(-50), 0, 0, 0]] * 2, dtype=torch.float32, device=dev); act._vel = torch.zeros_like(act._pos)
out = act._clip_effort(torch.tensor([[300.0, 0, 0, 0]] * 2, device=dev)).cpu().numpy()[0]
print("pitch -50 deg, demand +300 pitch -> applied (%.1f, %.1f) ; envelope extent there %.1f" % (out[0], out[1], interp(E["legs"]["L"]["tau_extent"], np.radians(-50), 0)[0]))
env.close()

# T-N in crank space: pitch joint moving fast (+10 rad/s -> cranks ~ -8.2 rad/s each, braking for + torque, motoring for - torque)
act._pos = torch.zeros(2, 4, device=dev); act._vel = torch.tensor([[10.0, 0, 0, 0]] * 2, device=dev)
# sign convention: pitch + moves the cranks NEGATIVE (Jc[:,0] < 0), and a + pitch torque needs
# NEGATIVE crank torque -> (+tau, +vel) at the ankle is the MOTORING quadrant for the cranks
o1 = act._clip_effort(torch.tensor([[300.0, 0, 0, 0]] * 2, device=dev)).cpu().numpy()[0]
o2 = act._clip_effort(torch.tensor([[-300.0, 0, 0, 0]] * 2, device=dev)).cpu().numpy()[0]
print("pitch vel +10 rad/s (cranks ~8 rad/s < corner 12.6): +300 -> %.1f (motoring, still peak), -300 -> %.1f (braking, peak)" % (o1[0], o2[0]))
act._vel = torch.tensor([[20.0, 0, 0, 0]] * 2, device=dev)
o3 = act._clip_effort(torch.tensor([[300.0, 0, 0, 0]] * 2, device=dev)).cpu().numpy()[0]
o4 = act._clip_effort(torch.tensor([[-300.0, 0, 0, 0]] * 2, device=dev)).cpu().numpy()[0]
print("pitch vel +20 rad/s (cranks ~16.5 rad/s): +300 -> %.1f (motoring: T-N roll-off, expect ~66), -300 -> %.1f (braking: peak)" % (o3[0], o4[0]))
