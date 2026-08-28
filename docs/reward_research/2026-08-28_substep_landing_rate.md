# reward 연구 — 착지 하중률을 물리 서브스텝(200 Hz)에서 계산하는 재설계 (2026-08-28)

> 트리거: [[2026-08-26_human_landing_bundle]] §11c — 평가기(50 Hz control step)와 `impact_probe_multi`(200 Hz
> physics substep)가 CTL/처치군의 **순서 자체를 뒤집었다**. 원인은 CTL의 착지 스파이크가 15–25 ms 폭인데 50 Hz
> 샘플링(20 ms 간격)이 그 스파이크의 절반을 놓치기 때문(§11c 실측: 진짜 피크 2.353 BW vs 평가기 관측 1.207 BW).
> `foot_loading_rate`(`rewards.py:700-767`)는 지금 `env.step_dt`(50 Hz) 한 번의 차분으로 dF/dt를 계산한다 —
> 측정 대상과 같은 종류의 에일리어싱을 **보상 항 자체가** 겪는다. 바꾸려는 reward:
> `foot_loading_rate`의 rate 계산을 50 Hz control-step diff → 200 Hz physics-substep 기반으로 교체하고,
> 그 데이터를 공급하기 위해 `feet_ground_contact` 센서(`config/pygmalion/env_cfgs.py:76-87`)에
> `history_length`를 배선한다. 부수 발견: `contact_force_cap`(`rewards.py:807`)도 같은 종류의 결함을 공유한다
> (§4c, 별도 후속 과제로 플래그만 하고 본 노트의 범위 밖에 둔다).

## 1. 직전 결과 분석 (기존 노트 재확인, 새로 만든 데이터 없음)

이 노트는 새 학습·측정을 돌리지 않았다 — [[2026-08-26_human_landing_bundle]]에 이미 있는 §11(200 Hz 다중env
프로브)과 §12(부호버그 사후분석)의 결론을 **재조합**해 다음 질문에 답한다: "50 Hz 에일리어싱을 안 겪는 하중률
항을 어떻게 만드는가." 관련 실측 재인용:

| 지표 | CTL | TRT(`rate`) | B2(`both`) | 비고 |
|---|---:|---:|---:|---|
| 스트라이크 피크 GRF, 200 Hz 다중env 중앙값 (BW) | **2.353** | 1.353 | 1.261 | §11b |
| 하중률, 200 Hz 다중env 중앙값 (BW/s) | **277.4** | 23.7 | 28.6 | §11b |
| 스트라이크 피크 GRF, 평가기 50 Hz·32ep (BW) | 1.207 | 1.155 | 1.135 | §10 — CTL이 실제 피크의 **절반**만 보임 |
| 하중률, 평가기 50 Hz·32ep (BW/s) | 9.92 | 15.78 | **8.78** | §10 — **CTL·TRT의 순서가 200Hz와 반대** |

§12에서 밝혀진 두 번째 문제: `foot_loading_rate`는 접촉힘 z부호 버그로 **세 번의 런(2,400 iter×3) 동안 정확히
0**이었다. 부호는 이미 고쳐졌고(`rewards.py:743-745`의 `(-contact_sensor.data.force[..., 2]).clamp(min=0.0)`),
가중치 `1e-4`(`config/pygmalion/env_cfgs.py:397-406`)는 §12d가 명시하듯 **"항이 죽어 있던 상태에서 정한 값이라
학습에서 한 번도 검증되지 않았다."** 즉 이 항은 (a) 살아는 있지만 (b) 학습에서 시험된 적 없고 (c) 시험되더라도
50 Hz 표본으로 계산돼 자신이 잡으려는 현상보다 느리게 샘플링한다 — 세 가지가 독립적인 미해결 문제다. 본 노트는
(c)를 해소하는 것이 목표이고, (b)는 §6의 게이트 절차로, (a)는 이미 해소됐다.

