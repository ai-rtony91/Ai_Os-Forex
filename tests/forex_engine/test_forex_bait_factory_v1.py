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
def test_bait_factory_builds_hot_warm_cold_chain_without_trading() -> None:
    result = run_forex_bait_factory_v1(target_bait_count=3, cycles=2)
    assert result["status"] == "BAIT_READY_FOR_REVIEW"
    assert result["pipeline"] == [
        "hypothesis_builder",
        "warm_cold_scorer",
        "proof_ledger",
        "edge_autopilot",
        "paper_campaign_handoff",
    ]
    assert result["bait_count"] >= 3
    assert result["label_counts"]["HOT"] >= 1
    assert result["label_counts"]["WARM"] >= 1
    assert result["label_counts"]["COLD"] >= 1
    risky = next(item for item in result["bait_box"] if item["candidate_id"] == "c5-gbp-buy")
    assert risky["label"] == "COLD"
    assert result["paper_campaign_handoff"]["handoff_status"] == "READY_WHEN_BAIT_BOX_EMPTY_OR_OWNER_PRACTICE_CREDS_PRESENT"
    assert result["paper_campaign_handoff"]["command"]
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
        "--output-root", str(output_root),
        "--target-bait", "3",
        "--cycles", "2",
        "--write-state",
        "--write-report",
    ]) == 0
    state = json.loads((output_root / STATE_NAME).read_text(encoding="utf-8"))
    report = (output_root / REPORT_NAME).read_text(encoding="utf-8")
    assert state["status"] == "BAIT_READY_FOR_REVIEW"
    assert "AIOS Forex Bait Factory V1" in report
    assert "hypothesis_builder -> warm_cold_scorer -> proof_ledger -> edge_autopilot -> paper_campaign_handoff" in report
    assert "Broker/API calls: false" in report
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

