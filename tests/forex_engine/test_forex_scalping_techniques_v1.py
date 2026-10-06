from __future__ import annotations

import pytest

from automation.forex_engine.forex_scalping_techniques_v1 import (
    bollinger_state,
    build_technique_contracts,
    ema,
    opening_range_breakout,
    rsi,
    technique_fidelity_state,
)


def test_ema_and_rsi_are_deterministic():
    values = [float(i) for i in range(40)]
    assert ema(values, 5)[4] == 2
    assert rsi(values, 14)[-1] == 100.0


def test_rsi_first_value_requires_exactly_period_changes():
    assert rsi([10.0, 12.0, 11.0], 3) == [None, None, None]
    # Changes +2, -1, +3 give mean gain 5/3 and mean loss 1/3.
    assert rsi([10.0, 12.0, 11.0, 14.0], 3) == [None, None, None, pytest.approx(250 / 3)]


def test_rsi_wilder_reference_includes_first_post_seed_change():
    # Fourth change -2: averages 10/9 and 8/9 => RSI 500/9.
    # Fifth change +3: averages 47/27 and 16/27 => RSI 4700/63.
    values = [10.0, 12.0, 11.0, 14.0, 12.0, 15.0]
    assert rsi(values, 3)[3:] == pytest.approx([250 / 3, 500 / 9, 4700 / 63])


def test_rsi_14_reference_vector():
    # Fixed Wilder example: first fourteen deltas sum to +3.34 / -1.40.
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
              45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00]
    assert rsi(closes)[:14] == [None] * 14
    assert rsi(closes)[14:] == pytest.approx([70.46413502109705, 66.24961855355505])


@pytest.mark.parametrize("values,expected", [
    ([1.0] * 18, 50.0),
    (list(map(float, range(18))), 100.0),
    (list(map(float, range(18, 0, -1))), 0.0),
])
def test_rsi_flat_up_and_down(values, expected):
    assert rsi(values)[14:] == [expected] * 4


def test_rsi_future_values_do_not_change_past_values_or_filter_decisions():
    prefix = [10.0, 12.0, 11.0, 14.0, 12.0, 15.0, 9.0, 8.0]
    expected = rsi(prefix, 3)
    for suffix in ([1.0, 1000.0], [5000.0, 0.01], []):
        actual = rsi(prefix + suffix, 3)[:len(prefix)]
        assert actual == expected
        assert [(v <= 70, v >= 30) for v in actual if v is not None] == [
            (v <= 70, v >= 30) for v in expected if v is not None
        ]


@pytest.mark.parametrize("period", [0, -1, 1.5, True])
def test_rsi_rejects_invalid_period(period):
    with pytest.raises(ValueError, match="positive integer"):
        rsi([1.0, 2.0], period)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_rsi_rejects_nonfinite_closes_even_during_warmup(bad):
    with pytest.raises(ValueError, match="finite"):
        rsi([1.0, bad])


def test_rsi_empty_and_period_one():
    assert rsi([]) == []
    assert rsi([1.0, 2.0, 1.0, 1.0], 1) == [None, 100.0, 0.0, 50.0]


def test_opening_range_breakout_uses_prior_range_only():
    rows = [{"high": 1.0, "low": 0.5, "close": 0.75} for _ in range(12)]
    rows.append({"high": 1.2, "low": 0.7, "close": 1.1})
    assert opening_range_breakout(rows, 12) == "LONG"


def test_fidelity_rejects_order_book_claims():
    state = technique_fidelity_state()
    assert state["order_book_claims"] is False
    assert state["centralized_volume_claims"] is False
    assert bollinger_state([1.0] * 25, 24) == "INSIDE"


def test_all_82_inventory_techniques_have_objective_directional_contracts():
    contracts = build_technique_contracts()
    assert len(contracts) == 82
    assert len({contract["technique_id"] for contract in contracts}) == 82
    assert all(contract["directions"] == ["LONG", "SHORT"] for contract in contracts)
    assert all(contract["direction_isolation_required"] is True for contract in contracts)
    assert all(contract["completed_bar_only"] is True for contract in contracts)
    assert all(contract["objective_entry_rules"] for contract in contracts)
    assert all(contract["objective_exit_rules"] for contract in contracts)
    assert all(contract["controls"] for contract in contracts)
    assert all(len(contract["fingerprint"]) == 64 for contract in contracts)


