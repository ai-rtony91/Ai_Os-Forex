CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-027
PACKET NAME: Authoritative Forex Pair-Timeframe Data Matrix
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_62
LANE: FOREX_AUTHORITATIVE_DATA_MATRIX
WORKTREE: C:\Dev\Ai.Os
BRANCH: main

MISSION ID: MISSION-AIOS-001
MISSION NAME: AIOS Governed Self-Building Operating System
PROGRAM ID: PRG-FOREX-001
PROGRAM NAME: AIOS Forex Supervised Operational Validation Program V1
EPIC ID: EPC-FOREX-006
EPIC NAME: Historical Dataset Validation And Immutable Freezing V1
BUCKET ID: BKT-FOREX-010
BUCKET NAME: Dataset Evidence Validation Provenance And Freeze V1

ALLOWED PATHS:
- automation/orchestration/work_packets/active/PKT-FOREX-027.md
- automation/forex_engine/forex_authoritative_data_matrix_v1.py
- scripts/forex_delivery/run_forex_authoritative_data_matrix_v1.py
- tests/forex_engine/test_forex_authoritative_data_matrix_v1.py
- .aios/staging/PKT_FOREX_027/
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json only through claim and release scripts

FORBIDDEN PATHS:
- every path not listed above
- .git/
- AGENTS.md
- RISK_POLICY.md
- Reports/
- all source datasets and source evidence, which are read-only
- broker/
- oanda/
- secrets/
- credentials/
- live_trading/

APPROVAL AUTHORITY: Anthony explicitly directed the complete authoritative dataset audit and a machine-readable pair-by-granularity matrix before further strategy scoring. This packet reads metadata only and writes bounded engine, test, runner, packet, and isolated staging artifacts. Commit, push, merge, deployment, canonical promotion, data acquisition, broker access, credentials, PAPER, Practice, LIVE, orders, collectors, and money movement remain unauthorized.

PROTECTED ACTION RULE: Commit, push, merge, canonical promotion, and final-holdout execution each require separate explicit Human Owner approval. Approval does not transfer between actions.

PREFLIGHT:
- require branch main without switching branches
- classify the existing dirty tree as preserved current work
- require lock-registry integrity and zero active locks
- claim exactly LOCK_EAST_FOREX_AUTHORITATIVE_DATA_MATRIX_OCC62
- verify every metadata input SHA-256 before generating output

MISSION:
Build one deterministic, metadata-only matrix that reconciles the intended 68-pair universe, the 68-pair raw and 58-pair eligible M5 corpus, the 58-pair native H1 corpus, and the three-pair seven-granularity certified high-frequency corpus.

OBJECTIVE:
Create and reproduce an exact 68-pair by 14-granularity matrix without opening any price partition, candle file, validation period, or final holdout.

REQUIRED INPUTS:
- .aios/runtime/forex_historical_dataset_freezes_v1/pending/AIOS_FOREX_HISTORICAL_DATASET_VALIDATION_RECEIPT.json
- .aios/runtime/forex_frozen_21_series_edge_research_v1/AIOS_FOREX_PHASE1_RESEARCH_CONTRACT.json
- .aios/runtime/forex_m5_immutable_corpus_v2/manifest.json
- .aios/runtime/forex_m5_immutable_corpus_v2/FROZEN.json
- .aios/runtime/forex_cross_sectional_short_horizon_reversal_v1/AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CONTRACT.json
- .aios/runtime/forex_multi_regime_corpus_v3/manifests/manifest.json
- Reports/forex_delivery/AIOS_FOREX_PAIR_COVERAGE_MATRIX_V3.json

REQUIREMENTS:
- Audit TICK, S1, S5, S10, S15, S30, M1, M2, M4, M5, M10, M15, M30, and H1 for all 68 intended pairs.
- Produce exactly 952 sorted pair-granularity rows.
- Label native, derived-on-demand, absent, raw-present-ineligible, and certified evidence separately.
- Record pair, base, quote, granularity, source, source path and SHA-256, dataset identity and SHA-256, timestamps, records, partitions, bid/ask/mid/spread evidence, gaps, duplicates, order, completed-candle status, certification, development and walk-forward eligibility, source-specific final-holdout boundary, holdout status, and exact exclusion reason.
- Record TICK and S1 as absent.
- Record M10, M15, and M30 as causal closed-M5 derivations, never as native files.
- Preserve the different high-frequency and M5/H1 holdout boundaries.
- Record stale contradictory reports as superseded evidence, not as current truth.
- Do not open source market rows or count this metadata audit as a strategy trial.
- Run twice in isolated directories and require byte-identical artifacts.

VALIDATOR CHAIN:
- packet governance and completeness
- focused regression tests
- exact input SHA-256 checks
- schema, row-count, uniqueness, ordering, coverage, derivation, absence, eligibility, holdout, safety, and metadata-only tests
- two-run byte-identical artifact validation
- lock registry integrity
- Git diff check
- exact OCC62 release and zero-active-lock verification

STOP POINT:
After deterministic matrix validation and OCC62 release, immediately resume Stage-0 successor selection without opening price outcomes.

SAFE NEXT ACTION:
Use the matrix plus cumulative rejection memory to admit only a materially distinct, data-compatible bounded hypothesis.

FINAL REPORT FORMAT:
Short milestone only while the edge-research goal remains active. No commit and no push.
