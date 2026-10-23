from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "automation" / "orchestration" / "aios_wake_continue.py"
POLICY_SOURCE_PATH = REPO_ROOT / "apps" / "trading_lab" / "trading_lab" / "forex_decision_policy.py"


def load_module():
    spec = importlib.util.spec_from_file_location("aios_wake_continue", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def seed_executor(repo_root: Path) -> None:
    path = repo_root / "automation" / "orchestration" / "aios_autonomy_execute.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# executor placeholder\n", encoding="utf-8")


def seed_scaffold(repo_root: Path) -> None:
    bot_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_paper_bot.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_paper_bot.py"
    bot_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    bot_path.write_text("# bot placeholder\n", encoding="utf-8")
    test_path.write_text("# test placeholder\n", encoding="utf-8")


def seed_backtest(repo_root: Path) -> None:
    backtest_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_backtest.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_backtest.py"
    backtest_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    backtest_path.write_text("# backtest placeholder\n", encoding="utf-8")
    test_path.write_text("# backtest test placeholder\n", encoding="utf-8")


def seed_ledger(repo_root: Path) -> None:
    ledger_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_paper_ledger.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_paper_ledger.py"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text("# ledger placeholder\n", encoding="utf-8")
    test_path.write_text("# ledger test placeholder\n", encoding="utf-8")


def seed_strategy(repo_root: Path) -> None:
    strategy_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_strategy_rules.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_strategy_rules.py"
    strategy_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    strategy_path.write_text("# strategy placeholder\n", encoding="utf-8")
    test_path.write_text("# strategy test placeholder\n", encoding="utf-8")


def seed_data_import(repo_root: Path) -> None:
    data_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_data_import.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_data_import.py"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text("# data import placeholder\n", encoding="utf-8")
    test_path.write_text("# data import test placeholder\n", encoding="utf-8")


def seed_report(repo_root: Path) -> None:
    report_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_report.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_report.py"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# report placeholder\n", encoding="utf-8")
    test_path.write_text("# report test placeholder\n", encoding="utf-8")


def seed_decision_policy(repo_root: Path) -> None:
    policy_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_decision_policy.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_decision_policy.py"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(POLICY_SOURCE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    test_path.write_text("# decision policy test placeholder\n", encoding="utf-8")


def seed_risk_controls(repo_root: Path) -> None:
    risk_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_risk_controls.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_risk_controls.py"
    risk_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    risk_path.write_text("# risk controls placeholder\n", encoding="utf-8")
    test_path.write_text("# risk controls test placeholder\n", encoding="utf-8")


def seed_execution_simulator(repo_root: Path) -> None:
    simulator_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_paper_execution_simulator.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_paper_execution_simulator.py"
    simulator_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    simulator_path.write_text("# execution simulator placeholder\n", encoding="utf-8")
    test_path.write_text("# execution simulator test placeholder\n", encoding="utf-8")


def seed_execution_ledger_integration(repo_root: Path) -> None:
    integration_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_execution_ledger_integration.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_execution_ledger_integration.py"
    integration_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    integration_path.write_text("# execution ledger integration placeholder\n", encoding="utf-8")
    test_path.write_text("# execution ledger integration test placeholder\n", encoding="utf-8")


def seed_portfolio_state(repo_root: Path) -> None:
    portfolio_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_portfolio_state.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_portfolio_state.py"
    portfolio_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    portfolio_path.write_text("# portfolio state placeholder\n", encoding="utf-8")
    test_path.write_text("# portfolio state test placeholder\n", encoding="utf-8")


def seed_session_controller(repo_root: Path) -> None:
    session_path = repo_root / "apps" / "trading_lab" / "trading_lab" / "forex_paper_session_controller.py"
    test_path = repo_root / "tests" / "trading_lab" / "test_forex_paper_session_controller.py"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text("# paper session controller placeholder\n", encoding="utf-8")
    test_path.write_text("# paper session controller test placeholder\n", encoding="utf-8")


def passing_runner(command: list[str], _repo_root: Path) -> dict[str, object]:
    return {
        "command": " ".join(command),
        "returncode": 0,
        "passed": True,
        "stdout": "",
        "stderr": "",
    }


def test_imports():
    module = load_module()
    assert module.SCHEMA == "AIOS_WAKE_CONTINUE.v1"


def test_unsupported_goal_blocked(tmp_path):
    module = load_module()
    state_path = tmp_path / "state.json"
    report = module.run_wake_continue(
        tmp_path,
        goal="unsupported",
        apply=True,
        max_cycles=1,
        max_repairs=1,
        state_path=state_path,
        command_runner=passing_runner,
    )
    assert report["result"] == "blocked"
    assert report["blocked_reason"] == "unsupported_goal"
    assert state_path.exists()


def test_detects_scaffold_missing_selects_build_action(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    state_path = tmp_path / "state.json"
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=False,
        max_cycles=3,
        max_repairs=1,
        state_path=state_path,
    )
    assert report["result"] == "preview_only"
    assert report["selected_action"] == "build_forex_scaffold"


def test_detects_scaffold_present_selects_backtest_action(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    state_path = tmp_path / "state.json"
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=False,
        max_cycles=3,
        max_repairs=1,
        state_path=state_path,
    )
    assert report["result"] == "preview_only"
    assert report["selected_action"] == "build_forex_backtest"


def test_detects_scaffold_and_backtest_present_selects_ledger_action(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    state_path = tmp_path / "state.json"
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=False,
        max_cycles=3,
        max_repairs=1,
        state_path=state_path,
    )
    assert report["result"] == "preview_only"
    assert report["selected_action"] == "build_forex_ledger"


def test_detects_scaffold_backtest_and_ledger_present_selects_strategy_action(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    state_path = tmp_path / "state.json"
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=False,
        max_cycles=3,
        max_repairs=1,
        state_path=state_path,
    )
    assert report["result"] == "preview_only"
    assert report["selected_action"] == "build_forex_strategy"


def test_detects_prior_forex_components_present_selects_data_import_action(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    state_path = tmp_path / "state.json"
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=False,
        max_cycles=3,
        max_repairs=1,
        state_path=state_path,
    )
    assert report["result"] == "preview_only"
    assert report["selected_action"] == "build_forex_data_import"


def test_detects_data_import_present_selects_report_action(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    state_path = tmp_path / "state.json"
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=False,
        max_cycles=3,
        max_repairs=1,
        state_path=state_path,
    )
    assert report["result"] == "preview_only"
    assert report["selected_action"] == "build_forex_report"


def test_detects_report_present_selects_decision_policy_action(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    state_path = tmp_path / "state.json"
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=False,
        max_cycles=3,
        max_repairs=1,
        state_path=state_path,
    )
    assert report["result"] == "preview_only"
    assert report["selected_action"] == "build_forex_decision_policy"


def test_apply_validate_all_action_returns_done_and_writes_state(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)
    state_path = tmp_path / "state.json"
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=3,
        max_repairs=1,
        state_path=state_path,
        command_runner=passing_runner,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert report["result"] == "DONE_FOR_CURRENT_GOAL"
    assert report["selected_action"] == "validate_all_forex"
    assert report["goal_decision"]["schema"] == "AIOS_FOREX_GOAL_DECISION.v1"
    assert report["goal_decision"]["decision_bridge_passed"] is True
    assert report["goal_decision"]["decision"] == "continue_build"
    assert report["goal_decision"]["reason_code"] == "acceptable_report"
    assert report["goal_decision"]["next_build_recommendation"].startswith("Continue")
    assert report["next_build_plan"]["schema"] == "AIOS_NEXT_BUILD_PLAN.v1"
    assert report["next_build_plan"]["route"] == "build_next_paper_component"
    assert report["next_build_plan"]["next_component"] == "forex_risk_controls"
    assert report["bounded_executor_handoff"]["schema"] == "AIOS_BOUNDED_EXECUTOR_HANDOFF.v1"
    assert report["bounded_executor_handoff"]["handoff_status"] == "ready"
    assert report["bounded_executor_handoff"]["allowed_action"] == "build_forex_risk_controls"
    assert report["cli_result_ingest"]["schema"] == "AIOS_CLI_RESULT_INGEST.v1"
    assert report["local_runner_bridge"]["schema"] == "AIOS_LOCAL_RUNNER_BRIDGE.v1"
    assert report["local_runner_bridge"]["runner_status"] == "preview_ready"
    assert report["bounded_executor_ready"]["schema"] == "AIOS_BOUNDED_EXECUTOR_READY.v1"
    assert report["bounded_executor_ready"]["status"] == "ready_for_human_review"
    assert report["resume_state"]["schema"] == "AIOS_RESUME_STATE.v1"
    assert report["resume_state"]["resume_ready"] is True
    assert report["operator_relay"]["schema"] == "AIOS_OPERATOR_RELAY.v1"
    assert report["operator_relay"]["codex_prompt_ready"] is True
    assert report["control_plane_status"]["schema"] == "AIOS_CONTROL_PLANE_STATUS.v1"
    assert report["control_plane_status"]["dashboard_ready"] is True
    assert report["next_safe_action"] == report["control_plane_status"]["next_action"]
    assert len(report["validators_run"]) == 1
    assert state["schema"] == "AIOS_WAKE_CONTINUE.v1"
    assert state["goal_decision"]["decision"] == "continue_build"
    assert state["next_build_plan"]["next_component"] == "forex_risk_controls"
    assert state["bounded_executor_handoff"]["handoff_status"] == "ready"
    assert report["resume_state_paths"] is None
    # APPLY always retains successful-attempt evidence before fallible builders;
    # an unrequested accepted resume checkpoint is still never published.
    assert list((tmp_path / "Reports/aios_resume").glob("AIOS_RESUME_ATTEMPT_*.json"))
    assert not (tmp_path / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json").exists()
    assert report["control_plane_status_path"] is None
    assert not (tmp_path / "Reports" / "aios_control_plane").exists()


def test_write_resume_state_persists_after_done_when_requested(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=3,
        max_repairs=1,
        state_path=tmp_path / "state.json",
        command_runner=passing_runner,
        write_resume_state_requested=True,
        resume_state_dir=tmp_path / "Reports" / "aios_resume",
        write_control_plane_status_requested=True,
        control_plane_dir=tmp_path / "Reports" / "aios_control_plane",
    )
    assert report["result"] == "DONE_FOR_CURRENT_GOAL"
    assert report["resume_state"]["schema"] == "AIOS_RESUME_STATE.v1"
    assert report["resume_state"]["resume_ready"] is True
    assert report["resume_state_paths"]["timestamped"].startswith("Reports/aios_resume/AIOS_RESUME_STATE_")
    assert report["resume_state_paths"]["latest"] == "Reports/aios_resume/AIOS_RESUME_STATE_latest.json"
    assert (tmp_path / report["resume_state_paths"]["timestamped"]).exists()
    assert (tmp_path / report["resume_state_paths"]["latest"]).exists()
    assert report["control_plane_status"]["dashboard_ready"] is True
    assert report["control_plane_status_path"] == "Reports/aios_control_plane/AIOS_CONTROL_PLANE_STATUS_latest.json"
    assert (tmp_path / report["control_plane_status_path"]).exists()
    assert report["next_safe_action"] == report["control_plane_status"]["next_action"]


def test_validate_all_with_risk_controls_selects_execution_simulator(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)
    seed_risk_controls(tmp_path)
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=3,
        max_repairs=1,
        state_path=tmp_path / "state.json",
        command_runner=passing_runner,
    )
    assert report["result"] == "DONE_FOR_CURRENT_GOAL"
    assert report["selected_action"] == "validate_all_forex_with_risk_controls"
    assert report["post_risk_decision"]["schema"] == "AIOS_FOREX_POST_RISK_DECISION.v1"
    assert report["post_risk_decision"]["selected_next_component"] == "forex_paper_execution_simulator"
    assert report["post_risk_decision"]["selected_action"] == "build_forex_paper_execution_simulator"
    assert report["next_build_plan"]["next_component"] == "forex_paper_execution_simulator"
    assert report["next_build_plan"]["next_packet_id"] == "PKT-AIOS-FOREX-PAPER-EXECUTION-SIMULATOR-CONTINUATION-APPLY"
    assert report["bounded_executor_handoff"]["handoff_status"] == "ready"
    assert report["bounded_executor_handoff"]["allowed_action"] == "build_forex_paper_execution_simulator"
    assert report["bounded_executor_ready"]["status"] == "ready_for_human_review"
    assert report["control_plane_status"]["dashboard_ready"] is True
    assert "paper execution simulator" in report["next_safe_action"]


