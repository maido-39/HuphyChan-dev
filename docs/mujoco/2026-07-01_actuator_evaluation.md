# mjlab Pygmalion 액추에이터 선정 평가 (v2) — worst-case 부하 대 RobStride 스펙

> v2: 방법론 비평(저비용 QDD 액추에이터 선정 리딩리스트) 반영 — 열 RC/overload 모델·sim→real 마찰보정·관절파워·**독립 해석 정적검산** 추가. §A 참조.

| 항목 | 값 |
|---|---|
| 목적 | 학습 정책의 **worst-case 관절부하** vs RobStride 스펙 → **액추에이터 선정 안전권 판정** |
| Task / run | `Mjlab-Velocity-Flat-Pygmalion` / `2026-06-30_20-12-31`, checkpoint **model_30000**(최종) |
| worst-case | DR corners **vx≤2.5 m/s, yaw≤1.0 rad/s** + 랜덤(`--worst-case`), flat / **rough 분리** |
| 측정 | CPU 분리 rollout(학습 무중단), 7200 step·dt 0.02s(≈144s), 총질량 51.5 kg |
| **sim→real 보정** | 마찰·기어효율 **×1.15**(η≈0.9+마찰; 무마찰 시뮬 과소평가 보정, 보수적) |
| 모터스펙 | `Motor_Spec/RS0{0,2,3,4}` (48V) — TN곡선 + overload_rotation(145℃ 도달시간) |
| 도구 | `motor_specs.py`·`actuator_eval.py`·`analytic_static.py` · [README](README.md) |

---

## 0. 안전권 판정 기준 (v2)

| 축 | 기준 | 구현 |
|---|---|---|
| **토크 연속/열** | RMS ≤ rated **또는** 정상온도 T_ss ≤ 145℃ | T_ss = 25 + 120·(τ_rms/rated)² (동손 ∝τ²) |
| **토크 순간** | P99·Peak ≤ peak | effort_limit 도달=정책이 더 원함 |
| **속도** | 토크-속도 cloud가 TN곡선(48V) 내부 | out-env% = cloud 이탈 비율 |
| **열 과도** | thermal-state **S < 1** | overload곡선 직접적분(가열 1/t_lim, 냉각 τ_cool) — ×2.5 휴리스틱 대체 |
| **독립 검산** | 정적 gravity-hold ≤ peak (§2.5) | RL 무관 하한 |

---

## 1. 모터 스펙 (RobStride @48V)

![[motor_tn_curves.png]]
![[motor_overload.png]]

| 모터 | rated | peak | vel_lim | 반사관성 | gear | 구동 관절(×L/R) |
|---|--:|--:|--:|--:|--:|---|
| **RS00** | 5 | 14 | 33 rad/s | 0.0005 | 10:1 | ankle_roll |
| **RS03** | 20 | 60 | 20 rad/s | 0.0050 | 9:1 | hip_yaw, ankle_pitch |
| **RS04** | 40 | 120 | 15 rad/s | 0.0070 | 9:1 | hip_pitch, hip_roll, knee |

(overload_rotation의 'rated'행이 연속토크 확정: RS00=5·RS03=20·RS04=40. TN 저속영역은 peak로 clamp.)

---

## 2. worst-case 판정표 (sim→real ×1.15 보정, P_mech=양다리 피크)

### [flat] — 정책 학습지형, **깨끗한 판정**

