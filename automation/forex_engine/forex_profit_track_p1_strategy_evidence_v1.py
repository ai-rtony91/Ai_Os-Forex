"""Fail-closed, local-only Profit Track P1 strategy evidence evaluation."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from automation.forex_engine.profit_proof_ledger_v1 import ProfitProofLedgerConfig

VERSION = "forex_profit_track_p1_strategy_evidence_v1"
VALID_EVIDENCE_TYPES = {"paper", "supervised_demo"}
KNOWN_EVIDENCE_TYPES = VALID_EVIDENCE_TYPES | {"fixture", "live"}
REQUIRED_FIELDS = ("trade_id", "entry", "exit", "realized_pl", "timestamp", "evidence_type")
PRIVATE_KEYS = {
    "account_id", "account_number", "api_key", "authorization", "credential",
    "credentials", "password", "private_account_id", "secret", "token",
}
RAW_PAYLOAD_KEYS = {"broker_payload", "raw_broker_payload", "raw_payload"}
SAFETY_FLAGS = {
    "broker_call_performed": False,
    "broker_write_performed": False,
    "credentials_loaded": False,
    "order_submission_allowed": False,
    "live_execution_allowed": False,
    "money_movement_allowed": False,
}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _unsafe_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in PRIVATE_KEYS | RAW_PAYLOAD_KEYS:
                found.add(normalized)
            found.update(_unsafe_keys(child))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            found.update(_unsafe_keys(child))
    return found


def _max_drawdown(pnl_values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for pnl in pnl_values:
        equity += pnl
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return round(drawdown, 8)


def _consecutive_losses(pnl_values: list[float]) -> int:
    current = longest = 0
    for pnl in pnl_values:
        current = current + 1 if pnl < 0 else 0
        longest = max(longest, current)
    return longest


def evaluate_strategy_evidence(
    records: Any = None,
    *,
    as_of: datetime | None = None,
    max_evidence_age_days: int = 7,
    config: ProfitProofLedgerConfig | None = None,
) -> dict[str, Any]:
    """Evaluate sanitized trade records without granting execution authority."""
    active_config = config or ProfitProofLedgerConfig()
    now = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    raw_records = list(records) if isinstance(records, Sequence) and not isinstance(records, (str, bytes)) else []
    rejected: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    if records is not None and not isinstance(records, Sequence):
        rejected.append({"record_index": None, "reasons": ["malformed_record_container"]})

    for index, raw in enumerate(raw_records):
        reasons: list[str] = []
        if not isinstance(raw, Mapping):
            rejected.append({"record_index": index, "reasons": ["malformed_record"]})
            continue
        unsafe = _unsafe_keys(raw)
        if unsafe & RAW_PAYLOAD_KEYS:
            reasons.append("raw_broker_payload_rejected")
        if unsafe & PRIVATE_KEYS:
            reasons.append("secret_or_private_account_identifier_rejected")
        missing = [field for field in REQUIRED_FIELDS if field not in raw or raw[field] in (None, "")]
        reasons.extend(f"missing_{field}" for field in missing)
        trade_id = str(raw.get("trade_id", "")).strip()
        if trade_id and trade_id in seen_ids:
            reasons.append("duplicate_trade_id")
        entry = _finite_number(raw.get("entry"))
        exit_price = _finite_number(raw.get("exit"))
        pnl = _finite_number(raw.get("realized_pl"))
        for field, value in (("entry", entry), ("exit", exit_price), ("realized_pl", pnl)):
            if field not in missing and value is None:
                reasons.append(f"non_finite_or_invalid_{field}")
        timestamp = _timestamp(raw.get("timestamp"))
        if "timestamp" not in missing and timestamp is None:
            reasons.append("invalid_timestamp")
        evidence_type = str(raw.get("evidence_type", "")).strip().lower()
        if evidence_type and evidence_type not in KNOWN_EVIDENCE_TYPES:
            reasons.append("invalid_evidence_type")
        if reasons:
            rejected.append({"record_index": index, "trade_id": trade_id or None, "reasons": reasons})
            continue
        seen_ids.add(trade_id)
        accepted.append({
            "trade_id": trade_id,
            "entry": entry,
            "exit": exit_price,
            "realized_pl": pnl,
            "timestamp": timestamp,
            "evidence_type": evidence_type,
        })

    qualifying = [record for record in accepted if record["evidence_type"] in VALID_EVIDENCE_TYPES]
    pnl_values = [record["realized_pl"] for record in qualifying]
    wins = [pnl for pnl in pnl_values if pnl > 0]
    losses = [pnl for pnl in pnl_values if pnl < 0]
    gross_profit = round(sum(wins), 8)
    gross_loss = round(abs(sum(losses)), 8)
    trade_count = len(qualifying)
    expectancy = round(sum(pnl_values) / trade_count, 8) if trade_count else 0.0
    profit_factor = round(gross_profit / gross_loss, 8) if gross_loss else (None if not gross_profit else "INFINITE")
    max_drawdown = _max_drawdown(pnl_values)
    timestamps = [record["timestamp"] for record in qualifying]
    latest = max(timestamps) if timestamps else None
    freshness_days = max((now - latest).total_seconds() / 86400, 0.0) if latest else None
    evidence_fresh = freshness_days is not None and freshness_days <= max_evidence_age_days
    evidence_types = sorted({record["evidence_type"] for record in accepted})

    missing_evidence: list[str] = []
    if not qualifying:
        missing_evidence.append("qualifying_paper_or_supervised_demo_evidence")
    if trade_count < active_config.minimum_total_trades:
        missing_evidence.append("minimum_trade_sample")
    if not evidence_fresh:
        missing_evidence.append("fresh_evidence")

    numeric_profit_factor = float("inf") if profit_factor == "INFINITE" else (profit_factor or 0.0)
    risk_failed = (
        max_drawdown > float(active_config.maximum_drawdown)
        or _consecutive_losses(pnl_values) > active_config.maximum_consecutive_losses
        or numeric_profit_factor < float(active_config.minimum_profit_factor)
    )
    if not qualifying:
        status = "NO_EVIDENCE"
    elif trade_count < active_config.minimum_total_trades:
        status = "INSUFFICIENT_SAMPLE"
    elif expectancy <= 0:
        status = "NEGATIVE_EXPECTANCY"
    elif risk_failed:
        status = "RISK_LIMIT_FAILED"
    elif not evidence_fresh or rejected:
        status = "REQUIRE_MORE_EVIDENCE"
    else:
        status = "READY_FOR_P2_REVIEW"

    profitability_proven = status == "READY_FOR_P2_REVIEW"
    return {
        "version": VERSION,
        "strategy_evidence_status": status,
        "evidence_types": evidence_types,
        "trade_count": trade_count,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(len(wins) / trade_count, 8) if trade_count else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pl": round(sum(pnl_values), 8),
        "average_win": round(gross_profit / len(wins), 8) if wins else 0.0,
        "average_loss": round(gross_loss / len(losses), 8) if losses else 0.0,
        "expectancy_per_trade": expectancy,
        "profit_factor": profit_factor,
        "maximum_drawdown": max_drawdown,
        "consecutive_losses": _consecutive_losses(pnl_values),
        "evidence_date_range": {
            "start": min(timestamps).isoformat() if timestamps else None,
            "end": latest.isoformat() if latest else None,
        },
        "evidence_freshness": {
            "as_of": now.isoformat(), "age_days": round(freshness_days, 8) if freshness_days is not None else None,
            "maximum_age_days": max_evidence_age_days, "fresh": evidence_fresh,
        },
        "missing_evidence": missing_evidence,
        "rejected_records": rejected,
        "accepted_record_count": len(accepted),
        "thresholds": {
            "source": "ProfitProofLedgerConfig",
            "minimum_total_trades": active_config.minimum_total_trades,
            "minimum_profit_factor": float(active_config.minimum_profit_factor),
            "maximum_drawdown": float(active_config.maximum_drawdown),
            "maximum_consecutive_losses": active_config.maximum_consecutive_losses,
            "maximum_evidence_age_days": max_evidence_age_days,
        },
        **SAFETY_FLAGS,
        "profitability_proven": profitability_proven,
        "ready_for_p2_review": profitability_proven,
    }


def result_to_markdown(result: Mapping[str, Any]) -> str:
    """Render a deterministic, operator-readable report."""
    return "\n".join([
        "# AIOS Forex Profit Track P1 Strategy Evidence V1",
        "",
        f"- P1 status: {result['strategy_evidence_status']}",
        f"- Evidence types: {', '.join(result['evidence_types']) or 'NONE'}",
        f"- Trade count: {result['trade_count']}",
        f"- Win rate: {result['win_rate']}",
        f"- Expectancy per trade: {result['expectancy_per_trade']}",
        f"- Profit factor: {result['profit_factor']}",
        f"- Maximum drawdown: {result['maximum_drawdown']}",
        f"- Rejected records: {len(result['rejected_records'])}",
        f"- Missing evidence: {', '.join(result['missing_evidence']) or 'NONE'}",
        f"- Profitability proven: {str(result['profitability_proven']).lower()}",
        f"- Ready for P2 review: {str(result['ready_for_p2_review']).lower()}",
        f"- Live execution allowed: {str(result['live_execution_allowed']).lower()}",
        "",
        "This report grants no broker, order, credential, deployment, or money-movement authority.",
        "READY_FOR_P2_REVIEW is review-only and never automatic P2 approval.",
        "",
    ])
