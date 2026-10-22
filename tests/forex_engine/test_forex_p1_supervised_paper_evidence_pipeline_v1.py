from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import automation.forex_engine.forex_p1_supervised_paper_evidence_pipeline_v1 as evidence_module
from automation.forex_engine.forex_p1_supervised_paper_evidence_pipeline_v1 import (
    ATOMIC_WRITE_SCHEMA,
    RECOVERY_RECEIPT_FIELDS,
    SAFETY_FLAGS,
    VERSION,
    append_jsonl_recoverable,
    atomic_write_json,
    load_json_recoverable,
    run_pipeline,
)


def trade(trade_id: str = "paper-001", evidence_type: str = "paper") -> dict:
    return {
        "trade_id": trade_id,
        "evidence_type": evidence_type,
        "strategy_id": "strategy-c1",
        "instrument": "EUR_USD",
        "direction": "buy",
        "entry_timestamp_utc": "2026-08-01T10:00:00Z",
        "exit_timestamp_utc": "2026-08-01T11:00:00Z",
        "entry_price": 1.1,
        "exit_price": 1.101,
        "stop_price": 1.099,
        "target_price": 1.101,
        "quantity_or_units": 100,
        "realized_pl": 10,
        "fees": 1,
        "risk_amount": 10,
        "exit_reason": "target",
        "entry_rationale": "bounded paper review",
        "evidence_source": "sanitized_local_review",
        "reviewed_by": "human_owner",
        "review_timestamp_utc": "2026-08-01T12:00:00Z",
    }


@pytest.fixture
def paths(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    return tuple(tmp_path / name for name in ("input.json", "ledger.json", "state.json", "report.md"))


def run(paths: tuple[Path, Path, Path, Path], records: object) -> dict:
    input_path, ledger, state, report = paths
    input_path.write_text(json.dumps(records), encoding="utf-8")
    return run_pipeline(input_path, ledger, state, report)


def test_empty_input_stays_no_evidence_and_writes_outputs(paths):
    result = run(paths, [])
    assert result["p1_status_after"] == "NO_EVIDENCE"
    assert result["accepted_records"] == result["rejected_records"] == 0
    assert all(path.exists() for path in paths[1:])


@pytest.mark.parametrize("evidence_type", ["paper", "supervised_demo"])
def test_accepts_qualifying_sanitized_types(paths, evidence_type):
    result = run(paths, [trade(evidence_type=evidence_type)])
    assert result["accepted_records"] == 1
    assert result["qualifying_trade_count"] == 1
    assert result["evidence_type_counts"] == {evidence_type: 1}


def test_preserves_supertrend_identity_and_paper_only_metadata(paths):
    record = {
        **trade(),
        "strategy_id": "supertrend_pullback_v1",
        "strategy_name": "supertrend_pullback_v1",
        "mode": "PAPER_ONLY",
        "paper_only": True,
        "strategy_config": {"atr_period": 3, "multiplier": 2.0},
    }
    result = run(paths, [record])
    ledger = json.loads(paths[1].read_text(encoding="utf-8"))
    accepted = ledger["records"][0]
    assert result["accepted_records"] == 1
    assert accepted["strategy_name"] == "supertrend_pullback_v1"
    assert accepted["mode"] == "PAPER_ONLY"
    assert accepted["paper_only"] is True
    assert accepted["strategy_config"] == {"atr_period": 3, "multiplier": 2.0}


@pytest.mark.parametrize("evidence_type", ["fixture", "synthetic", "live", "broker_raw"])
def test_rejects_nonqualifying_evidence_types(paths, evidence_type):
    result = run(paths, [trade(evidence_type=evidence_type)])
    assert result["accepted_records"] == 0
    assert "unsupported_evidence_type" in result["rejections"][0]["reasons"]


def test_duplicate_id_is_rejected_and_prior_evidence_is_unchanged(paths):
    first = run(paths, [trade()])
    ledger_before = paths[1].read_text(encoding="utf-8")
    second = run(paths, [trade()])
    assert first["accepted_records"] == 1
    assert second["duplicate_records"] == 1
    assert paths[1].read_text(encoding="utf-8") == ledger_before


def test_duplicate_within_one_input_is_rejected(paths):
    result = run(paths, [trade(), trade()])
    assert result["accepted_records"] == 1
    assert result["duplicate_records"] == 1


def test_missing_field_is_not_inferred(paths):
    record = trade()
    del record["strategy_id"]
    result = run(paths, [record])
    assert "missing_strategy_id" in result["rejections"][0]["reasons"]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"exit_timestamp_utc": "not-a-time"}, "invalid_exit_timestamp_utc"),
        ({"exit_timestamp_utc": "2026-08-01T09:00:00Z"}, "invalid_timestamp_order"),
        ({"entry_price": float("nan")}, "non_finite_or_invalid_entry_price"),
        ({"api_key": "not-recorded"}, "secret_or_private_identifier_rejected"),
        ({"account_id": "private"}, "secret_or_private_identifier_rejected"),
        ({"order_id": "private"}, "secret_or_private_identifier_rejected"),
        ({"raw_broker_payload": {}}, "raw_broker_payload_rejected"),
        ({"entry_rationale": "password=do-not-store"}, "secret_or_private_identifier_rejected"),
        ({"strategy_name": "different"}, "strategy_identity_mismatch"),
        ({"mode": "LIVE"}, "paper_only_mode_required"),
        ({"paper_only": False}, "paper_only_true_required"),
    ],
)
def test_fail_closed_rejections(paths, mutation, reason):
    record = trade()
    record.update(mutation)
    result = run(paths, [record])
    assert reason in result["rejections"][0]["reasons"]