| joint | motor | RMS/rated | P99/peak | Peak/peak | spd P99/Peak | out-env% | 열 S / T_ss | P_mech | 판정 |
|---|---|--:|--:|--:|--:|--:|:--:|--:|:--:|
| hip_pitch | RS04 | 20.7/40 (52%) ✅ | 57 (48%) | 89 (74%) ✅ | 41/92 | 0.00 | 0.02 / 57℃ ✅ | 609W | ✅ |
| hip_roll | RS04 | 23.1/40 (58%) ✅ | 63 (53%) | 99 (82%) ✅ | 15/46 | 0.00 | 0.00 / 65℃ ✅ | 139W | ✅ |
| hip_yaw | RS03 | 9.4/20 (47%) ✅ | 28 (46%) | 52 (87%) ✅ | 28/56 | 0.00 | 0.00 / 51℃ ✅ | 86W | ✅ |
| **knee** | RS04 | 32.1/40 (80%) ✅ | 83 (69%) | **138 (115%)** ⚠ | 107/267 | 0.17 | 0.23 / 102℃ ✅ | 1647W | ❌ |
| **ankle_pitch** | RS03 | **22.6/20 (113%)** ⚠ | **69 (115%)** | **69 (115%)** ⚠ | 108/233 | **2.57** | 0.36 / **178℃** ⚠ | 444W | ❌ |
| **ankle_roll** | RS00 | 3.6/5 (72%) ✅ | 9.9 (71%) | **16.1 (115%)** ⚠ | 63/206 | 0.15 | 0.28 / 88℃ ✅ | 122W | ❌ |

**flat 종합**: 미달 3 — **ankle_pitch**(RMS·열·envelope 全 위반=근본), knee·ankle_roll(순간 peak 초과). 시스템 피크 **P_mech 3.0 kW / P_elec≈3.3 kW**.

### [rough] — flat정책 **blind 배포**(OOD 비관적 상한, §2 주의)

