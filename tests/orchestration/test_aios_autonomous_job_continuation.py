from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "automation" / "orchestration" / "continuation" / "aios_autonomous_job_continuation.py"
FIXED_NOW = "2026-06-16T12:00:00Z"


def test_research_owner_observation_requires_identity_progress_and_freshness():
    project = _load().project_research_observation
    now = 1000.
    record = {"schema": "S6_RESEARCH_OWNER_OBSERVATION.v1", "owner": "EXISTING_GOAL_MUSCLE98",
              "role": "MARKET", "source_pins_checked": True, "phase": "SCORING",
              "worker_identity": "EAST_OCC_97_S6", "job": "FIXTURE", "active_workers": 1,
              "heartbeat_at": 999., "useful_progress_at": 900., "metadata_saved_at": 999.,
              "last_accepted_at": 850., "queue_size": 3}
    assert project(record, now=now)["state"] == "ACTIVE_OWNER_REPORTED"
    assert project({**record, "useful_progress_at": 600.}, now=now)["state"] == "STALLED"
    assert project({**record, "heartbeat_at": 960.}, now=now)["active_workers"] is None
    assert project({**record, "heartbeat_at": 1001.}, now=now)["state"] == "STALE"
    for change in ({"role": "BUILDER"}, {"source_pins_checked": False}, {"worker_identity": "unsafe/path"}):
        assert project({**record, **change}, now=now)["active_workers"] is None
    assert project(None, now=now)["state"] == "UNKNOWN"
    assert project({**record, "phase": "WAITING_FOR_OWNER"}, now=now)["active_workers"] == 0


