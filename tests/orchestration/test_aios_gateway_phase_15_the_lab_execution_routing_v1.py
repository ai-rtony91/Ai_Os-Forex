from automation.orchestration.aios_the_lab_execution_router_v1 import preview_lab_route
def req():return {"mode":"PAPER","route":"THE_LAB_PREVIEW","expected_route":"THE_LAB_PREVIEW","authority":"PAPER_ONLY","required_authority":"PAPER_ONLY","approval_expires_epoch":20,"route_digest":"digest","expected_route_digest":"digest"}
def test_paper_preview_has_no_broker_order_or_money_capability():
 r=preview_lab_route(req(),now_epoch=10);assert r["status"]=="PREVIEW_ONLY" and not r["broker_call"] and not r["order_submitted"] and not r["money_moved"] and r["risk_policy_preserved"]
def test_live_authority_stale_and_tampered_routes_block():
 for k,v in (("mode","LIVE"),("authority","LIVE"),("approval_expires_epoch",10),("route_digest","tampered")):
  x=req();x[k]=v;assert preview_lab_route(x,now_epoch=10)["status"]=="BLOCKED"
