# 62 · 전수검사 — 폴리시 학습법·리워드 재검토 / 자연 보행 / 최악조건 도출 / 설계값 선정

> 2026-07-09. 사용자 요청: "지금까지의 연구 전수검사 + 학습법·리워드 재검토. ①어떻게 사람처럼 자연스러운 gait cycle로 에너지·충격 효율적으로 걷게 하나 ②설계용 최악조건은 어떻게 도출하나 ③어떤 값을 써서 설계하나."
> 방법: 병렬 감사 4계통(gaitfix 시대 / g1·humanref·Siekmann 시대 / 자연보행 지식·문헌권고 / 최악조건·설계값 방법론) + mjlab 시대(A0~P2, R계열, warm-start churn)는 본 세션 직접 지식. 교차일치 확인함. 원 감사보고는 세션 로그, 근거는 각 항목의 원 노트 링크.

---

## §1. 리워드/학습법 계보 전수검사 — 확정된 원칙 12

55+개 실험, 16+개 reward_research 노트에서 **A/B 또는 전후 증거로 확정**된 것만:

| # | 원칙 | 증거 (수치) | 출처 |
|---|---|---|---|
| 1 | **기하 앵커가 아키텍처 층** — base_height(−1.0@0.85) 제거=까치발 회귀(0.95m), 복원 1변수로 즉치(0.851m, 10→57사이클) | v3 vs v4 clean A/B | [[2026-06-29_tiptoe_regression]] |
| 2 | **관절각 모방(DeepMimic류)은 위상 불일치로 실패** — weight ↑(+1.0→2.5)일수록 악화: hip corr +0.6→−0.28, CoT 2.62 | humanref v3/v7 | humanref_v7 리포트 |
| 3 | **위상은 "입법"이 답** — Siekmann periodic_contact 1개 항이 까치발·절뚝·에너지 동시 해결: GRF 8.9→3.1×BW, CoT 2.62→1.22, 비대칭 0.83→0.18 | v7→v8 | siekmann_v8 |
| 4 | **but 고정 클록은 정지·가변속과 충돌** — v=0에서 강제 스텝핑, tracking 0.32 고착 → command-gated 스택으로 회귀(P2) | periodic_contact 제거 연구 | [[2026-07-05 periodic_contact_removal]] |
| 5 | **일(τ·ω) 보상은 cap 필수** — 무cap ankle_pushoff: reward 324 폭주(정상 41), GRF 11.5×BW. 역으로 **페널티의 clip이 너무 낮으면 큰 스파이크의 기울기가 죽음**(B1 clip400: P99 −19% 정체+peak 악화 → clip800 즉치 −27%) | pushoff v1 vs v2 · B1 vs B1w2 | forefoot_pushoff, mjlab B1/B1w2 |
| 6 | **순서 규칙: 충격 cap → push-off** — cap 없이 push-off 먼저 넣으면 게이밍(v9 GRF 11.5×BW) | v9 사건 | siekmann_pushoff_v9 |
| 7 | **직접 토크 보상(\|τ_toe\|) 금지** — 정적 컬로 게이밍; 원인(전족부 GRF/CoP 진행)을 보상해야 | v5 toe_load 실패 | [[2026-06-29_toe_use_reward]] |
| 8 | **약한 페널티(−0.5)는 추종(+2~3) 못 이김** — foot_flat/swing_height 기여 ~2%로 무력; "완화≠생성"(base 완화해도 vault 안 생김, 전이 메커니즘 필요) | g1is_v2, gaitfix v6/v7 | 해당 리포트 |
| 9 | **검증된 베이스라인 우선** — G1 vanilla가 20항 커스텀(gaitfix v7)을 추종 3×(0.186 vs 0.545)로 압도; <10항 미니멀이 실기체 검증 스택 | g1van_full vs v7 | [[g1-vanilla-beats-custom-reward]] |
| 10 | **pose std는 상태별 분리** — std_standing 0.05(직립 고정) + std_walking knee 1.2(보행 굴곡 허용): 정지 −5.6°/보행 −67° 양립 | P2-final | [[2026-07-06 straight_knee_stiff_gait]] |
| 11 | **게인은 리워드보다 상류** — link-critical Kd: 하중 2~3.5×↑ AND 추종 2.8~5×↓ 양축 열세; Kp/Kd는 링크 관성 기준으로 | B vs C 단일변수 A/B | [[53_bc_kd_controlled_ab]] |
| 12 | **커리큘럼 상태는 가중치와 함께 이식됨** — warm-start 시 step counter 복원→DR·명령 iter0 최대→**축 churn**(자식이 부모 도메인에서 vx 81→26%); 2단계(Phase1 DR-off→램프)가 flat·rough 모두에서 유일하게 재현 성공 | P1/P2 성공, rough 1차 실패→P1 재시작 즉치(track 0.33→0.98) | [[61_velocity_tracking_review]] §5 |

