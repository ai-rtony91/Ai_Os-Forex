"""Small, bounded Requester Pays adapter for the PKT-044 Dukascopy source.

It plans and inventories only daily BID/ASK minute-candle objects and the
same-provider daily tick fallback where a full minute-candle pair is absent.
It does not score a strategy, create cloud resources, use account APIs, or
issue S3 writes.  Bulk downloads remain caller-gated by a verified source
contract and the cumulative owner cost limit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from .dukascopy_bi5 import (
    DukascopyBi5Error,
    canonical_pair,
    daily_candle_key,
    daily_tick_key,
    parse_daily_candle_key,
    parse_daily_tick_key,
    source_symbol,
)


AWS_EXECUTABLE = Path(r"C:\Users\mylab\AppData\Local\Programs\Amazon\AWSCLIV2\aws.exe")
AWS_PROFILE = "AIOS-FOREX"
AWS_REGION = "eu-west-1"
AWS_BUCKET = "cfg-public-proper-wallaby"
REQUEST_PAYER = "requester"
AWS_GET_PROCESS_TIMEOUT_SECONDS = 180
AWS_GET_CONNECT_TIMEOUT_SECONDS = 30
AWS_GET_READ_TIMEOUT_SECONDS = 120
TEMPORARY_GET_ERROR_PREFIXES = (
    "AWS_GET-OBJECT_TIMEOUT",
    "AWS_GET-OBJECT_READ_TIMEOUT",
    "AWS_GET_OBJECT_TIMEOUT",
    "AWS_GET_OBJECT_READ_TIMEOUT",
    "AWS_GET_OBJECT_CONNECTION_RESET",
    "AWS_GET_OBJECT_SERVICE_UNAVAILABLE",
    "AWS_GET_OBJECT_THROTTLED",
    "AWS_GET_OBJECT_CONNECTION_FAILURE",
)
UTC = timezone.utc
_TICK_KEY = re.compile(r"^(?P<symbol>[A-Z]{6})/20\d{2}/\d{2}/\d{2}_ticks\.bi5$")
_MONTHLY_AGGREGATE_KEY = re.compile(
    r"^(?P<symbol>[A-Z]{6})/20\d{2}/\d{2}/(?:BID|ASK)_candles_(?:day|hour)_1\.bi5$"
)


class DukascopyAcquisitionError(RuntimeError):
    """An acquisition or inventory contract was not met."""


@dataclass(frozen=True)
class SourceObject:
    pair: str
    trading_day: str
    side: str
    key: str
    size: int
    etag: str | None
    last_modified: str | None
    data_type: str
    storage_class: str | None = None


@dataclass(frozen=True)
class Inventory:
    start: str
    end: str
    pair_count: int
    calendar_date_count: int
    bid_object_count: int
    ask_object_count: int
    total_object_count: int
    total_listed_bytes: int
    missing_expected_object_count: int
    unresolved_source_day_count: int
    available_tick_object_count: int
    available_tick_bytes: int
    fallback_tick_object_count: int
    fallback_tick_bytes: int
    non_target_object_count: int
    unexpected_object_count: int
    objects: tuple[SourceObject, ...]
    missing_expected_keys: tuple[str, ...]
    non_target_keys: tuple[str, ...]
    unexpected_keys: tuple[str, ...]
    per_pair: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class AcquisitionChunk:
    """One bounded pair/month transfer whose allowed keys were inventoried."""

    pair: str
    prefix: str
    objects: tuple[SourceObject, ...]
    chunk_id: str


@dataclass(frozen=True)
class CostBasis:
    list_per_1000_usd: float
    get_per_1000_usd: float
    head_per_1000_usd: float
    transfer_per_gb_usd: float
    price_source: str
    retrieved_at_utc: str
    free_allowance_assumption: str
    retrieval_per_gb_usd: float = 0.0


@dataclass(frozen=True)
class CostGate:
    total_objects: int
    total_list_requests_planned: int
    total_get_requests_planned: int
    total_head_requests_planned: int
    exact_listed_object_bytes: int
    conservative_download_bytes: int
    prior_cost_usd: float
    list_cost_usd: float
    get_cost_usd: float
    head_cost_usd: float
    transfer_cost_usd: float
    other_cost_usd: float
    safety_margin_usd: float
    conservative_remaining_cost_usd: float
    conservative_total_job_cost_usd: float
    owner_limit_usd: float
    source_semantics_requirement_id: str
    source_semantic_fit: str
    source_acquisition_status: str
    cost_gate: str


@dataclass(frozen=True)
class SourceSemanticsRequirement:
    """Frozen data requirements that must pass before a cost or bulk-data gate."""

    strategy_specification_id: str
    required_pair_count: int
    required_price_sides: tuple[str, ...]
    midpoint_semantics: str
    timestamp_granularity: str
    candle_construction: str
    activity_semantics: str
    preregistration_status: str


@dataclass(frozen=True)
class SourceSemanticsCapability:
    """Evidence-backed provider capability map; it contains no market outcomes."""

    source_id: str
    evidence_id: str
    mapped_pair_count: int
    available_price_sides: tuple[str, ...]
    timestamp_granularities: tuple[str, ...]
    candle_constructions: tuple[str, ...]
    native_mid_coverage_complete: bool
    paired_tick_coverage_complete: bool
    paired_tick_same_record: bool
    execution_coverage_complete: bool
    activity_semantics: str
    native_mid_object_count: int
    paired_tick_object_count: int


@dataclass(frozen=True)
class SourceSemanticsGate:
    """Fail-closed pre-acquisition result for one frozen or proposed strategy."""

    strategy_specification_id: str
    source_id: str
    evidence_id: str
    semantic_fit: str
    acquisition_status: str
    requires_new_fingerprint: bool
    blockers: tuple[str, ...]
    required_pair_count: int
    mapped_pair_count: int
    midpoint_semantics: str
    native_mid_object_count: int
    paired_tick_object_count: int


@dataclass(frozen=True)
class PairedTickPreacquisitionGate:
    """Local PKT-045 semantics result; it deliberately proves no coverage."""

    strategy_specification_id: str
    source_id: str
    local_tick_proof_id: str
    semantic_contract_status: str
    full_coverage_status: str
    acquisition_status: str
    blockers: tuple[str, ...]
    required_pair_count: int
    mapped_pair_count: int


@dataclass(frozen=True)
class PairedTickInventoryPlan:
    """Expected tick-object keys only, generated without an AWS request."""

    start: str
    end: str
    pair_count: int
    calendar_date_count: int
    total_expected_tick_object_count: int
    objects: tuple[str, ...]


@dataclass(frozen=True)
class PairedTickInventory:
    """Exact listed PKT-045 tick objects, distinct from the old candle plan.

    A missing daily tick key is evidence of source availability, not permission
    to invent a quote.  It is retained for the later executable-path
    certification instead of being hidden during cost planning.
    """

    start: str
    end: str
    pair_count: int
    calendar_date_count: int
    expected_tick_object_count: int
    available_tick_object_count: int
    total_listed_bytes: int
    missing_expected_object_count: int
    non_target_object_count: int
    unexpected_object_count: int
    objects: tuple[SourceObject, ...]
    missing_expected_keys: tuple[str, ...]
    non_target_keys: tuple[str, ...]
    unexpected_keys: tuple[str, ...]
    per_pair: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class PairedTickCostGate:
    """Cumulative PKT-045 cost gate for the exact paired-tick inventory."""

    total_objects: int
    total_list_requests_actual: int
    total_get_requests_planned: int
    total_head_requests_planned: int
    exact_listed_object_bytes: int
    conservative_download_bytes: int
    prior_spend_estimate_usd: float
    inventory_cost_usd: float
    remaining_request_cost_usd: float
    remaining_retrieval_cost_usd: float
    remaining_transfer_cost_usd: float
    other_applicable_cost_usd: float
    retry_and_uncertainty_reserve_usd: float
    conservative_total_project_cost_usd: float
    owner_limit_usd: float
    source_semantics_status: str
    inventory_status: str
    cost_gate: str


@dataclass(frozen=True)
class PairedTickAcquisitionGate:
    """A post-inventory authorization object, distinct from local semantics proof."""

    packet_id: str
    required_pair_count: int
    mapped_pair_count: int
    available_tick_object_count: int
    inventory_missing_calendar_keys: int
    inventory_unexpected_object_count: int
    source_semantics_status: str
    cost_gate: str
    conservative_total_project_cost_usd: float
    owner_limit_usd: float
    acquisition_status: str


_MID_SEMANTICS_NATIVE = "NATIVE_PROVIDER_MID_OHLC"
_MID_SEMANTICS_PAIRED_TICKS = "PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION"
_MID_SEMANTICS_NONE = "NOT_REQUIRED"
_VALID_MID_SEMANTICS = {
    _MID_SEMANTICS_NATIVE,
    _MID_SEMANTICS_PAIRED_TICKS,
    _MID_SEMANTICS_NONE,
}
_ACQUISITION_READY_PREREGISTRATIONS = {"FROZEN", "APPROVED"}


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise DukascopyAcquisitionError("ACQUISITION_TIMEZONE_MISSING")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calendar_days(start: datetime, end: datetime) -> tuple[date, ...]:
    if start.tzinfo is None or end.tzinfo is None:
        raise DukascopyAcquisitionError("ACQUISITION_TIMEZONE_MISSING")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if start >= end or start.time() != datetime.min.time() or end.time() != datetime.min.time():
        raise DukascopyAcquisitionError("ACQUISITION_INTERVAL_MUST_BE_UTC_DAY_ALIGNED")
    days: list[date] = []
    current = start.date()
    while current < end.date():
        days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _month_prefix(pair: str, trading_day: date) -> str:
    return f"{source_symbol(pair)}/{trading_day.year:04d}/{trading_day.month - 1:02d}/"


def month_prefixes(pairs: Sequence[str], start: datetime, end: datetime) -> tuple[tuple[str, str], ...]:
    """Return deterministic pair/month prefixes needed for a daily inventory."""
    dates = _calendar_days(start, end)
    months = sorted({(item.year, item.month) for item in dates})
    return tuple(
        (pair, f"{source_symbol(pair)}/{year:04d}/{month - 1:02d}/")
        for pair in sorted({str(pair).upper() for pair in pairs})
        for year, month in months
    )


class AwsRequesterPaysClient:
    """Narrow local wrapper around the approved read-only AWS CLI operations."""

    def __init__(
        self,
        *,
        executable: Path = AWS_EXECUTABLE,
        profile: str = AWS_PROFILE,
        region: str = AWS_REGION,
        bucket: str = AWS_BUCKET,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        if Path(executable) != AWS_EXECUTABLE:
            raise DukascopyAcquisitionError("AWS_EXECUTABLE_NOT_APPROVED")
        if profile != AWS_PROFILE or region != AWS_REGION or bucket != AWS_BUCKET:
            raise DukascopyAcquisitionError("AWS_SOURCE_SCOPE_NOT_APPROVED")
        self.executable = Path(executable)
        self.profile = profile
        self.region = region
        self.bucket = bucket
        self._runner = runner
        self._request_counts = {"list": 0, "get": 0, "sync": 0}

    @property
    def request_counts(self) -> dict[str, int]:
        return dict(self._request_counts)

    def _command(self, operation: str, *operation_args: str) -> list[str]:
        if operation not in {"list-objects-v2", "get-object"}:
            raise DukascopyAcquisitionError("AWS_OPERATION_NOT_APPROVED")
        command = [
            str(self.executable), "s3api", operation, "--bucket", self.bucket,
            "--request-payer", REQUEST_PAYER, "--profile", self.profile,
            "--region", self.region, "--no-cli-pager", *operation_args,
        ]
        if operation == "get-object":
            command[command.index("--no-cli-pager") + 1:command.index("--no-cli-pager") + 1] = [
                "--cli-connect-timeout", str(AWS_GET_CONNECT_TIMEOUT_SECONDS),
                "--cli-read-timeout", str(AWS_GET_READ_TIMEOUT_SECONDS),
            ]
        return command

    def _run_json(self, operation: str, *operation_args: str) -> dict[str, Any]:
        if not self.executable.is_file():
            raise DukascopyAcquisitionError("AWS_EXECUTABLE_MISSING")
        command = self._command(operation, *operation_args, "--output", "json")
        self._request_counts["list" if operation == "list-objects-v2" else "get"] += 1
        try:
            run_kwargs = {"text": True, "capture_output": True, "check": False}
            if operation == "get-object":
                run_kwargs["timeout"] = AWS_GET_PROCESS_TIMEOUT_SECONDS
                child_env = os.environ.copy()
                child_env["AWS_MAX_ATTEMPTS"] = "1"
                run_kwargs["env"] = child_env
            else:
                run_kwargs["timeout"] = 30
            completed = self._runner(command, **run_kwargs)
        except subprocess.TimeoutExpired as exc:
            raise DukascopyAcquisitionError(f"AWS_{operation.upper()}_TIMEOUT") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "AWS_COMMAND_FAILED").strip().splitlines()[-1]
            if operation == "get-object":
                if "Could not connect to the endpoint URL" in detail:
                    raise DukascopyAcquisitionError(f"AWS_GET_OBJECT_CONNECTION_FAILURE:{detail[:240]}")
                if "Read timeout on endpoint URL" in detail or "Connection timed out" in detail:
                    raise DukascopyAcquisitionError(f"AWS_GET_OBJECT_READ_TIMEOUT:{detail[:240]}")
            raise DukascopyAcquisitionError(f"AWS_{operation.upper()}_FAILED:{detail[:240]}")
        try:
            return json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise DukascopyAcquisitionError("AWS_JSON_RESPONSE_INVALID") from exc

    def list_prefix(self, prefix: str, *, max_pages: int | None = None) -> tuple[dict[str, Any], ...]:
        """List one constrained prefix with an optional explicit page ceiling."""
        if not prefix or prefix.startswith("/") or ".." in prefix:
            raise DukascopyAcquisitionError("AWS_PREFIX_INVALID")
        if max_pages is not None and (isinstance(max_pages, bool) or max_pages <= 0):
            raise DukascopyAcquisitionError("AWS_LIST_PAGE_LIMIT_INVALID")
        token: str | None = None
        output: list[dict[str, Any]] = []
        pages = 0
        while True:
            args = ["--prefix", prefix]
            if token is not None:
                args.extend(["--continuation-token", token])
            payload = self._run_json("list-objects-v2", *args)
            pages += 1
            output.extend(item for item in payload.get("Contents", []) if isinstance(item, dict))
            if not payload.get("IsTruncated"):
                break
            if max_pages is not None and pages >= max_pages:
                raise DukascopyAcquisitionError("AWS_LIST_PAGE_LIMIT_EXCEEDED")
            token = payload.get("NextContinuationToken")
            if not isinstance(token, str) or not token:
                raise DukascopyAcquisitionError("AWS_LIST_PAGINATION_INVALID")
        return tuple(output)

    def get_object(self, key: str, destination: Path, *, output_root: Path, attempt_tag: str | None = None) -> dict[str, Any]:
        """Download exactly one inventoried source object to the approved root."""
        try:
            destination.resolve().relative_to(output_root.resolve())
        except ValueError as exc:
            raise DukascopyAcquisitionError("AWS_DESTINATION_OUTSIDE_APPROVED_ROOT") from exc
        try:
            parse_daily_candle_key(key)
        except DukascopyBi5Error:
            try:
                parse_daily_tick_key(key)
            except DukascopyBi5Error as exc:
                raise DukascopyAcquisitionError("AWS_SOURCE_KEY_NOT_APPROVED") from exc
        if destination.exists():
            raise DukascopyAcquisitionError("AWS_DESTINATION_ALREADY_EXISTS")
        suffix = ".part" if attempt_tag is None else f".{attempt_tag}.part"
        temporary = destination.with_name(f"{destination.name}{suffix}")
        if temporary.exists():
            raise DukascopyAcquisitionError("AWS_DESTINATION_PARTIAL_EXISTS")
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self._run_json("get-object", "--key", key, str(temporary))
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise DukascopyAcquisitionError("AWS_GET_OBJECT_OUTPUT_MISSING_OR_EMPTY")
        temporary.replace(destination)
        return payload

    def sync_exact_objects(
        self,
        *,
        prefix: str,
        destination: Path,
        include_patterns: Sequence[str],
        output_root: Path,
    ) -> None:
        """Run one bounded S3-to-local sync for already-inventoried object names.

        AWS CLI performs source ``GetObject`` calls internally.  The command is
        constrained to exactly one pair/month prefix and an explicit include
        list.  It never uses ``--delete`` or a destination outside PKT-044
        staging.  Later local checks prove every downloaded key, size, and hash.
        """
        if not prefix or prefix.startswith("/") or ".." in prefix:
            raise DukascopyAcquisitionError("AWS_PREFIX_INVALID")
        try:
            destination.resolve().relative_to(output_root.resolve())
        except ValueError as exc:
            raise DukascopyAcquisitionError("AWS_DESTINATION_OUTSIDE_APPROVED_ROOT") from exc
        patterns = tuple(sorted({str(pattern) for pattern in include_patterns}))
        if not patterns or any(
            not pattern or pattern.startswith("/") or ".." in pattern or "\\" in pattern for pattern in patterns
        ):
            raise DukascopyAcquisitionError("AWS_SYNC_INCLUDE_PATTERN_INVALID")
        if not self.executable.is_file():
            raise DukascopyAcquisitionError("AWS_EXECUTABLE_MISSING")
        destination.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.executable), "s3", "sync", f"s3://{self.bucket}/{prefix}", str(destination),
            "--exclude", "*",
        ]
        for pattern in patterns:
            command.extend(("--include", pattern))
        command.extend((
            "--request-payer", REQUEST_PAYER, "--profile", self.profile,
            "--region", self.region, "--no-cli-pager", "--no-progress", "--only-show-errors",
        ))
        self._request_counts["sync"] += 1
        try:
            completed = self._runner(command, text=True, capture_output=True, check=False, timeout=1_800)
        except subprocess.TimeoutExpired as exc:
            raise DukascopyAcquisitionError("AWS_SYNC_TIMEOUT") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "AWS_SYNC_FAILED").strip().splitlines()[-1]
            raise DukascopyAcquisitionError(f"AWS_SYNC_FAILED:{detail[:240]}")


def _source_object(item: dict[str, Any], *, pair: str) -> SourceObject | None:
    key = item.get("Key")
    size = item.get("Size")
    if not isinstance(key, str) or not isinstance(size, int) or size < 0:
        raise DukascopyAcquisitionError("AWS_LIST_OBJECT_METADATA_INVALID")
    try:
        key_pair, trading_day, side = parse_daily_candle_key(key)
    except DukascopyBi5Error:
        return None
    if key_pair != str(pair).upper():
        raise DukascopyAcquisitionError("AWS_LIST_PAIR_IDENTITY_MISMATCH")
    return SourceObject(
        pair=key_pair,
        trading_day=trading_day.isoformat(),
        side=side,
        key=key,
        size=size,
        etag=item.get("ETag") if isinstance(item.get("ETag"), str) else None,
        last_modified=item.get("LastModified") if isinstance(item.get("LastModified"), str) else None,
        data_type="MINUTE_CANDLE",
        storage_class=item.get("StorageClass") if isinstance(item.get("StorageClass"), str) else None,
    )


def _tick_source_object(item: dict[str, Any], *, pair: str) -> SourceObject | None:
    key = item.get("Key")
    size = item.get("Size")
    if not isinstance(key, str) or not isinstance(size, int) or size < 0:
        raise DukascopyAcquisitionError("AWS_LIST_OBJECT_METADATA_INVALID")
    try:
        key_pair, trading_day = parse_daily_tick_key(key)
    except DukascopyBi5Error:
        return None
    if key_pair != str(pair).upper():
        raise DukascopyAcquisitionError("AWS_LIST_PAIR_IDENTITY_MISMATCH")
    return SourceObject(
        pair=key_pair,
        trading_day=trading_day.isoformat(),
        side="BID_ASK",
        key=key,
        size=size,
        etag=item.get("ETag") if isinstance(item.get("ETag"), str) else None,
        last_modified=item.get("LastModified") if isinstance(item.get("LastModified"), str) else None,
        data_type="TICK",
        storage_class=item.get("StorageClass") if isinstance(item.get("StorageClass"), str) else None,
    )


def _is_known_non_target_key(item: dict[str, Any], *, pair: str) -> bool:
    key = item.get("Key")
    if not isinstance(key, str):
        return False
    tick_match = _TICK_KEY.fullmatch(key)
    if tick_match is not None and tick_match.group("symbol") == source_symbol(pair):
        return False
    aggregate_match = _MONTHLY_AGGREGATE_KEY.fullmatch(key)
    return aggregate_match is not None and aggregate_match.group("symbol") == source_symbol(pair)


def build_inventory(
    *,
    pairs: Sequence[str],
    start: datetime,
    end: datetime,
    listed_by_prefix: dict[tuple[str, str], Sequence[dict[str, Any]]],
) -> Inventory:
    """Build one deterministic same-provider source plan from bounded listings.

    A pair/day uses its two daily minute-candle objects only when both BID and
    ASK exist.  If either side is absent, the plan uses one same-provider tick
    object with both observed sides when that object exists.  The planner never
    combines a candle side with a tick side, and it records every unresolved
    source day instead of manufacturing a replacement.
    """
    canonical_pairs = tuple(sorted({str(pair).upper() for pair in pairs}))
    if not canonical_pairs:
        raise DukascopyAcquisitionError("INVENTORY_PAIR_SET_EMPTY")
    dates = _calendar_days(start, end)
    expected_minute_keys = {
        daily_candle_key(pair, trading_day, side)
        for pair in canonical_pairs
        for trading_day in dates
        for side in ("BID", "ASK")
    }
    minute_objects: dict[str, SourceObject] = {}
    tick_objects: dict[str, SourceObject] = {}
    non_target: set[str] = set()
    unexpected: set[str] = set()
    expected_prefixes = set(month_prefixes(canonical_pairs, start, end))
    if set(listed_by_prefix) != expected_prefixes:
        raise DukascopyAcquisitionError("INVENTORY_PREFIX_SET_INCOMPLETE")
    for (pair, prefix), items in sorted(listed_by_prefix.items()):
        if not prefix.startswith(f"{source_symbol(pair)}/"):
            raise DukascopyAcquisitionError("INVENTORY_PREFIX_PAIR_MISMATCH")
        for item in items:
            parsed = _source_object(item, pair=pair)
            if parsed is None:
                parsed = _tick_source_object(item, pair=pair)
            if parsed is None:
                key = str(item.get("Key", "<missing-key>"))
                if _is_known_non_target_key(item, pair=pair):
                    non_target.add(key)
                else:
                    unexpected.add(key)
                continue
            destination = minute_objects if parsed.data_type == "MINUTE_CANDLE" else tick_objects
            if parsed.key in minute_objects or parsed.key in tick_objects:
                raise DukascopyAcquisitionError("INVENTORY_DUPLICATE_SOURCE_KEY")
            destination[parsed.key] = parsed

    missing_minute = tuple(sorted(expected_minute_keys - set(minute_objects)))
    planned: list[SourceObject] = []
    fallback_tick: list[SourceObject] = []
    unresolved_days: dict[str, list[str]] = {pair: [] for pair in canonical_pairs}
    fallback_days: dict[str, list[str]] = {pair: [] for pair in canonical_pairs}
    for pair in canonical_pairs:
        for trading_day in dates:
            bid_key = daily_candle_key(pair, trading_day, "BID")
            ask_key = daily_candle_key(pair, trading_day, "ASK")
            bid = minute_objects.get(bid_key)
            ask = minute_objects.get(ask_key)
            if bid is not None and ask is not None:
                planned.extend((bid, ask))
                continue
            tick = tick_objects.get(daily_tick_key(pair, trading_day))
            if tick is not None:
                planned.append(tick)
                fallback_tick.append(tick)
                fallback_days[pair].append(trading_day.isoformat())
                continue
            unresolved_days[pair].append(trading_day.isoformat())

    selected = tuple(sorted(planned, key=lambda entry: entry.key))
    per_pair: dict[str, dict[str, Any]] = {}
    for pair in canonical_pairs:
        entries = [entry for entry in selected if entry.pair == pair]
        missing_entries = [key for key in missing_minute if key.startswith(f"{source_symbol(pair)}/")]
        unresolved = unresolved_days[pair]
        per_pair[pair] = {
            "PAIR": pair,
            "PREFIX": f"{source_symbol(pair)}/",
            "EXPECTED_DATE_RANGE": {"start": _utc_text(start), "end": _utc_text(end)},
            "BID_OBJECTS": sum(entry.side == "BID" for entry in entries),
            "ASK_OBJECTS": sum(entry.side == "ASK" for entry in entries),
            "TICK_FALLBACK_OBJECTS": sum(entry.data_type == "TICK" for entry in entries),
            "PLANNED_OBJECTS": len(entries),
            "PLANNED_BYTES": sum(entry.size for entry in entries),
            "MISSING_BID_DATES": [parse_daily_candle_key(key)[1].isoformat() for key in missing_entries if "/BID_" in key],
            "MISSING_ASK_DATES": [parse_daily_candle_key(key)[1].isoformat() for key in missing_entries if "/ASK_" in key],
            "TICK_FALLBACK_DATES": fallback_days[pair],
            "UNRESOLVED_SOURCE_DATES": unresolved,
            "STATUS": "INVENTORY_COMPLETE" if not unresolved else "SOURCE_DATE_GAPS",
        }
    return Inventory(
        start=_utc_text(start), end=_utc_text(end), pair_count=len(canonical_pairs),
        calendar_date_count=len(dates),
        bid_object_count=sum(entry.side == "BID" for entry in selected),
        ask_object_count=sum(entry.side == "ASK" for entry in selected),
        total_object_count=len(selected), total_listed_bytes=sum(entry.size for entry in selected),
        missing_expected_object_count=len(missing_minute),
        unresolved_source_day_count=sum(len(days) for days in unresolved_days.values()),
        available_tick_object_count=len(tick_objects), available_tick_bytes=sum(entry.size for entry in tick_objects.values()),
        fallback_tick_object_count=len(fallback_tick), fallback_tick_bytes=sum(entry.size for entry in fallback_tick),
        non_target_object_count=len(non_target), unexpected_object_count=len(unexpected), objects=selected,
        missing_expected_keys=missing_minute, non_target_keys=tuple(sorted(non_target)),
        unexpected_keys=tuple(sorted(unexpected)), per_pair=per_pair,
    )


def acquisition_chunks(inventory: Inventory, *, months_per_chunk: int = 1) -> tuple[AcquisitionChunk, ...]:
    """Group the frozen source plan into deterministic bounded transfers.

    Month-sized chunks are the default.  A caller may group up to six calendar
    months under one pair/year prefix to reduce CLI startup without widening the
    inventory; every source key remains an explicit ``--include`` pattern.
    """
    if isinstance(months_per_chunk, bool) or months_per_chunk <= 0 or months_per_chunk > 6:
        raise DukascopyAcquisitionError("ACQUISITION_MONTH_GROUP_INVALID")
    grouped: dict[tuple[str, str, str], list[SourceObject]] = {}
    for source in inventory.objects:
        parts = source.key.split("/")
        if len(parts) not in {4, 5} or any(not part or part in {".", ".."} for part in parts):
            raise DukascopyAcquisitionError("ACQUISITION_SOURCE_KEY_INVALID")
        if not "/".join(parts[:3]).startswith(f"{source_symbol(source.pair)}/"):
            raise DukascopyAcquisitionError("ACQUISITION_SOURCE_PAIR_MISMATCH")
        grouped.setdefault((source.pair, parts[1], parts[2]), []).append(source)
    chunks: list[AcquisitionChunk] = []
    pair_years = sorted({(pair, year) for pair, year, _month in grouped})
    for pair, year in pair_years:
        months = sorted(month for candidate_pair, candidate_year, month in grouped if candidate_pair == pair and candidate_year == year)
        for start_index in range(0, len(months), months_per_chunk):
            chunk_months = months[start_index:start_index + months_per_chunk]
            items = [source for month in chunk_months for source in grouped[(pair, year, month)]]
            if months_per_chunk == 1:
                prefix = f"{source_symbol(pair)}/{year}/{chunk_months[0]}/"
                chunk_id = f"{source_symbol(pair)}_{year}_{chunk_months[0]}"
            else:
                prefix = f"{source_symbol(pair)}/{year}/"
                chunk_id = f"{source_symbol(pair)}_{year}_{chunk_months[0]}_{chunk_months[-1]}"
            chunks.append(
                AcquisitionChunk(
                    pair=pair, prefix=prefix, objects=tuple(sorted(items, key=lambda item: item.key)), chunk_id=chunk_id
                )
            )
    return tuple(chunks)


def raw_object_path(raw_root: Path, source: SourceObject) -> Path:
    """Return a safe staging-relative raw path for one inventoried object."""
    try:
        if source.data_type == "MINUTE_CANDLE":
            parse_daily_candle_key(source.key)
        elif source.data_type == "TICK":
            parse_daily_tick_key(source.key)
        else:
            raise DukascopyAcquisitionError("ACQUISITION_SOURCE_TYPE_INVALID")
    except DukascopyBi5Error as exc:
        raise DukascopyAcquisitionError("ACQUISITION_SOURCE_KEY_INVALID") from exc
    destination = raw_root.joinpath(*source.key.split("/"))
    try:
        destination.resolve().relative_to(raw_root.resolve())
    except ValueError as exc:
        raise DukascopyAcquisitionError("ACQUISITION_RAW_PATH_INVALID") from exc
    return destination


def _chunk_receipt_path(receipt_root: Path, chunk: AcquisitionChunk) -> Path:
    if not re.fullmatch(r"[A-Z]{6}_20\d{2}_\d{2}(?:_\d{2})?", chunk.chunk_id):
        raise DukascopyAcquisitionError("ACQUISITION_CHUNK_ID_INVALID")
    return receipt_root / f"{chunk.chunk_id}.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                block = handle.read(1_048_576)
                if not block:
                    break
                digest.update(block)
    except OSError as exc:
        raise DukascopyAcquisitionError("ACQUISITION_RAW_FILE_READ_FAILED") from exc
    return digest.hexdigest()


def _chunk_local_records(chunk: AcquisitionChunk, raw_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for source in chunk.objects:
        path = raw_object_path(raw_root, source)
        temporary = path.with_name(f"{path.name}.part")
        if temporary.exists():
            raise DukascopyAcquisitionError("ACQUISITION_PARTIAL_LOCAL_SOURCE_OBJECT")
        if not path.is_file():
            missing.append(source.key)
            continue
        if path.stat().st_size != source.size:
            raise DukascopyAcquisitionError("ACQUISITION_LOCAL_SIZE_MISMATCH")
        records.append({
            "PAIR": source.pair,
            "DATE": source.trading_day,
            "SIDE": source.side,
            "DATA_TYPE": source.data_type,
            "OBJECT_KEY": source.key,
            "SIZE": source.size,
            "ETAG": source.etag,
            "LAST_MODIFIED": source.last_modified,
            "SHA256": _sha256_file(path),
        })
    return records, missing


def acquire_chunk(
    *,
    chunk: AcquisitionChunk,
    raw_root: Path,
    receipt_root: Path,
    output_root: Path,
    client: AwsRequesterPaysClient | None = None,
) -> dict[str, Any]:
    """Acquire or verify one checkpointed pair/month source chunk."""
    client = client or AwsRequesterPaysClient()
    receipt_path = _chunk_receipt_path(receipt_root, chunk)
    if receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DukascopyAcquisitionError("ACQUISITION_RECEIPT_INVALID") from exc
        expected_keys = [source.key for source in chunk.objects]
        if (
            receipt.get("schema") != "AIOS_PKT044_DUKASCOPY_ACQUISITION_CHUNK_V1"
            or receipt.get("PAIR") != chunk.pair
            or receipt.get("PREFIX") != chunk.prefix
            or receipt.get("CHUNK_ID") != chunk.chunk_id
            or receipt.get("OBJECT_KEYS") != expected_keys
        ):
            raise DukascopyAcquisitionError("ACQUISITION_RECEIPT_IDENTITY_MISMATCH")
        records, missing = _chunk_local_records(chunk, raw_root)
        if missing or receipt.get("RAW_OBJECTS") != records:
            raise DukascopyAcquisitionError("ACQUISITION_RECEIPT_LOCAL_STATE_MISMATCH")
        return receipt

    records, missing = _chunk_local_records(chunk, raw_root)
    if missing:
        prefix_root = raw_root.joinpath(*chunk.prefix.strip("/").split("/"))
        includes = [source.key[len(chunk.prefix):] for source in chunk.objects]
        client.sync_exact_objects(
            prefix=chunk.prefix, destination=prefix_root, include_patterns=includes, output_root=output_root
        )
        records, missing = _chunk_local_records(chunk, raw_root)
    if missing:
        raise DukascopyAcquisitionError("ACQUISITION_SYNC_OUTPUT_INCOMPLETE")
    receipt = {
        "schema": "AIOS_PKT044_DUKASCOPY_ACQUISITION_CHUNK_V1",
        "PAIR": chunk.pair,
        "PREFIX": chunk.prefix,
        "CHUNK_ID": chunk.chunk_id,
        "OBJECT_KEYS": [source.key for source in chunk.objects],
        "OBJECT_COUNT": len(chunk.objects),
        "RAW_BYTES": sum(source.size for source in chunk.objects),
        "RAW_OBJECTS": records,
        "STATUS": "COMPLETE",
    }
    write_new_deterministic_json(receipt_path, receipt)
    return receipt


def acquire_inventory_chunks(
    *,
    inventory: Inventory,
    semantics_gate: SourceSemanticsGate,
    raw_root: Path,
    receipt_root: Path,
    output_root: Path,
    cost_gate: CostGate,
    client: AwsRequesterPaysClient | None = None,
    max_new_chunks: int | None = None,
    months_per_chunk: int = 1,
) -> dict[str, int | bool]:
    """Advance a bounded, idempotent acquisition only through a passed gate."""
    if semantics_gate.semantic_fit != "PASS" or semantics_gate.acquisition_status != "ELIGIBLE":
        raise DukascopyAcquisitionError("ACQUISITION_SOURCE_SEMANTICS_NOT_ELIGIBLE")
    if cost_gate.cost_gate != "PASS" or cost_gate.conservative_total_job_cost_usd > cost_gate.owner_limit_usd:
        raise DukascopyAcquisitionError("ACQUISITION_COST_GATE_FAILED")
    if max_new_chunks is not None and (isinstance(max_new_chunks, bool) or max_new_chunks <= 0):
        raise DukascopyAcquisitionError("ACQUISITION_CHUNK_LIMIT_INVALID")
    client = client or AwsRequesterPaysClient()
    chunks = acquisition_chunks(inventory, months_per_chunk=months_per_chunk)
    completed = 0
    new_chunks = 0
    for chunk in chunks:
        receipt_path = _chunk_receipt_path(receipt_root, chunk)
        if receipt_path.is_file():
            acquire_chunk(
                chunk=chunk, raw_root=raw_root, receipt_root=receipt_root, output_root=output_root, client=client
            )
            completed += 1
            continue
        if max_new_chunks is not None and new_chunks >= max_new_chunks:
            break
        acquire_chunk(chunk=chunk, raw_root=raw_root, receipt_root=receipt_root, output_root=output_root, client=client)
        completed += 1
        new_chunks += 1
    return {
        "complete": completed == len(chunks),
        "completed_chunks": completed,
        "total_chunks": len(chunks),
        "new_chunks": new_chunks,
        "sync_calls": client.request_counts["sync"],
        "months_per_chunk": months_per_chunk,
        "source_objects_complete": sum(len(chunk.objects) for chunk in chunks[:completed]),
    }


def collect_inventory_from_aws(
    *,
    pairs: Sequence[str],
    start: datetime,
    end: datetime,
    client: AwsRequesterPaysClient | None = None,
    checkpoint_root: Path | None = None,
) -> tuple[Inventory, int]:
    """Collect only the exact pair/month listing set and return request count.

    When a checkpoint root is supplied, every completed month listing is saved
    before the next request.  A resumed run consumes only validated prior
    checkpoint files and never reissues their paid LIST request.
    """
    client = client or AwsRequesterPaysClient()
    if checkpoint_root is None:
        listed_by_prefix = {
            (pair, prefix): client.list_prefix(prefix)
            for pair, prefix in month_prefixes(pairs, start, end)
        }
        return build_inventory(pairs=pairs, start=start, end=end, listed_by_prefix=listed_by_prefix), client.request_counts["list"]
    progress = advance_inventory_checkpoints(
        pairs=pairs, start=start, end=end, checkpoint_root=checkpoint_root, client=client, max_new_prefixes=None
    )
    if not progress["complete"]:
        raise DukascopyAcquisitionError("INVENTORY_CHECKPOINT_COLLECTION_INCOMPLETE")
    return load_inventory_from_checkpoints(pairs=pairs, start=start, end=end, checkpoint_root=checkpoint_root), int(progress["new_list_requests"])


def advance_inventory_checkpoints(
    *,
    pairs: Sequence[str],
    start: datetime,
    end: datetime,
    checkpoint_root: Path,
    client: AwsRequesterPaysClient | None = None,
    max_new_prefixes: int | None,
) -> dict[str, int | bool]:
    """Advance a checkpointed inventory in a small explicit number of prefixes."""
    if max_new_prefixes is not None and (isinstance(max_new_prefixes, bool) or max_new_prefixes <= 0):
        raise DukascopyAcquisitionError("INVENTORY_CHUNK_LIMIT_INVALID")
    client = client or AwsRequesterPaysClient()
    before = client.request_counts["list"]
    prefixes = month_prefixes(pairs, start, end)
    completed = 0
    new_prefixes = 0
    for pair, prefix in prefixes:
        checkpoint = _listing_checkpoint_path(checkpoint_root, pair, prefix)
        if checkpoint.is_file():
            _read_listing_checkpoint(checkpoint, pair=pair, prefix=prefix)
            completed += 1
            continue
        if max_new_prefixes is not None and new_prefixes >= max_new_prefixes:
            break
        items = client.list_prefix(prefix)
        write_new_deterministic_json(
            checkpoint,
            {
                "schema": "AIOS_PKT044_DUKASCOPY_LIST_CHECKPOINT_V1",
                "PAIR": pair,
                "PREFIX": prefix,
                "OBJECTS": list(items),
            },
        )
        new_prefixes += 1
        completed += 1
    return {
        "complete": completed == len(prefixes),
        "completed_prefixes": completed,
        "total_prefixes": len(prefixes),
        "new_prefixes": new_prefixes,
        "new_list_requests": client.request_counts["list"] - before,
    }


def load_inventory_from_checkpoints(
    *, pairs: Sequence[str], start: datetime, end: datetime, checkpoint_root: Path
) -> Inventory:
    """Build only after every exact expected pair/month list checkpoint exists."""
    listed_by_prefix: dict[tuple[str, str], Sequence[dict[str, Any]]] = {}
    for pair, prefix in month_prefixes(pairs, start, end):
        checkpoint = _listing_checkpoint_path(checkpoint_root, pair, prefix)
        if not checkpoint.is_file():
            raise DukascopyAcquisitionError("INVENTORY_CHECKPOINT_COLLECTION_INCOMPLETE")
        listed_by_prefix[(pair, prefix)] = _read_listing_checkpoint(checkpoint, pair=pair, prefix=prefix)
    return build_inventory(pairs=pairs, start=start, end=end, listed_by_prefix=listed_by_prefix)


def _listing_checkpoint_path(root: Path, pair: str, prefix: str) -> Path:
    parts = prefix.strip("/").split("/")
    if len(parts) != 3 or parts[0] != source_symbol(pair):
        raise DukascopyAcquisitionError("INVENTORY_CHECKPOINT_PREFIX_INVALID")
    return root / "list_checkpoints" / f"{parts[0]}_{parts[1]}_{parts[2]}.json"


def _read_listing_checkpoint(path: Path, *, pair: str, prefix: str) -> tuple[dict[str, Any], ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DukascopyAcquisitionError("INVENTORY_CHECKPOINT_INVALID") from exc
    if (
        payload.get("schema") != "AIOS_PKT044_DUKASCOPY_LIST_CHECKPOINT_V1"
        or payload.get("PAIR") != pair
        or payload.get("PREFIX") != prefix
        or not isinstance(payload.get("OBJECTS"), list)
    ):
        raise DukascopyAcquisitionError("INVENTORY_CHECKPOINT_IDENTITY_MISMATCH")
    if not all(isinstance(item, dict) for item in payload["OBJECTS"]):
        raise DukascopyAcquisitionError("INVENTORY_CHECKPOINT_OBJECTS_INVALID")
    return tuple(payload["OBJECTS"])


def inventory_payload(inventory: Inventory) -> dict[str, Any]:
    return {
        "schema": "AIOS_PKT044_DUKASCOPY_OBJECT_INVENTORY_V1",
        "DEVELOPMENT_START": inventory.start,
        "DEVELOPMENT_END": inventory.end,
        "PAIR_COUNT": inventory.pair_count,
        "CALENDAR_DATE_COUNT": inventory.calendar_date_count,
        "BID_OBJECT_COUNT": inventory.bid_object_count,
        "ASK_OBJECT_COUNT": inventory.ask_object_count,
        "TOTAL_OBJECT_COUNT": inventory.total_object_count,
        "TOTAL_LISTED_BYTES": inventory.total_listed_bytes,
        "MISSING_EXPECTED_OBJECT_COUNT": inventory.missing_expected_object_count,
        "UNRESOLVED_SOURCE_DAY_COUNT": inventory.unresolved_source_day_count,
        "AVAILABLE_TICK_OBJECT_COUNT": inventory.available_tick_object_count,
        "AVAILABLE_TICK_BYTES": inventory.available_tick_bytes,
        "FALLBACK_TICK_OBJECT_COUNT": inventory.fallback_tick_object_count,
        "FALLBACK_TICK_BYTES": inventory.fallback_tick_bytes,
        "NON_TARGET_OBJECT_COUNT": inventory.non_target_object_count,
        "UNEXPECTED_OBJECT_COUNT": inventory.unexpected_object_count,
        "OBJECTS": [asdict(item) for item in inventory.objects],
        "MISSING_EXPECTED_KEYS": list(inventory.missing_expected_keys),
        "NON_TARGET_KEYS": list(inventory.non_target_keys),
        "UNEXPECTED_KEYS": list(inventory.unexpected_keys),
        "PER_PAIR": inventory.per_pair,
    }


def deterministic_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_new_deterministic_json(path: Path, payload: dict[str, Any]) -> str:
    """Write once; an idempotent same-byte rerun is allowed, overwrite is not."""
    data = deterministic_json_bytes(payload)
    digest = sha256_bytes(data)
    if path.exists():
        if path.read_bytes() != data:
            raise DukascopyAcquisitionError("OUTPUT_ALREADY_EXISTS_DIFFERENT")
        return digest
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    if temporary.exists():
        raise DukascopyAcquisitionError("OUTPUT_TEMPORARY_ALREADY_EXISTS")
    temporary.write_bytes(data)
    temporary.replace(path)
    return digest


def _semantic_tokens(values: Sequence[str], *, field: str) -> tuple[str, ...]:
    normalized = tuple(sorted({str(value).upper() for value in values}))
    if not normalized or any(not value or not re.fullmatch(r"[A-Z0-9_]+", value) for value in normalized):
        raise DukascopyAcquisitionError(f"SOURCE_SEMANTICS_{field}_INVALID")
    return normalized


def evaluate_source_semantics(
    *,
    requirement: SourceSemanticsRequirement,
    capability: SourceSemanticsCapability,
) -> SourceSemanticsGate:
    """Check source fitness before cost estimation or acquisition.

    A provider can be useful while still being unsuitable for a particular
    frozen strategy.  In particular, an observed BID/ASK candle pair does not
    prove a native MID stream, and a same-record tick midpoint is a separate
    strategy/data specification rather than a repair of a native-MID contract.
    """
    if not requirement.strategy_specification_id or not capability.source_id or not capability.evidence_id:
        raise DukascopyAcquisitionError("SOURCE_SEMANTICS_IDENTITY_MISSING")
    if isinstance(requirement.required_pair_count, bool) or requirement.required_pair_count <= 0:
        raise DukascopyAcquisitionError("SOURCE_SEMANTICS_REQUIRED_PAIR_COUNT_INVALID")
    if isinstance(capability.mapped_pair_count, bool) or capability.mapped_pair_count < 0:
        raise DukascopyAcquisitionError("SOURCE_SEMANTICS_MAPPED_PAIR_COUNT_INVALID")
    if requirement.midpoint_semantics not in _VALID_MID_SEMANTICS:
        raise DukascopyAcquisitionError("SOURCE_SEMANTICS_MIDPOINT_REQUIREMENT_INVALID")
    if requirement.preregistration_status not in {"FROZEN", "APPROVED", "PROPOSED"}:
        raise DukascopyAcquisitionError("SOURCE_SEMANTICS_PREREGISTRATION_STATUS_INVALID")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (capability.native_mid_object_count, capability.paired_tick_object_count)
    ):
        raise DukascopyAcquisitionError("SOURCE_SEMANTICS_OBJECT_COUNT_INVALID")

    required_sides = _semantic_tokens(requirement.required_price_sides, field="REQUIRED_PRICE_SIDES")
    available_sides = _semantic_tokens(capability.available_price_sides, field="AVAILABLE_PRICE_SIDES")
    required_granularity = str(requirement.timestamp_granularity).upper()
    required_construction = str(requirement.candle_construction).upper()
    if not re.fullmatch(r"[A-Z0-9_]+", required_granularity) or not re.fullmatch(r"[A-Z0-9_]+", required_construction):
        raise DukascopyAcquisitionError("SOURCE_SEMANTICS_REQUIREMENT_FORMAT_INVALID")
    available_granularities = _semantic_tokens(capability.timestamp_granularities, field="AVAILABLE_GRANULARITIES")
    available_constructions = _semantic_tokens(capability.candle_constructions, field="AVAILABLE_CONSTRUCTIONS")

    blockers: list[str] = []
    if capability.mapped_pair_count != requirement.required_pair_count:
        blockers.append("PAIR_COVERAGE_INCOMPLETE")
    for side in required_sides:
        if side not in available_sides:
            blockers.append(f"REQUIRED_PRICE_SIDE_MISSING_{side}")
    if required_granularity not in available_granularities:
        blockers.append("TIMESTAMP_GRANULARITY_UNSUPPORTED")
    if required_construction not in available_constructions:
        blockers.append("CANDLE_CONSTRUCTION_UNSUPPORTED")
    if not capability.execution_coverage_complete:
        blockers.append("EXECUTION_PRICE_COVERAGE_UNPROVEN")
    if requirement.activity_semantics != "NOT_REQUIRED" and requirement.activity_semantics != capability.activity_semantics:
        blockers.append("ACTIVITY_SEMANTICS_UNSUPPORTED")

    requires_new_fingerprint = requirement.midpoint_semantics == _MID_SEMANTICS_PAIRED_TICKS
    if requirement.midpoint_semantics == _MID_SEMANTICS_NATIVE:
        if "MID" not in available_sides or not capability.native_mid_coverage_complete:
            blockers.append("NATIVE_MID_REQUIRED")
    elif requirement.midpoint_semantics == _MID_SEMANTICS_PAIRED_TICKS:
        if "BID" not in available_sides or "ASK" not in available_sides:
            blockers.append("PAIRED_TICK_EXECUTION_SIDES_MISSING")
        if not capability.paired_tick_coverage_complete:
            blockers.append("PAIRED_TICK_COVERAGE_UNPROVEN")
        if not capability.paired_tick_same_record:
            blockers.append("PAIRED_TICK_SYNCHRONIZATION_UNPROVEN")

    ordered_blockers = tuple(sorted(set(blockers)))
    semantic_fit = "PASS" if not ordered_blockers else "FAIL"
    if ordered_blockers:
        acquisition_status = "BLOCKED"
    elif requirement.preregistration_status not in _ACQUISITION_READY_PREREGISTRATIONS:
        acquisition_status = "AWAITING_PREREGISTRATION"
    else:
        acquisition_status = "ELIGIBLE"
    return SourceSemanticsGate(
        strategy_specification_id=requirement.strategy_specification_id,
        source_id=capability.source_id,
        evidence_id=capability.evidence_id,
        semantic_fit=semantic_fit,
        acquisition_status=acquisition_status,
        requires_new_fingerprint=requires_new_fingerprint,
        blockers=ordered_blockers,
        required_pair_count=requirement.required_pair_count,
        mapped_pair_count=capability.mapped_pair_count,
        midpoint_semantics=requirement.midpoint_semantics,
        native_mid_object_count=capability.native_mid_object_count,
        paired_tick_object_count=capability.paired_tick_object_count,
    )


def source_semantics_gate_payload(
    gate: SourceSemanticsGate,
    *,
    requirement: SourceSemanticsRequirement,
    capability: SourceSemanticsCapability,
) -> dict[str, Any]:
    """Return a deterministic evidence record for a pre-acquisition decision."""
    return {
        "schema": "AIOS_PKT044_SOURCE_SEMANTICS_GATE_V1",
        "REQUIREMENT": asdict(requirement),
        "CAPABILITY": asdict(capability),
        "RESULT": asdict(gate),
    }


def plan_paired_tick_inventory(
    *,
    pairs: Sequence[str],
    start: datetime,
    end: datetime,
) -> PairedTickInventoryPlan:
    """Plan one source-native tick object per pair/day without listing S3.

    This is intentionally an *expected* inventory.  It asserts neither that a
    key exists nor that its data is usable.  A later, explicitly authorised
    inventory phase must turn this plan into evidence before a cost gate or
    acquisition can become eligible.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise DukascopyAcquisitionError("PAIRED_TICK_PLAN_TIMEZONE_MISSING")
    if start.astimezone(UTC).time() != datetime.min.time() or end.astimezone(UTC).time() != datetime.min.time():
        raise DukascopyAcquisitionError("PAIRED_TICK_PLAN_BOUNDARY_NOT_UTC_DAY")
    canonical_pairs = tuple(sorted({source_symbol(pair) for pair in pairs}))
    if not canonical_pairs or len(canonical_pairs) != len(tuple(pairs)):
        raise DukascopyAcquisitionError("PAIRED_TICK_PLAN_PAIR_SET_INVALID")
    days = _calendar_days(start.astimezone(UTC), end.astimezone(UTC))
    objects = tuple(
        daily_tick_key(symbol, trading_day)
        for symbol in canonical_pairs
        for trading_day in days
    )
    if len(objects) != len(set(objects)):
        raise DukascopyAcquisitionError("PAIRED_TICK_PLAN_DUPLICATE_KEY")
    return PairedTickInventoryPlan(
        start=_utc_text(start),
        end=_utc_text(end),
        pair_count=len(canonical_pairs),
        calendar_date_count=len(days),
        total_expected_tick_object_count=len(objects),
        objects=objects,
    )


