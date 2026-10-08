"""Frozen Stage-1 screen for abnormal OANDA price-update-count response.

Only development candles before 2025-04-01 are read.  Validation and final
holdout data are fail-closed.  The provider field is treated as a count of
prices created, never as traded or notional volume.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import itertools
import json
import math
import random
import sqlite3
import statistics
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable


PACKET_ID = "PKT-FOREX-030"
FAMILY = "ABNORMAL_OANDA_PRICE_UPDATE_COUNT_RESPONSE_V1"
CORPUS_ID = "AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2"
CORPUS_SHA256 = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
MANIFEST_SHA256 = "1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b"
PREREG_SHA256 = "103e228952ad73d2921ddbaadf031d3af0ba174ecd044be4ed7bc0ce57871d16"
DEV_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
SCORE_START = datetime(2024, 4, 1, tzinfo=timezone.utc)
DEV_END = datetime(2025, 4, 1, tzinfo=timezone.utc)
HOLDOUT_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
FOLD_BOUNDARIES = (
    datetime(2024, 4, 1, tzinfo=timezone.utc),
    datetime(2024, 6, 1, tzinfo=timezone.utc),
    datetime(2024, 8, 1, tzinfo=timezone.utc),
    datetime(2024, 10, 1, tzinfo=timezone.utc),
    datetime(2024, 12, 1, tzinfo=timezone.utc),
    datetime(2025, 2, 1, tzinfo=timezone.utc),
    datetime(2025, 4, 1, tzinfo=timezone.utc),
)
RISK_FRACTION = 0.0005
PRIOR_ATTEMPTS = 1179
CANDIDATE_COUNT = 8
CUMULATIVE_ATTEMPTS = PRIOR_ATTEMPTS + CANDIDATE_COUNT
RANDOM_SEED = 29030
NO_TRADE_EXPECTANCY_R = 0.0
MINIMUM_MATCHED_CONTROL_COVERAGE = 0.80


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("_JPY") else 0.0001


def true_range(bar: dict[str, Any], previous_close: float | None) -> float:
    high = float(bar["mid"]["h"])
    low = float(bar["mid"]["l"])
    if previous_close is None:
        return high - low
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def robust_center_scale(history: Iterable[float]) -> tuple[float, float]:
    values = list(history)
    center = statistics.median(values)
    return center, 1.4826 * statistics.median(abs(item - center) for item in values)


def fold_index(moment: datetime) -> int:
    for index, (left, right) in enumerate(zip(FOLD_BOUNDARIES, FOLD_BOUNDARIES[1:])):
        if left <= moment < right:
            return index
    return -1


def in_embargo(moment: datetime) -> bool:
    distance = timedelta(minutes=30)
    return any(abs(moment - boundary) < distance for boundary in FOLD_BOUNDARIES)


def session_label(moment: datetime) -> str:
    if 7 <= moment.hour < 12:
        return "LONDON"
    if 12 <= moment.hour < 16:
        return "LONDON_NEW_YORK_OVERLAP"
    if 16 <= moment.hour < 21:
        return "NEW_YORK"
    return "ASIA_HANDOFF_OTHER"


def scenario_outcome(
    *, pair: str, bars: list[dict[str, Any]], signal_index: int,
    holding_bars: int, direction: str, atr: float, scenario: str,
) -> tuple[float, str, float, float, str, float, float, float, float]:
    entry_bar = bars[signal_index + 1]
    slippage_pips = {"gross": 0.0, "base": 0.1, "stress": 0.5}[scenario]
    slippage = pip_size(pair) * slippage_pips
    if direction == "LONG":
        entry = float(entry_bar["mid" if scenario == "gross" else "ask"]["o"]) + slippage
        stop = entry - atr
    else:
        entry = float(entry_bar["mid" if scenario == "gross" else "bid"]["o"]) - slippage
        stop = entry + atr
    exit_price = entry
    exit_reason = "TIME"
    exit_bar = entry_bar
    for offset in range(1, holding_bars + 1):
        bar = bars[signal_index + offset]
        side = "mid" if scenario == "gross" else ("bid" if direction == "LONG" else "ask")
        if direction == "LONG" and float(bar[side]["l"]) <= stop:
            exit_price = min(stop, float(bar[side]["o"])) - slippage
            exit_reason = "STOP"
            exit_bar = bar
            break
        if direction == "SHORT" and float(bar[side]["h"]) >= stop:
            exit_price = max(stop, float(bar[side]["o"])) + slippage
            exit_reason = "STOP"
            exit_bar = bar
            break
        if offset == holding_bars:
            exit_price = float(bar[side]["c"]) + (-slippage if direction == "LONG" else slippage)
            exit_bar = bar
    result_price = exit_price - entry if direction == "LONG" else entry - exit_price
    entry_spread_pips = (float(entry_bar["ask"]["o"]) - float(entry_bar["bid"]["o"])) / pip_size(pair)
    exit_spread_pips = (float(exit_bar["ask"]["c"]) - float(exit_bar["bid"]["c"])) / pip_size(pair)
    return (
        entry,
        timestamp_text(parse_timestamp(exit_bar["timestamp"]) + timedelta(minutes=5)),
        exit_price,
        stop,
        exit_reason,
        result_price / atr,
        result_price / pip_size(pair),
        entry_spread_pips,
        exit_spread_pips,
    )


def deterministic_random_direction(candidate_id: str, event_id: str) -> str:
    digest = hashlib.sha256(f"{RANDOM_SEED}:{candidate_id}:{event_id}".encode("ascii")).digest()
    return "LONG" if digest[0] & 1 else "SHORT"


def verify_preregistration(path: Path) -> dict[str, Any]:
    if sha256_file(path) != PREREG_SHA256:
        raise ValueError("PREREGISTRATION_SHA256_MISMATCH")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("strategy_id") != FAMILY or len(data.get("candidates", [])) != CANDIDATE_COUNT:
        raise ValueError("PREREGISTRATION_CONTENT_MISMATCH")
    if data["dataset"]["development_end_exclusive"] != timestamp_text(DEV_END):
        raise ValueError("DEVELOPMENT_BOUNDARY_MISMATCH")
    return data


def verify_manifest(corpus_root: Path) -> dict[str, Any]:
    manifest_path = corpus_root / "manifest.json"
    if sha256_file(manifest_path) != MANIFEST_SHA256:
        raise ValueError("MANIFEST_SHA256_MISMATCH")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("aggregate_corpus_fingerprint") != CORPUS_SHA256:
        raise ValueError("CORPUS_FINGERPRINT_MISMATCH")
    if len(manifest.get("eligible_pairs", [])) != 58:
        raise ValueError("PAIR_UNIVERSE_MISMATCH")
    return manifest


def development_artifacts(manifest: dict[str, Any], pair: str) -> list[dict[str, Any]]:
    return sorted(
        (
            item for item in manifest["artifacts"]
            if item["instrument"] == pair
            and parse_timestamp(item["start_utc"]) < DEV_END
            and parse_timestamp(item["end_utc"]) <= DEV_END
        ),
        key=lambda item: item["start_utc"],
    )


def read_pair_bars(
    corpus_root: Path, manifest: dict[str, Any], pair: str, verification: dict[str, Any]
) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    previous = ""
    for item in development_artifacts(manifest, pair):
        path = corpus_root / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
            raise ValueError(f"M5_PARTITION_MISMATCH:{item['path']}")
        verification[item["path"]] = {"bytes": item["bytes"], "sha256": item["sha256"], "status": "PASS"}
        with gzip.open(path, "rt", encoding="ascii") as handle:
            for line in handle:
                row = json.loads(line)
                moment = parse_timestamp(row.get("timestamp", ""))
                if moment >= DEV_END:
                    raise ValueError("VALIDATION_OR_LATER_ROW_REACHED")
                if moment >= HOLDOUT_START:
                    raise ValueError("FINAL_HOLDOUT_ROW_REACHED")
                if moment < DEV_START:
                    continue
                if row.get("instrument") != pair or row.get("complete") is not True or row["timestamp"] <= previous:
                    raise ValueError(f"MALFORMED_OR_NONCHRONOLOGICAL_ROW:{pair}")
                if not isinstance(row.get("volume"), int) or isinstance(row.get("volume"), bool) or row["volume"] < 0:
                    raise ValueError(f"INVALID_PRICE_UPDATE_COUNT:{pair}")
                previous = row["timestamp"]
                bars.append(row)
    return bars


def create_event_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE events (
          event_id TEXT PRIMARY KEY, pair TEXT NOT NULL, signal_timestamp TEXT NOT NULL,
          minute_of_week INTEGER NOT NULL, entry_timestamp TEXT NOT NULL, fold INTEGER NOT NULL, session TEXT NOT NULL,
          volatility_regime TEXT NOT NULL, trend_range_regime TEXT NOT NULL,
          price_update_count INTEGER NOT NULL, history_center REAL NOT NULL,
          history_scale REAL NOT NULL, activity_z REAL NOT NULL,
          displacement_atr REAL NOT NULL, body_direction INTEGER NOT NULL,
          spread_pips REAL NOT NULL, matched_nonshock INTEGER NOT NULL,
          long_3 TEXT NOT NULL, short_3 TEXT NOT NULL, long_6 TEXT NOT NULL, short_6 TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX event_order ON events(signal_timestamp, pair)")
    connection.execute("CREATE INDEX matched_lookup ON events(pair, minute_of_week, matched_nonshock, signal_timestamp)")


def consecutive_path(bars: list[dict[str, Any]], index: int, holding_bars: int = 6) -> bool:
    if index + holding_bars >= len(bars):
        return False
    moments = [parse_timestamp(bars[offset]["timestamp"]) for offset in range(index, index + holding_bars + 1)]
    return all(right - left == timedelta(minutes=5) for left, right in zip(moments, moments[1:]))


def insert_pair_events(connection: sqlite3.Connection, pair: str, bars: list[dict[str, Any]]) -> int:
    ranges: deque[float] = deque(maxlen=20)
    slot_history: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=8))
    previous_close: float | None = None
    inserted = 0
    statement = "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    for index, bar in enumerate(bars):
        moment = parse_timestamp(bar["timestamp"])
        signal_complete = moment + timedelta(minutes=5)
        volume = int(bar["volume"])
        slot = moment.weekday() * 1440 + moment.hour * 60 + moment.minute
        history = slot_history[slot]
        z_value: float | None = None
        center = scale = 0.0
        if len(history) == 8:
            center, scale = robust_center_scale(history)
            if scale > 0:
                z_value = (math.log1p(volume) - center) / scale

        if (
            len(ranges) == 20 and z_value is not None and SCORE_START <= signal_complete < DEV_END
            and not in_embargo(signal_complete) and consecutive_path(bars, index, 6)
        ):
            atr = math.fsum(ranges) / 20
            close = float(bar["mid"]["c"])
            open_price = float(bar["mid"]["o"])
            displacement = abs(close - open_price) / atr if atr > 0 else 0.0
            exit_complete = parse_timestamp(bars[index + 6]["timestamp"]) + timedelta(minutes=5)
            fold = fold_index(signal_complete)
            if displacement >= 0.5 and fold >= 0 and fold_index(exit_complete - timedelta(microseconds=1)) == fold:
                body_direction = 1 if close > open_price else -1
                outcomes: dict[tuple[str, int], str] = {}
                for direction in ("LONG", "SHORT"):
                    for hold in (3, 6):
                        value = [
                            scenario_outcome(
                                pair=pair, bars=bars, signal_index=index, holding_bars=hold,
                                direction=direction, atr=atr, scenario=scenario,
                            )
                            for scenario in ("gross", "base", "stress")
                        ]
                        outcomes[(direction, hold)] = json.dumps(value, separators=(",", ":"))
                trend_distance = abs(close - float(bars[index - 12]["mid"]["c"])) if index >= 12 else 0.0
                spread = (float(bar["ask"]["c"]) - float(bar["bid"]["c"])) / pip_size(pair)
                core = {
                    "activity_z": round(z_value, 12),
                    "displacement_atr": round(displacement, 12),
                    "pair": pair,
                    "signal_timestamp": timestamp_text(signal_complete),
                }
                event_id = sha256_bytes(canonical_bytes(core))
                connection.execute(statement, (
                    event_id, pair, timestamp_text(signal_complete), slot, bars[index + 1]["timestamp"], fold,
                    session_label(signal_complete),
                    "LOW" if atr / close < 0.0005 else ("HIGH" if atr / close > 0.0015 else "NORMAL"),
                    "TREND" if trend_distance >= 2.0 * atr else "RANGE",
                    volume, center, scale, z_value, displacement, body_direction, spread,
                    int(abs(z_value) < 0.5), outcomes[("LONG", 3)], outcomes[("SHORT", 3)],
                    outcomes[("LONG", 6)], outcomes[("SHORT", 6)],
                ))
                inserted += 1

        history.append(math.log1p(volume))
        ranges.append(true_range(bar, previous_close))
        previous_close = float(bar["mid"]["c"])
    connection.commit()
    return inserted


EVENT_COLUMNS = (
    "event_id", "pair", "signal_timestamp", "minute_of_week", "entry_timestamp", "fold", "session",
    "volatility_regime", "trend_range_regime", "price_update_count", "history_center",
    "history_scale", "activity_z", "displacement_atr", "body_direction", "spread_pips",
    "matched_nonshock", "long_3", "short_3", "long_6", "short_6",
)


def event_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(EVENT_COLUMNS, row))


def outcome(event: dict[str, Any], direction: str, hold: int, scenario: str) -> list[Any]:
    values = json.loads(event[f"{direction.lower()}_{hold}"])
    return values[{"gross": 0, "base": 1, "stress": 2}[scenario]]


def direction_for(event: dict[str, Any], arm: str) -> str:
    direction = "LONG" if event["body_direction"] > 0 else "SHORT"
    if arm == "REVERSAL":
        return "SHORT" if direction == "LONG" else "LONG"
    return direction


def selected_events(
    connection: sqlite3.Connection, *, where_sql: str, params: tuple[Any, ...],
    arm: str, hold: int, rank_field: str,
) -> list[tuple[dict[str, Any], str]]:
    query = f"SELECT {','.join(EVENT_COLUMNS)} FROM events WHERE {where_sql} ORDER BY signal_timestamp,{rank_field} DESC,displacement_atr DESC,pair,event_id"
    cursor = connection.execute(query, params)
    accepted: list[tuple[dict[str, Any], str]] = []
    active: list[tuple[str, str, set[str]]] = []
    for _, grouped in itertools.groupby(cursor, key=lambda row: row[2]):
        group = [event_dict(row) for row in grouped]
        entry_timestamp = group[0]["entry_timestamp"]
        active = [item for item in active if item[0] > entry_timestamp]
        for event in group:
            pair = event["pair"]
            currencies = set(pair.split("_"))
            if len(active) >= 5 or any(existing_pair == pair or currencies & used for _, existing_pair, used in active):
                continue
            direction = direction_for(event, arm)
            exit_timestamp = str(outcome(event, direction, hold, "base")[1])
            active.append((exit_timestamp, pair, currencies))
            accepted.append((event, direction))
    return accepted


def result_row(
    *, event: dict[str, Any], direction: str, hold: int, candidate_id: str,
    candidate_fingerprint: str, strategy_id: str = FAMILY,
) -> dict[str, Any]:
    gross = outcome(event, direction, hold, "gross")
    base = outcome(event, direction, hold, "base")
    stress = outcome(event, direction, hold, "stress")
    return {
        "strategy_id": strategy_id,
        "candidate_id": candidate_id,
        "candidate_fingerprint": candidate_fingerprint,
        "event_id": event["event_id"],
        "instrument": event["pair"],
        "direction": direction,
        "signal_timestamp": event["signal_timestamp"],
        "entry_timestamp": event["entry_timestamp"],
        "entry_price": base[0],
        "exit_timestamp": base[1],
        "exit_price": base[2],
        "stop_loss": base[3],
        "take_profit": None,
        "spread_pips": event["spread_pips"],
        "signal_close_spread_pips": event["spread_pips"],
        "entry_open_spread_pips": base[7],
        "exit_bar_close_spread_pips": base[8],
        "spread_accounting": "EMBEDDED_IN_EXECUTABLE_SIDE_ENTRY_STOP_AND_EXIT_PRICES",
        "modeled_slippage_pips_per_side": 0.1,
        "gross_result_pips": gross[6],
        "net_result_pips": base[6],
        "gross_result_r": gross[5],
        "net_result_r": base[5],
        "stress_result_r": stress[5],
        "result_r": base[5],
        "entry_reason": "ABNORMAL_PRICE_UPDATE_COUNT_X_SIGNED_M5_DISPLACEMENT",
        "exit_reason": base[4],
        "session": event["session"],
        "volatility_regime": event["volatility_regime"],
        "trend_or_range_regime": event["trend_range_regime"],
        "economic_event_proximity": "NOT_APPLICABLE_NO_CERTIFIED_POINT_IN_TIME_EVENT_FEED",
        "fold": event["fold"],
        "filter_results": {
            "completed_signal_candle": True,
            "next_bar_entry": True,
            "consecutive_path": True,
            "purge_embargo_clear": True,
            "activity_z": event["activity_z"],
            "displacement_atr": event["displacement_atr"],
            "price_update_count": event["price_update_count"],
            "history_center": event["history_center"],
            "history_scale": event["history_scale"],
            "spread_filter": "NONE_ALL_OBSERVED_SPREADS_CHARGED",
            "exposure_gate": "PASS",
        },
    }


def baseline_rows(
    accepted: list[tuple[dict[str, Any], str]], *, candidate_id: str,
    fingerprint: str, hold: int, random_direction: bool,
) -> list[dict[str, Any]]:
    rows = []
    for event, original_direction in accepted:
        direction = deterministic_random_direction(candidate_id, event["event_id"]) if random_direction else original_direction
        rows.append(result_row(
            event=event, direction=direction, hold=hold, candidate_id=candidate_id,
            candidate_fingerprint=fingerprint, strategy_id=f"BASELINE_{candidate_id}",
        ))
    return rows


def matched_nonshock_rows(
    connection: sqlite3.Connection, accepted: list[tuple[dict[str, Any], str]], *,
    candidate_id: str, fingerprint: str, arm: str, hold: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return one unique prior control and its paired shock row when available.

    Shocks arrive in chronological order.  Greedily assigning the newest eligible
    unused prior observation therefore preserves causality and prevents a single
    quiet event from being reused to manufacture baseline coverage.
    """
    control_rows: list[dict[str, Any]] = []
    shock_rows: list[dict[str, Any]] = []
    used_control_event_ids: set[str] = set()
    query = (
        f"SELECT {','.join(EVENT_COLUMNS)} FROM events "
        "WHERE pair=? AND minute_of_week=? AND matched_nonshock=1 AND signal_timestamp<? "
        "ORDER BY signal_timestamp DESC,event_id"
    )
    for shock_event, shock_direction in accepted:
        matches = connection.execute(
            query,
            (shock_event["pair"], shock_event["minute_of_week"], shock_event["signal_timestamp"]),
        )
        match = next((item for item in matches if item[0] not in used_control_event_ids), None)
        if match is None:
            continue
        event = event_dict(match)
        used_control_event_ids.add(event["event_id"])
        direction = direction_for(event, arm)
        row = result_row(
            event=event, direction=direction, hold=hold, candidate_id=candidate_id,
            candidate_fingerprint=fingerprint, strategy_id=f"BASELINE_{candidate_id}",
        )
        row["matched_to_shock_event_id"] = shock_event["event_id"]
        row["matched_to_shock_signal_timestamp"] = shock_event["signal_timestamp"]
        row["matched_pair"] = event["pair"]
        row["matched_minute_of_week"] = event["minute_of_week"]
        row["matched_activity_z"] = event["activity_z"]
        row["shock_pair"] = shock_event["pair"]
        row["shock_minute_of_week"] = shock_event["minute_of_week"]
        row["match_rule"] = "NEWEST_UNUSED_STRICTLY_PRIOR_SAME_PAIR_SAME_UTC_MINUTE_OF_WEEK_ACTIVITY_Z_ABS_LT_0_5"
        control_rows.append(row)
        shock_rows.append(result_row(
            event=shock_event, direction=shock_direction, hold=hold,
            candidate_id=candidate_id, candidate_fingerprint=fingerprint,
        ))
    return control_rows, shock_rows


