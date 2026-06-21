# 37 — 발목 링크 설계 vs 시뮬 충실도 (ankle_roll 직결 / ankle_pitch 1:1 링크)

> 사용자 설계(2026-06-22): **ankle_roll = 직결, ankle_pitch = 1:1 비율 링크구조**(원격 모터 + 푸시로드/4절). 질문: 현 sim 파일이 feasible한가, 이 점이 반영됐나. MJCF `assets/biped_lower_body_mjcf/robot.xml` + yaml 확인. 관련: [[36_all_actuator_tn_envelopes]] · [[project-pygmalion-locomotion]].

## MJCF 실제 구조 (검증, 왼다리)
```
shin_link(2.82kg) → [ankle_pitch joint] → ankle_pitch_link(0.11kg) → [ankle_roll joint] → foot_link(0.97kg) → toe(0.13kg)
  ankle_pitch: axis X, range −50°~+40°(90°), actuatorfrcrange ±60, class rs03
  ankle_roll : axis Y, range ±20°,           actuatorfrcrange ±14, class rs00  (foot_link에 위치 = distal)
```
yaml 주석: ankle_pitch_rs03 = "RS03 **DIRECT** motor on the joint axis (**NOT a rod/linkage**)" — 즉 **운동학은 직결 hinge로 모델링**.

## 판정: 1차근사로 feasible, 단 링크는 *명시* 모델링 안 됨 (부분 반영)

### ✅ 반영된 것
- **ankle_roll 직결**: RS00이 distal joint(foot_link)에, frcrange ±14 = RS00 peak. **정확**.
- **★ ankle_pitch 질량분포가 링크를 *암묵 반영***: `ankle_pitch_link`이 **0.11kg** = RS03(880g)이 **관절에 없음**의 결정적 증거 → 모터가 proximal(shin) 원격배치된 링크설계와 정합. **링크의 핵심 이점 "낮은 distal 관성"이 살아있음**(발끝 가벼움 → swing 관성·착지충격↓). foot 0.97kg ≈ RS00 0.31 + 발판 0.66 (RS03 없음).
- **1:1 → 토크/속도 한계 = 직결과 동일**: frcrange ±60 = RS03 peak. 1:1에서 joint측=motor측 → **액추에이터 사이징 그대로 유효**.

### ❌ 반영 안 된 것 (1:1 링크가 만드는 gap)
1. **가변 전달비**: 실제 4절/푸시로드는 중립자세서만 정확히 1:1, ROM 끝(−50°/+40°)서 유효비 ±10~20% 변동. sim = 상수 1:1. 90° ROM은 커서 편차 큼 가능.
2. **ROM 실현성**: sim hinge는 90°를 자유롭게 가나 실제 링크는 자체 ROM·특이점 보유. **이 범위를 링크가 실제로 내는지 기하 확인 필수**(못 내면 sim 보행이 HW서 infeasible). 참고: 인간 발목 ~70°(저측 50+배측 20)인데 sim 90°는 넉넉.
3. **★ 링크 구조하중 (HW설계 목표상 최중요)**: sim은 **joint 토크**만 측정. 링크는 이를 **로드 힘 = joint토크/레버암**으로 전달 + bell-crank 피벗 반력. **로드/벨크랭크/베어링 사이징엔 레버암 기하 필요 → sim엔 없음**. RS03 모터는 사이징되나 **링크 부재 자체는 직접 측정 안 됨**.
4. **컴플라이언스/백래시**: 푸시로드 축변형 + 조인트 백래시(발 진동과 연관 가능) — sim은 강체.
5. **CAD 확인 1건**: 0.11kg로 "관절엔 모터 없음" 확정했으나, RS03 880g이 shin(2.82kg)에 *정확히* 들어갔는지는 MJCF만으론 분해 불가 → Fusion CAD 확인(누락 시 shin 관성·총질량 과소). 단 총 leg질량(12.86kg/leg ≈ 모터6×6.3 + 구조6.5)은 정합.