def paired_tick_inventory_plan_payload(plan: PairedTickInventoryPlan) -> dict[str, Any]:
    """Return deterministic pre-acquisition evidence without availability claims."""
    return {
        "schema": "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_EXPECTED_INVENTORY_V1",
        "START": plan.start,
        "END_EXCLUSIVE": plan.end,
        "PAIR_COUNT": plan.pair_count,
        "CALENDAR_DATE_COUNT": plan.calendar_date_count,
        "TOTAL_EXPECTED_TICK_OBJECT_COUNT": plan.total_expected_tick_object_count,
        "OBJECT_KEYS": list(plan.objects),
        "INVENTORY_STATUS": "EXPECTED_KEYS_ONLY_NO_AWS_REQUESTS",
        "EXISTENCE_STATUS": "UNVERIFIED_REQUIRES_LATER_AUTHORIZED_LIST",
    }


def build_paired_tick_inventory(
    *,
    pairs: Sequence[str],
    start: datetime,
    end: datetime,
    listed_by_prefix: dict[tuple[str, str], Sequence[dict[str, Any]]],
) -> PairedTickInventory:
    """Build the exact PKT-045 paired-tick inventory from bounded listings.

    This intentionally selects only daily ``*_ticks.bi5`` objects.  BID/ASK
    minute-candle objects remain non-target layout evidence and cannot enter
    the successor corpus or its cost estimate.
    """
    canonical_pairs = tuple(sorted({canonical_pair(pair) for pair in pairs}))
    if not canonical_pairs or len(canonical_pairs) != len(tuple(pairs)):
        raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_PAIR_SET_INVALID")
    plan = plan_paired_tick_inventory(pairs=canonical_pairs, start=start, end=end)
    expected_keys = set(plan.objects)
    expected_prefixes = set(month_prefixes(canonical_pairs, start, end))
    if set(listed_by_prefix) != expected_prefixes:
        raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_PREFIX_SET_INCOMPLETE")

    tick_objects: dict[str, SourceObject] = {}
    non_target: set[str] = set()
    unexpected: set[str] = set()
    for (pair, prefix), items in sorted(listed_by_prefix.items()):
        canonical = canonical_pair(pair)
        if canonical not in canonical_pairs or not prefix.startswith(f"{source_symbol(canonical)}/"):
            raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_PREFIX_PAIR_MISMATCH")
        for item in items:
            parsed = _tick_source_object(item, pair=canonical)
            if parsed is not None:
                if parsed.key in tick_objects:
                    raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_DUPLICATE_SOURCE_KEY")
                if parsed.key in expected_keys:
                    tick_objects[parsed.key] = parsed
                else:
                    unexpected.add(parsed.key)
                continue
            key = item.get("Key")
            if not isinstance(key, str):
                raise DukascopyAcquisitionError("AWS_LIST_OBJECT_METADATA_INVALID")
            try:
                candle_pair, _day, _side = parse_daily_candle_key(key)
            except DukascopyBi5Error:
                if _is_known_non_target_key(item, pair=canonical):
                    non_target.add(key)
                else:
                    unexpected.add(key)
            else:
                if candle_pair != canonical:
                    raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_CANDLE_PAIR_MISMATCH")
                non_target.add(key)

    selected = tuple(sorted(tick_objects.values(), key=lambda item: item.key))
    missing = tuple(sorted(expected_keys - set(tick_objects)))
    per_pair: dict[str, dict[str, Any]] = {}
    for pair in canonical_pairs:
        pair_objects = tuple(item for item in selected if item.pair == pair)
        pair_missing = tuple(key for key in missing if key.startswith(f"{source_symbol(pair)}/"))
        per_pair[pair] = {
            "PAIR": pair,
            "PREFIX": f"{source_symbol(pair)}/",
            "EXPECTED_DATE_RANGE": {"start": _utc_text(start), "end": _utc_text(end)},
            "EXPECTED_TICK_OBJECTS": plan.calendar_date_count,
            "TICK_OBJECTS": len(pair_objects),
            "LISTED_BYTES": sum(item.size for item in pair_objects),
            "MISSING_TICK_DATES": [parse_daily_tick_key(key)[1].isoformat() for key in pair_missing],
            "STATUS": "INVENTORY_COMPLETE" if not pair_missing else "SOURCE_DATE_GAPS",
        }
    return PairedTickInventory(
        start=plan.start,
        end=plan.end,
        pair_count=plan.pair_count,
        calendar_date_count=plan.calendar_date_count,
        expected_tick_object_count=plan.total_expected_tick_object_count,
        available_tick_object_count=len(selected),
        total_listed_bytes=sum(item.size for item in selected),
        missing_expected_object_count=len(missing),
        non_target_object_count=len(non_target),
        unexpected_object_count=len(unexpected),
        objects=selected,
        missing_expected_keys=missing,
        non_target_keys=tuple(sorted(non_target)),
        unexpected_keys=tuple(sorted(unexpected)),
        per_pair=per_pair,
    )


