from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from automation.forex_engine.consolidated_readiness_blocker_closure_v1 import (
    BLOCKED_BY_POLICY,
    BLOCKED_BY_RISK,
    BLOCKED_BY_BROKER_GATE,
    CANONICAL_BLOCKERS,
    PROFITABLE_LIVE_BOT_READY,
    REQUIRE_MORE_EVIDENCE,
    build_profitable_live_bot_final_status,
    run_consolidated_readiness_blocker_closure_v1,
)
from automation.forex_engine.candidate_intake_demo_review_bridge import (
    run_candidate_intake_demo_review_bridge,
)


def _base_payload():
    return {
        "candidate": {
            "candidate_id": "c1-eur-buy",
            "strategy_name": "ema_mean_reversion",
            "pair": "EURUSD",
            "direction": "buy",
            "walk_forward_status": "passed",
            "mitigation_status": "improved",
        },
        "paper_metrics": {
            "total_trades": 120,
            "closed_trades": 120,
            "win_rate": 0.61,
            "expectancy": 0.12,
            "profit_factor": 1.8,
            "max_drawdown": 0.05,
            "risk_of_ruin": 0.01,
            "risk_adjusted_return": 0.20,
            "sample_size": 120,
        },
        "walk_forward_status": "passed",
        "validation_results": [{"id": "v1"}],
        "validation_payload": {"status": "PASS"},
        "candidate_approved_for_demo_validation": True,
        "demo_validation_contract": {"demo_validation_contract_completed": True, "status": "COMPLETE"},
        "live_readiness_candidate": {"candidate_id": "c1-eur-buy", "live_ready": True},
        "approval_trace": {"signed": True, "reviewed_by": "review_lead"},
        "risk_limits": {"max_drawdown_limit": 0.10},
        "kill_switch_proof": {"status": "PASS", "timestamp": "2026-06-22T00:00:00+00:00"},
        "rollback_proof": {"status": "PASS"},
        "reconciliation_proof": {"status": "PASS"},
        "evidence_timestamp": datetime.now(timezone.utc).isoformat(),
        "replayability_proof": {"status": "PASS"},
        "final_disarm_proof": {"status": "PASS"},
        "post_trade_journal_path": "/tmp/post_trade_journal.csv",
        "one_shot_exception_package": {"exception_package_completed": True},
        "live_review_certificate": {"certificate_completed": True},
        "human_review_ready": True,
    }


def _full_demo_ready_payload():
    payload = _base_payload()
    payload["validation_results"] = [{"status": "PASS"}]
    return payload


def _full_live_ready_payload():
    payload = _full_demo_ready_payload()
    payload["live_readiness_candidate"] = {"live_ready": True}
    return payload


def _approval_window():
    now = datetime.now(timezone.utc)
    return {
        "starts_at_utc": (now - timedelta(minutes=5)).isoformat(),
        "expires_at_utc": (now + timedelta(hours=1)).isoformat(),
    }