**교차-run 실패 카탈로그** (재시도 금지 목록): 관절각 human-ref 추종(위상 불일치, 3회) · \|τ_toe\|/정적 forefoot fraction(게이밍·무력) · 무cap 일 보상(해킹) · air_time을 저질량용 가중치로 이식(51.5kg에선 flight 죽음, asimov) · tight ankle deviation(착지 경직→GRF 2×) · cross-robot warm-start(붕괴) · link-critical Kd · soft 합성점수 최적화(제약위반 해 선택, [[60_fourbar_optimizer_research]]).

**리워드 스태킹의 정량 캐스케이드** (mjlab B-계열, GRF P99 ×BW): A1b 2.45 → B1(cap −0.005/clip400) 2.34 → B1w2(−0.01/clip800) 2.05 → B2(+thermal) 1.88 → B3(+Siekmann) 1.63 → P2-final 1.28 — 단일 마법 항 없음, **층 순서대로 누적**.

**추가 원칙 13 — 기여도 회계**: 총 reward의 ~0.1% 미만 기여 항은 아무것도 못 움직임(forefoot_cop 0.018%, cop_progression 0.09% 실측) — 새 항 투입 시 기여율을 게이트 지표로.

**미절제(un-ablated) 교란 목록** (후속 A/B 후보): ①action_scale 0.25 — A0 이후 전 계열 고정, 게인 효과와 분리 불가 ②ankle_pitch 110→45% 해방 — cap/thermal 캐스케이드 합작(개별 기여 미분해) ③**air_time vs periodic_contact — 동일 명령·지형에서 정면 A/B 한 번도 없음**(P2와 B3는 다른 지표로 수락됨; §2b-2의 명령게이팅 클록 실험이 이 공백을 겸사 메움) ④P1/P2 번들 — 대칭 XML+직립 init+0° 하드스톱+std_walking 1.2+air_time+hip 150/6이 동시 투입, 개별 귀속 불가 ⑤std_walking knee 1.2 — 단일 진단 기반, 스윕 없음 ⑥**mjlab엔 base_height reward 앵커가 아예 없음**(low_base 종료 0.7m만) — IsaacLab 시대 최대 레버였는데 이식 안 됨; 까치발 재발 시 1순위 복원 후보(고정 타깃의 vault 억제 부작용 있으니 deadband 형으로).

---

## §2. ①자연스러운 gait cycle + 에너지·충격 효율 — 처방

### 2a. 현재 최고 기록 원장(ledger)
| 지표 | 최고값 | 달성 config | 사람 기준 |
|---|--:|---|---|
| GRF P99 | 1.28×BW | P2-final (cap) | 보행 1.0~1.2 |
| GRF peak(clean) | 3.1×BW | siekmann_v8 | — |
| CoT | 1.22 | siekmann_v8 | ~0.2(인간), 로봇 0.7~2 |
| double-support | 15% | P2-final | 20~24% |
| 하중 L/R 비대칭 | 0~8% | P2-final | — |
| 운동학 L/R 비대칭 | 24%(knee flex) | P2-final 잔존 | ~0 |
| toe 사용 | 26% 적재, 타이밍 틀림(스윙 71~79%서 peak) | — | push-off 50~62% |

**긴장 관계**: 자연성 최고(v8, 클록)와 배포 강건성 최고(P2, command-gated)가 다른 스택. v8의 클록은 정지를 깨고, P2는 클록이 없어 대칭·CoT가 v8보다 약함.

