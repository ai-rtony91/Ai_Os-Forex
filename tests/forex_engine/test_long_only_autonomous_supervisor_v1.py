from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import inspect

from automation.forex_engine import long_only_autonomous_supervisor_v1 as supervisor


def _approval_window():
    now = datetime.now(timezone.utc)
    return {
        "starts_at_utc": (now - timedelta(minutes=5)).isoformat(),
        "expires_at_utc": (now + timedelta(hours=1)).isoformat(),
    }


def _live_exception_contracts():
    window = _approval_window()
    return {
        "request": {
            "packet_id": "AIOS-FOREX-LONG-ONLY-AUTONOMY-TEST",
            "approval_window": dict(window),
            "broker_path": "approved-human-owner-vault-handle",
            "instrument": "EUR_USD",
            "side": "buy",
            "units": 1,
            "max_loss": 1.0,
            "daily_loss_cap": 2.0,
            "stop_loss": 1.0,
            "take_profit": 2.0,
            "order_type": "market",
            "evidence_bundle_id": "evidence-long-only-autonomy-test",
            "kill_switch_required": True,
            "approval_nonce_hash": "sha256:redacted-test-nonce",
            "arming_step": "manual-human-owner-arm",
            "stop_point": "hard-stop-before-live-execution",
            "one_order_only": True,
            "retry_allowed": False,
            "autonomous_reentry_allowed": False,
        },
        "approval": {
            "packet_id": "AIOS-FOREX-LONG-ONLY-AUTONOMY-TEST",
            "human_owner": "Anthony",
            "approval_type": "single_live_micro_trade_exception",
            "approval_window": dict(window),
            "broker_path": "approved-human-owner-vault-handle",
            "instrument": "EUR_USD",
            "side": "buy",
            "units": 1,
            "max_loss": 1.0,
            "daily_loss_cap": 2.0,
            "stop_loss": 1.0,
            "take_profit": 2.0,
            "order_type": "market",
            "evidence_bundle_id": "evidence-long-only-autonomy-test",
            "approval_nonce_hash": "sha256:redacted-test-nonce",
            "arming_step": "manual-human-owner-arm",
            "stop_point": "hard-stop-before-live-execution",
            "non_transferable": True,
            "expires_after_use": True,
            "validator_authority": False,
            "dashboard_authority": False,
            "router_authority": False,
        },
        "evidence_bundle": {
            "evidence_bundle_id": "evidence-long-only-autonomy-test",
            "packet_id": "AIOS-FOREX-LONG-ONLY-AUTONOMY-TEST",
            "broker_sandbox_or_demo_proof": True,
            "risk_gate_passed": True,
            "kill_switch_active": True,
            "daily_loss_cap_active": True,
            "approval_hash_verified": True,
            "sanitized": True,
            "owner_live_exception_request": True,
            "owner_approval_required": True,
            "owner_approval_present": True,
            "arming_timestamp": datetime.now(timezone.utc).isoformat(),
            "kill_switch_confirmed": True,
            "max_loss_confirmed": True,
            "daily_stop_confirmed": True,
            "stop_loss_confirmed": True,
            "take_profit_confirmed": True,
            "one_order_only_confirmed": True,
            "micro_size_confirmed": True,
            "low_effective_leverage_confirmed": True,
            "sanitized_evidence_only": True,
            "no_credential_read": True,
            "no_credential_write": True,
            "no_env_read": True,
            "no_env_write": True,
            "no_account_id_read": True,
            "no_account_id_write": True,
            "no_network_call": True,
            "no_broker_mutation": True,
            "no_live_order_execution": True,
            "scheduler_enabled": False,
            "daemon_enabled": False,
            "webhook_enabled": False,
            "background_execution": False,
            "credential_read": False,
            "credential_write": False,
            "env_read": False,
            "env_write": False,
            "account_id_read": False,
            "account_id_write": False,
            "network_call": False,
            "broker_mutation": False,
            "live_order_execution": False,
        },
        "arming_state": {
            "packet_id": "AIOS-FOREX-LONG-ONLY-AUTONOMY-TEST",
            "approval_nonce_hash": "sha256:redacted-test-nonce",
            "evidence_bundle_id": "evidence-long-only-autonomy-test",
            "kill_switch_active": True,
            "daily_loss_cap_active": True,
            "evidence_bundle_present": True,
            "approval_hash_verified": True,
            "approval_window_active": True,
            "one_order_remaining": True,
            "armed": True,
            "orders_remaining": 1,
        },
    }


