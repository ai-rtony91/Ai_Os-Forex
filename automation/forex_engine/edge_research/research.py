"""Bounded PKT044 calculations called by the existing factory, not a controller."""
from array import array
from bisect import bisect_left
from collections import defaultdict, deque, Counter
from datetime import timedelta, datetime, timezone
import copy
import math
import statistics

from automation.forex_engine import forex_edge_discovery_tournament_stage1_v1 as data
from automation.forex_engine import forex_edge_validation_pipeline_v1 as validation
from automation.forex_engine import forex_control_baseline_rsi_filter_comparison_stage1_v1 as handoff
from automation.forex_engine.edge_research import data as pkt045_data
from automation.forex_engine.edge_research.features import snapshots, utc
from automation.forex_engine.edge_research.execution import (
    ARM_IDS, SCENARIOS, certify_executable_paths, opportunity_paths, portfolio,
)


# PKT-045 is deliberately a new research specification, not a repair of the
# frozen PKT-044 native-MID experiment.  These identities are data- and
# rule-derived only; they never consume a market outcome or write research
# memory.
PKT045_PACKET_ID = "PKT-FOREX-045"
PKT045_PARENT_PACKET_ID = "PKT-FOREX-044"
PKT045_EXPERIMENT_ID = "EXP_FOREX_045_DUKASCOPY_PAIRED_TICK_MID_AB_V1"
PKT045_DATA_SEMANTICS_VERSION = "DUKASCOPY_PAIRED_TICK_MID_THEN_M5_V1"
PKT045_SOURCE_REQUIREMENT_VERSION = "DUKASCOPY_PAIRED_TICK_SOURCE_REQUIREMENTS_V1"
PKT045_TARGET_PAIR_COUNT = 58
PKT045_BASELINE_ID = "DUKASCOPY_TICK_MID_COST_CERTIFIED_SUPERTREND_BASELINE"
PKT045_CHALLENGER_ID = "DUKASCOPY_TICK_MID_COST_CERTIFIED_SUPERTREND_BASELINE_PLUS_RSI14_70_30"
PKT045_DEVELOPMENT_START = "2024-01-01T00:00:00+00:00"
PKT045_DEVELOPMENT_END = "2025-04-01T00:00:00+00:00"
PKT045_SETUP_ID = "PKT045_DUKASCOPY_PAIRED_TICK_MID_ST3_2_TWO_CLOSE"


def specifications(pairs):
    common = {
        "signal_family": "COST_CERTIFIED_SUPERTREND_BASELINE",
        "data_identity": {"corpus": data.CORPUS_ID, "manifest_sha256": data.CORPUS_MANIFEST_SHA256,
                          "metadata_sha256": data.INSTRUMENT_METADATA_SHA256,
                          "start": data.DEV_START.isoformat(), "end_exclusive": data.DEV_END.isoformat()},
        "formation_horizon": "CONTIGUOUS_M5_RESET_AT_ANY_GAP_ATR3_FIRST_INDEX2_RSI14_FIRST_INDEX14",
        "execution_horizon": "M5_NEXT_CONTIGUOUS_OPEN",
        "direction": "SYMMETRIC_BIDIRECTIONAL",
        "entry_rule": "EXISTING_SUPERTREND_ATR3_MULTIPLIER2_TWO_CLOSE_CONFIRMATION_INITIAL_STATE_AND_CHANGES_ONE_EVENT",
        "exit_rule": {"initial_stop": "CONFIRMATION_LOWER_BAND_LONG_UPPER_SHORT_MUST_BE_BEYOND_LIQUIDATION_OPEN",
            "trailing": "COMPLETED_BAND_NEVER_LOOSEN_EFFECTIVE_NEXT_BAR", "opposite": "TWO_CLOSE_OPPOSITE_NEXT_OPEN",
            "maximum_bars": 288, "take_profit": None,
            "order": ["GAP_STOP", "SCHEDULED_EXIT", "OPPOSITE_EXIT", "INTRABAR_STOP", "CLOSE_TRAILING_UPDATE"],
            "financing_exit": "16:30_AMERICA_NEW_YORK_US_DST_2024_2025",
            "development_exit": "2025-03-31T23:55:00Z_OPEN",
            "missing_path": "INVALID_TEST_NOT_ASSUMED_FILL",
            "intrabar_settlement": "BAR_CLOSE_NO_EARLIER_CAPACITY_RELEASE"},
        "cost_contract": {"pip": "CERTIFIED_PER_PAIR", "fills": "LONG_ASK_BID_SHORT_BID_ASK",
            "slippage_pips_per_side": SCENARIOS,
            "entry_cost_ceiling": "CURRENT_OPEN_SPREAD_PLUS_0.2_PIP_LE_25_PERCENT_BASE_INITIAL_DISTANCE",
            "spread": "EMBEDDED_ONCE", "financing": "NO_17_NY_EXPOSURE",
            "gross": "MIDPOINT_SHADOW_SAME_RULES_NO_SLIPPAGE_NOT_PAIRED_SPREAD_ESTIMATE"},
        "regime_filters": {"calendar": "NO_ENTRY_16:00_THROUGH_17:15_NY_WEEKEND_JAN1_DEC25_OR_LAST10_DEV_MINUTES",
                           "rsi": None},
        "pair_currency_universe": list(pairs),
        "parameters": {"atr": 3, "multiplier": 2., "confirm_bars": 2, "rsi": 14},
        "portfolio_rules": {"account": "USD", "starting_equity": 100000., "risk_starting_equity": .0025,
            "positions": 4, "total_risk": .01, "currency_gross_risk": .01, "per_pair": 1,
            "priority": "TIMESTAMP_THEN_PAIR", "fx": "SHORTEST_LEXICAL_PATH_SIDE_CORRECT_SAME_TIME",
            "valuation": "LIQUIDATION_AT_COMPLETED_CLOSE_AND_EVENT_OPEN", "sizing": "BASE_RISK_SIZE_FIXED_ACROSS_COST_STRESS"}}
    challenger = copy.deepcopy(common)
    challenger["regime_filters"]["rsi"] = "WILDER14_LONG_LE70_SHORT_GE30_MISSING_FILTERED"
    return [{"candidate_id": identity, "specification": spec, "fingerprint": validation.candidate_fingerprint(spec)}
            for identity, spec in zip(ARM_IDS, (common, challenger))]


