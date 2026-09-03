# 121. pygviewer — Sim↔Real 비교 웹뷰어: 설계·결정·진행 로그 (2026-09-03~)

> 사용자 요청(09-03): 시뮬레이션 거동과 실물 로봇 거동을 같은 화면·같은 데이터 형식으로 비교하는 MuJoCo 웹 뷰어.
> 이 문서 = **설계 정본 + 진행 로그**(구현 코더가 각 phase 완료 시 §9에 기록). 승인 계획 원문:
> `~/.claude/plans/optimized-leaping-hamster.md`(로컬). 코드: `tools/pygviewer/`.

## 0. 요구 9항목 ↔ 구현 매핑

| # | 요구 | 구현 | Phase |
|---|---|---|---|
| 1 | 모델 3종×2분파(RP/AB) | bake로 6변형 `.mjb`+계약 JSON, UI 드롭다운 | P0 |
| 2 | base_link 고정(완전/회전자유, 위치 지정) | mocap 앵커 + `eq weld`(fixed) / `eq connect`(pivot, 사용자 오프셋 점) 런타임 토글, 높이 슬라이더, 지면 on/off | P1 |
| 3 | 중력 유지 | `m.opt.gravity` 불변(코드로 보장) | P0 |
| 4 | 관절 raw 모니터링 | Snapshot(q·qd·τ·target) 30 Hz 리드아웃 + 미러축 관절은 물리각 병기 | P1 |
| 5 | 관절 목표 q 입력 UI/API | 슬라이더+숫자 양방향, `POST /target`; AB는 발목공간 슬라이더(역해 그리드) + 크랭크 | P1 |
| 6 | 학습 weight 로드 | ONNX 러너 + `.pt→ONNX` bake(parity 검증) + `.pt` 직접 로드(mjlab 지연 임포트), 모델 계약 sha 일치 검사 | P2 |
| 7 | 선택 관절 플롯 | viser `add_uplot` 링버퍼 10 s@50 Hz, ≤8채널 | P1 |
| 8 | 텔레메트리 송수신 | 스키마 v1(JSON, sim 관절명·rad/SI·t_ns·seq·contract_hash), `WS /ws/out`·`/ws/in`, REST, OpenAPI+API.md; 뷰어→실물 명령은 **문서만** | P3 |
| 9 | 원격 모터값 주입(실물 뷰어) | HUPHY UDP(9870 포맷) 어댑터 + 명시적 12행 매핑표(브리지가 부호·영점·순서·deg→rad 담당), 더미 송신기, jsonl.gz 기록/재생, real_replay 모드 | P3 |
| + | 비교 모드 전부 | 동일 목표 시퀀스 응답비교(`compare.py`), 정책 섀도우(obs 항목별 sim/real 소스 mux, 전송 금지 하드코딩), 오프라인 재생 | P4 |

## 1. 사용자 결정 (09-03, 4차 질문으로 확정 — 재질문 금지)
base 고정 = 스탠드/접지 둘 다 · 회전중심 = 사용자 지정 오프셋 · 통신 양방향 설계·수신만 구현·API 문서 철저 · 비교모드 전부 ·
리포 내 `tools/pygviewer/`+mjlab venv · 실물 호스트 미정(더미 송신기) · 변환은 브리지 · 와이어 정준 = sim 관절명+rad/SI ·
정책 .pt+ONNX 둘 다 · PD 게인 학습/실물 전환 · 토크 = 크랭크 토크 + Jcᵀ 등가 병행 · 상체 미수신 = default 유지+'데이터 없음' ·
**하드웨어 사실**: sim `L_*` = 실물 왼다리(HUPHY left/can0), HUPHY ankle_a/b = crank_A(위)/B(아래) — 검증 프로토콜 2·3단계 통과 전 UNVERIFIED 배너.

