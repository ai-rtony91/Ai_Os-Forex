from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "automation" / "orchestration" / "aios_work_countdown_v1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("aios_work_countdown_v1", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def packet(packet_id: str, status: str, **extra: object) -> dict[str, object]:
    value: dict[str, object] = {
        "packet_id": packet_id, "title": packet_id, "status": status,
        "priority": "medium", "milestone_value": 10, "risk_level": "low",
        "required_files": [f"automation/orchestration/{packet_id.lower()}.py"],
        "validators": ["python -m pytest test.py -q"],
    }
    value.update(extra)
    return value


def inventory(*packets: dict[str, object]) -> dict[str, object]:
    return {"authoritative_packet_inventory": True, "packets": list(packets)}


def test_countdown_passes_repository_state_to_ready_packet() -> None:
    state = {"worktree": "/owned/countdown", "branch": "lane/countdown"}
    result = load_module().build_work_countdown(inventory(packet("READY", "ready")), repository_state=state)
    preview = result["queue_plan"]["codex_ready_packet_preview"]
    assert preview["packet_ready"] is True
    assert preview["repository_state"] == state


@pytest.fixture
def packet_repo(tmp_path: Path) -> Path:
    for state in ("active", "blocked", "complete"):
        (tmp_path / "automation/orchestration/work_packets" / state).mkdir(parents=True)
    return tmp_path


def write_json(root: Path, state: str, name: str, payload: object) -> Path:
    path = root / "automation/orchestration/work_packets" / state / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_live_folders_are_authoritative_and_mismatch_is_reported(packet_repo: Path) -> None:
    module = load_module()
    write_json(packet_repo, "active", "a.json", packet("ACTIVE", "complete"))
    write_json(packet_repo, "blocked", "b.json", packet("BLOCKED", "active"))
    write_json(packet_repo, "complete", "c.json", packet("COMPLETE", "blocked"))
    result = module.build_work_countdown(repo_root=packet_repo)
    assert result["current_task"]["packet_id"] == "ACTIVE"
    assert result["blocked_tasks"][0]["packet_id"] == "BLOCKED"
    assert result["completed_tasks"][0]["packet_id"] == "COMPLETE"
    assert result["completed_packet_count"] == 1
    assert result["completion_percentage"] == 33.33
    assert len(result["canonical_work_packet_inventory"]["folder_status_mismatches"]) == 3


def test_json_and_markdown_ids_parse_and_legacy_without_id_is_excluded(packet_repo: Path) -> None:
    module = load_module()
    write_json(packet_repo, "complete", "z.json", packet("JSON-ID", "complete"))
    md = packet_repo / "automation/orchestration/work_packets/active/a.md"
    md.write_text("# Packet\nPACKET ID: MD-ID\nSTATUS: active\n", encoding="utf-8")
    legacy = packet_repo / "automation/orchestration/work_packets/blocked/legacy.md"
    legacy.write_text("# Historical packet without an ID\n", encoding="utf-8")
    state = module.build_work_countdown(repo_root=packet_repo)
    inv = state["canonical_work_packet_inventory"]
    assert [item["packet_id"] for item in inv["records"]] == ["MD-ID", "JSON-ID"]
    assert inv["inventory_status"] == "PARTIAL"
    assert inv["excluded_legacy_records"][0]["record_identity"].endswith("legacy.md")
    assert state["total_packet_count"] == 2
    assert state["evidence_limitation"].startswith("Scoped percentage")


def test_duplicate_ids_and_parse_failures_block_calculation(packet_repo: Path) -> None:
    module = load_module()
    write_json(packet_repo, "active", "a.json", packet("DUP", "active"))
    write_json(packet_repo, "complete", "b.json", packet("DUP", "complete"))
    (packet_repo / "automation/orchestration/work_packets/blocked/bad.json").write_text("{", encoding="utf-8")
    result = module.build_work_countdown(repo_root=packet_repo)
    inv = result["canonical_work_packet_inventory"]
    assert inv["inventory_status"] == "BLOCKED"
    assert inv["duplicate_packet_ids"] == ["DUP"]
    assert len(inv["parse_failures"]) == 1
    assert result["data_quality_status"] == "BLOCKED"
    assert result["completion_percentage"] is None
    assert result["next_task"] == "REPAIR_CANONICAL_PACKET_INVENTORY"


