# -*- coding: utf-8 -*-
"""Reward-term glossary: term -> (what it is, why it is given). Used by make_run_report.py and the retro updater
to build the §2b reward table (이름 / 가중치 / 기여 / 무엇 / 왜) in every experiment note (rule, user 2026-06-29).

Keep WHAT/WHY short (one phrase). Add new terms here as they are introduced (a missing term -> '[작성 필요]')."""

REWARD_GLOSSARY = {
    # --- task tracking ---
    "track_lin_vel_xy_exp": ("명령 선속도(x,y) 추종 exp", "작업 목표: 원하는 속도로 보행"),
    "track_ang_vel_z_exp": ("명령 각속도(yaw) 추종 exp", "작업 목표: 방향 전환 추종"),
    # --- base motion regularizers (G1/stock) ---
    "lin_vel_z_l2": ("수직 속도 penalty", "상하 bounce 억제(보통 0으로 끔)"),
    "ang_vel_xy_l2": ("roll/pitch 각속도 penalty", "몸통 흔들림 억제"),
    "flat_orientation_l2": ("몸통 수평(중력 proj) penalty", "몸통 똑바로 유지"),
    # --- smoothness / actuation ---
    "dof_acc_l2": ("관절 가속도 L2 penalty", "고주파 진동(떨림) 억제 = smooth"),
    "dof_torques_l2": ("관절 토크 L2 penalty", "에너지/토크 절감(과사용 억제)"),
    "dof_pos_limits": ("관절 한계 근접 penalty", "ROM 끝 회피(HW 보호)"),
    "action_rate_l2": ("action 변화율 penalty", "급격한 명령 변화 억제 = smooth"),
    "torque_soft_limit": ("effort 85% 초과 토크 penalty", "모터 가용범위 유지(sim2real/HW)"),
    "torque_soft_limit_ankle": ("ankle_roll 토크 한계 penalty", "포화 ankle_roll offload(열보호)"),
    # --- gait / feet ---
    "feet_air_time": ("발 공중(또는 single-stance) 시간 보상", "보폭/스텝 유도(threshold 미달 시 dead)"),
    "feet_slide": ("접지 발 미끄러짐 penalty", "발 고정(slip 방지)"),
    "feet_distance": ("양발 간격(min/max) penalty", "발 교차(scissoring) 방지"),
    "feet_lateral_sep": ("양발 측방 분리 penalty", "다리 교차(8자) 방지"),
    "feet_swing_height": ("swing 발 목표 clearance 이탈 penalty", "발 들어올리기(까치발/shuffle 억제)"),
    "no_flight": ("양발 동시 공중(flight) penalty", "비행 억제(저충격 하중측정)"),
    "double_support": ("양발 지지 구간 보상", "double-support 겹침(no-flight·안정)"),
    "lateral_foot_placement": ("발 배치가 XcoM 추종 보상", "capture-point 측방 안정(스텝으로 균형)"),
    # --- posture (gaitfix anti-tiptoe set) ---
    "base_height": ("몸통 높이 목표(0.85) L2 penalty", "★ 다리 신전(까치발) 방지 = 근본 자세제약(gaitfix)"),
    "upright": ("몸통 직립 자세 보상", "몸통 똑바로(앞으로 안 숙임)"),
    "foot_flat_orientation": ("발-body 기울기(pitch/roll) penalty", "까치발 직접 억제(증상; 약함)"),
    "foot_roll_flat": ("발-body roll 평탄 penalty", "발 좌우 평탄(균형 하중)"),
    # --- joint deviation ---
    "joint_deviation_hip": ("hip 중립 이탈 penalty", "hip 자세 안정(과회전 억제)"),
    "joint_deviation_hiproll": ("hip_roll 중립 이탈 penalty", "다리 벌어짐/모임 억제"),
    "joint_deviation_ankle": ("ankle 중립 이탈 penalty", "발목 자세 tight 유지(블로그식)"),
    "knee_straight": ("무릎 과신전(straight) penalty", "무릎 굽힘 유지(충격 흡수)"),
    # --- impact / landing (HW 1.5-2.7kN 보호) ---
    "foot_impact_force": ("발 접지력 초과분 penalty", "저충격 착지(HW 파손 보호)"),
    "foot_landing_vel": ("착지 순간 수직속도 penalty", "부드러운 착지(충격 저감)"),
    # --- energy / heel-toe / toe ---
    "power_cot": ("속도정규화 기계적 일률(CoT) 보상", "에너지 효율(stand-still 회피)"),
    "forefoot_cop": ("앞발 CoP 하중 보상", "forefoot rollover 유도"),
    "cop_progression": ("CoP heel→toe 진행 보상", "인간 heel-toe rollover 인코딩"),
    "ankle_pushoff": ("ankle push-off 일(work) 보상", "toe-off 추진력"),
    "gait_reference_tracking": ("사람 gait reference 관절각 추종(contact-phase)", "★ 인간형 gait shape(까치발/shuffle 격파)"),
    "toe_load_stance": ("terminal stance toe 하중 보상", "★ push-off windlass(toe 적시 사용)"),
    # --- termination / contacts ---
    "termination_penalty": ("조기 종료(낙상) penalty", "넘어짐 회피"),
    "undesired_contacts": ("원치 않는 link 접촉 penalty", "무릎/몸통 지면 충돌 회피"),
}


def lookup(term):
    """Return (what, why) for a term; ('[작성 필요]','[작성 필요]') if unknown."""
    g = REWARD_GLOSSARY.get(term)
    return g if g else ("[작성 필요]", "[작성 필요]")


def parse_reward_weights(run_dir):
    """Robust parse of <run_dir>/params/env.yaml rewards -> {term: weight}. Regex (not yaml.safe_load) because
    IsaacLab dumps python-object tags that break safe_load."""
    import os, re
    p = os.path.join(run_dir, "params", "env.yaml")
    if not os.path.exists(p):
        return {}
    txt = open(p).read()
    m = re.search(r"\nrewards:\n(.*?)\n(?=\S)", txt, re.S)   # rewards block until the next col-0 key
    block = m.group(1) if m else ""
    out = {}
    for tm in re.finditer(r"^  ([A-Za-z_0-9]+):\n((?:    .*\n?)+)", block, re.M):
        wm = re.search(r"^    weight:\s*([-+\d.eE]+)", tm.group(2), re.M)
        if wm:
            try:
                out[tm.group(1)] = float(wm.group(1))
            except ValueError:
                pass
    return out