def _pkt045_pairs(pairs):
    """Freeze the successor's target universe without reading any prices."""
    normalized = tuple(sorted({str(pair) for pair in pairs}))
    if len(normalized) != PKT045_TARGET_PAIR_COUNT:
        raise ValueError("PKT045_TARGET_PAIR_UNIVERSE_NOT_EXACT_58")
    if any(not pair or "_" not in pair for pair in normalized):
        raise ValueError("PKT045_TARGET_PAIR_IDENTIFIER_INVALID")
    return normalized


def paired_tick_mid_successor_specifications(pairs):
    """Return PKT-045's unscored, separately fingerprinted A/B cards.

    The source-derived midpoint is explicitly created from a same-record
    bid/ask tick before M5 aggregation.  It must never be substituted for the
    PKT-044 provider-native MID stream.  This helper only freezes a proposed
    contract; it neither opens a corpus nor permits a score.
    """
    universe = _pkt045_pairs(pairs)
    common = copy.deepcopy(specifications(universe)[0]["specification"])
    common.update({
        "signal_family": PKT045_BASELINE_ID,
        "data_identity": {
            "provider": "DUKASCOPY",
            "source_type": "PAIRED_TICK",
            "corpus": "UNACQUIRED_PKT045_DUKASCOPY_PAIRED_TICK_MID",
            "corpus_status": "PREACQUISITION_NO_CERTIFIED_CORPUS",
            "data_semantics_version": PKT045_DATA_SEMANTICS_VERSION,
            "source_requirement_version": PKT045_SOURCE_REQUIREMENT_VERSION,
            "start": PKT045_DEVELOPMENT_START,
            "end_exclusive": PKT045_DEVELOPMENT_END,
        },
        "research_identity": {
            "packet_id": PKT045_PACKET_ID,
            "experiment_id": PKT045_EXPERIMENT_ID,
            "parent_packet_id": PKT045_PARENT_PACKET_ID,
            "parent_outcome": "MATERIAL_DATA_SEMANTICS_CHANGE",
            "data_semantics_version": PKT045_DATA_SEMANTICS_VERSION,
            "source_requirement_version": PKT045_SOURCE_REQUIREMENT_VERSION,
        },
        "price_semantics": {
            "signal_mid": "MID_T_EQUALS_BID_T_PLUS_ASK_T_DIVIDED_BY_2_SAME_SOURCE_RECORD_ONLY",
            "m5_mid": "FIRST_MAX_MIN_LAST_MID_T_IN_COMPLETED_UTC_FIVE_MINUTE_INTERVAL",
            "execution": "OBSERVED_DUKASCOPY_BID_ASK_SIDE_CORRECT",
            "forbidden": (
                "NEAREST_NEIGHBOR_BID_ASK_PAIRING",
                "CANDLE_LEVEL_BID_ASK_EXTREMA_AVERAGING",
                "INTERPOLATION",
                "FORWARD_FILL",
                "FUTURE_DATA",
                "MIXED_PROVIDER_VALUES",
            ),
        },
        "pair_currency_universe": list(universe),
    })
    challenger = copy.deepcopy(common)
    challenger["regime_filters"]["rsi"] = "WILDER14_LONG_LE70_SHORT_GE30_MISSING_FILTERED"
    return [
        {"candidate_id": PKT045_BASELINE_ID, "specification": common,
         "fingerprint": validation.candidate_fingerprint(common)},
        {"candidate_id": PKT045_CHALLENGER_ID, "specification": challenger,
         "fingerprint": validation.candidate_fingerprint(challenger)},
    ]


