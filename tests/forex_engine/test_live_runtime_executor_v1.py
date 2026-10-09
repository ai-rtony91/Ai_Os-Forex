from __future__ import annotations

from automation.forex_engine import live_runtime_executor_v1 as executor
from automation.forex_engine import oanda_live_runtime_connector_v2 as connector_mod


class FakeLiveConnector:
    supports_live_orders = True
    supports_single_order_only = True
    supports_micro_size_only = True
    live_endpoint_confirmed = True
    stores_credentials = False
    stores_account_id = False
    demo_only = False
    paper_only = False

    def __init__(self) -> None:
        self.calls = []

    def place_live_micro_order(self, intent: dict) -> dict:
        self.calls.append(dict(intent))
        return {
            "submitted": True,
            "status": "ACCEPTED",
            "units": intent.get("units"),
            "instrument": intent.get("instrument"),
            "side": intent.get("side"),
        }


class UnsafeConnector:
    supports_live_orders = False
    supports_single_order_only = False
    supports_micro_size_only = False
    live_endpoint_confirmed = False
    stores_credentials = True
    stores_account_id = True
    demo_only = True
    paper_only = True


def _command_contract() -> dict:
    return {
        "command_status": executor.LIVE_ORDER_COMMAND_READY,
        "ready": True,
        "order_executed": False,
        "broker_call_performed": False,
        "final_execute_live_order_command": True,
        "sanitized_order_intent": {
            "instrument": "EUR_USD",
            "side": "BUY",
            "units": 1,
            "risk_cap": 1,
            "stop_loss": 1.09,
            "take_profit": 1.11,
        },
    }


def _auth_gate() -> dict:
    return {
        "auth_status": executor.PROTECTED_LIVE_ACTION_AUTH_READY,
        "ready": True,
        "protected_action": "live_order_command_contract",
    }


def _runtime_context() -> dict:
    return {
        "operator_present": True,
        "one_trade_only": True,
        "micro_size_only": True,
        "max_loss_gate_clear": True,
        "daily_stop_clear": True,
        "kill_switch_enabled": False,
        "risk_cap_confirmed": True,
        "stop_loss_confirmed": True,
        "take_profit_confirmed": True,
        "live_exception_mode": True,
        "allow_live_network_once": True,
        "credentials_runtime_only": True,
        "credentials_persisted": False,
        "account_id_persisted": False,
    }


def _runtime_request() -> dict:
    return executor.build_live_runtime_execution_request(
        _command_contract(),
        _auth_gate(),
        runtime_context=_runtime_context(),
    )


def _oanda_config() -> dict:
    return connector_mod.build_oanda_live_connector_config(
        {
            "operator_approved_live_runtime": True,
            "live_endpoint_confirmed": True,
            "credentials_runtime_only": True,
            "credentials_persisted": False,
            "account_id_persisted": False,
            "single_order_only": True,
            "micro_size_only": True,
            "no_retry": True,
            "no_loop": True,
            "max_order_count": 1,
            "transport_injected": True,
        }
    )


def test_runtime_request_ready_path() -> None:
    request = _runtime_request()

    assert request["request_status"] == executor.LIVE_RUNTIME_REQUEST_READY
    assert request["ready"] is True
    assert request["broker_call_performed"] is False
    assert request["order_executed"] is False
    assert request["env_read"] is False


def test_runtime_request_invalid_when_command_missing() -> None:
    request = executor.build_live_runtime_execution_request(None, _auth_gate(), runtime_context=_runtime_context())

    assert request["request_status"] == executor.LIVE_RUNTIME_REQUEST_INVALID
    assert "command_contract_missing" in request["blockers"]


def test_runtime_request_invalid_when_auth_missing() -> None:
    request = executor.build_live_runtime_execution_request(_command_contract(), None, runtime_context=_runtime_context())

    assert request["request_status"] == executor.LIVE_RUNTIME_REQUEST_INVALID
    assert "auth_gate_missing" in request["blockers"]


def test_runtime_request_review_required_when_context_missing() -> None:
    request = executor.build_live_runtime_execution_request(_command_contract(), _auth_gate())

    assert request["request_status"] == executor.LIVE_RUNTIME_REQUEST_REVIEW_REQUIRED
    assert "runtime_context_missing" in request["blockers"]


def test_runtime_request_blocks_kill_switch() -> None:
    context = _runtime_context()
    context["kill_switch_enabled"] = True

    request = executor.build_live_runtime_execution_request(_command_contract(), _auth_gate(), runtime_context=context)

    assert request["request_status"] == executor.LIVE_RUNTIME_REQUEST_BLOCKED
    assert "kill_switch_enabled" in request["blockers"]


