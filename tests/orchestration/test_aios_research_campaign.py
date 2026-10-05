from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest
import automation.orchestration.research_campaign.aios_research_campaign as campaign_module

try:
    from automation.orchestration.research_campaign.aios_research_campaign import (
        CampaignCheckpointError,
        CampaignSpec,
        CampaignValidationError,
        Experiment,
        ExperimentOutcome,
        evaluate_edge_gate,
        experiment_fingerprint,
        load_checkpoint,
        run_campaign_cycle,
        score_evidence,
        write_checkpoint,
    )
except ImportError:
    CampaignCheckpointError = None  # type: ignore[assignment]
    CampaignSpec = None  # type: ignore[assignment]
    CampaignValidationError = None  # type: ignore[assignment]
    Experiment = None  # type: ignore[assignment]
    ExperimentOutcome = None  # type: ignore[assignment]
    evaluate_edge_gate = None  # type: ignore[assignment]
    experiment_fingerprint = None  # type: ignore[assignment]
    load_checkpoint = None  # type: ignore[assignment]
    run_campaign_cycle = None  # type: ignore[assignment]
    score_evidence = None  # type: ignore[assignment]
    write_checkpoint = None  # type: ignore[assignment]


def _campaign_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "campaign_id": "forex-first-v1",
        "campaign_version": "1",
        "market_lanes": ["FOREX_EURUSD_PRIMARY", "CME_INDEX_FUTURES_COMPARISON"],
        "experiment_budget": 4,
        "edge_gates": {"min_oos_trade_count": 100},
        "freshness": {"progress_max_age_seconds": 600},
    }
    payload.update(overrides)
    return payload


def _experiment_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "experiment_id": "display-a",
        "market_lane": "FOREX_EURUSD_PRIMARY",
        "strategy_family": "MOMENTUM",
        "instrument": "EUR_USD",
        "session_window": "LONDON_NY_OVERLAP",
        "stage": "CHEAP_SCREEN",
        "data_capability": {
            "pinned": True,
            "source_id": "fixture-forex",
            "contract_definition_id": "EURUSD-2026",
            "calendar_id": "forex-eurusd",
            "pip_value": 10.0,
            "cost_model_id": "fixture-costs-v1",
        },
        "cost_scenario": "BASELINE",
        "parameter_fingerprint": "momentum-v1",
        "expected_evidence_version": "1",
    }
    payload.update(overrides)
    return payload


NOW = "2026-10-05T12:00:00Z"


def _campaign_with_catalog(
    catalog: list[dict[str, Any]], **overrides: Any
) -> CampaignSpec:
    return CampaignSpec.from_dict(
        _campaign_payload(experiment_catalog=catalog, **overrides)
    )


def _outcome_for(
    experiment: Experiment, status: str = "ADVANCE", **overrides: Any
) -> ExperimentOutcome:
    payload = {
        "experiment_fingerprint": experiment_fingerprint(experiment),
        "stage": experiment.stage,
        "status": status,
        "reason": "fixture",
        "evidence_version": experiment.expected_evidence_version,
        "completed_at_utc": NOW,
    }
    payload.update(overrides)
    return ExperimentOutcome(**payload)


def _checkpoint_for(
    spec: CampaignSpec,
    decision: Any,
    outcomes: list[ExperimentOutcome],
) -> dict[str, Any]:
    return campaign_module.build_checkpoint(spec, outcomes, decision, NOW)


def _require_contract() -> None:
    assert CampaignSpec is not None, "research campaign contract is not implemented"
    assert CampaignValidationError is not None, "research campaign error type is not implemented"
    assert Experiment is not None, "experiment contract is not implemented"
    assert experiment_fingerprint is not None, "experiment fingerprint function is not implemented"


def _require_scorecard() -> None:
    _require_contract()
    assert score_evidence is not None, "evidence scorecard is not implemented"
    assert evaluate_edge_gate is not None, "edge gate is not implemented"


def _require_router() -> None:
    _require_scorecard()
    assert ExperimentOutcome is not None, "experiment outcome contract is not implemented"
    assert run_campaign_cycle is not None, "campaign router is not implemented"


def _require_checkpoint() -> None:
    _require_router()
    assert CampaignCheckpointError is not None, "checkpoint error type is not implemented"
    assert load_checkpoint is not None, "checkpoint loader is not implemented"
    assert write_checkpoint is not None, "checkpoint writer is not implemented"


def _evidence_with_data_and_cost() -> dict[str, Any]:
    return {
        "evidence": [
            {
                "category": "data_quality",
                "source_id": "fixture-data",
                "version": "1",
                "status": "PASS",
            },
            {
                "category": "cost_model",
                "source_id": "fixture-costs",
                "version": "1",
                "status": "PASS",
            },
        ]
    }


def _performance_fixture() -> dict[str, Any]:
    return {
        "source_id": "fixture-forex",
        "cost_model_id": "fixture-costs-v1",
        "dataset_sha256": "a" * 64,
        "currency": "USD",
        "initial_equity": 10000,
        "selection_frozen_at_utc": "2025-12-31T00:00:00Z",
        "oos_start_utc": "2026-01-01T00:00:00Z",
        "oos_end_utc": "2026-02-01T00:00:00Z",
        "trades": [
            {"trade_id": str(index), "closed_at_utc": "2026-01-02T00:00:00Z", "gross_pnl": 3 if index % 2 == 0 else -1, "base_cost": 0.2, "stress_cost": 0.5}
            for index in range(100)
        ],
    }



def _qualifying_evidence(**overrides: Any) -> dict[str, Any]:
    payload = {
        "candidate_fingerprint": "fixture-candidate",
        "evidence_version": "1",
        "positive_oos_expectancy": True,
        "positive_stressed_expectancy": True,
        "profit_factor_after_costs": 1.10,
        "max_drawdown_pct": 10.0,
        "oos_trade_count": 100,
        "walk_forward_stable": True,
        "replication_stable": True,
        "nearby_parameter_stable": True,
        "no_profit_concentration": True,
        "performance_evidence": _performance_fixture(),
    }
    payload.update(overrides)
    return payload


def run_one_hundred_fixture_cycles() -> dict[str, Any]:
    catalog = [
        _experiment_payload(
            experiment_id=f"fixture-{index}",
            parameter_fingerprint=f"fixture-parameters-{index}",
        )
        for index in range(100)
    ]
    spec = _campaign_with_catalog(catalog, experiment_budget=100)
    outcomes: list[ExperimentOutcome] = []
    seen_fingerprints: set[str] = set()
    duplicate_fingerprints: list[str] = []
    live_authorization_seen = False

    for _ in range(100):
        decision = run_campaign_cycle(spec, outcomes, NOW)
        assert decision.status == "ADVANCE"
        assert decision.next_experiment is not None
        fingerprint = experiment_fingerprint(decision.next_experiment)
        if fingerprint in seen_fingerprints:
            duplicate_fingerprints.append(fingerprint)
        seen_fingerprints.add(fingerprint)
        outcomes.append(_outcome_for(decision.next_experiment))
        score = score_evidence(spec, _evidence_with_data_and_cost())
        gate = evaluate_edge_gate(spec, _qualifying_evidence())
        live_authorization_seen = live_authorization_seen or any(
            (
                score["live_authorization"],
                gate["live_authorization"],
                decision.to_dict()["live_authorization"],
            )
        )

    return {
        "duplicate_fingerprints": duplicate_fingerprints,
        "max_live_readiness_authority": live_authorization_seen,
    }


