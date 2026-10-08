"""PKT-045 paired-tick corpus construction and checked local reader.

This module has no network, broker, or scoring entry point.  It turns only
receipted same-record Dukascopy ticks into deterministic completed M5 rows.
The derived midpoint remains a named PKT-045 data semantic, never a substitute
for a provider-native MID candle.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from automation.forex_engine import forex_edge_validation_pipeline_v1 as validation
from . import dukascopy_acquisition as acquisition
from . import dukascopy_bi5


UTC = timezone.utc
PKT045_CORPUS_SCHEMA = "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_M5_CORPUS_V1"
PKT045_MIDPOINT_METHOD = "PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION"
PKT045_DUKASCOPY_FX_SCALE_RULE_VERSION = "DUKASCOPY_BI5_FX_POINT_VALUE_V1"
PKT045_DUKASCOPY_FX_SCALE_DOCUMENTATION = (
    "https://www.dukascopy.com/wiki/en/development/data-export/"
)


class Pkt045CorpusError(RuntimeError):
    """The separate successor corpus is incomplete, changed, or malformed."""


def _inside(path: Path, root: Path, code: str) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise Pkt045CorpusError(code) from exc


def _utc_text(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise Pkt045CorpusError("PKT045_CORPUS_TIMESTAMP_TIMEZONE_MISSING")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def dukascopy_fx_tick_metadata(pairs: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Return the documented BI5 point-value rule for the frozen FX universe.

    This is source metadata, not a repurposed OANDA display precision.  The
    Dukascopy BI5 format documentation specifies point value 100,000 for
    standard FX quotations and 1,000 for JPY quote-currency pairs.  PKT-045's
    frozen universe contains only six-letter FX instruments, so every mapping
    is explicit, deterministic, and fails closed for another asset type.
    """
    result: dict[str, dict[str, Any]] = {}
    for supplied in pairs:
        try:
            pair = dukascopy_bi5.canonical_pair(str(supplied))
        except dukascopy_bi5.DukascopyBi5Error as exc:
            raise Pkt045CorpusError("PKT045_DUKASCOPY_FX_PAIR_IDENTIFIER_INVALID") from exc
        base, quote = pair.split("_")
        if not (base.isalpha() and quote.isalpha() and len(base) == len(quote) == 3):
            raise Pkt045CorpusError("PKT045_DUKASCOPY_FX_PAIR_IDENTIFIER_INVALID")
        if pair in result:
            raise Pkt045CorpusError("PKT045_DUKASCOPY_FX_PAIR_DUPLICATE")
        jpy_quote = quote == "JPY"
        result[pair] = {
            "source_price_scale": 1_000 if jpy_quote else 100_000,
            "pip_size": 0.01 if jpy_quote else 0.0001,
            "source_scale_rule_version": PKT045_DUKASCOPY_FX_SCALE_RULE_VERSION,
            "source_scale_documentation": PKT045_DUKASCOPY_FX_SCALE_DOCUMENTATION,
        }
    return dict(sorted(result.items()))


def _price_scale(pair: str, source_metadata: Mapping[str, Mapping[str, Any]]) -> int:
    metadata = source_metadata.get(pair)
    if not isinstance(metadata, Mapping):
        raise Pkt045CorpusError("PKT045_CORPUS_SOURCE_METADATA_MISSING:" + pair)
    scale = metadata.get("source_price_scale")
    if isinstance(scale, bool) or not isinstance(scale, int):
        raise Pkt045CorpusError("PKT045_CORPUS_SOURCE_PRICE_SCALE_INVALID:" + pair)
    if scale not in dukascopy_bi5.SUPPORTED_PRICE_SCALES:
        raise Pkt045CorpusError("PKT045_CORPUS_PRICE_SCALE_UNSUPPORTED:" + pair)
    return scale


def _pair_data_path(corpus_root: Path, pair: str) -> Path:
    symbol = dukascopy_bi5.source_symbol(pair)
    return corpus_root / "pairs" / f"{symbol}.m5.jsonl.gz"


def _pair_manifest_path(corpus_root: Path, pair: str) -> Path:
    symbol = dukascopy_bi5.source_symbol(pair)
    return corpus_root / "pair_manifests" / f"{symbol}.json"


