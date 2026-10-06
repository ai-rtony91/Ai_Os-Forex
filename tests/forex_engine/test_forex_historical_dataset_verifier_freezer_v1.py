from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from automation.forex_engine.forex_historical_dataset_verifier_freezer_v1 import (
    BATCH_SCHEMA,
    CHECKPOINT_NAME,
    CHECKPOINT_SCHEMA,
    EXPECTED_GRANULARITIES,
    EXPECTED_INSTRUMENTS,
    GRANULARITY_SECONDS,
    MANIFEST_NAME,
    MANIFEST_SCHEMA,
    VerificationConfig,
    freeze_dataset,
    main,
    sha256_file,
    stamp,
    verify_dataset,
)


FINGERPRINT = "e7ea1cf452a0cbafc9e2071c250c81b6cef242f800e2a2d0e694bcabfbade680"
HEAD = "b86c65140ed03d53d6c8d6c3618e50da0502f51b"
START = datetime(2024, 1, 1, tzinfo=timezone.utc)
END = datetime(2024, 1, 2, tzinfo=timezone.utc)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def candle(moment: datetime) -> dict:
    return {
        "complete": True,
        "time": stamp(moment),
        "volume": 10,
        "bid": {"o": "1.1000", "h": "1.1010", "l": "1.0990", "c": "1.1005"},
        "ask": {"o": "1.1002", "h": "1.1012", "l": "1.0992", "c": "1.1007"},
    }


