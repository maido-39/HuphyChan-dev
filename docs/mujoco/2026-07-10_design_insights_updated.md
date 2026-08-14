# ★ 설계 인사이트 종합 v2 — 모던 계보(권위 데이터)로 갱신

> 2026-07-10. [[2026-07-03_design_insights_all_regimes]]의 그래프·수요표를 **07-03 이후 학습한 정책 전부**로 갱신(별개 노트, 원본 무결). 추가 데이터: mjlab **P2-final flat**(2단계 커리큘럼, 현행) · **R2 rough 40k**(최종 config) · ★**rough P2-final**(2단계 커리큘럼·in-DR wide-DR = 권위 rough) · init-pose A/B(bent) · knee220 probe. 대조 앵커로 g1vanilla(무규율 참조)·pushoff_v9(리워드 해킹 상한)·stage4(구 IsaacLab rough) 유지.
> ★모던 config = **ankle_pitch effort 90(2×RS03 2-RSU co-act, rated 40)·ankle_roll 50(2×RS00, rated 10)** — 07-03 시대(60/14 단일모터)와 한계선 다름. 도구: `regime_compare_v2.py`. 데이터 ×1.15(마찰), 한계선 실정격.

관련: [[2026-07-03_design_insights_all_regimes]](원본) · [[2026-07-03_final_design_point]] · [[64_joint_bearing_design_inputs]] · [[63_peak_provenance_clips]]

---

## 0. 수요표 갱신 — 모던 계보 ($|\tau|$ RMS/P99/max · $|\omega|$ P99/max rpm)

