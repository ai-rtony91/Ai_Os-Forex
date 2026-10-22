from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from automation.forex_engine.forex_p1_eurusd_market_history_signal_v1 import (
    FRESHNESS_SECONDS,
    HISTORY_SCHEMA,
    MINIMUM_REWARD_TO_RISK,
    build_signal_state,
    validate_market_history,
)
from automation.forex_engine.forex_p1_shadow_opportunity_audit_v1 import (
    analyze_cycle,
    build_audit_state,
    decision_lineage,
    merge_audit_states,
    portfolio_replay,
    production_decision_graph,
    resolve_counterfactual,
    shadow_audit_safety_state,
)
from automation.forex_engine.regime import (
    HIGH_VOLATILITY_RANGE_PCT,
    LOW_VOLATILITY_RANGE_PCT,
)
from scripts.forex_delivery.run_forex_p1_shadow_opportunity_audit_v1 import (
    parser,
    render_audit_report,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def history(closes=None, *, count=16, half_range=0.00015) -> dict:
    if closes is None:
        closes = [1.1000 + index * 0.00008 for index in range(count)]
    count = len(closes)
    candles = []
    for index, close in enumerate(closes):
        stamp = NOW - timedelta(minutes=5 * (count - 1 - index))
        candles.append({
            "observed_at_utc": stamp.isoformat().replace("+00:00", "Z"),
            "open": close,
            "high": close + half_range,
            "low": close - half_range,
            "close": close,
            "volume": 100 + index,
            "complete": True,
        })
    return {
        "schema": HISTORY_SCHEMA, "evidence_type": "SANITIZED_CANDLE_HISTORY",
        "provenance": "TEST_FIXTURE", "broker_label": "OANDA", "environment": "PRACTICE",
        "instrument": "EUR_USD", "granularity": "M5", "requested_count": count,
        "returned_count": count, "first_observed_at_utc": candles[0]["observed_at_utc"],
        "last_observed_at_utc": candles[-1]["observed_at_utc"], "candles": candles,
        "source_status": "VALID", "stale_status": "VALID", "read_only": True,
        "complete": True, "broker_write_performed": False, "credentials_persisted": False,
        "account_identifier_included": False, "raw_payload_included": False,
        "order_submission_allowed": False, "demo_execution_allowed": False,
        "live_execution_allowed": False, "money_movement_allowed": False,
    }


def validated(value: dict) -> dict:
    return validate_market_history(value, now=NOW + timedelta(minutes=5), allow_fixture=True)


def candidate(**overrides) -> dict:
    base = {
        "shadow_candidate_id": "candidate-1",
        "observed_utc": "2026-08-11T12:00:00Z",
        "hypothetical_entry": 1.1000,
        "hypothetical_stop": 1.0990,
        "hypothetical_target": 1.1020,
        "paper_units": 100,
        "source_group": "PRODUCTION_REJECTED_SHADOW",
    }
    return {**base, **overrides}


def candle(stamp: str, *, high: float, low: float, close: float = 1.1000) -> dict:
    return {"observed_at_utc": stamp, "open": close, "high": high, "low": low, "close": close, "complete": True}


def test_decision_lineage_explains_low_volatility_distance_without_threshold_change():
    value = validated(history([1.10000, 1.10005, 1.10010], half_range=0.00005))
    lineage = decision_lineage(value, cycle=3)
    assert lineage["production_signal"] == "RISK_REJECTED"
    assert lineage["first_failed_gate"] == "G03_MINIMUM_VOLATILITY"
    assert lineage["actual_value"] < lineage["required_value"] == LOW_VOLATILITY_RANGE_PCT
    assert lineage["distance_to_pass"] < 0


def test_production_decision_signal_and_thresholds_remain_unchanged():
    value = validated(history())
    original = copy.deepcopy(value)
    before = build_signal_state(value, generated_at_utc="2026-08-11T12:05:00Z")
    state = build_audit_state(value)
    after = build_signal_state(value, generated_at_utc="2026-08-11T12:05:00Z")
    assert before == after
    assert value == original
    assert state["production_decision_changed"] is False
    assert state["production_threshold_changed"] is False
    assert state["strategy_name"] == "supertrend_pullback_v1"
    assert state["configuration"]["supertrend_atr_length"] == 3
    assert state["configuration"]["supertrend_multiplier"] == 2.0
    assert FRESHNESS_SECONDS == 300
    assert MINIMUM_REWARD_TO_RISK == 2.0
    assert LOW_VOLATILITY_RANGE_PCT == 0.0003
    assert HIGH_VOLATILITY_RANGE_PCT == 0.0020


def test_shadow_cannot_open_position_increment_count_or_change_production_pnl():
    state = build_audit_state(validated(history()))
    assert state["position_open_allowed"] is False
    assert state["qualifying_trade_credit_allowed"] is False
    assert state["production_pnl_mutation_allowed"] is False
    assert state["production_actual_campaign_evidence"]["accepted_qualifying_trades"] == 0
    for cycle_state in state["cycle_records"]:
        if cycle_state["shadow_candidate"]:
            assert cycle_state["shadow_candidate"]["executed"] is False
            assert cycle_state["shadow_candidate"]["production_credit"] == 0
            assert cycle_state["shadow_candidate"]["production_pnl_effect"] == 0


def test_counterfactual_is_deterministic_and_target_before_stop_wins():
    future = [
        candle("2026-08-11T12:05:00Z", high=1.1010, low=1.0995, close=1.1008),
        candle("2026-08-11T12:10:00Z", high=1.1021, low=1.1004, close=1.1020),
    ]
    first = resolve_counterfactual(candidate(), future)
    second = resolve_counterfactual(candidate(), copy.deepcopy(future))
    assert first == second
    assert first["result"] == "WIN"
    assert first["target_before_stop"] is True
    assert first["hypothetical_r"] == 2.0


def test_same_candle_target_and_stop_is_ambiguous_not_profitable():
    result = resolve_counterfactual(
        candidate(), [candle("2026-08-11T12:05:00Z", high=1.1021, low=1.0989)]
    )
    assert result["result"] == "AMBIGUOUS"
    assert result["target_before_stop"] is False
    assert result["stop_before_target"] is False
    assert result["hypothetical_r"] is None
    assert result["hypothetical_pnl"] is None


def test_missing_rule_data_is_unresolved():
    result = resolve_counterfactual(candidate(hypothetical_stop=None), [])
    assert result["result"] == "UNRESOLVED"
    assert result["resolution_reason"] == "missing_canonical_rule_data"


def test_future_data_never_changes_current_production_lineage():
    value = validated(history([1.10000, 1.10005, 1.10010], half_range=0.00005))
    future_win = [candle("2026-08-11T12:05:00Z", high=1.1010, low=1.1000)]
    future_loss = [candle("2026-08-11T12:05:00Z", high=1.1002, low=1.0990)]
    win = analyze_cycle(value, future_win, cycle=3)
    loss = analyze_cycle(value, future_loss, cycle=3)
    assert win["lineage"] == loss["lineage"]
    assert win["supertrend"] == loss["supertrend"]
    assert win["shadow_candidate"]["counterfactual"] != loss["shadow_candidate"]["counterfactual"]


def test_portfolio_replay_respects_one_active_position_and_chronology():
    first = candidate(
        shadow_candidate_id="first", observed_utc="2026-08-11T12:00:00Z",
        counterfactual={"result": "WIN", "resolution_time": "2026-08-11T12:10:00Z", "hypothetical_r": 2.0, "hypothetical_pnl": 0.2},
    )
    overlap = candidate(
        shadow_candidate_id="overlap", observed_utc="2026-08-11T12:05:00Z",
        counterfactual={"result": "WIN", "resolution_time": "2026-08-11T12:15:00Z", "hypothetical_r": 2.0, "hypothetical_pnl": 0.2},
    )
    later = candidate(
        shadow_candidate_id="later", observed_utc="2026-08-11T12:10:00Z",
        counterfactual={"result": "LOSS", "resolution_time": "2026-08-11T12:20:00Z", "hypothetical_r": -1.0, "hypothetical_pnl": -0.1},
    )
    result = portfolio_replay([overlap, later, first])
    assert result["one_active_position_respected"] is True
    assert result["selected_candidate_ids"] == ["first", "later"]
    assert result["skipped_candidate_ids"] == ["overlap"]
    assert result["total_r"] == 1.0


def test_decision_graph_maps_real_production_source_functions():
    graph = production_decision_graph()
    ids = {item["gate_id"] for item in graph}
    assert {"G01_MARKET_DATA_CONTRACT", "G03_MINIMUM_VOLATILITY", "G05_BUY_TREND_ALIGNMENT", "G09_ONE_ACTIVE_PAPER_POSITION"} <= ids
    assert all(item["source_file"].startswith("automation/forex_engine/") for item in graph)


def test_rolling_audit_state_merge_deduplicates_overlapping_m5_cycles():
    first = build_audit_state(validated(history(count=8)))
    shifted_history = history(count=8)
    for item in shifted_history["candles"]:
        shifted = datetime.fromisoformat(item["observed_at_utc"].replace("Z", "+00:00")) + timedelta(minutes=10)
        item["observed_at_utc"] = shifted.isoformat().replace("+00:00", "Z")
    shifted_history["first_observed_at_utc"] = shifted_history["candles"][0]["observed_at_utc"]
    shifted_history["last_observed_at_utc"] = shifted_history["candles"][-1]["observed_at_utc"]
    second = build_audit_state(shifted_history)
    merged = merge_audit_states(first, second)
    expected = {item["utc"] for item in first["cycle_records"]} | {item["utc"] for item in second["cycle_records"]}
    assert merged["cycles_analyzed"] == len(expected)
    assert len({item["utc"] for item in merged["cycle_records"]}) == len(expected)
    assert merge_audit_states(merged, second)["cycles_analyzed"] == len(expected)


def test_shadow_safety_contract_is_fail_closed():
    state = shadow_audit_safety_state()
    for key in (
        "production_feedback_allowed", "position_open_allowed", "qualifying_trade_credit_allowed",
        "production_pnl_mutation_allowed", "broker_write_performed", "practice_order_performed",
        "live_trade_performed", "money_movement_performed", "credentials_persisted",
    ):
        assert state[key] is False


def test_report_labels_separate_production_shadow_and_supertrend_without_external_state():
    report = render_audit_report(build_audit_state(validated(history())))
    for label in ("PRODUCTION", "SHADOW — NOT EXECUTED", "SUPERTREND — DIAGNOSTIC ONLY"):
        assert label in report


def test_delivery_runner_has_no_broker_access_or_runtime_credential_path():
    source = (
        ROOT / "scripts/forex_delivery/run_forex_p1_shadow_opportunity_audit_v1.py"
    ).read_text(encoding="utf-8")
    forbidden_fragments = (
        "OandaReadOnlyClient",
        "OANDA_API_TOKEN",
        "OANDA_ACCOUNT_ID",
        "OANDA_RUNTIME_CREDENTIALS_REQUIRED",
        "resolve_canonical_practice_transport",
        "extract_sanitized_price_snapshot",
        ".candles(",
        ".pricing(",
        "os.environ",
        "run_observations",
        "_read_only_capture",
        'add_parser("observe")',
        "owner-local-runtime",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)

    args = parser().parse_args(["audit"])
    assert args.command == "audit"
    with pytest.raises(SystemExit):
        parser().parse_args(["observe"])
