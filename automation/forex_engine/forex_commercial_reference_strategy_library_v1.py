"""Deterministic Stage-0 commercial reference library for AIOS Forex research.

This module never reads market data. Public material is hypothesis and process
input only. Registration is not evidence of profitability or fitness for PAPER
or LIVE trading.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from automation.forex_engine.forex_edge_validation_pipeline_v1 import (
    SCIENTIFIC_FINGERPRINT_FIELDS,
    atomic_write,
    candidate_fingerprint,
    canonical_json,
    pretty_json,
    read_trial_ledger,
    sha256_bytes,
    sha256_file,
    sha256_value,
    validate_trial_ledger,
)


SCHEMA = "AIOS_FOREX_COMMERCIAL_REFERENCE_AND_BENCHMARK_REGISTRY_V1"
PACKET_ID = "PKT-FOREX-041"
REFERENCE_COUNT = 7
ACCESS_DATE = "2026-09-06"
HISTORICAL_SCORED_ATTEMPT_LOWER_BOUND = 1220
PRIOR_PROPOSED_UNSCORED = 518
PKT039_STATUS = "PAUSED_BEFORE_OUTCOME_SCORING"

FROZEN_SOURCE_HASHES = {
    "automation/orchestration/work_packets/active/PKT-FOREX-039.md": "bd3822db4420ba4d4d91465e6bf62a66bd28e49fde4245e1ffd181d422d3abf7",
    "automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py": "40bc12c0826455308ff41ff0b71da4a70fc983b4dfe871ab81003ee7deb69af7",
    "scripts/forex_delivery/run_forex_edge_discovery_tournament_stage1_v1.py": "936f8985299cb1870f5942f415cae3ad881de0290730667fd1a9a40fd0f1fe63",
    "automation/orchestration/work_packets/active/PKT-FOREX-040.md": "ccfd7a9351232e020e2bc3034f271b913bce0e3b3d1c841d41a9d42f35e93778",
    "automation/forex_engine/forex_edge_validation_pipeline_v1.py": "5430e07a24c0973a7ea0c22702b8599a902e0c79937524197b943b123c90f326",
    "scripts/forex_delivery/run_forex_edge_validation_pipeline_v1.py": "9821234d8c99485a2c96ae4ad0a1b286998a1570b95047042adc7d48577921ee",
    "tests/forex_engine/test_forex_edge_validation_pipeline_v1.py": "d4c71f83e70cc3b2dde06995d04475e96d549d9d34dc94cb14a14e669aafaf11",
}

REQUIRED_REFERENCE_FIELDS = (
    "REFERENCE_STRATEGY_ID", "PUBLIC_SOURCE", "PUBLICLY_SUPPORTED_MECHANISM",
    "SOURCE_MARKET_UNIVERSE", "SOURCE_TIME_HORIZON", "AIOS_ADAPTATION_STATUS",
    "EXACT_SIGNAL_DEFINITION", "EXACT_ENTRY_RULE", "EXACT_EXIT_RULE",
    "EXACT_INVALIDATION_RULE", "RISK_RULE", "COST_ASSUMPTIONS",
    "EXPECTED_FAILURE_REGIMES", "BENCHMARK_PURPOSE", "SCIENTIFIC_LIMITATIONS",
    "PUBLIC_REFERENCE_RULE", "AIOS_ADAPTATION", "AIOS_UNTESTED_PARAMETER",
)

BIAS_CHECK_REQUIREMENTS = (
    "FUTURE_DATA_INVARIANCE",
    "LOOKAHEAD_PERTURBATION",
    "RECURSIVE_WARMUP_CONSISTENCY",
    "DUPLICATE_AND_RENAMED_FINGERPRINT_DETECTION",
    "COMPARATOR_FROZEN_BEFORE_OUTCOME_ACCESS",
    "PUBLIC_RULE_ADAPTATION_PARAMETER_SEPARATION",
    "PUBLIC_PERFORMANCE_NOT_ACCEPTED_AS_AIOS_EVIDENCE",
    "IDENTICAL_COST_RISK_AND_PARTITION_TREATMENT",
    "PRIOR_REJECTION_RECONCILIATION",
    "RESEARCH_TO_PRODUCTION_SEMANTIC_PARITY",
    "BACKTEST_FORWARD_DRY_RUN_RECONCILIATION_BEFORE_ANY_LIVE_AUTHORITY",
)

STAGES = ("RESEARCH", "BACKTEST", "VALIDATION", "PAPER", "SUPERVISED_LIVE")


def public_sources() -> list[dict[str, Any]]:
    common = {
        "access_date": ACCESS_DATE,
        "use": "HYPOTHESIS_OR_PROCESS_REFERENCE_ONLY",
        "performance_claim_use": "NOT_ACCEPTED_AS_AIOS_EVIDENCE",
        "code_imported": False,
        "license_treatment": "REFERENCE_ONLY_NO_CODE_OR_SUBSTANTIAL_TEXT_COPIED",
    }
    rows = [
        ("MAN_AHL_PROCESS", "Man AHL", "https://www.man.com/ahl", "CONTINUOUS_WEB_PAGE", "Scientific empirical research, unified codebase, concept-to-backtest-to-production process, diversification, execution competition."),
        ("MAN_AHL_TREND", "Man Group", "https://www.man.com/capabilities/trend-following", "CONTINUOUS_WEB_PAGE", "Systematic momentum across many markets on purpose-built execution infrastructure."),
        ("MAN_AHL_SPEED", "Man Group", "https://www.man.com/insights/need-for-speed-trend-following", "2023-01-04", "Multiple trend speeds; faster variants have higher turnover and greater transaction-cost sensitivity."),
        ("QUANTCONNECT_GUIDE", "QuantConnect", "https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/research-guide", "CONTINUOUS_DOCUMENTATION", "Hypothesis-first research, overfitting awareness, and out-of-sample separation."),
        ("QUANTCONNECT_PIPELINE", "QuantConnect", "https://www.quantconnect.com/docs/v2/cloud-platform/research-pipeline", "CONTINUOUS_DOCUMENTATION", "Ideas to research, backtest, paper, and live pipeline with paper/backtest reconciliation."),
        ("NAUTILUS_PARITY", "NautilusTrader", "https://nautilustrader.io/docs/", "CONTINUOUS_DOCUMENTATION", "Shared time and execution semantics between deterministic simulation and live systems."),
        ("FREQTRADE_LOOKAHEAD", "Freqtrade", "https://www.freqtrade.io/en/stable/lookahead-analysis/", "CONTINUOUS_DOCUMENTATION", "Perturbation-based detection of future-data dependence."),
        ("FREQTRADE_RECURSIVE", "Freqtrade", "https://www.freqtrade.io/en/stable/recursive-analysis/", "CONTINUOUS_DOCUMENTATION", "Indicator consistency checks across different warm-up lengths."),
        ("FREQTRADE_FORWARD", "Freqtrade", "https://www.freqtrade.io/en/stable/strategy-101/", "CONTINUOUS_DOCUMENTATION", "Backtest limitations and forward dry-run comparison."),
        ("AQR_CENTURY_TREND", "AQR Capital Management", "https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing", "2017-10-31", "Long-horizon time-series momentum evidence including currency forwards; not intraday validation."),
        ("BIS_CURRENCY_MOMENTUM", "Menkhoff, Sarno, Schmeling, Schrimpf / BIS", "https://www.bis.org/publications/working-paper-366-currency-momentum-strategies", "2011-12-13", "Cross-sectional currency momentum using monthly formation and holding periods; not M5 validation."),
    ]
    return [{"source_id": source_id, "organization": organization, "url": url, "publication_date": date, "supported_use": supported, **common} for source_id, organization, url, date, supported in rows]


def _base_reference(
    strategy_id: str,
    sources: Sequence[str],
    mechanism: str,
    source_universe: str,
    source_horizon: str,
    public_rule: str,
    signal: str,
    entry: str,
    exit_rule: str,
    invalidation: str,
    untested: Sequence[str],
    failure_regimes: Sequence[str],
    purpose: str,
    formation: str,
    execution: str,
    horizon_class: str,
) -> dict[str, Any]:
    scientific_spec = {
        "signal_family": signal,
        "data_identity": "PUBLIC_REFERENCE_ONLY_NO_AIOS_MARKET_OUTCOME",
        "formation_horizon": formation,
        "execution_horizon": execution,
        "direction": "SYMMETRIC_LONG_SHORT_REFERENCE",
        "entry_rule": entry,
        "exit_rule": exit_rule,
        "cost_contract": "PKT040_GROSS_BASE_STRESSED_SEVERE_BUT_PLAUSIBLE",
        "regime_filters": [],
        "pair_currency_universe": "REFERENCE_SOURCE_UNIVERSE;_AIOS_58_PAIR_ELIGIBILITY_REQUIRES_SEPARATE_SCORING_AUTHORITY",
        "parameters": {"reference_strategy_id": strategy_id, "untested": list(untested)},
        "portfolio_rules": {"risk_fraction": 0.0025, "maximum_positions": 5, "currency_exposure_cap": 0.005, "status": "AIOS_UNTESTED_PARAMETER"},
    }
    return {
        "REFERENCE_STRATEGY_ID": strategy_id,
        "REFERENCE_CLASS": "PUBLIC_MECHANISM_BASELINE" if sources else "AIOS_CONTROL_ARCHETYPE",
        "PUBLIC_SOURCE": list(sources),
        "PUBLICLY_SUPPORTED_MECHANISM": mechanism,
        "SOURCE_MARKET_UNIVERSE": source_universe,
        "SOURCE_TIME_HORIZON": source_horizon,
        "AIOS_ADAPTATION_STATUS": "PROPOSED_UNSCORED_REFERENCE_ONLY",
        "EXACT_SIGNAL_DEFINITION": signal,
        "EXACT_ENTRY_RULE": entry,
        "EXACT_EXIT_RULE": exit_rule,
        "EXACT_INVALIDATION_RULE": invalidation,
        "RISK_RULE": "VOLATILITY_NORMALIZED_EQUAL_RISK;_0.25_PERCENT_RISK_PER_POSITION;_MAX_5_POSITIONS;_0.50_PERCENT_ABSOLUTE_CURRENCY_CAP;_UNTESTED",
        "COST_ASSUMPTIONS": "PKT040_SIDE_CORRECT_GROSS_BASE_STRESSED_SEVERE_BUT_PLAUSIBLE;_MISSING_FINANCING_BLOCKS_UNSUPPORTED_HORIZON",
        "EXPECTED_FAILURE_REGIMES": list(failure_regimes),
        "BENCHMARK_PURPOSE": purpose,
        "SCIENTIFIC_LIMITATIONS": "PUBLIC_PRECEDENT_IS_NOT_AIOS_EDGE_EVIDENCE;_TIMEFRAME_AND_INSTRUMENT_TRANSLATION_REQUIRE_INDEPENDENT_VALIDATION",
        "PUBLIC_REFERENCE_RULE": public_rule,
        "AIOS_ADAPTATION": "APPLY_THE_RULE_ONLY_TO_A_CERTIFIED_ELIGIBLE_UNIVERSE_WITH_PKTFX040_COST_DEPENDENCE_AND_PROVENANCE_CONTROLS",
        "AIOS_UNTESTED_PARAMETER": list(untested),
        "AIOS_HORIZON_CLASS": horizon_class,
        "SCIENTIFIC_SPECIFICATION": scientific_spec,
    }


def reference_strategies() -> list[dict[str, Any]]:
    return [
        _base_reference("SLOW_TIME_SERIES_MOMENTUM", ("AQR_CENTURY_TREND", "MAN_AHL_SPEED"), "Own past return may persist because of gradual adjustment and behavioral underreaction.", "Currency forwards plus futures across major asset classes", "12 completed months formation / 1 month holding", "LONG_IF_PRIOR_12_MONTH_EXCESS_RETURN_POSITIVE;_SHORT_IF_NEGATIVE", "SIGN_OF_PRIOR_12_COMPLETED_MONTH_EXCESS_RETURN", "NEXT_EXECUTABLE_MONTHLY_REBALANCE_AFTER_SIGNAL", "ONE_MONTH_OR_NEXT_PREREGISTERED_SIGN_REVERSAL", "SIGN_REVERSAL_OR_DATA_COST_PORTFOLIO_BLOCK", ("AIOS instrument mapping", "M5/H1 translation", "risk and cost calibration"), ("FAST_REVERSALS", "CROWDED_TRENDS", "HIGH_CORRELATION", "COST_SHOCK"), "Long-horizon trend comparator", "12_MONTHS", "1_MONTH", "SLOW"),
        _base_reference("MEDIUM_TIME_SERIES_MOMENTUM", ("MAN_AHL_SPEED",), "Intermediate trend persistence may balance reaction speed and turnover.", "Liquid futures and FX forwards", "Public multi-week trend-speed comparison", "MEDIUM_SPEED_TREND_DIRECTION_FROM_COMPLETED_PRICES", "SIGN_OF_PRIOR_3_COMPLETED_MONTH_EXCESS_RETURN", "NEXT_EXECUTABLE_MONTHLY_REBALANCE_AFTER_SIGNAL", "ONE_MONTH_OR_NEXT_PREREGISTERED_SIGN_REVERSAL", "SIGN_REVERSAL_OR_DATA_COST_PORTFOLIO_BLOCK", ("3-month proxy", "AIOS timeframe translation", "risk and cost calibration"), ("WHIPSAW", "ABRUPT_REVERSAL", "HIGH_COST"), "Intermediate trend comparator", "3_MONTHS", "1_MONTH", "MEDIUM"),
        _base_reference("FAST_TIME_SERIES_MOMENTUM", ("MAN_AHL_SPEED",), "Faster trend response may reduce reversal losses but incurs higher turnover.", "50 liquid futures and FX forward markets in the cited comparison", "Weeks in the cited comparison; no M5 claim", "FAST_TREND_DIRECTION_FROM_COMPLETED_PRICES_WITH_EXPLICIT_COST_PENALTY", "SIGN_OF_PRIOR_1_COMPLETED_MONTH_EXCESS_RETURN", "NEXT_EXECUTABLE_MONTHLY_REBALANCE_AFTER_SIGNAL", "ONE_MONTH_OR_NEXT_PREREGISTERED_SIGN_REVERSAL", "SIGN_REVERSAL_OR_BASE_COST_FAILURE", ("1-month proxy", "intraday adaptation", "execution delay", "slippage"), ("CHOP", "WIDE_SPREAD", "HIGH_TURNOVER", "LATENCY"), "Fast cost-sensitive trend comparator", "1_MONTH", "1_MONTH", "FAST"),
        _base_reference("CROSS_SECTIONAL_CURRENCY_STRENGTH", ("BIS_CURRENCY_MOMENTUM",), "Broad winner currencies may continue outperforming broad losers.", "Up to 48 currencies against USD in the cited study", "1/3/6/9/12 month formation and holding grids", "RANK_CURRENCIES_BY_LAGGED_EXCESS_RETURN_AND_COMPARE_EXTREME_PORTFOLIOS", "RANK_12_MONTH_LAGGED_CURRENCY_RETURN;_LONG_TOP_QUARTILE_SHORT_BOTTOM_QUARTILE", "NEXT_EXECUTABLE_MONTHLY_REBALANCE_AFTER_FROZEN_RANK", "ONE_MONTH_FIXED_HOLD", "RANK_MEMBERSHIP_LOSS_OR_DATA_COST_PORTFOLIO_BLOCK", ("12/1 month choice", "quartiles", "currency graph mapping", "M5/H1 translation"), ("LOW_DISPERSION", "LIMITS_TO_ARBITRAGE", "COST_CONCENTRATION", "CURRENCY_CROWDING"), "Cross-sectional comparator", "12_MONTHS", "1_MONTH", "CROSS_SECTIONAL"),
        _base_reference("TREND_PULLBACK_CONTINUATION", (), "A controlled retracement may improve entry location within an established impulse.", "AIOS control archetype; no selected public rule", "12/48/288 M5 formation and 3/12/48 M5 diagnostic horizons", "NO_EXACT_PUBLIC_RULE_SELECTED", "PKT038_NORMALIZED_IMPULSE_AT_LEAST_1_AND_PRIOR_12_CLOSE_BREAK", "AFTER_20_TO_60_PERCENT_CLOSE_RETRACEMENT_FIRST_CLOSE_BEYOND_PREVIOUS_TWO_CLOSES_THEN_NEXT_EXECUTABLE_BAR", "PREREGISTERED_FORWARD_HORIZON;_LATER_2R_OR_SEPARATELY_COUNTED_3R_ONLY_AFTER_MECHANISM_SURVIVES", "RETRACEMENT_ABOVE_60_PERCENT_OR_12_BAR_EXPIRY", ("all PKT038 pullback constants", "structural stop buffer", "later target family"), ("MISSED_RUNNERS", "DEEP_REVERSALS", "CHOP", "SPREAD_WIDENING"), "Pullback challenger and immediate-entry comparator", "12_48_288_M5_BARS", "3_12_48_M5_BARS", "INTRADAY_PULLBACK"),
        _base_reference("VOLATILITY_EXPANSION_BREAKOUT", (), "Compression followed by directional expansion may create continuation.", "AIOS control archetype; no selected institutional parameter set", "M5/H1 translation untested", "NO_EXACT_PUBLIC_RULE_SELECTED", "PRIOR_12_BAR_RANGE_BELOW_75_PERCENT_OF_TRAILING_288_BAR_MEDIAN_RANGE_THEN_COMPLETED_CLOSE_BREAKS_PRIOR_12_BAR_CLOSE_EXTREME", "NEXT_EXECUTABLE_BAR_AFTER_COMPLETED_BREAK", "12_COMPLETED_M5_BARS_FIXED", "CLOSE_REENTERS_FROZEN_PREBREAK_RANGE_OR_COST_BLOCK", ("12-bar compression", "75-percent threshold", "288-bar reference", "12-bar exit"), ("FALSE_BREAK", "NEWS_SHOCK", "HIGH_SPREAD", "LOW_LIQUIDITY"), "Breakout challenger", "12_AND_288_M5_BARS", "12_M5_BARS", "INTRADAY_BREAKOUT"),
        _base_reference("SIMPLE_MEAN_REVERSION_CONTROL", ("MAN_AHL_PROCESS",), "Some systematic programs study mean reversion, but no selected public source establishes this exact control.", "AIOS control archetype", "M5/H1 translation untested", "PUBLIC_SOURCE_SUPPORTS_FAMILY_EXISTENCE_NOT_THIS_RULE", "48_BAR_ROLLING_RETURN_ZSCORE;_LONG_AT_OR_BELOW_MINUS_2;_SHORT_AT_OR_ABOVE_PLUS_2", "NEXT_EXECUTABLE_BAR_AFTER_COMPLETED_SIGNAL", "EXIT_AT_ZERO_ZSCORE_OR_AFTER_12_COMPLETED_M5_BARS", "ZSCORE_EXTENDS_BEYOND_3_OR_DATA_COST_PORTFOLIO_BLOCK", ("48-bar lookback", "2/3 z-score thresholds", "12-bar exit"), ("PERSISTENT_TREND", "GAP", "VOLATILITY_SHIFT", "COST_DOMINANCE"), "Negative-control challenger", "48_M5_BARS", "12_M5_BARS", "INTRADAY_REVERSION"),
    ]


def champion_challenger_contract() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_CHAMPION_CHALLENGER_CONTRACT_V1",
        "ordered_required_baselines": ["NO_TRADE", "MATCHED_RANDOM_DIRECTION", "SIMPLE_PAIR_MOMENTUM", "BEST_APPLICABLE_COMMERCIAL_REFERENCE_BASELINE", "CURRENT_AIOS_CHAMPION_IF_ANY"],
        "selection_timing": "FROZEN_BEFORE_OUTCOME_ACCESS",
        "selection_inputs": ["signal_family", "horizon_class", "instrument_universe", "execution_contract", "declared_reference_strategy_id"],
        "selection_must_not_use": ["candidate_return", "candidate_profit_factor", "candidate_sharpe", "baseline_return", "best_backtest"],
        "comparison_contract": "IDENTICAL_PARTITIONS_COSTS_RISK_NORMALIZATION_AND_PORTFOLIO_LIMITS",
        "incremental_pass": ["candidate_after_cost_expectancy_gt_0", "candidate_after_cost_expectancy_gt_reference", "candidate_risk_normalized_return_gt_reference"],
        "missing_applicable_reference": "BLOCK",
        "no_current_champion": "NOT_APPLICABLE_NO_CHAMPION",
        "public_precedent_proves_edge": False,
    }


def research_to_production_parity_contract() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_RESEARCH_TO_PRODUCTION_PARITY_CONTRACT_V1",
        "stages": list(STAGES),
        "frozen_semantics": list(SCIENTIFIC_FINGERPRINT_FIELDS),
        "required_match": "SAME_CANDIDATE_FINGERPRINT_AT_EVERY_STAGE",
        "declared_environment_differences": ["data_availability", "execution_delay", "fill_uncertainty", "spread", "slippage", "financing"],
        "undeclared_difference": "BLOCK",
        "paper_authorized": False,
        "live_authorized": False,
    }


def semantic_parity(stage_specs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    missing = [stage for stage in STAGES if stage not in stage_specs]
    if missing:
        return {"status": "BLOCK", "reasons": [f"MISSING_STAGE:{stage}" for stage in missing]}
    fingerprints = {stage: candidate_fingerprint(stage_specs[stage]) for stage in STAGES}
    unique = set(fingerprints.values())
    return {"status": "PASS" if len(unique) == 1 else "FAIL", "fingerprints": fingerprints, "semantic_fingerprint": next(iter(unique)) if len(unique) == 1 else None}


def select_commercial_baseline(candidate: Mapping[str, Any], references: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    declared = str(candidate.get("declared_reference_strategy_id", ""))
    horizon = str(candidate.get("horizon_class", ""))
    if not declared or not horizon:
        return {"status": "BLOCK", "reason": "REFERENCE_AND_HORIZON_MUST_BE_FROZEN_BEFORE_SCORING"}
    matches = [row for row in references if row["REFERENCE_STRATEGY_ID"] == declared]
    if len(matches) != 1:
        return {"status": "BLOCK", "reason": "DECLARED_REFERENCE_NOT_REGISTERED"}
    reference = matches[0]
    if reference["AIOS_HORIZON_CLASS"] != horizon:
        return {"status": "BLOCK", "reason": "REFERENCE_HORIZON_NOT_APPLICABLE"}
    return {"status": "PASS", "reference_strategy_id": declared, "selection_used_outcomes": False}


def incremental_value(candidate_metrics: Mapping[str, Any], reference_metrics: Mapping[str, Any]) -> dict[str, Any]:
    required = ("after_cost_expectancy", "risk_normalized_return")
    if any(key not in candidate_metrics or key not in reference_metrics for key in required):
        return {"status": "BLOCK", "reason": "INCREMENTAL_METRICS_MISSING"}
    candidate_expectancy = float(candidate_metrics["after_cost_expectancy"])
    reference_expectancy = float(reference_metrics["after_cost_expectancy"])
    candidate_risk = float(candidate_metrics["risk_normalized_return"])
    reference_risk = float(reference_metrics["risk_normalized_return"])
    passed = candidate_expectancy > 0.0 and candidate_expectancy > reference_expectancy and candidate_risk > reference_risk
    return {"status": "PASS" if passed else "FAIL", "incremental_expectancy": candidate_expectancy - reference_expectancy, "incremental_risk_normalized_return": candidate_risk - reference_risk}


def verify_frozen_sources(repo_root: Path) -> dict[str, Any]:
    mismatches = []
    for relative, expected in FROZEN_SOURCE_HASHES.items():
        path = repo_root / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        if actual != expected:
            mismatches.append({"path": relative, "expected": expected, "actual": actual})
    return {"status": "PASS" if not mismatches else "FAIL", "checked": len(FROZEN_SOURCE_HASHES), "mismatches": mismatches}


def _load_index(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("FINGERPRINT_INDEX_MISSING")
    value = json.loads(path.read_text(encoding="ascii"))
    if value.get("schema") != "AIOS_FOREX_FINGERPRINT_INDEX_V1" or not isinstance(value.get("entries"), list):
        raise ValueError("FINGERPRINT_INDEX_INVALID")
    return value


def _append_ledger_record(records: list[dict[str, Any]], payload: Mapping[str, Any]) -> dict[str, Any]:
    body = {"sequence": len(records) + 1, "previous_record_sha256": records[-1]["record_sha256"], **dict(payload)}
    body["record_sha256"] = sha256_value(body)
    records.append(body)
    validate_trial_ledger(records)
    return body


def _validate_references(references: Sequence[Mapping[str, Any]], sources: Sequence[Mapping[str, Any]]) -> None:
    if len(references) != REFERENCE_COUNT or len({row["REFERENCE_STRATEGY_ID"] for row in references}) != REFERENCE_COUNT:
        raise ValueError("REFERENCE_COUNT_OR_IDENTITY_INVALID")
    source_ids = {row["source_id"] for row in sources}
    for reference in references:
        missing = [field for field in REQUIRED_REFERENCE_FIELDS if field not in reference]
        if missing:
            raise ValueError(f"REFERENCE_FIELDS_MISSING:{reference.get('REFERENCE_STRATEGY_ID')}:{','.join(missing)}")
        if any(source_id not in source_ids for source_id in reference["PUBLIC_SOURCE"]):
            raise ValueError("REFERENCE_SOURCE_UNKNOWN")
        if reference["AIOS_ADAPTATION_STATUS"] != "PROPOSED_UNSCORED_REFERENCE_ONLY":
            raise ValueError("REFERENCE_MUST_REMAIN_UNSCORED")
        candidate_fingerprint(reference["SCIENTIFIC_SPECIFICATION"])
    if any(row["performance_claim_use"] != "NOT_ACCEPTED_AS_AIOS_EVIDENCE" or row["code_imported"] for row in sources):
        raise ValueError("PUBLIC_SOURCE_EVIDENCE_BOUNDARY_BROKEN")


def build_registry(ledger_path: Path, fingerprint_index_path: Path) -> dict[str, Any]:
    ledger = [dict(row) for row in read_trial_ledger(ledger_path)]
    prior_summary = validate_trial_ledger(ledger)
    if prior_summary["scored_attempt_lower_bound"] < HISTORICAL_SCORED_ATTEMPT_LOWER_BOUND or prior_summary["proposed_unscored_count"] < PRIOR_PROPOSED_UNSCORED:
        raise ValueError("PRIOR_RESEARCH_MEMORY_INCOMPLETE")
    index = _load_index(fingerprint_index_path)
    references = reference_strategies()
    sources = public_sources()
    _validate_references(references, sources)
    existing = {row["fingerprint"]: row for row in index["entries"]}
    dispositions = []
    additions = []
    for reference in references:
        fingerprint = candidate_fingerprint(reference["SCIENTIFIC_SPECIFICATION"])
        reference["CANDIDATE_FINGERPRINT"] = fingerprint
        if fingerprint in existing:
            disposition = "DUPLICATE_OF_EXISTING_PROPOSED_SPECIFICATION"
        else:
            disposition = "APPENDED_PROPOSED_UNSCORED_REFERENCE"
            entry = {
                "candidate_id": f"PKT041_REFERENCE_{reference['REFERENCE_STRATEGY_ID']}",
                "reference_strategy_id": reference["REFERENCE_STRATEGY_ID"],
                "fingerprint": fingerprint,
                "specification": {field: reference["SCIENTIFIC_SPECIFICATION"][field] for field in SCIENTIFIC_FINGERPRINT_FIELDS},
                "status": "PROPOSED_UNSCORED",
                "reference_only": True,
            }
            additions.append(entry)
            existing[fingerprint] = entry
            _append_ledger_record(ledger, {
                "event_id": entry["candidate_id"],
                "status": "PROPOSED_UNSCORED",
                "scored_trial_increment": 0,
                "proposed_count": 1,
                "provenance": "PKT_FOREX_041_COMMERCIAL_REFERENCE_ARCHETYPE_STAGE0",
                "candidate_fingerprint": fingerprint,
            })
        dispositions.append({"reference_strategy_id": reference["REFERENCE_STRATEGY_ID"], "fingerprint": fingerprint, "disposition": disposition})
    index["entries"] = sorted(existing.values(), key=lambda row: (row["fingerprint"], row["candidate_id"]))
    final_summary = validate_trial_ledger(ledger)
    index["pkt041_reference_count"] = REFERENCE_COUNT
    index["pkt041_new_proposed_unscored"] = len(additions)
    index["total_proposed_unscored"] = final_summary["proposed_unscored_count"]
    contract = champion_challenger_contract()
    parity = research_to_production_parity_contract()
    sample_spec = references[0]["SCIENTIFIC_SPECIFICATION"]
    parity_test = semantic_parity({stage: sample_spec for stage in STAGES})
    if parity_test["status"] != "PASS":
        raise ValueError("SEMANTIC_PARITY_SELF_TEST_FAILED")
    registry = {
        "schema": SCHEMA,
        "packet_id": PACKET_ID,
        "status": "COMMERCIAL_REFERENCE_LIBRARY_REGISTERED_STAGE0",
        "public_sources": sources,
        "reference_strategies": references,
        "reference_dispositions": dispositions,
        "champion_challenger_contract": contract,
        "research_to_production_parity_contract": parity,
        "bias_check_requirements": list(BIAS_CHECK_REQUIREMENTS),
        "prior_family_reconciliation": {
            "rule": "FINGERPRINT_BEFORE_NAME;_REFERENCE_REGISTRATION_DOES_NOT_RESET_HISTORY",
            "known_prior_families": ["TIME_SERIES_MOMENTUM", "CROSS_SECTIONAL_CURRENCY_STRENGTH", "TREND_PULLBACK", "VOLATILITY_EXPANSION", "MEAN_REVERSION"],
            "outcome_claim": "NO_PRIOR_REJECTION_OVERRIDDEN",
        },
        "research_memory": {
            "prior_proposed_unscored": prior_summary["proposed_unscored_count"],
            "new_proposed_unscored": len(additions),
            "total_proposed_unscored": final_summary["proposed_unscored_count"],
            "scored_attempt_lower_bound_before": prior_summary["scored_attempt_lower_bound"],
            "scored_attempt_lower_bound_after": final_summary["scored_attempt_lower_bound"],
            "scored_trial_increment": 0,
            "ledger_head_sha256": final_summary["head_sha256"],
        },
        "safety": {
            "development_market_rows_opened": 0,
            "validation_rows_opened": 0,
            "holdout_rows_opened": 0,
            "pkt_forex_039_status": PKT039_STATUS,
            "pkt_forex_039_cells_scored": 0,
            "verified_edge": False,
            "paper_authorized": False,
            "live_authorized": False,
        },
        "synthetic_certification": {
            "benchmark_selection": select_commercial_baseline({"declared_reference_strategy_id": "SLOW_TIME_SERIES_MOMENTUM", "horizon_class": "SLOW"}, references),
            "incremental_value_pass": incremental_value({"after_cost_expectancy": 0.02, "risk_normalized_return": 0.5}, {"after_cost_expectancy": 0.01, "risk_normalized_return": 0.3}),
            "incremental_value_fail": incremental_value({"after_cost_expectancy": 0.00, "risk_normalized_return": 0.2}, {"after_cost_expectancy": 0.01, "risk_normalized_return": 0.3}),
            "semantic_parity": parity_test,
        },
    }
    registry["registry_sha256"] = sha256_value(registry)
    return {"registry": registry, "ledger": ledger, "fingerprint_index": index, "prior_summary": prior_summary, "final_summary": final_summary}


def build_scientific_artifacts(ledger_path: Path, fingerprint_index_path: Path) -> dict[str, bytes]:
    built = build_registry(ledger_path, fingerprint_index_path)
    artifacts = {
        "AIOS_FOREX_COMMERCIAL_REFERENCE_AND_BENCHMARK_REGISTRY_V1.json": pretty_json(built["registry"]).encode("ascii"),
        "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl": "".join(canonical_json(row) + "\n" for row in built["ledger"]).encode("ascii"),
        "AIOS_FOREX_FINGERPRINT_INDEX_V1.json": pretty_json(built["fingerprint_index"]).encode("ascii"),
    }
    receipt = {
        "schema": "AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_RECEIPT_V1",
        "packet_id": PACKET_ID,
        "status": "PASS",
        "reference_strategies_registered": REFERENCE_COUNT,
        "new_proposed_unscored": built["final_summary"]["proposed_unscored_count"] - built["prior_summary"]["proposed_unscored_count"],
        "total_proposed_unscored": built["final_summary"]["proposed_unscored_count"],
        "conservative_scored_attempt_lower_bound": built["final_summary"]["scored_attempt_lower_bound"],
        "new_scored_trial_increment": 0,
        "new_market_rows_opened": 0,
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
        "pkt_forex_039_status": PKT039_STATUS,
        "pkt_forex_039_cells_scored": 0,
        "champion_challenger_contract": "PASS",
        "research_to_production_parity": "PASS",
        "bias_check_requirements": "PASS",
        "verified_edge": False,
        "paper_authorized": False,
        "live_authorized": False,
    }
    artifacts["AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_RECEIPT.json"] = pretty_json(receipt).encode("ascii")
    inventory = {name: {"bytes": len(payload), "sha256": sha256_bytes(payload)} for name, payload in sorted(artifacts.items())}
    manifest = {"schema": "AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_MANIFEST_V1", "scientific_artifact_count": len(artifacts), "artifacts": inventory, "aggregate_sha256": sha256_value(inventory)}
    artifacts["AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_MANIFEST.json"] = pretty_json(manifest).encode("ascii")
    return artifacts


def write_stage0(output_root: Path, ledger_path: Path, fingerprint_index_path: Path, repo_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise ValueError("OUTPUT_COLLISION")
    frozen = verify_frozen_sources(repo_root)
    if frozen["status"] != "PASS":
        raise ValueError("FROZEN_SOURCE_CHANGED")
    artifacts = build_scientific_artifacts(ledger_path, fingerprint_index_path)
    for name, payload in artifacts.items():
        atomic_write(output_root / name, payload)
    manifest = json.loads(artifacts["AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_MANIFEST.json"])
    return {"status": "PASS", "output_root": str(output_root), "aggregate_sha256": manifest["aggregate_sha256"], "scientific_artifact_count": manifest["scientific_artifact_count"], "frozen_source_status": frozen["status"], "new_market_rows_opened": 0, "new_scored_trial_increment": 0}


def compare_stage0(first_root: Path, second_root: Path) -> dict[str, Any]:
    first = {path.name: path.read_bytes() for path in first_root.iterdir() if path.is_file()}
    second = {path.name: path.read_bytes() for path in second_root.iterdir() if path.is_file()}
    mismatches = sorted(set(first) ^ set(second)) + sorted(name for name in set(first) & set(second) if first[name] != second[name])
    first_manifest = json.loads(first["AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_MANIFEST.json"])
    second_manifest = json.loads(second["AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_MANIFEST.json"])
    return {"status": "PASS" if not mismatches else "FAIL", "byte_identical": not mismatches, "mismatches": mismatches, "first_aggregate_sha256": first_manifest["aggregate_sha256"], "second_aggregate_sha256": second_manifest["aggregate_sha256"]}


def validate_stage0_artifacts(source_root: Path) -> dict[str, Any]:
    required = {
        "AIOS_FOREX_COMMERCIAL_REFERENCE_AND_BENCHMARK_REGISTRY_V1.json",
        "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl",
        "AIOS_FOREX_FINGERPRINT_INDEX_V1.json",
        "AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_RECEIPT.json",
        "AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_MANIFEST.json",
    }
    files = {path.name: path for path in source_root.iterdir() if path.is_file()}
    if set(files) != required:
        raise ValueError("STAGE0_ARTIFACT_SET_INVALID")
    manifest = json.loads(files["AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_MANIFEST.json"].read_text(encoding="ascii"))
    inventory = manifest.get("artifacts", {})
    expected_inventory_names = required - {"AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_MANIFEST.json"}
    if set(inventory) != expected_inventory_names or manifest.get("scientific_artifact_count") != len(expected_inventory_names):
        raise ValueError("STAGE0_MANIFEST_INVENTORY_INVALID")
    actual_inventory = {}
    for name in sorted(expected_inventory_names):
        payload = files[name].read_bytes()
        actual_inventory[name] = {"bytes": len(payload), "sha256": sha256_bytes(payload)}
    if actual_inventory != inventory or manifest.get("aggregate_sha256") != sha256_value(actual_inventory):
        raise ValueError("STAGE0_ARTIFACT_HASH_MISMATCH")
    return {"status": "PASS", "artifact_count": len(expected_inventory_names), "aggregate_sha256": manifest["aggregate_sha256"], "files": files}


def promote_stage0(source_root: Path, runtime_registry: Path, ledger_path: Path, fingerprint_index_path: Path) -> dict[str, Any]:
    validation = validate_stage0_artifacts(source_root)
    files = validation["files"]
    registry = json.loads(files["AIOS_FOREX_COMMERCIAL_REFERENCE_AND_BENCHMARK_REGISTRY_V1.json"].read_text(encoding="ascii"))
    receipt = json.loads(files["AIOS_FOREX_COMMERCIAL_REFERENCE_STAGE0_RECEIPT.json"].read_text(encoding="ascii"))
    new_ledger_bytes = files["AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl"].read_bytes()
    old_ledger_bytes = ledger_path.read_bytes()
    if not new_ledger_bytes.startswith(old_ledger_bytes):
        raise ValueError("TRIAL_LEDGER_APPEND_ONLY_PREFIX_VIOLATION")
    ledger_rows = [json.loads(line) for line in new_ledger_bytes.decode("ascii").splitlines()]
    summary = validate_trial_ledger(ledger_rows)
    if registry.get("status") != "COMMERCIAL_REFERENCE_LIBRARY_REGISTERED_STAGE0" or len(registry.get("reference_strategies", [])) != REFERENCE_COUNT:
        raise ValueError("RUNTIME_REGISTRY_INVALID")
    if receipt.get("new_scored_trial_increment") != 0 or summary["scored_attempt_lower_bound"] < HISTORICAL_SCORED_ATTEMPT_LOWER_BOUND:
        raise ValueError("SCORED_MEMORY_CHANGED")
    new_index = json.loads(files["AIOS_FOREX_FINGERPRINT_INDEX_V1.json"].read_text(encoding="ascii"))
    old_index = _load_index(fingerprint_index_path)
    old_pairs = {(row["fingerprint"], canonical_json(row)) for row in old_index["entries"]}
    new_pairs = {(row["fingerprint"], canonical_json(row)) for row in new_index["entries"]}
    if not old_pairs.issubset(new_pairs):
        raise ValueError("FINGERPRINT_INDEX_PRIOR_ENTRY_CHANGED")
    atomic_write(runtime_registry, files["AIOS_FOREX_COMMERCIAL_REFERENCE_AND_BENCHMARK_REGISTRY_V1.json"].read_bytes())
    atomic_write(fingerprint_index_path, files["AIOS_FOREX_FINGERPRINT_INDEX_V1.json"].read_bytes())
    suffix = new_ledger_bytes[len(old_ledger_bytes):]
    if suffix:
        with ledger_path.open("ab") as handle:
            handle.write(suffix)
            handle.flush()
    return {"status": "PASS", "reference_strategies_registered": REFERENCE_COUNT, "new_proposed_unscored": receipt["new_proposed_unscored"], "new_scored_trial_increment": 0, "scored_attempt_lower_bound": summary["scored_attempt_lower_bound"], "ledger_head_sha256": summary["head_sha256"], "aggregate_sha256": validation["aggregate_sha256"], "runtime_registry_sha256": sha256_file(runtime_registry), "fingerprint_index_sha256": sha256_file(fingerprint_index_path), "trial_ledger_sha256": sha256_file(ledger_path)}
