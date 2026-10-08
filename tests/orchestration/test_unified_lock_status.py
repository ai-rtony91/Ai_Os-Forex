import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "automation" / "orchestration" / "coordination_spine" / "Get-AiOsUnifiedLockStatus.DRY_RUN.ps1"


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


def test_empty_state_produces_zero_counts_and_no_unmapped_states(tmp_path: Path) -> None:
    lock_registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    claim_registry = tmp_path / "WORKER_CLAIM_REGISTRY_001.json"
    output_path = tmp_path / "UNIFIED_LOCK_STATUS.json"

    write_json(lock_registry, {"locks": []})
    write_json(claim_registry, {"claims": []})

    result = run_script(
        "-LockRegistryPath",
        str(lock_registry),
        "-ClaimRegistryPath",
        str(claim_registry),
        "-InstanceLockPath",
        str(tmp_path / "supervisor.lock"),
        "-OutputPath",
        str(output_path),
        "-Apply",
    )

    assert result["held_locks_count"] == 0
    assert result["stale_locks_count"] == 0
    assert result["collision_count"] == 0
    assert result["worker_claim_count"] == 0
    assert result["packet_lock_count"] == 0
    assert result["instance_lock_count"] == 0
    assert result["unknown_lock_records"] == []
    assert result["claim_registry_boundary_warnings"] == []
    assert result["safety_status"] == "PASS"
    assert result["write_behavior"] == "telemetry_only"
    assert output_path.exists()

    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["held_locks_count"] == 0
    assert persisted["unknown_lock_records"] == []


def test_placeholder_template_claim_registry_is_excluded_from_active_state(tmp_path: Path) -> None:
    lock_registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    claim_registry = tmp_path / "WORKER_CLAIM_REGISTRY_001.json"
    output_path = tmp_path / "UNIFIED_LOCK_STATUS.json"

    write_json(lock_registry, {"locks": []})
    write_json(
        claim_registry,
        {
            "schema": "AIOS_WORKER_CLAIM_REGISTRY.v1",
            "worker_id": "WORKER_ID_PLACEHOLDER",
            "worker_name": "WORKER_NAME_PLACEHOLDER",
            "packet_id": "PACKET_ID_PLACEHOLDER",
            "assigned_paths": [],
            "claim_timestamp": "TIMESTAMP_PLACEHOLDER",
            "expiration_placeholder": "TIMESTAMP_PLACEHOLDER",
            "claim_status": "claimed",
        },
    )

    result = run_script(
        "-LockRegistryPath",
        str(lock_registry),
        "-ClaimRegistryPath",
        str(claim_registry),
        "-InstanceLockPath",
        str(tmp_path / "supervisor.lock"),
        "-OutputPath",
        str(output_path),
        "-Apply",
    )

    assert result["worker_claim_count"] == 0
    assert result["packet_lock_count"] == 0
    assert result["unknown_lock_records"] == []
    assert result["safety_status"] == "PASS"
    assert result["claim_registry_boundary_warnings"]
    assert result["claim_registry_boundary_warnings"][0]["reason"] == "placeholder_claim_template_excluded"


def test_held_stale_collision_and_unknown_are_reported_without_mutation(tmp_path: Path) -> None:
    lock_registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    claim_registry = tmp_path / "WORKER_CLAIM_REGISTRY_001.json"
    output_path = tmp_path / "UNIFIED_LOCK_STATUS.json"
    instance_lock = tmp_path / "supervisor.lock"

    write_json(
        lock_registry,
        {
            "locks": [
                {"path": "C:\\Dev\\Ai.Os\\foo.txt", "owner": "worker-a", "state": "HELD", "packet_id": "p-1"},
                {"path": "C:\\Dev\\Ai.Os\\foo.txt", "owner": "worker-b", "state": "HELD", "packet_id": "p-2"},
                {"path": "C:\\Dev\\Ai.Os\\bar.txt", "owner": "worker-c", "state": "STALE"},
                {"path": "C:\\Dev\\Ai.Os\\baz.txt", "state": "MYSTERY"},
            ]
        },
    )
    write_json(
        claim_registry,
        {
            "claims": [
                {
                    "worker_id": "worker-claim",
                    "packet_id": "packet-claim",
                    "claim_status": "claimed",
                    "expiration_placeholder": "review",
                }
            ]
        },
    )
    write_json(instance_lock, {"status": "held", "owner": "supervisor"})

    result = run_script(
        "-LockRegistryPath",
        str(lock_registry),
        "-ClaimRegistryPath",
        str(claim_registry),
        "-InstanceLockPath",
        str(instance_lock),
        "-OutputPath",
        str(output_path),
        "-Apply",
    )

    assert result["held_locks_count"] >= 2
    assert result["stale_locks_count"] == 1
    assert result["collision_count"] >= 1
    assert result["worker_claim_count"] == 1
    assert result["packet_lock_count"] >= 3
    assert result["instance_lock_count"] == 1
    assert result["safety_status"] == "REVIEW_REQUIRED"
    assert result["unknown_lock_records"]
    assert any(record.get("reason") for record in result["unknown_lock_records"])

    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["collision_count"] == result["collision_count"]
    assert persisted["unknown_lock_records"]


def test_script_uses_atomic_write_pattern_and_stays_dry_run_first() -> None:
    script_text = SCRIPT.read_text(encoding="utf-8")

    assert "if ($Apply)" in script_text
    assert "[System.IO.File]::WriteAllText" in script_text
    assert "Move-Item -LiteralPath $tempPath -Destination $OutputPath -Force" in script_text
    assert "Claim-AiOsFileLock" not in script_text
    assert "Release-AiOsFileLock" not in script_text
    assert "Assign-AiOsFileLock" not in script_text
    assert "Dispatch" not in script_text
    assert "Approve" not in script_text
