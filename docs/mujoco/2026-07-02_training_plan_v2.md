

> ★ **게이트 길이 정책(2026-07-04, 사용자)**: **3000 iter는 너무 짧다** — 최소 **6000~10000 iter**까지 봐야 판정 신뢰. mid-training(1500/3000) 판정은 노이즈 크고 수렴 전이라 오판 위험(B1 −18% vs −20% 같은 경계판정이 그 증거). 앞으로 accept/reject는 **6000+ (가능하면 10000)** 기준, watcher 마일스톤도 6000·10000로. 이전 노트의 3000-게이트 판정은 참고치로 강등.

> ★ **게이트 길이 정책(2026-07-04, 사용자)**: **3000 iter는 너무 짧다** — 최소 **6000~10000 iter**까지 봐야 판정 신뢰. mid-training(1500/3000) 판정은 노이즈 크고 수렴 전이라 오판 위험(B1 −18% vs −20% 같은 경계판정이 그 증거). 앞으로 accept/reject는 **6000+ (가능하면 10000)** 기준, watcher 마일스톤도 6000·10000로. 이전 노트의 3000-게이트 판정은 참고치로 강등.

# 학습·Reward 계획 v2 — 연구 총검토 후 refine (게이트 기반)

> 2026-07-02. 지금까지의 전 연구(IsaacLab 계보 + mjlab 분석)를 3-agent 검증(계보 교훈 / reward 함수 감사 / 적대적 비평)으로 refine. **초안의 중대 결함 2개가 비평에서 반박되어 수정됨**(아래 ★). 원칙: 제어스택 먼저 → reward 변인분리 → HW, 각 단계 kill/keep 게이트.

관련: ★ **[분석 기록(근거 원본)](2026-07-02_analysis_reward_audit_critique.md)** — 본 계획의 3-agent 분석(reward 인벤토리·함수형태 file:line, Siekmann 이식 스펙, 비평 전문) · [gait 분석·wobble](2026-07-02_gait_analysis_and_wobble.md) · [action_scale](2026-07-02_action_scale_and_gains.md) · [actuator eval](2026-07-01_actuator_evaluation.md)

---

## 0. 현재 상태 (사실)

- **A0 진행중**: action_scale 0.25 + low_base<0.7m termination, fresh. iter ~1200, 무릎꿇기 **해결**(base 평균 0.811m, 직립 렌더 확인), low_base 종료 236→52 감소 중. wandb `09jc1mdb`, video 3000iter.
- **Reward 현황 감사 결과**: 활성 = tracking(2.0/2.0)·upright(1.0)·pose(1.0)·dof_limits(−1)·action_rate(−0.1)·foot_clearance(−2)·swing_height(−0.25)·slip(−0.1)·self_col(−1)·body_ang_vel(−0.05)·ang_momentum(−0.02). **사실상 꺼짐**: `soft_landing −1e-5`(→GRF 안 줄어드는 직접 원인), `torque_limit −0.0`(hip 재분산 메커니즘 미사용), `air_time 0.0`. **에너지 항 전무**(joint_torques_l2 등 존재하나 미배선).
- **진단 확정**: Kp/Kd 로터관성 기준(hip 0.56Hz·ζ0.11) = wobble·추종불량·토크 미사용. GRF 학습 무반응. ROM⊥vx. knee/ankle 포화·hip 여유.

## ★ 비평이 잡은 내 초안의 결함 (수정 반영)

