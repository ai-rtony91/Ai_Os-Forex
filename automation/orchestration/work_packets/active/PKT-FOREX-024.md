CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-024
PACKET NAME: Round-Number Conditional Order-State Stage-1 Screen
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_59
LANE: FOREX_ROUND_NUMBER_CONDITIONAL_ORDER_STATE_STAGE1
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
- automation/orchestration/work_packets/active/PKT-FOREX-024.md
- automation/forex_engine/forex_round_number_conditional_order_state_v1.py
- tests/forex_engine/test_forex_round_number_conditional_order_state_v1.py
- scripts/forex_delivery/run_forex_round_number_conditional_order_state_v1.py
- .aios/staging/PKT_FOREX_024/
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json only through approved claim and release scripts

FORBIDDEN PATHS:
- AGENTS.md
- RISK_POLICY.md
- .git/
- .github/
- Reports/
- .aios/runtime/
- secrets/
- credentials/
- .env
- broker/
- oanda/
- live_trading/
- webhooks/
- every path not listed in ALLOWED PATHS

APPROVAL AUTHORITY: Anthony explicitly directed continuous historical edge research and automatic bounded successor execution after PKT-FOREX-023. This packet reads frozen historical data and writes only isolated staging artifacts. Commit, push, merge, deployment, canonical promotion, final-holdout access, broker access, credentials, PAPER, Practice, LIVE, orders, collectors, and money movement remain unauthorized.

NO-REPOSITORY-PUBLISH AUTHORITY: Anthony explicitly requires no commit and no push. Merge and deployment are outside this packet.

PROTECTED ACTION RULE: Commit, push, merge, canonical promotion, new protected write boundaries, and final-holdout execution each require separate explicit Human Owner approval. Approval does not transfer between actions.

PREFLIGHT:
- pwd
- git status --short --branch
- git branch --show-current
- git remote -v
- require post-PKT-FOREX-023 registry SHA-256 913ad7f4d70db113d31858997933d3e8258623d0c606d2719ab8d05fea0a5bad
- require zero active locks
- require PKT-FOREX-023 completion SHA-256 e92ede3c26e41e430c31301a1d94dcdc1cc1ce23fac192639ad85c6b8925e360
- claim exactly LOCK_EAST_FOREX_ROUND_NUMBER_CONDITIONAL_ORDER_STATE_STAGE1_OCC59
- preserve unrelated dirty files

MISSION:
Execute the frozen Stage-1 chronological development screen for ROUND_NUMBER_CONDITIONAL_ORDER_STATE_CLASSIFIER on all 58 eligible frozen M5 pairs. Test the approach-bounce and confirmed-cross branches with all five required direction variants. Use observed bid/ask, fixed slippage, exact baselines, full journals, global trial-memory adjustment, and no final holdout.

OBJECTIVE:
Produce a valid, deterministic Stage-1 accept-or-reject decision for all ten frozen candidates without reading validation or final-holdout outcomes, changing any rule after results, or counting an implementation repair as a new trial.

FROZEN INPUTS:
- .aios/staging/PKT_FOREX_023/run1/AIOS_FOREX_ROUND_NUMBER_SUCCESSOR_PREREGISTRATION.json SHA-256 b3c4529012dc73f5e8a0f7d2b0ab386fe80b5ff732ab32d04d512ca7608d535c
- .aios/runtime/forex_m5_immutable_corpus_v2/manifest.json SHA-256 1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b
- .aios/runtime/forex_m5_immutable_corpus_v2/FROZEN.json SHA-256 961031d7e5f16586d49a5168d33530e08e97240213bc2a93ee66ea32ce93adb7
- aggregate corpus fingerprint 44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a
- nine current rejection sources frozen by PKT-FOREX-023
- PKT-FOREX-023 global computational-attempt lower bound 1,164