def paired_tick_mid_successor_context(pairs):
    """Build the no-outcome context consumed by the preregistration handoff."""
    universe = _pkt045_pairs(pairs)
    cards = paired_tick_mid_successor_specifications(universe)
    return {
        "packet_id": PKT045_PACKET_ID,
        "experiment_id": PKT045_EXPERIMENT_ID,
        "parent_packet_id": PKT045_PARENT_PACKET_ID,
        "parent_outcome": "MATERIAL_DATA_SEMANTICS_CHANGE",
        "data_semantics_version": PKT045_DATA_SEMANTICS_VERSION,
        "source_requirement_version": PKT045_SOURCE_REQUIREMENT_VERSION,
        "provider": "DUKASCOPY",
        "source_type": "PAIRED_TICK",
        "required_price_sides": ("BID", "ASK"),
        "same_record_pairing": True,
        "timestamp_semantics": "SOURCE_NATIVE_CAUSAL_TICK_ORDER",
        "midpoint_semantics": "PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION",
        "m5_aggregation": "FIRST_MAX_MIN_LAST_MID_T_COMPLETED_UTC_M5_ONLY",
        "execution_price_semantics": "SOURCE_BACKED_BID_ASK_SIDE_CORRECT",
        "pair_universe": list(universe),
        "development_start": PKT045_DEVELOPMENT_START,
        "development_end_exclusive": PKT045_DEVELOPMENT_END,
        "cards": cards,
        "scoring_allowed": False,
        "market_outcomes_opened": False,
    }


def validate_paired_tick_mid_successor_context(context):
    """Fail closed before PKT-045 can plan acquisition or reach a scorer."""
    required = {
        "packet_id": PKT045_PACKET_ID,
        "experiment_id": PKT045_EXPERIMENT_ID,
        "parent_packet_id": PKT045_PARENT_PACKET_ID,
        "parent_outcome": "MATERIAL_DATA_SEMANTICS_CHANGE",
        "data_semantics_version": PKT045_DATA_SEMANTICS_VERSION,
        "source_requirement_version": PKT045_SOURCE_REQUIREMENT_VERSION,
        "provider": "DUKASCOPY",
        "source_type": "PAIRED_TICK",
        "same_record_pairing": True,
        "timestamp_semantics": "SOURCE_NATIVE_CAUSAL_TICK_ORDER",
        "midpoint_semantics": "PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION",
        "m5_aggregation": "FIRST_MAX_MIN_LAST_MID_T_COMPLETED_UTC_M5_ONLY",
        "execution_price_semantics": "SOURCE_BACKED_BID_ASK_SIDE_CORRECT",
        "scoring_allowed": False,
        "market_outcomes_opened": False,
    }
    if not isinstance(context, dict):
        raise ValueError("PKT045_CONTEXT_INVALID")
    for key, value in required.items():
        if context.get(key) != value:
            raise ValueError(f"PKT045_CONTEXT_{key.upper()}_MISMATCH")
    if tuple(context.get("required_price_sides", ())) != ("BID", "ASK"):
        raise ValueError("PKT045_CONTEXT_EXECUTION_SIDE_REQUIREMENT_INVALID")
    universe = _pkt045_pairs(context.get("pair_universe", ()))
    cards = context.get("cards")
    if not isinstance(cards, list) or len(cards) != 2:
        raise ValueError("PKT045_CONTEXT_CARD_COUNT_INVALID")
    expected = (PKT045_BASELINE_ID, PKT045_CHALLENGER_ID)
    if tuple(card.get("candidate_id") for card in cards) != expected:
        raise ValueError("PKT045_CONTEXT_CANDIDATE_IDENTITY_INVALID")
    if len({card.get("fingerprint") for card in cards}) != 2:
        raise ValueError("PKT045_CONTEXT_FINGERPRINT_DUPLICATE")
    for card in cards:
        if validation.candidate_fingerprint(card.get("specification")) != card.get("fingerprint"):
            raise ValueError("PKT045_CONTEXT_FINGERPRINT_INVALID")
        if card["specification"].get("pair_currency_universe") != list(universe):
            raise ValueError("PKT045_CONTEXT_PAIR_UNIVERSE_MISMATCH")
    changed = {
        key for key in set(cards[0]["specification"]) | set(cards[1]["specification"])
        if cards[0]["specification"].get(key) != cards[1]["specification"].get(key)
    }
    if changed != {"regime_filters"}:
        raise ValueError("PKT045_CONTEXT_NOT_ONE_CONTROLLED_CHANGE")
    left = cards[0]["specification"]["regime_filters"]
    right = cards[1]["specification"]["regime_filters"]
    if set(left) != set(right) or {key for key in left if left[key] != right[key]} != {"rsi"}:
        raise ValueError("PKT045_CONTEXT_RSI_NOT_ONLY_CHANGE")
    return {
        "status": "PASS",
        "packet_id": PKT045_PACKET_ID,
        "experiment_id": PKT045_EXPERIMENT_ID,
        "candidate_ids": list(expected),
        "pair_count": len(universe),
        "fingerprints": [card["fingerprint"] for card in cards],
        "scoring_status": "BLOCKED_AWAITING_CERTIFIED_CORPUS_AND_FUTURE_AUTHORITY",
    }


