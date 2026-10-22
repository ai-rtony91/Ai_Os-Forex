import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DOC=ROOT/"docs/orchestration/AIOS_YUBIKEY_AND_PASSKEY_AUTHORITY_MODEL_V1.md"
SCHEMA=ROOT/"schemas/orchestration/aios_yubikey_and_passkey_authority_model_v1.schema.json"

def test_phase_9_identity_and_closed_schema():
    s=json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert s["x-aios-phase"]==9
    assert s["x-aios-owner-bundle"]=="OWNER-BUNDLE-2-DEVICE-IDENTITY"
    assert s["x-aios-protected-transition"]=="BLOCKED"
    assert s["additionalProperties"] is False
    assert s["properties"]["authority_state"]=={"const":"BLOCKED"}
    assert s["x-aios-operational-capability"] is False

def test_phase_9_requirements_and_fail_closed_boundary():
    value=" ".join(DOC.read_text(encoding="utf-8").lower().split())
    for phrase in ['opaque factor references', 'no private keys', 'no secrets', 'no physical enrollment', 'stale or revoked factor rejection', 'cross-device binding', 'factor authority remains blocked']:
        assert phrase in value
    for phrase in ("unknown, missing, stale, conflicting, replayed, revoked, or unverifiable input resolves to `blocked`", "does not grant or consume", "no operational capability exists"):
        assert phrase in value

def test_phase_9_schema_has_exact_safe_record_shape():
    s=json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert set(s["required"])=={"record_version","record_id","phase","state","authority_state","issued_at","expires_at","action_binding","subject_reference","provenance","integrity_reference"}
    assert "ACTIVE" not in s["properties"]["state"]["enum"]
