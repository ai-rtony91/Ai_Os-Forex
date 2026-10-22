# AIOS Forex Supertrend Weekly Paper Evidence V1

## Campaign status

- STATUS: READY_FOR_PAPER_COLLECTION
- CAMPAIGN_ID: AIOS-FOREX-P1-SUPERTREND-30-TRADE-PAPER-CAMPAIGN-V1
- STRATEGY_NAME: supertrend_pullback_v1
- CONFIGURATION: ATR 3, multiplier 2.0
- MODE: PAPER_ONLY
- PAPER_ONLY: true
- QUALIFYING_TRADES: 0/30
- ACTIVE_POSITION_STATUS: NONE
- WEEKLY_EVIDENCE_STATUS: READY_FOR_COLLECTION
- VALIDATION_STATUS: PASS
- RUNTIME_LAUNCH_STATUS: NOT_LAUNCHED
- COMMIT_STATUS_AT_REPORT_CREATION: NOT_YET_COMMITTED

## Weekly evidence

No qualifying paper trades were collected by this implementation packet. The dedicated runner will group accepted, already-closed paper records by ISO week and report trade count, wins, losses, flat results, net paper profit-and-loss, and expectancy for each week.

## Evidence rules

- Only `supertrend_pullback_v1` records with ATR period 3 and multiplier 2.0 qualify.
- Only records explicitly marked `PAPER_ONLY` and `paper_only: true` qualify.
- Duplicate trade IDs, wrong strategy settings, non-paper evidence, and any record claiming broker, credential, network, practice-order, or live-trade activity fail closed.
- Thirty qualifying records are required before campaign status becomes complete.
- The ledger and reports use dedicated Supertrend filenames and do not mutate Generic P1 campaign state.

No runtime, broker, credential, practice-order, live-order, or money-movement action occurred. A separate owner-approved packet is required to start paper collection.
