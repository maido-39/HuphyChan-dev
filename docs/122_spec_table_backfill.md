# 122. 학습 노트 설정 명세 표(§1b~§1b-4) 전수 소급 + 자동화 (2026-09-03)

> **한 줄**: 학습 기록 111건 전부에 "이 실험은 어떤 설정으로 돌렸나" 표 4종을 붙였고,
> 앞으로는 학습 실행기가 자동으로 넣는다. 표는 사람이 옮겨 적지 않고 **그 런이 남긴
> `params/env.yaml`에서 도구가 생성**한다.
> 도구: `mujoco-sim/mjlab/analysis/run_spec_tables.py` · 소급 드라이버: `tools/notes/backfill_spec_tables.py`

## 1. 배경

사용자 지시(2026-09-03 20:20): *"이건 모든 Docs에 다 넣으라고"* — [[experiments/2026-09-03_legonly_ab_v2]]
§1b~§1b-4에 넣은 구성을 **전 학습 런 노트에 소급**하고, 앞으로는 자동으로 들어가게 할 것.

붙이는 표 4종(모두 그 런의 config 파싱):

| § | 내용 | 원천 |
|---|---|---|
| §1b(=§1b-1) | 리워드 항목별 weight·왜·어떻게 + 관절별 Kp/Kd/effort | `reward_gains_table.py` |
| §1b-2 | 그룹별 모터·Kp·Kd·effort(stall)·무부하속도·armature·쿨롱·점성·T-N 점수 | env.yaml `actuators` |
| §1b-3 | 모델 XML range·soft 한계·액션 clip·사용가능 창·default | 모델 XML + env.yaml |
| §1b-4 | 이 런의 `PYG_*` 스택 플래그 | `repro/launch_manifest.json` |

### 1-1. ★ soft 한계 공식 정정 (기준본의 오류를 바로잡음)

기준본 §1b-3은 soft 한계를 `XML range의 각 경계 × 0.9`로 적었으나, mjlab 실제 구현은
**중심 ± 0.5 · range · factor**다.

- `mujoco-sim/mjlab/src/mjlab/entity/entity.py:710-714` — `joint_pos_mean ∓ 0.5·joint_pos_range·factor`
- `.../asset_zoo/robots/pygmalion/pygmalion_constants.py:841` `safe_target_clip()` — **동일 산술**

대칭 관절은 두 식이 같지만 비대칭 관절은 갈린다. 무릎 `[0, 120]`의 soft 한계는
**`[6, 114]`이지 `[0, 108]`이 아니다**. 그리고 이 값은 기준본이 "액션 clip" 열에 이미 적어 둔
바로 그 숫자다 — 즉 `PYG_SAFE_TARGET_CLIP=1`인 런에서 **soft 한계 = 액션 clip**이고, 정책이
통과하는 클램프와 시뮬레이터가 강제하는 클램프는 하나의 계약이다. 도구는 올바른 식을 쓰고,
기준본도 도구 출력으로 교체했다(사용자 승인 2026-09-03).

## 2. 인벤토리 (111 노트)

| 분류 | 수 | 처리 |
|---|--:|---|
| 학습 런 노트 (런 디렉토리 확정) | **103** | §1b~§1b-4 생성 삽입 |
| 종합/비교/계획 노트 | 8 | 각 런 노트를 가리키는 포인터 블록 |
| 런 디렉토리 소실 | **0** | — |
| 모델 미해석 | **0** | — |

### 2-1. 모델 XML 해석 방식 (103 런 노트)

