"""Verify an externally restored frozen Phase 1 runtime bundle.

This checker is intentionally read-only for runtime inputs. It does not
reconstruct evidence; it only confirms that restored files match the frozen
hash contract before the postmortem rerun is attempted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

from automation.forex_engine.forex_frozen_21_series_phase1_postmortem_v1 import (
    DATASET_ID,
    DATASET_SHA256,
    INPUT_HASHES,
    REPRODUCTION_COMMAND,
)


SCHEMA = "AIOS_FOREX_FROZEN_RUNTIME_RESTORE_VERIFIER.v1"
DEFAULT_INPUT_ROOT = Path(".aios/runtime/forex_frozen_21_series_edge_research_v1")
DEFAULT_STATE_PATH = Path("Reports/forex_delivery/AIOS_FOREX_FROZEN_RUNTIME_RESTORE_VERIFIER_V1_STATE.json")
DEFAULT_REPORT_PATH = Path("Reports/forex_delivery/AIOS_FOREX_FROZEN_RUNTIME_RESTORE_VERIFIER_V1_REPORT.md")


def output_overlaps_frozen_inputs(output_path: Path, input_root: Path) -> bool:
    output = output_path.resolve()
    return any(output == root or root in output.parents for root in {input_root.resolve(), DEFAULT_INPUT_ROOT.resolve()})


def validate_expected_hashes(expected_hashes: Mapping[str, str]) -> None:
    for name, digest in expected_hashes.items():
        if not isinstance(name, str) or not name or name in {".", ".."} or "/" in name or "\\" in name or ":" in name:
            raise ValueError("expected name must be a plain filename")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            raise ValueError(f"expected hash must be 64 hexadecimal characters: {name}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def verify_restore_bundle(
    input_root: Path = DEFAULT_INPUT_ROOT,
    *,
    expected_hashes: Mapping[str, str] = INPUT_HASHES,
) -> dict[str, Any]:
    validate_expected_hashes(expected_hashes)
    input_root = Path(input_root)
    file_results: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    mismatched: list[dict[str, str]] = []
    matched = 0
    present = 0

    for name, expected_sha256 in sorted(expected_hashes.items()):
        path = input_root / name
        record: dict[str, Any] = {"expected_sha256": expected_sha256, "present": path.is_file()}
        if path.is_symlink():
            present += 1
            record["present"] = True
            record["blocked_symlink"] = True
            mismatched.append({"name": name, "expected_sha256": expected_sha256, "actual_sha256": "SYMLINK_BLOCKED"})
            file_results[name] = record
            continue
        if not path.is_file():
            missing.append(name)
            file_results[name] = record
            continue
        present += 1
        actual_sha256 = sha256_file(path)
        record["bytes"] = path.stat().st_size
        record["actual_sha256"] = actual_sha256
        record["sha256_match"] = actual_sha256.lower() == expected_sha256.lower()
        if record["sha256_match"]:
            matched += 1
        else:
            mismatched.append({"name": name, "expected_sha256": expected_sha256, "actual_sha256": actual_sha256})
        file_results[name] = record

    safe = not missing and not mismatched
    frozen_contract = {name: digest.lower() for name, digest in expected_hashes.items()} == INPUT_HASHES
    safe_to_rerun = safe and frozen_contract
    default_root = input_root.resolve() == DEFAULT_INPUT_ROOT.resolve()
    status = "PASS" if safe else ("BLOCKED_RESTORE_BUNDLE_MISSING_INPUTS" if missing else "BLOCKED_RESTORE_BUNDLE_HASH_MISMATCH")
    return {
        "schema": SCHEMA,
        "status": status,
        "input_root": input_root.as_posix(),
        "dataset_id": DATASET_ID,
        "dataset_sha256": DATASET_SHA256,
        "counts": {
            "expected": len(expected_hashes),
            "present": present,
            "matched": matched,
            "missing": len(missing),
            "mismatched": len(mismatched),
        },
        "missing": missing,
        "mismatched": mismatched,
        "files": file_results,
        "frozen_contract_match": frozen_contract,
        "safe_to_rerun_postmortem": safe_to_rerun,
        "postmortem_rerun_command": REPRODUCTION_COMMAND if safe_to_rerun and default_root else None,
        "next_safe_action": (
            "rerun_frozen_phase1_postmortem" if safe_to_rerun and default_root else
            "rerun_frozen_phase1_postmortem_with_verified_input_root" if safe_to_rerun else
            "use_frozen_contract_for_postmortem" if safe else
            "restore_authoritative_runtime_bundle_then_rerun_verifier"
        ),
        "safety": {
            "creates_runtime_inputs": False,
            "uses_broker": False,
            "uses_credentials": False,
            "uses_network": False,
            "places_orders": False,
        },
    }


def render_report(receipt: Mapping[str, Any]) -> str:
    missing = receipt.get("missing", [])
    mismatched = receipt.get("mismatched", [])
    lines = [
        "# AIOS Forex Frozen Runtime Restore Verifier V1",
        "",
        f"Status: {receipt['status']}",
        "",
        f"Input root: `{receipt['input_root']}`",
        f"Dataset: `{receipt['dataset_id']}` / `{receipt['dataset_sha256']}`",
        "",
        "This verifier does not create or reconstruct frozen runtime evidence. It only checks files restored from the authoritative archive against the frozen hash contract.",
        "",
        "## Counts",
        "",
        f"- Expected files: {receipt['counts']['expected']}",
        f"- Present files: {receipt['counts']['present']}",
        f"- Matched files: {receipt['counts']['matched']}",
        f"- Missing files: {receipt['counts']['missing']}",
        f"- Mismatched files: {receipt['counts']['mismatched']}",
        "",
        "## Next Safe Action",
        "",
        f"`{receipt['next_safe_action']}`",
    ]
    if missing:
        lines.extend(["", "## Missing Inputs", ""])
        lines.extend(f"- `{name}`" for name in missing)
    if mismatched:
        lines.extend(["", "## Hash Mismatches", ""])
        lines.extend(f"- `{item['name']}`" for item in mismatched)
    if receipt.get("postmortem_rerun_command"):
        lines.extend(["", "## Postmortem Rerun", "", f"`{receipt['postmortem_rerun_command']}`"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args(argv)

    if output_overlaps_frozen_inputs(args.state_path, args.input_root) or output_overlaps_frozen_inputs(args.report_path, args.input_root):
        parser.error("state and report paths must be outside frozen input roots")
    if args.state_path.resolve() == args.report_path.resolve():
        parser.error("state and report paths must be different files")

    receipt = verify_restore_bundle(args.input_root)
    atomic_json(args.state_path, receipt)
    atomic_text(args.report_path, render_report(receipt))
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
