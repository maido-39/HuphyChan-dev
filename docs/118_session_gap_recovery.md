# 118. 세션 공백기(08-31~09-03) 컨텍스트 복구 — 계획·의사결정 요약

본 세션(Fable 메인루프) 부재 중 외부 세션들이 수행한 작업의 **의사결정 관련 정보만** 증류한다.
원자료: `.tmp_session_transfer/` (OLD_Claude 869 jsonl → Codex 5 실질 jsonl → 개인 Claude 9 jsonl)
+ 그 후 산출물인 docs/108–117 + 라이브 브리핑. 과정 서사는 각 정식 문서에 있고 여기 반복하지 않는다.

## 0. 타임라인

| 순서 | 주체 | 기간 | 핵심 산출 |
|---|---|---|---|
| 1 | OLD_Claude (본 세션 전신) | ~08-31 | docs/103–107 시대 (V2 레시피·sim2sim·백로그) |
| 2 | Codex | 09-01~09-02 06:59 | v30 재추출·모델 재구축 → docs/108–116 |
| 3 | 개인 Claude ×3 병렬 | 09-02 07:35~09-03 01:00 | 뷰어(A)·HUPHY 어댑터(B)·IMU 실측(C) → docs/117, EBIMU 판정 |
| 4 | 본 세션 복귀 | 09-03 | 이 문서. legonly_ab_v1 모니터링 인수 |

## 1. 공백기 문서 지도 (한 줄 판정)

| 문서 | 내용 | 상태 |
|---|---|---|
| [[108_pretraining_quality_audit]] | 사전학습 품질 감사 | 참고 |
| [[109_12dof_sim2real_decision_gate]] | ★사용자 재스코프: **주라인 = 12-DOF 하체(waist_yaw 모터 질량만, DOF 없음)**. 상체(v2u1)는 부차 실험으로 강등 | **유효 게이트** |
| [[110_prototype_tempmass_student_teacher_report]] | Student-Teacher actor 45D 계약(ang_vel3+grav3+q히스토리24+prev_action12+cmd3) | 유효 |
| [[111_fusion_v30_urdf_rebuild]] | Fusion 라이브 문서 v30(757바디) → 89/89 메쉬 재추출 절차 | 유효 |
| [[112_v30_armfix_rp_ab_part_review]] | 부품 재검토(RS03 실측 0.9195 kg, 10개로 정정; 알루미늄 9바디×L/R=18) | 유효 |
| [[113_rotation_mass_dr_hw_deploy_audit]] | 회전·질량 DR 감사. 내부 A/B 크로스맵 표는 **당일 자진철회**(로그로 재확인) | 철회분 제외 유효 |
| [[114_huphy_proxyfix_rotation_dr_audit]] | proxyfix 질량 확정 35.675 kg, DR 정본 JSON | **정본** |
| [[115_motor_flange_huphy_crosscheck]] | HUPHY 코덱 교차검증: sim축 PASS / 모터부호 UNKNOWN / **HW NO-GO** | §5.1은 아래 2-A로 재검토 필요 |
| [[116_policy_huphy_adaptation_design]] | Policy→HUPHY OBS/Action 어댑터 설계 | 아래 2-A 반영 필요 |
| [[117_model_finalization_and_oneleg_training_plan]] | 모델 확정(부호 9·ROM 8·귀속 6·미러 2 수정, 스냅샷 `7cb25dc`) + LegOnly 학습계획 | **정본** |

## 2. 로그·외부저장소에만 있고 문서에 없던 것 (핵심 델타)

**A. HUPHY 신규 커밋 `133855f`** (09-02, 전송 스냅샷 이후 — 본 세션이 재클론으로 발견):
"fix(robstride): 인코딩 범위를 제조사 260713 판본으로 교정" — **RS03/RS04 게인 인코딩 범위
0~5000, 그 외 모델 0~500 (10×)**. 이전 테이블(Seeed 251112판)은 3개 모델이 제조사값과 불일치.
→ docs/115 §5.1의 "10× 코덱 불일치" P0와 docs/116의 와이어 스케일링 설계는 **이 커밋 기준으로
재대조**해야 한다. 개인세션의 반론(불일치가 MIT vs Private 프로토콜 열 혼동일 가능성)도 기록됨.
제안된 벤치 실측 2건(토크 리드백 Kp 확인, RS04 pmax 분도기 확인)은 **미실행** — NO-GO 게이트 유지.

**B. EBIMU 최종판정** (브리핑 09-02 21:09~22:12에만 존재, 정식 노트 없음):
X축 **가속도만** 부호 반전(회전 테스트 2053점 중 94.6% 재현), Y·Z 정상(오차 ~0.001).
HUPHY 코드 결백(업스트림과 diff 0줄, 가속도 축변환 자체가 없음) → 원인 = 센서 펌웨어/실장.
정책 입력(projected gravity)은 쿼터니언 전용이라 **학습에 영향 없음**. 개인세션의 "Y축 반전" 관찰은
뷰어의 반사변환 버그(행렬식 −1)로 설명·폐기. 잔여: 검증에 쓴 매뉴얼이 V5인데 실물은 **V6**(docs/110)
— V6 레지스터맵 재확인 1건. 무효 데이터: 초기 600 s/5분 캡처 2건(중복 리더 경합) — **그 dropout
수치 재사용 금지**. 유효본 = 단일리더 2분 12,000/12,000 (드롭 0).