| 출처 | 수 | 권위도 |
|---|--:|---|
| 런 디렉토리 `repro/` 스냅샷 | 36 | ★ 그 런이 실제로 로드한 파일 |
| IsaacLab `spawn.usd_path` → 변환원 MJCF | 4 | ★ env.yaml이 경로를 직접 기록 |
| 이 시기 `pygmalion_constants._XML_NAME` 기본 분기 (`pygmalion.xml`) | 28 | 근거 문장 inline |
| v3 printed 계열 (`v3_printed_loop`/`v3_printed`) | 18 | 근거 문장 inline |
| 노트 선언 `PYG_HIP_CANT30=1` → `pygmalion_cant30.xml` | 4 | 노트 선언 |
| 노트 선언 `PYG_ROLLOFF30=1` / `PYG_HIP_CANT20=1` | 2 / 2 | 노트 선언 |
| 노트 선언 `PYG_MODEL_V4=1` → `pygmalion_v4_printed_loop.xml` | 3 | 노트 선언 |
| v3/v4 printed 폐루프 **계열**(ROM 확정, 질량 미해석) | 6 | §5 참조 |
| **합계** | **103** | |

귀속의 객관 근거:
- **July 계열**: 그 시기 코드의 기본 분기가 `pygmalion.xml`(`PYG_V2`/`CANT`/`ROLLOFF` 미설정 시).
  메모리 확정사항 *"hip_roll 내전 하드스톱 +25° / 외전 −45° 유지 (2026-07-13 gen21)"* 가
  이 파일의 range와 일치 → 교차검증.
- **August AB/RP**: `pygmalion_v4_printed_loop.xml`의 파일 생성 시각이 **2026-08-26 21:22**.
  그 이전에 시작된 런은 v4를 로드할 수 없다 → v3 귀속의 **객관 상한**.

### 2-2. `PYG_*` 플래그(§1b-4) 출처

| 출처 | 수 |
|---|--:|
| `repro/launch_manifest.json` (권위) | 6 |
| 노트 본문/실행 명령에서 추출(라벨 명시) | 47 |
| 기록 없음 → "원본 설정 소실" 명시 | 50 |

플래그가 소실된 50건은 **플래그만** 소실이고, 리워드 가중치·게인·ROM은 런 config 파싱으로
확정되어 있다(§1b~§1b-3).

## 3. 진행 로그

| 시각 | 처리 | 결과 |
|---|---|---|
| 09-03 21:0x | `run_spec_tables.py` 신규 작성 | v30/v3/July-serial/IsaacLab 4개 시대 출력 검증 |
| 09-03 21:1x | `backfill_spec_tables.py` 신규 작성 | `--inventory` 111/111 매핑, 미매핑 0 |
| 09-03 21:2x | soft 한계 공식 오류 발견·정정 | 무릎 `[0,108]`→`[6,114]`, 기준본 재생성 |
| 09-03 21:3x | 전 노트 소급 삽입 | 103 런 노트 + 8 포인터, 재실행 시 103건 skip(멱등 확인) |
| 09-03 21:4x | §1b 표가 "다른 노트 참조"뿐이던 16건 재생성 | `--b1-sub` 모드로 중복 H2 없이 실수치 삽입 |
| 09-03 21:5x | 자동화(런처 2곳·스킬·audit 경고) | §4 |
| 09-03 21:5x | Quartz 렌더 확인 | `/experiments/2026-09-03_legonly_ab_v2` 200, 표 8개, ROM 16행 정상 |

## 4. 자동화 변경점

1. **`mujoco-sim/mjlab/analysis/run_spec_tables.py`** (신규) — 표 4종 생성기. 모델 해석 4단계
   (repro 스냅샷 → manifest `PYG_MODEL_TAG` → 호출자 지정+근거 → IsaacLab usd_path),
   실패 시 **"모델 미해석"** 명시(조용한 생략 금지). `<!-- SPEC-TABLES:BEGIN/END -->` 마커로
   **멱등**, `--dry-run`/`--force`/`--p2`/`--with-1b`/`--b1-sub` 지원.
2. **`run_v2_scratch.py`** — `record_spec_tables()` 추가, **P1 종료 시**와 **P2 종료 시**(P1+P2 대조)
   자동 호출. 예외는 절대 학습을 죽이지 않는다(경고만).
