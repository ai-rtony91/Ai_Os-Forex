"""Deterministic GET-only multi-pair M5 replay bridge.

This module is research/validation only. It discovers the practice Forex
universe, fetches completed M5 candles, normalizes instrument metadata, and
replays the existing Supertrend pullback V1 strategy without awarding any
qualifying campaign credit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from automation.forex_engine.forex_persistent_all_pairs_m1_m2_observer_v1 import (
    completed_candles,
    eligible_forex_instruments,
    validate_observer_client,
)
from automation.forex_engine.models import Candle
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient
from automation.forex_engine.strategies import (
    SUPERTREND_PULLBACK_V1,
    SupertrendPullbackConfig,
    classify_r_multiple,
    evaluate_supertrend_pullback,
    planned_reward_risk,
    realized_r_multiple,
)

VERSION = "forex_multipair_m5_replay_v1"
PROTOCOL_VERSION = "supertrend_pullback_multipair_long_v1"
SCHEMA = "AIOS_FOREX_MULTIPAIR_M5_REPLAY_V1"
REPLAY_ROOT = Path(".aios/runtime/forex_multipair_m5_replay_v1")
M5_GRANULARITY = "M5"
DEFAULT_CANDLE_COUNT = 500
SUPPORTED_DECISION_REASONS = (
    "insufficient_candles",
    "no_supertrend_flip",
    "chop_zone_repeated_flips",
    "trend_not_aligned",
    "pullback_not_confirmed",
    "volatility_filter_failed",
    "duplicate_position_guard",
    "data_unavailable",
    "stale_history",
    "stale_snapshot",
    "unknown_no_signal",
)
DECISION_GATE_MAP = {
    "insufficient_candles": "DATA",
    "no_supertrend_flip": "SUPERTREND_DIRECTION",
    "chop_zone_repeated_flips": "CHOP",
    "trend_not_aligned": "SUPERTREND_DIRECTION",
    "no_supertrend_direction": "SUPERTREND_DIRECTION",
    "missing_supertrend_band": "SUPERTREND_DIRECTION",
    "weak_candle_body": "BODY",
    "pullback_not_confirmed": "BODY",
    "close_confirmation_missing": "CLOSE_CONFIRMATION",
    "entry_extended_from_band": "BAND_EXTENSION",
    "volatility_filter_failed": "ATR",
    "reward_risk_below_minimum": "RR",
    "duplicate_position_guard": "DUPLICATE_POSITION",
    "data_unavailable": "DATA",
    "stale_history": "DATA",
    "stale_snapshot": "DATA",
    "unknown_no_signal": "OTHER",
}


@dataclass(frozen=True)
class ReplayInstrument:
    instrument: str
    display_precision: int
    pip_location: int
    tradeable: bool
    priceable: bool

    @property
    def quote_currency(self) -> str:
        return self.instrument.split("_", 1)[1]

    @property
    def base_currency(self) -> str:
        return self.instrument.split("_", 1)[0]

    @property
    def pip_size(self) -> float:
        return 10 ** self.pip_location


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("mapping_required")
    return value


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"invalid_{name}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_{name}") from exc
    if not math.isfinite(result):
        raise ValueError(f"invalid_{name}")
    return result


def _normalize_reason(reasons: Sequence[str] | None) -> str:
    if not reasons:
        return "OTHER"
    for reason in reasons:
        if reason in DECISION_GATE_MAP:
            return DECISION_GATE_MAP[reason]
    return "OTHER"


def _normalize_instrument_record(item: Mapping[str, Any]) -> ReplayInstrument | None:
    name = str(item.get("name", "")).upper()
    if item.get("type") != "CURRENCY":
        return None
    if item.get("tradeable") is False or item.get("halted") is True:
        return None
    if item.get("displayPrecision") is None or item.get("pipLocation") is None:
        return None
    try:
        return ReplayInstrument(
            instrument=name,
            display_precision=int(item["displayPrecision"]),
            pip_location=int(item["pipLocation"]),
            tradeable=True,
            priceable=True,
        )
    except (TypeError, ValueError):
        return None


def discover_fixed_universe(client: OandaReadOnlyClient) -> dict[str, Any]:
    validate_observer_client(client)
    payload = _as_mapping(client.discover_instruments())
    universe = eligible_forex_instruments(payload)
    eligible: list[ReplayInstrument] = []
    excluded: list[dict[str, Any]] = []
    raw = payload.get("instruments", [])
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, Mapping):
            excluded.append({"instrument": "UNKNOWN", "reason": "invalid_instrument_record"})
            continue
        normalized = _normalize_instrument_record(item)
        if normalized is None:
            excluded.append({
                "instrument": str(item.get("name", "UNKNOWN")).upper() or "UNKNOWN",
                "reason": "metadata_or_tradeability_invalid",
            })
            continue
        eligible.append(normalized)
    eligible = sorted(eligible, key=lambda item: item.instrument)
    fingerprint_source = {
        "eligible_instruments": [
            {
                "instrument": item.instrument,
                "display_precision": item.display_precision,
                "pip_location": item.pip_location,
            }
            for item in eligible
        ]
    }
    fingerprint = hashlib.sha256(_stable_json(fingerprint_source).encode("utf-8")).hexdigest()
    return {
        "schema": SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "discovered_pairs": [item.instrument for item in eligible],
        "eligible_instruments": [item.__dict__ | {"pip_size": item.pip_size} for item in eligible],
        "excluded_instruments": excluded,
        "universe_fingerprint": fingerprint,
        "raw_universe_status": universe.get("universe_status"),
        "raw_payload_included": False,
        "broker_write_performed": False,
        "practice_order_performed": False,
        "live_trade_performed": False,
        "money_movement_performed": False,
        "credentials_persisted": False,
    }


def fetch_replay_history(
    client: OandaReadOnlyClient,
    instrument: str,
    *,
    candle_count: int = DEFAULT_CANDLE_COUNT,
    price_component: str = "M",
) -> dict[str, Any]:
    requested_count = candle_count + 1
    payload = _as_mapping(
        client.observation_candles(
            instrument,
            granularity=M5_GRANULARITY,
            count=requested_count,
            price=price_component,
        )
    )
    if price_component not in {"M", "MBA"}:
        raise ValueError("unsupported_price_component")
    candles = completed_candles(payload, instrument=instrument, granularity=M5_GRANULARITY)
    if len(candles) < candle_count:
        raise ValueError("insufficient_completed_m5_history")
    candles = candles[-candle_count:]
    sanitized: list[dict[str, Any]] = []
    if price_component == "MBA":
        for candle in payload.get("candles", []):
            if not isinstance(candle, Mapping) or candle.get("complete") is not True:
                continue
            sanitized.append(_sanitize_mba_candle(candle, instrument=instrument))
    return {
        "instrument": instrument,
        "granularity": M5_GRANULARITY,
        "price_component": price_component,
        "requested_count": requested_count,
        "returned_count": len(candles),
        "candles": [item.__dict__ for item in candles],
        "sanitized_candles": sanitized[-candle_count:],
        "complete": True,
        "sanitized": True,
        "raw_payload_included": False,
    }


def _pair_group_key(instrument: str) -> tuple[str, str]:
    base, quote = instrument.split("_", 1)
    return base, quote


def build_replay_cache(
    client: OandaReadOnlyClient,
    *,
    runtime_root: Path = REPLAY_ROOT,
    candle_count: int = DEFAULT_CANDLE_COUNT,
    price_component: str = "M",
) -> dict[str, Any]:
    universe = discover_fixed_universe(client)
    runtime_root.mkdir(parents=True, exist_ok=True)
    pair_histories: dict[str, Any] = {}
    excluded: list[dict[str, Any]] = list(universe["excluded_instruments"])
    for pair in universe["discovered_pairs"]:
        try:
            history = fetch_replay_history(client, pair, candle_count=candle_count, price_component=price_component)
            pair_histories[pair] = history
            (runtime_root / f"{pair}_M5.json").write_text(_stable_json(history), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - surfaced as excluded evidence
            excluded.append({"instrument": pair, "reason": f"history_capture_failed:{exc}"})
    fingerprint_source = {
        "universe_fingerprint": universe["universe_fingerprint"],
        "pairs": {
            name: {
                "returned_count": payload["returned_count"],
                "first_utc": payload["candles"][0]["timestamp"],
                "last_utc": payload["candles"][-1]["timestamp"],
            }
            for name, payload in sorted(pair_histories.items())
        },
    }
    cache = {
        "schema": SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "captured_at_utc": _stamp(_utc_now()),
        "candle_count": candle_count,
        "universe_fingerprint": universe["universe_fingerprint"],
        "discovered_pairs": universe["discovered_pairs"],
        "eligible_instruments": universe["eligible_instruments"],
        "excluded_instruments": excluded,
        "pair_histories": pair_histories,
        "fingerprint": hashlib.sha256(_stable_json(fingerprint_source).encode("utf-8")).hexdigest(),
        "broker_write_performed": False,
        "practice_order_performed": False,
        "live_trade_performed": False,
        "money_movement_performed": False,
        "credentials_persisted": False,
    }
    runtime_root.joinpath("replay_cache.json").write_text(
        _stable_json(
            cache
            | {
                "pair_histories": pair_histories,
                "pair_history_names": list(pair_histories),
            }
        ),
        encoding="utf-8",
    )
    return cache


def _to_candle_items(history: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candles = history.get("candles")
    if not isinstance(candles, list):
        raise ValueError("candles_required")
    return [item for item in candles if isinstance(item, Mapping)]


def _candle_value(item: Mapping[str, Any], field: str) -> float:
    if field in item:
        return _finite(item[field], field)
    mid = item.get("mid")
    if isinstance(mid, Mapping):
        mid_key = {"open": "o", "high": "h", "low": "l", "close": "c"}[field]
        if mid_key in mid:
            return _finite(mid[mid_key], field)
    raise ValueError(f"missing_{field}")


def _sanitize_mba_candle(item: Mapping[str, Any], *, instrument: str) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ValueError("mba_candle_mapping_required")
    if item.get("complete") is not True:
        raise ValueError("mba_candle_incomplete")
    timestamp = item.get("time") or item.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
        raise ValueError("mba_candle_timestamp_required")
    mid = item.get("mid")
    bid = item.get("bid")
    ask = item.get("ask")
    if not isinstance(mid, Mapping):
        raise ValueError("mba_mid_required")
    if not isinstance(bid, Mapping):
        raise ValueError("mba_bid_required")
    if not isinstance(ask, Mapping):
        raise ValueError("mba_ask_required")
    record = {
        "instrument": instrument,
        "timestamp": timestamp,
        "complete": True,
        "volume": float(item.get("volume", 0.0)),
        "mid": {
            "open": _finite(mid.get("o"), "mid_open"),
            "high": _finite(mid.get("h"), "mid_high"),
            "low": _finite(mid.get("l"), "mid_low"),
            "close": _finite(mid.get("c"), "mid_close"),
        },
        "bid": {
            "open": _finite(bid.get("o"), "bid_open"),
            "high": _finite(bid.get("h"), "bid_high"),
            "low": _finite(bid.get("l"), "bid_low"),
            "close": _finite(bid.get("c"), "bid_close"),
        },
        "ask": {
            "open": _finite(ask.get("o"), "ask_open"),
            "high": _finite(ask.get("h"), "ask_high"),
            "low": _finite(ask.get("l"), "ask_low"),
            "close": _finite(ask.get("c"), "ask_close"),
        },
    }
    if not record["ask"]["close"] > record["bid"]["close"]:
        raise ValueError("mba_ask_bid_spread_required")
    return record


def _trade_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "expectancy_r": 0.0,
            "profit_factor": None,
            "maximum_drawdown_r": 0.0,
            "average_realized_r": 0.0,
            "largest_loss_r": 0.0,
            "maximum_loss_streak": 0,
            "net_r": 0.0,
        }
    r_values = [float(item["realized_r"]) for item in trades]
    wins = [r for r in r_values if r > 0]
    losses = [r for r in r_values if r < 0]
    equity = peak = drawdown = 0.0
    streak = max_streak = 0
    for value in r_values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        if value < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trade_count": len(trades),
        "win_rate": sum(v > 0 for v in r_values) / len(r_values),
        "expectancy_r": sum(r_values) / len(r_values),
        "profit_factor": (gross_profit / gross_loss) if gross_loss else (float("inf") if gross_profit else None),
        "maximum_drawdown_r": drawdown,
        "average_realized_r": sum(r_values) / len(r_values),
        "largest_loss_r": min(r_values),
        "maximum_loss_streak": max_streak,
        "net_r": sum(r_values),
    }


def _quote_snapshot_map(pricing_payload: Mapping[str, Any]) -> dict[str, float]:
    prices = pricing_payload.get("prices")
    if not isinstance(prices, list):
        return {}
    mids: dict[str, float] = {}
    for item in prices:
        if not isinstance(item, Mapping):
            continue
        instrument = str(item.get("instrument", "")).upper()
        bids, asks = item.get("bids"), item.get("asks")
        if not isinstance(bids, list) or not bids or not isinstance(asks, list) or not asks:
            continue
        try:
            bid = float(bids[0]["price"])
            ask = float(asks[0]["price"])
        except (TypeError, ValueError, KeyError):
            continue
        if ask <= bid:
            continue
        mids[instrument] = round((bid + ask) / 2.0, 10)
    return mids


def _simulate_exit(
    candles: Sequence[Mapping[str, Any]],
    entry_index: int,
    *,
    direction: str,
    entry_price: float,
    stop: float,
    target: float,
) -> tuple[dict[str, Any] | None, int | None]:
    for index in range(entry_index + 1, len(candles)):
        candle = candles[index]
        high = _finite(candle["high"], "high")
        low = _finite(candle["low"], "low")
        if direction == "BUY":
            if low <= stop:
                return {"exit_price": stop, "exit_reason": "paper_stop", "exit_index": index}, index
            if high >= target:
                return {"exit_price": target, "exit_reason": "paper_target", "exit_index": index}, index
        else:
            if high >= stop:
                return {"exit_price": stop, "exit_reason": "paper_stop", "exit_index": index}, index
            if low <= target:
                return {"exit_price": target, "exit_reason": "paper_target", "exit_index": index}, index
    return None, None


def replay_pair(
    instrument: ReplayInstrument,
    history: Mapping[str, Any],
    *,
    strategy_config: SupertrendPullbackConfig | None = None,
    quote_mids: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    config = strategy_config or SupertrendPullbackConfig()
    candles = _to_candle_items(history)
    normalized: list[dict[str, Any]] = []
    first_failure_counts: dict[str, int] = {
        "DATA": 0,
        "SUPERTREND_DIRECTION": 0,
        "CHOP": 0,
        "ATR": 0,
        "BODY": 0,
        "CLOSE_CONFIRMATION": 0,
        "BAND_EXTENSION": 0,
        "GEOMETRY": 0,
        "RR": 0,
        "DIRECTION_POLICY": 0,
        "DUPLICATE_POSITION": 0,
        "OTHER": 0,
    }
    valid_buy = valid_sell = 0
    policy_blocked_sell = 0
    trades: list[dict[str, Any]] = []
    quote_mids = dict(quote_mids or {})
    for index in range(len(candles)):
        window = candles[: index + 1]
        if len(window) < config.atr_period + 2:
            continue
        candles_obj = [
            Candle(
                symbol=instrument.instrument.replace("_", ""),
                timeframe="5m",
                timestamp=item.get("observed_at_utc", item.get("timestamp")),
                open=_candle_value(item, "open"),
                high=_candle_value(item, "high"),
                low=_candle_value(item, "low"),
                close=_candle_value(item, "close"),
                volume=float(item.get("volume", 0)),
                source="sanitized_market_history",
            )
            for item in window
        ]
        result = evaluate_supertrend_pullback(candles_obj, config)
        accepted = bool(result.get("accepted"))
        signal = result.get("signal")
        reasons = list(result.get("no_trade_reasons") or [])
        gate = _normalize_reason(reasons)
        normalized.append({
            "instrument": instrument.instrument,
            "cycle_index": index + 1,
            "accepted": accepted,
            "direction": getattr(signal, "direction", None) if signal else None,
            "reasons": reasons,
            "first_failure": gate,
        })
        if accepted and signal is not None:
            direction = str(signal.direction)
            if direction == "BUY":
                valid_buy += 1
            elif direction == "SELL":
                valid_sell += 1
                policy_blocked_sell += 1
            exit_record, exit_index = _simulate_exit(
                candles,
                index,
                direction=direction,
                entry_price=float(signal.entry_price),
                stop=float(signal.stop_loss),
                target=float(signal.take_profit),
            )
            if exit_record is None:
                continue
            entry = float(signal.entry_price)
            stop = float(signal.stop_loss)
            target = float(signal.take_profit)
            units = 100
            risk = abs(entry - stop)
            realized_pl_quote = (
                (exit_record["exit_price"] - entry) * units
                if direction == "BUY"
                else (entry - exit_record["exit_price"]) * units
            )
            realized_r = realized_r_multiple(realized_pl_quote, risk)
            quote_currency = instrument.quote_currency
            realized_pl_usd: float | str = "NOT_COMPUTABLE"
            if quote_currency == "USD":
                realized_pl_usd = realized_pl_quote
            else:
                direct = quote_mids.get(f"{quote_currency}_USD")
                inverse = quote_mids.get(f"USD_{quote_currency}")
                if direct and direct > 0:
                    realized_pl_usd = round(realized_pl_quote * direct, 8)
                elif inverse and inverse > 0:
                    realized_pl_usd = round(realized_pl_quote / inverse, 8)
            trades.append({
                "instrument": instrument.instrument,
                "strategy_name": SUPERTREND_PULLBACK_V1,
                "protocol_version": PROTOCOL_VERSION,
                "direction": direction,
                "entry_timestamp_utc": window[index].get("observed_at_utc", window[index].get("timestamp")),
                "exit_timestamp_utc": candles[exit_index].get("observed_at_utc", candles[exit_index].get("timestamp")),
                "entry_price": entry,
                "stop_price": stop,
                "target_price": target,
                "risk_amount": risk,
                "planned_reward_risk": planned_reward_risk(entry, stop, target),
                "exit_price": exit_record["exit_price"],
                "exit_reason": exit_record["exit_reason"],
                "realized_pl_quote_currency": realized_pl_quote,
                "quote_currency": quote_currency,
                "realized_pl_usd": realized_pl_usd,
                "realized_r": realized_r,
                "roi_class": classify_r_multiple(realized_pl_quote, risk),
                "mfe_r": None,
                "mae_r": None,
                "holding_duration_seconds": (
                    datetime.fromisoformat(candles[exit_index].get("observed_at_utc", candles[exit_index].get("timestamp")).replace("Z", "+00:00"))
                    - datetime.fromisoformat(window[index].get("observed_at_utc", window[index].get("timestamp")).replace("Z", "+00:00"))
                ).total_seconds() if exit_index is not None else None,
                "paper_only": True,
                "evidence_type": "PAPER",
                "units": units,
            })
        else:
            if reasons:
                first_failure_counts[gate] = first_failure_counts.get(gate, 0) + 1
            else:
                first_failure_counts["OTHER"] = first_failure_counts.get("OTHER", 0) + 1

    trade_stats = _trade_stats(trades)
    multiple_filters_blocked = sum(
        1 for item in normalized if not item["accepted"] and len(item["reasons"]) > 1
    )
    return {
        "instrument": instrument.instrument,
        "display_precision": instrument.display_precision,
        "pip_location": instrument.pip_location,
        "pip_size": instrument.pip_size,
        "candles": len(candles),
        "decision_rows": normalized,
        "valid_buy_candidates": valid_buy,
        "valid_sell_candidates": valid_sell,
        "sell_rejected_only_by_policy": policy_blocked_sell,
        "first_failure_counts": first_failure_counts,
        "multiple_filters_blocked": multiple_filters_blocked,
        "trades": trades,
        "trade_stats": trade_stats,
    }


def run_multipair_m5_replay(
    client: OandaReadOnlyClient,
    *,
    runtime_root: Path = REPLAY_ROOT,
    candle_count: int = DEFAULT_CANDLE_COUNT,
    price_component: str = "M",
) -> dict[str, Any]:
    cache = build_replay_cache(
        client,
        runtime_root=runtime_root,
        candle_count=candle_count,
        price_component=price_component,
    )
    universe = cache["eligible_instruments"]
    pricing_payload = _as_mapping(client.pricing(tuple(cache["discovered_pairs"])) if cache["discovered_pairs"] else {"prices": []})
    quote_mids = _quote_snapshot_map(pricing_payload)
    pair_results: list[dict[str, Any]] = []
    total_buy = total_sell = total_sell_blocked = 0
    total_first_failure: dict[str, int] = {}
    total_trades: list[dict[str, Any]] = []
    for item in universe:
        instrument = ReplayInstrument(
            instrument=item["instrument"],
            display_precision=int(item["display_precision"]),
            pip_location=int(item["pip_location"]),
            tradeable=True,
            priceable=True,
        )
        history = cache["pair_histories"][instrument.instrument]
        result = replay_pair(instrument, history, quote_mids=quote_mids)
        pair_results.append(result)
        total_buy += result["valid_buy_candidates"]
        total_sell += result["valid_sell_candidates"]
        total_sell_blocked += result["sell_rejected_only_by_policy"]
        total_trades.extend(result["trades"])
        for key, value in result["first_failure_counts"].items():
            total_first_failure[key] = total_first_failure.get(key, 0) + int(value)

    hours = sum(
        max(
            1.0 / 12.0,
            (
                datetime.fromisoformat(pair["candles"][-1].get("observed_at_utc", pair["candles"][-1].get("timestamp")).replace("Z", "+00:00"))
                - datetime.fromisoformat(pair["candles"][0].get("observed_at_utc", pair["candles"][0].get("timestamp")).replace("Z", "+00:00"))
            ).total_seconds()
            / 3600.0,
        )
        for pair in cache["pair_histories"].values()
    )
    per_day = total_buy / max(1.0 / 24.0, hours) * 24.0
    per_day_all = (total_buy + total_sell) / max(1.0 / 24.0, hours) * 24.0
    return {
        "schema": SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "captured_at_utc": _stamp(_utc_now()),
        "universe_fingerprint": cache["universe_fingerprint"],
        "eligible_pairs": [item["instrument"] for item in universe],
        "pair_results": pair_results,
        "pair_count": len(universe),
        "discovered_pairs": len(cache["discovered_pairs"]),
        "candles_per_pair": {name: data["returned_count"] for name, data in cache["pair_histories"].items()},
        "total_candles": sum(data["returned_count"] for data in cache["pair_histories"].values()),
        "first_failure_counts": total_first_failure,
        "first_failure_counts_total": total_first_failure,
        "valid_buy_candidates": total_buy,
        "valid_sell_candidates": total_sell,
        "sell_rejected_only_by_policy": total_sell_blocked,
        "buy_only_opportunities_per_day": per_day,
        "buy_plus_sell_opportunities_per_day": per_day_all,
        "baseline_opportunities_per_day": 0.6362697048,
        "throughput_multiplier": per_day / 0.6362697048 if 0.6362697048 else None,
        "projected_days_to_30_buy_only": 30.0 / max(1e-9, per_day),
        "projected_days_to_30_buy_plus_sell": 30.0 / max(1e-9, per_day_all),
        "price_precision": _normalization_classification(universe, "display_precision"),
        "pip_handling": _normalization_classification(universe, "pip_location"),
        "atr_normalization": "REQUIRES_NORMALIZATION",
        "pl_normalization": _pl_normalization_classification(universe),
        "broker_write_performed": False,
        "practice_order_performed": False,
        "live_trade_performed": False,
        "money_movement_performed": False,
        "credentials_persisted": False,
        "replay_grants_qualifying_credit": False,
        "current_collector_untouched": True,
        "total_replay_hours": hours,
        "pricing_quote_mids": quote_mids,
        "trade_count": len(total_trades),
        "trades": total_trades,
    }


def _normalization_classification(universe: Sequence[Mapping[str, Any]], field: str) -> str:
    values = {item[field] for item in universe}
    if not values:
        return "BLOCKING"
    return "VALID" if len(values) == 1 else "REQUIRES_NORMALIZATION"


def _pl_normalization_classification(universe: Sequence[Mapping[str, Any]]) -> str:
    quotes = {str(item["instrument"]).split("_", 1)[1] for item in universe}
    return "VALID" if quotes == {"USD"} else "REQUIRES_NORMALIZATION"


def summarize_replay_bridge(result: Mapping[str, Any]) -> dict[str, Any]:
    counts = dict(result.get("first_failure_counts_total") or result.get("first_failure_counts") or {})
    return {
        "schema": result.get("schema", SCHEMA),
        "protocol_version": result.get("protocol_version", PROTOCOL_VERSION),
        "eligible_pairs": result.get("eligible_pairs", []),
        "discovered_pairs": result.get("discovered_pairs", 0),
        "candles_per_pair": result.get("candles_per_pair", {}),
        "ATR_ONLY_BLOCKED": counts.get("ATR", 0),
        "BODY_ONLY_BLOCKED": counts.get("BODY", 0),
        "CHOP_ONLY_BLOCKED": counts.get("CHOP", 0),
        "CLOSE_CONFIRMATION_ONLY_BLOCKED": counts.get("CLOSE_CONFIRMATION", 0),
        "BAND_EXTENSION_ONLY_BLOCKED": counts.get("BAND_EXTENSION", 0),
        "RR_ONLY_BLOCKED": counts.get("RR", 0),
        "MULTIPLE_FILTERS_BLOCKED": sum(
            int(item.get("multiple_filters_blocked", 0)) for item in result.get("pair_results", [])
        ),
        "VALID_BUY_CANDIDATES": result.get("valid_buy_candidates", 0),
        "VALID_SELL_CANDIDATES": result.get("valid_sell_candidates", 0),
        "SELL_REJECTED_ONLY_BY_POLICY": result.get("sell_rejected_only_by_policy", 0),
        "MULTIPAIR_BUY_ONLY_OPPORTUNITIES_PER_DAY": result.get("buy_only_opportunities_per_day", 0.0),
        "MULTIPAIR_BUY_PLUS_SELL_OPPORTUNITIES_PER_DAY": result.get("buy_plus_sell_opportunities_per_day", 0.0),
        "BASELINE_OPPORTUNITIES_PER_DAY": result.get("baseline_opportunities_per_day", 0.6362697048),
        "THROUGHPUT_MULTIPLIER": result.get("throughput_multiplier"),
        "PROJECTED_DAYS_TO_30": result.get("projected_days_to_30_buy_only"),
        "PRICE_PRECISION": result.get("price_precision"),
        "PIP_HANDLING": result.get("pip_handling"),
        "ATR_NORMALIZATION": result.get("atr_normalization"),
        "PL_NORMALIZATION": result.get("pl_normalization"),
        "REPLAY_GRANTED_QUALIFYING_CREDIT": result.get("replay_grants_qualifying_credit", False),
        "CURRENT_COLLECTOR_UNTOUCHED": result.get("current_collector_untouched", True),
    }


def _load_process_credentials() -> tuple[str, str]:
    token = os.environ.get("OANDA_API_TOKEN", "")
    account = os.environ.get("OANDA_ACCOUNT_ID", "")
    if not token or not account:
        raise ValueError("PROCESS_OANDA_PRACTICE_CREDENTIALS_REQUIRED")
    return token, account


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the deterministic multi-pair M5 replay bridge.")
    parser.add_argument("--runtime-root", default=str(REPLAY_ROOT))
    parser.add_argument("--candle-count", type=int, default=DEFAULT_CANDLE_COUNT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    token, account = _load_process_credentials()
    client = OandaReadOnlyClient(api_token=token, account_id=account, environment="practice")
    result = run_multipair_m5_replay(
        client,
        runtime_root=Path(args.runtime_root),
        candle_count=args.candle_count,
    )
    summary = summarize_replay_bridge(result)
    if args.json:
        print(_stable_json(summary), end="")
    else:
        for key, value in summary.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
