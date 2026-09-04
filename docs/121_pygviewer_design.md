# 121. pygviewer — Sim↔Real 비교 웹뷰어: 설계·결정·진행 로그 (2026-09-03~)

> 사용자 요청(09-03): 시뮬레이션 거동과 실물 로봇 거동을 같은 화면·같은 데이터 형식으로 비교하는 MuJoCo 웹 뷰어.
> 이 문서 = **설계 정본 + 진행 로그**(구현 코더가 각 phase 완료 시 §9에 기록). 승인 계획 원문:
> `~/.claude/plans/optimized-leaping-hamster.md`(로컬). 코드: `tools/pygviewer/`.

## 0. 요구 9항목 ↔ 구현 매핑

| # | 요구 | 구현 | Phase |
|---|---|---|---|
| 1 | 모델 3종×2분파(RP/AB) | bake로 6변형 `.mjb`+계약 JSON, UI 드롭다운 | P0 |
| 2 | base_link 고정(완전/회전자유, 위치 지정) | mocap 앵커 + `eq weld`(fixed) / `eq connect`(pivot, 사용자 오프셋 점) 런타임 토글, 높이 슬라이더, 지면 on/off. **09-04 추가: `string`(안전 테더)** — spatial tendon LIMITED [0,L0], z_set 아래서만 팽팽(단방향 캐치, 마운트 아님), 수평 항상 자유 | P1 (+string P1+, 09-04) |
| 3 | 중력 유지 | `m.opt.gravity` 불변(코드로 보장) | P0 |
| 4 | 관절 raw 모니터링 | Snapshot(q·qd·τ·target) 30 Hz 리드아웃 + 미러축 관절은 물리각 병기 | P1 |
| 5 | 관절 목표 q 입력 UI/API | 슬라이더+숫자 양방향, `POST /target`; AB는 발목공간 슬라이더(역해 그리드) + 크랭크 | P1 |
| 6 | 학습 weight 로드 | ONNX 러너 + `.pt→ONNX` bake(parity 검증) + `.pt` 직접 로드(mjlab 지연 임포트), 모델 계약 sha 일치 검사 | P2 |
| 7 | 선택 관절 플롯 | viser `add_uplot` 링버퍼 10 s@50 Hz, ≤8채널 | P1 |
| 8 | 텔레메트리 송수신 | 스키마 v1(JSON, sim 관절명·rad/SI·t_ns·seq·contract_hash), `WS /ws/out`·`/ws/in`, REST, OpenAPI+API.md; 뷰어→실물 명령은 **문서만** | P3 |
| 9 | 원격 모터값 주입(실물 뷰어) | HUPHY UDP(9870 포맷) 어댑터 + 명시적 12행 매핑표(브리지가 부호·영점·순서·deg→rad 담당), 더미 송신기, jsonl.gz 기록/재생, real_replay 모드 | P3 |
| + | 비교 모드 전부 | 동일 목표 시퀀스 응답비교(`compare.py`), 정책 섀도우(obs 항목별 sim/real 소스 mux, 전송 금지 하드코딩), 오프라인 재생 | P4 ✅ |

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

**[추가, 2026-09-04 ROM 클립 세션]** R6("default 계약 일치")·R3("null 결측·플래그, 값을 지어내지 않음")를
수신측 구동 지점까지 확장: `real_replay`/`file_replay`가 관절을 qpos로 스냅하기 직전(`sim_core.py
_update_replay_targets`), 받은 값을 관절의 **하드 MJCF range**(`joint_contract[name]["range"]`, R6가
말하는 소프트 `safe_clip`보다 넓은 절대 상한)로 클립한다. 이전엔 클립이 전혀 없어 실측
`range_violations L_knee 1373`(무캘리브/다회전 실물값이 qpos에 그대로 꽂힘)이 실제로 관측됐음.
원본 텔레메트리 값은 `RealState.q`에 그대로 유지(R3: 값을 지어내거나 지우지 않음, 플롯·위반카운트는
진실을 봄) — 클립은 오직 물리엔진에 먹이는 구동값에만 적용. NaN/inf는 "이번 틱 데이터 없음"으로
처리(R3의 null 규약과 동일한 정신: 절대 스냅하지 않음, 추측하지 않음). 폐루프 AB 크랭크는 원래도
qpos 스냅이 아니라 PD 타깃(소프트 safe_clip, hard range의 부분집합)이라 동작 변화는 없지만 클램프
집계는 동일하게 적용. 관절별 `replay_clamped_now`(이번 틱)·`replay_clamp_count`(누적)이
`/status`·`/snapshot`의 `telemetry` 딕셔너리에 별도 키로 노출(§0 R6/R3 관련 항목이지만
`telemetry.py`의 `range_violations` 자료구조 자체는 건드리지 않음 — 그건 다른 항목(A2)의 범위).
송신측(`/target`·`/ankle`)은 NaN/inf를 422로 거부, 응답이 `{requested, applied, clip_range}`로
정직화(이전엔 클립 "범위"만 돌려주고 실제 적용값은 숨겨져 있었음). 상세·테스트·커밋은 §9.

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
| P4 | 스크립트 플레이어·compare·obs mux·섀도우 | 지연 주입 더미 오버레이 png · 더미 IMU가 액션 변화 | ✅ 09-04 (offset 32.0ms vs 30ms 주입, Δaction 평균 0.270 rad, pytest 198) |
| 등록 | dashboard PORTS·start_all·README·launch.json·브리핑 | — | ✅ 22:20 (8094/8095) |
| UI v2 | 레이아웃 B 대시보드(7항목, §10) | `/` `/dash` 200 · 정적자산 4종 200 · `/presets` 왕복 · policy load→cmd0→policy_sim 시퀀스 · WS src=real 부가 프레임 | ✅ 09-04 (pytest 231, §10) |
| P1+ string | 안전 테더 base 모드(사용자 요청 09-04 01:20) | 낙하 캐치(z_set±0.02, 장력≈무게 231.8N±10%) · 기립중 슬랙(0N)→PD넘어짐 시 taut 전환·z≥z_set-0.02 유지 · 모드 왕복 NaN 無 · 6변형 계약에 tendon id | ✅ 09-04 (아래 §9, pytest 210) |

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

- 09-04 — **P4 항목2 완료 (동일 목표 시퀀스 플레이어)**. `modes.TargetScript`(스텁이었음)가 `{joint_names, rows:[[t_s, q...]], loop}`를 로드해 경과 sim시간 기준 선형보간; `SimCore.run_script`가 manual 모드에서 재생(정책/리플레이 모드 중엔 시작 거부, 비구동 관절명 거부), 이후 모든 `JointState`에 `run_id` 태그(스키마 `Header`에 신규 옵션 필드) — 같은 스크립트 파일을 실물 브리지로 재생한 녹화와 `compare.py`가 나중에 정렬할 수 있도록. `POST /script/run{path,run_id}`/`POST /script/stop` + 뷰어 최소 패널. 표본 스크립트 2개(`tools/pygviewer/scripts/`)를 구운 LegOnly-AB 계약의 실제 default_q/관절명으로 생성: `sine_hips_knees_1hz_20deg.json`(양쪽 hip_pitch+knee, 각자 자기 default 기준 1Hz·20° 진폭, 3s@50Hz), `step_knee_5x10deg.json`(L_knee_joint 10° 스텝 5회, 1s dwell) — 검증 프로토콜 ⑤(지연보정, 급경사 스텝엣지)·⑥(동일목표 오버레이)용. `tests/test_script_player.py` 11건(보간/루프/클램프, run_script 모드·관절명 가드, 자연종료시 run_id 해제, 녹화 run_id 왕복, REST 엔드포인트 2개). **pytest 181 passed**(항목1의 170에서 +11). 커밋 `9da79eb`.

- 09-04 — **P4 항목3 완료 (`compare.py`)**. 두 `record.py` jsonl.gz 녹화(헤더+JointState 행)를 직접 읽어 R11(contract_hash 불일치 시 `--i-know` 없으면 SystemExit 거부)·R9(base 모드/높이/지면/gains_source 상이 시 경고 배너, 거부는 안 함)·R5(공통 **절대** t_ns 기준 격자에서 상호상관으로 clock offset 추정 — 파일별 자기 시작시각 기준 상대시간으로 하면 지연이 재영점화로 상쇄되어 사라짐을 30ms 주입 합성테스트가 실제로 잡아냄: 첫 구현은 5ms만 반환했고 `_series_abs`로 절대시간 사용하도록 수정 후 통과, 세그먼트 분할 재추정으로 지터 프록시)를 구현. joint별 target/q/tau_est PNG(영어 라벨, sim 실선/real 점선)를 `docs/img/`에 저장. `tests/test_compare.py` 7건(합성 30ms+5ms지터 녹화로 오프셋 회수 15ms 이내, 계약불일치 거부/우회, 조건경고, PNG 출력, 관절 결측 graceful). **pytest 188 passed**(항목2의 181에서 +7). 커밋 `8be2921`.

