"""Packet 033 objective scalping technique primitives."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any



PACKET_ID = "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033"
STATE = Path("Reports/forex_delivery/AIOS_FOREX_SCALPING_TECHNIQUE_FIDELITY_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_SCALPING_TECHNIQUE_FIDELITY_V1_REPORT.md")


FAMILY_RULES: dict[str, dict[str, list[str]]] = {
    "A": {
        "entry": ["completed-bar trend state matches direction", "completed-bar pullback returns to the frozen trend zone"],
        "exit": ["opposite completed-bar trend state", "frozen stop, target, or maximum holding bars"],
        "controls": ["trend-strength floor", "spread ceiling", "no entry before indicator warmup"],
    },
    "B": {
        "entry": ["completed bar closes beyond the frozen causal range", "breakout direction matches the isolated side"],
        "exit": ["completed bar returns inside the frozen range", "frozen stop, target, or maximum holding bars"],
        "controls": ["minimum range observations", "spread ceiling", "no same-bar lookahead"],
    },
    "C": {
        "entry": ["completed bar reaches the frozen range extreme", "reversion state confirms the isolated side"],
        "exit": ["completed bar reaches the frozen center or opposite band", "frozen stop or maximum holding bars"],
        "controls": ["range-regime gate", "spread ceiling", "trend-regime exclusion"],
    },
    "D": {
        "entry": ["completed bar crosses or rejects the causal session average", "distance threshold matches the isolated side"],
        "exit": ["completed bar reaches the frozen average-price objective", "frozen stop or session boundary"],
        "controls": ["causal session reset", "price-count proxy only", "spread ceiling"],
    },
    "E": {
        "entry": ["completed bars satisfy the frozen swing or candle-pattern definition", "level confirmation matches the isolated side"],
        "exit": ["completed bar invalidates the frozen structure", "frozen stop, target, or maximum holding bars"],
        "controls": ["objective pivot window", "minimum range threshold", "spread ceiling"],
    },
    "F": {
        "entry": ["completed bar falls inside the frozen UTC session window", "session rule confirms the isolated side"],
        "exit": ["frozen session window closes", "frozen stop, target, or maximum holding bars"],
        "controls": ["UTC calendar only", "rollover exclusion", "spread ceiling"],
    },
    "G": {
        "entry": ["completed-bar volatility or spread statistic crosses the frozen threshold", "state transition matches the isolated side"],
        "exit": ["completed-bar volatility state normalizes", "frozen stop, target, or maximum holding bars"],
        "controls": ["causal rolling percentile", "spread ceiling", "abnormal-gap abstention"],
    },
    "H": {
        "entry": ["completed bar follows a frozen official-event timestamp window", "post-event state matches the isolated side"],
        "exit": ["frozen post-event window closes", "frozen stop, target, or spread-abstention gate"],
        "controls": ["official timestamps only", "pre-event abstention", "spread normalization gate"],
    },
    "I": {
        "entry": ["completed synchronized bars produce the frozen currency rank", "selected pair matches the isolated strong/weak side"],
        "exit": ["completed synchronized rank reverses or converges", "frozen stop, target, or rebalance boundary"],
        "controls": ["synchronized pair timestamp", "currency concentration cap", "spread ceiling"],
    },
    "J": {
        "entry": ["completed synchronized legs produce a residual beyond the frozen threshold", "residual direction matches the isolated side"],
        "exit": ["completed residual reaches the frozen convergence level", "frozen stop or maximum holding bars"],
        "controls": ["synchronized multi-leg bars", "leg concentration cap", "combined spread ceiling"],
    },
    "K": {
        "entry": ["completed granular bars satisfy the frozen microstructure-proxy rule", "proxy state matches the isolated side"],
        "exit": ["completed granular proxy decays beyond the frozen half-life", "frozen stop, target, or latency boundary"],
        "controls": ["native second-or-subminute data required", "latency sensitivity gate", "spread ceiling"],
    },
    "L": {
        "entry": ["completed order-book or trade-tape snapshot satisfies the frozen imbalance rule", "flow direction matches the isolated side"],
        "exit": ["completed flow state normalizes or reverses", "frozen stop, target, or maximum holding interval"],
        "controls": ["native order-book or trade-tape data required", "venue identity required", "no OHLC volume substitution"],
    },
}


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2 / (period + 1)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for i in range(period, len(values)):
        current = alpha * values[i] + (1 - alpha) * current
        out[i] = current
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    """Wilder RSI: seed at index period, then include every new price change.

    A flat seed is neutral (50); gains without losses are 100 and losses
    without gains are 0. Callers supply completed closes in time order.
    """
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("RSI period must be a positive integer")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("RSI closes must be finite")
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = [max(0.0, values[i] - values[i - 1]) for i in range(1, len(values))]
    losses = [max(0.0, values[i - 1] - values[i]) for i in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(values)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = (50.0 if avg_gain == 0 else 100.0) if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return out


def bollinger_state(values: list[float], index: int, period: int = 20, width: float = 2.0) -> str:
    if index < period:
        return "WARMUP"
    window = values[index - period : index]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std = variance ** 0.5
    if values[index] > mean + width * std:
        return "ABOVE_UPPER"
    if values[index] < mean - width * std:
        return "BELOW_LOWER"
    return "INSIDE"


def opening_range_breakout(rows: list[dict[str, Any]], index: int, lookback: int = 12) -> str:
    if index < lookback:
        return "WARMUP"
    high = max(float(r["high"]) for r in rows[index - lookback : index])
    low = min(float(r["low"]) for r in rows[index - lookback : index])
    close = float(rows[index]["close"])
    if close > high:
        return "LONG"
    if close < low:
        return "SHORT"
    return "NO_TRADE"


def build_technique_contracts() -> list[dict[str, Any]]:
    from automation.forex_engine.forex_scalping_technique_inventory_v1 import FAMILIES
    contracts: list[dict[str, Any]] = []
    for family_id, family in FAMILIES.items():
        family_rules = FAMILY_RULES[family_id]
        data_eligible = family_id not in {"K", "L"}
        for technique_id in family["techniques"]:
            contract: dict[str, Any] = {
                "technique_id": technique_id,
                "family_id": family_id,
                "family_name": family["name"],
                "contract_version": "1.0.0",
                "directions": ["LONG", "SHORT"],
                "direction_isolation_required": True,
                "completed_bar_only": True,
                "objective_entry_rules": [f"signal definition: {technique_id}", *family_rules["entry"]],
                "objective_exit_rules": list(family_rules["exit"]),
                "controls": [*family_rules["controls"], "frozen parameter registry", "negative results preserved"],
                "data_requirement": family["data"],
                "data_eligible": data_eligible,
                "eligibility_status": "PRE_DATA_CONTRACT_READY" if data_eligible else "INELIGIBLE_REQUIRED_DATA_NOT_FROZEN",
                "implementation_status": "IMPLEMENTED_PRIMITIVE" if technique_id in {
                    "A1_EMA_PULLBACK",
                    "B1_OPENING_RANGE_BREAKOUT",
                    "C1_BOLLINGER_REVERSION",
                    "C3_RSI_REVERSION",
                    "D1_SESSION_VWAP_PULLBACK_CONTINUATION",
                    "G3_SPREAD_PERCENTILE",
                } else "CONTRACT_ONLY_NOT_IMPLEMENTED",
            }
            contract["fingerprint"] = sha256_text(stable(contract))
            contracts.append(contract)
    contracts.sort(key=lambda contract: contract["technique_id"])
    return contracts


# New S6 designs, not recovered Packet 033 rules or historical market evidence.
# A singleton domain is deliberate: outcomes may not choose the parameters.
S6_PRICE_DESIGNS = {
    "E1_SWING_BREAK_RETEST": {"pivot_left": 2, "pivot_right": 2, "retest_bars": 6,
                              "break_atr": 0.25, "retest_atr": 0.10},
    "C2_KELTNER_REVERSION": {"lookback": 20, "channel_atr": 2.0,
                             "reentry_bars": 3, "maximum_drift_atr": 0.5},
    "G4_SPREAD_COMPRESSION_IMPULSE": {"lookback": 20, "wide_multiple": 2.0,
                                     "compression_multiple": 1.0, "body_atr": 1.0},
}


def s6_price_signals(rows: list[dict[str, Any]], technique_id: str) -> list[dict[str, Any]]:
    """Pure causal signals; next-open fills and portfolio accounting belong to S6.

    Rows contain completed mid OHLC, UTC timestamp and observed close spread.
    All state resets at a missing M5 bar. A pivot first exists after its right
    confirmation bars close. Neither break nor excursion can trigger a retest
    or reentry on the same bar. Pending levels never move with later prices.
    """
    from datetime import datetime, timedelta, timezone
    if technique_id not in S6_PRICE_DESIGNS:
        raise ValueError("UNLISTED_S6_TECHNIQUE")
    settings = S6_PRICE_DESIGNS[technique_id]
    signals, segment, last, pivot_high, pivot_low, pending, center = [], 0, None, None, None, None, None
    stamps = []
    for i, row in enumerate(rows):
        stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0) or stamp.second or stamp.microsecond or stamp.minute % 5:
            raise ValueError("UTC_M5_REQUIRED")
        if last is not None and stamp <= last:
            raise ValueError("UNORDERED_OR_DUPLICATE_ROWS")
        if row.get("complete") is not True:
            raise ValueError("COMPLETED_BAR_REQUIRED")
        o, h, l, close, spread = [float(row[k]) for k in ("open", "high", "low", "close", "spread")]
        if not all(math.isfinite(x) for x in (o, h, l, close, spread)) or min(o, h, l, close) <= 0 or spread < 0 or l > min(o, close) or h < max(o, close):
            raise ValueError("INVALID_TECHNIQUE_ROW")
        if last is not None and stamp-last != timedelta(minutes=5):
            segment, pivot_high, pivot_low, pending, center = i, None, None, None, None
        stamps.append(stamp); last = stamp
        if i-segment < 21:
            continue
        prior = rows[i-20:i]
        atr = sum(max(float(r["high"])-float(r["low"]),
                      abs(float(r["high"])-float(rows[k-1]["close"])),
                      abs(float(r["low"])-float(rows[k-1]["close"])))
                  for k, r in enumerate(prior, i-20))/20
        if atr <= 0:
            pending = None
            continue
        direction, proof = 0, {}
        if technique_id == "E1_SWING_BREAK_RETEST":
            # Confirmation happens now; trading that new level starts next bar.
            if pending:
                d, level, armed, frozen_atr = pending
                if i-armed > settings["retest_bars"] or d*(close-level) < -settings["retest_atr"]*frozen_atr:
                    pending = None
                elif i > armed and ((d == 1 and l <= level+settings["retest_atr"]*frozen_atr and close > level and close > o)
                                    or (d == -1 and h >= level-settings["retest_atr"]*frozen_atr and close < level and close < o)):
                    direction, proof = d, {"level": level, "break_index": armed, "level_atr": frozen_atr}
                    pending = None
            if pending is None and not direction:
                previous = float(rows[i-1]["close"])
                for d, level in ((1, pivot_high), (-1, pivot_low)):
                    if level is not None and d*(previous-level) <= 0 and d*(close-level) >= settings["break_atr"]*atr:
                        pending = (d, level, i, atr)
                        break
            window = rows[i-4:i+1]; pivot = window[2]
            if all(float(pivot["high"]) > float(r["high"]) for j, r in enumerate(window) if j != 2):
                pivot_high = float(pivot["high"])
            if all(float(pivot["low"]) < float(r["low"]) for j, r in enumerate(window) if j != 2):
                pivot_low = float(pivot["low"])
        elif technique_id == "C2_KELTNER_REVERSION":
            if center is None:
                center = sum(float(r["close"]) for r in rows[segment:segment+20])/20
            center = (2/21)*float(rows[i-1]["close"])+(19/21)*center
            drift = abs(float(prior[-1]["close"])-float(prior[0]["close"]))/atr
            if pending:
                d, boundary, armed, frozen_atr = pending
                if i-armed > settings["reentry_bars"]:
                    pending = None
                elif i > armed and d*(close-boundary) > 0 and d*(close-o) > 0:
                    direction, proof = d, {"frozen_boundary": boundary, "excursion_index": armed, "level_atr": frozen_atr}
                    pending = None
            if pending is None and not direction and drift <= settings["maximum_drift_atr"]:
                if close < center-settings["channel_atr"]*atr:
                    pending = (1, center-settings["channel_atr"]*atr, i, atr)
                elif close > center+settings["channel_atr"]*atr:
                    pending = (-1, center+settings["channel_atr"]*atr, i, atr)
        else:
            spreads = sorted(float(r["spread"]) for r in prior)
            median = (spreads[9]+spreads[10])/2
            previous_spread = float(rows[i-1]["spread"])
            if median > 0 and previous_spread >= settings["wide_multiple"]*median and spread <= settings["compression_multiple"]*median and abs(close-o) >= settings["body_atr"]*atr:
                direction = 1 if close > o else -1
                proof = {"prior_median_spread": median, "previous_spread": previous_spread}
        if direction:
            signals.append({"signal_index": i, "entry_index": i+1, "direction": direction, "atr": atr,
                            "available_at": (stamp+timedelta(minutes=5)).isoformat(),
                            "segment_start": segment, "proof": proof})
    return signals


S6_CROSS_DESIGNS = {
    "X1_PEER_SHOCK_DELAYED_RESPONSE": {"peers": 3, "peer_body_atr": 1.0,
        "quiet_body_atr": 0.25, "response_body_atr": 0.25,
        "response_bars": 3, "peer_invalidation_atr": 0.5},
}


def s6_peer_shock_signals(rows_by_pair: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Completed synchronized peer shock, then a delayed single-leg response.

    Peers are information inputs only, never synthetic hedge fills. No rank,
    fitted equilibrium, missing-bar interpolation or forward-filled peer exists.
    A gap in any peer resets every pending signal and the common ATR warmup.
    """
    from datetime import datetime, timedelta
    pairs = sorted(rows_by_pair)
    if pairs != ["AUD_USD", "EUR_USD", "GBP_USD", "NZD_USD"]:
        raise ValueError("EXACT_FOUR_SYNCHRONIZED_PEERS_REQUIRED")
    maps = {}
    for pair in pairs:
        mapping, previous = {}, None
        for index, row in enumerate(rows_by_pair[pair]):
            stamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0) or stamp.second or stamp.microsecond or stamp.minute % 5:
                raise ValueError("UTC_M5_REQUIRED")
            if previous is not None and stamp <= previous:
                raise ValueError("UNORDERED_OR_DUPLICATE_ROWS")
            values = [float(row[k]) for k in ("open", "high", "low", "close", "spread")]
            o, h, l, close, spread = values
            if (row.get("complete") is not True or not all(math.isfinite(v) for v in values)
                    or min(values[:4]) <= 0 or spread < 0 or l > min(o, close) or h < max(o, close)):
                raise ValueError("INVALID_COMPLETED_PEER_ROW")
            mapping[stamp] = (index, row); previous = stamp
        maps[pair] = mapping
    stamps = sorted(set.intersection(*(set(maps[p]) for p in pairs)))
    signals = {p: [] for p in pairs}
    pending, history, previous = {}, [], None
    design = S6_CROSS_DESIGNS["X1_PEER_SHOCK_DELAYED_RESPONSE"]
    for stamp in stamps:
        if previous is not None and stamp - previous != timedelta(minutes=5):
            pending, history = {}, []
        previous = stamp
        if len(history) >= 21:
            atr = {}
            for p in pairs:
                ranges = []
                for k in range(len(history)-20, len(history)):
                    r = maps[p][history[k]][1]; pc = float(maps[p][history[k-1]][1]["close"])
                    ranges.append(max(float(r["high"])-float(r["low"]), abs(float(r["high"])-pc), abs(float(r["low"])-pc)))
                atr[p] = sum(ranges)/20
            if all(v > 0 for v in atr.values()):
                bodies = {p: (float(maps[p][stamp][1]["close"])-float(maps[p][stamp][1]["open"]))/atr[p] for p in pairs}
                for p in pairs:
                    peers = [q for q in pairs if q != p]
                    state = pending.get(p)
                    if state:
                        d, armed, level, frozen_atr, proof = state
                        age = int((stamp-armed).total_seconds()/300)
                        row = maps[p][stamp][1]
                        if age > design["response_bars"] or any(d*bodies[q] < -design["peer_invalidation_atr"] for q in peers):
                            pending.pop(p)
                        elif age > 0 and d*(float(row["close"])-float(row["open"])) >= design["response_body_atr"]*frozen_atr and d*(float(row["close"])-level) > 0:
                            index = maps[p][stamp][0]
                            signals[p].append({"signal_index": index, "entry_index": index+1, "direction": d,
                                "atr": frozen_atr, "available_at": (stamp+timedelta(minutes=5)).isoformat(),
                                "proof": {"shock_open": armed.isoformat(), "peer_body_atr": proof,
                                          "quiet_pair": p, "response_age_bars": age}})
                            pending.pop(p)
                            continue
                    if p not in pending and abs(bodies[p]) <= design["quiet_body_atr"]:
                        for d in (1, -1):
                            if all(d*bodies[q] >= design["peer_body_atr"] for q in peers):
                                pending[p] = (d, stamp, float(maps[p][stamp][1]["close"]), atr[p], {q:bodies[q] for q in peers})
                                break
        history.append(stamp)
        history = history[-21:]
    return signals