def build_fixture(root: Path, *, start: datetime = START, end: datetime = END,
                  second_time: datetime | None = None) -> Path:
    helper_hash = "a" * 64
    collector_hash = "b" * 64
    host = "https://api-fxpractice.example.invalid"
    series_records = []
    for instrument in EXPECTED_INSTRUMENTS:
        for granularity in EXPECTED_GRANULARITIES:
            step = timedelta(seconds=GRANULARITY_SECONDS[granularity])
            moments = [start, second_time or start + step]
            series_dir = root / f"{instrument}_{granularity}"
            ledger = []
            files = []
            total = 0
            for number, moment in enumerate(moments):
                request_cursor = start if number == 0 else moments[number - 1]
                name = f"{number:06d}_{instrument}_{granularity}.json"
                path = series_dir / name
                document = {
                    "schema": BATCH_SCHEMA,
                    "source": "OANDA_PRACTICE_INSTRUMENT_CANDLES",
                    "host": host,
                    "method": "GET_ONLY",
                    "instrument": instrument,
                    "granularity": granularity,
                    "price": "BA",
                    "from_utc": stamp(request_cursor),
                    "include_first": number == 0,
                    "overall_to_utc": stamp(end),
                    "to_boundary_semantics": "exclusive",
                    "pagination_contract": "FROM_PLUS_COUNT",
                    "to_sent_on_each_request": False,
                    "candles_per_request": 5000,
                    "candle_count": 1,
                    "candles": [candle(moment)],
                }
                write_json(path, document)
                digest = sha256_file(path)
                total += 1
                ledger.append({
                    "instrument": instrument,
                    "granularity": granularity,
                    "batch_number": number,
                    "request_cursor_utc": stamp(request_cursor),
                    "include_first": number == 0,
                    "first_accepted_utc": stamp(moment),
                    "last_accepted_utc": stamp(moment),
                    "accepted_row_count": 1,
                    "cumulative_row_count": total,
                    "artifact_path": str(path.resolve()),
                    "artifact_sha256": digest,
                    "next_cursor_utc": stamp(moment),
                    "next_local_boundary_utc": stamp(moment + step),
                    "completed": False,
                })
                files.append({"path": str(path.resolve()), "sha256": digest, "candle_count": 1})
            checkpoint = {
                "schema": CHECKPOINT_SCHEMA,
                "scope_fingerprint": FINGERPRINT,
                "helper_sha256": helper_hash,
                "collector_sha256": collector_hash,
                "status": "SERIES_COMPLETE",
                "host": host,
                "method": "GET_ONLY",
                "instrument": instrument,
                "granularity": granularity,
                "price": "BA",
                "overall_from_utc": stamp(start),
                "overall_to_utc": stamp(end),
                "to_boundary_semantics": "exclusive",
                "pagination_contract": "FROM_PLUS_COUNT",
                "to_sent_on_each_request": False,
                "include_first_strategy": "FIRST_REQUEST_TRUE_THEN_FROM_LAST_ACCEPTED_WITH_INCLUDE_FIRST_FALSE",
                "candles_per_request": 5000,
                "next_cursor_utc": stamp(moments[-1]),
                "next_batch_index": len(moments),
                "complete_candles": total,
                "last_candle_utc": stamp(moments[-1]),
                "next_local_boundary_utc": stamp(moments[-1] + step),
                "batches": ledger,
                "secret_value_exposed": False,
                "live_host_contacted": False,
                "order_attempted": False,
                "broker_mutation": False,
                "updated_utc": stamp(end),
            }
            write_json(series_dir / CHECKPOINT_NAME, checkpoint)
            series_records.append({
                "instrument": instrument,
                "granularity": granularity,
                "complete_candles": total,
                "batches": len(moments),
                "last_candle_utc": stamp(moments[-1]),
                "status": "SERIES_COMPLETE",
                "scope_fingerprint": FINGERPRINT,
                "files": files,
            })
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "scope_fingerprint": FINGERPRINT,
        "helper_sha256": helper_hash,
        "collector_sha256": collector_hash,
        "host": host,
        "method": "GET_ONLY",
        "output_root": str(root.resolve()),
        "overall_from_utc": stamp(start),
        "overall_to_utc": stamp(end),
        "from_utc": stamp(start),
        "to_utc": stamp(end),
        "to_boundary_semantics": "exclusive",
        "pagination_contract": "FROM_PLUS_COUNT",
        "to_sent_on_each_request": False,
        "include_first_strategy": "FIRST_REQUEST_TRUE_THEN_FROM_LAST_ACCEPTED_WITH_INCLUDE_FIRST_FALSE",
        "candles_per_request": 5000,
        "request_timeout_seconds": 30,
        "batch_count": 5000,
        "max_batches_per_series": 0,
        "started_utc": stamp(start),
        "completed_utc": stamp(end),
        "series_count": 21,
        "complete_series": 21,
        "incomplete_series": 0,
        "duplicate_check": "VALIDATED_PER_BATCH_AND_ACROSS_CHECKPOINT",
        "gap_check": "PROVIDER_ORDER_PRESERVED_NO_FIXED_INTERVAL_SKIP",
        "request_parallelism": 1,
        "parallel_request_allowed": False,
        "burst_control": "SINGLE_SEQUENTIAL_REQUEST_LOOP_WITH_BOUNDED_RETRY",
        "secret_value_exposed": False,
        "live_host_contacted": False,
        "order_attempted": False,
        "broker_mutation": False,
        "series": series_records,
    }
    write_json(root / MANIFEST_NAME, manifest)
    return root


def config(root: Path, *, start: datetime = START, end: datetime = END,
           fingerprint: str = FINGERPRINT) -> VerificationConfig:
    return VerificationConfig(root, fingerprint, stamp(start), stamp(end), source_head=HEAD)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def refresh_batch_hash(root: Path, instrument: str, granularity: str, number: int) -> None:
    path = root / f"{instrument}_{granularity}" / f"{number:06d}_{instrument}_{granularity}.json"
    digest = sha256_file(path)
    checkpoint_path = path.parent / CHECKPOINT_NAME
    checkpoint = load(checkpoint_path)
    checkpoint["batches"][number]["artifact_sha256"] = digest
    write_json(checkpoint_path, checkpoint)
    manifest_path = root / MANIFEST_NAME
    manifest = load(manifest_path)
    record = next(item for item in manifest["series"] if item["instrument"] == instrument and item["granularity"] == granularity)
    record["files"][number]["sha256"] = digest
    write_json(manifest_path, manifest)


