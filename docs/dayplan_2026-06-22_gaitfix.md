# 학습·연구 계획 — 2026-06-22 02:40 → 내일 (gait-fix 재출발)

## ★ 대전제 (재출발 이유)
그동안의 HW 분석(ankle_roll 포화·무릎 감속비 sweep·2-RSU/모터상향)은 **전부 깨진 gait 위에서 측정**됨 — 다리 교차·발 edge 보행·무릎 0/-10° 직선·토우 안 굽음. 사용자 통찰: **발 edge → 측면 CoP → ankle_roll 과부하**(= HW 요구 아니라 gait 결함 산물 가능성). → **좋은 gait를 먼저 확보**하고, 그 위에서 재측정·재분석해야 결론이 유효.

## 구조적 보장 (이제 강제됨)
- 학습 = `run_training.sh` launcher만 (직접 train.py = PreToolUse 훅 차단). train(영상 overview) → play(클로즈업) → report 자동.
- Stop-audit = 미기록 run / `[작성 필요]` / 영상누락(overview+close-up) 차단.
- plot = 영어만(한글 라벨 0 확인). 모든 학습 incl. 테스트 = 영상+노트.

---

## Phase A — 좋은 gait 확보 (★ critical path; 다른 모든 게 여기 의존)
1. **gaitfix_v3** (진행중: targeted L-R 충돌 + 보상재설계(ankle_pushoff 0.5→0.1·forefoot_cop 0.5→0.8·간접세트) + jitter↑) → 완료 시 **정면 클로즈업 audit**: ① 다리 물리 비교차 ② 토우 굽음(전족 적재되나) ③ 무릎 굽음 ④ jitter 줄었나 ⑤ 발 평탄(edge 사라졌나).
2. **결함 남으면 iterate** (gaitfix_v4/v5, 각 ~20-30min + audit):
   - 토우 여전히 안 굽음 → `forefoot_cop`/`toe_load_stance`(미배선) 더↑ · push-off 곡선 재조정.
   - jitter 남음 → **jerk(2차 action) 항 추가** or dof_acc 더↑.
   - 충돌에 덜 적응(낙상↑) → iter↑(warm-start가 깨진 gait라 재학습 필요).
3. **good-gait 판정 기준**: 다리 비교차 · 토우 굽음 · 발 평탄 · 저jitter · 저충격(landing_vel/impact) · 자연스러움. → 통과해야 Phase B.

## Phase B — 재측정 + ★가설 검증
4. good-gait 정책 **측정** (전 actuator, schedule 0.3~2.0 확장 + `--push` DR).
5. ★ **ankle_roll demand 떨어지나?** = "roll 과부하가 gait 결함이었다" 확정 → **모터상향·2-RSU 불필요** 증명(or 여전히 높으면 HW 요구 확정). 발목 설계 결론 확정.
6. 토우 사용·전족 하중·무릎/전 actuator 토크-속도 재측정.

## Phase C — HW 분석 재수행 (good gait 위; 구 분석 무효 → 전부 다시)
7. **무릎 감속비 sweep 재수행** (good gait·물리충돌 포함). 8. **전 actuator 분석**(joint+motor side, fast/slow). 9. **HW 결정 재도출**: 발목 모터(RS00 스왑 docs/39 vs 링크감속 vs 2-RSU) · 무릎 비 · 구조하중.

## Phase D — rough+DR (시간되면 / 10시 후)
10. rough-forefoot sweep (good gait, A방식 = flat baseline + rough+DR). → deployment-robust 사이징.

---

## 연구/노트
- gait-fix 작업(보상재설계·targeted충돌·토우 정량) → 노트화(launcher report + docs).
- Phase B서 **roll 과부하=gait결함** 검증 결과 → docs/37 갱신(발목 설계 최종).
- 새 연구 필요 시(toe-load 보상·jerk·parallel-ankle 세부) 수행+기록.

## 시간 배분 (~02:40 기준)
- **오늘밤 핵심 = Phase A+B** (좋은 gait + 재측정 + 가설검증). gait iterate가 변수 — 2-3회 돌 수 있음.
- **Phase C+D = 10시 넘길 수 있음**(사용자: 넘겨도 OK). 구 sweep 전부 무효라 재수행 분량 큼.
- 각 학습 완료마다 audit + 노트, 막히면 보수적 중단/iterate.
