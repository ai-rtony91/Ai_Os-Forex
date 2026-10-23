"""PKT044 bounded batch I/O used only through existing factory/controller routing."""
from pathlib import Path
from datetime import date, datetime, timezone
from dataclasses import asdict
import ctypes
import gzip
import json
import os
import shutil
import time
import xml.etree.ElementTree as ET
from typing import Any, Mapping

from automation.forex_engine import forex_edge_validation_pipeline_v1 as validation
from automation.forex_engine import forex_edge_discovery_tournament_stage1_v1 as data
from automation.forex_engine import forex_edge_discovery_tournament_stage0_v1 as stage0
from automation.forex_engine.edge_research import research
from automation.forex_engine.edge_research import dukascopy_acquisition
from automation.forex_engine.edge_research import dukascopy_bi5
from automation.forex_engine.edge_research import data as pkt045_data

CODE_PATHS = (
    "automation/forex_engine/edge_research/features.py", "automation/forex_engine/edge_research/execution.py",
    "automation/forex_engine/edge_research/research.py", "automation/forex_engine/edge_research/batch.py",
    "automation/forex_engine/indicators.py", "automation/forex_engine/forex_scalping_techniques_v1.py",
    "automation/forex_engine/forex_edge_validation_pipeline_v1.py",
    "automation/forex_engine/forex_edge_discovery_tournament_stage0_v1.py",
    "automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py",
    "automation/forex_engine/forex_control_baseline_rsi_filter_comparison_stage1_v1.py",
    "automation/forex_engine/forex_high_throughput_edge_factory_v1.py",
    "automation/forex_engine/forex_edge_existence_controller_v1.py",
    "scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py",
    "scripts/forex_delivery/run_forex_factor_common_component_momentum_stage0_v1.py")

PKT045_PACKET_ID = "PKT-FOREX-045"
PKT045_WORKER_ID = "EAST_OCC_83"
PKT045_STAGING_RELATIVE = Path(".aios/staging/PKT_FOREX_045")
PKT045_TICK_PROBE_RELATIVE = Path(
    ".aios/staging/PKT_FOREX_044/dukascopy_tick_probe_occ82_20260907/AUDCAD_2024_00_02_ticks.bi5"
)
PKT045_PRIOR_DUKASCOPY_SPEND_USD = 0.22917987961
PKT045_OWNER_CUMULATIVE_COST_LIMIT_USD = 1.00
PKT045_STAGE0_RECEIPT_RELATIVE = Path(
    ".aios/staging/PKT_FOREX_045/preregistration_occ83_20260907/PREREGISTRATION_RECEIPT_RUN1.json"
)
PKT045_STAGE0_RECEIPT_SHA256 = "75b7c661ab197e5da531f0cbfedd43584176d514e67eef01ad0495f24f67dd0f"
PKT045_STAGE1_WORKER_ID = "EAST_OCC_84"
PKT045_STAGE1_LANE = "FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_ACQUISITION_CERTIFICATION_STAGE1"
PKT045_STAGE1_LOCK_ID = "LOCK_EAST_FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_ACQUISITION_CERTIFICATION_STAGE1_OCC84"
PKT045_STAGE1_RELATIVE = Path(".aios/staging/PKT_FOREX_045/stage1_occ84")
PKT045_STAGE1_INVENTORY_ADDITIONAL_LIMIT_USD = 0.02
PKT045_STAGE1_OUTPUT_LIMIT_BYTES = 8 * 1024**3
PKT045_STAGE1_CORPUS_RESERVATION_BYTES = 1536 * 1024**2
PKT045_STAGE1_OPERATIONAL_RESERVATION_BYTES = 64 * 1024**2
PKT045_STAGE1_FREE_DISK_RESERVE_BYTES = 10 * 1024**3
PKT045_STAGE1_FOREGROUND_SECONDS = 240 * 60 * 60
PKT045_MAX_CONCURRENT_GETS = 2
PKT045_CODE_PATHS = (
    "automation/forex_engine/edge_research/dukascopy_bi5.py",
    "automation/forex_engine/edge_research/dukascopy_acquisition.py",
    "automation/forex_engine/edge_research/data.py",
    "automation/forex_engine/edge_research/features.py",
    "automation/forex_engine/edge_research/execution.py",
    "automation/forex_engine/edge_research/research.py",
    "automation/forex_engine/edge_research/batch.py",
    "automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py",
    "automation/forex_engine/forex_control_baseline_rsi_filter_comparison_stage1_v1.py",
    "scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py",
)

# Original build-and-launch claim began 05:56:25Z. Amendments do not reset
# its six-hour ceiling. Counting owner-wait time too is conservative.
ORIGINAL_DEADLINE = datetime(2026, 9, 7, 11, 56, 25, tzinfo=timezone.utc)
CORRECTION_ID = "MEASUREMENT_AVAILABILITY_R1"
PARENT_ROOT = ".aios/staging/PKT_FOREX_044/first_launch_occ82_20260907"
PARENT_CONTRACT_SHA256 = "b215c8dfb6eb030cda3dcd025661e95070d7313bb7943fe36dcfeb16caadc7ab"
PARENT_INVALID_SHA256 = "2445b09d5daaba75b82ac1262c1797e090648d54a04adb745c245731b9537957"


def verify_correction_parent(root, cards):
    parent = root/PARENT_ROOT
    if (validation.sha256_file(parent/"contract.json") != PARENT_CONTRACT_SHA256 or
            validation.sha256_file(parent/"invalid_test.json") != PARENT_INVALID_SHA256):
        raise ValueError("CORRECTION_PARENT_EVIDENCE_CHANGED")
    original = json.loads((parent/"contract.json").read_bytes())
    if original["cards"] != cards:
        raise ValueError("CORRECTION_CHANGED_ECONOMIC_SPECIFICATION")
    return {"correction_id": CORRECTION_ID, "parent_root": PARENT_ROOT,
            "parent_contract_sha256": PARENT_CONTRACT_SHA256, "parent_invalid_sha256": PARENT_INVALID_SHA256,
            "new_strategy_specifications": 0,
            "measurement_rule": "UNAVAILABLE_MIDPOINT_DIAGNOSTIC_IS_NULL;_EXECUTABLE_PATH_GAP_REMAINS_FATAL;_NO_SUBSET_GROSS_ESTIMATE"}


def code_identity(root):
    return {p: validation.sha256_file(root/p) for p in CODE_PATHS}


def save_new(path, payload):
    encoded = (validation.pretty_json(payload)+"\n").encode("utf-8")
    if path.exists():
        if path.read_bytes() != encoded: raise ValueError("IMMUTABLE_BATCH_ARTIFACT_CONFLICT:"+path.name)
        return validation.sha256_bytes(encoded)
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return validation.sha256_bytes(encoded)


