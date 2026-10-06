#!/usr/bin/env python3
"""Run one isolated PKT-FOREX-039 development-only reproduction."""
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

from automation.forex_engine.forex_edge_discovery_tournament_stage1_v1 import (  # noqa: E402
    FINGERPRINT_INDEX_RELATIVE,
    EXPECTED_CUMULATIVE_LOWER_BOUND,
    TRIAL_LEDGER_RELATIVE,
    build_artifacts,
    build_corrective_artifacts,
    canonical_bytes,
    prepare_corrective_memory_update,
    prepare_global_memory_update,
    read_trial_ledger,
    repair_execution_direction_counts,
    research,
    sha256_bytes,
    sha256_file,
    validate_trial_ledger,
)


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def execute(corpus_root: Path, stage0_root: Path, output_root: Path) -> dict[str, object]:
    corpus_root = corpus_root.resolve()
    stage0_root = stage0_root.resolve()
    output_root = output_root.resolve()
    expected_corpus = (REPO_ROOT / ".aios/runtime/forex_m5_immutable_corpus_v2").resolve()
    expected_stage0 = (REPO_ROOT / ".aios/staging/PKT_FOREX_038/final_reproduction1").resolve()
    allowed_output = (REPO_ROOT / ".aios/staging/PKT_FOREX_039").resolve()
    if corpus_root != expected_corpus:
        raise ValueError("CORPUS_ROOT_NOT_FROZEN_CANONICAL_INPUT")
    if stage0_root != expected_stage0:
        raise ValueError("STAGE0_ROOT_NOT_FROZEN_CANONICAL_INPUT")
    if not _inside(output_root, allowed_output) or output_root == allowed_output:
        raise ValueError("OUTPUT_ROOT_OUTSIDE_PACKET_STAGING")
    if output_root.exists():
        raise FileExistsError(f"OUTPUT_ROOT_ALREADY_EXISTS:{output_root}")

    result, journal, journal_audit, verification = research(corpus_root, stage0_root, REPO_ROOT)
    ledger_path = REPO_ROOT / TRIAL_LEDGER_RELATIVE
    fingerprint_path = REPO_ROOT / FINGERPRINT_INDEX_RELATIVE
    ledger_records = read_trial_ledger(ledger_path)
    fingerprint_index = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    result_sha256 = sha256_bytes(canonical_bytes(result))
    ledger_payload, fingerprint_payload, memory_update = prepare_global_memory_update(
        result,
        verification["runtime_contracts"],
        ledger_records,
        fingerprint_index,
        result_sha256,
    )
    artifacts = build_artifacts(
        result, journal, journal_audit, verification,
        ledger_payload, fingerprint_payload, memory_update,
    )
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
        "promotion_state": result["promotion_state"],
        "scored_cell_count": result["new_outcome_scored_trials"],
        "cumulative_actual_attempt_lower_bound": result["cumulative_actual_attempt_lower_bound"],
        "mechanism_observed_cell_count": len(result["mechanism_observed_cells"]),
        "mechanism_observed_cells": result["mechanism_observed_cells"],
        "development_rows_opened_per_pass": result["reader"]["unique_development_rows_per_pass"],
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
        "verified_edge": False,
        "artifact_count": len(artifacts),
        "aggregate_sha256": aggregate,
        "output_root": output_root.as_posix(),
    }


