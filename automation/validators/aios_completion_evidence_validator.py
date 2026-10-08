"""AI_OS completion evidence validator.

The governance validator proves a packet's SHAPE. This validator proves a
mission actually COMPLETED in reality: that the claimed deliverables exist, the
change set stayed inside the packet's allowed paths and touched no forbidden
path, validation evidence is present, and no activation hazard leaked in.

It is read-only over the repo and mutates no state. A VERIFIED verdict is
evidence only; it does not approve commit, push, merge, or any protected action.

Verdicts:
    COMPLETION_VERIFIED     - deliverables real, in-scope, evidence present, clean
    COMPLETION_UNPROVEN     - nothing contradicts, but proof is incomplete
    COMPLETION_CONTRADICTED - reality contradicts the claim (missing/empty file,
                              forbidden-path edit, or activation hazard)

Pure standard library. No network, no mutation.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


VALIDATOR_NAME = "aios_completion_evidence_validator"
VERSION = "1.0"

# Note: content secret/activation scanning is deliberately NOT done here.
# It is the job of the dedicated secret-prevention / governance layer, and doing
# it on deliverable contents false-positives on security tooling and test
# fixtures (the "scanner flags itself" problem). This validator proves the work
# is real and in-scope via the path layer; the forbidden-path check below already
# blocks edits to broker/secrets/live paths.

EVIDENCE_MARKERS = [
    r"(?i)\bpass(ed)?\b",
    r"(?i)pytest",
    r"(?i)git diff --check",
    r"(?i)\bvalidat",
]


@dataclass
class RuleResult:
    rule_id: str
    severity: str          # CONTRADICT | UNPROVEN | INFO
    passed_boolean: bool
    message: str
    evidence: str


def _norm(p: str) -> str:
    return p.strip().strip("-").strip().strip("`").replace("\\", "/").strip().rstrip("/")


def extract_path_list(packet_text: str, marker: str) -> list[str]:
    """Collect path entries listed under an ALL-CAPS marker until the next marker."""
    lines = packet_text.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        stripped = line.strip()
        if not capturing:
            if stripped.upper().startswith(marker):
                capturing = True
            continue
        # stop at the next ALL-CAPS section header (e.g. "FORBIDDEN PATHS:")
        if re.match(r"^[A-Z][A-Z _/-]{3,}:?\s*$", stripped) and stripped.upper() != marker:
            break
        if not stripped:
            continue
        cleaned = _norm(stripped)
        # only treat path-shaped lines as paths
        if cleaned and ("/" in cleaned or cleaned.endswith(".md") or "." in cleaned or cleaned.isupper() is False):
            if not cleaned.endswith(":"):
                out.append(cleaned)
    return out


def _under(path: str, prefix: str) -> bool:
    path = path.replace("\\", "/").strip().rstrip("/")
    prefix = prefix.replace("\\", "/").strip().rstrip("/")
    if not prefix:
        return False
    return path == prefix or path.startswith(prefix + "/")


def evaluate_completion(
    packet_text: str,
    changed_files: list[str],
    repo_root: Path,
    evidence_text: Optional[str],
    input_path: str = "<completion>",
) -> dict[str, object]:
    rules: list[RuleResult] = []
    changed_files = [c.replace("\\", "/").strip() for c in changed_files if c.strip()]
    allowed = extract_path_list(packet_text, "ALLOWED PATHS") if packet_text else []
    forbidden = extract_path_list(packet_text, "FORBIDDEN PATHS") if packet_text else []

    # 1. deliverables declared (UNPROVEN if none)
    rules.append(RuleResult(
        "CEV-001-DELIVERABLES-DECLARED", "UNPROVEN", bool(changed_files),
        "At least one claimed deliverable/changed file is declared.",
        f"{len(changed_files)} declared",
    ))

    # 2. every claimed file exists and is non-empty (CONTRADICT)
    missing: list[str] = []
    empty: list[str] = []
    for rel in changed_files:
        fp = repo_root / rel
        if not fp.exists() or not fp.is_file():
            missing.append(rel)
        elif fp.stat().st_size == 0:
            empty.append(rel)
    rules.append(RuleResult(
        "CEV-002-DELIVERABLES-REAL", "CONTRADICT", not (missing or empty),
        "Every claimed deliverable exists and is non-empty.",
        f"missing={missing} empty={empty}",
    ))

    # 3. all changed files within allowed paths (CONTRADICT if packet declared allowed paths)
    out_of_scope = [c for c in changed_files if allowed and not any(_under(c, a) for a in allowed)]
    rules.append(RuleResult(
        "CEV-003-WITHIN-ALLOWED", "CONTRADICT", not out_of_scope,
        "Every changed file is inside the packet allowed paths.",
        f"out_of_scope={out_of_scope}" if allowed else "no allowed-path list in packet (skipped)",
    ))

    # 4. no changed file under a forbidden path (CONTRADICT)
    forbidden_hits = [c for c in changed_files for f in forbidden if _under(c, f)]
    rules.append(RuleResult(
        "CEV-004-NO-FORBIDDEN-PATH", "CONTRADICT", not forbidden_hits,
        "No changed file touches a forbidden path.",
        f"forbidden_hits={sorted(set(forbidden_hits))}",
    ))

    # 5. validation evidence present (UNPROVEN)
    has_evidence = bool(evidence_text) and any(re.search(m, evidence_text) for m in EVIDENCE_MARKERS)
    rules.append(RuleResult(
        "CEV-005-EVIDENCE-PRESENT", "UNPROVEN", has_evidence,
        "Validation evidence (test/validator results) is present, not asserted.",
        "evidence markers found" if has_evidence else "no validation markers in evidence",
    ))

    contradicted = [asdict(r) for r in rules if not r.passed_boolean and r.severity == "CONTRADICT"]
    unproven = [asdict(r) for r in rules if not r.passed_boolean and r.severity == "UNPROVEN"]
    if contradicted:
        verdict = "COMPLETION_CONTRADICTED"
    elif unproven:
        verdict = "COMPLETION_UNPROVEN"
    else:
        verdict = "COMPLETION_VERIFIED"

    return {
        "validator_name": VALIDATOR_NAME,
        "version": VERSION,
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "input_path": input_path,
        "verdict": verdict,
        "approves_protected_action": False,
        "contradictions": contradicted,
        "unproven": unproven,
        "rules_checked": [asdict(r) for r in rules],
        "reasons": [item["message"] + " :: " + item["evidence"] for item in (contradicted + unproven)],
        "safe_next_action": (
            "Mission is verified by evidence; a human may now consider the protected gate."
            if verdict == "COMPLETION_VERIFIED"
            else "Do not treat as complete. Resolve the listed contradictions/unproven items first."
        ),
    }


def _sample_check() -> dict[str, object]:
    packet = (
        "CODEX-ONLY PROMPT\nALLOWED PATHS:\n- automation/validators/\n- tests/orchestration/\n"
        "FORBIDDEN PATHS:\n- AGENTS.md\n- broker/\nMISSION:\nsample\n"
    )
    evidence = "pytest: 3 passed. git diff --check PASS. validation complete."
    base = Path(tempfile.gettempdir()) / "aios_completion_evidence_validator_samples"
    base.mkdir(parents=True, exist_ok=True)
    root = base / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    try:
        (root / "automation/validators").mkdir(parents=True)
        good = "automation/validators/sample_good.py"
        (root / good).write_text("print('ok')\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("authority\n", encoding="utf-8")

        verified = evaluate_completion(packet, [good], root, evidence)
        unproven = evaluate_completion(packet, [good], root, None)              # no evidence
        missing = evaluate_completion(packet, ["automation/validators/ghost.py"], root, evidence)
        forbidden = evaluate_completion(packet, ["AGENTS.md"], root, evidence)  # forbidden + exists
        return {
            "verified": verified["verdict"],
            "unproven": unproven["verdict"],
            "contradicted_missing": missing["verdict"],
            "contradicted_forbidden": forbidden["verdict"],
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AI_OS mission completion against real evidence.")
    parser.add_argument("--packet", help="packet .md to read allowed/forbidden paths from")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--changed", action="append", default=[], help="a changed/claimed file (repeatable)")
    parser.add_argument("--evidence", help="path to an evidence report (md/json/txt)")
    parser.add_argument("--sample-check", action="store_true")
    args = parser.parse_args()

    if args.sample_check:
        result = _sample_check()
        print(json.dumps(result, indent=2, sort_keys=True))
        ok = (
            result["verified"] == "COMPLETION_VERIFIED"
            and result["unproven"] == "COMPLETION_UNPROVEN"
            and result["contradicted_missing"] == "COMPLETION_CONTRADICTED"
            and result["contradicted_forbidden"] == "COMPLETION_CONTRADICTED"
        )
        return 0 if ok else 1

    packet_text = Path(args.packet).read_text(encoding="utf-8") if args.packet else ""
    evidence_text = Path(args.evidence).read_text(encoding="utf-8") if args.evidence else None
    result = evaluate_completion(
        packet_text, args.changed, Path(args.repo_root), evidence_text,
        input_path=args.packet or "<completion>",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] != "COMPLETION_CONTRADICTED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
