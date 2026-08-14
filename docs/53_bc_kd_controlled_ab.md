# 53 · B vs C — Kd 단일변인 통제 A/B (under-damped 6 vs link-critical 14/35/16)

> 2026-07-08. **가설**(BeyondMimic식): stiff Kp에 Kd를 실제 link 관성 기준 critical로 올리면 sim 진동↓·매끄러운 gait → real 전이·하중 개선. **검증**: seed 42, 10000-iter 단일런, **오직 joint damping만 차이**(env.yaml diff로 확인)인 B/C를 동일 flat command schedule로 측정. 관련: [[52_hip_yaw_connection_loads]], [[2026-07-07_kpkd_beyondmimic_derivation]], [[ankle-actuator-tn-sizing]].

## 1. 변인통제 (검증됨)
| | B (baseline) | C (BeyondMimic-critical) |
|---|---|---|
| run | 2026-07-07_18-51-51 @9999 | 2026-07-08_03-29-40 @9999 |
| hip_pitch/roll Kd | 6.0 | **35.0** |
| hip_yaw Kd | 6.0 | **14.0** |
| knee Kd | 6.0 | **16.0** |
| ankle Kd | 1.81 | 1.81 (동일) |
| 그 외 env.yaml | — | **완전 동일** (diff = damping 3줄뿐) |
| seed | 42 | 42 |

$K_d^{crit}=2\sqrt{K_p I_{link}}$ ([[2026-07-07_kpkd_beyondmimic_derivation]]): hip $\zeta$ 0.16→~1, knee 0.36→~1. B는 심한 under-damped($\zeta$ 0.16).

## 2. 결과 — **가설과 반대**: C가 하중을 크게 증가시킴

![[bc_kd6_vs_kd14.png]]

**Foot GRF** (per-foot $|F_z|$, L+R pooled; BW=505 N)
| | B (Kd6) | C (Kd14) | C/B |
|---|--:|--:|--:|
| peak | 2.1 BW | **6.1 BW** | 2.88× |
| p95 | 1.1 BW | 1.2 BW | 1.15× |

**관절 토크** [N·m] (L+R pooled)
| joint | B p95 | C p95 | C/B | B peak | C peak |
|---|--:|--:|--:|--:|--:|
| hip_pitch | 44.7 | 102.1 | **2.28×** | 119.6 | 120.0 (한계) |
| hip_roll | 42.9 | 72.3 | 1.68× | 82.6 | 120.0 (한계) |
| hip_yaw | 15.6 | 34.8 | 2.23× | 46.5 | 60.0 (한계) |
| knee | 27.8 | 96.0 | **3.45×** | 120.0 | 120.0 (한계) |
| ankle_pitch | 30.9 | 45.2 | 1.46× | 88.8 | 90.0 |
| ankle_roll | 6.9 | 11.3 | 1.63× | 17.6 | 50.0 (한계) |

**thigh(hip_yaw 커넥션) 로컬축 p99**
| 성분 | B (Kd6) | C (Kd14) | C/B |
|---|--:|--:|--:|
| F_axial [N] | 557 | 784 | 1.41× |
| F_radial [N] | 186 | 377 | **2.03×** |
| M_torsion [N·m] | 11 | 45 | **4.1×** |
| M_bend [N·m] | 85 | 179 | 2.11× |

## 3. 안정성 확인 (둘 다 정상 — C가 실패한 게 아님)
| | base_z mean/min/max | upright(z) min | 낙상 |
|---|---|---|---|
| B | 0.851 / 0.702 / 0.904 | 0.882 | 0.0% |
| C | 0.847 / 0.697 / **1.060** | 0.786 | 0.0% |

둘 다 넘어지지 않고 직립 보행. C는 base_z가 1.06까지(B 0.90) 튀고 upright min 0.79(B 0.88) → **C가 더 공격적·바운시한 gait**(하중↑의 원인). eval 실패 아티팩트가 아니라 실제 학습된 거동.

## 3b. q/qtarget/error 분석 — 토크 폭증의 근본원인 ([[feedback-qtarget-analysis-rule]])
qtarget = 실제 모터지령(`sim.data.ctrl`). PD 회귀 `tau ~ Kp·e − Kd·qdot`:

