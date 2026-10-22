from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from automation.orchestration.aios_consolidated_autonomy_self_audit_routing_repair import (
    build_next_packet,
    classify_blocker,
    discover_blockers,
    route_tests,
    run_cycle,
    select_repair,
)


def _seed_repo(tmp_path: Path) -> Path:
    report_dir = tmp_path / "Reports" / "forex_delivery"
    report_dir.mkdir(parents=True)
    (report_dir / "AIOS_FOREX_WORKFLOW_AUTONOMY_ROUTER_V1_STATE.json").write_text(
        json.dumps({"active_blockers": ["kill_switch_state", "daily_stop_state"], "blockers": ["validator_gap"]}),
        encoding="utf-8",
    )
    (report_dir / "readiness_state_recalculation_v1_report.json").write_text(
        json.dumps({"blockers": ["test_gap"]}),
        encoding="utf-8",
    )
    (report_dir / "AIOS_FOREX_WORKFLOW_AUTONOMY_ROUTER_NEXT_CODEX_PACKET_V1.md").write_text(
        "kill_switch_state monitoring_ready",
        encoding="utf-8",
    )
    return tmp_path


def test_blocker_discovery_and_external_classification(tmp_path: Path) -> None:
    blockers = discover_blockers(_seed_repo(tmp_path))
    names = {item.name for item in blockers}
    assert {"kill_switch_state", "daily_stop_state", "validator_gap", "test_gap", "monitoring_ready"} <= names
    assert classify_blocker("owner evidence missing", "x").classification == "external"


def test_roi_ranking_and_dependency_ordering(tmp_path: Path) -> None:
    blockers = discover_blockers(_seed_repo(tmp_path))
    ranked = [(item.roi, item.dependency_rank) for item in blockers]
    assert ranked == sorted(ranked, key=lambda item: (-item[0], item[1]))


def test_safe_repair_selection_prefers_repository_fixable(tmp_path: Path) -> None:
    selected = select_repair(discover_blockers(_seed_repo(tmp_path)))
    assert selected["selected"] is True
    assert selected["candidate"]["classification"] == "repository_fixable"


def test_test_routing_checkpoint_resume_and_packet_generation(tmp_path: Path) -> None:
    state = run_cycle(_seed_repo(tmp_path), write=True, generated_at_utc=datetime(2026, 8, 5, tzinfo=timezone.utc))
    assert state["checkpoint_status"] == "written"
    assert state["resume_status"] == "stop_after_one_cycle"
    assert state["finite_cycle_confirmed"] is True
    assert state["no_execution_authority"] is True
    assert "tests/orchestration" in "\n".join(route_tests(state["selected_repair"]))
    assert state["next_generated_packet"].startswith("CODEX-ONLY PROMPT\n\nAI_OS EXECUTION TOKEN")
    assert "STOP POINT" in state["next_generated_packet"]
    for rel in state["output_paths"].values():
        assert (tmp_path / rel).exists()


def test_next_packet_dry_run_when_no_repo_fixable_blocker(tmp_path: Path) -> None:
    packet = build_next_packet(tmp_path, {"selected": False, "reason_code": "no_repository_fixable_blocker"}, ["pytest"])
    assert "MODE: DRY_RUN" in packet
    assert "Human Owner Anthony" in packet
