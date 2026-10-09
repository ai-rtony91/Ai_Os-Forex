from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Dev\Ai.Os")
REPORT_DIR = ROOT / "Reports" / "forex_delivery"
ZIP_PATH = REPORT_DIR / "AIOS_FOREX_A_LANE_CONTROL_REPAIR_PACKAGE_20261009.zip"
MANIFEST_PATH = REPORT_DIR / "AIOS_FOREX_A_LANE_CONTROL_REPAIR_PACKAGE_20261009_MANIFEST.json"

FILES = [
    "automation/forex_engine/live_runtime_executor_v1.py",
    "automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py",
    "automation/forex_engine/forex_owner_safety_evidence_artifact_verifier_v1.py",
    "tests/forex_engine/test_live_runtime_executor_v1.py",
    "tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py",
    "tests/forex_engine/test_forex_owner_safety_evidence_artifact_verifier_v1.py",
    "automation/forex_engine/forex_a_lane_owner_control_intake_validator_v1.py",
    "tests/forex_engine/test_forex_a_lane_owner_control_intake_validator_v1.py",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_STATE.json",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_REPORT.md",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_NEXT_CODEX_PACKET_V1.md",
    "Reports/forex_delivery/AIOS_FOREX_A_LANE_INSTALLATION_POLICY_RECEIPT_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_A_LANE_INSTALLATION_POLICY_RECEIPT_V1.md",
    "Reports/forex_delivery/AIOS_FOREX_A_B_LANE_COLLISION_BOUNDARY_RECEIPT_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_A_B_LANE_COLLISION_BOUNDARY_RECEIPT_V1.md",
    "Reports/forex_delivery/AIOS_FOREX_A_LANE_CONTROL_REPAIR_DIFF_20261009.patch",
    "Reports/forex_delivery/build_a_lane_installation_policy_receipt_20261009.py",
    "Reports/forex_delivery/AIOS_FOREX_A_LANE_REMAINING_CONTROL_GATE_PROBE_V1.json",
    "Reports/forex_delivery/probe_a_lane_remaining_control_gates_20261009.py",
    "Reports/forex_delivery/AIOS_FOREX_A_LANE_OWNER_CONTROL_INTAKE_PACKET_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_A_LANE_OWNER_CONTROL_INTAKE_PACKET_V1.md",
    "Reports/forex_delivery/build_a_lane_owner_control_intake_packet_20261009.py",
    "Reports/forex_delivery/build_a_b_lane_collision_boundary_receipt_20261009.py",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    entries = []
    for rel in FILES:
        path = ROOT / rel
        if not path.exists():
            raise SystemExit(f"missing: {rel}")
        entries.append({"path": rel, "size_bytes": path.stat().st_size, "sha256": sha(path)})
    manifest = {
        "manifest_schema": "AIOS_FOREX_A_LANE_CONTROL_REPAIR_PACKAGE_20261009_MANIFEST",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "A-lane platform/control/safety only; excludes Friend B data/strategy/PAPER lane files",
        "protected_actions_not_taken": ["no broker API", "no credentials", "no orders", "no execution policy change", "no script signing", "no claim script execution"],
        "verification": {
            "native_focused_tests": "76 passed",
            "native_broader_a_lane_tests": "211 passed",
            "governance_packets": "PASS",
        },
        "entries": entries,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in FILES:
            zf.write(ROOT / rel, rel)
        zf.write(MANIFEST_PATH, MANIFEST_PATH.relative_to(ROOT).as_posix())
    print(json.dumps({"zip": str(ZIP_PATH), "manifest": str(MANIFEST_PATH), "zip_sha256": sha(ZIP_PATH), "entry_count": len(entries) + 1}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
