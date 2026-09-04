/* pygviewer dashboard (layout B). Vanilla JS, no build step, no framework.
 *
 * Talks to the SAME FastAPI process that serves this page (relative URLs): REST for
 * commands/config, one WebSocket (/ws/out) for the hot path (JointState + Status +
 * PolicyIO), and a slow poll of a few REST endpoints (/snapshot, /gains, /presets,
 * /policy/list) for state that changes at human speed. See tools/pygviewer/API.md for
 * the wire schema this all reads.
 */
(function () {
"use strict";

const RAD2DEG = 180 / Math.PI;
const DEG2RAD = Math.PI / 180;
const RING_MAX_S = 60;

function el(id) { return document.getElementById(id); }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function fmt(v, n) { return (v === null || v === undefined || Number.isNaN(v)) ? "-" : Number(v).toFixed(n === undefined ? 3 : n); }

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) { opts.headers["content-type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  let data = null;
  try { data = await r.json(); } catch (e) { /* no body */ }
  if (!r.ok) { const msg = (data && data.detail) ? data.detail : r.statusText; throw new Error(`${method} ${path} -> ${r.status}: ${JSON.stringify(msg)}`); }
  return data;
}
function apiOk(method, path, body) { return api(method, path, body).catch((e) => { console.warn(e); toast(e.message); return null; }); }

let toastTimer = null;
function toast(msg) {
  let t = el("toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    t.style.cssText = "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);" +
      "background:#3a1414;color:#f88;padding:8px 14px;border-radius:6px;font-size:12px;" +
      "z-index:100;max-width:70vw;box-shadow:0 2px 8px #0008";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.style.display = "none"; }, 4000);
}

/* ------------------------------------------------------------------ global state */
const S = {
  contract: null,       // GET /contract .contract (raw baked contract)
  status: null,         // latest Status (WS)
  joints: null,         // latest sim JointState (WS)
  policyio: null,       // latest PolicyIO (WS, only while a policy is loaded)
  snapshot: null,       // GET /snapshot, polled
  gains: null,          // GET /gains, polled
  presets: null,        // GET /presets, polled
  policyList: [],       // GET /policy/list, polled while Policy tab open
  latestReal: { t: null, q: {}, qd: {}, tau: {}, target: {} },
  realJointNames: [],    // A4 fix: ordered union of joint names ever seen on a src="real"
                          // JointState frame - used (with sim action_joint_names) to build
                          // plot panels, so a real joint that doesn't fit the sim's L/R
                          // naming template still gets somewhere to plot instead of
                          // silently resolving to null. See panelsFor() below.
  latestTxSent: {},      // {joint_name: rad} - from polling /tx/status().last_sent_target
  ring: [],             // [{t, q:{}, target:{}, tau:{}, qd:{}, realQ:{}, realTau:{}, realQd:{}, realAgeS, sentTarget:{}}]
  txStatus: null,        // GET /tx/status, polled - server-side truth for enabled/armed/sending
  txDeadmanTimer: null,
  leftTab: "model",
  rightTab: "control",
  controlMode: "joints", // "joints" | "policy" - mutually exclusive sub-view of the Control tab
  unit: "deg",           // "deg" | "rad" - Joints tab display only; wire/internal stays rad
  plotWindowS: 10,
  plotRows: { pos: true, tau: false, qd: false },
  plotInstances: {},     // "pos:hip_pitch" -> uPlot instance
  modal: null,           // {row, kind} while the modal is open
  jointKinds: [],        // e.g. ['hip_pitch','hip_roll','hip_yaw','knee','crank_A','crank_B']
  lastPanelRealCount: 0, // A4 fix: S.realJointNames.length as of the last buildPlotGrid() -
                          // renderPlots() rebuilds when this goes stale (see there)
  plotPanels: {},        // A4 fix: kind -> {kind,Lname,Rname,realOnly} as actually built by
                          // buildPlotGrid() - seriesArraysFor()/openModal() read the real
                          // joint names from here instead of re-deriving an `L_${kind}_joint`
                          // guess, so a panel's own construction and its data query always
                          // agree (see panelsFor()).
  violations: null,      // GET /violations, polled only while the panel is open - {records, by_joint, total}
  violationPanelOpen: false,
  health: null,          // GET /health, polled only while the Telemetry tab is open - {link, joints, summary}
  lastHealthRxCount: undefined, // drives the topbar heartbeat dot's flicker (renderTopBar)
  policyLoadedName: null,
  policyLayoutDims: null, // {name,func,dim,offset}[] from POST /policy/load's own response -
                          // authoritative for THIS loaded policy (a policy_contract may
                          // override obs_terms order/subset vs. the model's own obs_layout)
  ws: null,
};

/* ------------------------------------------------------------------ contract helpers */
function jointKindsOf(actNames) {
  const seen = [];
  for (const n of actNames) {
    const kind = n.replace(/^[LR]_/, "").replace(/_joint$/, "");
    if (!seen.includes(kind)) seen.push(kind);
  }
  return seen;
}

/* ---- Plot panel construction (A4 fix, docs/121_pygviewer_design.md sec 10) --------------
 * Panels used to be built ONLY from S.jointKinds (derived from the sim contract's
 * action_joint_names), and seriesArraysFor() then re-guessed each panel's real-side data by
 * re-templating `L_${kind}_joint` / `R_${kind}_joint`. onJointState() already received and
 * buffered every src="real" joint (S.latestReal, then S.ring's realQ/realQd/realTau/
 * realTarget) regardless of its name - but a real joint whose name didn't fit that template
 * (an unmapped bridge name, an extra bench joint the sim contract doesn't actuate, a variant
 * mismatch) had no panel to land in and its series silently resolved to null forever, with
 * no visible error.
 *
 * Fix: build panels from the UNION of sim action_joint_names and every real joint name ever
 * observed, not from the sim contract alone. Pure and DOM-free so it's independently
 * testable (see the note below on verification limits - there is no JS test runner in this
 * repo, so this is exercised by code review + the doc/commit trail, not an automated test). */
function jointNameParts(name) {
  const m = /^([LR])_(.*)_joint$/.exec(name);
  if (m) return { kind: m[2], side: m[1] };
  return { kind: name, side: null }; // doesn't fit the L_*_joint/R_*_joint convention at all
}

function panelsFor(simNames, realNames) {
  const order = []; // display order: sim kinds first (stable, matches today's layout),
                     // then any additional kind only ever seen on the real side, in the
                     // order it was first observed
  const info = {};
  function ensure(kind) {
    if (!info[kind]) {
      info[kind] = { kind, Lname: null, Rname: null, single: null, inSim: false, inReal: false };
      order.push(kind);
    }
    return info[kind];
  }
  function ingest(names, flag) {
    (names || []).forEach((n) => {
      const { kind, side } = jointNameParts(n);
      const rec = ensure(kind);
      rec[flag] = true;
      if (side === "L") rec.Lname = n;
      else if (side === "R") rec.Rname = n;
      else rec.single = n; // no L/R prefix - gets a standalone (unpaired) panel
    });
  }
  ingest(simNames, "inSim");
  ingest(realNames, "inReal");
  return order.map((kind) => {
    const rec = info[kind];
    return {
      kind,
      Lname: rec.Lname || rec.single, // a lone unpaired name plots in the "L" slot
      Rname: rec.Rname,
      realOnly: rec.inReal && !rec.inSim, // sim contract has no such joint - flag it instead
                                          // of letting it look like an ordinary sim panel
    };
  });
}

function obsTermDims(contract) {
  const anames = contract.action_joint_names;
  let off = 0;
  return (contract.obs_layout || []).map((t) => {
    let dim;
    if (t.func === "builtin_sensor" || t.func === "projected_gravity_from_sensor") {
      const s = (contract.sensors || {})[t.params.sensor_name];
      dim = s ? s.dim : 3;
    } else if (t.func === "joint_pos_rel" || t.func === "joint_vel_rel") {
      const jn = t.joint_names || anames;
      dim = jn.length * Math.max(t.history_length || 1, 1);
    } else if (t.func === "last_action") {
      dim = anames.length;
    } else if (t.func === "generated_commands") {
      dim = 3;
    } else dim = 0;
    const out = { name: t.name, dim, offset: off };
    off += dim;
    return out;
  });
}

function displayVal(rad) { return S.unit === "deg" ? rad * RAD2DEG : rad; }
function internalVal(shown) { return S.unit === "deg" ? shown * DEG2RAD : shown; }
function unitSuffix() { return S.unit === "deg" ? "deg" : "rad"; }

/* ------------------------------------------------------------------ bootstrap */
async function loadContract() {
  const r = await api("GET", "/contract");
  S.contract = r.contract;
  S.jointKinds = jointKindsOf(S.contract.action_joint_names);
}

