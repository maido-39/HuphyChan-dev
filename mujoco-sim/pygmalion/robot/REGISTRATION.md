# mjlab upstream에 필요한 최소 수정 (Pygmalion 등록)

upstream `mujocolab/mjlab`(@20f10e96)에 아래를 적용해야 Pygmalion 로봇·태스크가 뜬다.
(`sync_to_mjlab.sh`가 robot 디렉토리는 복사해 준다. 아래 편집은 수동/확인.)

## 1) 로봇 등록 — `src/mjlab/asset_zoo/robots/__init__.py`
pygmalion 디렉토리를 `src/mjlab/asset_zoo/robots/pygmalion/`에 둔 뒤, import 추가:
```python
from mjlab.asset_zoo.robots.pygmalion.pygmalion_constants import (
  PYG_ACTION_SCALE as PYG_ACTION_SCALE,
)
from mjlab.asset_zoo.robots.pygmalion.pygmalion_constants import (
  get_pygmalion_robot_cfg as get_pygmalion_robot_cfg,
)
```

## 2) 태스크 등록 — `src/mjlab/tasks/velocity/config/pygmalion/`
`task_velocity_pygmalion/`를 `src/mjlab/tasks/velocity/config/pygmalion/`으로 복사.
이 폴더의 `__init__.py`가 `Mjlab-Velocity-Flat-Pygmalion` / `Mjlab-Velocity-Rough-Pygmalion`를 register.
velocity config가 이 서브패키지를 import하는지 확인(안 되면 `tasks/velocity/config/__init__.py`에
`from . import pygmalion` 추가). `uv run list-envs | grep Pygmalion`로 검증.

## 3) ls_parallel 패치 — `src/mjlab/sim/sim.py`
mujoco_warp ≥3.9.1이 `opt.ls_parallel`을 제거해 init crash → `hasattr` 가드:
```python
# _init_with_model() 내부, 기존:
#   self._wp_model.opt.ls_parallel = self.cfg.ls_parallel
# 변경:
if hasattr(self._wp_model.opt, "ls_parallel"):
    self._wp_model.opt.ls_parallel = self.cfg.ls_parallel
```
(variant 경로 line ~262도 동일 가드 권장 — flat/rough는 미발화.)

정확한 diff는 우리 mjlab 작업본과 upstream 20f10e96을 `git diff`로 비교.