| joint | motor | RMS/rated | P99/peak | Peak/peak | spd P99/**Peak** | out-env% | 열 S / T_ss | P_mech | 판정 |
|---|---|--:|--:|--:|--:|--:|:--:|--:|:--:|
| hip_pitch | RS04 | 26.3/40 (66%) ✅ | 138 (115%) | 138 (115%) ⚠ | 59/**640** | 1.19 | 0.10 / 77℃ | 12.8kW | ❌ |
| hip_roll | RS04 | 28.1/40 (70%) ✅ | 121 (101%) | 138 (115%) ⚠ | 37/**299** | 1.03 | 0.00 / 84℃ | 7.1kW | ❌ |
| hip_yaw | RS03 | 12.8/20 (64%) ✅ | 56 (94%) | 69 (115%) ⚠ | 54/**516** | 0.98 | 0.00 / 74℃ | 5.2kW | ❌ |
| **knee** | RS04 | **46.7/40 (117%)** ⚠ | 138 (115%) | 138 (115%) ⚠ | 145/**490** | 4.33 | **0.68** / **189℃** ⚠ | 7.0kW | ❌ |
| **ankle_pitch** | RS03 | 21.9/20 (109%) ⚠ | 69 (115%) | 69 (115%) ⚠ | 143/**753** | 4.41 | 0.33 / **169℃** ⚠ | 2.7kW | ❌ |
| **ankle_roll** | RS00 | 4.3/5 (86%) ✅ | 16.1 (115%) | 16.1 (115%) ⚠ | 137/**953** | 1.72 | **0.54** / 114℃ | 1.4kW | ❌ |

**rough 종합**: 6/6 미달. > ⚠ **속도 Peak 490~953 rpm = vel_lim의 4-6배 = 넘어짐/충격 transient**(P99는 137~145 정상권). flat정책 blind이므로 **비관적 OOD 상한** — 깨끗한 rough 사이징은 **rough-학습 정책 필요**. 단 knee 열 S=0.68·T_ss 189℃는 rough 생존 요구 시 실 위험.

**scatter (flat / rough):** torque-속도(+TN) · |토크|히스토그램 · **q-토크(+rated/peak/관절범위선)** · **q-속도(+속도한계/관절범위선)** — ★ q-scatter 2종+한계선은 전 관절 표준 룰(소급적용 2026-07-02)

| flat                                      | rough                                       |
| ----------------------------------------- | ------------------------------------------- |
| ![[torque_speed_flat.png]]  | ![[torque_speed_rough.png]]  |
| ![[torque_hist_flat.png]] | ![[torque_hist_rough.png]] |
| ![[q_torque_flat.png]]   | ![[q_torque_rough.png]]   |
| ![[q_speed_flat.png]]    | ![[q_speed_rough.png]]    |

> q-scatter 읽기(flat): **knee는 굴곡 −40~−80°대서 속도한계(143rpm) 초과** · **ankle_pitch는 관절범위 상한(+40°)과 속도한계를 동시에 침** · ankle_roll은 범위단(−20°) 도달 = 스트로크·속도 여유 모두 확인 가능.

---

## 2.5 독립 해석 정적검산 (A.7) — RL 무관 하한

정적 gravity-hold 토크(정책·시뮬 오차 무관, 모델 지오메트리만). W=505 N, shank 0.40·thigh 0.45·forefoot 0.124 m.

| pose | joint | motor | 정적 τ | rated | peak | vs peak |
|---|---|---|--:|--:|--:|:--:|
| **한다리 toe-stance(CoP@forefoot)** | ankle_pitch | RS03 | **63 N·m** | 20 | 60 | **초과** |
| 한다리 heel-stance | ankle_pitch | RS03 | 29 N·m | 20 | 60 | OK |
| 양다리 깊은스쿼트(다리당) | knee | RS04 | 77 N·m | 40 | 120 | ⚠>rated |
| **한다리 깊은스쿼트** | knee | RS04 | **155 N·m** | 40 | 120 | **초과** |
| 한다리 스쿼트(hip over toe) | hip_pitch | RS04 | 46 N·m | 40 | 120 | ⚠>rated |

> ★ **정적 toe-stance만으로 ankle_pitch 63 > 60(peak)** — RL과 독립적으로 **ankle_pitch(RS03) 부족 확증**. 한다리 스쿼트 knee 155 > 120도 극단정적서 초과. 발이 발목축보다 전방에 있어(forefoot +0.124, heel도 +) ankle_pitch는 항상 전방 모멘트 부담.

---

## 2.6 관절 파워 · 반사관성 (A.6)

- **피크 전력(드라이버/배터리 사이징)**: flat P_mech 3.0 kW / P_elec≈3.3 kW(η0.8). rough는 OOD 충격이라 과대(P_mech 36 kW). 관절별 최대: knee 1.6 kW·hip_pitch 0.6 kW(flat).
- **반사관성**(관절환산 $N^2 J_{rotor}$): RS04 0.007·RS03 0.005·RS00 0.0005 kg·m². QDD(9-10:1 저감속)라 낮음 → 역구동·충격흡수 유리(IMF 관점). 충격토크 = f(반사관성, 접촉속도) 정밀평가는 A.4 명시적 충격케이스 필요(defer).

---

## 2.7 부하-색 영상 (관절 saturation 시각화)

worst-case rollout을 **실제 지형 위**에서 리플레이 + 관절별 색-구(회색<rated, 노랑≥rated, 주황≥0.7peak, **빨강≥peak**). 제목에 실시간 명령(vx/vy/yaw) 표시. `render_loads.py`(saturation) / `make_dashboard_video.py`(좌 로봇 / 우 토크·RPM 히스토그램+limit).

- **saturation 영상**: flat [assets/worstcase_flat_loadviz.mp4](assets/worstcase_flat_loadviz.mp4) · rough [assets/worstcase_rough_loadviz.mp4](assets/worstcase_rough_loadviz.mp4)
- **대시보드 영상**(좌 영상/우 히스토그램): flat [assets/worstcase_flat_dashboard.mp4](assets/worstcase_flat_dashboard.mp4) · rough [assets/worstcase_rough_dashboard.mp4](assets/worstcase_rough_dashboard.mp4)

> ★ 영상서 **ankle 구가 빨강(≥peak)으로 자주 점등** = 판정표의 ankle_pitch/roll 포화가 시각 확인. hip은 대체로 회색(여유), knee는 급기동서 순간 주황/빨강.

---

## 3. 핵심 결론 (HW 사이징)

### (A) flat = 학습지형 → 깨끗한 판정
> **★ ankle_pitch(RS03)가 최우선 binding.** sim→real 보정 후 RMS 113%·**정상온도 178℃(과열)**·순간 69>60·TN이탈 2.57% = 4개 기준 全 위반. **독립 정적검산(63>60)까지 일치.** → RS03 명백히 부족.
> knee(RS04)·ankle_roll(RS00)은 보정 후 **순간 peak만 115% 초과**(RMS·열 여유) = 마진 부족이나 치명 아님.

### (B) rough = OOD 상한 → 참고
> 6/6 초과이나 속도 4-6× = 헛디딤 transient. 정상 사이징 근거 아님. rough 생존 필수 시 **knee 열(S 0.68·189℃)**이 최대 위험.

**권고**(우선순위):
1. **ankle_pitch 상향** (RL+정적 이중확증) — RS03(60)→RS04(120) 또는 감속비. push-off 저속영역이라 감속의 속도손실 무해. ★ **1순위**.
2. **knee·ankle_roll peak 마진 확보** — 현 순간 115% 초과. 마진 2-3×(QDD 관례) 권장. rough-학습 후 재평가.
3. **rough-학습 정책 확보 후 재측정** — 현 rough는 OOD.
4. **열 디레이팅**: 강제냉각 없으면 rated의 30-50%로 디레이팅(밀집 사지 고주변온도). 현 T_amb=25℃ 가정, 실 내부는 더 높음 → ankle_pitch/knee 더 악화.

---

## A. 방법론 비평 반영 (triage)

리딩리스트 비평 대비 채택/보류:

| 비평 | 상태 | 조치 |
|---|---|---|
| A.1 열: ×2.5 → 물리모델 | ✅ 채택 | overload곡선 직접 thermal-state S + 정상온도 T_ss. (단일-τ RC는 고과부하서 비보수→S누적 채택) |
| A.5 sim→real 토크 간극 | ✅ 채택 | ×1.15 마찰/효율 보정(스펙대조 전). actuator-net은 실HW 필요→보류 |
| A.6 관절파워·반사관성 | ✅ 채택 | §2.6 |
| A.7 독립 정적검산 | ✅ 채택 | §2.5 — ankle_pitch·knee 초과 독립확증 |
| A.3 전압적합 TN | ◐ 부분 | TN=48V 사용. 버스새그·회생·약계자는 배터리데이터 필요→caveat |
| A.2 기어박스 쇼크/L10 | ◐ 부분 | RobStride 통합QDD=별도 기어박스 스펙 無. peak=통합유닛값. 쇼크 2-5× 정격은 flag(데이터 없음) |
| A.4 명시적 충격/점프 | ◐ 부분 | 정책 점프불가. rough-blind가 충격 transient 일부 포함(속도 4-6×) |
| 멀티시드 P99 분포 | ⛔ 보류 | seed 파라미터화 필요(단일 seed=0 현재) |
| actuator-net·공동설계 재학습 | ⛔ 보류 | 실HW·반복재학습 = 별도 로드맵 |

**남은 리스크(미반영)**: 기어박스 쇼크토크 정격, 버스전압 새그, 멀티시드 P99 산포, 사지 관성 공동설계 루프. → HW 데이터/추가 학습 확보 시 다음 반복.

---

## B. 방법 / 재현

```bash
cd mujoco-sim/mjlab; RD=logs/rsl_rl/pygmalion_velocity/2026-06-30_20-12-31
CUDA_VISIBLE_DEVICES="" uv run python -u analysis/measure_loads.py --run-dir $RD \
  --task Mjlab-Velocity-Flat-Pygmalion  --checkpoint $RD/model_30000.pt --tag worstcase_flat  --worst-case --steps 7200
CUDA_VISIBLE_DEVICES="" uv run python -u analysis/measure_loads.py --run-dir $RD \
  --task Mjlab-Velocity-Rough-Pygmalion --checkpoint $RD/model_30000.pt --tag worstcase_rough --worst-case --blind --rough-terrain --steps 7200
# 판정 스크립트는 mjlab/analysis/ (conda pygmalion env: numpy/matplotlib)
python3 analysis/motor_specs.py                                           # TN·overload 플롯
python3 analysis/actuator_eval.py --tags worstcase_flat worstcase_rough --labels flat rough
uv run python analysis/analytic_static.py                                 # A.7 독립 정적검산(mujoco)
```

수정: `measure_loads.py`에 `--worst-case` 완성(직전 세션 argparse 누락분). 신규 `motor_specs.py`(TN·overload·열모델)·`actuator_eval.py`(마찰·파워·판정)·`analytic_static.py`(A.7).
