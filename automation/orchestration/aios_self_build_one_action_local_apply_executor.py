from __future__ import annotations

import argparse
import json
from pathlib import PurePosixPath
from typing import Any, Callable

from automation.orchestration.claims.aios_task_claim_control import ClaimError, ExecutionAdmission


SCHEMA = "AIOS_SELF_BUILD_ONE_ACTION_LOCAL_APPLY_EXECUTOR.v1"
LOCAL_EXECUTOR_MODE = "ONE_ACTION_LOCAL_APPLY_EXECUTOR"
EXECUTE_MODE = "EXECUTE_ONE_ACTION"
DRY_RUN_MODE = "DRY_RUN"
ONE_ACTION_APPLY_MODE = "ONE_ACTION_APPLY"
APPROVED_BY = "Anthony Meza"
DEFAULT_WORKING_DIRECTORY = r"C:\Dev\Ai.Os"
PREVIEW_LIMIT = 400
SANDBOX_1312_MARKER = "createprocessasuserw failed: 1312"

CommandRunner = Callable[[str, str], dict[str, Any]]

PROTECTED_REQUEST_KEYS = {
    "git_add",
    "git_commit",
    "git_push",
    "merge",
    "scheduler",
    "scheduler_activation",
    "daemon",
    "daemon_activation",
    "worker_dispatch",
    "queue_mutation",
    "approval_mutation",
    "broker",
    "broker_order",
    "broker_live_trading",
    "live_trading",
    "live_execution",
    "credentials",
    "credential_use",
    "real_orders",
    "real_order",
    "real_webhooks",
    "webhook_url",
    "destructive_cleanup",
    "destructive_action",
    "background_runtime",
    "network",
    "network_access",
    "codex_launch",
    "chatgpt_api_call",
    "protected_action_requested",
}

PROTECTED_ATTEMPT_KEYS = {
    "git_add_requested",
    "git_commit_requested",
    "git_push_requested",
    "merge_requested",
    "scheduler_activation_requested",
    "daemon_activation_requested",
    "worker_dispatch_requested",
    "queue_mutation_requested",
    "approval_mutation_requested",
    "broker_live_trading_requested",
    "credentials_requested",
    "real_orders_requested",
    "real_webhooks_requested",
    "destructive_cleanup_requested",
    "background_runtime_requested",
    "network_access_requested",
    "codex_launch_requested",
    "chatgpt_api_call_requested",
}

PRE_EXECUTION_CHECKS = [
    "local_executor_request.requested_true",
    "local_executor_request.mode_ONE_ACTION_LOCAL_APPLY_EXECUTOR",
    "local_executor_request.approved_by_Anthony_Meza",
    "local_executor_request.approval_token_present_true",
    "selected_queue_item_present",
    "apply_approval.approval_status_approved",
    "local_apply_executor_bridge.bridge_status_ready",
    "single_action_executor.executor_status_ready",
    "single_action_executor.command_would_run_true",
    "one_action_execution_controller.controller_status_ready",
    "one_action_execution_controller.command_execution_allowed_true",
    "one_action_apply_runner.runner_status_preview_ready",
    "one_action_apply_runner.command_execution_allowed_true",
    "one_action_execute_gate.gate_status_armed",
    "one_action_execute_gate.execution_gate_decision_one_action_execution_armed",
    "one_action_execute_gate.command_execution_allowed_true",
    "selected_action_matches_all_components",
    "command_to_run_present",
    "working_directory_present_or_defaulted",
    "allowed_paths_bounded",
    "validators_present",
    "max_files_changed_no_more_than_five",
    "max_repairs_no_more_than_one",
    "protected_actions_blocked",
    "apply_result_verifier.pre_execution_ready_or_passed",
]

PRE_EXECUTION_VERIFIER_REASONS = {"command_not_executed", "validators_missing"}


