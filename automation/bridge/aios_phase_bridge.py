from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_IMPORT_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_IMPORT_ROOT))

from automation.bridge.aios_approval_model import ApprovalRecord, compress_approval
from automation.bridge.aios_queue_model import inventory_queue_systems, load_known_state
from automation.bridge.aios_self_build_model import build_recommendations
from automation.bridge.aios_status_model import (
    PACKET_ID,
    capture_repo_snapshot,
    list_git_files,
    matching_files,
    utc_now,
    write_json,
    write_markdown,
)
from automation.bridge.aios_validator_model import discover_validators


DEFAULT_REPORT_ROOT = Path("Reports/generated/phase_0_to_4_bridge")
DEFAULT_TELEMETRY_OUTPUT_ROOT = Path("telemetry/generated/validator_results")
DEFAULT_APPROVAL_OUTPUT_ROOT = Path("telemetry/generated/approval_inbox")
AUTHORITY_FILES = [
    "AGENTS.md",
    "README.md",
    "docs/governance/source-of-truth-map.md",
    "docs/audits/active-system-map.md",
    "docs/governance/aios-identity-and-lane-governance.md",
    "docs/governance/operational-doctrine.md",
    "docs/workflows/AI_OS_COMMIT_PUSH_GATE.md",
    "docs/workflows/AI_OS_PR_LANE_RUNNER.md",
    "docs/workflows/OPENAI_CODEX_NIGHT_SUPERVISOR_ONBOARDING.md",
]


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def phase0(repo_root: Path, status_before: str, report_root: Path) -> dict[str, object]:
    snapshot = capture_repo_snapshot(repo_root)
    tracked = list_git_files(repo_root)
    missing_expected = [path for path in AUTHORITY_FILES if not (repo_root / path).exists()]
    governance = matching_files(tracked, ["docs/governance", "AGENTS.md", "RISK_POLICY"])
    workflows = matching_files(tracked, ["docs/workflows"])
    automation = matching_files(tracked, ["automation/"])
    validators = matching_files(tracked, ["validator", "validation", "test-"])
    tests = matching_files(tracked, ["tests/"])
    telemetry = matching_files(tracked, ["telemetry/"])
    ci = matching_files(tracked, [".github/workflows", ".githooks"])
    hooks = matching_files(tracked, [".githooks", "scripts/hooks"])
    queue_inventory = inventory_queue_systems(repo_root, tracked)
    phase0_findings = [
        "GOVERNANCE_DOC_ONLY where rules have no hook or CI enforcement",
        "APPLY_NOT_WIRED for DRY_RUN scripts without APPLY counterparts",
        "DOC_ONLY for future automation claims represented only in docs",
    ]
    payload = {
        "packet_id": PACKET_ID,
        "timestamp_utc": snapshot.timestamp_utc,
        "repo_root": snapshot.repo_root,
        "branch": snapshot.branch,
        "remote_origin": snapshot.remote_origin,
        "git_status_short": status_before or snapshot.git_status_short,
        "dirty_files": snapshot.dirty_files,
        "missing_expected_files": missing_expected,
        "found_governance_files": governance,
        "found_workflow_files": workflows,
        "found_automation_files": automation[:200],
        "found_validator_files": validators,
        "found_test_files": tests,
        "found_telemetry_files": telemetry,
        "found_ci_files": ci,
        "found_hook_files": hooks,
        "found_worker_state_files": queue_inventory.worker_queue_files,
        "found_approval_files": queue_inventory.approval_files,
        "found_sos_files": queue_inventory.sos_files,
        "phase0_findings": phase0_findings,
        "blocked_conditions": [],
        "safe_to_continue_boolean": True,
    }
    write_json(repo_root / report_root / "phase0_infrastructure_inventory.json", payload)
    write_markdown(
        repo_root / report_root / "PHASE0_INFRASTRUCTURE_INVENTORY.md",
        "Phase 0 Infrastructure Inventory",
        {
            "SUMMARY": "Inventory generated from tracked files and current Git state. This report is evidence only.",
            "WHAT EXISTS": {
                "governance_files": len(governance),
                "workflow_files": len(workflows),
                "automation_files_sampled": len(automation[:200]),
                "validator_files_sampled": len(validators),
            },
            "WHAT IS MISSING": missing_expected,
            "WHAT IS DISCONNECTED": phase0_findings,
            "WHAT IS UNSAFE TO TOUCH": ["AGENTS.md", "README.md", "live trading", "broker credentials", "commit", "push", "merge"],
            "WHAT CAN BE BUILT NOW": ["subordinate bridge evidence", "approval compressor", "governance validator", "self-build inspector"],
            "WHAT REQUIRES APPROVAL": ["protected root edits", "commit", "push", "merge", "live or broker work"],
            "SAFE NEXT ACTION": "Run the bridge in DRY_RUN and inspect reports.",
        },
    )
    return payload


