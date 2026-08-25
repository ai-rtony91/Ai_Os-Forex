from __future__ import annotations

import json
from pathlib import Path

from automation.forex_engine import broker_paper_adapter
from automation.forex_engine import broker_paper_adapter_plan_approval_gate


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "automation" / "forex_engine" / "broker_paper_adapter.py"
DEMO_PATH = REPO_ROOT / "automation" / "forex_engine" / "run_broker_paper_adapter_demo.py"
DOC_PATH = (
    REPO_ROOT
    / "docs"
    / "trading_lab"
    / "AIOS_FOREX_BUILDER_BROKER_PAPER_ADAPTER_IMPLEMENTATION_PACKET_V1.md"
)


def _approved_plan_gate_result() -> dict[str, object]:
    approval = broker_paper_adapter_plan_approval_gate.build_example_plan_only_approval()
    return broker_paper_adapter_plan_approval_gate.evaluate_broker_paper_adapter_plan_approval_gate(
        approval=approval
    )


def _paper_demo_verification(*, live_endpoint: bool = False) -> dict[str, object]:
    return {
        "paper_only": True,
        "environment": "PAPER",
        "broker_environment": "paper",
        "endpoint_live": live_endpoint,
        "broker_endpoint_live": live_endpoint,
        "account_mode": "PAPER_DEMO",
        "verified_by_human_owner": True,
        "live_execution_allowed": False,
        "live_broker_writes_allowed": False,
        "broker_writes_allowed": False,
        "broker_sdk_allowed": False,
        "network_api_allowed": False,
        "credentials_allowed": False,
    }


def _owner_checkpoint(*, long_validation_ready: bool = False) -> dict[str, object]:
    return {
        "paper_demo_execution_phase": True,
        "human_owner_approved": True,
        "approved_by_human_owner": "Anthony Meza",
        "approval_scope": "broker_paper_adapter_implementation_only",
        "mode": "PAPER_ONLY",
        "long_validation_ready": long_validation_ready,
        "live_execution_allowed": False,
        "broker_writes_allowed": False,
    }