def test_campaign_requires_exactly_forex_primary_and_futures_comparison_lanes() -> None:
    _require_contract()

    assert campaign_module.REQUIRED_MARKET_LANES == frozenset(
        {"FOREX_EURUSD_PRIMARY", "CME_INDEX_FUTURES_COMPARISON"}
    )

    with pytest.raises(CampaignValidationError, match="market_lanes"):
        CampaignSpec.from_dict(
            _campaign_payload(market_lanes=["FOREX_EURUSD_PRIMARY"])
        )


def test_campaign_rejects_missing_required_gate_or_freshness_fields() -> None:
    _require_contract()

    with pytest.raises(CampaignValidationError, match="edge_gates"):
        CampaignSpec.from_dict(_campaign_payload(edge_gates={}))

    with pytest.raises(CampaignValidationError, match="freshness"):
        CampaignSpec.from_dict(_campaign_payload(freshness={"progress_max_age_seconds": 0}))


def test_fingerprint_ignores_display_id_but_changes_for_strategy_or_cost_scenario() -> None:
    _require_contract()

    first = Experiment.from_dict(_experiment_payload(experiment_id="display-a"))
    same_experiment = Experiment.from_dict(_experiment_payload(experiment_id="display-b"))
    stressed = Experiment.from_dict(_experiment_payload(cost_scenario="STRESSED"))
    different_strategy = Experiment.from_dict(
        _experiment_payload(strategy_family="MEAN_REVERSION")
    )

    assert experiment_fingerprint(first) == experiment_fingerprint(same_experiment)
    assert experiment_fingerprint(first) != experiment_fingerprint(stressed)
    assert experiment_fingerprint(first) != experiment_fingerprint(different_strategy)


def test_fingerprint_changes_for_session_window_and_nested_contract_data_is_immutable() -> None:
    _require_contract()
    first = Experiment.from_dict(_experiment_payload())
    overnight = Experiment.from_dict(_experiment_payload(session_window="OVERNIGHT"))
    nested = Experiment.from_dict(
        _experiment_payload(
            data_capability={
                **_experiment_payload()["data_capability"],
                "metadata": {"quality": "A"},
            }
        )
    )

    assert experiment_fingerprint(first) != experiment_fingerprint(overnight)
    with pytest.raises(TypeError):
        nested.data_capability["metadata"]["quality"] = "B"


def test_campaign_rejects_unapproved_lane_and_incomplete_cme_capability() -> None:
    _require_contract()
    unapproved = _experiment_payload(market_lane="CRYPTO")

    with pytest.raises(CampaignValidationError, match="market_lane"):
        _campaign_with_catalog([unapproved])
    with pytest.raises(CampaignValidationError, match="data_capability"):
        Experiment.from_dict(
            _experiment_payload(data_capability={"pinned": True, "source_id": "fixture"})
        )


def test_score_uses_only_backed_evidence_and_derives_live_readiness_from_lower_meter() -> None:
    _require_scorecard()

    score = score_evidence(CampaignSpec.from_dict(_campaign_payload()), _evidence_with_data_and_cost())

    assert score["profitability_readiness"] == 20
    assert score["engineering_readiness"] == 50
    assert score["edge_evidence"] == 0
    assert score["live_readiness"] == 0
    assert score["live_authorization"] is False


def test_any_failed_edge_gate_blocks_paper_eligibility() -> None:
    _require_scorecard()

    gate = evaluate_edge_gate(
        CampaignSpec.from_dict(_campaign_payload()),
        _qualifying_evidence(profit_factor_after_costs=1.09),
    )

    assert gate["status"] == "REJECT"
    assert "profit_factor_after_costs" in gate["reasons"]
    assert gate["live_authorization"] is False


def test_nonfinite_edge_metric_or_missing_candidate_evidence_binding_is_rejected() -> None:
    _require_scorecard()
    spec = CampaignSpec.from_dict(_campaign_payload())

    nonfinite = evaluate_edge_gate(
        spec, _qualifying_evidence(profit_factor_after_costs=float("nan"))
    )
    unbound = evaluate_edge_gate(
        spec, _qualifying_evidence(candidate_fingerprint="", evidence_version="")
    )

    assert nonfinite["status"] == "REJECT"
    assert "profit_factor_after_costs" in nonfinite["reasons"]
    assert unbound["status"] == "REJECT"
    assert {"candidate_fingerprint", "evidence_version"}.issubset(unbound["reasons"])


def test_edge_gate_requires_a_known_paper_stage_candidate_and_matching_version() -> None:
    _require_scorecard()
    paper_candidate = Experiment.from_dict(_experiment_payload(stage="PAPER"))
    spec = _campaign_with_catalog([paper_candidate.to_dict()])
    qualifying = _qualifying_evidence(
        candidate_fingerprint=experiment_fingerprint(paper_candidate),
        evidence_version=paper_candidate.expected_evidence_version,
    )

    eligible = evaluate_edge_gate(spec, qualifying)
    unknown = evaluate_edge_gate(
        spec, _qualifying_evidence(candidate_fingerprint="not-in-catalog")
    )
    version_mismatch = evaluate_edge_gate(
        spec,
        _qualifying_evidence(
            candidate_fingerprint=experiment_fingerprint(paper_candidate),
            evidence_version="unexpected",
        ),
    )

    assert eligible["status"] == "PAPER_ELIGIBLE"
    assert unknown["status"] == "REJECT"
    assert "candidate_fingerprint" in unknown["reasons"]
    assert version_mismatch["status"] == "REJECT"
    assert "evidence_version" in version_mismatch["reasons"]


def test_passing_stage_advances_only_to_the_next_required_stage() -> None:
    _require_router()
    cheap_screen = Experiment.from_dict(_experiment_payload(stage="CHEAP_SCREEN"))
    cost = Experiment.from_dict(_experiment_payload(experiment_id="cost", stage="COST"))
    spec = _campaign_with_catalog([cheap_screen.to_dict(), cost.to_dict()])

    decision = run_campaign_cycle(spec, [_outcome_for(cheap_screen)], NOW)

    assert decision.status == "ADVANCE"
    assert decision.next_experiment == cost


def test_outcome_cannot_skip_an_unrecorded_predecessor_stage() -> None:
    _require_router()
    cost = Experiment.from_dict(_experiment_payload(stage="COST"))
    walk_forward = Experiment.from_dict(
        _experiment_payload(experiment_id="walk", stage="WALK_FORWARD")
    )
    spec = _campaign_with_catalog([cost.to_dict(), walk_forward.to_dict()])

    decision = run_campaign_cycle(spec, [_outcome_for(cost)], NOW)

    assert decision.status == "BLOCKED"
    assert decision.reason == "OUTCOME_STAGE_SEQUENCE_INVALID"


