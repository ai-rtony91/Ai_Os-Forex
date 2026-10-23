from __future__ import annotations

import argparse
import importlib.util
import json
import hashlib
import uuid
from contextlib import nullcontext
from copy import deepcopy
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


SCHEMA = "AIOS_WAKE_CONTINUE.v1"
SUPPORTED_GOALS = {"forex-paper-bot"}

AUTONOMY_EXECUTOR_PATH = Path("automation/orchestration/aios_autonomy_execute.py")
FOREX_BOT_PATH = Path("apps/trading_lab/trading_lab/forex_paper_bot.py")
FOREX_BOT_TEST_PATH = Path("tests/trading_lab/test_forex_paper_bot.py")
FOREX_BACKTEST_PATH = Path("apps/trading_lab/trading_lab/forex_backtest.py")
FOREX_BACKTEST_TEST_PATH = Path("tests/trading_lab/test_forex_backtest.py")
FOREX_LEDGER_PATH = Path("apps/trading_lab/trading_lab/forex_paper_ledger.py")
FOREX_LEDGER_TEST_PATH = Path("tests/trading_lab/test_forex_paper_ledger.py")
FOREX_STRATEGY_PATH = Path("apps/trading_lab/trading_lab/forex_strategy_rules.py")
FOREX_STRATEGY_TEST_PATH = Path("tests/trading_lab/test_forex_strategy_rules.py")
FOREX_DATA_IMPORT_PATH = Path("apps/trading_lab/trading_lab/forex_data_import.py")
FOREX_DATA_IMPORT_TEST_PATH = Path("tests/trading_lab/test_forex_data_import.py")
FOREX_REPORT_PATH = Path("apps/trading_lab/trading_lab/forex_report.py")
FOREX_REPORT_TEST_PATH = Path("tests/trading_lab/test_forex_report.py")
FOREX_DECISION_POLICY_PATH = Path("apps/trading_lab/trading_lab/forex_decision_policy.py")
FOREX_DECISION_POLICY_TEST_PATH = Path("tests/trading_lab/test_forex_decision_policy.py")
FOREX_RISK_CONTROLS_PATH = Path("apps/trading_lab/trading_lab/forex_risk_controls.py")
FOREX_RISK_CONTROLS_TEST_PATH = Path("tests/trading_lab/test_forex_risk_controls.py")
FOREX_PAPER_EXECUTION_SIMULATOR_PATH = Path("apps/trading_lab/trading_lab/forex_paper_execution_simulator.py")
FOREX_PAPER_EXECUTION_SIMULATOR_TEST_PATH = Path("tests/trading_lab/test_forex_paper_execution_simulator.py")
FOREX_EXECUTION_LEDGER_INTEGRATION_PATH = Path("apps/trading_lab/trading_lab/forex_execution_ledger_integration.py")
FOREX_EXECUTION_LEDGER_INTEGRATION_TEST_PATH = Path("tests/trading_lab/test_forex_execution_ledger_integration.py")
FOREX_PORTFOLIO_STATE_PATH = Path("apps/trading_lab/trading_lab/forex_portfolio_state.py")
FOREX_PORTFOLIO_STATE_TEST_PATH = Path("tests/trading_lab/test_forex_portfolio_state.py")
FOREX_PAPER_SESSION_CONTROLLER_PATH = Path("apps/trading_lab/trading_lab/forex_paper_session_controller.py")
FOREX_PAPER_SESSION_CONTROLLER_TEST_PATH = Path("tests/trading_lab/test_forex_paper_session_controller.py")
FOREX_GOAL_DECISION_BRIDGE_PATH = Path("automation/orchestration/aios_forex_goal_decision.py")
NEXT_BUILD_PLAN_ROUTER_PATH = Path("automation/orchestration/aios_next_build_plan.py")
BOUNDED_EXECUTOR_HANDOFF_PATH = Path("automation/orchestration/aios_bounded_executor_handoff.py")
POST_RISK_DECISION_PATH = Path("automation/orchestration/aios_forex_post_risk_decision.py")
RESUME_STATE_PATH = Path("automation/orchestration/aios_resume_state.py")
CLI_RESULT_INGEST_PATH = Path("automation/orchestration/aios_cli_result_ingest.py")
OPERATOR_RELAY_PATH = Path("automation/orchestration/aios_operator_relay.py")
LOCAL_RUNNER_BRIDGE_PATH = Path("automation/orchestration/aios_local_runner_bridge.py")
BOUNDED_EXECUTOR_READY_PATH = Path("automation/orchestration/aios_bounded_executor_ready.py")
CONTROL_PLANE_STATUS_PATH = Path("automation/orchestration/aios_control_plane_status.py")
MODE_CAPABILITY_REGISTRY_PATH = Path("automation/orchestration/aios_mode_capability_registry.py")
BUILD_INTENT_ROUTER_PATH = Path("automation/orchestration/aios_build_intent_router.py")
CONTINUATION_CONTROLLER_PATH = Path("automation/orchestration/aios_continuation_controller.py")
CODEX_PACKET_BUILDER_PATH = Path("automation/orchestration/aios_codex_packet_builder.py")
SOS_ESCALATION_POLICY_PATH = Path("automation/orchestration/aios_sos_escalation_policy.py")
SELF_BUILD_LOOP_READINESS_PATH = Path("automation/orchestration/aios_self_build_loop_readiness.py")
CONTINUATION_APPROVAL_AUTHORITY = (
    "Anthony Meza only approves staging, commit, push, merge, scheduler activation, daemon activation, "
    "worker dispatch, queue mutation, approval mutation, broker/live trading, credentials, real orders, "
    "real webhooks, and destructive actions."
)

CommandRunner = Callable[[list[str], Path], dict[str, Any]]


def safety_flags() -> dict[str, bool]:
    return {
        "git_add": False,
        "git_commit": False,
        "git_push": False,
        "merge": False,
        "delete_reset": False,
        "queue_mutation": False,
        "approval_mutation": False,
        "worker_dispatch": False,
        "runtime_launch": False,
        "scheduler": False,
        "daemon": False,
        "secrets": False,
        "broker": False,
        "live_trading": False,
        "real_orders": False,
    }


def approval_required() -> dict[str, bool]:
    return {
        "local_allowlisted_build": False,
        "commit": True,
        "push": True,
        "merge": True,
        "secrets": True,
        "broker_live_trading": True,
        "scheduler_activation": True,
        "destructive_action": True,
        "queue_mutation": True,
        "approval_mutation": True,
        "worker_dispatch": True,
    }


def read_repo_state(repo_root: Path) -> dict[str, bool]:
    return {
        "autonomy_executor_exists": (repo_root / AUTONOMY_EXECUTOR_PATH).exists(),
        "forex_scaffold_exists": (repo_root / FOREX_BOT_PATH).exists(),
        "forex_scaffold_test_exists": (repo_root / FOREX_BOT_TEST_PATH).exists(),
        "forex_backtest_exists": (repo_root / FOREX_BACKTEST_PATH).exists(),
        "forex_backtest_test_exists": (repo_root / FOREX_BACKTEST_TEST_PATH).exists(),
        "forex_ledger_exists": (repo_root / FOREX_LEDGER_PATH).exists(),
        "forex_ledger_test_exists": (repo_root / FOREX_LEDGER_TEST_PATH).exists(),
        "forex_strategy_exists": (repo_root / FOREX_STRATEGY_PATH).exists(),
        "forex_strategy_test_exists": (repo_root / FOREX_STRATEGY_TEST_PATH).exists(),
        "forex_data_import_exists": (repo_root / FOREX_DATA_IMPORT_PATH).exists(),
        "forex_data_import_test_exists": (repo_root / FOREX_DATA_IMPORT_TEST_PATH).exists(),
        "forex_report_exists": (repo_root / FOREX_REPORT_PATH).exists(),
        "forex_report_test_exists": (repo_root / FOREX_REPORT_TEST_PATH).exists(),
        "forex_decision_policy_exists": (repo_root / FOREX_DECISION_POLICY_PATH).exists(),
        "forex_decision_policy_test_exists": (repo_root / FOREX_DECISION_POLICY_TEST_PATH).exists(),
        "forex_risk_controls_exists": (repo_root / FOREX_RISK_CONTROLS_PATH).exists(),
        "forex_risk_controls_test_exists": (repo_root / FOREX_RISK_CONTROLS_TEST_PATH).exists(),
        "forex_paper_execution_simulator_exists": (repo_root / FOREX_PAPER_EXECUTION_SIMULATOR_PATH).exists(),
        "forex_paper_execution_simulator_test_exists": (repo_root / FOREX_PAPER_EXECUTION_SIMULATOR_TEST_PATH).exists(),
        "forex_execution_ledger_integration_exists": (repo_root / FOREX_EXECUTION_LEDGER_INTEGRATION_PATH).exists(),
        "forex_execution_ledger_integration_test_exists": (
            repo_root / FOREX_EXECUTION_LEDGER_INTEGRATION_TEST_PATH
        ).exists(),
        "forex_portfolio_state_exists": (repo_root / FOREX_PORTFOLIO_STATE_PATH).exists(),
        "forex_portfolio_state_test_exists": (repo_root / FOREX_PORTFOLIO_STATE_TEST_PATH).exists(),
        "forex_paper_session_controller_exists": (repo_root / FOREX_PAPER_SESSION_CONTROLLER_PATH).exists(),
        "forex_paper_session_controller_test_exists": (
            repo_root / FOREX_PAPER_SESSION_CONTROLLER_TEST_PATH
        ).exists(),
    }