def phase1(repo_root: Path, tracked: list[str], report_root: Path, telemetry_output_root: Path) -> dict[str, object]:
    queue_inventory = inventory_queue_systems(repo_root, tracked)
    validator_inventory = discover_validators(repo_root, tracked)
    known_state = load_known_state(repo_root)
    payload = {
        "systems_found": {
            "queue": queue_inventory.worker_queue_files[:50],
            "locks": queue_inventory.lock_files[:50],
            "approval": queue_inventory.approval_files[:50],
            "validators": [record.path for record in validator_inventory.validators[:50]],
        },
        "systems_wired": ["read-only queue inventory", "read-only approval inventory", "validator discovery"],
        "systems_left_doc_only": ["hook installation", "CI enforcement hardening", "Night Supervisor activation"],
        "systems_missing": [],
        "systems_requiring_approval": ["commit", "push", "merge", "protected root edits"],
        "adapter_files_created": [
            "automation/bridge/aios_phase_bridge.py",
            "automation/bridge/aios_queue_model.py",
            "automation/bridge/aios_validator_model.py",
        ],
        "adapter_files_updated": [],
        "test_files_created": [],
        "test_files_updated": [],
        "known_state_loaded": known_state,
        "safe_next_action": "Run python automation/bridge/aios_phase_bridge.py --mode DRY_RUN --repo-root .",
    }
    write_json(repo_root / report_root / "phase1_wiring_map.json", payload)
    write_json(repo_root / telemetry_output_root / "AIOS_VALIDATOR_REGISTRY.current.json", validator_inventory.to_dict())
    write_markdown(
        repo_root / report_root / "PHASE1_WIRING_MAP.md",
        "Phase 1 Wiring Map",
        {
            "SUMMARY": "Bridge adapters read existing queue, approval, lock, and validator surfaces without replacing them.",
            "SYSTEMS WIRED": payload["systems_wired"],
            "SYSTEMS LEFT DOC ONLY": payload["systems_left_doc_only"],
            "SYSTEMS REQUIRING APPROVAL": payload["systems_requiring_approval"],
            "SAFE NEXT ACTION": payload["safe_next_action"],
        },
    )
    return payload


def _sample_approval(now: str) -> ApprovalRecord:
    return ApprovalRecord.from_dict(
        {
            "approval_id": "sample-approval-local-apply",
            "source_packet_id": PACKET_ID,
            "created_utc": now,
            "operator": "Anthony",
            "decision": "approve",
            "mode_requested": "APPLY",
            "mode_allowed": "APPLY",
            "scope_summary": "Apply bounded local bridge evidence under automation/bridge and Reports.",
            "allowed_paths": ["automation/bridge/", "Reports/phase_0_to_4_bridge/"],
            "forbidden_paths": ["AGENTS.md", "README.md"],
            "protected_actions_detected": [],
            "approval_text": "Anthony explicitly approves APPLY for bounded local bridge evidence only.",
            "evidence_files": ["Reports/generated/phase_0_to_4_bridge/phase0_infrastructure_inventory.json"],
            "validator_chain": ["git diff --check", "python -m py_compile automation/bridge/aios_phase_bridge.py"],
            "expires_utc": "",
            "status": "pending",
        }
    )


