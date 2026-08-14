# 54 · hip_yaw RS03 액추에이터 부하 분석 (모터토크 vs 출력베어링 하중)

> 2026-07-08. "무릎 이하 다리를 hip_yaw RS03 하나가 버티나?"에 답하기 위해, thigh_link 반력 wrench를 **hip_yaw 회전축 기준**으로 분해. 액추에이터 한계는 **2개(모터토크 / 출력베어링)** 이고 서로 독립이라 분리 평가. [[52_hip_yaw_connection_loads]](beam축 분해, 10.8° 차이)·[[bc-kd-controlled-ab]] 연계. 스크립트 `analysis/hip_yaw_actuator_loads.py`.

## 1. 분석 프레임 — 2개의 독립 한계
hip_yaw 축 $\hat a_{yaw}$ = thigh 프레임 $[0,0,-1]$ (수직, beam축과 10.8°차). 반력 wrench를 이 축으로 분해:

| 성분 | 정의 | 받는 곳 | 대조 정격 |
|---|---|---|---|
| **M_motor** | \vec M·â_yaw | **모터**(능동) | RS03 토크(연속20/피크60 N·m) |
| **M_bend** | \lVert\vec M_⊥\rVert 전복모멘트 | **출력 베어링** | 틸팅모멘트 정격 |
| **F_axial** | \vec F·â_yaw 스러스트 | 출력 베어링 | 축하중 정격 |
| **F_radial** | \lVert\vec F_⊥\rVert | 출력 베어링 | 반경하중 정격 |

★모터토크(①)와 베어링하중(②)은 별개 — "다리무게를 버티나"는 주로 ②(전복모멘트·스러스트).

## 2. 결과 (p99, L+R pooled)

| 성분 | b3 **공칭** p99 | worst **엔벨로프** p99 | worst max (러프 스파이크) |
|---|--:|--:|--:|
| **M_motor** [N·m] | 16.1 | 35.7 | 618 |
| **M_bend** [N·m] | **51.5** | **146.5** | 1534 |
| **F_axial** [N] | 389 | 662 | 3566 |
| **F_radial** [N] | 207 | 378 | 2687 |

전체 p1/p50/p99/min/max: `docs/mujoco/assets/hip_yaw_actuator_loads.csv`

## 3. 진단 (RS03 = 피크60 / 연속20 N·m)
- **① 모터토크 OK**: M_motor 공칭 p99 **16 N·m < 연속 20**, worst p99 36 < 피크 60. yaw 방향 토크는 RS03가 충분. (단 연속20에 근접 → 지속 yaw회전 많으면 thermal 체크.)
- **② 걸림돌 = 전복모멘트 M_bend 공칭 51 N·m** — 캔틸레버로 매달린 다리의 굽힘을 **출력 베어링 하나가 반력**. + 스러스트 389N·전단 207N 동시. QDD 출력 베어링 틸팅정격이 보통 수십 N·m급이라 **마진 빠듯 가능성 큼**.

→ 사용자 우려는 방향은 맞되 **원인은 모터가 아니라 출력 베어링의 전복모멘트**. [[52_hip_yaw_connection_loads]] 캔틸레버(16mm)→양단지지(315mm) 논의와 동일 지점: knee쪽 보조지지로 $M_{bend}/L$ 분산 시 far-side 하중 **~20× 감소**(315/16).

## 4. FEA/스펙 체크용 하중 케이스 (복합하중 동시 인가)
출력 플랜지에 4성분을 **동시에** (베어링은 축+반경+모멘트 합산):

| 케이스 | M_bend | F_axial | F_radial | M_motor | 용도 |
|---|--:|--:|--:|--:|---|
| **A 공칭/피로** (b3 p99) | 51 | 389 | 207 | 16 | 상시 반복 → L10 수명·틸팅정격 |
| **B 마진** (worst p99) | 147 | 662 | 378 | 36 | 정적 안전율 |
| **C 극한** (worst max) | 1534 | ±3000 | 2687 | — | 항복/파단(생존, outlier) |

**할 일**: (1) RS03 데이터시트 출력베어링 틸팅모멘트/축·반경 정격 확보 → 케이스A M_bend 51과 안전율 비교. (2) 부족 시 **straddle(양단지지)** — knee쪽(315mm) 보조베어링 추가로 M_bend 분담. (3) M_motor 연속20 근접 → yaw 지속명령 thermal 확인.

## 재현
```bash
uv run python analysis/hip_yaw_actuator_loads.py --npz b3_demo worstcase_rough
```
