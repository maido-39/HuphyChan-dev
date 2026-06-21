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