def test_emit_continuation_controller_includes_packet_preview_for_execution_simulator(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)
    seed_risk_controls(tmp_path)
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=3,
        max_repairs=1,
        state_path=tmp_path / "state.json",
        command_runner=passing_runner,
        emit_continuation_controller=True,
    )
    assert report["result"] == "DONE_FOR_CURRENT_GOAL"
    assert report["mode_capability_registry"]["schema"] == "AIOS_MODE_CAPABILITY_REGISTRY.v1"
    assert report["build_intent_route"]["route_status"] == "ready_for_forex_control_plane"
    assert report["continuation_controller"]["schema"] == "AIOS_CONTINUATION_CONTROLLER.v1"
    assert report["continuation_controller"]["continuation_status"] == "ready_to_prepare_packet"
    assert report["continuation_controller"]["next_component"] == "forex_paper_execution_simulator"
    assert report["continuation_controller"]["codex_packet_required"] is True
    assert report["codex_packet_preview"]["schema"] == "AIOS_CODEX_PACKET_BUILDER.v1"
    assert report["codex_packet_preview"]["packet_ready"] is True
    assert report["codex_packet_preview"]["packet_id"] == "PKT-AIOS-FOREX-PAPER-EXECUTION-SIMULATOR-CONTINUATION-APPLY"
    assert "CODEX-ONLY PROMPT" in report["codex_packet_preview"]["codex_prompt_text"]
    assert report["sos_escalation"]["schema"] == "AIOS_SOS_ESCALATION_POLICY.v1"
    assert report["sos_escalation"]["sos_required"] is False
    assert report["next_safe_action"] == report["continuation_controller"]["next_safe_action"]


def test_validate_all_with_execution_simulator_present_stops_for_review(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)
    seed_risk_controls(tmp_path)
    seed_execution_simulator(tmp_path)
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=3,
        max_repairs=1,
        state_path=tmp_path / "state.json",
        command_runner=passing_runner,
    )
    assert report["result"] == "DONE_FOR_CURRENT_GOAL"
    assert report["selected_action"] == "validate_all_forex_with_risk_controls_and_execution_simulator"
    assert "tests/trading_lab/test_forex_paper_execution_simulator.py" in report["validators_run"][0]["command"]
    assert report["post_risk_decision"]["selected_next_component"] == "none"
    assert report["post_risk_decision"]["reason_code"] == "current_inventory_complete_for_defined_scope"
    assert report["next_build_plan"]["route"] == "build_next_paper_component"
    assert report["next_build_plan"]["next_component"] == "forex_execution_ledger_integration"
    assert report["bounded_executor_handoff"]["handoff_status"] == "ready"
    assert report["bounded_executor_handoff"]["allowed_action"] == "build_forex_execution_ledger_integration"


def test_validate_all_with_execution_ledger_integration_present_stops_for_review(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)
    seed_risk_controls(tmp_path)
    seed_execution_simulator(tmp_path)
    seed_execution_ledger_integration(tmp_path)
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=3,
        max_repairs=1,
        state_path=tmp_path / "state.json",
        command_runner=passing_runner,
    )
    assert report["result"] == "DONE_FOR_CURRENT_GOAL"
    assert report["selected_action"] == "validate_all_forex_with_execution_ledger_integration"
    assert "tests/trading_lab/test_forex_execution_ledger_integration.py" in report["validators_run"][0]["command"]
    assert report["next_build_plan"]["route"] == "build_next_paper_component"
    assert report["next_build_plan"]["next_component"] == "forex_portfolio_state"
    assert report["bounded_executor_handoff"]["handoff_status"] == "ready"
    assert report["bounded_executor_handoff"]["allowed_action"] == "build_forex_portfolio_state"
    assert report["bounded_executor_ready"]["status"] == "ready_for_human_review"
    assert report["control_plane_status"]["dashboard_ready"] is True


def test_validate_all_with_portfolio_state_present_stops_for_review(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)
    seed_risk_controls(tmp_path)
    seed_execution_simulator(tmp_path)
    seed_execution_ledger_integration(tmp_path)
    seed_portfolio_state(tmp_path)
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=3,
        max_repairs=1,
        state_path=tmp_path / "state.json",
        command_runner=passing_runner,
    )
    assert report["result"] == "DONE_FOR_CURRENT_GOAL"
    assert report["selected_action"] == "validate_all_forex_with_portfolio_state"
    assert "tests/trading_lab/test_forex_portfolio_state.py" in report["validators_run"][0]["command"]
    assert report["next_build_plan"]["route"] == "build_next_paper_component"
    assert report["next_build_plan"]["next_component"] == "forex_paper_session_controller"
    assert report["bounded_executor_handoff"]["handoff_status"] == "ready"
    assert report["bounded_executor_handoff"]["allowed_action"] == "build_forex_paper_session_controller"
    assert report["bounded_executor_ready"]["status"] == "ready_for_human_review"
    assert report["control_plane_status"]["dashboard_ready"] is True


def test_validate_all_with_session_controller_present_stops_for_review(tmp_path):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)
    seed_risk_controls(tmp_path)
    seed_execution_simulator(tmp_path)
    seed_execution_ledger_integration(tmp_path)
    seed_portfolio_state(tmp_path)
    seed_session_controller(tmp_path)
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=3,
        max_repairs=1,
        state_path=tmp_path / "state.json",
        command_runner=passing_runner,
    )
    assert report["result"] == "REVIEW_REQUIRED"
    assert report["selected_action"] == "validate_all_forex_with_session_controller"
    assert "tests/trading_lab/test_forex_paper_session_controller.py" in report["validators_run"][0]["command"]
    assert report["next_build_plan"]["route"] == "stop"
    assert report["bounded_executor_handoff"]["handoff_status"] == "stopped"
    assert report["self_build_loop_readiness"]["schema"] == "AIOS_SELF_BUILD_LOOP_READINESS.v1"
    assert report["self_build_loop_readiness"]["readiness_status"] == "review_required"
    assert report["self_build_loop_readiness"]["latest_validated_chain"] == "forex_paper_session_controller"
    assert report["self_build_loop_readiness"]["route_status"] == "stopped_for_review"
    assert (
        report["self_build_loop_readiness"]["reason_code"]
        == "forex_session_chain_complete_review_required"
    )
    assert (
        report["self_build_loop_readiness"]["next_allowed_self_build_action"]
        == "self_build_loop_readiness_review"
    )
    assert "self-build loop readiness" in report["next_safe_action"]


def test_validate_all_stop_route_returns_review_required(tmp_path, monkeypatch):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)

    def stop_decision(_repo_root: Path, goal: str) -> dict[str, object]:
        return {
            "schema": "AIOS_FOREX_GOAL_DECISION.v1",
            "goal": goal,
            "decision_bridge_passed": True,
            "decision": "stop_for_human_review",
            "reason_code": "risk_flags_present",
            "decision_reasons": ["risk_flags_present"],
        }

    monkeypatch.setattr(module, "build_goal_decision", stop_decision)
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=3,
        max_repairs=1,
        state_path=tmp_path / "state.json",
        command_runner=passing_runner,
    )
    assert report["result"] == "REVIEW_REQUIRED"
    assert report["next_build_plan"]["route"] == "stop"
    assert report["next_build_plan"]["next_component"] == "none"
    assert report["bounded_executor_handoff"]["handoff_status"] == "stopped"
    assert report["next_safe_action"] == report["bounded_executor_handoff"]["next_safe_action"]


