import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "docs/orchestration/AIOS_LOCATION_VAULT_AND_PRIVACY_BROKER_V1.md"
SCHEMA_PATH = ROOT / "schemas/orchestration/aios_location_vault_and_privacy_broker_v1.schema.json"
THREAT_PATH = ROOT / "docs/orchestration/AIOS_GATEWAY_THREAT_MODEL_V1.md"
MANIFEST_PATH = ROOT / "automation/orchestration/AIOS_OWNER_AUTHORITY_PHASES_V1.json"
BROKER_PATH = ROOT / "automation/orchestration/aios_approval_broker_v1.py"
EXPECTED_AUTHORITY_SHA256 = {
    MANIFEST_PATH: "663ee52e69fdeafbd9831edd14eba2e48b8384408d4f5c6d67ac245a2bfd1561",
    BROKER_PATH: "56c05e0b23e2dfb62e03a504ee377f52851e3ef5d8f266c4f921caa435ad6282",
}


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized(path: Path) -> str:
    return " ".join(text(path).lower().split())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema() -> dict:
    return json.loads(text(SCHEMA_PATH))


def test_phase_17_identity_and_owner_gate_are_exact():
    contract = schema()
    assert contract["x-aios-phase"] == 17
    assert contract["x-aios-phase-name"] == "Location Vault and Privacy Broker"
    assert contract["x-aios-owner-authority"] == "PRIVACY_CONSENT"
    assert contract["x-aios-owner-bundle"] == "OWNER-BUNDLE-4-LOCATION-PRIVACY"
    assert contract["x-aios-preparation-mode"] == "PREPARE_BEHIND_GATE"
    assert contract["x-aios-protected-transition"] == "BLOCKED"
    assert contract["x-aios-location-collection-capability"] is False
    assert contract["x-aios-network-capability"] is False


def test_closed_contract_permits_only_minimized_bounded_records():
    contract = schema()
    assert contract["additionalProperties"] is False
    assert set(contract["required"]) == {
        "record_version",
        "record_id",
        "purpose_binding",
        "consent",
        "location_evidence",
        "retention",
        "authority_state",
        "protected_transition",
    }
    assert contract["properties"]["authority_state"] == {"const": "BLOCKED"}
    assert contract["properties"]["protected_transition"] == {"const": "BLOCKED"}
    for definition in ("consentRecord", "locationEvidence", "retentionRecord"):
        assert contract["$defs"][definition]["additionalProperties"] is False
    evidence_properties = contract["$defs"]["locationEvidence"]["properties"]
    assert set(evidence_properties) == {
        "evidence_reference",
        "granularity_class",
        "privacy_classification",
        "sanitization_state",
        "integrity_reference",
    }


def test_no_precise_location_or_reconstructable_data_is_allowed():
    value = normalized(MODEL_PATH)
    for phrase in (
        "stores no actual coordinates",
        "collects no precise location",
        "opaque, purpose-bound references",
        "must not encode or permit reconstruction of a real place",
        "hashing raw location is not sufficient minimization",
        "no cross-purpose reuse",
        "must not be joinable",
    ):
        assert phrase in value
    forbidden_schema_fields = {
        "latitude",
        "longitude",
        "altitude",
        "address",
        "postal_code",
        "geofence",
        "place_name",
        "location_history",
        "provider_payload",
    }
    contract_fields = set(re.findall(r'"([a-z][a-z0-9_]*)"\s*:', text(SCHEMA_PATH)))
    assert forbidden_schema_fields.isdisjoint(contract_fields)
    combined = text(MODEL_PATH) + text(SCHEMA_PATH) + text(Path(__file__))
    assert not re.search(r"(?<!\d)[+-]?\d{1,2}\.\d{4,}\s*,\s*[+-]?\d{1,3}\.\d{4,}(?!\d)", combined)


