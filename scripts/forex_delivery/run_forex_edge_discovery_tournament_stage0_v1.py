#!/usr/bin/env python3
"""Run the deterministic metadata-only PKT-FOREX-038 Stage 0."""
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

from automation.forex_engine.forex_edge_discovery_tournament_stage0_v1 import build_stage0, sha256_bytes  # noqa: E402


REJECTION_INPUTS = (
    ".aios/runtime/forex_frozen_21_series_phase1_postmortem_v1/AIOS_FOREX_PHASE1_POSTMORTEM.json",
    "Reports/forex_delivery/AIOS_FOREX_CROSS_SECTIONAL_CURRENCY_STRENGTH_REJECTION_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_CROSS_PAIR_RESIDUAL_REJECTION_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_CURRENCY_FACTOR_REGIME_REJECTION_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_REJECTION_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_REJECTION_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_CFTC_POSITIONING_ACCELERATION_PRICE_CONTINUATION_REJECTION_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_CFTC_PARTICIPANT_DIVERGENCE_PRICE_CONFIRMATION_REJECTION_V1.json",
    "Reports/forex_delivery/AIOS_FOREX_CFTC_DEALER_INVENTORY_PRESSURE_REVERSAL_REJECTION_V1.json",
)


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def run(output_root: Path) -> dict[str, object]:
    output_root = output_root.resolve()
    allowed = (REPO_ROOT / ".aios/staging/PKT_FOREX_038").resolve()
    if output_root == allowed or not _inside(output_root, allowed):
        raise ValueError("OUTPUT_ROOT_OUTSIDE_PACKET_STAGING")
    if output_root.exists():
        raise FileExistsError(f"OUTPUT_ROOT_ALREADY_EXISTS:{output_root}")
    rejection_paths = [REPO_ROOT / relative for relative in REJECTION_INPUTS]
    missing = [path.as_posix() for path in rejection_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("MISSING_REJECTION_INPUTS:" + json.dumps(missing, separators=(",", ":")))
    artifacts = build_stage0(rejection_paths, REPO_ROOT)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    for name, content in sorted(artifacts.items()):
        (temporary / name).write_bytes(content)
    os.replace(temporary, output_root)
    aggregate = sha256_bytes(b"".join(name.encode("utf-8") + b"\0" + artifacts[name] for name in sorted(artifacts)))
    return {"status": "PASS", "packet_id": "PKT-FOREX-038", "artifact_count": len(artifacts), "artifact_names": sorted(artifacts), "aggregate_sha256": aggregate, "output_root": output_root.as_posix()}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
