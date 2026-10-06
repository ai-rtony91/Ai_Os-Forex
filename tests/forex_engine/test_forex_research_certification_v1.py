from automation.forex_engine.forex_research_certification_v1 import Candle, OrderIntent, aggregate_complete, execute_intent, execute_unique, maximum_drawdown_pct


def c(n, bid_o=100, bid_h=100, bid_l=100, bid_c=100, spread=1, complete=True):
    return Candle(f"2026-01-01T00:{n:02d}:00Z", bid_o, bid_h, bid_l, bid_c, bid_o+spread, bid_h+spread, bid_l+spread, bid_c+spread, complete)


def test_c1_long_plus_2r():
    out=execute_intent([c(0),c(1,100,105,100,103)],OrderIntent("e","LONG",0,99,105));assert out["reason"]=="TARGET" and out["realized_r"]==2
def test_c2_long_minus_1r():
    out=execute_intent([c(0),c(1,100,102,98,99)],OrderIntent("e","LONG",0,99,105));assert out["reason"]=="STOP" and out["realized_r"]==-1
def test_c3_short_plus_2r():
    out=execute_intent([c(0),c(1,100,100,95,96)],OrderIntent("e","SHORT",0,102,96));assert out["reason"]=="TARGET" and out["realized_r"]==2
def test_c4_short_minus_1r():
    out=execute_intent([c(0),c(1,100,102,99,101)],OrderIntent("e","SHORT",0,102,96));assert out["reason"]=="STOP" and out["realized_r"]==-1
def test_c5_signal_bar_long_cross_does_not_exit():
    out=execute_intent([c(0,100,101,90,100),c(1,100,106,100,105)],OrderIntent("e","LONG",0,99,105));assert out["reason"]=="TARGET" and out["exit_index"]==1
def test_c6_signal_bar_short_cross_does_not_exit():
    out=execute_intent([c(0,100,110,99,100),c(1,100,100,95,96)],OrderIntent("e","SHORT",0,102,96));assert out["reason"]=="TARGET" and out["exit_index"]==1
def test_c7_same_bar_stop_first():
    out=execute_intent([c(0),c(1,100,106,98,100)],OrderIntent("e","LONG",0,99,105));assert out["reason"]=="STOP"
def test_c8_long_uses_ask_entry_and_bid_exit():
    out=execute_intent([c(0),c(1,100,102,100,101)],OrderIntent("e","LONG",0,99,110));assert out["entry"]==101 and out["exit"]==101
def test_c9_short_uses_bid_entry_and_ask_exit():
    out=execute_intent([c(0),c(1,100,100,99,99)],OrderIntent("e","SHORT",0,102,90));assert out["entry"]==100 and out["exit"]==100
def test_c10_entry_gap_invalidation():
    assert execute_intent([c(0),c(1,bid_o=97)],OrderIntent("e","LONG",0,99,105))["status"]=="ENTRY_INVALIDATED_BY_GAP"
def test_c11_duplicate_event_suppression():
    values=execute_unique([c(0),c(1)], [OrderIntent("e","LONG",0,99,110),OrderIntent("e","LONG",0,99,110)]);assert len(values)==1
def test_c12_initial_r_is_frozen():
    out=execute_intent([c(0),c(1,100,106,100,105)],OrderIntent("e","LONG",0,99,105));assert out["initial_risk"]==2 and out["realized_r"]==2
def test_c13_running_peak_drawdown():
    assert round(maximum_drawdown_pct([2,-1,-1]),6)==round(100*((100000*1.005)-(100000*1.005*.9975*.9975))/(100000*1.005),6)
def test_c14_trade_cannot_close_before_entry():
    out=execute_intent([c(0,100,200,1,100),c(1,100,106,100,105)],OrderIntent("e","LONG",0,99,105));assert out["entry_index"]==1 and out["exit_index"]>=1
def test_c15_incomplete_aggregate_cannot_signal():
    assert aggregate_complete([c(0),c(1),c(2,complete=False)],3)==[] and aggregate_complete([c(0),c(1)],3)==[]
def test_c16_end_sample_uses_executable_side():
    long=execute_intent([c(0),c(1,bid_c=103)],OrderIntent("l","LONG",0,99,110));short=execute_intent([c(0),c(1,bid_c=97)],OrderIntent("s","SHORT",0,102,90));assert long["exit"]==103 and short["exit"]==98
