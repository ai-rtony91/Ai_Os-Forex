"""Deterministic, local-only compound work-braid planning for AI_OS.

The controller composes the canonical work-packet inventory and platform facade.
It never dispatches work, mutates a queue, invokes a generated prompt, or grants a
protected authority.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from automation.orchestration.aios_work_countdown_v1 import load_canonical_work_packet_inventory

SCHEMA = "AIOS_COMPOUND_WORK_BRAID.v1"
STATUSES = {
    "CLOSED_VERIFIED", "OPEN_ACTIONABLE", "BLOCKED_INTERNAL", "BLOCKED_EXTERNAL",
    "OWNER_DECISION_REQUIRED", "SUPERSEDED", "DUPLICATE", "INVALID",
    "UNKNOWN_REQUIRES_DISCOVERY",
}
PROTECTED = (
    "git_stage", "git_commit", "git_push", "pr_create", "git_merge",
    "queue_mutation", "worker_dispatch", "broker_access", "credential_access",
    "order_placement", "money_movement", "deployment", "autonomous_approval",
)
PROGRAM_NAMES = (
    "Repository Orchestration Reliability", "Loop Discovery and Closure",
    "Forex Evidence Completion", "Owner Demo Readiness", "Protected Live Review",
    "Broker-Verified Profit Evidence", "First Profitable Withdrawal",
    "Repeatability and Capital Governance", "Humanoid Funding Readiness",
)
CABLE_STAGES = (
    "preflight", "state_discovery", "dependency_verification", "implementation",
    "targeted_validation", "bounded_self_repair", "regression_validation",
    "evidence_generation", "artifact_accounting", "checkpoint_generation",
    "execution_receipt", "continuation_generation", "commit_readiness_report",
    "pr_readiness_report", "owner_handoff",
)


class WorkBraidError(ValueError):
    """Raised when fail-closed graph or resume validation fails."""


def stable_json(value: Any, *, pretty: bool = False) -> str:
    options = {"sort_keys": True, "ensure_ascii": False}
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return json.dumps(value, **options) + "\n"


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return sorted({str(item) for item in value if str(item)})


def _slug(value: str) -> str:
    return "-".join(part for part in "".join(c if c.isalnum() else " " for c in value.upper()).split())


def normalize_strand(source: Mapping[str, Any]) -> dict[str, Any]:
    strand_id = str(source.get("strand_id") or source.get("packet_id") or "").strip()
    observed = str(source.get("observed_status") or source.get("packet_status") or source.get("status") or "").lower()
    if not strand_id:
        normalized = "INVALID"
    elif source.get("superseded_by"):
        normalized = "SUPERSEDED"
    elif source.get("duplicate_group") and source.get("canonical") is False:
        normalized = "DUPLICATE"
    elif source.get("protected_action_required") or source.get("owner_decision_required"):
        normalized = "OWNER_DECISION_REQUIRED"
    elif source.get("external_dependency"):
        normalized = "BLOCKED_EXTERNAL"
    elif observed in {"complete", "completed", "closed", "done", "merged"}:
        # Folder/report status is not closure evidence. Missing validator evidence
        # remains a repository-actionable verification obligation.
        normalized = "CLOSED_VERIFIED" if source.get("closure_evidence") else "OPEN_ACTIONABLE"
    elif observed in {"blocked", "deferred", "hold", "paused"}:
        normalized = "BLOCKED_INTERNAL"
    elif observed in {"active", "open", "pending", "ready", "queued", "proposed", "in_progress"}:
        normalized = "OPEN_ACTIONABLE"
    else:
        normalized = "UNKNOWN_REQUIRES_DISCOVERY"
    required_paths = _strings(source.get("required_paths") or source.get("required_files") or source.get("source_path"))
    return {
        "strand_id": strand_id, "title": str(source.get("title") or strand_id),
        "source_type": str(source.get("source_type") or source.get("source_format") or "repository_evidence"),
        "source_reference": str(source.get("source_reference") or source.get("source_path") or strand_id),
        "component": str(source.get("component") or (required_paths[0] if required_paths else "repository_orchestration")),
        "observed_status": observed or "unknown", "normalized_status": normalized,
        "observed_evidence": _strings(source.get("observed_evidence") or source.get("source_path")),
        "root_cause": str(source.get("root_cause") or source.get("component") or "canonical_work_packet_obligation"),
        "dependencies": _strings(source.get("dependencies")), "reverse_dependencies": _strings(source.get("reverse_dependencies")),
        "duplicate_group": source.get("duplicate_group"), "superseded_by": source.get("superseded_by"),
        "required_paths": required_paths, "forbidden_paths": _strings(source.get("forbidden_paths") or source.get("blocked_files")),
        "validator_chain": _strings(source.get("validator_chain") or source.get("validators")),
        "completion_definition": _strings(source.get("completion_definition") or ["Required implementation and validators have evidence."]),
        "external_dependency": source.get("external_dependency"), "owner_decision_required": bool(source.get("owner_decision_required")),
        "protected_action_required": bool(source.get("protected_action_required") or source.get("required_approvals")),
        "repository_actionable": normalized == "OPEN_ACTIONABLE", "milestone_advanced": str(source.get("milestone_advanced") or "Repository Orchestration Reliability"),
        "risk_class": str(source.get("risk_class") or source.get("risk_level") or "low"), "effort_band": str(source.get("effort_band") or "medium"),
        "reuse_value": int(source.get("reuse_value") or 1), "autonomy_leverage": int(source.get("autonomy_leverage") or 1),
        "critical_path_weight": int(source.get("critical_path_weight") or 1), "economic_milestone_relevance": int(source.get("economic_milestone_relevance") or 0),
        "closure_evidence": _strings(source.get("closure_evidence")), "reason_codes": _strings(source.get("reason_codes") or [normalized.lower()]),
    }


def collapse_duplicates(strands: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_strand(item) for item in strands]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for strand in normalized:
        key = (_slug(strand["title"]), strand["component"])
        groups[key].append(strand)
    result: list[dict[str, Any]] = []
    for items in groups.values():
        items.sort(key=lambda item: item["strand_id"])
        canonical = items[0]
        if len(items) > 1:
            group = "DUP-" + stable_hash([item["strand_id"] for item in items])[:12].upper()
            canonical["duplicate_group"] = group
            canonical["reason_codes"] = sorted(set(canonical["reason_codes"] + ["canonical_duplicate_owner"]))
            for duplicate in items[1:]:
                duplicate["duplicate_group"] = group
                duplicate["normalized_status"] = "DUPLICATE"
                duplicate["repository_actionable"] = False
                duplicate["reason_codes"] = sorted(set(duplicate["reason_codes"] + ["duplicate_collapsed", f"canonical:{canonical['strand_id']}"]))
        result.extend(items)
    return sorted(result, key=lambda item: item["strand_id"])


def dependency_graph(strands: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    items = {strand["strand_id"]: strand for strand in strands}
    missing: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    for strand_id, strand in items.items():
        for dependency in strand["dependencies"]:
            edges.append({"from": dependency, "to": strand_id})
            if dependency not in items:
                missing.append({"strand_id": strand_id, "dependency": dependency})
    if missing:
        raise WorkBraidError("MISSING_DEPENDENCY: " + stable_json(missing).strip())
    visiting: list[str] = []
    visited: set[str] = set()
    cycle: list[str] = []
    def visit(node: str) -> None:
        nonlocal cycle
        if node in visiting:
            cycle = visiting[visiting.index(node):] + [node]
            return
        if node in visited or cycle:
            return
        visiting.append(node)
        for dep in sorted(items[node]["dependencies"]):
            visit(dep)
        visiting.pop(); visited.add(node)
    for node in sorted(items):
        visit(node)
    if cycle:
        raise WorkBraidError("DEPENDENCY_CYCLE: " + " -> ".join(cycle))
    reverse: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        reverse[edge["from"]].append(edge["to"])
    def depth(node: str) -> int:
        return 1 + max((depth(dep) for dep in items[node]["dependencies"]), default=0)
    active = [key for key, value in items.items() if value["normalized_status"] == "OPEN_ACTIONABLE"]
    critical = sorted(active, key=lambda key: (-depth(key), -len(reverse[key]), key))
    return {"nodes": sorted(items), "edges": sorted(edges, key=lambda x: (x["from"], x["to"])), "cycles": [], "missing_dependencies": [],
            "critical_path": critical, "highest_leverage_root_blocker": critical[0] if critical else None, "graph_hash": stable_hash([sorted(items), edges])}


def form_braids(strands: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for strand in strands:
        if strand["normalized_status"] != "OPEN_ACTIONABLE":
            continue
        key = (strand["root_cause"], tuple(strand["required_paths"]), tuple(strand["validator_chain"]), strand["milestone_advanced"])
        groups[key].append(strand)
    braids = []
    for key, items in sorted(groups.items(), key=lambda pair: str(pair[0])):
        ids = sorted(item["strand_id"] for item in items)
        braids.append({"braid_id": "BRAID-" + stable_hash(ids)[:12].upper(), "title": f"Compound {key[0]}", "strand_ids": ids,
            "shared_root_cause": key[0], "execution_order": ids, "required_paths": sorted({p for i in items for p in i["required_paths"]}),
            "validator_chain": sorted({v for i in items for v in i["validator_chain"]}), "excluded_strands": [], "exclusion_reasons": [],
            "rollback_boundary": "Exact required paths only", "expected_downstream_elimination": len(ids),
            "completion_definition": ["All contained strands are CLOSED_VERIFIED."], "readiness_status": "READY"})
    return braids


def _overlap(left: Iterable[str], right: Iterable[str]) -> bool:
    return bool(set(left) & set(right))


def form_cables(braids: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cables: list[dict[str, Any]] = []
    for braid in sorted(braids, key=lambda item: item["braid_id"]):
        compatible = None
        for cable in cables:
            if (cable["milestone"] == braid["shared_root_cause"] and not _overlap(cable["exact_write_boundary"], braid["required_paths"])) or set(cable["exact_write_boundary"]) == set(braid["required_paths"]):
                compatible = cable; break
        if compatible is None:
            compatible = {"cable_id": "CABLE-" + stable_hash([braid["braid_id"]])[:12].upper(), "title": braid["title"], "braid_ids": [],
                "prerequisite_cable_ids": [], "internal_execution_blocks": list(CABLE_STAGES), "exact_write_boundary": [], "validator_chain": [],
                "protected_actions": [], "owner_decisions": [], "external_waits": [], "checkpoint_policy": "Persist after every completed stage; reject material drift.",
                "repair_budget": 3, "completion_definition": ["All braids close with validator evidence."], "downstream_unlocks": [],
                "deterministic_priority_score": 0, "selection_reason": "Repository-local root blocker", "readiness_status": "READY", "milestone": braid["shared_root_cause"]}
            cables.append(compatible)
        compatible["braid_ids"].append(braid["braid_id"])
        compatible["exact_write_boundary"] = sorted(set(compatible["exact_write_boundary"] + list(braid["required_paths"])))
        compatible["validator_chain"] = sorted(set(compatible["validator_chain"] + list(braid["validator_chain"])))
        compatible["downstream_unlocks"].append(braid["expected_downstream_elimination"])
    for cable in cables:
        cable["deterministic_priority_score"] = 1000 + sum(cable["downstream_unlocks"]) * 100 + len(cable["braid_ids"]) * 10 - len(cable["exact_write_boundary"])
        cable["downstream_unlocks"] = [f"Eliminate {sum(cable['downstream_unlocks'])} downstream obligation(s)"]
        cable.pop("milestone")
    return sorted(cables, key=lambda item: (-item["deterministic_priority_score"], item["cable_id"]))


def repository_fingerprint(repo_root: str | Path, allowed_paths: Iterable[str] = ()) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)
        return result.stdout.strip()
    allowed = {}
    for relative in sorted(set(allowed_paths)):
        path = root / relative
        allowed[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return {"repository_root": str(root), "branch": git("branch", "--show-current"), "head": git("rev-parse", "HEAD"),
            "worktree_status": git("status", "--short"), "allowed_path_hashes": allowed,
            "worktree_fingerprint": stable_hash({"head": git("rev-parse", "HEAD"), "status": git("status", "--short"), "allowed": allowed})}


def make_checkpoint(state: Mapping[str, Any], fingerprint: Mapping[str, Any], *, completed_stages: Iterable[str] = (), repair_pass_count: int = 0) -> dict[str, Any]:
    completed = [stage for stage in CABLE_STAGES if stage in set(completed_stages)]
    if repair_pass_count > 3:
        raise WorkBraidError("REPAIR_BUDGET_EXHAUSTED")
    selected = state.get("selected_cable") or {}
    return {"schema": "AIOS_COMPOUND_WORK_BRAID_CHECKPOINT.v1", **dict(fingerprint), "dependency_graph_hash": state["dependency_graph"]["graph_hash"],
        "completed_strands": [], "completed_braids": [], "completed_cable_stages": completed, "remaining_stages": [s for s in CABLE_STAGES if s not in completed],
        "validation_receipts": [], "failed_attempts": [], "repair_pass_count": repair_pass_count,
        "current_hard_gate": "HUMAN_OWNER_REVIEW", "exact_restart_command": "python scripts/run_aios_compound_work_braid_v1.py --repo-root . --resume --pretty",
        "selected_cable_id": selected.get("cable_id"), "conditions_requiring_fresh_discovery": ["HEAD changed", "allowed-path content changed", "dependency graph changed", "governance changed"],
        "conditions_permitting_direct_continuation": ["HEAD, allowed paths, dependency graph, and governance are unchanged"]}


def validate_resume(checkpoint: Mapping[str, Any], fingerprint: Mapping[str, Any], dependency_graph_hash: str) -> None:
    if checkpoint.get("schema") != "AIOS_COMPOUND_WORK_BRAID_CHECKPOINT.v1":
        raise WorkBraidError("MALFORMED_CHECKPOINT")
    for key in ("head", "branch", "allowed_path_hashes"):
        if checkpoint.get(key) != fingerprint.get(key):
            raise WorkBraidError(f"REPOSITORY_DRIFT:{key}")
    if checkpoint.get("dependency_graph_hash") != dependency_graph_hash:
        raise WorkBraidError("DEPENDENCY_GRAPH_DRIFT")
    if int(checkpoint.get("repair_pass_count", 0)) > 3:
        raise WorkBraidError("REPAIR_BUDGET_EXHAUSTED")


def reconcile_prs(metadata: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    metadata = metadata or {}
    result = []
    for number in (1337, 1342, 1344):
        item = metadata.get(str(number)) or metadata.get(number)  # type: ignore[arg-type]
        if not item:
            classification = "REMOTE_METADATA_UNAVAILABLE"
        elif str(item.get("state", "")).upper() == "MERGED" or item.get("mergedAt"):
            classification = "MERGED_OR_ALREADY_PRESENT"
        else:
            classification = str(item.get("classification") or "OPEN_AND_REQUIRED")
        result.append({"pr_number": number, "classification": classification, "evidence": dict(item or {})})
    return result


def continuation_packet(state: Mapping[str, Any], fingerprint: Mapping[str, Any]) -> str:
    next_cable = state.get("selected_cable") or {"cable_id": "CABLE-AIOS-LOOP-DISCOVERY-AND-CLOSURE-V1", "title": "Loop Discovery and Closure"}
    allowed = next_cable.get("exact_write_boundary") or [
        "Reports/orchestration/AIOS_COMPOUND_WORK_BRAID_V1_STATE.json",
        "Reports/orchestration/AIOS_COMPOUND_WORK_BRAID_V1_REPORT.md",
        "Reports/orchestration/AIOS_COMPOUND_WORK_BRAID_V1_CHECKPOINT.json",
        "Reports/orchestration/AIOS_COMPOUND_WORK_BRAID_V1_NEXT_CODEX_PROMPT.md",
    ]
    allowed_text = "\n".join(f"- {path}" for path in allowed)
    return f"""CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN: HUMAN_OWNER_REVIEW_REQUIRED_BEFORE_EXECUTION