function wireUrl(path) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}${path}`;
}

function connectWs() {
  if (S.ws) { try { S.ws.close(); } catch (e) {} }
  const ws = new WebSocket(wireUrl("/ws/out?hz=50&types=JointState,Status,PolicyIO"));
  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.type === "JointState") onJointState(msg);
    else if (msg.type === "Status") { S.status = msg; }
    else if (msg.type === "PolicyIO") { S.policyio = msg; }
  };
  ws.onclose = () => { setTimeout(connectWs, 1000); };
  ws.onerror = () => { try { ws.close(); } catch (e) {} };
  S.ws = ws;
}

function zipNamed(names, arr) {
  const o = {};
  if (!arr) return o;
  names.forEach((n, i) => { o[n] = arr[i]; });
  return o;
}

function onJointState(msg) {
  if (msg.src === "real") {
    S.latestReal = {
      t: msg.t_ns / 1e9,
      q: zipNamed(msg.joint_names, msg.q),
      qd: zipNamed(msg.joint_names, msg.qd),
      tau: zipNamed(msg.joint_names, msg.tau_est),
      target: zipNamed(msg.joint_names, msg.target),
    };
    // A4 fix: remember every joint name ever seen on the real side, in first-seen order,
    // so buildPlotGrid() can give a panel to a real joint the sim contract doesn't know
    // about (see panelsFor()). This only ever grows; a real joint set is not expected to
    // change mid-session, and a stale leftover name here costs nothing (its series just
    // stops updating - a `-` in the modal - not a crash).
    (msg.joint_names || []).forEach((n) => {
      if (!S.realJointNames.includes(n)) S.realJointNames.push(n);
    });
    return;
  }
  S.joints = msg;
  const t = msg.t_ns / 1e9;
  const q = zipNamed(msg.joint_names, msg.q);
  const qd = zipNamed(msg.joint_names, msg.qd);
  const tau = zipNamed(msg.joint_names, msg.tau_est);
  const target = zipNamed(msg.joint_names, msg.target);
  const realAgeS = S.latestReal.t === null ? null : (t - S.latestReal.t);
  S.ring.push({
    t, q, qd, tau, target,
    realQ: S.latestReal.q, realQd: S.latestReal.qd, realTau: S.latestReal.tau, realTarget: S.latestReal.target,
    realAgeS,
    sentTarget: S.latestTxSent, // latest-only, from the 250ms /tx/status poll - see pollSlow
  });
  const cutoff = t - RING_MAX_S;
  while (S.ring.length && S.ring[0].t < cutoff) S.ring.shift();
}

/* ------------------------------------------------------------------ slow poll */
async function pollSlow() {
  try { S.snapshot = await api("GET", "/snapshot"); } catch (e) { /* transient */ }
  try {
    S.txStatus = await api("GET", "/tx/status");
    S.latestTxSent = S.txStatus.last_sent_target || {};
  } catch (e) { /* transient */ }
  try {
    if (S.rightTab === "gains") S.gains = await api("GET", "/gains");
  } catch (e) {}
  try {
    if (S.rightTab === "gains") S.presets = await api("GET", "/presets");
  } catch (e) {}
  try {
    if (S.controlMode === "policy" && S.rightTab === "control") S.policyList = await api("GET", "/policy/list");
  } catch (e) {}
  try {
    // A2: the full record list is only fetched while the panel is actually open - the
    // topbar badge itself reacts off the WS-delivered Status.telemetry.violations SUMMARY,
    // not this poll, so a closed panel costs nothing extra.
    if (S.violationPanelOpen) { S.violations = await api("GET", "/violations?limit=50"); renderViolationPanel(); }
  } catch (e) {}
  try {
    // Motor health: the per-joint grid only needs the Telemetry tab's own poll cadence -
    // the topbar LED/heartbeat react off the WS-delivered Status.telemetry.health SUMMARY.
    if (S.leftTab === "telemetry") { S.health = await api("GET", "/health"); renderHealthGrid(); }
  } catch (e) {}
}

/* ------------------------------------------------------------------ A2: violation panel */
function toggleViolationPanel() {
  S.violationPanelOpen = !S.violationPanelOpen;
  if (S.violationPanelOpen) {
    api("GET", "/violations?limit=50").then((v) => { S.violations = v; renderViolationPanel(); }).catch(() => {});
  } else {
    renderViolationPanel();
  }
}

function violationSideLabel(side) {
  return ({
    recv: "recv (received position)",
    recv_torque: "recv (received torque)",
    sim_actuator: "sim actuator (T-N saturated)",
    send: "send (to hardware)",
  })[side] || side;
}

function renderViolationPanel() {
  const panel = el("violation-panel");
  if (!panel) return;
  if (!S.violationPanelOpen) { panel.classList.remove("on"); return; }
  panel.classList.add("on");
  const v = S.violations || { records: [], by_joint: {}, total: 0 };
  const summaryRows = Object.entries(v.by_joint).map(([j, c]) => {
    const bySide = Object.entries(c).filter(([k]) => k !== "total").map(([k, n]) => `${k}:${n}`).join(" &middot; ");
    return `<tr><td>${j}</td><td>${c.total}</td><td class="small">${bySide}</td></tr>`;
  }).join("");
  const rows = v.records.slice().reverse().map((r) => {
    const val = (r.value === null || r.value === undefined) ? (r.rejected || "non-finite") : fmt(r.value, 4);
    const lim = (r.limit_lo === null || r.limit_lo === undefined || r.limit_hi === null || r.limit_hi === undefined)
      ? "-" : `[${fmt(r.limit_lo, 3)}, ${fmt(r.limit_hi, 3)}]`;
    const over = (r.over_by === null || r.over_by === undefined) ? "-" : fmt(r.over_by, 4);
    return `<tr data-joint="${r.joint}" data-side="${r.side}">
      <td>${fmt(r.age_s, 1)}s ago</td><td>${violationSideLabel(r.side)}</td><td>${r.joint}</td>
      <td>${val}</td><td>${lim}</td><td>${over}</td></tr>`;
  }).join("");
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <b style="color:#f88">&#9888; ROM / torque violations - ${v.total} total (all-time)</b>
      <div class="row" style="border:0;padding:0;gap:6px">
        <button id="viol-clear">clear</button>
        <button id="viol-close">close</button>
      </div>
    </div>
    <div class="small" style="margin-bottom:4px">per-joint cumulative (survives the record ring):</div>
    <table><thead><tr><th>joint</th><th>total</th><th>by side</th></tr></thead>
      <tbody>${summaryRows || '<tr><td colspan="3" class="small">none</td></tr>'}</tbody></table>
    <div class="small" style="margin-bottom:4px">most recent ${v.records.length} record(s) - click a row to highlight that joint's plot:</div>
    <table><thead><tr><th>when</th><th>side</th><th>joint</th><th>value</th><th>limit</th><th>over by</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6" class="small">none</td></tr>'}</tbody></table>
  `;
  el("viol-clear").onclick = async () => { await apiOk("POST", "/violations/clear"); S.violations = await api("GET", "/violations?limit=50"); renderViolationPanel(); };
  el("viol-close").onclick = () => { S.violationPanelOpen = false; renderViolationPanel(); };
  panel.querySelectorAll("tbody tr[data-joint]").forEach((tr) => {
    tr.addEventListener("click", () => {
      const joint = tr.dataset.joint;
      if (!joint || joint === "*" || joint === "?") return;
      const side = tr.dataset.side;
      const kind = jointNameParts(joint).kind;
      const row = (side === "sim_actuator" || side === "recv_torque") ? "tau" : "pos";
      if (S.plotPanels[kind]) openModal(row, kind);
      else toast(`no plot panel for ${joint} (${kind})`);
    });
  });
}

/* ------------------------------------------------------------------ tabs */
function initTabs() {
  el("left-tabs").addEventListener("click", (ev) => {
    const t = ev.target.closest(".tab");
    if (!t) return;
    document.querySelectorAll("#left-tabs .tab").forEach((x) => x.classList.remove("on"));
    t.classList.add("on");
    S.leftTab = t.dataset.tab;
    renderLeftTab();
  });
  el("right-tabs").addEventListener("click", (ev) => {
    const t = ev.target.closest(".tab");
    if (!t) return;
    document.querySelectorAll("#right-tabs .tab").forEach((x) => x.classList.remove("on"));
    t.classList.add("on");
    S.rightTab = t.dataset.tab;
    renderRightTab();
  });
}

/* ------------------------------------------------------------------ top bar */
function renderTopBar() {
  const st = S.status;
  el("pill-variant").textContent = S.contract ? S.contract.variant : "-";
  el("pill-mode").textContent = "mode: " + (st ? st.mode : "-");
  if (st) {
    let baseTxt = "base: " + st.base.mode;
    if (st.base.mode === "string" && st.string) {
      baseTxt += ` z=${fmt(st.string.z_set, 2)} ${st.string.taut ? "TAUT " + fmt(st.string.tension_N, 0) + "N" : "slack"}`;
    }
    el("pill-base").textContent = baseTxt;
  }
  el("pill-control").textContent = "panel: " + S.controlMode;

  const badges = [];
  if (st) {
    if (st.contract_stale) badges.push(`<span class="pill bad">contract STALE</span>`);
    if (st.side_mapping_verified === false) badges.push(`<span class="pill warn">side mapping UNVERIFIED</span>`);
    if (st.warnings && st.warnings.length) badges.push(`<span class="pill bad">${st.warnings.length} warning(s)</span>`);
    const tel = st.telemetry || {};
    if (tel.jitter_grey) badges.push(`<span class="pill warn">jitter &gt;15ms</span>`);
    // A2: red panel badge - Status.telemetry.violations is a SUMMARY (total/by_joint/last),
    // arriving at WS rate, so this reacts as fast as any other top-bar badge; the full
    // record list is only fetched (GET /violations) while the panel itself is open.
    const tv = tel.violations || {};
    if (tv.total) {
      badges.push(`<span class="pill bad" id="violation-badge" title="click for detail">&#9888; ${tv.total} ROM/torque violation(s)</span>`);
    }
  }
  el("topbar-badges").innerHTML = badges.join(" ");

  // Motor health: link LED (grey=never connected, red=stale, green=live) + a heartbeat dot
  // that flickers on every NEW rx_count since the last render - visually distinct from the
  // violations badge above (that one is a static red pill+table; this is a status LIGHT,
  // per item 5 of the task: "A2의 빨간 위반 패널과 시각적으로 구분").
  const healthEl = el("topbar-health");
  if (healthEl) {
    if (!st) {
      healthEl.innerHTML = "";
    } else {
      const tel = st.telemetry || {};
      const health = tel.health || {};
      const link = health.link || {};
      const summary = health.summary || {};
      const ledClass = !link.connected ? "led-none" : (tel.stale ? "led-dead" : "led-ok");
      const beat = (tel.rx_count !== undefined && tel.rx_count !== S.lastHealthRxCount);
      S.lastHealthRxCount = tel.rx_count;
      const beatClass = beat ? "heartbeat-on" : "heartbeat-off";
      const summaryTxt = link.connected
        ? `motors ${summary.ok || 0} ok / ${summary.warn || 0} warn / ${summary.dead || 0} dead`
        : "no real motor connected";
      healthEl.innerHTML =
        `<span class="led ${ledClass}"></span><span class="heartbeat-dot ${beatClass}"></span> ${summaryTxt}`;
    }
  }

  if (st) {
    const tel = st.telemetry || {};
    const rate = st.rates || {};
    let txt = `phys ${fmt(rate.phys_hz, 1)} Hz &middot; ctrl ${fmt(rate.ctrl_hz, 1)} Hz`;
    if (tel.rx_hz !== undefined && tel.rx_hz) {
      txt += ` &middot; rx ${fmt(tel.rx_hz, 1)}/s &middot; age ${fmt(tel.age_s, 2)}s &middot; offset ${fmt(tel.clock_offset_ms, 1)}ms`;
    }
    txt += ` &middot; RSS ${fmt(st.rss_mb, 0)} MB`;
    el("topbar-rates").innerHTML = txt;
  }
}

/* ------------------------------------------------------------------ main render loop (20 Hz) */
function renderTick() {
  renderTopBar();
  renderLeftTab();
  renderRightTab();
  renderPlots();
  if (S.modal) renderModalChart();
}

function boot() {
  document.title = "pygviewer";
  el("viser-frame").src = `http://${location.hostname}:8094`;
  initTabs();
  initPlotsToolbar();
  initModal();
  loadContract()
    .then(() => {
      renderLeftTab();
      renderRightTab();
      buildPlotGrid();
    })
    .catch((e) => toast("failed to load /contract: " + e.message));
  connectWs();
  // A2: event delegation, not a per-render listener - #topbar-badges' innerHTML is rebuilt
  // every renderTick (20 Hz), so a listener attached to the badge span itself would need
  // re-attaching every tick; the parent element is never replaced.
  el("topbar-badges").addEventListener("click", (ev) => {
    if (ev.target.closest("#violation-badge")) toggleViolationPanel();
  });
  setInterval(pollSlow, 250);
  setInterval(renderTick, 50); // 20 Hz
  pollSlow();
}

