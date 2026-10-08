CODEX-ONLY PROMPT
AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

# PKT-FOREX-043-R1 — Research Memory Compatibility Repair

IDENTITY MARKER: PKT_FOREX_043_R1_RESEARCH_MEMORY_COMPATIBILITY_REPAIR
SUPERVISOR IDENTITY: Codex East
PACKET ID: PKT-FOREX-043-R1
PACKET NAME: Research Memory Compatibility Repair
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_81
LANE: FOREX_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0_R1
WORKTREE: C:\Dev\Ai.Os
BRANCH: main, observed during preflight and preserved
LOCK ID: LOCK_EAST_FOREX_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0_R1_OCC81
APPROVAL AUTHORITY: Anthony, Human Owner, explicit PKT-FOREX-043-R1 authorization

MISSION ID: MISSION-AIOS-001
MISSION NAME: AIOS Governed Self-Building Operating System
PROGRAM ID: PRG-FOREX-001
PROGRAM NAME: AIOS Forex Supervised Operational Validation Program V1
EPIC ID: EPC-FOREX-002
EPIC NAME: Strategy Intelligence V1
BUCKET ID: BKT-FOREX-003
BUCKET NAME: Strategy Validation V1

## Mission

Repair the legacy whole-file research-memory pin so it preserves the trusted corrected PKT-FOREX-039 history while accepting valid append-only research records. Then inspect existing indicator implementations and evidence without changing or scoring any strategy.

## Allowed paths

- `automation/orchestration/work_packets/active/PKT-FOREX-043-R1.md`
- `automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py`
- `tests/forex_engine/test_forex_edge_discovery_tournament_stage1_v1.py`
- `tests/forex_engine/test_forex_edge_validation_pipeline_v1.py`
- `automation/orchestration/locks/FILE_LOCK_REGISTRY.json` only for OCC81
- New test-only subfolders beneath `.aios/staging/PKT_FOREX_038/` and `.aios/staging/PKT_FOREX_043/`

## Forbidden paths and actions

All other paths are read-only. Do not alter canonical research memory, scientific artifacts, PKT-FOREX-043's frozen specifications or baselines, signals, data, pip metadata, costs, entries, exits, results, or classifications. Do not open raw market, validation, or holdout data. Do not score candidates, access brokers or credentials, place orders, switch branches, reset, stash, clean, stage, commit, push, merge, create a PR, or deploy.

## Validator chain

1. Verify repository state, prior PKT-FOREX-043 registration, research-memory hashes, zero lock conflict, and canonical OCC81 identity.
2. Claim only OCC81 through the canonical lock interface.
3. Validate the trusted corrected historical ledger prefix and fingerprint entries.
4. Test valid append, changed or missing history, broken chains, duplicate event IDs, valid new fingerprints, and idempotent repeat verification.
5. Run the three formerly blocked tests and full relevant Forex regression chain without market access.
6. Verify canonical research memory and prior scientific artifacts are unchanged.
7. Inspect existing indicator code, tests, experiments, and result artifacts read-only.
8. Run scoped diff and lock-registry integrity checks.
9. Release only OCC81 and confirm zero active locks, no commit, and no push.

## Stop point

Stop after the append-only memory verifier and regressions pass, canonical research evidence remains unchanged, the read-only indicator review is complete, OCC81 is released, and one exact approval request for the smallest separate indicator comparison is prepared. Do not implement or register that comparison under this authority.

## Final report

Use the mandatory Owner View and successful APPLY report. Include exact repair and tests, files changed, unchanged research memory, compact indicator review, the smallest proposed comparison, remaining blockers, lock status, no-commit/no-push, and one complete next approval request.

## Execution state

