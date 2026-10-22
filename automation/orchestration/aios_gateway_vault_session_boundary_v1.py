"""Phase 16 opaque-reference session boundary; never retrieves secrets."""
from __future__ import annotations
import re
from typing import Any, Mapping
OPAQUE=re.compile(r"^vaultref_[A-Za-z0-9_-]{8,96}$")

def authorize_reference(request:Mapping[str,Any],*,now_epoch:int)->dict[str,Any]:
    required={"vault_reference","session_id","bound_session_id","scope","allowed_scope","expires_epoch","revoked","vault_state"}
    if set(request)!=required:return _blocked("INVALID_SHAPE")
    ref=request.get("vault_reference")
    if not isinstance(ref,str) or not OPAQUE.fullmatch(ref):return _blocked("NON_OPAQUE_REFERENCE")
    if request["vault_state"]!="AVAILABLE":return _blocked("VAULT_UNAVAILABLE")
    if request["revoked"]:return _blocked("REVOKED_SESSION")
    if request["session_id"]!=request["bound_session_id"]:return _blocked("CROSS_SESSION_REUSE")
    if request["scope"]!=request["allowed_scope"]:return _blocked("LEAST_PRIVILEGE_SCOPE_MISMATCH")
    if not isinstance(request["expires_epoch"],int) or now_epoch>=request["expires_epoch"]:return _blocked("EXPIRED_SESSION")
    return {"status":"REFERENCE_AUTHORIZED_NOT_RETRIEVED","vault_reference":ref,"secret_retrieved":False,"secret_persisted":False,"credential_logged":False}

def redact(value:str)->str:return "[REDACTED]" if value else ""
def _blocked(reason:str)->dict[str,Any]:return {"status":"BLOCKED","reason":reason,"secret_retrieved":False,"secret_persisted":False,"credential_logged":False}
