# 66 · 실험 레지스트리 — 계보·변인·정량결과 총괄 (비교용)

> 2026-07-11. 전 실험을 **계보(era)별로 구분**하고 실험 간 **정량 비교가 가능하도록** 변인·핵심수치·판정을 한 표에 고정. 그래프 뷰: [[experiment_map.canvas]].
> ★**유지 규칙 (사용자 지시, 매 실험 필수·훅 강제)**: 새 실험마다 ① 이 표에 행 추가(런|변인|정량|판정) ② canvas에 노드+계보 엣지 추가. `audit_notes.sh`가 최신 실험노트보다 이 파일/canvas가 오래되면 세션 종료를 BLOCK.
> 비교 축(공통 자):
> - **추종**: 순수축 명령 달성률 % (★15s dwell 정상상태만 유효 — 2.4s 데이터는 과도응답, [[feedback-video-realtime-rule]])
> - **부하**: knee/hip P99·RMS (×1.15 마찰보정), GRF P99 (×BW) — SF 규칙 [[65_design_value_uncertainty]]
> - **품질**: CoT·낙상률·L/R 대칭
> - 측정 표준: `measure_full.py` fc(clean)/fcp(push) — 0.25격자·2D복합면·15s·in-DR push. **fc/fcp 태그 데이터만 권위**, 이전 npz는 dwell 위반으로 참고용.

## 0. 정책 명명 체계 + 현재 권위(authoritative) 앵커
★**정책 이름 규칙 (2026-07-11 재정의 v2, 사용자: 영어 유지·서술형·타임스탬프·약어 풀어쓰기)**:
`<terrain>-<vmax>max <reward-type> <robustness-stage> [<variant>] (<launch date>)`
- **reward-type**: `exp-tracking` = 구보상(지수형 속도추종 단독) · `progress-reward` = 선형 진행보상 추가(현행) · 차기 번들은 `gen2-bundle`
- **robustness-stage**: `no-domain-rand` = 물리 랜덤화 없이 gait 형성 (구 "P1") · `domain-rand+push-trained` = push/마찰/관성 랜덤화 램프로 강건화 (구 "P2")
- 파일태그(npz/로그)는 유지, 문서에는 "새이름 (태그)" 병기.

| 새 이름 | 태그/구명 | 데이터 | 비고 |
|---|---|---|---|
| **flat-1.5max exp-tracking domain-rand+push-trained (2026-07-07)** | `p2f_*` / flat P2-final | fc/fcp ✅ | 전박스서 추종붕괴·낙상 109회 → **앵커 부적합** |
| **rough-1.5max exp-tracking domain-rand+push-trained (2026-07-09)** | `p2r_*` / rough_p2_dr | fc/fcp ✅ | **험지 설계앵커**. 험지 정상상태 추종결손 캐비앗(65 §6c) |
| **flat-2.5max exp-tracking no-domain-rand — high-speed-freeze baseline (2026-07-10)** | `flat25p1_*` / flat25_p1 | fc/fcp ✅ | 고속 얼어붙음 실패, 대조 기준선 |
| ★★**flat-2.5max gen2.1-bundle domain-rand+push-ramp bent-knee-init (2026-07-13)** | `gen21p2_*` / gen21_bent_p2 | fc/fcp ✅ | ★★**flat 설계앵커 (현행, 2026-07-13 승격)** — 게이트 전항목 통과(vx2.5 92%·vy 98/98%·낙상 0/0·knee ω 실모터 내), [[2026-07-13_gen21_bent_p2]] |
| flat-2.5max progress-reward no-domain-rand (2026-07-10) | `flat25b_*` / flat25b_prog_p1 | fc/fcp ✅ | 구 flat 앵커(no-DR 세대) |
| flat-2.5max progress-reward no-domain-rand bent-knee-init (2026-07-11) | `bent_*` / flat25b_bentinit_p1 | fc/fcp ✅ | init-pose A/B 상대 (단일변인) |
| flat-2.5max progress-reward domain-rand+push-ramp (2026-07-11) | `p2push_*` / flat25b_prog_p2 | fc/fcp ✅ | straight P2 (stall 잔존) |
| flat-2.5max progress-reward domain-rand+push-ramp bent-knee-init (2026-07-11) | `bentp2_*` / flat25b_bentinit_p2 | fc/fcp ✅ | **전 flat 앵커(2026-07-12~13)** — gen21p2로 교대, 델타표는 [[2026-07-13_gen21_bent_p2]] §4b |

