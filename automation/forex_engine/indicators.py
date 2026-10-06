"""PAPER_ONLY indicator calculations for local forex edge research."""

from automation.forex_engine.market_data import validate_candle_sequence


def research_bars_v1(bars, interval_seconds=300):
    """Strict closed-bar research contract. Missing/open-position data is never interpolated."""
    from datetime import datetime, timezone
    from math import isfinite
    if type(interval_seconds) is not int or interval_seconds <= 0:
        raise ValueError("RESEARCH_BAR_INTERVAL_INVALID")
    previous = None
    result = []
    for bar in bars:
        if not isinstance(bar, dict) or not {"timestamp", "o", "h", "l", "c"} <= set(bar):
            raise ValueError("RESEARCH_BAR_MISSING")
        timestamp = datetime.fromisoformat(bar["timestamp"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("RESEARCH_BAR_TIMEZONE_REQUIRED")
        timestamp = timestamp.astimezone(timezone.utc)
        if previous is not None and (timestamp-previous).total_seconds() != interval_seconds:
            raise ValueError("RESEARCH_BAR_GAP")
        values = [bar[k] for k in ("o", "h", "l", "c")]
        if any(type(v) not in (float, int) or not isfinite(v) or v <= 0 for v in values) or not (
                bar["l"] <= min(bar["o"], bar["c"]) <= max(bar["o"], bar["c"]) <= bar["h"]):
            raise ValueError("RESEARCH_BAR_PRICE_INVALID")
        result.append({**bar, "timestamp": timestamp.isoformat()})
        previous = timestamp
    return result


def supertrend_research_v1(bars, period=14, multiplier=3.0, interval_seconds=300):
    """Independent public-math implementation: Wilder ATR, arithmetic seed.

    Initial direction uses close vs HL2. Ratchets use previous close; strict
    crossings flip. Zero ATR is neutral. No rounding feedback into the math.
    Values at bar i become available only at its close, never its open.
    """
    from datetime import datetime, timedelta
    from math import isfinite
    if type(period) is not int or not 2 <= period <= 1000 or type(multiplier) not in (float, int) or not isfinite(multiplier) or multiplier <= 0:
        raise ValueError("RESEARCH_SUPERTREND_PARAMETER_INVALID")
    rows = research_bars_v1(bars, interval_seconds)
    ranges, output = [], []
    volatility = upper = lower = None
    direction = 0
    for i, row in enumerate(rows):
        previous_close = rows[i-1]["c"] if i else row["c"]
        ranges.append(max(row["h"]-row["l"], abs(row["h"]-previous_close), abs(row["l"]-previous_close)))
        if i == period-1:
            volatility = sum(ranges)/period
        elif i >= period:
            volatility = (volatility*(period-1)+ranges[-1])/period
        band = None
        if volatility is not None and volatility > 0:
            midpoint = (row["h"]+row["l"])/2
            basic_upper, basic_lower = midpoint+multiplier*volatility, midpoint-multiplier*volatility
            upper = basic_upper if upper is None or basic_upper < upper or previous_close > upper else upper
            lower = basic_lower if lower is None or basic_lower > lower or previous_close < lower else lower
            if direction == 0:
                direction = 1 if row["c"] >= midpoint else -1
            elif direction == -1 and row["c"] > upper:
                direction = 1
            elif direction == 1 and row["c"] < lower:
                direction = -1
            band = lower if direction == 1 else upper
        else:
            direction = 0
        output.append({"timestamp": row["timestamp"],
            "available_at": (datetime.fromisoformat(row["timestamp"])+timedelta(seconds=interval_seconds)).isoformat(),
            "atr": volatility, "upper": upper, "lower": lower, "band": band, "direction": direction,
            "period": period, "multiplier": multiplier, "contract": "SUPERTREND_RESEARCH_V1"})
    return output


UP = 1
DOWN = -1
FLAT = 0


def true_range(candles):
    """Return deterministic true range values for a validated candle sequence."""
    validate_candle_sequence(candles)
    ranges = []
    previous_close = None
    for candle in candles:
        high_low = candle.high - candle.low
        if previous_close is None:
            ranges.append(round(high_low, 10))
        else:
            ranges.append(
                round(
                    max(
                        high_low,
                        abs(candle.high - previous_close),
                        abs(candle.low - previous_close),
                    ),
                    10,
                )
            )
        previous_close = candle.close
    return ranges


def atr(candles, period=14):
    """Return same-length ATR output. Values before enough data are None."""
    if period <= 0:
        raise ValueError("ATR period must be positive.")
    ranges = true_range(candles)
    values = []
    previous_atr = None
    for index, value in enumerate(ranges):
        if index + 1 < period:
            values.append(None)
            continue
        if index + 1 == period:
            previous_atr = sum(ranges[:period]) / period
        else:
            previous_atr = ((previous_atr * (period - 1)) + value) / period
        values.append(round(previous_atr, 10))
    return values


def supertrend(candles, period=10, multiplier=3.0):
    """Calculate Supertrend bands and direction using local candles only."""
    if multiplier <= 0:
        raise ValueError("Supertrend multiplier must be positive.")
    validate_candle_sequence(candles)
    atr_values = atr(candles, period)
    output = []
    final_upper = None
    final_lower = None
    previous_direction = FLAT

    for index, candle in enumerate(candles):
        atr_value = atr_values[index]
        if atr_value is None:
            output.append(
                {
                    "timestamp": candle.timestamp,
                    "atr": None,
                    "upper_band": None,
                    "lower_band": None,
                    "supertrend": None,
                    "direction": FLAT,
                }
            )
            continue

        hl2 = (candle.high + candle.low) / 2
        basic_upper = hl2 + multiplier * atr_value
        basic_lower = hl2 - multiplier * atr_value
        previous_close = candles[index - 1].close if index > 0 else candle.close

        if final_upper is None or basic_upper < final_upper or previous_close > final_upper:
            final_upper = basic_upper
        if final_lower is None or basic_lower > final_lower or previous_close < final_lower:
            final_lower = basic_lower

        if previous_direction == DOWN and candle.close > final_upper:
            direction = UP
        elif previous_direction in (UP, FLAT) and candle.close < final_lower:
            direction = DOWN
        elif previous_direction == FLAT:
            direction = UP if candle.close >= hl2 else DOWN
        else:
            direction = previous_direction

        trend_value = final_lower if direction == UP else final_upper
        output.append(
            {
                "timestamp": candle.timestamp,
                "atr": round(atr_value, 10),
                "upper_band": round(final_upper, 10),
                "lower_band": round(final_lower, 10),
                "supertrend": round(trend_value, 10),
                "direction": direction,
            }
        )
        previous_direction = direction
    return output
