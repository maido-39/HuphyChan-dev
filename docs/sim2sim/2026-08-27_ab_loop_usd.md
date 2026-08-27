# AB(폐루프 2-RSU) 발목의 USD 이식 — MuJoCo vs IsaacSim 정적 검증 (2026-08-27)

> *한 줄*: URDF가 표현하지 못하는 폐루프 발목을 **USD에서 4개의 구면조인트로 직접 닫고**,
> 같은 자세에서 **모터 토크 max 0.0078 N·m 일치 / 루프 벌어짐 0.0003 mm / 자유 발목이 MuJoCo와
> 2 µrad 이내 동일 지점에 안착**함을 확인했다. RP(직렬)에 이어 **AB도 IsaacSim으로 이전 가능**하다.

![[xengine_loop_static.png]]

## 0. 무엇이 문제였나

발목은 정강이(shin)에 달린 **크랭크 A/B** 2개가 **로드 A/B** 2개를 밀어 **발판(foot_link)** 을 기울이는
2-RSU 병렬 기구다. 즉 `정강이 → 크랭크 → 로드 → 발판 → (발목 피치/롤) → 정강이` 로 **닫힌 고리**가 생긴다.
URDF는 트리만 표현할 수 있어 로드의 끝단이 허공에 뜬 **뼈대(skeleton)** 밖에 못 옮긴다.
MuJoCo 쪽은 `<equality><connect>` 4개(다리당 2개)로 이 고리를 닫고 있다.

PhysX도 사정이 같다. articulation(축소좌표 솔버)은 **반드시 트리**여야 하고 고리를 아예 표현하지 못한다.
공식 해법은 고리를 끊는 조인트 하나를 골라 `physics:excludeFromArticulation = true` 로 표시해
**최대좌표(maximal) 강체 조인트**로 넘기는 것이다 — 그 조인트는 힘을 만들지 않는 **순수한 공간 구속**이 된다.

## 1. 무엇을 했나

| 단계 | 도구 | 결과 |
|---|---|---|
| 1 | `tools/sim2sim/urdf_to_usd.py` (loop URDF) | 30 링크 / 29 회전관절 / **31.3202 kg** — 크랭크·로드가 막다른 가지로 붙은 직렬 뼈대 |
| 2 | `tools/sim2sim/author_loop_usd.py` | `<connect>` 4개 → `UsdPhysicsSphericalJoint` 4개 + `excludeFromArticulation=true` |
| 3 | `tools/sim2sim/xengine_loop_mujoco.py` | 루프가 닫히는 자세를 뉴턴 해로 구함(잔차 **8.7e-10 mm**) + 정적 기준토크 2종 |
| 4 | `tools/sim2sim/xengine_loop_isaac_side.py` | 베이스 용접, 같은 자세, 정착 후 실효토크·루프 벌어짐 측정 |
| 5 | `tools/sim2sim/xengine_loop_report.py` | **Isaac이 실제 도달한 자세**에서 MuJoCo 재평가 → 대조표 |

**앵커는 옮겨 적지 않았다.** MJCF의 site `pos`는 이미 부모 바디 좌표계 값이고, URDF 임포터는
관절 `localPos0` = 부모 링크 좌표계의 origin, `localPos1` = 0 으로 쓴다(직접 확인).
즉 **링크 좌표계가 변환 없이 그대로 살아남으므로** site 좌표가 `localPos0/1`에 그대로 들어간다.

**총질량 차 3.9 g의 정체**: MuJoCo는 U-조인트 2자유도를 로드 바디 하나에 얹지만, URDF는 관절 사이에
링크가 있어야 하므로 1 g짜리 더미 링크 `*_rod_*_u` 4개가 생긴다. 31.3163 + 0.004 = **31.3203 kg**로 정확히 설명된다.

## 2. ★ 폐루프에서 `qfrc_bias`는 모터 토크가 아니다

직렬 모델에서는 관절의 중력 부하 = 그 관절 아래 subtree 무게이므로 `qfrc_bias`가 곧 답이었다.
루프에서는 아니다. **발판 무게는 크랭크의 subtree에 들어 있지 않고 로드를 타고 도착**하며,
발목 피치/롤에는 애초에 모터가 없다. 그래서 두 질문을 분리해 계산했다:

- **`motors`(실제 기계)** — 17개 실모터만 잡고 나머지는 자유. 정역학:
  $\tau_{act} + J_c^{\mathsf{T}}\lambda = \mathrm{qfrc\_bias}$ 를 17개 토크 + 12개 구속력에 대해 푼다
  (29×29 정방, cond 17.8, 잔차 3e-14 N·m).
- **`all_held`(직렬 스크립트를 그대로 옮긴 경우)** — 모든 관절을 서보로 잡음 → 루프는 아무것도 안 나름.

크랭크에서 둘의 차이는 2배에 가깝다 (예: `L_crank_A` **0.0887 → 0.0513 N·m**). 그림 오른쪽 패널이 그것이다.
직렬 스크립트를 그대로 이식했다면 이 차이가 "엔진 불일치"로 오독됐을 것이다.

## 3. 결과

