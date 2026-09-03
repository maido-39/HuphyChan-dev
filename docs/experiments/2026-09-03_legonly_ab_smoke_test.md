# LegOnly(12-DOF, 상체 없음) AB 오케스트레이션 스모크 (2026-09-03)

> **한 줄 판정:** LegOnly(상체 완전 제거, waist-yaw 액추에이터 질량만 유지) 모델이 처음으로
> `run_v2_scratch.py` 학습 오케스트레이션(P1 게이트 커리큘럼 → P2 DR 램프, 45D student/critic
> 관측, checkpoint resume)을 완주하는지 확인하는 인프라 시험이다. **보행 성능을 판정하는 런이
> 아니다.**

| 항목 | 값 |
|---|---|
| 상태 | ✅ **완주 — 인프라 PASS**, 보행 성능 판정 대상 아님 (P1 iter 200 settled, P2 iter 399 DONE, 06:35 소요) |
| 서술형 정책명 | `flat-2.5max progress-reward staged-domain-rand 12dof-legonly-smoke (2026-09-03)` |
| 로봇 | `LegOnly_prototype-tempmass-motormeasured-armfix_v30_proxyfix_loop.xml` |
| 모델 질량 | 23.630 kg (nbody=22, njnt=25 — 12관절×2측 hip_pitch/roll/yaw+knee+crank_A/B, ankle_pitch/roll은 폐루프 패시브) |
| 모델 SHA-256 | `41686d954d63b5ab28607563cb301501d206c1e57673109040afb758142bff2` |
| 질량 DR | `tools/robot_model/fusion_snapshots/v30_inspection/mass_dr_legonly_prototype-tempmass.json` (신규, round4 corrected-body DR에서 torso/shoulder_pitch_link/arm 항목만 제외한 leg+pelvis 서브셋) |
| 질량 DR SHA-256 | `c9e9cdb6686124ac454d8e3e8fd2f768094263721deb2e7961cc0f6519583275` |
| 배경 | [[117_model_finalization_and_oneleg_training_plan]] §5, 레시피 계보 [[2026-08-28_v2s1_AB]](`v2s1` — 확정 landing recipe + v4 질량 + vy stages + gated curriculum + critic DR 82ch, 2026-08-28 완주) |

## §1 재현 조건

### §1a 실행 명령

```bash
bash analysis/run_v2_scratch.sh --smoke \
  --run legonly_ab_smoke_test \
  --ankle AB --logger tensorboard \
  --env PYG_MODEL_TAG=LegOnly_prototype-tempmass-motormeasured-armfix_v30_proxyfix \
  --env PYG_MASS_DR_JSON=/home/syaro/MikuchanRemote/Human-Pygmalion/tools/robot_model/fusion_snapshots/v30_inspection/mass_dr_legonly_prototype-tempmass.json
```

`--dry-run`으로 사전 검증(env/명령 렌더 확인) 완료. 정확한 인자·P1/P2 환경 변수·승급 기록은
`analysis/out/v2_scratch_legonly_ab_smoke_test.json`이 권위 원장이다.

### §1b Policy 입력·출력 (v2s1 레시피 상속)

- **Actor(Student), 45D:** IMU 각속도 3 + projected gravity 3 + 모터 위치 $q(t-1),q(t)$ 24 +
  이전 action 12 + 명령 $(v_x,v_y,\dot\psi)$ 3.
- **Critic, DR-obs 포함 확장폭:** privileged true-state + `PYG_CRITIC_DR_OBS=1`의
  `dr_friction/dr_mass/dr_com/dr_push/dr_factor` 채널. `dr_mass`/`dr_com`는
  `SceneEntityCfg("robot")` 전신 스캔이라 바디 수(22)에 자동 적응 — LegOnly 전용 코드 변경 불필요.
- **Action, 12D:** 좌/우 각 hip pitch/roll/yaw, knee, crank A/B. LegOnly는 상체 바디가 물리적으로
  없으므로 `PYG_UPPER_DOF`(기본 OFF) 분기와 무관하게 처음부터 12-DOF다.

### §1c LegOnly 호환성 사전점검 (코드 변경 없이 확인한 것)

`pygmalion_constants.py`에 LegOnly 전용 훅은 없다 — 범용 `PYG_MODEL_TAG` 오버라이드가
`_ANKLE_LOOP`(AB) 분기에서 `{tag}_loop.xml`을 그대로 선택해 투명하게 동작한다(§0 no code change).
`env_cfgs.py`를 점검해 상체 부재와 충돌할 수 있는 지점을 확인:

1. `std_walking`/`std_running`(pose reward) 의 `waist_yaw`/`shoulder_*` 항목은
   `if os.environ.get("PYG_UPPER_DOF")` 안에서만 추가됨 → 미설정이므로 dict에 12관절만 남는다. 안전.
2. `upright`/`body_ang_vel` reward, `dr_com` obs, `low_base` termination은 전부
   `body_names=("base_link",)` 단일 루트 바디 기준 → LegOnly에도 `base_link`(pelvis) 존재, 안전.
