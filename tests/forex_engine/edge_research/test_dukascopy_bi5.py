"""PKT-044 BI5 decoder tests: synthetic failures plus saved real source probes."""

from datetime import date, datetime, timedelta, timezone
import lzma
from pathlib import Path
import struct

import pytest

from automation.forex_engine.edge_research.dukascopy_bi5 import (
    DukascopyBi5Error,
    MinuteCandle,
    Tick,
    daily_candle_key,
    daily_tick_key,
    decode_minute_candle_bi5,
    decode_tick_bi5,
    normalize_minute_candles_to_m5,
    normalize_paired_ticks_to_m5_with_derived_mid,
    normalize_ticks_to_m5,
    parse_daily_candle_key,
    parse_daily_tick_key,
)


UTC = timezone.utc
RECORD = struct.Struct(">5If")
TICK_RECORD = struct.Struct(">IIIff")
REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE_ROOT = REPO_ROOT / ".aios/staging/PKT_FOREX_044/dukascopy_probe_corrected_occ82_20260907"
TICK_PROBE_ROOT = REPO_ROOT / ".aios/staging/PKT_FOREX_044/dukascopy_tick_probe_occ82_20260907"
EQUIVALENCE_PROBE_ROOT = REPO_ROOT / ".aios/staging/PKT_FOREX_044/dukascopy_tick_minute_equivalence_probe_occ82_20260907"


def compressed(*records):
    raw = b"".join(RECORD.pack(*record) for record in records)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


def compressed_ticks(*records):
    raw = b"".join(TICK_RECORD.pack(*record) for record in records)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


def decode(payload, *, pair="EUR_USD", side="BID", day=date(2024, 1, 2), scale=100_000, **kwargs):
    return decode_minute_candle_bi5(
        payload,
        pair=pair,
        side=side,
        trading_day=day,
        source_key=daily_candle_key(pair, day, side),
        price_scale=scale,
        **kwargs,
    )


def decode_ticks(payload, *, pair="EUR_USD", day=date(2024, 1, 2), scale=100_000, **kwargs):
    return decode_tick_bi5(
        payload,
        pair=pair,
        trading_day=day,
        source_key=daily_tick_key(pair, day),
        price_scale=scale,
        **kwargs,
    )


def test_object_key_uses_zero_based_month_and_round_trips():
    key = daily_candle_key("AUD_CAD", date(2024, 9, 2), "ask")
    assert key == "AUDCAD/2024/08/02/ASK_candles_min_1.bi5"
    assert parse_daily_candle_key(key) == ("AUD_CAD", date(2024, 9, 2), "ASK")
    with pytest.raises(DukascopyBi5Error, match="MONTH_INVALID"):
        parse_daily_candle_key("AUDCAD/2024/12/02/ASK_candles_min_1.bi5")


def test_tick_key_uses_zero_based_month_and_round_trips():
    key = daily_tick_key("AUD_CAD", date(2024, 9, 2))
    assert key == "AUDCAD/2024/08/02_ticks.bi5"
    assert parse_daily_tick_key(key) == ("AUD_CAD", date(2024, 9, 2))
    with pytest.raises(DukascopyBi5Error, match="MONTH_INVALID"):
        parse_daily_tick_key("AUDCAD/2024/12/02_ticks.bi5")


