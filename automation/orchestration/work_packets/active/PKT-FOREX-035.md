CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-035
PACKET NAME: CFTC Asset-Manager Weekly Change Response Stage-0 Gate
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_70
LANE: FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_STAGE0
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
- automation/orchestration/work_packets/active/PKT-FOREX-035.md
- automation/forex_engine/forex_cftc_asset_manager_weekly_change_stage0_v1.py
- scripts/forex_delivery/run_forex_cftc_asset_manager_weekly_change_stage0_v1.py
- tests/forex_engine/test_forex_cftc_asset_manager_weekly_change_stage0_v1.py
- .aios/staging/PKT_FOREX_035
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json

READ-ONLY INPUT PATHS:
- .aios/staging/PKT_FOREX_019_022_R1/revision2/PKT_FOREX_019_022_R1_CORRECTIVE_PROMOTION_RECEIPT.json
- .aios/staging/PKT_FOREX_019_022_R1/revision2/PKT_FOREX_019_022_R1_PROMOTION_COMPLETION.json
- .aios/staging/PKT_FOREX_019_022_R1/revision2/prepromotion_rollback/ROLLBACK_MANIFEST.json
- .aios/staging/PKT_FOREX_019_022_R1/revision2/PKT019/promotion
- .aios/staging/PKT_FOREX_019_022_R1/revision2/PKT020/promotion
- .aios/staging/PKT_FOREX_019_022_R1/revision2/PKT021/promotion
- .aios/staging/PKT_FOREX_019_022_R1/revision2/PKT022/promotion
- .aios/runtime/forex_cftc_crowding_unwind_price_confirmation_v1
- .aios/runtime/forex_cftc_positioning_acceleration_price_continuation_v1
- .aios/runtime/forex_cftc_participant_divergence_price_confirmation_v1
- .aios/runtime/forex_cftc_dealer_inventory_pressure_reversal_v1
- Reports/forex_delivery/AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_V1_REPORT.md
- Reports/forex_delivery/AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_REJECTION_V1.json
- Reports/forex_delivery/AIOS_FOREX_CFTC_POSITIONING_ACCELERATION_PRICE_CONTINUATION_V1_REPORT.md
- Reports/forex_delivery/AIOS_FOREX_CFTC_POSITIONING_ACCELERATION_PRICE_CONTINUATION_REJECTION_V1.json
- Reports/forex_delivery/AIOS_FOREX_CFTC_PARTICIPANT_DIVERGENCE_PRICE_CONFIRMATION_V1_REPORT.md
- Reports/forex_delivery/AIOS_FOREX_CFTC_PARTICIPANT_DIVERGENCE_PRICE_CONFIRMATION_REJECTION_V1.json
- Reports/forex_delivery/AIOS_FOREX_CFTC_DEALER_INVENTORY_PRESSURE_REVERSAL_V1_REPORT.md
- Reports/forex_delivery/AIOS_FOREX_CFTC_DEALER_INVENTORY_PRESSURE_REVERSAL_REJECTION_V1.json
- .aios/runtime/forex_information_corpus_v1/frozen/FROZEN.json
- .aios/runtime/forex_information_corpus_v1/manifests/manifest.json
- .aios/runtime/forex_information_corpus_v1/normalized/cftc_2024.json
- .aios/runtime/forex_information_corpus_v1/normalized/cftc_2025.json
- .aios/staging/PKT_FOREX_027/run1/AIOS_FOREX_AUTHORITATIVE_PAIR_TIMEFRAME_MATRIX_V1.json
- .aios/staging/PKT_FOREX_036/PKT_FOREX_036_COMPLETION.json

FORBIDDEN PATHS:
- every write path not listed above
- .aios/runtime/forex_information_corpus_v1/normalized/cftc_2026.json
- market price outcomes
- validation price data
- final holdout data
- source dataset mutation
- .git/
- AGENTS.md
- RISK_POLICY.md
- Reports/
- broker/
- oanda/
- secrets/
- credentials/
- live_trading/

APPROVAL AUTHORITY: Anthony explicitly authorized these exact PKT-FOREX-035 paths and the OCC70 claim/release lifecycle on 2026-09-05. Commit, push, merge, pull request, branch switch, reset, stash, canonical promotion, broker access, credentials, PAPER, Practice, LIVE, orders, collectors, money movement, validation-price access, and final-holdout access remain unauthorized.

PROTECTED ACTION RULE: Approval is exact and non-transferable. Conditional PKT-FOREX-036 authority activates only if this Stage-0 packet passes every gate.