**C. 사용자 보행품질 지적(09-02 23:49, 로그상 미답변)**: legonly_ab_v1 라이브 뷰에서
"무릎을 전혀 안 쓰고(stiff-legged), AB도 제대로 안 쓰며, toe-off에 발끝 지지가 안 된다."
→ 09-03 사용자 신규 과제 #1로 승격(별도 문서 예정). 메모리의 tiptoe=base_height 퇴행 전례와
대조 필요.

**D. Fusion MCP 사용법 확정** (Codex; 111에 절차만 있고 아래 운영 지식은 로그에만):
- "Fusion이 자꾸 죽는" 진짜 원인 = **추출기 자신의 예외기반 폴백**(stdout이 비면 일부러 예외를
  던져 traceback을 긁음 → 축적 → ~77콜에서 호스트 사망). 정상 stdout 우선으로 수정됨.
- 단일 호출 응답 **1 MiB 캡**(757바디 전체 listing은 `[output truncated]` — 크래시 아님).
  구조 바디 89개로 필터 후 조회할 것.
- 네트워크: portproxy는 **.161(윈도우 PC)에서** 실행 + 방화벽 프로파일 주의 + DNS-rebinding 방어
  때문에 `Host: 127.0.0.1:27182` 강제 필요. 영구화 스크립트 `tools/fusion/setup_fusion_mcp_portproxy.bat`.
  접속 레시피(117 §0과 동일): `FUSION_MCP=http://192.168.20.161:27182/mcp
  FUSION_MCP_HOST=127.0.0.1:27182` + `M.connect()` 선행.
- Fusion "외부참조 포함 복사" API는 현 설치본에서 **무력화**(빈 폴더 산출) — 별도 deep-copy 경로 사용.
- `fusion2urdf` 애드인은 **불채택**(1-occurrence=1-link 가정이 미러다리/2-RSU 구조와 충돌).

**E. teammate mjcf (`~/external_repos/huphy_mjcf`, `8fa92be`)**: 수치 병합 **0건** — 축/부호
교차검증 전용으로 사용. hip 관절 위치 차이 의혹은 축을 직선으로 보면 수선거리 0~0.2 mm =
축방향 오프셋일 뿐, **허위경보 판정**. huphy.xml의 자체 gear 부호(예: R_hip_pitch −1)는 우리
`motor_sign_convention.json`과 **별개 규약으로 미통합**(뷰어 `--xml` 모드로 열람만).

**F. HUPHY P0 2건 발견·미수정** (우리는 read-only 원칙 유지):
(1) `sign`을 관절 **위치에만** 적용하고 속도엔 미적용 → sign=−1 모터의 joint_vel 부호 반전.
(2) MIT-codec 테이블 placeholder(vmax 33/Kp 500/Kd 5) vs 제조사 정식 — A의 133855f로 일부
해소됐을 수 있음, 재대조 시 함께 확인.

**G. 잔여 미확정 (이월)**: 우측 모터부호 4건(R hip_pitch·L crank A·R knee·L crank B)
DISPUTE/UNKNOWN — 미러 합성 금지 원칙 유지 중. 체결구 질량 모델 2.4315 kg vs 사용자 발언
"약 2 kg"(실측인지 추정인지 미확인, docs/113 오픈 항목과 동일 — 신규 과제 #3 질량 감사에서 흡수).
W&B entity 슬러그: 실험노트의 `dongyub39-snu`는 404였으나 09-03 v2 발사 시 wandb가 같은 슬러그로 sync(run r8j47gnd) — **슬러그는 맞고**, 404는 비로그인/비공개 프로젝트 문제로 추정.

## 3. 라이브 상태 (09-03 10:45 기준)

- **legonly_ab_v1**: P2 진행 중 **5,500/18,500 iter**, mean reward ~92.8. `/proc` 환경변수로
  **정본 DR JSON**(`mass_dr_legonly_fastener50_prototype-tempmass.json` = 117 §2 corrected 서브셋)
  사용 확인. gate_watch 가동.
- **와치독**: 08-26 19:41부터 죽어 있었음. cron은 5분마다 발사를 시도했으나(syslog 확인) 어떤
  소멸된 프로세스가 pgrep 패턴에 걸려 발사가 스킵된 것으로 추정. 09-03 10:35 재가동, 중복 1개
  정리. 옛 엔트리는 전부 finished 판정이라 오재개 위험 없음.
- **HUPHY** 재클론(133855f 포함) `~/external_repos/HUPHY`, huphy_mjcf 최신 `8fa92be`.

## 4. 백로그 정리 (docs/106 반영)

| 항목 | 판정 |
|---|---|
| 106 D1 어깨 형상 메쉬 | **해소** — v30 재추출이 89/89 전체 갱신 |
| 106 H2 v2u1 상체학습 | **재정의** — 주라인은 LegOnly 12-DOF(109 게이트). 상체는 SemiFullDoF/FullDoF 변형으로 흡수. 기존 ROM 오버라이드(어깨 −90/+60·허리 ±45)는 107 ROM표와 재대조 필요 |
| v2s1(v4 모델) 하중 측정값 | **구세대 강등** — 모델 세대가 v30(35.675 kg)으로 교체됨. 설계값 재측정은 legonly_ab_v1 완주 후 |
| 신규 오픈 | ①133855f 재대조(→115·116 갱신) ②EBIMU V6 매뉴얼 재확인 ③벤치 2실험 ④우측 모터부호 ⑤W&B entity ⑥보행품질(과제1) ⑦collision 검토(과제2) ⑧질량 감사(과제3) |
