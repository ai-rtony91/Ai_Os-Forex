import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "automation" / "orchestration" / "coordination_spine" / "Get-AiOsPacketFactoryView.DRY_RUN.ps1"


def run_script(*args: str) -> dict:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return json.loads(completed.stdout)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def duplicate_scan_args(*roots: Path) -> list[str]:
    return ["-DuplicateSearchRoots", ",".join(str(root) for root in roots)]


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


def make_dispatch(*, verdict: str = "SAFE_NO_WORK", blocked_reason: str | None = None) -> dict:
    return {
        "dispatcher_safety_verdict": verdict,
        "blocked_reason": blocked_reason,
        "depends_on_t2b": True,
        "write_behavior": "telemetry_only",
        "next_safe_action": "Resolve blockers before dispatch." if verdict == "BLOCKED" else "Proceed.",
    }


def make_minimal_proposed_packet_text(*, packet_id: str = "demo", extra: str = "") -> str:
    return f"""CODEX-ONLY PROMPT
AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED
IDENTITY MARKER: DEMO
SUPERVISOR IDENTITY: Demo
PACKET ID: {packet_id}
MODE: DRY_RUN
ZONE: demo-zone
WORKER IDENTITY: DemoWorker
LANE: demo-lane
WORKTREE: C:\\Dev\\Ai.Os
BRANCH: main
APPROVAL AUTHORITY: Anthony Meza
MISSION: Demo packet.
ALLOWED PATHS:
- automation/orchestration/coordination_spine/
FORBIDDEN PATHS:
- .git/
VALIDATOR CHAIN:
- git diff --check
STOP POINT:
Stop after review.
FINAL REPORT FORMAT:
SUMMARY:
SAFE NEXT ACTION:
{extra}
"""


def test_empty_no_packet_source_produces_safe_no_work_view(tmp_path: Path) -> None:
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "LEAD_DISPATCH_VIEW.json"
    output_path = tmp_path / "PACKET_FACTORY_VIEW.json"

    write_json(queue_index, make_queue(packet_count=0))
    write_json(lock_status, make_lock())
    write_json(recovery_view, make_recovery())
    write_json(lead_dispatch_view, make_dispatch())

    result = run_script(
        "-PacketRootPath",
        str(tmp_path / "empty_packets"),
        "-TemplateRootPath",
        str(tmp_path / "empty_packets" / "templates"),
        "-ProposedRootPath",
        str(tmp_path / "empty_packets" / "proposed"),
        "-ActiveRootPath",
        str(tmp_path / "empty_packets" / "active"),
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-LeadDispatchViewPath",
        str(lead_dispatch_view),
        "-OutputPath",
        str(output_path),
        *duplicate_scan_args(tmp_path / "empty_packets", tmp_path / "empty_packets" / "templates", tmp_path / "empty_packets" / "proposed", tmp_path / "empty_packets" / "active"),
    )

    assert result["packet_factory_safety_verdict"] == "SAFE_NO_WORK"
    assert result["recommended_next_packet_action"].startswith("No packet sources found")
    assert result["proposed_packet_count"] == 0
    assert result["active_packet_count"] == 0
    assert result["packet_template_count"] == 0


def test_proposed_packets_are_read_and_summarized_without_mutation(tmp_path: Path) -> None:
    packet_root = tmp_path / "packets"
    proposed = packet_root / "proposed"
    templates = packet_root / "templates"
    active = packet_root / "active"
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "LEAD_DISPATCH_VIEW.json"

    write_text(proposed / "AIOS-DEMO-PACKET.md", make_minimal_proposed_packet_text(packet_id="demo-packet"))
    write_json(templates / "AIOS_WORK_PACKET.template.json", {"packet_id": "", "mode": "DRY_RUN", "mission": "", "stop_condition": ""})
    write_json(queue_index, make_queue(packet_count=1, queued=1))
    write_json(lock_status, make_lock())
    write_json(recovery_view, make_recovery())
    write_json(lead_dispatch_view, make_dispatch())

    result = run_script(
        "-PacketRootPath",
        str(packet_root),
        "-TemplateRootPath",
        str(templates),
        "-ProposedRootPath",
        str(proposed),
        "-ActiveRootPath",
        str(active),
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-LeadDispatchViewPath",
        str(lead_dispatch_view),
        *duplicate_scan_args(packet_root, proposed, templates, active),
    )

    assert result["proposed_packet_count"] == 1
    assert result["packet_template_count"] == 1
    assert result["packet_records"][0]["packet_id"] == "demo-packet"
    assert result["packet_records"][0]["source_kind"] == "proposed"
    assert result["packet_records"][0]["status"] == "REVIEW_REQUIRED"


