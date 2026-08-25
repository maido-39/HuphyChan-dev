"""Deployment gap, sim-to-sim: run the RP policy on the REAL (closed-loop) mechanism.

RP was trained on a serial ankle whose torque limits were borrowed from the linkage. The
machine has the linkage. So the honest deployment question is: take the RP policy, convert
its ankle-angle action to crank targets the way hardware would (IK from the envelope's
crank_rad grid), drive the closed-loop model, and measure what is lost against the same
policy on its own serial model - and against the AB policy, which needs no conversion.

  PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_SOFT_LANDING=1 CUDA_VISIBLE_DEVICES="" \
    .venv/bin/python3 rp_policy_on_loop.py <rp_run_dir> <ckpt> <tag>
"""
import json, os, sys
import numpy as np, torch, mujoco
from dataclasses import asdict
from scipy.interpolate import RegularGridInterpolator
from mjlab.envs import ManagerBasedRlEnv
from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls
from mjlab.asset_zoo.robots.pygmalion.pygmalion_constants import ANKLE_RP_ENVELOPE
import mjlab.tasks  # noqa

D, CK, TAG = sys.argv[1:4]
OUT = '/home/syaro/pyg_fea/work/deploy_gap'; os.makedirs(OUT, exist_ok=True)
CMDS = [(0.0, 0.0, 0.0), (0.8, 0.0, 0.0), (1.6, 0.0, 0.0), (0.0, 0.8, 0.0), (-0.8, 0.0, 0.0)]
STEPS, WARM = 750, 250          # 15 s per command

# --- IK: (ankle pitch, roll) -> crank angles, from the envelope grid (what hardware would do)
E = json.load(open(ANKLE_RP_ENVELOPE))
pit = np.radians(np.array(E['grid']['pitch_deg'])); rol = np.radians(np.array(E['grid']['roll_deg']))
IK = {s: RegularGridInterpolator((pit, rol), np.array(E['legs'][s]['crank_rad']),
                                bounds_error=False, fill_value=None) for s in 'LR'}

# --- the RP policy, loaded once
os.environ['PYG_ANKLE_MODE'] = 'RP'
rp_cfg = load_env_cfg('Mjlab-Velocity-Flat-Pygmalion', play=True); rp_cfg.scene.num_envs = 32
rp_cfg.events.pop('push_robot', None)
# Freeze the command exactly as the built-in evaluator does: a resample would also re-roll
# is_standing / is_forward / is_world and heading_target, which silently changes what ~30 %
# of the envs are doing mid-block (scripts/evaluate.py make_eval_env_cfg).
_big = rp_cfg.episode_length_s + 100.0
rp_cfg.commands['twist'].resampling_time_range = (_big, _big)
rp_cfg.commands['twist'].rel_standing_envs = 0.0
rp_cfg.commands['twist'].rel_heading_envs = 0.0
rp_cfg.commands['twist'].rel_forward_envs = 0.0
rp_cfg.commands['twist'].rel_world_envs = 0.0
rp_env = ManagerBasedRlEnv(cfg=rp_cfg, device='cpu')
wrap = RslRlVecEnvWrapper(rp_env, clip_actions=load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion').clip_actions)
runner = (load_runner_cls('Mjlab-Velocity-Flat-Pygmalion') or MjlabOnPolicyRunner)(
    wrap, asdict(load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion')), device='cpu')
runner.load(CK, load_cfg={'actor': True}, strict=True, map_location='cpu')
policy = runner.get_inference_policy(device='cpu')
print('[deploy] RP policy loaded', flush=True)


def rollout(env, envw, to_crank):
    """to_crank=None -> native serial run; else map the ankle action to crank targets.

    32 envs and a RESET before every command: a single env carrying a degraded state from the
    previous block is the artifact that has misled this project five times (docs/95 s7b).
    The command is re-imposed every step because the command manager resamples on its own timer.
    """
    robot = env.unwrapped.scene['robot']
    res = {}
    for cmd in CMDS:
        obs, _ = envw.reset()
        tw = env.unwrapped.command_manager.get_term('twist')
        cvec = torch.tensor(cmd, dtype=torch.float32).repeat(env.unwrapped.num_envs, 1)
        tw.vel_command_b[:] = cvec
        tw.is_standing_env[:] = False
        if hasattr(tw, 'is_heading_env'): tw.is_heading_env[:] = False
        v, e = [], []
        for t in range(STEPS):
            with torch.no_grad():
                act = policy(obs)
            if to_crank is not None:
                act = to_crank(act, robot)
            obs, _, _, _ = envw.step(act)
            tw.vel_command_b[:] = cvec
            if t >= WARM:
                vv = robot.data.root_link_lin_vel_b[:, :2].numpy()          # [E,2]
                v.append(vv.mean(0)); e.append(np.linalg.norm(vv - np.array(cmd[:2]), axis=1).mean())
        res[cmd] = (float(np.mean(e)), float(np.linalg.norm(np.mean(v, 0))), float(np.linalg.norm(cmd[:2])))
    return res


print('[deploy] baseline: RP policy on its own serial model', flush=True)
base = rollout(wrap, wrap, None)
for c, r in base.items():
    print(f'   cmd {c} -> err {r[0]:.3f}  achieved {r[1]:.2f} / {r[2]:.2f}', flush=True)
json.dump({'baseline': {str(k): v for k, v in base.items()}}, open(f'{OUT}/{TAG}.json', 'w'), indent=1)
print('[deploy] baseline written', flush=True)
# ---------------------------------------------------------------------------------------
# Leg 2: the SAME RP policy driving the closed-loop (AB) model, the way hardware would -
# ankle-angle action -> IK -> crank targets, ankle angles read back by FK for the obs.
# The harness does not reproduce the built-in evaluator's absolute numbers (0.347 vs 0.144
# at 1.6 m/s), so only the PAIRED DIFFERENCE between the two legs is used: the same bias
# sits in both.
import gc
del rp_env, wrap, runner
gc.collect()

os.environ['PYG_ANKLE_MODE'] = 'AB'
ab_cfg = load_env_cfg('Mjlab-Velocity-Flat-Pygmalion', play=True); ab_cfg.scene.num_envs = 32
ab_cfg.events.pop('push_robot', None)
_b = ab_cfg.episode_length_s + 100.0
ab_cfg.commands['twist'].resampling_time_range = (_b, _b)
for f in ('rel_standing_envs', 'rel_heading_envs', 'rel_forward_envs', 'rel_world_envs'):
    setattr(ab_cfg.commands['twist'], f, 0.0)
ab_env = ManagerBasedRlEnv(cfg=ab_cfg, device='cpu')
ab_wrap = RslRlVecEnvWrapper(ab_env, clip_actions=load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion').clip_actions)
print('[deploy] loop env built; action dim', ab_env.action_manager.total_action_dim, flush=True)

robot = ab_env.scene['robot']
jn = list(robot.joint_names) if hasattr(robot, 'joint_names') else None
print('[deploy] loop joints', jn, flush=True)
os._exit(0)