def _buy_request(**overrides: object) -> dict[str, object]:
    payload = {
        "request_id": "buy-request",
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


def test_contract_doc_and_module_exist_and_block_live_capabilities() -> None:
    contract = broker_paper_adapter.build_broker_paper_adapter_contract()

    assert DOC_PATH.exists()
    assert MODULE_PATH.exists()
    assert contract["mode"] == "PAPER_ONLY_BROKER_PAPER_ADAPTER"
    assert contract["paper_only"] is True
    assert contract["plan_gate_required"] is True
    assert contract["paper_demo_verification_required"] is True
    assert contract["owner_checkpoint_required"] is True
    assert contract["receipt_chain_required"] is True
    assert contract["broker_writes"] == 0
    assert contract["supported_directions"] == ["BUY", "SHORT", "LONG"]
    assert contract["supported_instruments"] == ["EUR_USD", "GBP_USD", "USD_JPY"]
    for field in (
        "broker_sdk_allowed",
        "network_api_allowed",
        "credentials_allowed",
        "env_secret_read_allowed",
        "paper_broker_writes_allowed",
        "live_broker_writes_allowed",
        "broker_orders_allowed",
        "live_execution_allowed",
        "execution_allowed",
        "broker_request_sent",
        "network_used",
        "credentials_used",
        "live_ready",
        "live_trade_ready",
        "real_order_ready",
    ):
        assert contract[field] is False


def test_buy_request_produces_receipt_chain_without_broker_writes() -> None:
    result = broker_paper_adapter.evaluate_broker_paper_adapter(
        request=_buy_request(),
        plan_gate_result=_approved_plan_gate_result(),
        paper_demo_verification=_paper_demo_verification(),
        owner_checkpoint=_owner_checkpoint(),
    )
    summary = broker_paper_adapter.summarize_broker_paper_adapter(result)

    assert result["classification"] == "BROKER_PAPER_ADAPTER_READY"
    assert summary["classification"] == "BROKER_PAPER_ADAPTER_READY"
    assert result["broker_paper_adapter_ready"] is True
    assert result["paper_only"] is True
    assert result["live_execution_allowed"] is False
    assert result["paper_broker_writes_allowed"] is False
    assert result["live_broker_writes_allowed"] is False
    assert result["broker_writes"] == 0
    assert result["broker_request_sent"] is False
    assert result["submission_state"] == "PAPER_DEMO_SUBMISSION_RECORDED"
    assert result["acknowledgement_state"] == "PAPER_DEMO_ACKNOWLEDGED"
    assert result["rejection_receipt"] is None
    assert result["error_receipt"] is None
    assert result["final_state"] == "PAPER_DEMO_FINAL_READY"
    assert result["final_receipt"]["final_state"] == "PAPER_DEMO_FINAL_READY"
    assert result["evidence_bundle"]["receipt_chain_complete"] is True
    assert [receipt["receipt_type"] for receipt in result["evidence_bundle"]["receipt_chain"]] == [
        "intent",
        "submission",
        "acknowledgement",
        "final",
    ]
    assert summary["next_safe_packet"] == "FOREX-LONG-RUN-PAPER-SUPERVISOR"
    assert summary["next_safe_action"] == "RUN_PAPER_LONG_FORM_VALIDATION_CYCLE"


def test_short_request_normalizes_and_stays_paper_only() -> None:
    result = broker_paper_adapter.evaluate_broker_paper_adapter(
        request=_buy_request(side="SELL", request_id="short-request"),
        plan_gate_result=_approved_plan_gate_result(),
        paper_demo_verification=_paper_demo_verification(),
        owner_checkpoint=_owner_checkpoint(),
    )

    assert result["classification"] == "BROKER_PAPER_ADAPTER_READY"
    assert result["normalized_request"]["side"] == "SHORT"
    assert result["paper_only"] is True
    assert result["live_execution_allowed"] is False
    assert result["broker_writes"] == 0
    assert result["final_state"] == "PAPER_DEMO_FINAL_READY"


def test_long_request_requires_validation_and_never_executes() -> None:
    result = broker_paper_adapter.evaluate_broker_paper_adapter(
        request=_buy_request(side="LONG", request_id="long-request"),
        plan_gate_result=_approved_plan_gate_result(),
        paper_demo_verification=_paper_demo_verification(),
        owner_checkpoint=_owner_checkpoint(),
    )

    assert result["classification"] == "BROKER_PAPER_ADAPTER_BLOCKED"
    assert result["normalized_request"]["side"] == "LONG"
    assert result["long_validation_pending"] is True
    assert result["submission_state"] == "PAPER_DEMO_SUBMISSION_BLOCKED"
    assert result["acknowledgement_receipt"] is None
    assert result["rejection_receipt"] is not None
    assert "long_validation_required" in result["blockers"]
    assert result["broker_request_sent"] is False
    assert result["broker_writes"] == 0
    assert result["final_state"] == "PAPER_DEMO_FINAL_BLOCKED"


def test_live_boundary_or_credentials_in_verification_fail_closed() -> None:
    result = broker_paper_adapter.evaluate_broker_paper_adapter(
        request=_buy_request(request_id="live-boundary-request"),
        plan_gate_result=_approved_plan_gate_result(),
        paper_demo_verification=_paper_demo_verification(live_endpoint=True),
        owner_checkpoint=_owner_checkpoint(),
    )

    assert result["classification"] == "BROKER_PAPER_ADAPTER_BLOCKED"
    assert result["paper_demo_verification_ready"] is False
    assert "paper_demo_verification_not_ready" in result["blockers"]
    assert result["rejection_receipt"] is not None
    assert result["acknowledgement_receipt"] is None
    assert result["live_execution_allowed"] is False
    assert result["broker_writes"] == 0


def test_demo_imports_and_prints_required_lines(capsys) -> None:
    from automation.forex_engine import run_broker_paper_adapter_demo

    assert run_broker_paper_adapter_demo.main([]) == 0
    output = capsys.readouterr().out

    assert "AIOS Broker-Paper Adapter Demo" in output
    assert "Mode: PAPER_ONLY_BROKER_PAPER_ADAPTER" in output
    assert "Classification: BROKER_PAPER_ADAPTER_READY" in output
    assert "Paper only: true" in output
    assert "Live execution allowed: false" in output
    assert "Paper broker writes allowed: false" in output
    assert "Live broker writes allowed: false" in output
    assert "Broker writes: 0" in output
    assert "Broker request sent: false" in output
    assert "Next safe action: RUN_PAPER_LONG_FORM_VALIDATION_CYCLE" in output
    assert "Safety: paper/demo only; no live execution, no broker writes, no live credentials." in output


def test_modules_have_no_forbidden_imports_or_execution_calls() -> None:
    for path in (MODULE_PATH, DEMO_PATH):
        source = path.read_text(encoding="utf-8").lower()
        import_lines = "\n".join(
            line.strip()
            for line in source.splitlines()
            if line.startswith("import ") or line.startswith("from ")
        )

        for forbidden_import in ("requests", "socket", "urllib", "subprocess", "dotenv", "mt5", "ibkr"):
            assert forbidden_import not in import_lines
        for line in import_lines.splitlines():
            assert not line.startswith("import broker")
            assert not line.startswith("from broker")
            assert not line.startswith("import oanda")
            assert not line.startswith("from oanda")
        for forbidden_call in (
            "os.environ",
            "getenv",
            "open(",
            "write_text(",
            "write_bytes(",
            "start-process",
            "schedule.every",
            "daemon.daemoncontext",
        ):
            assert forbidden_call not in source

