CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-036
PACKET NAME: CFTC Asset-Manager Weekly Change Response Stage-1 Development Screen
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_71
LANE: FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_STAGE1
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
- automation/orchestration/work_packets/active/PKT-FOREX-036.md
- automation/forex_engine/forex_cftc_asset_manager_weekly_change_stage1_v1.py
- scripts/forex_delivery/run_forex_cftc_asset_manager_weekly_change_stage1_v1.py
- tests/forex_engine/test_forex_cftc_asset_manager_weekly_change_stage1_v1.py
- .aios/staging/PKT_FOREX_036
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json

READ-ONLY INPUT PATHS:
- automation/forex_engine/forex_cftc_asset_manager_weekly_change_stage0_v1.py
- .aios/staging/PKT_FOREX_035/expansion58/run1/AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_PREREGISTRATION.json
- .aios/staging/PKT_FOREX_035/PKT_FOREX_035_EXPANSION58_COMPLETION.json
- .aios/runtime/forex_information_corpus_v1/manifests/manifest.json
- .aios/runtime/forex_information_corpus_v1/normalized/cftc_2024.json
- .aios/runtime/forex_information_corpus_v1/normalized/cftc_2025.json
- .aios/runtime/forex_multi_regime_corpus_v3/manifests/manifest.json
- the exact 33 H1 artifact paths frozen in the expansion58 preregistration and corpus manifest

FORBIDDEN PATHS:
- every write path not listed above
- .aios/runtime/forex_information_corpus_v1/normalized/cftc_2026.json
- every H1 price row at or after 2025-04-01T00:00:00Z
- validation evidence
- final holdout evidence
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

APPROVAL AUTHORITY: Anthony explicitly authorized these exact PKT-FOREX-036 paths and the OCC71 claim/release lifecycle on 2026-09-05, conditional on PKT-FOREX-035 Stage-0 PASS. That condition passed. No other protected action is authorized.

PROTECTED ACTION RULE: Approval is exact and non-transferable. Commit, push, merge, pull request, branch switch, reset, stash, canonical promotion, broker access, credentials, PAPER, Practice, LIVE, orders, collectors, money movement, validation access, and final-holdout access remain unauthorized.

PREFLIGHT:
- require Stage-0 engine SHA-256 8dbe5165f198252160c81715d27bc71a3e72b0885c60427fb4f0fa7b08b34b47
- require frozen preregistration SHA-256 8fc26b4ecdbf5af4a60cf33137baff48c59cb37a854c5c97cc29e701d78aa0d6
- require Stage-0 completion SHA-256 882f14878c8f65d3e645335ce1a01fe311f1d1c82c0f5e5875fda33b8ff51fae
- require H1 manifest SHA-256 f784867978464aee59f4b3377eca013237378fd8c3a61c068f8c111ce6451d32
- require Stage-0 result ADMIT_STAGE1_LOW_COST_ONLY
- require exact mechanism fingerprint e2565e2d94c7411c43f57dc3bbd2d6559f25991f9f07b852a5e447c7f02227d5
- require OCC70 released, registry integrity, and zero active locks before exact OCC71 claim

MISSION:
Score exactly ten frozen candidates on chronological development evidence only, with realistic executable costs, exact inverse arms, strict baselines, full journals, deterministic two-run reproduction, and truthful failure handling.

REQUIREMENTS:
- Open and score no H1 row at or after 2025-04-01T00:00:00Z.
- Do not open the normalized 2026 CFTC artifact or any final-holdout artifact.
- Use exactly 1,254 causal pair-week signals across 33 mapped pairs: nine direct USD pairs and 24 base-minus-quote derived crosses.
- Enforce Friday publication availability before Monday 07:00 UTC entry, prior-only 26-change normalization, completed H1 candles, prior-only ATR20, 1.5-ATR stop, no target, and pre-rollover time exit.
- Use observed bid/ask plus 0.10 pip per side for base costs and 0.50 pip per side for stress; financing is not applicable because every trade exits before rollover.
- Cap total initial basket risk at 0.25 percent, each pair at 0.007575757575757576 percent, and each currency's gross initial risk at 0.10 percent; under-use risk where a cap binds.
- Compare strictly with zero and all frozen after-cost random, price-only, raw-change, and net-level baselines.
- A negative or zero expectancy candidate must never pass the baseline gate.
- Require gross and stressed expectancy above zero, net profit factor at least 1.05, drawdown at most 15 percent, at least 100 trades, four of six positive folds, ten positive pairs, seven positive currencies, pair positive-profit share no greater than 0.25, currency share no greater than 0.35, and the preregistered global-search-adjusted screen.
- Record predictive correlation, session dependence, turnover, break-even cost, direction balance, regime breadth, and cumulative counts 1210 to 1220 attempts and 158 to 168 governed candidates.
- Preserve all trades and losses, exact reverse identity, symmetric union identity, fold/regime/concentration diagnostics, break-even cost, and all ten cumulative scored trials.
- Run twice in isolated staging and require byte-identical artifacts.
- If all candidates fail, preserve the complete post-mortem and deterministic rejection fingerprint without parameter rescue.

VALIDATOR CHAIN:
- packet governance and completeness
- focused tests and prior CFTC regression tests
- frozen input, corpus, source, and artifact hash checks
- timestamp-first lower skip and validation-boundary stop tests
- CFTC publication-lag and prior-26 leakage tests
- exact candidate, reverse-arm, symmetric-union, baseline, cost, risk, fold, breadth, concentration, journal, and cumulative-trial tests
- JSON and AST checks
- two-run byte-identical artifact comparison
- path and Git-diff checks
- registry integrity
- exact OCC71 release and zero-active-lock verification

STOP POINT:
After PKT-FOREX-036 evidence is validator-PASS and OCC71 is released, continue only inside already authorized paths. Request exact new protected write authority for a successor or Stage-2 packet if required.

SAFE NEXT ACTION:
Preserve a hash-verified RESUMABLE_EDGE_RESEARCH checkpoint if no survivor exists or new protected write authority is required.

FINAL REPORT FORMAT:
Return only VERIFIED EDGE FOUND, HUMAN APPROVAL REQUIRED, or forced RESUMABLE checkpoint. No commit and no push.
