"""``bake policy`` - export a trained checkpoint to ONNX plus everything needed to prove the
viewer reproduces the trainer's input/output contract.

Three artefacts, and the second and third exist because "it looks right" is not evidence:

  ``<name>.onnx``                 the actor, exported through mjlab's own
                                  ``MjlabOnPolicyRunner.export_policy_to_onnx`` (opset 18,
                                  dynamo off) with ``attach_metadata_to_onnx`` metadata.
  ``<name>.policy_contract.json`` obs terms and their dims, obs/action joint names in the
                                  env's resolved order, action scale, default pose, clip,
                                  ``model_contract_sha``, run dir, env.yaml sha, ckpt sha.
  ``<name>.parity.npz``           32 random observations and the .pt policy's output for
                                  each, so the ONNX session can be proven equivalent.
  ``<name>.obs_parity.npz``       40 consecutive control steps of the REAL env: the raw
                                  ingredients an observation builder needs, next to the
                                  observation the env's own ObservationManager produced.
                                  This is what pins term order, the 2-frame history
                                  direction and the sign of projected gravity - measured,
                                  not read off the source and hoped for.

This module is imported by bake.py; it is separate only to keep bake.py readable.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .contract import canonical_sha, sha256_file, load_contract


def bake_policy(
  pt_path: str, variant: str, cache_dir: str, name: str | None = None, init_bent: bool = True
) -> dict:
  from .bake import TASK, variant_env, _git_head
  from . import REPO

  ckpt = Path(pt_path).resolve()
  if not ckpt.exists():
    raise FileNotFoundError(f"checkpoint not found: {ckpt}")
  run_dir = ckpt.parent
  name = name or f"{variant}__{run_dir.name}__{ckpt.stem}"

  # The model contract must exist first: a policy is only meaningful against the model it
  # was trained on, and the sha of that model contract is what the runtime checks.
  model_contract = load_contract(cache_dir, variant)

  os.environ.update(variant_env(variant, init_bent=init_bent))
  os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

  t0 = time.time()
  from dataclasses import asdict

  import numpy as np
  import torch

  import mjlab.tasks  # noqa: F401
  from mjlab.envs import ManagerBasedRlEnv
  from mjlab.rl import MjlabOnPolicyRunner, RslRlVecEnvWrapper
  from mjlab.rl.exporter_utils import attach_metadata_to_onnx, get_base_metadata
  from mjlab.tasks.registry import load_env_cfg, load_rl_cfg, load_runner_cls

  cfg = load_env_cfg(TASK, play=True)
  cfg.scene.num_envs = 1
  # Nominal robot: no domain randomisation, no mid-episode command resampling. Same
  # convention as analysis/gait_kinematics_probe.py, so the recorded observations describe
  # the model, not one draw of a randomised one.
  dropped = []
  for ev in list(cfg.events):
    if ev in ("push_robot", "foot_friction", "encoder_bias", "base_com") or ev.startswith(
      "inertial_dr_"
    ):
      cfg.events.pop(ev)
      dropped.append(ev)
  big = cfg.episode_length_s + 100.0
  cfg.commands["twist"].resampling_time_range = (big, big)

  env = ManagerBasedRlEnv(cfg=cfg, device="cpu")
  rl_cfg = load_rl_cfg(TASK)
  envw = RslRlVecEnvWrapper(env, clip_actions=rl_cfg.clip_actions)
  runner = (load_runner_cls(TASK) or MjlabOnPolicyRunner)(envw, asdict(rl_cfg), device="cpu")
  runner.load(str(ckpt), load_cfg={"actor": True}, strict=True, map_location="cpu")
  policy = runner.get_inference_policy(device="cpu")

  robot = env.scene["robot"]
  names = list(robot.joint_names)
  default_q = np.asarray(robot.data.default_joint_pos[0]).flatten()
  term = env.action_manager._terms["joint_pos"]
  act_names = list(term._target_names)
  om = env.observation_manager
  obs_dim = int(om.group_obs_dim["actor"][0])

  # ---------------------------------------------------------------- ONNX export
  out_dir = Path(cache_dir)
  out_dir.mkdir(parents=True, exist_ok=True)
  onnx_name = f"{name}.onnx"
  runner.export_policy_to_onnx(str(out_dir), onnx_name)
  onnx_path = out_dir / onnx_name
  meta = get_base_metadata(env, run_path=str(run_dir))
  meta.update(
    {
      "pygviewer_variant": variant,
      "pygviewer_model_contract_sha": model_contract.contract_sha,
      "checkpoint": str(ckpt),
      "obs_dim": obs_dim,
      "action_dim": len(act_names),
    }
  )
  attach_metadata_to_onnx(str(onnx_path), meta)

  # ---------------------------------------------------------------- .pt parity set
  rng = np.random.default_rng(0)
  # Observations are z-scored-ish quantities of order 1; 0.5 sigma keeps the samples in the
  # region the policy actually sees without pinning them to zero.
  parity_obs = rng.normal(0.0, 0.5, size=(32, obs_dim)).astype(np.float32)
  # rsl_rl's MLPModel takes a DICT of observation groups, not a bare tensor. The actor uses
  # only the "actor" group; the critic groups are absent at inference.
  obs_group = policy.obs_groups[0] if getattr(policy, "obs_groups", None) else "actor"
  from tensordict import TensorDict

  def infer(t):
    """The model takes a TensorDict of observation groups; the actor uses only its own."""
    return policy(TensorDict({obs_group: t}, batch_size=[t.shape[0]]))

  with torch.no_grad():
    parity_act = infer(torch.from_numpy(parity_obs)).cpu().numpy().astype(np.float32)

  # ---------------------------------------------------------------- env obs recording
  rec = _record_obs(env, envw, infer, om, robot, names, act_names, np, torch, obs_group=obs_group)

  np.savez(
    out_dir / f"{name}.parity.npz",
    obs=parity_obs,
    action=parity_act,
    checkpoint=str(ckpt),
    model_contract_sha=model_contract.contract_sha,
  )
  np.savez(out_dir / f"{name}.obs_parity.npz", **rec)

  # ---------------------------------------------------------------- contract
  env_yaml = run_dir / "params" / "env.yaml"
  contract = dict(
    contract_version=1,
    obs_group=obs_group,
    kind="policy",
    name=name,
    variant=variant,
    task=TASK,
    checkpoint=str(ckpt),
    ckpt_sha256=sha256_file(ckpt),
    run_dir=str(run_dir),
    env_yaml=str(env_yaml) if env_yaml.exists() else None,
    env_yaml_sha256=sha256_file(env_yaml) if env_yaml.exists() else None,
    model_contract_sha=model_contract.contract_sha,
    model_variant=variant,
    onnx=str(onnx_path),
    onnx_sha256=sha256_file(onnx_path),
    parity_npz=str(out_dir / f"{name}.parity.npz"),
    obs_parity_npz=str(out_dir / f"{name}.obs_parity.npz"),
    obs_dim=obs_dim,
    action_dim=len(act_names),
    obs_terms=_obs_terms(om, names, np),
    obs_joint_names=model_contract.raw["obs_joint_names"],
    action_joint_names=act_names,
    action_scale=model_contract.raw["action_scale"],
    clip_actions=rl_cfg.clip_actions,
    default_q={n: round(float(q), 8) for n, q in zip(names, default_q)},
    safe_clip=model_contract.raw["safe_clip"],
    env_toggles={k: v for k, v in os.environ.items() if k.startswith("PYG_")},
    dropped_events=dropped,
    mjlab_git=_git_head(Path(REPO) / "mujoco-sim/mjlab"),
    bake_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    bake_seconds=round(time.time() - t0, 1),
  )
  contract["contract_sha"] = canonical_sha(contract)
  (out_dir / f"{name}.policy_contract.json").write_text(json.dumps(contract, indent=1))

  print(
    f"BAKE_POLICY_OK {name}\n"
    f"  onnx        {onnx_path.name}  ({onnx_path.stat().st_size / 1e3:.0f} kB)\n"
    f"  obs/action  {obs_dim} / {len(act_names)}\n"
    f"  model sha   {model_contract.contract_sha[:12]}\n"
    f"  ckpt        {ckpt}\n"
    f"  obs record  {rec['env_obs'].shape[0]} steps\n"
    f"  {contract['bake_seconds']} s"
  )
  return contract


def _obs_terms(om, names, np) -> list[dict]:
  """Per actor term: name, dim, joint names, history length - the env's own resolution."""
  out = []
  for nm, tcfg in zip(om._group_obs_term_names["actor"], om._group_obs_term_cfgs["actor"]):
    ac = tcfg.params.get("asset_cfg")
    ids = getattr(ac, "joint_ids", None) if ac is not None else None
    jn = None
    if ids is not None:
      jn = names[ids] if isinstance(ids, slice) else [names[i] for i in ids]
    h = int(getattr(tcfg, "history_length", 0) or 0)
    base = len(jn) if jn else None
    out.append(
      dict(
        name=nm,
        func=getattr(tcfg.func, "__name__", str(tcfg.func)),
        sensor_name=tcfg.params.get("sensor_name"),
        command_name=tcfg.params.get("command_name"),
        joint_names=jn,
        history_length=h,
        dim=(base * max(h, 1)) if base else None,
        source_default="sim",
      )
    )
  return out


