CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-034
PACKET NAME: Intraday-Of-Week USD Settlement-Flow Stage-1 Development Screen
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_69
LANE: FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_STAGE1
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
- automation/orchestration/work_packets/active/PKT-FOREX-034.md
- automation/forex_engine/forex_intraday_of_week_usd_settlement_flow_stage1_v1.py
- scripts/forex_delivery/run_forex_intraday_of_week_usd_settlement_flow_stage1_v1.py
- tests/forex_engine/test_forex_intraday_of_week_usd_settlement_flow_stage1_v1.py
- .aios/staging/PKT_FOREX_034
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json

READ-ONLY INPUT PATHS:
- .aios/staging/PKT_FOREX_033/run1/AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_PREREGISTRATION.json
- .aios/staging/PKT_FOREX_033/PKT_FOREX_033_COMPLETION.json
- automation/forex_engine/forex_intraday_of_week_usd_settlement_flow_stage0_v1.py
- .aios/runtime/forex_multi_regime_corpus_v3/manifests/manifest.json
- .aios/runtime/forex_practice_history_human_inbox/*.H1.json for the frozen 17-pair scope

FORBIDDEN PATHS:
- every write path not listed above
- source dataset mutation
- 2025 validation outcome rows
- 2026 final holdout outcome rows
- .git/
- AGENTS.md
- RISK_POLICY.md
- Reports/
- broker/
- oanda/
- secrets/
- credentials/
- live_trading/

APPROVAL AUTHORITY: Anthony explicitly directed continuous historical edge research and automatic execution of bounded development screens covered by existing authority. Commit, push, merge, canonical promotion, broker access, credentials, PAPER, Practice, LIVE, orders, collectors, money movement, validation-data access, and final-holdout access remain unauthorized.

PROTECTED ACTION RULE: Commit, push, merge, canonical promotion, validation-data access, and final-holdout execution each require separate explicit Human Owner approval. Approval does not transfer between actions.

PREFLIGHT:
- require PKT-FOREX-033 result VALID_STAGE0_ADMISSION_PREREGISTRATION_FROZEN
- require preregistration SHA-256 a794032d15bd81cc4f6f0a81fea35a232b991ab12ece71df4ad485d4b7e5acf6
- require Stage-0 engine SHA-256 834cf50b01073aebe3a0723a1f88bb5af4ed10d85dfad74e7f12593f3fa1fdd3
- require H1 manifest SHA-256 f784867978464aee59f4b3377eca013237378fd8c3a61c068f8c111ce6451d32
- require exact active OCC69 lifecycle

MISSION:
Score exactly the five frozen PKT-FOREX-033 candidates on chronological 2019-2024 development folds using certified H1 bid/ask history, realistic slippage, strict baselines, and no 2025 or 2026 outcome access.

REQUIREMENTS:
- Stream each source only to the first 2025 timestamp sentinel; do not parse price fields from validation or holdout rows.
- Verify source hashes without interpreting post-development outcomes.
- Run capacity checks before calling any outcome-scoring function.
- Preserve every qualifying trade, including all losses, in a machine-readable journal.
- Use the frozen pair scope, direction variants, entry, exit, ATR stop, costs, folds, risk, baselines, and thresholds unchanged.
- Require after-cost expectancy to be strictly greater than zero and every required baseline.
- Preserve exact original-versus-reverse event identity and opposite direction.
- Record all five actual trials in cumulative counts, even if clearly negative.
- Produce a complete post-mortem and rejection fingerprint for every valid failure.
- Run twice in isolated staging and require byte-identical artifacts.

VALIDATOR CHAIN:
- packet governance and completeness
- focused and regression tests
- dependency and data-source hash checks
- streaming validation/holdout boundary tests
- capacity-before-outcome call-order guard
- completed-candle and prior-only ATR leakage checks
- executable bid/ask stop, exit, spread, and slippage checks
- exact direction and reverse-identity audit
- negative and zero baseline regression tests
- journal completeness and loss-preservation audit
- fold, pair, currency, regime, drawdown, and cost-stress audits
- post-mortem and rejection-fingerprint audit
- cumulative multiple-testing ledger update
- two-run byte-identical artifact comparison
- path guard
- lock registry integrity
- Git diff check
- exact OCC69 release and zero-active-lock verification

STOP POINT:
After valid Stage-1 results, complete post-mortems, deterministic reproduction, and OCC69 release, advance only a candidate passing every frozen Stage-1 gate. Otherwise select the next materially distinct hypothesis.

SAFE NEXT ACTION:
Keep 2025 validation and 2026 final holdout sealed unless a genuine Stage-1 survivor is frozen.

FINAL REPORT FORMAT:
Short milestone only while research continues. No commit and no push.
