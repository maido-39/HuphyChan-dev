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
| P0 | bake 6변형, SimCore, viser 씬, `/status` | 6 mjb+json; headless 5 s ≥195 Hz 물리·RSS<600 MB; `curl :8095/status` | 🔄 착수 21:15 |
| P1 | 관절 UI/API, base 3모드, 지면, 폐루프 settle, 플롯 | `test_basefix`(fixed 드리프트<1e-6, pivot 위치<1e-4) · `test_loop_settle`(vs loop_ankle_verify.json, closure<0.01 mm) · `test_bake_contract` · `test_sim_rate` | 🔄 |
| P2 | ONNX/.pt 정책, obs 빌더, 게인 소스 | `test_policy_parity`(<1e-4) · `test_obs_order` · 워킹 스모크(drift 러너와 vx 오차≤0.05) | ⏳ |
| P3 | 스키마·WS/REST·HUPHY UDP 어댑터·더미·레코더 | `test_schema` · 더미 sine→real_replay · WS 50 Hz · 10 s 기록 RSS 불증 | ⏳ |
| P4 | 스크립트 플레이어·compare·obs mux·섀도우 | 지연 주입 더미 오버레이 png · 더미 IMU가 액션 변화 | ⏳ |
| 등록 | dashboard PORTS·start_all·README·launch.json·브리핑 | — | ⏳ |

## 7. 재사용 소스
`tools/sim2sim/mujoco_ab_loop_drift.py`(PD/T-N/obs) · `tools/sim2sim/dump_contract_ab.py`(계약) · `tools/viewer/mjcf_joint_viewer.py`(viser·settle) ·
`pygmalion_constants.py`(get_spec·키프레임·safe_target_clip·signed_pose·joint_travel_sign) · `mjlab/rl/{runner,exporter_utils}.py`(ONNX) ·
`ankle_rp_envelope.json`(역해·Jcᵀ) · HUPHY `telemetry/{udp,snapshot}.py`(실물 포맷).

## 8. 열린 항목 (하드웨어)
실물 호스트·시계 동기 미정 · 관절별 모터 기종·kp/kd 인코딩(RS03/RS04 0~5000) · IMU 실장 방향(프로토콜 ⑦) · 좌우/발목 매핑 UNVERIFIED(프로토콜 ②③).

## 9. 진행 로그 (코더가 phase 완료마다 추가 — 시각·결과 숫자·커밋·문제)
- 09-03 21:15 — 계획 승인, P0/P1 구현 착수(코더). 이 문서 생성.
