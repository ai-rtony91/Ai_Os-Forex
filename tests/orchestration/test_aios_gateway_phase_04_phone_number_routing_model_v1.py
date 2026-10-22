import ast
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "docs/orchestration/AIOS_PHONE_NUMBER_ROUTING_MODEL_V1.md"
SCHEMA_PATH = ROOT / "schemas/orchestration/aios_phone_number_routing_model_v1.schema.json"
PHASE_1_PATH = ROOT / "docs/orchestration/AIOS_OWNER_CELLULAR_VOICE_GATEWAY_PROGRAM_CHARTER_V1.md"
PHASE_2_PATH = ROOT / "docs/orchestration/AIOS_FULL_CONVERSATION_CONTEXT_ARCHIVE_DESIGN_V1.md"
PHASE_3_PATH = ROOT / "docs/orchestration/AIOS_GATEWAY_THREAT_MODEL_V1.md"
MANIFEST_PATH = ROOT / "automation/orchestration/AIOS_OWNER_AUTHORITY_PHASES_V1.json"
BROKER_PATH = ROOT / "automation/orchestration/aios_approval_broker_v1.py"
EXPECTED_SHA256 = {
    PHASE_1_PATH: "a52b65a061a9ad38dadb6397be798c7458148fa2bd58a95f56f03f7c679849e3",
    PHASE_2_PATH: "5be5d00c6f83d6e6ae15b32ad1fa78fb1214397fb54bb0c1206f3bca792090cb",
    PHASE_3_PATH: "c9949abb91dfa8b35f0a488efcbcfd5e6364796e73ce2a0b561765886f817a49",
    MANIFEST_PATH: "663ee52e69fdeafbd9831edd14eba2e48b8384408d4f5c6d67ac245a2bfd1561",
    BROKER_PATH: "56c05e0b23e2dfb62e03a504ee377f52851e3ef5d8f266c4f921caa435ad6282",
}


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalized(path: Path) -> str:
    return " ".join(text(path).lower().split())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_phase_identity_and_owner_gate():
    schema = json.loads(text(SCHEMA_PATH))
    assert schema["x-aios-phase"] == 4
    assert schema["x-aios-phase-name"] == "Phone Number Routing Model"
    assert schema["x-aios-owner-authority"] == "PHONE_NUMBER"
    assert schema["x-aios-owner-bundle"] == "OWNER-BUNDLE-2-DEVICE-IDENTITY"
    assert schema["x-aios-preparation-mode"] == "PREPARE_BEHIND_GATE"
    assert schema["x-aios-protected-transition"] == "BLOCKED"
    value = normalized(MODEL_PATH)
    assert "design/preparation may complete autonomously behind the gate" in value
    assert "operationalizes a real phone/provider route remains **blocked**" in value


def test_routing_record_contract_is_exact_and_closed():
    schema = json.loads(text(SCHEMA_PATH))
    required = {
        "route_version", "route_id", "route_state", "provider_class",
        "number_reference_id", "number_classification", "inbound_policy",
        "outbound_policy", "source_binding_policy", "forwarding_policy",
        "failover_policy", "recovery_policy", "change_control_state",
        "verification_state", "authority_state", "privacy_classification",
        "provenance", "integrity_reference",
    }
    assert set(schema["required"]) == required
    assert schema["additionalProperties"] is False
    assert schema["properties"]["authority_state"] == {"const": "BLOCKED"}


def test_real_numbers_credentials_and_secrets_are_prohibited():
    combined = text(MODEL_PATH) + text(SCHEMA_PATH) + text(Path(__file__))
    assert not re.search(r"(?<![A-Za-z0-9])\+\d{8,15}(?!\d)", combined)
    value = normalized(MODEL_PATH)
    for phrase in (
        "no real phone number may appear", "carrier account id", "sim/esim identifier",
        "provider credential", "token", "password", "secret", "opaque references",
    ):
        assert phrase in value


def test_source_and_transport_metadata_are_explicitly_untrusted():
    value = normalized(MODEL_PATH)
    for phrase in (
        "caller id is untrusted", "ani/cli metadata is untrusted",
        "carrier metadata is untrusted", "provider transport is untrusted",
        "does not equal owner authority", "successful routing does not authorize",
        "identity and device factors remain mandatory",
    ):
        assert phrase in value


def test_every_phase_4_owned_threat_is_bound():
    value = text(MODEL_PATH)
    required = {"GW-T001", "GW-T002", "GW-T003", "GW-T004", "GW-T031", "GW-T039"}
    assert all(f"`{threat_id}`" in value for threat_id in required)
    phase_3_rows = [line for line in text(PHASE_3_PATH).splitlines() if line.startswith("| GW-T")]
    owned = {
        line.split("|")[1].strip()
        for line in phase_3_rows
        if "Phase 4" in line.split("|")[12]
    }
    assert owned == required


def test_route_states_are_fail_closed_and_never_active():
    states = json.loads(text(SCHEMA_PATH))["properties"]["route_state"]["enum"]
    assert states == [
        "UNCONFIGURED", "DESIGN_ONLY", "PENDING_OWNER_AUTHORITY",
        "PENDING_PROVIDER_VERIFICATION", "VERIFIED_NOT_ACTIVE", "BLOCKED", "REVOKED",
    ]
    assert "ACTIVE" not in states
    assert "every state is non-operational" in normalized(MODEL_PATH)


def test_change_takeover_failover_privacy_and_handoff_are_bounded():
    value = normalized(MODEL_PATH)
    for phrase in (
        "exact route identity", "current trusted human owner approval", "exact action binding",
        "expiry", "replay protection", "consume-once semantics", "receiving-boundary revalidation",
        "carrier ownership change", "port event", "sim/esim change", "number takeover",
        "provider-account anomaly", "route mismatch", "independent trusted owner path",
        "must never weaken identity, freshness, authority, integrity", "collect only opaque route identity",
        "redact transport metadata", "phase 4 completion does not authorize device enrollment",
    ):
        assert phrase in value


def test_no_provider_network_or_runtime_capability_exists():
    value = normalized(MODEL_PATH)
    assert "no vendor configuration, provider sdk, network client, account access, endpoint, or credential" in value
    assert "activates no telephony capability" in value
    source = text(Path(__file__))
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported == {"ast", "hashlib", "json", "re", "Path"}


def test_acceptance_matrix_and_phase_handoff_are_complete():
    value = text(MODEL_PATH)
    assert "| Requirement | Evidence | Pass condition | Downstream consumer |" in value
    assert "## Phase 4 handoff" in value
    assert "## Owner gate" in value


def test_prior_phases_manifest_and_approval_broker_are_unchanged():
    assert {path: digest(path) for path in EXPECTED_SHA256} == EXPECTED_SHA256
