"""Closed M5 feature snapshots. Pure calculations; no market/account I/O."""
from datetime import datetime, timedelta, timezone
import math
from automation.forex_engine import indicators
from automation.forex_engine.models import Candle
from automation.forex_engine.forex_scalping_techniques_v1 import ema, rsi, bollinger_state


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("TIMESTAMP_TIMEZONE_MISSING")
    return result.astimezone(timezone.utc)


def ny_time(moment):
    """Same US rule as session-inventory USD offsets, bounded to approved years."""
    if moment.tzinfo is None or moment.year not in (2024, 2025):
        raise ValueError("UNSUPPORTED_RESEARCH_CALENDAR")
    moment = moment.astimezone(timezone.utc)
    march = datetime(moment.year, 3, 1, 7, tzinfo=timezone.utc)
    start = march + timedelta(days=(6-march.weekday()) % 7+7)
    november = datetime(moment.year, 11, 1, 6, tzinfo=timezone.utc)
    end = november + timedelta(days=(6-november.weekday()) % 7)
    return moment.astimezone(timezone(timedelta(hours=-4 if start <= moment < end else -5)))


def no_entry(moment):
    local = ny_time(moment)
    minute = local.hour*60+local.minute
    return (960 <= minute < 1035 or local.weekday() == 5
            or (local.weekday() == 4 and minute >= 960)
            or (local.weekday() == 6 and minute < 1035)
            or (local.month, local.day) in {(1, 1), (12, 25)})


def financing_exit(moment):
    local = ny_time(moment)
    deadline = local.replace(hour=16, minute=30, second=0, microsecond=0)
    if local >= deadline:
        deadline += timedelta(days=1)
    return deadline.astimezone(timezone.utc)


def validate_bar(row, pair):
    if row.get("instrument") != pair or row.get("complete") is not True:
        raise ValueError("INCOMPLETE_OR_WRONG_INSTRUMENT")
    stamp = utc(row["timestamp"])
    if stamp.second or stamp.microsecond or stamp.minute % 5:
        raise ValueError("OFF_GRID_M5_TIMESTAMP")
    for side in ("bid", "ask", "mid"):
        o, h, l, c = [float(row[side][k]) for k in ("o", "h", "l", "c")]
        if not all(math.isfinite(x) and x > 0 for x in (o, h, l, c)):
            raise ValueError("INVALID_PRICE")
        if l > min(o, c) or h < max(o, c) or l > h:
            raise ValueError("OHLC_INVARIANT")
    if any(float(row["bid"][k]) > float(row["ask"][k]) for k in ("o", "h", "l", "c")):
        raise ValueError("CROSSED_BID_ASK")
    return stamp