| regime | knee | ankle_pitch | ankle_roll | hip_pitch |
|---|---|---|---|---|
| g1vanilla(무규율) | 31/93/138·98/200 | 44/**69clip**·**184/200** | 11.5/16clip·97/**307** | 37/103/138 |
| pushoff_v9(해킹) | 44/**224**/248·86/112 | 48/**69clip**·58/218 | 10.6/26/31·54/102 | 41/138/138 |
| **P2-final flat**(현행) | **17/49/138**·68/129 | **15.8/66/92**·75/170 | **3.8/14/27**·39/144 | 17.6/61/127 |
| bent(init A/B) | 33/83/120·86/139 | 22.8/64/102·68/108 | 2.2/8/14·18/61 | 21/79/132 |
| knee220 probe | 25/60/112·50/72 | 15.6/53/73·44/89 | 3.6/14/19·27/81 | 15.8/66/90 |
| stage4_rough(구) | **84/157/212**·67/71 | 13/44/69·75/146 | 8.4/16clip·81/**337** | 29/78/102 |
| R2 rough 40k | 42/102/138·51/151 | **9.0/26/37**·41/118 | 5.1/17/27·38/93 | 22/65/138 |
| ★**rough P2-final**(권위) | **30/110/138**·89/**262** | **9.5/30/68**·85/153 | **4.9/16/38**·53/146 | 19/61/130 |

## 오버레이 선도 (색=레짐, 굵은=50%코어·얇은=99%, 한계선=실정격)
### FLAT (5종: 무규율·해킹 앵커 + P2-final·bent·knee220)
![[v2_regimes_flat_speed_torque.png]]
![[v2_regimes_flat_q_torque.png]]
![[v2_regimes_flat_q_speed.png]]
### ROUGH (3종: stage4 구 / R2 40k / ★rough P2-final 권위)
![[v2_regimes_rough_speed_torque.png]]
![[v2_regimes_rough_q_torque.png]]
![[v2_regimes_rough_q_speed.png]]

---

## 1. 인사이트 갱신 (07-03 대비 확증/변경)

### I1 (확증·강화) — 관절별 리워드 민감도, 이제 권위 데이터로
- **ankle = 정책지배 재확인**: ankle_pitch RMS **9.0~48(5×)**, ankle_roll **2.2~11.5(5×)**. ★단, **모던 정책(P2/R2/roughP2) 전부 ankle_pitch RMS 9~16**로 수렴 = "규율된 스택"이 스타일 무관하게 발목을 rated(40) 훨씬 아래로 눌러줌. 무규율(g1v 44·해킹 48)만 상단.
- **hip 리워드 불변 확증**: hip_pitch RMS 15.8~41(모던은 17~21로 더 좁음) → 타이트 사이징 유효.
- **knee 중간·높은 하한**: RMS 17~84, 모던 권위(roughP2) 30/P99 110 — 여전히 구조지지 일이 하한.

### I2 (★변경) — ankle_pitch 클립 해소 = 2-RSU 사이징 검증됨
- 07-03: "7개 IsaacLab 레짐 전부 ankle_pitch 69 클립 포화" → HW 미결. **v2: effort 90(2-RSU)로 올린 모던 config에서 P2-final max 92·P99 66·RMS 15.8 = 클립 없이 rated(40) 이내 여유**. R2/roughP2도 P99 26~30. → **2-RSU(2×RS03 co-act)의 헤드룸이 실측 확인**. 무규율 정책만 가정하면 여전히 태우지만(g1v 44 RMS), 규율 스택 전제 시 대여유.
- 역방향(해킹) 증거 유지: pushoff_v9 knee P99 **224**.

### I3·I4 (확증) — knee 신전 단방향·ankle plantarflex 우세, 모던도 동일
signed 선도상 knee +신전 기둥·ankle 부호 분포는 레짐 불변(roughP2 tau 부호분포 −68~+138 유지). 링크 압축·2-RSU 크랭크 배향 결정 불변.

### I5 (★신규 주의) — 모던 rough도 knee 속도 peak 高
rough P2-final knee $\omega$ **max 262 rpm(27.4 rad/s)** — RS04 실측 무부하 19.9 rad/s 초과(P99는 89rpm/9.3rad/s로 무관). 즉 **정상화된 정책에서도 순간 무릎속도가 sim-to-real 갭에 걸림**([[reference-robstride-motor-specs]]). velocity_limit 19.9 재학습이 여전히 필요(진행 중인 2.5 커리큘럼에 병합 검토).

### I6 (갱신) — 설계 엔벨로프
| 관절 | 설계 기준(모던 권위 = roughP2/P2/R2) | 강건 기준(무규율) |
|---|---|---|
| knee | RMS 17~42·P99 49~110·max 138(클립) → **RS04+링크 1.5:1** 유효(peak 커버) | stage4 RMS 84 → 링크 1.5:1로 56=93%⚠ |
| ankle_pitch | RMS 9~16·P99 26~66 → **2-RSU(90) 대여유**(rated 40의 40%) | g1v 44 → 2-RSU 필수(단일 RS03 220%) |
| ankle_roll | RMS 3.8~5.1·P99 14~17 → **2-RSU(50) 여유**(rated 10) | g1v 11.5 → 여유 |
- ★**결론 갱신**: 07-03의 "2-RSU 필요성 확정"이 모던 권위 데이터로 **정량 확인** — ankle_pitch/roll 모두 규율 스택에서 2-RSU rated 이내 안착. 강건(무규율) 시나리오만 상단 압박.

### I7 (갱신) — 링크 반력 WRENCH
![[v2_regimes_wrench_flat.png]]
![[v2_regimes_wrench_rough.png]]

- **|F| P99**: 모던 정책 대폭 저감. flat P2-final foot P99 **657N**(≈1.3×BW)·max 2.69kN vs 해킹 pushoff max **6.2kN**·구 stage4-rough max **6.6kN**. **rough P2-final(권위) foot P99 873N·max 3.1kH** — 여전히 HW 파손한계 2.7kN을 peak서 초과하나 P99는 크게 아래. ★**bent init-pose가 최저**(foot max 707N) = 충격흡수 A/B 확증([[55_init_pose_straight_vs_bent]]).
- **|M| P99**: rough P2-final ankle/foot P99 167~173·**max 612~614 N·m**, shin P99 104·max 323. → FEA 모멘트 케이스 = 모던 P99 ~170(정상)/max 610(권위 rough)·구 레짐 상한 690~860.
- ★FEA 3단 갱신: 설계=**rough P2-final P99**(foot F 870N·M 170N·m)+SF · 검증=모던 union max(F 3.1kN·M 612) · 파국=해킹 6.2kN(리워드 규율 미보장 시). 관절프레임 분해·베어링 통계는 [[64_joint_bearing_design_inputs]].
- 단위: wrench ×1.15 미적용(구조반력). 모던 mjlab은 toe_link 없음(강체발) → toe 행 부재.

---

## 2. 종합 판정 (모던 데이터 기준)
1. **"리워드=사이징" 재확증**: 동일 로봇·규율 스택이면 ankle 수요가 rated 이내 안착(P2/R2/roughP2), 무규율/해킹만 상단 → HW 스펙에 **리워드 규율을 운용조건 명기** 원칙 유지·강화.
2. **2-RSU 헤드룸 실측**: ankle_pitch(90)·roll(50) 모두 모던 권위 데이터서 rated의 30~40% → 설계점 견고.
3. **knee = 유일 잔존 구조 하한**: P99 110·peak 138(클립) → 링크 레버 1.5:1 필수 불변.
4. **잔여 리스크**: knee $\omega$ peak 262rpm(sim-real 갭) → velocity_limit 재학습. rough foot |F| peak 3.1kN(파손한계 근접) → 충격cap 유지·bent자세 검토.

## 3. 재현
```bash
cd mujoco-sim/mjlab && CUDA_VISIBLE_DEVICES="" uv run python analysis/regime_compare_v2.py --out ../../docs/mujoco/assets
# → v2_regimes_{flat,rough}_{speed_torque,q_torque,q_speed}.png + v2_regimes_wrench_{flat,rough}.png + v2_regimes_{stats,wrench,limits}.csv
```
REGIMES_FLAT/ROUGH·모던 한계선(MJLAB_LIMITS_MODERN)·색: `regime_compare_v2.py`. 원본 07-03 그래프는 무손상 유지.