@pytest.mark.parametrize(
    "probe_root,filename,pair,side,day,first_open",
    [
        ("dukascopy_probe_corrected_occ82_20260907", "AUDCAD_2024_08_02_BID_candles_min_1.bi5", "AUD_CAD", "BID", date(2024, 9, 2), 0.91298),
        ("dukascopy_probe_corrected_occ82_20260907", "AUDCAD_2024_08_02_ASK_candles_min_1.bi5", "AUD_CAD", "ASK", date(2024, 9, 2), 0.91318),
        ("dukascopy_probe_corrected_occ82_20260907", "CADHKD_2024_04_20_BID_candles_min_1.bi5", "CAD_HKD", "BID", date(2024, 5, 20), 5.73292),
        ("dukascopy_probe_corrected_occ82_20260907", "CADHKD_2024_04_20_ASK_candles_min_1.bi5", "CAD_HKD", "ASK", date(2024, 5, 20), 5.73388),
        ("dukascopy_probe_occ82_20260907", "EURUSD_2024_01_02_BID_candles_min_1.bi5", "EUR_USD", "BID", date(2024, 2, 2), 1.08741),
    ],
)
def test_saved_real_probe_decodes_deterministically(probe_root, filename, pair, side, day, first_open):
    path = PROBE_ROOT.parent / probe_root / filename
    assert path.is_file(), f"SAVED_PROBE_MISSING:{path}"
    source_key = daily_candle_key(pair, day, side)
    first = decode_minute_candle_bi5(
        path.read_bytes(), pair=pair, side=side, trading_day=day, source_key=source_key, price_scale=100_000
    )
    second = decode_minute_candle_bi5(
        path.read_bytes(), pair=pair, side=side, trading_day=day, source_key=source_key, price_scale=100_000
    )
    assert first == second
    assert len(first) == 1_440
    assert first[0].timestamp == datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    assert first[-1].timestamp == datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=23, minutes=59)
    assert first[0].open == pytest.approx(first_open)
    assert [row.timestamp for row in first] == sorted(row.timestamp for row in first)
    assert all(row.side == side and row.pair == pair for row in first)


def test_real_probe_bid_and_ask_stay_distinct():
    day = date(2024, 9, 2)
    bid = decode_minute_candle_bi5(
        (PROBE_ROOT / "AUDCAD_2024_08_02_BID_candles_min_1.bi5").read_bytes(),
        pair="AUD_CAD", side="BID", trading_day=day,
        source_key=daily_candle_key("AUD_CAD", day, "BID"), price_scale=100_000,
    )
    ask = decode_minute_candle_bi5(
        (PROBE_ROOT / "AUDCAD_2024_08_02_ASK_candles_min_1.bi5").read_bytes(),
        pair="AUD_CAD", side="ASK", trading_day=day,
        source_key=daily_candle_key("AUD_CAD", day, "ASK"), price_scale=100_000,
    )
    assert bid[0].close < ask[0].close
    result = normalize_minute_candles_to_m5(bid, ask)
    assert len(result.bars) == 288
    assert not result.incomplete_buckets
    assert result.bars[0].timestamp == datetime(2024, 9, 2, tzinfo=UTC)
    assert result.bars[0].bid_source_record_count == 5
    assert result.bars[0].ask_source_record_count == 5


def test_saved_real_tick_probe_decodes_and_normalizes_deterministically():
    day = date(2024, 1, 2)
    path = TICK_PROBE_ROOT / "AUDCAD_2024_00_02_ticks.bi5"
    assert path.is_file(), f"SAVED_TICK_PROBE_MISSING:{path}"
    first = decode_tick_bi5(
        path.read_bytes(), pair="AUD_CAD", trading_day=day,
        source_key=daily_tick_key("AUD_CAD", day), price_scale=100_000,
    )
    second = decode_tick_bi5(
        path.read_bytes(), pair="AUD_CAD", trading_day=day,
        source_key=daily_tick_key("AUD_CAD", day), price_scale=100_000,
    )
    assert first == second
    assert len(first) == 100_705
    assert first[0].timestamp == datetime(2024, 1, 2, 0, 0, 0, 345_000, tzinfo=UTC)
    assert first[-1].timestamp == datetime(2024, 1, 2, 23, 59, 55, 331_000, tzinfo=UTC)
    assert first[0].bid == pytest.approx(0.90179)
    assert first[0].ask == pytest.approx(0.90196)
    assert all(row.ask >= row.bid for row in first)
    m5 = normalize_ticks_to_m5(first)
    assert len(m5.bars) == 288
    assert m5.bars[0].timestamp == datetime(2024, 1, 2, tzinfo=UTC)
    assert m5.bars[0].bid_open == pytest.approx(0.90179)
    assert m5.bars[0].ask_open == pytest.approx(0.90196)


