from automation.forex_engine import forex_m5_day_trading_adapter_v2 as m5


def test_m5_bridge_positive_trace_validates():
    trace = m5.make_m5_trace()
    result = m5.validate_m5_trace(trace, m5.make_m5_trace())
    assert result["overall_valid"] is True
    assert result["criteria"]["NEXT_M5_ENTRY"] is True
    assert result["criteria"]["M5_SIGNAL_CANDLE_COMPLETE"] is True


def test_m5_bridge_rejects_targeted_mutations():
    for mutation in ["partial_h1_context", "signal_candle_entry", "wrong_bid_ask", "duplicate_m5_event", "future_external_information"]:
        assert m5.m5_mutation_rejected(mutation), mutation
