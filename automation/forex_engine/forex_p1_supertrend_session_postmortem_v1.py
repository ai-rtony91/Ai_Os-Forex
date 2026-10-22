"""Deterministic, local-only postmortem for Supertrend PAPER evidence.

The builder consumes the existing supervised-paper ledger and campaign-state
shapes.  It performs no file I/O, credential access, network activity, broker
operation, scheduling, or order action.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn

from automation.forex_engine.strategies import SUPERTREND_PULLBACK_V1


VERSION = "forex_p1_supertrend_session_postmortem_v1"
SCHEMA = "AIOS_FOREX_P1_SUPERTREND_SESSION_POSTMORTEM.v1"
LEDGER_VERSION = "forex_p1_supervised_paper_evidence_pipeline_v1"
CAMPAIGN_VERSION = "forex_p1_supervised_paper_campaign_v1"
MAX_EVIDENCE_AGE = timedelta(days=7)

LEDGER_SAFETY_FLAGS = (
    "broker_call_performed",
    "broker_write_performed",
    "credentials_loaded",
    "account_access_performed",
    "order_submission_allowed",
    "order_modification_allowed",
    "order_close_allowed",
    "live_execution_allowed",
    "money_movement_allowed",
    "scheduler_created",
    "daemon_created",
    "webhook_created",
)
CAMPAIGN_SAFETY_FLAGS = (
    "broker_write_performed",
    "practice_order_performed",
    "live_trade_performed",
    "money_movement_performed",
    "credentials_persisted",
)
SAFETY_FLAGS = {
    "paper_only": True,
    "broker_call_performed": False,
    "broker_write_performed": False,
    "credentials_loaded": False,
    "network_call_performed": False,
    "oanda_request_performed": False,
    "scheduler_action_performed": False,
    "live_order_action_performed": False,
    "live_execution_allowed": False,
    "order_submission_allowed": False,
    "money_movement_allowed": False,
}

REQUIRED_RECORD_FIELDS = (
    "trade_id",
    "evidence_type",
    "strategy_id",
    "strategy_name",
    "mode",
    "paper_only",
    "instrument",
    "direction",
    "entry_timestamp_utc",
    "exit_timestamp_utc",
    "entry_price",
    "exit_price",
    "stop_price",
    "target_price",
    "quantity_or_units",
    "realized_pl",
    "fees",
    "risk_amount",
    "exit_reason",
    "entry_rationale",
    "evidence_source",
    "reviewed_by",
    "review_timestamp_utc",
)
NUMERIC_RECORD_FIELDS = (
    "entry_price",
    "exit_price",
    "stop_price",
    "target_price",
    "quantity_or_units",
    "realized_pl",
    "fees",
    "risk_amount",
)
PRIVATE_KEY_PARTS = (
    "account_id",
    "account_number",
    "api_key",
    "authorization",
    "credential",
    "password",
    "private_id",
    "secret",
    "token",
)
RAW_KEYS = frozenset(
    {"broker_payload", "raw_broker_payload", "raw_payload", "broker_raw", "response_body"}
)
CANONICAL_FALSE_SAFETY_FIELDS = frozenset(
    {
        "account_access_performed",
        "broker_call_performed",
        "broker_write_performed",
        "credentials_loaded",
        "credentials_persisted",
        "daemon_created",
        "live_execution_allowed",
        "live_order_action_performed",
        "live_trade_performed",
        "money_movement_allowed",
        "money_movement_performed",
        "network_call_performed",
        "oanda_request_performed",
        "order_close_allowed",
        "order_modification_allowed",
        "order_submission_allowed",
        "practice_order_performed",
        "scheduler_action_performed",
        "scheduler_created",
        "webhook_created",
    }
)
SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+[a-z0-9._-]+|api[_ -]?key\s*[:=]|authorization\s*[:=]|"
    r"password\s*[:=]|secret\s*[:=]|token\s*[:=])"
)


class PostmortemValidationError(ValueError):
    """A sanitized, stable failure raised for unsupported evidence."""


def _fail(code: str) -> NoReturn:
    raise PostmortemValidationError(code)


def stable_json(payload: Any) -> str:
    """Return deterministic JSON and reject non-JSON floating-point values."""
    try:
        rendered = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
        json.loads(rendered)
    except (TypeError, ValueError):
        _fail("postmortem_output_not_json_safe")
    return rendered


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(code)
    return value


def _sequence(value: Any, code: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail(code)
    return value


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code)
    return value.strip()


def _number(value: Any, code: str) -> float:
    if isinstance(value, bool):
        _fail(code)
    try:
        number = float(value)
    except (TypeError, ValueError):
        _fail(code)
    if not math.isfinite(number):
        _fail(code)
    return number


def _count(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(code)
    return value


def _utc(value: Any, code: str) -> datetime:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail(code)
    if parsed.tzinfo is None:
        _fail(code)
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _contains_sensitive(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in CANONICAL_FALSE_SAFETY_FIELDS:
                if child is not False:
                    return True
                continue
            if normalized in RAW_KEYS or any(part in normalized for part in PRIVATE_KEY_PARTS):
                return True
            if _contains_sensitive(child):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_sensitive(child) for child in value)
    elif isinstance(value, str):
        return bool(SECRET_VALUE.search(value))
    return False


def _require_false_flags(evidence: Mapping[str, Any], names: Sequence[str], code: str) -> None:
    if any(name not in evidence or evidence[name] is not False for name in names):
        _fail(code)


def _normalized_record(raw: Any) -> dict[str, Any]:
    record = _mapping(raw, "postmortem_trade_record_malformed")
    if _contains_sensitive(record):
        _fail("postmortem_sensitive_evidence_rejected")
    if any(field not in record for field in REQUIRED_RECORD_FIELDS):
        _fail("postmortem_trade_record_missing_field")

    normalized = {field: record[field] for field in REQUIRED_RECORD_FIELDS}
    for field in (
        "trade_id",
        "instrument",
        "direction",
        "exit_reason",
        "entry_rationale",
        "evidence_source",
        "reviewed_by",
    ):
        normalized[field] = _text(record[field], "postmortem_trade_record_malformed")
    if _text(record["evidence_type"], "postmortem_trade_record_malformed").lower() != "paper":
        _fail("postmortem_paper_evidence_required")
    normalized["evidence_type"] = "paper"
    if (
        _text(record["strategy_id"], "postmortem_strategy_identity_invalid")
        != SUPERTREND_PULLBACK_V1
        or _text(record["strategy_name"], "postmortem_strategy_identity_invalid")
        != SUPERTREND_PULLBACK_V1
    ):
        _fail("postmortem_strategy_identity_invalid")
    normalized["strategy_id"] = SUPERTREND_PULLBACK_V1
    normalized["strategy_name"] = SUPERTREND_PULLBACK_V1
    if _text(record["mode"], "postmortem_paper_boundary_invalid").upper() != "PAPER_ONLY":
        _fail("postmortem_paper_boundary_invalid")
    if record["paper_only"] is not True:
        _fail("postmortem_paper_boundary_invalid")
    normalized["mode"] = "PAPER_ONLY"
    normalized["paper_only"] = True

    entry = _utc(record["entry_timestamp_utc"], "postmortem_trade_timestamp_invalid")
    exit_time = _utc(record["exit_timestamp_utc"], "postmortem_trade_timestamp_invalid")
    review = _utc(record["review_timestamp_utc"], "postmortem_trade_timestamp_invalid")
    if exit_time <= entry or review < exit_time:
        _fail("postmortem_trade_timestamp_order_invalid")
    normalized["entry_timestamp_utc"] = _utc_text(entry)
    normalized["exit_timestamp_utc"] = _utc_text(exit_time)
    normalized["review_timestamp_utc"] = _utc_text(review)
    for field in NUMERIC_RECORD_FIELDS:
        normalized[field] = _number(record[field], "postmortem_trade_numeric_invalid")
    if normalized["quantity_or_units"] <= 0:
        _fail("postmortem_trade_numeric_invalid")
    normalized["direction"] = normalized["direction"].upper()
    if normalized["direction"] not in {"BUY", "SELL"}:
        _fail("postmortem_trade_direction_invalid")
    return normalized


def _metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pnl = [float(record["realized_pl"]) for record in records]
    wins = sum(value > 0 for value in pnl)
    losses = sum(value < 0 for value in pnl)
    breakevens = len(pnl) - wins - losses
    gross_profit = round(sum(value for value in pnl if value > 0), 8)
    gross_loss = round(abs(sum(value for value in pnl if value < 0)), 8)
    realized = round(sum(pnl), 8)
    equity = peak = maximum_drawdown = 0.0
    for value in pnl:
        equity = round(equity + value, 8)
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, peak - equity)
    profit_factor = round(gross_profit / gross_loss, 8) if gross_loss else None
    return {
        "trade_count": len(pnl),
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "realized_paper_pl": realized,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "expectancy": round(realized / len(pnl), 8),
        "profit_factor": profit_factor,
        "maximum_drawdown": round(maximum_drawdown, 8),
    }


def _same_number(actual: Any, expected: float) -> bool:
    try:
        return math.isfinite(float(actual)) and round(float(actual), 8) == expected
    except (TypeError, ValueError):
        return False


def _validate_campaign_reconciliation(
    campaign: Mapping[str, Any], records: Sequence[Mapping[str, Any]], metrics: Mapping[str, Any]
) -> tuple[datetime, datetime, datetime | None]:
    if campaign.get("campaign_version") != CAMPAIGN_VERSION:
        _fail("postmortem_campaign_version_unsupported")
    if campaign.get("qualifying_strategy_name") != SUPERTREND_PULLBACK_V1:
        _fail("postmortem_campaign_strategy_mismatch")
    if campaign.get("campaign_status") not in {"COMPLETE", "STOPPED", "WAITING_FOR_NEXT_RUN"}:
        _fail("postmortem_campaign_not_closed_for_review")

    count = len(records)
    if (
        _count(campaign.get("accepted_qualifying_trades"), "postmortem_campaign_count_invalid") != count
        or _count(campaign.get("current_trade_number"), "postmortem_campaign_count_invalid") != count
        or campaign.get("strategy_qualifying_trade_counts") != {SUPERTREND_PULLBACK_V1: count}
    ):
        _fail("postmortem_campaign_count_contradiction")

    trade_results = _sequence(campaign.get("trade_results"), "postmortem_campaign_results_invalid")
    if len(trade_results) != count:
        _fail("postmortem_campaign_results_contradiction")
    for index, (record, result_value) in enumerate(zip(records, trade_results, strict=True), start=1):
        result = _mapping(result_value, "postmortem_campaign_results_invalid")
        expected_outcome = (
            "WIN" if record["realized_pl"] > 0 else "LOSS" if record["realized_pl"] < 0 else "FLAT"
        )
        if (
            result.get("trade_number") != index
            or result.get("trade_id") != record["trade_id"]
            or result.get("strategy_name") != SUPERTREND_PULLBACK_V1
            or result.get("win_or_loss") != expected_outcome
            or not _same_number(result.get("realized_paper_pl"), float(record["realized_pl"]))
        ):
            _fail("postmortem_campaign_results_contradiction")

    source_profit_factor: float | str | None = metrics["profit_factor"]
    if metrics["gross_loss"] == 0:
        source_profit_factor = "INFINITE" if metrics["gross_profit"] else None
    expected_numbers = {
        "net_pl": metrics["realized_paper_pl"],
        "gross_profit": metrics["gross_profit"],
        "gross_loss": metrics["gross_loss"],
        "maximum_drawdown": metrics["maximum_drawdown"],
        "expectancy": metrics["expectancy"],
    }
    if any(not _same_number(campaign.get(name), value) for name, value in expected_numbers.items()):
        _fail("postmortem_campaign_metric_contradiction")
    if source_profit_factor is None:
        if campaign.get("profit_factor") is not None:
            _fail("postmortem_campaign_metric_contradiction")
    elif isinstance(source_profit_factor, str):
        if campaign.get("profit_factor") != source_profit_factor:
            _fail("postmortem_campaign_metric_contradiction")
    elif not _same_number(campaign.get("profit_factor"), source_profit_factor):
        _fail("postmortem_campaign_metric_contradiction")

    started = _utc(campaign.get("started_utc"), "postmortem_campaign_timestamp_invalid")
    updated = _utc(campaign.get("updated_utc"), "postmortem_campaign_timestamp_invalid")
    if updated < started:
        _fail("postmortem_campaign_timestamp_order_invalid")
    completed_value = campaign.get("completed_utc")
    completed = None
    if completed_value is not None:
        completed = _utc(completed_value, "postmortem_campaign_timestamp_invalid")
        if completed != updated:
            _fail("postmortem_campaign_timestamp_order_invalid")
    elif campaign.get("campaign_status") in {"COMPLETE", "STOPPED"}:
        _fail("postmortem_campaign_completion_missing")
    return started, updated, completed


def _metric(value: float | int | None, reason: str | None = None) -> dict[str, Any]:
    return {
        "status": "CALCULATED" if value is not None else "UNAVAILABLE",
        "value": value,
        "reason": reason,
    }


def _build(
    session_evidence: Any, campaign_evidence: Any
) -> dict[str, Any]:
    ledger = _mapping(session_evidence, "postmortem_session_evidence_malformed")
    campaign = _mapping(campaign_evidence, "postmortem_campaign_evidence_malformed")
    _require_false_flags(ledger, LEDGER_SAFETY_FLAGS, "postmortem_ledger_authority_invalid")
    _require_false_flags(campaign, CAMPAIGN_SAFETY_FLAGS, "postmortem_campaign_authority_invalid")
    if _contains_sensitive(ledger) or _contains_sensitive(campaign):
        _fail("postmortem_sensitive_evidence_rejected")
    if ledger.get("version") != LEDGER_VERSION:
        _fail("postmortem_ledger_version_unsupported")
    raw_records = _sequence(ledger.get("records"), "postmortem_records_missing")
    if not raw_records:
        _fail("postmortem_records_missing")
    records = [_normalized_record(record) for record in raw_records]
    trade_ids = [record["trade_id"] for record in records]
    if len(set(trade_ids)) != len(trade_ids):
        _fail("postmortem_duplicate_trade_id")
    expected_order = sorted(records, key=lambda item: (item["exit_timestamp_utc"], item["trade_id"]))
    if records != expected_order:
        _fail("postmortem_record_order_invalid")

    metrics = _metrics(records)
    campaign_started, campaign_updated, campaign_completed = _validate_campaign_reconciliation(
        campaign, records, metrics
    )
    newest_review = max(
        _utc(record["review_timestamp_utc"], "postmortem_trade_timestamp_invalid")
        for record in records
    )
    if newest_review > campaign_updated:
        _fail("postmortem_evidence_from_future")
    if campaign_updated - newest_review > MAX_EVIDENCE_AGE:
        _fail("postmortem_evidence_stale")

    earliest_entry = min(
        _utc(record["entry_timestamp_utc"], "postmortem_trade_timestamp_invalid")
        for record in records
    )
    latest_exit = max(
        _utc(record["exit_timestamp_utc"], "postmortem_trade_timestamp_invalid")
        for record in records
    )
    lineage_basis = {
        "ledger_version": LEDGER_VERSION,
        "campaign_version": CAMPAIGN_VERSION,
        "campaign_started_utc": _utc_text(campaign_started),
        "campaign_updated_utc": _utc_text(campaign_updated),
        "records": records,
    }
    lineage_json = json.dumps(lineage_basis, sort_keys=True, separators=(",", ":"), allow_nan=False)
    lineage_sha256 = hashlib.sha256(lineage_json.encode("utf-8")).hexdigest()
    session_id = f"supertrend-paper-session-{lineage_sha256[:20]}"

    unavailable: list[dict[str, str]] = []
    profit_factor_reason = None
    if metrics["profit_factor"] is None:
        profit_factor_reason = (
            "NO_LOSING_TRADES" if metrics["gross_profit"] else "NO_PROFIT_OR_LOSS_OBSERVED"
        )
        unavailable.append({"field": "profit_factor", "reason": profit_factor_reason})
    findings = [
        "SESSION_AND_CAMPAIGN_EVIDENCE_RECONCILED",
        "TRADE_COUNTS_RECONCILED",
        "REALIZED_PAPER_PL_RECONCILED",
    ]
    if unavailable:
        findings.append("UNPROVABLE_METRICS_LEFT_UNAVAILABLE")

    output = {
        "schema": SCHEMA,
        "version": VERSION,
        "session_identity": {
            "session_id": session_id,
            "identity_status": "CALCULATED_FROM_EVIDENCE_LINEAGE",
            "started_at_utc": _utc_text(earliest_entry),
            "ended_at_utc": _utc_text(latest_exit),
        },
        "strategy_identity": {
            "strategy_id": SUPERTREND_PULLBACK_V1,
            "strategy_name": SUPERTREND_PULLBACK_V1,
            "mode": "PAPER_ONLY",
            "paper_only": True,
        },
        "evidence_lineage": {
            "ledger_version": LEDGER_VERSION,
            "campaign_version": CAMPAIGN_VERSION,
            "source_sha256": lineage_sha256,
            "trade_ids": trade_ids,
            "record_count": len(records),
        },
        "observed_facts": {
            "campaign_status": campaign["campaign_status"],
            "campaign_started_utc": _utc_text(campaign_started),
            "campaign_updated_utc": _utc_text(campaign_updated),
            "campaign_completed_utc": (
                _utc_text(campaign_completed) if campaign_completed is not None else None
            ),
            "campaign_stop_reason": campaign.get("stop_reason"),
            "p1_status": campaign.get("p1_status"),
        },
        "calculated_metrics": {
            "trade_count": _metric(metrics["trade_count"]),
            "wins": _metric(metrics["wins"]),
            "losses": _metric(metrics["losses"]),
            "breakevens": _metric(metrics["breakevens"]),
            "realized_paper_pl": _metric(metrics["realized_paper_pl"]),
            "expectancy": _metric(metrics["expectancy"]),
            "profit_factor": _metric(metrics["profit_factor"], profit_factor_reason),
            "maximum_drawdown": _metric(metrics["maximum_drawdown"]),
        },
        "unavailable_information": unavailable,
        "findings": findings,
        "safety_flags": dict(SAFETY_FLAGS),
        "disposition": {
            "status": "OWNER_REVIEW_REQUIRED",
            "automatic_promotion_allowed": False,
            "next_safe_action": "Human owner review of sanitized PAPER evidence; no execution is authorized.",
        },
    }
    stable_json(output)
    return output


def build_supertrend_session_postmortem(
    session_evidence: Any, campaign_evidence: Any
) -> dict[str, Any]:
    """Build a sanitized postmortem or fail with a stable non-sensitive code."""
    try:
        return _build(session_evidence, campaign_evidence)
    except PostmortemValidationError:
        raise
    except Exception:
        raise PostmortemValidationError("postmortem_evidence_invalid") from None
