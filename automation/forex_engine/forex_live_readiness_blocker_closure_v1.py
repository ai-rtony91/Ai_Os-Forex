"""Close only provable non-forward live-readiness blockers.

This audit is deliberately evidence-only.  It cannot call a broker, read
credentials, submit orders, authorize live trading, or modify PAPER30 state.
Unknown risk authority remains fail-closed and explicitly queued for an owner
or governance decision.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine import forex_live_readiness_hardening_v1 as hardening  # noqa: E402
from automation.forex_engine.demo_reconciliation import reconcile_demo_snapshot  # noqa: E402
from automation.forex_engine.live_kill_switch_readiness_engine import (  # noqa: E402
    evaluate_live_kill_switch_readiness,
)
from automation.forex_engine.live_readiness_review import review_live_readiness  # noqa: E402


PACKET_ID = "PKT-EAST-FOREX-LIVE-READINESS-BLOCKER-CLOSURE-018A"
LOCK_ID = "LOCK_EAST_FOREX_LIVE_READINESS_RESEARCH_EAST_OCC_01"
RECONCILIATION_UNSAFE_CONTENT = "RECONCILIATION_UNSAFE_CONTENT"
PAPER30_STRATEGY_CONFIG_SHA256 = hardening.PAPER30_STRATEGY_CONFIG_SHA256
PACKET017_RESULT_PATH = hardening.RESULT_PATH
PAPER30_RUNTIME_PATH = hardening.PAPER30_RUNTIME_PATH
PAPER30_LEDGER_PATH = hardening.PAPER30_LEDGER_PATH
PAPER30_STATE_PATH = hardening.PAPER30_STATE_PATH
RESULT_PATH = (
    ROOT
    / "Reports/forex_delivery/AIOS_FOREX_LIVE_READINESS_BLOCKER_CLOSURE_V1_RESULTS.json"
)

CLASS_CLOSEABLE = "CLOSEABLE_NOW"
CLASS_FORWARD = "FORWARD_EVIDENCE_DEPENDENT"
CLASS_HUMAN = "HUMAN_APPROVAL_DEPENDENT"
CLASS_CONFIG = "AUTHORITY_CONFIGURATION_DEPENDENT"
CLASS_UNKNOWN = "UNKNOWN"

NON_PASS_CLASSIFICATION = {
    "PAPER_EVIDENCE": CLASS_FORWARD,
    "FORWARD_SAMPLE_SIZE": CLASS_FORWARD,
    "EXPECTANCY": CLASS_FORWARD,
    "PROFIT_FACTOR": CLASS_FORWARD,
    "NET_R": CLASS_FORWARD,
    "DRAWDOWN": CLASS_FORWARD,
    "LOSS_STREAK": CLASS_FORWARD,
    "KILL_SWITCH": CLASS_CONFIG,
    "DAILY_LOSS_STOP": CLASS_CONFIG,
    "AUDIT_LEDGER": CLASS_CLOSEABLE,
    "HUMAN_APPROVAL": CLASS_HUMAN,
}

REQUIRED_PROJECTED_LEDGER_FIELDS = (
    "market_data_freshness",
    "shadow_5r_outcomes",
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
    "r_parity_status",
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NONFINITE_BLOCKER_CLOSURE_RESULT")
    if isinstance(value, Mapping):
        for nested in value.values():
            _assert_finite(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_finite(nested)


def load_packet017_result(path: Path = PACKET017_RESULT_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("packet_id") != hardening.PACKET_ID:
        raise ValueError("READINESS_GATE_RECONCILIATION_FAILED")
    if payload.get("readiness_gate_count") != 27:
        raise ValueError("READINESS_GATE_RECONCILIATION_FAILED")
    return payload


def inventory_readiness_gates(previous: Mapping[str, Any]) -> dict[str, Any]:
    matrix = previous.get("readiness_matrix")
    if not isinstance(matrix, Mapping):
        raise ValueError("READINESS_GATE_RECONCILIATION_FAILED")
    if set(matrix) != set(hardening.READINESS_GATES) or len(matrix) != 27:
        raise ValueError("READINESS_GATE_RECONCILIATION_FAILED")

    status_counts = {
        status: sum(gate.get("status") == status for gate in matrix.values())
        for status in ("PASS", "FAIL", "PENDING", "NOT_YET_EVALUABLE")
    }
    if sum(status_counts.values()) != 27:
        raise ValueError("READINESS_GATE_RECONCILIATION_FAILED")

    gates: dict[str, Any] = {}
    classification_counts = {
        CLASS_CLOSEABLE: 0,
        CLASS_FORWARD: 0,
        CLASS_HUMAN: 0,
        CLASS_CONFIG: 0,
        CLASS_UNKNOWN: 0,
    }
    for name in hardening.READINESS_GATES:
        gate = matrix[name]
        status = gate.get("status")
        if status == "PASS":
            classification = None
        else:
            classification = NON_PASS_CLASSIFICATION.get(name, CLASS_UNKNOWN)
            classification_counts[classification] += 1
        gates[name] = {
            "status": status,
            "classification": classification,
            "blocker": copy.deepcopy(gate.get("blocker")),
            "evidence_provenance": f"{PACKET017_RESULT_PATH.relative_to(ROOT).as_posix()}#/readiness_matrix/{name}",
        }
    return {
        "gates": gates,
        "status_counts": status_counts,
        "classification_counts": classification_counts,
        "all_27_gates_accounted_for": len(gates) == 27,
    }


def resolve_daily_loss_limit(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    accepted = []
    reviewed = []
    for candidate in candidates:
        item = dict(candidate)
        value = item.get("value")
        valid_number = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) > 0
        )
        is_authoritative = item.get("authoritative") is True
        is_configured = item.get("configured") is True
        if valid_number and is_authoritative and is_configured and item.get("unit"):
            accepted.append(item)
            disposition = "ACCEPTED"
        else:
            disposition = str(item.get("rejection_reason") or "NOT_ACTIVE_AUTHORITATIVE_CONFIGURATION")
        reviewed.append({**item, "disposition": disposition})
    if len(accepted) > 1:
        distinct = {(float(item["value"]), str(item["unit"])) for item in accepted}
        if len(distinct) > 1:
            raise ValueError("RISK_AUTHORITY_CONFLICT")
    if accepted:
        selected = accepted[0]
        return {
            "daily_loss_limit_found": True,
            "daily_loss_limit_source": selected["source"],
            "daily_loss_limit_unit": selected["unit"],
            "daily_loss_limit_value": float(selected["value"]),
            "daily_loss_owner_decision_required": False,
            "candidates_reviewed": reviewed,
        }
    return {
        "daily_loss_limit_found": False,
        "daily_loss_limit_source": None,
        "daily_loss_limit_unit": None,
        "daily_loss_limit_value": None,
        "daily_loss_owner_decision_required": True,
        "candidates_reviewed": reviewed,
    }


def current_daily_loss_authority() -> dict[str, Any]:
    """Classify every numeric-looking allowed candidate without promoting samples."""

    return resolve_daily_loss_limit(
        [
            {
                "source": "automation/forex_engine/demo_trade_risk_gate_v1.py:build_sample_valid_risk_input",
                "value": 250.0,
                "unit": "USD",
                "authoritative": False,
                "configured": False,
                "rejection_reason": "SAMPLE_FIXTURE_NOT_OPERATIONAL_CONFIGURATION",
            },
            {
                "source": "automation/forex_engine/forex_basket_risk_exposure_governor_v1.py",
                "value": 0.03,
                "unit": "ACCOUNT_FRACTION",
                "authoritative": True,
                "configured": False,
                "rejection_reason": "POLICY_CEILING_REQUIRES_CALLER_SUPPLIED_LIMIT",
            },
            {
                "source": "automation/forex_engine/forex_daily_profit_execution_evidence_v1.py",
                "value": 0.03,
                "unit": "ACCOUNT_FRACTION",
                "authoritative": True,
                "configured": False,
                "rejection_reason": "VALIDATION_CEILING_REQUIRES_CALLER_SUPPLIED_LIMIT",
            },
            {
                "source": "RISK_POLICY.md:Single Live Micro-Trade Exception",
                "value": None,
                "unit": None,
                "authoritative": True,
                "configured": False,
                "rejection_reason": "DAILY_CAP_REQUIRED_BUT_NUMERIC_VALUE_NOT_DEFINED",
            },
        ]
    )


def kill_switch_authority_recovery() -> dict[str, Any]:
    """Report only explicit authority; tests and declarations-to-be are not authority."""

    return {
        "credential_revoke_path_authority_found": False,
        "credential_revoke_path_source": None,
        "notification_path_authority_found": False,
        "notification_path_source": None,
        "sources_reviewed": [
            "RISK_POLICY.md",
            "docs/orchestration/AIOS_FOREX_LIVE_READINESS_REVIEW.md",
            "docs/orchestration/AIOS_FOREX_FIRST_LIVE_MICRO_TRADE_PROOF.md",
            "docs/trading_lab/forex/FOREX_EXECUTION_CONTROL_STACK_V1.md",
            "docs/orchestration/AIOS_FOREX_RISK_GOVERNOR.md",
            "Reports/forex_delivery/AIOS_FOREX_LIVE_KILL_SWITCH_READINESS_ENGINE_V1_REPORT.md",
        ],
        "excluded_non_authority": [
            "tests/forex_engine/test_live_kill_switch_readiness_engine.py fixture",
            "boolean field names without declared operational paths",
        ],
        "missing_declarations": ["credential_revoke_path", "notification_path"],
    }


def reevaluate_kill_switch(authority: Mapping[str, Any]) -> dict[str, Any]:
    metadata = {
        "kill_switch_declared": True,
        "manual_operator_stop_declared": True,
        "max_daily_loss_stop_declared": True,
        "max_drawdown_stop_declared": True,
        "emergency_disable_declared": True,
        "credential_revoke_path_declared": authority.get(
            "credential_revoke_path_authority_found"
        )
        is True,
        "audit_logging_declared": True,
        "notification_path_declared": authority.get("notification_path_authority_found")
        is True,
        "operator_override_declared": True,
        "paper_only_review": True,
    }
    return evaluate_live_kill_switch_readiness(metadata)


def synthetic_demo_reconciliation_proof(*, stale: bool = False) -> dict[str, Any]:
    snapshot = {
        "allowed": True,
        "decision": "allowed",
        "mode": "DEMO_READONLY",
        "fresh": not stale,
        "prices": [{"instrument": "EUR_USD", "bid": 1.0998, "ask": 1.1002}],
        "positions_summary": [
            {
                "instrument": "EUR_USD",
                "side": "BUY",
                "units": 1000.0,
                "entry_price": 1.1,
                "stop_loss": 1.095,
                "take_profit": 1.11,
            }
        ],
        "orders": [
            {
                "instrument": "EUR_USD",
                "side": "BUY",
                "units": 1000.0,
                "entry_price": 1.1,
                "stop_loss": 1.095,
                "take_profit": 1.11,
            }
        ],
    }
    intent = {
        "pair": "EUR_USD",
        "side": "BUY",
        "units": 1000.0,
        "entry_price": 1.1,
        "stop_loss": 1.095,
        "take_profit": 1.11,
        "mode": "DEMO_MAPPING_ONLY",
        "submit_enabled": False,
        "broker_write_enabled": False,
        "live_trading": False,
    }
    result = reconcile_demo_snapshot(snapshot, intent)
    return {
        "synthetic": True,
        "engine_ready": result["mode"] == "DEMO_RECONCILIATION_ONLY",
        "synthetic_match_pass": result["matched"] is True,
        "stale_rejected": stale and result["allowed"] is False and result["stale_data"] is True,
        "result": result,
        "real_demo_evidence_complete": False,
        "network_calls": False,
        "broker_calls": False,
    }


def _normalized_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _truthy_safety_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on", "enabled"}
    return False


def _nonempty_safety_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _reconciliation_fields(value: Any) -> list[tuple[str, Any]]:
    fields: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            fields.append((_normalized_key(key), nested))
            fields.extend(_reconciliation_fields(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            fields.extend(_reconciliation_fields(nested))
    return fields


def _assert_reconciliation_content_safe(payload: Mapping[str, Any]) -> None:
    """Reject genuine credential, account, routing, or live-execution content.

    False-valued safety declarations are evidence that a capability is disabled;
    they are not evidence that a credential or capability is present.  Non-empty
    sensitive values and enabled execution flags remain fail-closed.
    """

    if not isinstance(payload, Mapping):
        raise ValueError(RECONCILIATION_UNSAFE_CONTENT)

    sensitive_value_tokens = (
        "token",
        "secret",
        "api_key",
        "password",
        "authorization",
        "private_key",
        "access_key",
        "refresh_key",
    )
    unsafe_reason_tokens = {
        "credentials_loaded",
        "credential_loaded",
        "credentials_present",
        "account_id_present",
        "broker_write_enabled",
        "order_submit_enabled",
        "live_trading_enabled",
        "network_submit_enabled",
    }

    for key, value in _reconciliation_fields(payload):
        if "account" in key and "id" in key and _nonempty_safety_value(value):
            raise ValueError(RECONCILIATION_UNSAFE_CONTENT)

        if "credential" in key:
            if _truthy_safety_value(value):
                raise ValueError(RECONCILIATION_UNSAFE_CONTENT)
            if not isinstance(value, bool) and _nonempty_safety_value(value):
                raise ValueError(RECONCILIATION_UNSAFE_CONTENT)

        if any(token in key for token in sensitive_value_tokens) and _nonempty_safety_value(
            value
        ):
            raise ValueError(RECONCILIATION_UNSAFE_CONTENT)

        enabled_semantics = (
            ("broker" in key and "write" in key),
            ("order" in key and "submit" in key),
            ("real" in key and "order" in key),
            ("live" in key and "trading" in key),
            ("network" in key and "submit" in key),
        )
        if any(enabled_semantics) and _truthy_safety_value(value):
            raise ValueError(RECONCILIATION_UNSAFE_CONTENT)

        if key in {"blocked_reason", "blocked_reasons"}:
            values = value if isinstance(value, (list, tuple)) else [value]
            if any(_normalized_key(item) in unsafe_reason_tokens for item in values):
                raise ValueError(RECONCILIATION_UNSAFE_CONTENT)


def minimal_reconciliation_review_view(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return only reconciliation-quality fields after fail-closed inspection."""

    original = copy.deepcopy(payload)
    _assert_reconciliation_content_safe(payload)
    view = {
        "allowed": copy.deepcopy(payload.get("allowed")),
        "matched": copy.deepcopy(payload.get("matched")),
        "match_score": copy.deepcopy(payload.get("match_score")),
        "mode": copy.deepcopy(payload.get("mode")),
    }
    if payload != original:
        raise ValueError(RECONCILIATION_UNSAFE_CONTENT)
    return view


