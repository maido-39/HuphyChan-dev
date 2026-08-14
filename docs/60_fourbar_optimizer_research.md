# 60 · 4절 링크 최적화 — 제약분리 전역탐색 리서치 & 구현 (DE + Deb)

> 2026-07-09. 사용자 요구: "언제나 Global 최적점 추종 + 모든 제약 만족 + **HARD 제약과 최적화 대상(목적) 분리**". 웹 리서치(서브에이전트) + Python 프로토타입 6-시나리오 검증 후 [tools/fourbar_designer.html](../tools/fourbar_designer.html)에 구현. 기능 명세: [[59_fourbar_designer_tool]].

## 1. 문제 재정식화 — HARD 제약 vs 목적
종전(soft 합성점수)의 병리: 페널티 가중치 트레이드로 **제약 위반 해가 "최고점"으로 선택**됨(실측: 멀티스타트 최적해가 전달각 149.8°>145 위반, S6 비교에서 f=230이지만 infeasible). 재정식화:

| 구분 | 항목 | 정규화 위반량 |
|---|---|---|
| HARD | 입력 전회전(crank-rocker) | \max(0,0.99-frac)×20 |
| HARD | Grashof 마진 ≥ 6mm | \max(0,6-m_G)/6 |
| HARD | 입력=최단 링크 | \max(0,(r_2-\min L)/\min L) (등급형 — 이진이면 DE가 정체, S4에서 실측) |
| HARD | 스윙 ≥ 요구 | \max(0,req-s)/req |
| HARD | 전달각 ∈ [40,145]° (운용창) | 하/상 별도 정규화 |
| HARD | 사용범위 커버(범위제한 ON) | 미커버각/범위각 |
| HARD | 수요 bin 전부 도달 | 미도달/전체 |
| HARD | ω 마진 ≥ 0 (bin별) | \max(0,-w_min)/5 |
| **목적** | **최악 τ마진 최대화** | f=\min_b(\min(T(ω_b/g)/g, 3T_pk)-τ_b) |

