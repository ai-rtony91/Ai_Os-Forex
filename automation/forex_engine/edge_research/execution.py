"""PKT044 fixed-rule execution; pure, development-only inputs supplied by caller."""
from datetime import timedelta
import math
import heapq
from collections import defaultdict
from automation.forex_engine.edge_research.features import utc, no_entry, financing_exit
from automation.forex_engine import forex_edge_validation_pipeline_v1 as validation

END = utc("2025-04-01T00:00:00Z")
SCENARIOS = {"BASE": .1, "STRESSED": .5, "SEVERE_BUT_PLAUSIBLE": 1.0}
ARM_IDS = ("COST_CERTIFIED_SUPERTREND_BASELINE", "COST_CERTIFIED_SUPERTREND_BASELINE_PLUS_RSI14_70_30")


class PricePathUnavailable(ValueError):
    """An unobserved path, distinct from a calculation/identity defect."""
    def __init__(self, reason, **details):
        super().__init__(reason)
        self.details = details


def entry_check(row, feature, pip, challenger):
    """Only the current open and earlier completed feature may affect entry."""
    stamp = utc(row["timestamp"])
    direction = feature["event_direction"]
    if direction not in (-1, 1) or not math.isfinite(pip) or pip <= 0:
        raise ValueError("ENTRY_IDENTITY_OR_PIP_INVALID")
    if stamp != utc(feature["feature_available_at"]):
        return "SKIPPED", "NO_CONTIGUOUS_CAUSAL_ENTRY", None
    if no_entry(stamp) or stamp >= END-timedelta(minutes=10):
        return "SKIPPED", "CALENDAR_OR_BOUNDARY_NO_ENTRY", None
    if challenger:
        rsi = feature["rsi14"]
        if rsi is None:
            return "FILTERED", "RSI_WARMUP", None
        if (direction == 1 and rsi > 70) or (direction == -1 and rsi < 30):
            return "FILTERED", "RSI_THRESHOLD", None
    bid, ask = float(row["bid"]["o"]), float(row["ask"]["o"])
    validation.validate_quote(validation.Quote(row["timestamp"], bid, ask))
    stop = feature["lower_band"] if direction == 1 else feature["upper_band"]
    base_entry = ask+.1*pip if direction == 1 else bid-.1*pip
    distance = direction*(base_entry-stop) if stop is not None else 0
    # Stop must be beyond the immediately executable liquidation side, not
    # merely beyond the entry quote. Otherwise spread alone triggers it.
    valid_side = stop is not None and (stop < bid if direction == 1 else stop > ask)
    if not valid_side or distance <= 0:
        return "SKIPPED", "INVALID_INITIAL_STOP", None
    if ask-bid+.2*pip > .25*distance:
        return "SKIPPED", "BASE_COST_CEILING", None
    return "EXECUTED", None, {"direction": direction, "initial_stop": stop,
        "initial_distance": distance, "entry": base_entry, "entry_time": stamp.isoformat()}


def path_exit(rows, features, entry_index, direction, initial_stop, *, midpoint=False):
    """A shadow midpoint path is diagnostic, not a measured spread-cost delta.

    Order: gap stop; scheduled calendar/boundary/holding/opposite exit;
    intrabar stop; close-derived trailing update effective on next bar.
    Missing paths invalidate the experiment; no favorable invented exit.
    """
    first = utc(rows[entry_index]["timestamp"])
    deadline = min(financing_exit(first), END-timedelta(minutes=5), first+timedelta(minutes=5*288))
    stop, previous = initial_stop, None
    for j in range(entry_index, len(rows)):
        row, stamp = rows[j], utc(rows[j]["timestamp"])
        if previous is not None and stamp-previous != timedelta(minutes=5):
            raise PricePathUnavailable("UNRESOLVED_OPEN_POSITION_PRICE_GAP", pair=row.get("instrument"), entry_time=first.isoformat(), last_available=previous.isoformat(), next_available=stamp.isoformat(), midpoint=midpoint)
        if stamp > deadline:
            raise PricePathUnavailable("SCHEDULED_EXIT_PRICE_MISSING", pair=row.get("instrument"), entry_time=first.isoformat(), deadline=deadline.isoformat(), next_available=stamp.isoformat(), midpoint=midpoint)
        side = "mid" if midpoint else ("bid" if direction == 1 else "ask")
        quote = row[side]
        opening = float(quote["o"])
        if (direction == 1 and opening <= stop) or (direction == -1 and opening >= stop):
            return {"index": j, "time": stamp.isoformat(), "price": opening, "reason": "GAP_STOP", "phase": "OPEN"}
        if stamp == deadline:
            return {"index": j, "time": stamp.isoformat(), "price": opening, "reason": "SCHEDULED_EXIT", "phase": "OPEN"}
        if j > entry_index and features[j-1]["event_direction"] == -direction:
            return {"index": j, "time": stamp.isoformat(), "price": opening, "reason": "OPPOSITE_CONFIRMED", "phase": "OPEN"}
        touched = float(quote["l"]) <= stop if direction == 1 else float(quote["h"]) >= stop
        if touched:
            # Exact intrabar event time is unknown. Capacity released at close,
            # never at a guessed earlier point inside this candle.
            return {"index": j, "time": (stamp+timedelta(minutes=5)).isoformat(), "price": stop,
                    "reason": "STOP", "phase": "CLOSE_UNORDERED_INTRABAR"}
        band = features[j]["lower_band"] if direction == 1 else features[j]["upper_band"]
        if band is not None:
            stop = max(stop, band) if direction == 1 else min(stop, band)
        previous = stamp
    raise PricePathUnavailable("OPEN_POSITION_AT_MISSING_DEVELOPMENT_EXIT", pair=rows[entry_index].get("instrument"), entry_time=first.isoformat(), midpoint=midpoint)


