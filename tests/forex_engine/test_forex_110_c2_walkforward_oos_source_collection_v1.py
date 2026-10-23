from __future__ import annotations

from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_110_c2_walkforward_oos_source_collection_v1 import (  # noqa: E402
    REAL_SANITIZED_LOCAL_SOURCE_FOUND,
    SAMPLE_TEST_ONLY,
    SOURCE_UNAVAILABLE,
    TARGET_CANDIDATE_ID,
    build_report_markdown,
    build_source_markdown,
    collect_c2_walkforward_oos_source,
)
from scripts.forex_delivery.run_forex_110_c2_walkforward_oos_source_collection_v1 import (  # noqa: E402
    REPORT_NAME,
    SOURCE_REPORT_NAME,
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


def write_walkforward_report(report_root: Path, candidate_id: str = "c1-eur-buy") -> None:
    (report_root / "AIOS_FOREX_WALK_FORWARD_DEPTH_PACKET_R_V1_REPORT.md").write_text(
        "\n".join(
            [
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
        ),
        encoding="utf-8",
    )


def write_c2_source(report_root: Path) -> Path:
    path = report_root / "AIOS_FOREX_110_C2_REAL_SOURCE.md"
    path.write_text(
        "\n".join(
            [
                f"- candidate: `{TARGET_CANDIDATE_ID}`",
                "- windows_total: 6",
                "- windows_passed: 6",
                "- oos_segments_total: 4",
                "- oos_segments_passed: 4",
                "- min_pass_rate: 0.75",
                "- max_drawdown: 0.02",
                "- max_allowed_drawdown: 0.05",
                "- sanitized: true",
                "- evidence_age_days: 1",
                "- max_evidence_age_days: 7",
            ]
        ),
        encoding="utf-8",
    )
    return path


def assert_permissions_false(result: dict) -> None:
    for flag in PROTECTED_FLAGS:
        assert result[flag] is False
        assert result["permissions"][flag] is False


def test_source_collection_blocks_when_only_c1_walkforward_source_exists(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root)

    result = collect_c2_walkforward_oos_source(
        report_root,
        search_roots=[report_root],
        repo_root=tmp_path,
    )

    assert result["evidence_source_classification"] == SOURCE_UNAVAILABLE
    assert result["c2_source_found"] is False
    assert result["c2_source_generated"] is False
    assert result["source_path"] is None
    assert result["source_is_real_sanitized_local"] is False
    assert result["oos_segments_total"] is None
    assert result["profit_persistence_unlocked"] is False
    assert_permissions_false(result)


def test_source_collection_records_sample_test_only_without_promotion(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    tests_root = tmp_path / "tests" / "forex_engine"
    report_root.mkdir()
    tests_root.mkdir(parents=True)
    write_profitability_report(report_root)
    write_walkforward_report(report_root)
    write_c2_source(tests_root)

    result = collect_c2_walkforward_oos_source(
        report_root,
        search_roots=[report_root, tests_root],
        repo_root=tmp_path,
    )

    assert result["evidence_source_classification"] == SAMPLE_TEST_ONLY
    assert result["source_is_test_or_sample"] is True
    assert result["source_is_real_sanitized_local"] is False
    assert result["source_path"] is None
    assert "oos_segments_total" in result["attack_to_finish"]["missing_evidence_field"]
    assert_permissions_false(result)


def test_complete_non_test_summary_is_unverified_without_source_receipts(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    source_root = tmp_path / "evidence"
    report_root.mkdir()
    source_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root, candidate_id=TARGET_CANDIDATE_ID)
    source_path = write_c2_source(source_root)

    result = collect_c2_walkforward_oos_source(
        report_root,
        search_roots=[source_root],
        repo_root=tmp_path,
    )

    assert result["evidence_source_classification"] == "UNVERIFIED_LOCAL_SUMMARY"
    assert result["c2_source_found"] is False
    assert result["source_path"] is None
    assert source_path.relative_to(tmp_path).as_posix() in result["diagnostic_source_paths"]
    assert result["candidate_alignment"] == "BLOCKED_NO_REAL_C2_OOS_SOURCE"
    assert result["oos_segments_total"] is None
    assert result["source_is_real_sanitized_local"] is False
    assert "NO_INDEPENDENT_VERIFIER_CONNECTED" in result["blockers"]
    import pytest
    with pytest.raises(ValueError, match="independent source verifier is unavailable"):
        build_source_markdown(result)
    assert_permissions_false(result)


def test_report_markdown_contains_attack_to_finish(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root)

    report = build_report_markdown(
        collect_c2_walkforward_oos_source(report_root, search_roots=[report_root], repo_root=tmp_path)
    )

    assert "Source collection status: `BLOCKED_NO_REAL_C2_OOS_SOURCE`" in report
    assert "ATTACK_TO_FINISH" in report
    assert "owner_approval_created: `false`" in report


def test_runner_writes_state_report_and_only_real_source_report(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    output_root = tmp_path / "out"
    report_root.mkdir()
    write_profitability_report(report_root)
    write_walkforward_report(report_root)

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
    assert state["c2_source_found"] is False
    assert (output_root / REPORT_NAME).exists()
    assert not (output_root / SOURCE_REPORT_NAME).exists()


def test_collector_source_formatter_rejects_forged_real_classification():
    import pytest
    result = {"evidence_source_classification": REAL_SANITIZED_LOCAL_SOURCE_FOUND,
              "source_is_real_sanitized_local": True,
              "source_authentication_status": "VERIFIED"}
    with pytest.raises(ValueError, match="independent source verifier is unavailable"):
        build_source_markdown(result)


def test_report_formatter_blocks_historical_and_forged_proof_labels():
    import copy
    historical = json.loads((Path(__file__).with_name("fixtures") / "c2_historical_false_proven_state.json").read_text())
    historical.update(source_collection_status="PROVEN_REAL_SANITIZED_LOCAL_C2_SOURCE",
                      evidence_source_classification="REAL_SANITIZED_LOCAL_SOURCE_FOUND",
                      c2_source_found=True, c2_source_generated=True,
                      walkforward_oos_status_after_rerun="PROVEN", profit_persistence_unlocked=True)
    historical["source_authentication_status"] = "VERIFIED"
    for key in historical.get("permissions", {}):
        historical["permissions"][key] = True
    before = copy.deepcopy(historical)
    report = build_report_markdown(historical)
    for forbidden in ['PROVEN_REAL_SANITIZED_LOCAL_C2_SOURCE', 'C2 source found: `true`', 'C2 source generated: `true`', 'Source is real sanitized local: `true`', 'Profit persistence unlocked: `true`']:
        assert forbidden not in report
    assert "NO_INDEPENDENT_VERIFIER_CONNECTED" in report
    for flag in PROTECTED_FLAGS:
        assert f"{flag}: `false`" in report
    assert historical == before