def test_append_order_is_deterministic(paths):
    later = trade("later")
    earlier = trade("earlier")
    earlier.update({
        "entry_timestamp_utc": "2026-07-31T10:00:00Z",
        "exit_timestamp_utc": "2026-07-31T11:00:00Z",
        "review_timestamp_utc": "2026-07-31T12:00:00Z",
    })
    run(paths, [later, earlier])
    ledger = json.loads(paths[1].read_text(encoding="utf-8"))
    assert [item["trade_id"] for item in ledger["records"]] == ["earlier", "later"]


def test_evaluator_is_triggered(monkeypatch, paths):
    import automation.forex_engine.forex_p1_supervised_paper_evidence_pipeline_v1 as module

    original = module.evaluate_strategy_evidence
    calls = []

    def tracked(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "evaluate_strategy_evidence", tracked)
    run(paths, [trade()])
    assert len(calls) == 2
    assert len(calls[-1]) == 1


def test_all_outputs_deny_execution_authority(paths):
    result = run(paths, [trade()])
    ledger = json.loads(paths[1].read_text(encoding="utf-8"))
    state = json.loads(paths[2].read_text(encoding="utf-8"))
    for key in SAFETY_FLAGS:
        assert result[key] is False
        assert ledger[key] is False
        assert state[key] is False
    report = paths[3].read_text(encoding="utf-8")
    assert "Live execution allowed: false" in report


def test_invalid_existing_authority_claim_fails_closed(paths):
    paths[1].write_text(json.dumps({"records": [], "live_execution_allowed": True}), encoding="utf-8")
    paths[0].write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="execution_authority"):
        run_pipeline(*paths)


def test_valid_current_bytes_load_without_consulting_lkg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "state.json"
    backup = target.with_name(f"{target.name}.lkg")
    payload = {"status": "VALID", "records": []}
    target.write_bytes(json.dumps(payload).encode("utf-8"))
    backup.write_bytes(b"invalid-backup-must-not-be-read")

    original_read_bytes = Path.read_bytes
    observed_reads: list[Path] = []

    def tracked_read_bytes(candidate: Path) -> bytes:
        observed_reads.append(candidate)
        if candidate == backup:
            raise AssertionError("valid current JSON consulted the LKG copy")
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)

    assert load_json_recoverable(
        target,
        expected_type=dict,
    ) == payload
    assert observed_reads == [target]