## 2. 이전 이력 — 반복하면 안 되는 실패 3종

1. **`foot_impact_velocity` 선형형**(2026-08-24 최초): 접지속도에 선형 relu 벌점 → 속도-무관 함정,
   `Σv·dt` = 밴드 통과 거리이므로 정책이 **더 빨리 통과**해 회피(1.24→2.42 m/s). 제곱형(`power=2.0`)으로 교정된
   채 지금도 사용 중(`rewards.py:657-699`). [[feedback-velocity-penalty-speed-invariant]]. **교훈**: 벌점이
   "통과형"일 때는 속도-불변성을 먼저 점검.
2. **`foot_loading_rate`를 `foot_impact_velocity`의 대체물로 투입**(bundleTRT, 2026-08-26 §7/§10/§12): 처음엔
   "하중률 항이 stride를 줄이는 해킹을 낳는다"로 기각했으나(§7), 32-episode 평가기 재측정(§9)과 텐서보드
   대조(§12b)로 재해석하니 **실제로 시험된 변인은 `foot_loading_rate`가 아니라 `foot_impact_velocity` 가중치를
   0으로 만든 것**이었다(항이 죽어 있었으므로). **교훈**: 검증된 항을 절대 완전 제거하지 말고 병행(`both`/`half`)
   하라 — 이번 노트의 제안도 이 규칙을 따른다(§6).
3. **단일 env 롤아웃으로 판정**(§9): `bundleC3`(단일env) vs `B3`(같은 설정, 1024env)의 duty가 0.77 ↔ 0.57,
   stride가 0.80 ↔ 1.52로 갈렸다 — **설정 차이가 아니라 배치 분산**이었다. 32-episode 평가기로 재측정하니 둘 다
   정상. **교훈**: 어떤 판정도 단일 env로 하지 않는다(이 세션에서 7번째 반복이라고 §9가 명시).

## 3. mjlab 코드베이스 조사 — 서브스텝 데이터를 리워드가 볼 수 있는가

### 3a. 리워드 매니저는 정말 control-step에서만 실행된다
`ManagerBasedRlEnv.step()`(`manager_based_rl_env.py:378-440`):
```python
for _ in range(self.cfg.decimation):        # L421 — 여기가 200 Hz 루프
  self.action_manager.apply_action()
  self.scene.write_data_to_sim()
  self.sim.step()
  self.scene.update(dt=self.physics_dt)     # L426 — 센서 update()도 매 서브스텝 호출됨
  self.metrics_manager.compute_substep()
...
self.reward_buf = self.reward_manager.compute(dt=self.step_dt)   # L440 — 루프 밖, 50 Hz
```
`decimation=4`, `physics_dt`(L261) = `sim.mujoco.timestep`(0.005s=200Hz), `step_dt`(L266) =
`physics_dt*decimation`(0.02s=50Hz). 리워드 함수 자체는 서브스텝을 볼 수 없다 — **다만 센서는 매 서브스텝
`update()`를 받는다**(L426, decimation 루프 안). 여기가 서브스텝 데이터를 control-step 리워드로 옮길 수 있는
유일한 지점이다.

### 3b. 그 다리는 이미 존재한다 — `ContactSensorCfg.history_length`
`contact_sensor.py:141-146` (docstring, 원문 그대로):
> "If >0, keep a rolling buffer of the last N substeps of force/torque/dist data. **Set to your decimation
> value so the buffer covers exactly one policy step**; useful for catching brief collisions that resolve
> mid-substep."

구현: `_update_history()`(L492-508)가 `scene.update()`를 통해 **매 서브스텝** 호출되어 `force_history`
버퍼([B, N, H, 3], `history_length` H)를 롤링 삽입한다(index 0 = 최신, `contact_sensor.py:218-224`).
H를 `decimation`과 같은 값(우리 설정에서 4)으로 두면, control-step이 끝나는 시점에 이 버퍼는 **그 control-step
동안 일어난 4번의 물리 서브스텝 샘플을 정확히, 겹침도 빠짐도 없이** 담고 있다(버퍼 크기 == 리셋 주기).
`mjlab/tests/test_contact_sensor.py:803-882`의 `test_history_shape`/`test_history_ordering`이 이 정확한
동작(순서·형상)을 이미 검증한다.

