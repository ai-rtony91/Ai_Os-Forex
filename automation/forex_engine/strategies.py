"""PAPER_ONLY Supertrend strategy candidates for local edge research."""

from dataclasses import dataclass
from math import isfinite

from automation.forex_engine.indicators import DOWN, UP, atr, supertrend
from automation.forex_engine.market_data import validate_candle_sequence
from automation.forex_engine.models import Direction, ForexSignal, SignalCandidate


SUPERTREND_PULLBACK_V1 = "supertrend_pullback_v1"


def cluster_scores_v1(values, maximum_iterations=32):
    """Deterministic three-cluster 1D Lloyd iteration; repeated/empty centers retained."""
    if not values or any(not isfinite(v) for v in values) or type(maximum_iterations) is not int or not 1 <= maximum_iterations <= 128:
        raise ValueError("SUPERTREND_CLUSTER_INPUT_INVALID")
    ordered = sorted(values)
    centers = [ordered[int((len(ordered)-1)*q)] for q in (0.25, 0.5, 0.75)]
    labels = []
    converged = False
    for iteration in range(maximum_iterations):
        labels = [min(range(3), key=lambda k: (abs(value-centers[k]), k)) for value in values]
        groups = [[value for value, label in zip(values, labels) if label == k] for k in range(3)]
        new = [sum(group)/len(group) if group else centers[k] for k, group in enumerate(groups)]
        if max(abs(a-b) for a, b in zip(new, centers)) <= 1e-12:
            centers, converged = new, True
            break
        centers = new
    # Final reassignment means labels always describe the returned centroids.
    labels = [min(range(3), key=lambda k: (abs(value-centers[k]), k)) for value in values]
    return {"centers": centers, "labels": labels, "iterations": iteration+1, "converged": converged,
            "empty_clusters": [k for k in range(3) if k not in labels]}


