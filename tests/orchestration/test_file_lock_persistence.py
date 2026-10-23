from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAIM_SCRIPT = REPO_ROOT / "automation/orchestration/locks/Claim-AiOsFileLock.DRY_RUN.ps1"
RELEASE_SCRIPT = REPO_ROOT / "automation/orchestration/locks/Release-AiOsFileLock.DRY_RUN.ps1"
STATUS_SCRIPT = REPO_ROOT / "automation/orchestration/locks/Get-AiOsWorkerLockStatus.DRY_RUN.ps1"
INTEGRITY_SCRIPT = REPO_ROOT / "automation/orchestration/validators/Test-LockRegistryIntegrity.DRY_RUN.ps1"
CANONICAL_REGISTRY = REPO_ROOT / "automation/orchestration/locks/FILE_LOCK_REGISTRY.json"


def registry_payload(*, locks: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema": "AIOS_FILE_LOCK_REGISTRY.v1",
        "system": "AI_OS",
        "mode": "DRY_RUN",
        "global_blocked_paths": [".git/", "broker/", "oanda/", "secrets/", "webhooks/", ".env"],
        "recommended_blocked_files": ["AGENTS.md", "README.md"],
        "locks": locks or [],
    }


def write_registry(path: Path, payload: dict[str, object] | None = None) -> None:
    path.write_text(json.dumps(payload or registry_payload(), indent=2), encoding="utf-8")