### 3c. 이 다리는 이미 이 코드베이스에서 쓰이고 있다 — 새로 만들 필요가 없다
`self_collision_cost`(`rewards.py:260-279`)가 정확히 이 패턴이다:
```python
def self_collision_cost(env, sensor_name, force_threshold=10.0):
  data = env.scene[sensor_name].data
  if data.force_history is not None:            # <- 있으면 서브스텝 해상도로
    force_mag = torch.norm(data.force_history, dim=-1)   # [B, N, H]
    hit = (force_mag > force_threshold).any(dim=1)         # [B, H]
    return hit.sum(dim=-1).float()
  assert data.found is not None                  # <- 없으면 50 Hz로 폴백
  return data.found.sum(dim=-1).float()
```
그리고 `self_collision` 센서는 실제로 `history_length=4`가 배선돼 있다(`config/pygmalion/env_cfgs.py:88-97`).
**`feet_ground_contact` 센서(`env_cfgs.py:76-87`)만 `history_length`가 없다**(기본값 0, `force_history=None`).
그 결과 `soft_landing`(L507)·`foot_impact_velocity`(L657)·`foot_loading_rate`(L700)·
`stance_knee_extension`(L768)·`contact_force_cap`(L807) — **발 접촉힘을 읽는 모든 리워드 항**이 50 Hz
`data.force`만 읽는다. 즉 §11c가 발견한 에일리어싱은 `foot_loading_rate` 하나만의 문제가 아니라 **`feet_ground_
contact`에 연결된 항 전부의 구조적 문제**이고, 고치는 방법은 이미 이 저장소 안에 검증된 형태로 존재한다 —
`self_collision_cost`가 5주 넘게 켜져 있었다는 것 자체가 이 메커니즘이 학습 루프에서 안전하다는 증거다.

### 3d. 메모리 비용
`force_history`는 `[num_envs, 2 feet, 4, 3] float32`. 16384 env에서 1.6 MB — 학습 RAM 예산(★실측 15 GB,
[[project-pygmalion-locomotion]])에 무시할 수준. `self_collision_cfg`가 이미 같은 크기를 물고 있다.

### 3e. mjx/warp 콜백은 필요 없다
질문에서 물었던 "mjx/warp per-substep callback"에 해당하는 것은 이 프로젝트엔 없고 **필요하지도 않다** —
`Scene.update()`가 이미 매 서브스텝 불리는 훅이고, `ContactSensor`가 그 훅에 얹혀 히스토리를 쌓는다.
`impact_probe_multi.py`가 하는 `sim.step` 몽키패치(외부 훅, 오프라인 측정 전용)와 달리, `history_length`는
**학습 루프 안에서 리워드가 직접 읽을 수 있는** 유일한 경로다.

## 4. 학술/자료조사

### 4a. 서브스텝 해상도 impact reward의 최신 사례
- **QuietWalk** (arXiv:2604.23702, 2026-04, "Physics-Informed RL for GRF-Aware Humanoid Locomotion"):
  PINN 기반 역동역학-일관 GRF 추정기를 학습 루프에 얼려 넣고, **발당 수직 GRF의 제곱**으로 impact reward를
  구성한다. "먼저 작은 impact 가중치로 안정 보행을 학습한 뒤 점진적으로 가중치를 올린다"는 **커리큘럼**을
  명시 — 이 프로젝트의 "죽어있던 항의 가중치를 학습 전 검증 없이 못 박지 말라"(§12d)는 교훈과 같은 방향.
  간접 신호(접지속도/가속도)보다 **직접 GRF 기반 페널티가 우월**하다고 주장하는 점도 우리가 `foot_impact_
  velocity`(간접, 접지속도) 하나만으로는 부족했던 경험(§7/§11d — 자세와 하중률이 트레이드오프 관계)과 정합.