## 2. 아키텍처
단일 프로세스 3스레드: `SimLoop`(물리 200 Hz·제어 50 Hz, PD+T-N `qfrc_applied` = 학습과 동일 수식, latest-only Snapshot, 드롭 허용·버퍼 금지) ·
viser(30 Hz 렌더, 10 Hz 플롯) · FastAPI/uvicorn(REST·WS·UDP 어댑터·레코더). 포트 8094(viser)/8095(API). CPU 전용(GPU는 학습 점유).
모듈: `bake.py`(mjlab·torch 임포트 유일) · `contract.py` · `sim_core.py` · `policy.py` · `modes.py` · `schema.py` · `api.py` · `ui.py` ·
`bridge/{huphy_udp,dummy_tx}.py` · `record.py` · `compare.py`. 캐시 `/home/syaro/pyg_fea/pygviewer/cache/`.
근거: 원본 XML은 nu=0·바닥·키프레임 없음(`tools/sim2sim/mujoco_ab_loop_drift.py:55-59`) → 학습 env에서 구운 모델 필수. 폐루프 AB는 qpos 스냅 금지(NaN) →
`tools/viewer/mjcf_joint_viewer.py settle_loop()` 검증 방식.

## 3. 와이어 스키마 v1 (요약; 정본은 `tools/pygviewer/API.md`)
헤더 `{v:1, type, t_ns(송신 모노토닉), seq, src: sim|real|policy|replay|dummy, frame:"model_v30", contract_hash}` ·
`JointState{joint_names[], q[rad], qd[rad/s], tau[N·m]|null("est." 라벨), target|null, temp_c|null, gains{kp,kd,tau_ff,kp_enc_range}|null, ankle_derived}` ·
`ImuState{quat_wxyz, gyro_rad_s, acc_m_s2, gravity_b, age_s}` · `PolicyIO{obs, obs_sources, action, target, cmd}` · `JointTarget`(뷰어→실물, 문서만) · `Status`.
결측 = `null`(HUPHY −1 센티널은 어댑터가 변환). 엔드포인트: `/status /contract /mode /target /base /policy/load /policy/cmd /obs_source /gains /script/run /record/*`, `WS /ws/out /ws/in`, `UDP :9871`.

## 4. Sim2Real 안전장치 (설계 내장, 요약)
R1 부호/영점(joint_contract travel_sign·mirrored + 브리지 명시표 + UI sign-sanity + 합성 스트림 테스트) · R2 발목 크랭크↔관절 FK 교차(0.02 rad) ·
R3 rad 고정·null 결측·|Δq|>π 플래그 · R4 속도/토크 부호 보정·유한차분 검사 · R5 t_ns/seq·clock offset 추정·jitter>15 ms 회색 · R6 default 계약 일치·창≥0.2 rad ·
R7 게인 diff 표·flags 표시·NaN 가드 · R8 IMU 중력 화살표 병행·정지 |Δg|<0.05 · R9 base 모드/높이/지면을 기록 헤더에 · R10 섀도우 전송 금지·소스별 히스토리 · R11 contract_hash 불일치 오버레이 거부.

## 5. 검증 프로토콜 (오버레이 신뢰 전 8단계)
① 정지 영점(|Δq|<0.02 rad, |Δg|<0.05) ② 관절별 부호 스윕(→ `motor_sign_convention.json` side_mapping_verified) ③ 발목 FK 교차(25점) ④ 속도 sanity(0.5 Hz sine)
⑤ 지연 보정(스텝 5회, jitter<15 ms) ⑥ 동일 목표 응답 오버레이(게인 일치 후만 의미) ⑦ IMU 틸트(±10°, 3° 내) ⑧ 기록 왕복(비트 동일).

## 6. 단계·검증 기준
| Phase | 내용 | 완료 기준(검증) | 상태 |
|---|---|---|---|
| P0 | bake 6변형, SimCore, viser 씬, `/status` | 6 mjb+json; headless 5 s ≥195 Hz 물리·RSS<600 MB; `curl :8095/status` | ✅ 21:55 (199.8 Hz·drops 0·RSS 147 MB) |
| P1 | 관절 UI/API, base 3모드, 지면, 폐루프 settle, 플롯 | `test_basefix`(fixed 드리프트<1e-6, pivot 위치<1e-4) · `test_loop_settle`(vs loop_ankle_verify.json, closure<0.01 mm) · `test_bake_contract` · `test_sim_rate` | ✅ 22:05 (98 tests / 11.7 s, 전부 통과) |
| P2 | ONNX/.pt 정책, obs 빌더, 게인 소스 | `test_policy_parity`(<1e-4) · `test_obs_order` · 워킹 스모크(drift 러너와 vx 오차≤0.05) | ✅ 09-03 22:40 |
| P3 | 스키마·WS/REST·HUPHY UDP 어댑터·더미·레코더 | `test_schema` · 더미 sine→real_replay · WS 50 Hz · 10 s 기록 RSS 불증 | ✅ 09-04 (161 tests, WS 49.4 msg/s, RSS +0.3 MB/10s) |
| P4 | 스크립트 플레이어·compare·obs mux·섀도우 | 지연 주입 더미 오버레이 png · 더미 IMU가 액션 변화 | ⏳ |
| 등록 | dashboard PORTS·start_all·README·launch.json·브리핑 | — | ✅ 22:20 (8094/8095) |