def set_second_time(root: Path, instrument: str, granularity: str, moment: datetime) -> None:
    series_dir = root / f"{instrument}_{granularity}"
    batch_path = series_dir / f"000001_{instrument}_{granularity}.json"
    batch = load(batch_path)
    batch["candles"][0]["time"] = stamp(moment)
    write_json(batch_path, batch)
    digest = sha256_file(batch_path)
    checkpoint_path = series_dir / CHECKPOINT_NAME
    checkpoint = load(checkpoint_path)
    step = timedelta(seconds=GRANULARITY_SECONDS[granularity])
    entry = checkpoint["batches"][1]
    entry["first_accepted_utc"] = stamp(moment)
    entry["last_accepted_utc"] = stamp(moment)
    entry["next_cursor_utc"] = stamp(moment)
    entry["next_local_boundary_utc"] = stamp(moment + step)
    entry["artifact_sha256"] = digest
    checkpoint["next_cursor_utc"] = stamp(moment)
    checkpoint["last_candle_utc"] = stamp(moment)
    checkpoint["next_local_boundary_utc"] = stamp(moment + step)
    write_json(checkpoint_path, checkpoint)
    manifest_path = root / MANIFEST_NAME
    manifest = load(manifest_path)
    record = next(item for item in manifest["series"] if item["instrument"] == instrument and item["granularity"] == granularity)
    record["last_candle_utc"] = stamp(moment)
    record["files"][1]["sha256"] = digest
    write_json(manifest_path, manifest)


def set_second_batch_candles(root: Path, instrument: str, granularity: str,
                             moments: list[datetime]) -> None:
    series_dir = root / f"{instrument}_{granularity}"
    batch_path = series_dir / f"000001_{instrument}_{granularity}.json"
    batch = load(batch_path)
    batch["candles"] = [candle(moment) for moment in moments]
    batch["candle_count"] = len(moments)
    write_json(batch_path, batch)
    digest = sha256_file(batch_path)
    checkpoint_path = series_dir / CHECKPOINT_NAME
    checkpoint = load(checkpoint_path)
    step = timedelta(seconds=GRANULARITY_SECONDS[granularity])
    entry = checkpoint["batches"][1]
    entry["first_accepted_utc"] = stamp(moments[0])
    entry["last_accepted_utc"] = stamp(moments[-1])
    entry["accepted_row_count"] = len(moments)
    entry["cumulative_row_count"] = 1 + len(moments)
    entry["next_cursor_utc"] = stamp(moments[-1])
    entry["next_local_boundary_utc"] = stamp(moments[-1] + step)
    entry["artifact_sha256"] = digest
    checkpoint["next_cursor_utc"] = stamp(moments[-1])
    checkpoint["complete_candles"] = 1 + len(moments)
    checkpoint["last_candle_utc"] = stamp(moments[-1])
    checkpoint["next_local_boundary_utc"] = stamp(moments[-1] + step)
    write_json(checkpoint_path, checkpoint)
    manifest_path = root / MANIFEST_NAME
    manifest = load(manifest_path)
    record = next(item for item in manifest["series"] if item["instrument"] == instrument and item["granularity"] == granularity)
    record["complete_candles"] = 1 + len(moments)
    record["last_candle_utc"] = stamp(moments[-1])
    record["files"][1]["sha256"] = digest
    record["files"][1]["candle_count"] = len(moments)
    write_json(manifest_path, manifest)


def source_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in sorted(root.rglob("*.json"))}


def verified_receipt(root: Path, receipt_path: Path) -> dict:
    receipt = verify_dataset(config(root))
    receipt["reproducibility_commands"] = ["verify synthetic fixture"]
    write_json(receipt_path, receipt)
    assert receipt["status"] == "PASS"
    return receipt


def defect_codes(result: dict) -> set[str]:
    return {item["code"] for item in result["defects"]}


def test_valid_21_series_fixture_passes(tmp_path: Path):
    result = verify_dataset(config(build_fixture(tmp_path / "source")))
    assert result["status"] == "PASS"
    assert (result["series_complete"], result["series_partial"], result["series_missing"], result["series_invalid"]) == (21, 0, 0, 0)
    assert result["total_candle_count"] == 42
    assert result["checkpoint_count"] == 21 and result["batch_file_count"] == 42


def test_missing_series_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    for path in (root / "EUR_USD_M1").iterdir():
        path.unlink()
    (root / "EUR_USD_M1").rmdir()
    result = verify_dataset(config(root))
    assert result["status"] == "FAIL" and result["series_missing"] == 1