def audit_matched_controls(candidate_count: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    matched_count = len(rows)
    event_ids = [row.get("event_id") for row in rows]
    identity_pass = all(
        row.get("matched_to_shock_event_id")
        and row.get("matched_to_shock_signal_timestamp")
        and row.get("event_id")
        for row in rows
    )
    strictly_prior_pass = bool(rows) and all(
        row["signal_timestamp"] < row["matched_to_shock_signal_timestamp"] for row in rows
    )
    same_pair_pass = bool(rows) and all(row.get("matched_pair") == row.get("shock_pair") for row in rows)
    same_minute_of_week_pass = bool(rows) and all(
        row.get("matched_minute_of_week") == row.get("shock_minute_of_week") for row in rows
    )
    activity_pass = bool(rows) and all(abs(float(row.get("matched_activity_z", math.inf))) < 0.5 for row in rows)
    unique_control_count = len(set(event_ids))
    no_reuse_pass = bool(rows) and unique_control_count == matched_count and None not in event_ids
    coverage = matched_count / candidate_count if candidate_count else 0.0
    coverage_pass = candidate_count > 0 and coverage >= MINIMUM_MATCHED_CONTROL_COVERAGE
    passed = all((
        identity_pass, strictly_prior_pass, same_pair_pass,
        same_minute_of_week_pass, activity_pass, no_reuse_pass, coverage_pass,
    ))
    return {
        "rule": "NEWEST_UNUSED_STRICTLY_PRIOR_SAME_PAIR_SAME_UTC_MINUTE_OF_WEEK_ACTIVITY_Z_ABS_LT_0_5",
        "candidate_trade_count": candidate_count,
        "matched_trade_count": matched_count,
        "unique_control_count": unique_control_count,
        "control_reuse_count": matched_count - unique_control_count,
        "coverage": coverage,
        "minimum_coverage": MINIMUM_MATCHED_CONTROL_COVERAGE,
        "nonzero_match_pass": matched_count > 0,
        "coverage_pass": coverage_pass,
        "strictly_prior_pass": strictly_prior_pass,
        "match_identity_pass": identity_pass,
        "same_pair_pass": same_pair_pass,
        "same_minute_of_week_pass": same_minute_of_week_pass,
        "activity_z_abs_lt_0_5_pass": activity_pass,
        "no_control_reuse_pass": no_reuse_pass,
        "pass": passed,
    }


def block_bootstrap(values: list[float], seed: int) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    block_size = min(20, len(values))
    blocks = [values[index:index + block_size] for index in range(0, len(values), block_size)]
    means = [math.fsum(block) / len(block) for block in blocks]
    center = math.fsum(values) / len(values)
    rng = random.Random(seed)
    samples = []
    for _ in range(256):
        sample = [means[rng.randrange(len(means))] for _ in means]
        samples.append(math.fsum(sample) / len(sample))
    samples.sort()
    lower = samples[max(0, int(0.025 * len(samples)) - 1)]
    se = math.sqrt(math.fsum((sample - center) ** 2 for sample in samples) / len(samples))
    return lower, se


def metrics(rows: list[dict[str, Any]], value_key: str, seed: int) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row["exit_timestamp"], row["instrument"], row["event_id"]))
    values = [float(row[value_key]) for row in ordered]
    wins = math.fsum(value for value in values if value > 0)
    losses = -math.fsum(value for value in values if value < 0)
    equity = peak = 1.0
    maximum_drawdown = 0.0
    for value in values:
        equity *= max(0.0, 1.0 + RISK_FRACTION * value)
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak * 100.0 if peak else 100.0)
    pair_values: dict[str, list[float]] = defaultdict(list)
    currency_values: dict[str, list[float]] = defaultdict(list)
    for row, value in zip(ordered, values):
        pair_values[row["instrument"]].append(value)
        for currency in row["instrument"].split("_"):
            currency_values[currency].append(value / 2)
    fold_values = {index: [float(row[value_key]) for row in ordered if row["fold"] == index] for index in range(6)}
    lower, se = block_bootstrap(values, seed)
    positive_total = math.fsum(value for value in values if value > 0)
    top_five = math.fsum(sorted((value for value in values if value > 0), reverse=True)[:5])
    pair_positive = {pair: math.fsum(items) for pair, items in pair_values.items() if math.fsum(items) > 0}
    currency_positive = {currency: math.fsum(items) for currency, items in currency_values.items() if math.fsum(items) > 0}
    def decomposition(field: str) -> dict[str, dict[str, float | int]]:
        grouped: dict[str, list[float]] = defaultdict(list)
        for row, value in zip(ordered, values):
            grouped[str(row[field])].append(value)
        return {
            key: {
                "trade_count": len(items),
                "trade_share": len(items) / len(values) if values else 0.0,
                "expectancy_r": math.fsum(items) / len(items),
                "total_result_r": math.fsum(items),
            }
            for key, items in sorted(grouped.items())
        }
    average_winner = wins / sum(value > 0 for value in values) if wins else 0.0
    losing_count = sum(value < 0 for value in values)
    average_loser = -losses / losing_count if losses else 0.0
    longest_losing_run = current_losing_run = 0
    for value in values:
        current_losing_run = current_losing_run + 1 if value < 0 else 0
        longest_losing_run = max(longest_losing_run, current_losing_run)
    sessions = decomposition("session")
    volatility_regimes = decomposition("volatility_regime")
    trend_range_regimes = decomposition("trend_or_range_regime")
    return {
        "trade_count": len(values),
        "long_trades": sum(row["direction"] == "LONG" for row in ordered),
        "short_trades": sum(row["direction"] == "SHORT" for row in ordered),
        "expectancy_r": math.fsum(values) / len(values) if values else 0.0,
        "profit_factor": wins / losses if losses else (999.0 if wins else 0.0),
        "win_rate": sum(value > 0 for value in values) / len(values) if values else 0.0,
        "average_winner_r": average_winner,
        "average_loser_r": average_loser,
        "average_reward_to_risk_ratio": average_winner / abs(average_loser) if average_loser else 0.0,
        "maximum_consecutive_losses": longest_losing_run,
        "maximum_drawdown_pct": maximum_drawdown,
        "instrument_breadth": len(pair_values),
        "currency_breadth": len(currency_values),
        "contributing_instruments": len(pair_positive),
        "contributing_currencies": len(currency_positive),
        "largest_pair_trade_share": max((len(items) for items in pair_values.values()), default=0) / len(values) if values else 1.0,
        "largest_currency_trade_share": max((len(items) for items in currency_values.values()), default=0) / (2 * len(values)) if values else 1.0,
        "top_five_positive_result_share": top_five / positive_total if positive_total > 0 else 1.0,
        "pair_results_r": {key: math.fsum(items) for key, items in sorted(pair_values.items())},
        "currency_results_r": {key: math.fsum(items) for key, items in sorted(currency_values.items())},
        "fold_expectancy_r": {str(key): math.fsum(items) / len(items) if items else 0.0 for key, items in fold_values.items()},
        "fold_trade_count": {str(key): len(items) for key, items in fold_values.items()},
        "positive_folds": sum(bool(items) and math.fsum(items) / len(items) > 0 for items in fold_values.values()),
        "session_decomposition": sessions,
        "volatility_regime_decomposition": volatility_regimes,
        "trend_range_decomposition": trend_range_regimes,
        "regime_breadth": {
            "sessions_with_trades": len({row["session"] for row in ordered}),
            "volatility_regimes_with_trades": len({row["volatility_regime"] for row in ordered}),
            "trend_range_regimes_with_trades": len({row["trend_or_range_regime"] for row in ordered}),
        },
        "regime_concentration": {
            "largest_session_trade_share": max((item["trade_share"] for item in sessions.values()), default=1.0),
            "largest_volatility_regime_trade_share": max((item["trade_share"] for item in volatility_regimes.values()), default=1.0),
            "largest_trend_range_regime_trade_share": max((item["trade_share"] for item in trend_range_regimes.values()), default=1.0),
            "determination": "REPORTED_NOT_GATED_STAGE1_STAGE2_REQUIRES_FROZEN_CONCENTRATION_AUDIT",
        },
        "block_bootstrap_lower_bound_r": lower,
        "block_bootstrap_standard_error_r": se,
    }


