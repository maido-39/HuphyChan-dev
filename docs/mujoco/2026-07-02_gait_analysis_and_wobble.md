# 보행 데이터 분석 — 속도별 관절거동 · 오버로드 · GRF · ★wobble 근본원인

> 2026-07-02. worstcase_flat.npz(구 정책, action_scale 0.8~1.8 hot) + progression으로 4개 병렬분석. 사용자 질문(Q1 보폭-속도, Q2 GRF, Q3 오버로드/hip, wobble) 답 + 실험계획. ⚠ 데이터는 **구 hot 정책** — action_scale=0.25 정책서 재확인 필요.

관련: [action_scale·Kp/Kd](2026-07-02_action_scale_and_gains.md) · [actuator eval](2026-07-01_actuator_evaluation.md)

---

## ★★ 결론: wobble("출렁거림") 근본원인 = Kp/Kd가 로터관성 기준

![[kpkd_bandwidth.png]]

$K_p = armature \times \omega_n^2$ ($\omega_n$=10Hz)로 **로터 반사관성(armature)만** 씀. 실제 관절이 움직이는 **링크 관성 I_total은 3~316배 큼**(mass matrix 대각). $f_{eff} = \sqrt{K_p/I_{total}}/2\pi$:

| 관절 | I_total/I_rotor | 현 Kp | **f_eff** | ζ_eff | 10Hz용 Kp |
|---|--:|--:|--:|--:|--:|
| **hip_pitch** | **316×** | 27.6 | **0.56 Hz** | **0.11** | 8740 |
| **hip_roll** | 237× | 27.6 | 0.65 Hz | 0.13 | 6560 |
| hip_yaw | 38× | 19.7 | 1.6 Hz | 0.32 | 757 |
| **knee** | 42× | 27.6 | 1.5 Hz | 0.31 | 1173 |
| ankle_pitch | 3× | 19.7 | 5.7 Hz | 1.15 | 60 |
| ankle_roll | 7× | 1.97 | 3.9 Hz | 0.78 | 13 |

★ **hip(0.6Hz)·knee(1.5Hz)이 목표 10Hz의 5~15%밖에 안 됨 + ζ 0.11~0.31(설계 2.0)** = **물렁 + 저댐핑 = 진동/출렁**. 몸통을 지탱하는 큰 관절일수록 심함. **발목은 이미 스펙 근처(3.9~5.7Hz)** — 사용자가 지목한 발목 Kp가 아니라 **HIP/KNEE Kp가 범인**.

**★ 수정**: $K_p = I_{total} \times \omega_n^2$, $K_d = 2\zeta\cdot I_{total}\cdot\omega_n$ ($\zeta\approx 1$). 단 full-10Hz Kp(hip 8740)는 **토크 포화**(작은 오차도 effort_limit 초과) → **포화 여유로 cap**(오차 ~0.15rad 기준 $K_p\lesssim effort/0.15$). → **hip/knee ~600, hip_yaw ~300, ankle 현행~60/13** 수준이 실용적 목표(hip 대역 0.6→~2.6Hz = 5×↑). 다음 실험 1순위.

---

## Q1. 속도별 보폭 조정 — 현재는 **속도와 무관**

![[gait_rom_polar.png]]
![[gait_rom_vs_vx.png]]

★ 관절 ROM이 **전진속도 |vx|와 무상관**(Pearson r −0.20~+0.07, 전 관절). 대신 **측방 |vy|**(hip_roll r0.52, ankle_roll 0.36)·**회전 |wz|**(hip_yaw 0.38)와 상관. 즉 **지금 정책은 "느림=작게/빠름=크게"가 안 됨** — 보폭이 속도에 안 걸려 있음.
- 최대 ROM: knee 72°, ankle_pitch 57° (대각·후진·회전 조합서). 최대속도: knee 267rpm, ankle_pitch 225rpm.
- → **속도별 보폭은 자동으로 안 생김 = reward 설계 필요**(Q1 실험). worst-case는 **대각/회전** 명령서 나오니 사이징도 거기서.

---

## Q2. GRF는 학습해도 안 줄어듦 — **확인됨**

![[grf_vs_training.png]]

