import ast
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "docs/orchestration/AIOS_TRUSTED_COMMAND_TERMINAL_MODEL_V1.md"
SCHEMA_PATH = ROOT / "schemas/orchestration/aios_trusted_command_terminal_model_v1.schema.json"
PHASE_1_PATH = ROOT / "docs/orchestration/AIOS_OWNER_CELLULAR_VOICE_GATEWAY_PROGRAM_CHARTER_V1.md"
PHASE_2_PATH = ROOT / "docs/orchestration/AIOS_FULL_CONVERSATION_CONTEXT_ARCHIVE_DESIGN_V1.md"
PHASE_3_PATH = ROOT / "docs/orchestration/AIOS_GATEWAY_THREAT_MODEL_V1.md"
PHASE_4_PATH = ROOT / "docs/orchestration/AIOS_PHONE_NUMBER_ROUTING_MODEL_V1.md"
MANIFEST_PATH = ROOT / "automation/orchestration/AIOS_OWNER_AUTHORITY_PHASES_V1.json"
BROKER_PATH = ROOT / "automation/orchestration/aios_approval_broker_v1.py"
EXPECTED_SHA256 = {
    PHASE_1_PATH: "a52b65a061a9ad38dadb6397be798c7458148fa2bd58a95f56f03f7c679849e3",
    PHASE_2_PATH: "5be5d00c6f83d6e6ae15b32ad1fa78fb1214397fb54bb0c1206f3bca792090cb",
    PHASE_3_PATH: "c9949abb91dfa8b35f0a488efcbcfd5e6364796e73ce2a0b561765886f817a49",
    PHASE_4_PATH: "33a686133011ce412e0b1384c2fe366a6971c6762e437f701d6471faa7f436c2",
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
    assert schema["x-aios-phase"] == 5
    assert schema["x-aios-phase-name"] == "Z Fold 6 Trusted Command Terminal Model"
    assert schema["x-aios-owner-authority"] == "DEVICE"
    assert schema["x-aios-owner-bundle"] == "OWNER-BUNDLE-2-DEVICE-IDENTITY"
    assert schema["x-aios-preparation-mode"] == "PREPARE_BEHIND_GATE"
    assert schema["x-aios-protected-transition"] == "BLOCKED"
    value = normalized(MODEL_PATH)
    assert "design/preparation may complete autonomously behind the gate" in value
    assert "operational trust activation remains **blocked**" in value


def test_device_record_contract_is_exact_and_closed():
    schema = json.loads(text(SCHEMA_PATH))
    required = {
        "device_record_version", "device_reference_id", "device_class", "device_state",
        "ownership_state", "enrollment_state", "attestation_state", "integrity_state",
        "os_security_state", "screen_lock_state", "biometric_policy_state",
        "passkey_readiness_state", "revocation_state", "recovery_state",
        "authority_state", "privacy_classification", "provenance", "integrity_reference",
    }
    assert set(schema["required"]) == required
    assert schema["additionalProperties"] is False
    assert schema["properties"]["authority_state"] == {"const": "BLOCKED"}
    assert "opaque" in normalized(MODEL_PATH)


def test_prohibited_identifiers_credentials_and_private_material_are_explicit():
    value = normalized(MODEL_PATH)
    for phrase in (
        "imei", "serial number", "android id", "advertising id", "sim/esim id",
        "mac address", "real phone number", "device certificate or private key",
        "passkey credential material", "yubikey secrets", "biometric templates",
        "tokens", "passwords", "secrets", "opaque references only",
    ):
        assert phrase in value
    combined = text(MODEL_PATH) + text(SCHEMA_PATH) + text(Path(__file__))
    assert not re.search(r"(?<![A-Za-z0-9])\+\d{8,15}(?!\d)", combined)


def test_device_signals_never_grant_owner_authority():
    value = normalized(MODEL_PATH)
    for phrase in (
        "device possession alone is insufficient and grants no authority",
        "an unlocked device alone is insufficient", "screen-lock success is insufficient",
        "a biometric match alone is insufficient", "an operating-system claim alone is insufficient",
        "attestation alone is evidence, not approval, and grants no authority",
        "human owner authority remains mandatory", "receiving boundary revalidates current authority",
    ):
        assert phrase in value


def test_every_phase_5_owned_threat_is_bound_exactly():
    schema = json.loads(text(SCHEMA_PATH))
    required = {"GW-T023"}
    assert set(schema["x-aios-phase-3-threat-bindings"]) == required
    phase_3_rows = [line for line in text(PHASE_3_PATH).splitlines() if line.startswith("| GW-T")]
    owned = {
        line.split("|")[1].strip()
        for line in phase_3_rows
        if "Phase 5" in line.split("|")[12]
    }
    assert owned == required
    assert all(f"`{threat_id}`" in text(MODEL_PATH) for threat_id in required)


def test_device_states_are_fail_closed_and_never_active():
    states = json.loads(text(SCHEMA_PATH))["properties"]["device_state"]["enum"]
    assert states == [
        "UNREGISTERED", "DESIGN_ONLY", "PENDING_OWNER_AUTHORITY", "PENDING_ENROLLMENT",
        "PENDING_ATTESTATION", "VERIFIED_NOT_ACTIVE", "BLOCKED", "REVOKED", "LOST",
        "COMPROMISED",
    ]
    assert "ACTIVE" not in states
    assert "TRUSTED_FOR_EXECUTION" not in states
    assert "every state is non-operational and fail closed" in normalized(MODEL_PATH)


def test_enrollment_revocation_recovery_and_handoffs_are_bounded():
    value = normalized(MODEL_PATH)
    for phrase in (
        "current owner approval", "exact opaque device reference", "exact enrollment action",
        "an expiry", "replay protection", "receiving-boundary verification",
        "independent recovery path", "lost device", "stolen device", "compromise suspicion",
        "os integrity failure", "attestation failure", "lock-screen policy failure",
        "owner revocation", "affected device cannot approve its own recovery",
        "phase 6 may consume", "phase 9 may consume",
    ):
        assert phrase in value


def test_no_device_os_network_or_runtime_capability_exists():
    value = normalized(MODEL_PATH)
    assert "does not modify operating-system settings, invoke adb, enroll with mdm" in value
    assert "provider or network client" in value
    assert "deploy software, or add runtime or remote-control capability" in value
    assert "no biometric capture, template, sample, or derived identity material" in value
    assert "actual passkey or yubikey authority and enrollment belong to phase 9" in value
    tree = ast.parse(text(Path(__file__)))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported == {"ast", "hashlib", "json", "re", "Path"}


def test_acceptance_matrix_privacy_and_owner_gate_are_complete():
    value = text(MODEL_PATH)
    assert "| Requirement | Evidence | Pass condition | Downstream consumer |" in value
    assert "## Privacy model" in value
    assert "## Phase 5 handoff" in value
    assert "## Owner gate" in value


def test_prior_phases_manifest_and_approval_broker_are_unchanged():
    assert {path: digest(path) for path in EXPECTED_SHA256} == EXPECTED_SHA256
