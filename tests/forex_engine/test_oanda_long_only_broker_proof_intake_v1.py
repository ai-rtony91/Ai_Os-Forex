from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import inspect

from automation.forex_engine import oanda_long_only_broker_proof_intake_v1 as intake


def _valid_proof():
    return {
        "broker_name": "OANDA_SANITIZED_PRACTICE",
        "broker_environment": "practice",
        "asset_class": "forex",
        "account_type": "practice_margin",
        "account_currency": "USD",
        "margin_available_confirmed": True,
        "effective_leverage_limit": 2.0,
        "long_permission": True,
        "short_permission": False,
        "fifo_required": True,
        "hedging_available": False,
        "instrument_tradable": True,
        "instrument": "EUR_USD",
        "max_units": 1000,
        "stop_loss_supported": True,
        "take_profit_supported": True,
        "order_type_supported": ["market"],
        "one_order_only_supported": True,
        "demo_sandbox_order_preview_supported": True,
        "broker_house_restrictions": [],
        "proof_timestamp": datetime.now(timezone.utc).isoformat(),
        "proof_source": "anthony_sanitized_oanda_practice_permission_proof",
        "sanitized_evidence_only": True,
        "no_credentials_in_payload": True,
        "no_account_id_in_payload": True,
        "no_env_in_payload": True,
        "no_network_call": True,
        "no_broker_mutation": True,
        "no_order_execution": True,
    }


def _result(proof):
    return intake.evaluate_oanda_long_only_broker_proof(proof)


def _blocked(proof):
    result = _result(proof)
    assert result["status"] == intake.OANDA_BROKER_PROOF_BLOCKED
    assert result["ready"] is False
    return result


def test_missing_proof_blocks():
    assert "missing_oanda_broker_proof" in _blocked({})["blockers"]


def test_non_dict_proof_blocks():
    assert "missing_oanda_broker_proof" in _blocked(["bad"])["blockers"]


def test_empty_proof_blocks():
    assert "missing_oanda_broker_proof" in _blocked({})["blockers"]


def test_missing_broker_name_blocks():
    proof = _valid_proof()
    proof.pop("broker_name")
    assert "missing_required_field:broker_name" in _blocked(proof)["blockers"]


def test_wrong_broker_blocks():
    proof = _valid_proof()
    proof["broker_name"] = "OTHER"
    assert "broker_name_not_oanda" in _blocked(proof)["blockers"]


def test_missing_environment_blocks():
    proof = _valid_proof()
    proof.pop("broker_environment")
    assert "missing_required_field:broker_environment" in _blocked(proof)["blockers"]


def test_live_environment_blocks():
    proof = _valid_proof()
    proof["broker_environment"] = "live"
    assert "broker_environment_not_demo_sandbox_or_practice" in _blocked(proof)["blockers"]


def test_production_environment_blocks():
    proof = _valid_proof()
    proof["broker_environment"] = "production"
    assert "broker_environment_not_demo_sandbox_or_practice" in _blocked(proof)["blockers"]


def test_missing_asset_class_blocks():
    proof = _valid_proof()
    proof.pop("asset_class")
    assert "missing_required_field:asset_class" in _blocked(proof)["blockers"]


def test_non_forex_asset_class_blocks():
    proof = _valid_proof()
    proof["asset_class"] = "crypto"
    assert "asset_class_not_forex" in _blocked(proof)["blockers"]


def test_missing_long_permission_blocks():
    proof = _valid_proof()
    proof.pop("long_permission")
    assert "missing_required_field:long_permission" in _blocked(proof)["blockers"]


def test_long_permission_false_blocks():
    proof = _valid_proof()
    proof["long_permission"] = False
    assert "long_permission_not_confirmed" in _blocked(proof)["blockers"]


def test_short_permission_false_does_not_block_long_only_proof():
    result = _result(_valid_proof())
    assert result["status"] == intake.OANDA_LONG_ONLY_BROKER_PROOF_READY
    assert result["short_side_enabled"] is False
    assert result["short_side_status"] == "SHORT_SIDE_DISABLED"
    assert result["account_permission_gate"]["short_permission"] is False


def test_short_permission_true_still_leaves_short_side_enabled_false():
    proof = _valid_proof()
    proof["short_permission"] = True
    result = _result(proof)
    assert result["status"] == intake.OANDA_LONG_ONLY_BROKER_PROOF_READY
    assert result["short_side_enabled"] is False


def test_missing_instrument_tradable_blocks():
    proof = _valid_proof()
    proof.pop("instrument_tradable")
    result = _blocked(proof)
    assert "missing_required_field:instrument_tradable" in result["blockers"]


def test_missing_stop_loss_support_blocks():
    proof = _valid_proof()
    proof["stop_loss_supported"] = False
    assert "stop_loss_not_supported" in _blocked(proof)["blockers"]


def test_missing_take_profit_support_blocks():
    proof = _valid_proof()
    proof["take_profit_supported"] = False
    assert "take_profit_not_supported" in _blocked(proof)["blockers"]


def test_missing_one_order_only_support_blocks():
    proof = _valid_proof()
    proof["one_order_only_supported"] = False
    assert "one_order_only_not_supported" in _blocked(proof)["blockers"]


def test_missing_demo_sandbox_order_preview_support_blocks():
    proof = _valid_proof()
    proof["demo_sandbox_order_preview_supported"] = False
    assert "demo_sandbox_order_preview_not_supported" in _blocked(proof)["blockers"]


def test_missing_sanitized_evidence_only_blocks():
    proof = _valid_proof()
    proof["sanitized_evidence_only"] = False
    assert "sanitized_evidence_only_not_confirmed" in _blocked(proof)["blockers"]