def pbo_proxy(candidate_results: dict[str, dict[str, Any]]) -> float:
    if not candidate_results:
        return 1.0
    ids = sorted(candidate_results)
    failures = 0
    splits = 0
    for training_folds in itertools.combinations(range(6), 3):
        testing_folds = set(range(6)) - set(training_folds)
        def average(candidate: str, folds: Iterable[int]) -> float:
            values = [candidate_results[candidate]["base_after_cost"]["fold_expectancy_r"][str(fold)] for fold in folds]
            return math.fsum(values) / len(values)
        selected = max(ids, key=lambda item: (average(item, training_folds), item))
        testing = sorted((average(item, testing_folds), item) for item in ids)
        selected_rank = next(index for index, (_, item) in enumerate(testing) if item == selected)
        failures += selected_rank < len(testing) / 2
        splits += 1
    return failures / splits if splits else 1.0


def gate_reasons(
    gates: dict[str, bool], *, gross_expectancy_r: float | None = None,
    after_cost_expectancy_r: float | None = None,
) -> list[str]:
    mapping = {
        "gross_edge": "NO_GROSS_EDGE",
        "after_cost": "COST_DESTROYED_EDGE",
        "profit_factor": "AFTER_COST_PROFIT_FACTOR_FAILURE",
        "drawdown": "EXCESSIVE_DRAWDOWN",
        "trades": "INSUFFICIENT_TRADES",
        "direction": "DIRECTION_CONCENTRATION",
        "breadth": "INSUFFICIENT_BREADTH",
        "folds": "WALK_FORWARD_FAILURE",
        "stress": "COST_STRESS_FAILURE",
        "baseline": "BASELINE_FAILURE",
        "concentration": "PAIR_OR_CURRENCY_CONCENTRATION",
        "leakage": "LEAKAGE",
        "accounting": "INVALID_EXPERIMENT",
        "matched_control": "INVALID_EXPERIMENT",
    }
    reasons = []
    for key, passed in gates.items():
        if passed:
            continue
        if key == "after_cost" and gross_expectancy_r is not None:
            if not (gross_expectancy_r > 0 and (after_cost_expectancy_r or 0.0) <= 0):
                continue
        reasons.append(mapping[key])
    return reasons


