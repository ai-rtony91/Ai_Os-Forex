CODEX-ONLY PROMPT
AI_OS BOOTSTRAP REQUIRED
AI_OS EXECUTION TOKEN

IDENTITY HEADER

IDENTITY MARKER:
AI_OS

SUPERVISOR IDENTITY:
Codex East

PACKET ID:
PKT-FOREX-014-R1

PACKET NAME:
Frozen 21-Series Cross-Sectional Currency Strength Research V1  State-Aligned Revision 1

EXECUTION BOUNDARY ID:
PKT-FOREX-014-R1-CROSS-SECTIONAL-CURRENCY-STRENGTH-001

MODE:
APPLY

ZONE:
EAST

WORKER IDENTITY:
EAST_OCC_48

ASSIGNED WORKER:
Codex East

LANE:
FOREX_CROSS_SECTIONAL_CURRENCY_STRENGTH

MISSION ID:
MISSION-AIOS-001

MISSION NAME:
AIOS Governed Self-Building Operating System

PROGRAM ID:
PRG-FOREX-001

PROGRAM NAME:
AIOS Forex Supervised Operational Validation Program V1

EPIC ID:
EPC-FOREX-002

EPIC NAME:
Strategy Intelligence

BUCKET ID:
BKT-FOREX-003

BUCKET NAME:
Strategy Validation

WORKTREE:
C:\Dev\Ai.Os

BRANCH:
main

EXPECTED HEAD:
b86c65140ed03d53d6c8d6c3618e50da0502f51b

HUMAN OWNER:
Anthony

APPROVAL AUTHORITY:
Human Owner Anthony must separately authorize this exact packet and its recorded SHA-256 before execution. Human Owner Anthony explicitly approves neither commit, push, nor merge through this packet. This packet does not approve broker access, trading, funding, or final-holdout access.

MISSION:
Implement and execute the preregistered cross-sectional currency-strength momentum family against development and Phase 1 validation only, record all twelve configurations and baselines, apply after-cost, walk-forward, stability, concentration, leakage, and multiple-testing gates, close the batch deterministically, and either reject it or identify one pre-holdout survivor. Do not open the final holdout.

DEPENDENCIES:
PKT-FOREX-013-R1 must be PASS. Require post-mortem receipt SHA-256 08c967e13c8afb11021ac5bee4e8a3bc7f1f5da7122b4a7ebede8a75e8ca6d2d, rejection ledger SHA-256 f92c0fe5fbcb982e32394e3483cf8750670a480801386c7102f0b089e877ec48, and preregistration SHA-256 1df11fdb6e6b256400f0b28d229653de469f4639f7f55e95d1c585713af50030.
PKT-FOREX-013-R1 STATUS: PASS.
PKT-FOREX-013-R1 RECEIPT PATH: C:\Dev\Ai.Os\.aios\runtime\forex_frozen_21_series_phase1_postmortem_v1\AIOS_FOREX_PHASE1_POSTMORTEM_RECEIPT.json.
PKT-FOREX-013-R1 RECEIPT SHA-256: 08c967e13c8afb11021ac5bee4e8a3bc7f1f5da7122b4a7ebede8a75e8ca6d2d.

DATASET BOUNDARY:
Dataset ID AIOS-FX-HIST-V1-b6a62a1175398354580b.
Dataset SHA-256 b6a62a1175398354580be3f242cdb67aa3134988b7448c1e1fa11d8abcfb1e7d.
Development interval 2024-01-01T00:00:00Z inclusive through 2025-04-01T00:00:00Z exclusive.
Phase 1 validation interval 2025-04-01T00:00:00Z inclusive through 2026-01-01T00:00:00Z exclusive.
Final holdout begins 2026-01-01T00:00:00Z and must remain sealed, unscored, and uninspected. Streaming readers must stop before reading or parsing a candle at or after that timestamp.

ALLOWED READ PATHS:
- C:\Dev\Ai.Os\AGENTS.md
- C:\Dev\Ai.Os\RISK_POLICY.md
- C:\Dev\Ai.Os\README.md
- C:\Dev\Ai.Os\docs\governance
- C:\Dev\Ai.Os\automation\validators
- C:\Dev\Ai.Os\automation\orchestration\locks
- C:\Dev\Ai.Os\automation\forex_engine\forex_frozen_21_series_edge_research_v1.py
- C:\Dev\Ai.Os\scripts\forex_delivery\run_forex_frozen_21_series_edge_research_v1.py
- C:\Dev\Ai.Os\tests\forex_engine\test_forex_frozen_21_series_edge_research_v1.py
- C:\Dev\Ai.Os\tests\forex_engine\test_run_forex_frozen_21_series_edge_research_v1.py
- C:\Dev\Ai.Os\.aios\runtime\forex_frozen_21_series_phase1_postmortem_v1
- C:\Dev\Ai.Os\.aios\runtime\forex_historical_dataset_freezes_v1\AIOS-FX-HIST-V1-b6a62a1175398354580b
- read-only Git metadata

