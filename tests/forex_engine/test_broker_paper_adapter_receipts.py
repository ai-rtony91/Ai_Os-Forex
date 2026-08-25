from __future__ import annotations

import json

from automation.forex_engine import broker_paper_adapter
from automation.forex_engine import broker_paper_adapter_plan_approval_gate


def _approved_plan_gate_result() -> dict[str, object]:
    approval = broker_paper_adapter_plan_approval_gate.build_example_plan_only_approval()
    return broker_paper_adapter_plan_approval_gate.evaluate_broker_paper_adapter_plan_approval_gate(
        approval=approval
    )


def _paper_demo_verification() -> dict[str, object]:
    return {
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


def _owner_checkpoint() -> dict[str, object]:
    return {
        "paper_demo_execution_phase": True,
        "human_owner_approved": True,
        "approved_by_human_owner": "Anthony Meza",
        "approval_scope": "broker_paper_adapter_implementation_only",
        "mode": "PAPER_ONLY",
        "long_validation_ready": False,
        "live_execution_allowed": False,
        "broker_writes_allowed": False,
    }


def _buy_request(**overrides: object) -> dict[str, object]:
    payload = {
        "request_id": "receipt-request",
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


def test_receipt_chain_links_intent_submission_ack_and_final_without_sensitive_fields() -> None:
    result = broker_paper_adapter.evaluate_broker_paper_adapter(
        request=_buy_request(),
        plan_gate_result=_approved_plan_gate_result(),
        paper_demo_verification=_paper_demo_verification(),
        owner_checkpoint=_owner_checkpoint(),
    )

    intent = result["intent_receipt"]
    submission = result["submission_receipt"]
    acknowledgement = result["acknowledgement_receipt"]
    final = result["final_receipt"]
    bundle = result["evidence_bundle"]

    assert [receipt["receipt_type"] for receipt in bundle["receipt_chain"]] == [
        "intent",
        "submission",
        "acknowledgement",
        "final",
    ]
    assert intent["request_fingerprint"] == submission["request_fingerprint"] == acknowledgement["request_fingerprint"] == final["request_fingerprint"]
    assert intent["intent_id"] == submission["intent_id"] == acknowledgement["intent_id"] == final["intent_id"]
    assert submission["previous_receipt_id"] == intent["receipt_id"]
    assert acknowledgement["previous_receipt_id"] == submission["receipt_id"]
    assert final["previous_receipt_id"] == acknowledgement["receipt_id"]
    assert intent["timestamp_utc"].endswith("Z")
    assert submission["timestamp_utc"].endswith("Z")
    assert acknowledgement["timestamp_utc"].endswith("Z")
    assert final["timestamp_utc"].endswith("Z")
    assert bundle["receipt_chain_complete"] is True
    assert bundle["broker_writes"] == 0
    assert bundle["live_execution_allowed"] is False

    sensitive_tokens = (
        "api_key",
        "access_token",
        "refresh_token",
        "password",
        "private_key",
        "account_id",
        "live_account_id",
        "broker_order_id",
    )
    serialized = json.dumps(bundle).lower()
    for token in sensitive_tokens:
        assert token not in serialized


def test_rejection_receipt_is_emitted_when_live_boundary_is_detected() -> None:
    result = broker_paper_adapter.evaluate_broker_paper_adapter(
        request=_buy_request(request_id="receipt-blocked-request"),
        plan_gate_result=_approved_plan_gate_result(),
        paper_demo_verification={
            **_paper_demo_verification(),
            "endpoint_live": True,
        },
        owner_checkpoint=_owner_checkpoint(),
    )

    assert result["classification"] == "BROKER_PAPER_ADAPTER_BLOCKED"
    assert result["acknowledgement_receipt"] is None
    assert result["rejection_receipt"] is not None
    assert result["rejection_receipt"]["receipt_type"] == "rejection"
    assert result["final_receipt"]["previous_receipt_id"] == result["rejection_receipt"]["receipt_id"]
    assert result["evidence_bundle"]["receipt_chain"][2]["receipt_type"] == "rejection"
    assert result["evidence_bundle"]["receipt_chain"][-1]["final_state"] == "PAPER_DEMO_FINAL_BLOCKED"

