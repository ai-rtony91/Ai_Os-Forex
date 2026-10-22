from __future__ import annotations

import json
from pathlib import Path

import pytest

from automation.orchestration.aios_engineering_velocity_forecast_v1 import (
    build_forecast, completion_credit, load_event_log, pert_expected, percentile, stable_json,
)

AS_OF = "2026-08-06T12:00:00Z"
CAL = {"typical_task_duration_minutes": 20, "provenance": "HUMAN_OWNER_REPORTED", "confidence": "LOW", "minimum_measured_samples_to_override": 5}


def event(index: int, minutes: float, lane: str = "lane") -> dict[str, object]:
    return {"event_id": f"e{index}", "event_type": "TASK_COMPLETED", "timestamp_utc": f"2026-08-0{index + 1}T10:00:00Z", "task_id": f"t{index}", "elapsed_seconds": minutes * 60, "lane": lane}


def project(**extra: object) -> dict[str, object]:
    value: dict[str, object] = {"forecast_target": "repository completion", "hierarchy": {"program": "p"}, "lane": "lane", "remaining_work": [{"id": "a", "category": "repository_fixable"}], "dependencies": []}
    value.update(extra); return value


def forecast(events=(), **kwargs):
    return build_forecast(project(**kwargs), events, calibration=CAL, as_of_utc=AS_OF)


def test_empty_history_is_insufficient_and_owner_calibration_is_low():
    state = forecast()
    assert state["confidence_label"] == "INSUFFICIENT_DATA"
    assert state["estimated_active_engineering_minutes"]["best"] == 20
    assert state["evidence_provenance"]["owner_calibration"]["provenance"] == "HUMAN_OWNER_REPORTED"


def test_five_measured_lane_tasks_override_owner_and_statistics_are_deterministic():
    state = forecast([event(i, value) for i, value in enumerate([10, 20, 30, 40, 50])])
    stats = state["observed_velocity"]["task_duration_minutes"]
    assert (stats["median"], stats["p25"], stats["p75"], stats["p90"]) == (30, 20, 40, 46)
    assert state["observed_velocity"]["selected_duration_source"] == "LANE_MEASURED_HISTORY"
    assert percentile([50, 10, 30, 20, 40], 90) == 46


@pytest.mark.parametrize("item", [{"state": "OPEN", "validated": True}, {"state": "CLOSED", "merged": False, "validated": True}, {"state": "MERGED", "validated": False}])
def test_unmerged_or_unvalidated_work_gets_no_credit(item):
    assert completion_credit(item) is False


def test_merged_validated_work_gets_credit():
    assert completion_credit({"state": "MERGED", "validated": True}) is True


def test_codex_receipts_supply_measured_duration_and_pr_without_created_time_is_safe():
    tasks = [
        {"packet_id": f"packet-{index}", "elapsed_seconds": minutes * 60, "lane": "lane"}
        for index, minutes in enumerate([11, 12, 13, 14, 15])
    ]
    state = build_forecast(
        project(), github_pr_metadata=[{"pr_number": 1364, "state": "MERGED", "merged_at": AS_OF}],
        codex_task_metadata=tasks, calibration=CAL, as_of_utc=AS_OF,
    )
    assert state["observed_velocity"]["selected_duration_source"] == "LANE_MEASURED_HISTORY"
    assert state["observed_velocity"]["task_duration_minutes"]["median"] == 13
    assert state["observed_velocity"]["merged_pr_lead_time_minutes"]["sample_count"] == 0
    assert "CODEX_TASK_METADATA" not in state["data_sources_missing"]


def test_external_wait_is_separate_and_unknown_prevents_date():
    state = forecast(remaining_work=[{"id": "a", "category": "repository_fixable"}, {"id": "gate", "category": "external_evidence", "wait_minutes": None}])
    assert state["estimated_active_engineering_minutes"]["best"] == 20
    assert set(state["estimated_calendar_completion_range"].values()) == {"UNKNOWN"}


def test_pert_and_lane_fallback():
    assert pert_expected(10, 20, 40) == pytest.approx(21.667)
    events = [event(i, 10 + i, "other") for i in range(5)]
    assert forecast(events)["observed_velocity"]["selected_duration_source"] == "REPOSITORY_MEASURED_HISTORY"


def test_dependency_cycle_fails_closed_and_path_is_deterministic():
    with pytest.raises(ValueError, match="cycle"):
        forecast(dependencies=[{"upstream": "a", "downstream": "b"}, {"upstream": "b", "downstream": "a"}])
    state = forecast(dependencies=[{"upstream": "a", "downstream": "b"}, {"upstream": "b", "downstream": "c"}])
    assert state["critical_path"] == ["a", "b", "c"]


def test_duplicates_conflicts_timestamps_numbers_and_sensitive_values_fail_closed(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    path.write_text('\n'.join([json.dumps(event(0, 20)), json.dumps(event(0, 30))]), encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting"):
        load_event_log(path)
    for payload, message in [({"event_id": "x", "event_type": "TASK_COMPLETED", "timestamp_utc": "bad", "elapsed_seconds": 10}, "timestamp"), ({"event_id": "x", "event_type": "TASK_COMPLETED", "timestamp_utc": AS_OF, "elapsed_seconds": float("inf")}, "finite"), ({"event_id": "x", "event_type": "TASK_COMPLETED", "timestamp_utc": AS_OF, "account_id": "private"}, "private")]:
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match=message): load_event_log(path)


def test_first_dollar_distinct_byte_stable_and_no_protected_behavior():
    first, second = forecast(), forecast()
    assert stable_json(first) == stable_json(second)
    assert first["first_withdrawable_dollar_status"] == "DISTINCT_MILESTONE_NOT_INFERRED"
    assert not any(first["protected_actions"].values())
    text = stable_json(first).lower()
    assert "credential" not in text and "account_id" not in text
