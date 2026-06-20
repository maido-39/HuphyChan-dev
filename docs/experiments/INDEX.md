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
| EXP-005 | 06-20 | Rough | GPU 16384 / 1000 | EXP-004 설정 + 계단/경사 커리큘럼 + **학습중 영상(조망+명령화살표)** | _(진행)_ | — | — | 🔄 학습 중 (run `…gpu_rough_v3vid`) |

> [!note] GPU 성능 튜닝 run (reward 무관, 참고)
> `gpu_rough_v1/v2/v3` = num_envs 2048→8192→16384 스윕(GPU util 60→90%). [[10_gpu_perf_tuning]].

## 배운 것 (누적 교훈)
1. **학습량부터**: reward 튜닝 전에 충분한 iter 확보 (EXP-001→002: err_vxy 0.9→0.25).
2. **영상 리뷰 필수**: 지표(err_vxy 0.25)는 좋아도 **방향버그(게걸음)**는 영상으로만 발견됨 (EXP-002).
3. **"서있기" local optimum**: 제약(자기충돌·토크리밋) 추가 시 ep_len 먼저 차고(서있기) err_vxy 나중에 하락(보행). 중간 과민반응 금지 (EXP-004).
4. **토크리밋 reward 효과**: 고관절 util 100%→70%. 단 발목은 진짜 병목(못 피함).
5. **편집설치 stale .pyc**: 소스 고쳐도 옛 동작 → `find -name '*.pyc' -delete` + `PYTHONDONTWRITEBYTECODE=1`.