- 09-04 — **P4 항목4 완료 (Gains diff 표, R7)**. `RealState`가 `JointState.gains`(스키마엔 P0/P1부터 있었으나 아무도 안 읽던 필드)를 저장; `SimCore.gains_table()`이 관절별 모터 기종(`joint_family`: RS03/RS04, 계약에 이미 구워져 있던 값 노출만 추가)·수신된 real kp/kd·5% 초과 시 플래그되는 real/sim 비율을 추가. UI Gains 폴더는 real 데이터가 있을 때만 확장 표를 렌더(없으면 기존 sim전용 표 유지)하고 플래그를 빨간 글씨로 표시, 매 readout tick마다 갱신(이전엔 패널 생성/소스전환 시에만 갱신 — 텔레메트리는 라이브로 들어오므로 정정). `tests/test_gains_diff.py` 3건(텔레메트리 전 real열 없음, 의도적 kp 불일치 플래그+kd 비플래그, 5%이내 비플래그). **pytest 191 passed**(항목3의 188에서 +3). 커밋 `1bd76bb`.

- 09-04 — **P4 항목5 완료 (`protocol.py`, 8단계 검증)**. §5의 자동화 가능 4단계(①정지영점·④속도sanity·⑤지연보정·⑧기록왕복)를 실행 가능하게 구현, 나머지 4단계(②③⑥⑦)는 절차·판정기준 텍스트만 출력하고 `MANUAL`로 표기(가짜 PASS 금지). 구현 중 `compare.estimate_clock_offset_ms`의 실버그 2건을 발견·수정: (a) 원시 레벨 상호상관은 사인파(항목3 검증)엔 맞지만 계단신호(스텝 트레이스)엔 틀림 — 평탄구간이 거의 모든 lag에서 자기자신과 상관되어 실제 에지 타이밍을 묻어버림(30ms 주입에 0ms 반환) → R5 문구("명령 에지 상호상관")를 문자 그대로 구현해 **그래디언트**로 교체(계단→뾰족한 스파이크, 사인→위상이동 코사인, 둘 다 깨끗한 피크). (b) 세그먼트별 지터 추정에서 무제한 'full' 탐색이 약한 에지를 가진 세그먼트에서 엉뚱한 먼 lag의 부엽에 걸림(5ms 주입에 한 세그먼트가 -965ms 반환) → ±300ms 탐색창 제한(전송지연은 물리적으로 초 단위가 될 수 없다는 타당한 사전지식) + 에지가 아예 없는(순수 dwell) 세그먼트는 전체창 에지에너지의 20% 미만이면 제외. `tests/test_protocol.py` 6건(단계순서·자동4단계 통과·수동4단계 미가장PASS·엄격예산으로 단계1 의도적FAIL·CLI). **실측(LegOnly-AB)**: 자동 4단계 전부 PASS — 정지영점 worst|dq|=0.0050rad/|dg|=0.0100, 속도sanity RMS=0.0002rad/s, 지연보정 주입30ms→추정 **정확히 30.0ms**·지터 0.0ms(dt=0.005s 양자화 하한, 15ms 예산 이내), 기록왕복 바이트동일. **pytest 197 passed**(항목4의 191에서 +6). 커밋 `4e97c11`.

- 09-04 — **P4 항목6 완료 (실측 검증 수치)**. 라이브 2-프로세스 방식(스크립트를 실제 소켓으로 별도 SimCore에 더미송신)을 두 차례 시도했으나 셸/서브프로세스 기동 타이밍 스큐가 수백ms~수초 단위로 30ms 신호를 압도(같은 머신의 CLOCK_MONOTONIC은 프로세스간 공유되어 절대시간 가정 자체는 타당 — 문제는 순수 기동 타이밍 정밀도이지 알고리즘이 아님, 기록만 하고 채택 안 함). 대신 `record.Recorder`/`schema.JointState` 실제 코드 + `bridge/dummy_tx.py`의 실제 `ScriptSource`+지연/지터 모델을 직접 사용(재구현 아님)해 sim 기록·real 기록을 생성 → `compare.py` 실행: **`step_knee_5x10deg.json`**(급경사 에지)로 주입 30ms/5ms지터 → 추정 **offset=32.0ms**(지터std 1.41ms, 주입 지터 이내) — `docs/img/compare_p4item6_step_dummy30ms_L_knee.png`. `sine_hips_knees_1hz_20deg.json`은 스크립트 자체 원본샘플이 50Hz(20ms) 격자라 30ms지연 분해능이 낮아 offset~8ms만 나옴(오버레이 시각화용으로만 유지, ms정밀 주장은 스텝스크립트 결과에 근거) — `docs/img/compare_p4item6_dummy30ms_{L,R}_{hip_pitch,knee}.png` 4장. `compare.py`에 `--offset-dt`(기본 5ms, 기존 10ms 기본값은 30ms 신호 분해에 조악) 추가 + 범례 경고 가드. **정책 섀도우 IMU tilt**: 10° 기울임 더미 IMU를 `base_ang_vel`/`projected_gravity`에 real로 라우팅 → 동일 sim상태·명령에서 baseline 대비 **평균|Δaction|=0.270 rad(raw action), 최대 0.912 rad** — 명백히 유의미(회귀테스트로 0.02rad 초과 고정, `test_policy_shadow.py` +1건). `protocol.py` 자동 4단계 여전히 PASS(항목5와 동일). **pytest 198 passed**(항목5의 197에서 +1). **RSS**: headless 5s **147 MB**, 라이브 운영 뷰어 프로세스 **226 MB** — 둘 다 300MB 예산 이내. 커밋 `22088f1`.
- 09-04 — **§6 표 갱신**: P4 행을 ✅로 표시(위 항목1~6 완료), 요구매핑표 §0 '+' 행도 완료로 갱신.