def technique_fidelity_state() -> dict[str, Any]:
    primitives = ["ema_pullback", "opening_range_breakout", "bollinger_reversion", "rsi_reversion", "session_vwap_proxy", "spread_percentile_filter"]
    contracts = build_technique_contracts()
    state = {
        "schema": "AIOS_FOREX_SCALPING_TECHNIQUE_FIDELITY.v1",
        "packet_id": PACKET_ID,
        "status": "SCALPING_TECHNIQUE_CONTRACTS_COMPLETE_PRE_DATA",
        "mechanical": True,
        "causal_completed_bar_only": True,
        "subjective_chart_drawing": False,
        "centralized_volume_claims": False,
        "order_book_claims": False,
        "implemented_primitives": primitives,
        "code_fingerprint": sha256_text("|".join(primitives)),
        "inventory_contract_count": len(contracts),
        "implemented_primitive_count": len(primitives),
        "contract_only_count": sum(1 for contract in contracts if contract["implementation_status"] == "CONTRACT_ONLY_NOT_IMPLEMENTED"),
        "data_ineligible_contract_count": sum(1 for contract in contracts if not contract["data_eligible"]),
        "technique_contracts": contracts,
        "contract_registry_hash": sha256_text(stable(contracts)),
    }
    return state


def write_outputs() -> dict[str, Any]:
    state = technique_fidelity_state()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{STATE.name}.", suffix=".tmp", dir=STATE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, STATE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    REPORT.write_text(
        "# AIOS Forex Scalping Technique Fidelity V1\n\n"
        f"- Status: {state['status']}\n"
        f"- Per-technique contracts: {state['inventory_contract_count']}\n"
        f"- Implemented primitives: {state['implemented_primitive_count']}\n"
        f"- Contract-only techniques: {state['contract_only_count']}\n"
        f"- Data-ineligible contracts: {state['data_ineligible_contract_count']}\n"
        f"- Contract registry hash: {state['contract_registry_hash']}\n"
        "- LONG/SHORT evaluation remains isolated.\n"
        "- Broker/API/live work: NO\n",
        encoding="utf-8",
    )
    return state


if __name__ == "__main__":
    print(json.dumps(write_outputs(), indent=2, sort_keys=True))