## 권고
- **하중측정 보정**: ankle_pitch joint토크(≤60)를 후처리로 **÷레버암 → 로드 힘**으로 변환해 링크 부재 사이징. (레버암 길이만 주어지면 measure에 컬럼 추가 가능.)
- **ROM 검증**: 링크가 sim −50°/+40°를 실제로 내는지 확인, 아니면 sim ROM을 링크 가용범위로 제한해 재학습.
- **충실도 업그레이드(선택)**: 각도의존 gain(가변비) 또는 실제 4절을 MJCF equality constraint로 모델링. 단 1:1이면 상수비 근사가 1차 사이징엔 보통 충분.

**한 줄**: 1:1이라 **토크/속도 한계 + 가벼운 발끝(distal 관성) = 옳게 반영**. **링크의 가변비·ROM·로드 구조하중·컴플라이언스 = 모델 밖**. 모터 사이징엔 충분, **링크 부재 사이징엔 레버암 기하 추가 필요**.

## 그 gap이 큰 영향인가? + 질량/관성 조정으로 feasible 가능한가? (사용자 06-22)

### Q1. 영향이 큰가 → ★ 아니다 (하중측정 목표엔 작다)
**1:1은 직결 근사가 *가장 잘 맞는* 경우** — 비=1이라 토크/속도 스케일이 없고, 질량/관성 *배치*만 중요. 지배 물리는 전부 잡힘: 질량분포(distal 관성) ✅·토크/속도 한계 ✅(=모터값)·joint 토크 ✅(=링크 전달 토크). 잔차의 *크기*:
| 미반영분 | 크기 | 영향 |
|---|---|---|
| 가변 전달비 | ROM 끝서 ±10~15%(잘 설계된 1:1) | 모터 사이징 마진 내 → **중-저** |
| 링크 자체 관성(로드+벨크랭크) | joint 반영관성 +10~30% | armature 상향으로 흡수 → **작음** |
| 로드 구조하중 | joint토크가 틀린 게 아니라 ÷레버암 후처리만 필요 | **0**(별도 계산) |
| 컴플라이언스/백래시 | 고주파·진동만, gross 하중 아님 | **저** |
→ **하중측정·모터사이징엔 영향 작음**(잔차 ±15% = 마진 내). 단 링크 *부재* 사이징엔 레버암 필요.

### Q2. 질량/관성 조정으로 feasible? → ★ 대체로 가능 (풀 4절 모델링 불필요)
1:1 링크는 다음 조정으로 직결 hinge가 충실한 proxy가 됨:
1. **모터 질량 proximal 배치 — 이미 됨**(ankle_pitch_link 0.11kg).
2. **ankle_pitch armature에 링크 반영관성 추가** — 모터 rotor(1:1 반영) + 로드/벨크랭크 반영분. (현 0.0049 = 모터 추정만 → 링크분 +α 상향.)
3. **joint ROM을 링크 가용범위로 제한**(아래 Agibot X2 ROM 참조).
4. **joint토크 ÷레버암 후처리**로 로드 힘 측정.
→ 질량/관성 튜닝 + ROM 제한 + 레버암 후처리로 **1차 사이징 충실도 확보**. *못* 고치는 것: 가변비(각도의존 gain 필요) — 단 ±15%라 보통 불필요.

### Agibot X2 대조 (사용자: "X2와 똑같은 설계") — ✅ 연구 완료 2026-06-21

**결론: 사용자 설계는 Agibot 아키텍처와 정합. roll직결/pitch-원격링크 = X2-N 논문이 명시적으로 채택한 방식.** 단 X2 자체는 기하/ROM/질량 수치 **미공개** → 대부분 X2-N(논문)·X1(오픈소스)에서 *유추*.

