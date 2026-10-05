from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import pytest

from automation.orchestration.watchdog.aios_deadman_watchdog import (
    evaluate,
    evaluate_campaign_health,
    read_json,
)


NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)


def _signed_state(state: dict[str, Any]) -> dict[str, Any]:
    digest = hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {**state, "digest": digest}


def _campaign_payload_for_health(
    completed_count: int,
    last_progress: str,
    progress_max_age_seconds: int = 600,
) -> dict[str, Any]:
    from automation.orchestration.research_campaign.aios_research_campaign import (
        CampaignSpec,
        ExperimentOutcome,
        build_checkpoint,
        experiment_fingerprint,
        run_campaign_cycle,
    )

    common = {
        "market_lane": "FOREX_EURUSD_PRIMARY",
        "strategy_family": "MOMENTUM",
        "instrument": "EUR_USD",
        "session_window": "LONDON",
        "stage": "CHEAP_SCREEN",
        "data_capability": {"pinned": True, "source_id": "fixture-forex", "calendar_id": "forex-eurusd", "cost_model_id": "fixture-costs-v1", "pip_value": 10.0},
        "cost_scenario": "BASELINE",
        "expected_evidence_version": "1",
    }
    catalog = [
        {
            **common,
            "experiment_id": f"candidate-{index}",
            "parameter_fingerprint": f"params-{index}",
        }
        for index in range(2)
    ]
    spec = CampaignSpec.from_dict({
        "campaign_id": "forex-first-v1",
        "campaign_version": "1",
        "market_lanes": ["FOREX_EURUSD_PRIMARY", "CME_INDEX_FUTURES_COMPARISON"],
        "experiment_budget": 2,
        "edge_gates": {"min_oos_trade_count": 100},
        "freshness": {"progress_max_age_seconds": progress_max_age_seconds},
        "experiment_catalog": catalog,
    })
    safe_progress = (
        last_progress
        if last_progress.endswith("Z") or last_progress.endswith("+00:00")
        else "2026-10-05T11:59:00Z"
    )
    outcomes = [
        ExperimentOutcome.from_dict({
            "experiment_fingerprint": experiment_fingerprint(spec.catalog[index]),
            "stage": "CHEAP_SCREEN",
            "status": "REJECT" if completed_count == 2 else "ADVANCE",
            "reason": "fixture",
            "evidence_version": "1",
            "completed_at_utc": safe_progress,
        })
        for index in range(completed_count)
    ]
    decision = run_campaign_cycle(spec, outcomes, safe_progress)
    checkpoint = build_checkpoint(spec, outcomes, decision, safe_progress)
    state = dict(checkpoint)
    state["last_progress_utc"] = last_progress
    return state


def _campaign_state(
    last_progress: str = "2026-10-05T11:59:00Z", **overrides: Any
) -> dict[str, Any]:
    completed_count = overrides.pop("_completed_count", 1)
    progress_max_age_seconds = overrides.pop("progress_max_age_seconds", 600)
    state = _campaign_payload_for_health(
        completed_count, last_progress, progress_max_age_seconds
    )
    state.update(overrides)
    return _signed_state(state)


def _no_edge_campaign_state(
    last_progress: str = "2026-10-05T11:59:00Z", **overrides: Any
) -> dict[str, Any]:
    progress_max_age_seconds = overrides.pop("progress_max_age_seconds", 600)
    state = _campaign_payload_for_health(2, last_progress, progress_max_age_seconds)
    state.update(overrides)
    return _signed_state(state)


def test_active_campaign_with_stale_progress_is_blocked_and_wake_worthy() -> None:
    health = evaluate_campaign_health(
        _campaign_state(last_progress="2026-10-05T00:00:00Z"), NOW, 300
    )

    assert health["status"] == "BLOCKED"
    assert health["reason"] == "campaign_progress_stale"
    assert health["sos_wake_required"] is True


def test_no_edge_in_scope_is_not_an_sos_fault() -> None:
    health = evaluate_campaign_health(_no_edge_campaign_state(), NOW, 300)

    assert health["status"] == "NO_EDGE_IN_SCOPE"
    assert health["sos_wake_required"] is False


def test_future_no_edge_checkpoint_is_blocked_before_terminal_no_wake_handling() -> None:
    health = evaluate_campaign_health(
        _no_edge_campaign_state(last_progress="2026-10-05T12:00:01Z"), NOW, 300
    )

    assert health["status"] == "BLOCKED"
    assert health["reason"] == "campaign_progress_future_timestamp"
    assert health["staleness_seconds"] == -1
    assert health["sos_wake_required"] is True


