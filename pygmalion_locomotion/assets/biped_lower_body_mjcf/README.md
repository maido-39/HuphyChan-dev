# URDF → MJCF 변환 (RobStride 하반신 이족 로봇, IsaacLab 학습용)

원본 URDF(`USD_Conversion_TEST`, Fusion 익스포터 출력)를 IsaacLab에서 학습 가능한
MJCF로 변환한 결과물입니다. 변환 방법 리서치 정리 + 실제 변환 파일 + 검증까지 포함합니다.

---

## 1. 변환 방법 리서치 (URDF → MJCF → IsaacLab)

### 1.1 핵심 사실
- **MuJoCo는 URDF를 직접 읽을 수 있습니다.** `mj_loadXML`(`mujoco.MjModel.from_xml_path`)이
  최상위 태그(`<robot>` = URDF, `<mujoco>` = MJCF)로 포맷을 자동 판별합니다.
  로드 후 `mj_saveLastXML`로 컴파일된 모델을 MJCF로 다시 내보낼 수 있습니다 →
  이것이 가장 신뢰성 높은 1차 변환 경로입니다.
- **단, 변환 시 액추에이터·센서·접촉설정·예쁜 구조는 보존되지 않습니다.**
  MuJoCo는 URDF의 transmission을 무시하므로 actuator는 변환 후 **수동으로 추가**해야 합니다.
- **IsaacLab은 MJCF를 USD로 임포트**합니다. `isaaclab.sim.converters.MjcfConverter` +
  `MjcfConverterCfg`가 내부적으로 `isaacsim.asset.importer.mjcf` 확장을 감싸 USD(instanceable)를 생성합니다.
  USD가 만들어지면 `ArticulationCfg(spawn=UsdFileCfg(...))`로 로드합니다.
- IsaacLab에서 **모터의 토크/속도 한계와 PD 게인은 보통 Python `ArticulationCfg`의
  Actuator 설정(`ImplicitActuatorCfg`/`DCMotorCfg`)에서 지정**합니다. MJCF가 USD로 넘겨주는 것은
  주로 기구학·질량/관성·관절 한계·armature(반사관성)·감쇠/마찰입니다.

### 1.2 URDF→MJCF에서 흔히 깨지는 지점 (그리고 처리법)
| 문제 | 처리 |
|---|---|
| `package://...` 경로 | 파일명만 남기고 `<compiler meshdir="meshes">`로 해결 |
| 메시 스케일 | 본 모델의 STL은 **이미 미터 단위**인데 URDF엔 `scale="0.001"` (익스포터 버그) → `scale=1`로 교정 |
| transmission/actuator 소실 | 변환 후 `<actuator>` 직접 작성 (모터 사양 반영) |
| 자기충돌 폭발 | 인접 링크 메시가 초기 자세에서 겹쳐 큰 접촉력 발생 → 충돌 필터링 필요 |
| 관성행렬 부정합 | `<compiler balanceinertia="true">`로 삼각부등식 위반 보정 |
| 자유부유 베이스 | URDF엔 free joint 없음 → MJCF에서 base에 `<freejoint>` 추가 |

### 1.3 본 변환의 파이프라인 (3단계, `convert_urdf_to_mjcf.py`)
1. **xacro → 평탄화 URDF**: `xacro:include` 제거, `package://` 제거, `scale=1` 교정,
   `<mujoco><compiler ...></mujoco>` 주입.
2. **MuJoCo로 raw MJCF 생성**: `from_xml_path` → `mj_saveLastXML`.
3. **후처리**: 의미 있는 관절/링크 이름, 모터별 actuator·기어비·armature·감쇠/마찰,
   충돌 스킴, 베이스 free joint, 기립 키프레임 추가.

---

## 2. 이 로봇의 구조 해석

하반신 이족(다리당 6 DOF + 발가락 1 = 7관절), 총 14관절, 총질량 **51.8 kg**, 키 ≈ 1.24 m.
원본 `Revolute N` 관절을 좌표축·가동범위·링크명으로 해석해 의미 있는 이름으로 매핑했습니다.

