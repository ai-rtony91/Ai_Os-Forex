from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "automation" / "orchestration" / "aios_candidate_packet_evidence_adapter.py"
PLANNER_PATH = REPO_ROOT / "automation" / "orchestration" / "aios_packet_queue_planner.py"


def load_adapter():
    spec = importlib.util.spec_from_file_location("aios_candidate_packet_evidence_adapter", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_planner():
    spec = importlib.util.spec_from_file_location("aios_packet_queue_planner", PLANNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def promoted_candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "promoted": True,
        "packet_id": "PKT-AIOS-PROMOTED",
        "title": "Build promoted self-build packet",
        "lane": "promoted-self-build",
        "priority": "high",
        "milestone_value": 99,
        "risk_level": "low",
        "status": "candidate",
        "required_files": ["automation/orchestration/promoted.py"],
        "blocked_files": [],
        "required_approvals": [],
        "validators": ["python -m pytest -p no:cacheprovider tests/orchestration/test_promoted.py -q"],
        "dependencies": [],
        "conflicts": [],
        "safety_flags": [],
    }
    payload.update(overrides)
    return payload


def assert_preview_only(result: dict[str, object]) -> None:
    assert result["commands_executed"] == []
    assert result["files_written"] == []
    assert result["workers_dispatched"] is False
    assert result["queues_mutated"] is False
    assert result["approvals_mutated"] is False
    safety = result["safety"]
    assert isinstance(safety, dict)
    assert safety["preview_only"] is True
    assert safety["evidence_only"] is True
    assert safety["command_execution"] is False
    assert safety["filesystem_writes"] is False
    assert safety["reports_written"] is False
    assert safety["network_access"] is False


def test_empty_evidence_returns_default_safe_self_build_candidate() -> None:
    adapter = load_adapter()

    result = adapter.build_candidate_packet_evidence({})
    candidate = result["candidate_packets"][0]

    assert result["schema"] == "AIOS_CANDIDATE_PACKET_EVIDENCE_ADAPTER.v1"
    assert result["default_candidate_used"] is True
    assert candidate["packet_id"] == "PKT-AIOS-SELFROUTE-CANDIDATE-EVIDENCE-INTEGRATION"
    assert candidate["title"] == "Connect candidate packet evidence adapter into self-route"
    assert candidate["lane"] == "connect-candidate-evidence-to-selfroute"
    assert candidate["priority"] == "high"
    assert candidate["milestone_value"] == "high"
    assert candidate["risk_level"] == "low"
    assert candidate["status"] == "candidate"
    assert "automation/orchestration/runtime/Invoke-AiOsRuntimeSelfRoute.ps1" in candidate["required_files"]
    assert_preview_only(result)


def test_generated_reports_paths_are_archive_noise_not_candidate_packets() -> None:
    adapter = load_adapter()

    result = adapter.build_candidate_packet_evidence(
        {"repo_status": {"untracked_paths": ["Reports/aios_control_plane/status.json"]}}
    )

    assert result["archive_noise"][0]["path"] == "Reports/aios_control_plane/status.json"
    assert result["archive_noise"][0]["classification"] == "archive_noise"
    assert all(
        "Reports/" not in path
        for candidate in result["candidate_packets"]
        for path in candidate["required_files"]
    )


def test_control_review_bridge_paths_are_archive_noise_not_candidate_packets() -> None:
    adapter = load_adapter()

    result = adapter.build_candidate_packet_evidence(
        {"repo_status": {"untracked_paths": ["control/review_bridge/codex_reports/report.json"]}}
    )

    assert result["archive_noise"][0]["path"] == "control/review_bridge/codex_reports/report.json"
    assert result["archive_noise"][0]["reason"] == "generated_backlog_path_not_promoted"
    assert all(
        "control/review_bridge/" not in path
        for candidate in result["candidate_packets"]
        for path in candidate["required_files"]
    )


def test_work_packet_preview_paths_are_noise_unless_explicitly_promoted() -> None:
    adapter = load_adapter()

    noise = adapter.build_candidate_packet_evidence(
        {"work_packet_preview_paths": ["automation/orchestration/work_packets/preview/next.md"]}
    )
    promoted = adapter.build_candidate_packet_evidence(
        {
            "work_packet_previews": [
                promoted_candidate(
                    path="automation/orchestration/work_packets/preview/next.md",
                    packet_id="PKT-AIOS-PREVIEW-PROMOTED",
                )
            ]
        }
    )

    assert noise["archive_noise"][0]["classification"] == "archive_noise"
    assert promoted["archive_noise"] == []
    assert promoted["candidate_packets"][0]["packet_id"] == "PKT-AIOS-PREVIEW-PROMOTED"


def test_explicitly_promoted_candidate_is_normalized() -> None:
    adapter = load_adapter()

    result = adapter.build_candidate_packet_evidence(
        {"manual_candidates": [promoted_candidate(required_files="automation/orchestration/one.py")]}
    )
    candidate = result["candidate_packets"][0]

    assert result["default_candidate_used"] is False
    assert candidate["packet_id"] == "PKT-AIOS-PROMOTED"
    assert candidate["required_files"] == ["automation/orchestration/one.py"]
    assert candidate["blocked_files"] == []
    assert candidate["dependencies"] == []
    assert candidate["conflicts"] == []


def test_candidate_output_is_compatible_with_packet_queue_planner_required_fields() -> None:
    adapter = load_adapter()
    planner = load_planner()

    result = adapter.build_candidate_packet_evidence({})
    candidate = result["candidate_packets"][0]
    for field in [
        "packet_id",
        "title",
        "lane",
        "priority",
        "milestone_value",
        "risk_level",
        "status",
        "required_files",
        "blocked_files",
        "required_approvals",
        "validators",
        "dependencies",
        "conflicts",
        "safety_flags",
    ]:
        assert field in candidate

    plan = planner.build_packet_queue_planner(result["candidate_packets"])
    assert plan["queue_status"] == "selected"
    assert plan["selected_packet"]["packet_id"] == candidate["packet_id"]


def test_forex_builder_alignment_is_present() -> None:
    adapter = load_adapter()

    candidate = adapter.build_candidate_packet_evidence({})["candidate_packets"][0]
    alignment = candidate["forex_builder_alignment"]

    assert alignment["proof_target"] == "industrial-grade forex bot builder"
    assert "no broker/live/secrets" in alignment["milestone"]
    assert alignment["requires_future_gates_before_execution"] is True


def test_unsafe_broker_live_secret_and_webhook_paths_become_safety_flags() -> None:
    adapter = load_adapter()

    result = adapter.build_candidate_packet_evidence(
        {
            "manual_candidates": [
                promoted_candidate(
                    required_files=[
                        "broker/live_order.py",
                        "trading/secret_webhook_handler.py",
                    ],
                )
            ]
        }
    )
    flags = result["candidate_packets"][0]["safety_flags"]

    assert any("unsafe_path:broker" in flag for flag in flags)
    assert any("unsafe_path:live" in flag for flag in flags)
    assert any("unsafe_path:secret" in flag for flag in flags)
    assert any("unsafe_path:webhook" in flag for flag in flags)


def test_required_approvals_are_preserved() -> None:
    adapter = load_adapter()

    candidate = adapter.build_candidate_packet_evidence(
        {
            "manual_candidates": [
                promoted_candidate(required_approvals=["Anthony approval for local apply"])
            ]
        }
    )["candidate_packets"][0]

    assert candidate["required_approvals"] == ["Anthony approval for local apply"]


def test_repository_state_survives_normalization_and_inherited_state() -> None:
    adapter, planner = load_adapter(), load_planner()
    state = {"worktree": "/owned/task-worktree", "branch": "lane/owned"}
    for evidence in (
        {"manual_candidates": [promoted_candidate(repository_state=state)]},
        {"manual_candidates": [promoted_candidate()], "repository_state": state},
    ):
        result = adapter.build_candidate_packet_evidence(evidence)
        preview = planner.build_packet_queue_planner(result)["codex_ready_packet_preview"]
        assert preview["packet_ready"] is True
        assert preview["repository_state"] == state


def test_invalid_candidate_state_is_not_replaced_by_inherited_state() -> None:
    result = load_adapter().build_candidate_packet_evidence({
        "repository_state": {"worktree": "/owned", "branch": "lane/owned"},
        "manual_candidates": [promoted_candidate(repository_state={})],
    })
    preview = load_planner().build_packet_queue_planner(result)["codex_ready_packet_preview"]
    assert preview["packet_ready"] is False
    assert preview["reason_code"] == "repository_state_missing"


def test_explicit_observation_replaces_stale_candidate_state() -> None:
    adapter, planner = load_adapter(), load_planner()
    evidence = {"manual_candidates": [promoted_candidate(repository_state={"worktree": "/stale", "branch": "stale"})]}
    state = {"worktree": "/observed", "branch": "lane/observed"}
    result = adapter.build_candidate_packet_evidence(evidence, repository_state=state)
    assert planner.build_packet_queue_planner(result)["codex_ready_packet_preview"]["repository_state"] == state
    failed = adapter.build_candidate_packet_evidence(evidence, repository_state={})
    assert planner.build_packet_queue_planner(failed)["codex_ready_packet_preview"]["packet_ready"] is False


def test_cli_observes_git_and_refuses_unobserved_repository(tmp_path, capsys) -> None:
    import json
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-b", "lane/observed", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "--allow-empty", "-m", "offline fixture"], check=True, capture_output=True)
    adapter, planner = load_adapter(), load_planner()
    stale = {"worktree": "/stale", "branch": "stale"}
    for target, ready in ((root, True), (tmp_path, False)):
        adapter.main(["--repo-root", str(target), "--evidence", json.dumps({"manual_candidates": [promoted_candidate(repository_state=stale)]})])
        result = json.loads(capsys.readouterr().out)
        preview = planner.build_packet_queue_planner(result)["codex_ready_packet_preview"]
        assert preview["packet_ready"] is ready
        if ready:
            assert preview["repository_state"] == {"worktree": str(root), "branch": "lane/observed"}


def test_validators_are_preserved() -> None:
    adapter = load_adapter()

    validator = "python -m pytest -p no:cacheprovider tests/orchestration/test_custom.py -q"
    candidate = adapter.build_candidate_packet_evidence(
        {"manual_candidates": [promoted_candidate(validators=[validator])]}
    )["candidate_packets"][0]

    assert candidate["validators"] == [validator]


def test_commands_executed_is_empty() -> None:
    adapter = load_adapter()

    assert adapter.build_candidate_packet_evidence({})["commands_executed"] == []


def test_files_written_is_empty() -> None:
    adapter = load_adapter()

    assert adapter.build_candidate_packet_evidence({})["files_written"] == []


def test_workers_dispatched_false() -> None:
    adapter = load_adapter()

    assert adapter.build_candidate_packet_evidence({})["workers_dispatched"] is False


def test_queues_mutated_false() -> None:
    adapter = load_adapter()

    assert adapter.build_candidate_packet_evidence({})["queues_mutated"] is False


def test_approvals_mutated_false() -> None:
    adapter = load_adapter()

    assert adapter.build_candidate_packet_evidence({})["approvals_mutated"] is False


def test_safety_preview_only_true() -> None:
    adapter = load_adapter()

    assert adapter.build_candidate_packet_evidence({})["safety"]["preview_only"] is True


def test_source_does_not_import_subprocess_network_or_file_write_tools() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    for forbidden in [
        "import subprocess",
        "from subprocess",
        "import requests",
        "import socket",
        "import urllib",
        "http.client",
        "open(",
        "write_text",
        "write_bytes",
        "with open",
        "os.system",
        "system(",
        "start-process",
    ]:
        assert forbidden not in source