def test_validate_all_unsupported_handoff_returns_blocked(tmp_path, monkeypatch):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)

    def unsupported_plan(_goal_decision: dict[str, object]) -> dict[str, object]:
        return {
            "schema": "AIOS_NEXT_BUILD_PLAN.v1",
            "goal": "forex-paper-bot",
            "input_decision": "continue_build",
            "route": "build_next_paper_component",
            "next_component": "unsupported_component",
            "next_packet_id": "PKT-AIOS-UNSUPPORTED",
            "reason_code": "acceptable_report",
            "plan_reasons": ["acceptable_report"],
            "next_safe_action": "Unsupported preview.",
        }

    monkeypatch.setattr(module, "build_next_build_plan", unsupported_plan)
    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=3,
        max_repairs=1,
        state_path=tmp_path / "state.json",
        command_runner=passing_runner,
    )
    assert report["result"] == "BLOCKED"
    assert report["bounded_executor_handoff"]["handoff_status"] == "blocked"
    assert report["bounded_executor_handoff"]["reason_code"] == "unsupported_component"
    assert report["next_safe_action"] == report["bounded_executor_handoff"]["next_safe_action"]


def test_max_cycles_respected(tmp_path):
    module = load_module()
    seed_executor(tmp_path)

    def build_without_materializing(command: list[str], _repo_root: Path) -> dict[str, object]:
        return {
            "command": " ".join(command),
            "returncode": 0,
            "passed": True,
            "stdout": "",
            "stderr": "",
        }

    report = module.run_wake_continue(
        tmp_path,
        goal="forex-paper-bot",
        apply=True,
        max_cycles=1,
        max_repairs=0,
        state_path=tmp_path / "state.json",
        command_runner=build_without_materializing,
    )
    assert report["result"] == "max_cycles_reached"
    assert len(report["commands_run"]) == 1


def test_safety_blocks_all_forbidden_actions():
    module = load_module()
    flags = module.safety_flags()
    assert flags
    assert all(value is False for value in flags.values())
    for key in [
        "git_add",
        "git_commit",
        "git_push",
        "merge",
        "delete_reset",
        "queue_mutation",
        "approval_mutation",
        "worker_dispatch",
        "runtime_launch",
        "scheduler",
        "daemon",
        "secrets",
        "broker",
        "live_trading",
        "real_orders",
    ]:
        assert flags[key] is False


def test_source_has_no_forbidden_command_or_ui_paths():
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    assert "apps/dashboard" not in source
    for command in ["git add", "git commit", "git push", "git merge"]:
        assert command not in source