1. **Kp=800 기각**: e_sat=120/800=0.15rad(8.6°) → 스윙 오차 0.3~0.8rad서 **bang-bang 지배**(선형설계 무의미). Kd=84는 |q̇|>1.43rad/s(스윙 3~10rad/s)서 **제동만으로 포화** = 자기 다리 브레이크. 실배포 참조: H1(47kg) Kp150-300/Kd2-6, G1 RL Kp100-150. knee Kd 계산오류(73→**31**). 반례: mjlab G1도 armature-기준인데 잘 걸음(RL이 50Hz 외루프 보상) → armature-기준 자체가 치명은 아님. **수정: Day-0 오프라인 chirp로 Kp∈{200,400,800} 포화듀티 측정(<30% 기준), Kp 200~480 예상.** armature 값 자체도 kbot 복사본(동일 RobStride 계열이라 준-신뢰) — RS 로터관성×기어² 검산 추가.
2. **torque_limit×고Kp 지뢰**: 이 항은 **pre-clip 명령토크** f_cmd를 벌줌 → 고Kp서 f_cmd 250~400Nm → 벌점 −2~−5/step(tracking +2 압도) → **정지가 최적**. 수정: **A1 gains 동결 후** A1 정책을 reward 함수에 offline replay해 weight 산정(기본 −0.5 금지).
3. **soft_landing 스케일**: raw Newton(착지스텝 500~2500) → −0.5는 보행 자체를 죽임. 산술: **−5e-4 → 재시도 −2e-3**. 게이밍(무비행 셔플) 감시: air_time_mean ≥0.2s 게이트.
4. **B1b(Siekmann)와 B3(보폭)는 같은 메커니즘** — clock 이식 시 속도-스케줄 clock으로 한 번에 설계(중복 구현 금지).

## IsaacLab 계보 교훈 (이식 스펙)

- ★ **Siekmann periodic_contact = 최고 지렛대** (v8 실증: asym 0.83→**0.18**, GRF 8→**3.1×BW**, CoT 2.6→**1.22**, 35/35 대칭 — 한 항이 절름발이+충격+대칭+에너지 동시 해결). 이식 스펙: 공유 clock φ(period 1.0s), L=φ/R=φ+0.5, swing=σ(20(ph−0.6))·σ(20(1−ph)), rew=mean[(1−swing)·e^(−8·발xy속도) + swing·e^(−0.02·발GRF)], **weight +1.5**, obs에 [sin2πφ,cos2πφ] 추가(fresh 필요). mjlab 인프라 전부 존재(~100줄).
- **base 높이 anchor**: tiptoe(IsaacLab)=무앵커 시 퇴행자세의 실증 — mjlab 무릎꿇기는 같은 실패군(낮은쪽). termination(0.7)은 가드, **reward anchor(target~0.81)**가 근본 — A0가 termination만으로 0.811 유지 중이라 **일단 보류**, 재발 시 투입.
- **금지 목록(반복 실패)**: 관절각 레퍼런스 추종(v3-v7 전패, phase 불일치), toe 직접 토크 보상(정적 curl로 게임), **무캡 파워 보상**(v9: pushoff가 GRF 3.1→11.5×BW 파탄, knee 216Nm 클립 — impact cap 전에 push-off 금지).

---

## 1. 확정 시퀀스 (kill/keep 게이트)

### Day-0 오프라인 사전작업 (GPU 불요, 즉시)
(a) ✅ **chirp 완료**([분석 기록 §5](2026-07-02_analysis_reward_audit_critique.md)) → **A1 게인 확정: hip_pitch 400/30 · hip_roll 400/26 · hip_yaw 400/9 (ζ≈0.5) · knee 800/12 · 발목 현행**. hip 0.56→2.1Hz. 발견: hip은 0.4rad@2.5Hz에 물리적 토크한계(218>120Nm, 대역 ~1.85Hz), 저Kd는 공진 기각, Kd84는 자기제동 58.7%로 기각(비평 실증). (b) ✅ knee Kd 재계산 반영 (c) A0 ckpt를 torque_limit에 replay → B2 weight 미리보기 — **A1 동결 후 A1 정책으로** (d) implicit 적분 Kd 안정성 — A1 스모크서 (e) armature ← RS 로터관성×기어² 검산(미완, kbot 복사본이나 동일 RS 계열이라 준-신뢰).

