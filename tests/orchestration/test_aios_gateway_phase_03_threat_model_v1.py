import ast
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "docs/orchestration/AIOS_GATEWAY_THREAT_MODEL_V1.md"
MANIFEST_PATH = ROOT / "automation/orchestration/AIOS_OWNER_AUTHORITY_PHASES_V1.json"
PHASE_1_PATH = ROOT / "docs/orchestration/AIOS_OWNER_CELLULAR_VOICE_GATEWAY_PROGRAM_CHARTER_V1.md"
PHASE_2_PATH = ROOT / "docs/orchestration/AIOS_FULL_CONVERSATION_CONTEXT_ARCHIVE_DESIGN_V1.md"
SCHEMA_PATH = ROOT / "schemas/orchestration/aios_conversation_context_archive_v1.schema.json"
BROKER_PATH = ROOT / "automation/orchestration/aios_approval_broker_v1.py"
EXPECTED_MANIFEST_SHA256 = "663ee52e69fdeafbd9831edd14eba2e48b8384408d4f5c6d67ac245a2bfd1561"
EXPECTED_PHASE_1_SHA256 = "a52b65a061a9ad38dadb6397be798c7458148fa2bd58a95f56f03f7c679849e3"
EXPECTED_PHASE_2_SHA256 = "5be5d00c6f83d6e6ae15b32ad1fa78fb1214397fb54bb0c1206f3bca792090cb"
EXPECTED_SCHEMA_SHA256 = "190f926ecfea1451e3c48e54b5bcfb00c09a2979d3a64eb4ecb87125de667ce8"
EXPECTED_BROKER_SHA256 = "56c05e0b23e2dfb62e03a504ee377f52851e3ef5d8f266c4f921caa435ad6282"


def text() -> str:
    return MODEL_PATH.read_text(encoding="utf-8")


def normalized() -> str:
    return " ".join(text().lower().split())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def threat_rows() -> list[list[str]]:
    rows = []
    for line in text().splitlines():
        if re.match(r"^\| GW-T\d{3} \|", line):
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def test_exact_phase_identity_manifest_authority_and_bundle():
    phase = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["phases"][2]
    assert phase == {
        "phase_id": 3,
        "name": "Gateway Threat Model",
        "owner_authority": "RISK_ACCEPTANCE",
        "owner_bundle": "OWNER-BUNDLE-1-POLICY",
        "owner_action": "Accept or reject the documented residual gateway risks after mitigations are presented.",
    }
    value = text()
    for marker in (
        "Phase 3 = Gateway Threat Model", "`RISK_ACCEPTANCE`",
        "`OWNER-BUNDLE-1-POLICY`", "`PREPARE_BEHIND_GATE`",
        "protected_transition | `BLOCKED`",
    ):
        assert marker in value


def test_authority_boundary_is_explicit_and_fail_closed():
    value = normalized()
    assert "human owner remains final authority" in value
    assert "approval broker remains non-authoritative" in value
    assert "validator pass is evidence only" in value
    assert "neither authorizes a protected transition nor constitutes owner risk acceptance" in value


def test_phase_1_phase_2_and_schema_are_referenced():
    value = text()
    assert "AIOS_OWNER_CELLULAR_VOICE_GATEWAY_PROGRAM_CHARTER_V1.md" in value
    assert "AIOS_FULL_CONVERSATION_CONTEXT_ARCHIVE_DESIGN_V1.md" in value
    assert "aios_conversation_context_archive_v1.schema.json" in value


def test_threat_ids_are_unique_and_register_has_required_fields():
    rows = threat_rows()
    ids = [row[0] for row in rows]
    assert len(ids) >= 24
    assert len(ids) == len(set(ids))
    assert ids == [f"GW-T{number:03d}" for number in range(1, len(ids) + 1)]
    assert all(len(row) == 16 for row in rows)
    assert all(row[11].startswith("Phase ") for row in rows)
    assert all(row[12] for row in rows)
    assert all("BLOCKED" in row[14] or "QUARANTINED" in row[14] for row in rows)
    assert all(row[13] == "UNASSESSED" for row in rows)