def test_invalid_current_recovers_and_receipt_hashes_captured_bytes(
    tmp_path: Path,
):
    target = tmp_path / "state.json"
    backup = target.with_name(f"{target.name}.lkg")
    invalid_current = b'{"records":[}\xff'
    recovered_payload = {
        "status": "LAST_KNOWN_GOOD",
        "records": [{"trade_id": "paper-001"}],
    }
    target.write_bytes(invalid_current)
    backup.write_bytes(json.dumps(recovered_payload).encode("utf-8"))

    result = load_json_recoverable(
        target,
        expected_type=dict,
    )

    assert result == recovered_payload
    assert json.loads(target.read_text(encoding="utf-8")) == recovered_payload

    receipt_path = target.with_name(f"{target.name}.recovery.jsonl")
    receipt_lines = receipt_path.read_text(encoding="utf-8").splitlines()
    assert len(receipt_lines) == 1
    receipt = json.loads(receipt_lines[0])
    assert receipt["status"] == "RECOVERED_FROM_LAST_KNOWN_GOOD"
    assert receipt["invalid_current_sha256"] == hashlib.sha256(
        invalid_current
    ).hexdigest()
    assert receipt["invalid_current_byte_count"] == len(invalid_current)
    assert receipt["original_read_error"] is None
    assert receipt["trades_invented"] == 0
    assert receipt["pnl_invented"] is False


def test_invalid_current_path_is_read_exactly_once_before_lkg_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "ledger.json"
    backup = target.with_name(f"{target.name}.lkg")
    target.write_bytes(b'{"records": [}')
    backup.write_bytes(b'{"records": []}')

    original_read_bytes = Path.read_bytes
    current_read_count = 0

    def counted_read_bytes(candidate: Path) -> bytes:
        nonlocal current_read_count
        if candidate == target:
            current_read_count += 1
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)

    assert load_json_recoverable(
        target,
        expected_type=dict,
    ) == {"records": []}
    assert current_read_count == 1


def test_original_read_oserror_uses_lkg_without_second_current_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "state.json"
    backup = target.with_name(f"{target.name}.lkg")
    target.write_bytes(b'{"status": "unreadable"}')
    recovered_payload = {"status": "RECOVERED", "records": []}
    backup.write_bytes(json.dumps(recovered_payload).encode("utf-8"))

    original_read_bytes = Path.read_bytes
    current_read_count = 0

    def failing_current_read(candidate: Path) -> bytes:
        nonlocal current_read_count
        if candidate == target:
            current_read_count += 1
            raise OSError(
                "Authorization: Bearer do-not-record-this-exception"
            )
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", failing_current_read)

    assert load_json_recoverable(
        target,
        expected_type=dict,
    ) == recovered_payload
    assert current_read_count == 1

    receipt_path = target.with_name(f"{target.name}.recovery.jsonl")
    receipt = json.loads(
        receipt_path.read_text(encoding="utf-8").splitlines()[0]
    )
    assert receipt["invalid_current_sha256"] == "UNAVAILABLE"
    assert receipt["invalid_current_byte_count"] == "UNAVAILABLE"
    assert receipt["original_read_error"] == "OSERROR"
    assert "do-not-record-this-exception" not in json.dumps(receipt)


def test_corrupt_current_and_corrupt_lkg_fail_closed(tmp_path: Path):
    target = tmp_path / "state.json"
    backup = target.with_name(f"{target.name}.lkg")
    invalid_current = b'{"status": [}'
    invalid_backup = b'{"status":'
    target.write_bytes(invalid_current)
    backup.write_bytes(invalid_backup)

    with pytest.raises(
        ValueError,
        match="JSON_RECOVERY_FAILED:state.json:current_and_backup_invalid",
    ):
        load_json_recoverable(target, expected_type=dict)

    assert target.read_bytes() == invalid_current
    assert backup.read_bytes() == invalid_backup
    assert not target.with_name(f"{target.name}.recovery.jsonl").exists()


def test_truncated_final_jsonl_is_quarantined_and_prior_records_survive(
    tmp_path: Path,
):
    target = tmp_path / "cycle_events.jsonl"
    valid_record = b'{"event_id":"event-001","status":"VALID"}\n'
    truncated_record = b'{"event_id":"event-torn","status":'
    target.write_bytes(valid_record + truncated_record)

    append_jsonl_recoverable(
        target,
        {
            "event_id": "event-002",
            "status": "VALID",
        },
    )

    recovered_records = [
        json.loads(line)
        for line in target.read_text(encoding="utf-8").splitlines()
    ]
    assert recovered_records == [
        {
            "event_id": "event-001",
            "status": "VALID",
        },
        {
            "event_id": "event-002",
            "status": "VALID",
        },
    ]

    receipt_path = target.with_name(f"{target.name}.recovery.jsonl")
    receipt_lines = receipt_path.read_text(encoding="utf-8").splitlines()
    assert len(receipt_lines) == 1
    receipt = json.loads(receipt_lines[0])
    assert receipt["status"] == "TRUNCATED_FINAL_JSONL_QUARANTINED"
    assert receipt["quarantined_sha256"] == hashlib.sha256(
        truncated_record
    ).hexdigest()
    assert receipt["retained_records"] == 1
    assert receipt["trades_invented"] == 0
    assert receipt["pnl_invented"] is False


