import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DOC=ROOT/"docs/orchestration/AIOS_ANTI_REPLAY_AND_TIME_BOUND_LIVENESS_MODEL_V1.md"
SCHEMA=ROOT/"schemas/orchestration/aios_anti_replay_and_time_bound_liveness_model_v1.schema.json"

def test_phase_8_identity_and_closed_schema():
    s=json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert s["x-aios-phase"]==8
    assert s["x-aios-owner-bundle"]=="OWNER-BUNDLE-1-POLICY"
    assert s["x-aios-protected-transition"]=="BLOCKED"
    assert s["additionalProperties"] is False
    assert s["properties"]["authority_state"]=={"const":"BLOCKED"}
    assert s["x-aios-operational-capability"] is False

def test_phase_8_requirements_and_fail_closed_boundary():
    value=" ".join(DOC.read_text(encoding="utf-8").lower().split())
    for phrase in ['nonce model', 'expiry', 'replay rejection', 'delayed replay rejection', 'consume-once behavior', 'duplicate receipt rejection', 'clock-skew handling', 'race and toctou handling', 'unknown clock fails closed']:
        assert phrase in value
    for phrase in ("unknown, missing, stale, conflicting, replayed, revoked, or unverifiable input resolves to `blocked`", "does not grant or consume", "no operational capability exists"):
        assert phrase in value

def test_phase_8_schema_has_exact_safe_record_shape():
    s=json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert set(s["required"])=={"record_version","record_id","phase","state","authority_state","issued_at","expires_at","action_binding","subject_reference","provenance","integrity_reference"}
    assert "ACTIVE" not in s["properties"]["state"]["enum"]
