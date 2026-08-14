# G1 ankle effort 검증 — 실모터 토크로 grounding (deep-research `wkq7dxauc`)

> 2026-07-04. 사용자 질문: "2-RSU effort=50이 G1 ankle 실모터 최대토크로 검증됐나?" → deep-research(99 agents, 3-0 검증)로 확인. **결론: G1 ankle 실모터 토크는 비공개, 50은 sim placeholder지만 실무적으로 defensible.**

## 핵심 사실 (검증 3-0)
1. ★ **G1 ankle 실 관절토크·모터모델·전달비는 어디에도 공개 안 됨.** Unitree 공식 데이터시트가 명시하는 유일한 관절토크는 **knee = 90 N·m(G1) / 120 N·m(G1-EDU)**, 각주에 "**최대 관절모터**"라 명기 → ankle 모터는 90~120 상한이나 개별 스펙 없음. [datasheet, user manual]
2. ★ **내가 본 88/139/50은 mujoco_menagerie MJCF sim placeholder**(actuatorfrcrange: hip p/y ±88·hip roll&knee ±139·**ankle p/r ±50**). README 자인: "derived from g1_description... position actuators (needs tuning)". = **실모터 토크 아님, 관절-공간 clamp.** (내 복사가 이것.)
3. **M107(ankle 45·knee 360 N·m)은 H1(다른 로봇) 액추에이터** — G1 아님. 단 H1은 실제값이라 데이터포인트: **동급 휴머노이드 ankle ≈ 45 N·m 실관절토크**(H1 ~47kg).
4. ★ **2-RSU 모터↔관절 = 형상의존 Jacobian**($\tau_{joint} = J(q)^T f_{motor}$), **고정 전달비 아님**. G1 sim은 ankle을 독립 serial 힌지 2개로 단순화(실 2-RSU 커플링 추상화).
5. G1 ~35kg, 우리 51.5kg = **1.47×**. 단 **ankle 관절토크는 질량 무관하게 45~50**(G1 sim 50@35kg, H1 real 45@47kg) = 휴머노이드가 ankle을 의도적으로 최소화.

## 판정 — effort=50은 defensible, 단 명칭 정정
- ❌ "G1 실 ankle 모터 최대토크" = **존재하지 않음**(사용자 전제 충족 불가).
- ✅ **50 = 현존 최선 grounding**: G1 sim 50 + H1 real 45 = 동급 ankle 관절토크 실측대. 우리 **RMS 수요 9.4 N·m ≪ 50 = 열적 대여유**. 실무적 타당.
- ⚠ 단 우리 **worst-case peak 65 > 50** → effort 50이면 정책이 ankle을 50에서 클립(오히려 현실적: 실 G1/H1급 ankle도 거기서 클립). 2-RSU co-actuation이 순간 peak을 2모터로 분담.
- ★ **진짜 HW 사이징은 sim 숫자 복사가 아니라 `mech_design_eval.py`**: 우리 모터 선택(실토크) → 우리 2-RSU 기하 J(q) → $\tau_{joint}=J^T f$ 를 ROM 전체서 수요와 대조. sim effort는 그 결과의 관절-공간 근사일 뿐.

## 조치
- **effort=50 유지**(연구-backed, 실 humanoid ankle급). 단 "G1 sim joint-space value(≈H1 real 45)"로 명칭 정정, "실모터 토크 아님" 명기.
- C1(현 effort 50)은 그대로 진행 — 50은 realistic constraint라 정책이 현실적 ankle 사용 학습.
- **다음: `mech_design_eval.py` 구현** = 우리 모터×2-RSU 기하 J(q)로 실사이징(이게 사용자가 원한 진짜 검증). 후보 모터(RS03 60·DM-J4340 27 등)별 관절 capability를 수요 대조.

## 소스
G1 datasheet(roscomponents)·user manual(reliablerobotics)·mujoco_menagerie g1.xml·ASAP arXiv:2502.01143(G1 ankle linkage 명시)·Zhou&Tsagarakis ASME JMR 10(5) 2018(2-DoF 병렬 ankle 토크분배)·arXiv:2509.16469(병렬 ankle 최적화)·arXiv:2506.12314(knee 120 실측).