def test_valid_newline_less_final_jsonl_record_gets_separator(tmp_path: Path):
    target = tmp_path / "state.jsonl"
    target.write_bytes(b'{"record": "old"}')

    evidence_module.append_jsonl_recoverable(target, {"record": "new"})

    records = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert records == [{"record": "old"}, {"record": "new"}]
    assert target.read_bytes().endswith(b"\n")


def test_temporary_file_write_failure_preserves_previous_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "state.json"
    previous_bytes = b'{"status":"PREVIOUS_VALID"}\n'
    target.write_bytes(previous_bytes)
    original_open = Path.open

    class FailingWriteStream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.stream.close()
            return False

        def write(self, payload):
            self.stream.write(payload[:1])
            raise OSError("simulated temporary-file write failure")

        def flush(self):
            self.stream.flush()

        def fileno(self):
            return self.stream.fileno()

    def controlled_open(candidate: Path, mode="r", *args, **kwargs):
        stream = original_open(candidate, mode, *args, **kwargs)
        if (
            mode == "xb"
            and candidate.parent == target.parent
            and candidate.name.startswith(f".{target.name}.")
        ):
            return FailingWriteStream(stream)
        return stream

    monkeypatch.setattr(Path, "open", controlled_open)

    with pytest.raises(OSError, match="temporary-file write failure"):
        atomic_write_json(
            target,
            {"status": "NEW"},
            preserve_last_known_good=False,
        )

    assert target.read_bytes() == previous_bytes
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []
    assert not target.with_name(f"{target.name}.recovery.jsonl").exists()


def test_fsync_failure_preserves_previous_destination_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "state.json"
    previous_bytes = b'{"status":"PREVIOUS_VALID"}\n'
    target.write_bytes(previous_bytes)

    def fail_fsync(_file_descriptor):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(evidence_module.os, "fsync", fail_fsync)

    with pytest.raises(OSError, match="fsync failure"):
        atomic_write_json(
            target,
            {"status": "NEW"},
            preserve_last_known_good=False,
        )

    assert target.read_bytes() == previous_bytes
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []
    assert not target.with_name(f"{target.name}.recovery.jsonl").exists()


