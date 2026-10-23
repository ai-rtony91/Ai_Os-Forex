#!/usr/bin/env python3
"""Run, compare, and register PKT-FOREX-043 Stage-0 artifacts."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from automation.forex_engine.forex_factor_common_component_momentum_stage0_v1 import (  # noqa: E402
    FINGERPRINT_INDEX_RELATIVE,
    TRIAL_LEDGER_RELATIVE,
    build_stage0,
    build_edge_cards,
    canonical_bytes,
    memory_summary,
    prepare_memory_registration,
    read_trial_ledger,
    sha256_bytes,
    sha256_file,
)
from automation.forex_engine.forex_edge_validation_pipeline_v1 import atomic_write, msvcrt


ALLOWED_ROOT = REPO_ROOT / ".aios/staging/PKT_FOREX_043"


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def run(output_root: Path) -> dict[str, object]:
    output_root = output_root.resolve()
    allowed = ALLOWED_ROOT.resolve()
    if not _inside(output_root, allowed) or output_root == allowed:
        raise ValueError("OUTPUT_ROOT_OUTSIDE_PKT_FOREX_043")
    if output_root.exists():
        raise FileExistsError(f"OUTPUT_ROOT_EXISTS:{output_root}")
    allowed.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=str(allowed)))
    try:
        artifacts = build_stage0(REPO_ROOT)
        for name, payload in artifacts.items():
            (temporary / name).write_bytes(payload)
        os.replace(temporary, output_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    aggregate = sha256_bytes(canonical_bytes({name: sha256_file(output_root / name) for name in sorted(artifacts)}))
    return {"status": "PASS", "output_root": str(output_root), "artifact_count": len(artifacts), "aggregate_sha256": aggregate, "market_rows_opened": 0, "validation_rows_opened": 0, "holdout_rows_opened": 0, "new_scored_trial_increment": 0}


def compare(first_root: Path, second_root: Path) -> dict[str, object]:
    first_root, second_root = first_root.resolve(), second_root.resolve()
    if not _inside(first_root, ALLOWED_ROOT.resolve()) or not _inside(second_root, ALLOWED_ROOT.resolve()):
        raise ValueError("COMPARE_ROOT_OUTSIDE_PKT_FOREX_043")
    first = {path.name: sha256_file(path) for path in first_root.iterdir() if path.is_file()}
    second = {path.name: sha256_file(path) for path in second_root.iterdir() if path.is_file()}
    mismatches = sorted(name for name in set(first) | set(second) if first.get(name) != second.get(name))
    aggregate = sha256_bytes(canonical_bytes(first)) if not mismatches else ""
    return {"status": "PASS" if not mismatches else "FAIL", "byte_identical": not mismatches, "artifact_count": len(first), "aggregate_sha256": aggregate, "mismatches": mismatches}


def promote_memory(source_root: Path) -> dict[str, object]:
    source_root = source_root.resolve()
    if not _inside(source_root, ALLOWED_ROOT.resolve()) or source_root == ALLOWED_ROOT.resolve():
        raise ValueError("SOURCE_ROOT_OUTSIDE_PKT_FOREX_043")
    staged_ledger = (source_root / "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl").read_bytes()
    staged_index = (source_root / "AIOS_FOREX_FINGERPRINT_INDEX_V1.json").read_bytes()
    staged_records = [json.loads(line) for line in staged_ledger.decode("ascii").splitlines()]
    staged_index_value = json.loads(staged_index)
    summary = memory_summary(staged_records, staged_index_value)
    if summary["pkt043_index_entries"] != 36:
        raise RuntimeError("STAGED_MEMORY_INVALID")
    ledger_path = REPO_ROOT / TRIAL_LEDGER_RELATIVE
    index_path = REPO_ROOT / FINGERPRINT_INDEX_RELATIVE
    current_ledger = ledger_path.read_bytes()
    current_index = index_path.read_bytes()
    # Rebuild the only permitted change from trusted history and the frozen
    # PKT043 cards. Current totals may lawfully grow; this publisher must not
    # publish a score, alter a prior entry, or accept arbitrary staged growth.
    factor_entries = [row for row in staged_index_value["entries"] if row.get("packet_id") == "PKT-FOREX-043"]
    cards = build_edge_cards(factor_entries[0]["specification"]["pair_currency_universe"])
    current_records = read_trial_ledger(ledger_path)
    try:
        expected_ledger, expected_index, _ = prepare_memory_registration(
            cards, current_records, json.loads(current_index))
    except (ValueError, RuntimeError) as error:
        raise RuntimeError("MEMORY_PAIR_INVALID_REQUIRES_RECOVERY") from error
    expected_records = [json.loads(line) for line in expected_ledger.decode("ascii").splitlines()]
    if current_ledger == staged_ledger and current_index == staged_index:
        # Valid identical files are a no-op, including lawful append order in
        # the newer index. Do not rewrite them merely to sort serialization.
        if staged_records != expected_records:
            raise RuntimeError("STAGED_MEMORY_NOT_EXACT_FROZEN_REGISTRATION")
        changed = False
    else:
        if staged_records != expected_records or staged_index_value != json.loads(expected_index):
            raise RuntimeError("STAGED_MEMORY_NOT_EXACT_FROZEN_REGISTRATION")
        if not staged_ledger.startswith(current_ledger):
            raise RuntimeError("CANONICAL_LEDGER_NOT_PREFIX_OF_STAGED_LEDGER")
        _publish_pair(source_root, ledger_path, index_path, current_ledger, current_index, staged_ledger, staged_index)
        changed = True
    readback = memory_summary(read_trial_ledger(ledger_path), json.loads(index_path.read_text(encoding="utf-8")))
    if readback != summary:
        raise RuntimeError("CANONICAL_MEMORY_READBACK_MISMATCH")
    return {"status": "PASS", "changed": changed, "idempotent": not changed, "new_scored_trial_increment": 0, "ledger_sha256": sha256_file(ledger_path), "fingerprint_index_sha256": sha256_file(index_path), **readback}


def _publish_pair(source_root, ledger_path, index_path, current_ledger, current_index, staged_ledger, staged_index):
    """Shared checked publisher write kernel; callers validate their own scope."""
    if msvcrt is None:
        raise RuntimeError("MEMORY_PUBLICATION_EXCLUSIVE_LOCK_UNAVAILABLE")
    # Cooperating publishers serialize on the ledger handle. Readback under
    # the lock detects another writer since validation; never replace that
    # handle's path while locked. Both-file atomicity is not claimed.
    with ledger_path.open("r+b") as handle:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            handle.seek(0)
            if handle.read() != current_ledger or index_path.read_bytes() != current_index:
                raise RuntimeError("MEMORY_CHANGED_DURING_PUBLICATION")
            recovery = Path(tempfile.mkdtemp(prefix="memory_publication_", dir=str(source_root)))
            for name, payload in (("before_ledger.jsonl", current_ledger), ("before_index.json", current_index),
                                  ("target_ledger.jsonl", staged_ledger), ("target_index.json", staged_index)):
                with (recovery / name).open("xb") as backup:
                    backup.write(payload)
                    backup.flush()
                    os.fsync(backup.fileno())
            intent = {"schema": "AIOS_FOREX_MEMORY_PUBLICATION_INTENT.v1",
                      "before_ledger_sha256": sha256_bytes(current_ledger),
                      "before_index_sha256": sha256_bytes(current_index),
                      "target_ledger_sha256": sha256_bytes(staged_ledger),
                      "target_index_sha256": sha256_bytes(staged_index),
                      "recovery": "STOP_AND_VERIFY_SAVED_BEFORE_PAIR_AND_STAGED_TARGET;_NO_AUTOMATIC_ROLLBACK"}
            with (recovery / "intent.json").open("xb") as intent_handle:
                intent_handle.write(canonical_bytes(intent))
                intent_handle.flush()
                os.fsync(intent_handle.fileno())
            try:
                handle.seek(0)
                handle.write(staged_ledger)
                handle.truncate()
                handle.flush()
                os.fsync(handle.fileno())
                atomic_write(index_path, staged_index)
            except Exception as error:
                raise RuntimeError(f"MEMORY_PUBLICATION_INTERRUPTED_REQUIRES_RECOVERY:{recovery}") from error
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def prepare_pkt044_publication(records, index, cards, phase, evidence_sha256, *, correction_id=None):
    """Pure, bounded append preparation; no permissions or market I/O here."""
    import copy
    from automation.forex_engine import forex_edge_validation_pipeline_v1 as validation
    from automation.forex_engine.edge_research.execution import ARM_IDS
    if correction_id not in (None, "MEASUREMENT_AVAILABILITY_R1"):
        raise ValueError("PKT044_CORRECTION_NOT_APPROVED")
    if tuple(card["candidate_id"] for card in cards) != ARM_IDS or phase not in {"OUTCOME_EXAMINED", "VALID_TEST_REJECTED", "INVALID_TEST"}:
        raise ValueError("PKT044_PUBLICATION_BUDGET_OR_PHASE_INVALID")
    if len(evidence_sha256) != 64 or any(c not in "0123456789abcdef" for c in evidence_sha256):
        raise ValueError("PKT044_PUBLICATION_EVIDENCE_INVALID")
    validation.validate_trial_ledger(records)
    updated, target = list(records), copy.deepcopy(index)
    for card in cards:
        fingerprint = validation.candidate_fingerprint(card["specification"])
        if fingerprint != card["fingerprint"]:
            raise ValueError("PKT044_FINGERPRINT_MISMATCH")
        identity = card["candidate_id"]
        matches = [entry for entry in target["entries"] if entry["candidate_id"] == identity or entry["fingerprint"] == fingerprint]
        prior = [row for row in updated if row.get("candidate_id") == identity]
        if correction_id and not all(any(row["event_id"] == "PKT044:"+identity+":"+state for row in prior)
                                     for state in ("OUTCOME_EXAMINED", "INVALID_TEST")):
            raise ValueError("PKT044_CORRECTION_PARENT_MISSING")
        if bool(matches) != bool(prior):
            raise ValueError("PKT044_PARTIAL_MEMORY_PAIR_REQUIRES_RECOVERY")
        entry = {**card, "status": "OUTCOME_EXAMINED", "packet_id": "PKT-FOREX-044"}
        if matches and matches != [entry]:
            raise ValueError("PKT044_DUPLICATE_OR_CHANGED_CANDIDATE")
        if not matches:
            if phase != "OUTCOME_EXAMINED": raise ValueError("PKT044_RESULT_WITHOUT_OUTCOME_ACCESS")
            target["entries"].append(entry)
        event_id = "PKT044:"+identity+":"+phase
        if correction_id:
            event_id += ":"+correction_id
        payload = {"event_id": event_id, "candidate_id": identity, "candidate_fingerprint": fingerprint,
            "packet_id": "PKT-FOREX-044", "status": phase,
            "scored_trial_increment": 1 if phase == "OUTCOME_EXAMINED" and not correction_id else 0, "proposed_count": 0,
            "evidence_sha256": evidence_sha256, "provenance": "PKT044_APPROVED_BOUNDED_DEVELOPMENT_BATCH"}
        if correction_id:
            payload.update(correction_id=correction_id, corrects_event_id="PKT044:"+identity+":INVALID_TEST",
                           original_trial_event_id="PKT044:"+identity+":OUTCOME_EXAMINED")
            if phase != "OUTCOME_EXAMINED" and not any(row["event_id"] == "PKT044:"+identity+":OUTCOME_EXAMINED:"+correction_id for row in prior):
                raise ValueError("PKT044_CORRECTION_OUTCOME_ACCESS_MISSING")
        existing = [row for row in prior if row["event_id"] == event_id]
        if existing:
            actual = {k:v for k,v in existing[0].items() if k not in {"sequence", "previous_record_sha256", "record_sha256"}}
            if actual != payload: raise ValueError("PKT044_COMPLETION_CONFLICT")
            continue
        if phase == "OUTCOME_EXAMINED" and not correction_id and any(row.get("scored_trial_increment", 0) for row in prior):
            raise ValueError("PKT044_REPEAT_SCORE_FORBIDDEN")
        if phase != "OUTCOME_EXAMINED" and not any(row["status"] == "OUTCOME_EXAMINED" for row in prior):
            raise ValueError("PKT044_RESULT_WITHOUT_OUTCOME_ACCESS")
        updated.append(validation._ledger_record(len(updated)+1, updated[-1]["record_sha256"], payload))
    validation.validate_trial_ledger(updated)
    return updated, target


def publish_pkt044(source_root, cards, phase, evidence_sha256):
    """Approved PKT044 interface using the same publisher transaction kernel."""
    from datetime import datetime, timezone
    from automation.forex_engine import forex_edge_discovery_tournament_stage1_v1 as memory
    from automation.forex_engine import forex_edge_discovery_tournament_stage0_v1 as stage0
    from automation.forex_engine.edge_research.research import specifications
    from scripts.forex_delivery.run_forex_control_baseline_rsi_filter_comparison_stage1_v1 import check_writer
    source_root = source_root.resolve()
    allowed = REPO_ROOT / ".aios/staging/PKT_FOREX_044"
    if not _inside(source_root, allowed) or source_root == allowed:
        raise ValueError("PKT044_PUBLICATION_SOURCE_OUTSIDE_SCOPE")
    evidence_name = "contract.json" if phase == "OUTCOME_EXAMINED" else "handoff.json" if phase == "VALID_TEST_REJECTED" else "invalid_test.json"
    evidence_path = source_root / evidence_name
    if not evidence_path.is_file() or sha256_file(evidence_path) != evidence_sha256:
        raise ValueError("PKT044_PUBLICATION_CHECKED_EVIDENCE_MISSING")
    evidence = json.loads(evidence_path.read_bytes())
    contract = json.loads((source_root/"contract.json").read_bytes())
    correction = contract.get("measurement_correction")
    correction_id = None
    if correction is not None:
        from automation.forex_engine.edge_research.batch import verify_correction_parent
        if correction != verify_correction_parent(REPO_ROOT, cards) or contract.get("cards") != cards:
            raise ValueError("PKT044_CORRECTION_CONTRACT_MISMATCH")
        correction_id = correction["correction_id"]
    if phase == "OUTCOME_EXAMINED" and evidence.get("cards") != cards:
        raise ValueError("PKT044_FROZEN_CONTRACT_IDENTITY_MISMATCH")
    if phase == "VALID_TEST_REJECTED" or (phase == "INVALID_TEST" and correction_id):
        from automation.forex_engine.forex_edge_validation_pipeline_v1 import validate_research_record
        if len(evidence.get("records", [])) != 2: raise ValueError("PKT044_CHECKED_RESULTS_MISSING")
        for record, card in zip(evidence["records"], cards):
            validate_research_record(record)
            if record["candidate_id"] != card["candidate_id"] or record["fingerprint"] != card["fingerprint"]:
                raise ValueError("PKT044_RESULT_IDENTITY_MISMATCH")
    if cards != specifications(sorted(memory.certified_instrument_metadata())):
        raise ValueError("PKT044_PUBLICATION_NOT_FROZEN_TWO_CONFIGURATIONS")
    registry_path = REPO_ROOT / "automation/orchestration/locks/FILE_LOCK_REGISTRY.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    ledger_path, index_path = REPO_ROOT / TRIAL_LEDGER_RELATIVE, REPO_ROOT / FINGERPRINT_INDEX_RELATIVE
    for path in (source_root, ledger_path, index_path):
        check_writer(registry, path, datetime.now(timezone.utc))
    memory.verify_runtime_contracts(REPO_ROOT, stage0.first_wave_manifest()["cells"], require_pre_score=False)
    before_ledger, before_index = ledger_path.read_bytes(), index_path.read_bytes()
    records = [json.loads(line) for line in before_ledger.splitlines()]
    updated, target = prepare_pkt044_publication(records, json.loads(before_index), cards, phase, evidence_sha256, correction_id=correction_id)
    if updated == records and target == json.loads(before_index):
        return {"changed": False, **memory_summary(records, target)}
    suffix = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)+"\n").encode("ascii") for row in updated[len(records):])
    staged_ledger, staged_index = before_ledger+suffix, canonical_bytes(target)
    memory.verify_append_only_corrected_memory(updated, target,
        memory.read_trial_ledger(REPO_ROOT / memory.TRUSTED_CORRECTED_LEDGER_RELATIVE),
        json.loads((REPO_ROOT / memory.TRUSTED_CORRECTED_FINGERPRINT_INDEX_RELATIVE).read_bytes()))
    registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    for path in (source_root, ledger_path, index_path): check_writer(registry, path, datetime.now(timezone.utc))
    _publish_pair(source_root, ledger_path, index_path, before_ledger, before_index, staged_ledger, staged_index)
    if ledger_path.read_bytes() != staged_ledger or index_path.read_bytes() != staged_index:
        raise ValueError("PKT044_PUBLICATION_READBACK_MISMATCH")
    return {"changed": True, **memory_summary(updated, target)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run", "compare", "promote-memory"))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--first-root", type=Path)
    parser.add_argument("--second-root", type=Path)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        if args.output_root is None:
            parser.error("run requires --output-root")
        result = run(args.output_root)
    elif args.command == "compare":
        if args.first_root is None or args.second_root is None:
            parser.error("compare requires --first-root and --second-root")
        result = compare(args.first_root, args.second_root)
    else:
        if args.source_root is None:
            parser.error("promote-memory requires --source-root")
        result = promote_memory(args.source_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