AI_OS BOOTSTRAP REQUIRED: READ_AND_OBEY_CURRENT_REPOSITORY_AGENTS_MD_BEFORE_EXECUTION
IDENTITY MARKER: AIOS_COMPOUND_WORK_BRAID_CONTINUATION_V1
SUPERVISOR IDENTITY: HUMAN OWNER ANTHONY
PACKET ID: PACKET-{next_cable['cable_id']}
MODE: APPLY
ZONE: CODEX_CLOUD_LOCAL_REPOSITORY
WORKER IDENTITY: CODEX_CLOUD_ENGINEERING_WORKER_01
LANE: AIOS_ORCHESTRATION_COMPOUND_WORK_BRAID
WORKTREE: {fingerprint['repository_root']}
BRANCH: {fingerprint['branch']}
MISSION ID: MISSION-AIOS-CLOSING-THE-LOOP-V1
MISSION NAME: AI_OS Closing the Loop
PROGRAM ID: PROGRAM-AIOS-COMPOUND-AUTONOMY-V1
PROGRAM NAME: AI_OS Compound Engineering Autonomy
EPIC ID: EPIC-AIOS-WORK-BRAID-ORCHESTRATION-V1
EPIC NAME: AI_OS Work-Braid Orchestration
BUCKET ID: BUCKET-AIOS-OPEN-LOOP-CONSOLIDATION-V1
BUCKET NAME: Repository Open-Loop Consolidation
PACKET NAME: {next_cable['title']}

