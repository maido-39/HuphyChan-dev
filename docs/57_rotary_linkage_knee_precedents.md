# 57 · 로터리 액추에이터 + 링키지 무릎 — 실 사례 조사

> 2026-07-08. 무릎 공간 부족 → RS04(로터리 QDD)를 허벅지에 두고 **링크로 무릎 구동** 검토([[55_init_pose_straight_vs_bent]] knee 부하, 벨트 vs 크랭크 논의의 후속). "이런 로터리+링키지 무릎 선례가 있나?" 병렬 리서치(Fable5). 리니어+링크(Optimus/Kangaroo/LOLA)·직결(Unitree)·벨트(MIT)와 **명확 구분**. 신뢰도 ★★★=논문/특허, ★★=티어다운.

## 1. 확인된 로터리+링키지 무릎 (★★★)
| 로봇 | 링키지 타입 | 모터 위치 | 비고 |
|---|---|---|---|
| **Cassie / Digit** (Agility/OSU) | **가변비 4절** (+로프감속 전단) | 허벅지 | ★우리 최근접·**상용**. 비 **0.3→1.1 가변**(토크수요 큰 각도서 큰 비). 특허 [US10144464](https://patents.google.com/patent/US10144464) |
| **ATRIAS** (Oregon State) | 4절 (무릎=수동정점), fiberglass 스프링 | hip | 로터리 SEA 50:1 하모닉+스프링→4절. [Hubicki IJRR](https://mime.engineering.oregonstate.edu/research/drl/_documents/hubicki_2016.pdf) |
| **Tello Leg** (UIUC, Ramos) | 스퍼차동 + hamstring 평행기구 + 4절(정강이) | hip 위 | 2모터 협동구동(점프당 절반토크), 비선형 5차다항 근사. [arXiv:2203.00644](https://arxiv.org/pdf/2203.00644) |
| **Mithra** (MDPI 2025) | **개방형 4절(거의 평행사변형)** | 허벅지 중앙 | ★"cable-pulley보다 **강성·정비성** 우수해 링키지 선택" 명시. [MDPI Robotics 14(3):28](https://www.mdpi.com/2218-6581/14/3/28) |
| **DecARt Leg** (2025) | 수동기어 + 4절 평행 | 다리뿌리 | hip장착 knee가 무릎직결보다 우수(메트릭). [arXiv:2511.10021](https://arxiv.org/html/2511.10021v1) |
| **Salto-1P** (Berkeley) | **8절, 강가변MA** | — | 모터한계 **3.6× 파워**(가변MA로 SEA 에너지변조). [Haldane IROS2016](https://www.researchgate.net/publication/311753849_A_power_modulating_leg_mechanism_for_monopedal_hopping) |
| Ghost Minitaur / Baleka | 5절(대칭) | hip | 직결로터리+5바(4족/이족). [Kenneally RA-L2016](https://www.researchgate.net/publication/294104797_Design_Principles_for_a_Family_of_Direct-Drive_Legged_Robots) |

설계연구 논문: [가변감속비 교차 4절 다리](https://www.researchgate.net/publication/338938001), [Rod-and-Lever 휴머노이드](https://www.researchgate.net/publication/313497042), [가변출력토크 무릎(Springer)](https://link.springer.com/chapter/10.1007/978-3-031-67383-2_18).

## 2. 제외군 (구분 명확화)
- **리니어 액추에이터+링크**(로터리 아님): PAL Kangaroo(리니어+serial-parallel), LOLA/Johnnie(볼스크류), Kepler(롤러스크류), Tesla Optimus, IHMC Nadia.
- **벨트**(링키지 아님): **MIT Humanoid 무릎=벨트**(논문 [arXiv:2104.09025](https://arxiv.org/pdf/2104.09025) 직접확인: *"The knee, ankle and elbow joints contain a belt gearing system"*), Mini Cheetah.
- **직결**(무릎축): Unitree G1/H1, Booster T1.

## 3. 시사점 (우리 설계 검증)
1. **Cassie/Digit = 우리가 제안한 것의 상용 선례**: 로터리 모터 허벅지 + **가변비 4절**, 비를 토크수요 큰 각도서 크게(0.3→1.1). = 우리 "MA(θ)를 −43° peak에 매칭"([[55...]] knee 수요 플롯)과 동일 사고. **상용 검증됨**.
2. **채택 이유가 우리 논리와 일치**: (a) 모터 근위→다리관성↓, (b) 4절 가변비가 토크-속도 매칭(벨트·직결 불가). Mithra는 **케이블-풀리 대신 링키지**를 강성·정비성으로 명시 선택 = 우리가 벨트→링키지 기운 이유와 동일.
3. **지형**: 직결(Unitree)·리니어스크류+레버(Optimus/Kepler)가 다수, **로터리+링키지는 소수파지만 Cassie/Digit 상용 + 연구계(ATRIAS/Tello/Mithra/Salto)로 확실히 검증**. "다리관성↓ + 가변MA"가 목표일 때의 정통 선택.
4. **적용**: 우리 4절 무릎은 Cassie식 가변비 4절을 참고 — MA(θ) peak를 우리 수요각(−43° 공칭)에 두고, 데드포인트를 저수요 끝단(신전쪽)에. ROM은 4절로 ~120–140° 목표.

## 참고문헌
★★★: [Cassie 특허 US10144464](https://patents.google.com/patent/US10144464) · [Grizzle Cassie 제어](https://grizzle.robotics.umich.edu/files/Feedback_Control_of_a_Cassie_Bipedal_Robot__Standing_and_Walking_Final.pdf) · [ATRIAS Hubicki](https://mime.engineering.oregonstate.edu/research/drl/_documents/hubicki_2016.pdf) · [Tello arXiv:2203.00644](https://arxiv.org/pdf/2203.00644) · [Mithra MDPI](https://www.mdpi.com/2218-6581/14/3/28) · [DecARt 2511.10021](https://arxiv.org/html/2511.10021v1) · [Salto IROS2016](https://www.researchgate.net/publication/311753849_A_power_modulating_leg_mechanism_for_monopedal_hopping) · [MIT Humanoid 2104.09025](https://arxiv.org/pdf/2104.09025)
서베이: Tello(근위작동 메트릭 CII) · DecARt(2025 상용분류) · [휴머노이드 역학 리뷰(Adv.Robotics 2020)](https://www.tandfonline.com/doi/full/10.1080/01691864.2020.1813624) — *"크랭크 기구를 무릎에 적용하면 액추에이터·감속기를 허벅지에 배치해 다리관성 저감"*.

## 원시 인용
- Cassie 특허: link 길이 설계로 *"the ratio of the angular velocity of the output link to the angular velocity of the input link varies (for example from approximately 0.3 to 1.1) depending on the angle of the output link"* → *"large ratios of knee joint torques to knee motor torques at certain characteristic knee joint angles where large knee torques are generally required."*
- Mithra: *"linkages are used to connect the off-axis actuators to the joints to provide sufficient stiffness and simplicity of maintenance compared to cable-pulley systems."*
- MIT Humanoid: *"The knee, ankle and elbow joints contain a belt gearing system to deliver higher torques at these joints."*
