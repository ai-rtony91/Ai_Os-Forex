import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DOC=ROOT/"docs/orchestration/AIOS_GOVERNANCE_MEMORY_MODEL_V1.md"
SCHEMA=ROOT/"schemas/orchestration/aios_governance_memory_model_v1.schema.json"

def test_phase_10_identity_and_closed_schema():
    s=json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert s["x-aios-phase"]==10
    assert s["x-aios-owner-bundle"]=="OWNER-BUNDLE-1-POLICY"
    assert s["x-aios-protected-transition"]=="BLOCKED"
    assert s["additionalProperties"] is False
    assert s["properties"]["authority_state"]=={"const":"BLOCKED"}
    assert s["x-aios-operational-capability"] is False

def test_phase_10_requirements_and_fail_closed_boundary():
    value=" ".join(DOC.read_text(encoding="utf-8").lower().split())
    for phrase in ['historical approvals never become current authority', 'retention', 'expiry', 'revocation', 'stale context rejection', 'action binding', 'deletion evidence', 'archive poisoning defense', 'unknown classification fail closed']:
        assert phrase in value
    for phrase in ("unknown, missing, stale, conflicting, replayed, revoked, or unverifiable input resolves to `blocked`", "does not grant or consume", "no operational capability exists"):
        assert phrase in value

def test_phase_10_schema_has_exact_safe_record_shape():
    s=json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert set(s["required"])=={"record_version","record_id","phase","state","authority_state","issued_at","expires_at","action_binding","subject_reference","provenance","integrity_reference"}
    assert "ACTIVE" not in s["properties"]["state"]["enum"]