- **"max foot speed in a short history window upon touchdown"** (Berkeley/OSU 계열 Cassie/Digit sim-to-real
  RL 문헌, 2022-2024, 예: arXiv:2207.07835 계보 "Dynamic Bipedal Maneuvers through Sim-to-Real RL") —
  터치다운 직후 **짧은 히스토리 윈도우에서 최댓값**을 벌점 대상으로 삼는 패턴이 실기 이식된 선례로 확인된다.
  대상이 발속도이지 dF/dt는 아니지만, **"단일 샘플 대신 윈도우 내 max"**가 실기 검증된 패턴이라는 점에서
  본 노트가 제안하는 "H개 서브스텝 내 max"와 같은 형태다.
- 자사 기존 인용(2026-07-02_gait_research_q123.md, 재확인만): Humanoid-Gym 역치형 GRF 벌점(C11, 실로봇
  검증, `-0.01·min(max(F-400N,0),100)`), Cassie 충격/smoothing 커리큘럼(C3, 후반에 충격 가중치↑), REEM-C
  역치 cap(F4, 1500N). 전부 **역치+클립형**이고 **커리큘럼**을 쓴다 — 우리 `contact_force_cap`이 이미 이
  선례를 따르고 있다(threshold 420N=1.2BW, clip 560N).

### 4b. "리워드 에일리어싱"은 legged-RL 특유의 개념이 아니라 신호처리 일반론
WebSearch로 "reward sampled below the phenomenon's Nyquist rate"에 대한 legged-RL 전용 논문은 찾지 못했다
(신뢰도 낮음 — 이 정확한 실패모드를 다룬 논문은 없거나 검색으로 발견 못함). 대신 확인된 것: (1) 신호처리
일반론 — 표본화 주파수가 낮으면 고주파 성분이 저주파로 접힌다(에일리어싱, Data Physics DSA 개론) — 이 노트가
말하는 메커니즘의 교과서적 근거이지 legged-RL 특이 사례는 아니다. (2) 로보틱스 RL 일반론 — "실기 제어주파수는
200–1000 Hz인데 정책은 그보다 낮은 빈도로 갱신되고, 그 사이는 별도의 고빈도 컨트롤러(예: 관절 임피던스
1000 Hz)가 채운다"는 계층 구조가 흔하다(쿼드러페드 RL 50 Hz + 조인트 컨트롤러 1000 Hz 사례) — 이는 우리
문제와 반대 방향의 해법(정책이 아니라 저수준 컨트롤러가 고주파를 처리)이라 이 프로젝트(순수 end-to-end RL,
WBC/임피던스 레이어 없음)에는 직접 적용되지 않는다. **결론**: "control-step보다 빠른 물리 현상을 벌점 대상으로
삼을 때 control-step 샘플링을 쓰면 측정-회피가 나온다"는 이 노트의 핵심 주장은 **§11c의 자사 실측**(200Hz vs
50Hz 순서 역전)이 근거이지, 외부 논문이 직접 근거는 아니다 — 정직하게 표기한다.

### 4c. 부수 발견 — `contact_force_cap`도 같은 병을 앓는다 (본 노트 범위 밖, 후속 과제로만 기록)
`contact_force_cap`(`rewards.py:807-833`)은 `torch.norm(sensor_data.force, dim=-1)`로 **50 Hz `data.force`**를
읽는다. §11b/§10 실측이 이미 보여주듯 CTL의 진짜 피크는 2.353 BW인데 50 Hz 평가기는 1.207 BW만 본다 — 즉
`contact_force_cap`의 threshold 420N(1.2 BW)이 걸러야 할 진짜 스파이크의 **거의 절반을 놓치고 있을 가능성이
높다**. 고치는 방법은 §3c와 동일(`force_history.max(dim=-1)`로 피크를 대체) — 이 노트의 §6에서 대안 B로
같이 제시하되, `foot_loading_rate` 자체의 수정과는 **독립적으로 검증**해야 한다(한 번에 두 항을 바꾸면 원인을
분리할 수 없다는 것이 §7/§12b의 교훈이다).