def test_runtime_request_blocks_persisted_credentials_and_account_id() -> None:
    context = _runtime_context()
    context["credentials_persisted"] = True
    context["account_id_persisted"] = True

    request = executor.build_live_runtime_execution_request(_command_contract(), _auth_gate(), runtime_context=context)

    assert request["request_status"] == executor.LIVE_RUNTIME_REQUEST_BLOCKED
    assert "credentials_persisted_forbidden" in request["blockers"]
    assert "account_id_persisted_forbidden" in request["blockers"]


def test_executor_review_required_when_execute_false() -> None:
    result = executor.execute_single_live_micro_trade(_runtime_request(), FakeLiveConnector(), execute_requested=False)

    assert result["execution_status"] == executor.LIVE_RUNTIME_EXECUTION_REVIEW_REQUIRED
    assert result["executed"] is False
    assert result["order_count"] == 0


def test_executor_blocks_missing_connector_when_execute_true() -> None:
    result = executor.execute_single_live_micro_trade(_runtime_request(), None, execute_requested=True)

    assert result["execution_status"] == executor.LIVE_RUNTIME_EXECUTION_BLOCKED
    assert "live_connector_missing" in result["blockers"]


def test_executor_blocks_unsafe_connector() -> None:
    result = executor.execute_single_live_micro_trade(_runtime_request(), UnsafeConnector(), execute_requested=True)

    assert result["execution_status"] == executor.LIVE_RUNTIME_EXECUTION_BLOCKED
    assert any("connector_" in blocker for blocker in result["blockers"])
    assert result["executed"] is False


def test_executor_submits_exactly_one_order_with_fake_connector() -> None:
    connector = FakeLiveConnector()

    result = executor.execute_single_live_micro_trade(_runtime_request(), connector, execute_requested=True)

    assert result["execution_status"] == executor.LIVE_RUNTIME_EXECUTION_SUBMITTED
    assert result["executed"] is True
    assert result["order_count"] == 1
    assert len(connector.calls) == 1
    assert result["no_loop"] is True
    assert result["no_retry"] is True
    assert result["one_order_only"] is True


def test_executor_blocks_connector_refusal_without_marking_submitted() -> None:
    command = _command_contract()
    command["sanitized_order_intent"]["units"] = connector_mod.MAX_LIVE_MICRO_UNITS + 1
    request = executor.build_live_runtime_execution_request(
        command,
        _auth_gate(),
        runtime_context=_runtime_context(),
    )
    connector = connector_mod.OandaLiveRuntimeConnectorV2(_oanda_config(), FakeLiveConnector())

    result = executor.execute_single_live_micro_trade(request, connector, execute_requested=True)

    assert result["execution_status"] == executor.LIVE_RUNTIME_EXECUTION_BLOCKED
    assert result["executed"] is False
    assert result["order_count"] == 0
    assert result["sanitized_broker_result"]["submitted"] is False
    assert result["sanitized_broker_result"]["accepted"] is False
    assert "connector_order_not_submitted" in result["blockers"]
    assert "units_exceed_micro_max" in result["blockers"]


def test_executor_output_is_sanitized() -> None:
    connector = FakeLiveConnector()
    result = executor.execute_single_live_micro_trade(_runtime_request(), connector, execute_requested=True)

    assert "account_id" not in result["sanitized_broker_result"]
    assert "token" not in result["sanitized_broker_result"]
    assert result["sanitized_broker_result"]["credential_persisted"] is False


def test_live_ledger_ready_from_sanitized_submitted_result() -> None:
    connector = FakeLiveConnector()
    execution = executor.execute_single_live_micro_trade(_runtime_request(), connector, execute_requested=True)

    ledger = executor.record_live_micro_trade_runtime_result(execution, {"reviewed": True, "pnl": 0.5})

    assert ledger["ledger_status"] == executor.LIVE_RUNTIME_LEDGER_READY
    assert ledger["ready"] is True
    assert ledger["evidence_summary"]["order_count"] == 1


def test_live_ledger_blocks_sensitive_result_review() -> None:
    connector = FakeLiveConnector()
    execution = executor.execute_single_live_micro_trade(_runtime_request(), connector, execute_requested=True)

    ledger = executor.record_live_micro_trade_runtime_result(execution, {"account_id": "123"})

    assert ledger["ledger_status"] == executor.LIVE_RUNTIME_LEDGER_BLOCKED
    assert "sensitive_result_review_field_detected" in ledger["blockers"]


def test_no_real_network_or_broker_is_used_in_tests() -> None:
    connector = FakeLiveConnector()
    execution = executor.execute_single_live_micro_trade(_runtime_request(), connector, execute_requested=True)

    assert len(connector.calls) == 1
    assert execution["safety_summary"]["credential_persistence"] is False
    assert execution["safety_summary"]["env_read"] is False
    assert execution["safety_summary"]["scheduler_daemon_webhook"] is False