def test_machine_readable_missing_packet_id_blocks_calculation(packet_repo: Path) -> None:
    write_json(packet_repo, "active", "missing.json", {"title": "Missing ID", "status": "active"})
    result = load_module().build_work_countdown(repo_root=packet_repo)
    inventory_state = result["canonical_work_packet_inventory"]
    assert inventory_state["inventory_status"] == "BLOCKED"
    assert inventory_state["missing_packet_ids"] == [
        "automation/orchestration/work_packets/active/missing.json"
    ]
    assert "machine_readable_packet_ids_missing" in inventory_state["data_quality_blockers"]
    assert result["completion_percentage"] is None


def test_empty_inventory_routes_registration(packet_repo: Path) -> None:
    result = load_module().build_work_countdown(repo_root=packet_repo)
    assert result["inventory_status"] == "EMPTY"
    assert result["evidence_status"] == "INCOMPLETE"
    assert result["completion_percentage"] is None
    assert result["next_task"] == "CREATE_OR_REGISTER_CANONICAL_WORK_PACKET"


def test_counts_are_bounded_and_blocked_gets_no_credit(packet_repo: Path) -> None:
    module = load_module()
    for index in range(2):
        write_json(packet_repo, "complete", f"c{index}.json", packet(f"C{index}", "complete"))
    write_json(packet_repo, "blocked", "b.json", packet("B", "blocked"))
    result = module.build_work_countdown(repo_root=packet_repo)
    assert result["total_packet_count"] == 3
    assert result["completed_packet_count"] == 2
    assert result["completed_packet_count"] <= result["total_packet_count"]
    assert 0 <= result["completion_percentage"] <= 100
    assert result["completion_percentage"] == 66.67


def test_paths_are_deterministic_and_source_files_are_not_modified(packet_repo: Path) -> None:
    module = load_module()
    later = write_json(packet_repo, "complete", "z.json", packet("Z", "complete"))
    earlier = write_json(packet_repo, "active", "a.json", packet("A", "active"))
    before = {path: path.read_bytes() for path in (later, earlier)}
    first = module.load_canonical_work_packet_inventory(packet_repo)
    second = module.load_canonical_work_packet_inventory(packet_repo)
    assert [item["source_path"] for item in first["records"]] == sorted(item["source_path"] for item in first["records"])
    assert module.stable_json(first) == module.stable_json(second)
    assert first["source_files_modified"] is False
    assert before == {path: path.read_bytes() for path in before}


def test_explicit_evidence_precedes_repo_and_selection_is_deterministic(packet_repo: Path) -> None:
    module = load_module()
    write_json(packet_repo, "complete", "ignored.json", packet("IGNORED", "complete"))
    evidence = inventory(packet("LOW", "ready", priority="low"), packet("HIGH", "ready", priority="high"))
    result = module.build_work_countdown(evidence, repo_root=packet_repo)
    assert result["next_task"]["packet_id"] == "HIGH"
    assert result["total_packet_count"] == 2


def test_telemetry_and_campaign_percentages_do_not_override_packet_math(packet_repo: Path) -> None:
    module = load_module()
    write_json(packet_repo, "active", "a.json", packet("A", "active"))
    write_json(packet_repo, "complete", "c.json", packet("C", "complete"))
    result = module.build_work_countdown(
        repo_root=packet_repo,
        repository_state={"stale_telemetry_completion_percentage": 99},
        campaign_registry_context={"completion_percentage": 87},
    )
    assert result["completion_percentage"] == 50.0
    assert result["campaign_registry_planning_context"]["completion_percentage"] == 87
    assert result["dependency_graph"]["unified_queue_index_projection"] == "READ_ONLY_PROJECTION"
    assert result["dependency_graph"]["campaign_registry_planning_context"] == "PLANNING_CONTEXT"


def test_external_provider_and_protected_actions_remain_separate(packet_repo: Path) -> None:
    write_json(packet_repo, "complete", "c.json", packet("C", "complete"))
    result = load_module().build_work_countdown(repo_root=packet_repo)
    provider = result["first_withdrawable_dollar_state"]
    assert provider["provider_status"] == "EXTERNAL_PENDING_VERIFICATION"
    assert provider["verification_state"] == "WAITING_FOR_REMOTE_EVIDENCE"
    assert result["external_wait_state"]["excluded_from_engineering_stages"] is True
    assert result["dependency_graph"]["first_withdrawable_dollar_external_provider"] == "EXTERNAL_PENDING"
    assert result["protected_actions"] and not any(result["protected_actions"].values())


def test_stable_json_serialization(packet_repo: Path) -> None:
    module = load_module()
    write_json(packet_repo, "complete", "c.json", packet("C", "complete"))
    result = module.build_work_countdown(repo_root=packet_repo)
    assert module.stable_json(result) == module.stable_json(result)
    assert json.loads(module.stable_json(result))["schema"] == "AIOS_WORK_COUNTDOWN.v1"