| 원본 | 관절 이름 | 기능 | 축 | 가동범위(rad) | 모터 |
|---|---|---|---|---|---|
| Revolute 1/8  | `*_hip_pitch_joint`  | 고관절 피치 | X | −2.18 ~ 0.52 | RS04 |
| Revolute 2/9  | `*_hip_roll_joint`   | 고관절 롤   | 경사축 | −0.79 ~ 0.44 | RS04 |
| Revolute 3/10 | `*_hip_yaw_joint`    | 고관절 요   | Z | −0.87 ~ 0.87 | RS03 |
| Revolute 4/11 | `*_knee_joint`       | 무릎       | X | −2.44 ~ 0.17 | RS04 + AT3 벨트 1:3 |
| Revolute 5/12 | `*_ankle_pitch_joint`| 발목 피치   | X | −0.87 ~ 0.70 | RS03 (링크 구동) |
| Revolute 6/13 | `*_ankle_roll_joint` | 발목 롤    | Y | −0.35 ~ 0.35 | RS00 |
| Revolute 7/14 | `*_toe_joint`        | 발가락     | X | −0.87 ~ 0    | **모터 미지정 → 패시브** |

---

## 3. 액추에이터 사양 반영 (RobStride, 출력축 기준)

| 모터 | 피크 토크 | 정격 토크 | 내부 감속 | 무부하 속도 | 적용 관절 |
|---|---|---|---|---|---|
| **RS04** | 120 N·m | 40 N·m | 9:1 | 200 rpm (20.9 rad/s) | hip pitch, hip roll |
| **RS04 + AT3 벨트 1:3** | **360 N·m** | 120 N·m | 9:1 × 3 = 27:1 | **66.7 rpm (6.98 rad/s)** | knee |
| **RS03** | 60 N·m | 20 N·m | 9:1 | 220 rpm (23.0 rad/s) | hip yaw, ankle pitch |
| **RS00** | 14 N·m | ~5 N·m | 10:1 | 315 rpm (33.0 rad/s) | ankle roll |

> 출처: RobStride 공식/유통 사양서. 피크·정격 토크와 무부하 속도는 모두 **모듈 출력축(내부 유성기어
> 포함 후)** 값이므로, 모터가 관절을 직접 구동하면 그대로 관절값으로 사용합니다.

### 3.1 무릎 — AT3 벨트 1:3
모터 출력 뒤에 벨트로 추가 1:3 감속. 관절 기준으로:
- 토크 = 120 × 3 = **360 N·m** (peak), 속도 = 200 ÷ 3 = **66.7 rpm**.
- 반사관성(armature)에는 총 감속비 27의 제곱(=729)이 반영됨 → 무릎 armature가 가장 큼(0.0875).
- MJCF에선 관절 좌표계로 `actuatorfrcrange="-360 360"`, `<motor ctrlrange="-360 360">`로 명시.
  IsaacLab cfg에선 `effort_limit=360`, `velocity_limit=6.98`로 지정.

### 3.2 발목 피치 — 링크(푸시로드) 구동
RS03가 발목 축에 직접 붙지 않고 링크 기구로 구동됩니다. 링크의 유효 전달비(레버암)는
관절 각도에 따라 변하지만, **링크 기하 정보가 URDF에 없어** 1차 모델에서는 유효비 ≈ 1:1로 두고
RS03 출력값(60 N·m, 23 rad/s)을 그대로 적용했습니다.
링크 치수를 알면 평균 기계적 이득으로 `effort_limit`를 스케일하거나, MuJoCo `equality/tendon`으로
실제 4절 링크를 모델링해 정밀화할 수 있습니다. (현재는 단일 회전관절 근사)

### 3.3 반사관성(armature) — 추정값, 튜닝 필요
`armature = J_rotor × (총 감속비)²`. RobStride는 로터 관성을 공개하지 않아
모터 크기 기반으로 추정했습니다(아래). **실측/시스템 식별로 보정 권장**합니다.

| class | armature | damping | frictionloss | 비고 |
|---|---|---|---|---|
| `rs04`      | 0.0097 | 1.0 | 0.3 | hip pitch/roll |
| `rs04_knee` | 0.0875 | 1.5 | 0.5 | 27:1 반영 |
| `rs03`      | 0.0049 | 0.5 | 0.2 | hip yaw, ankle pitch |
| `rs00`      | 0.0015 | 0.2 | 0.1 | ankle roll |
| `toe`       | 0.0005 | 0.2 | 0.05 | 패시브 + 복원스프링 stiffness=20 |

