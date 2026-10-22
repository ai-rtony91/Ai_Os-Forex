#!/usr/bin/env python3
"""Generate local compound work-braid state, report, and checkpoint artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.orchestration.aios_compound_work_braid_v1 import (
    build_compound_work_braid,
    make_checkpoint,
    render_report,
    stable_json,
    validate_state,
    validate_resume,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    output = root / "Reports" / "orchestration"
    state_path = output / "AIOS_COMPOUND_WORK_BRAID_V1_STATE.json"
    report_path = output / "AIOS_COMPOUND_WORK_BRAID_V1_REPORT.md"
    checkpoint_path = output / "AIOS_COMPOUND_WORK_BRAID_V1_CHECKPOINT.json"
    prompt_path = output / "AIOS_COMPOUND_WORK_BRAID_V1_NEXT_CODEX_PROMPT.md"
    state = build_compound_work_braid(root)
    validation = validate_state(state)
    if validation["status"] != "PASS":
        raise SystemExit("state validation failed: " + ", ".join(validation["defects"]))
    state["schema_validation"] = validation
    if args.resume:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        validate_resume(checkpoint, state["repository"], state["dependency_graph"]["graph_hash"])
    checkpoint = make_checkpoint(state, state["repository"], completed_stages=("preflight", "state_discovery", "dependency_verification", "implementation", "targeted_validation", "regression_validation", "evidence_generation", "artifact_accounting", "checkpoint_generation", "execution_receipt", "continuation_generation", "commit_readiness_report", "pr_readiness_report", "owner_handoff"))
    output.mkdir(parents=True, exist_ok=True)
    state_path.write_text(stable_json(state, pretty=True), encoding="utf-8")
    report_path.write_text(render_report(state), encoding="utf-8")
    checkpoint_path.write_text(stable_json(checkpoint, pretty=True), encoding="utf-8")
    prompt_path.write_text(state["continuation_packet"], encoding="utf-8")
    print(stable_json(state, pretty=args.pretty), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
