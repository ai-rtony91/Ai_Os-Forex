# AIOS Forex A-Lane Owner Control Intake Packet V1

Created UTC: 2026-10-09T20:52:03+00:00

Fill only sanitized facts. Do not include API tokens, passwords, full account IDs, banking details, or screenshots containing secrets.

## execution_policy_resolution

Status: UNKNOWN

- approved_execution_policy_route: 
- policy_scope: CurrentUser or approved enterprise route
- reviewed_claim_script_sha256: 33a8eb24a4113abb3126a5b0e65ff595dc2f8c16d6857afd185c6a915007f087
- reviewed_release_script_sha256: 9b829a7c292a991f39891594efe5d2d0fd151e9a0a444bc9a85ff07ae2d395b6
- trusted_signer_name: 
- post_sign_claim_script_sha256: 
- post_sign_release_script_sha256: 
- owner_attestation: 
- evidence_timestamp_utc: 

## daily_loss_authority

Status: UNKNOWN

- daily_loss_cap_value: 
- daily_loss_cap_unit: USD or ACCOUNT_PERCENT
- trading_day_timezone: 
- rollover_cutoff_time: 
- restart_persistence_required: True
- owner_attestation: 
- evidence_timestamp_utc: 

## kill_switch_authority

Status: UNKNOWN

- manual_operator_stop_path: 
- credential_revoke_path: 
- notification_path: 
- max_daily_loss_stop_declared: True
- max_drawdown_stop_declared: True
- audit_logging_declared: True
- owner_attestation: 
- evidence_timestamp_utc: 

## broker_permission_boundary

Status: UNKNOWN

- broker_name_sanitized: OANDA
- broker_environment: practice
- asset_class: forex
- account_type_sanitized: 
- account_currency: 
- margin_available_confirmed: 
- effective_leverage_limit: 
- long_permission: 
- short_permission: 
- fifo_required: 
- hedging_available: 
- instrument_tradable: 
- max_units: 
- stop_loss_supported: 
- take_profit_supported: 
- order_type_supported: market
- one_order_only_supported: 
- demo_sandbox_order_preview_supported: 
- broker_house_restrictions: []
- proof_source_sanitized: 
- evidence_timestamp_utc: 

## owner_safety_controls_refresh

Status: UNKNOWN

- kill_switch_state_artifact: 
- daily_stop_state_artifact: 
- max_loss_state_artifact: 
- monitoring_ready_artifact: 
- freshness_window_hours: 24
- owner_attestation: 
- evidence_timestamp_utc: 