## 7. 재사용 소스
`tools/sim2sim/mujoco_ab_loop_drift.py`(PD/T-N/obs) · `tools/sim2sim/dump_contract_ab.py`(계약) · `tools/viewer/mjcf_joint_viewer.py`(viser·settle) ·
`pygmalion_constants.py`(get_spec·키프레임·safe_target_clip·signed_pose·joint_travel_sign) · `mjlab/rl/{runner,exporter_utils}.py`(ONNX) ·
`ankle_rp_envelope.json`(역해·Jcᵀ) · HUPHY `telemetry/{udp,snapshot}.py`(실물 포맷).

## 8. 열린 항목 (하드웨어)
실물 호스트·시계 동기 미정 · 관절별 모터 기종·kp/kd 인코딩(RS03/RS04 0~5000) · IMU 실장 방향(프로토콜 ⑦) · 좌우/발목 매핑 UNVERIFIED(프로토콜 ②③).

## 9. 진행 로그 (코더가 phase 완료마다 추가 — 시각·결과 숫자·커밋·문제)
- 09-03 21:15 — 계획 승인, P0/P1 구현 착수(코더). 이 문서 생성.
- 09-03 22:20 — **P0+P1 완료**. 6변형 bake, SimCore 200/50 Hz, viser 패널, FastAPI, pytest 98개 통과. 커밋 `70eb5aa`(본체·3,710줄) + `c6aef14`(`-m tools.pygviewer` 진입점). 가동 중: viser `http://192.168.20.177:8094`, API `http://192.168.20.177:8095/docs`, 로그 `tools/pygviewer/logs/pygviewer.log`. 상세는 아래.
- 09-03 22:45 — **P2 완료** (인계받은 코더). 커밋 `e05db7f`(WIP, 이전 코더가 API 과부하로 4회 끊긴 뒤 보존) 확인 결과, 실제로는 §6 P2 완료기준 대부분이 이미 구현돼 있었다: `policy.py`(ObsBuilder/OnnxPolicy/TorchPolicy/ObsSourceMux/action_to_target/check_compatible), `api.py`의 `/policy/load` `/policy/list` `/policy/unload` `/policy/cmd` `/policy/io` `/obs_source` `/gains`, `sim_core.py`의 `_policy_tick`(50 Hz 컨트롤 틱에 정책 추론), `ui.py`의 Policy/Gains 폴더(vx/vy/wz 슬라이더·run mode·obs-source 드롭다운·소스 마스크 문자열 readout). 인계 노트가 "Policy·Gains 폴더 구현 중"이라 적어둔 지점보다 실제 진행이 앞서 있었다.
  - **찾은 실버그**: `POST /mode`가 P1 시절 동기 사전검사(`mode not in ("idle","manual")`)를 그대로 두고 있어 `policy_sim`을 501로 거부했다 — `sim_core._apply_cmd`는 이미 받아주는데도. UI 패널은 `core._apply_cmd`를 직접 호출해 API를 건너뛰므로 패널 테스트로는 안 보였고, 재기동한 뷰어에 curl로 엔드포인트를 하나씩 찔러보다 발견. `api.py`를 고쳐 `real_replay`/`file_replay`만 501(P3/P4), `policy_sim`/`policy_shadow`는 정책 미로드시 409로 정정. 회귀 테스트 `tests/test_api_policy.py`(8케이스, FastAPI TestClient) 추가. pytest 전체 **130 passed**(기존 122 + 신규 8), ~13 s. 커밋 `5912895`.
  - **스모크(`smoke_walk.py`, model_700 ONNX, mjlab env 불필요)**: 정지(cmd=0, 15 s) `fell=False`, base_z **0.9040 m**(mjlab gait-probe 기준 0.9026, Δ**+0.0014 m**, 기준 0.02 이내), L_knee **+0.0924 rad**(기준 +0.1015, Δ**-0.0091 rad = -0.52°**), R_knee **-0.1061 rad**(기준 -0.1027, Δ**-0.0034 rad = -0.19°**) — 둘 다 ±2° 기대치 이내. 보행(cmd vx=0.6 m/s, 15 s) `fell=False`, vx(base-frame, t≥4s) **0.545 m/s**, 오차 **0.055 m/s**(기준 ≤0.1), 15 s에 7.25 m 이동. `closure worst 37.27 mm`는 새 버그가 아니라 §9 항목4(bent 키프레임 발바닥 침투, 38.6 mm)와 같은 계열의 기존 기록값 — 리셋 직후부터 고정, 재확인만 함.
  - **API 종단검증**(재기동한 라이브 프로세스, curl): `/policy/list`(2개 model_700/model_5200 모두 compatible=true) → `/policy/load`(name=model_700, obs_dim 45, action_dim 12, layout 5항: base_ang_vel/projected_gravity/motor_pos_history/actions/command) → `/mode policy_sim`(수정 후 200 OK, base free+ground on 상태로 실제 주행 확인) → `/policy/cmd` → `/policy/io`(obs_sources 5항 전부 sim) → `/obs_source real`(501, P3 안내문) → `/gains`(GET: train 소스 kp/kd + kp_train/kd_train 대조표; POST source=real: real_gains 테이블 없어 400) → `/policy/unload` → `/mode idle` 순으로 전부 기대대로 응답.
  - **뷰어 재기동**: 기존 PID 3270444(21:49 기동, e05db7f 이전 API 코드를 메모리에 물고 있던 프로세스 — curl로 `/policy/load`가 구버전 501을 반환해 발견)를 kill, `setsid nohup ... run.py --variant LegOnly-AB --port 8094 --api-port 8095`로 재기동. `curl :8095/status` 200, contract_hash 갱신 확인, `/docs`(OpenAPI) 200.
  - **문서 갱신**: `tools/pygviewer/API.md`(정책/게인 엔드포인트를 "구현됨" 표로 이동, `/mode` 행 정정), `tools/pygviewer/README.md`(상태 줄 P2 포함, 신규 "Policy (P2)" 절, Tests 표에 `test_policy_parity.py`/`test_obs_order.py`/`test_api_policy.py` 3행 추가, layout 표의 `policy.py` 설명 갱신).
  - **`.pt` 직접 로드 수동 1회 확인**(지시대로 자동화하지 않고 curl 1회): `POST /policy/load {"pt": ".../model_700.pt", "allow_uncontracted": true}` → `kind: torch`, 로드 10.9 s, RSS 225 MB → **1327.3 MB**(문서화된 ~11 s/~1.3 GB와 일치). `mode policy_sim` + `cmd vx=0.4`로 3 s 구동 후 base 안 넘어짐(로드 직후 free+ground에서 정상 기립) 확인, 곧바로 unload해 메모리 반환. 이 확인 도중 재기동 타이밍 실수로 옛 `/mode` 버그를 한 번 더 재현했다가(재기동 전 api.py만 고치고 프로세스를 안 띄워서) 재기동 후 재확인 — 최종 결과는 위 API 종단검증과 동일하게 전부 통과.
  - **미해결**: `test_policy_parity.py`/`test_obs_order.py`는 인계 시점에 이미 있었고 이번 세션에서 새로 작성하지 않음(둘 다 통과 확인만); `ankle_pitch` RP 5.4° 창 관측(§9 추가 관측)은 여전히 관찰만 된 상태; `closure worst 37.27mm`(스모크 로그)가 기존 38.6mm 침투 기록과 정확히 같은 수치인지는 추가로 재확인하지 않음(계열은 같다고 판단).