> **데이터(2026-07-11)**: 4정책 모두 fc/fcp **완료** — [[65_design_value_uncertainty]] §2(신 권위표)/§2b(push delta)/§3(GRF) 갱신됨.

## 1. Era-1 · IsaacLab 초기 커스텀 리워드 (2026-06-21) — 전부 폐기
| 런 | 변인 | 결과/교훈 |
|---|---|---|
| flat_fwd_fixed → flat_wide_dr → stage3_ankle_offload → stage4/5_rough | 커스텀 보상 스택 점증 | 보행은 형성됐으나 GRF 8×BW·부자연 gait. [[2026-06-21_06-41-42_stage4_rough]] |
| forefoot_cop / forefoot_pushoff·2 | CoP 전진·pushoff 보상 직접 부여 | ★**보상해킹**: 정적 컬로 게임됨 — "toe 토크 직접 보상 금지" 교훈의 기원 |
| softcontact·2 | 소프트 접촉 파라미터 | 접촉 개선 미미, 폐기 |

## 2. Era-2 · gaitfix 시리즈 (2026-06-22) — 20-term 커스텀의 한계
| 런 | 변인 | 정량 |
|---|---|---|
| gaitfix v2→v7 (+collisiontest) | foot-edge/base높이/pelvis/CoP 항 순차 수정 | **periodic_contact(Siekmann 클록)이 유일한 대형 레버**: GRF 8→3.1BW·CoT 2.62→1.22·L/R 0.83→0.18 ([[62_policy_reward_design_review]] 실패카탈로그) |

## 3. Era-3 · G1 피벗 (2026-06-22) — ★베이스라인 우선 원칙 확립
| 런 | 변인 | 판정 |
|---|---|---|
| [[2026-06-22_17-28-08_g1vanilla]] / g1van_full / g1_rigidtoe2 | G1 표준 minimal 보상 vs 우리 20-term | **바닐라 압승**(자연스러움·추종·낙상) → "검증된 베이스라인 먼저" 원칙 ([[g1-vanilla-beats-custom-reward]]) |

## 4. Era-4 · G1IS/HumanRef/Siekmann (2026-06-28~29) — 사람참조 실패, 클록 성공
| 런 | 변인 | 판정 |
|---|---|---|
| g1is_dm4340 / swingfix / asimov / g1is_v2 | 모터스펙 반영·스윙·Asimov 보상 | 부분개선, 계보 미채택 |
| humanref v3/baseh/toe/v6sym/v7 | **DeepMimic류 관절참조 추적** | ★**반복 실패**(위상 불일치) — 참조추적은 1차 수단 금지 |
| siekmann_v8 / siekmann_pushoff_v9 | 위상클록 periodic_contact (+pushoff) | 클록 성공 / pushoff **무캡 보상해킹**(GRF 11.5BW) — cap 순서 원칙 |

## 5. Era-5 · mjlab 이행 + 통제 A/B (2026-07-02~05)
| 런/A·B | 변인 (단일) | 정량 판정 |
|---|---|---|
| A0a/A0b/A0/A1/A1b | actionscale·resume·lowbase·knee gain | mjlab 파이프라인 확립 |
| B1/B1w2/B2/B3 | 보상 가중 튜닝 | B3 = ankle 정책서 기준(ankle_pitch 47%/roll 14%, [[ankle-actuator-tn-sizing]]) |
| **Kd A/B** [[53_bc_kd_controlled_ab]] | Kd6(B) vs link-critical Kd14(C) | C: 하중 **2~3.5×↑**(knee 3.45×, GRF 6.1 vs 2.1BW) AND 추종 **2.8~5×↓** → **C 기각** |
| **init-pose A/B(구)** [[55_init_pose_straight_vs_bent]] | straight vs bent(크라우치) | bent: GRF **−35%** but knee토크 **+98%**·CoT −8% = 승자없는 재분배 (⚠구 조건 — Era-8서 재실험) |
| R1/R1b/R2 (rough 구식) | Kd28·periodic_contact 시절 rough | **재개 금지**(구식 config, [[rough-terrain-warmstart]]) |

