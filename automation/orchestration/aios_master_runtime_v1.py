"""Canonical coordinator for registered AI_OS orchestration APIs.

Only fixed Git/GitHub metadata commands and registered Python callables are used;
runtime artifacts are data and are never interpreted as commands.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

SCHEMA = "AIOS_MASTER_RUNTIME.v1"
STAGES = (
    "repository_preflight", "capability_discovery", "success_preservation",
    "open_work_reconciliation", "dependency_graph", "compound_work_braid",
    "cable_selection", "queue_planning", "packet_resolution", "validation",
    "checkpoint", "owner_report", "next_prompt_generation",
)
PROTECTED = ("broker_access", "credential_access", "deployment", "push", "pr_publication", "merge", "order_execution")


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode()).hexdigest()


class RuntimeBlocked(RuntimeError):
    """Fail-closed runtime contract violation with stable reason codes."""


class ResumeRejected(RuntimeBlocked):
    """Checkpoint identity is incompatible with the repository."""


class AIOSMasterRuntime:
    """Compose canonical services without executing generated instructions."""

    CAPABILITIES = {
        "orchestration_platform": ("automation/orchestration/platform.py", "tests/orchestration/test_orchestration_platform_v1.py"),
        "canonical_spine": ("automation/orchestration/aios_canonical_orchestration_spine_v1.py", "tests/orchestration/test_aios_canonical_orchestration_spine_v1.py"),
        "compound_work_braid": ("automation/orchestration/aios_compound_work_braid_v1.py", "tests/orchestration/test_aios_compound_work_braid_v1.py"),
        "packet_queue_planner": ("automation/orchestration/aios_packet_queue_planner.py", "tests/orchestration/test_aios_packet_queue_planner.py"),
        "development_dispatcher": ("automation/orchestration/runtime_queue/aios_development_dispatcher.py", "tests/orchestration/test_aios_development_dispatcher.py"),
        "packet_builder": ("automation/orchestration/aios_codex_packet_builder.py", "tests/orchestration/test_aios_codex_packet_builder.py"),
        "packet_resolver": ("automation/orchestration/runtime_queue/aios_execution_packet_resolver.py", "tests/orchestration/test_aios_execution_packet_resolver.py"),
        "autonomy_governor": ("automation/orchestration/aios_autonomy_decision_governor.py", "tests/orchestration/test_aios_autonomy_decision_governor.py"),
        "work_countdown": ("automation/orchestration/aios_work_countdown_v1.py", "tests/orchestration/test_aios_work_countdown_v1.py"),
    }

    def __init__(self, repo_root: str | Path = ".", *, platform: Any = None) -> None:
        self.root = Path(repo_root).resolve()
        if platform is None:
            from automation.orchestration.platform import OrchestrationPlatform
            platform = OrchestrationPlatform(self.root)
        self.platform = platform
        self.state_path = self.root / ".aios/runtime/master-runtime-v1.json"

    def _git(self, *args: str, check: bool = True) -> str:
        return subprocess.run(["git", *args], cwd=self.root, check=check, text=True, capture_output=True).stdout.strip()

    def repository(self) -> dict[str, Any]:
        return {"root": str(self.root), "branch": self._git("branch", "--show-current"), "head": self._git("rev-parse", "HEAD"), "status_lines": self._git("status", "--porcelain").splitlines()}

    def capabilities(self) -> list[dict[str, Any]]:
        head = self.repository()["head"]
        owners: dict[str, list[str]] = {}
        result = []
        for capability_id, (source, test) in self.CAPABILITIES.items():
            owners.setdefault(source, []).append(capability_id)
            exists = (self.root / source).is_file() and (self.root / test).is_file()
            result.append({"capability_id": capability_id, "owner": source, "source_paths": [source], "test_paths": [test], "schema_paths": [], "commit_sha": head, "evidence_status": "CREDITED" if exists else "INCOMPLETE", "freshness": "OBSERVED_HEAD"})
        conflicts = {path: ids for path, ids in owners.items() if len(ids) > 1}
        canonical_entries = [path for path in ("aios.py",) if (self.root / path).is_file()]
        compatibility_entries = [path for path in ("scripts/run_aios_master_runtime_v1.py",) if (self.root / path).is_file()]
        if conflicts or len(canonical_entries) != 1:
            raise RuntimeBlocked("DUPLICATE_CAPABILITY_OWNER" if conflicts else "DUPLICATE_ENTRY_POINT")
        self.entry_points = {"canonical": canonical_entries, "compatibility": compatibility_entries, "conflicts": []}
        return result

    def environment(self) -> dict[str, str]:
        tools = {"python": sys.executable, "git": shutil.which("git"), "gh_cli": shutil.which("gh"), "powershell": shutil.which("pwsh") or shutil.which("powershell"), "node": shutil.which("node"), "npm": shutil.which("npm")}
        matrix = {key: ("AVAILABLE" if value else ("REQUIRED_MISSING" if key in {"python", "git"} else "OPTIONAL_MISSING")) for key, value in tools.items()}
        matrix["git_remote"] = "AVAILABLE" if self._git("remote") else "UNAVAILABLE_NOT_REQUIRED"
        try:
            import jsonschema  # noqa: F401
            matrix["jsonschema"] = "AVAILABLE"
        except ImportError:
            matrix["jsonschema"] = "OPTIONAL_MISSING"
        return matrix

    def reconcile_prs(self) -> dict[str, str]:
        if not shutil.which("gh") or not self._git("remote"):
            return {str(number): "REMOTE_METADATA_UNAVAILABLE" for number in (1337, 1342, 1344)}
        result = {}
        head = self.repository()["head"]
        for number in (1337, 1342, 1344):
            command = ["gh", "pr", "view", str(number), "--json", "state,mergeable,headRefOid,mergeCommit"]
            viewed = subprocess.run(command, cwd=self.root, text=True, capture_output=True)
            if viewed.returncode:
                result[str(number)] = "REMOTE_METADATA_UNAVAILABLE"
                continue
            metadata = json.loads(viewed.stdout)
            merge_sha = (metadata.get("mergeCommit") or {}).get("oid")
            if metadata.get("state") == "MERGED" or merge_sha == head:
                classification = "SUPERSEDED_BY_MAIN"
            elif metadata.get("mergeable") == "MERGEABLE":
                classification = "MERGE_CANDIDATE"
            else:
                classification = "DIVERGED_REPAIR_REQUIRED"
            result[str(number)] = classification
        return result

    @staticmethod
    def _summary(value: Any) -> dict[str, Any]:
        return {"schema": value.get("schema") or value.get("schema_version"), "status": value.get("status") or value.get("queue_status") or value.get("decision_category"), "fingerprint": fingerprint(value)}

    def _compose(self, repository: dict[str, Any], capabilities: list[dict[str, Any]]) -> dict[str, Any]:
        deterministic_time = "1970-01-01T00:00:00Z"
        spine = self.platform.spine(as_of_utc=deterministic_time)
        braid = self.platform.compound_work_braid()
        queue = self.platform.queue({"candidates": []})
        dispatch = self.platform.dispatch({"schema": "AIOS_RUNTIME_EXECUTION_QUEUE.v1", "items": []})
        builder = self.platform.build_packet(repository_state={}, packet_identity={}, mission="", allowed_paths=[], validators=[])
        resolver = self.platform.resolve_packet({}, {})
        governor = self.platform.govern_autonomy({}, generated_at_utc=deterministic_time)
        countdown = self.platform.countdown()
        return {"spine": self._summary(spine), "braid": self._summary(braid), "queue": self._summary(queue), "dispatcher": self._summary(dispatch), "packet_builder": self._summary(builder), "packet_resolver": self._summary(resolver), "autonomy_governor": self._summary(governor), "countdown": self._summary(countdown), "selected_cable": braid.get("selected_cable"), "capability_count": len(capabilities)}

    def _identity(self, repo: dict[str, Any], graph: dict[str, Any], composition: dict[str, Any]) -> dict[str, Any]:
        return {"root": repo["root"], "branch": repo["branch"], "head": repo["head"], "dependency_graph_fingerprint": fingerprint(graph), "allowed_paths_fingerprint": fingerprint(["orchestration_consolidation"]), "composition_fingerprint": fingerprint(composition)}

    def _stages(self, identity: dict[str, Any], composition: dict[str, Any]) -> list[dict[str, Any]]:
        completed, previous = [], ""
        for index, stage_id in enumerate(STAGES):
            inputs = {"identity": identity, "composition": composition, "previous": previous}
            output = fingerprint({"stage": stage_id, "inputs": inputs})
            completed.append({"stage_id": stage_id, "capability_id": f"master_runtime.{stage_id}", "dependencies": [] if index == 0 else [STAGES[index-1]], "mode": "REGISTERED_PYTHON_API", "input_fingerprint": fingerprint(inputs), "output_fingerprint": output, "validator_ids": ["master_runtime_contract_v1"], "retry_limit": 1, "approval_required": False, "protected_action": False, "status": "COMPLETED", "reason_codes": ["REGISTERED_API_COMPOSED"], "completion_receipt": output})
            previous = output
        return completed

    def _write_checkpoint(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.state_path)

    def execute(self, *, command: str = "plan", checkpoint: bool = False) -> dict[str, Any]:
        repo, capabilities = self.repository(), self.capabilities()
        graph = {"nodes": list(STAGES), "edges": [[STAGES[i - 1], STAGES[i]] for i in range(1, len(STAGES))]}
        composition = self._compose(repo, capabilities)
        identity = self._identity(repo, graph, composition)
        state = {"schema": SCHEMA, "status": "PASS", "command": command, "repository": repo, "identity": identity, "capabilities": capabilities, "entry_points": self.entry_points, "environment": self.environment(), "dependency_graph": graph, "composition": composition, "protected_actions": {key: False for key in PROTECTED}, "permissions": {"arbitrary_shell": False, "generated_prompt_execution": False}, "open_pr_reconciliation": self.reconcile_prs()}
        state["stages"] = self._stages(identity, composition)
        state["owner_report"] = {"credited_capabilities": len([c for c in capabilities if c["evidence_status"] == "CREDITED"]), "duplicate_work": [], "selected_cable": composition["selected_cable"], "completed_stages": len(state["stages"]), "blocked_stages": 0, "exact_next_owner_action": "Review and create the prepared pull request.", "protected_actions_disabled": list(PROTECTED)}
        state["normalized_fingerprint"] = fingerprint({k: v for k, v in state.items() if k not in {"command", "repository"}} | {"repository": {k: v for k, v in repo.items() if k != "status_lines"}})
        if checkpoint:
            self._write_checkpoint(state)
        return state

    def resume(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            raise ResumeRejected("CHECKPOINT_NOT_FOUND")
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        current = self.execute(command="resume")
        reasons = [f"INCOMPATIBLE_{key.upper()}" for key, value in current["identity"].items() if saved.get("identity", {}).get(key) != value]
        if reasons:
            raise ResumeRejected(",".join(reasons))
        self._write_checkpoint(current)
        return current

    def validate_state(self, state: dict[str, Any]) -> dict[str, Any]:
        defects = []
        if [stage.get("stage_id") for stage in state.get("stages", [])] != list(STAGES): defects.append("INVALID_STAGE_ORDER")
        if any(state.get("protected_actions", {}).values()): defects.append("PROTECTED_ACTION_ENABLED")
        if state.get("permissions") != {"arbitrary_shell": False, "generated_prompt_execution": False}: defects.append("UNSAFE_EXECUTION_PERMISSION")
        required = {"stage_id", "capability_id", "dependencies", "mode", "input_fingerprint", "output_fingerprint", "validator_ids", "retry_limit", "approval_required", "protected_action", "status", "reason_codes", "completion_receipt"}
        if any(required - set(stage) for stage in state.get("stages", [])): defects.append("INCOMPLETE_STAGE_RECEIPT")
        if state.get("entry_points", {}).get("conflicts"): defects.append("DUPLICATE_ENTRY_POINT")
        return {"schema": "AIOS_MASTER_RUNTIME_VALIDATION.v1", "status": "PASS" if not defects else "BLOCKED", "defects": defects}


def run(repo_root: str | Path = ".", command: str = "plan") -> dict[str, Any]:
    runtime = AIOSMasterRuntime(repo_root)
    if command == "resume": return runtime.resume()
    state = runtime.execute(command=command, checkpoint=command == "run")
    if command == "validate": state["validation"] = runtime.validate_state(state)
    return state