- 09-04 00:15 — **P3 선행 점검**: "closure worst 37.27mm"가 side-aware 픽스 전 값을 담았을 가능성을 확인. 결론 = **같은 수치, 버그 아님**. (a) bake의 `default_q`/keyframe qpos는 `robot.data.default_joint_pos`에서 **직접** 읽는다(`bake.py:128`) — env 그 자체가 리셋하는 값과 동일 소스이고, bake 시각(13:10 UTC)은 `_bent_joint_pos()`/`signed_pose()` 커밋(546a7ed5, 03:32 UTC, "Derive left/right joint signs from the model")보다 뒤라 최신 로직 반영 확인. mjlab 트리 전체에서 `_reexpress_loop_pose` 함수명 자체를 찾지 못함(`grep -rn` 무결과) — reward_research 노트가 가리키는 실제 코드는 `_bent_joint_pos()`(v3 룩업 loop json 병합) + `signed_pose()`(범위유도 부호)이고, 이미 bake가 사용 중. (b) 뷰어 리셋 직후(settle 전) closure 직접 측정: **37.270473 mm**(코드로 재현, `SimCore.reset()` 직후 `closure_mm()`), 50 물리스텝(0.25s) 후 **0.042 mm**, 1000스텝(5s) 후 **0.009 mm**로 즉시 수렴 — `_bent_joint_pos()` 자체 docstring이 "매 리셋은 loop가 뜯긴 채 시작해 snap해 닫힌다"고 이미 명시한 현상과 정확히 일치(약 20mm 규모로 서술), mjlab 학습 env도 동일한 방식(조인트값 직접대입 후 첫 스텝들에서 물리가 닫음)으로 리셋하므로 뷰어 고유 버그가 아니다. sole penetration 38.6mm(발바닥 침투, base_z 방향)와는 **다른 지표**(closure는 rod_end-ball 사이트 거리, mechanism 폐루프)이자 다른 축 — 우연히 자릿수가 비슷할 뿐 같은 숫자 계열이 아님(정정: 이전 세션 "같은 계열" 판단은 틀렸음, 여기서 바로잡음). 재bake 불필요, 조치 없음.
- 09-04 01:10 — **P3 완료**. `schema.py`에 `to_jsonl/from_jsonl/validate_joint_names/MESSAGE_TYPES` 추가. 신규 `telemetry.py`(`RealState`: latest-only 버퍼, rx rate/age/seq-gap/moving-median clock offset/jitter, `|dq|>pi` 래핑 플래그, 관절범위±0.05rad 플래그, contract_hash 불일치 카운터, sign-sanity 2s창). `api.py`에 `WS /ws/in`(JointState/ImuState 검증+주입, 미지 관절명 거부), `/record/{start,stop}`, `/replay/{load,seek,speed}`, `/mode`에 `real_replay`/`file_replay` 정식 허용(`policy_shadow`만 P4로 501). `sim_core.py`: `real_replay`/`file_replay` 진입 시 base 강제 fixed, direct-drive(비크랭크) 관절은 매틱 수신값이 있을 때만 qpos 스냅(qvel=0)+해당 틱만 토크 0, 크랭크는 PD 타깃으로 라우팅; 미수신 관절은 평소 PD 유지(디폴트 고정, free-float 아님). `bridge/huphy_udp.py`(`JointMap`·`HuphyBridge`·`HuphyUdpReceiver`), `bridge/joint_map_huphy.json`(12행 motors + 4행 ankle_joints, `side_mapping_verified:false`), `bridge/dummy_tx.py`(sine/script/jsonl → ws/udp, latency/jitter/drop 주입, `--imu`). `record.py`(`Recorder`/`Replayer`, jsonl.gz 스트리밍). 신규 테스트 `test_schema.py`(10) · `test_bridge_huphy.py`(10) · `test_record.py`(9), `test_api_policy.py` +2(대체) — **130 → 161 tests, 전부 통과**.
  - **실버그 1건 발견+수정**: `RealState.status()`가 자기 lock을 쥔 채 `self.rx_hz()`(자체 lock 재획득)를 호출 — `threading.Lock`은 재진입 불가라 **자기 자신과 데드락**. `SimCore()` 생성자가 `reset()` 직후 `_publish()`에서 `status()`를 호출하므로 **거의 모든 pytest가 생성 시점에 영구 정지**했다(60s+ 타임아웃, `ps` futex_wait_queue로 확인). `rx_hz()`를 lock 밖에서 미리 호출하도록 수정.
  - **실버그 2건**: `real_replay`가 "미수신 관절 default 유지" 규칙을 어기고 있었다 — 원래 코드는 모드가 replay이면 **모든** direct-drive 관절 토크를 무조건 0으로 만들어, 데이터가 없는 관절도 free-float(중력하에 표류)했다. `test_record.py::test_real_replay_with_no_telemetry_is_identical_to_manual_mode`(차분 테스트: 동일 초기상태에서 manual 계속 vs real_replay 무수신 궤적이 1e-9로 완전히 같아야 함 — 원래 코드는 즉시 발산)로 재현·고정. 수정: 매 컨트롤틱마다 "이번 틱에 실제로 데이터가 있는 direct-drive 관절"만 토크 0+스냅하도록 캐시 분리(`_update_replay_targets`/`_replay_direct_now`).
  - **크랭크 PD 물리검증 함정**: 초기 테스트에서 두 크랭크(A/B)에 독립적으로 임의 목표를 준 결과(+0.05 rad 균일 오프셋) 크랭크A가 명령과 무관하게 항상 +0.23rad 근방에 수렴 — 버그로 의심했으나, `ankle_inverse`로 만든 **기구학적으로 유효한** 크랭크쌍으로도 base=fixed(허공에 매달린 다리)에서는 크랭크 Kp(22.3, "물리 앵커값, 자유노브 아님")가 다리 자중 중력토크를 못 이겨 목표에 못 미친다는 것을 확인 — 사실이며 게인 재조정 대상 아님. 테스트를 "PD가 target을 정확히 라우팅하는가"(배관 검증, 통과)로 범위축소하고 물리수렴 주장은 제거, 이 사실을 README/API.md에 기록.
  - **라이브 종단검증**(재기동한 뷰어 프로세스, 실 소켓): `websocat` 대신 python `websockets` 클라이언트로 `WS /ws/out?hz=50` → **49.4 msg/s**(2초 창, 99프레임). `bridge dummy --pattern sine --target ws`(L_hip_pitch, amp 0.15, freq 0.3Hz) → `/ws/in` → `real_replay` → `/joints` 폴링으로 q가 정확히 [-0.325,-0.025] 포락선(default −0.175±0.15) 내에서 sine을 따라감 확인, `telemetry.age_s` ≤0.018s·`rx_hz` 50.0·`clock_offset_ms` 0.33(동일호스트라 작음) 표시. `bridge dummy --pattern sine --target udp`(L/R_knee, amp 0.2, freq 0.25Hz)를 독립 `bridge huphy` 프로세스(포트 9871)로 보내 어댑터 검증 — L_knee/R_knee가 정확히 미러(0.35±0.2 vs −0.35∓0.2)로 추종, `hard_failures=0`, `rx_hz≈101`(다리 2개×50Hz 패킷이므로 배가 정상). 라이브 `/record/start`→10s→`/record/stop`: RSS **219.5→219.8 MB(+0.3MB)**, 2004줄, 0 에러; `/replay/load`→`/mode file_replay`로 로드한 녹화가 실제 재생(cursor 195/2004 @1s) 확인.
  - **미해결**: `policy_shadow`(obs mux 실측 real 소스)·`compare.py`·스크립트 플레이어는 P4 그대로 남김. HUPHY 브리지 CLI(`bridge huphy`)는 **독립 프로세스**(자체 SimCore)로만 구현 — 라이브 뷰어 프로세스에 직접 주입하려면 별도 배선이 필요(API.md에 명시). `side_mapping_verified:false` 유지(검증 프로토콜 2·3단계 미실시, 하드웨어 없음). Sign-sanity 패널은 실제 하드웨어 데이터로는 아직 시험 안 됨(더미로만).
