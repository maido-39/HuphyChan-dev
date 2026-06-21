# 36 — 전 액추에이터 T-N 봉투 (교차검증 종합, 설계 분석용)

> 연구 워크플로우 `wgk8q2vo3`(RS04·RS03·RS00 각 2+ 독립출처 교차검증). 원자료(공식 PDF 추출 곡선·과부하·전기파라미터): [[robstride-datasheet]]. 무릎 감속비 분석: [[35_knee_gear_ratio_analysis]] · 액추에이터 landscape: [[knee-actuator-landscape]]. 모터 포화 demand: `assets/forefoot_motor_util.md`.

검증 상태: **RS03 / RS00 = verified yes**(공식 매뉴얼 PDF 곡선 직접 판독 + 4~5 독립 리셀러/wiki 교차), **RS04 = verified partial**(헤드라인 5출처 PASS, T-N 곡선 모양만 공식 vs 리셀러 불일치 — 공식 채택). 모든 모터 **2+ 독립출처** 확보.

---

## 1. 교차검증 T-N 표 (모터 단위, 출력축 = 내부 기어박스 이후)

| 모터 | 역할 | rated/peak (N·m) | 무부하/정격 rpm | **평탄 corner** | 연속(thermal) | Kt / line R | 출처 일치? |
|---|---|---|---|---|---|---|---|
| **RS04** | hip_pitch/roll | **40 / 120** | 200 / **167** | **≤~95 rpm** | **40 N·m**(회전) / 28.5(스톨) | 2.1 / 0.16Ω | 헤드라인 ✅ 5출처. **⚠ 곡선모양 불일치** |
| **RS03** | hip_yaw, ankle_pitch | **20 / 60** | 200 / **100** | **≤~120 rpm** | **20 N·m**(회전) / 13(스톨) | 2.36 / 0.39Ω | 헤드라인 ✅ 6출처. **⚠ 정격속도 불일치** |
| **RS00** | ankle_roll | **5 / 14** | 315 / **100** | **≈100 rpm** | **5 N·m**(연속) | 1.48 / 1.5Ω | 헤드라인 ✅ 5출처. **⚠ 정격속도 불일치** |

**불일치 flag (전부 동일 패턴 — 리셀러 정격속도 over-optimistic):**
- **RS04 T-N 곡선모양**: 리셀러(OpenELAB) "~120 N·m를 100rpm까지 평탄 유지" vs **공식 매뉴얼 "95rpm서 이미 peak, 곧장 단조감소"**(110rpm→110, 150rpm→78, 190rpm→10). → **공식 채택**. 리셀러는 고속 토크유지 과대평가.
- **RS03 정격부하속도**: 리셀러 4곳 **180 rpm** vs **공식 100 rpm**(20N·m@100rpm 명시). → **공식 100 채택**.
- **RS00 정격부하속도**: 리셀러(OpenELAB) **260 rpm** vs **공식 100 rpm**(+AIFITLAB 매뉴얼 일치). 100이 T-N corner·50W 정격과 자기일치. → **공식 100 채택**. (우리 기존 "260 rated"는 리셀러값이었음 — 정정.)
- 무시 가능: RS03 무부하 200(공식) vs 195(리셀러), ±10% 내.

**★ 핵심 결론 (3모터 공통)**: 세 모터 모두 **전압제한 봉투**(저속 평탄부 → field-weakening roll-off). **"peak 토크 × max 속도 단순 박스" 가정은 전부 틀림** — 고속에서 가용 토크 급감. (현 sim의 ImplicitActuator = 박스 → 충실도 한계, docs/35.)

공식 곡선(로컬, 저작권상 비커밋):
![[rs04_tn_curve_official.png]]
![[rs03_tn_curve_official.png]]
![[rs00_tn_overload_official.png]]

---

## 2. 관절 단위 봉투 (joint-side, 외부 기어 반영)

직결 관절은 모터 출력축 = 관절축 → 위 표 그대로. **무릎만 외부 벨트 g배** → **토크 ×g, 속도 ÷g**:

| 관절 | 액추에이터 | 외부비 | joint peak/rated (N·m) | joint 연속(N·m) | joint 무부하/정격 rpm | joint 무부하 rad/s |
|---|---|---|---|---|---|---|
| hip_pitch/roll | RS04 direct | 1.0 | **120 / 40** | 40 | 200 / 167 | 20.9 |
| hip_yaw | RS03 direct | 1.0 | **60 / 20** | 20 | 200 / 100 | 20.9 |
| **knee** belt=1.0 | RS04×1.0 | 1.0 | **120 / 40** | 40 | 200 / 167 | 20.9 |
| **knee** belt=1.5 | RS04×1.5 | 1.5 | **180 / 60** | 60 | 133 / 111 | 13.9 |
| **knee** belt=2.0 | RS04×2.0 | 2.0 | **240 / 80** | 80 | 100 / 83 | 10.5 |
| **knee** belt=2.5 | RS04×2.5 | 2.5 | **300 / 100** | 100 | 80 / 67 | 8.4 |
| ankle_pitch | RS03 direct | 1.0 | **60 / 20** | 20 | 200 / 100 | 20.9 |
| ankle_roll | RS00 direct | 1.0 | **14 / 5** | 5 | 315 / 100 | 33.0 |

**무릎 벨트 트레이드오프**: belt가 클수록 토크 천장↑ 속도 천장↓. ⚠ **T-N 재투영 주의**: 모터속도 = joint × (9×g)라 belt 클수록 모터가 고속 roll-off로 빨리 진입 → 고속 swing 가용토크는 표값보다 작다. belt 2.5서 joint 70rpm swing이면 모터 ~189rpm → RS04 곡선상 ~10 N·m(×2.5 = joint 25 N·m)밖에 안 남음. **belt↑ = 고속 토크 붕괴**. 현 flat 데이터(직결-학습 무릎 max 80 N·m·105rpm, [[sweep_gear_ratio]])는 belt 1.5~2.0를 시사하나 **rough+DR 미반영** — sweep 진행 중.

---

## 3. 교차검증 신뢰도 + 미해결값

- **높은 신뢰**(공식 PDF + 다출처): rated/peak·Kt·감속비·질량/외형·T-N 곡선모양·회전/스톨 과부하 듀티표(전 모터 공식 추출).
- **중간 신뢰**(단일계열): line R/인덕턴스 — RS03는 공식 미기재, 리셀러 0.39Ω(RS04 패턴상 신뢰). RS04 0.16Ω·RS00 1.5Ω은 공식.
- ⚠ **미해결 / bench 식별 필요**:
  - **rotor inertia(armature)**: **전 모델 공식·리셀러 모두 미공개**. sim armature 전부 추정 → ζ·고주파 안정성 직결, bench 식별 권장.
  - **효율맵**: 전 모델 미공개(RS04 85pp 전수 grep 확인) → Joule reward는 line R 근사만.
  - **열 시상수**: 듀티표만 있고 연속 시상수·열저항 미공개 → RMS 열한계는 듀티표 보간으로만.

---

## 4. ★ ankle_roll (RS00) — 바인딩 액추에이터, 상향 검토

**진단: RS00는 명백히 포화(undersized).** 모션 데이터(`forefoot_motor_util.md`): L/R_ankle_roll clip|τ| = **14.0 N·m → peak 100% 포화**(clip=unclip=effort_limit 상시 걸림), RMS는 연속 5 N·m의 **~1.5~2.8배(280%rated)**.
- RS00 과부하 듀티: **5=무한 · 10=18s · 12=10s · 14=단 5초** → 현 demand 수십 초도 지속 불가.

| 후보 | rated/peak | 무부하 rpm | 질량 | ankle_roll demand(14)에 대해 |
|---|---|---|---|---|
| RS00 (현재) | 5 / 14 | 315 | 310g | peak 100% 포화 ❌ |
| **RS01/02** | 6 / 17 | 315·410 | 소형 | peak 여유 ~18%, **연속 6은 여전히 빠듯** |
| RS03급 | 20 / 60 | 200 | 880g | 용량 충분하나 발끝 관성↑ |

⚠ **솔직한 단서**: RS01/02(6/17)는 클리핑은 면하나 **연속 6 N·m**라 RMS demand(~7.5+)를 여전히 못 받침 → 열 바인딩 잔존 가능. **권고 순서: ① demand 저감(설계로 14 포화 자체 제거 = 최선, 모터 키우면 발 무거워짐) ② RS01/02 상향(클리핑 해소·연속 경계선) ③ 지속 포화 시 RS03급(질량 트레이드오프 평가)**. → rough+DR sweep 후 ankle_roll demand 재측정해 확정.

---
관련: [[35_knee_gear_ratio_analysis]] · [[33_knee_actuator_landscape]] · [[sweep_gear_ratio]] · [[robstride-datasheet]] · [[28_reward_actuator_fidelity]]