def _paired_tick_listing_checkpoint_path(root: Path, pair: str, prefix: str) -> Path:
    parts = prefix.strip("/").split("/")
    canonical = canonical_pair(pair)
    if len(parts) != 3 or parts[0] != source_symbol(canonical):
        raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_CHECKPOINT_PREFIX_INVALID")
    return root / "tick_list_checkpoints" / f"{parts[0]}_{parts[1]}_{parts[2]}.json"


def _read_paired_tick_listing_checkpoint(path: Path, *, pair: str, prefix: str) -> tuple[dict[str, Any], ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_CHECKPOINT_INVALID") from exc
    if (
        payload.get("schema") != "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_LIST_CHECKPOINT_V1"
        or payload.get("PAIR") != canonical_pair(pair)
        or payload.get("PREFIX") != prefix
        or not isinstance(payload.get("OBJECTS"), list)
        or isinstance(payload.get("LIST_REQUESTS"), bool)
        or not isinstance(payload.get("LIST_REQUESTS"), int)
        or payload["LIST_REQUESTS"] <= 0
    ):
        raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_CHECKPOINT_IDENTITY_MISMATCH")
    if not all(isinstance(item, dict) for item in payload["OBJECTS"]):
        raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_CHECKPOINT_OBJECTS_INVALID")
    return tuple(payload["OBJECTS"])


def paired_tick_inventory_list_request_count(
    *, pairs: Sequence[str], start: datetime, end: datetime, checkpoint_root: Path
) -> int:
    """Read the durable request count without making an AWS request."""
    total = 0
    for pair, prefix in month_prefixes(tuple(canonical_pair(item) for item in pairs), start, end):
        path = _paired_tick_listing_checkpoint_path(checkpoint_root, pair, prefix)
        _read_paired_tick_listing_checkpoint(path, pair=pair, prefix=prefix)
        payload = json.loads(path.read_text(encoding="utf-8"))
        total += payload["LIST_REQUESTS"]
    return total


def advance_paired_tick_inventory_checkpoints(
    *,
    pairs: Sequence[str],
    start: datetime,
    end: datetime,
    checkpoint_root: Path,
    client: AwsRequesterPaysClient | None = None,
    max_new_prefixes: int | None,
    max_pages_per_prefix: int,
) -> dict[str, int | bool]:
    """Checkpoint exact P45 pair/month listings without rescanning prior work."""
    if max_new_prefixes is not None and (isinstance(max_new_prefixes, bool) or max_new_prefixes <= 0):
        raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_CHUNK_LIMIT_INVALID")
    if isinstance(max_pages_per_prefix, bool) or max_pages_per_prefix <= 0:
        raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_PAGE_LIMIT_INVALID")
    canonical_pairs = tuple(canonical_pair(pair) for pair in pairs)
    if len(set(canonical_pairs)) != len(canonical_pairs):
        raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_PAIR_SET_INVALID")
    client = client or AwsRequesterPaysClient()
    before = client.request_counts["list"]
    prefixes = month_prefixes(canonical_pairs, start, end)
    completed = 0
    new_prefixes = 0
    for pair, prefix in prefixes:
        checkpoint = _paired_tick_listing_checkpoint_path(checkpoint_root, pair, prefix)
        if checkpoint.is_file():
            _read_paired_tick_listing_checkpoint(checkpoint, pair=pair, prefix=prefix)
            completed += 1
            continue
        if max_new_prefixes is not None and new_prefixes >= max_new_prefixes:
            break
        before_prefix = client.request_counts["list"]
        items = client.list_prefix(prefix, max_pages=max_pages_per_prefix)
        request_count = client.request_counts["list"] - before_prefix
        write_new_deterministic_json(
            checkpoint,
            {
                "schema": "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_LIST_CHECKPOINT_V1",
                "PAIR": canonical_pair(pair),
                "PREFIX": prefix,
                "LIST_REQUESTS": request_count,
                "OBJECTS": list(items),
            },
        )
        new_prefixes += 1
        completed += 1
    return {
        "complete": completed == len(prefixes),
        "completed_prefixes": completed,
        "total_prefixes": len(prefixes),
        "new_prefixes": new_prefixes,
        "new_list_requests": client.request_counts["list"] - before,
    }


def load_paired_tick_inventory_from_checkpoints(
    *, pairs: Sequence[str], start: datetime, end: datetime, checkpoint_root: Path
) -> PairedTickInventory:
    """Load a complete exact P45 inventory; missing checkpoints fail closed."""
    canonical_pairs = tuple(canonical_pair(pair) for pair in pairs)
    listed: dict[tuple[str, str], Sequence[dict[str, Any]]] = {}
    for pair, prefix in month_prefixes(canonical_pairs, start, end):
        checkpoint = _paired_tick_listing_checkpoint_path(checkpoint_root, pair, prefix)
        if not checkpoint.is_file():
            raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_CHECKPOINT_COLLECTION_INCOMPLETE")
        listed[(pair, prefix)] = _read_paired_tick_listing_checkpoint(checkpoint, pair=pair, prefix=prefix)
    return build_paired_tick_inventory(pairs=canonical_pairs, start=start, end=end, listed_by_prefix=listed)


def collect_paired_tick_inventory_from_aws(
    *,
    pairs: Sequence[str],
    start: datetime,
    end: datetime,
    checkpoint_root: Path,
    client: AwsRequesterPaysClient | None = None,
    max_new_prefixes: int | None = None,
    max_pages_per_prefix: int = 2,
) -> tuple[PairedTickInventory, dict[str, int | bool]]:
    """Collect the finite P45 tick inventory, resuming only trusted checkpoints."""
    progress = advance_paired_tick_inventory_checkpoints(
        pairs=pairs,
        start=start,
        end=end,
        checkpoint_root=checkpoint_root,
        client=client,
        max_new_prefixes=max_new_prefixes,
        max_pages_per_prefix=max_pages_per_prefix,
    )
    if not progress["complete"]:
        raise DukascopyAcquisitionError("PAIRED_TICK_INVENTORY_CHECKPOINT_COLLECTION_INCOMPLETE")
    return load_paired_tick_inventory_from_checkpoints(
        pairs=pairs, start=start, end=end, checkpoint_root=checkpoint_root
    ), progress


def paired_tick_inventory_payload(inventory: PairedTickInventory) -> dict[str, Any]:
    """Deterministic inventory evidence; it makes no corpus-certification claim."""
    return {
        "schema": "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_OBJECT_INVENTORY_V1",
        "DEVELOPMENT_START": inventory.start,
        "DEVELOPMENT_END": inventory.end,
        "PAIR_COUNT": inventory.pair_count,
        "CALENDAR_DATE_COUNT": inventory.calendar_date_count,
        "EXPECTED_TICK_OBJECT_COUNT": inventory.expected_tick_object_count,
        "AVAILABLE_TICK_OBJECT_COUNT": inventory.available_tick_object_count,
        "TOTAL_LISTED_BYTES": inventory.total_listed_bytes,
        "MISSING_EXPECTED_OBJECT_COUNT": inventory.missing_expected_object_count,
        "NON_TARGET_OBJECT_COUNT": inventory.non_target_object_count,
        "UNEXPECTED_OBJECT_COUNT": inventory.unexpected_object_count,
        "OBJECTS": [asdict(item) for item in inventory.objects],
        "MISSING_EXPECTED_KEYS": list(inventory.missing_expected_keys),
        "NON_TARGET_KEYS": list(inventory.non_target_keys),
        "UNEXPECTED_KEYS": list(inventory.unexpected_keys),
        "PER_PAIR": inventory.per_pair,
        "INVENTORY_STATUS": "VERIFIED_EXACT_TICK_LISTING",
        "CORPUS_CERTIFICATION_STATUS": "NOT_RUN",
        "SCORING_STATUS": "BLOCKED_AWAITING_CERTIFIED_CORPUS",
    }


def build_paired_tick_cost_gate(
    *,
    inventory: PairedTickInventory,
    semantics_gate: PairedTickPreacquisitionGate,
    mapped_pair_count: int,
    total_list_requests_actual: int,
    prior_spend_estimate_usd: float,
    pricing: CostBasis,
    retry_and_uncertainty_reserve_usd: float,
    owner_limit_usd: float = 1.0,
    total_head_requests_planned: int = 0,
    other_applicable_cost_usd: float = 0.0,
) -> PairedTickCostGate:
    """Compute the full cumulative P45 cost gate from exact tick objects.

    The gate grants no certification or score.  It treats each listed paired
    tick object as one future GetObject request and assumes no unproven free
    transfer allowance.  Automatic GET retries are intentionally not planned;
    a failed charged request is a checkpointed stop, not a way around the
    owner's hard ceiling.
    """
    if semantics_gate.semantic_contract_status != "PASS":
        raise DukascopyAcquisitionError("PAIRED_TICK_COST_GATE_SEMANTICS_FAILED")
    if mapped_pair_count != semantics_gate.required_pair_count or inventory.pair_count != mapped_pair_count:
        raise DukascopyAcquisitionError("PAIRED_TICK_COST_GATE_PAIR_MAPPING_INCOMPLETE")
    if inventory.available_tick_object_count <= 0 or inventory.available_tick_object_count != len(inventory.objects):
        raise DukascopyAcquisitionError("PAIRED_TICK_COST_GATE_INVENTORY_EMPTY_OR_INVALID")
    if any(item.storage_class != "STANDARD" for item in inventory.objects):
        raise DukascopyAcquisitionError("PAIRED_TICK_COST_GATE_STORAGE_CLASS_PRICING_REQUIRED")
    numeric = (
        total_list_requests_actual, prior_spend_estimate_usd, pricing.list_per_1000_usd,
        pricing.get_per_1000_usd, pricing.head_per_1000_usd, pricing.retrieval_per_gb_usd, pricing.transfer_per_gb_usd,
        retry_and_uncertainty_reserve_usd, owner_limit_usd, total_head_requests_planned,
        other_applicable_cost_usd,
    )
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 for value in numeric):
        raise DukascopyAcquisitionError("PAIRED_TICK_COST_GATE_BASIS_INVALID")
    inventory_cost = total_list_requests_actual / 1_000 * pricing.list_per_1000_usd
    request_cost = (
        inventory.available_tick_object_count / 1_000 * pricing.get_per_1000_usd
        + total_head_requests_planned / 1_000 * pricing.head_per_1000_usd
    )
    transfer_cost = inventory.total_listed_bytes / 1_000_000_000 * pricing.transfer_per_gb_usd
    retrieval_cost = inventory.total_listed_bytes / 1_000_000_000 * pricing.retrieval_per_gb_usd
    total = (
        prior_spend_estimate_usd + inventory_cost + request_cost + retrieval_cost + transfer_cost
        + other_applicable_cost_usd + retry_and_uncertainty_reserve_usd
    )
    return PairedTickCostGate(
        total_objects=inventory.available_tick_object_count,
        total_list_requests_actual=int(total_list_requests_actual),
        total_get_requests_planned=inventory.available_tick_object_count,
        total_head_requests_planned=int(total_head_requests_planned),
        exact_listed_object_bytes=inventory.total_listed_bytes,
        conservative_download_bytes=inventory.total_listed_bytes,
        prior_spend_estimate_usd=float(prior_spend_estimate_usd),
        inventory_cost_usd=inventory_cost,
        remaining_request_cost_usd=request_cost,
        remaining_retrieval_cost_usd=retrieval_cost,
        remaining_transfer_cost_usd=transfer_cost,
        other_applicable_cost_usd=float(other_applicable_cost_usd),
        retry_and_uncertainty_reserve_usd=float(retry_and_uncertainty_reserve_usd),
        conservative_total_project_cost_usd=total,
        owner_limit_usd=float(owner_limit_usd),
        source_semantics_status="PASS_PAIRED_TICK_CONTRACT",
        inventory_status="VERIFIED_EXACT_TICK_LISTING",
        cost_gate="PASS" if total <= owner_limit_usd else "FAIL",
    )