def _final_status_payload():
    return {
        "candidate": {
            "candidate_id": "c1-eur-buy",
            "strategy_name": "ema_mean_reversion",
            "pair": "EURUSD",
            "direction": "buy",
            "walk_forward_status": "passed",
            "mitigation_status": "improved",
        },
        "paper_metrics": {
            "total_trades": 30,
            "closed_trades": 30,
            "win_rate": 0.61,
            "expectancy": 0.12,
            "profit_factor": 1.8,
            "max_drawdown": 0.05,
            "sample_size": 30,
        },
        "walk_forward_status": "passed",
        "walk_forward_result": {
            "windows_evaluated": 3,
            "passing_windows": 3,
            "walk_forward_gate_cleared": True,
        },
        "validation_results": [{"status": "PASS"}],
        "candidate_approved_for_demo_validation": True,
        "demo_validation_contract": {"demo_validation_contract_completed": True, "status": "COMPLETE"},
        "live_readiness_candidate": {"candidate_id": "c1-eur-buy", "live_ready": True},
        "approval_trace": {"signed": True, "reviewed_by": "review_lead"},
        "risk_limits": {
            "maximum_loss": 1.0,
            "daily_loss_cap": 2.0,
            "stop_loss": 1.0,
            "take_profit": 2.0,
            "max_drawdown_limit": 0.10,
            "effective_leverage": 0.5,
            "max_effective_leverage": 2.0,
            "requested_units": 1,
            "max_live_micro_units": 1000,
        },
        "kill_switch_proof": {"status": "PASS"},
        "rollback_proof": {"status": "PASS"},
        "reconciliation_proof": {"status": "PASS"},
        "evidence_timestamp": datetime.now(timezone.utc).isoformat(),
        "replayability_proof": {"status": "PASS"},
        "final_disarm_proof": {"status": "PASS"},
        "post_trade_journal_path": "/tmp/post_trade_journal.csv",
        "one_shot_exception_package": {"exception_package_completed": True},
        "live_review_certificate": {"certificate_completed": True},
        "human_review_ready": True,
        "one_shot_controls": {
            "one_order_only": True,
            "micro_size_only": True,
            "retry_allowed": False,
            "autonomous_reentry_allowed": False,
            "scheduler_enabled": False,
            "daemon_enabled": False,
            "webhook_enabled": False,
            "background_execution": False,
        },
        "broker_gate": {
            "broker_sandbox_or_demo_proof": True,
            "broker_mutation": False,
            "credentials_persisted": False,
            "account_id_persisted": False,
        },
        "account_permission_gate": {
            "broker_name": "OANDA_SANITIZED_DEMO",
            "broker_environment": "demo",
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
            "max_units": 1000,
            "stop_loss_supported": True,
            "take_profit_supported": True,
            "order_type_supported": ["market"],
            "one_order_only_supported": True,
            "demo_sandbox_order_preview_supported": True,
            "broker_house_restrictions": [],
            "proof_timestamp": datetime.now(timezone.utc).isoformat(),
            "proof_source": "sanitized_contract_fixture_no_broker_io",
            "sanitized_evidence_only": True,
            "activation_side": "long",
        },
        "live_exception_contracts": _live_exception_contracts(),
    }


def test_current_long_only_demo_supervisor_can_prepare_but_not_execute():
    result = supervisor.build_long_only_autonomous_supervisor_contract()
    assert result["status"] == supervisor.AUTONOMOUS_REQUIRE_MORE_EVIDENCE
    assert result["can_prepare_demo_plan"] is False
    assert result["execution_allowed"] is False
    assert result["ready_to_execute"] is False
    assert result["demo_plan"]["prepare_only"] is True
    assert result["demo_plan"]["order_execution"] is False
    assert result["next_safe_action"] == "restore_profitable_evidence_and_walk_forward_gate"


def test_short_side_stays_disabled():
    result = supervisor.build_long_only_autonomous_supervisor_contract(
        final_status_payload=_final_status_payload(),
        supervisor_contract={"activation_side": "short", "short_side_enabled": True},
    )
    assert result["short_side_enabled"] is False
    assert result["short_side_status"] == "SHORT_SIDE_DISABLED"
    assert "short_side_disabled" in result["blockers"]["policy"]
    assert result["execution_allowed"] is False


def test_broker_gate_blocks_execution():
    payload = _final_status_payload()
    payload["broker_gate"] = {}
    payload["account_permission_gate"] = {}
    result = supervisor.build_long_only_autonomous_supervisor_contract(final_status_payload=payload)
    assert result["status"] == supervisor.AUTONOMOUS_BLOCKED_BY_BROKER_GATE
    assert result["readiness_gates"]["broker_gate_cleared"] is False
    assert result["execution_allowed"] is False


def test_policy_gate_blocks_live_autonomy():
    payload = _final_status_payload()
    payload["live_exception_contracts"].pop("approval")
    payload["live_exception_contracts"]["evidence_bundle"]["owner_approval_present"] = False
    result = supervisor.build_long_only_autonomous_supervisor_contract(final_status_payload=payload)
    assert result["status"] == supervisor.AUTONOMOUS_BLOCKED_BY_POLICY
    assert result["readiness_gates"]["policy_gate_cleared"] is False
    assert result["live_autonomy_allowed"] is False


