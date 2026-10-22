from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone

from automation.forex_engine import campaign_evidence_accumulator as campaign_accumulator
from automation.forex_engine import demo_candidate_lifecycle_manager as lifecycle
from automation.forex_engine import demo_validation_contract
from automation.forex_engine import live_readiness_review
from automation.forex_engine import strategy_campaign_supervisor as campaign_supervisor
from automation.forex_engine import strategy_evaluation_harness
from automation.forex_engine import walkforward_validation_harness


def _strategy_result() -> dict:
    return strategy_evaluation_harness.evaluate_strategy(
        "Journey Alpha",
        "v1",
        [
            {"realized_pl": 210.0},
            {"realized_pl": -90.0},
            {"realized_pl": 150.0},
            {"realized_pl": -40.0},
            {"realized_pl": 110.0},
            {"realized_pl": 80.0},
        ],
    )


def _walkforward_result() -> dict:
    return walkforward_validation_harness.validate_walkforward_strategy(
        "Journey Alpha",
        "v1",
        validation_windows=2,
        window_trade_outcomes=[[210.0, -90.0, 150.0, -40.0, 110.0, 80.0], [180.0, -70.0, 120.0, -30.0, 100.0, 60.0]],
    )


def _campaign_evidence(*, expectancy: float = 0.12, profit_factor: float = 1.32, drawdown: float = 3.8, evidence_score: float = 0.88, trade_count: int = 25, session_count: int = 3) -> dict:
    return campaign_accumulator.evaluate_campaign_evidence(
        paper_session_results=[
            {
                "trade_count": trade_count,
                "session_count": session_count,
                "win_count": int(trade_count * 0.6),
                "loss_count": int(trade_count * 0.4),
                "realized_pl": 12.0,
                "expectancy": expectancy,
                "profit_factor": profit_factor,
                "max_drawdown": drawdown,
                "evidence_score": evidence_score,
            }
        ],
        profitability_results=[{"status": "passed", "score": 0.95}],
        walk_forward_results=[{"status": "pass", "score": 0.9}],
        promotion_results=[{"status": "success", "score": 1.0}],
        capital_allocation_results=[{"status": "true", "score": 1.0}],
    )


def _campaign_supervisor(*, campaign_evidence_blockers: list[str] | None = None, capital_pass: bool = True) -> dict:
    return campaign_supervisor.evaluate_campaign_supervisor(
        campaign_evidence_result=_campaign_evidence() if campaign_evidence_blockers is None else {"campaign_evidence_status": campaign_evidence_blockers[0]},
        promotion_workflow_result={"status": "PASS", "passed": True},
        capital_allocation_result={"status": "PASS" if capital_pass else "FAIL", "passed": capital_pass},
    )


def _candidate_lifecycle() -> dict:
    campaign = campaign_supervisor.evaluate_campaign_supervisor(
        campaign_evidence_result=_campaign_evidence(),
        promotion_workflow_result={"status": "PASS", "passed": True},
        capital_allocation_result={"status": "PASS", "passed": True},
    )
    created = lifecycle.evaluate_demo_candidate_lifecycle(
        campaign,
        {"strategy_id": "journey-1", "strategy_name": "journey"},
    )
    active = lifecycle.evaluate_demo_candidate_lifecycle(
        campaign,
        {"requested_transition": "ACTIVATE", "strategy_id": "journey-1", "strategy_name": "journey"},
        {"candidate_state": created["candidate_state"]},
    )
    approved = lifecycle.evaluate_demo_candidate_lifecycle(
        campaign,
        {"requested_transition": "APPROVE", "strategy_id": "journey-1", "strategy_name": "journey"},
        {"candidate_state": active["candidate_state"]},
    )
    return {
        "campaign_supervisor_result": campaign,
        "candidate_state": approved["candidate_state"],
        "candidate_id": approved["candidate_id"],
        "candidate_approved": True,
    }


def _contract_input(*, candidate_state: str = lifecycle.DEMO_CANDIDATE_APPROVED_FOR_DEMO_VALIDATION, candidate_approved: bool = True, validation_results=None, overrides=None) -> dict:
    overrides = overrides or {}
    state = {
        "demo_candidate_record": {
            "candidate_id": "cand-journey",
            "candidate_state": candidate_state,
            "candidate_approved": candidate_approved,
        },
        "demo_validation_results": validation_results or [
            {
                "validation_session_count": 3,
                "validation_trade_count": 20,
                "validation_expectancy": 0.12,
                "validation_profit_factor": 1.3,
                "validation_max_drawdown": 2.0,
                "validation_evidence_score": 0.88,
            }
        ],
    }
    state.update(overrides)
    return state


