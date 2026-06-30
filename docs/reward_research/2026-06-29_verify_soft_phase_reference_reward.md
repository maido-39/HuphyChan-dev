# 2026-06-29 · 검증(adversarial) — "soft phase reference reward" (클럭 없는 normative 관절커브 추종)

> CLAIM(methods): 하드 위상클럭 없이 문헌 normative 관절커브(Perry&Burnfield)에 L1/L2 error reward를 주되, 정책이
> 스스로 위상타이밍을 찾게 두는 "중간지대". 위상추정기 불필요, 속도변화에 강건, 구현 쉬움. 단점: 형태(morphology)
> 불일치, 어느 관절을 얼마나 페널티할지 수동튜닝, 접촉제약 없으면 hard-landing 잔존.
> SOURCE: methods | REFS: Perry & Burnfield 3rd ed. (2010); docs/22, docs/11.

## 한 줄 판정
**supported = TRUE, 단 caveat 큼.** 구현은 우리 스택에서 100% 실현가능하고 이미 유사항이 가동 중. 그러나 **claim의
핵심 주장("클럭 없이 *전체 위상-인덱스 커브*를 L1/L2 추종"="중간지대")은 문헌상 부정확/오도**다. 클럭 없는 순수 L2-to-curve는
**mode-collapse(평균자세로 수렴)** 위험이 있고, 문헌의 진짜 "위상 없는 imitation"은 **AMP(판별자/분포매칭)**이지
L2추종이 아니다. **올바른 형태는 (a) range/band 소프트제약 또는 (b) contact-proxy 위상**이며, 둘 다 우리가 이미 구현.

## 검증 단계별

### 1. 실현가능성(rsl_rl 2.3.3 / IsaacLab 2.2) — ★ 반증 실패(=가능)
- 설치 확인: `rsl_rl_lib-2.3.3.dist-info`, `IsaacLab VERSION=2.2.0`(isaaclab 0.44.9). 
- reward 항은 순수 `f(env,...)->Tensor[num_envs]` 함수. `env.scene[cfg.name].data.joint_pos[:, joint_ids]`로 관절각,
  `env.episode_length_buf`(+1/step, reset 0)·`env.step_dt`(=0.02s)로 에피소드 시간 접근 — **IsaacLab 수정 불필요**
  (`manager_based_rl_env.py:79,201` 확인).
- ★ 결정적: 우리 `rewards.py`에 **이미** `cop_progression`(contact-time를 "clock-proxy"로 위상 정규화),
  `joint_deviation_l1`(=관절각 L1-to-target, IsaacLab 내장, cfg에서 hip에 가동중)이 운용 중. claim이 말하는 구현은
  구조적으로 **이미 프로덕션에서 도는 패턴**. `docs/reward_research/2026-06-28_next_levers_clock_symmetry.md`에서
  병렬연구가 `gait_phase_contact`+`gait_clock`이 설치버전서 완전지원됨을 32-tool 검증함.
- → "infeasible / IsaacLab 수정 필요" 반증 **실패**. 가능.

### 2. 방법론 정확성 — ★ 부분 반증 성공(claim의 "중간지대" 프레이밍이 오도)
- 문헌 분류는 이분법이 분명함:
  - **feature/tracking imitation(DeepMimic류)**: 위상변수로 시간정렬 후 관절각 등 L2 비교. "phase variable serves as a
    learned proxy for temporal progress … reward computed … synchronized via the phase". 즉 **L2추종은 위상에 의존**.
  - **위상 없는 imitation(AMP/GAN류)**: 판별자가 **짧은 transition window의 분포**를 매칭 → "removes the need for
    phase-based or time-indexed alignment". **L2-to-curve가 아님**.