def test_partial_series_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    checkpoint_path = root / "EUR_USD_M1" / CHECKPOINT_NAME
    checkpoint = load(checkpoint_path)
    checkpoint["status"] = "SERIES_PARTIAL"
    write_json(checkpoint_path, checkpoint)
    result = verify_dataset(config(root))
    assert result["status"] == "FAIL" and result["series_partial"] == 1


def test_invalid_series_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    path = root / "EUR_USD_M1" / "000000_EUR_USD_M1.json"
    batch = load(path)
    batch["candles"][0]["bid"]["h"] = "1.0000"
    write_json(path, batch)
    refresh_batch_hash(root, "EUR_USD", "M1", 0)
    result = verify_dataset(config(root))
    assert result["status"] == "FAIL" and result["series_invalid"] >= 1
    assert "CANDLE_SCHEMA_INVALID" in defect_codes(result)


def test_malformed_manifest_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    (root / MANIFEST_NAME).write_text("{", encoding="utf-8")
    result = verify_dataset(config(root))
    assert result["status"] == "FAIL" and "MALFORMED_TERMINAL_MANIFEST" in defect_codes(result)


def test_checkpoint_mismatch_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    path = root / "EUR_USD_M1" / CHECKPOINT_NAME
    checkpoint = load(path)
    checkpoint["instrument"] = "GBP_USD"
    write_json(path, checkpoint)
    result = verify_dataset(config(root))
    assert "CHECKPOINT_INSTRUMENT_MISMATCH" in defect_codes(result)


def test_missing_batch_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    (root / "EUR_USD_M1" / "000001_EUR_USD_M1.json").unlink()
    result = verify_dataset(config(root))
    assert result["status"] == "FAIL" and "BATCH_MISSING_OR_EMPTY" in defect_codes(result)


def test_altered_batch_hash_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    path = root / "EUR_USD_M1" / "000000_EUR_USD_M1.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    result = verify_dataset(config(root))
    assert "CHECKPOINT_ARTIFACT_RECONCILIATION_FAILURE" in defect_codes(result)


def test_declared_actual_candle_count_mismatch_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    path = root / "EUR_USD_M1" / "000000_EUR_USD_M1.json"
    batch = load(path)
    batch["candle_count"] = 2
    write_json(path, batch)
    refresh_batch_hash(root, "EUR_USD", "M1", 0)
    assert "CANDLE_COUNT_MISMATCH" in defect_codes(verify_dataset(config(root)))


def test_duplicate_candle_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    path = root / "EUR_USD_M1" / "000000_EUR_USD_M1.json"
    batch = load(path)
    batch["candles"].append(dict(batch["candles"][0]))
    batch["candle_count"] = 2
    write_json(path, batch)
    refresh_batch_hash(root, "EUR_USD", "M1", 0)
    result = verify_dataset(config(root))
    assert result["duplicate_count"] >= 1 and "DUPLICATE_CANDLE" in defect_codes(result)


def test_out_of_order_candle_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    path = root / "EUR_USD_M1" / "000000_EUR_USD_M1.json"
    batch = load(path)
    batch["candles"] = [candle(START + timedelta(minutes=1)), candle(START)]
    batch["candle_count"] = 2
    write_json(path, batch)
    refresh_batch_hash(root, "EUR_USD", "M1", 0)
    result = verify_dataset(config(root))
    assert result["overlap_count"] >= 1 and "UNCONTROLLED_OVERLAP" in defect_codes(result)


def test_cross_batch_duplicate_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    set_second_time(root, "EUR_USD", "M1", START)
    result = verify_dataset(config(root))
    assert result["duplicate_count"] >= 1


def test_cross_batch_overlap_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    set_second_time(root, "EUR_USD", "M1", START - timedelta(seconds=1))
    result = verify_dataset(config(root))
    assert result["overlap_count"] >= 1 and "UNCONTROLLED_OVERLAP" in defect_codes(result)


