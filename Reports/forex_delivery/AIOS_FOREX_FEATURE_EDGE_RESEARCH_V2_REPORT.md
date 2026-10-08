# AIOS Forex Feature Edge Research V2

WHAT HAPPENED:

Packet 012 repaired the shared cost contract, built a 3,906,863-event causal feature dataset, and exhausted 26 frozen feature candidates without a Development passer.

IS IT SAFE:

YES. Research was local and PAPER-only; broker writes, Practice orders, OANDA LIVE, credential access, and money movement were all false.

WHAT DO I DO NEXT:

Review the protected publication handoff after repository changes are separated from unrelated dirty work; do not enter LIVE credentials.

HOW CLOSE ARE WE:

Estimated readiness: 35% to profitable-edge proof. Execution and cost integrity are proven, but no candidate passed Development.

WHICH MODE SHOULD I USE:

INSTANT for review.

CONTINUATION AUDIT:

- Current phase: `TERMINAL_REPORT`
- Last completed action: research exhaustion classification
- First incomplete action: `NONE`
- Next-action queue: empty
- Authorized internal work remaining: false
- Safe independent work remaining: false
- External dependency present: false
- Stop-Gate result: `PASS`
- Objective terminal basis: all 26 frozen candidates were processed with LONG/SHORT isolation; zero passed Development
- Exact resume trigger: new governed methodology or data authorization
- Exact resume command: none for Packet 012

TECHNICAL DETAILS:

## Preflight

- Repository: `C:\Dev\Ai.Os`
- Branch: `main`
- HEAD: `b86c65140ed03d53d6c8d6c3618e50da0502f51b`
- Origin relationship: ahead 7
- Lock: `AIOS-LOCK-a2eb257a6de346ccb5791025b45396df`
- Duplicate writer evidence: no prior active lock; one foreground packet process only

## Cost repair

- Old contract: synthetic adjusted entry plus full explicit round-trip deduction could charge spread/slippage twice.
- New contract: `RAW_REFERENCE_EXPLICIT_COST` or `EXECUTABLE_BID_ASK`; spread is deducted only in the raw-reference model.
- Mixed adjusted-fill plus explicit-cost paths fail closed.
- Direct integration migrated: `automation/forex_engine/backtest.py` now keeps reference fills raw and applies one explicit round-trip charge.
- Prior research impact: Packet 009/010 and certified edge research used direct bid/ask paths and remain `UNAFFECTED`.

## Certified research base

- Reference executor: `6dd60fb853a088636f2367a0f58e2a0c305f68ac72f83bd20e9ae6114f2aeba5`
- Corpus: `AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2`
- Corpus fingerprint: `44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a`
- Manifest SHA-256: `1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b`
- Eligible pairs: 58 of 68 attempted
- Frozen status: `FROZEN_VALID`

## Feature protocol and event data

- Protocol hash: `f522fb4930fbc880424fa700def02b8ecaa9c332bfeac4e1e5a72486d88e50e8`
- Candidate count: 26 (cap 30)
- Event-manifest hash: `2afb5c083198bbae0209fa72d22c18931481e898576ad1138171f360e6000bd2`
- Total unique events: 3,906,863
- Breakout resets: 858,630
- Failed breakouts: 858,636
- Volatility transitions: 472,966
- Trend pullbacks: 524,888
- Cross-currency divergences: 1,147,989
- Strength alignments: 43,754
- Duplicate EVENT_ID count: 0

## Candidate research

- Generation A best adequately sampled result: `A-04 LONG`, 132,042 trades, -0.4871R expectancy, PF 0.4400, -64,324R, 100% drawdown.
- Generation B best result: `B-01 LONG`, 73,752 trades, -0.5363R expectancy, PF 0.3927, -39,555R, 100% drawdown.
- Generation C positive result: `C-01 LONG`, 12 trades, +0.6667R expectancy, PF 2.1429, +8R, 1.00% drawdown; rejected for sample size and breadth.
- Generation C `C-01 SHORT`: 369 trades, -0.0325R expectancy, PF 0.9570, 10.76% drawdown; rejected.
- Development passers: 0
- Registry-wide null repetitions: 500
- Best-of-registry null 95th-percentile expectancy: 1.0R
- Bootstrap candidates: none because no candidate cleared the Development gate
- Validation: not opened
- Sealed historical Holdout: not opened
- Finalists: none
- Forward: not started
- V2: not created
- PAPER V2: not started

## Terminal classification

- Status: `RESEARCH_EXHAUSTED_FEATURE_EDGE_NOT_FOUND`
- Dominant failure: `NO_INCREMENTAL_FEATURE_EDGE`
- OANDA LIVE contacted: false
- Broker write: false
- Practice order: false
- Money movement: false

ATTACK_TO_FINISH:

- blocker_id: `NO_BLOCKER`
- blocker_status: `COMPLETE`
- exact_blocker: finite Packet 012 feature registry exhausted without a robust Development edge
- canonical_owner_file: `automation/forex_engine/forex_feature_edge_research_v2.py`
- test_file: `tests/forex_engine/test_forex_feature_edge_research_v2.py`
- runner_script: `python -B -m automation.forex_engine.forex_feature_edge_research_v2 --execute`
- missing_evidence_field: `NONE`
- unlock_status_required: `COMPLETE`
- next_packet_name: deeper feature research or extended-data methodology packet
- owner_action_required: review this report; do not enter LIVE credentials
- stop_condition: `RESEARCH_EXHAUSTED_FEATURE_EDGE_NOT_FOUND`
- no_bloat_guard: do not rerun this registry, rebuild Corpus V2, resurrect retired price-only families, or create LIVE/PAPER paths without a promoted finalist
