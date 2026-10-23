from __future__ import annotations

import json
import sys
import tempfile
import secrets
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from autonomy_bridge import build_bridge_state, classify_item, collect_source_files


SAFETY_ORDER = {"PASS": 0, "UNKNOWN": 1, "WARN": 2, "NEEDS_APPROVAL": 3, "BLOCKED": 4}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_operation_glue_approval_reaches_must_see(tmp_path: Path) -> None:
    approval_path = tmp_path / "control" / "operation_glue" / "APPROVAL_INBOX.json"
    write_json(
        approval_path,
        {
            "schema": "AIOS_OPERATION_GLUE_APPROVAL_INBOX.v0_1",
            "status": "WAITING_APPROVAL",
            "item_count": 1,
            "approval_required_count": 1,
            "entries": [
                {
                    "item_id": "APPROVAL_ITEM_SMOKE",
                    "status": "WAITING_APPROVAL",
                    "approval_required": True,
                    "reason": "Smoke Glue item requires Human Owner review.",
                    "next_safe_action": "Review Glue approval before execution.",
                }
            ],
            "next_safe_action": "Review Glue approval before execution.",
        },
    )

    result_path = tmp_path / "telemetry" / "operation_glue" / "worker_results" / "WORKER_RESULT_SMOKE.json"
    write_json(
        result_path,
        {
            "schema": "AIOS_OPERATION_GLUE_WORKER_RESULT.v0_1",
            "status": "PASS",
            "summary": "Worker result exists so Glue telemetry is visible.",
        },
    )

    source_paths = {path.relative_to(tmp_path).as_posix() for path in collect_source_files(tmp_path)}
    assert "control/operation_glue/APPROVAL_INBOX.json" in source_paths
    assert "telemetry/operation_glue/worker_results/WORKER_RESULT_SMOKE.json" in source_paths

    state = build_bridge_state(tmp_path)

    glue_approval = [
        item
        for item in state["items_needing_approval"]
        if item["source_path"] == "control/operation_glue/APPROVAL_INBOX.json"
    ]
    assert glue_approval
    assert glue_approval[0]["status"] == "NEEDS_APPROVAL"
    assert glue_approval[0]["status"] != "PASS"
    assert state["approval_needed_count"] >= 1
    assert "Review Glue approval before execution." in state["must_see"]


def test_glue_approval_classification_prefers_safer_status() -> None:
    classification = classify_item(
        {
            "source_path": "control/operation_glue/APPROVAL_INBOX.json",
            "status": "READY_FOR_NEXT_SAFE_ACTION",
            "text": json.dumps(
                {
                    "entries": [
                        {
                            "status": "WAITING_APPROVAL",
                            "approval_required": True,
                            "reason": "Human approval required.",
                        }
                    ]
                }
            ),
        }
    )

    assert classification["status"] == "NEEDS_APPROVAL"
    assert classification["status"] != "PASS"


def test_explicit_blocked_status_beats_pass_text() -> None:
    classification = classify_item(
        {
            "source_path": "relay/inbox/current-blocked.task.json",
            "status": "BLOCKED",
            "summary": "Worker says PASS and complete.",
        }
    )

    assert classification["status"] == "BLOCKED"


def test_explicit_risk_and_gate_flags_are_safe() -> None:
    classification = classify_item(
        {
            "source_path": "control/operation_glue/APPROVAL_INBOX.json",
            "status": "PASS",
            "risk_level": "HIGH",
            "gate_flags": ["HUMAN_APPROVAL_REQUIRED"],
            "summary": "Looks routine.",
        }
    )

    assert classification["status"] == "NEEDS_APPROVAL"


def test_new_blocker_language_is_not_pass() -> None:
    classification = classify_item(
        {
            "source_path": "relay/inbox/new.task.txt",
            "summary": "Execute live trading through broker execution immediately.",
        }
    )

    assert classification["status"] == "BLOCKED"


def test_ambiguous_input_defaults_safe() -> None:
    classification = classify_item({"source_path": "telemetry/unknown/item.json", "summary": "unclear"})

    assert classification["status"] == "NEEDS_APPROVAL"
    assert classification["status"] != "PASS"


def test_prior_cases_same_or_safer() -> None:
    cases = [
        ({"source_path": "relay/error/danger.task.txt", "summary": "Please place a buy order for EURUSD live now."}, "BLOCKED"),
        ({"source_path": "relay/inbox/current.task.json", "status": "WAITING"}, "NEEDS_APPROVAL"),
        ({"source_path": "relay/done/example.task.json", "status": "PASS"}, "PASS"),
        ({"source_path": "relay/outbox/repo-summary.report.txt", "summary": "review stale unknown"}, "WARN"),
    ]

    for item, previous_status in cases:
        current = classify_item(item)["status"]
        assert SAFETY_ORDER[current] >= SAFETY_ORDER[previous_status]


def test_reference_schema_does_not_become_current_blocker() -> None:
    classification = classify_item(
        {
            "source_path": "automation/orchestration/night_supervisor/NIGHT_SUPERVISOR_REPORT.schema.json",
            "status": "BLOCKED",
            "summary": "Safety text mentions broker, OANDA, API key, and real order boundaries.",
        }
    )

    assert classification["status"] == "WARN"
    assert classification["category"] == "reference_evidence"


