# Reward 근본원인 — gait cycle 미형성 + 발 진동 (feet_air_time 도입)

> 2026-07-06. 사용자 관찰(V2 flat teleop): 발이 진동하고 **제대로 된 gait cycle이 안 만들어짐**. periodic_contact 제거 후(정지·속도추종은 고쳐짐) 나타난 회귀. 리워드 편집 전 근본원인 규명(HOOK).
> 관련: [periodic_contact 제거](2026-07-05_periodic_contact_removal.md) · [gait research Q123](2026-07-02_gait_research_q123.md)

## 1. 증상 + 실측 진단 (v2_flat_demo, vx=1.0 전진블록)
| 지표 | 값 | 해석 |
|---|--|--|
| 접촉 토글률 | L 3.7 / R 3.3 /s (~1.8Hz) | 케이던스 정상, chatter 아님 |
| stance run <5프레임(chatter) | **0개** | 접촉레벨 진동 없음 |
| **양발 동시접지(double support)** | **49%** | ★정상보행 20-30% → **과다 = shuffle** |
| flight phase | 0% | walk(정상) |
| ankle_pitch stance 각속도 | 19 rpm | 낮음(stance 발 진동 아님) |

## 2. 근본원인 — swing 구조 미강제 → high double-support shuffle
- periodic_contact 제거로 **gait 타이밍을 강제하는 항이 사라짐**. g1 command-gated 스택(foot_clearance/swing_height/slip/soft_landing)은 **swing이 일어날 때 형상을 다듬을 뿐, swing 자체를 유발하진 않음**.
- 그 결과 정책이 **에너지 최소 해 = 양발을 오래 붙인 채 조금씩 미는 shuffle**(DS 49%)로 수렴. 명확한 heel-off→swing→heel-strike 사이클이 없음 → 사용자가 본 "gait cycle 미형성 + 발 진동".
- "발 진동"의 정체 = 접촉레벨 chatter(없음)가 아니라 **불명확한 짧은 스텝의 shuffle**이 시각적으로 진동처럼 보임.

## 3. 해법 — feet_air_time (swing 체공 보상, command-gated)
- **`feet_air_time`**(mjlab 내장, 현재 weight 0): 각 발의 current_air_time이 [0.05, 0.5]s **범위 안에 있으면 +보상**. → 발이 **명확히 뜨는 swing**을 유발 → double-support↓, 뚜렷한 gait cycle. 
- **command-gated**(command_threshold 0.5): 명령<0.5(정지·저속)이면 보상 0 → **정지 유지**(periodic_contact 문제 재발 없음).
- **고정 클럭 아님**: 체공"시간"만 보상하고 케이던스/위상은 강제 안 함 → **속도추종 자유**(periodic_contact의 미수렴 문제 없음).
- = Rudin 2021/legged_gym/Unitree 표준. periodic_contact(고정클럭) 대신 air_time(체공보상)이 정지+추종+gait cycle 셋을 동시 만족하는 방식.

## 4. 변경 (변인통제: 이번엔 air_time 단일 변경)
1. **`air_time` weight 0 → +1.0** (command-gated 유지, threshold [0.05,0.5]s).
2. 나머지 유지: foot_swing_height(−0.25)·foot_clearance(−2.0)·foot_slip(−0.1)·soft_landing·track(±2)·contact_force_cap·thermal_effort.
- ★ **action_rate/gain은 이번에 안 건드림** — air_time만 바꿔 gait cycle 효과를 격리 측정. 진동이 air_time으로 안 풀리면 다음 run에서 action_rate_l2↑ 또는 ankle gain 검토(별도 변인).

## 5. 계획 (사용자 지시)
- **flat 10000 iter** 학습(빠른 iterate) → gait cycle·진동·DS비율 재판정.
- 그후 **증류 vs 이어학습** 결정.

## 6. 검증 지표
- ① double-support 49% → **~25-35%**(명확한 swing), ② 시각적 gait cycle 형성, ③ 정지(cmd=0) 유지, ④ track_linear 수렴 유지(air_time이 추종 안 깨는지).
