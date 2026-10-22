import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "automation" / "orchestration" / "coordination_spine" / "Get-AiOsLeadDispatchView.DRY_RUN.ps1"


def run_script(*args: str) -> dict:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


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


def test_no_queue_candidates_produces_safe_no_work_decision(tmp_path: Path) -> None:
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"

    write_json(queue_index, make_queue(packet_count=0))
    write_json(lock_status, {"held_locks_count": 0, "stale_locks_count": 0, "collision_count": 0, "safety_status": "PASS", "write_behavior": "telemetry_only"})
    write_json(recovery_view, {"recovery_readiness": "READY_KNOWN", "blockers": [], "warnings": [], "heartbeat_status": "HEALTHY", "write_behavior": "telemetry_only"})

    result = run_script(
        "-DispatcherSampleCheck",
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-OutputPath",
        str(tmp_path / "LEAD_DISPATCH_VIEW.json"),
    )

    assert result["dispatcher_safety_verdict"] == "SAFE_NO_WORK"
    assert result["dispatcher_candidate"]["evaluated_decision"] == "NO_WORK"
    assert result["blocked_reason"] is None
    assert result["depends_on_t2b"] is True


def test_blocked_queue_or_recovery_state_produces_blocked_verdict(tmp_path: Path) -> None:
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"

    write_json(queue_index, make_queue(packet_count=2, blocked=1))
    write_json(lock_status, {"held_locks_count": 0, "stale_locks_count": 0, "collision_count": 0, "safety_status": "PASS", "write_behavior": "telemetry_only"})
    write_json(recovery_view, {"recovery_readiness": "BLOCKED", "blockers": ["marker_stale"], "warnings": ["heartbeat_degraded"], "heartbeat_status": "DEGRADED", "write_behavior": "telemetry_only"})

    result = run_script(
        "-DispatcherSampleCheck",
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-OutputPath",
        str(tmp_path / "LEAD_DISPATCH_VIEW.json"),
    )

    assert result["dispatcher_safety_verdict"] == "BLOCKED"
    assert "queue_blocked" in result["blocked_reason"]
    assert "recovery_blocked" in result["blocked_reason"]


def test_lock_collision_or_review_required_blocks_dispatch(tmp_path: Path) -> None:
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"

    write_json(queue_index, make_queue(packet_count=1, queued=1))
    write_json(lock_status, {"held_locks_count": 1, "stale_locks_count": 0, "collision_count": 1, "safety_status": "REVIEW_REQUIRED", "write_behavior": "telemetry_only"})
    write_json(recovery_view, {"recovery_readiness": "READY_KNOWN", "blockers": [], "warnings": [], "heartbeat_status": "HEALTHY", "write_behavior": "telemetry_only"})

    result = run_script(
        "-DispatcherSampleCheck",
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-OutputPath",
        str(tmp_path / "LEAD_DISPATCH_VIEW.json"),
    )

    assert result["dispatcher_safety_verdict"] == "BLOCKED"
    assert "lock_review_required_or_collision" in result["blocked_reason"]


def test_t2b_dependency_is_reported_not_executed() -> None:
    script_text = SCRIPT.read_text(encoding="utf-8")

    assert "assignment_executor.py" in script_text
    assert "Assign-AIOSPacket" not in script_text
    assert "Claim-AiOsFileLock" not in script_text
    assert "Release-AiOsFileLock" not in script_text
    assert "New-AiOsPacketApprovalRequest" not in script_text
    assert "depends_on_t2b" in script_text


def test_script_contains_atomic_write_pattern_and_no_mutating_calls() -> None:
    script_text = SCRIPT.read_text(encoding="utf-8")

    assert "Write-AiOsAtomicJson" in script_text
    assert "[System.IO.File]::WriteAllText" in script_text
    assert "Move-Item -LiteralPath $tempPath -Destination $destinationFull -Force" in script_text
    assert "Assign-AIOSPacket" not in script_text
    assert "Claim-AiOsFileLock" not in script_text
    assert "Release-AiOsFileLock" not in script_text
    assert "approval_inbox" not in script_text
    assert "queue/write" not in script_text
