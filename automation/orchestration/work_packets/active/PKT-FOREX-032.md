CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-032
PACKET NAME: Directed USD-Anchor To Non-USD Cross Price-Discovery Lead-Lag Stage-1 Screen
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_67
LANE: FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE1
WORKTREE: C:\Dev\Ai.Os
BRANCH: main

MISSION ID: MISSION-AIOS-001
MISSION NAME: AIOS Governed Self-Building Operating System
PROGRAM ID: PRG-FOREX-001
PROGRAM NAME: AIOS Forex Supervised Operational Validation Program V1
EPIC ID: EPC-FOREX-002
EPIC NAME: Strategy Intelligence V1
BUCKET ID: BKT-FOREX-003
BUCKET NAME: Strategy Validation V1

ALLOWED PATHS:
- automation/orchestration/work_packets/active/PKT-FOREX-032.md
- automation/forex_engine/forex_directed_anchor_cross_lead_lag_stage1_v1.py
- scripts/forex_delivery/run_forex_directed_anchor_cross_lead_lag_stage1_v1.py
- tests/forex_engine/test_forex_directed_anchor_cross_lead_lag_stage1_v1.py
- .aios/staging/PKT_FOREX_032
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json

READ-ONLY INPUT PATHS:
- .aios/runtime/forex_m5_immutable_corpus_v2/FROZEN.json
- .aios/runtime/forex_m5_immutable_corpus_v2/manifest.json
- .aios/runtime/forex_m5_immutable_corpus_v2/partitions/
- .aios/staging/PKT_FOREX_031/run1/AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_PREREGISTRATION.json
- .aios/staging/PKT_FOREX_031/PKT_FOREX_031_COMPLETION.json
- .aios/staging/PKT_FOREX_030/PKT_FOREX_030_COMPLETION.json
- existing strategy, candidate, rejection, and multiple-testing ledgers

FORBIDDEN PATHS:
- every write path not listed above
- source dataset mutation
- validation rows at or after 2025-04-01T00:00:00Z
- final holdout rows at or after 2026-01-01T00:00:00Z
- .git/
- AGENTS.md
- RISK_POLICY.md
- Reports/
- broker/
- oanda/
- secrets/
- credentials/
- live_trading/

APPROVAL AUTHORITY: Anthony explicitly directed continuous high-throughput historical edge research and execution of bounded Stage-1 screens under existing historical-research authority. Commit, push, merge, canonical promotion, broker access, credentials, PAPER, Practice, LIVE, orders, collectors, money movement, validation-data access, and final-holdout access remain unauthorized.

PROTECTED ACTION RULE: Commit, push, merge, canonical promotion, validation-data access, and final-holdout execution each require separate explicit Human Owner approval. Approval does not transfer between actions.

PREFLIGHT:
- require PKT-FOREX-031 completion result ADMIT_STAGE1_LOW_COST_ONLY
- require frozen preregistration SHA-256 743b28805713e73328f198fecdbd0d907d988c4e1b5c145d89b3b518261bba97
- require authoritative M5 corpus fingerprint 44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a
- require cumulative actual-attempt lower bound 1187 and governed after-cost candidate count 135
- require registry integrity and zero active locks
- claim exactly LOCK_EAST_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE1_OCC67

MISSION:
Execute the frozen eight-candidate chronological development screen without changing its mechanism, links, dataset, costs, folds, parameters, capacity gates, baselines, or thresholds.

OBJECTIVE:
First verify synchronized opportunity capacity without calculating forward returns. Only if every fixed capacity gate passes, score the eight continuation and exact-reverse candidates on development data and reject weak mechanisms before validation data is opened.

REQUIREMENTS:
- Modify the lock registry only through approved claim and release scripts.
- Verify every opened partition hash before reading it.
- Use only completed development candles strictly before 2025-04-01T00:00:00Z.
- Run the frozen synchronized-opportunity capacity gate before any forward-return calculation; a capacity failure adds zero trials.
- Score exactly eight candidates only after capacity passes and then advance cumulative counts from 1187 to 1195 and from 135 to 143.
- Preserve exact fixed directed links, base-quote normalization, timestamp synchronization, target deduplication, ranking, exposure, risk, rollover, entry, stop, exit, spread, slippage, and cost rules.
- Evaluate continuation and exact-reverse orders on identical opportunities.
- Preserve a complete simulated-trade journal including every selected loss and all required source, anchor, target, sign, timing, spread, cost, fold, session, volatility, and regime fields.
- Evaluate no-trade, deterministic random-sign, same-pair anchor momentum diagnostic, target-own one-bar momentum, pooled currency-strength, and wrong-anchor baselines.
- Require after-cost expectancy to be strictly greater than zero and prevent negative or zero expectancy from passing any no-trade comparison.
- Compute gross, after-cost, stress, break-even cost, profit factor, drawdown, trade, direction, pair, currency, fold, regime, concentration, and selection-bias results.
- Preserve every valid failure in a complete post-mortem with truthful primary and secondary causes, deterministic rejection fingerprint, prohibited repetitions, salvage evidence, and next distinct hypothesis.
- Do not access validation or final-holdout rows even if a candidate passes Stage 1.
- Run twice in isolated staging and require byte-identical deterministic artifacts.

VALIDATOR CHAIN:
- packet governance and completeness
- focused, regression, cost, leakage, and path tests
- manifest, dataset, completion, and preregistration hash checks
- exact candidate-grid, link, and fingerprint checks
- pre-score capacity and synchronized timestamp checks
- completed-candle, next-candle, fold, purge, embargo, rollover, side-price, stop, slippage, and cost-accounting checks
- exact continuation versus reverse opportunity-pair checks
- negative and zero expectancy no-trade baseline regressions
- all required baseline identity and population checks
- journal completeness and no-dropped-loss checks
- pair, currency, direction, session, regime, period, and trade concentration checks
- global multiple-testing and PBO-proxy checks
- complete post-mortem check
- two-run byte-identical artifact comparison
- path guard
- lock registry integrity
- Git diff check
- exact OCC67 release and zero-active-lock verification

STOP POINT:
After valid Stage-1 results and post-mortem are preserved and OCC67 is released, continue to Stage 2 only for a survivor; otherwise select the next distinct hypothesis.

SAFE NEXT ACTION:
Do not open validation data unless at least one frozen candidate passes every Stage-1 gate.

FINAL REPORT FORMAT:
Short milestone only while research continues. No commit and no push.
