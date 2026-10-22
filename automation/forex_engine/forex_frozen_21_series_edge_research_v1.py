"""Offline Phase 1 edge research for the frozen AIOS 21-series dataset.

The module is deliberately self-contained and standard-library only.  It reads
an already certified immutable dataset, evaluates a predeclared candidate
registry chronologically, and writes bounded evidence.  It has no broker,
credential, network, collector, PAPER, or LIVE dependency.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import calendar
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence


TOOL_VERSION = "1.0.0"
SCHEMA = "AIOS_FOREX_FROZEN_21_SERIES_EDGE_RESEARCH.v1"
DATASET_ID = "AIOS-FX-HIST-V1-b6a62a1175398354580b"
DATASET_SHA256 = "b6a62a1175398354580be3f242cdb67aa3134988b7448c1e1fa11d8abcfb1e7d"
SOURCE_STATE_SHA256 = "7e594b81d02a6d910043fb818498bce176d1360b866d4b2c37e111a9288631d6"
MANIFEST_SHA256 = "9aba4a71f9c72ced9bd359bfc1b29315cf0d5d9d7c6f2ad9a578bfecacaeb7d1"
SCOPE_FINGERPRINT = "e7ea1cf452a0cbafc9e2071c250c81b6cef242f800e2a2d0e694bcabfbade680"
EXPECTED_HEAD = "b86c65140ed03d53d6c8d6c3618e50da0502f51b"
EXPECTED_INSTRUMENTS = ("EUR_USD", "GBP_USD", "USD_JPY")
EXPECTED_GRANULARITIES = ("M1", "M2", "M4", "S5", "S10", "S15", "S30")
GRANULARITY_SECONDS = {"M1": 60, "M2": 120, "M4": 240, "S5": 5, "S10": 10, "S15": 15, "S30": 30}
REQUESTED_START = "2024-01-01T00:00:00Z"
DEVELOPMENT_END = "2025-08-06T04:48:00Z"
VALIDATION_END = "2026-02-16T14:24:00Z"
SEALED_HOLDOUT_END = "2026-08-30T00:00:00Z"
RISK_FRACTION = 0.0025


class ResearchBlocked(RuntimeError):
    """Raised when evidence cannot safely support a research result."""


@dataclass(frozen=True)
class Candle:
    time: datetime
    instrument: str
    granularity: str
    bid_o: float
    bid_h: float
    bid_l: float
    bid_c: float
    ask_o: float
    ask_h: float
    ask_l: float
    ask_c: float

    @property
    def mid_c(self) -> float:
        return (self.bid_c + self.ask_c) / 2.0

    @property
    def mid_h(self) -> float:
        return (self.bid_h + self.ask_h) / 2.0

    @property
    def mid_l(self) -> float:
        return (self.bid_l + self.ask_l) / 2.0


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    family: str
    variant: int
    granularity: str
    lookback: int
    slow_lookback: int
    stop_atr: float
    target_r: float
    threshold: float
    max_holding_bars: int
    directions: tuple[str, ...] = ("LONG", "SHORT")


@dataclass
class Position:
    candidate_id: str
    instrument: str
    direction: str
    signal_time: datetime
    entry_time: datetime
    entry: float
    stop: float
    target: float
    risk: float
    split: str
    session: str
    regime: str
    bars: int = 0


def parse_utc(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("TIMESTAMP_TIMEZONE_MISSING")
    return parsed.astimezone(timezone.utc)


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256((stable(value) + "\n").encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchBlocked(f"JSON_READ_FAILED:{path}:{type(exc).__name__}") from exc


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
            stream.write("\n")
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


def build_candidates() -> list[Candidate]:
    """Return the deterministic, outcome-blind Phase 1 registry."""
    specs = {
        "TREND_CONTINUATION": (("M2", 18, 48, 0.10), ("M4", 24, 64, 0.12), ("M4", 30, 80, 0.14)),
        "PULLBACK": (("M1", 16, 48, 0.10), ("M2", 20, 60, 0.12), ("M4", 24, 72, 0.14)),
        "BREAKOUT": (("S30", 18, 54, 0.00), ("M1", 24, 72, 0.00), ("M2", 30, 90, 0.00)),
        "MOMENTUM": (("S10", 18, 54, 0.80), ("S30", 24, 72, 1.00), ("M1", 30, 90, 1.20)),
        "VOLATILITY_EXPANSION": (("S5", 18, 54, 1.15), ("S15", 24, 72, 1.25), ("S30", 30, 90, 1.35)),
        "SESSION_BREAKOUT": (("S30", 18, 54, 0.00), ("M1", 24, 72, 0.00), ("M2", 30, 90, 0.00)),
        "MEAN_REVERSION": (("S10", 18, 54, 1.35), ("S30", 24, 72, 1.60), ("M1", 30, 90, 1.85)),
        "MULTI_TIMEFRAME_CONFIRMATION": (("M1", 16, 64, 0.08), ("M2", 20, 80, 0.10), ("M4", 24, 96, 0.12)),
    }
    candidates: list[Candidate] = []
    for family, variants in specs.items():
        for variant, (granularity, lookback, slow, threshold) in enumerate(variants, 1):
            candidates.append(
                Candidate(
                    candidate_id=f"{family}-V{variant}", family=family, variant=variant,
                    granularity=granularity, lookback=lookback, slow_lookback=slow,
                    stop_atr=(1.25, 1.50, 1.75)[variant - 1],
                    target_r=(1.50, 2.00, 2.50)[variant - 1], threshold=threshold,
                    max_holding_bars=(24, 36, 48)[variant - 1],
                )
            )
    return candidates


def build_contract(*, source_head: str = EXPECTED_HEAD) -> dict[str, Any]:
    candidates = build_candidates()
    registry = [asdict(item) for item in candidates]
    return {
        "schema": f"{SCHEMA}.contract", "tool_version": TOOL_VERSION,
        "packet_id": "PKT-FOREX-004", "execution_boundary_id": "PKT-FOREX-004-FROZEN-21-SERIES-PHASE1-001",
        "source_head": source_head, "research_code_sha256": sha256_file(Path(__file__)),
        "dataset_id": DATASET_ID, "dataset_sha256": DATASET_SHA256,
        "source_state_sha256": SOURCE_STATE_SHA256, "manifest_sha256": MANIFEST_SHA256,
        "scope_fingerprint": SCOPE_FINGERPRINT, "seed": 4001,
        "candidate_cap": 24, "candidate_registry_sha256": canonical_sha256(registry),
        "splits": {
            "development": [REQUESTED_START, DEVELOPMENT_END],
            "phase1_validation": [DEVELOPMENT_END, VALIDATION_END],
            "sealed_final_holdout": [VALIDATION_END, SEALED_HOLDOUT_END],
        },
        "holdout_policy": "SEALED_AND_NOT_EVALUATED_IN_PHASE1",
        "embargo": "MAX_LOOKBACK_PLUS_MAX_HOLDING_BARS_PER_CANDIDATE",
        "execution": "SIGNAL_AFTER_COMPLETED_CLOSE_ENTRY_AT_NEXT_ELIGIBLE_OPEN",
        "costs": {
            "base": {"spread": "RECORDED_BID_ASK_ONCE", "slippage_price": 0.00001, "financing": "NO_POSITION_ACROSS_NEW_YORK_17_00"},
            "stress": {"spread_multiplier": 1.5, "slippage_price": 0.00003, "financing": "NO_POSITION_ACROSS_NEW_YORK_17_00"},
        },
        "risk_fraction_per_trade": RISK_FRACTION,
        "adequacy": {"trades": 200, "long_trades": 50, "short_trades": 50, "instruments": 2, "positive_development_folds": 4},
        "gates": {"expectancy_r_gt": 0.0, "profit_factor_gte": 1.10, "max_drawdown_pct_lte": 10.0, "largest_pair_share_lte": 0.60},
        "reproduction_command": (
            "python scripts/forex_delivery/run_forex_frozen_21_series_edge_research_v1.py run "
            "--dataset-root .aios/runtime/forex_historical_dataset_freezes_v1/AIOS-FX-HIST-V1-b6a62a1175398354580b "
            "--output-root .aios/runtime/forex_frozen_21_series_edge_research_v1 --source-head " + source_head
        ),
    }


def _require_equal(document: Mapping[str, Any], field: str, expected: Any, source: str) -> None:
    if document.get(field) != expected:
        raise ResearchBlocked(f"{source}_{field.upper()}_MISMATCH")


def verify_frozen_dataset(dataset_root: Path, *, verify_files: bool = True) -> dict[str, Any]:
    """Fail closed unless the immutable dataset matches the authorized identity."""
    dataset_root = dataset_root.resolve()
    if dataset_root.name != DATASET_ID:
        raise ResearchBlocked("DATASET_ID_PATH_MISMATCH")
    inventory = load_json(dataset_root / "AIOS_FOREX_HISTORICAL_DATASET_INVENTORY.json")
    validation = load_json(dataset_root / "AIOS_FOREX_HISTORICAL_DATASET_VALIDATION_RECEIPT.json")
    freeze = load_json(dataset_root / "AIOS_FOREX_HISTORICAL_DATASET_FREEZE_RECEIPT.json")
    for doc, source in ((inventory, "INVENTORY"), (freeze, "FREEZE")):
        _require_equal(doc, "dataset_id", DATASET_ID, source)
        _require_equal(doc, "dataset_sha256", DATASET_SHA256, source)
        _require_equal(doc, "scope_fingerprint", SCOPE_FINGERPRINT, source)
    # The v1 validation receipt predates assignment of the deterministic
    # dataset ID.  Its dataset hash is authoritative; the inventory and freeze
    # receipt bind that hash to DATASET_ID.
    _require_equal(validation, "dataset_sha256", DATASET_SHA256, "VALIDATION")
    _require_equal(validation, "scope_fingerprint", SCOPE_FINGERPRINT, "VALIDATION")
    _require_equal(validation, "source_state_sha256", SOURCE_STATE_SHA256, "VALIDATION")
    _require_equal(validation, "manifest_sha256", MANIFEST_SHA256, "VALIDATION")
    _require_equal(freeze, "source_state_sha256", SOURCE_STATE_SHA256, "FREEZE")
    _require_equal(freeze, "manifest_sha256", MANIFEST_SHA256, "FREEZE")
    _require_equal(validation, "status", "PASS", "VALIDATION")
    _require_equal(freeze, "status", "PASS", "FREEZE")
    _require_equal(validation, "series_complete", 21, "VALIDATION")
    _require_equal(validation, "total_candle_count", 70822831, "VALIDATION")
    series = inventory.get("series_inventory")
    files = inventory.get("file_inventory")
    if not isinstance(series, list) or len(series) != 21 or not isinstance(files, list) or len(files) != 14200:
        raise ResearchBlocked("FROZEN_INVENTORY_CARDINALITY_MISMATCH")
    observed = {(item.get("instrument"), item.get("granularity")) for item in series}
    expected = {(pair, granularity) for pair in EXPECTED_INSTRUMENTS for granularity in EXPECTED_GRANULARITIES}
    if observed != expected:
        raise ResearchBlocked("FROZEN_SERIES_CARTESIAN_PRODUCT_MISMATCH")
    source_root = (dataset_root / "source_artifacts").resolve()
    try:
        source_root.relative_to(dataset_root)
    except ValueError as exc:
        raise ResearchBlocked("SOURCE_ARTIFACT_PATH_ESCAPE") from exc
    checked = 0
    total_bytes = 0
    for item in files:
        relative = Path(str(item.get("relative_path", "")))
        path = (source_root / relative).resolve()
        try:
            path.relative_to(source_root)
        except ValueError as exc:
            raise ResearchBlocked(f"INVENTORY_PATH_ESCAPE:{relative}") from exc
        if not path.is_file() or path.stat().st_size != item.get("bytes"):
            raise ResearchBlocked(f"FROZEN_FILE_MISSING_OR_SIZE_MISMATCH:{relative.as_posix()}")
        if verify_files and sha256_file(path) != item.get("sha256"):
            raise ResearchBlocked(f"FROZEN_FILE_HASH_MISMATCH:{relative.as_posix()}")
        checked += 1
        total_bytes += path.stat().st_size
    return {
        "dataset_root": str(dataset_root), "source_root": str(source_root), "inventory": inventory,
        "files_checked": checked, "bytes_checked": total_bytes, "hashes_checked": bool(verify_files),
    }


def _number(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ResearchBlocked(f"CANDLE_{field.upper()}_INVALID") from exc
    if not math.isfinite(result):
        raise ResearchBlocked(f"CANDLE_{field.upper()}_INVALID")
    return result


def _candle(raw: Mapping[str, Any], instrument: str, granularity: str) -> Candle:
    if raw.get("complete") is not True:
        raise ResearchBlocked("INCOMPLETE_CANDLE_IN_FROZEN_BATCH")
    bid = raw.get("bid")
    ask = raw.get("ask")
    if not isinstance(bid, Mapping) or not isinstance(ask, Mapping):
        raise ResearchBlocked("CANDLE_BID_ASK_MISSING")
    values = {f"bid_{key}": _number(bid.get(key), f"bid_{key}") for key in "ohlc"}
    values.update({f"ask_{key}": _number(ask.get(key), f"ask_{key}") for key in "ohlc"})
    if values["bid_h"] < max(values["bid_o"], values["bid_l"], values["bid_c"]) or values["bid_l"] > min(values["bid_o"], values["bid_h"], values["bid_c"]):
        raise ResearchBlocked("CANDLE_BID_OHLC_INVALID")
    if values["ask_h"] < max(values["ask_o"], values["ask_l"], values["ask_c"]) or values["ask_l"] > min(values["ask_o"], values["ask_h"], values["ask_c"]):
        raise ResearchBlocked("CANDLE_ASK_OHLC_INVALID")
    if any(values[f"ask_{key}"] < values[f"bid_{key}"] for key in "ohlc"):
        raise ResearchBlocked("CANDLE_NEGATIVE_SPREAD")
    return Candle(time=parse_utc(str(raw.get("time"))), instrument=instrument, granularity=granularity, **values)


def iter_series(dataset: Mapping[str, Any], instrument: str, granularity: str) -> Iterator[Candle]:
    inventory = dataset["inventory"]
    source_root = Path(dataset["source_root"])
    batches = sorted(
        (item for item in inventory["file_inventory"] if item.get("role") == "batch" and item.get("instrument") == instrument and item.get("granularity") == granularity),
        key=lambda item: int(item["batch_number"]),
    )
    if not batches or [int(item["batch_number"]) for item in batches] != list(range(len(batches))):
        raise ResearchBlocked(f"BATCH_CONTINUITY_FAILED:{instrument}:{granularity}")
    previous: datetime | None = None
    for item in batches:
        path = source_root / item["relative_path"]
        document = load_json(path)
        if document.get("instrument") != instrument or document.get("granularity") != granularity:
            raise ResearchBlocked(f"BATCH_CONTAMINATION:{item['relative_path']}")
        candles = document.get("candles")
        if not isinstance(candles, list) or len(candles) != document.get("candle_count"):
            raise ResearchBlocked(f"BATCH_CANDLE_COUNT_MISMATCH:{item['relative_path']}")
        for raw in candles:
            candle = _candle(raw, instrument, granularity)
            if previous is not None and candle.time <= previous:
                raise ResearchBlocked(f"CANDLE_ORDER_OR_DUPLICATE:{instrument}:{granularity}:{stamp(candle.time)}")
            previous = candle.time
            yield candle


def _atr(history: Sequence[Candle], length: int = 14) -> float | None:
    if len(history) < length + 1:
        return None
    total = 0.0
    for index in range(len(history) - length, len(history)):
        current, prior = history[index], history[index - 1]
        total += max(current.mid_h - current.mid_l, abs(current.mid_h - prior.mid_c), abs(current.mid_l - prior.mid_c))
    value = total / length
    return value if value > 0 else None


def signal_for(candidate: Candidate, history: Sequence[Candle]) -> str | None:
    required = candidate.slow_lookback * 4 + 2 if candidate.family == "MULTI_TIMEFRAME_CONFIRMATION" else candidate.slow_lookback + 2
    if len(history) < required:
        return None
    close = history[-1].mid_c
    prior_close = history[-2].mid_c
    recent = history[-candidate.lookback - 1:-1]
    slow = history[-candidate.slow_lookback:]
    recent_high = max(item.mid_h for item in recent)
    recent_low = min(item.mid_l for item in recent)
    fast_mean = sum(item.mid_c for item in history[-candidate.lookback:]) / candidate.lookback
    prior_fast = sum(item.mid_c for item in history[-candidate.lookback - 1:-1]) / candidate.lookback
    slow_mean = sum(item.mid_c for item in slow) / candidate.slow_lookback
    atr = _atr(history)
    if not atr:
        return None
    family = candidate.family
    if family == "TREND_CONTINUATION":
        return "LONG" if close > fast_mean > slow_mean and fast_mean > prior_fast else "SHORT" if close < fast_mean < slow_mean and fast_mean < prior_fast else None
    if family == "PULLBACK":
        return "LONG" if fast_mean > slow_mean and prior_close <= prior_fast and close > fast_mean else "SHORT" if fast_mean < slow_mean and prior_close >= prior_fast and close < fast_mean else None
    if family == "BREAKOUT":
        return "LONG" if close > recent_high else "SHORT" if close < recent_low else None
    if family == "MOMENTUM":
        move = (close - history[-candidate.lookback].mid_c) / atr
        return "LONG" if move > candidate.threshold else "SHORT" if move < -candidate.threshold else None
    if family == "VOLATILITY_EXPANSION":
        ranges = [item.mid_h - item.mid_l for item in recent]
        baseline = sum(ranges) / len(ranges)
        current_range = history[-1].mid_h - history[-1].mid_l
        if baseline <= 0 or current_range < baseline * candidate.threshold:
            return None
        return "LONG" if close > fast_mean else "SHORT" if close < fast_mean else None
    if family == "SESSION_BREAKOUT":
        if history[-1].time.hour < 7 or history[-1].time.hour >= 16:
            return None
        return "LONG" if close > recent_high else "SHORT" if close < recent_low else None
    if family == "MEAN_REVERSION":
        variance = sum((item.mid_c - fast_mean) ** 2 for item in history[-candidate.lookback:]) / candidate.lookback
        deviation = math.sqrt(variance)
        if deviation <= 0:
            return None
        z = (close - fast_mean) / deviation
        return "SHORT" if z > candidate.threshold else "LONG" if z < -candidate.threshold else None
    if family == "MULTI_TIMEFRAME_CONFIRMATION":
        start = len(history) - candidate.slow_lookback * 4 + 3
        higher = [history[index].mid_c for index in range(start, len(history), 4)]
        if len(higher) < candidate.slow_lookback:
            return None
        higher_slow = sum(higher[-candidate.slow_lookback:]) / candidate.slow_lookback
        prior_higher = higher[:-1]
        higher_old = sum(prior_higher[-candidate.slow_lookback:]) / candidate.slow_lookback if len(prior_higher) >= candidate.slow_lookback else higher_slow
        return "LONG" if close > fast_mean > higher_slow and higher_slow >= higher_old else "SHORT" if close < fast_mean < higher_slow and higher_slow <= higher_old else None
    raise ResearchBlocked(f"UNKNOWN_CANDIDATE_FAMILY:{family}")


def _nth_sunday(year: int, month: int, occurrence: int) -> int:
    sundays = [week[calendar.SUNDAY] for week in calendar.monthcalendar(year, month) if week[calendar.SUNDAY]]
    return sundays[occurrence - 1]


def _eastern_offset_at(at_utc: datetime) -> timedelta:
    """Return the U.S. Eastern offset without requiring an OS tz database."""
    at_utc = at_utc.astimezone(timezone.utc)
    start = datetime(at_utc.year, 3, _nth_sunday(at_utc.year, 3, 2), 7, tzinfo=timezone.utc)
    end = datetime(at_utc.year, 11, _nth_sunday(at_utc.year, 11, 1), 6, tzinfo=timezone.utc)
    return timedelta(hours=-4 if start <= at_utc < end else -5)


def _crosses_new_york_rollover(entry: datetime, exit_limit: datetime) -> bool:
    entry = entry.astimezone(timezone.utc)
    exit_limit = exit_limit.astimezone(timezone.utc)
    local_start = (entry + _eastern_offset_at(entry)).date()
    local_end = (exit_limit + _eastern_offset_at(exit_limit)).date()
    day = local_start
    while day <= local_end:
        probe = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
        boundary = datetime(day.year, day.month, day.day, 17, tzinfo=timezone.utc) - _eastern_offset_at(probe)
        if entry < boundary <= exit_limit:
            return True
        day += timedelta(days=1)
    return False


def _fold_index(at: datetime) -> int:
    start, end = parse_utc(REQUESTED_START), parse_utc(DEVELOPMENT_END)
    if at < start or at >= end:
        return -1
    return min(5, int((at - start) / ((end - start) / 6)))


def _spread_extra(candle: Candle, multiplier: float, component: str) -> float:
    spread = max(0.0, getattr(candle, f"ask_{component}") - getattr(candle, f"bid_{component}"))
    return spread * max(0.0, multiplier - 1.0) / 2.0


def _trade_result(position: Position, candle: Candle, slippage: float, spread_multiplier: float) -> tuple[float, str] | None:
    if position.direction == "LONG":
        stop_hit = candle.bid_l - slippage - _spread_extra(candle, spread_multiplier, "l") <= position.stop
        target_hit = candle.bid_h - slippage - _spread_extra(candle, spread_multiplier, "h") >= position.target
        if stop_hit:
            return (position.stop - position.entry) / position.risk, "STOP"
        if target_hit:
            return (position.target - position.entry) / position.risk, "TARGET"
    else:
        stop_hit = candle.ask_h + slippage + _spread_extra(candle, spread_multiplier, "h") >= position.stop
        target_hit = candle.ask_l + slippage + _spread_extra(candle, spread_multiplier, "l") <= position.target
        if stop_hit:
            return (position.entry - position.stop) / position.risk, "STOP"
        if target_hit:
            return (position.entry - position.target) / position.risk, "TARGET"
    return None


def _trade_record(position: Position, candle: Candle, r_value: float, reason: str, split: str, cost_case: str) -> dict[str, Any]:
    return {
        "candidate_id": position.candidate_id, "instrument": position.instrument,
        "direction": position.direction, "signal_time": stamp(position.signal_time),
        "entry_time": stamp(position.entry_time), "exit_time": stamp(candle.time),
        "r": round(r_value, 10), "reason": reason, "split": split,
        "development_fold": _fold_index(position.signal_time), "cost_case": cost_case,
        "session": position.session, "regime": position.regime,
    }


def _session(at: datetime) -> str:
    hour = at.hour
    return "ASIA" if hour < 7 else "LONDON" if hour < 13 else "NEW_YORK" if hour < 21 else "ROLLOVER_WINDOW"


def _regime(history: Sequence[Candle]) -> str:
    current = _atr(history)
    if current is None or len(history) < 45:
        return "UNKNOWN"
    ranges = [item.mid_h - item.mid_l for item in history[-45:-1]]
    baseline = sum(ranges) / len(ranges) if ranges else 0.0
    if baseline <= 0:
        return "UNKNOWN"
    ratio = current / baseline
    return "LOW_VOLATILITY" if ratio < 0.75 else "HIGH_VOLATILITY" if ratio > 1.35 else "NORMAL_VOLATILITY"


def _eligible_signal_split(candidate: Candidate, at: datetime) -> str | None:
    development_start = parse_utc(REQUESTED_START)
    development_end = parse_utc(DEVELOPMENT_END)
    validation_end = parse_utc(VALIDATION_END)
    seconds = GRANULARITY_SECONDS[candidate.granularity]
    lookback_bars = candidate.slow_lookback * 4 if candidate.family == "MULTI_TIMEFRAME_CONFIRMATION" else candidate.slow_lookback
    embargo = timedelta(seconds=seconds * (lookback_bars + candidate.max_holding_bars))
    holding = timedelta(seconds=seconds * candidate.max_holding_bars)
    if development_start + embargo <= at and at + holding < development_end:
        return "development"
    if development_end + embargo <= at and at + holding < validation_end:
        return "phase1_validation"
    return None


def _evaluate_series_cases(candles: Iterable[Candle], candidates: Sequence[Candidate],
                           cost_cases: Sequence[tuple[str, float, float]]) -> tuple[list[dict[str, Any]], int]:
    """Evaluate all cost cases in one chronological streaming pass."""
    if not candidates:
        count = sum(1 for item in candles if item.time < parse_utc(VALIDATION_END))
        return [], count
    max_history = max(item.slow_lookback * 4 if item.family == "MULTI_TIMEFRAME_CONFIRMATION" else item.slow_lookback for item in candidates) + 2
    history: deque[Candle] = deque(maxlen=max_history)
    pending: dict[tuple[str, str], tuple[str, datetime, float, str, str, str]] = {}
    positions: dict[tuple[str, str], Position] = {}
    trades: list[dict[str, Any]] = []
    count = 0
    cadence = max(1, 300 // GRANULARITY_SECONDS[candidates[0].granularity])
    for candle in candles:
        if candle.time >= parse_utc(VALIDATION_END):
            break
        count += 1
        for candidate in candidates:
            for cost_case, slippage, spread_multiplier in cost_cases:
                key = (candidate.candidate_id, cost_case)
                queued = pending.pop(key, None)
                if queued and key not in positions:
                    direction, signal_time, atr, signal_split, signal_session, signal_regime = queued
                    limit = candle.time + timedelta(seconds=GRANULARITY_SECONDS[candidate.granularity] * candidate.max_holding_bars)
                    if not _crosses_new_york_rollover(candle.time, limit):
                        extra = _spread_extra(candle, spread_multiplier, "o")
                        entry = candle.ask_o + slippage + extra if direction == "LONG" else candle.bid_o - slippage - extra
                        risk = atr * candidate.stop_atr
                        positions[key] = Position(
                            candidate.candidate_id, candle.instrument, direction, signal_time, candle.time, entry,
                            entry - risk if direction == "LONG" else entry + risk,
                            entry + candidate.target_r * risk if direction == "LONG" else entry - candidate.target_r * risk,
                            risk, signal_split, signal_session, signal_regime,
                        )
                position = positions.get(key)
                if position:
                    position.bars += 1
                    result = _trade_result(position, candle, slippage, spread_multiplier)
                    if result is None and position.bars >= candidate.max_holding_bars:
                        extra = _spread_extra(candle, spread_multiplier, "c")
                        exit_price = candle.bid_c - slippage - extra if position.direction == "LONG" else candle.ask_c + slippage + extra
                        result = (((exit_price - position.entry) if position.direction == "LONG" else (position.entry - exit_price)) / position.risk, "TIME")
                    if result is not None:
                        trades.append(_trade_record(position, candle, result[0], result[1], position.split, cost_case))
                        del positions[key]
        history.append(candle)
        if count % cadence:
            continue
        snapshot = list(history)
        for candidate in candidates:
            direction = signal_for(candidate, snapshot)
            atr = _atr(snapshot)
            signal_split = _eligible_signal_split(candidate, candle.time)
            if direction in candidate.directions and atr and signal_split:
                signal_session = _session(candle.time)
                signal_regime = _regime(snapshot)
                for cost_case, _slippage, _spread_multiplier in cost_cases:
                    key = (candidate.candidate_id, cost_case)
                    if key not in pending and key not in positions:
                        pending[key] = (direction, candle.time, atr, signal_split, signal_session, signal_regime)
    return trades, count


def evaluate_series(candles: Iterable[Candle], candidates: Sequence[Candidate], *, slippage: float, cost_case: str) -> tuple[list[dict[str, Any]], int]:
    """Evaluate one cost case; retained as a focused-test/public primitive."""
    return _evaluate_series_cases(candles, candidates, ((cost_case, slippage, 1.0),))


def metrics(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(trades, key=lambda item: (item["exit_time"], item["instrument"], item["candidate_id"]))
    values = [float(item["r"]) for item in ordered]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    equity = peak = 1.0
    max_drawdown = 0.0
    for value in values:
        equity *= max(0.000001, 1.0 + RISK_FRACTION * value)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak * 100.0)
    pairs: dict[str, int] = defaultdict(int)
    directions: dict[str, int] = defaultdict(int)
    folds: dict[int, list[float]] = defaultdict(list)
    for item in ordered:
        pairs[str(item["instrument"])] += 1
        directions[str(item["direction"])] += 1
        if int(item["development_fold"]) >= 0:
            folds[int(item["development_fold"])].append(float(item["r"]))
    total = len(values)
    pf = sum(wins) / abs(sum(losses)) if losses else (999999.0 if wins else 0.0)
    largest = max(values, default=0.0)
    return {
        "trade_count": total, "long_trades": directions["LONG"], "short_trades": directions["SHORT"],
        "instrument_count": len(pairs), "pair_counts": dict(sorted(pairs.items())),
        "largest_pair_share": max(pairs.values(), default=0) / total if total else 0.0,
        "expectancy_r": sum(values) / total if total else 0.0, "net_r": sum(values),
        "profit_factor": pf, "maximum_drawdown_pct": max_drawdown,
        "largest_trade_r": largest, "expectancy_without_largest_trade_r": (sum(values) - largest) / (total - 1) if total > 1 else 0.0,
        "positive_development_folds": sum(1 for values_ in folds.values() if values_ and sum(values_) / len(values_) > 0),
        "development_fold_trade_counts": {str(key): len(value) for key, value in sorted(folds.items())},
    }


def aggregate_trades(trades: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Compact one-series trades into restart-safe sufficient statistics."""
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for trade in trades:
        key = f"{trade['candidate_id']}|{trade['cost_case']}|{trade['split']}"
        grouped[key].append(trade)
    compact: dict[str, dict[str, Any]] = {}
    for key, rows in grouped.items():
        values = [float(item["r"]) for item in rows]
        pair = str(rows[0]["instrument"])
        fold_counts: dict[str, int] = defaultdict(int)
        fold_sums: dict[str, float] = defaultdict(float)
        for item in rows:
            fold = int(item["development_fold"])
            if fold >= 0:
                fold_counts[str(fold)] += 1
                fold_sums[str(fold)] += float(item["r"])
        metric = metrics(rows)
        compact[key] = {
            "trade_count": len(rows),
            "long_trades": sum(item["direction"] == "LONG" for item in rows),
            "short_trades": sum(item["direction"] == "SHORT" for item in rows),
            "pair_counts": {pair: len(rows)},
            "sum_r": sum(values), "gross_win_r": sum(value for value in values if value > 0),
            "gross_loss_r": sum(value for value in values if value < 0),
            "largest_trade_r": max(values, default=0.0),
            "fold_counts": dict(fold_counts), "fold_sums": dict(fold_sums),
            "series_drawdowns_pct": {pair: metric["maximum_drawdown_pct"]},
            "direction_stats": {}, "session_stats": {}, "regime_stats": {},
        }
        dimensions = (
            ("direction_stats", "direction", ("LONG", "SHORT")),
            ("session_stats", "session", ("ASIA", "LONDON", "NEW_YORK", "ROLLOVER_WINDOW")),
            ("regime_stats", "regime", ("LOW_VOLATILITY", "NORMAL_VOLATILITY", "HIGH_VOLATILITY", "UNKNOWN")),
        )
        for output_field, source_field, names in dimensions:
            for name in names:
                selected = [float(item["r"]) for item in rows if item.get(source_field) == name]
                compact[key][output_field][name] = {
                    "count": len(selected), "sum_r": sum(selected),
                    "gross_win_r": sum(item for item in selected if item > 0),
                    "gross_loss_r": sum(item for item in selected if item < 0),
                }
    return compact


