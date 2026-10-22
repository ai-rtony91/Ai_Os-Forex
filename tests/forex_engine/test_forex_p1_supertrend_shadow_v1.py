from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from automation.forex_engine.forex_p1_eurusd_market_history_signal_v1 import (
    HISTORY_SCHEMA,
    build_signal_state,
    validate_market_history,
)
from automation.forex_engine.forex_p1_supertrend_shadow_v1 import (
    ATR_LENGTH,
    MULTIPLIER,
    STRATEGY_NAME,
    evaluate_supertrend_shadow,
    supertrend_shadow_safety_state,
)

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def history(count: int = 14, *, rising: bool = True) -> dict:
    candles = []
    for index in range(count):
        close = 1.1000 + (index * 0.0002 * (1 if rising else -1))
        stamp = NOW - timedelta(minutes=5 * (count - 1 - index))
        candles.append({
            "observed_at_utc": stamp.isoformat().replace("+00:00", "Z"),
            "open": close - (0.00005 if rising else -0.00005),
            "high": close + (0.00015 if rising else 0.00025),
            "low": close - (0.00015 if rising else 0.00005),
            "close": close,
            "volume": 100 + index,
            "complete": True,
        })
    return {
        "schema": HISTORY_SCHEMA,
        "evidence_type": "SANITIZED_CANDLE_HISTORY",
        "provenance": "TEST_FIXTURE",
        "broker_label": "OANDA",
        "environment": "PRACTICE",
        "instrument": "EUR_USD",
        "granularity": "M5",
        "requested_count": count,
        "returned_count": count,
        "first_observed_at_utc": candles[0]["observed_at_utc"],
        "last_observed_at_utc": candles[-1]["observed_at_utc"],
        "candles": candles,
        "source_status": "VALID",
        "stale_status": "VALID",
        "read_only": True,
        "complete": True,
        "broker_write_performed": False,
        "credentials_persisted": False,
        "account_identifier_included": False,
        "raw_payload_included": False,
        "order_submission_allowed": False,
        "demo_execution_allowed": False,
        "live_execution_allowed": False,
        "money_movement_allowed": False,
    }


def validated(value: dict) -> dict:
    return validate_market_history(value, now=NOW + timedelta(minutes=5), allow_fixture=True)


def test_supertrend_standard_fixture_and_explicit_configuration():
    result = evaluate_supertrend_shadow(validated(history()))
    assert result["supertrend_direction"] == "BULLISH"
    assert result["supertrend_value"] is not None
    assert result["atr_value"] is not None
    assert result["strategy_name"] == STRATEGY_NAME == "supertrend_pullback_v1"
    assert result["mode"] == "PAPER_ONLY"
    assert result["paper_only"] is True
    assert result["atr_period"] == result["atr_length"] == ATR_LENGTH == 3
    assert result["multiplier"] == MULTIPLIER == 2.0
    assert result["price_distance_to_supertrend"] > 0


def test_supertrend_bearish_fixture_is_diagnostic_not_a_short_trade():
    result = evaluate_supertrend_shadow(validated(history(rising=False)))
    assert result["supertrend_direction"] == "BEARISH"
    assert result["position_open_allowed"] is False
    assert result["production_feedback_allowed"] is False
    assert "direction" not in result or result["supertrend_direction"] != "SELL"


def test_supertrend_insufficient_data_fails_safe():
    result = evaluate_supertrend_shadow(validated(history(count=3)))
    assert result["supertrend_direction"] == "INSUFFICIENT_DATA"
    assert result["supertrend_value"] is None
    assert result["atr_value"] is None
    assert result["supertrend_bars_in_direction"] == 0


def test_supertrend_has_no_production_feedback():
    value = validated(history())
    before_input = copy.deepcopy(value)
    before = build_signal_state(value, generated_at_utc="2026-08-11T12:05:00Z")
    evaluate_supertrend_shadow(value)
    after = build_signal_state(value, generated_at_utc="2026-08-11T12:05:00Z")
    assert before == after
    assert value == before_input
    assert "supertrend" not in before


def test_supertrend_safety_contract_blocks_every_execution_path():
    state = supertrend_shadow_safety_state()
    assert state["strategy_name"] == "supertrend_pullback_v1"
    assert state["paper_only"] is True
    assert state["atr_period"] == 3
    assert state["multiplier"] == 2.0
    assert state["shadow_only"] is True
    assert state["diagnostic_only"] is True
    for key in (
        "production_feedback_allowed", "position_open_allowed",
        "qualifying_trade_credit_allowed", "production_pnl_mutation_allowed",
        "broker_write_performed", "practice_order_performed", "live_trade_performed",
        "money_movement_performed", "credentials_persisted",
    ):
        assert state[key] is False
