from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Dev\Ai.Os")
REPORT_DIR = ROOT / "Reports" / "forex_delivery"
OUT_JSON = REPORT_DIR / "AIOS_FOREX_A_LANE_INSTALLATION_POLICY_RECEIPT_V1.json"
OUT_MD = REPORT_DIR / "AIOS_FOREX_A_LANE_INSTALLATION_POLICY_RECEIPT_V1.md"

CLAIM = ROOT / "automation" / "orchestration" / "locks" / "Claim-AiOsFileLock.DRY_RUN.ps1"
RELEASE = ROOT / "automation" / "orchestration" / "locks" / "Release-AiOsFileLock.DRY_RUN.ps1"
REGISTRY = ROOT / "automation" / "orchestration" / "locks" / "FILE_LOCK_REGISTRY.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ps_json(command: str):
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def read_execution_policy_by_scope() -> dict[str, str]:
    scopes = ["MachinePolicy", "UserPolicy", "Process", "CurrentUser", "LocalMachine"]
    out: dict[str, str] = {}
    for scope in scopes:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Get-ExecutionPolicy -Scope {scope}"],
            check=True,
            capture_output=True,
            text=True,
        )
        out[scope] = completed.stdout.strip()
    return out


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    policy = read_execution_policy_by_scope()
    signatures = ps_json(
        "Get-AuthenticodeSignature "
        "'C:\\Dev\\Ai.Os\\automation\\orchestration\\locks\\Claim-AiOsFileLock.DRY_RUN.ps1',"
        "'C:\\Dev\\Ai.Os\\automation\\orchestration\\locks\\Release-AiOsFileLock.DRY_RUN.ps1' "
        "| Select-Object Path,Status,StatusMessage,SignerCertificate | ConvertTo-Json -Depth 5"
    )
    if isinstance(signatures, dict):
        signatures = [signatures]
    scripts = []
    sig_by_path = {str(row.get("Path")): row for row in signatures}
    for path in (CLAIM, RELEASE):
        sig = sig_by_path.get(str(path), {})
        scripts.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
                "sha256": sha256(path) if path.exists() else None,
                "authenticode_status": str(sig.get("Status")),
                "authenticode_status_message": sig.get("StatusMessage"),
                "signer_present": bool(sig.get("SignerCertificate")),
            }
        )
    blocker_reasons = []
    if policy.get("CurrentUser") == "Restricted":
        blocker_reasons.append("CurrentUser execution policy is Restricted")
    for script in scripts:
        if script["authenticode_status"] != "Valid" or not script["signer_present"]:
            blocker_reasons.append(f"{Path(script['path']).name} is not signed by a trusted signer")
    receipt = {
        "receipt_schema": "AIOS_FOREX_A_LANE_INSTALLATION_POLICY_RECEIPT_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=False, capture_output=True, text=True).stdout.strip(),
        "branch": subprocess.run(["git", "-C", str(ROOT), "branch", "--show-current"], check=False, capture_output=True, text=True).stdout.strip(),
        "execution_policy": policy,
        "lock_registry": {"path": str(REGISTRY), "exists": REGISTRY.exists(), "sha256": sha256(REGISTRY) if REGISTRY.exists() else None},
        "claim_scripts": scripts,
        "installation_claim_ready": not blocker_reasons,
        "blocker_reasons": blocker_reasons,
        "protected_actions_not_taken": [
            "no execution policy changed",
            "no script signing performed",
            "no claim script executed",
            "no repair installation performed",
            "no broker API used",
            "no credentials read",
            "no orders placed",
        ],
        "required_owner_resolution": [
            "Choose a legitimate Windows execution-policy route for reviewed signed scripts",
            "Review and sign the exact claim/release script contents or provide trusted signed equivalents",
            "Rerun canonical claim and ownership checks after policy/signature resolution",
        ],
    }
    OUT_JSON.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# AIOS Forex A-Lane Installation Policy Receipt V1",
        "",
        f"Created UTC: {receipt['created_utc']}",
        f"Branch: {receipt['branch']}",
        f"Head: {receipt['head']}",
        "",
        f"Installation claim ready: {receipt['installation_claim_ready']}",
        "",
        "## Blockers",
    ]
    lines.extend(f"- {item}" for item in blocker_reasons or ["none"])
    lines.extend(["", "## Protected Actions Not Taken"])
    lines.extend(f"- {item}" for item in receipt["protected_actions_not_taken"])
    lines.extend(["", "## Required Owner Resolution"])
    lines.extend(f"- {item}" for item in receipt["required_owner_resolution"])
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(OUT_JSON), "md": str(OUT_MD), "installation_claim_ready": receipt["installation_claim_ready"], "blocker_count": len(blocker_reasons)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
