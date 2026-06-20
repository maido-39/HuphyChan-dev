# 18 · 연구 로드맵 — 하드웨어 설계 + 자연/효율 보행

> [!abstract] 큰 그림
> 이 프로젝트의 본질 = **하체 휴머노이드 하드웨어 설계**. RL 정책은 *현실적 하중을 만드는 도구*다. 목표 = **사람처럼 자연스럽고 에너지 효율적인** 보행. → **자연·효율 gait ↔ 하중 대표성**은 한 몸: 이상한 gait는 비대표 하중을 만들어 잘못된 HW로 이어진다. 그래서 "자연·효율 gait"는 목표이자 *좋은 설계 데이터의 전제*.

## 두 축
- **A. 하중 특성화 → 설계 스펙** (어떤 조인트/연결부를, 어떤 힘에, 얼마나 강하게) — ★핵심 산출
- **B. 자연/효율 보행** (목표 + 하중 대표성 보장)

---

## 오전: 야간 결과 검토 (stage-3/4)
- **stage-3 (에너지/toe reward)**: 재측정 → toe 사용%↑? 관절토크↓? CoT↓? 진동(>5Hz)↓? 추종 유지? → 에너지 튜닝 성패 판정.
- **stage-4 (rough 전이)**: 계단/경사 보행 성립? 지형별 하중?
- 결과에 따라 **gait 방향 결정**: 에너지 튜닝으로 충분 vs AMP/주기보상 필요.

## Theme 1 — 하중 → 설계 (★우선)
| # | 작업 | 산출 |
|---|---|---|
| 1.1 | **전체 측정 캠페인** — 속도(0.5/1/1.5/2.0)·질량(0.9-1.2×)·지형(평지/계단/경사)·외란(push) sweep, **clipped+unclipped** | 전 운용영역 하중 데이터셋 |
| 1.2 | **조인트 sizing** — `analyze_motor_util.py`를 전 조건/unclipped로 확장 (% 정격/Peak) | 어느 모터 상향(발목)·하향(무릎)·기어비 |
| 1.3 | ★**연결부/링크 구조 설계 [신규]** — 측정된 **6축 링크 반력**(Fx,Fy,Fz,Tx,Ty,Tz)을 **굽힘모멘트 √(Tx²+Ty²)·축력 Fz·전단 √(Fx²+Fy²)·비틀림 Tz**로 분해 → 링크 단면·하우징·볼트패턴·베어링 강도 스펙 | "연결부 어떻게/얼마나 강하게" 정량 답 |
| 1.4 | **Duty cycle / 열** — peak vs RMS(연속) + % 정격 → 연속정격 초과 관절(발목 280-300%)의 열·피로 마진 | 간헐 vs 연속 사이징 |
| 1.5 | **Worst-case envelope** — 시나리오별 관절/링크 peak (push→고관절, 고속→발목, 착지→무릎, 계단→?) | 설계 하중 포락선 |

> 측정 인프라(`measure.py`: 관절토크 + 6축 링크반력 + GRF)는 이미 다 로깅 중 → 1.3 구조분석 스크립트만 신규 필요.

## Theme 2 — 자연/효율 보행 (목표 + 하중 대표성)
| # | 작업 |
|---|---|
| 2.1 | 야간 **에너지/toe 실험 정량 평가** (toe 사용·토크·CoT) |
| 2.2 | **사람다움/효율 지표**: Cost-of-Transport (목표 보행 ~0.2-0.4), **Harmonic Ratio**(체간가속 FFT 대칭·부드러움), 관절각 궤적 vs 인간 보행 데이터, gait 위상/타이밍 |
| 2.3 | 부족하면: **AMP**(adversarial motion prior, mocap 스타일매칭) 또는 **Siekmann 주기보상**([[Paperreview/siekmann-periodic-reward]]) — 둘 다 toe 적재에도 기여 |
| 2.4 | 토크리밋·에너지 reward가 **대표성**을 해치지 않는지(과도 절약→비현실 gait) 검증 |

