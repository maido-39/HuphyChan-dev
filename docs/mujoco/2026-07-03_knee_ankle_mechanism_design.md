# Knee 링크·Ankle 2-RSU 설계 — 그림으로 보는 방법론 (v2)

> 2026-07-03 v2: "이해 안 됨" 피드백 반영 전면 재작성 — **다이어그램 + DR 커버리지 검증 + in-DR/OOD 분리 + contour 선도**. v1의 결론은 유지하되 ★**worst-case 수치의 OOD 오염을 발견·보정**(§3).

관련: [최종 설계점](2026-07-03_final_design_point.md) · [actuator eval](2026-07-01_actuator_evaluation.md)

**★ 데이터 기준 정책**: 본 노트의 모든 선도·수치 = **B3@12k 최종 정책**(최종 reward 스택: A1b gains+충격cap+열분배+Siekmann; run `2026-07-03` model_12000, wandb `m4ik3uph`=B3-siekmann-FINAL-DESIGN-POINT). `final_flat`=그 정책의 worst-case flat, `final_rough`=**동일 정책의 blind rough 배포**(보수 상한 — R1 rough 정식학습 수렴 시 교체). 움직임 확인: `assets/final_flat_loadviz.mp4`(실시간)·`final_flat_dashboard.mp4` 또는 teleop 뷰어.

---

## 1. 한 장 요약 — 무엇을 만들려는가

![[mech_diagrams.png]]

- **Knee(왼쪽 그림)**: 모터를 무릎이 아니라 **허벅지(근위)에 두고**, 크랭크→푸시로드→정강이 레버로 무릎을 민다. 지렛대 원리: **모터토크 = 무릎토크 ÷ 레버비 r(q)**. r≈1.5로 잡으면 무릎이 요구하는 50 N·m RMS가 모터에겐 33 N·m(RS04 rated 40의 83%)이 된다. 로드는 밀고 당기기만 하므로 heel-strike 충격에 강하고, 벨트처럼 장력·텐셔너가 없다.
- **Ankle(오른쪽 그림)**: G1/Digit식 **2-RSU 병렬** — 정강이 위쪽의 모터 2개가 로드 2개로 발판을 민다. **두 로드가 같이 밀면 pitch, 반대로 밀면 roll**. 그래서 pitch 부하(우리의 큰 쪽)를 **모터 2개가 나눠** 든다(모터당 절반). 모터가 위로 올라가 발이 가벼워진다(원위 관성↓).

## 2. 힘 계산 — 딱 3단계

![[mech_pipeline.png]]

1. **수요**: 우리가 이미 측정한 관절별 (각도 q, 토크 τ, 속도 ω) 구름(npz).
2. **기구 사상**: 후보 기하(크랭크 길이, 로드 길이, 부착점)가 정해지면 각도별 레버비 r(q)(knee) 또는 2×2 Jacobian J(q)(ankle)가 계산됨(폐루프 기하, 코사인법칙 수준) → **모터가 실제로 내야 하는 토크·속도**로 변환: $\tau_m = \tau_j/r(q)$, $\omega_m = \omega_j\cdot r(q)$ (ankle은 $\tau_m = J^{-T}\tau_j$).
3. **판정·최적화**: 변환된 구름이 **모터 TN곡선 안**에 들고, $RMS(\tau_m) \leq rated$(열), ROM 내 특이점 없음 → 만족하는 기하 중 마진 최대/질량 최소를 고른다.

이 파이프라인은 2025년 IIT 논문(Cervettini, §7)이 **그대로 공인**한 방식이고, 우리 `actuator_eval`에 J(q)만 끼우면 된다(`mech_design_eval.py`로 구현 예정).

## 3. ★ 엄밀성 검토 — "worst-case"가 진짜 worst-case였나? (v2.1 정정)

![[dr_coverage.png]]

**학습 DR의 실체(커리큘럼 3단계, B3@12k 기준)**: vx∈[−2.0, **3.0**] · vy∈[±1] · yaw∈[±**0.7**]. 측정 스케줄(vx≤2.5)의 vx는 **전부 in-DR**이었고, **yaw>0.7 코너만 OOD**였다(초기 v2에서 vx 오염을 과대평가했던 것 정정 — 커리큘럼 3단계를 놓쳤음).

**in-DR만으로 재계산**(×1.15, `design_plots.py`):

