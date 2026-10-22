"""One-shot, Practice-only adapter from canonical OANDA pricing to P1 paper sessions."""
from __future__ import annotations

import importlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "AIOS_P1_OANDA_PRACTICE_SNAPSHOT_CAPTURE.v1"
SNAPSHOT_SCHEMA = "AIOS_P1_SUPERVISED_PAPER_MARKET_SNAPSHOT.v1"
INSTRUMENT = "EUR_USD"
FRESHNESS_SECONDS = 300
MAX_UNITS = 1_000_000
SNAPSHOT_KEYS = frozenset({"schema", "evidence_type", "provenance", "broker_label", "environment", "instrument", "observed_at_utc", "bid", "ask", "mid", "spread", "source_status", "stale_status", "read_only", "broker_call_performed", "broker_write_performed", "credentials_loaded_runtime_only", "credentials_persisted", "account_identifier_included", "authorization_header_included", "broker_order_identifier_included", "raw_payload_included", "order_submission_allowed", "demo_execution_allowed", "live_execution_allowed", "money_movement_allowed"})
FORBIDDEN = re.compile(r"(?i)(fixture|mock|synthetic|narrative|example|token|secret|authorization|account[_ -]?id|raw[_ -]?(payload|response)|order[_ -]?id)")


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def resolve_canonical_practice_transport() -> type:
    return importlib.import_module("automation.forex_engine.oanda_read_only_client").OandaReadOnlyClient


def validate_practice_runtime_configuration(*, environment: str, instrument: str, owner_local_runtime: bool) -> dict[str, Any]:
    if environment.strip().lower() != "practice": raise ValueError("practice_environment_required")
    if instrument != INSTRUMENT: raise ValueError("EUR_USD_required")
    if not owner_local_runtime: raise ValueError("owner_local_runtime_flag_required")
    return {"environment": "PRACTICE", "instrument": instrument, "read_only": True}


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool): raise ValueError(f"invalid_{name}")
    try: result = float(value)
    except (TypeError, ValueError) as exc: raise ValueError(f"invalid_{name}") from exc
    if not math.isfinite(result) or result <= 0: raise ValueError(f"invalid_{name}")
    return result


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"): raise ValueError("explicit_utc_timestamp_required")
    try: return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc: raise ValueError("invalid_utc_timestamp") from exc


def extract_sanitized_price_snapshot(payload: Mapping[str, Any], *, instrument: str = INSTRUMENT, broker_call_performed: bool = False, credentials_loaded_runtime_only: bool = False, now: datetime | None = None) -> dict[str, Any]:
    prices = payload.get("prices")
    if not isinstance(prices, list) or len(prices) != 1 or not isinstance(prices[0], Mapping): raise ValueError("invalid_pricing_payload")
    price = prices[0]
    if price.get("instrument") != instrument: raise ValueError("instrument_mismatch")
    bids, asks = price.get("bids"), price.get("asks")
    if not isinstance(bids, list) or not bids or not isinstance(asks, list) or not asks: raise ValueError("missing_bid_or_ask")
    bid, ask = _number(bids[0].get("price"), "bid"), _number(asks[0].get("price"), "ask")
    snapshot = {"schema": SNAPSHOT_SCHEMA, "evidence_type": "SANITIZED_READ_ONLY_MARKET_SNAPSHOT", "provenance": "GENUINE_OBSERVED_MARKET_DATA", "broker_label": "OANDA", "environment": "PRACTICE", "instrument": instrument, "observed_at_utc": price.get("time"), "bid": bid, "ask": ask, "mid": (bid + ask) / 2, "spread": ask - bid, "source_status": "VALID", "stale_status": "VALID", "read_only": True, "broker_call_performed": broker_call_performed, "broker_write_performed": False, "credentials_loaded_runtime_only": credentials_loaded_runtime_only, "credentials_persisted": False, "account_identifier_included": False, "authorization_header_included": False, "broker_order_identifier_included": False, "raw_payload_included": False, "order_submission_allowed": False, "demo_execution_allowed": False, "live_execution_allowed": False, "money_movement_allowed": False}
    return validate_sanitized_snapshot(snapshot, now=now)