| | PD fit R² | 포화율(|tau|≥95%한계) | tracking err_p95 (knee) |
|---|---|---|---|
| B (Kd6) | **1.00** (전 관절) | **0.0%** (전 관절) | 0.15 rad |
| C (Kd14) | 0.56–0.88 (**깨짐**) | 0.2–2.4% (**전 관절 한계 도달**) | 0.36 rad (2.4×) |

**config-gain 감쇠항 수요 `|Kd·qdot|` p95** (원인 확정):

| 관절 | B: Kd·qdot | C: Kd·qdot | actuator 한계 |
|---|--:|--:|--:|
| hip_pitch | 15 | **157** (10.5×) | 120 |
| knee | 32 | **151** (4.8×) | 120 |
| ankle (Kd 불변) | 7.5 | 9.9 (≈동일) | 90 |

★ **근본원인**: C의 **감쇠토크 수요 하나만으로 액추에이터 한계(120)를 초과**(hip 157, knee 151) → 포화(R² 붕괴) → qtarget 추종 실패(err 2.4×) → 공격적 gait → qdot↑ → 악순환. **Kd 안 바꾼 ankle은 D항 그대로** = 순수 Kd 상향이 원인임을 관절별 분리 입증. "link 관성 임계감쇠"가 **액추에이터 토크예산 무시**한 오류.
![[qtarget_error_bc.png]]

![[ghost_B_Kd6_vs_C_Kd14.mp4]]

## 4. Tracking 비교 (caveat 종결 — C가 tracking도 열세)
qpos_full 유한차분으로 achieved base 속도 복원 → heading 프레임서 cmd와 비교(mean $|achieved-cmd|$, command 전환 후 15샘플 settle-mask). `analysis/bc_tracking.py`.

| 성분 | B (Kd6) | C (Kd14) | C/B | 승자 |
|---|--:|--:|--:|---|
| err_vx [m/s] | 0.272 | 0.770 | 2.83× | **B** |
| err_vy [m/s] | 0.358 | 0.508 | 1.42× | **B** |
| err_wz [rad/s] | 0.227 | 1.154 | 5.08× | **B** |

C는 **전 성분에서 tracking이 2.8–5× 나쁨**. (finite-diff라 err_wz 절대값엔 노이즈 있으나, 3성분 모두 + §2 하중·§3 바운시 gait와 방향 일관 → 견고.)

## 5. 해석 & 결론
- **물리**: Kd↑ = 관절이 속도를 강하게 억제 → (a) 컴플라이언스↓ → 충격력 전달↑(GRF peak 6.1 BW) + 감쇠토크 자체↑(knee p95 3.5×, 다수 토크한계 포화), (b) policy의 명령운동을 방해 → tracking↓. under-damped B가 **하드웨어에 더 부드럽고 tracking도 우수**.
- **가설 반증 (확정)**: "link-critical Kd로 진동↓·전이↑" 기대와 정반대. C는 **하중 2-3.5× ↑ AND tracking 2.8-5× ↓ = 양 축 모두 열세**. → **link-critical Kd 방향 기각**, under-damped Kd6(B) 유지. C가 knee/hip을 토크한계까지 밀던 것도 사이징 악화([[ankle-actuator-tn-sizing]] 결론과 일관 — B 계열 저Kd가 옳음).
- **남은 확인**: C의 원 동기였던 "sim 진동/wobble"은 별도 스펙트럼 분석 대상이나, tracking·하중이 모두 나쁜 이상 우선순위 낮음. real 전이 견고성은 하드웨어 확보 후 검증.

## 재현
```bash
bash analysis/bc_compare_driver.sh          # measure B/C + ghost
uv run python analysis/bc_metrics.py        # GRF + 관절토크 표
uv run python analysis/thigh_local_axis_p99.py  # thigh 로컬축 (B,C 포함)
uv run python analysis/bc_tracking.py       # velocity tracking error
uv run python analysis/plot_bc.py           # 비교 플롯
```
CSV: `docs/mujoco/assets/bc_metrics.csv`, `docs/mujoco/assets/thigh_local_axis_p99.csv`