#### "어느 X2인가" 명확화
- **灵犀(Lingxi) X2** = 智元/Agibot가 2025-03 발표한 1.3m 휴머노이드(데스크용). 표준 X2 = **28 DOF, 33.8kg, ~1.3m**. 변형: X2/X2 Pro=25 DOF, X2 Ultra=31 DOF(팔·허리 +2씩). 양산 진행(2025말 5000대). 다리 6 DOF/leg.
- **X2-N** = X2 기반 **바퀴-다리 변형형**(arxiv 2604.21541, HKUST+Agibot X-lab, 2026-04). 28kg, 1.1m, foot-leg모드 21 DOF. **다리 = 표준 휴머노이드 6 DOF/leg(3-hip, 1-knee, 2-ankle)** → 발목 메커니즘은 X2 계열 대표. ★ 본 노트의 발목 actuation 근거는 주로 이 논문.

#### (1) 발목 actuation — ★ 사용자 주장 **확증**
> X2-N 논문 III: *"the knee and **ankle pitch actuators are relocated closer to the CoM** for reducing limb inertia. We further design **four-bar linkage mechanisms within the limbs** for power and torque transmission of these joints."*
- = **ankle_pitch = 원격모터(근위, CoM쪽) + 4절링크** ⟺ 사용자 "원격모터+푸시로드/4절" **정확히 일치**.
- **ankle_roll**: 논문은 *"position control of **ankle roll actuator** to rigidly lock the wheel mount"* — roll 액추에이터가 발목/발 근처에 위치(직접 그 joint 구동). ⟺ 사용자 "roll 직결" 정합(단 X2-N에선 roll이 wheel-lock 겸용 = N 변형 특수).
- **표준 X2 공식**: *"전신 28 DOF에 **병렬구조(并联)를 하나도 안 씀** → 전달계 완전 디커플(完全解耦)"*. ★ **모순 아님**: 4절/푸시로드(1모터→1 DOF)는 *직렬(serial, 디커플)* 링크. Agibot이 "병렬 없음"이라 할 때의 *병렬*은 2모터가 2 발목 DOF를 *연성구동*하는 방식(Unitree/Tesla식)을 뜻함. 사용자의 "1:1 링크"(roll·pitch 독립) = 정확히 이 **직렬-디커플 링크** → **사용자 주장과 일관**.

#### (2) ROM — X2 미공개, 인체/X1 참고
- X2·X2-N 모두 발목 pitch/roll **각도 미공개**. 우리 sim pitch −50°/+40°(90°)·roll ±20°는 인체(저측50+배측20=70°pitch, 내외번~±20° roll)와 정합 → **타당하나 X2 수치 대조 불가**. 링크 자체 ROM 기하검증은 여전히 필요(노트 본문 ❌-2).

#### (3) 모터 모델 (X2-N Table I, **QDD 유성기어**, ★ 핵심 수치)
| Actuator | Mass(g) | Gear ratio | Peak torque(Nm) | Peak speed(rpm) |
|---|---|---|---|---|
| R90 | 990 | 16:1 | 120 | 105 |
| R57 | 370 | 40:1 | 30 | 110 |
| R52 | 360 | 36:1 | 20 | 130 |
| R52-U | 410 | 72:1 | 40 | 65 |
> *"quasi-direct-drive designs with planetary gear reductions … high backdrivability … near-linear current→torque."* (토크센서리스)
- 우리 RS00(roll, 14Nm)·RS03(pitch, 60Nm)와 직접 일치 모델명은 없음(우리는 RobStride 命名). 단 **계열 = QDD 유성기어**로 동일 사상. 우리 pitch 60Nm은 X2-N R90(120)·R57(30) 사이 → 1.3m급 발목 pitch로 타당범위.