def conversion_paths(pairs):
    graph = defaultdict(list)
    for pair in sorted(pairs):
        base, quote = pair.split("_")
        graph[base].append((quote, pair, True))
        graph[quote].append((base, pair, False))
    paths = {"USD": []}
    for currency in sorted(graph):
        todo, seen = deque([(currency, [])]), {currency}
        while todo:
            node, path = todo.popleft()
            if node == "USD":
                paths[currency] = path
                break
            for neighbor, pair, direct in sorted(graph[node]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    todo.append((neighbor, path+[(pair, direct)]))
        if currency not in paths:
            raise ValueError("USD_CONVERSION_GRAPH_DISCONNECTED")
    return paths


def quote_provider(tables, paths):
    def convert(currency, timestamp, phase, positive):
        moment = int(utc(timestamp).timestamp())
        lookup = moment if phase == "OPEN" else moment-300
        rate = 1.
        for pair, direct in paths[currency]:
            table = tables[pair]
            index = bisect_left(table["time"], lookup)
            if index == len(table["time"]) or table["time"][index] != lookup:
                raise ValueError("CAUSAL_FX_CONVERSION_QUOTE_MISSING:"+pair+":"+timestamp+":"+phase)
            bid = table["bo" if phase == "OPEN" else "bc"][index]
            ask = table["ao" if phase == "OPEN" else "ac"][index]
            validation.validate_quote(validation.Quote(timestamp, bid, ask))
            rate *= (bid if positive else ask) if direct else 1/(ask if positive else bid)
        return rate
    return convert


def prepare_inputs(corpus, manifest, progress, before_outcome, check_limits):
    """Checked development reader only; no full-corpus hashing or cached prices."""
    metadata = data.certified_instrument_metadata()
    tables, opportunities, verification = {}, [], {}
    for number, pair in enumerate(manifest["eligible_pairs"], 1):
        check_limits()
        rows = data.read_pair_bars(corpus, manifest, pair, verification, before_outcome=before_outcome)
        features = snapshots(pair, rows)
        table = {key: array("q" if key == "time" else "d") for key in ("time", "bo", "ao", "bc", "ac")}
        for row in rows:
            table["time"].append(int(utc(row["timestamp"]).timestamp()))
            for key, side, field in (("bo", "bid", "o"), ("ao", "ask", "o"), ("bc", "bid", "c"), ("ac", "ask", "c")):
                table[key].append(float(row[side][field]))
        tables[pair] = table
        opportunities.extend(opportunity_paths(pair, rows, features, float(metadata[pair]["pip_size"])))
        progress("PREPARE_PAIRS", number, len(manifest["eligible_pairs"]), {"pair": pair, "records": len(rows), "opportunities": len(opportunities)})
        del rows, features
        check_limits()
    return opportunities, tables, verification


def _pkt045_pip(pair, source_metadata):
    metadata = source_metadata.get(pair)
    if not isinstance(metadata, dict):
        raise ValueError("PKT045_SOURCE_METADATA_PAIR_MISSING:" + pair)
    pip = metadata.get("pip_size")
    if isinstance(pip, bool) or not isinstance(pip, (int, float)) or not math.isfinite(pip) or pip <= 0:
        raise ValueError("PKT045_SOURCE_METADATA_PIP_INVALID:" + pair)
    return float(pip)


def _pkt045_quote_table(rows):
    table = {key: array("q" if key == "time" else "d") for key in ("time", "bo", "ao", "bc", "ac")}
    for row in rows:
        table["time"].append(int(utc(row["timestamp"]).timestamp()))
        for key, side, field in (("bo", "bid", "o"), ("ao", "ask", "o"), ("bc", "bid", "c"), ("ac", "ask", "c")):
            table[key].append(float(row[side][field]))
    return table


def certify_pkt045_successor_availability(
    corpus_root, pairs, source_metadata, progress, check_limits,
):
    """Prove frozen executable-price availability without calculating returns.

    The pass does derive frozen indicators and entry/exit clocks, but it never
    calls opportunity scoring, portfolio allocation, P&L, uncertainty, or a
    candidate ranking.  Its result is therefore a data/execution certification
    input rather than a market-performance result.
    """
    universe = _pkt045_pairs(pairs)
    if set(universe) != set(source_metadata):
        raise ValueError("PKT045_AVAILABILITY_SOURCE_METADATA_UNIVERSE_MISMATCH")
    report = {
        "schema": "AIOS_PKT045_EXECUTABLE_PATH_AVAILABILITY_V1",
        "PACKET_ID": PKT045_PACKET_ID,
        "EXPERIMENT_ID": PKT045_EXPERIMENT_ID,
        "PAIR_COUNT": len(universe),
        "OUTCOME_EXPOSURE": "FROZEN_EXECUTION_AVAILABILITY_ONLY_NO_PNL_OR_RANKING",
        "PAIR_RESULTS": {},
        "UNRESOLVED_REQUIRED_EXECUTABLE_PATHS": [],
    }
    candidate_ids = (PKT045_BASELINE_ID, PKT045_CHALLENGER_ID)
    for number, pair in enumerate(universe, 1):
        check_limits()
        rows = pkt045_data.read_paired_tick_m5_rows(corpus_root=corpus_root, pair=pair)
        features = snapshots(pair, rows, setup_id=PKT045_SETUP_ID)
        result = certify_executable_paths(pair, rows, features, _pkt045_pip(pair, source_metadata), candidate_ids=candidate_ids)
        report["PAIR_RESULTS"][pair] = {
            "M5_ROWS": len(rows),
            "SOURCE_MIDPOINT_METHOD": pkt045_data.PKT045_MIDPOINT_METHOD,
            **result,
        }
        report["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS"].extend(result["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS"])
        progress("EXECUTABLE_PATH_CERTIFICATION", number, len(universe), {
            "pair": pair,
            "m5_rows": len(rows),
            "unresolved": len(result["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS"]),
        })
        del rows, features
        check_limits()
    report["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS"] = sorted(
        report["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS"],
        key=lambda item: (item["PAIR"], item["SIGNAL_TIMESTAMP"], item["ENTRY_TIMESTAMP"], item["REASON"]),
    )
    report["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS_COUNT"] = len(report["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS"])
    report["EXECUTABLE_DATA_CERTIFICATION"] = (
        "PASS" if not report["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS"] else "FAIL"
    )
    return report


def prepare_pkt045_inputs(corpus_root, pairs, source_metadata, progress, before_outcome, check_limits):
    """Open the certified PKT-045 corpus for the first result only.

    This deliberately has no fallback to the PKT-044/OANDA reader.  The caller
    must make the first outcome examination durable *before* this function
    reads its first successor price row.
    """
    universe = _pkt045_pairs(pairs)
    if set(universe) != set(source_metadata):
        raise ValueError("PKT045_PREPARE_SOURCE_METADATA_UNIVERSE_MISMATCH")
    if not callable(before_outcome):
        raise ValueError("PKT045_OUTCOME_ACCESS_CALLBACK_REQUIRED")
    tables, opportunities, verification = {}, [], {}
    outcome_access_started = False
    for number, pair in enumerate(universe, 1):
        check_limits()
        if not outcome_access_started:
            before_outcome()
            outcome_access_started = True
        rows = pkt045_data.read_paired_tick_m5_rows(corpus_root=corpus_root, pair=pair)
        features = snapshots(pair, rows, setup_id=PKT045_SETUP_ID)
        tables[pair] = _pkt045_quote_table(rows)
        opportunities.extend(opportunity_paths(pair, rows, features, _pkt045_pip(pair, source_metadata)))
        verification[pair] = {
            "records": len(rows),
            "midpoint_method": pkt045_data.PKT045_MIDPOINT_METHOD,
            "source": "PKT045_CERTIFIED_DUKASCOPY_PAIRED_TICK_CORPUS",
        }
        progress("PREPARE_PKT045_PAIRS", number, len(universe), {
            "pair": pair, "records": len(rows), "opportunities": len(opportunities),
        })
        del rows, features
        check_limits()
    return opportunities, tables, verification


def measures(values):
    missing = sum(value is None for value in values)
    if missing:
        return {"count": len(values), "available_count": len(values)-missing, "missing_count": missing,
                "expectancy": None, "profit_factor": None, "win_rate": None, "average_win": None, "average_loss": None,
                "status": "UNAVAILABLE_INCOMPLETE_COVERAGE_NO_SUBSET_ESTIMATE"}
    if not values:
        return {"count": 0, "expectancy": None, "profit_factor": None, "win_rate": None, "average_win": None, "average_loss": None}
    wins, losses = [x for x in values if x > 0], [x for x in values if x < 0]
    return {"count": len(values), "expectancy": statistics.fmean(values),
        "profit_factor": sum(wins)/-sum(losses) if losses else None,
        "no_losses": not losses, "win_rate": len(wins)/len(values),
        "average_win": statistics.fmean(wins) if wins else None,
        "average_loss": statistics.fmean(losses) if losses else None}


def attribution(opportunities, arm):
    dimensions = {name: defaultdict(list) for name in ("pair", "currency", "direction", "month", "session", "volatility", "spread")}
    for item in opportunities:
        result = item["arms"][arm]
        if result["status"] != "EXECUTED": continue
        f, value = item["feature"], result["net"]
        labels = {"pair": item["pair"], "direction": "LONG" if f["event_direction"] == 1 else "SHORT",
                  "month": f["timestamp"][:7], "session": "NY_08_12" if 8 <= f["ny_hour"] < 12 else "NY_12_16" if 12 <= f["ny_hour"] < 16 else "OTHER",
                  "volatility": "RANGE_ABOVE_ATR3" if f["range"] > f["atr3"] else "RANGE_AT_OR_BELOW_ATR3",
                  "spread": "SPREAD_ABOVE_10PCT_ATR" if f["spread_close"] > .1*f["atr3"] else "SPREAD_AT_OR_BELOW_10PCT_ATR"}
        for name, label in labels.items(): dimensions[name][label].append(value)
        for currency in item["pair"].split("_"): dimensions["currency"][currency].append(value/2)
    report = {name: {label: {**measures(values), "sum_r": sum(values)} for label, values in sorted(groups.items())} for name, groups in dimensions.items()}
    report["units"] = "DESCRIPTIVE_R_NOT_CASH_OR_INDEPENDENT_CURRENCY_EVIDENCE"
    removal = {}
    for name in ("pair", "currency"):
        if not report[name]:
            removal[name] = None
            continue
        strongest = max(report[name], key=lambda key: (report[name][key]["sum_r"], key))
        remaining = [item["arms"][arm]["net"] for item in opportunities if item["arms"][arm]["status"] == "EXECUTED"
                     and (item["pair"] != strongest if name == "pair" else strongest not in item["pair"].split("_"))]
        removal[name] = {"removed": strongest, "remaining": measures(remaining), "research_choice_only": True}
    report["strongest_removed"] = removal
    return report


def measure_batch(opportunities, tables, cards, progress, check_limits, *, development_start=None, development_end=None):
    """One result feeds checked summaries and the existing bounded planner."""
    provider = quote_provider(tables, conversion_paths(sorted(tables)))
    output = {"arms": [], "matched": None, "verified_edge": False}
    day_values = defaultdict(lambda: {p: 0. for p in tables})
    for item in opportunities:
        day = item["feature"]["timestamp"][:10]
        a, b = [(x["net"] if x["status"] == "EXECUTED" else 0.) for x in item["arms"]]
        day_values[day][item["pair"]] += b-a
    # Entire frozen calendar retained, including no-opportunity days. Zero
    # denotes the defined strategy's zero return, never missing market prices.
    synchronized = []
    start = data.DEV_START if development_start is None else utc(development_start) if isinstance(development_start, str) else development_start
    end = data.DEV_END if development_end is None else utc(development_end) if isinstance(development_end, str) else development_end
    if not isinstance(start, datetime) or not isinstance(end, datetime) or start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("MEASURE_BATCH_DEVELOPMENT_BOUNDARY_INVALID")
    day = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    while day < end:
        stamp = day.strftime("%Y-%m-%d")
        synchronized.append({"timestamp": stamp+"T00:00:00Z", "pair_returns": day_values[stamp]})
        day += timedelta(days=1)
    uncertainty = validation.synchronized_block_bootstrap(synchronized, block_size=2, label_horizon=2, runs=512, seed=44044)
    output["matched"] = {"original_opportunities": len(opportunities),
        "delta_r_per_original_opportunity": sum(sum(row["pair_returns"].values()) for row in synchronized)/len(opportunities) if opportunities else None,
        "uncertainty": uncertainty, "uncertainty_unit": "DAILY_PAIR_MEAN_R_DIFFERENCE",
        "calendar_days": len(synchronized), "not_independent_confirmation": True}
    for arm, card in enumerate(cards):
        selected = [o["arms"][arm] for o in opportunities if o["arms"][arm]["status"] == "EXECUTED"]
        metrics = {scenario: measures([o["path"]["net_r"][scenario] for o in selected]) for scenario in SCENARIOS}
        gross = measures([o["path"]["gross_r"] for o in selected])
        portfolios = {}
        for scenario in SCENARIOS:
            check_limits()
            portfolios[scenario] = portfolio(opportunities, arm, provider, scenario, check_limits=check_limits)
            progress("PORTFOLIO", arm*3+list(SCENARIOS).index(scenario)+1, 6, {"arm": card["candidate_id"], "scenario": scenario})
        counts = Counter(o["arms"][arm]["status"] for o in opportunities)
        output["arms"].append({"candidate_id": card["candidate_id"], "fingerprint": card["fingerprint"],
            "opportunities": len(opportunities), "executed": len(selected), "filtered": counts["FILTERED"], "skipped": counts["SKIPPED"],
            "skip_reasons": dict(Counter(o["arms"][arm]["reason"] for o in opportunities if o["arms"][arm]["status"] != "EXECUTED")),
            "gross_shadow": gross, "net": metrics,
            "net_r_per_original_opportunity": sum(o["net"] for o in selected)/len(opportunities) if opportunities else None,
            "portfolio": portfolios, "attribution": attribution(opportunities, arm),
            "gross_limit": "SHADOW_MIDPOINT_PATH_NOT_IDENTICAL_TIMES_WHEN_SIDE_STOP_DIFFERS",
            "evidence_status": "REUSED_DEVELOPMENT", "contamination_status": "USED"})
    return output


def _handoff_identity(cards, experiment_identity):
    """Return an explicit identity for a checked result without a PKT044 fallback."""
    if experiment_identity is None:
        return {
            "experiment_id": "PKT-FOREX-044", "run_id": "PKT044_FIRST_BATCH",
            "data_boundary": {"start": data.DEV_START.isoformat(), "end_exclusive": data.DEV_END.isoformat()},
            "baseline_candidate_id": ARM_IDS[0], "changed_variable": "regime_filters",
        }
    required = ("experiment_id", "run_id", "data_boundary", "baseline_candidate_id", "changed_variable")
    if not isinstance(experiment_identity, dict) or any(key not in experiment_identity for key in required):
        raise ValueError("CHECKED_HANDOFF_EXPLICIT_IDENTITY_INCOMPLETE")
    if experiment_identity["baseline_candidate_id"] != cards[0]["candidate_id"]:
        raise ValueError("CHECKED_HANDOFF_BASELINE_IDENTITY_MISMATCH")
    boundary = experiment_identity["data_boundary"]
    if not isinstance(boundary, dict) or not boundary.get("start") or not boundary.get("end_exclusive"):
        raise ValueError("CHECKED_HANDOFF_DATA_BOUNDARY_INVALID")
    return copy.deepcopy(experiment_identity)


def checked_handoff(result, cards, index, artifacts, *, experiment_identity=None):
    identity = _handoff_identity(cards, experiment_identity)
    records = []
    for arm, card in zip(result["arms"], cards):
        failed = []
        checks = {key: "NOT_EVALUATED" for key in handoff.PROMOTION_REQUIREMENTS}
        base, stress = arm["net"]["BASE"], arm["net"]["STRESSED"]
        checks["cost_stress"] = "PASS" if stress["expectancy"] is not None and stress["expectancy"] > 0 else "FAIL"
        checks["matched_baseline"] = result["matched"]["uncertainty"]["status"]
        checks["portfolio_risk"] = "PASS" if arm["portfolio"]["BASE"]["maximum_drawdown"] <= .1 else "FAIL"
        contributing = [x for x in arm["attribution"]["pair"].values() if x["sum_r"] > 0]
        checks["breadth"] = "PASS" if len(contributing) >= 2 else "FAIL"
        for key, state in checks.items():
            if state == "FAIL": failed.append(key)
        if base["expectancy"] is None or base["expectancy"] <= 0: failed.append("positive_net")
        if base["profit_factor"] is None or base["profit_factor"] < 1.1: failed.append("profit_factor_1_10")
        if arm["executed"] < 200: failed.append("sample_200")
        # Missing robustness/history inputs never acquire a fallback PASS.
        record = {key: None for key in validation.RESEARCH_OPTIONAL_FIELDS}
        record.update(schema=validation.RESEARCH_RECORD_SCHEMA, experiment_id=identity["experiment_id"], run_id=identity["run_id"],
            candidate_id=card["candidate_id"], specification=card["specification"], fingerprint=card["fingerprint"],
            data_boundary=identity["data_boundary"],
            evidence_status="REUSED_DEVELOPMENT", contamination_status="USED", validity="VALID",
            opportunities=arm["opportunities"], executed_trades=arm["executed"], filtered_trades=arm["filtered"], skipped_trades=arm["skipped"],
            skip_reasons=arm["skip_reasons"], sample_requirement=200, metrics={"unit": "R", "gross": arm["gross_shadow"]["expectancy"], "net": base["expectancy"]},
            failed_gates=failed, promotion_checks=checks, artifacts=artifacts, pair_attribution=arm["attribution"]["pair"],
            currency_attribution=arm["attribution"]["currency"], session_attribution=arm["attribution"]["session"],
            regime_attribution={k: arm["attribution"][k] for k in ("volatility", "spread")},
            uncertainty=result["matched"]["uncertainty"], baseline=identity["baseline_candidate_id"], changed_variable=identity["changed_variable"],
            risk_metrics={"unit": "USD", "maximum_drawdown": arm["portfolio"]["BASE"]["maximum_drawdown"]},
            missing_gates=[key for key, state in checks.items() if state == "NOT_EVALUATED"])
        validation.validate_research_record(record)
        records.append(record)
    review = handoff.review_batch(records, index)
    # No automatic parameter guess. A next question requiring a new precise
    # contract remains a proposal request, not a fabricated registered strategy.
    review["proposal_registration_count"] = 0
    review["proposal_limit_reason"] = "NEXT_QUESTION_REQUIRES_SEPARATE_EXACT_PREREGISTRATION;_NO_PARAMETER_SEARCH"
    return {"records": records, "review": review, "next_state": "AWAITING_APPROVAL", "budget_remaining": 0}


def invalid_handoff(cards, artifacts, error, *, experiment_identity=None):
    """Checked incomplete failure; unknown counts are not invented zeroes."""
    if experiment_identity is None:
        identity = {
            "experiment_id": "PKT-FOREX-044", "run_id": "PKT044_MEASUREMENT_AVAILABILITY_R1",
            "data_boundary": {"start": data.DEV_START.isoformat(), "end_exclusive": data.DEV_END.isoformat()},
            "baseline_candidate_id": ARM_IDS[0], "changed_variable": "regime_filters",
        }
    else:
        identity = _handoff_identity(cards, experiment_identity)
    records = []
    for card in cards:
        record = {key: None for key in validation.RESEARCH_OPTIONAL_FIELDS}
        record.update(schema=validation.RESEARCH_RECORD_SCHEMA, experiment_id=identity["experiment_id"],
            run_id=identity["run_id"], candidate_id=card["candidate_id"],
            specification=card["specification"], fingerprint=card["fingerprint"],
            data_boundary=identity["data_boundary"],
            evidence_status="REUSED_DEVELOPMENT", contamination_status="USED", validity="INVALID",
            opportunities=None, executed_trades=None, sample_requirement=200,
            metrics={"unit": "R", "gross": None, "net": None}, failed_gates=[str(error)], artifacts=artifacts,
            failure_details=getattr(error, "details", {}))
        validation.validate_research_record(record)
        records.append(record)
    return records