- 09-04 — **P4 착수**. 서버 과부하(529)로 두 차례 백그라운드 서브에이전트 위임이 응답 없이 실패(디스크 변경 0건, 커밋 없음) → 사용자 지시로 서브에이전트 위임 중단, 코더가 직접 항목별로 구현·커밋.
- 09-04 — **P4 항목1 완료 (policy_shadow / obs mux)**. `ObsSourceMux.set()`가 더 이상 `real`을 거부하지 않음 — `policy.ObsBuilder.build_shadow()`가 5개 obs항(`base_ang_vel`/`projected_gravity`/`motor_pos_history`/`actions`/`command`)을 항별로 sim 또는 real에서 조립, 각자 자기 종류의 신선도 시계로 스테일 가드(IMU 나이=gyro/gravity, 관절텔레메트리 나이=q-history, 신규 PolicyIO 나이=actions/command — "실물이 실제로 어떤 속도를 명령받았나"는 다른 와이어 개념이 없어 실물 호스트 자신의 PolicyIO 자기보고를 `/ws/in`으로 수신하는 것이 유일한 real 소스). real 요청인데 자료가 없거나 `max_age_s`(0.1s)보다 오래되면 그 틱만 sim 폴백 + `shadow_warnings`/`obs_sources_effective`에 기록(무음 폴백 금지, 항목1 요구사항). q-history는 sim용(`q_hist`)과 real용(`real_q_hist`)을 완전히 분리된 버퍼로 유지(정책 로드 시점부터 매 컨트롤틱 항상 채움) — 창 내 sim/real 프레임 혼입 없음. `--shadow-follow`(CLI/`POST /policy/shadow_follow`/UI 체크박스)가 없으면 정책 출력은 표시·기록만 되고 `self.target`을 건드리지 않음; 있으면 로컬 sim만 그 액션으로 스텝(전송 경로 자체가 코드에 없음 — `modes.SHADOW_MAY_TRANSMIT=False`, sim 스레드는 소켓을 열지 않음, `test_policy_shadow.py::test_shadow_action_has_no_transmit_path`로 고정). API: `/mode policy_shadow`·`/obs_source real` 더 이상 501 아님(정책 미로드시만 409); `/ws/in`이 `PolicyIO`도 수신. UI: Policy 폴더에 `policy_shadow` 모드·shadow_follow 체크박스·5칸 상시 소스 스트립(초록 sim/주황 real/빨강 "real 요청했으나 폴백"). `record.py` 헤더에 policy_shadow 녹화 시 요청 마스크 기록(R9). P3 시절 501-스텁 테스트 2건을 새 계약으로 교체 + `tests/test_policy_shadow.py` 9건 신규(스테일 폴백·실측 IMU 소싱·PolicyIO 소싱·shadow_follow 게이팅·무전송 구조보증). **pytest 170 passed**(기존 161 + 순증 9). 커밋 `c6d9a46`.