def test_missing_required_packet_fields_are_review_required(tmp_path: Path) -> None:
    packet_root = tmp_path / "packets"
    proposed = packet_root / "proposed"
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "LEAD_DISPATCH_VIEW.json"

    write_text(
        proposed / "AIOS-MISSING-FIELDS.md",
        """CODEX-ONLY PROMPT
AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED
PACKET ID: missing-fields
MODE: DRY_RUN
MISSION: Missing fields.
STOP POINT:
Stop after review.
FINAL REPORT FORMAT:
SUMMARY:
""",
    )
    write_json(queue_index, make_queue(packet_count=1, queued=1))
    write_json(lock_status, make_lock())
    write_json(recovery_view, make_recovery())
    write_json(lead_dispatch_view, make_dispatch())

    result = run_script(
        "-PacketRootPath",
        str(packet_root),
        "-ProposedRootPath",
        str(proposed),
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-LeadDispatchViewPath",
        str(lead_dispatch_view),
        *duplicate_scan_args(packet_root, proposed),
    )
    assert result["packet_factory_safety_verdict"] == "REVIEW_REQUIRED"
    assert result["missing_required_fields"]
    assert result["missing_required_fields"][0]["packet_id"] == "missing-fields"
    assert "APPROVAL AUTHORITY" in result["missing_required_fields"][0]["missing_fields"]
    assert "ALLOWED PATHS" in result["missing_required_fields"][0]["missing_fields"]


def test_duplicate_intent_is_blocked_or_review_required_by_severity(tmp_path: Path) -> None:
    packet_root = tmp_path / "packets"
    proposed = packet_root / "proposed"
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "LEAD_DISPATCH_VIEW.json"

    write_text(
        proposed / "duplicate-owner.md",
        make_minimal_proposed_packet_text(
            packet_id="duplicate-owner",
            extra="Packet Factory Unifier\ncoordination_spine packet factory\nGet-AiOsPacketFactoryView",
        ),
    )
    write_json(queue_index, make_queue(packet_count=1, queued=1))
    write_json(lock_status, make_lock())
    write_json(recovery_view, make_recovery())
    write_json(lead_dispatch_view, make_dispatch())

    result = run_script(
        "-PacketRootPath",
        str(packet_root),
        "-ProposedRootPath",
        str(proposed),
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-LeadDispatchViewPath",
        str(lead_dispatch_view),
        *duplicate_scan_args(packet_root, proposed),
    )

    statuses = {item["query"]: item["status"] for item in result["duplicate_intent_findings"]}
    assert statuses["Get-AiOsPacketFactoryView"] == "BLOCKED"
    assert statuses["Packet Factory Unifier"] == "REVIEW_REQUIRED"
    assert result["packet_factory_safety_verdict"] == "BLOCKED"


def test_approval_required_and_context_blockers_are_surfaces_without_approval(tmp_path: Path) -> None:
    packet_root = tmp_path / "packets"
    proposed = packet_root / "proposed"
    queue_index = tmp_path / "UNIFIED_QUEUE_INDEX.json"
    lock_status = tmp_path / "UNIFIED_LOCK_STATUS.json"
    recovery_view = tmp_path / "RECOVERY_BOOTSTRAP_VIEW.json"
    lead_dispatch_view = tmp_path / "LEAD_DISPATCH_VIEW.json"

    write_text(proposed / "approval-required.md", make_minimal_proposed_packet_text(packet_id="approval-required", extra="Human Owner approval\nAPPLY requires a separate explicit Human Owner approval."))
    write_json(queue_index, make_queue(packet_count=2, blocked=1))
    write_json(lock_status, make_lock(held=1, collision=1, safety="REVIEW_REQUIRED"))
    write_json(recovery_view, make_recovery(readiness="BLOCKED", blockers=["marker_stale"], warnings=["heartbeat_degraded"]))
    write_json(lead_dispatch_view, make_dispatch(verdict="BLOCKED", blocked_reason="queue_blocked"))

    result = run_script(
        "-PacketRootPath",
        str(packet_root),
        "-ProposedRootPath",
        str(proposed),
        "-QueueIndexPath",
        str(queue_index),
        "-LockStatusPath",
        str(lock_status),
        "-RecoveryViewPath",
        str(recovery_view),
        "-LeadDispatchViewPath",
        str(lead_dispatch_view),
        *duplicate_scan_args(packet_root, proposed),
    )

    assert result["packet_factory_safety_verdict"] == "BLOCKED"
    assert "queue_blocked" in result["blockers"]
    assert "lock_review_required_or_collision" in result["blockers"]
    assert "recovery_blocked" in result["blockers"]
    assert "lead_dispatch_blocked" in result["blockers"]
    assert result["approval_required_items"]
    assert result["approval_required_items"][0]["packet_id"] == "approval-required"


def test_script_contains_atomic_write_pattern_and_no_mutating_operations() -> None:
    script_text = SCRIPT.read_text(encoding="utf-8")

    assert "WriteAllText" in script_text
    assert "Move-Item -LiteralPath $tempPath -Destination $destinationFull -Force" in script_text
    assert "Get-AiOsPacketFactoryView" in script_text
    assert "Assign-AIOSPacket" not in script_text
    assert "Claim-AiOsFileLock" not in script_text
    assert "Release-AiOsFileLock" not in script_text
    assert "approval_inbox" not in script_text
    assert "Start-ScheduledTask" not in script_text
    assert "Invoke-AiOsNightCycle" not in script_text
    assert "Live Trading" not in script_text