/* ================================================================== Left tabs */
function renderLeftTab() {
  const body = el("left-body");
  if (!S.contract) { body.innerHTML = `<div class="small">loading contract...</div>`; return; }
  switch (S.leftTab) {
    case "model": return renderTabModel(body);
    case "base": return renderTabBase(body);
    case "telemetry": return renderTabTelemetry(body);
    case "script": return renderTabScript(body);
    case "status": return renderTabStatus(body);
  }
}

function renderTabModel(body) {
  const c = S.contract;
  const st = S.status;
  body.innerHTML = `
    <h3>Variant</h3>
    <div class="row"><label>variant</label><span class="mono">${c.variant}</span></div>
    <div class="row"><label>ankle_mode</label><span class="mono">${c.ankle_mode}</span></div>
    <div class="row"><label>contract sha</label><span class="mono">${c.contract_sha.slice(0, 12)}</span></div>
    <div class="row"><label>stale</label><span>${st ? (st.contract_stale ? "STALE" : "fresh") : "-"}</span></div>
    <div class="small" style="margin:6px 0">This process owns one baked model for its whole
      life - switching variant means restarting <span class="mono">run.py --variant &lt;name&gt;</span>
      (docs/121 section 2). This dropdown is read-only for that reason.</div>
    <select disabled style="width:100%">
      ${["FullDoF-AB", "FullDoF-RP", "SemiFullDoF-AB", "SemiFullDoF-RP", "LegOnly-AB", "LegOnly-RP"]
        .map((v) => `<option ${v === c.variant ? "selected" : ""}>${v}</option>`).join("")}
    </select>
    <button id="btn-reload-contract" style="margin-top:8px;width:100%">reload contract + status</button>
  `;
  el("btn-reload-contract").onclick = async () => {
    await loadContract();
    toast("contract reloaded");
    buildPlotGrid();
  };
}

function renderTabBase(body) {
  const c = S.contract;
  const st = S.status;
  const base = st ? st.base : { mode: "fixed", ground: true, pivot_offset: [0, 0, 0], pos: [0, 0, 0] };
  const stringSt = st ? st.string : null;
  if (!body.dataset.built) {
    body.innerHTML = `
      <h3>Base mode</h3>
      <div class="seg" id="base-mode-seg">
        ${["free", "fixed", "pivot", "string"].map((m) => `<span data-m="${m}">${m}</span>`).join("")}
      </div>
      <div class="row"><label id="base-h-label">height [m]</label>
        <input type="range" id="base-height" min="0.3" max="1.3" step="0.005" style="flex:1;margin:0 8px">
        <span class="mono" id="base-height-val">-</span></div>
      <div class="row"><label>offset x/y/z [m]</label>
        <span><input class="num" id="off-x" type="number" step="0.005" style="width:56px">
        <input class="num" id="off-y" type="number" step="0.005" style="width:56px">
        <input class="num" id="off-z" type="number" step="0.005" style="width:56px"></span></div>
      <div class="row" id="row-followxy" style="display:none"><label>follow_xy</label>
        <input type="checkbox" id="follow-xy"></div>
      <div class="row"><label>ground</label><input type="checkbox" id="ground-cb"></div>
      <div class="row"><label>string tension</label><span class="mono" id="string-tension">-</span></div>
      <hr class="hr">
      <h3>Reset</h3>
      <div class="row"><button id="btn-reset-home" style="flex:1">home</button>
        <button id="btn-reset-bent" style="flex:1">knees_bent</button></div>
    `;
    body.dataset.built = "1";
    el("base-mode-seg").addEventListener("click", (ev) => {
      const s = ev.target.closest("span");
      if (!s) return;
      apiOk("POST", "/base", { mode: s.dataset.m });
    });
    el("base-height").addEventListener("input", (ev) => {
      const v = parseFloat(ev.target.value);
      const mode = (S.status || {}).base ? S.status.base.mode : "fixed";
      if (mode === "string") apiOk("POST", "/base", { z_set: v });
      else apiOk("POST", "/base", { height: v });
    });
    const pushOffset = () => {
      const xyz = [parseFloat(el("off-x").value) || 0, parseFloat(el("off-y").value) || 0, parseFloat(el("off-z").value) || 0];
      const mode = (S.status || {}).base ? S.status.base.mode : "fixed";
      if (mode === "string") apiOk("POST", "/base", { hook_offset: xyz });
      else apiOk("POST", "/base", { pivot_offset: xyz });
    };
    ["off-x", "off-y", "off-z"].forEach((id) => el(id).addEventListener("change", pushOffset));
    el("follow-xy").addEventListener("change", (ev) => apiOk("POST", "/base", { follow_xy: ev.target.checked }));
    el("ground-cb").addEventListener("change", (ev) => apiOk("POST", "/base", { ground: ev.target.checked }));
    el("btn-reset-home").onclick = () => apiOk("POST", "/reset", { keyframe: "home" });
    el("btn-reset-bent").onclick = () => apiOk("POST", "/reset", { keyframe: "knees_bent" });
  }
  document.querySelectorAll("#base-mode-seg span").forEach((s) => s.classList.toggle("on", s.dataset.m === base.mode));
  el("base-h-label").textContent = base.mode === "string" ? "z_set [m]" : "height [m]";
  if (document.activeElement !== el("base-height")) {
    el("base-height").value = base.mode === "string" && stringSt ? stringSt.z_set : base.pos[2];
  }
  el("base-height-val").textContent = fmt(el("base-height").value, 3);
  el("row-followxy").style.display = base.mode === "string" ? "" : "none";
  if (document.activeElement.tagName !== "INPUT" || !document.activeElement.id.startsWith("off-")) {
    const off = base.mode === "string" && stringSt ? stringSt.hook_offset : base.pivot_offset;
    if (off) { el("off-x").value = fmt(off[0], 3); el("off-y").value = fmt(off[1], 3); el("off-z").value = fmt(off[2], 3); }
  }
  if (document.activeElement !== el("follow-xy")) el("follow-xy").checked = !!(stringSt && stringSt.follow_xy);
  if (document.activeElement !== el("ground-cb")) el("ground-cb").checked = !!base.ground;
  el("string-tension").textContent = stringSt
    ? `${stringSt.taut ? "TAUT" : "slack"} ${fmt(stringSt.tension_N, 1)} N (z_set ${fmt(stringSt.z_set, 3)}, len ${fmt(stringSt.ten_length, 3)})`
    : "n/a (mode != string)";
}

function renderTabTelemetry(body) {
  const st = S.status;
  const tel = st ? (st.telemetry || {}) : {};
  if (!body.dataset.built) {
    body.innerHTML = `
      <div id="tel-banner"></div>
      <h3>Receive</h3>
      <div class="row"><label>rx rate</label><span class="mono" id="tel-rx">-</span></div>
      <div class="row"><label>age</label><span class="mono" id="tel-age">-</span></div>
      <div class="row"><label>clock offset</label><span class="mono" id="tel-off">-</span></div>
      <div class="row"><label>seq gaps</label><span class="mono" id="tel-gaps">-</span></div>
      <div class="row"><label>wrap/range/contract errs</label><span class="mono" id="tel-errs">-</span></div>
      <hr class="hr">
      <h3>Motor health</h3>
      <div class="row"><label>link</label><span class="mono" id="health-link">-</span></div>
      <div id="health-grid" class="health-grid"></div>
      <hr class="hr">
      <h3>Record</h3>
      <div class="row"><button id="btn-rec-start" style="flex:1">start</button>
        <button id="btn-rec-stop" style="flex:1">stop</button></div>
      <div class="small" id="rec-status"></div>
      <hr class="hr">
      <h3>Replay</h3>
      <input id="replay-path" placeholder="/path/to/recording.jsonl.gz" style="width:100%;margin-bottom:4px">
      <div class="row"><button id="btn-replay-load" style="flex:1">load</button>
        <button id="btn-replay-go" style="flex:1">mode: file_replay</button></div>
      <div class="row"><label>speed</label><input id="replay-speed" type="number" value="1.0" step="0.1" style="width:70px"></div>
      <hr class="hr">
      ${renderTxSectionHtml()}
    `;
    body.dataset.built = "1";
    el("btn-rec-start").onclick = async () => { const r = await apiOk("POST", "/record/start", {}); if (r) el("rec-status").textContent = "recording -> " + r.path; };
    el("btn-rec-stop").onclick = async () => { const r = await apiOk("POST", "/record/stop"); if (r) el("rec-status").textContent = `stopped: ${r.path} (${r.n_lines || r.n_lines === 0 ? r.n_lines : "?"} lines)`; };
    el("btn-replay-load").onclick = async () => { const r = await apiOk("POST", "/replay/load", { path: el("replay-path").value }); if (r) toast(`loaded ${r.n_rows} rows, ${fmt(r.duration_s, 1)}s`); };
    el("btn-replay-go").onclick = () => apiOk("POST", "/mode", { mode: "file_replay" });
    el("replay-speed").addEventListener("change", (ev) => apiOk("POST", "/replay/speed", { speed: parseFloat(ev.target.value) || 1.0 }));
    wireTxSection();
  }
  renderTxStatusLive();
  const banner = el("tel-banner");
  if (st && st.side_mapping_verified === false) {
    banner.innerHTML = `<div class="warnbanner">side mapping UNVERIFIED (protocol steps 2/3 not run on hardware yet) - see docs/121 section 5</div>`;
  } else if (st && st.side_mapping_verified === true) {
    banner.innerHTML = `<div class="okbanner">side mapping verified</div>`;
  } else banner.innerHTML = "";
  el("tel-rx").textContent = tel.rx_hz !== undefined ? `${fmt(tel.rx_hz, 1)}/s (${tel.rx_count || 0} total)` : "-";
  el("tel-age").textContent = tel.age_s !== undefined && tel.age_s !== null ? `${fmt(tel.age_s, 3)}s ${tel.stale ? "(STALE)" : ""}` : "no data yet";
  el("tel-off").textContent = tel.clock_offset_ms !== undefined && tel.clock_offset_ms !== null
    ? `${fmt(tel.clock_offset_ms, 1)}ms +/- ${fmt(tel.clock_jitter_ms, 1)}ms ${tel.jitter_grey ? "(jitter high)" : ""}` : "-";
  el("tel-gaps").textContent = tel.seq_gaps !== undefined ? tel.seq_gaps : "-";
  el("tel-errs").textContent = `wrap ${tel.wrap_events || 0} / range ${Object.keys(tel.range_violations || {}).length} / contract ${tel.contract_mismatches || 0}`;
  renderHealthGrid();
}

