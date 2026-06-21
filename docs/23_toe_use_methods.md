# 23 · Toe를 쓰게 하는 법 — 산업계 + 최신 논문 + Trial-and-Error 계획 (wljkv3uu8)

> [!question] 질문: Optimus/Figure 등 대기업은 toe를 어떻게 쓰나? 최신 논문은? → 가설 세워 실제 적용(trial-and-error).

## 한 줄 결론
**우리 하드웨어(수동 toe + 능동 발목)는 Optimus/Asimov와 정확히 일치 = 산업 표준**(toe 모터 추가 X). **수동 toe에 직접 보상한 RL 논문은 없음 = 우리가 학계 최전선(발표 가능).** toe는 **간접 적재** — 종말기에 CoP/접촉을 앞발로 굴려야 함. → **H1(종말-단일지지 forefoot-load 보상) + H6(power-CoT)** 먼저 시도.

## ① 산업계 (Optimus/Figure/Atlas/Unitree/Figure/Apollo/1X/Sanctuary)
- **전원 toe 모터 없음** — 전 업계가 능동 toe를 mass/복잡도/제어부담 대비 toe-off 이득이 작다고 **거부**. **우리의 수동-toe·능동-발목 설계 = 지배적·검증된 산업 선택. toe 모터 추가하지 말 것.**
- **Tesla Optimus Gen2 / Asimov(Menlo)** = 우리와 거의 동일(2-DOF 능동 발목 + 수동 sprung toe, 제어 밖).
- **toe는 간접 적재**: ① Atlas(강체발)는 whole-body 제어가 발 pitch를 **미구속**하고 종말기에 **CoP를 앞발로 이동** → toe-off 창발. 우리 forefoot-rollover 보상이 그 RL 대응 = **정답 메커니즘**. ② **rocker/forefoot 기하**가 굴림을 가능케 함 — **우리 robot.xml에 별도 forefoot(L/R_toe_link + 콜리전 geom)이 이미 있음(검증됨) = 기하는 장애 아님.** ③ k=60(1.05 N·m/deg) = 인간 최적(~56).