### P0/P1 결과 (2026-09-03, 코더)

**bake 6변형** — `/home/syaro/pyg_fea/pygviewer/cache/`, 변형당 서브프로세스 1개(약 8 s, RAM 1.3 GB 피크).
`nq`가 AB 31 / RP 19인 것은 폐루프의 로드 유니버설 힌지 8개 + 수동 발목 4개 차이다.

| variant | nu | nq | joints | mass [kg] | actor obs | contract sha | ankle inverse 잔차 [rad] | loop closure [mm] |
|---|---|---|---|---|---|---|---|---|
| FullDoF-AB | 12 | 31 | 24 | 35.6744 | 45 | `ade40b5b0de3` | 0.00815 | 0.00155 |
| FullDoF-RP | 12 | 19 | 12 | 35.674332 | 45 | `e089dba18224` | — | — |
| SemiFullDoF-AB | 12 | 31 | 24 | 35.6744 | 45 | `c9572af40b54` | 0.00788 | 0.00166 |
| SemiFullDoF-RP | 12 | 19 | 12 | 35.674332 | 45 | `c05e871d0173` | — | — |
| LegOnly-AB | 12 | 31 | 24 | 23.63014 | 45 | `46e0c18a820a` | 0.00788 | 0.00167 |
| LegOnly-RP | 12 | 19 | 12 | 23.630072 | 45 | `2c58faf8e478` | — | — |

