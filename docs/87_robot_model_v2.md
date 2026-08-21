# 87. Pygmalion v2 로봇 모델 — 최종 CAD에서 URDF·MJCF 재구축 (2026-08-20)

목표([[83_fusion360_measurement_spec]] 후속): 최종 CAD에서 조인트·질량(모터/나사/베어링)을 정확히
걸어 **URDF + mjlab 로봇 파일 + 충돌 메시**를 만들고, 전 관절 구동·관성을 검증해 보행 RL에 쓸 수
있게 한다. 발목은 **roll/pitch 직렬**.

![zero pose](img/robot_v2_zero_pose.png)
![sweeps](img/robot_v2_joint_sweeps.png)

> 위: 직립 자세(좌 측면 x–z, 우 정면 y–z), MJCF가 실제로 읽는 메시를 MuJoCo 바디 자세로 투영.
> 아래: 관절별 ROM 최소/중간/최대 스윕(왼다리). 이 호스트는 GL이 없어 자체 투영 렌더다.

## §1 결과물

| 파일 | 내용 |
|---|---|
| `pygmalion_locomotion/assets/pygmalion_v2/pygmalion_v2.urdf` | 13관절(free + 12) URDF, 메시·관성 포함 |
| `mujoco-sim/mjlab/.../xmls/pygmalion_v2.xml` | mjlab 로봇 파일 (기존 `pygmalion.xml`과 같은 클래스·이름 규약) |
| `pygmalion_locomotion/assets/pygmalion_v2/meshes/*.stl` | 시각 메시(바디별, 링크 프레임, m) + `*_hull.stl` 충돌 볼록껍질 + `R_*` 미러. 47 MB, git 제외 — STEP에서 결정적으로 재생성 |
| `~/pyg_fea/steps/robot_massprops_step.json` | 강체별 질량·COM·관성텐서(CAD 전역 mm) + 모터 축 |
| `pygmalion_locomotion/assets/pygmalion_v2/validation.json` | 검증 수치(직립 높이 등) — mjlab 키프레임이 이 파일을 읽음 |

사용: `PYG_V2=1` 로 mjlab 전 태스크가 v2 모델을 쓴다(`pygmalion_constants.py` 토글, 기존 cant/rolloff
토글과 같은 패턴). 액추에이터·관절명·발 사이트·충돌 geom 이름(`L_foot2..6_collision`)은 기존과 동일해
task 설정을 손대지 않는다.

## §2 어떻게 만들었나 (`tools/robot_model/`)

1. **질량속성 — `massprops_step.py`**: 링크별 STEP의 모든 솔리드를 OCC 체적적분으로 질량·COM·**풀 관성텐서**
   (6061 2.70). 나사·베어링은 인벤토리 체적×7.85의 점질량. 모터 7개는 자리표시자 형상 + **카탈로그 질량**
   (RS04 1.42, RS03 0.88 — CAD 질량은 자리표시자, docs/83 §1). 모터 회전축은 솔리드의 최대 원통면에서
   **실측**. 체적은 인벤토리와 0.5 % 이내 일치(assert), 텐서는 양정·삼각부등식(assert).
2. **강체 귀속**: 골반 = CenterParts + Waist_Yaw RS04 + 힙피치 스테이터; 힙피치링크 = HipPitch2Roll + 힙롤
   RS04; 힙롤링크 = PipRoll2Yaw + 힙요 RS03; 대퇴 = HipYaw2Knee; **정강이 = Knee2Ankle + 무릎 RS04 + 발목
   RS03×2 + 클레비스 포크 + 크랭크 + 로드/2**; 발목피치링크 = 십자; 발 = 발판 + 로드/2. 베어링은 잇는
   두 바디에 반씩. ([[81_rl_model_vs_cad_mass]] v4의 기하 분해와 동일)
3. **관절 프레임**: 힙 3축이 **(−123.7, 70, 60)에서 교차**(모터 원통축 실측 — 구 MJCF의 힙롤 15° 캔트는
   현 CAD에 없다). 무릎 (y115, z−310), 발목 (y145, z−800). CAD→sim = z축 +90° (sim = (−y, x, z)):
   전방 +x, 왼다리 −y — 기존 모델 규약. 축 부호도 기존과 동일(hip_pitch +y, hip_roll +x, hip_yaw −z,
   knee −y, ankle_pitch −y, ankle_roll −x)이라 정책·보상·키프레임 의미가 유지된다.