## 5. 원인 규명

**근본 원인**: `feet_ground_contact` 센서에 `history_length`가 배선돼 있지 않아, 이 센서를 읽는 리워드 항
전부가 200 Hz 현상(15–25 ms 폭 착지 스파이크)을 50 Hz(20 ms 간격)로 표본화한다. 이건 `foot_loading_rate`
하나의 버그가 아니라 **센서 설정의 구조적 공백**이고, 고치는 메커니즘(`history_length` + `force_history`)은
이미 이 저장소의 `self_collision_cost`가 5주 이상 실전에서 써온 검증된 패턴이다. `foot_loading_rate`가 rate
(1계 차분)를 계산하기 때문에 이 에일리어싱의 피해가 가장 크게 증폭된다 — 피크 자체는 50%만 줄어 보이지만
(2.353→1.207 BW) 그 차분인 하중률은 CTL/처치군의 **순서 자체가 뒤집힐 정도**로 왜곡된다(§1 표).

## 6. 제안

### 6a. 센서 배선 (선행 조건, 1줄)
`config/pygmalion/env_cfgs.py:76-87`의 `feet_ground_cfg`에 `self_collision_cfg`와 동일한 방식으로 추가:
```python
feet_ground_cfg = ContactSensorCfg(
  name="feet_ground_contact",
  primary=ContactMatch(mode="subtree", pattern=r"^(L_foot_link|R_foot_link)$", entity="robot"),
  secondary=ContactMatch(mode="body", pattern="terrain"),
  fields=("found", "force"),
  reduce="netforce",
  num_slots=1,
  track_air_time=True,
  history_length=4,   # NEW — env.cfg.decimation과 반드시 같은 값으로 하드코딩하지 말고 참조할 것
)
```
`history_length`는 상수 4가 아니라 **`cfg.decimation`을 그대로 참조**하도록 배선해야 한다(decimation이 바뀌면
같이 깨지는 하드코딩을 피한다). 이 변경은 `force`/`found`의 형태·다른 항의 동작에 영향을 주지 않는다
(`self_collision_cost`가 이미 증명 — history 필드는 순수 추가분이다).

### 6b. 본 제안 — `foot_loading_rate`를 서브스텝 rate로 승격 (대안 A: rate, 요청된 항 그대로)
기존 클래스(`rewards.py:700-767`)의 상태머신(터치다운 검출·윈도우·제곱 비용·명령 게이트·로깅)은 **그대로
둔다** — 오직 "이번 control-step의 순간 rate를 어떻게 계산하는가" 한 줄만 바꾼다.