def _live_exception_contracts():
    window = _approval_window()
    return {
        "request": {
            "packet_id": "AIOS-FOREX-FINAL-READINESS-TEST",
            "approval_window": dict(window),
            "broker_path": "approved-human-owner-vault-handle",
            "instrument": "EUR_USD",
            "side": "buy",
            "units": 1,
            "max_loss": 1.0,
            "daily_loss_cap": 2.0,
            "stop_loss": 1.0,
            "take_profit": 2.0,
            "order_type": "market",
            "evidence_bundle_id": "evidence-final-readiness-test",
            "kill_switch_required": True,
            "approval_nonce_hash": "sha256:redacted-test-nonce",
            "arming_step": "manual-human-owner-arm",
            "stop_point": "hard-stop-before-live-execution",
            "one_order_only": True,
            "retry_allowed": False,
            "autonomous_reentry_allowed": False,
        },
        "approval": {
            "packet_id": "AIOS-FOREX-FINAL-READINESS-TEST",
            "human_owner": "Anthony",
            "approval_type": "single_live_micro_trade_exception",
            "approval_window": dict(window),
            "broker_path": "approved-human-owner-vault-handle",
            "instrument": "EUR_USD",
            "side": "buy",
            "units": 1,
            "max_loss": 1.0,
            "daily_loss_cap": 2.0,
            "stop_loss": 1.0,
            "take_profit": 2.0,
            "order_type": "market",
            "evidence_bundle_id": "evidence-final-readiness-test",
            "approval_nonce_hash": "sha256:redacted-test-nonce",
            "arming_step": "manual-human-owner-arm",
            "stop_point": "hard-stop-before-live-execution",
            "non_transferable": True,
            "expires_after_use": True,
            "validator_authority": False,
            "dashboard_authority": False,
            "router_authority": False,
        },
        "evidence_bundle": {
            "evidence_bundle_id": "evidence-final-readiness-test",
            "packet_id": "AIOS-FOREX-FINAL-READINESS-TEST",
            "broker_sandbox_or_demo_proof": True,
            "risk_gate_passed": True,
            "kill_switch_active": True,
            "daily_loss_cap_active": True,
            "approval_hash_verified": True,
            "sanitized": True,
            "owner_live_exception_request": True,
            "owner_approval_required": True,
            "owner_approval_present": True,
            "arming_timestamp": datetime.now(timezone.utc).isoformat(),
            "kill_switch_confirmed": True,
            "max_loss_confirmed": True,
            "daily_stop_confirmed": True,
            "stop_loss_confirmed": True,
            "take_profit_confirmed": True,
            "one_order_only_confirmed": True,
            "micro_size_confirmed": True,
            "low_effective_leverage_confirmed": True,
            "sanitized_evidence_only": True,
            "no_credential_read": True,
            "no_credential_write": True,
            "no_env_read": True,
            "no_env_write": True,
            "no_account_id_read": True,
            "no_account_id_write": True,
            "no_network_call": True,
            "no_broker_mutation": True,
            "no_live_order_execution": True,
            "scheduler_enabled": False,
            "daemon_enabled": False,
            "webhook_enabled": False,
            "background_execution": False,
            "credential_read": False,
            "credential_write": False,
            "env_read": False,
            "env_write": False,
            "account_id_read": False,
            "account_id_write": False,
            "network_call": False,
            "broker_mutation": False,
            "live_order_execution": False,
        },
        "arming_state": {
            "packet_id": "AIOS-FOREX-FINAL-READINESS-TEST",
            "approval_nonce_hash": "sha256:redacted-test-nonce",
            "evidence_bundle_id": "evidence-final-readiness-test",
            "kill_switch_active": True,
            "daily_loss_cap_active": True,
            "evidence_bundle_present": True,
            "approval_hash_verified": True,
            "approval_window_active": True,
            "one_order_remaining": True,
            "armed": True,
            "orders_remaining": 1,
        },
    }


def _final_status_payload():
    payload = _full_live_ready_payload()
    payload["paper_metrics"]["sample_size"] = 30
    payload["paper_metrics"]["closed_trades"] = 30
    payload["paper_metrics"]["total_trades"] = 30
    payload["walk_forward_result"] = {
        "windows_evaluated": 3,
        "passing_windows": 3,
        "walk_forward_gate_cleared": True,
    }
    payload["risk_limits"] = {
        "maximum_loss": 1.0,
        "daily_loss_cap": 2.0,
        "stop_loss": 1.0,
        "take_profit": 2.0,
        "max_drawdown_limit": 0.10,
        "effective_leverage": 0.5,
        "max_effective_leverage": 2.0,
        "requested_units": 1,
        "max_live_micro_units": 1000,
    }
    payload["kill_switch_proof"] = {"status": "PASS"}
    payload["one_shot_controls"] = {
        "one_order_only": True,
        "micro_size_only": True,
        "retry_allowed": False,
        "autonomous_reentry_allowed": False,
        "scheduler_enabled": False,
        "daemon_enabled": False,
        "webhook_enabled": False,
        "background_execution": False,
    }
    payload["broker_gate"] = {
        "broker_sandbox_or_demo_proof": True,
        "broker_mutation": False,
        "credentials_persisted": False,
        "account_id_persisted": False,
    }
    payload["account_permission_gate"] = {
        "broker_name": "OANDA_SANITIZED_DEMO",
        "broker_environment": "demo",
        "asset_class": "forex",
        "account_type": "practice_margin",
        "account_currency": "USD",
        "margin_available_confirmed": True,
        "effective_leverage_limit": 2.0,
        "long_permission": True,
        "short_permission": False,
        "fifo_required": True,
        "hedging_available": False,
        "instrument_tradable": True,
        "max_units": 1000,
        "stop_loss_supported": True,
        "take_profit_supported": True,
        "order_type_supported": ["market"],
        "one_order_only_supported": True,
        "demo_sandbox_order_preview_supported": True,
        "broker_house_restrictions": [],
        "proof_timestamp": datetime.now(timezone.utc).isoformat(),
        "proof_source": "sanitized_contract_fixture_no_broker_io",
        "sanitized_evidence_only": True,
        "activation_side": "long",
    }
    payload["live_exception_contracts"] = _live_exception_contracts()
    return payload