def reconciliation_projection_regression_proof() -> dict[str, bool]:
    """Exercise the boundary without retaining any sensitive fixture value."""

    benign = {
        "allowed": True,
        "matched": True,
        "match_score": 1.0,
        "mode": "DEMO_RECONCILIATION_ONLY",
        "safety": {
            "credentials": False,
            "broker_write": False,
            "live_trading": False,
            "real_orders": False,
            "network_submit": False,
        },
    }
    view = minimal_reconciliation_review_view(benign)

    def rejected(extra: Mapping[str, Any]) -> bool:
        candidate = copy.deepcopy(benign)
        candidate.update(copy.deepcopy(dict(extra)))
        try:
            minimal_reconciliation_review_view(candidate)
        except ValueError as exc:
            return str(exc) == RECONCILIATION_UNSAFE_CONTENT
        return False

    failed = copy.deepcopy(benign)
    failed.update({"allowed": False, "matched": False, "match_score": 0.0})
    failed_view = minimal_reconciliation_review_view(failed)
    return {
        "credentials_false_regression_pass": view == {
            "allowed": True,
            "matched": True,
            "match_score": 1.0,
            "mode": "DEMO_RECONCILIATION_ONLY",
        },
        "credentials_true_fail_closed_pass": rejected({"credentials": True}),
        "credential_value_fail_closed_pass": rejected(
            {"credential_marker": "SANITIZED_PRESENT_MARKER"}
        ),
        "account_id_fail_closed_pass": rejected(
            {"account_id": "SANITIZED_PRESENT_MARKER"}
        ),
        "broker_write_fail_closed_pass": rejected({"broker_write": True}),
        "order_submit_fail_closed_pass": rejected({"order_submit": True}),
        "live_trading_fail_closed_pass": rejected({"live_trading": True}),
        "network_submit_fail_closed_pass": rejected({"network_submit": True}),
        "failed_reconciliation_preserved": failed_view == {
            "allowed": False,
            "matched": False,
            "match_score": 0.0,
            "mode": "DEMO_RECONCILIATION_ONLY",
        },
    }


