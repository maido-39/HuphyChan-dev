# 자율 야간 계획 — 2026-06-21 22:00 → 06-22 10:00 (~12h, 1 GPU)

## A. 체계적 검토 — 내가 건 큐 / 제안한 research question

**실험 큐 ([[experiment_queue]])**
- E1 공간 CoP-진행 + ankle 충돌 해소 (ankle fix ✅ 완료 / CoP 보상 미구현)
- E2 + 새 PD(knee11/hip24) + **무릎 belt 1.5**
- E3 phase-clock 대안(조건부) · E4 비대칭 critic · E5 heel 바디+진짜 CoP(USD변경)

**사용자 제안 research question / 분석**
1. ★ **감속비 SWEEP** — 직결+벨트 후보 여러개를 *각각 학습*해 demand·성능 비교(순환성 깨기). [최대 제안]
2. 액추에이터 모델: 박스 vs T-N — **답: ImplicitActuator=박스**(평평 effort+하드 속도클립, T-N droop 미모델). → 사다리꼴 T-N 클립 구현 제안.
3. 무릎 진짜 속도 demand 재측정(한계 올려 — 현 데이터 1:3에 클립).
4. 충격 리워드 검증 — ✅ 동작하나 error_vel 0.72 plateau(가중치 과함).

**미기록 연구(규칙상 노트화 필요)**: womafnnro(무릎 액추 landscape), wyvmh4gpv(CoP 공식, 부분). RS04 T-N·다조건·belt 분석.

## B. 야간 실행 계획 (watcher-driven, 완료시 깨어 다음 단계)

> robustness: ① 학습 중 무거운 분석 금지(RAM) ② warm-start+~1000iter 짧게(죽어도 손실↓) ③ 죽으면 재기동.

**Phase 1 (~22:00–23:30) softcontact2 완주 + 측정** [진행중]
- softcontact2(충격보상) 완주 → measure: **H1 충격이 떨어졌나**(pushoff3 4.5-7.2kN 대비) + **무릎 진짜 속도 demand**(velocity_limit 임시 200rpm + 고속명령 2.0).
- (학습 중엔 분석 금지) GPU 빈 사이 womafnnro·wyvmh4gpv 노트화.

**Phase 2 (~23:30–08:00) ★ 감속비 SWEEP** [야간 본체]
- base: forefoot_cop model_2499(수렴 walker) · 보상: forefoot셋 동일(충격항은 -1.0/-0.005로 완화=plateau교훈) · 모든 비 동일.
- 후보 **직결1.0 · 1.5 · 2.0 · 2.5**: 비별 무릎 effort=g×120·vel=200/g·armature=1.2e-4×(9g)² 설정 → warm-start ~1000iter → measure.
- 비별 메트릭: **error_vel·CoT·충격/구조하중·무릎 토크%·속도%활용·gait**. (각 ~1.5-2h × 4 = ~7h)
- **H2(가설)**: 무릎 speed-bound라 *저감속(1.0-1.5)*이 추종·효율 우수 / *고감속(2.5)*은 속도캡으로 추종↓. ROUGH 포함시 1.0은 토크부족(2.7%) → **1.5가 균형**일 것.
- 병렬(GPU 빈 사이 CPU): 사다리꼴 T-N 클립 액추에이터 구현+config-test(충실 re-sweep용) · CoP 보상 first-cut(E1용).

**Phase 3 (~08:00–10:00) 종합 + 보고**
- sweep 비교표 + 플롯(영어) → **최선 감속비 권장**(데이터 기반, 순환성 없는). T-N 모델 준비됐으면 충실 재검 메모.
- 아침 보고서 + 모든 분석 규칙대로 노트화(refs·영어플롯).

## C. 판정 기준 (보수적 중단 [[27_training_review_loop]])
- 각 sweep run: error_vel 수렴·낙상<5%·reward 회복이면 ~1000iter서 측정. 비정상이면 보수적(초반 dip 무시).
- 죽으면 마지막 ckpt에서 재기동. 1 run 막히면 건너뛰고 다음 비.