#### (4) 질량 — X2 미공개, **X1 오픈소스 URDF가 ★결정적 secondary 증거**
X1 train repo `resources/robots/x1/urdf/x1.urdf`(실측):
```
hip_pitch 1.67 · hip_roll 0.29 · hip_yaw 2.74 · knee_pitch 1.51(shin)
ankle_pitch 0.062kg  ← ★ 관절엔 모터 없음! (우리 0.11kg과 동일 사상: bare bracket)
ankle_roll 0.59kg(=발)
toe_a/b 푸시로드 체인: link 0.031 + ball 0.057 + loop 0.006 (×2)
```
- ★ X1도 **ankle_pitch 링크 0.062kg = 모터 부재 증거** → 우리 0.11kg 모델링과 **동형**.
- ★ X1 URDF에 `toe_a_*`/`toe_b_*`의 `link→ball→loop` 체인 = **푸시로드(closed-loop 끝단)** = 발목을 shin(knee_pitch)에서 원격구동하는 **링크 하드웨어가 오픈소스에 실재**. (동일패턴이 waist·wrist에도: `motor_a/b→ball→loop`.) → Agibot이 전신에 원격모터+푸시로드 링크 쓰는 직접 증거.
- ⚠ 단 X1 **오픈소스 sim 모델(`xyber_x1_serial.xml` MJCF)은 링크를 직결 hinge로 추상화**(equality/connect 미정의, ankle motor ctrlrange ±18Nm). → **Agibot 자신도 sim에선 우리와 똑같이 "링크→직결 hinge 근사"**를 씀. **우리 모델링 선택을 강하게 정당화.**

#### (5) 링크 기하 (레버암/로드 길이/전달비) — X2 미공개
- X2 4절의 레버암·로드길이·bell-crank 수치 **어디에도 공개 안 됨**. X1 URDF에서 푸시로드 기하 *일부* 추출 가능(예: toe_a loop offset y=−0.195m, toe_b y=−0.140m, ball joint 위치) — 단 이는 *toe* 보조링크라 ankle_pitch 주링크 레버암과 직결 아님. **정확한 레버암은 X1 CAD/메시 측정 필요**(URDF만으론 부분).
- **전달비 "1:1" 직접 확증 자료 없음**: X2/X2-N 모두 발목 4절 전달비 미공개. 4절은 본질상 *각도의존(가변)*이라 "정확히 1:1 상수"는 *중립자세 근사*로만 성립 — 노트 본문 ❌-1과 일치. **사용자의 "1:1"은 설계 의도(중립부근)로 해석, HW상수비 아님.**

#### 종합 판정
- **roll직결 / pitch 원격-4절링크** = Agibot(X2-N 논문 + X1 오픈소스 하드웨어)가 **실제 채택** → 사용자 설계 **feasible·정합** (high confidence on *architecture*).
- **"X2와 똑같다"** = 아키텍처 레벨 ✅. 단 정확한 레버암/로드길이/전달비/ROM/발목 질량 *수치*는 X2 미공개 → 우리 sim 값은 X1/인체/X2-N에서 *유추*된 것이지 X2 datasheet 매칭 아님 (numbers: low-medium confidence).
- **레버암 후처리값**: X2 공개수치 없음 → 정확 레버암 미확보. 차선책: X1 메시(STL) 측정 또는 우리 Fusion CAD에서 ankle_pitch 벨크랭크 레버암 직접 측정 후 joint토크÷레버암.

#### 근거 URL
- X2-N 논문(발목 4절·근위재배치·액추에이터표): https://arxiv.org/html/2604.21541v1
- X1 오픈소스 train(URDF/MJCF, 질량·푸시로드체인): https://github.com/AgibotTech/agibot_x1_train  (`resources/robots/x1/urdf/x1.urdf`, `.../mjcf/robot/xyber_x1/xyber_x1_serial.xml`)
- X1 오픈소스 하드웨어: https://github.com/AgibotTech/agibot_x1_hardware
- 灵犀X2 공식(병렬구조 미사용·완전해耦·28DOF·Power Flow): https://www.zhiyuan-robot.com/products/X2 · https://ai-bot.cn/products-x2/
- X2 스펙(33.8kg/1.3m/28DOF, 변형별 DOF): https://www.pconline.com.cn/zhizao/1898/18985432.html · https://aixzd.com/robot/x2

