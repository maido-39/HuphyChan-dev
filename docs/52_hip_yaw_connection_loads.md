# 52 · Hip-yaw 커넥션(thigh_link) 하중 심화 — 부호 world p99 + 로컬 축분해

> 2026-07-08. Knee↔Hip-yaw 사이, **hip_yaw 조인트가 구동하는 링크 = `thigh_link`**(hip_yaw 자식 body)에 걸리는 반력/모멘트를 (1) world 프레임 **부호 포함** 6-DoF, (2) 링크 **로컬 beam 축**으로 분해해 percentile(p1/p50/p99/min/max)로 정리. HW 설계(단면·베어링·핀 사이징)용. 관련: [[46_wrench_6dof_loads]](per-joint 6-DoF), [[2026-07-07_beyondmimic_vs_g1_method]](b3 vs c1 게인).

## 1. 방법 (파이프라인)
- 원천: `analysis/out/<run>.npz` 의 per-body `Fx/Fy/Fz/Tx/Ty/Tz_{L,R}_thigh_link` (MuJoCo `cfrc_int`, **world 프레임·CoM**) + `qpos_full`(T×19).
- **World 부호 p99**: L·R 샘플 풀링 후 성분별 percentile. 부호가 있어 음극단 $p_1$·양극단 $p_{99}$ 양쪽을 냄. 스크립트 `analysis/hip_yaw_wrench_p99.py`.
- **로컬 축분해**: `qpos_full`을 런 자체 모델(`<run>_model.mjb`)로 리플레이 → 프레임별 `xmat`(body→world) 복원 → $v_{local}=R^\top v_{world}$. 장축 단위벡터 $\hat a$ = thigh 로컬프레임에서 자식 `shin_link.pos` 방향(→무릎). 스크립트 `analysis/thigh_local_axis_p99.py`.
  $$F_{axial}=\vec F_{l}\cdot\hat a,\quad F_{radial}=\lVert \vec F_{l}-F_{axial}\hat a\rVert,\quad M_{torsion}=\vec M_{l}\cdot\hat a,\quad M_{bend}=\lVert \vec M_{l}-M_{torsion}\hat a\rVert$$
  $F_{axial}$·$M_{torsion}$은 부호(+ = 무릎방향 압축 / 비틀림), $F_{radial}$·$M_{bend}$은 크기($\ge 0$).
- 대상 3종: **b3_demo**(final flat), **c1_final**(BeyondMimic-critical flat), **worstcase_rough**(설계 상한).

## 2. 로컬 축분해 p99 (핵심 — 설계에 직접 사용)

![[hipyaw_thigh_local_axis_p99.png]]

| dataset | F_axial p99 [N] | F_radial p99 [N] | M_torsion p99 [N·m] | M_bend p99 [N·m] |
|---|--:|--:|--:|--:|
| b3 (final flat) | 416 | 138 | 10 | 53 |
| c1 (BM-critical) | 428 | 173 | 15 | 79 |
| worstcase rough | 671 | 342 | 26 | 149 |

전체 p1/p50/p99/min/max: `docs/mujoco/assets/thigh_local_axis_p99.csv`

**설계 함의**
- **축압축 지배**: $F_{axial}$ p50 $\approx$ 180 N(한 다리 체중지지), p99 416 N(flat)/671 N(rough). thigh는 **압축·좌굴(buckling) 부재**로 사이징.
- **전단(radial)은 축력의 $\sim$1/3** (p99 138–342 N) — 무릎 커넥터 전단핀·볼트 대상.
- **굽힘 $\gg$ 비틀림** ($M_{bend}$ 53 vs $M_{torsion}$ 10, flat): 링크는 **굽힘 지배** → 단면을 굽힘축 방향으로 최적화, 비틀림 여유는 큼.

## 3. World 프레임 부호 p1..p99 (방향성)

![[hipyaw_thigh_world_signed_p99.png]]

부호 규약: $F_x$ 전후(+전진), $F_y$ 좌우(+좌), $F_z$ 수직(+상). $F_z$ p50 $\approx -180$ N = 체중 정적 반력(하향).

**b3_demo** (final flat)

| 성분 | p1 | p50 | p99 | min | max |
|---|--:|--:|--:|--:|--:|
| F_x [N] | −72.1 | −0.7 | 68.9 | −114.0 | 91.3 |
| F_y [N] | −43.8 | −1.1 | 60.1 | −77.2 | 142.6 |
| F_z [N] | −431.2 | −186.8 | 118.7 | −492.6 | 166.5 |
| M_x [N·m] | −26.7 | 5.4 | 35.1 | −57.6 | 51.0 |
| M_y [N·m] | −38.7 | −1.7 | 37.2 | −100.9 | 103.5 |
| M_z [N·m] | −7.6 | −0.1 | 7.9 | −17.6 | 17.1 |

**c1_final** (BeyondMimic-critical flat)

| 성분 | p1 | p50 | p99 | min | max |
|---|--:|--:|--:|--:|--:|
| F_x [N] | −74.1 | −0.4 | 73.9 | −226.9 | 166.7 |
| F_y [N] | −73.9 | −0.1 | 75.1 | −204.1 | 171.4 |
| F_z [N] | −446.2 | −183.9 | 139.2 | −594.3 | 256.9 |
| M_x [N·m] | −53.1 | 0.4 | 55.0 | −121.3 | 105.8 |
| M_y [N·m] | −48.9 | −0.1 | 51.0 | −134.0 | 108.8 |
| M_z [N·m] | −10.7 | 0.1 | 10.3 | −26.5 | 27.0 |

**worstcase_rough** (설계 상한 엔벨로프)

| 성분 | p1 | p50 | p99 | min | max |
|---|--:|--:|--:|--:|--:|
| F_x [N] | −180.6 | −0.7 | 175.8 | −2116 | 2610 |
| F_y [N] | −172.7 | −0.8 | 179.1 | −2588 | 2472 |
| F_z [N] | −673.9 | −154.3 | 170.0 | −3564 | 2004 |
| M_x [N·m] | −78.0 | −0.4 | 79.4 | −1176 | 1210 |
| M_y [N·m] | −79.9 | 0.1 | 86.3 | −553 | 993 |
| M_z [N·m] | −29.9 | −0.1 | 25.9 | −742 | 820 |

전체(42개 데이터셋): `docs/mujoco/assets/hip_yaw_thigh_wrench_p99.csv`

**관찰**
- **$F_z$(수직) 지배**, $F_x/F_y$·모멘트는 $\pm$70 N/40 N·m대로 작음.
- **부호 대칭**: $F_x,F_y,M_x,M_y,M_z$ 모두 $p_1\approx-p_{99}$, $p_{50}\approx0$ → 보행 중 좌우 교번하중(**피로설계** 대상). $F_z$만 한쪽(−)으로 치우침.
- **c1 > b3** (모멘트 p99: $M_x$ 35→55, $M_y$ 37→51 N·m): Kd를 link-critical로 올리며 감쇠토크 증가. **아직 학습 중(iter~3500)이라 잠정** — 종료 후 재측정.
- **worstcase min/max**는 러프 순간 스파이크($F_z$ −3564 N) → 구조 안전율용. 상시하중은 p99 기준.

## 4. 재현
```bash
uv run python analysis/hip_yaw_wrench_p99.py       # world 부호 p99 (전 42셋)
uv run python analysis/thigh_local_axis_p99.py     # 로컬 축분해 p99 (3셋)
uv run python analysis/plot_hipyaw_loads.py        # 플롯 2종
```
