"""Phase 13 deterministic, non-executing gateway router."""
from __future__ import annotations
from typing import Any, Mapping
ROUTES={"INSPECT":"READ_ONLY_REVIEW","STATUS":"READ_ONLY_REVIEW","PREPARE":"LOCAL_PREPARATION","VALIDATE":"LOCAL_VALIDATION"}

def route_message(message:Mapping[str,Any], *, now_epoch:int)->dict[str,Any]:
    required={"message_id","intent","authority","required_authority","policy","required_policy","issued_epoch","expires_epoch","consumed","route_binding"}
    if set(message)!=required:return _blocked("INVALID_SHAPE")
    intent=message.get("intent")
    if intent not in ROUTES:return _blocked("UNKNOWN_DESTINATION")
    if message["authority"]!=message["required_authority"]:return _blocked("AUTHORITY_MISMATCH")
    if message["policy"]!=message["required_policy"]:return _blocked("POLICY_MISMATCH")
    if message["consumed"]:return _blocked("DUPLICATE_MESSAGE")
    if not isinstance(now_epoch,int) or not isinstance(message["issued_epoch"],int) or not isinstance(message["expires_epoch"],int):return _blocked("UNKNOWN_CLOCK")
    if now_epoch<message["issued_epoch"] or now_epoch>=message["expires_epoch"]:return _blocked("STALE_MESSAGE")
    expected=f"{intent}:{ROUTES[intent]}"
    if message["route_binding"]!=expected:return _blocked("CONFUSED_DEPUTY_OR_ROUTE_MISMATCH")
    return {"status":"ROUTED_NOT_EXECUTED","destination":ROUTES[intent],"message_id":message["message_id"],"execution_performed":False}

def _blocked(reason:str)->dict[str,Any]:return {"status":"BLOCKED","reason":reason,"execution_performed":False}
