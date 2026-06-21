# 발목 QDD 상향-토크 시장조사 — 원자료 (검증)

> 워크플로우 ankle-qdd-uptorque-survey (2026-06-22). 발목 ROLL(RS00급) + PITCH/MID(RS03급) 저가 상용 QDD 대체후보. wiki: [[39_ankle_qdd_uptorque_survey]] · [[36_all_actuator_tn_envelopes]] · [[38_parallel_ankle_sim2real]].

## 기준 (우리 발목, 검증 [[raw/robstride-datasheet]])

| 우리 모터 | 역할 | peak/cont (N·m) | 무게 | 프레임 | 감속 | 가격 |
|---|---|---|---|---|---|---|
| RobStride RS00 | ankle_roll (직결, **포화** 100%peak·RMS 114%cont) | 14 / 5 | 310 g | Φ57×51 | 10:1 | $125 (Seeed; $119 ×10) |
| RobStride RS03 | ankle_pitch (링크, 포화·링크감속으로 fix가능) | 60 / 20 | 880 g | Φ106×56 | 9:1 | $225 (Seeed; $214 ×10) |

- 목표 roll: ~25-30 N·m peak를 ~300-450g, Φ60-70 프레임에. 디커플드 roll-직결 유지.
- 목표 mid: 50-100 N·m peak를 700-1100g, Φ90-110.

## ROLL급 후보 (소형 ~Φ57-70, ~300-700g)

| 모델 | peak/cont N·m | 무게 | 프레임 | 감속 | 가격 | 출처 |
|---|---|---|---|---|---|---|
| **DAMIAO DM-J4340-2EC** | **27 / 9** | **362 g** | **Φ57** | 40:1 | **$155**(24/48V) | aifitlab |
| DAMIAO DM-J4310-2EC | ~7 rated | ~ | Φ~ | ~10:1 | ~$130 | foxtech |
| CubeMars AK70-10 | 24.8 / 8.3 | 610 g | Φ70 | 10:1 | — | cubemars |
| CubeMars AK80-8 | 25 / 10 | 570 g | Φ80 | 8:1 | — | cubemars |
| CubeMars AK80-9 | 18 / 9 | 485 g | Φ80 | 9:1 | — | cubemars |
| MyActuator RMD-X8 (1:6) | 20 peak | ~710 g (X8Pro P9-25=710g) | Φ80급 | 6:1 | ~$300급 | myactuator/robotshop |
| RobStride RS01/RS02 | 17 / 6 | 380-405 g | Φ78.5 | 7.75:1 | ~$160(RS02) | robstride |

### verbatim
- DM-J4340-2EC: "27N.M peak (24V/48V), 9N.M rated, 362g, 57mm OD, 40:1, 14Bit dual enc, CAN 1Mbps, from $155" — aifitlab.com/products/damiao-dm-j4340-2ec-servo-motor
- AK70-10: "peak torque 24.8Nm @ 23.2A peak, 310 RPM, 610g, 10:1, rated 8.3Nm" — cubemars.com/product/ak70-10-kv100-robotic-actuator.html
- AK80-8: "0.570kg, 10/25Nm rated/peak, 8:1" — cubemars.com/goods-1151-AK80-8.html
- RS00: "$125 ($119 ×10), 14N.m peak, 310g, 10:1" — seeedstudio.com/Robostride-00-Actuator-p-6664.html

## PITCH/MID급 후보 (Φ90-110, ~700-1150g, 50-100 N·m)

| 모델 | peak/cont N·m | 무게 | 프레임 | 감속 | 가격 | 출처 |
|---|---|---|---|---|---|---|
| **RobStride RS03 (기준)** | **60 / 20** | **880 g** | **Φ106** | 9:1 | **$225** | seeed |
| DAMIAO DM-J8009-2EC | 40 / 20 | ~ (Φ98 OD) | Φ98 | 9:1 | $385 | dronegearup/aifitlab |
| DAMIAO DM-J8009P-2EC | 40 / 20 | ~ | Φ~ | 9:1 | $398 | foxtech/openelab |
| DAMIAO DM-J10010-2EC | ~ (확인필요) | ~ | Φ~100 | 10:1 | $357 | aifitlab |
| CubeMars AK10-9 V2 | 48 / 18 | 960 g | Φ98×61.7 | 9:1 | $698.90 | cubemars |
| CubeMars AK80-64 | 120 / 48 | 850 g | Φ80 | 64:1 (저속) | — (DigiKey/RobotShop 재고) | cubemars |
| MyActuator RMD-X10-40 (P7) | 40 / 15 | 1150 g | Φ~100 | 7:1 | $625 | aifitlab |
| MyActuator RMD-X10 (P35-100) | 100 peak | ~1.3kg급 | Φ~135 | 35:1 (저속) | ~$600+ | robotshop/myactuator |

### verbatim
- RS03: "$225 ($214 ×10), 60N.m peak, 880g, 9:1, 66.67 N.m/kg" — seeedstudio.com/Robostride-03-Actuator-p-6774.html
- DM-J8009: "24V nominal, 20A nom/50A peak, 20Nm nom/40Nm peak, 100rpm@24V/200@48V, $385" — dronegearup.com / aifitlab
- AK10-9 V2: "48Nm peak, 18Nm rated, 960g, Φ98×61.7mm, 9:1, ~50 Nm/kg, $698.90" — cubemars.com/product/ak10-9-v2-0-kv60-robotic-actuator.html
- AK80-64: "0.85kg, 48/120Nm rated/peak, 64:1" — cubemars.com/goods-1143-AK80-64.html
- RMD-X10-40: "40Nm peak, 15Nm rated, 1.15kg, 7:1, $625" — aifitlab.com/products/myactuator-rmd-x10-40-motor
- RMD-X10 P35-100: "35:1, 100N·m peak" — robotshop.com/products/myactuator-rmd-x10-s2-v3...

## 충돌/불확실
- DM-J10010 토크 미확정(가격 $357만). 8009과 동급(40-50 peak)일 가능성, 확인 필요.
- RMD-X8/X10 무게는 변형·드라이버 유무로 편차. X8Pro(P9-25)=710g 확정.
- AK80-64는 64:1 저속(120 N·m이나 무릎/엉덩이용; 발목 pitch 속도엔 부적합 가능).
- AK 시리즈 단가는 cubemars 공식페이지 직접 미표기 → 리셀러($400-700급) 추정.