- Status: `COMPLETE`.
- Repair: the whole-file memory pin is now a trusted-snapshot plus validated append-only-tail check. The trusted PKT-FOREX-042 corrective manifest is pinned by SHA-256 and identifies the corrected PKT-FOREX-039 ledger and fingerprint baseline.
- Historical protection: the exact `227`-record ledger prefix and `79` protected fingerprint entries must remain present and in order. The full current ledger must pass hash-chain, unique-event, record-schema, and scored-attempt rules. Every later candidate identity must match a valid fingerprint-index specification and an exact later ledger identity.
- Rejected mutations covered by tests: changed, missing, or reordered historical records; broken chains; duplicate event IDs; invalid later records; changed or missing protected fingerprints; and conflicting later candidate identities.
- Trusted corrected ledger baseline: `227` records, scored-attempt lower bound `1292`, proposed count `525`.
- Current append-only ledger: `263` records, scored-attempt lower bound `1292`, proposed count `561`.
- Current later records and fingerprints: `36`, all PKT-FOREX-043 proposed-unscored registrations.
- Focused repair tests: `10 passed`.
- Full applicable PKT-FOREX-038/039/040/041/042/043 regression chain: `110 passed`; no tests skipped or deselected.
- Read-only indicator and activity test set: `81 passed`.
- Canonical ledger SHA-256 unchanged: `5101414160c7d803a820786d69818dc575bed549205ef5661a7fb54958248d20`.
- Canonical fingerprint-index SHA-256 unchanged: `6df7c2a7a1b1b301a3f43179542b228eda20492a5094cc486a2ba0195776f078`.
- Trusted PKT-FOREX-042 corrective-manifest SHA-256 unchanged: `9df195ac79f68671b99e54293874974b88fb3574cb681e1c58f7822358c3b191`.
- PKT-FOREX-043 two-run scientific aggregate unchanged: `5793d495145e9d56d5c4bb0c40ab9d310264a24bedd3d1ce3136921b08fd1ed4`; `11` artifacts, byte-identical, zero mismatches.
- Reviewed source SHA-256: `7c86e6e2638dedd57bfcd7b3608539d903d5429ba825fa6e277534d9f43a0cdc`.
- Reviewed Stage-1 test SHA-256: `48cfdaf620a243903c0a51358918ceedf8cd0334c936ff0b78e852155d04d58f`.
- Market, validation, and holdout rows opened by this repair: `0`.
- New scored-trial increment: `0`.
- Verified edge: `FALSE`.
- OCC81: `RELEASED`; post-release registry integrity passed and active-lock count is `0`.
- Commit: `NOT_PERFORMED`.
- Push: `NOT_PERFORMED`.

## Read-only indicator review