def test_empty_evidence_blocked():
    payload = run_consolidated_readiness_blocker_closure_v1(evidence_payload={}, write_reports=False)
    assert payload["status"] == "BLOCKED"
    assert payload["decision"] == "blocked"
    assert payload["blockers"]


def test_walk_forward_failed_blocker():
    payload = _base_payload()
    payload["walk_forward_status"] = "failed"
    payload["candidate"]["walk_forward_status"] = "failed"
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "walk_forward_failed" in result["unresolved_blockers"]


def test_missing_paper_metrics_blocker():
    payload = _base_payload()
    payload["paper_metrics"] = {"sample_size": 12}
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "paper_evidence_not_ready" in result["unresolved_blockers"]


def test_negative_expectancy_blocker():
    payload = _base_payload()
    payload["paper_metrics"]["expectancy"] = -0.01
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "paper_evidence_not_ready" in result["unresolved_blockers"]


def test_low_profit_factor_blocker():
    payload = _base_payload()
    payload["paper_metrics"]["profit_factor"] = 1.0
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "paper_evidence_not_ready" in result["unresolved_blockers"]


def test_missing_validation_results_blocker():
    payload = _base_payload()
    payload["validation_results"] = []
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_validation_results" in result["unresolved_blockers"]


def test_candidate_not_approved_blocker():
    payload = _base_payload()
    payload["candidate_approved_for_demo_validation"] = False
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "candidate_not_approved_for_demo_validation" in result["unresolved_blockers"]


def test_demo_contract_not_complete_blocker():
    payload = _base_payload()
    payload["demo_validation_contract"] = {"status": "PENDING"}
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "demo_contract_not_complete" in result["unresolved_blockers"]
    assert "demo_validation_contract_not_complete" in result["unresolved_blockers"]


def test_missing_live_readiness_candidate_blocker():
    payload = _base_payload()
    payload["live_readiness_candidate"] = {}
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_live_readiness_candidate" in result["unresolved_blockers"]


def test_missing_approval_trace_blocker():
    payload = _base_payload()
    payload.pop("approval_trace")
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_approval_trace" in result["unresolved_blockers"]


def test_missing_risk_limits_blocker():
    payload = _base_payload()
    payload["risk_limits"] = {}
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_risk_limits" in result["unresolved_blockers"]


def test_missing_kill_switch_proof_blocker():
    payload = _base_payload()
    payload["kill_switch_proof"] = None
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_kill_switch_proof" in result["unresolved_blockers"]


def test_missing_rollback_proof_blocker():
    payload = _base_payload()
    payload["rollback_proof"] = None
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_rollback_proof" in result["unresolved_blockers"]


def test_missing_reconciliation_proof_blocker():
    payload = _base_payload()
    payload["reconciliation_proof"] = None
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_reconciliation_proof" in result["unresolved_blockers"]