def test_no_credentials_in_payload_false_blocks():
    proof = _valid_proof()
    proof["no_credentials_in_payload"] = False
    assert "credentials_in_payload_detected" in _blocked(proof)["blockers"]


def test_no_account_id_in_payload_false_blocks():
    proof = _valid_proof()
    proof["no_account_id_in_payload"] = False
    assert "account_id_in_payload_detected" in _blocked(proof)["blockers"]


def test_no_env_in_payload_false_blocks():
    proof = _valid_proof()
    proof["no_env_in_payload"] = False
    assert "env_in_payload_detected" in _blocked(proof)["blockers"]


def test_no_network_call_false_blocks():
    proof = _valid_proof()
    proof["no_network_call"] = False
    assert "network_call_detected" in _blocked(proof)["blockers"]


def test_no_broker_mutation_false_blocks():
    proof = _valid_proof()
    proof["no_broker_mutation"] = False
    assert "broker_mutation_detected" in _blocked(proof)["blockers"]


def test_no_order_execution_false_blocks():
    proof = _valid_proof()
    proof["no_order_execution"] = False
    assert "order_execution_detected" in _blocked(proof)["blockers"]


def test_credential_looking_key_blocks():
    proof = _valid_proof()
    proof["credentials"] = {"redacted": True}
    assert "sensitive_payload_key:credentials" in _blocked(proof)["blockers"]


def test_token_looking_value_blocks():
    proof = _valid_proof()
    proof["proof_source"] = "Bearer redacted"
    assert "sensitive_payload_value_detected" in _blocked(proof)["blockers"]


def test_account_id_looking_key_blocks():
    proof = _valid_proof()
    proof["account_id"] = "redacted"
    assert "sensitive_payload_key:account_id" in _blocked(proof)["blockers"]


def test_env_looking_value_blocks():
    proof = _valid_proof()
    proof["proof_source"] = "C:/tmp/.env"
    assert "sensitive_payload_value_detected" in _blocked(proof)["blockers"]


def test_unknown_extra_field_blocks():
    proof = _valid_proof()
    proof["extra"] = "not allowed"
    result = _blocked(proof)
    assert "unknown_fields_present" in result["blockers"]
    assert "unknown_field:extra" in result["blockers"]


def test_valid_sanitized_oanda_demo_proof_returns_ready():
    proof = _valid_proof()
    proof["broker_environment"] = "demo"
    result = _result(proof)
    assert result["status"] == intake.OANDA_LONG_ONLY_BROKER_PROOF_READY
    assert result["ready"] is True
    assert result["broker_gate_clear_for_demo_preparation"] is True


def test_valid_sanitized_oanda_practice_proof_returns_ready():
    result = _result(_valid_proof())
    assert result["status"] == intake.OANDA_LONG_ONLY_BROKER_PROOF_READY
    assert result["ready"] is True
    assert result["long_only_ready_for_demo_preparation"] is True


def test_valid_proof_keeps_execution_allowed_false():
    result = _result(_valid_proof())
    assert result["execution_allowed"] is False


def test_valid_proof_keeps_ready_to_execute_false():
    result = _result(_valid_proof())
    assert result["ready_to_execute"] is False


def test_valid_proof_keeps_demo_order_allowed_false():
    result = _result(_valid_proof())
    assert result["demo_order_allowed"] is False


def test_valid_proof_keeps_live_autonomy_allowed_false():
    result = _result(_valid_proof())
    assert result["live_autonomy_allowed"] is False


def test_integrated_supervisor_remains_prepare_only_and_execution_false():
    result = intake.build_oanda_long_only_autonomous_supervisor_contract(_valid_proof())
    assert result["oanda_broker_proof_status"] == intake.OANDA_LONG_ONLY_BROKER_PROOF_READY
    assert result["status"] == "AUTONOMOUS_REQUIRE_MORE_EVIDENCE"
    assert result["readiness_gates"]["evidence_gate_cleared"] is False
    assert result["readiness_gates"]["risk_gate_cleared"] is False
    assert result["readiness_gates"]["broker_gate_cleared"] is True
    assert result["readiness_gates"]["policy_gate_cleared"] is False
    assert result["can_prepare_demo_plan"] is False
    assert result["execution_allowed"] is False
    assert result["ready_to_execute"] is False
    assert result["live_autonomy_allowed"] is False
    assert result["safety"]["network_used"] is False
    assert result["safety"]["broker_mutation"] is False
    assert result["safety"]["order_execution"] is False
    assert result["next_safe_action"] == "restore_profitable_evidence_and_walk_forward_gate"


def test_invalid_integrated_supervisor_stays_broker_blocked():
    proof = _valid_proof()
    proof["broker_environment"] = "live"
    result = intake.build_oanda_long_only_autonomous_supervisor_contract(proof)
    assert result["oanda_broker_proof_status"] == intake.OANDA_BROKER_PROOF_BLOCKED
    assert result["status"] == "AUTONOMOUS_BLOCKED_BY_BROKER_GATE"
    assert result["execution_allowed"] is False


def test_inputs_are_not_mutated():
    proof = _valid_proof()
    original = deepcopy(proof)
    intake.evaluate_oanda_long_only_broker_proof(proof)
    intake.build_oanda_long_only_autonomous_supervisor_contract(proof)
    assert proof == original


def test_source_has_no_forbidden_runtime_apis():
    source = inspect.getsource(intake)
    forbidden = (
        "import requests",
        "from requests",
        "import urllib",
        "from urllib",
        "import socket",
        "from socket",
        "os.environ",
        "getenv(",
        "open(",
        "Path(",
        "read_text",
        "subprocess",
        "Start-Process",
    )
    for token in forbidden:
        assert token not in source