def test_saved_tick_and_minute_candle_probes_produce_the_same_m5_ohlc():
    day = date(2024, 1, 2)
    ticks = decode_tick_bi5(
        (TICK_PROBE_ROOT / "AUDCAD_2024_00_02_ticks.bi5").read_bytes(),
        pair="AUD_CAD", trading_day=day, source_key=daily_tick_key("AUD_CAD", day), price_scale=100_000,
    )
    bid = decode_minute_candle_bi5(
        (EQUIVALENCE_PROBE_ROOT / "AUDCAD_2024_00_02_BID_candles_min_1.bi5").read_bytes(),
        pair="AUD_CAD", side="BID", trading_day=day,
        source_key=daily_candle_key("AUD_CAD", day, "BID"), price_scale=100_000,
    )
    ask = decode_minute_candle_bi5(
        (EQUIVALENCE_PROBE_ROOT / "AUDCAD_2024_00_02_ASK_candles_min_1.bi5").read_bytes(),
        pair="AUD_CAD", side="ASK", trading_day=day,
        source_key=daily_candle_key("AUD_CAD", day, "ASK"), price_scale=100_000,
    )
    from_ticks = normalize_ticks_to_m5(ticks).bars
    from_minutes = normalize_minute_candles_to_m5(bid, ask).bars
    assert len(from_ticks) == len(from_minutes) == 288
    tick_ohlc = [
        (bar.timestamp, bar.bid_open, bar.bid_high, bar.bid_low, bar.bid_close,
         bar.ask_open, bar.ask_high, bar.ask_low, bar.ask_close)
        for bar in from_ticks
    ]
    minute_ohlc = [
        (bar.timestamp, bar.bid_open, bar.bid_high, bar.bid_low, bar.bid_close,
         bar.ask_open, bar.ask_high, bar.ask_low, bar.ask_close)
        for bar in from_minutes
    ]
    assert tick_ohlc == minute_ohlc


@pytest.mark.parametrize(
    "payload,expected",
    [
        (b"not lzma", "DECOMPRESSION_FAILED"),
        (lzma.compress(b"x", format=lzma.FORMAT_ALONE), "RECORD_BOUNDARY_INVALID"),
        (compressed((86_400, 100_000, 100_000, 99_999, 100_001, 1.0)), "MINUTE_OFFSET_INVALID"),
        (compressed((0, 0, 100_000, 99_999, 100_001, 1.0)), "NONPOSITIVE"),
        (compressed((0, 100_000, 100_000, 100_001, 99_999, 1.0)), "OHLC_INVARIANT"),
        (compressed((0, 100_000, 100_000, 99_999, 100_001, float("nan"))), "ACTIVITY_INVALID"),
        (compressed((0, 100_000, 100_000, 99_999, 100_001, 1.0), (0, 100_000, 100_000, 99_999, 100_001, 1.0)), "NON_MONOTONIC"),
    ],
)
def test_synthetic_payload_failures(payload, expected):
    with pytest.raises(DukascopyBi5Error, match=expected):
        decode(payload)


@pytest.mark.parametrize(
    "payload,expected",
    [
        (b"not lzma", "DECOMPRESSION_FAILED"),
        (lzma.compress(b"x", format=lzma.FORMAT_ALONE), "TICK_RECORD_BOUNDARY_INVALID"),
        (compressed_ticks((86_400_000, 100_001, 100_000, 1.0, 1.0)), "TICK_OFFSET_INVALID"),
        (compressed_ticks((0, 0, 100_000, 1.0, 1.0)), "NONPOSITIVE"),
        (compressed_ticks((0, 99_999, 100_000, 1.0, 1.0)), "BID_ASK_RELATION"),
        (compressed_ticks((0, 100_001, 100_000, float("nan"), 1.0)), "VOLUME_INVALID"),
        (
            compressed_ticks((1_000, 100_001, 100_000, 1.0, 1.0), (999, 100_001, 100_000, 1.0, 1.0)),
            "TIMESTAMP_NON_MONOTONIC",
        ),
    ],
)
def test_synthetic_tick_payload_failures(payload, expected):
    with pytest.raises(DukascopyBi5Error, match=expected):
        decode_ticks(payload)


def test_tick_decoder_rejects_payload_that_exceeds_explicit_decompression_limit():
    payload = compressed_ticks(
        (0, 100_001, 100_000, 1.0, 1.0),
        (1, 100_002, 100_001, 1.0, 1.0),
    )
    with pytest.raises(DukascopyBi5Error, match="DECOMPRESSED_SIZE_LIMIT_EXCEEDED"):
        decode_ticks(payload, max_decompressed_bytes=TICK_RECORD.size)