```python
class foot_loading_rate:
  def __init__(self, cfg, env):
    contact_sensor = env.scene[cfg.params["sensor_name"]]
    n_feet = contact_sensor.data.force.shape[1]
    self._prev_f = torch.zeros(env.num_envs, n_feet, device=env.device)  # 직전 윈도우의 마지막 서브스텝값
    self._peak = torch.zeros(env.num_envs, n_feet, device=env.device)
    self._age = torch.full((env.num_envs, n_feet), 1e3, device=env.device)
    self._dt_phys = env.physics_dt                                      # NEW: 200 Hz 실제 dt

  def __call__(self, env, sensor_name, body_weight=346.8, window_s=0.06,
               contact_threshold=7.0, rate_clip=400.0,                  # NEW: rate_clip
               command_name=None, command_threshold=0.05):
    contact_sensor: ContactSensor = env.scene[sensor_name]
    fh = contact_sensor.data.force_history
    assert fh is not None, "feet_ground_contact needs history_length == decimation (see 6a)"
    fz_sub = (-fh[..., 2]).clamp(min=0.0).flip(-1)     # [B,F,H], index0(최신)->flip->시간순 oldest..newest
    seq = torch.cat([self._prev_f.unsqueeze(-1), fz_sub], dim=-1)              # [B,F,H+1], 이음매 없음
    d = (seq[..., 1:] - seq[..., :-1]).clamp(min=0.0) / self._dt_phys / body_weight  # [B,F,H] BW/s @ 200Hz
    d = d.clamp(max=rate_clip)              # 접촉솔버 잡음 1-서브스텝 스파이크가 제곱항을 지배하지 않게 가드
    rate = d.max(dim=-1).values             # 이번 control-step 동안의 진짜 200Hz 피크 rate
    self._prev_f = fz_sub[..., -1].clone()  # 다음 윈도우를 위해 이번 윈도우의 마지막 서브스텝값 저장

    f = fz_sub[..., -1]                     # == 기존 코드의 f (data.force와 동일한 순간값)
    in_contact = f > contact_threshold
    touchdown = in_contact & (self._age > window_s)
    self._age = torch.where(touchdown, torch.zeros_like(self._age), self._age + env.step_dt)
    self._age = torch.where(in_contact, self._age, torch.full_like(self._age, 1e3))
    inside = in_contact & (self._age <= window_s)
    self._peak = torch.where(touchdown, rate, torch.where(inside, torch.maximum(self._peak, rate), self._peak))
    scored = inside & (self._age >= window_s - env.step_dt)
    cost = torch.sum((self._peak * scored.float()) ** 2, dim=1)
    # ... (Metrics 로깅·command 게이트는 기존과 동일, 생략)
    return cost
```
`impact_probe_multi.py`의 오프라인 슈미트-트리거 검출과 다르게, 여기선 터치다운 판정(50 Hz 기준 `in_contact`)
은 그대로 두고 **rate 계산만** 200 Hz로 올린다 — 판정 로직을 새로 만들지 않아 회귀 위험이 작다.

### 6c. 대안 B — 서브스텝 피크힘 (미분 없음, 더 단순·더 강건)
```python
def foot_peak_substep_force(env, sensor_name, threshold=420.0, clip=560.0,
                             command_name=None, command_threshold=0.05):
  """contact_force_cap과 같은 형태(threshold+clip, C11/F4 선례)지만 50Hz data.force 대신
  200Hz force_history의 이번 control-step 내 최댓값을 본다."""
  fh = env.scene[sensor_name].data.force_history
  assert fh is not None
  peak = (-fh[..., 2]).clamp(min=0.0).max(dim=-1).values     # [B,F] 진짜 200Hz 피크
  excess = torch.clamp(peak - threshold, min=0.0, max=clip)
  return torch.sum(excess, dim=1)   # (+ command 게이트는 기존 항들과 동일 패턴)
```
`threshold=420N`/`clip=560N`은 **새로 정하지 않고** `contact_force_cap`의 PYG_SOFT_LANDING 값을 그대로
재사용한다(`config/pygmalion/env_cfgs.py:288-289`, 1.2×BW 유도 근거는 2026-08-24 노트) — 같은 물리량을
더 정확한 해상도로 보는 것뿐이므로 새 상수를 발명하지 않는다.

### 6d. 랭킹과 회피-강건성 근거

