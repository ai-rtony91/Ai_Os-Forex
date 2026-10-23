from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "automation" / "orchestration" / "aios_codex_packet_builder.py"


def load_module():
    spec = importlib.util.spec_from_file_location("aios_codex_packet_builder", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def simulator_handoff(module) -> dict[str, object]:
    return {
        "handoff_status": "ready",
        "allowed_action": module.SIMULATOR_ACTION,
        "next_packet_id": module.SIMULATOR_PACKET_ID,
        "allowed_paths": module.SIMULATOR_ALLOWED_PATHS,
        "validators": module.SIMULATOR_VALIDATORS,
    }


def test_imports():
    module = load_module()
    assert module.SCHEMA == "AIOS_CODEX_PACKET_BUILDER.v1"


def test_builder_emits_packet_for_execution_simulator():
    module = load_module()
    packet = module.build_codex_packet_preview(
        {"codex_packet_required": True},
        {},
        simulator_handoff(module),
    )
    assert packet["packet_ready"] is True
    assert packet["packet_id"] == module.SIMULATOR_PACKET_ID
    assert packet["write_scope"] == module.SIMULATOR_ALLOWED_PATHS
    assert packet["validator_chain"] == module.SIMULATOR_VALIDATORS


def test_packet_text_contains_valid_identity_header_and_stop():
    module = load_module()
    packet = module.build_codex_packet_preview(
        {"codex_packet_required": True},
        {},
        simulator_handoff(module),
    )
    text = packet["codex_prompt_text"]
    for required in [
        "CODEX-ONLY PROMPT",
        "AI_OS EXECUTION TOKEN",
        "AI_OS BOOTSTRAP REQUIRED",
        "SUPERVISOR IDENTITY",
        "ZONE",
        "WORKER IDENTITY",
        "LANE",
        "APPROVAL AUTHORITY",
        "MODE: APPLY",
        "WORKTREE",
        "BRANCH",
        "PACKET ID",
        "VALIDATOR CHAIN",
        "STOP: Report only. Do not stage. Do not commit. Do not push.",
    ]:
        assert required in text


def test_builder_does_not_emit_packet_when_not_required():
    module = load_module()
    packet = module.build_codex_packet_preview(
        {"codex_packet_required": False},
        {},
        simulator_handoff(module),
    )
    assert packet["packet_ready"] is False
    assert packet["codex_prompt_text"] == ""


def test_source_has_no_command_or_external_call_imports():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "requests" not in source


def repository_identity() -> dict[str, str]:
    return {
        "mission_id": "MISSION-FOREX-PROFIT-STAGES",
        "mission_name": "Forex profit-stage completion",
        "program_id": "PROGRAM-FOREX",
        "program_name": "Trading Lab Forex",
        "epic_id": "EPIC-PAPER-EVIDENCE",
        "epic_name": "Paper profitability evidence",
        "bucket_id": "BUCKET-PACKET-GENERATION",
        "bucket_name": "Governed packet generation",
        "packet_id": "PKT-FOREX-REPO-ALIGNED-APPLY-001",
        "packet_name": "Repository-aligned APPLY packet",
        "supervisor_identity": "Codex East Worksite Supervisor",
        "zone": "EAST",
        "worker_identity": "EAST_OCC_01",
        "lane": "forex-paper-profit-stage-packet-generator",
        "stop_point": "Report after validation; no protected Git or broker action.",
    }


def test_repository_aligned_builder_uses_observed_state_and_full_identity():
    module = load_module()
    packet = module.build_repository_aligned_apply_packet(
        repository_state={"worktree": "/workspace/Ai_Os", "branch": "work", "status_lines": []},
        packet_identity=repository_identity(),
        mission="Implement the bounded paper-only profitability evidence stage.",
        allowed_paths=["automation/orchestration/aios_codex_packet_builder.py"],
        validators=["python -m pytest tests/orchestration/test_aios_codex_packet_builder.py"],
    )

    assert packet["packet_ready"] is True
    assert packet["repository_state"]["branch"] == "work"
    text = packet["codex_prompt_text"]
    assert text.startswith("CODEX-ONLY PROMPT\n")
    assert "BRANCH: work" in text
    assert "MISSION ID: MISSION-FOREX-PROFIT-STAGES" in text
    assert "STOP POINT:" in text
    assert "FINAL REPORT FORMAT:" in text
    assert "task-start" in text and "task-complete" in text and "task-blocked" in text
    assert ".aios/runtime/engineering_timing/" in packet["write_scope"]


def test_repository_aligned_builder_fails_closed_for_dirty_repository():
    module = load_module()
    packet = module.build_repository_aligned_apply_packet(
        repository_state={"worktree": "/workspace/Ai_Os", "branch": "work", "status_lines": [" M unsafe.py"]},
        packet_identity=repository_identity(),
        mission="Implement a bounded change.",
        allowed_paths=["safe.py"],
        validators=["python -m pytest"],
    )

    assert packet["packet_ready"] is False
    assert packet["reason_code"] == "repository_dirty"
    assert packet["codex_prompt_text"] == ""
    assert packet["dirty_files"] == ["M unsafe.py"]


def test_repository_aligned_builder_rejects_incomplete_identity():
    module = load_module()
    identity = repository_identity()
    identity.pop("bucket_id")
    packet = module.build_repository_aligned_apply_packet(
        repository_state={"worktree": "/workspace/Ai_Os", "branch": "work", "status_lines": []},
        packet_identity=identity,
        mission="Implement a bounded change.",
        allowed_paths=["safe.py"],
        validators=["python -m pytest"],
    )

    assert packet["packet_ready"] is False
    assert packet["reason_code"] == "identity_fields_missing"
    assert packet["missing_identity_fields"] == ["bucket_id"]


def test_repository_aligned_builder_blocks_forbidden_receipt_destination():
    module = load_module()
    packet = module.build_repository_aligned_apply_packet(
        repository_state={"worktree": "/owned-memory", "branch": "owned", "status_lines": []},
        packet_identity=repository_identity(), mission="Check composed source scope.",
        allowed_paths=["docs/owned.md"], validators=["owned validation label"],
        forbidden_paths=[module.DELIVERY_RECEIPT_PATHS[1]],
    )
    assert packet["packet_ready"] is False
    assert packet["codex_prompt_text"] == ""
    assert packet["reason_code"] == "composed_scope_conflict"


def test_campaign_builder_actual_consumer_and_exact_task_scope(tmp_path, monkeypatch):
    from automation.orchestration.aios_codex_packet_builder import (
        build_repository_aligned_apply_packet,
    )
    from automation.orchestration.relay.aios_codex_prompt_consumer_v1 import (
        validate_prompt,
    )
    from tests.orchestration.test_aios_repo_state_evidence import _campaign_fixture
    _, item, state, profile, reader, _, _, _ = _campaign_fixture(tmp_path, monkeypatch)
    result = build_repository_aligned_apply_packet(repository_state=state, packet_identity=item["packet_identity"],
        mission=item["mission"], allowed_paths=item["allowed_paths"], forbidden_paths=item["forbidden_paths"],
        validators=item["validators"], approval_authority=item["approval_authority"], campaign_profile=profile,
        campaign_admission_reader=reader, campaign_selection=profile.selection)
    assert result["packet_ready"] is True and result["write_scope"] == item["allowed_paths"]
    prompt = tmp_path / "campaign-prompt.md"; prompt.write_text(result["codex_prompt_text"], encoding="utf-8")
    assert list(validate_prompt(prompt).allowed_paths) == item["allowed_paths"]
    assert "Observed is_clean: false; legacy safe_for_apply: false" in result["codex_prompt_text"]
    assert "$(" not in result["codex_prompt_text"] and "TASK TIMING START:" not in result["codex_prompt_text"]
    assert ".aios/runtime/engineering_timing/" not in result["write_scope"]
    assert result["delivery_tracking"]["runtime_admission_qualified"] is False
    assert not (tmp_path / "relay").exists()
    missing = build_repository_aligned_apply_packet(repository_state=state, packet_identity=item["packet_identity"],
        mission=item["mission"], allowed_paths=item["allowed_paths"], forbidden_paths=item["forbidden_paths"],
        validators=item["validators"], approval_authority=item["approval_authority"], campaign_profile=profile,
        campaign_selection=profile.selection)
    assert missing["packet_ready"] is False
