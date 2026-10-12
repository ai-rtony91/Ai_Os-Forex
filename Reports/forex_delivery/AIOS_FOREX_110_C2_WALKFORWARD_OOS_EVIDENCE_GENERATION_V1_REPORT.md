# AIOS Forex 110 C2 Walk-Forward OOS Evidence Generation V1

Packet ID: `PKT-FOREX-110-C2-WALKFORWARD-OOS-EVIDENCE-GENERATION-V1`
C2 evidence status: `BLOCKED_TOP_CANDIDATE_MISMATCH`
Target candidate id: `c2-eur-buy-stronger-review-ready`
Top candidate id: `NONE`
Candidate alignment: `TOP_CANDIDATE_MISMATCH`
Evidence source classification: `SAMPLE_TEST_ONLY`

## Required Proof Fields
- proof_candidate: `MISSING`
- windows_total: `MISSING`
- windows_passed: `MISSING`
- oos_segments_total: `MISSING`
- oos_segments_passed: `MISSING`
- min_pass_rate: `MISSING`
- max_drawdown: `MISSING`
- max_allowed_drawdown: `MISSING`
- sanitized: `MISSING`
- evidence_age_days: `MISSING`
- max_evidence_age_days: `MISSING`
- candidate_alignment: `TOP_CANDIDATE_MISMATCH`

## Blockers
- profit truth-lock top candidate is NONE, not c2-eur-buy-stronger-review-ready

## Source Classification
- Real C2 walk-forward/OOS proof was not created unless complete sanitized local evidence was already present.
- Sample/test-style C2 references were not promoted into proof.
- No broker, credential, demo, live, scheduler, commit, push, PR, or merge action was performed.

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

## ATTACK_TO_FINISH
- blocker_id: MISSING_EVIDENCE_FIELD
- blocker_status: BLOCKED
- exact_blocker: profit truth-lock top candidate is NONE, not c2-eur-buy-stronger-review-ready
- canonical_owner_file: automation/forex_engine/walk_forward_evidence_intake_v1.py
- test_file: tests/forex_engine/test_forex_110_c2_walkforward_oos_evidence_generation_v1.py
- runner_script: scripts/forex_delivery/run_forex_110_c2_walkforward_oos_evidence_generation_v1.py
- missing_evidence_field: oos_segments_total,oos_segments_passed,candidate_alignment
- unlock_status_required: PROVEN
- next_packet_name: PKT-FOREX-110-C2-WALKFORWARD-OOS-SOURCE-COLLECTION-V1
- owner_action_required: provide missing field oos_segments_total,oos_segments_passed,candidate_alignment
- stop_condition: TOP_CANDIDATE_MISMATCH
- no_bloat_guard: Reuse existing walk-forward intake and do not promote sample/test C2 data into proof.

## Next Safe Action
Resolve the profit truth-lock top candidate before collecting C2 OOS proof.
