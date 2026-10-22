import json
import os
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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_queue(*, packet_count: int, queued: int = 0, running: int = 0, blocked: int = 0, waiting: int = 0, complete: int = 0) -> dict:
    return {
        "schema": "AIOS_UNIFIED_QUEUE_INDEX.v1",
        "packet_count": packet_count,
        "normalized_state_counts": {
            "QUEUED": queued,
            "RUNNING": running,
            "BLOCKED": blocked,
            "WAITING_APPROVAL": waiting,
            "COMPLETE": complete,
            "FAILED": 0,
            "ARCHIVED": 0,
        },
        "source_state_counts": {},
    }


def make_lock(*, held: int = 0, stale: int = 0, collision: int = 0, safety: str = "PASS") -> dict:
    return {
        "held_locks_count": held,
        "stale_locks_count": stale,
        "collision_count": collision,
        "safety_status": safety,
        "write_behavior": "telemetry_only",
    }


def make_recovery(*, readiness: str = "READY_KNOWN", blockers: list[str] | None = None, warnings: list[str] | None = None) -> dict:
    return {
        "recovery_readiness": readiness,
        "blockers": blockers or [],
        "warnings": warnings or [],
        "heartbeat_status": "HEALTHY",
        "write_behavior": "telemetry_only",
    }


def make_dispatch(*, verdict: str = "SAFE_NO_WORK", blocked_reason: str | None = None, depends_on_t2b: bool = True) -> dict:
    return {
        "dispatcher_safety_verdict": verdict,
        "blocked_reason": blocked_reason,
        "depends_on_t2b": depends_on_t2b,
        "write_behavior": "telemetry_only",
        "next_safe_action": "Proceed cautiously." if verdict == "SAFE_NO_WORK" else "Resolve blockers before dispatch.",
    }


def make_packet_factory(*, verdict: str = "SAFE_NO_WORK") -> dict:
    return {
        "schema": "AIOS_PACKET_FACTORY_VIEW.v1",
        "system": "AI_OS",
        "mode": "DRY_RUN",
        "generated_at": "2026-06-09T00:00:00Z",
        "repo_root": str(REPO_ROOT),
        "proposed_packet_count": 0,
        "active_packet_count": 0,
        "packet_template_count": 0,
        "duplicate_intent_findings": [],
        "missing_required_fields": [],
        "approval_required_items": [],
        "queue_context_summary": {"present": True, "packet_count": 0, "normalized_state_counts": {}, "source_state_counts": {}},
        "lock_context_summary": {"present": True, "held_locks_count": 0, "stale_locks_count": 0, "collision_count": 0, "safety_status": "PASS", "write_behavior": "telemetry_only"},
        "recovery_context_summary": {"present": True, "recovery_readiness": "READY_KNOWN", "blockers": [], "warnings": [], "heartbeat_status": "HEALTHY", "write_behavior": "telemetry_only"},
        "lead_dispatch_context_summary": {"present": True, "dispatcher_safety_verdict": "SAFE_NO_WORK", "blocked_reason": "", "depends_on_t2b": True, "next_safe_action": "Proceed cautiously."},
        "packet_factory_safety_verdict": verdict,
        "write_path_enabled": False,
        "write_behavior": "telemetry_only",
        "recommended_next_packet_action": "Draft the next packet using the current templates and approval chain.",
        "blockers": [],
        "warnings": [],
    }


