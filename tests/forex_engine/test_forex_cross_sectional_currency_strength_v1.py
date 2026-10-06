import json
from pathlib import Path

from automation.forex_engine.forex_cross_sectional_currency_strength_v1 import (
    _gate, _metrics, aggregate_currency_exposure, candidates, direct_pair,
    exposure_allowed, iter_candles, pair_return_signs, strength_scores, write_outputs,
)

def fake_result(status="CLOSED_FAILED_POSTMORTEM_PENDING", survivors=None):
    metric={"expectancy_r":-0.1,"profit_factor":0.9,"maximum_drawdown_pct":11.0}
    rows={}
    for item in candidates():
        rows[item["candidate_id"]]={"definition":item,"validation":metric,"stress_validation":metric,"gates":{"base":False}}
    return {"status":status,"survivors":[] if survivors is None else survivors,"candidate_results":rows,"holdout_status":"NOT_EVALUATED","safety":{"network":False}}

def test_pair_return_signs_and_inversion():
    assert pair_return_signs("EUR_USD")=={"EUR":1,"USD":-1}
    assert direct_pair("EUR","USD")==("EUR_USD","LONG")
    assert direct_pair("USD","EUR")==("EUR_USD","SHORT")

def test_strength_scores_have_correct_currency_signs():
    s=strength_scores({"EUR_USD":0.01,"GBP_USD":-0.02,"USD_JPY":0.03})
    assert s["EUR"]>0 and s["GBP"]<0 and s["JPY"]<0

def test_non_direct_cross_is_skipped(): assert direct_pair("EUR","GBP") is None

def test_currency_exposure_aggregation():
    assert aggregate_currency_exposure([{"pair":"EUR_USD","direction":"LONG","risk":1}])=={"EUR":1,"USD":-1}

def test_duplicate_currency_exposure_is_blocked():
    p=[{"pair":"EUR_USD","direction":"LONG","risk":1}]
    assert not exposure_allowed(p,"GBP_USD","LONG")

def test_candidate_grid_is_exact_and_bounded():
    c=candidates();assert len(c)==12;assert {x["lookback"] for x in c}=={15,30,60};assert {x["holding"] for x in c}=={15,30}

def test_stream_stops_before_holdout_without_parsing_later_object(tmp_path):
    p=tmp_path/"batch.json";p.write_text('{\n"candles": [\n{"complete":true,"time":"2025-12-31T23:59:00.000000000Z","bid":{"o":"1","h":"1","l":"1","c":"1"},"ask":{"o":"1","h":"1","l":"1","c":"1"}},\n{"complete":true,"time":"2026-01-01T00:00:00.000000000Z","forbidden":true},\nTHIS_IS_NOT_JSON\n]}',encoding="utf-8")
    out=list(iter_candles(p,"2026-01-01T00:00:00"));assert len(out)==1;assert "forbidden" not in out[0]

def test_metrics_apply_cost_drawdown_and_counts():
    trades=[{"r":1.5,"pair":"EUR_USD","direction":"LONG","fold":i%6} for i in range(120)]+[{"r":-1,"pair":"GBP_USD","direction":"SHORT","fold":i%6} for i in range(80)]
    m=_metrics(trades);assert m["trade_count"]==200;assert m["profit_factor"]>1.1;assert m["instrument_count"]==2

def test_gate_rejects_inadequate_sample():
    m=_metrics([]);assert not _gate(m)

def test_write_outputs_are_truthful_and_sealed(tmp_path):
    result=fake_result()
    receipt=write_outputs(result,{"x":1},tmp_path/"out",tmp_path/"report.md",tmp_path/"reject.json")
    assert receipt["candidate_count"]==12 and receipt["holdout_status"]=="NOT_EVALUATED"
    rejection=json.loads((tmp_path/"reject.json").read_text())
    assert rejection["status"]=="POSTMORTEM_COMPLETE_REJECTED"
    assert len(rejection["candidate_rows"])==12
    assert len(rejection["family_fingerprint"])==64
    assert rejection["next_distinct_family"]["family"]=="CROSS_PAIR_RESIDUAL_COINTEGRATION_MEAN_REVERSION"

def test_manifest_has_hashes_and_bytes(tmp_path):
    result=fake_result("PRE_HOLDOUT_SURVIVOR",["x"])
    write_outputs(result,{"x":1},tmp_path/"out",tmp_path/"report",tmp_path/"reject")
    m=json.loads((tmp_path/"out/AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_MANIFEST.json").read_text());assert all(x["bytes"]>0 and len(x["sha256"])==64 for x in m.values())

def test_no_network_or_broker_vocabulary_in_runtime_api():
    import automation.forex_engine.forex_cross_sectional_currency_strength_v1 as module
    assert not hasattr(module,"requests") and not hasattr(module,"socket")
