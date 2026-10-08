from datetime import datetime,timezone
from automation.forex_engine import forex_session_inventory_cycle_v1 as s

def test_five_variants_and_attempt_accounting():
    assert len(s.candidate_definitions())==5
    assert {x['direction_variant'] for x in s.candidate_definitions()}==set(s.DIRECTIONS)
    assert s.CUMULATIVE_ATTEMPTS==s.PRIOR_ATTEMPTS+5

def test_pair_eligibility_is_cross_session_and_broad():
    assert s.pair_is_eligible('EUR_USD')
    assert s.pair_is_eligible('AUD_JPY')
    assert not s.pair_is_eligible('EUR_GBP')
    assert not s.pair_is_eligible('USD_CNH')

def test_dst_aware_london_signal_changes_utc_hour():
    winter=s.local_session_signals('EUR_USD','2024-01-15T08:00:00Z')
    summer=s.local_session_signals('EUR_USD','2024-07-15T07:00:00Z')
    assert ('SHORT','EUR') in winter
    assert ('SHORT','EUR') in summer

def test_new_york_quote_session_original_direction_long():
    signals=s.local_session_signals('EUR_USD','2024-01-15T13:00:00Z')
    assert ('LONG','USD') in signals

def test_no_trade_baseline_strictly_rejects_zero_and_negative():
    worse={'expectancy_r':-1.0}
    assert not s.baseline_gate({'expectancy_r':0.0},worse,worse)
    assert not s.baseline_gate({'expectancy_r':-0.1},worse,worse)

def test_family_is_not_session_breakout():
    d=s.family_descriptor()
    assert d['mechanism']=='LOCAL_HOURS_CROSS_BORDER_INVENTORY_DEMAND'
    assert 'breakout' not in str(d).lower()

def test_hold_and_stop_are_frozen_cost_resistant_horizon():
    assert s.HOLDING_BARS==48
    assert s.STOP_ATR==2.0
    assert s.core.DEV_END<s.core.HOLDOUT_START
