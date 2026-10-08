from __future__ import annotations
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from automation.forex_engine.forex_bait_factory_v1 import (  # noqa: E402
    PROTECTED_FALSE_FIELDS,
    build_report_markdown,
    run_forex_bait_factory_v1,
)
from scripts.forex_delivery.run_forex_bait_factory_v1 import (  # noqa: E402
    REPORT_NAME,
    STATE_NAME,
    main,
)
def test_bait_factory_does_not_promote_unbound_hypotheses(tmp_path: Path) -> None:
    result = run_forex_bait_factory_v1(
        report_root=tmp_path / "empty", target_bait_count=3, cycles=2
    )
    assert result["pipeline"] == [
        "hypothesis_builder", "warm_cold_scorer", "proof_ledger",
        "edge_autopilot", "paper_campaign_handoff",
    ]
    assert result["status"] == "BAIT_SEARCH_CONTINUES"
    assert result["bait_count"] == 0
    assert result["label_counts"] == {"HOT": 0, "WARM": 0, "COLD": 0, "UNTESTED": 5}
    assert all(item["next_step"] == "collect_candidate_specific_evidence" for item in result["bait_box"])
    assert all(item["expectancy"] is None and item["profit_factor"] is None for item in result["bait_box"])
    assert result["proof_ledger"]["top_candidate_id"] == "NONE"
    assert result["edge_autopilot"]["candidate_count"] == 0
    assert result["paper_campaign_handoff"]["handoff_status"] == "BLOCKED_NO_CANDIDATE_PROOF"
    for field in PROTECTED_FALSE_FIELDS:
        assert result[field] is False
        assert result["permissions"][field] is False
def test_bait_factory_target_not_met_keeps_search_open() -> None:
    result = run_forex_bait_factory_v1(target_bait_count=10, cycles=2)
    assert result["status"] == "BAIT_SEARCH_CONTINUES"
    assert result["cycles_completed"] == 2
    assert result["stop_reason"] == "TARGET_BAIT_COUNT_NOT_MET_REPO_SAFE"
def test_bait_factory_report_and_cli_write_outputs(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    assert main([
        "--report-root", str(tmp_path / "empty"),
        "--output-root", str(output_root),
        "--target-bait", "3",
        "--cycles", "2",
        "--write-state",
        "--write-report",
    ]) == 0
    state = json.loads((output_root / STATE_NAME).read_text(encoding="utf-8"))
    report = (output_root / REPORT_NAME).read_text(encoding="utf-8")
    assert state["status"] == "BAIT_SEARCH_CONTINUES"
    assert state["bait_count"] == 0
    assert "AIOS Forex Bait Factory V1" in report
    assert "hypothesis_builder -> warm_cold_scorer -> proof_ledger -> edge_autopilot -> paper_campaign_handoff" in report
    assert "Broker/API calls: false" in report
def test_factory_candidate_counts_do_not_depend_on_cwd(tmp_path: Path, monkeypatch) -> None:
    report_root = ROOT / "Reports" / "forex_delivery"
    first = run_forex_bait_factory_v1(report_root=report_root)
    monkeypatch.chdir(tmp_path)
    second = run_forex_bait_factory_v1(report_root=report_root)
    assert [(row["candidate_id"], row["closed_trade_count"]) for row in first["bait_box"]] == [
        (row["candidate_id"], row["closed_trade_count"]) for row in second["bait_box"]
    ]
    assert first["bait_count"] == second["bait_count"] == 0


def test_build_report_handles_empty_bait() -> None:
    report = build_report_markdown(
        {
            "packet_id": "test",
            "status": "BAIT_SEARCH_CONTINUES",
            "stop_reason": "TARGET_BAIT_COUNT_NOT_MET_REPO_SAFE",
            "cycles_completed": 1,
            "cycles_requested": 1,
            "bait_count": 0,
            "target_bait_count": 3,
            "bait_box": [],
            "label_counts": {"HOT": 0, "WARM": 0, "COLD": 0},
            "paper_campaign_handoff": {"handoff_status": "BLOCKED", "command": ""},
            "next_safe_action": "keep searching",
        }
    )
    assert "- none" in report
    assert "keep searching" in report

