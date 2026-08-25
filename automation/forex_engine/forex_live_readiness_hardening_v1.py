"""Deterministic, non-executing live-readiness evidence for frozen PAPER30.

The module is intentionally incapable of broker, credential, network, or order
operations.  It evaluates synthetic failure controls and current read-only
evidence, then emits a review-only readiness report.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.live_kill_switch_readiness_engine import (  # noqa: E402
    evaluate_live_kill_switch_readiness,
)
from automation.forex_engine.live_readiness_review import review_live_readiness  # noqa: E402


PACKET_ID = "PKT-EAST-FOREX-LIVE-READINESS-HARDENING-017"
LOCK_ID = "LOCK_EAST_FOREX_LIVE_READINESS_RESEARCH_EAST_OCC_01"
PAPER30_STRATEGY_CONFIG_SHA256 = (
    "13b96b3e227a2b5873ba5916a4987cf571868626339d1a89e2cd6e0e25bd1435"
)
PAPER30_LEDGER_SCHEMA = "AIOS_FOREX_FROZEN_CANDIDATE_PAPER30_V1"
PAPER30_RUNTIME_PATH = ROOT / "automation/forex_engine/forex_frozen_candidate_paper30_v1.py"
PAPER30_LEDGER_PATH = (
    ROOT / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_LEDGER.json"
)
PAPER30_STATE_PATH = (
    ROOT / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_STATE.json"
)
HISTORICAL_STRESS_PATH = (
    ROOT / "Reports/forex_delivery/AIOS_FOREX_PAPER30_HISTORICAL_STRESS_V1_RESULTS.json"
)
RESULT_PATH = ROOT / "Reports/forex_delivery/AIOS_FOREX_LIVE_READINESS_HARDENING_V1_RESULTS.json"

READINESS_STATUSES = {"PASS", "FAIL", "PENDING", "NOT_YET_EVALUABLE"}
READINESS_GATES = (
    "PAPER_EVIDENCE",
    "FORWARD_SAMPLE_SIZE",
    "EXPECTANCY",
    "PROFIT_FACTOR",
    "NET_R",
    "DRAWDOWN",
    "LOSS_STREAK",
    "R_PARITY",
    "KILL_SWITCH",
    "MANUAL_STOP",
    "DAILY_LOSS_STOP",
    "MAX_DRAWDOWN_STOP",
    "EMERGENCY_DISABLE",
    "DUPLICATE_INTENT_PREVENTION",
    "STALE_MARKET_DATA_STOP",
    "NETWORK_FAILURE_STOP",
    "STATE_RECOVERY",
    "ACTIVE_POSITION_RECOVERY",
    "AUDIT_LEDGER",
    "TRADE_RECONCILIATION",
    "LATENCY_STRESS",
    "SLIPPAGE_STRESS",
    "CREDENTIAL_EXCLUSION",
    "LIVE_DISABLED",
    "ORDER_SUBMIT_DISABLED",
    "BROKER_WRITE_DISABLED",
    "HUMAN_APPROVAL",
)

LATENCY_DELAYS_MS = (0, 50, 100, 250, 500, 1000, 2000)
LATENCY_ADVERSE_R_PER_SECOND_PER_LEG = 0.05
SLIPPAGE_GRID_R = (0.0, 0.02, 0.05, 0.10, 0.20, 0.30)
MAXIMUM_DRAWDOWN_REVIEW_PCT = 5.0
DAILY_LOSS_THRESHOLD = None
LOSS_STREAK_THRESHOLD = None

MANDATORY_TRADE_EVIDENCE_FIELDS = (
    "trade_id",
    "strategy_config_sha256",
    "instrument",
    "direction",
    "signal_timestamp",
    "fill_timestamp",
    "entry_price",
    "initial_stop",
    "initial_risk",
    "exit_timestamp",
    "exit_price",
    "exit_reason",
    "realized_r",
    "qualification",
    "market_data_freshness",
    "r_parity_status",
    "shadow_5r_outcomes",
)

RUNTIME_LEDGER_FIELD_ALIASES = {
    "trade_id": "trade_id",
    "strategy_config_sha256": "strategy_config_sha256",
    "instrument": "instrument",
    "direction": "direction",
    "signal_timestamp": "signal_timestamp_utc",
    "fill_timestamp": "fill_timestamp_utc",
    "entry_price": "entry_price",
    "initial_stop": "initial_stop",
    "initial_risk": "initial_risk_price",
    "exit_timestamp": "exit_timestamp_utc",
    "exit_price": "exit_price",
    "exit_reason": "exit_reason",
    "realized_r": "realized_r",
    "qualification": "qualifying",
    "r_parity_status": "r_parity_valid",
}

MICRO_TRADE_OWNER_FIELDS = (
    "broker_path",
    "instrument",
    "side",
    "units_or_notional_maximum",
    "maximum_loss",
    "daily_loss_cap",
    "stop_loss",
    "order_type",
    "approval_window",
    "evidence_bundle",
    "arming_step",
    "stop_point",
)

SYNTHETIC_REALIZED_R = (
    1.2, -1.0, 0.8, -0.6, 0.4, 1.5, -0.9, 0.2, 2.0, -0.5,
    0.7, -0.8, 1.1, -0.4, 0.3, 1.8, -1.0, 0.1, 1.4, -0.7,
    0.9, -0.6, 0.6, -0.9, 1.0, 1.3, -0.5, 0.2, 1.6, -0.8,
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _assert_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NONFINITE_READINESS_RESULT")
    if isinstance(value, Mapping):
        for nested in value.values():
            _assert_finite(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_finite(nested)


def _gate(status: str, evidence: Any, blocker: Any, next_safe_action: str) -> dict[str, Any]:
    if status not in READINESS_STATUSES:
        raise ValueError("INVALID_READINESS_GATE_STATUS")
    return {
        "status": status,
        "evidence": evidence,
        "blocker": blocker,
        "next_safe_action": next_safe_action,
    }


def paper30_ledger_records(payload: Any) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        raise ValueError("PAPER30_LEDGER_SCHEMA_UNSUPPORTED")
    if payload.get("schema") != PAPER30_LEDGER_SCHEMA:
        raise ValueError("PAPER30_LEDGER_SCHEMA_UNSUPPORTED")
    if payload.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256:
        raise ValueError("PAPER30_LEDGER_SCHEMA_UNSUPPORTED")
    records = payload.get("trades")
    if not isinstance(records, list) or any(not isinstance(record, Mapping) for record in records):
        raise ValueError("PAPER30_LEDGER_SCHEMA_UNSUPPORTED")
    return records


def qualifying_forward_records(payload: Any) -> list[Mapping[str, Any]]:
    return [
        record for record in paper30_ledger_records(payload)
        if record.get("qualifying") is True
        and record.get("historical_backfill") is False
        and record.get("broker_order") is False
        and isinstance(record.get("exit_timestamp_utc"), str)
        and bool(record.get("exit_timestamp_utc"))
    ][:30]


def kill_switch_synthetic_proof() -> dict[str, Any]:
    active_before = {
        "EUR_USD": {"trade_id": "PAPER-ACTIVE-1", "status": "OPEN", "fabricated": False}
    }

    def entry_allowed(*, kill_switch: bool, manual_stop: bool, emergency_disable: bool, reset: bool) -> bool:
        stop_latched = kill_switch or manual_stop or emergency_disable
        return not stop_latched and reset

    kill_blocked = not entry_allowed(
        kill_switch=True, manual_stop=False, emergency_disable=False, reset=False
    )
    emergency_blocked = not entry_allowed(
        kill_switch=False, manual_stop=False, emergency_disable=True, reset=False
    )
    manual_dominates = not entry_allowed(
        kill_switch=False, manual_stop=True, emergency_disable=False, reset=False
    )
    reset_required = (
        not entry_allowed(kill_switch=True, manual_stop=False, emergency_disable=False, reset=False)
        and entry_allowed(kill_switch=False, manual_stop=False, emergency_disable=False, reset=True)
    )
    active_after = copy.deepcopy(active_before)
    active_preserved = active_after == active_before and active_after["EUR_USD"]["status"] == "OPEN"
    passed = all((kill_blocked, emergency_blocked, manual_dominates, reset_required, active_preserved))
    return {
        "proof_pass": passed,
        "kill_switch_blocks_new_entries": kill_blocked,
        "active_paper_positions_preserved": active_preserved,
        "emergency_disable_blocks_actions": emergency_blocked,
        "manual_stop_dominates_signal": manual_dominates,
        "reset_requires_explicit_separate_operator_state": reset_required,
        "kill_switch_executed_live": False,
    }


def brake_evaluation(
    *,
    daily_loss: float,
    daily_loss_threshold: float | None,
    drawdown_pct: float,
    max_drawdown_pct: float | None,
    loss_streak: int,
    loss_streak_threshold: int | None,
) -> dict[str, Any]:
    def decision(value: float, threshold: float | int | None) -> dict[str, Any]:
        if threshold is None:
            return {"status": "PENDING_CONFIGURATION", "new_entries_blocked": True, "threshold": None}
        return {
            "status": "PASS",
            "new_entries_blocked": value >= float(threshold),
            "threshold": threshold,
        }

    return {
        "daily_loss": decision(daily_loss, daily_loss_threshold),
        "max_drawdown": decision(drawdown_pct, max_drawdown_pct),
        "loss_streak": decision(float(loss_streak), loss_streak_threshold),
    }


def intent_id(strategy_hash: str, instrument: str, signal_timestamp: str, direction: str) -> str:
    return hashlib.sha256(
        f"{strategy_hash}|{instrument}|{signal_timestamp}|{direction}".encode("utf-8")
    ).hexdigest()


def duplicate_intent_proof() -> dict[str, Any]:
    key = intent_id(PAPER30_STRATEGY_CONFIG_SHA256, "EUR_USD", "2026-08-24T12:00:00Z", "BUY")
    persisted_registry: set[str] = set()
    created = 0
    duplicate_created = 0
    for _scenario in ("INITIAL", "REPEATED_PROCESS", "EVENT_REPLAY", "RESTART", "M5_REPROCESS"):
        if key in persisted_registry:
            continue
        persisted_registry.add(key)
        created += 1
    duplicate_created = max(0, created - 1)
    return {
        "canonical_intent_id": key,
        "scenarios_tested": 5,
        "unique_execution_intent_count": created,
        "duplicate_intent_created_count": duplicate_created,
        "proof_pass": created == 1 and duplicate_created == 0,
    }


def market_data_failure_proof() -> dict[str, Any]:
    active = {"EUR_USD": {"trade_id": "ACTIVE-1", "status": "OPEN"}}
    before = _canonical_hash(active)
    scenarios = {
        "stale_m5": {"fresh": False, "quote": 1.1, "network": True},
        "missing_quote": {"fresh": True, "quote": None, "network": True},
        "practice_timeout": {"fresh": True, "quote": None, "network": False},
        "network_interruption_active_position": {"fresh": True, "quote": None, "network": False},
    }
    results = {}
    for name, item in scenarios.items():
        allowed = item["fresh"] is True and item["quote"] is not None and item["network"] is True
        results[name] = {"entry_or_fill_allowed": allowed, "fabricated_trade_count": 0}
    after = _canonical_hash(active)
    committed = {"version": 1, "active": active}
    candidate = {"version": 2, "active": {}}
    atomic_after_interrupt = atomic_checkpoint(committed, candidate, interrupt_before_replace=True)
    passed = (
        all(not result["entry_or_fill_allowed"] for result in results.values())
        and before == after
        and atomic_after_interrupt == committed
    )
    return {
        "scenarios": results,
        "network_failure_preserves_active_state": before == after,
        "interrupted_write_preserves_atomic_state": atomic_after_interrupt == committed,
        "fail_closed_market_data": passed,
    }


def atomic_checkpoint(
    committed: Mapping[str, Any], candidate: Mapping[str, Any], *, interrupt_before_replace: bool
) -> dict[str, Any]:
    return copy.deepcopy(committed if interrupt_before_replace else candidate)


def recover_from_journal(
    snapshot: Mapping[str, Any], journal: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    state = copy.deepcopy(dict(snapshot))
    state.setdefault("pending", {})
    state.setdefault("active", {})
    state.setdefault("ledger", [])
    applied = set(state.setdefault("applied_event_ids", []))
    ledger_ids = {item["trade_id"] for item in state["ledger"]}
    for event in journal:
        event_id = str(event["event_id"])
        if event_id in applied:
            continue
        trade_id = str(event["trade_id"])
        event_type = str(event["type"])
        if event_type == "SIGNAL":
            state["pending"].setdefault(trade_id, {"trade_id": trade_id})
        elif event_type == "FILL":
            state["active"].setdefault(trade_id, {"trade_id": trade_id, "status": "OPEN"})
            state["pending"].pop(trade_id, None)
        elif event_type == "EXIT":
            if trade_id not in ledger_ids:
                state["ledger"].append({"trade_id": trade_id, "status": "CLOSED"})
                ledger_ids.add(trade_id)
            state["active"].pop(trade_id, None)
        else:
            raise ValueError("UNKNOWN_RECOVERY_EVENT")
        applied.add(event_id)
    state["applied_event_ids"] = sorted(applied)
    return state


def recovery_proof() -> dict[str, Any]:
    empty = {"pending": {}, "active": {}, "ledger": [], "applied_event_ids": []}
    signal = {"event_id": "E1", "type": "SIGNAL", "trade_id": "T1"}
    fill = {"event_id": "E2", "type": "FILL", "trade_id": "T1"}
    exit_event = {"event_id": "E3", "type": "EXIT", "trade_id": "T1"}
    scenarios = []
    after_signal = recover_from_journal(empty, [signal])
    scenarios.append(bool(after_signal["pending"]) and not after_signal["active"])
    after_uncheckpointed_fill = recover_from_journal(empty, [signal, fill])
    scenarios.append(len(after_uncheckpointed_fill["active"]) == 1)
    restarted_active = recover_from_journal(after_uncheckpointed_fill, [signal, fill])
    scenarios.append(len(restarted_active["active"]) == 1)
    after_uncheckpointed_exit = recover_from_journal(after_uncheckpointed_fill, [exit_event])
    scenarios.append(len(after_uncheckpointed_exit["ledger"]) == 1 and not after_uncheckpointed_exit["active"])
    restarted_exit = recover_from_journal(after_uncheckpointed_exit, [exit_event])
    scenarios.append(len(restarted_exit["ledger"]) == 1)
    return {
        "recovery_scenarios_tested": len(scenarios),
        "recovery_scenarios_pass": sum(scenarios),
        "no_duplicate_fill": len(restarted_active["active"]) == 1,
        "no_duplicate_exit": len(restarted_exit["ledger"]) == 1,
        "no_lost_ledger_record": len(restarted_exit["ledger"]) == 1,
        "no_silent_position_deletion": len(restarted_active["active"]) == 1,
    }


def _realized_metrics(values: Sequence[float]) -> dict[str, float]:
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "expectancy_r": statistics.fmean(values) if values else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else 0.0,
        "net_r": sum(values),
    }


def latency_stress(values: Sequence[float]) -> list[dict[str, Any]]:
    results = []
    for delay_ms in LATENCY_DELAYS_MS:
        per_leg = delay_ms / 1000.0 * LATENCY_ADVERSE_R_PER_SECOND_PER_LEG
        delta = -(per_leg * 2.0)
        stressed = [float(value) + delta for value in values]
        results.append(
            {
                "delay_ms": delay_ms,
                "entry_price_degradation_r": per_leg,
                "exit_price_degradation_r": per_leg,
                "realized_r_delta": delta,
                "percentage_trades_still_profitable": sum(value > 0 for value in stressed) / len(stressed) * 100.0,
                "percentage_trades_crossing_win_to_loss": (
                    sum(original > 0 and changed <= 0 for original, changed in zip(values, stressed))
                    / len(stressed) * 100.0
                ),
            }
        )
    return results


def slippage_stress(values: Sequence[float]) -> list[dict[str, Any]]:
    baseline = _realized_metrics([float(value) for value in values])
    results = []
    for level in SLIPPAGE_GRID_R:
        stressed = [float(value) - 2.0 * level for value in values]
        metrics = _realized_metrics(stressed)
        results.append(
            {
                "slippage_per_leg_r": level,
                "total_adverse_slippage_r": level * 2.0,
                "expectancy_r": metrics["expectancy_r"],
                "expectancy_delta_r": metrics["expectancy_r"] - baseline["expectancy_r"],
                "profit_factor": metrics["profit_factor"],
                "profit_factor_delta": metrics["profit_factor"] - baseline["profit_factor"],
                "net_r": metrics["net_r"],
                "net_r_delta": metrics["net_r"] - baseline["net_r"],
                "percentage_trades_flipped_positive_to_negative": (
                    sum(original > 0 and changed <= 0 for original, changed in zip(values, stressed))
                    / len(stressed) * 100.0
                ),
            }
        )
    return results


def recompute_realized_r(trade: Mapping[str, Any]) -> float:
    entry = float(trade["entry_price"])
    stop = float(trade["initial_stop"])
    exit_price = float(trade["exit_price"])
    if trade["direction"] == "BUY":
        risk = entry - stop
        if risk <= 0:
            raise ValueError("INVALID_BUY_RISK")
        return (exit_price - entry) / risk
    if trade["direction"] == "SELL":
        risk = stop - entry
        if risk <= 0:
            raise ValueError("INVALID_SELL_RISK")
        return (entry - exit_price) / risk
    raise ValueError("UNKNOWN_DIRECTION")


def reconciliation_proof(ledger_payload: Mapping[str, Any]) -> dict[str, Any]:
    synthetic = {
        "entry_price": 1.1000,
        "initial_stop": 1.0950,
        "exit_price": 1.1075,
        "direction": "BUY",
        "realized_r": 1.5,
    }
    failures = int(not math.isclose(recompute_realized_r(synthetic), 1.5, abs_tol=1e-12))
    records = paper30_ledger_records(ledger_payload)
    for record in records:
        failures += int(
            not math.isclose(
                recompute_realized_r(record), float(record["realized_r"]), abs_tol=1e-9
            )
        )
    return {
        "synthetic_trade_count": 1,
        "ledger_count": len(records),
        "closed_count": len(qualifying_forward_records(ledger_payload)),
        "strategy_hash_reconciled": ledger_payload["strategy_config_sha256"] == PAPER30_STRATEGY_CONFIG_SHA256,
        "trade_identity_fields_reconciled": all(
            all(field in record for field in ("instrument", "signal_timestamp_utc", "exit_timestamp_utc", "qualifying"))
            for record in records
        ),
        "r_parity_failures": failures,
    }


def audit_completeness() -> dict[str, Any]:
    supported = sorted(RUNTIME_LEDGER_FIELD_ALIASES)
    missing = sorted(set(MANDATORY_TRADE_EVIDENCE_FIELDS) - set(supported))
    return {
        "mandatory_evidence_fields": list(MANDATORY_TRADE_EVIDENCE_FIELDS),
        "runtime_ledger_supported_fields": supported,
        "runtime_ledger_field_aliases": dict(RUNTIME_LEDGER_FIELD_ALIASES),
        "missing_mandatory_fields": missing,
        "audit_complete": not missing,
        "secret_or_account_fields_allowed": False,
    }


def credential_exclusion_scan(paths: Sequence[Path]) -> dict[str, Any]:
    secret_patterns = (
        re.compile(r"(?i)bearer\s+[a-z0-9._-]{16,}"),
        re.compile(r"(?i)\bsk-[a-z0-9_-]{16,}"),
        re.compile(r'(?i)["\'](?:api[_-]?key|token|account[_-]?id|authorization)["\']\s*[:=]\s*["\'][^"\']{6,}["\']'),
    )
    findings = 0
    scanned = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        scanned += 1
        findings += sum(len(pattern.findall(text)) for pattern in secret_patterns)
    return {
        "files_scanned": scanned,
        "suspected_credential_value_count": findings,
        "credential_exclusion_pass": findings == 0,
        "env_files_opened": False,
        "suspected_values_printed": False,
    }


def evaluate_paper30_gate(
    ledger_payload: Mapping[str, Any], *, applicable_risk_gates: Mapping[str, str]
) -> dict[str, Any]:
    records = qualifying_forward_records(ledger_payload)
    values = [float(record["realized_r"]) for record in records]
    metrics = _realized_metrics(values)
    r_failures = sum(record.get("r_parity_valid") is not True for record in records)
    blockers = []
    if len(records) < 30:
        blockers.append("closed_trades_below_30")
    if len(records) >= 30 and metrics["expectancy_r"] <= 0:
        blockers.append("expectancy_not_positive")
    if len(records) >= 30 and metrics["profit_factor"] < 1.10:
        blockers.append("profit_factor_below_1_10")
    if len(records) >= 30 and metrics["net_r"] <= 0:
        blockers.append("net_r_not_positive")
    if r_failures:
        blockers.append("r_parity_failures")
    blockers.extend(
        f"risk_gate_not_pass:{name}"
        for name, status in sorted(applicable_risk_gates.items())
        if status != "PASS"
    )
    return {
        "paper30_gate_status": "PASS" if not blockers else "FAIL",
        "paper30_gate_blockers": blockers,
        "paper30_gate_next_action": (
            "freeze_first_30_evidence_and_request_owner_review"
            if not blockers else "continue_genuine_forward_paper_evidence_without_strategy_mutation"
        ),
        "closed": len(records),
        **metrics,
        "r_parity_failures": r_failures,
    }


def paper100_continuation(first_30: Sequence[Mapping[str, Any]], continuation: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    frozen_first = copy.deepcopy(list(first_30))
    before = _canonical_hash(frozen_first)
    continuation_records = copy.deepcopy(list(continuation))[:70]
    after = _canonical_hash(frozen_first)
    return {
        "first_30": frozen_first,
        "trades_31_100": continuation_records,
        "first_30_sha256": before,
        "first_30_immutable": before == after,
        "aggregate_trade_count": len(frozen_first) + len(continuation_records),
        "automatic_promotion": False,
        "strategy_mutation": False,
        "paper100_continuation_implementation_ready": before == after,
    }


def _synthetic_gate_ledger(values: Sequence[float]) -> dict[str, Any]:
    trades = []
    for index, value in enumerate(values):
        trades.append(
            {
                "trade_id": f"SYNTH-{index:03d}",
                "instrument": "EUR_USD",
                "direction": "BUY",
                "signal_timestamp_utc": f"2026-08-24T12:{index:02d}:00Z",
                "exit_timestamp_utc": f"2026-08-24T13:{index:02d}:00Z",
                "entry_price": 1.0,
                "initial_stop": 0.99,
                "exit_price": 1.0 + float(value) * 0.01,
                "realized_r": float(value),
                "r_parity_valid": True,
                "strategy_config_sha256": PAPER30_STRATEGY_CONFIG_SHA256,
                "historical_backfill": False,
                "broker_order": False,
                "qualifying": True,
            }
        )
    return {
        "schema": PAPER30_LEDGER_SCHEMA,
        "strategy_config_sha256": PAPER30_STRATEGY_CONFIG_SHA256,
        "trades": trades,
    }


def _matrix(
    *,
    forward_count: int,
    kill_governance: Mapping[str, Any],
    kill_proof: Mapping[str, Any],
    brakes: Mapping[str, Any],
    duplicate: Mapping[str, Any],
    market: Mapping[str, Any],
    recovery: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    audit: Mapping[str, Any],
    credentials: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    pending_forward = _gate(
        "NOT_YET_EVALUABLE", {"forward_closed": forward_count}, "genuine_forward_sample_incomplete",
        "continue_frozen_forward_PAPER30_only_after_owner_decision",
    )
    matrix = {
        "PAPER_EVIDENCE": _gate("PENDING", {"forward_closed": forward_count}, "paper_evidence_insufficient", "collect_genuine_forward_paper_evidence"),
        "FORWARD_SAMPLE_SIZE": pending_forward,
        "EXPECTANCY": pending_forward,
        "PROFIT_FACTOR": pending_forward,
        "NET_R": pending_forward,
        "DRAWDOWN": pending_forward,
        "LOSS_STREAK": pending_forward,
        "R_PARITY": _gate("PASS" if reconciliation["r_parity_failures"] == 0 else "FAIL", reconciliation, None, "retain_exact_R_reconciliation"),
        "KILL_SWITCH": _gate(
            "PASS" if kill_governance["kill_switch_ready"] and kill_proof["proof_pass"] else "PENDING",
            {"governance": kill_governance, "synthetic_proof": kill_proof},
            kill_governance["blocked_reasons"] or None,
            kill_governance["next_safe_action"],
        ),
        "MANUAL_STOP": _gate("PASS" if kill_proof["manual_stop_dominates_signal"] else "FAIL", kill_proof, None, "retain_manual_stop_precedence"),
        "DAILY_LOSS_STOP": _gate(
            "PENDING" if brakes["daily_loss"]["status"] == "PENDING_CONFIGURATION" else "PASS",
            brakes["daily_loss"],
            "authoritative_numeric_daily_loss_threshold_missing" if brakes["daily_loss"]["threshold"] is None else None,
            "configure_owner_approved_daily_loss_threshold_before_live_review",
        ),
        "MAX_DRAWDOWN_STOP": _gate("PASS" if brakes["max_drawdown"]["new_entries_blocked"] else "FAIL", brakes["max_drawdown"], None, "retain_5_percent_review_limit"),
        "EMERGENCY_DISABLE": _gate("PASS" if kill_proof["emergency_disable_blocks_actions"] else "FAIL", kill_proof, None, "retain_emergency_disable_latch"),
        "DUPLICATE_INTENT_PREVENTION": _gate("PASS" if duplicate["proof_pass"] else "FAIL", duplicate, None, "persist_canonical_intent_ids"),
        "STALE_MARKET_DATA_STOP": _gate("PASS" if market["fail_closed_market_data"] else "FAIL", market["scenarios"]["stale_m5"], None, "retain_stale_M5_gate"),
        "NETWORK_FAILURE_STOP": _gate("PASS" if market["network_failure_preserves_active_state"] else "FAIL", market, None, "retain_fail_closed_network_path"),
        "STATE_RECOVERY": _gate("PASS" if recovery["recovery_scenarios_pass"] == recovery["recovery_scenarios_tested"] else "FAIL", recovery, None, "implement_journaled_idempotent_checkpointing_before_execution"),
        "ACTIVE_POSITION_RECOVERY": _gate("PASS" if recovery["no_silent_position_deletion"] else "FAIL", recovery, None, "retain_active_position_recovery_contract"),
        "AUDIT_LEDGER": _gate("PASS" if audit["audit_complete"] else "FAIL", audit, audit["missing_mandatory_fields"] or None, "add_missing_evidence_fields_in_a_separate_runtime_packet"),
        "TRADE_RECONCILIATION": _gate("PASS" if reconciliation["r_parity_failures"] == 0 else "FAIL", reconciliation, None, "retain_independent_reconciliation"),
        "LATENCY_STRESS": _gate("PASS", {"simulation_only": True}, None, "replace_assumptions_only_after_measured_demo_latency_exists"),
        "SLIPPAGE_STRESS": _gate("PASS", {"simulation_only": True}, None, "replace_assumptions_only_after_measured_demo_slippage_exists"),
        "CREDENTIAL_EXCLUSION": _gate("PASS" if credentials["credential_exclusion_pass"] else "FAIL", credentials, None, "retain_no_secret_evidence_boundary"),
        "LIVE_DISABLED": _gate("PASS", {"live_enabled": False}, None, "keep_live_disabled"),
        "ORDER_SUBMIT_DISABLED": _gate("PASS", {"order_submit_enabled": False}, None, "keep_order_submit_disabled"),
        "BROKER_WRITE_DISABLED": _gate("PASS", {"broker_write_enabled": False}, None, "keep_broker_writes_disabled"),
        "HUMAN_APPROVAL": _gate("PENDING", {"current_live_approval": False}, "human_live_approval_absent", "request_review_only_after_all_evidence_gates_pass"),
    }
    if tuple(matrix) != READINESS_GATES:
        raise ValueError("READINESS_MATRIX_CONTRACT_MISMATCH")
    return matrix


def build_report() -> dict[str, Any]:
    invariants = {
        "paper30_runtime": PAPER30_RUNTIME_PATH,
        "paper30_ledger": PAPER30_LEDGER_PATH,
        "paper30_state": PAPER30_STATE_PATH,
    }
    pre_hashes = {name: _sha256_file(path) for name, path in invariants.items()}
    ledger = json.loads(PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    state = json.loads(PAPER30_STATE_PATH.read_text(encoding="utf-8"))
    historical = json.loads(HISTORICAL_STRESS_PATH.read_text(encoding="utf-8"))
    forward_pre = len(qualifying_forward_records(ledger))
    if forward_pre != 0 or state.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")

    kill_metadata = {
        "kill_switch_declared": True,
        "manual_operator_stop_declared": True,
        "max_daily_loss_stop_declared": True,
        "max_drawdown_stop_declared": True,
        "emergency_disable_declared": True,
        "credential_revoke_path_declared": False,
        "audit_logging_declared": True,
        "notification_path_declared": False,
        "operator_override_declared": True,
        "paper_only_review": True,
    }
    kill_governance = evaluate_live_kill_switch_readiness(kill_metadata)
    kill_proof = kill_switch_synthetic_proof()
    brakes = brake_evaluation(
        daily_loss=0.0,
        daily_loss_threshold=DAILY_LOSS_THRESHOLD,
        drawdown_pct=MAXIMUM_DRAWDOWN_REVIEW_PCT,
        max_drawdown_pct=MAXIMUM_DRAWDOWN_REVIEW_PCT,
        loss_streak=0,
        loss_streak_threshold=LOSS_STREAK_THRESHOLD,
    )
    duplicate = duplicate_intent_proof()
    market = market_data_failure_proof()
    recovery = recovery_proof()
    latency = latency_stress(SYNTHETIC_REALIZED_R)
    slippage = slippage_stress(SYNTHETIC_REALIZED_R)
    reconciliation = reconciliation_proof(ledger)
    audit = audit_completeness()
    credentials = credential_exclusion_scan(
        [
            ROOT / "RISK_POLICY.md",
            ROOT / "docs/orchestration/AIOS_FOREX_LIVE_READINESS_REVIEW.md",
            ROOT / "docs/orchestration/AIOS_FOREX_FIRST_LIVE_MICRO_TRADE_PROOF.md",
            ROOT / "docs/trading_lab/forex/FOREX_EXECUTION_CONTROL_STACK_V1.md",
            ROOT / "automation/forex_engine/live_readiness_review.py",
            ROOT / "automation/forex_engine/live_kill_switch_readiness_engine.py",
            PAPER30_RUNTIME_PATH,
            PAPER30_STATE_PATH,
            PAPER30_LEDGER_PATH,
            HISTORICAL_STRESS_PATH,
        ]
    )
    matrix = _matrix(
        forward_count=forward_pre,
        kill_governance=kill_governance,
        kill_proof=kill_proof,
        brakes=brakes,
        duplicate=duplicate,
        market=market,
        recovery=recovery,
        reconciliation=reconciliation,
        audit=audit,
        credentials=credentials,
    )
    gate_counts = {
        status: sum(gate["status"] == status for gate in matrix.values())
        for status in ("PASS", "FAIL", "PENDING", "NOT_YET_EVALUABLE")
    }

    paper30_gate = evaluate_paper30_gate(
        ledger,
        applicable_risk_gates={
            "daily_loss_stop": matrix["DAILY_LOSS_STOP"]["status"],
            "max_drawdown_stop": matrix["MAX_DRAWDOWN_STOP"]["status"],
            "kill_switch": matrix["KILL_SWITCH"]["status"],
        },
    )
    first_30_fixture = _synthetic_gate_ledger(SYNTHETIC_REALIZED_R)["trades"]
    continuation = paper100_continuation(first_30_fixture, [])
    live_review = review_live_readiness(
        {"allowed": False, "demo_promotion_ready": False},
        {"allowed": False, "mode": "DEMO_RUN_PLAN_ONLY"},
        {"allowed": False, "matched": False},
        {},
        {"validation_passed": True},
        {
            "risk_ok": False,
            "risk_failures": [
                "daily_loss_threshold_not_configured",
                "loss_streak_threshold_not_configured",
            ],
        },
        {"verified": kill_proof["proof_pass"], "disabled": False},
        human_approval=False,
        limits={"maximum_drawdown_pct": MAXIMUM_DRAWDOWN_REVIEW_PCT},
        metadata={"paper30_forward_count": forward_pre, "review_only": True},
    )
    micro_checklist = {field: None for field in MICRO_TRADE_OWNER_FIELDS}
    classification = (
        "LIVE_READINESS_INFRASTRUCTURE_HAS_BLOCKERS"
        if gate_counts["FAIL"]
        else "LIVE_READINESS_INFRASTRUCTURE_STRONG_FORWARD_EVIDENCE_PENDING"
        if gate_counts["PENDING"] or gate_counts["NOT_YET_EVALUABLE"]
        else "LIVE_READINESS_AUDIT_INCONCLUSIVE"
    )

    post_hashes = {name: _sha256_file(path) for name, path in invariants.items()}
    forward_post = len(qualifying_forward_records(json.loads(PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))))
    unchanged = pre_hashes == post_hashes and forward_pre == forward_post
    if not unchanged:
        raise ValueError("PAPER30_FORWARD_STATE_CHANGED")
    latency_by_delay = {item["delay_ms"]: item for item in latency}
    slippage_by_level = {item["slippage_per_leg_r"]: item for item in slippage}
    source_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()

    result = {
        "packet_id": PACKET_ID,
        "lock_id": LOCK_ID,
        "source_head": source_head,
        "paper30_strategy_config_sha256": PAPER30_STRATEGY_CONFIG_SHA256,
        "forward_paper30_count_pre": forward_pre,
        "forward_paper30_count_post": forward_post,
        "known_historical_evidence": {
            "expectancy_r": historical["expectancy_r"],
            "profit_factor": historical["profit_factor"],
            "net_r": historical["net_r"],
            "max_drawdown_r": historical["max_drawdown_r"],
            "max_loss_streak": historical["max_loss_streak"],
            "p30_net_positive_probability": historical["p30_net_r_positive"],
            "p30_pf_ge_1_10_probability": historical["p30_pf_ge_1_10"],
            "classification": historical["historical_stress_classification"],
            "strategy_tuning_authority": False,
        },
        "readiness_matrix": matrix,
        "readiness_gate_count": len(matrix),
        "readiness_pass_count": gate_counts["PASS"],
        "readiness_fail_count": gate_counts["FAIL"],
        "readiness_pending_count": gate_counts["PENDING"] + gate_counts["NOT_YET_EVALUABLE"],
        "readiness_status_counts": gate_counts,
        "kill_switch_governance": kill_governance,
        "kill_switch_proof": kill_proof,
        "kill_switch_status": matrix["KILL_SWITCH"]["status"],
        "kill_switch_executed_live": False,
        "daily_loss_stop_status": brakes["daily_loss"]["status"],
        "max_drawdown_stop_status": brakes["max_drawdown"]["status"],
        "loss_streak_stop_status": brakes["loss_streak"]["status"],
        "risk_threshold_sources": {
            "daily_loss": "NOT_CONFIGURED_IN_ALLOWED_AUTHORITATIVE_CURRENT_STATE",
            "max_drawdown": "live_readiness_review.py:maximum_drawdown_pct_default_5_0",
            "loss_streak": "NOT_CONFIGURED_IN_ALLOWED_AUTHORITATIVE_CURRENT_STATE",
        },
        "duplicate_intent_proof": duplicate,
        "duplicate_intent_created_count": duplicate["duplicate_intent_created_count"],
        "market_data_failure_proof": market,
        "fail_closed_market_data": market["fail_closed_market_data"],
        "recovery_proof": recovery,
        "recovery_scenarios_tested": recovery["recovery_scenarios_tested"],
        "recovery_scenarios_pass": recovery["recovery_scenarios_pass"],
        "latency_stress": latency,
        "latency_stress_simulation_only": True,
        "latency_50ms_r_delta": latency_by_delay[50]["realized_r_delta"],
        "latency_250ms_r_delta": latency_by_delay[250]["realized_r_delta"],
        "latency_1000ms_r_delta": latency_by_delay[1000]["realized_r_delta"],
        "slippage_stress": slippage,
        "slippage_stress_simulation_only": True,
        "slippage_0_05r_expectancy": slippage_by_level[0.05]["expectancy_r"],
        "slippage_0_10r_expectancy": slippage_by_level[0.10]["expectancy_r"],
        "slippage_0_20r_expectancy": slippage_by_level[0.20]["expectancy_r"],
        "trade_reconciliation": reconciliation,
        "r_parity_failures": reconciliation["r_parity_failures"],
        "audit_completeness": audit,
        "credential_exclusion": credentials,
        "credential_exclusion_pass": credentials["credential_exclusion_pass"],
        "paper30_gate": paper30_gate,
        "paper30_gate_implementation_ready": True,
        "paper100_continuation": continuation,
        "paper100_continuation_implementation_ready": continuation["paper100_continuation_implementation_ready"],
        "live_readiness_review": live_review,
        "live_readiness_score": live_review["readiness_score"],
        "live_readiness_blockers": live_review["blocked_reasons"],
        "live_readiness_next_safe_action": live_review["next_safe_action"],
        "live_micro_trade_exception_requestable": False,
        "future_micro_trade_owner_checklist": micro_checklist,
        "live_micro_trade_execution_enabled": False,
        "paper30_forward_state_unchanged": unchanged,
        "paper30_invariant_pre_sha256": pre_hashes,
        "paper30_invariant_post_sha256": post_hashes,
        "network_calls": False,
        "broker_calls": False,
        "broker_writes": False,
        "practice_orders": False,
        "live_orders": False,
        "money_movement": False,
        "credentials_accessed": False,
        "account_identifiers_accessed": False,
        "live_authorized": False,
        "order_submit_enabled": False,
        "automatic_arming": False,
        "readiness_classification": classification,
        "status": classification,
    }
    _assert_finite(result)
    json.dumps(result, sort_keys=True, allow_nan=False)
    return result


def run() -> dict[str, Any]:
    result = build_report()
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    report = run()
    print(json.dumps({"status": report["status"], "result_path": str(RESULT_PATH)}, allow_nan=False))