4. **메시 — `meshes_step.py`**: gmsh(OCC)로 솔리드별 표면 메시(8 mm) → 바디별 병합 → 링크 프레임 변환 →
   STL; 충돌 = 구조 솔리드 볼록껍질. 모터 자리표시자는 gmsh가 솔리드당 수 분을 쓰길래 메시하지 않고
   **실측 축·반경·길이의 해석 원통**으로 그린다(`build_robot.py`).
5. **빌드 — `build_robot.py`**: 같은 JSON에서 URDF와 MJCF를 동시에 생성(일관성 보장), MuJoCo 컴파일 검사.
   충돌 프리미티브(대퇴·정강이 캡슐, 발 캡슐 5열, 몸통 캡슐)는 기존 규약.

## §3 검증 (`validate_robot.py`)

| 항목 | 결과 | 기준 |
|---|---|---|
| 바디 질량 | MJCF = 질량속성 파일 (1e-3 이내) | |
| 힙→무릎 / 무릎→발목 | **0.370 / 0.490 m** | CAD 370 / 490 ✓ |
| 힙→밑창 | 0.903 m → 직립 base 높이 **0.903** | 구 모델 0.87 |
| 스탠스 폭 | 0.2474 m | CAD 2×123.7 ✓ |
| 관절 스윕 자기충돌 | hip_roll 내전 ≥13°에서만 L/R 정강이 접촉(다른 다리 직립 시) — 기하학적 사실 | 나머지 5관절 0 |
| **관성 실측(MuJoCo 질량행렬)** | 힙피치 축 **2.262 kg·m²**, 무릎 축 **0.454** | STEP 점질량 추정 2.214 / 0.437 (+2 %, 솔리드 자체 관성분) ✓ |
| 총질량 | **41.42 kg** | 표 교정값 44.51(배터리 제외) — 차이는 상체 자리표시자·누락 나사 |

## §4 자리표시자 — Fusion이 붙으면 교체할 것

1. **상체 15.34 kg 집중질량**(Torso+Neck+팔×2, docs/82 교정표). COM·관성은 구 base_link 스케일링.
   → Fusion §2 상체 질량속성 또는 §7 재-export.
2. **모터 질량 = 카탈로그**(케이블·브래킷 제외). → Fusion 실측.
3. 이 STEP(8/14)에는 **나사 141개가 없다**(docs/82 §6) — 질량 ~0.35 kg 차이.
4. 발목 roll 캡은 sim ±20 유지(`PYG_ANKLE_ROLL15` 토글 그대로). pitch 캡 +40(설계 +30 미결).

## §5 2-RSU 폐루프(AB 모터 링크)는 다음 단계

MuJoCo는 `equality/connect`로 로드 양끝 볼조인트를 닫을 수 있어 mjlab에서 모델링 가능하다. v2는
직렬 발목이고 로드는 정강이에 시각용으로만 붙어 있다. 폐루프 버전은 학습 안정성과 별개 검증이 필요해
**v2.1로 분리**한다.

## §6 환경 제약 (이 호스트)

- **GPU 드라이버 미로드**(`nvidia-smi` 통신 실패, `/dev/nvidia*` 없음) → RL 학습 불가. CPU로 mjlab
  태스크 환경 스모크(2 env, 100 step)만 수행. 학습은 드라이버 복구 후 `scripts/run_training.sh`.
- **Fusion MCP(27182)**: 이 리눅스 호스트·LAN에 리스너 없음 — Windows PC의 `ssh -L`은 그쪽 로컬용.
  이 호스트에서 쓰려면 PC에서 `ssh -R 27182:127.0.0.1:27182 syaro@192.168.20.177` 역터널.
  클라이언트는 준비됨(`tools/fusion/mcp_client.py list`).

관련: [[81_rl_model_vs_cad_mass]] · [[82_final_design_mass_review]] · [[83_fusion360_measurement_spec]]
