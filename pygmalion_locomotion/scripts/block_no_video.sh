#!/bin/bash
# PreToolUse(Bash) HOOK — ROOT-CAUSE ENFORCEMENT of "video ON at every training start".
# The user repeatedly DEFINED the training start/end protocol (video on for gait debugging); the model kept
# passing --no_video by its own choice. The Stop-hook audit only catches it AFTER the run. This blocks it at
# LAUNCH so it is impossible to start a real training run without video. Robust: any parse error -> exit 0.
input=$(cat 2>/dev/null)
cmd=$(printf '%s' "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null) || exit 0
# only police ACTUAL launches: `python ... train.py ... --no_video` contiguous in one pipeline segment.
# (this excludes git commit messages / echo / grep that merely MENTION the strings — the false positive
#  that blocked the commit describing this very hook.)
printf '%s' "$cmd" | grep -qE 'python[^|&;]*train\.py[^|&;]*--no_video' || exit 0
# allow explicitly-named test/config runs (they may skip video)
printf '%s' "$cmd" | grep -qE "_test|_configtest|_cfgtest|vidtest|configtest" && exit 0
echo "★★ BLOCKED (PreToolUse): train.py was launched with --no_video on a NON-test run. The user's STANDING RULE is video ON at EVERY training start (gait debugging is impossible without it) and the model kept violating it. REMOVE --no_video and relaunch. FLAT keeps density / ROUGH adjusts spacing so robots are distinguishable (frame-check). For a throwaway build/config test, name the run *_configtest." >&2
exit 2