def paired_tick_cost_gate_payload(cost_gate: PairedTickCostGate, pricing: CostBasis) -> dict[str, Any]:
    """Return the exact P45 cumulative-cost evidence without a free allowance."""
    payload = asdict(cost_gate)
    payload.update({
        "schema": "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_COST_GATE_V1",
        "AWS_PRICE_SOURCE": pricing.price_source,
        "SOURCE_RETRIEVED_AT": pricing.retrieved_at_utc,
        "FREE_ALLOWANCE_ASSUMPTION": pricing.free_allowance_assumption,
        "LIST_PRICE_AND_UNIT": f"{pricing.list_per_1000_usd} USD per 1,000 requests",
        "GET_PRICE_AND_UNIT": f"{pricing.get_per_1000_usd} USD per 1,000 requests",
        "HEAD_PRICE_AND_UNIT": f"{pricing.head_per_1000_usd} USD per 1,000 requests",
        "RETRIEVAL_PRICE_AND_UNIT": f"{pricing.retrieval_per_gb_usd} USD per GB",
        "DATA_TRANSFER_PRICE_AND_UNIT": f"{pricing.transfer_per_gb_usd} USD per GB",
        "AUTOMATIC_GET_RETRIES": 0,
        "CORPUS_CERTIFICATION_STATUS": "NOT_RUN",
        "SCORING_STATUS": "BLOCKED_AWAITING_COST_GATE_AND_CERTIFIED_CORPUS",
    })
    return payload


