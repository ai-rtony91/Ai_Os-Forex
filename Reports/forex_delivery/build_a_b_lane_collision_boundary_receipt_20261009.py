from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Dev\Ai.Os")
OUT_JSON = ROOT / "Reports" / "forex_delivery" / "AIOS_FOREX_A_B_LANE_COLLISION_BOUNDARY_RECEIPT_V1.json"
OUT_MD = ROOT / "Reports" / "forex_delivery" / "AIOS_FOREX_A_B_LANE_COLLISION_BOUNDARY_RECEIPT_V1.md"

A_LANE_ALLOW = [
    "automation/forex_engine/live_runtime_executor_v1.py",
    "automation/forex_engine/oanda_live_runtime_connector_v2.py",
    "automation/forex_engine/forex_owner_safety_evidence_intake_verification_prep_v1.py",
    "automation/forex_engine/forex_owner_safety_evidence_artifact_verifier_v1.py",
    "tests/forex_engine/test_live_runtime_executor_v1.py",
    "tests/forex_engine/test_oanda_live_runtime_connector_v2.py",
    "tests/forex_engine/test_forex_owner_safety_evidence_intake_verification_prep_v1.py",
    "tests/forex_engine/test_forex_owner_safety_evidence_artifact_verifier_v1.py",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_STATE.json",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_V1_REPORT.md",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_INTAKE_VERIFICATION_PREP_NEXT_CODEX_PACKET_V1.md",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_STATE.json",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_V1_REPORT.md",
    "Reports/forex_delivery/AIOS_FOREX_OWNER_SAFETY_EVIDENCE_ARTIFACT_VERIFIER_NEXT_CODEX_PACKET_V1.md",
    "Reports/forex_delivery/AIOS_FOREX_A_LANE_INSTALLATION_POLICY_RECEIPT_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_A_LANE_INSTALLATION_POLICY_RECEIPT_V1.md",
]

FRIEND_B_PREFIX_HINTS = [
    "automation/forex_engine/candidate_",
    "automation/forex_engine/canonical_demo_review_evidence_bridge.py",
    "automation/forex_engine/forex_directed_",
    "automation/forex_engine/forex_edge_",
    "automation/forex_engine/forex_high_throughput_",
    "automation/forex_engine/forex_intraday_",
    "automation/forex_engine/forex_scalping_",
    "automation/forex_engine/next_candidate_",
    "Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_",
    "Reports/forex_delivery/AIOS_FOREX_CANDIDATE_",
    "Reports/forex_delivery/AIOS_FOREX_EDGE_",
    "Reports/forex_delivery/AIOS_FOREX_NEXT_CANDIDATE_",
    "Reports/forex_delivery/AIOS_FOREX_P1_",
    "Reports/forex_delivery/AIOS_FOREX_SCALPING_",
    "Reports/forex_delivery/proof_bundle_to_candidate_bridge_report.json",
    "tests/forex_engine/test_candidate_",
    "tests/forex_engine/test_canonical_demo_review_evidence_bridge.py",
    "tests/forex_engine/test_forex_all_timeframe_",
    "tests/forex_engine/test_next_candidate_",
    "tests/forex_engine/test_proof_bundle_",
]


def git_lines(*args: str) -> list[str]:
    p = subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True)
    return [line.rstrip() for line in p.stdout.splitlines() if line.strip()]


def classify(path: str) -> str:
    if path in A_LANE_ALLOW or path.startswith("Reports/forex_delivery/build_a_") or path.startswith("Reports/forex_delivery/apply_a_lane_") or path.startswith("Reports/forex_delivery/patch_policy_"):
        return "A_LANE_CONTROL"
    if any(path.startswith(prefix) for prefix in FRIEND_B_PREFIX_HINTS):
        return "FRIEND_B_DATA_STRATEGY_PAPER"
    if path in {"AGENTS.md", "docs/governance/AI_OS_REPO_MEMORY.md"}:
        return "SHARED_GOVERNANCE_DO_NOT_TOUCH_WITHOUT_EXPLICIT_SCOPE"
    return "UNCLASSIFIED_REVIEW_BEFORE_TOUCH"


def main() -> int:
    status = git_lines("status", "--short")
    rows = []
    for line in status:
        path = line[3:] if len(line) > 3 else line
        rows.append({"status": line[:2], "path": path, "lane": classify(path)})
    receipt = {
        "receipt_schema": "AIOS_FOREX_A_B_LANE_COLLISION_BOUNDARY_RECEIPT_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "branch": git_lines("branch", "--show-current")[0],
        "head": git_lines("rev-parse", "HEAD")[0],
        "friend_b_scope": "P05/P06/P07/P08/P14 accounting, data, strategy, independent PAPER verifier, PAPER observations",
        "a_lane_scope": "P01/P02/P03/P04/P09/P10/P11/P12/P13 platform, installation, runtime safety, broker boundary, controls",
        "collision_policy": [
            "A-lane will not modify Friend B classified data/strategy/PAPER files without exact returned evidence and explicit integration point",
            "Friend B should not modify A-lane source/control files listed in a_lane_allow without a patch handoff",
            "Shared governance files require explicit task ID and source hash before any edit",
        ],
        "a_lane_allow": A_LANE_ALLOW,
        "working_tree_classification": rows,
        "counts": {lane: sum(1 for row in rows if row["lane"] == lane) for lane in sorted({row["lane"] for row in rows})},
    }
    OUT_JSON.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# AIOS Forex A/B Lane Collision Boundary Receipt V1", "", f"Created UTC: {receipt['created_utc']}", f"Branch: {receipt['branch']}", f"Head: {receipt['head']}", "", "## Counts"]
    lines.extend(f"- {k}: {v}" for k, v in receipt["counts"].items())
    lines.extend(["", "## Collision Policy"])
    lines.extend(f"- {item}" for item in receipt["collision_policy"])
    lines.extend(["", "## Working Tree Classification"])
    lines.extend(f"- {row['status']} {row['path']} => {row['lane']}" for row in rows)
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(OUT_JSON), "md": str(OUT_MD), "counts": receipt["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
