# 39 · 발목 상향-토크 QDD 시장조사 — RS00/RS03 대체 저가 상용 후보 (검증, ankle-qdd-uptorque-survey)

> [!question] 검증한 질문
> 발목 **roll(RS00 직결, 포화 바인딩)** 을 비슷한 크기/무게로 **더 큰 토크**(~25-30 N·m peak, ~300-450g, Φ60-70)로 올릴 저가 상용 QDD가 있나? 발목 **pitch(RS03급, ~60 N·m)** 도 700-1100g·Φ90-110·peak 50-100 N·m 후보를 조사. RS00/RS03을 토크-at-size 또는 가격에서 이기나?

> [!abstract] 한 줄
> **ROLL: 명확한 승자 = DAMIAO DM-J4340 (27 N·m peak / 362g / Φ57 / 40:1 / $155).** RS00(14/310g/$125)과 거의 동일 외형에 **peak 토크 ~2배**, +52g·+$30뿐 — 디커플드 roll-직결 그대로 드롭인. 목표(25-30 N·m)를 단품으로 정확히 충족. **PITCH/MID: RS03(60/880g/$225)이 가격·토크밀도(66.7 N·m/kg)에서 사실상 최강 — off-the-shelf로 이기기 어렵다.** 동급 Φ98 후보들은 토크가 더 낮거나(DM-J8009 40, AK10-9 48) 2-3배 비싸다($385-699). 더 큰 토크는 AK80-64(120/64:1, 저속) 또는 RMD-X10 P35(100/35:1)뿐이며 둘 다 고감속·고가 → pitch 속도/단가에 부적합. **RS03은 유지하고 링크 감속으로 fix가 정답.**

> 검증 원문층: [[raw/ankle-qdd-uptorque-survey]]. 관련 [[36_all_actuator_tn_envelopes]] · [[38_parallel_ankle_sim2real]] · [[37_ankle_linkage_fidelity]] · [[21_motor_power_weight]] · [[raw/robstride-datasheet]].

---

## 0. 기준선 (우리 발목)

