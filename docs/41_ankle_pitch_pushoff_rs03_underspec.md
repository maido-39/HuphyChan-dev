# 41 · ankle_pitch RS03 push-off under-spec 판정 + fix (gear / motor / spring) — 검증

> [!question] 검증 질문 (사용자 2026-06-22)
> ankle_pitch = RS03 QDD via 1:1 링크(Agibot-X2식 근위재배치), effort cap = RS03 peak ~60 N·m. 실측(gaitfix_v4, **약한** push-off gait): tau_ankle_pitch ∈ [−60,+20] N·m → **이미 −60에서 클립**(plantarflex=push-off 방향), Pmech peak ~265 W(단일샘플). gaitfix_v6에서 push-off 복원(ankle_pushoff 0.1→0.5 + heel→toe CoP rollover)하면 demand 더 상승. **RS03 60 N·m peak가 인간형 push-off에 진짜 under-spec인가? 옳은 fix는? (링크 감속비↑ / 더 큰 모터 / passive toe·SEA offload)**

> [!abstract] 한 줄
> **YES — 직결/1:1로는 RS03 60 N·m가 인간형 push-off에 under-spec.** 인간 발목 plantarflex peak ≈ **1.5 N·m/kg → 51.8 kg서 ~78 N·m**(우리 60의 **1.3×**), peak power **>2.5 W/kg → ~130 W**(우리 265 W 단일샘플은 인간 2배 = 빠른/공격적 push-off나 측정 artifact 의심). 이미 약한 gait서 −60 클립 = HW floor 확정. **★ fix = 링크 감속 N≈1.3~1.5(RS03 유지, T-N 위반 0%)가 1순위** — 발목은 **토크-bound·속도여유**(peak τ@0rpm, max speed@2 N·m)라 감속이 거의 무손실. 2순위 = **passive toe / SEA가 push-off 임펄스 일부 공급해 모터 peak를 낮춤**(문헌: 스프링만으로 impulsive push-off 가능; toe 강성 최적 56 N·m/rad=우리 k60). 모터 교체(3순위)는 비효율 — RS03가 동급 가성비/토크밀도 챔피언(별도 [[39_ankle_qdd_uptorque_survey]]).

> 원문층/raw excerpts 본 노트 §6. 관련: [[39_ankle_qdd_uptorque_survey]](§4 RS00 자매판정)·[[36_all_actuator_tn_envelopes]](RS03 봉투)·[[37_ankle_linkage_fidelity]](링크 N 1.5/2.0 sweep)·[[12_toe_stiffness]]·[[19_toe_ablation]]·[[15_toe_joint_research]](toe spring)·[[31_humanoid_hw_comparison]].

---

## 1. RS03 봉투 vs 실측 (joint-side, [[36_all_actuator_tn_envelopes]])

| 항목 | RS03 joint-side | 실측 ankle_pitch | 판정 |
|---|---|---|---|
| peak τ | **60 N·m** | tau ∈ [−60,+20], **−60 클립** | ❌ **토크 100% 포화**(약한 gait서 이미) |
| cont τ (thermal) | **20 N·m** | RMS 25.6 (128% cont) | ❌ **열과부하** |
| 무부하/corner | 200 rpm / corner ~120 | gait 91 rpm (46%) | ✅ **속도여유 큼** → 감속 기회 |
| Pmech | (60×corner) | peak ~265 W(단일샘플) | 인간 ~130W의 2배(빠른 push-off/artifact 의심) |

→ ★ **토크-bound + 속도여유** = 무릎과 동형. 링크 감속이 토크를 (남는)속도와 맞바꿔 포화·열 동시 해소.

## 2. 인간형 push-off 요구 (mass-normalize, 51.8 kg)

| 양 | 인간 정규화 | 51.8 kg 환산 | RS03(60/20) 대비 |
|---|---|---|---|
| ankle **plantarflex moment** | **~1.5 N·m/kg** (preferred-speed gait) | **~78 N·m** | peak 60의 **1.3×** → under-spec |
| ankle **push-off power** peak | **>2.5 W/kg** (타 관절 3배) | **~130 W** | 우리 265W 단일샘플 = 2배(의심) |
| ankle positive **work**/step | (CoM push-off ~19 J @73kg, Huang 2015) | ~13–19 J | toe/SEA가 일부 공급 후보 |
| MTP(toe) moment | ~0.13 N·m/kg | ~6.7 N·m | 우리 toe 15 N·m = 이미 2배+ |

→ **인간형 push-off는 ~78 N·m peak를 요구 — 우리 60 cap을 30% 초과.** 우리 측정이 약한 gait서 이미 −60 클립인 건 정합(인간 78을 60으로 자른 것). v6서 push-off 복원하면 demand가 78쪽으로 상승.

## 3. 동급 휴머노이드 발목 pitch sizing (peer, [[31_humanoid_hw_comparison]])