EXACT EXPERIMENT:
- Development rows only: 2024-01-01T00:00:00Z inclusive through 2025-04-01T00:00:00Z exclusive.
- Final holdout begins 2026-01-01T00:00:00Z and must not be opened.
- Signal timeframe M5; completed candles only; entry at the next available completed M5 candle open.
- Pip size is 0.01 for JPY-quote pairs and 0.0001 otherwise. Eligible round levels are integer multiples of 50 pips.
- APPROACH_00_50_REVERSAL: from above, completed low enters the 0.01-percent band above a lower round level without touching or crossing it, original direction LONG; from below, completed high enters the band below an upper round level without touching or crossing it, original direction SHORT.
- COMPLETED_CROSS_00_50_CONTINUATION: prior close and completed close lie on opposite sides of the next crossed round level; upward original direction LONG, downward original direction SHORT.
- Exact shifted-level baseline repeats each rule at 25-pip-offset levels.
- Five separate candidates per branch: ORIGINAL_LONG, EXACT_REVERSED_SHORT, ORIGINAL_SHORT, EXACT_REVERSED_LONG, SYMMETRIC_BIDIRECTIONAL.
- Approach maximum hold two M5 bars; cross maximum hold three M5 bars.
- Protective stop is 1.0 times the completed-candle 14-bar simple true-range average frozen at signal time. No profit target.
- Base execution is observed executable ask for LONG and bid for SHORT plus 0.10 pip slippage per side. Stress execution uses 0.50 pip slippage per side. Gross uses midpoint with zero slippage.
- Skip nonconsecutive candle paths, fold-boundary purge/embargo windows, and any path touching 21:45 through 22:15 UTC so no financing model is needed.
- Base scheduling permits one position per pair, no shared currency among simultaneous positions, and at most five positions. Position risk is 0.25 percent of simulated equity at the protective stop.
- Spread limit is NONE; every observed spread is charged and recorded. Economic-event filter is NOT_APPLICABLE because no certified point-in-time event calendar is required; no trade may be removed post hoc.
- Six chronological development folds with 18-M5-bar boundary embargo.
- Preserve every accepted simulated trade in a deterministic compressed JSONL journal with all fields required by the Human Owner directive.

BASELINES:
- no-trade expectancy exactly zero
- matched-frequency deterministic random direction
- exact rules at deterministic 25-pip-offset non-round levels
- simple prior-completed-bar direction at the same accepted event timestamps
- gross midpoint zero-slippage comparison
- base observed bid/ask plus 0.10 pip slippage
- stress observed bid/ask plus 0.50 pip slippage

STAGE-1 GATES:
- gross expectancy greater than zero
- after-cost expectancy strictly greater than no-trade zero
- profit factor at least 1.10
- maximum drawdown no greater than 10 percent
- at least 200 trades
- at least two instruments and six currencies
- at least four of six chronological folds have positive after-cost expectancy
- stress expectancy greater than zero
- after-cost expectancy exceeds deterministic random, shifted-level, and simple-rule baselines
- no single pair over 50 percent and no single currency over 50 percent of exposures
- leakage and accounting audits PASS
- search-adjusted lower expectancy bound over all 1,174 actual attempts is greater than zero

TRIAL ACCOUNTING:
- Add exactly ten data-scored candidates if the valid experiment completes.
- Cumulative computational-attempt lower bound becomes 1,174.
- Keep 112 separately as the pre-existing fully governed after-cost lineage.
- Baselines are fixed controls, not selected candidate configurations.
- If implementation is defective, repair and rerun unchanged without adding trials.

FAILURE ROUTING:
- A valid candidate failure must be preserved with exact metrics, both direction counterparts, break-even cost, fold behavior, concentration, baselines, multiple-testing result, deterministic fingerprints, prohibited repeats, and next distinct hypothesis.
- If no candidate passes, close this mechanism truthfully and continue after exact lock release.
- Do not run Stage 2 for a candidate that fails Stage 1.

VALIDATOR CHAIN:
- python automation/validators/aios_governance_validator.py --input automation/orchestration/work_packets/active/PKT-FOREX-024.md
- python automation/orchestration/autonomy_review/aios_packet_completeness_review.py --packet automation/orchestration/work_packets/active/PKT-FOREX-024.md --path-status SCOPED
- python -m pytest tests/forex_engine/test_forex_round_number_conditional_order_state_v1.py -q
- run the complete experiment twice in separate .aios/staging/PKT_FOREX_024 roots
- require byte-identical artifact names and bytes
- validate every JSON and deterministic gzip journal
- verify all 58 eligible pairs and every opened partition before use
- verify development-only timestamps, completed-candle next-bar execution, fold embargo, rollover exclusion, costs, baselines, journal completeness, exact candidate count, trial memory, postmortem, and holdout zero
- git diff --check
- git diff/readback of exactly the packet, engine, test, and runner paths
- automation/orchestration/validators/Test-LockRegistryIntegrity.DRY_RUN.ps1

STOP POINT:
After valid Stage-1 PASS artifacts, release only OCC59 and verify zero active locks. If there is no Stage-1 survivor, continue to the next materially distinct preregistered mechanism from the post-release state. Stop only for a protected-action approval or unavoidable runtime boundary. Never commit or push.

SAFE NEXT ACTION:
Claim OCC59, run the frozen experiment twice in isolated packet staging, validate byte identity, release OCC59, and route the truthful result through its frozen successor rule.

FINAL REPORT FORMAT:
Only VERIFIED EDGE FOUND, HUMAN APPROVAL REQUIRED, or a hash-verified RESUMABLE_EDGE_RESEARCH checkpoint caused by unavoidable platform/runtime termination.
