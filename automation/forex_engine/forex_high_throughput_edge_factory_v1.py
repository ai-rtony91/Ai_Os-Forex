"""No-outcome factory repair and round-number Stage-0 gate for PKT-FOREX-037.

This module never opens price, broker, credential, Paper, Practice, LIVE, or
holdout data.  It builds a compact mixed-radix description of one million
hypotheses, reconciles known historical research ledgers, ranks economic
mechanism clusters, and emits one bounded successor preregistration.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


PACKET_ID = "PKT-FOREX-037"
CATALOG_SCHEMA = "AIOS_FOREX_VIRTUAL_HYPOTHESIS_CATALOG.v1"
CATALOG_SIZE = 1_000_000
CHUNK_SIZE = 4096
CURRENT_FAMILY_DIGEST = "42b15e860e6918b3420da8808102f7dc0aa07bc4528c3897e027b524fc78f96d"
CURRENT_CANDIDATE_DIGEST = "7089d906f069b0b7e138672f99ce9d745045dd98379cbd4747aa8a5dc06799d4"
CURRENT_INPUT_MANIFEST_DIGEST = "697043d8a3977c1339a0c54218622fb7ead2fadef250e0d859b999b32df972c3"
M5_CORPUS_HASH = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
M5_MANIFEST_SHA256 = "1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b"
PAIR_TIMEFRAME_MATRIX_SHA256 = "55bdf7e07117bcd2e7f1e81c9204fe0945c69b0986e09cb3166859aceb27ec41"
INSTRUMENT_METADATA_SHA256 = "13a922c29806f153eea73adb06bc7f23c1b6a3bcee272f58fcd28777a99a200e"
PRIOR_COMPLETION_SHA256 = "8bdb2b2e23e7fdc7812ba07f39d7183e9c4a5e603403e96491f95a9a09187dcc"
CURRENT_ATTEMPT_LOWER_BOUND = 1220
CURRENT_GOVERNED_CANDIDATES = 168


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


MECHANISMS = (
    {
        "id": "ROUND_NUMBER_CONDITIONAL_ORDER_STATE",
        "economic_mechanism": "TAKE_PROFIT_ORDERS_CLUSTER_AT_00_50_WHILE_STOP_ORDERS_CLUSTER_JUST_BEYOND_LEVELS",
        "long_direction": "BUY_A_LOWER_LEVEL_APPROACH_BOUNCE_OR_UPPER_LEVEL_CONFIRMED_CROSS",
        "exact_reverse_short_direction": "SHORT_THE_EXACT_SAME_LOWER_APPROACH_OR_UPPER_CROSS_EVENT",
        "short_direction": "SHORT_AN_UPPER_LEVEL_APPROACH_BOUNCE_OR_LOWER_LEVEL_CONFIRMED_CROSS",
        "exact_reverse_long_direction": "BUY_THE_EXACT_SAME_UPPER_APPROACH_OR_LOWER_CROSS_EVENT",
        "bidirectional_version": "TRADE_BOTH_ORIGINAL_LONG_AND_ORIGINAL_SHORT_EVENT_CLASSES",
        "source_ids": ["NYFED_SR125_ROUND_NUMBER_ORDERS", "NYFED_SR150_STOP_CASCADES"],
        "nearest_rejected": ["BREAKOUT", "MEAN_REVERSION"],
        "collision": "DISTINCT_IF_APPROACH_AND_CONFIRMED_CROSS_STATE_ARE_EXPLICIT",
        "data_compatibility": "CERTIFIED_58_PAIR_M5",
        "scores": [5, 5, 5, 4, 5],
    },
    {
        "id": "VIX_SHOCK_SAFE_HAVEN_INTRADAY",
        "economic_mechanism": "GLOBAL_RISK_REDUCTION_CREATES_SAFE_HAVEN_DEMAND_AND_CARRY_UNWIND",
        "long_direction": "BUY_SAFE_HAVEN_CURRENCY_AGAINST_RISK_CURRENCY_AFTER_POINT_IN_TIME_VIX_SHOCK",
        "exact_reverse_short_direction": "SHORT_SAFE_HAVEN_CURRENCY_ON_THE_IDENTICAL_VIX_SHOCK",
        "short_direction": "SHORT_RISK_CURRENCY_AGAINST_SAFE_HAVEN_CURRENCY_AFTER_POINT_IN_TIME_VIX_SHOCK",
        "exact_reverse_long_direction": "BUY_RISK_CURRENCY_ON_THE_IDENTICAL_VIX_SHOCK",
        "bidirectional_version": "LONG_SAFE_HAVENS_AND_SHORT_RISK_CURRENCIES_IN_ONE_EXPOSURE_CAPPED_BASKET",
        "source_ids": ["IMF_WP_2013_008_RISK_OFF", "IMF_WP_2013_228_YEN"],
        "nearest_rejected": ["CURRENCY_FACTOR_REGIME_ALLOCATION"],
        "collision": "LOW_MEDIUM_EXTERNAL_STATE_IS_DISTINCT",
        "data_compatibility": "FROZEN_VIX_PLUS_CERTIFIED_H1_M5_SHORT_HISTORY",
        "scores": [5, 4, 4, 4, 5],
    },
    {
        "id": "SESSION_HANDOFF_INVENTORY_CYCLE",
        "economic_mechanism": "RECURRING_LOCAL_HOURS_CROSS_BORDER_INVENTORY_DEMAND",
        "long_direction": "BUY_CURRENCY_DURING_COUNTER_CURRENCY_LOCAL_HOURS",
        "exact_reverse_short_direction": "SHORT_CURRENCY_DURING_COUNTER_CURRENCY_LOCAL_HOURS",
        "short_direction": "SHORT_CURRENCY_DURING_ITS_OWN_LOCAL_HOURS",
        "exact_reverse_long_direction": "BUY_CURRENCY_DURING_ITS_OWN_LOCAL_HOURS",
        "bidirectional_version": "APPLY_BOTH_LOCAL_HOURS_LEGS_WITH_DST_AWARE_WINDOWS",
        "source_ids": ["SNB_RANALDO_2009_SESSION_SEGMENTATION", "SNB_BREEDON_RANALDO_2011"],
        "nearest_rejected": ["SESSION_BREAKOUT"],
        "collision": "MEDIUM_DISTINCT_ONLY_AS_INVENTORY_CYCLE_NOT_SESSION_FILTER",
        "data_compatibility": "M5_COMPATIBLE_CALENDAR_QUALIFICATION_REQUIRED",
        "scores": [4, 4, 4, 4, 4],
    },
    {
        "id": "RISK_OFF_LEVERAGED_FUND_CONTRACTION",
        "economic_mechanism": "RISK_OFF_FORCED_DELEVERAGING_UNWINDS_CROWDED_LEVERAGED_FUND_POSITIONS",
        "long_direction": "BUY_CURRENCY_PREVIOUSLY_SHORT_CROWDED_WHEN_ABSOLUTE_POSITION_CONTRACTS_IN_RISK_OFF_STATE",
        "exact_reverse_short_direction": "SHORT_THE_SAME_CURRENCY_ON_THE_IDENTICAL_CONTRACTION_EVENT",
        "short_direction": "SHORT_CURRENCY_PREVIOUSLY_LONG_CROWDED_WHEN_ABSOLUTE_POSITION_CONTRACTS_IN_RISK_OFF_STATE",
        "exact_reverse_long_direction": "BUY_THE_SAME_CURRENCY_ON_THE_IDENTICAL_CONTRACTION_EVENT",
        "bidirectional_version": "TRADE_BOTH_CROWDING_SIGNS_WITH_DISJOINT_CURRENCY_EXPOSURE",
        "source_ids": ["KREMENS_POSITIONING_RISK"],
        "nearest_rejected": ["CFTC_POSITIONING_STATE_WITH_PRICE_CONFIRMATION", "CFTC_POSITIONING_ACCELERATION_WITH_PRICE_CONTINUATION"],
        "collision": "HIGH_UNLESS_CAUSAL_INTERACTION_BEATS_EACH_COMPONENT",
        "data_compatibility": "CFTC_VIX_H1_AVAILABLE_EVENT_CAPACITY_AND_FINANCING_CAVEATS",
        "scores": [5, 3, 3, 3, 5],
    },
    {
        "id": "POLICY_SURPRISE_INTRADAY_REPRICING",
        "economic_mechanism": "UNEXPECTED_POLICY_INFORMATION_REPRICES_RELATIVE_INTEREST_RATE_PATHS",
        "long_direction": "BUY_POSITIVE_SURPRISE_CURRENCY",
        "exact_reverse_short_direction": "SHORT_POSITIVE_SURPRISE_CURRENCY",
        "short_direction": "SHORT_NEGATIVE_SURPRISE_CURRENCY",
        "exact_reverse_long_direction": "BUY_NEGATIVE_SURPRISE_CURRENCY",
        "bidirectional_version": "TRADE_BOTH_SURPRISE_SIGNS",
        "source_ids": [],
        "nearest_rejected": [],
        "collision": "LOW",
        "data_compatibility": "BLOCKED_MISSING_POINT_IN_TIME_CONSENSUS_SURPRISE",
        "scores": [5, 1, 4, 2, 5],
    },
    {
        "id": "POST_FIX_LIQUIDITY_DEMAND",
        "economic_mechanism": "BENCHMARK_FIX_LIQUIDITY_DEMAND_CREATES_PRE_FIX_PRESSURE_AND_POST_FIX_REVERSAL",
        "long_direction": "BUY_DOCUMENTED_POST_FIX_REVERSAL_LEG",
        "exact_reverse_short_direction": "SHORT_THE_IDENTICAL_POST_FIX_EVENT",
        "short_direction": "SHORT_DOCUMENTED_POST_FIX_REVERSAL_LEG",
        "exact_reverse_long_direction": "BUY_THE_IDENTICAL_POST_FIX_EVENT",
        "bidirectional_version": "TRADE_BOTH_FIX_DIRECTIONS",
        "source_ids": ["KROHN_FIXINGS_2024"],
        "nearest_rejected": ["SESSION_BREAKOUT"],
        "collision": "MEDIUM",
        "data_compatibility": "M5_COMPATIBLE_BUT_SOURCE_COST_ADJUSTED_RESULT_NEGATIVE",
        "scores": [3, 4, 1, 4, 4],
    },
    {
        "id": "VOLATILITY_COMPRESSION_BREAKOUT",
        "economic_mechanism": "ABNORMAL_COMPRESSION_PRECEDES_RANGE_EXPANSION",
        "long_direction": "BUY_UPSIDE_RANGE_BREAK",
        "exact_reverse_short_direction": "SHORT_UPSIDE_RANGE_BREAK",
        "short_direction": "SHORT_DOWNSIDE_RANGE_BREAK",
        "exact_reverse_long_direction": "BUY_DOWNSIDE_RANGE_BREAK",
        "bidirectional_version": "TRADE_BOTH_BREAK_DIRECTIONS",
        "source_ids": [],
        "nearest_rejected": ["BREAKOUT", "VOLATILITY_EXPANSION"],
        "collision": "DUPLICATE_BLOCKED",
        "data_compatibility": "CERTIFIED_M5_H1",
        "scores": [3, 5, 2, 5, 2],
    },
    {
        "id": "CROSS_SECTIONAL_RELATIVE_VALUE",
        "economic_mechanism": "TEMPORARY_CROSS_CURRENCY_MISPRICING_CONVERGES",
        "long_direction": "BUY_UNDERVALUED_CURRENCY",
        "exact_reverse_short_direction": "SHORT_UNDERVALUED_CURRENCY",
        "short_direction": "SHORT_OVERVALUED_CURRENCY",
        "exact_reverse_long_direction": "BUY_OVERVALUED_CURRENCY",
        "bidirectional_version": "MARKET_NEUTRAL_LONG_SHORT_BASKET",
        "source_ids": [],
        "nearest_rejected": ["CROSS_PAIR_RESIDUAL_COINTEGRATION_MEAN_REVERSION", "CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL"],
        "collision": "DUPLICATE_BLOCKED",
        "data_compatibility": "CERTIFIED_58_PAIR_M5",
        "scores": [3, 5, 3, 3, 2],
    },
    {
        "id": "GENERIC_TREND_PULLBACK",
        "economic_mechanism": "PERSISTENT_INFORMATION_DIFFUSION_WITH_TEMPORARY_PULLBACK",
        "long_direction": "BUY_PULLBACK_IN_UPTREND",
        "exact_reverse_short_direction": "SHORT_PULLBACK_IN_UPTREND",
        "short_direction": "SHORT_RALLY_IN_DOWNTREND",
        "exact_reverse_long_direction": "BUY_RALLY_IN_DOWNTREND",
        "bidirectional_version": "TRADE_BOTH_TREND_SIGNS",
        "source_ids": ["FXABSOLUTE_EDGE_GUIDE"],
        "nearest_rejected": ["PULLBACK", "TREND_CONTINUATION", "MULTI_TIMEFRAME_CONFIRMATION"],
        "collision": "DUPLICATE_BLOCKED",
        "data_compatibility": "CERTIFIED_M1_H1_WHERE_AVAILABLE",
        "scores": [2, 4, 2, 4, 2],
    },
    {
        "id": "GENERIC_SESSION_LIQUIDITY_SWEEP_REVERSAL",
        "economic_mechanism": "SESSION_EXTREME_STOP_CLUSTER_SWEEP_THEN_FAILED_AUCTION",
        "long_direction": "BUY_FAILED_BREAK_BELOW_SESSION_LOW",
        "exact_reverse_short_direction": "SHORT_FAILED_BREAK_BELOW_SESSION_LOW",
        "short_direction": "SHORT_FAILED_BREAK_ABOVE_SESSION_HIGH",
        "exact_reverse_long_direction": "BUY_FAILED_BREAK_ABOVE_SESSION_HIGH",
        "bidirectional_version": "TRADE_BOTH_SESSION_EXTREMES",
        "source_ids": ["FXABSOLUTE_EDGE_GUIDE", "BIS_STERLING_FLASH_EVENT_2017"],
        "nearest_rejected": ["MEAN_REVERSION", "SESSION_BREAKOUT"],
        "collision": "BLOCKED_UNSUPPORTED_GENERIC_SWEEP_NARRATIVE",
        "data_compatibility": "M5_COMPATIBLE",
        "scores": [2, 5, 2, 4, 3],
    },
)

CONTEXTS = tuple(
    {
        "id": name,
        "session_condition": session,
        "volatility_condition": volatility,
        "trend_condition": trend,
        "range_condition": range_condition,
        "relative_value_condition": relative,
        "positioning_condition": positioning,
        "risk_sentiment_condition": risk,
        "economic_event_condition": event,
    }
    for name, session, volatility, trend, range_condition, relative, positioning, risk, event in (
        ("UNCONDITIONED", "ANY", "ANY", "ANY", "ANY", "NOT_APPLICABLE", "NOT_APPLICABLE", "ANY", "NO_EVENT_FILTER"),
        ("LONDON", "LONDON_07_00_16_00_UTC", "NORMAL", "ANY", "ANY", "NOT_APPLICABLE", "NOT_APPLICABLE", "ANY", "NO_EVENT_FILTER"),
        ("LONDON_NY_OVERLAP", "LONDON_NEW_YORK_OVERLAP_12_00_16_00_UTC", "NORMAL", "ANY", "ANY", "NOT_APPLICABLE", "NOT_APPLICABLE", "ANY", "NO_EVENT_FILTER"),
        ("ASIA_HANDOFF", "ASIA_TO_EUROPE_HANDOFF", "NORMAL", "ANY", "ANY", "NOT_APPLICABLE", "NOT_APPLICABLE", "ANY", "NO_EVENT_FILTER"),
        ("LOW_VOL", "ANY", "TRAINING_FROZEN_LOW_QUANTILE", "ANY", "COMPRESSION", "NOT_APPLICABLE", "NOT_APPLICABLE", "RISK_ON", "NO_EVENT_FILTER"),
        ("HIGH_VOL", "ANY", "TRAINING_FROZEN_HIGH_QUANTILE", "ANY", "EXPANSION", "NOT_APPLICABLE", "NOT_APPLICABLE", "RISK_OFF", "NO_EVENT_FILTER"),
        ("TREND", "ANY", "ANY", "TRAINING_FROZEN_TREND", "NOT_RANGE", "NOT_APPLICABLE", "NOT_APPLICABLE", "ANY", "NO_EVENT_FILTER"),
        ("RANGE", "ANY", "ANY", "NOT_TREND", "TRAINING_FROZEN_RANGE", "NOT_APPLICABLE", "NOT_APPLICABLE", "ANY", "NO_EVENT_FILTER"),
        ("POSITIONING", "ANY", "ANY", "ANY", "ANY", "NOT_APPLICABLE", "POINT_IN_TIME_CFTC", "ANY", "NO_EVENT_FILTER"),
        ("EVENT_EXCLUSION", "ANY", "ANY", "ANY", "ANY", "NOT_APPLICABLE", "NOT_APPLICABLE", "ANY", "EXCLUDE_ONLY_IF_CERTIFIED_POINT_IN_TIME_CALENDAR_EXISTS"),
    )
)

TIMEFRAMES = tuple(
    {"id": key, "signal_timeframe": signal, "confirmation_timeframe": confirmation}
    for key, signal, confirmation in (
        ("M1_M5", "M1", "M5"), ("M5_NONE", "M5", "NONE"), ("M5_M15", "M5", "M15"),
        ("M5_M30", "M5", "M30"), ("M5_H1", "M5", "H1"), ("M15_M30", "M15", "M30"),
        ("M15_H1", "M15", "H1"), ("M30_H1", "M30", "H1"), ("H1_NONE", "H1", "NONE"),
        ("M30_NONE", "M30", "NONE"),
    )
)
LOOKBACKS = ("1_BAR", "2_BARS", "3_BARS", "4_BARS", "6_BARS", "8_BARS", "12_BARS", "16_BARS", "24_BARS", "32_BARS")
THRESHOLDS = ("0.00", "0.25", "0.50", "0.75", "1.00", "1.25", "1.50", "2.00", "2.50", "3.00")
DIRECTIONS = ("ORIGINAL_LONG", "EXACT_REVERSED_SHORT", "ORIGINAL_SHORT", "EXACT_REVERSED_LONG", "SYMMETRIC_BIDIRECTIONAL")
EXITS = (
    {"id": "FIXED_TIME", "exit_rule": "EXIT_ON_COMPLETED_TIME_LIMIT", "stop_type": "ENTRY_ATR_PROTECTIVE_STOP", "take_profit_type": "NONE_TIME_EXIT_PRIMARY", "time_exit": "SOURCE_OR_HORIZON_TEMPLATE", "position_sizing_rule": "VOLATILITY_SCALED_0.25_PERCENT_EQUITY_RISK", "exposure_cap": "MAX_FIVE_DISJOINT_CURRENCY_PAIRS", "holding_period_class": "INTRADAY_NO_ROLLOVER"},
    {"id": "STOP_TARGET_TIME", "exit_rule": "FIRST_EXECUTABLE_STOP_TARGET_OR_TIME", "stop_type": "ENTRY_ATR", "take_profit_type": "FIXED_R_MULTIPLE", "time_exit": "BOUNDED_BY_SIGNAL_TIMEFRAME", "position_sizing_rule": "VOLATILITY_SCALED_0.25_PERCENT_EQUITY_RISK", "exposure_cap": "MAX_FIVE_DISJOINT_CURRENCY_PAIRS", "holding_period_class": "INTRADAY_OR_PREREGISTERED_SLOW"},
)
PAIR_SELECTIONS = (
    "CERTIFIED_58_PAIR_FULL_UNIVERSE", "ALL_SPREAD_ELIGIBLE_PAIRS", "DISJOINT_CURRENCY_MAX_FIVE",
    "SAFE_HAVEN_VERSUS_RISK_CROSSES", "CFTC_MAPPABLE_PAIRS", "MAJOR_PAIRS", "NON_USD_CROSSES",
    "TRAINING_ONLY_LIQUIDITY_TIERS_THEN_FROZEN", "ROUND_LEVEL_PIP_COMPATIBLE_PAIRS", "POINT_IN_TIME_EVENT_EXPOSED_PAIRS",
)


AXES = (MECHANISMS, CONTEXTS, TIMEFRAMES, LOOKBACKS, THRESHOLDS, DIRECTIONS, EXITS)
AXIS_NAMES = ("mechanism", "context", "timeframe", "lookback", "threshold", "direction", "exit")


def catalog_cardinality() -> int:
    return math.prod(len(axis) for axis in AXES)


def decode_index(index: int) -> tuple[int, ...]:
    if index < 0 or index >= CATALOG_SIZE:
        raise IndexError("CATALOG_INDEX_OUT_OF_RANGE")
    values = [0] * len(AXES)
    remainder = index
    for position in range(len(AXES) - 1, -1, -1):
        remainder, values[position] = divmod(remainder, len(AXES[position]))
    return tuple(values)


def encode_index(indices: Iterable[int]) -> int:
    values = tuple(indices)
    if len(values) != len(AXES):
        raise ValueError("CATALOG_AXIS_COUNT_MISMATCH")
    ordinal = 0
    for value, axis in zip(values, AXES):
        if value < 0 or value >= len(axis):
            raise IndexError("CATALOG_AXIS_INDEX_OUT_OF_RANGE")
        ordinal = ordinal * len(axis) + value
    return ordinal


def _pair_selection(index: int) -> str:
    return PAIR_SELECTIONS[index % len(PAIR_SELECTIONS)]


def spec_at(index: int) -> dict[str, Any]:
    mi, ci, ti, li, qi, di, ei = decode_index(index)
    mechanism = MECHANISMS[mi]
    context = CONTEXTS[ci]
    timeframe = TIMEFRAMES[ti]
    exit_spec = EXITS[ei]
    spec = {
        "catalog_id": f"FXH-{index:07d}",
        "economic_mechanism": mechanism["economic_mechanism"],
        "long_direction": mechanism["long_direction"],
        "exact_reverse_short_direction": mechanism["exact_reverse_short_direction"],
        "original_short_direction": mechanism["short_direction"],
        "exact_reverse_long_direction": mechanism["exact_reverse_long_direction"],
        "bidirectional_version": mechanism["bidirectional_version"],
        "direction_variant": DIRECTIONS[di],
        "pair_selection_logic": _pair_selection(qi),
        "currency_selection_logic": "NORMALIZE_PAIR_ORIENTATION_TO_SIGNED_BASE_AND_QUOTE_CURRENCY_EXPOSURE",
        "session_condition": context["session_condition"],
        "volatility_condition": context["volatility_condition"],
        "trend_condition": context["trend_condition"],
        "range_condition": context["range_condition"],
        "relative_value_condition": context["relative_value_condition"],
        "positioning_condition": context["positioning_condition"],
        "risk_sentiment_condition": context["risk_sentiment_condition"],
        "economic_event_condition": context["economic_event_condition"],
        "signal_timeframe": timeframe["signal_timeframe"],
        "confirmation_timeframe": timeframe["confirmation_timeframe"],
        "entry_rule": f"COMPLETED_CANDLE_RULE_{mechanism['id']}_LOOKBACK_{LOOKBACKS[li]}_THRESHOLD_{THRESHOLDS[qi]}",
        "exit_rule": exit_spec["exit_rule"],
        "stop_type": exit_spec["stop_type"],
        "take_profit_type": exit_spec["take_profit_type"],
        "time_exit": exit_spec["time_exit"],
        "position_sizing_rule": exit_spec["position_sizing_rule"],
        "exposure_cap": exit_spec["exposure_cap"],
        "holding_period_class": exit_spec["holding_period_class"],
        "lookback_slot": LOOKBACKS[li],
        "threshold_slot": THRESHOLDS[qi],
    }
    spec["candidate_fingerprint"] = sha256_bytes(canonical_bytes(spec))
    return spec


INVERSE_DIRECTIONS = {
    "ORIGINAL_LONG": "EXACT_REVERSED_SHORT",
    "EXACT_REVERSED_SHORT": "ORIGINAL_LONG",
    "ORIGINAL_SHORT": "EXACT_REVERSED_LONG",
    "EXACT_REVERSED_LONG": "ORIGINAL_SHORT",
    "SYMMETRIC_BIDIRECTIONAL": "SYMMETRIC_BIDIRECTIONAL",
}


def inverse_spec(spec: dict[str, Any]) -> dict[str, Any]:
    output = dict(spec)
    output.pop("candidate_fingerprint", None)
    output["direction_variant"] = INVERSE_DIRECTIONS[spec["direction_variant"]]
    output["candidate_fingerprint"] = sha256_bytes(canonical_bytes(output))
    return output


def catalog_descriptor() -> dict[str, Any]:
    descriptor = {
        "schema": CATALOG_SCHEMA,
        "derivation_version": "MIXED_RADIX_RULE_AST_V1",
        "enumeration_order": list(AXIS_NAMES),
        "axis_lengths": {name: len(axis) for name, axis in zip(AXIS_NAMES, AXES)},
        "cardinality": catalog_cardinality(),
        "materialized_item_count": 0,
        "market_outcomes_read": False,
        "catalog_items_count_as_trials": False,
        "mechanisms": MECHANISMS,
        "contexts": CONTEXTS,
        "timeframes": TIMEFRAMES,
        "lookbacks": LOOKBACKS,
        "thresholds": THRESHOLDS,
        "directions": DIRECTIONS,
        "exits": EXITS,
        "pair_selection_templates": PAIR_SELECTIONS,
    }
    descriptor["descriptor_sha256"] = sha256_bytes(canonical_bytes(descriptor))
    return descriptor


def catalog_chunk_hashes(descriptor_sha256: str) -> list[dict[str, Any]]:
    chunks = []
    for start in range(0, CATALOG_SIZE, CHUNK_SIZE):
        end = min(CATALOG_SIZE, start + CHUNK_SIZE)
        digest = hashlib.sha256()
        for index in range(start, end):
            token = f"{descriptor_sha256}:{index}:{','.join(map(str, decode_index(index)))}\n".encode("ascii")
            digest.update(token)
        chunks.append({"chunk": len(chunks), "start": start, "end_exclusive": end, "count": end - start, "sha256": digest.hexdigest()})
    return chunks


class DeterministicImplementationCatalog:
    """Lazy mixed-radix catalog, independent of data, results and execution.

    Conditional blocks contain only active implementation axes. Identity does
    not include an ordinal, catalog version, provenance URL or cost label.
    Consumers supply economic rules and enforce admission/history policy.
    The original intraday catalog API above remains unchanged.
    """

    def __init__(self, descriptor: dict[str, Any]):
        import bisect
        self._bisect = bisect
        self._descriptor = json.loads(canonical_bytes(descriptor))
        self._blocks = self._descriptor["blocks"]
        self._ends: list[int] = []
        self._counts: list[int] = []
        self.family_counts: dict[str, int] = {}
        block_keys = set()
        total = 0
        for block in self._blocks:
            if not block["mechanism"] or not block["axes"]:
                raise ValueError("EMPTY_CATALOG_BLOCK")
            key = sha256_bytes(canonical_bytes(block))
            if key in block_keys:
                raise ValueError("DUPLICATE_CATALOG_BLOCK")
            block_keys.add(key)
            fixed = set(block["fixed"])
            count = 1
            for name, values in block["axes"].items():
                if name in fixed or not values or len({canonical_bytes(v) for v in values}) != len(values):
                    raise ValueError("DUPLICATE_OR_EMPTY_AXIS")
                count *= len(values)
            total += count
            self._counts.append(count)
            self._ends.append(total)
            family = block["mechanism"]["family"]
            self.family_counts[family] = self.family_counts.get(family, 0) + count
        self.cardinality = total
        self.descriptor_sha256 = sha256_bytes(canonical_bytes(self._descriptor))

    @property
    def descriptor(self) -> dict[str, Any]:
        return json.loads(canonical_bytes(self._descriptor))

    @staticmethod
    def fingerprint(mechanism: dict[str, Any], implementation: dict[str, Any]) -> str:
        return sha256_bytes(canonical_bytes({"mechanism": mechanism, "implementation": implementation}))

    def spec_at(self, index: int) -> dict[str, Any]:
        if type(index) is not int or not 0 <= index < self.cardinality:
            raise ValueError("CATALOG_INDEX_OUT_OF_RANGE")
        block_index = self._bisect.bisect_right(self._ends, index)
        block = self._blocks[block_index]
        local = index - (self._ends[block_index - 1] if block_index else 0)
        implementation = dict(block["fixed"])
        for name, values in reversed(list(block["axes"].items())):
            local, digit = divmod(local, len(values))
            implementation[name] = values[digit]
        mechanism = block["mechanism"]
        return json.loads(canonical_bytes({
            "index": index, "catalog_version": self._descriptor["version"],
            "mechanism": mechanism, "implementation": implementation,
            "implementation_sha256": self.fingerprint(mechanism, implementation)}))

    def index_of(self, spec: dict[str, Any]) -> int:
        if spec.get("catalog_version") != self._descriptor["version"]:
            raise ValueError("CATALOG_VERSION_MISMATCH")
        mechanism, implementation = spec["mechanism"], spec["implementation"]
        if spec.get("implementation_sha256") != self.fingerprint(mechanism, implementation):
            raise ValueError("IMPLEMENTATION_HASH_MISMATCH")
        matches = []
        for n, block in enumerate(self._blocks):
            if mechanism != block["mechanism"] or set(implementation) != set(block["fixed"]) | set(block["axes"]):
                continue
            if any(implementation[k] != v for k, v in block["fixed"].items()):
                continue
            local = 0
            for name, values in block["axes"].items():
                try:
                    digit = values.index(implementation[name])
                except ValueError:
                    break
                local = local * len(values) + digit
            else:
                matches.append((self._ends[n - 1] if n else 0) + local)
        if len(matches) != 1:
            raise ValueError("UNKNOWN_OR_AMBIGUOUS_IMPLEMENTATION")
        if "index" in spec and spec["index"] != matches[0]:
            raise ValueError("CATALOG_ORDINAL_MISMATCH")
        return matches[0]

    def iter_specs(self, start: int = 0, end: int | None = None):
        end = self.cardinality if end is None else end
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= self.cardinality:
            raise ValueError("CATALOG_RANGE_OUT_OF_BOUNDS")
        for index in range(start, end):
            yield self.spec_at(index)

    def family_ranges(self) -> dict[str, list[tuple[int, int]]]:
        result: dict[str, list[tuple[int, int]]] = {}
        for n, block in enumerate(self._blocks):
            start = self._ends[n - 1] if n else 0
            result.setdefault(block["mechanism"]["family"], []).append((start, self._ends[n]))
        return result

    def content_chunks(self, chunk_size: int = 4096):
        if type(chunk_size) is not int or chunk_size < 1:
            raise ValueError("INVALID_CHUNK_SIZE")
        for start in range(0, self.cardinality, chunk_size):
            end = min(self.cardinality, start + chunk_size)
            h = hashlib.sha256()
            for spec in self.iter_specs(start, end):
                h.update(canonical_bytes(spec))
            yield {"start": start, "end_exclusive": end, "count": end - start, "sha256": h.hexdigest()}


def supertrend_research_catalog_v1() -> DeterministicImplementationCatalog:
    """Separate namespace; never mutates the frozen documented-FX warehouse.

    Conditional axes are active only in their policy. Memory determines decay;
    there is no second equivalent decay axis. Fingerprints are implementation
    identities, not proof of independent mechanisms or distinct trades.
    """
    periods = [7, 10, 14, 20, 28, 40, 56, 80]
    grids = [[0.5, 0.75, 1.0, 3.0, 5.0],
             [0.75, 1.0, 1.5, 2.0, 2.75, 4.0, 6.0],
             [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.5, 5.0, 7.0],
             [0.5, 0.75, 1.0, 1.25, 1.75, 2.25, 3.0, 4.0, 5.25, 6.5, 8.0]]
    memory, cadence = [4, 8, 16, 32, 64, 96, 128, 256], [1, 2, 4, 8]
    common = {"atr_period": periods, "factors": grids}
    fixed = {"bar_contract": "STRICT_CLOSED_M5_V1", "indicator_contract": "SUPERTREND_RESEARCH_V1",
             "execution": "NEXT_OPEN_CANONICAL_S6", "instrument": "SPOT_NO_ROLLOVER",
             "risk": "FROZEN_BOUNDED_FIXED_RISK", "cost_scenarios": "EXISTING_S6_BASE_STRESS_EXTREME"}
    def block(policy, axes):
        return {"mechanism": {"family": "SUPERTREND_" + policy + "_RESEARCH_V1",
            "hypothesis": "CAUSAL_PRICE_TREND_STUDY", "method_version": "INDEPENDENT_PUBLIC_MATH_V1"},
            "fixed": {**fixed, "policy": policy}, "axes": axes}
    return DeterministicImplementationCatalog({"version": "SUPERTREND_STUDY_CATALOG_V1",
        "status": "INVENTORY_ONLY", "market_authority": False,
        "source_method": "Public mathematical concepts; no vendor implementation copied; admission separate",
        "blocks": [block("CLASSIC", {"atr_period": periods, "multiplier": [0.5, 0.75, 1, 1.5, 2, 3, 4, 6]}),
            block("ADAPTIVE_CLUSTER", {**common, "performance_memory": memory, "update_cadence": cadence,
                "cluster_rule": ["WORST", "MIDDLE", "BEST"], "representative": ["MEDIAN_MEMBER", "MEDOID_LOW_TIE"]}),
            block("CONSENSUS", {**common, "consensus_threshold": [0.34, 0.67, 1.0],
                "normalization": ["DIRECTION", "BAND_DISTANCE"], "neutral_rule": ["CASH", "RETAIN_PREVIOUS"], "update_cadence": cadence}),
            block("STABILITY_SELECTED", {**common, "performance_memory": memory, "update_cadence": cadence,
                "adjacency_radius": [1, 2], "minimum_support": [0.5, 0.75, 1.0], "maximum_dispersion": [0.1, 0.3, 0.7]})]})


def supertrend_static_prefilter_v1(spec, catalog, closed_fingerprints=()):
    """No prices/outcomes. Closed history is a prohibition, never parameter rescue."""
    try:
        catalog.index_of(spec)
    except (KeyError, TypeError, ValueError):
        return {"state": "STATIC_REJECTED", "reason": "INVALID_OR_NOOP_IDENTITY", "market_exposure": 0}
    if spec["implementation_sha256"] in closed_fingerprints:
        return {"state": "CLOSED_HISTORY", "reason": "EXACT_SETTLED_FINGERPRINT", "market_exposure": 0}
    return {"state": "INVENTORY_ONLY", "reason": "DATA_COST_HISTORY_GRANT_ADMISSION_REQUIRED", "market_exposure": 0}


def supertrend_trade_equivalence_v1(direction_sequences):
    """Diagnostic only: equal frozen opportunity directions collapse to one path identity."""
    grouped = {}
    for fingerprint, sequence in direction_sequences.items():
        if any(type(x) is not int or x not in (-1, 0, 1) for x in sequence):
            raise ValueError("TRADE_EQUIVALENCE_DIRECTION_INVALID")
        digest = sha256_bytes(canonical_bytes(sequence))
        grouped.setdefault(digest, []).append(fingerprint)
    return {"implementation_count": len(direction_sequences), "distinct_direction_sequences": len(grouped),
            "groups": {k: sorted(v) for k, v in sorted(grouped.items())},
            "independent_samples": False, "market_exposure": 0}


def public_sources() -> list[dict[str, Any]]:
    def row(source_id: str, title: str, url: str, author: str, publication: str, source_type: str,
            mechanism: str, rules: str, performance: str, costs: str, walk_forward: bool,
            code: str, license_name: str, risks: list[str], compatibility: str,
            match: str, priority: str, disposition: str) -> dict[str, Any]:
        return {
            "source_id": source_id, "title": title, "url": url, "author_or_organization": author,
            "publication_date": publication, "access_date": "2026-09-04", "source_type": source_type,
            "claimed_economic_mechanism": mechanism, "claimed_market_and_timeframe": "FOREX_AS_DISCLOSED_BY_SOURCE",
            "exact_disclosed_rules": rules, "claimed_performance": performance, "costs_included": costs,
            "walk_forward_included": walk_forward, "source_code": code, "license": license_name,
            "replication_risks": risks, "aios_dataset_compatibility": compatibility,
            "existing_fingerprint_match": match, "research_priority": priority,
            "final_disposition": disposition, "evidence_status": "UNVERIFIED_HYPOTHESIS_SOURCE",
        }

    return [
        row("FXABSOLUTE_EDGE_GUIDE", "How to Build a Trading Edge", "https://fxabsolute.com/how-to-build-trading-edge", "FXAbsolute", "2026-08-24", "COMMERCIAL_GUIDE",
            "Precise observable rules and condition analysis may improve research discipline", "No single reproducible strategy; examples include structure, sessions, volatility, and filters", "Marketing benchmarks and testimonials are unsupported", "MIXED_UNVERIFIED", False, "NONE", "UNSTATED",
            ["marketing bias", "optimized examples", "claims are not independent evidence"], "METHOD_GUIDANCE_ONLY", "HIGH_WITH_REJECTED_GENERIC_FAMILIES", "METHOD_ONLY", "USE_DISCIPLINE_NOT_PERFORMANCE_CLAIMS"),
        row("NYFED_SR125_ROUND_NUMBER_ORDERS", "Currency Orders and Exchange-Rate Dynamics", "https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr125.pdf", "Carol L. Osler; Federal Reserve Bank of New York", "2001-04", "CENTRAL_BANK_STAFF_REPORT",
            "Take-profit orders cluster at round numbers while stop orders cluster just beyond them", "00 or 00/50 levels; approach within 0.01 percent; compare bounces and completed crossings", "Order clustering and short-horizon conditional price effects", "NO", False, "NONE", "FEDERAL_RESERVE_PUBLICATION",
            ["dated dealer sample", "small effect may be consumed by costs", "quote precision differences"], "STRONG_M1_M5_COMPATIBILITY", "MEDIUM_HIGH_GENERIC_BREAKOUT_REVERSION", "HIGH", "STAGE1_AFTER_SEMANTIC_GATE"),
        row("NYFED_SR150_STOP_CASCADES", "Stop-Loss Orders and Price Cascades in Currency Markets", "https://www.newyorkfed.org/research/staff_reports/sr150.html", "Carol L. Osler; Federal Reserve Bank of New York", "2002-07", "CENTRAL_BANK_STAFF_REPORT",
            "Activated stop orders create short-horizon positive-feedback cascades", "Compare price continuation at documented stop clusters after genuine crossing", "Faster and longer trends around stop-loss clusters", "NO", False, "NONE", "FEDERAL_RESERVE_PUBLICATION",
            ["proprietary order data unavailable", "spread expansion", "breakout collision"], "SUPPORTS_COMPLETED_CROSS_BRANCH", "HIGH_BREAKOUT_UNLESS_ROUND_STATE_EXPLICIT", "SUPPORT", "MECHANISM_SUPPORT_ONLY"),
        row("IMF_WP_2013_008_RISK_OFF", "The Behavior of Currencies during Risk-off Episodes", "https://www.imf.org/-/media/websites/imf/imported-full-text-pdf/external/pubs/ft/wp/2013/_wp1308.pdf", "Reinout De Bock; Irineu de Carvalho Filho; IMF", "2013-01", "IMF_WORKING_PAPER",
            "Risk reduction creates carry unwind and safe-haven demand", "Risk-off when VIX is 10 points above backward 60-day average; measure 1 to 12 weeks", "JPY CHF USD appreciation and VIX-beta cross section", "NO", False, "NONE", "IMF_COPYRIGHT",
            ["few independent events", "reaction may predate tradable signal", "financing"], "VIX_H1_M5_PARTIAL_SHORT_HISTORY", "LOW_MEDIUM", "HIGH", "STAGE1_WITH_INTRADAY_ADAPTATION"),
        row("IMF_WP_2013_228_YEN", "The Curious Case of the Yen as a Safe Haven Currency", "https://www.imf.org/en/publications/wp/issues/2016/12/31/the-curious-case-of-the-yen-as-a-safe-haven-currency-a-forensic-analysis-41039", "Dennis Botman; Irineu de Carvalho Filho; Waikei Raphael Lam; IMF", "2013-11-06", "IMF_WORKING_PAPER",
            "Risk shocks induce forward hedging and reduction of net-short JPY positions", "Event study; no complete executable trading rule", "JPY appreciation during risk-off episodes", "NO", False, "NONE", "IMF_COPYRIGHT",
            ["single-currency concentration", "forward data unavailable"], "SUPPORTS_ONE_BASKET_LEG", "LOW", "SUPPORT", "MECHANISM_SUPPORT_ONLY"),
        row("SNB_RANALDO_2009_SESSION_SEGMENTATION", "Segmentation and time-of-day patterns in foreign exchange markets", "https://edoc.unibas.ch/entities/publication/0dc3ca2c-1f2b-4e55-b2d5-ddad38fd4cec", "Angelo Ranaldo; Swiss National Bank affiliation", "2009-12-01", "PEER_REVIEWED_PAPER",
            "Domestic-hours cross-border demand creates cyclical inventory pressure", "Short a currency in domestic hours and long in counter-currency hours across four-hour periods", "Broad time-of-day patterns", "YES", False, "NONE", "IN_COPYRIGHT_ELSEVIER",
            ["modern decay", "DST errors", "spread at handoff"], "M5_H1_CALENDAR_REQUIRED", "MEDIUM_SESSION", "MEDIUM", "FAST_SCREEN_AFTER_CALENDAR_GATE"),
        row("SNB_BREEDON_RANALDO_2011", "Intraday patterns in FX returns and order flow", "https://www.snb.ch/en/publications/research/working-papers/2011/working_paper_2011_04", "Francis Breedon; Angelo Ranaldo; Swiss National Bank", "2011-03-23", "SNB_WORKING_PAPER",
            "Order flow supports local-hours inventory cycles", "Short own-session currency and long during counter-currency session", "Only EUR/USD clearly profitable after costs", "YES", False, "NONE", "SNB_PUBLICATION",
            ["pair concentration", "after-cost decay"], "M5_COMPATIBLE", "MEDIUM_SESSION", "LOW_MEDIUM", "FAST_SCREEN_ONLY"),
        row("KREMENS_POSITIONING_RISK", "Positioning Risk", "https://www.wu.ac.at/fileadmin/wu/d/ri/isk/VSFX_2020/2_1a_Kremens_Speculator_Risk_20200625.pdf", "Lukas Kremens", "2020-06-25", "ACADEMIC_WORKING_PAPER",
            "Risk-off forced deleveraging reverses leveraged-fund position changes", "After risk-off week and absolute position contraction, hold opposite direction next week", "Conditional active-week results reported", "BID_ASK_REPORTED", False, "NONE", "UNSTATED",
            ["rare events", "S&P input missing", "financing", "CFTC publication lag"], "PARTIAL_VIX_RECONSTRUCTION_ONLY", "HIGH_CFTC_COLLISION", "CONDITIONAL", "STAGE0_CAPACITY_AND_COLLISION_GATE"),
        row("BIS_STERLING_FLASH_EVENT_2017", "Report on the 7 October 2016 sterling flash event", "https://www.bis.org/media-releases/20170113-report-sterling-flash-event-released-markets-committee", "BIS Markets Committee", "2017-01-13", "OFFICIAL_EVENT_REPORT",
            "Low liquidity stop losses and unsuitable algorithms amplify moves", "No trading rule", "Single-event retracement", "NO", False, "NONE", "BIS_COPYRIGHT",
            ["single event", "extreme costs", "unobserved order flow"], "SAFETY_REGIME_ONLY", "HIGH_GENERIC_SWEEP", "SAFETY", "DO_NOT_TRADE_STANDALONE"),
        row("KROHN_FIXINGS_2024", "Foreign Exchange Fixings and Returns around the Clock", "https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13306", "Lukas Krohn", "2024", "PEER_REVIEWED_PAPER",
            "Fixing demand creates pre-fix pressure and post-fix reversal", "Trade documented fixing windows", "Liquidity-demanding cost-adjusted strategy reported negative", "YES", False, "NONE", "WILEY_COPYRIGHT",
            ["adverse selection", "spread costs", "session collision"], "M5_COMPATIBLE", "MEDIUM", "NEGATIVE_CONTROL", "REJECT_EXECUTABLE_EDGE"),
    ]


def _extract_fingerprints(payload: dict[str, Any]) -> tuple[set[str], set[str]]:
    families: set[str] = set()
    candidates: set[str] = set()
    if isinstance(payload.get("family_fingerprint"), str):
        families.add(payload["family_fingerprint"])
    for row in payload.get("candidate_rows", {}).values() if isinstance(payload.get("candidate_rows"), dict) else []:
        for key in ("candidate_fingerprint", "exact_rules_fingerprint", "rules_hash"):
            if isinstance(row.get(key), str):
                candidates.add(row[key])
                break
    ledger = payload.get("rejection_ledger", {})
    if isinstance(ledger, dict):
        for row in ledger.get("family_rows", []):
            value = row.get("family_fingerprint") or row.get("mechanism_fingerprint")
            if isinstance(value, str):
                families.add(value)
        for row in ledger.get("candidate_rows", []):
            value = row.get("candidate_fingerprint") or row.get("exact_rules_fingerprint") or row.get("rules_hash")
            if isinstance(value, str):
                candidates.add(value)
    return families, candidates


def _set_digest(values: set[str]) -> str:
    return sha256_bytes(json.dumps(sorted(values), separators=(",", ":")).encode("utf-8"))


def reconcile_memory(rejection_paths: list[Path], legacy_root: Path) -> dict[str, Any]:
    families: set[str] = set()
    candidates: set[str] = set()
    inputs = []
    for path in rejection_paths:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        found_families, found_candidates = _extract_fingerprints(payload)
        families.update(found_families)
        candidates.update(found_candidates)
        relative_path = path.resolve().relative_to(legacy_root.resolve()).as_posix()
        inputs.append({"path": relative_path, "sha256": sha256_file(path)})
    family_digest = _set_digest(families)
    candidate_digest = _set_digest(candidates)
    # The authoritative receipt freezes phase-first, then packet-sequence order.
    input_digest = sha256_bytes(canonical_bytes(inputs).rstrip(b"\n"))
    if (len(families), len(candidates), family_digest, candidate_digest) != (16, 112, CURRENT_FAMILY_DIGEST, CURRENT_CANDIDATE_DIGEST):
        raise ValueError("CURRENT_GOVERNED_MEMORY_MISMATCH")
    if input_digest != CURRENT_INPUT_MANIFEST_DIGEST:
        raise ValueError("CURRENT_REJECTION_INPUT_MANIFEST_MISMATCH")

    legacy = {
        "mtf_gross_screen": ("Reports/forex_delivery/AIOS_FOREX_MTF_HYPOTHESIS_LEDGER_V1.json", "da2067a7ae731c1d7b8fb0e45fec06c96e95d4620ed5055741c0c987b9412e10", 912, "OUTCOME_TOUCHED_GROSS_SCREEN"),
        "next_generation": ("Reports/forex_delivery/AIOS_FOREX_NEXT_GENERATION_CANDIDATE_REGISTRY_V1.json", "5c2c9f46d5a7dc3be7955090b17aafb03b37bffbe88cffa6a3bef13a3461b60a", 32, "OUTCOME_TOUCHED_DEVELOPMENT"),
        "early_edge": (".aios/runtime/forex_edge_research_v1/candidate_registry.json", "54eb123f2d5a3b4d53414f5eb62b21f65cfea3fda621699bbfd5cd0a51c6ec89", 8, "OUTCOME_TOUCHED_LEGACY_NAMESPACE"),
        "feature_edge": (".aios/runtime/forex_feature_edge_research_v2/candidate_registry.json", "68156ea71fc5d6d883fb6820e05391be7cefc25940f81c8db2dfd2b25766c911", 22, "OUTCOME_TOUCHED_LEGACY_NAMESPACE"),
        "full_spectrum": (".aios/runtime/forex_full_spectrum_edge_program_v1/registry.json", "c75b9a36179a3a983c00a846a00faba7849a25bf674f1999dacbfce4abb57e7b", 48, "OUTCOME_TOUCHED_LEGACY_NAMESPACE"),
        "mechanism_program": (".aios/runtime/forex_mechanism_edge_program_v1/hypothesis_registry.json", "fabcd1b08f44139a4f99cbc5f9c44bd8f95f19d556b968cf1cf6890ad7de4910", 30, "OUTCOME_TOUCHED_LEGACY_NAMESPACE"),
        "scalping_catalog": ("Reports/forex_delivery/AIOS_FOREX_ALL_TIMEFRAME_SCALPING_HYPOTHESIS_LEDGER_V1.json", "a6eb2da7193cfbc2786d0dfee43617d2c712d6385885eb5b761ccd46e9d154c6", 263, "PROPOSED_UNTESTED"),
        "institutional_preview": (".aios/runtime/forex_institutional_edge_program_v1/hypothesis_registry_preview.json", "3b01fd55d784a419374ccbe29123d02d9e24419f9ede14e367d9dd50038d93f2", 48, "PROPOSED_UNTESTED"),
        "targeted_invalid": ("Reports/forex_delivery/AIOS_FOREX_TARGETED_CANDIDATE_REGISTRY_V3.json", "95b78009544fa1d4c5af7a5d5d79f81f2361ec54eeef9e0e3c33065f3bc47f17", 20, "ATTEMPTED_NO_DATA_INVALID"),
    }
    legacy_rows = []
    for source_id, (relative, expected, count, classification) in legacy.items():
        path = legacy_root / relative
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"LEGACY_SOURCE_HASH_MISMATCH:{source_id}")
        legacy_rows.append({"source_id": source_id, "path": relative, "sha256": actual, "count": count, "classification": classification})
    return {
        "schema": "AIOS_FOREX_GLOBAL_EXPERIMENT_MEMORY_SNAPSHOT.v1",
        "current_governed_lineage": {"rejected_families": 16, "scored_after_cost_candidates": 112, "family_digest": family_digest, "candidate_digest": candidate_digest, "input_manifest_digest": input_digest, "input_order": "CANONICAL_PHASE_THEN_PACKET_SEQUENCE", "inputs": inputs},
        "legacy_sources": legacy_rows,
        "cross_namespace_semantic_overlap_status": "UNRESOLVED_BLOCKS_CHAMPION_PROMOTION_BUT_DOES_NOT_ERASE_COMPUTE_ATTEMPTS",
        "conservative_nonoverlapping_computational_attempt_lower_bound": 1164,
        "fully_governed_after_cost_trial_count": 112,
        "known_heterogeneous_fold_summary_count": 4600,
        "current_lineage_summary_fold_windows": 288,
        "proposed_untested_count": 311,
        "attempted_no_data_invalid_count": 20,
        "new_stage0_catalog_scored_trials": 0,
        "holdout_evaluations": 0,
        "champion_promotion_blocked_until_legacy_unknown_resolved": True,
    }


def cluster_rows() -> list[dict[str, Any]]:
    rows = []
    for mechanism in MECHANISMS:
        score = sum(mechanism["scores"])
        blocked = "BLOCKED" in mechanism["collision"] or "BLOCKED" in mechanism["data_compatibility"] or "NEGATIVE" in mechanism["data_compatibility"]
        descriptor = {key: mechanism[key] for key in ("id", "economic_mechanism", "long_direction", "exact_reverse_short_direction", "short_direction", "exact_reverse_long_direction", "bidirectional_version")}
        rows.append({
            "cluster_id": mechanism["id"], "mechanism_fingerprint": sha256_bytes(canonical_bytes(descriptor)),
            "economic_reason": mechanism["economic_mechanism"], "inverse_direction": mechanism["exact_reverse_short_direction"],
            "semantic_collision": mechanism["collision"], "certified_data_compatibility": mechanism["data_compatibility"],
            "public_source_ids": mechanism["source_ids"], "known_failure_modes": ["TRANSACTION_COSTS", "SELECTION_BIAS", "REGIME_OR_PAIR_CONCENTRATION"],
            "economic_justification_score": mechanism["scores"][0], "data_compatibility_score": mechanism["scores"][1],
            "cost_resistance_score": mechanism["scores"][2], "implementation_simplicity_score": mechanism["scores"][3],
            "information_value_score": mechanism["scores"][4], "rank_score": score,
            "stage0_disposition": "BLOCKED" if blocked else "ELIGIBLE_FOR_BOUNDED_PREREGISTRATION",
        })
    return sorted(rows, key=lambda row: (-row["rank_score"], row["cluster_id"]))


def closure_audit(repo_root: Path) -> dict[str, Any]:
    required = [
        ".aios/staging/PKT_FOREX_019_022_R1/revision2/PKT_FOREX_019_022_R1_PROMOTION_COMPLETION.json",
        ".aios/staging/PKT_FOREX_023/PKT_FOREX_023_COMPLETION.json",
        ".aios/staging/PKT_FOREX_024/PKT_FOREX_024_COMPLETION.json",
        ".aios/staging/PKT_FOREX_025/PKT_FOREX_025_COMPLETION.json",
        ".aios/staging/PKT_FOREX_026/RESUMABLE_EDGE_RESEARCH.json",
        ".aios/staging/PKT_FOREX_027/PKT_FOREX_027_COMPLETION.json",
        ".aios/staging/PKT_FOREX_028/PKT_FOREX_028_COMPLETION.json",
        ".aios/staging/PKT_FOREX_029/PKT_FOREX_029_COMPLETION.json",
        ".aios/staging/PKT_FOREX_030/PKT_FOREX_030_COMPLETION.json",
        ".aios/staging/PKT_FOREX_031/PKT_FOREX_031_COMPLETION.json",
        ".aios/staging/PKT_FOREX_032/PKT_FOREX_032_COMPLETION.json",
        ".aios/staging/PKT_FOREX_033/PKT_FOREX_033_COMPLETION.json",
        ".aios/staging/PKT_FOREX_034/PKT_FOREX_034_COMPLETION.json",
        ".aios/staging/PKT_FOREX_035/PKT_FOREX_035_EXPANSION58_COMPLETION.json",
        ".aios/staging/PKT_FOREX_036/PKT_FOREX_036_EXPANSION58_COMPLETION.json",
    ]
    rows = []
    for relative in required:
        path = repo_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"MISSING_PACKET_CLOSURE:{relative}")
        rows.append({"path": relative, "sha256": sha256_file(path)})
    latest = repo_root / required[-1]
    if sha256_file(latest) != PRIOR_COMPLETION_SHA256:
        raise ValueError("PKT036_COMPLETION_SHA256_MISMATCH")
    payload = json.loads(latest.read_text(encoding="utf-8"))
    valid = payload["result"] == "VALID_STAGE1_FAILURE" and payload["actual_computational_attempt_lower_bound_after"] == CURRENT_ATTEMPT_LOWER_BOUND and payload["governed_after_cost_candidates_after"] == CURRENT_GOVERNED_CANDIDATES and payload["validation_rows_opened"] == payload["final_holdout_rows_opened"] == 0
    return {"packet_range": "PKT-FOREX-019_THROUGH_PKT-FOREX-036", "closure_evidence": rows, "latest_checkpoint_sha256": PRIOR_COMPLETION_SHA256, "status": "PASS" if valid else "FAIL"}


def run_pkt044_batch(repo_root, output, contract, manifest, *, resume=False):
    """Explicit approved scoring route, separate from the old no-data catalog."""
    from automation.forex_engine.edge_research.batch import execute
    from automation.forex_engine.edge_research.execution import ARM_IDS
    if (contract.get("packet_id") != "PKT-FOREX-044" or contract.get("worker") != "EAST_OCC_82"
            or tuple(x["candidate_id"] for x in contract.get("cards", [])) != ARM_IDS
            or contract.get("budget", {}).get("new_scored_specifications") != 2):
        raise ValueError("FACTORY_BATCH_PERMISSION_OR_BUDGET_INVALID")
    return execute(repo_root, output, contract, manifest, resume=resume)


def resolve_certified_datasets(repo_root: Path) -> dict[str, Any]:
    m5_path = repo_root / ".aios/runtime/forex_m5_immutable_corpus_v2/manifest.json"
    matrix_path = repo_root / ".aios/staging/PKT_FOREX_027/run1/AIOS_FOREX_AUTHORITATIVE_PAIR_TIMEFRAME_MATRIX_V1.json"
    metadata_path = repo_root / ".aios/staging/PKT_FOREX_042/final_run1/AIOS_FOREX_PKT039_CORRECTED_INPUT_VERIFICATION.json"
    expected = ((m5_path, M5_MANIFEST_SHA256), (matrix_path, PAIR_TIMEFRAME_MATRIX_SHA256), (metadata_path, INSTRUMENT_METADATA_SHA256))
    for path, digest in expected:
        if sha256_file(path) != digest:
            raise ValueError(f"IMMUTABLE_DATASET_INPUT_MISMATCH:{path.name}")
    m5 = json.loads(m5_path.read_text(encoding="utf-8"))
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    pairs = tuple(sorted(m5["eligible_pairs"]))
    m5_rows = {row["pair"]: row for row in matrix["rows"] if row["granularity"] == "M5" and row["development_eligibility"] is True}
    h1_rows = {row["pair"]: row for row in matrix["rows"] if row["granularity"] == "H1" and row["development_eligibility"] is True}
    metadata_rows = metadata["instrument_metadata"]["pair_metadata"]
    if len(pairs) != 58 or set(pairs) != set(m5_rows) or set(pairs) != set(h1_rows) or set(pairs) != set(metadata_rows):
        raise ValueError("EXACT_58_PAIR_DATASET_ALIGNMENT_FAILED")
    rows = []
    for pair in pairs:
        item = metadata_rows[pair]
        if item["pip_size"] != 10 ** item["pip_location"] or item["display_precision"] <= -item["pip_location"]:
            raise ValueError(f"INSTRUMENT_METADATA_INVALID:{pair}")
        rows.append({
            "pair": pair,
            "base_currency": pair.split("_")[0],
            "quote_currency": pair.split("_")[1],
            "pip_location": item["pip_location"],
            "pip_size": item["pip_size"],
            "display_precision": item["display_precision"],
            "round_level_step_pips": 50,
            "round_level_offsets_pips": [0],
            "arbitrary_control_offsets_pips": [25],
            "m5_source_path": m5_rows[pair]["source_path"],
            "m5_source_sha256": m5_rows[pair]["source_sha256"],
            "h1_source_path": h1_rows[pair]["source_path"],
            "h1_source_sha256": h1_rows[pair]["source_sha256"],
            "status": "ELIGIBLE",
            "exclusion_reason": "NONE",
        })
    fine = {granularity: sorted(row["pair"] for row in matrix["rows"] if row["granularity"] == granularity and row["development_eligibility"] is True) for granularity in ("S5", "S10", "S15", "S30", "M1", "M2", "M4")}
    if any(value != ["EUR_USD", "GBP_USD", "USD_JPY"] for value in fine.values()):
        raise ValueError("SUBMINUTE_THREE_PAIR_SCOPE_DRIFT")
    return {
        "schema": "AIOS_FOREX_IMMUTABLE_DATASET_RESOLVER.v1",
        "m5_corpus": {"id": m5["corpus_id"], "aggregate_sha256": m5["aggregate_corpus_fingerprint"], "manifest_sha256": M5_MANIFEST_SHA256},
        "pair_timeframe_matrix_sha256": PAIR_TIMEFRAME_MATRIX_SHA256,
        "instrument_metadata_sha256": INSTRUMENT_METADATA_SHA256,
        "pair_count": 58,
        "eligible_pair_count": 58,
        "excluded_pair_count": 0,
        "pair_rows": rows,
        "subminute_and_m1_m4_finalist_scope": fine,
        "files_opened": [m5_path.relative_to(repo_root).as_posix(), matrix_path.relative_to(repo_root).as_posix(), metadata_path.relative_to(repo_root).as_posix()],
        "market_price_rows_opened": 0,
        "validation_rows_opened": 0,
        "final_holdout_rows_opened": 0,
        "status": "PASS",
    }


def round_number_candidates(mechanism_fingerprint: str) -> list[dict[str, Any]]:
    candidates = []
    for branch in ("ROUND_NUMBER_APPROACH_REJECTION", "ROUND_NUMBER_COMPLETED_CROSS_CONTINUATION"):
        buffers = (None,) if branch == "ROUND_NUMBER_APPROACH_REJECTION" else (0, 1)
        for distance in (2, 5, 10):
            for buffer_pips in buffers:
                for holding_minutes in (15, 30, 60):
                    for direction in DIRECTIONS:
                        definition = {
                            "branch": branch,
                            "approach_distance_pips": distance,
                            "confirmation_buffer_pips": buffer_pips,
                            "holding_minutes": holding_minutes,
                            "direction_variant": direction,
                            "level_grid": "EVERY_50_PIPS_FROM_ZERO_USING_METADATA_PIP_SIZE",
                            "event_lockout_minutes": 60,
                            "stop": "1_0_CAUSAL_M5_ATR20_FIXED_AT_ENTRY",
                            "target_r": 2.0,
                        }
                        definition["candidate_id"] = f"RN-{branch.removeprefix('ROUND_NUMBER_')}-D{distance}-B{'NA' if buffer_pips is None else buffer_pips}-H{holding_minutes}-{direction}"
                        definition["candidate_fingerprint"] = sha256_bytes(canonical_bytes({"mechanism_fingerprint": mechanism_fingerprint, "definition": definition}))
                        candidates.append(definition)
    if len(candidates) != 135 or len({row["candidate_fingerprint"] for row in candidates}) != 135:
        raise ValueError("ROUND_NUMBER_CANDIDATE_GRID_INVALID")
    return candidates


def after_cost_pips(gross_pips: float, entry_spread_pips: float, exit_spread_pips: float, slippage_pips_per_side: float, financing_pips: float = 0.0) -> float:
    return gross_pips - entry_spread_pips / 2.0 - exit_spread_pips / 2.0 - 2.0 * slippage_pips_per_side - financing_pips


def champion_gate(metrics: dict[str, Any]) -> bool:
    return bool(metrics.get("after_cost_expectancy", 0) > 0 and metrics.get("profit_factor", 0) >= 1.10 and metrics.get("maximum_drawdown_pct", 100) <= 10 and metrics.get("trades", 0) >= 200 and all(metrics.get(key) is True for key in ("walk_forward", "cost_stress", "parameter_stability", "leakage", "concentration", "baseline", "multiple_testing", "reproduction")))


def factory_capabilities() -> dict[str, Any]:
    names = ["immutable_dataset_resolver", "exact_58_pair_timeframe_matrix", "completed_candle_gate", "causal_m5_h1_asof_contract", "bid_ask_cost_function", "exact_inverse_mapping", "arbitrary_level_control", "strategy_candidate_fingerprints", "cheap_stage1_gate", "break_even_cost_contract", "walk_forward_fold_contract", "parameter_stability_contract", "regime_concentration_contract", "cumulative_multiple_testing_ledger", "deterministic_checkpoint_resume", "minimal_early_failure_artifacts", "automatic_postmortem_rejection_memory", "champion_selection_gate", "cryptographic_holdout_seal_contract"]
    return {"schema": "AIOS_FOREX_EDGE_FACTORY_CAPABILITY_MATRIX.v1", "capabilities": {name: {"status": "IMPLEMENTED_OR_FROZEN_INTERFACE", "stage0_market_outcomes_read": False} for name in names}, "stage1_implementation_rule": "SCORER_MUST_USE_THESE_FROZEN_INTERFACES_AND_ADD_REGRESSION_TESTS_BEFORE_OUTCOME_INTERPRETATION", "status": "PASS"}


def successor_preregistration(memory: dict[str, Any], clusters: list[dict[str, Any]], datasets: dict[str, Any]) -> dict[str, Any]:
    selected = next(row for row in clusters if row["cluster_id"] == "ROUND_NUMBER_CONDITIONAL_ORDER_STATE")
    if selected["stage0_disposition"] != "ELIGIBLE_FOR_BOUNDED_PREREGISTRATION":
        raise ValueError("SUCCESSOR_CLUSTER_NOT_ELIGIBLE")
    candidates = round_number_candidates(selected["mechanism_fingerprint"])
    prereg = {
        "schema": "AIOS_FOREX_ROUND_NUMBER_CONDITIONAL_ORDER_STATE_PREREGISTRATION.v2",
        "packet_id": PACKET_ID,
        "strategy_identity": "ROUND_NUMBER_CONDITIONAL_ORDER_STATE_STRATEGY",
        "economic_mechanism": selected["economic_reason"],
        "dataset_identity": datasets["m5_corpus"],
        "pair_universe": [row["pair"] for row in datasets["pair_rows"]],
        "pair_metadata": datasets["pair_rows"],
        "timeframe_roles": {"event_discovery_entry_exit": "M5", "regime_decomposition": "H1_CAUSAL_ASOF_ONLY", "finalist_execution": datasets["subminute_and_m1_m4_finalist_scope"]},
        "round_level_definition": "Price levels at integer multiples of 50*pip_size from zero; 00 and 50 alternate on that grid. Pip size comes only from the frozen instrument metadata snapshot.",
        "arbitrary_level_control": "Identical event rules at integer multiples of 50*pip_size plus 25*pip_size; frozen before returns.",
        "event_rules": {
            "approach_rejection": "Prior completed M5 close must be on one side and farther than the configured approach distance. The next completed M5 candle must touch or cross the level and close back on the prior side. Enter at the following M5 executable open away from the level.",
            "completed_cross_continuation": "Prior completed M5 close must be on one side. A completed M5 candle must close beyond the level by the configured buffer. The next completed M5 decision candle must remain beyond the level. Enter at the following M5 executable open in the crossing direction.",
            "lockout": "One event per pair, level, and crossing direction during the following 60 minutes; earliest event wins without outcome access.",
        },
        "direction_rules": {"variants": list(DIRECTIONS), "inverse_identity": "identical event IDs, timestamps, prices, holds, stops, targets, costs, folds and opportunities with arithmetic opposite order side", "state_independence": "APPROACH_REJECTION_AND_COMPLETED_CROSS_MUST_PASS_SEPARATELY"},
        "parameter_grid": candidates,
        "candidate_count": len(candidates),
        "development_period": "2024-01-01T00:00:00Z/2025-04-01T00:00:00Z",
        "validation_period": "2025-04-01T00:00:00Z/2026-01-01T00:00:00Z_SEALED_DURING_STAGE1",
        "final_holdout": "2026_ROWS_SEALED_SINGLE_USE",
        "entry": "next causally available M5 executable ask for long or bid for short",
        "exit": "first executable 1.0 ATR20 stop, 2.0R target, or completed 15/30/60-minute time exit",
        "costs": {"base": "observed bid/ask plus 0.10 pip adverse slippage per side", "stress": "observed bid/ask plus 0.50 pip adverse slippage per side", "financing": "apply only if a position crosses a certified financing boundary", "entry_delay": "finalist-only S5/S10/S15/S30 and M1/M2/M4 sensitivity on the certified three-pair scope"},
        "baselines": ["NO_TRADE_ZERO", "MATCHED_RANDOM_DIRECTION", "MATCHED_25_75_ARBITRARY_LEVEL", "GENERIC_BREAKOUT", "GENERIC_MEAN_REVERSION", "UNGATED_CANDIDATE_BEFORE_ANY_REGIME_FILTER"],
        "stage1_rejection": ["NO_GROSS_PREDICTIVE_EVIDENCE", "NO_PLAUSIBLE_REALISTIC_COST_PATH", "FAILS_MATCHED_ARBITRARY_LEVEL", "FAILS_RANDOM_DIRECTION", "INSUFFICIENT_PAIR_OR_CURRENCY_BREADTH", "DIRECTION_SESSION_OR_REGIME_CONCENTRATION", "LEAKAGE"],
        "preholdout_gates": {"after_cost_expectancy": ">0", "profit_factor": ">=1.10", "maximum_drawdown_pct": "<=10", "trades": ">=200", "long_trades_if_enabled": ">=50", "short_trades_if_enabled": ">=50", "contributing_instruments": ">=2", "walk_forward": "PASS", "cost_stress": "PASS", "parameter_stability": "PASS", "leakage": "PASS", "concentration": "PASS", "baseline": "PASS", "multiple_testing": "PASS_GLOBAL_HISTORY", "two_run_reproduction": "BYTE_IDENTICAL"},
        "folds": {"count": 6, "construction": "chronological development folds", "purge": "remove every event whose entry or exit crosses a fold boundary", "embargo": "12 M5 bars"},
        "multiple_testing": {"attempt_lower_bound_before": CURRENT_ATTEMPT_LOWER_BOUND, "governed_candidates_before": CURRENT_GOVERNED_CANDIDATES, "stage0_increment": 0, "stage1_increment_if_all_configurations_scored": len(candidates), "global_PBO_or_deflated_Sharpe_equivalent_required": True},
        "journal_fields": ["strategy_id", "candidate_id", "candidate_fingerprint", "pair", "direction", "level", "level_class", "signal_timestamp", "decision_timestamp", "entry_timestamp", "entry_price", "exit_timestamp", "exit_price", "stop_loss", "take_profit", "spread", "slippage", "gross_result", "net_result", "result_r", "entry_reason", "exit_reason", "session", "volatility_regime", "trend_range_regime", "economic_event_proximity", "every_filter_result"],
        "reproduction_command": "python -B scripts/forex_delivery/run_forex_round_number_conditional_order_state_stage1_v1.py run --output-root .aios/staging/PKT_FOREX_038/run1",
        "market_outcomes_read": False,
    }
    prereg["strategy_mechanism_fingerprint"] = selected["mechanism_fingerprint"]
    prereg["preregistration_sha256"] = sha256_bytes(canonical_bytes(prereg))
    return prereg


def build_stage0(rejection_paths: list[Path], repo_root: Path) -> dict[str, bytes]:
    memory = reconcile_memory(rejection_paths, repo_root)
    closure = closure_audit(repo_root)
    datasets = resolve_certified_datasets(repo_root)
    memory["prior_factory_snapshot"] = dict(memory["current_governed_lineage"])
    memory["verified_current_state"] = {"actual_computational_attempt_lower_bound": CURRENT_ATTEMPT_LOWER_BOUND, "governed_after_cost_candidates": CURRENT_GOVERNED_CANDIDATES, "source_checkpoint_sha256": PRIOR_COMPLETION_SHA256}
    memory["conservative_nonoverlapping_computational_attempt_lower_bound"] = CURRENT_ATTEMPT_LOWER_BOUND
    memory["fully_governed_after_cost_trial_count"] = CURRENT_GOVERNED_CANDIDATES
    descriptor = catalog_descriptor()
    if descriptor["cardinality"] != CATALOG_SIZE:
        raise ValueError("CATALOG_CARDINALITY_MISMATCH")
    chunks = catalog_chunk_hashes(descriptor["descriptor_sha256"])
    if len(chunks) != 245 or chunks[-1]["count"] != 576:
        raise ValueError("CATALOG_CHUNK_PROOF_MISMATCH")
    catalog = dict(descriptor)
    catalog.update({
        "chunk_size": CHUNK_SIZE, "chunk_count": len(chunks), "last_chunk_count": chunks[-1]["count"],
        "chunk_hashes": chunks, "chunk_chain_sha256": sha256_bytes(canonical_bytes([row["sha256"] for row in chunks])),
        "boundary_examples": [spec_at(0), spec_at(1), spec_at(CATALOG_SIZE // 2), spec_at(CATALOG_SIZE - 1)],
    })
    clusters = cluster_rows()
    sources = {"schema": "AIOS_FOREX_HYPOTHESIS_SOURCE_REGISTRY.v1", "proof_role": "HYPOTHESIS_ONLY_NOT_EDGE_EVIDENCE", "sources": public_sources()}
    prereg = successor_preregistration(memory, clusters, datasets)
    capabilities = factory_capabilities()
    contract = {
        "schema": "AIOS_FOREX_HIGH_THROUGHPUT_EDGE_FACTORY_CONTRACT.v2", "packet_id": PACKET_ID,
        "stage": 0, "market_outcomes_read": False, "catalog_items_scored": 0,
        "funnel": ["STAGE0_NO_DATA_DUPLICATE_AND_ELIGIBILITY", "STAGE1_CHEAP_MECHANISM_SCREEN", "STAGE2_COST_SURVIVABILITY", "STAGE3_CHRONOLOGICAL_VALIDATION", "STAGE4_COMPLETE_PREHOLDOUT", "STAGE5_SINGLE_USE_FINAL_HOLDOUT"],
        "edge_gates": {"after_cost_expectancy": ">0", "profit_factor": ">=1.10", "maximum_drawdown_pct": "<=10", "trades": ">=200", "holdout": "SEALED_UNTIL_ONE_PREHOLDOUT_CHAMPION"},
        "safety": {key: False for key in ("network", "broker", "credentials", "paper", "practice", "live", "orders", "money_movement", "holdout_access", "commit", "push")},
    }
    checkpoint = {
        "schema": "AIOS_FOREX_HIGH_THROUGHPUT_EDGE_FACTORY_CHECKPOINT.v2", "status": "STAGE0_COMPLETE_SUCCESSOR_PREREGISTERED",
        "catalog_descriptor_sha256": descriptor["descriptor_sha256"], "catalog_cardinality": CATALOG_SIZE,
        "scored_trial_increment": 0, "global_attempt_lower_bound": CURRENT_ATTEMPT_LOWER_BOUND, "governed_after_cost_candidates": CURRENT_GOVERNED_CANDIDATES,
        "selected_successor": prereg["strategy_identity"], "selected_successor_sha256": prereg["preregistration_sha256"],
        "holdout_evaluations": 0, "pending_candidate_ids": [row["candidate_id"] for row in prereg["parameter_grid"]], "next_action": "REQUEST_EXACT_PKT_FOREX_038_STAGE1_WRITE_AUTHORITY_AFTER_OCC72_RELEASE",
    }
    report = (
        "# AIOS Forex High-Throughput Edge Factory V1\n\n"
        "Stage 0 built a compact, fully reconstructable 1,000,000-item hypothesis catalog without reading market outcomes. "
        "The catalog added zero scored trials. Current governed memory is preserved at 1,220 actual-attempt lower bound and 168 governed after-cost candidates. "
        "All 58 certified M5 pairs and their authoritative instrument precision metadata passed the no-outcome eligibility gate. "
        "The round-number approach-rejection and completed-cross states are frozen as 135 configurations but remain unscored. "
        "The final holdout remains sealed.\n"
    ).encode("utf-8")
    core = {
        "AIOS_FOREX_EDGE_FACTORY_CONTRACT.json": pretty_bytes(contract),
        "AIOS_FOREX_HYPOTHESIS_CATALOG.json": pretty_bytes(catalog),
        "AIOS_FOREX_HYPOTHESIS_SOURCE_REGISTRY.json": pretty_bytes(sources),
        "AIOS_FOREX_GLOBAL_EXPERIMENT_MEMORY.json": pretty_bytes(memory),
        "AIOS_FOREX_PACKET_CLOSURE_AUDIT.json": pretty_bytes(closure),
        "AIOS_FOREX_IMMUTABLE_DATASET_RESOLVER.json": pretty_bytes(datasets),
        "AIOS_FOREX_EDGE_FACTORY_CAPABILITY_MATRIX.json": pretty_bytes(capabilities),
        "AIOS_FOREX_MECHANISM_CLUSTER_RANKING.json": pretty_bytes({"schema": "AIOS_FOREX_MECHANISM_CLUSTER_RANKING.v1", "clusters": clusters}),
        "AIOS_FOREX_ROUND_NUMBER_SUCCESSOR_PREREGISTRATION.json": pretty_bytes(prereg),
        "AIOS_FOREX_EDGE_FACTORY_CHECKPOINT.json": pretty_bytes(checkpoint),
        "AIOS_FOREX_EDGE_FACTORY_V1_REPORT.md": report,
    }
    manifest = {"schema": "AIOS_FOREX_EDGE_FACTORY_MANIFEST.v1", "artifacts": {name: {"bytes": len(content), "sha256": sha256_bytes(content)} for name, content in sorted(core.items())}}
    manifest_bytes = pretty_bytes(manifest)
    receipt = {
        "schema": "AIOS_FOREX_EDGE_FACTORY_RECEIPT.v2", "packet_id": PACKET_ID, "status": "PASS",
        "manifest_sha256": sha256_bytes(manifest_bytes), "artifact_count": len(core) + 2,
        "acceptance": {"catalog_cardinality_1000000": "PASS", "catalog_not_materialized": "PASS", "five_direction_variants": "PASS", "inverse_involution": "PASS", "chunk_proof_245_last_576": "PASS", "packet_019_036_closure": closure["status"], "current_counts_1220_168": "PASS", "exact_58_pair_dataset_resolver": datasets["status"], "authoritative_instrument_precision": "PASS", "candidate_grid_135": "PASS", "proposal_trial_increment_zero": "PASS", "public_sources_hypothesis_only": "PASS", "successor_preregistered_not_scored": "PASS", "holdout_sealed": "PASS", "safety_flags_false": "PASS", "factory_capability_contract": capabilities["status"]},
        "safety": contract["safety"],
    }
    return {**core, "AIOS_FOREX_EDGE_FACTORY_MANIFEST.json": manifest_bytes, "AIOS_FOREX_EDGE_FACTORY_RECEIPT.json": pretty_bytes(receipt)}
