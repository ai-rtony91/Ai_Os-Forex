"""Phase 15 paper-only route preview; no broker adapter exists here."""
from __future__ import annotations
from typing import Any, Mapping
ALLOWED_MODES={"DRY_RUN","MOCK","PAPER"}

def preview_lab_route(request:Mapping[str,Any],*,now_epoch:int)->dict[str,Any]:
    required={"mode","route","expected_route","authority","required_authority","approval_expires_epoch","route_digest","expected_route_digest"}
    if set(request)!=required:return _blocked("INVALID_SHAPE")
    if request["mode"] not in ALLOWED_MODES:return _blocked("LIVE_OR_UNKNOWN_MODE")
    if request["route"]!="THE_LAB_PREVIEW" or request["route"]!=request["expected_route"] or request["route_digest"]!=request["expected_route_digest"]:return _blocked("ROUTE_TAMPERING")
    if request["authority"]!=request["required_authority"]:return _blocked("EXECUTION_AUTHORITY_MISMATCH")
    if not isinstance(request["approval_expires_epoch"],int) or now_epoch>=request["approval_expires_epoch"]:return _blocked("STALE_APPROVAL")
    return {"status":"PREVIEW_ONLY","mode":request["mode"],"broker_call":False,"order_submitted":False,"money_moved":False,"risk_policy_preserved":True}

def _blocked(reason:str)->dict[str,Any]:return {"status":"BLOCKED","reason":reason,"broker_call":False,"order_submitted":False,"money_moved":False}