def test_order_flow_and_subminute_contracts_fail_closed_without_data():
    contracts = build_technique_contracts()
    blocked = [contract for contract in contracts if contract["family_id"] in {"K", "L"}]
    assert blocked
    assert all(contract["data_eligible"] is False for contract in blocked)
    assert all(contract["eligibility_status"] == "INELIGIBLE_REQUIRED_DATA_NOT_FROZEN" for contract in blocked)


def test_contract_registry_distinguishes_implemented_from_contract_only():
    state = technique_fidelity_state()
    assert state["inventory_contract_count"] == 82
    assert state["implemented_primitive_count"] == 6
    assert state["contract_only_count"] == 76
    assert state["data_ineligible_contract_count"] == 14
    assert len(state["contract_registry_hash"]) == 64


def s6_rows():
    from datetime import datetime, timedelta, timezone
    start = datetime(2024, 1, 3, 10, tzinfo=timezone.utc)
    return [{"timestamp": (start+timedelta(minutes=5*i)).isoformat(), "complete": True,
             "open": 1., "high": 1.0003, "low": .9997, "close": 1., "spread": .0001}
            for i in range(35)]


def peer_fixture(direction=1):
    import copy
    pairs = ["AUD_USD", "EUR_USD", "GBP_USD", "NZD_USD"]
    rows = {p:copy.deepcopy(s6_rows()) for p in pairs}
    for p in pairs[1:]:
        rows[p][21].update(close=1+direction*.0012, high=1.0015, low=.9985)
    rows[pairs[0]][22].update(close=1+direction*.0003, high=1.0006, low=.9994)
    return rows


@pytest.mark.parametrize("direction", [1, -1])
def test_peer_shock_requires_later_response_and_is_prefix_invariant(direction):
    from automation.forex_engine.forex_scalping_techniques_v1 import s6_peer_shock_signals
    rows = peer_fixture(direction)
    assert not any(s6_peer_shock_signals({p:r[:22] for p,r in rows.items()}).values())
    expected = s6_peer_shock_signals({p:r[:23] for p,r in rows.items()})
    signal = expected["AUD_USD"][0]
    assert signal["direction"] == direction and signal["signal_index"] == 22 and signal["entry_index"] == 23
    assert len(signal["proof"]["peer_body_atr"]) == 3
    assert signal["proof"]["response_age_bars"] == 1
    rows["NZD_USD"][28].update(close=10, high=11)
    assert {p:[s for s in v if s["signal_index"] <= 22] for p,v in s6_peer_shock_signals(rows).items()} == expected


def test_peer_missing_timestamp_resets_pending_without_forward_fill():
    from automation.forex_engine.forex_scalping_techniques_v1 import s6_peer_shock_signals
    rows = peer_fixture(); del rows["EUR_USD"][22]
    assert not any(s6_peer_shock_signals(rows).values())


def test_peer_shock_requires_all_peers_not_a_single_pair_momentum_proxy():
    from automation.forex_engine.forex_scalping_techniques_v1 import s6_peer_shock_signals
    rows = peer_fixture(); rows["EUR_USD"][21] = s6_rows()[21]
    assert not any(s6_peer_shock_signals(rows).values())
    rows = peer_fixture(); rows["AUD_USD"][22] = s6_rows()[22]
    assert not any(s6_peer_shock_signals(rows).values())


def test_peer_shock_stale_response_and_reversed_peer_cancel():
    from automation.forex_engine.forex_scalping_techniques_v1 import s6_peer_shock_signals
    rows = peer_fixture(); rows["AUD_USD"][22] = s6_rows()[22]
    rows["AUD_USD"][25].update(close=1.0004, high=1.0007)
    assert not any(s6_peer_shock_signals(rows).values())
    rows = peer_fixture(); rows["EUR_USD"][22].update(close=.998, low=.997)
    assert not any(s6_peer_shock_signals(rows).values())