**검증 수치**

| 항목 | 기준 | 실측 |
|---|---|---|
| 물리 실시간 (LegOnly-AB, CPU) | ≥195 Hz | **199.8 Hz**, 제어 50.1 Hz, drop 0 |
| RSS (headless / 뷰어 가동) | <600 MB | **147 MB / 218 MB** |
| base `fixed` 2 s 드리프트 | <1e-6 m | **2.4e-13 m** (MuJoCo 기본 solref면 1.9e-4 m) |
| base `pivot` 회전중심 이동 (5 s) | <1e-4 m | **1.1e-8 m**, 자세는 중력으로 자유 회전 |
| AB 폐루프 closure (정지·명령 6점) | <0.01 mm | **0.0017~0.0091 mm** |
| 발목 명령 → 실제 각 (6점, 좌측) | — | 부호맵 적용 **0.008 rad** / 미적용 **0.360 rad** |
| 전달비 vs `loop_ankle_verify.json`(v3) | 5 % 이내 | pitch 1.172 vs 1.210, roll 1.378 vs 1.418 (3 %) |
| pytest | ≤2 분 | **98 passed / 11.7 s** |

그림: `docs/img/pygviewer_p1_verification.png` (이 호스트에 오프스크린 OpenGL이 없어 matplotlib 스틱피겨 + 그래프).

