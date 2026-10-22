import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHARTER_PATH = ROOT / "docs/orchestration/AIOS_OWNER_CELLULAR_VOICE_GATEWAY_PROGRAM_CHARTER_V1.md"
MANIFEST_PATH = ROOT / "automation/orchestration/AIOS_OWNER_AUTHORITY_PHASES_V1.json"
CANONICAL_PHASE_NAME = "Owner Cellular Voice Gateway Program Charter"
AUTONOMOUS_PHASES = {1, 12, 13}
OWNER_GATED_PHASES = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15, 16, 17}
BUNDLES = {
    "OWNER-BUNDLE-1-POLICY": {2, 3, 6, 7, 8, 10, 11},
    "OWNER-BUNDLE-2-DEVICE-IDENTITY": {4, 5, 9},
    "OWNER-BUNDLE-3-RUNTIME-SECRETS": {14, 15, 16},
    "OWNER-BUNDLE-4-LOCATION-PRIVACY": {17},
}


def charter() -> str:
    return CHARTER_PATH.read_text(encoding="utf-8")


def normalized_charter() -> str:
    return " ".join(charter().lower().split())


def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_and_charter_preserve_exact_phase_1_identity_and_authority():
    phase = manifest()["phases"][0]
    assert phase == {
        "phase_id": 1,
        "name": CANONICAL_PHASE_NAME,
        "owner_authority": "NONE",
    }
    assert CANONICAL_PHASE_NAME in charter()
    assert "owner_authority = NONE" in charter()


def test_charter_lists_all_canonical_phases_once_and_in_order():
    text = charter().split("## Canonical 17-phase dependency map", 1)[1].split(
        "## Four owner bundles", 1
    )[0]
    listed = re.findall(r"(?m)^(\d+)\. (.+)$", text)
    dependency_rows = [(int(number), name) for number, name in listed if int(number) <= 17]
    expected = [(phase["phase_id"], phase["name"]) for phase in manifest()["phases"]]
    assert dependency_rows == expected
    assert {number for number, _ in dependency_rows} == set(range(1, 18))


def test_manifest_preserves_exact_autonomous_protected_and_bundle_sets():
    phases = manifest()["phases"]
    autonomous = {phase["phase_id"] for phase in phases if phase["owner_authority"] == "NONE"}
    protected = {phase["phase_id"] for phase in phases if phase["owner_authority"] != "NONE"}
    bundles = {
        bundle: {phase["phase_id"] for phase in phases if phase.get("owner_bundle") == bundle}
        for bundle in BUNDLES
    }
    assert autonomous == AUTONOMOUS_PHASES
    assert protected == OWNER_GATED_PHASES
    assert bundles == BUNDLES
    for bundle, phase_ids in BUNDLES.items():
        assert bundle in charter()
        assert phase_ids == bundles[bundle]


def test_broker_and_protected_transition_authority_remain_fail_closed():
    text = normalized_charter()
    assert "approval broker remains non-authoritative" in text
    assert "grants no authority to any later phase or protected transition" in text
    assert "fail-closed rule" in text
    assert "remains **blocked**" in text
    assert "may infer permission" in text


def test_every_prohibited_phase_1_capability_is_excluded():
    text = normalized_charter()
    prohibited = (
        "phone-number provisioning", "sms/mms", "cellular-provider integration",
        "carrier apis", "call initiation", "inbound call handling", "microphone capture",
        "speech recognition", "speaker recognition", "biometric enrollment",
        "device enrollment", "z fold trust activation", "passkeys", "yubikey enrollment",
        "liveness verification", "replay-protection runtime", "credentials", "secrets",
        "vault access", "location collection", "location storage",
        "runtime execution bridge", "the_lab execution", "deployment", "trading",
        "broker access", "orders", "money movement",
    )
    assert all(item in text for item in prohibited)
    assert "does not implement or activate" in text


def test_handoff_and_acceptance_matrix_are_defined():
    text = charter()
    assert "## Phase handoff contract" in text
    assert "## Acceptance matrix" in text
    assert "| Requirement | Evidence | Pass condition | Downstream consumer |" in text
    assert "Before Phase 2 or any later implementation relies on Phase 1" in text
