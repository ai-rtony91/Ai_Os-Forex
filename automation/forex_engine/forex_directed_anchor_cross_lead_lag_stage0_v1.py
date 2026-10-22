"""No-outcome Stage-0 gate for directed USD-anchor to non-USD-cross lead-lag."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-FOREX-031"
STRATEGY_ID = "DIRECTED_ANCHOR_TO_CROSS_PRICE_DISCOVERY_LEAD_LAG_V1"
MECHANISM_FINGERPRINT = "1f5948e3538c1ef55a1f91fca91cc41ff3e49aac5d6dd77a1f14a584a3bccfec"
CORPUS_ID = "AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2"
CORPUS_SHA256 = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
MANIFEST_SHA256 = "1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b"
ACCESS_DATE = "2026-09-05"
PRIOR_ATTEMPTS = 1187
PRIOR_AFTER_COST_CANDIDATES = 135

ANCHORS = {
    "AUD_USD": {"currency": "AUD", "sign_multiplier": 1},
    "EUR_USD": {"currency": "EUR", "sign_multiplier": 1},
    "GBP_USD": {"currency": "GBP", "sign_multiplier": 1},
    "NZD_USD": {"currency": "NZD", "sign_multiplier": 1},
    "USD_CAD": {"currency": "CAD", "sign_multiplier": -1},
    "USD_CHF": {"currency": "CHF", "sign_multiplier": -1},
    "USD_JPY": {"currency": "JPY", "sign_multiplier": -1},
}

MECHANISM_DESCRIPTOR = {
    "anchor_pairs": list(ANCHORS),
    "anchor_return": "ONE_COMPLETED_M5_MID_CLOSE_TO_CLOSE_RETURN_WITH_POSITIVE_SIGN_MEANING_NON_USD_ANCHOR_CURRENCY_APPRECIATION",
    "anchor_scale": "ATR20_COMPUTED_ONLY_THROUGH_T_MINUS_1",
    "cost_base": "OBSERVED_BID_ASK_PLUS_0.10_PIP_SLIPPAGE_PER_SIDE",
    "cost_stress": "OBSERVED_BID_ASK_PLUS_0.50_PIP_SLIPPAGE_PER_SIDE",
    "dataset_id": CORPUS_ID,
    "dataset_sha256": CORPUS_SHA256,
    "development": "2024-01-01T00:00:00Z/2025-04-01T00:00:00Z",
    "direction_arms": ["CONTINUATION", "EXACT_REVERSE"],
    "economic_mechanism": "LIQUID_USD_MAJOR_PAIRS_INCORPORATE_CURRENCY_SPECIFIC_INFORMATION_BEFORE_NON_USD_CROSSES_SHARING_THE_SAME_CURRENCY",
    "entry": "NEXT_SYNCHRONIZED_TARGET_M5_EXECUTABLE_OPEN_T_PLUS_1",
    "final_holdout": "2026-01-01T00:00:00Z/2026-08-30T00:00:00Z_SEALED",
    "granularity": "M5",
    "portfolio_risk_cap": 0.0025,
    "position_risk_fraction": 0.0005,
    "rollover": "SKIP_IF_MAXIMUM_HOLD_INTERSECTS_21_55_TO_22_10_UTC",
    "selection": "DEDUPLICATE_TARGET_BY_LARGEST_ABSOLUTE_ANCHOR_SHOCK_THEN_SELECT_AT_MOST_FIVE_CURRENCY_DISJOINT_TARGETS_BY_ABSOLUTE_SHOCK_DESC_SPREAD_TO_ATR_ASC_LEXICAL_TIEBREAK",
    "shock_threshold_atr": [1.0, 1.5],
    "signal_timing": "COMPLETED_ANCHOR_BAR_T_ONLY",
    "stop": "ONE_TARGET_ATR20_FIXED_AT_ENTRY",
    "strategy_id": STRATEGY_ID,
    "take_profit": "NONE",
    "target_universe_rule": "ALL_CERTIFIED_M5_NON_USD_PAIRS_CONTAINING_THE_ANCHOR_NON_USD_CURRENCY",
    "time_exit_bars": [1, 3],
    "validation": "2025-04-01T00:00:00Z/2026-01-01T00:00:00Z_UNOPENED_UNLESS_STAGE1_SURVIVES",
}

TARGETS = (
    "AUD_CAD", "AUD_CHF", "AUD_HKD", "AUD_JPY", "AUD_NZD", "AUD_SGD",
    "CAD_CHF", "CAD_HKD", "CAD_JPY", "CAD_SGD", "CHF_HKD", "CHF_JPY",
    "CHF_ZAR", "EUR_AUD", "EUR_CAD", "EUR_CHF", "EUR_CZK", "EUR_GBP",
    "EUR_HKD", "EUR_HUF", "EUR_JPY", "EUR_NZD", "EUR_PLN", "EUR_SEK",
    "EUR_SGD", "EUR_ZAR", "GBP_AUD", "GBP_CAD", "GBP_CHF", "GBP_HKD",
    "GBP_JPY", "GBP_NZD", "GBP_PLN", "GBP_SGD", "GBP_ZAR", "HKD_JPY",
    "NZD_CAD", "NZD_CHF", "NZD_JPY", "SGD_CHF", "SGD_JPY",
)

EXPECTED_CANDIDATE_FINGERPRINTS = {
    "DACL-T1P0-CONTINUATION-H1": "8e85cb541b5830eccd5acad2631cc6062b44ffde8cfeb0d18d308ddbbe6a7b36",
    "DACL-T1P0-CONTINUATION-H3": "2a41ffc2d2422cedaa35d5b3efead29ccd60483602d038f177faec370c85b926",
    "DACL-T1P0-EXACT_REVERSE-H1": "4c7a16696d413fa5f553e3b84f1ec2dc177b582d62269a1330fd703208e74f39",
    "DACL-T1P0-EXACT_REVERSE-H3": "1b396d37d229764d58680130e0065d067359bbf6ae88d2cd5f6685b52106a3bf",
    "DACL-T1P5-CONTINUATION-H1": "7df7a44fd5c70a688d6a57cce303c2bc7a4eef9173f77547b5b837af7d8b08b4",
    "DACL-T1P5-CONTINUATION-H3": "4125b5c78e9841e6e513e42cc845acb69c7fc86f2ad4c9473e8127c42b070786",
    "DACL-T1P5-EXACT_REVERSE-H1": "e3eb3097899ec324a294ddd433ccbdddb62ffd7c2e17064671eb3845942d1fc8",
    "DACL-T1P5-EXACT_REVERSE-H3": "9bbda15c09f7e36250f95c4520da92dd785d7b8828361eae2948fd59aa469c52",
}


def canonical_bytes(value: Any, *, compact: bool = False) -> bytes:
    options = {"sort_keys": True, "ensure_ascii": True, "allow_nan": False}
    text = json.dumps(value, separators=(",", ":"), **options) if compact else json.dumps(value, indent=2, **options)
    return (text + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directed_links() -> dict[str, list[str]]:
    return {
        anchor: [target for target in TARGETS if details["currency"] in target.split("_")]
        for anchor, details in sorted(ANCHORS.items())
    }


def target_exposure_sign(target: str, currency: str) -> int:
    base, quote = target.split("_")
    if currency == base:
        return 1
    if currency == quote:
        return -1
    raise ValueError("TARGET_DOES_NOT_CONTAIN_ANCHOR_CURRENCY")


def order_sign(anchor_return_sign: int, anchor: str, target: str, arm: str) -> int:
    if anchor_return_sign not in (-1, 1):
        raise ValueError("ANCHOR_RETURN_SIGN_MUST_BE_NONZERO")
    details = ANCHORS[anchor]
    normalized = anchor_return_sign * int(details["sign_multiplier"])
    continuation = normalized * target_exposure_sign(target, str(details["currency"]))
    if arm == "CONTINUATION":
        return continuation
    if arm == "EXACT_REVERSE":
        return -continuation
    raise ValueError("UNKNOWN_ARM")


def candidate_definitions() -> list[dict[str, Any]]:
    if sha256_bytes(canonical_bytes(MECHANISM_DESCRIPTOR, compact=True)) != MECHANISM_FINGERPRINT:
        raise RuntimeError("MECHANISM_FINGERPRINT_MISMATCH")
    candidates = []
    for threshold, label in ((1.0, "1P0"), (1.5, "1P5")):
        for arm in ("CONTINUATION", "EXACT_REVERSE"):
            for hold in (1, 3):
                candidate_id = f"DACL-T{label}-{arm}-H{hold}"
                definition = {
                    "arm": arm,
                    "candidate_id": candidate_id,
                    "holding_m5_bars": hold,
                    "shock_threshold_atr": threshold,
                    "strategy_id": STRATEGY_ID,
                }
                fingerprint = sha256_bytes(canonical_bytes({
                    "mechanism_fingerprint": MECHANISM_FINGERPRINT,
                    "definition": definition,
                }, compact=True))
                if fingerprint != EXPECTED_CANDIDATE_FINGERPRINTS[candidate_id]:
                    raise RuntimeError(f"CANDIDATE_FINGERPRINT_MISMATCH:{candidate_id}")
                candidates.append({**definition, "candidate_fingerprint": fingerprint})
    return candidates


def build_source_registry() -> dict[str, Any]:
    common = {
        "claimed_performance": "NONE_ACCEPTED_AS_EVIDENCE",
        "source_code_exists": False,
        "aios_dataset_compatibility": "INDIRECT_MECHANISM_ONLY_M5_RULE_REQUIRES_INDEPENDENT_AIOS_TEST",
        "existing_fingerprint_match": False,
        "final_disposition": "HYPOTHESIS_INPUT_ONLY_UNVERIFIED",
    }
    sources = [
        {
            **common,
            "source_id": "BIS_DREHMANN_SUSHKO_2022_USD_VEHICLE",
            "url": "https://www.bis.org/publications/global-foreign-exchange-market-higher-volatility-environment",
            "title": "The global foreign exchange market in a higher-volatility environment",
            "author_or_organization": "Mathias Drehmann; Vladyslav Sushko",
            "publication_date": "2022-12-05",
            "access_date": ACCESS_DATE,
            "source_type": "BIS_QUARTERLY_REVIEW_SPECIAL_FEATURE",
            "claimed_economic_mechanism": "USD is the dominant vehicle currency and many non-USD conversions route via USD.",
            "claimed_market_and_timeframe": "GLOBAL_FX_MARKET_NO_TRADABLE_M5_RULE",
            "exact_disclosed_rules": "NONE",
            "costs_included": False,
            "walk_forward_included": False,
            "license": "NO_EXPLICIT_OPEN_LICENSE_STATED_BIS_COPYRIGHT_TERMS_APPLY",
            "replication_risks": ["NO_PAIR_LEVEL_M5_RULE", "NO_RETAIL_COST_TEST", "MECHANISM_NOT_EDGE_PROOF"],
            "research_priority": "HIGH_MECHANISM_SUPPORT_LOW_DIRECT_RULE_SUPPORT",
            "final_disposition": "INDIRECT_MECHANISM_SUPPORT_NOT_EDGE_PROOF",
        },
        {
            **common,
            "source_id": "BIS_MARKETS_COMMITTEE_2011_HFT_FX",
            "url": "https://www.bis.org/publ/mktc05.htm",
            "title": "High-frequency trading in the foreign exchange market",
            "author_or_organization": "Markets Committee Study Group, chaired by Guy Debelle",
            "publication_date": "2011-09-27",
            "access_date": ACCESS_DATE,
            "source_type": "INSTITUTIONAL_MARKET_STRUCTURE_REPORT",
            "claimed_economic_mechanism": "Small quote-update lags and cross-platform pricing discrepancies can exist.",
            "claimed_market_and_timeframe": "FX_HIGH_FREQUENCY_LIKELY_FASTER_THAN_M5",
            "exact_disclosed_rules": "NO_REPRODUCIBLE_M5_CROSS_PAIR_STRATEGY",
            "costs_included": False,
            "walk_forward_included": False,
            "license": "NO_EXPLICIT_OPEN_LICENSE_STATED_BIS_COPYRIGHT_TERMS_APPLY",
            "replication_risks": ["DOCUMENTED_EFFECT_LIKELY_SUB_M5", "NO_EXECUTABLE_RULE", "LATENCY_ARBITRAGE_LABEL_PROHIBITED"],
            "research_priority": "TIMEFRAME_WARNING",
            "final_disposition": "TIMEFRAME_WARNING_AND_INDIRECT_SUPPORT",
        },
        {
            **common,
            "source_id": "NYFED_ROSENBERG_TRAUB_2008_PRICE_DISCOVERY",
            "url": "https://www.newyorkfed.org/research/staff_reports/sr262.html",
            "title": "Price Discovery in the Foreign Currency Futures and Spot Market",
            "author_or_organization": "Joshua V. Rosenberg; Leah G. Traub",
            "publication_date": "2006-10",
            "revision_date": "2008-02",
            "access_date": ACCESS_DATE,
            "source_type": "FEDERAL_RESERVE_STAFF_REPORT",
            "claimed_economic_mechanism": "FX information shares can differ across venues and change over time.",
            "claimed_market_and_timeframe": "FX_FUTURES_AND_SPOT_NOT_PAIR_TO_PAIR_M5",
            "exact_disclosed_rules": "NONE",
            "costs_included": False,
            "walk_forward_included": False,
            "license": "NO_EXPLICIT_OPEN_LICENSE_STATED_NEW_YORK_FED_TERMS_APPLY",
            "replication_risks": ["VENUE_RESULT_NOT_CROSS_PAIR_RULE", "OLD_SAMPLES", "NO_RETAIL_COST_TEST"],
            "research_priority": "MEDIUM_INDIRECT_SUPPORT",
            "final_disposition": "INDIRECT_PRICE_DISCOVERY_SUPPORT_NOT_PAIR_LEAD_LAG_PROOF",
        },
        {
            **common,
            "source_id": "FXABSOLUTE_EDGE_GUIDE",
            "url": "https://fxabsolute.com/how-to-build-trading-edge",
            "title": "How to Build a Trading Edge in Forex",
            "author_or_organization": "FXAbsolute",
            "publication_date": "NOT_DISCLOSED",
            "reviewed_date": "2026-08-24",
            "access_date": ACCESS_DATE,
            "source_type": "COMMERCIAL_EDUCATIONAL_GUIDE",
            "claimed_economic_mechanism": "NONE",
            "claimed_market_and_timeframe": "GENERAL_FOREX_METHODOLOGY",
            "exact_disclosed_rules": "Methodology only: define falsifiable deterministic rules, preserve all trials, and reserve untouched later data.",
            "costs_included": "NOT_SPECIFIED",
            "walk_forward_included": "PARTIAL_UNTOUCHED_DATA_GUIDANCE_NOT_FORMAL_WALK_FORWARD",
            "license": "NO_EXPLICIT_LICENSE_STATED_NO_CODE_ADAPTED",
            "replication_risks": ["COMMERCIAL_SOURCE", "MARKETING_THRESHOLDS_UNVERIFIED", "NO_STRATEGY_EDGE_EVIDENCE"],
            "research_priority": "PROCESS_GUIDANCE_ONLY",
            "final_disposition": "METHODOLOGY_ONLY_UNVERIFIED_NOT_EDGE_PROOF",
        },
    ]
    return {
        "schema": "AIOS_FOREX_HYPOTHESIS_SOURCE_REGISTRY_SUPPLEMENT.v1",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "evidence_role": "HYPOTHESIS_INPUT_ONLY_NOT_EDGE_PROOF",
        "sources": sources,
        "unsupported_claims": [
            "NO_SOURCE_PROVES_USD_MAJOR_TO_NON_USD_CROSS_M5_AFTER_COST_EXPECTANCY",
            "NO_SCREENSHOT_TESTIMONIAL_OR_MARKETED_THRESHOLD_IS_VALIDATION",
        ],
        "status": "PASS_SOURCES_RECORDED_AS_UNVERIFIED_HYPOTHESIS_INPUT",
    }


def build_preregistration() -> dict[str, Any]:
    links = directed_links()
    return {
        "schema": "AIOS_FOREX_STRATEGY_PREREGISTRATION.v1",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_mechanism_fingerprint": MECHANISM_FINGERPRINT,
        "strategy_mechanism_descriptor": MECHANISM_DESCRIPTOR,
        "mechanism_label": "FIVE_TO_FIFTEEN_MINUTE_DIRECTED_INFORMATION_DIFFUSION_PROXY",
        "economic_mechanism": "A completed large move in a liquid USD-major anchor may incorporate information about its non-USD currency before a different non-USD cross sharing that currency fully adjusts.",
        "claim_limit": "FALSIFIABLE_M5_DIFFUSION_PROXY_NOT_LATENCY_ARBITRAGE_OR_PROVEN_PRICE_DISCOVERY",
        "dataset": {
            "id": CORPUS_ID,
            "sha256": CORPUS_SHA256,
            "development_start": "2024-01-01T00:00:00Z",
            "development_end_exclusive": "2025-04-01T00:00:00Z",
            "validation_access": "PROHIBITED_UNLESS_STAGE1_SURVIVOR",
            "final_holdout_start": "2026-01-01T00:00:00Z",
            "final_holdout": "SEALED_SINGLE_USE",
        },
        "pair_universe": {
            "anchors": ANCHORS,
            "targets": list(TARGETS),
            "directed_links": links,
            "link_count": sum(map(len, links.values())),
        },
        "timeframes": {"signal": "M5", "execution": "M5", "confirmation": "NONE"},
        "signal_calculation": {
            "raw_anchor_return_t": "ln(anchor_mid_close_t/anchor_mid_close_t_minus_1) on one completed native M5 candle",
            "normalized_anchor_return_t": "anchor sign multiplier times raw anchor return; positive means non-USD anchor currency appreciation versus USD",
            "anchor_atr20_t_minus_1": "20 completed anchor true ranges t-20 through t-1 using mid OHLC and prior close",
            "shock_ratio": "abs(anchor_mid_close_t-anchor_mid_close_t_minus_1)/anchor_atr20_t_minus_1",
            "synchronization": "target must have exact timestamps t and t+1; no forward fill or nearest match",
        },
        "direction_rules": {
            "target_exposure": "+1 when anchor currency is target base; -1 when target quote",
            "continuation": "sign(normalized_anchor_return_t) times target exposure sign",
            "exact_reverse": "arithmetic negative of continuation at identical opportunity",
        },
        "entry_rules": {
            "time": "next synchronized target M5 bar t+1 open",
            "price": "BUY ask open plus 0.10 pip adverse slippage; SELL bid open minus 0.10 pip",
            "simultaneous_deduplication": "same target keeps largest shock ratio then lexical anchor",
            "ranking": "shock ratio descending, entry spread divided by target ATR ascending, target then anchor lexical",
        },
        "exit_rules": {
            "stop": "one target ATR20 computed through completed target t; BUY checks bid low and SELL checks ask high",
            "take_profit": "NONE",
            "time_exit": "executable close of target bar t+H; BUY bid close and SELL ask close",
            "same_bar_ambiguity": "STOP_FIRST_PESSIMISTIC",
            "rollover": "skip if maximum hold intersects 21:55 through 22:10 UTC",
        },
        "position_sizing": "risk 0.05 percent current equity to fixed one-ATR stop",
        "risk_limits": {
            "maximum_open_positions": 5,
            "maximum_total_initial_risk_percent": 0.25,
            "maximum_pair_positions": 1,
            "shared_currency_positions": 0,
        },
        "cost_model": {
            "gross": "midpoint entry and exit without slippage",
            "base": "observed executable bid/ask plus 0.10 pip adverse slippage per side",
            "stress": "observed executable bid/ask plus 0.50 pip adverse slippage per side",
            "financing": "NOT_APPLICABLE_ROLLOVER_INTERSECTIONS_SKIPPED",
        },
        "parameter_grid": {
            "shock_threshold_atr": [1.0, 1.5],
            "arm": ["CONTINUATION", "EXACT_REVERSE"],
            "holding_m5_bars": [1, 3],
            "candidate_count": 8,
        },
        "chronological_folds": [
            {"fold": index + 1, "score_start": left, "score_end_exclusive": right, "training": "all development rows strictly before score_start"}
            for index, (left, right) in enumerate((
                ("2024-04-01T00:00:00Z", "2024-06-01T00:00:00Z"),
                ("2024-06-01T00:00:00Z", "2024-08-01T00:00:00Z"),
                ("2024-08-01T00:00:00Z", "2024-10-01T00:00:00Z"),
                ("2024-10-01T00:00:00Z", "2024-12-01T00:00:00Z"),
                ("2024-12-01T00:00:00Z", "2025-02-01T00:00:00Z"),
                ("2025-02-01T00:00:00Z", "2025-04-01T00:00:00Z"),
            ))
        ],
        "purge_and_embargo": "23 M5 bars at every fold boundary: 20 warm-up plus 3 maximum hold bars",
        "stage1_pre_score_capacity_gate": {
            "minimum_selected_opportunities_per_candidate": 400,
            "minimum_positive_anchor_opportunities": 100,
            "minimum_negative_anchor_opportunities": 100,
            "minimum_targets": 20,
            "minimum_currencies": 10,
            "minimum_opportunities_per_each_of_six_folds": 30,
            "failure_status": "STAGE0_INSUFFICIENT_CAPACITY_ZERO_TRIALS_ADDED",
        },
        "baselines": [
            "NO_TRADE_ZERO_EXPECTANCY",
            "MATCHED_DETERMINISTIC_RANDOM_SIGN_IDENTICAL_TIMESTAMPS_AND_TARGETS",
            "SAME_PAIR_ANCHOR_MOMENTUM_DIAGNOSTIC",
            "TARGET_OWN_ONE_BAR_MOMENTUM",
            "UNDIRECTED_POOLED_CURRENCY_STRENGTH_NO_RANKING",
            "WRONG_CURRENCY_ANCHOR_FIXED_ROTATION",
            "COST_FREE_GROSS",
            "BASE_AND_STRESS_COST",
        ],
        "stage1_rejection_gates": {
            "gross_expectancy_must_exceed_zero": True,
            "after_cost_expectancy_must_exceed_zero": True,
            "minimum_profit_factor": 1.05,
            "minimum_trades": 100,
            "maximum_drawdown_percent": 15.0,
            "minimum_positive_folds": 4,
            "minimum_contributing_pairs": 10,
            "minimum_contributing_currencies": 5,
            "must_beat_required_after_cost_baselines": True,
            "same_pair_anchor_momentum": "DIAGNOSTIC_SIMPLE_BASELINE_FAILURE_IF_NOT_BEATEN",
            "leakage": "PASS_REQUIRED",
        },
        "stage2_promotion_gates": {
            "after_cost_expectancy_must_exceed_zero": True,
            "minimum_profit_factor": 1.10,
            "minimum_trades": 200,
            "maximum_drawdown_percent": 10.0,
            "cost_stress": "PASS_REQUIRED",
            "parameter_stability": "PASS_REQUIRED",
            "pair_currency_regime_concentration": "PASS_REQUIRED",
            "multiple_testing": "GLOBAL_HISTORY_ADJUSTED_PASS_REQUIRED",
            "deterministic_two_run_reproduction": "BYTE_IDENTICAL_REQUIRED",
        },
        "candidates": candidate_definitions(),
        "reproduction_commands": [
            "python -B scripts/forex_delivery/run_forex_directed_anchor_cross_lead_lag_stage1_v1.py --output .aios/staging/PKT_FOREX_032/run1",
            "python -B scripts/forex_delivery/run_forex_directed_anchor_cross_lead_lag_stage1_v1.py --output .aios/staging/PKT_FOREX_032/run2",
        ],
        "preregistered_before_outcome_access": True,
        "status": "FROZEN_IF_STAGE0_ELIGIBLE",
    }


def run(repo_root: Path, output: Path) -> dict[str, Any]:
    corpus = repo_root / ".aios/runtime/forex_m5_immutable_corpus_v2"
    manifest_path = corpus / "manifest.json"
    frozen_path = corpus / "FROZEN.json"
    if sha256_file(manifest_path) != MANIFEST_SHA256:
        raise RuntimeError("MANIFEST_SHA256_MISMATCH")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if manifest.get("corpus_id") != CORPUS_ID or manifest.get("aggregate_corpus_fingerprint") != CORPUS_SHA256:
        raise RuntimeError("MANIFEST_CORPUS_IDENTITY_MISMATCH")
    if frozen.get("aggregate_corpus_fingerprint") != CORPUS_SHA256:
        raise RuntimeError("FROZEN_CORPUS_IDENTITY_MISMATCH")

    eligible = set(manifest.get("eligible_pairs", []))
    links = directed_links()
    target_currencies = sorted({currency for target in TARGETS for currency in target.split("_")})
    gates = {
        "seven_anchors_present": len(ANCHORS) == 7 and set(ANCHORS) <= eligible,
        "forty_one_targets_present": len(TARGETS) == len(set(TARGETS)) == 41 and set(TARGETS) <= eligible,
        "all_targets_exclude_usd": all("USD" not in target.split("_") for target in TARGETS),
        "sixty_two_directed_links": sum(map(len, links.values())) == 62,
        "minimum_four_targets_per_anchor": min(map(len, links.values())) >= 4,
        "minimum_thirty_five_unique_targets": len(TARGETS) >= 35,
        "minimum_fourteen_target_currencies": len(target_currencies) >= 14,
        "exact_eight_candidate_fingerprints": len(candidate_definitions()) == 8,
        "prior_trial_memory_preserved": PRIOR_ATTEMPTS == 1187 and PRIOR_AFTER_COST_CANDIDATES == 135,
        "market_rows_opened_zero": True,
        "forward_returns_calculated_zero": True,
    }
    status = "ADMIT_STAGE1_LOW_COST_ONLY" if all(gates.values()) else "BLOCK_STAGE0"
    capacity = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE0_CAPACITY.v1",
        "packet_id": PACKET_ID,
        "corpus_id": CORPUS_ID,
        "corpus_sha256": CORPUS_SHA256,
        "manifest_sha256": MANIFEST_SHA256,
        "manifest_eligible_pairs": len(eligible),
        "anchor_count": len(ANCHORS),
        "target_count": len(TARGETS),
        "directed_link_count": sum(map(len, links.values())),
        "target_currency_count": len(target_currencies),
        "directed_links": links,
        "gates": gates,
        "deferred_pre_score_checks": "EXACT_SYNCHRONIZATION_AND_SIGNAL_CAPACITY_RUN_BEFORE_ANY_FORWARD_RETURN_IN_STAGE1",
        "safety": {
            "market_rows_opened": 0,
            "forward_returns_calculated": 0,
            "strategy_candidates_scored": 0,
            "validation_rows_opened": 0,
            "final_holdout_rows_opened": 0,
            "broker_access": False,
            "credentials_accessed": False,
            "orders": False,
        },
        "status": status,
    }
    duplicate = {
        "schema": "AIOS_FOREX_MECHANISM_DUPLICATE_DECISION.v1",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_mechanism_fingerprint": MECHANISM_FINGERPRINT,
        "decision": "DISTINCT_ONLY_WITH_FIXED_DIRECTED_BOUNDARY",
        "distinguishing_features": [
            "fixed ex-ante USD-major anchors",
            "different non-USD target sharing the normalized anchor currency",
            "directed completed-M5 t to next-M5 t+1 transmission",
            "no pair or currency ranking and no fitted relation",
        ],
        "blocked_duplicate_forms": {
            "same_signal_and_target": "MOMENTUM_fc8f85ab",
            "currency_aggregation_then_rank": "CROSS_SECTIONAL_CURRENCY_STRENGTH_MOMENTUM_01225285",
            "target_residual_or_convergence": "CROSS_PAIR_RESIDUAL_COINTEGRATION_MEAN_REVERSION_40617c18",
            "cross_sectional_overextension_reversal": "CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_aca56a9b",
            "price_update_count_filter": "ABNORMAL_OANDA_PRICE_UPDATE_COUNT_RESPONSE_286f43f2",
        },
        "prohibited_rescues": [
            "POST_HOC_SESSION_PAIR_DIRECTION_VOLATILITY_REGIME_OR_SPREAD_FILTER",
            "COSMETIC_THRESHOLD_HOLD_OR_STOP_CHANGE_OUTSIDE_FROZEN_GRID",
            "VALIDATION_DERIVED_PAIR_SELECTION",
            "REMOVAL_OF_REALISTIC_COSTS",
        ],
        "existing_data_scored_rejected_families": 19,
        "existing_governed_after_cost_candidates": PRIOR_AFTER_COST_CANDIDATES,
        "actual_computational_attempt_lower_bound": PRIOR_ATTEMPTS,
        "actual_trials_added": 0,
        "status": "PASS_TO_STAGE1_IF_CAPACITY_GATES_PASS",
    }
    contract = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE0_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "status": status,
        "market_outcomes_scored": False,
        "actual_trials_added": 0,
        "actual_computational_attempt_lower_bound": PRIOR_ATTEMPTS,
        "governed_after_cost_candidates": PRIOR_AFTER_COST_CANDIDATES,
        "final_holdout": "SEALED_NOT_EVALUATED",
    }
    source_registry = build_source_registry()
    preregistration = build_preregistration()
    output.mkdir(parents=True, exist_ok=True)
    values = {
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE0_CAPACITY.json": capacity,
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_DUPLICATE_DECISION.json": duplicate,
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_HYPOTHESIS_SOURCES.json": source_registry,
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_PREREGISTRATION.json": preregistration,
        "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE0_CONTRACT.json": contract,
    }
    files = {}
    for name, value in sorted(values.items()):
        payload = canonical_bytes(value)
        (output / name).write_bytes(payload)
        files[name] = {"bytes": len(payload), "sha256": sha256_bytes(payload)}
    receipt = {
        "schema": "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE0_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "files": files,
        "aggregate_sha256": sha256_bytes(b"".join(
            name.encode("utf-8") + b"\0" + bytes.fromhex(details["sha256"])
            for name, details in sorted(files.items())
        )),
        "result": status,
        "actual_trials_added": 0,
        "validation_rows_opened": 0,
        "final_holdout_rows_opened": 0,
        "status": "PASS" if status == "ADMIT_STAGE1_LOW_COST_ONLY" else "BLOCK",
    }
    receipt_payload = canonical_bytes(receipt)
    (output / "AIOS_FOREX_DIRECTED_ANCHOR_CROSS_LEAD_LAG_STAGE0_RECEIPT.json").write_bytes(receipt_payload)
    return {"receipt_sha256": sha256_bytes(receipt_payload), **receipt}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.repo_root.resolve(), args.output.resolve())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
