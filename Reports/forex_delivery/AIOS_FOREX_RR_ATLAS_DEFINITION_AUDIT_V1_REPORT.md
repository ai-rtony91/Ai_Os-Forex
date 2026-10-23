# AIOS Forex R:R Atlas Definition Audit V1

Status: `COMPLETE`

- Denominator: Unconditional sampled H1 bars from eligible pairs in the Development window, capped by development_indices sampling per pair.
- Event contract: +nR before -1R barrier outcome, not a complete candidate trade system and not conditioned on a frozen opportunity event.
- Horizon: 96 H1 bars.
- Same-bar ordering: stop-first in barrier_result.
- Null: Packet 026 atlas state did not include a separate dependence-preserving null reach-rate table; Packet 027 treats this as an interpretation limitation, not as proof of edge.
- Breakeven interpretation: The atlas is a diagnostic opportunity map. If naively compared to fixed full-win/full-loss breakeven, all 2R-6R raw reach rates are negative before additional costs; because the denominator is unconditional sampled bars, this does not by itself reject conditional event strategies.
- LONG 2R6R: {'2R': 0.224735, '3R': 0.116645, '4R': 0.058156, '5R': 0.027785, '6R': 0.013329}
- SHORT 2R6R: {'2R': 0.225332, '3R': 0.117838, '4R': 0.056698, '5R': 0.028846, '6R': 0.014456}