def snapshots(pair, rows, *, setup_id="PKT044_ST3_2_TWO_CLOSE"):
    """Reuse tested ST/ATR/RSI/EMA; reset history at every missing M5 bar.

    Context cannot alter A/B decisions. Pivots are available at confirmation,
    not backdated. Undefined ratios and unavailable evidence remain None.
    """
    output, start = [], 0
    stamps = [validate_bar(row, pair) for row in rows]
    if stamps != sorted(set(stamps)):
        raise ValueError("NONCHRONOLOGICAL_OR_DUPLICATE_BAR")
    boundaries = [i for i in range(1, len(rows)) if stamps[i]-stamps[i-1] != timedelta(minutes=5)] + [len(rows)]
    for end in boundaries:
        segment = rows[start:end]
        candles = [Candle(pair, "M5", row["timestamp"], *[float(row["mid"][k]) for k in ("o", "h", "l", "c")], 0, "CERTIFIED_M5") for row in segment]
        if not candles:
            continue
        closes = [c.close for c in candles]
        trend, strength = indicators.supertrend(candles, 3, 2.0), rsi(closes, 14)
        fast, slow, context = ema(closes, 12), ema(closes, 26), ema(closes, 20)
        macd = [None if a is None or b is None else a-b for a, b in zip(fast, slow)]
        macd_signal = [None]*min(25, len(closes)) + ema([x for x in macd if x is not None], 9)
        last_direction, age, active, pending, count = 0, 0, None, None, 0
        swing_high = swing_low = None
        for i, candle in enumerate(candles):
            t, event = trend[i], 0
            direction = t["direction"]
            age = age+1 if direction == last_direction else 0
            last_direction = direction
            if direction:
                if direction == active:
                    pending, count = None, 0
                else:
                    count = count+1 if pending == direction else 1
                    pending = direction
                    if count == 2:
                        active, event, pending, count = direction, direction, None, 0
            available = stamps[start+i]+timedelta(minutes=5)
            if i >= 4:
                window = candles[i-4:i+1]
                pivot = window[2]
                if all(pivot.high > x.high for j, x in enumerate(window) if j != 2):
                    swing_high = {"value": pivot.high, "turning_time": pivot.timestamp, "available_at": available.isoformat()}
                if all(pivot.low < x.low for j, x in enumerate(window) if j != 2):
                    swing_low = {"value": pivot.low, "turning_time": pivot.timestamp, "available_at": available.isoformat()}
            span, atr = candle.high-candle.low, t["atr"]
            recent = closes[max(0, i-19):i+1]
            mean = sum(recent)/20 if len(recent) == 20 else None
            std = (sum((x-mean)**2 for x in recent)/20)**0.5 if mean is not None else None
            output.append({"pair": pair, "timeframe": "M5", "source": "CERTIFIED_M5_COMPLETED",
                "timestamp": candle.timestamp, "decision_time": available.isoformat(),
                "feature_available_at": available.isoformat(), "latest_source_time": available.isoformat(),
                "setup_id": setup_id, "segment_start": start,
                "open": candle.open, "high": candle.high, "low": candle.low, "close": candle.close,
                "range": span, "body_range": abs(candle.close-candle.open)/span if span else None,
                "upper_wick": candle.high-max(candle.open, candle.close),
                "lower_wick": min(candle.open, candle.close)-candle.low,
                "close_location": (candle.close-candle.low)/span if span else None,
                "atr3": atr, "rsi14": strength[i], "supertrend": t["supertrend"],
                "upper_band": t["upper_band"], "lower_band": t["lower_band"],
                "direction": direction, "trend_age": age, "event_direction": event,
                "distance_supertrend": candle.close-t["supertrend"] if atr is not None else None,
                "distance_supertrend_atr": (candle.close-t["supertrend"])/atr if atr else None,
                "ema12": fast[i], "ema26": slow[i], "ema20": context[i],
                "ema20_slope": context[i]-context[i-1] if i and context[i-1] is not None else None,
                "macd12_26": macd[i], "macd_signal9": macd_signal[i],
                "momentum12": math.log(candle.close/closes[i-12]) if i >= 12 else None,
                "bollinger_mean20": mean, "bollinger_upper": mean+2*std if std is not None else None,
                "bollinger_lower": mean-2*std if std is not None else None,
                "bandwidth": 4*std/mean if mean else None,
                "bollinger_prior_window_state": bollinger_state(closes, i),
                "confirmed_swing_high": swing_high, "confirmed_swing_low": swing_low,
                "spread_close": float(segment[i]["ask"]["c"])-float(segment[i]["bid"]["c"]),
                "ny_hour": ny_time(available).hour, "activity_count": segment[i].get("volume"),
                "activity_meaning": "PROVIDER_CANDLE_PRICE_UPDATE_COUNT_NOT_TRADED_VOLUME",
                "adx": None, "unavailable": {"adx": "EXISTING_ADX_STARTUP_NOT_CERTIFIED_FOR_SHARED_CONTEXT",
                    "intrabar_path": "OHLC_NOT_ORDERED_QUOTES", "true_volume": "NO_TRADE_TAPE"}})
        start = end
    return output
