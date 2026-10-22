from datetime import datetime,timezone
from automation.forex_engine.forex_m5_immutable_corpus_v2 import START,consensus_open_coverage,cutoff,months,request_windows

def test_cutoff_is_latest_fully_completed_m5():
    assert cutoff(datetime(2026,8,28,12,17,tzinfo=timezone.utc))==datetime(2026,8,28,12,10,tzinfo=timezone.utc)
def test_months_cover_without_overlap():
    end=datetime(2024,3,15,tzinfo=timezone.utc);values=months(START,end);assert values[0][0]==START and values[-1][1]==end and all(a[1]==b[0] for a,b in zip(values,values[1:]))
def test_request_windows_respect_5000_candle_limit():
    values=request_windows(START,datetime(2024,2,1,tzinfo=timezone.utc));assert max((b-a).total_seconds()/300 for a,b in values)<=5000 and all(a[1]==b[0] for a,b in zip(values,values[1:]))
def test_consensus_open_market_classifies_provider_gaps():
    result=consensus_open_coverage({'A':{'t1','t2'},'B':{'t1','t2'},'C':{'t1'}},2)
    assert result['open_timestamp_count']==2 and result['coverage']['C']==.5 and result['classified_provider_gaps']['C']==1 and result['unclassified_critical_gaps']==0
