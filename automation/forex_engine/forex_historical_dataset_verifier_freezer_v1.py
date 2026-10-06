"""Verify and freeze the AIOS 21-series historical Forex dataset.

The verifier is read-only unless a validation receipt path is explicitly
provided.  The freezer copies the already-batched artifacts without changing
their contents, verifies the copy, and atomically promotes a content-addressed
dataset directory.

This module has no network, credential, collector, order, or broker dependency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


TOOL_VERSION = "1.0.1"
VALIDATION_SCHEMA = "AIOS_FOREX_HISTORICAL_DATASET_VALIDATION_RECEIPT.v1"
FREEZE_SCHEMA = "AIOS_FOREX_HISTORICAL_DATASET_FREEZE_RECEIPT.v1"
MANIFEST_SCHEMA = "AIOS_FOREX_SCALPING_HISTORY_MANIFEST.v1"
CHECKPOINT_SCHEMA = "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.v1"
BATCH_SCHEMA = "AIOS_FOREX_SCALPING_HISTORY_BATCH.v1"
MANIFEST_NAME = "AIOS_FOREX_SCALPING_HISTORY_MANIFEST.json"
CHECKPOINT_NAME = "AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json"
EXPECTED_INSTRUMENTS = ("EUR_USD", "GBP_USD", "USD_JPY")
EXPECTED_GRANULARITIES = ("M1", "M2", "M4", "S10", "S15", "S30", "S5")
GRANULARITY_SECONDS = {"M1": 60, "M2": 120, "M4": 240, "S10": 10, "S15": 15, "S30": 30, "S5": 5}
COMPLETE_MANIFEST_STATUSES = {"SERIES_COMPLETE", "SERIES_COMPLETE_REUSED_FROM_CHECKPOINT"}
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class DatasetBlockedError(RuntimeError):
    """The operation could not safely produce a validation decision."""


@dataclass(frozen=True)
class VerificationConfig:
    source_root: Path
    scope_fingerprint: str
    start_utc: str
    end_utc: str
    instruments: tuple[str, ...] = EXPECTED_INSTRUMENTS
    granularities: tuple[str, ...] = EXPECTED_GRANULARITIES
    source_head: str = "UNKNOWN"
    max_defects: int = 100


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("timestamp must contain a timezone")
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a nonempty string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must contain a timezone")
    return parsed.astimezone(timezone.utc)


def stamp(value: datetime) -> str:
    value = value.astimezone(timezone.utc)
    if value.microsecond:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON_PARSE_FAILED:{path.name}:{type(exc).__name__}") from exc


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True).encode("utf-8"))
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _artifact_record(path: Path, root: Path, role: str, instrument: str | None = None,
                     granularity: str | None = None, batch_number: int | None = None) -> dict[str, Any]:
    return {
        "relative_path": path.resolve().relative_to(root.resolve()).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "role": role,
        "instrument": instrument,
        "granularity": granularity,
        "batch_number": batch_number,
    }


def _defect(defects: list[dict[str, Any]], code: str, message: str,
            series: str | None = None, path: Path | None = None) -> None:
    defects.append({
        "code": code,
        "message": message,
        "series": series,
        "path": str(path) if path is not None else None,
    })


def _same_utc(left: Any, right: Any) -> bool:
    try:
        return parse_utc(left) == parse_utc(right)
    except (TypeError, ValueError):
        return False


def _price_component_valid(component: Any) -> bool:
    if not isinstance(component, Mapping):
        return False
    try:
        values = {name: Decimal(component[name]) for name in ("o", "h", "l", "c")}
    except (KeyError, InvalidOperation, TypeError):
        return False
    return values["h"] >= max(values["o"], values["l"], values["c"]) and values["l"] <= min(
        values["o"], values["h"], values["c"]
    )


def _bid_ask_valid(candle: Mapping[str, Any]) -> bool:
    if not _price_component_valid(candle.get("bid")) or not _price_component_valid(candle.get("ask")):
        return False
    try:
        return all(Decimal(candle["bid"][name]) <= Decimal(candle["ask"][name]) for name in ("o", "h", "l", "c"))
    except (InvalidOperation, TypeError, KeyError):
        return False


def _weekly_closure(left: datetime, right: datetime, maximum: timedelta = timedelta(hours=96)) -> bool:
    if right - left > maximum:
        return False
    cursor = left.replace(minute=0, second=0, microsecond=0)
    while cursor <= right:
        if cursor.weekday() in (5, 6):
            return True
        cursor += timedelta(hours=1)
    return False


def _series_key(instrument: str, granularity: str) -> str:
    return f"{instrument}/{granularity}"


def _expected_keys(config: VerificationConfig) -> list[tuple[str, str]]:
    return [(instrument, granularity) for instrument in config.instruments for granularity in config.granularities]


def _validate_config(config: VerificationConfig) -> None:
    if len(set(config.instruments)) != len(config.instruments) or len(set(config.granularities)) != len(config.granularities):
        raise DatasetBlockedError("EXPECTED_SCOPE_CONTAINS_DUPLICATES")
    if len(config.instruments) * len(config.granularities) != 21:
        raise DatasetBlockedError("EXPECTED_SCOPE_MUST_CONTAIN_21_SERIES")
    if any(re.fullmatch(r"[A-Z]{3}_[A-Z]{3}", item) is None for item in config.instruments):
        raise DatasetBlockedError("INVALID_EXPECTED_INSTRUMENT")
    if any(item not in GRANULARITY_SECONDS for item in config.granularities):
        raise DatasetBlockedError("INVALID_EXPECTED_GRANULARITY")
    if HEX_64.fullmatch(config.scope_fingerprint) is None:
        raise DatasetBlockedError("INVALID_EXPECTED_SCOPE_FINGERPRINT")
    if parse_utc(config.end_utc) <= parse_utc(config.start_utc):
        raise DatasetBlockedError("INVALID_EXPECTED_DATE_RANGE")
    if config.max_defects <= 0:
        raise DatasetBlockedError("MAX_DEFECTS_MUST_BE_POSITIVE")


def verify_dataset(config: VerificationConfig) -> dict[str, Any]:
    """Validate all collector artifacts and return a bounded receipt."""
    _validate_config(config)
    root = config.source_root.resolve()
    start = parse_utc(config.start_utc)
    end = parse_utc(config.end_utc)
    defects: list[dict[str, Any]] = []
    missing: set[str] = set()
    partial: set[str] = set()
    invalid: set[str] = set()
    artifacts: list[dict[str, Any]] = []
    series_inventory: dict[str, dict[str, Any]] = {}
    raw_gaps: list[dict[str, Any]] = []
    duplicate_count = 0
    overlap_count = 0
    checkpoint_count = 0
    batch_file_count = 0
    nonzero_file_count = 0
    end_bound_confirmed_count = 0

    if not root.is_dir():
        _defect(defects, "SOURCE_ROOT_MISSING", "source root is not a directory", path=root)
        return _final_receipt(config, defects, missing, partial, invalid, artifacts, series_inventory, [], 0, 0, 0, 0, 0, 0, None, None)

    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file() or manifest_path.stat().st_size <= 0:
        _defect(defects, "TERMINAL_MANIFEST_MISSING", "terminal manifest is missing or empty", path=manifest_path)
        return _final_receipt(config, defects, missing, partial, invalid, artifacts, series_inventory, [], 0, 0, 0, 0, 0, 0, None, None)

    nonzero_file_count += 1
    artifacts.append(_artifact_record(manifest_path, root, "terminal_manifest"))
    manifest_sha256 = artifacts[-1]["sha256"]
    try:
        manifest = load_json(manifest_path)
    except ValueError as exc:
        _defect(defects, "MALFORMED_TERMINAL_MANIFEST", str(exc), path=manifest_path)
        return _final_receipt(config, defects, missing, partial, invalid, artifacts, series_inventory, [], 0, 0, 0, 0, 0, 1, manifest_sha256, None)
    if not isinstance(manifest, Mapping):
        _defect(defects, "MANIFEST_NOT_OBJECT", "terminal manifest must be a JSON object", path=manifest_path)
        manifest = {}

    manifest_checks = {
        "MANIFEST_SCHEMA_MISMATCH": manifest.get("schema") == MANIFEST_SCHEMA,
        "SCOPE_FINGERPRINT_MISMATCH": manifest.get("scope_fingerprint") == config.scope_fingerprint,
        "MANIFEST_START_BOUNDARY_MISMATCH": _same_utc(manifest.get("overall_from_utc"), start),
        "MANIFEST_END_BOUNDARY_MISMATCH": _same_utc(manifest.get("overall_to_utc"), end),
        "MANIFEST_FROM_ALIAS_MISMATCH": _same_utc(manifest.get("from_utc"), start),
        "MANIFEST_TO_ALIAS_MISMATCH": _same_utc(manifest.get("to_utc"), end),
        "MANIFEST_BOUNDARY_SEMANTICS_MISMATCH": manifest.get("to_boundary_semantics") == "exclusive",
        "MANIFEST_PAGINATION_MISMATCH": manifest.get("pagination_contract") == "FROM_PLUS_COUNT",
        "MANIFEST_METHOD_MISMATCH": manifest.get("method") == "GET_ONLY",
        "MANIFEST_SERIES_COUNT_MISMATCH": manifest.get("series_count") == 21,
        "MANIFEST_COMPLETE_COUNT_MISMATCH": manifest.get("complete_series") == 21,
        "MANIFEST_INCOMPLETE_COUNT_MISMATCH": manifest.get("incomplete_series") == 0,
        "MANIFEST_COMPLETION_MISSING": bool(manifest.get("completed_utc")),
        "MANIFEST_SAFETY_MISMATCH": manifest.get("secret_value_exposed") is False
        and manifest.get("live_host_contacted") is False and manifest.get("order_attempted") is False
        and manifest.get("broker_mutation") is False,
        "MANIFEST_HELPER_HASH_INVALID": isinstance(manifest.get("helper_sha256"), str)
        and HEX_64.fullmatch(manifest["helper_sha256"]) is not None,
        "MANIFEST_COLLECTOR_HASH_INVALID": isinstance(manifest.get("collector_sha256"), str)
        and HEX_64.fullmatch(manifest["collector_sha256"]) is not None,
        "MANIFEST_INCLUDE_FIRST_STRATEGY_MISMATCH": manifest.get("include_first_strategy")
        == "FIRST_REQUEST_TRUE_THEN_FROM_LAST_ACCEPTED_WITH_INCLUDE_FIRST_FALSE",
        "MANIFEST_TO_SENT_MISMATCH": manifest.get("to_sent_on_each_request") is False,
        "MANIFEST_DUPLICATE_CONTRACT_MISMATCH": manifest.get("duplicate_check")
        == "VALIDATED_PER_BATCH_AND_ACROSS_CHECKPOINT",
        "MANIFEST_GAP_CONTRACT_MISMATCH": manifest.get("gap_check")
        == "PROVIDER_ORDER_PRESERVED_NO_FIXED_INTERVAL_SKIP",
        "MANIFEST_PARALLELISM_MISMATCH": manifest.get("request_parallelism") == 1
        and manifest.get("parallel_request_allowed") is False,
    }
    for code, passed in manifest_checks.items():
        if not passed:
            _defect(defects, code, code.lower().replace("_", " "), path=manifest_path)
    if manifest.get("completed_utc"):
        try:
            parse_utc(manifest["completed_utc"])
        except ValueError:
            _defect(defects, "MANIFEST_COMPLETION_INVALID", "completed_utc is not parseable", path=manifest_path)
    try:
        output_root_matches = Path(str(manifest.get("output_root", ""))).resolve() == root
    except OSError:
        output_root_matches = False
    if not output_root_matches:
        _defect(defects, "MANIFEST_OUTPUT_ROOT_MISMATCH", "manifest output_root does not identify source root", path=manifest_path)

    manifest_series: dict[tuple[str, str], Mapping[str, Any]] = {}
    raw_series = manifest.get("series")
    if not isinstance(raw_series, list):
        _defect(defects, "MANIFEST_SERIES_NOT_LIST", "manifest series must be a list", path=manifest_path)
        raw_series = []
    for item in raw_series:
        if not isinstance(item, Mapping):
            _defect(defects, "MANIFEST_SERIES_ENTRY_INVALID", "series entry is not an object", path=manifest_path)
            continue
        key = (str(item.get("instrument", "")), str(item.get("granularity", "")))
        if key in manifest_series:
            _defect(defects, "MANIFEST_SERIES_DUPLICATE", f"duplicate series entry {key}", path=manifest_path)
            continue
        manifest_series[key] = item
    expected = set(_expected_keys(config))
    unexpected = sorted(set(manifest_series) - expected)
    if unexpected:
        _defect(defects, "UNEXPECTED_SERIES", f"unexpected series: {unexpected}", path=manifest_path)
    expected_directories = {f"{instrument}_{granularity}" for instrument, granularity in expected}
    actual_directories = {path.name for path in root.iterdir() if path.is_dir()}
    if actual_directories != expected_directories:
        _defect(
            defects,
            "SERIES_DIRECTORY_INVENTORY_MISMATCH",
            f"missing={sorted(expected_directories - actual_directories)} unexpected={sorted(actual_directories - expected_directories)}",
            path=root,
        )

    for instrument, granularity in _expected_keys(config):
        key_tuple = (instrument, granularity)
        key = _series_key(instrument, granularity)
        record = manifest_series.get(key_tuple)
        series_dir = root / f"{instrument}_{granularity}"
        checkpoint_path = series_dir / CHECKPOINT_NAME
        if record is None or not series_dir.is_dir() or not checkpoint_path.is_file():
            missing.add(key)
            _defect(defects, "SERIES_MISSING", "manifest, directory, or checkpoint is missing", key, series_dir)
            continue
        if checkpoint_path.stat().st_size <= 0:
            invalid.add(key)
            _defect(defects, "CHECKPOINT_EMPTY", "checkpoint is empty", key, checkpoint_path)
            continue
        checkpoint_count += 1
        nonzero_file_count += 1
        artifacts.append(_artifact_record(checkpoint_path, root, "checkpoint", instrument, granularity))
        try:
            checkpoint = load_json(checkpoint_path)
        except ValueError as exc:
            invalid.add(key)
            _defect(defects, "CHECKPOINT_MALFORMED", str(exc), key, checkpoint_path)
            continue
        if not isinstance(checkpoint, Mapping):
            invalid.add(key)
            _defect(defects, "CHECKPOINT_NOT_OBJECT", "checkpoint must be an object", key, checkpoint_path)
            continue

        manifest_status = str(record.get("status", ""))
        checkpoint_status = str(checkpoint.get("status", ""))
        if manifest_status not in COMPLETE_MANIFEST_STATUSES or checkpoint_status != "SERIES_COMPLETE":
            partial.add(key)
            _defect(defects, "SERIES_PARTIAL", f"manifest={manifest_status} checkpoint={checkpoint_status}", key, checkpoint_path)
            continue

        checks = {
            "CHECKPOINT_SCHEMA_MISMATCH": checkpoint.get("schema") == CHECKPOINT_SCHEMA,
            "CHECKPOINT_SCOPE_MISMATCH": checkpoint.get("scope_fingerprint") == config.scope_fingerprint,
            "CHECKPOINT_INSTRUMENT_MISMATCH": checkpoint.get("instrument") == instrument,
            "CHECKPOINT_GRANULARITY_MISMATCH": checkpoint.get("granularity") == granularity,
            "CHECKPOINT_START_MISMATCH": _same_utc(checkpoint.get("overall_from_utc"), start),
            "CHECKPOINT_END_MISMATCH": _same_utc(checkpoint.get("overall_to_utc"), end),
            "CHECKPOINT_BOUNDARY_MISMATCH": checkpoint.get("to_boundary_semantics") == "exclusive",
            "CHECKPOINT_PAGINATION_MISMATCH": checkpoint.get("pagination_contract") == "FROM_PLUS_COUNT",
            "CHECKPOINT_METHOD_MISMATCH": checkpoint.get("method") == "GET_ONLY",
            "CHECKPOINT_PRICE_MISMATCH": checkpoint.get("price") == "BA",
            "CHECKPOINT_PROVENANCE_MISMATCH": checkpoint.get("helper_sha256") == manifest.get("helper_sha256")
            and checkpoint.get("collector_sha256") == manifest.get("collector_sha256")
            and checkpoint.get("host") == manifest.get("host"),
            "CHECKPOINT_SAFETY_MISMATCH": checkpoint.get("secret_value_exposed") is False
            and checkpoint.get("live_host_contacted") is False and checkpoint.get("order_attempted") is False
            and checkpoint.get("broker_mutation") is False,
            "MANIFEST_SERIES_SCOPE_MISMATCH": record.get("scope_fingerprint") == config.scope_fingerprint,
            "CHECKPOINT_REQUEST_SIZE_MISMATCH": checkpoint.get("candles_per_request") == manifest.get("candles_per_request"),
            "CHECKPOINT_INCLUDE_FIRST_STRATEGY_MISMATCH": checkpoint.get("include_first_strategy")
            == "FIRST_REQUEST_TRUE_THEN_FROM_LAST_ACCEPTED_WITH_INCLUDE_FIRST_FALSE",
            "CHECKPOINT_TO_SENT_MISMATCH": checkpoint.get("to_sent_on_each_request") is False,
        }
        for code, passed in checks.items():
            if not passed:
                invalid.add(key)
                _defect(defects, code, code.lower().replace("_", " "), key, checkpoint_path)

        ledger = checkpoint.get("batches")
        if not isinstance(ledger, list):
            invalid.add(key)
            _defect(defects, "CHECKPOINT_BATCH_LEDGER_INVALID", "batches must be a list", key, checkpoint_path)
            continue
        if checkpoint.get("next_batch_index") != len(ledger):
            invalid.add(key)
            _defect(defects, "CHECKPOINT_BATCH_COUNT_MISMATCH", "next_batch_index differs from ledger length", key, checkpoint_path)
        disk_batches = sorted(series_dir.glob(f"[0-9][0-9][0-9][0-9][0-9][0-9]_{instrument}_{granularity}.json"))
        if len(disk_batches) != len(ledger):
            invalid.add(key)
            _defect(defects, "BATCH_FILE_CONTINUITY_FAILURE", "disk batch count differs from ledger length", key, series_dir)
        all_json_batches = sorted(path for path in series_dir.glob("*.json") if path.name != CHECKPOINT_NAME)
        if all_json_batches != disk_batches:
            invalid.add(key)
            _defect(defects, "BATCH_FILENAME_CONTAMINATION", "unexpected JSON batch filename", key, series_dir)

        manifest_files = record.get("files")
        if not isinstance(manifest_files, list) or len(manifest_files) != len(ledger):
            invalid.add(key)
            _defect(defects, "MANIFEST_FILE_LEDGER_MISMATCH", "manifest file count differs from checkpoint", key, manifest_path)
            manifest_files = []
        total = 0
        previous_time: datetime | None = None
        previous_batch_number: int | None = None
        previous_batch_verified = False
        first_time: datetime | None = None
        last_time: datetime | None = None
        step = timedelta(seconds=GRANULARITY_SECONDS[granularity])

        for batch_number, entry in enumerate(ledger):
            expected_name = f"{batch_number:06d}_{instrument}_{granularity}.json"
            batch_path = series_dir / expected_name
            if not isinstance(entry, Mapping) or entry.get("batch_number") != batch_number:
                invalid.add(key)
                _defect(defects, "CHECKPOINT_LEDGER_SEQUENCE_FAILURE", f"invalid ledger entry {batch_number}", key, checkpoint_path)
                continue
            if not batch_path.is_file() or batch_path.stat().st_size <= 0:
                invalid.add(key)
                _defect(defects, "BATCH_MISSING_OR_EMPTY", expected_name, key, batch_path)
                continue
            batch_file_count += 1
            nonzero_file_count += 1
            artifact = _artifact_record(batch_path, root, "batch", instrument, granularity, batch_number)
            artifacts.append(artifact)
            if not _safe_under(batch_path, root):
                invalid.add(key)
                _defect(defects, "BATCH_OUTSIDE_SOURCE_ROOT", expected_name, key, batch_path)
            try:
                ledger_path = Path(str(entry.get("artifact_path", ""))).resolve()
            except OSError:
                ledger_path = Path()
            checkpoint_artifact_reconciled = (
                ledger_path == batch_path.resolve() and entry.get("artifact_sha256") == artifact["sha256"]
            )
            if not checkpoint_artifact_reconciled:
                invalid.add(key)
                _defect(defects, "CHECKPOINT_ARTIFACT_RECONCILIATION_FAILURE", expected_name, key, batch_path)
            manifest_file = manifest_files[batch_number] if batch_number < len(manifest_files) else {}
            try:
                manifest_file_path = Path(str(manifest_file.get("path", ""))).resolve()
            except (AttributeError, OSError):
                manifest_file_path = Path()
            manifest_artifact_reconciled = (
                isinstance(manifest_file, Mapping)
                and manifest_file_path == batch_path.resolve()
                and manifest_file.get("sha256") == artifact["sha256"]
            )
            if not manifest_artifact_reconciled:
                invalid.add(key)
                _defect(defects, "MANIFEST_FILE_RECONCILIATION_FAILURE", expected_name, key, batch_path)
            try:
                batch = load_json(batch_path)
            except ValueError as exc:
                invalid.add(key)
                _defect(defects, "BATCH_MALFORMED", str(exc), key, batch_path)
                continue
            if not isinstance(batch, Mapping):
                invalid.add(key)
                _defect(defects, "BATCH_NOT_OBJECT", expected_name, key, batch_path)
                continue
            batch_checks = {
                "BATCH_SCHEMA_MISMATCH": batch.get("schema") == BATCH_SCHEMA,
                "BATCH_SOURCE_MISMATCH": batch.get("source") == "OANDA_PRACTICE_INSTRUMENT_CANDLES",
                "BATCH_INSTRUMENT_MISMATCH": batch.get("instrument") == instrument,
                "BATCH_GRANULARITY_MISMATCH": batch.get("granularity") == granularity,
                "BATCH_PRICE_MISMATCH": batch.get("price") == "BA",
                "BATCH_METHOD_MISMATCH": batch.get("method") == "GET_ONLY",
                "BATCH_HOST_MISMATCH": batch.get("host") == manifest.get("host"),
                "BATCH_END_MISMATCH": _same_utc(batch.get("overall_to_utc"), end),
                "BATCH_BOUNDARY_MISMATCH": batch.get("to_boundary_semantics") == "exclusive",
                "BATCH_PAGINATION_MISMATCH": batch.get("pagination_contract") == "FROM_PLUS_COUNT",
                "BATCH_CURSOR_MISMATCH": _same_utc(batch.get("from_utc"), entry.get("request_cursor_utc")),
                "BATCH_INCLUDE_FIRST_MISMATCH": batch.get("include_first") is (batch_number == 0),
                "BATCH_REQUEST_SIZE_MISMATCH": batch.get("candles_per_request") == manifest.get("candles_per_request"),
                "BATCH_TO_SENT_MISMATCH": batch.get("to_sent_on_each_request") is False,
            }
            for code, passed in batch_checks.items():
                if not passed:
                    invalid.add(key)
                    _defect(defects, code, code.lower().replace("_", " "), key, batch_path)
            provider_batch_verified = (
                checkpoint_artifact_reconciled
                and manifest_artifact_reconciled
                and all(batch_checks.values())
            )
            candles = batch.get("candles")
            if not isinstance(candles, list):
                invalid.add(key)
                _defect(defects, "CANDLES_NOT_LIST", expected_name, key, batch_path)
                continue
            declared = batch.get("candle_count")
            accepted = entry.get("accepted_row_count")
            manifest_count = manifest_file.get("candle_count") if isinstance(manifest_file, Mapping) else None
            if declared != len(candles) or accepted != len(candles) or manifest_count != len(candles):
                invalid.add(key)
                _defect(defects, "CANDLE_COUNT_MISMATCH", expected_name, key, batch_path)
            batch_first: datetime | None = None
            batch_last: datetime | None = None
            for candle_index, candle in enumerate(candles):
                if not isinstance(candle, Mapping):
                    invalid.add(key)
                    _defect(defects, "CANDLE_SCHEMA_INVALID", f"{expected_name}:{candle_index}", key, batch_path)
                    continue
                try:
                    candle_time = parse_utc(candle.get("time"))
                except ValueError:
                    invalid.add(key)
                    _defect(defects, "CANDLE_TIMESTAMP_INVALID", f"{expected_name}:{candle_index}", key, batch_path)
                    continue
                if candle.get("complete") is not True or not isinstance(candle.get("volume"), int) or candle["volume"] < 0 or not _bid_ask_valid(candle):
                    invalid.add(key)
                    _defect(defects, "CANDLE_SCHEMA_INVALID", f"{expected_name}:{candle_index}", key, batch_path)
                if not (start <= candle_time < end):
                    invalid.add(key)
                    _defect(defects, "CANDLE_OUTSIDE_REQUESTED_RANGE", stamp(candle_time), key, batch_path)
                if previous_time is not None:
                    if candle_time == previous_time:
                        duplicate_count += 1
                        invalid.add(key)
                        _defect(defects, "DUPLICATE_CANDLE", stamp(candle_time), key, batch_path)
                    elif candle_time < previous_time:
                        overlap_count += 1
                        invalid.add(key)
                        _defect(defects, "UNCONTROLLED_OVERLAP", stamp(candle_time), key, batch_path)
                    elif candle_time - previous_time > step:
                        same_verified_batch = (
                            previous_batch_number == batch_number and provider_batch_verified
                        )
                        pagination_reconciled = False
                        if previous_batch_number == batch_number - 1 and batch_number > 0:
                            previous_entry = ledger[batch_number - 1]
                            pagination_reconciled = (
                                previous_batch_verified
                                and provider_batch_verified
                                and isinstance(previous_entry, Mapping)
                                and _same_utc(previous_entry.get("last_accepted_utc"), previous_time)
                                and _same_utc(entry.get("request_cursor_utc"), previous_entry.get("last_accepted_utc"))
                                and entry.get("include_first") is False
                                and batch.get("include_first") is False
                                and _same_utc(batch.get("from_utc"), entry.get("request_cursor_utc"))
                                and _same_utc(entry.get("first_accepted_utc"), candle_time)
                            )
                        raw_gaps.append({"series": key, "instrument": instrument, "granularity": granularity,
                                         "left_utc": stamp(previous_time), "right_utc": stamp(candle_time),
                                         "missing_steps": int((candle_time - previous_time).total_seconds() // step.total_seconds()) - 1,
                                         "left_batch_number": previous_batch_number,
                                         "right_batch_number": batch_number,
                                         "same_verified_batch": same_verified_batch,
                                         "pagination_reconciled": pagination_reconciled})
                previous_time = candle_time
                previous_batch_number = batch_number
                previous_batch_verified = provider_batch_verified
                batch_first = batch_first or candle_time
                batch_last = candle_time
                first_time = first_time or candle_time
                last_time = candle_time
            if batch_first is None or batch_last is None:
                invalid.add(key)
                _defect(defects, "EMPTY_BATCH", expected_name, key, batch_path)
            else:
                if not _same_utc(entry.get("first_accepted_utc"), batch_first) or not _same_utc(entry.get("last_accepted_utc"), batch_last):
                    invalid.add(key)
                    _defect(defects, "LEDGER_ACCEPTED_BOUNDARY_MISMATCH", expected_name, key, batch_path)
                if not _same_utc(entry.get("next_cursor_utc"), batch_last) or not _same_utc(entry.get("next_local_boundary_utc"), batch_last + step):
                    invalid.add(key)
                    _defect(defects, "LEDGER_NEXT_BOUNDARY_MISMATCH", expected_name, key, batch_path)
                if batch_number == 0:
                    if not _same_utc(entry.get("request_cursor_utc"), start) or entry.get("include_first") is not True:
                        invalid.add(key)
                        _defect(defects, "INITIAL_PAGINATION_MISMATCH", expected_name, key, batch_path)
                else:
                    previous_entry = ledger[batch_number - 1]
                    if not _same_utc(entry.get("request_cursor_utc"), previous_entry.get("last_accepted_utc")) or entry.get("include_first") is not False:
                        invalid.add(key)
                        _defect(defects, "CROSS_BATCH_PAGINATION_MISMATCH", expected_name, key, batch_path)
            total += len(candles)
            if entry.get("cumulative_row_count") != total:
                invalid.add(key)
                _defect(defects, "CUMULATIVE_COUNT_MISMATCH", expected_name, key, checkpoint_path)

        if checkpoint.get("complete_candles") != total or record.get("complete_candles") != total:
            invalid.add(key)
            _defect(defects, "SERIES_TOTAL_MISMATCH", f"computed {total}", key, checkpoint_path)
        if checkpoint.get("next_batch_index") != record.get("batches"):
            invalid.add(key)
            _defect(defects, "MANIFEST_CHECKPOINT_BATCH_MISMATCH", key, key, checkpoint_path)
        if last_time is not None and (not _same_utc(checkpoint.get("last_candle_utc"), last_time) or not _same_utc(record.get("last_candle_utc"), last_time)):
            invalid.add(key)
            _defect(defects, "SERIES_LAST_TIMESTAMP_MISMATCH", key, key, checkpoint_path)
        end_bound_confirmed_count += 1
        series_inventory[key] = {
            "instrument": instrument,
            "granularity": granularity,
            "requested_start_utc": stamp(start),
            "requested_end_utc": stamp(end),
            "first_candle_utc": stamp(first_time) if first_time else None,
            "last_candle_utc": stamp(last_time) if last_time else None,
            "candle_count": total,
            "batch_count": len(ledger),
            "checkpoint_relative_path": checkpoint_path.relative_to(root).as_posix(),
            "end_bound_confirmed": True,
        }

    gap_occurrences: dict[tuple[str, str, str], set[str]] = {}
    for gap in raw_gaps:
        identity = (gap["granularity"], gap["left_utc"], gap["right_utc"])
        gap_occurrences.setdefault(identity, set()).add(gap["instrument"])
    legitimate_gaps: list[dict[str, Any]] = []
    no_price_update_gap_count = 0
    no_price_update_examples: list[dict[str, Any]] = []
    unexplained_gap_count = 0
    for gap in raw_gaps:
        left, right = parse_utc(gap["left_utc"]), parse_utc(gap["right_utc"])
        identity = (gap["granularity"], gap["left_utc"], gap["right_utc"])
        if _weekly_closure(left, right):
            gap["classification"] = "WEEKLY_MARKET_CLOSURE"
            legitimate_gaps.append(gap)
        elif gap_occurrences[identity] == set(config.instruments):
            gap["classification"] = "THREE_INSTRUMENT_PROVIDER_CLOSURE"
            legitimate_gaps.append(gap)
        elif gap["same_verified_batch"] or gap["pagination_reconciled"]:
            # Local collector evidence proves ordered provider output, not why
            # the provider emitted no candle for every nominal interval.
            gap["classification"] = "VERIFIED_PROVIDER_NO_PRICE_UPDATE_INTERVAL"
            no_price_update_gap_count += 1
            if len(no_price_update_examples) < config.max_defects:
                no_price_update_examples.append(gap)
        else:
            gap["classification"] = "UNEXPLAINED_INTERNAL_GAP"
            unexplained_gap_count += 1
            invalid.add(gap["series"])
            _defect(defects, "UNEXPLAINED_INTERNAL_GAP", f"{gap['left_utc']} to {gap['right_utc']}", gap["series"])

    return _final_receipt(
        config, defects, missing, partial, invalid, artifacts, series_inventory, legitimate_gaps,
        unexplained_gap_count, duplicate_count, overlap_count, checkpoint_count, batch_file_count,
        nonzero_file_count, manifest_sha256, manifest,
        no_price_update_gap_count=no_price_update_gap_count,
        no_price_update_examples=no_price_update_examples,
    )


def _final_receipt(config: VerificationConfig, defects: list[dict[str, Any]], missing: set[str], partial: set[str],
                   invalid: set[str], artifacts: list[dict[str, Any]], series_inventory: Mapping[str, dict[str, Any]],
                   legitimate_gaps: list[dict[str, Any]], unexplained_gap_count: int, duplicate_count: int,
                   overlap_count: int, checkpoint_count: int, batch_file_count: int, nonzero_file_count: int,
                   manifest_sha256: str | None, manifest: Mapping[str, Any] | None,
                   no_price_update_gap_count: int = 0,
                   no_price_update_examples: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    expected_keys = {_series_key(a, b) for a, b in _expected_keys(config)}
    missing = set(missing)
    if manifest is None:
        missing |= expected_keys
    partial -= missing
    invalid -= missing | partial
    complete = expected_keys - missing - partial - invalid
    ordered_artifacts = sorted(artifacts, key=lambda item: item["relative_path"])
    ordered_series = [series_inventory[key] for key in sorted(series_inventory)]
    source_state_sha256 = canonical_sha256(ordered_artifacts) if ordered_artifacts else None
    dataset_sha256 = canonical_sha256({"files": ordered_artifacts, "series": ordered_series}) if ordered_artifacts else None
    status = "PASS" if not defects and len(complete) == 21 and not missing and not partial and not invalid else "FAIL"
    collector_provenance = {
        "manifest_schema": manifest.get("schema") if manifest else None,
        "helper_sha256": manifest.get("helper_sha256") if manifest else None,
        "collector_sha256": manifest.get("collector_sha256") if manifest else None,
        "host": manifest.get("host") if manifest else None,
        "method": manifest.get("method") if manifest else None,
        "price": "BA",
        "pagination_contract": manifest.get("pagination_contract") if manifest else None,
        "boundary_semantics": manifest.get("to_boundary_semantics") if manifest else None,
        "gap_classification": {
            "contract": "CLOSURE_OR_HASH_VERIFIED_PROVIDER_BATCH_OR_RECONCILED_PAGINATION_BOUNDARY",
            "market_closure_gap_count": len(legitimate_gaps),
            "no_price_update_interval_count": no_price_update_gap_count,
            "genuine_unexplained_gap_count": unexplained_gap_count,
            "local_evidence_limitation": (
                "Classification proves ordered, hash-reconciled provider output; it does not prove why the provider "
                "emitted no candle for each nominal interval."
            ),
            "no_price_update_examples": list(no_price_update_examples or ()),
        },
        "safety": {
            "secret_value_exposed": manifest.get("secret_value_exposed") if manifest else None,
            "live_host_contacted": manifest.get("live_host_contacted") if manifest else None,
            "order_attempted": manifest.get("order_attempted") if manifest else None,
            "broker_mutation": manifest.get("broker_mutation") if manifest else None,
        },
    }
    total_candles = sum(int(item["candle_count"]) for item in ordered_series)
    return {
        "schema": VALIDATION_SCHEMA,
        "schema_version": "1.0.0",
        "tool_version": TOOL_VERSION,
        "status": status,
        "generated_utc": utc_now(),
        "source_root": str(config.source_root.resolve()),
        "source_head": config.source_head,
        "scope_fingerprint": config.scope_fingerprint,
        "requested_start_utc": stamp(parse_utc(config.start_utc)),
        "requested_end_utc": stamp(parse_utc(config.end_utc)),
        "manifest_path": str((config.source_root.resolve() / MANIFEST_NAME)),
        "manifest_sha256": manifest_sha256,
        "source_state_sha256": source_state_sha256,
        "dataset_sha256": dataset_sha256,
        "series_expected": 21,
        "series_complete": len(complete),
        "series_partial": len(partial),
        "series_missing": len(missing),
        "series_invalid": len(invalid),
        "complete_series": sorted(complete),
        "partial_series": sorted(partial),
        "missing_series": sorted(missing),
        "invalid_series": sorted(invalid),
        "duplicate_count": duplicate_count,
        "overlap_count": overlap_count,
        "unexplained_gap_count": unexplained_gap_count,
        "legitimate_closure_gap_count": len(legitimate_gaps),
        "legitimate_closure_gaps": legitimate_gaps[: config.max_defects],
        "end_bound_confirmed_count": len(complete),
        "checkpoint_count": checkpoint_count,
        "batch_file_count": batch_file_count,
        "nonzero_file_count": nonzero_file_count,
        "total_candle_count": total_candles,
        "series_inventory": ordered_series,
        "file_inventory": ordered_artifacts,
        "defect_count": len(defects),
        "defects": defects[: config.max_defects],
        "defects_truncated": len(defects) > config.max_defects,
        "collector_provenance": collector_provenance,
        "reproducibility_commands": [],
    }


def write_validation_receipt(path: Path, receipt: Mapping[str, Any], command: str) -> None:
    value = dict(receipt)
    value["reproducibility_commands"] = [command]
    atomic_json(path, value)


def _fresh_source_inventory(source_root: Path, inventory: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    fresh: list[dict[str, Any]] = []
    for expected in inventory:
        path = source_root / str(expected["relative_path"])
        if not path.is_file() or not _safe_under(path, source_root):
            raise ValueError(f"SOURCE_DRIFT_MISSING:{expected['relative_path']}")
        current = dict(expected)
        current["bytes"] = path.stat().st_size
        current["sha256"] = sha256_file(path)
        fresh.append(current)
    return sorted(fresh, key=lambda item: item["relative_path"])


def _existing_freeze_matches(destination: Path, receipt: Mapping[str, Any]) -> bool:
    freeze_receipt_path = destination / "AIOS_FOREX_HISTORICAL_DATASET_FREEZE_RECEIPT.json"
    inventory_path = destination / "AIOS_FOREX_HISTORICAL_DATASET_INVENTORY.json"
    validation_path = destination / "AIOS_FOREX_HISTORICAL_DATASET_VALIDATION_RECEIPT.json"
    try:
        frozen = load_json(freeze_receipt_path)
        inventory = load_json(inventory_path)
        validation = load_json(validation_path)
    except ValueError:
        return False
    if frozen.get("dataset_sha256") != receipt.get("dataset_sha256") or validation.get("source_state_sha256") != receipt.get("source_state_sha256"):
        return False
    if inventory.get("file_inventory") != receipt.get("file_inventory"):
        return False
    for item in receipt.get("file_inventory", []):
        target = destination / "source_artifacts" / item["relative_path"]
        if not target.is_file() or target.stat().st_size != item["bytes"] or sha256_file(target) != item["sha256"]:
            return False
    return True


def freeze_dataset(*, source_root: Path, validation_receipt: Path, freeze_root: Path,
                   expected_scope_fingerprint: str, expected_start_utc: str, expected_end_utc: str,
                   source_head: str, command: str, apply_read_only: bool = True,
                   failure_hook: Any = None) -> dict[str, Any]:
    """Promote an exactly verified source state into a copy-once dataset."""
    source_root = source_root.resolve()
    freeze_root = freeze_root.resolve()
    try:
        receipt = load_json(validation_receipt)
    except ValueError as exc:
        return {"status": "FAIL", "reason": str(exc), "schema": FREEZE_SCHEMA}
    required_equal = {
        "status": "PASS",
        "source_root": str(source_root),
        "scope_fingerprint": expected_scope_fingerprint,
        "requested_start_utc": stamp(parse_utc(expected_start_utc)),
        "requested_end_utc": stamp(parse_utc(expected_end_utc)),
        "source_head": source_head,
    }
    for field, expected in required_equal.items():
        if receipt.get(field) != expected:
            return {"status": "FAIL", "reason": f"VALIDATION_RECEIPT_{field.upper()}_MISMATCH", "schema": FREEZE_SCHEMA}
    if receipt.get("series_complete") != 21 or any(receipt.get(name) != 0 for name in ("series_partial", "series_missing", "series_invalid", "duplicate_count", "overlap_count", "unexplained_gap_count")):
        return {"status": "FAIL", "reason": "VALIDATION_RECEIPT_ACCEPTANCE_FAILURE", "schema": FREEZE_SCHEMA}
    dataset_hash = receipt.get("dataset_sha256")
    source_state_hash = receipt.get("source_state_sha256")
    manifest_hash = receipt.get("manifest_sha256")
    if not all(isinstance(item, str) and HEX_64.fullmatch(item) for item in (dataset_hash, source_state_hash, manifest_hash)):
        return {"status": "FAIL", "reason": "VALIDATION_RECEIPT_HASH_INVALID", "schema": FREEZE_SCHEMA}
    inventory = receipt.get("file_inventory")
    if not isinstance(inventory, list) or not inventory:
        return {"status": "FAIL", "reason": "VALIDATION_RECEIPT_INVENTORY_MISSING", "schema": FREEZE_SCHEMA}
    try:
        fresh = _fresh_source_inventory(source_root, inventory)
    except ValueError as exc:
        return {"status": "FAIL", "reason": str(exc), "schema": FREEZE_SCHEMA}
    if fresh != inventory or canonical_sha256(fresh) != source_state_hash:
        return {"status": "FAIL", "reason": "SOURCE_DRIFT_BEFORE_FREEZE", "schema": FREEZE_SCHEMA}
    if sha256_file(source_root / MANIFEST_NAME) != manifest_hash:
        return {"status": "FAIL", "reason": "SOURCE_MANIFEST_DRIFT", "schema": FREEZE_SCHEMA}

    dataset_id = f"AIOS-FX-HIST-V1-{dataset_hash[:20]}"
    destination = freeze_root / dataset_id
    if destination.exists():
        if _existing_freeze_matches(destination, receipt):
            return {
                "schema": FREEZE_SCHEMA, "schema_version": "1.0.0", "tool_version": TOOL_VERSION,
                "status": "PASS", "dataset_id": dataset_id, "dataset_sha256": dataset_hash,
                "source_state_sha256": source_state_hash, "manifest_sha256": manifest_hash,
                "immutable_dataset_path": str(destination), "idempotent": True,
            }
        return {"status": "FAIL", "reason": "DESTINATION_COLLISION", "schema": FREEZE_SCHEMA, "dataset_id": dataset_id}

    freeze_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{dataset_id}.", suffix=".tmp", dir=freeze_root))
    promoted = False
    try:
        source_copy = temporary / "source_artifacts"
        for item in inventory:
            source = source_root / item["relative_path"]
            target = source_copy / item["relative_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if target.stat().st_size != item["bytes"] or sha256_file(target) != item["sha256"]:
                raise ValueError(f"FROZEN_COPY_HASH_MISMATCH:{item['relative_path']}")
        if failure_hook is not None:
            failure_hook(temporary)
        after_copy = _fresh_source_inventory(source_root, inventory)
        if after_copy != inventory or canonical_sha256(after_copy) != source_state_hash:
            raise ValueError("SOURCE_DRIFT_DURING_FREEZE")
        inventory_doc = {
            "schema": "AIOS_FOREX_HISTORICAL_DATASET_INVENTORY.v1",
            "dataset_id": dataset_id,
            "dataset_sha256": dataset_hash,
            "scope_fingerprint": expected_scope_fingerprint,
            "series_inventory": receipt["series_inventory"],
            "file_inventory": inventory,
        }
        validation_copy = dict(receipt)
        validation_hash = sha256_file(validation_receipt)
        freeze_receipt = {
            "schema": FREEZE_SCHEMA,
            "schema_version": "1.0.0",
            "tool_version": TOOL_VERSION,
            "status": "PASS",
            "generated_utc": utc_now(),
            "dataset_id": dataset_id,
            "immutable_dataset_path": str(destination),
            "source_root": str(source_root),
            "source_head": source_head,
            "scope_fingerprint": expected_scope_fingerprint,
            "requested_start_utc": stamp(parse_utc(expected_start_utc)),
            "requested_end_utc": stamp(parse_utc(expected_end_utc)),
            "manifest_sha256": manifest_hash,
            "source_state_sha256": source_state_hash,
            "dataset_sha256": dataset_hash,
            "validation_receipt_sha256": validation_hash,
            "series_expected": 21,
            "series_complete": 21,
            "series_inventory": receipt["series_inventory"],
            "total_candle_count": receipt["total_candle_count"],
            "collector_provenance": receipt["collector_provenance"],
            "file_count": len(inventory),
            "copy_method": "VERIFIED_BYTE_COPY_ATOMIC_PROMOTION",
            "read_only_applied": bool(apply_read_only),
            "idempotent": False,
            "reproducibility_commands": list(receipt.get("reproducibility_commands", [])) + [command],
        }
        atomic_json(temporary / "AIOS_FOREX_HISTORICAL_DATASET_INVENTORY.json", inventory_doc)
        shutil.copyfile(validation_receipt, temporary / "AIOS_FOREX_HISTORICAL_DATASET_VALIDATION_RECEIPT.json")
        atomic_json(temporary / "AIOS_FOREX_HISTORICAL_DATASET_FREEZE_RECEIPT.json", freeze_receipt)
        atomic_text(temporary / "AIOS_FOREX_HISTORICAL_DATASET_SUMMARY.md", _freeze_summary(freeze_receipt))
        if apply_read_only:
            for path in temporary.rglob("*"):
                if path.is_file():
                    path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.replace(temporary, destination)
        promoted = True
        return freeze_receipt
    except (OSError, ValueError) as exc:
        return {"status": "FAIL", "reason": str(exc), "schema": FREEZE_SCHEMA, "dataset_id": dataset_id}
    finally:
        if not promoted and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=False)


def _freeze_summary(receipt: Mapping[str, Any]) -> str:
    return (
        "# AIOS Historical Dataset Freeze\n\n"
        f"- Status: `{receipt['status']}`\n"
        f"- Dataset ID: `{receipt['dataset_id']}`\n"
        f"- Dataset SHA-256: `{receipt['dataset_sha256']}`\n"
        f"- Scope fingerprint: `{receipt['scope_fingerprint']}`\n"
        f"- Series: {receipt['series_complete']}/{receipt['series_expected']}\n"
        f"- Candles: {receipt['total_candle_count']}\n"
    )


def owner_summary(result: Mapping[str, Any]) -> str:
    if result.get("schema") == VALIDATION_SCHEMA:
        return (
            f"DATASET_VALIDATION={result.get('status')} "
            f"SERIES={result.get('series_complete')}/{result.get('series_expected')} "
            f"PARTIAL={result.get('series_partial')} MISSING={result.get('series_missing')} "
            f"INVALID={result.get('series_invalid')} CANDLES={result.get('total_candle_count')} "
            f"DUPLICATES={result.get('duplicate_count')} OVERLAPS={result.get('overlap_count')} "
            f"UNEXPLAINED_GAPS={result.get('unexplained_gap_count')}"
        )
    return (
        f"DATASET_FREEZE={result.get('status')} DATASET_ID={result.get('dataset_id', 'NONE')} "
        f"DATASET_SHA256={result.get('dataset_sha256', 'NONE')} IDEMPOTENT={result.get('idempotent', False)} "
        f"REASON={result.get('reason', 'NONE')}"
    )


def _command_text(argv: Sequence[str]) -> str:
    return "python scripts/forex_delivery/run_forex_historical_dataset_verifier_freezer_v1.py " + " ".join(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify or freeze the AIOS 21-series historical dataset")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--source-root", type=Path, required=True)
    verify.add_argument("--expected-scope-fingerprint", required=True)
    verify.add_argument("--expected-start-utc", required=True)
    verify.add_argument("--expected-end-utc", required=True)
    verify.add_argument("--expected-instruments", nargs="+", default=list(EXPECTED_INSTRUMENTS))
    verify.add_argument("--expected-granularities", nargs="+", default=list(EXPECTED_GRANULARITIES))
    verify.add_argument("--source-head", required=True)
    verify.add_argument("--validation-receipt", type=Path)
    verify.add_argument("--max-defects", type=int, default=100)
    verify.add_argument("--output-format", choices=("json", "human", "both"), default="both")
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--source-root", type=Path, required=True)
    freeze.add_argument("--validation-receipt", type=Path, required=True)
    freeze.add_argument("--freeze-root", type=Path, required=True)
    freeze.add_argument("--expected-scope-fingerprint", required=True)
    freeze.add_argument("--expected-start-utc", required=True)
    freeze.add_argument("--expected-end-utc", required=True)
    freeze.add_argument("--source-head", required=True)
    freeze.add_argument("--output-format", choices=("json", "human", "both"), default="both")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    effective_argv = list(argv) if argv is not None else list(os.sys.argv[1:])
    command = _command_text(effective_argv)
    try:
        if args.operation == "verify":
            config = VerificationConfig(
                source_root=args.source_root,
                scope_fingerprint=args.expected_scope_fingerprint,
                start_utc=args.expected_start_utc,
                end_utc=args.expected_end_utc,
                instruments=tuple(args.expected_instruments),
                granularities=tuple(args.expected_granularities),
                source_head=args.source_head,
                max_defects=args.max_defects,
            )
            result = verify_dataset(config)
            result["reproducibility_commands"] = [command]
            if args.validation_receipt is not None:
                atomic_json(args.validation_receipt, result)
        else:
            result = freeze_dataset(
                source_root=args.source_root,
                validation_receipt=args.validation_receipt,
                freeze_root=args.freeze_root,
                expected_scope_fingerprint=args.expected_scope_fingerprint,
                expected_start_utc=args.expected_start_utc,
                expected_end_utc=args.expected_end_utc,
                source_head=args.source_head,
                command=command,
            )
    except (DatasetBlockedError, OSError, ValueError) as exc:
        result = {"status": "BLOCKED", "reason": str(exc), "tool_version": TOOL_VERSION}
    if args.output_format in ("json", "both"):
        compact = {key: result.get(key) for key in (
            "status", "reason", "dataset_id", "dataset_sha256", "source_state_sha256", "manifest_sha256",
            "series_expected", "series_complete", "series_partial", "series_missing", "series_invalid",
            "total_candle_count", "duplicate_count", "overlap_count", "unexplained_gap_count",
            "legitimate_closure_gap_count", "defect_count", "defects_truncated", "idempotent",
        ) if key in result}
        compact["defects"] = result.get("defects", [])
        print(json.dumps(compact, sort_keys=True, separators=(",", ":")))
    if args.output_format in ("human", "both"):
        print(owner_summary(result))
    return 0 if result.get("status") == "PASS" else 1 if result.get("status") == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