ALLOWED PATHS:
{allowed_text}

FORBIDDEN PATHS:
- AGENTS.md
- RISK_POLICY.md
- SECURITY.md
- .git/
- .github/
- .env
- secrets/
- credentials/
- private/
- automation/forex_engine/
- Every path not explicitly listed under ALLOWED PATHS.

APPROVAL AUTHORITY:
Human Owner Anthony must explicitly approve this continuation before execution. No protected action is authorized.

VALIDATOR CHAIN:
1. Read back every changed file.
2. Confirm every changed path is in ALLOWED PATHS.
3. Run targeted tests declared by the selected cable.
4. Run git diff --check.
5. Run git status --short --branch.

STOP POINT:
Stop after implementation, validation, evidence generation, and owner handoff. Do not stage, commit, push, open or modify a PR, merge, deploy, access credentials, access a broker, or place an order.

MISSION:
Execute the selected dependency-correct cable only after owner approval: {next_cable['title']}.

PREFLIGHT:
Run pwd, git status --short --branch, git branch --show-current, git remote -v, git rev-parse HEAD, git diff --name-only, and git diff --stat. Stop on state mismatch.

FINAL REPORT FORMAT:
SUMMARY:
WHAT CHANGED:
FILES CHANGED:
VALIDATION:
REMAINING DIRTY FILES:
SAFE NEXT COMMAND:
STATUS: COMPLETE, NO COMMIT, NO PUSH
"""


def build_compound_work_braid(repo_root: str | Path, *, pr_metadata: Mapping[str, Mapping[str, Any]] | None = None, source_strands: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    inventory = load_canonical_work_packet_inventory(root)
    sources = list(source_strands) if source_strands is not None else list(inventory["records"])
    strands = collapse_duplicates(sources)
    graph = dependency_graph(strands)
    braids = form_braids(strands)
    cables = form_cables(braids)
    selected = cables[0] if cables else None
    state = {"schema": SCHEMA, "mode": "LOCAL_PLANNING_ONLY", "status": "READY" if selected else "NO_EXECUTABLE_CABLE",
        "repository": {}, "strands": strands, "braids": braids, "cables": cables, "selected_cable": selected,
        "dependency_graph": graph, "pr_reconciliation": reconcile_prs(pr_metadata),
        "programs": [{"program_id": f"PROGRAM-{index + 1:02d}", "name": name, "status": "ACTIVE" if index == 0 else "PLANNING_ONLY", "cable_ids": [item["cable_id"] for item in cables] if index == 0 else []} for index, name in enumerate(PROGRAM_NAMES)],
        "counts": {"strand_count": len(strands), "braid_count": len(braids), "cable_count": len(cables),
                   "duplicate_count": sum(s["normalized_status"] == "DUPLICATE" for s in strands), "superseded_count": sum(s["normalized_status"] == "SUPERSEDED" for s in strands)},
        "permissions": {key: False for key in PROTECTED}, "protected_actions": {key: False for key in PROTECTED},
        "queue_mutation_performed": False, "packet_execution_performed": False,
        "evidence_limitations": ["Repository-local evidence only", "PR metadata unavailable when not explicitly supplied"]}
    fingerprint = repository_fingerprint(root, selected["exact_write_boundary"] if selected else ())
    state["repository"] = fingerprint
    state["continuation_packet"] = continuation_packet(state, fingerprint)
    return state


def render_report(state: Mapping[str, Any]) -> str:
    counts = state["counts"]; selected = state.get("selected_cable") or {}
    prs = "\n".join(f"- PR #{item['pr_number']}: `{item['classification']}`" for item in state["pr_reconciliation"])
    return f"""# AI_OS Compound Work-Braid V1 Report