| 항목 | 값 | 판정 |
|---|---|---|
| 모터 토크 차이 (`motors`) | **max 0.0078 N·m** (R_hip_pitch), 중앙값 0.0007 | 직렬 기준(0.0070)과 **동급** ✅ |
| 최대 부하 대비 | 3.23 N·m 중 0.24 % | ✅ |
| 루프 벌어짐 (Isaac 월드 앵커 간 거리) | **0.00013 ~ 0.00030 mm** | 목표 1 mm의 **1/3000** ✅ |
| 자유 발목 안착 위치 | Isaac − MuJoCo(같은 크랭크각) = **≤ 2 µrad** | ✅ |
| DOF / 링크 / 질량 | 29 / 30 / 31.3202 kg (양쪽 동일) | ✅ |
| `all_held` 차이 | max 0.0645 N·m — **전부 루프 관련 관절**(발목 피치·크랭크·rod u1) | 예상된 계측 오류 ⚠ |

`motors` 단계에서 발목이 명령 자세에서 0.021 rad 벗어난 것은 **기하 오차가 아니라 크랭크 서보 처짐**이다:
크랭크 −0.0206 rad ↔ rod u1 +0.0215 ↔ 발목 피치 +0.0209 로 1:1 전달되며,
같은 크랭크각을 MuJoCo에 주고 루프를 풀면 **2 µrad 이내로 같은 곳**이 나온다.

## 4. MJCF 임포터 실측 — 예측은 맞았고, 형태만 달랐다

리서치 노트의 예측: `LoadEqualityConnect()`가 `std::string(c->Attribute("body1"))`를 널 검사 없이 호출 →
우리 XML은 `site1`/`site2` 형식이라 nullptr → **세그폴트**.

실측(설치본 2.5.8):
- 정적 근거 — 배포 플러그인 `.so`에 `body1`/`body2`/`anchor`/`connect`/`equality` 문자열은 있고 **`site1`/`site2`는 없다**.
- 동적 근거 — `MJCFCreateAsset`이 **`RuntimeError: basic_string::_M_construct null not valid`** 로 실패.
  결과: `import_status=(False, None)`, 조인트 프림 0개, `/loop_joints` 없음.

⇒ **원인(널 문자열 생성)은 예측 그대로**, 다만 세그폴트가 아니라 잡히는 C++ 예외였다.
프로세스는 살아남지만 **모델은 하나도 안 나온다**. 손 저작(path #1)이 옳은 선택이었음이 확인됐다.

## 5. 재사용을 위한 함정 3개

1. **`pxr`는 SimulationApp 없이도 쓸 수 있다.** isaacsim 휠 안 `extscache/omni.usd.libs-*/pxr`를
   `PYTHONPATH`에, 그 `bin`·`lib`과 **인터프리터의 `libpython3.11.so.1.0`** 을 `LD_LIBRARY_PATH`에 넣으면 된다.
   (이게 없으면 임포트가 맨 `ImportError`로 죽어 원인이 안 보인다.) → USD 저작은 **GPU 락이 필요 없다**.
2. **리셋 때 관절 위치는 전부 한 번에.** 구동 관절만 넣으면 폐쇄 구속이 자세와 싸워 로봇이 날아간다
   (IsaacLab #1250, 아직 미해결). 본 스크립트는 29개를 항상 함께 쓴다.
3. **폐쇄 조인트에는 limit·drive·저항을 절대 넣지 말 것.** 콘 각도는 -1(무제한), 강성 0.
   최대좌표 조인트는 articulation보다 **낮은 우선순위**로 풀리므로 오차가 여기 쌓인다
   (그래서 velocity iteration을 임포터 기본 1 → 4로 올려 저작해 둔다).

## 6. 남은 것

- ~~정적 일치 ≠ 동적 일치. 다음은 AB 정책 롤아웃~~ **완료** → [[2026-08-27_ab_dynamic_rollout]].
  ⚠ 그 롤아웃은 **v3 루프 USD**를 새로 빌드해 썼다 — `bundleD1_AB`가 학습한 모델이 v3(35.347 kg)이고
  이 노트의 USD는 v4(31.320 kg)이기 때문이다. 이 노트의 정적 검증은 v4 자산에 대한 것으로 유효하다.
- 폐쇄 조인트의 **compliance(MuJoCo `solref`/`solimp`)는 이식되지 않는다**(손 저작이든 임포터든 동일).
  현재는 PhysX의 강체 구속으로 근사되어 있고, 충격 시 이 차이가 어떻게 드러나는지는 미측정.
- ~~루프 벌어짐은 정적 하중에서의 값이다~~ ★**측정했고, 같은 수준이 아니다**
  ([[2026-08-27_ab_dynamic_rollout]] §5): 걷는 동안 Isaac은 반복수 32/16에서 평균 0.043 / 최대
  2.82 mm, 4/8에서 평균 2.56 / 최대 **12.94 mm**까지 벌어진다. **비교 기준도 0이 아니다** —
  같은 정책으로 굴린 MuJoCo 자신이 최대 **0.626 mm** 벌어진다(`connect`는 소프트 구속).
  ⇒ 본 노트의 0.0003 mm는 *정지 하중*의 값으로만 인용할 것.

도구: `tools/sim2sim/{author_loop_usd,xengine_loop_mujoco,xengine_loop_isaac_side,xengine_loop_report,plot_loop_xengine,mjcf_import_probe}.py`
드라이버: `tools/sim2sim/run_loop_usd_build.sh` (공용 GPU 락 `~/pyg_fea/locks/gpu.lock`을 mkdir로 잡고 전체 순서 실행)
산출물: `/home/syaro/pyg_fea/usd/pygmalion_v4_printed_loop.usd` ·
결과 JSON `/home/syaro/pyg_fea/work/xengine_loop_{mujoco,isaac,verdict}.json`, `author_loop_usd.json`, `mjcf_import_probe.json`
리서치 근거: `docs/research_raw/2026-08-27_physx_closed_loop_ankle.md`
