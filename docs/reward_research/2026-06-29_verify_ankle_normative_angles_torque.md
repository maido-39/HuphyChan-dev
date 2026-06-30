# Adversarial verify · Ankle normative angles + peak torque claim (human-gait-data source)

> [!question] Claim under test (2026-06-29)
> SOURCE human-gait-data. CLAIM = "Ankle Dorsi/Plantarflexion normative angles and peak torques". Detail asserts a phase-by-phase ankle sagittal trajectory + peak plantarflexor torque 1.5 N·m/kg (~78 N·m @51.8 kg), with action = forefoot_cop/push-off rollover reward + gear 1.3-1.5x or toe spring k=60.

> [!abstract] Verdict: **PARTIALLY supported — supported=true with a load-bearing caveat.**
> The ENGINEERING conclusions are sound and already cross-verified in our [[41_ankle_pitch_pushoff_rs03_underspec]]: peak plantarflexor moment ~1.4-1.5 N·m/kg → ~78 N·m is normative (Winter; clinical 1.25-1.5 N·m/kg measured), heel→toe rollover is the correct human pattern, push-off power peaks in terminal stance, and gear 1.3-1.5x / toe k=60 are defensible offloads. BUT the claim's **phase-by-phase angle timeline is materially WRONG in 3 places**, and one **REF is misattributed/fabricated**. Use the torque + rollover direction; DISCARD the specific angle-vs-%-cycle numbers as written and re-derive from a real normative curve before encoding any tracking target.

## What is WRONG (adversarial findings)

1. **Initial contact angle.** Claim: heel-strike = dorsiflexion ~7-10°. Normative (Perry, AAPM&R, Orthobullets): ankle is at **~neutral (0°)** at initial contact, not 7-10° dorsiflexed. WRONG.

2. **Mid-stance SIGN REVERSED (most serious).** Claim: "mid-stance ~30% = plantarflex ~5-10°". Normative: during mid-stance the tibia rolls forward over the planted foot → ankle **DORSIFLEXES to ~+5 to +10°** (AAPM&R: "about 5 degrees of dorsiflexion"; this is *controlled dorsiflexion*, negative ankle work). The claim has the **sign backwards** — it says plantarflex where humans dorsiflex. This is the single most important error: encoding it as a target would train the OPPOSITE of human mid-stance.

3. **Omits the terminal-stance dorsiflexion PEAK + mistimes push-off.** Claim: "plantarflex begins at ~10%", peak plantarflex 20-25° at 50-60%. Normative: ankle keeps dorsiflexing through stance to a **peak dorsiflexion ~+10° around 45-50%** (terminal stance), THEN rapid plantarflexion ("powered plantarflexion") begins, reaching **peak plantarflexion ~-15 to -20° at toe-off ~60-62%**. So (a) net plantarflexion does NOT begin at 10% — the joint is dorsiflexing 10→50%; (b) push-off peak magnitude is more like **15-20°, not 20-25°**; (c) the claim never mentions the terminal-stance dorsiflexion peak that is the spring-loading event.

4. **REF misattribution (fabricated title).** Claim cites "Huang et al. (2015) 'Mechanical reduction of internal friction in the human ankle' JEB 218, 2709-2717 (PMC4664043)" as the source of 1.5 N·m/kg. PMC4664043 is actually **"Mechanical and energetic consequences of reduced ankle plantar-flexion in human walking"** (Huang, Shorter, Adamczyk, Kuo, JEB 2015). The cited title is wrong, and verified: the paper does **NOT report a 1.5 N·m/kg peak moment** (it studies energetic cost of restricted push-off; ~3.94 J extra metabolic per 1 J ankle work lost). The 1.5 N·m/kg figure traces to **Winter**, not this paper. Use Winter / clinical sources for the torque number, not this citation.

## What is RIGHT (survives the attack)

- **Peak plantarflexor moment ~1.4-1.5 N·m/kg** = normative (clinical measured 1.25-1.5 N·m/kg; Winter). → ~78 N·m @51.8 kg. Consistent with our independent [[41_ankle_pitch_pushoff_rs03_underspec]].
- **Heel→toe CoP rollover, push-off power peak in terminal stance, ankle dominates push-off** (Winter 1983: active plantarflexor push-off, not passive roll-off; coincides with 2nd vertical-GRF peak). Direction of the proposed forefoot_cop / push-off reward is correct.
- **Plantarflex ROM ~25-30°, dorsi ROM ~10°** is roughly right as TOTAL ROM (heel-strike-region transient PF + powered PF down to ~-20° + DF peak +10° → ~30° span). The error is in the *per-phase assignment*, not the total ROM.
- **Swing dorsiflexion ~ toward neutral/slight DF for clearance** — qualitatively right.
- **Gear 1.3-1.5x OR toe k=60** offloads — already our §41 conclusion (1순위 link reduction; toe k=60 = human-matched per Nature Sci Rep 2025).

## Impact on our goal (human-like, low-impact, low-energy load measurement)

- HARMFUL IF the angle timeline is encoded verbatim as a DeepMimic/phase-reference tracking target: items 1-3 (esp. mid-stance sign reversal) would train an anti-human mid-stance and a too-early/too-deep push-off. This directly threatens the human-like + low-energy goal.
- SAFE to adopt: the ~78 N·m torque budget (already in §41/§49 HW sizing) and the heel→toe rollover reward direction. These do not depend on the wrong angle numbers.
- ACTION before implementing task #11 (encode normative joint angles): pull a real normative ankle-angle curve (Winter Table/Appendix, or Perry Fig 8-8) and digitize it, rather than the prose numbers in this claim. Correct skeleton: IC ~0° → LR plantarflex to ~-5° (foot-flat ~7-12%) → controlled DF rising → terminal-stance peak DF ~+10° @~48% → powered PF to ~-15..-20° @toe-off ~62% → swing DF back to ~0..neutral for clearance.

## Refs (verified this session)
- Clinical peak ankle PF moment 1.25-1.5 N·m/kg: https://pmc.ncbi.nlm.nih.gov/articles/PMC4664043/ context + biomedical-engineering-online 13:19 (PMC3943831)
- Winter 1983 active plantarflexor push-off (2nd GRF peak): summarized in PMC3943831 / search synthesis
- Normative phase angles (IC neutral, midstance ~+5° DF, terminal DF peak ~+10%, pre-swing PF to ~-20°): https://now.aapmr.org/biomechanics-normal-gait/ · https://www.orthobullets.com/foot-and-ankle/7001/gait-cycle · enability.com normal-gait-1
- Sagittal ankle ROM ~30° (DF up to ~20°, PF 40-55° in some refs incl. closed-chain): PMC4994968 (Biomechanics of the ankle)
- Huang et al. 2015 ACTUAL title (REF correction): "Mechanical and energetic consequences of reduced ankle plantar-flexion in human walking", JEB 2015 — PMC4664043
- Our prior independent derivation of ~78 N·m: [[41_ankle_pitch_pushoff_rs03_underspec]] §2, [[49_ankle_actuator_tn_sizing]]

> [!note] Honesty
> verified: 1.5 N·m/kg torque normative (multi-source) · phase-angle errors items 1-3 (Perry/AAPM&R/Orthobullets converge) · Huang ref misattribution (fetched PMC4664043, title+content confirmed mismatch). estimate/caveat: exact peak-PF angle (-15 vs -20°) and exact % timing vary by source/speed; could not fetch Perry Fig 8-8 or Winter Appendix directly (paywalled) — used secondary normative summaries that consistently agree on the SIGN and PHASE pattern that contradicts the claim.