## Owner View
- Selected next cable: `{selected.get('cable_id', 'NONE')}`.
- Current hard gate: Human Owner review.
- Protected actions granted: none.

## Registry Summary
- Strands: {counts['strand_count']}
- Braids: {counts['braid_count']}
- Cables: {counts['cable_count']}
- Duplicates: {counts['duplicate_count']}
- Superseded: {counts['superseded_count']}

## PR Reconciliation
{prs}

## Safety
This output is deterministic local planning evidence. It did not mutate a queue, execute a packet, access credentials, access a broker, place an order, or grant approval.
"""


def validate_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the safety-critical state contract without optional packages."""
    required = {"schema", "mode", "status", "repository", "strands", "braids", "cables", "dependency_graph", "programs", "counts", "permissions", "protected_actions", "continuation_packet"}
    defects = [f"missing:{key}" for key in sorted(required - set(state))]
    if state.get("schema") != SCHEMA:
        defects.append("invalid:schema")
    if state.get("mode") != "LOCAL_PLANNING_ONLY":
        defects.append("invalid:mode")
    if len(state.get("programs", [])) != len(PROGRAM_NAMES):
        defects.append("invalid:program_count")
    if not str(state.get("continuation_packet", "")).startswith("CODEX-ONLY PROMPT\n"):
        defects.append("invalid:continuation_marker")
    for gate in ("permissions", "protected_actions"):
        if not isinstance(state.get(gate), Mapping) or any(value is not False for value in state.get(gate, {}).values()):
            defects.append(f"unsafe:{gate}")
    for strand in state.get("strands", []):
        if strand.get("normalized_status") not in STATUSES:
            defects.append(f"invalid:strand_status:{strand.get('strand_id')}")
    return {"schema": "AIOS_COMPOUND_WORK_BRAID_VALIDATION.v1", "status": "PASS" if not defects else "BLOCKED", "defects": defects,
            "schema_path": "schemas/orchestration/aios_compound_work_braid_v1.schema.json", "grants_authority": False}


@dataclass
class CompoundWorkBraidController:
    repo_root: Path

    def build(self, **options: Any) -> dict[str, Any]:
        return build_compound_work_braid(self.repo_root, **options)

    def checkpoint(self, state: Mapping[str, Any], **options: Any) -> dict[str, Any]:
        return make_checkpoint(state, state["repository"], **options)