def authorize_paired_tick_acquisition(
    *,
    preacquisition_gate: PairedTickPreacquisitionGate,
    inventory: PairedTickInventory,
    cost_gate: PairedTickCostGate,
    packet_id: str = "PKT-FOREX-045",
) -> PairedTickAcquisitionGate:
    """Combine the completed P45 gates into the only acquisition authority.

    The preacquisition gate intentionally remains an evidence-only local proof.
    It cannot be passed directly to a downloader.  This narrow transition is
    allowed only when that proof, the exact 58-pair inventory and the whole-job
    cost gate all independently pass.
    """
    if packet_id != "PKT-FOREX-045":
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_PACKET_ID_INVALID")
    if preacquisition_gate.semantic_contract_status != "PASS":
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_SEMANTICS_NOT_PASSED")
    if preacquisition_gate.required_pair_count != preacquisition_gate.mapped_pair_count:
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_PAIR_MAPPING_INCOMPLETE")
    if inventory.pair_count != preacquisition_gate.required_pair_count:
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_INVENTORY_PAIR_COUNT_MISMATCH")
    if inventory.available_tick_object_count <= 0 or inventory.available_tick_object_count != len(inventory.objects):
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_INVENTORY_EMPTY_OR_INVALID")
    if inventory.unexpected_object_count:
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_INVENTORY_UNEXPECTED_OBJECTS")
    if cost_gate.source_semantics_status != "PASS_PAIRED_TICK_CONTRACT" or cost_gate.inventory_status != "VERIFIED_EXACT_TICK_LISTING":
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_COST_INPUTS_UNVERIFIED")
    if cost_gate.cost_gate != "PASS" or cost_gate.conservative_total_project_cost_usd > cost_gate.owner_limit_usd:
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_COST_GATE_FAILED")
    if cost_gate.total_objects != inventory.available_tick_object_count:
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_COST_OBJECT_COUNT_MISMATCH")
    return PairedTickAcquisitionGate(
        packet_id=packet_id,
        required_pair_count=preacquisition_gate.required_pair_count,
        mapped_pair_count=preacquisition_gate.mapped_pair_count,
        available_tick_object_count=inventory.available_tick_object_count,
        inventory_missing_calendar_keys=inventory.missing_expected_object_count,
        inventory_unexpected_object_count=inventory.unexpected_object_count,
        source_semantics_status=preacquisition_gate.semantic_contract_status,
        cost_gate=cost_gate.cost_gate,
        conservative_total_project_cost_usd=cost_gate.conservative_total_project_cost_usd,
        owner_limit_usd=cost_gate.owner_limit_usd,
        acquisition_status="ELIGIBLE_AFTER_FULL_COVERAGE_AND_COST_GATE",
    )


