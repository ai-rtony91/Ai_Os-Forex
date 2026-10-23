from __future__ import annotations

from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_110_c2_walkforward_oos_evidence_generation_v1 import (  # noqa: E402
    BLOCKED_NO_REAL_C2_OOS_SOURCE,
    BLOCKED_TOP_CANDIDATE_MISMATCH,
    TARGET_CANDIDATE_ID,
    build_report_markdown,
    run_c2_walkforward_oos_evidence_generation,
)
from scripts.forex_delivery.run_forex_110_c2_walkforward_oos_evidence_generation_v1 import (  # noqa: E402
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


def write_walkforward_report(
    report_root: Path,
    *,
    candidate_id: str,
    include_oos: bool = True,
) -> None:
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


def test_c2_generator_blocks_when_only_c1_walkforward_source_exists(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root, candidate_id="c1-eur-buy")

    result = run_c2_walkforward_oos_evidence_generation(report_root)

    assert result["target_candidate_id"] == TARGET_CANDIDATE_ID
    assert result["c2_oos_evidence_status"] == BLOCKED_TOP_CANDIDATE_MISMATCH
    assert result["candidate_alignment"] == "TOP_CANDIDATE_MISMATCH"
    assert result["oos_segments_total"] is None
    assert result["oos_segments_passed"] is None
    assert result["evidence_source_classification"] == "SAMPLE_TEST_ONLY"
    assert "c1-eur-buy" in result["walkforward_source_candidate_ids"]
    assert_permissions_false(result)


def test_complete_aligned_summary_does_not_create_candidate_or_oos_proof(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root, candidate_id=TARGET_CANDIDATE_ID)

    result = run_c2_walkforward_oos_evidence_generation(report_root)

    assert result["c2_oos_evidence_status"] == BLOCKED_TOP_CANDIDATE_MISMATCH
    assert result["candidate_alignment"] == "TOP_CANDIDATE_MISMATCH"
    assert result["oos_segments_total"] is None
    assert result["oos_segments_passed"] is None
    assert result["required_proof_fields"]["candidate"] is None
    assert result["top_candidate_id"] == "NONE"
    assert result["profit_persistence_unlocked"] is False
    assert result["attack_to_finish"]["blocker_status"] == "BLOCKED"
    assert_permissions_false(result)


def test_c2_generator_blocks_incomplete_aligned_local_evidence(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root, candidate_id=TARGET_CANDIDATE_ID, include_oos=False)

    result = run_c2_walkforward_oos_evidence_generation(report_root)

    assert result["c2_oos_evidence_status"] == BLOCKED_TOP_CANDIDATE_MISMATCH
    assert result["candidate_alignment"] == "TOP_CANDIDATE_MISMATCH"
    assert "oos_segments_total" in result["walkforward_intake_missing_fields"]
    assert "oos_segments_passed" in result["walkforward_intake_missing_fields"]
    assert result["profit_persistence_unlocked"] is False
    assert_permissions_false(result)


def test_report_markdown_records_blocked_without_candidate_intake_pattern(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root, candidate_id="c1-eur-buy")

    report = build_report_markdown(run_c2_walkforward_oos_evidence_generation(report_root))

    assert "C2 evidence status: `BLOCKED_TOP_CANDIDATE_MISMATCH`" in report
    assert "candidate_alignment: `TOP_CANDIDATE_MISMATCH`" in report
    assert "- candidate: `" not in report
    assert "ATTACK_TO_FINISH" in report


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
    assert state["c2_oos_evidence_status"] == BLOCKED_TOP_CANDIDATE_MISMATCH
    assert (output_root / REPORT_NAME).exists()
