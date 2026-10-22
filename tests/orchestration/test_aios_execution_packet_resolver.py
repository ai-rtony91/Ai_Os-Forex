from __future__ import annotations

from automation.orchestration.runtime_queue.aios_execution_packet_resolver import resolve_execution_packet


def identity() -> dict[str, str]:
    return {
        "mission_id": "MISSION-AIOS", "mission_name": "AIOS completion",
        "program_id": "PROGRAM-ORCH", "program_name": "Orchestration",
        "epic_id": "EPIC-RESOLUTION", "epic_name": "Packet resolution",
        "bucket_id": "BUCKET-RUNTIME", "bucket_name": "Runtime queue",
        "packet_id": "PKT-RESOLVE-001", "packet_name": "Resolve execution packet",
        "supervisor_identity": "Codex East Worksite Supervisor", "zone": "EAST",
        "worker_identity": "EAST_OCC_01", "lane": "orchestration-packet-resolution",
        "stop_point": "Return a packet candidate only; do not execute or mutate runtime state.",
    }


def item(**overrides: object) -> dict:
    value = {
        "queue_schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1", "packet_id": "PKT-RESOLVE-001",
        "packet_identity": identity(), "mode": "APPLY", "approval_state": "APPROVED",
        "approval_authority": "Anthony Meza approved this bounded local APPLY packet only.",
        "commit_message": "feat(orchestration): add execution packet resolver",
        "pr_authority": "Create exactly one PR with the exact commit title; do not merge.",
        "mission": "Implement the bounded execution packet resolver.",
        "allowed_paths": ["automation/orchestration/runtime_queue/aios_execution_packet_resolver.py"],
        "forbidden_paths": ["RISK_POLICY.md"], "validators": ["python -m pytest tests/orchestration/test_aios_execution_packet_resolver.py"],
        "depends_on": [], "attempt": 0, "max_attempts": 2, "protected_action": False,
    }
    value.update(overrides)
    return value


def state(**overrides: object) -> dict:
    value = {"worktree": "/workspace/Ai_Os", "branch": "work", "status_lines": [], "dependency_states": {}}
    value.update(overrides)
    return value


def test_successful_resolution_creates_complete_candidate() -> None:
    result = resolve_execution_packet(item(), state())
    assert result["status"] == "CREATED"
    assert result["packet"]["packet_ready"] is True
    assert result["packet"]["codex_prompt_text"].startswith("CODEX-ONLY PROMPT")
    assert all(value is False for value in result["safety"].values())


def test_existing_packet_is_reused() -> None:
    created = resolve_execution_packet(item(), state())["packet"]
    result = resolve_execution_packet(item(), state(), existing_packets=[created])
    assert result["status"] == "REUSED"
    assert result["packet"] == created
    assert created["write_scope"][:1] == item()["allowed_paths"]
    assert "Reports/orchestration/AIOS_CODEX_TASK_DELIVERY_METADATA_V1.json" in created["write_scope"]


def test_existing_packet_with_tampered_canonical_content_is_blocked() -> None:
    created = resolve_execution_packet(item(), state())["packet"]
    created["validator_chain"] = ["python -c 'bypass validation'"]
    result = resolve_execution_packet(item(), state(), existing_packets=[created])
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "existing_packet_canonical_mismatch"


def test_existing_packet_is_not_reused_for_changed_identity() -> None:
    created = resolve_execution_packet(item(), state())["packet"]
    changed_identity = identity()
    changed_identity["worker_identity"] = "EAST_OCC_02"
    result = resolve_execution_packet(
        item(packet_identity=changed_identity), state(), existing_packets=[created]
    )
    assert result["status"] == "BLOCKED"
    assert result["reason_code"] == "existing_packet_canonical_mismatch"


def test_duplicate_packets_block_resolution() -> None:
    packet = resolve_execution_packet(item(), state())["packet"]
    assert resolve_execution_packet(item(), state(), existing_packets=[packet, packet])["reason_code"] == "duplicate_canonical_packets"


def test_incomplete_identity_is_blocked() -> None:
    broken = identity(); broken.pop("epic_id")
    result = resolve_execution_packet(item(packet_identity=broken), state())
    assert result["reason_code"] == "identity_fields_missing"


def test_placeholder_is_blocked() -> None:
    assert resolve_execution_packet(item(mission="Implement {feature}"), state())["reason_code"] == "placeholder_detected"


def test_dirty_state_is_blocked() -> None:
    assert resolve_execution_packet(item(), state(status_lines=["M unsafe.py"]))["reason_code"] == "repository_dirty"


def test_invalid_scope_is_blocked() -> None:
    assert resolve_execution_packet(item(allowed_paths=["../unsafe.py"]), state())["reason_code"] == "invalid_scope"


def test_failed_dependency_is_blocked() -> None:
    result = resolve_execution_packet(item(depends_on=["PKT-FIRST"]), state(dependency_states={"PKT-FIRST": "ERROR"}))
    assert result["reason_code"] == "dependencies_failed"


def test_exhausted_retries_are_blocked() -> None:
    assert resolve_execution_packet(item(attempt=2, max_attempts=2), state())["reason_code"] == "retries_exhausted"


def test_unapproved_apply_is_blocked() -> None:
    assert resolve_execution_packet(item(approval_state="PENDING"), state())["reason_code"] == "apply_approval_required"


def test_protected_action_is_blocked() -> None:
    assert resolve_execution_packet(item(protected_action=True), state())["reason_code"] == "protected_action"