def corrective_execute(corpus_root: Path, stage0_root: Path, output_root: Path) -> dict[str, object]:
    corpus_root = corpus_root.resolve()
    stage0_root = stage0_root.resolve()
    output_root = output_root.resolve()
    expected_corpus = (REPO_ROOT / ".aios/runtime/forex_m5_immutable_corpus_v2").resolve()
    expected_stage0 = (REPO_ROOT / ".aios/staging/PKT_FOREX_038/final_reproduction1").resolve()
    allowed_output = (REPO_ROOT / ".aios/staging/PKT_FOREX_042").resolve()
    if corpus_root != expected_corpus:
        raise ValueError("CORPUS_ROOT_NOT_FROZEN_CANONICAL_INPUT")
    if stage0_root != expected_stage0:
        raise ValueError("STAGE0_ROOT_NOT_FROZEN_CANONICAL_INPUT")
    if not _inside(output_root, allowed_output) or output_root == allowed_output:
        raise ValueError("OUTPUT_ROOT_OUTSIDE_PKT042_STAGING")
    if output_root.exists():
        raise FileExistsError(f"OUTPUT_ROOT_ALREADY_EXISTS:{output_root}")

    result, journal, journal_audit, verification = research(
        corpus_root, stage0_root, REPO_ROOT, corrective_replay=True,
    )
    ledger_path = REPO_ROOT / TRIAL_LEDGER_RELATIVE
    fingerprint_path = REPO_ROOT / FINGERPRINT_INDEX_RELATIVE
    ledger_records = read_trial_ledger(ledger_path)
    fingerprint_index = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    result_sha256 = sha256_bytes(canonical_bytes(result))
    ledger_payload, fingerprint_payload, memory_update = prepare_corrective_memory_update(
        result, verification["runtime_contracts"], ledger_records, fingerprint_index, result_sha256,
    )
    artifacts = build_corrective_artifacts(
        result, journal, journal_audit, verification,
        ledger_payload, fingerprint_payload, memory_update,
    )
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
        "corrective_replay_cells": result["outcome_cells_replayed"],
        "new_scored_trial_increment": 0,
        "cumulative_actual_attempt_lower_bound": result["cumulative_actual_attempt_lower_bound"],
        "corrected_survivors": len(result["mechanism_observed_cells"]),
        "development_rows_opened_per_pass": result["reader"]["unique_development_rows_per_pass"],
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
        "verified_edge": False,
        "artifact_count": len(artifacts),
        "aggregate_sha256": aggregate,
        "output_root": output_root.as_posix(),
    }


def rebuild_corrective_reporting(source_root: Path, output_root: Path) -> dict[str, object]:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    allowed = (REPO_ROOT / ".aios/staging/PKT_FOREX_042").resolve()
    if not _inside(source_root, allowed) or not _inside(output_root, allowed) or output_root == allowed:
        raise ValueError("CORRECTIVE_REPORT_REBUILD_ROOT_OUTSIDE_PKT042_STAGING")
    if output_root.exists():
        raise FileExistsError(f"OUTPUT_ROOT_ALREADY_EXISTS:{output_root}")
    source_manifest = json.loads((source_root / "AIOS_FOREX_PKT039_CORRECTIVE_MANIFEST.json").read_text(encoding="utf-8"))
    for name, receipt in source_manifest["artifacts"].items():
        path = source_root / name
        if not path.is_file() or len(path.read_bytes()) != receipt["bytes"] or sha256_file(path) != receipt["sha256"]:
            raise RuntimeError(f"SOURCE_CORRECTIVE_ARTIFACT_MISMATCH:{name}")
    result = json.loads((source_root / "AIOS_FOREX_PKT039_CORRECTED_RESULTS.json").read_text(encoding="utf-8"))
    journal = (source_root / "AIOS_FOREX_PKT039_CORRECTED_EVENT_EVIDENCE.jsonl.gz").read_bytes()
    journal_audit = json.loads((source_root / "AIOS_FOREX_PKT039_CORRECTED_JOURNAL_AUDIT.json").read_text(encoding="utf-8"))
    verification = json.loads((source_root / "AIOS_FOREX_PKT039_CORRECTED_INPUT_VERIFICATION.json").read_text(encoding="utf-8"))
    ledger_path = REPO_ROOT / TRIAL_LEDGER_RELATIVE
    fingerprint_path = REPO_ROOT / FINGERPRINT_INDEX_RELATIVE
    ledger_records = read_trial_ledger(ledger_path)
    fingerprint_index = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    result_sha256 = sha256_bytes(canonical_bytes(result))
    ledger_payload, fingerprint_payload, memory_update = prepare_corrective_memory_update(
        result, verification["runtime_contracts"], ledger_records, fingerprint_index, result_sha256,
    )
    artifacts = build_corrective_artifacts(
        result, journal, journal_audit, verification,
        ledger_payload, fingerprint_payload, memory_update,
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    for name, content in sorted(artifacts.items()):
        (temporary / name).write_bytes(content)
    os.replace(temporary, output_root)
    aggregate = sha256_bytes(b"".join(name.encode("utf-8") + b"\0" + artifacts[name] for name in sorted(artifacts)))
    return {
        "status": "PASS",
        "source_full_replay_root": source_root.as_posix(),
        "corrective_replay_cells": result["outcome_cells_replayed"],
        "new_scored_trial_increment": 0,
        "artifact_count": len(artifacts),
        "aggregate_sha256": aggregate,
        "output_root": output_root.as_posix(),
    }


def compare(first_root: Path, second_root: Path) -> dict[str, object]:
    first_root, second_root = first_root.resolve(), second_root.resolve()
    allowed_roots = (
        (REPO_ROOT / ".aios/staging/PKT_FOREX_039").resolve(),
        (REPO_ROOT / ".aios/staging/PKT_FOREX_042").resolve(),
    )
    if not any(_inside(first_root, allowed) and _inside(second_root, allowed) for allowed in allowed_roots):
        raise ValueError("COMPARISON_ROOT_OUTSIDE_PACKET_STAGING")
    first = {path.name: path.read_bytes() for path in first_root.iterdir() if path.is_file()}
    second = {path.name: path.read_bytes() for path in second_root.iterdir() if path.is_file()}
    mismatches = sorted(set(first) ^ set(second) | {name for name in set(first) & set(second) if first[name] != second[name]})
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "byte_identical": not mismatches,
        "artifact_count": len(first),
        "mismatches": mismatches,
        "aggregate_sha256": sha256_bytes(b"".join(name.encode("utf-8") + b"\0" + first[name] for name in sorted(first))) if not mismatches else None,
    }


