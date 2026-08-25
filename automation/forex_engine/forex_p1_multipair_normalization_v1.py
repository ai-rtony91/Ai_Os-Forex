"""Normalization helpers for the normalized multi-pair P1 paper collector."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from automation.forex_engine.forex_persistent_all_pairs_m1_m2_observer_v1 import (
    completed_candles,
    eligible_forex_instruments,
    quote_currency_to_usd,
    validate_observer_client,
)
from automation.forex_engine.models import Candle, Direction
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient
from automation.forex_engine.strategies import (
    SUPERTREND_PULLBACK_V1,
    SupertrendPullbackConfig,
    evaluate_supertrend_pullback,
    realized_r_multiple,
)

M5_GRANULARITY = "M5"
DEFAULT_CANDLE_COUNT = 50
PROTOCOL_VERSION = "supertrend_pullback_multipair_long_v1"
SCHEMA = "AIOS_FOREX_MULTIPAIR_NORMALIZATION_V1"
STRATEGY_ID = SUPERTREND_PULLBACK_V1
TARGET_RR = 2.0
MIN_RR = 1.5
ATR_THRESHOLD_PIPS = 4.0


@dataclass(frozen=True)
class NormalizedInstrument:
    instrument: str
    display_precision: int
    pip_location: int
    tradeable: bool
    priceable: bool

    @property
    def base_currency(self) -> str:
        return self.instrument.split("_", 1)[0]

    @property
    def quote_currency(self) -> str:
        return self.instrument.split("_", 1)[1]

    @property
    def pip_size(self) -> float:
        return 10 ** self.pip_location


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


def _normalized_direction(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction_entry_price(direction: str, snapshot: Mapping[str, Any]) -> float:
    if direction == Direction.BUY:
        return _finite(snapshot["ask"], "ask")
    if direction == Direction.SELL:
        return _finite(snapshot["bid"], "bid")
    raise ValueError("unsupported_direction")


def _candidate_geometry_valid(direction: str, entry: float, stop: float, target: float) -> bool:
    if direction == Direction.BUY:
        return stop < entry < target
    if direction == Direction.SELL:
        return target < entry < stop
    return False


def _candidate_id_payload(
    *,
    instrument: str,
    timestamp: str,
    direction: str,
    entry: float,
    stop: float,
    target: float,
) -> dict[str, Any]:
    return {
        "instrument": instrument,
        "timestamp": timestamp,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
    }


def discover_fixed_universe(client: OandaReadOnlyClient) -> dict[str, Any]:
    validate_observer_client(client)
    payload = _as_mapping(client.discover_instruments())
    discovered = eligible_forex_instruments(payload)
    raw = payload.get("instruments", [])
    eligible: list[NormalizedInstrument] = []
    excluded: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        raise ValueError("instruments_list_required")
    for item in raw:
        if not isinstance(item, Mapping):
            excluded.append({"instrument": "UNKNOWN", "reason": "invalid_instrument_record"})
            continue
        name = str(item.get("name", "")).upper()
        if item.get("type") != "CURRENCY":
            excluded.append({"instrument": name or "UNKNOWN", "reason": "not_currency"})
            continue
        if item.get("tradeable") is False or item.get("halted") is True:
            excluded.append({"instrument": name or "UNKNOWN", "reason": "not_tradeable"})
            continue
        if item.get("displayPrecision") is None or item.get("pipLocation") is None:
            excluded.append({"instrument": name or "UNKNOWN", "reason": "missing_metadata"})
            continue
        try:
            eligible.append(
                NormalizedInstrument(
                    instrument=name,
                    display_precision=int(item["displayPrecision"]),
                    pip_location=int(item["pipLocation"]),
                    tradeable=True,
                    priceable=True,
                )
            )
        except (TypeError, ValueError):
            excluded.append({"instrument": name or "UNKNOWN", "reason": "invalid_metadata"})
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
    return {
        "schema": SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "discovered_pairs": [item.instrument for item in eligible],
        "eligible_instruments": [item.__dict__ | {"pip_size": item.pip_size} for item in eligible],
        "excluded_instruments": excluded,
        "universe_fingerprint": hashlib.sha256(_stable_json(fingerprint_source).encode("utf-8")).hexdigest(),
        "raw_universe_status": discovered.get("universe_status"),
        "broker_write_performed": False,
        "practice_order_performed": False,
        "live_trade_performed": False,
        "money_movement_performed": False,
        "credentials_persisted": False,
    }


def sanitized_price_snapshot(
    pricing_payload: Mapping[str, Any],
    *,
    instrument: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = _as_mapping(pricing_payload)
    prices = payload.get("prices")
    if not isinstance(prices, list):
        raise ValueError("prices_list_required")
    selected: Mapping[str, Any] | None = None
    for item in prices:
        if isinstance(item, Mapping) and str(item.get("instrument", "")).upper() == instrument:
            selected = item
            break
    if selected is None:
        raise ValueError("instrument_price_missing")
    bids, asks = selected.get("bids"), selected.get("asks")
    if not isinstance(bids, list) or not bids or not isinstance(asks, list) or not asks:
        raise ValueError("bid_ask_required")
    bid = _finite(bids[0].get("price"), "bid")
    ask = _finite(asks[0].get("price"), "ask")
    if ask <= bid:
        raise ValueError("positive_spread_required")
    quote_time = selected.get("time")
    if not isinstance(quote_time, str) or not quote_time.endswith("Z"):
        raise ValueError("explicit_utc_timestamp_required")
    observed = _stamp(datetime.fromisoformat(quote_time.replace("Z", "+00:00")))
    current = now or datetime.now(timezone.utc)
    return {
        "schema": "AIOS_P1_SUPERVISED_PAPER_MARKET_SNAPSHOT.v1",
        "evidence_type": "SANITIZED_READ_ONLY_MARKET_SNAPSHOT",
        "provenance": "GENUINE_OBSERVED_MARKET_DATA",
        "instrument": instrument,
        "observed_at_utc": observed,
        "bid": bid,
        "ask": ask,
        "mid": round((bid + ask) / 2.0, 10),
        "spread": round(ask - bid, 10),
        "source_status": "VALID",
        "stale_status": "VALID",
        "read_only": True,
        "broker_write_performed": False,
        "credentials_included": False,
        "account_identifier_included": False,
        "raw_payload_included": False,
        "current_utc": _stamp(current),
        "data_status": "FRESH",
    }


def _candle_value(item: Mapping[str, Any], field: str) -> float:
    if field in item:
        return _finite(item[field], field)
    mid = item.get("mid")
    if isinstance(mid, Mapping):
        mapping = {"open": "o", "high": "h", "low": "l", "close": "c"}
        if mapping[field] in mid:
            return _finite(mid[mapping[field]], field)
    raise ValueError(f"missing_{field}")


def fetch_completed_m5_history(
    client: OandaReadOnlyClient,
    instrument: str,
    *,
    candle_count: int = DEFAULT_CANDLE_COUNT,
) -> dict[str, Any]:
    payload = _as_mapping(
        client.observation_candles(instrument, granularity=M5_GRANULARITY, count=candle_count)
    )
    candles = completed_candles(payload, instrument=instrument, granularity=M5_GRANULARITY)
    if len(candles) < candle_count:
        raise ValueError("insufficient_completed_m5_history")
    return {
        "instrument": instrument,
        "granularity": M5_GRANULARITY,
        "requested_count": candle_count,
        "returned_count": len(candles),
        "candles": [item.__dict__ for item in candles],
        "complete": True,
        "sanitized": True,
        "raw_payload_included": False,
    }


def candles_to_strategy_window(history: Mapping[str, Any], *, instrument: str) -> list[Candle]:
    candles = history.get("candles")
    if not isinstance(candles, list):
        raise ValueError("candles_list_required")
    result: list[Candle] = []
    for item in candles:
        if not isinstance(item, Mapping):
            continue
        timestamp = str(item.get("observed_at_utc") or item.get("timestamp") or "")
        if not timestamp.endswith("Z"):
            raise ValueError("explicit_utc_timestamp_required")
        result.append(
            Candle(
                symbol=instrument.replace("_", ""),
                timeframe="5m",
                timestamp=timestamp,
                open=_candle_value(item, "open"),
                high=_candle_value(item, "high"),
                low=_candle_value(item, "low"),
                close=_candle_value(item, "close"),
                volume=float(item.get("volume", 0)),
                source="sanitized_market_history",
            )
        )
    if not result:
        raise ValueError("no_candles_available")
    return result


def quote_mids_from_pricing(pricing_payload: Mapping[str, Any]) -> dict[str, float]:
    payload = _as_mapping(pricing_payload)
    prices = payload.get("prices")
    if not isinstance(prices, list):
        return {}
    mids: dict[str, float] = {}
    for item in prices:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("instrument", "")).upper()
        bids, asks = item.get("bids"), item.get("asks")
        if not isinstance(bids, list) or not bids or not isinstance(asks, list) or not asks:
            continue
        try:
            bid = float(bids[0]["price"])
            ask = float(asks[0]["price"])
        except (TypeError, ValueError, KeyError):
            continue
        if ask > bid:
            mids[name] = round((bid + ask) / 2.0, 10)
    return mids


def normalized_min_atr_price(instrument: str) -> float:
    if not isinstance(instrument, str) or "_" not in instrument:
        raise ValueError("forex_instrument_required")
    quote = instrument.split("_", 1)[1]
    pip_size = 0.01 if quote == "JPY" else 0.0001
    return round(ATR_THRESHOLD_PIPS * pip_size, 10)


def normalized_strategy_config(instrument: str, *, base_config: SupertrendPullbackConfig | None = None) -> SupertrendPullbackConfig:
    config = base_config or SupertrendPullbackConfig()
    return replace(config, min_atr=normalized_min_atr_price(instrument))


def _historical_mba_candle(
    replay_cache: Mapping[str, Any],
    instrument: str,
    timestamp: str,
) -> Mapping[str, Any] | None:
    history = replay_cache.get("pair_histories", {}).get(instrument)
    if not isinstance(history, Mapping):
        return None
    candles = history.get("sanitized_candles") or history.get("candles")
    if not isinstance(candles, list):
        return None
    for item in candles:
        if isinstance(item, Mapping) and str(item.get("timestamp")) == timestamp:
            return item
    return None


def historical_normalized_usd_pl(
    *,
    quote_currency: str,
    quote_pl: float,
    conversion_timestamp: str,
    replay_cache: Mapping[str, Any],
) -> dict[str, Any]:
    quote_currency = str(quote_currency).upper()
    if quote_currency == "USD":
        return {
            "quote_currency": "USD",
            "quote_currency_pl": round(quote_pl, 8),
            "conversion_pair": "USD_USD",
            "conversion_timestamp": conversion_timestamp,
            "conversion_side": "NATIVE",
            "conversion_rate": 1.0,
            "normalized_usd_pl": round(quote_pl, 8),
            "conversion_provenance": "GENUINE_OANDA_HISTORICAL_MBA_CONVERSION",
            "pl_normalization_status": "AVAILABLE",
        }
    direct_pair = f"{quote_currency}_USD"
    inverse_pair = f"USD_{quote_currency}"
    direct_candle = _historical_mba_candle(replay_cache, direct_pair, conversion_timestamp)
    if direct_candle is not None and isinstance(direct_candle.get("bid"), Mapping) and isinstance(direct_candle.get("ask"), Mapping):
        bid = _finite(direct_candle["bid"].get("close"), "conversion_bid")
        ask = _finite(direct_candle["ask"].get("close"), "conversion_ask")
        if quote_pl >= 0:
            return {
                "quote_currency": quote_currency,
                "quote_currency_pl": round(quote_pl, 8),
                "conversion_pair": direct_pair,
                "conversion_timestamp": conversion_timestamp,
                "conversion_side": "BID",
                "conversion_rate": bid,
                "normalized_usd_pl": round(quote_pl * bid, 8),
                "conversion_provenance": "GENUINE_OANDA_HISTORICAL_MBA_CONVERSION",
                "pl_normalization_status": "AVAILABLE",
            }
        return {
            "quote_currency": quote_currency,
            "quote_currency_pl": round(quote_pl, 8),
            "conversion_pair": direct_pair,
            "conversion_timestamp": conversion_timestamp,
            "conversion_side": "ASK",
            "conversion_rate": ask,
            "normalized_usd_pl": round(quote_pl * ask, 8),
            "conversion_provenance": "GENUINE_OANDA_HISTORICAL_MBA_CONVERSION",
            "pl_normalization_status": "AVAILABLE",
        }
    inverse_candle = _historical_mba_candle(replay_cache, inverse_pair, conversion_timestamp)
    if inverse_candle is not None and isinstance(inverse_candle.get("bid"), Mapping) and isinstance(inverse_candle.get("ask"), Mapping):
        bid = _finite(inverse_candle["bid"].get("close"), "conversion_bid")
        ask = _finite(inverse_candle["ask"].get("close"), "conversion_ask")
        if quote_pl >= 0:
            return {
                "quote_currency": quote_currency,
                "quote_currency_pl": round(quote_pl, 8),
                "conversion_pair": inverse_pair,
                "conversion_timestamp": conversion_timestamp,
                "conversion_side": "ASK",
                "conversion_rate": ask,
                "normalized_usd_pl": round(quote_pl / ask, 8),
                "conversion_provenance": "GENUINE_OANDA_HISTORICAL_MBA_CONVERSION",
                "pl_normalization_status": "AVAILABLE",
            }
        return {
            "quote_currency": quote_currency,
            "quote_currency_pl": round(quote_pl, 8),
            "conversion_pair": inverse_pair,
            "conversion_timestamp": conversion_timestamp,
            "conversion_side": "BID",
            "conversion_rate": bid,
            "normalized_usd_pl": round(quote_pl / bid, 8),
            "conversion_provenance": "GENUINE_OANDA_HISTORICAL_MBA_CONVERSION",
            "pl_normalization_status": "AVAILABLE",
        }
    return {
        "quote_currency": quote_currency,
        "quote_currency_pl": round(quote_pl, 8),
        "conversion_pair": None,
        "conversion_timestamp": conversion_timestamp,
        "conversion_side": None,
        "conversion_rate": None,
        "normalized_usd_pl": None,
        "conversion_provenance": "GENUINE_OANDA_HISTORICAL_MBA_CONVERSION",
        "pl_normalization_status": "UNAVAILABLE_FOR_TRADE",
    }


def replay_candidate(
    instrument: NormalizedInstrument,
    candles: Sequence[Candle],
    snapshot: Mapping[str, Any],
    *,
    strategy_config: SupertrendPullbackConfig | None = None,
) -> dict[str, Any] | None:
    config = normalized_strategy_config(instrument.instrument, base_config=strategy_config)
    evaluation = evaluate_supertrend_pullback(list(candles), config)
    if evaluation.get("accepted") is not True:
        return None
    signal = evaluation.get("signal")
    direction = _normalized_direction(getattr(signal, "direction", ""))
    if signal is None or direction not in (Direction.BUY, Direction.SELL):
        return None
    entry = _direction_entry_price(direction, snapshot)
    stop = _finite(signal.stop_loss, "stop_price")
    target = _finite(signal.take_profit, "target_price")
    if not _candidate_geometry_valid(direction, entry, stop, target):
        return None
    risk_distance = entry - stop if direction == Direction.BUY else stop - entry
    if risk_distance <= 0:
        return None
    risk_pips = risk_distance / instrument.pip_size
    planned_rr = (target - entry) / risk_distance if direction == Direction.BUY else (entry - target) / risk_distance
    if planned_rr < MIN_RR:
        return None
    return {
        "strategy_id": STRATEGY_ID,
        "strategy_name": STRATEGY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "instrument": instrument.instrument,
        "base_currency": instrument.base_currency,
        "quote_currency": instrument.quote_currency,
        "direction": direction,
        "timeframe": "M5",
        "display_precision": instrument.display_precision,
        "pip_location": instrument.pip_location,
        "pip_size": instrument.pip_size,
        "entry_price": round(entry, instrument.display_precision),
        "stop_price": round(stop, instrument.display_precision),
        "target_price": round(target, instrument.display_precision),
        "risk_distance": round(risk_distance, instrument.display_precision + 4),
        "risk_pips": round(risk_pips, 8),
        "planned_reward_risk": round(planned_rr, 8),
        "planned_target_reward_risk": TARGET_RR,
        "units": 100,
        "entry_rationale": f"normalized multi-pair {STRATEGY_ID} paper signal",
        "candidate_id": hashlib.sha256(
            json.dumps(
                _candidate_id_payload(
                    instrument=instrument.instrument,
                    timestamp=candles[-1].timestamp,
                    direction=direction,
                    entry=round(entry, instrument.display_precision),
                    stop=round(stop, instrument.display_precision),
                    target=round(target, instrument.display_precision),
                ),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:24],
        "status": "PAPER_ELIGIBLE",
        "sanitized": True,
        "current": True,
        "mode": "PAPER_ONLY",
        "paper_only": True,
        "signal": signal,
        "evaluation": evaluation,
        "quote_conversion_rate": quote_currency_to_usd(instrument.instrument, {}),
        "mfe_r": None,
        "mae_r": None,
        "realized_pl_usd": "NOT_COMPUTABLE",
    }


def calibrate_candidate_to_actual_entry(
    candidate: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    reward_risk: float | None = None,
) -> dict[str, Any]:
    direction = _normalized_direction(candidate.get("direction"))
    entry_side = _direction_entry_price(direction, snapshot)
    stop = _finite(candidate["stop_price"], "stop_price")
    planned_rr = reward_risk if reward_risk is not None else _finite(candidate.get("planned_target_reward_risk", TARGET_RR), "planned_target_reward_risk")
    if planned_rr <= 0:
        raise ValueError("invalid_reward_risk")
    if direction == Direction.BUY and not stop < entry_side:
        raise ValueError("invalid_actual_entry_geometry")
    if direction == Direction.SELL and not entry_side < stop:
        raise ValueError("invalid_actual_entry_geometry")
    risk_distance = entry_side - stop if direction == Direction.BUY else stop - entry_side
    target = entry_side + (risk_distance * planned_rr) if direction == Direction.BUY else entry_side - (risk_distance * planned_rr)
    adjusted = dict(candidate)
    adjusted["entry_price"] = round(entry_side, int(candidate.get("display_precision", 5)))
    adjusted["stop_price"] = round(stop, int(candidate.get("display_precision", 5)))
    adjusted["target_price"] = round(target, int(candidate.get("display_precision", 5)))
    adjusted["risk_distance"] = round(risk_distance, int(candidate.get("display_precision", 5)) + 4)
    adjusted["risk_amount"] = round(risk_distance * float(candidate.get("units", 100)), 8)
    adjusted["planned_reward_risk"] = round(planned_rr, 8)
    adjusted["planned_target_reward_risk"] = round(planned_rr, 8)
    adjusted["nominal_target_rr"] = round(planned_rr, 8)
    adjusted["effective_reward_risk"] = round((adjusted["target_price"] - adjusted["entry_price"]) / risk_distance, 8)
    adjusted["actual_paper_entry"] = adjusted["entry_price"]
    adjusted["signal_reference_entry"] = round(_finite(candidate.get("entry_price", entry_side), "entry_price"), int(candidate.get("display_precision", 5)))
    if not _candidate_geometry_valid(direction, adjusted["entry_price"], adjusted["stop_price"], adjusted["target_price"]):
        raise ValueError("invalid_actual_entry_geometry")
    return adjusted


def candidate_rank_key(candidate: Mapping[str, Any], snapshot: Mapping[str, Any]) -> tuple[float, float, float, str]:
    planned_rr = _finite(candidate.get("planned_reward_risk", 0.0), "planned_reward_risk")
    spread = _finite(snapshot["ask"], "ask") - _finite(snapshot["bid"], "bid")
    risk_distance = max(1e-12, _finite(candidate.get("risk_distance", 0.0), "risk_distance"))
    spread_to_risk = spread / risk_distance
    return (-planned_rr, spread_to_risk, -_finite(snapshot.get("bid", snapshot["ask"]), "bid"), str(candidate["instrument"]))


def normalized_trade_outcome(
    session: Mapping[str, Any],
    closing_snapshot: Mapping[str, Any],
    *,
    quote_mids: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    quote_mids = dict(quote_mids or {})
    direction = _normalized_direction(session.get("direction"))
    entry_price = float(session["entry_price"])
    if direction == Direction.SELL:
        realized_pl_quote = (entry_price - float(closing_snapshot["ask"])) * int(session["units"])
    else:
        realized_pl_quote = (float(closing_snapshot["bid"]) - entry_price) * int(session["units"])
    quote_currency = str(session["quote_currency"])
    realized_pl_usd: float | str = "NOT_COMPUTABLE"
    if quote_currency == "USD":
        realized_pl_usd = round(realized_pl_quote, 8)
    else:
        direct = quote_mids.get(f"{quote_currency}_USD")
        inverse = quote_mids.get(f"USD_{quote_currency}")
        if direct and direct > 0:
            realized_pl_usd = round(realized_pl_quote * direct, 8)
        elif inverse and inverse > 0:
            realized_pl_usd = round(realized_pl_quote / inverse, 8)
    risk = float(session["risk_amount"])
    realized_r = realized_r_multiple(realized_pl_quote, risk)
    return {
        "realized_pl_quote_currency": round(realized_pl_quote, 8),
        "realized_pl_usd": realized_pl_usd,
        "realized_r": realized_r,
        "roi_class": "POSITIVE_R" if (realized_r or 0) > 0 else ("NEGATIVE_R" if (realized_r or 0) < 0 else "FLAT_R"),
        "quote_currency": quote_currency,
    }
