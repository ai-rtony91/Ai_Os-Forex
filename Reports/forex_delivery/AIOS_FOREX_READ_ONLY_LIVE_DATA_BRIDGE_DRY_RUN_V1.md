# AIOS Forex Read-Only Live Data Bridge Dry Run V1

Status: READ_ONLY_SANITIZED

No live trade, BUY, SELL, close, order placement, broker write call, secret, account ID, order ID, transaction ID, or raw broker payload is recorded here.

## Summary

```json
{
  "broker_reachable": false,
  "freshness_utc": "2026-08-05T20:45:33Z",
  "live_execution_allowed": false,
  "next_safe_action": "Run the read-only live data bridge, review sanitized readiness, then proceed to AIOS-FOREX-PAPER-SIGNAL-EXECUTION-LOOP-V1 before any live arming gate.",
  "pl_available": false,
  "positions_reconciled": false,
  "source_label": "FIXTURE_NOT_LIVE",
  "source_type": "fixture",
  "stale_status": "BLOCKED",
  "trading_history_available": false
}
```

## Sanitized Read Model

```json
{
  "block_reason": "AIOS_FOREX_READONLY_LIVE_ENABLE is not 1; using fixture/readiness fallback.",
  "broker_state": {
    "account_reachable": false,
    "block_reason": "AIOS_FOREX_READONLY_LIVE_ENABLE is not 1; using fixture/readiness fallback.",
    "broker_mode": "not_enabled",
    "daily_pl_available": false,
    "freshness_utc": "2026-08-05T20:45:33Z",
    "live_trading_allowed_from_this_data": false,
    "margin_risk_available": false,
    "open_positions_reconciled": false,
    "pending_orders_reconciled": false,
    "read_only": true,
    "sanitized_evidence_path": "Reports/forex_delivery/AIOS_FOREX_READ_ONLY_LIVE_DATA_BRIDGE_DRY_RUN_V1.md",
    "source_label": "FIXTURE_NOT_LIVE",
    "source_type": "fixture",
    "stale_status": "BLOCKED"
  },
  "capabilities": {
    "broker_write_calls_allowed": false,
    "close_trade_allowed": false,
    "get_requests_only": true,
    "live_execution_allowed": false,
    "order_placement_allowed": false,
    "post_put_patch_delete_allowed": false,
    "read_only": true
  },
  "execution_readiness": {
    "LIVE_READY": false,
    "block_reason": "AIOS_FOREX_READONLY_LIVE_ENABLE is not 1; using fixture/readiness fallback.",
    "blocked_reasons": [
      "real_market_data_source_not_enabled",
      "broker_account_state_not_reconciled",
      "positions_not_reconciled",
      "daily_pl_not_available",
      "auto_exit_not_ready",
      "trading_history_writeback_not_available",
      "signal_logic_not_connected",
      "risk_governor_not_approved",
      "human_owner_live_execution_not_armed"
    ],
    "freshness_utc": "2026-08-05T20:45:33Z",
    "live_execution_allowed": false,
    "live_trading_allowed_from_this_data": false,
    "next_safe_action": "Run the read-only live data bridge, review sanitized readiness, then proceed to AIOS-FOREX-PAPER-SIGNAL-EXECUTION-LOOP-V1 before any live arming gate.",
    "read_only": true,
    "sanitized_evidence_path": "Reports/forex_delivery/AIOS_FOREX_READ_ONLY_LIVE_DATA_BRIDGE_DRY_RUN_V1.md",
    "source_label": "FIXTURE_NOT_LIVE",
    "source_type": "fixture",
    "stale_status": "BLOCKED"
  },
  "exit_readiness": {
    "auto_exit_ready": false,
    "block_reason": "No open position requiring live exit protection was reconciled.",
    "freshness_utc": "2026-08-05T20:45:33Z",
    "live_trading_allowed_from_this_data": false,
    "manual_close_fallback": "BROKER_UI_MANUAL_FALLBACK_REQUIRED",
    "max_time_policy_present": false,
    "read_only": true,
    "sanitized_evidence_path": "Reports/forex_delivery/AIOS_FOREX_READ_ONLY_LIVE_DATA_BRIDGE_DRY_RUN_V1.md",
    "source_label": "FIXTURE_NOT_LIVE",
    "source_type": "fixture",
    "stale_status": "BLOCKED",
    "stop_loss_present": false,
    "take_profit_policy_present": false,
    "trailing_stop_policy_present": false
  },
  "freshness_utc": "2026-08-05T20:45:33Z",
  "live_trading_allowed_from_this_data": false,
  "market": {
    "block_reason": "AIOS_FOREX_READONLY_LIVE_ENABLE is not 1; using fixture/readiness fallback.",
    "freshness_utc": "2026-08-05T20:45:33Z",
    "live_trading_allowed_from_this_data": false,
    "price_snapshot_available": false,
    "read_only": true,
    "sanitized_evidence_path": "Reports/forex_delivery/AIOS_FOREX_READ_ONLY_LIVE_DATA_BRIDGE_DRY_RUN_V1.md",
    "selected_pair": "EUR_USD",
    "source_label": "FIXTURE_NOT_LIVE",
    "source_type": "fixture",
    "stale_status": "BLOCKED"
  },
  "mode": "READ_ONLY",
  "money_strip": {
    "ask": "UNAVAILABLE",
    "balance": "UNAVAILABLE",
    "bid": "UNAVAILABLE",
    "block_reason": "AIOS_FOREX_READONLY_LIVE_ENABLE is not 1; using fixture/readiness fallback.",
    "broker": "OANDA",
    "broker_mode": "not_enabled",
    "currency": "UNAVAILABLE",
    "equity": "UNAVAILABLE",
    "execution_allowed": false,
    "freshness_utc": "2026-08-05T20:45:33Z",
    "live_order_allowed": false,
    "live_trading_allowed_from_this_data": false,
    "margin_available": "UNAVAILABLE",
    "margin_used": "UNAVAILABLE",
    "margin_used_percent": "UNAVAILABLE",
    "mode": "READ_ONLY",
    "nav": "UNAVAILABLE",
    "open_position_count": 0,
    "open_trade_count": 0,
    "order_placement_allowed": false,
    "pending_order_count": 0,
    "read_only": true,
    "realized_pl": "UNAVAILABLE",
    "sanitized_evidence_path": "Reports/forex_delivery/AIOS_FOREX_READ_ONLY_LIVE_DATA_BRIDGE_DRY_RUN_V1.md",
    "selected_pair": "EUR_USD",
    "source_label": "FIXTURE_NOT_LIVE",
    "source_type": "fixture",
    "spread": "UNAVAILABLE",
    "stale_status": "BLOCKED",
    "status": "BLOCKED",
    "unrealized_pl": "UNAVAILABLE",
    "withdrawal_limit": "UNAVAILABLE"
  },
  "positions": {
    "block_reason": "AIOS_FOREX_READONLY_LIVE_ENABLE is not 1; using fixture/readiness fallback.",
    "freshness_utc": "2026-08-05T20:45:33Z",
    "live_trading_allowed_from_this_data": false,
    "open_position_count": 0,
    "open_trade_count": 0,
    "open_trades": [],
    "positions": [],
    "positions_reconciled": false,
    "read_only": true,
    "sanitized_evidence_path": "Reports/forex_delivery/AIOS_FOREX_READ_ONLY_LIVE_DATA_BRIDGE_DRY_RUN_V1.md",
    "source_label": "FIXTURE_NOT_LIVE",
    "source_type": "fixture",
    "stale_status": "BLOCKED"
  },
  "read_only": true,
  "risk_pl": {
    "block_reason": "AIOS_FOREX_READONLY_LIVE_ENABLE is not 1; using fixture/readiness fallback.",
    "daily_pl_available": false,
    "freshness_utc": "2026-08-05T20:45:33Z",
    "live_trading_allowed_from_this_data": false,
    "margin_available": "UNAVAILABLE",
    "margin_risk_available": false,
    "read_only": true,
    "realized_pl": "UNAVAILABLE",
    "sanitized_evidence_path": "Reports/forex_delivery/AIOS_FOREX_READ_ONLY_LIVE_DATA_BRIDGE_DRY_RUN_V1.md",
    "source_label": "FIXTURE_NOT_LIVE",
    "source_type": "fixture",
    "stale_status": "BLOCKED",
    "unrealized_pl": "UNAVAILABLE"
  },
  "sanitized_evidence_path": "Reports/forex_delivery/AIOS_FOREX_READ_ONLY_LIVE_DATA_BRIDGE_DRY_RUN_V1.md",
  "schema": "AIOS_FOREX_READ_ONLY_LIVE_DATA_BRIDGE.v1",
  "secret_status": {
    "ACCOUNT_ID_RECORDED": false,
    "OANDA_ACCOUNT_ID_STATUS": "MISSING",
    "OANDA_API_TOKEN_STATUS": "MISSING",
    "RAW_BROKER_PAYLOAD_RECORDED": false,
    "SECRET_VALUES_PRINTED": false
  },
  "selected_pair": "EUR_USD",
  "source_label": "FIXTURE_NOT_LIVE",
  "source_type": "fixture",
  "stale_status": "BLOCKED",
  "trading_history": {
    "block_reason": "No sanitized real closed-trade history is available.",
    "closed_trade_count": 0,
    "freshness_utc": "2026-08-05T20:45:33Z",
    "live_trading_allowed_from_this_data": false,
    "read_only": true,
    "rows": [],
    "sanitized_evidence_path": "Reports/forex_delivery/AIOS_FOREX_READ_ONLY_LIVE_DATA_BRIDGE_DRY_RUN_V1.md",
    "source_label": "FIXTURE_NOT_LIVE",
    "source_type": "fixture",
    "stale_status": "BLOCKED",
    "trading_history_available": false
  }
}
```