def _paired_tick_object_receipt_path(receipt_root: Path, source: SourceObject) -> Path:
    """Return an exact-object receipt path without allowing path traversal."""
    if source.data_type != "TICK" or source.side != "BID_ASK":
        raise DukascopyAcquisitionError("PAIRED_TICK_RECEIPT_SOURCE_TYPE_INVALID")
    try:
        parse_daily_tick_key(source.key)
    except DukascopyBi5Error as exc:
        raise DukascopyAcquisitionError("PAIRED_TICK_RECEIPT_SOURCE_KEY_INVALID") from exc
    destination = receipt_root / "raw_object_receipts" / Path(*source.key.split("/"))
    destination = destination.with_suffix(".json")
    try:
        destination.resolve().relative_to(receipt_root.resolve())
    except ValueError as exc:
        raise DukascopyAcquisitionError("PAIRED_TICK_RECEIPT_PATH_INVALID") from exc
    return destination


def _paired_tick_source_identity(source: SourceObject) -> dict[str, Any]:
    """Return the immutable inventory identity required for one raw tick file."""
    if source.data_type != "TICK" or source.side != "BID_ASK" or source.storage_class != "STANDARD":
        raise DukascopyAcquisitionError("PAIRED_TICK_SOURCE_IDENTITY_INVALID")
    pair, trading_day = parse_daily_tick_key(source.key)
    if pair != source.pair or trading_day.isoformat() != source.trading_day or source.size <= 0:
        raise DukascopyAcquisitionError("PAIRED_TICK_SOURCE_IDENTITY_MISMATCH")
    return {
        "PAIR": source.pair,
        "DATE": source.trading_day,
        "SIDE": source.side,
        "DATA_TYPE": source.data_type,
        "OBJECT_KEY": source.key,
        "LISTED_SIZE": source.size,
        "LISTED_ETAG": source.etag,
        "LISTED_LAST_MODIFIED": source.last_modified,
        "STORAGE_CLASS": source.storage_class,
    }