def _record_obs(env, envw, infer, om, robot, names, act_names, np, torch, obs_group="actor",
                steps: int = 40):
  """Roll the env and record, per control step, the observation AND its ingredients.

  Everything is read the way a deployment runtime would have to read it: joint angles from
  the entity's own joint_pos in ``robot.joint_names`` order, IMU values straight out of
  ``sensordata``, the previous RAW action out of the action term.  If a builder fed these
  reproduces ``env_obs``, the builder has the contract right.
  """
  import mujoco

  m = env.sim.mj_model
  obs_names = None
  for nm, tcfg in zip(om._group_obs_term_names["actor"], om._group_obs_term_cfgs["actor"]):
    ac = tcfg.params.get("asset_cfg")
    ids = getattr(ac, "joint_ids", None) if ac is not None else None
    if ids is not None:
      obs_names = names[ids] if isinstance(ids, slice) else [names[i] for i in ids]
      break
  jidx = [names.index(n) for n in obs_names]
  s_adr = {}
  for s in range(m.nsensor):
    nm = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_SENSOR, s) or ""
    s_adr[nm.split("/")[-1]] = (int(m.sensor_adr[s]), int(m.sensor_dim[s]))

  def t2n(x):
    return np.asarray(x.detach().cpu()).astype(np.float64)

  got = envw.get_observations()
  obs = got[0] if isinstance(got, tuple) else got
  rows = dict(env_obs=[], motor_q=[], gyro=[], upvector=[], last_action=[], cmd=[], action=[],
              base_z=[])
  for _ in range(steps):
    actor_obs = obs[obs_group]
    sd = t2n(env.sim.data.sensordata)[0]
    rows["env_obs"].append(t2n(actor_obs)[0])
    rows["motor_q"].append(t2n(robot.data.joint_pos)[0][jidx])
    a, n_ = s_adr["imu_ang_vel"]
    rows["gyro"].append(sd[a : a + n_])
    a, n_ = s_adr["imu_upvector"]
    rows["upvector"].append(sd[a : a + n_])
    rows["last_action"].append(t2n(env.action_manager._terms["joint_pos"].raw_action)[0])
    rows["cmd"].append(t2n(env.command_manager.get_command("twist"))[0])
    rows["base_z"].append(float(t2n(robot.data.root_link_pos_w)[0][2]))
    with torch.no_grad():
      act = infer(actor_obs)
    rows["action"].append(t2n(act)[0])
    stepped = envw.step(act)
    obs = stepped[0]
  out = {k: np.asarray(v, dtype=np.float64) for k, v in rows.items()}
  out["obs_joint_names"] = np.asarray(obs_names)
  out["default_q_obs"] = np.asarray(
    [float(robot.data.default_joint_pos[0][names.index(n)]) for n in obs_names]
  )
  return out