| Item | Existing code and tests | Existing use and evidence | Current limit |
|---|---|---|---|
| RSI | `forex_scalping_techniques_v1.py`; shadow filters in `forex_p1_experience_learning_loop_v1.py` and `forex_p1_risk_market_hardening_v1.py`; calculation and threshold tests exist | Implemented as a range-reversion primitive and a BUY/SELL entry filter. Strategy-proof sample evidence is synthetic, and P1 use was shadow-only; neither establishes market value. | The shared RSI writes its first value one candle late and lacks a standard reference-vector or future-data invariance test. Repair and certify it before a scored comparison. |
| MACD | `forex_supertrend_macd_adx_v1.py`, `forex_macd_confluence_research_v1.py`, and `forex_macd_confluence_runner_v1.py`; calculation and execution tests exist | `FILTER_B_ZERO` was selected on training data, then underperformed Control Baseline V2 in validation: expectancy `-0.08713R` versus `+0.07156R`, PF `0.7741` versus `1.1673`, net difference `-57.5856R`. PKT-032 also found zero robust gross survivors in its combined screen. | This tested MACD rule failed; other rules remain unknown. The shared MACD signal line is seeded with pre-MACD zeros, so its warm-up needs reference repair before new use. |
| Momentum | PKT-FOREX-039/042 Stage-1 code and tests; PKT-FOREX-043 factor/common-component Stage-0 code and tests | The corrected PKT-039 replay tested `72` pair-momentum cells and had zero survivors. PKT-043 registered `36` new common-component/residual specifications plus `18` matched baselines without scoring. | The corrected losing cells stay rejected. PKT-043 remains frozen and unscored; reused or contaminated data cannot supply independent confirmation. |
| ATR | `indicators.py` and `forex_supertrend_macd_adx_v1.py`; Wilder smoothing, warm-up, and causal Supertrend tests exist | Used inside Supertrend, for volatility normalization, stops, and risk sizing in Supertrend, PKT-030 activity, and PKT-032 screens. | Existing results test strategies that use ATR; they do not isolate ATR's predictive value. Do not change ATR entry and exit behavior in the same comparison. |
| Supertrend | `indicators.py`, `strategies.py`, and `forex_supertrend_macd_adx_v1.py`; calculation, direction, configuration, and campaign tests exist | The initial 30-trade campaign produced no trades because of data and restrictive filters. The later Paper60 evidence is genuinely negative for that exact setup: 30 LONG losses and weak uncertified SHORT results. PKT-032 had zero robust gross survivors. | The earlier configuration mismatch was repaired separately. No-trade evidence, implementation repair, and negative trading evidence must remain separate; Supertrend is retired only for the current milestone, not disproven in every setup. |
| ADX | `forex_supertrend_macd_adx_v1.py`; basic availability and nonnegative-value tests exist | Used as a trend-strength filter in PKT-032 combinations; that 912-hypothesis gross screen had zero robust survivors. Other ADX entries in the scalping registry are contracts only. | No fair after-cost baseline-versus-one-ADX-rule test was found. Its current Wilder helper treats unavailable early DX values as zero, so warm-up needs reference verification first. |
| Bollinger / bandwidth | `forex_scalping_techniques_v1.py`; deterministic inside-band test exists | Bollinger reversion is an implemented pre-data primitive and strategy contract. No scored Bollinger experiment was found. | Only categorical band state exists. Bandwidth is not implemented, and bands, initialization, reference vectors, and future-data invariance are untested. |
| Activity data | `forex_abnormal_price_update_response_stage0_v1.py` and `stage1_v1.py`; provider-semantic, causal-history, execution, cost, and audit tests exist | PKT-029 preregistered eight rules; PKT-030 scored them and closed with zero survivors. The best candidate still had `-1.34342R` after-cost expectancy across `37,951` trades. | OANDA `volume` counts prices created in the candle. It is an `OANDA_PRICE_UPDATE_COUNT_PROXY`, not traded, transaction, tick, or notional volume. No independent tick or traded-volume field was found. |

## Smallest separate comparison

- Proposed packet: `PKT-FOREX-044`; worker: `EAST_OCC_82`; lane: `FOREX_CONTROL_BASELINE_RSI_FILTER_COMPARISON_STAGE1`.
- Canonical preview lock: `LOCK_EAST_FOREX_CONTROL_BASELINE_RSI_FILTER_COMPARISON_STAGE1_OCC82`; the post-OCC81 dry-run status is `READY_TO_CLAIM`, with zero collisions and zero policy blocks. Claim only after owner approval is received.
- Baseline: the existing M5 Control Baseline V2, unchanged: Supertrend ATR period `3`, multiplier `2.0`, both BUY and SELL directions, completed signal candle, next-candle executable entry, and the same pair list, dates, costs, risk, and exits.
- One added direction-symmetric rule: accept a baseline BUY only when completed-candle Wilder RSI(14) is at or below `70`, and accept a baseline SELL only when RSI(14) is at or above `30`; otherwise record the original opportunity as filtered with zero return in the opportunity-set comparison.
- Calculation contract: close-only M5 RSI; first value after `14` close-to-close changes; seed average gain/loss with the arithmetic mean of those `14` changes; thereafter use Wilder recursion `(prior_average*13 + current_change_component)/14`; timestamp the completed signal candle; enter no earlier than the next candle.
- Tests required before scoring: hand-calculated reference vectors, flat/up/down edge cases, exact warm-up, completed-candle timestamp alignment, and proof that changing any future candle cannot alter an earlier RSI or filter decision.
- Comparison outputs: per-executed-trade metrics and original-opportunity-set metrics, including retained and rejected opportunities, costs, fold/breadth results, overlap with the baseline momentum/Supertrend signal, and no change to exits or risk.
- Evidence limit: this is exploratory on reused development/validation evidence and cannot be independent confirmation. A result is a new research choice, never a correction to a prior loss.
