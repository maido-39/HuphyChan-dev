# gen21_rough_uneven2_p2b — rough 설계앵커 (uneven, DR+push full ramp)

> **한 줄**: uneven2 P1(계단·급슬로프 제거, fell 0 수렴)에 **DR+push 램프**를 정상 주입한 P2. 첫 P2(`2026-07-15_00-58-24_gen21_rough_uneven2_p2`)는 dr_factor 0.33 정체 버그로 폐기, dr윈도우 정렬 override(PYG_DR_START/END_ITER=12000/24000)로 재학습한 것이 본 런. **dr 0→1.0 완전 램프하는 내내 fell ~0** = 유효 robust rough 앵커. 부하 측정(v2)·A/B는 아래 §후속.

## §1 재현성
- run: `logs/rsl_rl/pygmalion_velocity/2026-07-15_03-48-03_gen21_rough_uneven2_p2b` (최종 model_23998)
- launch: `PYG_UNEVEN=1 PYG_INIT_BENT=1 PYG_DR_START_ITER=12000 PYG_DR_END_ITER=24000` + `train_wandb_video.py Mjlab-Velocity-Rough-Pygmalion --resume --load-run <uneven2_p1> --load-checkpoint model_11999`, 4096 env, +12k iter(→abs 23999).
- 지형: `UNEVEN_TERRAINS_CFG`(flat0.2·slope0.15+0.15@rise/run 0.3·rough0.25·wave0.25, **계단 0%**). config: params/env.yaml.
- 측정소스: `p2b_v2_fc` **완료**(2026-07-16 01:07, v2 텔레포트, tile 88.6%) — §3c/§5/§7 채움.

## §1b Reward & Gains
- Gen-2.1 번들 동일([[2026-07-13_gen21_bent_p2]]) — 지형(UNEVEN)·DR override만 변인. Kp/Kd/effort/speed 불변.

## §2 최종 지표 (full DR+push, dr_factor=1.0)
- **fell_over 0.0000**(최종), DR 램프 구간(iter 12k→24k) 내내 0.00–0.04 유지.
- track_linear reward 0.66·track_angular 0.60·Mean reward 27.0 (rough+full DR라 flat 1.33보다 낮음이 정상; 절대 추종%는 v2 측정에서).
- dr_factor 궤적: 0(iter12k)→0.33(16k)→0.50(18k)→0.67(20k)→0.83(22k)→**1.0(24k)**.

## §4 부모/변인 비교
- vs 첫 P2 `2026-07-15_00-58-24_gen21_rough_uneven2_p2`(폐기): 동일 launch, **dr override만 추가**. 그 런은 dr_factor가 iter 17571에도 0.0 → DR 미주입(robust 무효). 원인·수정은 [[2026-07-14_gen21_rough_uneven2_p1]] §P2-버그.
- vs P1: DR+push 램프 추가(단일변인).

## §9 DR/push 램프
- ★핵심 수정: dr윈도우를 `start_step=288000(iter12k)·end_step=576000(iter24k)`로 정렬(env override). counter는 resume 시 복원(P1 12k+FRESH→288000)되므로 P2b 시작부터 램프 개시. push_max x/y±0.7·z±0.4·rpy±0.52/0.78, friction 0.3–1.2, encoder±0.015, com±0.025~0.03. dr=1.0 완전 도달 확인.

## §3c 측정 커버리지 (v2 텔레포트, p2b_v2_fc — 완료 2026-07-16 01:07)
- **tile_dwell 88.6%** · grid_dwell 100% — 구 p2r_fc(60% 오염) 대비 **대폭 개선**, v2 텔레포트 프로토콜 유효. (목표 90%에 1.4%p 근접 — 앵커로 수용, 잔여는 블록 경계 settle 구간.)

## §5·§7 부하 — rough 앵커 vs flat 앵커 (실측, 적응정책)
![[rough_vs_flat_anchor.png]]

| 관절 (모터) | rough RMS/P99 | flat RMS/P99 | rough %rated/%peak | rough−flat |
|---|---|---|---|---|
| hip_pitch (RS04) | 28.4/94.5 | 27.7/91.7 | 71%/79% | +2/+2 |
| hip_yaw (RS04) | 12.3/38.2 | 12.8/32.9 | 31%/32% | −1/+4 |
| hip_roll (RS04) | 23.2/62.1 | 23.6/58.1 | 58%/52% | −1/+3 |
| knee (RS04) | 38.6/107.4 | 45.5/112.4 | 96%/89% | **−17/−4** |
| ankle_pitch (RS03) | 14.9/49.5 | 13.6/54.7 | 75%/83% | +7/−9 |
| **ankle_roll (RS00)** | **5.2/17.7** | 2.9/10.3 | **104%/126%** | **+45/+53** |
| **GRF (BW)** | **P99 1.74** | P99 1.20 | | **+45%** |

### 해석 (rough가 flat 대비 하중을 어떻게 바꾸나)
- ★**ankle_roll(RS00)이 험지의 지배 병목**: P99 17.7 = **RS00 peak 14의 126% 초과**, RMS 104% rated. 울퉁불퉁·경사에서 **발목 측방(내번/외번) 보정이 급증** → 최약 모터(RS00 14/5)가 flat에선 여유(73% peak)였다가 rough서 초과. **RS00→상위(RS02급) 상향 or ankle_roll 링크레버 재설계 검토 필요**.
- **GRF P99 1.74BW**(flat 1.20, +45%) — 험지 착지 충격↑. 구조·베어링 사이징은 rough 앵커값으로. (raw peak 13.8BW는 클립 아티팩트, P99×1.25로 사이징.)
- **knee는 오히려 −17%p RMS/−4%p P99**(더 신중한 gait) — flat이 knee 열부하 worst 유지.
- hip_pitch/hip_roll P99 소폭↑(+2/+3), 나머지 무해.
- **설계 하중 세트 결론**: flat=knee 열(114% rated)이 worst / rough=**ankle_roll(RS00)·GRF**가 worst. 두 앵커의 **관절별 max**를 설계 상한으로 채택.

## §11 이상징후 — reward 스파이크
- neg-spike 20/12k iter(P1 36→감소), fell 무영향. uneven 엣지 대형접촉의 캡없는 페널티 추정 → Gen-2.2 캡 후보.

## §12 판정
- ✅ **유효 robust rough 설계앵커 확정** — full DR+push fell ~0, v2 tile 88.6%, 부하 실측 완료.
- ★설계 반영: **rough는 ankle_roll(RS00 126% peak)·GRF 1.74BW가 병목** = flat(knee 열)과 다른 관절이 worst. 하중 세트 = flat∪rough 관절별 max. RS00 ankle_roll 상향/레버 재설계가 rough 대응 핵심 과제.
- 계보: flat 앵커 gen21_bent_p2 → uneven2 P1(지형수정) → **본 P2b**(DR정상) = **flat+rough 설계 하중 세트 완성**.

## 후속 (선택 — 앵커 승격 시)
- §8c TN 설계선도·§10 링크 wrench 6관절·§3b loadviz 영상은 앵커 확정에 따라 gen21_bent_p2급으로 확장 가능(현재 §5/§7 부하판정으로 설계 의사결정 충분).
- 등록: [[66_experiment_registry]] Era-9, [[experiment_map.canvas]], INDEX.
