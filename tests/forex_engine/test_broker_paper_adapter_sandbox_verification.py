from __future__ import annotations

from automation.forex_engine import broker_paper_adapter
from automation.forex_engine import broker_paper_adapter_plan_approval_gate


def _approved_plan_gate_result() -> dict[str, object]:
    approval = broker_paper_adapter_plan_approval_gate.build_example_plan_only_approval()
    return broker_paper_adapter_plan_approval_gate.evaluate_broker_paper_adapter_plan_approval_gate(
        approval=approval
    )


def _paper_demo_verification(**overrides: object) -> dict[str, object]:
    payload = {
        "paper_only": True,
        "environment": "PAPER",
        "broker_environment": "paper",
        "endpoint_live": False,
        "broker_endpoint_live": False,
        "account_mode": "PAPER_DEMO",
        "verified_by_human_owner": True,
        "live_execution_allowed": False,
        "live_broker_writes_allowed": False,
        "broker_writes_allowed": False,
        "broker_sdk_allowed": False,
        "network_api_allowed": False,
        "credentials_allowed": False,
    }
    payload.update(overrides)
    return payload


def _owner_checkpoint(**overrides: object) -> dict[str, object]:
    payload = {
        "paper_demo_execution_phase": True,
        "human_owner_approved": True,
        "approved_by_human_owner": "Anthony Meza",
        "approval_scope": "broker_paper_adapter_implementation_only",
        "mode": "PAPER_ONLY",
        "long_validation_ready": False,
        "live_execution_allowed": False,
        "broker_writes_allowed": False,
    }
    payload.update(overrides)
    return payload


def _buy_request(**overrides: object) -> dict[str, object]:
    payload = {
        "request_id": "sandbox-request",
        "symbol": "EUR_USD",
        "side": "BUY",
        "quantity_units": 1,
        "stop_loss_pips": 8.0,
        "take_profit_pips": 12.0,
        "max_loss_usd": 10.0,
        "paper_only": True,
        "live_execution_allowed": False,
        "paper_broker_writes_allowed": False,
        "broker_writes_allowed": False,
        "broker_sdk_allowed": False,
        "network_api_allowed": False,
        "credentials_allowed": False,
        "dry_run": True,
        "long_validation_ready": False,
    }
    payload.update(overrides)
    return payload


def test_boundary_summary_blocks_live_execution_and_broker_writes() -> None:
    boundary = broker_paper_adapter.broker_paper_adapter_boundary_summary()

    assert boundary["paper_only"] is True
    assert boundary["paper_demo_only"] is True
    assert boundary["plan_gate_required"] is True
    assert boundary["paper_demo_verification_required"] is True
    assert boundary["owner_checkpoint_required"] is True
    assert boundary["receipt_chain_required"] is True
    assert boundary["broker_integration_active"] is False
    assert boundary["broker_sdk_allowed"] is False
    assert boundary["network_allowed"] is False
    assert boundary["network_api_allowed"] is False
    assert boundary["credentials_allowed"] is False
    assert boundary["paper_broker_writes_allowed"] is False
    assert boundary["live_broker_writes_allowed"] is False
    assert boundary["broker_orders_allowed"] is False
    assert boundary["live_execution_allowed"] is False
    assert boundary["execution_allowed"] is False
    assert boundary["broker_request_sent"] is False
    assert boundary["network_used"] is False
    assert boundary["broker_writes"] == 0
    assert boundary["live_ready"] is False
    assert boundary["live_trade_ready"] is False
    assert boundary["real_order_ready"] is False


def test_missing_plan_gate_or_verification_blocks_progression() -> None:
    blocked = broker_paper_adapter.evaluate_broker_paper_adapter(
        request=_buy_request(),
        plan_gate_result={"classification": "WATCHLIST", "broker_paper_adapter_plan_approval_gate_ready": False},
        paper_demo_verification={},
        owner_checkpoint={},
    )

    assert blocked["classification"] == "BROKER_PAPER_ADAPTER_BLOCKED"
    assert "plan_gate_not_ready" in blocked["blockers"]
    assert "paper_demo_verification_not_ready" in blocked["blockers"]
    assert "owner_checkpoint_not_ready" in blocked["blockers"]
    assert blocked["broker_writes"] == 0
    assert blocked["live_execution_allowed"] is False
    assert blocked["broker_request_sent"] is False
    assert blocked["rejection_receipt"] is not None
    assert blocked["final_state"] == "PAPER_DEMO_FINAL_BLOCKED"


def test_ready_path_requires_plan_gate_and_sandbox_verification_and_owner_checkpoint() -> None:
    ready = broker_paper_adapter.evaluate_broker_paper_adapter(
        request=_buy_request(),
        plan_gate_result=_approved_plan_gate_result(),
        paper_demo_verification=_paper_demo_verification(),
        owner_checkpoint=_owner_checkpoint(),
    )

    assert ready["classification"] == "BROKER_PAPER_ADAPTER_READY"
    assert ready["plan_gate_ready"] is True
    assert ready["paper_demo_verification_ready"] is True
    assert ready["owner_checkpoint_ready"] is True
    assert ready["paper_only"] is True
    assert ready["live_execution_allowed"] is False
    assert ready["broker_writes"] == 0
    assert ready["final_state"] == "PAPER_DEMO_FINAL_READY"


def test_live_endpoint_verification_is_rejected_even_when_plan_gate_is_ready() -> None:
    blocked = broker_paper_adapter.evaluate_broker_paper_adapter(
        request=_buy_request(request_id="live-verification-request"),
        plan_gate_result=_approved_plan_gate_result(),
        paper_demo_verification=_paper_demo_verification(endpoint_live=True),
        owner_checkpoint=_owner_checkpoint(),
    )

    assert blocked["classification"] == "BROKER_PAPER_ADAPTER_BLOCKED"
    assert blocked["paper_demo_verification_ready"] is False
    assert "paper_demo_verification_not_ready" in blocked["blockers"]
    assert blocked["rejection_receipt"] is not None
    assert blocked["acknowledgement_receipt"] is None
    assert blocked["broker_writes"] == 0
    assert blocked["live_execution_allowed"] is False
    assert blocked["final_state"] == "PAPER_DEMO_FINAL_BLOCKED"
