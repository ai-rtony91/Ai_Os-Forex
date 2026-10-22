from automation.forex_engine.forex_p1_risk_market_hardening_v1 import (
    HardeningConfig, PairStateStore, clock_latency_integrity, completed_candle_gate,
    daily_drawdown_model, debounce_candidate, h1_supertrend_shadow_filter,
    high_impact_event, idempotency_identity, immutable_bar_identity, news_blackout,
    paper_position_size, reconcile_paper_state, reward_risk_guard, rsi_shadow_filter,
    slippage_model, spread_quality_guard, weekly_performance_drift,
)


def test_completed_bar_and_debounce_are_immutable():
    gate = completed_candle_gate(is_complete=True, candle_open_utc="2026-08-18T12:00:00Z", now_utc="2026-08-18T12:06:00Z")
    assert gate["passed"] is True and gate["candle_close_utc"] == "2026-08-18T12:05:00Z"
    identity = immutable_bar_identity(instrument="EUR_USD", timeframe="M5", candle_open_utc=gate["candle_open_utc"])
    assert debounce_candidate(candidate_id=identity, seen_candidate_ids=[])["passed"] is True
    assert debounce_candidate(candidate_id=identity, seen_candidate_ids=[identity])["duplicate"] is True


def test_shadow_mtf_rsi_and_configured_controls():
    cfg = HardeningConfig()
    assert h1_supertrend_shadow_filter(m5_direction="BUY", h1_bullish=True)["passed"] is True
    assert rsi_shadow_filter(71)["passed"] is False
    assert cfg.h1_atr_period == 10 and cfg.h1_supertrend_multiplier == 3.0
    assert reward_risk_guard(1.5)["production_passed"] is True
    assert reward_risk_guard(1.75)["shadow_strict_passed"] is False


def test_pair_state_isolation_and_paper_sizing():
    store = PairStateStore(); store.set("EUR_USD", "M5", {"active": "eur"}); store.set("GBP_USD", "M5", {"active": "gbp"})
    assert store.get("EUR_USD", "M5")["active"] == "eur"
    assert store.get("GBP_USD", "M5")["active"] == "gbp"
    size = paper_position_size(account_equity=10000, entry=1.1, stop=1.099)
    assert size["risk_percent"] == 1.0 and size["units"] == 100000 and size["live_trade_performed"] is False


def test_spread_slippage_news_and_drawdown_are_analysis_only():
    assert spread_quality_guard(spread=0.0003, rolling_spreads=[0.0001, 0.0002])["passed"] is False
    assert slippage_model(signal_price=1.1, quote_price=1.1001, spread=0.0002)["order_submitted"] is False
    event = high_impact_event(event_id="nfp-1", name="NFP", event_utc="2026-08-18T13:30:00Z")
    assert news_blackout(evaluation_utc="2026-08-18T13:15:00Z", event=event)["blocked"] is True
    assert daily_drawdown_model(starting_equity=10000, current_equity=9700)["paper_shadow_halt"] is True


def test_idempotency_reconciliation_latency_and_weekly_drift():
    identity = idempotency_identity(instrument="EUR_USD", timeframe="M5", bar_identity="b1", strategy_name="s", entry=1, stop=.9, target=1.2)
    assert identity == idempotency_identity(instrument="EUR_USD", timeframe="M5", bar_identity="b1", strategy_name="s", entry=1, stop=.9, target=1.2)
    assert reconcile_paper_state(local_position={"instrument": "EUR_USD"}, broker_snapshot={"instrument": "GBP_USD"})["match"] is False
    assert clock_latency_integrity(broker_timestamp_utc="2026-08-18T12:05:00Z", candle_close_utc="2026-08-18T12:05:00Z", pricing_timestamp_utc="2026-08-18T12:05:30Z", evaluated_at_utc="2026-08-18T12:06:00Z")["passed"] is True
    drift = weekly_performance_drift([{"outcome_r": 1}, {"outcome_r": -1, "outcome_classification": "FALSE_POSITIVE"}])
    assert drift["resolved"] == 2 and drift["production_mutation_allowed"] is False
