"""Deterministic repository-local preview of the canonical AIOS orchestration spine."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.orchestration.aios_packet_queue_planner import build_packet_queue_planner
from automation.orchestration.aios_work_countdown_v1 import load_canonical_work_packet_inventory

SCHEMA = "AIOS_CANONICAL_ORCHESTRATION_SPINE.v1"
MODE = "READ_ONLY_ORCHESTRATION_PREVIEW"
REQUIRED_COMPONENTS = (
    "automation/orchestration/aios_autonomy_decision_governor.py",
    "automation/orchestration/aios_packet_queue_planner.py",
    "automation/orchestration/aios_candidate_packet_evidence_adapter.py",
    "automation/orchestration/aios_work_countdown_v1.py",
    "automation/orchestration/relay/aios_codex_prompt_consumer_v1.py",
    "automation/orchestration/relay/aios_self_consuming_codex_cycle_v1.py",
)
ROLE_SOURCES = {
    "REPOSITORY_STATE": ["Reports/repo_state/AIOS_REPO_STATE_LATEST.json"],
    "CONTEXT_AND_MEMORY": ["docs/governance/AIOS_FAILURE_MEMORY_V1.md"],
    "PACKET_AND_DEPENDENCY": ["automation/orchestration/aios_packet_queue_planner.py"],
    "EVIDENCE": ["automation/orchestration/aios_candidate_packet_evidence_adapter.py"],
    "PROFIT_READINESS": ["Reports/forex_delivery/AIOS_FOREX_LIVE_READINESS_FORECAST_V1_STATE.json"],
    "PR_LIFECYCLE": ["docs/workflows/AI_OS_PR_LANE_RUNNER.md"],
    "RELAY": ["automation/orchestration/relay/aios_codex_prompt_consumer_v1.py", "automation/orchestration/relay/aios_self_consuming_codex_cycle_v1.py"],
    "AUTONOMY": ["automation/orchestration/aios_autonomy_decision_governor.py"],
    "ECONOMIC_COUNTDOWN": ["automation/orchestration/aios_work_countdown_v1.py", "Reports/orchestration/AIOS_WORK_COUNTDOWN_V1_STATE.json"],
}
PROTECTED = {key: False for key in (
    "packet_execution", "relay_invocation", "worker_dispatch", "queue_mutation",
    "approval_mutation", "network_access", "git_write", "github_access",
    "broker_access", "credential_access", "order_placement", "money_movement",
    "scheduler_start", "daemon_start", "webhook_start",
)}


def stable_json(value: Any, pretty: bool = False) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":")) + "\n"


def discover_canonical_components(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    items = [{"source_path": path, "exists": (root / path).is_file()} for path in REQUIRED_COMPONENTS]
    missing = [item["source_path"] for item in items if not item["exists"]]
    return {"status": "CANONICAL_READY" if not missing else "BLOCKED_CANONICAL_COMPONENT_MISSING", "components": items, "missing": missing}


def _owner(record: dict[str, Any]) -> str:
    text = " ".join(str(record.get(k, "")) for k in ("packet_id", "title", "source_path")).lower()
    if "forex" in text or "dollar" in text or "trade" in text:
        return "PROFIT_READINESS"
    if "relay" in text or "codex" in text:
        return "RELAY"
    if "approval" in text or "pr" in text:
        return "PR_LIFECYCLE"
    return "PACKET_AND_DEPENDENCY"


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def build_task_catalog(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    ids: dict[str, str] = {}
    titles: dict[str, str] = {}
    for source in sorted(records, key=lambda x: str(x.get("source_path", ""))):
        packet_id = str(source.get("packet_id") or "").strip()
        title = str(source.get("title") or packet_id).strip()
        status = str(source.get("folder_state") or source.get("status") or "").upper()
        classification = {"ACTIVE": "ACTIVE", "BLOCKED": "BLOCKED", "COMPLETE": "COMPLETE"}.get(status, "UNCLASSIFIED")
        aliases: list[str] = []
        canonical = packet_id
        if packet_id and packet_id.lower() in ids:
            classification, canonical = "ALIAS", ids[packet_id.lower()]
            aliases.append(packet_id)
        elif _key(title) and _key(title) in titles:
            classification, canonical = "DUPLICATE", titles[_key(title)]
        else:
            if packet_id:
                ids[packet_id.lower()] = packet_id
            if _key(title):
                titles[_key(title)] = packet_id
        completion = [source.get("source_path")] if classification == "COMPLETE" else []
        result.append({
            "task_id": packet_id, "packet_id": packet_id, "canonical_task_id": canonical,
            "title": title, "aliases": aliases, "source_path": source.get("source_path"),
            "classification": classification, "controller_owner": _owner(source),
            "dependencies": list(source.get("dependencies") or []), "priority": source.get("priority", "normal"),
            "risk_level": source.get("risk_level", "low"), "protected_action_requirements": list(source.get("required_approvals") or []),
            "repository_state": deepcopy(source.get("repository_state")),
            "required_files": list(source.get("required_files") or []),
            "blocked_files": list(source.get("blocked_files") or []),
            "conflicts": list(source.get("conflicts") or []),
            "safety_flags": list(source.get("safety_flags") or []),
            "completion_evidence": completion, "validation_evidence": list(source.get("validators") or []),
            "economic_milestone_contribution": "REPOSITORY_LOCAL_WORK",
        })
    return result


def build_controller_registry(repo_root: str | Path, catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    root = Path(repo_root).resolve()
    registry = []
    for role, paths in ROLE_SOURCES.items():
        missing = [path for path in paths if not (root / path).exists()]
        owned = [task["task_id"] for task in catalog if task["controller_owner"] == role]
        registry.append({"controller_id": role, "purpose": role.replace("_", " ").title(), "canonical_source_paths": paths,
                         "status": "CANONICAL_READY" if not missing else "CANONICAL_PARTIAL", "dependencies": [],
                         "owned_task_ids": owned, "duplicate_candidates": [], "blockers": missing,
                         "safe_next_action": "Use repository-local evidence only."})
    return registry


def _dep_id(dep: Any) -> str:
    return str(dep.get("packet_id") or dep.get("id") or "") if isinstance(dep, dict) else str(dep)


def build_dependency_graph(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {task["task_id"]: task for task in catalog if task["task_id"]}
    edges, missing = [], []
    graph: dict[str, list[str]] = defaultdict(list)
    for task in catalog:
        for raw in task["dependencies"]:
            dep = _dep_id(raw)
            edges.append({"from": dep, "to": task["task_id"]})
            graph[task["task_id"]].append(dep)
            if dep not in by_id:
                missing.append({"task_id": task["task_id"], "dependency": dep})
    visiting: set[str] = set(); visited: set[str] = set(); cyclic: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting: cyclic.update(visiting); return
        if node in visited: return
        visiting.add(node)
        for dep in graph[node]:
            if dep in by_id: visit(dep)
        visiting.remove(node); visited.add(node)
    for node in sorted(by_id): visit(node)
    completed = sorted(t["task_id"] for t in catalog if t["classification"] == "COMPLETE")
    blocked = {t["task_id"] for t in catalog if t["classification"] in {"BLOCKED", "ALIAS", "DUPLICATE", "SUPERSEDED", "UNCLASSIFIED"}}
    blocked.update(item["task_id"] for item in missing); blocked.update(cyclic)
    ready = sorted(t["task_id"] for t in catalog if t["classification"] == "ACTIVE" and t["task_id"] not in blocked and all(dep in completed for dep in graph[t["task_id"]]) and not t["protected_action_requirements"])
    return {"nodes": sorted(by_id), "edges": edges, "satisfied_dependencies": [e for e in edges if e["from"] in completed],
            "missing_dependencies": missing, "cyclic_dependencies": sorted(cyclic), "blocked_nodes": sorted(blocked),
            "ready_nodes": ready, "completed_nodes": completed, "critical_path": ready[:1], "next_executable_task": ready[0] if ready else None}


def build_queue_plan(catalog: list[dict[str, Any]], graph: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    for task in catalog:
        if task["task_id"] in graph["ready_nodes"]:
            candidates.append({
                "packet_id": task["packet_id"], "title": task["title"],
                "status": "ready", "priority": task["priority"], "risk_level": task["risk_level"],
                "required_files": list(task.get("required_files") or []),
                "blocked_files": list(task.get("blocked_files") or []),
                "validators": list(task.get("validation_evidence") or []),
                "repository_state": deepcopy(task.get("repository_state")),
                "conflicts": list(task.get("conflicts") or []),
                "safety_flags": list(task.get("safety_flags") or []),
                "dependencies": [], "required_approvals": [],
            })
    planner = build_packet_queue_planner({"candidates": candidates})
    selected = planner.get("selected_packet")
    packet_ready = planner["codex_ready_packet_preview"]["packet_ready"] is True
    blocked = set(graph["blocked_nodes"]) | {item["packet_id"] for item in planner["blocked_packets"]}
    ready = [item["packet_id"] for item in candidates if item["packet_id"] not in blocked
             and build_packet_queue_planner([item])["codex_ready_packet_preview"]["packet_ready"] is True]
    # The selected candidate's strict preview must pass before any ready work
    # is advertised. Dependency eligibility alone cannot qualify execution.
    if not packet_ready:
        ready = []
    blocked.update(set(graph["ready_nodes"]) - set(ready))
    return {"selected_task": selected, "packet_ready": packet_ready,
            "ready_queue": ready, "blocked_queue": sorted(blocked),
            "deferred_queue": [t["task_id"] for t in catalog if t["classification"] in {"SUPERSEDED", "ALIAS", "DUPLICATE"}],
            "completed_queue": graph["completed_nodes"], "external_wait_queue": [t["task_id"] for t in catalog if t["classification"] == "EXTERNAL_PENDING"],
            "owner_approval_queue": [t["task_id"] for t in catalog if t["protected_action_requirements"]],
            "queue_reasoning": planner.get("next_safe_action") if packet_ready else planner["codex_ready_packet_preview"]["reason_code"],
            "queue_mutation_performed": False, "worker_dispatch_performed": False}


def _load_json(path: Path) -> dict[str, Any]:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return {}


def build_orchestration_spine(repo_root: str | Path, as_of_utc: str | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve(); components = discover_canonical_components(root)
    if components["missing"]: raise FileNotFoundError("BLOCKED_CANONICAL_COMPONENT_MISSING: " + ", ".join(components["missing"]))
    inventory = load_canonical_work_packet_inventory(root); catalog = build_task_catalog(inventory["records"])
    registry = build_controller_registry(root, catalog); graph = build_dependency_graph(catalog); queue = build_queue_plan(catalog, graph)
    unclassified = [t for t in catalog if t["classification"] == "UNCLASSIFIED"]
    ownership = [t["task_id"] for t in catalog if not t["controller_owner"]]
    classified = len(catalog) - len(unclassified); coverage_percent = round(classified * 100 / len(catalog), 2) if catalog else 100.0
    coverage = {"discovered_item_count": len(catalog), "classified_item_count": classified, "unclassified_item_count": len(unclassified),
                "duplicate_item_count": sum(t["classification"] in {"ALIAS", "DUPLICATE"} for t in catalog),
                "superseded_item_count": sum(t["classification"] == "SUPERSEDED" for t in catalog),
                "controller_ownership_conflicts": ownership, "classification_coverage_percent": coverage_percent,
                "unclassified_sources": [{"source_path": t["source_path"], "reason": "unrecognized_status"} for t in unclassified]}
    forecast = _load_json(root / "Reports/forex_delivery/AIOS_FOREX_LIVE_READINESS_FORECAST_V1_STATE.json")
    hours = forecast.get("verified_engineering_hours_remaining")
    percent = forecast.get("verified_completion_percentage")
    highest = forecast.get("current_highest_blocker") or forecast.get("highest_blocker") or "NOT_VERIFIED"
    selected = queue["selected_task"]
    next_task = selected["packet_id"] if selected and queue["packet_ready"] else None
    graph.update(ready_nodes=queue["ready_queue"], blocked_nodes=queue["blocked_queue"],
                 next_executable_task=next_task, critical_path=[next_task] if next_task else [])
    economic = {"primary_operator_milestone": "FIRST_REALIZED_NET_POSITIVE_DOLLAR_SUCCESSFULLY_TRANSFERRED",
                "repository_live_trade_milestone": "FIRST_GOVERNED_LIVE_FOREX_MICRO_TRADE",
                "first_withdrawable_dollar_status": "NOT_VERIFIED", "live_trade_readiness_status": forecast.get("status", "NOT_VERIFIED"),
                "verified_engineering_hours_remaining": hours, "engineering_hours_status": "VERIFIED" if hours is not None else "NOT_VERIFIED",
                "verified_completion_percentage": percent, "completion_percentage_status": "VERIFIED" if percent is not None else "NOT_VERIFIED",
                "current_highest_blocker": highest, "next_verified_task": next_task}
    blockers = (["BLOCKED_UNCLASSIFIED_WORK"] if unclassified else []) + (["CONTROLLER_OWNERSHIP_CONFLICT"] if ownership else []) + (["DEPENDENCY_CYCLE"] if graph["cyclic_dependencies"] else [])
    if next_task is None and any(task["classification"] == "ACTIVE" for task in catalog):
        blockers.append("NO_VERIFIED_READY_TASK")
    return {"schema": SCHEMA, "mode": MODE, "generated_at_utc": as_of_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "status": "BLOCKED_UNCLASSIFIED_WORK" if unclassified else ("BLOCKED" if blockers else "READY"), "controller_registry": registry,
            "task_catalog": catalog, "dependency_graph": graph, "queue_plan": queue, "economic_anchor": economic, "coverage": coverage,
            "blockers": blockers, "next_verified_task": next_task, "owner_action_required": bool(queue["owner_approval_queue"]),
            "permissions": dict(PROTECTED), "protected_actions": dict(PROTECTED),
            "evidence_limitations": ["Repository-local evidence only", "No Codex or ChatGPT UI task metadata", "Classification coverage is not project completion"]}


def render_orchestration_report(state: dict[str, Any]) -> str:
    c, e, q, g = state["coverage"], state["economic_anchor"], state["queue_plan"], state["dependency_graph"]
    rows = "\n".join(f"- **{r['controller_id']}** — {r['status']}" for r in state["controller_registry"])
    tasks = "\n".join(f"- `{t['task_id']}` — {t['classification']} — {t['controller_owner']}" for t in state["task_catalog"]) or "- None discovered."
    return f"""# 🧭 AI_OS CANONICAL ORCHESTRATION SPINE