### 2b. 권장 차기 스택 (검증된 것 + 문헌권고 중 미시도, 우선순위순)
1. **[유지] 3층 아키텍처**: ①기하 앵커(base_height≒low_base term, pose 이중 std, upright) ②위상 구조 ③효율·충격(contact_force_cap −0.01/600N, thermal_effort Σ(τ/rated)²) — 순서 불변(충격 cap이 push-off보다 먼저).
2. **[신규-최우선] 명령-게이팅된 클록**: |cmd|>0.15에서만 활성화되는 periodic_contact(v8 그대로: stance 60%, 발 0.5 위상차, sin/cos obs) — v8의 대칭·GRF·CoT 이득과 P2의 정지·가변속 양립이 목표. 게이트 자체는 이미 air_time에서 검증된 패턴.
3. **[신규] 대칭은 소프트 로스가 아니라 구조로**: mirror-equivariant actor(또는 rsl_rl symmetry augmentation) — 문헌상 soft loss 대비 "정확히 0" 대칭 오차. 24% 운동학 절뚝 + 측방 만성 약점([[61]])의 정공법. 미시도 레버 중 최대.
4. **[신규] toe-off 3단**: ⚠**전제 2개** — ①cap 존재 ②**toe joint 복원**: 현 mjlab 활성 XML(pygmalion.xml)은 toe joint가 주석 처리된 **rigid foot**임을 전수검사에서 확인(2에이전트 독립 지적+XML 직접 검증). passive toe는 IsaacLab 시대 모델에만 있었고, windlass/CoP-rollover 연구 전체가 현 계보에선 좌초 상태 + 측정된 ankle 하중도 toe 컴플라이언스 제외값. 복원(k≈60 N·m/rad) 후 → `ankle_pushoff_work`(+0.5, cap 80W, terminal-single-stance 게이트) → `cop_progression`(+1.2, 클록 위상 0.45~0.6 게이트). v9 실패는 순서 위반이었지 항 자체가 아님. 병행: sole 기하(전족 분리 접촉) 검토.
5. **[에너지] power_cot(속도정규화)** 본선 미투입 상태 — CoT 1.22→1.0↓ 목표로 마지막에 소량(+0.2~0.4, anneal). PPO-Lagrangian 하드제약은 리팩터 커서 보류.
6. **[학습법 고정] 2단계 커리큘럼 + warm-start 규칙**: Phase1 PYG_NO_DR(+FRESH_STEPS) → Phase2 DR 램프; cross-config 이식 시 actor-only + counter 명시 결정([[rough-terrain-warmstart]]). 게이트: 시간(≤1h)+iter 이중, 방향별 추종 재측정(§[[61]] 방법)을 게이트 표준지표에 추가.

---

## §3. ②설계용 최악조건 도출 — 프로토콜

### 3a. 확정된 방법론 (이 프로젝트가 비싸게 배운 것)
1. **수렴 정책만 측정** — 12k 중간측정은 낙관 오류(knee 93→107%, ankle_roll 29→134% @39k). 게이트는 수렴까지.
2. **"최악"은 반드시 in-DR** — 학습분포 밖(OOD) 명령의 스파이크는 설계값 오염(blind-rough 속도 490~953rpm은 인공물). 해법은 스케줄 자르기가 아니라 **학습 DR을 넓혀 최악 스케줄을 in-DR로 만들기**(yaw ±0.7→±1.5 선례). 측정마다 dr_coverage 플롯 필수.
3. **수요는 정책 인공물** — 8개 리워드 체계에서 ankle_pitch 6×, ankle_roll 30× 변동; B3 반전(핫폴리시 ankle 113%→정상화 후 47%). ⇒ **"리워드 규율(cap·thermal)을 HW 스펙의 운용조건으로 명기"**. 제어(Kd) 정상화도 선행(3.45× 갭).
4. **peak는 단일시드 고분산** — 동일 명령서 GRF peak 2.4~6.2kN 요동; 추세판단은 p95/RMS로.
5. **클리핑=검열된 수요** — τ가 모터한계에 붙으면 그건 수요가 아니라 "모터가 낸 만큼"(과소평가).

