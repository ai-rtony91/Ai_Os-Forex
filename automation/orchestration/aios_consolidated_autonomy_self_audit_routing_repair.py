from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "AIOS_CONSOLIDATED_AUTONOMY_SELF_AUDIT_ROUTING_REPAIR.v1"
PACKET_ID = "AIOS-CONSOLIDATED-AUTONOMY-SELF-AUDIT-ROUTING-REPAIR-NEXT-PACKET-V1"
REPORT_DIR = Path("Reports/orchestration")
STATE_NAME = "AIOS_CONSOLIDATED_AUTONOMY_SELF_AUDIT_ROUTING_REPAIR_STATE.json"
REPORT_NAME = "AIOS_CONSOLIDATED_AUTONOMY_SELF_AUDIT_ROUTING_REPAIR_REPORT.md"
NEXT_PACKET_NAME = "AIOS_CONSOLIDATED_AUTONOMY_SELF_AUDIT_ROUTING_REPAIR_NEXT_CODEX_PACKET.md"
CHECKPOINT_NAME = "AIOS_CONSOLIDATED_AUTONOMY_SELF_AUDIT_ROUTING_REPAIR_CHECKPOINT.json"

EXTERNAL_TERMS = (
    "owner", "credential", "credentials", "broker", "oanda", "api", "external",
    "account", "live", "demo", "approval", "evidence", "human", "anthony",
)
SAFETY_BLOCKS = {
    "broker_api_allowed": False,
    "credentials_allowed": False,
    "order_execution_allowed": False,
    "live_trading_allowed": False,
    "network_allowed": False,
    "scheduler_allowed": False,
    "daemon_allowed": False,
    "continuous_execution_allowed": False,
    "execution_authority_granted": False,
}
DEFAULT_VALIDATORS = [
    "python -m pytest -q tests/orchestration",
    "python -m pytest -q tests/forex_delivery",
    "python -m pytest -q tests/forex_engine/test_forex_final_readiness_checker_v1.py",
]


@dataclass(frozen=True)
class Blocker:
    name: str
    source: str
    classification: str
    roi: int
    dependency_rank: int
    reason: str


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _as_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def canonical_sources(repo_root: Path) -> dict[str, str]:
    candidates = {
        "workflow_router_state": "Reports/forex_delivery/AIOS_FOREX_WORKFLOW_AUTONOMY_ROUTER_V1_STATE.json",
        "finish_line_state": "Reports/forex_delivery/AIOS_FOREX_FINISH_LINE_MISSION_CONTROLLER_V1_STATE.json",
        "critical_safety_state": "Reports/forex_delivery/AIOS_FOREX_CRITICAL_SAFETY_EVIDENCE_CLOSURE_V1_STATE.json",
        "readiness_recalculation": "Reports/forex_delivery/readiness_state_recalculation_v1_report.json",
        "workflow_next_packet": "Reports/forex_delivery/AIOS_FOREX_WORKFLOW_AUTONOMY_ROUTER_NEXT_CODEX_PACKET_V1.md",
    }
    return {key: value for key, value in candidates.items() if (repo_root / value).exists()}


def discover_blockers(repo_root: Path) -> list[Blocker]:
    blockers: dict[str, Blocker] = {}
    for label, rel in canonical_sources(repo_root).items():
        path = repo_root / rel
        if path.suffix.lower() == ".json":
            payload = _load_json(path)
            raw: list[str] = []
            for key in ("active_blockers", "blockers", "owner_safety_evidence_missing", "missing", "external_blockers"):
                raw.extend(_as_strings(payload.get(key)))
            active = payload.get("active_blocker")
            raw.extend(_as_strings(active))
        else:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            raw = [term for term in ("kill_switch_state", "daily_stop_state", "max_loss_state", "monitoring_ready") if term in text]
        for name in raw:
            key = name.strip()
            if not key or key in blockers:
                continue
            blockers[key] = classify_blocker(key, label)
    return sorted(blockers.values(), key=lambda item: (-item.roi, item.dependency_rank, item.classification != "repository_fixable", item.name))


def classify_blocker(name: str, source: str) -> Blocker:
    lowered = name.lower()
    external = any(term in lowered for term in EXTERNAL_TERMS) or source in {"workflow_router_state", "critical_safety_state"}
    classification = "external" if external else "repository_fixable"
    if any(term in lowered for term in ("kill", "stop", "loss", "monitor")):
        roi, dependency = 95, 10
    elif "test" in lowered or "validator" in lowered:
        roi, dependency = 80, 20
    else:
        roi, dependency = 60, 50
    reason = "requires owner/broker/external evidence" if classification == "external" else "can be repaired by repository-only code or tests"
    return Blocker(name=name, source=source, classification=classification, roi=roi, dependency_rank=dependency, reason=reason)


def select_repair(blockers: Iterable[Blocker]) -> dict[str, Any]:
    fixable = [item for item in blockers if item.classification == "repository_fixable"]
    if not fixable:
        return {"selected": False, "reason_code": "no_repository_fixable_blocker", "candidate": None}
    item = sorted(fixable, key=lambda b: (-b.roi, b.dependency_rank, b.name))[0]
    return {"selected": True, "reason_code": "repository_fixable_blocker_selected", "candidate": asdict(item)}


def route_tests(selected: dict[str, Any]) -> list[str]:
    tests = [
        "python -m pytest -q tests/orchestration/test_aios_consolidated_autonomy_self_audit_routing_repair.py",
        *DEFAULT_VALIDATORS,
    ]
    if not selected.get("selected"):
        tests.append("python -m json.tool Reports/orchestration/AIOS_CONSOLIDATED_AUTONOMY_SELF_AUDIT_ROUTING_REPAIR_STATE.json")
    return tests