/* ---------------------------------------------------------------- motor health grid */
function renderHealthGrid() {
  const linkEl = el("health-link");
  const gridEl = el("health-grid");
  if (!linkEl || !gridEl) return;
  const h = S.health;
  if (!h) {
    linkEl.textContent = "-";
    gridEl.innerHTML = `<div class="small">waiting for /health...</div>`;
    return;
  }
  const link = h.link || {};
  linkEl.textContent = link.connected
    ? `connected - rx ${fmt(link.rx_hz, 1)}/s, age ${fmt(link.age_s, 2)}s, seq_gaps ${link.seq_gaps || 0}`
    : "no real telemetry ever received";
  const joints = h.joints || {};
  const names = S.contract ? S.contract.action_joint_names : Object.keys(joints);
  gridEl.innerHTML = names.map((n) => {
    const j = joints[n] || { state: "dead", diag: false };
    const bits = [];
    bits.push(`age ${j.age_s === null || j.age_s === undefined ? "never" : fmt(j.age_s, 2) + "s"}`);
    if (j.diag) {
      bits.push(`motor_age ${j.motor_age_ms === null || j.motor_age_ms === undefined ? "-" : fmt(j.motor_age_ms, 0) + "ms"}`);
      bits.push(`ack ${j.ack === null || j.ack === undefined ? "-" : j.ack}`);
      bits.push(`miss ${j.miss === null || j.miss === undefined ? "-" : j.miss}`);
      bits.push(`temp ${j.temp_c === null || j.temp_c === undefined ? "-" : fmt(j.temp_c, 1) + "C"}`);
    } else {
      bits.push("no diag data (reception recency only)");
    }
    bits.push(`q ${j.q === null || j.q === undefined ? "-" : fmt(displayVal(j.q), 1) + unitSuffix()}`);
    const title = `${n}: ${j.state}\n${bits.join("\n")}`;
    return `<div class="health-cell health-${j.state}" title="${title}">${n.replace(/_joint$/, "")}</div>`;
  }).join("");
}

function renderTabScript(body) {
  if (!body.dataset.built) {
    body.innerHTML = `
      <h3>Target-q script player</h3>
      <select id="script-path" style="width:100%;margin-bottom:6px">
        <option value="tools/pygviewer/scripts/sine_hips_knees_1hz_20deg.json">sine_hips_knees_1hz_20deg.json</option>
        <option value="tools/pygviewer/scripts/step_knee_5x10deg.json">step_knee_5x10deg.json</option>
      </select>
      <input id="script-runid" placeholder="run_id (optional)" style="width:100%;margin-bottom:6px">
      <div class="row"><button id="btn-script-run" style="flex:1">run</button>
        <button id="btn-script-stop" style="flex:1">stop</button></div>
      <div class="small" id="script-status"></div>
    `;
    body.dataset.built = "1";
    el("btn-script-run").onclick = async () => {
      const r = await apiOk("POST", "/script/run", { path: el("script-path").value, run_id: el("script-runid").value || null });
      if (r) toast(`running ${r.run_id} (${fmt(r.duration_s, 1)}s)`);
    };
    el("btn-script-stop").onclick = () => apiOk("POST", "/script/stop");
  }
  const tel = S.status ? (S.status.telemetry || {}) : {};
  const sc = tel.script;
  el("script-status").textContent = sc
    ? `running: t=${fmt(sc.t, 2)}/${fmt(sc.duration_s, 2)}s`
    : (S.joints && S.joints.run_id ? `last run_id: ${S.joints.run_id}` : "idle");
}

function renderTabStatus(body) {
  const st = S.status;
  if (!st) { body.innerHTML = `<div class="small">waiting for /ws/out...</div>`; return; }
  const rates = st.rates || {};
  body.innerHTML = `
    <h3>Rates</h3>
    <div class="row"><label>physics</label><span class="mono">${fmt(rates.phys_hz, 1)} Hz</span></div>
    <div class="row"><label>control</label><span class="mono">${fmt(rates.ctrl_hz, 1)} Hz</span></div>
    <div class="row"><label>drops</label><span class="mono">${rates.drops}</span></div>
    <div class="row"><label>phys steps</label><span class="mono">${rates.phys_steps}</span></div>
    <div class="row"><label>sim time</label><span class="mono">${fmt(st.sim_time_s, 1)} s</span></div>
    <hr class="hr">
    <h3>Process</h3>
    <div class="row"><label>RSS</label><span class="mono">${fmt(st.rss_mb, 1)} MB</span></div>
    <div class="row"><label>contract</label><span class="mono">${st.contract_stale ? "STALE" : "fresh"}</span></div>
    <hr class="hr">
    <h3>Warnings</h3>
    <div class="small">${(st.warnings && st.warnings.length) ? st.warnings.map((w) => `&bull; ${w}`).join("<br>") : "none"}</div>
  `;
}

/* ================================================================== Right tab: Control */
function renderRightTab() {
  const body = el("right-body");
  if (!S.contract) return;
  switch (S.rightTab) {
    case "control": return renderTabControl(body);
    case "gains": return renderTabGains(body);
    case "obs": return renderTabObs(body);
  }
}

/* Joints <-> Policy is a mutually-exclusive sub-toggle inside Control (design item 4):
   switching TO Joints stops a running policy (-> manual); switching TO Policy resumes it
   (-> policy_sim) if one is loaded. Both live under one right-hand "Control" tab per the
   layout-B decision (docs/121 section 10). */
async function setControlMode(mode) {
  if (mode === S.controlMode) return;
  S.controlMode = mode;
  if (mode === "joints") {
    if (S.status && S.status.mode && S.status.mode.startsWith("policy")) {
      await apiOk("POST", "/mode", { mode: "manual" });
    }
  } else if (mode === "policy") {
    if (S.policyLoadedName && S.status && (S.status.mode === "manual" || S.status.mode === "idle")) {
      await apiOk("POST", "/mode", { mode: "policy_sim" });
    }
  }
  renderTabControl(el("right-body"), true);
}

function renderTabControl(body, force) {
  if (!body.dataset.builtControl || force) {
    body.innerHTML = `
      <div class="row tight">
        <span class="seg" id="control-mode-seg">
          <span data-m="joints">Joints</span><span data-m="policy">Policy</span>
        </span>
        <span class="seg" id="unit-seg"><span data-u="deg">deg</span><span data-u="rad">rad</span></span>
      </div>
      <div id="control-sub"></div>
    `;
    body.dataset.builtControl = "1";
    el("control-mode-seg").addEventListener("click", (ev) => {
      const s = ev.target.closest("span"); if (!s) return;
      setControlMode(s.dataset.m);
    });
    el("unit-seg").addEventListener("click", (ev) => {
      const s = ev.target.closest("span"); if (!s) return;
      S.unit = s.dataset.u;
      renderJointsPanel(el("control-sub"), true);
    });
  }
  document.querySelectorAll("#control-mode-seg span").forEach((s) => s.classList.toggle("on", s.dataset.m === S.controlMode));
  document.querySelectorAll("#unit-seg span").forEach((s) => s.classList.toggle("on", s.dataset.u === S.unit));
  const sub = el("control-sub");
  if (S.controlMode === "joints") renderJointsPanel(sub);
  else renderPolicyPanel(sub);
}

/* ---------------------------------------------------------------- Joints (item 2) */
function renderJointsPanel(sub, force) {
  const c = S.contract;
  if (!sub.dataset.builtJoints || force) {
    const rows = c.action_joint_names.map((n) => {
      const jc = c.joint_contract[n] || {};
      const mirrorNote = jc.mirrored ? ` <span class="phys" title="physical angle = travel_sign*q, matches the twin leg">phys</span>` : "";
      return `
      <div class="joint-row" data-n="${n}">
        <span class="name" title="${n}">${n.replace("_joint", "")}${mirrorNote}</span>
        <input type="range" class="slider" step="0.001">
        <input type="number" class="num" step="0.001">
        <span class="phys mono" title="physical angle (mirrored joints only)"></span>
        <input type="checkbox" class="tx-cb" disabled title="read-only mirror of the Telemetry tab's TX enable list - toggle it there">
      </div>`;
    }).join("");
    sub.innerHTML = `
      <div class="small" style="margin:4px 0">Slider range = contract safe_clip. "phys" on a
        mirrored joint is travel_sign&times;q, so both legs read alike. TX checkboxes mirror
        the Telemetry tab's TX enable list (read-only here - configure it there).</div>
      ${rows}
      <button id="btn-joints-home" style="width:100%;margin-top:6px">targets -&gt; default pose</button>
      ${renderAnkleFootSpaceHtml(c)}
    `;
    sub.dataset.builtJoints = "1";
    c.action_joint_names.forEach((n) => {
      const row = sub.querySelector(`.joint-row[data-n="${n}"]`);
      const lo = c.safe_clip[n] ? c.safe_clip[n][0] : c.joint_contract[n].range[0];
      const hi = c.safe_clip[n] ? c.safe_clip[n][1] : c.joint_contract[n].range[1];
      const slider = row.querySelector(".slider");
      const num = row.querySelector(".num");
      slider.min = displayVal(lo); slider.max = displayVal(hi);
      slider.step = S.unit === "deg" ? 0.1 : 0.001;
      num.step = slider.step;
      let guard = false;
      const push = (shownVal) => {
        if (guard) return;
        const rad = clamp(internalVal(shownVal), lo, hi);
        guard = true; slider.value = displayVal(rad); num.value = displayVal(rad).toFixed(S.unit === "deg" ? 1 : 3); guard = false;
        apiOk("POST", "/target", { values: { [n]: rad } });
      };
      slider.addEventListener("input", () => push(parseFloat(slider.value)));
      num.addEventListener("change", () => push(parseFloat(num.value)));
    });
    el("btn-joints-home").onclick = () => {
      const values = {};
      c.action_joint_names.forEach((n) => { values[n] = c.default_q[n]; });
      apiOk("POST", "/target", { values });
    };
    wireAnkleFootSpace(sub, c);
  }
  // live readout refresh (does not fight an in-progress drag: skip the focused control)
  const q = S.joints ? zipNamed2(S.joints.joint_names, S.joints.q) : {};
  c.action_joint_names.forEach((n) => {
    const row = sub.querySelector(`.joint-row[data-n="${n}"]`);
    if (!row) return;
    const slider = row.querySelector(".slider"), num = row.querySelector(".num"), phys = row.querySelector(".phys");
    const target = c.default_q[n];
    const cur = q[n];
    if (document.activeElement !== slider && document.activeElement !== num) {
      const showTarget = S.joints ? zipNamed2(S.joints.joint_names, S.joints.target)[n] : target;
      slider.value = displayVal(showTarget); num.value = displayVal(showTarget).toFixed(S.unit === "deg" ? 1 : 3);
    }
    const jc = c.joint_contract[n] || {};
    if (jc.mirrored && cur !== undefined) phys.textContent = displayVal(jc.travel_sign * cur).toFixed(1);
    else phys.textContent = cur !== undefined ? displayVal(cur).toFixed(1) : "";
    const txCb = row.querySelector(".tx-cb");
    if (txCb) txCb.checked = !!(S.txStatus && (S.txStatus.enable || []).includes(n));
  });
}

function zipNamed2(names, arr) { const o = {}; if (!arr) return o; names.forEach((n, i) => { o[n] = arr[i]; }); return o; }