def merge_aggregates(target: dict[str, dict[str, Any]], addition: Mapping[str, Mapping[str, Any]]) -> None:
    for key, incoming in addition.items():
        if key not in target:
            target[key] = json.loads(json.dumps(incoming))
            continue
        current = target[key]
        for field in ("trade_count", "long_trades", "short_trades"):
            current[field] += int(incoming[field])
        for field in ("sum_r", "gross_win_r", "gross_loss_r"):
            current[field] += float(incoming[field])
        current["largest_trade_r"] = max(float(current["largest_trade_r"]), float(incoming["largest_trade_r"]))
        for field in ("pair_counts", "fold_counts"):
            for name, value in incoming[field].items():
                current[field][name] = current[field].get(name, 0) + int(value)
        for name, value in incoming["fold_sums"].items():
            current["fold_sums"][name] = current["fold_sums"].get(name, 0.0) + float(value)
        current["series_drawdowns_pct"].update(incoming["series_drawdowns_pct"])
        for field in ("direction_stats", "session_stats", "regime_stats"):
            for name, stats in incoming[field].items():
                current[field].setdefault(name, {"count": 0, "sum_r": 0.0, "gross_win_r": 0.0, "gross_loss_r": 0.0})
                for metric_name in ("count", "sum_r", "gross_win_r", "gross_loss_r"):
                    current[field][name][metric_name] += stats[metric_name]