## 6. Era-6 · flat P2 권위, 1.5 독트린 (2026-07-07)
| 런 | 정량 (p2_long, ⚠2.4s dwell → p2f_fc로 대체 중) |
|---|---|
| [[2026-07-07_P2_final_flat]] | knee P99 42.4·hip_roll RMS 24.3·GRF P99 1.33BW·bootstrap CI ±3~18% ([[65_design_value_uncertainty]] §2) |

## 7. Era-7 · rough 2단계 (2026-07-09)
| 런 | 변인 | 판정 |
|---|---|---|
| rough_warmstart_p2final | 단일단계 warm-start+즉시 DR | ★**churn 실패**(vx 81→26%) — common_step_counter 복원 함정 |
| rough_p1_nodr | 2단계-P1 (FRESH_STEPS+DR off) | track 0.33→0.98 즉치 회복 = 레시피 확립 |
| [[2026-07-09_rough_p2_final]] (rough_p2_dr) | 2단계-P2 (DR 램프) | **rough 권위(v2 확정)**: 측정 v2(텔레포트·시드, tile 99.8%)로 재확정 — knee F_r P99 665·GRF 1.48BW·§7c 마스크교정은 선택편향 판명(64 §7d). ★험지 정상상태 추종 41~57%·후진≈0 → Gen-2.1 rough가 해소 목표 |

## 8. Era-8 · flat25 / 진행보상 / init A/B, 2.5 독트린 (2026-07-10~, 현행)
| 런 | 변인 (vs 직전) | 정량 | 판정 |
|---|---|---|---|
| [[2026-07-10_flat25_p1]] | 커리큘럼 2.5 개방 (exp추종만) | knee P99 **96.1**·hip_roll RMS 73%·GRF 1.50BW | 저중속 OK, **고속 얼어붙음**(2.0→5%) |
| flat25_p2 / p2_vid | P2 DR 램프 | cmd 2.0→0.10 | **폐기**(freeze, [[2026-07-09to10_superseded_runs]]) |
| [[2026-07-10_flat25b_prog_p1]] | **+선형 진행보상, std 0.75** (단일변인) | 2.0→**102%**·2.5→**86%**(15s)·hip_pitch P99 **119.8**·knee 97.5·GRF 1.73BW·ankle_pitch RMS 106% | ✅freeze 해소 / ⚠중저속 stall·vy 31~42%·후진 76% ([[2026-07-11_midspeed_stall_overshoot]]) |
| **bentinit_p1** [[2026-07-11_bentinit_ab_plan]] | **PYG_INIT_BENT=1 단일변인** (config diff 실증) | reward 102.3·progress **0.896**(>straight 0.80)·낙상 0 | ✅완주·측정완료 |
| **★P1 init A/B 판정** [[2026-07-12_bentinit_ab_result]] | straight vs bent, 동일 fc/fcp 프로토콜 | **bent 승**: knee P99 −20%(113.9→90.8)·GRF peak −37%(7.5→4.7BW)·전관절 M_t↓(ankle_roll −38%)·push낙상 31 vs 19·vx2.5 93% vs 86%. 비용: ankle_pitch P99 +186%(2-RSU 필수)·hip_yaw +13% | **구 A/B(+98% knee) 반전** — 고속레짐선 bent 우세. Gen-2 init=bent 잠정 |
| flat25b_prog_p2 (`p2push_*`) | P1→DR+push 램프 (20k→32k) | ✅완주·측정. knee P99 91.9·GRF 1.35BW·push낙상 3. ⚠**stall 잔존**(2.5 블록 33~70% 널뛰기) | DR로 stall 안 고쳐짐 확증 |
| bentinit_p2 (`bentp2_*`) | bent P1→동일 P2 레시피 | ✅완주·측정. **push 453회 낙상 0**·추종 균일 79~97%·knee 109.3·GRF **1.30BW** | 전 flat 앵커(2026-07-12~13) — gen21p2로 교대 |
| **gen2_bent_p1** [[2026-07-12_gen2_bent_p1]] | **Gen-2 번들 4건**(bent init+hip_roll std 0.4+stand_still_penalty+knee_overspeed) | ★게이트: **vy 61/96% 최초통과**·stall 0.75→84%·후진 109~117% 회복·knee ω 15.6 ✅ / 2.5→67%·knee P99=클립(체류 2%) ❌ | 부분통과 — P2가 최종판정(bent 선례상 P1 널뛰기는 DR이 완화). ⚠stall벌점 creep-게이밍 시그니처(1.5→43%) → ablation 후보: 상대임계 |
| **gen2_bent_p2** (학습중, 2026-07-12_18-34) | gen2 P1→DR+push 램프 (+12k→32k) | ★최종게이트: vy 90/93%·GRF 1.24BW·knee 102.9(클립이탈)·ω 13.9·낙상 0 ✅ / **고속 57%/56% ❌(creep 게이밍 DR 불변)** [[2026-07-12_gen2_bent_p2]] | **앵커 유지=bentp2**(고속 미달성→부하 과소). ablation 발동 |
| **gen21_bent_p1** [[2026-07-13_gen21_bent_p1]] | stand_still_penalty **절대→상대임계**(proj<0.3·\|cmd\|) 단일변수 [[2026-07-13_stall_relative_threshold]], env.yaml diff=0(코드 조건식만) | fc: 2.5→**85%**·**1.5→114%(creep 해소)**·0.75→97% / −2.0→69%·vy +1.0→65%(DR-off 명목 저조) / knee P99 102.5·ω P99.9 13.9·GRF 1.38BW·낙상 0/0 | ✅게이트 통과(1.5·2.5 헤드라인) → P2 진행. 후진·측방 저조는 P2 DR이 해소 |
| **gen21_bent_p2** [[2026-07-13_gen21_bent_p2]] | gen21 P1→DR+push 램프(+12k→31998, 단일변인 diff 실증) | ★최종게이트 **통과**: 2.5→**92%**·−2.0→91%·vy **98/98%**·knee RMS 45.5/P99 112.4(체류 0.69%)·ω P99.9 14.3(max 18.9<19.9)·GRF 1.31/1.40BW·낙상 **0/0**·push delta knee +0.5% (⚠1.5=59% — 인접 94~96%·P1 114%로 **단일블록 노이즈 판정**) | ★★**flat 설계앵커 승격**(bentp2 대체, 65 §2). 험지 Gen-2.1 warm-start 부모 |
| **★P2 init A/B 최종판정** [[2026-07-12_bentinit_ab_result]] §8-9 | 양팔 push-학습 후 재비교 | bent: 낙상 0 vs 3·추종 균일·과반관절/GRF 우세; straight 우위는 knee(+19%, achieved-confound)·ankle_roll M_t뿐 | **Gen-2 init = bent 확정** |