def test_all_required_threat_coverage_concepts_are_represented():
    value = normalized()
    concepts = (
        "caller/source spoofing", "sim swap or phone-number takeover",
        "carrier/provider account compromise", "carrier/provider infrastructure compromise",
        "voice cloning or deepfake impersonation", "recorded voice replay", "delayed replay",
        "liveness bypass", "transcript tampering", "speech-to-text command substitution",
        "prompt or instruction injection", "conversation archive poisoning",
        "historical approval replay", "stale-context promotion", "archive integrity tampering",
        "message ordering or sequence manipulation", "identity/session confusion",
        "confused-deputy behavior", "cross-phase authority escalation",
        "forged approval/verifier result", "approval broker misuse",
        "unsafe fallback or downgrade path", "trusted-device compromise",
        "passkey or yubikey possession compromise", "secret/session leakage",
        "privacy leakage", "location leakage", "logging or telemetry exfiltration",
        "unauthorized archive export", "attachment/reference abuse", "denial of service",
        "resource exhaustion", "race or toctou error", "runtime bridge compromise",
        "the_lab execution-boundary bypass", "fail-open error handling",
        "audit/repudiation ambiguity", "retention or deletion failure",
        "malicious or compromised external dependency",
    )
    assert all(concept in value for concept in concepts)


def test_risk_scoring_is_deterministic_ordinal_and_internally_consistent():
    value = normalized()
    assert "ordinal prioritization only" in value
    assert "risk_score = likelihood * impact" in value
    assert "deterministic prioritization, not a probability estimate, certification, or guarantee" in value
    bands = ((1, 3, "LOW"), (4, 7, "MEDIUM"), (8, 11, "HIGH"), (12, 16, "CRITICAL"))
    for row in threat_rows():
        likelihood, impact, score = map(int, row[6:9])
        assert likelihood in range(1, 5) and impact in range(1, 5)
        assert score == likelihood * impact
        assert any(low <= score <= high and row[9] == severity for low, high, severity in bands)


def test_archive_invariants_and_residual_risk_remain_fail_closed():
    value = normalized()
    for phrase in (
        "historical archive content is non-authoritative", "unknown critical classifications quarantine",
        "message order is sequence-based", "duplicate/conflict rules fail closed",
        "integrity verification detects alteration but does not authenticate owner",
        "sanitization and sensitivity classifications must be revalidated",
        "prohibited/private data may not be silently promoted", "archive availability cannot be assumed",
        "real conversation data cannot be assumed", "archive history cannot produce current owner approval",
    ):
        assert phrase in value
    assert "every threat remains `unassessed`" in value
    assert "accepted" not in {row[13].lower() for row in threat_rows()}


def test_phase_4_and_all_runtime_or_protected_capabilities_remain_inactive():
    value = normalized()
    assert "phase 4 remains non-activated and not authorized" in value
    assert "this document introduces none of those runtime surfaces" in value
    assert "implements no gateway or protected capability" in value
    assert "no real phone number, real conversation data, credential or secret value" in value
    assert "exact location data" in value
    for prohibition in ("configure telephony", "deploy", "connect a broker", "trade", "place orders", "move money"):
        assert prohibition in value


def test_test_module_introduces_no_network_or_process_execution():
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported == {"ast", "hashlib", "json", "re", "Path"}


def test_phase_1_phase_2_schema_broker_and_manifest_are_unchanged():
    assert digest(MANIFEST_PATH) == EXPECTED_MANIFEST_SHA256
    assert digest(PHASE_1_PATH) == EXPECTED_PHASE_1_SHA256
    assert digest(PHASE_2_PATH) == EXPECTED_PHASE_2_SHA256
    assert digest(SCHEMA_PATH) == EXPECTED_SCHEMA_SHA256
    assert digest(BROKER_PATH) == EXPECTED_BROKER_SHA256