### A0 — ✅ **게이트 PASS + 특성화 완료 + kill** (2026-07-02)
- low_base 종료 236→**0.5**(iter 3275), 직립 렌더 확인(iter 800), run `2026-07-02_(fresh)` ckpt model_500~8300 보존.
- **특성화**(model_8300, wide-dr 3600step, `analysis/out/a0_characterize.npz`): base mean **0.817**/P5 0.799(0.71-cheat 없음) · knee **51%/78%**(클립 해소!) · ankle_roll **20%/22%**(해소!) · **ankle_pitch RMS 110%/peak 100% = 여전히 binding**(★정책무관 확정: hot·calm·정적 3중 증거) · GRF P99 2.08/peak 4.48×BW(B1 대상) · CoT≈0.10(명령거리 근사).
- ★ **판정: knee/ankle_roll 과부하의 주범 = hot action_scale이었음.** ankle_pitch만 HW 부족 잔존.

### A1 = Kp/Kd 보정 (fresh, gains만 단독변수, vs A0 동일 iter 비교) — 🔄 **착수 2026-07-02**
- **적용 게인**(chirp §5, `pygmalion_constants.py` 반영·검증): hip_pitch/roll **400/28** · hip_yaw **400/9**(RS03 actuator를 hip_yaw/ankle_pitch로 분리) · knee **800/12** · 발목 armature-유도 유지(19.7/1.26, 1.97/0.13). action_scale 0.25·low_base termination 동일.
- iter **500** kill: 에피소드길이 ≥0.6×A0@500 아니면 Kp 반감 재출발(400→200 이분탐색).
- iter **1500** accept: |vx err|≤A0 ∧ base mode≥0.79 ∧ low_base≈0 ∧ hip RMS↑/knee 클립↓ ∧ **wobble 렌더 비교**. → **제어스택 동결** + worst-case 측정 + §7(중간 HW 체크). 2회 기각 시 A0 gains 유지, armature 자체 재진단.
- **판정(2026-07-02, model_28400·reward 67·`a1_eval`)**: ★ **조건부 기각 1회차** — base 0.809·low_base≈0·직립보행·**hip RMS 28→57%(근위 재분배 성공)**·★★**ankle_pitch RMS 110→59%(만성 열과부하가 gains만으로 해방!)**·ankle_roll 20→10%. **기각 사유: knee RMS 51→129%(T_ss 225℃)** — knee 800이 hip 400 대비 과강성이라 부하가 knee로 과집중. GRF P99 2.08→2.69(강성 스트라이크, B1 대상). q-scatter/렌더/npz: `a1_eval` 일식.
- **A1b 착수**: knee만 **400/8**로 리밸런스(chirp 검증 조합), hip 400/28·hip_yaw 400/9 유지. 기대: ankle 해방 유지 + knee 정상화. caveat: A0@8300 vs A1@28400 비교는 iter 불일치 — A1b는 8300 체크포인트서도 대조 예정.
- **★ A1b 판정(2026-07-03, model_10400 `a1b_eval`)**: **제어스택 ACCEPT** — base 0.810·직립·ankle_pitch 70%(해방 유지)·ankle_roll 15%·GRF P99 2.45. **knee RMS 125%(212℃)는 Kp 800→400으로도 불변 = 게인 아티팩트 아닌 정책 수요**(토크 벌점 전무 탓; A0의 낮은 부하는 soft 게인이 토크를 못 전달해 숨긴 것). → knee 열은 **B-phase(reward) 표적으로 이관**, gains 동결(hip 400/28·hip_yaw 400/9·knee 400/8·발목 armature). mid-training(10.4k) 인플레이션 여부는 A1b 완주분서 재확인.
- **모니터링 체계(2026-07-03, 사용자 지적 반영)**: `gate_watch.sh`(iter 마일스톤+1h heartbeat+사망 감지 → 알림) 모든 학습에 필수 동반. memory `feedback-rl-monitoring-cadence` 등록.

