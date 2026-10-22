from automation.orchestration.aios_gateway_router_contract_v1 import route_message
def msg(): return {"message_id":"msg_12345","intent":"VALIDATE","authority":"NONE","required_authority":"NONE","policy":"LOCAL","required_policy":"LOCAL","issued_epoch":10,"expires_epoch":20,"consumed":False,"route_binding":"VALIDATE:LOCAL_VALIDATION"}
def test_routes_deterministically_without_execution():
 r=route_message(msg(),now_epoch=15); assert r=={"status":"ROUTED_NOT_EXECUTED","destination":"LOCAL_VALIDATION","message_id":"msg_12345","execution_performed":False}
def test_unknown_mismatch_duplicate_stale_and_confused_deputy_block():
 changes=[("intent","EXECUTE"),("authority","OWNER"),("policy","OTHER"),("consumed",True),("route_binding","VALIDATE:WRONG")]
 for k,v in changes:
  x=msg();x[k]=v;assert route_message(x,now_epoch=15)["status"]=="BLOCKED"
 assert route_message(msg(),now_epoch=20)["reason"]=="STALE_MESSAGE"
