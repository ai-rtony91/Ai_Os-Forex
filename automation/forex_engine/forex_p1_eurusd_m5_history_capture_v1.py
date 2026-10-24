"""One-shot sanitizer for canonical EUR_USD M5 OANDA Practice history."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from automation.forex_engine.forex_p1_eurusd_market_history_signal_v1 import (
    FRESHNESS_SECONDS,
    GENUINE_PROVENANCE,
    GRANULARITY,
    HISTORY_KEYS,
    HISTORY_SCHEMA,
    INSTRUMENT,
    validate_market_history,
)
from automation.forex_engine.oanda_practice_candle_history_transport_v1 import (
    HOST, PATH, TIMEOUT_SECONDS, OandaPracticeCandleHistoryTransportV1,
)

MIN_COUNT = 3
MAX_COUNT = 50
RUNTIME_PATH = ".aios/runtime/forex_market_history/EUR_USD_latest.json"
APPROVAL_SCHEMA = "AIOS_OANDA_PRACTICE_CANDLE_SESSION_APPROVAL.v1"
APPROVAL_ROOT = ".aios/runtime/forex_authorizations"
APPROVAL_KEYS = frozenset({"schema", "approval_id", "packet_id", "owner_identity", "approved_at_utc",
    "expires_at_utc", "environment", "method", "host", "path", "instrument", "granularity", "price",
    "count", "timeout_seconds", "request_budget", "output_path", "stop_point"})
RAW_CANDLE_KEYS = frozenset({"time", "complete", "volume", "mid"})
MID_KEYS = frozenset({"o", "h", "l", "c"})


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def resolve_canonical_practice_transport(client: OandaPracticeCandleHistoryTransportV1) -> OandaPracticeCandleHistoryTransportV1:
    if type(client) is not OandaPracticeCandleHistoryTransportV1:
        raise ValueError("dedicated_practice_candle_transport_required")
    return client


def _approval_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_approval_key")
        result[key] = value
    return result


def load_and_validate_approval(path: Path, *, repository_root: Path, packet_id: str,
                               now: datetime | None = None) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("approval_symlink_rejected")
    root = repository_root.resolve()
    resolved = path.resolve()
    allowed = (root / APPROVAL_ROOT).resolve()
    if not resolved.is_relative_to(allowed) or not resolved.is_relative_to(root):
        raise ValueError("unsafe_approval_path")
    try:
        approval = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_approval_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non_finite_approval")))
    except OSError:
        raise ValueError("approval_unavailable") from None
    if not isinstance(approval, dict) or set(approval) != APPROVAL_KEYS:
        raise ValueError("exact_approval_schema_required")
    expected = {"schema": APPROVAL_SCHEMA, "packet_id": packet_id, "owner_identity": "Human Owner Anthony",
        "environment": "practice", "method": "GET", "host": HOST, "path": PATH, "instrument": "EUR_USD",
        "granularity": "M5", "price": "M", "count": 50, "timeout_seconds": TIMEOUT_SECONDS,
        "request_budget": 1, "output_path": RUNTIME_PATH, "stop_point": "AFTER_ONE_SANITIZED_WRITE_OR_FAILURE"}
    if any(approval.get(key) != value for key, value in expected.items()):
        raise ValueError("approval_contract_mismatch")
    if not isinstance(approval["approval_id"], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", approval["approval_id"]):
        raise ValueError("invalid_approval_id")
    sensitive = {"token", "account_id", "accountid", "raw_payload", "order_id"}
    if any(key.lower() in sensitive for key in approval):
        raise ValueError("sensitive_approval_field")
    approved, expires = _utc(approval["approved_at_utc"]), _utc(approval["expires_at_utc"])
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if expires <= approved or expires - approved > timedelta(minutes=15) or current < approved or current >= expires:
        raise ValueError("approval_time_window_rejected")
    return dict(approval)


def validate_runtime_capture_request(*, owner_local_runtime: bool, environment: str,
                                     instrument: str, granularity: str, count: int,
                                     output: str) -> dict[str, Any]:
    if owner_local_runtime is not True:
        raise ValueError("explicit_owner_local_runtime_required")
    if environment != "practice":
        raise ValueError("practice_environment_required")
    if instrument != INSTRUMENT:
        raise ValueError("EUR_USD_required")
    if granularity != GRANULARITY:
        raise ValueError("M5_required")
    if isinstance(count, bool) or count != 50:
        raise ValueError("count_must_equal_50")
    if output.replace("\\", "/") != RUNTIME_PATH:
        raise ValueError("canonical_runtime_path_required")
    return {"environment": environment, "instrument": instrument,
            "granularity": granularity, "count": count, "output": RUNTIME_PATH}


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("explicit_utc_timestamp_required")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("invalid_utc_timestamp") from exc
    return parsed.astimezone(timezone.utc)


def _price(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_{name}") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"invalid_{name}")
    return number


def extract_canonical_completed_candles(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping) or set(payload) != {"instrument", "granularity", "candles"}:
        raise ValueError("raw_payload_shape_rejected")
    if payload["instrument"] != INSTRUMENT:
        raise ValueError("EUR_USD_required")
    if payload["granularity"] != GRANULARITY:
        raise ValueError("M5_required")
    raw = payload.get("candles")
    if not isinstance(raw, list):
        raise ValueError("candles_list_required")
    result: list[dict[str, Any]] = []
    timestamps: list[datetime] = []
    for item in raw:
        if not isinstance(item, Mapping) or not set(item) <= RAW_CANDLE_KEYS:
            raise ValueError("raw_candle_fields_rejected")
        if item.get("complete") is not True:
            continue
        mid = item.get("mid")
        if not isinstance(mid, Mapping) or set(mid) != MID_KEYS:
            raise ValueError("midpoint_shape_rejected")
        timestamp = _utc(item.get("time"))
        values = {name: _price(mid[key], name) for key, name in
                  (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"))}
        if not values["low"] <= min(values["open"], values["close"]):
            raise ValueError("invalid_ohlc_geometry")
        if not values["high"] >= max(values["open"], values["close"]):
            raise ValueError("invalid_ohlc_geometry")
        volume = item.get("volume")
        if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
            raise ValueError("invalid_volume")
        timestamps.append(timestamp)
        result.append({"observed_at_utc": item["time"], **values,
                       "volume": volume, "complete": True})
    if len(result) < MIN_COUNT:
        raise ValueError("REQUIRE_MORE_HISTORY")
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("duplicate_candle_timestamp")
    if timestamps != sorted(timestamps):
        raise ValueError("unsorted_candle_timestamps")
    return result


def build_canonical_history_artifact(candles: list[dict[str, Any]], *, requested_count: int) -> dict[str, Any]:
    return {
        "schema": HISTORY_SCHEMA, "evidence_type": "SANITIZED_CANDLE_HISTORY",
        "provenance": GENUINE_PROVENANCE, "broker_label": "OANDA",
        "environment": "PRACTICE", "instrument": INSTRUMENT,
        "granularity": GRANULARITY, "requested_count": requested_count,
        "returned_count": len(candles), "first_observed_at_utc": candles[0]["observed_at_utc"],
        "last_observed_at_utc": candles[-1]["observed_at_utc"], "candles": candles,
        "source_status": "VALID", "stale_status": "VALID", "read_only": True,
        "complete": True, "broker_write_performed": False, "credentials_persisted": False,
        "account_identifier_included": False, "raw_payload_included": False,
        "order_submission_allowed": False, "demo_execution_allowed": False,
        "live_execution_allowed": False, "money_movement_allowed": False,
    }


def validate_canonical_history_artifact(history: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    if set(history) != HISTORY_KEYS:
        raise ValueError("canonical_history_fields_required")
    return validate_market_history(history, now=now)


def build_capture_state(*, generated_at_utc: str, repository_root: str, branch: str,
                        head: str) -> dict[str, Any]:
    return {"schema": "AIOS_P1_EURUSD_M5_HISTORY_CAPTURE_STATE.v1",
            "generated_at_utc": generated_at_utc, "repository_root": repository_root,
            "branch": branch, "head": head, "canonical_transport": "OandaPracticeCandleHistoryTransportV1",
            "candles_method_available": True, "practice_only_enforced": True,
            "default_network_access_allowed": False, "owner_local_capture_supported": True,
            "runtime_history_path": RUNTIME_PATH, "freshness_seconds": FRESHNESS_SECONDS,
            "genuine_history_captured": False, "genuine_history_consumed": False,
            "genuine_signal_generated": False, "candidate_generated": False,
            "paper_session_opened": False, "broker_call_performed": False,
            "credentials_loaded": False, "credentials_persisted": False,
            "broker_write_performed": False, "demo_order_performed": False,
            "live_order_performed": False, "money_movement_performed": False,
            "status": "READY_FOR_OWNER_LOCAL_CAPTURE", "blockers": [],
            "next_safe_action": "Run the documented one-shot ASUS PowerShell handoff."}


def render_owner_report(state: Mapping[str, Any]) -> str:
    return "# AIOS P1 EUR_USD M5 History Capture V1\n\n" + "\n".join(
        f"- {key}: {str(value).lower() if isinstance(value, bool) else value}"
        for key, value in state.items()) + "\n"