def ledger_schema_projection(previous: Mapping[str, Any]) -> dict[str, Any]:
    audit = previous.get("audit_completeness")
    if not isinstance(audit, Mapping):
        raise ValueError("READINESS_GATE_RECONCILIATION_FAILED")
    runtime_source = PAPER30_RUNTIME_PATH.read_text(encoding="utf-8")
    aliases = dict(audit.get("runtime_ledger_field_aliases", {}))
    projected_sources = {
        **{name: {"source": source, "type": "CURRENT_TRADE_FIELD"} for name, source in aliases.items()},
        "market_data_freshness": {
            "source": "sentinel/latest_completed_M5_timestamp_and_runtime_freshness_status",
            "type": "FUTURE_EVIDENCE_PROJECTION",
        },
        "shadow_5r_outcomes": {
            "source": "AIOS_FOREX_PAPER30_5R_SHADOW.jsonl joined by trade_id",
            "type": "FUTURE_EVIDENCE_PROJECTION",
        },
    }
    missing = sorted(set(REQUIRED_PROJECTED_LEDGER_FIELDS) - set(projected_sources))
    runtime_support_proven = all(
        marker in runtime_source
        for marker in ("signal_timestamp_utc", "r_parity_valid", "shadow_closed", "shadow_reached")
    )
    ready = not missing and runtime_support_proven
    return {
        "paper30_ledger_schema_extension_ready": ready,
        "projected_schema_fields": projected_sources,
        "required_fields": list(REQUIRED_PROJECTED_LEDGER_FIELDS),
        "projection_missing_fields": missing,
        "current_runtime_missing_fields": list(audit.get("missing_mandatory_fields", [])),
        "current_ledger_already_contains_extension": False,
        "runtime_modified": False,
        "ledger_modified": False,
        "strategy_semantics_changed": False,
        "shadow_5r_authority": "OBSERVATION_ONLY",
    }


