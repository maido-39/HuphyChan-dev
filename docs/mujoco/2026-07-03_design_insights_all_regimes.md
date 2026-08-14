---
share_link: https://share.note.sx/iutt041g#6qJ1xyjbYUpOJjSvd7Sg674M+rn7wi7+l+mIrcvXim8
share_updated: 2026-07-06T02:31:02+09:00
---
# ★ 설계 인사이트 종합 — 8개 리워드 체계 × 전 관절 수요 비교

> 2026-07-03. 06-21~29 IsaacLab 계보(gaitfix/G1vanilla/G1IS-tiptoe/humanref/Siekmann v8/pushoff v9/stage4) + mjlab FINAL(B3@12k)의 측정 npz **전부를 동일 분석(signed contour)으로 통과** → 리워드 설계가 관절 수요를 어떻게 바꾸는지, 무엇이 불변인지 → HW 설계 인사이트. 도구: `regime_compare.py`(stats CSV 포함).
> caveat: 구 측정=30s·vx≤1.0 스케줄, FINAL=144s worst-case — **크기 비교는 보수적, 형상·비율 비교가 본질**. 토크 max가 클립값(69/138/248/16.1/31)에 붙으면 그 시대 effort 한계 포화를 뜻함.

관련: [메커니즘 설계 v2](2026-07-03_knee_ankle_mechanism_design.md) · [최종 설계점](2026-07-03_final_design_point.md)

---

## 0. 한눈 요약 — 레짐별 수요 (×1.15, $|\tau|$ RMS/P99/max · $|\omega|$ P99/max)

