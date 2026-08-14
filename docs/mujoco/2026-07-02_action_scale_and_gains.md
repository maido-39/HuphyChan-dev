# action_scale 0.25 재학습 + Kp/Kd 분석 (동엽님 분석 반영)

> 2026-07-02. 동엽님 분석(action_scale 과대·추종오차·앵클 사이징)을 받아 **action_scale를 flat 0.25로 고치고 재학습 착수**. Kp/Kd 조정 가이드(요청 item 5)와 앵클 판단 정리.

관련: [액추에이터 평가 v2](2026-07-01_actuator_evaluation.md) · [ankle DM-J4340 스왑](2026-07-01_ankle_dm4340_swap.md)

---

## 1. action_scale — 무엇이 문제였나 (★ 이번 학습)

`target_q = default_q + action_scale × net_out` (net_out은 무차원).

**기존**: `PYG_ACTION_SCALE[n] = 0.25 × effort_limit / Kp` → 관절별 **0.76~1.77**:
- RS04(120/27.6)=1.09 · RS03(60/19.7)=0.76 · RS00(14/1.97)=**1.77**

→ net_out=1.0이 **최대 ~1.8 rad(>100°) 관절 변위**를 명령 = 정책이 과격한 포즈 지시 → (a) 토크 수요 부풀림, (b) 명령-실제 괴리, (c) 무차원 출력이라 학습이 "알아서 스케일 맞춤"이 안 됨(스케일은 하이퍼파라미터, gradient가 못 줄임).

**변경**: **flat 0.25** (IsaacLab G1·Unitree 표준). net_out=1.0 → 0.25 rad(≈14°). `pygmalion_constants.py` 소스+라이브 사본 둘 다 반영.

> ★ **액추에이터 평가에 직결**: 제 eval(ankle_pitch/knee binding, peak 115%)은 **action_scale 0.76~1.09의 과격 정책** 기준 = 부하 과대평가 가능. 0.25 재학습→재측정으로 **진짜 binding인지 판별**.

---

## 2. Kp/Kd — 왜 추종오차? 어떻게 고치나 (item 5)

**현재 유도**: $K_p = armature \times \omega_n^2$, $K_d = 2\zeta\cdot armature\cdot\omega_n$ ($\omega_n$=10Hz=62.8, $\zeta$=2).
- RS04: 0.007×62.8²=**27.6** / RS03 19.7 / RS00 1.97.

**문제 = armature(로터 반사관성)만 씀**. 관절은 로터가 아니라 **링크(허벅지·정강이·발)**를 움직이고, 링크의 관절축 관성 `I_link`은 armature의 **10~100배**. 실제 폐루프 고유진동수:

```
$\omega_{actual} = \sqrt{K_p / I_{total}} = \omega_n\sqrt{armature / I_{total}} \ll \omega_n$ (10Hz)
```

I_total ≫ armature라 **실제 대역폭이 10Hz보다 훨씬 낮음 → 제어기가 무름 → 추종 지연**. 무거운 링크(knee·부하받는 ankle)일수록 I_total↑ → **추종 더 나쁨**(동엽님 관측과 일치). ζ=2(과감쇠)라 접근도 굼뜸.

**★ item 3 답(토크 리밋 다 못 씀)**: Kp 낮음 → $\tau_{cmd} = K_p(q_{target}-q) - K_d\dot q$가 effort_limit에 못 미침 → 부하 관절이 **under-drive** = 지연되며 토크 여유를 남김. 즉 추종불량과 토크 미사용이 **같은 원인**(soft PD).

**조정법**:
- **A(권장·원리적)**: 모델에서 **관절별 총관성 I_total(로터+링크)**를 뽑아 `Kp = I_total·ω_n²`(목표 대역 10Hz), `Kd = 2ζ√(Kp·I_total)`, ζ≈1(임계). → 의도한 대역을 실제로 달성. *다음 실험서 내가 I_total 계산해 세팅 가능.*
- **B(실용·G1식)**: Kp를 현재의 2~4×로 상향 + ζ≈1, **trembling/발진 감시**([[2026-06-28_g1_trembling_saturation]]). G1: hip 100·knee 150·ankle 40.
- **주의**: 위치 PD는 지면반력 외란을 적분항 없이 완전 제거 못 함 → **부하 중 잔차오차는 자연스러움**. 0 오차를 좇지 말고 합리적 대역만.
- **action_scale와 상호작용**: 0.25로 명령 변위가 작아져 **절대 오차도 감소** → action_scale + Kp 보정이 함께 추종 개선.

---

## 3. 앵클 (item 4)

- **ankle_pitch(RS03 60)**: eval서 60 포화였으나 **과격정책 탓 가능**. G1 표는 G1 ankle_pitch가 자기 25 N·m의 100% util(push-off 주력관절) = 우리 RS03(60)은 G1의 2.4× 여유. **0.25 재측정서 포화 풀리는지 확인**이 먼저.
- **ankle_roll(RS00 14)**: G1도 peak 14지만 **우리 로봇이 더 무거움(51.5 vs G1 ~35kg)**. eval(peak 16>14)+동엽님 일치 → **DM-J4340-2EC(27/9, 40:1)로 상향**([스왑 노트](2026-07-01_ankle_dm4340_swap.md)). 속도 1/4(무부하 100rpm)이나 앵클롤 운전점 저속이라 flat 0.2%만 클립.

---

## 4. 계획

| 단계 | 내용 |
|---|---|
| **now** | action_scale=0.25 fresh 학습 (8192 envs, →30001 iter, ≈10h) |
| 다음 | 완료→ ① worst-case 재측정 + **actuator eval 재실행**(binding 재판정) ② Target-vs-Actual 추종 재평가 |
| 그 후 | Kp/Kd A안(I_total 보정) 학습 → 추종/토크사용 개선 확인 |
| HW | 재측정 부하 확정 후 ankle_roll→DM-J4340 반영 재학습 |

**변경**: `pygmalion_constants.py` action_scale `0.25*e/s` → `0.25`. run: `logs/rsl_rl/pygmalion_velocity/<2026-07-02_*>`, 명령 `uv run train Mjlab-Velocity-Flat-Pygmalion --env.scene.num-envs 8192 --video True`.