def test_cli_main_writes_state_in_temp_path(tmp_path, capsys):
    module = load_module()
    seed_executor(tmp_path)
    seed_scaffold(tmp_path)
    seed_backtest(tmp_path)
    seed_ledger(tmp_path)
    seed_strategy(tmp_path)
    seed_data_import(tmp_path)
    seed_report(tmp_path)
    seed_decision_policy(tmp_path)
    state_path = tmp_path / "state.json"
    exit_code = module.main(
        [
            "--goal",
            "forex-paper-bot",
            "--repo-root",
            str(tmp_path),
            "--state-path",
            str(state_path),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    report = json.loads(captured.out)
    assert report["result"] == "preview_only"
    assert report["selected_action"] == "validate_all_forex"
    assert state_path.exists()



def publication_fixture(repo_root):
    for seed in (seed_executor, seed_scaffold, seed_backtest, seed_ledger, seed_strategy, seed_data_import, seed_report, seed_decision_policy):
        seed(repo_root)


def test_repaired_validation_runs_the_same_native_finalizer(tmp_path):
    module = load_module()
    publication_fixture(tmp_path)
    calls = []

    def runner(command, repo_root):
        result = passing_runner(command, repo_root)
        calls.append(result)
        if len(calls) == 1:
            result.update(passed=False, returncode=1)
        return result

    report = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True, max_repairs=1,
        state_path=tmp_path / "state.json", command_runner=runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    assert report["result"] == "DONE_FOR_CURRENT_GOAL"
    assert report["repair_attempts"] == 1
    assert len(report["commands_run"]) == 3
    assert report["next_build_plan"]["next_component"] == "forex_risk_controls"
    assert report["bounded_executor_handoff"]["handoff_status"] == "ready"
    assert report["resume_state_paths"]
    assert report["control_plane_status_path"]


def test_native_control_serialization_failure_preserves_accepted_resume(tmp_path, monkeypatch):
    module = load_module()
    publication_fixture(tmp_path)
    first = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=passing_runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    latest = tmp_path / first["resume_state_paths"]["latest"]
    accepted = latest.read_bytes()
    # Separate the known second-resolution collision from this serializer fault.
    import time
    time.sleep(1.1)
    native_builder = module.build_control_plane_status

    def unserializable(*args, **kwargs):
        status = native_builder(*args, **kwargs)
        status["bad_native_value"] = object()
        return status

    monkeypatch.setattr(module, "build_control_plane_status", unserializable)
    failed = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=passing_runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    assert failed["result"] == "BLOCKED"
    assert failed["finalization"]["errors"][0]["stage"] == "control_plane"
    assert latest.read_bytes() == accepted
    assert failed["finalization"]["candidate_path"]


def test_wake_portfolio_wrapper_preserves_core_invalid_safety_evidence():
    module = load_module()
    plan = module.build_portfolio_state_plan("forex-paper-bot")
    handoff = module.build_bounded_executor_handoff(plan)
    ready = module.build_bounded_executor_ready(handoff)
    resume = module.build_resume_state({"schema": module.SCHEMA, "goal": "forex-paper-bot", "result": "DONE_FOR_CURRENT_GOAL", "next_build_plan": plan, "bounded_executor_handoff": handoff})
    resume["safety"]["credentials"] = "false"
    controller = module.build_continuation_controller(resume, {}, handoff, ready, module.build_mode_capability_registry(), user_goal="forex-paper-bot")
    assert controller["reason_code"] == "invalid_safety_evidence"
    assert controller["productive_executor_available"] is False
    assert controller["local_runner_available"] is False



def native_contract(name):
    path = REPO_ROOT / "automation/orchestration" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def saved_relay(repo_root):
    path = repo_root / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json"
    resume = json.loads(path.read_bytes())
    return native_contract("aios_operator_relay").build_operator_relay(resume, {"blockers": []}, repo_root=repo_root)


def test_native_published_bundle_is_read_back_by_actual_relay(tmp_path):
    module = load_module()
    publication_fixture(tmp_path)
    result = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=passing_runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    assert result["result"] == "DONE_FOR_CURRENT_GOAL"
    relay = saved_relay(tmp_path)
    assert relay["codex_prompt_ready"] is True
    assert relay["checkpoint_id"] == result["resume_state"]["checkpoint_id"]
    executor = native_contract("aios_productive_bounded_executor")
    assert executor.validate_handoff_scope("build_forex_risk_controls", result["bounded_executor_handoff"])[0] is True


def test_state_save_failure_blocks_candidate_and_recovery_does_not_run_action(tmp_path, monkeypatch):
    module = load_module()
    publication_fixture(tmp_path)
    calls = []

    def runner(command, root):
        calls.append(tuple(command))
        return passing_runner(command, root)

    first = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    latest = tmp_path / first["resume_state_paths"]["latest"]
    accepted = latest.read_bytes()
    state_writer = module.write_state

    def fail_state(_path, _report):
        raise OSError("owned_state_write_failed")

    monkeypatch.setattr(module, "write_state", fail_state)
    failed = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    assert failed["result"] == "BLOCKED"
    assert [entry["stage"] for entry in failed["finalization"]["errors"]] == ["generic_state", "failure_state"]
    assert latest.read_bytes() == accepted
    old_relay = saved_relay(tmp_path)
    assert old_relay["checkpoint_id"] == first["resume_state"]["checkpoint_id"]
    candidate = tmp_path / failed["finalization"]["candidate_path"]
    assert candidate.exists()
    diagnostic = tmp_path / failed["finalization"]["failure_path"]
    assert json.loads(diagnostic.read_bytes())["finalization"]["errors"] == failed["finalization"]["errors"]
    monkeypatch.setattr(module, "write_state", state_writer)
    recovered = module.recover_finalization(tmp_path, candidate, expected_identity=failed["execution_identity"])
    assert recovered["result"] == "DONE_FOR_CURRENT_GOAL"
    assert len(calls) == 2
    assert recovered["execution_identity"]["attempt_id"] == failed["execution_identity"]["attempt_id"]
    assert saved_relay(tmp_path)["codex_prompt_ready"] is True


def test_recovery_rejects_changed_inputs_without_overwriting_candidate(tmp_path, monkeypatch):
    module = load_module()
    publication_fixture(tmp_path)
    writer = module.write_control_plane_status
    monkeypatch.setattr(module, "write_control_plane_status", lambda *a, **k: (_ for _ in ()).throw(OSError("control_fault")))
    failed = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=passing_runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    candidate = tmp_path / failed["finalization"]["candidate_path"]
    original = candidate.read_bytes()
    (tmp_path / "apps/trading_lab/trading_lab/forex_decision_policy.py").write_text("# changed after validation\n", encoding="utf-8")
    monkeypatch.setattr(module, "write_control_plane_status", writer)
    recovered = module.recover_finalization(tmp_path, candidate, expected_identity=failed["execution_identity"])
    assert recovered["result"] == "BLOCKED"
    assert recovered["blocked_reason"] == "checkpoint_inputs_changed"
    assert candidate.read_bytes() == original
    assert not (tmp_path / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json").exists()



def test_success_cannot_bind_inputs_changed_during_validation(tmp_path):
    module = load_module()
    publication_fixture(tmp_path)

    def changed_inputs(command, root):
        path = root / "apps/trading_lab/trading_lab/forex_strategy_rules.py"
        path.write_text("# altered while the command ran\n", encoding="utf-8")
        return passing_runner(command, root)

    result = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=changed_inputs,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    assert result["result"] == "BLOCKED"
    assert result["blocked_reason"] == "execution_inputs_changed_during_validation"
    assert not (tmp_path / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json").exists()


def test_failed_repair_never_runs_validation_retry_or_accepts_handoff(tmp_path):
    module = load_module()
    publication_fixture(tmp_path)
    calls = []

    def failed(command, root):
        calls.append(tuple(command))
        result = passing_runner(command, root)
        result.update(passed=False, returncode=1)
        return result

    result = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True, max_repairs=1,
        state_path=tmp_path / "state.json", command_runner=failed,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    assert result["result"] == "failed"
    assert len(calls) == 2
    assert result["bounded_executor_handoff"] is None
    assert not (tmp_path / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json").exists()


def test_reader_rejects_pending_candidate_while_native_writes_are_in_flight(tmp_path, monkeypatch):
    module = load_module()
    publication_fixture(tmp_path)
    native = module.write_control_plane_status
    observations = []

    def observe(root, status, output):
        # An uncommitted archive is passed through the actual pure consumer;
        # its boolean cannot advertise readiness without owner readback.
        archives = list((root / "Reports/aios_resume").glob("AIOS_RESUME_STATE_*.json"))
        candidates = [p for p in archives if "." not in p.stem and p.name != "AIOS_RESUME_STATE_latest.json"]
        candidate = json.loads(candidates[0].read_bytes())
        observations.append(native_contract("aios_operator_relay").build_operator_relay(candidate, {"blockers": []}))
        return native(root, status, output)

    monkeypatch.setattr(module, "write_control_plane_status", observe)
    result = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=passing_runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    assert observations[0]["codex_prompt_ready"] is False
    assert result["result"] == "DONE_FOR_CURRENT_GOAL"
    assert saved_relay(tmp_path)["codex_prompt_ready"] is True


def test_native_reader_rejects_changed_projection_and_tampered_receipt(tmp_path):
    module = load_module()
    publication_fixture(tmp_path)
    result = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=passing_runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    state_path = tmp_path / "state.json"
    original = state_path.read_bytes()
    state_path.write_text('{"result":"BLOCKED"}\n', encoding="utf-8")
    assert saved_relay(tmp_path)["codex_prompt_ready"] is False
    state_path.write_bytes(original)
    assert saved_relay(tmp_path)["codex_prompt_ready"] is True
    archive = tmp_path / result["resume_state_paths"]["timestamped"]
    completion = archive.with_name(f"{archive.stem}.completion.json")
    value = json.loads(completion.read_bytes())
    value["checkpoint_id"] = "wrong-attempt"
    completion.write_text(json.dumps(value), encoding="utf-8")
    assert saved_relay(tmp_path)["codex_prompt_ready"] is False


def test_recovery_rejects_wrong_expected_attempt_and_preserves_original(tmp_path, monkeypatch):
    from copy import deepcopy
    module = load_module()
    publication_fixture(tmp_path)
    monkeypatch.setattr(module, "write_control_plane_status", lambda *a, **k: (_ for _ in ()).throw(OSError("control_fault")))
    failed = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=passing_runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    candidate = tmp_path / failed["finalization"]["candidate_path"]
    original = candidate.read_bytes()
    expected = deepcopy(failed["execution_identity"])
    expected["attempt_id"] = "different-attempt"
    rejected = module.recover_finalization(tmp_path, candidate, expected_identity=expected)
    assert rejected["blocked_reason"] == "checkpoint_expected_identity_mismatch"
    assert candidate.read_bytes() == original


def test_session_wrapper_preserves_core_hard_safety_stop():
    module = load_module()
    plan = module.build_session_controller_plan("forex-paper-bot")
    handoff = module.build_bounded_executor_handoff(plan)
    ready = module.build_bounded_executor_ready(handoff)
    resume = module.build_resume_state({"schema": module.SCHEMA, "goal": "forex-paper-bot", "result": "DONE_FOR_CURRENT_GOAL", "next_build_plan": plan, "bounded_executor_handoff": handoff})
    resume["safety"]["broker"] = True
    controller = module.build_continuation_controller(resume, {}, handoff, ready, module.build_mode_capability_registry(), user_goal="forex-paper-bot")
    assert controller["sos_required"] is True
    assert controller["productive_executor_available"] is False
    assert controller["local_runner_available"] is False



def test_resume_recovery_evidence_excludes_command_output_and_payload_secrets(tmp_path):
    module = load_module()
    publication_fixture(tmp_path)

    def output_runner(command, root):
        result = passing_runner(command, root)
        result.update(stdout="private-command-output-sentinel", stderr="private-error-output-sentinel", credentials={"token": "private-payload-sentinel"})
        return result

    report = module.run_wake_continue(tmp_path, goal="forex-paper-bot", apply=True,
        state_path=tmp_path / "state.json", command_runner=output_runner,
        write_resume_state_requested=True, write_control_plane_status_requested=True)
    assert report["result"] == "DONE_FOR_CURRENT_GOAL"
    archive = tmp_path / report["resume_state_paths"]["timestamped"]
    saved = archive.read_text(encoding="utf-8")
    assert "private-command-output-sentinel" not in saved
    assert "private-error-output-sentinel" not in saved
    assert "private-payload-sentinel" not in saved
    assert saved_relay(tmp_path)["codex_prompt_ready"] is True


# Supplemental E06 negatives: actual persisted reader and native builders/writers.
import pytest
from copy import deepcopy


def supplemental_publish(module, root, **kwargs):
    return module.run_wake_continue(root, goal="forex-paper-bot", apply=True,
        state_path=root / "state.json", command_runner=kwargs.pop("command_runner", passing_runner),
        write_resume_state_requested=kwargs.pop("write_resume", True),
        write_control_plane_status_requested=kwargs.pop("write_control", True), **kwargs)


def supplemental_hashes(root):
    paths = [root / "state.json", root / "Reports/aios_control_plane/AIOS_CONTROL_PLANE_STATUS_latest.json",
             root / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json"]
    return {str(path): path.read_bytes() if path.is_file() else None for path in paths}


@pytest.mark.parametrize("removed", [("publication",), ("resume_state_paths",), ("publication", "resume_state_paths")])
def test_supplemental_missing_bindings_never_disable_actual_reader(tmp_path, removed):
    module = load_module(); publication_fixture(tmp_path)
    supplemental_publish(module, tmp_path)
    assert saved_relay(tmp_path)["codex_prompt_ready"] is True
    latest = tmp_path / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json"
    state = json.loads(latest.read_bytes())
    for key in removed: del state[key]
    state["next_build_plan"]["next_component"] = "unbound_mutated_plan"
    latest.write_text(json.dumps(state), encoding="utf-8")
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    relay = saved_relay(tmp_path)
    assert relay["codex_prompt_ready"] is False
    assert relay["publication_error"]
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("corruption", ["omit_generic", "omit_control", "duplicate", "extra", "path", "snapshot", "coordinated_hash"])
def test_supplemental_completion_exact_archive_bound_projection_set(tmp_path, corruption):
    import hashlib
    module = load_module(); publication_fixture(tmp_path)
    result = supplemental_publish(module, tmp_path)
    archive = tmp_path / result["resume_state_paths"]["timestamped"]
    completion = archive.with_name(archive.stem + ".completion.json")
    receipt = json.loads(completion.read_bytes()); outputs = receipt["outputs"]
    generic = next(o for o in outputs if o["path"] == "state.json")
    control = next(o for o in outputs if o["path"].endswith("AIOS_CONTROL_PLANE_STATUS_latest.json"))
    if corruption == "omit_generic":
        (tmp_path / "state.json").write_text('{"result":"BLOCKED"}', encoding="utf-8")
        receipt["outputs"].remove(generic)
    elif corruption == "omit_control": receipt["outputs"].remove(control)
    elif corruption == "duplicate": receipt["outputs"].append(deepcopy(generic))
    elif corruption == "extra":
        extra = deepcopy(generic); extra["path"] = "extra.json"; receipt["outputs"].append(extra)
    elif corruption == "path": generic["path"] = control["path"]
    elif corruption == "snapshot": generic["snapshot"] = control["snapshot"]
    else:
        changed = b'{"result":"BLOCKED"}\n'
        (tmp_path / "state.json").write_bytes(changed)
        (tmp_path / generic["snapshot"]).write_bytes(changed)
        generic["sha256"] = hashlib.sha256(changed).hexdigest()
    completion.write_text(json.dumps(receipt), encoding="utf-8")
    before = supplemental_hashes(tmp_path)
    assert saved_relay(tmp_path)["codex_prompt_ready"] is False
    assert supplemental_hashes(tmp_path) == before


SUPPLEMENTAL_BUILDERS = ["build_cli_result_ingest", "build_goal_decision", "build_next_build_plan",
    "build_bounded_executor_handoff", "build_local_runner_bridge", "build_bounded_executor_ready",
    "build_resume_state", "build_operator_relay", "build_control_plane_status",
    "build_mode_capability_registry", "build_intent_route", "build_continuation_controller",
    "build_sos_escalation", "build_codex_packet_preview", "attach_self_build_loop_readiness"]


@pytest.mark.parametrize("builder", SUPPLEMENTAL_BUILDERS)
@pytest.mark.parametrize("repaired", [False, True])
def test_supplemental_builder_fault_is_durable_and_recovery_never_replays(tmp_path, monkeypatch, builder, repaired):
    module = load_module(); publication_fixture(tmp_path)
    calls = []
    def runner(command, root):
        calls.append(tuple(command)); result = passing_runner(command, root)
        if repaired and len(calls) == 1: result.update(passed=False, returncode=1)
        return result
    if builder == "build_codex_packet_preview": seed_risk_controls(tmp_path)
    native = getattr(module, builder)
    fault_calls = []
    def fault(*args, **kwargs):
        fault_calls.append(builder)
        raise OSError("owned_builder_fault_" + builder)
    monkeypatch.setattr(module, builder, fault)
    failed = supplemental_publish(module, tmp_path, command_runner=runner, max_repairs=int(repaired), emit_continuation_controller=True)
    assert failed["result"] == "BLOCKED"
    assert fault_calls == [builder]
    assert failed["finalization"]["errors"][0]["stage"] == "builders"
    candidate = tmp_path / failed["finalization"]["candidate_path"]
    captured = candidate.read_bytes()
    assert failed["execution_identity"]["attempt_id"].encode() in captured
    assert failed["execution_identity"]["successful_result_sha256"].encode() in captured
    assert len(calls) == (3 if repaired else 1)
    monkeypatch.setattr(module, builder, native)
    recovered = module.recover_finalization(tmp_path, candidate, expected_identity=failed["execution_identity"])
    assert recovered["result"] == "DONE_FOR_CURRENT_GOAL"
    assert len(calls) == (3 if repaired else 1)
    assert candidate.read_bytes() == captured
    assert recovered["execution_identity"] == failed["execution_identity"]
    assert saved_relay(tmp_path)["codex_prompt_ready"] is True


@pytest.mark.parametrize("pending", [False, True])
def test_supplemental_stale_recovery_preserves_newer_acceptance(tmp_path, monkeypatch, pending):
    module = load_module(); publication_fixture(tmp_path)
    calls = []
    def runner(command, root): calls.append(tuple(command)); return passing_runner(command, root)
    native = module.write_control_plane_status
    if pending: monkeypatch.setattr(module, "write_control_plane_status", lambda *a, **k: (_ for _ in ()).throw(OSError("owned_pending")))
    first = supplemental_publish(module, tmp_path, command_runner=runner)
    candidate = tmp_path / (first["finalization"]["candidate_path"] if pending else first["resume_state_paths"]["timestamped"])
    candidate_bytes = candidate.read_bytes()
    monkeypatch.setattr(module, "write_control_plane_status", native)
    second = supplemental_publish(module, tmp_path, command_runner=runner)
    accepted = supplemental_hashes(tmp_path)
    rejected = module.recover_finalization(tmp_path, candidate, expected_identity=first["execution_identity"])
    assert rejected["result"] == "BLOCKED"
    assert rejected["blocked_reason"] == "checkpoint_stale_predecessor"
    assert supplemental_hashes(tmp_path) == accepted
    assert candidate.read_bytes() == candidate_bytes
    assert len(calls) == 2
    relay = saved_relay(tmp_path)
    assert relay["codex_prompt_ready"] is True
    assert relay["checkpoint_id"] == second["resume_state"]["checkpoint_id"]


def test_supplemental_current_complete_recovery_is_verified_noop(tmp_path, monkeypatch):
    module = load_module(); publication_fixture(tmp_path)
    first = supplemental_publish(module, tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.setattr(module, "finalize_success", lambda *a, **k: (_ for _ in ()).throw(AssertionError("completed_recovery_must_not_rebuild")))
    recovered = module.recover_finalization(tmp_path, tmp_path / first["resume_state_paths"]["timestamped"], expected_identity=first["execution_identity"])
    assert recovered["result"] == "DONE_FOR_CURRENT_GOAL"
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    (tmp_path / "state.json").write_text('{"result":"BLOCKED"}', encoding="utf-8")
    corrupt = supplemental_hashes(tmp_path)
    rejected = module.recover_finalization(tmp_path, tmp_path / first["resume_state_paths"]["timestamped"], expected_identity=first["execution_identity"])
    assert rejected["result"] == "BLOCKED"
    assert supplemental_hashes(tmp_path) == corrupt


def test_supplemental_acceptance_advancing_during_builders_rejects_before_writes(tmp_path, monkeypatch):
    module = load_module(); publication_fixture(tmp_path)
    native = module.build_goal_decision; second = []
    def publish_newer(*args, **kwargs):
        monkeypatch.setattr(module, "build_goal_decision", native)
        second.append(supplemental_publish(module, tmp_path))
        second.append(supplemental_hashes(tmp_path))
        return native(*args, **kwargs)
    monkeypatch.setattr(module, "build_goal_decision", publish_newer)
    rejected = supplemental_publish(module, tmp_path)
    assert rejected["result"] == "BLOCKED"
    assert supplemental_hashes(tmp_path) == second[1]
    assert saved_relay(tmp_path)["checkpoint_id"] == second[0]["resume_state"]["checkpoint_id"]


@pytest.mark.parametrize("invalid", [None, [], "wrong", 1, True])
@pytest.mark.parametrize("slot", ["latest", "paths", "publication", "completion", "outputs", "output_record"])
def test_supplemental_malformed_disk_envelopes_fail_closed_without_writes(tmp_path, invalid, slot):
    module = load_module(); publication_fixture(tmp_path)
    result = supplemental_publish(module, tmp_path)
    latest = tmp_path / result["resume_state_paths"]["latest"]
    archive = tmp_path / result["resume_state_paths"]["timestamped"]
    completion = archive.with_name(archive.stem + ".completion.json")
    if slot in {"latest", "paths", "publication"}:
        value = json.loads(latest.read_bytes())
        if slot == "latest": value = invalid
        else: value["resume_state_paths" if slot == "paths" else "publication"] = invalid
        latest.write_text(json.dumps(value), encoding="utf-8")
    else:
        value = json.loads(completion.read_bytes())
        if slot == "completion": value = invalid
        elif slot == "outputs": value["outputs"] = invalid
        else: value["outputs"][0] = invalid
        completion.write_text(json.dumps(value), encoding="utf-8")
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    relay = saved_relay(tmp_path)
    assert relay["codex_prompt_ready"] is False
    assert relay["publication_error"]
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("invalid", [None, [], "wrong", 1, True])
def test_supplemental_malformed_recovery_is_controlled_and_preserves_bytes(tmp_path, invalid):
    module = load_module(); publication_fixture(tmp_path)
    result = supplemental_publish(module, tmp_path)
    archive = tmp_path / result["resume_state_paths"]["timestamped"]
    archive.write_text(json.dumps(invalid), encoding="utf-8")
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    rejected = module.recover_finalization(tmp_path, archive, expected_identity=result["execution_identity"])
    assert rejected["result"] == "BLOCKED"
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("write_resume,write_control", [(True, True), (True, False), (False, True), (False, False)])
def test_supplemental_valid_requested_projection_combinations(tmp_path, write_resume, write_control):
    module = load_module(); publication_fixture(tmp_path)
    result = supplemental_publish(module, tmp_path, write_resume=write_resume, write_control=write_control)
    assert result["result"] == "DONE_FOR_CURRENT_GOAL"
    assert (tmp_path / "state.json").is_file()
    if write_resume: assert saved_relay(tmp_path)["codex_prompt_ready"] is True
    assert (tmp_path / "Reports/aios_control_plane/AIOS_CONTROL_PLANE_STATUS_latest.json").exists() is write_control


@pytest.mark.parametrize("builder_fault", [False, True])
def test_supplemental_postcapture_lock_fault_preserves_primary_and_attempt(tmp_path, monkeypatch, builder_fault):
    from contextlib import contextmanager
    module = load_module(); publication_fixture(tmp_path)
    owner = module.resume_owner(); native_lock = owner.publication_lock
    calls = []; lock_calls = []
    def runner(command, root): calls.append(tuple(command)); return passing_runner(command, root)
    @contextmanager
    def lock_fault(*args, **kwargs):
        lock_calls.append(True)
        if len(lock_calls) > 1: raise OSError("owned_postcapture_lock_fault")
        with native_lock(*args, **kwargs): yield
    monkeypatch.setattr(owner, "publication_lock", lock_fault)
    monkeypatch.setattr(module, "resume_owner", lambda: owner)
    if builder_fault:
        monkeypatch.setattr(module, "build_goal_decision", lambda *a, **k: (_ for _ in ()).throw(OSError("owned_primary_builder_fault")))
    failed = supplemental_publish(module, tmp_path, command_runner=runner)
    assert failed["result"] == "BLOCKED"
    errors = failed["finalization"]["errors"]
    assert errors[0]["stage"] == ("builders" if builder_fault else "publication_lock")
    assert any(error["stage"] == "failure_lock" for error in errors)
    path = tmp_path / failed["finalization"]["successful_attempt_path"]
    assert path.is_file()
    assert failed["execution_identity"]["attempt_id"].encode() in path.read_bytes()
    assert len(calls) == 1
    assert not (tmp_path / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json").exists()


def test_supplemental_unexpected_builder_exception_uses_same_durable_boundary(tmp_path, monkeypatch):
    module = load_module(); publication_fixture(tmp_path)
    native = module.build_goal_decision
    monkeypatch.setattr(module, "build_goal_decision", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("owned_builder_runtime_error")))
    failed = supplemental_publish(module, tmp_path)
    assert failed["result"] == "BLOCKED"
    assert failed["finalization"]["errors"][0]["type"] == "RuntimeError"
    path = tmp_path / failed["finalization"]["candidate_path"]
    monkeypatch.setattr(module, "build_goal_decision", native)
    assert module.recover_finalization(tmp_path, path, expected_identity=failed["execution_identity"])["result"] == "DONE_FOR_CURRENT_GOAL"


@pytest.mark.parametrize("builder", ["read_repo_state", "build_post_risk_decision", "build_execution_ledger_integration_plan", "build_portfolio_state_plan", "build_session_controller_plan"])
@pytest.mark.parametrize("repaired", [False, True])
def test_supplemental_remaining_native_builder_stages_capture_before_fault(tmp_path, monkeypatch, builder, repaired):
    module = load_module(); publication_fixture(tmp_path)
    if builder != "read_repo_state": seed_risk_controls(tmp_path)
    if builder in {"build_execution_ledger_integration_plan", "build_portfolio_state_plan", "build_session_controller_plan"}: seed_execution_simulator(tmp_path)
    if builder in {"build_portfolio_state_plan", "build_session_controller_plan"}: seed_execution_ledger_integration(tmp_path)
    if builder == "build_session_controller_plan": seed_portfolio_state(tmp_path)
    native = getattr(module, builder); calls = []; builder_calls = []
    def fault(*args, **kwargs):
        builder_calls.append(True)
        if builder == "read_repo_state" and len(builder_calls) == 1: return native(*args, **kwargs)
        raise OSError("owned_remaining_builder_fault")
    def runner(command, root):
        calls.append(tuple(command)); result = passing_runner(command, root)
        if repaired and len(calls) == 1: result.update(passed=False, returncode=1)
        return result
    monkeypatch.setattr(module, builder, fault)
    failed = supplemental_publish(module, tmp_path, command_runner=runner, max_repairs=int(repaired))
    assert failed["result"] == "BLOCKED"
    assert failed["finalization"]["errors"][0]["stage"] == "builders"
    path = tmp_path / failed["finalization"]["candidate_path"]
    assert path.is_file()
    count = len(calls)
    monkeypatch.setattr(module, builder, native)
    recovered = module.recover_finalization(tmp_path, path, expected_identity=failed["execution_identity"])
    assert recovered["result"] in {"DONE_FOR_CURRENT_GOAL", "REVIEW_REQUIRED"}
    assert len(calls) == count == (3 if repaired else 1)


@pytest.mark.parametrize("slot", ["write_control", "write_resume", "emit_continuation_controller", "state_path", "resume_dir", "control_dir", "attempt_id", "returncode", "command"])
def test_supplemental_malformed_content_addressed_attempt_fields_reject(tmp_path, slot):
    module = load_module(); publication_fixture(tmp_path)
    result = supplemental_publish(module, tmp_path)
    owner = module.resume_owner()
    attempt = tmp_path / result["resume_state"]["publication"]["attempt_path"]
    value = json.loads(attempt.read_bytes())
    if slot in value["requested"]: value["requested"][slot] = 0
    elif slot == "attempt_id": value["execution_identity"][slot] = ["wrong-type"]
    elif slot == "returncode":
        identity = value["execution_identity"]; identity["successful_result"]["returncode"] = False
        identity["successful_result_sha256"] = owner.content_hash(identity["successful_result"])
    else: value["execution_identity"]["command"] = "wrong-type"
    mutated = attempt.with_name("AIOS_RESUME_ATTEMPT_" + owner.content_hash(value) + ".json")
    mutated.write_bytes(owner.serialized_bytes(value))
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    rejected = module.recover_finalization(tmp_path, mutated, expected_identity=value["execution_identity"])
    assert rejected["result"] == "BLOCKED"
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("corruption", ["envelope", "bound_content"])
def test_supplemental_normal_publication_preserves_corrupt_prior_frontier(tmp_path, corruption):
    module = load_module(); publication_fixture(tmp_path)
    first = supplemental_publish(module, tmp_path)
    latest = tmp_path / first["resume_state_paths"]["latest"]
    value = json.loads(latest.read_bytes())
    if corruption == "envelope": value = []
    else: value["next_build_plan"]["next_component"] = "corrupt_prior_plan"
    latest.write_text(json.dumps(value), encoding="utf-8")
    before = supplemental_hashes(tmp_path)
    rejected = supplemental_publish(module, tmp_path)
    assert rejected["result"] == "BLOCKED"
    assert rejected["finalization"]["errors"][0]["message"] == "checkpoint_frontier_invalid"
    assert supplemental_hashes(tmp_path) == before
    assert (tmp_path / rejected["finalization"]["successful_attempt_path"]).is_file()


def test_supplemental_recovery_frontier_check_and_writes_share_actual_owner_lock(tmp_path, monkeypatch):
    import threading
    module = load_module(); publication_fixture(tmp_path)
    writer = module.write_control_plane_status
    monkeypatch.setattr(module, "write_control_plane_status", lambda *a, **k: (_ for _ in ()).throw(OSError("owned_pending_for_interleave")))
    first = supplemental_publish(module, tmp_path)
    candidate = tmp_path / first["finalization"]["candidate_path"]
    monkeypatch.setattr(module, "write_control_plane_status", writer)
    entered = threading.Event(); release = threading.Event(); publisher_done = threading.Event()
    native = module.build_goal_decision
    outcomes = {}; errors = []
    def pause_recovery(*args, **kwargs):
        if threading.current_thread().name == "owned-recovery":
            entered.set()
            assert release.wait(10), "owned test release deadline"
        return native(*args, **kwargs)
    monkeypatch.setattr(module, "build_goal_decision", pause_recovery)
    def recover():
        try: outcomes["recovery"] = module.recover_finalization(tmp_path, candidate, expected_identity=first["execution_identity"])
        except BaseException as exc: errors.append(exc)
    def publish():
        try: outcomes["publisher"] = supplemental_publish(module, tmp_path)
        except BaseException as exc: errors.append(exc)
        finally: publisher_done.set()
    recovery = threading.Thread(target=recover, name="owned-recovery")
    publisher = threading.Thread(target=publish, name="owned-publisher")
    recovery.start()
    try:
        assert entered.wait(10)
        publisher.start()
        assert not publisher_done.wait(0.15), "new acceptance must wait for recovery's owner lock"
    finally:
        release.set()
        recovery.join(15)
        if publisher.ident is not None: publisher.join(15)
    assert not recovery.is_alive() and not publisher.is_alive()
    assert not errors
    assert outcomes["recovery"]["result"] == "DONE_FOR_CURRENT_GOAL"
    assert outcomes["publisher"]["result"] == "DONE_FOR_CURRENT_GOAL"
    assert saved_relay(tmp_path)["checkpoint_id"] == outcomes["publisher"]["resume_state"]["checkpoint_id"]


def test_supplemental_metadata_cannot_redirect_canonical_persisted_owner(tmp_path):
    module = load_module(); publication_fixture(tmp_path)
    supplemental_publish(module, tmp_path)
    custom = supplemental_publish(module, tmp_path, resume_state_dir=tmp_path / "Reports/aios_resume/owned-custom")
    canonical_latest = tmp_path / "Reports/aios_resume/AIOS_RESUME_STATE_latest.json"
    custom_latest = tmp_path / custom["resume_state_paths"]["latest"]
    canonical_latest.write_bytes(custom_latest.read_bytes())
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    rejected = saved_relay(tmp_path)
    assert rejected["codex_prompt_ready"] is False
    assert rejected["publication_error"] == "checkpoint_selected_owner_mismatch"
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_supplemental_custom_owner_requires_explicit_trusted_selection(tmp_path):
    module = load_module(); publication_fixture(tmp_path)
    custom_dir = tmp_path / "Reports/aios_resume/owned-custom"
    result = supplemental_publish(module, tmp_path, resume_state_dir=custom_dir)
    state = json.loads((tmp_path / result["resume_state_paths"]["latest"]).read_bytes())
    relay = native_contract("aios_operator_relay")
    assert relay.build_operator_relay(state, {"blockers": []}, repo_root=tmp_path)["codex_prompt_ready"] is False
    explicit = relay.build_operator_relay(state, {"blockers": []}, repo_root=tmp_path, resume_output_dir=custom_dir)
    assert explicit["codex_prompt_ready"] is True
    assert explicit["checkpoint_id"] == result["resume_state"]["checkpoint_id"]


# Native publication finalization tests borrow only inert fixture definitions.
def _np_wake_case(root, monkeypatch, task="A", lookup=None):
    import importlib.util
    fixture_path = Path(__file__).with_name("test_aios_resume_state.py")
    spec = importlib.util.spec_from_file_location("wake_resume_fixture", fixture_path)
    held = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(held)
    case = held._np_case(root, monkeypatch, task, lookup)
    case["helpers"] = held.__dict__
    return case


def test_native_builder_failure_retains_complete_attempt_and_recovers_no_execution(tmp_path,monkeypatch):
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"];attempt=h["_np_capture"](case)
    original=attempt.read_bytes();wake=case["wake"];builder=wake._build_native_projection
    monkeypatch.setattr(case["cycle"],"_invoke_native_aggregate_host",lambda *a,**k:pytest.fail("validator replay"))
    monkeypatch.setattr(wake,"_build_native_projection",lambda *a,**k:(_ for _ in ()).throw(OSError("owned native builder primary")))
    failed=h["_np_recover"](case,attempt)
    assert failed["result"]=="BLOCKED" and attempt.read_bytes()==original
    assert "owned native builder primary" in json.dumps(failed)
    assert list((tmp_path/case["requested"]["resume_dir"]).glob("AIOS_RESUME_FAILURE_*.json"))
    monkeypatch.setattr(wake,"_build_native_projection",builder)
    assert h["_np_recover"](case,attempt)["result"]=="COMPLETE"
    assert attempt.read_bytes()==original


@pytest.mark.parametrize("boundary",["snapshot","completion","latest"])
def test_native_writer_boundaries_preserve_attempt_and_same_attempt_recovery(tmp_path,monkeypatch,boundary):
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"];attempt=h["_np_capture"](case)
    owner=case["owner"];immutable=owner.immutable_write;atomic=owner.atomic_write;fired=[]
    def write(path,data):
        selected=(".projection-" in path.name if boundary=="snapshot" else path.name.endswith(".completion.json"))
        if boundary!="latest" and selected and not fired:
            fired.append(str(path));raise OSError("owned "+boundary+" primary")
        return immutable(path,data)
    def replace(path,data):
        if boundary=="latest" and path.name==owner.LATEST_FILENAME and not fired:
            fired.append(str(path));raise OSError("owned latest primary")
        return atomic(path,data)
    monkeypatch.setattr(owner,"immutable_write",write);monkeypatch.setattr(owner,"atomic_write",replace)
    failed=h["_np_recover"](case,attempt)
    assert fired and failed["result"]=="BLOCKED" and attempt.exists()
    assert h["_np_read"](case) is None
    assert h["_np_recover"](case,attempt)["result"]=="COMPLETE"


def test_native_orphan_completion_does_not_commit_or_rollback_previous(tmp_path,monkeypatch):
    a=_np_wake_case(tmp_path,monkeypatch,"A");h=a["helpers"]
    assert h["_np_recover"](a,h["_np_capture"](a))["result"]=="COMPLETE"
    latest=tmp_path/a["requested"]["resume_dir"]/a["owner"].LATEST_FILENAME;previous=latest.read_bytes()
    b=_np_wake_case(tmp_path,monkeypatch,"B",a["lookup"]);attempt=h["_np_capture"](b);owner=b["owner"];atomic=owner.atomic_write
    def replace(path,data):
        if path==latest:raise OSError("owned orphan before sole head")
        return atomic(path,data)
    monkeypatch.setattr(owner,"atomic_write",replace)
    assert h["_np_recover"](b,attempt)["result"]=="BLOCKED"
    assert latest.read_bytes()==previous and h["_np_read"](b) is None
    assert len(list(latest.parent.glob("*.completion.json")))>=2
    assert h["_np_read"](a)["execution_identity"]["task_id"]=="A"


def test_native_stale_pending_recovery_preserves_newer_bytes(tmp_path,monkeypatch):
    a=_np_wake_case(tmp_path,monkeypatch,"A");h=a["helpers"]
    assert h["_np_recover"](a,h["_np_capture"](a))["result"]=="COMPLETE"
    b=_np_wake_case(tmp_path,monkeypatch,"B",a["lookup"]);pending=h["_np_capture"](b)
    c=_np_wake_case(tmp_path,monkeypatch,"C",a["lookup"])
    assert h["_np_recover"](c,h["_np_capture"](c))["result"]=="COMPLETE"
    before=h["_np_snapshot"](tmp_path)
    rejected=h["_np_recover"](b,pending)
    assert rejected["result"]=="BLOCKED"
    assert h["_np_snapshot"](tmp_path)==before


def test_native_current_complete_recovery_is_verified_noop(tmp_path,monkeypatch):
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"];attempt=h["_np_capture"](case)
    assert h["_np_recover"](case,attempt)["result"]=="COMPLETE"
    before=h["_np_snapshot"](tmp_path)
    monkeypatch.setattr(case["wake"],"_build_native_projection",lambda *a,**k:pytest.fail("builder replay"))
    monkeypatch.setattr(case["cycle"],"_invoke_native_aggregate_host",lambda *a,**k:pytest.fail("validator replay"))
    assert h["_np_recover"](case,attempt)["result"]=="COMPLETE"
    assert h["_np_snapshot"](tmp_path)==before


def test_native_complete_XML_without_durable_attempt_never_guesses_capture(tmp_path,monkeypatch):
    case=_np_wake_case(tmp_path,monkeypatch)
    before=case["helpers"]["_np_snapshot"](tmp_path)
    with pytest.raises(ValueError,match="without_complete_attempt|no_replay"):
        case["owner"].find_native_attempt(tmp_path,admitted_context=case["context"],native_admission_reader=case["reader"])
    assert case["helpers"]["_np_snapshot"](tmp_path)==before


@pytest.mark.parametrize("secondary",[False,True])
def test_native_capture_write_failure_preserves_prepared_result_and_both_causes(tmp_path,monkeypatch,secondary):
    case=_np_wake_case(tmp_path,monkeypatch);owner=case["owner"];write=owner.immutable_write
    def fail(path,data):
        if path.name.startswith("AIOS_RESUME_ATTEMPT_"):raise OSError("owned capture primary")
        if secondary and path.name.startswith("AIOS_RESUME_FAILURE_"):raise OSError("owned failure evidence secondary")
        return write(path,data)
    monkeypatch.setattr(owner,"immutable_write",fail)
    evidence=case["data"]["evidence"]["capture"]
    result=case["wake"].publish_native_requirement(tmp_path,admitted_context=case["context"],
        execution_capture_path=evidence["path"],execution_capture_sha256=evidence["sha256"],
        validation_record=case["validation"],requested=case["requested"],native_admission_reader=case["reader"])
    encoded=json.dumps(result)
    assert result["result"]=="BLOCKED" and "owned capture primary" in encoded
    assert "attempt-A" in encoded and "AIOS_NATIVE_REQUIREMENT_RESULT.v1" in encoded
    if secondary:assert "owned failure evidence secondary" in encoded
    else:
        saved=list((tmp_path/case["requested"]["resume_dir"]).glob("AIOS_RESUME_FAILURE_*.json"))
        assert saved and b"AIOS_NATIVE_REQUIREMENT_RESULT.v1" in saved[0].read_bytes()


def test_native_postcapture_lock_failure_preserves_primary_secondary_and_attempt(tmp_path,monkeypatch):
    from contextlib import contextmanager
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"];attempt=h["_np_capture"](case);original=attempt.read_bytes()
    @contextmanager
    def locked(*a,**k):
        raise OSError("owned late publication lock")
        yield
    monkeypatch.setattr(case["owner"],"publication_lock",locked)
    result=h["_np_recover"](case,attempt)
    assert result["result"]=="BLOCKED" and "owned late publication lock" in json.dumps(result)
    assert len(result["finalization"]["errors"])>=2 and attempt.read_bytes()==original


def _np_reseal_semantic_state(case,change):
    from copy import deepcopy
    h=case["helpers"];owner=case["owner"];root=case["root"]
    state=h["_np_read"](case);pending=json.loads((root/state["publication"]["pending_checkpoint"]).read_bytes())
    for key in ("checkpoint_id","generated_at_utc","resume_state_paths"):pending.pop(key,None)
    change(pending)
    new_pending=owner.write_resume_state(root,pending,output_dir=case["requested"]["resume_dir"],publish_latest=False)
    pending_path=root/new_pending["resume_state_paths"]["timestamped"];outputs=[]
    for output in state["publication"]["accepted_outputs"]:
        selected=deepcopy(output)
        snapshot=pending_path.with_name(pending_path.stem+".projection-"+output["role"]+"-"+output["sha256"]+".json")
        snapshot.write_bytes((root/output["snapshot"]).read_bytes())
        selected["snapshot"]=snapshot.relative_to(root).as_posix();outputs.append(selected)
    accepted={k:v for k,v in new_pending.items() if k not in {"checkpoint_id","generated_at_utc","resume_state_paths"}}
    accepted["publication"]={**state["publication"],"pending_checkpoint":new_pending["resume_state_paths"]["timestamped"],"accepted_outputs":outputs}
    rebuilt=owner.write_resume_state(root,accepted,output_dir=case["requested"]["resume_dir"],publish_latest=False)
    archive=root/rebuilt["resume_state_paths"]["timestamped"];payload=archive.read_bytes()
    receipt={"checkpoint_id":rebuilt["checkpoint_id"],"archive_sha256":h["_np_hash"](payload),
        "execution_identity":rebuilt["publication"]["execution_identity"],"outputs":outputs}
    archive.with_name(archive.stem+".completion.json").write_bytes(owner.serialized_bytes(receipt))
    (archive.parent/owner.LATEST_FILENAME).write_bytes(payload)


@pytest.mark.parametrize("kind",["schema","result","request","ready_int","safety_int","extra"])
def test_native_resealed_state_semantics_cannot_forge_acceptance(tmp_path,monkeypatch,kind):
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"]
    assert h["_np_recover"](case,h["_np_capture"](case))["result"]=="COMPLETE"
    def change(state):
        if kind=="schema":state["schema"]="unsupported"
        elif kind=="result":state["result"]="PENDING"
        elif kind=="request":state["requirement_request"]=[]
        elif kind=="ready_int":state["resume_ready"]=1
        elif kind=="safety_int":state["safety"]["worker_dispatch"]=0
        else:state["unexpected"]={"approved":True}
    _np_reseal_semantic_state(case,change)
    before=h["_np_snapshot"](tmp_path)
    with pytest.raises(ValueError):h["_np_read"](case)
    assert h["_np_snapshot"](tmp_path)==before


# C3 adds source-compatible prepared recovery and readback controls.
def _np_c3_prepared_failure(case, kind="valid"):
    from copy import deepcopy
    h=case["helpers"];owner=case["owner"];root=case["root"]
    identity=case["cycle"].native_execution_identity(root,case["context"],case["validation"],native_admission_reader=case["reader"])
    record={"record_type":"successful_attempt","execution_identity":identity,
        "finalization_input":{"schema":"AIOS_NATIVE_FINALIZATION.v1","execution_identity":identity,
            "requirement_request":identity["requirement_request"]},
        "requested":deepcopy(case["requested"]),"required_outputs":owner.requested_projections(root,case["requested"]),
        "predecessor_sha256":None}
    if kind=="minimal":record["finalization_input"]={"unadmitted":True}
    elif kind=="outputs":record["required_outputs"]=[]
    elif kind=="extra":record["unadmitted"]=True
    elif kind=="owner":record["requested"]["resume_dir"]="Reports/aios_resume/NOT-ADMITTED"
    selected=root/case["requested"]["resume_dir"];selected.mkdir(parents=True,exist_ok=True)
    target=root/record["requested"]["resume_dir"]
    digest=owner.content_hash(record)
    if kind=="attempt_name":digest="f"*64
    attempt=target/("AIOS_RESUME_ATTEMPT_"+digest+".json")
    failure={"schema":"AIOS_NATIVE_FINALIZATION.v1","result":"BLOCKED",
        "prepared_native_attempt":{**record,"attempt_path":attempt.relative_to(root).as_posix()}}
    raw=owner.serialized_bytes(failure)
    path=selected/("AIOS_RESUME_FAILURE_"+h["_np_hash"](raw)+".json");path.write_bytes(raw)
    return path,attempt,record


def test_native_valid_prepared_failure_recovers_exact_original_without_replay(tmp_path,monkeypatch):
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"]
    path,attempt,record=_np_c3_prepared_failure(case)
    failure_raw=path.read_bytes()
    monkeypatch.setattr(case["cycle"],"_invoke_native_aggregate_host",lambda *a,**k:pytest.fail("validator replay"))
    report=case["wake"].recover_native_finalization(tmp_path,path,admitted_context=case["context"],native_admission_reader=case["reader"])
    assert report["result"]=="COMPLETE"
    assert path.read_bytes()==failure_raw and attempt.read_bytes()==case["owner"].serialized_bytes(record)
    assert h["_np_read"](case)==report["resume_state"]


@pytest.mark.parametrize("kind",["minimal","outputs","extra","owner","attempt_name"])
def test_native_prepared_record_complete_validation_precedes_any_derived_write(tmp_path,monkeypatch,kind):
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"]
    path,attempt,record=_np_c3_prepared_failure(case,kind)
    before=h["_np_c3_pins"](tmp_path);directories={p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_dir()}
    with pytest.raises(ValueError):case["wake"].recover_native_finalization(tmp_path,path,admitted_context=case["context"],native_admission_reader=case["reader"])
    assert not attempt.exists()
    assert h["_np_c3_pins"](tmp_path)==before
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_dir()}==directories


@pytest.mark.parametrize("artifact,placement",[(artifact,placement) for artifact in ("attempt","failure") for placement in ("private_shaped","foreign_owner","invalid_name")])
def test_native_candidate_owner_and_name_are_checked_before_payload_read(tmp_path,monkeypatch,artifact,placement):
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"];owner=case["owner"]
    original=h["_np_capture"](case);record=json.loads(original.read_bytes())
    assert owner._load_native_attempt(tmp_path,original,admitted_context=case["context"],native_admission_reader=case["reader"],live=False)==record
    if artifact=="attempt":raw=original.read_bytes();name=original.name
    else:
        failure={"schema":"AIOS_NATIVE_FINALIZATION.v1","result":"BLOCKED",
            "prepared_native_attempt":{**record,"attempt_path":original.relative_to(tmp_path).as_posix()}}
        raw=owner.serialized_bytes(failure);name="AIOS_RESUME_FAILURE_"+h["_np_hash"](raw)+".json"
    if placement=="private_shaped":sentinel=tmp_path/"owned-private-shaped"/".env"/name
    elif placement=="foreign_owner":sentinel=tmp_path/"Reports/aios_resume/NOT-ADMITTED-READ"/name
    else:sentinel=original.parent/("AIOS_RESUME_"+artifact.upper()+"_invalid.json")
    sentinel.parent.mkdir(parents=True,exist_ok=True);sentinel.write_bytes(raw)
    before=h["_np_c3_pins"](tmp_path);reads=[];open_original=Path.open
    def tracked_open(path,*args,**kwargs):
        mode=args[0] if args else kwargs.get("mode","r")
        if path==sentinel and ("r" in mode or "+" in mode):
            reads.append(str(path));raise AssertionError("unadmitted owned sentinel payload read")
        return open_original(path,*args,**kwargs)
    with monkeypatch.context() as tracking:
        tracking.setattr(Path,"open",tracked_open)
        with pytest.raises(ValueError):
            if artifact=="attempt":owner._load_native_attempt(tmp_path,sentinel,admitted_context=case["context"],native_admission_reader=case["reader"],live=False)
            else:case["wake"].recover_native_finalization(tmp_path,sentinel,admitted_context=case["context"],native_admission_reader=case["reader"])
    assert reads==[] and h["_np_c3_pins"](tmp_path)==before


def test_native_generic_snapshot_reseal_cannot_replace_deterministic_projection(tmp_path,monkeypatch):
    from copy import deepcopy
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"];owner=case["owner"]
    attempt=h["_np_capture"](case);attempt_raw=attempt.read_bytes()
    report=h["_np_recover"](case,attempt);assert report["result"]=="COMPLETE"
    state=h["_np_read"](case);assert state==report["resume_state"]
    forged=deepcopy(state);publication=forged["publication"]
    assert len(publication["accepted_outputs"])==1 and publication["accepted_outputs"][0]["role"]=="generic"
    pending=tmp_path/publication["pending_checkpoint"]
    unrelated=b'{"schema":"OWNED_UNRELATED_GENERIC_SENTINEL.v1","unrelated":true}\n'
    digest=h["_np_hash"](unrelated)
    snapshot=pending.with_name(pending.stem+".projection-generic-"+digest+".json")
    output=publication["accepted_outputs"][0];output["sha256"]=digest;output["snapshot"]=snapshot.relative_to(tmp_path).as_posix()
    snapshot.write_bytes(unrelated);(tmp_path/output["path"]).write_bytes(unrelated)
    semantic={k:v for k,v in forged.items() if k not in {"generated_at_utc","resume_state_paths","checkpoint_id"}}
    checkpoint_id=owner.content_hash(semantic)
    old_archive=tmp_path/state["resume_state_paths"]["timestamped"]
    archive=old_archive.with_name(old_archive.name.rsplit("_",1)[0]+"_"+checkpoint_id+".json")
    forged["checkpoint_id"]=checkpoint_id;forged["resume_state_paths"]["timestamped"]=archive.relative_to(tmp_path).as_posix()
    payload=owner.serialized_bytes(forged);archive.write_bytes(payload)
    completion={"checkpoint_id":checkpoint_id,"archive_sha256":h["_np_hash"](payload),
        "execution_identity":publication["execution_identity"],"outputs":publication["accepted_outputs"]}
    archive.with_name(archive.stem+".completion.json").write_bytes(owner.serialized_bytes(completion))
    (tmp_path/forged["resume_state_paths"]["latest"]).write_bytes(payload)
    before=h["_np_c3_pins"](tmp_path)
    with pytest.raises(ValueError):h["_np_read"](case)
    assert attempt.read_bytes()==attempt_raw and h["_np_c3_pins"](tmp_path)==before


def test_native_stale_pending_recovery_preserves_newer_bytes(tmp_path,monkeypatch):
    a=_np_wake_case(tmp_path,monkeypatch,"A");h=a["helpers"]
    assert h["_np_recover"](a,h["_np_capture"](a))["result"]=="COMPLETE"
    b=_np_wake_case(tmp_path,monkeypatch,"B",a["lookup"]);pending=h["_np_capture"](b)
    c=_np_wake_case(tmp_path,monkeypatch,"C",a["lookup"])
    assert h["_np_recover"](c,h["_np_capture"](c))["result"]=="COMPLETE"
    before=h["_np_c3_pins"](tmp_path)
    monkeypatch.setattr(c["cycle"],"_invoke_native_aggregate_host",lambda *args,**kwargs:pytest.fail("validator replay"))
    rejected=h["_np_recover"](b,pending);assert rejected["result"]=="BLOCKED"
    after=h["_np_c3_pins"](tmp_path)
    assert all(after.get(name)==digest for name,digest in before.items())
    added=set(after)-set(before);assert added
    selected=tmp_path/b["requested"]["resume_dir"]
    for relative in added:
        path=tmp_path/relative;raw=path.read_bytes()
        assert path.parent==selected and path.name=="AIOS_RESUME_FAILURE_"+h["_np_hash"](raw)+".json"
        failure=json.loads(raw)
        assert failure["result"]=="BLOCKED"
        assert any("stale_predecessor" in error["message"] for error in failure["finalization"]["errors"])



def _np_c3_unlocked_public_state(case):
    from copy import deepcopy
    h=case["helpers"];owner=case["owner"];root=case["root"]
    identity=case["cycle"].native_execution_identity(root,case["context"],case["validation"],native_admission_reader=case["reader"])
    record={"record_type":"successful_attempt","execution_identity":identity,
        "finalization_input":{"schema":"AIOS_NATIVE_FINALIZATION.v1","execution_identity":identity,
            "requirement_request":identity["requirement_request"]},
        "requested":deepcopy(case["requested"]),"required_outputs":owner.requested_projections(root,case["requested"]),
        "predecessor_sha256":None}
    selected=root/case["requested"]["resume_dir"];selected.mkdir(parents=True,exist_ok=True)
    attempt=selected/("AIOS_RESUME_ATTEMPT_"+owner.content_hash(record)+".json")
    attempt.write_bytes(owner.serialized_bytes(record))
    state=case["wake"]._build_native_projection(record)
    state["publication"]={**record,"attempt_path":attempt.relative_to(root).as_posix()}
    assert not (selected/".publication.lock").exists()
    return state,record,selected


def test_native_public_publish_valid_selected_owner_control(tmp_path,monkeypatch):
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"];owner=case["owner"]
    state,record,selected=_np_c3_unlocked_public_state(case)
    def projections(candidate):
        outputs=[]
        for expected in owner.requested_projections(tmp_path,record["requested"]):
            assert expected["role"]=="generic"
            destination=tmp_path/expected["path"]
            payload=owner.serialized_bytes(owner._native_generic_projection(record,candidate))
            owner.atomic_write(destination,payload)
            outputs.append({**expected,"sha256":h["_np_hash"](payload)})
        return outputs
    published=owner.publish_resume_state(tmp_path,state,projections,output_dir=selected,
        admitted_context=case["context"],native_admission_reader=case["reader"])
    assert h["_np_read"](case)==published and (selected/".publication.lock").is_file()


@pytest.mark.parametrize("kind",["wrong_owner","malformed_context"])
def test_native_public_publish_rejects_before_any_directory_lock_or_projection_write(tmp_path,monkeypatch,kind):
    case=_np_wake_case(tmp_path,monkeypatch);h=case["helpers"];owner=case["owner"]
    state,record,selected=_np_c3_unlocked_public_state(case)
    context,reader=case["context"],case["reader"];target=selected
    if kind=="wrong_owner":target=tmp_path/"Reports/aios_resume/UNADMITTED-PUBLIC"
    else:
        context,reader=h["_np_admit_mutation"](case,lambda data:data.update(schema="unsupported-native-context"))
    before=h["_np_c3_pins"](tmp_path);directories={p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_dir()}
    def forbidden_projection(candidate):pytest.fail("unqualified projection writer called")
    with pytest.raises(ValueError):owner.publish_resume_state(tmp_path,state,forbidden_projection,output_dir=target,
        admitted_context=context,native_admission_reader=reader)
    assert h["_np_c3_pins"](tmp_path)==before and not (selected/".publication.lock").exists()
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_dir()}==directories


def test_native_historical_A_after_B_never_collects_live_status(tmp_path,monkeypatch):
    from automation.orchestration import aios_repo_state_evidence as repo_evidence
    a=_np_wake_case(tmp_path,monkeypatch,"A");h=a["helpers"];attempt_a=h["_np_capture"](a)
    accepted_a=h["_np_recover"](a,attempt_a);assert accepted_a["result"]=="COMPLETE"
    b=_np_wake_case(tmp_path,monkeypatch,"B",a["lookup"])
    assert h["_np_recover"](b,h["_np_capture"](b))["result"]=="COMPLETE"
    before=h["_np_c3_pins"](tmp_path);calls=[]
    def forbidden_status(actual_root,runner):
        calls.append(str(actual_root));raise AssertionError("historical verification collected live status")
    monkeypatch.setattr(repo_evidence,"_run_git_status",forbidden_status)
    assert a["cycle"].native_execution_identity(tmp_path,a["context"],a["validation"],native_admission_reader=a["reader"],live=False)["task_id"]=="A"
    assert h["_np_read"](a)==accepted_a["resume_state"]
    assert h["_np_recover"](a,attempt_a)["result"]=="COMPLETE"
    assert not calls and h["_np_c3_pins"](tmp_path)==before