### 3.4 발가락 — 패시브 처리
모터가 지정되지 않아 **액추에이터 없이** 약한 복원 스프링(stiffness=20)+감쇠로 모델링했습니다.
세 가지 중 택1 권장: (a) 현행 패시브 유지, (b) 강체로 고정(`<weld>` 또는 발가락 관절 제거),
(c) 실제 토(toe-off) 모터가 있으면 사양 알려주시면 actuator 추가.

---

## 4. 충돌·안정성 처리
- 모든 충돌 geom에 `contype=1, conaffinity=0` → **로봇 자기충돌 OFF**(바닥과만 충돌).
  IsaacLab의 `self_collision=False` 기본값과 일치. 발-발/선택적 자기충돌이 필요하면
  해당 링크 conaffinity만 켜면 됩니다.
- 시각 geom(`group=2`, 무충돌)과 충돌 geom(`group=3`) 분리. 현재 충돌은 메시 볼록껍질 사용 →
  학습 속도·접촉 안정성을 위해 발은 박스 프리미티브로 교체하는 것을 권장.
- `balanceinertia=true`로 관성 보정, `integrator=implicitfast`, `timestep=0.005`(MuJoCo 테스트용).

---

## 5. 파일 구성
```
biped_lower_body_mjcf/
├── robot.xml                 # ★ 메인 MJCF (로봇 단독, IsaacLab 임포트 대상)
├── scene.xml                 # MuJoCo 테스트 씬 (바닥/조명 + robot.xml include)
├── robot.urdf                # 정리된 중간 URDF (참고용)
├── meshes/                   # STL 15개 (미터 단위)
├── biped_cfg.py              # ★ IsaacLab ArticulationCfg (모터별 actuator 그룹)
├── convert_urdf_to_mjcf.py   # 재현용 변환 스크립트
└── src_urdf/                 # 원본 xacro/trans/gazebo
```

## 6. 사용법

### 6.1 MuJoCo로 즉시 확인
```bash
pip install mujoco
python -m mujoco.viewer --mjcf=scene.xml     # 'stand' 키프레임으로 기립 확인
```

### 6.2 IsaacLab으로 가져오기
```python
from isaaclab.sim.converters import MjcfConverter, MjcfConverterCfg
cfg = MjcfConverterCfg(asset_path="robot.xml", usd_dir="./usd",
                       usd_file_name="biped_lower_body.usd",
                       fix_base=False, import_inertia_tensor=True,
                       self_collision=False, make_instanceable=True)
usd_path = MjcfConverter(cfg).usd_path
```
이후 `biped_cfg.py`의 `BIPED_CFG`(`spawn=UsdFileCfg(usd_path=...)`)를 환경에 사용하세요.
actuator 그룹은 관절명 정규식(`.*_hip_pitch_joint` 등)으로 묶여 있어 그대로 매칭됩니다.

---

## 7. 검증 결과 (MuJoCo 3.9)
- `robot.xml` 컴파일 성공: nq=21, nv=20, **actuator=12**(발가락 2개 제외), body=16.
- 모터별 `armature/damping/frictionloss/actuatorfrcrange` 정상 반영(예: knee ±360, hip ±120).
- **베이스 공중 고정 + PD 자세유지**: 다리가 중력 하중 하에서 목표자세 추종오차 ≈ 0 →
  모델·액추에이터 정합성 확인.
- 자유 베이스에서 제어 없이 주저앉음은 **밸런스 정책 부재(정상)** — RL이 학습할 부분이며 NaN/폭발 없음.
- 렌더링으로 외형(몸통+양다리 비례, 기립 높이 0.87 m) 확인.

## 8. 학습 전 점검·튜닝 체크리스트
1. **armature/감쇠/마찰**: 실측 또는 식별로 보정(특히 무릎·발목 링크).
2. **발목 피치 링크 전달비**: 실제 4절 링크 기하로 정밀화 또는 평균비로 effort 스케일.
3. **발가락 처리**: 패시브 유지 / 고정 / 모터 추가 중 결정.
4. **발 충돌**: 메시 → 박스 프리미티브 교체로 접촉 안정성·속도 개선.
5. **PD 게인(`stiffness/damping`)**: `biped_cfg.py`의 값은 시작점 — 과제에 맞게 튜닝.
6. **초기 자세**: 직립(0)보다 무릎 약간 굽힘이 보행 학습에 유리할 수 있음.