def write_old(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("old", encoding="utf-8")
    old_time = 1_600_000_000
    os.utime(path, (old_time, old_time))


def test_all_sources_present_produces_composed_cockpit_view(tmp_path: Path) -> None:
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "LEAD_DISPATCH_VIEW.json"
    packet_factory_view = tmp_path / "PACKET_FACTORY_VIEW.json"

    write_json(queue_index, make_queue(packet_count=0))
    write_json(lock_status, make_lock())
    write_json(recovery_view, make_recovery())
    write_json(lead_dispatch_view, make_dispatch())
    write_json(packet_factory_view, make_packet_factory())

    result = run_script(
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
        "-OutputPath",
        str(tmp_path / "COORDINATION_SPINE_VIEW.json"),
    )

    assert result["approval_gate_status"] in {"SAFE_NO_WORK", "REVIEW_REQUIRED"}
    assert result["module5b_status"] == "unknown"
    assert result["t2b_status"] == "prerequisite_only"
    assert result["live_dispatch_status"] == "BLOCKED"
    assert result["write_path_enabled"] is False
    assert result["write_behavior"] == "telemetry_only"
    assert result["packet_factory_summary"]["present"] is True


def test_missing_source_fails_closed_to_review_required(tmp_path: Path) -> None:
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "LEAD_DISPATCH_VIEW.json"

    write_json(queue_index, make_queue(packet_count=0))
    write_json(lock_status, make_lock())
    write_json(recovery_view, make_recovery())
    write_json(lead_dispatch_view, make_dispatch())

    result = run_script(
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-LeadDispatchViewPath",
        str(lead_dispatch_view),
        "-PacketFactoryViewPath",
        str(tmp_path / "missing_PACKET_FACTORY_VIEW.json"),
    )

    assert result["approval_gate_status"] == "REVIEW_REQUIRED"
    assert result["packet_factory_summary"]["present"] is False
    assert "packet_factory_source_missing" in result["blockers"]


def test_blocked_queue_lock_recovery_and_dispatch_state_blocks_live_action(tmp_path: Path) -> None:
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "LEAD_DISPATCH_VIEW.json"
    packet_factory_view = tmp_path / "PACKET_FACTORY_VIEW.json"

    write_json(queue_index, make_queue(packet_count=3, blocked=2))
    write_json(lock_status, make_lock(held=1, collision=1, safety="REVIEW_REQUIRED"))
    write_json(recovery_view, make_recovery(readiness="BLOCKED", blockers=["marker_stale"], warnings=["heartbeat_degraded"]))
    write_json(lead_dispatch_view, make_dispatch(verdict="BLOCKED", blocked_reason="queue_blocked"))
    write_json(packet_factory_view, make_packet_factory(verdict="BLOCKED"))

    result = run_script(
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

    assert result["approval_gate_status"] == "BLOCKED"
    assert result["live_dispatch_status"] == "BLOCKED"
    assert "queue_blocked" in result["blockers"]
    assert "held_locks_present" in result["blockers"]
    assert "lock_collision_present" in result["blockers"]
    assert "marker_stale" in result["blockers"]
    assert "queue_blocked" in result["blockers"]


def test_stale_source_fails_closed_to_review_required(tmp_path: Path) -> None:
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "LEAD_DISPATCH_VIEW.json"
    packet_factory_view = tmp_path / "PACKET_FACTORY_VIEW.json"

    write_json(queue_index, make_queue(packet_count=0))
    write_json(lock_status, make_lock())
    write_json(recovery_view, make_recovery())
    write_json(lead_dispatch_view, make_dispatch())
    write_json(packet_factory_view, make_packet_factory())
    write_old(packet_factory_view)

    result = run_script(
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

    assert result["approval_gate_status"] == "REVIEW_REQUIRED"
    assert result["packet_factory_summary"]["freshness_status"] == "STALE"


def test_script_contains_atomic_write_pattern_and_no_mutating_operations() -> None:
    script_text = SCRIPT.read_text(encoding="utf-8")

    assert "WriteAllText" in script_text
    assert "Move-Item -LiteralPath $tempPath -Destination $destinationFull -Force" in script_text
    assert "Assign-AIOSPacket" not in script_text
    assert "Claim-AiOsFileLock" not in script_text
    assert "Release-AiOsFileLock" not in script_text
    assert "Start-ScheduledTask" not in script_text
    assert "approval_inbox" not in script_text
    assert "broker" not in script_text
    assert "webhook" not in script_text
    assert "secret" not in script_text