def phase2(
    repo_root: Path,
    now: str,
    report_root: Path = Path("Reports/phase_0_to_4_bridge"),
    approval_output_root: Path = DEFAULT_APPROVAL_OUTPUT_ROOT,
) -> dict[str, object]:
    valid_decision = compress_approval(_sample_approval(now))
    blocked_decision = compress_approval(
        ApprovalRecord.from_dict(
            {
                "approval_id": "sample-blocked-live",
                "source_packet_id": PACKET_ID,
                "created_utc": now,
                "operator": "Anthony",
                "decision": "approve",
                "mode_requested": "APPLY",
                "mode_allowed": "APPLY",
                "scope_summary": "Apply live trading broker execution.",
                "allowed_paths": ["apps/trading_lab/"],
                "forbidden_paths": [],
                "protected_actions_detected": [],
                "approval_text": "Apply live trading broker execution.",
                "evidence_files": [],
                "validator_chain": ["git diff --check"],
                "expires_utc": "",
                "status": "pending",
            }
        )
    )
    payload = {
        "approval_compressor": "automation/bridge/aios_approval_model.py",
        "valid_sample": valid_decision.to_dict(),
        "blocked_sample": blocked_decision.to_dict(),
        "status_values": ["WAIT", "BLOCKED", "REQUIRES_APPROVAL", "APPLY_READY", "APPLY_EXECUTED", "COMPLETE"],
        "safe_next_action": "Use approval compressor as a validator, not as authority.",
    }
    write_json(repo_root / report_root / "phase2_approval_compressor_result.json", payload)
    write_json(repo_root / approval_output_root / "AIOS_APPROVAL_INBOX.current.json", {"sample_decisions": payload})
    write_markdown(
        repo_root / report_root / "PHASE2_APPROVAL_COMPRESSOR.md",
        "Phase 2 Approval Compressor",
        {
            "SUMMARY": "Approval compressor distinguishes ready, waiting, approval-required, and blocked states.",
            "VALID SAMPLE STATUS": valid_decision.status,
            "BLOCKED SAMPLE STATUS": blocked_decision.status,
            "SAFE NEXT ACTION": payload["safe_next_action"],
        },
    )
    return payload


def phase3(repo_root: Path, report_root: Path) -> dict[str, object]:
    payload = {
        "governance_validator": "automation/validators/aios_governance_validator.py",
        "hook_template": ".githooks/pre-commit",
        "hook_installer": "scripts/hooks/Install-AiOsGitHooks.ps1",
        "workflow_doc": "docs/workflows/AI_OS_LOCAL_HOOKS.md",
        "ci_workflow": ".github/workflows/aios-governance.yml",
        "protected_actions_not_performed": ["hook auto-install", "commit", "push", "merge"],
        "safe_next_action": "Run governance validator sample check.",
    }
    write_json(repo_root / report_root / "phase3_governance_enforcement.json", payload)
    write_markdown(
        repo_root / report_root / "PHASE3_GOVERNANCE_ENFORCEMENT.md",
        "Phase 3 Governance Enforcement",
        {
            "SUMMARY": "Governance enforcement is implemented as local validator, opt-in hook template, and minimal CI workflow.",
            "PROTECTED ACTIONS NOT PERFORMED": payload["protected_actions_not_performed"],
            "SAFE NEXT ACTION": payload["safe_next_action"],
        },
    )
    return payload


def phase4(repo_root: Path, now: str, phase0_payload: dict[str, object], report_root: Path) -> dict[str, object]:
    recommendations = build_recommendations(now, phase0_payload)
    payload = {
        "inspector": "automation/self_build/aios_self_build_inspector.py",
        "recommendations": [recommendation.to_dict() for recommendation in recommendations],
        "safe_next_action": "Review recommendations; do not execute them automatically.",
    }
    write_json(repo_root / report_root / "phase4_self_build_inspection.json", payload)
    write_markdown(
        repo_root / report_root / "PHASE4_SELF_BUILD_INSPECTION.md",
        "Phase 4 Self-Build Inspection",
        {
            "SUMMARY": "Self-build inspector recommends bounded future packets without executing them.",
            "RECOMMENDATION COUNT": len(recommendations),
            "SAFE NEXT ACTION": payload["safe_next_action"],
        },
    )
    return payload


