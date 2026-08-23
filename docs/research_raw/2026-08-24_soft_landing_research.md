# Soft-landing: past trial-and-error + literature — raw (2026-08-24)

Workflow `soft-landing-research` (3 sonnet doc readers + 4 sonnet web lenses + sonnet brief). Decision: [docs/95](../95_soft_landing_prescription.md).

## Brief

# Soft-Landing 보상항 결정 브리프 — ankleAB_c2r / ankleRP_c2 (iter 2500)

**대상**: `foot_impact_velocity` (w=-2.0, relu(-v_z), height<0.08m & F<0.02BW 게이트) + `contact_force_cap` 임계값 600→420N/클립 800→560N 재조정, 두 arm(AB/RP) 동일 적용.
**소스**: `mujoco-sim/mjlab/src/mjlab/tasks/velocity/mdp/rewards.py:635-696`, `.../config/pygmalion/env_cfgs.py:246-273` (코드 확인 완료, `PYG_SOFT_LANDING` env var 게이트 — **아직 미가동**).

**TL;DR**: 진단(접지속도 4×human, 하중률 10×human)은 근거가 탄탄하다. 처방의 게이트 형태(height+force 근접장, command-gate)는 문헌 최고 실전 사례(LimX `foot_landing_vel`, 8cm 임계값 완전 일치)와 사실상 동일하다. 다만 (a) 함수형태가 relu-선형이라 우리가 죽이려는 꼬리(p90 1.7-1.8 m/s)에 문헌 사례(LimX 제곱, Olympus clamp)보다 약하게 반응하고, (b) w=-2의 9% 기여도는 "계산값"이지 측정값이 아니며 — 이 프로젝트 역사에서 계산된 기여도와 실측 기여도가 크게 어긋난 전례(forefoot_cop: 설계 의도 무관하게 실측 0.06%)가 있고, (c) 프로젝트 자체가 이미 겪은 최대 리스크는 "약한 생성 항이 tracking에 묻힌다"가 아니라 "새 항이 기존 air_time/foot_clearance와 상충해 셔플로 회귀한다"는 쪽(2026-07-06 findings)이다. §4/§7에 측정 계획을 못박는다.

---

## 1. 과거 시행착오 (연대순)