## Theme 3 — sim2real 충실도 (하중이 "진짜"여야)
- **액추에이터 모델**: RobStride 토크-속도 곡선·마찰·관성을 sim에 반영(현재 ImplicitActuator) — 하중 정확도 직결.
- **접촉 모델**: 발 콜라이더·접촉강성 검증 (toe 접촉 42% HF가 모델 아티팩트인지).
- **blind/teacher-student 정책**(height_scan 없이) — 실제 배포·하중 생성 gait ([[13_sim2real_height_scan]]).

## Theme 4 — 설계 반복 루프 (닫기)
1. 측정 하중 → **스펙 갱신**(모터 사이징·링크 강도·기어비) via `robstride_biped.yaml` 핫스왑([[08_robot_hotswap]]).
2. 갱신 스펙으로 **재학습·재측정** → 하중이 새 한계 내로 들어오는지(설계 수렴) 검증.
3. 수렴까지 반복 → **최종 HW 설계 데이터시트**.

## 추가 — HW 심화 + Toe Ablation + CAD 연동 (사용자 요청 · 리서치 `ws2d3t2mh` 진행중 → 리포트 예정)

### Toe Ablation (Theme 2 보강) — *어떻게 비교할지 메트릭 연구 중*
- **구성 비교**: passive toe(k=60) vs **rigid/locked** vs **no-toe(평발)** vs 강성 몇 단계. 각 구성 **재학습**(seed≥3, 동일 DR/명령/seed로 교란통제).
- **메트릭 후보**(연구 확정 예정): **CoT**(에너지효율) · **발-지면 충격**(GRF peak·loading rate·heelstrike transient) · **관절 토크·파워**(특히 *ankle offload* 여부) · 낙상/push-recovery · 추종오차 · **Harmonic Ratio**(부드러움) · (AMP 도입 시) **discriminator/style loss**(사람다움).

### 모터/감속비/속도·파워 (Theme 1 보강) — *"힘→강도"의 정량 답*
- **모터 선정 적정성 + 대안**: RobStride 라인업 + **동일 슬롯·유사 토크/형태** 대안(Unitree·MyActuator·CubeMars·T-Motor) 비교표. **사이즈가 1차 제약**.
- **무릎 감속비**: 현재 1:3(360 N·m, 측정 flat peak ~196) → **1:2 / 1:2.5** 검토 — 출력토크↓·**출력속도↑**·반사관성(~비²)·백드라이브성·효율. 평지 vs 계단 요구 분리.
- **토크-속도 검증**: peak/정격뿐 아니라 **요구 (토크, 속도) 점이 모터 토크-속도 포락선 안인지** (고속서 토크 강하/약자장).
- **부위별 파워(W)**: P=τ·ω (+전기 τ·ω/η + i²R 동손), **peak/RMS**, 총 전력예산 → 부위별 W 막대. 로그된 토크×관절속도로 산출.
- **무게/페이로드 민감도**: 체중 감량 / **+10 kg 페이로드** → 부위별 힘·토크·파워·gait 변화. **질량 sweep 재측정**(RL gait가 적응하므로 스케일링만으론 부족). 위치(몸통 vs 말단)별 영향 구분.

### Theme 5 — Fusion 360 ↔ Isaac Lab 연동 (리포트)
- **파이프라인**: Fusion360 → URDF/MJCF → USD. **링크/조인트 명명**(우리 env의 컨테이너-Xform 네스팅 주의), **질량/관성/COM**(Fusion 물성 vs 수동), **재질/밀도**, **메시 단순화**(visual/collision 분리·convex 분해·decimation), **프레임/단위**(mm↔m·축).
- **함정 체크리스트** + **CAD 수정→재변환→재학습/측정 반복 루프** 정립 (Fusion에서 모터무게/링크구조 반영 방법).