def break_even_cost(
    gross_expectancy_r: float, base_expectancy_r: float, stress_expectancy_r: float,
    stress_additional_round_trip_pips: float = 0.8,
) -> dict[str, float | str]:
    """Describe break-even cost with explicit round-trip units.

    Gross expectancy is the exact break-even total transaction-cost budget in
    R/trade.  Pip equivalents are linear estimates derived from the frozen
    base-to-stress slippage delta and are labelled as such.
    """
    sensitivity = (
        (base_expectancy_r - stress_expectancy_r) / stress_additional_round_trip_pips
        if stress_additional_round_trip_pips > 0 else 0.0
    )
    current_cost_r = gross_expectancy_r - base_expectancy_r
    return {
        "unit_contract": "TOTAL_ROUND_TRIP_COST_NOT_PER_SIDE",
        "break_even_total_transaction_cost_r_per_trade": max(0.0, gross_expectancy_r),
        "observed_base_total_transaction_cost_r_per_trade": current_cost_r,
        "base_cost_headroom_r_per_trade": base_expectancy_r,
        "estimated_r_per_additional_round_trip_pip": sensitivity,
        "estimated_break_even_total_transaction_cost_pips_round_trip": (
            max(0.0, gross_expectancy_r) / sensitivity if sensitivity > 0 else 0.0
        ),
        "estimated_observed_base_transaction_cost_pips_round_trip": (
            max(0.0, current_cost_r) / sensitivity if sensitivity > 0 else 0.0
        ),
        "additional_round_trip_slippage_pips_to_zero": (
            max(0.0, base_expectancy_r) / sensitivity if sensitivity > 0 else 0.0
        ),
    }