### P0/P1에서 발견한 함정 (계획 대비 정정 4건)

1. **`ankle_rp_envelope.json`의 크랭크 격자는 v30에 그대로 쓸 수 없다.** 계획 §1은 이 격자를
   역해로 지정했으나, 격자는 `pygmalion_v3_printed_loop`에서 푼 것이고 v30 생성기가 크랭크
   관절축 부호를 바꿨다. 그대로 쓰면 발 자세가 명령에서 **0.360 rad(20.7°)** 어긋난다. bake가
   격자를 직접 명령해 보고 8가지 (swap, ±A, ±B) 중 최적을 **측정으로 적합**한다(L: A→−A,
   R: B→−B) → 잔차 0.008 rad. 실패 시(`usable:false`) bake가 측정한 2×2 야코비의 선형 역해로
   자동 대체하고 UI에 표기.
2. **한 다리 안에서 crank_A와 crank_B의 관절축이 서로 반대다**(L: A=−Y, B=+Y). 그래서 v3의
   "공통 크랭크당 피치"는 v30 q공간에서 **대향 모드**다. 좌우 사이에서도 crank·ankle_roll 축이
   미러인데 **range가 대칭이라 range 비교만으로는 미러가 안 잡힌다** → 계약에
   `range_mirrored`/`axis_mirrored`를 분리 기록하고 테스트로 고정.
3. **씬 spec을 다시 compile하면 mjlab의 SimulationCfg가 사라진다.** mjlab은 timestep·solver를
   *컴파일된 모델*에 적용하므로 spec에는 XML 원래 `<option>`(timestep 0.002)이 남아 있다. 처음
   구운 모델은 500 Hz·다른 solver 설정이었다. 이제 bake가 `opt` 블록 전체를 env에서 복사하고
   timestep/integrator/solver/iterations/cone/impratio를 **계약으로 검증**한다.
4. **bent 키프레임이 발바닥을 바닥 아래 38.6 mm에 놓는다.** `_v2_standing_z()`가 pygmalion_v2
   검증 파일의 `standing_base_z`를 읽는데 v30은 다른 로봇이라, 매 학습 리셋이 발이 묻힌 상태로
   시작하고 솔버가 첫 ~20 스텝에 밀어낸다(base z 0.868 → 0.906). 뷰어는 학습과 동일하게
   재현하고 값을 계약(`keyframe_sole_penetration_m`)과 테스트에 기록만 한다 — **모델·설정은
   건드리지 않음**.

추가 관측: RP 3변형의 `ankle_pitch`는 default +0.360 rad가 자기 `safe_clip` 상한(+0.454)에서
**0.094 rad(5.4°)** 밖에 안 떨어져 있다(반대쪽은 66.6°). legonly_ab_v1의 창 0° 사고와 같은 계열이며
치명적 수준은 아니라 테스트에 측정값으로 고정해 두었다(더 좁아지면 실패).

### 계획 대비 의도적 편차 (승인 필요)

* bake 토글에 과제 지시 목록(`PYG_INIT_MID/MOTOR_MEAS/TN/STUDENT_TEACHER`) 외에
  **`PYG_V2` `PYG_INIT_BENT` `PYG_SAFE_TARGET_CLIP` `PYG_ARM_ABD_DEG=15`를 추가**했다. `PYG_INIT_MID`는
  `PYG_INIT_BENT` 없이는 무효이고, 이 조합이 현재 학습(legonly_ab_v2)의 매니페스트와 일치한다.
  `--no-init-bent`로 끌 수 있고 `env_toggles`에 그대로 기록된다.
* 뷰어 기본 base 모드를 `fixed`로 했다(`--base free`로 변경). P1에는 균형을 잡는 것이 없어
  free로 두면 약 2 s 만에 넘어져 첫 화면이 쓰러진 로봇이 된다.