## 🎯 OWNER VIEW
- 📊 Classification coverage: {c['classification_coverage_percent']:.2f}% (discovered repository-local work only)
- 📚 Discovered tasks: {c['discovered_item_count']}
- 🧹 Duplicates and aliases: {c['duplicate_item_count']}
- 🧱 Unclassified work: {c['unclassified_item_count']}
- 📋 Next safe task: {state['next_verified_task'] or 'NONE_VERIFIED'}
- 💵 First-dollar status: {e['first_withdrawable_dollar_status']}
- 📉 Verified engineering hours remaining: {e['verified_engineering_hours_remaining'] if e['engineering_hours_status'] == 'VERIFIED' else 'NOT_VERIFIED'}
- ⛔ Highest blocker: {e['current_highest_blocker']}
- 🔐 Owner action required: {str(state['owner_action_required']).lower()}
- 🛑 Worker dispatch: false

## 🧱 CONTROLLER REGISTRY
{rows}

## 📚 TASK CATALOG
{tasks}

## 🔗 DEPENDENCY GRAPH
- Ready: {len(g['ready_nodes'])}; blocked: {len(g['blocked_nodes'])}; cycles: {len(g['cyclic_dependencies'])}.

## 🧹 DUPLICATE AND ALIAS CONSOLIDATION
- Duplicate artifacts are reported only and remain unchanged.