def _informational_terminal_state(status: str, last_progress: str) -> dict[str, Any]:
    from automation.orchestration.research_campaign.aios_research_campaign import (
        CampaignSpec,
        ExperimentOutcome,
        RESEARCH_STAGES,
        build_checkpoint,
        experiment_fingerprint,
        run_campaign_cycle,
    )

    payload = _campaign_payload_for_health(0, last_progress)["routing_context"]["campaign_spec"]
    if status == "BUDGET_EXHAUSTED":
        payload["experiment_budget"] = 1
        completed_count = 1
    else:
        common = payload["experiment_catalog"][0]
        payload["experiment_catalog"] = [
            {**common, "experiment_id": f"terminal-{stage}", "stage": stage}
            for stage in RESEARCH_STAGES
        ]
        payload["experiment_budget"] = len(RESEARCH_STAGES)
        completed_count = len(RESEARCH_STAGES)
    spec = CampaignSpec.from_dict(payload)
    outcomes = [
        ExperimentOutcome.from_dict({
            "experiment_fingerprint": experiment_fingerprint(candidate),
            "stage": candidate.stage,
            "status": "ADVANCE",
            "reason": "fixture-only terminal result",
            "evidence_version": "1",
            "completed_at_utc": last_progress,
        })
        for candidate in spec.catalog[:completed_count]
    ]
    decision = run_campaign_cycle(spec, outcomes, last_progress)
    return _signed_state(build_checkpoint(spec, outcomes, decision, last_progress))


@pytest.mark.parametrize("status", ["BUDGET_EXHAUSTED", "RESEARCH_COMPLETE"])
def test_terminal_research_status_is_informational_even_after_progress_age_limit(
    status: str,
) -> None:
    health = evaluate_campaign_health(
        _informational_terminal_state(status, "2026-10-05T00:00:00Z"), NOW, 300
    )

    assert health["status"] == status
    assert health["sos_wake_required"] is False
    assert health["live_delivery_armed"] is False


@pytest.mark.parametrize("status", ["BUDGET_EXHAUSTED", "RESEARCH_COMPLETE"])
def test_future_informational_terminal_state_is_always_blocked(status: str) -> None:
    health = evaluate_campaign_health(
        _informational_terminal_state(status, "2026-10-05T12:00:01Z"), NOW, 300
    )

    assert health["status"] == "BLOCKED"
    assert health["reason"] == "campaign_progress_future_timestamp"
    assert health["sos_wake_required"] is True


@pytest.mark.parametrize("missing_field", ["reason", "sos_wake_required", "live_authorization"])
def test_rehashed_no_edge_checkpoint_missing_decision_invariant_is_blocked(
    missing_field: str,
) -> None:
    state = _no_edge_campaign_state()
    state.pop("digest")
    state["last_decision"].pop(missing_field)

    health = evaluate_campaign_health(_signed_state(state), NOW, 300)

    assert health["status"] == "BLOCKED"
    assert health["sos_wake_required"] is True


def test_watchdog_configuration_cannot_loosen_persisted_campaign_freshness() -> None:
    health = evaluate_campaign_health(
        _campaign_state(
            last_progress="2026-10-05T11:58:00Z",
            progress_max_age_seconds=60,
        ),
        NOW,
        300,
    )

    assert health["status"] == "BLOCKED"
    assert health["reason"] == "campaign_progress_stale"
    assert health["progress_threshold_seconds"] == 60


def test_active_checkpoint_with_empty_completed_history_is_blocked() -> None:
    state = _campaign_state(
        last_progress="2026-10-05T12:00:00Z",
        _completed_count=0,
    )

    health = evaluate_campaign_health(state, NOW, 300)

    assert health["status"] == "BLOCKED"
    assert health["reason"] == "campaign_active_empty_history"
    assert health["sos_wake_required"] is True


def test_canonical_exhausted_no_edge_campaign_is_informational() -> None:
    state = _no_edge_campaign_state()

    health = evaluate_campaign_health(state, NOW, 300)

    assert health["status"] == "NO_EDGE_IN_SCOPE"
    assert health["sos_wake_required"] is False


def test_rehashed_active_checkpoint_cannot_restamp_progress_without_completed_work() -> None:
    old_outcomes = _campaign_state(last_progress="2026-10-05T00:00:00Z")["outcomes"]
    restamped = _campaign_state(
        last_progress="2026-10-05T11:59:00Z", outcomes=old_outcomes,
    )

    health = evaluate_campaign_health(restamped, NOW, 300)

    assert health["status"] == "BLOCKED"
    assert health["reason"] == "campaign_progress_missing_or_unparseable"
    assert health["sos_wake_required"] is True


