"""Run PKT-FOREX-019 twice, require byte identity, and atomically promote."""
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

from automation.forex_engine.forex_cftc_crowding_unwind_price_confirmation_v1 import build_artifacts, research, write_artifacts


PREFIX = "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION"


def artifact_destinations(output_root: Path, report_path: Path, rejection_path: Path) -> dict[str, Path]:
    return {
        f"{PREFIX}_CONTRACT.json": output_root / f"{PREFIX}_CONTRACT.json",
        f"{PREFIX}_CANDIDATE_REGISTRY.json": output_root / f"{PREFIX}_CANDIDATE_REGISTRY.json",
        f"{PREFIX}_RESULTS.json": output_root / f"{PREFIX}_RESULTS.json",
        f"{PREFIX}_CHECKPOINT.json": output_root / f"{PREFIX}_CHECKPOINT.json",
        f"{PREFIX}_MANIFEST.json": output_root / f"{PREFIX}_MANIFEST.json",
        f"{PREFIX}_RECEIPT.json": output_root / f"{PREFIX}_RECEIPT.json",
        f"{PREFIX}_V1_REPORT.md": report_path,
        f"{PREFIX}_REJECTION_V1.json": rejection_path,
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
    if args.stage_parent:
        args.stage_parent.mkdir(parents=True, exist_ok=True)
    if args.stage_root:
        stage_root = args.stage_root
        if not stage_root.is_dir():
            raise FileNotFoundError(f"PRECREATED_STAGE_ROOT_REQUIRED:{stage_root}")
    else:
        stage_root = Path(tempfile.mkdtemp(prefix="AIOS_PKT_FOREX_019_", dir=str(args.stage_parent) if args.stage_parent else None))
    first_result = research(args.h1_manifest, args.cftc_root, args.rejection_source)
    first = build_artifacts(first_result, ROOT / "automation/forex_engine/forex_cftc_crowding_unwind_price_confirmation_v1.py")
    write_artifacts(first, stage_root / "run1" / "runtime", stage_root / "run1" / "report.md", stage_root / "run1" / "rejection.json")
    second_result = research(args.h1_manifest, args.cftc_root, args.rejection_source)
    second = build_artifacts(second_result, ROOT / "automation/forex_engine/forex_cftc_crowding_unwind_price_confirmation_v1.py")
    write_artifacts(second, stage_root / "run2" / "runtime", stage_root / "run2" / "report.md", stage_root / "run2" / "rejection.json")
    compare_artifacts(first, second)
    for name, path in destinations.items():
        atomic_write(path, first[name])
        if path.read_bytes() != first[name]:
            raise ValueError(f"PROMOTION_BYTE_MISMATCH:{path}")
    receipt = json.loads(first[f"{PREFIX}_RECEIPT.json"])
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
    parser.add_argument("--h1-manifest", required=True, type=Path)
    parser.add_argument("--cftc-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--report-path", required=True, type=Path)
    parser.add_argument("--rejection-path", required=True, type=Path)
    parser.add_argument("--rejection-source", required=True, action="append", type=Path)
    parser.add_argument("--stage-parent", type=Path)
    parser.add_argument("--stage-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(execute(args), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