def test_ready_demo_status_still_does_not_execute():
    result = supervisor.build_long_only_autonomous_supervisor_contract(
        final_status_payload=_final_status_payload()
    )
    assert result["status"] == supervisor.AUTONOMOUS_DEMO_READY
    assert result["readiness_gates"]["final_live_for_keeps_ready"] is True
    assert result["can_prepare_demo_plan"] is True
    assert result["execution_allowed"] is False
    assert result["live_autonomy_allowed"] is False


def test_evidence_regression_requires_more_evidence():
    payload = _final_status_payload()
    payload["paper_metrics"]["sample_size"] = 29
    result = supervisor.build_long_only_autonomous_supervisor_contract(final_status_payload=payload)
    assert result["status"] == supervisor.AUTONOMOUS_REQUIRE_MORE_EVIDENCE
    assert "insufficient_sample" in result["blockers"]["evidence"]


def test_required_risk_controls_block_autonomous_readiness():
    mutations = (
        ("kill_switch", lambda payload: payload.__setitem__("kill_switch_proof", None), "missing_kill_switch"),
        ("daily_stop", lambda payload: payload["risk_limits"].pop("daily_loss_cap"), "missing_daily_stop_cap"),
        ("max_loss", lambda payload: payload["risk_limits"].pop("maximum_loss"), "missing_max_loss_cap"),
        ("stop_loss", lambda payload: payload["risk_limits"].pop("stop_loss"), "missing_stop_loss"),
        ("take_profit", lambda payload: payload["risk_limits"].pop("take_profit"), "missing_take_profit"),
    )
    for _name, mutate, blocker in mutations:
        payload = _final_status_payload()
        mutate(payload)
        result = supervisor.build_long_only_autonomous_supervisor_contract(final_status_payload=payload)
        assert result["status"] == supervisor.AUTONOMOUS_BLOCKED_BY_RISK
        assert blocker in result["blockers"]["risk"]


def test_audit_log_and_operator_review_are_required_before_live():
    result = supervisor.build_long_only_autonomous_supervisor_contract(
        final_status_payload=_final_status_payload(),
        supervisor_contract={
            "audit_log_required": False,
            "operator_review_required_before_live": False,
        },
    )
    assert result["status"] == supervisor.AUTONOMOUS_BLOCKED_BY_POLICY
    assert "audit_log_required" in result["blockers"]["policy"]
    assert "operator_review_required_before_live" in result["blockers"]["policy"]
    assert result["can_prepare_demo_plan"] is False


def test_scheduler_daemon_webhook_background_process_are_not_allowed():
    for field in ("scheduler_enabled", "daemon_enabled", "webhook_enabled", "background_execution"):
        result = supervisor.build_long_only_autonomous_supervisor_contract(
            final_status_payload=_final_status_payload(),
            supervisor_contract={field: True},
        )
        assert result["status"] == supervisor.AUTONOMOUS_BLOCKED_BY_POLICY
        assert f"{field}_not_allowed" in result["blockers"]["policy"]
        assert result["safety"][field.replace("_enabled", "")] is False
        assert result["execution_allowed"] is False


def test_supervisor_safety_flags_never_touch_protected_runtime_paths():
    result = supervisor.build_long_only_autonomous_supervisor_contract(
        final_status_payload=_final_status_payload()
    )
    safety = result["safety"]
    assert safety["credential_read"] is False
    assert safety["credential_write"] is False
    assert safety["env_read"] is False
    assert safety["account_id_read"] is False
    assert safety["account_id_write"] is False
    assert safety["network_used"] is False
    assert safety["broker_mutation"] is False
    assert safety["order_execution"] is False
    assert safety["live_trading"] is False
    assert safety["scheduler"] is False
    assert safety["daemon"] is False
    assert safety["webhook"] is False
    assert safety["background_execution"] is False


def test_supervisor_source_has_no_forbidden_runtime_apis():
    source = inspect.getsource(supervisor)
    forbidden = (
        "import requests",
        "from requests",
        "import urllib",
        "from urllib",
        "import socket",
        "from socket",
        "os.environ",
        "getenv(",
        ".env",
        "subprocess",
        "Start-Process",
        "scheduler.",
        "import daemon",
        "from daemon",
        "webhook.post",
        "live_order",
        "broker_sdk",
        "oanda",
    )
    for token in forbidden:
        assert token not in source


def test_contract_inputs_are_not_mutated():
    payload = _final_status_payload()
    original = deepcopy(payload)
    supervisor.build_long_only_autonomous_supervisor_contract(final_status_payload=payload)
    assert payload == original
