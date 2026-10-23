"""Run PKT-FOREX-018 twice, verify byte identity, and atomically promote."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_cross_sectional_short_horizon_reversal_v1 import (
    build_artifacts,
    research,
    write_artifacts,
)


def artifact_destinations(output_root: Path, report_path: Path, rejection_path: Path) -> dict[str, Path]:
    return {
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CONTRACT.json": output_root / "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CONTRACT.json",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CANDIDATE_REGISTRY.json": output_root / "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CANDIDATE_REGISTRY.json",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RESULTS.json": output_root / "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RESULTS.json",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CHECKPOINT.json": output_root / "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CHECKPOINT.json",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_MANIFEST.json": output_root / "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_MANIFEST.json",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RECEIPT.json": output_root / "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RECEIPT.json",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_V1_REPORT.md": report_path,
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_REJECTION_V1.json": rejection_path,
    }


def require_absent(destinations: dict[str, Path]) -> None:
    collisions = [str(path) for path in destinations.values() if path.exists()]
    if collisions:
        raise FileExistsError("OUTPUT_COLLISION:" + ",".join(collisions))


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def compare_artifacts(first: dict[str, bytes], second: dict[str, bytes]) -> None:
    if set(first) != set(second):
        raise ValueError("DETERMINISTIC_ARTIFACT_NAME_MISMATCH")
    mismatches = [name for name in sorted(first) if first[name] != second[name]]
    if mismatches:
        raise ValueError("DETERMINISTIC_BYTE_MISMATCH:" + ",".join(mismatches))


def execute(args: argparse.Namespace) -> dict[str, object]:
    destinations = artifact_destinations(args.output_root, args.report_path, args.rejection_path)
    require_absent(destinations)
    stage_root = Path(tempfile.mkdtemp(prefix="AIOS_PKT_FOREX_018_"))
    first_result = research(args.corpus_root, args.rejection_source, max_timestamps=args.max_timestamps)
    first = build_artifacts(first_result, ROOT / "automation/forex_engine/forex_cross_sectional_short_horizon_reversal_v1.py")
    write_artifacts(first, stage_root / "run1" / "runtime", stage_root / "run1" / "report.md", stage_root / "run1" / "rejection.json")
    second_result = research(args.corpus_root, args.rejection_source, max_timestamps=args.max_timestamps)
    second = build_artifacts(second_result, ROOT / "automation/forex_engine/forex_cross_sectional_short_horizon_reversal_v1.py")
    write_artifacts(second, stage_root / "run2" / "runtime", stage_root / "run2" / "report.md", stage_root / "run2" / "rejection.json")
    compare_artifacts(first, second)
    for name, path in destinations.items():
        atomic_write(path, first[name])
        if path.read_bytes() != first[name]:
            raise ValueError(f"PROMOTION_BYTE_MISMATCH:{path}")
    receipt = json.loads(first["AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RECEIPT.json"])
    return {
        "status": receipt["status"],
        "acceptance_status": receipt["acceptance_status"],
        "candidate_count": receipt["candidate_count"],
        "survivor_count": receipt["survivor_count"],
        "best_candidate": receipt["best_candidate"],
        "holdout_status": receipt["holdout_status"],
        "deterministic_artifact_count": len(first),
        "stage_root": str(stage_root),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--rejection-path", required=True, type=Path)
    parser.add_argument("--rejection-source", required=True, action="append", type=Path)
    parser.add_argument("--max-timestamps", type=int)
    args = parser.parse_args()
    print(json.dumps(execute(args), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