def metrics_from_aggregate(value: Mapping[str, Any] | None) -> dict[str, Any]:
    value = value or {}
    total = int(value.get("trade_count", 0))
    pair_counts = dict(value.get("pair_counts", {}))
    sum_r = float(value.get("sum_r", 0.0))
    largest = float(value.get("largest_trade_r", 0.0))
    gross_loss = float(value.get("gross_loss_r", 0.0))
    fold_counts = dict(value.get("fold_counts", {}))
    fold_sums = dict(value.get("fold_sums", {}))
    # Adding each instrument's peak-to-trough drawdown is conservative: it
    # assumes their worst paths coincide instead of granting diversification.
    conservative_drawdown = min(100.0, sum(float(item) for item in value.get("series_drawdowns_pct", {}).values()))
    def grouped_metrics(field: str) -> dict[str, Any]:
        output = {}
        for name, stats in value.get(field, {}).items():
            count = int(stats["count"])
            loss = float(stats["gross_loss_r"])
            output[name] = {
                "trade_count": count,
                "expectancy_r": float(stats["sum_r"]) / count if count else 0.0,
                "profit_factor": float(stats["gross_win_r"]) / abs(loss) if loss else (999999.0 if float(stats["gross_win_r"]) > 0 else 0.0),
            }
        return output
    return {
        "trade_count": total, "long_trades": int(value.get("long_trades", 0)),
        "short_trades": int(value.get("short_trades", 0)), "instrument_count": len(pair_counts),
        "pair_counts": dict(sorted(pair_counts.items())),
        "largest_pair_share": max(pair_counts.values(), default=0) / total if total else 0.0,
        "expectancy_r": sum_r / total if total else 0.0, "net_r": sum_r,
        "profit_factor": float(value.get("gross_win_r", 0.0)) / abs(gross_loss) if gross_loss else (999999.0 if sum_r > 0 else 0.0),
        "maximum_drawdown_pct": conservative_drawdown, "drawdown_policy": "SUM_OF_PER_INSTRUMENT_MAX_DRAWDOWNS_CONSERVATIVE",
        "largest_trade_r": largest,
        "expectancy_without_largest_trade_r": (sum_r - largest) / (total - 1) if total > 1 else 0.0,
        "positive_development_folds": sum(1 for key, count in fold_counts.items() if count and float(fold_sums.get(key, 0.0)) / count > 0),
        "development_fold_trade_counts": dict(sorted(fold_counts.items())),
        "direction_metrics": grouped_metrics("direction_stats"),
        "session_metrics": grouped_metrics("session_stats"),
        "regime_metrics": grouped_metrics("regime_stats"),
    }


