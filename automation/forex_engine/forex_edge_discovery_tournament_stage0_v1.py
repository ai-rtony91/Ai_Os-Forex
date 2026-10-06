"""Deterministic, metadata-only Forex edge tournament preregistration.

PKT-FOREX-038 never opens market-price outcome rows.  It preserves prior
research memory, records information contamination, freezes a bounded
four-arm development experiment, and exposes small synthetic-only helpers for
causality, graph, partition, and pullback-state-machine regression tests.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from automation.forex_engine import forex_high_throughput_edge_factory_v1 as prior


PACKET_ID = "PKT-FOREX-038"
IDENTITY_MARKER = "PKT_FOREX_038_EDGE_DISCOVERY_TOURNAMENT_STAGE0"
WORKER_ID = "EAST_OCC_73"
CURRENT_ATTEMPT_LOWER_BOUND = 1220
PRIOR_PROPOSED_UNSCORED = 446
NEW_FIRST_WAVE_CELLS = 72
M5_DEVELOPMENT = ("2024-01-01T00:00:00Z", "2025-04-01T00:00:00Z")
M5_VALIDATION = ("2025-04-01T00:00:00Z", "2026-01-01T00:00:00Z")
M5_RESERVED_2026 = ("2026-01-01T00:00:00Z", "2026-08-29T03:50:00Z")
PRIOR_COMPLETION = ".aios/staging/PKT_FOREX_037/PKT_FOREX_037_COMPLETION.json"
PRIOR_COMPLETION_SHA256 = "642e779d61e7820fec0b3aa4222db2ebb553ea99c7fb5eaf6587549a812efc70"
PRIOR_SOURCE_HASHES = {
    "automation/forex_engine/forex_high_throughput_edge_factory_v1.py": "57a243303d7f5c02ec2254f9a1b3bed0834b936ba93246c413e7d4c8cca55ba5",
    "automation/orchestration/work_packets/active/PKT-FOREX-037.md": "d0d6050627f322f738150f9767b62abc57d17a79ba6ae5640ce5d3d633ab70d1",
    "scripts/forex_delivery/run_forex_high_throughput_edge_factory_v1.py": "27fedbd5ced756261c8d752b5bba19b01a3ec31b1141326bed67e18fe23f6abe",
    "tests/forex_engine/test_forex_high_throughput_edge_factory_v1.py": "1aec6fbb5bf4ae2ee1cbb412010fc9cacbe94e0412d7aa2cbc0f66b68756b7bb",
}
PROVENANCE_INPUT_HASHES = {
    ".aios/runtime/forex_final_holdout_access_guard_v1.json": "cdabbfb16b75e6f31c8eff2d84f29c3171fc95fcd90e4bab51b90b4991bf19a1",
    ".aios/runtime/forex_feature_edge_research_v2/feature_protocol.json": "f6c98840e08b790055dc4730e12f366abeaed0d4d80ae0f4ce3c5a3a658bd183",
    ".aios/runtime/forex_feature_edge_research_v2/currency_factor_table.json": "8797751e2137fd080516885f448cbfc35bafc43a2011e08c47efafe7332d1d26",
    "Reports/forex_delivery/AIOS_FOREX_FEATURE_EDGE_RESEARCH_V2_STATE.json": "7a1ff224024ea29da816b5c83393ea16f2a4be4420a602bb16444ec60b204744",
    "Reports/forex_delivery/AIOS_FOREX_EDGE_RESEARCH_V1_STATE.json": "47b9fde5aea4b33c0edd63715f7917f67a728428cc4478e544f87b2002c55b11",
    "automation/forex_engine/forex_feature_edge_research_v2.py": "2c5439a29dcfb16075c5bb4f4533b0b08d9cdf4bf926ceaa20134cf8020e2a1f",
}
# Historical identities above describe PKT037/038, not mutable current code.
# These replacements were reviewed and recorded in the PKT044 launch checkpoint
# before this compatibility amendment. Unknown versions remain blocked.
REVIEWED_PKT044_SOURCE_HASHES = {
    "automation/forex_engine/forex_high_throughput_edge_factory_v1.py": "11a66f2a3512b38ab3095aa25b46ba9fe5cc53155fd4fcd9411eedcebc85065c",
    "scripts/forex_delivery/run_forex_high_throughput_edge_factory_v1.py": "5b990ac835d4271070bd768805b9f5a9ea848fa3c4fefddb4305e6ba9b0d9b19",
    "tests/forex_engine/test_forex_high_throughput_edge_factory_v1.py": "e9fff7bcce332f3f0acc573df26b66747b54fa6b7ab444db286a1ba8feb4a63a",
}
ACCESS_CHECKPOINT = ".aios/staging/PKT_FOREX_044/amendment_occ82_20260907/launch_blocker_checkpoint.json"
METADATA_PROVENANCE_HASHES = {
    ".aios/runtime/forex_final_holdout_access_guard_v1.json": PROVENANCE_INPUT_HASHES[".aios/runtime/forex_final_holdout_access_guard_v1.json"],
    ACCESS_CHECKPOINT: "1c0d1b453f73ab89db8896008d82e86155e75a04d1c56c86427745cb304f01f5",
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def assert_metadata_only_paths(paths: Iterable[str]) -> None:
    forbidden_tokens = ("/partitions/", "/events/", ".jsonl", ".csv", ".parquet", ".feather")
    forbidden_names = {"currency_factor_table.json", "opportunity_surface.json", "aios_forex_edge_research_v1_state.json", "aios_forex_feature_edge_research_v2_state.json"}
    for raw in paths:
        normalized = raw.replace("\\", "/").lower()
        if Path(normalized).name in forbidden_names or any(token in normalized for token in forbidden_tokens):
            raise PermissionError(f"FORBIDDEN_OUTCOME_FILE_ACCESS:{raw}")


def validate_half_open_event(
    partition: Sequence[str], *, feature_times: Sequence[str], signal_time: str,
    entry_time: str, exit_time: str, label_end_time: str, context_close_time: str,
) -> bool:
    if len(partition) != 2:
        raise ValueError("PARTITION_MUST_HAVE_TWO_BOUNDARIES")
    start, end = map(parse_utc, partition)
    ordered = [*map(parse_utc, feature_times), parse_utc(signal_time), parse_utc(entry_time), parse_utc(exit_time), parse_utc(label_end_time)]
    if not start < end or any(not (start <= stamp < end) for stamp in ordered):
        raise ValueError("PARTITION_BOUNDARY_CROSSING")
    if parse_utc(context_close_time) > parse_utc(signal_time):
        raise ValueError("HIGHER_TIMEFRAME_NOT_COMPLETED")
    return True


def normalized_momentum(closes: Sequence[float | None], t: int, lookback: int, sigma_window: int = 288) -> float:
    if lookback <= 0 or sigma_window < 2 or t < max(lookback, sigma_window) or t >= len(closes):
        raise ValueError("INSUFFICIENT_MOMENTUM_WARMUP")
    required = closes[t - sigma_window : t + 1]
    if any(value is None or not math.isfinite(float(value)) or float(value) <= 0 for value in required):
        raise ValueError("MISSING_OR_INVALID_CLOSE")
    returns = [math.log(float(closes[index]) / float(closes[index - 1])) for index in range(t - sigma_window + 1, t + 1)]
    sigma = statistics.stdev(returns)
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("ZERO_OR_INVALID_VOLATILITY")
    return math.log(float(closes[t]) / float(closes[t - lookback])) / (sigma * math.sqrt(lookback))


def _solve_linear(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    augmented = [list(matrix[row]) + [vector[row]] for row in range(n)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("CURRENCY_GRAPH_RANK_DEFICIENT")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(n):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [left - factor * right for left, right in zip(augmented[row], augmented[column])]
    return [augmented[row][-1] for row in range(n)]


def fit_currency_strength(observations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not observations:
        raise ValueError("EMPTY_CURRENCY_GRAPH")
    timestamps = {row.get("timestamp") for row in observations}
    if None in timestamps or len(timestamps) != 1:
        raise ValueError("UNSYNCHRONIZED_CURRENCY_GRAPH")
    lineages: set[str] = set()
    undirected: set[tuple[str, str]] = set()
    currencies: set[str] = set()
    parsed = []
    for row in observations:
        pair = str(row.get("pair", ""))
        parts = pair.split("_")
        if len(parts) != 2 or parts[0] == parts[1] or row.get("native") is not True:
            raise ValueError("INVALID_OR_SYNTHETIC_GRAPH_OBSERVATION")
        lineage = str(row.get("lineage", ""))
        if not lineage or lineage in lineages:
            raise ValueError("DUPLICATE_SYNTHETIC_LINEAGE")
        lineages.add(lineage)
        edge = tuple(sorted(parts))
        if edge in undirected:
            raise ValueError("DUPLICATE_PAIR_ORIENTATION")
        undirected.add(edge)
        value = float(row.get("log_return"))
        if not math.isfinite(value):
            raise ValueError("MISSING_GRAPH_RETURN")
        currencies.update(parts)
        parsed.append((parts[0], parts[1], value))
    adjacency = {currency: set() for currency in currencies}
    for base, quote, _ in parsed:
        adjacency[base].add(quote)
        adjacency[quote].add(base)
    visited = set()
    stack = [min(currencies)]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(sorted(adjacency[node] - visited))
    if visited != currencies:
        raise ValueError("DISCONNECTED_CURRENCY_GRAPH")
    ordered = sorted(currencies)
    reference = ordered[-1]
    variables = ordered[:-1]
    index = {currency: slot for slot, currency in enumerate(variables)}
    normal = [[0.0 for _ in variables] for _ in variables]
    rhs = [0.0 for _ in variables]
    for base, quote, value in parsed:
        row = [0.0 for _ in variables]
        if base != reference:
            row[index[base]] += 1.0
        if quote != reference:
            row[index[quote]] -= 1.0
        for i, left in enumerate(row):
            rhs[i] += left * value
            for j, right in enumerate(row):
                normal[i][j] += left * right
    fitted = _solve_linear(normal, rhs)
    raw = {reference: 0.0, **{currency: fitted[index[currency]] for currency in variables}}
    mean = sum(raw.values()) / len(raw)
    strengths = {currency: raw[currency] - mean for currency in ordered}
    residuals = [value - (strengths[base] - strengths[quote]) for base, quote, value in parsed]
    return {
        "strengths": strengths,
        "currency_count": len(ordered),
        "edge_count": len(parsed),
        "maximum_independent_currency_coordinates": len(ordered) - 1,
        "sum_constraint": sum(strengths.values()),
        "residual_sum_squares": sum(value * value for value in residuals),
        "normalization": "FIT_RAW_LOG_RETURNS_THEN_NORMALIZE",
    }


def leave_target_pair_out(observations: Sequence[dict[str, Any]], target_pair: str) -> dict[str, Any]:
    remaining = [row for row in observations if row["pair"] != target_pair]
    result = fit_currency_strength(remaining)
    result["diagnostic"] = "LEAVE_TARGET_PAIR_OUT_NOT_PROOF_OF_INDEPENDENCE_TRIANGULATION_CAN_RECONSTRUCT"
    result["target_pair"] = target_pair
    return result


def pullback_state_machine(
    closes: Sequence[float | None], *, pair: str, direction: str, impulse_index: int,
    lookback: int, max_wait: int = 12,
) -> dict[str, Any]:
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("INVALID_DIRECTION")
    if impulse_index < max(lookback, 2) or impulse_index >= len(closes):
        raise ValueError("INVALID_IMPULSE_INDEX")
    if any(value is None or not math.isfinite(float(value)) for value in closes[impulse_index - lookback : impulse_index + 1]):
        raise ValueError("MISSING_EVENT_DATA")
    anchor = float(closes[impulse_index - lookback])
    endpoint = float(closes[impulse_index])
    signed_size = (endpoint - anchor) if direction == "LONG" else (anchor - endpoint)
    if signed_size <= 0:
        raise ValueError("NONPOSITIVE_IMPULSE_SIZE")
    event_id = sha256_bytes(canonical_bytes({"pair": pair, "direction": direction, "impulse_index": impulse_index, "lookback": lookback, "anchor": anchor, "endpoint": endpoint}))
    states = ["IDLE", "IMPULSE_IDENTIFIED"]
    qualified = False
    last = min(len(closes) - 1, impulse_index + max_wait)
    for index in range(impulse_index + 1, last + 1):
        value = closes[index]
        if value is None or not math.isfinite(float(value)):
            states.append("DATA_BLOCKED")
            return {"event_id": event_id, "terminal_state": "DATA_BLOCKED", "states": states, "anchor": anchor, "endpoint": endpoint}
        close = float(value)
        retracement = ((endpoint - close) if direction == "LONG" else (close - endpoint)) / signed_size
        if retracement > 0.60:
            states.append("INVALIDATED")
            return {"event_id": event_id, "terminal_state": "INVALIDATED", "states": states, "anchor": anchor, "endpoint": endpoint, "terminal_index": index}
        if not qualified and 0.20 <= retracement <= 0.60:
            qualified = True
            states.append("PULLBACK_QUALIFIED")
        if qualified and index >= impulse_index + 2:
            previous = float(closes[index - 1])
            previous_two = float(closes[index - 2])
            resumed = close > max(previous, previous_two) if direction == "LONG" else close < min(previous, previous_two)
            if resumed:
                states.extend(["RESUMPTION_CONFIRMED", "ENTRY_ELIGIBLE"])
                if index + 1 >= len(closes) or closes[index + 1] is None:
                    states[-1] = "DATA_BLOCKED"
                    return {"event_id": event_id, "terminal_state": "DATA_BLOCKED", "states": states, "anchor": anchor, "endpoint": endpoint}
                return {"event_id": event_id, "terminal_state": "ENTRY_ELIGIBLE", "states": states, "anchor": anchor, "endpoint": endpoint, "trigger_index": index, "entry_index": index + 1}
    states.append("EXPIRED")
    return {"event_id": event_id, "terminal_state": "EXPIRED", "states": states, "anchor": anchor, "endpoint": endpoint, "terminal_index": last}


def reject_duplicate_event_ids(event_ids: Sequence[str]) -> bool:
    if len(set(event_ids)) != len(event_ids):
        raise ValueError("DUPLICATE_EVENT_ID")
    return True


def source_experiment_map() -> dict[str, Any]:
    rows = [
        {
            "source_id": "BIS_WORK366_CURRENCY_MOMENTUM", "title": "Currency Momentum Strategies",
            "url": "https://www.bis.org/publ/work366.pdf", "author_or_organization": "Menkhoff; Sarno; Schmeling; Schrimpf / BIS", "publication_date": "2011-12-13",
            "published_finding": "Winner-minus-loser currency portfolios were studied across up to 48 currencies; formation and holding periods were 1, 3, 6, 9, or 12 months and bid-ask costs were analyzed.",
            "instrument_universe": "Up to 48 currencies against USD", "sampling_frequency": "MONTHLY", "formation_horizon": "1/3/6/9/12_MONTHS", "holding_horizon": "1/3/6/9/12_MONTHS", "execution_assumptions": "MONTHLY_EXCESS_RETURNS_AND_BID_ASK_ADJUSTMENT",
            "aios_adaptation": "Test whether M5-derived currency-graph strength predicts later intraday returns.", "untested_design_choices": ["M5 normalization", "quartile selection", "12/48/288-bar formation", "3/12/48-bar holding"],
            "limitations": ["Published monthly result does not establish an intraday edge", "AIOS sample is shorter", "pair graph is not the paper's USD-only portfolio construction"], "evidence_role": "HYPOTHESIS_ONLY",
        },
        {
            "source_id": "STLFED_WP_1999_016_INTRADAY", "title": "Intraday Technical Trading in the Foreign Exchange Market",
            "url": "https://files.stlouisfed.org/files/htdocs/wp/1999/99-016.pdf", "author_or_organization": "Christopher J. Neely; Paul A. Weller / Federal Reserve Bank of St. Louis", "publication_date": "2001-01-10",
            "published_finding": "Stable intraday predictability did not yield positive excess returns after realistic costs and active trading-hour restrictions.",
            "instrument_universe": "USD/DEM, USD/JPY, USD/GBP, USD/CHF", "sampling_frequency": "30_MINUTE_PRIMARY_WITH_INTRADAY_QUOTE_ANALYSIS", "formation_horizon": "OPTIMIZED_RULE_DEPENDENT", "holding_horizon": "RULE_DEPENDENT", "execution_assumptions": "ONE_WAY_COST_STATES_AND_RESTRICTED_TRADING_HOURS",
            "aios_adaptation": "Require conditional forward movement to exceed side-correct executable costs before strategy promotion.", "untested_design_choices": ["AIOS cost stress magnitudes", "M5 entry delay"],
            "limitations": ["Historical market structure", "Different instruments and sampling", "Predictability is not profitability"], "evidence_role": "NEGATIVE_COST_CONTROL",
        },
        {
            "source_id": "NYFED_SR150_STOP_CASCADES", "title": "Stop-Loss Orders and Price Cascades in Currency Markets",
            "url": "https://www.newyorkfed.org/research/staff_reports/sr150.html", "author_or_organization": "Carol L. Osler / Federal Reserve Bank of New York", "publication_date": "2002-07",
            "published_finding": "Minute quotes for dollar-mark, dollar-yen, and dollar-pound showed unusually rapid moves around documented round-number stop clusters; effects were reported for hours, not days.",
            "instrument_universe": "USD/DEM, USD/JPY, USD/GBP; separate bank order sample also included EUR/USD", "sampling_frequency": "MINUTE_QUOTES_AND_DEALER_ORDER_RECORDS", "formation_horizon": "ROUND_LEVEL_CROSS_EVENT", "holding_horizon": "INTRADAY_HOURS", "execution_assumptions": "NOT_AN_EXECUTABLE_COSTED_STRATEGY",
            "aios_adaptation": "Retain round-number states as a challenger subject to matched arbitrary-level and cost controls.", "untested_design_choices": ["00/50 M5 translation", "approach and failed-reclaim state machine"],
            "limitations": ["Dated small instrument sample", "Private order data unavailable", "Round-number behavior does not prove current after-cost tradability"], "evidence_role": "MECHANISM_SUPPORT_ONLY",
        },
        {
            "source_id": "BAILEY_LOPEZ_DE_PRADO_DSR", "title": "The Deflated Sharpe Ratio",
            "url": "https://doi.org/10.2139/ssrn.2460551", "author_or_organization": "David H. Bailey; Marcos Lopez de Prado", "publication_date": "2014-07-31",
            "published_finding": "DSR adjusts Sharpe evidence for selection bias under multiple testing and non-normal returns.",
            "instrument_universe": "GENERAL", "sampling_frequency": "GENERAL", "formation_horizon": "NOT_APPLICABLE", "holding_horizon": "NOT_APPLICABLE", "execution_assumptions": "STATISTICAL_METHOD_NOT_TRADING_RULE",
            "aios_adaptation": "Use complete trial history plus realized return moments and trial dependence before promotion.", "untested_design_choices": ["Effective independent trial estimate for AIOS namespaces"],
            "limitations": ["Not a profitability certificate", "Cannot be computed from trial count alone", "Requires reconciled performance inputs"], "evidence_role": "SELECTION_BIAS_CONTROL",
        },
        {
            "source_id": "OANDA_V20_CANDLE_DEFINITIONS", "title": "Instrument Definitions",
            "url": "https://developer.oanda.com/rest-live-v20/instrument-df/", "author_or_organization": "OANDA Developer Documentation", "publication_date": "UNKNOWN",
            "published_finding": "Candles may expose bid, ask, and midpoint OHLC separately; volume is the number of prices created and complete marks a finished candle.",
            "instrument_universe": "OANDA_INSTRUMENTS", "sampling_frequency": "S5_THROUGH_MONTHLY_AS_DOCUMENTED", "formation_horizon": "NOT_APPLICABLE", "holding_horizon": "NOT_APPLICABLE", "execution_assumptions": "DATA_SCHEMA_ONLY",
            "aios_adaptation": "Use midpoint only for features and side-correct bid/ask for historical fill approximations; never call price-count volume centralized order flow.", "untested_design_choices": ["Modeled slippage", "entry-delay stress"],
            "limitations": ["Historical candle opens are not guaranteed live fills", "Candle data are not tick-by-tick execution evidence"], "evidence_role": "DATA_SEMANTICS",
        },
    ]
    return {"schema": "AIOS_FOREX_SOURCE_TO_EXPERIMENT_MAP.v1", "separation_rule": "PUBLISHED_FINDING_NE_AIOS_ADAPTATION_NE_UNTESTED_DESIGN_CHOICE", "sources": rows}


def edge_cards() -> list[dict[str, Any]]:
    definitions = [
        (1, "CROSS_SECTIONAL_CURRENCY_MOMENTUM", "Broad strong currencies continue to outperform broad weak currencies", "CURRENCY_GRAPH_STRENGTH", "FULL_58_PAIR_M5_GRAPH", "PRIMARY_FIRST_WAVE"),
        (2, "FACTOR_COMMON_COMPONENT_MOMENTUM", "Common currency components persist more than pair residuals", "GRAPH_COMPONENT_AND_RESIDUAL", "58_PAIR_M5_WITH_H1_CONTEXT", "CATALOG_ONLY_PENDING_SIMPLE_ARM_RESULT"),
        (3, "CONDITIONAL_TIME_SERIES_MOMENTUM", "Large volatility-normalized displacement continues in suitable states", "NORMALIZED_PAIR_MOMENTUM", "58_PAIR_M5", "PRIMARY_FIRST_WAVE_ARM_A"),
        (4, "MOMENTUM_PULLBACK_CONTINUATION", "A controlled retracement improves entry location without breaking the impulse", "FROZEN_IMPULSE_PULLBACK_RESUMPTION", "58_PAIR_M5", "PRIMARY_FIRST_WAVE_ARMS_C_D"),
        (5, "CROSS_SECTIONAL_DISPERSION_REGIME", "Momentum strength changes with causal cross-sectional dispersion", "MOMENTUM_X_DISPERSION", "58_PAIR_SYNCHRONIZED_M5", "DIAGNOSTIC_ONLY_NO_FILTER_SELECTION"),
        (6, "VOLATILITY_AND_LIQUIDITY_REGIME", "Execution state determines whether gross effects survive costs", "CAUSAL_VOLATILITY_AND_SPREAD_R", "58_PAIR_M5", "DIAGNOSTIC_ONLY_NO_FILTER_SELECTION"),
        (7, "VOLATILITY_EXPANSION_BREAKOUT", "Compression can precede directional range expansion", "NORMALIZED_COMPRESSION_BREAK", "58_PAIR_M5_H1", "CHALLENGER_PRIOR_REJECTION_COLLISION"),
        (8, "CONDITIONAL_MEAN_REVERSION", "Extreme normalized displacement can reverse in bounded regimes", "NORMALIZED_EXTREME_REVERSAL", "58_PAIR_M5", "CHALLENGER_PRIOR_REJECTION_COLLISION"),
        (9, "CARRY_CONDITIONED_MOMENTUM", "Rate differential may condition rather than create momentum", "MOMENTUM_X_POINT_IN_TIME_CARRY", "POINT_IN_TIME_RATE_ELIGIBLE_SUBSET", "CATALOG_ONLY_FINANCING_LIMIT"),
        (10, "ROUND_NUMBER_CONDITIONAL_ORDER_STATE", "Order clustering can cause rejection or post-cross cascades", "ROUND_LEVEL_STATE", "58_PAIR_M5", "CHALLENGER_135_PRIOR_PROPOSALS_UNSCORED"),
    ]
    cards = []
    for rank, edge_id, rationale, signal, universe, disposition in definitions:
        card = {
            "EDGE_ID": edge_id, "PRIORITY": rank, "HYPOTHESIS": rationale,
            "ECONOMIC_OR_BEHAVIORAL_RATIONALE": rationale, "PRIMARY_SIGNAL": signal,
            "REGIME_CONDITIONS": "UNGATED_PRIMARY_WITH_SESSION_VOLATILITY_LIQUIDITY_DISPERSION_DIAGNOSTICS",
            "EXPECTED_HOLDING_HORIZON": "3_12_48_COMPLETED_M5_INTERVALS_FOR_FIRST_WAVE" if rank in {1, 3, 4} else "MUST_BE_SEPARATELY_PREREGISTERED",
            "EXPECTED_FAILURE_REGIMES": ["HIGH_COST", "SHOCK", "PAIR_OR_CURRENCY_CONCENTRATION"],
            "PAIR_UNIVERSE": universe, "TIMEFRAME": "M5_SIGNAL_AND_EXECUTION_H1_CONTEXT_ONLY_WHEN_CAUSAL",
            "ENTRY_MECHANISM": "FIRST_EXECUTABLE_SIDE_CORRECT_PRICE_AFTER_COMPLETED_SIGNAL",
            "INVALIDATION_MECHANISM": "MECHANISM_SPECIFIC_FROZEN_STATE_FAILURE_OR_DATA_COST_BLOCK",
            "EXIT_FAMILY": "EFFECT_SCREEN_FIRST;_2R_AND_3R_ONLY_AFTER_MECHANISM_SURVIVES",
            "COST_MODEL": "OBSERVED_BID_ASK_PLUS_PREREGISTERED_SLIPPAGE_STRESS_NO_DOUBLE_SPREAD",
            "PORTFOLIO_EXPOSURE_MODEL": "CURRENCY_LEVEL_GROSS_NET_AND_MAX_FIVE_DISJOINT_PAIRS",
            "PARAMETER_FAMILY": "BOUNDED_PRE_REGISTERED_ONLY", "PRE_REGISTERED_VARIANTS": disposition,
            "TRIAL_COUNT_INCREMENT_RULE": "INCREMENT_ONCE_PER_CELL_WHEN_ANY_REAL_OUTCOME_IS_EXAMINED",
            "FALSIFICATION_CRITERIA": ["NO_DIRECTIONAL_EFFECT", "NO_INCREMENT_OVER_SIMPLE_BASELINE", "COST_DESTROYED", "CONCENTRATED", "CAUSALITY_FAILURE"],
            "PROMOTION_CRITERIA": "STRICT_REPOSITORY_CHARTER_PLUS_GLOBAL_SELECTION_BIAS_AND_DETERMINISTIC_REPRODUCTION",
        }
        card["EDGE_FINGERPRINT"] = sha256_bytes(canonical_bytes(card))
        cards.append(card)
    return cards


def first_wave_manifest() -> dict[str, Any]:
    arms = {
        "A": "NORMALIZED_PAIR_MOMENTUM_IMMEDIATE_NEXT_BAR",
        "B": "ARM_A_PLUS_STRONG_BASE_WEAK_QUOTE_GRAPH_SELECTION",
        "C": "ARM_A_PLUS_PULLBACK_AND_RESUMPTION",
        "D": "ARM_A_PLUS_GRAPH_SELECTION_PLUS_PULLBACK_AND_RESUMPTION",
    }
    cells = []
    for arm in arms:
        for lookback in (12, 48, 288):
            for horizon in (3, 12, 48):
                for direction in ("ECONOMIC_DIRECTION", "EXACT_INVERSE_DIAGNOSTIC"):
                    spec = {"arm": arm, "rule_structure": arms[arm], "formation_lookback_m5": lookback, "forward_horizon_m5": horizon, "direction": direction, "status": "PROPOSED_UNSCORED"}
                    spec["cell_id"] = f"FXT-{arm}-L{lookback}-H{horizon}-{'ORIG' if direction == 'ECONOMIC_DIRECTION' else 'INV'}"
                    spec["candidate_fingerprint"] = sha256_bytes(canonical_bytes(spec))
                    cells.append(spec)
    if len(cells) != NEW_FIRST_WAVE_CELLS or len({row["candidate_fingerprint"] for row in cells}) != NEW_FIRST_WAVE_CELLS:
        raise ValueError("FIRST_WAVE_CELL_GRID_INVALID")
    return {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_FIRST_WAVE.v1", "packet_id": PACKET_ID,
        "research_question": "DO_GRAPH_SELECTION_AND_OR_PULLBACK_ADD_FUTURE_AFTER_COST_INFORMATION_BEYOND_SIMPLE_NORMALIZED_PAIR_MOMENTUM",
        "arms_are_independent_edges": False, "cells": cells, "primary_cell_count": 36, "inverse_diagnostic_cell_count": 36, "maximum_cells": 72,
        "skip_rule": "DUPLICATE_OR_UNSUPPORTED_CELLS_ARE_NOT_SCORED_AND_ARE_NOT_REFILLED",
        "population_rule": "ALL_ORIGINALLY_ELIGIBLE_IMPULSES_REMAIN_IN_DENOMINATOR_INCLUDING_MISSED_RUNNERS_EXPIRED_AND_UNFILLED_EVENTS",
        "shared_inputs": {"completed_candles": True, "sigma_previous_returns": 288, "momentum_threshold_absolute": 1.0, "breakout_preceding_completed_closes": 12, "graph_quartiles": "TOP_BASE_BOTTOM_QUOTE_LONG_MIRRORED_SHORT", "ties": "CURRENCY_CODE_ASCENDING_AFTER_STRENGTH", "minimum_graph": "CONNECTED_STABLE_MEMBERSHIP_WITH_AT_LEAST_6_CURRENCIES"},
        "pullback": {"wait_m5_bars": 12, "retracement_fraction": [0.20, 0.60], "resumption": "FIRST_COMPLETED_CLOSE_BEYOND_PREVIOUS_TWO_COMPLETED_CLOSES", "new_impulse_high_before_qualification": "IGNORE_EXTENSION_KEEP_FROZEN_ANCHOR_AND_ENDPOINT", "rearm": "AFTER_EVENT_TERMINAL_STATE_AND_12_BAR_PAIR_DIRECTION_COOLDOWN"},
        "inverse_rule": "SAME_OPPORTUNITIES_TIMESTAMPS_HOLDS_EXITS_AND_FOLDS_WITH_OPPOSITE_SIDE_AND_INDEPENDENT_SIDE_CORRECT_COSTS_NOT_NEGATED_NET_PNL",
        "partitions": {"development": list(M5_DEVELOPMENT), "validation": list(M5_VALIDATION), "reserved_2026": list(M5_RESERVED_2026), "interval_semantics": "HALF_OPEN"},
        "new_outcome_scored_trials": 0,
    }


def graph_contract() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_CURRENCY_GRAPH_CONTRACT.v1", "equation": "s=argmin||r-Bs||^2 subject_to_sum_s_zero",
        "incidence_orientation": "PLUS_ONE_BASE_MINUS_ONE_QUOTE", "input": "SYNCHRONIZED_NATIVE_RAW_LOG_RETURNS",
        "normalization_order": "FIT_RAW_LOG_RETURNS_THEN_NORMALIZE_STRENGTHS", "maximum_independent_coordinates": "C_MINUS_ONE_FOR_CONNECTED_C_CURRENCY_GRAPH",
        "requirements": ["CONNECTEDNESS", "SYNCHRONIZED_TIMESTAMPS", "STABLE_MEMBERSHIP", "DETERMINISTIC_ORIENTATION", "EXPLICIT_MISSING_DATA_POLICY", "UNIQUE_NATIVE_LINEAGE"],
        "missing_data_policy": "DROP_WHOLE_SYNCHRONIZED_TIMESTAMP_BEFORE_RANKING_IF_FROZEN_MEMBERSHIP_IS_INCOMPLETE_OR_DISCONNECTED",
        "synthetic_rule": "SYNTHETIC_OR_DERIVED_COPIES_NEVER_ADD_INDEPENDENT_INPUTS_AND_SYNTHETIC_OHLC_EXTREMA_ARE_NOT_EXECUTABLE",
        "prediction_gate": "GRAPH_RECONSTRUCTION_IS_NOT_PREDICTION;_B_OR_D_MUST_BEAT_MATCHED_A_OR_C_ON_FUTURE_AFTER_COST_OUTCOMES",
        "leave_target_pair_out": "DIAGNOSTIC_WHERE_GRAPH_REMAINS_CONNECTED;_TRIANGULATION_CAN_STILL_RECONSTRUCT_TARGET_SO_NOT_PROOF_OF_INDEPENDENCE",
    }


def cost_exposure_contract() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_COST_AND_EXPOSURE_CONTRACT.v1",
        "fills": {"LONG": "ASK_ENTRY_TO_BID_EXIT", "SHORT": "BID_ENTRY_TO_ASK_EXIT", "spread": "EMBEDDED_ONCE_IN_SIDE_CORRECT_FILLS_NEVER_SUBTRACTED_AGAIN"},
        "cost_states": {
            "BASE": {"spread": "OBSERVED_BID_ASK", "adverse_slippage_pips_per_side": 0.10, "status": "EXISTING_VERIFIED_SETTING"},
            "STRESSED": {"spread": "OBSERVED_BID_ASK", "adverse_slippage_pips_per_side": 0.50, "status": "EXISTING_VERIFIED_SETTING"},
            "SEVERE_BUT_PLAUSIBLE": {"spread": "OBSERVED_BID_ASK", "adverse_slippage_pips_per_side": 1.00, "status": "FROZEN_RESEARCH_ASSUMPTION_NOT_ESTIMATED_FROM_STAGE0_OUTCOMES"},
        },
        "delay_states": ["NEXT_M5_OPEN_APPROXIMATION", "PLUS_ONE_M5_BAR_STRESS", "FINALIST_ONLY_CERTIFIED_FINE_CANDLE_SENSITIVITY"],
        "financing": "MISSING_IS_NOT_ZERO;_FIRST_WAVE_MAX_4_HOURS_AND_BLOCK_ANY_EVENT_CROSSING_UNSUPPORTED_FINANCING_OR_MARKET_CLOSURE_BOUNDARY",
        "effect_screen_units": "FORWARD_LOG_RETURN_AND_BREAK_EVEN_COST_NO_R_BEFORE_STOP_EXISTS",
        "risk_translation": {"risk_fraction_per_position": 0.0025, "maximum_simultaneous_pairs": 5, "shared_currency_pairs": "DISALLOWED_UNLESS_PORTFOLIO_SOLVER_PROVES_CAP", "sizing_changes_to_PASS_drawdown": "FORBIDDEN"},
        "required_portfolio_reports": ["currency_gross_exposure", "currency_net_exposure", "pair_correlation", "signal_correlation", "largest_pair_contribution", "largest_currency_factor_contribution", "effective_independent_bets", "simultaneous_correlated_positions", "portfolio_pnl"],
    }


def entry_exit_contract() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_LATER_TRADE_TRANSLATION_CONTRACT.v1", "launch_authorized": False,
        "entry": "FIRST_SIDE_CORRECT_EXECUTABLE_PRICE_AFTER_COMPLETED_TRIGGER_WITH_NEXT_M5_OPEN_ONLY_A_HISTORICAL_APPROXIMATION",
        "initial_stop": "BEYOND_OBSERVED_PULLBACK_EXTREME_PLUS_ONE_INSTRUMENT_PIP_FROZEN_RESEARCH_BUFFER_IF_NO_STRONGER_CANONICAL_CONVENTION_IS_FOUND",
        "targets": ["2R_SEPARATELY_COUNTED", "3R_SEPARATELY_COUNTED"], "time_exit": "MATCHED_3_12_OR_48_M5_HORIZON_AND_BEFORE_UNSUPPORTED_FINANCING_OR_MARKET_CLOSURE",
        "gap_handling": "FILL_AT_FIRST_AVAILABLE_ADVERSE_SIDE_CORRECT_PRICE", "same_candle_stop_and_target": "CONSERVATIVE_STOP_FIRST_WHEN_ORDERING_UNKNOWN",
        "rounding": "ROUND_OUTWARD_TO_INSTRUMENT_DISPLAY_PRECISION_WITHOUT_REDUCING_DECLARED_RISK", "cancellation": "CANCEL_ON_EVENT_EXPIRY_INVALIDATION_DATA_BLOCK_OR_COST_BLOCK",
        "forbidden_initial_features": ["PARTIAL_PROFITS", "BREAK_EVEN_MOVE", "DISCRETIONARY_TRAIL", "ADAPTIVE_TARGET", "MARTINGALE", "AVERAGING_DOWN", "REINFORCEMENT_LEARNING"],
        "net_expectancy_r": "MEAN_NET_PNL_DIVIDED_BY_FROZEN_INITIAL_RISK_UNDER_DECLARED_FILL_AND_STOP_CONVENTION",
    }


def statistical_contract() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_STATISTICAL_CONTRACT.v1",
        "primary_outcomes": ["mean_forward_return", "median_forward_return", "hit_rate", "standardized_effect_size", "95pct_synchronized_block_bootstrap_interval", "sample_count", "pair_breadth", "currency_breadth", "regime_breadth"],
        "baselines": ["NO_TRADE_ZERO", "MATCHED_RANDOM_DIRECTION", "ARM_A_SIMPLE_PAIR_MOMENTUM", "UNFILTERED_MATCHED_ARM"],
        "stage1_mechanism_observed": "PREDECLARED_DIRECTION_AND_BLOCK_BOOTSTRAP_INTERVAL_EXCLUDES_ZERO_WITH_AT_LEAST_200_EVENTS_8_PAIRS_6_CURRENCIES_AND_30_EFFECTIVE_SYNCHRONIZED_BLOCKS",
        "incremental_gate": "B_BEATS_A_C_BEATS_A_AND_D_BEATS_B_AND_C_ON_MATCHED_ORIGINALLY_ELIGIBLE_IMPULSE_POPULATION_WITH_ECONOMICALLY_MEANINGFUL_BREAK_EVEN_COST",
        "resampling": "SYNCHRONIZED_MARKET_WIDE_288_M5_BAR_BLOCKS;_OVERLAPPING_LABELS_CLUSTERED_BY_EVENT_AND_TIME_BLOCK",
        "concentration_attacks": ["REMOVE_STRONGEST_PAIR", "REMOVE_STRONGEST_CURRENCY", "REMOVE_STRONGEST_PERIOD", "LONG_SHORT_SPLIT", "SESSION_SPLIT", "VOLATILITY_SPLIT", "DERIVED_CROSS_SPLIT"],
        "global_trials": {"pre_stage1_lower_bound": CURRENT_ATTEMPT_LOWER_BOUND, "unresolved_cross_namespace_overlap": True, "stage0_increment": 0, "stage1_increment": "ONE_PER_REAL_OUTCOME_EXAMINED_CELL_UP_TO_72"},
        "dsr": {"implementation_status": "MISSING_REAL_IMPLEMENTATION", "required_inputs": ["candidate_return_series", "sampling_frequency", "sample_length", "observed_sharpe", "return_skew", "return_kurtosis", "number_of_trials", "cross_trial_sharpe_variance_or_effective_independent_trials", "benchmark_sharpe"], "not_a_profitability_certificate": True},
        "cscv_pbo": {"implementation_status": "MISSING_REAL_CSCV_ONLY_PROXIES_EXIST", "required_inputs": ["aligned_performance_matrix_all_scored_variants", "even_chronological_subsamples", "in_sample_and_out_of_sample_ranks", "logit_of_oos_rank", "dependence_preserving_partition_rules"], "required_before_promotion": True},
        "promotion_gates": {"qualifying_trades": ">=200", "net_expectancy": ">0", "profit_factor": ">=1.10", "maximum_drawdown_pct": "<=10", "contributing_instruments": ">=2_AND_NOT_EFFECTIVELY_ONE_CURRENCY_BET", "walk_forward": "PASS", "cost_stress": "PASS", "parameter_stability": "PASS", "leakage": "PASS", "concentration": "PASS", "multiple_testing": "PASS_GLOBAL_HISTORY", "reproduction": "TWO_RUN_BYTE_IDENTICAL"},
    }


def prior_family_reconciliation() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_PRIOR_FAMILY_RECONCILIATION.v1",
        "canonical_governed_family_fingerprint_set_sha256": prior.CURRENT_FAMILY_DIGEST,
        "canonical_governed_candidate_fingerprint_set_sha256": prior.CURRENT_CANDIDATE_DIGEST,
        "canonical_governed_family_fingerprint_count": 16,
        "canonical_governed_candidate_fingerprint_count": 112,
        "historical_families": ["BREAKOUT", "MEAN_REVERSION", "MOMENTUM", "MULTI_TIMEFRAME_CONFIRMATION", "PULLBACK", "SESSION_BREAKOUT", "TREND_CONTINUATION", "VOLATILITY_EXPANSION", "CROSS_SECTIONAL_CURRENCY_STRENGTH_MOMENTUM", "CROSS_PAIR_RESIDUAL_COINTEGRATION_MEAN_REVERSION", "CURRENCY_FACTOR_REGIME_ALLOCATION", "CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL", "CFTC_CROWDING_UNWIND", "CFTC_POSITIONING_ACCELERATION", "CFTC_PARTICIPANT_DIVERGENCE", "CFTC_DEALER_INVENTORY", "ROUND_NUMBER_EVENT", "SESSION_INVENTORY", "ABNORMAL_PRICE_UPDATE_RESPONSE", "DIRECTED_ANCHOR_CROSS_LEAD_LAG", "INTRADAY_USD_SETTLEMENT_FLOW", "CFTC_ASSET_MANAGER_WEEKLY_CHANGE"],
        "arm_relationships": {
            "A": "JUSTIFIED_SIMPLE_BASELINE_REPLICATION_OF_PRIOR_MOMENTUM_NOT_A_NEW_EDGE",
            "B": "SAME_BROAD_STRENGTH_MECHANISM_AS_PRIOR_CROSS_SECTIONAL_AND_FEATURE_WORK_BUT_NEW_CONSTRAINED_GRAPH_MEASUREMENT;_MUST_SHOW_INCREMENTAL_INFORMATION_NOT_CLAIM_NOVELTY",
            "C": "CONTROLLED_PULLBACK_TRANSLATION_COLLIDES_WITH_PRIOR_PULLBACK_FAMILY;_JUSTIFIED_ONLY_AS_MATCHED_COMPONENT_COMPARISON_NOT_NEW_EDGE",
            "D": "COMBINATION_ARM_NOT_INDEPENDENT_EDGE_AND_MUST_BEAT_B_AND_C",
        },
        "novelty_rule": "BROADER_UNIVERSE_ALONE_IS_NOT_NOVELTY",
        "round_number": "PRESERVE_135_PROPOSED_UNSCORED_AS_CHALLENGER;_DO_NOT_SCORE_WITHOUT_NEW_BUDGET_AND_MATERIALLY_DISTINCT_SPEC",
    }


def information_provenance(repo_root: Path) -> dict[str, Any]:
    # Check the complete allowlist BEFORE any content access, including hashing.
    assert_metadata_only_paths(METADATA_PROVENANCE_HASHES)
    documents = {}
    for relative, expected in METADATA_PROVENANCE_HASHES.items():
        try:
            content = (repo_root / relative).read_bytes()
        except FileNotFoundError as exc:
            raise ValueError(f"PROVENANCE_METADATA_MISSING:{relative}") from exc
        if sha256_bytes(content) != expected:
            raise ValueError(f"PROVENANCE_INPUT_HASH_MISMATCH:{relative}")
        documents[relative] = json.loads(content)
    guard = documents[".aios/runtime/forex_final_holdout_access_guard_v1.json"]
    incident = documents[ACCESS_CHECKPOINT]["access_exception"]
    if (guard["datasets"]["FINAL_HOLDOUT_V1"]["status"] != "SPENT_CONTAMINATED"
            or incident["strict_no_protected_access_claim"] is not False
            or incident["declared_cache_end"] != "2026-08-28T20:55:00Z"
            or len(incident["old_reports_parsed"]) != 2):
        raise ValueError("INFORMATION_PROVENANCE_EVIDENCE_MISMATCH")
    return {
        "schema": "AIOS_FOREX_INFORMATION_PROVENANCE_ASSESSMENT.v1",
        "HOLDOUT_INFORMATION_PROVENANCE": "CONTAMINATED",
        "VALIDATION_INFORMATION_PROVENANCE": "REUSED",
        "legacy_final_holdout_v1": guard["datasets"]["FINAL_HOLDOUT_V1"],
        "validation_evidence": {"current_interval": list(M5_VALIDATION), "older_development_interval": None, "overlap": None, "meaning": "PRIOR_REUSED_CLASSIFICATION_RETAINED;_SAVED_INCIDENT_RECORDS_OUTCOME_SUMMARY_ACCESS;_NOT_REASSESSED_FROM_PROTECTED_CONTENT"},
        "holdout_evidence": {"current_interval": list(M5_RESERVED_2026), "derived_cache": incident["derived_cache_hashed"], "historically_recorded_cache_sha256": PROVENANCE_INPUT_HASHES[incident["derived_cache_hashed"]], "previously_recorded_cache_last_timestamp": incident["declared_cache_end"], "feature_campaign_validation_results": None, "feature_campaign_holdout_results": None, "meaning": "PRIOR_ACCESS_REMAINS_CONTAMINATION;_CACHE_AND_OUTCOMES_NOT_REOPENED"},
        "metadata_inputs": METADATA_PROVENANCE_HASHES,
        "prior_access_incident": incident,
        "protected_content_opened_by_this_check": False,
        "hash_limit": "HASHES_DETECT_BYTE_CHANGE_BUT_DO_NOT_PREVENT_OR_UNDO_ACCESS",
        "subsequent_reader_minimum_enforcement": ["DEVELOPMENT_ONLY_PARTITION_SHARD_ALLOWLIST", "ROW_TIMESTAMP_GATE_BEFORE_FEATURE_CALCULATION", "FEATURE_LABEL_ENTRY_EXIT_AND_CONTEXT_HALF_OPEN_BOUNDARY_GATE", "DENY_DERIVED_CACHES_WITH_LATER_INFORMATION", "APPEND_ONLY_ACCESS_RECEIPT_WITH_SOURCE_AND_MAX_TIMESTAMP", "FAIL_CLOSED_ON_UNDECLARED_PATH"],
        "repository_wide_access_control_repaired": False,
        "independent_validation_claim_allowed_on_current_2025_2026_intervals": False,
        "development_only_research_allowed": True,
        "new_untouched_holdout_requirement": "ACQUIRE_AND_CRYPTOGRAPHICALLY_SEAL_NEW_OBSERVATIONS_STRICTLY_AFTER_2026-08-29T03:50:00Z_BEFORE_ANY_FEATURE_OR_REPORT_ACCESS",
        "stage0_rows_opened": {"development_price": 0, "validation": 0, "final_holdout": 0},
    }


def research_memory(rejection_paths: list[Path], repo_root: Path) -> dict[str, Any]:
    base = prior.reconcile_memory(rejection_paths, repo_root)
    completion_path = repo_root / PRIOR_COMPLETION
    if sha256_file(completion_path) != PRIOR_COMPLETION_SHA256:
        raise ValueError("PKT037_COMPLETION_HASH_MISMATCH")
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    if completion["global_attempt_lower_bound"] != CURRENT_ATTEMPT_LOWER_BOUND or completion["candidate_count_proposed"] != 135 or completion["candidate_count_scored"] != 0:
        raise ValueError("PKT037_MEMORY_MISMATCH")
    for relative, expected in PRIOR_SOURCE_HASHES.items():
        role = ("engine" if relative.startswith("automation/forex_engine/") else
                "packet" if relative.endswith(".md") else
                "runner" if relative.startswith("scripts/") else "tests")
        if completion["source_hashes"][role] != expected:
            raise ValueError(f"PKT037_HISTORICAL_SOURCE_IDENTITY_CHANGED:{relative}")
        if sha256_file(repo_root / relative) != REVIEWED_PKT044_SOURCE_HASHES.get(relative, expected):
            raise ValueError(f"UNREVIEWED_CURRENT_SOURCE_CHANGED:{relative}")
    return {
        "schema": "AIOS_FOREX_GLOBAL_TRIAL_MEMORY_SNAPSHOT.v1", "packet_id": PACKET_ID,
        "global_attempt_lower_bound_before": CURRENT_ATTEMPT_LOWER_BOUND, "global_attempt_lower_bound_after_stage0": CURRENT_ATTEMPT_LOWER_BOUND,
        "unresolved_cross_namespace_overlap": base["cross_namespace_semantic_overlap_status"],
        "status_classes": {
            "PROPOSED_UNSCORED": {"prior": PRIOR_PROPOSED_UNSCORED, "new_first_wave_cells": NEW_FIRST_WAVE_CELLS, "total_spec_records": PRIOR_PROPOSED_UNSCORED + NEW_FIRST_WAVE_CELLS},
            "OUTCOME_EXAMINED": {"lower_bound": CURRENT_ATTEMPT_LOWER_BOUND},
            "VALID_TEST_REJECTED": {"known_governed_lower_bound": completion["governed_after_cost_candidates"]},
            "INVALID_TEST_DATA_OR_IMPLEMENTATION": {"count": "UNKNOWN_UNRECONCILED_LEGACY_NAMESPACE"},
            "INSUFFICIENT_EVIDENCE": {"count": "UNKNOWN_UNRECONCILED_LEGACY_NAMESPACE"},
            "DUPLICATE_OF_PRIOR_TEST": {"new_first_wave_exact_hash_duplicates": 0, "semantic_collisions": "RECORDED_IN_PRIOR_FAMILY_RECONCILIATION"},
            "SURVIVOR": {"verified_edge": 0},
        },
        "round_number_proposals_preserved": 135, "round_number_scored_by_pkt037": 0,
        "canonical_governed_fingerprint_memory": base["current_governed_lineage"],
        "new_outcome_scored_trials": 0, "validation_rows_opened": 0, "final_holdout_rows_opened": 0,
        "prior_completion_sha256": PRIOR_COMPLETION_SHA256, "prior_source_hashes": PRIOR_SOURCE_HASHES,
        "reviewed_current_source_hashes": REVIEWED_PKT044_SOURCE_HASHES,
    }


def successor_requirements() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_REQUIREMENTS.v1", "recommended_packet_id": "PKT-FOREX-039",
        "purpose": "DEVELOPMENT_ONLY_FOUR_ARM_CURRENCY_MOMENTUM_COMPONENT_EFFECT_SCREEN",
        "exact_paths": ["automation/orchestration/work_packets/active/PKT-FOREX-039.md", "automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py", "scripts/forex_delivery/run_forex_edge_discovery_tournament_stage1_v1.py", "tests/forex_engine/test_forex_edge_discovery_tournament_stage1_v1.py", ".aios/staging/PKT_FOREX_039/", "automation/orchestration/locks/FILE_LOCK_REGISTRY.json_ONLY_EXACT_OCC74_CLAIM_RELEASE"],
        "reader_contract": "PARSE_ONLY_PERMITTED_DEVELOPMENT_SHARDS_ONCE_SHARE_DETERMINISTIC_FEATURES_CHECKPOINT_CELLS_SINGLE_WRITER",
        "allowed_outcomes": "DEVELOPMENT_2024-01-01_INCLUSIVE_TO_2025-04-01_EXCLUSIVE_ONLY", "validation_access": False, "reserved_2026_access": False,
        "maximum_new_scored_cells": 72, "do_not_refill_skips": True, "stop_after": "DEVELOPMENT_EFFECT_SCREEN_AND_POSTMORTEM_OR_SURVIVOR_HANDOFF",
    }


def build_stage0(rejection_paths: list[Path], repo_root: Path) -> dict[str, bytes]:
    datasets = prior.resolve_certified_datasets(repo_root)
    memory = research_memory(rejection_paths, repo_root)
    provenance = information_provenance(repo_root)
    cards = edge_cards()
    first_wave = first_wave_manifest()
    artifacts: dict[str, bytes] = {
        "AIOS_FOREX_PACKET_IDENTITY.json": pretty_bytes({
            "packet_id": PACKET_ID, "identity_marker": IDENTITY_MARKER, "supervisor_identity": "Codex East",
            "zone": "EAST", "worker_identity": WORKER_ID, "mode": "APPLY",
            "owner_lane": "FOREX_EDGE_DISCOVERY_TOURNAMENT_STAGE0", "assigned_worker": "Codex",
            "branch": "main", "worktree": "C:\\Dev\\Ai.Os",
            "allowed_write_boundary": ["automation/orchestration/work_packets/active/PKT-FOREX-038.md", "automation/forex_engine/forex_edge_discovery_tournament_stage0_v1.py", "scripts/forex_delivery/run_forex_edge_discovery_tournament_stage0_v1.py", "tests/forex_engine/test_forex_edge_discovery_tournament_stage0_v1.py", ".aios/staging/PKT_FOREX_038/", "automation/orchestration/locks/FILE_LOCK_REGISTRY.json_ONLY_OCC73"],
            "blocked_paths": ["ALL_UNLISTED_PATHS", "PRICE_PARTITIONS", "VALIDATION_ROWS", "FINAL_HOLDOUT_ROWS"],
            "forbidden_paths": [".git", ".env", "broker", "oanda", "live_trading", "secrets"],
            "approval_authority": "Anthony explicit PKT-FOREX-038 Stage-0 authorization 2026-09-06",
            "validator_chain": ["authority", "lock", "ast", "synthetic_causality", "focused_regression", "two_run_reproduction", "artifact_comparison", "diff_readback", "lock_release"],
            "lock_id": "LOCK_EAST_FOREX_EDGE_DISCOVERY_TOURNAMENT_STAGE0_OCC73",
            "stop_condition": "STOP_AFTER_VALIDATED_STAGE0_OCC73_RELEASE_AND_EXACT_PKT039_APPROVAL_SENTENCE",
        }),
        "AIOS_FOREX_EDGE_TOURNAMENT_CONTRACT.json": pretty_bytes({
            "schema": "AIOS_FOREX_EDGE_DISCOVERY_TOURNAMENT_STAGE0.v1", "packet_id": PACKET_ID, "identity_marker": IDENTITY_MARKER,
            "edge_not_strategy": "EDGE_IS_CONDITIONAL_MARKET_BEHAVIOR;_STRATEGY_IS_DETERMINISTIC_HARVEST_MECHANISM",
            "priority_order": [card["EDGE_ID"] for card in cards], "current_promotion_state": "EDGE_HYPOTHESIS",
            "permitted_states": ["EDGE_HYPOTHESIS", "MECHANISM_OBSERVED", "DEVELOPMENT_SURVIVOR", "COST_SURVIVOR", "ROBUSTNESS_SURVIVOR", "VALIDATION_SURVIVOR", "FINAL_HOLDOUT_SURVIVOR", "PAPER_CANDIDATE", "PAPER_VALIDATED_EDGE"],
            "stage0": {"development_price_rows_opened": 0, "validation_rows_opened": 0, "final_holdout_rows_opened": 0, "new_outcome_scored_trials": 0},
            "verified_edge": False, "paper_or_live_authorized": False,
        }),
        "AIOS_FOREX_EDGE_CARDS.json": pretty_bytes({"schema": "AIOS_FOREX_EDGE_CARDS.v1", "cards": cards}),
        "AIOS_FOREX_SOURCE_TO_EXPERIMENT_MAP.json": pretty_bytes(source_experiment_map()),
        "AIOS_FOREX_PRIOR_FAMILY_RECONCILIATION.json": pretty_bytes(prior_family_reconciliation()),
        "AIOS_FOREX_INFORMATION_PROVENANCE.json": pretty_bytes(provenance),
        "AIOS_FOREX_GLOBAL_TRIAL_MEMORY.json": pretty_bytes(memory),
        "AIOS_FOREX_FIRST_WAVE_EXPERIMENT_MANIFEST.json": pretty_bytes(first_wave),
        "AIOS_FOREX_CURRENCY_GRAPH_CONTRACT.json": pretty_bytes(graph_contract()),
        "AIOS_FOREX_PULLBACK_STATE_MACHINE.json": pretty_bytes({"schema": "AIOS_FOREX_PULLBACK_STATE_MACHINE.v1", "states": ["IDLE", "IMPULSE_IDENTIFIED", "PULLBACK_QUALIFIED", "RESUMPTION_CONFIRMED", "ENTRY_ELIGIBLE", "EXPIRED", "INVALIDATED", "DATA_BLOCKED", "COST_BLOCKED"], "implementation": "pullback_state_machine", "anchors": "FROZEN_AT_IMPULSE"}),
        "AIOS_FOREX_COST_EXPOSURE_CONTRACT.json": pretty_bytes(cost_exposure_contract()),
        "AIOS_FOREX_LATER_ENTRY_EXIT_CONTRACT.json": pretty_bytes(entry_exit_contract()),
        "AIOS_FOREX_STATISTICAL_CONTRACT.json": pretty_bytes(statistical_contract()),
        "AIOS_FOREX_SUCCESSOR_REQUIREMENTS.json": pretty_bytes(successor_requirements()),
        "AIOS_FOREX_IMMUTABLE_DATASET_REFERENCE.json": pretty_bytes({"schema": "AIOS_FOREX_TOURNAMENT_DATASET_REFERENCE.v1", "m5": datasets["m5_corpus"], "pair_count": datasets["pair_count"], "h1_context_pairs": 58, "fine_candle_finalist_scope": datasets["subminute_and_m1_m4_finalist_scope"], "market_rows_opened": 0}),
    }
    report = (
        "# AIOS Forex Edge Discovery Tournament Stage 0\n\n"
        "Ten Edge Cards and a bounded four-arm currency-momentum component comparison were frozen without opening market outcomes. "
        "The 1,220 scored-attempt lower bound and 446 prior proposed-but-unscored records remain visible; 72 new cells are proposed but unscored. "
        "The 2025 validation interval is REUSED and the 2026 reserved interval is CONTAMINATED by a prior derived feature cache, so neither can support an independent-validation claim. "
        "A development-only Stage 1 can proceed under a separate packet. VERIFIED_EDGE remains false.\n"
    ).encode("utf-8")
    artifacts["AIOS_FOREX_EDGE_TOURNAMENT_STAGE0_REPORT.md"] = report
    manifest = {"schema": "AIOS_FOREX_EDGE_TOURNAMENT_MANIFEST.v1", "artifacts": {name: {"bytes": len(content), "sha256": sha256_bytes(content)} for name, content in sorted(artifacts.items())}}
    manifest_bytes = pretty_bytes(manifest)
    artifacts["AIOS_FOREX_EDGE_TOURNAMENT_MANIFEST.json"] = manifest_bytes
    receipt = {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_RECEIPT.v1", "packet_id": PACKET_ID, "status": "PASS",
        "manifest_sha256": sha256_bytes(manifest_bytes), "artifact_count": len(artifacts) + 1,
        "acceptance": {"ten_edge_cards": "PASS", "first_wave_36_plus_36": "PASS", "prior_memory_preserved": "PASS", "pkt037_sources_preserved": "PASS", "source_claims_separated": "PASS", "information_provenance_truthful": "PASS", "graph_c_minus_one_contract": "PASS", "entry_exit_unambiguous": "PASS", "cost_exposure_frozen": "PASS", "statistics_fail_closed": "PASS", "zero_outcome_access": "PASS"},
        "counters": {"development_price_rows_opened": 0, "validation_rows_opened": 0, "final_holdout_rows_opened": 0, "new_outcome_scored_trials": 0},
        "verified_edge": False, "commit": "NOT_PERFORMED", "push": "NOT_PERFORMED",
        "safety": {key: False for key in ("network_at_runtime", "broker", "credentials", "paper", "practice", "live", "orders", "money_movement", "market_outcome_access")},
    }
    artifacts["AIOS_FOREX_EDGE_TOURNAMENT_RECEIPT.json"] = pretty_bytes(receipt)
    return artifacts