def risk_configuration_map(daily: Mapping[str, Any], kill: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "MAX_DRAWDOWN_LIMIT": {
            "value": 5.0,
            "unit": "PERCENT",
            "authority_source": "automation/forex_engine/live_readiness_review.py:_limits",
            "status": "PROVEN",
        },
        "DAILY_LOSS_LIMIT": {
            "value": daily.get("daily_loss_limit_value"),
            "unit": daily.get("daily_loss_limit_unit"),
            "authority_source": daily.get("daily_loss_limit_source"),
            "status": "PROVEN" if daily.get("daily_loss_limit_found") else "MISSING_AUTHORITY",
        },
        "LOSS_STREAK_LIMIT": {
            "value": None,
            "unit": "CONSECUTIVE_LOSSES",
            "authority_source": "automation/forex_engine/risk_management.py references external config without a numeric value in allowed authority",
            "status": "MISSING_AUTHORITY",
        },
        "MAX_CONCURRENT_EXPOSURE": {
            "value": 1,
            "unit": "ACTIVE_POSITION_PER_INSTRUMENT",
            "authority_source": "automation/forex_engine/forex_frozen_candidate_paper30_v1.py:MAX_ACTIVE_POSITIONS_PER_INSTRUMENT",
            "status": "PROVEN",
        },
        "PER_TRADE_RISK_LIMIT": {
            "value": 0.01,
            "unit": "ACCOUNT_FRACTION_POLICY_CEILING",
            "authority_source": "automation/forex_engine/forex_basket_risk_exposure_governor_v1.py",
            "status": "PROVEN",
        },
        "KILL_SWITCH": {
            "value": "FAIL_CLOSED_DECLARATION_GATE",
            "unit": "BOOLEAN_CONTROL_SET",
            "authority_source": "automation/forex_engine/live_kill_switch_readiness_engine.py",
            "status": "PROVEN" if kill.get("kill_switch_ready") else "MISSING_AUTHORITY",
        },
    }