def baseline_comparison_pass(
    *, candidate_expectancy_r: float, random_expectancy_r: float,
    price_expectancy_r: float, matched_shock_expectancy_r: float,
    matched_control_expectancy_r: float, matched_control_valid: bool,
) -> bool:
    return (
        candidate_expectancy_r > NO_TRADE_EXPECTANCY_R
        and candidate_expectancy_r > random_expectancy_r
        and candidate_expectancy_r > price_expectancy_r
        and matched_control_valid
        and matched_shock_expectancy_r > matched_control_expectancy_r
    )


def classify_failures(failures: list[str]) -> tuple[str | None, list[str]]:
    priority = [
        "INVALID_EXPERIMENT", "LEAKAGE", "NO_GROSS_EDGE", "COST_DESTROYED_EDGE",
        "BASELINE_FAILURE", "WALK_FORWARD_FAILURE", "COST_STRESS_FAILURE",
        "PARAMETER_INSTABILITY", "EXCESSIVE_DRAWDOWN", "INSUFFICIENT_TRADES",
        "INSUFFICIENT_BREADTH", "PAIR_OR_CURRENCY_CONCENTRATION",
        "DIRECTION_CONCENTRATION", "AFTER_COST_PROFIT_FACTOR_FAILURE",
    ]
    ordered = [item for item in priority if item in failures]
    ordered.extend(sorted(item for item in failures if item not in ordered))
    return (ordered[0] if ordered else None, ordered[1:])


def parameter_sensitivity(candidate: str, results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    current = results[candidate]
    definition = current["definition"]
    dimensions = ("volume_z_min", "arm", "holding_m5_bars")
    neighbors = []
    for other_id, other in sorted(results.items()):
        if other_id == candidate:
            continue
        changed = [key for key in dimensions if other["definition"][key] != definition[key]]
        if len(changed) != 1:
            continue
        neighbors.append({
            "candidate_id": other_id,
            "changed_dimension": changed[0],
            "after_cost_expectancy_r": other["base_after_cost"]["expectancy_r"],
            "expectancy_difference_r": other["base_after_cost"]["expectancy_r"] - current["base_after_cost"]["expectancy_r"],
            "same_expectancy_sign": (other["base_after_cost"]["expectancy_r"] > 0) == (current["base_after_cost"]["expectancy_r"] > 0),
        })
    return {
        "neighbor_count": len(neighbors),
        "same_sign_neighbor_count": sum(item["same_expectancy_sign"] for item in neighbors),
        "neighbors": neighbors,
    }


def terminal_status(survivors: list[str]) -> str:
    return "STAGE1_SURVIVOR" if survivors else "CLOSED_FAILED_POSTMORTEM_COMPLETE"


def journal_bytes(rows: list[dict[str, Any]]) -> bytes:
    raw = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        for row in rows
    )
    return gzip.compress(raw, compresslevel=9, mtime=0)


