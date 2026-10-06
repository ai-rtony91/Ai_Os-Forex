from __future__ import annotations

from pathlib import Path

from automation.forex_engine import readiness_state_recalculation_v1 as readiness_v1


def test_readiness_state_recalculation_v1_top_level_keys_stable():
    payload = readiness_v1.run_readiness_state_recalculation_v1(write_reports=False)

    expected_keys = [
        "mode",
        "packet_id",
        "candidate_id",
        "review_state",
        "promotion_readiness_pct",
        "demo_readiness_pct",
        "live_readiness_pct",
        "forex_completion_pct",
        "evidence_completion_pct",
        "blockers_before",
        "blockers_cleared",
        "blockers_remaining",
        "proof_bundle_consumed",
        "demo_contract_present",
        "one_shot_package_present",
        "readiness_certificate_present",
        "live_readiness_components",
        "live_readiness_components_complete",
        "live_readiness_components_total",
        "review_chain_ready",
        "next_safe_action",
        "safety",
        "live_trading_authorized",
    ]
    for key in expected_keys:
        assert key in payload


def test_readiness_state_recalculation_v1_targets_c1_eur_buy():
    payload = readiness_v1.run_readiness_state_recalculation_v1(write_reports=False)
    assert payload["candidate_id"] == "c1-eur-buy"


def test_readiness_state_recalculation_v1_artifact_presence():
    payload = readiness_v1.run_readiness_state_recalculation_v1(write_reports=False)
    assert payload["proof_bundle_consumed"] is False
    assert isinstance(payload["demo_contract_present"], bool)
    assert isinstance(payload["one_shot_package_present"], bool)
    assert isinstance(payload["readiness_certificate_present"], bool)
    assert payload["live_readiness_components"] == {
        "demo_contract": payload["demo_contract_present"],
        "one_shot_package": payload["one_shot_package_present"],
        "readiness_certificate": payload["readiness_certificate_present"],
    }
    assert payload["live_readiness_components_complete"] == sum(
        int(value) for value in payload["live_readiness_components"].values()
    )
    assert payload["live_readiness_components_total"] == 3


def test_readiness_state_recalculation_v1_live_auth_false():
    payload = readiness_v1.run_readiness_state_recalculation_v1(write_reports=False)
    assert payload["live_trading_authorized"] is False


def test_readiness_state_recalculation_v1_percentages_bounded():
    payload = readiness_v1.run_readiness_state_recalculation_v1(write_reports=False)
    assert 0.0 <= payload["promotion_readiness_pct"] <= 100.0
    assert 0.0 <= payload["demo_readiness_pct"] <= 100.0
    assert 0.0 <= payload["live_readiness_pct"] <= 100.0
    assert 0.0 <= payload["forex_completion_pct"] <= 100.0
    assert 0.0 <= payload["evidence_completion_pct"] <= 100.0


def test_readiness_state_recalculation_v1_blockers_deterministic_and_reportable():
    payload = readiness_v1.run_readiness_state_recalculation_v1(write_reports=False)
    assert payload["blockers_remaining"] == sorted(payload["blockers_remaining"])
    assert isinstance(payload["blockers_before"], list)
    assert isinstance(payload["blockers_cleared"], list)
    assert isinstance(payload["blockers_remaining"], list)


def test_readiness_state_recalculation_v1_next_safe_action_exists():
    payload = readiness_v1.run_readiness_state_recalculation_v1(write_reports=False)
    assert isinstance(payload["next_safe_action"], str)
    assert payload["next_safe_action"] != ""


def test_readiness_state_recalculation_v1_does_not_credit_blocked_bridge_as_demo_ready():
    payload = readiness_v1.run_readiness_state_recalculation_v1(write_reports=False)
    assert payload["bridge_payload"]["candidate_bridge_verdict"] != "DEMO_REVIEW_READY"
    assert payload["proof_bundle_consumed"] is False
    assert payload["demo_readiness_pct"] == 0.0
    assert payload["live_readiness_components_total"] == 3
    assert payload["live_readiness_components_complete"] <= payload["live_readiness_components_total"]


def test_readiness_state_recalculation_v1_write_report_path_under_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = readiness_v1.run_readiness_state_recalculation_v1(write_reports=True)
    report_path = Path(payload["report_path"])
    assert report_path.is_absolute() is False
    assert "Reports/forex_delivery" in str(report_path.as_posix())