iters 3k→36k: peak 4.3~9.3×BW(노이즈, 최악은 중반 15k), **P99 1.3~2.0·RMS 0.6~0.73 전 구간 평탄**. first-vs-last는 오히려 소폭 상승. **학습이 충격을 안 줄임**(사용자 관측 정확). 원인: hot action_scale이 발을 계속 내리침 + **GRF 감소를 강제하는 reward항이 약하거나 없음**. → action_scale=0.25 + **명시적 impact/GRF 페널티**(Q4 사뿐사뿐)로 재검.

---

## Q3. 오버로드 = 원위(발목/무릎)만, **HIP 여유 있음**

![[overload_torque_map.png]]
![[overload_speed_map.png]]
![[torque_distribution.png]]

- **토크 초과**: knee 115%·ankle_pitch 115%·ankle_roll 108%(전부 motor peak에 clip). **속도 초과**: knee **187%**·ankle_pitch 118%.
- **★ HIP 저활용**: hip_pitch +31·hip_roll +21·hip_yaw +8 N·m **여유**, 다리토크의 48~52%만 hip이 부담. → **knee/ankle 부하를 hip으로 재분산 가능**(reward/자세/기어). Q3 답: reward로 해결 시도할 가치 O(체급↑ 전에).
- 위치별: 토크초과=저속/제자리 지지+측방·회전, 속도초과=빠른 회전+strafe.

---

## 실험 우선순위 (변인분리, 빠른검증 우선)

| # | 실험 | 유형 | 근거(분석) | 기대 |
|---|---|---|---|---|
| 0 | action_scale=0.25 (**진행중**) | config | hot이 부하·GRF·wobble 원흉 | 부하↓·GRF↓? wobble은 **잔존 예상**(Kp/Kd라) |
| **1** | **Kp/Kd 보정**(hip/knee I_total기반, cap) | config | ★hip 0.6Hz·ζ0.11 | **wobble 해결**·추종↑·토크사용 정상화 |
| 2 | Ankle Roll 40/Pitch 80 | config·변인분리 | ankle 토크 clip | 오버로드 여유·gait 변화 |
| 3 | 토크 hip 재분산 | reward | hip 여유 +8~31Nm | knee/ankle 오버↓ |
| 4 | GRF 페널티(사뿐사뿐) | reward | GRF 평탄(Q2) | 충격↓ |
| 5 | 속도별 보폭 | reward | ROM⊥vx(Q1) | 느림작게/빠름크게 |

**진행**: 0(진행중) 걷는 즉시 렌더로 **wobble 잔존 확인**(예측: 잔존→Kp/Kd가 범인 확정) → **1(Kp/Kd)** 최우선. config 실험(1,2)이 reward 실험(3~5)보다 빠르고 변인분리 깨끗 → 먼저.

**방법**: 각 실험 baseline+한변수, 학습→걷는영상+reward 검증되면 정지→다음. reward 실험(3~5)은 각각 reward-research 노트 후.

---

## 방법 / 기록 (소급)

- workflow `w46ww7p4s`(run `wf_910cb6d3-060`), 4 agents 병렬(~140k tokens/23 tools/151s): `gait_velocity_map`(명령블록 분할→ROM·peak속도 vs 속도평면) / `overload_map`(×1.15 보정 토크·속도 % vs 한계, hip 분담) / `grf_trend`(prog_3000~36000 npz→GRF peak/P99/RMS ×BW) / `kpkd_bandwidth`(★mj_fullM 대각=I_total→f_eff·ζ_eff).
- 데이터: `mjlab/analysis/out/worstcase_flat.npz`(N=7200, 60 명령블록, dt 0.02s, 구 hot 정책 model_30000) + `out/prog/prog_*.npz`. 모터맵: RS04(120/40)/RS03(60/20)/RS00(14/5).
- 산출 플롯 8종은 본문 임베드(assets/gait_*·overload_*·torque_distribution·grf_vs_training·kpkd_bandwidth). 수치는 agent가 스크립트 실행·자가검증 후 보고.
- ⚠ 후속 비평([분석 기록 §3](2026-07-02_analysis_reward_audit_critique.md))이 본 노트의 **"10Hz용 Kp=8740/6560" 처방을 기각** — 포화 지배·자기제동(Kd84가 1.43rad/s↑서 클립). 진단(f_eff 0.56~1.5Hz=물렁)은 유효하나 armature가 kbot 복사값이라 316× 수치는 검산 대상. 확정 처방은 [계획 v2](2026-07-02_training_plan_v2.md)(Day-0 chirp→Kp 200-480).