def test_replace_failure_preserves_previous_destination_without_success_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "state.json"
    previous_bytes = b'{"status":"PREVIOUS_VALID"}\n'
    target.write_bytes(previous_bytes)

    def fail_replace(_source, destination):
        assert Path(destination) == target
        raise OSError("simulated replace failure")

    monkeypatch.setattr(evidence_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failure"):
        atomic_write_json(
            target,
            {"status": "NEW"},
            preserve_last_known_good=False,
        )

    assert target.read_bytes() == previous_bytes
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []
    assert not target.with_name(f"{target.name}.recovery.jsonl").exists()


def test_recovery_receipt_uses_only_explicit_sanitized_allowlist(
    tmp_path: Path,
):
    target = tmp_path / "state.json"
    evidence_module._append_recovery_receipt(
        target,
        {
            "status": "RECOVERED_FROM_LAST_KNOWN_GOOD",
            "invalid_current_sha256": "a" * 64,
            "invalid_current_byte_count": 17,
            "original_read_error": None,
            "trades_invented": 0,
            "pnl_invented": False,
            "unexpected_field": "must-not-be-written",
            "broker_response_body": "must-not-be-written",
        },
    )

    receipt_path = target.with_name(f"{target.name}.recovery.jsonl")
    receipt = json.loads(
        receipt_path.read_text(encoding="utf-8").splitlines()[0]
    )
    assert set(receipt).issubset(RECOVERY_RECEIPT_FIELDS)
    assert set(receipt) == {
        "schema",
        "version",
        "observed_at_utc",
        "status",
        "invalid_current_sha256",
        "invalid_current_byte_count",
        "original_read_error",
        "trades_invented",
        "pnl_invented",
    }
    assert "unexpected_field" not in receipt
    assert "broker_response_body" not in receipt


def test_payload_cannot_override_reserved_receipt_identity_fields(
    tmp_path: Path,
):
    target = tmp_path / "state.json"
    evidence_module._append_recovery_receipt(
        target,
        {
            "schema": "ATTACKER_SCHEMA",
            "version": "ATTACKER_VERSION",
            "observed_at_utc": "1900-01-01T00:00:00Z",
            "status": "RECOVERED_FROM_LAST_KNOWN_GOOD",
            "invalid_current_sha256": "b" * 64,
            "invalid_current_byte_count": 1,
            "original_read_error": None,
            "trades_invented": 0,
            "pnl_invented": False,
        },
    )

    receipt_path = target.with_name(f"{target.name}.recovery.jsonl")
    receipt = json.loads(
        receipt_path.read_text(encoding="utf-8").splitlines()[0]
    )
    assert receipt["schema"] == ATOMIC_WRITE_SCHEMA
    assert receipt["version"] == VERSION
    assert receipt["observed_at_utc"] != "1900-01-01T00:00:00Z"
    assert receipt["observed_at_utc"].endswith("Z")


def test_recovery_receipts_never_persist_sensitive_source_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    forbidden_values = (
        "OANDA_API_TOKEN",
        "practice-token-value",
        "OANDA_ACCOUNT_ID",
        "101-001-12345678-001",
        "Authorization",
        "Bearer broker-secret",
        "broker_response_body",
        "complete-private-broker-response",
        "exception-private-context",
    )

    corrupt_target = tmp_path / "corrupt.json"
    corrupt_backup = corrupt_target.with_name(f"{corrupt_target.name}.lkg")
    corrupt_bytes = (
        b'{"OANDA_API_TOKEN":"practice-token-value",'
        b'"OANDA_ACCOUNT_ID":"101-001-12345678-001",'
        b'"Authorization":"Bearer broker-secret",'
        b'"broker_response_body":"complete-private-broker-response"'
    )
    corrupt_target.write_bytes(corrupt_bytes)
    corrupt_backup.write_bytes(b'{"status":"RECOVERED"}')

    assert load_json_recoverable(
        corrupt_target,
        expected_type=dict,
    ) == {"status": "RECOVERED"}

    error_target = tmp_path / "read-error.json"
    error_backup = error_target.with_name(f"{error_target.name}.lkg")
    error_target.write_bytes(b'{"status":"unreadable"}')
    error_backup.write_bytes(b'{"status":"RECOVERED"}')
    original_read_bytes = Path.read_bytes

    def fail_sensitive_read(candidate: Path) -> bytes:
        if candidate == error_target:
            raise OSError(
                "exception-private-context "
                "Authorization: Bearer broker-secret"
            )
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", fail_sensitive_read)

    assert load_json_recoverable(
        error_target,
        expected_type=dict,
    ) == {"status": "RECOVERED"}

    injected_target = tmp_path / "injected.json"
    evidence_module._append_recovery_receipt(
        injected_target,
        {
            "status": "RECOVERED_FROM_LAST_KNOWN_GOOD",
            "invalid_current_sha256": "c" * 64,
            "invalid_current_byte_count": 1,
            "original_read_error": None,
            "trades_invented": 0,
            "pnl_invented": False,
            "OANDA_API_TOKEN": "practice-token-value",
            "OANDA_ACCOUNT_ID": "101-001-12345678-001",
            "Authorization": "Bearer broker-secret",
            "broker_response_body": "complete-private-broker-response",
        },
    )

    receipt_corpus = "\n".join(
        (
            corrupt_target.with_name(
                f"{corrupt_target.name}.recovery.jsonl"
            ).read_text(encoding="utf-8"),
            error_target.with_name(
                f"{error_target.name}.recovery.jsonl"
            ).read_text(encoding="utf-8"),
            injected_target.with_name(
                f"{injected_target.name}.recovery.jsonl"
            ).read_text(encoding="utf-8"),
        )
    )
    receipt_corpus_lower = receipt_corpus.lower()
    for forbidden_value in forbidden_values:
        assert forbidden_value.lower() not in receipt_corpus_lower