def reevaluate_matrix(
    previous: Mapping[str, Any],
    *,
    projection: Mapping[str, Any],
    demo: Mapping[str, Any],
    kill: Mapping[str, Any],
    daily: Mapping[str, Any],
) -> dict[str, Any]:
    matrix = copy.deepcopy(dict(previous["readiness_matrix"]))
    matrix["AUDIT_LEDGER"] = {
        "status": "PASS" if projection["paper30_ledger_schema_extension_ready"] else "FAIL",
        "evidence": copy.deepcopy(dict(projection)),
        "blocker": None if projection["paper30_ledger_schema_extension_ready"] else "schema_projection_incomplete",
        "next_safe_action": "integrate_projected_fields_only_in_a_separate_owner_approved_runtime_packet",
    }
    matrix["TRADE_RECONCILIATION"] = {
        "status": "PASS" if demo["engine_ready"] and demo["synthetic_match_pass"] else "FAIL",
        "evidence": copy.deepcopy(dict(demo)),
        "blocker": None if demo["synthetic_match_pass"] else "synthetic_reconciliation_failed",
        "next_safe_action": "collect_real_sanitized_demo_reconciliation_evidence_later",
    }
    matrix["KILL_SWITCH"] = {
        "status": "PASS" if kill["kill_switch_ready"] else "PENDING",
        "evidence": copy.deepcopy(dict(kill)),
        "blocker": copy.deepcopy(kill["blocked_reasons"]) or None,
        "next_safe_action": kill["next_safe_action"],
    }
    matrix["DAILY_LOSS_STOP"] = {
        "status": "PASS" if daily["daily_loss_limit_found"] else "PENDING",
        "evidence": copy.deepcopy(dict(daily)),
        "blocker": None if daily["daily_loss_limit_found"] else "authoritative_numeric_daily_loss_threshold_missing",
        "next_safe_action": "owner_define_daily_loss_limit_in_existing_risk_authority",
    }
    if set(matrix) != set(hardening.READINESS_GATES) or len(matrix) != 27:
        raise ValueError("READINESS_GATE_RECONCILIATION_FAILED")
    counts = {
        status: sum(item["status"] == status for item in matrix.values())
        for status in ("PASS", "FAIL", "PENDING", "NOT_YET_EVALUABLE")
    }
    if sum(counts.values()) != 27:
        raise ValueError("READINESS_GATE_RECONCILIATION_FAILED")
    return {"matrix": matrix, "status_counts": counts}