## 8b. Era-9 · 하드웨어 기하 co-design (2026-07-14~) — CAD 확정 기하 → MJCF → 재학습
> 기하(MJCF) 자체가 변인인 시대. 부하값은 기하 간 이전 불가([[67_hip_cant_and_roll_motor_review]] §3) — 변형마다 Gen-2.1 레시피 재학습 + fc/fcp 재측정.

| 런 | 변인 (vs 직전) | 정량 | 판정 |
|---|---|---|---|
| **cant30_p1** (`2026-07-14_01-08-15`, ✅완주 model_19999) [[2026-07-14_cant30_p1]] | **PYG_HIP_CANT30=1 단일변인**(vs gen21_bent_p1): hip_pitch 축 30° inner-up 캔트 + pitch↔yaw 스큐 3.4→0mm + hip_roll 축 29.7mm 오프셋(측방 28.3/수직 8.6). reward/gains/init/DR-off 동일(Gen-2.1 P1 fresh, 8192env·20k) | 기하검증: 캔트 30.000°·스큐 0.000mm·오프셋 29.671mm·L/R 미러 PASS. ★단일변인 실증: env.yaml **diff=0**(기하는 spec_fn XML 경유)·PYG 토글 3종 확인 | ✅ **P1 게이트 통과**: reward 97.88·progress 0.86·err_xy 0.955·**fell 0.000** = 비캔트 gen21 P1과 동등(quick gate 2.5→90%·0.75→95%·1.5→76%). **캔트가 학습 무해** 1차 확정 → **P2 진행**(`07-40-59_cant30_p2`, DR+push 12k, ETA≈11:40) → 부하 A/B(cant30_p2_fc↔gen21p2_fc)가 docs/67 §5/§6 예측(pitch τ −12%·yaw duty +45%·반영관성 +33%) 검증 |
| **cant30_p2** (`2026-07-14_07-40-59`, ✅완주 model_31998) [[2026-07-14_cant30_p2]] | cant30_p1 resume + DR+push 램프 12k(vs gen21_bent_p2와 단일변인=캔트기하). reward/gains/init 동일 | full DR+push(dr_factor 1.0): **fell 0.0000**·track_lin **1.33**(비캔트 1.35)·track_ang 1.25·reward 72–74. **부하 A/B**(cant30p2_fc↔gen21p2_fc): knee RMS 114→101%·hip_pitch −3 (완화) ↔ ankle_pitch P99 91→97%·ankle_roll 73→89%·hip_roll RMS +8 (가중) | ✅ **정책비용 0**(비캔트 동등). **부하=재분배(knee↓/발목↑), 무료이득 아님** — 약체발목 peak 가중이라 순수부하론 비권장, **정당성=패키징**. 재투영(−12%)은 적응실측(−3%)+knee/발목 재분배로 정정(docs/67 §8). α20 확인가치 |
| **gen21_rough_uneven_p1** (`2026-07-14_17-18-44`, ⚠️중간폐기 iter1900) [[2026-07-14_gen21_rough_uneven_p1]] | 1차 처방: 계단 40% 제거(PYG_UNEVEN) but **슬로프 45° 잔존**. actor-only ws(flat)+DR-off·4096env | fell 0.60→0.32(감소 명확=계단 주범 확증) but ~0.33 둔화(≈슬로프비율 0.30, 급슬로프서 실패)·reward −260 불안정 | ⚠️ **부분성공**: 계단제거 방향 옳음. slope 45°가 잔여병목→slope 0.3으로 재launch(uneven2) |
| **gen21_rough_uneven2_p1** (`2026-07-14_18-21-12`, ✅완주 model_11999) [[2026-07-14_gen21_rough_uneven2_p1]] | 2차 처방: 계단0% + **슬로프 45°→17°(slope_range 0.3)**. 나머지 동일 | **fell iter600서 ~0.00 수렴, 종료 0.0000**·track_lin 1.10–1.17·reward ~58. ⚠reward 스파이크 36/12k iter(캡없는 페널티, fell무해) | ✅ **진단 완전확증** — walkable uneven만 남기니 낙상 0. rough 트랙 소생 |
| ~~gen21_rough_uneven2_p2~~ (`00-58-24`, ✗폐기) | P1 resume DR+push | **dr_factor 0.0 고정**(iter17571) | ✗ DR 미램프 버그(start_step=20k iter 하드코딩 vs P1=12k). kill |
| **rolloff30_p2** (`2026-07-16_07-32-41`, ✅완주 model_23998) [[2026-07-16_rolloff30_p2]] | rolloff30 P1 resume + DR+push(dr override). roll축만 외측30mm 단일변인 | dr 1.0·**fell 0.0000**·track_lin 1.31·reward 66 | ✅ 기하 무저해. fc 재측정중(⚠첫 시도 launch실패 적발)→A/B: roll RMS +15N·m 상시 가설(docs/67 §9) 검증 |
| **cant20fp_p2** (`2026-07-20_23-57-05`, 학습중) [[2026-07-20_cant20fp_p1]] | P1 resume+DR+push(dr override) | (학습중) | 🔄 완주→fc→**α20 vs α30 vs flat 3-way** |
| **cant20fp_p1** (`2026-07-20_19-50-12`, ✅완주 model_11999) [[2026-07-20_cant20fp_p1]] | **α=30→20 단일변인**(pygmalion_cant20.xml: 축 cos20/±sin20·스큐 0.002mm 재해결·roll offset 유지, PYG_HIP_CANT20 + 발평행 hip_yaw ∓0.113=±6.2°→0°). flat·ws·DR-off | fell **0.0000**·track_lin 1.69·reward 106 (cant30fp 동등) | ✅ P1 정상→P2. A/B 목표: ankle_pitch 100% peak 회복 여부(§6 스윗스팟 검증) |
| **cant30fp_p2** (`2026-07-15_23-36-31`, ✅완주 model_23998) [[2026-07-15_cant30fp_p2]] | cant30fp P1 resume + DR+push(dr override). 발평행 초기자세. vs 구 cant30_p2=발보정만 | dr 0→1.0·**fell 0.0000**·track_lin **1.35**(gen21p2·구cant 동등)·reward 77 | ✅ **3-way A/B 완결**: 발평행→ankle_roll/hip_yaw/hip_roll **flat 회복** BUT **knee offload 소실**(116, flat보다↑)·ankle_pitch **100% RS03 peak 잔존**. ★구 cant 재분배=발벌림 산물. **캔트=하중 순이득 없음→패키징 단독 정당화**(docs/67 §10) |
| **cant30fp_p1** (`2026-07-15_18-43-21`, ✅완주 model_11999) [[2026-07-15_cant30fp_p1]] | ★**cant30 재학습(feet-parallel)**: 캔트 BENT의 발 ±9° toe-out을 hip_yaw init 보정(L−0.165/R+0.165, cant30 전용 keyframe)으로 X+ 평행화(heading 0.00° 검증). flat·warm-start·DR-off·8192env. 구 cant30(발벌어짐) 대체 | fell **0.0000**·track_lin **1.69**·track_ang 1.60·reward 105 (구 cant30_p1 동등, 발평행이 gait 무저해) | ✅ P1 정상 → P2(`23-36-31`, dr override) 진행→fc→A/B(vs 구cant·gen21p2). cant30**fp**=feet-parallel |
| **rolloff30_p1** (`2026-07-15_14-17-23`, ✅완주 model_11999) [[2026-07-15_rolloff30_p1]] [[2026-07-15_gen21_rough_uneven2_p2b]] | **PYG_ROLLOFF30 단일변인**(hip_roll축만 외측30mm, yaw이하 원위치·pitch불변). flat, actor-only ws(gen21_bent_p2)+DR-off, 8192env. cant30과 동일방법론 | (학습중) | 🔄 roll-offset **A/B용**(docs/67 §9). 완주→P2(★dr override 12k/24k)→fc→**vs gen21p2_fc**로 roll RMS 상승·재분배 확정 |
| **gen21_rough_uneven2_p2b** (`2026-07-15_03-48-03`, ✅완주 model_23998) [[2026-07-15_gen21_rough_uneven2_p2b]] [[2026-07-14_gen21_rough_uneven2_p1]] | P1 resume + DR+push, **PYG_DR_START/END_ITER=12000/24000**(dr윈도우 정렬 override) | dr P2b시작부터 램프(0.006→1.0@iter24k)·fell 0.0000 | ✅ **rough 설계앵커 확정**(v2 tile 88.6%). 부하: knee −17%p·**ankle_roll RS00 P99 73→126% peak 초과(험지 병목)**·GRF 1.74BW(flat 1.20). flat(knee 열)과 다른 관절 worst → 하중세트=flat∪rough max. RS00 상향 과제 |

