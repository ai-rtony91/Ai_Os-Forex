# AIOS Forex Autonomy Completion Governor Rerun + Bucket Policy V1 Report

Status: AUTONOMY_BLOCKED
Current branch: work
Current head: acb6d327352e0542dcbcc8a521891fbc7ade8648
Input files used: /workspace/Ai_Os/Reports/forex_delivery/AIOS_FOREX_AUTONOMY_COMPLETION_STATE_MODEL_V1.json, /workspace/Ai_Os/Reports/forex_delivery/AIOS_FOREX_LIVE_MICRO_EXCEPTION_GOVERNOR_INPUT_TEMPLATE_V1.json

Governor status: AUTONOMY_BLOCKED
Bucket status: BUCKET_MAX_LOSS_HOLD
Next autonomy action: HOLD_FOR_RISK_RESET
Owner gate status: OWNER_GATE_PENDING
Broker gate status: LIVE_BRIDGE_NOT_READY
Live micro exception status: LIVE_MICRO_REVIEW_BLOCKED

Cumulative band semantics:
- cumulative_return_percent: None
- cumulative_return_target_percent_low: 100.0
- cumulative_return_target_percent_high: 120.0

Safety boundary:
- order_execution_allowed: False
- broker_api_allowed: False
- credentials_allowed: False
- account_identifier_persistence_allowed: False
- scheduler_allowed: False
- daemon_allowed: False
- webhook_allowed: False

Governor blockers:
- profitability evidence is not complete
- sample_size=12 is below minimum 30
- walk_forward_windows=1 is below minimum 2
- max_drawdown=0.21 exceeds threshold 0.15
- profit_factor=1.00 below threshold 2.00
- expectancy=-0.10 below threshold 0.50
- live bridge evidence is not available
- kill switch state is 'UNKNOWN'
- daily stop state is 'UNKNOWN'
- max loss state is not configured
- take-profit / stop-loss evidence is missing
- monitoring readiness is false
- evidence_age_days=40 exceeds freshness limit 14
- owner approval is pending
Bucket blockers:
- governor_status_require_more_evidence
- live_bridge_eligibility_missing
- sample_and_walkforward_shortfall
- target_bucket_not_reached
- owner_approval_pending
- max_loss_state_hold

Next safe action: Hold until risk reset evidence (max-loss / daily-stop / kill-switch) clears.

Validators:
- python -m py_compile automation/forex_engine/forex_autonomy_completion_governor_rerun_and_bucket_policy_v1.py
- python -m py_compile scripts/forex_delivery/run_forex_autonomy_completion_governor_rerun_and_bucket_policy_v1.py
- python -m pytest tests/forex_engine/test_forex_autonomy_completion_governor_rerun_and_bucket_policy_v1.py -q
- python scripts/forex_delivery/run_forex_autonomy_completion_governor_rerun_and_bucket_policy_v1.py
- python -m json.tool Reports/forex_delivery/AIOS_FOREX_AUTONOMY_COMPLETION_GOVERNOR_RERUN_AND_BUCKET_POLICY_V1_STATE.json
- git diff --check -- automation/forex_engine/forex_autonomy_completion_governor_rerun_and_bucket_policy_v1.py scripts/forex_delivery/run_forex_autonomy_completion_governor_rerun_and_bucket_policy_v1.py tests/forex_engine/test_forex_autonomy_completion_governor_rerun_and_bucket_policy_v1.py Reports/forex_delivery/AIOS_FOREX_AUTONOMY_COMPLETION_GOVERNOR_RERUN_AND_BUCKET_POLICY_V1_STATE.json Reports/forex_delivery/AIOS_FOREX_AUTONOMY_COMPLETION_GOVERNOR_RERUN_AND_BUCKET_POLICY_V1_REPORT.md Reports/forex_delivery/AIOS_FOREX_AUTONOMY_COMPLETION_GOVERNOR_RERUN_AND_BUCKET_POLICY_V1_NEXT_CODEX_PACKET_V1.md