def opportunity_paths(pair, rows, features, pip):
    """One original signal population; selected paths independent of capacity.

    All net scenarios use identical signal/stop timestamps. Midpoint gross is
    its separately labelled shadow path, not an invented midpoint at a bid stop.
    """
    opportunities = []
    for i, feature in enumerate(features):
        if not feature["event_direction"]:
            continue
        identity = pair+":"+feature["timestamp"]
        item = {"id": identity, "pair": pair, "feature": feature, "arms": [], "pip": pip,
                "entry_spread": (float(rows[i+1]["ask"]["o"])-float(rows[i+1]["bid"]["o"])) if i+1 < len(rows) else None}
        if i+1 == len(rows):
            item["arms"] = [{"status": "SKIPPED", "reason": "NO_CAUSAL_ENTRY", "net": None} for _ in ARM_IDS]
            opportunities.append(item)
            continue
        shared = None
        for challenger in (False, True):
            status, reason, entry = entry_check(rows[i+1], feature, pip, challenger)
            arm = {"status": status, "reason": reason, "net": None}
            if entry is not None:
                if shared is None:
                    direction = entry["direction"]
                    exit_row = path_exit(rows, features, i+1, direction, entry["initial_stop"])
                    gross_unavailable = None
                    try:
                        gross_exit = path_exit(rows, features, i+1, direction, entry["initial_stop"], midpoint=True)
                    except PricePathUnavailable as error:
                        # Diagnostic only. Never catch or replace a net-path
                        # failure, and never drop the original opportunity.
                        gross_exit = None
                        gross_unavailable = {"reason": str(error), **error.details}
                    entry_side = float(rows[i+1]["ask" if direction == 1 else "bid"]["o"])
                    net = {name: direction*(exit_row["price"]-direction*slip*pip-entry_side-direction*slip*pip)
                           for name, slip in SCENARIOS.items()}
                    gross = direction*(gross_exit["price"]-float(rows[i+1]["mid"]["o"])) if gross_exit is not None else None
                    shared = {**entry, "entry_index": i+1, "exit": exit_row, "gross_exit": gross_exit,
                        "quote_pnl": net, "gross_quote_pnl": gross,
                        "net_r": {k:v/entry["initial_distance"] for k,v in net.items()},
                        "gross_r": gross/entry["initial_distance"] if gross is not None else None,
                        "gross_unavailable": gross_unavailable,
                        "gross_method": "MIDPOINT_SHADOW_PATH_SAME_RULES_DIFFERENT_STOP_TRIGGER_POSSIBLE"}
                    side = "bid" if direction == 1 else "ask"
                    # Net liquidation marks of completed bars. A stop in the
                    # last bar is recorded once as an exit, not again as a mark.
                    shared["marks"] = [
                        ((utc(rows[k]["timestamp"])+timedelta(minutes=5)).isoformat(),
                         float(rows[k][side]["c"]))
                        for k in range(i+1, exit_row["index"])]
                arm.update(path=shared, net=shared["net_r"]["BASE"])
            item["arms"].append(arm)
        opportunities.append(item)
    return opportunities