def test_peer_shock_duplicate_incomplete_and_expanded_pair_scope_fail():
    from automation.forex_engine.forex_scalping_techniques_v1 import s6_peer_shock_signals
    rows = peer_fixture(); rows["AUD_USD"][22]["timestamp"] = rows["AUD_USD"][21]["timestamp"]
    with pytest.raises(ValueError, match="DUPLICATE"): s6_peer_shock_signals(rows)
    rows = peer_fixture(); rows["AUD_USD"][22]["complete"] = False
    with pytest.raises(ValueError, match="INVALID_COMPLETED"): s6_peer_shock_signals(rows)
    rows = peer_fixture(); rows.pop("AUD_USD")
    with pytest.raises(ValueError, match="EXACT_FOUR"): s6_peer_shock_signals(rows)


def test_s6_confirmed_pivot_break_then_later_retest_is_causal():
    from automation.forex_engine.forex_scalping_techniques_v1 import s6_price_signals
    rows = s6_rows()
    rows[21].update(high=1.001, close=1.0004)
    for i in (22, 23): rows[i].update(high=1.0006, close=1.0002)
    rows[24].update(open=1.0002, high=1.0016, low=1.0001, close=1.0014)
    rows[25].update(open=1.0011, high=1.0015, low=1.00095, close=1.0013)
    prefix = s6_price_signals(rows[:26], "E1_SWING_BREAK_RETEST")
    assert len(prefix) == 1
    assert prefix[0]["signal_index"] == 25 and prefix[0]["entry_index"] == 26
    assert prefix[0]["proof"]["break_index"] == 24
    assert prefix[0]["proof"]["level"] == 1.001
    rows[27].update(high=100, close=99)
    assert [s for s in s6_price_signals(rows, "E1_SWING_BREAK_RETEST") if s["signal_index"] < 26] == prefix
    assert s6_price_signals(rows[:25], "E1_SWING_BREAK_RETEST") == []


def test_s6_channel_reentry_and_spread_state_are_distinct_sequences():
    from automation.forex_engine.forex_scalping_techniques_v1 import s6_price_signals
    rows = s6_rows()
    rows[21].update(low=.9984, close=.9985)
    rows[22].update(open=.9986, low=.9985, high=.9992, close=.9991)
    signals = s6_price_signals(rows[:23], "C2_KELTNER_REVERSION")
    assert len(signals) == 1 and signals[0]["direction"] == 1
    assert signals[0]["proof"]["excursion_index"] == 21
    assert s6_price_signals(rows[:22], "C2_KELTNER_REVERSION") == []
    rows = s6_rows(); rows[20]["spread"] = .0004
    rows[21].update(high=1.0012, close=1.001)
    signals = s6_price_signals(rows[:22], "G4_SPREAD_COMPRESSION_IMPULSE")
    assert len(signals) == 1 and signals[0]["direction"] == 1
    rows[20]["spread"] = .0001
    assert s6_price_signals(rows[:22], "G4_SPREAD_COMPRESSION_IMPULSE") == []


@pytest.mark.parametrize("technique", ["E1_SWING_BREAK_RETEST", "C2_KELTNER_REVERSION", "G4_SPREAD_COMPRESSION_IMPULSE"])
def test_s6_prefix_invariance_gap_reset_and_invalid_rows(technique):
    from automation.forex_engine.forex_scalping_techniques_v1 import s6_price_signals
    rows = s6_rows()
    expected = s6_price_signals(rows[:25], technique)
    assert [s for s in s6_price_signals(rows, technique) if s["signal_index"] < 25] == expected
    rows[23]["timestamp"] = rows[22]["timestamp"]
    with pytest.raises(ValueError, match="DUPLICATE"): s6_price_signals(rows, technique)
    rows = s6_rows(); rows[22]["complete"] = False
    with pytest.raises(ValueError, match="COMPLETED"): s6_price_signals(rows, technique)
    rows = s6_rows(); rows[20]["spread"] = .0004; rows[21].update(high=1.0012, close=1.001)
    rows[21]["timestamp"] = "2024-01-03T14:00:00+00:00"
    assert s6_price_signals(rows[:22], technique) == []
