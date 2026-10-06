"""Governed PKT044 commands plus bounded PKT045 Stage 0/Stage 1 commands."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine import forex_control_baseline_rsi_filter_comparison_stage1_v1 as handoff
from automation.forex_engine import forex_edge_validation_pipeline_v1 as validation

LOCK_ID = "LOCK_EAST_FOREX_CONTROL_BASELINE_RSI_FILTER_COMPARISON_STAGE1_OCC82"
ALLOWED_ROOT = ROOT / ".aios/staging/PKT_FOREX_044"
PKT045_LOCK_ID = "LOCK_EAST_FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_PREREGISTRATION_STAGE0_OCC83"
PKT045_WORKER_ID = "EAST_OCC_83"
PKT045_PACKET_ID = "PKT-FOREX-045"
PKT045_ALLOWED_ROOT = ROOT / ".aios/staging/PKT_FOREX_045"
PKT045_STAGE1_LOCK_ID = "LOCK_EAST_FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_ACQUISITION_CERTIFICATION_STAGE1_OCC84"
PKT045_STAGE1_WORKER_ID = "EAST_OCC_84"
PKT045_STAGE1_ALLOWED_ROOT = ROOT / ".aios/staging/PKT_FOREX_045/stage1_occ84"


def check_writer(registry: dict, output: Path, now: datetime, *, lock_id=LOCK_ID,
                 worker_id="EAST_OCC_82", packet_id="PKT-FOREX-044") -> None:
    active = [row for row in registry["locks"] if row["status"] == "ACTIVE"]
    ours = [row for row in active if row["lock_id"] == lock_id and row["worker_id"] == worker_id and row["packet_id"] == packet_id]
    if len(ours) != 1 or validation.parse_utc(ours[0]["expires_at_utc"]) <= now:
        raise ValueError("HANDOFF_WRITER_LOCK_MISSING_OR_EXPIRED")
    relative = output.relative_to(ROOT).as_posix().casefold()
    def covers(path):
        normalized = path.replace("\\", "/").rstrip("/").casefold()
        return relative == normalized or relative.startswith(normalized + "/")
    def overlaps(path):
        normalized = path.replace("\\", "/").rstrip("/").casefold()
        return covers(path) or normalized.startswith(relative + "/")
    if not any(covers(path) for path in ours[0]["claimed_paths"]):
        raise ValueError("HANDOFF_OUTPUT_NOT_OWNED")
    for row in active:
        if row is ours[0]:
            continue
        if any(overlaps(path) for path in row["claimed_paths"]):
            raise ValueError("HANDOFF_OVERLAPPING_WRITER")


def save_once(output: Path, payload: dict, *, max_bytes: int = 1024 * 1024 * 1024) -> dict:
    """Immutable content receipt written last; incomplete folders fail closed."""
    output = output.resolve()
    if not output.is_relative_to(ALLOWED_ROOT.resolve()) or output == ALLOWED_ROOT.resolve():
        raise ValueError("HANDOFF_OUTPUT_OUTSIDE_PACKET")
    data = (validation.pretty_json(payload) + "\n").encode("utf-8")
    if len(data) > max_bytes:
        raise ValueError("HANDOFF_STORAGE_LIMIT")
    receipt = {"schema": "AIOS_FOREX_HANDOFF_RECEIPT.v1", "status": "COMPLETE",
               "payload_sha256": validation.sha256_bytes(data), "bytes": len(data),
               "market_trials_added": 0, "next_state": "AWAITING_APPROVAL"}
    receipt_bytes = (validation.pretty_json(receipt) + "\n").encode("utf-8")
    if output.exists():
        if not (output / "receipt.json").is_file() or not (output / "handoff.json").is_file():
            raise ValueError("HANDOFF_PARTIAL_OUTPUT_PRESERVE_AND_USE_NEW_DIRECTORY")
        if (output / "handoff.json").read_bytes() != data or (output / "receipt.json").read_bytes() != receipt_bytes:
            raise ValueError("HANDOFF_COMPLETION_CONFLICT")
        return receipt
    output.mkdir(parents=True, exist_ok=False)
    with (output / "handoff.json").open("xb") as handle:
        handle.write(data)
    with (output / "receipt.json").open("xb") as handle:
        handle.write(receipt_bytes)
    return receipt


def run(output: Path) -> dict:
    output = output.resolve()
    registry_path = ROOT / "automation/orchestration/locks/FILE_LOCK_REGISTRY.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    check_writer(registry, output, datetime.now(timezone.utc))
    payload = handoff.replay_completed_summary(ROOT)
    # Recheck ownership after reading inputs; do not claim or widen authority here.
    check_writer(json.loads(registry_path.read_text(encoding="utf-8-sig")), output, datetime.now(timezone.utc))
    return save_once(output, payload)


def _load_pricing_basis(path: Path) -> object:
    path = path.resolve()
    if not path.is_relative_to(PKT045_STAGE1_ALLOWED_ROOT.resolve()) or not path.is_file():
        raise ValueError("PKT045_STAGE1_PRICING_BASIS_OUTSIDE_APPROVED_ROOT")
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = (
        "LIST_PER_1000_USD", "GET_PER_1000_USD", "HEAD_PER_1000_USD", "RETRIEVAL_PER_GB_USD", "TRANSFER_PER_GB_USD",
        "AWS_PRICE_SOURCE", "SOURCE_RETRIEVED_AT", "FREE_ALLOWANCE_ASSUMPTION",
    )
    if any(key not in payload for key in required):
        raise ValueError("PKT045_STAGE1_PRICING_BASIS_INCOMPLETE")
    from automation.forex_engine.edge_research.dukascopy_acquisition import CostBasis
    return CostBasis(
        list_per_1000_usd=payload["LIST_PER_1000_USD"],
        get_per_1000_usd=payload["GET_PER_1000_USD"],
        head_per_1000_usd=payload["HEAD_PER_1000_USD"],
        retrieval_per_gb_usd=payload["RETRIEVAL_PER_GB_USD"],
        transfer_per_gb_usd=payload["TRANSFER_PER_GB_USD"],
        price_source=payload["AWS_PRICE_SOURCE"],
        retrieved_at_utc=payload["SOURCE_RETRIEVED_AT"],
        free_allowance_assumption=payload["FREE_ALLOWANCE_ASSUMPTION"],
    )


def dispatch(command, output, *, approved=False, approved_pkt045_preregistration=False,
             approved_pkt045_stage1_inventory=False, approved_pkt045_stage1=False,
             pricing_basis=None, test_receipt=None, max_new_objects=None):
    from automation.forex_engine.edge_research import batch
    output = output.resolve()
    if command in {"preregister-pkt045", "status-pkt045"}:
        if not output.is_relative_to(PKT045_ALLOWED_ROOT.resolve()) or output == PKT045_ALLOWED_ROOT.resolve():
            raise ValueError("OUTPUT_OUTSIDE_PKT045")
        if command == "status-pkt045":
            return batch.pkt045_status(ROOT, output)
        if not approved_pkt045_preregistration:
            raise ValueError("EXPLICIT_PKT045_PREREGISTRATION_PERMISSION_REQUIRED")
        registry_path = ROOT / "automation/orchestration/locks/FILE_LOCK_REGISTRY.json"
        writer_args = {"lock_id": PKT045_LOCK_ID, "worker_id": PKT045_WORKER_ID, "packet_id": PKT045_PACKET_ID}
        check_writer(json.loads(registry_path.read_text(encoding="utf-8-sig")), output, datetime.now(timezone.utc), **writer_args)
        result = batch.preregister_pkt045(ROOT, output)
        # Recheck ownership after every local evidence write.  This command has
        # no acquisition, corpus, or scoring branch.
        check_writer(json.loads(registry_path.read_text(encoding="utf-8-sig")), output, datetime.now(timezone.utc), **writer_args)
        return result
    if command in {"inventory-pkt045-stage1", "status-pkt045-stage1", "freeze-pkt045-stage1", "acquire-pkt045-stage1", "certify-pkt045-stage1", "run-pkt045-stage1", "resume-pkt045-stage1"}:
        if output != PKT045_STAGE1_ALLOWED_ROOT.resolve():
            raise ValueError("OUTPUT_OUTSIDE_PKT045_STAGE1")
        if command == "status-pkt045-stage1":
            return batch.pkt045_stage1_status(ROOT, output)
        registry_path = ROOT / "automation/orchestration/locks/FILE_LOCK_REGISTRY.json"
        writer_args = {
            "lock_id": PKT045_STAGE1_LOCK_ID,
            "worker_id": PKT045_STAGE1_WORKER_ID,
            "packet_id": PKT045_PACKET_ID,
        }
        if command == "inventory-pkt045-stage1":
            if not approved_pkt045_stage1_inventory:
                raise ValueError("EXPLICIT_PKT045_STAGE1_INVENTORY_PERMISSION_REQUIRED")
            if pricing_basis is None:
                raise ValueError("PKT045_STAGE1_PRICING_BASIS_REQUIRED")
            check_writer(json.loads(registry_path.read_text(encoding="utf-8-sig")), output, datetime.now(timezone.utc), **writer_args)
            result = batch.pkt045_stage1_inventory_and_cost(ROOT, output, pricing=_load_pricing_basis(pricing_basis))
            check_writer(json.loads(registry_path.read_text(encoding="utf-8-sig")), output, datetime.now(timezone.utc), **writer_args)
            return result
        if not approved_pkt045_stage1:
            raise ValueError("EXPLICIT_PKT045_STAGE1_PERMISSION_REQUIRED")
        check_writer(json.loads(registry_path.read_text(encoding="utf-8-sig")), output, datetime.now(timezone.utc), **writer_args)
        if command == "freeze-pkt045-stage1":
            result = batch.freeze_pkt045_stage1(ROOT, output)
        elif command in {"acquire-pkt045-stage1", "resume-pkt045-stage1"}:
            result = batch.acquire_pkt045_stage1(ROOT, output, max_new_objects=max_new_objects)
        elif command == "certify-pkt045-stage1":
            result = batch.certify_pkt045_stage1(ROOT, output)
        elif command == "run-pkt045-stage1":
            result = batch.run_pkt045_stage1(ROOT, output)
        else:
            raise ValueError("UNKNOWN_PKT045_STAGE1_COMMAND")
        check_writer(json.loads(registry_path.read_text(encoding="utf-8-sig")), output, datetime.now(timezone.utc), **writer_args)
        return result
    from automation.forex_engine import forex_edge_discovery_tournament_stage1_v1 as data
    from automation.forex_engine.forex_edge_existence_controller_v1 import route_pkt044_research
    if not output.is_relative_to(ALLOWED_ROOT.resolve()) or output == ALLOWED_ROOT.resolve():
        raise ValueError("OUTPUT_OUTSIDE_PKT044")
    if command == "summary": return run(output)
    if command in {"status", "review"}:
        current = batch.status(output)
        if command == "review":
            if current.get("state") != "BATCH_COMPLETE": raise ValueError("RESULT_NOT_COMPLETE")
            current["handoff"] = json.loads((output/"handoff.json").read_bytes())
        return current
    if not approved: raise ValueError("EXPLICIT_PKT044_LAUNCH_PERMISSION_REQUIRED")
    if command in {"run-batch", "correct-batch"}:
        if test_receipt is None: raise ValueError("TEST_RECEIPT_REQUIRED_BEFORE_LAUNCH")
        contract, manifest = batch.freeze(ROOT, output, test_receipt, correction=command == "correct-batch")
    elif command == "resume":
        contract = json.loads((output/"contract.json").read_bytes())
        manifest = data.verify_corpus_manifest(ROOT/".aios/runtime/forex_m5_immutable_corpus_v2")
    else: raise ValueError("UNKNOWN_BATCH_COMMAND")
    return route_pkt044_research(ROOT, output, contract, manifest, approved=approved, resume=command == "resume")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "summary", "run-batch", "correct-batch", "status", "resume", "review",
        "preregister-pkt045", "status-pkt045", "inventory-pkt045-stage1", "status-pkt045-stage1",
        "freeze-pkt045-stage1", "acquire-pkt045-stage1", "resume-pkt045-stage1", "certify-pkt045-stage1", "run-pkt045-stage1",
    ), nargs="?", default="summary")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--approve-pkt044-launch", action="store_true")
    parser.add_argument("--approve-pkt045-preregistration", action="store_true")
    parser.add_argument("--approve-pkt045-stage1-inventory", action="store_true")
    parser.add_argument("--approve-pkt045-stage1", action="store_true")
    parser.add_argument("--pricing-basis", type=Path)
    parser.add_argument("--test-receipt", type=Path)
    parser.add_argument("--max-new-objects", type=int)
    args = parser.parse_args()
    print(json.dumps(dispatch(args.command, args.output_root, approved=args.approve_pkt044_launch,
                             approved_pkt045_preregistration=args.approve_pkt045_preregistration,
                             approved_pkt045_stage1_inventory=args.approve_pkt045_stage1_inventory,
                             approved_pkt045_stage1=args.approve_pkt045_stage1,
                             pricing_basis=args.pricing_basis,
                             test_receipt=args.test_receipt,
                             max_new_objects=args.max_new_objects), sort_keys=True))
