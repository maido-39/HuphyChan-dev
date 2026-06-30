# Adversarial verify: IsaacLab 2.2 curriculum mechanism (flat→rough transfer)

Date: 2026-06-29
Type: adversarial verification (subagent), primary-source code read
Verdict: **PARTIALLY SUPPORTED** — core mechanism correct, but one factual claim is WRONG.

## Claim under test
> IsaacLab 2.2 terrain curriculum is ONLY `terrain_levels_vel` (no command/mass/friction
> curriculum built-in); custom terms must be added to CurriculumCfg. All curriculum terms are
> called every reset if env_ids arg; they mutate env state live.

## What is CORRECT (verified in source)
- `CurriculumManager.compute()` iterates `zip(self._term_names, self._term_cfgs)` and calls
  `term_cfg.func(self._env, env_ids, **term_cfg.params)`, storing return for logging.
  (curriculum_manager.py L124-139) ✔
- `compute(env_ids=...)` is called from `ManagerBasedRLEnv._reset_idx()` (L358), which runs
  inside `step()` only `if len(reset_env_ids) > 0` (L216-221). So curriculum updates fire on
  the resetting envs each step that has resets — and `env_ids` is the **subset** that reset
  (not a global `slice(None)`). Terms mutating global state (terrain levels, command ranges)
  still take effect for everyone. ✔ (claim's "every reset" wording is slightly loose: it is
  per-reset-batch, env_ids = only the envs that reset, but the live-mutation point stands.)
- The **velocity task** mdp (`.../locomotion/velocity/mdp/curriculums.py`) defines ONLY
  `terrain_levels_vel`. ✔
- `velocity_env_cfg.py` `CurriculumCfg` has only `terrain_levels = CurrTerm(func=mdp.terrain_levels_vel)`. ✔
- `__post_init__` (L322-329) conditionally sets `terrain_generator.curriculum = True` iff
  `getattr(self.curriculum, "terrain_levels", None) is not None`. ✔ (proposed-action guidance correct)

## What is WRONG / outdated
The phrase **"no command/mass/friction curriculum built-in ... custom terms MUST be added"** is
FALSE for IsaacLab 2.2. The **core** module
`source/isaaclab/isaaclab/envs/mdp/curriculums.py` ships GENERIC built-in curriculum terms:
- `class modify_reward_weight(ManagerTermBase)` — step-scheduled reward weight change.
- `class modify_env_param(ManagerTermBase)` — modifies ANY env attribute via dotted-path
  `address` + user `modify_fn` (docstring lists physics material props, observation ranges as
  examples → covers friction).
- `class modify_term_cfg(modify_env_param)` — simplified-address sibling; docstring's own
  example modifies a COMMAND range:
  `address="commands.object_pose.ranges.pos_x"`, returns new value after `num_steps`.

So command-range and friction curricula do NOT require a fully-custom function — you can use
`mdp.modify_term_cfg` / `mdp.modify_env_param` with a small `modify_fn`. (You DO still have to
add the term to your CurriculumCfg, and the velocity *task* preset doesn't include them by
default — that part of the claim is fine.)

## Safety note for our heavy low-impact load-measurement biped
- `terrain_levels_vel` move-up criterion = walked > `terrain_generator.size[0]/2`; move-down =
  walked < commanded_dist*0.5. Generic, not impact-aware. A terrain curriculum will push the
  policy onto harder terrain purely on locomotion distance — it does NOT bound GRF. For a HW
  that breaks at 1.5–2.7 kN, terrain difficulty escalation can raise peak GRF unmonitored.
  Recommend: cap `max_init_terrain_level`, and add a GRF/impact-gated guard rather than relying
  on the stock distance curriculum.
- `modify_env_param`/`modify_term_cfg` gate on `env.common_step_counter` (global step), not on
  any safety/impact metric — same caveat.

## Refs (primary)
- curriculum_manager.py L124-139, L92-122
  file:///home/syaro/MikuchanRemote/Human-Pygmalion/sim/IsaacLab/source/isaaclab/isaaclab/managers/curriculum_manager.py
- core mdp curriculums.py (modify_reward_weight / modify_env_param / modify_term_cfg)
  file:///home/syaro/MikuchanRemote/Human-Pygmalion/sim/IsaacLab/source/isaaclab/isaaclab/envs/mdp/curriculums.py
- velocity_env_cfg.py CurriculumCfg L277-281, __post_init__ L322-329
  file:///home/syaro/MikuchanRemote/Human-Pygmalion/sim/IsaacLab/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/velocity_env_cfg.py
- velocity mdp curriculums.py (terrain_levels_vel only)
  file:///home/syaro/MikuchanRemote/Human-Pygmalion/sim/IsaacLab/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/mdp/curriculums.py
- manager_based_rl_env.py compute call site L358, step reset gate L216-221
  file:///home/syaro/MikuchanRemote/Human-Pygmalion/sim/IsaacLab/source/isaaclab/isaaclab/envs/manager_based_rl_env.py