def audit_journal_bytes(payload: bytes, expected_rows: int) -> dict[str, Any]:
    required = {
        "strategy_id", "candidate_id", "candidate_fingerprint", "instrument", "direction",
        "signal_timestamp", "entry_timestamp", "entry_price", "exit_timestamp", "exit_price",
        "stop_loss", "take_profit", "signal_close_spread_pips", "entry_open_spread_pips",
        "exit_bar_close_spread_pips", "modeled_slippage_pips_per_side", "gross_result_r",
        "net_result_r", "result_r", "entry_reason", "exit_reason", "session",
        "volatility_regime", "trend_or_range_regime", "economic_event_proximity", "filter_results",
    }
    row_count = losing_rows = missing_required_rows = 0
    with gzip.open(io.BytesIO(payload), "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            row_count += 1
            losing_rows += float(row["net_result_r"]) < 0
            missing_required_rows += not required.issubset(row)
    return {
        "valid_jsonl": True,
        "row_count": row_count,
        "expected_rows": expected_rows,
        "losing_rows": losing_rows,
        "missing_required_rows": missing_required_rows,
        "pass": row_count == expected_rows and losing_rows > 0 and missing_required_rows == 0,
    }


def research(corpus_root: Path, prereg_path: Path) -> tuple[dict[str, Any], bytes]:
    prereg = verify_preregistration(prereg_path)
    manifest = verify_manifest(corpus_root)
    connection = sqlite3.connect(":memory:")
    create_event_table(connection)
    verification: dict[str, Any] = {}
    event_count = 0
    development_rows = 0
    for pair in sorted(manifest["eligible_pairs"]):
        bars = read_pair_bars(corpus_root, manifest, pair, verification)
        development_rows += len(bars)
        event_count += insert_pair_events(connection, pair, bars)

    definitions = sorted(prereg["candidates"], key=lambda item: item["candidate_id"])
    results: dict[str, Any] = {}
    journal: list[dict[str, Any]] = []
    baseline_cache: dict[tuple[str, int, str], dict[str, Any]] = {}

    for definition_index, definition in enumerate(definitions):
        candidate_id = definition["candidate_id"]
        arm = definition["arm"]
        hold = int(definition["holding_m5_bars"])
        threshold = float(definition["volume_z_min"])
        fingerprint = definition["candidate_fingerprint"]
        accepted = selected_events(
            connection, where_sql="activity_z>=?", params=(threshold,), arm=arm,
            hold=hold, rank_field="activity_z",
        )
        rows = [
            result_row(event=event, direction=direction, hold=hold, candidate_id=candidate_id, candidate_fingerprint=fingerprint)
            for event, direction in accepted
        ]
        journal.extend(rows)
        random_rows = baseline_rows(
            accepted, candidate_id=candidate_id, fingerprint=fingerprint,
            hold=hold, random_direction=True,
        )

        cache_key = (arm, hold, "price")
        if cache_key not in baseline_cache:
            price_selected = selected_events(
                connection, where_sql="1=1", params=(), arm=arm, hold=hold, rank_field="displacement_atr",
            )
            price_rows = baseline_rows(
                price_selected, candidate_id=f"PRICE-{arm}-{hold}", fingerprint="BASELINE",
                hold=hold, random_direction=False,
            )
            baseline_cache[cache_key] = metrics(price_rows, "net_result_r", RANDOM_SEED + 100 + definition_index)

        matched_rows, matched_shock_rows = matched_nonshock_rows(
            connection, accepted, candidate_id=f"MATCHED-{candidate_id}", fingerprint="BASELINE",
            arm=arm, hold=hold,
        )

        base = metrics(rows, "net_result_r", RANDOM_SEED + definition_index)
        gross = metrics(rows, "gross_result_r", RANDOM_SEED + definition_index)
        stress = metrics(rows, "stress_result_r", RANDOM_SEED + definition_index)
        random_result = metrics(random_rows, "net_result_r", RANDOM_SEED + definition_index)
        price_result = baseline_cache[cache_key]
        matched_result = metrics(matched_rows, "net_result_r", RANDOM_SEED + 200 + definition_index)
        matched_shock_result = metrics(
            matched_shock_rows, "net_result_r", RANDOM_SEED + 300 + definition_index
        )
        matched_audit = audit_matched_controls(len(rows), matched_rows)
        accounting = all(
            row["entry_timestamp"] >= row["signal_timestamp"]
            and row["exit_timestamp"] > row["entry_timestamp"]
            and row["filter_results"]["completed_signal_candle"]
            and row["filter_results"]["history_scale"] > 0
            for row in rows
        )
        baseline_pass = baseline_comparison_pass(
            candidate_expectancy_r=base["expectancy_r"],
            random_expectancy_r=random_result["expectancy_r"],
            price_expectancy_r=price_result["expectancy_r"],
            matched_shock_expectancy_r=matched_shock_result["expectancy_r"],
            matched_control_expectancy_r=matched_result["expectancy_r"],
            matched_control_valid=matched_audit["pass"],
        )
        gates = {
            "gross_edge": gross["expectancy_r"] > 0,
            "after_cost": base["expectancy_r"] > NO_TRADE_EXPECTANCY_R,
            "profit_factor": base["profit_factor"] >= 1.05,
            "drawdown": base["maximum_drawdown_pct"] <= 15.0,
            "trades": base["trade_count"] >= 100,
            "direction": base["long_trades"] >= 40 and base["short_trades"] >= 40,
            "breadth": base["contributing_instruments"] >= 10 and base["contributing_currencies"] >= 5,
            "folds": base["positive_folds"] >= 4,
            "stress": stress["expectancy_r"] > 0,
            "baseline": baseline_pass,
            "concentration": base["largest_pair_trade_share"] <= 0.25 and base["largest_currency_trade_share"] <= 0.40 and base["top_five_positive_result_share"] <= 0.30,
            "leakage": True,
            "accounting": accounting,
            "matched_control": matched_audit["pass"],
        }
        critical = NormalDist().inv_cdf(1.0 - 0.05 / CUMULATIVE_ATTEMPTS)
        adjusted_lower = base["expectancy_r"] - critical * base["block_bootstrap_standard_error_r"]
        results[candidate_id] = {
            "definition": definition,
            "gross_midpoint": gross,
            "base_after_cost": base,
            "stress_after_cost": stress,
            "baselines": {
                "no_trade_expectancy_r": 0.0,
                "deterministic_random_direction": random_result,
                "activity_random_sign": random_result,
                "exact_price_displacement_only": price_result,
                "matched_nonshock_same_utc_minute_of_week": matched_result,
                "matched_shock_identical_subset": matched_shock_result,
            },
            "matched_control_audit": matched_audit,
            "break_even": break_even_cost(
                gross["expectancy_r"], base["expectancy_r"], stress["expectancy_r"]
            ),
            "multiple_testing": {
                "prior_actual_attempt_lower_bound": PRIOR_ATTEMPTS,
                "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPTS,
                "family_candidate_count": CANDIDATE_COUNT,
                "bonferroni_one_sided_critical_z": critical,
                "search_adjusted_expectancy_lower_bound_r": adjusted_lower,
                "block_bootstrap_lower_bound_r": base["block_bootstrap_lower_bound_r"],
            },
            "gates": gates,
            "stage1_pass": all(gates.values()),
            "failure_causes": gate_reasons(
                gates, gross_expectancy_r=gross["expectancy_r"],
                after_cost_expectancy_r=base["expectancy_r"],
            ),
        }

    pbo = pbo_proxy(results)
    for row in results.values():
        row["multiple_testing"]["probability_of_backtest_overfitting_proxy"] = pbo
        row["multiple_testing"]["stage2_precheck_pass"] = (
            row["multiple_testing"]["search_adjusted_expectancy_lower_bound_r"] > 0
            and row["multiple_testing"]["block_bootstrap_lower_bound_r"] > 0
            and pbo <= 0.50
        )
    survivors = sorted(candidate for candidate, row in results.items() if row["stage1_pass"])
    best = max(results, key=lambda candidate: (results[candidate]["base_after_cost"]["expectancy_r"], candidate))
    connection.close()
    return {
        "schema": "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_STAGE1_RESULTS.v1",
        "packet_id": PACKET_ID,
        "status": terminal_status(survivors),
        "family": FAMILY,
        "family_fingerprint": prereg["strategy_mechanism_fingerprint"],
        "preregistration_sha256": PREREG_SHA256,
        "corpus_id": CORPUS_ID,
        "corpus_sha256": CORPUS_SHA256,
        "provider_field_semantics": "OANDA_PRICE_UPDATE_COUNT_PROXY_NOT_TRADED_OR_NOTIONAL_VOLUME",
        "eligible_pair_count": 58,
        "eligible_pairs": sorted(manifest["eligible_pairs"]),
        "development_rows_opened": development_rows,
        "event_count_before_candidate_scheduling": event_count,
        "verified_partition_count": len(verification),
        "partition_verification": dict(sorted(verification.items())),
        "candidate_count": CANDIDATE_COUNT,
        "prior_actual_attempt_lower_bound": PRIOR_ATTEMPTS,
        "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPTS,
        "governed_after_cost_candidates_before": 127,
        "governed_after_cost_candidates_after": 135,
        "candidate_results": results,
        "family_pbo_proxy": pbo,
        "best_candidate": best,
        "survivors": survivors,
        "journal_row_count": len(journal),
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
        "holdout_status": "NOT_EVALUATED",
        "safety": {key: False for key in ("network", "broker", "credentials", "collector", "paper", "practice", "live", "orders", "money_movement")},
    }, journal_bytes(sorted(journal, key=lambda row: (row["candidate_id"], row["signal_timestamp"], row["instrument"], row["event_id"])))


def build_artifacts(result: dict[str, Any], journal: bytes, prereg: dict[str, Any], code_path: Path) -> dict[str, bytes]:
    causes = sorted({cause for row in result["candidate_results"].values() for cause in row["failure_causes"]})
    sensitivities = {candidate: parameter_sensitivity(candidate, result["candidate_results"]) for candidate in sorted(result["candidate_results"])}
    best_failures = result["candidate_results"][result["best_candidate"]]["failure_causes"]
    primary_family_cause = classify_failures(best_failures)[0]
    union_primary, union_secondary = classify_failures(causes)
    ordered_family_causes = ([union_primary] if union_primary is not None else []) + union_secondary
    secondary_family_causes = [cause for cause in ordered_family_causes if cause != primary_family_cause]
    postmortem = {
        "schema": "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_POSTMORTEM.v1",
        "status": "NOT_APPLICABLE_STAGE1_SURVIVOR" if result["survivors"] else "POSTMORTEM_COMPLETE_REJECTED",
        "family": FAMILY,
        "economic_mechanism": prereg["economic_mechanism"],
        "dataset_identity": {
            "corpus_id": result["corpus_id"],
            "corpus_sha256": result["corpus_sha256"],
            "development_start_inclusive": timestamp_text(SCORE_START),
            "development_end_exclusive": timestamp_text(DEV_END),
            "validation_rows_opened": 0,
            "holdout_rows_opened": 0,
        },
        "pair_universe": result["eligible_pairs"],
        "timeframes": prereg["timeframes"],
        "provider_field_semantics": result["provider_field_semantics"],
        "candidate_count": CANDIDATE_COUNT,
        "candidate_rows": {
            candidate: {
                "candidate_fingerprint": row["definition"]["candidate_fingerprint"],
                "exact_rules": row["definition"],
                "gross": row["gross_midpoint"],
                "net": row["base_after_cost"],
                "stress": row["stress_after_cost"],
                "baselines": row["baselines"],
                "matched_control_audit": row["matched_control_audit"],
                "break_even": row["break_even"],
                "multiple_testing": row["multiple_testing"],
                "gates": row["gates"],
                "root_causes": row["failure_causes"],
                "primary_failure_cause": classify_failures(row["failure_causes"])[0],
                "secondary_failure_causes": classify_failures(row["failure_causes"])[1],
                "parameter_sensitivity": sensitivities[candidate],
                "disposition": "ADVANCE_STAGE2" if row["stage1_pass"] else "REJECTED_DO_NOT_RETEST",
            }
            for candidate, row in sorted(result["candidate_results"].items())
        },
        "root_causes": causes,
        "primary_family_failure_cause": primary_family_cause,
        "secondary_family_failure_causes": secondary_family_causes,
        "parameter_sensitivity": sensitivities,
        "session_volatility_and_trend_range_decomposition": {
            candidate: {
                "session": row["base_after_cost"]["session_decomposition"],
                "volatility": row["base_after_cost"]["volatility_regime_decomposition"],
                "trend_range": row["base_after_cost"]["trend_range_decomposition"],
                "regime_breadth": row["base_after_cost"]["regime_breadth"],
                "regime_concentration": row["base_after_cost"]["regime_concentration"],
            }
            for candidate, row in sorted(result["candidate_results"].items())
        },
        "rejection_fingerprint": sha256_bytes(canonical_bytes({
            "family": result["family_fingerprint"],
            "failures": {candidate: row["failure_causes"] for candidate, row in sorted(result["candidate_results"].items())},
        })),
        "prohibited_repeats": [
            "RENAME_PRICE_UPDATE_COUNT_AS_TRADED_OR_TICK_VOLUME",
            "COSMETIC_ACTIVITY_Z_HOLD_OR_STOP_CHANGE",
            "POST_HOC_PAIR_SESSION_DIRECTION_OR_REGIME_FILTER",
            "PURE_PRICE_BREAKOUT_OR_REVERSAL_RESCUE",
            "REMOVE_OBSERVED_SPREAD_OR_SLIPPAGE",
        ],
        "salvageable_evidence": "Only a fresh economically distinct mechanism may proceed; the OANDA count must never be represented as transaction volume.",
        "next_distinct_hypothesis": "DIRECTED_ANCHOR_TO_CROSS_PRICE_DISCOVERY_LEAD_LAG_STAGE0_DUPLICATE_GATE",
        "holdout_status": "NOT_EVALUATED",
    }
    checkpoint = {
        "schema": "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_CHECKPOINT.v1",
        "status": "STAGE1_COMPLETE",
        "packet_status": result["status"],
        "completed_candidate_ids": sorted(result["candidate_results"]),
        "pending_candidate_ids": [],
        "survivors": result["survivors"],
        "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPTS,
        "governed_after_cost_candidates": 135,
        "holdout_status": "NOT_EVALUATED",
        "next_action": "ADVANCE_SURVIVOR_TO_STAGE2" if result["survivors"] else postmortem["next_distinct_hypothesis"],
    }
    best = result["candidate_results"][result["best_candidate"]]
    report = (
        "# Abnormal OANDA Price-Update Count Response Stage-1 Screen\n\n"
        f"Status: `{result['status']}`\n\n"
        f"Eight frozen candidates were scored on {result['eligible_pair_count']} certified M5 pairs. "
        f"The best candidate was `{result['best_candidate']}` with gross expectancy "
        f"{best['gross_midpoint']['expectancy_r']:.9f}R, after-cost expectancy "
        f"{best['base_after_cost']['expectancy_r']:.9f}R, profit factor "
        f"{best['base_after_cost']['profit_factor']:.9f}, maximum drawdown "
        f"{best['base_after_cost']['maximum_drawdown_pct']:.9f}%, and "
        f"{best['base_after_cost']['trade_count']} trades. Stage-1 survivors: {len(result['survivors'])}.\n\n"
        "The input field is OANDA price-update count, not traded or notional volume. "
        "The final holdout remained sealed. Results are historical simulations, not realized profit.\n"
    ).encode("utf-8")
    contract = {
        "schema": "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "family": FAMILY,
        "preregistration_sha256": PREREG_SHA256,
        "preregistration": prereg,
        "prior_actual_attempt_lower_bound": PRIOR_ATTEMPTS,
        "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPTS,
        "holdout_rule": "SEALED_NOT_EVALUATED",
    }
    registry = {
        "schema": "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_CANDIDATE_REGISTRY.v1",
        "family": FAMILY,
        "family_fingerprint": result["family_fingerprint"],
        "candidate_count": CANDIDATE_COUNT,
        "candidates": prereg["candidates"],
        "cumulative_actual_attempt_lower_bound": CUMULATIVE_ATTEMPTS,
    }
    primary = {
        "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_CONTRACT.json": canonical_bytes(contract),
        "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_CANDIDATE_REGISTRY.json": canonical_bytes(registry),
        "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_RESULTS.json": canonical_bytes(result),
        "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_TRADE_JOURNAL.jsonl.gz": journal,
        "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_POSTMORTEM.json": canonical_bytes(postmortem),
        "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_CHECKPOINT.json": canonical_bytes(checkpoint),
        "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_STAGE1_REPORT.md": report,
    }
    code = code_path.read_bytes()
    manifest = {
        "schema": "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_MANIFEST.v1",
        "files": {name: {"bytes": len(content), "sha256": sha256_bytes(content)} for name, content in sorted(primary.items())},
        "code": {"path": code_path.as_posix(), "bytes": len(code), "sha256": sha256_bytes(code)},
        "verified_partition_count": result["verified_partition_count"],
        "journal_rows": result["journal_row_count"],
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
    }
    primary["AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_MANIFEST.json"] = canonical_bytes(manifest)
    journal_audit = audit_journal_bytes(journal, result["journal_row_count"])
    acceptance = {
        "schema": "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_ACCEPTANCE.v1",
        "packet_id": PACKET_ID,
        "checks": {
            "exact_eight_candidates": len(result["candidate_results"]) == 8,
            "trial_memory_1179_to_1187": result["cumulative_actual_attempt_lower_bound"] == 1187,
            "all_58_pairs": result["eligible_pair_count"] == 58,
            "partitions_verified": result["verified_partition_count"] == 58 * 15,
            "complete_candidate_journal": result["journal_row_count"] > 0,
            "valid_one_object_per_line_jsonl": journal_audit["pass"],
            "journal_entry_and_exit_spreads": journal_audit["missing_required_rows"] == 0,
            "matched_controls_valid_unique_and_adequately_covered": all(
                row["matched_control_audit"]["pass"]
                and row["matched_control_audit"]["control_reuse_count"] == 0
                and row["matched_control_audit"]["coverage"] >= MINIMUM_MATCHED_CONTROL_COVERAGE
                for row in result["candidate_results"].values()
            ),
            "matched_baseline_uses_identical_shock_subset": all(
                row["baselines"]["matched_shock_identical_subset"]["trade_count"]
                == row["baselines"]["matched_nonshock_same_utc_minute_of_week"]["trade_count"]
                for row in result["candidate_results"].values()
            ),
            "postmortem_regime_and_parameter_analysis": bool(sensitivities) and all(
                row["base_after_cost"]["regime_breadth"]["sessions_with_trades"] > 0
                and "determination" in row["base_after_cost"]["regime_concentration"]
                for row in result["candidate_results"].values()
            ),
            "postmortem_complete_performance_statistics": all(
                all(field in row["base_after_cost"] for field in (
                    "win_rate", "average_winner_r", "average_loser_r",
                    "average_reward_to_risk_ratio", "maximum_consecutive_losses",
                ))
                for row in result["candidate_results"].values()
            ),
            "no_trade_zero_baseline": all(row["baselines"]["no_trade_expectancy_r"] == 0.0 for row in result["candidate_results"].values()),
            "negative_or_zero_cannot_pass_baseline": all((row["base_after_cost"]["expectancy_r"] > 0) == row["gates"]["after_cost"] for row in result["candidate_results"].values()),
            "validation_rows_zero": result["validation_rows_opened"] == 0,
            "holdout_rows_zero": result["holdout_rows_opened"] == 0,
        },
    }
    acceptance["status"] = "PASS" if all(acceptance["checks"].values()) else "FAIL"
    acceptance["journal_audit"] = journal_audit
    primary["AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_ACCEPTANCE.json"] = canonical_bytes(acceptance)
    return primary


def write_artifacts(output: Path, artifacts: dict[str, bytes]) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(artifacts.items()):
        (output / name).write_bytes(content)
    receipt = {
        "schema": "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "files": {
            name: {"bytes": len(content), "sha256": sha256_bytes(content)}
            for name, content in sorted(artifacts.items())
        },
        "aggregate_sha256": sha256_bytes(b"".join(
            name.encode("utf-8") + b"\0" + hashlib.sha256(content).digest()
            for name, content in sorted(artifacts.items())
        )),
        "status": "PASS",
    }
    receipt_bytes = canonical_bytes(receipt)
    (output / "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_RECEIPT.json").write_bytes(receipt_bytes)
    return {"receipt_sha256": sha256_bytes(receipt_bytes), **receipt}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--preregistration", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    corpus = (args.corpus_root or repo / ".aios/runtime/forex_m5_immutable_corpus_v2").resolve()
    prereg_path = (args.preregistration or repo / ".aios/staging/PKT_FOREX_029/run1/AIOS_FOREX_ABNORMAL_PRICE_UPDATE_PREREGISTRATION_V1.json").resolve()
    result, journal = research(corpus, prereg_path)
    prereg = verify_preregistration(prereg_path)
    artifacts = build_artifacts(result, journal, prereg, Path(__file__).resolve())
    receipt = write_artifacts(args.output.resolve(), artifacts)
    print(json.dumps({
        "status": result["status"], "survivors": result["survivors"],
        "best_candidate": result["best_candidate"], "journal_rows": result["journal_row_count"],
        "cumulative_actual_attempt_lower_bound": result["cumulative_actual_attempt_lower_bound"],
        "receipt_sha256": receipt["receipt_sha256"], "aggregate_sha256": receipt["aggregate_sha256"],
        "validation_rows_opened": 0, "holdout_rows_opened": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
