# 106. 세션 지시사항 종합 + 계획 (2026-08-27 재정리)

사용자가 이 세션에서 지시한 것들을 **포인트로 재구성**하고 각 상태·다음 행동을 명시한다.
정본 진행상황은 [[000.Real-time Brefing]]; 이 문서는 지시→계획 매핑이다.

## A. 완료 (검증까지)

| # | 지시 | 결과 | 산출물 |
|---|---|---|---|
| A1 | IMU 위치 = Hip Yaw 모터 표면 −Z 187 mm | v4 모델에 site `-1e-06 0.007078 -0.0695` 반영 | [[105_imu_and_shoulder_cad_update]] |
| A2 | 어깨 **질량** 갱신(출력물 밀도, torso 무시) | 35.347 → **31.316 kg**, 검증 통과 | 105 §4 |
| A3 | 모터 +/− 규약(로터면 법선 CW=+) | **5 일치 / 2 반전**(hip_pitch·shoulder_pitch). +n으로 정정 | `motor_sign_convention.json` |
| A4 | ROM sweep 루프 전관절 + 영상 | 17관절 완주·복귀, 실시간, 부호배지 | `rom_sweep_v4_printed_serial.mp4` |
| A5 | Material 반투명 색분류 다이어그램 | 모터 실린더 불투명 + 구조물 반투명 | `material_map_v4_printed.png` |
| A6 | IMU Yaw drift → 학습 제외 확인 | projected_gravity yaw-불변 **수치증명**, 절대yaw 관측 없음 | 검증 완료 |
| A7 | EULA 승인 → IsaacSim | 설치·실행 검증(물리장면 생성) | `tools/sim2sim/isaac_smoke.py` |
| A8 | Sim2Sim 교차엔진 | 정적 **0.007 N·m**, 동적 RP·AB 롤아웃, 접촉 스윕 | [[sim2sim/2026-08-27_xengine_dynamic_rollout]] |
| A9 | 변환레이어 사전준비 | `rp_policy_contract.json`(관절매핑·게인·T-N·armature) | = 배포 변환레이어 사양 |
| A10 | 실시간 브리핑 + 항상발동 | 페이지+`briefing.py`, Stop/PostToolUse 훅 강제 | `000.Real-time Brefing.md` |
| A11 | 3-코어 분업(Fable/Opus/Sonnet) | 에이전트 정의+락, 8작업 병렬 처리 | `.claude/agents/` |
| A12 | 사전검토/자원낭비 방지 | pre-mortem 규칙 + 코드 클램프(assert_slice_ok·probe 거부) | 메모리+코드 |
| A13 | 다리 Contact 예측 가능성 | 조사: 크리틱 특권관측, 보조헤드 저비용(공짜 라벨 존재) | 조사노트 |

## B. 진행 중

| # | 항목 | 상태 |
|---|---|---|
| **B1** | **V2 본학습 `v2s1`** (from scratch, 확정스택, deadband 제외) | 🔄 P1 iter ~570, 낙상 0. gate_watch 가동. **첫 게이트서 승급 케이던스 판정** |

## C. 다음 큐 (B1 완주 후 / 병렬 가능)

| # | 항목 | 선행조건 | 근거 |
|---|---|---|---|
| C1 | V2 P1 완주 → P2(DR램프+entropy) 자동전이 감시 | B1 | 런처 자동, 게이트 종료 감시 |
| C2 | V2 완주 → fc/fcp 측정 + §7 모터활용 + 정식 노트 | C1 | 하중 스터디 본론 |
| C3 | 저속 수정 재설계 = **peak substep force 항**(1순위) | ✅연구노트 완료 [[reward_research/2026-08-28_substep_landing_rate]] | P1 deadband 기각(착지 경직). history_length=decimation 배선 |
| **C3★** | ★**전역 결함**: 발 접촉 리워드 **전부**(soft_landing·impact_velocity·loading_rate·knee_ext·contact_force_cap)가 50Hz `data.force` 읽음 = 에일리어싱. `feet_ground_cfg`에 `history_length=4` 배선하면 200Hz 노출 | 리워드 노트 완료 | 조사 발견. self_collision은 이미 4로 되어있음 = 발 센서만 누락 |
| C4 | 측방/후진/저속 yaw 측정(전진 격자만 했음) | — | P1 미측정 축 |
| C5 | AB 동적 GRF(정책+접촉) 잔여 비교 | 32/16 확정됨 | 교차엔진 완결 |

## D. 보류 (재촉 없음 — 가치 대비 비용 낮음)

| # | 항목 | 해제조건 |
|---|---|---|
| **D1** | 어깨 **형상 메쉬** 갱신 | 커넥터 호출누수로 재시작 3회 실패. **SSH 키 등록**(무인 처리) 또는 `ArmR_Dummy` STEP 수동 내보내기. 학습 영향 없음(팔 weld·질량 반영완료) |

## E. /goal 미완 (장기)

| # | 항목 | 비고 |
|---|---|---|
| E1 | **red-team 검증** — 모델을 지속 시각화하며 적대검증 | /goal 명시. 교차엔진이 부분 충족. 논문화는 별개(docs/91: "first end-to-end" 주장 금지) |
| E2 | 하중 측정 → HW 설계값 확정 | C2가 v4 기준 재산출; 설계값은 MuJoCo 본선(교차엔진 판정 반영) |

## F. 기술부채 (소액)

- review_loop.sh가 옛 런(ankleAB_c3) 하드코딩 → v2s1 스냅샷 누락(gate_watch는 정상). 다음 손볼 때 인자화.
- 와치독 resume는 `--agent.seed` 미전달(기본 42) — 시드 실험 시 함정.
- AB 하중률 교차엔진 ×3.88 미해결 = MuJoCo solref 컴플라이언스 PhysX 이식불가(수용된 한계).