def test_stale_relay_approval_is_historical_warning() -> None:
    classification = classify_item(
        {
            "source_path": "relay/approvals/20260530-165828-dirty-repo.approval.md",
            "status": "BLOCKED",
            "summary": "Risk level: blocker. Historical dirty repo approval from 2026-05-30.",
        }
    )

    assert classification["status"] == "WARN"
    assert classification["category"] == "historical_evidence"


def test_projection_state_does_not_self_block() -> None:
    classification = classify_item(
        {
            "source_path": "telemetry/night_supervisor/AUTONOMY_BRIDGE_STATE.json",
            "supervisor_status": "BLOCKED",
            "plain_summary": "16 blocked items were seen in a prior bridge projection.",
        }
    )

    assert classification["status"] == "WARN"
    assert classification["category"] == "reference_evidence"


def test_current_scheduler_request_stays_blocked() -> None:
    classification = classify_item(
        {
            "source_path": "relay/approvals/register-night-scheduler.approval.md",
            "status": "WAITING",
            "summary": "Approval request to create a scheduler task for unattended operation.",
        }
    )

    assert classification["status"] == "BLOCKED"


def test_relay_readme_is_reference_warning() -> None:
    classification = classify_item(
        {
            "source_path": "relay/README.md",
            "summary": "Relay documentation mentions approval and protected action flow.",
        }
    )

    assert classification["status"] == "WARN"
    assert classification["category"] == "reference_evidence"


def test_relay_example_approval_is_reference_warning() -> None:
    classification = classify_item(
        {
            "source_path": "relay/approvals/example.approval.json",
            "status": "WAITING",
            "summary": "Example approval packet proposes git add -A for demonstration only.",
        }
    )

    assert classification["status"] == "WARN"
    assert classification["category"] == "reference_evidence"


def test_historical_relay_goal_approval_is_warning() -> None:
    classification = classify_item(
        {
            "source_path": "relay/approvals/g-push-the-validator-to-main.approval.json",
            "status": "WAITING",
            "summary": "Historical goal approval requests commit and push review.",
        }
    )

    assert classification["status"] == "WARN"
    assert classification["category"] == "historical_evidence"


def test_relay_done_task_is_historical_warning() -> None:
    classification = classify_item(
        {
            "source_path": "relay/done/g-goal-review-waiting-approval-items-plan.task.json",
            "status": "WAITING_APPROVAL",
            "summary": "Completed planning task still mentions waiting approval items.",
        }
    )

    assert classification["status"] == "WARN"
    assert classification["category"] == "historical_evidence"


def test_relay_log_state_is_historical_warning() -> None:
    classification = classify_item(
        {
            "source_path": "relay/logs/disk_alert_state.json",
            "summary": "Runtime log state has no active approval request.",
        }
    )

    assert classification["status"] == "WARN"
    assert classification["category"] == "historical_evidence"


class AutonomyBridgeGlueTests(unittest.TestCase):
    def test_operation_glue_approval_reaches_must_see(self) -> None:
        base = Path(tempfile.gettempdir()) / "aios_pytest_workspace" / "autonomy_bridge"
        base.mkdir(parents=True, exist_ok=True)
        temp_dir = base / secrets.token_hex(8)
        temp_dir.mkdir(parents=True, exist_ok=False)
        try:
            test_operation_glue_approval_reaches_must_see(temp_dir)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_glue_approval_classification_prefers_safer_status(self) -> None:
        test_glue_approval_classification_prefers_safer_status()

    def test_explicit_blocked_status_beats_pass_text(self) -> None:
        test_explicit_blocked_status_beats_pass_text()

    def test_explicit_risk_and_gate_flags_are_safe(self) -> None:
        test_explicit_risk_and_gate_flags_are_safe()

    def test_new_blocker_language_is_not_pass(self) -> None:
        test_new_blocker_language_is_not_pass()

    def test_ambiguous_input_defaults_safe(self) -> None:
        test_ambiguous_input_defaults_safe()

    def test_prior_cases_same_or_safer(self) -> None:
        test_prior_cases_same_or_safer()

    def test_reference_schema_does_not_become_current_blocker(self) -> None:
        test_reference_schema_does_not_become_current_blocker()

    def test_stale_relay_approval_is_historical_warning(self) -> None:
        test_stale_relay_approval_is_historical_warning()

    def test_projection_state_does_not_self_block(self) -> None:
        test_projection_state_does_not_self_block()

    def test_current_scheduler_request_stays_blocked(self) -> None:
        test_current_scheduler_request_stays_blocked()

    def test_relay_readme_is_reference_warning(self) -> None:
        test_relay_readme_is_reference_warning()

    def test_relay_example_approval_is_reference_warning(self) -> None:
        test_relay_example_approval_is_reference_warning()

    def test_historical_relay_goal_approval_is_warning(self) -> None:
        test_historical_relay_goal_approval_is_warning()

    def test_relay_done_task_is_historical_warning(self) -> None:
        test_relay_done_task_is_historical_warning()

    def test_relay_log_state_is_historical_warning(self) -> None:
        test_relay_log_state_is_historical_warning()


if __name__ == "__main__":
    unittest.main()
