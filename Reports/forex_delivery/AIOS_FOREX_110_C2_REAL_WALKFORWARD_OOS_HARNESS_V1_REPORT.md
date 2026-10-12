# AIOS Forex 110 C2 Real Walk-Forward OOS Harness V1

Packet ID: `PKT-FOREX-110-C2-REAL-WALKFORWARD-OOS-HARNESS-BUILD-V1`
Harness status: `BLOCKED_REAL_WALKFORWARD_OOS_HARNESS`
Candidate: `c2-eur-buy-stronger-review-ready`
Candidate alignment: `ALIGNED`
Walk-forward/OOS status: `WALK_FORWARD_OOS_READY`

## Sanitized Evidence Fields
- windows_total: `6`
- windows_passed: `6`
- oos_segments_total: `4`
- oos_segments_passed: `4`
- min_pass_rate: `0.75`
- max_drawdown: `0.22`
- max_allowed_drawdown: `0.5`
- sanitized: `True`
- evidence_age_days: `1.0`
- max_evidence_age_days: `7`

## Blockers
- default walk-forward/OOS inputs are synthetic sample data
- source authenticity is not independently verified
- NO_INDEPENDENT_VERIFIER_CONNECTED

## Permission Locks
- next_demo_trade_allowed: `false`
- broker_action_allowed: `false`
- real_money_allowed: `false`
- compounding_allowed: `false`
- bank_movement_allowed: `false`
- live_trading_allowed: `false`
- credential_access_allowed: `false`
- order_submission_allowed: `false`
- owner_approval_created: `false`

## Next Safe Action
Provide independently verified candidate-bound source, trades and costs through the existing evidence owner. Do not trade.