def test_current_exact_purpose_consent_is_mandatory_and_fail_closed():
    value = normalized(MODEL_PATH)
    for phrase in (
        "consent is external human owner authority",
        "current-consent reference",
        "scope and purpose exactly match",
        "issue and expiry times are valid",
        "consent has not been revoked",
        "missing, stale, expired, revoked, mismatched, replayed, unverifiable, or unknown consent fails closed",
        "historic consent and historic location can never become current authority",
        "consent for one purpose cannot be reused for another purpose",
        "current owner authority is independently revalidated",
    ):
        assert phrase in value
    states = schema()["$defs"]["consentRecord"]["properties"]["consent_state"]["enum"]
    assert "CURRENT_EXTERNAL_CONSENT_EVIDENCE" in states
    assert {"MISSING", "EXPIRED", "REVOKED", "MISMATCHED", "UNKNOWN", "BLOCKED"}.issubset(states)
    assert "GRANTED" not in states


def test_location_evidence_never_grants_owner_authority():
    value = normalized(MODEL_PATH)
    for phrase in (
        "location evidence is contextual evidence only",
        "cannot independently identify the owner",
        "grant execution authority",
        "integrity evidence detects mutation but does not prove consent",
        "rather than trusting an upstream `pass` value",
        "phase 17 completion grants no downstream authority",
    ):
        assert phrase in value


def test_retention_deletion_quarantine_and_revocation_are_explicit():
    value = normalized(MODEL_PATH)
    for phrase in (
        "retention is purpose-limited and time-bounded",
        "consent revocation",
        "retention expiry",
        "deletion evidence is an opaque sanitized reference",
        "unknown retention or deletion state is quarantined",
        "exports are denied by default",
    ):
        assert phrase in value
    retention = schema()["$defs"]["retentionRecord"]
    assert set(retention["properties"]["deletion_state"]["enum"]) == {
        "NOT_DUE", "DELETION_REQUIRED", "DELETED", "QUARANTINED", "UNKNOWN"
    }


def test_every_phase_17_owned_threat_is_bound_exactly():
    required = {"GW-T026", "GW-T027", "GW-T028", "GW-T029", "GW-T038"}
    assert set(schema()["x-aios-phase-3-threat-bindings"]) == required
    rows = [line for line in text(THREAT_PATH).splitlines() if line.startswith("| GW-T")]
    owned = {
        line.split("|")[1].strip()
        for line in rows
        if "Phase 17" in line.split("|")[12]
    }
    assert owned == required
    assert all(f"`{threat_id}`" in text(MODEL_PATH) for threat_id in required)


def test_no_location_permission_provider_network_vault_or_runtime_capability():
    value = normalized(MODEL_PATH)
    for phrase in (
        "adds no gps or sensor access",
        "android or grapheneos permission mutation",
        "geofencing",
        "background collection",
        "provider/location api",
        "network client",
        "external vault access",
        "credential access",
        "daemon",
        "scheduler",
        "deployment",
        "runtime activation",
        "no trading, broker, order, or money-moving capability",
        "there is no local runtime component",
    ):
        assert phrase in value


def test_acceptance_matrix_handoff_and_owner_gate_are_complete():
    value = text(MODEL_PATH)
    assert "| Requirement | Evidence | Pass condition | Consumer |" in value
    assert "## Upstream dependencies and downstream handoff" in value
    assert "## Owner gate" in value
    assert "does not grant or consume that\nbundle" in value


def test_manifest_and_approval_broker_remain_unchanged_and_non_authoritative():
    assert {path: digest(path) for path in EXPECTED_AUTHORITY_SHA256} == EXPECTED_AUTHORITY_SHA256
    manifest = json.loads(text(MANIFEST_PATH))
    phase = next(item for item in manifest["phases"] if item["phase_id"] == 17)
    assert phase["owner_authority"] == "PRIVACY_CONSENT"
    assert phase["owner_bundle"] == "OWNER-BUNDLE-4-LOCATION-PRIVACY"
    assert "never creates decisions" in normalized(BROKER_PATH)