#### ★ 보강 리서치 2026-06-21 (재확증 + X1 teardown 신규증거)

재조사 결과 위 결론 **재확증**. 신규/보강 증거:

1. **X1 BOM 확정** (오픈소스 GitHub + 다수 출처): 전신 29관절 = **R86-2×9, R86-3×6, R52×10, L28×4** + 그리퍼2. → **L28 = 자체개발 추杆(push-rod 선형 액추에이터), 4개**. "4종 액추에이터, 3종 자체모터 + 1종 자체추杆." L28 스펙: 고속·대추력 범용 추杆, CANFD/4pin-USB, **무게 ~200g**. → 4개 L28 = 양 발목 + 추가위치(toe/보조). **발목이 추杆(선형링크) 구동임을 BOM 레벨에서 확증.**

2. **X1 구조 teardown (지후 "灵犀X1 结构简析")** — 발목 직접기술:
   - *"经典的6自由度腿，**踝关节由拉杆驱动的结构**"* (고전 6-DOF 다리, **발목은 拉杆[당김봉/링크]구동**).
   - *"**踝关节复用的腰部的万向节**"* (발목이 허리의 **万向节[유니버설/카르단 조인트] 재사용**).
   - 허리 메커니즘: *"基于一个万向节 … 万向节上방两电机同步旋转→前后弯腰; 差动→左右弯腰"* (万向节 위 2모터: 동기회전→pitch, 차동→roll).
   - 다리 치수: 허벅지 226mm, 정강이(shank) **304.94mm**. 모터는 **shank에 탑재**(발목 관절 아님) — 우리 sim의 distal-경량(ankle_pitch_link 0.11kg) 설계와 동형.
   - ★ **뉘앙스(우리 sim과의 차이)**: X1 teardown은 발목 **양 DOF 모두 拉杆+万向节 차동**으로 기술(2-rod differential). 우리 sim·사용자 설계 = **roll 직결 + pitch만 1:1 링크**(비대칭). X2-N 논문은 후자(roll 액추에이터 별도 + pitch만 4절)를 명시 → 사용자 설계는 **X2-N 논문**과 더 정합, **X1 teardown의 차동발목**과는 상이. (세대/모델차로 추정: X1 차동 만향절 ↔ X2 디커플 직렬. 아래 "병렬 미사용" 마케팅과도 일관 — X2가 X1의 차동을 디커플로 개선.)

3. **X2 "병렬구조 미사용" 재확인** (다수 출처): *"全身28 DOF, **未使用任何并联结构**"* — 4절/추杆(1모터→1 DOF, 직렬)는 이 진술과 **모순 아님**(병렬=2모터 연성구동 의미). 노트 본문 (1)절 판정 유지.

**한 줄 보강**: 오늘 재조사로 (a) X1 BOM의 L28 추杆×4 = 발목 선형링크 BOM 확증, (b) X1 teardown = 발목 拉杆+만향절·모터 shank탑재 확증, (c) X2 "병렬 미사용" 재확인. **단 X1은 발목 양축 차동(2-rod), 사용자/우리 sim은 roll직결+pitch단일링크 → X2-N 논문과 정합·X1 teardown과 상이**(모델/세대차).

신규 출처: X1 teardown https://zhuanlan.zhihu.com/p/1895593089554436375 · L28 추杆 https://www.zhiyuan-robot.com/DOCS/PM/PFL28 · X1 하드웨어 BOM/STEP https://github.com/AgibotTech/agibot_x1_hardware · X2 상세 https://zhuanlan.zhihu.com/p/1909304508170875310

관련: [[36_all_actuator_tn_envelopes]] · [[30_knee_biomechanics]] · [[17_toe_usage_vibration]] · [[31_humanoid_hw_comparison]]
