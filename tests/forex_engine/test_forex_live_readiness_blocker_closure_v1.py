from __future__ import annotations

import hashlib
import json

import pytest

from automation.forex_engine import forex_live_readiness_blocker_closure_v1 as closure


def _hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _previous() -> dict:
    return closure.load_packet017_result()


def _review_reconciliation(payload: dict) -> dict:
    return closure.review_live_readiness(
        {"allowed": False, "demo_promotion_ready": False},
        {"allowed": False, "mode": "DEMO_RUN_PLAN_ONLY"},
        payload,
        {},
        {"validation_passed": True},
        {"risk_ok": True},
        {"verified": True, "disabled": False},
        human_approval=False,
    )


def _benign_reconciliation_payload() -> dict:
    return {
        "allowed": True,
        "matched": True,
        "match_score": 1.0,
        "mode": "DEMO_RECONCILIATION_ONLY",
        "safety": {
            "credentials": False,
            "broker_write": False,
            "live_trading": False,
            "real_orders": False,
            "network_submit": False,
        },
    }


def test_27_gate_inventory_reconciles_without_disappearing_gate() -> None:
    inventory = closure.inventory_readiness_gates(_previous())
    assert inventory["all_27_gates_accounted_for"] is True
    assert len(inventory["gates"]) == 27
    assert set(inventory["gates"]) == set(closure.hardening.READINESS_GATES)
    assert inventory["status_counts"] == {
        "PASS": 16,
        "FAIL": 1,
        "PENDING": 4,
        "NOT_YET_EVALUABLE": 6,
    }


def test_non_pass_gate_classification_is_complete_and_deterministic() -> None:
    inventory = closure.inventory_readiness_gates(_previous())
    assert inventory["classification_counts"] == {
        closure.CLASS_CLOSEABLE: 1,
        closure.CLASS_FORWARD: 7,
        closure.CLASS_HUMAN: 1,
        closure.CLASS_CONFIG: 2,
        closure.CLASS_UNKNOWN: 0,
    }


def test_daily_loss_threshold_is_not_invented_from_samples_or_ceilings() -> None:
    result = closure.current_daily_loss_authority()
    assert result["daily_loss_limit_found"] is False
    assert result["daily_loss_limit_value"] is None
    assert result["daily_loss_owner_decision_required"] is True
    dispositions = {item["disposition"] for item in result["candidates_reviewed"]}
    assert "SAMPLE_FIXTURE_NOT_OPERATIONAL_CONFIGURATION" in dispositions
    assert "POLICY_CEILING_REQUIRES_CALLER_SUPPLIED_LIMIT" in dispositions


def test_existing_authoritative_daily_loss_configuration_would_be_reused() -> None:
    result = closure.resolve_daily_loss_limit(
        [
            {
                "source": "authoritative_fixture",
                "value": 1.5,
                "unit": "PERCENT",
                "authoritative": True,
                "configured": True,
            }
        ]
    )
    assert result["daily_loss_limit_found"] is True
    assert result["daily_loss_limit_value"] == 1.5
    assert result["daily_loss_limit_source"] == "authoritative_fixture"


def test_kill_switch_declarations_are_not_fabricated() -> None:
    authority = closure.kill_switch_authority_recovery()
    assert authority["credential_revoke_path_authority_found"] is False
    assert authority["notification_path_authority_found"] is False
    result = closure.reevaluate_kill_switch(authority)
    assert result["kill_switch_ready"] is False
    assert "kill_switch_control_failed:credential_revoke_path_declared" in result[
        "blocked_reasons"
    ]
    assert "kill_switch_control_failed:notification_path_declared" in result[
        "blocked_reasons"
    ]


def test_synthetic_demo_reconciliation_matches_all_required_fields() -> None:
    proof = closure.synthetic_demo_reconciliation_proof()
    result = proof["result"]
    assert proof["engine_ready"] is True
    assert proof["synthetic_match_pass"] is True
    assert result["matched"] is True
    assert result["pair_match"] is True
    assert result["side_match"] is True
    assert result["units_match"] is True
    assert result["price_within_tolerance"] is True
    assert result["stop_loss_match"] is True
    assert result["take_profit_match"] is True
    assert result["position_seen"] is True
    assert result["order_seen"] is True
    assert proof["real_demo_evidence_complete"] is False


def test_stale_synthetic_demo_reconciliation_fails_closed() -> None:
    proof = closure.synthetic_demo_reconciliation_proof(stale=True)
    assert proof["stale_rejected"] is True
    assert proof["result"]["allowed"] is False
    assert proof["result"]["stale_data"] is True


def test_credentials_false_regression_is_benign_after_minimal_projection() -> None:
    original = _benign_reconciliation_payload()
    before = json.loads(json.dumps(original))
    raw_review = _review_reconciliation(original)
    assert "credentials_present" in raw_review["blocked_reasons"]

    projected = closure.minimal_reconciliation_review_view(original)
    repaired_review = _review_reconciliation(projected)
    assert "credentials_present" not in repaired_review["blocked_reasons"]
    assert repaired_review["reconciliation_ok"] is True
    assert original == before
    assert projected == {
        "allowed": True,
        "matched": True,
        "match_score": 1.0,
        "mode": "DEMO_RECONCILIATION_ONLY",
    }


