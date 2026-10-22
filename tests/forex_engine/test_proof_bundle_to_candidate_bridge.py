from __future__ import annotations

from pathlib import Path

from automation.forex_engine import canonical_demo_review_evidence_bridge as canonical_bridge
from automation.forex_engine import proof_bundle_to_candidate_bridge as module
from automation.forex_engine import replay_reconciliation_proof_bundle


def _proof_payload() -> dict:
    return {
        "mode": "FOREX_REPLAY_RECONCILIATION_PROOF_BUNDLE_V1",
        "packet_id": "AIOS_REPLAY_RECONCILIATION_TEST",
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
        "selected_candidate_id": "c1-eur-buy",
        "selected_strategy": "mean_reversion_gap",
        "selected_direction": "LONG",
        "source_candidate_verdict": canonical_bridge.PAPER_CONTINUE,
        "source_review_chain_status": "REVIEW_CHAIN_INCOMPLETE",
        "proof_bundle_status": replay_reconciliation_proof_bundle.PROOF_BUNDLE_COMPLETE,
        "proofs": {
            "replay_proof": {"status": True},
            "reconciliation_proof": {"status": True},
            "rollback_proof": {"status": True},
            "demo_validation_proof": {"status": True},
        },
    }


def _candidate_payload() -> dict:
    return {
        "mode": "FOREX_CANDIDATE_INTAKE_TO_DEMO_REVIEW_BRIDGE_V1",
        "packet_id": "AIOS_FOREX_CANDIDATE_INTAKE_DEMO_REVIEW_BRIDGE_V1",
        "safety": {},
        "selected_candidate_id": "c1-eur-buy",
        "selected_strategy": "mean_reversion_gap",
        "selected_direction": "LONG",
        "normalized_candidate": {
            "candidate_id": "c1-eur-buy",
            "strategy": "mean_reversion_gap",
            "pair": "EURUSD",
            "direction": "LONG",
            "expectancy": 0.18,
            "profit_factor": 1.36,
            "max_drawdown": 0.08,
            "win_rate": 0.47,
            "sample_size": 58,
            "walk_forward_status": "pass",
            "paper_evidence_status": "passed",
            "mitigation_status": "not_worse",
        },
        "demo_review_bundle": {},
        "verdict": canonical_bridge.PAPER_CONTINUE,
        "blockers": [],
        "next_safe_action": "",
    }


def _install_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "automation.forex_engine.replay_reconciliation_proof_bundle.run_replay_reconciliation_proof_bundle",
        lambda *, write_reports=True: _proof_payload(),
    )
    monkeypatch.setattr(
        "automation.forex_engine.candidate_intake_demo_review_bridge.run_candidate_intake_demo_review_bridge",
        lambda write_reports=True: _candidate_payload(),
    )


def test_stable_top_level_keys(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    required = {
        "mode",
        "packet_id",
        "safety",
        "selected_candidate_id",
        "selected_strategy",
        "selected_direction",
        "source_proof_bundle_status",
        "source_candidate_verdict",
        "candidate_bridge_verdict",
        "proof_bundle_ready_for_candidate_bridge",
        "enriched_candidate",
        "canonical_review_bundle",
        "closed_blockers",
        "remaining_blockers",
        "strategy_quality_gaps",
        "demo_contract_gaps",
        "review_package_gaps",
        "human_review_gaps",
        "safety_gaps",
        "next_safe_action",
    }
    assert required.issubset(payload.keys())


def test_complete_proof_bundle_creates_replay_proof(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert payload["enriched_candidate"]["replay_proof"] is True


def test_complete_proof_bundle_creates_reconciliation_proof(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert payload["enriched_candidate"]["reconciliation_proof"] is True


def test_complete_proof_bundle_creates_rollback_proof(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert payload["enriched_candidate"]["rollback_proof"] is True


def test_complete_proof_bundle_creates_demo_validation_proof(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert payload["enriched_candidate"]["demo_validation_proof"] is True


def test_safety_clean_bundle_creates_kill_switch_and_risk(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert payload["enriched_candidate"]["kill_switch_proof"] is True
    assert payload["enriched_candidate"]["risk_proof"] is True


def test_enriched_candidate_includes_freshness_proof(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert payload["enriched_candidate"]["freshness_proof"] == {"age_hours": 1}


def test_closed_blockers_includes_missing_replay_proof(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert "missing_replay_proof" in payload["closed_blockers"]


def test_closed_blockers_includes_missing_reconciliation_proof(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert "missing_reconciliation_proof" in payload["closed_blockers"]


def test_closed_blockers_includes_missing_rollback_proof(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert "missing_rollback_proof" in payload["closed_blockers"]


def test_closed_blockers_includes_missing_demo_validation_proof(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert "missing_demo_validation_proof" in payload["closed_blockers"]


def test_strategy_quality_blockers_are_preserved(monkeypatch):
    _install_payload(monkeypatch)
    monkeypatch.setattr(
        "automation.forex_engine.candidate_intake_demo_review_bridge.run_candidate_intake_demo_review_bridge",
        lambda write_reports=True: {
            **_candidate_payload(),
            "normalized_candidate": {
                **_candidate_payload()["normalized_candidate"],
                "walk_forward_status": "failed",
            },
        },
    )
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert any(blocker == "walk_forward_failed" for blocker in payload["remaining_blockers"])


def test_safety_gap_causes_blocked_payload(monkeypatch):
    payload = _proof_payload()
    payload["safety"]["broker_connected"] = True
    _install_payload(monkeypatch)
    monkeypatch.setattr(
        "automation.forex_engine.replay_reconciliation_proof_bundle.run_replay_reconciliation_proof_bundle",
        lambda *, write_reports=True: payload,
    )
    result = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert result["candidate_bridge_verdict"] == module.BLOCKED_INCOMPLETE_EVIDENCE
    assert result["safety_gaps"]


def test_blocked_bridge_does_not_mark_proof_bundle_ready():
    result = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert result["candidate_bridge_verdict"] != module.DEMO_REVIEW_READY
    assert result["proof_bundle_ready_for_candidate_bridge"] is False


def test_write_reports_false_returns_no_report_path(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert "report_path" not in payload


def test_write_reports_true_returns_report_path(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=True)
    path = payload.get("report_path")
    assert isinstance(path, Path)
    assert path.is_file()
    assert str(path).replace("\\", "/").startswith("Reports/forex_delivery/")


def test_canonical_review_bundle_has_verdict_blockers_next_safe_action(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    bundle = payload["canonical_review_bundle"]
    assert "verdict" in bundle
    assert "blockers" in bundle
    assert "next_safe_action" in bundle


def test_live_trading_authorized_remains_false(monkeypatch):
    _install_payload(monkeypatch)
    payload = module.run_proof_bundle_to_candidate_bridge(write_reports=False)
    assert payload["safety"]["live_trading_authorized"] is False