def _gate(metric: Mapping[str, Any], *, require_folds: bool) -> tuple[bool, list[str]]:
    reasons = []
    checks = (
        (metric["trade_count"] >= 200, "TRADE_COUNT_BELOW_200"),
        (metric["long_trades"] >= 50, "LONG_TRADE_COUNT_BELOW_50"),
        (metric["short_trades"] >= 50, "SHORT_TRADE_COUNT_BELOW_50"),
        (metric["instrument_count"] >= 2, "INSTRUMENT_COUNT_BELOW_2"),
        (metric["expectancy_r"] > 0, "EXPECTANCY_NOT_POSITIVE"),
        (metric["profit_factor"] >= 1.10, "PROFIT_FACTOR_BELOW_1_10"),
        (metric["maximum_drawdown_pct"] <= 10.0, "DRAWDOWN_ABOVE_10_PERCENT"),
        (metric["largest_pair_share"] <= 0.60, "PAIR_CONCENTRATION_ABOVE_60_PERCENT"),
        (metric["expectancy_without_largest_trade_r"] > 0, "SINGLE_TRADE_DEPENDENCE"),
    )
    reasons.extend(reason for passed, reason in checks if not passed)
    for direction in ("LONG", "SHORT"):
        direction_metric = metric.get("direction_metrics", {}).get(direction, {})
        if direction_metric.get("trade_count", 0) >= 50 and direction_metric.get("expectancy_r", 0.0) <= 0:
            reasons.append(f"{direction}_EXPECTANCY_NOT_POSITIVE")
        if direction_metric.get("trade_count", 0) >= 50 and direction_metric.get("profit_factor", 0.0) < 1.10:
            reasons.append(f"{direction}_PROFIT_FACTOR_BELOW_1_10")
    if require_folds and metric["positive_development_folds"] < 4:
        reasons.append("FEWER_THAN_FOUR_POSITIVE_DEVELOPMENT_FOLDS")
    return not reasons, reasons