def select_next_action(goal: str, repo_state: dict[str, bool]) -> tuple[str, str | None]:
    if goal not in SUPPORTED_GOALS:
        return "blocked", "unsupported_goal"
    if not repo_state["autonomy_executor_exists"]:
        return "blocked", "autonomy_executor_missing"
    if not repo_state["forex_scaffold_exists"]:
        return "build_forex_scaffold", None
    if not repo_state["forex_scaffold_test_exists"]:
        return "blocked", "forex_scaffold_test_missing"
    if not repo_state["forex_backtest_exists"]:
        return "build_forex_backtest", None
    if not repo_state["forex_backtest_test_exists"]:
        return "blocked", "forex_backtest_test_missing"
    if not repo_state["forex_ledger_exists"]:
        return "build_forex_ledger", None
    if not repo_state["forex_ledger_test_exists"]:
        return "blocked", "forex_ledger_test_missing"
    if not repo_state["forex_strategy_exists"]:
        return "build_forex_strategy", None
    if not repo_state["forex_strategy_test_exists"]:
        return "blocked", "forex_strategy_test_missing"
    if not repo_state["forex_data_import_exists"]:
        return "build_forex_data_import", None
    if not repo_state["forex_data_import_test_exists"]:
        return "blocked", "forex_data_import_test_missing"
    if not repo_state["forex_report_exists"]:
        return "build_forex_report", None
    if not repo_state["forex_report_test_exists"]:
        return "blocked", "forex_report_test_missing"
    if not repo_state["forex_decision_policy_exists"]:
        return "build_forex_decision_policy", None
    if not repo_state["forex_decision_policy_test_exists"]:
        return "blocked", "forex_decision_policy_test_missing"
    if repo_state["forex_risk_controls_exists"] != repo_state["forex_risk_controls_test_exists"]:
        return "blocked", "forex_risk_controls_incomplete"
    if repo_state["forex_paper_execution_simulator_exists"] != repo_state["forex_paper_execution_simulator_test_exists"]:
        return "blocked", "forex_paper_execution_simulator_incomplete"
    if repo_state["forex_execution_ledger_integration_exists"] != repo_state["forex_execution_ledger_integration_test_exists"]:
        return "blocked", "forex_execution_ledger_integration_incomplete"
    if repo_state["forex_portfolio_state_exists"] != repo_state["forex_portfolio_state_test_exists"]:
        return "blocked", "forex_portfolio_state_incomplete"
    if repo_state["forex_paper_session_controller_exists"] != repo_state["forex_paper_session_controller_test_exists"]:
        return "blocked", "forex_paper_session_controller_incomplete"
    if repo_state["forex_risk_controls_exists"]:
        if repo_state["forex_paper_execution_simulator_exists"]:
            if repo_state["forex_execution_ledger_integration_exists"]:
                if repo_state["forex_portfolio_state_exists"]:
                    if repo_state["forex_paper_session_controller_exists"]:
                        return "validate_all_forex_with_session_controller", None
                    return "validate_all_forex_with_portfolio_state", None
                return "validate_all_forex_with_execution_ledger_integration", None
            return "validate_all_forex_with_risk_controls_and_execution_simulator", None
        return "validate_all_forex_with_risk_controls", None
    return "validate_all_forex", None


def command_for_action(action: str, max_repairs: int) -> list[str]:
    if action == "build_forex_scaffold":
        return [
            sys.executable,
            AUTONOMY_EXECUTOR_PATH.as_posix(),
            "--goal",
            "forex-paper-bot",
            "--apply",
            "--max-repairs",
            str(max_repairs),
        ]
    if action in {
        "build_forex_backtest",
        "build_forex_ledger",
        "build_forex_strategy",
        "build_forex_data_import",
        "build_forex_report",
        "build_forex_decision_policy",
    }:
        return [
            sys.executable,
            AUTONOMY_EXECUTOR_PATH.as_posix(),
            "--goal",
            "forex-paper-bot",
            "--continue",
            "--apply",
            "--max-repairs",
            str(max_repairs),
        ]
    if action == "validate_all_forex":
        return [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            FOREX_BOT_TEST_PATH.as_posix(),
            FOREX_BACKTEST_TEST_PATH.as_posix(),
            FOREX_LEDGER_TEST_PATH.as_posix(),
            FOREX_STRATEGY_TEST_PATH.as_posix(),
            FOREX_DATA_IMPORT_TEST_PATH.as_posix(),
            FOREX_REPORT_TEST_PATH.as_posix(),
            FOREX_DECISION_POLICY_TEST_PATH.as_posix(),
        ]
    if action == "validate_all_forex_with_risk_controls":
        return [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            FOREX_BOT_TEST_PATH.as_posix(),
            FOREX_BACKTEST_TEST_PATH.as_posix(),
            FOREX_LEDGER_TEST_PATH.as_posix(),
            FOREX_STRATEGY_TEST_PATH.as_posix(),
            FOREX_DATA_IMPORT_TEST_PATH.as_posix(),
            FOREX_REPORT_TEST_PATH.as_posix(),
            FOREX_DECISION_POLICY_TEST_PATH.as_posix(),
            FOREX_RISK_CONTROLS_TEST_PATH.as_posix(),
        ]
    if action == "validate_all_forex_with_risk_controls_and_execution_simulator":
        return [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            FOREX_BOT_TEST_PATH.as_posix(),
            FOREX_BACKTEST_TEST_PATH.as_posix(),
            FOREX_LEDGER_TEST_PATH.as_posix(),
            FOREX_STRATEGY_TEST_PATH.as_posix(),
            FOREX_DATA_IMPORT_TEST_PATH.as_posix(),
            FOREX_REPORT_TEST_PATH.as_posix(),
            FOREX_DECISION_POLICY_TEST_PATH.as_posix(),
            FOREX_RISK_CONTROLS_TEST_PATH.as_posix(),
            FOREX_PAPER_EXECUTION_SIMULATOR_TEST_PATH.as_posix(),
        ]
    if action == "validate_all_forex_with_execution_ledger_integration":
        return [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            FOREX_BOT_TEST_PATH.as_posix(),
            FOREX_BACKTEST_TEST_PATH.as_posix(),
            FOREX_LEDGER_TEST_PATH.as_posix(),
            FOREX_STRATEGY_TEST_PATH.as_posix(),
            FOREX_DATA_IMPORT_TEST_PATH.as_posix(),
            FOREX_REPORT_TEST_PATH.as_posix(),
            FOREX_DECISION_POLICY_TEST_PATH.as_posix(),
            FOREX_RISK_CONTROLS_TEST_PATH.as_posix(),
            FOREX_PAPER_EXECUTION_SIMULATOR_TEST_PATH.as_posix(),
            FOREX_EXECUTION_LEDGER_INTEGRATION_TEST_PATH.as_posix(),
        ]
    if action == "validate_all_forex_with_portfolio_state":
        return [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            FOREX_BOT_TEST_PATH.as_posix(),
            FOREX_BACKTEST_TEST_PATH.as_posix(),
            FOREX_LEDGER_TEST_PATH.as_posix(),
            FOREX_STRATEGY_TEST_PATH.as_posix(),
            FOREX_DATA_IMPORT_TEST_PATH.as_posix(),
            FOREX_REPORT_TEST_PATH.as_posix(),
            FOREX_DECISION_POLICY_TEST_PATH.as_posix(),
            FOREX_RISK_CONTROLS_TEST_PATH.as_posix(),
            FOREX_PAPER_EXECUTION_SIMULATOR_TEST_PATH.as_posix(),
            FOREX_EXECUTION_LEDGER_INTEGRATION_TEST_PATH.as_posix(),
            FOREX_PORTFOLIO_STATE_TEST_PATH.as_posix(),
        ]
    if action == "validate_all_forex_with_session_controller":
        return [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            FOREX_BOT_TEST_PATH.as_posix(),
            FOREX_BACKTEST_TEST_PATH.as_posix(),
            FOREX_LEDGER_TEST_PATH.as_posix(),
            FOREX_STRATEGY_TEST_PATH.as_posix(),
            FOREX_DATA_IMPORT_TEST_PATH.as_posix(),
            FOREX_REPORT_TEST_PATH.as_posix(),
            FOREX_DECISION_POLICY_TEST_PATH.as_posix(),
            FOREX_RISK_CONTROLS_TEST_PATH.as_posix(),
            FOREX_PAPER_EXECUTION_SIMULATOR_TEST_PATH.as_posix(),
            FOREX_EXECUTION_LEDGER_INTEGRATION_TEST_PATH.as_posix(),
            FOREX_PORTFOLIO_STATE_TEST_PATH.as_posix(),
            FOREX_PAPER_SESSION_CONTROLLER_TEST_PATH.as_posix(),
        ]
    raise ValueError(f"unsupported action: {action}")