3. **위험 지점(발견·회피)**: `PYG_INERTIAL_DR=1`(base_env 기본 ON)의 pseudo-inertia 이벤트 루프가
   `PYG_MASS_DR_JSON`의 `links`/`mjlab_body_names`를 순회하며 `SceneEntityCfg(body_names=...)`를
   만든다. 원본 round4 DR JSON은 `torso`/`shoulder_pitch_link`/`arm` 항목을 포함하는데, 이 바디들은
   LegOnly 모델에 **존재하지 않아** 바디명 해석이 실패할 것으로 판단 → 위 §질량 DR 표의 leg-only
   서브셋(`mass_dr_legonly_prototype-tempmass.json`, pelvis+6개 다리 링크만)을
   `PYG_MASS_DR_JSON`으로 명시 오버라이드해 회피. P1은 어차피 `p1_env()`가
   `PYG_INERTIAL_DR`을 pop하므로 무관, P2(스모크의 짧은 DR 램프+digest 구간)에서만 실사용.
4. `dr_levels` 커리큘럼의 `inertial_max`는 같은 루프에서 파생되므로 별도 수정 불필요.

## §2 결과

`analysis/out/v2_scratch_legonly_ab_smoke_test.json`(권위 원장) + `review_loop.sh` 스냅샷(§2c)
기준. 판정 기준(§2a) 4개 전부 확인:

1. **PASS** — P1이 게이트 top stage(4)에 iter 120에서 도달, iter 154에 settle 조건 만족
   (`err_steady 0.3235` vs baseline `0.4816`, streak 15, dwell 34) → iter 200에서 정상 종료.
   `fell_over`는 전 구간 0.0000~0.0005(스모크 완화한계 1.0 대비 여유 큼). Stage 0→1 승급만
   `forced=true`(MAX-DWELL, iter 60) — 이는 stage 0이 zero-command 워밍업이라 err가 NaN이라
   스모크 전용 강제승급 경로이며, 07-02 idrsmoke_test 노트와 동일한 정상 패턴.
2. **PASS** — P2가 P1 실측 종료 iter(200)에서 `PYG_DR_START_ITER=200`/`PYG_DR_END_ITER=320`을
   계산해 launch, `dr_factor`는 iter 210의 0.096 → 224의 0.213 → 249의 0.421 → 324의 **1.000**으로
   증가, iter 399(digest 종료)까지 1.0 유지.
3. **PASS(핵심)** — LegOnly 전용 leg-only 서브셋 `mass_dr_legonly_prototype-tempmass.json`을
   `PYG_MASS_DR_JSON`으로 넘긴 P2가 크래시 없이 정상 진행(iter 200→399, `PYG_INERTIAL_DR=1`
   pseudo-inertia 이벤트가 pelvis+6개 다리 링크 바디명만 순회 — §1c에서 예측한 torso/shoulder/arm
   바디 부재로 인한 `SceneEntityCfg` 해석 실패는 **발생하지 않음**, 사전 회피가 실제로 유효했음을
   확인).
4. **PASS** — Critic 관측 폭 82D(로그에서 `Linear(in_features=82, ...)` 직접 확인, v2s1과 동일
   구성), Actor/Action 차원 관련 크래시·shape mismatch 전무. P2 `[entropy-anneal]` iter 200
   `entropy_coef=0.01`부터 iter 399 종료까지 정상 어닐링.

**최종 지표(iter 399, P2 phase-end)**: reward 7.1(50avg 6.8) — 스모크 저환경(1024 env, 세션
6.5분) 특성상 절대값은 참고용. `fell_over` 0.000, `error_vel_xy` 0.319, `error_vel_yaw` 0.379,
`thermal_effort_mean` 2.56, `stance_knee_deg` 3.26°(KNEE_EXT 목표 25°엔 스모크 짧은 학습으론
미도달 — 정상, iter 수 자체가 성능 판정용이 아님), `foot_impact_vel_max` 1.27.

**결론**: LegOnly 모델이 v2s1 풀스택 오케스트레이션(게이트 P1→DR 램프 P2, checkpoint full-resume,
critic DR obs, 45D student)과 처음으로 완전히 맞물렸다. 유일하게 새로 필요했던 조치는 leg-only
서브셋 질량-DR JSON(§0 배경 표) 하나였고 코드 변경은 0건. 다음 단계는 §3.

## §3 다음 단계

스모크 PASS 시: (a) 실제 LegOnly 본학습(`legonly_ab_v1` 등, v2s1과 동일 16384 env 풀스택) 준비 —
런처는 동일 명령에서 `--smoke` 제거 + `--run` 변경만 필요, (b) 실패 시 §1c에서 다루지 못한
호환성 문제를 여기 추가 기록.