def test_missing_freshness_blocker():
    payload = _base_payload()
    payload["evidence_timestamp"] = "2025-01-01T00:00:00+00:00"
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_evidence_freshness" in result["unresolved_blockers"]


def test_missing_replayability_blocker():
    payload = _base_payload()
    payload["replayability_proof"] = None
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_replayability_proof" in result["unresolved_blockers"]


def test_missing_final_disarm_proof_blocker():
    payload = _base_payload()
    payload["final_disarm_proof"] = None
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_final_disarm_proof" in result["unresolved_blockers"]


def test_missing_post_trade_journal_path_blocker():
    payload = _base_payload()
    payload["post_trade_journal_path"] = ""
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_post_trade_journal_path" in result["unresolved_blockers"]


def test_missing_one_shot_package_blocker():
    payload = _base_payload()
    payload["one_shot_exception_package"] = {"exception_package_completed": False}
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "one_shot_exception_package_not_review_ready" in result["unresolved_blockers"]


def test_missing_live_review_certificate_blocker():
    payload = _base_payload()
    payload["live_review_certificate"] = {"certificate_completed": False}
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "live_review_certificate_not_review_ready" in result["unresolved_blockers"]


def test_missing_human_review_ready_blocker():
    payload = _base_payload()
    payload["human_review_ready"] = False
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "missing_human_review_ready" in result["unresolved_blockers"]


def test_mitigation_worsened_blocker():
    payload = _base_payload()
    payload["candidate"]["mitigation_status"] = "worsened"
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert "mitigation_worsened" in result["unresolved_blockers"]


def test_demo_evidence_clears_demo_only():
    payload = _full_demo_ready_payload()
    payload["live_readiness_candidate"] = {}
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert result["ready_for_demo_validation"] is True
    assert result["ready_for_live_review"] is False


def test_full_live_readiness_evidence_clears_live_blockers():
    payload = _full_live_ready_payload()
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy", evidence_payload=payload, write_reports=False
    )
    assert result["ready_for_demo_validation"] is True
    assert result["ready_for_live_review"] is True
    assert result["status"] == "READY"
    assert result["unresolved_blockers"] == []


def test_blocker_constants_are_stable():
    required = {
        "walk_forward_failed",
        "paper_evidence_not_ready",
        "mitigation_worsened",
        "missing_validation_results",
        "candidate_not_approved_for_demo_validation",
        "demo_contract_not_complete",
        "missing_live_readiness_candidate",
        "missing_approval_trace",
        "missing_risk_limits",
        "missing_kill_switch_proof",
        "missing_rollback_proof",
        "missing_reconciliation_proof",
        "missing_evidence_freshness",
        "missing_replayability_proof",
        "missing_final_disarm_proof",
        "missing_post_trade_journal_path",
        "demo_validation_contract_not_complete",
        "one_shot_exception_package_not_review_ready",
        "live_review_certificate_not_review_ready",
        "missing_human_review_ready",
    }
    assert set(CANONICAL_BLOCKERS) >= required


def test_payload_stable_blocker_keys_and_ready_live_auth_false():
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy",
        evidence_payload=_full_live_ready_payload(),
        write_reports=False,
    )
    assert result["safety"]["paper_only"] is True
    assert result["safety"]["live_trading_authorized"] is False
    assert "unresolved_blockers" in result
    assert "resolved_blockers" in result
    assert "blocker_details" in result


def test_report_path_under_reports():
    payload = _base_payload()
    result = run_consolidated_readiness_blocker_closure_v1(
        candidate_id="c1-eur-buy",
        evidence_payload=payload,
        write_reports=True,
    )
    report_path = Path(result["report_path"])
    assert "Reports/forex_delivery" in report_path.as_posix()
    assert report_path.name.endswith(".md") or report_path.name.endswith(".json")


def test_current_evidence_remains_blocked_for_incomplete_evidence():
    result = run_candidate_intake_demo_review_bridge(write_reports=False)
    assert result["verdict"] == "BLOCKED_INCOMPLETE_EVIDENCE"
    assert result["normalized_candidate"]["sample_size"] < 30
    assert "insufficient_sample" in result["blockers"]