| 순위 | 항 | 회피-강건성 | 비고 |
|---|---|---|---|
| **1** | **대안 B: 서브스텝 피크힘** | 틱 사이 은닉 불가(§3c 메커니즘 자체가 매 서브스텝을 봄) **AND** "발을 안 뗀다"는 하중률 특유의 퇴화해가 **원천적으로 없다** — 입각기 정상 지지력(~0.5–1.0 BW/발)은 애초에 threshold(1.2 BW) 아래라 계속 밟고 있어도 비용이 늘지 않는다. 1계 미분이 없어 접촉솔버 잡음 증폭도 없다 | `contact_force_cap`의 검증된 상수를 재사용하는 가장 낮은 리스크의 변경. **선행 도입 권장** |
| **2** | **대안 A: 서브스텝 rate (본 요청)** | 틱 사이 은닉은 막지만, **"계속 밟고 있으면 dF/dt=0"이라는 퇴화해는 여전히 존재**(§7 B2/TRT에서 실제로 관측된 메커니즘, duty 0.75·stride 0.83) — `rate_clip` 가드로 잡음은 줄여도 이 해킹 경로 자체는 그대로다. **stride/s·air_time·duty를 상시 게이트 지표로 유지해야 함**(§7 규칙, 반복 강조) | 스파이크의 "모양"(상승 속도)을 직접 겨냥한다는 점에서 질문이 요청한 것과 가장 근접 |
| 3 | `foot_impact_velocity` (기존, 유지) | 접촉 *전*의 밀도 높은 gradient — 위 두 항과 겨냥 지점이 다르다(원인=접근 속도 vs 결과=충격량). §11d: 다리를 펴면(자세 목표) 같은 접지속도라도 rate가 오른다 — **자세와 하중률은 트레이드오프**이므로 이 항 단독으로는 부족하고 위 항들과 상호보완이 필요 | **절대 0으로 만들지 말 것**(§7/§12b 교훈, "half"/"both" 모드 유지) |
| 4 | 임펄스(∫F dt, 입각기 전체) | 완만한 60N/60ms 램프와 날카로운 600N/15ms 스파이크가 총 임펄스는 비슷할 수 있어 **스파이크 모양 정보를 희석**한다 — 이 실패모드(스파이크 그 자체)에는 부적합 | 리워드 항이 아니라 **감시용 보조 지표**로만 병행 계측 권장 |
| 5 | GRF-rate 하드 리밋 / 임피던스 레이어 | Cassie/Digit급 실기는 저수준 임피던스 컨트롤러(≥1000 Hz)가 이 역할을 맡고 RL 정책은 그 위에서 목표를 준다 — **이 프로젝트는 순수 end-to-end RL이라 그런 레이어가 없다**(4b) | 이 노트의 범위 밖. RL 리워드만으로 한계에 부딪히면 검토할 아키텍처 옵션으로만 기록 |

**권장 조합**: 대안 B(피크힘, `contact_force_cap`을 대체 또는 병행)를 먼저 단독 검증 → 이어서 대안 A(rate)를
**`foot_impact_velocity`를 유지한 채** 병행 투입, `both` 방식(§7/§12b가 확정한 유일하게 안전한 병행 패턴)으로.
**둘을 동시에 처음 켜지 않는다** — 원인 분리가 안 된다(§7/§12b의 반복된 교훈).

### 6e. 가중치 시작값 — 숫자를 새로 발명하지 않고 절차로 정한다
§12d 자체가 명시한 실패: "0.002는 항이 죽어 있던 상태에서 정한 값이라 한 번도 검증되지 않았다." 같은 실수를
피하려 **정확한 숫자 대신 절차**를 제안한다:
1. 대안 B의 `threshold`/`clip`은 §6c처럼 `contact_force_cap`의 기존 검증값(420N/560N)을 **그대로 재사용**.
   가중치는 `contact_force_cap`의 현재 `-0.01`을 시작점으로, `/home/syaro/pyg_fea/work/dbg_term_alive.py`로
   최신 체크포인트에서 스텝당 기여를 재고 `contact_force_cap`이 지금 내는 기여(`Metrics/contact_force_
   excess_mean`×가중치)와 같은 자릿수가 되도록만 맞춘다.