def live_readiness_reevaluation(
    *, demo: Mapping[str, Any], kill: Mapping[str, Any], daily: Mapping[str, Any]
) -> dict[str, Any]:
    reconciliation = minimal_reconciliation_review_view(demo["result"])
    risk_failures = ["loss_streak_threshold_not_configured"]
    if not daily["daily_loss_limit_found"]:
        risk_failures.append("daily_loss_threshold_not_configured")
    if not kill["kill_switch_ready"]:
        risk_failures.append("kill_switch_authority_incomplete")
    return review_live_readiness(
        {"allowed": False, "demo_promotion_ready": False},
        {"allowed": False, "mode": "DEMO_RUN_PLAN_ONLY"},
        reconciliation,
        {},
        {"validation_passed": True},
        {"risk_ok": False, "risk_failures": risk_failures},
        {"verified": hardening.kill_switch_synthetic_proof()["proof_pass"], "disabled": False},
        human_approval=False,
        limits={"maximum_drawdown_pct": 5.0},
        metadata={
            "review_only": True,
            "synthetic_reconciliation_only": True,
            "real_demo_evidence_complete": False,
        },
    )


def next_work_queue() -> list[dict[str, Any]]:
    return [
        {
            "priority": 1,
            "blocker": "SAFETY_CONFIGURATION_AUTHORITY",
            "owner": "Human Owner and existing risk-governance owner",
            "prerequisite": "Define numeric daily-loss and loss-streak limits plus credential-revoke and notification paths in existing authority",
            "can_execute_now": False,
            "requires_market_open": False,
            "requires_forward_trades": False,
            "requires_human_value": True,
        },
        {
            "priority": 2,
            "blocker": "PAPER30_LEDGER_SCHEMA_RUNTIME_INTEGRATION",
            "owner": "Codex East under a separate owner-approved runtime packet",
            "prerequisite": "Adopt the proven market-data freshness and 5R shadow projection without strategy mutation",
            "can_execute_now": False,
            "requires_market_open": False,
            "requires_forward_trades": False,
            "requires_human_value": False,
        },
        {
            "priority": 3,
            "blocker": "REAL_DEMO_EVIDENCE_AND_RECONCILIATION",
            "owner": "Human Owner supervised demo lane",
            "prerequisite": "Owner-approved sanitized demo evidence; synthetic proof is infrastructure only",
            "can_execute_now": False,
            "requires_market_open": True,
            "requires_forward_trades": False,
            "requires_human_value": False,
        },
        {
            "priority": 4,
            "blocker": "GENUINE_FORWARD_PAPER30_EVIDENCE",
            "owner": "PAPER30 forward campaign",
            "prerequisite": "Fresh market and genuine frozen-strategy PAPER trades",
            "can_execute_now": False,
            "requires_market_open": True,
            "requires_forward_trades": True,
            "requires_human_value": False,
        },
        {
            "priority": 5,
            "blocker": "HUMAN_LIVE_APPROVAL",
            "owner": "Human Owner Anthony",
            "prerequisite": "All evidence and safety gates pass before review",
            "can_execute_now": False,
            "requires_market_open": False,
            "requires_forward_trades": True,
            "requires_human_value": True,
        },
        {
            "priority": 6,
            "blocker": "FUTURE_MICRO_LIVE_EXCEPTION_REVIEW",
            "owner": "Human Owner Anthony",
            "prerequisite": "Current RISK_POLICY.md one-shot exception packet with every required field",
            "can_execute_now": False,
            "requires_market_open": True,
            "requires_forward_trades": True,
            "requires_human_value": True,
        },
    ]