def certify_executable_paths(pair, rows, features, pip, *, candidate_ids):
    """Check frozen entry/exit price availability without calculating a return.

    This is deliberately narrower than :func:`opportunity_paths`: it uses the
    exact signal, entry, stop and exit clock but never computes P&L, gross
    diagnostics, portfolio allocation or candidate ranking.  A normal skipped
    opportunity remains a recorded no-entry outcome; an open position whose
    required price path is missing is a certification blocker.
    """
    if len(candidate_ids) != 2 or len(set(candidate_ids)) != 2:
        raise ValueError("EXECUTABLE_PATH_CERTIFICATION_CANDIDATE_IDENTITY_INVALID")
    if len(rows) != len(features):
        raise ValueError("EXECUTABLE_PATH_CERTIFICATION_ROW_FEATURE_ALIGNMENT_INVALID")
    checked = 0
    attempted_entries = {candidate: 0 for candidate in candidate_ids}
    skipped = {candidate: {} for candidate in candidate_ids}
    unresolved = []
    for index, feature in enumerate(features):
        if not feature.get("event_direction"):
            continue
        checked += 1
        if index + 1 == len(rows):
            for candidate in candidate_ids:
                skipped[candidate]["NO_CAUSAL_ENTRY_AT_DEVELOPMENT_BOUNDARY"] = (
                    skipped[candidate].get("NO_CAUSAL_ENTRY_AT_DEVELOPMENT_BOUNDARY", 0) + 1
                )
            continue
        shared_path_checked = False
        for challenger, candidate in enumerate(candidate_ids):
            status, reason, entry = entry_check(rows[index + 1], feature, pip, bool(challenger))
            if entry is None:
                reason = reason or status
                skipped[candidate][reason] = skipped[candidate].get(reason, 0) + 1
                continue
            attempted_entries[candidate] += 1
            if shared_path_checked:
                continue
            try:
                path_exit(rows, features, index + 1, entry["direction"], entry["initial_stop"])
            except PricePathUnavailable as error:
                unresolved.append({
                    "PAIR": pair,
                    "CANDIDATE_IDS": list(candidate_ids),
                    "SIGNAL_TIMESTAMP": feature.get("timestamp"),
                    "ENTRY_TIMESTAMP": entry.get("entry_time"),
                    "REASON": str(error),
                    "DETAILS": error.details,
                })
            shared_path_checked = True
    return {
        "PAIR": pair,
        "SIGNAL_EVENTS": checked,
        "ATTEMPTED_ENTRIES": attempted_entries,
        "NORMAL_SKIPS": skipped,
        "UNRESOLVED_REQUIRED_EXECUTABLE_PATHS": unresolved,
        "OUTCOME_EXPOSURE": "FROZEN_EXECUTION_AVAILABILITY_ONLY_NO_PNL_OR_RANKING",
    }


def quote_to_usd(currency, timestamp, quotes, *, positive=True):
    """Side-correct conversion at the declared settlement time, no stale quotes."""
    if currency == "USD":
        return 1.0
    direct, inverse = currency+"_USD", "USD_"+currency
    if direct in quotes:
        bid, ask = quotes[direct](timestamp)
        return bid if positive else ask
    if inverse in quotes:
        bid, ask = quotes[inverse](timestamp)
        return 1/ask if positive else 1/bid
    raise ValueError("ACCOUNT_CONVERSION_PAIR_MISSING:"+currency)