def test_current_final_status_remains_blocked_by_evidence_gate_without_broker_proof():
    result = build_profitable_live_bot_final_status()
    assert result["status"] == REQUIRE_MORE_EVIDENCE
    assert result["evidence_gate_cleared"] is False
    assert result["risk_gate_cleared"] is False
    assert "insufficient_sample" in result["blockers"]["evidence"]


def test_final_status_blocks_insufficient_sample_until_depth_exists():
    payload = _final_status_payload()
    payload["paper_metrics"]["sample_size"] = 29
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == REQUIRE_MORE_EVIDENCE
    assert "insufficient_sample" in result["blockers"]["evidence"]


def test_final_status_sufficient_sample_moves_to_broker_gate():
    payload = _final_status_payload()
    payload["broker_gate"] = {}
    payload["live_exception_contracts"] = {}
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["evidence_gate_cleared"] is True
    assert result["risk_gate_cleared"] is True
    assert result["status"] == BLOCKED_BY_BROKER_GATE


def test_final_status_walk_forward_failure_blocks_readiness():
    payload = _final_status_payload()
    payload["candidate"]["walk_forward_status"] = "failed"
    payload["walk_forward_result"]["walk_forward_gate_cleared"] = False
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == REQUIRE_MORE_EVIDENCE
    assert "walk_forward_not_cleared" in result["blockers"]["evidence"]


def test_final_status_profitable_evidence_and_live_controls_can_clear():
    result = build_profitable_live_bot_final_status(evidence_payload=_final_status_payload())
    assert result["status"] == PROFITABLE_LIVE_BOT_READY
    assert result["live_for_keeps_ready"] is True
    assert result["evidence_gate_cleared"] is True
    assert result["risk_gate_cleared"] is True
    assert result["broker_gate_cleared"] is True
    assert result["policy_gate_cleared"] is True


def test_final_status_requires_kill_switch():
    payload = _final_status_payload()
    payload["kill_switch_proof"] = None
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == BLOCKED_BY_RISK
    assert "missing_kill_switch" in result["blockers"]["risk"]


def test_final_status_requires_max_loss_cap():
    payload = _final_status_payload()
    payload["risk_limits"].pop("maximum_loss")
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == BLOCKED_BY_RISK
    assert "missing_max_loss_cap" in result["blockers"]["risk"]


def test_final_status_requires_daily_stop_cap():
    payload = _final_status_payload()
    payload["risk_limits"].pop("daily_loss_cap")
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == BLOCKED_BY_RISK
    assert "missing_daily_stop_cap" in result["blockers"]["risk"]


def test_final_status_requires_stop_loss():
    payload = _final_status_payload()
    payload["risk_limits"].pop("stop_loss")
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == BLOCKED_BY_RISK
    assert "missing_stop_loss" in result["blockers"]["risk"]


def test_final_status_requires_take_profit():
    payload = _final_status_payload()
    payload["risk_limits"].pop("take_profit")
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == BLOCKED_BY_RISK
    assert "missing_take_profit" in result["blockers"]["risk"]


def test_final_status_requires_one_order_only_constraints():
    payload = _final_status_payload()
    payload["one_shot_controls"]["one_order_only"] = False
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == BLOCKED_BY_RISK
    assert "missing_one_order_only_constraint" in result["blockers"]["risk"]


def test_final_status_missing_broker_proof_blocks():
    payload = _final_status_payload()
    payload["broker_gate"]["broker_sandbox_or_demo_proof"] = False
    payload["account_permission_gate"]["demo_sandbox_order_preview_supported"] = False
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == BLOCKED_BY_BROKER_GATE
    assert "missing_broker_demo_or_sandbox_proof" in result["blockers"]["broker"]


def test_final_status_unknown_account_permission_blocks():
    payload = _final_status_payload()
    payload["account_permission_gate"].pop("margin_available_confirmed")
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == BLOCKED_BY_BROKER_GATE
    assert "unknown_account_permission:margin_available_confirmed" in result["blockers"]["broker"]