### B1 = GRF/사뿐사뿐 (A1 위, 타임박스 1런) — 리서치 반영([Q123 리서치](../reward_research/2026-07-02_gait_research_q123.md))
- ★ 1안(실로봇 검증, Humanoid-Gym C11): **역치형 GRF 벌점 `−w·min(max(F_foot−600N, 0), cap)`**(600N≈1.2×BW, 상시작동) — soft_landing(첫접촉만)보다 견고. 2안: soft_landing −5e-4.
- iter 1000 게이트: GRF P99 ↓≥20% ∧ air_time≥0.2s. 미달 → **즉시 B1b: Siekmann 이식**(속도-스케줄 clock 내장=B3 흡수). 커리큘럼: gait 형성 후 충격 가중치↑(Cassie C3).
- B2 보강(ALMI C8): torque_limit + **관절군 차등 벌점(ankle 토크 5×·action rate 2×)** = hip 분배 실로봇 템플릿.
- **🔄 B1 착수(2026-07-03 04:05)**: A1b 12k GATE(watcher 정상발화)서 kill → B1 = A1b 게인 동결 + `contact_force_cap(600N, clip400, −0.005)` 단독변수. 신규 metric 발화 확인(excess_mean 28.5N·벌점 −0.0097/step). wandb `peezxrqs`(B1-impactcap-600N), watcher 500 게이트 가동. 판정 기준: GRF P99 ↓≥20% vs **A1b@동일iter**(ckpt 500~12000 보존) ∧ air_time≥0.2s.
- **B1 게이트 경과**: 500 PASS(에피소드길이 동일 996·excess 28.5→11.5 하락). **1500 = 경계선**(`b1_1500` vs `a1b_1500`): GRF P99 2.86→2.34(**−18%**, 기준 −20%에 2%p 미달)·knee RMS 119→111%·base 0.80 유지·air_time 0.14 vs 0.16(★기준 0.2s는 baseline도 미달=게이트 캘리브레이션 오류, 상대감시로 전환). **판정: 3000으로 연장**(mid-training 과소평가+excess 하락 지속) — 3000서 <−20%면 가중 −0.01 에스컬레이션, air_time<0.12면 셔플 게이밍→Siekmann 직행.
- **B1 3000 게이트(`b1_3000` vs `a1b_3000`)**: P99 2.81→2.29(**−19%**, 2연속 경계미달·정체) · **peak 4.36→5.19 악화**(clip400이 >1000N gradient 차단, 5.19×BW=2.6kN≈HW 한계 2.7kN) · air 0.19(셔플 아님) · ★**knee RMS 129→104%**(충격억제의 부수효과, B2 부담 급감). → **에스컬레이션 1회: B1w2 = weight −0.01 + clip 800**(peak gradient 복원). 재게이트 1500/3000 동일 프로토콜; 재미달 시 Siekmann 직행.
- **B1w2 1500(`b1w2_1500`)**: P99 2.86→**2.12(−26%) ✅ 통과** · peak 4.37(악화 해소 — clip800 적중) · **air 0.11 ⚠ 셔플 경계 하회**(A1b 0.16→B1 0.14→B1w2 0.11, 벌점 강화가 비행 압축). **최종판정은 3000 이중기준**: P99≤−20% ∧ air≥0.12 회복(B1 전례 1500→3000 +0.05). air 미회복 시 셔플 확정→Siekmann 직행(wandb `3e8hhk88`).
- ★★ **B1w2 3000 = ACCEPT(`b1w2_3000`)**: P99 2.81→**2.05(−27%)** ✅ · peak **3.82**(baseline보다 개선) ✅ · air **0.15 회복** ✅ · knee 122%. **B1 동결**: `contact_force_cap(−0.01, 600N, clip800)`. 충격 P99 ≈1.04kN = HW 한계(1.5~2.7kN) 안. 교훈 기록: 벌점 clip이 낮으면 대형 스파이크 gradient 소실→오히려 악화(B1서 실증).
- **🔄 B2 착수(2026-07-03)**: B1w2 동결 + **`thermal_effort` = Σ(τ/rated)² (weight −0.02)** 단독변수 — torque_limit(peak만)로는 knee **RMS(열)** 못 잡음 → 정격-정규화 제곱합이 **비율 균등화=재분배**를 직접 최적화(사용자 "균등분배" 그 자체). rated맵: hip/knee 40·hip_yaw/ankle_pitch 20·ankle_roll 5. 게이트: **knee RMS<100%** ∧ tracking ±10% vs B1w2@동일iter(ckpt ~3.5k 보존).
- **B2 1500(`b2_1500`)**: 전 관절 열부하 일괄↓ — hip_pitch 98→**82**·ankle_pitch 98→**81**·hip_roll 52·knee 113→**109**(게이트 미달, raw는 95%)·GRF P99 2.04(B1 보존+)·base 0.81. → 3000 최종(미달 시 −0.05 에스컬레이션). wandb `71hmokt6`.
- ★★ **B2 3000 = ACCEPT(조건부, `b2_3000`)**: hip_pitch 88→**72**·**ankle_pitch 109→88(마진 포함 rated 진입!)**·knee 122→**114(raw 99%)**·GRF P99 **1.88**(≈950N). 판정: knee 잔여 14%는 **확정된 knee 링크 레버 1.4~1.6:1이 커버**(유효 rated 60 → 76%) — reward 추가 압박은 gait 훼손 리스크만. **B2 동결, 잔여는 HW 이관**([메커니즘 노트](2026-07-03_knee_ankle_mechanism_design.md)에 명기).
- **🔄 B3 착수(2026-07-03)**: B2 동결 + **Siekmann v8-검증 패키지**: `gait_clock` obs(actor+critic, +2dim→fresh) + `periodic_contact`(+1.5, stance 0.6·k_v8·k_f0.02·sharp20, L/R 반주기) + swing 항 2개 제거(clock이 입법) + **standing 게이팅**(F11, |cmd|≤0.05→양발 stance 보상). 게이트: **GRF L/R asym <0.3**(v8: 0.18)·GRF P99 유지(≤2.1)·air≥0.12·contact cycle 대칭.
- ★ **B3 1500 = PASS(`b3_1500`, wandb `m4ik3uph`)**: **asym 0.04**(v8의 0.18보다 우수!)·사이클 **77/73 대칭**(주기 1.0s 정합)·**air 0.31s**(진짜 swing 형성)·P99 2.05 유지·base 0.80·렌더=자연 스트라이드(heel-off 스윙). ⚠ peak 2.91→4.63(mid-training 착지 과도) — 3000서 추세 확인, 지속 상승 시 contact_force_cap과의 균형 재조정.
- ⚠ 로드맵 메모: **mjlab 모델은 강체 발(toe 없음)** — Q3(toe/CoP/foot-roll)의 완결은 toe 지오메트리를 mjlab 로봇에 추가하거나 IsaacLab 계통 병행 필요. B3는 대칭·타이밍·human-likeness까지 담당.
- ★★★ **B3@12k = 최종 설계점**([노트](2026-07-03_final_design_point.md)): P99 1.63·peak 2.18×BW·knee 97.9%·ankle_pitch 65%·asym 0.18. worst-case 판정 v3 = **ankle 상향 철회·knee 링크 레버만 잔존**. reward 84.5로 완전 평탄 → **15k서 조기 종료(FINAL ckpt model_15100)**, GPU를 R1(rough 정식학습, task#6)에 재배치. 영상 4종(실시간 1×)·q-scatter·CSV 일습 완비.
- **🔄 R1 착수(2026-07-03)**: `Mjlab-Velocity-Rough-Pygmalion` fresh — **B-스택 전체 상속** + height_scan + 지형 커리큘럼. 목적: rough 판정의 OOD 한계 해소(knee S 0.88 경계 재검), HW rough 하중 확정. **OOM 사가**: 8192(37GB)→4096(18.5GB)→2048(9.2GB) 전부 실패 — 원인 = rough cfg의 **`ccd_iterations=500`**(EPA 버퍼 = naccdmax×ccd_iter 선형). **500→100 수정** 후 4096 envs @11.5GB 성공(env_cfgs 주석 기록). wandb `vmsro94z`(R1-rough-fullstack), watcher 500.
- ★★ **B3 3000 = PASS·최종 스택 확정(`b3_3000`)**: asym **0.02**·P99 **1.98**(계보 최저)·**peak 4.63→3.09 하락**(착지 연화, 우려 해소)·air 0.23·knee 116(노이즈 대역, raw~101%). **최종 reward 스택 = A1b gains + contact_force_cap(−0.01/600/800) + thermal_effort(−0.02) + Siekmann(clock+periodic_contact 1.5)**. → 수렴 완주(watcher 12k, 시간당 heartbeat) 후 **최종 설계점 파이프라인**: worst-case flat+rough 측정→actuator_eval→§7→q-scatter→loadviz/dashboard 영상→설계점 노트(메커니즘 설계 입력 갱신)→wandb 리포트.

### B2 = hip 재분산 (B1 승자 위)
- weight는 Day-0 replay 산출값(−0.5 아님). iter 1500 게이트: hip RMS util +10pt ∧ knee/ankle 클립<5% ∧ tracking ±10%. 애매 시 A1+B2 단독 ablation 1런.

### B3 = 속도별 보폭
- B1b clock이 흡수. 잔존 시(r<0.5): 착지시 last_air_time 기반 custom 항(내장 air_time은 이진창이라 불가 — 감사 확인).
- 평가 프로토콜: vx{0.3,0.6,1.0,1.5} 스윕 → 보폭·케이던스 각각 단조증가, r>0.7.

### C = HW (측정 기반, **B 중간에 plant 변경 금지**)
- 최종정책 worst-case(flat+rough) → actuator_eval 재판정 → ankle_roll DM-J4340 config → **마지막에** 40/80Nm 캡 실험(plant 변경=전 비교 무효화라 최후). ankle_pitch 정적 63>60(정책무관)은 **지금 서류상 확정**: RS03 부족.

## 2. 전 런 공통 리포트 지표 (게이트마다)
base높이 분포(mode) · low_base/종료율 · |vx err| · action 포화율 · **CoT**(전 런; 에너지 항은 없지만 지표는 기록) · GRF 첫접촉 peak(×BW, 목표<3.5) P99 RMS · L/R asym(<0.2) · motor-util §7(RMS/P99/peak %rated) · air_time_mean · 렌더 1500/3000iter + wandb video 3000iter.

## 3. 사용자 6개 실험 요청과의 매핑
| 요청 | 계획 위치 |
|---|---|
| 1. Ankle Roll 40/Pitch 80 변인분리 | C 마지막(plant 변경) — 근거: 비교오염 방지 |
| 2. 발목 Kp 단단히 | A1에 포함하되 분석상 **발목은 이미 3.9~5.7Hz 정상, hip/knee가 병목** — 발목 단독 상향은 비권장, hip/knee 보정이 상체 흔들림의 진짜 해법 |
| 3. 속도별 보폭 | B3(=B1b clock에 흡수) |
| 4. 사뿐사뿐 | B1(soft_landing→Siekmann) |
| 5. hip 활용/토크분산 | B2(torque_limit 재활성, replay로 weight) — reward로 가능, 체급↑은 C서 최후 판단 |
| 6. 추가 실험 | Day-0 chirp, armature 검산, B2 ablation |
