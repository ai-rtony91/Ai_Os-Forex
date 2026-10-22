from __future__ import annotations

import json
from io import StringIO
from typing import Any

import scripts.run_forex_replay_reconciliation_proof_bundle as cli


def _payload() -> dict[str, Any]:
    return {
        "selected_candidate_id": "c1-eur-buy",
        "selected_strategy": "ema_rsi",
        "selected_direction": "LONG",
        "source_candidate_verdict": "PAPER_CONTINUE",
        "source_review_chain_status": "REVIEW_CHAIN_INCOMPLETE",
        "source_journey_final_verdict": "JOURNEY_INCOMPLETE",
        "proof_bundle_status": "PROOF_BUNDLE_COMPLETE",
        "proof_bundle_ready_for_candidate_bridge": False,
        "replay_proof_status": True,
        "reconciliation_proof_status": True,
        "rollback_proof_status": True,
        "demo_validation_proof_status": True,
        "replay_trace_id": "replay:c1-eur-buy:ema_rsi:LONG:PAPER_CONTINUE:REVIEW_CHAIN_INCOMPLETE:JOURNEY_INCOMPLETE",
        "reconciliation_trace_id": "recon:c1-eur-buy:ema_rsi:LONG",
        "rollback_plan_id": "rollback-plan:paper-only-review",
        "demo_validation_trace_id": "demo-validation:PAPER_CONTINUE:REVIEW_CHAIN_INCOMPLETE",
        "unresolved_blockers": {},
        "next_safe_action": "collect_more",
        "safety": {
            "paper_only": True,
            "broker_connected": False,
            "credentials_used": False,
            "account_id_present": False,
            "network_used": False,
            "order_execution": False,
            "demo_trading": False,
            "live_trading": False,
            "live_trading_authorized": False,
        },
    }


def test_human_output_includes_required_fields(monkeypatch: Any) -> None:
    monkeypatch.setattr(cli, "run_replay_reconciliation_proof_bundle", lambda write_reports=True: _payload())
    output = StringIO()
    monkeypatch.setattr(cli.sys, "stdout", output)
    code = cli.main([])
    text = output.getvalue()
    assert "AIOS Forex Replay Reconciliation Proof Bundle" in text
    assert "proof_bundle_status: PROOF_BUNDLE_COMPLETE" in text
    assert code == 0


def test_json_output_parsable(monkeypatch: Any) -> None:
    monkeypatch.setattr(cli, "run_replay_reconciliation_proof_bundle", lambda write_reports=True: _payload())
    output = StringIO()
    monkeypatch.setattr(cli.sys, "stdout", output)
    code = cli.main(["--json"])
    parsed = json.loads(output.getvalue())
    assert code == 0
    assert parsed["selected_candidate_id"] == "c1-eur-buy"
    assert parsed["proof_bundle_status"] == "PROOF_BUNDLE_COMPLETE"
    assert parsed["proof_bundle_ready_for_candidate_bridge"] is False


def test_write_report_calls_bundle_with_report(monkeypatch: Any) -> None:
    captured: dict[str, bool] = {"called": False, "write_reports": None}

    def fake_bundle(*, write_reports: bool = True, journey_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        captured["called"] = True
        captured["write_reports"] = write_reports
        return _payload()

    monkeypatch.setattr(cli, "run_replay_reconciliation_proof_bundle", fake_bundle)
    output = StringIO()
    monkeypatch.setattr(cli.sys, "stdout", output)
    cli.main(["--write-report"])
    assert captured["called"] is True
    assert captured["write_reports"] is True


def test_default_calls_bundle_without_report(monkeypatch: Any) -> None:
    captured: dict[str, bool] = {"called": False, "write_reports": None}

    def fake_bundle(*, write_reports: bool = True, journey_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        captured["called"] = True
        captured["write_reports"] = write_reports
        return _payload()

    monkeypatch.setattr(cli, "run_replay_reconciliation_proof_bundle", fake_bundle)
    output = StringIO()
    monkeypatch.setattr(cli.sys, "stdout", output)
    cli.main([])
    assert captured["called"] is True
    assert captured["write_reports"] is False


def test_exit_code_complete_zero(monkeypatch: Any) -> None:
    monkeypatch.setattr(cli, "run_replay_reconciliation_proof_bundle", lambda write_reports=True: _payload())
    assert cli.main(["--json"]) == 0


def test_exit_code_incomplete_one(monkeypatch: Any) -> None:
    payload = _payload()
    payload["proof_bundle_status"] = "PROOF_BUNDLE_INCOMPLETE"
    payload["proof_bundle_ready_for_candidate_bridge"] = False
    monkeypatch.setattr(cli, "run_replay_reconciliation_proof_bundle", lambda write_reports=True: payload)
    assert cli.main(["--json"]) == 1


def test_exit_code_blocked_two(monkeypatch: Any) -> None:
    payload = _payload()
    payload["proof_bundle_status"] = "PROOF_BUNDLE_BLOCKED"
    payload["proof_bundle_ready_for_candidate_bridge"] = False
    monkeypatch.setattr(cli, "run_replay_reconciliation_proof_bundle", lambda write_reports=True: payload)
    assert cli.main(["--json"]) == 2


def test_repo_root_import_bootstrap(monkeypatch: Any) -> None:
    import runpy
    module = runpy.run_path("scripts/run_forex_replay_reconciliation_proof_bundle.py")
    assert "main" in module


def test_no_live_trading_authorized_true(monkeypatch: Any) -> None:
    payload = _payload()
    monkeypatch.setattr(cli, "run_replay_reconciliation_proof_bundle", lambda write_reports=True: payload)
    output = StringIO()
    monkeypatch.setattr(cli.sys, "stdout", output)
    cli.main(["--json"])
    parsed = json.loads(output.getvalue())
    assert parsed["safety"]["live_trading_authorized"] is False