## 8c. Era-10 · 프린트 로봇 + 실측 모터 + 발목 기구 A/B (2026-08-23~)
> 모델이 바뀐 시대: 3D 프린트 하체 질량(35.35 kg, [[89_printed_parts_density_ratio]]) + 실측 모터 파라미터(armature/damping/friction, 벤치 시스템ID) + 실측 T-N 곡선 액추에이터 + 하드웨어 관절/토크 한계. 발목은 **AB(2-RSU 폐루프, 크랭크 액션)** vs **RP(직렬 + 자세별 선형화 토크 한계)** 두 케이스. 보상 = gen21 번들 그대로, DR·속도·푸시는 단일 런 커리큘럼. [[92_ankle_ab_rp_training_setup]], [[91_closed_loop_ankle_rl]].

| 런 | 변인 (vs 직전) | 정량 | 판정 |
|---|---|---|---|
| ~~ankleAB_c1 / ankleRP_c1~~ (`20-45-09/27`, ✗ iter 172 중단) | 팔이 영점(매달림)으로 weld → hip_roll 링크와 14 mm 관통 | — | ✗ 상체 팔 15° 외전 고정 후 c2로 재시작 |
| (config-test) ankleAB_softtest / softtest2 [[2026-08-24_ankleAB_softtest]] [[2026-08-24_ankleAB_softtest2]] (02:00 / 02:43, c2r 3100+800 iter, 1024 env) | soft-landing 항 형태: 선형 w −2 vs 제곱 w −1 | 접지속도 1.24 → **2.42**(선형, 해킹) / **0.98**(제곱) m/s; 피크 1.50 → 1.66 / 1.31 BW | 선형 기각·제곱 채택 → c3 |
| **ankleAB_c3 / ankleRP_c3** "flat-2.5max gen21-bundle+**soft-landing** curriculum-dr+push ankle-AB / -RP (2026-08-24)" (`03-22-35` / `03-22-58`, ✅**완주 32,000** 2026-08-25 23:06, 39 h 45 m) [[2026-08-24_ankleAB_c3]] [[2026-08-24_ankleRP_c3]] | c2 + `PYG_SOFT_LANDING`(제곱 접지속도 w −1·h 0.10, GRF 캡 420/560) — 두 arm 동일, **유일 변인 = 발목 기구학** | **낙상 0.000 양쪽**(vx 2.5·DR 만배 12k iter 소화). fc 전체박스 121명령×15 s: 추종 순수vx **AB 0.89 / RP 0.90**, vy 0.68 / 0.75. **모터 여유(2026-08-26 정정, 모터축 사상): AB 0.51–0.53 / RP 0.44–0.55, 포화 ≤0.03 % — 사실상 동률** (앞선 'RP 0.80·3.3 %'는 발목축을 모터곡선에 대조한 오류). 발목축 수요 p99 59–65 N·m → **RS03 직결 불가, 2-RSU 증폭 필요**. 에너지 CoT RP 0.277 < AB 0.314(−12 %), 충격 무승부, 보폭 AB 273 vs RP 175 mm. ★두 arm 모두 **명령 0.25 m/s 무시**(리워드 산술상 정지가 최적) | ✅ 차이는 하드웨어가 아니라 **행동공간**. RP = 에너지 −12 %·학습 1.7배, AB = 인간형 파형·넓은 보폭. 완주 측정 종료: fc/fcp 121명령×15 s, 평가기 576 ep/arm **성공률 100 %**, 전진 추종 2.4 m/s에서도 0.17 m/s. 다음 세대 계획 [[103_v2_training_plan]] |
| **ankleAB_c2 → c2r** "flat-2.5max gen21-bundle curriculum-dr+push ankle-AB-loop (2026-08-23)" (`21-02-10` → OOM iter1252 → `23-17-35_ankleAB_c2r` resume model_1200, ⏸ iter 4400에서 중단 → c3로 계승) [[2026-08-23_ankleAB_c2]] | vs gen21_bent_p2: 프린트 질량·실측 모터(RS04 J .0163/b .0095/tc .269, RS03 .0153/.0223/.285)·T-N 곡선·**폐루프 발목(크랭크 RS03 ×2, Kp 22.3/Kd 1.41/60 N·m)**·단일 런 커리큘럼(DR 10k→20k, vx 단계 2.5@16k)·16384 env·상체 weld+팔 15° 외전 고정·hip_yaw ±45° | iter 610: reward 109·fell 0; iter 1200 분석(93 §5b): 보행 발목 17° 사용·토크 12.8 N·m·GRFc 1.39 BW, **정지 잔떨림+0.4 Hz 스웨이**; 최신 스냅샷 iter 2659(08-24 01:22): reward 114.1(50avg 114.4)·fell 0.000·err_vel_xy 0.509·thermal 4.02 | 🔄 CONTINUE (4k 게이트서 정지 떨림 재확인) |
| (분석) 폐루프 구속 강성 solimp 전례·변인통제 [[94_loop_constraint_stiffness]] (2026-08-24) | 같은 AB 정책, 구속만 0.9→0.9999 5단계 | 튐 |Δτ| p99: 기본 18.0 / 0.99–0.9999 11–12 N·m, 폐루프 오차 8.4→0.08 mm | 0.999 유지; 학습 A/B(0.95/0.99·solref 5 ms, BRUCE 데드밴드)는 본런 후 |
| **ankleRP_c2** "flat-2.5max gen21-bundle curriculum-dr+push ankle-RP-serial (2026-08-23)" (`2026-08-23_21-02-18`, ⏸ iter 3400에서 중단 → c3로 계승) [[2026-08-23_ankleRP_c2]] | ankleAB_c2와 **단일변인 = 발목 기구**: 직렬 pitch/roll(Kp 28.5/Kd 1.81) + 루프 자코비안 크랭크공간 클램프(±60, T-N) + 반영 관성/마찰. env.yaml diff = 발목 항목만(launch 직후 확인) | iter 610: reward 113·fell 0; iter 1200 분석: 발목 10° 사용·**bang-bang 목표(−40↔+35°) PD 포화 토크 스파이크**·GRFc 1.51 BW; 최신 스냅샷 iter 3433(08-24 02:22): reward 113.5(50avg 113.8)·fell 0.000·err_vel_xy 0.509·thermal 3.56 | 🔄 CONTINUE |

