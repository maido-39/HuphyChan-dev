# 58 · 2-RSU 발목 설계기 — 이론·기능 리서치 & 개발 스펙

> 2026-07-08. 2-RSU(Rotary-Spherical-Universal) 발목 3D 설계툴 개발 전 리서치(Fable5 ×2: 이론/알고리즘 + 유사툴/기능). 1차 참조 **Cervettini et al., "A Framework for Optimal Ankle Design of Humanoid Robots," Humanoids 2025** ([arXiv:2509.16469](https://arxiv.org/abs/2509.16469)) — 우리 [mech_design_eval.py](../mujoco-sim/mjlab/analysis/mech_design_eval.py) J^T 프레임워크의 원출처. 큐: [[project-2rsu-ankle-tool]]. 이론 검증: J는 IK 유한차분과 수치 대조(빌드 시 1줄 테스트).

## 1. 기구 모델 & 프레임 ({S}=정강이, 원점=짐벌중심 U₀)
림 $i\in\{A,B\}$: $a_i$=크랭크 피벗위치(고정), $\hat z_i$=모터 회전축(단위), $\hat u_i,\hat v_i=\hat z_i\times\hat u_i$=크랭크 평면 정규기저($\hat u_i$=$\alpha_i{=}0$ 크랭크방향), $c_i$=크랭크길이, $r_i$=로드길이, $b_i$=발판 로드엔드(발 프레임 {F} 고정).
- 플랫폼 회전(짐벌 둘레): $R(\phi,\vartheta)=R_y(\vartheta)R_x(\phi)$ (roll $\phi$, pitch $\vartheta$; 한 규약 고정).
- 크랭크핀 $p_i(\alpha_i)=a_i+c_i(\cos\alpha_i\,\hat u_i+\sin\alpha_i\,\hat v_i)$, 발엔드 $q_i(\phi,\vartheta)=R\,b_i$, 로드 $l_i=p_i-q_i$, 제약 $\lVert l_i\rVert=r_i$.

## 2. 역기구학 (림별 폐형)
$d_i=q_i-a_i$, 크랭크가 $\hat z_i\perp$이므로 $d_i$의 평면성분만 결합:
$$A_i\cos\alpha_i+B_i\sin\alpha_i=C_i,\quad A_i=c_i(\hat u_i\!\cdot\! d_i),\ B_i=c_i(\hat v_i\!\cdot\! d_i),\ C_i=\tfrac12(c_i^2+\lVert d_i\rVert^2-r_i^2)$$
$$\boxed{\ \alpha_i=\operatorname{atan2}(B_i,A_i)\pm\arccos\!\big(C_i/\sqrt{A_i^2+B_i^2}\big)\ }$$
- **존재(=워크스페이스 경계)**: $C_i^2\le A_i^2+B_i^2$. 실패=로드가 크랭크원↔발엔드 못이음.
- **분기**: dyad elbow up/down 2해. 조립자세($\phi{=}\vartheta{=}0$)서 CAD 부호 선택 → 스윕 중 **직전 $\alpha_i$에 가장 가까운 해 추적**(림별 독립, per-pose 고정부호는 가짜 구멍/부호flip).
- ★ arcsin 아닌 **atan2±acos** 사용(사분면 안전).

## 3. Jacobian (속도루프) & 정역학
$\lVert l_i\rVert^2=r_i^2$ 미분 → $l_i\cdot(\dot p_i-\dot q_i)=0$, $\dot p_i=\dot\alpha_i(\hat z_i\times(p_i-a_i))$, $\dot q_i=\omega\times q_i$:
$$J_i=\frac{(q_i\times l_i)^{\mathsf T}E(\vartheta)}{\,l_i\cdot(\hat z_i\times(p_i-a_i))\,},\qquad [\dot\alpha_A,\dot\alpha_B]^{\mathsf T}=J\,[\dot\phi,\dot\vartheta]^{\mathsf T}$$
오일러율→$\omega$: $\omega=E(\vartheta)[\dot\phi,\dot\vartheta]^{\mathsf T}$, $E=[\,R_y(\vartheta)\hat x\ \ \hat y\,]$ (3×2). ★$E$ 빼면(오일러율을 $\omega$로 오인) 중립 밖 토크 오류.
**정역학(가상일)**: $\tau_{plat}=J^{\mathsf T}\tau_{mot},\quad \tau_{mot}=J^{-\mathsf T}\tau_{plat}$ — 이게 mech_design_eval의 $\tau=J^{\mathsf T}f$. (스크류 교차검증: S-U 로드는 로드축 순수力 1개 전달 → 짐벌모멘트 $q_i\times\hat l_i$=분자, 모터축모멘트=분모, 동일 $J$.)

## 4. 워크스페이스 & 특이점 (Gosselin-Angeles 1990)
$A[\dot\phi,\dot\vartheta]^{\mathsf T}+B\dot\alpha=0$, $A$행=$(q_i\times l_i)^{\mathsf T}E$, $B=-\mathrm{diag}(l_i\cdot(\hat z_i\times c_i))$.
- **Type1 (serial, $\det B{=}0$)**: 크랭크-로드 데드센터 = **IK존재경계 = 워크스페이스 경계**. 플랫폼 이동성↓, 力전달→∞(토글). 도달 제약.
- **Type2 (parallel, $\det A{=}0$)**: 두 로드 모멘트축 종속 → 플랫폼 자유도 획득 → **$J^{-\mathsf T}$ 발산=필요 모터토크 →∞**. ★사용영역을 이걸로 제한. 잘 설계된 발목은 작동영역을 Type2서 멀리 둠.

**격자 알고리즘**: (φ,ϑ) ±60°격자 → 림별 $A,B,C$ → $C^2{>}A^2{+}B^2$면 미도달 → 아니면 $\alpha$(연속분기)·$J$ 계산 → $|\det J|$·특이점 tol 체크(분모 $|l_i\cdot(\hat z_i\times c_i)|{>}\epsilon$ 가드) → (선택) S콘/U레인지/간섭 필터.

## 5. 토크맵 & 조작성 (R-P 평면에 그릴 것)
- **필요토크맵**(사이징 핵심): 수요 $\tau_{plat}$(우리 측정 ankle_pitch/roll)에서 $\tau_{mot}=J^{-\mathsf T}\tau_{plat}$ → R-P를 $\max_i|\tau_{mot,i}|/\tau_{rated}$로 색칠. Type2 근처 발산.
- **능력 zonotope**(2모터엔 정확): $\tau_{mot}\in[-\tau_{max},\tau_{max}]^2$의 플랫폼토크 도달집합 = **평행사변형** $J^{\mathsf T}\cdot\text{box}$, 꼭짓점 $J^{\mathsf T}[\pm\tau_{max},\pm\tau_{max}]$. 커서자세서 이 평행사변형에 **수요점 안/밖**=충분성 판정.
- **조작성**: $\kappa=\sigma_{max}/\sigma_{min}$ of $M=JJ^{\mathsf T}$ (Cervettini 설계비용항). 힘타원체 $\{\tau_p:\tau_p^{\mathsf T}(J^{\mathsf T}J)^{-1}\tau_p\le\tau_{max}^2\}$.

## 6. 툴 기능 스펙 (유사툴 리서치 종합)
참고: PMKS+(웹 UX·URL상태·관절플롯), GIM(워크스페이스 격자스캔), pycapacity(힘 폴리토프), SAM(force+동기플롯), Linkage/Rector(편집중 무정지).
- **파라미터 패널**: 슬라이더+수치+🔒잠금/◇범위(4절툴 재사용), **프리셋=우리 실물**(r_c30/a_p60/a_r40mm, RS03 60/20 실측TN), URL/localStorage 상태.
- **3D 뷰**(Three.js 없이): Zdog식 프리미티브(조인트=원·로드=round-cap 굵은선·플랫폼=채운path) + painter's algorithm + **직교투영** + orbit(드래그 yaw/pitch). ~70줄.
- **R-P 히트맵** + 레이어토글 {도달성 / 모터토크 이용률% / 1/κ(J)}, **워크스페이스 경계곡선**, **특이점 등고선**, **실측 수요영역 오버레이**(우리 ankle 측정 R-P·τ).
- **양방향 커서**(맵↔3D): 맵 커서→3D 자세, 3D 플랫폼 드래그→맵. 커서자세 readout(α_A,α_B, τ_mot, κ) + **능력 평행사변형 + 수요점**.
- 특이점 근처 링크 빨강경고, 편집중 무정지 재계산(디바운스).

## 7. 우리 파라미터화 (스케치 + 누락분 확정)
사용자 스케치(X+=전방): b=크랭크축 Y오프셋(±미러), a=모터축간거리, f=모터축↔발바닥, α=크랭크길이($c_i$), β=로드길이($r_i$), c=발엔드 Y오프셋, e=R-P중심↔바닥, d=발엔드↔바닥. **누락(§1 필요)**: 크랭크중심 X(cx)·발엔드 X(px)·**크랭크축 방향 $\hat z_i$**·**홈위상 $\hat u_i$**. → ★순수 Y-Z 평면은 roll만(pitch 0), pitch엔 X구조 필수. 기본가정: $\hat z_i\parallel Y$(시상면 스윙), cx로 pitch레버 생성.

## 8. 참고문헌
★ [Cervettini Humanoids 2025 (arXiv:2509.16469)](https://arxiv.org/abs/2509.16469) — RSU 폐형IK·$\tau=J^{\mathsf T}f$·$M=JJ^{\mathsf T}$·IK존재영역에 워크스페이스 포함 설계. [ASME JMR 2018 humanoid parallel ankle](https://asmedigitalcollection.asme.org/mechanismsrobotics/article-abstract/10/5/051015/474148) · [Gosselin&Angeles 1990 특이점분류](https://www.researchgate.net/profile/Clement-Gosselin/publication/3298042_Singularity_Analysis_of_Closed-Loop_Kinematic_Chains) · [2SPRR+1U ankle](https://link.springer.com/chapter/10.1007/978-3-319-93188-3_49) · Merlet *Parallel Robots*, Tsai *Robot Analysis*.
툴: [PMKS+](https://pmksplus.com/) · [GIM](https://www.ehu.eus/compmech/software/) · [pycapacity](https://github.com/auctus-team/pycapacity) · [SAM](https://www.artas.nl/en/sam/features/analysis) · [Zdog](https://zzz.dog/).
Unitree G1: **PR모드**(펌웨어가 pitch/roll 변환) vs **AB모드**("병렬기구 운동학 직접 계산") — 방정식 미공개, 위 수식이 그 gap.

## 원시 인용
- Cervettini: *"v ≜ J(q)q̇ … τ = J(q)ᵀf"*, IK 존재식 *"ρᵢ sin(αᵢ+ϕᵢ)=kᵢ"*, 설계재파라미터화로 목표 R-P영역 Ω를 *"entirely contained within the region where the IK problem admits solutions"*. 최적 RSU가 serial 대비 최대 41% 개선.
- Gosselin-Angeles: det A(Type2, 플랫폼 자유도획득)·det B(Type1, 다리한계) 3분류.
- Unitree: AB모드는 *"requires users to calculate the parallel mechanism kinematics themselves"*.

## 7. 문헌 보강 (2026-08-04 재검색)
본 노트(1차: Cervettini RSU 프레임워크)에 더해 설계 선례 추가:
- **RH5 휴머노이드** ([arXiv:2101.10591](https://arxiv.org/pdf/2101.10591)) — 발목 2-DOF를 **2SPRR+1U** 병렬로 구동, 직렬-병렬 하이브리드 전신 설계. 우리 2-RSU와 위상은 다르나 "발목 병렬화로 원위 질량 절감" 동일 사조.
- **2SPRR+1U 운동학 해석** ([Springer](https://link.springer.com/chapter/10.1007/978-3-319-93188-3_49)) — 대수기하로 FK/IK·워크스페이스·특이곡선.
- **Ankle-Knee 병렬 다리** ([IEEE 10907561](https://ieeexplore.ieee.org/document/10907561/)) — 발목에 2-RSS(우리와 근접 위상), 무릎까지 평행사변형 연동.
- ★**PKM 최적화 w/ 조인트 리밋·간섭 제약** ([arXiv:2202.11950](https://arxiv.org/pdf/2202.11950)) — 국소+전역 결합 탐색, **스페리컬 요동한계를 명시적 제약으로** 넣는 접근 = 우리 v2 swing/swing_foot 제약과 동일 사조. 멀티스타트 전역성 검증 방법론 참조처.
결론: 우리 파이프라인(폐형 IK + 유한차분 J + 실측수요 replay + Deb/사전식 + 요동각 제약 + 멀티스타트)은 문헌 프레임워크(Cervettini)에 실측 수요·G1 검증·peak/P99 계층을 얹은 확장형 — 위상 대안(2SPRR+1U, 2RSS)은 현 CAD 확정으로 비채택.
