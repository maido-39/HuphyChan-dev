# 중간 학습검토 루프 + 보수적 중단 기준 (연구 we12yjosz)

> [!warning] 핵심 원칙 — 보수적
> **느리지만 건강한 run을 죽이는 게 compute 낭비보다 훨씬 큰 리스크.** RL은 plateau서 coasting하다 도약하고, 일시적으로 나빠졌다 크게 좋아진다. **단일/단기 신호로 절대 중단 금지** — *지속(수십~수백 iter) + 여러 지표 동반(corroborated)* 일 때만. 시간척도(Rudin): 평지 보행 <4분, rough ~20분 = **수백~수천 iter** → "iter 50에 수렴 안 됨"은 무의미.

## 검토 체크리스트 (스냅샷마다 — 단일점 아닌 이동평균 SLOPE + 커리큘럼 레벨 대조)
| 지표 | 건강 | 벗어나면 |
|---|---|---|
| **mean_reward** | 노이즈낀 **concave 상승→고원**. warm-start iter0-3 dip 후 회복 정상 | 처음부터 flat→**refine**(보상스케일/지배 패널티/명령난이도). 수백 iter 단조 하락/NaN→**terminal** |
| **episode_length** | reward와 동반 상승→time-out cap(~1000) 고원 | cap 한참 아래 고원→warning. 낙상과 함께 지속 하락→terminal |
| **noise_std + entropy** | **느리고 매끈한 감소**(reward 추종), 바닥 ~0.2-0.4. **초반/신과제 일시 상승=정상**(entropy bonus) | **reward 낮은데 std/entropy 함께 0으로 붕괴**→terminal(조기수렴, 탐색 사망) |
| **value_loss + explained_var** | **hump**(초반↑ 후 안정), exp_var→1. **spike는 보통 GOOD**(새 고가치 발견·커리큘럼 level-up) | 단조 폭발 / exp_var≤0 + reward flat 지속→terminal(critic 학습실패) |
| **surrogate** | 0 근처 진동(약간 음수), <~1. **단독 kill 신호 아님**(가장 약함) | >1 지속→warning. KL폭발+reward붕괴 동반시만 확인용 |
| **KL + LR(rsl_rl 적응)** | KL~0.01(<0.02), **LR 튕김=컨트롤러 작동**(KL>0.02→LR/1.5). 단일 spike 정상 | **지속 rail-pin**(LR 1e-5+KL≫0.02 / LR 1e-2+KL~0 reward flat)→terminal |
| **낙상(base_contact) vs 생존(time_out)** | 낙상↓·생존↑. **커리큘럼 level-up 직후 낙상 일시↑ 정상** | 커리큘럼 이유 없이 **낙상 ~1.0로 재상승**+reward/length 붕괴→terminal(catastrophic forgetting) |
| **error_vel_xy/yaw** | 작은 바닥으로 감소(0 아님). 커리큘럼 step서 ↑후 재하강 정상 | 높은 고원→refine. **reward↑인데 error 정체/악화=REWARD HACKING**→보상함수 고치고 재시작 |

## DO-NOT-STOP (예상된 일시현상, 수십 iter 내 회복 — 절대 중단 금지)
1. **warm-start iter0-3 dip**(reward/length↓·낙상↑·vloss spike·KL spike→LR컷) — fresh optimizer가 미지상태 만남, 불가피.
2. **noise_std/entropy 일시 상승/bump**(초반·신과제) = 탐색, 발산 아님.
3. **value-loss spike 후 재수렴** = critic가 새 고가치 만남(보통 커리큘럼 level-up) = GOOD.
4. **낙상↑/length↓/error_vel↑이 커리큘럼 level-up과 동시** = 더 어려운 과제의 당연한 비용, 재수렴.
5. **LR 튕김 + 단일 KL spike** = 적응 컨트롤러 설계대로 작동, self-heal.
6. **surrogate 0 근처 진동/약간 음수** = 올바른 PPO 거동.
7. **긴 reward plateau** = 종종 도약 직전. 인내로 통과.

## JUSTIFIED-STOP (지속+동반 → 중단/재시작/수정)
- **A. NaN/inf**(loss나 action) → 즉시 중단.
- **B. 비가역 붕괴**: reward 바닥 flat **AND** noise_std/entropy 함께 ~0 붕괴(동시발생이 실패; 하나만은 아님).
- **C. LR 1e-5 바닥 고착 + KL≫0.02 + reward/value 발산**(trust region 영구 위반). (반대: LR 1e-2 + KL~0 + reward flat 지속.)
- **D. value loss 단조 발산**(exp_var≤0 + reward flat 지속) = critic 학습 안 됨.
- **E. warm-start dip서 영영 못 나옴**: 관대한 인내창 후에도 부모 baseline 근처로 회복·상승 기미 없음(커리큘럼 이유 없이).
- **F. catastrophic forgetting**: 낙상 ~1.0로 재상승 + reward/length 붕괴 + 커리큘럼 이유 없음.
- **G. REWARD HACKING 확정**: reward↑인데 error_vel 정체/악화 + 영상서 gait 병적/게이밍 → **보상함수 수정 후 재시작**(resume 금지, 더 학습하면 악용 고착). *reward↑가 중단을 정당화하는 유일 케이스.*

## 결정 로직 (한 스냅샷 → 이력으로 추세 복원 + 커리큘럼 오버레이)
- **CONTINUE(기본·최우선)**: reward slope↑/고원, length cap 근처, std/entropy 매끈 감소, exp_var→1, KL~0.01 LR튕김, 낙상↓, error_vel↓. **애매하면 CONTINUE 후 재스냅샷**. 형제 seed 있으면 교차확인(느린학습 vs 죽음).
- **REFINE-next(살아있으나 평범; 끝까지 돌리고 다음 config 변경)**: 지속 WARNING(처음부터 flat·std너무빠른감소·KL 만성>0.02 톱니·특정 버킷서 낙상/error 정체·부분해). "이 config의 한계"지 "지금 고장"이 아님.
- **STOP-now(드묾)**: JUSTIFIED-STOP A-G가 **지속+동반**으로 충족될 때만.
- **타이브레이커**: off 지표 1개→CONTINUE+관찰. 커리큘럼/warm-start로 설명 안 되는 **2개+ 동반 지속**→REFINE 격상. terminal 시그니처 일치→STOP.

## 출처
- [rsl_rl PPO 소스(KL적응 LR·clip)](https://github.com/leggedrobotics/rsl_rl/blob/main/rsl_rl/algorithms/ppo.py) · [Rudin 2021(평지<4분·rough~20분)](https://arxiv.org/abs/2109.11978) · [WSRL warm-start dip ~50k 회복](https://arxiv.org/html/2412.07762v3) · [PPO 37 details(KL<0.02·exp_var)](https://iclr-blog-track.github.io/2022/03/25/ppo-implementation-details/)

관련: [[25_dayplan_2026-06-21]] · [[24_training_health_analysis]] · [[26_reading_list]]
