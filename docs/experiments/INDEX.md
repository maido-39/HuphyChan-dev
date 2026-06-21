# 학습 실험 대장 (Trial-and-Error Ledger)

> 모든 학습 run의 **가설 → 변경 → 명령 → 결과(지표) → 판정**을 한 곳에서 관리한다.
> 새 run을 돌릴 때마다 여기 한 줄 추가 + 중요한 건 `EXP-NNN_*.md` 상세노트. (reward 세부는 [[04_reward_experiments]])

## 규칙 (어떻게 기록)
- **ID**: `EXP-NNN` 순번. **run**: `logs/rsl_rl/<exp>/<timestamp>_<run_name>`.
- 지표: `reward`(Train/mean), `ep_len`(Mean episode length, /1000), `err_vxy`(Metrics/base_velocity/error_vel_xy↓좋음).
- 학습 중 영상: `<run>/videos/train/*.mp4` + 누적 `<run>/videos/accumulated_progress.mp4`.
- 판정: ✅수렴/유효 · ⚠️문제발견 · ❌폐기.

## 대장 (시간순)
| ID | 날짜 | task | envs/iter | 핵심 변경 (가설) | reward | ep_len | err_vxy | 판정 |
|---|---|---|---|---|---|---|---|---|
| EXP-001 | 06-20 | Flat | CPU 1024 / 330 | G1레시피+사람다움4종 시작점 | +7.8 | 814 | **0.9** | ⚠️ 균형OK·속도추종 부족(=학습량 부족) |
| EXP-002 | 06-20 | Flat | GPU 2048 / 1500 | #001을 충분히 학습 (가중치 동일) | **+41.9** | 990 | **0.25** | ⚠️ 수렴했으나 **방향버그(게걸음)**·DR꺼짐·자기충돌X 발견 (run `…17-08-09_gpu_flat_v1`) |
| EXP-003 | 06-20 | Flat | GPU 16384 / 800 | omnidirectional cmd + 체중/마찰/COM DR + feet_distance↑ | +42 | ~1000 | 0.28 | ⚠️ DR 추가, 단 방향버그·자기충돌 여전 (run `…gpu_flat_v2dr`) + stale-pyc 삽질 |
| EXP-004 | 06-20 | Flat | GPU 16384 / 800 | **방향 −90°회전 + 자기충돌 ON + 토크리밋 reward** | +39 | **1000** | **0.28** | ✅ **전진 보행 정상**(MuJoCo FK 검증). 발목 병목 확인 (run `…18-36-47_gpu_flat_v3fix`) |
| EXP-005 | 06-20 | Rough | GPU 16384 / 1000 | EXP-004 설정 + 계단/경사 커리큘럼 + **학습중 영상(조망+명령화살표)** | +? | — | — | ⚠️ rough 초기 (run `…gpu_rough_v3vid/toe150`) |
| EXP-006 | 06-21 | Flat | 16384 / 999 | **방향버그 완전수정**(flat_fwd_fixed) — 전진 보행 확립 | +? | 999 | — | ✅ 평지 전진 base (run `…00-38-22_flat_fwd_fixed`) |
| EXP-007 | 06-21 | Flat | 16384 / 1499 | **넓은 DR**(vx 2.5·yaw 1.57·마찰·외력↑) | +? | — | — | ✅ stage-2 [[2026-06-21_01-52-57_flat_wide_dr]] |
| EXP-008 | 06-21 | Flat | 16384 / 2499 | **발목 offload**(torque_soft_limit) — 포화 발목 완화 | +? | — | — | ✅ stage-3 [[2026-06-21_03-46-50_stage3_ankle_offload]] |
| EXP-009 | 06-21 | Rough | 16384 / 1999 | 평지→**rough 이전**(warm-start) | +? | — | — | ⚠️ stage-4 [[2026-06-21_06-41-42_stage4_rough]] |
| EXP-010 | 06-21 | Rough | 16384 / 1300 | rough **수렴 시도** | +5.3 | 879 | **0.918** | ❌ **미수렴**(낙상20%) [[2026-06-21_10-33-47_stage5_rough_converge]] |
| EXP-011 | 06-21 | Flat | 16384 / 2499 | **forefoot CoP 간접보상**(H-A: toe 적재 유도) | +? | — | — | ⚠️ **H-A 음성**(toe 미적재) [[2026-06-21_12-22-03_forefoot_cop]] |
| EXP-012 | 06-21 | Flat | 16384 / 300 | **ankle push-off 일 보상** scale=0.1 | **+484** | 975 | **1.73** | ❌ **reward-HACK** [[2026-06-21_15-40-30_forefoot_pushoff]] |
| EXP-013 | 06-21 | Flat | 16384 / 900 | push-off **수정**(scale0.02·cap80·w0.5) | +41 | 994 | **0.59** | ✅ **건강·H-A양성**(ankle_pushoff↑), 영상수정위해 중도종료→재개 [[2026-06-21_16-30-58_forefoot_pushoff2]] |
| EXP-013b | 06-21 | Flat | 16384 / 500 | pushoff2 이어서(평지영상 밀도수정·재개) `…18-00-41_forefoot_pushoff3` | +43 | — | 0.50 | ⚠️ 영상수정 후 재개, iter500서 **측정 위해 종료**(이 npz가 무릎 감속비 분석의 주 데이터 → [[35_knee_gear_ratio_analysis]]) |
| EXP-014 | 06-21 | Flat | 16384 / 1919 | **impact reward**(foot_landing_vel w−2.0 + foot_impact_force w−0.01), pushoff2 warm-start | +34.5 | — | **0.72** | ❌ **OOM**(iter1919 RAM kill) + **추종 악화**(0.50→0.72 plateau, 가중치 과대→−1.0/−0.005 하향) [[2026-06-21_19-03-51_softcontact]] |
| EXP-015 | 06-21 | Flat | 16384 / ~50 | softcontact **완주 시도**(model_1950 warm-start) | — | — | — | ❌ **OOM/INCOMPLETE**(iter~50 SIGKILL exit137, warm-start dip 중 사망) [[2026-06-21_21-59-35_softcontact2]] |

> [!note] GPU 성능 튜닝 / 초기 탐색 run (reward 무관, 노트 생략)
> `gpu_rough_v1/v2/v3/v3fix/v3vid/toe150`=envs 스윕·rough 초기 탐색([[10_gpu_perf_tuning]]) · `gpu_flat_v1/v2dr/teacher/curric/toe150`=초기 탐색(EXP-002~006으로 수렴) · `*_test/_configtest`=설정검증(미기록).

## 배운 것 (누적 교훈)
1. **학습량부터**: reward 튜닝 전에 충분한 iter 확보 (EXP-001→002: err_vxy 0.9→0.25).
2. **영상 리뷰 필수**: 지표(err_vxy 0.25)는 좋아도 **방향버그(게걸음)**는 영상으로만 발견됨 (EXP-002).
3. **"서있기" local optimum**: 제약(자기충돌·토크리밋) 추가 시 ep_len 먼저 차고(서있기) err_vxy 나중에 하락(보행). 중간 과민반응 금지 (EXP-004).
4. **토크리밋 reward 효과**: 고관절 util 100%→70%. 단 발목은 진짜 병목(못 피함).
5. **편집설치 stale .pyc**: 소스 고쳐도 옛 동작 → `find -name '*.pyc' -delete` + `PYTHONDONTWRITEBYTECODE=1`.
