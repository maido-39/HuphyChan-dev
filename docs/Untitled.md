---
share_link: https://share.note.sx/v9qpf2rt#BYUInTMXloiISndbKPIYS9ENMNlUBx8jE8vt3x9g77E
share_updated: 2026-06-21T12:30:47+09:00
---
Isaac 로딩 시작됨(cpufreq 경고는 무해, 크래시 아님). forefoot 실행은 백그라운드로 진행되며 시작 실패 시 자동 통지됩니다. 논문 리스트를 발표합니다.

## 📚 오늘 읽을 논문 (우선순위 — [docs/26](docs/26_reading_list.md))
**의존성 체인: 방법 → 모터결정 → 신뢰 → 지형 → toe. 1~3만 읽어도 ankle_roll·knee가 "결정가능"이 됩니다.**

| # | 논문 | 왜 지금 |
|---|---|---|
| **1** | [De 2011 — Motor Sizing from Dynamic Task Spec](https://repository.upenn.edu/ese_papers/611/) | **마스터 방법**: RL모션→토크-속도 포락선→모터곡선→감속비 최적화. 우리 사이징 파이프라인의 뼈대 |
| **2** | [Zhu 2025 — Bipedal Jumping w/ Actuator Limits](https://doi.org/10.3390/math13152466) | **속도의존 토크경계** = ankle_roll "진짜 부족 vs 속도제한" 진단 |
| **3** | [Zhang 2025 — Transmission Optimization](https://doi.org/10.3390/biomimetics10030173) | knee **1:3→1:2의 정량 답** + 무릎 예제(peak τ −18.5%) |
| **4** | [Hwangbo 2019 — Learning Agile Motor Skills](https://arxiv.org/abs/1901.08652) | **sim 토크≠실제** 원전 + actuator-net = 모든 사이징의 신뢰 관문 |
| **5** | [Zhu/Hong 2025 — Cycloidal QDD Torque Est.](https://arxiv.org/abs/2410.16591) | **우리 RobStride와 같은 QDD**서 실토크 추정 |
| **6** | [Rudin 2021 — Learn to Walk in Minutes](https://arxiv.org/abs/2109.11978) | **rough 미수렴 직접 처방**(지형 커리큘럼). 우리 스택의 원조 |
| **7** | [Cho 2025 — Toe Joint Stiffness (Nature)](https://doi.org/10.1038/s41598-025-17957-4) | **수동 toe 강성 0.98 Nm/deg** + toe가 다리 총토크↓ |
| **8** | [Fu 2021 — Energy→Emergence of Gaits](https://arxiv.org/abs/2111.01674) | **간접 신호 레시피**(파워 패널티)→자연 gait. 우리 CoP 보상 근거 |

## 🔬 frontier gap (우리 작업이 novel임을 확증)
**①수동 스프링 toe + 심층RL = 결합 논문 없음(우리가 frontier)** · ②ankle_roll은 전두면인데 문헌은 죄다 시상면 · ③RL하중→사이징 루프는 우리가 조립 · ④Isaac-PhysX GRF 충실도 미검증(MuJoCo 교차검증 필요) · ⑤RobStride 마찰 bench-ID 필요 · ⑥수동toe rough 수렴 미검증 · ⑦에너지만으론 인간형 부족(GRF+pain 필요).

## ⚡ 계획 재조정 (지적 반영)
**맞습니다 — toe 사용률(H-A)은 평지로 충분.** 그래서:
- ✅ **stage-5 rough 중단**(reward 11.95→5.30 **발산 중**이었음 — 중단 잘함). fresh·미수렴이라 최대토크용으로도 부적합.
- ✅ **forefoot CoP 실험을 지금 착수**(stage-5 완료를 안 기다림 → **~90분 절약**). config-test 통과(forefoot_cop 보상 정상·transfer 로드 확인).
- ⏭️ rough(최대토크 H-C)는 **나중에 지형 커리큘럼(Rudin)으로 제대로** 재학습. 당장은 stage-4 데이터로 충분.

forefoot ~3hr 후 완료 통지 → 측정 + **H-A 판정**(앞발 GRF비율·ankle/knee τ·CoT + static-curl probe) 자동 진행. 그 사이 위 논문(특히 1·2·3) 읽으시면 측정 결과 해석이 바로 됩니다.