def portfolio(opportunities, arm, quote_provider, scenario="BASE", starting_equity=100000., check_limits=lambda: None):
    """Separate realizable lifecycles with starting-equity risk, not pooled pips.

    quote_provider(currency, time, phase, positive) supplies same-time causal
    conversion. Intrabar fills settle at candle close, without guessed ordering.
    """
    if arm not in (0, 1) or scenario not in SCENARIOS or starting_equity <= 0:
        raise ValueError("PORTFOLIO_CONTRACT_INVALID")
    items = sorted(opportunities, key=lambda o: (o["feature"]["feature_available_at"], o["pair"]))
    events, serial = [], 0
    for item in items:
        if item["arms"][arm]["status"] == "EXECUTED":
            serial += 1
            heapq.heappush(events, (item["arms"][arm]["path"]["entry_time"], 2, item["pair"], serial, "ENTRY", item, None))
    positions, decisions, trades = {}, [], []
    cash, curve, max_open = starting_equity, [starting_equity], 0
    currency_max = defaultdict(float)
    work_units = 0
    while events:
        work_units += 1
        if work_units % 1024 == 0: check_limits()
        timestamp, phase = events[0][:2]
        same_phase = []
        while events and events[0][:2] == (timestamp, phase):
            same_phase.append(heapq.heappop(events))
        for _, _, pair, _, action, item, price in same_phase:
            identity = item["id"]
            path = item["arms"][arm]["path"]
            quote_currency = pair.split("_")[1]
            if action == "ENTRY":
                currencies = pair.split("_")
                used = defaultdict(float)
                for existing in positions.values():
                    for currency in existing["pair"].split("_"):
                        used[currency] += .0025
                reason = None
                if any(pos["pair"] == pair for pos in positions.values()): reason = "PAIR_POSITION_LIMIT"
                elif len(positions) >= 4: reason = "TOTAL_OPEN_RISK_OR_POSITION_LIMIT"
                elif any(used[currency]+.0025 > .01+1e-15 for currency in currencies): reason = "CURRENCY_RISK_LIMIT"
                if reason:
                    decisions.append({"id": identity, "status": "SKIPPED", "reason": reason})
                    continue
                conversion = quote_provider(quote_currency, timestamp, "OPEN", False)
                units = starting_equity*.0025/(path["initial_distance"]*conversion)
                if not math.isfinite(units) or units <= 0:
                    raise ValueError("PORTFOLIO_INVALID_SIZING")
                pip = item["pip"]
                # path.entry includes BASE slip; replace only that slip.
                entry_price = path["entry"]+path["direction"]*(SCENARIOS[scenario]-.1)*pip
                positions[identity] = {"pair": pair, "units": units, "entry": entry_price, "mark": 0., "direction": path["direction"]}
                decisions.append({"id": identity, "status": "EXECUTED", "units": units})
                max_open = max(max_open, len(positions))
                for currency in currencies:
                    currency_max[currency] = max(currency_max[currency], used[currency]+.0025)
                for when, marked_price in path["marks"]:
                    serial += 1
                    heapq.heappush(events, (when, 0, pair, serial, "MARK", item, marked_price))
                exit_phase = 1 if path["exit"]["phase"] == "OPEN" else 0
                serial += 1
                heapq.heappush(events, (path["exit"]["time"], exit_phase, pair, serial, "EXIT", item, path["exit"]["price"]))
                # Entry liquidation loss belongs in marked drawdown immediately.
                price = entry_price-path["direction"]*(item["entry_spread"]+2*SCENARIOS[scenario]*pip)
                action = "ENTRY_MARK"
            position = positions.get(identity)
            if position is None:
                raise ValueError("PORTFOLIO_POSITION_LIFECYCLE_INVALID")
            if action != "ENTRY_MARK":
                price -= position["direction"]*SCENARIOS[scenario]*item["pip"]
            quote_pnl = position["direction"]*(price-position["entry"])*position["units"]
            conversion_phase = "OPEN" if phase in (1, 2) else "CLOSE"
            cash_pnl = quote_pnl*quote_provider(quote_currency, timestamp, conversion_phase, quote_pnl >= 0)
            if not math.isfinite(cash_pnl):
                raise ValueError("PORTFOLIO_NONFINITE_PNL")
            position["mark"] = cash_pnl
            if action == "EXIT":
                cash += cash_pnl
                trades.append({"id": identity, "pair": pair, "entry_time": path["entry_time"],
                    "exit_time": timestamp, "pnl_usd": cash_pnl, "units": position["units"],
                    "direction": position["direction"], "reason": path["exit"]["reason"]})
                del positions[identity]
        equity = cash+sum(position["mark"] for position in positions.values())
        if equity <= 0:
            raise ValueError("PORTFOLIO_INSOLVENT")
        curve.append(equity)
    if positions:
        raise ValueError("PORTFOLIO_OPEN_LIFECYCLE_AT_END")
    return {"account_currency": "USD", "starting_equity": starting_equity, "ending_equity": cash,
        "net_pnl_usd": cash-starting_equity, "maximum_drawdown": validation.maximum_drawdown(curve),
        "equity_curve": curve, "decisions": decisions, "trades": trades,
        "maximum_positions": max_open, "currency_open_risk_max": dict(currency_max),
        "settlement": "INTRABAR_EXITS_SETTLED_AT_BAR_CLOSE_WITH_SIDE_CORRECT_FX_CONVERSION"}