def test_countdown_consumes_explicit_first_dollar_evidence(packet_repo: Path) -> None:
    write_json(packet_repo, "complete", "c.json", packet("C", "complete"))
    receipt = {
        "packet_id": "C", "canonical": True, "evidence_provenance": "receipt",
        "pr_id": "1", "merged": True, "merge_commit_sha": "abcdef1234567",
        "test_command": "pytest", "test_conclusion": "passed",
        "ci_check_id": "ci-1", "ci_conclusion": "success", "engineering_hours": 25,
    }
    result = load_module().build_work_countdown(
        repo_root=packet_repo,
        first_withdrawable_dollar_state={
            "execution_receipts": [receipt], "expected_packet_count": 1,
            "remaining_hours": {"low": 25, "best": 75, "high": 125},
        },
    )
    assert result["hours_completed"] == 25
    assert result["hours_remaining_best"] == 75
    assert result["weeks_remaining_50h_best"] == 1.5
    assert result["derived_completion_percentage"] == 25.0
    assert result["credited_packet_count"] == 1
    assert result["dependency_graph"]["first_withdrawable_dollar_external_provider"] == "EVIDENCE_PROJECTION"


def test_folder_completion_is_not_receipt_credit(packet_repo: Path) -> None:
    write_json(packet_repo, "complete", "c.json", packet("C", "complete"))
    result = load_module().build_work_countdown(repo_root=packet_repo)
    assert result["completion_percentage"] == 100.0
    assert result["hours_completed"] is None
    assert result["derived_completion_percentage"] is None


def test_cli_routes_first_dollar_evidence_into_countdown(
    packet_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_json(packet_repo, "complete", "c.json", packet("C", "complete"))
    receipt = {
        "packet_id": "C", "canonical": True, "evidence_provenance": "receipt",
        "pr_id": "1325", "merged": True, "merge_commit_sha": "65608879b0d5385",
        "test_command": "pytest", "test_conclusion": "passed",
        "ci_check_id": "ci-1325", "ci_conclusion": "success",
        "engineering_hours": 3,
    }
    first_dollar_evidence = {
        "execution_receipts": [receipt], "expected_packet_count": 1,
        "remaining_hours": {"low": 2, "best": 4, "high": 8},
        "highest_verified_blocker": "COLLECT_GENUINE_DEMO_PROFIT_EVIDENCE",
    }

    exit_code = load_module().main([
        "--repo-root", str(packet_repo),
        "--first-withdrawable-dollar-evidence", json.dumps(first_dollar_evidence),
    ])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["hours_completed"] == 3
    assert result["hours_remaining_best"] == 4
    assert result["next_verified_blocker"] == "COLLECT_GENUINE_DEMO_PROFIT_EVIDENCE"
    assert result["dependency_graph"]["first_withdrawable_dollar_external_provider"] == "EVIDENCE_PROJECTION"


def test_cli_reads_first_dollar_evidence_file(
    packet_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_json(packet_repo, "complete", "c.json", packet("C", "complete"))
    evidence_path = packet_repo / "first-dollar-evidence.json"
    evidence_path.write_text(json.dumps({
        "execution_receipts": [{
            "packet_id": "C", "canonical": True,
            "evidence_provenance": "receipt", "pr_id": "1326",
            "merged": True, "merge_commit_sha": "aa5c654b86326",
            "test_command": "pytest", "test_conclusion": "passed",
            "ci_check_id": "ci-1326", "ci_conclusion": "success",
            "engineering_hours": 5,
        }],
        "expected_packet_count": 1,
        "remaining_hours": {"low": 1, "best": 3, "high": 6},
        "highest_verified_blocker": "COLLECT_GENUINE_DEMO_PROFIT_EVIDENCE",
    }), encoding="utf-8")

    exit_code = load_module().main([
        "--repo-root", str(packet_repo),
        "--first-withdrawable-dollar-evidence-file", str(evidence_path),
    ])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["hours_completed"] == 5
    assert result["hours_remaining_best"] == 3
    assert result["next_verified_blocker"] == "COLLECT_GENUINE_DEMO_PROFIT_EVIDENCE"


def test_cli_rejects_two_first_dollar_evidence_sources(packet_repo: Path) -> None:
    evidence_path = packet_repo / "first-dollar-evidence.json"
    evidence_path.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        load_module().main([
            "--first-withdrawable-dollar-evidence", "{}",
            "--first-withdrawable-dollar-evidence-file", str(evidence_path),
        ])

    assert exc_info.value.code == 2
