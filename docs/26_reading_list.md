# 논문 리딩 리스트 (큐레이션 wu807crtd, 2026-06-21)

> 7개 테마 병렬 리서치 → 우리 미해결 질문(간접 toe보상·ankle_roll/knee 사이징·sim 하중신뢰도·rough 수렴)에 직결되게 우선순위화. 모든 URL 실재 검증.

## ★ 오늘 먼저 읽을 순서 (의존성 체인: 방법→모터결정→신뢰→지형→toe)
**1+2+3만 읽어도 ankle_roll·knee가 "미결→결정가능"이 됩니다.**

| # | 논문 | 왜 지금 | 연결 질문 |
|---|---|---|---|
| 1 | **De 2011 — Motor Sizing for Legged Robots Using Dynamic Task Specification** [link](https://repository.upenn.edu/ese_papers/611/) | 마스터 방법: RL 모션→토크-속도 포락선→모터곡선 겹침→**감속비 최적화**. 나머지가 이 파이프라인에 끼워짐 | 사이징 전체·ankle_roll·knee 1:3vs1:2 |
| 2 | **Zhu 2025 — RL for Bipedal Jumping (Actuator Limits)** [link](https://doi.org/10.3390/math13152466) | **속도의존 토크경계**(평평한 peak cap 아님) = ankle_roll "진짜 부족 vs 속도제한" 진단 도구 | ankle_roll 진단·sim 토크마진 |
| 3 | **Zhang 2025 — Dynamic Motion-Based Optimization of Transmission** [link](https://doi.org/10.3390/biomimetics10030173) | knee 1:3→1:2의 **정량 답**: 고토크/고속 구간 분리→비율 매칭. 무릎 예제+HW검증(peak τ −18.5%·속도 −24.8%) | knee 감속비 (지금 데이터로 바로 가능) |
| 4 | **Hwangbo 2019 — Learning Agile Motor Skills (ANYmal)** [link](https://arxiv.org/abs/1901.08652) | **sim 토크 ≠ 실제 토크** 원전 + actuator-net 해법 = 14관절 하중 신뢰의 개념적 관문 | sim 하중신뢰도(전 사이징의 전제) |
| 5 | **Zhu/Hong 2025 — Cycloidal QDD + Learned Torque Estimation** [link](https://arxiv.org/abs/2410.16591) | **우리 RobStride와 같은 QDD**서 토크센서 없이 실토크 추정 = 4번을 우리 하드웨어로 구체화 | QDD 토크신뢰 → 사이징급 수치 |
| 6 | **Rudin 2021 — Learning to Walk in Minutes (terrain curriculum)** [link](https://arxiv.org/abs/2109.11978) | **rough 미수렴의 직접 처방**: 지형레벨 커리큘럼(승급/강등)+명령 커리큘럼. 우리 Isaac Lab 스택의 원조 | rough 수렴 → 최대토크 측정 unblock |
| 7 | **Cho 2025 — Optimizing Toe Joint Stiffness (Nature Sci.Rep.)** [link](https://doi.org/10.1038/s41598-025-17957-4) | **수동 토션스프링 toe** 모델·강성 최적화→**0.98 Nm/deg** 타깃 + 9링크(toe) vs 7링크: toe가 다리 총토크↓ | 간접 toe(직접보상X)·강성 스펙·발목 offload |
| 8 | **Fu 2021 — Minimizing Energy → Emergence of Gaits (CoRL)** [link](https://arxiv.org/abs/2111.01674) | **간접 신호 레시피**: 기계파워 패널티(Σ\|τ·q̇\|)만으로 자연 gait·속도전이 창발. brittle 직접 toe보상 대체 | 간접 toe(에너지)·효율=자연 베이스 |

## ★ frontier gap (문헌이 못 다루는 = 우리 기여)
1. **진정한 수동 스프링 toe + 심층RL(Isaac/MuJoCo)**: 결합 논문 없음 → **우리가 frontier**. 0-토크 스프링이 PPO하에 간접 CoP/에너지로 적재·에너지반환하게 만드는 건 미해결.
2. **전두면(ankle_roll) 사이징**: 거의 모든 toe/push-off 논문이 **시상면**(hip pitch·knee·ankle pitch). ankle_roll 포화는 **측방 균형·CoP 이동(전두면)** — 직접 사이징한 문헌 없음.
3. **RL측정 하중→기어/모터 선택 루프**: 선택논문은 *생체역학/해석적* 타깃 가정. "RL 포락선→토크-속도 점군→비율+모터+열/마찰 마진" 통합은 **우리가 조립**.
4. **Isaac-PhysX의 접촉력/CoP/GRF 충실도**: Acosta는 Drake/MuJoCo/Bullet만 검증(Cassie 착지 포함), **Isaac/PhysX는 미검증** → MuJoCo MJX로 교차검증 필요.
5. **RobStride 정적/쿨롱 마찰·기어손실**: Hu 2025은 실마찰이 ideal-sim 토크를 낙관적 하한으로 만듦 입증하나 **우리 액추에이터 수치는 직접 bench-ID** 필요.
6. **수동 toe 14-DOF biped의 rough 수렴(9.7GB·sm_120)**: Rudin 커리큘럼은 원리상 약이나, 펄럭이는 수동 toe + 제한 compute서 수렴할지 **미검증**.
7. **에너지만으론 인간형 부족**(Schumacher 2025: GRF·관절한계 'pain' 패널티 필요): 수동 toe형 우리 형상의 effort+GRF+pain 가중 균형은 **미해결**.

## 테마별 전체 (참고)
- **사이징**: De2011 · Zhang2025 · Shin2023 [구속RL](https://arxiv.org/abs/2312.17507) · Zhu2025
- **수동 toe**: Cho2025 · [Duke Humanoid 2024](https://arxiv.org/abs/2409.19795)(에너지보상 CoT −31% 실HW) · [Huang2012 분절발](https://doi.org/10.1007/s10409-012-0079-6)
- **모터/기어**: [Wensing2017 MIT Cheetah proprioceptive](https://doi.org/10.1109/TRO.2016.2640183) · [Urs2022 QDD 모터선택](https://arxiv.org/abs/2202.12365) · [Singh2025 단단 유성기어](https://arxiv.org/abs/2506.16356) · [Sunbeam2025 인간수준 액추에이션](https://arxiv.org/abs/2511.06796)
- **효율=자연**: Fu2021 · [Schumacher2025 iScience](https://doi.org/10.1016/j.isci.2025.112243)(에너지+GRF+pain) · [Radosavovic2024 Sci.Robotics](https://doi.org/10.1126/scirobotics.adi9579) · [Srinivasan-Ruina2006 Nature](https://doi.org/10.1038/nature04113)
- **sim2real 하중**: Zhu/Hong2025 · Hwangbo2019 · [Acosta2022 충돌검증](https://arxiv.org/abs/2110.00541) · [Hu2025 정적마찰](https://arxiv.org/abs/2503.01255)
- **AMP**: [Peng2021 AMP](https://arxiv.org/abs/2104.02180) · [Escontrela2022 AMP=복잡보상 대체](https://arxiv.org/abs/2203.15103) · [HumanMimic2023](https://arxiv.org/abs/2309.14225) · [전신humanoid 2024](https://arxiv.org/abs/2402.18294)
- **SOTA biped**: Duke · Radosavovic · Rudin2021 · [Siekmann2021 주기보상](https://arxiv.org/abs/2011.01387) · (+[Li2024 IJRR](https://arxiv.org/abs/2401.16889))

관련: [[25_dayplan_2026-06-21]] · [[21_motor_power_weight]] · [[23_toe_use_methods]] · [[24_training_health_analysis]] · [[18_research_roadmap]]
