# AIOS Forex Edge Autopilot V1

Packet ID: `PKT-FOREX-EDGE-AUTOPILOT-V1`
Status: TARGET_REVIEW_CANDIDATES_FOUND
Stop reason: TARGET_REVIEW_CANDIDATES_FOUND_REPO_SAFE
Cycles completed: 1/3
Candidates found: 3/3

## Candidate Basket
- c2-eur-buy-stronger-review-ready
  - Tier: PRIMARY_EDGE_PROOF
  - Status: PROVEN_FOR_OPERATOR_REVIEW_ONLY
  - Source: profit_truth_lock_and_walkforward_oos_truth_lock
  - Permissions: review_only_no_demo_live_or_order_authority
- CANDIDATE-EURUSD-C1
  - Tier: SECONDARY_REVIEW_READY
  - Status: REVIEW_READY_NEEDS_BROKER_SLIPPAGE_RECONCILIATION
  - Source: candidate_selector_hardening
  - Permissions: review_only_no_demo_live_or_order_authority
- supertrend
  - Tier: STRATEGY_REVIEW_ONLY
  - Status: SUPER_TREND_PROOF_REVIEW_READY
  - Source: strategy_promotion_router
  - Permissions: review_only_no_demo_live_or_order_authority

## Proof Gates
- broker_boundary_status: OWNER_GATED_BROKER_CONNECTION_PROOF_READY_FOR_REVIEW
- ledger_status: PROFIT_PROOF_LEDGER_PROMOTABLE
- profit_proof_status: PROVEN
- profit_truth_lock_status: PROVEN
- selector_status: REVIEW_READY_CANDIDATE_SELECTED
- statistical_classification: STATISTICAL_PROFIT_PROOF_READY
- strategy_promotion_status: STRATEGY_PROMOTION_REVIEW_READY
- trusted_22_6_status: TRUSTED_PROFIT_22_6_STRATEGY_REVIEW_READY
- walk_forward_oos_status: PROVEN
- walkforward_truth_lock_status: PROVEN

## Rejected / Blocked Candidates
- weak-negative-expectancy: PROFIT_PROOF_LEDGER_BLOCKED_NEGATIVE_EXPECTANCY (expectancy -0.11 is not positive, profit factor 0.76 below minimum 1.25)
- weak-low-profit-factor: PROFIT_PROOF_LEDGER_BLOCKED_LOW_PROFIT_FACTOR (profit factor 1.18 below minimum 1.25)
- CANDIDATE-GBPUSD-WEAK: REJECTED_BY_HARDENING (insufficient_sample, low_profit_factor, missing_walk_forward_evidence, weak_evidence_depth, missing_owner_review_readiness)
- CANDIDATE-USDJPY-DRAWDOWN: REJECTED_BY_HARDENING (excessive_drawdown, mitigation_worsened)

## Safety
- Broker/API calls: false
- Credential/env reads: false
- Demo/live/order authority: false
- Scheduler/daemon/background loop started: false

## Next Safe Action
Review the ranked basket, then run the owner-approved OANDA Practice read-only PAPER campaign locally to collect more closed paper trades.