PREFLIGHT:
- require the 32 PKT-FOREX-019 through 022 canonical artifacts to match receipt SHA-256 345295f9ff2029424479a73b1601418ffa0ae2accce968396bd8fae5858caddc and aggregate ba7a446a36a17c3497edd1d4efe500ac7768ba2d0733d6fe748380ff47e5d62c
- require all four prior CFTC rejected families and 48 unique candidate fingerprints in cumulative failure memory
- require the preserved direct-nine PKT-FOREX-036 completion hash c641f3d1b255f8f6a01e2a2e7739c780c78da6e9f09876b0dbacd3e365e31c50
- require cumulative actual-attempt lower bound 1210 and governed after-cost candidate count 158
- require information corpus hash 57da729226ebd675d7c79f182510f0612fc2f93cd0f20a05abed64243163d854
- require H1 corpus hash 4357f24113ba54b9a6f8d6a3d87860109ca7429dbbd627b20c3d5a30540c6b32
- require registry integrity and zero active locks before claiming OCC70
- require exact South African rand coverage label and include USD_ZAR

MISSION:
Run a deterministic no-price-outcome corrective Stage-0 duplicate, semantic, 58-pair data-compatibility, capacity, public-source, counterevidence, and preregistration gate for weekly changes in public TFF asset-manager net positioning.

OBJECTIVE:
Decide whether exactly ten fixed original, exact-reverse, and symmetric candidates may proceed to a bounded chronological Stage-1 development screen without repeating rejected CFTC level, leveraged-fund acceleration, participant-divergence, dealer-inventory, or price-confirmation mechanisms.

REQUIREMENTS:
- Modify the lock registry only through approved claim and release scripts.
- Open no market price rows and calculate no forward returns or performance.
- Do not open or hash normalized 2026 CFTC data.
- Audit all 58 frozen-certified development-eligible H1 pairs and emit exactly one eligibility row per pair.
- Use every causal mapping: nine direct USD pairs plus 24 derived crosses whose base and quote currencies both have point-in-time CFTC contracts.
- Define each pair signal as base-currency z-score minus quote-currency z-score, with USD fixed to neutral zero.
- Exclude exactly 25 pairs lacking a required non-USD CFTC contract and preserve their eligibility for unrelated price-based research.
- Freeze five direction variants by two holding periods: 6 and 12 H1 bars.
- Compute current weekly change z-score against exactly 26 prior changes, excluding current change from normalization.
- Freeze publication lag, revision behavior, completed-candle execution, prior-only ATR, stop, spread, slippage, risk, fold, purge, embargo, baseline, rejection, promotion, journal, and reproduction rules before Stage 1.
- Require no-trade, deterministic random, prior-week price continuation/reversal, raw change-sign, and position-level baselines.
- Record CFTC, BIS, NBER, Kremens placebo/weak-predictor counterevidence, and FXAbsolute process guidance as unverified hypothesis inputs only.
- Preserve cumulative multiple-testing counts at 1210 attempts and 158 governed candidates because Stage 0 scores no outcomes; freeze a ten-candidate Stage-1 increment to 1220 and 168.
- Record a no-outcome pair/grouping inventory and one consolidated missing-capability audit without modifying unrelated factory files.
- Run twice in isolated staging and require byte-identical deterministic artifacts.

VALIDATOR CHAIN:
- packet governance and completeness
- focused and regression tests
- receipt, promotion, rollback, manifest, information-corpus, H1-corpus, and source-file hash checks
- four-family and 48-candidate cumulative failure-memory checks
- exact 58-row mapping, 33 eligible pairs, nine direct mappings, 24 derived crosses, 25 exclusions, and SO AFRICAN RAND to USD_ZAR
- causal availability, current-excluded prior-26 normalization, six fold, and exact ten-candidate checks
- public source and placebo counterevidence completeness
- zero market-price, validation-price, and holdout-row access
- cumulative trial memory unchanged
- two-run byte-identical artifact comparison
- path guard
- lock registry integrity
- Git diff check
- exact OCC70 release and zero-active-lock verification

STOP POINT:
After validator-PASS Stage-0 artifacts are preserved and OCC70 is released, execute PKT-FOREX-036 only if the decision is ADMIT_STAGE1_LOW_COST_ONLY.

SAFE NEXT ACTION:
Do not score market outcomes until the frozen Stage-1 preregistration hash is verified from both Stage-0 runs.

FINAL REPORT FORMAT:
Short milestone only while research continues. No commit and no push.