function renderAnkleFootSpaceHtml(c) {
  if (!c.ankle_inverse) return "";
  const meta = c.ankle_inverse;
  const pLo = Math.min(...meta.pitch_deg), pHi = Math.max(...meta.pitch_deg);
  const rLo = Math.min(...meta.roll_deg), rHi = Math.max(...meta.roll_deg);
  return `
    <hr class="hr">
    <h3>Ankle foot-space (AB) - method ${meta.method}, worst residual ${meta.worst_residual_rad} rad</h3>
    ${["L", "R"].map((s) => `
      <div class="row tight"><label>${s} pitch [deg]</label>
        <input type="range" class="ankle-slider" data-side="${s}" data-axis="pitch" min="${pLo}" max="${pHi}" step="0.5" value="0" style="flex:1;margin:0 8px">
        <span class="mono ankle-val" data-side="${s}" data-axis="pitch">0.0</span></div>
      <div class="row tight"><label>${s} roll [deg]</label>
        <input type="range" class="ankle-slider" data-side="${s}" data-axis="roll" min="${rLo}" max="${rHi}" step="0.5" value="0" style="flex:1;margin:0 8px">
        <span class="mono ankle-val" data-side="${s}" data-axis="roll">0.0</span></div>
    `).join("")}
  `;
}

function wireAnkleFootSpace(sub, c) {
  if (!c.ankle_inverse) return;
  const state = { L: { pitch: 0, roll: 0 }, R: { pitch: 0, roll: 0 } };
  sub.querySelectorAll(".ankle-slider").forEach((sl) => {
    sl.addEventListener("input", () => {
      const side = sl.dataset.side, axis = sl.dataset.axis;
      state[side][axis] = parseFloat(sl.value);
      sub.querySelector(`.ankle-val[data-side="${side}"][data-axis="${axis}"]`).textContent = fmt(sl.value, 1);
      apiOk("POST", "/ankle", { side, pitch: state[side].pitch * DEG2RAD, roll: state[side].roll * DEG2RAD });
    });
  });
}

/* ---------------------------------------------------------------- Policy (item 4) */
// PURE (no DOM, no fetch): given the name that was being loaded and whatever `api()` threw,
// produce the text an operator should see. Split out so the "does a failure reason survive
// as visible text" behaviour is testable without a browser - see this file's sibling
// docs/121 section 10 note and tests/test_policy_ui_contract.py for the backend half of the
// contract this depends on (POST /policy/load's error body is always {"detail": "<string>"}).
function policyLoadErrorText(name, err) {
  const label = name ? `'${name}'` : "policy";
  const detail = err && err.message ? err.message : String(err || "unknown error");
  return `failed to load ${label}: ${detail}`;
}

async function loadAndRunPolicy(name) {
  try {
    const r = await api("POST", "/policy/load", { name });
    S.policyLoadedName = name;
    S.policyLayoutDims = r.layout || null; // server's own builder.describe() - authoritative
    await api("POST", "/policy/cmd", { vx: 0, vy: 0, wz: 0 });
    await api("POST", "/mode", { mode: "policy_sim" });
    toast(`loaded ${name}, running policy_sim at cmd=0`);
    renderTabControl(el("right-body"), true);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: policyLoadErrorText(name, err) };
  }
}

async function loadAndRunPolicyByPath(path) {
  const body = path.trim().endsWith(".pt") ? { pt: path.trim() } : { onnx: path.trim() };
  try {
    const r = await api("POST", "/policy/load", body);
    S.policyLoadedName = path.trim();
    S.policyLayoutDims = r.layout || null;
    await api("POST", "/policy/cmd", { vx: 0, vy: 0, wz: 0 });
    await api("POST", "/mode", { mode: "policy_sim" });
    toast(`loaded ${path}, running policy_sim at cmd=0`);
    renderTabControl(el("right-body"), true);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: policyLoadErrorText(path, err) };
  }
}

function renderPolicyPanel(sub) {
  const st = S.status;
  const snapPolicy = (S.snapshot || {}).policy;
  if (!sub.dataset.builtPolicy) {
    sub.innerHTML = `
      <div class="row tight">
        <label>policy</label>
        <select id="pol-select" style="flex:1;min-width:0;text-overflow:ellipsis;overflow:hidden;white-space:nowrap"></select>
        <button id="btn-pol-refresh" title="refresh the baked-policy list">&#8635;</button>
      </div>
      <button id="btn-pol-load-run" class="primary" style="width:100%;margin:6px 0">Load &amp; Run</button>
      <div class="small" id="pol-load-error" style="color:var(--bad);display:none;margin-bottom:6px"></div>
      <div class="row tight"><label>status</label><span class="mono" id="pol-loaded-badge">none</span></div>
      <div class="row"><label>mode</label>
        <span class="seg" id="pol-mode-seg"><span data-m="policy_sim">policy_sim</span><span data-m="policy_shadow">policy_shadow</span></span></div>
      <div class="row"><label>shadow_follow</label><input type="checkbox" id="pol-shadow-follow"></div>
      <div class="row"><label>vx [m/s]</label><input type="range" id="pol-vx" min="-1" max="1" step="0.02" style="flex:1;margin:0 8px"><span class="mono" id="pol-vx-v">0</span></div>
      <div class="row"><label>vy [m/s]</label><input type="range" id="pol-vy" min="-0.5" max="0.5" step="0.02" style="flex:1;margin:0 8px"><span class="mono" id="pol-vy-v">0</span></div>
      <div class="row"><label>wz [rad/s]</label><input type="range" id="pol-wz" min="-1" max="1" step="0.02" style="flex:1;margin:0 8px"><span class="mono" id="pol-wz-v">0</span></div>
      <div class="row tight"><button id="btn-pol-runstop" style="flex:1">Run</button>
        <button id="btn-pol-unload" style="flex:1">Unload</button></div>
      <details style="margin-top:6px">
        <summary class="small" style="cursor:pointer">advanced: load by file path</summary>
        <div class="row tight" style="margin-top:4px">
          <input id="pol-path" placeholder="/path/to/policy.onnx or .pt" style="flex:1;min-width:0">
          <button id="btn-pol-load-path">Load path</button>
        </div>
      </details>
      <hr class="hr">
      <h3>Obs source (per term)</h3>
      <div id="pol-obs-src"></div>
      <div id="pol-src-strip" class="obsbars" style="margin-top:6px"></div>
      <div class="small" id="pol-warn"></div>
    `;
    sub.dataset.builtPolicy = "1";

    function setLoadBusy(busy) {
      const b = el("btn-pol-load-run");
      b.disabled = busy;
      b.textContent = busy ? "loading..." : "Load & Run";
    }
    function showLoadError(text) {
      const e = el("pol-load-error");
      e.textContent = text;
      e.style.display = text ? "block" : "none";
    }

    el("btn-pol-refresh").onclick = async () => {
      try { S.policyList = await api("GET", "/policy/list"); } catch (e) { toast(e.message); }
    };
    el("btn-pol-load-run").onclick = async () => {
      const n = el("pol-select").value;
      if (!n) { showLoadError("no baked policy selected"); return; }
      showLoadError("");
      setLoadBusy(true);
      const res = await loadAndRunPolicy(n);
      setLoadBusy(false);
      if (!res.ok) { showLoadError(res.error); toast(res.error); }
    };
    el("btn-pol-load-path").onclick = async () => {
      const p = el("pol-path").value;
      if (!p.trim()) { showLoadError("enter a .onnx or .pt path first"); return; }
      showLoadError("");
      setLoadBusy(true);
      const res = await loadAndRunPolicyByPath(p);
      setLoadBusy(false);
      if (!res.ok) { showLoadError(res.error); toast(res.error); }
    };
    el("pol-mode-seg").addEventListener("click", (ev) => {
      const s = ev.target.closest("span"); if (!s) return;
      apiOk("POST", "/mode", { mode: s.dataset.m });
    });
    el("pol-shadow-follow").addEventListener("change", (ev) => apiOk("POST", "/policy/shadow_follow", { enabled: ev.target.checked }));
    ["vx", "vy", "wz"].forEach((k) => {
      el("pol-" + k).addEventListener("input", () => {
        el(`pol-${k}-v`).textContent = fmt(el("pol-" + k).value, 2);
        apiOk("POST", "/policy/cmd", {
          vx: parseFloat(el("pol-vx").value) || 0, vy: parseFloat(el("pol-vy").value) || 0, wz: parseFloat(el("pol-wz").value) || 0,
        });
      });
    });
    el("btn-pol-runstop").onclick = () => {
      const running = st && (st.mode === "policy_sim" || st.mode === "policy_shadow");
      apiOk("POST", "/mode", { mode: running ? "idle" : "policy_sim" });
    };
    el("btn-pol-unload").onclick = async () => {
      await apiOk("POST", "/policy/unload"); S.policyLoadedName = null; renderTabControl(el("right-body"), true);
    };
  }
  const sel = el("pol-select");
  const names = (S.policyList || []).map((p) => p.name);
  if (sel.dataset.rendered !== JSON.stringify(names)) {
    sel.innerHTML = (S.policyList || []).map((p) => `<option value="${p.name}" title="${p.name}" ${p.compatible ? "" : "disabled"}>${p.name}${p.compatible ? "" : " (incompatible)"}</option>`).join("") || `<option disabled>no baked policies found</option>`;
    sel.dataset.rendered = JSON.stringify(names);
  }
  if (sel.selectedIndex >= 0 && sel.options[sel.selectedIndex]) sel.title = sel.options[sel.selectedIndex].title;
  document.querySelectorAll("#pol-mode-seg span").forEach((s) => s.classList.toggle("on", st && st.mode === s.dataset.m));
  const loaded = !!snapPolicy;
  const running = loaded && st && (st.mode === "policy_sim" || st.mode === "policy_shadow");
  el("pol-loaded-badge").textContent = loaded
    ? `loaded: ${snapPolicy.name || S.policyLoadedName || "?"} (${snapPolicy.kind === "torch" ? "pt" : (snapPolicy.kind || "?")})`
    : "none";
  el("btn-pol-runstop").disabled = !loaded;
  el("btn-pol-runstop").textContent = running ? "Stop (idle)" : "Run";
  el("btn-pol-unload").disabled = !loaded;
  document.querySelectorAll("#pol-mode-seg span").forEach((s) => { s.style.pointerEvents = loaded ? "" : "none"; s.style.opacity = loaded ? "" : "0.4"; });
  if (snapPolicy) {
    if (document.activeElement !== el("pol-shadow-follow")) el("pol-shadow-follow").checked = !!snapPolicy.shadow_follow;
    if (document.activeElement !== el("pol-vx")) { el("pol-vx").value = snapPolicy.cmd[0]; el("pol-vx-v").textContent = fmt(snapPolicy.cmd[0], 2); }
    if (document.activeElement !== el("pol-vy")) { el("pol-vy").value = snapPolicy.cmd[1]; el("pol-vy-v").textContent = fmt(snapPolicy.cmd[1], 2); }
    if (document.activeElement !== el("pol-wz")) { el("pol-wz").value = snapPolicy.cmd[2]; el("pol-wz-v").textContent = fmt(snapPolicy.cmd[2], 2); }
    renderObsSourceControls(el("pol-obs-src"), snapPolicy);
    renderObsSourceStrip(el("pol-src-strip"), snapPolicy);
    el("pol-warn").innerHTML = (snapPolicy.shadow_warnings || []).map((w) => `&bull; ${w}`).join("<br>");
  }
}