def test_active_progress_matches_semantically_equivalent_completed_utc_timestamp() -> None:
    outcomes = _campaign_state()["outcomes"]
    outcomes[0]["completed_at_utc"] = "2026-10-05T11:59:00+00:00"

    health = evaluate_campaign_health(_campaign_state(outcomes=outcomes), NOW, 300)

    assert health["status"] == "OK"


def test_rehashed_no_edge_with_nonempty_history_cannot_restamp_progress() -> None:
    old_outcomes = _campaign_state(last_progress="2026-10-05T00:00:00Z")["outcomes"]
    restamped = _no_edge_campaign_state(
        last_progress="2026-10-05T11:59:00Z", outcomes=old_outcomes
    )

    health = evaluate_campaign_health(restamped, NOW, 300)

    assert health["status"] == "BLOCKED"
    assert health["sos_wake_required"] is True


def test_optional_campaign_checkpoint_preserves_default_and_merges_blocked_health(
    tmp_path: Any,
) -> None:
    heartbeat = tmp_path / "heartbeat.json"
    heartbeat.write_text('{"heartbeatAt":"2026-10-05T11:59:00Z"}', encoding="utf-8")

    default_alert = evaluate(heartbeat, 600, NOW)

    assert "campaign_health" not in default_alert
    checkpoint = tmp_path / "campaign_checkpoint.json"
    checkpoint.write_text(
        json.dumps(_campaign_state(last_progress="2026-10-05T00:00:00Z")),
        encoding="utf-8",
    )

    alert = evaluate(
        heartbeat,
        600,
        NOW,
        campaign_state_path=checkpoint,
        campaign_progress_threshold_seconds=300,
    )

    assert alert["status"] == "BLOCKED"
    assert alert["reason"] == "campaign_health:campaign_progress_stale"
    assert alert["campaign_health"]["status"] == "BLOCKED"
    assert alert["sos_wake_required"] is True


def test_inconsistent_history_or_future_progress_fails_closed() -> None:
    repeated_earlier = _campaign_state(
        completed_fingerprints=["old", "old", "completed-1"],
        outcomes=[
            {
                "experiment_fingerprint": "old",
                "stage": "CHEAP_SCREEN",
                "status": "REJECT",
                "reason": "fixture",
                "evidence_version": "1",
                "completed_at_utc": "2026-10-05T10:00:00Z",
            },
            {
                "experiment_fingerprint": "old",
                "stage": "CHEAP_SCREEN",
                "status": "REJECT",
                "reason": "fixture",
                "evidence_version": "1",
                "completed_at_utc": "2026-10-05T10:30:00Z",
            },
            {
                "experiment_fingerprint": "completed-1",
                "stage": "CHEAP_SCREEN",
                "status": "ADVANCE",
                "reason": "fixture",
                "evidence_version": "1",
                "completed_at_utc": "2026-10-05T11:00:00Z",
            },
        ],
    )
    future = _campaign_state(last_progress="2026-10-05T12:01:00Z")

    repeated_health = evaluate_campaign_health(repeated_earlier, NOW, 300)
    future_health = evaluate_campaign_health(future, NOW, 300)

    assert repeated_health["status"] == "BLOCKED"
    assert repeated_health["reason"] == "campaign_completed_fingerprints_duplicate"
    assert future_health["status"] == "BLOCKED"
    assert future_health["reason"] == "campaign_progress_future_timestamp"


def test_malformed_checkpoint_outcome_fails_closed() -> None:
    malformed = _campaign_state(
        outcomes=[{"experiment_fingerprint": "completed-1"}]
    )

    health = evaluate_campaign_health(malformed, NOW, 300)

    assert health["status"] == "BLOCKED"
    assert health["reason"] == "campaign_outcomes_malformed"


def test_campaign_checkpoint_requires_explicit_utc_timestamps() -> None:
    naive_progress = _campaign_state(last_progress="2026-10-05T11:59:00")

    health = evaluate_campaign_health(naive_progress, NOW, 300)

    assert health["status"] == "BLOCKED"
    assert health["reason"] == "campaign_progress_missing_or_unparseable"


