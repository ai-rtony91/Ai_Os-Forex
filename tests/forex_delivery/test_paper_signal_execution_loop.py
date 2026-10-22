from pathlib import Path
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from forex_delivery.paper_signal_execution_loop import (  # noqa: E402
    build_paper_signal_execution_loop_result,
    build_sanitized_report,
    cli_summary,
)


def test_paper_loop_runs_without_secrets_and_keeps_live_execution_blocked():
    result = build_paper_signal_execution_loop_result()
    payload = json.dumps(result, sort_keys=True)

    assert result["mode"] == "PAPER_SIMULATION"
    assert result["selected_pair"] == "EUR_USD"
    assert result["signal_side"] == "BUY"
    assert result["risk_approval"] is True
    assert result["paper_entry_created"] is True
    assert result["paper_close_reconcile"] is True
    assert result["trading_history_row_written"] is True
    assert result["live_execution_allowed"] is False
    assert result["broker_write_calls_allowed"] is False
    assert result["order_placement_allowed"] is False
    assert "OANDA_API_TOKEN" not in payload
    assert "OANDA_ACCOUNT_ID" not in payload
    assert "transactionID" not in payload
    assert "orderID" not in payload


def test_aggregate_result_contains_required_loop_fields():
    result = build_paper_signal_execution_loop_result()

    for key in (
        "selected_pair",
        "signal_side",
        "strategy_name",
        "confidence",
        "signal_reason",
        "spread_slippage_status",
        "risk_approval",
        "paper_entry_created",
        "paper_entry_price",
        "paper_units",
        "exit_plan_status",
        "stop_loss_policy",
        "take_profit_policy",
        "trailing_stop_policy",
        "max_time_policy",
        "paper_close_reconcile",
        "realized_paper_pl",
        "exit_reason",
        "trading_history_row_written",
        "evidence_path",
        "live_execution_allowed",
        "next_safe_action",
    ):
        assert key in result


def test_sanitized_report_and_cli_summary_are_paper_only():
    result = build_paper_signal_execution_loop_result()
    report = build_sanitized_report(result)
    summary = cli_summary(result)

    assert "AIOS Forex Paper Signal Execution Loop Dry Run V1" in report
    assert "PAPER_SIMULATION" in report
    assert summary["live_execution_allowed"] is False
    assert summary["trading_history_row_written"] is True
    assert "OANDA_API_TOKEN" not in report
    assert "OANDA_ACCOUNT_ID" not in report


def test_no_broker_write_methods_or_live_endpoints_appear_in_paper_loop_code():
    paths = [
        REPO_ROOT / "src" / "forex_delivery" / "paper_signal_execution_loop.py",
        REPO_ROOT / "automation" / "forex_engine" / "paper_execution_simulator.py",
        REPO_ROOT / "scripts" / "forex_delivery" / "run_paper_signal_execution_loop.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)

    for forbidden in (
        "requests.",
        "urllib.request",
        ".post(",
        ".put(",
        ".patch(",
        ".delete(",
        "/orders",
        "/trades/",
        "/positions/",
        "createorder",
        "cancelorder",
        "closetrade",
        "closeposition",
    ):
        assert forbidden not in combined


def test_dashboard_references_paper_loop_status_without_browser_broker_calls():
    dashboard_path = REPO_ROOT / "apps" / "dashboard" / "src" / "MinimalOperatorDashboard.jsx"
    source = dashboard_path.read_text(encoding="utf-8")

    assert "DISPLAY_ONLY" in source
    assert "EXEC OFF" in source
    assert "BROKER LOCKED" in source
    assert "trading execution stays locked" in source
    assert "ORDER CONTROL remains absent" in source
    for forbidden in ("fetch(", "XMLHttpRequest", "axios", "OANDA_API_TOKEN", "OANDA_ACCOUNT_ID"):
        assert forbidden not in source