def rebuild_reporting(source_root: Path, output_root: Path) -> dict[str, object]:
    source_root, output_root = source_root.resolve(), output_root.resolve()
    allowed = (REPO_ROOT / ".aios/staging/PKT_FOREX_039").resolve()
    if not _inside(source_root, allowed) or not _inside(output_root, allowed) or output_root == allowed:
        raise ValueError("REPORT_REBUILD_ROOT_OUTSIDE_PACKET_STAGING")
    if output_root.exists():
        raise FileExistsError(f"OUTPUT_ROOT_ALREADY_EXISTS:{output_root}")
    result = json.loads((source_root / "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_RESULTS.json").read_text(encoding="utf-8"))
    journal = (source_root / "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_EVENT_EVIDENCE.jsonl.gz").read_bytes()
    journal_audit = json.loads((source_root / "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_JOURNAL_AUDIT.json").read_text(encoding="utf-8"))
    verification = json.loads((source_root / "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_INPUT_VERIFICATION.json").read_text(encoding="utf-8"))
    repair_execution_direction_counts(result, journal)
    ledger_path = REPO_ROOT / TRIAL_LEDGER_RELATIVE
    fingerprint_path = REPO_ROOT / FINGERPRINT_INDEX_RELATIVE
    ledger_records = read_trial_ledger(ledger_path)
    fingerprint_index = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    result_sha256 = sha256_bytes(canonical_bytes(result))
    ledger_payload, fingerprint_payload, memory_update = prepare_global_memory_update(
        result, verification["runtime_contracts"], ledger_records, fingerprint_index, result_sha256,
    )
    artifacts = build_artifacts(
        result, journal, journal_audit, verification,
        ledger_payload, fingerprint_payload, memory_update,
    )
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    for name, content in sorted(artifacts.items()):
        (temporary / name).write_bytes(content)
    os.replace(temporary, output_root)
    return {
        "status": result["status"],
        "reporting_repair": "PASS",
        "scored_cell_count": result["new_outcome_scored_trials"],
        "mechanism_observed_cell_count": len(result["mechanism_observed_cells"]),
        "aggregate_sha256": sha256_bytes(b"".join(name.encode("utf-8") + b"\0" + artifacts[name] for name in sorted(artifacts))),
        "output_root": output_root.as_posix(),
    }


