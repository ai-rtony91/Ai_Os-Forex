from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json, subprocess, sys
import pytest
import automation.forex_engine.forex_p1_oanda_practice_snapshot_capture_v1 as m

NOW=datetime(2026,8,6,10,1,tzinfo=timezone.utc)
def raw(): return {"prices":[{"instrument":"EUR_USD","time":"2026-08-06T10:00:00Z","bids":[{"price":"1.1000"}],"asks":[{"price":"1.1002"}],"accountID":"must-not-survive"}]}
def snap(): return m.extract_sanitized_price_snapshot(raw(), now=NOW)
def candidate(**changes):
    value={"strategy_id":"s1","candidate_id":"c1","instrument":"EUR_USD","direction":"BUY","units":100,"stop_price":1.099,"target_price":1.102,"risk_amount":.12,"entry_rationale":"bounded momentum review","status":"PAPER_ELIGIBLE","sanitized":True,"current":True}
    value.update(changes); return value

def test_resolves_canonical_transport():
    cls=m.resolve_canonical_practice_transport(); assert cls.__module__=="automation.forex_engine.oanda_read_only_client"
def test_configuration_is_practice_only():
    assert m.validate_practice_runtime_configuration(environment="practice",instrument="EUR_USD",owner_local_runtime=True)["read_only"]
    for kwargs in ({"environment":"live","instrument":"EUR_USD","owner_local_runtime":True},{"environment":"practice","instrument":"GBP_USD","owner_local_runtime":True},{"environment":"practice","instrument":"EUR_USD","owner_local_runtime":False}):
        with pytest.raises(ValueError): m.validate_practice_runtime_configuration(**kwargs)
def test_extraction_allowlist_and_fixture_zero_credit():
    value=snap(); assert set(value)==m.SNAPSHOT_KEYS and "accountID" not in value and value["broker_call_performed"] is False
    state=m.build_capture_state(); assert state["qualifying_p1_trade_count_changed"] is False and state["genuine_snapshot_captured"] is False
def test_snapshot_freshness_and_prices():
    value=snap(); assert m.validate_sanitized_snapshot(value,now=NOW)["ask"]==1.1002
    with pytest.raises(ValueError,match="stale_snapshot"): m.validate_sanitized_snapshot(value,now=datetime(2026,8,6,11,tzinfo=timezone.utc))
    with pytest.raises(ValueError): m.validate_sanitized_snapshot({**value,"bid":float("nan")},now=NOW)
def test_candidate_match_and_open_uses_canonical_controller(monkeypatch,tmp_path):
    value=snap(); monkeypatch.setattr(m,"validate_sanitized_snapshot",lambda x:dict(x)); calls=[]
    request=m.prepare_session_open_request(candidate(),value,"Anthony","2026-08-06T10:01:00Z",tmp_path/"active.json")
    import automation.forex_engine.forex_p1_supervised_paper_session_v1 as controller
    monkeypatch.setattr(controller,"open_paper_session",lambda *args:calls.append(args) or {"status":"ACTIVE"})
    assert m.open_session_through_canonical_controller(request)["status"]=="ACTIVE" and calls[0][0]["ask"]==1.1002
@pytest.mark.parametrize("change",[{"status":"WATCH"},{"direction":"SELL"},{"units":0},{"live_execution_allowed":True},{"entry_rationale":"synthetic example"}])
def test_bad_candidates_are_not_fabricated(change):
    with pytest.raises(ValueError,match="NO_PAPER_TRADE_CANDIDATE"): m.validate_paper_candidate(candidate(**change))
def test_default_cli_is_offline_and_handoff_is_exact():
    root=Path(__file__).parents[2]; runner=root/"scripts/forex_delivery/run_forex_p1_oanda_practice_snapshot_capture_v1.py"
    result=subprocess.run([sys.executable,str(runner)],cwd=root,text=True,capture_output=True,check=True); data=json.loads(result.stdout)
    assert data["network_call_performed"] is False
    handoff=subprocess.run([sys.executable,str(runner),"print-owner-handoff"],cwd=root,text=True,capture_output=True,check=True).stdout
    assert "C:\\Dev\\Ai.Os" in handoff and "OANDA_DEMO_ACCESS_TOKEN" in handoff
    assert "OANDA_DEMO_ACCOUNT_ID" in handoff and "No OANDA order is placed" in handoff
    assert "<" not in handoff and "TODO" not in handoff
def test_schema_and_build_state_parse():
    root=Path(__file__).parents[2]; schema=json.loads((root/"schemas/forex_delivery/aios_p1_oanda_practice_snapshot_capture_v1.schema.json").read_text())
    assert schema["additionalProperties"] is False and set(schema["required"])==m.SNAPSHOT_KEYS
