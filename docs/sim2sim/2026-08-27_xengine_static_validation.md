# 교차엔진 정적 검증 — MuJoCo vs IsaacSim 5.0 (2026-08-27)

> *한 줄*: v4 URDF를 USD로 변환해 IsaacSim에 올리고, **같은 자세에서 중력 부하 토크가
> 17관절 전부 max 0.007 N·m(중앙값 0.0002) 이내로 일치**함을 확인했다. 모델 이전은 유효하다.

## 방법
1. `tools/sim2sim/urdf_to_usd.py` — `pygmalion_v4_printed.urdf` → USD.
   `merge_fixed_joints=False`(링크별 질량 비교 목적), `density=0`(URDF 관성 그대로, 재유도 금지).
2. 양쪽 다 베이스를 공중에 고정하고 동일한 비대칭 굽힘 자세(17관절 전부 모멘트암이 생기는 자세) 지정.
3. MuJoCo: `qfrc_bias`(qvel=0) = 중력 부하. IsaacSim: 강성 PD(kp 2000)로 자세 유지 후 3 s 정착,
   `get_measured_joint_efforts()` = 중력 부하.
4. ★1차 비교는 max 0.43 N·m 차이가 났는데, 이는 **서보 정착 오차(q_err 0.024 rad)** 때문 —
   Isaac은 실제 도달 자세의 토크를, MuJoCo는 명령 자세의 토크를 답하고 있었다.
   MuJoCo를 **Isaac이 실제 도달한 자세**에서 재평가하니 차이가 60배 줄었다.
   ⇒ 교차엔진 비교는 항상 "같은 질문"인지부터 검증할 것.

## 결과
| | 값 |
|---|---|
| 총질량 | **31.3163 kg 양쪽 동일** (그램 단위) |
| 관절 수 | 18링크 / 17회전관절 양쪽 동일 |
| 중력 토크 차이 | **max 0.0070 N·m / 중앙값 0.0002** (최대 부하 3.2 N·m 대비 0.2 %) |

## 재사용을 위한 엔진 함정 5개 (전부 실측)
1. isaacsim 5.0 pip은 **Python 3.11 전용** — 에러가 "no matching distribution"으로 나와 패키지 부재처럼 읽힘.
2. Kit이 stdout을 삼키고 **`SimulationApp.close()`는 프로세스를 즉시 종료** — 결과는 close() **전에** 파일로.
3. **`open_stage`는 World 생성 전에** — 뒤에 하면 World가 반쯤 초기화된 채 `_scene` AttributeError.
4. **베이스를 kinematic으로 만들면 articulation이 해체**됨(`dof_names=None`) — 고정은 FixedJoint(world→base)로.
5. Isaac articulation의 DOF 순서는 URDF 순서가 아니라 **폭 우선**(hip L/R, waist, ... 깊이순) — 이름으로 재매핑 필수.
   이것이 곧 배포 변환 레이어의 조인트 매핑 사양이다.

## 다음
정적 일치 ≠ 동적 일치. 접촉·솔버·적분기가 다르므로 **보행 정책 롤아웃 비교**가 다음 단계다:
RP 정책 ONNX를 IsaacSim에서 50 Hz로 돌려 추종·GRF·낙상을 MuJoCo와 대조.

도구: `tools/sim2sim/{urdf_to_usd,usd_static_check,xengine_static_torque,xengine_isaac_side}.py`
결과: `/home/syaro/pyg_fea/work/xengine_{mujoco,isaac,verdict}.json`