## D. 안 할 것 (시간/리스크)
- E5(heel USD변경)·phase-clock(E3) — 야간 자율엔 부적합(HW변경/설계판단). 아침 보고서서 제안.
- 사용자 확정 필요한 HW결정(최종 감속비)은 sweep 결과 *제시*까지만, 확정은 사용자.

## E. ★ 확장 자율 연구 프로그램 (사용자 06-22, 10시 이후 지속 OK)
지시: sweep 비교는 응답 대기 없이 자율. 그 다음 **전 actuator 정량/정성 분석 + 모터 T-N 교차검증 + 설계탐색 + 주제별 노트 지속**.
1. **sweep 완주** g1.5→2.0→2.5 → 비교표 + 최선 감속비 (자율).
2. **전 actuator 속도/토크 demand** (무릎 분석처럼 확장): 빠른/느린 보행별(cmd_vx 0.3~2.0) 각 관절(hip p/r/y·knee·ankle p/r)의 **joint-side** 속도/토크(RMS/p95/max) + ★**motor-side 부하**(joint demand를 감속비 reflect: 모터속도=joint×G, knee=×(9×belt)). measure.py SCHEDULE을 0.3~2.0 전범위로 확장(현재 ≤1.0).
3. **모터 T-N 교차검증** RS04(무릎=감속)·RS03/04(hip)·RS00/03(ankle) — 신뢰소스 **2+개** 대조.
4. **설계탐색**: 각 모터 T-N이 그 demand를 fast/slow서 덮나? 타깃(자연·효율 gait + HW생존)에 맞는 감속비/모터 후보.
5. **주제별 연구노트 지속** + 부족/문제 가설 시 추가 연구. 계획·노트 지속 갱신. (Stop-hook이 노트 누락 차단.)

## F. ★ Rough + DR 고려 + 분석방법(A vs B) 결정 (사용자 06-22)
사용자: deploy엔 obstacle/외란 → **rough도 봐야**. flat-only 결과 이미 뒤집힘(direct→1.5). **DR의 요구토크 영향도 미지**. A(flat→rough 따로) vs B(flat+rough 같이) 분석 후 진행.

**A vs B:**
| 항목 | A: flat·rough 따로 학습/분석 | B: flat+rough 같이 |
|---|---|---|
| 정책 | flat baseline + rough(전이) 2개 | 1개 혼합 |
| sizing demand | terrain별 → 최악(rough+DR) 채택 | 결합 demand |
| 진단(왜 바뀌나) | ★ terrain별 명확 | binning 필요 |
| 학습량 | 2× | 1× |
| 현실성 | rough task=deploy분포(DR포함) | 동일 |

**결정 = A (flat baseline + rough+DR 따로).** 이유: ① sizing은 **rough+DR 최악이 binding**(flat만으론 오판한 전례) ② A가 **terrain 효과를 명확히**(결과 바뀐 이유 진단 = 사용자 관심) ③ **rough task가 이미 deployment 분포**(터레인 변동 + push/마찰 DR 내장)라 rough sweep = deployment-realistic ≈ B. B는 혼합되어 terrain 효과 은폐 + rough task가 이미 mix 제공해 별도 B-mix 불필요.

**진행:**
1. flat sweep 완주(baseline + 순환성 demo, 진행중).
2. **rough-forefoot env 생성**(rough terrain + flat과 *동일* forefoot+impact 보상 → 비교가능) → **rough+DR sweep** 4비 → 측정(★ `--push`로 DR/외란 효과도).
3. 비별 **flat vs rough+DR demand 비교** → deployment-robust 감속비. 전 actuator(hip p/r/y·knee·ankle p/r) 동일 분석(joint+motor side).
4. ★ **ankle_roll(RS00)이 rough+DR서 더 포화?**(평지서 이미 151% RMS) → 모터 upsize(RS01/02) 검토.
