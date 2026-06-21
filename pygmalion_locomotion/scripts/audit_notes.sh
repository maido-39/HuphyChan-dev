#!/bin/bash
# audit_notes.sh — Stop-HOOK enforcement: BLOCK (exit 2) if substantial training runs / analysis are
# un-recorded as notes. The memory rules kept being forgotten; this makes the HARNESS enforce them so it
# does not depend on the model remembering. stderr is fed back to the model as the reason to keep working.
# Wired as a Claude Code Stop hook (settings.json). Robust: any internal error -> exit 0 (never wedge).
ROOT=/home/syaro/MikuchanRemote/Human-Pygmalion
cd "$ROOT" 2>/dev/null || exit 0
g=""

# (1) DONE substantial runs (>=500 iter, inactive >5min) whose name is referenced NOWHERE in docs/
for d in pygmalion_locomotion/logs/rsl_rl/*/*/; do
  [ -d "$d" ] || continue
  run=$(basename "$d")
  # skip runs matching the explicit skip-list (exploratory / config-test runs not individually noted)
  [ -f docs/experiments/.audit_skip ] && grep -qFf docs/experiments/.audit_skip <<<"$run" 2>/dev/null && continue
  l=$(ls "$d"model_*.pt 2>/dev/null | sed 's/.*model_//; s/\.pt//' | sort -n | tail -1)
  [ -z "$l" ] && continue
  [ "$l" -lt 500 ] 2>/dev/null && continue
  # skip ACTIVE runs (a checkpoint written in the last 5 min)
  [ -n "$(find "$d" -maxdepth 1 -name 'model_*.pt' -mmin -5 2>/dev/null)" ] && continue
  short=$(echo "$run" | cut -d_ -f3-)   # strip YYYY-MM-DD_HH-MM-SS -> run_name (INDEX refs use short name)
  { grep -rqF "$run" docs/ 2>/dev/null || { [ -n "$short" ] && grep -rqF "$short" docs/ 2>/dev/null; }; } && continue
  g="$g\n  - run '$run' (iter $l): NO docs note  -> docs/experiments/$run.md + INDEX"
done

# (2) experiment notes left with [작성 필요] placeholders
for f in $(grep -rlF "작성 필요" docs/experiments/*.md 2>/dev/null); do
  g="$g\n  - ${f##*/}: [작성 필요] 미작성 (정량/정성 분석 채우기)"
done

# (3) ad-hoc ANALYSIS plots in docs/assets not embedded in any note
for p in docs/assets/*.png; do
  [ -e "$p" ] || continue
  n=${p##*/}
  case "$n" in *knee_*|*analysis*|*demand*|*envelope*|*_split*|*compare*|*ratio*) ;; *) continue ;; esac
  grep -rqF "$n" docs/*.md docs/experiments/*.md 2>/dev/null && continue
  g="$g\n  - plot '$n': 어떤 노트에도 미임베딩 (분석 노트에 ![](assets/$n) 추가)"
done

# (4) substantial TRAINING runs with NO in-training VIDEO (--no_video used -> gait 디버깅 불가; user rule:
#     항상 영상 ON, FLAT=밀도유지 / ROUGH=spacing조정해 로봇 분간). accumulate 또는 train clip 둘 다 없으면 flag.
for d in pygmalion_locomotion/logs/rsl_rl/*/*/; do
  [ -d "$d" ] || continue
  run=$(basename "$d")
  [ -f docs/experiments/.audit_skip ] && grep -qFf docs/experiments/.audit_skip <<<"$run" 2>/dev/null && continue
  l=$(ls "$d"model_*.pt 2>/dev/null | sed 's/.*model_//; s/\.pt//' | sort -n | tail -1)
  [ -z "$l" ] && continue
  [ "$l" -lt 500 ] 2>/dev/null && continue
  [ -n "$(find "$d" -maxdepth 1 -name 'model_*.pt' -mmin -5 2>/dev/null)" ] && continue
  # ★ require BOTH (user 2026-06-22): OVERVIEW (train clips / accumulate) AND CLOSE-UP (play single-robot).
  ov=0; { [ -f "${d}videos/accumulated_progress.mp4" ] || ls "${d}videos/train/"*.mp4 >/dev/null 2>&1; } && ov=1
  cu=0; ls "${d}videos/play/"*.mp4 >/dev/null 2>&1 && cu=1
  [ "$ov" = 1 ] && [ "$cu" = 1 ] && continue
  miss=""; [ "$ov" = 0 ] && miss="overview"; [ "$cu" = 0 ] && miss="$miss close-up"
  g="$g\n  - run '$run' (iter $l): 영상 누락 ($miss) -> 학습 영상ON(overview) + 끝나고 play.py --video(단일로봇 클로즈업) 둘 다 필요. gait 디버깅용"
done

if [ -n "$g" ]; then
  printf "★★ NOTE-AUDIT BLOCK — 미기록 실험/분석이 있습니다. 종료 전 노트화하세요 (feedback-training-report-rule / feedback-research-recording-rule):%b\n(진짜 끝내려면: 노트를 만들거나, config-test면 무시 가능 — 단 반복 누락은 사용자가 싫어함)\n" "$g" >&2
  exit 2
fi
exit 0