| (분석) 영상 계보 감사 — 아카이브 최적화 클립 = 폐기된 §7e 패턴서치 [[71_ankle_2rsu_optimization_setup]] §18 (2026-08-24) | 08-11 클립 종료 기하 vs 최종 v9h2 대조(프레임 판독 + 4에이전트 감사, 적대적 반증 4건 기각) | 7개 중 5개 불일치(RP_h 20 vs 10 = 2배·A_r 70 vs 65), 마진 16.3% vs +3.41%; 최종 DE 실비용 NP80×161세대=12,880평가 | 신규 자산 `ankle_opt_de_v9h2_convergence.mp4`(23 s)로 대체, 아카이브 8번 ⚠superseded 표기 |
| (분석) 논문 투고 타당성 + 사전연구 41편 [[91_paper_feasibility_icra2027]] (2026-08-24) | 레드팀 3렌즈(신규성/검증/엄밀성) + 4갈래 문헌조사 + 투고처 마감 확인 | 3인 전원 2/5 · ICRA 2026 종료 확인 · ICRA 2027(9/15) 제출 불가 · 치명결함 5건(실측 0건·구형 모델 하중·정책분산 2.6×·FEA 판정 불일치·포지셔닝) | RA-L(11–12월)→IROS 2027 재타겟, 선행조건 E1 freeze 재측정 + E2 발목 벤치 |

