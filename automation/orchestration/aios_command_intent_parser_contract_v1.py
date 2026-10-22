"""Phase 12 deterministic intent parser. Normalizes; never executes."""
from __future__ import annotations
import re
from typing import Any, Mapping

SUPPORTED={"inspect":"INSPECT","status":"STATUS","prepare":"PREPARE","validate":"VALIDATE"}
_FORBIDDEN=re.compile(r"(?:[;&|`]|\$\(|<script|ignore\s+(?:all\s+)?(?:prior|previous)|system\s*prompt)",re.I)

def parse_intent(request: Mapping[str,Any])->dict[str,Any]:
    required={"transcript","transcript_digest","provenance","risk_metadata","action_binding"}
    if set(request)!=required: return _blocked("INVALID_SHAPE")
    transcript=request.get("transcript")
    if not isinstance(transcript,str) or not transcript.strip(): return _blocked("EMPTY_TRANSCRIPT")
    normalized=" ".join(transcript.casefold().split())
    if _FORBIDDEN.search(normalized): return _blocked("INJECTION_OR_SUBSTITUTION")
    matches=[(prefix,action) for prefix,action in SUPPORTED.items() if normalized==prefix or normalized.startswith(prefix+" ")]
    if len(matches)!=1: return _blocked("AMBIGUOUS_OR_UNSUPPORTED")
    if any(not isinstance(request[k],(str,dict)) or not request[k] for k in required-{"transcript"}): return _blocked("MISSING_METADATA")
    prefix,action=matches[0]
    return {"status":"PARSED_NOT_EXECUTED","intent":action,"arguments":normalized[len(prefix):].strip(),"transcript_digest":request["transcript_digest"],"provenance":request["provenance"],"risk_metadata":request["risk_metadata"],"action_binding":request["action_binding"],"execution_performed":False}

def _blocked(reason:str)->dict[str,Any]: return {"status":"BLOCKED","reason":reason,"execution_performed":False}