## 2. 리서치 결론 (원문 발췌 → docs 링크)
- **Deb 규칙** (Deb 2000, CMAME 186:311, [link](https://www.sciencedirect.com/science/article/abs/pii/S0045782599003898)): 3규칙 사전식 — feasible>infeasible / infeasible끼리 위반합 최소 / feasible끼리 목적. *"elimination of the requirement for appropriate penalty factor selection"* — 파라미터 프리, 요구사항 그대로.
- **약점** (Mezura-Montes & Coello survey, [link](https://hal.science/hal-04799805v1/document)): *"problems with a reduced and disconnected feasible region… very likely to get trapped prematurely"* → 대응 = 큰 개체군+재시작. 업그레이드 경로 = ε-constrained(Takahama & Sakai εDE, CEC2006 우승).
- **DE+Deb = 정석 조합** (Lampinen, ["Simple Feasibility Rules and DE"](https://link.springer.com/chapter/10.1007/978-3-540-24694-7_73)) — DE 선택연산 한 줄 교체.
- **4절 링크 합성 선례**: Cabrera 2002(GA+페널티, 분야 baseline), Sleesongsom & Bureerat 2018(*"If the parameter is too small, the resulting optimum solution may be infeasible…"* — 페널티 명시적 기각, [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC6236668/)), Acharyya & Mandal(GA/PSO/DE 비교 — **DE 최고**, [link](https://www.sciencedirect.com/science/article/abs/pii/S0094114X09000470)).
- **다봉엔 DE/rand/1/bin** (>best/1: *"DE/rand/1 has global and random characteristics"*), NP=10D, F∈[0.5,1] 디더, CR=0.9.
- **이산 2변수(기수 4)**: 유전자 인코딩 대신 **조합 열거**(Lampinen & Zelinka MIDC-DE 함의) — 계단항이 landscape에서 제거됨.
- **정지/anytime**: 개선정체 G세대 + 최대세대(Zielinski & Laur); best-feasible-**ever** 아카이브는 선택압에 안 밀리게 개체군 밖 보관.
- 대안 기각: dual annealing/DIRECT(비선형 제약 네이티브 미지원), CMA-ES(D=4에 과함).

## 3. 구현 (fourbar_designer.html)
DE/rand/1/bin: NP=40(UI 조정), F 세대별 디더 [0.5,1], CR=0.9, LHS 초기화, **개체0=현재 설계**, (kSign±1)×(조립 A/B) **4조합 순차 DE**, 정체 30세대/최대 150세대 종료, 종료 후 좌표 패턴 정제(Deb 수락) → **전역 best-feasible-ever 적용**. 시드 고정(mulberry32)=실행마다 동일 결과. 애니메이션: 프레임 12ms 예산으로 평가 단위 state machine, 뷰어는 항상 best-ever 표시. **feasible이 없으면 최소위반 해 + 위반 항목 목록 보고**(예: "✗ ω마진 1.13, 전달각<40 0.37…"). 우측에 **HARD 체크패널**(9항목 ✓/✗ + 실측값 + 목적값) 상시 표시 — 수동 설계 중에도 어떤 제약이 깨졌는지 즉시 보임.

sweep은 전진차분(샘플당 solve 1회)으로 재작성 — 평가 ~3× 가속(DE 예산 확보).

## 4. 검증 (Python 프로토타입, scratchpad `de_deb.py`)
6 시나리오(스크린샷 재현/사용범위 ON/peak 통계/전자유 req120/타이트박스/공칭-완화). 전 시나리오에서:
- **위반량**: DE+Deb가 멀티스타트(soft) 대비 전부 우세 (S1 1.80 vs 2.61 · S3 4.0 vs 7.08).
- **S6(feasible 존재)**: DE만 완전 feasible(f=223.8); soft는 f=230처럼 보이나 **위반 0.255 상태** = 페널티 트레이드 병리 재현.
- **결정성**: 동일 시드 2회 실행 결과 완전 일치(전 시나리오).
- **등급형 최단링크**: 이진(S4 sumV=1.0 정체) → 등급형(0.909, 유의미한 최소위반 방향) 개선 확인.
- ★ S1~S3의 **ω 위반은 물리적 진실**: worst 무릎 ω수요(p95 최대 22 rad/s)가 RS04 무부하(19.9)를 초과 — 토크증폭(|g|<1) 레버로는 ω 더 감소 → **RS04 직결·감속 계열로는 worst 시나리오 hard-feasible 불가**([[reference-robstride-motor-specs]] sim-to-real 갭과 일치). 툴이 이제 이걸 숨기지 않고 "위반: ω마진"으로 보고.

## 5. 남은 개선 경로
- feasible 영역이 극소/단절인 케이스에서 Deb 정체 시: ε-constrained(ε→0 스케줄)로 교체. → **§6에서 구현됨(2026-07-09)**
- 목적 다중화(τ마진 + 컴팩트성 등) 필요 시: NSGA-II 계열.

## 6. v2 (2026-07-09 저녁): ε-DE + 연속 라운드 + 후보 아카이브 & 사용자 박스 불능 증명
사용자 지적("최적해 무조건 있을 텐데 계속 탐색하게 해라, 후보군도 여러 개 보여라")에 대응:
- **ε-constrained 선택**(Takahama & Sakai): 위반 ≤ ε(세대)이면 feasible 동급으로 목적 비교, $\varepsilon(g)=\varepsilon_0(1-g/T_c)^5$, $\varepsilon_0$=초기 개체군 위반 중앙값, $T_c$=0.6·GENMAX — Deb의 얇은/단절 feasible 영역 정체(§2 약점) 보완. 실측: 동일 예산에서 min-violation 1.819→1.767 개선.
- **연속 라운드**: 4조합+정제 완료 후 시드를 결정적으로 바꿔 재시작(아카이브 엘리트 승계), 정지 버튼 또는 5라운드 무개선 수렴/50라운드 백스톱까지 계속.
- **후보 아카이브**: 전 평가에서 다양성 유지(같은 조합+정규화 L∞<0.06이면 동일 분지로 병합) 상위 8개 보존, UI 패널에 ✓feasible/✗Σv로 나열, 클릭 적용.

**★불능 증명(사용자 박스: r1=257.1🔒, r2·r4∈[40,80], worst+p99, syncK)**: Grashof 마진 6 ⇒ **r2≤r4−6** & r3∈[r1+r2−r4+6, r1−r2+r4−6] (유일 창) — 이 전체 유효집합을 **11,844점 격자 전수 스캔 → feasible 0개**(최소위반도 ω 1.58 잔존). 기구학적 원인: 수요 최심굴곡 bin(−112~−127°, ω 17~22 rad/s)이 **로커 스윙 반전점 부근**에 위치 — 모든 crank-rocker는 스윙 끝에서 g→0이므로 속도가 사라지는 지점에 최대 속도를 요구하는 꼴. 사용범위를 [−100,−20]으로 좁혀도 ω 0.50 위반 잔존(스윙 여유 부족). 알고리즘이 아니라 **아키텍처-데이터 조합의 물리적 불능**.

## 7. 완화 민감도(2026-07-09 저녁) — 주범 확정 & 설계 Revise
단일 축 스윕(A~E): 모터속도 34 rad/s↑·수요 ω 절반·r4≤150·μ하한 15°·각각 단독으로는 **전부 불능**. 원인 = 독립 차단기 2개: ①**μ창 기하**(r1 지배 긴 커플러에서 $d\mu\approx-d\theta_4$ ⇒ 110° 스윙이 μ창 105°[40,145] 초과; r4를 키우면 μ는 풀리나 스윙이 66°로 붕괴) ②**심굴곡 ω**(스윙 끝 g→0). 2축 조합(F: 수요×μ, G: 사용범위×수요)도 **전회전 유지 시 전부 불능**.

**★해법 = 전회전(crank-rocker) 요구 폐기**: 제한-아크(왕복) 구동은 Grashof가 불필요 → **r2>r4 증속 기하** 허용 + 수요 스팬이 아크 내부에 위치 → **현재 데이터·현재 박스 그대로 FEASIBLE**:
- μ40 유지: f=−83 N·m @ r2=77.5/r3=212.5/r4=40 (아크 사용)
- μ30 허용: f=−62 @ r2=70/r3=229.5/r4=47.5 · +수요10%완화 시 f=−55
잔여 음(−)의 τ마진은 hard 제약이 아니라 목적값 — 심굴곡 bin의 τ120@ω20 동시요구(클리핑된 검열 수요) 때문이며, velocity_limit 19.9 재학습 후 재평가하면 개선 예상. **모터는 어차피 왕복 구동이므로 전회전 포기는 실기 손실이 없음**(입력측 안전은 아크 내 g-부호 일관성+μ창으로 보장).

**툴 반영(v3)**: "전회전 요구" 토글 추가 — OFF 시 rot/Grashof/최단링크 제약을 제거하고 스윕을 연속·g-부호 일관 서브아크로 분해해 최적 아크를 선택(체크패널에 사용 아크° 표시), DE/후보 아카이브가 그대로 이 모드에서 동작. 플롯·판정 패널은 P99/Peak 두 통계를 동시 표시(선택 통계=판정·최적화 기준).

## 9. ★τ-HARD 정정 + 모터 파워 포락선 (2026-07-10, 사용자 지적)
**정식화 오류 정정**: v2~v3에서 τ마진을 목적으로만 두어 "용량 34 vs 수요 120"이 ✓FEASIBLE로 승인되는 병리 발생(사용자 발견). **토크·속도는 둘 다 반드시 지켜야 하는 설계변수** → `v.tau=max(0,−f)/40`을 HARD로 승격, 목적=feasible 내 최악 τ마진(≥0) 최대화.

**근본 진단 — 파워 포락선**: 기어비/링크는 파워를 만들지 못하므로, bin의 τ×ω 동시수요가 모터 최대 기계파워를 넘으면 **어떤 기하로도 불가**. RS04 실측 TN의 $P_{max}=1.29$kW인데 worst 정책의 무릎 bin별 **실동시파워 p99 = 2.5~3.5kW**(−127~−77°, τ·ω 곱의 p99를 npz에서 직접 계산; envelope 짝짓기 τ99×ω95보다도 큼). flat(nom)은 67W. 원인 = sim이 velocity_limit 33×effort 120 ≈ 4kW 가짜 모터로 학습된 인공물([[reference-robstride-motor-specs]] 갭의 파워 버전). 툴에 "모터 파워 커버" 진단 행 추가 — 초과 bin 수와 Pmax를 표시하고, infeasible 사유에 "기하로 해결 불가 → 재학습/사용범위/모터 재검토"를 명시.

**τ-hard 재검증 스캔**: 전체 worst+nom=파워초과 13bin→불능(정직) · 사용범위 [−70,−25]=1bin 초과→불능 · **[−60,−25]=초과 0 → ★FEASIBLE f=+4.7 N·m** (r2=65/r3=221/r4=80, 제한-아크·μ완화) · nom만=f=+203. 즉 지속하중 구간(≥−60°, §8 점유 분석과 일치)은 **RS04 4절로 정당하게 커버 가능**하며, 심굴곡은 velocity-19.9 재학습으로 수요가 정상화되기 전까지는 링크 설계 대상이 아님(파워 적자).

## 8. 하중-가중 전달각 창 (2026-07-09 밤, 사용자 제안)
데이터 검증: **flat 정상보행은 무릎 −60°보다 깊은 굴곡 점유 0.8%·τp99 22 N·m** — 사용자 직관대로 하중이 없음. worst의 심굴곡 고τ(>80N·m 20~55%)는 점유 1~4%의 **낙상회복성 과도**(모터클립)로, 업계 원칙([[56]])상 과부하 영역. → **2-구간 μ창** 구현: 무릎 ≥−60°(지속하중)만 엄격 [40,145], 그보다 깊으면 [20,170] 완화(`muRelax` UI, 경계·창 조정 가능).
재스캔 결과: ①전회전(crank-rocker)은 μ완화 + 심굴곡 ω를 과도취급까지 해도 **여전히 불능**(구조적으로 사망) ②**제한-아크는 f −83→−64로 개선**(+19 N·m) & 최적점이 극단(r2=77.5/r4=40)에서 온건한 기하(r2=57.5/r3=238/r4=47.5)로 이동 — μ완화의 실효는 "crank-rocker 소생"이 아니라 **제한-아크 설계의 마진·기하 개선**.