def _response_metadata(response: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only non-secret GetObject response fields needed for provenance."""
    allowed = ("ContentLength", "ETag", "VersionId", "LastModified", "ContentType")
    return {key: response[key] for key in allowed if key in response}


def _read_paired_tick_receipt(path: Path, source: SourceObject, raw_root: Path) -> dict[str, Any]:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DukascopyAcquisitionError("PAIRED_TICK_RAW_RECEIPT_INVALID") from exc
    identity = _paired_tick_source_identity(source)
    if receipt.get("schema") != "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_RAW_OBJECT_RECEIPT_V1":
        raise DukascopyAcquisitionError("PAIRED_TICK_RAW_RECEIPT_SCHEMA_INVALID")
    if receipt.get("STATUS") != "COMPLETE" or receipt.get("SOURCE") != identity:
        raise DukascopyAcquisitionError("PAIRED_TICK_RAW_RECEIPT_IDENTITY_MISMATCH")
    raw_path = raw_object_path(raw_root, source)
    if raw_path.with_name(f"{raw_path.name}.part").exists():
        raise DukascopyAcquisitionError("PAIRED_TICK_RAW_PARTIAL_OBJECT_PRESENT")
    if not raw_path.is_file() or raw_path.stat().st_size != source.size:
        raise DukascopyAcquisitionError("PAIRED_TICK_RAW_RECEIPT_LOCAL_STATE_MISMATCH")
    local_hash = _sha256_file(raw_path)
    if receipt.get("LOCAL_SHA256") != local_hash:
        raise DukascopyAcquisitionError("PAIRED_TICK_RAW_RECEIPT_HASH_MISMATCH")
    response = receipt.get("GET_OBJECT_RESPONSE")
    if not isinstance(response, dict) or response.get("ContentLength") != source.size:
        raise DukascopyAcquisitionError("PAIRED_TICK_RAW_RECEIPT_RESPONSE_INVALID")
    returned_etag = response.get("ETag")
    if source.etag is not None and returned_etag != source.etag:
        raise DukascopyAcquisitionError("PAIRED_TICK_RAW_RECEIPT_ETAG_MISMATCH")
    return receipt


def paired_tick_completed_raw_receipts(
    *, inventory: PairedTickInventory, raw_root: Path, receipt_root: Path
) -> tuple[dict[str, Any], ...]:
    """Read only checked local P45 receipts; an unreceipted file is ineligible."""
    records: list[dict[str, Any]] = []
    for source in inventory.objects:
        receipt_path = _paired_tick_object_receipt_path(receipt_root, source)
        if not receipt_path.is_file():
            continue
        records.append(_read_paired_tick_receipt(receipt_path, source, raw_root))
    return tuple(records)


def _atomic_operational_json(path: Path, payload: dict[str, Any]) -> None:
    """Durably update mutable operational state without sealing scientific evidence."""
    data = deterministic_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _paired_tick_acquisition_projection(
    *, cost_gate: PairedTickCostGate, completed_count: int, completed_bytes: int
) -> dict[str, Any]:
    """Return a conservative whole-job projection before each chargeable GET.

    The cost gate already budgets every exact listed object.  This explicit
    progress view makes it impossible for a resume to mistake completed work
    for free headroom or to add automatic retry capacity.
    """
    if completed_count < 0 or completed_bytes < 0:
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_PROGRESS_INVALID")
    if completed_count > cost_gate.total_objects or completed_bytes > cost_gate.conservative_download_bytes:
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_PROGRESS_EXCEEDS_PLAN")
    return {
        "COMPLETED_OBJECTS": completed_count,
        "COMPLETED_BYTES": completed_bytes,
        "REMAINING_OBJECTS": cost_gate.total_objects - completed_count,
        "REMAINING_BYTES": cost_gate.conservative_download_bytes - completed_bytes,
        "PROJECTED_TOTAL_PROJECT_COST_USD": cost_gate.conservative_total_project_cost_usd,
        "OWNER_LIMIT_USD": cost_gate.owner_limit_usd,
        "AUTOMATIC_GET_RETRIES": 1,
        "WITHIN_HARD_LIMIT": cost_gate.conservative_total_project_cost_usd <= cost_gate.owner_limit_usd,
    }


def acquire_paired_tick_inventory(
    *,
    inventory: PairedTickInventory,
    acquisition_gate: PairedTickAcquisitionGate,
    cost_gate: PairedTickCostGate,
    raw_root: Path,
    receipt_root: Path,
    checkpoint_path: Path,
    output_root: Path,
    client: AwsRequesterPaysClient | None = None,
    max_new_objects: int | None = None,
    before_get: Callable[[SourceObject, Mapping[str, Any]], None] | None = None,
    retry_state_path: Path | None = None,
    started_at: float | None = None,
    max_concurrent_gets: int = 1,
) -> dict[str, Any]:
    """Acquire only sealed P45 paired-tick objects, one receipted GET at a time.

    No generic S3 sync is used here: every possible paid request is an
    inventoried GetObject with a durable object receipt, exact size check and
    SHA-256. Temporary failures receive at most one durable retry per key.
    """
    if (
        acquisition_gate.packet_id != "PKT-FOREX-045"
        or acquisition_gate.acquisition_status != "ELIGIBLE_AFTER_FULL_COVERAGE_AND_COST_GATE"
        or acquisition_gate.source_semantics_status != "PASS"
        or acquisition_gate.cost_gate != "PASS"
        or acquisition_gate.conservative_total_project_cost_usd > acquisition_gate.owner_limit_usd
    ):
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_GATE_NOT_ELIGIBLE")
    if cost_gate.cost_gate != "PASS" or cost_gate.conservative_total_project_cost_usd > cost_gate.owner_limit_usd:
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_COST_GATE_FAILED")
    if max_new_objects is not None and (isinstance(max_new_objects, bool) or max_new_objects <= 0):
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_OBJECT_LIMIT_INVALID")
    if isinstance(max_concurrent_gets, bool) or not isinstance(max_concurrent_gets, int) or not 1 <= max_concurrent_gets <= 4:
        raise DukascopyAcquisitionError("PAIRED_TICK_MAX_CONCURRENCY_INVALID")
    try:
        raw_root.resolve().relative_to(output_root.resolve())
        receipt_root.resolve().relative_to(output_root.resolve())
        checkpoint_path.resolve().relative_to(output_root.resolve())
    except ValueError as exc:
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_OUTPUT_SCOPE_INVALID") from exc
    if (
        inventory.pair_count != acquisition_gate.required_pair_count
        or acquisition_gate.mapped_pair_count != acquisition_gate.required_pair_count
        or inventory.available_tick_object_count != acquisition_gate.available_tick_object_count
        or inventory.available_tick_object_count != len(inventory.objects)
        or inventory.available_tick_object_count != cost_gate.total_objects
    ):
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_INVENTORY_MISMATCH")
    client = client or AwsRequesterPaysClient()
    completed_receipts = paired_tick_completed_raw_receipts(
        inventory=inventory, raw_root=raw_root, receipt_root=receipt_root,
    )
    completed_by_key = {record["SOURCE"]["OBJECT_KEY"]: record for record in completed_receipts}
    if len(completed_by_key) != len(completed_receipts):
        raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_DUPLICATE_RECEIPT")
    completed_bytes = sum(int(record["SOURCE"]["LISTED_SIZE"]) for record in completed_receipts)
    retry_state_path = retry_state_path or checkpoint_path.with_name("retry_attempts.json")
    try:
        retry_state = json.loads(retry_state_path.read_text(encoding="utf-8")) if retry_state_path.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise DukascopyAcquisitionError("PAIRED_TICK_RETRY_STATE_INVALID") from exc
    if not isinstance(retry_state, dict):
        raise DukascopyAcquisitionError("PAIRED_TICK_RETRY_STATE_INVALID")
    new_objects = 0
    deferred_keys: set[str] = set()
    exhausted_keys: set[str] = set()

    if max_concurrent_gets > 1:
        # The controller remains the sole owner of shared state. Workers only
        # perform independent GETs; receipt/checkpoint mutations are serialized.
        state_lock = threading.Lock()
        reserved_keys: set[str] = set()

        def worker(source: SourceObject) -> str:
            nonlocal completed_bytes, new_objects
            receipt_path = _paired_tick_object_receipt_path(receipt_root, source)
            raw_path = raw_object_path(raw_root, source)
            with state_lock:
                if source.key in completed_by_key:
                    return "SKIP"
                if source.key in reserved_keys:
                    return "SKIP"
                if receipt_path.exists() or raw_path.exists() or raw_path.with_name(f"{raw_path.name}.part").exists():
                    raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_UNRECEIPTED_OR_CONFLICTING_LOCAL_OBJECT")
                reserved_keys.add(source.key)
                projection = _paired_tick_acquisition_projection(
                    cost_gate=cost_gate, completed_count=len(completed_by_key), completed_bytes=completed_bytes,
                )
                if before_get is not None:
                    # The callback may inspect the output tree. During parallel
                    # GETs, an expected .part file is owned by this controller
                    # and must not be mistaken for stale unreceipted output.
                    try:
                        before_get(source, projection, reserved_keys)
                    except TypeError as exc:
                        # Preserve the public two-argument callback contract for
                        # existing callers while allowing the PKT-045 controller
                        # to pass its in-flight ownership set.
                        if "positional" not in str(exc) and "argument" not in str(exc):
                            raise
                        before_get(source, projection)
            try:
                response = client.get_object(source.key, raw_path, output_root=output_root)
                response_metadata = _response_metadata(response)
                actual_size = raw_path.stat().st_size if raw_path.is_file() else None
                if actual_size != source.size or response_metadata.get("ContentLength") != source.size:
                    raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_SOURCE_OBJECT_CONFLICT")
                if source.etag is not None and response_metadata.get("ETag") != source.etag:
                    raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_SOURCE_OBJECT_CONFLICT")
                receipt = {
                    "schema": "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_RAW_OBJECT_RECEIPT_V1",
                    "STATUS": "COMPLETE", "SOURCE": _paired_tick_source_identity(source),
                    "GET_OBJECT_RESPONSE": response_metadata, "LOCAL_SHA256": _sha256_file(raw_path),
                    "ACQUISITION_TIMESTAMP_UTC": datetime.now(UTC).isoformat(),
                }
                with state_lock:
                    write_new_deterministic_json(receipt_path, receipt)
                    completed_by_key[source.key] = receipt
                    completed_bytes += source.size
                    new_objects += 1
                    _atomic_operational_json(checkpoint_path, {
                        "schema": "AIOS_PKT045_PAIRED_TICK_ACQUISITION_CHECKPOINT_V1",
                        "STATUS": "RUNNING", "LAST_COMPLETED_OBJECT_KEY": source.key,
                        "COMPLETED_OBJECTS": len(completed_by_key), "COMPLETED_BYTES": completed_bytes,
                        "GET_REQUESTS_THIS_RUN": client.request_counts["get"],
                        "CURRENT_CONCURRENCY": max_concurrent_gets,
                        "PROJECTION": _paired_tick_acquisition_projection(cost_gate=cost_gate, completed_count=len(completed_by_key), completed_bytes=completed_bytes),
                        "SAFE_RESUME_ACTION": "VALIDATE_RECEIPTS_THEN_CONTINUE_ONLY_UNRECEIPTED_INVENTORIED_KEYS",
                    })
                return "COMPLETE"
            except Exception as exc:
                error_text = str(exc)
                with state_lock:
                    retry_count = int(retry_state.get(source.key, 0) or 0)
                    if error_text.startswith(TEMPORARY_GET_ERROR_PREFIXES) and retry_count < 3:
                        retry_state[source.key] = retry_count + 1
                        _atomic_operational_json(retry_state_path, retry_state)
                        deferred_keys.add(source.key)
                        return "DEFERRED"
                    if error_text.startswith(TEMPORARY_GET_ERROR_PREFIXES):
                        exhausted_keys.add(source.key)
                        return "EXHAUSTED"
                raise

        candidates = [source for source in inventory.objects if source.key not in completed_by_key]
        if max_new_objects is not None:
            candidates = candidates[:max_new_objects]
        with ThreadPoolExecutor(max_workers=max_concurrent_gets, thread_name_prefix="pkt045-get") as pool:
            futures = [pool.submit(worker, source) for source in candidates]
            for future in as_completed(futures):
                future.result()
        return {
            "complete": len(completed_by_key) == cost_gate.total_objects,
            "completed_objects": len(completed_by_key), "total_objects": cost_gate.total_objects,
            "completed_bytes": completed_bytes, "new_objects": new_objects,
            "get_requests_this_run": client.request_counts["get"],
            "projection": _paired_tick_acquisition_projection(cost_gate=cost_gate, completed_count=len(completed_by_key), completed_bytes=completed_bytes),
            "deferred_objects": sorted(deferred_keys), "exhausted_objects": sorted(exhausted_keys),
            "max_concurrent_gets": max_concurrent_gets,
        }

    for position, source in enumerate(inventory.objects, 1):
        _paired_tick_source_identity(source)
        receipt_path = _paired_tick_object_receipt_path(receipt_root, source)
        raw_path = raw_object_path(raw_root, source)
        if source.key in completed_by_key:
            continue
        if receipt_path.exists() or raw_path.exists() or raw_path.with_name(f"{raw_path.name}.part").exists():
            raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_UNRECEIPTED_OR_CONFLICTING_LOCAL_OBJECT")
        projection = _paired_tick_acquisition_projection(
            cost_gate=cost_gate, completed_count=len(completed_by_key), completed_bytes=completed_bytes,
        )
        if not projection["WITHIN_HARD_LIMIT"]:
            raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_PROJECTED_COST_EXCEEDS_LIMIT")
        if max_new_objects is not None and new_objects >= max_new_objects:
            break
        if before_get is not None:
            before_get(source, projection)
        try:
            response = client.get_object(source.key, raw_path, output_root=output_root)
        except Exception as exc:
            error_text = str(exc)
            retry_count = int(retry_state.get(source.key, 0) or 0)
            temporary_failure = error_text.startswith(TEMPORARY_GET_ERROR_PREFIXES)
            if temporary_failure and retry_count < 3:
                retry_state[source.key] = retry_count + 1
                _atomic_operational_json(retry_state_path, retry_state)
                prior_partial = raw_path.with_name(f"{raw_path.name}.part")
                if prior_partial.exists():
                    recovery = output_root / "recovery" / f"{source.key.replace('/', '_')}.attempt{retry_count + 1}.part"
                    recovery.parent.mkdir(parents=True, exist_ok=True)
                    prior_partial.replace(recovery)
                deferred_keys.add(source.key)
                _atomic_operational_json(checkpoint_path, {
                    "schema": "AIOS_PKT045_PAIRED_TICK_ACQUISITION_CHECKPOINT_V1",
                    "STATUS": "DEFERRED_TEMPORARY_FAILURE",
                    "FAILED_OBJECT_KEY": source.key,
                    "COMPLETED_OBJECTS": len(completed_by_key),
                    "COMPLETED_BYTES": completed_bytes,
                    "GET_REQUESTS_THIS_RUN": client.request_counts["get"],
                    "PROJECTION": projection,
                    "ERROR": error_text,
                    "ATTEMPTS_USED": retry_count + 1,
                })
                continue
            elif temporary_failure:
                exhausted_keys.add(source.key)
                _atomic_operational_json(checkpoint_path, {
                    "schema": "AIOS_PKT045_TICK_ACQUISITION_CHECKPOINT_V1",
                    "STATUS": "EXHAUSTED_TEMPORARY_FAILURE",
                    "FAILED_OBJECT_KEY": source.key,
                    "COMPLETED_OBJECTS": len(completed_by_key),
                    "COMPLETED_BYTES": completed_bytes,
                    "GET_REQUESTS_THIS_RUN": client.request_counts["get"],
                    "PROJECTION": projection,
                    "ERROR": error_text,
                    "ATTEMPTS_USED": retry_count + 1,
                })
                continue
            else:
                _atomic_operational_json(checkpoint_path, {
                    "schema": "AIOS_PKT045_PAIRED_TICK_ACQUISITION_CHECKPOINT_V1",
                    "STATUS": "STOPPED_GET_FAILURE_NO_RETRY" if retry_count else "STOPPED_GET_FAILURE_UNCLASSIFIED",
                    "FAILED_OBJECT_KEY": source.key,
                    "COMPLETED_OBJECTS": len(completed_by_key),
                    "COMPLETED_BYTES": completed_bytes,
                    "GET_REQUESTS_THIS_RUN": client.request_counts["get"],
                    "PROJECTION": projection,
                    "ERROR": error_text,
                })
                raise
        response_metadata = _response_metadata(response)
        actual_size = raw_path.stat().st_size if raw_path.is_file() else None
        conflict = actual_size != source.size or response_metadata.get("ContentLength") != source.size
        if source.etag is not None and response_metadata.get("ETag") != source.etag:
            conflict = True
        if conflict:
            write_new_deterministic_json(receipt_path, {
                "schema": "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_RAW_OBJECT_CONFLICT_V1",
                "STATUS": "CONFLICT_NOT_CERTIFIED",
                "SOURCE": _paired_tick_source_identity(source),
                "GET_OBJECT_RESPONSE": response_metadata,
                "LOCAL_SIZE": actual_size,
                "LOCAL_SHA256": _sha256_file(raw_path) if raw_path.is_file() else None,
            })
            raise DukascopyAcquisitionError("PAIRED_TICK_ACQUISITION_SOURCE_OBJECT_CONFLICT")
        receipt = {
            "schema": "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_RAW_OBJECT_RECEIPT_V1",
            "STATUS": "COMPLETE",
            "SOURCE": _paired_tick_source_identity(source),
            "GET_OBJECT_RESPONSE": response_metadata,
            "LOCAL_SHA256": _sha256_file(raw_path),
            "ACQUISITION_TIMESTAMP_UTC": datetime.now(UTC).isoformat(),
        }
        write_new_deterministic_json(receipt_path, receipt)
        completed_by_key[source.key] = receipt
        completed_bytes += source.size
        new_objects += 1
        projection = _paired_tick_acquisition_projection(
            cost_gate=cost_gate, completed_count=len(completed_by_key), completed_bytes=completed_bytes,
        )
        _atomic_operational_json(checkpoint_path, {
            "schema": "AIOS_PKT045_PAIRED_TICK_ACQUISITION_CHECKPOINT_V1",
            "STATUS": "RUNNING" if len(completed_by_key) < cost_gate.total_objects else "RAW_ACQUISITION_COMPLETE",
            "LAST_COMPLETED_OBJECT_KEY": source.key,
            "LAST_COMPLETED_POSITION": position,
            "COMPLETED_OBJECTS": len(completed_by_key),
            "COMPLETED_BYTES": completed_bytes,
            "GET_REQUESTS_THIS_RUN": client.request_counts["get"],
            "PROJECTION": projection,
            "SAFE_RESUME_ACTION": "VALIDATE_RECEIPTS_THEN_CONTINUE_ONLY_UNRECEIPTED_INVENTORIED_KEYS",
        })
    final_projection = _paired_tick_acquisition_projection(
        cost_gate=cost_gate, completed_count=len(completed_by_key), completed_bytes=completed_bytes,
    )
    return {
        "complete": len(completed_by_key) == cost_gate.total_objects,
        "completed_objects": len(completed_by_key),
        "total_objects": cost_gate.total_objects,
        "completed_bytes": completed_bytes,
        "new_objects": new_objects,
        "get_requests_this_run": client.request_counts["get"],
        "projection": final_projection,
        "deferred_objects": sorted(deferred_keys),
        "exhausted_objects": sorted(exhausted_keys),
    }


def evaluate_paired_tick_preacquisition_gate(
    *,
    requirement: SourceSemanticsRequirement,
    mapped_pair_count: int,
    local_tick_proof_id: str,
    local_tick_proof_passed: bool,
) -> PairedTickPreacquisitionGate:
    """Check the local PAIRED_TICK contract without claiming 58-pair coverage.

    The existing ``evaluate_source_semantics`` remains the full gate used before
    a cost calculation or acquisition: it requires verified coverage.  This
    narrower gate exists so PKT-045 can be preregistered from saved local proof
    while staying explicitly blocked until a future authorised inventory.
    """
    if not local_tick_proof_id or not isinstance(local_tick_proof_passed, bool):
        raise DukascopyAcquisitionError("PAIRED_TICK_LOCAL_PROOF_ID_INVALID")
    if isinstance(mapped_pair_count, bool) or not isinstance(mapped_pair_count, int) or mapped_pair_count < 0:
        raise DukascopyAcquisitionError("PAIRED_TICK_MAPPED_PAIR_COUNT_INVALID")
    blockers: list[str] = []
    if requirement.midpoint_semantics != _MID_SEMANTICS_PAIRED_TICKS:
        blockers.append("PAIRED_TICK_MID_SEMANTICS_REQUIRED")
    if tuple(sorted(str(side).upper() for side in requirement.required_price_sides)) != ("ASK", "BID"):
        blockers.append("PAIRED_TICK_BID_ASK_REQUIRED")
    if str(requirement.timestamp_granularity).upper() != "TICK":
        blockers.append("PAIRED_TICK_TIMESTAMP_REQUIRED")
    if str(requirement.candle_construction).upper() != "PAIRED_TICKS_THEN_M5":
        blockers.append("PAIRED_TICK_M5_CONSTRUCTION_REQUIRED")
    if requirement.preregistration_status not in _ACQUISITION_READY_PREREGISTRATIONS:
        blockers.append("PAIRED_TICK_PREREGISTRATION_NOT_FROZEN")
    if mapped_pair_count != requirement.required_pair_count:
        blockers.append("PAIR_MAPPING_INCOMPLETE")
    if not local_tick_proof_passed:
        blockers.append("LOCAL_PAIRED_TICK_PROOF_FAILED")
    ordered = tuple(sorted(set(blockers)))
    return PairedTickPreacquisitionGate(
        strategy_specification_id=requirement.strategy_specification_id,
        source_id="DUKASCOPY_PAIRED_TICK",
        local_tick_proof_id=local_tick_proof_id,
        semantic_contract_status="PASS" if not ordered else "FAIL",
        full_coverage_status="UNVERIFIED_REQUIRES_EXACT_TICK_INVENTORY",
        acquisition_status=(
            "BLOCKED_AWAITING_EXACT_TICK_INVENTORY_CURRENT_PRICING_COST_GATE_AND_OWNER_AUTHORITY"
            if not ordered else "BLOCKED"
        ),
        blockers=ordered,
        required_pair_count=requirement.required_pair_count,
        mapped_pair_count=mapped_pair_count,
    )


def paired_tick_preacquisition_gate_payload(
    gate: PairedTickPreacquisitionGate,
    *,
    requirement: SourceSemanticsRequirement,
) -> dict[str, Any]:
    return {
        "schema": "AIOS_PKT045_PAIRED_TICK_PREACQUISITION_SEMANTICS_GATE_V1",
        "REQUIREMENT": asdict(requirement),
        "RESULT": asdict(gate),
        "COST_GATE_STATUS": "NOT_RUN_REQUIRES_FULL_SOURCE_SEMANTICS_PASS",
        "AWS_REQUESTS": 0,
    }


def build_cost_gate(
    *,
    inventory: Inventory,
    semantics_gate: SourceSemanticsGate,
    total_list_requests_planned: int,
    total_get_requests_planned: int,
    total_head_requests_planned: int,
    prior_cost_usd: float,
    pricing: CostBasis,
    safety_margin_usd: float,
    owner_limit_usd: float = 1.0,
    other_cost_usd: float = 0.0,
) -> CostGate:
    """Calculate a conservative gate without assuming a free transfer allowance."""
    if semantics_gate.semantic_fit != "PASS" or semantics_gate.acquisition_status != "ELIGIBLE":
        raise DukascopyAcquisitionError("COST_GATE_SOURCE_SEMANTICS_NOT_ELIGIBLE")
    numeric = (
        prior_cost_usd, pricing.list_per_1000_usd, pricing.get_per_1000_usd,
        pricing.head_per_1000_usd, pricing.transfer_per_gb_usd, safety_margin_usd,
        owner_limit_usd, other_cost_usd,
    )
    if any(not isinstance(value, (int, float)) or value < 0 for value in numeric):
        raise DukascopyAcquisitionError("COST_BASIS_INVALID")
    list_cost = total_list_requests_planned / 1_000 * pricing.list_per_1000_usd
    get_cost = total_get_requests_planned / 1_000 * pricing.get_per_1000_usd
    head_cost = total_head_requests_planned / 1_000 * pricing.head_per_1000_usd
    # AWS advertises data-transfer units in decimal GB.  No free allowance is
    # assumed by this hard gate, even if one may later prove applicable.
    transfer_cost = inventory.total_listed_bytes / 1_000_000_000 * pricing.transfer_per_gb_usd
    remaining = list_cost + get_cost + head_cost + transfer_cost + other_cost_usd + safety_margin_usd
    total = prior_cost_usd + remaining
    return CostGate(
        total_objects=inventory.total_object_count,
        total_list_requests_planned=total_list_requests_planned,
        total_get_requests_planned=total_get_requests_planned,
        total_head_requests_planned=total_head_requests_planned,
        exact_listed_object_bytes=inventory.total_listed_bytes,
        conservative_download_bytes=inventory.total_listed_bytes,
        prior_cost_usd=prior_cost_usd, list_cost_usd=list_cost, get_cost_usd=get_cost,
        head_cost_usd=head_cost, transfer_cost_usd=transfer_cost, other_cost_usd=other_cost_usd,
        safety_margin_usd=safety_margin_usd, conservative_remaining_cost_usd=remaining,
        conservative_total_job_cost_usd=total, owner_limit_usd=owner_limit_usd,
        source_semantics_requirement_id=semantics_gate.strategy_specification_id,
        source_semantic_fit=semantics_gate.semantic_fit,
        source_acquisition_status=semantics_gate.acquisition_status,
        cost_gate="PASS" if total <= owner_limit_usd else "FAIL",
    )


def cost_gate_payload(cost_gate: CostGate, pricing: CostBasis) -> dict[str, Any]:
    payload = asdict(cost_gate)
    payload.update({
        "schema": "AIOS_PKT044_DUKASCOPY_COST_GATE_V1",
        "AWS_PRICE_SOURCE": pricing.price_source,
        "SOURCE_RETRIEVED_AT": pricing.retrieved_at_utc,
        "FREE_ALLOWANCE_ASSUMPTION": pricing.free_allowance_assumption,
        "LIST_PRICE_AND_UNIT": f"{pricing.list_per_1000_usd} USD per 1,000 requests",
        "GET_PRICE_AND_UNIT": f"{pricing.get_per_1000_usd} USD per 1,000 requests",
        "HEAD_PRICE_AND_UNIT": f"{pricing.head_per_1000_usd} USD per 1,000 requests",
        "DATA_TRANSFER_PRICE_AND_UNIT": f"{pricing.transfer_per_gb_usd} USD per GB",
    })
    return payload