★**DR JSON 갱신(2026-09-03, 스모크 launch 직후)**: 이 스모크가 쓴
`mass_dr_legonly_prototype-tempmass.json`은 round4(body 귀속만 수정, 나사 완전성 방법론은
기본값 1.0=미적용)에서 파생된 서브셋이다. 이후 `PYG_FASTENER_COMPLETENESS_MIN=0.5`(docs/114 §5)로
재실행해 body 귀속 수정 + 나사 50% 불확실성을 **합친** 권위본
`mass_dr_fastener50_v30proxyfix_corrected.json`을 만들었고, 그 LegOnly 서브셋
`mass_dr_legonly_fastener50_prototype-tempmass.json`도 생성했다(docs/117 §2). **실제 본학습은
이 fastener50 서브셋을 `PYG_MASS_DR_JSON`으로 써야 한다** — 이 스모크는 오케스트레이션
검증(=바디명이 안 깨지는지)이 목적이라 재launch하지 않고 구버전 그대로 둔다.

## §2c 학습 중 리뷰 (게이트마다 스냅샷, docs/27 체크리스트)

![progress](mujoco/assets/legonly_ab_smoke_test_p1_progress.png)

| 시각 | iter | reward | ep_len | noise σ | value loss | entropy | surrogate / LR | fell / low_base | err_vel xy / yaw | dr_factor / vx_max | thermal | 판정(docs/27) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 09-03 02:35 | 216 | 5.4 (50avg 5.2) | 143 | 0.507 | 0.0479 | 8.65 | -0.0058 / 1.7e-04 | 0.000 / 7.167 | 0.201 / 0.399 | 0.00 / 2.5 | 2.51 | P1 phase-end: review before P2 |
| 09-03 02:42 | 399 | 7.1 (50avg 6.8) | 155 | 0.379 | 0.0767 | 4.64 | -0.0065 / 1.3e-04 | 0.000 / 6.208 | 0.319 / 0.379 | 1.00 / 2.5 | 2.56 | P2 phase-end: final smoke/training health review |
| 09-03 03:30 | 399 | 7.1 (50avg 6.8) | 155 | 0.379 | 0.0767 | 4.64 | -0.0065 / 1.3e-04 | 0.000 / 6.208 | 0.319 / 0.379 | 1.00 / 2.5 | 2.56 | (자동 스냅샷, 판정은 게이트 리뷰에서) |
| 09-03 04:30 | 399 | 7.1 (50avg 6.8) | 155 | 0.379 | 0.0767 | 4.64 | -0.0065 / 1.3e-04 | 0.000 / 6.208 | 0.319 / 0.379 | 1.00 / 2.5 | 2.56 | (자동 스냅샷, 판정은 게이트 리뷰에서) |
| 09-03 05:30 | 399 | 7.1 (50avg 6.8) | 155 | 0.379 | 0.0767 | 4.64 | -0.0065 / 1.3e-04 | 0.000 / 6.208 | 0.319 / 0.379 | 1.00 / 2.5 | 2.56 | (자동 스냅샷, 판정은 게이트 리뷰에서) |
| 09-03 06:30 | 399 | 7.1 (50avg 6.8) | 155 | 0.379 | 0.0767 | 4.64 | -0.0065 / 1.3e-04 | 0.000 / 6.208 | 0.319 / 0.379 | 1.00 / 2.5 | 2.56 | (자동 스냅샷, 판정은 게이트 리뷰에서) |
| 09-03 07:30 | 399 | 7.1 (50avg 6.8) | 155 | 0.379 | 0.0767 | 4.64 | -0.0065 / 1.3e-04 | 0.000 / 6.208 | 0.319 / 0.379 | 1.00 / 2.5 | 2.56 | (자동 스냅샷, 판정은 게이트 리뷰에서) |
| 09-03 08:30 | 399 | 7.1 (50avg 6.8) | 155 | 0.379 | 0.0767 | 4.64 | -0.0065 / 1.3e-04 | 0.000 / 6.208 | 0.319 / 0.379 | 1.00 / 2.5 | 2.56 | (자동 스냅샷, 판정은 게이트 리뷰에서) |
| 09-03 09:30 | 399 | 7.1 (50avg 6.8) | 155 | 0.379 | 0.0767 | 4.64 | -0.0065 / 1.3e-04 | 0.000 / 6.208 | 0.319 / 0.379 | 1.00 / 2.5 | 2.56 | (자동 스냅샷, 판정은 게이트 리뷰에서) |
| 09-03 10:30 | 399 | 7.1 (50avg 6.8) | 155 | 0.379 | 0.0767 | 4.64 | -0.0065 / 1.3e-04 | 0.000 / 6.208 | 0.319 / 0.379 | 1.00 / 2.5 | 2.56 | (자동 스냅샷, 판정은 게이트 리뷰에서) |
| 09-03 11:30 | 399 | 7.1 (50avg 6.8) | 155 | 0.379 | 0.0767 | 4.64 | -0.0065 / 1.3e-04 | 0.000 / 6.208 | 0.319 / 0.379 | 1.00 / 2.5 | 2.56 | (자동 스냅샷, 판정은 게이트 리뷰에서) |