| 로봇 | 질량 | ankle 메커니즘 | ankle **pitch** 유효 peak | 근거 |
|---|---|---|---|---|
| **우리** | 51.8 kg | RS03 **1:1 직렬링크** | **60 N·m** | MJCF frcrange |
| Unitree G1 | ~35 kg | **2모터 병렬**(A/B) | **~50 N·m** (2모터 합, pitch+roll 공유) | quadruped.de / datasheet |
| Booster T1 | ~30 kg | **2모터 병렬** | joint motor max 130(최대관절), 발목 2모터 공유 | bipedal.de |
| Agibot X2-N | 28 kg | roll액추 + pitch **4절**(근위) | R90 120 또는 R57 30 (+4-bar **감속**으로 유효↑) | arxiv 2604.21541 Table I |
| Cassie/Agility | ~31 kg | **SEA**(6-bar+2 series springs) | 스프링이 push-off 에너지 저장·반환 | — |
| Berkeley Humanoid | 16 kg | 직렬 직결 | 최소 액추 9.7 N·m peak | arxiv 2407.21781 |

- ★ **패턴(roll판정과 동일)**: 우리보다 **가벼운** G1(35)·T1(30)·X2(28)가 발목 pitch에 (a)**2모터 병렬**(토크 합산) 또는 (b)**링크 감속**(X2 4-bar) 또는 (c)**SEA 스프링**으로 유효토크/임펄스를 확보. **51.8 kg(피어 1.5–1.8× 무거움)에 단일 RS03 60 N·m(1:1) = 클래스 최하 토크/kg.** G1조차 50 N·m를 35 kg에 쓰는데 우리는 60을 51.8 kg에 → mass-norm 1.16 vs 1.43 → **우리가 더 빡빡.**
- ★ X2(우리 아키텍처 원형)는 발목 pitch에 **4절 = 감속**을 쓴다 → "1:1"은 X2조차 안 한다. **우리의 1:1이 under-spec의 직접 원인.**

## 4. ★ FIX (우선순위)

### 1순위 — 링크 감속 N≈1.3~1.5 (RS03 유지, 기어박스 불필요) [[37_ankle_linkage_fidelity]] §
발목이 **토크-bound·속도여유** + **토크-속도 분리**(peak τ@0rpm push-off / max speed@swing 2 N·m)라 감속이 거의 무손실:

| N | joint peak | joint 무부하rpm | motor RMS(=25.6/N) | ★T-N 위반(τ·ω 동시) | 판정 |
|---|---|---|---|---|---|
| 1.0(현 1:1) | 60 | 200 | 25.6 (>20 ❌열) | 0% | 포화·열과부하 |
| **1.3** | **78** | 154 | 19.7 (≈20 경계) | 0% | ★ 인간 peak(78) 정확히 커버 |
| **1.5** | **90** | 133 | 17 (✅) | 0% | ★ peak·열 둘다 해소·rough 마진 |
| 2.0 | 120 | 100 | 12.8 (✅) | 0% | 토크과잉·속도 무부하근접(rough서 빡빡) |

- **N=1.3** = 인간 push-off peak(78)를 정확히 맞춤. **N=1.5** = rough+DR(발목 demand ~2배) 마진 포함 권장. 둘 다 **T-N 위반 0%**(고속점 토크 작아 감속 안전), motor 속도 137rpm<200 OK.
- 설계 핵심 = **레버암 2개**: r_m(모터측, 로드힘 F=τ/r_m, 마진위해 r_m≥40–45mm → F≤1.3kN) + N=r_a/r_m(전달비). r_a≈68mm(N1.5) 패키징 검토. (전부 [[37_ankle_linkage_fidelity]] 도출.)
- ⚠ circularity: N 바꾸면 정책 재적응 → **ankle 링크비 sweep**(무릎식 co-design)이 정밀화. flat 데이터 출발점.

### 2순위 — passive toe / SEA가 push-off 임펄스 일부 공급 (모터 peak 저감)
- **문헌: 스프링만으로 impulsive push-off 가능** — "Power to the springs"(MPI-IS 2022): GAS/SOL MTU를 **선형 스프링으로 교체**해도 NMS 시뮬+실로봇이 안정보행+**impulsive APO 유지**. 결론: *"no complex ankle actuation is needed to obtain an impulsive APO if more mechanical intelligence is incorporated"*. → **발목 push-off의 상당부를 passive로 옮길 수 있음**(Achilles tendon=스프링 모사).
- **toe 강성 최적 = 56 N·m/rad = 우리 k60** (Nature Sci Rep 2025) — 우리 toe 스프링이 이미 인간 일치. **stiffer toe가 MTP negative work 감소**(−2.81→−1.81 J, PMC7499201) = push-off 효율↑. toe ablation([[19_toe_ablation]])이 ankle_pitch peak τ·peak power offload를 정량화할 설계.
- **Duke Humanoid(arxiv 2409.19795)** alpha→0: ⚠ **정정** — Duke는 *passive 스프링이 아니라* **active 병렬링크 + RL이 joint를 passive로 끄는(α curriculum 0.5→0) 제어**. CoT **50%↓(sim 0.1m/s)·31%↓(real 0.3m/s, 1.13→0.77)**. 우리엔 *제어측* 교훈(passive dynamics 활용 reward)이지 스프링 HW 아님.
- **prosthetic 디커플 스프링**(Cambridge Wearable Tech 2024, PMC10936356): collision 에너지를 저장→push-off로 재활용하는 **passive** 메커니즘 → SEA/병렬스프링이 ankle 모터 peak를 낮추는 직접 사례.
- 우리 적용: **이미 passive toe 보유** → ankle_pitch push-off의 일부를 toe rollover로 분산(단 [[12_toe_stiffness]]: toe moment 타깃 ~7 N·m로 작음, *주* 동력은 발목). **SEA/병렬 ankle 스프링 추가**가 더 큰 offload — 단 HW 복잡·sim 모델링 필요.

