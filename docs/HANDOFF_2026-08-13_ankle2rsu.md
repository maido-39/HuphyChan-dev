# HANDOFF — 발목 2-RSU 최적화 세션 (2026-08-13)

> 이 문서 하나로 이 세션에서 한 모든 작업을 새 세션에서 이어받을 수 있게 정리. 상세 로그·수식·중간과정은 [[71_ankle_2rsu_optimization_setup]] §9~§12에 있고, 여기는 그걸 빠르게 재구성하기 위한 요약+포인터.

## 0. ★★★ 가장 먼저 할 일 — 백그라운드 프로세스 확인

이 세션에서 띄운 DE(Differential Evolution, 차분진화) 최적화 스윕이 **아직 백그라운드에서 실행 중일 수 있다.** 새 세션 시작하면 바로 확인:

```bash
ps aux | grep ankle_opt_de_v3 | grep -v grep
ls /home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab/analysis/logs/sweep/final_*.json | wc -l
for m in base coupled widebox noswingfoot; do
  echo "$m: $(ls .../analysis/logs/sweep/final_${m}_*.json 2>/dev/null | wc -l)"
done
```

세션 종료 시점 진행상황(2026-08-13 16:02 기준): **base 100/100 완료**, coupled 74/100, widebox 70/100, noswingfoot 17/30 진행중. 프로세스가 살아있으면 그냥 두면 됨(각 드라이버가 목표 도달 시 자동 종료). 죽어있으면 재시작 방법은 §5 참조.

## 1. 이 작업이 뭔가 (배경)

이족보행 로봇 발목을 구동하는 **2-RSU 병렬기구**(모터 2개 + 크랭크·로드로 원격 구동, 실제 발목 pitch·roll 관절은 별도) 설계 최적화. 9개 치수 파라미터(크랭크 길이 A_r/B_r, 로드 길이 A_L/B_L, 로드 발측 부착위치 RP_B/RP_r/RP_h, 모터 정강이측 위치 A_h/B2RP)를 실측 하중데이터(13,503샘플, 평지+험지) 기준으로 DE 알고리즘이 탐색. 목적함수 = 토크·속도·로드축력·요동각 등 여러 마진 중 **최소값**(min-margin, 하나라도 마이너스면 불가능).

## 2. 세션 중 발견한 것들 (시간순)

### 2a. 부호 버그 (docs §9~§10)
기구모델의 pitch 부호가 로봇 실제 부호와 반대로 들어가고 있었음. 로봇 MJCF 관절체인에서 회전행렬을 직접 재유도(`R(tp,tr)=R_pitch(tp)@R_roll(tr)`)하고 MuJoCo FK로 pitch+roll 동시자세 검증 후 수정.

### 2b. swing_foot 여각 버그 (docs §10c)
발측 볼조인트 요동각 공식이 `arcsin`(회전평면 이탈각 개념, 크랭크측엔 맞음)을 쓰고 있었는데 발측은 진짜 원뿔각(boresight cone) 개념이라 `arccos`여야 했음 — 여각(90°−진짜각)을 계산하고 있었던 것. 손계산 검산으로 발견.

**두 버그를 모두 고친 결과**: 이전까지 "swing_foot 3.8% 여유로 겨우 통과"라고 봤던 게 완전히 틀렸고, 실제로는 확정 박스로 swing_foot≤20° 요동각 한도를 **ROM 전역에서 만족 불가능** — 실측 자세 재생 기준 99.1%가 위반, 중앙값 39.7°(한도의 2배).

### 2c. 인프라 버그 3종 (100시드 스윕 준비 중 발견)
1. BLAS 스레드 과다구독(numpy가 프로세스당 전코어 사용 → 8워커×8스레드로 load avg 80+) → `OMP_NUM_THREADS=1` 등으로 해결.
2. 워커마다 265MB CSV 재파싱 → 프로세스당 RSS 1.8GB, 스왑 가득참 → G1 배열 사전 캐시(`.npz`, 2.2MB)로 해결(RSS 115MB로 감소).
3. 평가함수 서브샘플링 시도 중 `.max()` 기반 지표(torque_pk 등)에서 균일랜덤 서브샘플이 진짜 최댓값 표본을 누락 → percentile용(비편향)과 peak용(원자료 상위15% 합집합) 풀을 분리해 해결.