def _row_from_bar(bar: dukascopy_bi5.DerivedMidM5Candle) -> dict[str, Any]:
    if not bar.completed or bar.midpoint_method != PKT045_MIDPOINT_METHOD:
        raise Pkt045CorpusError("PKT045_CORPUS_BAR_SEMANTICS_INVALID")
    return {
        "instrument": bar.pair,
        "timestamp": _utc_text(bar.timestamp),
        "bid": {"o": bar.bid_open, "h": bar.bid_high, "l": bar.bid_low, "c": bar.bid_close},
        "ask": {"o": bar.ask_open, "h": bar.ask_high, "l": bar.ask_low, "c": bar.ask_close},
        "mid": {"o": bar.mid_open, "h": bar.mid_high, "l": bar.mid_low, "c": bar.mid_close},
        "volume": bar.source_record_count,
        "complete": True,
        "midpoint_method": bar.midpoint_method,
        "source_keys": list(bar.source_keys),
    }


def _validate_row(row: Mapping[str, Any], *, pair: str, previous_timestamp: datetime | None) -> datetime:
    if row.get("instrument") != pair or row.get("complete") is not True:
        raise Pkt045CorpusError("PKT045_CORPUS_ROW_IDENTITY_INVALID")
    if row.get("midpoint_method") != PKT045_MIDPOINT_METHOD:
        raise Pkt045CorpusError("PKT045_CORPUS_ROW_MIDPOINT_SEMANTICS_INVALID")
    try:
        stamp = validation.parse_utc(str(row["timestamp"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise Pkt045CorpusError("PKT045_CORPUS_ROW_TIMESTAMP_INVALID") from exc
    if stamp.second or stamp.microsecond or stamp.minute % 5:
        raise Pkt045CorpusError("PKT045_CORPUS_ROW_M5_GRID_INVALID")
    if previous_timestamp is not None and stamp <= previous_timestamp:
        raise Pkt045CorpusError("PKT045_CORPUS_ROW_ORDER_OR_DUPLICATE_INVALID")
    for side in ("bid", "ask", "mid"):
        value = row.get(side)
        if not isinstance(value, Mapping):
            raise Pkt045CorpusError("PKT045_CORPUS_ROW_SIDE_MISSING")
        try:
            o, h, l, c = (float(value[key]) for key in ("o", "h", "l", "c"))
        except (KeyError, TypeError, ValueError) as exc:
            raise Pkt045CorpusError("PKT045_CORPUS_ROW_OHLC_INVALID") from exc
        if not all(number > 0 and number < float("inf") for number in (o, h, l, c)):
            raise Pkt045CorpusError("PKT045_CORPUS_ROW_PRICE_INVALID")
        if l > min(o, c) or h < max(o, c) or l > h:
            raise Pkt045CorpusError("PKT045_CORPUS_ROW_OHLC_INVARIANT_INVALID")
    if any(float(row["bid"][field]) > float(row["ask"][field]) for field in ("o", "h", "l", "c")):
        raise Pkt045CorpusError("PKT045_CORPUS_ROW_BID_ASK_RELATION_INVALID")
    if not isinstance(row.get("volume"), int) or row["volume"] <= 0:
        raise Pkt045CorpusError("PKT045_CORPUS_ROW_SOURCE_COUNT_INVALID")
    if not isinstance(row.get("source_keys"), list) or not row["source_keys"]:
        raise Pkt045CorpusError("PKT045_CORPUS_ROW_PROVENANCE_INVALID")
    return stamp


def _raw_receipts_by_key(
    *, inventory: acquisition.PairedTickInventory, raw_root: Path, receipt_root: Path
) -> dict[str, dict[str, Any]]:
    receipts = acquisition.paired_tick_completed_raw_receipts(
        inventory=inventory, raw_root=raw_root, receipt_root=receipt_root,
    )
    if len(receipts) != inventory.available_tick_object_count:
        raise Pkt045CorpusError("PKT045_CORPUS_UNRECEIPTED_RAW_OBJECTS")
    indexed = {receipt["SOURCE"]["OBJECT_KEY"]: receipt for receipt in receipts}
    if len(indexed) != len(receipts) or set(indexed) != {source.key for source in inventory.objects}:
        raise Pkt045CorpusError("PKT045_CORPUS_RAW_RECEIPT_SET_MISMATCH")
    return indexed


def _write_pair(
    *,
    corpus_root: Path,
    pair: str,
    sources: Sequence[acquisition.SourceObject],
    raw_root: Path,
    receipts_by_key: Mapping[str, Mapping[str, Any]],
    price_scale: int,
    max_corpus_bytes: int | None,
) -> dict[str, Any]:
    data_path = _pair_data_path(corpus_root, pair)
    manifest_path = _pair_manifest_path(corpus_root, pair)
    partial = data_path.with_name(f"{data_path.name}.part")
    if data_path.exists() or manifest_path.exists() or partial.exists():
        if not data_path.is_file() or not manifest_path.is_file() or partial.exists():
            raise Pkt045CorpusError("PKT045_CORPUS_PAIR_PARTIAL_OR_CONFLICTING_OUTPUT")
        return verify_pair_m5_file(data_path=data_path, manifest_path=manifest_path, pair=pair)
    if not sources:
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_SOURCE_OBJECTS_MISSING")
    data_path.parent.mkdir(parents=True, exist_ok=True)
    source_records = 0
    m5_rows = 0
    previous: datetime | None = None
    raw_entries: list[dict[str, Any]] = []
    try:
        with partial.open("xb") as raw_handle:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as compressed:
                for source in sorted(sources, key=lambda item: item.key):
                    receipt = receipts_by_key.get(source.key)
                    if receipt is None:
                        raise Pkt045CorpusError("PKT045_CORPUS_SOURCE_RECEIPT_MISSING")
                    path = acquisition.raw_object_path(raw_root, source)
                    try:
                        payload = path.read_bytes()
                        key_pair, trading_day = dukascopy_bi5.parse_daily_tick_key(source.key)
                        ticks = dukascopy_bi5.decode_tick_bi5(
                            payload,
                            pair=key_pair,
                            trading_day=trading_day,
                            source_key=source.key,
                            price_scale=price_scale,
                        )
                        normalized = dukascopy_bi5.normalize_paired_ticks_to_m5_with_derived_mid(ticks)
                    except (OSError, dukascopy_bi5.DukascopyBi5Error) as exc:
                        raise Pkt045CorpusError("PKT045_CORPUS_TICK_NORMALIZATION_FAILED:" + source.key) from exc
                    if not ticks or normalized.incomplete_buckets:
                        raise Pkt045CorpusError("PKT045_CORPUS_SOURCE_OBJECT_HAS_NO_VALID_COMPLETED_TICKS:" + source.key)
                    source_records += len(ticks)
                    for bar in normalized.bars:
                        row = _row_from_bar(bar)
                        stamp = _validate_row(row, pair=pair, previous_timestamp=previous)
                        previous = stamp
                        compressed.write((validation.canonical_json(row) + "\n").encode("ascii"))
                        m5_rows += 1
                        if max_corpus_bytes is not None and m5_rows % 1_024 == 0:
                            compressed.flush()
                            if raw_handle.tell() > max_corpus_bytes:
                                raise Pkt045CorpusError("PKT045_CORPUS_OUTPUT_RESERVATION_EXCEEDED")
                    raw_entries.append({
                        "OBJECT_KEY": source.key,
                        "LISTED_SIZE": source.size,
                        "LISTED_ETAG": source.etag,
                        "LOCAL_SHA256": receipt["LOCAL_SHA256"],
                        "TICK_RECORDS": len(ticks),
                    })
            raw_handle.flush()
            os.fsync(raw_handle.fileno())
        partial.replace(data_path)
    except Exception:
        # A partial file is deliberately retained as an explicit recovery block.
        raise
    if not m5_rows:
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_HAS_NO_M5_ROWS")
    manifest = {
        "schema": "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_PAIR_MANIFEST_V1",
        "PAIR": pair,
        "PRICE_SCALE": price_scale,
        "MIDPOINT_METHOD": PKT045_MIDPOINT_METHOD,
        "RAW_OBJECT_COUNT": len(raw_entries),
        "RAW_OBJECTS": raw_entries,
        "SOURCE_TICK_RECORDS": source_records,
        "M5_ROWS": m5_rows,
        "M5_FILE": data_path.name,
        "M5_FILE_SHA256": validation.sha256_file(data_path),
        "FIRST_TIMESTAMP": None,
        "LAST_TIMESTAMP": None,
    }
    verified = _scan_pair_m5_file(data_path=data_path, pair=pair)
    manifest["FIRST_TIMESTAMP"] = verified["FIRST_TIMESTAMP"]
    manifest["LAST_TIMESTAMP"] = verified["LAST_TIMESTAMP"]
    acquisition.write_new_deterministic_json(manifest_path, manifest)
    return manifest


def _scan_pair_m5_file(*, data_path: Path, pair: str) -> dict[str, Any]:
    if not data_path.is_file():
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_FILE_MISSING")
    previous: datetime | None = None
    count = 0
    try:
        with gzip.open(data_path, mode="rt", encoding="ascii", newline="") as handle:
            for line in handle:
                if not line.endswith("\n"):
                    raise Pkt045CorpusError("PKT045_CORPUS_PAIR_LINE_TERMINATOR_INVALID")
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise Pkt045CorpusError("PKT045_CORPUS_PAIR_JSON_INVALID") from exc
                previous = _validate_row(row, pair=pair, previous_timestamp=previous)
                count += 1
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_GZIP_INVALID") from exc
    if not count or previous is None:
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_EMPTY")
    first: datetime | None = None
    with gzip.open(data_path, mode="rt", encoding="ascii", newline="") as handle:
        for line in handle:
            first = validation.parse_utc(json.loads(line)["timestamp"])
            break
    if first is None:
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_EMPTY")
    return {"M5_ROWS": count, "FIRST_TIMESTAMP": _utc_text(first), "LAST_TIMESTAMP": _utc_text(previous)}


def verify_pair_m5_file(*, data_path: Path, manifest_path: Path, pair: str) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_MANIFEST_INVALID") from exc
    if manifest.get("schema") != "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_PAIR_MANIFEST_V1" or manifest.get("PAIR") != pair:
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_MANIFEST_IDENTITY_INVALID")
    if manifest.get("M5_FILE") != data_path.name or manifest.get("M5_FILE_SHA256") != validation.sha256_file(data_path):
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_FILE_HASH_MISMATCH")
    scanned = _scan_pair_m5_file(data_path=data_path, pair=pair)
    for key, value in scanned.items():
        if manifest.get(key) != value:
            raise Pkt045CorpusError("PKT045_CORPUS_PAIR_MANIFEST_CONTENT_MISMATCH")
    return manifest


def build_paired_tick_m5_corpus(
    *,
    inventory: acquisition.PairedTickInventory,
    raw_root: Path,
    receipt_root: Path,
    corpus_root: Path,
    output_root: Path,
    source_metadata: Mapping[str, Mapping[str, Any]],
    development_start: datetime,
    development_end: datetime,
    max_corpus_bytes: int | None = None,
    progress: Callable[[str, int, int, Mapping[str, Any]], None] | None = None,
    check_limits: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Build or verify the immutable PKT-045 M5 corpus from receipted raw ticks."""
    _inside(corpus_root, output_root, "PKT045_CORPUS_OUTPUT_SCOPE_INVALID")
    _inside(raw_root, output_root, "PKT045_CORPUS_RAW_SCOPE_INVALID")
    _inside(receipt_root, output_root, "PKT045_CORPUS_RECEIPT_SCOPE_INVALID")
    if development_start.tzinfo is None or development_end.tzinfo is None:
        raise Pkt045CorpusError("PKT045_CORPUS_DEVELOPMENT_TIMEZONE_INVALID")
    if max_corpus_bytes is not None and (
        isinstance(max_corpus_bytes, bool) or not isinstance(max_corpus_bytes, int) or max_corpus_bytes <= 0
    ):
        raise Pkt045CorpusError("PKT045_CORPUS_OUTPUT_RESERVATION_INVALID")
    pairs = tuple(sorted(inventory.per_pair))
    if len(pairs) != inventory.pair_count or set(pairs) != set(source_metadata):
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_UNIVERSE_MISMATCH")
    receipts_by_key = _raw_receipts_by_key(
        inventory=inventory, raw_root=raw_root, receipt_root=receipt_root,
    )
    by_pair: dict[str, list[acquisition.SourceObject]] = defaultdict(list)
    for source in inventory.objects:
        by_pair[source.pair].append(source)
    manifests = []
    for number, pair in enumerate(pairs, 1):
        if check_limits is not None:
            check_limits()
        existing_size = sum(path.stat().st_size for path in corpus_root.rglob("*") if path.is_file()) if corpus_root.exists() else 0
        if max_corpus_bytes is not None and existing_size > max_corpus_bytes:
            raise Pkt045CorpusError("PKT045_CORPUS_OUTPUT_RESERVATION_EXCEEDED")
        remaining = None if max_corpus_bytes is None else max_corpus_bytes - existing_size
        # Reserve enough room for gzip's final buffered block/footer.  A corpus
        # that cannot reserve this small fixed amount stops before the pair is
        # sealed rather than writing beyond the Stage 1 output reservation.
        if remaining is not None and remaining <= 8_192:
            raise Pkt045CorpusError("PKT045_CORPUS_OUTPUT_RESERVATION_EXCEEDED")
        manifests.append(_write_pair(
            corpus_root=corpus_root,
            pair=pair,
            sources=by_pair[pair],
            raw_root=raw_root,
            receipts_by_key=receipts_by_key,
            price_scale=_price_scale(pair, source_metadata),
            max_corpus_bytes=(None if remaining is None else remaining - 8_192),
        ))
        if progress is not None:
            progress("NORMALIZE_PKT045_PAIR", number, len(pairs), {
                "pair": pair, "m5_rows": manifests[-1]["M5_ROWS"],
            })
        if check_limits is not None:
            check_limits()
    raw_manifest = {
        "schema": "AIOS_PKT045_DUKASCOPY_PAIRED_TICK_RAW_MANIFEST_V1",
        "OBJECTS": [
            {
                "SOURCE": receipt["SOURCE"],
                "LOCAL_SHA256": receipt["LOCAL_SHA256"],
                "GET_OBJECT_RESPONSE": receipt["GET_OBJECT_RESPONSE"],
            }
            for _key, receipt in sorted(receipts_by_key.items())
        ],
    }
    raw_manifest_hash = acquisition.write_new_deterministic_json(
        corpus_root / "RAW_OBJECT_MANIFEST.json", raw_manifest,
    )
    pair_manifest_hashes = {
        manifest["PAIR"]: validation.sha256_file(_pair_manifest_path(corpus_root, manifest["PAIR"]))
        for manifest in manifests
    }
    corpus_basis = {
        "packet_id": "PKT-FOREX-045",
        "schema": PKT045_CORPUS_SCHEMA,
        "provider": "DUKASCOPY",
        "source_type": "PAIRED_TICK",
        "midpoint_method": PKT045_MIDPOINT_METHOD,
        "pairs": list(pairs),
        "development_start": _utc_text(development_start),
        "development_end": _utc_text(development_end),
        "raw_manifest_sha256": raw_manifest_hash,
        "pair_manifest_sha256": pair_manifest_hashes,
        "normalizer_sha256": validation.sha256_file(Path(dukascopy_bi5.__file__)),
        "source_scale_rule_version": PKT045_DUKASCOPY_FX_SCALE_RULE_VERSION,
        "source_scale_metadata_sha256": validation.sha256_value(source_metadata),
    }
    corpus_id = "PKT045_DUKASCOPY_PAIRED_TICK_MID_" + validation.sha256_value(corpus_basis)[:16]
    manifest = {
        **corpus_basis,
        "corpus_id": corpus_id,
        "pair_count": len(pairs),
        "raw_object_count": len(receipts_by_key),
        "raw_bytes": sum(source.size for source in inventory.objects),
        "source_tick_records": sum(int(item["SOURCE_TICK_RECORDS"]) for item in manifests),
        "m5_rows": sum(int(item["M5_ROWS"]) for item in manifests),
        "corpus_status": "SEALED_AWAITING_EXECUTABLE_PATH_CERTIFICATION",
    }
    acquisition.write_new_deterministic_json(corpus_root / "CORPUS_MANIFEST.json", manifest)
    return verify_paired_tick_m5_corpus(corpus_root=corpus_root, expected_pairs=pairs)


def verify_paired_tick_m5_corpus(*, corpus_root: Path, expected_pairs: Sequence[str]) -> dict[str, Any]:
    """Verify the frozen local PKT-045 corpus without opening other data roots."""
    manifest_path = corpus_root / "CORPUS_MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Pkt045CorpusError("PKT045_CORPUS_MANIFEST_INVALID") from exc
    pairs = tuple(sorted(expected_pairs))
    if (
        manifest.get("schema") != PKT045_CORPUS_SCHEMA
        or manifest.get("packet_id") != "PKT-FOREX-045"
        or manifest.get("source_type") != "PAIRED_TICK"
        or manifest.get("midpoint_method") != PKT045_MIDPOINT_METHOD
        or manifest.get("pairs") != list(pairs)
        or manifest.get("pair_count") != len(pairs)
    ):
        raise Pkt045CorpusError("PKT045_CORPUS_MANIFEST_IDENTITY_INVALID")
    pair_hashes = manifest.get("pair_manifest_sha256")
    if not isinstance(pair_hashes, Mapping) or set(pair_hashes) != set(pairs):
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_MANIFEST_SET_INVALID")
    total_rows = 0
    for pair in pairs:
        path = _pair_data_path(corpus_root, pair)
        pair_manifest = _pair_manifest_path(corpus_root, pair)
        if validation.sha256_file(pair_manifest) != pair_hashes[pair]:
            raise Pkt045CorpusError("PKT045_CORPUS_PAIR_MANIFEST_HASH_MISMATCH")
        checked = verify_pair_m5_file(data_path=path, manifest_path=pair_manifest, pair=pair)
        total_rows += int(checked["M5_ROWS"])
    if manifest.get("m5_rows") != total_rows or total_rows <= 0:
        raise Pkt045CorpusError("PKT045_CORPUS_TOTAL_ROW_MISMATCH")
    if not (corpus_root / "RAW_OBJECT_MANIFEST.json").is_file():
        raise Pkt045CorpusError("PKT045_CORPUS_RAW_MANIFEST_MISSING")
    return manifest


def read_paired_tick_m5_rows(*, corpus_root: Path, pair: str) -> list[dict[str, Any]]:
    """Read one checked pair only; no fallback to PKT-044 or another corpus."""
    canonical = dukascopy_bi5.canonical_pair(pair)
    try:
        manifest = json.loads((corpus_root / "CORPUS_MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Pkt045CorpusError("PKT045_CORPUS_MANIFEST_INVALID") from exc
    pairs = manifest.get("pairs")
    hashes = manifest.get("pair_manifest_sha256")
    if (
        manifest.get("schema") != PKT045_CORPUS_SCHEMA
        or manifest.get("packet_id") != "PKT-FOREX-045"
        or not isinstance(pairs, list)
        or not isinstance(hashes, Mapping)
        or canonical not in pairs
        or canonical not in hashes
    ):
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_NOT_ELIGIBLE")
    pair_manifest_path = _pair_manifest_path(corpus_root, canonical)
    if validation.sha256_file(pair_manifest_path) != hashes[canonical]:
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_MANIFEST_HASH_MISMATCH")
    verify_pair_m5_file(
        data_path=_pair_data_path(corpus_root, canonical),
        manifest_path=pair_manifest_path,
        pair=canonical,
    )
    rows: list[dict[str, Any]] = []
    try:
        with gzip.open(_pair_data_path(corpus_root, canonical), mode="rt", encoding="ascii", newline="") as handle:
            for line in handle:
                rows.append(json.loads(line))
    except (OSError, EOFError, gzip.BadGzipFile, json.JSONDecodeError) as exc:
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_READER_FAILED") from exc
    previous: datetime | None = None
    for row in rows:
        previous = _validate_row(row, pair=canonical, previous_timestamp=previous)
    if not rows:
        raise Pkt045CorpusError("PKT045_CORPUS_PAIR_EMPTY")
    return rows