2. 대안 A는 지금의 `1e-4`를 시작점으로 유지하되(§12d의 "같은 정책에서 stance_knee_extension과 동급 −0.033"
   기준이 유일하게 있는 보정 근거이므로), **rate_clip**은 `impact_probe_multi.py`로 최신 체크포인트를 200 Hz
   다중env로 먼저 재측정해 관측된 rate 분포의 p90 근방(예: CTL 277 BW/s 중앙값 기준이면 clip을 400–500대에서
   시작)으로 잡는다 — `contact_force_cap`의 clip이 BW 재스케일 실측으로 유도됐던 것과 같은 절차(2026-08-24
   노트).
3. **학습 투입 전 필수**: `dbg_term_alive.py`로 100–120 스텝 굴려 (a) `Episode_Reward/<term>`이 0이 아님
   (b) 부호가 음수 (c) 전체 보상 예산 대비 비중이 `stance_knee_extension`(약 3.7%)과 같은 자릿수인지 확인.
   이건 §12c(3)이 "게이트 체크리스트에 넣는다"고 명시한 바로 그 절차다 — 세 번 죽은 항으로 런을 태운 뒤에
   나온 규칙이므로 반드시 지킨다.

### 6f. 측정 규약 (기존 규칙 재확인, 새로 추가하는 것 없음)
- 하중률·피크힘은 **200 Hz 다중env 프로브(`impact_probe_multi.py`)로만** 최종 판정한다 — 50 Hz 32ep 평가기는
  추종·duty·stride·성공률에 쓴다(§11d 규칙, "두 도구는 경쟁 관계가 아니라 측정 대역이 다르다").
- 판정은 **32 episode 이상**으로만 한다 — 단일 env 롤아웃 금지(§9, 이 세션 7번째 위반이었던 규칙).
- `air_time`/`flight_frac`/`stride/s`/`duty`를 상시 감시 지표에 넣는다 — 대안 A(rate)는 "발을 안 뗀다"는
  퇴화해가 구조적으로 남아 있다(§7).
- 새 항은 검증된 항(`foot_impact_velocity`)을 대체하지 않고 병행한다(`both`) — 완전 제거는 재기각 대상.

## 7. 캐비어트 (≤5)

1. §4b에서 밝혔듯 "control-step보다 빠른 현상을 벌점 삼으면 회피가 나온다"는 이 노트의 핵심 주장은 **자사
   실측(§11c)에 근거**하며, 이 정확한 실패모드를 다룬 외부 legged-RL 논문은 검색으로 찾지 못했다 — 일반
   신호처리 원리로 뒷받침되지만 legged-RL 문헌의 직접 선례는 아니다.
2. 대안 A(rate)의 `rate_clip` 값은 이 노트에서 **추정치**(CTL 277 BW/s 중앙값 참고)일 뿐, `impact_probe_
   multi.py`로 최신 체크포인트를 재측정하기 전까지 확정값이 아니다.
3. §4c(`contact_force_cap`의 동일 결함)는 이 노트의 제안에 포함하지 않았다 — 같이 고치면 원인 분리가 안
   된다는 §7/§12b의 교훈에 따라 **의도적으로 범위 밖에 둔다**. 후속 노트가 필요하다.
4. `history_length`를 `decimation`에 정확히 맞춰야 한다는 전제(§3b/6a)는 코드 docstring과 테스트로
   확인했지만, `decimation`이 4가 아닌 값으로 바뀌는 설정(다른 태스크/체크포인트)에서 하드코딩된 4를 그대로
   쓰면 조용히 틀린 창을 읽는다 — §6a에서 "cfg.decimation을 참조"하라고 명시했지만 구현 시 실제로 하드코딩되지
   않았는지 코드리뷰에서 재확인이 필요하다.
5. 이 노트는 새 학습·측정을 수행하지 않은 **설계 노트**다 — §6e의 가중치·clip은 절차만 제시했고 숫자는
   `dbg_term_alive.py`/`impact_probe_multi.py` 실측 전까지 잠정치다. 실측 없이 이 노트의 숫자를 그대로
   학습에 박아 넣지 말 것(§12d가 경고하는 바로 그 실수).
