import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "automation" / "orchestration" / "coordination_spine" / "Invoke-AiOsCoordinationSpine.DRY_RUN.ps1"


def run_script(*args: str) -> dict:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(completed.stdout)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def make_recovery(*, readiness: str = "READY_KNOWN", blockers: list[str] | None = None, warnings: list[str] | None = None) -> dict:
    return {
        "schema": "AIOS_RECOVERY_BOOTSTRAP_VIEW.v1",
        "system": "AI_OS",
        "mode": "DRY_RUN",
        "generated_at": "2026-06-10T00:00:00Z",
        "repo_root": "C:\\Dev\\Ai.Os",
        "source_readers": [],
        "marker_present": True,
        "marker_path": "control/cycle/last_marker.json",
        "marker_freshness_status": "FRESH",
        "marker_age_seconds": 1,
        "queue_index_present": True,
        "queue_counts": {"QUEUED": 1, "RUNNING": 0, "BLOCKED": 0, "WAITING_APPROVAL": 0, "COMPLETE": 1, "FAILED": 0, "ARCHIVED": 0},
        "lock_status_present": True,
        "held_locks_count": 0,
        "stale_locks_count": 0,
        "collision_count": 0,
        "active_packet_count": 0,
        "blocked_packet_count": 0,
        "heartbeat_status": "OK",
        "recovery_readiness": readiness,
        "blockers": blockers or [],
        "warnings": warnings or [],
        "write_behavior": "telemetry_only",
    }


def write_recovery_payload(path: Path, readiness: str = "READY_KNOWN") -> None:
    write_json(path, make_recovery(readiness=readiness))


def test_readable_recovery_source_is_marked_present(tmp_path: Path) -> None:
    queue_index = tmp_path / "telemetry" / "coordination_spine" / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "telemetry" / "coordination_spine" / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "telemetry" / "coordination_spine" / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "telemetry" / "coordination_spine" / "LEAD_DISPATCH_VIEW.json"
    packet_factory_view = tmp_path / "telemetry" / "coordination_spine" / "PACKET_FACTORY_VIEW.json"

    write_json(queue_index, {"packet_count": 0, "normalized_state_counts": {"QUEUED": 0, "RUNNING": 0, "BLOCKED": 0, "WAITING_APPROVAL": 0, "COMPLETE": 1, "FAILED": 0, "ARCHIVED": 0}})
    write_json(lock_status, {"held_locks_count": 0, "stale_locks_count": 0, "collision_count": 0, "safety_status": "PASS", "write_behavior": "telemetry_only"})
    write_recovery_payload(recovery_view, readiness="READY_KNOWN")
    write_json(lead_dispatch_view, {"dispatcher_safety_verdict": "SAFE_NO_WORK", "next_safe_action": "No action.", "write_behavior": "telemetry_only"})
    write_json(
        packet_factory_view,
        {
            "schema": "AIOS_PACKET_FACTORY_VIEW.v1",
            "system": "AI_OS",
            "mode": "DRY_RUN",
            "generated_at": "2026-06-09T00:00:00Z",
            "repo_root": str(REPO_ROOT),
            "packet_factory_safety_verdict": "REVIEW_REQUIRED",
            "write_path_enabled": False,
            "write_behavior": "telemetry_only",
            "proposed_packet_count": 0,
            "active_packet_count": 0,
            "queue_context_summary": {"present": True, "packet_count": 0, "normalized_state_counts": {}, "source_state_counts": {}},
            "lock_context_summary": {"present": True, "held_locks_count": 0, "stale_locks_count": 0, "collision_count": 0, "safety_status": "PASS", "write_behavior": "telemetry_only"},
            "approval_required_items": [],
            "missing_required_fields": [],
            "duplicate_intent_findings": [],
        },
    )

    result = run_script(
        "-RepoRoot",
        str(tmp_path),
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-LeadDispatchViewPath",
        str(lead_dispatch_view),
        "-PacketFactoryViewPath",
        str(packet_factory_view),
    )

    assert result["recovery_summary"]["present"] is True
    assert result["recovery_summary"]["freshness_status"] in {"FRESH", "STALE"}
    assert "recovery_source_unreadable" not in result["blockers"]
    assert result["approval_gate_status"] != "BLOCKED"


def test_missing_recovery_source_reports_unreadable_blocker(tmp_path: Path) -> None:
    queue_index = tmp_path / "telemetry" / "coordination_spine" / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "telemetry" / "coordination_spine" / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "telemetry" / "coordination_spine" / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "telemetry" / "coordination_spine" / "LEAD_DISPATCH_VIEW.json"

    write_json(queue_index, {"packet_count": 0, "normalized_state_counts": {"QUEUED": 0, "RUNNING": 0, "BLOCKED": 0, "WAITING_APPROVAL": 0, "COMPLETE": 0, "FAILED": 0, "ARCHIVED": 0}})
    write_json(lock_status, {"held_locks_count": 0, "stale_locks_count": 0, "collision_count": 0, "safety_status": "PASS", "write_behavior": "telemetry_only"})
    write_json(lead_dispatch_view, {"dispatcher_safety_verdict": "SAFE_NO_WORK", "next_safe_action": "No action.", "write_behavior": "telemetry_only"})

    result = run_script(
        "-RepoRoot",
        str(tmp_path),
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-LeadDispatchViewPath",
        str(lead_dispatch_view),
        "-PacketFactoryViewPath",
        str(tmp_path / "telemetry" / "coordination_spine" / "PACKET_FACTORY_VIEW.json"),
    )

    assert result["recovery_summary"]["present"] is False
    assert result["recovery_summary"]["freshness_status"] in {"MISSING", "UNREADABLE"}
    assert result["blockers"]
    assert "recovery_source_unreadable" in result["blockers"] or "recovery_source_missing" in result["blockers"]
