from __future__ import annotations

from typing import Any

from automation.forex_engine import replay_reconciliation_proof_bundle as bundle_module


def _journey_fixture() -> dict[str, Any]:
    return {
        "selected_candidate_id": "c1-eur-buy",
        "selected_strategy": "ema_rsi",
        "selected_direction": "LONG",
        "candidate_demo_review_verdict": "PAPER_CONTINUE",
        "review_chain_status": "REVIEW_CHAIN_INCOMPLETE",
        "final_verdict": "JOURNEY_INCOMPLETE",
        "final_next_safe_action": "collect_more",
        "safety": {
            "paper_only": True,
            "broker_connected": False,
            "credentials_used": False,
            "account_id_present": False,
            "network_used": False,
            "order_execution": False,
            "demo_trading": False,
            "live_trading": False,
        },
        "candidate_demo_review_blockers": ["paper_continue"],
        "review_chain_blockers": ["walk_forward_warning_not_ready"],
    }


def test_stable_top_level_keys(monkeypatch: Any) -> None:
    expected_keys = {
        "mode",
        "packet_id",
        "safety",
        "selected_candidate_id",
        "selected_strategy",
        "selected_direction",
        "source_candidate_verdict",
        "source_review_chain_status",
        "source_journey_final_verdict",
        "proof_bundle_status",
        "proof_bundle_ready_for_candidate_bridge",
        "proofs",
        "unresolved_blockers",
        "next_safe_action",
    }

    def fake_journey(*, write_reports: bool = True) -> dict[str, Any]:
        return _journey_fixture()

    monkeypatch.setattr(bundle_module.review_chain_end_to_end_candidate_journey, "run_review_chain_end_to_end_candidate_journey", fake_journey)
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert expected_keys.issubset(payload.keys())


def test_clean_current_journey_creates_replay_proof(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert payload["replay_proof_status"] is True


def test_clean_current_journey_creates_reconciliation_proof(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert payload["reconciliation_proof_status"] is True


def test_clean_current_journey_creates_rollback_proof(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert payload["rollback_proof_status"] is True


def test_clean_current_journey_creates_demo_validation_proof(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert payload["demo_validation_proof_status"] is True


def test_all_four_proof_statuses_pass_for_clean_paper_only_journey(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert payload["replay_proof_status"] is True
    assert payload["reconciliation_proof_status"] is True
    assert payload["rollback_proof_status"] is True
    assert payload["demo_validation_proof_status"] is True


def test_complete_journey_is_complete_status(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert payload["proof_bundle_status"] == bundle_module.PROOF_BUNDLE_COMPLETE


def test_complete_bundle_ready_flag(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert payload["proof_bundle_ready_for_candidate_bridge"] is True


def test_missing_selected_candidate_id_returns_incomplete(monkeypatch: Any) -> None:
    payload = _journey_fixture()
    payload["selected_candidate_id"] = ""
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: payload,
    )
    bundle = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert bundle["proof_bundle_status"] == bundle_module.PROOF_BUNDLE_INCOMPLETE


def test_unsafe_broker_flag_blocks(monkeypatch: Any) -> None:
    payload = _journey_fixture()
    payload["safety"]["broker_connected"] = True
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: payload,
    )
    bundle = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert bundle["proof_bundle_status"] == bundle_module.PROOF_BUNDLE_BLOCKED


def test_unsafe_network_flag_blocks(monkeypatch: Any) -> None:
    payload = _journey_fixture()
    payload["safety"]["network_used"] = True
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: payload,
    )
    bundle = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert bundle["proof_bundle_status"] == bundle_module.PROOF_BUNDLE_BLOCKED


def test_unsafe_credential_flag_blocks(monkeypatch: Any) -> None:
    payload = _journey_fixture()
    payload["safety"]["credentials_used"] = True
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: payload,
    )
    bundle = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert bundle["proof_bundle_status"] == bundle_module.PROOF_BUNDLE_BLOCKED


def test_live_trading_authorized_stays_false(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert payload["safety"]["live_trading_authorized"] is False


def test_unresolved_non_proof_blockers_preserved(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    blockers = payload["unresolved_blockers"]
    assert "strategy_quality_gaps" in blockers
    assert "demo_contract_gaps" in blockers
    assert "review_package_gaps" in blockers
    assert "human_review_gaps" in blockers
    assert "safety_gaps" in blockers


def test_write_reports_false_has_no_report_path(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert "report_path" not in payload


def test_write_reports_true_returns_report_path(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=True)
    assert isinstance(payload["report_path"], str)
    assert payload["report_path"].replace("\\", "/").startswith("Reports/forex_delivery/")


def test_proof_payload_includes_trace_ids(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        bundle_module.review_chain_end_to_end_candidate_journey,
        "run_review_chain_end_to_end_candidate_journey",
        lambda write_reports=True: _journey_fixture(),
    )
    payload = bundle_module.run_replay_reconciliation_proof_bundle(write_reports=False)
    assert payload["replay_trace_id"].startswith("replay:")
    assert isinstance(payload["reconciliation_trace_id"], str)
    assert payload["rollback_plan_id"].startswith("rollback-plan:")
    assert payload["demo_validation_trace_id"].startswith("demo-validation:")
