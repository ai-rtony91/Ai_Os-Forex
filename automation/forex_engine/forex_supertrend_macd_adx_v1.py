"""Packet 032 deterministic Supertrend, MACD, and ADX calculations.

The module is local research code only.  It uses completed OHLC candles passed
by the caller and contains no broker, credential, order, or network path.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PACKET_ID = "PKT-EAST-FOREX-MTF-GROSS-EDGE-DISCOVERY-032"
SCHEMA = "AIOS_FOREX_SUPERTREND_MACD_ADX.v1"


@dataclass(frozen=True)
class Ohlc:
    time: str
    open: float
    high: float
    low: float
    close: float
    bid_close: float | None = None
    ask_close: float | None = None
    complete: bool = True


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def module_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def normalize_candle(row: Any) -> Ohlc:
    """Normalize repository candle shapes into one deterministic OHLC record."""
    if isinstance(row, Ohlc):
        return row
    if "mid" in row:
        mid = row["mid"]
        bid = row.get("bid") or {}
        ask = row.get("ask") or {}
        stamp = row.get("timestamp") or row.get("time") or row.get("observed_at_utc")
        return Ohlc(
            time=str(stamp),
            open=float(mid["o"]),
            high=float(mid["h"]),
            low=float(mid["l"]),
            close=float(mid["c"]),
            bid_close=float(bid["c"]) if "c" in bid else None,
            ask_close=float(ask["c"]) if "c" in ask else None,
            complete=bool(row.get("complete", True)),
        )
    stamp = row.get("timestamp") or row.get("time") or row.get("observed_at_utc")
    return Ohlc(
        time=str(stamp),
        open=float(row.get("open", row.get("o"))),
        high=float(row.get("high", row.get("h"))),
        low=float(row.get("low", row.get("l"))),
        close=float(row.get("close", row.get("c"))),
        bid_close=float(row["bid_close"]) if "bid_close" in row else None,
        ask_close=float(row["ask_close"]) if "ask_close" in row else None,
        complete=bool(row.get("complete", True)),
    )


def normalize_candles(rows: Iterable[Any]) -> list[Ohlc]:
    return [normalize_candle(row) for row in rows if normalize_candle(row).complete]


def true_ranges(candles: list[Ohlc]) -> list[float | None]:
    out: list[float | None] = []
    prev_close: float | None = None
    for candle in candles:
        if prev_close is None:
            tr = candle.high - candle.low
        else:
            tr = max(candle.high - candle.low, abs(candle.high - prev_close), abs(candle.low - prev_close))
        out.append(max(0.0, tr))
        prev_close = candle.close
    return out


def wilder(values: list[float | None], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(values)
    clean: list[float] = []
    for index, value in enumerate(values):
        if value is None:
            clean.append(0.0)
        else:
            clean.append(float(value))
        if index == period - 1:
            out[index] = sum(clean[:period]) / period
        elif index >= period:
            prev = out[index - 1]
            assert prev is not None
            out[index] = ((prev * (period - 1)) + clean[index]) / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for index in range(period, len(values)):
        current = (values[index] * alpha) + (current * (1 - alpha))
        out[index] = current
    return out


def atr(candles: list[Ohlc], period: int) -> list[float | None]:
    return wilder(true_ranges(candles), period)


def supertrend(candles_input: Iterable[Any], period: int = 10, multiplier: float = 3.0) -> list[dict[str, Any]]:
    candles = normalize_candles(candles_input)
    atr_values = atr(candles, period)
    out: list[dict[str, Any]] = []
    final_upper: float | None = None
    final_lower: float | None = None
    trend = 0
    for index, candle in enumerate(candles):
        atr_value = atr_values[index]
        if atr_value is None:
            out.append({"time": candle.time, "value": None, "trend": 0, "atr": None})
            continue
        hl2 = (candle.high + candle.low) / 2.0
        basic_upper = hl2 + multiplier * atr_value
        basic_lower = hl2 - multiplier * atr_value
        prev_close = candles[index - 1].close if index else candle.close
        if final_upper is None or basic_upper < final_upper or prev_close > final_upper:
            final_upper = basic_upper
        if final_lower is None or basic_lower > final_lower or prev_close < final_lower:
            final_lower = basic_lower
        if trend >= 0:
            trend = -1 if candle.close < final_lower else 1
        else:
            trend = 1 if candle.close > final_upper else -1
        value = final_lower if trend == 1 else final_upper
        out.append({"time": candle.time, "value": value, "trend": trend, "atr": atr_value})
    return out


def macd(candles_input: Iterable[Any], fast: int = 12, slow: int = 26, signal: int = 9) -> list[dict[str, Any]]:
    candles = normalize_candles(candles_input)
    closes = [c.close for c in candles]
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    macd_line: list[float | None] = []
    for f_value, s_value in zip(fast_ema, slow_ema):
        macd_line.append(None if f_value is None or s_value is None else f_value - s_value)
    signal_input = [0.0 if value is None else value for value in macd_line]
    signal_line = ema(signal_input, signal)
    out: list[dict[str, Any]] = []
    for index, candle in enumerate(candles):
        line = macd_line[index]
        sig = signal_line[index] if line is not None else None
        hist = None if line is None or sig is None else line - sig
        out.append({"time": candle.time, "macd": line, "signal": sig, "histogram": hist})
    return out


def adx(candles_input: Iterable[Any], period: int = 14) -> list[dict[str, Any]]:
    candles = normalize_candles(candles_input)
    tr = true_ranges(candles)
    plus_dm: list[float | None] = [0.0]
    minus_dm: list[float | None] = [0.0]
    for index in range(1, len(candles)):
        up_move = candles[index].high - candles[index - 1].high
        down_move = candles[index - 1].low - candles[index].low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
    sm_tr = wilder(tr, period)
    sm_plus = wilder(plus_dm, period)
    sm_minus = wilder(minus_dm, period)
    dx_values: list[float | None] = []
    plus_di_values: list[float | None] = []
    minus_di_values: list[float | None] = []
    for tr_value, plus_value, minus_value in zip(sm_tr, sm_plus, sm_minus):
        if tr_value is None or tr_value == 0 or plus_value is None or minus_value is None:
            plus_di_values.append(None)
            minus_di_values.append(None)
            dx_values.append(None)
            continue
        plus_di = 100.0 * plus_value / tr_value
        minus_di = 100.0 * minus_value / tr_value
        denom = plus_di + minus_di
        dx = None if denom == 0 else 100.0 * abs(plus_di - minus_di) / denom
        plus_di_values.append(plus_di)
        minus_di_values.append(minus_di)
        dx_values.append(dx)
    adx_values = wilder(dx_values, period)
    out: list[dict[str, Any]] = []
    for index, candle in enumerate(candles):
        out.append(
            {
                "time": candle.time,
                "plus_di": plus_di_values[index],
                "minus_di": minus_di_values[index],
                "adx": adx_values[index],
            }
        )
    return out


def fidelity_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "packet_id": PACKET_ID,
        "status": "INDICATOR_FIDELITY_IMPLEMENTED",
        "supertrend": {
            "atr_method": "Wilder true range smoothing",
            "band_carry_forward": True,
            "trend_state_transition": True,
            "completed_candles_only": True,
        },
        "macd": {
            "ema_method": "deterministic seeded SMA then EMA recursion",
            "line_signal_histogram": True,
            "completed_candles_only": True,
        },
        "adx": {
            "true_range": True,
            "plus_dm_minus_dm": True,
            "wilder_smoothed_di_dx_adx": True,
            "completed_candles_only": True,
        },
        "indicator_code_hash": module_hash(),
        "broker_or_live_api_work": "NO",
    }