def resident_bytes():
    if os.name != "nt": raise ValueError("RESOURCE_MONITOR_NOT_AVAILABLE")
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [(key, ctypes.c_size_t) for key in (
            "peak", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
    result = Counters()
    result.cb = ctypes.sizeof(result)
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = ctypes.c_void_p
    read = ctypes.windll.psapi.GetProcessMemoryInfo
    read.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not read(process(), ctypes.byref(result), result.cb): raise ValueError("RESOURCE_MONITOR_FAILED")
    return result.working


def validate_test_receipt(root, receipt_path):
    receipt = json.loads(receipt_path.read_bytes())
    if receipt["code_identity"] != code_identity(root): raise ValueError("TESTED_CODE_CHANGED")
    report = root / receipt["junit_path"]
    if validation.sha256_file(report) != receipt["junit_sha256"]: raise ValueError("TEST_REPORT_CHANGED")
    suites = ET.parse(report).getroot()
    leaves = list(suites.iter("testcase"))
    if not leaves or any(list(case) and any(x.tag in {"failure", "error", "skipped"} for x in case) for case in leaves):
        raise ValueError("REQUIRED_TEST_FAILURE_OR_SKIP")
    classes = {case.get("classname", "") for case in leaves}
    if not all(any(name in cls for cls in classes) for name in (
        "test_features", "test_execution", "test_batch", "test_forex_edge_validation_pipeline_v1",
        "test_forex_factor_common_component_momentum_stage0_v1", "test_forex_high_throughput_edge_factory_v1")):
        raise ValueError("REQUIRED_REGRESSION_CHAIN_MISSING")
    return {"tests": len(leaves), "report_sha256": receipt["junit_sha256"]}


def freeze(root, output, test_receipt, *, correction=False):
    from scripts.forex_delivery.run_forex_control_baseline_rsi_filter_comparison_stage1_v1 import check_writer
    allowed = (root/".aios/staging/PKT_FOREX_044").resolve()
    output = output.resolve()
    if not output.is_relative_to(allowed) or output == allowed: raise ValueError("BATCH_OUTPUT_OUTSIDE_SCOPE")
    check_writer(json.loads((root/"automation/orchestration/locks/FILE_LOCK_REGISTRY.json").read_text(encoding="utf-8-sig")), output, datetime.now(timezone.utc))
    tests = validate_test_receipt(root, test_receipt)
    remaining_seconds = (ORIGINAL_DEADLINE-datetime.now(timezone.utc)).total_seconds()
    if remaining_seconds <= 0: raise ValueError("ORIGINAL_FOREGROUND_BUDGET_EXHAUSTED")
    corpus = root/".aios/runtime/forex_m5_immutable_corpus_v2"
    manifest = data.verify_corpus_manifest(corpus)
    memory = data.verify_runtime_contracts(root, stage0.first_wave_manifest()["cells"], require_pre_score=False)
    cards = research.specifications(manifest["eligible_pairs"])
    contract = {"schema": "AIOS_PKT044_EXECUTABLE_BATCH.v1", "packet_id": "PKT-FOREX-044",
        "worker": "EAST_OCC_82", "cards": cards, "code_identity": code_identity(root), "tests": tests,
        "budget": {"new_scored_specifications": 2, "reproductions": 1, "followup_proposals": 3,
                   "seconds": remaining_seconds, "absolute_deadline": ORIGINAL_DEADLINE.isoformat(),
                   "original_limit_seconds": 21600, "budget_not_reset": True,
                   "memory_bytes": 4*1024**3, "output_bytes": 1024**3},
        "selector": "EXISTING_CHECKED_HANDOFF_REPAIR_MISSING_EVIDENCE_FREEZE_COST_PRIORITY_THEN_CANDIDATE_ID",
        "data_access": "DEVELOPMENT_ONLY_2024_01_01_INCLUSIVE_2025_04_01_EXCLUSIVE",
        "independence": "REUSED_EXPLORATORY_DEVELOPMENT_ONLY",
        "starting_trial_summary": memory["pre_score_trial_memory"],
        "conversion_paths": research.conversion_paths(manifest["eligible_pairs"])}
    if correction:
        contract["measurement_correction"] = verify_correction_parent(root, cards)
    if output.exists(): raise ValueError("USE_RESUME_FOR_EXISTING_BATCH")
    output.mkdir(parents=True, exist_ok=False)
    save_new(output/"contract.json", contract)
    return contract, manifest


def status(output):
    contract_path, checkpoint = output/"contract.json", output/"checkpoint.json"
    if not contract_path.is_file(): raise ValueError("BATCH_CONTRACT_MISSING")
    contract = json.loads(contract_path.read_bytes())
    result = json.loads(checkpoint.read_bytes()) if checkpoint.is_file() else {"state": "FROZEN_NOT_STARTED"}
    digest = validation.sha256_file(contract_path)
    if result.get("contract_sha256", digest) != digest:
        raise ValueError("CHECKPOINT_CONTRACT_CHANGED")
    if result.get("state") == "BATCH_COMPLETE":
        for run in ("run1", "run2"):
            receipt = json.loads((output/run/"receipt.json").read_bytes())
            if any(validation.sha256_file(output/run/name) != sha for name, sha in receipt["artifacts"].items()):
                raise ValueError("COMPLETED_RUN_ARTIFACT_CHANGED")
        if validation.sha256_file(output/"handoff.json") != result["handoff_sha256"]:
            raise ValueError("COMPLETED_HANDOFF_CHANGED")
    return {"packet_id": contract["packet_id"], "contract_sha256": validation.sha256_file(contract_path), **result}


def execute(root, output, contract, manifest, *, resume=False):
    from scripts.forex_delivery import run_forex_factor_common_component_momentum_stage0_v1 as publisher
    from scripts.forex_delivery.run_forex_control_baseline_rsi_filter_comparison_stage1_v1 import check_writer
    if contract.get("packet_id") != "PKT-FOREX-044":
        raise ValueError("SUCCESSOR_SCORING_REQUIRES_CERTIFIED_CORPUS_AND_FUTURE_AUTHORITY")
    previous = status(output)
    if previous.get("state") == "BATCH_COMPLETE": return previous
    if previous.get("state") == "BLOCKED": raise ValueError("BLOCKED_BATCH_REQUIRES_DIAGNOSIS_NOT_BLIND_RETRY")
    if contract["code_identity"] != code_identity(root): raise ValueError("FROZEN_CODE_CHANGED")
    if contract["cards"] != research.specifications(manifest["eligible_pairs"]): raise ValueError("FROZEN_SCIENCE_CHANGED")
    if contract.get("measurement_correction") != (verify_correction_parent(root, contract["cards"]) if contract.get("measurement_correction") else None):
        raise ValueError("CORRECTION_CONTRACT_CHANGED")
    start = time.monotonic()
    used_before = previous.get("elapsed_seconds", 0.)
    peak = previous.get("peak_working_bytes", 0)
    registry = root/"automation/orchestration/locks/FILE_LOCK_REGISTRY.json"
    checkpoint = dict(previous)
    def check_limits():
        nonlocal peak
        check_writer(json.loads(registry.read_text(encoding="utf-8-sig")), output, datetime.now(timezone.utc))
        peak = max(peak, resident_bytes())
        if peak > contract["budget"]["memory_bytes"]: raise ValueError("BATCH_MEMORY_LIMIT")
        if used_before+time.monotonic()-start > contract["budget"]["seconds"]: raise ValueError("BATCH_TIME_LIMIT")
        if contract["budget"].get("absolute_deadline") and datetime.now(timezone.utc) >= datetime.fromisoformat(contract["budget"]["absolute_deadline"]):
            raise ValueError("ORIGINAL_FOREGROUND_BUDGET_EXHAUSTED")
        storage_root = root/".aios/staging/PKT_FOREX_044"
        if not storage_root.exists(): storage_root = output  # isolated fixture
        if sum(p.stat().st_size for p in storage_root.rglob("*") if p.is_file()) > contract["budget"]["output_bytes"]:
            raise ValueError("BATCH_STORAGE_LIMIT")
        if code_identity(root) != contract["code_identity"]: raise ValueError("FROZEN_CODE_CHANGED")
    def progress(stage, completed, total, details):
        checkpoint.update(state="RUNNING", stage=stage, completed=completed, total=total, details=details,
            elapsed_seconds=used_before+time.monotonic()-start, peak_working_bytes=peak,
            last_progress_utc=datetime.now(timezone.utc).isoformat(), resume="CHECK_CONTRACT_AND_RESUME_NO_DUPLICATE_TRIALS")
        validation.atomic_write(output/"checkpoint.json", (validation.pretty_json(checkpoint)+"\n").encode())
        print(json.dumps({"stage": stage, "completed": completed, "total": total, **details}), flush=True)
    touched = False
    def before_outcome():
        nonlocal touched
        if not touched:
            check_limits()
            publisher.publish_pkt044(output, contract["cards"], "OUTCOME_EXAMINED", validation.sha256_file(output/"contract.json"))
            save_new(output/"outcome_access.json", {"contract_sha256": validation.sha256_file(output/"contract.json"), "configurations": [c["candidate_id"] for c in contract["cards"]], "status": "OUTCOME_ACCESS_STARTED"})
            touched = True
    try:
        check_limits()
        corpus = root/".aios/runtime/forex_m5_immutable_corpus_v2"
        for run_number in (1, 2):
            run_root = output/f"run{run_number}"
            run_root.mkdir(exist_ok=True)
            receipt_path = run_root/"receipt.json"
            if receipt_path.exists():
                receipt = json.loads(receipt_path.read_bytes())
                if any(validation.sha256_file(run_root/name) != digest for name, digest in receipt["artifacts"].items()):
                    raise ValueError("COMPLETED_RUN_ARTIFACT_CHANGED")
                continue
            if any(run_root.iterdir()): raise ValueError("PARTIAL_RUN_OUTPUT_REQUIRES_CHECKED_RECOVERY")
            progress("RUN_START", run_number, 2, {"reproduction": run_number == 2})
            opportunities, tables, verification = research.prepare_inputs(corpus, manifest, progress, before_outcome, check_limits)
            result = research.measure_batch(opportunities, tables, contract["cards"], progress, check_limits)
            save_new(run_root/"scientific_result.json", result)
            save_new(run_root/"development_verification.json", verification)
            with (run_root/"opportunities.jsonl.gz").open("xb") as raw:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                    for item in opportunities:
                        compressed.write((validation.canonical_json(item)+"\n").encode("ascii"))
                raw.flush()
                os.fsync(raw.fileno())
            hashes = {name: validation.sha256_file(run_root/name) for name in ("scientific_result.json", "development_verification.json", "opportunities.jsonl.gz")}
            save_new(receipt_path, {"artifacts": hashes, "rows_read": sum(x["records"] for x in verification.values()), "validation_rows": 0, "holdout_rows": 0})
            del opportunities, tables, result
            check_limits()
        first = json.loads((output/"run1/receipt.json").read_bytes())
        second = json.loads((output/"run2/receipt.json").read_bytes())
        if first != second: raise ValueError("SCIENTIFIC_REPRODUCTION_MISMATCH")
        result = json.loads((output/"run1/scientific_result.json").read_bytes())
        index = json.loads((root/data.FINGERPRINT_INDEX_RELATIVE).read_bytes())
        artifacts = {str((output/"run1"/name).relative_to(root)).replace("\\", "/"): digest for name, digest in first["artifacts"].items()}
        reviewed = research.checked_handoff(result, contract["cards"], index, artifacts)
        handoff_hash = save_new(output/"handoff.json", reviewed)
        publication = publisher.publish_pkt044(output, contract["cards"], "VALID_TEST_REJECTED", handoff_hash)
        save_new(output/"publication.json", publication)
        check_limits()
        checkpoint.update(state="BATCH_COMPLETE", stage="AWAITING_APPROVAL", budget_remaining=0, handoff_sha256=handoff_hash,
            elapsed_seconds=used_before+time.monotonic()-start, peak_working_bytes=peak, reproduction="BYTE_IDENTICAL",
            selected_next_action=reviewed["review"]["selected_next_action"], publication=publication,
            final_holdout_access=False, verified_edge=False)
        validation.atomic_write(output/"checkpoint.json", (validation.pretty_json(checkpoint)+"\n").encode())
        return status(output)
    except Exception as error:
        checkpoint.update(state="BLOCKED", blocker=str(error), elapsed_seconds=used_before+time.monotonic()-start,
            peak_working_bytes=peak, market_outcome_access_started=touched or (output/"outcome_access.json").exists())
        if checkpoint["market_outcome_access_started"]:
            # Save unknown counts as unknown and route through the real checked
            # reviewer. The invalid original remains separate and immutable.
            try:
                artifacts = {str((output/"contract.json").relative_to(root)).replace("\\", "/"): validation.sha256_file(output/"contract.json")}
                records = research.invalid_handoff(contract["cards"], artifacts, error)
                index = json.loads((root/data.FINGERPRINT_INDEX_RELATIVE).read_bytes())
                review = research.handoff.review_batch(records, index)
                invalid_hash = save_new(output/"invalid_test.json", {"records": records, "review": review,
                    "failure_details": getattr(error, "details", {}), "blocker": str(error), "next_state": "AWAITING_APPROVAL"})
                publication = publisher.publish_pkt044(output, contract["cards"], "INVALID_TEST", invalid_hash)
                save_new(output/"invalid_publication.json", publication)
                checkpoint.update(invalid_test_sha256=invalid_hash, publication=publication,
                                  selected_next_action=review["selected_next_action"])
            except Exception as publication_error:
                checkpoint["invalid_handoff_publication_blocker"] = str(publication_error)
        validation.atomic_write(output/"checkpoint.json", (validation.pretty_json(checkpoint)+"\n").encode())
        # Outcome access was already durable even if no completed report exists.
        raise


def pkt045_code_identity(root: Path) -> dict[str, str]:
    """Hash only the scoped successor code used to build a local receipt."""
    return {path: validation.sha256_file(root / path) for path in PKT045_CODE_PATHS}


def _pkt045_tick_proof(root: Path) -> dict[str, object]:
    """Use the saved local same-record tick probe without contacting AWS."""
    probe = root / PKT045_TICK_PROBE_RELATIVE
    if not probe.is_file():
        raise ValueError("PKT045_SAVED_TICK_PROBE_MISSING")
    source_key = dukascopy_bi5.daily_tick_key("AUD_CAD", date(2024, 1, 2))
    payload = probe.read_bytes()
    first_ticks = dukascopy_bi5.decode_tick_bi5(
        payload, pair="AUD_CAD", trading_day=date(2024, 1, 2), source_key=source_key, price_scale=100_000,
    )
    second_ticks = dukascopy_bi5.decode_tick_bi5(
        payload, pair="AUD_CAD", trading_day=date(2024, 1, 2), source_key=source_key, price_scale=100_000,
    )
    if first_ticks != second_ticks:
        raise ValueError("PKT045_TICK_DECODE_NOT_DETERMINISTIC")
    first = dukascopy_bi5.normalize_paired_ticks_to_m5_with_derived_mid(first_ticks)
    second = dukascopy_bi5.normalize_paired_ticks_to_m5_with_derived_mid(second_ticks)
    if first != second or not first.bars:
        raise ValueError("PKT045_PAIRED_TICK_MID_PROOF_FAILED")
    rows = [
        {
            "timestamp": bar.timestamp.isoformat(), "bid": (bar.bid_open, bar.bid_high, bar.bid_low, bar.bid_close),
            "ask": (bar.ask_open, bar.ask_high, bar.ask_low, bar.ask_close),
            "mid": (bar.mid_open, bar.mid_high, bar.mid_low, bar.mid_close),
            "record_count": bar.source_record_count, "source_keys": bar.source_keys,
            "midpoint_method": bar.midpoint_method,
        }
        for bar in first.bars
    ]
    return {
        "status": "PASS",
        "source": str(PKT045_TICK_PROBE_RELATIVE).replace("\\", "/"),
        "source_sha256": validation.sha256_file(probe),
        "source_key": source_key,
        "pair": "AUD_CAD",
        "source_tick_count": len(first_ticks),
        "m5_bar_count": len(first.bars),
        "first_timestamp": first.bars[0].timestamp.isoformat(),
        "last_timestamp": first.bars[-1].timestamp.isoformat(),
        "scientific_rows_sha256": validation.sha256_value(rows),
        "midpoint_method": "PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION",
        "aws_requests": 0,
    }


def build_pkt045_preregistration(root: Path) -> dict[str, object]:
    """Build a deterministic, unscored PKT-045 receipt from local evidence.

    This intentionally does not instantiate an AWS client, create a corpus, or
    invoke an outcome/scoring function.  It is the boundary between a frozen
    successor specification and a later separately authorised acquisition.
    """
    pairs = tuple(data.certified_instrument_metadata())
    context = research.paired_tick_mid_successor_context(pairs)
    context_check = research.validate_paired_tick_mid_successor_context(context)
    tournament_check = data.validate_successor_preacquisition_contract(context)
    local_proof = _pkt045_tick_proof(root)
    requirement = dukascopy_acquisition.SourceSemanticsRequirement(
        strategy_specification_id=research.PKT045_EXPERIMENT_ID,
        required_pair_count=len(pairs),
        required_price_sides=("BID", "ASK"),
        midpoint_semantics="PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION",
        timestamp_granularity="TICK",
        candle_construction="PAIRED_TICKS_THEN_M5",
        activity_semantics="NOT_REQUIRED",
        preregistration_status="FROZEN",
    )
    semantic_gate = dukascopy_acquisition.evaluate_paired_tick_preacquisition_gate(
        requirement=requirement,
        mapped_pair_count=len(pairs),
        local_tick_proof_id=local_proof["scientific_rows_sha256"],
        local_tick_proof_passed=local_proof["status"] == "PASS",
    )
    if semantic_gate.semantic_contract_status != "PASS":
        raise ValueError("PKT045_SOURCE_SEMANTICS_GATE_FAILED")
    start = datetime.fromisoformat(research.PKT045_DEVELOPMENT_START)
    end = datetime.fromisoformat(research.PKT045_DEVELOPMENT_END)
    tick_plan = dukascopy_acquisition.plan_paired_tick_inventory(pairs=pairs, start=start, end=end)
    index = json.loads((root / data.FINGERPRINT_INDEX_RELATIVE).read_bytes())
    preregistration_handoff = research.handoff.review_preregistered_successor(context, index)
    if preregistration_handoff["execution_allowed"] or preregistration_handoff["market_trials_added"]:
        raise ValueError("PKT045_PREREGISTRATION_EXECUTION_ROUTE_FORBIDDEN")
    remaining = PKT045_OWNER_CUMULATIVE_COST_LIMIT_USD - PKT045_PRIOR_DUKASCOPY_SPEND_USD
    return {
        "schema": "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_MID_PREREGISTRATION_V1",
        "PACKET_ID": PKT045_PACKET_ID,
        "WORKER": PKT045_WORKER_ID,
        "LANE": "FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_PREREGISTRATION_STAGE0",
        "LOCK": "LOCK_EAST_FOREX_DUKASCOPY_PAIRED_TICK_MID_SUCCESSOR_PREREGISTRATION_STAGE0_OCC83",
        "PARENT_PACKET": research.PKT045_PARENT_PACKET_ID,
        "PARENT_OUTCOME": "MATERIAL_DATA_SEMANTICS_CHANGE",
        "EXPERIMENT_ID": research.PKT045_EXPERIMENT_ID,
        "SPECIFICATION_A_ID": research.PKT045_BASELINE_ID,
        "SPECIFICATION_B_ID": research.PKT045_CHALLENGER_ID,
        "FINGERPRINT_A": context["cards"][0]["fingerprint"],
        "FINGERPRINT_B": context["cards"][1]["fingerprint"],
        "DATA_SEMANTICS_VERSION": research.PKT045_DATA_SEMANTICS_VERSION,
        "SOURCE_REQUIREMENT_VERSION": research.PKT045_SOURCE_REQUIREMENT_VERSION,
        "PROVIDER": "DUKASCOPY",
        "SOURCE_TYPE": "PAIRED_TICK",
        "MID_FORMULA": "MID_T_EQUALS_BID_T_PLUS_ASK_T_DIVIDED_BY_2_SAME_SOURCE_RECORD_ONLY",
        "M5_AGGREGATION_RULE": "FIRST_MAX_MIN_LAST_MID_T_COMPLETED_UTC_M5_ONLY",
        "EXECUTION_SIDE_RULE": "LONG_ASK_BID_SHORT_BID_ASK_STOP_AND_EXIT_SOURCE_BACKED_SIDE_CORRECT",
        "TARGET_PAIR_COUNT": len(pairs),
        "PAIR_LIST_HASH": validation.sha256_value(list(pairs)),
        "TARGET_DEVELOPMENT_START": research.PKT045_DEVELOPMENT_START,
        "TARGET_DEVELOPMENT_END": research.PKT045_DEVELOPMENT_END,
        "SUPERTREND_VERSION": "EXISTING_ATR3_MULTIPLIER2_TWO_CLOSE_CONFIRMATION",
        "ATR_VERSION": "EXISTING_WILDER_ATR3_COMPLETED_M5",
        "RSI_VERSION": "REPAIRED_WILDER_RSI14_COMPLETED_M5",
        "RSI_THRESHOLD": "LONG_LE70_SHORT_GE30_MISSING_FILTERED",
        "SOURCE_SEMANTICS_GATE_VERSION": "AIOS_PKT045_PAIRED_TICK_PREACQUISITION_SEMANTICS_GATE_V1",
        "NO_AWS_ACCESS": True,
        "NO_ACQUISITION": True,
        "NO_SCORING": True,
        "NO_RESEARCH_MEMORY_PUBLICATION": True,
        "CONTEXT_CHECK": context_check,
        "TOURNAMENT_PREACQUISITION_CHECK": tournament_check,
        "LOCAL_TICK_PROOF": local_proof,
        "SOURCE_SEMANTICS_GATE": dukascopy_acquisition.paired_tick_preacquisition_gate_payload(
            semantic_gate, requirement=requirement,
        ),
        "EXPECTED_TICK_INVENTORY": dukascopy_acquisition.paired_tick_inventory_plan_payload(tick_plan),
        "COST_PLAN": {
            "PRIOR_DUKASCOPY_SPEND_USD": PKT045_PRIOR_DUKASCOPY_SPEND_USD,
            "OWNER_CUMULATIVE_COST_LIMIT_USD": PKT045_OWNER_CUMULATIVE_COST_LIMIT_USD,
            "THEORETICAL_REMAINING_CEILING_USD": remaining,
            "STATUS": "NOT_RUN_NO_AWS_AUTHORITY_CURRENT_PRICING_AND_INVENTORY_REQUIRED",
        },
        "FACTORY_HANDOFF": preregistration_handoff,
        "CODE_IDENTITY": pkt045_code_identity(root),
    }


def preregister_pkt045(root: Path, output: Path) -> dict[str, object]:
    """Write two identical immutable PKT-045 preregistration receipts."""
    allowed = (root / PKT045_STAGING_RELATIVE).resolve()
    output = output.resolve()
    if not output.is_relative_to(allowed) or output == allowed:
        raise ValueError("PKT045_OUTPUT_OUTSIDE_SCOPE")
    first = build_pkt045_preregistration(root)
    second = build_pkt045_preregistration(root)
    first_bytes = dukascopy_acquisition.deterministic_json_bytes(first)
    second_bytes = dukascopy_acquisition.deterministic_json_bytes(second)
    if first_bytes != second_bytes:
        raise ValueError("PKT045_PREREGISTRATION_NOT_DETERMINISTIC")
    run1 = dukascopy_acquisition.write_new_deterministic_json(output / "PREREGISTRATION_RECEIPT_RUN1.json", first)
    run2 = dukascopy_acquisition.write_new_deterministic_json(output / "PREREGISTRATION_RECEIPT_RUN2.json", second)
    if run1 != run2:
        raise ValueError("PKT045_PREREGISTRATION_RECEIPT_HASH_MISMATCH")
    receipt = {
        "schema": "AIOS_PKT045_PREREGISTRATION_RECEIPT_V1",
        "packet_id": PKT045_PACKET_ID,
        "run1_sha256": run1,
        "run2_sha256": run2,
        "scientific_identity_sha256": run1,
        "status": "PASS_PREACQUISITION_ONLY",
        "next_state": "AWAITING_ACQUISITION_AUTHORITY",
        "aws_requests": 0,
        "market_trials_added": 0,
        "research_memory_mutation": False,
    }
    receipt_hash = dukascopy_acquisition.write_new_deterministic_json(output / "PREREGISTRATION_RECEIPT.json", receipt)
    return {**receipt, "receipt_sha256": receipt_hash, "output": str(output)}


def pkt045_status(root: Path, output: Path) -> dict[str, object]:
    """Check immutable local preregistration receipts without a scoring route."""
    output = output.resolve()
    expected = ("PREREGISTRATION_RECEIPT_RUN1.json", "PREREGISTRATION_RECEIPT_RUN2.json", "PREREGISTRATION_RECEIPT.json")
    if any(not (output / name).is_file() for name in expected):
        raise ValueError("PKT045_PREREGISTRATION_RECEIPT_MISSING")
    run1 = (output / expected[0]).read_bytes()
    run2 = (output / expected[1]).read_bytes()
    receipt = json.loads((output / expected[2]).read_bytes())
    if run1 != run2 or receipt.get("run1_sha256") != validation.sha256_bytes(run1):
        raise ValueError("PKT045_PREREGISTRATION_RECEIPT_CHANGED")
    if receipt.get("status") != "PASS_PREACQUISITION_ONLY" or receipt.get("market_trials_added") != 0:
        raise ValueError("PKT045_PREREGISTRATION_STATUS_INVALID")
    return {"packet_id": PKT045_PACKET_ID, "status": receipt["status"], "receipt_sha256": validation.sha256_file(output / expected[2]),
            "next_state": receipt["next_state"], "execution_allowed": False, "market_trials_added": 0}


def _pkt045_stage1_output(root: Path, output: Path) -> Path:
    expected = (root / PKT045_STAGE1_RELATIVE).resolve()
    resolved = output.resolve()
    if resolved != expected:
        raise ValueError("PKT045_STAGE1_OUTPUT_ROOT_MISMATCH")
    return resolved


def _pkt045_stage1_preregistration(root: Path) -> tuple[dict[str, Any], tuple[str, ...], dict[str, Any]]:
    """Load and revalidate the sealed Stage 0 science without opening prices.

    The pair target is reconstructed only from Stage 0's immutable expected
    tick keys.  That avoids reopening the old corpus or protected historical
    sources merely to learn the 58 pair identifiers.
    """
    source = root / PKT045_STAGE0_RECEIPT_RELATIVE
    if not source.is_file() or validation.sha256_file(source) != PKT045_STAGE0_RECEIPT_SHA256:
        raise ValueError("PKT045_STAGE1_PREREGISTRATION_RECEIPT_MISMATCH")
    try:
        receipt = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("PKT045_STAGE1_PREREGISTRATION_RECEIPT_INVALID") from exc
    if (
        receipt.get("PACKET_ID") != PKT045_PACKET_ID
        or receipt.get("EXPERIMENT_ID") != research.PKT045_EXPERIMENT_ID
        or receipt.get("NO_AWS_ACCESS") is not True
        or receipt.get("NO_SCORING") is not True
        or receipt.get("LOCAL_TICK_PROOF", {}).get("status") != "PASS"
    ):
        raise ValueError("PKT045_STAGE1_PREREGISTRATION_IDENTITY_INVALID")
    keys = receipt.get("EXPECTED_TICK_INVENTORY", {}).get("OBJECT_KEYS")
    if not isinstance(keys, list) or not keys:
        raise ValueError("PKT045_STAGE1_EXPECTED_TICK_KEYS_MISSING")
    try:
        pairs = tuple(sorted({dukascopy_bi5.canonical_pair(str(key).split("/", 1)[0]) for key in keys}))
    except dukascopy_bi5.DukascopyBi5Error as exc:
        raise ValueError("PKT045_STAGE1_EXPECTED_TICK_PAIR_INVALID") from exc
    if len(pairs) != research.PKT045_TARGET_PAIR_COUNT or receipt.get("TARGET_PAIR_COUNT") != len(pairs):
        raise ValueError("PKT045_STAGE1_PAIR_TARGET_MISMATCH")
    if validation.sha256_value(list(pairs)) != receipt.get("PAIR_LIST_HASH"):
        raise ValueError("PKT045_STAGE1_PAIR_LIST_HASH_MISMATCH")
    plan = dukascopy_acquisition.plan_paired_tick_inventory(
        pairs=pairs,
        start=datetime.fromisoformat(research.PKT045_DEVELOPMENT_START),
        end=datetime.fromisoformat(research.PKT045_DEVELOPMENT_END),
    )
    if list(plan.objects) != keys:
        raise ValueError("PKT045_STAGE1_EXPECTED_TICK_PLAN_CHANGED")
    context = research.paired_tick_mid_successor_context(pairs)
    checked = research.validate_paired_tick_mid_successor_context(context)
    if [card["fingerprint"] for card in context["cards"]] != [receipt.get("FINGERPRINT_A"), receipt.get("FINGERPRINT_B")]:
        raise ValueError("PKT045_STAGE1_FINGERPRINT_MISMATCH")
    requirement = dukascopy_acquisition.SourceSemanticsRequirement(
        strategy_specification_id=research.PKT045_EXPERIMENT_ID,
        required_pair_count=len(pairs),
        required_price_sides=("BID", "ASK"),
        midpoint_semantics="PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION",
        timestamp_granularity="TICK",
        candle_construction="PAIRED_TICKS_THEN_M5",
        activity_semantics="NOT_REQUIRED",
        preregistration_status="FROZEN",
    )
    semantic_gate = dukascopy_acquisition.evaluate_paired_tick_preacquisition_gate(
        requirement=requirement,
        mapped_pair_count=len(pairs),
        local_tick_proof_id=str(receipt["LOCAL_TICK_PROOF"].get("scientific_rows_sha256", "")),
        local_tick_proof_passed=receipt["LOCAL_TICK_PROOF"].get("status") == "PASS",
    )
    if semantic_gate.semantic_contract_status != "PASS":
        raise ValueError("PKT045_STAGE1_SOURCE_SEMANTICS_GATE_FAILED")
    return receipt, pairs, {
        "context_check": checked,
        "requirement": requirement,
        "semantic_gate": semantic_gate,
        "expected_plan": plan,
    }


def pkt045_stage1_pre_inventory_cost_guard(
    root: Path,
    *,
    pricing: dukascopy_acquisition.CostBasis,
    max_pages_per_prefix: int = 1,
    uncertainty_reserve_usd: float = 0.01,
) -> dict[str, Any]:
    """Fail closed before the first remote P45 inventory request.

    It budgets every pair/month list call at the explicit finite page cap.
    No free allowance is presumed, and a page-cap breach later stops rather
    than silently expanding the paid inventory scan.
    """
    if isinstance(max_pages_per_prefix, bool) or max_pages_per_prefix <= 0:
        raise ValueError("PKT045_STAGE1_LIST_PAGE_LIMIT_INVALID")
    if not isinstance(uncertainty_reserve_usd, (int, float)) or uncertainty_reserve_usd < 0:
        raise ValueError("PKT045_STAGE1_INVENTORY_RESERVE_INVALID")
    receipt, pairs, prepared = _pkt045_stage1_preregistration(root)
    prefix_count = len(dukascopy_acquisition.month_prefixes(
        pairs,
        datetime.fromisoformat(research.PKT045_DEVELOPMENT_START),
        datetime.fromisoformat(research.PKT045_DEVELOPMENT_END),
    ))
    upper_list_requests = prefix_count * max_pages_per_prefix
    request_cost = upper_list_requests / 1_000 * pricing.list_per_1000_usd
    estimate = request_cost + uncertainty_reserve_usd
    return {
        "schema": "AIOS_PKT045_PRE_INVENTORY_COST_GUARD_V1",
        "PACKET_ID": PKT045_PACKET_ID,
        "EXPERIMENT_ID": research.PKT045_EXPERIMENT_ID,
        "STAGE0_RECEIPT_SHA256": validation.sha256_file(root / PKT045_STAGE0_RECEIPT_RELATIVE),
        "PAIR_COUNT": len(pairs),
        "PAIR_MONTH_PREFIX_COUNT": prefix_count,
        "MAX_PAGES_PER_PREFIX": max_pages_per_prefix,
        "MAX_LIST_REQUESTS": upper_list_requests,
        "LIST_REQUEST_COST_USD": request_cost,
        "UNCERTAINTY_RESERVE_USD": float(uncertainty_reserve_usd),
        "CONSERVATIVE_INVENTORY_COST_USD": estimate,
        "INVENTORY_ADDITIONAL_LIMIT_USD": PKT045_STAGE1_INVENTORY_ADDITIONAL_LIMIT_USD,
        "AWS_PRICE_SOURCE": pricing.price_source,
        "FREE_ALLOWANCE_ASSUMPTION": pricing.free_allowance_assumption,
        "SOURCE_SEMANTICS_GATE": prepared["semantic_gate"].semantic_contract_status,
        "COST_GATE": "PASS" if estimate <= PKT045_STAGE1_INVENTORY_ADDITIONAL_LIMIT_USD else "FAIL",
        "AWS_REQUESTS_MADE": 0,
        "NO_ACQUISITION": True,
        "NO_SCORING": True,
    }


def pkt045_stage1_inventory_and_cost(
    root: Path,
    output: Path,
    *,
    pricing: dukascopy_acquisition.CostBasis,
    client: dukascopy_acquisition.AwsRequesterPaysClient | None = None,
    max_pages_per_prefix: int = 1,
    uncertainty_reserve_usd: float = 0.01,
) -> dict[str, Any]:
    """Run the authorized inventory/cost phase, never acquisition or scoring."""
    stage_root = _pkt045_stage1_output(root, output)
    guard = pkt045_stage1_pre_inventory_cost_guard(
        root,
        pricing=pricing,
        max_pages_per_prefix=max_pages_per_prefix,
        uncertainty_reserve_usd=uncertainty_reserve_usd,
    )
    if guard["COST_GATE"] != "PASS":
        raise ValueError("PKT045_STAGE1_PRE_INVENTORY_COST_GATE_FAILED")
    receipt, pairs, prepared = _pkt045_stage1_preregistration(root)
    dukascopy_acquisition.write_new_deterministic_json(
        stage_root / "pricing" / "PKT045_PRE_INVENTORY_COST_GUARD.json", guard,
    )
    checkpoint_root = stage_root / "checkpoints" / "inventory"
    inventory, progress = dukascopy_acquisition.collect_paired_tick_inventory_from_aws(
        pairs=pairs,
        start=datetime.fromisoformat(research.PKT045_DEVELOPMENT_START),
        end=datetime.fromisoformat(research.PKT045_DEVELOPMENT_END),
        checkpoint_root=checkpoint_root,
        client=client,
        max_pages_per_prefix=max_pages_per_prefix,
    )
    actual_list_requests = dukascopy_acquisition.paired_tick_inventory_list_request_count(
        pairs=pairs,
        start=datetime.fromisoformat(research.PKT045_DEVELOPMENT_START),
        end=datetime.fromisoformat(research.PKT045_DEVELOPMENT_END),
        checkpoint_root=checkpoint_root,
    )
    inventory_payload = dukascopy_acquisition.paired_tick_inventory_payload(inventory)
    inventory_hash = dukascopy_acquisition.write_new_deterministic_json(
        stage_root / "inventory" / "PKT045_PAIRED_TICK_OBJECT_INVENTORY.json", inventory_payload,
    )
    cost_gate = dukascopy_acquisition.build_paired_tick_cost_gate(
        inventory=inventory,
        semantics_gate=prepared["semantic_gate"],
        mapped_pair_count=len(pairs),
        total_list_requests_actual=actual_list_requests,
        prior_spend_estimate_usd=PKT045_PRIOR_DUKASCOPY_SPEND_USD,
        pricing=pricing,
        retry_and_uncertainty_reserve_usd=uncertainty_reserve_usd,
        owner_limit_usd=PKT045_OWNER_CUMULATIVE_COST_LIMIT_USD,
    )
    cost_payload = dukascopy_acquisition.paired_tick_cost_gate_payload(cost_gate, pricing)
    cost_payload.update({
        "PRIOR_SPEND_ESTIMATE_USD": PKT045_PRIOR_DUKASCOPY_SPEND_USD,
        "INVENTORY_COST_WITHIN_ADDITIONAL_LIMIT": guard["COST_GATE"] == "PASS",
        "INVENTORY_ARTIFACT_SHA256": inventory_hash,
        "ACTUAL_LIST_REQUESTS": actual_list_requests,
        "NEW_GET_REQUESTS": 0,
        "NO_ACQUISITION": True,
        "NO_SCORING": True,
    })
    cost_hash = dukascopy_acquisition.write_new_deterministic_json(
        stage_root / "pricing" / "PKT045_DUKASCOPY_TICK_COST_GATE.json", cost_payload,
    )
    result = {
        "schema": "AIOS_PKT045_STAGE1_INVENTORY_AND_COST_RECEIPT_V1",
        "PACKET_ID": PKT045_PACKET_ID,
        "WORKER": PKT045_STAGE1_WORKER_ID,
        "LANE": PKT045_STAGE1_LANE,
        "LOCK": PKT045_STAGE1_LOCK_ID,
        "STAGE0_RECEIPT_SHA256": validation.sha256_file(root / PKT045_STAGE0_RECEIPT_RELATIVE),
        "PAIR_COUNT": len(pairs),
        "SOURCE_SEMANTICS_GATE": prepared["semantic_gate"].semantic_contract_status,
        "INVENTORY_PROGRESS": progress,
        "INVENTORY_SHA256": inventory_hash,
        "COST_GATE_SHA256": cost_hash,
        "COST_GATE": cost_gate.cost_gate,
        "NEXT_STATE": (
            "AWAITING_ACQUISITION_AND_CERTIFICATION" if cost_gate.cost_gate == "PASS"
            else "BLOCKED_CUMULATIVE_COST_LIMIT"
        ),
        "AWS_REQUESTS_MADE": actual_list_requests,
        "RAW_OBJECTS_DOWNLOADED": 0,
        "MARKET_TRIALS_ADDED": 0,
        "RESEARCH_MEMORY_MUTATION": False,
    }
    dukascopy_acquisition.write_new_deterministic_json(
        stage_root / "receipts" / "PKT045_STAGE1_INVENTORY_AND_COST_RECEIPT.json", result,
    )
    return result


def pkt045_stage1_status(root: Path, output: Path) -> dict[str, Any]:
    """Read local Stage 1 evidence; it never invokes AWS or a scoring path."""
    stage_root = _pkt045_stage1_output(root, output)
    receipt_path = stage_root / "receipts" / "PKT045_STAGE1_INVENTORY_AND_COST_RECEIPT.json"
    if not receipt_path.is_file():
        return {
            "packet_id": PKT045_PACKET_ID,
            "stage": 1,
            "status": "AWAITING_INVENTORY_AND_COST_GATE",
            "aws_requests": 0,
            "acquisition_allowed": False,
            "scoring_allowed": False,
        }
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("PACKET_ID") != PKT045_PACKET_ID or receipt.get("MARKET_TRIALS_ADDED") != 0:
        raise ValueError("PKT045_STAGE1_STATUS_RECEIPT_INVALID")
    return {
        "packet_id": PKT045_PACKET_ID,
        "stage": 1,
        "status": receipt.get("NEXT_STATE"),
        "cost_gate": receipt.get("COST_GATE"),
        "aws_requests": receipt.get("AWS_REQUESTS_MADE"),
        "acquisition_allowed": receipt.get("COST_GATE") == "PASS",
        "scoring_allowed": False,
        "market_trials_added": 0,
        "receipt_sha256": validation.sha256_file(receipt_path),
    }


def _pkt045_stage1_pricing(stage_root: Path) -> dukascopy_acquisition.CostBasis:
    """Read the sealed first-party pricing input; never assume free transfer."""
    path = stage_root / "pricing" / "AWS_S3_EU_WEST_1_STANDARD_PRICING_20260908.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("PKT045_STAGE1_PRICING_BASIS_MISSING_OR_INVALID") from exc
    required = (
        "LIST_PER_1000_USD", "GET_PER_1000_USD", "HEAD_PER_1000_USD",
        "RETRIEVAL_PER_GB_USD", "TRANSFER_PER_GB_USD", "AWS_PRICE_SOURCE",
        "SOURCE_RETRIEVED_AT", "FREE_ALLOWANCE_ASSUMPTION",
    )
    if any(key not in payload for key in required):
        raise ValueError("PKT045_STAGE1_PRICING_BASIS_INCOMPLETE")
    return dukascopy_acquisition.CostBasis(
        list_per_1000_usd=float(payload["LIST_PER_1000_USD"]),
        get_per_1000_usd=float(payload["GET_PER_1000_USD"]),
        head_per_1000_usd=float(payload["HEAD_PER_1000_USD"]),
        retrieval_per_gb_usd=float(payload["RETRIEVAL_PER_GB_USD"]),
        transfer_per_gb_usd=float(payload["TRANSFER_PER_GB_USD"]),
        price_source=str(payload["AWS_PRICE_SOURCE"]),
        retrieved_at_utc=str(payload["SOURCE_RETRIEVED_AT"]),
        free_allowance_assumption=str(payload["FREE_ALLOWANCE_ASSUMPTION"]),
    )


def _pkt045_stage1_inventory_and_cost(root: Path, stage_root: Path):
    """Rebuild the exact local gates from sealed evidence, without AWS I/O."""
    stage_root = _pkt045_stage1_output(root, stage_root)
    receipt_path = stage_root / "receipts" / "PKT045_STAGE1_INVENTORY_AND_COST_RECEIPT.json"
    inventory_path = stage_root / "inventory" / "PKT045_PAIRED_TICK_OBJECT_INVENTORY.json"
    cost_path = stage_root / "pricing" / "PKT045_DUKASCOPY_TICK_COST_GATE.json"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        saved_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        saved_cost = json.loads(cost_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("PKT045_STAGE1_INVENTORY_OR_COST_EVIDENCE_MISSING") from exc
    if (
        receipt.get("PACKET_ID") != PKT045_PACKET_ID
        or receipt.get("INVENTORY_SHA256") != validation.sha256_file(inventory_path)
        or receipt.get("COST_GATE_SHA256") != validation.sha256_file(cost_path)
        or receipt.get("COST_GATE") != "PASS"
    ):
        raise ValueError("PKT045_STAGE1_INVENTORY_OR_COST_RECEIPT_MISMATCH")
    _stage0, pairs, prepared = _pkt045_stage1_preregistration(root)
    inventory = dukascopy_acquisition.load_paired_tick_inventory_from_checkpoints(
        pairs=pairs,
        start=datetime.fromisoformat(research.PKT045_DEVELOPMENT_START),
        end=datetime.fromisoformat(research.PKT045_DEVELOPMENT_END),
        checkpoint_root=stage_root / "checkpoints" / "inventory",
    )
    if saved_inventory != dukascopy_acquisition.paired_tick_inventory_payload(inventory):
        raise ValueError("PKT045_STAGE1_SEALED_TICK_INVENTORY_CHANGED")
    actual_list_requests = dukascopy_acquisition.paired_tick_inventory_list_request_count(
        pairs=pairs,
        start=datetime.fromisoformat(research.PKT045_DEVELOPMENT_START),
        end=datetime.fromisoformat(research.PKT045_DEVELOPMENT_END),
        checkpoint_root=stage_root / "checkpoints" / "inventory",
    )
    pricing = _pkt045_stage1_pricing(stage_root)
    cost = dukascopy_acquisition.build_paired_tick_cost_gate(
        inventory=inventory,
        semantics_gate=prepared["semantic_gate"],
        mapped_pair_count=len(pairs),
        total_list_requests_actual=actual_list_requests,
        prior_spend_estimate_usd=PKT045_PRIOR_DUKASCOPY_SPEND_USD,
        pricing=pricing,
        retry_and_uncertainty_reserve_usd=0.01,
        owner_limit_usd=PKT045_OWNER_CUMULATIVE_COST_LIMIT_USD,
    )
    if any(saved_cost.get(key) != value for key, value in asdict(cost).items()):
        raise ValueError("PKT045_STAGE1_SEALED_COST_GATE_CHANGED")
    if (
        saved_cost.get("AWS_PRICE_SOURCE") != pricing.price_source
        or saved_cost.get("SOURCE_RETRIEVED_AT") != pricing.retrieved_at_utc
        or saved_cost.get("FREE_ALLOWANCE_ASSUMPTION") != pricing.free_allowance_assumption
        or saved_cost.get("ACTUAL_LIST_REQUESTS") != actual_list_requests
        or saved_cost.get("INVENTORY_ARTIFACT_SHA256") != validation.sha256_file(inventory_path)
    ):
        raise ValueError("PKT045_STAGE1_SEALED_PRICING_OR_LISTING_CHANGED")
    gate = dukascopy_acquisition.authorize_paired_tick_acquisition(
        preacquisition_gate=prepared["semantic_gate"], inventory=inventory, cost_gate=cost,
    )
    return receipt, pairs, prepared, inventory, pricing, cost, gate


def _pkt045_directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


def pkt045_stage1_resource_gate(
    root: Path, output: Path, inventory, *, in_flight_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Check the Stage 1 disk/output ceilings before a new raw GET or pair write."""
    stage_root = _pkt045_stage1_output(root, output)
    raw_root = stage_root / "raw_ticks"
    receipt_root = stage_root / "receipts"
    completed = dukascopy_acquisition.paired_tick_completed_raw_receipts(
        inventory=inventory, raw_root=raw_root, receipt_root=receipt_root,
    )
    completed_keys = {item["SOURCE"]["OBJECT_KEY"] for item in completed}
    expected_raw = {dukascopy_acquisition.raw_object_path(raw_root, source).resolve() for source in inventory.objects}
    if raw_root.exists():
        for item in raw_root.rglob("*"):
            item_resolved = item.resolve()
            expected_partial = (
                item.is_file()
                and item.name.endswith(".part")
                and item.with_name(item.name[:-len(".part")]).resolve() in expected_raw
            )
            if item.is_file() and item_resolved not in expected_raw and not expected_partial:
                raise ValueError("PKT045_STAGE1_RAW_OBJECT_OUTSIDE_SEALED_INVENTORY")
    in_flight_keys = in_flight_keys or set()
    for source in inventory.objects:
        raw_path = dukascopy_acquisition.raw_object_path(raw_root, source)
        if raw_path.exists() and source.key not in completed_keys and source.key not in in_flight_keys:
            raise ValueError("PKT045_STAGE1_UNRECEIPTED_RAW_OBJECT_PRESENT")
    completed_bytes = sum(int(item["SOURCE"]["LISTED_SIZE"]) for item in completed)
    if completed_bytes > inventory.total_listed_bytes:
        raise ValueError("PKT045_STAGE1_RAW_BYTES_EXCEED_INVENTORY")
    stage_bytes = _pkt045_directory_bytes(stage_root)
    corpus_bytes = _pkt045_directory_bytes(stage_root / "corpus_m5")
    remaining_raw = inventory.total_listed_bytes - completed_bytes
    remaining_corpus_reservation = max(PKT045_STAGE1_CORPUS_RESERVATION_BYTES - corpus_bytes, 0)
    additional = remaining_raw + remaining_corpus_reservation + PKT045_STAGE1_OPERATIONAL_RESERVATION_BYTES
    projected_stage_bytes = stage_bytes + additional
    free_bytes = shutil.disk_usage(stage_root).free
    return {
        "schema": "AIOS_PKT045_STAGE1_RESOURCE_GATE_V1",
        "OUTPUT_LIMIT_BYTES": PKT045_STAGE1_OUTPUT_LIMIT_BYTES,
        "STAGE_BYTES_CURRENT": stage_bytes,
        "RAW_OBJECTS_RECEIPTED": len(completed),
        "RAW_BYTES_RECEIPTED": completed_bytes,
        "RAW_BYTES_REMAINING": remaining_raw,
        "CORPUS_RESERVATION_BYTES": PKT045_STAGE1_CORPUS_RESERVATION_BYTES,
        "CORPUS_BYTES_CURRENT": corpus_bytes,
        "OPERATIONAL_RESERVATION_BYTES": PKT045_STAGE1_OPERATIONAL_RESERVATION_BYTES,
        "PROJECTED_STAGE_BYTES": projected_stage_bytes,
        "FREE_BYTES_CURRENT": free_bytes,
        "FREE_DISK_RESERVE_BYTES": PKT045_STAGE1_FREE_DISK_RESERVE_BYTES,
        "RESOURCE_GATE": "PASS" if (
            projected_stage_bytes <= PKT045_STAGE1_OUTPUT_LIMIT_BYTES
            and free_bytes - additional >= PKT045_STAGE1_FREE_DISK_RESERVE_BYTES
        ) else "FAIL",
    }


def _pkt045_stage1_check_writer(root: Path, output: Path) -> None:
    from scripts.forex_delivery.run_forex_control_baseline_rsi_filter_comparison_stage1_v1 import check_writer
    registry = json.loads((root / "automation/orchestration/locks/FILE_LOCK_REGISTRY.json").read_text(encoding="utf-8-sig"))
    check_writer(
        registry, output, datetime.now(timezone.utc), lock_id=PKT045_STAGE1_LOCK_ID,
        worker_id=PKT045_STAGE1_WORKER_ID, packet_id=PKT045_PACKET_ID,
    )


def freeze_pkt045_stage1(root: Path, output: Path) -> dict[str, Any]:
    """Seal the passed local gates and source code before the first paid GET."""
    stage_root = _pkt045_stage1_output(root, output)
    _pkt045_stage1_check_writer(root, stage_root)
    _receipt, pairs, prepared, inventory, _pricing, cost, gate = _pkt045_stage1_inventory_and_cost(root, stage_root)
    resources = pkt045_stage1_resource_gate(root, stage_root, inventory)
    if resources["RESOURCE_GATE"] != "PASS":
        raise ValueError("PKT045_STAGE1_RESOURCE_GATE_FAILED")
    metadata = pkt045_data.dukascopy_fx_tick_metadata(pairs)
    context = research.paired_tick_mid_successor_context(pairs)
    research.validate_paired_tick_mid_successor_context(context)
    contract = {
        "schema": "AIOS_PKT045_STAGE1_ACQUISITION_CONTRACT_V1",
        "PACKET_ID": PKT045_PACKET_ID,
        "WORKER": PKT045_STAGE1_WORKER_ID,
        "LANE": PKT045_STAGE1_LANE,
        "LOCK": PKT045_STAGE1_LOCK_ID,
        "EXPERIMENT_ID": research.PKT045_EXPERIMENT_ID,
        "STAGE0_RECEIPT_SHA256": validation.sha256_file(root / PKT045_STAGE0_RECEIPT_RELATIVE),
        "CARDS": context["cards"],
        "SOURCE_SEMANTICS_GATE": asdict(prepared["semantic_gate"]),
        "ACQUISITION_GATE": asdict(gate),
        "INVENTORY_SHA256": validation.sha256_file(stage_root / "inventory" / "PKT045_PAIRED_TICK_OBJECT_INVENTORY.json"),
        "COST_GATE_SHA256": validation.sha256_file(stage_root / "pricing" / "PKT045_DUKASCOPY_TICK_COST_GATE.json"),
        "SOURCE_METADATA": metadata,
        "SOURCE_METADATA_SHA256": validation.sha256_value(metadata),
        "RESOURCE_GATE": {
            "OUTPUT_LIMIT_BYTES": PKT045_STAGE1_OUTPUT_LIMIT_BYTES,
            "CORPUS_RESERVATION_BYTES": PKT045_STAGE1_CORPUS_RESERVATION_BYTES,
            "OPERATIONAL_RESERVATION_BYTES": PKT045_STAGE1_OPERATIONAL_RESERVATION_BYTES,
            "FREE_DISK_RESERVE_BYTES": PKT045_STAGE1_FREE_DISK_RESERVE_BYTES,
            "STATUS": resources["RESOURCE_GATE"],
        },
        "CODE_IDENTITY": pkt045_code_identity(root),
        "NO_PROTECTED_DATA_ACCESS": True,
        "NO_TRADING": True,
        "SCORING_STATUS": "BLOCKED_AWAITING_CERTIFIED_CORPUS",
    }
    # Compare the JSON representation, not Python tuple/list implementation
    # details, so revalidation is byte-stable across process resumes.
    contract = json.loads(validation.pretty_json(contract))
    candidate = (validation.pretty_json(contract) + "\n").encode("utf-8")
    base = stage_root / "receipts" / "PKT045_STAGE1_ACQUISITION_CONTRACT.json"
    path = base
    if path.exists() and path.read_bytes() != candidate:
        version = 2
        while True:
            path = stage_root / "receipts" / f"PKT045_STAGE1_ACQUISITION_CONTRACT_V{version}.json"
            if not path.exists() or path.read_bytes() == candidate:
                break
            version += 1
    digest = save_new(path, contract)
    return {**contract, "CONTRACT_SHA256": digest}


def _load_pkt045_stage1_contract(root: Path, output: Path) -> dict[str, Any]:
    stage_root = _pkt045_stage1_output(root, output)
    candidates = list(stage_root.glob("receipts/PKT045_STAGE1_ACQUISITION_CONTRACT*.json"))
    if not candidates:
        path = stage_root / "receipts" / "PKT045_STAGE1_ACQUISITION_CONTRACT.json"
    else:
        def contract_version(candidate: Path) -> int:
            stem = candidate.stem
            return int(stem.rsplit("_V", 1)[1]) if "_V" in stem else 1
        path = max(candidates, key=contract_version)
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("PKT045_STAGE1_ACQUISITION_CONTRACT_MISSING") from exc
    rebuilt = freeze_pkt045_stage1(root, stage_root)
    if contract != {key: value for key, value in rebuilt.items() if key != "CONTRACT_SHA256"}:
        raise ValueError("PKT045_STAGE1_ACQUISITION_CONTRACT_CHANGED")
    if contract.get("CODE_IDENTITY") != pkt045_code_identity(root):
        raise ValueError("PKT045_STAGE1_FROZEN_CODE_CHANGED")
    return contract


def acquire_pkt045_stage1(
    root: Path, output: Path, *, client: dukascopy_acquisition.AwsRequesterPaysClient | None = None,
    max_new_objects: int | None = None,
) -> dict[str, Any]:
    """Run the one permitted PKT-045 raw tick downloader after sealed gates."""
    stage_root = _pkt045_stage1_output(root, output)
    contract = _load_pkt045_stage1_contract(root, stage_root)
    _receipt, _pairs, _prepared, inventory, _pricing, cost, gate = _pkt045_stage1_inventory_and_cost(root, stage_root)
    started = time.monotonic()
    checkpoint = stage_root / "checkpoints" / "raw_acquisition.json"
    retry_state_path = stage_root / "checkpoints" / "retry_attempts.json"
    if checkpoint.exists():
        prior = json.loads(checkpoint.read_text(encoding="utf-8"))
        failed_key = prior.get("FAILED_OBJECT_KEY")
        prior_error = str(prior.get("ERROR", ""))
        retry_state = json.loads(retry_state_path.read_text(encoding="utf-8")) if retry_state_path.exists() else {}
        if failed_key and prior_error.startswith(dukascopy_acquisition.TEMPORARY_GET_ERROR_PREFIXES):
            source_index = next((i for i, item in enumerate(inventory.objects) if item.key == failed_key), None)
            if source_index is not None:
                failed_raw = dukascopy_acquisition.raw_object_path(stage_root / "raw_ticks", inventory.objects[source_index])
                previous_part = failed_raw.with_name(f"{failed_raw.name}.part")
                if previous_part.exists():
                    recovery = stage_root / "recovery" / f"{failed_key.replace('/', '_')}.previous_failure.part"
                    recovery.parent.mkdir(parents=True, exist_ok=True)
                    if not recovery.exists():
                        previous_part.replace(recovery)

        # Deferred failures may be from earlier passes, not only the last
        # checkpointed key. Isolate every stale partial before a new pass.
        for source in inventory.objects:
            if int(retry_state.get(source.key, 0) or 0) <= 0:
                continue
            raw = dukascopy_acquisition.raw_object_path(stage_root / "raw_ticks", source)
            partial = raw.with_name(f"{raw.name}.part")
            if partial.exists():
                recovery = stage_root / "recovery" / f"{source.key.replace('/', '_')}.attempt{int(retry_state.get(source.key, 0) or 0)}.part"
                recovery.parent.mkdir(parents=True, exist_ok=True)
                if not recovery.exists():
                    partial.replace(recovery)

    # The approved amendment permits exactly one additional attempt for the
    # named timeout.  Persist authorization before dispatch and isolate the
    # prior partial file so a repeated resume cannot issue another GET.
    timeout_retry_marker = stage_root / "receipts" / "PKT045_STAGE1_TIMEOUT_RETRY_AUTHORIZATION.json"
    if not timeout_retry_marker.exists() and checkpoint.exists():
        prior = json.loads(checkpoint.read_text(encoding="utf-8"))
        failed_key = prior.get("FAILED_OBJECT_KEY")
        if failed_key == "AUDCAD/2024/03/18_ticks.bi5" and prior.get("ERROR") == "AWS_GET-OBJECT_TIMEOUT":
            failed_raw = dukascopy_acquisition.raw_object_path(stage_root / "raw_ticks", inventory.objects[
                next(i for i, item in enumerate(inventory.objects) if item.key == failed_key)
            ])
            previous_part = failed_raw.with_name(f"{failed_raw.name}.part")
            if previous_part.exists():
                previous_part.rename(previous_part.with_name(f"{previous_part.name}.previous_timeout"))
            save_new(timeout_retry_marker, {
                "schema": "AIOS_PKT045_STAGE1_TIMEOUT_RETRY_AUTHORIZATION_V1",
                "OBJECT_KEY": failed_key,
                "PRIOR_FAILED_ATTEMPTS": 2,
                "ADDITIONAL_ATTEMPTS_AUTHORIZED": 1,
                "STATUS": "AUTHORIZED_BEFORE_DISPATCH",
            })

    def before_get(source, projection, in_flight_keys=None):
        _pkt045_stage1_check_writer(root, stage_root)
        if resident_bytes() > 4 * 1024**3:
            raise ValueError("PKT045_STAGE1_MEMORY_LIMIT")
        if time.monotonic() - started > PKT045_STAGE1_FOREGROUND_SECONDS:
            raise ValueError("PKT045_STAGE1_FOREGROUND_TIME_LIMIT")
        resources = pkt045_stage1_resource_gate(
            root, stage_root, inventory, in_flight_keys=in_flight_keys,
        )
        validation.atomic_write(checkpoint, (validation.pretty_json({
            "STATUS": "RUNNING", "NEXT_OBJECT_KEY": source.key, "PROJECTION": projection,
            "RESOURCE_GATE": resources, "SAFE_RESUME_ACTION": "VALIDATE_RECEIPTS_THEN_CONTINUE_UNRECEIPTED_INVENTORIED_KEYS",
        }) + "\n").encode("utf-8"))
        if resources["RESOURCE_GATE"] != "PASS":
            raise ValueError("PKT045_STAGE1_RESOURCE_GATE_FAILED")

    result = None
    retry_backoff_seconds = (60, 300, 900)
    current_pass = 1
    for retry_pass in range(4):
        current_pass = retry_pass + 1
        result = dukascopy_acquisition.acquire_paired_tick_inventory(
            inventory=inventory, acquisition_gate=gate, cost_gate=cost,
            raw_root=stage_root / "raw_ticks", receipt_root=stage_root / "receipts",
            checkpoint_path=checkpoint, output_root=stage_root, client=client,
            max_new_objects=max_new_objects, before_get=before_get,
            retry_state_path=retry_state_path,
            max_concurrent_gets=PKT045_MAX_CONCURRENT_GETS,
        )
        if result["complete"] or max_new_objects is not None or not result.get("deferred_objects"):
            break
        if retry_pass < 3:
            time.sleep(retry_backoff_seconds[retry_pass])
    assert result is not None
    contract_candidates = list(stage_root.glob("receipts/PKT045_STAGE1_ACQUISITION_CONTRACT*.json"))
    contract_path = max(contract_candidates, key=lambda candidate: int(candidate.stem.rsplit("_V", 1)[1]) if "_V" in candidate.stem else 1)
    final = {"schema": "AIOS_PKT045_STAGE1_RAW_ACQUISITION_RECEIPT_V1", "CONTRACT_SHA256": validation.sha256_file(
        contract_path), **result}
    status_snapshot = {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "completed_objects": result["completed_objects"],
        "planned_objects": result["total_objects"],
        "remaining_objects": result["total_objects"] - result["completed_objects"],
        "deferred_objects": len(result.get("deferred_objects", [])),
        "exhausted_objects": len(result.get("exhausted_objects", [])),
        "permanent_blockers": 0,
        "completed_bytes": result["completed_bytes"],
        "current_pass": current_pass,
        "projected_cumulative_cost": result["projection"]["PROJECTED_TOTAL_PROJECT_COST_USD"],
        "process_pid": os.getpid(),
        "worker": PKT045_STAGE1_WORKER_ID,
        "lock_id": PKT045_STAGE1_LOCK_ID,
        "state": "COMPLETE" if result["complete"] else "DEFERRED_OR_BLOCKED",
    }
    _atomic_operational_json(stage_root / "checkpoints" / "download_status.json", status_snapshot)
    if result["complete"]:
        save_new(stage_root / "receipts" / "PKT045_STAGE1_RAW_ACQUISITION_RECEIPT.json", final)
    return final


def certify_pkt045_stage1(root: Path, output: Path) -> dict[str, Any]:
    """Normalize receipted ticks and certify all 58 executable paths, twice."""
    stage_root = _pkt045_stage1_output(root, output)
    contract = _load_pkt045_stage1_contract(root, stage_root)
    raw_receipt_path = stage_root / "receipts" / "PKT045_STAGE1_RAW_ACQUISITION_RECEIPT.json"
    if not raw_receipt_path.is_file():
        raise ValueError("PKT045_STAGE1_RAW_ACQUISITION_NOT_COMPLETE")
    raw_receipt = json.loads(raw_receipt_path.read_text(encoding="utf-8"))
    if raw_receipt.get("complete") is not True:
        raise ValueError("PKT045_STAGE1_RAW_ACQUISITION_NOT_COMPLETE")
    _receipt, pairs, _prepared, inventory, _pricing, _cost, _gate = _pkt045_stage1_inventory_and_cost(root, stage_root)
    metadata = contract.get("SOURCE_METADATA")
    if not isinstance(metadata, dict):
        raise ValueError("PKT045_STAGE1_SOURCE_METADATA_MISSING")
    started = time.monotonic()
    progress_path = stage_root / "checkpoints" / "certification.json"

    def check_limits():
        _pkt045_stage1_check_writer(root, stage_root)
        if resident_bytes() > 4 * 1024**3:
            raise ValueError("PKT045_STAGE1_MEMORY_LIMIT")
        if time.monotonic() - started > PKT045_STAGE1_FOREGROUND_SECONDS:
            raise ValueError("PKT045_STAGE1_FOREGROUND_TIME_LIMIT")
        if _pkt045_directory_bytes(stage_root) > PKT045_STAGE1_OUTPUT_LIMIT_BYTES:
            raise ValueError("PKT045_STAGE1_OUTPUT_LIMIT")

    def progress(stage, completed, total, details):
        validation.atomic_write(progress_path, (validation.pretty_json({
            "schema": "AIOS_PKT045_STAGE1_CERTIFICATION_CHECKPOINT_V1",
            "STATUS": "RUNNING", "STAGE": stage, "COMPLETED": completed, "TOTAL": total,
            "DETAILS": details, "SAFE_RESUME_ACTION": "VERIFY_CORPUS_AND_RESTART_CERTIFICATION",
        }) + "\n").encode("utf-8"))

    corpus_root = stage_root / "corpus_m5"
    first_manifest = pkt045_data.build_paired_tick_m5_corpus(
        inventory=inventory,
        raw_root=stage_root / "raw_ticks",
        receipt_root=stage_root / "receipts",
        corpus_root=corpus_root,
        output_root=stage_root,
        source_metadata=metadata,
        development_start=datetime.fromisoformat(research.PKT045_DEVELOPMENT_START),
        development_end=datetime.fromisoformat(research.PKT045_DEVELOPMENT_END),
        max_corpus_bytes=PKT045_STAGE1_CORPUS_RESERVATION_BYTES,
        progress=progress,
        check_limits=check_limits,
    )
    corpus_manifest_path = corpus_root / "CORPUS_MANIFEST.json"
    corpus_manifest_sha = validation.sha256_file(corpus_manifest_path)

    def availability():
        return research.certify_pkt045_successor_availability(
            corpus_root=corpus_root,
            pairs=pairs,
            source_metadata=metadata,
            progress=progress,
            check_limits=check_limits,
        )

    availability_one = availability()
    # Re-reading the sealed pair files and running the same availability code a
    # second time proves deterministic scientific certification without a new
    # data read or a scoring call.
    availability_two = availability()
    first_science = {"CORPUS_MANIFEST": first_manifest, "AVAILABILITY": availability_one}
    second_science = {"CORPUS_MANIFEST": json.loads(corpus_manifest_path.read_text(encoding="utf-8")), "AVAILABILITY": availability_two}
    first_bytes = validation.canonical_json(first_science).encode("utf-8")
    second_bytes = validation.canonical_json(second_science).encode("utf-8")
    if first_bytes != second_bytes:
        raise ValueError("PKT045_STAGE1_CERTIFICATION_NONDETERMINISTIC")
    certification = {
        "schema": "AIOS_PKT045_STAGE1_CERTIFICATION_RECEIPT_V1",
        "PACKET_ID": PKT045_PACKET_ID,
        "EXPERIMENT_ID": research.PKT045_EXPERIMENT_ID,
        "CORPUS_MANIFEST_SHA256": corpus_manifest_sha,
        "PAIR_COUNT": len(pairs),
        "M5_ROWS": first_manifest.get("m5_rows"),
        "SOURCE_TICK_RECORDS": first_manifest.get("source_tick_records"),
        "UNRESOLVED_REQUIRED_EXECUTABLE_PATHS": availability_one["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS_COUNT"],
        "EXECUTABLE_DATA_CERTIFICATION": availability_one["EXECUTABLE_DATA_CERTIFICATION"],
        "SCIENTIFIC_RUN1_SHA256": validation.sha256_bytes(first_bytes),
        "SCIENTIFIC_RUN2_SHA256": validation.sha256_bytes(second_bytes),
        "PROTECTED_DATA_READS": 0,
        "SCORING_PERFORMED": False,
    }
    save_new(stage_root / "certification" / "CERTIFICATION_RUN1.json", first_science)
    save_new(stage_root / "certification" / "CERTIFICATION_RUN2.json", second_science)
    save_new(stage_root / "certification" / "PKT045_STAGE1_CERTIFICATION_RECEIPT.json", certification)
    return certification


def run_pkt045_stage1(root: Path, output: Path) -> dict[str, Any]:
    """Drive the approved local Stage 1 phases from durable state.

    This is deliberately the single controller entry point.  It resumes
    acquisition when the raw receipt is absent, then immediately invokes
    corpus construction and deterministic certification when acquisition is
    complete.  It never treats a textual next step as a transition and it
    fails closed before any scoring or memory publication is attempted.
    """
    stage_root = _pkt045_stage1_output(root, output)
    phase_path = stage_root / "checkpoints" / "phase_state.json"

    def transition(phase: str, status: str, **details: Any) -> dict[str, Any]:
        payload = {
            "schema": "AIOS_PKT045_STAGE1_PHASE_STATE_V1",
            "PACKET_ID": PKT045_PACKET_ID,
            "PHASE": phase,
            "STATUS": status,
            "UPDATED_UTC": datetime.now(timezone.utc).isoformat(),
            **details,
        }
        validation.atomic_write(
            phase_path,
            (validation.pretty_json(payload) + "\n").encode("utf-8"),
        )
        return payload

    raw_receipt = stage_root / "receipts" / "PKT045_STAGE1_RAW_ACQUISITION_RECEIPT.json"
    certification_receipt = stage_root / "certification" / "PKT045_STAGE1_CERTIFICATION_RECEIPT.json"
    try:
        transition("ACQUIRE", "RUNNING", ENTRY="RESUME_FROM_RECEIPTS")
        if not raw_receipt.is_file():
            acquisition = acquire_pkt045_stage1(root, stage_root)
            if acquisition.get("complete") is not True:
                return transition(
                    "ACQUIRE", "DEFERRED_OR_BLOCKED",
                    COMPLETED_OBJECTS=acquisition.get("completed_objects"),
                    TOTAL_OBJECTS=acquisition.get("total_objects"),
                    DEFERRED_OBJECTS=acquisition.get("deferred_objects", []),
                    NEXT_PHASE="ACQUIRE",
                )
        transition("SEAL_RAW", "PASS", NEXT_PHASE="BUILD_M5")
        if not certification_receipt.is_file():
            certification = certify_pkt045_stage1(root, stage_root)
        else:
            certification = json.loads(certification_receipt.read_text(encoding="utf-8"))
        if certification.get("EXECUTABLE_DATA_CERTIFICATION") != "PASS":
            return transition(
                "CERTIFY", "FAIL", CERTIFICATION=certification,
                NEXT_PHASE="STOP_CERTIFICATION_FAILURE",
            )
        # The repository currently has no checked PKT-045 outcome publisher or
        # frozen A/B executor.  Do not silently score, publish, or claim that
        # those phases ran.  Persist the exact handoff boundary instead.
        return transition(
            "CERTIFY", "PASS", CERTIFICATION=certification,
            NEXT_PHASE="RUN_FROZEN_AB",
            STATUS_DETAIL="FROZEN_AB_EXECUTOR_NOT_IMPLEMENTED_IN_EXISTING_RUNNER",
        )
    except Exception as exc:
        transition(
            "FAILED", "BLOCKED", ERROR=f"{type(exc).__name__}:{exc}",
            NEXT_PHASE="OWNER_REVIEW_REQUIRED",
        )
        raise