## 📋 SAFE QUEUE PREVIEW
- Selected: {state['next_verified_task'] or 'NONE_VERIFIED'}; queue mutation: false; worker dispatch: false.

## 💵 FIRST-DOLLAR ANCHOR
- First transferred net-positive dollar: {e['first_withdrawable_dollar_status']}.
- First governed live micro-trade is a separate milestone and does not prove profit or transfer.

## 📉 VERIFIED REMAINING WORK
- Engineering hours: {e['verified_engineering_hours_remaining'] if e['engineering_hours_status'] == 'VERIFIED' else 'NOT_VERIFIED'}.
- Classification coverage is not repository, Forex, live-readiness, profitability, or first-dollar completion.

## ⛔ CURRENT BLOCKERS
- {e['current_highest_blocker']}

## ▶️ NEXT VERIFIED TASK
- {state['next_verified_task'] or 'NONE_VERIFIED'}

## 🔐 OWNER APPROVAL BOUNDARY
- Protected actions require separate Human Owner approval.

## 🧪 VALIDATION
- Status: {state['status']}; classified: {c['classified_item_count']}/{c['discovered_item_count']}.

## 🛑 PROTECTED ACTION CONFIRMATION
- All protected-action values are false. Relay was not invoked; network and Git were not mutated.
"""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(); p.add_argument("--repo-root", default="."); p.add_argument("--as-of-utc")
    p.add_argument("--state-output"); p.add_argument("--report-output"); p.add_argument("--pretty", action="store_true"); return p


def main() -> int:
    args = _parser().parse_args(); state = build_orchestration_spine(args.repo_root, args.as_of_utc)
    output = stable_json(state, args.pretty); print(output, end="")
    if args.state_output: Path(args.state_output).write_text(output, encoding="utf-8")
    if args.report_output: Path(args.report_output).write_text(render_orchestration_report(state), encoding="utf-8")
    return 0


if __name__ == "__main__": raise SystemExit(main())