def test_wrong_side_identity_and_scale_fail_closed():
    payload = compressed((0, 100_000, 100_000, 99_999, 100_001, 1.0))
    with pytest.raises(DukascopyBi5Error, match="SOURCE_IDENTITY_MISMATCH"):
        decode_minute_candle_bi5(
            payload, pair="EUR_USD", side="BID", trading_day=date(2024, 1, 2),
            source_key=daily_candle_key("EUR_USD", date(2024, 1, 2), "ASK"), price_scale=100_000,
        )
    with pytest.raises(DukascopyBi5Error, match="PRICE_SCALE_UNSUPPORTED"):
        decode(payload, scale=12_345)


def test_out_of_period_record_is_rejected_before_use():
    payload = compressed((0, 100_000, 100_000, 99_999, 100_001, 1.0))
    with pytest.raises(DukascopyBi5Error, match="OUTSIDE_ALLOWED_RANGE"):
        decode(payload, permitted_end=datetime(2024, 1, 2, tzinfo=UTC))


def minute(pair, side, stamp, value):
    return MinuteCandle(
        pair=pair, side=side, timestamp=stamp, open=value, high=value + .00003,
        low=value - .00002, close=value + .00001, activity=1.0,
        source_key="synthetic", source_offset_seconds=stamp.hour * 3600 + stamp.minute * 60,
    )


def test_m5_normalization_is_causal_and_missing_minutes_remain_missing():
    start = datetime(2024, 1, 2, 12, tzinfo=UTC)
    bid = [minute("EUR_USD", "BID", start + timedelta(minutes=index), 1.1 + index * .0001) for index in range(10)]
    ask = [minute("EUR_USD", "ASK", start + timedelta(minutes=index), 1.1002 + index * .0001) for index in range(10)]
    result = normalize_minute_candles_to_m5(bid, ask)
    assert [bar.timestamp for bar in result.bars] == [start, start + timedelta(minutes=5)]
    assert result.bars[0].bid_open == pytest.approx(1.1)
    assert result.bars[0].bid_close == pytest.approx(1.10041)

    missing = ask[:3] + ask[4:]
    missing_result = normalize_minute_candles_to_m5(bid, missing)
    assert [bar.timestamp for bar in missing_result.bars] == [start + timedelta(minutes=5)]
    assert missing_result.incomplete_buckets == (start,)

    altered_future = list(bid)
    altered_future[-1] = minute("EUR_USD", "BID", altered_future[-1].timestamp, 1.9)
    assert normalize_minute_candles_to_m5(altered_future, ask).bars[0] == result.bars[0]


def test_normalization_rejects_side_substitution_and_duplicates():
    start = datetime(2024, 1, 2, 12, tzinfo=UTC)
    bid = [minute("EUR_USD", "BID", start + timedelta(minutes=index), 1.1) for index in range(5)]
    ask = [minute("EUR_USD", "ASK", start + timedelta(minutes=index), 1.1002) for index in range(5)]
    with pytest.raises(DukascopyBi5Error, match="SIDE_IDENTITY"):
        normalize_minute_candles_to_m5(bid, bid)
    with pytest.raises(DukascopyBi5Error, match="NONUNIQUE"):
        normalize_minute_candles_to_m5(bid + [bid[0]], ask)


def tick(pair, stamp, ask, bid, sequence, source_key="synthetic_ticks"):
    return Tick(
        pair=pair,
        timestamp=stamp,
        ask=ask,
        bid=bid,
        ask_volume=1.0,
        bid_volume=1.0,
        source_key=source_key,
        source_offset_milliseconds=(stamp.hour * 3_600_000 + stamp.minute * 60_000 + stamp.second * 1_000),
        source_sequence=sequence,
    )


