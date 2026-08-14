---
share_link: https://share.note.sx/i1a1z7k5#RM+09sJGOD0sN06l5j7fxC2NhNsou31qtqwkCoQl1U0
share_updated: 2026-07-05T02:01:54+09:00
---
# PACE (leggedrobotics/pace-sim2real) — 정리 + 우리 활용

> 2026-07-04. peer(광운대/robros)가 "lucky-ID"로 언급한 도구. https://github.com/leggedrobotics/pace-sim2real. WebFetch(repo·arXiv 2509.06342).

## 무엇인가
- **PACE = Precise Adaptation through Continuous Evolution.** ★**ETH RSL(Marco Hutter — ANYmal·legged-RL 최정상 그룹)** 제작, **Apache-2.0 오픈소스**.
- 논문: **"Towards Bridging the Gap: Systematic Sim-to-Real Transfer for Diverse Legged Robots"** (Bjelonic·Tischhauser·Hutter, **IJRR** — 로봇 최고 저널, arXiv:2509.06342, 2025).
- 해결 문제 = ★**정확히 우리 문제**: sim의 액추에이터/관절 dynamics를 **실 데이터로 시스템 식별**해 sim2real gap을 닫음. (우리 armature/damping/frictionloss는 kbot 복사값·비ID / peer "RS04가 명령 PD 안 따름".)

## 어떻게 동작
- ★ **bottom-up 파라미터 식별 3단계**(= peer의 크레인 워크플로의 논문판):
  1. **액추에이터**(벤치 excitation)
  2. **전신 in-air 궤적**(크레인 공중)
  3. **on-ground 보행**
- **PMSM 물리 에너지 모델**(RobStride = PMSM이라 적합) + **최소 파라미터셋**으로 gap 포착
- **CMA-ES**(진화최적화)로 sim↔real 오차 최소화하는 **물리적으로 의미있는 파라미터** 피팅(actuator-net 아님 = 해석 가능)
- ★ 결과: ANYmal **CoT 32%↓(1.27)**, **domain randomization 없이 전이**(모델이 정확하면 DR 불필요 = 덜 보수적·덜 흔들림). 3개 주 플랫폼 + 10개 추가 로봇 검증.

## 어떻게 쓰나
```
Isaac Lab 5.0+ 설치 → PACE clone → pip install -e source/pace_sim2real
데이터 수집:  python scripts/pace/data_collection.py   (excitation)
파라미터 피팅: python scripts/pace/fit.py               (CMA-ES)
출력: logs/pace/[robot]/ 에 피팅된 액추에이터/관절 파라미터
```
- 입력: 실 로봇 센서 데이터(excitation 궤적) + 로봇 config. 데모: **ANYmal D**.

## ★ 우리에게 어떻게 도움
1. **핵심 sim2real 리스크 직접 해소**: "RS04 PD 미추종"·비ID 액추에이터 → **실 모터의 armature/damping/friction/PMSM 모델을 벤치·크레인 데이터로 ID** → mjlab에 반영 → 정책이 실 역학으로 학습 → **zero-shot 향상**(Duke/Berkeley 성공요인과 동일 논리).
2. **crane bring-up의 disciplined 버전**: 우리 2개월 계획 W2~W8(벤치→공중→접지)이 **PACE의 3단계와 정확히 같음** → "말랑게인 크레인 매칭"을 임시방편 아닌 **논문 파이프라인**으로.
3. **DR 없이 전이** → 무거운 DR로 인한 보수적·흔들림 gait 회피(51.5kg서 특히 중요).
4. **peer(robros)가 실사용** → 우리 급 팀의 실증.

## ★ 정직한 CAVEAT — Isaac Lab 의존 (우리는 mjlab)
- PACE는 **Isaac Lab 전용**. 우리 파이프라인은 **mjlab(MuJoCo-Warp)**. 직접 실행엔 gap.
- 단 **극복 가능**:
  - **(a) 파라미터는 물리량**(모터관성·댐핑·마찰·PMSM) → **엔진 무관, mjlab에 그대로 이식** 가능(같은 실물 로봇).
  - **(b) 방법이 엔진 독립**: excitation→CMA-ES fit은 개념적으로 mjlab에도 재구현 가능.
  - **(c) 우리 계보**: 원래 IsaacLab→sim2sim→MuJoCo였음 → Isaac이 낯설지 않음. **PACE ID는 Isaac서 돌리고 피팅 파라미터를 mjlab으로 이식**하는 게 현실적.
- 실행 선택지: ① Isaac서 PACE로 ID → 물리파라미터 mjlab 이식(권장, 최소노력) / ② PACE의 CMA-ES fit 로직만 mjlab에 포팅(더 통합적, 더 일) / ③ 논문 방법(bottom-up 3단계)을 우리 chirp_gain_test 확장으로 자체구현.

## 2개월 계획에의 슬롯
- **W2~4 벤치**(RS02→실모터): PACE data_collection로 excitation → CMA-ES fit → 실 액추에이터 파라미터
- **W5~8 크레인**: in-air·on-ground 단계로 파라미터 정밀화 → mjlab 갱신 → 재학습(30분) → zero-shot 개선
- 이게 "RS04 PD 미추종"·"CAD inertia에 모터·나사 미반영" 문제를 정면 해결.

## 참고
repo(Apache-2.0)·arXiv:2509.06342(IJRR)·pace.filipbjelonic.com. 관련: [2개월 계획](2026-07-04_2month_plan.md)·[sim2real 방법론](2026-07-04_2rsu_knee_sim2real_method.md).
