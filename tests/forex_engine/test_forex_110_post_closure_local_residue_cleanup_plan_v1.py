from __future__ import annotations

import json
import subprocess
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import automation.forex_engine.forex_110_post_closure_local_residue_cleanup_plan_v1 as cleanup_plan  # noqa: E402
from automation.forex_engine.forex_110_post_closure_local_residue_cleanup_plan_v1 import (  # noqa: E402
    build_report_markdown,
    run_forex_110_post_closure_local_residue_cleanup_plan_v1,
)
from scripts.forex_delivery.run_forex_110_post_closure_local_residue_cleanup_plan_v1 import (  # noqa: E402
    REPORT_NAME,
    STATE_NAME,
    main,
)


def _git_lines(repo_root: Path, args: list[str]) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return [line.rstrip() for line in completed.stdout.splitlines() if line.strip()]


def _current_branch(repo_root: Path) -> str:
    lines = _git_lines(repo_root, ["status", "--short", "--branch"])
    if not lines or not lines[0].startswith("## "):
        return ""
    status_body = lines[0][3:]
    branch = status_body.split("...", 1)[0]
    return branch.split(" [", 1)[0]


def test_run_function_returns_classified_cleanup_plan() -> None:
    non_ignored_expected = len(_git_lines(ROOT, ["ls-files", "--others", "--exclude-standard"]))
    ignored_expected = len(_git_lines(ROOT, ["ls-files", "-i", "-o", "--exclude-standard"]))
    branch = _current_branch(ROOT)
    result = run_forex_110_post_closure_local_residue_cleanup_plan_v1(
        ROOT / "Reports" / "forex_delivery",
        repo_root=ROOT,
    )

    assert result["packet_id"] == "PKT-FOREX-110-POST-CLOSURE-LOCAL-RESIDUE-CLEANUP-PLAN-V1"
    assert result["cleanup_plan_status"] in {
        "PLAN_ONLY",
        "PLAN_BLOCKED_PRECHECK_RETRY_REQUIRED",
        "PLAN_BLOCKED_NON_MAIN_BRANCH",
    }
    assert result["repo_status"]["branch"] == branch
    if branch == "main":
        assert result["cleanup_plan_status"] == "PLAN_ONLY"
    else:
        assert result["cleanup_plan_status"] == "PLAN_BLOCKED_NON_MAIN_BRANCH"
    assert result["non_ignored_untracked_count"] == non_ignored_expected
    assert result["ignored_local_generated_count"] == ignored_expected
    assert result["deletion_performed"] is False
    assert result["git_clean_performed"] is False
    assert result["gitignore_modified"] is False
    assert result["broker_api_used"] is False
    assert result["credentials_used"] is False
    assert result["env_read"] is False
    assert result["account_identifiers_used"] is False
    assert result["order_execution"] is False
    assert result["demo_authorized"] is False
    assert result["live_authorized"] is False
    assert result["scheduler_started"] is False
    assert result["daemon_started"] is False
    assert result["webhook_started"] is False
    assert result["background_loop_started"] is False
    assert result["bitwarden_started"] is False

    assert isinstance(result["safe_to_clean_later"], list)
    assert all(
        {"category", "count", "samples", "next_step"}.issubset(item)
        for item in result["safe_to_clean_later"]
    )
    assert cleanup_plan._build_safe_to_clean_later([]) == []
    assert any(item["category"] == ".local_backlog/" for item in result["review_required_before_clean"])
    assert result["protected_do_not_touch"]


def test_plan_report_is_plan_only() -> None:
    result = run_forex_110_post_closure_local_residue_cleanup_plan_v1(
        ROOT / "Reports" / "forex_delivery",
        repo_root=ROOT,
    )
    report = build_report_markdown(result)

    assert "This is a cleanup PLAN ONLY." in report
    assert "No delete occurred." in report
    assert "No git clean occurred." in report
    assert "No broker/live/demo/order/money/credential work occurred." in report
    assert "Safe-to-clean items require a later explicit APPLY cleanup packet." in report
    assert "Review-required items require owner review before any deletion." in report
    assert "Protected do not touch items must remain unchanged." in report


def test_runner_writes_state_and_report(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    exit_code = main(
        [
            "--report-root",
            str(ROOT / "Reports" / "forex_delivery"),
            "--output-root",
            str(output_root),
            "--write-state",
            "--write-report",
        ],
    )
    state_file = output_root / STATE_NAME
    report_file = output_root / REPORT_NAME

    assert exit_code == 0
    assert state_file.exists()
    assert report_file.exists()

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["packet_id"] == "PKT-FOREX-110-POST-CLOSURE-LOCAL-RESIDUE-CLEANUP-PLAN-V1"
    assert state["cleanup_plan_status"] in {
        "PLAN_ONLY",
        "PLAN_BLOCKED_PRECHECK_RETRY_REQUIRED",
        "PLAN_BLOCKED_NON_MAIN_BRANCH",
    }
    assert "PLAN ONLY" in report_file.read_text(encoding="utf-8")

