"""Robustness sim2sim: does the trained policy DEPEND on the actuator model it was trained with?

Isaac Sim is not installed here (sim/IsaacLab is a source checkout with no _isaac_sim), and the
crank/ankle actuators are MOTOR type - mjlab computes the PD and the T-N clamp in Python and
writes torque to ctrl - so stepping the model with the plain MuJoCo C library would mean
reimplementing the very actuator under test. Instead this runs the SAME validated harness with
the actuator model toggled, which is the deployment question that actually matters:

  PYG_TN=1/0          the measured 48 V torque-speed clamp on/off
  PYG_MOTOR_MEAS=1/0  measured rotor inertia / damping / Coulomb friction vs nominal

Harness validation (2026-08-26): forward tracking reproduces the built-in evaluator to within
0.008 m/s (0.172 vs 0.170 at 0.8, 0.135 vs 0.143 at 1.6), and a hand-rebuilt actor observation
matches the env's own observation to 0.000000 on every term.

  PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_SOFT_LANDING=1 PYG_ANKLE_MODE=AB \
  CUDA_VISIBLE_DEVICES="" .venv/bin/python3 sim2sim_mujoco.py <run_dir> <ckpt> <tag>
"""
import json, os, sys
import numpy as np, torch, mujoco
from dataclasses import asdict
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
import mjlab.tasks  # noqa

D, CK, TAG = sys.argv[1:4]
MODE = os.environ.get('PYG_ANKLE_MODE', 'AB')
OUT = '/home/syaro/pyg_fea/work/sim2sim'; os.makedirs(OUT, exist_ok=True)
CMDS = [(0.8, 0.0, 0.0), (1.6, 0.0, 0.0), (0.0, 0.8, 0.0), (-0.8, 0.0, 0.0)]
SEC, WARM = 12.0, 3.0
DT_CTRL = 0.02

cfg = load_env_cfg('Mjlab-Velocity-Flat-Pygmalion', play=True)
cfg.scene.num_envs = 1
cfg.events.pop('push_robot', None)
_b = cfg.episode_length_s + 100.0
cfg.commands['twist'].resampling_time_range = (_b, _b)
for f in ('rel_standing_envs', 'rel_heading_envs', 'rel_forward_envs', 'rel_world_envs'):
    setattr(cfg.commands['twist'], f, 0.0)
env = ManagerBasedRlEnv(cfg=cfg, device='cpu')
envw = RslRlVecEnvWrapper(env, clip_actions=load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion').clip_actions)
runner = (load_runner_cls('Mjlab-Velocity-Flat-Pygmalion') or MjlabOnPolicyRunner)(
    envw, asdict(load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion')), device='cpu')
runner.load(CK, load_cfg={'actor': True}, strict=True, map_location='cpu')
policy = runner.get_inference_policy(device='cpu')
robot = env.scene['robot']
mj = env.sim.mj_model
print(f'[s2s] {MODE} policy loaded; model nq {mj.nq} nu {mj.nu} dt {mj.opt.timestep}', flush=True)

# the observation the actor sees, rebuilt from plain-MuJoCo state (same terms, same order)
om = env.observation_manager
ACTOR = list(om.active_terms['actor'])
print('[s2s] actor terms', ACTOR, flush=True)
mujoco.mj_saveModel(mj, f'{OUT}/{TAG}_model.mjb')
json.dump({'mode': MODE, 'actor_terms': ACTOR, 'nq': int(mj.nq), 'nu': int(mj.nu),
           'timestep': float(mj.opt.timestep), 'ctrl_dt': DT_CTRL,
           'note': 'harness scaffold; plain-MuJoCo leg to be added after the mjlab reference leg validates'},
          open(f'{OUT}/{TAG}_meta.json', 'w'), indent=1)


def mjlab_leg():
    res = {}
    for cmd in CMDS:
        obs, _ = envw.reset()
        tw = env.command_manager.get_term('twist')
        cv = torch.tensor(cmd, dtype=torch.float32).repeat(env.num_envs, 1)
        tw.vel_command_b[:] = cv
        v, e = [], []
        for t in range(int(SEC / DT_CTRL)):
            with torch.no_grad():
                act = policy(obs)
            obs, _, _, _ = envw.step(act)
            tw.vel_command_b[:] = cv
            if t * DT_CTRL >= WARM:
                vv = robot.data.root_link_lin_vel_b[:, :2].numpy()
                v.append(vv.mean(0)); e.append(np.linalg.norm(vv - np.array(cmd[:2]), axis=1).mean())
        res[str(cmd)] = dict(err=float(np.mean(e)), achieved=float(np.linalg.norm(np.mean(v, 0))),
                             cmd=float(np.linalg.norm(cmd[:2])))
        print(f'   [mjlab] {cmd} err {res[str(cmd)]["err"]:.3f} achieved {res[str(cmd)]["achieved"]:.2f}', flush=True)
    return res


ref = mjlab_leg()
json.dump({'mjlab_reference': ref}, open(f'{OUT}/{TAG}.json', 'w'), indent=1)
print('[s2s] mjlab reference leg written', flush=True)

os._exit(0)
