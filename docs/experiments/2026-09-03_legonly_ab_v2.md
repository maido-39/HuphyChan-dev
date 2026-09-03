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

## §2 이하 — 완주 후 측정으로 채운다 (fc/fcp + 200Hz 프로브 + §7 모터활용)

## §2c 학습 중 리뷰 (게이트마다 스냅샷, docs/27 체크리스트)

| 시각 | iter | reward | ep_len | noise σ | value loss | entropy | surrogate / LR | fell / low_base | err_vel xy / yaw | dr_factor / vx_max | thermal | 판정(docs/27) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

## §R 참조
[[2026-09-03_legonly_ab_v1]] · [[2026-09-03_legonly_ab_sideaware_smoke]] ·
[[../reward_research/2026-09-03_stiff_knee_root_cause]] · [[117_model_finalization_and_oneleg_training_plan]]