- claim은 "L2-to-curve + 클럭 없음"을 *중간지대*로 제시하나, 문헌엔 그 정확한 조합의 검증 사례가 약하다. 위험:
  **클럭/위상이 빠진 순수 L2 추종은 mode-collapse**("imitative methods that directly imitate expert trajectories using
  an L2 loss are susceptible to the inherent mode collapse problem"). 위상-인덱스 없이 시변(time-varying) 커브를 L2로 누르면
  정책이 **모든 위상에서 동시에 작은 오차를 내는 평균자세(거의 정적)** 로 수렴할 수 있음 → 우리 목표(보행·toe사용)에 **유해**.
- DeepMimic이 정적붕괴를 피하는 장치는 **위상정렬 + RSI + early-termination**인데, claim은 이걸 다 뺀다. RSI 없는 dynamic
  스킬은 "small backwards hop"으로 붕괴(검증사례). → "클럭 없이도 형태만 맞으면 된다"는 **순진한 형태로는 위험**.

### 3. 올바른 실현형태(=claim을 살리는 방향) — 문헌 지지 있음
- **(a) range/band 소프트제약**: "soft-stop limits / shaping constraints & costs"로 gait 속성을 지정(constrained RL). 위상-인덱스
  전체커브 추종이 아니라 **정상 가동범위 밖만 페널티** → mode-collapse 회피, "어느 관절 얼마나"의 튜닝부담↓. Berkeley
  Science Robotics(2024)는 gait library 대신 **biomechanics-기반 reward**로 사람다운 보행 — claim의 "문헌 normative"의 정당한 형태.
- **(b) contact-proxy 위상**: 우리 `cop_progression`/`gait_phase_contact`처럼 **접촉시간/접촉상태**를 위상프록시로 → 정적붕괴를
  방지하면서 위상추정기 없이 시간정렬. claim의 "클럭 없이"는 사실 이쪽(=암묵적 위상프록시)이라야 작동.
- 우리 자체 자산: **docs/47 (6-DoF gait-cycle, 위상 0-100% normative)** = 우리 로봇 retarget된 위상별 관절하중 보유 →
  claim의 단점①(morphology 불일치)을 **우리 데이터로 회피 가능**(Perry&Burnfield 외부커브에 의존할 필요 적음).

### 4. claim의 단점 항목 검증
- ① morphology 불일치 — **맞음**(다리분절비/팔 다름). 우리는 docs/47 자체 gait-cycle로 완화 가능.
- ② 관절선택·가중 수동튜닝 — **맞음**(L2 imitation의 알려진 약점; AMP가 이걸 판별자로 대체). band/range형이 튜닝부담 낮춤.
- ③ 접촉제약 없으면 hard-landing 잔존 — **맞음**. 우리 `foot_impact_force`(>700N 소프트)·`foot_landing_vel`와 반드시 병행.
  HW 1.5-2.7kN 파손한계 고려시 imitation만으론 GRF 보장 못함 → 임팩트항 유지 필수.

## 우리 목표(human-like·low-impact·min-energy·HW 하중측정) 적합성
- 유익: 위상추정기 없이 사람다움 shaping 가능, 우리 docs/47 자산 재활용, 기존 항들과 가산 호환.
- 유해 가능: **순수 L2-to-curve(클럭X)는 정적/평균자세 붕괴 → 속도추종↓·보행소실**. 반드시 (a) band/range 또는
  (b) contact-proxy 위상 형태로, **임팩트·랜딩속도 항과 병행**, **속도추종 dominant** 유지.

## 권고(빌드 시)
1. claim을 "전체 위상커브 L2 추종(클럭X)" 그대로 쓰지 말 것 → **range/band 소프트제약** 또는 **contact-proxy 위상 추종**으로.
2. normative 소스는 **우리 docs/47 6-DoF gait-cycle 우선**(retarget됨), Perry&Burnfield는 교차검증/누락관절 보강용.
3. `foot_impact_force`+`foot_landing_vel` 병행(hard-landing). 속도추종 weight dominant 유지(mode-collapse 가드).
4. ablation으로 정적붕괴 감시: achieved/cmd>0.85, double-support%·toe-off% (docs/47 지표)로 보행 살아있나 확인.

## 출처
- Feature vs GAN imitation (위상 필요성/AMP 위상프리): https://breadli428.github.io/post/lfd/ · https://arxiv.org/pdf/2507.05906
- DeepMimic(위상변수·RSI·ET): https://arxiv.org/pdf/1804.02717
- AMP(분포매칭, 시간정렬 불요, 에너지효율 CoT): https://arxiv.org/pdf/2104.02180 · https://arxiv.org/pdf/2203.15103
- Berkeley 실세계 휴머노이드(gait library 대신 biomechanics reward): https://www.science.org/doi/10.1126/scirobotics.adi9579
- L2 imitation mode-collapse / constrained-RL soft-limit: 검색요지(위 본문 인용)
- Perry & Burnfield, Gait Analysis 3rd ed.(2010), 위상 0-100% normative 관절각: https://books.google.com/books/about/Gait_Analysis.html?id=86cLEQAAQBAJ
- 우리 스택/구현 근거: `source/.../mdp/rewards.py`(joint_deviation_l1), `source/.../rewards.py`(cop_progression),
  `manager_based_rl_env.py:79,201`(episode_length_buf), docs/47, docs/22, docs/11,
  docs/reward_research/2026-06-28_next_levers_clock_symmetry.md
