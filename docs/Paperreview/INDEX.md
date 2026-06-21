# Paperreview · 핵심 논문 리뷰 색인

> 프로젝트 결정에 핵심인 논문의 구조화 리뷰. 각 노트의 레퍼런스에서 `→ 리뷰 [[Paperreview/<slug>]]`로 링크.

- [[margolis-rapid-locomotion]] — An end-to-end RL controller drives the MIT Mini Cheetah quadruped to a record 3.9 m/s by replacing manual velo… **왜**: It is the primary-source definition of the grid-adaptive velocity curriculum you depend on
- [[siekmann-periodic-reward]] — A clock-indexed, von-Mises-smoothed reward that penalizes foot FORCE during swing and foot VELOCITY during sta… **왜**: It gives you a drop-in, fully-specified reward (exact coefficients, kernels, and weights) 
- [[radosavovic-humanoid-transformer]] — A causal-transformer policy over proprioceptive obs-action history, trained with massively parallel RL + teach… **왜**: It is the single best published justification for excluding a toe joint from an RL locomot
- [[caps-smooth-control]] — A two-term action-policy regularizer (temporal + spatial smoothness) added directly to the policy loss of any … **왜**: It is the canonical, minimal, drop-in recipe for killing RL control jitter - exactly our f
- [[toe-stiffness-optimization]] — A trajectory-optimization study plus a 20-subject human boot experiment that pins the best fixed passive toe (… **왜**: It is the one paper that gives you a defensible number for your passive toe spring: ~56-60
- [[kuo-donelan-dynamic-walking]] — The Kuo/Donelan/Ruina dynamic-walking energetics canon (5 papers, 2002–2010): efficient walking is governed by step-to-step TRANSITION work (push-off/collision), ~2/3 of metabolic cost, optimized by a pre-emptive forefoot push-off; the COM should arc, not flatten. **왜**: the verified theoretical basis for our forefoot/CoP + CoT reward — reward timed push-off / transition energy / penalize collision, NOT joint-angle templates or a flattened COM.
