CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-019-022-R1
PACKET NAME: Shared CFTC Execution Kernel Corrective Rerun
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_57
LANE: FOREX_CFTC_EXECUTION_KERNEL_CORRECTIVE_RERUN
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
- automation/orchestration/work_packets/active/PKT-FOREX-019-022-R1.md
- automation/forex_engine/forex_cftc_crowding_unwind_price_confirmation_v1.py
- automation/forex_engine/forex_cftc_positioning_acceleration_price_continuation_v1.py
- automation/forex_engine/forex_cftc_participant_divergence_price_confirmation_v1.py
- automation/forex_engine/forex_cftc_dealer_inventory_pressure_reversal_v1.py
- tests/forex_engine/test_forex_cftc_crowding_unwind_price_confirmation_v1.py
- tests/forex_engine/test_forex_cftc_positioning_acceleration_price_continuation_v1.py
- tests/forex_engine/test_forex_cftc_participant_divergence_price_confirmation_v1.py
- tests/forex_engine/test_forex_cftc_dealer_inventory_pressure_reversal_v1.py
- .aios/staging/PKT_FOREX_019_022_R1/
- .aios/runtime/forex_cftc_crowding_unwind_price_confirmation_v1/
- .aios/runtime/forex_cftc_positioning_acceleration_price_continuation_v1/
- .aios/runtime/forex_cftc_participant_divergence_price_confirmation_v1/
- .aios/runtime/forex_cftc_dealer_inventory_pressure_reversal_v1/
- Reports/forex_delivery/AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_V1_REPORT.md
- Reports/forex_delivery/AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_REJECTION_V1.json
- Reports/forex_delivery/AIOS_FOREX_CFTC_POSITIONING_ACCELERATION_PRICE_CONTINUATION_V1_REPORT.md
- Reports/forex_delivery/AIOS_FOREX_CFTC_POSITIONING_ACCELERATION_PRICE_CONTINUATION_REJECTION_V1.json
- Reports/forex_delivery/AIOS_FOREX_CFTC_PARTICIPANT_DIVERGENCE_PRICE_CONFIRMATION_V1_REPORT.md
- Reports/forex_delivery/AIOS_FOREX_CFTC_PARTICIPANT_DIVERGENCE_PRICE_CONFIRMATION_REJECTION_V1.json
- Reports/forex_delivery/AIOS_FOREX_CFTC_DEALER_INVENTORY_PRESSURE_REVERSAL_V1_REPORT.md
- Reports/forex_delivery/AIOS_FOREX_CFTC_DEALER_INVENTORY_PRESSURE_REVERSAL_REJECTION_V1.json
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json only through the approved lock claim and release scripts

FORBIDDEN PATHS:
- AGENTS.md
- RISK_POLICY.md
- .git/
- .github/
- secrets/
- credentials/
- .env
- broker/
- oanda/
- live_trading/
- webhooks/
- every path not listed in ALLOWED PATHS

APPROVAL AUTHORITY: Anthony explicitly authorized continuous local historical edge-research APPLY work on 2026-09-04. Canonical promotion of corrected research artifacts remains a separate protected action. Commit, push, merge, deployment, broker access, credentials, PAPER, Practice, LIVE, orders, collectors, and money movement are not authorized.

NO-REPOSITORY-PUBLISH AUTHORITY: Anthony explicitly approves no commit, no push, and no merge for this packet.

PREFLIGHT:
- pwd
- git status --short --branch
- git branch --show-current
- git remote -v
- adopt the verified post-PKT-FOREX-022 registry state with SHA-256 8eadf05acd92391bb57e78b3ff080cca2658fa0882d00a88bd48c334e90f17ea and zero active locks
- claim exactly LOCK_EAST_FOREX_CFTC_EXECUTION_KERNEL_CORRECTIVE_RERUN_OCC57

MISSION:
Correct the shared implementation defects that invalidate interpretation of PKT-FOREX-019 through PKT-FOREX-022, add exact regression tests, and rerun the four unchanged preregistered experiments twice in isolated staging. This repair is not a new hypothesis and must not increment the cumulative experiment ledger.