def test_tick_normalization_is_causal_and_does_not_fabricate_empty_buckets():
    start = datetime(2024, 1, 2, 12, tzinfo=UTC)
    source = [
        tick("EUR_USD", start, 1.1002, 1.1, 0),
        tick("EUR_USD", start + timedelta(minutes=3), 1.1005, 1.1003, 1),
        tick("EUR_USD", start + timedelta(minutes=5), 1.1007, 1.1005, 2),
    ]
    result = normalize_ticks_to_m5(source)
    assert [bar.timestamp for bar in result.bars] == [start, start + timedelta(minutes=5)]
    assert result.bars[0].bid_open == pytest.approx(1.1)
    assert result.bars[0].bid_close == pytest.approx(1.1003)
    assert result.bars[0].bid_source_record_count == 2
    assert result.incomplete_buckets == ()

    altered_future = list(source)
    altered_future[-1] = tick("EUR_USD", start + timedelta(minutes=5), 2.0, 1.9, 2)
    assert normalize_ticks_to_m5(altered_future).bars[0] == result.bars[0]


def test_tick_normalization_rejects_duplicate_source_rows_and_side_errors():
    start = datetime(2024, 1, 2, 12, tzinfo=UTC)
    first = tick("EUR_USD", start, 1.1002, 1.1, 0)
    with pytest.raises(DukascopyBi5Error, match="SOURCE_ROW_DUPLICATE"):
        normalize_ticks_to_m5([first, first])
    with pytest.raises(DukascopyBi5Error, match="BID_ASK_RELATION"):
        normalize_ticks_to_m5([tick("EUR_USD", start, 1.1, 1.1002, 0)])


def test_paired_ticks_build_mid_before_m5_aggregation_not_from_candle_extrema():
    start = datetime(2024, 1, 2, 12, tzinfo=UTC)
    source = [
        tick("EUR_USD", start, 1.1002, 1.1, 0),
        # BID high and ASK high happen on separate ticks.  Averaging the two
        # side-candle highs would produce an unavailable synthetic extreme.
        tick("EUR_USD", start + timedelta(minutes=1), 1.1006, 1.1005, 1),
        tick("EUR_USD", start + timedelta(minutes=2), 1.1015, 1.0999, 2),
        tick("EUR_USD", start + timedelta(minutes=4), 1.1004, 1.1001, 3),
    ]
    result = normalize_paired_ticks_to_m5_with_derived_mid(source)
    assert len(result.bars) == 1
    bar = result.bars[0]
    expected_midpoints = (1.1001, 1.10055, 1.1007, 1.10025)
    assert bar.mid_open == pytest.approx(expected_midpoints[0])
    assert bar.mid_high == pytest.approx(max(expected_midpoints))
    assert bar.mid_low == pytest.approx(min(expected_midpoints))
    assert bar.mid_close == pytest.approx(expected_midpoints[-1])
    assert bar.midpoint_method == "PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION"
    assert bar.mid_high != pytest.approx((bar.bid_high + bar.ask_high) / 2.0)
    assert bar.source_record_count == 4


def test_derived_mid_is_causal_and_never_fills_empty_tick_buckets():
    start = datetime(2024, 1, 2, 12, tzinfo=UTC)
    source = [
        tick("EUR_USD", start, 1.1002, 1.1, 0),
        tick("EUR_USD", start + timedelta(minutes=3), 1.1004, 1.1002, 1),
        tick("EUR_USD", start + timedelta(minutes=5), 1.1007, 1.1005, 2),
    ]
    result = normalize_paired_ticks_to_m5_with_derived_mid(source)
    assert [bar.timestamp for bar in result.bars] == [start, start + timedelta(minutes=5)]
    assert result.incomplete_buckets == ()
    altered_future = list(source)
    altered_future[-1] = tick("EUR_USD", start + timedelta(minutes=5), 2.0, 1.9, 2)
    assert normalize_paired_ticks_to_m5_with_derived_mid(altered_future).bars[0] == result.bars[0]
    assert normalize_paired_ticks_to_m5_with_derived_mid(()).bars == ()


def test_minute_candle_normalization_does_not_claim_a_derived_mid_series():
    start = datetime(2024, 1, 2, 12, tzinfo=UTC)
    bid = [minute("EUR_USD", "BID", start + timedelta(minutes=index), 1.1) for index in range(5)]
    ask = [minute("EUR_USD", "ASK", start + timedelta(minutes=index), 1.1002) for index in range(5)]
    candle = normalize_minute_candles_to_m5(bid, ask).bars[0]
    assert not hasattr(candle, "mid_open")