def supertrend_policy_v1(bars, implementation, indicator):
    """Causal study policy. Scores are lagged gross directional diagnostics, not P&L/HOT.

    Member paths keep their own ratchets. A cluster selects an actual member,
    unlike a vendor's averaged-factor dynamic path. Internal selections are
    returned for selection-history accounting. Execution belongs to S6.
    """
    policy = implementation["policy"]
    if policy not in {"CLASSIC", "ADAPTIVE_CLUSTER", "CONSENSUS", "STABILITY_SELECTED"}:
        raise ValueError("SUPERTREND_POLICY_INVALID")
    factors = implementation.get("factors", [implementation.get("multiplier")])
    if not isinstance(factors, list) or not factors or factors != sorted(set(factors)) or any(
            type(f) not in (int, float) or not isfinite(f) or f <= 0 for f in factors):
        raise ValueError("SUPERTREND_FACTOR_DOMAIN_INVALID")
    period = implementation["atr_period"]
    paths = [indicator(bars, period, factor) for factor in factors]
    cadence = implementation.get("update_cadence", 1)
    memory = implementation.get("performance_memory", 1)
    if type(cadence) is not int or cadence < 1 or type(memory) is not int or memory < 1:
        raise ValueError("SUPERTREND_MEMORY_CADENCE_INVALID")
    alpha = 2/(memory+1)
    scores = [0.0]*len(factors)
    selected = 0
    prior_direction = 0
    output = []
    for i, row in enumerate(bars):
        lagged = list(scores)
        clustering = None
        direction = 0
        warm = paths[0][i]["atr"] is not None and paths[0][i]["atr"] > 0
        if warm and policy == "CLASSIC":
            direction = paths[0][i]["direction"]
        elif warm and policy == "ADAPTIVE_CLUSTER":
            if (i-period+1) % cadence == 0:
                clustering = cluster_scores_v1(lagged)
                if not clustering["converged"]:
                    raise ValueError("SUPERTREND_CLUSTER_NOT_CONVERGED")
                occupied = sorted(set(clustering["labels"]), key=lambda k: (clustering["centers"][k], k))
                rule = implementation["cluster_rule"]
                rank = {"WORST": 0, "MIDDLE": len(occupied)//2, "BEST": len(occupied)-1}.get(rule)
                if rank is None:
                    raise ValueError("SUPERTREND_CLUSTER_RULE_INVALID")
                members = [n for n, k in enumerate(clustering["labels"]) if k == occupied[rank]]
                representative = implementation["representative"]
                if representative == "MEDIAN_MEMBER":
                    selected = members[(len(members)-1)//2]
                elif representative == "MEDOID_LOW_TIE":
                    mean_factor = sum(factors[n] for n in members)/len(members)
                    selected = min(members, key=lambda n: (abs(factors[n]-mean_factor), n))
                else:
                    raise ValueError("SUPERTREND_REPRESENTATIVE_INVALID")
            direction = paths[selected][i]["direction"]
        elif warm and policy == "CONSENSUS":
            if (i-period+1) % cadence == 0:
                normalization = implementation["normalization"]
                if normalization == "DIRECTION":
                    vote = sum(path[i]["direction"] for path in paths)/len(paths)
                elif normalization == "BAND_DISTANCE":
                    vote = sum(max(-1.0, min(1.0, (row["c"]-path[i]["band"])/path[i]["atr"])) for path in paths)/len(paths)
                else:
                    raise ValueError("SUPERTREND_CONSENSUS_NORMALIZATION_INVALID")
                threshold = implementation["consensus_threshold"]
                if type(threshold) not in (float, int) or not 0 < threshold <= 1:
                    raise ValueError("SUPERTREND_CONSENSUS_THRESHOLD_INVALID")
                neutral_rule = implementation["neutral_rule"]
                if neutral_rule not in {"CASH", "RETAIN_PREVIOUS"}:
                    raise ValueError("SUPERTREND_CONSENSUS_NEUTRAL_INVALID")
                direction = 1 if vote >= threshold else -1 if vote <= -threshold else prior_direction if neutral_rule == "RETAIN_PREVIOUS" else 0
            else:
                direction = prior_direction
            selected = (len(factors)-1)//2
        elif warm and policy == "STABILITY_SELECTED":
            if (i-period+1) % cadence == 0:
                radius = implementation["adjacency_radius"]
                minimum = implementation["minimum_support"]
                maximum = implementation["maximum_dispersion"]
                if type(radius) is not int or radius < 1 or not 0 < minimum <= 1 or maximum < 0:
                    raise ValueError("SUPERTREND_STABILITY_DOMAIN_INVALID")
                eligible = []
                for n in range(len(factors)):
                    neighbors = list(range(max(0, n-radius), min(len(factors), n+radius+1)))
                    values = [lagged[k] for k in neighbors]
                    mean = sum(values)/len(values)
                    dispersion = (sum((v-mean)**2 for v in values)/len(values))**0.5
                    coverage = len(neighbors)/(2*radius+1)
                    if coverage >= minimum and dispersion <= maximum:
                        eligible.append((mean, -dispersion, -n, n))
                selected = max(eligible)[-1] if eligible else None
            direction = paths[selected][i]["direction"] if selected is not None else 0
        band = paths[selected][i]["band"] if selected is not None else None
        output.append({**paths[0][i], "direction": direction, "band": band, "policy": policy,
            "selected_multiplier": factors[selected] if selected is not None else None,
            "lagged_scores": lagged, "score_as_of_index": i-1, "cluster": clustering,
            "internal_member_count": len(factors), "score_is_after_cost_pnl": False,
            "independent_votes": False, "hot_status": "NOT_SCIENTIFIC_EVIDENCE"})
        # Performance available at close i is used for decisions at i+1 or later.
        if i and paths[0][i-1]["atr"] and paths[0][i-1]["atr"] > 0:
            move = (row["c"]-bars[i-1]["c"])/paths[0][i-1]["atr"]
            scores = [(1-alpha)*s+alpha*move*paths[n][i-1]["direction"] for n, s in enumerate(scores)]
        prior_direction = direction
    return output


def closed_higher_timeframe_v1(features, decision_at):
    from datetime import datetime
    at = datetime.fromisoformat(decision_at.replace("Z", "+00:00"))
    if at.tzinfo is None:
        raise ValueError("HIGHER_TIMEFRAME_TIMEZONE_REQUIRED")
    visible = [f for f in features if datetime.fromisoformat(f["available_at"].replace("Z", "+00:00")) <= at]
    return max(visible, key=lambda f: datetime.fromisoformat(f["available_at"].replace("Z", "+00:00")), default=None)


def technical_context_v1(bars, index, lookback=10):
    """Four fixed public concepts, using prior support/reference levels. No sizing or orders."""
    if type(index) is not int or type(lookback) is not int or lookback < 2 or not 0 <= index < len(bars):
        raise ValueError("TECHNICAL_CONTEXT_DOMAIN_INVALID")
    if index < lookback:
        return {"state": "WARMUP", "directions": {}, "orders_allowed": False}
    prior = bars[index-lookback:index]
    row = bars[index]
    low, high = min(b["l"] for b in prior), max(b["h"] for b in prior)
    reference = sum(b["c"] for b in prior)/lookback
    sign = lambda x: 1 if x > 0 else -1 if x < 0 else 0
    bounce = 1 if row["l"] <= low and row["c"] > low and row["c"] > row["o"] else (
        -1 if row["h"] >= high and row["c"] < high and row["c"] < row["o"] else 0)
    reversal = 1 if prior[-1]["c"] < reference <= row["c"] else -1 if prior[-1]["c"] > reference >= row["c"] else 0
    return {"state": "KNOWN", "directions": {"MOMENTUM_CONTINUATION": sign(row["c"]-prior[0]["c"]),
        "SUPPORT_RESISTANCE_BOUNCE": bounce, "REFERENCE_REVERSAL": reversal,
        "BREAKOUT": 1 if row["c"] > high else -1 if row["c"] < low else 0},
        "prior_support": low, "prior_resistance": high, "reference": reference,
        "available_bar_index": index, "orders_allowed": False, "provenance": "CLEAN_PUBLIC_CONCEPTS_V1"}


MATCHED_CHANNELS_V1 = ((), ("TECHNICAL",), ("SENTIMENT",), ("FUNDAMENTAL",),
    ("TECHNICAL", "SENTIMENT"), ("TECHNICAL", "FUNDAMENTAL"),
    ("SENTIMENT", "FUNDAMENTAL"), ("TECHNICAL", "SENTIMENT", "FUNDAMENTAL"))


def matched_filter_v1(direction, technical, sentiment, fundamental, channels, event_buffer_seconds=900):
    if tuple(channels) not in MATCHED_CHANNELS_V1 or direction not in (-1, 1):
        raise ValueError("MATCHED_FILTER_NOT_FROZEN")
    missing, rejected = [], []
    if "TECHNICAL" in channels:
        if technical["state"] != "KNOWN":
            missing.append("TECHNICAL")
        elif technical["directions"]["MOMENTUM_CONTINUATION"] != direction:
            rejected.append("TECHNICAL")
    if "SENTIMENT" in channels:
        if sentiment["state"] != "KNOWN":
            missing.append("SENTIMENT")
        elif sentiment["direction"]*direction <= 0:
            rejected.append("SENTIMENT")
    if "FUNDAMENTAL" in channels:
        if fundamental["state"] != "KNOWN":
            missing.append("FUNDAMENTAL")
        elif fundamental.get("event_proximity_seconds") is not None and fundamental["event_proximity_seconds"] <= event_buffer_seconds:
            rejected.append("SCHEDULED_EVENT_RISK")
    return {"accept": not missing and not rejected, "state": "DATA_BLOCKED" if missing else "REJECTED_FILTER" if rejected else "ADMITTED",
            "missing_channels": missing, "rejected_channels": rejected, "orders_allowed": False}


def after_cost_plateau_v1(results, center, radius, minimum_support, maximum_dispersion):
    """Predeclared adjacency on numeric index; a development report, never proof."""
    if not 0 <= center < len(results) or radius < 1 or not 0 < minimum_support <= 1 or maximum_dispersion < 0:
        raise ValueError("PLATEAU_DOMAIN_INVALID")
    nearby = results[max(0, center-radius):min(len(results), center+radius+1)]
    if any(r.get("after_cost") is not True or type(r.get("expectancy_r")) not in (float, int) or not isfinite(r["expectancy_r"]) for r in nearby):
        raise ValueError("PLATEAU_AFTER_COST_EVIDENCE_REQUIRED")
    values = [r["expectancy_r"] for r in nearby]
    mean = sum(values)/len(values)
    dispersion = (sum((v-mean)**2 for v in values)/len(values))**0.5
    support = sum(v > 0 for v in values)/(2*radius+1)
    return {"broad_positive_development_plateau": support >= minimum_support and mean > 0 and dispersion <= maximum_dispersion,
            "support": support, "dispersion": dispersion, "mean_expectancy_r": mean,
            "neighbors_are_independent": False, "verified_edge": False}


@dataclass(frozen=True)
class SupertrendPullbackConfig:
    atr_period: int = 3
    supertrend_multiplier: float = 2.0
    min_body_to_range: float = 0.45
    min_atr: float = 0.0004
    max_band_extension_atr: float = 2.5
    min_reward_risk: float = 1.5
    target_reward_risk: float = 2.0
    chop_lookback: int = 4


def classify_r_multiple(realized_pl: float | int | None, risk_amount: float | int | None) -> str:
    try:
        risk = float(risk_amount)
        pnl = float(realized_pl)
    except (TypeError, ValueError):
        return "INVALID_R"
    if not (risk > 0 and isfinite(risk) and isfinite(pnl)):
        return "INVALID_R"
    realized_r = pnl / risk
    if realized_r > 0:
        return "POSITIVE_R"
    if realized_r < 0:
        return "NEGATIVE_R"
    return "FLAT_R"


def realized_r_multiple(realized_pl: float | int | None, risk_amount: float | int | None) -> float | None:
    try:
        risk = float(risk_amount)
        pnl = float(realized_pl)
    except (TypeError, ValueError):
        return None
    if not (risk > 0 and isfinite(risk) and isfinite(pnl)):
        return None
    return pnl / risk


def planned_reward_risk(entry_price: float | int | None, stop_loss: float | int | None, take_profit: float | int | None) -> float | None:
    try:
        entry = float(entry_price)
        stop = float(stop_loss)
        target = float(take_profit)
    except (TypeError, ValueError):
        return None
    if not all(map(isfinite, (entry, stop, target))):
        return None
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if not (risk > 0):
        return None
    return reward / risk


def evaluate_supertrend_pullback(candles, strategy_config=SupertrendPullbackConfig()):
    validate_candle_sequence(candles)
    last = candles[-1]
    no_trade_reasons = []
    if len(candles) < strategy_config.atr_period + 2:
        no_trade_reasons.append("NO_TRADE: insufficient_data")
        return _blocked_candidate(candles, no_trade_reasons, strategy_config)

    trend = supertrend(candles, strategy_config.atr_period, strategy_config.supertrend_multiplier)
    atr_values = atr(candles, strategy_config.atr_period)
    last_trend = trend[-1]
    last_atr = atr_values[-1]

    if last_trend["direction"] not in (UP, DOWN):
        no_trade_reasons.append("NO_TRADE: no_supertrend_direction")
    if last_atr is None or last_atr < strategy_config.min_atr:
        no_trade_reasons.append("NO_TRADE: volatility_below_atr_threshold")
    if _recent_flip_count(trend, strategy_config.chop_lookback) >= 2 or _recent_close_flip_count(candles, strategy_config.chop_lookback) >= 3:
        no_trade_reasons.append("NO_TRADE: chop_zone_repeated_flips")
    if _body_to_range(last) < strategy_config.min_body_to_range:
        no_trade_reasons.append("NO_TRADE: weak_candle_body")

    direction = Direction.BUY if last_trend["direction"] == UP else Direction.SELL
    band = last_trend["lower_band"] if direction == Direction.BUY else last_trend["upper_band"]
    if band is None:
        no_trade_reasons.append("NO_TRADE: missing_supertrend_band")
        return _blocked_candidate(candles, no_trade_reasons, strategy_config)

    if direction == Direction.BUY and last.close <= last.open:
        no_trade_reasons.append("NO_TRADE: close_confirmation_missing")
    if direction == Direction.SELL and last.close >= last.open:
        no_trade_reasons.append("NO_TRADE: close_confirmation_missing")

    extension = abs(last.close - band)
    if last_atr and extension > strategy_config.max_band_extension_atr * last_atr:
        no_trade_reasons.append("NO_TRADE: entry_extended_from_band")

    stop_buffer = max(last_atr or 0.0, abs(last.close - band) * 0.5)
    if direction == Direction.BUY:
        stop_loss = min(band, last.low) - stop_buffer * 0.25
        risk = last.close - stop_loss
        take_profit = last.close + (risk * strategy_config.target_reward_risk)
    else:
        stop_loss = max(band, last.high) + stop_buffer * 0.25
        risk = stop_loss - last.close
        take_profit = last.close - (risk * strategy_config.target_reward_risk)

    reward = abs(take_profit - last.close)
    reward_risk = reward / risk if risk > 0 else 0.0
    if risk <= 0 or reward_risk < strategy_config.min_reward_risk:
        no_trade_reasons.append("NO_TRADE: reward_risk_below_minimum")

    if no_trade_reasons:
        return _blocked_candidate(candles, no_trade_reasons, strategy_config, direction, stop_loss, take_profit)

    candidate = SignalCandidate(
        symbol=last.symbol,
        timeframe=last.timeframe,
        direction=direction,
        entry_price=round(last.close, 5),
        stop_loss=round(stop_loss, 5),
        take_profit=round(take_profit, 5),
        strategy_name=SUPERTREND_PULLBACK_V1,
        regime_trend="SUPERTREND_UP" if direction == Direction.BUY else "SUPERTREND_DOWN",
        regime_volatility="ATR_OK",
        confidence_hint=78,
        reasons=[
            "supertrend_direction",
            "close_confirmation",
            "body_strength_filter",
            "atr_volatility_filter",
            "reward_risk_filter",
        ],
        metadata={
            "mode": "PAPER_ONLY",
            "atr": round(last_atr, 10),
            "band": round(band, 10),
            "reward_risk": round(reward_risk, 4),
            "planned_reward_risk": round(reward_risk, 4),
            "min_reward_risk": strategy_config.min_reward_risk,
            "target_reward_risk": strategy_config.target_reward_risk,
            "warning": "edge candidate only; no live approval",
        },
    )
    return {
        "strategy_name": SUPERTREND_PULLBACK_V1,
        "accepted": True,
        "candidate": candidate,
        "signal": candidate_to_signal(candidate, last.timestamp),
        "no_trade_reasons": [],
    }


def generate_supertrend_signals_from_candles(candles, _config=None):
    result = evaluate_supertrend_pullback(candles)
    signal = result.get("signal")
    return ([signal] if signal else []), result


def candidate_to_signal(candidate, timestamp):
    if candidate.blocked_reason:
        raise ValueError(candidate.blocked_reason)
    return ForexSignal(
        symbol=candidate.symbol,
        timeframe=candidate.timeframe,
        direction=candidate.direction,
        entry_price=candidate.entry_price,
        stop_loss=candidate.stop_loss,
        take_profit=candidate.take_profit,
        timestamp=timestamp,
        strategy_name=candidate.strategy_name,
        metadata=dict(candidate.metadata),
    )


def _blocked_candidate(candles, reasons, strategy_config, direction=None, stop_loss=None, take_profit=None):
    last = candles[-1]
    candidate = SignalCandidate(
        symbol=last.symbol,
        timeframe=last.timeframe,
        direction=direction,
        entry_price=round(last.close, 5),
        stop_loss=round(stop_loss if stop_loss is not None else last.close, 5),
        take_profit=round(take_profit if take_profit is not None else last.close, 5),
        strategy_name=SUPERTREND_PULLBACK_V1,
        regime_trend="BLOCKED",
        regime_volatility="BLOCKED",
        confidence_hint=0,
        reasons=list(reasons),
        blocked_reason="; ".join(reasons),
        metadata={
            "mode": "PAPER_ONLY",
            "min_reward_risk": strategy_config.min_reward_risk,
            "warning": "NO_TRADE research result only",
        },
    )
    return {
        "strategy_name": SUPERTREND_PULLBACK_V1,
        "accepted": False,
        "candidate": candidate,
        "signal": None,
        "no_trade_reasons": list(reasons),
    }


def _body_to_range(candle):
    candle_range = candle.high - candle.low
    if candle_range <= 0:
        return 0.0
    return abs(candle.close - candle.open) / candle_range


def _recent_flip_count(trend, lookback):
    directions = [item["direction"] for item in trend if item["direction"] in (UP, DOWN)]
    recent = directions[-lookback:]
    if len(recent) < 2:
        return 0
    return sum(1 for previous, current in zip(recent, recent[1:]) if previous != current)


def _recent_close_flip_count(candles, lookback):
    recent = candles[-lookback:]
    directions = []
    for candle in recent:
        if candle.close > candle.open:
            directions.append(UP)
        elif candle.close < candle.open:
            directions.append(DOWN)
        else:
            directions.append(0)
    return sum(1 for previous, current in zip(directions, directions[1:]) if previous and current and previous != current)
