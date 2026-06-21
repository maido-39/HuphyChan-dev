# 무릎 생체역학 — 검증 발췌 (학술조사 wsx14ecd0)

> 출처: 워크플로우 wsx14ecd0가 원문 fetch·검증. wiki: [[30_knee_biomechanics]].

- 무릎 **굴곡 135°·신전 0°**(정상 ROM) — AAOS ROM 표(Hendriks et al., PRS Global Open Suppl. PDF) · verified
- 무릎 = **modified hinge, 1 DOF, 역관절 불가**, 신전 ~0° 하드스톱 — StatPearls [NBK518967](https://www.ncbi.nlm.nih.gov/books/NBK518967/)·[NBK500017](https://www.ncbi.nlm.nih.gov/books/NBK500017/) · verified
- 과신전: 선수 평균 **−5°(남)/−6°(여)**; **>5° genu recurvatum** — [PMC11608511](https://pmc.ncbi.nlm.nih.gov/articles/PMC11608511/) verified; **>10° 병리·>15° 수술** — ScienceInsights · verified(단일출처)
- **loading-response 무릎 굴곡 ~15-20°**(초기 stance 2-12%, eccentric quad 흡수); **swing peak ~60°** — AAPM&R·Competitive Edge PT · verified(2차; Perry 원전 미fetch)
- **screw-home**: 종말 신전서 경골 외회전 ~10°/마지막 30°(NASM) → 인대 close-packed 락 — verified(15°/20° 대체수치 미검증)
- **heel-strike COM 방향전환 18.5±3.0°**; **collision 음의일 0.205±0.032 J/kg·step·push-off 0.242±0.043** — Adamczyk&Kuo 2009 JEB [PMC2726857](https://pmc.ncbi.nlm.nih.gov/articles/PMC2726857/) · verified
- collision 음의일 ∝ 걸음길이⁴(r² 0.95-0.96), 전이 ~2/3 대사 — Donelan 2002 ([[raw/kuo-canon-numbers]]) · verified
- 깊은 BHBK crouch = 대사 **+50-60%** — Carey&Crompton 2005 · verified(초록)
- **Cassie** 무릎 −164~−37°(과신전 0, bird) · **H1** nominal 무릎 0.3rad(굴곡) — MuJoCo/공식 · verified
- legged_gym `_reward_stand_still`(default 자세로)·`_reward_dof_pos_limits`(한계 접근 벌점) = 무릎 락/park 표준 fix · verified
- **PROJECT FACT**: robot.urdf L knee 굴곡 −140°/과신전 +10°, R knee −125°/+10°; hip_pitch L±50°/R±40°(비대칭). **live nominal(robstride_biped.yaml): knee −0.40rad·hip_pitch −0.20·ankle +0.20 = 이미 flexed.** dof_pos_limits=발목만·joint_deviation=hip만(무릎 무보상). · verified(파일 직접)
