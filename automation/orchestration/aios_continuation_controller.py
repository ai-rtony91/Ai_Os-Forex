from __future__ import annotations

import argparse
import json
from typing import Any


SCHEMA = "AIOS_CONTINUATION_CONTROLLER.v1"

PRODUCTIVE_EXECUTOR_ACTIONS = {"build_forex_risk_controls"}
HARD_SAFETY_FLAGS = {
    "broker",
    "live_trading",
    "real_orders",
    "real_webhooks",
    "credentials",
    "scheduler",
    "daemon",
    "worker_dispatch",
    "queue_mutation",
    "approval_mutation",
    "destructive_action",
}


def base_safety() -> dict[str, bool]:
    return {
        "broker": False,
        "live_trading": False,
        "real_orders": False,
        "real_webhooks": False,
        "credentials": False,
        "scheduler": False,
        "daemon": False,
        "worker_dispatch": False,
        "queue_mutation": False,
        "approval_mutation": False,
        "destructive_action": False,
        "git_add": False,
        "git_commit": False,
        "git_push": False,
        "merge": False,
    }


def approval_required(*, human_review: bool = True) -> dict[str, bool]:
    return {
        "human_review": human_review,
        "local_apply": human_review,
        "commit": True,
        "push": True,
        "merge": True,
        "scheduler_activation": True,
        "daemon_activation": True,
        "worker_dispatch": True,
        "queue_mutation": True,
        "approval_mutation": True,
        "broker_live_trading": True,
        "credentials": True,
        "real_orders": True,
        "real_webhooks": True,
    }


def _collect_safety(*contracts: dict[str, Any] | None) -> dict[str, bool]:
    safety = base_safety()
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        source = contract.get("safety", contract.get("safety_summary", {}))
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if key in safety:
                safety[key] = safety[key] or bool(value)
    return safety


def _current_mode(user_goal: str | None, mode_registry: dict[str, Any]) -> str:
    text = str(user_goal or "").lower()
    if "dashboard" in text:
        return "dashboard"
    if "game" in text:
        return "game"
    if "forex" in text or "fx" in text:
        return "forex"
    return str(mode_registry.get("active_mode", "forex")) if isinstance(mode_registry, dict) else "forex"


def _mode_enabled(mode_registry: dict[str, Any], mode_id: str) -> bool:
    modes = mode_registry.get("modes", {}) if isinstance(mode_registry, dict) else {}
    mode = modes.get(mode_id, {}) if isinstance(modes, dict) else {}
    return mode.get("status") == "active_proof_target"


def _next_component(
    resume_state: dict[str, Any],
    control_plane_status: dict[str, Any],
    bounded_executor_handoff: dict[str, Any],
) -> str:
    if control_plane_status.get("next_component") not in {None, "", "unknown"}:
        return str(control_plane_status["next_component"])
    if bounded_executor_handoff.get("next_component") not in {None, "", "unknown"}:
        return str(bounded_executor_handoff["next_component"])
    plan = resume_state.get("next_build_plan", {})
    if isinstance(plan, dict):
        return str(plan.get("next_component", "unknown"))
    return "unknown"


