# Dashboard — 도구 사이트맵 + 헬스 인디케이터

    bash tools/dashboard/start_all.sh      # 모든 서비스 기동(이미 떠 있으면 건너뜀)
    http://192.168.20.177:8890/tools/dashboard/

| 포트 | 서비스 |
|---|---|
| 8890 | 이 대시보드 + 리포지토리 파일 서빙(docs/영상/이미지/HTML 도구) |
| 8089 / 8090 | viser live — AB / RP 런의 **최신 체크포인트 자동 로드**(30 s 폴링), Torques 탭(관절별 토크 uplot + AB 발목 환산 토크), Controls 탭(명령 슬라이더, 체크포인트 선택) — `mujoco-sim/mjlab/analysis/viser_live.py`, 재시작 `analysis/viser_live.sh AB|RP [port]` |
| 6006 | TensorBoard (`logs/rsl_rl/pygmalion_velocity` 전 런) |
| 8892 | 컬리전 웹 뷰어 (`tools/collision_viewer`) |
| 8891 | 조립(나사) 뷰어 (`tools/assembly_viewer`) |
| — | wandb: https://wandb.ai/dongyub39-snu/pygmalion |

헬스: `status.py`가 15 s마다 `status.json`을 갱신 — 런별 생존/iter/reward/낙상/s·iter/ETA/최신 체크포인트 나이(>20 min이면 ⚠ stale)/롤아웃 클립 수, 서비스 포트 up/down, 백그라운드 헬퍼(gate_watch·review_loop·gpu_sampler·viser_live·train) 프로세스 수, GPU util/메모리, load, 디스크.
