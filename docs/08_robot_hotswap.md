# 08 · 로봇 핫스왑 (질량/관성/관절구조를 쉽게 갈고 재학습)

> [!abstract] 목표
> 설계가 자주 바뀌므로(무게·관성·COM·관절구조), **YAML 한 파일만 고치고 1커맨드로 변환→재학습**하도록.
> 모든 body/joint 이름·actuator·물리속성이 이 spec 한 곳에서 나온다(다른 곳 하드코딩 없음).

---

## 왜 (Why)
하드웨어 프로토타이핑은 반복이다. 매번 코드 여러 군데(actuator, 이름 regex, reward)를 고치면 실수·드리프트가 난다.
→ **단일 진실원(single source of truth)** = `assets/robot_specs/robstride_biped.yaml`.

## 무엇을 (What) — spec이 정의하는 것
- `source.file`: 로봇 원본(**MJCF .xml/.mjcf 또는 URDF**) + USD 출력 경로
- `convert`: fix_base, 관성 임포트, self_collision 등 변환 옵션
- `init`: 스폰 높이 + 초기 관절각
- `roles`: **base / foot / undesired_contact / target_base_height** (env가 여기서 읽음)
- `actuators`: 그룹별 `type: motor | passive_spring`, effort/velocity/stiffness/damping/armature
- `action_joints`: 정책 제어 관절(생략 시 motor 그룹에서 자동 도출 → 패시브 자동 제외)
- `physics`: **mass_scale_all + per-body overrides(mass/mass_scale/inertia_scale/com)** — 시작 시 적용

## 어디서 (Where)
- spec: `assets/robot_specs/robstride_biped.yaml`
- 로더: `source/pygmalion_locomotion/robots/spec.py` (`RobotSpec`, `build_articulation_cfg`,
  `convert_to_usd`, `apply_physics_overrides`, `roles`)
- `robots/biped_cfg.py` → spec에서 ArticulationCfg 생성 (하드코딩 제거)
- `tasks/.../velocity_env_cfg.py` → `ROLES`에서 이름 읽음, startup 이벤트 `apply_robot_physics`

## 어떻게 (How) — 시나리오별

### A. 물리속성만 바꾸기 (질량/관성/COM) — **변환 불필요**
`physics:` 섹션만 수정 후 재학습. 예:
```yaml
physics:
  mass_scale_all: 1.2            # 전체 20% 무겁게
  overrides:
    - {body: base_link, mass: 30.0}        # 몸통 절대질량 30kg (관성 비례 보정)
    - {body: ".*_shin_link", mass_scale: 1.1}
    - {body: base_link, com: [0.0, 0.0, -0.02]}  # COM 2cm 아래로
```
→ startup 이벤트가 `default_mass/default_inertia`에서 **매번 재계산**(idempotent)해 적용. MJCF·USD 손 안 댐.

### B. 관절구조/로봇 바꾸기 — **변환 1커맨드**
1. 새 MJCF/URDF를 `assets/`에 두고 `source.file`을 가리킴
2. `actuators` 그룹·`roles`·`init.joint_pos`의 관절/링크 이름을 새 구조에 맞게 수정
3. 변환 + 학습:
```bash
python scripts/convert_asset.py --force      # 소스 바뀌면 자동 재변환(해시 캐시). 메시만 바꾸면 --force 필수
python scripts/train.py --task Pygmalion-Velocity-Flat-v0 --headless --num_envs 512
```
> USD는 **소스 파일 바이트 + 변환옵션 해시**로 캐시 → 소스가 바뀌면 자동 재생성. 단 *참조 메시*만 바꾸면
> 해시가 안 변하므로 `--force` 필요(코드 주석·이 노트에 명시).

## 검증된 동작 (구현 시 확인)
- spec 파싱/검증 + action joint 자동 도출(toe 제외) ✓
- **passive_spring effort_limit=0 거부**(스프링이 죽는 실수 방지) ✓
- `effort_limit_sim`/`velocity_limit_sim` 사용 — implicit actuator에서 `velocity_limit`은 무시되는
  Isaac Lab 2.2 동작 반영(구버전 코드의 잠재 버그 수정).

## 설계 안전장치 (적대적 리뷰 반영)
- **모든 관절이 actuator 그룹에 속해야** Isaac Lab이 에러 안 냄 → 검증에서 강제(toe=passive 포함).
- **질량 단일 소유**: spec이 소유, env의 `add_base_mass`는 끔(이중적용 방지).
- regex는 `re.match`(시작 고정) — 이름 변경 시 매칭 0이면 경고.
- 질량 절대지정 시 관성은 new/old 비로 스케일, 항상 `default_*`에서 재계산(누적 오류 방지).

## 관련 노트
- [[02_asset_conversion]] · [[03_environment]] · [[05_sensing_logging]]