@pytest.mark.parametrize(("field", "value", "code"), [
    ("instrument", "GBP_USD", "BATCH_INSTRUMENT_MISMATCH"),
    ("granularity", "M2", "BATCH_GRANULARITY_MISMATCH"),
])
def test_pair_or_granularity_contamination_fails(tmp_path: Path, field: str, value: str, code: str):
    root = build_fixture(tmp_path / "source")
    path = root / "EUR_USD_M1" / "000000_EUR_USD_M1.json"
    batch = load(path)
    batch[field] = value
    write_json(path, batch)
    refresh_batch_hash(root, "EUR_USD", "M1", 0)
    assert code in defect_codes(verify_dataset(config(root)))


def test_reconciled_cross_batch_no_price_update_gap_is_accepted(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    set_second_time(root, "EUR_USD", "M1", START + timedelta(minutes=5))
    result = verify_dataset(config(root))
    classification = result["collector_provenance"]["gap_classification"]
    assert result["status"] == "PASS"
    assert result["unexplained_gap_count"] == 0
    assert classification["no_price_update_interval_count"] == 1


def test_same_verified_batch_no_price_update_gap_is_accepted(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    set_second_batch_candles(
        root,
        "EUR_USD",
        "M1",
        [START + timedelta(minutes=1), START + timedelta(minutes=5)],
    )
    result = verify_dataset(config(root))
    classification = result["collector_provenance"]["gap_classification"]
    assert result["status"] == "PASS"
    assert result["unexplained_gap_count"] == 0
    assert classification["no_price_update_interval_count"] == 1


def test_unreconciled_cross_batch_gap_still_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    set_second_time(root, "EUR_USD", "M1", START + timedelta(minutes=5))
    series_dir = root / "EUR_USD_M1"
    batch_path = series_dir / "000001_EUR_USD_M1.json"
    checkpoint_path = series_dir / CHECKPOINT_NAME
    wrong_cursor = START + timedelta(seconds=30)
    batch = load(batch_path)
    batch["from_utc"] = stamp(wrong_cursor)
    write_json(batch_path, batch)
    checkpoint = load(checkpoint_path)
    checkpoint["batches"][1]["request_cursor_utc"] = stamp(wrong_cursor)
    write_json(checkpoint_path, checkpoint)
    refresh_batch_hash(root, "EUR_USD", "M1", 1)
    result = verify_dataset(config(root))
    assert result["unexplained_gap_count"] == 1
    assert "UNEXPLAINED_INTERNAL_GAP" in defect_codes(result)
    assert "CROSS_BATCH_PAGINATION_MISMATCH" in defect_codes(result)


def test_legitimate_weekly_closure_is_accepted(tmp_path: Path):
    friday = datetime(2024, 1, 5, 21, 0, tzinfo=timezone.utc)
    sunday = datetime(2024, 1, 7, 22, 0, tzinfo=timezone.utc)
    root = build_fixture(tmp_path / "source", start=friday, end=datetime(2024, 1, 8, tzinfo=timezone.utc), second_time=sunday)
    result = verify_dataset(config(root, start=friday, end=datetime(2024, 1, 8, tzinfo=timezone.utc)))
    assert result["status"] == "PASS" and result["legitimate_closure_gap_count"] == 21


def test_provider_wide_closure_requires_three_instrument_consensus(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    moment = START + timedelta(minutes=10)
    for instrument in EXPECTED_INSTRUMENTS:
        set_second_time(root, instrument, "M1", moment)
    result = verify_dataset(config(root))
    assert result["status"] == "PASS" and result["legitimate_closure_gap_count"] == 3


@pytest.mark.parametrize(("start", "end", "code"), [
    (START + timedelta(seconds=1), END, "MANIFEST_START_BOUNDARY_MISMATCH"),
    (START, END + timedelta(seconds=1), "MANIFEST_END_BOUNDARY_MISMATCH"),
])
def test_incorrect_boundary_fails(tmp_path: Path, start: datetime, end: datetime, code: str):
    root = build_fixture(tmp_path / "source")
    assert code in defect_codes(verify_dataset(config(root, start=start, end=end)))


def test_incorrect_scope_fingerprint_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    result = verify_dataset(config(root, fingerprint="f" * 64))
    assert result["status"] == "FAIL" and "SCOPE_FINGERPRINT_MISMATCH" in defect_codes(result)


def test_source_drift_before_freeze_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    receipt_path = tmp_path / "validation.json"
    verified_receipt(root, receipt_path)
    path = root / "EUR_USD_M1" / "000000_EUR_USD_M1.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    result = freeze_dataset(source_root=root, validation_receipt=receipt_path, freeze_root=tmp_path / "frozen",
                            expected_scope_fingerprint=FINGERPRINT, expected_start_utc=stamp(START),
                            expected_end_utc=stamp(END), source_head=HEAD, command="freeze synthetic")
    assert result["status"] == "FAIL" and result["reason"] == "SOURCE_DRIFT_BEFORE_FREEZE"


def test_destination_collision_fails(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    receipt_path = tmp_path / "validation.json"
    receipt = verified_receipt(root, receipt_path)
    destination = tmp_path / "frozen" / f"AIOS-FX-HIST-V1-{receipt['dataset_sha256'][:20]}"
    destination.mkdir(parents=True)
    (destination / "unrelated.txt").write_text("collision", encoding="utf-8")
    result = freeze_dataset(source_root=root, validation_receipt=receipt_path, freeze_root=tmp_path / "frozen",
                            expected_scope_fingerprint=FINGERPRINT, expected_start_utc=stamp(START),
                            expected_end_utc=stamp(END), source_head=HEAD, command="freeze synthetic")
    assert result["status"] == "FAIL" and result["reason"] == "DESTINATION_COLLISION"


def test_identical_freeze_is_idempotent_and_source_is_unchanged(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    receipt_path = tmp_path / "validation.json"
    verified_receipt(root, receipt_path)
    before = source_hashes(root)
    kwargs = dict(source_root=root, validation_receipt=receipt_path, freeze_root=tmp_path / "frozen",
                  expected_scope_fingerprint=FINGERPRINT, expected_start_utc=stamp(START),
                  expected_end_utc=stamp(END), source_head=HEAD, command="freeze synthetic", apply_read_only=False)
    first = freeze_dataset(**kwargs)
    second = freeze_dataset(**kwargs)
    assert first["status"] == "PASS" and first["idempotent"] is False
    assert second["status"] == "PASS" and second["idempotent"] is True
    assert source_hashes(root) == before


def test_atomic_failure_leaves_no_promoted_dataset(tmp_path: Path):
    root = build_fixture(tmp_path / "source")
    receipt_path = tmp_path / "validation.json"
    receipt = verified_receipt(root, receipt_path)
    dataset_id = f"AIOS-FX-HIST-V1-{receipt['dataset_sha256'][:20]}"
    result = freeze_dataset(source_root=root, validation_receipt=receipt_path, freeze_root=tmp_path / "frozen",
                            expected_scope_fingerprint=FINGERPRINT, expected_start_utc=stamp(START),
                            expected_end_utc=stamp(END), source_head=HEAD, command="freeze synthetic",
                            apply_read_only=False, failure_hook=lambda _: (_ for _ in ()).throw(ValueError("injected")))
    assert result["status"] == "FAIL"
    assert not (tmp_path / "frozen" / dataset_id).exists()
    assert not list((tmp_path / "frozen").glob("*.tmp"))


def test_verify_does_not_mutate_source_and_cli_output_is_bounded(tmp_path: Path, capsys):
    root = build_fixture(tmp_path / "source")
    before = source_hashes(root)
    code = main([
        "verify", "--source-root", str(root), "--expected-scope-fingerprint", FINGERPRINT,
        "--expected-start-utc", stamp(START), "--expected-end-utc", stamp(END),
        "--source-head", HEAD, "--output-format", "both",
    ])
    output = capsys.readouterr().out
    assert code == 0 and len(output) < 3000
    assert "file_inventory" not in output and MANIFEST_SCHEMA not in output
    assert source_hashes(root) == before


def test_module_has_no_network_credential_or_collector_dependency():
    source = Path("automation/forex_engine/forex_historical_dataset_verifier_freezer_v1.py").read_text(encoding="utf-8")
    forbidden = ("import requests", "import urllib", "oanda_read_only_client", "OANDA_API_TOKEN", "OANDA_ACCOUNT_ID", "Acquire-AiOs")
    assert not any(value in source for value in forbidden)