def test_watchdog_json_reader_rejects_oversized_and_deeply_nested_files(
    tmp_path,
) -> None:
    from automation.orchestration.research_campaign.aios_research_campaign import (
        MAX_JSON_INPUT_BYTES,
    )

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{} " + b" " * MAX_JSON_INPUT_BYTES)
    deeply_nested = tmp_path / "deeply-nested.json"
    deeply_nested.write_text("[" * 10_000 + "0" + "]" * 10_000, encoding="utf-8")

    assert read_json(oversized) is None
    assert read_json(deeply_nested) is None


def test_watchdog_blocks_oversized_digest_valid_checkpoint() -> None:
    from automation.orchestration.research_campaign.aios_research_campaign import (
        MAX_JSON_INPUT_BYTES,
    )

    checkpoint = _campaign_state()
    checkpoint.pop("digest")
    checkpoint["padding"] = "x" * MAX_JSON_INPUT_BYTES
    oversized = _signed_state(checkpoint)

    health = evaluate_campaign_health(oversized, NOW, 300)

    assert health["status"] == "BLOCKED"
    assert health["reason"] == "campaign_checkpoint_malformed"


def test_rehashed_false_no_edge_decision_is_blocked_by_catalog_replay(tmp_path) -> None:
    from automation.orchestration.research_campaign.aios_research_campaign import (
        CampaignDecision,
        CampaignSpec,
        ExperimentOutcome,
        experiment_fingerprint,
        run_campaign_cycle,
        write_checkpoint,
    )
    import automation.orchestration.research_campaign.aios_research_campaign as campaign_module

    candidate_payload = {
        "market_lane": "FOREX_EURUSD_PRIMARY",
        "strategy_family": "MOMENTUM",
        "instrument": "EUR_USD",
        "session_window": "LONDON",
        "stage": "CHEAP_SCREEN",
        "data_capability": {"pinned": True, "source_id": "fixture-forex", "calendar_id": "forex-eurusd", "cost_model_id": "fixture-costs-v1", "pip_value": 10.0},
        "cost_scenario": "BASELINE",
        "expected_evidence_version": "1",
    }
    catalog = [
        {
            **candidate_payload,
            "experiment_id": "candidate-a",
            "parameter_fingerprint": "params-a",
        },
        {
            **candidate_payload,
            "experiment_id": "candidate-b",
            "parameter_fingerprint": "params-b",
        },
    ]
    spec = CampaignSpec.from_dict({
        "campaign_id": "forex-first-v1",
        "campaign_version": "1",
        "market_lanes": ["FOREX_EURUSD_PRIMARY", "CME_INDEX_FUTURES_COMPARISON"],
        "experiment_budget": 2,
        "edge_gates": {"min_oos_trade_count": 100},
        "freshness": {"progress_max_age_seconds": 60},
        "experiment_catalog": catalog,
    })
    completed = ExperimentOutcome.from_dict({
        "experiment_fingerprint": experiment_fingerprint(spec.catalog[0]),
        "stage": "CHEAP_SCREEN",
        "status": "ADVANCE",
        "reason": "fixture-complete",
        "evidence_version": "1",
        "completed_at_utc": "2026-10-05T00:00:00Z",
    })
    decision = run_campaign_cycle(spec, [completed], "2026-10-05T12:00:00Z")
    assert decision.status == "ADVANCE"
    forged_no_edge = CampaignDecision(
        status="NO_EDGE_IN_SCOPE",
        reason="CAMPAIGN_APPROVED_CATALOG_EXHAUSTED",
        sos_wake_required=False,
    )

    with pytest.raises(campaign_module.CampaignCheckpointError):
        campaign_module.build_checkpoint(
            spec, [completed], forged_no_edge, "2026-10-05T12:00:00Z"
        )

    checkpoint = campaign_module.build_checkpoint(
        spec, [completed], decision, "2026-10-05T12:00:00Z"
    )
    path = write_checkpoint(tmp_path, checkpoint)
    state = json.loads(path.read_text(encoding="utf-8"))
    state.pop("digest")
    state["last_decision"] = forged_no_edge.to_dict()
    state["digest"] = hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    health = evaluate_campaign_health(state, NOW, 300)

    assert health["status"] == "BLOCKED"
    assert health["sos_wake_required"] is True


def test_watchdog_fails_closed_for_non_mapping_routing_context() -> None:
    state = _campaign_state()
    state.pop("digest")
    state["routing_context"] = None

    health = evaluate_campaign_health(_signed_state(state), NOW, 300)

    assert health["status"] == "BLOCKED"
    assert health["sos_wake_required"] is True