ALLOWED WRITE PATHS:
- C:\Dev\Ai.Os\automation\forex_engine\forex_cross_sectional_currency_strength_v1.py
- C:\Dev\Ai.Os\scripts\forex_delivery\run_forex_cross_sectional_currency_strength_v1.py
- C:\Dev\Ai.Os\tests\forex_engine\test_forex_cross_sectional_currency_strength_v1.py
- C:\Dev\Ai.Os\tests\forex_engine\test_run_forex_cross_sectional_currency_strength_v1.py
- C:\Dev\Ai.Os\Reports\forex_delivery\AIOS_FOREX_CROSS_SECTIONAL_CURRENCY_STRENGTH_RESEARCH_V1_REPORT.md
- C:\Dev\Ai.Os\Reports\forex_delivery\AIOS_FOREX_CROSS_SECTIONAL_CURRENCY_STRENGTH_REJECTION_V1.json
- C:\Dev\Ai.Os\.aios\runtime\forex_cross_sectional_currency_strength_v1\AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_CONTRACT.json
- C:\Dev\Ai.Os\.aios\runtime\forex_cross_sectional_currency_strength_v1\AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_CANDIDATE_REGISTRY.json
- C:\Dev\Ai.Os\.aios\runtime\forex_cross_sectional_currency_strength_v1\AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_RESULTS.json
- C:\Dev\Ai.Os\.aios\runtime\forex_cross_sectional_currency_strength_v1\AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_CHECKPOINT.json
- C:\Dev\Ai.Os\.aios\runtime\forex_cross_sectional_currency_strength_v1\AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_MANIFEST.json
- C:\Dev\Ai.Os\.aios\runtime\forex_cross_sectional_currency_strength_v1\AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_RECEIPT.json
- C:\Dev\Ai.Os\automation\orchestration\locks\FILE_LOCK_REGISTRY.json only for this packet's exact claim and release lifecycle

FORBIDDEN PATHS AND ACTIONS:
- Every write to the frozen dataset or Phase 1/post-mortem evidence
- Reading, parsing, scoring, or tuning on timestamps at or after 2026-01-01T00:00:00Z
- Unregistered parameters, adaptive searches, pair-only or session-only rescue filters, and any repeated Phase 1 mechanism
- Network market data, OANDA, brokers, credentials, collectors, PAPER, Practice, LIVE, orders, deposits, withdrawals, or money movement
- Frontend, authentication, dependency, package, schema, governance, or unrelated changes
- Staging, commit, push, merge, PR, deployment, branch switch, reset, stash, clean, or destructive cleanup

PREFLIGHT:
1. Read AGENTS.md and RISK_POLICY.md completely and verify repository root, branch main, HEAD b86c65140ed03d53d6c8d6c3618e50da0502f51b, and dirty-state preservation.
2. Require the three dependency hashes above and receipt status PASS, 24 rejection fingerprints, next family CROSS_SECTIONAL_CURRENCY_STRENGTH_MOMENTUM, and holdout NOT_EVALUATED.
3. Require the dataset ID and hash from its receipts without scanning candle contents.
4. Require FILE_LOCK_REGISTRY.json SHA-256 c942032fe1499144bd1add9ca388ae980b7aac42e90eacab2796086b32b58957, 50 records, lock-registry integrity PASS, and zero ACTIVE locks at entry.
5. Require all twelve non-registry output paths absent and no research/collector process by process name.
6. Stop on state drift, collision, output collision, dependency mismatch, dataset mismatch, process conflict, or holdout evidence access.

LOCK PLAN:
Canonical lock ID LOCK_EAST_FOREX_CROSS_SECTIONAL_CURRENCY_STRENGTH_OCC48.
Preview Claim-AiOsFileLock.DRY_RUN.ps1 with WorkerId EAST_OCC_48, Zone EAST, AssignedWorker Codex East, PacketId and ApprovalPacketId PKT-FOREX-014-R1, Lane FOREX_CROSS_SECTIONAL_CURRENCY_STRENGTH, the twelve non-registry outputs, ApprovalAuthority Human Owner Anthony, TtlMinutes 480, and OutputJson. Require READY_TO_CLAIM with zero collisions, policy blocks, and review items. After separate packet authorization, repeat with Apply. At the stop point preview and apply Release-AiOsFileLock.DRY_RUN.ps1 for the exact lock and worker, then require RELEASED, integrity PASS, and zero ACTIVE locks.

