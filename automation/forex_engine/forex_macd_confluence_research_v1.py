from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping, Sequence

from automation.forex_engine.models import Candle, Direction
from automation.forex_engine.strategies import evaluate_supertrend_pullback

FAST_EMA = 12
SLOW_EMA = 26
SIGNAL_EMA = 9
M5_GRANULARITY = "M5"
DEFAULT_CANDLE_COUNT = 50
REPLAY_CACHE_PATH = Path(".aios/runtime/forex_multipair_m5_replay_mba_v1/replay_cache.json")


@dataclass(frozen=True)
class TradeStats:
    signals: int
    accepted: int
    rejected: int
    closed: int
    buy: int
    sell: int
    wins: int
    losses: int
    flats: int
    win_rate: float
    expectancy_r: float
    profit_factor: float
    net_r: float
    max_drawdown_r: float
    max_loss_streak: int
    mean_mfe_r: float
    median_mfe_r: float
    mean_mae_r: float
    median_mae_r: float
    rejected_winners: int
    rejected_losers: int
    rejected_flats: int
    r_saved_by_rejecting_losers: float
    r_lost_by_rejecting_winners: float
    net_filter_value_r: float


def load_replay_cache(path: Path = REPLAY_CACHE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def ema_series(values: Sequence[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("ema_period_must_be_positive")
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    output: list[float] = []
    ema = float(values[0])
    output.append(ema)
    for value in values[1:]:
        ema = (float(value) * alpha) + (ema * (1.0 - alpha))
        output.append(ema)
    return output


def macd_series(closes: Sequence[float]) -> dict[str, list[float]]:
    fast = ema_series(closes, FAST_EMA)
    slow = ema_series(closes, SLOW_EMA)
    macd_line = [round(f - s, 12) for f, s in zip(fast, slow)]
    signal_line = ema_series(macd_line, SIGNAL_EMA)
    histogram = [round(m - s, 12) for m, s in zip(macd_line, signal_line)]
    return {
        "fast_ema": fast,
        "slow_ema": slow,
        "macd_line": macd_line,
        "signal_line": signal_line,
        "histogram": histogram,
    }


def macd_snapshot(closes: Sequence[float]) -> dict[str, float]:
    series = macd_series(closes)
    return {
        "macd_line": series["macd_line"][-1],
        "signal_line": series["signal_line"][-1],
        "histogram": series["histogram"][-1],
    }


def macd_values_at_index(candles: Sequence[Candle], index: int) -> dict[str, float]:
    if not candles:
        raise ValueError("candles_required")
    if index < 0 or index >= len(candles):
        raise IndexError("macd_index_out_of_range")
    closes = _closing_prices(candles[: index + 1])
    return macd_snapshot(closes)


def _to_candles(items: Sequence[Mapping[str, Any]], *, symbol: str) -> list[Candle]:
    candles: list[Candle] = []
    for item in items:
        if "open" in item and "high" in item and "low" in item and "close" in item:
            open_price = float(item["open"])
            high_price = float(item["high"])
            low_price = float(item["low"])
            close_price = float(item["close"])
        else:
            bid = item.get("bid")
            ask = item.get("ask")
            mid = item.get("mid")
            if isinstance(mid, Mapping):
                open_price = float(mid.get("open", mid.get("o")))
                high_price = float(mid.get("high", mid.get("h")))
                low_price = float(mid.get("low", mid.get("l")))
                close_price = float(mid.get("close", mid.get("c")))
            elif isinstance(bid, Mapping) and isinstance(ask, Mapping):
                open_price = float(bid.get("open", bid.get("close")))
                high_price = float(ask.get("high", ask.get("close")))
                low_price = float(bid.get("low", bid.get("close")))
                close_price = float(bid.get("close"))
            else:
                raise ValueError("unsupported_replay_candle_shape")
        candles.append(
            Candle(
                symbol=symbol.replace("_", ""),
                timeframe="5m",
                timestamp=str(item["timestamp"]),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=float(item.get("volume", 0.0)),
                source=str(item.get("source", "replay_cache")),
            )
        )
    return candles


def _closing_prices(candles: Sequence[Candle]) -> list[float]:
    return [float(candle.close) for candle in candles]


def _ohlc_window(candles: Sequence[Candle], end_index: int) -> list[Candle]:
    return list(candles[: end_index + 1])


def _exit_trade(candles: Sequence[Candle], signal: Mapping[str, Any], entry_index: int) -> dict[str, Any] | None:
    direction = str(signal["direction"]).upper()
    entry_price = float(candles[entry_index].open)
    stop = float(signal["stop_loss"])
    target = float(signal["take_profit"])
    risk = abs(entry_price - stop)
    if risk <= 0:
        return None
    if direction == Direction.BUY:
        for candle in candles[entry_index + 1 :]:
            if candle.low <= stop:
                exit_price = stop
                realized_r = (exit_price - entry_price) / risk
                return _trade_result(direction, entry_price, stop, target, exit_price, realized_r, candle, signal)
            if candle.high >= target:
                exit_price = target
                realized_r = (exit_price - entry_price) / risk
                return _trade_result(direction, entry_price, stop, target, exit_price, realized_r, candle, signal)
    else:
        for candle in candles[entry_index + 1 :]:
            if candle.high >= stop:
                exit_price = stop
                realized_r = (entry_price - exit_price) / risk
                return _trade_result(direction, entry_price, stop, target, exit_price, realized_r, candle, signal)
            if candle.low <= target:
                exit_price = target
                realized_r = (entry_price - exit_price) / risk
                return _trade_result(direction, entry_price, stop, target, exit_price, realized_r, candle, signal)
    exit_price = float(candles[-1].close)
    realized_r = ((exit_price - entry_price) / risk) if direction == Direction.BUY else ((entry_price - exit_price) / risk)
    return _trade_result(direction, entry_price, stop, target, exit_price, realized_r, candles[-1], signal)


def _trade_result(direction: str, entry_price: float, stop: float, target: float, exit_price: float, realized_r: float, candle: Candle, signal: Mapping[str, Any]) -> dict[str, Any]:
    mfe = max(entry_price, exit_price) if direction == Direction.BUY else min(entry_price, exit_price)
    mae = min(entry_price, exit_price) if direction == Direction.BUY else max(entry_price, exit_price)
    return {
        "direction": direction,
        "entry_price": entry_price,
        "stop_price": stop,
        "target_price": target,
        "exit_price": exit_price,
        "closed_at": candle.timestamp,
        "realized_r": realized_r,
        "mfe_r": abs((mfe - entry_price) / abs(entry_price - stop)),
        "mae_r": abs((entry_price - mae) / abs(entry_price - stop)),
        "mfe_price": mfe,
        "mae_price": mae,
        "signal": dict(signal),
    }


def _signal_matches_filter(direction: str, macd_line: float, signal_line: float, histogram: float, prior_histogram: float, filter_name: str) -> bool:
    if filter_name == "FILTER_A_SIGNAL":
        return (direction == Direction.BUY and macd_line > signal_line) or (direction == Direction.SELL and macd_line < signal_line)
    if filter_name == "FILTER_B_ZERO":
        return (direction == Direction.BUY and macd_line > 0) or (direction == Direction.SELL and macd_line < 0)
    if filter_name == "FILTER_C_FULL":
        return (
            (direction == Direction.BUY and macd_line > signal_line and macd_line > 0 and histogram > 0)
            or (direction == Direction.SELL and macd_line < signal_line and macd_line < 0 and histogram < 0)
        )
    if filter_name == "FILTER_D_ACCELERATION":
        return (direction == Direction.BUY and histogram > 0 and histogram > prior_histogram) or (
            direction == Direction.SELL and histogram < 0 and histogram < prior_histogram
        )
    raise ValueError("unsupported_filter")


def _trade_stats(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    closed = list(trades)
    realized = [float(item["realized_r"]) for item in closed]
    wins = sum(1 for value in realized if value > 0)
    losses = sum(1 for value in realized if value < 0)
    flats = sum(1 for value in realized if value == 0)
    gross_profit = sum(value for value in realized if value > 0)
    gross_loss = sum(-value for value in realized if value < 0)
    win_rate = wins / len(closed) if closed else 0.0
    expectancy = sum(realized) / len(closed) if closed else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    loss_streak = 0
    max_loss_streak = 0
    mfe_values = [float(item.get("mfe_r", 0.0)) for item in closed]
    mae_values = [float(item.get("mae_r", 0.0)) for item in closed]
    for value in realized:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
        if value < 0:
            loss_streak += 1
            max_loss_streak = max(max_loss_streak, loss_streak)
        else:
            loss_streak = 0
    rejected_winners = sum(1 for item in closed if float(item["realized_r"]) > 0 and not bool(item.get("accepted", True)))
    rejected_losers = sum(1 for item in closed if float(item["realized_r"]) < 0 and not bool(item.get("accepted", True)))
    rejected_flats = sum(1 for item in closed if float(item["realized_r"]) == 0 and not bool(item.get("accepted", True)))
    r_saved = sum(-float(item["realized_r"]) for item in closed if float(item["realized_r"]) < 0 and not bool(item.get("accepted", True)))
    r_lost = sum(float(item["realized_r"]) for item in closed if float(item["realized_r"]) > 0 and not bool(item.get("accepted", True)))
    return {
        "closed": len(closed),
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "win_rate": win_rate,
        "expectancy_r": expectancy,
        "profit_factor": profit_factor,
        "net_r": sum(realized),
        "max_drawdown_r": max_drawdown,
        "max_loss_streak": max_loss_streak,
        "mean_mfe_r": mean(mfe_values) if mfe_values else 0.0,
        "median_mfe_r": median(mfe_values) if mfe_values else 0.0,
        "mean_mae_r": mean(mae_values) if mae_values else 0.0,
        "median_mae_r": median(mae_values) if mae_values else 0.0,
        "rejected_winners": rejected_winners,
        "rejected_losers": rejected_losers,
        "rejected_flats": rejected_flats,
        "r_saved_by_rejecting_losers": r_saved,
        "r_lost_by_rejecting_winners": r_lost,
        "net_filter_value_r": r_saved - r_lost,
    }


def trade_filter_match(
    direction: str,
    macd_line: float,
    signal_line: float,
    histogram: float,
    prior_histogram: float,
    filter_name: str,
) -> bool:
    return _signal_matches_filter(direction, macd_line, signal_line, histogram, prior_histogram, filter_name)


def evaluate_macd_filter_on_trades(
    trades: Sequence[Mapping[str, Any]],
    filter_name: str | None = None,
) -> dict[str, Any]:
    all_trades = [dict(item) for item in trades]
    if filter_name is None:
        accepted_trades = []
        for item in all_trades:
            candidate = dict(item)
            candidate["accepted"] = True
            accepted_trades.append(candidate)
    else:
        accepted_trades = []
        filtered = []
        for item in all_trades:
            accepted = _signal_matches_filter(
                str(item["direction"]),
                float(item["macd_line"]),
                float(item["signal_line"]),
                float(item["histogram"]),
                float(item["prior_histogram"]),
                filter_name,
            )
            candidate = dict(item)
            candidate["accepted"] = accepted
            filtered.append(candidate)
            if accepted:
                accepted_trades.append(candidate)
    if filter_name is None:
        filtered = accepted_trades
    stats = _trade_stats(accepted_trades)
    stats.update(
        {
            "signals": len(all_trades),
            "accepted": len(accepted_trades),
            "rejected": len(all_trades) - len(accepted_trades),
            "closed": len(accepted_trades),
            "buy": sum(1 for trade in accepted_trades if trade["direction"] == Direction.BUY),
            "sell": sum(1 for trade in accepted_trades if trade["direction"] == Direction.SELL),
        }
    )
    if filter_name is not None:
        stats["rejected_winners"] = sum(1 for item in all_trades if float(item["realized_r"]) > 0 and not _signal_matches_filter(
            str(item["direction"]),
            float(item["macd_line"]),
            float(item["signal_line"]),
            float(item["histogram"]),
            float(item["prior_histogram"]),
            filter_name,
        ))
        stats["rejected_losers"] = sum(1 for item in all_trades if float(item["realized_r"]) < 0 and not _signal_matches_filter(
            str(item["direction"]),
            float(item["macd_line"]),
            float(item["signal_line"]),
            float(item["histogram"]),
            float(item["prior_histogram"]),
            filter_name,
        ))
        stats["rejected_flats"] = sum(1 for item in all_trades if float(item["realized_r"]) == 0 and not _signal_matches_filter(
            str(item["direction"]),
            float(item["macd_line"]),
            float(item["signal_line"]),
            float(item["histogram"]),
            float(item["prior_histogram"]),
            filter_name,
        ))
        stats["r_saved_by_rejecting_losers"] = sum(-float(item["realized_r"]) for item in all_trades if float(item["realized_r"]) < 0 and not _signal_matches_filter(
            str(item["direction"]),
            float(item["macd_line"]),
            float(item["signal_line"]),
            float(item["histogram"]),
            float(item["prior_histogram"]),
            filter_name,
        ))
        stats["r_lost_by_rejecting_winners"] = sum(float(item["realized_r"]) for item in all_trades if float(item["realized_r"]) > 0 and not _signal_matches_filter(
            str(item["direction"]),
            float(item["macd_line"]),
            float(item["signal_line"]),
            float(item["histogram"]),
            float(item["prior_histogram"]),
            filter_name,
        ))
        stats["net_filter_value_r"] = stats["r_saved_by_rejecting_losers"] - stats["r_lost_by_rejecting_winners"]
    return stats


def _collect_control_trades(history: Sequence[Candle]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    closes = _closing_prices(history)
    series = macd_series(closes)
    all_trades: list[dict[str, Any]] = []
    accepted_trades: list[dict[str, Any]] = []
    for index in range(4, len(history) - 1):
        window = _ohlc_window(history, index)
        result = evaluate_supertrend_pullback(window)
        if not result.get("accepted"):
            continue
        signal = result["signal"]
        direction = str(signal.direction).upper()
        macd_line = series["macd_line"][index]
        signal_line = series["signal_line"][index]
        histogram = series["histogram"][index]
        prior_histogram = series["histogram"][index - 1]
        base_trade = _exit_trade(history, signal.__dict__, index + 1)
        if base_trade is None:
            continue
        base_trade["accepted"] = True
        base_trade["macd_line"] = macd_line
        base_trade["signal_line"] = signal_line
        base_trade["histogram"] = histogram
        base_trade["prior_histogram"] = prior_histogram
        all_trades.append(base_trade)
    return all_trades, accepted_trades


def evaluate_macd_filter(history: Sequence[Candle], filter_name: str | None = None) -> dict[str, Any]:
    all_trades, _accepted_placeholder = _collect_control_trades(history)
    if filter_name is None:
        filtered = [dict(item) for item in all_trades]
        for item in filtered:
            item["accepted"] = True
    else:
        filtered = []
        for item in all_trades:
            accepted = _signal_matches_filter(
                item["signal"]["direction"],
                float(item["macd_line"]),
                float(item["signal_line"]),
                float(item["histogram"]),
                float(item["prior_histogram"]),
                filter_name,
            )
            candidate = dict(item)
            candidate["accepted"] = accepted
            if accepted:
                filtered.append(candidate)
        rejected = [dict(item, accepted=False) for item in all_trades if not _signal_matches_filter(
            item["signal"]["direction"],
            float(item["macd_line"]),
            float(item["signal_line"]),
            float(item["histogram"]),
            float(item["prior_histogram"]),
            filter_name,
        )]
        filtered.extend(rejected)
    stats = _trade_stats(filtered)
    stats.update(
        {
            "signals": len(all_trades),
            "accepted": sum(1 for trade in filtered if trade.get("accepted")),
            "rejected": sum(1 for trade in filtered if not trade.get("accepted")),
            "closed": sum(1 for trade in filtered if trade.get("accepted")),
            "buy": sum(1 for trade in filtered if trade.get("accepted") and trade["direction"] == Direction.BUY),
            "sell": sum(1 for trade in filtered if trade.get("accepted") and trade["direction"] == Direction.SELL),
        }
    )
    return stats


def evaluate_replay_cache(cache: Mapping[str, Any]) -> dict[str, Any]:
    pair_histories = cache.get("pair_histories", {})
    results: dict[str, Any] = {}
    aggregate: dict[str, list[dict[str, Any]]] = {
        "control": [],
        "FILTER_A_SIGNAL": [],
        "FILTER_B_ZERO": [],
        "FILTER_C_FULL": [],
        "FILTER_D_ACCELERATION": [],
    }
    for instrument, history in pair_histories.items():
        candles = history.get("sanitized_candles") or history.get("candles")
        if not isinstance(candles, list) or not candles:
            continue
        candle_objs = _to_candles(candles, symbol=instrument)
        control = evaluate_macd_filter(candle_objs, None)
        filters = {
            "FILTER_A_SIGNAL": evaluate_macd_filter(candle_objs, "FILTER_A_SIGNAL"),
            "FILTER_B_ZERO": evaluate_macd_filter(candle_objs, "FILTER_B_ZERO"),
            "FILTER_C_FULL": evaluate_macd_filter(candle_objs, "FILTER_C_FULL"),
            "FILTER_D_ACCELERATION": evaluate_macd_filter(candle_objs, "FILTER_D_ACCELERATION"),
        }
        results[instrument] = {"control": control, "filters": filters}
        aggregate["control"].append(control)
        for key in filters:
            aggregate[key].append(filters[key])
    return results


def main() -> dict[str, Any]:
    cache = load_replay_cache()
    return evaluate_replay_cache(cache)