def run_powershell(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def run_json(script: Path, *args: str) -> dict[str, object]:
    result = run_powershell(script, *args, "-OutputJson")
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def active_lock(path: str, *, worker_id: str = "worker-a", lock_id: str = "lock-a") -> dict[str, object]:
    return {
        "schema": "AIOS_PACKET_LOCK.v1",
        "schema_version": "1.0.0",
        "lock_id": lock_id,
        "worker_id": worker_id,
        "packet_id": "packet-a",
        "lane": "test",
        "status": "ACTIVE",
        "claimed_paths": [path],
        "created_at_utc": "2026-06-08T00:00:00.0000000Z",
        "updated_at_utc": "2026-06-08T00:00:00.0000000Z",
        "expires_at_utc": "2099-01-01T00:00:00.0000000Z",
        "release_condition": "test release",
        "approval_packet_id": "approval-a",
        "notes": "test fixture",
    }


def released_lock(path: str, *, worker_id: str = "worker-a", lock_id: str = "lock-a") -> dict[str, object]:
    lock = active_lock(path, worker_id=worker_id, lock_id=lock_id)
    lock["status"] = "RELEASED"
    lock["released_at_utc"] = "2026-06-08T01:00:00.0000000Z"
    return lock


def assert_no_temp_registry_files(registry_path: Path) -> None:
    leftovers = list(registry_path.parent.glob(f".{registry_path.name}.*.tmp"))
    assert leftovers == []


def test_empty_registry_valid(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    write_registry(registry)

    result = run_json(STATUS_SCRIPT, "-RegistryPath", str(registry))

    assert result["lock_count"] == 0
    assert result["active_lock_count"] == 0
    assert result["safety"]["writes_performed"] == 0


def test_malformed_registry_fails_closed(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    registry.write_text("{", encoding="utf-8")

    result = run_powershell(
        CLAIM_SCRIPT,
        "-RegistryPath",
        str(registry),
        "-Paths",
        "automation/orchestration/locks/example.txt",
        "-Apply",
        "-OutputJson",
    )

    assert result.returncode != 0
    assert "LOCK_REGISTRY_FAIL_CLOSED" in result.stderr
    assert registry.read_text(encoding="utf-8") == "{"
    assert_no_temp_registry_files(registry)


def test_active_same_file_collision_blocks(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    write_registry(registry, registry_payload(locks=[active_lock("automation/orchestration/locks/file.txt")]))

    result = run_json(
        CLAIM_SCRIPT,
        "-RegistryPath",
        str(registry),
        "-Paths",
        "automation/orchestration/locks/file.txt",
        "-Apply",
    )

    assert result["claim_status"] == "REVIEW_REQUIRED"
    assert result["writes_performed"] == 0
    assert json.loads(registry.read_text(encoding="utf-8"))["locks"][0]["lock_id"] == "lock-a"


def test_parent_child_overlap_blocks(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    write_registry(registry, registry_payload(locks=[active_lock("automation/orchestration/locks")]))

    result = run_json(
        CLAIM_SCRIPT,
        "-RegistryPath",
        str(registry),
        "-Paths",
        "./automation/orchestration/locks/child/file.txt",
        "-Apply",
    )

    assert result["claim_status"] == "REVIEW_REQUIRED"
    assert result["writes_performed"] == 0
    assert result["collisions"][0]["risk_type"] == "ACTIVE_LOCK_COLLISION"


def test_global_blocked_path_blocks(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    write_registry(registry)

    result = run_json(CLAIM_SCRIPT, "-RegistryPath", str(registry), "-Paths", "broker/live.json", "-Apply")

    assert result["claim_status"] == "BLOCKED"
    assert result["policy_blocks"][0]["risk_type"] == "GLOBAL_BLOCKED_PATH"
    assert json.loads(registry.read_text(encoding="utf-8"))["locks"] == []


def test_same_worker_reclaim_requires_review(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    write_registry(registry, registry_payload(locks=[active_lock("automation/orchestration/locks", worker_id="worker-a")]))

    result = run_json(
        CLAIM_SCRIPT,
        "-RegistryPath",
        str(registry),
        "-WorkerId",
        "worker-a",
        "-Paths",
        "automation/orchestration/locks/new.txt",
        "-Apply",
    )

    assert result["claim_status"] == "REVIEW_REQUIRED"
    assert result["collisions"][0]["risk_type"] == "SAME_WORKER_RECLAIM_REVIEW"
    assert result["writes_performed"] == 0


def test_successful_claim_persists_atomically_to_temp_fixture(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    write_registry(registry)

    result = run_json(
        CLAIM_SCRIPT,
        "-RegistryPath",
        str(registry),
        "-WorkerId",
        "worker-a",
        "-PacketId",
        "packet-a",
        "-Lane",
        "locks",
        "-Paths",
        "./automation/orchestration/locks/new.txt",
        "-ApprovalPacketId",
        "approval-a",
        "-Apply",
    )

    persisted = json.loads(registry.read_text(encoding="utf-8"))
    lock = persisted["locks"][0]

    assert result["claim_status"] == "READY_TO_CLAIM"
    assert result["writes_performed"] == 1
    assert lock["status"] == "ACTIVE"
    assert lock["claimed_paths"] == ["automation/orchestration/locks/new.txt"]
    for field in {
        "schema",
        "schema_version",
        "lock_id",
        "worker_id",
        "packet_id",
        "lane",
        "status",
        "claimed_paths",
        "created_at_utc",
        "updated_at_utc",
        "expires_at_utc",
        "release_condition",
        "approval_packet_id",
        "notes",
    }:
        assert field in lock
    assert_no_temp_registry_files(registry)


def test_release_requires_matching_worker_id_and_lock_id(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    write_registry(registry, registry_payload(locks=[active_lock("automation/orchestration/locks/file.txt")]))

    wrong_worker = run_json(RELEASE_SCRIPT, "-RegistryPath", str(registry), "-WorkerId", "worker-b", "-LockId", "lock-a", "-Apply")
    assert wrong_worker["release_status"] == "BLOCKED"
    assert wrong_worker["writes_performed"] == 0

    released = run_json(RELEASE_SCRIPT, "-RegistryPath", str(registry), "-WorkerId", "worker-a", "-LockId", "lock-a", "-Apply")
    persisted = json.loads(registry.read_text(encoding="utf-8"))

    assert released["release_status"] == "READY_TO_RELEASE"
    assert released["writes_performed"] == 1
    assert persisted["locks"][0]["status"] == "RELEASED"
    assert "released_at_utc" in persisted["locks"][0]


def test_release_of_non_active_lock_is_review_required(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    lock = active_lock("automation/orchestration/locks/file.txt")
    lock["status"] = "RELEASED"
    write_registry(registry, registry_payload(locks=[lock]))

    result = run_json(RELEASE_SCRIPT, "-RegistryPath", str(registry), "-WorkerId", "worker-a", "-LockId", "lock-a", "-Apply")

    assert result["release_status"] == "REVIEW_REQUIRED"
    assert result["writes_performed"] == 0


def test_release_path_narrowing_cannot_release_unowned_path(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    write_registry(registry, registry_payload(locks=[active_lock("automation/orchestration/locks/file.txt")]))

    result = run_json(
        RELEASE_SCRIPT,
        "-RegistryPath",
        str(registry),
        "-WorkerId",
        "worker-a",
        "-LockId",
        "lock-a",
        "-Path",
        "automation/orchestration/workers/inbox/item.json",
        "-Apply",
    )

    assert result["release_status"] == "BLOCKED"
    assert result["writes_performed"] == 0
    assert json.loads(registry.read_text(encoding="utf-8"))["locks"][0]["status"] == "ACTIVE"


def test_canonical_registry_is_not_mutated_by_tests() -> None:
    before = CANONICAL_REGISTRY.read_text(encoding="utf-8")

    result = run_json(CLAIM_SCRIPT, "-Paths", "automation/orchestration/locks/preview-only.txt")

    assert result["mode"] == "DRY_RUN"
    assert result["writes_performed"] == 0
    assert CANONICAL_REGISTRY.read_text(encoding="utf-8") == before


def test_no_activation_terms_enable_runtime_behavior() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in [CLAIM_SCRIPT, RELEASE_SCRIPT, STATUS_SCRIPT])
    lowered = combined.lower()

    forbidden_phrases = [
        "invoke-aiosnightcycle",
        "start-scheduler",
        "start-night",
        "send-sos",
        "adb ",
        "oanda api",
        "live trading enabled",
        "worker launch approved",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in lowered


def test_integrity_accepts_zero_and_one_active_lock(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    write_registry(registry)
    empty = run_powershell(INTEGRITY_SCRIPT, "-LockRegistryPath", str(registry))
    assert empty.returncode == 0
    assert empty.stdout.startswith("PASS:")

    write_registry(registry, registry_payload(locks=[active_lock("tmp/a")]))
    one = run_powershell(INTEGRITY_SCRIPT, "-LockRegistryPath", str(registry))
    assert one.returncode == 0
    assert one.stdout.startswith("PASS:")


def test_integrity_accepts_released_history_and_one_current_active(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    history = [released_lock("tmp/a"), released_lock("tmp/b"), active_lock("tmp/c")]
    write_registry(registry, registry_payload(locks=history))
    result = run_powershell(INTEGRITY_SCRIPT, "-LockRegistryPath", str(registry))
    assert result.returncode == 0
    assert result.stdout.startswith("PASS:")


def test_integrity_rejects_two_active_records_for_one_canonical_id(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    locks = [active_lock("tmp/a"), active_lock("tmp/b")]
    write_registry(registry, registry_payload(locks=locks))
    result = run_powershell(INTEGRITY_SCRIPT, "-LockRegistryPath", str(registry))
    assert "Multiple ACTIVE records share canonical lock_id" in result.stdout


def test_integrity_rejects_malformed_and_unresolved_duplicate_records(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    malformed = active_lock("tmp/a", worker_id="")
    unresolved = active_lock("tmp/b")
    unresolved["status"] = "EXPIRED"
    write_registry(registry, registry_payload(locks=[malformed, released_lock("tmp/c"), unresolved]))
    result = run_powershell(INTEGRITY_SCRIPT, "-LockRegistryPath", str(registry))
    assert "missing worker_id" in result.stdout
    assert "unresolved non-terminal history" in result.stdout


def test_claim_blocks_second_active_canonical_id_even_for_disjoint_path(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    canonical_id = "LOCK_EAST_TEST_LOCK_OCC90"
    existing = active_lock("tmp/a", worker_id="EAST_OCC_90", lock_id=canonical_id)
    write_registry(registry, registry_payload(locks=[existing]))
    result = run_json(
        CLAIM_SCRIPT,
        "-RegistryPath", str(registry),
        "-WorkerId", "EAST_OCC_90",
        "-Zone", "EAST",
        "-Lane", "TEST_LOCK",
        "-PacketId", "packet-b",
        "-Paths", "tmp/b",
        "-ApprovalPacketId", "owner-approved",
        "-Apply",
    )
    assert result["claim_status"] == "REVIEW_REQUIRED"
    assert result["writes_performed"] == 0
    assert any(item["risk_type"] == "CANONICAL_LOCK_ALREADY_ACTIVE" for item in result["review_required"])


def test_sequential_canonical_claims_release_exact_active_lifecycle(tmp_path: Path) -> None:
    registry = tmp_path / "FILE_LOCK_REGISTRY.json"
    write_registry(registry)
    common = (
        "-RegistryPath", str(registry),
        "-WorkerId", "EAST_OCC_90",
        "-Zone", "EAST",
        "-Lane", "TEST_LOCK",
        "-ApprovalPacketId", "owner-approved",
        "-Apply",
    )
    first = run_json(CLAIM_SCRIPT, *common, "-PacketId", "packet-1", "-Paths", "tmp/a")
    first_release = run_json(RELEASE_SCRIPT, "-RegistryPath", str(registry), "-WorkerId", "EAST_OCC_90", "-LockId", first["lock"]["lock_id"], "-Apply")
    second = run_json(CLAIM_SCRIPT, *common, "-PacketId", "packet-2", "-Paths", "tmp/b")
    before_second_release = json.loads(registry.read_text(encoding="utf-8"))["locks"]
    second_release = run_json(RELEASE_SCRIPT, "-RegistryPath", str(registry), "-WorkerId", "EAST_OCC_90", "-LockId", second["lock"]["lock_id"], "-Apply")
    persisted = json.loads(registry.read_text(encoding="utf-8"))["locks"]
    assert first_release["release_status"] == "READY_TO_RELEASE"
    assert second["lock"]["lock_id"] == first["lock"]["lock_id"]
    assert [item["status"] for item in before_second_release] == ["RELEASED", "ACTIVE"]
    assert second_release["release_status"] == "READY_TO_RELEASE"
    assert [item["status"] for item in persisted] == ["RELEASED", "RELEASED"]
    assert persisted[0]["released_at_utc"] != persisted[1]["released_at_utc"]


def test_current_registry_integrity_passes_without_mutation() -> None:
    before = CANONICAL_REGISTRY.read_bytes()
    result = run_powershell(INTEGRITY_SCRIPT, "-LockRegistryPath", str(CANONICAL_REGISTRY))
    assert result.returncode == 0
    assert result.stdout.startswith("PASS:")
    assert CANONICAL_REGISTRY.read_bytes() == before