def _atomic_replace(path: Path, payload: bytes) -> None:
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def promote_memory(source_root: Path) -> dict[str, object]:
    source_root = source_root.resolve()
    allowed = (REPO_ROOT / ".aios/staging/PKT_FOREX_039").resolve()
    if not _inside(source_root, allowed):
        raise ValueError("SOURCE_ROOT_OUTSIDE_PACKET_STAGING")
    manifest_path = source_root / "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, receipt in manifest["artifacts"].items():
        path = source_root / name
        if not path.is_file() or len(path.read_bytes()) != receipt["bytes"] or sha256_file(path) != receipt["sha256"]:
            raise RuntimeError(f"STAGED_ARTIFACT_MISMATCH:{name}")
    ledger_source = source_root / "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl"
    index_source = source_root / "AIOS_FOREX_FINGERPRINT_INDEX_V1.json"
    staged_ledger = read_trial_ledger(ledger_source)
    summary = validate_trial_ledger(staged_ledger)
    staged_index = json.loads(index_source.read_text(encoding="utf-8"))
    if summary["scored_attempt_lower_bound"] != 1292 or staged_index.get("pkt039_outcome_examined") != 72:
        raise RuntimeError("STAGED_MEMORY_UPDATE_NOT_EXACT_72")

    ledger_path = REPO_ROOT / TRIAL_LEDGER_RELATIVE
    index_path = REPO_ROOT / FINGERPRINT_INDEX_RELATIVE
    current_ledger, current_index = ledger_path.read_bytes(), index_path.read_bytes()
    if len(read_trial_ledger(ledger_path)) != 11:
        raise RuntimeError("CANONICAL_LEDGER_ALREADY_CHANGED")
    try:
        _atomic_replace(ledger_path, ledger_source.read_bytes())
        _atomic_replace(index_path, index_source.read_bytes())
        readback = validate_trial_ledger(read_trial_ledger(ledger_path))
        if readback["scored_attempt_lower_bound"] != 1292 or sha256_file(index_path) != sha256_file(index_source):
            raise RuntimeError("CANONICAL_MEMORY_READBACK_FAILED")
    except Exception:
        _atomic_replace(ledger_path, current_ledger)
        _atomic_replace(index_path, current_index)
        raise
    return {
        "status": "PASS",
        "records": len(staged_ledger),
        "scored_attempt_lower_bound": summary["scored_attempt_lower_bound"],
        "ledger_sha256": sha256_file(ledger_path),
        "fingerprint_index_sha256": sha256_file(index_path),
        "pkt039_outcome_examined": staged_index["pkt039_outcome_examined"],
        "pkt039_survivors": staged_index["pkt039_survivors"],
    }