def _autonomous_job_summary(autonomous_job_state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(autonomous_job_state, dict):
        return {
            "available": False,
            "state": "UNAVAILABLE",
            "security_state": "UNKNOWN",
            "allowed": False,
            "stop_reason": "missing",
            "next_safe_action": "Autonomous job continuation evidence is unavailable.",
        }
    security = autonomous_job_state.get("security_snapshot")
    security = security if isinstance(security, dict) else {}
    state = str(autonomous_job_state.get("state") or "UNKNOWN").upper()
    return {
        "available": True,
        "state": state,
        "security_state": str(security.get("overall_state") or "UNKNOWN").upper(),
        "allowed": autonomous_job_state.get("safe_to_continue_without_human") is True and state == "CONTINUE",
        "stop_reason": str(autonomous_job_state.get("stop_reason") or ""),
        "next_safe_action": str(autonomous_job_state.get("next_safe_action") or "Review autonomous job continuation state."),
    }


def build_continuation_controller(
    *,
    resume_state: dict[str, Any] | None = None,
    control_plane_status: dict[str, Any] | None = None,
    bounded_executor_handoff: dict[str, Any] | None = None,
    bounded_executor_ready: dict[str, Any] | None = None,
    mode_registry: dict[str, Any] | None = None,
    user_goal: str | None = None,
    autonomous_job_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resume = resume_state if isinstance(resume_state, dict) else {}
    control = control_plane_status if isinstance(control_plane_status, dict) else {}
    handoff = bounded_executor_handoff if isinstance(bounded_executor_handoff, dict) else {}
    ready = bounded_executor_ready if isinstance(bounded_executor_ready, dict) else {}
    registry = mode_registry if isinstance(mode_registry, dict) else {}

    current_mode = _current_mode(user_goal or resume.get("goal"), registry)
    current_goal = str(resume.get("goal") or control.get("current_goal") or user_goal or "unknown")
    next_component = _next_component(resume, control, handoff)
    allowed_action = str(handoff.get("allowed_action", "none"))
    ready_status = str(ready.get("status", "not_ready"))
    handoff_status = str(handoff.get("handoff_status", "blocked"))
    safety = _collect_safety(resume, control, handoff, ready)
    autonomous = _autonomous_job_summary(autonomous_job_state)
    # This projection never grants signed execution authority.
    progress_event = str(resume.get('progress_event', '')) in {
        'unit_finished', 'batch_finished', 'candidate_dead', 'candidate_rejected',
        'candidate_passed', 'report_written', 'checkpoint_saved', 'stage_finished',
        'context_turn_ended', 'recoverable_retry', 'next_safe_work_ready'}

    if autonomous["state"] == "SOS":
        action_type = "sos_stop"
        continuation_status = "blocked"
        reason_code = "autonomous_job_security_sos"
        codex_packet_required = False
        productive_available = False
        next_action = "Stop for SOS escalation."
        next_safe_action = autonomous["next_safe_action"]
    elif autonomous["state"] == "STOP":
        action_type = "human_review"
        continuation_status = "blocked"
        reason_code = "autonomous_job_stop"
        codex_packet_required = False
        productive_available = False
        next_action = "Stop for human review."
        next_safe_action = autonomous["next_safe_action"]
    elif autonomous["state"] == "REVIEW_REQUIRED":
        action_type = "human_review"
        continuation_status = "human_review_required"
        reason_code = "autonomous_job_review_required"
        codex_packet_required = False
        productive_available = False
        next_action = "Stop for human review."
        next_safe_action = autonomous["next_safe_action"]
    elif any(safety.get(flag) is True for flag in HARD_SAFETY_FLAGS):
        action_type = "sos_stop"
        continuation_status = "blocked"
        reason_code = "safety_blocker_present"
        codex_packet_required = False
        productive_available = False
        next_action = "Stop for SOS escalation."
        next_safe_action = "Stop and escalate safety blocker before continuing AIOS build work."
    elif not _mode_enabled(registry, current_mode):
        action_type = "human_review"
        continuation_status = "human_review_required"
        reason_code = "mode_not_enabled"
        codex_packet_required = False
        productive_available = False
        next_action = "Stop for human review."
        next_safe_action = "Ask Anthony to approve or define the requested AIOS mode before continuing."
    elif progress_event and autonomous['allowed']:
        action_type = 'continue_safe_preparation'
        continuation_status = 'ready_to_prepare_packet'
        reason_code = 'normal_progress_is_not_a_stop'
        codex_packet_required = False
        productive_available = False
        next_action = 'prepare next currently allowed work'
        next_safe_action = autonomous['next_safe_action']
    elif handoff_status == "stopped" or next_component == "none":
        action_type = "human_review"
        continuation_status = "human_review_required"
        reason_code = "route_stopped"
        codex_packet_required = False
        productive_available = False
        next_action = "Stop for human review."
        next_safe_action = "Review current scope before preparing another bounded packet."
    elif ready_status == "ready_for_human_review" and allowed_action in PRODUCTIVE_EXECUTOR_ACTIONS:
        action_type = "execute_existing_tool_after_human_approval"
        continuation_status = "ready_for_human_approved_execution"
        reason_code = "productive_executor_support_available"
        codex_packet_required = False
        productive_available = True
        next_action = allowed_action
        next_safe_action = f"After Anthony approval, run the existing productive executor for {allowed_action}."
    elif ready_status == "ready_for_human_review":
        action_type = "build_executor_support_packet"
        continuation_status = "ready_to_prepare_packet"
        reason_code = "productive_executor_support_missing"
        codex_packet_required = True
        productive_available = False
        next_action = f"build executor support for {allowed_action}"
        next_safe_action = (
            f"Prepare a bounded Codex packet to add productive executor support for {allowed_action}. "
            "Do not execute it until Anthony approves."
        )
    else:
        action_type = "human_review"
        continuation_status = "not_ready"
        reason_code = str(ready.get("reason_code", "bounded_executor_not_ready"))
        codex_packet_required = False
        productive_available = False
        next_action = "Stop for human review."
        next_safe_action = "Repair bounded executor readiness before continuing."

    stop_class = None
    if action_type == 'sos_stop':
        stop_class = 'SAFETY_INTEGRITY_BLOCK'
    elif action_type == 'human_review':
        stop_class = 'SAFETY_INTEGRITY_BLOCK' if continuation_status == 'blocked' else 'OWNER_ACTION_REQUIRED'
    return {
        "schema": SCHEMA,
        'stop_reason_class': stop_class,
        'safe_preparation_required': stop_class == 'OWNER_ACTION_REQUIRED',
        'normal_continue_prompt_required': False,
        'execution_authority_granted': False,
        "continuation_status": continuation_status,
        "current_mode": current_mode,
        "current_goal": current_goal,
        "next_component": next_component,
        "next_action": next_action,
        "action_type": action_type,
        "codex_packet_required": codex_packet_required,
        "local_runner_available": bool(handoff_status == "ready" and ready_status == "ready_for_human_review"),
        "productive_executor_available": productive_available,
        "sos_required": action_type == "sos_stop",
        "reason_code": reason_code,
        "next_safe_action": next_safe_action,
        "autonomous_job_continuation_available": autonomous["available"],
        "autonomous_job_continuation_state": autonomous["state"],
        "autonomous_job_security_state": autonomous["security_state"],
        "autonomous_continuation_allowed": autonomous["allowed"],
        "autonomous_job_stop_reason": autonomous["stop_reason"],
        "autonomous_job_next_safe_action": autonomous["next_safe_action"],
        "approval_required": approval_required(human_review=True),
        "safety": safety,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview the AIOS continuation controller contract.")
    parser.add_argument("--action", default="build_forex_paper_execution_simulator")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    controller = build_continuation_controller(
        resume_state={"goal": "forex-paper-bot"},
        control_plane_status={"current_goal": "forex-paper-bot", "next_component": "forex_paper_execution_simulator"},
        bounded_executor_handoff={
            "handoff_status": "ready",
            "next_component": "forex_paper_execution_simulator",
            "allowed_action": args.action,
        },
        bounded_executor_ready={"status": "ready_for_human_review"},
        mode_registry={
            "active_mode": "forex",
            "modes": {"forex": {"status": "active_proof_target"}},
        },
        user_goal="forex-paper-bot",
    )
    print(json.dumps(controller, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