def build_report() -> dict[str, Any]:
    invariant_paths = {
        "paper30_runtime": PAPER30_RUNTIME_PATH,
        "paper30_ledger": PAPER30_LEDGER_PATH,
        "paper30_state": PAPER30_STATE_PATH,
    }
    pre_hashes = {name: _sha256_file(path) for name, path in invariant_paths.items()}
    ledger = json.loads(PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    state = json.loads(PAPER30_STATE_PATH.read_text(encoding="utf-8"))
    forward_pre = len(hardening.qualifying_forward_records(ledger))
    if (
        forward_pre != 0
        or state.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256
    ):
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")

    previous = load_packet017_result()
    inventory = inventory_readiness_gates(previous)
    daily = current_daily_loss_authority()
    daily_brake = hardening.brake_evaluation(
        daily_loss=0.0,
        daily_loss_threshold=daily["daily_loss_limit_value"],
        drawdown_pct=0.0,
        max_drawdown_pct=5.0,
        loss_streak=0,
        loss_streak_threshold=None,
    )["daily_loss"]
    kill_authority = kill_switch_authority_recovery()
    kill = reevaluate_kill_switch(kill_authority)
    demo = synthetic_demo_reconciliation_proof()
    stale_demo = synthetic_demo_reconciliation_proof(stale=True)
    projection = ledger_schema_projection(previous)
    risk_map = risk_configuration_map(daily, kill)
    reevaluated = reevaluate_matrix(
        previous, projection=projection, demo=demo, kill=kill, daily=daily
    )
    live_review = live_readiness_reevaluation(demo=demo, kill=kill, daily=daily)
    projection_regression = reconciliation_projection_regression_proof()
    false_credential_blocker = "credentials_present" in live_review["blocked_reasons"]
    if false_credential_blocker or not all(projection_regression.values()):
        raise ValueError("READINESS_BLOCKER_CLOSURE_VALIDATION_FAILED")

    post_hashes = {name: _sha256_file(path) for name, path in invariant_paths.items()}
    ledger_post = json.loads(PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    forward_post = len(hardening.qualifying_forward_records(ledger_post))
    unchanged = pre_hashes == post_hashes and forward_pre == forward_post
    if not unchanged:
        raise ValueError("PAPER30_FORWARD_STATE_CHANGED")

    before_counts = inventory["status_counts"]
    after_counts = reevaluated["status_counts"]
    config_remaining = (
        not daily["daily_loss_limit_found"]
        or not kill["kill_switch_ready"]
        or risk_map["LOSS_STREAK_LIMIT"]["status"] != "PROVEN"
    )
    blockers_reduced = (
        after_counts["PASS"] > before_counts["PASS"]
        and after_counts["FAIL"] < before_counts["FAIL"]
    )
    if config_remaining:
        classification = "LIVE_READINESS_NON_FORWARD_BLOCKERS_REMAIN"
    elif blockers_reduced:
        classification = "LIVE_READINESS_BLOCKERS_REDUCED_FORWARD_EVIDENCE_PENDING"
    else:
        classification = "LIVE_READINESS_BLOCKER_CLOSURE_INCONCLUSIVE"

    classification_counts = inventory["classification_counts"]
    source_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    result = {
        "packet_id": PACKET_ID,
        "lock_id": LOCK_ID,
        "source_head": source_head,
        "paper30_strategy_config_sha256": PAPER30_STRATEGY_CONFIG_SHA256,
        "readiness_gate_inventory": inventory,
        "readiness_gate_count": 27,
        "readiness_pass_count_before": before_counts["PASS"],
        "readiness_pass_count_after": after_counts["PASS"],
        "readiness_fail_count_before": before_counts["FAIL"],
        "readiness_fail_count_after": after_counts["FAIL"],
        "readiness_pending_count_before": before_counts["PENDING"]
        + before_counts["NOT_YET_EVALUABLE"],
        "readiness_pending_count_after": after_counts["PENDING"]
        + after_counts["NOT_YET_EVALUABLE"],
        "closeable_now_count": classification_counts[CLASS_CLOSEABLE],
        "forward_dependent_count": classification_counts[CLASS_FORWARD],
        "human_dependent_count": classification_counts[CLASS_HUMAN],
        "config_dependent_count": classification_counts[CLASS_CONFIG],
        "unknown_classification_count": classification_counts[CLASS_UNKNOWN],
        "daily_loss_authority": daily,
        "daily_loss_limit_found": daily["daily_loss_limit_found"],
        "daily_loss_limit_source": daily["daily_loss_limit_source"],
        "daily_loss_limit_unit": daily["daily_loss_limit_unit"],
        "daily_loss_limit_value": daily["daily_loss_limit_value"],
        "daily_loss_owner_decision_required": daily[
            "daily_loss_owner_decision_required"
        ],
        "daily_loss_stop_status": daily_brake["status"],
        "daily_loss_synthetic_brake": daily_brake,
        "kill_switch_authority_recovery": kill_authority,
        "credential_revoke_path_authority_found": kill_authority[
            "credential_revoke_path_authority_found"
        ],
        "notification_path_authority_found": kill_authority[
            "notification_path_authority_found"
        ],
        "kill_switch_status_before": previous["kill_switch_status"],
        "kill_switch_status_after": "PASS" if kill["kill_switch_ready"] else "PENDING",
        "kill_switch_blockers_after": kill["blocked_reasons"],
        "kill_switch_reevaluation": kill,
        "demo_reconciliation_engine_ready": demo["engine_ready"],
        "demo_reconciliation_synthetic_match_pass": demo["synthetic_match_pass"],
        "demo_reconciliation_stale_rejection_pass": stale_demo["stale_rejected"],
        "demo_evidence_real_complete": False,
        "demo_reconciliation_proof": demo,
        "reconciliation_review_view_sanitized": True,
        "reconciliation_unsafe_content_detected": False,
        "false_credential_blocker_present": false_credential_blocker,
        **projection_regression,
        "paper30_ledger_schema_extension_ready": projection[
            "paper30_ledger_schema_extension_ready"
        ],
        "ledger_schema_projection": projection,
        "risk_configuration_map": risk_map,
        "reevaluated_readiness_matrix": reevaluated["matrix"],
        "live_readiness_score_before": previous["live_readiness_score"],
        "live_readiness_score_after": live_review["readiness_score"],
        "live_readiness_blockers_after": live_review["blocked_reasons"],
        "live_readiness_pass_count_after": after_counts["PASS"],
        "live_readiness_pending_count_after": after_counts["PENDING"]
        + after_counts["NOT_YET_EVALUABLE"],
        "live_readiness_fail_count_after": after_counts["FAIL"],
        "live_readiness_review": live_review,
        "next_work_queue": next_work_queue(),
        "blockers_legitimately_reduced": blockers_reduced,
        "paper30_forward_state_unchanged": unchanged,
        "paper30_invariant_pre_sha256": pre_hashes,
        "paper30_invariant_post_sha256": post_hashes,
        "forward_paper30_count_pre": forward_pre,
        "forward_paper30_count_post": forward_post,
        "historical_forward_trades_credited": 0,
        "human_live_approval": False,
        "live_micro_trade_execution_enabled": False,
        "live_authorized": False,
        "network_calls": False,
        "broker_calls": False,
        "practice_orders": False,
        "live_orders": False,
        "money_movement": False,
        "credentials_accessed": False,
        "account_identifiers_persisted": False,
        "audit_execution_count": 1,
        "authorized_replacement_audit_runs": 1,
        "actual_replacement_audit_runs": 1,
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