| joint | 지형 | τ RMS/P99/max (in-DR) | ω P99/max (in-DR) | ALL 대비 차이 |
|---|---|---|---|---|
| knee | flat | 44 / 93 / 138 | 41 / 101 | ≈동일(오염 미미) |
| knee | rough† | 46 / 138 / 138 | 74 / **341** | ≈동일 — ★스파이크는 OOD가 아니라 **blind 헛디딤** |
| ankle_pitch | flat | 9.8 / 38 / 65 | 43 / 122 | ≈동일 |
| ankle_roll | rough† | 0.9 / 2.6 / 8.5 | 83 / **183** | 속도 max만 363→183(yaw-OOD 기인) |

† rough = blind 배포(B3 flat정책이 지형 못 봄) — **속도 스파이크(341rpm 등)의 주범은 명령이 아니라 실명(blind) 헛디딤**. → 해법은 측정 스케줄 조정이 아니라 **R1(rough 정식학습, height_scan)**.

**결론(정정판)**: ① flat 설계수치는 명령-OOD 오염 미미 = 유효. ② ★**rough의 극단 속도는 blind+OOD 아티팩트로 실측 확인됨** — R1b 정식학습(100% in-DR worst-case): GRF P99 1.50·knee RMS 93%·ankle 여유 = 깨끗(설계점 노트 rough행).  ③ ★**사용자 지시로 학습 DR 확장**: yaw ±0.7→**±1.5**(vx는 이미 3.0), R1b가 확장 DR로 resume 학습 중 → 이후 worst-case(vx2.5·yaw1.5)는 **구성상 전부 in-DR**.

## 4. 설계 선도 — flat/rough 색분리 + 밀도 contour (신규 룰)

각 점구름 위에 **실선=50% 코어(전형 듀티≈RMS 대역) · 파선=99%(≈P99 영역) · 점선=99.9%(≈peak 영역)**, 회색=OOD. 파랑=flat, 주황=rough. ★**v2.2: 전 선도 signed(절대값 제거)** — 사분면(II/IV=제동/회생)과 방향별 하중이 보이도록 소급 재생성(사용자 지적).

**속도-토크 (+TN곡선)** — "모터가 낼 수 있는 영역 안에 수요가 드는가":
![[contour_speed_torque.png]]
읽기(signed): ★**knee 토크는 사실상 단방향(+, 신전지지)** — 0속도 부근 수직 기둥(+50~+138) = stance 유지하중 → **푸시로드가 주로 한 방향 압축**을 받는다는 뜻(로드 좌굴설계 기준 방향 확정). ★**ankle_pitch는 음(−, plantarflex push) 우세의 십자형** — 2-RSU 크랭크를 plantarflex 토크 쪽에 유리하게 배향. hip은 대칭. 전 관절 in-DR 99%가 미러 TN 안.

**각도-토크** — "스트로크 어디서 힘이 필요한가 → 레버 피크 배치 근거":
![[contour_q_torque.png]]
읽기: knee 토크는 −40~−80°(stance 굴곡)에 집중 → **레버비 피크를 이 각도대에 배치**. ankle_pitch는 +10~+40°(dorsi 지지) 집중 → 2-RSU 크랭크 레버를 거기 정렬(RH5가 실제로 한 방식).

**각도-속도** — "관절범위·속도한계 사용률":
![[contour_q_speed.png]]
읽기: knee 속도 코어는 한계 안, 파선이 −40~−80°서 143rpm에 근접(레버 1.5:1 시 모터측은 95rpm 한계 — in-DR P99 41→62rpm 환산으로 여유. worst 순간만 클립).

## 4b. ★ Kp/Kd·effort 감사 + G1 매칭 (2026-07-04)

**Gain 감사** (사용자 지적 — G1 33kg vs Pygmalion 51.5kg):
| 관절 | Pygmalion(전) Kp/Kd/eff | Unitree G1 Kp/Kd/eff | 판정 |
|---|---|---|---|
| hip_pitch/roll | 400 / 28 / 120 | 40–99 / 2.6–6.3 / 88–139 | ⚠ Kp **4× G1**(chirp 10Hz·ζ2 유래; 질량 1.55×로도 과함) — 작동하나 과강성 의심 |
| knee | 400 / 8 / 120 | 99 / 6.3 / 139 | ⚠ 동상 |
| **ankle_pitch** | **19.7** / 1.26 / 60 | 28.5 / 1.81 / 50 | ❌ armature(로터관성)유래=소프트 |
| **ankle_roll** | **1.97** / 0.13 / 14 | 28.5 / 1.81 / 50 | ❌❌ **G1의 1/14** = 위치권한 거의 0(부하 작아 "작동"했을 뿐) |

