# 48 · 전-실험 모터 토크 이용률 — 최대토크영역 사용량 + ankle_roll 모터선정

> measure npz의 관절토크(L+R)를 RobStride **rated(연속/열)·peak(순간)**([[28_reward_actuator_fidelity]])와 대조. `scripts/motor_util_cross.py`. CSV: `logs/measure/motor_util_cross.csv`. ★ NOMINAL(DR off).

**핵심 지표**: `RMS%rated`=열/연속 binding(>100%=과열) · `peak%peak`=순간포화(=100%면 effort_limit clip에 붙음=더 원함) · `sat%`=peak에 붙어있는 시간비.


## A. ankle_roll (RS00: rated 5 / peak 14 N·m) — 전 실험

| 실험 | peak | sat% | RMS | **RMS%rated** | peak%peak |
|---|--:|--:|--:|--:|--:|
| g1vanilla | 14.0 | 42 | 10.0 | **200%** ⚠ | 100% |
| fwd_stage1_toe | 14.0 | 48 | 9.9 | **199%** ⚠ | 100% |
| v3_clipped | 14.0 | 46 | 9.8 | **197%** ⚠ | 100% |
| flat_trained_v1 | 14.0 | 43 | 9.5 | **191%** ⚠ | 100% |
| v3_unclipped | 14.0 | 42 | 9.5 | **190%** ⚠ | 100% |
| g1van_full | 14.0 | 9 | 8.5 | **169%** ⚠ | 100% |
| g1van_flat | 14.0 | 19 | 8.3 | **167%** ⚠ | 100% |
| stage4_clip | 14.0 | 18 | 7.3 | **147%** ⚠ | 100% |
| stage4_unclip | 14.0 | 16 | 7.2 | **144%** ⚠ | 100% |
| synthetic_test | 11.2 | 0 | 7.1 | **142%** ⚠ | 80% |
| stage3_clip | 14.0 | 13 | 7.0 | **140%** ⚠ | 100% |
| stage3_unclip | 14.0 | 13 | 6.9 | **138%** ⚠ | 100% |
| sweep_g2p5 | 14.0 | 13 | 6.8 | **135%** ⚠ | 100% |
| sweep_g1p0 | 14.0 | 11 | 6.3 | **126%** | 100% |
| g1_rigidtoe2 | 14.0 | 5 | 5.9 | **119%** | 100% |
| sweep_g1p5 | 14.0 | 8 | 5.9 | **117%** | 100% |
| pushoff3 | 14.0 | 8 | 5.8 | **116%** | 100% |
| sweep_g2p0 | 14.0 | 5 | 5.7 | **114%** | 100% |
| gaitfix_v7 | 14.0 | 6 | 5.6 | **113%** | 100% |
| gaitfix_v3 | 14.0 | 4 | 5.5 | **110%** | 100% |
| gaitfix_v5 | 14.0 | 1 | 5.3 | **107%** | 100% |
| forefoot_unclip | 14.0 | 6 | 5.3 | **106%** | 100% |
| forefoot_clip | 14.0 | 5 | 5.3 | **105%** | 100% |
| gaitfix_v6 | 14.0 | 3 | 5.2 | **105%** | 100% |
| gaitfix_v4 | 14.0 | 3 | 5.0 | **101%** | 100% |

## B. 전 모터 RMS%rated (대표 실험) — ankle_roll만 과부하

| 실험 | hip_pitch | hip_roll | hip_yaw | knee | ankle_pitch | ankle_roll |
|---|--:|--:|--:|--:|--:|--:|
| flat_trained_v1 | 43 | **102** | 40 | 73 | **135** | **191** |
| g1van_full | 82 | 61 | 39 | 91 | **207** | **169** |
| g1vanilla | 80 | 75 | 48 | 67 | **190** | **200** |
| gaitfix_v7 | 36 | 61 | 43 | 76 | **146** | **113** |
| stage4_clip | 64 | 78 | 33 | **183** | 58 | **147** |
| stage4_unclip | 56 | 80 | 35 | **179** | 53 | **144** |

(굵게 = RMS가 연속정격 초과 = 그 듀티서 과열. ankle_roll만 만성 초과; 나머지는 여유.)

