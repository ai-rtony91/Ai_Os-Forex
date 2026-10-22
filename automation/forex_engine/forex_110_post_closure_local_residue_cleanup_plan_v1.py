"""Create a repo-safe post-closure local residue cleanup plan for Forex 110.

This module is report-only. It must never delete files, run git clean, modify
``.gitignore``, or perform broker/demo/live/order/money/credential actions.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Iterable

PACKET_ID = "PKT-FOREX-110-POST-CLOSURE-LOCAL-RESIDUE-CLEANUP-PLAN-V1"
ENGINE_VERSION = "forex_110_post_closure_local_residue_cleanup_plan_v1"

DEFAULT_REPORT_ROOT = Path("Reports") / "forex_delivery"

REQUIRED_ROOT_FILE_PATH = Path("Reports/forex_delivery")

ROOT_RUNTIME_JSON_FILES = (
    "approval.json",
    "completion_report.json",
    "validation_result.json",
    "task_log.json",
)

FOREX_110_PROOF_ARTIFACT_PREFIXES = (
    "Reports/forex_delivery/AIOS_FOREX_110_",
)

FOREX_110_PROTECTED_FILES = (
    "Reports/forex_delivery/AIOS_FOREX_110_COMPLETION_INDEX_V1.md",
    "Reports/forex_delivery/AIOS_FOREX_FINAL_PROTECTED_BOUNDARY_HANDOFF_V1.md",
    "Reports/forex_delivery/AIOS_FOREX_POST_110_NEXT_PROJECT_BLOCKER_BITWARDEN_V1.md",
)

FORBIDDEN_ACTIONS = (
    "git clean",
    "Remove-Item",
    "del",
    "rm",
    "unlink",
    "shutil.rmtree",
    "deleting ignored Reports",
    "deleting local backlog/hold",
    "modifying .gitignore",
    "modifying source-of-truth files",
    "modifying Forex 110 proof files",
)

PROTECTED_PATH_PREFIXES = (
    "AGENTS.md",
    "README.md",
    "RISK_POLICY.md",
    "WHITEPAPER.md",
    "docs/governance/source-of-truth-map.md",
    "docs/governance/AI_OS_REPO_MEMORY.md",
    "docs/governance/aios-identity-and-lane-governance.md",
    "docs/audits/active-system-map.md",
    "docs/AI_OS/",
    ".env",
    "archive/reports_legacy/",
    "telemetry/",
    "services/",
)


def run_forex_110_post_closure_local_residue_cleanup_plan_v1(
    report_root: str | Path = DEFAULT_REPORT_ROOT,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable local residue cleanup plan."""

    root = Path(repo_root) if repo_root is not None else _repo_root_from_report_root(Path(report_root))
    status = _git_status_lines(root)
    non_ignored_untracked_count, ignored_items = _run_git_counts(root)
    tracked_generated_candidates = _find_tracked_log_candidates(root)
    safe_to_clean_later = _build_safe_to_clean_later(ignored_items)
    review_required_before_clean = _build_review_required_before_clean(ignored_items, root)
    repo_clean_state = _is_repo_clean(status["dirty_lines"])

    root_runtime_json_files = [
        str(path)
        for path in (root / name for name in ROOT_RUNTIME_JSON_FILES)
        if path.exists()
    ]

    forex_110_closure_landed = (
        _is_truthy((root / "Reports/forex_delivery/AIOS_FOREX_110_COMPLETION_INDEX_V1.md").exists())
        and _is_truthy((root / "Reports/forex_delivery/AIOS_FOREX_FINAL_PROTECTED_BOUNDARY_HANDOFF_V1.md").exists())
        and _is_truthy((root / "Reports/forex_delivery/AIOS_FOREX_POST_110_NEXT_PROJECT_BLOCKER_BITWARDEN_V1.md").exists())
    )

    if status["branch"] != "main":
        cleanup_plan_status = "PLAN_BLOCKED_NON_MAIN_BRANCH"
    else:
        cleanup_plan_status = "PLAN_ONLY"

    attack_to_finish = _attack_to_finish(
        cleanup_plan_status=cleanup_plan_status,
        branch=status["branch"],
        repo_clean=repo_clean_state,
        non_ignored_nontracked=non_ignored_untracked_count,
    )

    repo_status = {
        "branch": status["branch"],
        "status_line_count": len(status["lines"]),
        "dirty_line_count": len(status["dirty_lines"]),
        "working_tree_clean": repo_clean_state,
        "remote": status["remote"],
        "gitignore_permission_warning": status["gitignore_permission_warning"],
    }

    result: dict[str, Any] = {
        "packet_id": PACKET_ID,
        "cleanup_plan_status": cleanup_plan_status,
        "repo_status": repo_status,
        "non_ignored_untracked_count": non_ignored_untracked_count,
        "ignored_local_generated_count": len(ignored_items),
        "safe_to_clean_later": safe_to_clean_later,
        "review_required_before_clean": review_required_before_clean,
        "protected_do_not_touch": list(_build_protected_items()),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "tracked_generated_candidates": tracked_generated_candidates,
        "root_runtime_json_files": root_runtime_json_files,
        "gitignore_permission_warning": status["gitignore_warning_text"],
        "forex_110_closure_landed": bool(forex_110_closure_landed),
        "deletion_performed": False,
        "git_clean_performed": False,
        "gitignore_modified": False,
        "broker_api_used": False,
        "credentials_used": False,
        "env_read": False,
        "account_identifiers_used": False,
        "order_execution": False,
        "demo_authorized": False,
        "live_authorized": False,
        "scheduler_started": False,
        "daemon_started": False,
        "webhook_started": False,
        "background_loop_started": False,
        "bitwarden_started": False,
            "next_safe_action": _next_safe_action(cleanup_plan_status),
        "ATTACK_TO_FINISH": attack_to_finish,
    }
    return result


