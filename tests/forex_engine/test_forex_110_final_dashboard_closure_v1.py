from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_110_final_dashboard_closure_v1 import (  # noqa: E402
    build_clickable_emoji_window_map_markdown,
    build_dashboard_contract_markdown,
    build_report_markdown,
    run_forex_110_final_dashboard_closure_v1,
)
from scripts.forex_delivery.run_forex_110_final_dashboard_closure_v1 import (  # noqa: E402
    BITWARDEN_BLOCKER_NAME,
    DOC_CLOSURE_NAME,
    DOC_CONTRACT_NAME,
    DOC_WINDOW_MAP_NAME,
    INDEX_NAME,
    PROTECTED_BOUNDARY_NAME,
    REPORT_CONTRACT_NAME,
    REPORT_NAME,
    STATE_NAME,
    main,
)


PROTECTED_FLAGS = (
    "broker_api_used",
    "credentials_used",
    "env_read",
    "account_identifiers_used",
    "order_execution",
    "demo_authorized",
    "live_authorized",
    "scheduler_started",
    "daemon_started",
    "webhook_started",
    "background_loop_started",
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


def write_required_states(report_root: Path) -> None:
    report_root.mkdir(parents=True)
    (report_root / "AIOS_FOREX_110_PROFIT_EVIDENCE_TRUTH_LOCK_V1_STATE.json").write_text(
        json.dumps(
            {
                "truth_lock_status": "PROVEN",
                "profit_proof_status": "PROVEN",
                "persistent_profitability_status": "PERSISTENT_PROFITABILITY_READY",
            }
        ),
        encoding="utf-8",
    )
    (report_root / "AIOS_FOREX_110_PERSISTENT_PROFITABILITY_PERIOD_EVIDENCE_V1_STATE.json").write_text(
        json.dumps(
            {
                "period_evidence_status": "PROVEN_PERSISTENT_PROFITABILITY_PERIODS",
                "consecutive_profitable_periods": 6,
                "min_profitable_periods": 3,
            }
        ),
        encoding="utf-8",
    )
    (report_root / "AIOS_FOREX_110_PERSISTENT_PROFITABILITY_PERIOD_SOURCE_V1.md").write_text(
        "persistent profitability period source\n",
        encoding="utf-8",
    )
    (report_root / "AIOS_FOREX_110_WALKFORWARD_OOS_SUFFICIENCY_TRUTH_LOCK_V1_STATE.json").write_text(
        json.dumps({"truth_lock_status": "PROVEN", "walk_forward_oos_status": "PROVEN"}),
        encoding="utf-8",
    )
    (report_root / "AIOS_FOREX_110_C2_REAL_WALKFORWARD_OOS_HARNESS_V1_STATE.json").write_text(
        json.dumps({"harness_status": "PROVEN_REAL_WALKFORWARD_OOS_HARNESS"}),
        encoding="utf-8",
    )
    (report_root / "AIOS_FOREX_110_C2_WALKFORWARD_OOS_SOURCE_COLLECTION_V1_STATE.json").write_text(
        json.dumps({"source_collection_status": "PROVEN_REAL_SANITIZED_LOCAL_C2_SOURCE"}),
        encoding="utf-8",
    )
    (report_root / "AIOS_FOREX_110_C2_WALKFORWARD_OOS_EVIDENCE_GENERATION_V1_STATE.json").write_text(
        json.dumps({"c2_oos_evidence_status": "PROVEN"}),
        encoding="utf-8",
    )


def assert_protected_flags_false(result: dict) -> None:
    for flag in PROTECTED_FLAGS:
        assert result[flag] is False
        assert result["protected_permission_flags"][flag] is False
    assert result["all_protected_permission_flags_false"] is True


def test_closure_returns_required_review_ready_state(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_required_states(report_root)

    result = run_forex_110_final_dashboard_closure_v1(report_root)

    assert result["closure_status"] == "READY_FOR_OWNER_REVIEW"
    assert result["repo_safe_completion_status"] == "FOREX_110_REPO_SAFE_PROOF_CHAIN_REVIEW_READY"
    assert result["profit_truth_lock_status"] == "PROVEN"
    assert result["profit_proof_status"] == "PROVEN"
    assert result["persistent_profitability_status"] == "READY"
    assert result["walkforward_oos_status"] == "PROVEN"
    assert result["c2_source_status"] == "PROVEN"
    assert result["dashboard_completion_status"] == "COMPLETE"
    assert result["protected_boundary_status"] == "LOCKED_FALSE"
    assert result["bitwarden_blocked_until_forex_110_complete"] is True
    assert result["ATTACK_TO_FINISH"]["blocker_id"] == "NO_BLOCKER"
    assert_protected_flags_false(result)


def test_dashboard_contract_and_window_map_include_required_windows(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    write_required_states(report_root)
    result = run_forex_110_final_dashboard_closure_v1(report_root)

    contract = build_dashboard_contract_markdown(result)
    window_map = build_clickable_emoji_window_map_markdown(result)
    report = build_report_markdown(result)

    for section in (
        "Command Center",
        "Safety Gate",
        "Candidate",
        "Evidence",
        "Profit Proof",
        "Broker Boundary",
        "Reports",
        "SOS / Owner Wake",
        "Settings Placeholder",
        "Secrets Later",
    ):
        assert section in contract
        assert section in window_map
    assert "No profit guarantee" in report
    assert "No autonomous real-money trading" in report


def test_runner_writes_allowed_outputs(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    output_root = tmp_path / "out"
    doc_root = tmp_path / "docs"
    write_required_states(report_root)

    exit_code = main(
        [
            "--report-root",
            str(report_root),
            "--output-root",
            str(output_root),
            "--doc-root",
            str(doc_root),
            "--write-state",
            "--write-report",
            "--write-index",
            "--write-dashboard-contract",
            "--write-protected-boundary-handoff",
            "--write-bitwarden-blocker",
        ]
    )

    state = json.loads((output_root / STATE_NAME).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert state["closure_status"] == "READY_FOR_OWNER_REVIEW"
    for path in (
        output_root / REPORT_NAME,
        output_root / INDEX_NAME,
        output_root / REPORT_CONTRACT_NAME,
        output_root / PROTECTED_BOUNDARY_NAME,
        output_root / BITWARDEN_BLOCKER_NAME,
        doc_root / DOC_CLOSURE_NAME,
        doc_root / DOC_CONTRACT_NAME,
        doc_root / DOC_WINDOW_MAP_NAME,
    ):
        assert path.exists()


def test_committed_dashboard_cache_agrees_with_corrected_candidate_proof():
    root = ROOT / "Reports" / "forex_delivery"
    fresh = run_forex_110_final_dashboard_closure_v1(root)
    cached = json.loads((root / "AIOS_FOREX_110_FINAL_DASHBOARD_CLOSURE_V1_STATE.json").read_text())
    for field in ("closure_status", "profit_proof_status", "dashboard_completion_status"):
        assert fresh[field] == "BLOCKED"
        assert cached[field] == fresh[field]
    assert cached["clickable_emoji_windows"] == fresh["clickable_emoji_windows"]
    for flag in PROTECTED_FLAGS:
        assert cached[flag] is False


def test_blocked_completion_index_does_not_claim_review_ready():
    from automation.forex_engine.forex_110_final_dashboard_closure_v1 import build_completion_index_markdown
    result = run_forex_110_final_dashboard_closure_v1(ROOT / "Reports" / "forex_delivery")
    assert result["closure_status"] == "BLOCKED"
    report = build_completion_index_markdown(result)
    assert "Forex 110 repo-safe proof chain is review-ready" not in report
    assert "Forex 110 repo-safe proof chain remains blocked" in report


def closure_with_truth_lock(truth_lock: dict, c2_status: str = "PROVEN") -> dict:
    states = {
        "AIOS_FOREX_110_PROFIT_EVIDENCE_TRUTH_LOCK_V1_STATE.json": truth_lock,
        "AIOS_FOREX_110_PERSISTENT_PROFITABILITY_PERIOD_EVIDENCE_V1_STATE.json": {
            "period_evidence_status": "PROVEN_PERSISTENT_PROFITABILITY_PERIODS",
        },
        "AIOS_FOREX_110_WALKFORWARD_OOS_SUFFICIENCY_TRUTH_LOCK_V1_STATE.json": {
            "truth_lock_status": "PROVEN",
        },
        "AIOS_FOREX_110_C2_REAL_WALKFORWARD_OOS_HARNESS_V1_STATE.json": {
            "harness_status": "PROVEN_REAL_WALKFORWARD_OOS_HARNESS",
        },
        "AIOS_FOREX_110_C2_WALKFORWARD_OOS_SOURCE_COLLECTION_V1_STATE.json": {
            "source_collection_status": "PROVEN_REAL_SANITIZED_LOCAL_C2_SOURCE",
        },
        "AIOS_FOREX_110_C2_WALKFORWARD_OOS_EVIDENCE_GENERATION_V1_STATE.json": {
            "c2_oos_evidence_status": c2_status,
        },
    }
    with patch(
        "automation.forex_engine.forex_110_final_dashboard_closure_v1._read_json",
        side_effect=lambda path: states[path.name],
    ):
        return run_forex_110_final_dashboard_closure_v1()


def test_blocked_clickable_window_summaries_agree_with_source_statuses() -> None:
    result = run_forex_110_final_dashboard_closure_v1(ROOT / "Reports" / "forex_delivery")
    summaries = {window["target"]: window["default_summary"] for window in result["clickable_emoji_windows"]}

    assert result["closure_status"] == "BLOCKED"
    assert result["profit_proof_status"] == "BLOCKED"
    assert summaries["command_center"] == "Forex 110 blocked state and next safe action."
    assert summaries["candidate"] == "No top candidate is available for owner review."
    assert summaries["profit_proof"] == "Profit proof is blocked for owner review only."
    window_map = build_clickable_emoji_window_map_markdown(result)
    assert "review-ready" not in window_map
    assert "Profit proof is proven" not in window_map
    assert_protected_flags_false(result)


def test_ready_clickable_window_summaries_preserve_source_proof_status() -> None:
    result = closure_with_truth_lock({
        "truth_lock_status": "PROVEN",
        "profit_proof_status": "PROVEN",
        "persistent_profitability_status": "PERSISTENT_PROFITABILITY_READY",
        "top_candidate_id": "C2",
    })
    summaries = {window["target"]: window["default_summary"] for window in result["clickable_emoji_windows"]}

    assert result["closure_status"] == "READY_FOR_OWNER_REVIEW"
    assert result["profit_proof_status"] == "PROVEN"
    assert summaries["command_center"] == "Forex 110 review-ready state and next safe action."
    assert summaries["candidate"] == "Top candidate is review-ready only."
    assert summaries["profit_proof"] == "Profit proof is proven for owner review only."
    window_map = build_clickable_emoji_window_map_markdown(result)
    assert all(summary in window_map for summary in summaries.values())
    assert_protected_flags_false(result)


def test_ready_closure_does_not_manufacture_a_top_candidate() -> None:
    for candidate_id in (None, "", "NONE"):
        result = closure_with_truth_lock({
            "truth_lock_status": "PROVEN",
            "profit_proof_status": "PROVEN",
            "persistent_profitability_status": "PERSISTENT_PROFITABILITY_READY",
            "top_candidate_id": candidate_id,
        })
        summaries = {window["target"]: window["default_summary"] for window in result["clickable_emoji_windows"]}

        assert result["closure_status"] == "READY_FOR_OWNER_REVIEW"
        assert summaries["candidate"] == "No top candidate is available for owner review."


def test_blocked_closure_projects_profit_proof_status_independently() -> None:
    for status in ("BLOCKED", "UNKNOWN", "PROVEN"):
        truth_lock = {
            "truth_lock_status": "PROVEN",
            "persistent_profitability_status": "PERSISTENT_PROFITABILITY_READY",
            "top_candidate_id": "C2",
        }
        if status != "UNKNOWN":
            truth_lock["profit_proof_status"] = status
        result = closure_with_truth_lock(truth_lock, c2_status="BLOCKED")
        summaries = {window["target"]: window["default_summary"] for window in result["clickable_emoji_windows"]}

        assert result["closure_status"] == "BLOCKED"
        assert result["profit_proof_status"] == status
        assert summaries["profit_proof"] == f"Profit proof is {status.lower()} for owner review only."
        assert summaries["candidate"] == "Top candidate has not cleared the proof chain."
        assert summaries["command_center"] == "Forex 110 blocked state and next safe action."
        assert_protected_flags_false(result)