## 9. 측정 캠페인 (2026-07-11, fc/fcp 표준) — 데이터 대응표
| 태그 | 정책 | 상태 |
|---|---|---|
| p2r_fc / p2r_fcp | rough_p2_dr | ⚠지형혼합(59.7%) — **p2r_v2로 대체** |
| **p2r_v2_fc / fcp** | rough_p2_dr | ✅ **rough 권위**(v2 텔레포트·시드, tile 99.8/98.9%, 64 §7d) |
| flat25b_fc / fcp | flat25b_prog_p1 | ✅ (★flat 설계앵커, §2 of 65) |
| p2f_fc / fcp | flat P2-final | ✅ (⚠전박스서 추종붕괴·낙상 109/609회 — 부하값 낙상오염, 앵커 부적합) |
| flat25p1_fc / fcp | flat25_p1 | ✅ (베이스라인 대조용) |
| bent_fc / fcp | bentinit_p1 | ✅ (init A/B P1 arm) |
| bentp2_fc / fcp | flat25b_bentinit_p2 | ✅ (★현행 push-학습 flat 앵커) |
| gen2p1_fc / fcp | gen2_bent_p1 | ✅ (DR-OFF 명목, 게이트 부분통과) |
| gen2p2_fc / fcp | gen2_bent_p2 | ✅ (⚠pure-vx creep 미달성 confound — 부하값 참조용, 앵커 아님) |
| gen21p1_fc / fcp | gen21_bent_p1 | ✅ (DR-OFF 명목, 게이트 통과) |
| **gen21p2_fc / fcp** | gen21_bent_p2 | ✅ ★★**flat 설계앵커(현행)** — 게이트 통과·낙상 0/0, 65 §2/§2b/§3 갱신 |