def summarize_results(candidates: Sequence[Candidate], trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_candidate: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for trade in trades:
        by_candidate[str(trade["candidate_id"])].append(trade)
    results: dict[str, Any] = {}
    for candidate in candidates:
        own = by_candidate[candidate.candidate_id]
        result: dict[str, Any] = {"definition": asdict(candidate)}
        for cost_case in ("base", "stress"):
            for split in ("development", "phase1_validation"):
                subset = [item for item in own if item["cost_case"] == cost_case and item["split"] == split]
                metric = metrics(subset)
                passed, reasons = _gate(metric, require_folds=(split == "development"))
                result[f"{cost_case}_{split}"] = {"metrics": metric, "pass": passed, "rejection_reasons": reasons}
        results[candidate.candidate_id] = result
    for candidate in candidates:
        result = results[candidate.candidate_id]
        siblings = [results[item.candidate_id] for item in candidates if item.family == candidate.family and item.candidate_id != candidate.candidate_id]
        neighbors = sum(1 for item in siblings if item["base_development"]["pass"] and item["base_phase1_validation"]["pass"])
        cost_pass = result["base_development"]["pass"] and result["base_phase1_validation"]["pass"] and result["stress_development"]["pass"] and result["stress_phase1_validation"]["pass"]
        result["neighboring_parameter_pass_count"] = neighbors
        result["parameter_stability_pass"] = neighbors >= 1
        result["cost_stress_pass"] = result["stress_development"]["pass"] and result["stress_phase1_validation"]["pass"]
        result["phase1_pass"] = cost_pass and result["parameter_stability_pass"]
        rejection = []
        for key in ("base_development", "base_phase1_validation", "stress_development", "stress_phase1_validation"):
            rejection.extend(f"{key.upper()}:{reason}" for reason in result[key]["rejection_reasons"])
        if not result["parameter_stability_pass"]:
            rejection.append("PARAMETER_NEIGHBOR_STABILITY_FAILED")
        result["rejection_reasons"] = sorted(set(rejection))
    return results


def summarize_aggregates(candidates: Sequence[Candidate], aggregates: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for candidate in candidates:
        result: dict[str, Any] = {"definition": asdict(candidate)}
        for cost_case in ("base", "stress"):
            for split in ("development", "phase1_validation"):
                metric = metrics_from_aggregate(aggregates.get(f"{candidate.candidate_id}|{cost_case}|{split}"))
                passed, reasons = _gate(metric, require_folds=(split == "development"))
                result[f"{cost_case}_{split}"] = {"metrics": metric, "pass": passed, "rejection_reasons": reasons}
        results[candidate.candidate_id] = result
    for candidate in candidates:
        result = results[candidate.candidate_id]
        siblings = [results[item.candidate_id] for item in candidates if item.family == candidate.family and item.candidate_id != candidate.candidate_id]
        neighbors = sum(1 for item in siblings if item["base_development"]["pass"] and item["base_phase1_validation"]["pass"])
        result["neighboring_parameter_pass_count"] = neighbors
        result["parameter_stability_pass"] = neighbors >= 1
        result["cost_stress_pass"] = result["stress_development"]["pass"] and result["stress_phase1_validation"]["pass"]
        result["phase1_pass"] = all((result["base_development"]["pass"], result["base_phase1_validation"]["pass"], result["cost_stress_pass"], result["parameter_stability_pass"]))
        rejection = []
        for key in ("base_development", "base_phase1_validation", "stress_development", "stress_phase1_validation"):
            rejection.extend(f"{key.upper()}:{reason}" for reason in result[key]["rejection_reasons"])
        if not result["parameter_stability_pass"]:
            rejection.append("PARAMETER_NEIGHBOR_STABILITY_FAILED")
        result["rejection_reasons"] = sorted(set(rejection))
    return results


def _checkpoint_valid(checkpoint: Mapping[str, Any], contract_hash: str, registry_hash: str) -> bool:
    return all((
        checkpoint.get("schema") == f"{SCHEMA}.checkpoint",
        checkpoint.get("dataset_sha256") == DATASET_SHA256,
        checkpoint.get("source_state_sha256") == SOURCE_STATE_SHA256,
        checkpoint.get("contract_sha256") == contract_hash,
        checkpoint.get("candidate_registry_sha256") == registry_hash,
        isinstance(checkpoint.get("completed_series"), list),
        isinstance(checkpoint.get("aggregates"), Mapping),
    ))


def _checkpoint_identity_matches(checkpoint: Mapping[str, Any], contract_hash: str, registry_hash: str) -> bool:
    return all((
        checkpoint.get("schema") == f"{SCHEMA}.checkpoint",
        checkpoint.get("dataset_sha256") == DATASET_SHA256,
        checkpoint.get("source_state_sha256") == SOURCE_STATE_SHA256,
        checkpoint.get("contract_sha256") == contract_hash,
        checkpoint.get("candidate_registry_sha256") == registry_hash,
    ))


def _report(state: Mapping[str, Any]) -> str:
    return "\n".join((
        "# AIOS Forex Frozen 21-Series Edge Research V1", "",
        f"- Status: `{state['status']}`",
        f"- Dataset: `{state['dataset_id']}`",
        f"- Dataset SHA-256: `{state['dataset_sha256']}`",
        f"- Series processed: {state['series_processed']}/21",
        f"- Candles streamed before the sealed holdout: {state['candles_streamed']}",
        f"- Candidate registry: {state['candidate_count']}",
        f"- Phase 1 survivors: {state['survivor_count']}",
        "- Final holdout: SEALED; not evaluated in Phase 1",
        "- PAPER, Practice, LIVE, broker, credential, and money activity: NONE",
        "- A survivor is research evidence only, not proof of profit.", "",
    ))


def run_phase1(*, dataset_root: Path, output_root: Path, state_path: Path, report_path: Path,
               source_head: str = EXPECTED_HEAD, verify_files: bool = True,
               max_series: int | None = None, progress: Any = None,
               restart_invalid_checkpoint: bool = False) -> dict[str, Any]:
    contract = build_contract(source_head=source_head)
    if source_head != EXPECTED_HEAD:
        raise ResearchBlocked("SOURCE_HEAD_MISMATCH")
    dataset = verify_frozen_dataset(dataset_root, verify_files=verify_files)
    candidates = build_candidates()
    registry = [asdict(item) for item in candidates]
    registry_hash = canonical_sha256(registry)
    contract_hash = canonical_sha256(contract)
    output_root.mkdir(parents=True, exist_ok=True)
    contract_path = output_root / "AIOS_FOREX_PHASE1_RESEARCH_CONTRACT.json"
    registry_path = output_root / "AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json"
    results_path = output_root / "AIOS_FOREX_PHASE1_RESULTS.json"
    checkpoint_path = output_root / "AIOS_FOREX_PHASE1_CHECKPOINT.json"
    receipt_path = output_root / "AIOS_FOREX_PHASE1_RECEIPT.json"
    atomic_json(contract_path, contract)
    atomic_json(registry_path, {"schema": f"{SCHEMA}.registry", "candidate_registry_sha256": registry_hash, "candidates": registry})
    completed: list[str] = []
    aggregates: dict[str, dict[str, Any]] = {}
    candles_streamed = 0
    if checkpoint_path.exists():
        if restart_invalid_checkpoint:
            atomic_json(checkpoint_path, {
                "schema": f"{SCHEMA}.checkpoint", "dataset_sha256": DATASET_SHA256,
                "source_state_sha256": SOURCE_STATE_SHA256, "contract_sha256": contract_hash,
                "candidate_registry_sha256": registry_hash, "completed_series": [],
                "candles_streamed": 0, "aggregates": {}, "restart_reason": "AUTHORIZED_CODE_REPAIR",
            })
        else:
            checkpoint = load_json(checkpoint_path)
            if checkpoint.get("status") == "TERMINAL" and _checkpoint_identity_matches(checkpoint, contract_hash, registry_hash):
                if results_path.is_file() and checkpoint.get("results_sha256") == sha256_file(results_path) and state_path.is_file():
                    existing = load_json(state_path)
                    if existing.get("dataset_sha256") == DATASET_SHA256 and existing.get("contract_sha256") == contract_hash:
                        return existing
                raise ResearchBlocked("TERMINAL_CHECKPOINT_EVIDENCE_MISMATCH")
            if not _checkpoint_valid(checkpoint, contract_hash, registry_hash):
                raise ResearchBlocked("CHECKPOINT_IDENTITY_DRIFT")
            completed = list(checkpoint["completed_series"])
            aggregates = dict(checkpoint["aggregates"])
            candles_streamed = int(checkpoint.get("candles_streamed", 0))
    series_inventory = sorted(dataset["inventory"]["series_inventory"], key=lambda item: (item["instrument"], item["granularity"]))
    if max_series is not None:
        series_inventory = series_inventory[:max_series]
    by_granularity: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_granularity[candidate.granularity].append(candidate)
    for item in series_inventory:
        key = f"{item['instrument']}/{item['granularity']}"
        if key in completed:
            continue
        series_trades, count = _evaluate_series_cases(
            iter_series(dataset, item["instrument"], item["granularity"]),
            by_granularity[item["granularity"]], (("base", 0.00001, 1.0), ("stress", 0.00003, 1.5)),
        )
        merge_aggregates(aggregates, aggregate_trades(series_trades))
        candles_streamed += count
        completed.append(key)
        atomic_json(checkpoint_path, {
            "schema": f"{SCHEMA}.checkpoint", "dataset_sha256": DATASET_SHA256,
            "source_state_sha256": SOURCE_STATE_SHA256, "contract_sha256": contract_hash,
            "candidate_registry_sha256": registry_hash, "completed_series": completed,
            "candles_streamed": candles_streamed, "aggregates": aggregates,
        })
        if progress:
            progress(key, len(completed), len(series_inventory), candles_streamed)
    candidate_results = summarize_aggregates(candidates, aggregates)
    survivors = sorted(key for key, value in candidate_results.items() if value["phase1_pass"])
    complete_run = len(completed) == 21 and max_series is None
    status = "PHASE1_CANDIDATES_READY_FOR_PHASE2" if survivors and complete_run else "PHASE1_EXHAUSTED_NO_CANDIDATE" if complete_run else "BLOCKED"
    results = {
        "schema": f"{SCHEMA}.results", "status": status, "dataset_id": DATASET_ID,
        "dataset_sha256": DATASET_SHA256, "contract_sha256": contract_hash,
        "candidate_registry_sha256": registry_hash, "series_processed": len(completed),
        "candles_streamed": candles_streamed, "candidate_results": candidate_results,
        "survivors": survivors, "sealed_holdout_status": "NOT_EVALUATED",
    }
    atomic_json(results_path, results)
    atomic_json(checkpoint_path, {
        "schema": f"{SCHEMA}.checkpoint", "status": "TERMINAL",
        "dataset_sha256": DATASET_SHA256, "source_state_sha256": SOURCE_STATE_SHA256,
        "contract_sha256": contract_hash, "candidate_registry_sha256": registry_hash,
        "completed_series": completed, "candles_streamed": candles_streamed,
        "aggregate_key_count": len(aggregates), "results_sha256": sha256_file(results_path),
    })
    receipt = {
        "schema": f"{SCHEMA}.receipt", "status": status, "packet_id": "PKT-FOREX-004",
        "execution_boundary_id": "PKT-FOREX-004-FROZEN-21-SERIES-PHASE1-001",
        "dataset_id": DATASET_ID, "dataset_sha256": DATASET_SHA256,
        "source_state_sha256": SOURCE_STATE_SHA256, "manifest_sha256": MANIFEST_SHA256,
        "scope_fingerprint": SCOPE_FINGERPRINT, "source_head": source_head,
        "contract_sha256": contract_hash, "candidate_registry_sha256": registry_hash,
        "results_sha256": sha256_file(results_path), "series_processed": len(completed),
        "candles_streamed": candles_streamed, "candidate_count": len(candidates),
        "survivor_count": len(survivors), "survivors": survivors,
        "sealed_holdout_status": "NOT_EVALUATED", "reproduction_command": contract["reproduction_command"],
        "safety": {"network": False, "credentials": False, "collector": False, "paper": False, "live": False, "broker_write": False, "money_movement": False},
    }
    atomic_json(receipt_path, receipt)
    state = {
        **receipt, "schema": SCHEMA, "files_checked": dataset["files_checked"],
        "bytes_checked": dataset["bytes_checked"], "candidate_count": len(candidates),
        "survivor_count": len(survivors), "survivors": survivors,
        "results_path": str(results_path), "receipt_path": str(receipt_path),
    }
    atomic_json(state_path, state)
    atomic_text(report_path, _report(state))
    return state


__all__ = [
    "Candidate", "Candle", "ResearchBlocked", "build_candidates", "build_contract",
    "aggregate_trades", "canonical_sha256", "evaluate_series", "iter_series", "merge_aggregates",
    "metrics", "metrics_from_aggregate", "run_phase1",
    "signal_for", "summarize_results", "verify_frozen_dataset",
]