## ② 최신 논문 (state-of-the-art)
- **수동 toe 스프링을 직접 보상한 휴머노이드 RL 논문 = 없음** → 우리가 frontier.
- **heel-to-toe 굴림은 거의 전부 인간 모션 모방으로** 달성: [Adam (AMP, arXiv 2402.18294)](https://arxiv.org/html/2402.18294v4) 유일 시연(단 toe DOF 없음, 굴림은 발목 운동학·정성적 사진뿐), [GMP (CVAE prior, 2503.09015)](https://arxiv.org/html/2503.09015v1) 안정적 후속.
- **수동 발 스프링 적재는 사족에서 에너지/CoT 보상으로 해결**(우리 stage-3 확증): [Compliant-feet quadruped (2605.14411)](https://arxiv.org/html/2605.14411) — "스프링 적재" 항 없이 토크/에너지 페널티만으로 적재, **중간 강성 최적**. 수동요소는 **에너지항으로만 간접 적재**.
- **우리의 빈 primitive(기회)**: 에너지/CoT항 + **CoP를 종말기에 앞발로 강제하는 공간 제약** → 부하가 무릎이 아니라 toe로. 도구: [CoP/ZMP-progression 보상 (2509.09106)](https://arxiv.org/pdf/2509.09106), [Siekmann 주기클록 (2011.01387)](https://arxiv.org/abs/2011.01387)을 **sub-foot(heel 초기·forefoot 종말)로 확장**.

## ③ Trial-and-Error 계획 (랭크) — 빠른 실험 루프
| # | 가설 | 방법(핵심) | 검증 메트릭 |
|---|---|---|---|
| **H1** ★먼저 | 종말-단일지지 **forefoot-load** 보상 | `toe_load_stance` 업그레이드: \|τ_toe\| 보상, **(접지)∧(반대발 swing)∧(종말)∧(전진)** 게이트(static curl 방지). w+0.3-0.5, τ_ref 27 | toe-load% 6-26%→40-70%, **GRF 2차피크**, ankle τ↓, CoT 유지, 추종 −<5% |
| **H6** ★H1과 함께 | vel-norm **power-CoT**(효율 곱셈) | `power_cot`(존재): exp(−scale·Σ\|τω\|/(σ\|v\|+ε)), 정지 비최적. w+0.5-1.0, scale 0.003 | CoT↓, toe-load는 H1과 결합시만↑ |
| H3 | 발 pitch/**heel-rise** shaping(운동학 원인) | 종말-단일지지서 stance발 toe-down pitch 보상(H1 static-curl 방지) | heel-rise·toe-load 동반↑ |
| H2 | Siekmann 클록 + **sub-foot CoP** 스케줄 | obs에 위상클록 추가 + heel→toe CoP 이동 보상 | CoP_x 단조, GRF 2차피크 |
| H4 | 인간 heel-to-toe **레퍼런스 모방**(발목 미추종) | 인간 보행 retarget, hip/knee 모방·**발목 약하게** → toe 자가적재 | 모방오차, GRF 2차피크 |
| H5 | **AMP** 인간 스타일(최후) | discriminator 스타일 보상 + H1 anchor | discriminator, toe-load% |

## ★ 정정 — "직접 toe 보상은 anti-pattern" (후속 연구 whirkj8ws, 사용자 지적이 맞음)
> [!warning] H1(직접 \|τ_toe\| 보상)은 폐기. 간접 CoP로 교체.
> **H1은 reward hacking 안티패턴**: 수동 toe라 \|τ_toe\|=k·변형 → **변형(상관량)을 보상 = 의도(굴림)와 인과 분리**. 정책이 **정적 toe-curl/등척성**으로 변형만 만들어 보상 챙김(걷지 않고). **우리 toe는 과감쇠(ζ≈2.9)라 *유지된 curl*이 싸서 더 위험.** **게이트로도 안 막힘**(Skalse 2022: 보상 좁혀도 unhackable 아님). 학계가 **수동 스프링을 보상에서 제외**(Cassie)하는 이유 = 인과방향: *결과(push-off/roll)를 보상하면 적재는 부산물로 따라옴*.

**개정 계획 (실제 실행)**:
1. ★ **CoP/앞발 진행 보상(간접, 리드)** `forefoot_cop` — 종말-단일지지서 **앞발 GRF 비율**(toe_link/(toe+foot)) 보상. *발이 어디에 하중을 싣나(굴림)*를 보상 = toe 적재의 **합법적 원인**, toe로 게임 불가. 우리가 이미 로깅하는 GRF로 계산.
2. **에너지/CoT**(`power_cot`, 종속) — 자유 스프링을 쓰도록 압력. 단독 금지(셔플/freeze 퇴행).
3. (선택) ankle-pitch heel-rise 참조(능동 발목이라 합법).
4. toe-load 항을 **굳이 쓰면 PBRS(potential-based) 형태로만**(Ng-Harada-Russell: 최적정책 불변, 해킹최적 추가 불가) — 원시 \|τ_toe\| 금지.
5. AMP는 나중.
> **검증 필수**: toe 적재 에피소드가 *실제 heel→toe CoP 이동 + 전진 CoM 변위*와 일치하는지 적대적 probe(정적 curl 아님). → `Flat-Forefoot-v0`를 **forefoot_cop+power_cot로 교체 적용**(H1 폐기), 학습은 GPU 프리 시.

## 출처
- [산업계 active vs passive toe 논쟁](https://www.humanoidsdaily.com/news/stepping-forward-the-debate-over-active-vs-passive-toes-in-humanoid-robotics) · [Menlo/Asimov 다리 설계(우리 51.8kg급 일치)](https://menlo.ai/blog/humanoid-legs-100-days) · [Atlas CoP-forward toe-off (1709.03660)](https://arxiv.org/pdf/1709.03660)
- [Adam AMP heel-to-toe (2402.18294)](https://arxiv.org/html/2402.18294v4) · [GMP (2503.09015)](https://arxiv.org/html/2503.09015v1) · [Compliant-feet quadruped (2605.14411)](https://arxiv.org/html/2605.14411) · [CoP/ZMP RL (2509.09106)](https://arxiv.org/pdf/2509.09106) · [Siekmann (2011.01387)](https://arxiv.org/abs/2011.01387)

> [!note] 이론 근거 (CoP/push-off 방향이 *왜* 맞나)
> [[Paperreview/kuo-donelan-dynamic-walking]] — Kuo/Donelan/Ruina 캐논: 보행 에너지는 **step-to-step 전이(선제 push-off/collision)**가 지배(순대사 ~2/3), 관절각이 아니라 **COM 전이 에너지**를 보상해야 함. 우리 forefoot CoP·CoT 방향을 직접 뒷받침하고 *평탄 COM·관절각 템플릿 보상 금지*까지 명시.

관련: [[17_toe_usage_vibration]] · [[22_energy_toe_reward]] · [[19_toe_ablation]] · [[26_reading_list]] · [[Paperreview/kuo-donelan-dynamic-walking]] · [[Paperreview/siekmann-periodic-reward]] · [[18_research_roadmap]]
