# 05 · 센싱 & 로깅 (토크 / 축력(x,y,z 반력) / GRF)

> [!abstract] 목표 (산출물 핵심)
> 걷는 동안 **각 관절 토크**, **각 링크의 축력(=관절 반력 Fx,Fy,Fz)+모멘트**, **발 지면반력(GRF)**을
> 실시간으로 보고 CSV/npz로 로깅해 하드웨어 설계에 쓴다.

---

## 왜 (Why)
모터 선정·구조 강도 설계에는 "실제 보행 시 각 부위에 얼마의 힘/토크가 걸리나"가 필요하다.
시뮬에서 이를 정확히 뽑아내면 실물 제작 전 설계 마진을 정량적으로 잡을 수 있다.

## 무엇을 — 3가지 물리량과 정확한 API
| 물리량 | Isaac Lab API | shape | 단위/프레임 |
|---|---|---|---|
| **관절 토크** | `robot.data.applied_torque` | (envs, 관절) | N·m (actuator가 실제 인가) |
| **링크 축력/반력** | `robot.data.body_incoming_joint_wrench_b` | (envs, 링크, **6**) | Fx,Fy,Fz [N] · Tx,Ty,Tz [N·m], **부모 body frame** |
| **발 GRF** | `contact_sensor.data.net_forces_w` | (envs, body, 3) | N, **world frame** |

> `body_incoming_joint_wrench_b` = PhysX `get_link_incoming_joint_force()`.
> "부모→자식 관절이 전달하는 반력". 루트(base_link)→world 반력도 포함 → **베이스 반력**도 측정됨.
> 이것이 사용자가 요청한 "각 링크에 걸리는 축력(x,y,z 반력)"이다.

## 어디서 (Where)
- `sensors/wrench_logger.py` → `WrenchLogger`
  - `record(sim_time, command)` : 매 스텝 env0 데이터 누적
  - `save(tag)` : `logs/measure/<tag>.csv` + `.npz` + `_meta.json`(단위/이름표)
  - `latest_summary()` : HUD용 (관절토크 dict + 발 GRF + base 높이)
- CSV 컬럼: `time, base_height, cmd_*`, `tau_<joint>`, `Fx/Fy/Fz/Tx/Ty/Tz_<body>`, `GRF_<foot>_{x,y,z,mag}`

## 어떻게 (How) — 사용
```python
from pygmalion_locomotion.sensors import WrenchLogger
logger = WrenchLogger(robot, contact_sensor, foot_body_regex=".*_foot_link", out_dir="logs/measure")
# loop:
logger.record(sim_t, command=(vx,vy,wz))
# end:
logger.save(tag="rough_m1.0")   # -> CSV/NPZ/meta
```
- 실시간 표시: [[06_teleop]]의 HUD가 `latest_summary()`로 갱신.
- 오프라인 분석: `scripts/analyze.py` → 관절토크 peak/RMS, 링크 축력 peak, GRF, **모터 정격 대비표** + 그래프.

## 질량 조정 (요구사항)
`sensors/mass_utils.py`:
- `apply_mass_scale(robot, scale)` : 전 링크 질량·관성 ×scale (균일 스케일)
- `set_base_mass(robot, kg)` : base_link 절대질량 지정(+관성 비례)
- `get_mass_summary(robot)` : 링크별 질량 + TOTAL
> PhysX `set_masses/set_inertias`는 CPU 텐서·리셋 직후 호출. 측정 시 질량을 바꿔가며 하중 변화를 본다.

## 검증 포인트
- 정지 기립 시 `Fz_base_link` ≈ 총중량×g (예: 51.8kg×9.81 ≈ 508 N) → 반력 부호/크기 sanity.
- 발 GRF 합 ≈ 총중량 (접지 중). 한 발 지지기엔 한쪽 발에 집중.

## 다음 노트
- [[06_teleop]] · [[07_measurement]]