def build_next_packet(repo_root: Path, selected: dict[str, Any], tests: list[str]) -> str:
    candidate = selected.get("candidate") or {}
    repair_name = candidate.get("name", "external_owner_evidence_wait")
    mode = "DRY_RUN" if not selected.get("selected") else "APPLY"
    objective = (
        f"Inspect and repair the repository-fixable blocker `{repair_name}` using repository evidence only."
        if selected.get("selected") else
        "Collect owner-sanitized evidence for external Forex readiness blockers; do not mutate broker, credentials, or order state."
    )
    return "\n".join([
        "CODEX-ONLY PROMPT", "", "AI_OS EXECUTION TOKEN", "AI_OS BOOTSTRAP REQUIRED", "",
        "IDENTITY MARKER: AIOS_CONSOLIDATED_AUTONOMY_NEXT_PACKET", "SUPERVISOR IDENTITY: ChatGPT planning supervisor",
        "PACKET ID: AIOS-CONSOLIDATED-AUTONOMY-ROUTED-NEXT-ACTION-V1", f"MODE: {mode}",
        "ZONE: LOCAL_REPOSITORY", "WORKER IDENTITY: EAST_OCC_NEXT", "LANE: AUTONOMY_SELF_AUDIT_ROUTING_REPAIR",
        f"WORKTREE: {repo_root.as_posix()}", "BRANCH: resolve after preflight", "ALLOWED PATHS:",
        "automation/orchestration/", "automation/forex_engine/", "scripts/forex_delivery/", "tests/orchestration/", "tests/forex_engine/", "Reports/orchestration/", "Reports/forex_delivery/", "",
        "FORBIDDEN PATHS:", "AGENTS.md", "RISK_POLICY.md", "SECURITY.md", ".github/workflows/", ".env", ".env.*", "credentials/", "secrets/", "live order paths", "deployment paths", "startup persistence", "scheduled tasks", "dashboard assets", "unrelated files", "",
        "APPROVAL AUTHORITY: Human Owner Anthony approval required before APPLY, staging, commit, push, merge, broker access, credentials, or execution.",
        "VALIDATOR CHAIN:", *tests, "git diff --check", "git status --short --branch", "",
        "MISSION:", objective, "",
        "PRELIGHT:", "pwd", "git status --short --branch", "git branch --show-current", "git remote -v", "",
        "STOP POINT: Stop after one bounded repository-evidence cycle. No continuous execution.",
        "FINAL REPORT FORMAT: SUMMARY; FILES CHANGED; VALIDATION; NEXT SAFE ACTION; STATUS.", "",
    ])


def run_cycle(repo_root: Path, *, write: bool = False, generated_at_utc: datetime | None = None) -> dict[str, Any]:
    blockers = discover_blockers(repo_root)
    selected = select_repair(blockers)
    tests = route_tests(selected)
    next_packet = build_next_packet(repo_root, selected, tests)
    now = generated_at_utc or datetime.now(timezone.utc)
    state = {
        "schema": SCHEMA,
        "packet_id": PACKET_ID,
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_artifacts": canonical_sources(repo_root),
        "blockers_discovered": [asdict(item) for item in blockers],
        "repository_fixable_blockers": [asdict(item) for item in blockers if item.classification == "repository_fixable"],
        "external_blockers": [asdict(item) for item in blockers if item.classification == "external"],
        "selected_repair": selected,
        "test_routing": tests,
        "checkpoint_status": "ready_to_write" if write else "preview_only",
        "resume_status": "stop_after_one_cycle",
        "next_generated_packet": next_packet,
        "finite_cycle_confirmed": True,
        "live_execution_allowed": False,
        "safety_boundary": SAFETY_BLOCKS,
        "no_execution_authority": True,
    }
    if write:
        out_dir = repo_root / REPORT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        state_path = out_dir / STATE_NAME
        report_path = out_dir / REPORT_NAME
        packet_path = out_dir / NEXT_PACKET_NAME
        checkpoint_path = out_dir / CHECKPOINT_NAME
        state["checkpoint_status"] = "written"
        state["output_paths"] = {"state": str(state_path.relative_to(repo_root)), "report": str(report_path.relative_to(repo_root)), "next_packet": str(packet_path.relative_to(repo_root)), "checkpoint": str(checkpoint_path.relative_to(repo_root))}
        serialized = json.dumps(state, indent=2, sort_keys=True) + "\n"
        state_path.write_text(serialized, encoding="utf-8")
        checkpoint_path.write_text(serialized, encoding="utf-8")
        packet_path.write_text(next_packet, encoding="utf-8")
        report_path.write_text(render_report(state), encoding="utf-8")
    return state


def render_report(state: dict[str, Any]) -> str:
    blockers = state["blockers_discovered"]
    return "\n".join([
        "# AIOS Consolidated Autonomy Self-Audit Routing Repair Report", "",
        f"- packet_id: {state['packet_id']}", f"- finite_cycle_confirmed: {state['finite_cycle_confirmed']}",
        f"- live_execution_allowed: {state['live_execution_allowed']}", f"- blockers_discovered: {len(blockers)}",
        f"- repository_fixable_blockers: {len(state['repository_fixable_blockers'])}", f"- external_blockers: {len(state['external_blockers'])}",
        f"- selected_repair: {state['selected_repair']['reason_code']}", f"- checkpoint_status: {state['checkpoint_status']}",
        f"- resume_status: {state['resume_status']}", "", "## Test Routing", *[f"- {cmd}" for cmd in state["test_routing"]], "", "## Next Packet", "```text", state["next_generated_packet"], "```", ""
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one finite AIOS Forex autonomy self-audit routing cycle.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    print(json.dumps(run_cycle(repo_root, write=args.write), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
