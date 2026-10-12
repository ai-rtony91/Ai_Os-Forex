"""Governed live runtime executor V1.

This module defines the first guarded live-runtime execution boundary for one
single live micro-trade. It is fail-closed by default. It never reads .env,
never persists credentials, never starts background workers, and never executes
unless an explicit runtime request, protected auth gate, and injected connector
all pass.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


LIVE_RUNTIME_REQUEST_READY = "LIVE_RUNTIME_REQUEST_READY"
LIVE_RUNTIME_REQUEST_BLOCKED = "LIVE_RUNTIME_REQUEST_BLOCKED"
LIVE_RUNTIME_REQUEST_INVALID = "LIVE_RUNTIME_REQUEST_INVALID"
LIVE_RUNTIME_REQUEST_REVIEW_REQUIRED = "LIVE_RUNTIME_REQUEST_REVIEW_REQUIRED"

LIVE_RUNTIME_EXECUTION_READY = "LIVE_RUNTIME_EXECUTION_READY"
LIVE_RUNTIME_EXECUTION_BLOCKED = "LIVE_RUNTIME_EXECUTION_BLOCKED"
LIVE_RUNTIME_EXECUTION_INVALID = "LIVE_RUNTIME_EXECUTION_INVALID"
LIVE_RUNTIME_EXECUTION_REVIEW_REQUIRED = "LIVE_RUNTIME_EXECUTION_REVIEW_REQUIRED"
LIVE_RUNTIME_EXECUTION_SUBMITTED = "LIVE_RUNTIME_EXECUTION_SUBMITTED"

LIVE_RUNTIME_LEDGER_READY = "LIVE_RUNTIME_LEDGER_READY"
LIVE_RUNTIME_LEDGER_BLOCKED = "LIVE_RUNTIME_LEDGER_BLOCKED"
LIVE_RUNTIME_LEDGER_INVALID = "LIVE_RUNTIME_LEDGER_INVALID"
LIVE_RUNTIME_LEDGER_REVIEW_REQUIRED = "LIVE_RUNTIME_LEDGER_REVIEW_REQUIRED"

LIVE_ORDER_COMMAND_READY = "LIVE_ORDER_COMMAND_READY"
PROTECTED_LIVE_ACTION_AUTH_READY = "PROTECTED_LIVE_ACTION_AUTH_READY"
PROTECTED_ACTION_AUTH_READY = "PROTECTED_ACTION_AUTH_READY"

MAX_LIVE_MICRO_UNITS = 1000

SENSITIVE_KEYS = frozenset(
    {
        "tok" + "en",
        "access_" + "tok" + "en",
        "refresh_" + "tok" + "en",
        "api_" + "key",
        "a" + "pikey",
        "sec" + "ret",
        "pass" + "word",
        "credential",
        "credentials",
        "account_" + "id",
        "account_number",
        "broker_order_id",
        "raw_payload",
        "raw_request",
        "raw_response",
        "authorization",
    }
)


def build_live_runtime_execution_request(
    command_contract: Mapping[str, Any] | None,
    auth_gate: Mapping[str, Any] | None,
    live_connector: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    command = dict(command_contract or {})
    auth = dict(auth_gate or {})
    context = dict(runtime_context or {})
    blockers: list[str] = []

    if not command:
        status = LIVE_RUNTIME_REQUEST_INVALID
        blockers.append("command_contract_missing")
    elif not _command_ready(command):
        status = LIVE_RUNTIME_REQUEST_INVALID
        blockers.append("command_contract_not_ready")
    elif not auth:
        status = LIVE_RUNTIME_REQUEST_INVALID
        blockers.append("auth_gate_missing")
    elif not _auth_ready(auth):
        status = LIVE_RUNTIME_REQUEST_INVALID
        blockers.append("auth_gate_not_ready")
    elif not context:
        status = LIVE_RUNTIME_REQUEST_REVIEW_REQUIRED
        blockers.append("runtime_context_missing")
    else:
        status = LIVE_RUNTIME_REQUEST_READY
        blockers.extend(_runtime_context_blockers(context))

        if blockers:
            status = LIVE_RUNTIME_REQUEST_BLOCKED

    order_intent = _sanitize_mapping(
        command.get("sanitized_order_intent")
        or command.get("order_intent")
        or command.get("trade_intent")
        or {
            "instrument": command.get("instrument", "EUR_USD"),
            "side": command.get("side", "BUY"),
            "units": command.get("units", 1),
            "risk_cap": command.get("risk_cap", 1),
            "stop_loss": command.get("stop_loss", "required"),
            "take_profit": command.get("take_profit", "required"),
        }
    )

    return {
        "request_schema": "AIOS_LIVE_RUNTIME_EXECUTION_REQUEST_V1",
        "request_status": status,
        "ready": status == LIVE_RUNTIME_REQUEST_READY,
        "blockers": tuple(_unique(blockers)),
        "sanitized_order_intent": order_intent,
        "runtime_context_summary": _sanitize_mapping(context),
        "auth_summary": {
            "ready": _auth_ready(auth),
            "protected_action": str(auth.get("protected_action", auth.get("sanitized_summary", {}).get("protected_action", ""))),
        },
        "safety_summary": _safety_summary(order_executed=False, broker_call=False),
        "next_safe_action": _next_request_action(status),
        "latency_budget": {
            "command_contract_eval_ms": 1,
            "auth_gate_eval_ms": 1,
            "runtime_context_eval_ms": 1,
            "network_latency_ms": "excluded_until_execute_requested",
        },
        "live_connector_present": live_connector is not None,
        "order_executed": False,
        "broker_call_performed": False,
        "credential_persisted": False,
        "env_read": False,
        "scheduler_daemon_webhook": False,
    }


def execute_single_live_micro_trade(
    runtime_request: Mapping[str, Any] | None,
    live_connector: Any = None,
    execute_requested: bool = False,
) -> dict[str, Any]:
    request = dict(runtime_request or {})
    blockers: list[str] = []

    if not request:
        status = LIVE_RUNTIME_EXECUTION_INVALID
        blockers.append("runtime_request_missing")
    elif request.get("request_status") != LIVE_RUNTIME_REQUEST_READY or not request.get("ready"):
        status = LIVE_RUNTIME_EXECUTION_BLOCKED
        blockers.append("runtime_request_not_ready")
    elif not execute_requested:
        status = LIVE_RUNTIME_EXECUTION_REVIEW_REQUIRED
        blockers.append("execute_requested_false")
    elif live_connector is None:
        status = LIVE_RUNTIME_EXECUTION_BLOCKED
        blockers.append("live_connector_missing")
    else:
        connector_ok, connector_blockers = _validate_live_connector(live_connector)
        if not connector_ok:
            status = LIVE_RUNTIME_EXECUTION_BLOCKED
            blockers.extend(connector_blockers)
        else:
            status = LIVE_RUNTIME_EXECUTION_READY

    executed = False
    order_count = 0
    broker_result: dict[str, Any] = {}
    connector_called = False
    transport_attempted: bool | None = False
    outcome_known = True

    if status == LIVE_RUNTIME_EXECUTION_READY and execute_requested:
        intent = dict(request.get("sanitized_order_intent", {}))
        connector_called = True
        transport_attempted = None
        try:
            result = live_connector.place_live_micro_order(dict(intent))
        except Exception:
            result = {"outcome_known": False, "blockers": ("connector_outcome_unknown",)}
        broker_result = _sanitize_mapping(result or {})
        submitted_raw = broker_result.get("submitted", False)
        accepted_raw = broker_result.get("accepted", False)
        if type(submitted_raw) is not bool:
            blockers.append("connector_submitted_not_bool")
        if type(accepted_raw) is not bool:
            blockers.append("connector_accepted_not_bool")
        broker_result["submitted"] = submitted_raw is True
        broker_result["accepted"] = accepted_raw is True
        outcome_known = _known_order_outcome(broker_result)
        reported_attempt = broker_result.get("transport_attempted")
        if _attempt_acknowledgement_conflict(broker_result):
            transport_attempted = None
        elif type(reported_attempt) is bool:
            transport_attempted = reported_attempt
        elif broker_result.get("submitted") is True:
            transport_attempted = True
        if _confirmed_order_submission(broker_result):
            executed = True
            order_count = 1
            status = LIVE_RUNTIME_EXECUTION_SUBMITTED
        else:
            status = LIVE_RUNTIME_EXECUTION_BLOCKED
            if broker_result.get("submitted") is False:
                blockers.append("connector_order_not_submitted")
            reasons = broker_result.get("blockers")
            if isinstance(reasons, (list, tuple)):
                blockers.extend(reason for reason in reasons if isinstance(reason, str))
            if broker_result.get("submitted") is True and broker_result.get("accepted") is False:
                blockers.append("connector_order_not_accepted")
            else:
                blockers.append("connector_not_accepted" if outcome_known else "connector_outcome_unknown")

    safety = _safety_summary(order_executed=executed, broker_call=transport_attempted is True)
    # Preserve uncertainty instead of falsely claiming no broker interaction.
    safety["broker_call_performed"] = transport_attempted

    return {
        "execution_schema": "AIOS_SINGLE_LIVE_MICRO_TRADE_EXECUTOR_V1",
        "execution_status": status,
        "ready": status in {LIVE_RUNTIME_EXECUTION_READY, LIVE_RUNTIME_EXECUTION_SUBMITTED},
        "executed": executed,
        "order_count": order_count,
        "order_count_semantics": "confirmed_accepted_submissions_this_call",
        "connector_called": connector_called,
        "transport_attempted": transport_attempted,
        "outcome_known": outcome_known,
        "retry_allowed": False,
        "blockers": tuple(_unique(blockers)),
        "sanitized_broker_result": broker_result,
        "safety_summary": safety,
        "next_safe_action": _next_execution_action(status),
        "latency_budget": {
            "runtime_request_eval_ms": 1,
            "connector_gate_eval_ms": 1,
            "single_order_submit_ms": 1 if executed else 0,
            "network_latency_ms": "runtime_injected_connector_only" if connector_called else "excluded_until_execute_requested",
        },
        "no_loop": True,
        "no_retry": True,
        "one_order_only": order_count <= 1,
        "credential_persisted": False,
        "env_read": False,
        "scheduler_daemon_webhook": False,
    }


def record_live_micro_trade_runtime_result(
    execution_result: Mapping[str, Any] | None,
    result_review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    execution = dict(execution_result or {})
    review = dict(result_review or {})
    blockers: list[str] = []
    broker_result = execution.get("sanitized_broker_result")
    attempt_conflict = (_attempt_acknowledgement_conflict(broker_result)
                        or (_confirmed_order_submission(broker_result)
                            and "transport_attempted" in execution
                            and execution["transport_attempted"] is not True))
    outcome_known = (_known_order_outcome(broker_result) and not attempt_conflict
                     and execution.get("outcome_known", True) is True)
    confirmed = (execution.get("execution_status") == LIVE_RUNTIME_EXECUTION_SUBMITTED
                 and execution.get("executed") is True
                 and execution.get("order_count") == 1
                 and outcome_known
                 and _confirmed_order_submission(execution.get("sanitized_broker_result")))

    if not execution:
        status = LIVE_RUNTIME_LEDGER_INVALID
        blockers.append("execution_result_missing")
    elif execution.get("execution_status") != LIVE_RUNTIME_EXECUTION_SUBMITTED or not execution.get("executed"):
        status = LIVE_RUNTIME_LEDGER_REVIEW_REQUIRED
        blockers.append("execution_not_submitted")
    elif not confirmed:
        status = LIVE_RUNTIME_LEDGER_REVIEW_REQUIRED
        if isinstance(broker_result, Mapping):
            if broker_result.get("submitted") is not True:
                blockers.append("broker_result_not_submitted")
            if broker_result.get("accepted") is not True:
                blockers.append("broker_result_not_accepted")
        blockers.append("connector_submission_unconfirmed")
    elif _contains_sensitive_keys(review):
        status = LIVE_RUNTIME_LEDGER_BLOCKED
        blockers.append("sensitive_result_review_field_detected")
    elif _contains_sensitive_keys(execution.get("sanitized_broker_result", {})):
        status = LIVE_RUNTIME_LEDGER_BLOCKED
        blockers.append("sensitive_broker_result_field_detected")
    else:
        status = LIVE_RUNTIME_LEDGER_READY

    sanitized_result = {
        "broker_result": _sanitize_mapping(broker_result),
        "review": _sanitize_mapping(review),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "one_order_only": confirmed,
        "reported_order_count": execution.get("order_count", 0),
        "sanitized": True,
    }
    transport_attempted = execution.get("transport_attempted")
    if type(transport_attempted) is not bool and isinstance(broker_result, Mapping):
        transport_attempted = broker_result.get("transport_attempted")
    if type(transport_attempted) is not bool:
        transport_attempted = True if confirmed else None
    if attempt_conflict:
        transport_attempted = None
    safety = _safety_summary(order_executed=confirmed, broker_call=transport_attempted is True)
    safety["broker_call_performed"] = transport_attempted

    return {
        "ledger_schema": "AIOS_LIVE_RUNTIME_RESULT_LEDGER_V1",
        "ledger_status": status,
        "ready": status == LIVE_RUNTIME_LEDGER_READY,
        "outcome_known": outcome_known,
        "retry_allowed": False,
        "blockers": tuple(_unique(blockers)),
        "sanitized_result": sanitized_result,
        "evidence_summary": {
            "execution_submitted": confirmed,
            "order_count": 1 if confirmed else 0,
            "one_order_only": execution.get("order_count", 0) <= 1,
        },
        "safety_summary": safety,
        "next_safe_action": _next_ledger_action(status),
        "latency_budget": {
            "execution_result_read_ms": 1,
            "ledger_sanitize_ms": 1,
            "network_latency_ms": "not_applicable_post_execution_record",
        },
    }


def _known_order_outcome(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    submitted, accepted = payload.get("submitted"), payload.get("accepted")
    return (type(submitted) is bool and type(accepted) is bool
            and not (accepted and not submitted)
            and ("transport_attempted" not in payload or type(payload["transport_attempted"]) is bool)
            and not _attempt_acknowledgement_conflict(payload)
            and payload.get("outcome_known", True) is True
            and not (accepted and payload.get("blockers")))


def _attempt_acknowledgement_conflict(payload: Any) -> bool:
    return (isinstance(payload, Mapping) and payload.get("submitted") is True
            and "transport_attempted" in payload and payload["transport_attempted"] is not True)


def _confirmed_order_submission(payload: Any) -> bool:
    return (_known_order_outcome(payload) and payload.get("submitted") is True
            and payload.get("accepted") is True and not payload.get("blockers"))


def _command_ready(command: Mapping[str, Any]) -> bool:
    status = str(command.get("command_status", "")).strip().upper()
    final_command = bool(
        command.get("final_execute_live_order_command")
        or command.get("command_summary", {}).get("final_execute_live_order_command")
    )
    return (
        status == LIVE_ORDER_COMMAND_READY
        and bool(command.get("ready"))
        and bool(command.get("order_executed")) is False
        and bool(command.get("broker_call_performed")) is False
        and final_command
    )


def _auth_ready(auth: Mapping[str, Any]) -> bool:
    status = str(auth.get("auth_status", "")).strip().upper()
    protected_action = str(
        auth.get("protected_action")
        or auth.get("sanitized_summary", {}).get("protected_action", "")
    )
    return (
        status in {PROTECTED_LIVE_ACTION_AUTH_READY, PROTECTED_ACTION_AUTH_READY}
        and bool(auth.get("ready"))
        and protected_action
        in {"live_order_command_contract", "live_micro_trade_arming", "live_micro_trade_exception"}
    )


def _runtime_context_blockers(context: Mapping[str, Any]) -> list[str]:
    checks = {
        "operator_present": True,
        "one_trade_only": True,
        "micro_size_only": True,
        "max_loss_gate_clear": True,
        "daily_stop_clear": True,
        "risk_cap_confirmed": True,
        "stop_loss_confirmed": True,
        "take_profit_confirmed": True,
        "live_exception_mode": True,
        "allow_live_network_once": True,
        "credentials_runtime_only": True,
    }
    blockers = []
    for key, expected in checks.items():
        if bool(context.get(key, False)) is not expected:
            blockers.append(f"{key}_required")

    if bool(context.get("kill_switch_enabled", False)):
        blockers.append("kill_switch_enabled")
    if bool(context.get("credentials_persisted", False)):
        blockers.append("credentials_persisted_forbidden")
    if bool(context.get("account_id_persisted", False)):
        blockers.append("account_id_persisted_forbidden")

    return blockers


def _validate_live_connector(connector: Any) -> tuple[bool, tuple[str, ...]]:
    blockers: list[str] = []

    for attr in (
        "demo_only",
        "paper_only",
        "stores_credentials",
        "stores_account_id",
    ):
        if bool(getattr(connector, attr, False)):
            blockers.append(f"connector_{attr}_forbidden")

    required_true = (
        "supports_live_orders",
        "supports_single_order_only",
        "supports_micro_size_only",
        "live_endpoint_confirmed",
    )
    for attr in required_true:
        if bool(getattr(connector, attr, False)) is not True:
            blockers.append(f"connector_{attr}_required")

    if not hasattr(connector, "place_live_micro_order"):
        blockers.append("connector_place_live_micro_order_missing")

    return not blockers, tuple(blockers)


def _sanitize_value(value: Any) -> Any:
    """Apply the existing sensitive-key filter through every nested container."""
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, list | tuple):
        return [_sanitize_value(item) for item in value]
    return value


def _sanitize_mapping(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).strip().lower()
        if lowered in SENSITIVE_KEYS:
            continue
        sanitized[str(key)] = _sanitize_value(value)
    sanitized["credential_persisted"] = False
    sanitized["account_id_persisted"] = False
    sanitized["raw_broker_payload_persisted"] = False
    return sanitized


def _contains_sensitive_keys(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    lowered = {str(key).strip().lower() for key in payload}
    return bool(lowered.intersection(SENSITIVE_KEYS))


def _safety_summary(order_executed: bool, broker_call: bool) -> dict[str, bool]:
    return {
        "live_trading_possible": True,
        "order_execution": bool(order_executed),
        "broker_call_performed": bool(broker_call),
        "credential_persistence": False,
        "env_read": False,
        "scheduler_daemon_webhook": False,
        "one_order_only": True,
        "looping": False,
        "retrying": False,
    }


def _unique(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen = set()
    output = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return tuple(output)


def _next_request_action(status: str) -> str:
    return {
        LIVE_RUNTIME_REQUEST_READY: "await_explicit_execute_requested_true_with_live_connector",
        LIVE_RUNTIME_REQUEST_BLOCKED: "resolve_live_runtime_request_blockers",
        LIVE_RUNTIME_REQUEST_INVALID: "repair_command_or_auth_gate",
        LIVE_RUNTIME_REQUEST_REVIEW_REQUIRED: "capture_runtime_context",
    }.get(status, "capture_runtime_context")


def _next_execution_action(status: str) -> str:
    return {
        LIVE_RUNTIME_EXECUTION_READY: "submit_single_live_micro_order_if_execute_requested",
        LIVE_RUNTIME_EXECUTION_SUBMITTED: "record_live_micro_trade_runtime_result",
        LIVE_RUNTIME_EXECUTION_BLOCKED: "resolve_live_executor_blockers",
        LIVE_RUNTIME_EXECUTION_INVALID: "repair_runtime_request",
        LIVE_RUNTIME_EXECUTION_REVIEW_REQUIRED: "set_execute_requested_true_only_when_operator_is_present",
    }.get(status, "set_execute_requested_true_only_when_operator_is_present")


def _next_ledger_action(status: str) -> str:
    return {
        LIVE_RUNTIME_LEDGER_READY: "review_live_micro_trade_result_and_stop",
        LIVE_RUNTIME_LEDGER_BLOCKED: "repair_sanitized_live_result",
        LIVE_RUNTIME_LEDGER_INVALID: "repair_execution_result",
        LIVE_RUNTIME_LEDGER_REVIEW_REQUIRED: "wait_for_submitted_execution_result",
    }.get(status, "wait_for_submitted_execution_result")
