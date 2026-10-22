from __future__ import annotations

from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_110_walkforward_oos_sufficiency_truth_lock_v1 import (  # noqa: E402
    TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_BLOCKED,
    TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_CANDIDATE_MISMATCH,
    WALK_FORWARD_OOS_BLOCKED_MISSING_EVIDENCE,
    WALK_FORWARD_OOS_BLOCKED_TOP_CANDIDATE_MISMATCH,
    build_report_markdown,
    run_walkforward_oos_sufficiency_truth_lock,
)
from automation.forex_engine.profit_proof_ledger_v1 import (
    build_sample_profit_proof_candidates,
)
from scripts.forex_delivery.run_forex_110_walkforward_oos_sufficiency_truth_lock_v1 import (  # noqa: E402
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


def write_profitability_report(report_root: Path) -> None:
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


def write_walkforward_report(report_root: Path, *, candidate_id: str, include_oos: bool = True) -> None:
    lines = [
        f"- candidate: `{candidate_id}`",
        "- windows_total: 6",
        "- windows_passed: 6",
        "- min_pass_rate: 0.75",
        "- max_drawdown: 0.02",
        "- max_allowed_drawdown: 0.05",
        "- sanitized: true",
        "- evidence_age_days: 1",
        "- max_evidence_age_days: 7",
    ]
    if include_oos:
        lines.extend(["- oos_segments_total: 4", "- oos_segments_passed: 4"])
    (report_root / "AIOS_FOREX_WALK_FORWARD_DEPTH_PACKET_R_V1_REPORT.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def assert_permissions_false(result: dict) -> None:
    for flag in PROTECTED_FLAGS:
        assert result[flag] is False
        assert result["permissions"][flag] is False


def test_truth_lock_blocks_unauthenticated_aligned_summary(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root, candidate_id="c2-eur-buy-stronger-review-ready")

    result = run_walkforward_oos_sufficiency_truth_lock(report_root, build_sample_profit_proof_candidates())

    assert result["walk_forward_oos_status"] == "BLOCKED_SOURCE_AUTHENTICITY"
    assert "NO_INDEPENDENT_VERIFIER_CONNECTED" in result["blockers"]
    assert result["profit_persistence_unlocked"] is False
    assert result["truth_lock_status"] == TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_BLOCKED
    assert result["top_candidate_alignment"]["status"] == "ALIGNED"
    assert result["attack_to_finish"]["blocker_status"] == "BLOCKED"
    assert result["attack_to_finish"]["missing_evidence_field"] == "source_authentication"
    assert_permissions_false(result)


def test_truth_lock_blocks_current_style_candidate_mismatch(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root, candidate_id="c1-eur-buy")

    result = run_walkforward_oos_sufficiency_truth_lock(report_root, build_sample_profit_proof_candidates())

    assert result["walk_forward_oos_status"] == WALK_FORWARD_OOS_BLOCKED_TOP_CANDIDATE_MISMATCH
    assert result["truth_lock_status"] == TRUTH_LOCK_REVIEW_READY_WALKFORWARD_OOS_CANDIDATE_MISMATCH
    assert result["profit_persistence_unlocked"] is False
    assert result["top_candidate_alignment"]["status"] == "MISMATCHED"
    assert result["attack_to_finish"]["missing_evidence_field"] == "candidate_alignment"
    assert_permissions_false(result)


def test_truth_lock_blocks_missing_oos_counts(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(
        report_root,
        candidate_id="c2-eur-buy-stronger-review-ready",
        include_oos=False,
    )

    result = run_walkforward_oos_sufficiency_truth_lock(report_root, build_sample_profit_proof_candidates())

    assert result["walk_forward_oos_status"] == WALK_FORWARD_OOS_BLOCKED_MISSING_EVIDENCE
    assert "oos_segments_total" in result["evidence_missing"]
    assert "oos_segments_passed" in result["evidence_missing"]
    assert result["profit_persistence_unlocked"] is False
    assert_permissions_false(result)


def test_truth_lock_prefers_c2_source_over_older_c1_report(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root, candidate_id="c1-eur-buy")
    (report_root / "AIOS_FOREX_110_C2_WALKFORWARD_OOS_SOURCE_V1.md").write_text(
        "\n".join(
            [
                "- candidate: `c2-eur-buy-stronger-review-ready`",
                "- windows_total: 6",
                "- windows_passed: 6",
                "- oos_segments_total: 4",
                "- oos_segments_passed: 4",
                "- min_pass_rate: 0.75",
                "- max_drawdown: 0.22",
                "- max_allowed_drawdown: 0.5",
                "- sanitized: true",
                "- evidence_age_days: 1",
                "- max_evidence_age_days: 7",
            ]
        ),
        encoding="utf-8",
    )

    result = run_walkforward_oos_sufficiency_truth_lock(report_root, build_sample_profit_proof_candidates())

    assert result["walk_forward_oos_status"] == "BLOCKED_SOURCE_AUTHENTICITY"
    assert "NO_INDEPENDENT_VERIFIER_CONNECTED" in result["blockers"]
    assert result["normalized_walkforward_oos_summary"]["windows_total"] == 6.0
    assert result["normalized_walkforward_oos_summary"]["max_allowed_drawdown"] == 0.5
    assert result["profit_persistence_unlocked"] is False
    assert_permissions_false(result)


def test_report_markdown_contains_attack_to_finish(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root, candidate_id="c1-eur-buy")

    report = build_report_markdown(run_walkforward_oos_sufficiency_truth_lock(report_root, build_sample_profit_proof_candidates()))

    assert "Walk-forward/OOS status: `BLOCKED_TOP_CANDIDATE_MISMATCH`" in report
    assert "ATTACK_TO_FINISH" in report
    assert "owner_approval_created: `false`" in report


def test_runner_writes_state_and_report(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    output_root = tmp_path / "out"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root, candidate_id="c1-eur-buy")

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
    assert state["walk_forward_oos_status"] == WALK_FORWARD_OOS_BLOCKED_TOP_CANDIDATE_MISMATCH
    assert (output_root / REPORT_NAME).exists()