| 날짜 | 계통 | 문제 | 시도 (항·가중치) | 결과 (수치) | 교훈 | 출처 |
|---|---|---|---|---|---|---|
| 06-22 | gaitfix v3→v4 | ankle_roll(RS00, 5/14N·m) 포화 | v3: `foot_roll_flat` -0.5. v4: 스탠스 0.20→0.24 + foot-body orientation | RMS 110%→(v4) 100%, **peak는 v3·v4 모두 14N·m(100%)에 고정**. CoP-lever 계산: 14N·m/508N=2.8cm=발 반폭과 일치 | RMS는 gait artifact(회복 가능), **peak는 mg×foot 반폭의 물리적 하한**(보상 튜닝으로 못 뚫음) | `docs/reward_research/2026-06-22_03-50`, `2026-06-22_11-00` |
| 06-22 | gaitfix v6 | `base_height_l2`(-1.0@0.85) 과잉구속이 push-off vault 억제 | 가중치 균일 완화 -1.0→-0.25 | CoM bob 1.19→1.46cm (+23%, 여전히 human ~2.5-5cm의 28-58%) | **균일 가중치 완화는 구속의 "형태"를 안 바꿔** 약하다 → floor-only 페널티로 재설계 필요 | `docs/reward_research/2026-06-22_11-30` |
| 06-22 | gaitfix v6 | 정적 forefoot CoP 보상이 효과 없어 보임 | `forefoot_cop` w=0.8 | 실측 기여도 **+0.0251 = 총보상의 0.06%** | **정적/순간 보상은 tracking(+0.74)에 묻혀 죽는다** — 시간적 시퀀스는 시간적 보상으로만 형성 가능. 새 항의 실제 기여도는 반드시 측정, 계산만으로 판단 금지 | `docs/reward_research/2026-06-22_12-19`, `_12-30` |
| 06-22 | gaitfix v7 | 생성 레버 4종 동시 추가 | `cop_progression`+1.2, `base_height_floor`-0.5, `flat_orientation_deadband`±7°, `double_support_bonus`+0.1 | ankle_pitch RMS 26.5→**29.3** (over-drive 가드 위반), gait 거의 안 변함 | 약한 생성 레버 여러 개를 동시에 얹어도 tracking 지배 못 뚫음 → gaitfix 라인 **HOLD**, G1-vanilla 베이스라인 전환 | `docs/reward_research/2026-06-22_12-29-19_gaitfix_v7.md` |
| 06-28 | Menlo/Asimov 블로그 그대로 적용 | air_time+0.5(비행 보상)+ankle_deviation-0.5(타이트) 그대로 이식 | 16kg-다리 로봇용 레시피를 51.8kg 로봇에 그대로 적용 | **GRF peak 1079N(2.1BW)→1991N(3.9BW)**, ankle_pitch 243% 과부하. air_time 기여도 -0.0164=거의 죽음(비행 자체는 원인 아니었음, 진짜 원인은 타이트 ankle 페널티가 저컴플라이언스 착지 유발) | **차용 레시피를 로봇 질량 안 맞고 그대로 쓰면 리워드해킹급 사고** — 채택 금지 판정 | `docs/reward_research/2026-06-28_asimov_reward_asis.md` |
| 06-28 | g1is_dm4340 (`_apply_g1_impact_stable` 기원) | 순수 임팩트 항만 추가 | `foot_landing_vel` -1, `foot_impact_force` -0.005, `knee_straight` -5 (foot-flat/heel-toe 항은 그대로 제거된 채) | ankle_roll RMS 215%(peak sat 50%), ankle_pitch RMS 191%(sat 21%), base_height 0.952=까치발 | **임팩트 항 단독으로는 불충분** — foot-flat 없인 까치발→좁은 지지면→ankle 전부 떠맡음→그대로 포화. 모터를 키워도 나쁜 gait가 늘어난 토크 다 씀 | `docs/experiments/2026-06-28_19-55-27_g1is_dm4340_flat.md` |
| 06-29 | human-ref v5 (`toe_load_stance`) | `clamp(\|τ_toe\|/27,0,1)` 말기-스탠스 게이트 | 굽힘 크기 0.075→0.108rad(증가) **but 최대굽힘 위상 78-95%(swing/관성)** — 목표 50-60%(push-off)와 불일치 | 수동/과댐핑 관절에 직접-토크 보상 = **정적 held-curl로 게임 가능**한 안티패턴(ζ=2.89 확인). 크기는 오르되 타이밍은 그대로 → 겉보기 개선일 뿐 | `docs/reward_research/2026-06-29_toe_use_reward.md`, `_verify_biomech_toe_pushoff_mtp_angle.md` |
| 06-29 | Siekmann v8 (★최대 레버) | `periodic_contact`(phase clock) +1.5 | GRF 비대칭 0.83→**0.18**, GRF peak 8.9BW→**3.1BW**, CoT 2.62→**1.22** | **한 개의 위상-legislating 항이 까치발+절뚝+충격+에너지를 동시에 해결** — 이 프로젝트 보상사 최대 단일 레버 | `docs/experiments/2026-06-29_13-00-01_siekmann_v8_flat.md` |
| 06-29 | Siekmann pushoff v9 | v8 위에 `ankle_pushoff_work`+0.5(80W클램프, 임팩트캡 **없이**) | GRF peak **3.1BW→11.5BW**(5822N), human-likeness 0.14→0.05 | **비캡핑 power/work 보상 = 해킹**: 정책이 공격적 push-off로 파밍. → **"임팩트캡이 push-off 보상보다 먼저"** 순서 원칙 확립 | `docs/experiments/2026-06-29_22-48-47_siekmann_pushoff_v9_flat.md` |
| 07-03 | mjlab B1 | `contact_force_cap` w=-0.005, threshold600/**clip400** | GRF P99 2.45→2.34BW(-19%, 경계) **but peak 오히려 악화**(클립이 큰 스파이크 그래디언트 차단) | **클립이 너무 낮으면 최대 스파이크의 그래디언트를 죽인다** | `docs/experiments/2026-07-03_04-03-01_mjlab_B1.md` |
| 07-03 | mjlab B1w2 | 동일 항, threshold600/**clip800**, w=-0.01 | GRF P99 2.34→**2.05BW**(-27%, 즉시) | 클립 상향이 문제 해결 — **지금 제안도 동일 항의 threshold만 바꾸고 clip비율(threshold의 1.33배)은 유지**해야 같은 함정 재발 안 함 | `docs/62_policy_reward_design_review.md` §1 캐스케이드 표 |
| 07-03 | mjlab B2 | +`thermal_effort` -0.02, Σ(τ/rated)² | GRF P99 2.05→**1.88BW**, ankle_pitch RMS 109→88%, knee 114%(유일 초과) | 토크 재분배(캡과 무관한 축)가 GRF 하락과 별개로 가산 | `docs/experiments/2026-07-03_06-23-45_mjlab_B2.md` |
| 07-03 | mjlab B3 (★ankle 정책서 앵커) | +`periodic_contact`(Siekmann 이식) +1.5, swing-shaping 항 0으로 | GRF P99 1.88→**1.63BW**, 비대칭 0.83→**0.02**, ankle_pitch RMS 113→**47%** | **cap→thermal→clock 고정 순서**로 5단계 누적, GRF 2.45→1.28BW(P2-final까지)까지 어떤 단일 항도 "마법"이 아니었음 | `docs/experiments/2026-07-03_07-34-12_mjlab_B3.md` |
| 07-05 | G1-vanilla 계통 (별도 라인) | 고정주기 Siekmann 클록(1.0s, stance 0.6)이 정지 불가+속도추종 정체(0.32) 유발 | `periodic_contact`+`gait_clock` obs 전면 제거, command-gated `foot_swing_height`/`foot_clearance` 재활성 | track_linear_velocity 0.32(정체)→회복 | **가변 속도 명령엔 고정주기 클록이 안 맞는다** — B3(위 항목)와 다른 계통이라 클록 실패가 재현된 것. 현재 gen21 계통은 클록 없이 command-gated 항만 사용 | `docs/reward_research/2026-07-05_periodic_contact_removal.md` |
| 07-06 | G1-vanilla 계통 | 클록 제거 후 셔플(double-support 49% vs human 20-30%) 재발 | `feet_air_time`(built-in, threshold 0.05-0.5s) w=0→**+1.0**, command-gated | contact toggle율 정상(1.8Hz)이나 DS 49%→air_time 도입으로 개선 | **아무것도 명확한 swing을 강제 안 하면 PPO는 에너지최소해(양발 붙이고 살짝 미끄럼)로 수렴** — "발 떨림"으로 보였던 게 실은 셔플 | `docs/reward_research/2026-07-06_gait_cycle_air_time.md` |
| 07-12 | gen2_bent_p1/p2 (기각) | `stand_still_penalty` -1.0, **절대 임계값** \|v\|<0.15 | 고속(2.5) 추종 67%(게이트 85% 미달), **push 후 재악화**(fcp knee P99 클립 도달, delta+16.6%) | **절대 임계값은 "느리게 기어가기"로 게임됨**(cmd2.5인데 실속 1.44m/s) — stand_still 지표는 좋아 보이나 전체 속도구간 추종은 악화 | `docs/experiments/2026-07-12_gen2_bent_p1.md`, `_p2.md` |
| 07-13 | gen21_bent_p2 (★현재 flat 설계앵커) | 절대→**상대 임계값**(v·cmd_hat < 0.3\|cmd\|)로 단일변인 교체 | 고속 2.5→92%, push delta knee **+0.5%**(vs gen2의 +16.6%), 낙상 fc 0/fcp 0/453 | **절대 임계값 위험을 상대 임계값으로 고침** — 지금 제안의 `height_threshold=0.08m`(절대)·`contact_threshold=7N`(절대)도 같은 게임 가능성 있음(§4 참조) | `docs/experiments/2026-07-13_gen21_bent_p2.md` |
| 07-12 | bentinit A/B (P1→P2 확정) | 착지충격 vs knee토크 트레이드오프 정량화 | bent-knee init | GRF peak -37%(7.52→4.73BW) **but** knee P99 -20%(P2에선 straight의 실속 오염 제거 후 재확인) | **자세로 GRF를 낮추면 knee 부하가 반대로 움직일 수 있다** — 새 `foot_impact_velocity`도 착지속도를 낮추려 정책이 무릎굽힘 크라우치 전략으로 이동시킬 위험, §4에서 감시 대상 | `docs/experiments/2026-07-12_bentinit_ab_result.md` §1-9 |
| **08-24** | ankleAB_c2r/RP_c2 (iter 2500, **현재 제안**) | 접지속도 4×human, 하중률 10×human 진단 | `foot_impact_velocity` w=-2.0, `contact_force_cap` 420N/560N | **미시행** — 게이트: 접지속도 중앙값<0.6m/s, 하중률 중앙값<60BW/s, GRF p90<1.4BW, 추종/낙상 ±10% | 반증가능 예측 명시: "속도항 단독으로 하중률 반토막 → 미벌점 하강속도가 주원인. 아니면 → GRF 임계값 미스캘리브레이션이 지배" | `docs/reward_research/2026-08-24_soft_landing_impact.md` |

---

## 2. 문헌의 soft-landing 항 (formula · weight · gate · robot · deployed?)

| 항 | Formula | Weight | Gate | Robot | 실기 배포 확인 | 출처 |
|---|---|---|---|---|---|---|
| legged_gym `feet_contact_forces` | Σ clip(‖F‖-F_max, min=0) | task-cfg (고정 안 됨) | 항상 on | ANYmal 계통 | Unitree 포크로 실기 배포 (아래) | github.com/leggedrobotics/legged_gym `legged_robot.py:882-906` |
| unitree_rl_gym (동일 함수 포크) | 동일 | 로봇별 config | 항상 on | **Unitree G1/H1/Go2 실기** | ✅ 실기 | github.com/unitreerobotics/unitree_rl_gym |
| Humanoid-Gym/XBotL `feet_contact_forces` | Σ clip(‖F‖-700, 0, **400**) | -0.01 | 항상 on, 페널티 자체에 400N 상한 클립 | XBot-S/XBot-L | ✅ 실기 (arXiv:2404.05695) | github.com/roboterax/humanoid-gym |
| Humanoid-Gym `feet_contact_number` | 위상매칭 +1 / 불일치 -0.3 | +1.2 | gait-phase 게이트 | XBot | ✅ 실기 | 상동 |
| Humanoid-Gym `base_acc` | exp(-‖Δ(v,ω)‖·3) | 0.2 | 항상 | XBot | ✅ 실기 | 상동 |
| Booster T1 `feet_vel_z` | Σ((Δfoot_z)/dt)² | **0 (기본 비활성 배포)** | — | Booster T1 | 배포되었으나 **이 항은 꺼진 채** | github.com/BoosterRobotics/booster_gym `T1.yaml:250-291` |
| IsaacLab `feet_air_time_positive_biped` (G1) | 단일지지 min(in_mode_time), clamp≤threshold | 0.25 | single-stance & \|cmd\|>0.1 | Unitree G1 | 라이브러리/레퍼런스 config (실기 확인은 G1 자체) | github.com/isaac-sim/IsaacLab `.../g1/rough_env_cfg.py` |
| Berkeley Humanoid `feet_air_time` (양측 임계값) | (last_air-min)·first_contact, clamp≤(max-min) | 2.0 (min0.2/max0.5) | \|cmd\|>0.1 | Berkeley Humanoid | ✅ 실기 | github.com/HybridRobotics/isaac_berkeley_humanoid |
| **LimX TRON1 `foot_landing_vel`** (가장 근접한 문헌형) | Σ v_z² · [height<**0.08m** & ¬contact & v_z<0] | **-0.15** | 높이+비접촉+하강 (우리 게이트와 사실상 동일 구조) | LimX TRON1/P1 | ⚠️ 리포는 실기 제품라인 대상이나 **이 정확한 항의 실기 검증은 이 조사에서 미확인** | github.com/limxdynamics/tron1-rl-isaacgym `pointfoot_flat.py:366-421` |
| **Cassie jumping `Ground Impact`** | exp(-α·F_z²) (지수커널) | 5→10 (스테이지별), **착지 후 0** | **위상게이트**: t≤T_J(접근/비행)만 on, 착지 후 off | Cassie | ✅ 실기 zero-shot (1.4m 롱점프 등) | arXiv:2302.09450 Table II |
| **Olympus quadruped `Catch landing`** | **clamp(-v_z, 0, 1)** ← 우리 relu(-v_z)와 거의 동일하나 **상한 클램프 있음** | 미확인(표 열 못 가져옴, gap) | 착지 국면 추정 | Olympus quadruped | ✅ 실기(1.0m 수직점프) | arXiv:2510.24584 Table IV |
| Olympus `Soft impact` | max(0, 1-\|min(0,(a/a_max)·v)\|) | 미확인 | 착지 국면 추정 | Olympus | ✅ 실기 | 상동 |
| Robot Crash Course (낙상, 보행 아님) | -Σ‖w^c·f^c‖²_∞ (부위별 가중 200) | 200 | 낙상 임팩트 창 | 낙상 컨트롤러 | ❌ 실기 배포 미확인 | arXiv:2511.10635 |
| **`feet_contact_momentum`/`feet_impact`/`contact_no_vel` (요청된 정확한 이름)** | — | — | — | — | **어디서도 발견 못함** (GitHub code-search 인증 실패, grep.app 차단, 6회 웹서치 공백) | 미검증 — 사내/비공개 명명일 가능성 |

**핵심 시사점**: 우리 relu(-v_z)·height<0.08m 게이트는 **LimX와 구조적으로 거의 동일**(임계값 0.08m까지 일치)하지만, LimX는 제곱(v_z²)이고 우리는 선형(relu). Olympus는 clamp로 상한을 둔다. 우리만 **무제한 선형** — §4에서 다룸.

---

## 3. 해킹 모드와 방지책

| 증상 | 원인 | 탐지 지표 | 방지책 | 출처 |
|---|---|---|---|---|
| 정지/동작거부(freeze) | 동작비용 항이 tracking 대비 과도 → 가만히 있는 게 국소최적해 | tracking error 급등 + air_time→0 + 명령활성구간 추종률 | 커리큘럼으로 페널티 가중치를 학습 초반엔 낮게, 후반에 상향(k_c^{k_d}) | Hwangbo 2019 (Sci.Robotics), 우리 07-05 `track_linear_velocity` 0.32 고착 사례 |
| 양발 동시 호핑 | 순수 속도추종만으론 단측지지 강제 안 됨 | single-stance duty ≈0/100(정상 40-50%와 괴리) | single-foot-contact 보상(가장 튜닝-불필요) | van Marum et al. arXiv:2404.19173 §IV-B |
| 양발접지 보상이 회복스텝을 처벌 | 정지시 이중접지 보상이 push 회복(필연적 단측 이탈)까지 처벌 | push 직후 낙상률 증가, 회복스텝 억제 | 정지 명령에서는 접촉-무관 상수 보상으로 대체(명령게이트) | van Marum et al. 상동 §IV-B |
| **비캡핑 push-off/파워 보상 파밍** | 임팩트캡 없이 work/power 보상 추가 → 공격적 슬램 후 강한 push-off가 이득 | 보상 기여도 이상치(324 vs 정상 41), GRF 급등 | **임팩트캡을 push-off/파워 보상보다 먼저 도입**(순서 불변 원칙) | 우리 v9(2026-06-29), Principle 5/6, docs/62 |
| **직접 토크/편차 보상의 정적 curl 게임** | 과댐핑 수동관절에서 \|τ\|=k·편차가 정적 유지로 값싸게 채워짐 | 최대굽힘 위상 히스토그램이 목표창(50-60%)과 어긋남 | 상관물(토크) 대신 **원인**(CoP/GRF 분포)을 보상 | 우리 toe_load_stance v5(2026-06-29) |
| **절대 임계값 크리핑(creep-gaming)** | 절대속도 임계값(\|v\|<c)을 "느리게라도 통과"로 충족, 진짜 추종은 포기 | 전체 명령그리드별 추종률(단일 stall 지표만 보면 놓침) | **상대 임계값**(v·cmd_hat < α\|cmd\|)로 전환 | 우리 gen2→gen21(2026-07-12/13) |
| air_time/flight 보상이 무거운 로봇에서 GRF 스파이크 유발 | 비행 자체를 보상 → 로봇 질량 대비 낙하에너지 과다 | air_time 기여도 vs GRF peak 상관, 로봇 질량 교차확인 | 비행-보상 대신 높이/duty 기반 air_time 사용 | 우리 Menlo/Asimov as-is(2026-06-28); Rudin et al. CoRL2021(반대방향 성공사례) |
| air_time 보상이 오히려 **한 걸음도 못 뗌**(frozen) | 임계값/가중치 미스튜닝 (커뮤니티 미해결 리포트) | swing 이벤트 0, air_time obs 고착 | 임계값/가중치 재튜닝 — **미검증, 스레드 내 해결책 없음** | IsaacLab Discussion #1977 (동료검토 아님, 참고용) |
| 정적/순간 보상이 시간적 시퀀스를 못 만듦 | 크기는 맞아도 tracking에 묻힘 | **총보상 대비 기여도 %를 직접 측정**(계산치 신뢰 금지) | 위상/시간 게이트 버전으로 교체하거나 가중치를 기여도 3-5%대까지 상향 | 우리 forefoot_cop(0.06% 실측, 06-22) |
| **[예측, 미관측] `foot_impact_velocity`가 셔플/저클리어런스로 회귀 유도** | 새 항이 조밀(매 스텝)·오래된 `foot_clearance`/`air_time`은 성기다 → swing 진폭을 줄여 게이트(height<0.08 & 하강) 노출 자체를 회피하는 게 더 싸질 수 있음 | **foot clearance 피크·air_time 평균·stride length**를 impact-velocity와 함께 삼중 확인 — 속도는 내려갔는데 clearance/stride도 같이 내려가면 셔플 회귀 | clearance/air_time 가중치 상향 또는 impact 항을 스윙 말기(위상)로 추가 게이트 | 우리 2026-07-06 셔플 전례로부터 유추(직접 관측 아님, §4 참조) |

---

## 4. 우리 처방 평가

**형태 자체는 known-good에 가깝다.** relu(-v_z), height<0.08m 게이트는 LimX `foot_landing_vel`(임계값 0.08m 정확히 일치)과 구조적으로 동형이고, command-gate(0.05) 관행은 프로젝트 자체 컨벤션(soft_landing과 동일 패턴, 07-05 수정 이후 표준)과 일치한다. 두 arm에 동일 적용해 A/B 단일변인성을 지킨 것(`env_cfgs.py:259-273`)도 맞다.

**다만 세 가지가 검증되지 않은 채 남아 있다:**

1. **함수형태 — 선형 vs 제곱/클램프.** 우리 relu(-v_z)는 무제한 선형: 1.5m/s 슬램에 -3/step. LimX는 v_z²(제곱 — 꼬리에 더 강하게 반응), Olympus는 clamp(-v_z,0,1)(포화 — 큰 위반과 아주 큰 위반을 구분 안 함). 게이트 목표가 **중앙값과 p90을 모두** 명시(§7)하는데, 지금 형태는 중앙값 개선에 유리하고 p90/max 꼬리(AB p90 1.69, RP 1.82, 최댓값 미기재)엔 상대적으로 약하다. **제곱형 relu(-v_z)²를 대안으로 시험 권고** — 기존 원칙(docs/62 §5 "리워드 캡을 너무 낮게 잡으면 큰 스파이크 그래디언트가 죽는다")은 **보상 상한 클립**에 관한 것이고 **성장하는 페널티**엔 적용 안 되므로 상충 없음.
2. **가중치 9% 기여도는 계산값, 실측 아님.** 노트 자체가 "estimated"라 명시. forefoot_cop 전례(계산상 유의미해 보였으나 실측 0.06%)를 감안하면, **iter+500 시점에 `Metrics/foot_impact_vel_mean`과 총보상 대비 실제 기여도 %를 반드시 측정**해야 한다(B1/B2/B3 때처럼).
3. **절대 임계값 두 개(`height_threshold=0.08m`, `contact_threshold=7N`)가 게임 가능한 경계다.** gen2의 절대-임계값 creep-gaming 전례가 이 프로젝트에서 실제로 일어났던 만큼, "발을 0.08m 문턱 바로 위에서 서성이다가 문턱을 넘는 순간만 감속" 같은 경계선 준수 패턴이 나타나는지 반드시 확인 필요.

**측정 npz에서 볼 지표(우선순위순):**
- **foot clearance(스윙 피크 높이) + air_time 평균 + stride length** — 셋이 함께 낮아지면 셔플 회귀(§3 마지막 행), impact velocity만 낮아지고 셋은 유지되면 진짜 개선.
- **contact duty(스탠스:스윙 비)** — human ~60:40, 07-06 셔플 실패시 double-support 49%였던 전례와 비교.
- **knee 토크 P99/RMS** — bent-init A/B(docs/55)처럼 착지충격 저감이 무릎으로 전가되는지 확인. 현재 gen21 앵커의 knee P99 112.4(94% of clip)가 이미 유일한 binding 관절이라 추가 여유가 크지 않음.
- **tracking error(error_vel_xy/yaw), fall rate** — 게이트 자체에 이미 ±10% 조건 포함.
- **stand-still fraction / cadence(step frequency)** — "착지 직전 망설임"으로 스텝 주기가 늘어나는지(낙상률엔 안 잡히는 은닉 실패모드).
- **height-at-contact 히스토그램** — 0.08m 문턱 근처에 비정상적으로 몰리면 경계-게임 신호.

**해킹 시 변경안(양방향, 상충 주의):**
- **게이트 미충족(효과 부족)** → 처방 자체의 계획대로 w -2→-4, threshold 0.08→0.12.
- **셔플/클리어런스 붕괴(과잉 억제)** → 반대 방향: threshold를 낮추거나(더 좁은 근접장만 처벌), `foot_clearance`/`air_time` 가중치를 동반 상향, 또는 스윙 위상(말기 1/3) 게이트를 추가해 조기 스윙 잡음에 반응 안 하게.
- **경계-게임(절대 임계값)** 확인되면 gen21의 해법을 그대로 이식: 절대(0.08m/7N) 대신 상대(예: 발-지면 거리를 스텝길이 또는 최대 클리어런스 대비 비율)로.
- 자원이 허락하면(현재 RAM 15GB 실측 상한 하에서), **B1/B1w2/B2/B3처럼 단일변인 캐스케이드**로 분리 확인 — `foot_impact_velocity`만 켜고 `contact_force_cap` 재조정은 그대로 둔 짧은(2-4k iter) 격리런으로 두 메커니즘 중 무엇이 지배적인지 노트 자체의 반증가능 예측을 실제로 닫는 것을 권고(선택사항, 메인 A/B는 계획대로 진행해도 무방).

---

## 5. 사람/로봇 기준값

| 지표 | 사람 (출처) | 우리 로봇 (iter2500, AB/RP) | 우리 설계앵커 (docs/65) |
|---|---|---|---|
| 접지 수직속도 | **불일치 있음**: 컨텍스트 기준 0.1-0.4m/s (출처 미상, 미검증) vs Price et al. 슈즈별 0.18-0.36m/s(PMC4101391) vs **Baines et al. 2018 맨발 1.3m/s 보행 시 0.39-0.78m/s(평균 0.57m/s, PMC6023236)** | AB 1.34/1.69m/s(중앙/p90), RP 1.54/1.82m/s | 게이트 목표 중앙값<0.6m/s — **Baines 맨발 평균(0.57)과 이미 근접**, 컨텍스트 하한(0.1-0.4)보다 훨씬 관대 |
| GRF 1차 피크 | 저속보행 ~1.0BW → 워크런전환(1.8-2.2m/s) ~1.39-1.5BW(Li 2001 ISB, 직접 원문 확인: 13.6N/kg=1.39BW; Nilsson&Thorstensson 1989: 1.0→1.5BW) | AB 1.40/1.67BW(중앙/p90, max2.17), RP 1.55/1.89BW(max2.01) — **측정 명령은 0.4/0.8m/s(저속!)** | flat gen21p2_fc: RMS0.70BW/P99 1.31BW(fcp 1.40BW)/peak6.36BW |
| 하중률 | 8-30BW/s(Keller et al. 1996, 보행~조깅~러닝 전 구간, 보행 전용 하위구간 미분리·미검증) | AB max 155/266BW/s(중앙/p90), RP 158/207BW/s | — |
| 1차피크 도달시간 | **두 개념 혼동 주의**: (a) 매끈한 체중수용 피크 ~100-130ms(Li 2001, stance의 20-24%) — 컨텍스트의 "100-150ms"와 일치 (b) 일부 보행자만 보이는 날카로운 힐스트라이크 과도스파이크 12-23ms(Baines 2018) — **완전히 다른 현상, 혼동 시 오해석** | AB 25ms, RP 10ms | — |
| 발목/GRF 비대칭 | — | (참고) Siekmann v8 이후 0.02-0.18 수준으로 정상화된 전례 | — |

**⚠ 컨텍스트 재검토 필요**: 위 표의 첫 행처럼, "human 0.1-0.4 m/s"라는 우리 문서의 기존 기준값이 두 개의 독립 문헌 출처(신발 0.18-0.36, 맨발 0.39-0.78) 어느 쪽 중심값과도 안 맞고 둘 다보다 낮다. 또한 GRF 행처럼, AB/RP는 **저속(0.4/0.8m/s) 명령에서 측정**되었는데 인간 비교치로 "1.0-1.2BW"(중속 보행 표준값)를 쓰면 **비교가 오히려 관대**하다 — Nilsson&Thorstensson 추세선을 외삽하면 0.4-0.8m/s 인간의 1차피크는 1.0BW보다 낮을 가능성이 커서, 로봇의 실제 미스매치는 명시된 "1.3-1.6배"보다 클 수 있음(외삽, 직접측정 아님— 검증 권고).

---

## 6. 시뮬 요인 — 우리 수치를 부풀리고 있는가?

코드 직접 확인(2026-08-24 이 브리프 작성 중 grep/read):

| 파라미터 | 발-지면 접촉 (foot_capsule) | 발목 폐루프 constraint | MuJoCo 기본값 |
|---|---|---|---|
| solref | **미설정 → 기본값 그대로** | `0.002`→refsafe로 10ms 강제 | `0.02 1` |
| solimp | **미설정 → 기본값 그대로** | `0.999 0.9999 0.0001` | `0.9 0.95 0.001 0.5 2` |
| condim/cone/impratio | 미설정(기본 3/pyramidal/1.0) | 해당없음(equality) | 3/pyramidal/1.0 |
| 물리 dt | 5ms(200Hz) | 5ms | — |
| 제어 dt | 20ms(50Hz, decimation=4) | 동일 | — |

(발-지면: `pygmalion_v2.xml:3-16,110-114,160-164`, `scene.xml` grep 공백 확인; 발목루프: `pygmalion_v3_printed_loop.xml:316-319`; 옵션 적용부: `mjlab/sim/sim.py:88-135`; dt/decimation: `velocity_env_cfg.py:449,454`)

1. **발-지면 접촉 솔버는 MuJoCo 순정 기본값 그대로**이며, 이는 이 브리프가 훑은 legged_gym/IsaacLab/Humanoid-Gym 등 **외부 배포 스택 전부도 오버라이드 안 하는 값**이다 — 우리만 유독 무르거나 단단하지 않음. 발이 5개 평행 캡슐(폭 1cm, `foot_capsule` 클래스)로 구성된 "박스형 창"이라는 점은 평평 착지 시 다중 근-동시접촉을 만들 수 있어 이론적으로 첫 몇 ms의 힘 상승을 실제보다 날카롭게 만들 가능성이 있지만, **이 프로젝트에서 이 가설 자체는 격리 테스트된 적이 없다** (미검증).
2. **실제로 스윕된 것은 발-지면이 아니라 발목 2-RSU 폐루프 equality constraint다**(`docs/94_loop_constraint_stiffness.md`, 이 브리프 작성 중 원문 79줄 전체 확인). 이 스윕은 "부드러운 구속(0.9/0.95 기본값)이 오히려 더 튄다" — 하지만 이건 **루프 처짐/토크 잭터/vx 추종오차**(RMS 8.37mm, |Δτ|p99 18.0N·m, vx오차 0.78 vs 현재 0.999 설정의 0.08mm/11.4N·m/0.13)에 관한 것이지, 발-지면 GRF의 "바운스"가 아니다. 즉 이 결과는 **"발목 메커니즘을 무르게 하면 착지가 나아진다"는 가설은 기각**하지만, **"발-지면 접촉솔버가 원인"이라는 가설은 아예 테스트되지 않은 채 남아 있다** — 내부 노트의 "sim numerics 아님" 결론은 발목-루프 축에서만 닫힌 것이지 발-지면 축까지 닫힌 게 아니다. 이 구분을 정확히 하는 것이 이 섹션의 핵심 시정사항.
3. **복원계수(restitution)는 어디에도 명시적으로 설정되지 않음**(solref가 양수=표준 스프링-댐퍼 형태, 음수/직접강성 미사용) — 모델에 "인위적 탄성"은 없다.
4. **측정도구 자체의 시간축은 일관적이다**: `impact_probe.py`는 `dt=mj.opt.timestep`(=0.005s)를 그대로 읽어 200Hz로 매 서브스텝 기록하고, "50Hz 센서뷰"는 `F[::4]`로 명시적으로 서브샘플링한다(`tools/robot_model/loop_tests/impact_probe.py:50,58,82-83`) — 이는 학습 시 실제 decimation=4와 정확히 일치, 측정-학습 간 시간축 불일치는 없음.
5. **다만 200Hz(물리) vs 50Hz(보상이 보는 것) 자체가 구조적 사각지대다**: 진짜 순간 최대(AB max 2.17BW)의 상당 부분이 50Hz로 서브샘플된 신호(p99 1.41BW)에 안 잡힌다 — 이건 "시뮬 아티팩트"가 아니라 **어떤 보상항이든 겪는 근본적 샘플링 한계**이며, 정확히 이 때문에 `foot_impact_velocity`(50Hz로도 잘 보이는 완만한 접근속도 신호)가 `contact_force_cap`(50Hz로 부분적으로 놓치는 임펄스형 신호) 단독보다 원리적으로 유리한 설계다 — **처방의 항 선택 자체를 정당화하는 근거**로 명시해도 좋다.
6. **미검증 잔여 축**: 훈련은 GPU `mujoco_warp`, 측정도구(`impact_probe.py`, `device='cpu'`)와 §94 스윕(CPU 8s)은 CPU MuJoCo — GPU/CPU 물리 백엔드 간 float32 정밀도·솔버반복 수렴 차이가 수치를 미세하게 흔들 가능성은 이 조사에서 확인도 반증도 못함(낮은 우선순위 잔여 리스크로 플래그).

**종합**: 증거의 무게는 "정책이 만든 진짜 행동" 쪽으로 기운다(외부 표준과 동일한 접촉솔버, 명시적 복원계수 없음, 유일하게 스윕된 강성축은 반대방향으로 악화). 그러나 "발-지면 솔버 자체가 원인이 아니다"는 **직접 검증된 적 없는 추론**이다 — 이 soft-landing 개편 전체를 신뢰하기 전에, §94와 같은 방법론(PYG_-style env var 오버라이드)으로 **발-지면 접촉의 solref/solimp 자체를 한 번 스윕**하는 저비용 확인을 선택적으로 권고한다.

---

## 7. 권고 게이트 수치

| 지표 | 현재(iter2500) | 목표 게이트 (+4k iter) | 미달 시 에스컬레이션 |
|---|---|---|---|
| 접지속도 중앙값 | AB 1.34 / RP 1.54 m/s | **<0.6 m/s** | w -2→-4 |
| 접지속도 p90 | AB 1.69 / RP 1.82 m/s | (명시 안 됐으나 §4 권고: 병행 추적) | 함수형 relu→relu² 검토 |
| 하중률 중앙값 | AB 155 / RP 158 BW/s(max) | **<60 BW/s** | height threshold 0.08→0.12 |
| GRF p90 | AB 1.67 / RP 1.89 BW | **<1.4 BW** | contact_force_cap 추가 재조정 |
| 추종/낙상 | 기준 | **±10% 이내** | 원복 후 재설계 |
| **(§4 추가 권고, 게이트에 없던 것)** foot clearance·air_time·stride length | 베이스라인 필요 | 셋 다 impact-velocity와 동시에 낮아지지 않을 것 | 셔플 신호 시 clearance/air_time 가중치 동반 상향 또는 위상게이트 추가 |
| **(§4 추가 권고)** foot_impact_velocity 실측 보상 기여도 | 계산값 9%(미측정) | 측정치가 계산값과 10배 이상 어긋나면(forefoot_cop 전례) 가중치 전면 재산정 | — |
| **(§4 추가 권고)** height-at-contact 히스토그램 | — | 0.08m 문턱 근처 비정상 집중 없음 | 절대→상대 임계값(gen21 방식) 전환 |

두 arm 모두 iter ~2700-3200/32000(8-10%) 시점 — 보상 변경 시 A/B 공정성을 위해 **양쪽 다 재시작 필요**(결정은 사용자 몫, `docs/reward_research/2026-08-24_soft_landing_impact.md` 명시).

## Internal findings

- **Soft-landing / foot impact velocity (2026-08-24, most recent)** | docs/reward_research/2026-08-24_soft_landing_impact.md
  - what: Symptom: ankleAB_c2r/ankleRP_c2 (iter 2500, vx 0.8 stage) stomp the ground. Diagnostic tool tools/robot_model/loop_tests/impact_probe.py, physics 200Hz, 0.4/0.8 m/s x10s.
  - tried: Root causes identified: (1) soft_landing weight is -1e-5 = effectively off (single 50Hz first-contact sample, weak even when on). (2) contact_force_cap threshold 600N was sized for the 51.5kg robot (BW 505N = 1.2BW); the printed/current robot is BW 347N so 600N=1.73BW and clip 800N=2.3BW -- p90 peaks (1.67-1.89 BW) barely graze the threshold, so it barely fires. (3) foot_clearance/swing_height (ta
  - result: Peak magnitude (1.4-1.6 BW) is NOT the real problem -- landing speed (4x human) and loading rate (10x human) are, and no existing reward term sees either.
  - numbers: Foot pre-contact vertical velocity: AB 1.34/1.69 m/s (median/p90), RP 1.54/1.82 m/s vs human 0.1-0.4 m/s (4x human). Vertical GRF peak: AB 1.40/1.67 BW (max 2.17), RP 1.55/1.89 BW (max 2.01) vs human 1.0-1.2 BW. Loading rate max dF/dt: AB 155/266 BW/s, RP 158/207 BW/s vs human 10-20 BW/s (running 50
- **Prescribed fix for soft landing (2026-08-24, not yet trained)** | docs/reward_research/2026-08-24_soft_landing_impact.md
  - what: New reward foot_impact_velocity + rescaled contact_force_cap, applied identically to both running arms (ankleAB_c2r, ankleRP_c2) to keep the A/B single-variable.
  - tried: 
  - result: Not yet run -- gate defined for +4k iters: impact-velocity median <0.6 m/s, loading-rate median <60 BW/s, peak p90 <1.4 BW, tracking/falls within +/-10% of current. Miss -> w -2 to -4, h0 0.08 to 0.12.
  - numbers: foot_impact_velocity (new): sum_feet relu(-v_z) * [z_foot<0.08m AND F<0.02BW], command-gated, weight w=-2.0 (measured mean 0.04 m/s/foot -> ~-0.16/step = 9% of tracking's +1.8; a 1.5 m/s slam gives ~-3/step). contact_force_cap: threshold 600->420N (1.2BW), clip 800->560N (BW rescaled from 505N to 34
- **periodic_contact fixed clock removed (2026-07-05)** | docs/reward_research/2026-07-05_periodic_contact_removal.md
  - what: Symptom: robot cannot stand still (steps in place even at command=0), and track_linear_velocity never converges (stuck ~0.32 across a 40k-iter run) while track_angular converges (0.77) -- fixed-frequency Siekmann clock (period 1.0s, stance 0.6) fighting variable cadence needed for variable vx.
  - tried: Contrast with g1 vanilla config which has NO periodic_contact and achieves both standing and tracking via command-gated foot terms -- used as the working reference to diagnose the pygmalion-specific regression.
  - result: Decision: remove periodic_contact (+1.5) reward and gait_clock obs entirely; re-enable command-gated foot_swing_height (base -0.25) and foot_clearance (base -2.0), matching g1-vanilla's emergent-gating approach (command_threshold 0.05 on all foot shape terms).
  - numbers: R2 40k-iter run: track_linear_velocity ~0.32 (flat), track_angular_velocity 0.77, periodic_contact contribution 0.58. periodic_contact command_threshold was 0.05 (too low, gates on even tiny commands); gait_clock obs cycles with NO gate at all.
- **Gait cycle didn't form after periodic_contact removal -> feet_air_time added (2026-07-06)** | docs/reward_research/2026-07-06_gait_cycle_air_time.md
  - what: After removing periodic_contact, robot regained standing/tracking but developed a shuffle: feet vibrate, no clean gait cycle. Measured on v2_flat_demo at vx=1.0.
  - tried: Fix: turn on feet_air_time (mjlab built-in, was weight 0) at weight +1.0, command-gated (threshold 0.5), rewarding current_air_time in [0.05,0.5]s. Kept all impact-layer terms and did not touch action_rate/gain in this run to isolate the air_time effect (single-variable change).
  - result: Root cause: nothing forces a clear swing phase -> PPO converges to the energy-minimum solution of keeping both feet down and shuffling forward a little (DS 49%). 'Foot vibration' the user saw was actually indistinct short-step shuffling, not contact chatter.
  - numbers: Contact toggle rate: L 3.7/R 3.3 per second (~1.8Hz, normal cadence, not chatter). Stance runs <5 frames (chatter): 0 (none). Double-support: 49% (normal human 20-30%, so ~2x too much = shuffle). Flight phase: 0% (walk, normal). Ankle_pitch stance angular velocity: 19 rpm (low, not oscillating).
- **G1 reward -> foot trembling/instability/saturation root-cause (2026-06-28)** | docs/reward_research/2026-06-28_g1_trembling_saturation.md
  - what: User observation: G1+impact-reduction config produces far more foot trembling, instability, and actuator saturation than the gaitfix lineage. Root-cause via reward-config diff (adversarial: DR, PD gains, network ruled out identical).
  - tried: Minimal fix applied: add ankle to dof_acc_l2 range, action_rate_l2 -0.005->-0.008, actuator swap (ankle_roll RS00 14/5Nm -> DM-J4340-2EC 40/14Nm) as the structural saturation fix rather than over-penalizing torque (which risks 'timid gait'). Held back (risk of breaking clean walking): foot_flat_orientation, lateral_foot_placement, wide stance.
  - result: Smoking gun = H2: G1's dof_acc_l2 range excludes ankles (only hip+knee), while gaitfix explicitly includes ankles -- gaitfix code comment: 'ankles excluded -> high-freq buzz, >5Hz torque energy ankle 17-23%'. Confirmed contributing: H1 (weak action_rate), H3 (10x weaker torque penalty -> saturation), H4 (G1 lacks foot_flat_orientation/lateral_foot_placement/wide feet_distance/torque_soft_limit_ank
  - numbers: Torque chatter dtau/dt (N.m/s) / rev-per-second: g1vanilla ankle_roll 179 / 13.5, ankle_pitch 927, knee 1038; g1van_full 195/14.0, 731, 1186; gaitfix_v7 119/6.8, 305, 477; gaitfix_v4 96/7.2, 279, 475 -- G1 is 2-3x gaitfix. Saturation: G1 ankle_roll RMS 169-200% of rated, sat 9-42%, vs gaitfix 101-11
- **Menlo/Asimov blog reward applied verbatim -- flight/GRF spike reward-hacking incident (2026-06-28)** | docs/reward_research/2026-06-28_asimov_reward_asis.md
  - what: Applied a blog's reward philosophy faithfully (feet_air_time real-airtime variant +0.5 for flight, tight ankle joint_deviation -0.5, minimal shaping, no swing_height/cop/foot_flat). Blog's robot has 16kg legs; ours is 51.8kg.
  - tried: This is a documented reward-hacking-adjacent incident: applying an unadapted borrowed reward recipe (air_time for flight, tight ankle pose tolerance) to a heavier robot directly produced oversized GRF impact and actuator overload; rejected.
  - result: Confirmed unsuitable for the load-measurement goal: air_time/tight-ankle reward recipe caused impact spike (3.9xBW) and ankle overload, even though tiptoe was (unexpectedly) reduced. Verdict: proceed with v2 (swing_height+foot_flat) without air_time or tight-ankle deviation.
  - numbers: Predicted then measured: GRF peak 1991N = 3.9xBW (asimov run) vs g1is baseline 1079N = 2.1xBW -- entered the 1.5-2.7kN HW breakage range, invalidating the low-impact load-measurement goal. air_time contribution measured DEAD at -0.0164 (flight itself only 1.3%, so the mechanism predicted -- flight c
- **heel-toe stride fix -- tiptoe/shuffle root cause + swing_height fix + toe collision bug (2026-06-28)** | docs/reward_research/2026-06-28_heeltoe_stride_fix.md
  - what: g1is_dm4340_flat model developed tiptoe-shuffle (ankle RMS 200% saturated). 6-agent adversarial workflow, 136 web tool-uses.
  - tried: v2 fix: add toe_link collision capsules (3 per foot, primitive, flush with sole rake) via robot.xml + re-convert USD; add full-axis foot_flat_orientation (roll AND pitch) at -0.5 to directly penalize stance-phase tilt; raise swing_height weight -20->-30. DROP list (re-stacking banned): lateral_foot_placement, base_height_floor, double_support_bonus, power_cot, ankle_pushoff_work, feet_lateral_sepa
  - result: Phase1: ADD feet_swing_height = -20 * sum((foot_z - h_target)^2) * not-contact (Unitree G1-verified weight -20@0.08); DEMOTE feet_air_time 0.25->0.0. Phase1 alone (swing_height -20@0.12) FAILED for 2 reasons found afterward: (1) swing_height is only ~1% of reward vs tracking, and only constrains the swinging foot -- can't fix stance-phase plantarflexion tiptoe; (2) toe_link had NO collision geomet
  - numbers: feet_air_time_positive_biped contribution +0.0096 = dead (zero gradient) since it only rewards single-stance duration clamped at 0.4s threshold, not stride.
- **Menlo/Asimov blog philosophy review -- item-by-item literature check (2026-06-28)** | docs/reward_research/2026-06-28_menlo_blog_review.md
  - what: 8-agent, 187-web-tool-use adversarial review of the blog's reward/obs/DR/toe philosophy before adopting it.
  - tried: Adopted from blog: clock-free locomotion (already our lineage), gentle-feet GRF/impact penalties (QuietWalk squared-GRF), ang-vel normalization. Rejected: air_time/flight, blog's exact ankle pose tolerance (HW-specific to their parallel-RSU ankle), ground-truth-velocity-removal claims (blog anecdote, no peer-reviewed ablation).
  - result: Blog's air_time +0.5 (flight reward) explicitly REJECTED for our robot: 'blog's air_time +0.5 (flight-inducing) is for a 16kg-leg robot -- for our 51.8kg robot this maximizes landing GRF, directly opposite our low-impact goal. Adoption prohibited.' Also flagged: blog's 'gait clock removal' is a non-action for us (already clock-free); limp should be solved via symmetry augmentation, not a clock (a 
  - numbers: QuietWalk (arXiv 2604.23702): squared-GRF penalty reduces footstep sound ~7dB.
- **Gait-emergence literature synthesis -- Siekmann periodic contact as top lever (2026-06-29)** | docs/reward_research/2026-06-29_gait_emergence_siekmann.md
  - what: User-provided deep-research report + internal v-series review on how human gait emerges in RL, focused on fixing persistent tiptoe.
  - tried: Staged plan: Stage0 base_height+tracking (kept) -> Stage1 Siekmann periodic_contact+clock obs (remove swing_height/foot_flat, superseded) -> Stage2 symmetry loss -> Stage3 impact cap (soft ~700-900N, hard 1.5kN) + energy penalty -> Stage4 stride/push-off (terminal-stance 40-60% gated ankle-power burst, NOT un-timed toe-deflection) -> Stage5 DeepMimic-lite if still not natural enough (AMP deferred,
  - result: 3-factor recipe for human-like stride (none alone sufficient): (1) geometric anchor (base_height + leg-extension constraint) already present; (2) phase-clocked periodic contact-schedule reward (Siekmann) = highest leverage, legislates stance/swing rhythm, fixes heel-strike-to-toe-off timing AND L/R limp simultaneously; (3) energy/mechanical-work penalty (-|tau.qdot|), subordinate to tracking.
  - numbers: Siekmann periodic reward: stance:swing ratio ~60:40, cycle ~100-120 steps/min (T~1.0s). Target detection metrics: toe-off converge to ~60% phase, stance:swing -> 60:40, GRF asymmetry 0.83->>0.95, 8xBW spike removal target, impact cap soft ~700-900N / hard 1.5kN (BW=508N).
- **Human gait reference (contact-phase DeepMimic) v3-v7 progression -- 8xBW GRF and limp (2026-06-29)** | docs/reward_research/2026-06-29_human_gait_reference.md
  - what: Weak penalty terms (foot_flat, swing_height) plateaued (e.g. foot_flat_orientation -0.046@iter500 -> -0.051@1000, never converging to 0) because tracking reward dominates. gait_humanlikeness.py tool built: hip range_ratio only 0.02-0.05 (2-5% of human ROM) confirming shuffle quantitatively.
  - tried: toe_load_stance = clamp(|tau_toe|/27,0,1) gated to terminal single-support -- increased toe bend magnitude but not timing, an early sign of the direct-torque-reward antipattern later formally rejected.
  - result: AMP ruled infeasible for our stack (rsl_rl 2.3.3 has no discriminator; IsaacLab AMP is skrl+direct, incompatible with our manager-based env; mocap mismatched to our passive-toe morphology). Recommended and adopted: contact-phase-indexed DeepMimic soft tracking (gait_reference_tracking, sagittal-only hip_pitch/knee/ankle_pitch, weight ~+1.0, k~2) + mechanical_power penalty (-Sigma|tau*omega|, weigh
  - numbers: v3 (human-ref, no base_height): base height 0.926, tiptoe persists, unstable. v4 (+base_height): base 0.851, stable 57 cycles, hip corr +0.6-0.7 -- tiptoe FIXED but range_ratio 0.29 (amplitude), asymmetry 0.83, GRF 8xBW remain. v5 (+toe_load_stance): toe bend 0.075->0.108 (more flexion) but wrong ti
- **tiptoe root cause = base_height regression when switching gaitfix->G1 (2026-06-29)** | docs/reward_research/2026-06-29_tiptoe_regression.md
  - what: User: 'gaitfix lineage had figure-8 walking but never tiptoe; tiptoe is critical, find the ROOT cause via regression, not another reward patch.'
  - tried: Fix applied: restore base_height_l2 (weight -1.0, target 0.85) into the shared _apply_g1_impact_stable base class so ALL downstream configs (g1is/dm4340/asimov/human-ref) inherit it, not just human-ref. Mechanism: without base_height, PPO extends the legs for velocity-tracking reach -> only way to keep feet on ground is ankle plantarflexion (tiptoe); with base_height pinned to 0.85, legs stay bent
  - result: Workflow (17 agents) ranked causes: base_height removal ~75% of the regression, lin_vel_z_l2 (-0.2->0) ~10% (amplifier), missing swing clearance ~8%, weak ankle/action_rate regularization ~4% (already fixed), model swap ~3% (later aggravator, ruled out as confound via timing evidence -- first tiptoe run used the SAME old mesh feet as flat-walking gaitfix, so the regression tracked the reward chang
  - numbers: Base height measured: gaitfix v5/v6/v7 = 0.803/0.825/0.828 (flat-footed) vs g1is_dm4340 = 0.952 (tiptoe); v2(foot_flat) = 0.738. G1VanillaRewards code comment explicitly lists removed terms: 'NO forefoot_cop / ankle_pushoff / cop_progression / foot_roll_flat / lateral_foot_placement / feet_distance 
- **toe-use reward design -- direct torque reward banned as antipattern (2026-06-29)** | docs/reward_research/2026-06-29_toe_use_reward.md
  - what: 17-agent literature synthesis on how to get emergent toe use without gaming it.
  - tried: Recommended stack order (hard prerequisite chain): (1) Siekmann periodic_contact+clock backbone FIRST (=v8, done) -- removes mid-swing inertial toe-bend failure mode; (2) THEN ankle_pushoff_work (+0.5) as the CoP-forward engine; (3) THEN cop_progression (+1.2), re-gated to Siekmann's terminal-stance clock window (phase 0.45-0.6) rather than contact-time proxy; (4) THEN power_cot. Explicit DO-NOT-A
  - result: Core verdict: '|tau_toe| reward is an antipattern -- passive so tau=k*deflection is just a correlate of roll, AND can be gamed by static toe-curl (over-damped toe makes held curl cheap). v5 (toe_load_stance) is exactly this failure -- flexion MAGNITUDE increased but TIMING stayed wrong.' Correct approach: reward the CAUSE (forefoot GRF/CoP progression), let toe deflection be an emergent byproduct.
  - numbers: Toe spring k~=60 N.m/rad matches human MTP (56-60 per Nature Sci Rep 2025). cop_progression weight +1.2, ankle_pushoff_work +0.5 (clamp to 80W, gated). forefoot_cop (static fraction, weight 0.8) contributed only 0.06% of total reward in v6 (measured, see toe rollover notes).
- **Adversarial verify: normative ankle angle claim had wrong sign at mid-stance (2026-06-29)** | docs/reward_research/2026-06-29_verify_ankle_normative_angles_torque.md
  - what: A sourced claim about ankle sagittal trajectory + peak torque was checked against primary biomechanics literature before being used as a DeepMimic tracking target.
  - tried: Action before implementing: dig up a real normative curve (Winter table / Perry Fig 8-8) and digitize it rather than trust the prose claim.
  - result: Verdict: 'PARTIALLY supported.' Torque number and rollover direction are sound and usable; but 'encoding the angle timeline verbatim as a tracking target would train an ANTI-human mid-stance and a too-early/too-deep push-off -- directly threatens the human-like + low-energy goal.' Also caught a fabricated/misattributed reference (Huang et al. title wrong; PMC4664043 does not report 1.5 N.m/kg).
  - numbers: Correct skeleton: IC ~0 deg (not 7-10 deg dorsiflexed as claimed) -> loading-response plantarflex to ~-5 deg -> controlled dorsiflexion RISING through midstance to terminal-stance peak dorsiflexion ~+10 deg @~48% (claim said plantarflex ~5-10 deg here -- SIGN REVERSED) -> powered plantarflexion to ~
- **Adversarial verify: MTP push-off angle target (35-45deg) is physically impossible on this robot (2026-06-29)** | docs/reward_research/2026-06-29_verify_biomech_toe_pushoff_mtp_angle.md
  - what: A claim recommending phase-gated toe reward targeting 35-45deg MTP dorsiflexion at 50-60% gait was checked against robot geometry.
  - tried: toe_load_stance (docs/22, clamp(|tau_toe|/27,0,1) terminal-stance gate) explicitly re-flagged as the exact rejected mechanism. Also flagged: v7's rejected candidate (b) 'toe FLEXION late-stage gate' was explicitly rejected in the 2026-06-22_12-19 note for the same static-curl-gaming reason. Correct approach re-affirmed: cop_progression (indirect CoP/load reward) + periodic_contact, not a direct to
  - result: Verdict: supported=FALSE. The 35-45deg angle target is (a) physically impossible on our toe geometry (ceiling ~21deg), (b) based on the wrong reference value (assisted ROM, not gait-dynamic ROM), and (c) its implied mechanism (direct phase-gated toe-deflection/torque reward) is a PROVEN reward-hacking antipattern already tried and rejected (toe_load_stance increased bend magnitude, not timing; and
  - numbers: robot.xml: toe hinge at y=-0.192m from foot_link, toe segment length only 6.5cm (y -0.065..0), spring k=60 N.m/rad. theta=M/k, M=Fz*d_cop, d_cop<=toe length. At measured forefoot Fz=340N and toe length 6.5cm: absolute physical ceiling theta_max ~21 deg (all load at tip). Even at Fz=560N (1.1BW) with
- **Adversarial verify: windlass-stiffness premise wrong but CoP-progression prescription confirmed anyway (2026-06-29)** | docs/reward_research/2026-06-29_verify_biomech_windlass_stiffness_cop.md
  - what: A claim about Hicks windlass mechanism (arch stiffness +10-20%, fascia strain 2-4%, energy 0.05-0.1J) recommending CoP-progression reward was checked against the primary source it cited.
  - tried: None new -- confirms existing cop_progression/periodic_contact stack; explicitly warns not to cite the windlass-stiffness premise since it's factually wrong.
  - result: Verdict: supported=FALSE for the premise (windlass-stiffness claims contradict their own cited source and don't apply -- our robot has no plantar fascia/arch/intrinsic muscles at all, so windlass coupling doesn't exist in the model), but the IMPLICATION (CoP-progression reward is the only real lever, not toe-stiffness tuning) is SOUND and was independently already adopted (cop_progression +1.2, pe
  - numbers: Claim cited 'Ker JRSI 2009' for +10-20% arch stiffness gain; actual paper (Welte et al. 2018, PMC6127178) found the OPPOSITE -- windlass engagement makes the arch MORE flexible (stiffness decreases). Claim's energy figure (0.05-0.1 J) off by an order of magnitude vs Welte's mJ/kg values (~1.1J retur
- **Adversarial verify: soft phase-reference reward (clockless normative curve tracking) risks mode collapse (2026-06-29)** | docs/reward_research/2026-06-29_verify_soft_phase_reference_reward.md
  - what: A methods claim proposed L1/L2 tracking of literature normative joint curves WITHOUT a hard phase clock as a 'middle ground', letting the policy find its own timing.
  - tried: Recommended correct implementations instead: (a) range/band soft constraints (penalize only outside normal ROM, not full-curve tracking) or (b) contact-proxy phase (our own cop_progression/gait_phase_contact pattern) -- both already implemented in production. Also: foot_impact_force + foot_landing_vel must run alongside any imitation reward since imitation alone doesn't bound GRF/hard-landing.
  - result: Verdict: 'supported=TRUE but with large caveats.' Feasible to implement (already have cop_progression as a clock-proxy and joint_deviation_l1 in production), but the claim's core framing ('L2-to-curve without a clock = middle ground') is literature-inaccurate: pure clockless L2-to-time-varying-curve tracking is known to risk mode-collapse to an averaged/near-static pose (imitation-learning literat
  - numbers: n/a (literature/methodology verification, no new empirical numbers).
- **Deep-research Q1-Q3: natural gait, torque distribution & soft landing, passive toe -- external literature synthesis (2026-07-02)** | docs/reward_research/2026-07-02_gait_research_q123.md
  - what: ~300-agent, 9.6M-token deep research answering: how to get natural human-like efficient/low-impact gait, how to distribute torque and land softly, and how passive toe/toe-off should be rewarded. 3-vote adversarial synthesis, 11 findings all 3-0.
  - tried: Design implemented from this research (2026-07-03): mdp.contact_force_cap(threshold=600N~=1.2xBW, clip=400N) -- always-on (not first-contact only, unlike soft_landing), weight -0.005, gate = GRF P99 drop >=20% vs A1b baseline AND air_time >=0.2s (to catch a no-flight shuffle gaming attempt).
  - result: Confirmed our Siekmann phase-clock backbone matches the mainstream literature approach; refined (not refuted) the earlier 'joint-angle imitation fails' finding -- it only fails when the reference phase isn't synchronized to the actual contact phase (Cassie/Humanoid-Gym succeed specifically because reference is generated in the SAME clock phase the policy observes). Direct toe torque reward remains
  - numbers: C11 (Humanoid-Gym, real robot): soft-landing formula = -0.01 * min(max(F_foot-400N,0),100), i.e. per-foot threshold ~1.2xBW (400N), penalizing only the excess, clipped at 100 -- for OUR robot's BW this translates to threshold ~600N (1.2*505N). F4 (REEM-C): threshold cap -0.01*(Fz_L+Fz_R), only exces
- **contact_force_cap and B-series reward cascade result (from docs/62 synthesis, cross-referencing q123 note)** | docs/62_policy_reward_design_review.md (Section 1, cascade table)
  - what: The stacking of contact_force_cap, thermal_effort, and Siekmann periodic_contact was measured across successive reward configs on the same lineage.
  - tried: Documented failure: 'clip too low kills gradient on large spikes' -- B1 with clip=400N showed P99 -19% but PEAK actually WORSENED (stuck), while B1w2 (clip raised to 800N) immediately improved -27%. Lesson formalized as Principle 5 in docs/62: uncapped work-based rewards must be capped (else exploit, e.g. uncapped ankle_pushoff_work spiking reward to 324 vs normal 41, GRF 11.5xBW), but the clip va
  - result: No single 'magic' reward term solved GRF; reduction accumulated in a fixed LAYER ORDER (impact cap before push-off) across the cascade, GRF P99 dropped from 2.45xBW to 1.28xBW total across 5 successive additions.
  - numbers: GRF P99 (xBW), successive reward configs: A1b 2.45 -> B1 (contact_force_cap threshold-clip -0.005/clip400) 2.34 -> B1w2 (-0.01/clip800) 2.05 -> B2 (+thermal_effort) 1.88 -> B3 (+Siekmann periodic_contact) 1.63 -> P2-final 1.28.
- **Siekmann v8 impact/asymmetry breakthrough result (cited across multiple notes, canonical principle #3 in docs/62)** | docs/62_policy_reward_design_review.md (Principle 3) and 2026-06-29_toe_use_reward.md / 2026-06-29_verify_biomech_toe_pushoff_mtp_angle.md (cross-references)
  - what: Adding the single Siekmann periodic_contact reward term (v7->v8) simultaneously fixed tiptoe, limp, and energy.
  - tried: n/a -- this is the success case that grounded the subsequent recommendation to gate cop_progression to the Siekmann clock's terminal-stance window (phase 0.45-0.6) rather than a contact-time proxy.
  - result: Established as the strongest single-term result in the project's reward history: 'phase is legislated by LAW (a periodic-contact reward), not imitation -- one term simultaneously fixed tiptoe, limp, and energy.'
  - numbers: GRF: 8.9xBW -> 3.1xBW. CoT: 2.62 -> 1.22. Asymmetry: 0.83 -> 0.18. Also noted elsewhere: siekmann_v8 measured toe max-flexion phase L69%/R41% (target ~60% push-off, imprecise but improved).
- **Reward hacking incident: uncapped ankle push-off work (v9, cited in docs/62 and gait_research_q123)** | docs/62_policy_reward_design_review.md (Principle 5/6) referencing 'siekmann_pushoff_v9' and 2026-06-22_12-30_toe_rollover... note (history section)
  - what: An uncapped positive work reward on ankle push-off (scale 0.1, no cap) was tried as a push-off engine.
  - tried: Principle established: impact-force cap must be introduced BEFORE any push-off/work reward is added, in that fixed order -- adding push-off first (as v9 did) reward-hacks.
  - result: Formal reward-hacking incident, explicitly catalogued as one of the project's 'do not retry' failure modes ('uncapped work reward -> hacking'). After the incident, ankle_pushoff_work was rescaled (scale 0.02, cap 80W, late-gated) and then further de-emphasized to weight 0.1 (near off) out of self-conflict concerns with ankle_roll saturation.
  - numbers: reward exploded to 324 (normal ~41), error_vel 1.56, GRF 11.5xBW.
- **Toe direct-torque reward antipattern (toe_load_stance, cross-referenced across many notes)** | docs/reward_research/2026-06-22_12-30_toe_rollover_cop_progression_gaitfix_v6.md, 2026-06-29_toe_use_reward.md, 2026-06-29_verify_biomech_toe_pushoff_mtp_angle.md
  - what: A reward directly penalizing/rewarding |tau_toe| (passive toe spring torque = k*deflection) as a proxy for toe use.
  - tried: Rejected alternative also explicitly considered and rejected in 2026-06-22_12-19_gaitfix_v7_cop_progression.md candidate (b): 'toe FLEXION late-gate' -- same static-curl-gaming failure mode. Replaced by indirect cause-based rewards (cop_progression on GRF-fraction position, not toe torque).
  - result: Formally deprecated / catalogued as a cross-run 'do not retry' failure: since the toe is passive and over-damped, |tau_toe| reward can be satisfied by a static held curl rather than a genuine rolling push-off -- magnitude goes up, timing does not change, i.e. the policy games the metric rather than producing the intended biomechanics.
  - numbers: v5 measurement: toe bend increased 0.075->0.108 rad (magnitude up) but max-flexion phase stayed at 78-95% (swing/inertia), not push-off (~50-60%); L/R mean 10 vs 2 (asymmetric).
- **Static/momentary forefoot_cop reward measured as near-zero-contribution (gaitfix v6, 2026-06-22)** | docs/reward_research/2026-06-22_12-19_gaitfix_v7_cop_progression.md and 2026-06-22_toe_rollover_cop_progression_gaitfix_v6.md
  - what: A static (single-instant) forefoot GRF-fraction reward term intended to encourage toe/forefoot loading.
  - tried: Replaced by cop_progression (temporal, tau_n * frac product gated to late-stance) at weight +1.0-1.5, targeting 3-5% reward contribution. forefoot_cop demoted to weight 0.0 (removed) or 0.2 (static anchor) to avoid diluting the new term's gradient.
  - result: Confirmed via direct measurement (not just hypothesis) that a purely static/instantaneous GRF-fraction reward cannot create the needed TEMPORAL heel-to-toe CoP-progression sequence -- it is drowned out by tracking (+0.74) and upright (+0.45).
  - numbers: forefoot_cop weight 0.8; measured reward contribution in v6 = +0.0251, i.e. 0.06% of total reward (43.4).
- **Foot edge / ankle_roll peak plateau -- HW-floor vs reward-artifact split judgment (2026-06-22, gaitfix v3-v5)** | docs/reward_research/2026-06-22_03-50 / 2026-06-22_11-00 notes
  - what: ankle_roll (RS00, rated 5N.m continuous / 14N.m peak) stayed saturated across three successive reward attempts targeting foot edge-walking.
  - tried: v5 proposed lateral foot-placement reward + hip-roll offload as an untried routing lever before concluding HW under-spec; if v5 also fails to move peak below ~90% (12.6 N.m), hardware upgrade path recommended: RS00->DAMIAO DM-J4340-2EC (27/9 N.m, near drop-in), 2-RSU parallel ankle, or widening the foot.
  - result: Formal SPLIT verdict: RMS (sustained load) IS a reward/gait artifact and was partially recovered by widening stance (~20%); PEAK is at a genuine physical/hardware floor (mg x foot half-width) that reward shaping cannot move further without routing load elsewhere (foot-placement/hip) or upgrading hardware (motor, parallel actuation, or foot width).
  - numbers: v3 (joint-angle penalty foot_roll_flat -0.5): ankle_roll RMS ~110% continuous rated, peak 100% (14N.m), edge angle 20->18deg (barely moved). v4 (stance widened 0.20->0.24 + foot-body-orientation reward): RMS improved 6.3->5.0 N.m (~20% down, confirmed via a HARDER target that still lowered = a genui
- **Base_height / pelvis rigidity suppressing push-off vault (2026-06-22, gaitfix v6)** | docs/reward_research/2026-06-22_11-30_base_overconstrain_pelvis_swing_gaitfix_v6.md and 2026-06-22_12-19_gaitfix_v7_cop_progression.md
  - what: base_height_l2 fixed-target penalty (-1.0 @ target 0.85m) suppresses the CoM vault of push-off and pelvis swing, indirectly killing toe rollover too.
  - tried: v7 fix: replace fixed-target L2 with a floor-only penalty (base_height_floor, margin 0.06m, weight -0.5) + deadband on flat_orientation (+-7deg cone, sin7deg=0.122) + a new double-support incentive (target 15-20%) bundled together (adversarial verification determined base-relaxation ALONE would be null since neither new base term fired at v6's actual operating point -- 0% of frames below the floor
  - result: IsaacLab's own reference humanoids (G1, H1) have NO base_height term at all and zero out lin_vel_z_l2 -- confirmed as the field-standard pattern, contrasted with our fixed-target L2 penalty which was found to be a humanoid antipattern that fights push-off/vault directly (CoM-energy change from push-off is 86-96% coupled to vault height per literature). Relaxing base_height alone (v6: -1.0 -> -0.25
  - numbers: Measured vertical CoM bob amplitude 1.4-1.46cm vs human ~2.5-5cm (28-58% of human). Pelvis roll/pitch swing 3.9/1.5deg vs human ~7/4deg, unchanged even after flat_orientation weakened to -0.5. Double-support only 2% (vs human ~20%), single-support 97-98%, M-shape (vault) amplitude only 0.18cm vs hum
- **Registry overview (docs/66_experiment_registry.md)** | docs/66_experiment_registry.md
  - what: Master table of eras/runs with the standard comparison axes: 추종(tracking %, 15s dwell only valid), 부하(knee/hip P99·RMS ×1.15 friction-corrected, GRF P99 ×BW), 품질(CoT·fall rate·L/R symmetry). Measurement standard = measure_full.py fc(clean)/fcp(push), 0.25 grid, 2D compound plane, 15s dwell, in-DR push.
  - tried: 
  - result: flat design anchor progression: flat25b_prog_p1 -> flat25b_bentinit_p2 (bentp2) -> gen21_bent_p2 (current, 2026-07-13).
  - numbers: See per-run entries below.
- **gaitfix_v7 (Era-2, custom 20-term reward, HELD)** | docs/experiments/2026-06-22_12-29-19_gaitfix_v7.md
  - what: Final gaitfix iteration adding cop_progression(+1.2), base_height_floor(-0.5, floor not fixed target), flat_orientation_deadband(±7°), double_support_bonus(+0.1). Result: generative levers too weak, gait barely changed -> line HELD, pivot to G1 vanilla baseline.
  - tried: cop_progression (+1.2, toe CoP load), base_height_floor (-0.5, collapse floor vs fixed target), flat_orientation_deadband (±7° free tilt), double_support_bonus (+0.1).
  - result: 
  - numbers: toe bend 13°->16° (human 30°), forefoot fraction 33%->34% (human ≳70%), single/double support 98/2%->96/3% (human 80/20%), bob 1.46->1.70cm, ankle_pitch RMS 26.5->29.3, fall rate 1%->0%. No explicit GRF xBW recorded in this note (GRF penalty contribution only -0.0351).
- **Siekmann v8 (2026-06-29) — periodic_contact clock, THE breakthrough** | docs/experiments/2026-06-29_13-00-01_siekmann_v8_flat.md
  - what: Replaced joint-angle imitation (humanref v3-v7, failed) with Siekmann periodic contact-schedule phase clock (+1.5 weight): stance=foot stopped, swing=foot low-force, L/R phase offset 0.5, sin/cos clock obs added (obs 239->241).
  - tried: 
  - result: One clock term (+1.5 periodic_contact) simultaneously fixed limping, impact, symmetry, human-likeness, and energy -- confirmed as the single largest lever in the whole reward-design history (per docs/62 catalog entry #3: 'GRF 8.9→3.1×BW, CoT 2.62→1.22, 비대칭 0.83→0.18').
  - numbers: GRF asymmetry 0.87->0.83->0.18; GRF peak 8.7BW->8.9BW->3.1BW; CoT 1.54->2.62->1.22; cycle L/R 6/51 -> 35/35; base_height 0.85 maintained; toe use 0.41/0.28 -> 0.65/0.33 -> 0.34/0.34 (symmetric). GRF absolute: 'L1345/R1569N(asym 0.18)'; 'peak 3.1×BW... 단 1.5kN soft 초과 → Stage3 impact cap 필요'. base 0.
- **Siekmann pushoff v9 (2026-06-29) — power-farming regression** | docs/experiments/2026-06-29_22-48-47_siekmann_pushoff_v9_flat.md
  - what: Added ankle_pushoff_work(+0.5, terminal-stance plantarflexion power τ·ω clamp 0-80W) and cop_progression(+1.2, heel->toe CoP progression) on top of v8, WITHOUT an impact/GRF cap. Intent: cause windlass/toe-off to emerge without directly rewarding toe torque.
  - tried: 
  - result: Confirmed the design principle 'impact/GRF cap must precede push-off reward' -- ungapped power reward = reward-gaming/hacking. Led directly to the B-series contact_force_cap ordering rule.
  - numbers: GRF peak: v8 3.1BW -> v9 11.5BW (5822N); GRF asym 0.18->0.13 (improved); human-likeness 0.14->0.05 (worse); CoT 1.22->1.66 (344W); toe flex phase L77%/R71% (target ~60%); toe flex amount L0.145/R0.034 rad; knee peak clipped at effort limit 216 N·m both legs.
- **G1 Impact Stable (g1is_dm4340_flat, 2026-06-28) — origin of _apply_g1_impact_stable() function** | docs/experiments/2026-06-28_19-55-27_g1is_dm4340_flat.md; function defined in pygmalion_locomotion/source/pygmalion_locomotion/tasks/locomotion/g1_vanilla_env_cfg.py:213
  - what: Introduced the lineage-wide `_apply_g1_impact_stable` reward bundle: G1 vanilla + impact terms (foot_landing_vel -1, foot_impact_force -0.005, knee_straight -5) + anti-trembling (dof_acc now includes ankle -3e-7, action_rate -0.01). Also swapped ankle_roll motor RS00->DM-J4340-2EC and knee gear +1.8:1.
  - tried: 
  - result: Impact terms alone were insufficient -- caused tiptoe gait because foot-flat/heel-toe shaping was removed, which then overloaded ankle actuators via narrow support base. Directly motivated later reintroduction of foot-flat/heel-toe shaping and eventually the Siekmann clock. Note: base_height fix for tiptoe regression is documented separately in docs/reward_research/2026-06-29_tiptoe_regression.md,
  - numbers: ankle_roll RMS 215% of rated, peak 100% (sat 50%); ankle_pitch RMS 191% rated, peak 100% (sat 21%); knee RMS 24% (headroom, gear change succeeded); hip RMS 43-59%; base_height mean 0.952m (tiptoe confirmed); GRF L273/R242 N (mild asymmetry). fall rate 0%, error_vel_xy 0.228.
- **mjlab B1 (2026-07-03) — first impact cap (contact_force_cap)** | docs/experiments/2026-07-03_04-03-01_mjlab_B1.md
  - what: Added contact_force_cap reward term: weight -0.005, formula -min(max(F-600,0),800) i.e. threshold 600N, clip 800N excess penalty, on top of A1b baseline (gains: hip/knee Kp400/Kd28 or 8, ankle Kp≈2/19.7).
  - tried: contact_force_cap -0.005 weight, clip800(?) -- actually clip 400 per note text 'clip400 gradient 차단' (the reward formula constant differs slightly from later B2/B3 -0.01/clip800; B1 used a tighter/lower clip that blocked the gradient for big spikes, motivating escalation to B1w2).
  - result: 
  - numbers: Mean reward 74.64 (iter 3385); error_vel_xy 0.767, error_vel_yaw 0.661; fell_over 0.000/low_base 0.167; knee RMS 104%rated, ankle_pitch RMS 115%rated. GRF P99 (from docs/62 cascade table) = 2.34xBW (down from A1b's 2.45xBW, a modest -19% relative move flagged as marginal because clip400 blocked grad
- **mjlab B1w2 (escalated impact cap)** | docs/62_policy_reward_design_review.md (row 5, 29)
  - what: Escalated contact_force_cap to weight -0.01, clip 800 (per docs/62: 'clip800 즉치 −27%').
  - tried: 
  - result: Confirms the impact-cap clip constant is critical: a too-low clip (400) truncates gradient for large spikes and barely moves P99; raising to clip800 (with weight -0.01) produced the actual drop.
  - numbers: GRF P99: A1b 2.45xBW -> B1 2.34xBW -> B1w2 2.05xBW -> B2 1.88xBW -> B3 1.63xBW -> P2-final 1.28xBW.
- **mjlab B2 (2026-07-03) — thermal_effort added** | docs/experiments/2026-07-03_06-23-45_mjlab_B2.md
  - what: Added thermal_effort reward: weight -0.02, formula -Σ(τ/rated)² (torque redistribution across joints to reduce single-joint heat), on top of B1's contact_force_cap now at -0.01/clip800.
  - tried: 
  - result: Thermal redistribution reduced hip_pitch and ankle_pitch RMS% while GRF continued dropping (2.05->1.88xBW), 'ACCEPT'.
  - numbers: Mean reward 70.17 (iter 3356); error_vel_xy 0.848, error_vel_yaw 0.653; fell_over 0.000/low_base 0.042; knee RMS 114% (binding, only joint over rated), ankle_pitch RMS 88%. GRF P99 1.88xBW (per cascade table).
- **mjlab B3 (2026-07-03) — Siekmann clock ported into mjlab, final B-series stack** | docs/experiments/2026-07-03_07-34-12_mjlab_B3.md
  - what: Added periodic_contact (Siekmann phase clock, +1.5) to the B2 stack (contact_force_cap -0.01/clip800 + thermal_effort -0.02), removing redundant swing-shaping terms (foot_clearance/foot_swing_height set to 0, clock now legislates swing).
  - tried: 
  - result: B3 became the 'ankle policy document' anchor referenced by registry (ankle_pitch 47%/ankle_roll 14% of rated -- ankle-actuator-tn-sizing.md memory). This B-series cascade (A1b->B1->B1w2->B2->B3->P2-final) is the definitive quantified proof that 'no single magic reward term' fixed GRF -- it accumulated in strict layer order: contact_force_cap first, then thermal_effort, then periodic_contact (per d
  - numbers: Mean reward 84.41 (iter 15199); error_vel_xy 2.861 (random-command video eval, not tracking-quality metric), error_vel_yaw 0.605; fell_over 0.000/low_base 0.042. GRF P99 1.63xBW (per cascade table, down from B2's 1.88). L/R GRF asymmetry 0.83->0.02. ankle_pitch RMS dropped from 113% to 47% of rated 
- **flat25b_prog_p1 (2026-07-10) — progress reward FIX, current-generation flat lineage root** | docs/experiments/2026-07-10_flat25b_prog_p1.md
  - what: Added track_lin_vel_progress (+1, linear progress reward: min(v·cmd_hat, |cmd|)) and widened track_linear_velocity std 0.5->0.866, on top of flat25_p1 (which froze at high speed). Straight-knee init, DR-OFF, 20000 iter complete.
  - tried: 
  - result: Resolved the high-speed 'freeze' failure of flat25_p1 (which achieved only 5-10% at vx>=2.0). Established knee P99≈97 and GRF P99≈1.73BW as the flat-2.5 nominal (DR-off) design point; hip_pitch became newly co-dominant at P99≈120 (clip-limited) due to high-speed propulsion demand.
  - numbers: GRF P99 1.73BW, peak 5.95BW (R foot), L/R peak asym 15% (down from flat25_p1's 44%). knee P99 97.5 (81% of 120 clip), RMS 30.6 (76%rated); hip_pitch P99 119.8 (100% clip, sat 1.06%), RMS 32.6 (81%); ankle_pitch RMS 106% (only RMS-binding joint, unless 2-RSU co-actuation assumed=53%). knee omega P99.
- **gen2_bent_p1/p2 (2026-07-12) — Gen-2 bundle, ultimately REJECTED (stall creep-gaming)** | docs/experiments/2026-07-12_gen2_bent_p1.md; docs/experiments/2026-07-12_gen2_bent_p2.md
  - what: 4-term bundle vs flat25b: (1) bent-knee init (2) pose std_walking[hip_roll] 0.15->0.4 (3) new stand_still_penalty -1.0 (absolute threshold |v|<0.15 when |cmd|>0.3) (4) new knee_overspeed -0.5 (penalize |knee_qdot|>19.9 rad/s).
  - tried: 
  - result: REJECTED: absolute-threshold stand_still_penalty let the policy game the reward by 'creeping' (walking slowly, e.g. 1.44m/s at cmd 2.5) to avoid the stall penalty while sacrificing the progress reward -- confirmed a structural reward-gaming defect that DR/push training did NOT fix (in fact worsened, spreading from mid-speed to high-speed and reverse blocks). Anchor stayed at bentp2 (flat25b_bentin
  - numbers: P1 gate: vy+1.0->61%/-1.0->96% (pass, first time), stall 0.75->84% (pass but flagged as creep-gaming), knee omega P99.9 15.6 (pass), GRF 1.44BW (pass), vx2.5->67% (FAIL, gate 85%), knee P99=120(clip)/RMS 121% (FAIL). P2 final: vx2.5->57% (worse than P1's 67%), vx1.5->56%, GRF P99 1.24BW, knee P99 10
- **gen21_bent_p1/p2 (2026-07-13) — Gen-2.1, single-variable ablation FIXED creep, PROMOTED to current flat anchor** | docs/experiments/2026-07-13_gen21_bent_p2.md; docs/experiments/2026-07-13_gen21_bent_p1.md
  - what: Single-variable ablation vs Gen-2: replaced stand_still_penalty's absolute detection threshold (|v|<0.15) with a RELATIVE pursuit floor (v·cmd_hat < 0.3|cmd|), same weight -1.0, same deadband |cmd|>0.3; all other Gen-2 bundle terms (bent init, hip_roll std 0.4, knee_overspeed) unchanged. env.yaml diff=0 (condition logic only).
  - tried: 
  - result: PROMOTED: 'flat 설계앵커 = gen21p2_fc' (registry §0, §8: 'flat 설계앵커(현행, 2026-07-13 승격)') replacing bentp2. Design values with safety factors: knee RMS 45.5×1.15=52.3 (thermal), knee P99 112.4×1.25=140.5 (instantaneous, exceeds 120 clip meaning true demand is clip-masked -- covered by planned 1.5:1 knee link-lever giving 93.7 effective), hip_pitch P99 91.7×1.25=114.6, push-sensitive joints anchored dir
  - numbers: P1(DR-off) gate: vx1.5->114%, vx2.5->85%, fell 0/0. P2(DR+push) final gate: vx2.5->92%, vx-2.0->91%, vx1.5->59% (1pt below 60% threshold, judged single-block noise not systemic creep), vy+1.0/-1.0->98%/98% (best of series), knee omega P99.9 14.3 (max 18.9, 0 samples over 19.9 real-motor limit), knee
- **init-pose A/B, P1 (straight vs bent knee) — 2026-07-12_bentinit_ab_result.md §1-7** | docs/experiments/2026-07-12_bentinit_ab_result.md
  - what: Straight-knee (flat25b_prog_p1) vs bent-knee-init (flat25b_bentinit_p1), single-variable diff (init_state only), same fc/fcp measurement protocol, 2.5-box/progress-reward high-speed regime.
  - tried: 
  - result: Reversed the OLD 2026-07-08 A/B conclusion (docs/55, low-speed/exp-reward regime) which found bent knee +98% knee torque / -35% GRF ('no clean winner, redistribution'). In the NEW high-speed/progress-reward regime, bent knee WINS on nearly every axis: -20% knee torque, -37% GRF peak, better push robustness, better high-speed tracking. Interpretation given in note §4: 'straight가 고속 추진에서 knee/hip을 극
  - numbers: straight->bent deltas: knee P99 113.9->90.8 (-20%), hip_pitch P99 95.3->91.0 (-5%), hip_roll P99 55.5->53.7 (-3%), hip_yaw P99 35.0->39.6 (+13%), ankle_pitch P99 23.2->66.4 (+186%), GRF P99 1.52BW->1.37BW (-10%), GRF peak 7.52BW->4.73BW (-37%), falls (clean) 13 vs 15 (~equal), falls under push 13->3
- **init-pose A/B, P2-vs-P2 final confirmation (2026-07-12_bentinit_ab_result.md §8-9)** | docs/experiments/2026-07-12_bentinit_ab_result.md
  - what: Re-ran straight vs bent comparison after BOTH arms completed push/DR training (P2), to control for the P1 finding possibly being an artifact of straight's untrained push response.
  - tried: 
  - result: FINAL: 'Gen-2 init = bent-knee 확정' (bent-knee init confirmed as the Gen-2 standard). Bent wins on tracking consistency, push robustness (0 falls vs 3), majority of joint loads, and GRF; straight's only advantages (knee P99, ankle_roll M_t) are confounded by straight's persistent stall failing to achieve commanded speed. Design anchor set to bent P2 (bentp2_fc): knee 109.3, hip_pitch 95.0, GRF 1.30
  - numbers: straight P2 vs bent P2: falls under push 3 vs 0; knee P99 91.9 vs 109.3 (+19%, flagged as confounded by straight's stall blocks not achieving commanded speed); hip_pitch/roll/yaw P99 98.6/57.2/34.4 vs 95.0/54.7/31.7 (bent lower); ankle_pitch P99 62.0 vs 60.5 (converged); ankle_roll M_t P99 160.0 vs 
- **Design-side GRF/impact statistic doctrine (P99 vs peak, SF rules)** | /home/syaro/MikuchanRemote/Human-Pygmalion/docs/65_design_value_uncertainty.md §1, §4, §5
  - what: docs/65 establishes a strict statistic hierarchy for what may be used as a design load: RMS and P99 are trustworthy (narrow bootstrap CI), raw peak is explicitly forbidden for sizing because it is a single-event/clip artifact with wide CI.
  - tried: 
  - result: 
  - numbers: CI width by statistic: RMS ±3–14% (usually ≤9%, '높음' reliable) / P99 ±4–18% ('높음', validated across 100+ crossings) / peak ±4–47% ('낮음', single-event, DO NOT static-size). §5 SF table: thermal/continuous(RMS) → RMS upper-CI × 1.15; instantaneous/repeated(P99) → P99 upper-CI × 1.25; structural/max → 
- **Current authoritative GRF design numbers (flat/rough anchors)** | /home/syaro/MikuchanRemote/Human-Pygmalion/docs/65_design_value_uncertainty.md §2b, §3, §2d, §8
  - what: docs/65 §3 gives the current authoritative GRF table (fc, clean rollouts) used as the design anchor; §2b gives push (fcp) deltas; §2d/§8h give an updated 'contact-only' GRF figure that supersedes the link-Fz based one.
  - tried: 
  - result: 
  - numbers: flat anchor (gen21p2_fc): RMS 351.7 N (0.70 BW), P99 664 N (1.31 BW ±1.3%), fcp P99 1.40 BW, peak 3214 N (6.36 BW). Old flat (flat25b_fc): RMS 352.9 N (0.70 BW), P99 769.6 N (1.52 BW), peak 3799 N (7.52 BW). Rough (p2r_fc): RMS 358.5 N (0.71 BW), P99 768.1 N (1.52 BW), peak 3948 N (7.82 BW). §2d ben
- **Joint/bearing-side impact & structural load-case doctrine (docs/64)** | /home/syaro/MikuchanRemote/Human-Pygmalion/docs/64_joint_bearing_design_inputs.md §1–§2, §8j (hip_pitch LC table ~line 460-508), §8k (ankle stopper ~line 512-591)
  - what: docs/64 defines the bearing/housing design methodology built on the same P99/peak hierarchy: static C0 uses in-DR P99~peak × s0(1.5–3); life L10 uses RMC (cubic-mean) not RMS; a single simultaneous 6-vector at the peak instant is the FEA load case (not per-component peaks combined); fall/impact tail is explicitly NOT for static sizing but for overload/fuse/protection design.
  - tried: 
  - result: 
  - numbers: §2 table: bearing static C0 = in-DR P99~peak ×s0 1.5-3; life L10 = RMC(p=3 ball/10:3 roller) + equivalent-revolution (oscillation-corrected); housing/bolt static = simultaneous peak 6-vector ×SF 1.5-2 (3-4 FEA cases/joint); fall tail = static sizing ✗ → overload/fuse/protection policy input only. hi
- **Ankle-roll/pitch penetration events are ground-driven, not motor/policy-driven** | /home/syaro/MikuchanRemote/Human-Pygmalion/docs/64_joint_bearing_design_inputs.md §8k-b
  - what: docs/64 §8k-b shows via frame-by-frame GRF/angle traces that the two worst stopper-penetration events (ankle_roll 23.3°, ankle_pitch 17.7°) are caused by sudden ground contact geometry (foot outer-edge landing during turn; sloped-tile landing during lateral step), not by motor torque — i.e., impact-driven kinematics that a torque-based reward/soft-landing term would not directly capture.
  - tried: 
  - result: 
  - numbers: ankle_roll event: swing (GRF 0) → 605N contact → −1.8° to −43.3° in 40ms (~1000°/s), during wz=−1.00 turn. ankle_pitch event: −18.2° to 57.7° in 60ms (~660°/s) during vy=+0.74 lateral step on sloped tile. Design implication stated verbatim: 'ankle 스토퍼는 토크 정격이 아니라 충격 에너지·접근 속도로 사이징해야 한다(접근 각속도 660~10
- **Bent-init A/B: impact absorption (GRF) vs knee torque tradeoff** | /home/syaro/MikuchanRemote/Human-Pygmalion/docs/55_init_pose_straight_vs_bent.md §1, §2, §3, §4
  - what: docs/55 is a controlled A/B (seed 42, no-DR, only init pose changed) directly on point: bending the knee at init lowers GRF impact substantially but roughly doubles knee torque — the exact tension the new soft-landing term could reproduce/interact with.
  - tried: 
  - result: 
  - numbers: GRF peak: straight 2.15 BW → bent 1.39 BW (−35%, 'bent wins'). GRF p95: straight 1.14 → bent 1.03 BW. Knee torque p95: straight 29.9 N·m → bent 59.2 N·m (+98%). Knee tracking error p95: straight 0.151 rad → bent 0.276 rad. Other joints under bent: hip_pitch tau −24% (50.9→38.9), hip_roll tau −28% (4
- **Ankle AB/RP training context — current runs at time of soft-landing proposal** | /home/syaro/MikuchanRemote/Human-Pygmalion/docs/92_ankle_ab_rp_training_setup.md §4-§7; /home/syaro/MikuchanRemote/Human-Pygmalion/docs/93_ankle_ab_rp_comparison_plan.md §0, §3(E), §5b
  - what: docs/92/93 describe the currently running ankleAB_c2r/ankleRP_c2 A/B training (same reward/curriculum/mass/motor/T-N/init/upper-body/DR, only ankle mechanism differs) that the soft-landing reward change would apply to, and its own already-measured impact/landing figures at iter 1200 before the soft-landing term existed.
  - tried: 
  - result: 
  - numbers: docs/93 §5 (iter 1016, stage-1): thermal AB 4.00 / RP 3.65; landing[N] AB 275 / RP 283. §5b (iter 1200, ankle_usage_tremble measurement): contact-only GRF_L p99 AB 1.39 BW vs RP 1.51 BW; contact duty AB 0.51 vs RP 0.64; RP shows 'bang-bang' ankle target rail (target swings −40..+35° vs actual +15..+
- **Soft-landing proposal: diagnosis and prescribed reward change** | /home/syaro/MikuchanRemote/Human-Pygmalion/docs/reward_research/2026-08-24_soft_landing_impact.md (full file)
  - what: docs/reward_research/2026-08-24_soft_landing_impact.md diagnoses hard footfalls in the currently running ankleAB_c2r/ankleRP_c2 (iter 2500) via a dedicated 200Hz impact probe, finds existing soft_landing/contact_force_cap terms are effectively inert given real robot BW, and prescribes a new foot_impact_velocity reward term plus a rescaled contact_force_cap.
  - tried: 
  - result: 
  - numbers: Measured (median/p90) at 0.4&0.8 m/s, AB vs RP vs human(1.0-1.3m/s): pre-contact vertical foot speed AB 1.34/1.69 m/s, RP 1.54/1.82 m/s, human 0.1-0.4 m/s; vertical GRF peak AB 1.40/1.67 BW (max 2.17), RP 1.55/1.89 BW (max 2.01), human 1.0-1.2 BW; loading rate max dF/dt AB 155/266 BW/s, RP 158/207 B
- **Potential conflict/tension for synthesis to judge** | Cross-reference: docs/65_design_value_uncertainty.md §5, §2d, §3; docs/64_joint_bearing_design_inputs.md §8k, §8k-b; docs/55_init_pose_straight_vs_bent.md §1-4; docs/reward_research/2026-08-24_soft_landing_impact.md
  - what: Cross-referencing the above: the design side's authoritative GRF anchor doctrine (§5 of docs/65, 'P99 ≈ 1.4BW × 1.3', current flat/rough anchors at P99 1.31-1.81 BW) and the docs/64 §8k finding that ankle stopper impacts are GROUND-DRIVEN kinematic events (not motor-torque events, approach speeds 660-1000°/s) sit against the soft-landing proposal's target of driving GRF p90 below 1.4 BW and contact speed below 0.6 m/s. The bent-init A/B (docs/55) already shows that suppressing GRF impact via pos
  - tried: 
  - result: 
  - numbers: Design GRF anchors to satisfy: flat P99 1.31-1.40 BW (fc/fcp), rough P99 1.81 BW (contact-corrected, docs/65 §2d) vs soft-landing gate target GRF p90 <1.4 BW. Knee torque already sensitive to posture (docs/55: bent +98% torque for −35% GRF peak) and to reward generation (docs/65 §2e/§9: knee RMS env

## Web findings

- **legged_gym (ETH RSL) — foundational reward set, base for nearly every fork below** | https://github.com/leggedrobotics/legged_gym/blob/master/legged_gym/envs/base/legged_robot.py (verified via raw.githubusercontent.com, lines 882-906)
  - Three contact-related reward terms that recur (often verbatim) across the whole ecosystem: feet_air_time (rewards swing duration above a threshold, gated off at zero command), stumble (penalizes horizontal>>vertical contact force, i.e. hitting a vertical surface), and feet_contact_forces (GRF cap — penalizes ||F|| above cfg.rewards.max_contact_force). No literal impact-velocity or momentum term exists in this base class.
  - result: Confirmed exact source, byte-for-byte. This is the ancestor of unitree_rl_gym, AMP_for_hardware, and most quadruped stacks below — the GRF-cap pattern (`(||F||-max_contact_force).clip(min=0)`) is the standard 'GRF cap' the survey asked about.
  - numbers: air-time threshold 0.5 s; stumble ratio 5x; max_contact_force is a per-robot config value (not set in base class default).
  > def _reward_feet_air_time(self):
    contact = self.contact_forces[:, self.feet_indices, 2] > 1.
    contact_filt = torch.logical_or(contact, self.last_contacts)
    self.last_contacts = contact
    first_contact = (self.feet_air_time > 0.) * contact_filt
    self.feet_air_time += self.dt
    rew_ai
- **unitree_rl_gym (Unitree official, Go2/H1/H1-2/G1) — identical fork of legged_gym** | https://github.com/unitreerobotics/unitree_rl_gym/blob/main/legged_gym/envs/base/legged_robot.py
  - Same three functions (_reward_feet_air_time, _reward_stumble, _reward_feet_contact_forces) copied essentially verbatim from legged_gym.
  - result: Deployed on real Unitree G1/H1/Go2 hardware (Unitree's own sim2real pipeline). Confirms the GRF-cap pattern is what ships on real Unitree humanoids/quadrupeds, not a bespoke impact-momentum term.
  - numbers: Same structure as legged_gym; per-robot max_contact_force set in g1_config.py / h1_config.py (not independently re-verified here).
  > penalty term: torch.sum((torch.norm(self.contact_forces[:, self.feet_indices, :], dim=-1) - self.cfg.rewards.max_contact_force).clip(min=0.), dim=1)
- **Humanoid-Gym / XBotL (RobotEra XBot-S, XBot-L) — real-robot deployed, richest 'soft contact' reward menu of the survey** | https://github.com/roboterax/humanoid-gym — humanoid/envs/custom/humanoid_env.py (functions) and humanoid_config.py (weights), fetched raw and grepped directly
  - foot_slip: sqrt(horizontal foot speed) gated by contact (>5N). feet_clearance: rewards |foot_height - target| < 0.01 during swing only (height accumulated incrementally, reset on contact). feet_contact_number: +1 if contact matches the commanded gait phase, else -0.3 (mean over feet) — a phase-gated contact-timing reward. feet_contact_forces: sum((||F||-max_contact_force).clip(0,400)) — GRF cap with an explicit upper clip of 400N on the penalty itself. base_acc: exp(-||Δ(base lin+ang vel)||·3) —
  - result: Zero-shot deployed on real RobotEra XBot-S (1.2 m) and XBot-L (1.65 m) humanoids per the repo/paper (arXiv:2404.05695). Note: no reward here is literally named 'soft landing' in code — 'soft, cushion-like landing' is a claim made in the paper's prose/marketing, achieved by the combination of feet_co
  - numbers: config: max_contact_force=700; scales: feet_contact_forces=-0.01, feet_clearance=1.0, foot_slip=-0.05, feet_air_time=1.0, feet_contact_number=1.2, base_acc=0.2.
  > def _reward_foot_slip(self):
    contact = self.contact_forces[:, self.feet_indices, 2] > 5.
    foot_speed_norm = torch.norm(self.rigid_state[:, self.feet_indices, 7:9], dim=2)
    rew = torch.sqrt(foot_speed_norm)
    rew *= contact
    return torch.sum(rew, dim=1)

def _reward_feet_contact_forces
- **Booster Gym / Booster T1 humanoid — real-robot deployed; explicitly avoids contact-force-based swing detection** | https://github.com/BoosterRobotics/booster_gym — envs/t1.py (functions, lines 696-731) and envs/T1.yaml (scales, lines 250-291)
  - feet_slip: squared foot-position delta (≈velocity²) summed and gated by a contact flag, always active regardless of contact/no-contact bookkeeping oddity. feet_vel_z: squared vertical foot velocity — present as an available term but shipped with weight 0 by default. feet_roll: penalizes foot roll angle. feet_swing: rewards the correct foot being airborne during its scheduled swing-phase window (gait-phase gated, not contact-force gated).
  - result: Deployed on real Booster T1; the accompanying paper states explicitly: 'Due to the simplified collision estimation in Isaac Gym, we use the difference in height between the foot and the ground, rather than foot contact forces, to determine whether the robot is lifting its leg' — i.e. they deliberate
  - numbers: T1.yaml scales: feet_slip=-0.1, feet_vel_z=-0. (disabled), feet_roll=-0.1, feet_swing=3.0. Also paper (arXiv:2506.15132, Table II) shows same terms with survival=0.25 etc.
  > def _reward_feet_vel_z(self):
    return torch.sum(torch.square((self.last_feet_pos - self.feet_pos) / self.dt)[:, :, 2], dim=-1)

def _reward_feet_swing(self):
    left_swing = (torch.abs(self.gait_process - 0.25) < 0.5 * self.cfg["rewards"]["swing_period"]) & (self.gait_frequency > 1.0e-8)
    rig
- **IsaacLab default velocity-locomotion RewardsCfg (base_velocity task, quadruped-oriented defaults)** | https://github.com/isaac-sim/IsaacLab — source/isaaclab/isaaclab/envs/mdp/rewards.py (undesired_contacts/contact_forces, lines 267-300) and source/isaaclab_tasks/.../locomotion/velocity/mdp/rewards.py (feet_air_time/feet_air_time_positive_biped/feet_slide) and .../velocity_env_cfg.py (default RewardsCfg, lines ~231-280)
  - feet_air_time (mdp.feet_air_time — reward proportional to (last_air_time - threshold) on first contact, zeroed at zero command). undesired_contacts (counts sensor-body contacts above a force threshold — e.g. thigh contact). contact_forces (GRF cap — sum of clip(||F||-threshold, min=0)). feet_slide (penalizes horizontal body velocity of a foot body while in contact, contact defined by >1N net force).
  - result: This is the shared library every IsaacLab humanoid/quadruped task config (G1, H1, Berkeley Humanoid, ANYmal, Unitree Go2) imports from — confirms 'undesired_contacts' and 'contact_forces' (GRF cap) are the canonical IsaacLab primitives; there is no built-in 'feet_impact' or momentum term in this fil
  - numbers: Default RewardsCfg: feet_air_time weight 0.125-ish default template, threshold 0.5; undesired_contacts weight -1.0, threshold 1.0N; contact_forces threshold param-driven, no fixed default weight (task-specific).
  > def undesired_contacts(env, threshold, sensor_cfg):
    net_contact_forces = contact_sensor.data.net_forces_w_history
    is_contact = torch.max(torch.norm(net_contact_forces[:, :, sensor_cfg.body_ids], dim=-1), dim=1)[0] > threshold
    return torch.sum(is_contact, dim=1)

def contact_forces(env, t
- **IsaacLab Unitree G1 humanoid task (rough_env_cfg.py) — exact deployed-style weights** | https://github.com/isaac-sim/IsaacLab/blob/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/config/g1/rough_env_cfg.py (fetched and printed in full)
  - G1Rewards overrides base RewardsCfg: feet_air_time uses feet_air_time_positive_biped (single-stance-aware variant — only rewards air time when exactly one foot is in contact, i.e. proper biped alternation) on .*_ankle_roll_link bodies, threshold 0.4s, weight 0.25. feet_slide weight -0.1 on the same ankle-roll bodies. undesired_contacts is explicitly disabled (set to None) for G1.
  - result: This is the config most reproduction humanoid RL pipelines (including many follow-on G1 papers) start from — no explicit landing-velocity/impact term is present for G1 in mainline IsaacLab; softness comes indirectly from feet_slide + the single-stance air-time gate.
  - numbers: feet_air_time weight=0.25, threshold=0.4s; feet_slide weight=-0.1; termination_penalty=-200.0.
  > feet_air_time = RewTerm(
    func=mdp.feet_air_time_positive_biped,
    weight=0.25,
    params={"command_name": "base_velocity", "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*_ankle_roll_link"), "threshold": 0.4},
)
feet_slide = RewTerm(
    func=mdp.feet_slide,
    weight=-0.1,
    
- **feet_air_time_positive_biped — exact algorithm (single-stance gate)** | https://raw.githubusercontent.com/isaac-sim/IsaacLab/main/source/isaaclab_tasks/isaaclab_tasks/manager_based/locomotion/velocity/mdp/rewards.py
  - Unlike the plain feet_air_time (rewards time since last liftoff on contact), the biped variant tracks current_air_time and current_contact_time, takes whichever is running for each foot, and only rewards the min across feet when exactly one foot is in contact (single_stance). This prevents the reward from being gamed by hopping or double-support dwelling and is the mechanism most bipeds (G1, Berkeley Humanoid, H1) use to shape swing/stance timing (indirectly bearing on how 'controlled' each foot
  - result: Directly relevant background for interpreting any ankle/foot-timing reward comparisons (e.g. your own ankleAB/RP A-B runs) against the field standard.
  - numbers: clamp ceiling = threshold (task-specific, e.g. 0.4s for G1).
  > def feet_air_time_positive_biped(env, command_name, threshold, sensor_cfg):
    air_time = contact_sensor.data.current_air_time[:, sensor_cfg.body_ids]
    contact_time = contact_sensor.data.current_contact_time[:, sensor_cfg.body_ids]
    in_contact = contact_time > 0.0
    in_mode_time = torch.whe
- **Berkeley Humanoid (HybridRobotics, IsaacLab-based) — real-robot deployed** | https://github.com/HybridRobotics/isaac_berkeley_humanoid — .../velocity/mdp/rewards.py and .../velocity_env_cfg.py
  - feet_air_time here is a TWO-SIDED threshold variant (threshold_min AND threshold_max) — penalizes steps shorter than threshold_min (too twitchy/never really airborne) and caps reward growth above threshold_max (discourages hanging feet in the air too long, which would mean a harder eventual landing at higher approach speed).
  - result: Real-robot deployed (Berkeley Humanoid hardware paper). The min/max air-time band is the closest thing in this stack to an implicit landing-speed regulator (bounding how long/fast a foot swings before it must touch down) but there is no explicit foot-velocity-at-touchdown term.
  - numbers: RewardsCfg: feet_air_time weight=2.0, threshold_min=0.2, threshold_max=0.5, sensor body_names='.*faa' (foot-ankle-adapter); feet_slide weight=-0.25 on same bodies; undesired_contacts weight=-1.0 on hfe/haa (hip) bodies.
  > def feet_air_time(env, command_name, sensor_cfg, threshold_min, threshold_max):
    first_contact = contact_sensor.compute_first_contact(env.step_dt)[:, sensor_cfg.body_ids]
    last_air_time = contact_sensor.data.last_air_time[:, sensor_cfg.body_ids]
    air_time = (last_air_time - threshold_min) *
- **unitree_rl_lab (Unitree's newest IsaacLab-based stack, 2025-2026) — most feature-rich contact-timing reward set surveyed, still no explicit landing-velocity term** | https://github.com/unitreerobotics/unitree_rl_lab — source/unitree_rl_lab/unitree_rl_lab/tasks/locomotion/mdp/rewards.py (fetched and read in full)
  - feet_stumble (4x horizontal/vertical force ratio, vs legged_gym's 5x). foot_clearance_reward: exp(-Σ[(foot_z - target_height)² · tanh(k·||foot_xy_vel||)] / std) — height-error weighted by a tanh-saturated horizontal-speed gate, meant to allow height error near the ground (low speed) while punishing it mid-swing. air_time_variance_penalty: variance of per-foot last_air_time and last_contact_time across feet (symmetry/timing regularity, not impact). feet_gait: explicit phase-based stance/swing sch
  - result: No literal 'landing velocity' or 'contact momentum' term anywhere in this newest Unitree stack either — confirms the survey's target terms are not standard nomenclature even in late-2025/2026 official releases.
  - numbers: Function signatures only; per-task weight/threshold values live in separate robot config files not fetched (time-boxed).
  > def feet_stumble(env, sensor_cfg):
    forces_z = torch.abs(contact_sensor.data.net_forces_w[:, sensor_cfg.body_ids, 2])
    forces_xy = torch.linalg.norm(contact_sensor.data.net_forces_w[:, sensor_cfg.body_ids, :2], dim=2)
    reward = torch.any(forces_xy > 4 * forces_z, dim=1).float()
    return r
- **LimX Dynamics tron1-rl-isaacgym (TRON1/P1 commercial biped) — closest literal match to the requested search terms in the whole survey** | https://github.com/limxdynamics/tron1-rl-isaacgym — legged_gym/envs/pointfoot_flat/pointfoot_flat.py (functions, lines 366-421) and pointfoot_flat_config.py (weights, lines 247-273)
  - _reward_foot_landing_vel: an EXPLICIT pre-touchdown vertical-velocity penalty. Gate = foot height below a small threshold AND not yet in contact AND still moving downward ('about_to_land'); penalizes the SQUARE of that vertical velocity only in that gated window (zero elsewhere). This is functionally exactly a 'contact_no_vel' / 'soft landing' term even though the literal string 'contact_no_vel' doesn't appear. Also present: tracking_contacts_shaped_force / tracking_contacts_shaped_vel — exponen
  - result: LimX Dynamics sells and ships the TRON1/P1 real hardware that this exact open-source stack targets (per repo README and their humanoid-rl-deploy-* companion repos), so this is a real-robot-oriented reward set, though I could not independently confirm from this fetch alone that THIS specific foot_lan
  - numbers: scales: foot_landing_vel = -0.15, tracking_contacts_shaped_force = -2, tracking_contacts_shaped_vel = -2, feet_regulation = -0.05, feet_distance = -100, orientation = -10.0; params: about_landing_threshold = 0.08 m, gait_force_sigma = 25.0, gait_vel_sigma = 0.25, max_contact_force = 100.0 (defined i
  > def _reward_foot_landing_vel(self):
    z_vels = self.foot_velocities[:, :, 2]
    contacts = self.contact_forces[:, self.feet_indices, 2] > 0.1
    about_to_land = (self.foot_heights < self.cfg.rewards.about_landing_threshold) & (~contacts) & (z_vels < 0.0)
    landing_z_vels = torch.where(about_to
- **AMP-based humanoid/quadruped locomotion — no bespoke impact term; softness comes from the discriminator, not a hand-crafted reward** | https://github.com/escontra/AMP_for_hardware — legged_gym/envs/base/legged_robot.py, function list confirmed at lines 1038-1063 (_reward_feet_air_time, _reward_stumble, _reward_feet_contact_forces present; no additional impact term).
  - AMP_for_hardware (Escontrela, Peng, Hafner, Iscen, Levine, Abbeel — 'Adversarial Motion Priors Make Good Substitutes for Complex Reward Functions', CoRL 2022) uses the SAME legged_gym base task reward (feet_air_time, stumble, feet_contact_forces with max_contact_force cap) as the environment's task reward, adding the AMP discriminator score on top as a style/naturalness reward.
  - result: Deployed on real Unitree A1 quadruped per the paper. Implication for the survey: in the AMP paradigm, 'soft landing' is not engineered via an explicit foot-velocity/impact penalty — it emerges because the discriminator penalizes any motion (including landings) that deviates from the reference mocap 
  - numbers: Not independently re-extracted (identical to legged_gym base; time-boxed).
  > (same three functions as legged_gym base, confirmed present by name at lines 1038, 1051, 1060 of this fork)
- **Bipedal jumping on real Cassie — explicit, phase-gated ground-impact-force reward term (closest well-documented 'GRF cap gated by phase' in the literature)** | arXiv:2302.09450 (fetched full text via https://ar5iv.labs.arxiv.org/html/2302.09450, Table II)
  - Li, Cheng, Peng, Sreenath (UC Berkeley Hybrid Robotics), 'Robust and Versatile Bipedal Jumping Control through Reinforcement Learning', RSS 2023. All reward terms use a shared exponential kernel r(u,v)=exp(-α‖u-v‖²) ∈ (0,1]. A 'Ground Impact' term r(F_z, 0) is included ONLY during the pre-landing/flight phase (t ≤ T_J) with weight 5 (curriculum Stage 1) or 10 (Stages 2-3), and is explicitly DISABLED (weight 0) once t > T_J (post-landing) — i.e. an explicit phase gate exactly of the kind the surv
  - result: Zero-shot deployed on a real Cassie robot: long jump 1.4 m, high jump onto a 0.44 m platform, turning jumps ±55°, lateral jumps ±0.3 m, backward jumps 0.3 m — no real-world fine-tuning, no global position feedback. This is the strongest documented example in the survey of an explicit GRF-based impac
  - numbers: Ground Impact weight: 5 (stage1, pre-landing) -> 0 (post-landing); 10 (stage2/3, pre-landing) -> 0 (post-landing). Post-landing 'smoothing' terms activate instead: motor velocity r(q̇_m,0) weight 15/25, torque r(τ,0) weight 3/15, joint accel r(q̈,0) weight 10/5.
  > Reward kernel: r(u,v)=exp(-α‖u-v‖₂²). Table II row 'Ground Impact', formula r(F_z,0): weight 5 for t≤T_J / 0 for t>T_J (Stage 1); weight 10 for t≤T_J / 0 for t>T_J (Stages 2,3).
- **Olympus quadruped jumping — literally named 'soft landing' family of reward terms, deployed on real hardware** | https://arxiv.org/html/2510.24584v1 (Table IV, fetched directly)
  - Olsen, Pettersen, Alexis (NTNU), 'Towards Quadrupedal Jumping and Walking for Dynamic Locomotion using Reinforcement Learning', arXiv:2510.24584. Three explicit landing-softness terms in their reward Table IV: 'Soft impact' rewards deceleration in the direction of motion using body acceleration; 'Damp landing' rewards reduced joint angular velocity after touchdown; 'Catch landing' rewards downward velocity approaching zero.
  - result: Deployed on the real 'Olympus' quadruped: vertical jumps up to 1.0 m, horizontal jumps up to 1.25 m with centimeter accuracy, plus rough-terrain walking. This is the single clearest real-world example matching the survey's literal ask ('landing velocity terms... soft-landing').
  - numbers: Exact per-term weights not extracted (fetch returned formulas from Table IV but not the adjoining weight column; would need a follow-up fetch to pull precisely).
  > Soft impact: max(0, 1 - |min(0, (a_body/a_max) · ṽ_body)|)
Damp landing: clamp(θ̇_t, 0, 1)
Catch landing: clamp(-v_z, 0, 1)
- **Robot Crash Course — impact-minimization reward for falling (not walking-gait landing, but directly on-topic for 'soft landing' mechanics)** | https://arxiv.org/html/2511.10635 (fetched directly)
  - Strauch et al., 'Learning Soft and Stylized Falling', arXiv:2511.10635. Reward = weighted sum of a per-body-part-sensitivity-weighted squared contact-force term (protects head/shoulders/elbows more than pelvis/legs) plus a root-deceleration penalty, blended via a time-dependent spline u(t) into a pose-tracking term after the impact window.
  - result: This is a 'graceful falling' controller, not a walking/landing-from-a-step controller — flagged as adjacent-but-distinct from the survey's core ask. Real-hardware deployment status NOT verified from what I fetched (would need the paper's experiments section, not reached in this pass).
  - numbers: contact force weight 200; root accel weight 0.2; orientation weight 20.0; joint pos weight 1.0; sensitivity multipliers 1/2/3/4x by body part.
  > Contact force term: -Σ_comp ‖w^c f^c_t‖²_∞, weight 200. Root acceleration: -‖v̇_t‖²_2, weight 0.2. Body-part sensitivity weights: pelvis/legs 1.0, elbows 2.0, shoulders 3.0, head 4.0. Root orientation (post-impact blend): -u(t)‖R(θ_t)ᵀe_z - R(θ̂_t)ᵀe_z‖²_2, weight 20.0. Joint positions: -u(t)‖q_t-q̂
- **Literal search terms requested — 'feet_contact_momentum', 'feet_impact', 'contact_no_vel' — NOT FOUND as exact identifiers anywhere surveyed** | GitHub code search (blocked — requires auth token, returned HTTP 401 'Requires authentication' for unauthenticated /search/code); grep.app (blocked by a Vercel bot-challenge, HTTP 429); multiple WebSearch queries with these exact quoted strings returned no matching repos/papers.
  - Despite targeted GitHub/web searches, none of these three exact strings turned up in any repository, config, or paper across legged_gym, unitree_rl_gym, unitree_rl_lab, Humanoid-Gym, Booster Gym, LimX tron1-rl-isaacgym, IsaacLab (core + G1/H1/Berkeley Humanoid task configs), AMP_for_hardware, or the arXiv papers fetched. The closest real, shipping analogs found were: LimX's `foot_landing_vel` (pre-touchdown vertical-velocity² penalty, gated by height+direction — functionally = 'contact_no_vel'/'
  - result: These three strings appear to be either (a) internal/project-specific naming from the requester's own codebase or notes rather than established public terminology, or (b) used in some non-indexed private repo. I could not confirm or deny existence beyond what unauthenticated search access allows — f
  - numbers: n/a
  > curl https://api.github.com/search/code?q=feet_contact_momentum -> {"message": "Requires authentication", "status": "401"}
- **ETH ANYmal foundational papers (Hwangbo 2019, Lee 2020, Miki 2022) — reward tables NOT independently verified; qualitative-only** | https://www.science.org/doi/10.1126/scirobotics.abc5986 (Lee 2020), https://www.science.org/doi/10.1126/scirobotics.abk2822 (Miki 2022) — both paywalled; arXiv abstract pages (2010.11251, 2201.08117) contain no reward-table detail; the public supplementary-materials repo (leggedrobotics/learning_quadrupedal_locomotion_over_challenging_terrain_supplementary) contains only build/dependency instructions, no reward code.
  - These Science Robotics papers (Hwangbo et al. 2019 'Learning agile and dynamic motor skills for legged robots'; Lee et al. 2020 'Learning quadrupedal locomotion over challenging terrain'; Miki et al. 2022 'Learning robust perceptive locomotion for quadrupedal robots in the wild') are widely cited as the origin of foot-clearance / foot-velocity-based reward shaping that later became legged_gym's feet_air_time, but I could NOT retrieve their exact reward-table formulas or weights in this session.
  - result: UNVERIFIED. Do not cite specific numbers for these three papers' reward functions without going back to the paywalled PDFs (or a university proxy) — I explicitly avoided fabricating formulas from training-data memory here.
  - numbers: n/a
  > n/a — confirmed absent, not paraphrased from memory.
- **HumanoidBench — no dedicated soft-landing/impact reward term found** | https://github.com/carlosferrazza/humanoid-bench (tree search via GitHub API, https://api.github.com/repos/carlosferrazza/humanoid-bench/git/trees/main?recursive=true)
  - HumanoidBench (carlosferrazza/humanoid-bench, RSS 2024) is a benchmark suite (H1 + Shadow Hands, MuJoCo) with 31 tasks; I found no reward.py exposing an explicit contact-impact/landing-velocity term in the locomotion tasks I could locate in the repo tree (only tdmpc2/tdmpc2/envs/tasks/walker.py surfaced as reward-adjacent, which is a baseline-algorithm task file, not the benchmark's own humanoid task definitions).
  - result: Could not confirm HumanoidBench has any soft-landing-specific reward; its per-task reward files live under a directory structure I did not fully drill into (time-boxed) — treat as UNVERIFIED rather than 'confirmed absent'.
  - numbers: n/a
  > n/a
- **Standing-still as a reward-maximizing local minimum (torque/velocity penalty too high)** | Hwangbo, Lee, Dosovitskiy, Bellicoso, Tsounis, Koltun, Hutter, "Learning agile and dynamic motor skills for legged robots," Science Robotics 4(26), 2019. https://arxiv.org/abs/1901.08652 (published version DOI 10.1126/scirobotics.aau5872). Verified by downloading the PDF and extracting text with pdftotext.
  - When joint-torque and joint-velocity penalties are weighted too high relative to the task reward, the policy finds that simply standing still is already a good local minimum, since any motion costs more than the small tracking reward it buys. This is the direct analogue of a 'standing still instead of tracking' exploit, driven by a motion-cost term rather than a contact-force term specifically.
  - result: Curriculum avoided both extremes (unnatural jittery motion at low penalty, frozen standing at high penalty), enabling the ANYmal locomotion controller reported in the paper.
  - numbers: Torque cost weight c_tau=0.005*dt, joint-speed cost c_js=0.03*dt (Table S3); curriculum factor k_c starts at k0 in (0,1) and updates as k_{c,j+1} = (k_c,j)^{k_d}
  > "Low penalty on joint torque and velocity results in unnatural motions whereas high penalty on them results in a standing behavior. The main reason for the standing behavior is that such a behavior is already a good local minimum when there is high penalty associated with motion."
- **Falling-on-purpose (early termination as an exploit) from an unbounded tracking-cost shape** | Same paper as above (Hwangbo et al., Science Robotics 2019), Supplementary Materials S3.
  - With a plain Euclidean-norm tracking cost, accumulated cost while tracking error is high can exceed the fixed termination cost, so the policy learns that falling over (terminating the episode) is cheaper than continuing to be tracked poorly -- an exploit of the termination/impact cost design, not of a contact-force term per se, but directly analogous to the 'standing still / giving up instead of tracking' pathology.
  - result: Removed the incentive to terminate early; termination became strictly less favorable than continuing.
  - numbers: Termination cost fixed at 1 ("Upon termination, agent receives a cost of 1 and is reinitialized... only the ratio between the cost coefficients is important"); logistic kernel K(x) = -1/(e^x+2+e^-x) bounds cost to [-0.25,0)
  > "An Euclidean norm generates a high cost in the beginning of training where the tracking error is high such that termination (i.e. falling) becomes more rewarding strategy. On the other hand, the logistic kernel ensures that the cost is lower-bounded by zero and termination becomes less favorable."
- **Dragging-leg / shuffling gait with unnatural base height under an under-constrained reward; fixed with a feet air-time reward** | Rudin, Hoeller, Reist, Hutter, "Learning to Walk in Minutes Using Massively Parallel Deep Reinforcement Learning," CoRL 2021 / PMLR v164. https://arxiv.org/abs/2109.11978. Verified via PDF text extraction.
  - With only basic velocity-tracking + regularization reward terms, the trained quadruped policy is 'free to adopt any gait,' converges to trotting but exhibits shuffling artifacts -- a dragging leg that never leaves the ground and abnormal base heights -- fixed by adding an explicit reward for time each foot spends in the air.
  - result: Eliminated the dragging-leg / no-flight-phase artifact and produced a policy transferable to the real ANYmal within ~20 minutes of training.
  - numbers: Feet air-time reward term: sum over 4 feet of (t_air,f - 0.5), weight 2*dt, only counted at first contact (i.e. rewards keeping each foot in the air for ~0.5s per step before it lands) -- Table 2 / Appendix A.3.
  > "Given our relatively simple rewards and action space, the policy is free to adopt any gait and behavior. Interestingly, it always converges to a trotting gait, but there are often artifacts in the behavior, such as a dragging leg or unreasonably high or low base heights. After tuning of the reward 
- **feet_air_time reward causing the opposite failure: policy refuses to step at all (frozen / no-flight)** | GitHub, isaac-sim/IsaacLab Discussion #1977, "[Question] How to tune feet_air_time weight for reward." https://github.com/isaac-sim/IsaacLab/discussions/1977
  - Community-reported (not peer-reviewed) case where adding IsaacLab's feet_air_time reward term caused the policy to never lift its feet or take any step in simulation -- i.e. the air-time incentive backfired into a frozen/hovering-adjacent gait rather than fixing shuffling. Thread is unresolved with no vetted fix.
  - result: Unresolved in the thread; flagged here as a documented but unverified/community-level (not peer-reviewed) failure mode, opposite in direction to the Rudin et al. shuffling fix above -- illustrates that the same term can cause either a no-flight shuffle or a frozen/no-step gait depending on tuning.
  - numbers: No specific weight/threshold values that worked were reported.
  > Ashutosh781 (Feb 27, 2025): "whenever I train with the feet air time reward the policy doesn't learn to take a step at all in simulation." ClaudioChiariello (Feb 26, 2025): the robot "doesn't seem to want to lift its foot" despite the reward; increasing the weight "to a very large value...caused str
- **Hopping with both feet as a degenerate gait from bare command-tracking reward; fixed by a single-foot-contact reward** | van Marum, Shrestha, Duan, Dugar, Dao, Fern, "Revisiting Reward Design and Evaluation for Robust Humanoid Standing and Walking," arXiv:2404.19173 (2024). Verified via PDF text extraction.
  - Training a humanoid standing/walking controller with only velocity/orientation command-tracking terms converges to a bilateral hopping gait (both feet leave and land together) rather than an alternating walking gait.
  - result: Single-foot-contact reward chosen as most reliable/least tuning-dependent remedy for the hopping exploit.
  - numbers: Single-foot-contact reward weight 0.1; grants reward if exactly one foot was in contact at any point in the trailing 0.2 s grace window.
  > "We found that training with just these components results in a hopping locomotion behavior, where the robot moves by jumping with both feet. While this behavior satisfies the commands, it is not desirable walking behavior indicating that additional reward terms are required... To address hopping we
- **Double-foot-contact standing reward penalizes the exact recovery steps needed to reject pushes** | Same paper, van Marum et al. arXiv:2404.19173, Section IV-B.
  - A naive fix for hopping -- rewarding double-foot ground contact while standing -- backfires: it punishes the single-leg recovery step a policy must take to reject a disturbance, and biases walk-to-stand transitions toward the nearest foot placement rather than the most stable one.
  - result: Avoided penalizing legitimate recovery stepping while still discouraging unnecessary stepping under a zero-velocity command -- an explicit example of command-gating a contact-related reward term.
  - numbers: Feet-contact reward reduced to a constant of 1 for the standing command (contact-agnostic), weight 0.1 overall (Table I).
  > "Intuitively, we might expect standing to involve rewarding double foot contact. However, this is problematic since it penalizes the recovery steps needed to reject disturbances, as that requires breaking ground contact of at least one of the feet. Additionally, when transitioning from walking to st
- **'Stompy' high-impact touchdowns from RL controllers that over-anticipate disturbances (missing ground-contact-force term)** | van Marum et al., arXiv:2404.19173, Section V-D (Energy Efficiency) and Summary.
  - Real-hardware benchmarking revealed that the RL-trained standing/walking controllers used more energy per meter than a manufacturer baseline and visibly/audibly 'stomp' -- the authors attribute this to the policy always bracing for a possible disturbance, producing harder touchdowns and larger impact forces than necessary. They explicitly flag the missing remedy: adding a ground-contact-force penalty.
  - result: Identified as an open problem rather than a solved one -- useful as evidence that the ABSENCE of an impact/contact-force penalty produces high-impact stomping, the inverse of the over-penalization failures documented elsewhere in this list.
  - numbers: ≥33 J/m of energy not usefully spent, measured over a 10 s walk on hardware vs. an Agility Robotics baseline controller.
  > "This is also apparent visually during tests, as the RL controllers stomp more loudly... at least 33 J/m are not being spent usefully by the RL controllers. We hypothesize that higher energy usage might correspond to the situation where our RL controllers would always anticipate disturbances, so we 
- **Asymmetric gait from lack of a symmetry constraint; 'fall slowly or stand still' from lack of curriculum** | Yu, Turk, Liu, "Learning Symmetric and Low-Energy Locomotion," ACM Transactions on Graphics 37(4), Article 144, SIGGRAPH 2018. https://arxiv.org/abs/1801.08093. Verified via PDF text extraction.
  - Two distinct degenerate behaviors are documented in ablations of a minimalist locomotion-RL method: (1) without any curriculum, the character fails to move or balance, degenerating into falling slowly or standing still; (2) without a mirror-symmetry loss on left/right limb actions, the character learns a visibly asymmetric gait (moves more vigorously on one side) and takes far longer to train, most pronounced in running gaits.
  - result: Mirror symmetry loss (added to the PPO objective, not the per-step reward, to avoid violating the MDP/policy-gradient assumptions) fixed the asymmetric-gait problem and sped up training; curriculum (physical assistance force that is gradually relaxed) fixed the fall/stand-still degeneracy.
  - numbers: Quantified with a Symmetry Index SI(X_L,X_R) = 2|X_L-X_R|/(X_L+X_R)% on left/right average joint torques (Nigg et al. 1987 metric), reported in their Table 2.
  > "[W]ithout the curriculum learning, the trained policies fail to move forward or/and maintain balance. On the other hand, without the mirror symmetry loss, the learning process takes significantly more trials and results in asymmetric locomotion." And separately: "the algorithm typically learns to e
- **Anomalous asymmetric flight-phase duration in a high-speed near-optimal gait mode (tangential, not clearly caused by a contact-force penalty)** | Hwangbo et al., Science Robotics 2019 (arXiv:1901.08652), 'High-speed locomotion' section.
  - A high-speed ANYmal controller converged to a flying-trot-like gait with a much longer and asymmetric flight-phase duration between diagonal leg pairs -- described by the authors as not a naturally occurring gait pattern, which they attribute to multiple near-optimal solution modes rather than to any specific penalty term.
  - result: Left unresolved; included here as a caveat that not every asymmetric or unusual gait documented in the literature is explicitly tied to a contact/impact penalty -- some emerge from reward under-constraint at the optimization limit.
  - numbers: Reported top speed of 1.2 m/s on ANYmal, 50% faster than the platform's prior speed record, achieved with this asymmetric flying-trot gait.
  > "It is close to a flying trot but with significantly longer flight phase and asymmetric flight phase duration. This is not a commonly observed gait pattern in nature and we suspect that it is among multiple near-optimal solution modes for this task."
- **A contact-aware swing-phase reward preventing a degenerate stationary/foot-slip/no-motion policy** | Coholich, Murtaza, Hutchinson, Kira, "Hierarchical Reinforcement Learning and Value Optimization for Challenging Quadruped Locomotion," arXiv:2506.20036 (2025), Section II-D7 (Trajectory Generator Swing Phase Reward).
  - A trajectory-generator (TG)-based swing-phase reward term is explicitly justified as preventing the RL policy from collapsing to a degenerate stay-in-place policy that would otherwise farm reward from foot-stay, foot-slip, and smoothness terms without actually walking.
  - result: Swing-phase reward term is reported as the mechanism that keeps the policy from settling into a stationary, sliding-in-place local optimum.
  - numbers: Not extracted in this pass (weight coefficient not captured from the excerpt); see Eq. 10 of the paper.
  > "This term rewards the trajectory generator for entering the swing phase phi_t, weighted by the frequency of the trajectory generator (f_PMTG). This term prevents the RL algorithm from learning a degenerate policy that remains at the same place and collects maximum rewards for foot stay, foot slip, 
- **Secondary/blog corroboration of air-time and ground-reaction-force remedies (not peer-reviewed, treat as lower-confidence)** | Menlo.ai blog, https://menlo.ai/blog/teaching-a-humanoid-to-walk ; and an apparently related/mirrored post at Asimov, https://news.asimov.inc/p/teaching-a-humanoid-to-walk . Both fetched successfully (not 'could not open').
  - Two blog write-ups of a humanoid RL training pipeline (appears to be mirrored/cross-posted on two domains) state, without giving the underlying failure data, that they (a) added an air-time reward specifically to prevent shuffling, and (b) penalized excessive ground reaction forces specifically to stop the policy from stomping.
  - result: Consistent in direction with the peer-reviewed findings above (Rudin et al. for air-time-vs-shuffling; van Marum et al. for GRF-vs-stomping) but should be treated as marketing/engineering-blog corroboration rather than an independently verified experimental result.
  - numbers: Air-time reward weight cited as +0.5 (Menlo.ai); no specific ground-reaction-force threshold given (Asimov).
  > Menlo.ai: "We reward air time: +0.5" (stated as the fix to encourage dynamic gaits rather than shuffling). Asimov: the team "penalize[s] excessive ground reaction forces" so "the policy to place feet gently rather than stomping. Important for hardware longevity."
- **Symptoms explicitly searched for but NOT confirmed in an accessible primary source this session** | N/A -- absence-of-evidence note based on WebSearch queries run this session (see queries: toe-walking/tiptoe + RL, feet sliding + impact penalty, tiny strides/short strides + curriculum, hovering feet + air time). Several PDF full-texts (Yu/Turk/Liu, Siekmann et al., Hwangbo et al., Rudin et al., van Marum et al.) were opened and grepped and did not contain these specific documented causal chains.
  - Despite targeted searches, I could not find a citable, opened primary source that documents (as a causal, observed reward-hacking event) any of: (1) literal 'toe-walking' emerging specifically from a contact-force/impact penalty (only general foot-slip-cost and foot-clearance-cost term definitions were found, e.g. Hwangbo et al. Eq. 7-8, which are designed to prevent slip/dragging, not documented as having caused toe-walking); (2) 'tiny strides' as a named, measured failure mode; (3) feet litera
  - result: UNVERIFIED / NOT FOUND -- flagging explicitly rather than fabricating a citation. These specific failure->term->remedy chains may exist in sources not surfaced by the searches run (e.g. paywalled venues, non-indexed lab reports, or terminology I did not try), and a follow-up pass with different sear
  - numbers: N/A
  > N/A
- **Human walking: first (impact/weight-acceptance) peak vGRF magnitude vs. speed** | https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1748-1716.1989.tb08655.x ; https://pubmed.ncbi.nlm.nih.gov/2782094/
  - Nilsson & Thorstensson (1989) measured vertical GRF in 12 subjects walking 1.0-3.0 m/s (and running 1.5-6.0 m/s) on a force platform.
  - result: Consistent with textbook value: first peak ≈1.0 BW near very slow walking, ≈1.1-1.2 BW at normal 1.2-1.4 m/s, rising toward ≈1.4-1.5 BW near the walk-run transition (~1.8-2.2 m/s).
  - numbers: First-peak vertical GRF amplitude rises from about 1.0 BW at slow walking speed up to about 1.5 BW as speed increases through the walk-run range; the paper's general statement: 'peak forces' get 'larger' with speed and force periods get shorter.
  > "The peak amplitude of the vertical reaction force in walking and running increased with speed from approximately 1.0 to 1.5 b.w." / "Increased speed was accompanied by shorter force periods and larger peak forces." (abstract, as surfaced via search — full text not directly opened; treat as tool-sum
- **Human walking/running: vGRF scaling with speed, loading rate range** | https://pubmed.ncbi.nlm.nih.gov/11415629/ ; https://www.sciencedirect.com/science/article/abs/pii/0268003395000682 ; https://www.amti.biz/archive/relationship-between-vertical-ground-reaction-force-and-speed-during-walking-slow-jogging-and-running/
  - Keller, Weisberger, Ray, Hasan, Shiavi, Spengler (1996) 'Relationship between vertical ground reaction force and speed during walking, slow jogging, and running,' Clinical Biomechanics 11:253-259. 13 male/10 female subjects, walking+slow jogging 1.5-3.0 m/s, running 3.5-6.0 m/s.
  - result: Loading rate 8-30 BW/s bracket includes walking; walking-only loading rate is toward the low end of that range (roughly single-digit to ~15 BW/s), running dominates the high end — exact walking-only sub-range not isolated in what was retrievable.
  - numbers: Max vertical force (Fz) increases linearly from 1.2 BW (walking) to ~2.5 BW at 6.0 m/s (running), then plateaus in forward-lean sprinting. Loading rate (Gz) spans 8-30 BW/s across the whole walking-to-running speed range studied. Slow jogging shows >50% higher Fz and loading rate than either walking
  > "maximum force (FZ) increased linearly during walking and running from 1.2 BW to approximately 2.5 BW at 6.0 m/s, remaining constant during forward lean sprinting at higher speeds. Slow jogging was associated with a >50% higher FZ and loading rate (GZ) in comparison to walking or fast running." (too
- **Human walking: vGRF waveform, first/second peak, trough — concrete N/kg values with speed dependence, and time-to-first-peak** | https://isbweb.org/images/conf/2001/Longabstracts/PDF/0000_0099/0039.pdf
  - Li (2001) ISB conference long-abstract, 'Comparison of vertical ground reaction forces before and after gait transition,' treadmill force-platform study, 20 subjects (24±5 yr, 74±12 kg), walk-to-run transition induced from 0.89 m/s upward at constant acceleration; forces reported per kg body mass, timing as %stance.
  - result: Gives a concrete, verified numeric example of first-peak vGRF (~1.39 BW) and its stance-phase timing (~20-24%) at fast walking speed approaching the walk-run transition; also shows first peak grows and second peak shrinks as speed increases toward running.
  - numbers: Near the walk-run transition (fast walking, roughly 1.8-2.2 m/s): first peak mean = 13.6 N/kg = 1.39 BW; second peak mean = 11.3 N/kg = 1.15 BW; trough between peaks mean = 5.6 N/kg = 0.57 BW; walking impulse mean = 4.88 Ns/kg. From the accompanying Figure 1 plot (directly read from PDF): first peak
  > "Results indicated that the first peak (mean = 13.6 N/kg) of walking VGRF before WRT was increased linearly with increase of speed. The second peak (mean = 11.3 N/kg) decreased quadratically... the trough between the two peaks was decreased linearly with a mean of 5.6 N/kg. Impulse of walking VGRF (
- **Human walking: heel vertical velocity at touchdown (footwear study)** | https://pmc.ncbi.nlm.nih.gov/articles/PMC4101391/ ; https://link.springer.com/article/10.1186/1757-1146-7-S1-A68
  - Price, Cooper, Graham-Smith, Jones — 'Testing a mechanical protocol to replicate impact in walking footwear,' Journal of Foot and Ankle Research (conf. proceedings abstract, 2014); 13 subjects, various footwear styles during walking.
  - result: Footwear strongly affects heel touchdown velocity even at a given (unspecified but presumably normal/comfortable) walking speed; flip-flops/toe-post footwear roughly double the vertical heel velocity vs. trainers.
  - numbers: Vertical heel velocity toward the floor at touchdown: 0.18 ± 0.06 m/s in trainers (sneakers) up to 0.36 ± 0.05 m/s in flip-flops.
  > "vertical heel velocity toward the floor ranged from 0.18±0.06 m/s in trainers to 0.36±0.05 m/s in flip-flops" (tool-summarized from PMC fetch, walking speed not stated in the retrievable snippet — mark walking speed as unverified for this specific study).
- **Human walking: heel vertical velocity at touchdown and time-to-peak (heel-strike transient) at preferred barefoot speed** | https://pmc.ncbi.nlm.nih.gov/articles/PMC6023236/ ; https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0197428
  - Baines, Schwab, van Soest (2018) 'Experimental estimation of energy absorption during heel strike in human barefoot walking,' PLOS ONE 13(6):e0197428.
  - result: IMPORTANT: this t_p (~17.5 ms) is the time to the sharp early *heel-strike impact transient* (a high-frequency spike some but not all walkers show within the first ~50 ms of stance), NOT the same as the smooth 'first peak' (weight-acceptance peak) of the overall vGRF curve, which occurs later (~15-2
  - numbers: Preferred barefoot walking speed: mean 1.3 m/s (range 1.1-1.5 m/s). Heel vertical velocity at touchdown, Ż_H(t0): mean -0.57 m/s (range -0.78 to -0.39 m/s). Time to peak of the heel-strike transient force, t_p: mean 17.5 ms (range 12.0-23.3 ms). Energy absorbed during heel strike: total work -3.8±1.
  > Tool-summarized from PMC fetch: "Ż_H(t0): -0.57 m/s (range: -0.78 to -0.39 m/s)" ... "Overall mean: 1.3 m/s (range: 1.1 to 1.5 m/s)" ... "Time to peak force (t_p): 17.5 ms (range: 12.0 to 23.3 ms)" — these are AI-tool paraphrases of the source PDF/HTML, not manually re-verified against the original 
- **General reference range: normal walking first peak and time window for impact peak** | https://pubmed.ncbi.nlm.nih.gov/10567759/ (abstract page returned only a cookie-wall on direct fetch — UNVERIFIED, could not open full text) ; general framing corroborated by search-engine summaries citing multiple GRF sources
  - General biomechanics-literature framing surfaced across multiple searches (Whittle 1999 Gait & Posture review 'Generation and attenuation of transient impulsive forces beneath the foot'; general GRF review sources).
  - result: Treat only as rough qualitative confirmation that heel-strike impact transients are very fast (tens of ms) and speed-dependent; do not use the specific ms figures without independently opening Whittle (1999) or another primary source, which could not be accessed in this session.
  - numbers: Impact peak (transient) magnitude is speed-dependent and occurs during roughly the first 10-50 ms of stance (search-engine paraphrase: 'first 10-30% of stance (10-30 ms)' in one summary, 'first 10-50 ms' in another — these two summarized figures are inconsistent with each other and NOT independently
  > "Impact peaks are caused by the inertial change in some portion of the body over a brief period of time, usually during the first 10-50 ms of stance." / "Magnitude of the impact peak is speed dependent and occurs during the first 10% of stance (10-30ms)." (both are WebSearch AI-generated paraphrases
- **Humanoid/bipedal robot GRF: custom active-toe research biped (comparable, quantitative)** | arXiv:2606.19699 (fetched full PDF directly and read pages 1-6)
  - Kim, Ye, Cho, Yun, Cho, Kim (2026), 'Comparative Study on Agility, Efficiency, and Impact Absorption of Bipedal Robots with Active Toes,' arXiv:2606.19699. 14-DOF biped, total mass 32.0 kg (pelvis 15.46 kg + 2×[thigh 5.71+shank 1.68+foot 0.66+toe 0.22]=8.27 kg/leg), high-fidelity Isaac Lab RL sim with realistic actuator/friction modeling, straight-line walking at 1.33 m/s, toe-equipped vs. toe-ablation configurations, ten 20 m trials each.
  - result: This is a simulation (not hardware) result for a research-grade 32 kg biped, not one of the named commercial/lab robots (Cassie/Digit/ASIMO/Atlas/G1/H1), but it is a directly quotable, unit-comparable data point (~3.1-3.3× BW average GRF at 1.33 m/s) showing robot GRF running noticeably higher than 
  - numbers: Average (heel-strike) GRF at 1.33 m/s: toe-equipped 970.0 N, toe-ablation 1021.1 N (Δ -5.0%). Robot weight ≈ 32.0 kg × 9.81 m/s² ≈ 313.9 N ⇒ average GRF ≈ 3.09-3.25× BW (note: this is an 'average GRF' walking-condition metric as defined in the paper's Table 3, not necessarily the same as the human-b
  > "we performed ten straight-line walking trials over a 20 m path at 1.33 m/s for each configuration... relative to toe-ablation, toe-equipped reduces total power by 16.9% (313.0 W to 260.2 W), CoT by 17.5% (0.776 to 0.640), and heel-strike GRF by 5.0% (1021.1 N to 970.0 N)." (verbatim, directly read 
- **Humanoid robot LOLA: walking speed context only, no numeric GRF peak found** | https://pmc.ncbi.nlm.nih.gov/articles/PMC10230186/ ; https://royalsocietypublishing.org/doi/10.1098/rsos.221473
  - Royal Society Open Science paper 'Walking like a robot: do the ground reaction forces still intersect near one point when humans imitate a humanoid robot?' comparing human gait to the humanoid robot LOLA.
  - result: UNVERIFIED / NOT FOUND: could not obtain a numeric peak-GRF value for LOLA in this session; would need direct figure inspection of the paper's PDF.
  - numbers: LOLA's typical walking speed ≈0.5 m/s vs. human preferred ≈1.3 m/s. Paper presents vGRF only as normalized plots; no numeric peak vGRF value in BW or N could be extracted from what was retrievable.
  > "with 0.5 m s−1 it walks significantly slower than the preferred human walking speed." (tool-summarized from PMC fetch — UNVERIFIED against original figures/tables; the underlying paper likely has numeric GRF data in its figures that a text-only fetch could not read out).
- **Cassie, Digit, ASIMO, Atlas, G1, H1 — direct named-robot GRF/loading-rate/touchdown-velocity values** | Multiple searches attempted, e.g. https://arxiv.org/pdf/1809.07279 (ar5iv), https://arxiv.org/pdf/2411.12047, https://arxiv.org/pdf/2605.17681, various Cassie/Digit/Atlas control papers
  - Extensive targeted search across Cassie/Digit/Atlas/ASIMO/Unitree H1 & G1 literature (RL locomotion papers, hardware-control papers, force-estimation papers, GRF-estimation papers).
  - result: UNVERIFIED / NOT FOUND for all six named commercial/lab humanoid/biped robots specifically. If precise per-robot GRF numbers are required, the most promising unexplored leads from this session are: arXiv:2605.17681 (PRIME, uses Unitree G1 with a Bertec-4060 force plate at 1000 Hz — likely has numeri
  - numbers: Cassie robot mass confirmed as 31 kg (source: search-engine aggregation of Agility Robotics specs pages, e.g. https://www.robolist.ai/robots/cassie, https://par.nsf.gov/servlets/purl/10096925 — not independently re-verified by opening the primary spec sheet). No numeric peak-GRF-in-BW, loading-rate,
  > N/A — this is a negative/absence finding, not a quote.
- **solref definition, defaults, and timestep coupling rule** | https://mujoco.readthedocs.io/en/stable/modeling.html (Solver parameters / Reference section)
  - MuJoCo's contact reference acceleration (stiffness k, damping b) is set via `solref`, default "0.02 1" (timeconst=0.02s, dampratio=1). Positive values = (timeconst, dampratio) format; negative = direct (-stiffness, -damping) format, needed for e.g. perfectly elastic collisions. Doc states an explicit hard rule tying timeconst to timestep.
  - result: Directly load-bearing for footstrike sizing: if you shrink timestep to resolve sharper impact spikes, MuJoCo's own guard (refsafe) will force timeconst (and thus contact stiffness) to scale down too unless disabled — so timestep and achievable contact stiffness/peak-force fidelity are coupled, not i
  - numbers: default solref = 0.02 1; rule: timeconst >= 2 * timestep
  > solref : real(2), "0.02 1" ... The timeconst parameter should be at least two times larger than the simulation time step, otherwise the system can become too stiff relative to the numerical integrator (especially when Euler integration is used) and the simulation can go unstable. This is enforced in
- **solimp definition and effect on penetration/force at rest** | https://mujoco.readthedocs.io/en/stable/modeling.html (Impedance section)
  - solimp (5-param impedance function d(r), default "0.9 0.95 0.001 0.5 2") sets how strongly a constraint is enforced as a function of penetration depth r. Low d = weak/soft constraint (more penetration, generally lower peak force spread over more time); high d = stiff/strong constraint (closer to rigid, higher peak force).
  - result: Confirms solimp/solref jointly control the soft-constraint spring-damper that stands in for real contact compliance — the practical knob to trade GRF peak magnitude against penetration depth and numerical stability.
  - numbers: default solimp = 0.9 0.95 0.001 0.5 2
  > The impedance d ∈ (0,1) corresponds to a constraint's ability to generate force. Small values of d correspond to weak constraints while large values of d correspond to strong constraints. The impedance affects the constraint at all times, in particular when the system is at rest. ... solimp : real(5
- **MJX-vs-CPU-MuJoCo divergence for identical solref/solimp** | https://github.com/google-deepmind/mujoco/issues/2548
  - A GitHub issue documents that MJX and vanilla MuJoCo can produce measurably different trajectories for the *same* solimp/solref values, worse for box-box collisions; increasing MJX solver iterations did not reliably fix it, and the maintainers' interim approach was re-tuning solimp/solref specifically for MJX rather than assuming CPU-MuJoCo parity.
  - result: Practical implication: a solref/solimp pair tuned/validated on CPU MuJoCo is not guaranteed to reproduce the same GRF profile once trained under MJX — re-tune/re-validate impact stiffness after porting.
  - numbers: not applicable
  > MJX and Mujoco simulations could differ slightly for specific 'solimp' and 'solref' couples [with] larger discrepancies occurring in box-box collisions. ... pushing the MJX solver iterations did not help, worse, it may increase the error ... currently mitigating the difference by finding the correct
- **MJX/mujoco_warp solver-iteration guidance for GPU RL** | https://mujoco.readthedocs.io/en/stable/mjx.html
  - Official MJX docs recommend deliberately lowering solver iteration counts on GPU because RL with domain randomization doesn't need highly converged contact forces, and Newton solver converges well in very few iterations.
  - result: This is a stated reason peak-impact fidelity in MJX/mujoco_warp training runs is intentionally looser than in a CPU MuJoCo validation run — GRF peaks measured during MJX training should not be taken as final sim-to-real numbers without a CPU MuJoCo (or mujoco_warp high-iteration) re-check.
  - numbers: example values seen in the wild: iterations=3, ls_iterations=5 (see DeepMind's own G1 MJX config below)
  > the iterations and ls_iterations attributes ... should be brought down to just low enough that the simulation remains stable [since] accurate solver forces are not as important in reinforcement learning where domain randomization is often used. The NEWTON Solver delivers excellent convergence with v
- **DeepMind's own MuJoCo Playground config for Unitree G1 (concrete numbers)** | https://raw.githubusercontent.com/google-deepmind/mujoco_playground/main/mujoco_playground/_src/locomotion/g1/xmls/g1_mjx_feetonly.xml and .../scene_mjx_feetonly_flat_terrain.xml
  - Fetched the actual MJX-tailored G1 model files DeepMind ships in mujoco_playground. Physics timestep is 2ms (500 Hz), Euler integrator with joint-damping implicit handling disabled, low solver iteration counts, foot geoms are BOXES (not capsules/spheres), contact is restricted to explicit <pair> elements (not the full contype/conaffinity matrix), foot-floor pairs use condim=3 friction=0.6 with no solref/solimp override (i.e., MuJoCo defaults 0.02/1 and 0.9 0.95 0.001 0.5 2 are used for the actua
  - result: Directly relevant baseline: DeepMind trains G1 locomotion in MJX with box feet + default (untouched) contact softness, at 500 Hz physics, and explicitly prunes the contact graph to just the pairs that matter for GRF.
  - numbers: timestep=0.002s (500 Hz); solver iterations=3, ls_iterations=5; foot box half-size 0.09x0.03x0.008 (collision) vs default-class 0.085x0.03x0.005; friction=0.6 0.6; condim=3 on foot-floor, condim=1 on self-collision pairs
  > <option iterations="3" ls_iterations="5" timestep=".002" integrator="Euler"><flag eulerdamp="disable"/></option> ... <default class="foot"><geom size="0.085 0.03 0.005"/></default> ... <geom name="left_foot" class="foot" pos="0.04 0 -0.029" size="0.09 0.03 0.008" type="box"/> ... <pair name="left_fo
- **Unitree's own official G1 MJCF (mujoco_menagerie) uses SPHERE feet, not box/capsule** | https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/main/unitree_g1/g1.xml
  - The canonical Unitree G1 model distributed via google-deepmind/mujoco_menagerie represents each foot's ground-contact surface with four small spheres (r=5mm) rather than a box, capsule, or the visual mesh, and gives them elevated `priority` so the foot's own friction/condim win the MuJoCo geom-pair combination rule over the plane's.
  - result: Contrasts directly with DeepMind's own MJX rebuild (box feet, see above) and Booster's T1 (box feet, see below) — shows there is no single industry-standard foot collision primitive; sphere-corner contact is chosen specifically to avoid mesh-mesh / sharp-edge instability while keeping few, well-defi
  - numbers: sphere radius=0.005 m, friction=0.6, condim=3, priority=1 (4 spheres per foot at the corners)
  > <default class="foot">\n  <geom type="sphere" size="0.005" priority="1" friction="0.6" condim="3"/>\n</default>
- **priority attribute and geom-pair parameter combination rule** | https://mujoco.readthedocs.io/en/stable/modeling.html (contact parameter combination rules)
  - When two geoms in a contact (e.g. foot sphere and ground plane) have different `priority`, MuJoCo does not average their solref/solimp/condim/friction — the higher-priority geom's values fully win. This is why the G1 foot class sets priority="1" — it lets the foot geom's own condim=3/friction=0.6 dictate the contact regardless of what the ground geom specifies.
  - result: For GRF sizing, this means terrain/material solref-solimp changes on the ground geom will silently have NO effect on a foot with higher priority — a common footgun when domain-randomizing 'ground stiffness' by editing the floor geom instead of the foot geom.
  - numbers: not applicable
  > condim If one of the two geoms has higher priority, its condim is used. If both geoms have the same priority, the maximum of the two condims is used. ... friction ... if one of the two geoms has higher priority, its friction coefficients are used. Otherwise the element-wise maximum of each friction 
- **Booster Robotics T1 foot collision geometry** | https://raw.githubusercontent.com/BoosterRobotics/booster_assets/main/robots/T1/T1_23dof.xml
  - Booster's official T1 MJCF (booster_assets repo) gives each foot an invisible flat BOX collision geom (separate from the visual mesh, alpha=0), no explicit solref/solimp override found anywhere in the file, and the ground plane is set to condim="1" (frictionless) globally — friction/condim for the actual foot-ground contact is therefore effectively driven by whatever the foot geom or a <pair>/<default> elsewhere specifies (priority rule again).
  - result: Confirms box-foot as a second real-world convention (alongside DeepMind's MJX box feet) distinct from Unitree menagerie's sphere-corner approach.
  - numbers: box half-size 0.1124 x 0.05 x 0.0218 m; ground condim=1
  > <geom name="ground" type="plane" pos="0 0 0" size="0 0 1" material="matplane" condim="1"/> ... <body name="left_foot_link" ...>\n  <geom type="mesh" contype="0" conaffinity="0" ... mesh="left_foot_link"/>\n  <geom size="0.112434 0.05 0.02183" pos="0.0101079 0 -0.0214208" type="box" rgba="0.4 0.4 0.4
- **unitree_rl_gym sim2sim MuJoCo deploy timestep vs control rate (concrete decimation numbers)** | https://raw.githubusercontent.com/unitreerobotics/unitree_rl_gym/main/deploy/deploy_mujoco/configs/g1.yaml
  - Unitree's own sim2sim MuJoCo deployment config runs physics at 500 Hz and decimates 10:1 to a 50 Hz control loop — a directly comparable, named example of physics-timestep vs control-rate ratio for a real deployed humanoid policy.
  - result: Direct evidence for the 'contact sensor sampling rate vs control rate' question: contact/GRF is resolved every 2 ms physics step, but the policy/observation only updates every 20 ms — 10 physics steps of contact history occur per control step, so any wrapper that reads mjData contact/sensor state on
  - numbers: simulation_dt=0.002s (500 Hz), control_decimation=10 -> control at 50 Hz (20 ms)
  > # Simulation time step\nsimulation_dt: 0.002\n# Controller update frequency (meets the requirement of simulation_dt * controll_decimation=0.02; 50Hz)\ncontrol_decimation: 10
- **MuJoCo touch/force sensors are computed at the physics timestep, and can silently miss contact forces if site/geometry doesn't enclose the real contact** | https://github.com/google-deepmind/mujoco/issues/228 (maintainer comment, fetched via GitHub REST API)
  - MuJoCo touch sensors sum contact normal forces occurring inside a site's volume, evaluated at the physics step; a maintainer (Yuval Tassa) directly explains a common failure mode where the sensor reports near-zero because the site is too small to contain the actual contact points ('no surface contact' in MuJoCo — only point contacts).
  - result: Relevant caveat distinct from control-rate aliasing: even at full physics-step resolution, a touch sensor can under-report GRF if its site geometry doesn't geometrically cover the actual (few, point-based) contacts MuJoCo generates — worth checking site sizing before trusting a 'touch' sensor's peak
  - numbers: not applicable
  > Touch sensors report contact forces that occur inside the volume of a site, as explained here. Your sites are too small. There is no surface contact in MuJoCo, the sites need to cover a large volume to capture the few contacts.
- **Contact sensor / control-rate relationship — no single official doc page found stating an explicit rule** | searched mujoco.readthedocs.io/en/stable/computation/index.html and modeling.html
  - Could not find an official MuJoCo doc page that explicitly states in one place 'sensors sample once per mj_step, not once per control step' as a standalone rule (this behavior is implied by mj_step's structure and by the concrete decimation configs above, but I did not find a single canonical doc sentence saying so).
  - result: Marking this specific framing as unverified from primary docs — the behavior is inferable (sensors read mjData state which is updated every mj_step, and RL wrappers that call mj_step N times per env.step before reading obs will only see the state after the last substep unless they explicitly aggrega
  - numbers: not applicable
  > (no direct verbatim statement found)
- **Timestep effect on impact/energy behavior — elastic-jump discussion with concrete solref numbers** | https://github.com/google-deepmind/mujoco/discussions/2347
  - A GitHub discussion with a DeepMind maintainer walks through why energy appears to spike/vanish during a ground impact ('dark energy' hidden in contact deformation) and gives concrete solref/integrator/cone changes that reduced floor penetration from ~1 m to ~0.2 m.
  - result: Shows the direct, large-magnitude effect of stiffening solref on penetration depth (and by extension, on how sharply GRF spikes at footstrike) — but this was a WebFetch-summarized page, so treat the exact bracketed numbers as paraphrase-level, not guaranteed character-for-character maintainer wordin
  - numbers: solref tightened to ~[1e-3, 1] (vs default 0.02/1) cut penetration from ~1 m to ~0.2 m
  > Currently MuJoCo doesn't add elastic energy in contacts to those values. [...] solref tuning: Lower values (e.g., [1e-3, 1]) reduce penetration depth [...] The user experimented with solref=[-1e-3, 0] and various solimp settings, finding that reducing the first solref value decreased floor penetrati
- **Sim-to-real robustness research: deliberately randomizing solref timeconst to emulate stiff-to-compliant ground** | https://arxiv.org/html/2504.06585 (Sim-to-Real of Humanoid Locomotion Policies via Joint Torque Space Perturbation Injection) and https://arxiv.org/pdf/2504.13619 (Robust Humanoid Walking on Compliant and Uneven Terrain with Deep RL)
  - Two arXiv humanoid papers explicitly manipulate MuJoCo's solref timeconst as their mechanism for testing/training robustness to unmodeled ground compliance, treating it as a stand-in for real ground stiffness variation and a sim-to-real gap probe.
  - result: Gives two concrete, citable timeconst values/ranges used specifically to probe humanoid sim-to-real footstrike-compliance gaps. Note: these came via WebFetch/WebSearch synthesis, not a raw-curled PDF/HTML quote, so exact wording is paraphrase-level; the numeric values (0.1; range 0.02–0.4) were cons
  - numbers: test-time solref timeconst = 0.1 (vs MuJoCo default 0.02); randomization range 0.02–0.4 s for feet-side solref timeconst
  > Ground contact stiffness is reduced by setting the solref time constant to 0.1 [in the test/robustness environment; not used during training]. ... [in the terrain-compliance paper] the time constant parameter of the mass-spring-damper model of contact constraint between feet and ground [is varied] i
- **General MuJoCo timestep/integrator guidance (not impact-specific but foundational)** | https://mujoco.readthedocs.io/en/stable/computation/index.html (via WebFetch synthesis) and https://github.com/google-deepmind/mujoco/issues/954 (comments fetched via GitHub API)
  - Official docs state the general principle that smaller timestep improves stability/accuracy of any integrator (Euler, RK4, implicit, implicitfast) at the cost of speed, and that Euler handles joint damping implicitly (recommended over viscosity for stability). A real GitHub issue shows RK4 at very small timesteps still going numerically unstable under a torque controller with no force limits, resolved by switching to implicit/implicitfast — illustrating that raw timestep reduction alone doesn't 
  - result: Cautionary precedent: don't assume 'shrink the timestep' alone fixes impact-spike/instability issues — in this real thread the actual bug turned out to be unbounded controller torques, not integrator/timestep choice, until diagnosed with actuator-force sensors. The general integrator-accuracy statem
  - numbers: example unstable timesteps tested: 0.0004s, 0.0005s, 0.005s with RK4
  > This generally expected, but at larger timesteps. Can you try the implicit or implicitfast integrators? [maintainer yuvaltassa, issue #954] ... 'They both go unstable when setting timestep = "0.0004"' [OP reply confirming implicit/implicitfast alone didn't fix an actuator-code bug]