function renderObsSourceControls(container, snapPolicy) {
  const terms = Object.keys(snapPolicy.obs_sources || {});
  if (container.dataset.terms !== terms.join(",")) {
    container.innerHTML = terms.map((t) => `
      <div class="row tight"><label>${t}</label>
        <select data-term="${t}" class="obs-src-sel"><option value="sim">sim</option><option value="real">real</option></select></div>
    `).join("");
    container.dataset.terms = terms.join(",");
    container.querySelectorAll(".obs-src-sel").forEach((sel) => {
      sel.addEventListener("change", () => apiOk("POST", "/obs_source", { sources: { [sel.dataset.term]: sel.value } }));
    });
  }
  terms.forEach((t) => {
    const sel = container.querySelector(`.obs-src-sel[data-term="${t}"]`);
    if (sel && document.activeElement !== sel) sel.value = snapPolicy.obs_sources[t];
  });
}

function renderObsSourceStrip(container, snapPolicy) {
  const terms = Object.keys(snapPolicy.obs_sources_effective || snapPolicy.obs_sources || {});
  const req = snapPolicy.obs_sources || {};
  const eff = snapPolicy.obs_sources_effective || req;
  container.innerHTML = terms.map((t) => {
    const wanted = req[t], got = eff[t];
    const cls = wanted === "real" && got !== "real" ? "fallback" : (got === "real" ? "real" : "");
    return `<i class="${cls}" title="${t}: wanted ${wanted}, effective ${got}" style="height:${got === "real" ? 34 : 18}px"></i>`;
  }).join("");
}

/* ================================================================== Right tab: Gains (item 5) */
function renderTabGains(body) {
  const c = S.contract;
  if (!body.dataset.builtGains) {
    body.innerHTML = `
      <div class="row tight">
        <label>preset</label>
        <select id="gains-preset-sel" style="flex:1"></select>
        <button id="btn-preset-apply">apply</button>
      </div>
      <div class="row tight">
        <input id="gains-preset-name" placeholder="save current as..." style="flex:1">
        <button id="btn-preset-save">save</button>
      </div>
      <div style="overflow-x:auto"><table class="gains" id="gains-table"><thead><tr>
        <th>joint</th><th>motor</th><th>kp</th><th>kd</th><th>real kp</th><th>real kd</th>
      </tr></thead><tbody></tbody></table></div>
    `;
    body.dataset.builtGains = "1";
    el("btn-preset-apply").onclick = async () => {
      const name = el("gains-preset-sel").value;
      if (!name) return;
      const r = await apiOk("POST", "/presets/apply", { name });
      if (r) { S.gains = { source: r.source, gains: r.gains }; toast(`applied preset ${name}`); renderGainsTable(); }
    };
    el("btn-preset-save").onclick = async () => {
      const name = el("gains-preset-name").value.trim();
      if (!name || !S.gains) return;
      const gains = {};
      Object.entries(S.gains.gains).forEach(([n, g]) => { gains[n] = { kp: g.kp, kd: g.kd }; });
      const r = await apiOk("POST", "/presets", { name, gains });
      if (r) { toast(`saved preset '${name}'`); S.presets = await api("GET", "/presets"); renderPresetSelect(); }
    };
  }
  renderPresetSelect();
  renderGainsTable();
}

function renderPresetSelect() {
  const sel = el("gains-preset-sel");
  if (!sel) return;
  const presets = S.presets || { builtin: { train: "", real: "" }, custom: [] };
  const opts = [
    `<option value="train">train</option>`,
    `<option value="real">real (HUPHY kp=10/kd=1)</option>`,
    ...(presets.custom || []).map((p) => `<option value="${p.name}">${p.name}</option>`),
  ];
  const key = opts.join("|");
  if (sel.dataset.rendered !== key) { sel.innerHTML = opts.join(""); sel.dataset.rendered = key; }
}

function renderGainsTable() {
  const tbody = document.querySelector("#gains-table tbody");
  if (!tbody || !S.gains) return;
  const rows = Object.entries(S.gains.gains);
  if (tbody.dataset.n !== String(rows.length) || tbody.dataset.blank === "1") {
    tbody.innerHTML = rows.map(([n, g]) => `
      <tr data-n="${n}">
        <td>${n.replace("_joint", "")}</td><td>${g.motor || "-"}</td>
        <td><input type="number" class="gkp" step="1" style="width:60px"></td>
        <td><input type="number" class="gkd" step="0.1" style="width:60px"></td>
        <td class="grkp">-</td><td class="grkd">-</td>
      </tr>`).join("");
    tbody.dataset.n = String(rows.length);
    tbody.dataset.blank = "0";
    tbody.querySelectorAll("tr").forEach((tr) => {
      const n = tr.dataset.n;
      const push = () => {
        const kp = parseFloat(tr.querySelector(".gkp").value);
        const kd = parseFloat(tr.querySelector(".gkd").value);
        if (Number.isNaN(kp) || Number.isNaN(kd)) return;
        apiOk("POST", "/gains", { overrides: { [n]: { kp, kd } } }).then(() => { pollSlow(); });
      };
      tr.querySelector(".gkp").addEventListener("change", push);
      tr.querySelector(".gkd").addEventListener("change", push);
    });
  }
  rows.forEach(([n, g]) => {
    const tr = tbody.querySelector(`tr[data-n="${n}"]`);
    if (!tr) return;
    const kpEl = tr.querySelector(".gkp"), kdEl = tr.querySelector(".gkd");
    if (document.activeElement !== kpEl) kpEl.value = fmt(g.kp, 2);
    if (document.activeElement !== kdEl) kdEl.value = fmt(g.kd, 2);
    const rkp = tr.querySelector(".grkp"), rkd = tr.querySelector(".grkd");
    rkp.textContent = g.real_kp !== undefined ? fmt(g.real_kp, 2) : "-";
    rkp.className = "grkp" + (g.real_flag_kp ? " flag" : "");
    rkd.textContent = g.real_kd !== undefined ? fmt(g.real_kd, 2) : "-";
    rkd.className = "grkd" + (g.real_flag_kd ? " flag" : "");
  });
}

/* ================================================================== Right tab: Obs (item 3) */
let imu3d = null;

function renderTabObs(body) {
  if (!body.dataset.builtObs) {
    body.innerHTML = `<div id="obs-terms"></div>
      <h3 style="margin-top:10px">IMU (body frame)</h3>
      <div class="small">solid = sim, translucent = real (when connected). Red/green/blue =
        X/Y/Z body axes, yellow = projected gravity, cyan = gyro (scaled).</div>
      <div id="imu3d"></div>
      <div class="imu-legend" id="imu-legend"></div>`;
    body.dataset.builtObs = "1";
    imu3d = initImu3D(el("imu3d"));
  }
  const snapPolicy = (S.snapshot || {}).policy;
  const termsEl = el("obs-terms");
  if (!snapPolicy || !S.policyio) {
    termsEl.innerHTML = `<div class="small">no policy loaded - load one in the Policy panel to see the raw observation.</div>`;
  } else {
    renderObsBars(termsEl, snapPolicy);
  }
  updateImu3D();
}

function renderObsBars(container, snapPolicy) {
  const dims = S.policyLayoutDims || obsTermDims(S.contract);
  const obs = (S.policyio && S.policyio.obs) || [];
  const eff = snapPolicy.obs_sources_effective || snapPolicy.obs_sources || {};
  const req = snapPolicy.obs_sources || {};
  const key = dims.map((d) => d.name + d.dim).join(",");
  if (container.dataset.dims !== key) {
    container.innerHTML = dims.map((d) => `
      <div class="obsterm" data-term="${d.name}">
        <div class="lbl"><span>${d.name} (${d.dim})</span><span class="src-lbl"></span></div>
        <div class="obsbars">${Array.from({ length: d.dim }, () => "<i></i>").join("")}</div>
      </div>`).join("");
    container.dataset.dims = key;
  }
  dims.forEach((d) => {
    const wrap = container.querySelector(`.obsterm[data-term="${d.name}"]`);
    if (!wrap) return;
    const wanted = req[d.name], got = eff[d.name];
    const cls = wanted === "real" && got !== "real" ? "fallback" : (got === "real" ? "real" : "");
    wrap.querySelector(".src-lbl").textContent = wanted === "real" && got !== "real" ? "real -> fallback sim" : got;
    const bars = wrap.querySelectorAll(".obsbars i");
    for (let i = 0; i < d.dim; i++) {
      const v = obs[d.offset + i] || 0;
      const h = clamp(8 + Math.abs(v) * 12, 4, 34);
      const bar = bars[i];
      if (!bar) continue;
      bar.style.height = h + "px";
      bar.className = cls;
      bar.title = `${d.name}[${i}] = ${fmt(v, 3)}`;
    }
  });
}

/* -------------------------------------------------------- IMU 3D widget (three.js) */
function initImu3D(container) {
  const w = container.clientWidth || 300, h = 200;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(w, h);
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, w / h, 0.01, 100);
  // Robot/world frame is Z-UP (X forward, Y left) - the same frame the IMU quaternion,
  // projected gravity and gyro are expressed in. three.js defaults to Y-up, so we only
  // re-orient the CAMERA and the GROUND GRID (proper rotations, det +1) and feed the data
  // through untouched. Never swap data axes here: the EBIMU web viewer once did exactly
  // that and produced a mirror image (det -1) that reversed every rotation on screen.
  camera.up.set(0, 0, 1);
  camera.position.set(1.6, -1.3, 1.1);   // front-right-above, looking at the origin
  camera.lookAt(0, 0, 0);
  scene.add(new THREE.AmbientLight(0xffffff, 1.0));
  const grid = new THREE.GridHelper(2, 8, 0x445566, 0x2a2a30);
  grid.rotation.x = Math.PI / 2;          // GridHelper lies in XZ; rotate it into the XY ground plane (Z-up)
  scene.add(grid);

  function mkAxes(opacity) {
    const mk = (dir, color) => {
      const a = new THREE.ArrowHelper(dir.clone().normalize(), new THREE.Vector3(0, 0, 0), 0.55, color, 0.1, 0.05);
      a.line.material.transparent = true; a.line.material.opacity = opacity;
      a.cone.material.transparent = true; a.cone.material.opacity = opacity;
      return a;
    };
    return {
      x: mk(new THREE.Vector3(1, 0, 0), 0xe05050),
      y: mk(new THREE.Vector3(0, 1, 0), 0x50c060),
      z: mk(new THREE.Vector3(0, 0, 1), 0x5090e0),
    };
  }
  const bodyGroup = new THREE.Group();
  const realGroup = new THREE.Group();
  scene.add(bodyGroup); scene.add(realGroup);
  const bodyAxes = mkAxes(1.0);
  const realAxes = mkAxes(0.35);
  Object.values(bodyAxes).forEach((a) => bodyGroup.add(a));
  Object.values(realAxes).forEach((a) => realGroup.add(a));

  const mkArrow = (color, opacity) => {
    const a = new THREE.ArrowHelper(new THREE.Vector3(0, 0, -1), new THREE.Vector3(0, 0, 0), 0.01, color, 0.12, 0.06);
    a.line.material.transparent = true; a.line.material.opacity = opacity;
    a.cone.material.transparent = true; a.cone.material.opacity = opacity;
    return a;
  };
  const gravArrow = mkArrow(0xffcc55, 1.0); bodyGroup.add(gravArrow);
  const gravArrowReal = mkArrow(0xffcc55, 0.4); realGroup.add(gravArrowReal);
  const gyroArrow = mkArrow(0x00e5ff, 1.0); bodyGroup.add(gyroArrow);

  return { renderer, scene, camera, bodyGroup, realGroup, gravArrow, gravArrowReal, gyroArrow };
}

