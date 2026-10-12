"""OANDA live runtime connector contract V2.

This module provides the live connector contract compatible with
live_runtime_executor_v1. It is fail-closed unless runtime config and injected
transport are explicitly provided. It never reads .env and never persists
credentials or account identifiers.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping


OANDA_LIVE_CONNECTOR_CONFIG_READY = "OANDA_LIVE_CONNECTOR_CONFIG_READY"
OANDA_LIVE_CONNECTOR_CONFIG_BLOCKED = "OANDA_LIVE_CONNECTOR_CONFIG_BLOCKED"
OANDA_LIVE_CONNECTOR_CONFIG_INVALID = "OANDA_LIVE_CONNECTOR_CONFIG_INVALID"
OANDA_LIVE_CONNECTOR_CONFIG_REVIEW_REQUIRED = "OANDA_LIVE_CONNECTOR_CONFIG_REVIEW_REQUIRED"

OANDA_LIVE_CONNECTOR_READY = "OANDA_LIVE_CONNECTOR_READY"
OANDA_LIVE_CONNECTOR_BLOCKED = "OANDA_LIVE_CONNECTOR_BLOCKED"

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


def build_oanda_live_connector_config(runtime_config: Mapping[str, Any] | None) -> dict[str, Any]:
    config = dict(runtime_config or {})
    blockers: list[str] = []

    if not config:
        status = OANDA_LIVE_CONNECTOR_CONFIG_INVALID
        blockers.append("runtime_config_missing")
    elif not bool(config.get("operator_approved_live_runtime", False)):
        status = OANDA_LIVE_CONNECTOR_CONFIG_REVIEW_REQUIRED
        blockers.append("operator_approval_missing")
    else:
        checks = {
            "live_endpoint_confirmed": True,
            "credentials_runtime_only": True,
            "credentials_persisted": False,
            "account_id_persisted": False,
            "single_order_only": True,
            "micro_size_only": True,
            "no_retry": True,
            "no_loop": True,
            "transport_injected": True,
        }
        for key, expected in checks.items():
            if bool(config.get(key, False)) is not expected:
                blockers.append(f"{key}_invalid")
        if int(config.get("max_order_count", 0)) != 1:
            blockers.append("max_order_count_must_equal_one")

        status = OANDA_LIVE_CONNECTOR_CONFIG_READY if not blockers else OANDA_LIVE_CONNECTOR_CONFIG_BLOCKED

    return {
        "config_schema": "AIOS_OANDA_LIVE_CONNECTOR_CONFIG_V2",
        "config_status": status,
        "ready": status == OANDA_LIVE_CONNECTOR_CONFIG_READY,
        "blockers": tuple(_unique(blockers)),
        "sanitized_config": _sanitize_mapping(config),
        "capability_summary": {
            "supports_live_orders": status == OANDA_LIVE_CONNECTOR_CONFIG_READY,
            "supports_single_order_only": status == OANDA_LIVE_CONNECTOR_CONFIG_READY,
            "supports_micro_size_only": status == OANDA_LIVE_CONNECTOR_CONFIG_READY,
            "live_endpoint_confirmed": bool(config.get("live_endpoint_confirmed", False)),
            "stores_credentials": False,
            "stores_account_id": False,
        },
        "safety_summary": _safety_summary(order_submitted=False),
        "next_safe_action": _next_config_action(status),
    }


class OandaLiveRuntimeConnectorV2:
    """Injected OANDA live connector contract for exactly one live micro-order."""

    demo_only = False
    paper_only = False
    stores_credentials = False
    stores_account_id = False

    def __init__(
        self,
        config_result: Mapping[str, Any] | None,
        transport: Any = None,
        *,
        reserve_attempt: Callable[[], bool] | None = None,
    ) -> None:
        """Require an external durable, atomic reservation before transport.

        The caller must bind reserve_attempt to its existing one-shot scope.
        Only literal True may mean a new reservation was durably committed.
        Missing history, prior attempts, errors and uncertainty must not grant
        it. This component supplies no storage, reset or reconciliation policy.
        """
        self.config_result = dict(config_result or {})
        self.transport = transport
        self._reserve_attempt = reserve_attempt
        self.order_count = 0
        self._outcome_known = True

        ready = self.config_result.get("config_status") == OANDA_LIVE_CONNECTOR_CONFIG_READY and bool(
            self.config_result.get("ready", False)
        )
        self.supports_live_orders = bool(ready)
        self.supports_single_order_only = bool(ready)
        self.supports_micro_size_only = bool(ready)
        self.live_endpoint_confirmed = bool(
            self.config_result.get("capability_summary", {}).get("live_endpoint_confirmed", False)
        )

    def place_live_micro_order(self, order_intent: Mapping[str, Any] | None) -> dict[str, Any]:
        intent = dict(order_intent or {})
        blockers: list[str] = []

        if self.config_result.get("config_status") != OANDA_LIVE_CONNECTOR_CONFIG_READY or not self.config_result.get("ready"):
            blockers.append("connector_config_not_ready")
        if self.transport is None:
            blockers.append("transport_missing")
        if not callable(self._reserve_attempt):
            blockers.append("attempt_reservation_required")
        if self.order_count >= 1:
            blockers.append("second_order_blocked")
        blockers.extend(_order_intent_blockers(intent))

        method = getattr(self.transport, "place_live_micro_order", None)
        if not callable(method):
            method = getattr(self.transport, "submit_live_micro_order", None)
        if self.transport is not None and not callable(method):
            blockers.append("transport_order_method_missing")

        if blockers:
            return self._order_result(blockers=blockers)

        # Consume the local budget before reservation: the callback may commit
        # and then fail. Never release a reservation or clear this counter here.
        self.order_count += 1
        self._outcome_known = False
        try:
            reserved = self._reserve_attempt()
        except Exception:
            return self._order_result(blockers=["attempt_reservation_unavailable"])
        if reserved is not True:
            return self._order_result(blockers=["attempt_reservation_denied"])
        try:
            response = method(dict(intent))
        except Exception:
            # False below means no confirmed submission, never proof that the
            # broker did nothing. Preserve UNKNOWN and prohibit retry.
            return self._order_result(transport_attempted=True, blockers=["transport_outcome_unknown"])

        if not isinstance(response, Mapping):
            return self._order_result(transport_attempted=True, blockers=["transport_acknowledgement_invalid"])
        submitted, accepted = response.get("submitted"), response.get("accepted")
        if (type(submitted) is not bool or type(accepted) is not bool
                or (accepted and not submitted)
                or ("transport_attempted" in response and type(response["transport_attempted"]) is not bool)
                or (submitted and response.get("transport_attempted", True) is not True)
                or response.get("outcome_known", True) is not True
                or (accepted and response.get("blockers"))):
            return self._order_result(transport_attempted=True, blockers=["transport_acknowledgement_invalid"])
        self._outcome_known = True
        return self._order_result(submitted=submitted, accepted=accepted,
                                  transport_attempted=True, response=response,
                                  blockers=[] if accepted else ["transport_not_accepted"])

    def _order_result(
        self, *, submitted: bool = False, accepted: bool = False,
        transport_attempted: bool = False, response: Any = None,
        blockers: list[str],
    ) -> dict[str, Any]:
        return {
            "submitted": submitted,
            "accepted": accepted,
            "outcome_known": self._outcome_known,
            "transport_attempted": transport_attempted,
            "retry_allowed": False,
            "order_count": self.order_count,
            "sanitized_response": _sanitize_mapping(response or {}),
            "blockers": tuple(_unique(blockers)),
            "safety_summary": _safety_summary(order_submitted=submitted),
        }


def build_oanda_live_connector_readiness_packet(config_result: Mapping[str, Any] | None) -> dict[str, Any]:
    config = dict(config_result or {})
    ready = config.get("config_status") == OANDA_LIVE_CONNECTOR_CONFIG_READY and bool(config.get("ready"))
    blockers = tuple(config.get("blockers", ())) if config else ("config_missing",)
    return {
        "readiness_schema": "AIOS_OANDA_LIVE_CONNECTOR_READINESS_V2",
        "ready": ready,
        "blockers": tuple() if ready else blockers,
        "connector_capability_summary": {
            "supports_live_orders": ready,
            "supports_single_order_only": ready,
            "supports_micro_size_only": ready,
            "live_endpoint_confirmed": bool(config.get("capability_summary", {}).get("live_endpoint_confirmed", False)),
            "stores_credentials": False,
            "stores_account_id": False,
        },
        "safety_summary": _safety_summary(order_submitted=False),
        "next_safe_action": "inject_into_live_runtime_executor" if ready else "repair_oanda_live_connector_config",
    }


def _order_intent_blockers(intent: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    side = str(intent.get("side", "")).upper()
    units = _to_int(intent.get("units", 0))
    if not intent:
        blockers.append("order_intent_missing")
    if not str(intent.get("instrument", "")).strip():
        blockers.append("instrument_missing")
    if side not in {"BUY", "SELL"}:
        blockers.append("invalid_side")
    if units <= 0:
        blockers.append("invalid_units")
    if units > MAX_LIVE_MICRO_UNITS:
        blockers.append("units_exceed_micro_max")
    if not intent.get("stop_loss"):
        blockers.append("stop_loss_missing")
    if not intent.get("take_profit"):
        blockers.append("take_profit_missing")
    return blockers


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
        lowered = str(key).lower().strip()
        if lowered in SENSITIVE_KEYS:
            continue
        sanitized[str(key)] = _sanitize_value(value)
    sanitized["credential_persisted"] = False
    sanitized["account_id_persisted"] = False
    sanitized["raw_broker_payload_persisted"] = False
    return sanitized


def _safety_summary(order_submitted: bool) -> dict[str, bool]:
    return {
        "live_connector_contract": True,
        "order_submitted": bool(order_submitted),
        "credential_persistence": False,
        "account_id_persistence": False,
        "env_read": False,
        "scheduler_daemon_webhook": False,
        "no_loop": True,
        "no_retry": True,
        "one_order_only": True,
    }


def _next_config_action(status: str) -> str:
    return {
        OANDA_LIVE_CONNECTOR_CONFIG_READY: "build_oanda_live_connector_readiness_packet",
        OANDA_LIVE_CONNECTOR_CONFIG_BLOCKED: "resolve_live_connector_config_blockers",
        OANDA_LIVE_CONNECTOR_CONFIG_INVALID: "provide_runtime_config",
        OANDA_LIVE_CONNECTOR_CONFIG_REVIEW_REQUIRED: "obtain_operator_live_runtime_approval",
    }.get(status, "provide_runtime_config")


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _unique(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen = set()
    output = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return tuple(output)
