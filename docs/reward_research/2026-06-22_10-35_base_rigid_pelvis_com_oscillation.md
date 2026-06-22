# reward 연구 — base(골반) 과도하게 rigid → CoM 수직진동 부족 (2026-06-22)
> 트리거: 측정 — base_link(골반) 수직 CoM 진동 std ~1.0cm (amp ~1.4cm) = 사람(~2.5cm amp)의 **~55%**. 바꾸려는 reward: base_height_l2(−1.0)·flat_orientation_l2(−1.0)·lin_vel_z_l2(−0.2)·ang_vel_xy_l2(−0.05)·upright(+0.5). 가설(user): 이들이 자연 골반 swing(fore-aft + up-down + tilt/rotation)과 push-off vault를 억제. 조사(web, 6 sources, high confidence).

## 1. 직전 결과 분석
- base CoM 수직 amp ~1.4cm vs human ~2.5cm. 토우(MTP) 거의 안 굽음(별도 finding). → **rigid pelvis + flat toe**가 같이 묶임.
- 관측: base_height_l2가 *고정 목표높이*를 강제 → single-support vault의 CoM 상승을 페널티 → push-off과 직접 충돌.

## 2. 이전 이력
- forefoot_cop / ankle_pushoff / forefoot_pushoff 시도사 ([[experiments/2026-06-21_15-40-30_forefoot_pushoff]] 등) — 토우 rollover 약함 반복. base reward와의 결합은 미검토.

## 3. 학술/자료조사 (high confidence) — 사람 골반/CoM 수치 [[raw/human-pelvis-com-kinematics]]
- **골반 ROM (PMC5545133, n=44)**: TILT(sagittal) 2–5° (mean 4.3°, biphasic 2/stride); OBLIQUITY(frontal drop) 6–11° (mean 7.4°, 2/stride); ROTATION(transverse) 3–14° (mean 9.5°, 1/stride). [출처](https://pmc.ncbi.nlm.nih.gov/articles/PMC5545133/)
- **수직 CoM amp ~3–5cm**(고전 canon ~5cm pk-pk; Gard 3.0±0.4cm; Orendurff 2.74cm slow→4.83cm fast). **M-shape**: CoM **최고=mid-single-support(vault apex)**, **최저=double-support**, 2 peaks/stride, PE↔KE 진자교환. ML amp ~5cm@1.4m/s. [Orendurff](https://pubmed.ncbi.nlm.nih.gov/15685471/) · [Frontiers review](https://www.frontiersin.org/journals/neurology/articles/10.3389/fneur.2019.00999/full)
- **Six determinants**: 골반 rotation 8°→CoG −9.5mm, tilt 5°→−3mm, stance knee 5°→peak↓. 이 항들은 M을 *납작하게* 만드는 기구지만 결과는 여전히 3–5cm — **rigid가 아니라 "controlled rise"**. [podiapaedia](https://podiapaedia.org/wiki/biomechanics/gait/determinants-of-gait/)
- ★ **납작한 CoM은 비싸다 (Ortega & Farley JAP 2005)**: CoM 수직운동을 *억지로 평탄화*하면 CoM work는 줄어도 **순 대사비용 +~6%**(crouch 지지근력↑·진자교환 손실). 자연 vault가 대사 최적. [출처](https://journals.physiology.org/doi/full/10.1152/japplphysiol.00103.2005)
- ★ **push-off ↔ CoM 결합**: 후행 ankle push-off가 double-support에서 CoM 속도를 redirect, CoM 에너지변화=push-off 에너지의 86–96% [Kuo transition](https://pmc.ncbi.nlm.nih.gov/articles/PMC2726857/). push-off **−50%**면 대사 **+~50%**, collision +0.6J/1J, 무릎이 stance work로 보상 [Huang/Kuo](https://pmc.ncbi.nlm.nih.gov/articles/PMC4664043/). late-stance push-off가 CoM을 *위·앞*으로 impulsive하게 밀어 다음 vault로 [Lipfert JEB](https://journals.biologists.com/jeb/article/217/8/1218/).

## 4. 원인·문제 규명
- ★ **base_height_l2(−1.0, 고정 target)가 핵심 범인**: single-support vault의 CoM 상승(~2.5cm)을 페널티 → push-off가 CoM을 들어올리면 height 페널티↑ → policy가 **push-off과 vault를 둘 다 억제**. 토우가 안 굽는 것·CoM amp 55%가 *같은 원인의 두 증상*.
- flat_orientation_l2(−1.0)·ang_vel_xy_l2(−0.05): 골반 tilt(4°)·obliquity(7°) sagittal/frontal 진동을 억제(transverse rotation은 base orientation L2가 직접 막진 않지만 pitch/roll은 막음).
- lin_vel_z_l2(−0.2): 수직 CoM 속도 = vault의 미분 → 직접 진자운동 억제.
- 결과: **비현실적으로 rigid한 골반 → HW 설계용 관절하중이 비현실적**(목적 위배). 사람은 3–5cm vault + 4–10° 골반 swing이 *정상이며 대사최적*.

## 5. 제안 (reward 변경 + 왜)
1. ★ **base_height_l2(−1.0) 완화/재형상**: 고정 target 페널티 → (a) weight를 **−1.0→−0.25** 정도로 낮추거나, (b) **하한만 페널티**(주저앉음 방지)하고 *상승은 허용*하는 비대칭/deadband로. 목표: vault의 ~2.5cm 상승 허용. push-off·토우와 직접 coupling.
2. **lin_vel_z_l2(−0.2)→−0.05** 수준: 수직 CoM 속도(vault 미분)를 너무 누르지 않게. (완전 제거는 bounce 위험 → 약하게 유지.)
3. **flat_orientation_l2(−1.0)**: pitch/roll 4–7° 골반 swing 허용 위해 **−0.5** 또는 deadband. ang_vel_xy_l2(−0.05)는 이미 작음 — 유지 가능.
4. **검증 지표 = HW 질문의 답**: 재학습 후 (i) base CoM amp 1.4→~2.5cm 접근?, (ii) M-shape(midstance 최고/DS 최저) 출현?, (iii) 토우 rollover·ankle push-off 토크↑? → 그러면 base reward가 진짜 범인. 변화 없으면 다른 항(토우/ankle) 우선. **사람 ROM(tilt 2–5°·obliq 6–11°·rot 3–14°·vert 3–5cm)이 sanity range.**

출처: 위 하이퍼링크 6편(전부 peer-reviewed/임상). verified=사람 수치·대사비용 / 추정=우리 base reward로의 귀속(재학습으로 확인).