| 우리 모터 | 역할 | peak/cont N·m | 무게 | 프레임 | 감속 | 가격 |
|---|---|---|---|---|---|---|
| [RS00](https://www.seeedstudio.com/Robostride-00-Actuator-p-6664.html) | ankle_roll **직결·포화**(100%peak, RMS 114%cont = 바인딩) | 14 / 5 | 310 g | Φ57×51 | 10:1 | $125 |
| [RS03](https://www.seeedstudio.com/Robostride-03-Actuator-p-6774.html) | ankle_pitch **링크·포화**(링크감속으로 fix) | 60 / 20 | 880 g | Φ106×56 | 9:1 | $225 |

## 1. ROLL급 후보 (목표 25-30 N·m, 300-450g, Φ60-70)

| 모델 | peak/cont N·m | 무게 | 프레임 | 감속 | 가격 | RS00 대비 |
|---|---|---|---|---|---|---|
| ★ [DAMIAO DM-J4340-2EC](https://aifitlab.com/products/damiao-dm-j4340-2ec-servo-motor) | **27 / 9** | **362 g** | **Φ57** | 40:1 | **$155** | **peak 1.9× / +52g / +$30 — 드롭인 승** |
| [CubeMars AK70-10](https://www.cubemars.com/product/ak70-10-kv100-robotic-actuator.html) | 24.8 / 8.3 | 610 g | Φ70 | 10:1 | ~$300급 | peak 1.8×지만 **무게 2×**(610g 초과) |
| [CubeMars AK80-8](https://www.cubemars.com/goods-1151-AK80-8.html) | 25 / 10 | 570 g | Φ80 | 8:1 | — | peak 1.8×, cont 2×지만 무게·Φ 초과 |
| [CubeMars AK80-9](https://www.cubemars.com/goods.php?id=982) | 18 / 9 | 485 g | Φ80 | 9:1 | — | peak 1.3×만, 무게 1.6× |
| [MyActuator RMD-X8](https://www.robotshop.com/products/myactuator-rmd-x8pro-v3-can-bus-16-helical-mc-x-500-o-brushless-servo-driver) (1:6) | 20 / ~ | ~710 g(X8Pro P9-25) | Φ80급 | 6:1 | ~$300 | 무게 2.3×, 토크 이득 작음 |
| [RobStride RS01/RS02](https://robstride.com/products/robStride02) | 17 / 6 | 380-405 g | Φ78.5 | 7.75:1 | ~$160(RS02) | 같은 brand 상향, peak 1.2×만 |

> [!success] ROLL 결론
> **DM-J4340가 유일하게 "비슷한 외형 + 25-30 N·m"를 단품으로 충족.** RS00과 같은 Φ57, +52g(362 vs 310), peak 14→**27 N·m(1.9×)**, cont 5→9(1.8×). 40:1 감속이라 **속도는 낮다**(48V 무부하 ~100rpm). roll은 ROM 작고 저속이라 OK일 가능성 높으나, **roll 속도요구(보행 중 roll rate)를 sim 로그로 반드시 교차확인**(노트36 T-N envelope에 추가). $155로 RS00($125)보다 +$30 — 비용-효익 압도적. AK70-10/AK80-8은 토크는 닿지만 무게·직경이 목표 밖(610-570g).

## 2. PITCH/MID급 후보 (목표 50-100 N·m, 700-1100g, Φ90-110)

| 모델 | peak/cont N·m | 무게 | 프레임 | 감속 | 가격 | RS03(60/880/$225) 대비 |
|---|---|---|---|---|---|---|
| [DAMIAO DM-J8009-2EC](https://www.dronegearup.com/products/damiao-dm-j8009-2ec-24-v-20-n-m-9-1-98-mm-od-dual-encoder-integrated-robot-motor-with-can-1-mbps/) | 40 / 20 | (Φ98 OD) | Φ98 | 9:1 | $385 | **토크 ↓**(40<60), **가격 ↑** — 패배 |
| [DAMIAO DM-J10010-2EC](https://aifitlab.com/collections/damiao) | ~확인필요 | ~ | Φ~100 | 10:1 | $357 | 토크 미확정, 가격 ↑ |
| [CubeMars AK10-9 V2](https://www.cubemars.com/product/ak10-9-v2-0-kv60-robotic-actuator.html) | 48 / 18 | 960 g | Φ98×61.7 | 9:1 | **$698.90** | 토크 ↓·무게 ↑·**가격 3×** — 패배 |
| [CubeMars AK80-64](https://www.cubemars.com/goods-1143-AK80-64.html) | **120 / 48** | 850 g | Φ80 | **64:1**(저속) | ~$400-500급 | 토크 2×·더 가볍지만 **64:1 저속**(발목 pitch rate 부적합 가능) |
| [MyActuator RMD-X10-40](https://aifitlab.com/products/myactuator-rmd-x10-40-motor) | 40 / 15 | 1150 g | Φ~100 | 7:1 | **$625** | 토크 ↓·무게 ↑·가격 ↑ — 패배 |
| [MyActuator RMD-X10 P35-100](https://www.robotshop.com/products/myactuator-rmd-x10-s2-v3-bldc-can-bus-135mc-x-500-o-brushless-servo-driver) | **100** / ~ | ~1.3kg | Φ~135 | 35:1(저속) | ~$600+ | 토크 ↑지만 고감속·무겁·고가·Φ초과 |

> [!warning] PITCH/MID 결론
> **RS03은 "60 N·m / 880g / $225 / 66.67 N.m/kg"로 이 클래스의 가격·토크밀도 챔피언.** 동급 직경(Φ98-106)·동급 감속(7-9:1) 후보는 전부 **토크가 같거나 낮으면서 1.7-3배 비싸다**(DM-J8009 40N·m/$385, AK10-9 48N·m/$699, RMD-X10-40 40N·m/$625). 60 N·m를 **초과**하려면 고감속(AK80-64 64:1, RMD-X10 35:1)으로 가야 하는데 — peak 속도가 발목 pitch에 부족하고 무게·가격도 불리. **즉 RS03을 바꿀 이유가 없다.** 사용자 계획(링크 감속으로 pitch 포화 fix)이 정답: 같은 RS03에 링크비를 더해 관절 토크를 늘리는 것이 신규 모터 구매보다 싸고 가볍다.

## 3. 종합 권고

1. **roll = RS00 → DAMIAO DM-J4340 교체** ($155, +52g, peak 1.9×). 디커플드 roll-직결 설계 그대로. 단, **40:1 저속**이 보행 roll-rate를 커버하는지 sim 속도로그로 검증 후 확정([[36_all_actuator_tn_envelopes]] T-N에 4340 봉투 추가).
2. **pitch = RS03 유지 + 링크 감속** 으로 포화 fix (신규 모터 불필요 — 시장에 RS03 가성비를 이기는 동급 단품 없음).
3. 차순위 roll 대안: 무게 여유 있으면 AK80-8(25/10 N·m, 570g) — cont 토크가 4340(9)보다 약간 높음(10). 단 Φ80·570g로 프레임 초과.

> [!info] 미해결 / 후속
> - DM-J10010 정확한 peak 토크·무게 확인(가격 $357만 확보).
> - DM-J4340 48V T-N 곡선 입수해 roll 속도요구 대조(현재 무부하 ~100rpm만).
> - CubeMars/MyActuator 공식 단가 미표기 → 리셀러 추정치(검증 시 갱신).

---

## 4. ★ RS00 under-spec 판정 (gait artifact vs HW floor, 2026-06-22, 검증)

> [!question] 검증 질문
> ankle_roll RS00(14 N·m peak / ~5 N·m cont, 직결 QDD)이 ~51.8kg 바이페드 inversion/eversion에 **진짜 under-spec인가**(모터 키워야), 아니면 **gait artifact**(sim서 고칠 수 있나)? gaitfix v3/v4 후에도 peak 100%·RMS 100-114% 포화 지속.

### (1) First-principles 발목-roll 토크 밴드 (BW=508N, 단지지)
| 시나리오 | lateral CoP arm | ankle_roll τ | 비고 |
|---|---|---|---|
| 정상 보행 (flat-foot, CoP 발중앙 근처) | ~1-2cm | **5-10 N·m** | 생체역학 frontal-plane와 정합 |
| 적극 측방균형 / 외란 | ~3cm | **15 N·m** | RS00 peak(14) 막 초과 |
| 발 가장자리(edge) 단지지 | ~4-5cm | **20-25 N·m** | 최악, RS00 1.5-1.8× 초과 |

- **생체역학 교차검증**(3개 독립 추정 수렴):
  1. 인간 발목 **inversion peak ≈ 0.10 N·m/kg** → 51.8kg → **~5.2 N·m**(정상보행 frontal-plane 명령). [PMC10434928 exoskeleton]
  2. inversion peak ≈ **plantarflexion peak의 13%** → 인간 PF ~1.5 N·m/kg×51.8=77.7 → **~10 N·m**; 우리 pitch cap 60의 13%=**7.8 N·m**. [PMC3791398]
  3. 기하: 508N × (1-2cm flat / 4-5cm edge) = **5-10 / 20-25 N·m**.
- → **정상 보행 요구 ~5-10 N·m, 측방외란/edge 시 15-25 N·m.** RS00 14 peak는 **정상엔 충분, 균형/edge엔 부족**.

### (2) 동급 휴머노이드 발목-roll 토크 (peer)
| 로봇 | 질량 | ankle 메커니즘 | ankle roll 유효 peak τ | 근거 |
|---|---|---|---|---|
| **우리** | 51.8kg | RS00 **직결** | **14 N·m** | MJCF frcrange ±14 |
| Unitree G1 | ~35kg | **2모터 병렬**(PR↔AB) | ankle "50 N·m" 2모터가 **pitch+roll 공유** → roll축에 차동분배 (단일직결보다 ↑) | docs.quadruped.de / G1 datasheet |
| Booster T1 | ~30kg | **2모터 병렬** | joint motor max 130(knee), ankle 2모터 공유 | docs.bipedal.de (roll ±25°) |
| Agibot X2-N | 28kg | roll 액추에이터 + pitch 4절(근위) | **R57 = 30 N·m peak**(40:1, 370g) | arxiv 2604.21541 Table I |
| Berkeley Humanoid | 16kg | 직렬 직결 | 최소 액추에이터 5013 = **9.7 N·m peak / 4.6 cont** | arxiv 2407.21781 |
| DecARt Leg | ~35kg | **2-DoF ankle 전부 근위재배치**(multi-bar) | 수치 미공개, 링크로 유효토크↑ | arxiv 2511.10021 |

- ★ **패턴**: 우리보다 가벼운 G1(35)·T1(30)·X2(28)가 **roll축에 14 N·m보다 큰 유효토크**를 확보 — 대부분 (a) **2모터 병렬**(토크를 양축에 공유 → roll축 유효↑) 또는 (b) **링크 감속/재배치**(distal 관성↓ + 유효토크↑)로. **단일 직결 14 N·m을 51.8kg(피어 대비 1.5-1.8× 무거움)에 쓰는 건 클래스 최하단.** Berkeley(16kg)의 9.7조차 **질량당으론 우리보다 높음**(9.7/16=0.61 vs 14/51.8=0.27 N·m/kg).
- 질량당 발목-roll 토크: **우리 0.27 N·m/kg = 피어 중 최저**. X2-N R57 = 30/28 = **1.07**, Berkeley 9.7/16=0.61, G1 roll 유효(추정 25+)/35 ≈ 0.7+.

### (3) 판정 = ★ HW floor (gait artifact 아님), UPSIZE가 정답
- gaitfix v3(joint penalty)·v4(stance widen+foot-body reward) 모두 peak 100% 유지 = **sim 보상으로 안 내려감** → **gait artifact 아니라 물리 하한**. widen은 RMS만 6.3→5.0(20%↓), peak·edge 불변 = **측방균형 peak 수요가 RS00을 진짜 saturate**.
- first-principle 정상요구(5-10) vs RS00 cont(5): **RMS가 연속정격에 상시 100% = 열적으로도 under-spec**(직결 QDD는 방열 약함). peak 14 = 정상엔 OK지만 **외란/edge 마진 0** → 강건 보행 불가.
- **권고(우선순위)**:
  1. ★ **모터 업사이즈 = DAMIAO DM-J4340 (27/9 N·m, 362g, Φ57, $155)** — RS00과 거의 동형, peak 1.9×·cont 1.8×, 디커플 roll-직결 드롭인. first-principle edge 최악(25)을 peak 27로 **커버**, 정상요구(5-10)는 cont 9 내. **단 40:1 저속 → boot roll-rate sim 로그로 교차검증 필수**([[36_all_actuator_tn_envelopes]] 봉투).
  2. **차선 = 2-RSU 병렬발목**(G1/T1식) — roll축에 2모터 차동분배로 유효토크 ~2배, 단 운동학 2×2·특이점·sim2real 복잡([[38_parallel_ankle_sim2real]]).
  3. **차선 = roll 링크화**(X2식 재배치+감속) — distal 관성↓ + 무료 감속, 단 직결 단순성 상실([[37_ankle_linkage_fidelity]] §roll 감속 N1.5→21·N2→28, T-N 위반 0%).
- **gait 측에서 추가로 짜낼 여지(보조, peak는 못 내림)**: stance 추가 widen·CoP를 발중앙 유지 보상·toe push-off로 측방수요 일부 분산 — 단 v3/v4 증거상 **peak 100% 못 깸** → HW가 근본해결.

> [!success] 한 줄
> RS00 14/5는 51.8kg 발목-roll에 **under-spec = HW floor**(gait artifact 아님 — v3/v4가 증명). 정상요구 5-10 N·m엔 닿으나 **외란/edge 15-25 N·m·열(RMS=cont 100%)에 마진 0**, 질량당 토크 0.27 = 피어(X2 1.07/Berkeley 0.61) 최하. **DM-J4340(27/9, $155 드롭인) 업사이즈가 최단**; 또는 2-RSU 병렬/roll 링크화. 피어가 가벼운데도 더 큰 roll 토크를 쓰는 이유 = 측방균형은 단일직결로 빠듯하기 때문.

> [!info] 출처 (URL)
> - 인간 ankle inversion/eversion ~0.10 N·m/kg·plantarflex의 13%: https://pmc.ncbi.nlm.nih.gov/articles/PMC10434928/ · https://pmc.ncbi.nlm.nih.gov/articles/PMC3791398/
> - Unitree G1 발목 2모터 병렬·50 N·m: https://www.docs.quadruped.de/projects/g1/html/g1_overview.html · https://www.roscomponents.com/wp-content/uploads/2024/11/G1-UNITREE-DATASHEET.pdf
> - Booster T1 발목 ROM/병렬: http://www.docs.bipedal.de/projects/t1/html/overview.html
> - Agibot X2-N 액추에이터표(R57 30 N·m): https://arxiv.org/html/2604.21541v1
> - Berkeley Humanoid 액추에이터(5013 9.7/4.6): https://arxiv.org/pdf/2407.21781
> - DecARt Leg 발목 근위재배치(multi-bar): https://arxiv.org/html/2511.10021v1
> - 발목 설계 최적화 프레임워크(병렬 토크분배): https://arxiv.org/html/2509.16469v1
> - DM-J4340 27/9 N·m: https://aifitlab.com/products/damiao-dm-j4340-2ec-servo-motor