### 3b. 남은 갭 → 표준 프로토콜 제안 (차기 캠페인)
| 갭 | 조치 |
|---|---|
| 낙상/걸림/충돌 미시뮬 | **전용 캠페인**: 지정 낙하·trip 시나리오 + (문헌대로) 보호정책 유무 2조건 — 단 이 값은 §4의 "정적 사이징 대상"이 아니라 **과부하·퓨즈 설계 입력** |
| push-recovery 하중 미측정 | measure 스케줄에 학습 DR과 동일한 push 주입 추가 |
| 단일 시드 | 최소 3~5 시드 P99 산포 → 설계값에 신뢰구간 |
| rough 조건 거칠음 | terrain-level별(계단높이·경사) 조건부 하중 분해; rough 정책은 진행 중인 P1/P2 완료본으로 재측정 |
| 검열 수요 | effort limit 1.5×로 올린 측정 1회(학습 아님, 측정만) → 진수요 관찰 |
| 속도한계 sim-real 갭 | RS04 실측 19.9 rad/s로 velocity_limit 재학습 후 무릎 수요 재확정 |

### 3c. "진짜 최악"(낙상)은 정적 사이징하지 않는다 — 업계 스택([[56_humanoid_impact_fall_load_handling]])
계층: 충격내성 전달계(QDD/SEA, 하모닉이면 슬립클러치=기계 퓨즈) → **단시간 과부하 정격 1.5~5×** → 보호정책(낙하 토크 −78%) → 손상허용·현장수리. 우리 방향(무릎 4절 링크 = Cassie/Digit 가변비 선례, [[57]])과 정합.

---

## §4. ③어떤 값으로 설계하나 — 통계→설계결정 매핑 (확정 규칙)

| 설계 결정 | 사용 값 | 근거/조건 |
|---|---|---|
| 모터 **연속(열)** 정격 | **RMS ≤ rated** (또는 T_ss=25+120(τ_rms/rated)²\le145^°C); 과도는 overload 곡선 적분 S<1 | actuator_evaluation §0 |
| 모터 **순시** 정격 | **in-DR P99 ≤ peak** (peak 자체는 참고; 단일시드 고분산) | 진행분석 노트 |
| 속도/전압 여유 | 실측 **TN 곡선 포함률**(out-env %) — 카탈로그 아님 | Motor_Spec 실측 |
| 지속 포화 vs 순간 | **p95>rated=진짜 바인딩**, max만 초과=peak 마진 문제 | ankle_pitch vs knee-speed 사례 |
| 링크/구조 **정적 강도** | 축별 peak 시점의 **전체 6축 wrench 벡터** × SF 1.5~2.0 | 46/wrench 노트 |
| 구조 **피로** | RMS 6축 + 사이클 수 | 〃 |
| FEA 3단 | 설계=최종정책 P99 / 검증=정상영역 union max / 파국=해킹런 6.2kN | design_insights I7 |
| 기구 최적화(4절 등) | **HARD 제약 분리 + feasible끼리만 목적 비교**(Deb) — 합성점수 금지 | [[60]] |
| RL-free 하한 검증 | 정적 중력유지 검산(한발 스쿼트 knee 155 등) 항상 병행 | actuator_eval §2.5 |
| 낙상/충돌 | 정적 사이징 ✗ → 과부하 정격+퓨즈+보호정책 입력값 | §3c |
| 보정 | sim→real 마찰 ×1.15(액추에이터 τ만), 속도한계는 실측 재학습으로 해소 | 〃 |

**한 줄 원칙**: *열은 RMS로, 순시는 in-DR P99로, 구조는 P99 wrench×SF로, 추세는 p95로, 낙상은 사이징이 아니라 계층 스택으로, 그리고 모든 수요값 옆에 "어느 정책·어느 DR에서"를 명기한다.*

---

## §5. 실행 큐 (우선순위)
1. (진행 중) rough P1(`rough_p1_nodr`) 완료 → P2 DR램프 → **§[[61]] 방향별 추종 게이트 통과 확인**
2. rough P2 완료본으로 §3b 프로토콜 첫 적용(멀티시드 + push 주입 + terrain-level 분해) → 설계값 갱신
3. 명령-게이팅 클록 실험(§2b-2) — v8 지표(비대칭 0.18, CoT 1.22) 재현 + 정지 보존 게이트
4. mirror-equivariant/symmetry augmentation(§2b-3) — 절뚝·측방 정공법
5. toe-off 3단(§2b-4) — cap 전제 확인 후
6. RS04 19.9 rad/s 재학습(§3b) — 무릎 수요 최종 확정 → 4절 링크 설계 재실행([[59]] 툴)
