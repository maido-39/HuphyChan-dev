# 90. 논문 자료 지도 — 휴머노이드 설계·최적화 과정 (2026-08-16 작성, 세션 정리용)

**용도**: "RL 정책을 하중 발생기로 쓰는 휴머노이드 하드웨어 설계·최적화" 논문을 쓸 때,
어느 docs에 어떤 소재·수치·그림이 있는지의 지도. 각 항목의 **최신 판정은 해당 문서가 권위**
(이 지도는 포인터일 뿐, 결론을 재서술하지 않는다 — 특히 79~88은 제목 기준 포인터).

## §1 서사 골격 (논문 장 구성 후보)

1. **문제 설정**: 시뮬레이션 RL 보행 정책의 실측 부하로 하드웨어를 사이징하는 파이프라인.
   낙상·최악하중을 정적 사이징이 아닌 계층 스택으로 다루는 관점 — [[56_humanoid_impact_fall_load_handling]]
2. **하중 발생기로서의 RL 정책**: 측정 프로토콜(fc/fcp·지형분리·텔레포트 v2), 설계값 규율
   (열=RMS·순시=in-DR P99·구조=P99×SF·raw peak 사이징 금지) — [[62_policy_reward_design_review]] ·
   [[64_joint_bearing_design_inputs]](§7b 링크로컬 렌치, §8i 모멘트 기준점 버그 발견·정정) ·
   [[65_design_value_uncertainty]] · [[63_peak_provenance_clips]](피크는 클립·단발충격 오염)
3. **기구 치수 최적화 (발목 2-RSU 사례연구)**: Deb 사전식 DE + 실측 수요풀 + 인간보행 커버 하드제약,
   18시드/PCA 전역성 검증, 3중 제약 코너 해석, 레드팀 반증 — [[71_ankle_2rsu_optimization_setup]] ·
   [[72_ankle_2rsu_objective_spec_and_direction]] · [[74_ankle_2rsu_process_spec]] ·
   [[76_ankle_2rsu_design_summary]](확정 파라미터·CAD 대조·"왜 최적인가") ·
   [[75_human_ankle_alignment]](5개 공개 보행 데이터셋 정렬) · [[60_fourbar_optimizer_research]](Deb 3규칙 채택 근거)
4. **폐형식·파라메트릭 CAD 통합**: 크랭크각 닫힌 해(오차 2.8e-14°, 분기·단조성 증명) →
   Fusion 수식 → CAD 파라미터 9/9 실측일치 — [[76_ankle_2rsu_design_summary]] §10c ·
   `docs/fusion_ankle_phi_expressions.md` · [[83_fusion360_measurement_spec]] · [[88_cad_placeholder_mass_rom]]
5. **안전 아키텍처(ROM 보호)**: 크랭크 독립 스톱의 원리적 한계(직사각형 ⊋ 상관 +0.713 띠) →
   RP 짐벌 롤 스톱 선접촉 설계, 실측 스톱잔여모멘트 기반 사이징, 요동각 허용치 민감도(28°면 해소)
   — [[78_ankle_stopper_derivation]] 전체(§8 기하 논증, §12~§13 하중 정정·사이징, §15 민감도)
6. **구조 검증 캠페인(FEA)**: 링크단위 어셈블리·방향 포락(단위해 중첩+부호조합 전수)·
   베어링시트/볼트풋프린트 BC·구멍 휴리스틱 볼트검출(365개)·알루미늄 탭 전수판정·
   메시수렴·적대적 레드팀에 의한 판정 정정 이력 — [[77_structural_fea_lightweighting]](§1~§25) ·
   `tools/fea/` (femlib·envelope·detect_bolts·thread_check)
7. **재료 대체·경량화**: PLA 스크리닝/하이브리드 대체/내부부품 판정 — [[79_pla_material_screen]] ·
   [[80_hybrid_pla_substitution]] · [[85_pla_triage_simple_walking]] · [[86_internal_parts_pla_walking]]
8. **모델-실물 일관성**: RL 모델 질량 vs CAD 실측, 자리표시자 질량·ROM, 로봇모델 v2 —
   [[81_rl_model_vs_cad_mass]] · [[82_final_design_mass_review]] · [[87_robot_model_v2]]
9. **방법론 자체가 기여**: 다중 에이전트 분해→적대검증→합성 구조(직급 페르소나 무효 실증),
   레드팀이 정량 판정을 뒤집은 사례들(클레비스 77→194 MPa, 경량화 철회, PLA 5/6 DISPUTED)
   — [[42_research_methodology]] · 77 §9/§24 · 85 v2

## §2 그림·데이터 자산 (재생성 가능성 포함)

| 자산 | 위치 | 재생성 |
|---|---|---|
| 발목 최적화 검증(18시드·PCA·앙각·거울상·인간정렬) | `docs/mujoco/assets/ankle_v8_*` 등 (76 §3 카탈로그) | mjlab `analysis/ankle_opt_*` |
| ROM 스윕 영상 | `ankle_v9_rom_sweep.mp4` | `ankle_v9_rom_video.py` |
| 스토퍼 ROM 트레이드 | `ankle_stopper_rom_trim.png` | 유도과정 78 §8·§15 |
| 스톱잔여모멘트·사이징 | `docs/img/ankle_stop_residual.png` 등 | `tools/ankle_stop*.py` |
| FEA 셋업/결과 렌더·인터랙티브 | `fea_setup_*.png` · `:8091/fea_viewer.html`·`link_setup_viewer.html` | `tools/fea/merge_*.py` |
| CAD 인터랙티브(실메시·수요 오버레이·볼트) | `:8091/ankle_cad_viewer.html` (데이터 json 리포 내) | `tools/fea/`·`analysis/` |
| 실측 렌치·수요풀 | `analysis/out/*_fc.npz` · wrench_studio cache v41 | 측정 프로토콜 (64·62) |

## §3 논문 전 메워야 할 갭 (이 세션 시점 인지분 — 최신은 각 문서 §미결 참조)

1. **freeze 재측정**: 현 최적화·포락은 구정책 스크리닝 — 재학습(effort-81) 후 fc/fcp 재측정 →
   v9 재실행이 정식 수치 (74 §6)
2. **발목 모멘트 기준점 재계산**: §8i 정정이 발목엔 미적용 — 베어링 모멘트 정격 선정에 필요
3. **sim ROM ≠ 설계 캡** 점유 최악 33 % (78 §14-3) — 스토퍼 정적 판정 프레임의 전제 문제
4. 스토퍼 에너지(충격) 사이징·짐벌 스톱 CAD 반영 (78 §14)
5. FEA 잔여: 각 링크 최신 판정·경량화 재실행은 77 §22~§25가 권위 — 논문에는 "판정 정정 이력"
   자체를 방법론 소재로 쓸 것

관련: [[index]] · [[HANDOFF_2026-08-13_ankle2rsu]] · [[66_experiment_registry]](학습 런 계보)