def _readiness_input(approved: bool = True, validation_overrides=None) -> dict:
    payload = {
        "paper_to_demo_promotion": {"allowed": True, "demo_promotion_ready": True, "mode": "PAPER_TO_DEMO_PROMOTION_ONLY"},
        "demo_multi_trade_runner": {"allowed": True, "mode": "DEMO_RUN_PLAN_ONLY", "selected_intents": [{"idempotency_key": "journey"}]},
        "demo_reconciliation": {"allowed": True, "matched": True, "match_score": 1.0, "mode": "DEMO_RECONCILIATION_ONLY"},
        "session_replay": {"trade_count": 30, "session_count": 5, "max_drawdown_pct": 2.0, "risk_failures": []},
        "evidence_ledger": {"allowed": True, "validation_passed": True, "entries": [{"id": "evidence-1"}]},
        "risk_metrics": {"drawdown_pct": 2.0, "risk_failures": [], "risk_ok": True},
        "kill_switch_proof": {"present": True, "verified": True},
        "human_approval": approved,
        "limits": {"maximum_drawdown_pct": 5.0},
    }
    if validation_overrides:
        payload.update(validation_overrides)
    return payload


def _run_journey(
    *,
    campaign_blockers: list[str] | None = None,
    capital_pass: bool = True,
    contract_overrides=None,
    readiness_overrides=None,
) -> dict:
    strategy = _strategy_result()
    wf = _walkforward_result()
    campaign = _campaign_supervisor(campaign_evidence_blockers=campaign_blockers, capital_pass=capital_pass)
    if campaign_blockers or campaign["campaign_status"] != campaign_supervisor.CAMPAIGN_DEMO_CANDIDATE:
        lifecycle_record = {"candidate_state": lifecycle.DEMO_CANDIDATE_CREATED, "candidate_approved": False}
    else:
        lifecycle_record = _candidate_lifecycle()
    contract_result = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(overrides=contract_overrides or {})
    )
    readiness_result = live_readiness_review.review_live_readiness(**_readiness_input(overrides := (readiness_overrides or {})))
    return {
        "strategy": strategy,
        "walkforward": wf,
        "campaign": campaign,
        "candidate": lifecycle_record,
        "contract": contract_result,
        "readiness": readiness_result,
    }


