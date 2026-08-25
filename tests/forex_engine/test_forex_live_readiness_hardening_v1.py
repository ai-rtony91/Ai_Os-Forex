from __future__ import annotations

import hashlib
import json

import pytest

from automation.forex_engine import forex_live_readiness_hardening_v1 as hardening
from automation.forex_engine.live_readiness_review import review_live_readiness


def _hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_kill_switch_blocks_entry_without_closing_active_paper_position() -> None:
    result = hardening.kill_switch_synthetic_proof()
    assert result["proof_pass"] is True
    assert result["kill_switch_blocks_new_entries"] is True
    assert result["active_paper_positions_preserved"] is True
    assert result["kill_switch_executed_live"] is False


def test_daily_loss_brake_blocks_entry_at_supplied_authoritative_threshold() -> None:
    result = hardening.brake_evaluation(
        daily_loss=250.0,
        daily_loss_threshold=250.0,
        drawdown_pct=0.0,
        max_drawdown_pct=5.0,
        loss_streak=0,
        loss_streak_threshold=3,
    )
    assert result["daily_loss"] == {
        "status": "PASS",
        "new_entries_blocked": True,
        "threshold": 250.0,
    }


def test_unconfigured_daily_loss_threshold_fails_closed_pending_configuration() -> None:
    result = hardening.brake_evaluation(
        daily_loss=0.0,
        daily_loss_threshold=None,
        drawdown_pct=0.0,
        max_drawdown_pct=5.0,
        loss_streak=0,
        loss_streak_threshold=None,
    )
    assert result["daily_loss"]["status"] == "PENDING_CONFIGURATION"
    assert result["daily_loss"]["new_entries_blocked"] is True


def test_drawdown_brake_blocks_entry() -> None:
    result = hardening.brake_evaluation(
        daily_loss=0.0,
        daily_loss_threshold=250.0,
        drawdown_pct=5.0,
        max_drawdown_pct=5.0,
        loss_streak=0,
        loss_streak_threshold=3,
    )
    assert result["max_drawdown"]["new_entries_blocked"] is True


def test_duplicate_signal_does_not_duplicate_intent() -> None:
    result = hardening.duplicate_intent_proof()
    assert result["proof_pass"] is True
    assert result["unique_execution_intent_count"] == 1
    assert result["duplicate_intent_created_count"] == 0


def test_restart_does_not_duplicate_fill() -> None:
    snapshot = {"pending": {}, "active": {}, "ledger": [], "applied_event_ids": []}
    journal = [
        {"event_id": "E1", "type": "SIGNAL", "trade_id": "T1"},
        {"event_id": "E2", "type": "FILL", "trade_id": "T1"},
    ]
    first = hardening.recover_from_journal(snapshot, journal)
    second = hardening.recover_from_journal(first, journal)
    assert len(second["active"]) == 1


def test_restart_does_not_duplicate_exit() -> None:
    snapshot = {
        "pending": {},
        "active": {"T1": {"trade_id": "T1", "status": "OPEN"}},
        "ledger": [],
        "applied_event_ids": [],
    }
    journal = [{"event_id": "E3", "type": "EXIT", "trade_id": "T1"}]
    first = hardening.recover_from_journal(snapshot, journal)
    second = hardening.recover_from_journal(first, journal)
    assert len(second["ledger"]) == 1
    assert second["active"] == {}


def test_stale_market_and_missing_quote_fail_closed() -> None:
    result = hardening.market_data_failure_proof()
    assert result["fail_closed_market_data"] is True
    assert result["scenarios"]["stale_m5"]["entry_or_fill_allowed"] is False
    assert result["scenarios"]["missing_quote"]["fabricated_trade_count"] == 0


def test_network_failure_preserves_state() -> None:
    result = hardening.market_data_failure_proof()
    assert result["network_failure_preserves_active_state"] is True
    assert result["interrupted_write_preserves_atomic_state"] is True


def test_atomic_checkpoint_keeps_committed_state_on_interrupt() -> None:
    committed = {"version": 1, "ledger": ["T1"]}
    candidate = {"version": 2, "ledger": []}
    assert hardening.atomic_checkpoint(
        committed, candidate, interrupt_before_replace=True
    ) == committed


def test_r_reconciliation_is_exact() -> None:
    trade = {
        "entry_price": 1.1000,
        "initial_stop": 1.0950,
        "exit_price": 1.1075,
        "direction": "BUY",
    }
    assert hardening.recompute_realized_r(trade) == pytest.approx(1.5)


