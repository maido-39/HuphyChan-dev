# 실험 큐 (toe-roll / 충격 / 자연gait)

> 계획된 실험을 순서·가설·H-A·판정기준으로 관리. research `wyvmh4gpv`가 설계/순서 refine 예정. 실행은 [[experiments/INDEX]]에 기록.

## 진행 중
- **soft_contact** (running): 충격 보상(landing_vel-2.0 + impact_force) 단독, 옛 PD. → 완주 후 **구조하중 재측정**(6.7kN→<1.5kN?)이 판정.

## 큐 (순서)
| ID | 실험 | 변경점 | H-A (측정 판정) | 상태 |
|---|---|---|---|---|
| **E1** | **공간 CoP-진행 + ankle 충돌 해소** | ① `torque_soft_limit_ankle`→ankle_roll만(ankle_pitch 자유) ✅완료 ② 공간 CoP-진행 보상(tracking 동급 스케일, heel→toe) ⏳research grounding | toe 적재 9-20%→↑, CoP heel→toe 진행, error_vel 유지 | E1 설계 중 (warm-start soft_contact) |
| E2 | E1 + 새 PD + 벨트 | knee Kd11/hip24, 벨트 1:2.5 결합 | 충격↓ + 흐물거림↓(ζ0.7) 동시, 구조하중<1.5kN | 큐 (E1 후) |
| E3 | phase-clock 대안 | Siekmann/WTW 시간기반 contact schedule | E1(공간 CoP)가 부족할 때만 — ★우리 emergent+HW하중 목표와 긴장 | 조건부 큐 |
| E4 | 비대칭 critic | toe state·heel/toe GRF·CoP → critic만(privileged) | value가 toe-적재 크레딧 → 간접 개선 | 큐 |
| E5 | heel 바디 + 진짜 CoP | foot_link을 heel/ball로 분리(USD 재변환) | 2-region(foot/toe)이 부족하면 | 조건부 큐 (HW변경) |

## 판정 기준 (공통)
- **통과/진행**: toe 적재↑ + 구조하중<1.5kN + error_vel<0.65 + 낙상<5% + CoT↓
- **공간 CoP vs phase-clock**: HW-하중-측정 목표상 **공간 CoP 우선**(타이밍 prior 없이 *어디에* 실리나 보상). E1 부족 시에만 E3.
- 보고서(외부 toe-roll 리뷰) 검증 결과 반영: ankle 충돌 해소(✅), 스케일 동급, heel/toe 분리는 E5.

관련: [[23_toe_use_methods]] · [[29_natural_gait_reward_hw]] · [[28_reward_actuator_fidelity]] · [[31_humanoid_hw_comparison]] · [[32_actuator_damping]] · [[18_research_roadmap]]
