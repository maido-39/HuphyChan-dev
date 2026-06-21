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

관련: [[36_all_actuator_tn_envelopes]] · [[30_knee_biomechanics]] · [[17_toe_usage_vibration]]
