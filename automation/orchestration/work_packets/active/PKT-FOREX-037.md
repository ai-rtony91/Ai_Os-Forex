CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-037
PACKET NAME: Edge Factory Repair And Conditional Round-Number Stage-0 Gate
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_72
LANE: FOREX_EDGE_FACTORY_REPAIR_ROUND_NUMBER_STAGE0
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
- automation/orchestration/work_packets/active/PKT-FOREX-037.md
- automation/forex_engine/forex_high_throughput_edge_factory_v1.py
- scripts/forex_delivery/run_forex_high_throughput_edge_factory_v1.py
- tests/forex_engine/test_forex_high_throughput_edge_factory_v1.py
- .aios/staging/PKT_FOREX_037
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json only for exact OCC72 claim and release

READ-ONLY INPUTS:
- PKT-FOREX-019 through PKT-FOREX-036 staged completion, rejection, ledger, and post-mortem evidence
- .aios/runtime/forex_m5_immutable_corpus_v2/manifest.json
- .aios/staging/PKT_FOREX_027/run1/AIOS_FOREX_AUTHORITATIVE_PAIR_TIMEFRAME_MATRIX_V1.json
- .aios/runtime/forex_multipair_m5_replay_v1_repaired_v2/replay_cache.json
- the rejection inputs listed by run_forex_high_throughput_edge_factory_v1.py

FORBIDDEN PATHS AND ACTIONS:
- every write path not listed above
- market-price outcome rows
- validation and final-holdout rows
- source dataset mutation
- .git, protected governance, Reports, broker, OANDA, secrets, credentials, PAPER, Practice, LIVE, orders, money movement, deployment
- commit, push, merge, pull request, branch switch, reset, stash, destructive cleanup

APPROVAL AUTHORITY: Anthony explicitly approved these exact paths and the OCC72 lifecycle on 2026-09-06. No other protected action is authorized.

PREFLIGHT:
- require repository C:\Dev\Ai.Os on main while preserving all unrelated dirty work
- require PKT-FOREX-036 expansion checkpoint SHA-256 8bdb2b2e23e7fdc7812ba07f39d7183e9c4a5e603403e96491f95a9a09187dcc
- require cumulative counts 1220 actual-attempt lower bound and 168 governed after-cost candidates
- require registry integrity and zero active locks before OCC72 claim
- require exact immutable M5 manifest, pair/timeframe matrix, and instrument-metadata hashes

MISSION:
Repair the existing compact high-throughput research factory and produce a deterministic no-market-outcome Stage-0 eligibility and preregistration package for the Conditional Round-Number Order-Cluster Edge.

REQUIREMENTS:
- retain the compact one-million-item no-data hypothesis catalog without materializing one million files or counting proposals as trials
- audit all 58 certified M5 pairs and derive pip precision only from frozen instrument metadata
- verify H1 context for the same 58 pairs and the separate three-pair S5/S10/S15/S30/M1/M2/M4 finalist scope
- freeze independent approach-rejection and completed-cross-continuation states, exact inverse arms, 00/50 levels, matched 25/75 controls, 2/5/10-pip approaches, 0/1-pip cross buffers, 15/30/60-minute holds, 60-minute lockout, 1.0 ATR20 stop, 2.0R target, bid/ask costs, slippage, folds, baselines, concentration, multiplicity, reproduction, champion, and single-use holdout gates
- preserve the 135 candidate configurations as proposed and unscored at Stage 0
- open zero price outcomes, validation rows, and holdout rows
- emit minimal deterministic factory, dataset, memory, source, cluster, preregistration, capability, closure, manifest, receipt, report, and checkpoint artifacts twice

VALIDATOR CHAIN:
- packet identity, authority, path, and lock checks
- Python AST and JSON checks
- focused factory regression tests
- PKT-FOREX-019 through PKT-FOREX-036 closure and cumulative-memory checks
- exact 58-pair M5/H1 and authoritative pip-metadata checks
- exact 135-candidate uniqueness and inverse-direction checks
- no-trade, arbitrary-level, generic-rule and ungated baseline contract checks
- zero outcome, validation, holdout, broker and credential access checks
- two isolated byte-identical reproduction runs
- git diff --check
- exact OCC72 release and zero-active-lock verification

STOP POINT:
After validator-PASS artifacts are hash-verified and OCC72 is released, continue only through separately approved paths. PKT-FOREX-038 Stage 1 requires exact new protected-write approval.

FINAL REPORT:
Return only VERIFIED_EDGE_FOUND, one exact HUMAN_APPROVAL_REQUIRED sentence, or a hash-verified RESUMABLE_EDGE_RESEARCH checkpoint. No commit or push.
