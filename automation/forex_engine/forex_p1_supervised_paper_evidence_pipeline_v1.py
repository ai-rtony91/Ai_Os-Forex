"""Deterministic, local-only intake for supervised Profit Track P1 evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from automation.forex_engine.forex_profit_track_p1_strategy_evidence_v1 import (
    evaluate_strategy_evidence,
)

VERSION = "forex_p1_supervised_paper_evidence_pipeline_v1"
ATOMIC_WRITE_SCHEMA = "AIOS_FOREX_ATOMIC_RECOVERY_EVENT.v1"
RECOVERY_PAYLOAD_FIELDS = frozenset(
    {
        "status",
        "invalid_current_sha256",
        "invalid_current_byte_count",
        "original_read_error",
        "quarantined_sha256",
        "retained_records",
        "trades_invented",
        "pnl_invented",
    }
)
RECOVERY_RECEIPT_FIELDS = frozenset(
    {
        "schema",
        "version",
        "observed_at_utc",
    }
    | RECOVERY_PAYLOAD_FIELDS
)
RECOVERY_STATUSES = frozenset(
    {
        "RECOVERED_FROM_LAST_KNOWN_GOOD",
        "TRUNCATED_FINAL_JSONL_QUARANTINED",
    }
)
REQUIRED_FIELDS = (
    "trade_id", "evidence_type", "strategy_id", "instrument", "direction",
    "entry_timestamp_utc", "exit_timestamp_utc", "entry_price", "exit_price",
    "stop_price", "target_price", "quantity_or_units", "realized_pl", "fees",
    "risk_amount", "exit_reason", "entry_rationale", "evidence_source",
    "reviewed_by", "review_timestamp_utc",
)
OPTIONAL_IDENTITY_FIELDS = (
    "strategy_name", "mode", "paper_only", "strategy_config", "candidate_id",
)
NUMERIC_FIELDS = (
    "entry_price", "exit_price", "stop_price", "target_price",
    "quantity_or_units", "realized_pl", "fees", "risk_amount",
)
ALLOWED_EVIDENCE_TYPES = {"paper", "supervised_demo"}
PRIVATE_KEY_PARTS = (
    "account_id", "account_number", "api_key", "authorization", "credential",
    "order_id", "password", "private_id", "secret", "token",
)
RAW_KEYS = {"broker_payload", "raw_broker_payload", "raw_payload", "broker_raw"}
SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+[a-z0-9._-]+|api[_ -]?key\s*[:=]|password\s*[:=]|secret\s*[:=])"
)
SAFETY_FLAGS = {
    "broker_call_performed": False,
    "broker_write_performed": False,
    "credentials_loaded": False,
    "account_access_performed": False,
    "order_submission_allowed": False,
    "order_modification_allowed": False,
    "order_close_allowed": False,
    "live_execution_allowed": False,
    "money_movement_allowed": False,
    "scheduler_created": False,
    "daemon_created": False,
    "webhook_created": False,
}


def stable_json_bytes(payload: Any) -> bytes:
    """Serialize JSON deterministically and prove that it can be parsed."""
    rendered = json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    json.loads(rendered)
    return rendered.encode("utf-8")


def _atomic_replace_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary_path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _valid_json_bytes(payload: bytes) -> bool:
    try:
        json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return True


def _recovery_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.recovery.jsonl")


def _validated_sha256(value: Any, *, allow_unavailable: bool) -> str:
    if allow_unavailable and value == "UNAVAILABLE":
        return value
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("invalid_recovery_sha256")
    return value


def _validated_count(value: Any, *, allow_unavailable: bool) -> int | str:
    if allow_unavailable and value == "UNAVAILABLE":
        return value
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid_recovery_count")
    return value


def _sanitize_recovery_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    status = payload.get("status")
    if status not in RECOVERY_STATUSES:
        raise ValueError("invalid_recovery_status")

    sanitized: dict[str, Any] = {"status": status}

    if "invalid_current_sha256" in payload:
        sanitized["invalid_current_sha256"] = _validated_sha256(
            payload["invalid_current_sha256"],
            allow_unavailable=True,
        )
    if "invalid_current_byte_count" in payload:
        sanitized["invalid_current_byte_count"] = _validated_count(
            payload["invalid_current_byte_count"],
            allow_unavailable=True,
        )
    if "original_read_error" in payload:
        original_read_error = payload["original_read_error"]
        if original_read_error not in (None, "OSERROR"):
            raise ValueError("invalid_original_read_error")
        sanitized["original_read_error"] = original_read_error
    if "quarantined_sha256" in payload:
        sanitized["quarantined_sha256"] = _validated_sha256(
            payload["quarantined_sha256"],
            allow_unavailable=False,
        )
    if "retained_records" in payload:
        sanitized["retained_records"] = _validated_count(
            payload["retained_records"],
            allow_unavailable=False,
        )
    if "trades_invented" in payload:
        if payload["trades_invented"] != 0:
            raise ValueError("invalid_trades_invented")
        sanitized["trades_invented"] = 0
    if "pnl_invented" in payload:
        if payload["pnl_invented"] is not False:
            raise ValueError("invalid_pnl_invented")
        sanitized["pnl_invented"] = False

    return sanitized


def _append_recovery_receipt(
    path: Path,
    payload: Mapping[str, Any],
) -> None:
    sanitized_payload = _sanitize_recovery_payload(payload)
    receipt = {
        "schema": ATOMIC_WRITE_SCHEMA,
        "version": VERSION,
        "observed_at_utc": datetime.now(timezone.utc).isoformat().replace(
            "+00:00",
            "Z",
        ),
    }
    receipt.update(sanitized_payload)

    if not set(receipt).issubset(RECOVERY_RECEIPT_FIELDS):
        raise ValueError("recovery_receipt_field_violation")

    rendered = json.dumps(
        receipt,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    target = _recovery_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(rendered)
        stream.flush()
        os.fsync(stream.fileno())


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    preserve_last_known_good: bool = True,
) -> None:
    """Atomically persist validated JSON and retain one validated recovery copy."""
    rendered = stable_json_bytes(payload)
    backup = path.with_name(f"{path.name}.lkg")

    if preserve_last_known_good and path.exists():
        captured_current = path.read_bytes()
        if _valid_json_bytes(captured_current):
            _atomic_replace_bytes(backup, captured_current)

    _atomic_replace_bytes(path, rendered)

    if preserve_last_known_good and not backup.exists():
        _atomic_replace_bytes(backup, rendered)


def atomic_write_text(path: Path, payload: str) -> None:
    if not isinstance(payload, str):
        raise TypeError("text_payload_required")
    _atomic_replace_bytes(path, payload.encode("utf-8"))


def load_json_recoverable(
    path: Path,
    *,
    default: Any = None,
    expected_type: type | tuple[type, ...] | None = None,
) -> Any:
    """Load current JSON or recover only from a validated last-known-good copy."""
    if not path.exists():
        return default

    captured_current: bytes | None = None
    captured_sha256: str | None = None
    original_read_error: str | None = None

    try:
        # This is the only read of the current file. Hashing and parsing both
        # operate on this exact immutable byte capture.
        captured_current = path.read_bytes()
        captured_sha256 = hashlib.sha256(captured_current).hexdigest()
        current = json.loads(captured_current.decode("utf-8"))
        if expected_type is not None and not isinstance(current, expected_type):
            raise ValueError("unexpected_json_type")
        return current
    except OSError:
        # Never retain an exception message because it may contain paths,
        # credential markers, broker data, or other private context.
        original_read_error = "OSERROR"
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        pass

    backup = path.with_name(f"{path.name}.lkg")
    try:
        captured_backup = backup.read_bytes()
        recovered = json.loads(captured_backup.decode("utf-8"))
        if expected_type is not None and not isinstance(recovered, expected_type):
            raise ValueError("unexpected_backup_json_type")
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as backup_exc:
        raise ValueError(
            f"JSON_RECOVERY_FAILED:{path.name}:current_and_backup_invalid"
        ) from backup_exc

    atomic_write_json(
        path,
        recovered,
        preserve_last_known_good=False,
    )
    _append_recovery_receipt(
        path,
        {
            "status": "RECOVERED_FROM_LAST_KNOWN_GOOD",
            "invalid_current_sha256": captured_sha256 or "UNAVAILABLE",
            "invalid_current_byte_count": (
                len(captured_current)
                if captured_current is not None
                else "UNAVAILABLE"
            ),
            "original_read_error": original_read_error,
            "trades_invented": 0,
            "pnl_invented": False,
        },
    )
    return recovered


def append_jsonl_recoverable(
    path: Path,
    payload: Mapping[str, Any],
) -> None:
    """Append one durable JSONL record after quarantining only a torn final line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    captured_current = b""
    truncated_final: bytes | None = None

    if path.exists():
        captured_current = path.read_bytes()
        raw_lines = captured_current.splitlines(keepends=True)
        valid_lines: list[bytes] = []

        for index, raw_line in enumerate(raw_lines):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                if index != len(raw_lines) - 1:
                    raise ValueError("JSONL_MIDDLE_RECORD_CORRUPT") from error
                truncated_final = raw_line
                break
            valid_lines.append(stripped + b"\n")

        if truncated_final is not None:
            _atomic_replace_bytes(path, b"".join(valid_lines))
            _append_recovery_receipt(
                path,
                {
                    "status": "TRUNCATED_FINAL_JSONL_QUARANTINED",
                    "quarantined_sha256": hashlib.sha256(
                        truncated_final
                    ).hexdigest(),
                    "retained_records": len(valid_lines),
                    "trades_invented": 0,
                    "pnl_invented": False,
                },
            )

    separator = b""
    if truncated_final is None and captured_current and not captured_current.endswith(b"\n"):
        separator = b"\n"

    rendered = json.dumps(
        dict(payload),
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    with path.open("ab") as stream:
        stream.write(separator + rendered.encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())


def _utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _unsafe_content(value: Any) -> tuple[bool, bool]:
    private = raw = False
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            raw = raw or normalized in RAW_KEYS
            private = private or any(part in normalized for part in PRIVATE_KEY_PARTS)
            child_private, child_raw = _unsafe_content(child)
            private, raw = private or child_private, raw or child_raw
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            child_private, child_raw = _unsafe_content(child)
            private, raw = private or child_private, raw or child_raw
    elif isinstance(value, str):
        private = bool(SECRET_VALUE.search(value))
    return private, raw


def _validate(raw: Any, index: int, known_ids: set[str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(raw, Mapping):
        return None, {"record_index": index, "trade_id": None, "reasons": ["malformed_record"]}
    reasons: list[str] = []
    private, raw_payload = _unsafe_content(raw)
    if raw_payload:
        reasons.append("raw_broker_payload_rejected")
    if private:
        reasons.append("secret_or_private_identifier_rejected")
    missing = [field for field in REQUIRED_FIELDS if field not in raw or raw[field] in (None, "")]
    reasons.extend(f"missing_{field}" for field in missing)
    trade_id = str(raw.get("trade_id", "")).strip()
    if trade_id and trade_id in known_ids:
        reasons.append("duplicate_trade_id")
    evidence_type = str(raw.get("evidence_type", "")).strip().lower()
    if evidence_type and evidence_type not in ALLOWED_EVIDENCE_TYPES:
        reasons.append("unsupported_evidence_type")
    normalized = dict(raw)
    strategy_id = str(raw.get("strategy_id", "")).strip()
    strategy_name = str(raw.get("strategy_name") or strategy_id).strip()
    if strategy_id and strategy_name != strategy_id:
        reasons.append("strategy_identity_mismatch")
    normalized["strategy_name"] = strategy_name
    if "mode" in raw:
        mode = str(raw.get("mode", "")).strip().upper()
        if mode != "PAPER_ONLY":
            reasons.append("paper_only_mode_required")
        normalized["mode"] = mode
    if "paper_only" in raw and raw.get("paper_only") is not True:
        reasons.append("paper_only_true_required")
    if "strategy_config" in raw:
        if not isinstance(raw.get("strategy_config"), Mapping):
            reasons.append("invalid_strategy_config")
        else:
            normalized["strategy_config"] = dict(raw["strategy_config"])
    for field in NUMERIC_FIELDS:
        if field not in missing:
            number = _finite(raw.get(field))
            if number is None:
                reasons.append(f"non_finite_or_invalid_{field}")
            else:
                normalized[field] = number
    timestamps = {
        field: _utc_timestamp(raw.get(field))
        for field in ("entry_timestamp_utc", "exit_timestamp_utc", "review_timestamp_utc")
    }
    for field, parsed in timestamps.items():
        if field not in missing and parsed is None:
            reasons.append(f"invalid_{field}")
    if timestamps["entry_timestamp_utc"] and timestamps["exit_timestamp_utc"]:
        if timestamps["exit_timestamp_utc"] <= timestamps["entry_timestamp_utc"]:
            reasons.append("invalid_timestamp_order")
    if timestamps["exit_timestamp_utc"] and timestamps["review_timestamp_utc"]:
        if timestamps["review_timestamp_utc"] < timestamps["exit_timestamp_utc"]:
            reasons.append("review_precedes_exit")
    if reasons:
        return None, {"record_index": index, "trade_id": trade_id or None, "reasons": reasons}
    normalized["trade_id"] = trade_id
    normalized["evidence_type"] = evidence_type
    return {
        field: normalized[field]
        for field in (*REQUIRED_FIELDS, *OPTIONAL_IDENTITY_FIELDS)
        if field in normalized
    }, None


def _evaluator_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "trade_id": record["trade_id"],
            "entry": record["entry_price"],
            "exit": record["exit_price"],
            "realized_pl": record["realized_pl"],
            "timestamp": record["exit_timestamp_utc"],
            "evidence_type": record["evidence_type"],
        }
        for record in records
    ]


def _as_of(records: Sequence[Mapping[str, Any]]) -> datetime:
    timestamps = [_utc_timestamp(record["review_timestamp_utc"]) for record in records]
    return max((item for item in timestamps if item), default=datetime(1970, 1, 1, tzinfo=timezone.utc))


def _read_records(input_path: Path) -> tuple[list[Any], list[dict[str, Any]]]:
    payload = load_json_recoverable(input_path)
    if isinstance(payload, list):
        return payload, []
    if isinstance(payload, Mapping) and isinstance(payload.get("records"), list):
        return list(payload["records"]), []
    return [], [{"record_index": None, "trade_id": None, "reasons": ["malformed_record_container"]}]


def _load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": VERSION, "records": [], **SAFETY_FLAGS}
    ledger = load_json_recoverable(path, expected_type=Mapping)
    if not isinstance(ledger, Mapping) or not isinstance(ledger.get("records"), list):
        raise ValueError("invalid_existing_ledger")
    if any(ledger.get(key) is not False for key in SAFETY_FLAGS):
        raise ValueError("existing_ledger_claims_execution_authority")
    return dict(ledger)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_json(path, payload)


def run_pipeline(input_path: Path, ledger_path: Path, state_path: Path, report_path: Path) -> dict[str, Any]:
    """Run exactly one bounded evidence collection and evaluation cycle."""
    incoming, container_rejections = _read_records(input_path)
    ledger = _load_ledger(ledger_path)
    prior_records = list(ledger["records"])
    known_ids = {str(record["trade_id"]) for record in prior_records}
    before = evaluate_strategy_evidence(_evaluator_records(prior_records), as_of=_as_of(prior_records))
    accepted: list[dict[str, Any]] = []
    rejected = list(container_rejections)
    for index, raw in enumerate(incoming):
        record, rejection = _validate(raw, index, known_ids)
        if rejection:
            rejected.append(rejection)
            continue
        assert record is not None
        accepted.append(record)
        known_ids.add(record["trade_id"])
    combined = sorted(prior_records + accepted, key=lambda item: (item["exit_timestamp_utc"], item["trade_id"]))
    after = evaluate_strategy_evidence(_evaluator_records(combined), as_of=_as_of(combined))
    ledger = {"version": VERSION, "records": combined, **SAFETY_FLAGS}
    duplicate_count = sum("duplicate_trade_id" in item["reasons"] for item in rejected)
    counts = dict(sorted(Counter(item["evidence_type"] for item in combined).items()))
    state = {
        "version": VERSION,
        "pipeline_status": "COMPLETE",
        "input_records": len(incoming),
        "accepted_records": len(accepted),
        "rejected_records": len(rejected),
        "duplicate_records": duplicate_count,
        "rejections": rejected,
        "qualifying_trade_count": after["trade_count"],
        "evidence_type_counts": counts,
        "latest_trade_timestamp": after["evidence_date_range"]["end"],
        "evidence_freshness": after["evidence_freshness"],
        "p1_status_before": before["strategy_evidence_status"],
        "p1_status_after": after["strategy_evidence_status"],
        "profitability_proven": after["profitability_proven"],
        "ready_for_p2_review": after["ready_for_p2_review"],
        "next_safe_action": "Owner review of sanitized P1 evidence; no execution is authorized.",
        "p1_evaluator_result": after,
        **SAFETY_FLAGS,
    }
    _write_json(ledger_path, ledger)
    _write_json(state_path, state)
    atomic_write_text(report_path, result_to_markdown(state))
    return state


def result_to_markdown(state: Mapping[str, Any]) -> str:
    lines = [
        "# AIOS Forex P1 Supervised Paper Evidence Pipeline V1", "",
        f"- Pipeline status: {state['pipeline_status']}",
        f"- Accepted records: {state['accepted_records']}",
        f"- Rejected records: {state['rejected_records']}",
        f"- Duplicate records: {state['duplicate_records']}",
        f"- Qualifying trade count: {state['qualifying_trade_count']}",
        f"- Evidence type counts: {json.dumps(state['evidence_type_counts'], sort_keys=True)}",
        f"- P1 status before: {state['p1_status_before']}",
        f"- P1 status after: {state['p1_status_after']}",
        f"- Profitability proven: {str(state['profitability_proven']).lower()}",
        f"- Ready for P2 review: {str(state['ready_for_p2_review']).lower()}",
        f"- Live execution allowed: {str(state['live_execution_allowed']).lower()}",
        "",
        "## Safety flags",
        "",
    ]
    lines.extend(f"- {key}: {str(state[key]).lower()}" for key in SAFETY_FLAGS)
    lines.extend([
        "", state["next_safe_action"],
        "All broker, credential, account, order, money-movement, scheduler, daemon, and webhook permissions remain false.", "",
    ])
    return "\n".join(lines)