def test_unpinned_forex_candidate_is_blocked_without_synthetic_evidence() -> None:
    _require_router()
    unpinned = Experiment.from_dict(
        _experiment_payload(
            data_capability={
                **_experiment_payload()["data_capability"],
                "pinned": False,
            }
        )
    )
    spec = _campaign_with_catalog([unpinned.to_dict()])

    decision = run_campaign_cycle(spec, [], NOW)

    assert decision.status == "BLOCKED"
    assert decision.reason == "FOREX_DATA_CAPABILITY_MISSING"

def test_unpinned_futures_comparison_candidate_is_blocked_without_synthetic_evidence() -> None:
    _require_router()
    futures = Experiment.from_dict(
        _experiment_payload(
            market_lane="CME_INDEX_FUTURES_COMPARISON",
            instrument="MES",
            session_window="RTH",
            data_capability={
                "pinned": False,
                "source_id": "fixture-cme",
                "contract_definition_id": "MES-2026",
                "calendar_id": "cme-equity-index",
                "tick_value": 1.25,
                "cost_model_id": "fixture-costs-v1",
            },
        )
    )
    spec = _campaign_with_catalog([futures.to_dict()])

    decision = run_campaign_cycle(spec, [], NOW)

    assert decision.status == "BLOCKED"
    assert decision.reason == "FUTURES_DATA_CAPABILITY_MISSING"


def test_duplicate_fingerprint_is_suppressed_and_next_unseen_experiment_is_selected() -> None:
    _require_router()
    duplicate = Experiment.from_dict(_experiment_payload(experiment_id="duplicate-a"))
    duplicate_display_copy = Experiment.from_dict(
        _experiment_payload(experiment_id="duplicate-b")
    )
    unique = Experiment.from_dict(
        _experiment_payload(
            experiment_id="unique-candidate", strategy_family="MEAN_REVERSION"
        )
    )
    spec = _campaign_with_catalog(
        [duplicate.to_dict(), duplicate_display_copy.to_dict(), unique.to_dict()]
    )

    decision = run_campaign_cycle(spec, [_outcome_for(duplicate, status="REJECT")], NOW)

    assert decision.status == "REJECT"
    assert decision.reason == "DUPLICATE_EXPERIMENT_FINGERPRINT"
    assert decision.next_experiment == unique


def test_exhausted_budget_is_truthful_no_edge_not_success_or_sos() -> None:
    _require_router()
    candidate = Experiment.from_dict(_experiment_payload())
    spec = _campaign_with_catalog([candidate.to_dict()], experiment_budget=1)

    decision = run_campaign_cycle(spec, [_outcome_for(candidate, status="REJECT")], NOW)

    assert decision.status == "NO_EDGE_IN_SCOPE"
    assert decision.sos_wake_required is False


def test_same_resumed_cycle_returns_same_decision_without_duplicate_experiment(
    tmp_path: Path,
) -> None:
    _require_checkpoint()
    cheap_screen = Experiment.from_dict(_experiment_payload(stage="CHEAP_SCREEN"))
    cost = Experiment.from_dict(_experiment_payload(experiment_id="cost", stage="COST"))
    spec = _campaign_with_catalog([cheap_screen.to_dict(), cost.to_dict()])
    outcomes = [_outcome_for(cheap_screen)]
    first_decision = run_campaign_cycle(spec, outcomes, NOW)

    path = write_checkpoint(tmp_path, _checkpoint_for(spec, first_decision, outcomes))
    resumed = load_checkpoint(path, spec)

    assert run_campaign_cycle(spec, resumed["outcomes"], NOW) == first_decision


def test_changed_campaign_or_corrupt_checkpoint_fails_closed(tmp_path: Path) -> None:
    _require_checkpoint()
    path = tmp_path / "campaign_checkpoint.json"
    path.write_text("{bad json", encoding="utf-8")
    spec = CampaignSpec.from_dict(_campaign_payload())

    with pytest.raises(CampaignCheckpointError, match="checkpoint"):
        load_checkpoint(path, spec)

    valid_path = write_checkpoint(
        tmp_path / "valid-state",
        _checkpoint_for(spec, run_campaign_cycle(spec, [], NOW), []),
    )
    changed_spec = CampaignSpec.from_dict(_campaign_payload(campaign_version="2"))

    with pytest.raises(CampaignCheckpointError, match="campaign"):
        load_checkpoint(valid_path, changed_spec)


def test_checkpoint_rejects_malformed_progress_timestamp_or_decision(tmp_path: Path) -> None:
    _require_checkpoint()
    spec = CampaignSpec.from_dict(_campaign_payload())
    decision = run_campaign_cycle(spec, [], NOW)

    malformed_time = _checkpoint_for(spec, decision, [])
    malformed_time["last_progress_utc"] = "not-a-timestamp"
    with pytest.raises(CampaignCheckpointError, match="last_progress_utc"):
        write_checkpoint(tmp_path, malformed_time)

    malformed_decision = _checkpoint_for(spec, decision, [])
    malformed_decision["last_decision"] = {"status": "ADVANCE"}
    with pytest.raises(CampaignCheckpointError, match="last_decision"):
        write_checkpoint(tmp_path, malformed_decision)


def test_one_hundred_fixture_cycles_never_repeat_a_fingerprint_or_emit_live_authority() -> None:
    result = run_one_hundred_fixture_cycles()

    assert result["duplicate_fingerprints"] == []
    assert result["max_live_readiness_authority"] is False


@pytest.mark.parametrize("repeat_with_empty_outcomes", [False, True])
def test_checkpoint_builder_preserves_completed_work_timestamp_on_repeated_empty_cycle(
    tmp_path: Path, repeat_with_empty_outcomes: bool,
) -> None:
    builder = getattr(campaign_module, "build_checkpoint", None)
    assert builder is not None, "canonical checkpoint builder is not implemented"
    spec = _campaign_with_catalog([_experiment_payload()], experiment_budget=1)
    outcomes = [_outcome_for(
        spec.catalog[0], status="REJECT", completed_at_utc="2026-10-05T11:59:00Z"
    )]
    original = _checkpoint_for(spec, run_campaign_cycle(spec, outcomes, NOW), outcomes)
    loaded = load_checkpoint(write_checkpoint(tmp_path, original), spec)

    for later in ("2026-10-05T12:05:00Z", "2026-10-05T12:10:00Z"):
        checkpoint = builder(
            spec,
            [] if repeat_with_empty_outcomes else loaded["outcomes"],
            run_campaign_cycle(spec, loaded["outcomes"], later),
            later,
            previous_checkpoint=loaded,
        )
        loaded = load_checkpoint(write_checkpoint(tmp_path, checkpoint), spec)

    assert loaded["last_progress_utc"] == "2026-10-05T11:59:00Z"
    assert loaded["completed_fingerprints"] == [outcomes[0].experiment_fingerprint]
    assert loaded["progress_max_age_seconds"] == 600


