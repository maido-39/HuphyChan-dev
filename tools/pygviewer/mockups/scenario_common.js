// scenario_common.js — shared fake state machine for the S1/S2/S3 scenario-switch mockups
// (scenario_A/B/C.html). Pure front-end, no server calls, no persistence. Loaded by each
// mockup via <script src="scenario_common.js">.
//
// CORE PRINCIPLE (2026-09-04, coordinator instruction):
// A scenario is NOT a state the UI owns. It is a NAME computed from the viewer's real
// state (mode + TX arm + robot-program confirmation). Two controls already exist that can
// set that real state independently of any scenario button (the mode dropdown, the TX
// arm/disarm control) — if either one moves, the scenario label must recompute, and if the
// combination no longer matches ANY scenario's recipe exactly, the label MUST fall to
// "custom" rather than keep showing a stale name. Robot-program confirmation is 3-valued
// (confirmed / unknown / mismatch) because the viewer cannot always know what the robot is
// actually running — "unknown" and "mismatch" both count as NOT matching, on purpose.

(function (window) {
  'use strict';

  var MODES = ['idle', 'manual', 'policy_sim', 'policy_shadow', 'real_replay', 'file_replay'];

  // Robot-side programs the viewer can *believe* are running. Real system: only one of
  // these three is meaningful per scenario; 'other' stands in for "something else / a
  // program the viewer doesn't have a name for".
  var ROBOT_PROGRAMS = {
    huphy_remote_motion: { label: 'huphy_remote_motion', torque: 'ON' },
    policy_exec_obs_stream: { label: 'policy executor + obs streamer', torque: 'ON' },
    obs_streamer_torque_off: { label: 'obs streamer', torque: 'OFF' },
    other: { label: '(다른/알 수 없는 프로그램)', torque: '?' }
  };

  // Naming (2026-09-04 decision): the primary label names the COMBINATION by who is
  // driving / which way data flows, not an arbitrary "S1/S2/S3" scenario slot. Only one
  // combination sends anything to real hardware, and that has to be legible from the name
  // alone, not just from a color. S1/S2/S3 survive only as a small secondary tag for
  // cross-referencing docs/plans.
  var SCENARIOS = {
    S1: {
      key: 'S1',
      id: 'drive-both',
      tag: 'S1',
      nameKo: '실물 동시 구동',
      nameEnHint: 'drive both (sim + hardware)',
      summary: '같은 목표를 sim·실물에 동시에 주고 응답 비교',
      actionVerb: '실물 동시 구동으로 전환',
      actionSubtitle: '→ 목표를 실물로도 전송합니다. 토크가 켜집니다.',
      mode: 'manual',
      tx: true,
      robotProgram: 'huphy_remote_motion',
      sshCmd: "ssh bench@10.8.0.14 'sudo systemctl restart huphy_remote_motion'",
      txDirection: 'ON — 목표를 실물로 전송',
      risky: true // moving INTO this combination from tx=false arms real torque
    },
    S2: {
      key: 'S2',
      id: 'shadow-policy',
      tag: 'S2',
      nameKo: '로봇 정책 관측',
      nameEnHint: "shadow the robot's own policy",
      summary: '로봇이 정책을 돌리고 그 관측을 받아 sim 정책과 비교',
      actionVerb: '로봇 정책 관측으로 전환',
      actionSubtitle: '→ 전송 없음. 로봇 관측을 받아 비교만 합니다.',
      mode: 'policy_shadow',
      tx: false,
      robotProgram: 'policy_exec_obs_stream',
      sshCmd: "ssh bench@10.8.0.14 'sudo systemctl restart huphy_policy_exec'",
      txDirection: 'OFF — 정책 출력 전송 금지',
      risky: false,
      broken: true,
      brokenReason: '불가 — 수신된 관측이 뷰어에서 버려지고(수신측), 로봇도 관측을 내보내지 않음(송신측)'
    },
    S3: {
      key: 'S3',
      id: 'mirror-hardware',
      tag: 'S3',
      nameKo: '손으로 미러링',
      nameEnHint: 'mirror hardware, no physics',
      summary: '손으로 움직인 값을 물리 없이 그대로 표시 (향후 mode 이름: kinematic)',
      actionVerb: '손으로 미러링으로 전환',
      actionSubtitle: '→ 전송 없음. 사람이 움직인 값을 그대로 그립니다.',
      mode: 'real_replay',
      tx: false,
      robotProgram: 'obs_streamer_torque_off',
      sshCmd: "ssh bench@10.8.0.14 'sudo systemctl restart huphy_obs_streamer'",
      txDirection: 'OFF — 전송 없음',
      risky: false
    }
  };

  var SCENARIO_ORDER = ['S1', 'S2', 'S3'];

  function freshState() {
    return {
      mode: 'manual',
      tx: true,
      robotConfirm: 'confirmed', // 'confirmed' | 'unknown' | 'mismatch'
      robotProgram: 'huphy_remote_motion',
      guided: false, // false = 자동 SSH 전환 (현재 기본값) / true = 안내만 (향후 기본값)
      log: []
    };
  }

  // The label the UI is allowed to show. Returns a scenario key or null ("custom").
  // Matching is exact on purpose: mode, tx, AND robotConfirm==='confirmed' with the right
  // program. A close-but-not-exact match is still custom, never a guess.
  function deriveScenario(st) {
    for (var i = 0; i < SCENARIO_ORDER.length; i++) {
      var k = SCENARIO_ORDER[i];
      var sc = SCENARIOS[k];
      if (
        st.mode === sc.mode &&
        st.tx === sc.tx &&
        st.robotConfirm === 'confirmed' &&
        st.robotProgram === sc.robotProgram
      ) {
        return k;
      }
    }
    return null;
  }

  // Human-readable list of what differs between current state and one named scenario.
  function diffFromScenario(st, key) {
    var sc = SCENARIOS[key];
    var diffs = [];
    if (st.mode !== sc.mode) {
      diffs.push('뷰어 모드가 ' + st.mode + ' 임 (필요: ' + sc.mode + ')');
    }
    if (st.tx !== sc.tx) {
      diffs.push('TX가 ' + (st.tx ? '무장' : '해제') + ' 상태 (필요: ' + (sc.tx ? '무장' : '해제') + ')');
    }
    if (st.robotConfirm === 'unknown') {
      diffs.push('로봇 프로그램 확인 안 됨 (모름)');
    } else if (st.robotConfirm === 'mismatch') {
      diffs.push(
        '로봇 프로그램 마지막 확인이 어긋남 — 실행 중으로 보이는 것: ' +
          ROBOT_PROGRAMS[st.robotProgram].label
      );
    } else if (st.robotProgram !== sc.robotProgram) {
      diffs.push(
        '로봇이 ' +
          ROBOT_PROGRAMS[st.robotProgram].label +
          ' 실행 중(확인됨) — ' +
          sc.key +
          '는 ' +
          ROBOT_PROGRAMS[sc.robotProgram].label +
          ' 필요'
      );
    }
    return diffs;
  }

  // Which named scenario is "closest" (fewest mismatched axes), for the custom banner.
  function nearestCustomInfo(st) {
    var best = null;
    for (var i = 0; i < SCENARIO_ORDER.length; i++) {
      var k = SCENARIO_ORDER[i];
      var d = diffFromScenario(st, k);
      if (!best || d.length < best.diffs.length) {
        best = { key: k, diffs: d };
      }
    }
    return best;
  }

  // True if jumping to `key` from the given state would flip real torque from off/unknown
  // to on (S1 is the only scenario whose recipe demands tx=true / torque-ON program).
  function isRiskyActivation(st, key) {
    var sc = SCENARIOS[key];
    return !!sc.risky && st.tx !== true;
  }

  // Apply a scenario's mode+TX recipe to a state object in place. This is the "shortcut"
  // half only — it does NOT touch robotConfirm/robotProgram, because pressing a button in
  // the viewer cannot, by itself, make the robot actually be running the right program.
  function applyScenarioShortcut(st, key) {
    var sc = SCENARIOS[key];
    st.mode = sc.mode;
    st.tx = sc.tx;
  }

  // Simulate the robot-program switch. In "auto" mode this simulates the viewer SSHing in
  // directly and, on a zero exit code, marking the program confirmed (no independent
  // readback — that caveat is deliberately surfaced in the UI, not hidden). In "guided"
  // mode it does nothing to the state; it only returns the command for the operator to run
  // by hand, and the caller must show a separate "I ran it" confirmation control.
  function performRobotSwitch(st, key, guided) {
    var sc = SCENARIOS[key];
    if (guided) {
      return { executed: false, cmd: sc.sshCmd };
    }
    st.robotConfirm = 'confirmed';
    st.robotProgram = sc.robotProgram;
    return { executed: true, cmd: sc.sshCmd };
  }

  function modeLabel(m) {
    return m;
  }

  function fmtDeg(v) {
    // House rule: every on-screen angle carries a literal "(deg)" suffix.
    return v.toFixed(1) + ' (deg)';
  }

  window.ScenarioMockup = {
    MODES: MODES,
    ROBOT_PROGRAMS: ROBOT_PROGRAMS,
    SCENARIOS: SCENARIOS,
    SCENARIO_ORDER: SCENARIO_ORDER,
    freshState: freshState,
    deriveScenario: deriveScenario,
    diffFromScenario: diffFromScenario,
    nearestCustomInfo: nearestCustomInfo,
    isRiskyActivation: isRiskyActivation,
    applyScenarioShortcut: applyScenarioShortcut,
    performRobotSwitch: performRobotSwitch,
    modeLabel: modeLabel,
    fmtDeg: fmtDeg
  };
})(window);
