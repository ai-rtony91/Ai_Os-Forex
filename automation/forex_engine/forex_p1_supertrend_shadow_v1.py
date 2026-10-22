"""P1 Supertrend adapter for shadow diagnostics only.

The adapter deliberately consumes the same sanitized candle-history contract as
the P1 production signal, but it has no execution, campaign, or state-writing
dependency.  The numerical implementation remains canonical in
``automation.forex_engine.indicators``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from automation.forex_engine.indicators import DOWN, FLAT, UP, supertrend
from automation.forex_engine.models import Candle
from automation.forex_engine.strategies import (
    SUPERTREND_PULLBACK_V1,
    SupertrendPullbackConfig,
)

VERSION = "forex_p1_supertrend_shadow_v1"
STRATEGY_NAME = SUPERTREND_PULLBACK_V1
_CANONICAL_CONFIG = SupertrendPullbackConfig()
ATR_LENGTH = _CANONICAL_CONFIG.atr_period
MULTIPLIER = _CANONICAL_CONFIG.supertrend_multiplier

SAFETY = {
    "paper_only": True,
    "shadow_only": True,
    "diagnostic_only": True,
    "production_feedback_allowed": False,
    "position_open_allowed": False,
    "qualifying_trade_credit_allowed": False,
    "production_pnl_mutation_allowed": False,
    "broker_write_performed": False,
    "practice_order_performed": False,
    "live_trade_performed": False,
    "money_movement_performed": False,
    "credentials_persisted": False,
}


def _positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"positive_{name}_required")
    return value


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"positive_{name}_required")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"positive_{name}_required") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"positive_{name}_required")
    return result


def _candles(history: Mapping[str, Any]) -> list[Candle]:
    raw = history.get("candles") if isinstance(history, Mapping) else None
    if not isinstance(raw, list) or not raw:
        raise ValueError("sanitized_market_history_required")
    instrument = str(history.get("instrument", "EUR_USD")).replace("_", "")
    timeframe = str(history.get("granularity", "M5")).lower()
    result: list[Candle] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("invalid_shadow_candle")
        try:
            candle = Candle(
                symbol=instrument,
                timeframe=timeframe,
                timestamp=str(item["observed_at_utc"]),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item.get("volume", 0)),
                source="sanitized_p1_shadow_history",
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid_shadow_candle") from exc
        result.append(candle)
    return result


def evaluate_supertrend_shadow(
    history: Mapping[str, Any],
    *,
    atr_length: int = ATR_LENGTH,
    multiplier: float = MULTIPLIER,
) -> dict[str, Any]:
    """Return an explicit, non-executable Supertrend observation."""
    period = _positive_integer(atr_length, "atr_length")
    factor = _positive_number(multiplier, "multiplier")
    candles = _candles(history)
    base = {
        "version": VERSION,
        "strategy_name": STRATEGY_NAME,
        "mode": "PAPER_ONLY",
        "paper_only": True,
        "atr_period": period,
        "atr_length": period,
        "multiplier": factor,
        "candle_count": len(candles),
        "observed_at_utc": candles[-1].timestamp,
        **SAFETY,
    }
    if len(candles) < period + 2:
        return {
            **base,
            "supertrend_direction": "INSUFFICIENT_DATA",
            "supertrend_value": None,
            "atr_value": None,
            "price_distance_to_supertrend": None,
            "supertrend_flip_this_cycle": False,
            "supertrend_bars_in_direction": 0,
        }

    rows = supertrend(candles, period=period, multiplier=factor)
    latest = rows[-1]
    if latest["direction"] == FLAT or latest["supertrend"] is None:
        direction = "INSUFFICIENT_DATA"
    else:
        direction = "BULLISH" if latest["direction"] == UP else "BEARISH"

    previous = rows[-2] if len(rows) > 1 else None
    flipped = bool(
        previous
        and previous["direction"] in (UP, DOWN)
        and latest["direction"] in (UP, DOWN)
        and previous["direction"] != latest["direction"]
    )
    bars = 0
    if latest["direction"] in (UP, DOWN):
        for row in reversed(rows):
            if row["direction"] != latest["direction"]:
                break
            bars += 1

    value = latest["supertrend"]
    return {
        **base,
        "supertrend_direction": direction,
        "supertrend_value": value,
        "atr_value": latest["atr"],
        "price_distance_to_supertrend": (
            round(candles[-1].close - float(value), 10) if value is not None else None
        ),
        "supertrend_flip_this_cycle": flipped,
        "supertrend_bars_in_direction": bars,
    }


def supertrend_shadow_safety_state() -> dict[str, Any]:
    """Expose the immutable isolation boundary for validators and reports."""
    return {
        "version": VERSION,
        "strategy_name": STRATEGY_NAME,
        "mode": "PAPER_ONLY",
        "atr_period": ATR_LENGTH,
        "atr_length": ATR_LENGTH,
        "multiplier": MULTIPLIER,
        **SAFETY,
    }
