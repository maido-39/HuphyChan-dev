# -*- coding: utf-8 -*-
"""Gym registration for the biped velocity-tracking tasks."""

import gymnasium as gym

from . import agents

gym.register(
    id="Pygmalion-Velocity-Flat-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.flat_env_cfg:BipedFlatEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Flat-Forefoot-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.flat_env_cfg:BipedFlatForefootEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Flat-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.flat_env_cfg:BipedFlatEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Rough-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.velocity_env_cfg:BipedRoughEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedRoughPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Rough-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.velocity_env_cfg:BipedRoughEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedRoughPPORunnerCfg",
    },
)

# ★ ROUGH + forefoot/impact rewards (gear-ratio sweep rough+DR branch, user 2026-06-22)
gym.register(
    id="Pygmalion-Velocity-Rough-Forefoot-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.flat_env_cfg:BipedRoughForefootEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedRoughPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Rough-Forefoot-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.flat_env_cfg:BipedRoughForefootEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedRoughPPORunnerCfg",
    },
)

# ★ Unitree G1 VANILLA reward BASELINE on our robot (user 2026-06-22): HOLD gaitfix, see natural behavior
gym.register(
    id="Pygmalion-Velocity-Flat-G1Vanilla-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1VanillaEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Flat-G1Vanilla-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1VanillaEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

# ★ OUR latest gaitfix reward UNDER G1-MATCHED conditions (fair reward A/B vs full-G1, user 2026-06-22)
gym.register(
    id="Pygmalion-Velocity-Flat-OursG1cond-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedFlatForefootG1CondEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Flat-OursG1cond-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedFlatForefootG1CondEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

# ★ G1 vanilla base + minimal targeted (impact reduction + knee) -- the practical walker (user 2026-06-22)
gym.register(
    id="Pygmalion-Velocity-Flat-G1Impact-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1ImpactEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Flat-G1Impact-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1ImpactEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

# ★ G1 + impact + VERIFIED anti-trembling/saturation fixes (user 2026-06-28). FLAT first -> transfer to ROUGH.
gym.register(
    id="Pygmalion-Velocity-Flat-G1ImpactStable-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1ImpactStableEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Flat-G1ImpactStable-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1ImpactStableEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Rough-G1ImpactStable-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1ImpactStableRoughEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedRoughPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Rough-G1ImpactStable-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1ImpactStableRoughEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedRoughPPORunnerCfg",
    },
)

# ★ Human gait-reference tracking (contact-phase DeepMimic) — docs/reward_research/2026-06-29_human_gait_reference.
#   Warm-start from a G1ImpactStable flat ckpt (obs 239 unchanged). Fixes shuffle via a dense human-traj signal.
gym.register(
    id="Pygmalion-Velocity-Flat-HumanRef-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedHumanRefEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Flat-HumanRef-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedHumanRefEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Rough-HumanRef-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedHumanRefRoughEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedRoughPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Rough-HumanRef-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedHumanRefRoughEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedRoughPPORunnerCfg",
    },
)

# ★ v4: human-ref + toe_load_stance (push-off windlass) — docs/.../2026-06-29_human_gait_reference (toe review)
gym.register(
    id="Pygmalion-Velocity-Flat-HumanRefToe-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedHumanRefToeEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Flat-HumanRefToe-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedHumanRefToeEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

# ★ obs restructuring (Menlo blog review 2026-06-28): asymmetric actor-critic + base_lin_vel/toe critic-only + history
gym.register(
    id="Pygmalion-Velocity-Flat-G1ImpactStableAsymObs-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1ImpactStableAsymObsEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Flat-G1ImpactStableAsymObs-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1ImpactStableAsymObsEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Rough-G1ImpactStableAsymObs-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1ImpactStableAsymObsRoughEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedRoughPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Rough-G1ImpactStableAsymObs-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedG1ImpactStableAsymObsRoughEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedRoughPPORunnerCfg",
    },
)

# ★ Menlo/Asimov blog reward AS-IS (user 2026-06-28) — to surface the problems of direct application
gym.register(
    id="Pygmalion-Velocity-Flat-AsimovReward-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedAsimovRewardEnvCfg",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)

gym.register(
    id="Pygmalion-Velocity-Flat-AsimovReward-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    disable_env_checker=True,
    kwargs={
        "env_cfg_entry_point": f"{__name__}.g1_vanilla_env_cfg:BipedAsimovRewardEnvCfg_PLAY",
        "rsl_rl_cfg_entry_point": f"{agents.__name__}.rsl_rl_ppo_cfg:BipedFlatPPORunnerCfg",
    },
)
