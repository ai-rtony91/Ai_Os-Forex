from __future__ import annotations

from automation.forex_engine import live_runtime_executor_v1 as executor
from automation.forex_engine import oanda_live_runtime_connector_v2 as connector_mod


class FakeAttemptReservation:
    """One-use test fixture only; not a durable production implementation."""

    def __init__(self) -> None:
        self.used = False

    def __call__(self) -> bool:
        if self.used:
            return False
        self.used = True
        return True



class FakeTransport:
    def __init__(self) -> None:
        self.calls = []

    def place_live_micro_order(self, intent: dict) -> dict:
        self.calls.append(dict(intent))
        return {
            "submitted": True,
            "accepted": True,
            "instrument": intent["instrument"],
            "side": intent["side"],
            "units": intent["units"],
            "account_id": "SHOULD_NOT_PERSIST",
        }


def _config() -> dict:
    return {
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
        "dry_run_transport": False,
    }


def _intent() -> dict:
    return {
        "instrument": "EUR_USD",
        "side": "BUY",
        "units": 1,
        "risk_cap": 1,
        "stop_loss": 1.09,
        "take_profit": 1.11,
    }


def _runtime_request() -> dict:
    command = {
        "command_status": executor.LIVE_ORDER_COMMAND_READY,
        "ready": True,
        "order_executed": False,
        "broker_call_performed": False,
        "final_execute_live_order_command": True,
        "sanitized_order_intent": _intent(),
    }
    auth = {
        "auth_status": executor.PROTECTED_LIVE_ACTION_AUTH_READY,
        "ready": True,
        "protected_action": "live_order_command_contract",
    }
    context = {
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
    return executor.build_live_runtime_execution_request(command, auth, runtime_context=context)


def test_config_ready_path() -> None:
    result = connector_mod.build_oanda_live_connector_config(_config())

    assert result["config_status"] == connector_mod.OANDA_LIVE_CONNECTOR_CONFIG_READY
    assert result["ready"] is True


def test_config_invalid_when_missing() -> None:
    result = connector_mod.build_oanda_live_connector_config(None)

    assert result["config_status"] == connector_mod.OANDA_LIVE_CONNECTOR_CONFIG_INVALID
    assert "runtime_config_missing" in result["blockers"]


def test_config_review_required_without_operator_approval() -> None:
    config = _config()
    config["operator_approved_live_runtime"] = False

    result = connector_mod.build_oanda_live_connector_config(config)

    assert result["config_status"] == connector_mod.OANDA_LIVE_CONNECTOR_CONFIG_REVIEW_REQUIRED


def test_config_blocks_credential_persistence() -> None:
    config = _config()
    config["credentials_persisted"] = True

    result = connector_mod.build_oanda_live_connector_config(config)

    assert result["config_status"] == connector_mod.OANDA_LIVE_CONNECTOR_CONFIG_BLOCKED
    assert "credentials_persisted_invalid" in result["blockers"]


def test_config_blocks_account_id_persistence() -> None:
    config = _config()
    config["account_id_persisted"] = True

    result = connector_mod.build_oanda_live_connector_config(config)

    assert result["config_status"] == connector_mod.OANDA_LIVE_CONNECTOR_CONFIG_BLOCKED
    assert "account_id_persisted_invalid" in result["blockers"]


def test_config_blocks_max_order_count_above_one() -> None:
    config = _config()
    config["max_order_count"] = 2

    result = connector_mod.build_oanda_live_connector_config(config)

    assert result["config_status"] == connector_mod.OANDA_LIVE_CONNECTOR_CONFIG_BLOCKED
    assert "max_order_count_must_equal_one" in result["blockers"]


def test_connector_exposes_executor_required_attributes() -> None:
    config = connector_mod.build_oanda_live_connector_config(_config())
    connector = connector_mod.OandaLiveRuntimeConnectorV2(config, FakeTransport())

    assert connector.supports_live_orders is True
    assert connector.supports_single_order_only is True
    assert connector.supports_micro_size_only is True
    assert connector.live_endpoint_confirmed is True
    assert connector.stores_credentials is False
    assert connector.stores_account_id is False
    assert connector.demo_only is False
    assert connector.paper_only is False


def test_connector_blocks_without_transport() -> None:
    config = connector_mod.build_oanda_live_connector_config(_config())
    connector = connector_mod.OandaLiveRuntimeConnectorV2(config, None)

    result = connector.place_live_micro_order(_intent())

    assert result["submitted"] is False
    assert "transport_missing" in result["blockers"]


def test_connector_submits_exactly_one_fake_order() -> None:
    transport = FakeTransport()
    config = connector_mod.build_oanda_live_connector_config(_config())
    connector = connector_mod.OandaLiveRuntimeConnectorV2(config, transport, reserve_attempt=FakeAttemptReservation())

    result = connector.place_live_micro_order(_intent())

    assert result["submitted"] is True
    assert result["order_count"] == 1
    assert len(transport.calls) == 1


def test_connector_blocks_second_order() -> None:
    transport = FakeTransport()
    config = connector_mod.build_oanda_live_connector_config(_config())
    connector = connector_mod.OandaLiveRuntimeConnectorV2(config, transport, reserve_attempt=FakeAttemptReservation())

    connector.place_live_micro_order(_intent())
    result = connector.place_live_micro_order(_intent())

    assert result["submitted"] is False
    assert "second_order_blocked" in result["blockers"]
    assert len(transport.calls) == 1


def test_connector_blocks_invalid_units_and_side() -> None:
    config = connector_mod.build_oanda_live_connector_config(_config())
    connector = connector_mod.OandaLiveRuntimeConnectorV2(config, FakeTransport())
    intent = _intent()
    intent["units"] = 0
    intent["side"] = "HOLD"

    result = connector.place_live_micro_order(intent)

    assert result["submitted"] is False
    assert "invalid_units" in result["blockers"]
    assert "invalid_side" in result["blockers"]


def test_connector_sanitizes_broker_result() -> None:
    config = connector_mod.build_oanda_live_connector_config(_config())
    connector = connector_mod.OandaLiveRuntimeConnectorV2(config, FakeTransport(), reserve_attempt=FakeAttemptReservation())

    result = connector.place_live_micro_order(_intent())

    assert "account_id" not in result["sanitized_response"]
    assert result["sanitized_response"]["account_id_persisted"] is False


def test_connector_integrates_with_live_runtime_executor() -> None:
    transport = FakeTransport()
    config = connector_mod.build_oanda_live_connector_config(_config())
    connector = connector_mod.OandaLiveRuntimeConnectorV2(config, transport, reserve_attempt=FakeAttemptReservation())

    execution = executor.execute_single_live_micro_trade(_runtime_request(), connector, execute_requested=True)

    assert execution["execution_status"] == executor.LIVE_RUNTIME_EXECUTION_SUBMITTED
    assert execution["executed"] is True
    assert execution["order_count"] == 1
    assert len(transport.calls) == 1


def test_readiness_packet_ready() -> None:
    config = connector_mod.build_oanda_live_connector_config(_config())

    packet = connector_mod.build_oanda_live_connector_readiness_packet(config)

    assert packet["ready"] is True
    assert packet["connector_capability_summary"]["supports_live_orders"] is True


def test_no_env_or_real_network_used() -> None:
    config = connector_mod.build_oanda_live_connector_config(_config())
    connector = connector_mod.OandaLiveRuntimeConnectorV2(config, FakeTransport(), reserve_attempt=FakeAttemptReservation())
    result = connector.place_live_micro_order(_intent())

    assert result["safety_summary"]["env_read"] is False
    assert result["safety_summary"]["credential_persistence"] is False
    assert result["safety_summary"]["no_retry"] is True


def test_connector_defaults_to_denial_without_attempt_reservation() -> None:
    transport = FakeTransport()
    config = connector_mod.build_oanda_live_connector_config(_config())
    connector = connector_mod.OandaLiveRuntimeConnectorV2(config, transport)

    result = connector.place_live_micro_order(_intent())

    assert result["submitted"] is False
    assert result["accepted"] is False
    assert "attempt_reservation_required" in result["blockers"]
    assert transport.calls == []


def test_connector_empty_acknowledgement_remains_unknown() -> None:
    class EmptyFakeTransport(FakeTransport):
        def place_live_micro_order(self, intent: dict) -> dict:
            self.calls.append(dict(intent))
            return {}

    transport = EmptyFakeTransport()
    config = connector_mod.build_oanda_live_connector_config(_config())
    connector = connector_mod.OandaLiveRuntimeConnectorV2(config, transport, reserve_attempt=FakeAttemptReservation())

    result = connector.place_live_micro_order(_intent())

    assert result["accepted"] is False
    assert result["outcome_known"] is False
    assert result["retry_allowed"] is False
    assert len(transport.calls) == 1