def validate_sanitized_snapshot(snapshot: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    if set(snapshot) != SNAPSHOT_KEYS: raise ValueError("snapshot_fields_not_allowlisted")
    expected = {"schema": SNAPSHOT_SCHEMA, "evidence_type": "SANITIZED_READ_ONLY_MARKET_SNAPSHOT", "provenance": "GENUINE_OBSERVED_MARKET_DATA", "broker_label": "OANDA", "environment": "PRACTICE", "instrument": INSTRUMENT, "source_status": "VALID", "stale_status": "VALID", "read_only": True, "broker_write_performed": False, "credentials_persisted": False, "account_identifier_included": False, "authorization_header_included": False, "broker_order_identifier_included": False, "raw_payload_included": False, "order_submission_allowed": False, "demo_execution_allowed": False, "live_execution_allowed": False, "money_movement_allowed": False}
    if any(snapshot.get(k) != v for k, v in expected.items()): raise ValueError("invalid_or_unsafe_snapshot_contract")
    observed = _utc(snapshot["observed_at_utc"]); current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if observed > current or (current - observed).total_seconds() > FRESHNESS_SECONDS: raise ValueError("stale_snapshot")
    bid, ask, mid, spread = (_number(snapshot[k], k) for k in ("bid", "ask", "mid", "spread"))
    if ask < bid or not bid <= mid <= ask or not math.isclose(spread, ask-bid, abs_tol=1e-12): raise ValueError("invalid_market_prices")
    return dict(snapshot)


def validate_paper_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    if FORBIDDEN.search(stable_json(candidate)): raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    required = ("strategy_id", "candidate_id", "instrument", "direction", "units", "stop_price", "target_price", "risk_amount", "entry_rationale", "status", "sanitized", "current")
    deny = ("broker_call_performed", "broker_write_performed", "order_submission_allowed", "demo_execution_allowed", "live_execution_allowed", "money_movement_allowed")
    if any(not candidate.get(k) for k in required) or candidate.get("status") != "PAPER_ELIGIBLE" or candidate.get("sanitized") is not True or candidate.get("current") is not True or any(candidate.get(k, False) is not False for k in deny): raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    units = candidate["units"]
    if isinstance(units, bool) or not isinstance(units, int) or not 0 < units <= MAX_UNITS or candidate["instrument"] != INSTRUMENT or str(candidate["direction"]).upper() != "BUY": raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    return dict(candidate)


def match_candidate_to_snapshot(candidate: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    item, snap = validate_paper_candidate(candidate), validate_sanitized_snapshot(snapshot)
    if item["instrument"] != snap["instrument"] or not _number(item["stop_price"], "stop_price") < snap["ask"] < _number(item["target_price"], "target_price") or _number(item["risk_amount"], "risk_amount") <= 0: raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    return item


def prepare_session_open_request(candidate: Mapping[str, Any], snapshot: Mapping[str, Any], reviewer_identity: str, as_of_utc: str, runtime_path: Path) -> dict[str, Any]:
    item = match_candidate_to_snapshot(candidate, snapshot)
    if not reviewer_identity.strip(): raise ValueError("owner_reviewer_required")
    return {"snapshot": {k: snapshot[k] for k in ("schema", "evidence_type", "provenance", "instrument", "observed_at_utc", "bid", "ask", "mid", "spread", "source_status", "stale_status", "read_only", "broker_write_performed", "account_identifier_included", "raw_payload_included")} | {"credentials_included": False}, "candidate": item, "reviewer_identity": reviewer_identity, "as_of_utc": as_of_utc, "runtime_path": runtime_path}


def open_session_through_canonical_controller(request: Mapping[str, Any]) -> dict[str, Any]:
    controller = importlib.import_module("automation.forex_engine.forex_p1_supervised_paper_session_v1")
    return controller.open_paper_session(request["snapshot"], request["candidate"], request["reviewer_identity"], request["as_of_utc"], request["runtime_path"])


def build_capture_state(**changes: Any) -> dict[str, Any]:
    state = {"schema": SCHEMA, "status": "BUILD_VALIDATED_OFFLINE", "genuine_snapshot_captured": False, "paper_session_opened": False, "qualifying_p1_trade_count_changed": False, "broker_call_performed": False, "credentials_loaded": False, "credentials_persisted": False, "broker_write_performed": False, "demo_order_performed": False, "live_order_performed": False, "money_movement_performed": False}
    state.update(changes); return state


def render_owner_report(state: Mapping[str, Any]) -> str:
    return "# AIOS P1 OANDA Practice Snapshot Capture V1\n\n" + "\n".join(f"- {k}: {str(v).lower() if isinstance(v, bool) else v}" for k, v in state.items()) + "\n\nNo OANDA order is placed. Build fixtures receive zero P1 credit.\n"