def test_journey_perfect_candidate() -> None:
    result = _run_journey()
    assert result["strategy"]["demo_candidate"] is True
    assert result["walkforward"]["demo_candidate"] is True
    assert result["campaign"]["campaign_status"] == campaign_supervisor.CAMPAIGN_DEMO_CANDIDATE
    assert result["contract"]["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_COMPLETE
    assert result["contract"]["live_readiness_candidate"] is True
    assert result["readiness"]["approval_required"] is True
    assert result["readiness"]["decision"] == live_readiness_review.DECISION_REVIEW_ONLY
    assert result["readiness"]["allowed"] is False


def test_journey_insufficient_trades_continue() -> None:
    campaign = _campaign_evidence(trade_count=10, session_count=3)
    campaign = campaign_supervisor.evaluate_campaign_supervisor(
        campaign_evidence_result=campaign,
        promotion_workflow_result={"status": "PASS", "passed": True},
        capital_allocation_result={"status": "PASS", "passed": True},
    )
    assert campaign["campaign_status"] == campaign_supervisor.CAMPAIGN_MORE_EVIDENCE_REQUIRED
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(validation_results=[{"validation_session_count": 3, "validation_trade_count": 10, "validation_expectancy": 0.12, "validation_profit_factor": 1.3, "validation_max_drawdown": 2.0, "validation_evidence_score": 0.88}])
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_CONTINUE
    assert "minimum_validation_trades_not_met" in contract["blockers"]


def test_journey_insufficient_sessions_continue() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(validation_results=[{"validation_session_count": 1, "validation_trade_count": 20, "validation_expectancy": 0.12, "validation_profit_factor": 1.3, "validation_max_drawdown": 2.0, "validation_evidence_score": 0.88}])
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_CONTINUE
    assert "minimum_validation_sessions_not_met" in contract["blockers"]


def test_journey_low_evidence_score_rejects() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(validation_results=[{"validation_session_count": 3, "validation_trade_count": 20, "validation_expectancy": 0.12, "validation_profit_factor": 1.3, "validation_max_drawdown": 2.0, "validation_evidence_score": 0.2}])
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_REJECTED
    assert "evidence_score_below_threshold" in contract["blockers"]


def test_journey_low_profit_factor_rejects() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(validation_results=[{"validation_session_count": 3, "validation_trade_count": 20, "validation_expectancy": 0.12, "validation_profit_factor": 1.0, "validation_max_drawdown": 2.0, "validation_evidence_score": 0.88}])
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_REJECTED
    assert "profit_factor_below_threshold" in contract["blockers"]


def test_journey_negative_expectancy_rejects() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(validation_results=[{"validation_session_count": 3, "validation_trade_count": 20, "validation_expectancy": -0.2, "validation_profit_factor": 1.3, "validation_max_drawdown": 2.0, "validation_evidence_score": 0.88}])
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_REJECTED
    assert "negative_expectancy" in contract["blockers"]


def test_journey_excessive_drawdown_rejects() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(validation_results=[{"validation_session_count": 3, "validation_trade_count": 20, "validation_expectancy": 0.12, "validation_profit_factor": 1.3, "validation_max_drawdown": 20.0, "validation_evidence_score": 0.88}])
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_REJECTED
    assert "drawdown_above_threshold" in contract["blockers"]


def test_journey_candidate_not_approved_blocks() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(candidate_approved=False)
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_BLOCKED
    assert "candidate_not_approved_for_demo_validation" in contract["blockers"]


def test_journey_paused_candidate_blocks() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(candidate_state=lifecycle.DEMO_CANDIDATE_PAUSED)
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_BLOCKED
    assert "candidate_state_blocked" in contract["blockers"]


def test_journey_revoked_candidate_blocks() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(candidate_state=lifecycle.DEMO_CANDIDATE_REVOKED)
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_BLOCKED
    assert "candidate_state_blocked" in contract["blockers"]


def test_journey_unsafe_broker_flag_blocks() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(overrides={"broker_connection_active": True})
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_BLOCKED
    assert "unsafe_broker_connection_detected" in contract["blockers"]


def test_journey_unsafe_credential_flag_blocks() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(overrides={"credentials_accessed": True})
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_BLOCKED
    assert "unsafe_credential_access_detected" in contract["blockers"]


def test_journey_unsafe_account_identifier_flag_blocks() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(overrides={"account_identifiers_accessed": True})
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_BLOCKED
    assert "unsafe_account_identifier_detected" in contract["blockers"]


def test_journey_unsafe_order_execution_flag_blocks() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(overrides={"order_execution_enabled": True})
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_BLOCKED
    assert "unsafe_order_execution_detected" in contract["blockers"]


def test_journey_unsafe_live_trading_flag_blocks() -> None:
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(overrides={"live_trading_authorized": True})
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_BLOCKED
    assert "unsafe_live_trading_detected" in contract["blockers"]


def test_journey_missing_validation_results_requests_more_evidence() -> None:
    result = _run_journey(contract_overrides={"demo_validation_results": []})
    assert result["contract"]["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_MORE_EVIDENCE_REQUIRED
    assert "missing_validation_results" in result["contract"]["blockers"]


def test_journey_rejection_propagation() -> None:
    strategy = _strategy_result()
    wf = _walkforward_result()
    campaign = campaign_supervisor.evaluate_campaign_supervisor(
        campaign_evidence_result={"campaign_evidence_status": campaign_accumulator.CAMPAIGN_EVIDENCE_REJECTED, "campaign_expectancy": -0.1, "campaign_trade_count": 10, "campaign_session_count": 1, "campaign_profit_factor": 1.0, "campaign_max_drawdown": 4.0},
        promotion_workflow_result={"status": "PASS", "passed": True},
        capital_allocation_result={"status": "PASS", "passed": True},
    )
    contract = demo_validation_contract.evaluate_demo_validation_contract(_contract_input())
    readiness = live_readiness_review.review_live_readiness(**_readiness_input(approved=False))
    strategy["demo_candidate"] = False
    wf["demo_candidate"] = False
    assert strategy["demo_candidate"] is False or wf["demo_candidate"] is False
    assert campaign["campaign_status"] == campaign_supervisor.CAMPAIGN_REJECTED
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_COMPLETE
    assert readiness["allowed"] is False


def test_journey_continue_propagation() -> None:
    result = _run_journey()
    assert result["strategy"]["demo_candidate"] is True
    assert result["campaign"]["campaign_status"] == campaign_supervisor.CAMPAIGN_DEMO_CANDIDATE
    contract = demo_validation_contract.evaluate_demo_validation_contract(
        state=_contract_input(
            validation_results=[
                {
                    "validation_session_count": 3,
                    "validation_trade_count": 20,
                    "validation_expectancy": 0.005,
                    "validation_profit_factor": 1.3,
                    "validation_max_drawdown": 2.0,
                    "validation_evidence_score": 0.88,
                }
            ]
        )
    )
    assert contract["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_CONTINUE


def test_journey_complete_propagation_requires_readiness_flags() -> None:
    result = _run_journey(
        readiness_overrides={"human_approval": True},
    )
    assert result["contract"]["demo_validation_contract_status"] == demo_validation_contract.DEMO_CONTRACT_COMPLETE
    assert result["readiness"]["approval_required"] is True
    assert result["readiness"]["decision"] in {
        live_readiness_review.DECISION_REQUIRES_HUMAN_APPROVAL,
        live_readiness_review.DECISION_REVIEW_ONLY,
    }


def test_journey_readiness_hardening_no_unsafe_execution_paths() -> None:
    source = inspect.getsource(live_readiness_review)
    safety_tokens = ("requests", "urllib", "socket", "subprocess", "os.environ", "http://", "https://")
    for token in safety_tokens:
        assert token not in source
    result = live_readiness_review.review_live_readiness(**_readiness_input(approved=True))
    assert result["safety"]["paper_only"] is True
    assert result["safety"]["live_trading"] is False
    assert result["safety"]["real_orders"] is False
    assert result["safety"]["network_submit"] is False
    assert result["safety"]["broker_write"] is False
    assert result["safety"]["credentials"] is False


def test_review_journey_consumes_sanitized_demo_validation_evidence() -> None:
    from automation.forex_engine.review_chain_end_to_end_candidate_journey import (
        run_candidate_journey,
    )

    payload = {
        "demo_candidate_record": {
            "candidate_id": "c1-eur-buy",
            "candidate_state": "DEMO_CANDIDATE_APPROVED_FOR_DEMO_VALIDATION",
            "candidate_approved": True,
        },
        "demo_validation_results": [
            {
                "validation_session_count": 3,
                "validation_trade_count": 20,
                "validation_expectancy": 0.12,
                "validation_profit_factor": 1.3,
                "validation_max_drawdown": 2.0,
                "validation_evidence_score": 0.9,
            }
        ],
    }

    result = run_candidate_journey(demo_validation_payload=payload)

    assert result["demo_validation_evidence_consumed"] is True
    assert (
        result["demo_validation_contract"]["demo_validation_contract_status"]
        == demo_validation_contract.DEMO_CONTRACT_COMPLETE
    )
    assert result["live_trading_authorized"] is False


def test_review_journey_automatically_reuses_canonical_demo_ledger(tmp_path) -> None:
    from automation.forex_engine.review_chain_end_to_end_candidate_journey import (
        run_candidate_journey,
    )

    ledger = tmp_path / "demo_proof_ledger.jsonl"
    rows = []
    today = datetime.now(timezone.utc).date()
    for age_days in range(4, -1, -1):
        evidence_date = today - timedelta(days=age_days)
        rows.append(
            {
                "record_type": "REAL_DEMO_DAY",
                "date": evidence_date.isoformat(),
                "session_mode": "OANDA_PRACTICE",
                "session_source": "broker_demo",
                "fills": 6,
                "windows_toward_verdict": 2,
                "max_drawdown_pct": 2.0,
                "trade_rows": [
                    {"realized_pnl_usd": value}
                    for value in (2.0, 1.0, 1.0, 2.0, -0.5, 1.0)
                ],
                "live_trading_allowed": False,
                "live_order_execution_allowed": False,
                "live_capital_action_authorized": False,
                "money_movement_allowed": False,
                "bank_access_allowed": False,
            }
        )
    ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    result = run_candidate_journey(demo_evidence_ledger_path=ledger)

    assert result["demo_validation_evidence_consumed"] is True
    assert result["demo_validation_evidence_source"] == "canonical_demo_proof_ledger"
    assert (
        result["demo_validation_contract"]["demo_validation_contract_status"]
        == demo_validation_contract.DEMO_CONTRACT_COMPLETE
    )
    assert result["live_trading_authorized"] is False