def test_checkpoint_builder_persists_campaign_freshness_and_new_completion_time() -> None:
    builder = getattr(campaign_module, "build_checkpoint", None)
    assert builder is not None, "canonical checkpoint builder is not implemented"
    spec = _campaign_with_catalog(
        [_experiment_payload()], freshness={"progress_max_age_seconds": 45}
    )
    outcome = _outcome_for(spec.catalog[0], completed_at_utc="2026-10-05T11:58:00Z")

    checkpoint = builder(spec, [outcome], run_campaign_cycle(spec, [outcome], NOW), NOW)

    assert checkpoint["last_progress_utc"] == "2026-10-05T11:58:00Z"
    assert checkpoint["progress_max_age_seconds"] == 45
    assert checkpoint["last_decision"]["live_authorization"] is False


def test_checkpoint_builder_preserves_first_empty_history_across_later_attempts(
    tmp_path: Path,
) -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    first = campaign_module.build_checkpoint(spec, [], run_campaign_cycle(spec, [], NOW), NOW)
    loaded = load_checkpoint(write_checkpoint(tmp_path, first), spec)
    later = "2026-10-05T12:10:00Z"

    repeated = campaign_module.build_checkpoint(
        spec, [], run_campaign_cycle(spec, [], later), later, previous_checkpoint=loaded
    )

    assert repeated["last_progress_utc"] == "2026-10-05T12:00:00Z"
    assert repeated["completed_fingerprints"] == []


def test_checkpoint_builder_uses_newest_completed_time_when_history_grows(
    tmp_path: Path,
) -> None:
    spec = _campaign_with_catalog([
        _experiment_payload(experiment_id="first"),
        _experiment_payload(experiment_id="second", parameter_fingerprint="second"),
    ])
    first_outcome = _outcome_for(spec.catalog[0], completed_at_utc="2026-10-05T11:59:00Z")
    first = campaign_module.build_checkpoint(
        spec, [first_outcome], run_campaign_cycle(spec, [first_outcome], NOW), NOW
    )
    loaded = load_checkpoint(write_checkpoint(tmp_path, first), spec)
    outcomes = [first_outcome, _outcome_for(
        spec.catalog[1], completed_at_utc="2026-10-05T11:58:00Z"
    )]

    grown = campaign_module.build_checkpoint(
        spec, outcomes, run_campaign_cycle(spec, outcomes, NOW), NOW,
        previous_checkpoint=loaded,
    )

    assert grown["last_progress_utc"] == "2026-10-05T11:59:00Z"
    assert len(grown["completed_fingerprints"]) == 2


@pytest.mark.parametrize("changed_field, replacement", [
    ("completed_at_utc", "2026-10-05T11:59:00Z"),
    ("reason", "revised-result"),
    ("status", "REJECT"),
])
def test_checkpoint_builder_rejects_changes_to_persisted_completed_outcome(
    tmp_path: Path, changed_field: str, replacement: str,
) -> None:
    spec = _campaign_with_catalog([
        _experiment_payload(experiment_id="first"),
        _experiment_payload(experiment_id="second", parameter_fingerprint="second"),
    ])
    original_outcome = _outcome_for(
        spec.catalog[0], completed_at_utc="2026-10-05T00:00:00Z"
    )
    original = campaign_module.build_checkpoint(
        spec, [original_outcome], run_campaign_cycle(spec, [original_outcome], NOW), NOW
    )
    loaded = load_checkpoint(write_checkpoint(tmp_path, original), spec)
    changed = ExperimentOutcome.from_dict({
        **original_outcome.to_dict(), changed_field: replacement,
    })

    with pytest.raises(CampaignCheckpointError, match="history"):
        campaign_module.build_checkpoint(
            spec, [changed], run_campaign_cycle(spec, [changed], NOW), NOW,
            previous_checkpoint=loaded,
        )


@pytest.mark.parametrize("supplied_indices", [(0,), (1, 0), (0, 2)])
def test_checkpoint_builder_rejects_dropped_reordered_or_replaced_prior_history(
    tmp_path: Path, supplied_indices: tuple[int, ...],
) -> None:
    spec = _campaign_with_catalog([
        _experiment_payload(experiment_id=f"candidate-{index}", parameter_fingerprint=str(index))
        for index in range(3)
    ])
    all_outcomes = [_outcome_for(candidate) for candidate in spec.catalog]
    original_outcomes = all_outcomes[:2]
    original = campaign_module.build_checkpoint(
        spec, original_outcomes, run_campaign_cycle(spec, original_outcomes, NOW), NOW
    )
    loaded = load_checkpoint(write_checkpoint(tmp_path, original), spec)
    supplied = [all_outcomes[index] for index in supplied_indices]

    with pytest.raises(CampaignCheckpointError, match="history"):
        campaign_module.build_checkpoint(
            spec, supplied, run_campaign_cycle(spec, supplied, NOW), NOW,
            previous_checkpoint=loaded,
        )