- 09-04 02:20 — **base 모드 `string`(안전 테더) 완료** (사용자 요청 01:20: "위에서 가상의 끈이 잡고 있는 모드. z_set 아래로 내려가면 팽팽해져 받쳐주고, 그 위에서는 느슨해져 스스로 서 있어야 함"). 기존 free/fixed/pivot과 같은 계열, MuJoCo 표준 메커니즘(spatial tendon LIMIT)으로 구현 — 손수 힘 법칙을 쓰지 않음.
  - **bake.py**: 6변형 모두에 `pyg_string_anchor` 사이트(기존 `pyg_anchor` mocap 바디 위) + `pyg_string_hook` 사이트(base_link 원점, 런타임에 `site_pos`로 이동 — `base_pivot`의 `eq_data` 오프셋 재작성과 같은 기법) + `pyg_string` 2-사이트 spatial tendon 신규. 텐던은 `limited=false`로 구워 비활성(weld/pivot의 `active=False`와 같은 관례), `range=[0,L0]`(L0=1.0m), `solref_limit=(0.02,1.0)`(weld/pivot의 (0.002,1.0)보다 10배 완만 — 급낙하 충격 흡수). 계약에 `string_rig{tendon_id,anchor_site_id,hook_site_id,L0,solref_limit}` 신규 필드, `CONTRACT_VERSION` 1→2(필수 필드 변경이므로).
  - **sim_core.py**: `BASE_MODES`에 `"string"` 추가. `string` 모드에서 mocap 앵커의 world Z = `z_set + L0`(고정), (x,y)는 모드 진입 시점의 base (x,y)에 고정(기본, 실제 끈처럼 그네 운동 허용) 또는 `follow_xy=True`면 매틱 base (x,y) 추적(수직 레일, 그네 없음). `set_base(z_set=, hook_offset=, follow_xy=)` 신규 파라미터. 텐던 장력은 계산이 아니라 MuJoCo 솔버가 실제로 쓴 라그랑주 승수를 `d.efc_force`(제약타입 `mjCNSTR_LIMIT_TENDON`)에서 직접 읽음 — 슬랙일 땐 정확히 0.0(비활성 제약은 efc 행 자체가 없음). `Snapshot["string"] = {z_set,length,ten_length,taut,tension_N,hook_offset,follow_xy}`. mjviser는 텐던을 캡슐로 네이티브 렌더하므로(`tendon_width`/`tendon_rgba`) 커스텀 3D선 코드 없이 팽팽=빨강/슬랙=회색을 실시간 반영(`_string_status`가 매 publish마다 `tendon_rgba` 갱신), 다른 모드에서는 alpha=0으로 숨김.
  - **api/schema/ui**: `BaseState.mode`/`BaseIn.mode`에 `"string"` 추가(스키마 변경 불가피 — 안 하면 `/status`가 pydantic ValidationError로 즉시 깨짐), `BaseIn`에 `z_set/hook_offset/follow_xy`, `Status.string` 필드. UI Base 폴더에 `string` 라디오, Z_set 슬라이더(0.3~1.2m), pivot/hook 오프셋 xyz 공용 필드, follow_xy 체크박스, "z_set/길이/taut·slack/장력N" 실시간 마크다운. `__main__.py`에 `--base string`/`--string-z-set`/`--string-follow-xy`. `record.py` 헤더·`compare.py`의 R9 조건경고에 `z_set` 포함.
  - **물리 검증(격리 테스트, 로봇 없이)**: 23.63kg 점질량을 동일 텐던 리그로 낙하시켜 z_set=0.6에서 정착 오차 0(부동소수 잡음 수준), 장력 = 무게(231.8103N)를 6자리까지 정확히 재현 — 이 결과로 sim_core 배선을 신뢰하고 실모델로 확장.
  - **실측(LegOnly-AB, tests/test_string_mode.py)**: (1) 지면 off, 0.9m에서 낙하, Z_set=0.6 → 정착 z **0.6±0.001m**(20샘플 std<0.01), 정지 후 평균 장력 **231.8N** 근방(허용 10%, 로봇 자중과 일치) — 매달림 확인. (2) 지면 on, 기립 자세, Z_set=기립높이−0.15m → 시작 시 **슬랙(0N, taut=False)** 확인, 정책 없이 PD만으로 넘어지기 시작 → 텐던이 taut로 전환된 이후 매 샘플 `base z ≥ z_set−0.02m` 유지 확인. (3) string→fixed→free→string 왕복에서 NaN 無, `eq_active`/`tendon_limited` 잔류 無. (4) `hook_offset`이 실제 `site_pos`를 이동시킴, `follow_xy`가 수평 오프셋에도 앵커를 base 위에 유지. 신규 6개 + `test_bake_contract.py` 확장(6변형 모두 `string_rig` 존재·id 상이) 6개 = **pytest 210 passed**(기존 198 + 12), 6변형 재bake 전부 성공(변형당 ~7-9s). 기존 LegOnly-AB baked policy 2개(model_700/model_5200)는 모델 재bake로 contract_sha가 바뀌어 재bake 필요했음(예상된 부작용, 즉시 재baked·재검증).
  - **라이브 API 종단검증**: 별도 포트(18094/18095)에 재기동 → `POST /base {mode:string,z_set:0.6,ground:false}` → `GET /status`에서 `base.mode=string`, `string.taut=true`, `string.tension_N`(토폴된 자세라 순수 수직이 아니어서 166.8N — 각도 고려하면 정상) 확인 후 종료.
  - **함정**: (a) `contract_sha`가 `bake_utc` 타임스탬프를 포함해 매 재bake마다 바뀜(기존 설계) → 재bake할 때마다 그 변형에 물린 정책도 다시 구워야 함, 처음에 1번 놓쳐서(스크래치 디렉터리 시험bake) 다시 정합. (b) MuJoCo 텐던 LIMIT은 단방향(로프)이라 range=[0,L]이 정확히 "그 이상 못 벌어짐"을 뜻함 — 스프링이 아니므로 슬랙 구간엔 힘이 전혀 없음, 설계 그대로.
  - 6변형 재bake(캐시, git 비포함) 완료, 뷰어(8094/8095) 재기동 완료. 커밋 `12ca371`(코드+테스트), 이 문서/README/API.md 갱신은 뒤이은 커밋.

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
- 09-04 01:15 — **P0~P4 전부 완료(계획자 스팟체크)**: API 25 엔드포인트(/script/run·/policy/shadow_follow·/replay/* 포함) 노출 확인, compare 오버레이 png 3장 존재, P4 커밋 7건(c6d9a46…db25e5c) 확인, 뷰어 8094/8095 200. 실물 필요 단계(프로토콜 ②③⑥⑦)는 하드웨어 연결 후.

- 09-04 03:35 — **어깨 외전(arm abduction) 부호 버그 수정, mjlab 상수 파일**(사용자가 FullDoF/SemiFullDoF 뷰어 초기자세를 직접 보고 발견 — 이번엔 pygviewer 코드가 아니라 `mujoco-sim/mjlab/.../pygmalion_constants.py`가 원인). 상세 근본원인·수치는
  `docs/reward_research/2026-09-03_stiff_knee_root_cause.md` §3c "09-04 해소" 참조 — 요약:
  `get_spec()`/`_bent_joint_pos()` 두 함수가 `shoulder_roll` 외전 부호를 서로 반대로
  하드코딩해뒀고, v30 모델은 그 중 어느 쪽을 써도 한쪽 팔은 외전·다른쪽은 내전되는 상태였다.
  신설 `shoulder_roll_abduction_sign()`(관절 range에서 부호 유도, 대칭 range면 레거시 −1
  폴백)로 두 함수를 통일. v3/v4 레거시 결과는 소수 5자리까지 불변(Δ0) 확인. mjlab 커밋
  `d8421b9`(별도 저장소 — `git diff --submodule=log`로 부모 저장소에 포인터 반영).
  **pygviewer 쪽 물리 검증**: `tools/pygviewer/tests/test_arm_abduction.py` 신설 — baked
  FullDoF-AB/RP·SemiFullDoF-AB/RP 4변형에 대해 mj_forward 후 양팔의 world-y 오프셋이 어깨
  기준 바깥쪽(외전)인지 직접 확인. 재bake 전 FullDoF-AB/RP 2개에서 실제로 FAIL(왼팔이
  중심선 쪽으로 접힘)하는 것을 먼저 확인한 뒤 4변형 재bake(+LegOnly-AB/RP도 소스해시
  갱신 때문에 재bake, LegOnly-AB에 물린 정책 2개도 재bake) → pytest 214 passed(기존 210
  + 신규 4). 뷰어(8094/8095) 재기동, contract_hash 갱신 확인.
  **함정**: `mujoco-sim/mjlab`에서 `make format`(프로젝트 전체에 `ruff format`+
  `ruff check --fix`)을 실행했더니 무관한 파일 260여 개가 스타일 변경으로 잡혔다 — 그 중
  일부(`.gitignore`, `analysis/watchdog.sh`, `analysis/out/watchdog_runs.json`)는 진짜
  기존 미커밋 작업(실행 중인 watchdog이 계속 쓰는 로그 포함)이라 **되돌리지 않고 그대로
  둠**(git checkout 등 되돌리기 명령을 쓰지 않음 - 데이터 손실 위험 판단). 내가 의도한
  `pygmalion_constants.py` 변경은 AST 비교(ast.dump 전/후 diff)로 "정확히 이 3군데 함수
  변경 외에는 전부 서식뿐"임을 확인한 뒤 그 파일만, 그리고 신규 테스트 파일만 스테이징해
  커밋 — 나머지 260여 개 파일은 작업트리에 커밋되지 않은 채로 남아 있음(사용자/다음 세션이
  판단해 처리할 것).

## 10. UI v2 — 레이아웃 B 결정·구성 (2026-09-04, 코더)

사용자 요청(09-04): 기존 viser 패널 UI를 7항목(레이아웃·플롯·Joints·Policy·Obs·Gains·좌측탭+상단바)으로
개선. 3안(A/B/C) 목업(`tools/pygviewer/mockups/layout_{A,B,C}.html`) 중 **B 확정**(코드 리뷰 커밋
`0bbaa15`의 메시지에 기록).

**구성 = 레이아웃 B(FastAPI 자체 대시보드)**: `GET /`·`GET /dash`가 서빙하는 단일 HTML+JS
(`pygviewer/static/dashboard.{html,js}`), CDN 없이 로컬 번들(`pygviewer/static/vendor/`에
three.js r150·uPlot 1.6.30 — 이 LAN은 인터넷이 없음). 3열 그리드: 상단바(38px, variant·mode·base·
경고배지·rates) / 좌측 세로탭(250px, Model·Base link·Telemetry/Record·Script·Status) / 중앙
viser iframe(기존 패널 유지, 디버그용) / 우측 탭(340px, Control·Gains·Obs) / 좌+중 하단 플롯
스트립(320px).

**항목별 구현**(상세 근거·수치는 커밋 `5fc9d22`(백엔드 배선)·`0da1e4c`(대시보드)·`984ef7d`(테스트)):
1. **레이아웃** — 위 그리드. 모든 패널이 같은 origin(상대 fetch/WS)이라 주소 하나로 전부 동작.
2. **Joints** — 관절별 슬라이더+숫자(범위=계약 safe_clip), deg/rad 토글(내부·와이어는 항상 rad),
   미러 관절은 `travel_sign×q` 물리각 병기, AB 발목 foot-space 슬라이더(범위는 계약의
   `ankle_inverse.pitch_deg/roll_deg`에서 직접 — 신규 엔드포인트 불필요), 향후 실물 송신용
   "TX (HW)" 비활성 체크박스 자리(docs/123, 이번 범위 밖).
3. **Obs** — 정책의 45차원 관측을 항목별 막대(gyro3/grav3/q-hist24/last_action12/cmd3, 차원은
   `POST /policy/load` 응답의 `layout`에서 직접 취함 — obs_terms를 재정의한 정책도 안전),
   요청/실효 소스로 색분류(초록 sim/주황 real/빨강 "real 요청·sim 폴백"). 아래에 three.js
   위젯(바디 X/Y/Z축이 `Status.base.quat`로 회전, projected gravity·gyro 벡터, real IMU는
   `Status.telemetry.imu`가 있으면 반투명 병기).
4. **Policy** — `GET /policy/list` 드롭다운 + load 버튼이 `load→cmd(0,0,0)→mode=policy_sim`
   순서를 그대로 수행(이 시퀀스는 `tests/test_dashboard.py::test_policy_load_then_cmd_zero_then_
   mode_policy_sim`이 실제 API로 고정), vx/vy/wz 슬라이더, policy_sim/policy_shadow 전환,
   shadow_follow, 항목별 obs source 드롭다운+5칸 스트립, stop/unload. Control 탭의 Joints⇄Policy
   상호배타 토글은 **JS에서만** 처리(Joints로 가면 mode=manual, Policy로 가면 로드돼 있고
   idle/manual이면 mode=policy_sim 재개) — `sim_core.py`의 모드 시맨틱은 손대지 않음.
5. **Gains** — kp/kd 표(편집 즉시 `POST /gains`), train/real/custom 프리셋 선택(신규
   `GET/POST /presets`+`POST /presets/apply`), "다른 이름으로 저장", real 텔레메트리 수신 시
   real_kp/real_kd/비율/플래그 열.
6. **플롯** — 최대 3개 토글 행(q+target/tau/qd), 관절 **종류**당 uPlot 패널 1개(hip_pitch·
   hip_roll·hip_yaw·knee·crank_A·crank_B — `action_joint_names`에서 일반화 도출이라 RP의
   ankle_pitch/roll에도 그대로 맞음), 한 패널에 L/R 겹쳐그림(파랑/주황), target 점선, real은
   같은 sim 시간격자에 반투명 병기(real은 latest-only라 sim JointState 틱마다 "그 순간 가장
   최근에 본 real 값"을 같이 기록 — uPlot 한 차트에 x축 두 개를 둘 필요가 없어짐). 5/10/20/60s
   창, 클릭 시 확대 모달.
7. **좌측 탭+상단바** — Model(변형 read-only — 이 프로세스는 평생 baked 모델 하나만 가짐·contract
   sha·재로드), Base link(free/fixed/pivot/string, 모드별 height 또는 z_set, pivot/hook 오프셋,
   지면, string 장력, home/knees_bent 리셋), Telemetry/Record(rx rate/age/clock offset/jitter,
   `side_mapping_verified` UNVERIFIED 배너, record/replay), Script(샘플 스크립트 2개 run/stop),
   Status(rates·RSS·경고).

**백엔드는 기존 스키마에 추가만**(214개 기존 테스트 무변경 전제): `Status.imu`(sim
gyro/gravity, ObsBuilder와 같은 센서에서 유도)·`Status.side_mapping_verified`(joint_map_huphy.json
플래그)·`GainsIn.clear_overrides`(오버라이드 초기화, 기본 False)·`GET/POST /presets`+
`POST /presets/apply`(train=계약값/real=HUPHY kp10·kd1 균일/custom=저장 파일)·`WS /ws/out`이
JointState 요청 시 real 텔레메트리가 한 번이라도 왔으면 `src="real"` 프레임을 하나 더 보냄(기존
스키마 재사용, 아무것도 안 붙어 있으면 완전히 무변화).

**검증**(브라우저 없는 이 호스트의 대체 경로 — README에 이미 문서화된 방식): 뷰어 재기동 후
curl로 `GET /`·`/dash`·정적자산 4종 200, `/presets` 저장→적용 왕복, policy load→cmd0→policy_sim
시퀀스가 `/snapshot.policy.driving=true`로 이어짐을 실측; python `websockets` 클라이언트로
`/ws/out`이 평소엔 `src=sim`만 보내다가 `bridge dummy --imu`로 3초 텔레메트리를 주입하자
`src=real` JointState(수신 관절만 값, 나머지 null)와 `Status.telemetry.imu`가 즉시 나타남을
확인. **크롬 익스텐션이 이 호스트에서 연결되지 않아**(직접 시도해 확인) 실제 브라우저 렌더링·
uPlot/three.js 시각 결과는 미검증 — 미해결 항목으로 남김(§ 아래).

**의도적 스코프 경계**: 실물(HUPHY) 송신은 이 작업 범위 밖(`docs/123_pygviewer_tx_design.md`가
별도로 3안 검토 중 — 사용자 결정: HUPHY 코드 비침습, 안 A 1차 벤치 실험). Joints 탭의 TX 체크박스는
그 작업이 실제로 뭔가를 보낼 수 있게 되기 전까지 자리만 잡아둔 비활성 표시.

**미해결**: (a) 실제 브라우저 렌더 확인 없음(레이아웃 깨짐·CSS 오버플로·uPlot/three.js 렌더 실수는
코드 리뷰로만 잡음, 스크린샷 없음). (b) 모델 변형 드롭다운은 read-only(런타임 hot-swap은 SimCore가
프로세스당 모델 하나를 소유하는 현재 아키텍처를 바꿔야 해서 이번 범위 밖으로 명시적으로 남김).
(c) obs 항목의 실효 소스(`obs_sources_effective`)는 250ms 폴링(`/snapshot`)이라 WS 50Hz보다 느림 —
플롯/joints 갱신보다 5~10배 느린 배지 하나뿐이라 감수.

### TX(실물 송신) UI — 안전장치 스텁 (2026-09-04, 대시보드 작업 중 병행 지시)

사용자 확정(`docs/123_pygviewer_tx_design.md` §4): 대시보드에 실물 송신 제어를 추가하되, 다른 코더가
`bridge/tx_client.py`(50Hz UDP 송신)와 `JointTarget` 실제 구현을 만들고 있었음. 착수 전
`git log -- tools/pygviewer/pygviewer/bridge` 확인 결과 그 시점엔 미도착(P3 수신측 브리지만
존재) → 지시대로 **인터페이스 가정 최소화 + 스텁**으로 구현(커밋 `152aad2`). 작업 도중 다른
코더의 커밋(`c96a15e` JointTarget 실제 구현, `dfdb7b0` `tx_map.py` 부호/단위 역변환)이 같은
`main`에 도착했으나, `bridge/tx_client.py`(실제 송신기) 자체는 이 문서 작성 시점까지도 미도착 —
내 스텁은 여전히 유효한 경계 설계(스텁의 `send()`가 하는 일은 "sim-rad 목표값 기록"까지이고, HUPHY
단위·부호 변환은 이미 브리지 쪽 몫으로 설계돼 있어 재작업 불필요).

**구성**: `pygviewer/tx.py`의 `TxState` — 무장(arm)·해제·하트비트·모터별 활성화·전송의 상태기계이지만
**아무 바이트도 실제로 내보내지 않음**(모듈 docstring에 명시). 안전 요구(정책 출력 절대 송신 금지)는
**구조적으로** 강제: `arm(mode,...)`는 `mode != "manual"`이면 거부, `SimCore._on_control_tick`이 매
제어틱(50Hz)마다 `check_mode_gate(mode)`를 호출해 모드가 manual을 벗어나면 API 호출과 무관하게
즉시 무장 해제(`modes.SHADOW_MAY_TRANSMIT`와 동일한 "체크박스가 아니라 구조" 패턴). `send()`는
`active()`(무장 AND 하트비트가 `DEADMAN_TIMEOUT_S=0.3s` 이내)가 아니면 거부, 활성화되지 않은
모터는 조용히 드롭. 신규 엔드포인트 `POST /tx/{arm,disarm,heartbeat,motor,send}` + `GET /tx/status`.

**대시보드**: Telemetry/Record 탭에 TX 섹션(host:port, 2단 arm — 활성화 토글→ARM 버튼, 상태 배지,
12개 모터별 체크박스, kp/kd 상한 표시(docs/123 §3 벤치 실험값 5/0.5, 표시 전용)). 키보드 데드맨은
Space를 누르는 동안만(텍스트 입력 포커스 시 제외) `/tx/heartbeat`+`/tx/send`를 20Hz로 호출, 떼면
클라이언트에서 즉시 중단(서버 0.3s 타임아웃은 백스톱). 플롯의 q/target 행에 "sent target" 계열(점선,
자홍/청록) 추가 — 250ms `/tx/status` 폴링 결과를 real 텔레메트리와 같은 방식으로 sim 시간격자에
병기.

**검증**(라이브 curl): mode=idle에서 arm 409 → `/mode manual` 드레인 후 200 → 두 관절 값을 보냈지만
한쪽만 활성화 상태라 `sent`에 한 관절만 포함 → mode를 idle로 되돌리자 **한 제어틱 안에** 자동
무장해제(`disarm_reason: "mode changed to 'idle' while armed"`), 클라이언트 조치 없이. pytest
13건(대부분 순수 파이썬 TxState 유닛테스트, SimCore 인스턴스는 API/틱-연동 확인용 2건에만 —
test_dashboard.py에서 SimCore 인스턴스를 많이 만들면 전체 스위트 RSS 상한을 넘긴다는 걸 배워서
반영). 미검증: 실제 브라우저(키 입력 체감, 레이아웃)는 이번에도 확인 못함.

**[후속 완료, 2026-09-04 배선 세션]** 위 스텁이 실제 `bridge/tx_client.py`에 배선됨. 엔드포인트가
`{arm(host,port 포함), motor, send}` → `{config, enable, arm, disarm, heartbeat, status}`로
재설계(송신은 이제 `SimCore._on_control_tick`이 매 제어틱 자동 수행, 대시보드는 `/tx/send`를 더
이상 호출하지 않음), 대시보드 TX 섹션도 새 계약으로 전면 재배선(kp_max/kd_max/ttl_ms 입력,
"configure" 1단계 추가, 상태 배지가 armed/sending 구분 표시, seq·rate_hz·rejected_count·
arm_token 표시). 데드맨은 `DEADMAN_TIMEOUT_S=0.3s` 초과 시 disarm이 아니라 "hold"(새 패킷만
중단)로 재확인. 상세·실측 왕복 수치(dummy_rx 실제 UDP, ±2도 수렴, 하트비트 중단 0.3s 내 정지,
policy_sim 자동 disarm, enable 밖 관절 미송신)는 docs/123 §6. pytest 스텁 전용 13건 폐기 →
`test_tx_wiring.py` 18건으로 교체, 전체 스위트 343 passed. Joints 탭의 TX 체크박스도 "미래
작업 자리표시자"에서 Telemetry 탭 TX 설정의 읽기전용 미러로 의미가 바뀜.

### "L/R 관절이 같이 움직인다" 버그 조사 (2026-09-04, 대시보드 작업 중 병행 지시)

사용자가 이전 세션에 겪은 현상. 실제 재현·조치는 커밋 `a9a4a14`(상세 원인·수치는 그 커밋 메시지와
`tests/test_target_independence.py` 참조). 요지: **`/target`·`/ankle`의 커맨드 라우팅 자체엔
버그가 없음**(base=fixed·ground=off에서 소수점 6자리까지 완전 독립 재현). 사용자가 본 것은 두 가지
실제 물리 현상 중 하나였을 가능성이 큼 — (a) base=fixed+ground=on일 때 bent 키프레임 발이 바닥에
~38.6mm 파묻혀 양다리가 각자 독립적으로(그러나 동시에) 흔들림, (b) base≠fixed(예: free/string)일
때 한쪽 다리에 큰 목표를 주면 부유 베이스의 반작용으로 반대쪽 다리의 **실제 q**(목표는 아님)가
실제로 흔들림(뉴턴 3법칙, 버그 아님). 회귀 테스트로 고정(base=fixed+ground=off 조건에서 교차-다리
q 불변 확인, 같은-다리 결합은 의도적으로 별도 취급).

- 09-04 — **송신 경로(안 A) 구현** (다른 코더, docs/123 병행 문서). `tools/pygviewer/pygviewer/bridge/`에
  `tx_map.py`(sim rad→HUPHY cal-deg 역변환)·`remote_target.py`(arm/seq/데드맨 상태기계)·`dummy_rx.py`
  (huphy 없는 로컬 왕복 대상, 1차 PD 모터모델)·`huphy_remote_motion.py`(로봇측 스크립트, huphy는
  `run_real()` 내부에서만 지연 임포트)·`tx_client.py`(뷰어측 송신 라이브러리) 신규, `schema.py`의
  `JointTarget`에 `arm_token`/`origin`(Literal, "policy" 생성 자체를 거부)/`tau_ff` 추가. 이 문서의
  §1("수신 전용") 결정은 **메시지 자체**에는 더 이상 유효하지 않음(§3의 "receive only" 설계 의도 —
  뷰어가 명령하지 않는다 — 는 여전히 유효: 송신은 `origin=manual/script`로만, `api.py`/`ui.py`는
  이 세션에서 손대지 않았고 실제 UI 연결은 별도 작업). 상세·검증 수치·HUPHY 인터페이스 갭은
  docs/123 §5. pytest 89건 신규, 전체 333 passed(~30s). `api.py`/`ui.py`/대시보드는 건드리지 않음.
- 09-04 12:45 — **장애: 뷰어 프로세스 2개 동시 가동**(11:25·12:27 시작; 코더 재기동 시 기존 프로세스 미종료) → 사용자 "Policy 로드 안 됨" 신고. API 재현: load 200·mode 200이나 UI/3D 불일치 가능. 단일 인스턴스로 재기동(pid 996139, 8094/8095 동일 프로세스 확인), 정책 load→policy_sim 정상(|action|max 5.3). 재발 방지: pidfile+포트 선점 검사를 run.py에 추가하도록 지시(배선 코더). 교훈: pkill/pgrep 패턴은 앵커(`^…python3 tools/pygviewer/run.py`)로 — 문자열 포함 패턴은 호출 셸 자체를 죽임(exit 144 재현 2회).

- 09-04 (배선 세션) — **안 A 마무리: TX 대시보드 실배선 + pidfile 재발방지 + Policy 패널 UX**. (1)
  `pygviewer/tx.py`/`api.py`/`dashboard.{html,js}`를 실제 `bridge/tx_client.py`에 연결(엔드포인트
  재설계, 데드맨 3-노브 재설계, 실 UDP 왕복 검증) — 수치는 docs/123 §6. (2) 12:45 장애의 재발방지
  지시 이행: `pygviewer/__main__.py`에 `PID_FILE`(`tools/pygviewer/logs/pygviewer.pid`, PID
  liveness 확인 — 죽은 프로세스의 stale pidfile은 자동 회수) 추가, 기존 `port_free()`와 이중화;
  README에 안전 재기동 절차(comm 필터링으로 pkill/pgrep 자기잠금 방지) 추가. (3) 사용자 UX 지적
  (12:55, "Load UI가 안 보임" — `<select style="flex:1">`이 옵션 텍스트 길이 때문에 최소폭을
  줄이지 못해 `btn-pol-load`가 시각적으로 밀려남): Policy 패널을 select(ellipsis+title)+새로고침
  버튼 / 전폭 "Load & Run" 버튼(로딩 중 표시, 실패 시 토스트+영구 빨간 텍스트 둘 다) / 로드상태
  배지 / Run·Stop(idle) 토글+Unload / 접힘 경로직접입력 5행 구조로 재구성. 검증은
  `tests/test_policy_ui_contract.py`(3건, `/policy/load`의 400/404/409가 모두 표시가능한 문자열
  `detail`을 반환함을 확인 — 이 저장소엔 JS 테스트 러너가 없어 프런트 순수함수
  `policyLoadErrorText`는 백엔드 계약 테스트로 대체 검증, 별도로 기록해둠). 전체 스위트 343
  passed. 뷰어 재기동(단일 인스턴스, pidfile 생성 확인).

- 09-04 — **A4: 플롯에 실물 텔레메트리가 안 보이는 버그 수정** (`dashboard.js`만, 계획
  `optimized-leaping-hamster.md` A4). 원인: 6항목 플롯 패널이 sim 계약의 `action_joint_names`에서
  뽑은 관절 **종류**로만 만들어지고(`buildPlotGrid`), 데이터 조회도 `L_${kind}_joint`/
  `R_${kind}_joint` 템플릿을 **다시 추측**(`seriesArraysFor`)해서 썼음 — real 프레임은
  `onJointState`가 정상 수신·버퍼링(src="real" → `S.latestReal` → 링버퍼 realQ/realQd/realTau)
  했지만, sim 계약에 없는 관절명(브리지 매핑 실패·벤치 전용 관절)이 real로 오면 패널 자체가 없어
  조용히 사라짐. 추가로 velocity(qd) 행은 애초에 real 계열이 **정의돼 있지도 않았음**
  (ROW_META.qd에 real 라벨 누락 — 코드 확인으로 발견, sim 계약 일치 여부와 무관하게 항상 안 보임).
  수정: 패널 구성을 sim ∪ 관측된 real 관절명 합집합으로(`panelsFor(simNames, realNames)`, DOM 없는
  순수 함수, L/R 페어 유지·미매칭은 단독 패널+"real only" 배지), `seriesArraysFor`/`openModal`은
  그 패널이 실제로 만들어진 Lname/Rname을 그대로 읽음(재추측 제거로 구성-조회 불일치 가능성 소거),
  qd 행에 real 계열 2개 추가, 범례에 "sim" 명시(`L q sim` 등), 새 real 관절명이 나중에 도착해도
  자동 재구성(`realJointNames.length` 변화 감지), rx_count=0일 때 플롯 영역에 "no real stream"
  한 줄 표시(있으면 "real stream: rx {hz}/s"). 검증: 이 호스트에 브라우저/Node가 전혀 없어(재확인,
  `esprima` 4.0.1로 파일 전체 파싱 성공만 확인 — 미관련 기존 `??`/`?.` 문법은 esprima probe에서만
  중립화) **브라우저 렌더는 이번에도 미검증**; 순수함수 `panelsFor`의 로직을 Python으로 동일
  재구현해 4개 시나리오(벤치 단일 `L_knee_joint`/사전 미정의 이름 `knee_bench`/L·R 컨벤션은
  맞지만 계약에 없는 `L_ankle_twist_joint`/무 real 스트림) 수동 검증 — 라이브 뷰어(8095)의 실제
  벤치 케이스는 `L_knee_joint`가 sim 계약에도 있어 기존 코드로도 이름 매칭 자체는 됐었다는 것도
  이번에 확인(그래도 qd 누락·비표준 이름 케이스·범례 불명확은 실제 결함이었음). 서버는 재기동
  안 함(`/static/dashboard.js`가 디스크에서 매 요청 재서빙됨을 curl로 확인, 코드 변경이 바로 반영).
  pytest 전체 348 passed(회귀 없음, 다른 코더 작업으로 343→348).

- 09-04 — **A1/A3: 송신·수신 API 엔드포인트 ROM 클립 일관화** (계획 `optimized-leaping-hamster.md`
  A1/A3, A2·A4는 병행 작업하는 다른 에이전트 범위라 `static/dashboard.js`·`telemetry.py`의
  `range_violations` 자료구조는 손대지 않음). 배경: `/target` 송신측은 이미 `safe_clip`으로
  클램프되지만, **수신측**(`sim_core.py _update_replay_targets` → `_substep`의 qpos 스냅)은 클립이
  전혀 없어 실측 `range_violations L_knee 1373`(무캘리브/다회전 값이 qpos에 그대로 꽂힘, 폐루프 AB
  모델 solver 불안정 위험)이 나왔음.
  **(1) 수신측**: direct-drive 관절(hip/knee/RP-ankle)을 qpos 스냅 직전 하드 range로 클립
  (`sim_core.py:202` 부근 `range_lo/range_hi` 신설, `_update_replay_targets` 재작성). NaN/inf는
  "이번 틱 데이터 없음"으로 취급해 절대 스냅하지 않음(차분 테스트로 "무텔레메트리와 비트동일"까지
  확인). 폐루프 AB 크랭크는 기존 소프트 safe_clip 그대로(hard range의 부분집합이라 동작 변화
  없음)지만 하드 range 기준 클램프 집계는 추가. `replay_clamped_now`/`replay_clamp_count`를
  `_telemetry_status()`로 감싸 `/status`·`/snapshot`의 `telemetry` 딕셔너리에 별도 키로 노출
  (`telemetry.py` 자체는 무수정). **(2) 송신측**: `TargetIn`/`AnkleTargetIn`에 NaN/inf 거부
  validator(`JointTarget._finite_only`와 동일 패턴) 추가 → `POST /target` 실제로 wire bytes까지
  보내 테스트하다가 2차 버그 발견: FastAPI 기본 422 핸들러가 pydantic 에러의 `ctx["input"]`(NaN 자체)·
  `ctx["error"]`(raw `ValueError`)를 그대로 돌려주는데 Starlette `JSONResponse`는 `allow_nan=False`라
  **NaN 거부 응답 자체가 500으로 깨짐** — `loc/msg/type` 문자열만 돌려주는 `RequestValidationError`
  핸들러를 앱에 추가해 고침. `/target`·`/ankle` 응답을 `{requested, applied, clip_range}`로 정직화
  (이전 `clamped_to`는 범위만 돌려주고 실제 적용값을 숨겼음). **(3) TxClient**: 계약에 없는 관절이
  완전 무클램프로 새는 경로에 `hard_range` 폴백 kwarg 추가(현재 호출부는 전부 계약 관절만 써서
  사실상 방어적 배선, 유닛테스트 3건으로 잠금). **(4) HUPHY 브리지**: `joint_map_huphy.json`/
  `joint_map_bench.json`에 선택적 `rom_deg: [lo, hi]` 필드 추가(오늘은 전부 null — 두 리그 다
  커미셔닝 전), `HuphyBridge.parse_fast`가 설정되면 HUPHY cal-space 도(度) 단위로 변환 전 클립
  (`sim_core.py`의 하드 클립 앞단 방어층, 실제 안전보증은 여전히 (1)). **(5) 벤치 스크립트**
  (`deploy/bench/bench_telemetry.py`, 실물 CAN 스크립트라 **편집만·실행 안 함**, py_compile
  문법확인만): 계획은 "config `limits_deg`가 있으면 절대 클립"이었으나, HUPHY 자체 문서
  (`config/schema.py`, `motors/base.py`)가 "모든 각도는 cal 공간, `limits_deg`는 raw 아님"이라
  명시하고 이 스크립트는 `RobStrideBus`/`MitCommand.position_deg`로 raw 공간을 직접 다뤄
  offset/sign 변환이 전혀 없음 — 그대로 적용하면 **좌표계가 다른 값을 클립**하는 실질적 버그가
  됨. 계획 문구를 그대로 따르지 않고 **의도적으로 편차**: `--rom`(raw, q0 상대)은 그대로 유일한
  ROM 경계로 남기고, `limits_deg`는 시작 시 정보성 NOTE로만 출력(적용 안 함), 왜인지 docstring에
  명시. **테스트**: 신규 `tests/test_rom_clip.py`(7건, 직접구동 하드클립·NaN=무데이터·AB크랭크
  소프트클립+closure 유지·`/target` 정직 응답·NaN/inf 422), `test_tx_client.py`+3, `test_bridge_huphy.py`+2.
  전체 스위트 345(세션 시작 시점 기준, 다른 에이전트 작업 포함)→357, 3회 연속 무실패 확인. 미해결:
  ①`limits_deg`를 raw 공간에 안전하게 적용하려면 벤치 스크립트가 HUPHY 계산 Leg/Motor API를
  타거나 `huphy_udp.py`와 같은 offset/sign 변환을 새로 갖춰야 함(둘 다 이번 범위 밖). ② `rom_deg`는
  두 조인트맵 모두 null(실제 커미셔닝 값 없음, 방어층은 배선만 돼 있고 아직 실효 없음). 커밋:
  `678261f`(A1 수신 클립)·`d836a5f`(A3 송신 정직화+NaN)·`f4ba171`(TxClient hard_range)·
  `9115180`(rom_deg 조인트맵)·`ae5a1f3`(bench_telemetry 문서화)·`dce31f6`(test_rom_clip.py).

- 09-04 — **A2: ROM/토크 위반 레코드화 + 대시보드 빨간 패널** (계획 `optimized-leaping-hamster.md`
  A2). 사용자 요구: "ROM/토크제한 넘는 입력/출력이 발생할경우 빨간색 오류창이 뜨고, 어디서 어떤
  관절이 어떤값이 들어가는 문제가 발생했는지 보이게". A1/A4가 이미 만들어둔 `range_violations`
  (관절→카운트)와 `replay_clamp`(클램프 이번틱/누적)는 그대로 두고(다른 항목 범위, 하위호환
  필요 - 대시보드 Telemetry 탭·여러 테스트가 참조), **새 공유 로그** `pygviewer/violations.py`의
  `ViolationLog`(스레드세이프, 200건 링버퍼 + `(side,joint)` 누적 카운트, `clear()`)를 신설해
  네 지점 모두 같은 곳에 기록:
  - `side="recv"` — `telemetry.py::RealState.ingest_joint_state`(`:115-122`), 수신 q가 조인트
    range 밖일 때 기존 `range_violations[n]+=1` 옆에 `{joint, value, limit_lo/hi, over_by, src}`
    레코드 추가.
  - `side="recv_torque"`(신규 체크) — 같은 함수, 수신 `tau_est`가 계약 `gains[name].effort`를
    넘으면 기록. `RealState`에 `effort_limits` 딕셔너리 신규 인자로 추가(`SimCore`가
    `self.eff`에서 만들어 전달).
  - `side="sim_actuator"` — `sim_core.py::_tn_clamp`(`:756-780`), T-N 곡선이 PD raw 토크를
    실제로 자르는 순간(`raw_i > hi`/`< lo`)마다 `{tau_raw, tau_clamped, omega}` 포함 기록,
    **관절당 100ms 레이트리밋**(200Hz 서브스텝이라 무제한이면 링버퍼가 1관절로 도배됨 — 누적
    카운트는 레이트리밋과 무관하게 매번 증가, 링에 들어가는 개별 레코드만 솎아짐).
  - `side="send"` — `bridge/tx_client.py::_clamp_positions`(safe_clip 클램프, 신규
    `on_violation` 콜백 인자로 이 클라이언트 자체는 로그를 import하지 않게 분리), `tx.py`의
    `rejected_count` 증가 지점(BLOCKED_MODES 거부, joint="*"), `api.py`의 커스텀 422 핸들러
    (`/target`·`/ankle`의 NaN/inf 거부 — 값 자체는 저장 안 하고 `value:null` +
    `rejected:"non-finite (NaN/inf)"`만 기록, 관절명은 검증기 메시지에서 정규식 파싱).
  **API**: `GET /violations?limit=N&side=...` → `{records, by_joint, total}`(`age_s`는 요청
  시점 계산), `POST /violations/clear`. `Status.telemetry.violations`에는 요약만
  (`{total, by_joint, last}`, `ViolationLog.summary()`) — 링버퍼 전체는 안 실림.
  `GET /tx/status`에 `violations_count`(send측만) 추가.
  **대시보드**(`static/dashboard.js`/`dashboard.html`): `.wrap` 그리드에 새 행을 넣으면 다른 탭
  레이아웃까지 건드려야 해서(브라우저 렌더 확인 불가 상태에서 위험 판단), 대신 `position:fixed`
  오버레이(`#violation-panel`, 어느 탭에서도 보임)로 구현. 상단바 배지가 `Status.telemetry.
  violations.total`을 WS 갱신 속도로 반영(펄스 애니메이션, 위반 0이면 배지 자체가 안 생김 →
  배너 숨김 요구 충족), 클릭하면 패널 토글(`GET /violations?limit=50`을 그때만/250ms 폴링,
  닫혀 있으면 요청 안 함). 패널 = 관절별 누적 요약 표 + 최근 레코드 표(시각/쪽/관절/값/한계/
  초과량) + clear 버튼. 레코드 행 클릭 → `S.plotPanels`(A4)로 해당 관절의 pos/tau 플롯 모달을
  염(`side`가 sim_actuator/recv_torque면 tau 행, 그 외 pos 행).
  **라이브 검증**(재기동 후, 벤치 포워더가 실제로 50Hz 스트리밍 중인 프로세스에 대해):
  `GET /joints`의 sim `L_knee_joint` q=0.0(range [0, 2.0944])인데 실측 real q=**-1.501 rad**로
  하드 range 훨씬 밖 — `GET /violations?side=recv`가 `{joint:"L_knee_joint", value≈-1.50,
  limit_lo:0.0, limit_hi:2.0944, over_by≈1.50}`를 그대로 보여줌(아래 §9 라이브 확인 참조).
  **테스트**: `tests/test_violations.py` 19건 신규(순수 `ViolationLog` 단위 7건 + `SimCore`/API
  통합 12건 — recv/recv_torque 기록·레이트리밋·`/violations` 필터·clear·NaN 422 레코드·
  `Status.telemetry`가 요약만 나르는지·A1의 `replay_clamp`와 이 로그가 서로 침범 안 하는지).
  전체 스위트 357→376, 무실패. **미해결**: (a) 브라우저 실렌더 미확인(레이아웃/오버레이 z-index
  겹침은 코드 리뷰로만 검증, 다른 UI 세션과 동일한 한계). (b) send측 gain(kp/kd) 클램프는
  로그에 안 걸림(스코프를 위치 clamp/거부로 한정 — 사용자 요구가 ROM/토크였고 게인 클램프는
  성격이 다름). (c) `sim_actuator` 레이트리밋 100ms는 하드코딩값, 조정 가능하게 만들진 않음.

- 09-04 — **모터 Health Check: 연결 여부 실시간 인디케이터** (A2 바로 다음, 별도 커밋).
  사용자 요구: "웹 뷰어에서 실제 모터와 연결됐는지가 투명하지 않다. 모터 Health Check를
  실시간으로 보고 싶고, 데이터가 들어오는지 인디케이터로 보고 싶다". 조사 결과: HUPHY는
  모터별 진단(`temp/age/ack/miss`, `telemetry/snapshot.py DIAG_MOTOR_FIELDS` — `age`=마지막
  CAN 응답 후 ms(-1=한번도 없음), `ack`=1응답/0씹힘/-1미명령, `miss`=연속무응답, HUPHY 자신의
  주석이 "ack가 핵심"이라 명시)를 이미 정의하지만 **우리 브리지가 버리고 있었음**
  (`bridge/huphy_udp.py`의 `parse_fast`가 `FAST_MOTOR_FIELDS`(pos/tgt/vel/tau)만 받아들이고
  DIAG는 명시적으로 무시 — 주석 "diag/CAN fields are ignored, not hard failures"). 벤치
  송신기(`deploy/bench/bench_telemetry.py`)도 pos/tgt/err/vel/tau/temp만 보내고 있었음.
  **구현**: (1) `HuphyBridge`가 DIAG_MOTOR_FIELDS를 FAST와 같은 영속 버퍼에 누적하도록 확장
  (부호/영점 보정 없음 — 각도가 아님; `-1`(음수)은 `_sentinel`의 3연속 경고 없이 조용히
  `null`로 — 미명령 모터가 영구적으로 age=-1을 보내는 건 정상 상태지 경고감이 아님). DIAG만
  들어온 패킷도 이전 FAST 값을 들고 JointState를 emit(실물 HUPHY의 분리패킷 설계와 호환).
  (2) `JointState`에 `motor_age_ms/ack/miss` 3개 선택필드 추가(전부 기본 None, 하위호환 —
  `temp_c`는 이미 있었으나 이번까지 아무도 채우지 않고 있었음). (3) `RealState`에 관절별
  진단 저장 + **관절별 자체 수신시각**(`_joint_last_update_mono` — 기존엔 프로세스 전체
  하나의 수신시각만 있어 "한 관절만 조용해짐"을 못 잡았음) + 판정기(`health()`): 진단이
  한 번이라도 온 관절만 ack/miss/age_ms 기반 판정, **진단이 아예 없는 송신자(현재 벤치)는
  우리 수신 신선도(<0.2s ok, 0.2~1s warn, >1s dead)만으로 판정**하고 `diag:false`로
  명시(정보 없음을 숨기지 않음). "ack=0 연속"은 HUPHY의 `miss` 카운터로 등급화(1회
  놓침=warn, `miss>=5`=dead — 이 임계값은 브리핑에 숫자로 안 박혀 있어 코더가 정한 값,
  §9에 명시). (4) `GET /health` 신설(`{link, joints, summary}`), `Status.telemetry.health`는
  요약만(ok/warn/dead 개수+링크상태). (5) 대시보드: 상단바에 링크 LED(회색=한번도 연결
  안됨/초록=수신중/빨강=stale)+하트비트 점(패킷마다 rx_count 변화로 깜빡임, A2의 빨간 위반
  배지와 시각적으로 구분되게 색·모양 다르게), Telemetry 탭에 관절별 12칸 상태그리드
  (초록/노랑/빨강, hover로 age/motor_age/ack/miss/temp/마지막 q). (6) 벤치 송신기 **편집만
  (실행 안 함)**: `bus.state(mid).stamp`가 응답때만 갱신되는 것을 이용해 매 틱
  prev_stamp와 비교해 `ack`(응답왔나)·`miss`(연속누적, 로컬카운터)·`age`(`st.age(now)*1000`,
  `is_valid` 아니면 -1)를 HUPHY와 같은 키로 추가 전송 — 새 CAN 트래픽 없음, 기존
  refresh_states/collect 결과에서 파생만. **라이브 확인**(재기동 후, 현재 실행 중인 구버전
  벤치 프로세스는 그대로 두고 — 이 코더가 직접 벤치를 끊지 않음, 지시대로): `GET /health`가
  링크 `connected:true, rx_hz≈49.7`, `L_knee_joint: state=ok, diag:false`(현재 벤치가 구버전
  스크립트라 diag 필드가 아직 안 옴 — 편집만 하고 재가동은 안 했으므로 예상된 결과), **나머지
  11관절은 전부 `state=dead, age_s=null`**(한 번도 연결된 적 없음, 올바른 판정). summary
  `{ok:1, warn:0, dead:11}`. dead 전이 자체는 진짜 단선 대신 순수 `RealState` 유닛테스트에서
  가짜 시계로 1.5초를 "흘려" 확인(벤치를 실제로 끊지 않음). **테스트**
  `tests/test_health.py` 11건(ok/dead-by-age(가짜시계)/미연결-dead/ack=0-warn/miss1-warn/
  miss>=5-dead/diag있는데 age null=dead/diag전혀없음=수신신선도만+diag:false/`/health`
  스키마/`Status.telemetry.health`가 요약만/벤치형 단일관절 라이브 회귀). 기존
  `test_bridge_huphy.py`의 "diag는 전부 무시" 전제 테스트 1건을 이번 설계 변경에 맞게
  분리(guard/can은 여전히 무시, DIAG_MOTOR_FIELDS는 이제 파싱됨 — 신규 3건으로 교체).
  전체 스위트 376→390, 무실패. **미결**: (a) `source_addr`(송신자 IP) 필드는 구현 안 함
  (`RealState`가 UDP 주소를 모름 — 스레딩하려면 `HuphyUdpReceiver`까지 관통해야 해서 이번
  범위 밖). (b) 벤치가 실제로 새 진단 필드를 보내는 걸 라이브로 보려면 사용자가 벤치
  스크립트를 재시작해야 함(이 코더는 실물 모터 구동 스크립트를 직접 실행하지 않음). (c)
  `HEALTH_DEAD_MISS=5`/온도임계 60°C 기본값은 코더 판단(브리핑에 숫자 없음), 실측 후 조정
  필요할 수 있음.

- 09-04 — **A6: 렌더 루프 크래시 수정 + A5: 위반 배지/콘솔 로그 + 플롯 real 가시성** (사용자
  피드백 2건 + 코디네이터가 확정한 크래시 원인, `static/dashboard.{js,html}`만). **A6(별도
  커밋 `9b51b40`, 먼저)**: 브라우저 콘솔에 반복되던 `TypeError: can't access property
  'dataset', sub is null`(renderJointsPanel←renderTabControl←renderRightTab←renderTick).
  원인: Model/Base/Telemetry/Script/Status(`#left-body`)·Control/Gains/Obs(`#right-body`) 6개
  탭 렌더러가 **공유 body 엘리먼트의 dataset**에 탭별 "이미 빌드됨" 불boolean을 찍었는데
  Base/Telemetry/Script 셋은 같은 `dataset.built` 키를 공유, Control/Gains/Obs 셋은 각자
  다른 이름(`builtControl`/`builtGains`/`builtObs`)을 썼지만 서로의 플래그를 지우지 않음 —
  `innerHTML=...`는 자식만 교체하고 엘리먼트 자신의 속성은 남으므로 Control→Gains→Control
  이동 시 `builtControl`이 "1"로 남은 채 실제 DOM은 Gains 표, `el("control-sub")`가 null →
  `renderJointsPanel(null)`이 매 틱 크래시 → **try/catch가 없던 `renderTick`이 그 뒤 단계
  (`renderPlots` 포함)를 전부 정지** — 별도로 보고된 "real 모터 플롯이 안 보인다"의 실제
  메커니즘이 색/굵기가 아니라 이 크래시였음. 수정: 6곳 전부 `body.dataset.builtTab`(어느
  탭이 빌드됐는지 이름 하나) + `tabNeedsBuild(currentBuiltTab, tabName, force)`(순수함수)로
  통일, `renderJointsPanel`/`renderPolicyPanel`에 `if (!sub) return;` 널가드,
  `renderTick`의 5단계 각각 개별 try/catch(캐치된 예외는 `console.error` + 신설
  `#op-console`에 1줄로 표시 — 조용한 실패 재발 방지). `tests/test_tab_build_flags.py` 10건
  (탭전환 시퀀스 Control→Gains→Control·Base→Telemetry→Script→Base를 순수함수로 재현,
  소스텍스트 잠금).
  **A5(2건, 크래시 수정 다음 커밋)**: (1) 배지 텍스트 자체에 가장 최근 위반 관절명·값·한계를
  박음(`violationBadgeText`, WS `Status.telemetry.violations` 요약만 읽어 추가 요청 없음) —
  예 `⚠ 2627 · L_knee_joint (recv) -1.501 rad ∉ [0.000, 2.094]`(라이브 확인, 관절 2개 이상이면
  ` 외 N개` 접미). (2) 항상 보이는 접이식 콘솔(`#op-console`, 화면 우하단 고정) — 위반은
  50Hz(벤치 실측: 1초당 delta=51건)로 쏟아지므로 `coalesceLines`(순수, side|joint 키로 1초
  창 안 병합, 창 경과 시 새 레코드 없이도 강제 마감)로 초당 1줄 `HH:MM:SS.mmm [recv]
  L_knee_joint value=-1.501 limit=[0.000, 2.094] over=1.501 (x50)` 형태로 합침, clear/copy/
  autoscroll/collapse 버튼. (3) real 시리즈 색 버그: 기존 real은 **sim과 같은 hex에 알파
  접미만 붙인 것**(`#5b9bd588` 등) — "안 보인다"가 아니라 "sim과 구분 안 됨"이었음. sim과
  무관한 색(L=마젠타 `#ff3fa4`/R=시안 `#00e5ff`, width 2.4 실선, IMU 위젯 자이로색과 통일)로
  교체, 라벨에 `(real)` 명시. (4) 패널마다 항상-보임 리드아웃 `.pv`(`plotReadoutText`, uPlot에
  먹인 배열을 그대로 재사용 — 별도 추측 없음): `L sim 1.369 real -1.501 · R sim — real — ·
  real n=3` 형태, 선이 안 보여도 숫자로 확인 가능. (5) 범례: 사용자가 "실제 예시선(선 샘플)
  뒤에 라벨"을 요구 — uPlot 기본 범례(점/사각형 마커)는 그 요구에 부족해 **각 ROW 헤더에
  직접 그린 범례**(`legendSwatchHtml`, `makeSeriesFor(row)`에서 그대로 뽑아 stroke/width/dash를
  `border-top` 짧은 선분으로 재현 후 라벨 — 스타일 변경 시 자동 동기화, 고정 높이 헤더라
  `.plot-cell`의 `overflow:hidden`에 클립될 위험 없음)로 교체, 컴팩트 그리드에서는 uPlot
  자체 범례를 OFF(클리핑 위험 회피), 모달(확대뷰, 80vw×70vh 여유공간)에서는 ON +
  `.u-marker`를 점→짧은 선(`width:16px;height:3px`)으로 CSS 오버라이드. 낡은 캡션
  문구("light=real")는 제거하고 "click a panel to expand"만 남김. (6) tau 필드명 의심
  조사: **버그 없음** — `schema.py JointState.tau_est`가 표준 필드명이고 `api.py`의 sim/real
  두 생성자·`bridge/huphy_udp.py`가 모두 `tau_est=`로 채우며 `dashboard.js`도 `msg.tau_est`를
  읽음(회귀 테스트로 잠금); 사용자가 본 tau non-null=0은 그 순간 실제로 토크가 0에 가까웠던
  데이터 문제로 판단, 배선 문제 아님. **테스트**: `tests/test_violation_console.py` 20건
  (배지/콘솔 병합/플롯 리드아웃 순수함수를 Python으로 라인 단위 재구현+검증, tau 필드명
  스키마·발신자 일치, 소스텍스트 잠금). 전체 스위트 390→**420**(무실패). **라이브 확인**
  (뷰어 재기동, pid 갱신 확인): `/ws/out` sim/real 프레임 동시 수신(`L_knee_joint` sim
  q≈0.42/0.42, real q=-1.5007 — 큰 격차 실측), `/status`·`/violations` 총계 일치(재기동 후
  1초당 +51 확인), `curl`로 새 `dashboard.js`/`dashboard.html`(op-console·violationBadgeText·
  legendSwatchHtml 포함) 서빙 확인. **미결**: 이 호스트에 브라우저/Node가 없어(esprima
  4.0.1로 전체 파싱만 확인, `??`는 esprima probe에서만 `||`로 중립화) 배지·콘솔·범례·리드아웃이
  실제 화면에서 어떻게 보이는지는 여전히 미검증 — 서버 데이터·순수함수 로직·서빙 파일까지만
  이 코더가 확인 가능한 한계.