def test_final_status_shorting_permission_unknown_blocks_short_side_activation():
    payload = _final_status_payload()
    payload["account_permission_gate"]["activation_side"] = "short"
    payload["account_permission_gate"].pop("short_permission")
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["status"] == BLOCKED_BY_BROKER_GATE
    assert result["short_side_status"] == BLOCKED_BY_BROKER_GATE
    assert "unknown_account_permission:short_permission" in result["blockers"]["broker"]


def test_final_status_full_sanitized_permission_bundle_clears_broker_gate():
    result = build_profitable_live_bot_final_status(evidence_payload=_final_status_payload())
    assert result["broker_gate_cleared"] is True
    assert result["account_permission_gate"]["status"] == "ACCOUNT_PERMISSION_GATE_CLEARED"
    assert result["broker_gate_summary"]["broker_environment"] == "demo"
    assert result["broker_gate_summary"]["margin_available_confirmed"] is True


def test_final_status_missing_owner_approval_blocks_policy_gate():
    payload = _final_status_payload()
    payload["live_exception_contracts"].pop("approval")
    payload["live_exception_contracts"]["evidence_bundle"]["owner_approval_present"] = False
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["broker_gate_cleared"] is True
    assert result["status"] == BLOCKED_BY_POLICY
    assert "missing_owner_approval" in result["blockers"]["policy"]


def test_final_status_missing_arming_blocks_policy_gate():
    payload = _final_status_payload()
    payload["live_exception_contracts"].pop("arming_state")
    payload["live_exception_contracts"]["evidence_bundle"].pop("arming_timestamp")
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["broker_gate_cleared"] is True
    assert result["status"] == BLOCKED_BY_POLICY
    assert "missing_arming_timestamp" in result["blockers"]["policy"]


def test_final_status_full_sanitized_live_exception_bundle_clears_policy_gate():
    result = build_profitable_live_bot_final_status(evidence_payload=_final_status_payload())
    assert result["policy_gate_cleared"] is True
    assert result["live_exception_status"]["evidence_bundle_cleared"] is True
    assert result["live_exception_status"]["evidence_bundle_summary"]["owner_approval_present"] is True


def test_final_status_low_effective_leverage_guard_exists_and_blocks_excess():
    payload = _final_status_payload()
    result = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert result["risk_contract_summary"]["low_effective_leverage_guard"] is True

    payload["risk_limits"]["effective_leverage"] = 3.0
    blocked = build_profitable_live_bot_final_status(evidence_payload=payload)
    assert blocked["status"] == BLOCKED_BY_RISK
    assert "effective_leverage_above_low_guard" in blocked["blockers"]["risk"]


def test_final_status_blocks_scheduler_daemon_webhook_background_execution():
    fields = ("scheduler_enabled", "daemon_enabled", "webhook_enabled", "background_execution")
    for field in fields:
        payload = _final_status_payload()
        payload["one_shot_controls"][field] = True
        result = build_profitable_live_bot_final_status(evidence_payload=payload)
        assert result["status"] == BLOCKED_BY_POLICY
        assert f"{field}_not_allowed" in result["blockers"]["policy"]


def test_final_status_never_executes_or_authorizes_live_order():
    result = build_profitable_live_bot_final_status(evidence_payload=_final_status_payload())
    safety = result["safety"]
    assert safety["order_execution"] is False
    assert safety["live_trading"] is False
    assert safety["live_trading_authorized"] is False
    assert safety["broker_connected"] is False
    assert safety["credentials_used"] is False
    assert safety["network_used"] is False
    assert safety["credential_read"] is False
    assert safety["credential_write"] is False
    assert safety["env_read"] is False
    assert safety["account_id_read"] is False
    assert safety["account_id_write"] is False
    assert safety["broker_mutation"] is False
    assert safety["scheduler"] is False
    assert safety["daemon"] is False
    assert safety["webhook"] is False
    assert safety["background_execution"] is False
    assert result["long_only_status"] == "LONG_ONLY_ALLOWED"
    assert result["short_side_status"] == BLOCKED_BY_BROKER_GATE