@pytest.mark.parametrize(
    "unsafe_field",
    [
        {"credentials": True},
        {"credential_marker": "SANITIZED_PRESENT_MARKER"},
        {"account_id": "SANITIZED_PRESENT_MARKER"},
        {"broker_write": True},
        {"order_submit": True},
        {"live_trading": True},
        {"network_submit": True},
    ],
)
def test_genuine_unsafe_reconciliation_content_fails_closed_before_projection(
    unsafe_field: dict,
) -> None:
    payload = _benign_reconciliation_payload()
    payload.update(unsafe_field)
    before = json.loads(json.dumps(payload))
    with pytest.raises(ValueError, match=f"^{closure.RECONCILIATION_UNSAFE_CONTENT}$"):
        closure.minimal_reconciliation_review_view(payload)
    assert payload == before


def test_projection_does_not_upgrade_failed_reconciliation() -> None:
    payload = _benign_reconciliation_payload()
    payload.update({"allowed": False, "matched": False, "match_score": 0.0})
    projected = closure.minimal_reconciliation_review_view(payload)
    assert projected["allowed"] is False
    assert projected["matched"] is False
    assert projected["match_score"] == 0.0
    reviewed = _review_reconciliation(projected)
    assert reviewed["reconciliation_ok"] is False
    assert "reconciliation_missing" in reviewed["blocked_reasons"]


def test_ledger_extension_projection_contains_required_fields_without_runtime_change() -> None:
    before = _hash(closure.PAPER30_RUNTIME_PATH)
    projection = closure.ledger_schema_projection(_previous())
    assert projection["paper30_ledger_schema_extension_ready"] is True
    assert set(closure.REQUIRED_PROJECTED_LEDGER_FIELDS).issubset(
        projection["projected_schema_fields"]
    )
    assert projection["current_runtime_missing_fields"] == [
        "market_data_freshness",
        "shadow_5r_outcomes",
    ]
    assert projection["current_ledger_already_contains_extension"] is False
    assert projection["runtime_modified"] is False
    assert projection["strategy_semantics_changed"] is False
    assert _hash(closure.PAPER30_RUNTIME_PATH) == before


def test_current_ledger_state_and_forward_count_remain_unchanged_by_pure_proofs() -> None:
    paths = (
        closure.PAPER30_RUNTIME_PATH,
        closure.PAPER30_LEDGER_PATH,
        closure.PAPER30_STATE_PATH,
    )
    before = [_hash(path) for path in paths]
    ledger_before = json.loads(closure.PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    closure.synthetic_demo_reconciliation_proof()
    closure.ledger_schema_projection(_previous())
    after = [_hash(path) for path in paths]
    ledger_after = json.loads(closure.PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    assert after == before
    assert ledger_after == ledger_before
    assert len(closure.hardening.qualifying_forward_records(ledger_after)) == 0


def test_risk_configuration_map_is_deterministic_and_honest() -> None:
    daily = closure.current_daily_loss_authority()
    kill = closure.reevaluate_kill_switch(closure.kill_switch_authority_recovery())
    first = closure.risk_configuration_map(daily, kill)
    second = closure.risk_configuration_map(daily, kill)
    assert first == second
    assert first["MAX_DRAWDOWN_LIMIT"]["status"] == "PROVEN"
    assert first["DAILY_LOSS_LIMIT"]["status"] == "MISSING_AUTHORITY"
    assert first["LOSS_STREAK_LIMIT"]["status"] == "MISSING_AUTHORITY"
    assert first["KILL_SWITCH"]["status"] == "MISSING_AUTHORITY"


def test_reevaluated_matrix_keeps_all_gates_and_closes_projection_failure() -> None:
    previous = _previous()
    daily = closure.current_daily_loss_authority()
    kill = closure.reevaluate_kill_switch(closure.kill_switch_authority_recovery())
    demo = closure.synthetic_demo_reconciliation_proof()
    projection = closure.ledger_schema_projection(previous)
    result = closure.reevaluate_matrix(
        previous, projection=projection, demo=demo, kill=kill, daily=daily
    )
    assert set(result["matrix"]) == set(previous["readiness_matrix"])
    assert result["status_counts"] == {
        "PASS": 17,
        "FAIL": 0,
        "PENDING": 4,
        "NOT_YET_EVALUABLE": 6,
    }
    assert result["matrix"]["AUDIT_LEDGER"]["status"] == "PASS"
    assert result["matrix"]["DAILY_LOSS_STOP"]["status"] == "PENDING"
    assert result["matrix"]["KILL_SWITCH"]["status"] == "PENDING"


def test_live_review_is_review_only_and_keeps_real_evidence_blockers() -> None:
    daily = closure.current_daily_loss_authority()
    kill = closure.reevaluate_kill_switch(closure.kill_switch_authority_recovery())
    demo = closure.synthetic_demo_reconciliation_proof()
    result = closure.live_readiness_reevaluation(demo=demo, kill=kill, daily=daily)
    assert result["decision"] == "REVIEW_ONLY"
    assert result["allowed"] is False
    assert result["live_ready"] is False
    assert result["metadata"]["human_approval"] is False
    assert result["reconciliation_ok"] is True
    assert "reconciliation_missing" not in result["blocked_reasons"]
    assert "paper_evidence_insufficient" in result["blocked_reasons"]
    assert "demo_evidence_insufficient" in result["blocked_reasons"]
    assert "credentials_present" not in result["blocked_reasons"]


def test_report_contract_keeps_live_execution_and_forward_credit_false() -> None:
    ledger = json.loads(closure.PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    state = json.loads(closure.PAPER30_STATE_PATH.read_text(encoding="utf-8"))
    proof = closure.reconciliation_projection_regression_proof()
    assert len(closure.hardening.qualifying_forward_records(ledger)) == 0
    assert state["strategy_config_sha256"] == closure.PAPER30_STRATEGY_CONFIG_SHA256
    assert all(proof.values())
    json.dumps(proof, allow_nan=False)