function setArrow(arrow, vec3, scaleFor1) {
  const v = new THREE.Vector3(vec3[0], vec3[1], vec3[2]);
  const len = v.length();
  if (len < 1e-6) { arrow.visible = false; return; }
  arrow.visible = true;
  arrow.setDirection(v.clone().normalize());
  arrow.setLength(clamp(len * scaleFor1, 0.05, 1.1), 0.12, 0.06);
}

function updateImu3D() {
  if (!imu3d) return;
  const st = S.status;
  if (st && st.base && st.base.quat) {
    const q = st.base.quat; // [w,x,y,z]
    imu3d.bodyGroup.quaternion.set(q[1], q[2], q[3], q[0]);
  }
  if (st && st.imu) {
    if (st.imu.gravity_b) setArrow(imu3d.gravArrow, st.imu.gravity_b, 0.9);
    if (st.imu.gyro_rad_s) setArrow(imu3d.gyroArrow, st.imu.gyro_rad_s, 0.4);
  }
  const realImu = st && st.telemetry ? st.telemetry.imu : null;
  const legend = el("imu-legend");
  if (realImu) {
    imu3d.realGroup.visible = true;
    if (realImu.quat_wxyz) {
      const q = realImu.quat_wxyz;
      imu3d.realGroup.quaternion.set(q[1], q[2], q[3], q[0]);
    } else {
      imu3d.realGroup.quaternion.copy(imu3d.bodyGroup.quaternion);
    }
    if (realImu.gravity_b) setArrow(imu3d.gravArrowReal, realImu.gravity_b, 0.9);
    if (legend) legend.textContent = `real IMU age ${fmt(realImu.age_s, 2)}s`;
  } else {
    imu3d.realGroup.visible = false;
    if (legend) legend.textContent = "no real IMU connected";
  }
  imu3d.renderer.render(imu3d.scene, imu3d.camera);
}

/* ================================================================== Plot grid (item 6) */
const ROW_META = {
  pos: {
    title: "position [rad] (solid=q, dashed=target, dotted=sent-to-hardware)",
    labels: ["L q sim", "R q sim", "L target", "R target", "L real", "R real", "L sent", "R sent"],
  },
  tau: { title: "torque [N·m]", labels: ["L tau sim", "R tau sim", "L real", "R real"] },
  // A4 fix: qd used to have no real-side series at all (S.ring already carried realQd -
  // onJointState/pollSlow filled it - seriesArraysFor's qd branch just never read it), so
  // real velocity was invisible regardless of the panel-naming bug below. Added here.
  qd: { title: "velocity [rad/s]", labels: ["L qd sim", "R qd sim", "L real", "R real"] },
};

function initPlotsToolbar() {
  const tb = el("plots-toolbar");
  tb.innerHTML = `
    <b>Plots</b>
    <span>rows:</span>
    <span class="seg" id="plot-rows-seg">
      <span data-r="pos" class="on">q/target</span><span data-r="tau">tau</span><span data-r="qd">qd</span>
    </span>
    <span>window:</span>
    <span class="seg" id="plot-window-seg">
      <span data-w="5">5s</span><span data-w="10" class="on">10s</span><span data-w="20">20s</span><span data-w="60">60s</span>
    </span>
    <span class="small">L=blue R=orange &middot; solid=sim dashed=target light=real &middot; click a panel to expand</span>
    <span class="small" id="plots-real-status" style="margin-left:auto"></span>
  `;
  tb.querySelector("#plot-rows-seg").addEventListener("click", (ev) => {
    const s = ev.target.closest("span"); if (!s) return;
    const r = s.dataset.r;
    S.plotRows[r] = !S.plotRows[r];
    s.classList.toggle("on", S.plotRows[r]);
    buildPlotGrid();
  });
  tb.querySelector("#plot-window-seg").addEventListener("click", (ev) => {
    const s = ev.target.closest("span"); if (!s) return;
    S.plotWindowS = parseFloat(s.dataset.w);
    document.querySelectorAll("#plot-window-seg span").forEach((x) => x.classList.toggle("on", x === s));
  });
}

function destroyPlotInstances() {
  Object.values(S.plotInstances).forEach((u) => { try { u.destroy(); } catch (e) {} });
  S.plotInstances = {};
}

function makeSeriesFor(row) {
  const base = [{}];
  ROW_META[row].labels.forEach((label) => {
    const isR = label.startsWith("R");
    const isTarget = label.includes("target");
    const isReal = label.includes("real");
    const isSent = label.includes("sent"); // TX item 3: what was actually sent to hardware
    let stroke = isR ? "#e08a3c" : "#5b9bd5";
    const s = { label, stroke, width: isReal || isSent ? 1 : 1.5 };
    if (isTarget) s.dash = [6, 4];
    if (isReal) { s.stroke = isR ? "#e08a3c88" : "#5b9bd588"; s.width = 1; }
    if (isSent) { s.stroke = isR ? "#c060e0" : "#60e0c0"; s.dash = [1, 3]; s.width = 1.5; }
    base.push(s);
  });
  return base;
}

function makeUplot(row, kind, container) {
  const w = Math.max(container.clientWidth || 180, 60);
  const h = Math.max(container.clientHeight || 118, 60);
  const nSeries = ROW_META[row].labels.length;
  const opts = {
    width: w, height: h,
    padding: [4, 4, 0, 0],
    legend: { show: false },
    cursor: { show: false },
    scales: { x: { time: false } },
    axes: [{ show: false }, { show: true, size: 32, stroke: "#777", grid: { stroke: "#262626" } }],
    series: makeSeriesFor(row),
  };
  const wrap = document.createElement("div");
  wrap.className = "u-wrap";
  container.appendChild(wrap);
  const data = [[]];
  for (let i = 0; i < nSeries; i++) data.push([]);
  return new uPlot(opts, data, wrap);
}

function buildPlotGrid() {
  if (!S.contract) return;
  destroyPlotInstances();
  const root = el("plots-rows");
  root.innerHTML = "";
  // A4 fix: panels come from sim ∪ real observed names (panelsFor), not S.jointKinds alone,
  // so a real joint that doesn't fit the sim's L/R naming template still gets a panel
  // instead of silently disappearing. S.plotPanels is the lookup seriesArraysFor()/
  // openModal() use, so panel construction and data query can never disagree on names.
  const panels = panelsFor(S.contract.action_joint_names, S.realJointNames);
  S.plotPanels = {};
  panels.forEach((p) => { S.plotPanels[p.kind] = p; });
  S.lastPanelRealCount = S.realJointNames.length;
  const cellsToInit = []; // [row, kind, cellEl] - uPlot needs real layout, so build the
                          // whole DOM tree and attach it to `root` FIRST, then measure
  Object.keys(ROW_META).forEach((row) => {
    if (!S.plotRows[row]) return;
    const rowDiv = document.createElement("div");
    rowDiv.className = "plots-row";
    panels.forEach((p) => {
      const cell = document.createElement("div");
      cell.className = "plot-cell";
      cell.dataset.row = row; cell.dataset.kind = p.kind;
      // realOnly: this joint name is on the real stream but not in the sim contract's
      // action set (e.g. an unmapped bridge name) - tag it instead of letting it pass for
      // an ordinary sim panel, per item 3 of the A4 fix.
      const tag = p.realOnly ? ` <span class="pill warn" style="font-size:9px;padding:0 4px">real only</span>` : "";
      cell.innerHTML = `<span class="pt">${p.kind}${tag}</span>`;
      cell.addEventListener("click", () => openModal(row, p.kind));
      rowDiv.appendChild(cell);
      cellsToInit.push([row, p.kind, cell]);
    });
    const hdr = document.createElement("div");
    hdr.className = "small"; hdr.style.margin = "2px 4px";
    hdr.textContent = ROW_META[row].title;
    root.appendChild(hdr);
    root.appendChild(rowDiv);
  });
  // NOW every cell has real clientWidth/clientHeight (attached to `root`, which is in
  // `document`) - a detached node reports 0 and uPlot would fall back to a fixed size.
  cellsToInit.forEach(([row, kind, cell]) => {
    S.plotInstances[row + ":" + kind] = makeUplot(row, kind, cell);
  });
}

function seriesArraysFor(row, kind) {
  // A4 fix: read the panel's actual Lname/Rname (as built by buildPlotGrid -> panelsFor)
  // instead of re-guessing `L_${kind}_joint` here - a second, independent template that
  // could (and did) drift out of sync with what the panel was actually built from.
  const p = S.plotPanels[kind];
  const Lname = p ? p.Lname : `L_${kind}_joint`;
  const Rname = p ? p.Rname : `R_${kind}_joint`;
  const now = S.ring.length ? S.ring[S.ring.length - 1].t : 0;
  const cutoff = now - S.plotWindowS;
  const rows = S.ring.filter((r) => r.t >= cutoff);
  const xs = rows.map((r) => r.t - now);
  const get = (field, name) => rows.map((r) => (name && r[field] && r[field][name] !== undefined && r[field][name] !== null) ? r[field][name] : null);
  if (row === "pos") {
    return [
      xs, get("q", Lname), get("q", Rname), get("target", Lname), get("target", Rname),
      get("realQ", Lname), get("realQ", Rname), get("sentTarget", Lname), get("sentTarget", Rname),
    ];
  }
  if (row === "tau") return [xs, get("tau", Lname), get("tau", Rname), get("realTau", Lname), get("realTau", Rname)];
  return [xs, get("qd", Lname), get("qd", Rname), get("realQd", Lname), get("realQd", Rname)];
}

function renderPlots() {
  // A4 fix item 1: a new real joint name can arrive any time (not just at contract load /
  // row-toggle / resize, the only other buildPlotGrid() triggers) - if the observed real
  // name set has grown since the panels were last built, rebuild so it gets a panel too.
  // realJointNames only ever grows (see onJointState), so this settles after the first few
  // frames of a real stream and does not thrash.
  if (S.contract && S.realJointNames.length !== S.lastPanelRealCount) {
    buildPlotGrid();
  }
  const st = S.status;
  const tel = st ? (st.telemetry || {}) : {};
  const statusEl = el("plots-real-status");
  if (statusEl) {
    // A4 fix item 4: previously nothing at all indicated whether "no real series visible"
    // meant "no real stream" vs. "stream present but not plotting" (the actual bug).
    statusEl.textContent = tel.rx_count ? `real stream: rx ${fmt(tel.rx_hz, 1)}/s` : "no real stream";
  }
  Object.entries(S.plotInstances).forEach(([key, u]) => {
    const [row, kind] = key.split(":");
    u.setData(seriesArraysFor(row, kind));
  });
}