@pytest.mark.parametrize("rehash_offset_checkpoint", [False, True])
def test_checkpoint_with_explicit_utc_offset_can_be_loaded_and_rebuilt(
    tmp_path: Path, rehash_offset_checkpoint: bool,
) -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    outcome = _outcome_for(spec.catalog[0], completed_at_utc="2026-10-05T11:59:00+00:00")
    decision = run_campaign_cycle(spec, [outcome], NOW)
    path = write_checkpoint(tmp_path, _checkpoint_for(spec, decision, [outcome]))
    if rehash_offset_checkpoint:
        state = json.loads(path.read_text(encoding="utf-8"))
        state.pop("digest")
        state["last_progress_utc"] = "2026-10-05T11:59:00+00:00"
        state["outcomes"][0]["completed_at_utc"] = "2026-10-05T11:59:00+00:00"
        state["digest"] = hashlib.sha256(json.dumps(
            state, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        path.write_text(json.dumps(state), encoding="utf-8")
    loaded = load_checkpoint(path, spec)

    rebuilt = campaign_module.build_checkpoint(
        spec, [outcome], decision, NOW, previous_checkpoint=loaded
    )

    assert rebuilt["last_progress_utc"] == "2026-10-05T11:59:00Z"
    assert rebuilt["outcomes"][0]["completed_at_utc"] == "2026-10-05T11:59:00Z"


@pytest.mark.parametrize("invalid_kind", ["digest", "decision", "live_authorization", "freshness"])
def test_public_checkpoint_validator_rejects_digest_and_schema_errors(
    tmp_path: Path, invalid_kind: str,
) -> None:
    validator = getattr(campaign_module, "validate_checkpoint_payload", None)
    assert validator is not None, "canonical checkpoint validator is not implemented"
    spec = _campaign_with_catalog([_experiment_payload()])
    state = json.loads(write_checkpoint(
        tmp_path, _checkpoint_for(spec, run_campaign_cycle(spec, [], NOW), [])
    ).read_text(encoding="utf-8"))
    if invalid_kind == "digest":
        state["digest"] = "0" * 64
    else:
        state.pop("digest")
        if invalid_kind == "decision":
            state["last_decision"].pop("reason")
        elif invalid_kind == "live_authorization":
            state["last_decision"]["live_authorization"] = True
        else:
            state["progress_max_age_seconds"] = True
        state["digest"] = hashlib.sha256(json.dumps(
            state, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()

    with pytest.raises(CampaignCheckpointError):
        validator(state)


def test_public_checkpoint_validator_returns_canonical_payload_without_mutating_input(
    tmp_path: Path,
) -> None:
    validator = getattr(campaign_module, "validate_checkpoint_payload", None)
    assert validator is not None, "canonical checkpoint validator is not implemented"
    spec = _campaign_with_catalog([_experiment_payload()])
    state = json.loads(write_checkpoint(
        tmp_path, _checkpoint_for(spec, run_campaign_cycle(spec, [], NOW), [])
    ).read_text(encoding="utf-8"))

    payload = validator(state)

    assert "digest" in state
    assert "digest" not in payload
    assert payload["progress_max_age_seconds"] == 600
    assert payload["last_decision"]["live_authorization"] is False


@pytest.mark.parametrize("restamped_progress", ["2026-10-05T11:59:00Z", "2026-10-05T00:00:00Z"])
def test_canonical_active_checkpoint_rejects_progress_not_matching_newest_completion(
    tmp_path: Path, restamped_progress: str,
) -> None:
    spec = _campaign_with_catalog([
        _experiment_payload(experiment_id=f"candidate-{index}", parameter_fingerprint=str(index))
        for index in range(3)
    ])
    outcomes = [
        _outcome_for(spec.catalog[0], completed_at_utc="2026-10-05T00:01:00Z"),
        _outcome_for(spec.catalog[1], completed_at_utc="2026-10-05T00:00:00Z"),
    ]
    original = campaign_module.build_checkpoint(
        spec, outcomes, run_campaign_cycle(spec, outcomes, NOW), NOW
    )
    path = write_checkpoint(tmp_path, original)
    state = json.loads(path.read_text(encoding="utf-8"))
    state.pop("digest")
    state["last_progress_utc"] = restamped_progress
    state["digest"] = hashlib.sha256(json.dumps(
        state, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()

    with pytest.raises(CampaignCheckpointError, match="last_progress_utc"):
        campaign_module.validate_checkpoint_payload(state)
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(CampaignCheckpointError, match="last_progress_utc"):
        load_checkpoint(path, spec)


@pytest.mark.parametrize("decision_status", ["NO_EDGE_IN_SCOPE", "BLOCKED"])
def test_canonical_nonempty_checkpoint_always_binds_progress_to_completed_work(
    tmp_path: Path, decision_status: str,
) -> None:
    spec = _campaign_with_catalog([_experiment_payload()], experiment_budget=1)
    outcome_status = "BLOCKED" if decision_status == "BLOCKED" else "REJECT"
    outcome = _outcome_for(
        spec.catalog[0],
        status=outcome_status,
        completed_at_utc="2026-10-05T00:00:00Z",
    )
    decision = run_campaign_cycle(spec, [outcome], NOW)
    assert decision.status == decision_status
    original = campaign_module.build_checkpoint(spec, [outcome], decision, NOW)
    state = json.loads(write_checkpoint(tmp_path, original).read_text(encoding="utf-8"))
    state.pop("digest")
    state["last_progress_utc"] = "2026-10-05T11:59:00Z"
    state["digest"] = hashlib.sha256(json.dumps(
        state, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()

    with pytest.raises(CampaignCheckpointError, match="last_progress_utc"):
        campaign_module.validate_checkpoint_payload(state)


def test_checkpoint_freshness_budget_is_bound_to_campaign_spec(tmp_path: Path) -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    decision = run_campaign_cycle(spec, [], NOW)
    checkpoint = campaign_module.build_checkpoint(spec, [], decision, NOW)
    path = write_checkpoint(tmp_path, checkpoint)
    state = json.loads(path.read_text(encoding="utf-8"))
    state.pop("digest")
    state["progress_max_age_seconds"] = 3600
    state["digest"] = hashlib.sha256(json.dumps(
        state, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()

    with pytest.raises(CampaignCheckpointError, match="progress_max_age_seconds"):
        campaign_module.validate_checkpoint_payload(state)



def _paper_lineage() -> tuple[CampaignSpec, list[ExperimentOutcome], Experiment]:
    stages = [
        "CHEAP_SCREEN",
        "COST",
        "WALK_FORWARD",
        "TRUE_OOS",
        "STRESS",
        "REPLICATION",
        "PAPER",
    ]
    catalog = [
        _experiment_payload(
            experiment_id=f"paper-lineage-{stage.lower()}",
            stage=stage,
            parameter_fingerprint="paper-lineage-v1",
        )
        for stage in stages
    ]
    spec = _campaign_with_catalog(catalog, experiment_budget=len(catalog))
    outcomes = [_outcome_for(experiment) for experiment in spec.catalog[:-1]]
    return spec, outcomes, spec.catalog[-1]


def test_paper_stage_requires_candidate_bound_edge_evidence() -> None:
    spec, outcomes, paper_candidate = _paper_lineage()

    decision = run_campaign_cycle(spec, outcomes, NOW)

    assert decision.status == "REJECT"
    assert decision.reason == "PAPER_EDGE_GATE_REJECTED"
    assert decision.sos_wake_required is False
    assert decision.paper_edge_gate["status"] == "REJECT"
    assert decision.paper_edge_gate["live_authorization"] is False


@pytest.mark.parametrize(
    "evidence",
    [
        {"candidate_fingerprint": "wrong"},
        {"candidate_fingerprint": "wrong", "evidence_version": "1"},
        {
            **_qualifying_evidence(),
            "candidate_fingerprint": "wrong",
        },
        {
            **_qualifying_evidence(),
            "candidate_fingerprint": "fixture-candidate",
            "positive_oos_expectancy": False,
        },
    ],
)
def test_paper_stage_rejects_missing_wrong_or_failed_edge_evidence(
    evidence: dict[str, Any],
) -> None:
    spec, outcomes, _ = _paper_lineage()

    decision = run_campaign_cycle(spec, outcomes, NOW, paper_evidence=evidence)

    assert decision.status == "REJECT"
    assert decision.reason == "PAPER_EDGE_GATE_REJECTED"
    assert decision.sos_wake_required is False
    assert decision.paper_edge_gate["status"] == "REJECT"


def test_paper_stage_accepts_only_qualifying_candidate_bound_evidence_and_replays_it(
    tmp_path: Path,
) -> None:
    spec, outcomes, paper_candidate = _paper_lineage()
    evidence = _qualifying_evidence(
        candidate_fingerprint=experiment_fingerprint(paper_candidate),
        evidence_version=paper_candidate.expected_evidence_version,
    )

    decision = run_campaign_cycle(spec, outcomes, NOW, paper_evidence=evidence)
    checkpoint = campaign_module.build_checkpoint(
        spec, outcomes, decision, NOW, paper_evidence=evidence
    )
    path = write_checkpoint(tmp_path, checkpoint)
    loaded = load_checkpoint(path, spec)

    assert decision.status == "ADVANCE"
    assert decision.next_experiment == paper_candidate
    assert decision.paper_edge_gate["status"] == "PAPER_ELIGIBLE"
    assert decision.paper_edge_gate["live_authorization"] is False
    assert loaded["routing_context"]["route_inputs"]["paper_evidence"] == evidence


def test_evidence_score_skips_unhashable_categories_safely() -> None:
    spec, _, _ = _paper_lineage()

    score = score_evidence(
        spec,
        {"evidence": [{"category": [], "source_id": "fixture", "version": "1", "status": "PASS"}]},
    )

    assert score["supported_categories"] == []


@pytest.mark.parametrize(
    "payload",
    [
        _campaign_payload(experiment_budget=1001),
        _campaign_payload(experiment_catalog=[_experiment_payload()] * 1001),
    ],
)
def test_campaign_rejects_budget_or_catalog_above_bounded_limit(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(CampaignValidationError, match="1000"):
        CampaignSpec.from_dict(payload)


def test_router_rejects_more_than_one_thousand_outcomes_before_routing() -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    outcome = _outcome_for(spec.catalog[0])

    with pytest.raises(CampaignValidationError, match="1000"):
        run_campaign_cycle(spec, [outcome] * 1001, NOW)


def test_router_rejects_oversized_paper_evidence_before_routing() -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    oversized = {"evidence": [], "padding": "x" * (1024 * 1024)}

    with pytest.raises(CampaignValidationError, match="1 MiB"):
        run_campaign_cycle(spec, [], NOW, paper_evidence=oversized)


def test_output_root_validator_rejects_temp_root_repo_root_and_symlink_escape(
    tmp_path: Path,
) -> None:
    import tempfile

    validator = getattr(campaign_module, "validate_checkpoint_root", None)
    assert validator is not None, "checkpoint output-root validator is not implemented"
    with pytest.raises(CampaignCheckpointError):
        validator(Path(tempfile.gettempdir()))
    with pytest.raises(CampaignCheckpointError):
        write_checkpoint(Path(tempfile.gettempdir()), {})
    with pytest.raises(CampaignCheckpointError):
        write_checkpoint(Path(__file__).resolve().parents[2], {})
    with pytest.raises(CampaignCheckpointError):
        validator(Path(__file__).resolve().parents[2])
    escaped = tmp_path / "escaped-output"
    escaped.symlink_to(Path(__file__).resolve().parents[2], target_is_directory=True)
    with pytest.raises(CampaignCheckpointError):
        validator(escaped)


def test_output_root_can_be_below_a_temporary_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "working-directory"
    output_root = current / "checkpoint-output"
    current.mkdir()
    monkeypatch.chdir(current)

    validator = getattr(campaign_module, "validate_checkpoint_root", None)
    assert validator is not None

    assert validator(output_root) == output_root.resolve()


def test_old_routing_context_schema_is_rejected(tmp_path: Path) -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    decision = run_campaign_cycle(spec, [], NOW)
    checkpoint = campaign_module.build_checkpoint(spec, [], decision, NOW)
    checkpoint["routing_context"]["schema"] = "AIOS_RESEARCH_ROUTING_CONTEXT.v1"
    checkpoint["digest"] = hashlib.sha256(
        json.dumps(checkpoint, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    with pytest.raises(CampaignCheckpointError, match="schema"):
        campaign_module.validate_checkpoint_payload(checkpoint)


def test_checkpoint_validator_and_writer_reject_payloads_over_one_mib(
    tmp_path: Path,
) -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    decision = run_campaign_cycle(spec, [], NOW)
    checkpoint = campaign_module.build_checkpoint(spec, [], decision, NOW)
    checkpoint["padding"] = "x" * campaign_module.MAX_JSON_INPUT_BYTES
    checkpoint["digest"] = hashlib.sha256(
        campaign_module._canonical_json(checkpoint).encode("utf-8")
    ).hexdigest()

    with pytest.raises(CampaignCheckpointError, match="1 MiB"):
        campaign_module.validate_checkpoint_payload(checkpoint)

    output_root = tmp_path / "oversized-output"
    unsigned = {key: value for key, value in checkpoint.items() if key != "digest"}
    with pytest.raises(CampaignCheckpointError, match="1 MiB"):
        write_checkpoint(output_root, unsigned)
    assert not output_root.exists()


@pytest.mark.parametrize("reader", ["runner", "watchdog", "checkpoint", "writer"])
@pytest.mark.parametrize("file_kind", ["fifo", "directory"])
def test_json_consumers_fail_fast_for_special_files(
    tmp_path: Path, reader: str, file_kind: str
) -> None:
    if file_kind == "fifo" and not hasattr(os, "mkfifo"):
        pytest.skip("FIFOs are not available on this platform")
    path = tmp_path / "campaign_checkpoint.json"
    if file_kind == "fifo":
        os.mkfifo(path)
    else:
        path.mkdir()
    script = """
import runpy
import sys
from pathlib import Path
from automation.orchestration.research_campaign.aios_research_campaign import (
    CampaignSpec, build_checkpoint, load_checkpoint, run_campaign_cycle, write_checkpoint,
)
from automation.orchestration.research_campaign.aios_research_campaign_runner import _read_json
from automation.orchestration.watchdog.aios_deadman_watchdog import read_json
path, reader = Path(sys.argv[1]), sys.argv[2]
try:
    if reader == "runner":
        _read_json(str(path), "test input")
    elif reader == "watchdog":
        assert read_json(path) is None
        print("BLOCKED")
        raise SystemExit(0)
    else:
        helpers = runpy.run_path("tests/orchestration/test_aios_research_campaign.py")
        spec = helpers["_campaign_with_catalog"]([helpers["_experiment_payload"]()])
        if reader == "checkpoint":
            load_checkpoint(path, spec)
        else:
            now = "2026-10-05T12:00:00Z"
            decision = run_campaign_cycle(spec, [], now)
            write_checkpoint(path.parent, build_checkpoint(spec, [], decision, now))
except ValueError:
    print("BLOCKED")
else:
    raise AssertionError("special input unexpectedly accepted")
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script, str(path), reader],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{reader} blocked waiting for a special-file writer")
    finally:
        (tmp_path / ".campaign_checkpoint.lock").unlink(missing_ok=True)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "BLOCKED"


def test_load_checkpoint_rejects_file_over_one_mib_before_parsing(
    tmp_path: Path,
) -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    path = tmp_path / "oversized-checkpoint.json"
    path.write_bytes(b"{} " + b" " * campaign_module.MAX_JSON_INPUT_BYTES)

    with pytest.raises(CampaignCheckpointError, match="1 MiB"):
        load_checkpoint(path, spec)


def test_load_checkpoint_rejects_deeply_nested_json_without_traceback(
    tmp_path: Path,
) -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    path = tmp_path / "deeply-nested-checkpoint.json"
    path.write_text("[" * 10_000 + "0" + "]" * 10_000, encoding="utf-8")

    with pytest.raises(CampaignCheckpointError, match="unreadable or malformed"):
        load_checkpoint(path, spec)


def test_budget_stop_does_not_erase_a_passing_unfinished_lineage() -> None:
    spec, _, _ = _paper_lineage()
    limited = CampaignSpec.from_dict({**spec.to_dict(), "experiment_budget": 1})

    decision = run_campaign_cycle(limited, [_outcome_for(limited.catalog[0])], NOW)

    assert decision.status == "BUDGET_EXHAUSTED"
    assert decision.sos_wake_required is False
    assert decision.to_dict()["live_authorization"] is False


def test_scientific_rejection_prunes_lineage_without_a_false_operational_block() -> None:
    spec, _, _ = _paper_lineage()

    decision = run_campaign_cycle(spec, [_outcome_for(spec.catalog[0], status="REJECT")], NOW)

    assert decision.status == "NO_EDGE_IN_SCOPE"
    assert decision.sos_wake_required is False


def test_completed_passing_research_is_not_labeled_no_edge() -> None:
    spec, outcomes, paper_candidate = _paper_lineage()

    decision = run_campaign_cycle(spec, [*outcomes, _outcome_for(paper_candidate)], NOW)

    assert decision.status == "RESEARCH_COMPLETE"
    assert decision.to_dict()["live_authorization"] is False


def test_passing_partial_catalog_is_insufficient_evidence_not_no_edge() -> None:
    spec = _campaign_with_catalog([_experiment_payload()])

    decision = run_campaign_cycle(spec, [_outcome_for(spec.catalog[0])], NOW)

    assert decision.status == "BUDGET_EXHAUSTED"
    assert decision.reason == "CAMPAIGN_VALIDATION_SCOPE_INCOMPLETE"


@pytest.mark.parametrize("clock", ["not-a-clock", "2026-10-05T12:00:00"])
def test_router_rejects_invalid_clock_even_with_nonempty_history(clock: str) -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    with pytest.raises((CampaignValidationError, CampaignCheckpointError), match="now_utc"):
        run_campaign_cycle(spec, [_outcome_for(spec.catalog[0])], clock)


def test_router_blocks_future_completion_before_any_terminal_classification() -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    future = _outcome_for(spec.catalog[0], completed_at_utc="2099-01-01T00:00:00Z")

    decision = run_campaign_cycle(spec, [future], NOW)

    assert decision.status == "BLOCKED"
    assert decision.reason == "OUTCOME_COMPLETED_IN_FUTURE"


def test_paper_evidence_for_another_catalog_candidate_cannot_authorize_selection() -> None:
    original, outcomes, candidate = _paper_lineage()
    other = Experiment.from_dict({**candidate.to_dict(), "experiment_id": "other-paper", "parameter_fingerprint": "other"})
    spec = CampaignSpec.from_dict({**original.to_dict(), "experiment_catalog": [*original.to_dict()["experiment_catalog"], other.to_dict()]})
    evidence = _qualifying_evidence(candidate_fingerprint=experiment_fingerprint(other))

    decision = run_campaign_cycle(spec, outcomes, NOW, evidence)

    assert decision.status == "REJECT"
    assert "selected_candidate_mismatch" in decision.paper_edge_gate["reasons"]


def test_checkpoint_writer_cannot_overwrite_newer_completed_history(tmp_path: Path) -> None:
    spec = _campaign_with_catalog([
        _experiment_payload(experiment_id=str(index), parameter_fingerprint=str(index))
        for index in range(3)
    ])
    first_history = [_outcome_for(spec.catalog[0])]
    first = _checkpoint_for(spec, run_campaign_cycle(spec, first_history, NOW), first_history)
    write_checkpoint(tmp_path, first)
    new_history = [*first_history, _outcome_for(spec.catalog[1])]
    newer = _checkpoint_for(spec, run_campaign_cycle(spec, new_history, NOW), new_history)
    path = write_checkpoint(tmp_path, newer)
    before = path.read_bytes()

    with pytest.raises(CampaignCheckpointError, match="history"):
        write_checkpoint(tmp_path, first)

    assert path.read_bytes() == before


def test_checkpoint_writer_rejects_busy_writer_without_touching_state(tmp_path: Path) -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    payload = _checkpoint_for(spec, run_campaign_cycle(spec, [], NOW), [])
    lock = tmp_path / ".campaign_checkpoint.lock"
    lock.write_text("held by another writer", encoding="utf-8")

    with pytest.raises(CampaignCheckpointError, match="writer"):
        write_checkpoint(tmp_path, payload)

    assert lock.read_text() == "held by another writer"
    assert not (tmp_path / "campaign_checkpoint.json").exists()


def test_checkpoint_compare_and_swap_rejects_changed_revision(tmp_path: Path) -> None:
    spec = _campaign_with_catalog([
        _experiment_payload(experiment_id=str(index), parameter_fingerprint=str(index))
        for index in range(3)
    ])
    history = [_outcome_for(spec.catalog[0])]
    first = _checkpoint_for(spec, run_campaign_cycle(spec, history, NOW), history)
    path = write_checkpoint(tmp_path, first)
    old_digest = load_checkpoint(path, spec)["digest"]
    later = [*history, _outcome_for(spec.catalog[1])]
    newer = _checkpoint_for(spec, run_campaign_cycle(spec, later, NOW), later)
    write_checkpoint(tmp_path, newer)
    before = path.read_bytes()

    with pytest.raises(CampaignCheckpointError, match="revision"):
        write_checkpoint(tmp_path, newer, expected_digest=old_digest)

    assert path.read_bytes() == before


def test_checkpoint_create_only_cannot_replace_a_concurrent_first_write(tmp_path: Path) -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    payload = _checkpoint_for(spec, run_campaign_cycle(spec, [], NOW), [])
    path = write_checkpoint(tmp_path, payload)
    before = path.read_bytes()

    with pytest.raises(CampaignCheckpointError, match="revision"):
        write_checkpoint(tmp_path, payload, expected_digest=None)

    assert path.read_bytes() == before




def test_paper_gate_cannot_accept_metric_claims_without_trade_evidence() -> None:
    spec, _, candidate = _paper_lineage()
    evidence = _qualifying_evidence(candidate_fingerprint=experiment_fingerprint(candidate))
    evidence.pop("performance_evidence")

    gate = evaluate_edge_gate(spec, evidence)

    assert gate["status"] == "REJECT"
    assert "performance_evidence_required" in gate["reasons"]


def test_paper_gate_recomputes_cost_adjusted_metrics_from_trade_evidence() -> None:
    spec, _, candidate = _paper_lineage()
    evidence = _qualifying_evidence(candidate_fingerprint=experiment_fingerprint(candidate), performance_evidence=_performance_fixture())

    gate = evaluate_edge_gate(spec, evidence)

    assert gate["status"] == "PAPER_ELIGIBLE"
    assert gate["derived_metrics"]["oos_expectancy"] == pytest.approx(0.8)
    assert gate["derived_metrics"]["stressed_expectancy"] == pytest.approx(0.5)
    assert gate["derived_metrics"]["profit_factor_after_costs"] == pytest.approx(7 / 3)
    assert gate["derived_metrics"]["oos_trade_count"] == 100
    assert gate["paper_readiness_verified"] is False
    assert gate["source_authentication_verified"] is False


def test_positive_metric_claims_cannot_hide_losses_after_stress_costs() -> None:
    spec, _, candidate = _paper_lineage()
    performance = _performance_fixture()
    for trade in performance["trades"]:
        trade["stress_cost"] = 2
    evidence = _qualifying_evidence(candidate_fingerprint=experiment_fingerprint(candidate), performance_evidence=performance)

    gate = evaluate_edge_gate(spec, evidence)

    assert gate["status"] == "REJECT"
    assert "derived_stressed_expectancy" in gate["reasons"]


@pytest.mark.parametrize("defect", ["duplicate_trade", "costs", "source", "post_selection", "outside_oos"])
def test_performance_evidence_rejects_unsafe_or_unbound_trade_receipts(defect: str) -> None:
    spec, _, candidate = _paper_lineage()
    performance = _performance_fixture()
    if defect == "duplicate_trade":
        performance["trades"][1]["trade_id"] = "0"
    elif defect == "costs":
        performance["trades"][0]["stress_cost"] = 0
    elif defect == "source":
        performance["source_id"] = "unrelated-data"
    elif defect == "post_selection":
        performance["selection_frozen_at_utc"] = "2026-01-02T00:00:00Z"
    elif defect == "outside_oos":
        performance["trades"][0]["closed_at_utc"] = "2024-01-01T00:00:00Z"
    evidence = _qualifying_evidence(candidate_fingerprint=experiment_fingerprint(candidate), performance_evidence=performance)

    gate = evaluate_edge_gate(spec, evidence)

    assert gate["status"] == "REJECT"
    assert "performance_evidence_invalid" in gate["reasons"]


def test_supplied_completed_history_cannot_exceed_the_approved_budget() -> None:
    spec, outcomes, candidate = _paper_lineage()
    limited = CampaignSpec.from_dict({**spec.to_dict(), "experiment_budget": 1})

    decision = run_campaign_cycle(limited, [*outcomes, _outcome_for(candidate)], NOW)

    assert decision.status == "BLOCKED"
    assert decision.reason == "OUTCOME_HISTORY_EXCEEDS_APPROVED_BUDGET"


def test_later_stage_cannot_complete_before_its_predecessor() -> None:
    spec, _, _ = _paper_lineage()
    outcomes = [
        _outcome_for(spec.catalog[0], completed_at_utc="2026-10-05T10:00:00Z"),
        _outcome_for(spec.catalog[1], completed_at_utc="2026-10-05T09:00:00Z"),
    ]

    decision = run_campaign_cycle(spec, outcomes, NOW)

    assert decision.status == "BLOCKED"
    assert decision.reason == "OUTCOME_STAGE_CHRONOLOGY_INVALID"


def test_fractional_future_timestamp_is_not_truncated_into_valid_history() -> None:
    spec = _campaign_with_catalog([_experiment_payload()])
    outcome = _outcome_for(spec.catalog[0], completed_at_utc="2026-10-05T12:00:00.500000Z")

    decision = run_campaign_cycle(spec, [outcome], NOW)

    assert decision.status == "BLOCKED"
    assert decision.reason == "OUTCOME_COMPLETED_IN_FUTURE"


def test_subsecond_selection_overlap_cannot_be_hidden_by_timestamp_rounding() -> None:
    spec, _, candidate = _paper_lineage()
    performance = _performance_fixture()
    performance["selection_frozen_at_utc"] = "2026-01-01T00:00:00.900000Z"
    performance["oos_start_utc"] = "2026-01-01T00:00:00.100000Z"
    evidence = _qualifying_evidence(candidate_fingerprint=experiment_fingerprint(candidate), performance_evidence=performance)

    gate = evaluate_edge_gate(spec, evidence)

    assert gate["status"] == "REJECT"
    assert "performance_evidence_invalid" in gate["reasons"]


def test_duplicate_catalog_route_cannot_skip_the_paper_evidence_gate() -> None:
    original, outcomes, _ = _paper_lineage()
    spec = CampaignSpec.from_dict({
        **original.to_dict(),
        "experiment_catalog": [*original.to_dict()["experiment_catalog"], {**original.catalog[0].to_dict(), "experiment_id": "display-duplicate"}],
    })

    decision = run_campaign_cycle(spec, outcomes, NOW)

    assert decision.status == "REJECT"
    assert decision.reason == "PAPER_EDGE_GATE_REJECTED"
    assert decision.paper_edge_gate["status"] == "REJECT"


@pytest.mark.parametrize("nested_in_trade", [False, True])
def test_unknown_private_fields_in_performance_receipt_are_never_checkpointed(
    tmp_path: Path, nested_in_trade: bool,
) -> None:
    spec, outcomes, candidate = _paper_lineage()
    performance = _performance_fixture()
    target = performance["trades"][0] if nested_in_trade else performance
    target["account_id"] = "synthetic-private-field"
    evidence = _qualifying_evidence(candidate_fingerprint=experiment_fingerprint(candidate), performance_evidence=performance)
    decision = run_campaign_cycle(spec, outcomes, NOW, evidence)

    assert decision.status == "REJECT"
    with pytest.raises(CampaignCheckpointError, match="performance"):
        campaign_module.build_checkpoint(spec, outcomes, decision, NOW, paper_evidence=evidence)
    assert not list(tmp_path.iterdir())


def test_finished_candidate_does_not_hide_another_incomplete_passing_lineage() -> None:
    original, outcomes, candidate = _paper_lineage()
    partial = Experiment.from_dict(_experiment_payload(experiment_id="partial", parameter_fingerprint="partial"))
    spec = CampaignSpec.from_dict({
        **original.to_dict(), "experiment_budget": 8,
        "experiment_catalog": [*original.to_dict()["experiment_catalog"], partial.to_dict()],
    })

    decision = run_campaign_cycle(spec, [*outcomes, _outcome_for(candidate), _outcome_for(partial)], NOW)

    assert decision.status == "BUDGET_EXHAUSTED"
    assert decision.reason == "CAMPAIGN_VALIDATION_SCOPE_INCOMPLETE"


def test_finished_candidate_does_not_hide_an_unvisited_unroutable_lineage() -> None:
    original, outcomes, candidate = _paper_lineage()
    orphan = _experiment_payload(experiment_id="orphan-cost", stage="COST", parameter_fingerprint="orphan")
    spec = CampaignSpec.from_dict({
        **original.to_dict(), "experiment_budget": 8,
        "experiment_catalog": [*original.to_dict()["experiment_catalog"], orphan],
    })

    decision = run_campaign_cycle(spec, [*outcomes, _outcome_for(candidate)], NOW)

    assert decision.status == "BUDGET_EXHAUSTED"
    assert decision.reason == "CAMPAIGN_VALIDATION_SCOPE_INCOMPLETE"