### 3순위 — 모터 교체 (비권장)
[[39_ankle_qdd_uptorque_survey]] §2: **RS03(60/880g/$225/66.7 N·m·kg⁻¹)가 동급 가성비·토크밀도 챔피언.** 동급 Φ98 후보는 토크 같거나↓+1.7–3× 비쌈(DM-J8009 40/$385, AK10-9 48/$699). 60 초과하려면 고감속(AK80-64 64:1, RMD-X10 35:1)=저속·무거움·고가 → push-off 속도 부적합. **링크 감속이 모터 교체보다 싸고 가벼움.**

## 5. 종합 권고

1. ★ **링크 감속 N=1.3~1.5** (RS03 유지) — under-spec의 직접 fix, T-N 위반 0%, 무료감속. **rough+DR sweep 후 최종 확정**(demand ~2배 → N 재검증). X2도 4절=감속을 씀 = 우리 1:1이 예외였음.
2. **passive toe 유지·rollover gait**(k60=인간 일치) + ablation으로 ankle offload 정량화. SEA/병렬스프링은 더 큰 offload지만 HW 복잡 — 차후.
3. **모터 교체 불필요** — RS03 유지가 정답.
4. ⚠ **circularity·gait artifact 캐비엇**: 현 −60 클립은 *약한* gait서도 발생 = HW floor 신호(roll의 v3/v4 판정과 동형). 단 v6 push-off 복원 후 재측정 + 링크비 sweep으로 확정.

## 6. References (URL)

- 인간 ankle plantarflex moment ~1.5 N·m/kg · push-off power >2.5 W/kg(타 관절 3배): https://pmc.ncbi.nlm.nih.gov/articles/PMC4664043/ (JEB 2015, Huang) · https://journals.biologists.com/jeb/article/221/22/jeb182113/20747 (JEB 2018 augmented ankle power)
- CoM push-off ~19.1 J(73 kg, preferred 1.27 m/s): 상동 PMC4664043
- MTP(toe) moment ~0.13 N·m/kg · 4-seg foot: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4101357/
- **"Power to the springs"(스프링만으로 impulsive push-off, MPI-IS 2022)**: https://arxiv.org/abs/2205.00871 · https://dlg.is.mpg.de/publications/buch2022a
- toe 강성 최적 56 N·m/rad=우리 k60: https://www.nature.com/articles/s41598-025-17957-4 · stiffer toe MTP neg-work −2.81→−1.81J: https://pmc.ncbi.nlm.nih.gov/articles/PMC7499201/
- **Duke Humanoid** passive dynamics α→0, CoT 50%/31%↓(병렬링크+제어, 스프링 아님): https://arxiv.org/abs/2409.19795 · https://arxiv.org/html/2409.19795v2
- prosthetic 디커플 passive 스프링(collision→push-off 재활용): https://pmc.ncbi.nlm.nih.gov/articles/PMC10936356/
- Unitree G1 발목 50 N·m·2모터 병렬: https://www.docs.quadruped.de/projects/g1/html/g1_overview.html · https://www.roscomponents.com/wp-content/uploads/2024/11/G1-UNITREE-DATASHEET.pdf
- Booster T1 발목 2모터 병렬·joint motor 130 N·m: http://www.docs.bipedal.de/projects/t1/html/overview.html
- Agibot X2-N 액추에이터표(R90 120 / R57 30, pitch 4절 근위재배치): https://arxiv.org/html/2604.21541v1
- Berkeley Humanoid 액추에이터(9.7 N·m peak): https://arxiv.org/pdf/2407.21781

> [!note] 솔직성 (verified vs 추정)
> **verified**: 인간 1.5 N·m/kg·>2.5 W/kg(JEB)·MTP 0.13(PMC4101357)·"Power to the springs" 결론(arxiv/MPI)·toe 56 N·m/rad(Nature)·Duke 50%/31% CoT(arxiv)·G1 50 N·m 2모터·X2-N 액추표·RS03 60/20 봉투([[36]] 공식 PDF). 링크 N표·T-N 위반 0%·motor RMS=25.6/N는 [[37_ankle_linkage_fidelity]] flat 측정 기반 자체계산. **추정/캐비엇**: 우리 265W 단일샘플(artifact 의심, 미재현)·N=1.3이 78 정확커버(선형 가정)·rough demand ~2배(미측정 예상치)·circularity(정책 재적응 미반영). Duke는 스프링 아님 = **정정**(검색 1차 요약이 오도). 최종 N 확정은 rough+DR ankle 링크비 sweep 필요.
