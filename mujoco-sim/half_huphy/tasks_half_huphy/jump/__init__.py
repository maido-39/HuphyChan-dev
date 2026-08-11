"""Register Half Huphy jump / hop tasks."""

from mjlab.tasks.registry import register_mjlab_task

from .env_cfgs import half_huphy_jump_env_cfg
from .rl_cfg import half_huphy_jump_ppo_runner_cfg

register_mjlab_task(
  task_id="Mjlab-Jump-HalfHuphy",
  env_cfg=half_huphy_jump_env_cfg(),
  play_env_cfg=half_huphy_jump_env_cfg(play=True),
  rl_cfg=half_huphy_jump_ppo_runner_cfg(),
)

# Same hop task + explicit knee crouch→extend shaping (train in parallel).
register_mjlab_task(
  task_id="Mjlab-JumpKnee-HalfHuphy",
  env_cfg=half_huphy_jump_env_cfg(knee_crouch=True),
  play_env_cfg=half_huphy_jump_env_cfg(play=True, knee_crouch=True),
  rl_cfg=half_huphy_jump_ppo_runner_cfg(experiment_name="half_huphy_jump_knee"),
)

# JumpKnee with deeper crouch (60°) and 2× extension-speed scale (8 rad/s).
register_mjlab_task(
  task_id="Mjlab-JumpKnee60-HalfHuphy",
  env_cfg=half_huphy_jump_env_cfg(
    knee_crouch=True,
    knee_target_deg=60.0,
    knee_extend_vel_scale=8.0,
  ),
  play_env_cfg=half_huphy_jump_env_cfg(
    play=True,
    knee_crouch=True,
    knee_target_deg=60.0,
    knee_extend_vel_scale=8.0,
  ),
  rl_cfg=half_huphy_jump_ppo_runner_cfg(experiment_name="half_huphy_jump_knee60"),
)

# JumpKnee + ankle motors retuned (±14 Nm, armature 0.002, frictionloss 0.116).
register_mjlab_task(
  task_id="Mjlab-JumpKneeAnkle14-HalfHuphy",
  env_cfg=half_huphy_jump_env_cfg(knee_crouch=True, ankle14=True),
  play_env_cfg=half_huphy_jump_env_cfg(play=True, knee_crouch=True, ankle14=True),
  rl_cfg=half_huphy_jump_ppo_runner_cfg(
    experiment_name="half_huphy_jump_knee_ankle14"
  ),
)

# Ankle14 + soft torque limit + stronger push / ground-friction DR.
register_mjlab_task(
  task_id="Mjlab-JumpKneeAnkle14Torque-HalfHuphy",
  env_cfg=half_huphy_jump_env_cfg(
    knee_crouch=True,
    ankle14=True,
    torque_softlimit=True,
    push_xy_scale=2.0,  # max push ±1.0 m/s
    ground_friction_dr=True,  # sliding μ × [0.5, 1.5]
  ),
  play_env_cfg=half_huphy_jump_env_cfg(
    play=True,
    knee_crouch=True,
    ankle14=True,
    torque_softlimit=True,
    push_xy_scale=2.0,
    ground_friction_dr=True,
  ),
  rl_cfg=half_huphy_jump_ppo_runner_cfg(
    experiment_name="half_huphy_jump_knee_ankle14_torque"
  ),
)
