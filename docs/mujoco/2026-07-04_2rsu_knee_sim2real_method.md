# ★ 2-RSU 발목·링크 무릎 sim2real — 검증된 방법론 (실사례 리포트)

> 2026-07-04. 질문: 2-RSU 발목·링크 무릎을 실제로 sim2real 한 프로젝트 + 방법. deep-research `wfq8orh7p`(6 findings 확증, 1 반박). ★**결론이 우리 계획을 단순화**: sim은 직렬 그대로, 변환은 배포 경계에서.

## 결정적 결론 (한 줄)
> **직렬(serial)로 sim 학습 → 배포 시 transposed-Jacobian + PD로 병렬 모터에 변환.** 엔진 native 구속(equality/weld/tendon)으로 폐쇄연쇄를 sim에 넣는 팀은 **한 곳도 없음.**

## 실 사례 (하드웨어 검증)

### ★ 1. Booster Gym (Booster T1) — 우리가 복사할 레퍼런스
- **arXiv:2506.15132 + GitHub `BoosterRobotics/booster_gym` (오픈소스)**
- 방법: **가상 직렬 구조로 학습**(GPU 물리엔진 친화·효율) → **SDK의 series-parallel 변환 모듈**이 배포 시 "kinematic model로 가상관절 pos/vel 재구성 + **transposed Jacobian + PD**로 정책출력을 병렬구조로 변환"
- ★ 정밀 독해: transposed Jacobian은 **$\tau = J^T F$**(토크 사상), 즉 **PD로 계산한 가상관절 토크를 병렬 액추에이터 effort로 매핑**. full IK 아님.
- **실기 검증**: T1 전방향 보행(잔디·돌·흙·경사 10°), **1m서 10kg 낙하 충격 회복.** ← 병렬발목 sim2real이 이 방식으로 실증됨.

### 2. Unitree G1 — 왜 직렬 sim이 통하나
- **mujoco_menagerie g1.xml = 순수 직렬 힌지**(ankle pitch/roll 독립, equality/tendon **없음**), 실기 zero-shot 전이(MuJoCo Playground arXiv:2502.08844).
- ★ **핵심**: 폐쇄연쇄는 **Unitree 펌웨어 "PR 모드"가 pitch/roll → A/B 모터 변환**을 담당. 즉 **직렬 sim이 통하는 건 "무언가(펌웨어 or 내 Jacobian 층)가 경계에서 변환하기 때문."** → ★**RobStride엔 이 펌웨어 없음 → 우리가 변환층을 직접 만들어야 함**(= Booster Gym 방식).

### 3. ASAP (G1) — 대안: 학습-시 잔차
- **arXiv:2502.01143**: 발목 폐쇄연쇄를 **아예 모델링 안 함** → **4-DOF 발목 delta/residual action을 학습**해 링크 gap 흡수(학습-시 보정, 배포 모듈 아님). (반박: ASAP는 sim 표현법 자체는 공개 안 함.)

### 4. Menlo/Asimov — 사례 있으나 방법 비공개
- 병렬 RSU 발목, <100일 zero-shot 보행+푸시회복. 단 **정확한 발목 sim 표현·모터 매핑은 미공개**. 존재 증거지 방법 레퍼런스 아님.

### 5. LiPS (Tien Kung) — 반대 접근도 결국 Jacobian
- **arXiv:2503.08349**: sim에 **폐쇄연쇄 동역학 직접** 학습(실기 보행 검증). 단 **이조차 엔진 equality가 아니라 해석적 kinematics/Jacobian 매핑 층** 사용.

### 6. ★ 전 사례 공통 (핵심)
**RL 배포서 MuJoCo/Isaac native equality/tendon으로 발목 폐쇄연쇄를 닫는 팀 = 없음.** 이유: 대규모 병렬 학습서 구속은 느리고·GPU 비친화·불안정. 전부 **직렬추상+경계 Jacobian/펌웨어 변환**, 또는 **학습 잔차**로 처리.

## ★ 우리 계획에의 함의 (내 이전 방향 교정)

내가 "sim에 2-RSU 병렬기구를 equality로 모델링"하려던 건 **아무도 안 하는 방식**이었습니다. 교정:
1. ✅ **우리 mjlab sim은 이미 직렬(ankle pitch/roll 독립) = 올바른 표현.** 병렬 sim 모델링 **불필요**(큰 작업 제거).
2. ★ **배포 변환층을 만든다**: 2-RSU 발목 = **transposed Jacobian + PD**(Booster Gym 오픈소스 참조)로 정책의 직렬 관절출력 → 2 모터 명령. = peer("Jacobian 임피던스 하니 잘 됨")와 **정확히 일치**.
3. **링크 무릎**: 1-DOF라 더 쉬움 — 스칼라 전달비 **r(q)**로 모터각↔관절각 매핑(직렬 sim + 경계 변환).
4. **gap 크면**: ASAP식 residual action 추가(옵션).
5. **DR·ID**: Duke/Berkeley zero-shot 성공요인 = 정확한 액추에이터 모델+DR → 우리 관절 ID(사인스윕) 필수.

## 우리 2-RSU 배포 파이프라인 (확정)
```
[mjlab 직렬 sim 학습] → 정책 (가상 ankle_pitch/roll·knee 관절출력)
     ↓ (배포 경계, 실기 온보드)
[변환층]  ankle: tau_virtual = PD(q*,q) -> f_motor = J(q)^{-T} tau_virtual  (2 motors)
          knee:  q_motor = r(q_knee)^{-1} q_knee     (scalar link ratio)
     ↓
[RobStride 2-RSU + 링크 무릎]  + LPF(in/out) + 150Hz + 종단저항
```

## 리스크·완화 (사례 근거)
| 리스크 | 완화 (출처) |
|---|---|
| 병렬 임피던스 mismatch("튀고 깨짐") | transposed-Jacobian+PD 변환(Booster Gym·peer) |
| 링크비 sim-real 불일치 | J(q)/r(q) 실측 캘리브 + 관절 ID |
| 잔여 gap | ASAP residual action(옵션) |
| 정지-서기 불안정(MEVITA) | 자세정책 별도(S1) |

## 참고
Booster Gym(arXiv:2506.15132·GitHub)·MuJoCo Playground(2502.08844)·ASAP(2502.01143)·LiPS(2503.08349)·mujoco_menagerie G1·Menlo Asimov 블로그.