**→ 2-RSU 전환 조치**: ankle 근본문제 = 로터관성만으로 gain 산정 → **G1 ankle 스펙 정렬**: ankle_pitch=ankle_roll **Kp 28.5·Kd 1.81·effort 50 N·m**(2-RSU라 pitch/roll 대칭=양 모터 co-actuation). 근거: G1이 동일 2-RSU를 33kg서 이 스펙 운용. 측정수요(ankle_pitch peak 65)는 2-RSU 분담(~32/모터)으로 커버, roll(peak 2.8) 대여유. 질량 1.55×라 보수적 대안 ×1.5→75. 구현: `pygmalion_constants.py` ANKLE_2RSU_{KP,KD,EFF}.
> hip/knee Kp 400은 유지(chirp 검증·현 정책 학습됨). G1 대비 과강성은 **다음 실험 후보**(G1급 Kp로 낮춰 부하·자연스러움 비교, 재학습 필요라 별도 변인).

## 4c. ★ 2-RSU 실사이징 (mech_design_eval.py — J^T f, 2026-07-04)

사용자 지적("effort가 G1 실모터로 검증됐나")에 답: **G1 ankle 실모터 토크는 비공개**([리서치](../reward_research/2026-07-04_g1_ankle_effort_grounding.md)) → 우리 모터×기하 Jacobian으로 직접 사이징.

**수렴 rough(최악) 수요 → 2모터 사상** (crank 30mm):
| 레버비 a_p/r_c | 모터 τ peak | 모터 ω peak | 커버 모터 |
|---|--:|--:|---|
| **1.0** | 36 N·m | 188 rpm | ✅ **RS03**(60/191) |
| 1.5+ | 26 | 217↑ | ❌ 속도초과 |

- ★ **pitch는 2모터 co-actuation** → 관절 capability = $2\times\tau_{motor}\times$레버 $= 2\times 60\times 1 =$ **120 N·m**(RS03 2개). roll은 차동(낮음).
- **2×RS03 2-RSU가 수렴 수요 커버**: pitch 65≪120·roll 2.8 무시. **속도(188/191rpm)가 binding**(토크 아님) → 레버비 ~1.0 유지.
- → sim effort **비대칭 정정**: pitch 90(co-act)·roll 50(차동). 대칭 50/50은 2-RSU 물리 오표현이었음.
- 정밀화: 현 평면근사 → 실 부착점·로드 FK Jacobian(다음).

## 5. Knee에 벨트 감속? — 판정: 링크 레버로 (쉬운 설명)

1. **무엇이 필요한가**: knee는 열(RMS 44 vs rated 40)이 문제 → **1.4~1.6× 토크 증배**가 필요. 속도는 in-DR서 여유(코어 41rpm).
2. **벨트로 하면**: 관절측 127 N·m를 지름 8cm 풀리로 받으면 벨트에 **~3.2 kN 장력** — 광폭·대구경 필수 = 무겁고 큼 + 충격 시 톱니 스킵 위험. (MIT Humanoid가 21kg급에서 벨트 최종단 136 N·m을 실증했지만, 우리 체급(51.5kg 연속보행)의 아날로그 RH5·Kangaroo·BHR8은 전부 링크/볼스크류.)
3. **링크로 하면**: 어차피 링크 knee로 가므로 **레버비 자체를 1.4~1.6으로 설계**하면 부품 추가 없이 같은 효과 + 로드는 충격에 강건 + §4의 각도-토크 집중대에 레버 피크를 놓는 보너스.
→ **벨트는 불필요. 쓰더라도 모터측 저토크 보조단(≤2:1)만.**

## 6. 다음 단계
1. `mech_design_eval.py`: §2 파이프라인 구현 — 2-RSU(파라미터 4~5개)·knee 푸시로드(3개) 기하 스윕 → 마진 히트맵.
2. R1(rough 정식) 수렴 → rough 열을 실측으로 교체(현 blind 상한 대체).
3. 확정 기하 → 로드 부재력 F_rod = τ/lever + §3 wrench → FEA 하중케이스.