### 2d. 100시드 교차검증 스윕 (docs §11)
사용자 요청: 최소 100시드로 전역수렴 확인 + Q1~Q5 5개 설계질문. base 100/100 완료, **표준편차 0.02pp** — 통계적으로 확정된 전역최적점.

**5개 질문 답 (요약, 상세수치는 §11b~§11f)**:
- Q1(전역수렴+term별 iter): 수렴 확인됨. swing_foot만 세대내내 음수(binding), 나머지는 다 양수로 수렴 — DE가 다른 항목은 다 풀어내는데 swing_foot 하나만 박스 안에서 불가능.
- Q2(A_h=RP_r 결합): 성능상 거의 공짜(base와 0.01pp 차이) — 둘 다 어차피 하한(35)에 pinned.
- Q3(A_h·RP_r∈[40,45]): base보다 4.5pp 더 나쁨 — 최적점을 원래 위치(하한)에서 강제로 떼어놓는 효과.
- Q4(로드 축력): 여유 충분(peak도 예산의 32%만 사용, 68~69% 마진) — 병목 아님.
- Q5(swing_foot 유무 비교): 포함시 −168.5%(불가능), 제외시 +36.6%(충분히 가능) — **약 205pp가 swing_foot 하나의 비용**. 다른 항목은 swing_foot 유무와 무관하게 원래 여유 충분했음.

### 2e. Roll×Pitch 전영역 요동각 범위 + 애니메이션 (docs §11h)
- **AB(크랭크측)**: 전 영역에서 최대 1.5~4.2°만 사용 — 전혀 문제없음.
- **RP(발측=swing_foot)**: 중앙값부터 이미 24~26°(한도 20° 초과), 최악점 54~61°.
- `analysis/ankle_sweep_animation.py`로 pitch×roll 전영역 순회 애니메이션 제작·사용자에게 전달 완료 (`docs/mujoco/assets/ankle_ballswing_sweep.mp4`).

### 2f. 왜 중립자세부터 20°+ 인가 (사용자 추가 질문, docs 미기록 — 아래 §4 참조)
파라미터별 민감도 분석 결과 **A_h는 거의 무관**(변화폭 0.2° 이내). 진짜 원인은 **RP_B**(발측 앞뒤 부착위치): 크랭크 축(모터, 정강이측)은 좌우·상하 오프셋만 있고 **앞뒤(fore-aft) 오프셋이 아예 0**인데, 앵커(로드 발측 부착점)는 RP_B(50~80mm)만큼 앞뒤로 떨어져 있어서 중립자세에서도 로드가 이 간극을 메우려고 이미 기울어짐.

**발견**: 설계툴(`ankle.html`)엔 원래 모터 앞뒤 트림 파라미터(`ax_x`, ±80mm)가 있었는데 **우리 최적화기(v2/v3/v4) 전부 이걸 0으로 고정**하고 한 번도 자유변수로 안 썼음. 이 트림을 넣으면:
- 중립자세 요동각: 20°→9~15° (많이 개선)
- **전영역 최악값**: 50.8°→**46.3°**(30mm 근방이 최적, 9% 개선, 그 이상은 오히려 악화)

→ **사용자에게 "이걸 10번째 최적화변수로 추가할까요?" 질문했고, 아직 답 안 받음(대기 중).**

### 2g. 참고논문 검토 + v4 재매개변수화 시도 (docs §12 — 이 세션 내 신설, 아직 미완성 기록)
사용자가 링크한 논문(Cervettini et al., "A Framework for Optimal Ankle Design of Humanoid Robots", IEEE Humanoids 2025, arXiv:2509.16469) 읽음. 핵심 아이디어: 크랭크·로드 길이를 "무작위로 골라서 검사 후 버리기" 대신, **원하는 동작영역 전체에서 항상 IK가 닫히도록 길이 허용구간을 먼저 계산**하고 그 안에서 0~1 보조변수(γ,δ)로 탐색하는 재매개변수화.

논문 수식은 우리 기구(측면 오프셋 항 D_x 추가로 존재)에 안 맞아서 **직접 재유도**해서 `ankle_opt_de_v4.py`로 구현. 검증:
- 무작위 샘플 기준 ROM-닫힘 통과율: v3(기존) 1/300 → v4(신규) 4/300 (4배 개선하지만 절대치는 여전히 낮음)
- 실제 DE 1회 비교런(`v4test`, seed 9001): **v3와 거의 동일한 최종점(−168.55% vs v3의 −168.5X%)에 수렴, gen당 시간은 오히려 더 느림**(interval 계산 오버헤드) → **v4는 실질적 개선 없음으로 결론, 더 이상 추진 안 함**.