def _load():
    spec = importlib.util.spec_from_file_location("aios_autonomous_job_continuation", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _security(
    *,
    state: str = "CLEAR",
    safe_for_dry_run: bool = True,
    safe_for_apply: bool = False,
    sos_required: bool = False,
    stop_required: bool = False,
    review_required: bool = False,
) -> dict[str, Any]:
    return {
        "schema": "AIOS_PREEMPTIVE_SECURITY_STATE.v1",
        "overall_state": state,
        "safe_for_dry_run": safe_for_dry_run,
        "safe_for_apply": safe_for_apply,
        "sos_required": sos_required,
        "stop_required": stop_required,
        "review_required": review_required,
        "events": [],
        "next_safe_action": f"{state} fixture next action.",
    }


def _dirty(
    *,
    overall: str = "CLEAN",
    dirty_count: int = 0,
    safe_for_dry_run: bool = True,
    safe_for_apply: bool = True,
    sos_required: bool = False,
    protected_stop_required: bool = False,
    review_required: bool = False,
) -> dict[str, Any]:
    return {
        "schema": "AIOS_DIRTY_TREE_CLASSIFIER_RESULT.v1",
        "overall_classification": overall,
        "dirty_count": dirty_count,
        "safe_for_dry_run": safe_for_dry_run,
        "safe_for_apply": safe_for_apply,
        "sos_required": sos_required,
        "protected_stop_required": protected_stop_required,
        "review_required": review_required,
        "dirty_files": [],
    }


def _governor(
    *,
    task_id: str = "safe_dry_run",
    lane: str = "DRY_RUN",
    mode: str = "DRY_RUN",
    title: str = "Inspect continuation evidence.",
    blocked: bool = False,
    blocked_reason: str | None = None,
    allowed_paths: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "decision_id": "AIOS-ADG-fixture",
        "selected_candidate_id": task_id,
        "next_highest_value_task": title,
        "decision_category": "STATUS_RECON",
        "allowed_lane": lane,
        "required_validators": ["Fixture validator"],
        "blocked": blocked,
        "blocked_reason": blocked_reason,
        "recommended_packet_scope": {
            "packet_id_suggestion": f"AIOS-{task_id.upper()}",
            "mode": mode,
            "lane": lane,
            "files_allowed": allowed_paths or ["automation/orchestration/continuation/"],
            "files_forbidden": ["secrets/", ".env", "broker credentials"],
        },
    }


def _state(module, **overrides):
    evidence = module.build_evidence(
        repo_root="fixture",
        branch="main",
        dirty_tree=overrides.get("dirty_tree", _dirty()),
        security_state=overrides.get("security_state", _security()),
        governor_decision=overrides.get("governor_decision", _governor()),
        approval_gate=overrides.get("approval_gate"),
        approval_inbox=overrides.get("approval_inbox"),
        validator_evidence=overrides.get("validator_evidence", {"status": "pass"}),
        repair_result=overrides.get("repair_result"),
        generated_at_utc=FIXED_NOW,
    )
    return module.build_continuation_state(
        evidence=evidence,
        previous_state=overrides.get("previous_state"),
        generated_at_utc=FIXED_NOW,
    )


def test_clear_dry_run_candidate_continues_without_mutation() -> None:
    module = _load()

    state = _state(module)

    assert state["schema"] == "AIOS_AUTONOMOUS_JOB_CONTINUATION_STATE.v1"
    assert state["state"] == "CONTINUE"
    assert state["safe_to_continue_without_human"] is True
    assert state["execution"]["executed_commands"] == []
    assert state["execution"]["mutation_performed"] is False
    assert state["execution"]["apply_performed"] is False
    assert state["safety"]["git_commit_allowed"] is False


def test_security_stop_blocks_without_bypass() -> None:
    module = _load()

    state = _state(module, security_state=_security(state="STOP", safe_for_dry_run=False, stop_required=True))

    assert state["state"] == "STOP"
    assert state["stop_reason"] == "security_stop"
    assert state["safe_to_continue_without_human"] is False


def test_security_sos_emergency_stops() -> None:
    module = _load()

    state = _state(module, security_state=_security(state="SOS", safe_for_dry_run=False, sos_required=True))

    assert state["state"] == "SOS"
    assert state["stop_reason"] == "security_sos"
    assert "SOS" in state["next_safe_action"]


def test_watch_security_allows_dry_run_only() -> None:
    module = _load()

    dry_run = _state(module, security_state=_security(state="WATCH"))
    read_only = _state(
        module,
        security_state=_security(state="WATCH"),
        governor_decision=_governor(lane="READ_ONLY", mode="READ_ONLY"),
    )

    assert dry_run["state"] == "CONTINUE"
    assert read_only["state"] == "REVIEW_REQUIRED"
    assert read_only["stop_reason"] == "security_watch_requires_dry_run"


def test_dirty_sos_can_continue_only_when_preemptive_security_reduces_to_watch() -> None:
    module = _load()

    state = _state(
        module,
        security_state=_security(state="WATCH"),
        dirty_tree=_dirty(
            overall="SECURITY_SOS_DIRTY",
            dirty_count=2,
            safe_for_dry_run=False,
            safe_for_apply=False,
            sos_required=True,
        ),
    )

    assert state["state"] == "CONTINUE"
    assert state["security_snapshot"]["overall_state"] == "WATCH"


def test_protected_dirty_stops() -> None:
    module = _load()

    state = _state(
        module,
        dirty_tree=_dirty(
            overall="PROTECTED_AUTHORITY_DIRTY",
            dirty_count=1,
            safe_for_dry_run=False,
            safe_for_apply=False,
            protected_stop_required=True,
        ),
    )

    assert state["state"] == "STOP"
    assert state["stop_reason"] == "dirty_tree_protected_authority"


def test_apply_candidate_never_auto_runs() -> None:
    module = _load()

    state = _state(module, governor_decision=_governor(lane="APPLY_CODE_SAFE", mode="APPLY"))

    assert state["state"] == "REVIEW_REQUIRED"
    assert state["stop_reason"] == "non_dry_run_task"
    assert state["safety"]["apply_allowed"] is False


def test_approval_required_routes_to_review() -> None:
    module = _load()

    state = _state(module, approval_gate={"approval_status": "pending"})

    assert state["state"] == "REVIEW_REQUIRED"
    assert state["stop_reason"] == "approval_required"
    assert state["approval_snapshot"]["approval_required"] is True


def test_one_repair_attempt_can_continue_after_post_repair_pass() -> None:
    module = _load()

    state = _state(module, validator_evidence={"status": "failed"}, repair_result={"status": "pass"})

    assert state["state"] == "CONTINUE"
    assert state["repair_count"] == 1
    assert "REPAIR_ATTEMPT" in state["state_history"]


def test_one_repair_attempt_exhausts_on_second_failure() -> None:
    module = _load()

    state = _state(module, validator_evidence={"status": "failed"}, previous_state={"repair_count": 1})

    assert state["state"] == "STOP"
    assert state["repair_count"] == 1
    assert state["stop_reason"] == "validator_exhaustion"


def test_resume_mismatch_requires_review() -> None:
    module = _load()

    state = _state(
        module,
        previous_state={
            "repo_root": "fixture",
            "branch": "main",
            "dirty_signature": "changed",
            "security_signature": "changed",
            "task_signature": "changed",
        },
    )

    assert state["state"] == "REVIEW_REQUIRED"
    assert state["stop_reason"] == "resume_mismatch"
    assert state["resume"]["can_resume"] is False


def test_evidence_contract_preserves_required_snapshots() -> None:
    module = _load()

    state = _state(module)

    assert state["evidence"]["schema"] == "AIOS_AUTONOMOUS_JOB_CONTINUATION_EVIDENCE.v1"
    assert state["cycle_id"].startswith("AIOS-AJC-")
    assert state["selected_task"]["task_id"] == "safe_dry_run"
    assert state["dirty_signature"]
    assert state["security_signature"]
    assert state["task_signature"]