---


## 6b. 관절 부호 규약 (±각도·±토크 방향) — FK 검증 + 애니메이션

앞선 선도들의 signed 축(+/−)이 물리적으로 무엇인지 = **모델에서 각 관절을 +방향으로 꺾어 발이 어디로 가는지 FK로 실측**해 확정(추측 아님). 좌표: 전방 +x·좌 +y·상 +z, 좌측 다리 기준.

![[joint_sign_convention.gif]]

*(각 관절이 +방향으로 스윕. GIF/MP4: `assets/joint_sign_convention.{gif,mp4}`)*

| 관절              | **+ 방향**               | − 방향                              | 회전축(월드) · 선도 판독                                                                          |
| --------------- | ---------------------- | --------------------------------- | ---------------------------------------------------------------------------------------- |
| hip_pitch       | **신전**(다리 뒤로)          | 굴곡(앞)                             | +y축                                                                                      |
| hip_roll (L)    | **외전**(다리 바깥)          | 내전                                | +x축                                                                                      |
| hip_yaw (L)     | **내회전**(발끝 안쪽)         | 외회전                               | −z축                                                                                      |
| **knee**        | **신전**(폄)              | **굴곡**(구부림)                       | −y축. q 전부 음수(−95~−20°)=상시 굴곡; **+토크=신전 지지토크**(stance 평균 +57, 99%) → §4-I3 푸시로드 **압축** 정합 |
| **ankle_pitch** | **dorsiflexion**(발끝 위) | **plantarflexion**(발끝 아래=toe-off) | −y축. **−토크=plantarflex 지지/push-off 토크**(stance 평균 −4, 67%) → §4-I4 정합                    |
| ankle_roll (L)  | **eversion**(바깥날 내림)   | inversion                         | −x축                                                                                      |

### 좌우(L/R) 회전축 — 경험적 확정 + G1 비교 (사용자 지적)
발 이동 실측으로 확정: **같은 +q가 양다리에서 동일 해부학동작이냐**로 정렬 여부 판정.

| 관절군 | L/R 로컬축 | +q_L vs +q_R 해부학 | 정렬? |
|---|---|---|---|
| hip_pitch·knee·ankle_pitch (sagittal) | **동일** | 둘 다 신전/dorsi = 동일 | ✅ 이미 정렬 |
| **hip_roll·ankle_roll** (frontal) | **반전**(L=−R) | 둘 다 외전/eversion = 동일 | ✅ **미러축이 이미 정렬**(발 실측 L+y·R−y=둘다 외전) |
| **hip_yaw** (transverse) | **동일**(둘 다 −z) | +q_L=내회전 ↔ +q_R=외회전 = **반대** | ❌ **유일하게 R 플립 필요** |

★ **핵심**: roll 관절은 축이 반전돼 있어(mirror-authoring 결과) **raw q가 이미 양다리 해부학 정렬** — 플립 불필요. **hip_yaw만** 축이 동일(transverse)이라 raw가 어긋나므로 R 부호반전. 최종 **`MIRROR_FLIP={hip_yaw}`**만 signed 선도에 적용. (사이징 통계는 부호무관 불변.)

### 우리 회전방향이 일반적인가? — Unitree G1(양산 휴머노이드) 대조
`asset_zoo`의 G1 XML 관절축 추출 비교:
| 관절 | **Pygmalion** L/R 로컬축 | **Unitree G1** L/R 로컬축 |
|---|---|---|
| hip_pitch·knee·ankle_pitch | 동일 | 동일 |
| **hip_roll** | **반전**(0,−.97,.26 / 0,+.97,−.26) | **동일**(1,0,0 / 1,0,0) |
| **ankle_roll** | **반전**(0,1,0 / 0,−1,0) | **동일**(1,0,0 / 1,0,0) |
| hip_yaw | 동일(0,0,−1) | 동일(0,0,1) |