def promote_corrective_memory(source_root: Path) -> dict[str, object]:
    source_root = source_root.resolve()
    allowed = (REPO_ROOT / ".aios/staging/PKT_FOREX_042").resolve()
    if not _inside(source_root, allowed):
        raise ValueError("SOURCE_ROOT_OUTSIDE_PKT042_STAGING")
    manifest_path = source_root / "AIOS_FOREX_PKT039_CORRECTIVE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, receipt in manifest["artifacts"].items():
        path = source_root / name
        if not path.is_file() or len(path.read_bytes()) != receipt["bytes"] or sha256_file(path) != receipt["sha256"]:
            raise RuntimeError(f"STAGED_CORRECTIVE_ARTIFACT_MISMATCH:{name}")
    ledger_source = source_root / "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl"
    index_source = source_root / "AIOS_FOREX_FINGERPRINT_INDEX_V1.json"
    staged_ledger = read_trial_ledger(ledger_source)
    summary = validate_trial_ledger(staged_ledger)
    staged_index = json.loads(index_source.read_text(encoding="utf-8"))
    if not (
        summary["record_count"] == 227
        and summary["scored_attempt_lower_bound"] == EXPECTED_CUMULATIVE_LOWER_BOUND
        and staged_index.get("pkt039_prior_results_invalidated") == 72
        and staged_index.get("pkt039_corrective_replay_cells") == 72
        and staged_index.get("pkt039_corrective_replay_trial_increment") == 0
    ):
        raise RuntimeError("STAGED_CORRECTIVE_MEMORY_NOT_EXACT")

    ledger_path = REPO_ROOT / TRIAL_LEDGER_RELATIVE
    index_path = REPO_ROOT / FINGERPRINT_INDEX_RELATIVE
    current_ledger, current_index = ledger_path.read_bytes(), index_path.read_bytes()
    current_summary = validate_trial_ledger(read_trial_ledger(ledger_path))
    if current_summary["record_count"] != 83 or current_summary["scored_attempt_lower_bound"] != EXPECTED_CUMULATIVE_LOWER_BOUND:
        raise RuntimeError("CANONICAL_MEMORY_ALREADY_CHANGED")
    try:
        _atomic_replace(ledger_path, ledger_source.read_bytes())
        _atomic_replace(index_path, index_source.read_bytes())
        readback = validate_trial_ledger(read_trial_ledger(ledger_path))
        if readback != summary or sha256_file(index_path) != sha256_file(index_source):
            raise RuntimeError("CANONICAL_CORRECTIVE_MEMORY_READBACK_FAILED")
    except Exception:
        _atomic_replace(ledger_path, current_ledger)
        _atomic_replace(index_path, current_index)
        raise
    return {
        "status": "PASS",
        "records": summary["record_count"],
        "scored_attempt_lower_bound": summary["scored_attempt_lower_bound"],
        "new_scored_trial_increment": 0,
        "ledger_sha256": sha256_file(ledger_path),
        "fingerprint_index_sha256": sha256_file(index_path),
        "pkt039_prior_results_invalidated": staged_index["pkt039_prior_results_invalidated"],
        "pkt039_corrective_replay_cells": staged_index["pkt039_corrective_replay_cells"],
        "pkt039_corrected_survivors": staged_index["pkt039_corrected_survivors"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "corrective-run", "rebuild-reporting", "rebuild-corrective-reporting", "compare", "promote-memory", "promote-corrective-memory"])
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--stage0-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--first-root", type=Path)
    parser.add_argument("--second-root", type=Path)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        if not all((args.corpus_root, args.stage0_root, args.output_root)):
            parser.error("run requires --corpus-root, --stage0-root, and --output-root")
        output = execute(args.corpus_root, args.stage0_root, args.output_root)
    elif args.command == "corrective-run":
        if not all((args.corpus_root, args.stage0_root, args.output_root)):
            parser.error("corrective-run requires --corpus-root, --stage0-root, and --output-root")
        output = corrective_execute(args.corpus_root, args.stage0_root, args.output_root)
    elif args.command == "rebuild-reporting":
        if not all((args.source_root, args.output_root)):
            parser.error("rebuild-reporting requires --source-root and --output-root")
        output = rebuild_reporting(args.source_root, args.output_root)
    elif args.command == "rebuild-corrective-reporting":
        if not all((args.source_root, args.output_root)):
            parser.error("rebuild-corrective-reporting requires --source-root and --output-root")
        output = rebuild_corrective_reporting(args.source_root, args.output_root)
    elif args.command == "compare":
        if not all((args.first_root, args.second_root)):
            parser.error("compare requires --first-root and --second-root")
        output = compare(args.first_root, args.second_root)
    elif args.command == "promote-memory":
        if not args.source_root:
            parser.error("promote-memory requires --source-root")
        output = promote_memory(args.source_root)
    else:
        if not args.source_root:
            parser.error("promote-corrective-memory requires --source-root")
        output = promote_corrective_memory(args.source_root)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
