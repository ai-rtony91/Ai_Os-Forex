CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-030
PACKET NAME: Abnormal OANDA Price-Update Count Response Stage-1 Development Screen
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_65
LANE: FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_STAGE1
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
- automation/orchestration/work_packets/active/PKT-FOREX-030.md
- automation/forex_engine/forex_abnormal_price_update_response_stage1_v1.py
- scripts/forex_delivery/run_forex_abnormal_price_update_response_stage1_v1.py
- tests/forex_engine/test_forex_abnormal_price_update_response_stage1_v1.py
- .aios/staging/PKT_FOREX_030
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json

READ-ONLY INPUT PATHS:
- .aios/runtime/forex_m5_immutable_corpus_v2/FROZEN.json
- .aios/runtime/forex_m5_immutable_corpus_v2/manifest.json
- .aios/runtime/forex_m5_immutable_corpus_v2/partitions/
- .aios/staging/PKT_FOREX_029/
- existing strategy, candidate, rejection, and multiple-testing ledgers

FORBIDDEN PATHS:
- every write path not listed above
- any source dataset mutation
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
- require PKT-FOREX-029 completion SHA-256 f3c2151173322fff54e7d48f2959094fbeef9b04a4e15c00ef98551ee9d2808a
- require frozen preregistration SHA-256 103e228952ad73d2921ddbaadf031d3af0ba174ecd044be4ed7bc0ce57871d16
- require authoritative M5 corpus fingerprint 44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a
- require registry integrity and zero active locks
- claim exactly LOCK_EAST_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_STAGE1_OCC65

MISSION:
Execute the frozen eight-candidate chronological development screen without changing its strategy, dataset, costs, folds, parameters, baselines, or thresholds.

OBJECTIVE:
Determine whether any frozen candidate has positive gross and after-cost development expectancy and passes every Stage-1 gate without opening validation or final-holdout data.

REQUIREMENTS:
- Modify the lock registry only through the approved claim and release scripts.
- Verify every input partition hash before reading it.
- Use only completed development candles strictly before 2025-04-01T00:00:00Z.
- Score exactly eight candidates from the frozen 2x2x2 grid.
- Use next-candle executable bid/ask entry, executable-side stop and exit, observed spread, and fixed adverse slippage.
- Apply the frozen pair/currency exposure selection and risk rules.
- Preserve a complete simulated-trade journal including every selected loss and all required audit fields.
- Compute gross, after-cost, stress-cost, break-even cost, drawdown, fold, direction, pair, currency, and concentration results.
- Evaluate the no-trade zero-expectancy, deterministic random-direction, exact price-only, activity-random-sign, and matched non-shock baselines.
- Reject negative or zero gross or after-cost expectancy and prevent either from passing the zero baseline.
- Do not access validation or final-holdout rows even if a candidate passes Stage 1.
- Record all eight actual candidates and configurations in cumulative trial accounting only after a valid run.
- If valid failure, create a complete post-mortem, deterministic fingerprints, prohibited repetitions, salvage evidence, and next materially distinct hypothesis.
- Run twice in isolated staging and require byte-identical deterministic artifacts.

VALIDATOR CHAIN:
- packet governance and completeness
- focused and regression tests
- manifest, dataset, and preregistration hash checks
- exact candidate-grid and fingerprint checks
- completed-candle, timestamp, next-candle, leakage, purge, embargo, side-price, stop, slippage, and cost-accounting checks
- negative/zero expectancy no-trade baseline regression checks
- journal completeness and no-dropped-loss checks
- fold, breadth, concentration, random, simple-strategy, and matched-control baseline checks
- cumulative multiple-testing ledger checks
- two-run byte-identical artifact comparison
- path guard
- lock registry integrity
- Git diff check
- exact OCC65 release and zero-active-lock verification

STOP POINT:
After valid Stage-1 results and complete post-mortem are preserved and OCC65 is released, continue to Stage 2 only for a survivor; otherwise select the next distinct hypothesis.

SAFE NEXT ACTION:
Do not open validation data unless at least one frozen candidate passes every Stage-1 gate.

FINAL REPORT FORMAT:
Short milestone only while research continues. No commit and no push.