## 10. 다음 판정 대기 (게이트) — 2026-07-13 갱신
1. ~~P1 init A/B~~ ✅ bent 승 · ~~P2 push-학습 앵커~~ ✅ bentp2 → ~~gen2 P2~~ ❌ 기각 → ✅ **gen21p2_fc = 현행 flat 앵커**(2026-07-13 승격)
2. ~~gen2.1 상대임계 ablation~~ ✅ **통과·확정**(2026-07-13, [[2026-07-13_gen21_bent_p2]]): pure-vx 회복(2.5→92%)·push 회귀 해소(낙상 0/0·knee delta +0.5%)·번들 기존승리 유지 — Gen-2.1 레시피 = flat 표준
3. **rough Gen-2.1**: warm-start P1 진행 중(`2026-07-13_21-10-17_gen21_rough_p1`), 게이트 = 험지 정상상태 달성속도(65 §6c)
4. gen21p2 잔여 확인: vx 1.5 단일블록(59%) 시드 교체 재측정 · 떨림 스택(ankle action_rate 분리/EMA)은 차기 번들
5. **Era-9 cant30_p1** (2026-07-14 착수, `PYG_HIP_CANT30` 기하변형 fresh P1): 게이트 = gen21_bent_p1 대비 추종 유지 + yaw 부하 예측(docs/67 §3: P99 +9.6 N·m·ω RMS 0.88) 실측 대조 → 통과 시 P2(DR+push) 진행
