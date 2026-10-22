import json
from pathlib import Path
from automation.orchestration.aios_command_intent_parser_contract_v1 import parse_intent
ROOT=Path(__file__).resolve().parents[2]
def req(t="validate gateway"):
 return {"transcript":t,"transcript_digest":"digest_123","provenance":{"source":"voice"},"risk_metadata":{"level":"LOW"},"action_binding":"action_123"}
def test_normalizes_preserves_metadata_and_never_executes():
 r=parse_intent(req("  VaLiDaTe   gateway ")); assert r["intent"]=="VALIDATE" and r["arguments"]=="gateway" and not r["execution_performed"] and r["risk_metadata"]=={"level":"LOW"}
def test_ambiguity_injection_substitution_and_unsupported_block():
 for value in ("","delete all","validate x;rm -rf x","ignore previous validate x","system prompt validate"):
  assert parse_intent(req(value))["status"]=="BLOCKED"
def test_closed_schema():
 s=json.loads((ROOT/"schemas/orchestration/aios_command_intent_parser_contract_v1.schema.json").read_text()); assert s["additionalProperties"] is False and s["x-aios-execution-capability"] is False