def _base_safety() -> dict[str, bool]:
    return {
        "executor_only": True,
        "injected_runner_only": True,
        "dry_run_default": True,
        "command_execution_allowed_by_executor": False,
        "command_executed": False,
        "commands_executed": False,
        "command_to_run_executed": False,
        "direct_command_runner_used": False,
        "files_written": False,
        "reports_written": False,
        "network_access": False,
        "codex_launch": False,
        "chatgpt_api_call": False,
        "broker": False,
        "live_trading": False,
        "credentials": False,
        "real_orders": False,
        "real_webhooks": False,
        "scheduler": False,
        "daemon": False,
        "worker_dispatch": False,
        "queue_mutation": False,
        "approval_mutation": False,
        "git_add": False,
        "git_commit": False,
        "git_push": False,
        "merge": False,
        "destructive_action": False,
        "background_runtime": False,
        "protected_action_requested": False,
        "sandbox_1312_blocker": False,
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bounded_path(path_text: str) -> bool:
    parsed = PurePosixPath(path_text)
    return bool(path_text) and "\\" not in path_text and not parsed.is_absolute() and ".." not in parsed.parts


def _normalize_paths(paths: Any) -> list[str]:
    return [str(path) for path in _as_list(paths) if _bounded_path(str(path))]


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output


def _append_once(values: list[str], reason: str) -> None:
    if reason not in values:
        values.append(reason)


def _iter_items(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str, Any]]:
    output: list[tuple[tuple[str, ...], str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            output.append((path, key_text, child))
            output.extend(_iter_items(child, (*path, key_text)))
    elif isinstance(value, list):
        for child in value:
            output.extend(_iter_items(child, path))
    return output


def _payload_text(*payloads: Any) -> str:
    return " ".join(json.dumps(payload, sort_keys=True).lower() for payload in payloads if payload is not None)


def _protected_requested(*payloads: dict[str, Any]) -> bool:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for path, raw_key, value in _iter_items(payload):
            path_lower = {part.lower() for part in path}
            if "protected_actions_blocked" in path_lower or "approval_required" in path_lower:
                continue
            key = raw_key.lower()
            if isinstance(value, dict) and key == "protected_action_flags":
                if any(bool(flag_value) for flag_value in value.values()):
                    return True
            if value is True and (key in PROTECTED_REQUEST_KEYS or key in PROTECTED_ATTEMPT_KEYS):
                return True
    return False


def _collect_safety(*payloads: dict[str, Any]) -> dict[str, bool]:
    safety = _base_safety()
    if SANDBOX_1312_MARKER in _payload_text(*payloads):
        safety["sandbox_1312_blocker"] = True
    if _protected_requested(*payloads):
        safety["protected_action_requested"] = True
    return safety


def _first_action(*values: Any) -> str:
    for value in values:
        action = str(value or "")
        if action and action != "none":
            return action
    return "none"


def _validators(*payloads: dict[str, Any]) -> list[str]:
    for payload in payloads:
        validators = [str(validator) for validator in _as_list(payload.get("validators", [])) if str(validator)]
        if validators:
            return validators
    return []


def _first_int(*values: Any, default: int) -> int:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return default


def _has_int(*values: Any) -> bool:
    for value in values:
        if value in (None, ""):
            continue
        try:
            int(value)
        except (TypeError, ValueError):
            continue
        return True
    return False


def _path_values(payload: dict[str, Any], *keys: str) -> list[str]:
    output: list[str] = []
    for key in keys:
        output.extend(str(path) for path in _as_list(payload.get(key, [])))
    return output


def _path_rejection_reasons(allowed_paths: list[str], *path_groups: list[str]) -> list[str]:
    reasons: list[str] = []
    allowed = set(allowed_paths)
    if not allowed_paths:
        _append_once(reasons, "allowed_paths_missing")
    for raw_paths in path_groups:
        if not raw_paths:
            continue
        normalized = _normalize_paths(raw_paths)
        if len(normalized) != len(raw_paths) or set(normalized) - allowed:
            _append_once(reasons, "requested_paths_outside_allowed_paths")
    return reasons


def _action_alignment_reasons(
    queue_item: dict[str, Any],
    approval: dict[str, Any],
    bridge: dict[str, Any],
    executor: dict[str, Any],
    controller: dict[str, Any],
    runner: dict[str, Any],
    gate: dict[str, Any],
    execution_request: dict[str, Any],
    local_request: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    queue_action = _first_action(queue_item.get("action_id"))
    approval_actions = [
        action
        for action in (
            _first_action(approval.get("requested_action")),
            _first_action(approval.get("selected_queue_action")),
            _first_action(approval.get("action_id")),
        )
        if action != "none"
    ]
    component_actions = [
        _first_action(bridge.get("selected_action")),
        _first_action(executor.get("selected_action")),
        _first_action(controller.get("selected_action")),
        _first_action(runner.get("selected_action")),
        _first_action(gate.get("selected_action")),
    ]
    request_actions = [
        _first_action(execution_request.get("requested_action"), execution_request.get("selected_action"), execution_request.get("action_id")),
        _first_action(local_request.get("requested_action"), local_request.get("selected_action"), local_request.get("action_id")),
    ]

    if queue_action == "none":
        _append_once(reasons, "selected_action_missing")
    if str(approval.get("approval_status", "")) == "approved":
        if not approval_actions or any(action != queue_action for action in approval_actions):
            _append_once(reasons, "selected_action_mismatch")
    if any(action == "none" or action != queue_action for action in component_actions):
        _append_once(reasons, "selected_action_mismatch")
    if any(action != "none" and action != queue_action for action in request_actions):
        _append_once(reasons, "selected_action_mismatch")
    return reasons


def _verifier_gate_reasons(verifier: dict[str, Any]) -> tuple[list[str], list[str]]:
    block_reasons: list[str] = []
    rejection_reasons: list[str] = []
    if not verifier:
        block_reasons.append("apply_result_verifier_missing")
        return block_reasons, rejection_reasons

    verifier_status = str(verifier.get("verifier_status", "blocked"))
    verifier_reasons = [str(reason) for reason in _as_list(verifier.get("rejection_reasons", []))]
    if verifier_status == "blocked":
        if verifier_reasons and set(verifier_reasons) <= PRE_EXECUTION_VERIFIER_REASONS:
            return block_reasons, rejection_reasons
        block_reasons.append("apply_result_verifier_blocked")
    elif verifier_status in {"failed", "rejected"}:
        rejection_reasons.append(f"apply_result_verifier_{verifier_status}")
    elif verifier_status not in {"passed", "ready"}:
        block_reasons.append("apply_result_verifier_unknown_status")
    return block_reasons, rejection_reasons


def _preview(value: Any) -> str:
    return str(value or "")[:PREVIEW_LIMIT]


def _runner_evidence(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _post_execution_evidence(
    *,
    runner_called: bool,
    evidence: dict[str, Any],
    working_directory: str,
) -> dict[str, Any]:
    return {
        "command_runner_called": runner_called,
        "working_directory": working_directory,
        "returncode": evidence.get("returncode") if runner_called else None,
        "changed_files": [str(path) for path in _as_list(evidence.get("changed_files", []))],
        "validators_run": [str(validator) for validator in _as_list(evidence.get("validators_run", []))],
        "stdout_preview": _preview(evidence.get("stdout", "")) if runner_called else "",
        "stderr_preview": _preview(evidence.get("stderr", "")) if runner_called else "",
    }


def build_self_build_one_action_local_apply_executor(
    selected_queue_item: dict[str, Any] | None = None,
    apply_approval: dict[str, Any] | None = None,
    local_apply_executor_bridge: dict[str, Any] | None = None,
    single_action_executor: dict[str, Any] | None = None,
    one_action_execution_controller: dict[str, Any] | None = None,
    one_action_apply_runner: dict[str, Any] | None = None,
    one_action_execute_gate: dict[str, Any] | None = None,
    apply_result_verifier: dict[str, Any] | None = None,
    execution_request: dict[str, Any] | None = None,
    local_executor_request: dict[str, Any] | None = None,
    executor_options: dict[str, Any] | None = None,
    command_runner: CommandRunner | None = None,
    *,
    execution_admission: ExecutionAdmission | None = None,
) -> dict[str, Any]:
    queue_item = _as_dict(selected_queue_item)
    approval = _as_dict(apply_approval)
    bridge = _as_dict(local_apply_executor_bridge)
    executor = _as_dict(single_action_executor)
    controller = _as_dict(one_action_execution_controller)
    runner = _as_dict(one_action_apply_runner)
    gate = _as_dict(one_action_execute_gate)
    verifier = _as_dict(apply_result_verifier)
    execution = _as_dict(execution_request)
    local_request = _as_dict(local_executor_request)
    options = _as_dict(executor_options)

    execute_requested = options.get("execute") is True
    executor_mode = EXECUTE_MODE if execute_requested else DRY_RUN_MODE
    working_directory = str(local_request.get("working_directory") or options.get("working_directory") or DEFAULT_WORKING_DIRECTORY)
    selected_action = _first_action(
        gate.get("selected_action"),
        runner.get("selected_action"),
        controller.get("selected_action"),
        executor.get("selected_action"),
        bridge.get("selected_action"),
        approval.get("selected_queue_action"),
        approval.get("requested_action"),
        local_request.get("requested_action"),
        execution.get("requested_action"),
        queue_item.get("action_id"),
    )
    command_to_run = str(
        gate.get("command_to_run")
        or runner.get("command_to_run")
        or controller.get("command_to_run")
        or executor.get("command_to_run")
        or bridge.get("command_to_run")
        or local_request.get("command_to_run")
        or execution.get("command_to_run")
        or ""
    )
    allowed_paths_raw = [str(path) for path in _as_list(queue_item.get("allowed_paths", []))]
    allowed_paths = _normalize_paths(allowed_paths_raw)
    validators = _validators(queue_item, gate, runner, controller, executor, bridge)
    max_repairs_values = (
        gate.get("max_repairs"),
        runner.get("max_repairs"),
        controller.get("max_repairs"),
        executor.get("max_repairs"),
        bridge.get("max_repairs"),
        queue_item.get("max_repairs"),
    )
    max_files_changed_values = (
        gate.get("max_files_changed"),
        runner.get("max_files_changed"),
        controller.get("max_files_changed"),
        executor.get("max_files_changed"),
        bridge.get("max_files_changed"),
        verifier.get("max_files_changed"),
        queue_item.get("max_files_changed"),
    )
    max_repairs_present = _has_int(*max_repairs_values)
    max_files_changed_present = _has_int(*max_files_changed_values)
    max_repairs = _first_int(*max_repairs_values, default=1)
    max_files_changed = _first_int(*max_files_changed_values, default=len(allowed_paths) or 1)

    approval_status = str(approval.get("approval_status", "review_required"))
    bridge_status = str(bridge.get("bridge_status", "blocked"))
    single_executor_status = str(executor.get("executor_status", "blocked"))
    controller_status = str(controller.get("controller_status", "blocked"))
    runner_status = str(runner.get("runner_status", "blocked"))
    gate_status = str(gate.get("gate_status", "blocked"))
    gate_decision = str(gate.get("execution_gate_decision", "blocked"))
    safety = _collect_safety(queue_item, approval, bridge, executor, controller, runner, gate, verifier, execution, local_request, options)

    rejection_reasons: list[str] = []
    block_reasons: list[str] = []
    runner_called = False
    runner_evidence: dict[str, Any] = {}

    request_missing = not local_request
    if request_missing:
        block_reasons.append("local_executor_request_missing")
    else:
        if local_request.get("requested") is not True:
            block_reasons.append("local_executor_request_not_requested")
        if str(local_request.get("mode", "")) != LOCAL_EXECUTOR_MODE:
            block_reasons.append("local_executor_request_mode_not_one_action_local_apply_executor")
        if str(local_request.get("approved_by", "")) != APPROVED_BY:
            block_reasons.append("local_executor_request_approved_by_invalid")
        if local_request.get("approval_token_present") is not True:
            block_reasons.append("local_executor_request_approval_token_missing")

    if not queue_item:
        block_reasons.append("selected_queue_item_missing")
    if approval_status != "approved":
        block_reasons.append("apply_approval_not_approved")
    if bridge_status != "ready":
        block_reasons.append("local_apply_bridge_not_ready")
    if single_executor_status != "ready":
        block_reasons.append("single_action_executor_not_ready")
    if executor.get("command_would_run") is not True:
        block_reasons.append("command_would_run_false")
    if controller_status != "ready":
        block_reasons.append("one_action_execution_controller_not_ready")
    if controller.get("command_execution_allowed") is not True:
        block_reasons.append("one_action_execution_controller_not_allowed")
    if runner_status != "preview_ready":
        block_reasons.append("one_action_apply_runner_not_preview_ready")
    if runner.get("command_execution_allowed") is not True:
        block_reasons.append("one_action_apply_runner_not_allowed")
    if gate_status != "armed":
        block_reasons.append("one_action_execute_gate_not_armed")
    if gate_decision != "one_action_execution_armed":
        block_reasons.append("one_action_execute_gate_decision_not_armed")
    if gate.get("command_execution_allowed") is not True:
        block_reasons.append("one_action_execute_gate_not_allowed")
    if execute_requested and command_runner is None:
        block_reasons.append("command_runner_missing_for_execution")
    if safety["sandbox_1312_blocker"]:
        block_reasons.append("sandbox_1312_runner_blocker")

    if not request_missing:
        rejection_reasons.extend(
            _action_alignment_reasons(queue_item, approval, bridge, executor, controller, runner, gate, execution, local_request)
        )
        rejection_reasons.extend(
            _path_rejection_reasons(
                allowed_paths,
                allowed_paths_raw,
                _path_values(approval, "requested_write_paths", "write_paths", "allowed_paths"),
                _path_values(bridge, "allowed_paths"),
                _path_values(executor, "allowed_paths"),
                _path_values(controller, "allowed_paths"),
                _path_values(runner, "allowed_paths"),
                _path_values(gate, "allowed_paths"),
                _path_values(verifier, "allowed_paths", "changed_files", "unexpected_files"),
                _path_values(execution, "requested_write_paths", "write_paths", "allowed_paths", "paths"),
                _path_values(local_request, "requested_write_paths", "write_paths", "allowed_paths", "paths"),
                _path_values(options, "requested_write_paths", "write_paths", "allowed_paths", "paths"),
            )
        )
        if not validators:
            rejection_reasons.append("validators_missing")
        if not command_to_run:
            rejection_reasons.append("command_to_run_missing")
        if not max_files_changed_present:
            rejection_reasons.append("max_files_changed_missing")
        elif max_files_changed > 5:
            rejection_reasons.append("max_files_changed_exceeds_five")
        if not max_repairs_present:
            rejection_reasons.append("max_repairs_missing")
        elif max_repairs > 1:
            rejection_reasons.append("max_repairs_exceeds_one")

    if safety["protected_action_requested"]:
        rejection_reasons.append("protected_action_requested")

    if not request_missing:
        verifier_blocks, verifier_rejections = _verifier_gate_reasons(verifier)
        block_reasons.extend(verifier_blocks)
        rejection_reasons.extend(verifier_rejections)

    rejection_reasons = _dedupe(rejection_reasons)
    block_reasons = _dedupe(block_reasons)
    if not rejection_reasons and not block_reasons and execute_requested and command_runner is not None:
        def admitted_action():
            nonlocal runner_called
            runner_called = True
            return command_runner(command_to_run, working_directory)

        try:
            if not isinstance(execution_admission, ExecutionAdmission):
                raise ClaimError("final_authority_provider_missing")
            invocation = {
                "packet_id": queue_item.get("packet_id"), "goal_id": queue_item.get("goal"),
                "requested_action": selected_action, "command": command_to_run,
                "working_directory": working_directory, "allowed_paths": allowed_paths,
                "blocked_paths": queue_item.get("blocked_paths"), "validator_chain": validators,
                "resource_limits": {"max_repairs": max_repairs, "max_files_changed": max_files_changed},
                "output_roots": queue_item.get("output_roots"), "stop_point": queue_item.get("stop_point"),
            }
            runner_evidence = _runner_evidence(execution_admission.execute(invocation, admitted_action))
        except ClaimError as exc:
            block_reasons.append("final_authority_provider_missing" if str(exc) == "final_authority_provider_missing"
                                 else "final_authority_admission_blocked")
        except Exception as exc:  # pragma: no cover - defensive evidence path
            if runner_called:
                runner_evidence = {"returncode": None, "stdout": "", "stderr": str(exc), "changed_files": []}
                block_reasons.append("command_runner_failed")
            else:
                block_reasons.append("final_authority_admission_blocked")
        if runner_called and not runner_evidence:
            block_reasons.append("command_runner_evidence_missing")
        changed_files = [str(path) for path in _as_list(runner_evidence.get("changed_files", []))]
        if changed_files:
            post_path_reasons = _path_rejection_reasons(allowed_paths, changed_files)
            if post_path_reasons:
                rejection_reasons.append("command_runner_changed_files_outside_allowed_paths")

    rejection_reasons = _dedupe(rejection_reasons)
    block_reasons = _dedupe(block_reasons)
    command_executed = runner_called and bool(runner_evidence) and not block_reasons
    if rejection_reasons:
        executor_status = "rejected"
        next_safe_action = "Stop and repair rejected local executor inputs or post-execution evidence."
    elif block_reasons:
        executor_status = "blocked"
        if safety["sandbox_1312_blocker"]:
            next_safe_action = "Treat sandbox 1312 as a local runner blocker, not a code failure."
        else:
            next_safe_action = "Stop until local executor request, approval, bridge, controller, runner, gate, and injected runner readiness are satisfied."
    elif execute_requested:
        executor_status = "executed"
        next_safe_action = "Injected one-action execution evidence is available. Verify post-execution results before any packaging or protected action."
    else:
        executor_status = "dry_run_ready"
        next_safe_action = "Local executor is dry-run ready. Set execute true only with a separately approved injected command runner."

    command_execution_allowed = executor_status in {"dry_run_ready", "executed"}
    safety["command_execution_allowed_by_executor"] = command_execution_allowed
    safety["direct_command_runner_used"] = runner_called
    safety["command_executed"] = command_executed
    safety["commands_executed"] = command_executed
    safety["command_to_run_executed"] = command_executed

    returncode = runner_evidence.get("returncode") if runner_called else None
    return {
        "schema": SCHEMA,
        "executor_status": executor_status,
        "executor_mode": executor_mode,
        "selected_action": selected_action,
        "command_to_run": command_to_run,
        "command_execution_allowed": command_execution_allowed,
        "command_executed": command_executed,
        "command_returncode": returncode,
        "command_stdout_preview": _preview(runner_evidence.get("stdout", "")) if runner_called else "",
        "command_stderr_preview": _preview(runner_evidence.get("stderr", "")) if runner_called else "",
        "allowed_paths": allowed_paths,
        "validators": validators,
        "max_repairs": max_repairs,
        "max_files_changed": max_files_changed,
        "pre_execution_checks": PRE_EXECUTION_CHECKS.copy(),
        "post_execution_evidence": _post_execution_evidence(
            runner_called=runner_called,
            evidence=runner_evidence,
            working_directory=working_directory,
        ),
        "rejection_reasons": rejection_reasons or block_reasons,
        "next_safe_action": next_safe_action,
        "safety": safety,
    }


build_one_action_local_apply_executor = build_self_build_one_action_local_apply_executor
evaluate_self_build_one_action_local_apply_executor = build_self_build_one_action_local_apply_executor


def make_campaign_execution_connection(claim_controller, *, read_claim, read_executor_inputs,
                                       read_verification_inputs, command_runner, read_original_selection):
    """Compose existing owners; callers supply qualified source-code readers.

    No callable or permission is loaded from report JSON. The native publication
    reader remains a separate required connection; a passed comparison cannot
    close an original requirement or qualify Windows enforcement.
    """
    from automation.orchestration.claims.aios_task_claim_control import TaskClaimController, normalize_claim, _claim_contract
    from automation.orchestration.aios_self_build_apply_result_verifier import build_self_build_apply_result_verifier
    from automation.orchestration.aios_repo_state_evidence import campaign_json
    if (type(claim_controller) is not TaskClaimController or not all(callable(reader) for reader in
            (read_claim, read_executor_inputs, read_verification_inputs, command_runner, read_original_selection))):
        raise ClaimError("campaign execution source connections missing")
    fields = {"selected_queue_item", "apply_approval", "local_apply_executor_bridge", "single_action_executor",
              "one_action_execution_controller", "one_action_apply_runner", "one_action_execute_gate",
              "apply_result_verifier", "execution_request", "local_executor_request", "executor_options"}
    def execute(packet):
        try:
            original_packet_json = campaign_json(packet)
            task = packet["packet_id"]
            claim = normalize_claim(read_claim(task))
            inputs = json.loads(campaign_json(read_executor_inputs(task)))
            if type(inputs) is not dict or set(inputs) != fields:
                raise ClaimError("campaign original executor inputs missing")
            if claim["packet_id"] != task or inputs["selected_queue_item"].get("packet_id") != task:
                raise ClaimError("campaign selected task identity changed")
            selected = read_original_selection(task)
            if (type(selected) is not dict or set(selected) != {"packet", "claim", "queue_item"}
                    or campaign_json(selected["packet"]) != original_packet_json
                    or campaign_json(selected["queue_item"]) != campaign_json(inputs["selected_queue_item"])
                    or _claim_contract(normalize_claim(selected["claim"])) != _claim_contract(claim)):
                raise ClaimError("campaign original resolver selection changed")
            # This provider re-reads the original signed permission at dispatch;
            # report flags never replace it, and TEST_ONLY trust stays disabled.
            result = build_self_build_one_action_local_apply_executor(**inputs, command_runner=command_runner,
                execution_admission=ExecutionAdmission(claim_controller, claim))
            original_result_json = campaign_json(result)
            result = json.loads(original_result_json)
            if (result.get("executor_status") != "executed" or result.get("command_executed") is not True
                    or type(result.get("command_returncode")) is not int or result["command_returncode"] != 0):
                return {"status": "BLOCKED", "reason": "Existing local executor refused the action", "execution": result}
            verification = read_verification_inputs(task, json.loads(original_result_json))
            if (type(verification) is not dict
                    or campaign_json(verification.get("selected_queue_item")) != campaign_json(inputs["selected_queue_item"])
                    or campaign_json(verification.get("single_action_executor")) != original_result_json):
                raise ClaimError("campaign original result inputs missing")
            checked = build_self_build_apply_result_verifier(**verification)
            if checked.get("verifier_status") != "passed":
                return {"status": "VALIDATION_FAILED", "reason": "Existing result owner rejected the result", "verification": checked}
            return {"status": "COMPLETE", "execution": result, "verification": checked,
                    "original_requirement_closed": False}
        except (ClaimError, KeyError, TypeError, ValueError) as error:
            return {"status": "BLOCKED", "reason": "Campaign execution connection rejected: " + type(error).__name__}
    return execute


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare one AIOS self-build local APPLY command without default execution.")
    parser.add_argument("--queue-item", default="{}")
    parser.add_argument("--apply-approval", default="{}")
    parser.add_argument("--local-apply-executor-bridge", default="{}")
    parser.add_argument("--single-action-executor", default="{}")
    parser.add_argument("--one-action-execution-controller", default="{}")
    parser.add_argument("--one-action-apply-runner", default="{}")
    parser.add_argument("--one-action-execute-gate", default="{}")
    parser.add_argument("--apply-result-verifier", default="{}")
    parser.add_argument("--execution-request", default="{}")
    parser.add_argument("--local-executor-request", default="{}")
    parser.add_argument("--executor-options", default="{}")
    return parser


def _json_arg(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(
        json.dumps(
            build_self_build_one_action_local_apply_executor(
                _json_arg(args.queue_item),
                _json_arg(args.apply_approval),
                _json_arg(args.local_apply_executor_bridge),
                _json_arg(args.single_action_executor),
                _json_arg(args.one_action_execution_controller),
                _json_arg(args.one_action_apply_runner),
                _json_arg(args.one_action_execute_gate),
                _json_arg(args.apply_result_verifier),
                _json_arg(args.execution_request),
                _json_arg(args.local_executor_request),
                _json_arg(args.executor_options),
                None,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
