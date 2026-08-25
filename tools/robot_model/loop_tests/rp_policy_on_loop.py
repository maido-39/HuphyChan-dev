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
rp_cfg = load_env_cfg('Mjlab-Velocity-Flat-Pygmalion', play=True); rp_cfg.scene.num_envs = 1
rp_cfg.events.pop('push_robot', None)
rp_env = ManagerBasedRlEnv(cfg=rp_cfg, device='cpu')
wrap = RslRlVecEnvWrapper(rp_env, clip_actions=load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion').clip_actions)
runner = (load_runner_cls('Mjlab-Velocity-Flat-Pygmalion') or MjlabOnPolicyRunner)(
    wrap, asdict(load_rl_cfg('Mjlab-Velocity-Flat-Pygmalion')), device='cpu')
runner.load(CK, load_cfg={'actor': True}, strict=True, map_location='cpu')
policy = runner.get_inference_policy(device='cpu')
print('[deploy] RP policy loaded', flush=True)


def rollout(env, envw, to_crank):
    """to_crank=None -> native serial run; else map the ankle action to crank targets."""
    robot = env.unwrapped.scene['robot']
    res = {}
    obs, _ = envw.reset()
    for cmd in CMDS:
        env.unwrapped.command_manager.get_term('twist').vel_command_b[:] = torch.tensor([cmd], dtype=torch.float32)
        v, e = [], []
        for t in range(STEPS):
            with torch.no_grad():
                act = policy(obs)
            if to_crank is not None:
                act = to_crank(act, robot)
            obs, _, _, _ = envw.step(act)
            env.unwrapped.command_manager.get_term('twist').vel_command_b[:] = torch.tensor([cmd], dtype=torch.float32)
            if t >= WARM:
                vv = robot.data.root_link_lin_vel_b[0, :2].numpy()
                v.append(vv); e.append(np.linalg.norm(vv - np.array(cmd[:2])))
        res[cmd] = (float(np.mean(e)), float(np.linalg.norm(np.mean(v, 0))), float(np.linalg.norm(cmd[:2])))
    return res


print('[deploy] baseline: RP policy on its own serial model', flush=True)
base = rollout(wrap, wrap, None)
for c, r in base.items():
    print(f'   cmd {c} -> err {r[0]:.3f}  achieved {r[1]:.2f} / {r[2]:.2f}', flush=True)
json.dump({'baseline': {str(k): v for k, v in base.items()}}, open(f'{OUT}/{TAG}.json', 'w'), indent=1)
print('[deploy] baseline written; the loop-model leg needs the AB env and an action remap', flush=True)
os._exit(0)
