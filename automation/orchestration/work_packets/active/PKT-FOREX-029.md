CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-029
PACKET NAME: Abnormal OANDA Price-Update Count Response Stage-0 Qualification
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_64
LANE: FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_STAGE0
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
- automation/orchestration/work_packets/active/PKT-FOREX-029.md
- automation/forex_engine/forex_abnormal_price_update_response_stage0_v1.py
- scripts/forex_delivery/run_forex_abnormal_price_update_response_stage0_v1.py
- tests/forex_engine/test_forex_abnormal_price_update_response_stage0_v1.py
- .aios/staging/PKT_FOREX_029
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json

READ-ONLY INPUT PATHS:
- .aios/runtime/forex_m5_immutable_corpus_v2/FROZEN.json
- .aios/runtime/forex_m5_immutable_corpus_v2/manifest.json
- .aios/runtime/forex_m5_immutable_corpus_v2/partitions/
- .aios/staging/PKT_FOREX_027/
- .aios/staging/PKT_FOREX_028/
- existing strategy, candidate, rejection, and multiple-testing ledgers

FORBIDDEN PATHS:
- every write path not listed above
- any source dataset mutation
- validation rows after 2025-04-01T00:00:00Z
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

APPROVAL AUTHORITY: Anthony explicitly directed continuous high-throughput historical edge research, authorized public-source hypothesis work, and required Stage-0 duplicate, data, and eligibility gates. This packet performs a bounded development-data quality inspection and preregistration only. Commit, push, merge, canonical promotion, broker access, credentials, PAPER, Practice, LIVE, orders, collectors, money movement, and final-holdout access remain unauthorized.

PROTECTED ACTION RULE: Commit, push, merge, canonical promotion, and final-holdout execution each require separate explicit Human Owner approval. Approval does not transfer between actions.

PREFLIGHT:
- require PKT-FOREX-027 completion SHA-256 07bee0a186f6ac67f3edd6e919283c4688049f2c22d8691cdd2a8bf837c034df
- require authoritative M5 corpus fingerprint 44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a
- require PKT-FOREX-028 decision SHA-256 aa184b6ac38eba6dcaaed526b1e5f58beab29b5a5b6058f8b7c6bf541625fb4c
- require registry integrity and zero active locks
- claim exactly LOCK_EAST_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_STAGE0_OCC64

MISSION:
Determine whether OANDA M5 price-update counts can support a distinct, deterministic, point-in-time abnormal-activity response experiment across the certified 58-pair corpus.

OBJECTIVE:
Qualify provider-field semantics, data quality, duplicate independence, and bounded preregistration without computing any forward return or strategy performance.

REQUIREMENTS:
- Modify the lock registry only through the approved claim and release scripts.
- Call the field OANDA_PRICE_UPDATE_COUNT_PROXY, never traded, transaction, tick, or notional volume.
- Record official OANDA documentation stating candle volume is the number of prices created during the interval.
- Treat Cespa, Gargano, Riddiough, and Sarno (2022) CLS transaction-volume findings as indirect hypothesis input only, not provider-field equivalence or edge proof.
- Read only development partitions from 2024-01 through 2025-03 inclusive.
- Verify every selected partition hash against the frozen manifest before reading rows.
- Check chronological uniqueness, completed-candle flags, nonnegative integral volume, bid/ask/mid availability, positive spreads, gaps, zero or constant series, and robust same-minute-of-week history feasibility.
- Require at least 40 eligible pairs and at least 10 represented currencies.
- Open no validation or final-holdout rows and calculate no forward returns.
- Compare the mechanism against all rejection fingerprints and block cosmetic indicator, volatility, session, or pure-price variants.
- If eligible, freeze exactly eight candidates: volume-z threshold 2 or 3, continuation or reversal, and 3 or 6 M5-bar maximum holding period.
- Freeze exact signal, execution, cost, risk, exposure, baseline, fold, purge, embargo, stability, breadth, multiple-testing, reproduction, and rejection gates before Stage 1.
- Count zero actual data-scored candidates in this packet.

VALIDATOR CHAIN:
- packet governance and completeness
- focused unit tests
- frozen-manifest hash verification
- development-boundary and sealed-holdout assertions
- provider-field semantics assertions
- row schema, timestamp, completed-candle, quote, spread, volume, gap, and history-feasibility checks
- duplicate and fingerprint checks
- exact eight-candidate preregistration check
- deterministic two-run byte comparison
- path guard
- lock registry integrity
- Git diff check
- exact OCC64 release and zero-active-lock verification

STOP POINT:
After deterministic Stage-0 PASS or valid fail-closed rejection is preserved and OCC64 is released, continue to Stage 1 only if all eligibility gates pass.

SAFE NEXT ACTION:
If admitted, execute only the frozen eight-candidate development screen; otherwise choose the next materially distinct hypothesis.

FINAL REPORT FORMAT:
Short milestone only while research continues. No commit and no push.
