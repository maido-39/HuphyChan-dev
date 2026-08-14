# 직립 default → stiff-legged gait + 파일 오편집 규명

> 2026-07-06. V4(직립 무릎 default) 측정서 발견: ① 무릎이 walking서 −12°만 굽음(정상 −60°+) = stiff-legged, ② L/R 비대칭·역관절 수정이 실제로 반영 안 됨. 근본원인 규명 + 리워드 std 변경 정당화(HOOK).

## 1. 파일 오편집 (기구 수정 미반영)
- 로봇 spec은 `get_spec()` → **`PYG_XML = xmls/pygmalion.xml`** 로드.
- 내가 대칭·역관절0° 수정을 **`pygmalion_v2.xml`(미사용)** 에 함 → **학습엔 미반영**.
- 실제 학습 모델(pygmalion.xml): L_knee −140/**+10°**, R_knee −125/**+10°**(비대칭·하이퍼익스텐션 여전), R_hip_yaw ±40, R_toe −45. 측정 npz서 무릎 +13° overshoot 확인(소프트 리밋 초과).
- (측정 .mjb의 전 관절 ±20°는 measure_loads 저장 아티팩트 = 실제값 아님. npz qpos가 진짜.)

## 2. stiff-legged 근본원인 = 직립 default × pose 리워드
- `variable_posture` 리워드는 **`default_joint_pos`(=init_state)를 타깃**으로 $\exp(-err^2/std^2)$.
- init을 HOME(무릎 0° 직립)으로 바꾸니 **walking 중에도 타깃이 직립 무릎**.
- `std_walking[knee]=0.35`rad(20°): 무릎을 −40°로 굽히면 $err$=0.7 → $\exp(-4)$=0.018 = 강한 페널티. → 정책이 무릎을 −12°만 굽히는 **stiff-legged**로 수렴.
- 구 KNEES_BENT(default 무릎 −38°)에선 타깃이 굽힘이라 자연 보행 굽힘이 보상받았음.

## 3. 해법 (직립 default 유지 + 보행 굽힘 허용)
사용자 요구(정지 자세 직립)는 유지하되, **walking 시 무릎 굽힘을 penalize 안 하도록 std 완화**:
- `std_walking[knee]` 0.35 → **1.2**rad(69°): 보행 중 −60°+ 굽힘 자유(정지는 std_standing 0.05로 여전히 직립 타이트).
- `std_running[knee]` 0.6 → **1.5**rad: 달리기 더 큰 굽힘.
- 원리: variable_posture는 command 크기로 std_standing↔walking↔running 블렌드 → **정지=직립 강제, 보행=굽힘 허용** 동시 달성.

## 4. 기구 수정 (올바른 파일 pygmalion.xml)
- L/R 대칭: R_hip_yaw ±40→±50, R_knee flex −125→−140, R_toe −45→−50.
- 역관절 0°: L·R knee 상한 +10°(0.174533) → **0.0**(하이퍼익스텐션 금지, 소프트리밋이라 소량 overshoot 잔존 가능 — 필요시 solreflimit 강화).

## 5. 검증 지표 (재학습 V5)
- ① 무릎 walking flex −60°+ (stiff 해소), ② 정지 무릎 ~0°(직립 유지), ③ L/R 대칭(접촉duty·토크), ④ 역관절 ≲0°, ⑤ gait cycle double-support ~25%.
