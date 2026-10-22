from automation.orchestration.aios_gateway_runtime_bridge_v1 import BRIDGE_ENABLED,preview_bridge
def req():return {"session_id":"session_1","route":"LOCAL_VALIDATION","expected_route":"LOCAL_VALIDATION","authority_state":"REVALIDATED","issued_epoch":10,"expires_epoch":20,"payload_digest":"digest_1"}
def test_default_off_preview_has_sanitized_receipt_and_no_network():
 assert BRIDGE_ENABLED is False;r=preview_bridge(req(),now_epoch=15);assert r["status"]=="PREVIEW_ONLY" and not r["bridge_enabled"] and not r["network_used"] and r["deployment"]=="BLOCKED" and set(r["receipt"])=={"result","payload_digest"}
def test_authority_stale_route_and_unknown_clock_block():
 for k,v,now in (("authority_state","STALE",15),("route","OTHER",15),("expires_epoch",15,15),("expires_epoch","unknown",15)):
  x=req();x[k]=v;assert preview_bridge(x,now_epoch=now)["status"]=="BLOCKED"