IMPLEMENTATION REQUIREMENTS:
1. Use only the frozen preregistration. Implement exactly its synchronized signed currency-return construction, pair inversion, completed-bar timing, next-eligible bid/ask execution, rollover exclusion, exposure cap, stops, targets, time exits, and 0.25 percent risk sizing.
2. Evaluate exactly the 12 registered combinations from lookbacks 15/30/60, dispersion thresholds 1/2 bps, and holding periods 15/30, with stop ATR 1.0 and target 1.5R. Record every result.
3. Compare no-trade, matched-frequency random-direction seed 4014, cost-free, observed bid/ask plus 0.10 pip slippage per side, increased-cost 0.25 pip per side, and simplest-strength baselines.
4. Use six chronological anchored development folds, embargo equal to maximum lookback plus holding period, then one untouched Phase 1 validation interval. Never tune using validation outcomes.
5. Measure expectancy R, profit factor, maximum drawdown, trades, long/short counts, contributing instruments, positive folds, pair/direction/session/regime concentration, turnover, largest-trade dependence, walk-forward consistency, neighboring-parameter stability, and time-dependence-preserving uncertainty.
6. Account for all 12 trials and apply probability-of-backtest-overfitting plus deflated-Sharpe or a documented equivalent selection-bias correction. A best-of-many result cannot pass without adjusted evidence.
7. Require expectancy greater than zero, profit factor at least 1.10, drawdown at most 10 percent, 200 trades, 50 long, 50 short, two instruments, four positive folds, and PASS for walk-forward, cost stress, stability, concentration, leakage, and multiple-testing adjustment.
8. Include focused tests for sign/inversion, synchronization, missing pairs, exposure aggregation, duplicate exposure, lookahead, bid/ask execution, cost stress, neighbor stability, split embargo, holdout stop, deterministic output, and rejection-ledger duplicate checks.
9. Close outputs atomically with hashes and a deterministic reproduction command. If no candidate passes, emit a complete rejection artifact and POSTMORTEM_PENDING disposition. If one passes pre-holdout gates, freeze it only as PRE_HOLDOUT_SURVIVOR; do not open the holdout.
10. Code must be standard-library only and contain no network, credential, broker, collector, order, or process-launch path.

VALIDATOR CHAIN:
1. powershell.exe -NoProfile -ExecutionPolicy Bypass -File automation\orchestration\validators\Test-LockRegistryIntegrity.DRY_RUN.ps1
2. python -m py_compile automation\forex_engine\forex_cross_sectional_currency_strength_v1.py scripts\forex_delivery\run_forex_cross_sectional_currency_strength_v1.py tests\forex_engine\test_forex_cross_sectional_currency_strength_v1.py tests\forex_engine\test_run_forex_cross_sectional_currency_strength_v1.py with bytecode cache redirected outside the repository
3. python -m pytest -q -p no:cacheprovider tests\forex_engine\test_forex_cross_sectional_currency_strength_v1.py tests\forex_engine\test_run_forex_cross_sectional_currency_strength_v1.py
4. python -m pytest -q -p no:cacheprovider tests\forex_engine\test_forex_frozen_21_series_edge_research_v1.py tests\forex_engine\test_run_forex_frozen_21_series_edge_research_v1.py tests\forex_engine\test_forex_frozen_21_series_phase1_postmortem_v1.py tests\forex_engine\test_run_forex_frozen_21_series_phase1_postmortem_v1.py
5. Run the exact research command twice in isolated temp roots and require byte-identical canonical results and hashes.
6. Parse all JSON and require 12 configurations recorded, every baseline present, holdout NOT_EVALUATED, source/dataset hashes unchanged, and safety flags false.
7. python automation\validators\aios_governance_validator.py --input C:\Users\mylab\AppData\Local\Temp\AIOS_FOREX_PACKET_RECOVERY_20260903\PKT-FOREX-014-R1.txt
8. python automation\validators\aios_path_guard_validator.py with repeated allowed and changed arguments for exactly the thirteen repository paths including the lock registry.
9. git diff --check; require exit code zero, treating pre-existing line-ending messages only as warnings.
10. Verify no unrelated dirty/untracked path changed, release the exact lock, rerun integrity, and require zero ACTIVE locks.

ROLLBACK:
Before writing, record absence of all new outputs and hashes of all read dependencies. On failure, stop the active research process, remove only packet-created temporary or new output paths proven absent at preflight, leave the frozen dataset and prior evidence untouched, release the exact lock, and report the first failure. Do not alter unrelated work.

STOP POINT:
Stop only after the complete batch is deterministically CLOSED, every validator passes, the holdout remains NOT_EVALUATED, all twelve configurations are recorded, the lock is RELEASED, and the result is either POSTMORTEM_PENDING or one frozen PRE_HOLDOUT_SURVIVOR. Do not open the holdout and do not start PAPER.

FINAL REPORT FORMAT:
WHAT HAPPENED:
IS IT SAFE:
WHAT DO I DO NEXT:
HOW CLOSE ARE WE:
WHICH MODE SHOULD I USE:
TECHNICAL DETAILS:
PKT-FOREX-014-R1:
CONFIGURATIONS TESTED:
BASELINES:
PRE-HOLDOUT SURVIVORS:
AFTER-COST EXPECTANCY:
PROFIT FACTOR:
MAXIMUM DRAWDOWN:
WALK-FORWARD:
COST STRESS:
PARAMETER STABILITY:
MULTIPLE-TESTING ASSESSMENT:
FINAL HOLDOUT:
FILES CHANGED:
VALIDATORS:
LOCK STATUS:
TRADING OR BROKER CHANGES:
COMMIT:
PUSH:
EXACT BLOCKER:
SAFE NEXT ACTION:
STATUS:
