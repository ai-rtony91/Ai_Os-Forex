from __future__ import annotations

import ast
import copy
import hashlib
import json

import pytest

from automation.forex_engine import forex_risk_authority_closure_v1 as closure


def _hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_authority_hierarchy_and_inventory_are_deterministic() -> None:
    candidates = closure.authority_candidates()
    first = closure.analyze_authority_candidates(candidates)
    second = closure.analyze_authority_candidates(candidates)
    assert first == second
    assert tuple(first["controls"]) == closure.CONTROLS
    assert first["risk_authority_conflict_count"] == 0
    assert first["tests_examples_create_authority"] is False


def test_tests_examples_and_generated_plans_cannot_create_authority() -> None:
    candidates = closure.authority_candidates()
    candidates.append(
        closure._candidate(
            "MAX_RISK_PER_TRADE",
            99.0,
            "PERCENT",
            "tests/example_only.py",
            "TEST_FIXTURE",
            5,
            "CURRENT",
            "DOCUMENTED",
            "NON_AUTHORITY",
        )
    )
    analysis = closure.analyze_authority_candidates(candidates)
    assert analysis["controls"]["MAX_RISK_PER_TRADE"]["conflict_present"] is False
    assert analysis["controls"]["MAX_RISK_PER_TRADE"]["authoritative_value_count"] == 1
    assert closure.canonical_risk_map(analysis)["MAX_RISK_PER_TRADE"]["value"] == 1.0


def test_conflicting_active_authority_fails_closed() -> None:
    candidates = closure.authority_candidates()
    candidates.append(
        closure._candidate(
            "MAX_RISK_PER_TRADE",
            2.0,
            "PERCENT",
            "authoritative_conflict_fixture",
            "CANONICAL_CODE_CONSTANT",
            3,
            "CURRENT",
            "IMPLEMENTED",
            "EXACT_ACTIVE",
        )
    )
    with pytest.raises(ValueError, match=f"^{closure.RISK_AUTHORITY_CONFLICT}$"):
        closure.analyze_authority_candidates(candidates)


def test_missing_authority_stays_missing_and_disabled_defaults_are_not_values() -> None:
    risk_map = closure.canonical_risk_map()
    for control in ("MAX_DAILY_LOSS", "MAX_OPEN_RISK", "MAX_PAIR_EXPOSURE", "MAX_SPREAD"):
        assert risk_map[control]["status"] == "MISSING_AUTHORITY"
        assert risk_map[control]["value"] is None
    assert risk_map["LOSS_STREAK_LIMIT"]["status"] == "NOT_APPLICABLE"
    assert risk_map["COOLDOWN_AFTER_LOSS"]["status"] == "NOT_APPLICABLE"


def test_proven_active_values_and_drawdown_provenance() -> None:
    risk_map = closure.canonical_risk_map()
    assert risk_map["MAX_RISK_PER_TRADE"]["value"] == 1.0
    assert risk_map["MAX_RISK_PER_TRADE"]["unit"] == "PERCENT"
    assert risk_map["MAX_OPEN_TRADES"]["value"] == 1
    assert risk_map["MAX_DRAWDOWN"]["value"] == 5.0
    assert risk_map["MAX_DRAWDOWN"]["status"] == "PROVEN"
    assert risk_map["KILL_SWITCH"]["value"] is True


def test_daily_loss_behavior_is_correct_but_fixture_does_not_create_authority() -> None:
    proof = closure.risk_governor_synthetic_proof()
    scenarios = proof["scenarios"]
    assert scenarios["daily_loss_below_threshold_allowed"] is True
    assert scenarios["daily_loss_at_threshold_rejected"] is True
    assert scenarios["daily_loss_beyond_threshold_rejected"] is True
    assert proof["daily_loss_fixture_value_creates_authority"] is False


@pytest.mark.parametrize(
    "scenario",
    [
        "per_trade_equal_boundary_allowed",
        "per_trade_excess_rejected",
        "max_open_risk_rejected",
        "max_open_trades_rejected",
        "max_pair_exposure_rejected",
        "spread_rejected",
        "stale_market_data_rejected",
        "cooldown_after_loss_rejected",
        "duplicate_setup_rejected",
        "kill_switch_rejected",
    ],
)
def test_existing_governor_synthetic_contract(scenario: str) -> None:
    proof = closure.risk_governor_synthetic_proof()
    assert proof["scenarios"][scenario] is True
    assert proof["unresolved_limit_fixture_values_create_authority"] is False


def test_governor_proof_is_paper_only_and_non_executing() -> None:
    proof = closure.risk_governor_synthetic_proof()
    assert proof["proof_pass"] is True
    assert proof["paper_only"] is True
    assert proof["network_calls"] is False
    assert proof["broker_calls"] is False
    assert proof["live_execution_enabled"] is False


def test_owner_contract_names_only_genuine_missing_decisions() -> None:
    risk_map = closure.canonical_risk_map()
    required = closure.owner_risk_values_required(risk_map)
    names = {item["control_name"] for item in required}
    assert names == {
        "MAX_DAILY_LOSS",
        "MAX_OPEN_RISK",
        "MAX_PAIR_EXPOSURE",
        "MAX_SPREAD",
        "KILL_SWITCH_CREDENTIAL_REVOKE_PATH",
        "KILL_SWITCH_NOTIFICATION_PATH",
    }
    assert "LOSS_STREAK_LIMIT" not in names
    assert all("value" not in item for item in required)


def test_readiness_recalculation_changes_only_risk_evidence_and_keeps_future_gates() -> None:
    previous = closure.load_packet018a_result()
    original = copy.deepcopy(previous)
    result = closure.recalculate_readiness(previous, closure.canonical_risk_map())
    assert result["readiness_pass_count_before"] == 17
    assert result["readiness_pass_count_after"] == 17
    assert result["readiness_pending_count_before"] == 10
    assert result["readiness_pending_count_after"] == 10
    assert result["readiness_fail_count_before"] == 0
    assert result["readiness_fail_count_after"] == 0
    assert result["loss_streak_configuration_failure_removed_as_optional"] is True
    assert result["paper_evidence_blocker_preserved"] is True
    assert result["demo_evidence_blocker_preserved"] is True
    assert result["human_approval_blocker_preserved"] is True
    assert previous == original


def test_source_contract_and_json_contract_are_standards_compliant() -> None:
    proof = closure.source_contract_proof()
    payload = {
        "source": proof,
        "analysis": closure.analyze_authority_candidates(closure.authority_candidates()),
        "risk_map": closure.canonical_risk_map(),
        "governor": closure.risk_governor_synthetic_proof(),
    }
    assert proof["source_contract_proven"] is True
    json.dumps(payload, allow_nan=False)


def test_paper30_state_count_and_hashes_are_unchanged_by_pure_audit_functions() -> None:
    paths = (
        closure.PAPER30_RUNTIME_PATH,
        closure.PAPER30_LEDGER_PATH,
        closure.PAPER30_STATE_PATH,
    )
    before = [_hash(path) for path in paths]
    ledger = json.loads(closure.PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    state = json.loads(closure.PAPER30_STATE_PATH.read_text(encoding="utf-8"))
    closure.source_contract_proof()
    closure.risk_governor_synthetic_proof()
    closure.recalculate_readiness(closure.load_packet018a_result(), closure.canonical_risk_map())
    after = [_hash(path) for path in paths]
    assert after == before
    assert len(closure.hardening.qualifying_forward_records(ledger)) == 0
    assert state["strategy_config_sha256"] == closure.PAPER30_STRATEGY_CONFIG_SHA256


def test_new_audit_source_has_no_network_broker_or_credential_runtime_imports() -> None:
    source = (closure.ROOT / "automation/forex_engine/forex_risk_authority_closure_v1.py").read_text(
        encoding="utf-8"
    )
    parsed = ast.parse(source)
    forbidden_imports = {"requests", "socket", "urllib", "oanda", "ccxt", "mt5"}
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0].lower() in forbidden_imports for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0].lower() not in forbidden_imports

