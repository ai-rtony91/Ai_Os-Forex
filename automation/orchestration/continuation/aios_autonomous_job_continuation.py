"""AI_OS Autonomous Job Continuation V1.

Bounded READ_ONLY/DRY_RUN continuation evaluator. It consumes existing
continuation, security, dirty-tree, governor, approval, and validator evidence.
It does not run APPLY, stage, commit, push, launch workers, schedule daemons,
touch broker/live trading paths, call webhooks, or mutate dashboards.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_SCHEMA = "AIOS_AUTONOMOUS_JOB_CONTINUATION_STATE.v1"
EVIDENCE_SCHEMA = "AIOS_AUTONOMOUS_JOB_CONTINUATION_EVIDENCE.v1"
COMPONENT = "autonomous_job_continuation"
MODE = "DRY_RUN_READ_ONLY"


def project_research_observation(observation: dict | None, *, now: float) -> dict:
    """Narrow owner-reported observation, never dispatch or proof authority.

    A recent heartbeat cannot extend a phase with no useful progress. The
    publishing lifecycle owner must pin this module in its next exact grant.
    """
    import math
    phases = {"READING": 120, "SCORING": 300, "SAVING": 60, "CHECKING": 60,
              "ROUTING": 60, "WAITING_FOR_OWNER": 0, "STOPPED": 0}
    output = {"state": "UNKNOWN", "active_workers": None, "phase": "UNKNOWN",
              "job": None, "worker_identity": None, "heartbeat_at": None,
              "useful_progress_at": None, "metadata_saved_at": None,
              "last_accepted_at": None, "queue_size": None,
              "observation_kind": "OWNER_REPORTED_NOT_PROCESS_PROBE"}
    if not isinstance(observation, dict) or not math.isfinite(now):
        return output
    if (observation.get("schema") != "S6_RESEARCH_OWNER_OBSERVATION.v1" or
            observation.get("owner") != "EXISTING_GOAL_MUSCLE98" or
            observation.get("source_pins_checked") is not True or
            observation.get("role") != "MARKET" or
            observation.get("phase") not in phases):
        return output
    import re
    def identity(value):
        return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) else None
    def stamp(value):
        return value if type(value) in (float, int) and math.isfinite(value) and 0 <= value <= now else None
    def count(value):
        return value if type(value) is int and value >= 0 else None
    phase = observation["phase"]
    for field in ("heartbeat_at", "useful_progress_at", "metadata_saved_at", "last_accepted_at"):
        output[field] = stamp(observation.get(field))
    output.update(phase=phase, job=identity(observation.get("job")),
                  worker_identity=identity(observation.get("worker_identity")),
                  queue_size=count(observation.get("queue_size")))
    fresh = output["heartbeat_at"] is not None and now-output["heartbeat_at"] <= 30
    useful = output["useful_progress_at"] is not None and now-output["useful_progress_at"] <= phases[phase]
    if not fresh:
        output["state"] = "STALE"
    elif phase in ("STOPPED", "WAITING_FOR_OWNER"):
        output.update(state=phase, active_workers=0)
    elif not useful:
        output["state"] = "STALLED"
    elif output["worker_identity"] and output["job"] and count(observation.get("active_workers")) == 1:
        output.update(state="ACTIVE_OWNER_REPORTED", active_workers=1)
    return output

CONTINUATION_STATES = (
    "BOOT",
    "RECON",
    "TASK_SELECTION",
    "DRY_RUN_EXECUTION",
    "VALIDATION",
    "REPAIR_ATTEMPT",
    "CONTINUE",
    "REVIEW_REQUIRED",
    "STOP",
    "SOS",
)

SAFE_TASK_MODES = {"READ_ONLY", "DRY_RUN"}
STOP_SECURITY_STATES = {"REVIEW_REQUIRED", "STOP", "SOS"}
APPROVAL_REQUIRED_STATUSES = {
    "pending",
    "pending_review",
    "review",
    "missing",
    "missing_approval_status",
    "approval_required",
    "awaiting_approval",
}
VALIDATOR_FAILURE_STATUSES = {"fail", "failed", "error", "blocked", "review_required", "invalid"}
VALIDATOR_PASS_STATUSES = {"pass", "passed", "ok", "success", "green"}
UNSAFE_TERMS = (
    "broker",
    "oanda",
    "live trading",
    "live-trading",
    "real order",
    "live order",
    "webhook",
    "production",
    "deploy",
    "dashboard mutation",
    "apps/dashboard",
    "secret",
    "credential",
    ".env",
    "worker launch",
    "scheduler",
    "daemon",
    "git add",
    "git commit",
    "git push",
    "merge",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _load_module(path: Path, name: str) -> Any | None:
    if not path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_branch(repo_root: Path) -> str:
    head = repo_root / ".git" / "HEAD"
    try:
        text = head.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    if text.startswith("ref:"):
        return text.rsplit("/", 1)[-1]
    return "detached"


def _status_value(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("status", "result", "validator_status", "normalized_status", "approval_status"):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return str(value).strip().lower()
    validation = payload.get("validation")
    if isinstance(validation, dict):
        value = validation.get("status")
        if value not in (None, "", [], {}):
            return str(value).strip().lower()
    return ""


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _contains_unsafe(value: Any) -> bool:
    text = json.dumps(value, sort_keys=True, default=str).lower()
    return any(term in text for term in UNSAFE_TERMS)


def _task_scope_for_security_scan(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task.get("task_id"),
        "title": task.get("title"),
        "mode": task.get("mode"),
        "lane": task.get("lane"),
        "allowed_paths": task.get("allowed_paths"),
        "decision_category": task.get("decision_category"),
    }


def _dirty_signature(dirty_tree: dict[str, Any] | None) -> str:
    if not isinstance(dirty_tree, dict):
        return "missing"
    files = dirty_tree.get("dirty_files")
    if not isinstance(files, list):
        files = dirty_tree.get("files")
    normalized = []
    for item in files if isinstance(files, list) else []:
        if isinstance(item, dict):
            normalized.append(
                {
                    "path": str(item.get("path") or ""),
                    "classification": str(item.get("classification") or ""),
                    "indicators": sorted(str(value) for value in item.get("security_indicators") or []),
                }
            )
    return _hash_payload(
        {
            "overall": dirty_tree.get("overall_classification"),
            "dirty_count": dirty_tree.get("dirty_count"),
            "files": sorted(normalized, key=lambda item: item["path"]),
        }
    )


def _security_signature(security_state: dict[str, Any] | None) -> str:
    if not isinstance(security_state, dict):
        return "missing"
    events = []
    for event in security_state.get("events") or []:
        if isinstance(event, dict):
            events.append(
                {
                    "category": event.get("category"),
                    "severity": event.get("severity"),
                    "source_path": event.get("source_path"),
                }
            )
    return _hash_payload({"overall_state": security_state.get("overall_state"), "events": events})


def _governor_task(governor_decision: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(governor_decision, dict):
        return {
            "task_id": "none",
            "title": "No governor decision was available.",
            "mode": "BLOCKED",
            "lane": "BLOCKED",
            "blocked": True,
            "blocked_reason": "governor_decision_missing",
            "validators": ["Manual evidence review"],
            "allowed_paths": [],
            "forbidden_paths": [],
        }

    scope = governor_decision.get("recommended_packet_scope")
    scope = scope if isinstance(scope, dict) else {}
    lane = str(governor_decision.get("allowed_lane") or scope.get("lane") or "BLOCKED")
    scope_mode = str(scope.get("mode") or "").upper()
    if lane == "READ_ONLY":
        mode = "READ_ONLY"
    elif lane == "DRY_RUN" or scope_mode == "DRY_RUN":
        mode = "DRY_RUN"
    elif lane.startswith("APPLY") or scope_mode == "APPLY":
        mode = "APPLY"
    else:
        mode = "BLOCKED"

    blocked_reason = governor_decision.get("blocked_reason")
    return {
        "task_id": str(governor_decision.get("selected_candidate_id") or governor_decision.get("decision_id") or "none"),
        "title": str(governor_decision.get("next_highest_value_task") or "No safe next task is proven."),
        "mode": mode,
        "lane": lane,
        "blocked": governor_decision.get("blocked") is True or lane == "BLOCKED",
        "blocked_reason": None if blocked_reason in (None, "", [], {}) else str(blocked_reason),
        "validators": _as_list(governor_decision.get("required_validators")) or ["Manual evidence review"],
        "allowed_paths": _as_list(scope.get("files_allowed")),
        "forbidden_paths": _as_list(scope.get("files_forbidden")),
        "decision_category": str(governor_decision.get("decision_category") or "BLOCKED_STOP_AND_REPORT"),
    }


def _task_signature(task: dict[str, Any]) -> str:
    return _hash_payload(
        {
            "task_id": task.get("task_id"),
            "mode": task.get("mode"),
            "lane": task.get("lane"),
            "validators": task.get("validators"),
        }
    )


def _approval_summary(approval_gate: Any, approval_inbox: Any) -> dict[str, Any]:
    statuses = [_status_value(approval_gate), _status_value(approval_inbox)]
    pending = any(status in APPROVAL_REQUIRED_STATUSES for status in statuses if status)
    explicit = any(status in {"approved", "explicitly_approved", "pass", "passed"} for status in statuses)
    return {
        "approval_required": pending,
        "explicit_approval_present": explicit,
        "approval_gate_status": statuses[0] or "missing",
        "approval_inbox_status": statuses[1] or "missing",
        "approval_mutated": False,
    }


def _validator_summary(validator_evidence: Any, governor_task: dict[str, Any], repair_result: Any = None) -> dict[str, Any]:
    status = _status_value(validator_evidence)
    if not status and governor_task.get("decision_category") == "VALIDATOR_REPAIR":
        status = "failed"
    if not status:
        status = "unknown"
    repair_status = _status_value(repair_result)
    return {
        "status": status,
        "post_repair_status": repair_status or "unknown",
        "failed": status in VALIDATOR_FAILURE_STATUSES,
        "passed": status in VALIDATOR_PASS_STATUSES,
        "required_validators": list(governor_task.get("validators") or []),
    }


def collect_evidence(repo_root: str | Path, generated_at_utc: str | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    now = generated_at_utc or utc_now()
    dirty_tree: dict[str, Any] | None = None
    security_state: dict[str, Any] | None = None
    governor_decision: dict[str, Any] | None = None

    dirty_module = _load_module(root / "automation" / "orchestration" / "continuation" / "aios_dirty_tree_classifier.py", "aios_dirty_tree_classifier")
    if dirty_module is not None:
        try:
            dirty_tree = dirty_module.build_dirty_tree_classification(repo_root=root)
        except Exception:
            dirty_tree = None

    security_module = _load_module(root / "automation" / "security" / "aios_preemptive_security_layer.py", "aios_preemptive_security_layer")
    if security_module is not None:
        try:
            security_state = security_module.build_security_state(repo_root=root, dirty_tree=dirty_tree)
        except Exception:
            security_state = None

    governor_module = _load_module(root / "automation" / "orchestration" / "aios_autonomy_decision_governor.py", "aios_autonomy_decision_governor")
    if governor_module is not None:
        try:
            governor_decision = governor_module.choose_next_decision(
                governor_module.discover_evidence(root),
                generated_at_utc=now,
            )
        except Exception:
            governor_decision = None

    approval_gate = _load_json(root / "automation" / "orchestration" / "approval_inbox" / "APPLY_APPROVAL_GATE_001.json")
    approval_inbox = _load_json(root / "automation" / "orchestration" / "approval_inbox" / "APPROVAL_INBOX_001.json")
    validator_evidence = _load_json(root / "Reports" / "validator_evidence_router" / "AIOS_VALIDATOR_EVIDENCE_ROUTER_LATEST.json")

    return build_evidence(
        repo_root=str(root),
        branch=_read_branch(root),
        dirty_tree=dirty_tree,
        security_state=security_state,
        governor_decision=governor_decision,
        approval_gate=approval_gate,
        approval_inbox=approval_inbox,
        validator_evidence=validator_evidence,
        generated_at_utc=now,
    )


def build_evidence(
    *,
    repo_root: str,
    branch: str = "unknown",
    dirty_tree: dict[str, Any] | None = None,
    security_state: dict[str, Any] | None = None,
    governor_decision: dict[str, Any] | None = None,
    approval_gate: Any = None,
    approval_inbox: Any = None,
    validator_evidence: Any = None,
    repair_result: Any = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    now = generated_at_utc or utc_now()
    task = _governor_task(governor_decision)
    return {
        "schema": EVIDENCE_SCHEMA,
        "generated_at_utc": now,
        "repo_root": str(repo_root),
        "branch": branch,
        "dirty_tree": dirty_tree if isinstance(dirty_tree, dict) else None,
        "security_state": security_state if isinstance(security_state, dict) else None,
        "governor_decision": governor_decision if isinstance(governor_decision, dict) else None,
        "selected_task": task,
        "approval": _approval_summary(approval_gate, approval_inbox),
        "validator": _validator_summary(validator_evidence, task, repair_result=repair_result),
        "dirty_signature": _dirty_signature(dirty_tree),
        "security_signature": _security_signature(security_state),
        "task_signature": _task_signature(task),
        "safety": {
            "read_only": True,
            "dry_run_only": True,
            "apply_allowed": False,
            "git_add_allowed": False,
            "git_commit_allowed": False,
            "git_push_allowed": False,
            "pr_allowed": False,
            "merge_allowed": False,
            "worker_launch_allowed": False,
            "scheduler_allowed": False,
            "daemon_allowed": False,
            "broker_allowed": False,
            "live_trading_allowed": False,
            "production_allowed": False,
            "dashboard_mutation_allowed": False,
        },
    }


def _resume_check(previous_state: dict[str, Any] | None, evidence: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(previous_state, dict):
        return {"requested": False, "can_resume": False, "reason": "No previous state supplied."}
    expected = {
        "repo_root": previous_state.get("repo_root"),
        "branch": previous_state.get("branch"),
        "dirty_signature": previous_state.get("dirty_signature"),
        "security_signature": previous_state.get("security_signature"),
        "task_signature": previous_state.get("task_signature"),
    }
    observed = {
        "repo_root": evidence.get("repo_root"),
        "branch": evidence.get("branch"),
        "dirty_signature": evidence.get("dirty_signature"),
        "security_signature": evidence.get("security_signature"),
        "task_signature": _task_signature(task),
    }
    mismatches = [key for key, value in expected.items() if value not in (None, "", [], {}) and value != observed.get(key)]
    return {
        "requested": True,
        "can_resume": not mismatches,
        "reason": "Resume evidence matches." if not mismatches else "Resume evidence changed; review is required.",
        "mismatches": mismatches,
        "expected": expected,
        "observed": observed,
    }


def _new_state(
    *,
    evidence: dict[str, Any],
    state: str,
    state_history: list[str],
    selected_task: dict[str, Any],
    repair_count: int,
    resume: dict[str, Any],
    next_safe_action: str,
    stop_reason: str | None = None,
) -> dict[str, Any]:
    now = evidence.get("generated_at_utc") or utc_now()
    seed = {
        "generated_at_utc": now,
        "repo_root": evidence.get("repo_root"),
        "branch": evidence.get("branch"),
        "dirty_signature": evidence.get("dirty_signature"),
        "security_signature": evidence.get("security_signature"),
        "task_signature": _task_signature(selected_task),
        "state": state,
    }
    return {
        "schema": STATE_SCHEMA,
        "generated_at_utc": now,
        "cycle_id": f"AIOS-AJC-{_hash_payload(seed)}",
        "component": COMPONENT,
        "mode": MODE,
        "repo_root": evidence.get("repo_root"),
        "branch": evidence.get("branch"),
        "state": state,
        "state_history": state_history,
        "selected_task": selected_task,
        "validators": list(evidence.get("validator", {}).get("required_validators") or []),
        "validator_status": evidence.get("validator", {}).get("status", "unknown"),
        "repair_count": repair_count,
        "security_snapshot": {
            "overall_state": (evidence.get("security_state") or {}).get("overall_state", "UNKNOWN"),
            "safe_for_dry_run": (evidence.get("security_state") or {}).get("safe_for_dry_run") is True,
            "safe_for_apply": (evidence.get("security_state") or {}).get("safe_for_apply") is True,
            "sos_required": (evidence.get("security_state") or {}).get("sos_required") is True,
            "stop_required": (evidence.get("security_state") or {}).get("stop_required") is True,
            "review_required": (evidence.get("security_state") or {}).get("review_required") is True,
        },
        "dirty_signature": evidence.get("dirty_signature"),
        "security_signature": evidence.get("security_signature"),
        "task_signature": _task_signature(selected_task),
        "approval_snapshot": evidence.get("approval"),
        "resume": resume,
        "evidence": evidence,
        "execution": {
            "executed_commands": [],
            "allowlisted_action": "internal:dry_run_task_preview" if state == "CONTINUE" else "",
            "mutation_performed": False,
            "apply_performed": False,
            "protected_action_performed": False,
            "worker_launch_performed": False,
            "scheduler_performed": False,
            "daemon_performed": False,
        },
        "safe_to_continue_without_human": state == "CONTINUE",
        "stop_reason": stop_reason,
        "stop_reason_class": (None if state == 'CONTINUE' else
            'OWNER_ACTION_REQUIRED' if stop_reason in {'approval_required','non_dry_run_task'} else
            'UNRECOVERABLE_FAILURE' if stop_reason == 'validator_exhaustion' else 'SAFETY_INTEGRITY_BLOCK'),
        "normal_continue_prompt_required": False,
        "next_safe_action": next_safe_action,
        "safety": evidence.get("safety"),
    }


def build_continuation_state(
    *,
    repo_root: str | Path = ".",
    evidence: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    ev = evidence if isinstance(evidence, dict) else collect_evidence(repo_root, generated_at_utc=generated_at_utc)
    task = ev.get("selected_task") if isinstance(ev.get("selected_task"), dict) else _governor_task(ev.get("governor_decision"))
    history = ["BOOT", "RECON"]
    repair_count = int((previous_state or {}).get("repair_count") or 0)
    resume = _resume_check(previous_state, ev, task)

    if resume["requested"] and not resume["can_resume"]:
        return _new_state(
            evidence=ev,
            state="REVIEW_REQUIRED",
            state_history=history + ["REVIEW_REQUIRED"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason="resume_mismatch",
            next_safe_action="Stop and review resume mismatch before continuation.",
        )

    security = ev.get("security_state") if isinstance(ev.get("security_state"), dict) else {}
    security_state = str(security.get("overall_state") or "UNKNOWN")
    if security_state == "SOS" or security.get("sos_required") is True:
        return _new_state(
            evidence=ev,
            state="SOS",
            state_history=history + ["SOS"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason="security_sos",
            next_safe_action="SOS: stop continuation and escalate without printing secret-like values.",
        )
    if security_state in {"STOP", "REVIEW_REQUIRED", "UNKNOWN"} or security.get("stop_required") is True:
        state = "STOP" if security_state == "STOP" or security.get("stop_required") is True else "REVIEW_REQUIRED"
        return _new_state(
            evidence=ev,
            state=state,
            state_history=history + [state],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason=f"security_{security_state.lower()}",
            next_safe_action=str(security.get("next_safe_action") or "Stop for security review before continuation."),
        )

    dirty = ev.get("dirty_tree") if isinstance(ev.get("dirty_tree"), dict) else {}
    dirty_sos = dirty.get("sos_required") is True
    security_watch_or_clear = security_state in {"WATCH", "CLEAR"}
    if dirty.get("protected_stop_required") is True:
        return _new_state(
            evidence=ev,
            state="STOP",
            state_history=history + ["STOP"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason="dirty_tree_protected_authority",
            next_safe_action="Stop and review protected dirty files before continuation.",
        )
    if dirty_sos and not security_watch_or_clear:
        return _new_state(
            evidence=ev,
            state="SOS",
            state_history=history + ["SOS"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason="dirty_tree_security_sos",
            next_safe_action="SOS: dirty tree security indicators require escalation.",
        )
    if dirty.get("review_required") is True:
        return _new_state(
            evidence=ev,
            state="REVIEW_REQUIRED",
            state_history=history + ["REVIEW_REQUIRED"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason="dirty_tree_review_required",
            next_safe_action="Review dirty tree state before continuation.",
        )

    history.append("TASK_SELECTION")
    if task.get("blocked"):
        return _new_state(
            evidence=ev,
            state="REVIEW_REQUIRED",
            state_history=history + ["REVIEW_REQUIRED"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason=str(task.get("blocked_reason") or "governor_blocked"),
            next_safe_action="Review governor blocked decision before continuation.",
        )
    if task.get("mode") not in SAFE_TASK_MODES:
        return _new_state(
            evidence=ev,
            state="REVIEW_REQUIRED",
            state_history=history + ["REVIEW_REQUIRED"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason="non_dry_run_task",
            next_safe_action="Stop before APPLY or protected action; Anthony approval is required.",
        )
    if security_state == "WATCH" and task.get("mode") != "DRY_RUN":
        return _new_state(
            evidence=ev,
            state="REVIEW_REQUIRED",
            state_history=history + ["REVIEW_REQUIRED"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason="security_watch_requires_dry_run",
            next_safe_action="Continue only DRY_RUN work while security state is WATCH.",
        )
    if _contains_unsafe(_task_scope_for_security_scan(task)):
        return _new_state(
            evidence=ev,
            state="STOP",
            state_history=history + ["STOP"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason="unsafe_task_scope",
            next_safe_action="Stop before broker, live trading, secrets, production, dashboard mutation, worker, scheduler, or protected action scope.",
        )

    approval = ev.get("approval") if isinstance(ev.get("approval"), dict) else {}
    if approval.get("approval_required") is True:
        return _new_state(
            evidence=ev,
            state="REVIEW_REQUIRED",
            state_history=history + ["REVIEW_REQUIRED"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason="approval_required",
            next_safe_action="Stop until Anthony reviews required approval evidence.",
        )

    history.extend(["DRY_RUN_EXECUTION", "VALIDATION"])
    validator = ev.get("validator") if isinstance(ev.get("validator"), dict) else {}
    if validator.get("failed") is True:
        if repair_count >= 1:
            return _new_state(
                evidence=ev,
                state="STOP",
                state_history=history + ["STOP"],
                selected_task=task,
                repair_count=repair_count,
                resume=resume,
                stop_reason="validator_exhaustion",
                next_safe_action="Stop after one repair attempt; validator failure remains.",
            )
        repair_count = 1
        history.extend(["REPAIR_ATTEMPT", "VALIDATION"])
        if validator.get("post_repair_status") in VALIDATOR_PASS_STATUSES:
            return _new_state(
                evidence=ev,
                state="CONTINUE",
                state_history=history + ["CONTINUE"],
                selected_task=task,
                repair_count=repair_count,
                resume=resume,
                next_safe_action="Validator repair preview passed; continue with the next safe DRY_RUN cycle.",
            )
        return _new_state(
            evidence=ev,
            state="STOP",
            state_history=history + ["STOP"],
            selected_task=task,
            repair_count=repair_count,
            resume=resume,
            stop_reason="validator_exhaustion",
            next_safe_action="Stop after one deterministic repair preview; validator failure remains.",
        )

    return _new_state(
        evidence=ev,
        state="CONTINUE",
        state_history=history + ["CONTINUE"],
        selected_task=task,
        repair_count=repair_count,
        resume=resume,
        next_safe_action="Continue to the next safe READ_ONLY/DRY_RUN cycle.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit AI_OS Autonomous Job Continuation V1 state JSON.")
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect.")
    parser.add_argument("--previous-state-json", default="", help="Optional previous state JSON for resume validation.")
    args = parser.parse_args(argv)

    previous_state = None
    if args.previous_state_json:
        try:
            previous_state = json.loads(args.previous_state_json)
        except json.JSONDecodeError:
            previous_state = {"_parse_error": "previous_state_json_invalid"}
    state = build_continuation_state(repo_root=args.repo_root, previous_state=previous_state)
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