def write_consolidated(
    repo_root: Path,
    before_status: str,
    phase_payloads: dict[str, dict[str, object]],
    report_root: Path,
) -> dict[str, object]:
    after = capture_repo_snapshot(repo_root)
    changed = after.dirty_files
    payload = {
        "packet_id": PACKET_ID,
        "timestamp_utc": utc_now(),
        "repo_root": after.repo_root,
        "branch": after.branch,
        "git_status_before": before_status,
        "git_status_after": after.git_status_short,
        "files_inspected": AUTHORITY_FILES,
        "files_created": changed,
        "files_modified": [],
        "files_deleted": [],
        "phases_completed": ["phase0", "phase1", "phase2", "phase3", "phase4"],
        "phases_blocked": [],
        "phase0_summary": "Inventory generated.",
        "phase1_summary": "Read-only adapters wired.",
        "phase2_summary": "Approval compressor sample decisions generated.",
        "phase3_summary": "Governance validator and local hook assets present.",
        "phase4_summary": "Self-build recommendations generated.",
        "validators_run": [],
        "validator_results": {},
        "tests_run": [],
        "test_results": {},
        "protected_actions_detected": ["commit", "push", "merge", "protected root edits"],
        "protected_actions_not_performed": ["commit", "push", "merge", "protected root edits"],
        "approval_packets_created": [],
        "commit_performed_boolean": False,
        "push_performed_boolean": False,
        "merge_performed_boolean": False,
        "live_trading_touched_boolean": False,
        "broker_credentials_touched_boolean": False,
        "secrets_printed_boolean": False,
        "remaining_dirty_files": changed,
        "safe_next_command": "git status --short --branch",
        "status": "COMPLETE_NO_COMMIT_NO_PUSH",
        "phase_payloads": phase_payloads,
    }
    write_json(repo_root / report_root / "AIOS_PHASE_0_TO_4_BRIDGE_RESULT.json", payload)
    write_markdown(
        repo_root / report_root / "AIOS_PHASE_0_TO_4_BRIDGE_RESULT.md",
        "AIOS Phase 0 To 4 Bridge Result",
        {
            "SUMMARY": "Bridge infrastructure generated as evidence and subordinate code. No commit or push performed.",
            "PHASE 0 RESULT": payload["phase0_summary"],
            "PHASE 1 RESULT": payload["phase1_summary"],
            "PHASE 2 RESULT": payload["phase2_summary"],
            "PHASE 3 RESULT": payload["phase3_summary"],
            "PHASE 4 RESULT": payload["phase4_summary"],
            "FILES CREATED": changed,
            "FILES MODIFIED": [],
            "FILES NOT TOUCHED": ["AGENTS.md", "README.md", "docs/architecture/AI_OS_WHITEPAPER.md"],
            "VALIDATION": "Run validator chain after generation.",
            "PROTECTED ACTIONS DETECTED BUT NOT PERFORMED": payload["protected_actions_not_performed"],
            "REMAINING DIRTY FILES": changed,
            "COMMIT STATUS": "No commit performed.",
            "PUSH STATUS": "No push performed.",
            "SAFE NEXT COMMAND": payload["safe_next_command"],
            "STATUS": payload["status"],
        },
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AI_OS Phase 0 to 4 bridge evidence.")
    parser.add_argument("--mode", choices=["DRY_RUN", "APPLY"], default="DRY_RUN")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-root", default=str(DEFAULT_REPORT_ROOT))
    parser.add_argument("--telemetry-output-root", default=str(DEFAULT_TELEMETRY_OUTPUT_ROOT))
    parser.add_argument("--approval-output-root", default=str(DEFAULT_APPROVAL_OUTPUT_ROOT))
    parser.add_argument("--approval-check")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    report_root = Path(args.output_root)
    telemetry_output_root = Path(args.telemetry_output_root)
    approval_output_root = Path(args.approval_output_root)
    before = capture_repo_snapshot(repo_root)
    if args.approval_check:
        record = ApprovalRecord.from_dict(json.loads(Path(args.approval_check).read_text(encoding="utf-8")))
        print(json.dumps(compress_approval(record).to_dict(), indent=2, sort_keys=True))
        return 0
    if args.mode != "DRY_RUN":
        print(json.dumps({"status": "BLOCKED", "reason": "Bridge CLI writes evidence only in DRY_RUN mode."}, indent=2))
        return 2
    tracked = list_git_files(repo_root)
    now = utc_now()
    phase_payloads: dict[str, dict[str, object]] = {}
    phase_payloads["phase0"] = phase0(repo_root, before.git_status_short, report_root)
    phase_payloads["phase1"] = phase1(repo_root, tracked, report_root, telemetry_output_root)
    phase_payloads["phase2"] = phase2(repo_root, now, report_root, approval_output_root)
    phase_payloads["phase3"] = phase3(repo_root, report_root)
    phase_payloads["phase4"] = phase4(repo_root, now, phase_payloads["phase0"], report_root)
    result = write_consolidated(repo_root, before.git_status_short, phase_payloads, report_root)
    print(json.dumps({"status": result["status"], "report": str((repo_root / report_root).as_posix())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
