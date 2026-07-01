# mjlab Pygmalion 작업 (HuphyChan에 포함, upstream mjlab 제외)

mjlab(MuJoCo-Warp) 위에서 한 **Pygmalion 하지 로봇** RL·부하분석 작업의 **우리 소유 산출물만** 모은 폴더.
mjlab 본체(upstream `mujocolab/mjlab`)는 submodule(`../mjlab`)이라 여기엔 **upstream 코드는 없음** — 우리
추가/수정분 + 핵심 weights + 분석 결과만. 동료가 clone → `sync_to_mjlab.sh`로 mjlab에 얹어 실행.

## 구성
- `analysis/` — 측정·플롯·영상·진행분석·play 도구 (12개 스크립트). CPU 격리로 학습 무중단 실행.
- `robot/robots_pygmalion/` — 로봇 정의(`pygmalion_constants.py`, `xmls/` MJCF·메시, actuator config).
- `robot/task_velocity_pygmalion/` — velocity 태스크 config(reward/obs/spawn) + `Mjlab-Velocity-{Flat,Rough}-Pygmalion` 등록.
- `robot/REGISTRATION.md` — mjlab upstream에 필요한 최소 수정(2 import + sim.py 패치).
- `weights/` — **핵심 체크포인트만** (run1 0→30000 6000단위, run2 30000→ 6000단위+최신) + tensorboard `events.*`.
- `sync_to_mjlab.sh` — 위 robot/analysis를 mjlab clone에 복사(적용).
- 분석 결과(노트·플롯·영상)는 상위 **`docs/mujoco/`** 참조.

## 동료 사용법
```bash
# 1) mjlab 본체 (submodule과 동일 커밋 권장): 20f10e96
git clone https://github.com/mujocolab/mjlab && cd mjlab && git checkout 20f10e96
# 2) 우리 작업 적용
bash <이 폴더>/sync_to_mjlab.sh <mjlab 경로>
#    → robot/analysis 복사 + REGISTRATION.md의 2 import·sim.py 패치 안내
# 3) 환경
uv sync
# 4) 실행 (예: 학습 / 부하측정)
uv run train Mjlab-Velocity-Flat-Pygmalion --env.scene.num-envs 4096
CUDA_VISIBLE_DEVICES="" uv run python analysis/measure_loads.py --run-dir <run> --tag flat --wide-dr
# 5) weights 로 play (부하-색)
uv run python analysis/play_loadviz.py --checkpoint weights/run2_30000plus/model_51700.pt --run-dir <run>
```

## 참고
- 실제 Kp/Kd: ankle_roll 1.97/0.126, hip_yaw·ankle_pitch 19.74/1.26, hip_pitch·roll·knee 27.64/1.76 (ωₙ=10Hz, ζ=2).
- 측정값 정확성 audit·해석은 `docs/mujoco/` 노트 참조.
- 이 폴더는 upstream 코드가 없어 **HuphyChan에서 계속 commit** 가능(우리 파일만).