3. **`pygmalion_locomotion/scripts/run_training.sh`** — 리포트 생성 뒤 **(5/5) SPEC TABLES** 단계 추가.
4. **`.claude/skills/experiment-note/SKILL.md`** — §1 표에 §1b-2/3/4 필수 행 추가 + §1-1에
   "손으로 쓰지 않는다" 실행법·체크리스트, soft 한계 공식 명시.
   ⚠ `.claude/`는 `.gitignore` 31행에서 제외되므로 이 변경은 **커밋에 포함되지 않는다**(디스크에만
   존재). 다른 머신/클론에서는 스킬을 다시 적용해야 한다.
5. **`pygmalion_locomotion/scripts/audit_notes.sh`** — (7) **경고**(블록 아님): 학습 런 노트에
   §1b-2가 없으면 stderr로 알리고 고치는 명령을 함께 출력. 블록하지 않는 이유는 신규 노트를
   런처가 자동으로 채우므로 학습 중인 노트에 대해 세션을 헛되이 붙잡지 않기 위해서다.
6. **`tools/notes/backfill_spec_tables.py`** (신규) — 소급/점검 드라이버 + 인벤토리 표 출력.

## 5. 미해석·주의 목록 (추측으로 채우지 않은 것)

### 5-1. v3/v4 귀속 불가 6런 — ROM은 확정, **질량만** 미해석
`bundleE1_AB`(08-26 21:51, 08-27 03:46) · `bundleP1_AB` · `bundleP1s2_AB` · `bundleP1s3_AB` ·
`bundleD1s2_AB`. v4 XML 생성(08-26 21:22) 이후에 시작됐고 노트에 `PYG_MODEL_V4` 언급이 없다.
`pygmalion_v3_printed_loop.xml`과 `pygmalion_v4_printed_loop.xml`은 **관절 range가 완전히 동일**
하므로 §1b-3 ROM 표는 확정이고, 다른 것은 질량(v3 35.35 kg / v4 31.316 kg)뿐이다 — 노트에 그렇게 적었다.

### 5-2. XML 파일 최신성 경고 32건
런 시작 이후에 모델 XML이 수정된 경우(예: `pygmalion_v3_printed_loop.xml` 2026-08-26 20:36 수정 →
08-23/24 AB 런은 그 이전 버전 사용). 해당 노트의 §1b-3에 **"이 값은 현재 파일 기준"** 주의 문단이
자동으로 붙는다. 대상: 6월 IsaacLab 6건 · 7월 mjlab 12건 · 8월 AB 14건.

### 5-3. IsaacLab 시대 모델은 좌우 비대칭이었다 (부수 발견)
6월 런의 `repro/robot.xml` 스냅샷 기준: **R_hip_yaw ±40° vs L ±50° · R_knee −125° vs L −140° ·
R_toe −45° vs L −50°**. 좌우 대칭을 가정한 그 시대 분석이 있다면 재검토 대상이다.
(v2 이후 모델에서는 사라졌고, v30 proxyfix는 의도된 미러축이다.)

### 5-4. 종합 노트 8건
[[experiments/INDEX]] · `sweep_gear_ratio` · `2026-06-30to07-07_pre-flat25_backfill` ·
`2026-07-09to10_superseded_runs` · `2026-07-11_bentinit_ab_plan` · `2026-07-12_bentinit_ab_result` ·
`2026-08-26_ankleAB_vs_RP_comparison` · `2026-08-28_ab_ankle_usage_audit` —
단일 런 config가 없으므로 표 대신 각 런 노트를 가리키는 포인터 블록을 넣었다.

## 6. 상태

**완료** (2026-09-03).

| 커밋 | 범위 |
|---|---|
| mjlab `72b9f4c4` | `analysis/run_spec_tables.py`(신규) · `analysis/run_v2_scratch.py`(P1/P2 종료 훅) |
| parent `210b708` | 노트 111건 · `docs/122` · registry · 브리핑 · `tools/notes/backfill_spec_tables.py` · `run_training.sh` · `audit_notes.sh` · mjlab gitlink 범프 |

재점검: `python3 tools/notes/backfill_spec_tables.py --inventory`
(전 노트 재생성이 필요하면 `--force`; 새 런은 런처가 자동으로 넣으므로 손댈 필요 없다)
