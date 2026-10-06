"""Fail-closed readers for Dukascopy daily candle and tick BI5 objects.

This module deliberately has no network or strategy code.  It accepts a source
object only when the caller supplies its exact key, side where applicable, UTC
date, and price scale.  Daily minute-candle records are evidence-backed by the
saved PKT-044 BID/ASK probes.  Daily tick records use Dukascopy's documented
20-byte, big-endian layout.  The acquisition/certification layer must still
record the source-schema evidence before it permits a corpus to be used for
research.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import lzma
import math
import re
import struct
from typing import Iterable, Sequence


UTC = timezone.utc
RECORD = struct.Struct(">5If")
RECORD_BYTES = RECORD.size
TICK_RECORD = struct.Struct(">IIIff")
TICK_RECORD_BYTES = TICK_RECORD.size
SUPPORTED_PRICE_SCALES = frozenset({100, 1_000, 10_000, 100_000, 1_000_000})
# A daily tick object is decoded into Python objects before M5 aggregation.
# Keep the decompressed payload far below the Stage 1 four-GiB process ceiling;
# a larger object is a recoverable source/resource block, never a reason to
# stream an unbounded payload or silently drop ticks.
MAX_DECOMPRESSED_BI5_BYTES = 128 * 1024 * 1024
_OBJECT_KEY = re.compile(
    r"^(?P<symbol>[A-Z]{6})/(?P<year>20\d{2})/(?P<month>\d{2})/(?P<day>\d{2})/"
    r"(?P<side>BID|ASK)_candles_min_1\.bi5$"
)
_TICK_OBJECT_KEY = re.compile(
    r"^(?P<symbol>[A-Z]{6})/(?P<year>20\d{2})/(?P<month>\d{2})/(?P<day>\d{2})_ticks\.bi5$"
)


class DukascopyBi5Error(ValueError):
    """A source object is malformed, inconsistent, or outside its contract."""


@dataclass(frozen=True)
class MinuteCandle:
    pair: str
    side: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    activity: float
    source_key: str
    source_offset_seconds: int


@dataclass(frozen=True)
class Tick:
    """One source-native daily tick with both executable sides preserved."""

    pair: str
    timestamp: datetime
    ask: float
    bid: float
    ask_volume: float
    bid_volume: float
    source_key: str
    source_offset_milliseconds: int
    source_sequence: int


@dataclass(frozen=True)
class M5Candle:
    pair: str
    timestamp: datetime
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    ask_open: float
    ask_high: float
    ask_low: float
    ask_close: float
    bid_source_record_count: int
    ask_source_record_count: int
    source_keys: tuple[str, ...]
    completed: bool


@dataclass(frozen=True)
class M5Normalization:
    bars: tuple[M5Candle, ...]
    incomplete_buckets: tuple[datetime, ...]


@dataclass(frozen=True)
class DerivedMidM5Candle:
    """One M5 bar whose midpoint was formed from each paired source tick.

    This is deliberately distinct from a provider-native midpoint candle.  It
    is suitable only for a separately identified specification that explicitly
    permits ``(bid_t + ask_t) / 2`` before M5 aggregation.  It must never be
    substituted for a source-native MID candle or built from BID/ASK candle
    extrema.
    """

    pair: str
    timestamp: datetime
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    ask_open: float
    ask_high: float
    ask_low: float
    ask_close: float
    mid_open: float
    mid_high: float
    mid_low: float
    mid_close: float
    source_record_count: int
    source_keys: tuple[str, ...]
    completed: bool
    midpoint_method: str


@dataclass(frozen=True)
class DerivedMidM5Normalization:
    bars: tuple[DerivedMidM5Candle, ...]
    incomplete_buckets: tuple[datetime, ...]


def source_symbol(pair: str) -> str:
    """Map the controlled AIOS spelling ``AAA_BBB`` to a source symbol."""
    candidate = str(pair).upper()
    if re.fullmatch(r"[A-Z]{3}_[A-Z]{3}", candidate):
        return candidate.replace("_", "")
    if re.fullmatch(r"[A-Z]{6}", candidate):
        return candidate
    raise DukascopyBi5Error("BI5_PAIR_IDENTIFIER_INVALID")


def canonical_pair(pair: str) -> str:
    symbol = source_symbol(pair)
    return f"{symbol[:3]}_{symbol[3:]}"


def daily_candle_key(pair: str, trading_day: date, side: str) -> str:
    """Return the documented zero-based-month daily candle object key."""
    normalized_side = str(side).upper()
    if normalized_side not in {"BID", "ASK"}:
        raise DukascopyBi5Error("BI5_SIDE_INVALID")
    return (
        f"{source_symbol(pair)}/{trading_day.year:04d}/{trading_day.month - 1:02d}/"
        f"{trading_day.day:02d}/{normalized_side}_candles_min_1.bi5"
    )


def parse_daily_candle_key(source_key: str) -> tuple[str, date, str]:
    """Parse and validate the exact supported source-object layout."""
    match = _OBJECT_KEY.fullmatch(str(source_key))
    if not match:
        raise DukascopyBi5Error("BI5_OBJECT_KEY_LAYOUT_INVALID")
    zero_month = int(match.group("month"))
    if zero_month > 11:
        raise DukascopyBi5Error("BI5_OBJECT_KEY_MONTH_INVALID")
    try:
        trading_day = date(int(match.group("year")), zero_month + 1, int(match.group("day")))
    except ValueError as exc:
        raise DukascopyBi5Error("BI5_OBJECT_KEY_DATE_INVALID") from exc
    return canonical_pair(match.group("symbol")), trading_day, match.group("side")


def daily_tick_key(pair: str, trading_day: date) -> str:
    """Return the documented zero-based-month daily tick object key."""
    return (
        f"{source_symbol(pair)}/{trading_day.year:04d}/{trading_day.month - 1:02d}/"
        f"{trading_day.day:02d}_ticks.bi5"
    )


def parse_daily_tick_key(source_key: str) -> tuple[str, date]:
    """Parse and validate the exact supported daily tick object layout."""
    match = _TICK_OBJECT_KEY.fullmatch(str(source_key))
    if not match:
        raise DukascopyBi5Error("BI5_TICK_OBJECT_KEY_LAYOUT_INVALID")
    zero_month = int(match.group("month"))
    if zero_month > 11:
        raise DukascopyBi5Error("BI5_TICK_OBJECT_KEY_MONTH_INVALID")
    try:
        trading_day = date(int(match.group("year")), zero_month + 1, int(match.group("day")))
    except ValueError as exc:
        raise DukascopyBi5Error("BI5_TICK_OBJECT_KEY_DATE_INVALID") from exc
    return canonical_pair(match.group("symbol")), trading_day


def _validate_scale(price_scale: int) -> int:
    if isinstance(price_scale, bool) or not isinstance(price_scale, int):
        raise DukascopyBi5Error("BI5_PRICE_SCALE_INVALID")
    if price_scale not in SUPPORTED_PRICE_SCALES:
        raise DukascopyBi5Error("BI5_PRICE_SCALE_UNSUPPORTED")
    return price_scale


def _validate_allowed_interval(
    stamp: datetime,
    permitted_start: datetime | None,
    permitted_end: datetime | None,
) -> None:
    if permitted_start is not None:
        if permitted_start.tzinfo is None:
            raise DukascopyBi5Error("BI5_ALLOWED_START_TIMEZONE_MISSING")
        permitted_start = permitted_start.astimezone(UTC)
        if stamp < permitted_start:
            raise DukascopyBi5Error("BI5_TIMESTAMP_OUTSIDE_ALLOWED_RANGE")
    if permitted_end is not None:
        if permitted_end.tzinfo is None:
            raise DukascopyBi5Error("BI5_ALLOWED_END_TIMEZONE_MISSING")
        permitted_end = permitted_end.astimezone(UTC)
        if stamp >= permitted_end:
            raise DukascopyBi5Error("BI5_TIMESTAMP_OUTSIDE_ALLOWED_RANGE")


def _decompress_lzma_alone(payload: bytes, *, max_output_bytes: int = MAX_DECOMPRESSED_BI5_BYTES) -> bytes:
    """Decompress one BI5 stream with a fixed per-object memory ceiling."""
    if not isinstance(payload, bytes) or not payload:
        raise DukascopyBi5Error("BI5_PAYLOAD_EMPTY")
    if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or max_output_bytes <= 0:
        raise DukascopyBi5Error("BI5_DECOMPRESSION_LIMIT_INVALID")
    try:
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        raw_parts: list[bytes] = []
        raw_size = 0
        supplied = payload
        while not decoder.eof:
            chunk = decoder.decompress(supplied, max_length=min(1_048_576, max_output_bytes - raw_size + 1))
            supplied = b""
            raw_size += len(chunk)
            if raw_size > max_output_bytes:
                raise DukascopyBi5Error("BI5_DECOMPRESSED_SIZE_LIMIT_EXCEEDED")
            if chunk:
                raw_parts.append(chunk)
            if decoder.needs_input and not decoder.eof:
                raise DukascopyBi5Error("BI5_LZMA_DECOMPRESSION_FAILED")
        if decoder.unused_data:
            raise DukascopyBi5Error("BI5_LZMA_TRAILING_DATA_INVALID")
        raw = b"".join(raw_parts)
    except lzma.LZMAError as exc:
        raise DukascopyBi5Error("BI5_LZMA_DECOMPRESSION_FAILED") from exc
    if not raw:
        raise DukascopyBi5Error("BI5_DECOMPRESSED_PAYLOAD_EMPTY")
    return raw


def decode_minute_candle_bi5(
    payload: bytes,
    *,
    pair: str,
    side: str,
    trading_day: date,
    source_key: str,
    price_scale: int,
    permitted_start: datetime | None = None,
    permitted_end: datetime | None = None,
    max_decompressed_bytes: int = MAX_DECOMPRESSED_BI5_BYTES,
) -> tuple[MinuteCandle, ...]:
    """Decode one daily BI5 candle object without fabricating any observation.

    The stored order is ``offset_seconds, open, close, low, high, activity``.
    The output names fields in normal OHLC order.  A caller must provide the
    price scale; this function never infers it from a price or a pair name.
    """
    expected_pair = canonical_pair(pair)
    expected_side = str(side).upper()
    if expected_side not in {"BID", "ASK"}:
        raise DukascopyBi5Error("BI5_SIDE_INVALID")
    key_pair, key_day, key_side = parse_daily_candle_key(source_key)
    if key_pair != expected_pair or key_day != trading_day or key_side != expected_side:
        raise DukascopyBi5Error("BI5_SOURCE_IDENTITY_MISMATCH")
    scale = _validate_scale(price_scale)
    raw = _decompress_lzma_alone(payload, max_output_bytes=max_decompressed_bytes)
    if len(raw) % RECORD_BYTES:
        raise DukascopyBi5Error("BI5_RECORD_BOUNDARY_INVALID")

    start = datetime.combine(trading_day, time.min, tzinfo=UTC)
    output: list[MinuteCandle] = []
    previous_offset = -1
    for index in range(0, len(raw), RECORD_BYTES):
        offset, raw_open, raw_close, raw_low, raw_high, activity = RECORD.unpack_from(raw, index)
        if offset >= 86_400 or offset % 60:
            raise DukascopyBi5Error("BI5_MINUTE_OFFSET_INVALID")
        if offset <= previous_offset:
            raise DukascopyBi5Error("BI5_TIMESTAMP_NON_MONOTONIC_OR_DUPLICATE")
        previous_offset = offset
        if not all(value > 0 for value in (raw_open, raw_close, raw_low, raw_high)):
            raise DukascopyBi5Error("BI5_EXECUTABLE_PRICE_NONPOSITIVE")
        if raw_low > min(raw_open, raw_close) or raw_high < max(raw_open, raw_close):
            raise DukascopyBi5Error("BI5_OHLC_INVARIANT_INVALID")
        if not math.isfinite(activity) or activity < 0:
            raise DukascopyBi5Error("BI5_ACTIVITY_INVALID")
        stamp = start + timedelta(seconds=offset)
        _validate_allowed_interval(stamp, permitted_start, permitted_end)
        values = tuple(raw_value / scale for raw_value in (raw_open, raw_high, raw_low, raw_close))
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise DukascopyBi5Error("BI5_EXECUTABLE_PRICE_INVALID")
        output.append(
            MinuteCandle(
                pair=expected_pair,
                side=expected_side,
                timestamp=stamp,
                open=values[0],
                high=values[1],
                low=values[2],
                close=values[3],
                activity=float(activity),
                source_key=source_key,
                source_offset_seconds=offset,
            )
        )
    return tuple(output)


def decode_tick_bi5(
    payload: bytes,
    *,
    pair: str,
    trading_day: date,
    source_key: str,
    price_scale: int,
    permitted_start: datetime | None = None,
    permitted_end: datetime | None = None,
    max_decompressed_bytes: int = MAX_DECOMPRESSED_BI5_BYTES,
) -> tuple[Tick, ...]:
    """Decode a documented daily tick BI5 object without substituting quotes.

    Dukascopy's daily tick object carries ``milliseconds, ask, bid, ask volume,
    bid volume`` in a fixed 20-byte big-endian record.  Equal timestamps are
    allowed because source ticks can share a millisecond; their source order is
    retained through ``source_sequence``.  A timestamp moving backwards is not.
    """
    expected_pair = canonical_pair(pair)
    key_pair, key_day = parse_daily_tick_key(source_key)
    if key_pair != expected_pair or key_day != trading_day:
        raise DukascopyBi5Error("BI5_TICK_SOURCE_IDENTITY_MISMATCH")
    scale = _validate_scale(price_scale)
    raw = _decompress_lzma_alone(payload, max_output_bytes=max_decompressed_bytes)
    if len(raw) % TICK_RECORD_BYTES:
        raise DukascopyBi5Error("BI5_TICK_RECORD_BOUNDARY_INVALID")

    start = datetime.combine(trading_day, time.min, tzinfo=UTC)
    output: list[Tick] = []
    previous_offset = -1
    for sequence, index in enumerate(range(0, len(raw), TICK_RECORD_BYTES)):
        offset, raw_ask, raw_bid, ask_volume, bid_volume = TICK_RECORD.unpack_from(raw, index)
        if offset >= 86_400_000:
            raise DukascopyBi5Error("BI5_TICK_OFFSET_INVALID")
        if offset < previous_offset:
            raise DukascopyBi5Error("BI5_TICK_TIMESTAMP_NON_MONOTONIC")
        previous_offset = offset
        if raw_ask <= 0 or raw_bid <= 0:
            raise DukascopyBi5Error("BI5_TICK_EXECUTABLE_PRICE_NONPOSITIVE")
        if raw_ask < raw_bid:
            raise DukascopyBi5Error("BI5_TICK_BID_ASK_RELATION_INVALID")
        if not all(math.isfinite(value) and value >= 0 for value in (ask_volume, bid_volume)):
            raise DukascopyBi5Error("BI5_TICK_VOLUME_INVALID")
        stamp = start + timedelta(milliseconds=offset)
        _validate_allowed_interval(stamp, permitted_start, permitted_end)
        ask = raw_ask / scale
        bid = raw_bid / scale
        if not all(math.isfinite(value) and value > 0 for value in (ask, bid)):
            raise DukascopyBi5Error("BI5_TICK_EXECUTABLE_PRICE_INVALID")
        output.append(
            Tick(
                pair=expected_pair,
                timestamp=stamp,
                ask=ask,
                bid=bid,
                ask_volume=float(ask_volume),
                bid_volume=float(bid_volume),
                source_key=source_key,
                source_offset_milliseconds=offset,
                source_sequence=sequence,
            )
        )
    return tuple(output)


def _bucket_start(stamp: datetime) -> datetime:
    if stamp.tzinfo is None:
        raise DukascopyBi5Error("BI5_TIMESTAMP_TIMEZONE_MISSING")
    stamp = stamp.astimezone(UTC)
    return stamp.replace(minute=stamp.minute - stamp.minute % 5, second=0, microsecond=0)


def _side_map(records: Iterable[MinuteCandle], expected_side: str) -> tuple[str | None, dict[datetime, MinuteCandle]]:
    pair: str | None = None
    result: dict[datetime, MinuteCandle] = {}
    for record in records:
        if record.side != expected_side:
            raise DukascopyBi5Error("BI5_SIDE_IDENTITY_MISMATCH")
        if record.timestamp.tzinfo is None or record.timestamp.second or record.timestamp.microsecond:
            raise DukascopyBi5Error("BI5_SOURCE_TIMESTAMP_INVALID")
        if pair is None:
            pair = record.pair
        elif pair != record.pair:
            raise DukascopyBi5Error("BI5_MULTI_PAIR_NORMALIZATION_INPUT")
        if record.timestamp in result:
            raise DukascopyBi5Error("BI5_SOURCE_TIMESTAMP_NONUNIQUE")
        result[record.timestamp] = record
    return pair, result


def normalize_minute_candles_to_m5(
    bid_records: Sequence[MinuteCandle], ask_records: Sequence[MinuteCandle]
) -> M5Normalization:
    """Build complete UTC M5 candles only from genuine minute observations.

    A five-minute bucket is emitted only when every minute is present for both
    executable sides.  Missing source minutes remain an explicit incomplete
    bucket; no side, midpoint, prior close, or future price is substituted.
    """
    bid_pair, bid = _side_map(bid_records, "BID")
    ask_pair, ask = _side_map(ask_records, "ASK")
    if bid_pair is None and ask_pair is None:
        return M5Normalization(bars=(), incomplete_buckets=())
    if bid_pair is None or ask_pair is None or bid_pair != ask_pair:
        raise DukascopyBi5Error("BI5_BID_ASK_PAIR_MISMATCH")
    buckets = sorted({_bucket_start(stamp) for stamp in set(bid) | set(ask)})
    bars: list[M5Candle] = []
    incomplete: list[datetime] = []
    for bucket in buckets:
        stamps = tuple(bucket + timedelta(minutes=minute) for minute in range(5))
        bid_rows = tuple(bid.get(stamp) for stamp in stamps)
        ask_rows = tuple(ask.get(stamp) for stamp in stamps)
        if any(row is None for row in bid_rows) or any(row is None for row in ask_rows):
            incomplete.append(bucket)
            continue
        bid_complete = tuple(row for row in bid_rows if row is not None)
        ask_complete = tuple(row for row in ask_rows if row is not None)
        bars.append(
            M5Candle(
                pair=bid_pair,
                timestamp=bucket,
                bid_open=bid_complete[0].open,
                bid_high=max(row.high for row in bid_complete),
                bid_low=min(row.low for row in bid_complete),
                bid_close=bid_complete[-1].close,
                ask_open=ask_complete[0].open,
                ask_high=max(row.high for row in ask_complete),
                ask_low=min(row.low for row in ask_complete),
                ask_close=ask_complete[-1].close,
                bid_source_record_count=len(bid_complete),
                ask_source_record_count=len(ask_complete),
                source_keys=tuple(sorted({row.source_key for row in (*bid_complete, *ask_complete)})),
                completed=True,
            )
        )
    return M5Normalization(bars=tuple(bars), incomplete_buckets=tuple(incomplete))


def normalize_ticks_to_m5(ticks: Sequence[Tick]) -> M5Normalization:
    """Build M5 BID/ASK candles from actual ticks inside each UTC interval.

    A bucket without a tick is absent from the result.  This function never
    inserts a theoretical clock candle, carries a prior quote forward, or uses
    a later tick.  Availability certification decides whether an absent bucket
    matters to the frozen strategy's executable path.
    """
    if not ticks:
        return M5Normalization(bars=(), incomplete_buckets=())
    pair: str | None = None
    previous_stamp: datetime | None = None
    seen_source_rows: set[tuple[str, int]] = set()
    buckets: dict[datetime, list[Tick]] = {}
    for tick in ticks:
        if tick.timestamp.tzinfo is None:
            raise DukascopyBi5Error("BI5_TICK_TIMESTAMP_TIMEZONE_MISSING")
        stamp = tick.timestamp.astimezone(UTC)
        if pair is None:
            pair = tick.pair
        elif pair != tick.pair:
            raise DukascopyBi5Error("BI5_TICK_MULTI_PAIR_NORMALIZATION_INPUT")
        if previous_stamp is not None and stamp < previous_stamp:
            raise DukascopyBi5Error("BI5_TICK_NORMALIZATION_INPUT_NON_MONOTONIC")
        previous_stamp = stamp
        row_identity = (tick.source_key, tick.source_sequence)
        if row_identity in seen_source_rows:
            raise DukascopyBi5Error("BI5_TICK_SOURCE_ROW_DUPLICATE")
        seen_source_rows.add(row_identity)
        if not all(math.isfinite(value) and value > 0 for value in (tick.ask, tick.bid)):
            raise DukascopyBi5Error("BI5_TICK_NORMALIZATION_PRICE_INVALID")
        if tick.ask < tick.bid:
            raise DukascopyBi5Error("BI5_TICK_NORMALIZATION_BID_ASK_RELATION_INVALID")
        buckets.setdefault(_bucket_start(stamp), []).append(tick)

    bars: list[M5Candle] = []
    for bucket in sorted(buckets):
        rows = buckets[bucket]
        bars.append(
            M5Candle(
                pair=pair or "",
                timestamp=bucket,
                bid_open=rows[0].bid,
                bid_high=max(row.bid for row in rows),
                bid_low=min(row.bid for row in rows),
                bid_close=rows[-1].bid,
                ask_open=rows[0].ask,
                ask_high=max(row.ask for row in rows),
                ask_low=min(row.ask for row in rows),
                ask_close=rows[-1].ask,
                bid_source_record_count=len(rows),
                ask_source_record_count=len(rows),
                source_keys=tuple(sorted({row.source_key for row in rows})),
                completed=True,
            )
        )
    return M5Normalization(bars=tuple(bars), incomplete_buckets=())


def normalize_paired_ticks_to_m5_with_derived_mid(ticks: Sequence[Tick]) -> DerivedMidM5Normalization:
    """Aggregate same-record BID/ASK ticks into BID, ASK, and derived MID M5 bars.

    The method computes a midpoint for every paired source tick and then forms
    OHLC within that completed UTC five-minute bucket.  It intentionally does
    not average side-candle highs or lows, carry a quote forward, or create a
    theoretical empty bucket.  The resulting MID is a new, explicit data
    semantic and is not evidence that it matches a provider-native MID stream.
    """
    bid_ask = normalize_ticks_to_m5(ticks)
    if not bid_ask.bars:
        return DerivedMidM5Normalization(bars=(), incomplete_buckets=())

    rows_by_bucket: dict[datetime, list[Tick]] = {}
    for tick in ticks:
        stamp = tick.timestamp.astimezone(UTC)
        rows_by_bucket.setdefault(_bucket_start(stamp), []).append(tick)

    bars: list[DerivedMidM5Candle] = []
    for bar in bid_ask.bars:
        rows = rows_by_bucket.get(bar.timestamp)
        if not rows:
            raise DukascopyBi5Error("BI5_TICK_MID_BUCKET_MISSING")
        # This numerically stable form is exactly (bid + ask) / 2 for finite
        # prices while avoiding an unnecessary intermediate overflow.
        mids = tuple(row.bid + (row.ask - row.bid) / 2.0 for row in rows)
        if not all(math.isfinite(value) and value > 0 for value in mids):
            raise DukascopyBi5Error("BI5_TICK_MIDPOINT_INVALID")
        bars.append(
            DerivedMidM5Candle(
                pair=bar.pair,
                timestamp=bar.timestamp,
                bid_open=bar.bid_open,
                bid_high=bar.bid_high,
                bid_low=bar.bid_low,
                bid_close=bar.bid_close,
                ask_open=bar.ask_open,
                ask_high=bar.ask_high,
                ask_low=bar.ask_low,
                ask_close=bar.ask_close,
                mid_open=mids[0],
                mid_high=max(mids),
                mid_low=min(mids),
                mid_close=mids[-1],
                source_record_count=len(rows),
                source_keys=bar.source_keys,
                completed=True,
                midpoint_method="PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION",
            )
        )
    return DerivedMidM5Normalization(bars=tuple(bars), incomplete_buckets=())
