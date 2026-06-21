# 논문 리딩 리스트 v2 (검증판, 2026-06-21)

> [!warning] v1 폐기 → 이 v2가 정본
> v1은 요약이 논문 실제 내용과 안 맞고(읽지 않고 추측) 곁가지·비주류로 빠졌음. **v2는 각 논문을 실제 fetch해 초록·기여를 읽고 작성**(19편 전부 검증 통과, 탈락 0). 대가 랩·정통+최신, 3주제. *목적: 당신이 직접 연구를 이어갈 지식을 얻는 것.*

## ★ 먼저 읽을 순서 (start_here)
1. **Rudin 2021 — Learn to Walk in Minutes** [link](https://arxiv.org/abs/2109.11978) — **우리 Isaac/rsl_rl 스택의 시조.** 학습 패러다임·지형 커리큘럼·하이퍼파라미터 재튜닝(rough 수렴의 처방). 모든 게 이 위에 있으니 여기부터.
2. **Siekmann 2021 — Periodic Reward Composition** [link](https://arxiv.org/abs/2011.01387) — **가장 바로 구현 가능한 보상설계**: phase별 foot-FORCE/foot-VELOCITY 패널티로 gait 지정. 우리 per-foot GRF·접촉 센싱에 직결. clock/phase 보상의 골격.
3. **Kuo & Donelan 2010 — Dynamic Principles of Gait** [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC2816028/) — **왜 효율적 보행이 그렇게 생겼나**의 최고 개념 종합(step전환=비용 2/3·선제 push-off·도립진자·발 rollover·측면균형). open access. TOPIC 3 통합 — 발/toe 기술논문 전에.
4. **Fu 2021 — Minimizing Energy → Emergence of Gaits** [link](https://arxiv.org/abs/2111.01674) — 기계에너지 패널티만으로 자연 gait가 **창발**(모방 없이). 핵심질문의 *긍정* 절반.
5. **Schumacher 2023 — Natural Walking without Demonstrations** [link](https://arxiv.org/abs/2309.02976) — **결정적 정정**: 에너지 최소화 *만으로는* 붕괴/부자연. 속도타깃 + **'pain'/제약** 항이 있어야 자연. (우리 CoP+에너지+pain 사고와 정확히 일치.)

## TOPIC 1 — biped/humanoid 보행 RL 핵심 (방법·reward·curriculum·architecture)
| 논문 | 랩 / 연도 | tier | 한 줄(검증) |
|---|---|---|---|
| [Learn to Walk in Minutes](https://arxiv.org/abs/2109.11978) | **ETH Hutter** + NVIDIA, CoRL'21 | 근본 | 수천 로봇 GPU 병렬로 보행RL을 분 단위로 — Isaac/legged_gym/rsl_rl 스택의 기원. 지형 커리큘럼(승급/강등). |
| [Periodic Reward Composition](https://arxiv.org/abs/2011.01387) | **Oregon State Hurst**/Fern, ICRA'21 | 근본 | 참조 없이 모든 보행을 phase별 foot force/velocity 패널티로 지정. clock-phase 보상의 조상. |
| [Walk These Ways](https://arxiv.org/abs/2212.03238) | **MIT Improbable AI** (Agrawal), CoRL'22 | 근본 | 한 정책을 *해석가능한 gait 파라미터 공간*에 조건화 → 배포 시 gait 선택. teleop 명령변수 메뉴(속도·step주파수/위상·footswing·자세·stance폭). |
| [Versatile Dynamic Robust Bipedal (Cassie)](https://arxiv.org/abs/2401.16889) | **UC Berkeley Sreenath**/Abbeel/Levine, IJRR'24 | 근본 | 단일 정책 **이중(단/장) I/O-history** 구조로 주기(걷기/뛰기)+비주기(점프/정지) 망라, 실 Cassie 400m. 암묵 system-ID. |
| [Real-World Humanoid Locomotion](https://arxiv.org/abs/2303.03381) | **UC Berkeley BAIR** Malik/Sreenath, '23(SciRob'24) | 최신 | proprioceptive history에 **causal transformer** → 실 humanoid 야외 zero-shot, in-context 적응(teacher-student 대안). |
| [Humanoid Locomotion as Next-Token Prediction](https://arxiv.org/abs/2402.19469) | **UC Berkeley BAIR**, '24 | 최신 | 제어를 autoregressive **next-token 예측**으로, ~27h 이종데이터(sim·mocap·YouTube)로 SF서 실 humanoid zero-shot. |
| [Humanoid-Gym](https://arxiv.org/abs/2404.05695) | Tsinghua IIIS / RobotEra, '24 | 최신 | 오픈소스 Isaac-Gym humanoid RL, **sim-to-sim(IsaacGym→MuJoCo) 검증 게이트** 후 zero-shot s2r. |

## TOPIC 2 — 에너지효율 + 인간형 자연 gait
| 논문 | 랩 / 연도 | tier | 한 줄(검증) |
|---|---|---|---|
| [Minimal biped discovers walking & running](https://www.nature.com/articles/nature04113) | **Cornell Ruina**, Nature'06 | 근본 | 최소 biped서 *최소비용* 검색 → 도립진자 걷기·충격 뛰기가 자동 창발(gait 템플릿 없이). |
| [Energetics — Simplest Walking Model](https://doi.org/10.1115/1.1427703) | **Michigan Kuo**, ASME'02 | 근본 | 걷기 비용은 **heel-strike 충돌**이 지배, **heel strike 직전 선제 push-off가 ~4배 저렴**(mid-stance 토크 대비). |
| [Efficient bipedal robots (passive-dynamic)](https://www.science.org/doi/10.1126/science.1107799) | **Cornell/MIT/Delft** (Collins/Ruina/Tedrake/Wisse), Science'05 | 근본 | 수동동역학+소량 동력 로봇이 ASIMO보다 훨씬 적은 제어·에너지로 걷고 **더 자연스러움** = 효율↔자연 공존 증명. |
| [Minimizing Energy → Emergence](https://arxiv.org/abs/2111.01674) | **CMU Pathak** + Berkeley, CoRL'21 | 근본 | 에너지 보상으로 실 4족서 자연 gait 창발(속도 따라 walk→trot→bounce), 접촉스케줄·모방 없이. |
| [Emergence of Locomotion in Rich Environments](https://arxiv.org/abs/1707.02286) | **Google DeepMind**, '17 | 근본 | ★**반례**: 전진보상+다양지형만으론 robust하나 **ungainly(팔 휘젓기)** — 진행+지형만으론 자연/에너지최소 아님. |
| [Natural Walking w/o Demonstrations](https://arxiv.org/abs/2309.02976) | **MPI Tübingen Martius**, '23 | 최신 | 에너지 최소화 *만으론* 불충분 — **effort + 속도타깃 + 'pain'/제약**이라야 근골격 모델서 자연 보행. |
| [AMP: Adversarial Motion Priors](https://arxiv.org/abs/2104.02180) | **UC Berkeley BAIR** (Abbeel/Levine), SIGGRAPH'21 | 최신 | 에너지로 자연성 안 나오면 데이터로: 비라벨 모션 clip의 GAN style-reward를 task 보상에 가산(참조추종 brittle 없이). |

## TOPIC 3 — passive dynamics + 발/toe
| 논문 | 랩 / 연도 | tier | 한 줄(검증) |
|---|---|---|---|
| [Passive Dynamic Walking](https://journals.sagepub.com/doi/10.1177/027836499000900206) | **SFU McGeer**, IJRR'90 | 근본 | **시조**: 무동력·무제어 2D biped가 완만 경사서 중력만으로 안정·인간형 limit cycle = gait 구조/안정성은 *제어 아닌 역학*에 내재. |
| [Passive Walking With Knees](http://ruina.tam.cornell.edu/research/history/mcgeer_1990_passive_walking_knees.pdf) | **SFU McGeer**, ICRA'90 | 근본 | 무릎 추가 수동보행: 무릎 굴곡이 swing-foot 간격을 ~10배 싸게(0.2 vs 3 J/step) 해결. |
| [Advantages of a rolling foot](https://journals.biologists.com/jeb/article/209/20/3953/) | **Michigan Kuo/Collins**, JEB'06 | 근본 | ★발 rollover: 충돌(음)일은 **곡률반경²에 비례 감소**, 단 대사비용은 *중간(인간형 ~0.3 다리길이)* 곡률서 최소. (우리 발/toe 직결.) |
| [Dynamic Principles of Gait](https://pmc.ncbi.nlm.nih.gov/articles/PMC2816028/) | **Michigan Kuo + SFU Donelan**, '10 | 근본 | dynamic walking 종합: 도립진자+수동swing+heel충돌, **step전환=순대사비용 2/3**, 선제 ankle push-off가 경제적 동력. |
| [Unified perspective on ankle push-off](https://journals.biologists.com/jeb/article/219/23/3676/) | **Vanderbilt Zelik** + Adamczyk, JEB'16 | 최신 | push-off "다리swing이냐 COM가속이냐" 논쟁 해소: **국소적으로 후행다리를 가속, 그게 몸의 일부라 COM도 가속 — 둘 다 참.** |

## 우리 연구로의 연결 (왜 읽나)
- **TOPIC 1** = 우리가 *쓰는* 기계: Rudin(스택+rough 커리큘럼)·Siekmann(우리 GRF에 직결되는 보상설계)·Margolis(teleop 명령변수)·Li(이중 history)·Radosavovic(transformer history = teacher-student 대안).
- **TOPIC 2** = 핵심질문(효율=자연?): Fu(긍정)+Heess(반례, 에너지 없으면 ungainly)+Schumacher(정정, 에너지+pain) = **우리 forefoot_cop(원인)+power_cot(에너지)+pain 페널티 방향이 문헌과 정렬됨**을 확인.
- **TOPIC 3** = 우리 frontier(passive toe/발): McGeer(역학이 gait 준다)·**rolling-foot(충돌∝곡률², 우리 발 형상)**·Kuo(push-off 4배싸다·선제)·Zelik(push-off가 후행다리+COM 가속) = toe/push-off 보상의 생체역학 근거. → **정식 리뷰 [[Paperreview/kuo-donelan-dynamic-walking]]**(Kuo 전이-에너지 캐논, 원문검증 수치).

관련: [[25_dayplan_2026-06-21]] · [[27_training_review_loop]] · [[23_toe_use_methods]] · [[24_training_health_analysis]] · [[Paperreview/kuo-donelan-dynamic-walking]]
