# legonly_ab_v2 — LegOnly 12-DOF 본학습, side-aware 설정 수정판 (2026-09-03~) 〔진행 중〕

> *한 줄*: [[2026-09-03_legonly_ab_v1]](iter 5.7k 보수적 중단 — v30 미러축 vs 단일 default/clip로
> **L_knee 액션창 0°**)의 재발사. **유일 변인 = 설정 side-aware 수정**(모델 XML·리워드·레시피
> 전부 v1과 동일). 근본원인·수정 상세: [[../reward_research/2026-09-03_stiff_knee_root_cause]],
> 스모크: [[2026-09-03_legonly_ab_sideaware_smoke]].

| | |
|---|---|
| 로봇 | v1과 동일: `LegOnly_prototype-tempmass-motormeasured-armfix_v30_proxyfix_loop.xml` (23.630 kg, AB 폐루프) — **XML 무변경** |
| 질량 DR | v1과 동일: `mass_dr_legonly_fastener50_prototype-tempmass.json` |
| 스택 | v1과 동일(v2s1 상속): INIT_MID·KNEE_EXT 2.0@25°·SOFT_LANDING_MODE=half + vy 스테이지 + 게이트 커리큘럼 + critic DR 82ch + P2 entropy 어닐링 |
| **변인 (vs v1)** | ① default pose·action clip을 관절 range에서 부호 자동유도(`signed_pose`/`safe_target_clip`) — L_knee 창 0°→108°, R_hip_pitch 43°→130.5° ② bent 키프레임 폐루프 각 재표현(`_reexpress_loop_pose`) — 리셋 closure 37.27→0.001 mm ③ 프리플라이트 게이트 신설(`analysis/preflight_action_window.py`, 발사 전 자동) |
| 수정 검증 | 구모델 v3/v4 byte-identical(Δdefault 0.0, Δclip 4.7 µrad 단위환산 왕복, `--legacy-equivalence` 상시 회귀체크) · 스모크 399 iter 완주(낙상 0, 크래시 0) · L_knee qtarget 진폭 0→27~33° |
| env | 16384 (v1과 동일) |
| 계보 | 커밋: mjlab `546a7ed5`(픽스+게이트)·`81ea1255`(선행 launch 작업 분리), parent `b3bfd81` |

## §1a 실행 명령

```bash
bash analysis/run_v2_scratch.sh \
  --run legonly_ab_v2 --ankle AB --vy-stages \
  --env PYG_MODEL_TAG=LegOnly_prototype-tempmass-motormeasured-armfix_v30_proxyfix \
  --env PYG_MASS_DR_JSON=/home/syaro/MikuchanRemote/Human-Pygmalion/tools/robot_model/fusion_snapshots/v30_inspection/mass_dr_legonly_fastener50_prototype-tempmass.json
```

권위 원장: `analysis/out/v2_scratch_legonly_ab_v2.json`. wandb entity 미지정(v1의 `dongyub39-snu`
404 이슈 회피, docs/118 §2-G).

## §1c 완주 게이트에 추가된 판정 항목 (v1 교훈)

1. **운동학 재측정**(`gait_kinematics_probe.py`, 0.6/1.2 m/s): 무릎 swing 피크 — 인간 55~65°
   대비 얼마나 회복되는가. 여전히 ≪ 인간이면 리워드 근본원인 #2(swing knee driver 부재,
   연구노트 §1)로 진행 → Booster T1식 knee-height 항 +800 iter warm-start A/B(번들 금지).
2. R_knee 클립 포화율(스모크서 92.7%) 추이 — #2의 선행 지표.
3. toe-off 시그니처(이지 시 발피치·힐라이즈 좌우대칭) 재측정.

## §1d vel-0 정지 자세 스냅샷 (사용자 질문 09-03 14:05, model_700 = P1 ~1 h)

**설계 기본자세(init/default, 정책 액션 0의 기준)** — env.yaml init_state, side-aware 픽스 후:
hip_pitch L −10.03 / R +10.03° (양쪽 물리 굴곡 10°) · knee L +20.05 / R −20.05° (굴곡 20°) ·
crank A/B −17.1° · ankle_pitch +20.6° · ankle_roll +0.15° · hip_roll/yaw 0. 기하: 대퇴 전경 +3.1°,
하퇴 −13.5°(무릎이 발목보다 앞), 발바닥 최저점 = base 아래 0.907 m.
⚠ **키프레임 발바닥이 수평 대비 10.6° 기울어짐**(ankle_pitch +20.6°는 v3 시대 serial bent 값
0.36 rad을 그대로 재표현한 것 — v30 발 프레임에 맞지 않을 가능성). 리셋 직후 접촉 settle로
교정되고 정책 정지자세의 ankle_pitch는 +2/−7°라 학습엔 영향 경미하나, **키프레임 ankle 값의
v30 재산출은 백로그**.

**정책 정지 자세(model_700, vel 0 명령, 10 s 롤아웃 중 t≥4 s, 런과 동일 PYG_* 환경, 모델 23.630 kg 확인)**:
base z **0.903 m**(std 0), base vx −0.001±0.000 m/s — 완전 정지.

| 관절 | L [deg] | R [deg] | 물리 해석 |
|---|---|---|---|
| hip_pitch | −3.75 | +11.66 | 굴곡 L 3.8° / R 11.7° (비대칭) |
| hip_roll | +4.30 | +8.19 | 같은 방향 기울기(골반 측방 이동) |
| hip_yaw | −20.02 | −26.14 | **양발이 같은 방향으로 20~26° 회전 = 비틀린 정지자세**(미성숙 정책 아티팩트, 토크 0.5~1.2 N·m로 공짜) — P1 게이트 감시항목 |
| knee | +5.81 | −5.88 | 굴곡 5.8° 양쪽 **대칭** (창 열림 확인) |
| crank A / B | −0.5 / −4.0 | +4.0 / −7.7 | |
| ankle_pitch | +2.02 | −7.03 | 키프레임 +20.6°와 크게 다름(위 ⚠ 참조) |
| ankle_roll | −3.13 | +2.60 | |

토크(|τ| 평균, N·m): hip_pitch 4.6/4.6 · hip_roll 4.1/10.3 · knee 0.7/0.4 · crank ≤0.8. 원자료
`analysis/out/legonly_ab_v2_vel0_vx0.npz`. 게이트마다 재측정해 hip_yaw 비틀림 해소 여부 추적.

## §2 이하 — 완주 후 측정으로 채운다 (fc/fcp + 200Hz 프로브 + §7 모터활용)

## §2c 학습 중 리뷰 (게이트마다 스냅샷, docs/27 체크리스트)

| 시각 | iter | reward | ep_len | noise σ | value loss | entropy | surrogate / LR | fell / low_base | err_vel xy / yaw | dr_factor / vx_max | thermal | 판정(docs/27) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 09-03 14:26 | 685 | 110.5 (50avg 109.7) | 1000 | 0.183 | 0.0239 | -7.46 | -0.0016 / 1.2e-04 | 0.000 / 0.000 | 0.461 / 0.477 | 0.00 / 0.8 | 1.31 | (자동 스냅샷, 판정은 게이트 리뷰에서) |

## §R 참조
[[2026-09-03_legonly_ab_v1]] · [[2026-09-03_legonly_ab_sideaware_smoke]] ·
[[../reward_research/2026-09-03_stiff_knee_root_cause]] · [[117_model_finalization_and_oneleg_training_plan]]