OBJECTIVE:
Produce validator-PASS, byte-identical corrected staging artifacts for the four unchanged CFTC experiments without opening the holdout or changing their economic specifications.

PROTECTED ACTION RULE:
Commit, push, merge, canonical promotion, and final-holdout execution each require separate explicit Human Owner approval. Approval does not transfer between actions.

FIXED EXPERIMENT BOUNDARY:
- Preserve all four strategy identities and economic mechanisms.
- Preserve each frozen dataset, pair-eligibility rule, timeframe, decision time, entry signal, exit rule, stop, target, maximum holding period, direction permission, risk size, currency exposure, pair exposure, observed-spread model, slippage assumptions, parameter grid, development and validation periods, six chronological folds, holdout boundary, candidate fingerprints, family fingerprints, and cumulative trial count.
- Keep the final holdout sealed.

CORRECTIONS:
1. Trigger stops and targets on the executable quote side and fill them at an executable, conservative price.
2. Timestamp maximum-hold exits at the completed H1 close, not the bar open.
3. Reexecute random-direction controls through the same bid/ask, stop, target, slippage, and holding logic.
4. Match CFTC contracts exactly so cross-rate contracts cannot be mistaken for main currency futures.
5. Compute drawdown and bootstrap evidence by same-decision portfolio clusters rather than arbitrary trade order.
6. Report all six preregistered development folds, including empty folds as non-positive.
7. Fail the overfitting proxy closed when no development-positive candidate exists.
8. Enforce the current minimum gates: positive after-cost expectancy, profit factor at least 1.10, maximum drawdown at most 10%, at least 200 total pre-holdout qualifying trades, adequate long and short counts when both are enabled, breadth, walk-forward, cost stress, parameter stability, leakage, concentration, baseline, multiple testing, and reproducibility.
9. Replace hard-coded leakage and chronology PASS claims with computed evidence, including zero trades crossing split or fold boundaries.

VALIDATOR CHAIN:
- python -m pytest tests/forex_engine/test_forex_cftc_crowding_unwind_price_confirmation_v1.py tests/forex_engine/test_forex_cftc_positioning_acceleration_price_continuation_v1.py tests/forex_engine/test_forex_cftc_participant_divergence_price_confirmation_v1.py tests/forex_engine/test_forex_cftc_dealer_inventory_pressure_reversal_v1.py -q
- python -m pytest tests/forex_engine/test_run_forex_cftc_crowding_unwind_price_confirmation_v1.py tests/forex_engine/test_run_forex_cftc_positioning_acceleration_price_continuation_v1.py tests/forex_engine/test_run_forex_cftc_participant_divergence_price_confirmation_v1.py tests/forex_engine/test_run_forex_cftc_dealer_inventory_pressure_reversal_v1.py -q
- run each unchanged experiment twice in separate PKT_FOREX_019_022_R1 staging roots
- require byte-identical artifact sets for each experiment
- verify packet, artifact, path, holdout, leakage, cost, baseline, multiple-testing, and reproducibility receipts
- git diff --check
- git diff -- the four allowed engine files and four allowed test files
- automation/orchestration/locks/Test-LockRegistryIntegrity.DRY_RUN.ps1

STOP POINT:
If all corrected artifacts validate, stop before canonical replacement and request one exact protected-promotion approval. If no promotion approval is needed under verified authority, promote atomically, verify every byte, release only OCC57, verify zero active locks, and continue the edge-research factory. Never commit or push.

SAFE NEXT ACTION:
After validator PASS, present the exact four-experiment corrective promotion scope and its staged receipt hash for Human Owner approval.

FINAL REPORT FORMAT:
Only VERIFIED EDGE FOUND, HUMAN APPROVAL REQUIRED, or a hash-verified RESUMABLE_EDGE_RESEARCH checkpoint caused by unavoidable platform/runtime termination.
