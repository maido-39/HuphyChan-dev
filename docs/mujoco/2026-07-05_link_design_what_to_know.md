# 링크 구조 설계 — 내가 알아야 하는 것들 (지식 지도)

> 2026-07-05. 목적: knee 원격 링크(push-rod)·ankle 2-RSU 병렬을 **내 손으로 설계·판정**하기 위해 필요한 지식을 분야별로 정리. "따라하기"가 아니라 계산으로 판단하기 위함.
> 관련: [기구 설계 방법론](2026-07-03_knee_ankle_mechanism_design.md) · [serial vs 2-RSU](2026-07-04_serial_vs_2rsu_analysis.md) · [sim2real 방법](2026-07-04_2rsu_knee_sim2real_method.md)

---

## 0. 한 장 지도 — 설계는 이 사슬을 닫는 것

$$\text{관절 부하 수요}\;(\tau_j,\omega_j)\;\xrightarrow{\;\text{기구 } r(q),J(q)\;}\;\text{모터 수요}\;(\tau_m,\omega_m)\;\xrightarrow{\;\text{TN곡선}\;}\;\text{판정}$$

이미 왼쪽(부하 수요)은 측정했고 오른쪽(모터 스펙)은 안다. **가운데의 기구 사상 $r(q),J(q)$ 를 내가 만들 줄 알아야** 나머지가 연결된다. 그래서 아래 1번(기구학)이 심장.

---

## 1. 기구학 (Kinematics) — ★심장, 가장 먼저

**무엇**: 모터 각도 → 관절 각도의 관계, 그리고 그 미분(레버비/Jacobian).

### Knee = 1-DOF 4절(또는 슬라이더-크랭크) 링크
![[Pasted image 20260708205242.png]]
- 구성: 대퇴부 **크랭크**(모터축) → **푸시로드**(양단 볼조인트) → 정강이 **레버**.
- 폐루프 기하 → 관절각 $\theta_j$ 와 모터각 $\theta_m$ 의 관계는 **코사인 법칙 수준의 대수식**으로 닫힌다.
- 핵심 미분량 = **레버비** $r(q) = \dfrac{\partial \theta_j}{\partial \theta_m}$ — 각도마다 변한다(비선형). $r$ 이 크면 모터 토크가 줄지만($\tau_m=\tau_j/r$) 모터가 더 빨리 돌아야 한다($\omega_m=\omega_j\,r$).

### Ankle = 2-DOF 병렬 (2-RSU)
- 구성: 정강이 위 **모터 2개** → 로드 2개(**U-joint + Spherical**, 그래서 R-S-U) → 발판.
- 두 로드가 같이 밀면 pitch, 반대로 밀면 roll → **두 모터가 두 자유도에 커플링**.
- 핵심 = **2×2 Jacobian** $J(q)$: $\begin{bmatrix}\dot\theta_{pitch}\\\dot\theta_{roll}\end{bmatrix} = J(q)\begin{bmatrix}\dot\theta_{m1}\\\dot\theta_{m2}\end{bmatrix}$. 자세(q)마다 값이 다르다.

**알아야 할 것**: 폐루프 위치해석(loop closure), 속도해석으로 Jacobian 유도. → 교과: *로봇 기구학(Denavit 아님, 병렬기구/폐연쇄)*, *기계기구학(Theory of Machines, 4절링크)*. 병렬로봇 Jacobian은 **역기구학이 오히려 쉬움**(모터각→관절각 대신 관절각→모터각이 닫힌형).

---

## 2. 정역학 (Statics) — 힘/토크 사상은 Jacobian의 전치

**핵심 원리(가상일)**: $\tau_j\cdot\delta\theta_j = \tau_m\cdot\delta\theta_m$ 에서 바로
$$\tau_m = J(q)^{T}\,\tau_j \qquad(\text{knee 스칼라}:\ \tau_m=\tau_j/r(q))$$
- 즉 **속도는 $J$, 힘은 $J^{T}$** — 같은 기구가 두 사상을 동시에 규정(듀얼리티). 이걸 알면 §1의 $J$ 하나로 토크·속도·부재력이 전부 나온다.
- **로드 부재력**: $F_{rod} = \tau_j / (\text{레버암})$ → 로드 지름·좌굴, 볼조인트 정격, 부착 러그 FEA의 입력.
- 배포 제어도 같은 식: $f_{motor}=J(q)^{-T}\tau_{virtual}$ (Booster Gym 방식, [sim2real 노트](2026-07-04_2rsu_knee_sim2real_method.md)).

**알아야 할 것**: 가상일 원리, Jacobian 전치의 물리 의미. → 교과: *정역학*, *로봇역학 1장*.

---

## 3. 특이점·전달각 (Singularity / Transmission angle) — 안 하면 모터 터짐
![[Pasted image 20260708205249.png]]
- **특이점**: $r(q)\to 0$ 또는 $\det J(q)\to 0$ 인 자세 → $\tau_m\to\infty$. **ROM 안에 절대 들어오면 안 됨**.
- **4절 전달각** $\mu$: 로드와 종동절 사이각. $\mu$ 가 0/180°에 가까우면 힘이 안 실림(toggle). **작동 ROM 전체에서 $45°\lesssim\mu\lesssim135°$** 유지가 설계 규칙.
- **레버 피크 배치**: $r(q)$ 최댓값을 **부하가 가장 큰 관절각**에 정렬(우리 §4 각도-토크 집중대: knee $-40\sim-80°$, ankle dorsi $+10\sim+40°$). = 공짜로 마진 얻는 트릭(RH5가 실제로 함).

**알아야 할 것**: 특이점 판별, 전달각 개념. → 교과: *기구학 특이점/전달각* 절.

---

## 4. 액추에이터 정합 (이미 보유) — 변환된 구름이 TN 안에 드는가
- rated(연속/열) vs peak(순간) 토크, 속도한계, TN곡선. **$RMS(\tau_m)\le rated$**(열), 모든 점이 peak·속도 안.
- 반사관성 $N^2 I_{rotor}$(저감속 QDD라 작음 → 역구동 유리).
- 도구: [`actuator_eval.py`](../../mujoco-sim/mjlab/analysis/actuator_eval.py)·[`mech_design_eval.py`](../../mujoco-sim/mjlab/analysis/mech_design_eval.py)(기하 스윕→마진 히트맵). 지금은 평면근사 → **§1의 실 FK Jacobian으로 교체가 다음 정밀화**.

---

## 5. 기계요소 설계 (Machine elements) — 실물이 되는 부분
| 요소 | 알아야 할 것 | 우리 선택 |
|---|---|---|
| **로드엔드/볼조인트** | 정적·동적 정격, 미스얼라인 각, 유격 | Misumi 로드엔드(양단), 2-RSU는 U+S |
| **크랭크·레버 암** | 축력+굽힘 조합응력, 좌굴, 피로 | 6061/7075, FEA 하중케이스(§2 F_rod·wrench) |
| **피벗 베어링** | 하중정격·수명 L_10, 예압 | 관절 피벗 볼/니들 베어링 |
| **유격(backlash)** | 링크 유격→제어 성능 저하 | 예압·정밀공차로 최소화 |
| **체결** | 볼트 전단·인장, 이완 | 록타이트, 견착 계산 |

**알아야 할 것**: *기계요소설계*(베어링·볼트·피로), *재료역학*(좌굴 오일러식 $P_{cr}=\pi^2EI/(KL)^2$, 조합응력).

---

## 6. ROM·간섭 (Range of motion / interference)
- 사람 관절 ROM을 커버해야: knee $0\sim130°$, ankle pitch $\pm30°$·roll $\pm15°$ 수준(우리 측정 q 구름이 실제 필요 ROM).
- 전 ROM에서 **링크가 toggle(사점)·자기간섭·지면간섭** 없는지 CAD로 스윕 검증.
- **알아야 할 것**: CAD 모션스터디(간섭체크), 우리 측정 q범위.

---

## 7. 제어·sim2real 함의 (연결고리)
- 배포 경계에서 $J^{T}$ 변환층 필요(직렬 sim → 병렬 모터). = peer "Jacobian 임피던스" ([확정 방법](2026-07-04_2rsu_knee_sim2real_method.md)).
- **실 링크 기하 캘리브**(부착점 오차)가 sim2real gap의 큰 축 → 조립 후 관절 ID로 $J(q)$ 실측 보정.

---

## 8. 그래서 공부 우선순위 (내 학습 경로)
1. **병렬기구 기구학 + Jacobian**(§1) — 폐루프 위치·속도해석. *이거 하나가 §2·3·4·7을 다 연다.* 참고: Cervettini(IIT arXiv:2509.16469)가 우리와 동일 파이프라인을 논문화 — §7이 그대로 교본.
2. **가상일·Jacobian 듀얼리티**(§2) — 반나절.
3. **특이점/전달각**(§3) — 4절링크 표준.
4. **기계요소**(§5) — 로드엔드·베어링·좌굴만 우선.
5. CAD 모션스터디·FEA는 형상 확정 후(§6).

**레퍼런스 실물**(우리 체급 link-knee): RH5(DFKI)·Kangaroo(PAL)·BHR8 — 전부 링크/볼스크류(벨트 아님). ankle 2-RSU: G1·Digit·Asimov.

## 9. 다음 실행
- [ ] `mech_design_eval.py`에 **실 부착점 기반 FK Jacobian** 구현(현 평면근사 대체) → §1·2 자동화.
- [ ] 확정 기하 → $F_{rod}$·wrench로 FEA 하중케이스 → 로드·러그·크랭크 치수.
- [ ] CAD에서 전 ROM 간섭·전달각 스윕.
