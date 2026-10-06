#!/usr/bin/env python3
"""Run one isolated PKT-FOREX-024 Stage-1 research reproduction."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from automation.forex_engine.forex_round_number_conditional_order_state_v1 import (  # noqa: E402
    build_artifacts,
    research,
    sha256_bytes,
)


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def execute(corpus_root: Path, preregistration: Path, output_root: Path) -> dict[str, object]:
    corpus_root = corpus_root.resolve()
    preregistration = preregistration.resolve()
    output_root = output_root.resolve()
    expected_corpus = (REPO_ROOT / ".aios/runtime/forex_m5_immutable_corpus_v2").resolve()
    expected_prereg = (REPO_ROOT / ".aios/staging/PKT_FOREX_023/run1/AIOS_FOREX_ROUND_NUMBER_SUCCESSOR_PREREGISTRATION.json").resolve()
    allowed_output = (REPO_ROOT / ".aios/staging/PKT_FOREX_024").resolve()
    if corpus_root != expected_corpus:
        raise ValueError("CORPUS_ROOT_NOT_FROZEN_CANONICAL_INPUT")
    if preregistration != expected_prereg:
        raise ValueError("PREREGISTRATION_NOT_FROZEN_STAGE0_INPUT")
    if not _inside(output_root, allowed_output) or output_root == allowed_output:
        raise ValueError("OUTPUT_ROOT_OUTSIDE_PACKET_STAGING")
    if output_root.exists():
        raise FileExistsError(f"OUTPUT_ROOT_ALREADY_EXISTS:{output_root}")

    result, journals = research(corpus_root, preregistration)
    code_path = REPO_ROOT / "automation/forex_engine/forex_round_number_conditional_order_state_v1.py"
    artifacts = build_artifacts(result, journals, code_path)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    for name, content in sorted(artifacts.items()):
        (temporary / name).write_bytes(content)
    os.replace(temporary, output_root)
    aggregate = sha256_bytes(
        b"".join(name.encode("utf-8") + b"\0" + artifacts[name] for name in sorted(artifacts))
    )
    return {
        "status": result["status"],
        "acceptance_status": json.loads(artifacts["AIOS_FOREX_ROUND_NUMBER_RECEIPT.json"])["acceptance_status"],
        "candidate_count": result["candidate_count"],
        "survivor_count": len(result["survivors"]),
        "best_candidate": result["best_candidate"],
        "journal_row_count": result["journal_row_count"],
        "verified_partition_count": result["verified_partition_count"],
        "holdout_status": result["holdout_status"],
        "artifact_count": len(artifacts),
        "aggregate_sha256": aggregate,
        "output_root": output_root.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.corpus_root, args.preregistration, args.output_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