> ★ **두 관례가 공존, 우리 것은 "해부학(mirror) 관례", G1은 "월드(identical) 관례"**:
> - **Pygmalion(roll축 반전)** = 오른다리를 **기하 미러로 저작**한 결과(y성분 있는 roll축은 미러 시 부호반전, 순수 z인 yaw·sagittal은 불변) → **raw +q가 양다리 동일 해부학동작**(외전+). 사람 관절각 정의에 가까움.
> - **G1(roll축 동일)** = 축 벡터를 양다리 동일 문자열로 지정 → +q_roll이 **좌=외전/우=내전**(월드 동일 회전). CAD 미러 관례.
> - **결론**: 우리 방향은 "비정상"이 아니라 **미러-저작에서 자연히 나오는 정상 관례 중 하나**(오히려 해부학적으로 더 일관). 사용자 직관("joint tree상 어쩔 수 없이")이 **부분적으로 맞음** — 기하 미러 저작을 택하면 roll축 반전은 필연이나, G1처럼 축을 손으로 통일하면 피할 수도 있음(선택 사항). 분석엔 무영향: MIRROR_FLIP로 정렬만 하면 됨.

> ★ 부호는 **관절이 만드는 월드 회전축**으로 확정(point-변위 FK는 발 프레임 회전 탓에 발목서 노이즈 — docs/51 IsaacLab과 동일 축으로 교차검증). 초기 point-법의 hip_yaw·ankle_pitch·ankle_roll 오판정을 정정.

> ★ 이 규약으로 선도의 부호가 해석됨: 예) knee q-토크에서 **+토크(신전) 기둥**이 stance 지지 = 링크 로드가 받는 **압축** 방향. ankle_pitch는 plantarflex(−) 지지/push-off 토크 우세(stance −4, 67%; +토크=dorsi), knee는 신전(+) 지지토크 우세(+57, 99%). 재현: `MUJOCO_GL=egl uv run python analysis/joint_sign_anim.py`.

## 7. 레퍼런스 — ✅ 검증 완료 (deep-research `wruptxgvd`, 9 findings 전부 3-0)

### ★★ 우리 파이프라인(§2)과 동일한 공인 방법론
- **Cervettini et al. 2025** (IIT, arXiv:2509.16469): q(t)/q̇(t)/τ(t) 시계열 입력 → RSU/SPU 기하를 닫힌형 IK+J^T 사상 → 피크 액추에이터 토크·속도 bi-objective 최소화(상용 정격 제약). 직렬 대비 41%↓.
- **Lutz et al. 2025** (LAAS, arXiv:2503.22459): G1/H1/GR1/Digit/T1 ankle 계열의 닫힌형 기구학+2×2 Actuation Jacobian. ★설계룰: **수요·한계는 모터 공간에서**(상수비 근사는 병렬기구 능력 폐기; 4절 knee 특이점=완전굴곡/신전).

### 링크 MA 성형 / 체급 아날로그
- **Salto** (Science Robotics 2016, 10.1126/scirobotics.aag2048): 8절 링크 각도별 MA 성형의 원전.
- **BHR8-J1** (RA-L 2025, arXiv:2506.12314, 45kg): 볼스크류 knee의 닫힌형 k(θ) 3파라미터를 모터 TN 하 최적화 — "수요→모터평면" 정식화 최근접.
- **RH5** (DFKI, ICRA 2021, arXiv:2101.10591, **62.5kg 최근접 아날로그**): 병렬 ankle 121–304 N·m 각도의존 + 링크 knee. **피크 가용토크 각도 = 보행 피크수요 각도** 정렬 명시.
- **Kangaroo** (PAL, hal-03669855): 완전 링크 다리, 무릎 아래 모터 전무.

### 벨트 실증
- **MIT Humanoid** (arXiv:2104.09025, ~21kg): knee 6:1 유성×2:1 벨트=12:1, 136 N·m — 벨트 최종단 실증(경량·transient 듀티).
- **ODRI Solo** (RA-L 2020, arXiv:1910.00093): 9:1 2단 벨트, 2.7 N·m급 canonical.

## 8. 재현
```bash
cd mujoco-sim/mjlab
uv run python analysis/design_plots.py --flat final_flat --rough final_rough --out ../../docs/mujoco/assets
# → dr_coverage / contour_{q_torque,q_speed,speed_torque}.png + in-DR vs ALL 표
```
학습 DR 근거: `velocity_env_cfg.py:403-404`(커리큘럼 vx −1.5..2.0, yaw ±0.7). in-DR 마스크·contour 정의는 `design_plots.py` 참조.
