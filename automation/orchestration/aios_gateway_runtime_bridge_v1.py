"""Phase 14 local bridge preview. It has no network or background capability."""
from __future__ import annotations
from typing import Any, Mapping
BRIDGE_ENABLED=False

def preview_bridge(request:Mapping[str,Any],*,now_epoch:int)->dict[str,Any]:
    if BRIDGE_ENABLED:return _blocked("UNSAFE_CONFIGURATION")
    required={"session_id","route","expected_route","authority_state","issued_epoch","expires_epoch","payload_digest"}
    if set(request)!=required:return _blocked("INVALID_SHAPE")
    if request["authority_state"]!="REVALIDATED":return _blocked("AUTHORITY_NOT_REVALIDATED")
    if request["route"]!=request["expected_route"]:return _blocked("ROUTE_MISMATCH")
    if not all(isinstance(request[k],int) for k in ("issued_epoch","expires_epoch")) or not isinstance(now_epoch,int):return _blocked("UNKNOWN_CLOCK")
    if now_epoch<request["issued_epoch"] or now_epoch>=request["expires_epoch"]:return _blocked("STALE_SESSION")
    return {"status":"PREVIEW_ONLY","bridge_enabled":False,"network_used":False,"deployment":"BLOCKED","session_id":request["session_id"],"receipt":{"result":"NOT_DISPATCHED","payload_digest":request["payload_digest"]}}

def _blocked(reason:str)->dict[str,Any]:return {"status":"BLOCKED","reason":reason,"bridge_enabled":False,"network_used":False,"deployment":"BLOCKED"}