/* ---------------------------------------------------------------- expand modal */
function initModal() {
  el("modal-close").onclick = closeModal;
  el("modal").addEventListener("click", (ev) => { if (ev.target.id === "modal") closeModal(); });
}

function openModal(row, kind) {
  S.modal = { row, kind };
  const p = S.plotPanels[kind];
  const suffix = p && p.realOnly ? " (real only)" : "";
  el("modal-title").textContent = `${kind}${suffix} - ${ROW_META[row].title}`;
  el("modal").classList.add("on");
  const container = el("modal-chart");
  container.innerHTML = "";
  S.modalInstance = makeUplot(row, kind, container);
}

function closeModal() {
  S.modal = null;
  if (S.modalInstance) { try { S.modalInstance.destroy(); } catch (e) {} S.modalInstance = null; }
  el("modal").classList.remove("on");
}

function renderModalChart() {
  if (!S.modal || !S.modalInstance) return;
  S.modalInstance.setData(seriesArraysFor(S.modal.row, S.modal.kind));
}

window.addEventListener("resize", () => {
  clearTimeout(window.__resizeT);
  window.__resizeT = setTimeout(buildPlotGrid, 200);
});

/* ================================================================== TX (viewer->hardware)
 * docs/121 section 10 TX item / docs/123, WIRED 2026-09-04 to a real bridge.tx_client.TxClient
 * via pygviewer/tx.py's TxState - once armed this puts real 50 Hz UDP JointTarget packets on
 * the wire. Sends ONLY the current SimCore target (this Joints tab's sliders, or a running
 * script) - never a policy action (blocked both in the sim mode gate and in TxClient itself).
 *
 * Three-stage safety, mirroring the server exactly:
 *   1. POST /tx/config  - host/port/enable list/kp_max/kd_max/ttl_ms. Refused while armed.
 *   2. POST /tx/enable  - turns the TX subsystem on (needs a prior config).
 *   3. POST /tx/arm     - refused (409) unless enabled AND sim mode is 'manual'.
 * PLUS a keyboard dead-man, independent of all three: holding Space (not while typing in a
 * text field) calls POST /tx/heartbeat every ~100ms; releasing it does NOT disarm - the
 * server just stops sending new packets ("hold", not "stop") and the robot's OWN age-based
 * dead-man (bridge.remote_target, 0.2s) takes over from there, same as unplugging a cable. */
function renderTxSectionHtml() {
  const c = S.contract;
  const motorRows = c.action_joint_names.map((n) => `
    <label style="display:inline-flex;align-items:center;gap:3px;margin:2px 6px 2px 0;font-size:11px">
      <input type="checkbox" class="tx-motor-cb" data-n="${n}"> ${n.replace("_joint", "")}
    </label>`).join("");
  return `
    <h3>TX (hardware transmit)</h3>
    <div class="small" style="margin-bottom:4px">Sends ONLY the current manual/script target -
      never a policy action. Only allowed while mode is <b>manual</b> (Joints tab, or a
      running script) - never while a policy drives.</div>
    <div class="row tight"><label>host</label><input id="tx-host" value="127.0.0.1" style="width:96px">
      <label>port</label><input id="tx-port" type="number" value="9872" style="width:60px"></div>
    <div class="row tight"><label>kp max</label><input id="tx-kpmax" type="number" value="5" step="0.1" style="width:50px">
      <label>kd max</label><input id="tx-kdmax" type="number" value="0.5" step="0.05" style="width:50px">
      <label>ttl ms</label><input id="tx-ttlms" type="number" value="250" step="10" style="width:50px"></div>
    <div>${motorRows}</div>
    <div class="row tight"><button id="btn-tx-config" style="flex:1">1. configure (host/port/enable/gains)</button></div>
    <div class="row tight"><label>2. activate TX panel</label><input type="checkbox" id="tx-enable"></div>
    <div class="row tight"><button id="btn-tx-arm" style="flex:1">3. ARM</button>
      <button id="btn-tx-disarm" style="flex:1">disarm</button></div>
    <div class="row tight"><span id="tx-badge" class="pill">-</span>
      <span class="small" id="tx-heartbeat-age"></span></div>
    <div class="small" style="margin:4px 0">Hold <b>Space</b> to send (keyboard dead-man,
      ~100ms) - releasing it HOLDS the last target (does not disarm); the robot's own
      dead-man then takes over. seq <span id="tx-seq" class="mono">-</span> &middot;
      rate <span id="tx-rate" class="mono">-</span> Hz &middot;
      rejected <span id="tx-rejected" class="mono">0</span></div>
    <div class="small">arm_token (copy into the receiver's <span class="mono">--arm-token</span>):
      <span id="tx-token" class="mono">-</span></div>
  `;
}

function collectTxEnableList() {
  return Array.from(document.querySelectorAll(".tx-motor-cb"))
    .filter((cb) => cb.checked)
    .map((cb) => cb.dataset.n);
}

async function pushTxConfig() {
  const body = {
    host: el("tx-host").value,
    port: parseInt(el("tx-port").value, 10) || 0,
    enable: collectTxEnableList(),
    kp_max: parseFloat(el("tx-kpmax").value) || 5.0,
    kd_max: parseFloat(el("tx-kdmax").value) || 0.5,
    ttl_ms: parseInt(el("tx-ttlms").value, 10) || 250,
  };
  const r = await apiOk("POST", "/tx/config", body);
  if (r) { S.txStatus = r; toast(`TX configured: ${body.enable.length} joint(s) enabled`); }
  return r;
}

function txDeadmanTick() {
  if (!S.txStatus || !S.txStatus.armed) return;
  apiOk("POST", "/tx/heartbeat");
}

function startTxDeadman() {
  if (S.txDeadmanTimer) return;
  txDeadmanTick();
  S.txDeadmanTimer = setInterval(txDeadmanTick, 100); // ~100ms cadence, spec'd dead-man rate
}

function stopTxDeadman() {
  if (S.txDeadmanTimer) { clearInterval(S.txDeadmanTimer); S.txDeadmanTimer = null; }
}

function isTypingTarget(ev) {
  const t = ev.target;
  return t && ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName);
}

function wireTxSection() {
  el("btn-tx-config").onclick = () => {
    if (S.txStatus && S.txStatus.armed) { toast("disarm before reconfiguring"); return; }
    pushTxConfig();
  };
  el("tx-enable").addEventListener("change", async (ev) => {
    const on = ev.target.checked;
    const r = await apiOk("POST", "/tx/enable", { on });
    if (r) S.txStatus = r;
    else ev.target.checked = !on; // request refused (no config yet) - revert the checkbox
  });
  el("btn-tx-arm").onclick = async () => {
    const r = await apiOk("POST", "/tx/arm");
    if (r) { S.txStatus = r; toast("TX armed - hold Space to send"); }
  };
  el("btn-tx-disarm").onclick = async () => {
    stopTxDeadman();
    const r = await apiOk("POST", "/tx/disarm");
    if (r) S.txStatus = r;
  };
  document.querySelectorAll(".tx-motor-cb").forEach((cb) => {
    cb.addEventListener("change", () => {
      if (S.txStatus && S.txStatus.armed) { toast("disarm before changing enabled motors"); cb.checked = !cb.checked; return; }
      if (S.txStatus) pushTxConfig(); // config already exists - re-push with the new list
    });
  });
  // keyboard dead-man - document-level so it works regardless of which element has focus,
  // but never hijacks Space while the operator is typing into a text field.
  if (!window.__txKeyWired) {
    window.__txKeyWired = true;
    document.addEventListener("keydown", (ev) => {
      if (ev.code !== "Space" || ev.repeat || isTypingTarget(ev)) return;
      if (!S.txStatus || !S.txStatus.armed) return;
      ev.preventDefault();
      startTxDeadman();
    });
    document.addEventListener("keyup", (ev) => {
      if (ev.code !== "Space") return;
      stopTxDeadman();
    });
    window.addEventListener("blur", stopTxDeadman); // losing window focus must stop it too
  }
}

function renderTxStatusLive() {
  const badge = el("tx-badge");
  if (!badge) return;
  const tx = S.txStatus;
  const st = S.status;
  const modeOk = st && st.mode === "manual";
  el("btn-tx-arm").disabled = !modeOk || !tx || !tx.enabled || tx.armed;
  el("btn-tx-arm").title = modeOk ? "" : `blocked: mode is ${st ? st.mode : "?"}, TX only allowed in 'manual'`;
  if (!tx) { badge.textContent = "-"; badge.className = "pill"; return; }
  if (tx.sending) { badge.textContent = "SENDING"; badge.className = "pill ok"; }
  else if (tx.armed) { badge.textContent = "ARMED (hold Space)"; badge.className = "pill warn"; }
  else { badge.textContent = "DISARMED" + (tx.disarm_reason ? ` (${tx.disarm_reason})` : ""); badge.className = "pill"; }
  const ageEl = el("tx-heartbeat-age");
  if (ageEl) ageEl.textContent = tx.deadman_age_s !== null && tx.deadman_age_s !== undefined ? `heartbeat ${fmt(tx.deadman_age_s, 2)}s ago` : "";
  const seqEl = el("tx-seq"), rateEl = el("tx-rate"), rejEl = el("tx-rejected"), tokEl = el("tx-token");
  if (seqEl) seqEl.textContent = tx.last_seq === null || tx.last_seq === undefined ? "-" : tx.last_seq;
  if (rateEl) rateEl.textContent = fmt(tx.rate_hz, 1);
  if (rejEl) rejEl.textContent = tx.rejected_count ?? 0;
  if (tokEl) tokEl.textContent = tx.arm_token || "-";
  if (document.activeElement !== el("tx-enable")) el("tx-enable").checked = !!tx.enabled;
  document.querySelectorAll(".tx-motor-cb").forEach((cb) => {
    if (document.activeElement !== cb) cb.checked = (tx.enable || []).includes(cb.dataset.n);
  });
  // structural safety net mirrored in the UI: mode left 'manual' while armed -> the server
  // already auto-disarmed (SimCore._on_control_tick -> TxState.check_mode_gate); stop the
  // local dead-man loop too so it does not keep calling a now-pointless /tx/heartbeat.
  if (!modeOk) stopTxDeadman();
}

document.addEventListener("DOMContentLoaded", boot);

/* expose a few internals for the later sections of this file (loaded as one script,
   but organised so each dashboard tab's rendering code can be reviewed independently) */
window.__pygdash = {
  S, api, apiOk, toast, el, fmt, clamp, displayVal, internalVal, unitSuffix, obsTermDims, RAD2DEG, DEG2RAD,
  policyLoadErrorText, loadAndRunPolicy, loadAndRunPolicyByPath,
};
})();
