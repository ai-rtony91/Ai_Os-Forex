import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "automation" / "orchestration" / "coordination_spine" / "Invoke-AiOsRecoveryBootstrap.DRY_RUN.ps1"


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


def test_no_marker_produces_review_required_without_mutation(tmp_path: Path) -> None:
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    heartbeat = tmp_path / "runtime_heartbeat.json"
    output_path = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"

    write_json(queue_index, {"packet_count": 0, "normalized_state_counts": {k: 0 for k in ["QUEUED", "RUNNING", "BLOCKED", "WAITING_APPROVAL", "COMPLETE", "FAILED", "ARCHIVED"]}})
    write_json(lock_status, {"held_locks_count": 0, "stale_locks_count": 0, "collision_count": 0})
    write_json(heartbeat, {"status": "healthy"})

    result = run_script(
        "-MarkerPath",
        str(tmp_path / "last_marker.json"),
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-HeartbeatPath",
        str(heartbeat),
        "-OutputPath",
        str(output_path),
    )

    assert result["marker_present"] is False
    assert result["marker_freshness_status"] == "MISSING"
    assert result["recovery_readiness"] == "REVIEW_REQUIRED"
    assert "marker_missing" in result["warnings"]


def test_fresh_marker_produces_ready_known_status(tmp_path: Path) -> None:
    marker = tmp_path / "last_marker.json"
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    heartbeat = tmp_path / "runtime_heartbeat.json"

    write_json(
        marker,
        {
            "cycle_id": "cycle-1",
            "cycle_in_progress": False,
            "updated_at_utc": (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )
    write_json(queue_index, {"packet_count": 0, "normalized_state_counts": {k: 0 for k in ["QUEUED", "RUNNING", "BLOCKED", "WAITING_APPROVAL", "COMPLETE", "FAILED", "ARCHIVED"]}})
    write_json(lock_status, {"held_locks_count": 0, "stale_locks_count": 0, "collision_count": 0})
    write_json(heartbeat, {"status": "healthy"})

    result = run_script(
        "-MarkerPath",
        str(marker),
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-HeartbeatPath",
        str(heartbeat),
    )

    assert result["marker_present"] is True
    assert result["marker_freshness_status"] == "FRESH"
    assert result["recovery_readiness"] == "READY_KNOWN"
    assert result["warnings"] == []
    assert result["blockers"] == []


def test_queue_missing_and_lock_collision_affect_readiness(tmp_path: Path) -> None:
    marker = tmp_path / "last_marker.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    heartbeat = tmp_path / "runtime_heartbeat.json"

    write_json(marker, {"cycle_id": "cycle-2", "cycle_in_progress": False, "updated_at_utc": (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    write_json(lock_status, {"held_locks_count": 1, "stale_locks_count": 0, "collision_count": 1})
    write_json(heartbeat, {"status": "healthy"})

    result = run_script(
        "-MarkerPath",
        str(marker),
        "-QueueIndexPath",
        str(tmp_path / "missing_queue.json"),
        "-LockStatusPath",
        str(lock_status),
        "-HeartbeatPath",
        str(heartbeat),
    )

    assert result["queue_index_present"] is False
    assert "queue_index_missing" in result["warnings"]
    assert result["held_locks_count"] == 1
    assert result["collision_count"] == 1
    assert result["recovery_readiness"] == "BLOCKED"
    assert "held_locks_present" in result["blockers"]
    assert "lock_collision_present" in result["blockers"]


def test_heartbeat_unavailable_is_reported_without_crashing(tmp_path: Path) -> None:
    marker = tmp_path / "last_marker.json"
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"

    write_json(marker, {"cycle_id": "cycle-3", "cycle_in_progress": False, "updated_at_utc": (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    write_json(queue_index, {"packet_count": 0, "normalized_state_counts": {k: 0 for k in ["QUEUED", "RUNNING", "BLOCKED", "WAITING_APPROVAL", "COMPLETE", "FAILED", "ARCHIVED"]}})
    write_json(lock_status, {"held_locks_count": 0, "stale_locks_count": 0, "collision_count": 0})

    result = run_script(
        "-MarkerPath",
        str(marker),
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-HeartbeatPath",
        str(tmp_path / "missing_runtime_heartbeat.json"),
    )

    assert result["heartbeat_status"] == "UNAVAILABLE"
    assert "heartbeat_unavailable" in result["warnings"]
    assert result["recovery_readiness"] == "REVIEW_REQUIRED"


def test_script_contains_atomic_write_pattern_and_no_mutating_recovery_calls() -> None:
    script_text = SCRIPT.read_text(encoding="utf-8")

    assert "Write-AiOsAtomicJson" in script_text
    assert "[System.IO.File]::WriteAllText" in script_text
    assert "Move-Item -LiteralPath $tempPath -Destination $destinationFull -Force" in script_text
    assert "Invoke-AiOsNightCycle" not in script_text
    assert "Start-ScheduledTask" not in script_text
    assert "Claim-AiOsFileLock" not in script_text
    assert "Release-AiOsFileLock" not in script_text
    assert "Dispatch" not in script_text
