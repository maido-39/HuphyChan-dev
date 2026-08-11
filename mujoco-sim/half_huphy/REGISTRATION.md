# mjlab에 Half Huphy 등록 (최소 수정)

`sync_to_mjlab.sh`가 로봇·태스크 디렉토리를 복사하고, 아래 import가 없으면
`asset_zoo/robots/__init__.py`에 자동으로 넣는다.

## 1) 로봇 등록 — `src/mjlab/asset_zoo/robots/__init__.py`

```python
from mjlab.asset_zoo.robots.half_huphy.half_huphy_constants import (
  HALF_HUPHY_ACTION_SCALE as HALF_HUPHY_ACTION_SCALE,
)
from mjlab.asset_zoo.robots.half_huphy.half_huphy_constants import (
  get_half_huphy_robot_cfg as get_half_huphy_robot_cfg,
)
```

## 2) 태스크 등록 — 자동

`src/mjlab/tasks/half_huphy/`를 두면 `tasks/__init__.py`의 `import_packages`가
balance / jump 서브패키지를 로드하면서 `register_mjlab_task`가 실행된다.
별도 `tasks/__init__.py` 수정은 보통 필요 없다.

## 3) 검증

```bash
uv run list-envs | grep HalfHuphy
```

기대 태스크 ID:
- `Mjlab-Balance-HalfHuphy`
- `Mjlab-Jump-HalfHuphy`
- `Mjlab-JumpKnee-HalfHuphy`
- `Mjlab-JumpKnee60-HalfHuphy`
- `Mjlab-JumpKneeAnkle14-HalfHuphy`
- `Mjlab-JumpKneeAnkle14Torque-HalfHuphy`
