# 06 · 키보드 텔레오프 + HUD

> [!abstract] 목표
> 학습된 폴리시를 키보드로 조작하며(cmd_vel), 실시간 HUD로 관절토크·발GRF·베이스 반력을 보고,
> 원할 때 CSV/npz로 로깅한다. 평지/계단/울퉁불퉁/경사에서 직접 몰아본다.

---

## 어디서 / 어떻게
```bash
python scripts/play_keyboard.py --task Pygmalion-Velocity-Flat-Play-v0 \
    --checkpoint logs/rsl_rl/pygmalion_flat/<run>/model_xxx.pt --mass_scale 1.0
# 계단/울퉁불퉁/경사를 직접 걸으려면:
python scripts/play_keyboard.py --task Pygmalion-Velocity-Rough-Play-v0 --checkpoint <ckpt>
```

## 키 매핑 (★ WASD — play_keyboard.py에서 Se2Keyboard 기본 NUMPAD를 WASD로 오버라이드)
| 키 | 기능 |
|---|---|
| **W / S** | 전/후진 (vx) |
| **A / D** | 좌/우 이동 strafe (vy) |
| **Q / E** | 좌/우 회전 (wz) |
| L | 명령 0 |
| **R** | 로깅 시작/정지 (정지 시 자동 저장) |
| **P** | 외란 push (옆으로 밀기) |
| **[ / ]** | 로봇 질량 −/+ 5% |
| ESC | 종료 |
> 구현: `kbd._INPUT_KEY_MAPPING`을 W/A/S/D/Q/E로 교체(생성 직후). isaaclab 무수정.

## 가속 + 댐핑 (hold-to-accelerate)
- **누르고 있으면 가속**: `cur += dir·accel·dt`, 정책 명령범위(`cmd_term.cfg.ranges`)의 최대속도까지. 최대도달 ~`T_TO_MAX`=1.8s.
- **떼면 댐핑**: 지수감쇠 `cur *= exp(-dt/τ)`, `τ=0.35s`로 부드럽게 0으로 (deadzone 2%).
- 최대속도는 로드된 정책의 `cfg.ranges`에 자동 정합(평지 정책: vx 2.0/yaw 1.57). 콘솔에 `hold-to-accelerate: max(vx,vy,wz)=[...]` 출력.

## HUD가 보여주는 것 (시계열 plot)
- cmd (vx,vy,wz), base 높이, 총질량
- **관절별 토크 util% 시계열 그래프** + 가로 기준선(정격33%/80%/peak100%), 막대 색상=안전도(초록/노랑/주황/빨강)
- 발별 GRF [N]·베이스 반력 [N] 시계열
- 3D 뷰: 발에 GRF 화살표
- ⚠️ 명령 화살표(debug_vis)는 GUI에서 device 버그로 OFF (학습영상에선 ON)

> HUD는 `omni.ui` 패널 + debug-draw. GUI가 없으면 자동 no-op(로깅은 독립적으로 동작).

## 지형에 대하여
- 지형은 env 생성 시 결정되므로 **태스크로 선택**(Flat vs Rough). Rough 태스크엔 평지·계단(up/down)·
  울퉁불퉁·경사 서브터레인이 한 그리드에 있어, 로봇을 그 위로 몰며 각 지형을 체험·측정할 수 있다.

## 검증 / 스크린샷
- WASD로 전진 시 로봇이 추종해 걷고, HUD 토크/GRF가 갱신, R로 CSV 생성.
- `![](assets/06_teleop_hud.png)`

## 다음 노트
- [[07_measurement]]