def build_report_markdown(result: dict[str, Any]) -> str:
    """Build the plan markdown report."""

    safe_lines = _format_category_lines(result["safe_to_clean_later"], "Safe to clean later")
    review_lines = _format_category_lines(
        result["review_required_before_clean"],
        "Review required before clean",
    )

    protected_lines = ["- " + item for item in result["protected_do_not_touch"]]
    forbidden_lines = ["- " + item for item in result["forbidden_actions"]]

    lines = [
        "# AIOS Forex 110 Post-Closure Local Residue Cleanup Plan V1",
        "",
        f"Packet ID: `{result['packet_id']}`",
        f"Cleanup plan status: `{result['cleanup_plan_status']}`",
        f"Repo status: `{result['repo_status']}`",
        f"Forex 110 closure landed: `{str(result['forex_110_closure_landed']).lower()}`",
        "",
        "## Required mode",
        "- This is a cleanup PLAN ONLY.",
        "- No delete occurred.",
        "- No git clean occurred.",
        "- No broker/live/demo/order/money/credential work occurred.",
        "- Protected Forex 110 proof artifacts and governance boundaries remain unchanged.",
        "",
        "## Planned inventory summary",
        f"- Non-ignored untracked files: `{result['non_ignored_untracked_count']}`",
        f"- Ignored/local-generated files: `{result['ignored_local_generated_count']}`",
        f"- Tracked generated candidates: `{len(result['tracked_generated_candidates'])}`",
        f"- Root runtime JSON files: `{len(result['root_runtime_json_files'])}`",
        "",
    ]
    lines.extend(safe_lines)
    lines.extend(review_lines)
    lines.extend(
        [
            "## Protected do not touch",
            *protected_lines,
            "",
            "## Forbidden actions",
            *forbidden_lines,
            "",
            "## ATTACK_TO_FINISH",
        ]
    )
    for key, value in result["ATTACK_TO_FINISH"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.extend(
        [
            "## Next Safe Action",
            str(result["next_safe_action"]),
            "",
            "Safe-to-clean items require a later explicit APPLY cleanup packet.",
            "Review-required items require owner review before any deletion.",
            "Protected do not touch items must remain unchanged.",
            "",
        ]
    )
    return "\n".join(lines)


def _is_truthy(value: bool | object) -> bool:
    return bool(value)


def _repo_root_from_report_root(report_root: Path) -> Path:
    if (
        report_root.name == REQUIRED_ROOT_FILE_PATH.name
        and report_root.parent.name == REQUIRED_ROOT_FILE_PATH.parent.name
    ):
        return report_root.parent.parent
    return Path.cwd()


def _run_git_lines(repo_root: Path, args: list[str]) -> tuple[list[str], list[str]]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.splitlines(), completed.stderr.splitlines()


def _git_status_lines(repo_root: Path) -> dict[str, Any]:
    status_lines, error_lines = _run_git_lines(repo_root, ["status", "--short", "--branch"])
    branch = "UNKNOWN"
    remote = "UNKNOWN"
    if status_lines:
        first = status_lines[0].strip()
        if first.startswith("## "):
            status_body = first[3:]
            parts = status_body.split("...")
            branch = parts[0] if parts else status_body
            if len(parts) > 1:
                remote = parts[1].split(" [")[0]
    warnings = [line for line in error_lines if "permission denied" in line.lower()]
    return {
        "lines": status_lines,
        "dirty_lines": [line for line in status_lines if line and not line.startswith("##")],
        "branch": branch,
        "remote": remote,
        "gitignore_warning_text": "; ".join(warnings) if warnings else "",
        "gitignore_permission_warning": bool(warnings),
    }


def _run_git_counts(repo_root: Path) -> tuple[int, list[str]]:
    non_ignored_output, nonignored_warnings = _run_git_lines(
        repo_root,
        ["ls-files", "--others", "--exclude-standard"],
    )
    _ = nonignored_warnings
    ignored_output, ignored_warnings = _run_git_lines(
        repo_root,
        ["ls-files", "-i", "-o", "--exclude-standard"],
    )
    _ = ignored_warnings
    ignored = [line.strip() for line in ignored_output if line.strip()]
    return len([line.strip() for line in non_ignored_output if line.strip()]), ignored


def _find_tracked_log_candidates(repo_root: Path) -> list[str]:
    tracked, _ = _run_git_lines(repo_root, ["ls-files", "*.log"])
    return [line.strip() for line in tracked if line.strip()]


def _build_safe_to_clean_later(ignored_items: Iterable[str]) -> list[dict[str, Any]]:
    ignored = list(ignored_items)
    categories = [
        ("apps/dashboard/node_modules/", _is_dashboard_node_modules),
        ("Python __pycache__ folders", _is_pycache),
        (".pytest_cache/", _is_pytest_cache),
        ("apps/dashboard/dist/", _is_dashboard_dist),
        ("build/dist outputs", _is_build_dist),
    ]
    results: list[dict[str, Any]] = []
    for category, matcher in categories:
        paths = [path for path in ignored if matcher(path)]
        if paths:
            sample = paths[:3]
            results.append(
                {
                    "category": category,
                    "count": len(paths),
                    "samples": sample,
                    "next_step": "requires explicit cleanup APPLY packet",
                },
            )
    return results


def _build_review_required_before_clean(ignored_items: Iterable[str], repo_root: Path) -> list[dict[str, Any]]:
    ignored = list(ignored_items)
    categories = [
        ("ignored Reports/", lambda value: value.startswith("Reports/")),
        (".local_backlog/", lambda value: value.startswith(".local_backlog/")),
        (".local_hold/", lambda value: value.startswith(".local_hold/")),
    ]
    evidentiary = [
        path
        for path in ignored
        if _contains_any(path.lower(), ("evidence", "audit", "report", "handoff", "handover", "owner"))
    ]
    results: list[dict[str, Any]] = []
    for category, matcher in categories:
        paths = [path for path in ignored if matcher(path)]
        if paths or category == ".local_backlog/":
            results.append(
                {
                    "category": category,
                    "count": len(paths),
                    "samples": paths[:3],
                    "next_step": (
                        "owner review required before delete"
                        if paths
                        else "no current items; preserve review gate for future local backlog cleanup"
                    ),
                },
            )
    if evidentiary:
        results.append(
            {
                "category": "ignored evidence/audit/report/owner handoff material",
                "count": len(evidentiary),
                "samples": evidentiary[:3],
                "next_step": "owner review required before delete",
            }
        )
    review_root_runtime = [
        str(path)
        for name in ROOT_RUNTIME_JSON_FILES
        if (path := (repo_root / name)).exists()
    ]
    if review_root_runtime:
        results.append(
            {
                "category": "root runtime JSON files",
                "count": len(review_root_runtime),
                "samples": sorted(review_root_runtime),
                "next_step": "classify before any deletion in a separate cleanup packet",
            }
        )
    archived_logs = [path for path in _find_tracked_log_candidates(repo_root) if path.startswith("archive/")]
    if archived_logs:
        results.append(
            {
                "category": "archived .log files",
                "count": len(archived_logs),
                "samples": archived_logs,
                "next_step": "owner review required before delete",
            },
        )
    return results


def _build_protected_items() -> list[str]:
    items = {
        "Forex 110 proof artifacts:",
        "AIOS_FOREX_110_CLOSURE artifacts in Reports/forex_delivery",
    }
    items.update(FOREX_110_PROTECTED_FILES)
    items.update(PROTECTED_PATH_PREFIXES)
    items.update(FOREX_110_PROOF_ARTIFACT_PREFIXES)
    return sorted(items)


def _next_safe_action(cleanup_plan_status: str) -> str:
    if cleanup_plan_status != "PLAN_ONLY":
        return (
            "Resolve preflight mismatch first (branch, tracked changes, or non-ignored untracked files), "
            "then rerun this packet from the same repo root."
        )
    return (
        "No deletion occurred. For safe files, create a dedicated cleanup APPLY packet. "
        "For review-required files, owner review and explicit evidence-based authorization are required before any deletion."
    )


def _attack_to_finish(
    *,
    cleanup_plan_status: str,
    branch: str,
    repo_clean: bool,
    non_ignored_nontracked: int,
) -> dict[str, str]:
    if cleanup_plan_status == "PLAN_ONLY":
        return {
            "blocker_id": "NO_BLOCKER",
            "blocker_status": "READY_FOR_PLAN_REVIEW",
            "exact_blocker": "NONE",
            "canonical_owner_file": "Reports/forex_delivery/AIOS_FOREX_110_POST_CLOSURE_LOCAL_RESIDUE_CLEANUP_PLAN_V1_REPORT.md",
            "test_file": "tests/forex_engine/test_forex_110_post_closure_local_residue_cleanup_plan_v1.py",
            "runner_script": "scripts/forex_delivery/run_forex_110_post_closure_local_residue_cleanup_plan_v1.py",
            "missing_evidence_field": "NONE",
            "unlock_status_required": "PLAN_REVIEW_ONLY",
            "next_packet_name": "PKT-FOREX-110-POST-CLOSURE-LOCAL-RESIDUE-CLEANUP-APPLY-V1",
            "owner_action_required": "run an explicit cleanup APPLY packet for any file deletions",
            "stop_condition": "NONE",
            "no_bloat_guard": "Do not reuse this plan packet for cleanup operations.",
        }
    return {
        "blocker_id": "PRECHECK_BLOCKER",
        "blocker_status": "BLOCKED",
        "exact_blocker": f"branch={branch}; repo_clean={repo_clean}; non_ignored_untracked={non_ignored_nontracked}",
        "canonical_owner_file": "Reports/forex_delivery/AIOS_FOREX_110_FINAL_DASHBOARD_CLOSURE_V1.md",
        "test_file": "tests/forex_engine/test_forex_110_post_closure_local_residue_cleanup_plan_v1.py",
        "runner_script": "scripts/forex_delivery/run_forex_110_post_closure_local_residue_cleanup_plan_v1.py",
        "missing_evidence_field": "precheck_status",
        "unlock_status_required": "PLAN_REVIEW_ONLY",
        "next_packet_name": "PKT-FOREX-110-POST-CLOSURE-LOCAL-RESIDUE-CLEANUP-PLAN-V1",
        "owner_action_required": "rerun plan packet after preflight pass",
        "stop_condition": "precheck_failed",
        "no_bloat_guard": "Do not cleanup until preflight is compliant.",
    }


def _is_repo_clean(dirty_lines: list[str]) -> bool:
    return len(dirty_lines) == 0


def _contains_any(value: str, markers: Iterable[str]) -> bool:
    return any(marker in value for marker in markers)


def _is_dashboard_node_modules(path: str) -> bool:
    return path.startswith("apps/dashboard/node_modules/")


def _is_pycache(path: str) -> bool:
    return "__pycache__/" in path or path.endswith(".pyc")


def _is_pytest_cache(path: str) -> bool:
    return path.startswith(".pytest_cache/")


def _is_dashboard_dist(path: str) -> bool:
    return path.startswith("apps/dashboard/dist/")


def _is_build_dist(path: str) -> bool:
    return path.startswith("build/") and "/dist/" in path


def _format_category_lines(items: list[dict[str, Any]], heading: str) -> list[str]:
    lines = [f"## {heading}"]
    if not items:
        lines.extend(["- none", ""])
        return lines
    for item in items:
        lines.append(
            f"- {item['category']}: count={item['count']} "
            f"samples={item['samples']}"
        )
        lines.append(f"  - next: {item['next_step']}")
    lines.append("")
    return lines


__all__ = [
    "ENGINE_VERSION",
    "PACKET_ID",
    "ROOT_RUNTIME_JSON_FILES",
    "build_report_markdown",
    "run_forex_110_post_closure_local_residue_cleanup_plan_v1",
]
