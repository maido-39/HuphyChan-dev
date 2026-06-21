# 모니터링 로그 — forefoot_cop (실시간 중간검토)

> [!info] run / 가설 / 방법
> **run**: `2026-06-21_12-22-03_forefoot_cop` · warm-start stage-3(model_2499) · Flat-Forefoot-v0(CoP 0.5 + power_cot 0.4).
> **H-A**: 간접 CoP/앞발진행 + power-CoT 보상이 종말기 **앞발 GRF비율↑(toe 적재)** 을 *static-curl 없이* 유도하고 ankle/knee peak τ·CoT↓ 하는가?
> **방법**: `watch_run.sh` 주기형 watcher(~25분)가 스냅샷 → 매번 [[27_training_review_loop]] 체크리스트로 정량/정성 검토 후 **이 노트에 append**. 보수적(DO-NOT-STOP transients).

## 정량 로그 (스냅샷마다 append)
| 시각 | iter | reward | noise_std | error_vel | ep_len | 낙상 | vx | forefoot_cop | 판정 |
|---|---|---|---|---|---|---|---|---|---|
| 12:40 | 124 | 40.5 | 0.29 | 0.47 | 996 | ~1% | 1.24 | 0.0062 | CONTINUE |
| 13:00 | 385 | 42.27 | 0.27 | 0.48 | 1000 | <1% | 1.62 | 0.0075 | CONTINUE |
| 13:25 | 775 | 39.46 | 0.27 | 0.55 | 989 | <1% | 2.00 | 0.0078 | CONTINUE |

## 정성 분석 (유의미 항목)
- **iter 124** — warm-start 초반 0.24 reward가 **40으로 회복** = docs/27 **DO-NOT-STOP #1(warm-start dip)** 정확히 일치. 안 멈춘 게 옳았음. 전 지표 건강(낙상 1%·noise_std 매끈·value_loss 0.012).
- **iter 385** — 안정 수렴, 커리큘럼 vx 1.24→1.62 램핑. reward 42(parent 36 초과 = CoP+power_cot 가산). forefoot_cop 미미하나 초기라 판단 보류.
- **iter 775** — reward 42→**39.5**·error_vel 0.48→**0.55** 소폭 dip = **커리큘럼 vx가 2.0 도달**(명령 최대난이도)한 **DO-NOT-STOP #4(curriculum step)** = 정상. ep_len 989·낙상<1%·noise_std 0.27 안정 → 건강.
  - ★ **H-A 약화 신호**: `forefoot_cop` 0.0062→0.0075→**0.0078 평탄**. vx 2.0 도달·gait 정착 후에도 toe 적재가 안 늘어남(보상의 ~0.02%로 gradient 미약). **다음 스냅샷(~iter 1100)이 결정점** — 그때도 평탄하면: 이 run은 끝까지(건강 baseline+측정) 두되 *다음 실험* refine(forefoot_cop 가중 0.5→↑, 또는 late-single-support gate 완화, 또는 H3 heel-rise 능동발목 항).

관련: [[27_training_review_loop]] · [[25_dayplan_2026-06-21]] · [[23_toe_use_methods]]