def test_latency_stress_is_deterministic() -> None:
    first = hardening.latency_stress(hardening.SYNTHETIC_REALIZED_R)
    second = hardening.latency_stress(hardening.SYNTHETIC_REALIZED_R)
    assert first == second
    assert [item["delay_ms"] for item in first] == [0, 50, 100, 250, 500, 1000, 2000]
    assert next(item for item in first if item["delay_ms"] == 1000)["realized_r_delta"] == -0.1


def test_slippage_stress_is_deterministic_and_adverse_on_both_legs() -> None:
    first = hardening.slippage_stress(hardening.SYNTHETIC_REALIZED_R)
    second = hardening.slippage_stress(hardening.SYNTHETIC_REALIZED_R)
    assert first == second
    point = next(item for item in first if item["slippage_per_leg_r"] == 0.10)
    assert point["total_adverse_slippage_r"] == 0.20
    assert point["expectancy_delta_r"] == pytest.approx(-0.20)


def test_credential_exclusion_scans_values_without_opening_env(tmp_path) -> None:
    safe = tmp_path / "safe.json"
    safe.write_text(json.dumps({"credentials_persisted": False, "account_identifiers": False}), encoding="utf-8")
    result = hardening.credential_exclusion_scan([safe])
    assert result["credential_exclusion_pass"] is True
    assert result["suspected_credential_value_count"] == 0
    assert result["env_files_opened"] is False


def test_paper30_gate_pass_fixture() -> None:
    values = [1.0] * 20 + [-0.5] * 10
    ledger = hardening._synthetic_gate_ledger(values)
    result = hardening.evaluate_paper30_gate(
        ledger,
        applicable_risk_gates={"daily_loss": "PASS", "drawdown": "PASS", "kill": "PASS"},
    )
    assert result["paper30_gate_status"] == "PASS"
    assert result["closed"] == 30
    assert result["profit_factor"] == pytest.approx(4.0)


def test_paper30_gate_fail_fixture() -> None:
    ledger = hardening._synthetic_gate_ledger([1.0] * 29)
    result = hardening.evaluate_paper30_gate(
        ledger,
        applicable_risk_gates={"daily_loss": "PASS", "drawdown": "PASS", "kill": "PASS"},
    )
    assert result["paper30_gate_status"] == "FAIL"
    assert "closed_trades_below_30" in result["paper30_gate_blockers"]


def test_paper100_continuation_preserves_first_30() -> None:
    first = hardening._synthetic_gate_ledger([0.5] * 30)["trades"]
    continuation = hardening._synthetic_gate_ledger([0.25] * 70)["trades"]
    before = json.dumps(first, sort_keys=True)
    result = hardening.paper100_continuation(first, continuation)
    assert result["first_30_immutable"] is True
    assert result["aggregate_trade_count"] == 100
    assert json.dumps(first, sort_keys=True) == before
    assert result["automatic_promotion"] is False


def test_live_readiness_review_stays_review_only() -> None:
    result = review_live_readiness({}, {}, {}, {}, {}, {}, {}, human_approval=False)
    assert result["decision"] == "REVIEW_ONLY"
    assert result["allowed"] is False
    assert result["live_ready"] is False
    assert "paper_evidence_insufficient" in result["blocked_reasons"]


def test_audit_completeness_exposes_runtime_evidence_blockers() -> None:
    result = hardening.audit_completeness()
    assert result["audit_complete"] is False
    assert result["missing_mandatory_fields"] == [
        "market_data_freshness",
        "shadow_5r_outcomes",
    ]


def test_live_execution_and_broker_writes_are_structurally_false() -> None:
    proof = hardening.kill_switch_synthetic_proof()
    assert proof["kill_switch_executed_live"] is False
    source = hardening.Path(hardening.__file__).read_text(encoding="utf-8")
    assert "OandaReadOnlyClient" not in source
    assert "requests." not in source
    assert "urllib." not in source


def test_frozen_paper30_files_remain_untouched_by_pure_proofs() -> None:
    paths = (
        hardening.PAPER30_RUNTIME_PATH,
        hardening.PAPER30_LEDGER_PATH,
        hardening.PAPER30_STATE_PATH,
    )
    before = [_hash(path) for path in paths]
    hardening.kill_switch_synthetic_proof()
    hardening.duplicate_intent_proof()
    hardening.recovery_proof()
    after = [_hash(path) for path in paths]
    assert after == before
