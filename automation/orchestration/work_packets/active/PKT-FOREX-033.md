CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-033
PACKET NAME: Intraday-Of-Week USD Settlement-Flow Stage-0 Gate
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_68
LANE: FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_STAGE0
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
- automation/orchestration/work_packets/active/PKT-FOREX-033.md
- automation/forex_engine/forex_intraday_of_week_usd_settlement_flow_stage0_v1.py
- scripts/forex_delivery/run_forex_intraday_of_week_usd_settlement_flow_stage0_v1.py
- tests/forex_engine/test_forex_intraday_of_week_usd_settlement_flow_stage0_v1.py
- .aios/staging/PKT_FOREX_033
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json

READ-ONLY INPUT PATHS:
- Reports/forex_delivery/AIOS_FOREX_SCALPING_TECHNIQUE_FIDELITY_V1_STATE.json
- .aios/staging/PKT_FOREX_027/run1/AIOS_FOREX_AUTHORITATIVE_PAIR_TIMEFRAME_MATRIX_V1.json
- .aios/staging/PKT_FOREX_032/PKT_FOREX_032_COMPLETION.json
- .aios/runtime/forex_multi_regime_corpus_v3/manifests/manifest.json
- existing strategy, candidate, rejection, and multiple-testing ledgers

FORBIDDEN PATHS:
- every write path not listed above
- market outcome scoring
- source dataset mutation
- validation data
- final holdout data
- .git/
- AGENTS.md
- RISK_POLICY.md
- Reports/
- broker/
- oanda/
- secrets/
- credentials/
- live_trading/

APPROVAL AUTHORITY: Anthony explicitly directed continuous high-throughput historical edge research and bounded Stage-0 eligibility work under existing historical-research authority. Commit, push, merge, canonical promotion, broker access, credentials, PAPER, Practice, LIVE, orders, collectors, money movement, validation-data access, and final-holdout access remain unauthorized.

PROTECTED ACTION RULE: Commit, push, merge, canonical promotion, validation-data access, and final-holdout execution each require separate explicit Human Owner approval. Approval does not transfer between actions.

PREFLIGHT:
- require PKT-FOREX-032 completion result VALID_STAGE1_FAILURE_POSTMORTEM_COMPLETE
- require cumulative actual-attempt lower bound 1195 and governed after-cost candidate count 143
- require authoritative H1 corpus fingerprint 4357f24113ba54b9a6f8d6a3d87860109ca7429dbbd627b20c3d5a30540c6b32
- require existing F7_DAY_OF_WEEK contract fingerprint e3fbdbb0a0fdfba17f4646c32769ed9e1732fee40ba113bc7eb78585c8fca27f
- require registry integrity and zero active locks before claiming OCC68
- claim exactly LOCK_EAST_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_STAGE0_OCC68

MISSION:
Run a no-outcome Stage-0 duplicate, semantic, data-compatibility, public-source, and preregistration gate for a fixed H1 intraday-of-week foreign-currency-versus-USD settlement-flow hypothesis.

OBJECTIVE:
Decide whether exactly five fixed original, inverse, and symmetric candidates may proceed to a bounded chronological Stage-1 development screen without repeating rejected session-cycle, direction, or arbitrary-calendar mechanisms.

REQUIREMENTS:
- Modify the lock registry only through the approved claim and release scripts.
- Open no market rows and calculate no returns or strategy performance.
- Use exactly the 17 certified H1 USD pairs in the authoritative matrix; do not claim 58 multi-timeframe USD pairs.
- Normalize every pair as foreign currency per USD.
- Freeze five variants: Wednesday-Friday long foreign; its exact reversed short; Monday-Tuesday short foreign; its exact reversed long; and the symmetric original combination.
- Freeze 00:00 UTC entry and 20:00 UTC exit, prior completed 20-H1 ATR stop, no take profit, no rollover, bid/ask costs, slippage, exposure, folds, purge, embargo, baselines, gates, and reproduction before Stage 1.
- Require no-trade, deterministic random-direction, always-long-foreign, always-short-foreign, and weekday-agnostic-window baselines.
- Treat online and academic sources as hypothesis inputs only; preserve counterevidence and unsupported claims.
- Preserve cumulative multiple-testing counts unchanged because Stage 0 scores no outcomes.
- Run twice in isolated staging and require byte-identical deterministic artifacts.

VALIDATOR CHAIN:
- packet governance and completeness
- focused and regression tests
- authoritative matrix and H1 manifest hash checks
- exact 17-pair scope and orientation checks
- exact five-candidate grid and fingerprint checks
- F7 lineage and duplicate-boundary checks
- public-source registry completeness
- zero market-row, validation-row, and holdout-row access
- cumulative trial-memory unchanged
- two-run byte-identical artifact comparison
- path guard
- lock registry integrity
- Git diff check
- exact OCC68 release and zero-active-lock verification

STOP POINT:
After a validator-PASS Stage-0 decision and frozen preregistration are preserved and OCC68 is released, generate Stage 1 only if the decision is ADMIT_STAGE1_LOW_COST_ONLY.

SAFE NEXT ACTION:
Do not score market outcomes until the frozen Stage-1 preregistration hash is independently verified.

FINAL REPORT FORMAT:
Short milestone only while research continues. No commit and no push.
