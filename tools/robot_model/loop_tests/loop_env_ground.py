"""Loop ankle on the ground in mjlab: closure error and jitter while standing, under a base
push, and while the cranks are driven - the mujoco_warp #1510 (fp32 soft-equality + contact
oscillation) check. 4 envs identical -> cross-env divergence is reported too."""
import os, torch, numpy as np
from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg
import mjlab.tasks  # noqa
dev = "cpu"; N = 4
cfg = load_env_cfg("Mjlab-Velocity-Flat-Pygmalion", play=True)
cfg.scene.num_envs = N; cfg.events.pop("push_robot", None)
env = ManagerBasedRlEnv(cfg=cfg, device=dev)
robot = env.scene["robot"]; jn = list(robot.joint_names); ji = {n: i for i, n in enumerate(jn)}
m = env.sim.mj_model; d = env.sim.data
def closure_all():
    p = d.site_xpos
    return torch.stack([torch.linalg.norm(p[:, m.eq_obj1id[k]] - p[:, m.eq_obj2id[k]], dim=-1) for k in range(m.neq)], 1) * 1000  # [N, neq]
env.reset(); a = torch.zeros(N, env.action_manager.total_action_dim, device=dev)
term = env.action_manager.get_term("joint_pos"); an = list(term._target_names)
ia, ib = an.index("L_crank_A_joint"), an.index("L_crank_B_joint")
ria, rib = an.index("R_crank_A_joint"), an.index("R_crank_B_joint")
base = list(robot.body_names).index("base_link")
Z0 = float(robot.data.default_root_state[0, 2])
def pin(dz):
    st = robot.data.default_root_state.clone(); st[:, 2] = Z0 + dz; st[:, 7:] = 0
    robot.write_root_state_to_sim(st)
def phase(name, steps, act=None, dz=-0.01):
    cl, vel, z = [], [], []
    for i in range(steps):
        pin(dz)
        env.step(a if act is None else act)
        cl.append(closure_all().clone()); z.append(robot.data.root_link_pos_w[:, 2].clone())
        vel.append(robot.data.joint_vel[:, [ji["L_ankle_pitch_joint"], ji["L_ankle_roll_joint"]]].clone())
    cl = torch.stack(cl); vel = torch.stack(vel); z = torch.stack(z)       # [T, N, ...]
    q = robot.data.joint_pos[0]
    print("%-22s closure max %.3f mean %.3f mm | ankle vel rms %.3f rad/s (last 0.5 s) | base z %.3f (env spread %.2e) | L ankle p %+5.1f r %+5.1f deg" % (
        name, cl.max(), cl.mean(), vel[-25:].pow(2).mean().sqrt(), z[-1].mean(), float(z[-1].max() - z[-1].min()),
        np.degrees(float(q[ji["L_ankle_pitch_joint"]])), np.degrees(float(q[ji["L_ankle_roll_joint"]]))))
print("solimp", m.eq_solimp[0], "solref", m.eq_solref[0], "disableflags", int(m.opt.disableflags))
print("root pinned at standing z %.3f - 10 mm: feet pressed into the floor by the leg PD" % Z0)
phase("rest 3 s", 150)
phase("rest -20 mm 2 s", 100, dz=-0.02)
act = a.clone(); act[:, [ia, ib, ria, rib]] = -0.4    # both feet: crank -0.1 rad co-act -> ankle pitch +7 deg
phase("cranks co-act -0.4", 50, act=act)
act = a.clone(); act[:, [ia, ib, ria, rib]] = 0.4
phase("cranks co-act +0.4", 50, act=act)
act = a.clone(); act[:, ia] = 0.4; act[:, ib] = -0.4; act[:, ria] = -0.4; act[:, rib] = 0.4
phase("cranks diff (roll)", 50, act=act)
phase("release 2 s", 100)
phase("in the air 2 s", 100, dz=+0.3)
env.close()
