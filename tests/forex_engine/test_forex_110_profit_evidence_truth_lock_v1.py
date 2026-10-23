from __future__ import annotations

from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_110_profit_evidence_truth_lock_v1 import (  # noqa: E402
    PROFIT_PROOF_BLOCKED,
    build_report_markdown,
    run_profit_evidence_truth_lock,
)
from automation.forex_engine.profit_proof_ledger_v1 import (  # noqa: E402
    build_sample_all_blocked_candidates,
    build_sample_profit_proof_candidates,
)
from scripts.forex_delivery.run_forex_110_profit_evidence_truth_lock_v1 import (  # noqa: E402
    REPORT_NAME,
    STATE_NAME,
    main,
)


PROTECTED_FLAGS = (
    "next_demo_trade_allowed",
    "broker_action_allowed",
    "real_money_allowed",
    "compounding_allowed",
    "bank_movement_allowed",
    "live_trading_allowed",
    "credential_access_allowed",
    "order_submission_allowed",
    "owner_approval_created",
)


def write_complete_persistent_profit_report(report_root: Path) -> None:
    report_root.mkdir()
    (report_root / "AIOS_FOREX_PROFITABILITY_VERDICT_V1.md").write_text(
        "\n".join(
            [
                "- closed_trade_count: 40",
                "- min_closed_trade_count: 30",
                "- expectancy: 0.40",
                "- min_expectancy: 0.05",
                "- profit_factor: 1.50",
                "- min_profit_factor: 1.25",
                "- max_drawdown: 0.02",
                "- max_allowed_drawdown: 0.05",
                "- consecutive_profitable_periods: 5",
                "- min_profitable_periods: 4",
                "- after_costs: true",
                "- sanitized: true",
                "- evidence_age_days: 1",
                "- max_evidence_age_days: 7",
            ]
        ),
        encoding="utf-8",
    )


def write_blocked_persistent_profit_report(report_root: Path) -> None:
    report_root.mkdir()
    (report_root / "AIOS_FOREX_PROFITABILITY_VERDICT_V1.md").write_text(
        "\n".join(
            [
                "- closed_trade_count: 40",
                "- min_closed_trade_count: 30",
                "- expectancy: 0.40",
                "- min_expectancy: 0.05",
                "- profit_factor: 1.50",
                "- min_profit_factor: 1.25",
                "- max_drawdown: 0.02",
                "- max_allowed_drawdown: 0.05",
                "- consecutive_profitable_periods: 1",
                "- min_profitable_periods: 4",
                "- after_costs: true",
                "- sanitized: true",
                "- evidence_age_days: 1",
                "- max_evidence_age_days: 7",
            ]
        ),
        encoding="utf-8",
    )


def assert_permissions_false(result: dict) -> None:
    for flag in PROTECTED_FLAGS:
        assert result[flag] is False
        assert result["permissions"][flag] is False


def test_truth_lock_keeps_passing_synthetic_metrics_diagnostic(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_complete_persistent_profit_report(report_root)

    result = run_profit_evidence_truth_lock(report_root, build_sample_profit_proof_candidates())

    assert result["profit_proof_status"] == PROFIT_PROOF_BLOCKED
    assert result["source_authentication_status"] == "UNVERIFIED"
    assert "NO_INDEPENDENT_VERIFIER_CONNECTED" in result["blockers"]
    assert result["ledger_status"] == "PROFIT_PROOF_LEDGER_PROMOTABLE"
    assert_permissions_false(result)


def test_truth_lock_blocks_when_ledger_promotable_but_persistence_blocked(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_blocked_persistent_profit_report(report_root)

    result = run_profit_evidence_truth_lock(report_root, build_sample_profit_proof_candidates())

    assert result["profit_proof_status"] == PROFIT_PROOF_BLOCKED
    assert result["truth_lock_status"] == PROFIT_PROOF_BLOCKED
    assert result["diagnostic_ledger_promotable"] is True
    assert result["diagnostic_persistence_ready"] is False
    assert "profitable periods are below threshold" in result["blockers"]
    assert_permissions_false(result)


def test_truth_lock_blocks_when_ledger_has_no_promotable_candidate(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_complete_persistent_profit_report(report_root)

    result = run_profit_evidence_truth_lock(
        report_root,
        candidates=build_sample_all_blocked_candidates(),
    )

    assert result["profit_proof_status"] == PROFIT_PROOF_BLOCKED
    assert result["truth_lock_status"] == PROFIT_PROOF_BLOCKED
    assert result["ledger_status"] != "PROFIT_PROOF_LEDGER_PROMOTABLE"
    assert_permissions_false(result)


def test_report_markdown_contains_truth_and_locks(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_blocked_persistent_profit_report(report_root)

    report = build_report_markdown(run_profit_evidence_truth_lock(report_root))

    assert "Profit proof status: `BLOCKED`" in report
    assert "next_demo_trade_allowed: `false`" in report
    assert "profitable periods are below threshold" in report


def test_runner_writes_state_and_report(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    output_root = tmp_path / "out"
    write_blocked_persistent_profit_report(report_root)

    exit_code = main(
        [
            "--report-root",
            str(report_root),
            "--output-root",
            str(output_root),
            "--write-state",
            "--write-report",
        ]
    )
    state = json.loads((output_root / STATE_NAME).read_text(encoding="utf-8"))

    assert exit_code == 0
    assert state["profit_proof_status"] == PROFIT_PROOF_BLOCKED
    assert (output_root / REPORT_NAME).exists()
