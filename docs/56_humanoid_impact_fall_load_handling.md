# 56 · 다른 휴머노이드는 충격/낙하·전복모멘트 하중을 어떻게 다루나 (리서치)

> 2026-07-08. 우리 hip_yaw thigh M_bend = **51 N·m(공칭 평지) / 145 N·m(러프 p99, 스텀블·전도 포함) / 600–1534(극단 낙하 스파이크)** ([[54_hip_yaw_rs03_actuator_loads]]). "이 전복모멘트/충격을 실 휴머노이드는 어떻게 핸들링하나?" 병렬 리서치(Fable5) 2건 종합. 신뢰도 표기: ★★★=1차(논문/특허/데이터시트), ★★=티어다운, ★=벤더블로그.

## 1. 사이징 철학 — **아무도 최악 낙하를 정적 안전율로 기어에 걸지 않는다**
낙하/충격은 **여러 층위**로 분산 처리:
- **낙하 생존은 명시적 HW 요구**(★★★): Boston Dynamics 전기 Atlas — *"하드웨어는 테이블 모서리로 2m 낙하를 견뎌야 한다 — RL의 'bitter lesson' 중 흔한 일"*. + 사지 **수분 내 필드 교체**(무손상 아닌 손상허용+수리 설계). [Humanoids Daily](https://www.humanoidsdaily.com/news/form-as-function-boston-dynamics-details-the-industrial-design-logic-behind-the-production-atlas)
- **과부하 정격은 1.5–5× (단시간)**(★ 벤더가이드): 무릎/hip 모터는 "스쿼트·점프·착지충격(정격의 3–5× 과부하)" 커버, 시스템 1.2–1.5× 마진; 기어박스 "300% 충격 내성". [CubeMars](https://www.cubemars.com/how-to-choose-hip-and-knee-joint-motors-for-humanoids-robots.html), [PlaPivot](https://plapivot.com/blog/blog_humanoid_exoskeleton_actuator)
- **peak:continuous ≈ 2.1–2.4×** (★★★ Berkeley Humanoid actuator 표, [arXiv:2407.21781](https://arxiv.org/abs/2407.21781)): 전기/열 설계로 확보, **기계충격은 재료로 별도 처리**.
- **무제어 낙하 관절토크 ≈ 제어낙하의 4.6×**(★★★ SafeFall): 보호정책이 peak 관절토크 **−78.4%**, 접촉력 −68.3%. [arXiv:2511.18509](https://arxiv.org/abs/2511.18509)
- **유압 Atlas는 낙하를 정상 개발과정으로 취급**, 부품을 설계한계 너머로 밀어씀. [BD blog](https://bostondynamics.com/blog/build-it-break-it-fix-it/)

## 2. 기계적 전략 (충격을 액추에이터에서 흡수/차단)
- **★★★ QDD 백드라이버빌리티(핵심 패러다임)** — 저기어비(6–10:1)면 **반사관성이 N²로 작아** 충격이 기어이빨 대신 로터를 역구동(권선서 소산). MIT Cheetah **IMF(Impact Mitigation Factor)** 지표. Wensing/Kim T-RO 2017 [dspace](https://dspace.mit.edu/handle/1721.1/119863). MIT Humanoid가 그대로 계승: *"토크밀도 높은 모터 + 고대역 힘제어 + 백드라이버빌리티로 착지 고속충격서 기계적 강건성"* [arXiv:2104.09025](https://arxiv.org/abs/2104.09025).
- **★★★ 하모닉드라이브는 충격에 취약** — 고N(50–160:1) → 비역구동 → 얇은 flexspline이 충격토크+N²관성토크로 **균열/피로**. "지면충격 흡수 관절(무릎·발목)은 하모닉보다 충격내성 유성기어가 낫다". 그래서 BD는 **하모닉 안에 슬립클러치 특허**([US10337561B2](https://patents.google.com/patent/US10337561B2/en): Belleville스프링 예압 마찰클러치가 임계토크 초과 시 기어를 일시 디커플→충격 소산, 자동복귀·shim조정). Unitree/Berkeley/MIT는 다리에 **저비 유성/사이클로이드** 채택, 하모닉은 팔/손목만.
- **★★★ SEA(리프스프링)** — Cassie/Digit: 모터-관절 사이 리프스프링이 풋스트라이크 충격 흡수 + 변위로 힘센싱. [DecARt survey](https://arxiv.org/html/2511.10021v1)
- **★★ 롤러스크류/유압** — Optimus 다리 리니어(플래니터리 롤러스크류, 충격을 수십 나사접점 분산), Sanctuary 유압(비취성 컴플라이언트 하중경로).
- **★★★ Unitree G1** — 크로스롤러 1개/관절(CRBT355A 35mm/5mm 초박), 2단 유성, 무릎 90(EDU 120) N·m. 캔틸레버.

## 3. 베어링·마운팅 — **전복모멘트를 어떻게 받나** (우리 문제 직결)
- **★★★ 크로스롤러(CRB)가 표준 출력베어링**: radial+양방향 axial+틸팅모멘트를 1개로. Harmonic Drive SHD 데이터시트 허용 틸팅모멘트 $M_c$: **SHD-14=37, SHD-17=62, SHD-20=93, SHD-25=129, SHD-32=290, SHD-40=424 N·m** ([csd-shd.pdf](https://www.harmonicdrive.net/_hd/content/documents/csd-shd.pdf)). ★핵심: 휴머노이드 사이즈(20/25)서 **허용모멘트가 정격토크와 동차수** → 소형은 **출력베어링 L10수명이 기어보다 먼저 한계**.
- **★★★ 업계는 hip_yaw만 캔틸레버로 둔다 — "보통 모멘트가 작아서"**: MEVITA [arXiv:2508.17684](https://arxiv.org/html/2508.17684) — *"Hip-Y는 일반적으로 토크가 작으므로 double support(양단지지)는 Hip-R·Hip-P·Knee-P·Ankle-P에만 적용하는 게 일반적"*. 다리가 yaw축에 동축으로 매달려 전복모멘트가 원래 작기 때문.
- **★★ 토크-디커플링**(액추에이터는 토크만, 구조가 하중): Optimus(CRB+앵귤러콘택 조합), Agility Cassie/Digit(액추에이터를 골반에 몰고 링키지가 하중경로), IHMC Nadia(리니어+clevis=자연 양단지지), DecARt(모터를 다리 뿌리에).
- **원리**(Shigley): 캔틸레버 반력 $F(1+e/L)$, 스팬 넓히면 $M/L$로 감소. [MachineCalcs](https://machinecalcs.com/guides/what-is-overhung-load)

## 4. 제어 전략
- **★★★ 학습 보호낙하(SafeFall)**: 낙하예측(GRU)+RL 손상완화, 불가피시만 발동. 리워드에 **부품 교체비 기반 취약도 가중** + "actuator 최대정격토크" 페널티 + "기계연결부 과부하 방지 관절반력 페널티(HW스펙서 임계 결정)". → peak토크 −78%.
- **★★★ 착지 흡수 제어**: MIT Humanoid MPC+WBIC, 접촉감지 후 landing controller가 충격 흡수; 플래너 내부서 actuator 한계 강제.
- **★★★ 임피던스 제어**: 접촉 순간 관절 임피던스 낮춰 다리를 스프링-댐퍼로. QDD 힘제어/SEA 변위센싱이 가능케 함.
- **★★ 팔 반사**: Digit은 팔로 낙하 제동·기립.

## 5. 우리 Pygmalion에의 함의 (종합 + 우리 수치 대조)
1. **145 N·m는 SHD-20(93) 초과·SHD-25(129) 한계급** — 우리 러프 p99 전복모멘트는 실제 하모닉 출력 CRB 정격과 **동차수로 이미 빠듯**. 우리 RS03 출력베어링 틸팅정격을 반드시 이 145와 대조([[54_hip_yaw_rs03_actuator_loads]] 케이스 A/B/C).
2. **★우리만 hip_yaw 모멘트가 크다 — 재확인 필요**: 업계는 hip_yaw를 "저모멘트"라 캔틸레버로 두는데, 우리는 51(공칭)/145(러프). 원인 가설: (a) 동적 보행서 GRF가 yaw축서 편심(정적 동축 가정과 다름), (b) 우리 자세/geometry가 hip_yaw를 더 굽힘, (c) thigh 프레임 분해가 상류 hip_pitch/roll 구조가 받을 몫까지 포함. → **실제 마운팅(사용자 CAD)에서 이 모멘트를 yaw 출력베어링이 정말 혼자 받는지** 확인. 혼자면 업계가 hip_pitch/roll/knee에 쓰는 **straddle/토크-디커플링을 hip_yaw에도** 적용 권장.
3. **낙하 스파이크(600–1534)는 정적 사이징 대상 아님** — 업계 정답은: (a) 충격내성 전달계(저비 유성/사이클로이드·SEA·롤러스크류), (b) 1.5–3× 단시간 과부하+3× 기어충격정격, (c) **슬립클러치/기계퓨즈**(BD식)로 tail 처리, (d) **제어로 peak −78%**(SafeFall), (e) 손상허용+수리설계. 우리도 이 층위 스택으로 접근 — 낙하 600 N·m를 정적으로 버티게 하지 말고 클러치/제어로 자르는 게 정석.
4. **RS03(하모닉?) 재고**: 다리 충격관절에 하모닉이면 충격취약. QDD/저비 유성이 충격엔 유리(단 정밀·백래시 트레이드오프). 최소한 슬립클러치/기계퓨즈 검토.

## 참고문헌 (신뢰도순)
★★★: [Wensing T-RO 2017](https://dspace.mit.edu/handle/1721.1/119863) · [MIT Humanoid 2104.09025](https://arxiv.org/abs/2104.09025) · [Berkeley Humanoid 2407.21781](https://arxiv.org/abs/2407.21781) · [SafeFall 2511.18509](https://arxiv.org/abs/2511.18509) · [BD 슬립클러치 US10337561B2](https://patents.google.com/patent/US10337561B2/en) · [HD SHD 카탈로그](https://www.harmonicdrive.net/_hd/content/documents/csd-shd.pdf) · [MEVITA 2508.17684](https://arxiv.org/html/2508.17684) · [BD build-it-break-it](https://bostondynamics.com/blog/build-it-break-it-fix-it/)
★★: [G1 teardown](https://robotopian.com/blogs/news/unitree-g1-humanoid-robot-teardown) · [Optimus 하드웨어분석](https://x.com/seti_park/status/1885522686912455131) · [Cassie hopping](https://arxiv.org/pdf/1807.08037) · [IHMC design](https://robots.ihmc.us/humanoid-design)
★: [CubeMars 사이징가이드](https://www.cubemars.com/how-to-choose-hip-and-knee-joint-motors-for-humanoids-robots.html) · [PlaPivot](https://plapivot.com/blog/blog_humanoid_exoskeleton_actuator) · [firgelli](https://www.firgelli.com/pages/humanoid-robot-actuators)

## 원시 인용 발췌
- Atlas 낙하스펙: *"The hardware must survive a two-meter fall onto the edge of a table—a common occurrence during the 'bitter lesson' of reinforcement learning."*
- MEVITA hip_yaw: *"Since the Hip-Y joint generally experiences less torque, it is common to apply double support only to the Hip-R, Hip-P, Knee-P, and Ankle-P joints."*
- MIT Humanoid: *"...the ability to mitigate impacts through backdrivability... mechanical robustness that enables reliable control throughout the high speed impacts that occur when landing. These same design principles have been used in the design of the MIT Humanoid."*
- BD 슬립클러치: *"the axial preload may keep the clutch pads frictionally coupled to the circular spline until a predetermined torque limit is exceeded"* → 이후 하모닉 디커플·마찰소산.
- SafeFall: 보호정책 peak 관절토크 −78.4%, 접촉력 −68.3% (→ 무제어낙하 ≈ 4.6× 제어낙하).