def default_command_runner(command: list[str], repo_root: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def build_goal_decision(repo_root: Path, goal: str) -> dict[str, Any]:
    bridge_path = Path(__file__).with_name("aios_forex_goal_decision.py")
    spec = importlib.util.spec_from_file_location("aios_forex_goal_decision", bridge_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_FOREX_GOAL_DECISION.v1",
            "goal": goal,
            "decision_bridge_passed": False,
            "decision": "stop_for_human_review",
            "reason_code": "goal_decision_bridge_unavailable",
            "decision_reasons": ["goal_decision_bridge_unavailable"],
            "next_safe_action": "Stop and repair the missing Forex goal decision bridge.",
            "safety": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_goal_decision(repo_root, goal=goal)


def component_inventory_from_repo_state(repo_state: dict[str, bool]) -> dict[str, bool]:
    return {
        "forex_paper_bot": bool(repo_state.get("forex_scaffold_exists") and repo_state.get("forex_scaffold_test_exists")),
        "forex_backtest": bool(repo_state.get("forex_backtest_exists") and repo_state.get("forex_backtest_test_exists")),
        "forex_paper_ledger": bool(repo_state.get("forex_ledger_exists") and repo_state.get("forex_ledger_test_exists")),
        "forex_strategy_rules": bool(repo_state.get("forex_strategy_exists") and repo_state.get("forex_strategy_test_exists")),
        "forex_data_import": bool(repo_state.get("forex_data_import_exists") and repo_state.get("forex_data_import_test_exists")),
        "forex_report": bool(repo_state.get("forex_report_exists") and repo_state.get("forex_report_test_exists")),
        "forex_decision_policy": bool(repo_state.get("forex_decision_policy_exists") and repo_state.get("forex_decision_policy_test_exists")),
        "forex_risk_controls": bool(repo_state.get("forex_risk_controls_exists") and repo_state.get("forex_risk_controls_test_exists")),
        "forex_paper_execution_simulator": bool(
            repo_state.get("forex_paper_execution_simulator_exists")
            and repo_state.get("forex_paper_execution_simulator_test_exists")
        ),
        "forex_execution_ledger_integration": bool(
            repo_state.get("forex_execution_ledger_integration_exists")
            and repo_state.get("forex_execution_ledger_integration_test_exists")
        ),
        "forex_portfolio_state": bool(
            repo_state.get("forex_portfolio_state_exists")
            and repo_state.get("forex_portfolio_state_test_exists")
        ),
        "forex_paper_session_controller": bool(
            repo_state.get("forex_paper_session_controller_exists")
            and repo_state.get("forex_paper_session_controller_test_exists")
        ),
    }


def build_post_risk_decision(component_inventory: dict[str, bool], goal: str) -> dict[str, Any]:
    decision_path = Path(__file__).with_name("aios_forex_post_risk_decision.py")
    spec = importlib.util.spec_from_file_location("aios_forex_post_risk_decision", decision_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_FOREX_POST_RISK_DECISION.v1",
            "goal": goal,
            "current_component_state": component_inventory,
            "selected_next_component": "none",
            "selected_action": "none",
            "selected_packet_id": "NONE",
            "reason_code": "post_risk_decision_unavailable",
            "decision_reasons": ["post_risk_decision_unavailable"],
            "next_safe_action": "Stop and repair the missing post-risk decision builder.",
            "approval_required": approval_required(),
            "safety": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_post_risk_decision(component_inventory, goal=goal)


def build_next_build_plan(goal_decision: dict[str, Any]) -> dict[str, Any]:
    router_path = Path(__file__).with_name("aios_next_build_plan.py")
    spec = importlib.util.spec_from_file_location("aios_next_build_plan", router_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_NEXT_BUILD_PLAN.v1",
            "goal": goal_decision.get("goal", "forex-paper-bot"),
            "input_decision": goal_decision.get("decision", "invalid_decision"),
            "route": "stop",
            "next_component": "none",
            "next_packet_id": "NONE",
            "reason_code": "next_build_plan_router_unavailable",
            "plan_reasons": ["next_build_plan_router_unavailable"],
            "next_safe_action": "Stop and repair the missing next build plan router.",
            "approval_required": approval_required(),
            "safety": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_next_build_plan(goal_decision)


def build_execution_ledger_integration_plan(goal: str) -> dict[str, Any]:
    return {
        "schema": "AIOS_NEXT_BUILD_PLAN.v1",
        "goal": goal,
        "input_decision": "build_forex_execution_ledger_integration",
        "route": "build_next_paper_component",
        "next_component": "forex_execution_ledger_integration",
        "next_packet_id": "PKT-AIOS-FOREX-EXECUTION-LEDGER-INTEGRATION-APPLY",
        "reason_code": "execution_simulator_validated_ledger_integration_missing",
        "plan_reasons": [
            "execution_simulator_validated_ledger_integration_missing",
            "route:build_next_paper_component",
        ],
        "next_safe_action": "Prepare bounded execution-ledger integration packet for Anthony review.",
        "approval_required": approval_required(),
        "safety": safety_flags(),
    }


def build_portfolio_state_plan(goal: str) -> dict[str, Any]:
    return {
        "schema": "AIOS_NEXT_BUILD_PLAN.v1",
        "goal": goal,
        "input_decision": "build_forex_portfolio_state",
        "route": "build_next_paper_component",
        "next_component": "forex_portfolio_state",
        "next_packet_id": "PKT-AIOS-FOREX-PORTFOLIO-STATE-APPLY",
        "reason_code": "execution_ledger_integration_validated_portfolio_state_missing",
        "plan_reasons": [
            "execution_ledger_integration_validated_portfolio_state_missing",
            "route:build_next_paper_component",
        ],
        "next_safe_action": "Prepare bounded portfolio-state packet for Anthony review.",
        "approval_required": approval_required(),
        "safety": safety_flags(),
    }


def build_session_controller_plan(goal: str) -> dict[str, Any]:
    return {
        "schema": "AIOS_NEXT_BUILD_PLAN.v1",
        "goal": goal,
        "input_decision": "build_forex_paper_session_controller",
        "route": "build_next_paper_component",
        "next_component": "forex_paper_session_controller",
        "next_packet_id": "PKT-AIOS-FOREX-PAPER-SESSION-CONTROLLER-APPLY",
        "reason_code": "portfolio_state_validated_session_controller_missing",
        "plan_reasons": [
            "portfolio_state_validated_session_controller_missing",
            "route:build_next_paper_component",
        ],
        "next_safe_action": "Prepare bounded paper-session controller packet for Anthony review.",
        "approval_required": approval_required(),
        "safety": safety_flags(),
    }


def build_portfolio_state_handoff(next_build_plan: dict[str, Any]) -> dict[str, Any]:
    validators = [
        "python -m pytest -p no:cacheprovider tests/trading_lab/test_forex_portfolio_state.py",
        (
            "python -m pytest -p no:cacheprovider "
            "tests/orchestration/test_aios_productive_bounded_executor.py "
            "tests/orchestration/test_aios_wake_continue.py"
        ),
    ]
    return {
        "schema": "AIOS_BOUNDED_EXECUTOR_HANDOFF.v1",
        "goal": next_build_plan.get("goal", "forex-paper-bot"),
        "input_route": next_build_plan.get("route", "build_next_paper_component"),
        "next_component": "forex_portfolio_state",
        "next_packet_id": "PKT-AIOS-FOREX-PORTFOLIO-STATE-APPLY",
        "handoff_status": "ready",
        "reason_code": next_build_plan.get(
            "reason_code",
            "execution_ledger_integration_validated_portfolio_state_missing",
        ),
        "executor_mode": "local_apply_after_human_review",
        "allowed_action": "build_forex_portfolio_state",
        "allowed_paths": [
            "apps/trading_lab/trading_lab/forex_portfolio_state.py",
            "tests/trading_lab/test_forex_portfolio_state.py",
            "docs/orchestration/AIOS_FOREX_PORTFOLIO_STATE.md",
            "automation/orchestration/aios_productive_bounded_executor.py",
            "tests/orchestration/test_aios_productive_bounded_executor.py",
            "automation/orchestration/aios_wake_continue.py",
            "tests/orchestration/test_aios_wake_continue.py",
        ],
        "validators": validators,
        "command_preview": [
            (
                "python automation/orchestration/aios_productive_bounded_executor.py "
                "--goal forex-paper-bot --action build_forex_portfolio_state --apply --max-repairs 1"
            )
        ],
        "approval_required": approval_required(),
        "safety": safety_flags(),
        "next_safe_action": "Prepare bounded portfolio-state packet for Anthony review.",
    }


def build_session_controller_handoff(next_build_plan: dict[str, Any]) -> dict[str, Any]:
    validators = [
        "python -m pytest -p no:cacheprovider tests/trading_lab/test_forex_paper_session_controller.py",
        (
            "python -m pytest -p no:cacheprovider "
            "tests/orchestration/test_aios_productive_bounded_executor.py "
            "tests/orchestration/test_aios_wake_continue.py"
        ),
    ]
    return {
        "schema": "AIOS_BOUNDED_EXECUTOR_HANDOFF.v1",
        "goal": next_build_plan.get("goal", "forex-paper-bot"),
        "input_route": next_build_plan.get("route", "build_next_paper_component"),
        "next_component": "forex_paper_session_controller",
        "next_packet_id": "PKT-AIOS-FOREX-PAPER-SESSION-CONTROLLER-APPLY",
        "handoff_status": "ready",
        "reason_code": next_build_plan.get(
            "reason_code",
            "portfolio_state_validated_session_controller_missing",
        ),
        "executor_mode": "local_apply_after_human_review",
        "allowed_action": "build_forex_paper_session_controller",
        "allowed_paths": [
            "apps/trading_lab/trading_lab/forex_paper_session_controller.py",
            "tests/trading_lab/test_forex_paper_session_controller.py",
            "docs/orchestration/AIOS_FOREX_PAPER_SESSION_CONTROLLER.md",
            "automation/orchestration/aios_productive_bounded_executor.py",
            "tests/orchestration/test_aios_productive_bounded_executor.py",
            "automation/orchestration/aios_wake_continue.py",
            "tests/orchestration/test_aios_wake_continue.py",
        ],
        "validators": validators,
        "command_preview": [
            (
                "python automation/orchestration/aios_productive_bounded_executor.py "
                "--goal forex-paper-bot --action build_forex_paper_session_controller --apply --max-repairs 1"
            )
        ],
        "approval_required": approval_required(),
        "safety": safety_flags(),
        "next_safe_action": "Prepare bounded paper-session controller packet for Anthony review.",
    }


def build_bounded_executor_handoff(next_build_plan: dict[str, Any]) -> dict[str, Any]:
    if next_build_plan.get("next_component") == "forex_paper_session_controller":
        return build_session_controller_handoff(next_build_plan)
    if next_build_plan.get("next_component") == "forex_portfolio_state":
        return build_portfolio_state_handoff(next_build_plan)
    handoff_path = Path(__file__).with_name("aios_bounded_executor_handoff.py")
    spec = importlib.util.spec_from_file_location("aios_bounded_executor_handoff", handoff_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_BOUNDED_EXECUTOR_HANDOFF.v1",
            "goal": next_build_plan.get("goal", "forex-paper-bot"),
            "input_route": next_build_plan.get("route", "unknown"),
            "next_component": next_build_plan.get("next_component", "unknown"),
            "next_packet_id": next_build_plan.get("next_packet_id", "NONE"),
            "handoff_status": "blocked",
            "reason_code": "bounded_executor_handoff_unavailable",
            "executor_mode": "none",
            "allowed_action": "none",
            "allowed_paths": [],
            "validators": [],
            "command_preview": [],
            "approval_required": approval_required(),
            "safety": safety_flags(),
            "next_safe_action": "Stop and repair the missing bounded executor handoff builder.",
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_bounded_executor_handoff(next_build_plan)


def build_resume_state(wake_report: dict[str, Any]) -> dict[str, Any]:
    resume_path = Path(__file__).with_name("aios_resume_state.py")
    spec = importlib.util.spec_from_file_location("aios_resume_state", resume_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_RESUME_STATE.v1",
            "goal": wake_report.get("goal", "forex-paper-bot"),
            "result": wake_report.get("result", "BLOCKED"),
            "resume_ready": False,
            "resume_reason_code": "resume_state_builder_unavailable",
            "next_safe_action": "Stop and repair the missing resume-state builder.",
            "safety": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_resume_state(wake_report)


def build_cli_result_ingest(cli_report: dict[str, Any]) -> dict[str, Any]:
    ingest_path = Path(__file__).with_name("aios_cli_result_ingest.py")
    spec = importlib.util.spec_from_file_location("aios_cli_result_ingest", ingest_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_CLI_RESULT_INGEST.v1",
            "status": "BLOCKED",
            "validation_passed": False,
            "blockers": ["cli_result_ingest_unavailable"],
            "next_safe_action": "Stop and repair the missing CLI result ingest builder.",
            "safety_summary": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_cli_result_ingest(cli_report)


def build_operator_relay(
    resume_state: dict[str, Any],
    cli_result_ingest: dict[str, Any],
    next_build_plan: dict[str, Any],
) -> dict[str, Any]:
    relay_path = Path(__file__).with_name("aios_operator_relay.py")
    spec = importlib.util.spec_from_file_location("aios_operator_relay", relay_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_OPERATOR_RELAY.v1",
            "relay_status": "blocked",
            "human_action_required": True,
            "codex_prompt_ready": False,
            "next_safe_action": "Stop and repair the missing operator relay builder.",
            "safety": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_operator_relay(resume_state, cli_result_ingest, next_build_plan)


def build_local_runner_bridge(bounded_executor_handoff: dict[str, Any]) -> dict[str, Any]:
    if bounded_executor_handoff.get("allowed_action") == "build_forex_paper_session_controller":
        command = (
            "Set-Location -LiteralPath 'C:\\Dev\\Ai.Os'; "
            "python .\\automation\\orchestration\\aios_productive_bounded_executor.py "
            "--goal forex-paper-bot --action build_forex_paper_session_controller --apply --max-repairs 1"
        )
        return {
            "schema": "AIOS_LOCAL_RUNNER_BRIDGE.v1",
            "runner_status": "preview_ready",
            "command_preview": [command],
            "working_directory": "C:\\Dev\\Ai.Os",
            "validation_commands": bounded_executor_handoff.get("validators", []),
            "forbidden_actions": [
                "git_add",
                "git_commit",
                "git_push",
                "git_merge",
                "scheduler",
                "daemon",
                "worker_dispatch",
                "broker",
                "live_trading",
                "credentials",
                "real_orders",
                "real_webhooks",
            ],
            "approval_required": approval_required(),
            "safety": safety_flags(),
        }
    if bounded_executor_handoff.get("allowed_action") == "build_forex_portfolio_state":
        command = (
            "Set-Location -LiteralPath 'C:\\Dev\\Ai.Os'; "
            "python .\\automation\\orchestration\\aios_productive_bounded_executor.py "
            "--goal forex-paper-bot --action build_forex_portfolio_state --apply --max-repairs 1"
        )
        return {
            "schema": "AIOS_LOCAL_RUNNER_BRIDGE.v1",
            "runner_status": "preview_ready",
            "command_preview": [command],
            "working_directory": "C:\\Dev\\Ai.Os",
            "validation_commands": bounded_executor_handoff.get("validators", []),
            "forbidden_actions": [
                "git_add",
                "git_commit",
                "git_push",
                "git_merge",
                "scheduler",
                "daemon",
                "worker_dispatch",
                "broker",
                "live_trading",
                "credentials",
                "real_orders",
                "real_webhooks",
            ],
            "approval_required": approval_required(),
            "safety": safety_flags(),
        }
    bridge_path = Path(__file__).with_name("aios_local_runner_bridge.py")
    spec = importlib.util.spec_from_file_location("aios_local_runner_bridge", bridge_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_LOCAL_RUNNER_BRIDGE.v1",
            "runner_status": "blocked",
            "command_preview": [],
            "working_directory": str(Path(__file__).resolve().parents[2]),
            "validation_commands": [],
            "forbidden_actions": [],
            "approval_required": approval_required(),
            "safety": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_local_runner_bridge(bounded_executor_handoff)


def build_bounded_executor_ready(bounded_executor_handoff: dict[str, Any]) -> dict[str, Any]:
    if bounded_executor_handoff.get("allowed_action") == "build_forex_paper_session_controller":
        return {
            "schema": "AIOS_BOUNDED_EXECUTOR_READY.v1",
            "goal": bounded_executor_handoff.get("goal", "forex-paper-bot"),
            "status": "ready_for_human_review",
            "reason_code": "session_controller_handoff_bounded_ready",
            "allowed_action": "build_forex_paper_session_controller",
            "allowed_paths_bounded": True,
            "validators_bounded": True,
            "command_execution": False,
            "executed": False,
            "approval_required": approval_required(),
            "safety": safety_flags(),
            "next_safe_action": "Prepare or apply the bounded paper-session controller packet after Anthony approval.",
        }
    if bounded_executor_handoff.get("allowed_action") == "build_forex_portfolio_state":
        return {
            "schema": "AIOS_BOUNDED_EXECUTOR_READY.v1",
            "goal": bounded_executor_handoff.get("goal", "forex-paper-bot"),
            "status": "ready_for_human_review",
            "reason_code": "portfolio_state_handoff_bounded_ready",
            "allowed_action": "build_forex_portfolio_state",
            "allowed_paths_bounded": True,
            "validators_bounded": True,
            "command_execution": False,
            "executed": False,
            "approval_required": approval_required(),
            "safety": safety_flags(),
            "next_safe_action": "Prepare or apply the bounded portfolio-state packet after Anthony approval.",
        }
    ready_path = Path(__file__).with_name("aios_bounded_executor_ready.py")
    spec = importlib.util.spec_from_file_location("aios_bounded_executor_ready", ready_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_BOUNDED_EXECUTOR_READY.v1",
            "status": "blocked",
            "reason_code": "bounded_executor_ready_unavailable",
            "command_execution": False,
            "executed": False,
            "next_safe_action": "Stop and repair the missing bounded executor readiness builder.",
            "safety": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_bounded_executor_ready(bounded_executor_handoff)


def build_control_plane_status(
    resume_state: dict[str, Any],
    cli_result_ingest: dict[str, Any],
    operator_relay: dict[str, Any],
    local_runner_bridge: dict[str, Any],
    bounded_executor_ready: dict[str, Any],
) -> dict[str, Any]:
    status_path = Path(__file__).with_name("aios_control_plane_status.py")
    spec = importlib.util.spec_from_file_location("aios_control_plane_status", status_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_CONTROL_PLANE_STATUS.v1",
            "loop_status": "blocked",
            "resume_ready": False,
            "blockers": ["control_plane_status_unavailable"],
            "dashboard_ready": False,
            "next_action": "Stop and repair the missing control-plane status builder.",
            "safety": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    status = module.build_control_plane_status(
        resume_state=resume_state,
        cli_result_ingest=cli_result_ingest,
        operator_relay=operator_relay,
        local_runner_bridge=local_runner_bridge,
        bounded_executor_ready=bounded_executor_ready,
    )
    if bounded_executor_ready.get("allowed_action") in {
        "build_forex_portfolio_state",
        "build_forex_paper_session_controller",
    }:
        blockers = list(status.get("blockers") or [])
        safety = status.get("safety") or safety_flags()
        unsafe = any(
            bool(safety.get(key))
            for key in [
                "broker",
                "live_trading",
                "real_orders",
                "scheduler",
                "daemon",
                "worker_dispatch",
                "queue_mutation",
                "approval_mutation",
            ]
        )
        if not blockers and not unsafe and resume_state.get("resume_ready") is True:
            next_component = (
                "forex_paper_session_controller"
                if bounded_executor_ready.get("allowed_action") == "build_forex_paper_session_controller"
                else "forex_portfolio_state"
            )
            status["dashboard_ready"] = True
            status["loop_status"] = "ready_for_human_review"
            status["next_component"] = next_component
            status["next_action"] = f"Prepare bounded {next_component.replace('_', '-')} packet for Anthony review."
    return status


def build_mode_capability_registry() -> dict[str, Any]:
    registry_path = Path(__file__).with_name("aios_mode_capability_registry.py")
    spec = importlib.util.spec_from_file_location("aios_mode_capability_registry", registry_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_MODE_CAPABILITY_REGISTRY.v1",
            "active_mode": "forex",
            "active_goal": "forex-paper-bot",
            "modes": {},
            "reason_code": "mode_capability_registry_unavailable",
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_mode_capability_registry()


def build_intent_route(
    user_goal: str,
    resume_state: dict[str, Any],
    control_plane_status: dict[str, Any],
    mode_registry: dict[str, Any],
) -> dict[str, Any]:
    router_path = Path(__file__).with_name("aios_build_intent_router.py")
    spec = importlib.util.spec_from_file_location("aios_build_intent_router", router_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_BUILD_INTENT_ROUTER.v1",
            "detected_mode": "unknown",
            "detected_goal": "unknown",
            "proof_target": False,
            "route_status": "needs_human_clarification",
            "next_action": "Stop and repair the missing build-intent router.",
            "reason_code": "build_intent_router_unavailable",
            "safety": safety_flags(),
            "approval_required": approval_required(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.route_build_intent(user_goal, resume_state, control_plane_status, mode_registry)


def build_continuation_controller(
    resume_state: dict[str, Any],
    control_plane_status: dict[str, Any],
    bounded_executor_handoff: dict[str, Any],
    bounded_executor_ready: dict[str, Any],
    mode_registry: dict[str, Any],
    *,
    user_goal: str,
    autonomous_job_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    controller_path = Path(__file__).with_name("aios_continuation_controller.py")
    spec = importlib.util.spec_from_file_location("aios_continuation_controller", controller_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_CONTINUATION_CONTROLLER.v1",
            "continuation_status": "blocked",
            "current_mode": "unknown",
            "current_goal": user_goal,
            "next_component": "unknown",
            "next_action": "Stop and repair the missing continuation controller.",
            "action_type": "human_review",
            "codex_packet_required": False,
            "local_runner_available": False,
            "productive_executor_available": False,
            "sos_required": False,
            "reason_code": "continuation_controller_unavailable",
            "next_safe_action": "Stop and repair the missing continuation controller.",
            "approval_required": approval_required(),
            "safety": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    controller = module.build_continuation_controller(
        resume_state=resume_state,
        control_plane_status=control_plane_status,
        bounded_executor_handoff=bounded_executor_handoff,
        bounded_executor_ready=bounded_executor_ready,
        mode_registry=mode_registry,
        user_goal=user_goal,
        autonomous_job_state=autonomous_job_state,
    )
    if (
        bounded_executor_handoff.get("allowed_action")
        in {"build_forex_portfolio_state", "build_forex_paper_session_controller"}
        and bounded_executor_ready.get("status") == "ready_for_human_review"
        and controller.get("continuation_status") != "blocked"
        and controller.get("sos_required") is not True
        and not controller.get("invalid_evidence_fields")
        and controller.get("action_type") == "build_executor_support_packet"
        and controller.get("stop_reason_class") is None
        and bounded_executor_handoff.get("handoff_status") == "ready"
    ):
        action = str(bounded_executor_handoff.get("allowed_action"))
        next_component = str(bounded_executor_handoff.get("next_component", "unknown"))
        controller.update(
            {
                "continuation_status": "ready_for_human_approved_execution",
                "next_component": next_component,
                "next_action": action,
                "action_type": "execute_existing_tool_after_human_approval",
                "codex_packet_required": False,
                "local_runner_available": True,
                "productive_executor_available": True,
                "sos_required": False,
                "reason_code": "productive_executor_support_available",
                "next_safe_action": (
                    f"After Anthony approval, run the existing productive executor for {action}."
                ),
            }
        )
    if (controller.get("continuation_status") == "blocked" or controller.get("sos_required") is True
            or controller.get("invalid_evidence_fields")):
        controller["local_runner_available"] = False
        controller["productive_executor_available"] = False
        controller["codex_packet_required"] = False
    return controller


def build_sos_escalation(status: dict[str, Any]) -> dict[str, Any]:
    policy_path = Path(__file__).with_name("aios_sos_escalation_policy.py")
    spec = importlib.util.spec_from_file_location("aios_sos_escalation_policy", policy_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_SOS_ESCALATION_POLICY.v1",
            "sos_required": True,
            "severity": "high",
            "triggers": ["sos_escalation_policy_unavailable"],
            "wake_anthony": True,
            "stop_reason": "sos_escalation_policy_unavailable",
            "next_safe_action": "Stop and repair the missing SOS escalation policy.",
            "safety": safety_flags(),
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_sos_escalation(status)


def build_codex_packet_preview(
    continuation_controller: dict[str, Any],
    mode_registry: dict[str, Any],
    bounded_executor_handoff: dict[str, Any],
) -> dict[str, Any]:
    builder_path = Path(__file__).with_name("aios_codex_packet_builder.py")
    spec = importlib.util.spec_from_file_location("aios_codex_packet_builder", builder_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_CODEX_PACKET_BUILDER.v1",
            "packet_ready": False,
            "packet_id": "NONE",
            "packet_title": "No Codex Packet",
            "identity_header": {},
            "validator_chain": [],
            "write_scope": [],
            "safety_blocks": [],
            "codex_prompt_text": "",
            "reason_code": "codex_packet_builder_unavailable",
            "next_safe_action": "Stop and repair the missing Codex packet builder.",
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_codex_packet_preview(
        continuation_controller,
        mode_registry,
        bounded_executor_handoff,
        approval_authority=CONTINUATION_APPROVAL_AUTHORITY,
    )


def build_self_build_loop_readiness(wake_report: dict[str, Any]) -> dict[str, Any]:
    readiness_path = Path(__file__).with_name("aios_self_build_loop_readiness.py")
    spec = importlib.util.spec_from_file_location("aios_self_build_loop_readiness", readiness_path)
    if spec is None or spec.loader is None:
        return {
            "schema": "AIOS_SELF_BUILD_LOOP_READINESS.v1",
            "readiness_status": "not_ready",
            "current_goal": wake_report.get("goal", "unknown"),
            "latest_validated_chain": wake_report.get("selected_action", "unknown"),
            "tests_passed_count": 0,
            "route_status": "blocked",
            "reason_code": "self_build_loop_readiness_unavailable",
            "missing_capabilities": ["self_build_loop_readiness_module"],
            "next_allowed_self_build_action": "repair_self_build_loop_readiness",
            "codex_packet_required": False,
            "local_runner_available": False,
            "productive_executor_available": False,
            "sos_required": True,
            "protected_actions_blocked": approval_required(),
            "safety": safety_flags(),
            "next_safe_action": "Stop and repair the missing self-build loop readiness gate.",
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_self_build_loop_readiness(wake_report)


def attach_self_build_loop_readiness(report: dict[str, Any]) -> dict[str, Any]:
    readiness = build_self_build_loop_readiness(report)
    report["self_build_loop_readiness"] = readiness
    if readiness.get("reason_code") == "forex_session_chain_complete_review_required":
        report["next_safe_action"] = readiness.get(
            "next_safe_action",
            "Stop Forex feature expansion and review AIOS self-build loop readiness with Anthony.",
        )
    return report


def write_resume_state(repo_root: Path, resume_state: dict[str, Any], resume_state_dir: Path | None) -> dict[str, Any]:
    resume_path = Path(__file__).with_name("aios_resume_state.py")
    spec = importlib.util.spec_from_file_location("aios_resume_state", resume_path)
    if spec is None or spec.loader is None:
        raise ValueError("resume_state_builder_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.write_resume_state(repo_root, resume_state, output_dir=resume_state_dir)


def write_control_plane_status(
    repo_root: Path,
    control_plane_status: dict[str, Any],
    control_plane_dir: Path | None,
) -> dict[str, Any]:
    status_path = Path(__file__).with_name("aios_control_plane_status.py")
    spec = importlib.util.spec_from_file_location("aios_control_plane_status", status_path)
    if spec is None or spec.loader is None:
        raise ValueError("control_plane_status_builder_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.write_control_plane_status(repo_root, control_plane_status, output_dir=control_plane_dir)


def default_state_path() -> Path:
    return Path(tempfile.gettempdir()) / "AIOS_WAKE_CONTINUE_STATE.json"


def base_report(goal: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "goal": goal,
        "selected_action": None,
        "commands_run": [],
        "validators_run": [],
        "repair_attempts": 0,
        "goal_decision": None,
        "post_risk_decision": None,
        "next_build_plan": None,
        "bounded_executor_handoff": None,
        "cli_result_ingest": None,
        "operator_relay": None,
        "local_runner_bridge": None,
        "bounded_executor_ready": None,
        "control_plane_status": None,
        "control_plane_status_path": None,
        "self_build_loop_readiness": None,
        "resume_state": None,
        "resume_state_paths": None,
        "result": "blocked",
        "next_safe_action": "Inspect the blocked reason before continuing.",
        "approval_required": approval_required(),
        "safety": safety_flags(),
    }


def write_state(path: Path, report: dict[str, Any]) -> None:
    owner = resume_owner()
    owner.atomic_write(path, owner.serialized_bytes(report))



def resume_owner():
    spec = importlib.util.spec_from_file_location("aios_resume_state", Path(__file__).with_name("aios_resume_state.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execution_input_snapshot(repo_root: Path) -> dict[str, Any]:
    owner = resume_owner()
    inputs = {}
    for name, relative in globals().items():
        if name.endswith("_PATH") and isinstance(relative, Path) and not relative.is_absolute():
            path = owner.bounded_path(repo_root, relative)
            inputs[relative.as_posix()] = owner.file_hash(path) if path.is_file() else None
    return {"source_hashes": owner.source_identity(), "input_hashes": inputs}


def execution_identity(repo_root: Path, report: dict[str, Any], command: list[str], result: dict[str, Any]) -> dict[str, Any]:
    owner = resume_owner()
    inputs = execution_input_snapshot(repo_root)["input_hashes"]
    successful = owner._sanitize(result)
    return {
        "repo_root": str(owner._resolved_path(repo_root)), "goal": report["goal"],
        "selected_action": report["selected_action"],
        "task_id": owner.content_hash({"goal": report["goal"], "action": report["selected_action"]}),
        "attempt_id": uuid.uuid4().hex, "command": command,
        "source_hashes": owner.source_identity(), "input_hashes": inputs,
        "successful_result": successful, "successful_result_sha256": owner.content_hash(successful),
    }


def _failure(report: dict[str, Any], stage: str, exc: Exception) -> None:
    report["result"] = "BLOCKED"
    if not report.get("finalization", {}).get("errors"):
        report["blocked_reason"] = f"finalization_{stage}_failed"
    report["next_safe_action"] = "Recover only missing finalization from the saved source-bound successful attempt."
    report.setdefault("finalization", {}).setdefault("errors", []).append({"stage": stage, "type": type(exc).__name__, "message": str(exc)})


def finalization_request(repo_root: Path, *, state_path: Path, write_resume: bool, resume_dir: Path | None,
                         write_control: bool, control_dir: Path | None, emit_continuation_controller: bool) -> dict[str, Any]:
    owner = resume_owner()
    requested = {"state_path": owner.bounded_path(repo_root, state_path).relative_to(repo_root).as_posix(),
                 "write_resume": write_resume, "resume_dir": owner._resolve_output_dir(repo_root, resume_dir).relative_to(repo_root).as_posix(),
                 "write_control": write_control, "control_dir": owner.bounded_path(repo_root, control_dir or "Reports/aios_control_plane").relative_to(repo_root).as_posix(),
                 "emit_continuation_controller": emit_continuation_controller}
    owner.requested_projections(repo_root, requested)
    return requested


def capture_finalization(repo_root: Path, report: dict[str, Any], requested: dict[str, Any]) -> dict[str, Any]:
    owner = resume_owner()
    minimal = {key: deepcopy(report[key]) for key in ("schema", "goal", "selected_action", "commands_run", "validators_run", "repair_attempts", "execution_identity", "approval_required", "safety") if key in report}
    # Keep the D03 schema-bound typed flags; redact all payload/bulk output.
    minimal = owner._sanitize(minimal)
    for key in ("approval_required", "safety"):
        minimal[key] = owner._sanitize(report.get(key, {}), typed_metadata=report.get("schema") == SCHEMA, path=(key,))
    path, record = owner.capture_successful_attempt(repo_root, minimal, report["execution_identity"], requested)
    report["finalization"] = {"status": "pending", "errors": [], "candidate_path": path.relative_to(repo_root).as_posix(),
                              "successful_attempt_path": path.relative_to(repo_root).as_posix()}
    return {**record, "attempt_path": path.relative_to(repo_root).as_posix()}


def record_finalization_failure(repo_root: Path, report: dict[str, Any], publication: dict[str, Any] | None,
                                stage: str, exc: Exception, *, _locked=False, _immutable_only=False) -> dict[str, Any]:
    owner = resume_owner()
    _failure(report, stage, exc)
    report.setdefault("finalization", {})["status"] = "incomplete"
    requested = publication["requested"] if publication else None
    if not requested:
        return report
    target = owner._resolve_output_dir(repo_root, requested["resume_dir"])
    try:
        with (nullcontext() if _locked else owner.publication_lock(target)):
            # Never let an outdated attempt's fallback diagnostic damage a newer
            # accepted attempt. The immutable attempt remains usable for diagnosis.
            frontier_valid = False
            try:
                if not _immutable_only:
                    owner.validate_frontier(repo_root, target)
                    frontier_valid = True
            except (OSError, ValueError, TypeError, KeyError) as secondary:
                _failure(report, "failure_frontier", secondary)
            if not _immutable_only and frontier_valid and owner.accepted_revision(target) == publication["predecessor_sha256"]:
                diagnostic = {key: value for key, value in report.items() if key not in {"control_plane_status", "self_build_loop_readiness", "codex_packet_preview"}}
                try:
                    write_state(owner.bounded_path(repo_root, requested["state_path"]), diagnostic)
                except (OSError, ValueError, TypeError, KeyError) as secondary:
                    _failure(report, "failure_state", secondary)
            try:
                diagnostic = {key: value for key, value in report.items() if key not in {"control_plane_status", "self_build_loop_readiness", "codex_packet_preview"}}
                data = owner.serialized_bytes(owner._sanitize(diagnostic))
                failure_path = target / f"AIOS_RESUME_FAILURE_{hashlib.sha256(data).hexdigest()}.json"
                owner.immutable_write(failure_path, data)
                report["finalization"]["failure_path"] = failure_path.relative_to(repo_root).as_posix()
            except (OSError, ValueError, TypeError, KeyError) as secondary:
                _failure(report, "failure_evidence", secondary)
    except Exception as secondary:
        # No fallback write without the owner lock. The prebuilder immutable
        # successful attempt survives even if every later lock/write fails.
        _failure(report, "failure_lock", secondary)

    return report


def persist_finalization(repo_root: Path, report: dict[str, Any], *, state_path: Path,
                         write_resume: bool, resume_dir: Path | None,
                         write_control: bool, control_dir: Path | None,
                         emit_continuation_controller: bool = False,
                         publication: dict[str, Any] | None = None, _locked=False) -> dict[str, Any]:
    owner = resume_owner()
    if publication is None:
        requested = finalization_request(repo_root, state_path=state_path, write_resume=write_resume, resume_dir=resume_dir,
            write_control=write_control, control_dir=control_dir, emit_continuation_controller=emit_continuation_controller)
        publication = capture_finalization(repo_root, report, requested)
    stage = "resume_state"
    target = owner._resolve_output_dir(repo_root, publication["requested"]["resume_dir"])
    try:
        with (nullcontext() if _locked else owner.publication_lock(target)):
            try:
                owner.assert_predecessor(target, publication["predecessor_sha256"], repo_root=repo_root)
                if write_resume:
                    candidate_input = deepcopy(report["resume_state"])
                    candidate_input["publication"] = publication

                    def write_projections(candidate):
                        nonlocal stage
                        report["resume_state"] = candidate
                        report["resume_state_paths"] = candidate["resume_state_paths"]
                        report["finalization"]["candidate_path"] = candidate["resume_state_paths"]["timestamped"]
                        outputs = []
                        archive = repo_root / candidate["resume_state_paths"]["timestamped"]
                        for index, output in enumerate(owner.requested_projections(repo_root, publication["requested"])):
                            path = owner.bounded_path(repo_root, output["path"])
                            if path.exists():
                                data = path.read_bytes()
                                owner.immutable_write(archive.with_name(f"{archive.stem}.prior-{index}-{hashlib.sha256(data).hexdigest()}.json"), data)
                        if write_control:
                            stage = "control_plane"
                            report["control_plane_status"] = write_control_plane_status(repo_root, report["control_plane_status"], control_dir)
                            report["control_plane_status_path"] = report["control_plane_status"]["control_plane_status_path"]
                            path = repo_root / report["control_plane_status_path"]
                            outputs.append({"role": "control", "path": str(path), "sha256": owner.file_hash(path)})
                        stage = "generic_state"
                        report["finalization"]["status"] = "complete"
                        write_state(state_path, report)
                        outputs.append({"role": "generic", "path": str(state_path), "sha256": owner.file_hash(state_path)})
                        stage = "accepted_resume_commit"
                        return outputs

                    accepted = owner.publish_resume_state(repo_root, candidate_input, write_projections, output_dir=resume_dir, _locked=True)
                    report["resume_state"] = accepted
                    report["resume_state_paths"] = accepted["resume_state_paths"]
                else:
                    if write_control:
                        stage = "control_plane"
                        report["control_plane_status"] = write_control_plane_status(repo_root, report["control_plane_status"], control_dir)
                        report["control_plane_status_path"] = report["control_plane_status"]["control_plane_status_path"]
                    stage = "generic_state"
                    report["finalization"]["status"] = "complete"
                    write_state(state_path, report)
                return report
            except (OSError, ValueError, TypeError, KeyError) as exc:
                return record_finalization_failure(repo_root, report, publication, stage, exc, _locked=True)
    except Exception as exc:
        return record_finalization_failure(repo_root, report, publication, "publication_lock", exc, _locked=_locked)


def recover_finalization(repo_root: Path, candidate_path: Path, *, expected_identity: dict[str, Any]) -> dict[str, Any]:
    """Verify archive/current frontier before every write; never run an action."""
    owner = resume_owner()
    try:
        owner.require_object(expected_identity, "checkpoint_expected_identity_invalid")
        path = owner.bounded_path(repo_root, candidate_path)
        path.relative_to(owner._resolve_output_dir(repo_root))
        saved = owner.require_object(json.loads(path.read_bytes()), "checkpoint_recovery_envelope_invalid")
        if saved.get("record_type") == "successful_attempt":
            record = owner.load_successful_attempt(repo_root, path)
            publication = {**record, "attempt_path": path.relative_to(repo_root).as_posix()}
        else:
            archive, _ = owner.checkpoint_bytes(repo_root, saved)
            if archive != path:
                raise ValueError("checkpoint_archive_path_mismatch")
            publication = owner.publication_record(repo_root, saved)
        identity = publication["execution_identity"]
        if identity != expected_identity:
            raise ValueError("checkpoint_expected_identity_mismatch")
        owner.verify_execution_identity(repo_root, identity)
        requested = publication["requested"]
        target = owner._resolve_output_dir(repo_root, requested["resume_dir"])
        with owner.publication_lock(target, create=False):
            latest_path = target / owner.LATEST_FILENAME
            if latest_path.is_file():
                latest = owner.require_object(json.loads(latest_path.read_bytes()), "checkpoint_envelope_invalid")
                current_publication = owner.require_object(latest.get("publication"), "checkpoint_publication_unbound")
                if current_publication.get("execution_identity") == identity:
                    current = owner.load_resume_state(repo_root, output_dir=target, _locked=True)
                    if path.relative_to(repo_root).as_posix() not in {
                            current["resume_state_paths"]["timestamped"], current_publication.get("pending_checkpoint"), current_publication.get("attempt_path")}:
                        raise ValueError("checkpoint_current_candidate_mismatch")
                    generic = next(item for item in current_publication["accepted_outputs"] if item["role"] == "generic")
                    report = owner.require_object(json.loads(owner.bounded_path(repo_root, generic["path"]).read_bytes()), "checkpoint_generic_envelope_invalid")
                    report["resume_state"] = current
                    report["resume_state_paths"] = current["resume_state_paths"]
                    return report
            owner.assert_predecessor(target, publication["predecessor_sha256"], repo_root=repo_root)
            report = deepcopy(publication["finalization_input"])
            report["state_path"] = str(owner.bounded_path(repo_root, requested["state_path"]))
            report["finalization"] = {"status": "pending", "errors": [], "candidate_path": path.relative_to(repo_root).as_posix(),
                                      "successful_attempt_path": publication["attempt_path"]}
            try:
                report = finalize_success(repo_root, report, identity["successful_result"], emit_continuation_controller=requested["emit_continuation_controller"])
            except Exception as exc:
                return record_finalization_failure(repo_root, report, publication, "builders", exc, _locked=True)
            # An accepted archive is never republished; current accepted was
            # handled above and an old accepted archive must fail predecessor.
            clean_publication = {key: value for key, value in publication.items() if key not in {"pending_checkpoint", "accepted_outputs"}}
            return persist_finalization(repo_root, report,
                state_path=owner.bounded_path(repo_root, requested["state_path"]),
                write_resume=requested["write_resume"], resume_dir=Path(requested["resume_dir"]),
                write_control=requested["write_control"], control_dir=Path(requested["control_dir"]),
                emit_continuation_controller=requested["emit_continuation_controller"], publication=clean_publication, _locked=True)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        goal = expected_identity.get("goal", "unknown") if isinstance(expected_identity, dict) else "unknown"
        report = base_report(str(goal))
        report["result"] = "BLOCKED"
        report["blocked_reason"] = str(exc)
        report["next_safe_action"] = "Preserve the candidate and revalidate its source/input/attempt identity before recovery."
        return report


def finalize_success(repo_root: Path, report: dict[str, Any], command_result: dict[str, Any], *, emit_continuation_controller: bool = False) -> dict[str, Any]:
    goal = report["goal"]
    selected_action = report["selected_action"]
    repo_state = read_repo_state(repo_root)
    cli_result_ingest = build_cli_result_ingest(command_result)
    report["cli_result_ingest"] = cli_result_ingest
    goal_decision = build_goal_decision(repo_root, goal)
    report["goal_decision"] = goal_decision
    if not goal_decision.get("decision_bridge_passed", False):
        report["result"] = "blocked"
        report["blocked_reason"] = goal_decision.get("reason_code", "goal_decision_bridge_failed")
        report["next_safe_action"] = goal_decision.get(
            "next_safe_action",
            "Inspect the blocked Forex goal decision bridge output.",
        )
        return report
    if selected_action in {
        "validate_all_forex_with_risk_controls",
        "validate_all_forex_with_risk_controls_and_execution_simulator",
        "validate_all_forex_with_execution_ledger_integration",
        "validate_all_forex_with_portfolio_state",
        "validate_all_forex_with_session_controller",
    }:
        component_inventory = component_inventory_from_repo_state(repo_state)
        post_risk_decision = build_post_risk_decision(component_inventory, goal)
        report["post_risk_decision"] = post_risk_decision
        if (
            selected_action == "validate_all_forex_with_risk_controls_and_execution_simulator"
            and not component_inventory["forex_execution_ledger_integration"]
        ):
            next_build_plan = build_execution_ledger_integration_plan(goal)
        elif (
            selected_action == "validate_all_forex_with_execution_ledger_integration"
            and not component_inventory["forex_portfolio_state"]
        ):
            next_build_plan = build_portfolio_state_plan(goal)
        elif (
            selected_action == "validate_all_forex_with_portfolio_state"
            and not component_inventory["forex_paper_session_controller"]
        ):
            next_build_plan = build_session_controller_plan(goal)
        else:
            next_build_plan = build_next_build_plan(post_risk_decision)
    else:
        next_build_plan = build_next_build_plan(goal_decision)
    report["next_build_plan"] = next_build_plan
    bounded_executor_handoff = build_bounded_executor_handoff(next_build_plan)
    report["bounded_executor_handoff"] = bounded_executor_handoff
    local_runner_bridge = build_local_runner_bridge(bounded_executor_handoff)
    report["local_runner_bridge"] = local_runner_bridge
    bounded_executor_ready = build_bounded_executor_ready(bounded_executor_handoff)
    report["bounded_executor_ready"] = bounded_executor_ready
    handoff_status = bounded_executor_handoff.get("handoff_status")
    if (
        handoff_status == "ready"
        and local_runner_bridge.get("runner_status") == "preview_ready"
        and bounded_executor_ready.get("status") == "ready_for_human_review"
    ):
        report["result"] = "DONE_FOR_CURRENT_GOAL"
    elif handoff_status == "stopped":
        report["result"] = "REVIEW_REQUIRED"
    else:
        report["result"] = "BLOCKED"
        report["blocked_reason"] = bounded_executor_ready.get(
            "reason_code",
            bounded_executor_handoff.get("reason_code", "bounded_executor_handoff_blocked"),
        )
    report["next_safe_action"] = bounded_executor_handoff["next_safe_action"]
    resume_state = build_resume_state(report)
    report["resume_state"] = resume_state
    operator_relay = build_operator_relay(resume_state, cli_result_ingest, next_build_plan)
    report["operator_relay"] = operator_relay
    control_plane_status = build_control_plane_status(
        resume_state,
        cli_result_ingest,
        operator_relay,
        local_runner_bridge,
        bounded_executor_ready,
    )
    report["control_plane_status"] = control_plane_status
    report["next_safe_action"] = control_plane_status.get(
        "next_action",
        bounded_executor_handoff["next_safe_action"],
    )
    if report["result"] == "DONE_FOR_CURRENT_GOAL" and control_plane_status.get("dashboard_ready") is not True:
        report["result"] = "BLOCKED"
        report["blocked_reason"] = "control_plane_not_dashboard_ready"
        resume_state = build_resume_state(report)
        report["resume_state"] = resume_state
        operator_relay = build_operator_relay(resume_state, cli_result_ingest, next_build_plan)
        report["operator_relay"] = operator_relay
        control_plane_status = build_control_plane_status(
            resume_state,
            cli_result_ingest,
            operator_relay,
            local_runner_bridge,
            bounded_executor_ready,
        )
        report["control_plane_status"] = control_plane_status
        report["next_safe_action"] = control_plane_status.get(
            "next_action",
            bounded_executor_handoff["next_safe_action"],
        )
    if emit_continuation_controller:
        mode_capability_registry = build_mode_capability_registry()
        report["mode_capability_registry"] = mode_capability_registry
        intent_route = build_intent_route(
            goal,
            resume_state,
            report["control_plane_status"],
            mode_capability_registry,
        )
        report["build_intent_route"] = intent_route
        continuation_controller = build_continuation_controller(
            resume_state,
            report["control_plane_status"],
            bounded_executor_handoff,
            bounded_executor_ready,
            mode_capability_registry,
            user_goal=goal,
            autonomous_job_state=report.get("autonomous_job_state"),
        )
        report["continuation_controller"] = continuation_controller
        sos_escalation = build_sos_escalation(
            {
                "wake_result": report["result"],
                "blocked_reason": report.get("blocked_reason"),
                "build_intent_route": intent_route,
                "continuation_controller": continuation_controller,
                "control_plane_status": report["control_plane_status"],
                "bounded_executor_ready": bounded_executor_ready,
            }
        )
        report["sos_escalation"] = sos_escalation
        if sos_escalation.get("sos_required") is True:
            report["result"] = "BLOCKED"
            report["blocked_reason"] = sos_escalation.get("stop_reason", "sos_required")
            report["next_safe_action"] = sos_escalation.get(
                "next_safe_action",
                continuation_controller.get("next_safe_action", report["next_safe_action"]),
            )
        else:
            report["next_safe_action"] = continuation_controller.get(
                "next_safe_action",
                report["next_safe_action"],
            )
        if continuation_controller.get("codex_packet_required") is True:
            report["codex_packet_preview"] = build_codex_packet_preview(
                continuation_controller,
                mode_capability_registry,
                bounded_executor_handoff,
            )
    attach_self_build_loop_readiness(report)

    return report


def run_wake_continue(
    repo_root: Path,
    *,
    goal: str,
    apply: bool = False,
    max_cycles: int = 1,
    max_repairs: int = 0,
    state_path: Path | None = None,
    command_runner: CommandRunner | None = None,
    write_resume_state_requested: bool = False,
    resume_state_dir: Path | None = None,
    write_control_plane_status_requested: bool = False,
    control_plane_dir: Path | None = None,
    emit_continuation_controller: bool = False,
    autonomous_job_state: dict[str, Any] | None = None,
    continuation_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = base_report(goal)
    # Current stop evidence is a veto, never positive execution authority.
    # Evaluate it before state discovery, command adapters or output writes.
    if autonomous_job_state is not None or continuation_inputs is not None:
        context = continuation_inputs if isinstance(continuation_inputs, dict) else {}
        controller = build_continuation_controller(
            context.get("resume_state", {}),
            context.get("control_plane_status", {}),
            context.get("bounded_executor_handoff", {}),
            context.get("bounded_executor_ready", {}),
            context.get("mode_registry", {}),
            user_goal=goal, autonomous_job_state=autonomous_job_state,
        )
        report["continuation_controller"] = controller
        if controller.get("stop_reason_class") or controller.get("action_type") in {"human_review", "sos_stop"}:
            report["result"] = "blocked"
            report["blocked_reason"] = controller.get("reason_code", "continuation_preflight_blocked")
            report["stop_reason_class"] = controller.get("stop_reason_class") or "SAFETY_INTEGRITY_BLOCK"
            report["next_safe_action"] = controller.get("next_safe_action", "Reconcile current stop evidence.")
            return report
        # Existing report persistence/recovery owns these immutable input bytes.
        # No finalization request/profile or native API contract is extended.
        report["autonomous_job_state"] = json.loads(json.dumps(autonomous_job_state))
        report["continuation_inputs"] = json.loads(json.dumps(context))
    state_path = state_path or default_state_path()
    report["state_path"] = str(state_path)

    if max_cycles < 1:
        report["blocked_reason"] = "max_cycles_must_be_at_least_one"
        write_state(state_path, report)
        return report
    if max_repairs < 0:
        report["blocked_reason"] = "max_repairs_must_be_non_negative"
        write_state(state_path, report)
        return report

    runner = command_runner or default_command_runner

    for _cycle in range(max_cycles):
        repo_state = read_repo_state(repo_root)
        selected_action, blocked_reason = select_next_action(goal, repo_state)
        report["selected_action"] = selected_action

        if blocked_reason:
            report["blocked_reason"] = blocked_reason
            report["result"] = "blocked"
            write_state(state_path, report)
            return report

        if not apply:
            report["result"] = "preview_only"
            report["next_safe_action"] = "Run with --apply to execute the selected allowlisted action."
            write_state(state_path, report)
            return report

        command = command_for_action(selected_action, max_repairs)
        validated_snapshot = execution_input_snapshot(repo_root)
        command_result = runner(command, repo_root)
        report["commands_run"].append(command_result)
        if selected_action.startswith("validate_"):
            report["validators_run"].append(command_result)

        successful_result = command_result if command_result.get("passed") is True and command_result.get("returncode") == 0 else None
        while successful_result is None and report["repair_attempts"] < max_repairs:
            report["repair_attempts"] += 1
            repair_command = command_for_action("build_forex_decision_policy", max_repairs)
            repair_result = runner(repair_command, repo_root)
            report["commands_run"].append(repair_result)
            if repair_result.get("passed") is not True or repair_result.get("returncode") != 0:
                continue
            validated_snapshot = execution_input_snapshot(repo_root)
            retry_result = runner(command, repo_root)
            report["commands_run"].append(retry_result)
            if selected_action.startswith("validate_"):
                report["validators_run"].append(retry_result)
            if retry_result.get("passed") is True and retry_result.get("returncode") == 0:
                successful_result = retry_result

        if successful_result is not None:
            if selected_action.startswith("build_"):
                continue
            if execution_input_snapshot(repo_root) != validated_snapshot:
                report["result"] = "BLOCKED"
                report["blocked_reason"] = "execution_inputs_changed_during_validation"
                report["next_safe_action"] = "Revalidate the changed inputs before accepting this attempt."
                write_state(state_path, report)
                return report
            report["execution_identity"] = execution_identity(repo_root, report, command, successful_result)
            publication = None
            try:
                requested = finalization_request(repo_root, state_path=state_path, write_resume=write_resume_state_requested,
                    resume_dir=resume_state_dir, write_control=write_control_plane_status_requested, control_dir=control_plane_dir,
                    emit_continuation_controller=emit_continuation_controller)
                publication = capture_finalization(repo_root, report, requested)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                return record_finalization_failure(repo_root, report, publication, "attempt_capture", exc)
            try:
                report = finalize_success(repo_root, report, successful_result, emit_continuation_controller=emit_continuation_controller)
            except Exception as exc:
                return record_finalization_failure(repo_root, report, publication, "builders", exc)
            return persist_finalization(repo_root, report, state_path=state_path,
                write_resume=write_resume_state_requested, resume_dir=resume_state_dir,
                write_control=write_control_plane_status_requested, control_dir=control_plane_dir,
                emit_continuation_controller=emit_continuation_controller, publication=publication)

        report["result"] = "failed"
        report["next_safe_action"] = "Inspect command output before another bounded repair."
        write_state(state_path, report)
        return report

    report["result"] = "max_cycles_reached"
    report["next_safe_action"] = "Run another bounded cycle after reviewing state."
    write_state(state_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one bounded AIOS wake/continue cycle.")
    parser.add_argument("--goal", required=True, help="Supported goal: forex-paper-bot.")
    parser.add_argument("--apply", action="store_true", help="Execute the selected allowlisted action.")
    parser.add_argument("--max-cycles", type=int, default=1, help="Maximum cycles before stopping.")
    parser.add_argument("--max-repairs", type=int, default=0, help="Maximum repair attempts.")
    parser.add_argument("--repo-root", default=None, help="Optional repo root for tests.")
    parser.add_argument("--state-path", default=None, help="Optional JSON state output path.")
    parser.add_argument("--write-resume-state", action="store_true", help="Write sanitized resume state under Reports/aios_resume.")
    parser.add_argument("--resume-state-dir", default=None, help="Optional resume-state output dir under Reports/aios_resume.")
    parser.add_argument("--write-control-plane-status", action="store_true", help="Write control-plane latest status under Reports/aios_control_plane.")
    parser.add_argument("--control-plane-dir", default=None, help="Optional output dir under Reports/aios_control_plane.")
    parser.add_argument("--emit-continuation-controller", action="store_true", help="Include generic continuation-controller state in output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    state_path = Path(args.state_path).resolve() if args.state_path else None
    resume_state_dir = Path(args.resume_state_dir) if args.resume_state_dir else None
    control_plane_dir = Path(args.control_plane_dir) if args.control_plane_dir else None
    report = run_wake_continue(
        repo_root,
        goal=args.goal,
        apply=args.apply,
        max_cycles=args.max_cycles,
        max_repairs=args.max_repairs,
        state_path=state_path,
        write_resume_state_requested=args.write_resume_state,
        resume_state_dir=resume_state_dir,
        write_control_plane_status_requested=args.write_control_plane_status,
        control_plane_dir=control_plane_dir,
        emit_continuation_controller=args.emit_continuation_controller,
    )
    print(json.dumps(report, indent=2, sort_keys=False))
    return 0 if report["result"] in {"DONE_FOR_CURRENT_GOAL", "REVIEW_REQUIRED", "passed", "preview_only", "blocked", "BLOCKED", "max_cycles_reached"} else 1


def capture_native_finalization(repo_root, *, admitted_context, validation_record, requested, native_admission_reader):
    """Capture complete authenticated validation before any projection builder."""
    from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1 as cycle
    owner = resume_owner()
    data = cycle._native_admitted(admitted_context, native_admission_reader)
    if not cycle.strict_json_equal(requested, data["requested"]) or requested.get("write_resume") is not True:
        raise ValueError("native_projection_admission_mismatch")
    owner._native_selected_owner(repo_root, admitted_context, native_admission_reader)
    cycle._verify_native_result(data, validation_record)
    identity = None
    try:
        identity = cycle.native_execution_identity(repo_root, admitted_context, validation_record,
            native_admission_reader=native_admission_reader, live=True)
        minimal = {"schema": "AIOS_NATIVE_FINALIZATION.v1", "execution_identity": identity,
                   "requirement_request": identity["requirement_request"]}
        path, _ = owner.capture_successful_attempt(repo_root, minimal, identity, requested,
            admitted_context=admitted_context, native_admission_reader=native_admission_reader)
    except Exception as exc:
        prepared = getattr(exc, "native_prepared_attempt", None)
        report = {"schema": "AIOS_NATIVE_FINALIZATION.v1", "result": "BLOCKED", "execution_identity": identity,
                  "validation_record": validation_record, "native_context_json": admitted_context.context_json,
                  "finalization": {"status": "incomplete", "errors": []}, "prepared_native_attempt": prepared}
        report = record_finalization_failure(repo_root, report, prepared or {"requested": requested},
            "native_attempt_capture", exc, _immutable_only=True)
        exc.native_failure_report = report
        raise
    return path


def _build_native_projection(attempt):
    return resume_owner()._native_state_semantic(attempt)


def _persist_native_finalization(repo_root, path, *, admitted_context, native_admission_reader):
    owner = resume_owner()
    from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1 as cycle
    attempt = owner._load_native_attempt(repo_root, path, admitted_context=admitted_context,
        native_admission_reader=native_admission_reader, live=False)
    publication = {**attempt, "attempt_path": Path(path).relative_to(repo_root).as_posix()}
    report = {"schema": "AIOS_NATIVE_FINALIZATION.v1", "result": "PENDING",
        "execution_identity": attempt["execution_identity"],
        "finalization": {"status": "pending", "errors": [], "candidate_path": publication["attempt_path"],
                         "successful_attempt_path": publication["attempt_path"]}}
    target = owner._resolve_output_dir(repo_root, attempt["requested"]["resume_dir"])
    try:
        # Readback/noop before freshness checks: historical A must not recheck
        # old target bytes after B legitimately replaced them.
        accepted = owner.load_native_requirement(repo_root, output_dir=target, expected_request=admitted_context.request,
            admitted_context=admitted_context, native_admission_reader=native_admission_reader)
        if accepted is not None:
            report.update(result="COMPLETE", resume_state=accepted)
            report["finalization"]["status"] = "complete"
            return report
        with owner.publication_lock(target):
            owner._native_assert_predecessor(repo_root, target, attempt["predecessor_sha256"])
            owner._verify_native_identity(repo_root, attempt["execution_identity"], admitted_context, native_admission_reader, live=True)
            state = _build_native_projection(attempt)
            state["publication"] = publication
            def write_projections(candidate):
                outputs = []
                projection = owner._native_generic_projection(attempt, candidate)
                for output in owner.requested_projections(repo_root, attempt["requested"]):
                    if output["role"] != "generic":
                        raise ValueError("native_initial_projection_profile_invalid")
                    destination = cycle._native_nonprivate_path(str(repo_root / output["path"]), anchor=cycle.bound_path(str(repo_root)))
                    owner.atomic_write(destination, owner.serialized_bytes(projection))
                    outputs.append({**output, "sha256": owner.file_hash(destination)})
                return outputs
            accepted = owner.publish_resume_state(repo_root, state, write_projections, output_dir=target, _locked=True,
                admitted_context=admitted_context, native_admission_reader=native_admission_reader)
        verified = owner.load_native_requirement(repo_root, output_dir=target, expected_request=admitted_context.request,
            admitted_context=admitted_context, native_admission_reader=native_admission_reader)
        if not cycle.strict_json_equal(accepted, verified):
            raise ValueError("native_committed_readback_mismatch")
        report.update(result="COMPLETE", resume_state=verified)
        report["finalization"]["status"] = "complete"
        return report
    except Exception as exc:
        return record_finalization_failure(repo_root, report, publication, "native_publication", exc, _immutable_only=True)


def publish_native_requirement(repo_root, *, admitted_context, execution_capture_path, execution_capture_sha256,
                               validation_record, requested, native_admission_reader):
    """Finalize only; this function runs neither a provider nor a validator."""
    from automation.orchestration.relay import aios_self_consuming_codex_cycle_v1 as cycle
    owner = resume_owner()
    data = cycle._native_admitted(admitted_context, native_admission_reader)
    expected = data["evidence"]["capture"]
    if str(owner.bounded_path(repo_root, execution_capture_path)) != expected["path"] or execution_capture_sha256 != expected["sha256"]:
        raise ValueError("native_capture_argument_mismatch")
    # This entry receives the caller's complete authentic process/result, not a
    # receipt filename from which process success could be reconstructed.
    path = owner._existing_native_attempt(repo_root, admitted_context=admitted_context, native_admission_reader=native_admission_reader)
    if path is None:
        try:
            path = capture_native_finalization(repo_root, admitted_context=admitted_context, validation_record=validation_record,
                requested=requested, native_admission_reader=native_admission_reader)
        except Exception as exc:
            if hasattr(exc, "native_failure_report"):
                return exc.native_failure_report
            raise
    return _persist_native_finalization(repo_root, path, admitted_context=admitted_context, native_admission_reader=native_admission_reader)


def recover_native_finalization(repo_root, candidate_path, *, admitted_context, native_admission_reader):
    owner = resume_owner()
    cycle = owner._native_cycle()
    target = owner._native_selected_owner(repo_root, admitted_context, native_admission_reader)
    kind = "failure" if Path(candidate_path).name.startswith("AIOS_RESUME_FAILURE_") else "attempt"
    path = owner._native_owner_path(repo_root, candidate_path, target, kind)
    if kind == "failure":
        raw = cycle._native_file(path)
        if path.name != "AIOS_RESUME_FAILURE_" + hashlib.sha256(raw).hexdigest() + ".json":
            raise ValueError("native_failure_evidence_content_mismatch")
        failure = cycle._native_json(raw)
        prepared = failure.get("prepared_native_attempt") if type(failure) is dict else None
        if type(prepared) is not dict or type(prepared.get("attempt_path")) is not str:
            raise ValueError("native_failure_complete_attempt_missing_no_replay")
        record = {key: value for key, value in prepared.items() if key != "attempt_path"}
        path = owner._native_owner_path(repo_root, prepared["attempt_path"], target, "attempt")
        owner._validate_native_attempt_record(repo_root, record, path, admitted_context=admitted_context,
            native_admission_reader=native_admission_reader, live=True)
        with owner.publication_lock(target):
            owner._native_assert_predecessor(repo_root, target, record["predecessor_sha256"])
            owner.immutable_write(path, owner.serialized_bytes(record))
    return _persist_native_finalization(repo_root, path,
        admitted_context=admitted_context, native_admission_reader=native_admission_reader)


if __name__ == "__main__":
    raise SystemExit(main())
