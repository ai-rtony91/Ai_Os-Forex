from __future__ import annotations
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from automation.forex_engine.forex_edge_autopilot_v1 import (  # noqa: E402
    PROTECTED_FALSE_FIELDS,
    build_report_markdown,
    run_forex_edge_autopilot_v1,
)
from scripts.forex_delivery.run_forex_edge_autopilot_v1 import (  # noqa: E402
    REPORT_NAME,
    STATE_NAME,
    main,
)
def write_profitability_report(report_root: Path) -> None:
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "AIOS_FOREX_PROFITABILITY_VERDICT_V1.md").write_text(
        "\n".join(
            [
                "- closed_trade_count: 42",
                "- min_closed_trade_count: 30",
                "- expectancy: 0.26619048",
                "- min_expectancy: 0.05",
                "- profit_factor: 6.85340314",
                "- min_profit_factor: 1.25",
                "- max_drawdown: 0.22",
                "- max_allowed_drawdown: 0.50",
                "- consecutive_profitable_periods: 6",
                "- min_profitable_periods: 4",
                "- after_costs: true",
                "- sanitized: true",
                "- evidence_age_days: 1",
                "- max_evidence_age_days: 7",
            ]
        ),
        encoding="utf-8",
    )
def write_walkforward_report(report_root: Path) -> None:
    (report_root / "AIOS_FOREX_WALK_FORWARD_DEPTH_PACKET_R_V1_REPORT.md").write_text(
        "\n".join(
            [
                "- candidate: `c2-eur-buy-stronger-review-ready`",
                "- windows_total: 6",
                "- windows_passed: 6",
                "- oos_segments_total: 4",
                "- oos_segments_passed: 4",
                "- min_pass_rate: 0.75",
                "- max_drawdown: 0.22",
                "- max_allowed_drawdown: 0.50",
                "- sanitized: true",
                "- evidence_age_days: 1",
                "- max_evidence_age_days: 7",
            ]
        ),
        encoding="utf-8",
    )
def test_autopilot_finds_multiple_review_candidates_without_authority(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_profitability_report(report_root)
    write_walkforward_report(report_root)
    result = run_forex_edge_autopilot_v1(report_root, target_candidate_count=2, cycles=3)
    assert result["status"] == "TARGET_REVIEW_CANDIDATES_FOUND"
    assert result["cycles_completed"] == 1
    assert result["candidate_count"] >= 2
    assert result["candidate_basket"][0]["candidate_id"] == "c2-eur-buy-stronger-review-ready"
    assert result["proof_gates"]["profit_truth_lock_status"] == "PROVEN"
    assert result["proof_gates"]["walk_forward_oos_status"] == "PROVEN"
    assert result["false_positive_controls"]["weak_candidates_rejected"] >= 2
    for field in PROTECTED_FALSE_FIELDS:
        assert result[field] is False
        assert result["permissions"][field] is False
def test_autopilot_continues_when_target_count_not_met(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_profitability_report(report_root)
    write_walkforward_report(report_root)
    result = run_forex_edge_autopilot_v1(report_root, target_candidate_count=5, cycles=2)
    assert result["status"] == "SEARCH_CONTINUES_REPO_SAFE"
    assert result["cycles_completed"] == 2
    assert result["stop_reason"] == "BROKER_PRACTICE_READ_ONLY_BOUNDARY_OR_MORE_DATA_REQUIRED"
def test_report_and_cli_write_outputs(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    output_root = tmp_path / "out"
    write_profitability_report(report_root)
    write_walkforward_report(report_root)
    assert main([
        "--report-root", str(report_root),
        "--output-root", str(output_root),
        "--target-candidates", "2",
        "--cycles", "2",
        "--write-state",
        "--write-report",
    ]) == 0
    state = json.loads((output_root / STATE_NAME).read_text(encoding="utf-8"))
    report = (output_root / REPORT_NAME).read_text(encoding="utf-8")
    assert state["status"] == "TARGET_REVIEW_CANDIDATES_FOUND"
    assert "AIOS Forex Edge Autopilot V1" in report
    assert "c2-eur-buy-stronger-review-ready" in report
    assert "Demo/live/order authority: false" in report
def test_build_report_handles_empty_candidates() -> None:
    report = build_report_markdown(
        {
            "packet_id": "test",
            "status": "SEARCH_CONTINUES_REPO_SAFE",
            "stop_reason": "MORE_DATA_REQUIRED",
            "cycles_completed": 1,
            "cycles_requested": 1,
            "candidate_count": 0,
            "target_candidate_count": 3,
            "candidate_basket": [],
            "proof_gates": {},
            "rejected_or_blocked_candidates": [],
            "next_safe_action": "continue",
        }
    )
    assert "- none" in report
    assert "continue" in report
