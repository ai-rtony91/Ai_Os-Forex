from __future__ import annotations

from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_110_c2_real_walkforward_oos_harness_v1 import (  # noqa: E402
    run_c2_real_walkforward_oos_harness,
)
from automation.forex_engine.forex_110_persistent_profitability_period_evidence_v1 import (  # noqa: E402
    PERIOD_EVIDENCE_BLOCKED,
    PERIOD_EVIDENCE_PROVEN,
    PERIOD_EVIDENCE_SAMPLE_TEST_ONLY,
    SOURCE_NAME,
    build_report_markdown,
    run_persistent_profitability_period_evidence,
)
from scripts.forex_delivery.run_forex_110_persistent_profitability_period_evidence_v1 import (  # noqa: E402
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


def write_harness_state(report_root: Path, payload: dict | None = None) -> None:
    report_root.mkdir()
    result = run_c2_real_walkforward_oos_harness(payload)
    (report_root / "AIOS_FOREX_110_C2_REAL_WALKFORWARD_OOS_HARNESS_V1_STATE.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )


def assert_permissions_false(result: dict) -> None:
    for flag in PROTECTED_FLAGS:
        assert result[flag] is False
        assert result["permissions"][flag] is False


def test_default_fixture_cannot_generate_real_period_source(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_harness_state(report_root)

    result = run_persistent_profitability_period_evidence(report_root)

    assert result["period_evidence_status"] == PERIOD_EVIDENCE_SAMPLE_TEST_ONLY
    assert result["evidence_source_classification"] == "SAMPLE_TEST_ONLY"
    assert result["c2_period_source_found"] is True
    assert result["c2_period_source_generated"] is False
    assert result["source_is_test_or_sample"] is True
    assert result["source_is_real_sanitized_local"] is False
    assert result["consecutive_profitable_periods"] == 0
    assert result["min_profitable_periods"] == 3
    assert result["missing_profitable_periods"] == 3
    assert result["closed_trade_count"] == 0
    assert not (report_root / SOURCE_NAME).exists()
    assert_permissions_false(result)


def test_blocks_when_c2_harness_has_only_one_profitable_period(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_harness_state(
        report_root,
        {
            "candidate": "c2-eur-buy-stronger-review-ready",
            "strategy_name": "paper_long_run_supervisor_v2",
            "strategy_version": "c2-real-oos-v1",
            "walkforward_windows": [
                [0.62, -0.20, 0.48, 0.36, -0.14, 0.52, 0.31],
                [0.10, -0.40, -0.20, 0.05, -0.18, 0.02, -0.21],
                [0.08, -0.35, -0.22, 0.03, -0.19, 0.01, -0.20],
                [0.07, -0.33, -0.24, 0.04, -0.20, 0.02, -0.18],
                [0.06, -0.31, -0.25, 0.03, -0.21, 0.01, -0.17],
                [0.05, -0.30, -0.26, 0.02, -0.22, 0.01, -0.16],
            ],
            "oos_segments": [
                [0.44, -0.13, 0.36, 0.28, -0.08, 0.33],
                [0.42, -0.12, 0.34, 0.27, -0.09, 0.31],
                [0.45, -0.14, 0.35, 0.29, -0.10, 0.32],
                [0.43, -0.11, 0.33, 0.26, -0.08, 0.30],
            ],
            "evidence_age_days": 1,
        },
    )
    state = json.loads((report_root / "AIOS_FOREX_110_C2_REAL_WALKFORWARD_OOS_HARNESS_V1_STATE.json").read_text())
    state["harness_status"] = "PROVEN_REAL_WALKFORWARD_OOS_HARNESS"
    state["source_is_real_sanitized_local"] = True
    state["source_is_test_or_sample"] = False
    state["candidate_alignment"] = "ALIGNED"
    (report_root / "AIOS_FOREX_110_C2_REAL_WALKFORWARD_OOS_HARNESS_V1_STATE.json").write_text(
        json.dumps(state),
        encoding="utf-8",
    )

    result = run_persistent_profitability_period_evidence(report_root)

    assert result["period_evidence_status"] == "BLOCKED_UNVERIFIED_C2_PERIOD_SOURCE"
    assert result["consecutive_profitable_periods"] == 1
    assert result["missing_profitable_periods"] == 2
    assert result["c2_period_source_generated"] is False
    assert not (report_root / SOURCE_NAME).exists()
    assert_permissions_false(result)


def test_sample_or_test_source_stays_locked(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_harness_state(report_root)
    state_path = report_root / "AIOS_FOREX_110_C2_REAL_WALKFORWARD_OOS_HARNESS_V1_STATE.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["source_is_test_or_sample"] = True
    state_path.write_text(json.dumps(state), encoding="utf-8")

    result = run_persistent_profitability_period_evidence(report_root)

    assert result["period_evidence_status"] == PERIOD_EVIDENCE_SAMPLE_TEST_ONLY
    assert result["source_is_test_or_sample"] is True
    assert result["c2_period_source_generated"] is False
    assert_permissions_false(result)


def test_report_contains_attack_to_finish_and_locks(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_harness_state(report_root)

    report = build_report_markdown(run_persistent_profitability_period_evidence(report_root))

    assert "ATTACK_TO_FINISH" in report
    assert "next_demo_trade_allowed: `false`" in report
    assert "Period evidence status: `SAMPLE_TEST_ONLY`" in report


def test_runner_writes_state_and_report(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    output_root = tmp_path / "out"
    write_harness_state(report_root)

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
    assert state["period_evidence_status"] == PERIOD_EVIDENCE_SAMPLE_TEST_ONLY
    assert (output_root / REPORT_NAME).exists()


def test_historical_false_proven_harness_cannot_publish_period_source(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    fixture = Path(__file__).with_name("fixtures") / "c2_historical_false_proven_state.json"
    (root / "AIOS_FOREX_110_C2_REAL_WALKFORWARD_OOS_HARNESS_V1_STATE.json").write_bytes(fixture.read_bytes())
    result = run_persistent_profitability_period_evidence(root)
    assert result["period_evidence_status"] == "BLOCKED_UNVERIFIED_C2_PERIOD_SOURCE"
    assert result["source_authentication_status"] == "UNVERIFIED"
    assert result["c2_period_source_generated"] is False
    assert result["source_is_real_sanitized_local"] is False
    assert result["profit_persistence_unlocked"] is False
    assert "NO_INDEPENDENT_VERIFIER_CONNECTED" in result["blockers"]
    assert "precedence" not in result["next_safe_action"].lower()
    assert not (root / SOURCE_NAME).exists()
    assert_permissions_false(result)


def test_historical_period_result_cannot_be_exported_as_real_source():
    import pytest
    from automation.forex_engine.forex_110_persistent_profitability_period_evidence_v1 import build_source_markdown
    root = ROOT / "Reports" / "forex_delivery"
    historical = json.loads((root / "AIOS_FOREX_110_PERSISTENT_PROFITABILITY_PERIOD_EVIDENCE_V1_STATE.json").read_text())
    historical["period_evidence_status"] = PERIOD_EVIDENCE_PROVEN
    historical["source_authentication_status"] = "VERIFIED"
    with pytest.raises(ValueError, match="independent source verifier is unavailable"):
        build_source_markdown(historical)


def test_diagnostic_periods_preserve_failed_windows_and_unverified_costs():
    from automation.forex_engine.forex_110_persistent_profitability_period_evidence_v1 import _period_summary, _profitable_periods_from_harness
    historical = json.loads((Path(__file__).with_name("fixtures") / "c2_historical_false_proven_state.json").read_text())
    historical["walkforward_result"]["window_results"][2]["window_passed"] = False
    periods = _profitable_periods_from_harness(historical)
    summary = _period_summary(historical, periods)
    assert len(periods) == 5
    assert summary["consecutive_profitable_periods"] == 3
    assert summary["after_costs"] is False
    assert summary["cost_verification_status"] == "UNVERIFIED"
    assert summary["expectancy_unit"] == "USD_DIAGNOSTIC"


def test_report_formatter_blocks_historical_and_forged_proof_labels():
    import copy
    historical = json.loads((Path(__file__).with_name("fixtures") / "c2_historical_false_proven_state.json").read_text())
    historical.update(period_evidence_status="PROVEN_PERSISTENT_PROFITABILITY_PERIODS",
                      evidence_source_classification="REAL_SANITIZED_LOCAL_C2_PERIOD_SOURCE",
                      c2_period_source_generated=True, profit_proof_status_after_rerun="PROVEN",
                      profit_truth_lock_status_after_rerun="PROVEN", profit_persistence_unlocked=True)
    historical["source_authentication_status"] = "VERIFIED"
    for key in historical.get("permissions", {}):
        historical["permissions"][key] = True
    before = copy.deepcopy(historical)
    report = build_report_markdown(historical)
    for forbidden in ['PROVEN_PERSISTENT_PROFITABILITY_PERIODS', 'C2 period source generated: `true`', 'Profit proof status after rerun: `PROVEN`', 'Profit persistence unlocked: `true`']:
        assert forbidden not in report
    assert "NO_INDEPENDENT_VERIFIER_CONNECTED" in report
    for flag in PROTECTED_FLAGS:
        assert f"{flag}: `false`" in report
    assert historical == before
