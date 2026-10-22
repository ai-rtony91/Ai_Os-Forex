from automation.orchestration.aios_gateway_vault_session_boundary_v1 import authorize_reference,redact
def req():return {"vault_reference":"vaultref_opaque123","session_id":"session_a","bound_session_id":"session_a","scope":"sign_preview","allowed_scope":"sign_preview","expires_epoch":20,"revoked":False,"vault_state":"AVAILABLE"}
def test_opaque_reference_only_and_no_secret_access_or_logging():
 r=authorize_reference(req(),now_epoch=10);assert r["status"]=="REFERENCE_AUTHORIZED_NOT_RETRIEVED" and not r["secret_retrieved"] and not r["secret_persisted"] and not r["credential_logged"] and redact("sensitive")=="[REDACTED]"
def test_nonopaque_expired_revoked_unavailable_cross_session_scope_fail_closed():
 for k,v in (("vault_reference","real-secret-value"),("expires_epoch",10),("revoked",True),("vault_state","ERROR"),("bound_session_id","session_b"),("allowed_scope","admin")):
  x=req();x[k]=v;assert authorize_reference(x,now_epoch=10)["status"]=="BLOCKED"
