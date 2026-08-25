#!/bin/bash
# 인간형 착지 번들 시험 — 대조군 vs 처치군, +800 iter · 1024 env warm-start.
#   근거 노트: docs/reward_research/2026-08-26_human_landing_bundle.md
#   판정 지표: 접지 무릎 <= -15 deg / GRF 2차 봉우리 / 스윙 -55~-65 유지 / 낙상 0 /
#              추종 열화 <10 % / ★air_time·stride 유지(하중률 해킹 감시)
# 실행 전 확인: GPU 여유(nvidia-smi), RAM >= 6 GB, 두 런이 각 ~1.2 GB GPU.
# 사용법:  bash tools/robot_model/loop_tests/run_landing_bundle_test.sh [AB|RP]
set -euo pipefail
MODE="${1:-AB}"
cd /home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab
D=$(ls -d logs/rsl_rl/pygmalion_velocity/*_ankle${MODE}_c3)
CK=model_31999.pt
[ -f "$D/$CK" ] || { echo "!! $D/$CK 없음"; exit 2; }

COMMON="PYG_V2=1 PYG_INIT_BENT=1 PYG_ARM_ABD_DEG=15 PYG_INERTIAL_DR=1 PYG_ANKLE_MODE=$MODE \
        PYG_DR_START_ITER=0 PYG_DR_END_ITER=1 PYG_TN=1 PYG_MOTOR_MEAS=1"
#            ^ DR은 이미 만배인 체크포인트에서 이어가므로 즉시 full로 둔다

launch () {   # $1 = run name, $2.. = extra env
  local NAME="$1"; shift
  echo "== launch $NAME  $(date +%H:%M:%S)"
  env $COMMON "$@" nohup .venv/bin/python3 analysis/train_wandb_video.py \
      Mjlab-Velocity-Flat-Pygmalion --video True --video-interval 8000 --video-length 500 \
      --env.scene.num-envs 1024 --agent.max-iterations 800 --agent.run-name "$NAME" \
      --agent.logger wandb --agent.resume True --agent.load-run "$(basename $D)" \
      --agent.load-checkpoint "$CK" \
      > "logs/${NAME}.log" 2>&1 &
  echo "   pid $! -> logs/${NAME}.log"
}

# 대조군: c3와 완전히 같은 보상 (soft-landing = 접지속도 제곱)
launch "bundleCTL_${MODE}" PYG_SOFT_LANDING=1

sleep 20   # 두 런이 동시에 모델을 컴파일하지 않도록 살짝 어긋나게

# 처치군: 초기자세 중간값 + base_height 앵커 + 하중률 기반 착지
launch "bundleTRT_${MODE}" PYG_SOFT_LANDING=1 PYG_INIT_MID=1 \
       PYG_BASE_HEIGHT_ANCHOR=1 PYG_SOFT_LANDING_MODE=rate

cat <<'NOTE'

== 다음 단계 (사람이 확인)
1. 두 로그의 env.yaml diff로 의도한 3개 변인만 다른지 확인
2. 800 iter 완주 후 각 체크포인트에:
     tools/robot_model/loop_tests/impact_probe.py   (200 Hz 접지속도/피크/하중률)
     mjlab 내장 평가기 3시나리오 x 32 ep          (추종·성공률)
     tools/robot_model/abrp_gait_style.py          (접지 무릎·GRF 파형·스윙)
3. 판정표는 docs/reward_research/2026-08-26_human_landing_bundle.md §4
NOTE