## 3. 파일 위치 총정리

| 목적 | 경로 |
|---|---|
| 메인 문서(전체 과정·수식·§0~§12) | `docs/71_ankle_2rsu_optimization_setup.md` |
| 최적화기(현재 정본, SS10 수정 반영) | `mujoco-sim/mjlab/analysis/ankle_opt_de_v2.py` |
| 100시드 스윕용(margin term 전체 로깅+MODE 지원) | `mujoco-sim/mjlab/analysis/ankle_opt_de_v3.py` |
| 스윕 드라이버(병렬 시드 오케스트레이션) | `mujoco-sim/mjlab/analysis/run_sweep.py` |
| v4(재매개변수화, 결론: 미채택) | `mujoco-sim/mjlab/analysis/ankle_opt_de_v4.py` |
| 스윕 결과/로그 | `mujoco-sim/mjlab/analysis/logs/sweep/` (`final_<mode>_<tag>.json`=최종결과, `gens_<mode>_<tag>.jsonl`=세대별 전체 margin 로그) |
| G1(실기 텔레메트리) 캐시(파싱 속도용) | `mujoco-sim/mjlab/analysis/logs/g1_cache.npz` |
| 로드 축력 분석 스크립트+데이터 | `analysis/rod_wrench_analysis.py`, `analysis/logs/sweep/rod_wrench_data.npz` |
| 리포트 플롯 생성 스크립트 | `analysis/sweep_report_plots.py` (재실행하면 `docs/mujoco/assets/sweep_*.png` 전부 갱신) |
| 3D 렌더(정지) | `analysis/ankle_3d_viz_v2.py` → `docs/mujoco/assets/ankle_3d_geometry_v2_worstcase.png` |
| 스윕 애니메이션(영상) | `analysis/ankle_sweep_animation.py` → `docs/mujoco/assets/ankle_ballswing_sweep.mp4` |

## 4. 대기 중인 사용자 결정 (다음 세션에서 확인할 것)

1. **모터 정강이측 앞뒤 트림(ax_y/ax_x, ±80mm)을 10번째 최적화 변수로 추가할지** — 최악 요동각 9% 개선(50.8°→46.3°) 확인됨, 아직 사용자 답 없음(§2f).
2. swing_foot 근본 해결책 4가지 옵션 중 어느 것을 검토할지 (§10f): ①RP_B/RP_r 박스 하한 완화, ②B2RP 상한 완화, ③볼조인트 요동각 한도(20°) 자체 완화, ④기구 배치 재설계.
3. 100시드 스윕(coupled/widebox/noswingfoot) 완료까지 계속 모니터링할지, 중간에 충분하다고 판단하고 마무리할지.

## 5. 스윕이 죽어있을 경우 재시작 방법

```bash
cd /home/syaro/MikuchanRemote/Human-Pygmalion/mujoco-sim/mjlab
# 남은 시드만 이어서 돌리려면 run_sweep.py의 offset을 이미 완료된 최대 tag 번호+1로 조정 필요
# (완료분 재실행 방지). 예: coupled가 6000~6073까지 있으면 offset=6074부터.
nohup .venv/bin/python3 -u analysis/run_sweep.py coupled <남은수> 2 6074 > analysis/logs/sweep/driver_coupled.log 2>&1 &
disown
```
주의: 반드시 `OMP_NUM_THREADS=1` 등 환경변수가 걸려있는지 확인(§2c 버그 재발 방지) — `run_sweep.py`의 `launch()` 함수에 이미 박혀있음, 그대로 쓰면 안전.

## 6. 최종 결론 한 줄 요약

**확정 설계 박스로는 발측 볼조인트 요동각(swing_foot) 조건을 물리적으로 만족할 수 없다** — 100시드로 통계적으로 확정된 결론(std 0.02pp). 로드 강도·모터 토크·속도는 전부 여유 충분. 병목은 순전히 이 기구 배치가 요구하는 요동각 크기이며, §4의 4가지 옵션 중 하나를 선택해야 진전 가능. 모터 위치에 앞뒤 트림을 추가하면 부분적 개선(9%)은 가능하나 근본 해결은 아님.

---
[[71_ankle_2rsu_optimization_setup]] (전체 상세)
