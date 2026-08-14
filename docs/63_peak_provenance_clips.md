# 63 · Peak 발생 상황 영상 (provenance clips) — 설계값이 어디서 나왔나

> 2026-07-10. 사용자 요구: "peak 측정 시점의 gait·최악값의 출처를 영상으로 확인 가능하게." 도구: [analysis/peak_clips.py](../mujoco-sim/mjlab/analysis/peak_clips.py) — 관절별 |τ| peak 순간 **±2초, 2× 슬로모션** 클립을 |τ| 내림차순으로 이어붙인 몽타주. 캡션=관절·peak값·발생시각·Δt 카운트다운·명령 방향, **peak 관절 구 1.7× 확대**, peak 순간 ★PEAK★ 플래시, 색=부하 포화(회<노<주<빨), 실제 측정 지형 위 재생. 인터랙티브 대응물: `analysis/peak_pose_viz.py`(viser :8083, 각도-bin별 peak + wrench 수치표).

## 영상
**공칭(nom) 근거 — P2-final flat 정식측정 (p2_long, 18k steps·133명령·학습DR 일치)**
![[p2_long_peak_clips.mp4]]

**최악(worst) 근거 — ⚠구 blind-rough 캠페인 (worstcase_rough, 7/1) — 부검용**
![[worstcase_rough_peak_clips.mp4]]

**★최악(worst) 신규 정식 — rough P2 최종정책 in-DR wide-DR 캠페인 (p2r_final_wc, 7/10)**
![[p2r_final_wc_peak_clips.mp4]]
- 4절 설계기의 현행 worst 데이터 출처. 구 캠페인 대비 무릎 ω p99 28.9→10.4 rad/s, 심굴곡 bin 소멸(−77.5°까지만) — peak 상황이 정상 보행권으로 정상화됨. 기구·베어링 설계표: [[wds_p2r_final_wc]] (knee F_r p99 813N/peak 2958N 등, 관절프레임 분해+동시 6벡터).

## Peak 목록 (클립 순서 = 영상 챕터)
| p2_long (nom) | N·m | | worstcase_rough | N·m |
|---|--:|---|---|--:|
| L_hip_roll | 120 | | L_hip_pitch | **120=클립** |
| R_knee | 120 | | L_hip_roll | **120=클립** |
| L_hip_pitch | 111 | | L_knee | **120=클립** |
| R_hip_pitch | 82 | | R_hip_pitch | **120=클립** |
| R_ankle_pitch | 80 | | R_hip_roll | **120=클립** |
| R_hip_roll | 79 | | R_knee | **120=클립** |
| L_ankle_pitch | 76 | | L/R_hip_yaw | **60=클립** |
| L_knee | 72 | | L/R_ankle_pitch | **60=클립** |
| L/R_hip_yaw | 41/32 | | L/R_ankle_roll | **14=클립** |
| L/R_ankle_roll | 23/21 | | | |

## 관찰 (영상으로 검증 가능해진 것)
1. **worst의 peak는 12관절 전부 모터 effort 한계값 그 자체** — "수요"가 아니라 "모터가 낼 수 있었던 최대치"(검열 수요, [[60_fourbar_optimizer_research]] §9 파워 포락선 논증의 영상 증거). 클립을 보면 다수가 급후진(BACKWARD 2.0 — 현 정책 학습범위 밖 명령)·경사 충돌·회복 과도 중 발생.
2. **p2_long(nom)의 peak는 상황이 건전** — 정상 보행 사이클 내 지지상/방향전환에서 발생하며 hip_roll·knee만 120 순간 접촉.
3. 이 노트의 worst 영상은 **구세대 캠페인의 부검용** — rough P2 최종정책의 wide-DR 정식 캠페인 완료 시 동일 방식으로 `<new>_peak_clips.mp4`를 추가하고 4절 설계기 worst 데이터도 교체 예정.

## 재현
```bash
MUJOCO_GL=egl uv run python analysis/peak_clips.py --npz analysis/out/<tag>.npz --tag <tag> --out ../../docs/mujoco/assets
```
