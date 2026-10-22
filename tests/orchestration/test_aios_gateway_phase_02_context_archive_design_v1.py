import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESIGN_PATH = ROOT / "docs/orchestration/AIOS_FULL_CONVERSATION_CONTEXT_ARCHIVE_DESIGN_V1.md"
SCHEMA_PATH = ROOT / "schemas/orchestration/aios_conversation_context_archive_v1.schema.json"
MANIFEST_PATH = ROOT / "automation/orchestration/AIOS_OWNER_AUTHORITY_PHASES_V1.json"
BROKER_PATH = ROOT / "automation/orchestration/aios_approval_broker_v1.py"
PHASE_1_PATH = ROOT / "docs/orchestration/AIOS_OWNER_CELLULAR_VOICE_GATEWAY_PROGRAM_CHARTER_V1.md"
CANONICAL_PHASE_NAME = "Full Conversation Context Archive Design"
EXPECTED_MANIFEST_SHA256 = "663ee52e69fdeafbd9831edd14eba2e48b8384408d4f5c6d67ac245a2bfd1561"
EXPECTED_BROKER_SHA256 = "56c05e0b23e2dfb62e03a504ee377f52851e3ef5d8f266c4f921caa435ad6282"
EXPECTED_PHASE_1_SHA256 = "a52b65a061a9ad38dadb6397be798c7458148fa2bd58a95f56f03f7c679849e3"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(path: Path) -> str:
    return " ".join(_text(path).lower().split())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_phase_2_identity_bundle_and_owner_gate_are_exact():
    manifest = json.loads(_text(MANIFEST_PATH))
    phase = manifest["phases"][1]
    assert phase["phase_id"] == 2
    assert phase["name"] == CANONICAL_PHASE_NAME
    assert phase["owner_bundle"] == "OWNER-BUNDLE-1-POLICY"
    text = _normalized(DESIGN_PATH)
    assert "phase 2, **full conversation context archive design**" in text
    assert "protected transition is **blocked**" in text
    assert "design/preparation may complete autonomously" in text


def test_schema_has_complete_deterministic_record_contract():
    schema = json.loads(_text(SCHEMA_PATH))
    required = {
        "archive_version", "conversation_id", "session_id", "message_id", "sequence",
        "role", "timestamp", "source", "content", "content_classification",
        "authority_classification", "sensitivity_classification",
        "retention_classification", "provenance", "integrity_reference",
        "sanitization_state",
    }
    assert set(schema["required"]) == required
    assert schema["additionalProperties"] is False
    assert schema["properties"]["sequence"] == {"type": "integer", "minimum": 1}
    text = _normalized(DESIGN_PATH)
    assert "(conversation_id, session_id, sequence, message_id)" in text
    assert "canonical serialization uses utf-8 json" in text


def test_duplicates_gaps_and_identifier_conflicts_fail_closed():
    text = _normalized(DESIGN_PATH)
    assert "idempotently ignored" in text
    assert "reuse of a message id with different content" in text
    assert "reuse of a sequence by different message ids" in text
    assert "gap quarantines" in text
    assert "identifier conflict" in text


def test_archive_never_grants_approval_or_execution_authority():
    text = _normalized(DESIGN_PATH)
    assert "no archive record grants approval authority" in text
    assert "approval broker remains non-authoritative" in text
    assert "archived commands" in text and "historical context only" in text
    assert "stale or replayed approvals" in text and "fail closed" in text
    assert "integrity verification" in text and "does not authenticate the owner" in text


def test_privacy_retention_sanitization_and_fail_closed_classes_exist():
    schema = json.loads(_text(SCHEMA_PATH))["properties"]
    assert {"public", "internal", "private", "restricted", "unknown"} == set(
        schema["sensitivity_classification"]["enum"]
    )
    assert {
        "ephemeral", "short_term_operational", "long_term_governance",
        "prohibited_from_archive", "unknown",
    } == set(schema["retention_classification"]["enum"])
    assert {"raw_prohibited", "pending", "sanitized", "redacted", "quarantined"} == set(
        schema["sanitization_state"]["enum"]
    )
    text = _normalized(DESIGN_PATH)
    for term in ("minimization", "access boundary", "export boundary", "deletion/expiry"):
        assert term in text
    assert "undefined or `unknown` authority, sensitivity, provenance, sequence, retention, or integrity" in text


def test_no_secrets_real_data_storage_or_runtime_capability_is_introduced():
    text = _normalized(DESIGN_PATH)
    for term in ("secrets", "passwords", "tokens", "private keys", "credential values"):
        assert term in text
    assert "this phase supplies no real conversation content" in text
    assert "no live persistence, runtime activation, ingestion process, external storage" in text
    assert "does not implement phase 17 location storage" in text
    assert "does not fetch urls, ingest arbitrary binaries" in text


def test_handoff_and_acceptance_matrix_are_complete():
    text = _text(DESIGN_PATH)
    assert "## Phase 2 handoff" in text
    assert "## Acceptance matrix" in text
    assert "| Requirement | Evidence | Pass condition | Downstream consumer |" in text
    assert "Phase 3 and later phases may rely only on" in text


def test_canonical_phase_1_manifest_and_approval_broker_are_unchanged():
    assert _sha256(MANIFEST_PATH) == EXPECTED_MANIFEST_SHA256
    assert _sha256(BROKER_PATH) == EXPECTED_BROKER_SHA256
    assert _sha256(PHASE_1_PATH) == EXPECTED_PHASE_1_SHA256