## 우선순위 (내일)
1. **오전 야간결과 검토** → gait 방향 확정.
2. **Theme 1.3 연결부 구조분석 스크립트** (신규, 핵심 산출 — "연결부 설계"의 정량 답).
3. **Theme 1.1 전체 측정 캠페인** (envelope sweep) → 1.2/1.4/1.5 분석.
4. **Theme 2.2 사람다움/효율 지표** (gait 품질 = 하중 대표성 보증).
5. 결과 종합 → **Theme 4 스펙 갱신 1차** (발목↑·무릎↓ 등).

관련: [[07_measurement]] [[16_dr_expansion]] [[17_toe_usage_vibration]] [[08_robot_hotswap]] [[00_overview]]

## 리서치 ws2d3t2mh 추가 작업 (자동 반영)
- [ ] INFRA (do first, blocks everything): in wrench_logger.py record() write omega_<joint>=joint_vel[j] and P_mech_<joint>=tau*omega (and joint_pos_<joint>) -- the values are already read at lines 71-72 but never written. Unblocks CoT, electrical power, torque-speed validation, and the toe ankle-offload metric.
- [ ] ANALYSIS: extend analyze.py / analyze_motor_util.py with (a) per-joint peak-W vs RMS-W grouped bars + rated-W line, (b) electrical power P_elec = max(0,tau*omega)/eta + 1.5*(tau/(Kt*G))^2*R using the RS00/03/04 Kt/R table (eta_drive=0.80 as flagged uncertainty), (c) headline TOTAL avg-W and peak-W + CoT, (d) per-joint torque-SPEED scatter overlaid on each actuator envelope.
- [ ] ANALYSIS: add GRF impact-peak + loading-rate (20-80% slope) extraction from GRF_<foot>_z, and trunk Harmonic Ratio from finite-differenced base accel (add full root-state logging, currently only base_height is logged).
- [ ] SOURCING: pull the official RS03/RS04 (and RS00) torque-SPEED curves and rotor inertia from github.com/RobStride/Product_Information; re-confirm RS04 corner speed (~100 rpm) at your actual bus voltage. Bench-measure RS00 phase resistance (not published) to firm up ankle_roll copper-loss.
- [ ] GEAR STUDY: run the knee 1:3 vs 1:2.5 vs 1:2 comparison as a 3-config retrain. For each, edit YAML knee effort_limit/velocity_limit_rpm/armature(=0.0097*N^2) AND the knee MOTOR_RATING in BOTH analyze scripts; validate via torque-speed scatter at high-torque and high-speed corners. Adopt 1:2.5 unless unclipped logs show knee spikes >240 N*m.
- [ ] ABLATION: run the single-factor foot ablation A/B/C first (passive k=60 / rigid / no-toe), N>=3 shared seeds, identical DR/rewards/steps, eval on held-out seeds, IQM + bootstrap CIs, pre-registered decision rule. Add D(k~30)/E(k~90-120)/F(damped) only if the morphology effect is real. A,D,E,F are YAML-only (no USD reconvert); B is high-stiffness YAML; C needs an MJCF geometry edit + reconvert.
- [ ] PAYLOAD: after picking the winning foot config and knee ratio, run the mass sweep {0.8/1.0/1.2 uniform} + the torso-vs-distal +10 kg location pair, RETRAINING at each point (+10 kg is outside the +-5 kg training DR). Confirm RS00 ankle_roll is the binding actuator under distal payload; recommend high/centered payload placement.
- [ ] VALIDATION HARNESS: bake the 4-point CAD-export regression (TOTAL mass==51.8 kg, COM sane, forward=+X / feet along +Y, sensors find bodies) into a script gated on every convert_asset.py run so a CAD change cannot silently corrupt the sim.
- [ ] PUSH PROTOCOL: generalize measure.py's single 250 N lateral push (line 141) into a standardized magnitude (50-300 N) x direction sweep at fixed gait phase, reporting push-recovery success% per config -- needed as the robustness guard metric in the ablation.
- [ ] FUTURE FACTOR: treat AMP human-likeness (discriminator score) as a SEPARATE factor on the 2-3 best foot configs, not mixed into the morphology ablation; meanwhile compute an offline DTW/feature-distance human-likeness proxy from joint-angle/GRF trajectories.
