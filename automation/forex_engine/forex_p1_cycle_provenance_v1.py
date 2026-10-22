"""Sanitized, append-only cycle provenance for the P1 PAPER runtime."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "AIOS_FOREX_P1_CYCLE_PROVENANCE.v1"
FILENAME = "AIOS_FOREX_SUPERTREND_CYCLE_PROVENANCE.jsonl"
_SECRET_KEYS = ("token", "credential", "account", "payload", "order_id", "transaction")


def _stamp(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def _clean(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(part in lowered for part in _SECRET_KEYS):
        return None
    if isinstance(value, Mapping):
        return {str(k): _clean(v, str(k)) for k, v in value.items() if not any(part in str(k).lower() for part in _SECRET_KEYS)}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def telemetry_path(output_root: Path) -> Path:
    return output_root / FILENAME


def build_cycle_record(
    *, cycle_number: int, maximum_cycles: int, cycle_started_utc: str,
    cycle_completed_utc: str, action: str, rejection_reasons: list[str] | tuple[str, ...] = (),
    next_check_in_seconds: int | None = None, signal: Mapping[str, Any] | None = None,
    snapshot: Mapping[str, Any] | None = None, stale_reason: str | None = None,
    run_pid: int | None = None, lock_owner: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    signal = signal or {}
    snapshot = snapshot or {}
    extra_data = dict(extra or {})
    data = signal.get("provenance", {}) if isinstance(signal.get("provenance"), Mapping) else {}
    next_at = None
    if next_check_in_seconds is not None:
        try:
            next_at = _stamp(datetime.fromisoformat(cycle_completed_utc.replace("Z", "+00:00")) + timedelta(seconds=next_check_in_seconds))
        except (TypeError, ValueError):
            next_at = None
    record: dict[str, Any] = {
        "schema": SCHEMA, "runtime_version": "forex_p1_practice_paper_campaign_runtime_v1",
        "campaign_identity": "FOREX_P1_SUPERTREND_PRACTICE_RUNTIME_V1",
        "cycle_number": cycle_number, "maximum_cycles": maximum_cycles,
        "cycle_started_utc": cycle_started_utc, "cycle_completed_utc": cycle_completed_utc,
        "next_check_in_seconds": next_check_in_seconds, "next_check_at_utc": next_at,
        "instrument": "EUR_USD", "timeframe": "M5", "environment": "PRACTICE",
        "git_commit": os.environ.get("AIOS_GIT_COMMIT", "runtime-local"),
        "http_methods": ["GET"], "history_get_count": data.get("history_get_count", 0),
        "pricing_get_count": data.get("pricing_get_count", 0),
        "history_request_start_utc": data.get("history_request_start_utc"),
        "history_response_utc": data.get("history_response_utc"),
        "pricing_request_start_utc": data.get("pricing_request_start_utc"),
        "pricing_response_utc": data.get("pricing_response_utc"),
        "latest_completed_candle_open_utc": data.get("latest_completed_candle_open_utc"),
        "latest_completed_candle_close_utc": data.get("latest_completed_candle_close_utc"),
        "history_age_seconds": data.get("history_age_seconds"), "history_freshness_threshold": 300,
        "history_freshness_result": data.get("history_freshness_result", "STALE" if stale_reason == "stale_history" else "UNKNOWN"),
        "snapshot_observed_utc": snapshot.get("observed_at_utc"), "snapshot_age_seconds": data.get("snapshot_age_seconds"),
        "snapshot_freshness_threshold": 300,
        "snapshot_freshness_result": data.get("snapshot_freshness_result", "STALE" if stale_reason == "stale_snapshot" else "UNKNOWN"),
        "signal_source": signal.get("signal_source", "supertrend"), "strategy_name": signal.get("strategy_name"),
        "strategy_config": signal.get("strategy_config", {}), "atr_actual": data.get("atr_actual"),
        "minimum_atr": data.get("minimum_atr", 0.0004), "atr_margin_to_threshold": data.get("atr_margin_to_threshold"),
        "supertrend_direction": signal.get("direction"), "flip_counts": data.get("flip_counts"),
        "candle_body_ratio": data.get("candle_body_ratio"), "minimum_candle_body_ratio": data.get("minimum_candle_body_ratio", 0.45),
        "band": data.get("band"), "band_extension": data.get("band_extension"), "maximum_band_extension": data.get("maximum_band_extension", 2.5),
        "close_confirmation_result": data.get("close_confirmation_result"), "reward_risk_actual": data.get("reward_risk_actual"),
        "minimum_reward_risk": data.get("minimum_reward_risk", 1.5), "signal_status": signal.get("status"),
        "rejection_reasons": list(rejection_reasons), "entry_reference": data.get("entry_reference"),
        "stop": signal.get("stop_price"), "target": signal.get("target_price"),
        "bid": snapshot.get("bid"), "ask": snapshot.get("ask"), "spread": snapshot.get("spread"),
        "stop_lt_ask": data.get("stop_lt_ask"), "ask_lt_target": data.get("ask_lt_target"),
        "duplicate_position_guard": data.get("duplicate_position_guard"), "active_position_status": data.get("active_position_status", "NONE"),
        # A BUY is only a strategy signal.  It is not a paper candidate until
        # the runtime has evaluated stop < ask < target and the session guards.
        "candidate_status": extra_data.get("candidate_status", "NONE"),
        "paper_eligible": bool(extra_data.get("paper_eligible", False)),
        "signal_accepted": signal.get("status") == "BUY",
        "ask_geometry_status": extra_data.get("ask_geometry_status", "NOT_EVALUATED"),
        "paper_session_event": extra_data.get("paper_session_event", "NONE"),
        "first_failed_gate": data.get("first_failed_gate"),
        "all_failed_gates": data.get("all_failed_gates", list(rejection_reasons)),
        "atr_distance_to_pass": data.get("atr_distance_to_pass"),
        "atr_distance_percent": data.get("atr_distance_percent"),
        "body_distance_to_pass": data.get("body_distance_to_pass"),
        "price_distance_to_band": data.get("price_distance_to_band"),
        "extension_atr_ratio": data.get("extension_atr_ratio"),
        "spread_stop_distance_ratio": data.get("spread_stop_distance_ratio"),
        "supertrend_value": data.get("supertrend_value"),
        "bars_in_current_direction": data.get("bars_in_current_direction"),
        "flip_this_cycle": data.get("flip_this_cycle"),
        "recent_flip_count": data.get("recent_flip_count"),
        "close_confirmation": data.get("close_confirmation", "NOT_EVALUATED"),
        "buy_only_boundary": data.get("buy_only_boundary", "PASS"),
        "cycle_action": action,
        "runtime_pid": run_pid or os.getpid(), "lock_owner_identity": lock_owner,
        "broker_write_performed": False, "practice_order_performed": False, "live_trade_performed": False,
        "money_movement_performed": False, "credentials_persisted": False,
    }
    if extra_data:
        record.update(extra_data)
    return _clean(record)


def append_cycle_record(path: Path, record: Mapping[str, Any]) -> None:
    """Append one complete JSON line and flush it before returning."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(_clean(dict(record)), sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    # The provenance record is the runtime source event.  The learning ledger
    # is derived from it and deduplicated by stable cycle identity.
    try:
        from automation.forex_engine.forex_p1_experience_learning_loop_v1 import append_cycle_experience
        append_cycle_experience(
            path.parent,
            record,
            git_commit=str(record.get("git_commit") or "runtime-local"),
            dataset_identity={
                "instrument": record.get("instrument"),
                "timeframe": record.get("timeframe"),
                "candle_close": record.get("latest_completed_candle_close_utc"),
            },
        )
    except (OSError, ValueError):
        # A learning-ledger failure is fail-closed for provenance callers; it
        # must never become a trading capability or corrupt the JSONL record.
        raise