| regime | knee | ankle_pitch | ankle_roll |
|---|---|---|---|
| gaitfix_v7 | 35/81/100 · 78/116 | 34/**69clip** · 43/90 | 6.5/16clip · 40/79 |
| g1vanilla | 31/93/138 · 98/200 | 44/**69clip** · **184/200** | 11.5/16clip · 97/**307** |
| g1is(tiptoe) | 20/69/248 · 73/111 | 44/**69clip** · 102/200 | **22/31clip** · 18/98 |
| humanref_v7 | **59/248clip** · 111/112 | **58/69clip** · 82/171 | 10.5/31 · 67/100 |
| siekmann_v8 | 33/115/248 · 76/112 | 47/**69clip** · 64/137 | 11.3/31 · 50/73 |
| pushoff_v9(해킹) | 44/**224**/248 · 86/112 | 48/**69clip** · 58/218 | 10.6/31 · 54/102 |
| stage4_rough | **84**/157/212 · 67/71 | 13/44 · 75/146 | 8.4/16clip · 81/**337** |
| **FINAL B3(mjlab)** | 45/94/138 · 42/101 | **9.4/36/65** · 45/122 | **0.7/1.9/2.8** · 40/130 |

★ **레짐별 개별 선도(그 시대 한계선+산출근거 캡션 포함)** = `assets/regime_<label>.png` — 각 실험노트 §R에 소급 임베드됨. 한계선 전표: `assets/regimes_limits.csv`(관절측 effort/rated/vel + 모터·기어 명기; env.yaml 파싱).

| 시대별 주요 차이 | knee | ankle_roll |
|---|---|---|
| gaitfix/g1vanilla/stage4 (06-21~22) | RS04 1:1 = 120/40 | RS00 = 14/5 |
| g1is~v9 (06-28~29) | **RS04×1.8기어 = 216/72·111rpm** | **DM-J4340 = 27/9·100rpm** |
| mjlab FINAL (07-03) | RS04 1:1 = 120/40·143rpm | RS00 = 14/5·315rpm |

**오버레이 선도** (색=레짐, 굵은선=50% 코어·얇은선=99%. ★한계선 포함: 빨강=Peak·주황=Nominal — knee/ankle_roll은 시대별 상이라 **시대별 선을 라벨로 병기**(pk 120/216/360 등), 검정=관절측 TN곡선. 데이터만 ×1.15, 한계선은 실정격 그대로):
### FLAT 레짐 (7종: 계보 6 + FINAL)
![[regimes_flat_speed_torque.png]]
![[regimes_flat_q_torque.png]]
![[regimes_flat_q_speed.png]]

### ROUGH 레짐 (3종: stage4 IsaacLab 정식 / B3 blind 배포=비관 상한 / ★R1 정식학습 3k)
![[regimes_rough_speed_torque.png]]
![[regimes_rough_q_torque.png]]
![[regimes_rough_q_speed.png]]

> rough 3종 읽기: blind(파랑)의 극단 속도 스파이크가 R1 정식(주황)에선 크게 줄어드는지가 "blind=비관 상한" 가설의 실측 검증 — R1 수렴본(진행 중)으로 최종 교체 예정.

---

## 1. 인사이트 (설계 결정용)

### I1. 관절별 "리워드 민감도"가 완전히 다르다 → 마진 전략을 관절별로
- **ankle = 정책-지배 관절**: ankle_pitch RMS **9.4~58(6×)**, ankle_roll **0.7~22(30×)** — 수요의 대부분이 리워드 스타일. **hip = 리워드 불변에 가까움**(전 레짐 코어 유사) → 타이트 사이징 가능. **knee = 중간**(RMS 20~84, 4×)이나 하한이 높음(구조적 지지 일).
- → HW 전략: hip은 현 사이징 유지 / knee는 **구조적 하한을 링크 레버로** / ankle은 **"어떤 정책을 보장할 수 있나"가 곧 모터 선정**.

### I2. ★ 리워드 설계 = 액추에이터 사이징이다 (정량 증명)
- **7개 IsaacLab 레짐 전부 ankle_pitch가 클립(69) 포화 + RMS 33~58(rated 20의 1.7~2.9×)** — 어떤 스타일이든 "무규율" 리워드는 RS03을 태움. **유일한 예외 = FINAL B-스택**(충격cap+열분배+Siekmann): RMS 9.4.
- 역방향 증거: pushoff_v9(리워드 해킹)는 knee P99를 **224**까지 폭주시킴.
- → **결론**: ① "우리 B-스택 정책 운용"을 전제하면 현 모터(RS03/RS00)로 충분(최종 설계점 판정 유지). ② 전제 못 하면(임의 리워드/향후 실험) **ankle_roll DM-J4340(27/9)·ankle_pitch 60 유지가 재정당화**됨 — 리워드 규율을 **HW 스펙 문서에 운용 조건으로 명기**할 것.

### I3. knee 신전(+) 단방향성 = 레짐 불변 → 푸시로드 압축 설계 확정
전 레짐에서 0속도 부근 **+신전 기둥**(stance 지지)이 지배. 단 나쁜 레짐(humanref)은 굴곡측(−248)도 침 — 로드 **인장측 검증도 포함**(압축 좌굴 + 인장 조인트).

### I4. ankle_pitch 토크는 **plantarflexion 지지/push-off 방향 우세** = 레짐 불변 → 2-RSU 크랭크 배향
★ 부호규약 확정(월드 축, docs/51 교차검증): **+각도=dorsiflexion, −각도=plantarflexion(toe-off)**. stance 토크 평균 **−4.0 N·m·67%가 음수(=plantarflex 지지/push-off 토크)** = 인간형 발목 모멘트와 정합(mjlab 강체발이라도 발목 push-off 토크는 발현). 대형 −60 스파이크 = 큰 plantarflex 토크. → **2-RSU 크랭크 레버 피크를 plantarflex(−) 측·dorsi 각도(+10~40°)대에** 배향(RH5식). 단 dorsi측(+) 토크도 33% 있어(heel-strike 제어) co-actuation 양방향 여유 필요.

### I5. ankle 속도 피크는 스타일 의존(73~337rpm) — 2-RSU 모터 무부하속도는 **200rpm급 확보** 권장(g1vanilla 184 P99가 실증하는 "정상 보행도 빠른 발목" 케이스).

### I6. 설계 엔벨로프 권고(종합)
| 관절 | 설계 기준(B-스택 전제) | 강건 기준(정책 미보장) |
|---|---|---|
| knee | RMS 45·peak 140 → **RS04+링크 1.5:1**(유효 60/180) | RMS 84(stage4-rough급) → 링크 1.5:1로 RMS 56=93% ⚠, **1.8~2.0:1 검토** |
| ankle_pitch | RMS 9.4·peak 65 → RS03급 2-RSU 대여유 | RMS 58 → **2-RSU 분담(29/모터)** 필수 근거 — RS03×2로 커버 |
| ankle_roll | RMS 0.7 → 여유 | RMS 22 → **DM-J4340(27/9) 재정당화** |
- ★ **2-RSU의 진짜 가치가 여기서 확정**: 강건 기준에서도 pitch 58 RMS를 두 모터가 29씩 나누면 RS03(rated 20)가 145%→ 여전히 초과… **정확 산술은 J(q) 배분 포함 `mech_design_eval.py`서** — 개략으로도 co-actuation 없인 불가능한 수치.

### I7. 링크 반력 WRENCH (구조/FEA 하중케이스) — 신규
![[regimes_wrench_flat.png]]
![[regimes_wrench_rough.png]]

- **P99 |F|**: FINAL B3가 전 링크 최저(≈1×BW 부근) — 충격cap의 구조하중 효과. 반면 **pushoff_v9 max 6.1~6.2kN(발/발목)** = 리워드 해킹이 구조하중도 폭주시킴(HW 파손한계 2.7kN의 2.3배!). humanref max 4.5kN.
- **P99 |M|**: 대부분 60~170 N·m 대역, FINAL은 ankle/foot서 ~105(장기 worst-case 프로토콜 탓) — FEA 모멘트 케이스는 **200 N·m급(정상)** / **500~870(비정상 레짐 상한)** 이중으로.
- ★ **FEA 하중케이스 확정치**: `assets/regimes_wrench.csv`(terrain×regime×body×F/M×rms/p99/max 전표). 설계 케이스 = FINAL P99(+안전율), 검증 케이스 = 정상 레짐 union max(~1.5kN/170N·m), 파국 케이스 = v9급(6.2kN — 리워드 규율 미보장 시).
- 단위 주의: wrench는 **×1.15 미적용**(구조 반력 — 액추에이터 토크에만 마찰보정 적용).

**★ 관절별 wrench 3D 시각화** (관절 위치에 화살표 — 빨강=반력 힘, 파랑=반력 모멘트):
![[wrench_arrows_final_flat.png]]
![[wrench_arrows_final_flat.mp4]]

- 근사측면(반투명 링크 40%·화살표 확대) 뷰. ★**모멘트가 원위로 갈수록 누적**이 육안 확인: stance 다리서 hip ~55Nm → shin ~147 → **ankle/foot ~247Nm**(가장 큰 파란 화살표). 힘도 hip 300N → foot 730N 증가. = 지지 다리의 하중이 발목으로 집중되는 gait 역학 → **ankle/foot 링크·베어링 FEA가 최대 케이스**.
- cfrc_int(월드프레임, com기준). peak-부하 프레임 정적 + gait 1주기 애니. 생성: `analysis/wrench_arrows.py`. 정량 P99/max는 위 막대·`regimes_wrench.csv`.

## 2. 방법/재현
```bash
cd mujoco-sim/mjlab && uv run python analysis/regime_compare.py --out ../../docs/mujoco/assets
# → regimes_{flat,rough}_{speed_torque,q_torque,q_speed}.png + regimes_wrench_{flat,rough}.png + stats/limits/wrench CSV
```
레짐·경로·색: `regime_compare.py` REGIMES. 전 선도 signed(v2.2 룰)·contour 실선/선폭 인코딩(v2.3 룰).
