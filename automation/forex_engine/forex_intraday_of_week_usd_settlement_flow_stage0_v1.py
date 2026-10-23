"""No-outcome Stage-0 gate for an H1 intraday-of-week USD settlement-flow hypothesis."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-FOREX-033"
STRATEGY_ID = "INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_V1"
F7_CONTRACT_FINGERPRINT = "e3fbdbb0a0fdfba17f4646c32769ed9e1732fee40ba113bc7eb78585c8fca27f"
EXPECTED_MECHANISM_FINGERPRINT = "6b762c24fb92abe39748140a82a96cfb3e8aaa4a2d098908a789ca9be7907679"
H1_CORPUS_ID = "AIOS_FOREX_MULTI_REGIME_CORPUS_V3"
H1_CORPUS_SHA256 = "4357f24113ba54b9a6f8d6a3d87860109ca7429dbbd627b20c3d5a30540c6b32"
H1_MANIFEST_SHA256 = "f784867978464aee59f4b3377eca013237378fd8c3a61c068f8c111ce6451d32"
ACCESS_DATE = "2026-09-05"
PRIOR_ATTEMPTS = 1195
PRIOR_AFTER_COST_CANDIDATES = 143

PAIRS = (
    "AUD_USD", "EUR_USD", "GBP_USD", "NZD_USD", "USD_CAD", "USD_CHF",
    "USD_CNH", "USD_CZK", "USD_DKK", "USD_HUF", "USD_JPY", "USD_MXN",
    "USD_NOK", "USD_PLN", "USD_SEK", "USD_SGD", "USD_ZAR",
)

VARIANTS = (
    ("WED_FRI_ORIGINAL_LONG", (2, 3, 4), 1),
    ("WED_FRI_EXACT_REVERSED_SHORT", (2, 3, 4), -1),
    ("MON_TUE_ORIGINAL_SHORT", (0, 1), -1),
    ("MON_TUE_EXACT_REVERSED_LONG", (0, 1), 1),
    ("SYMMETRIC_ORIGINAL", (0, 1, 2, 3, 4), 0),
)

EXPECTED_CANDIDATE_FINGERPRINTS = {
    "IDOW-WED_FRI_ORIGINAL_LONG": "c6fc58d05ce8d10eb60a23f020d2dc58f2e0249d984c25b1a9aadc7377b15c3b",
    "IDOW-WED_FRI_EXACT_REVERSED_SHORT": "bd7c33d48524eda63b81c1e5d30905ac73358d6f9f3516d67410e84034fa9bed",
    "IDOW-MON_TUE_ORIGINAL_SHORT": "10d21211921082f1addd32aa2b57934386954c1d04f0aeda41fa5ad324bdd8d8",
    "IDOW-MON_TUE_EXACT_REVERSED_LONG": "d3290f71963fbd33107d3f8b1cacfb119ffb9082fad012d619b77f85376dc039",
    "IDOW-SYMMETRIC_ORIGINAL": "bdeec34154ca0830e4c370f4e749161c17597e0deda3683fcf0d0abd63a712d9",
}

MECHANISM_DESCRIPTOR = {
    "calendar": "UTC_ISO_WEEKDAY_WITH_MONDAY_ZERO",
    "cost_base": "OBSERVED_H1_BID_ASK_PLUS_0.10_PIP_ADVERSE_SLIPPAGE_PER_SIDE",
    "cost_stress": "OBSERVED_H1_BID_ASK_PLUS_0.50_PIP_ADVERSE_SLIPPAGE_PER_SIDE",
    "dataset_id": H1_CORPUS_ID,
    "dataset_sha256": H1_CORPUS_SHA256,
    "development": "2015-01-01T00:00:00Z/2025-01-01T00:00:00Z",
    "economic_mechanism": "RECURRING_WEEKDAY_SETTLEMENT_FUNDING_AND_INSTITUTIONAL_FLOW_IMBALANCES_CAN_CREATE_INTRADAY_USD_RELATIVE_RETURN_PATTERNS",
    "entry": "00:00_UTC_H1_EXECUTABLE_OPEN",
    "exit": "20:00_UTC_H1_EXECUTABLE_OPEN_SAME_DAY",
    "final_holdout": "2026-01-01T00:00:00Z/2026-08-29T00:00:00Z_SEALED",
    "granularity": "H1_NATIVE_COMPLETED_CANDLES",
    "pair_universe": list(PAIRS),
    "position_risk_fraction_total": 0.0025,
    "stop": "ONE_PRIOR_COMPLETED_ATR20_FIXED_AT_ENTRY",
    "take_profit": "NONE",
    "validation": "2025-01-01T00:00:00Z/2026-01-01T00:00:00Z_UNOPENED_UNLESS_STAGE1_SURVIVES",
    "variants": [item[0] for item in VARIANTS],
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


def mechanism_fingerprint() -> str:
    fingerprint = sha256_bytes(canonical_bytes(MECHANISM_DESCRIPTOR, compact=True))
    if fingerprint != EXPECTED_MECHANISM_FINGERPRINT:
        raise RuntimeError("MECHANISM_FINGERPRINT_MISMATCH")
    return fingerprint


def foreign_per_usd_order_sign(pair: str, foreign_direction: int) -> int:
    if pair not in PAIRS or foreign_direction not in (-1, 1):
        raise ValueError("INVALID_PAIR_OR_FOREIGN_DIRECTION")
    base, quote = pair.split("_")
    if quote == "USD":
        return foreign_direction
    if base == "USD":
        return -foreign_direction
    raise ValueError("PAIR_IS_NOT_USD_CROSS")


def variant_foreign_direction(variant: str, weekday: int) -> int:
    if weekday not in range(5):
        raise ValueError("WEEKDAY_OUTSIDE_MONDAY_TO_FRIDAY")
    if variant == "SYMMETRIC_ORIGINAL":
        return -1 if weekday in (0, 1) else 1
    for name, weekdays, direction in VARIANTS:
        if name == variant:
            if weekday not in weekdays:
                raise ValueError("VARIANT_NOT_ACTIVE_ON_WEEKDAY")
            return direction
    raise ValueError("UNKNOWN_VARIANT")


def candidate_definitions() -> list[dict[str, Any]]:
    parent = mechanism_fingerprint()
    candidates = []
    for name, weekdays, direction in VARIANTS:
        definition = {
            "candidate_id": f"IDOW-{name}",
            "foreign_direction": direction if direction else "MON_TUE_SHORT_WED_FRI_LONG",
            "holding_window_utc": "00:00_TO_20:00",
            "strategy_id": STRATEGY_ID,
            "variant": name,
            "weekdays": list(weekdays),
        }
        fingerprint = sha256_bytes(canonical_bytes({
            "mechanism_fingerprint": parent,
            "definition": definition,
        }, compact=True))
        if fingerprint != EXPECTED_CANDIDATE_FINGERPRINTS[definition["candidate_id"]]:
            raise RuntimeError(f"CANDIDATE_FINGERPRINT_MISMATCH:{definition['candidate_id']}")
        candidates.append({
            **definition,
            "candidate_fingerprint": fingerprint,
        })
    return candidates


def build_source_registry() -> dict[str, Any]:
    shared = {
        "claimed_performance": "UNVERIFIED_NOT_ACCEPTED_AS_EDGE_EVIDENCE",
        "source_code_exists": False,
        "existing_fingerprint_match": False,
        "aios_dataset_compatibility": "H1_RULE_REQUIRES_INDEPENDENT_AIOS_RECONSTRUCTION_WITH_CERTIFIED_BID_ASK_DATA",
    }
    return {
        "schema": "AIOS_FOREX_HYPOTHESIS_SOURCE_REGISTRY_SUPPLEMENT.v1",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "evidence_role": "HYPOTHESIS_INPUT_AND_COUNTEREVIDENCE_ONLY_NOT_EDGE_PROOF",
        "sources": [
            {
                **shared,
                "source_id": "KHADEMALOMOOM_NARAYAN_2020_IDOW",
                "url": "https://doi.org/10.1016/j.ememar.2020.100681",
                "title": "Intraday-of-the-week effects: What do the exchange rate data tell us?",
                "author_or_organization": "Siroos Khademalomoom; Paresh Kumar Narayan",
                "publication_date": "2020-06",
                "access_date": ACCESS_DATE,
                "source_type": "PEER_REVIEWED_JOURNAL_ARTICLE",
                "claimed_economic_mechanism": "INTRADAY_WEEKDAY_PATTERNS_IN_FOREIGN_CURRENCY_RETURNS_AGAINST_USD",
                "claimed_market_and_timeframe": "TWELVE_CURRENCIES_AGAINST_USD_HOURLY",
                "exact_disclosed_rules": "ABSTRACT_REPORTS_MON_TUE_DEPRECIATION_AND_REST_OF_WEEK_APPRECIATION; AIOS FREEZES ITS OWN HOURS_AND_COSTS",
                "costs_included": "NOT_ESTABLISHED_FROM_PUBLIC_ABSTRACT",
                "walk_forward_included": "NOT_ESTABLISHED_FROM_PUBLIC_ABSTRACT",
                "license": "PUBLISHER_COPYRIGHT_NO_OPEN_CODE_LICENSE_IDENTIFIED",
                "replication_risks": ["PUBLIC_ABSTRACT_NOT_FULL_RULESET", "PUBLISHED_SAMPLE_SELECTION", "TRANSACTION_COST_AND_DECAY_RISK"],
                "research_priority": "HIGH_INFORMATION_SIMPLE_REPLICATION",
                "final_disposition": "ELIGIBLE_HYPOTHESIS_INPUT_UNVERIFIED",
            },
            {
                **shared,
                "source_id": "YAMORI_KURIHARA_2004_DOW_DECAY",
                "url": "https://doi.org/10.1016/j.ribaf.2004.02.004",
                "title": "The day-of-the-week effect in foreign exchange markets: multi-currency evidence",
                "author_or_organization": "Nobuyoshi Yamori; Yutaka Kurihara",
                "publication_date": "2004-04",
                "access_date": ACCESS_DATE,
                "source_type": "PEER_REVIEWED_JOURNAL_ARTICLE",
                "claimed_economic_mechanism": "CALENDAR_ANOMALY_MAY_DECAY_AS_MARKETS_DEVELOP",
                "claimed_market_and_timeframe": "TWENTY_NINE_FOREIGN_EXCHANGE_RATES_DAILY_NEW_YORK",
                "exact_disclosed_rules": "WEEKDAY_DUMMY_RETURN_COMPARISON; NOT A COMPLETE TRADABLE H1 RULE",
                "costs_included": False,
                "walk_forward_included": "SUBPERIOD_COMPARISON_NOT_FORMAL_WALK_FORWARD",
                "license": "PUBLISHER_COPYRIGHT_NO_OPEN_CODE_LICENSE_IDENTIFIED",
                "replication_risks": ["DAILY_NOT_H1", "OLD_SAMPLE", "REPORTS_EFFECT_DISAPPEARED_FOR_ALMOST_ALL_CURRENCIES_IN_1990S"],
                "research_priority": "HIGH_COUNTEREVIDENCE",
                "final_disposition": "COUNTEREVIDENCE_REQUIRES_STRICT_DECAY_TEST",
            },
            {
                **shared,
                "source_id": "KUMAR_2018_CALENDAR_ANOMALY_DECAY",
                "url": "https://ideas.repec.org/a/eme/sefpps/sef-08-2015-0192.html",
                "title": "On the disappearance of calendar anomalies: have the currency markets become efficient?",
                "author_or_organization": "Satish Kumar",
                "publication_date": "2018",
                "access_date": ACCESS_DATE,
                "source_type": "PEER_REVIEWED_JOURNAL_ARTICLE_INDEX_RECORD",
                "claimed_economic_mechanism": "CALENDAR_ANOMALIES_CAN_DISAPPEAR_WITH_MARKET_EFFICIENCY",
                "claimed_market_and_timeframe": "TWENTY_USD_CURRENCY_PAIRS_DAILY_1995_TO_2014",
                "exact_disclosed_rules": "DOW_JANUARY_AND_TURN_OF_MONTH_TESTS; NO COMPLETE H1 EXECUTION RULE",
                "costs_included": "NOT_ESTABLISHED_FROM_PUBLIC_INDEX_RECORD",
                "walk_forward_included": "NOT_ESTABLISHED_FROM_PUBLIC_INDEX_RECORD",
                "license": "PUBLISHER_COPYRIGHT_NO_OPEN_CODE_LICENSE_IDENTIFIED",
                "replication_risks": ["DAILY_NOT_H1", "NO_EXECUTABLE_PUBLIC_RULE", "DECAY_AND_MULTIPLE_TESTING_RISK"],
                "research_priority": "HIGH_COUNTEREVIDENCE",
                "final_disposition": "COUNTEREVIDENCE_REQUIRES_STRICT_OUT_OF_SAMPLE_TEST",
            },
            {
                **shared,
                "source_id": "FXABSOLUTE_EDGE_GUIDE",
                "url": "https://fxabsolute.com/how-to-build-trading-edge",
                "title": "How to Build a Trading Edge in Forex",
                "author_or_organization": "FXAbsolute",
                "publication_date": "NOT_DISCLOSED",
                "access_date": ACCESS_DATE,
                "source_type": "COMMERCIAL_EDUCATIONAL_GUIDE",
                "claimed_economic_mechanism": "NONE",
                "claimed_market_and_timeframe": "GENERAL_FOREX_METHODOLOGY",
                "exact_disclosed_rules": "PROCESS_GUIDANCE_ONLY_DEFINE_RULES_JOURNAL_ALL_TRADES_TEST_ACROSS_CONDITIONS_AND_USE_UNTOUCHED_LATER_DATA",
                "costs_included": "NOT_SPECIFIED",
                "walk_forward_included": "PARTIAL_UNTOUCHED_DATA_GUIDANCE_NOT_FORMAL_WALK_FORWARD",
                "license": "NO_EXPLICIT_LICENSE_STATED_NO_CODE_ADAPTED",
                "replication_risks": ["COMMERCIAL_SOURCE", "MARKETING_CLAIMS_AND_THRESHOLDS_UNVERIFIED", "NO_STRATEGY_EDGE_EVIDENCE"],
                "research_priority": "PROCESS_GUIDANCE_ONLY",
                "final_disposition": "METHODOLOGY_ONLY_UNVERIFIED_NOT_EDGE_PROOF",
            },
        ],
        "unsupported_claims": [
            "NO_SOURCE_PROVES_CURRENT_AFTER_COST_H1_WEEKDAY_EXPECTANCY",
            "NO_PUBLISHED_RESULT_REPLACES_AIOS_BID_ASK_WALK_FORWARD_VALIDATION",
        ],
        "status": "PASS_SOURCES_AND_COUNTEREVIDENCE_RECORDED",
    }


def build_preregistration() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_STRATEGY_PREREGISTRATION.v1",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_mechanism_fingerprint": mechanism_fingerprint(),
        "parent_contract": {"technique_id": "F7_DAY_OF_WEEK", "fingerprint": F7_CONTRACT_FINGERPRINT},
        "strategy_mechanism_descriptor": MECHANISM_DESCRIPTOR,
        "economic_mechanism": "Recurring weekday settlement, funding, and institutional-flow imbalances may leave predictable intraday foreign-currency-versus-USD returns, but published decay evidence makes this a strict falsification test.",
        "dataset": {
            "id": H1_CORPUS_ID,
            "sha256": H1_CORPUS_SHA256,
            "development_start": "2015-01-01T00:00:00Z",
            "development_end_exclusive": "2025-01-01T00:00:00Z",
            "validation": "2025-01-01T00:00:00Z/2026-01-01T00:00:00Z_UNOPENED_UNLESS_STAGE1_SURVIVOR",
            "final_holdout": "2026_ROWS_SEALED_SINGLE_USE",
        },
        "pair_universe": list(PAIRS),
        "timeframes": {"signal": "UTC_CALENDAR", "execution": "H1", "confirmation": "NONE"},
        "signal_calculation": "ISO UTC weekday known before the 00:00 UTC H1 entry; no price-derived signal and no fitted weekday selection",
        "entry_rules": {"time": "00:00 UTC H1 open", "price": "BUY ask open plus base slippage; SELL bid open minus base slippage"},
        "exit_rules": {
            "stop": "one ATR20 computed only from completed H1 candles ending before entry; BUY stop checks bid low, SELL stop checks ask high",
            "take_profit": "NONE",
            "time_exit": "20:00 UTC H1 open same day; BUY exits bid and SELL exits ask",
            "rollover": "position must be flat before 21:55 UTC",
        },
        "direction_rules": {
            "normalization": "positive foreign direction means long non-USD currency versus USD regardless of pair quote orientation",
            "variants": candidate_definitions(),
            "exact_reverse_identity": "same pair, date, entry, exit, stop distance, and costs with arithmetic opposite direction",
        },
        "position_sizing": "equal initial ATR risk across eligible pairs, 0.25 percent total portfolio risk per weekday basket",
        "risk_limits": {"maximum_pair_risk_percent": 0.025, "maximum_total_initial_risk_percent": 0.25, "usd_share_of_gross_currency_legs_percent": 50.0},
        "cost_model": {
            "gross": "midpoint entry, stop, and exit without slippage",
            "base": "observed bid/ask plus 0.10 pip adverse slippage per side",
            "stress": "observed bid/ask plus 0.50 pip adverse slippage per side",
            "financing": "NOT_APPLICABLE_FLAT_BEFORE_ROLLOVER",
        },
        "parameter_grid": {"variants": [item[0] for item in VARIANTS], "candidate_count": 5, "fitted_parameters": 0},
        "chronological_folds": [
            {"fold": 1, "score_start": "2019-01-01T00:00:00Z", "score_end_exclusive": "2020-01-01T00:00:00Z", "training": "2015 through 2018 only"},
            {"fold": 2, "score_start": "2020-01-01T00:00:00Z", "score_end_exclusive": "2021-01-01T00:00:00Z", "training": "2015 through 2019 only"},
            {"fold": 3, "score_start": "2021-01-01T00:00:00Z", "score_end_exclusive": "2022-01-01T00:00:00Z", "training": "2015 through 2020 only"},
            {"fold": 4, "score_start": "2022-01-01T00:00:00Z", "score_end_exclusive": "2023-01-01T00:00:00Z", "training": "2015 through 2021 only"},
            {"fold": 5, "score_start": "2023-01-01T00:00:00Z", "score_end_exclusive": "2024-01-01T00:00:00Z", "training": "2015 through 2022 only"},
            {"fold": 6, "score_start": "2024-01-01T00:00:00Z", "score_end_exclusive": "2025-01-01T00:00:00Z", "training": "2015 through 2023 only"},
        ],
        "purge_and_embargo": "21 H1 bars at each fold boundary, covering ATR warm-up and maximum same-day hold",
        "stage1_pre_score_capacity_gate": {
            "minimum_complete_pair_days_per_candidate": 100,
            "minimum_complete_days_per_pair": 100,
            "minimum_pairs": 10,
            "minimum_pairs_per_each_of_six_folds": 8,
            "failure_status": "STAGE0_INSUFFICIENT_CAPACITY_ZERO_TRIALS_ADDED",
        },
        "baselines": [
            "NO_TRADE_ZERO_EXPECTANCY",
            "MATCHED_DETERMINISTIC_RANDOM_DIRECTION_IDENTICAL_PAIR_DATES",
            "ALWAYS_LONG_FOREIGN_SAME_WINDOW",
            "ALWAYS_SHORT_FOREIGN_SAME_WINDOW",
            "WEEKDAY_AGNOSTIC_SAME_WINDOW",
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
            "minimum_contributing_currencies": 6,
            "must_beat_all_required_after_cost_baselines": True,
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
        "journal_fields": [
            "strategy_id", "candidate_id", "pair", "direction", "signal_timestamp", "entry_timestamp",
            "entry_price", "exit_timestamp", "exit_price", "stop_loss", "take_profit", "spread",
            "modeled_slippage", "gross_result_r", "net_result_r", "entry_reason", "exit_reason",
            "session", "volatility_regime", "trend_range_regime", "economic_event_proximity", "filter_results",
        ],
        "reproduction_commands": [
            "python -B scripts/forex_delivery/run_forex_intraday_of_week_usd_settlement_flow_stage1_v1.py --output .aios/staging/PKT_FOREX_034/run1",
            "python -B scripts/forex_delivery/run_forex_intraday_of_week_usd_settlement_flow_stage1_v1.py --output .aios/staging/PKT_FOREX_034/run2",
        ],
        "preregistered_before_outcome_access": True,
        "status": "FROZEN_IF_STAGE0_ELIGIBLE",
    }


def run(repo_root: Path, output: Path) -> dict[str, Any]:
    matrix_path = repo_root / ".aios/staging/PKT_FOREX_027/run1/AIOS_FOREX_AUTHORITATIVE_PAIR_TIMEFRAME_MATRIX_V1.json"
    manifest_path = repo_root / ".aios/runtime/forex_multi_regime_corpus_v3/manifests/manifest.json"
    fidelity_path = repo_root / "Reports/forex_delivery/AIOS_FOREX_SCALPING_TECHNIQUE_FIDELITY_V1_STATE.json"
    completion_path = repo_root / ".aios/staging/PKT_FOREX_032/PKT_FOREX_032_COMPLETION.json"
    if sha256_file(manifest_path) != H1_MANIFEST_SHA256:
        raise RuntimeError("H1_MANIFEST_SHA256_MISMATCH")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    fidelity = json.loads(fidelity_path.read_text(encoding="utf-8"))
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    h1_rows = [row for row in matrix["rows"] if row["granularity"] == "H1" and row["development_eligibility"] and "USD" in (row["base_currency"], row["quote_currency"])]
    observed_pairs = sorted(row["pair"] for row in h1_rows)
    f7 = [item for item in fidelity["technique_contracts"] if item["technique_id"] == "F7_DAY_OF_WEEK"]
    gates = {
        "pkt032_completion_valid": completion.get("result") == "VALID_STAGE1_FAILURE_POSTMORTEM_COMPLETE",
        "prior_trial_memory_preserved": completion.get("actual_computational_attempt_lower_bound_after") == PRIOR_ATTEMPTS and completion.get("governed_after_cost_candidates_after") == PRIOR_AFTER_COST_CANDIDATES,
        "exact_seventeen_h1_usd_pairs": observed_pairs == list(PAIRS),
        "all_rows_native_certified_bid_ask": all(row["availability"] == "NATIVE_CERTIFIED" and row["bid_available"] and row["ask_available"] for row in h1_rows),
        "single_h1_corpus_identity": {row["dataset_sha256"] for row in h1_rows} == {H1_CORPUS_SHA256},
        "f7_contract_exact": len(f7) == 1 and f7[0]["fingerprint"] == F7_CONTRACT_FINGERPRINT and f7[0]["implementation_status"] == "CONTRACT_ONLY_NOT_IMPLEMENTED",
        "exact_five_candidate_fingerprints": len(candidate_definitions()) == len({item["candidate_fingerprint"] for item in candidate_definitions()}) == 5,
        "market_rows_opened_zero": True,
        "returns_calculated_zero": True,
    }
    decision = "ADMIT_STAGE1_LOW_COST_ONLY" if all(gates.values()) else "BLOCK_STAGE0"
    capacity = {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_STAGE0_CAPACITY.v1",
        "packet_id": PACKET_ID,
        "dataset_id": H1_CORPUS_ID,
        "dataset_sha256": H1_CORPUS_SHA256,
        "manifest_sha256": H1_MANIFEST_SHA256,
        "matrix_sha256": sha256_file(matrix_path),
        "pair_count": len(observed_pairs),
        "pairs": observed_pairs,
        "gates": gates,
        "deferred_pre_score_checks": "COMPLETE_INTRADAY_WINDOWS_AND_STOP_DATA_CHECKED_BEFORE_ANY_RETURN_IN_STAGE1",
        "safety": {"market_rows_opened": 0, "returns_calculated": 0, "strategy_candidates_scored": 0, "validation_rows_opened": 0, "final_holdout_rows_opened": 0, "broker_access": False, "credentials_accessed": False, "orders": False},
        "status": decision,
    }
    duplicate = {
        "schema": "AIOS_FOREX_MECHANISM_DUPLICATE_DECISION.v1",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_mechanism_fingerprint": mechanism_fingerprint(),
        "parent_f7_contract_fingerprint": F7_CONTRACT_FINGERPRINT,
        "decision": "DISTINCT_EXISTING_UNSCORED_CONTRACT_WITH_FIXED_SETTLEMENT_FLOW_BOUNDARY",
        "distinguishing_features": ["calendar-only ex-ante signal", "native H1 17-pair USD breadth", "fixed 00:00-to-20:00 UTC window", "foreign-per-USD orientation", "original and exact inverse candidates"],
        "blocked_duplicate_forms": ["POST_HOC_BEST_WEEKDAY_OR_HOUR_SELECTION", "RELABELED_SESSION_INVENTORY_CYCLE", "PAIR_SPECIFIC_WEEKDAY_TUNING", "PRICE_INDICATOR_ADDED_TO_RESCUE_CALENDAR_RULE"],
        "prohibited_rescues": ["POST_HOC_PAIR_DIRECTION_SESSION_VOLATILITY_TREND_OR_EVENT_FILTER", "VALIDATION_DERIVED_WEEKDAY_OR_HOUR_SELECTION", "REMOVAL_OF_COSTS", "DELETION_OF_LOSING_TRADES"],
        "existing_governed_after_cost_candidates": PRIOR_AFTER_COST_CANDIDATES,
        "actual_computational_attempt_lower_bound": PRIOR_ATTEMPTS,
        "actual_trials_added": 0,
        "status": "PASS_TO_STAGE1_IF_CAPACITY_GATES_PASS",
    }
    contract = {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_STAGE0_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "status": decision,
        "market_outcomes_scored": False,
        "actual_trials_added": 0,
        "actual_computational_attempt_lower_bound": PRIOR_ATTEMPTS,
        "governed_after_cost_candidates": PRIOR_AFTER_COST_CANDIDATES,
        "validation": "SEALED_NOT_OPENED",
        "final_holdout": "SEALED_NOT_OPENED",
    }
    values = {
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_STAGE0_CAPACITY.json": capacity,
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_DUPLICATE_DECISION.json": duplicate,
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_HYPOTHESIS_SOURCES.json": build_source_registry(),
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_PREREGISTRATION.json": build_preregistration(),
        "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_STAGE0_CONTRACT.json": contract,
    }
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, value in sorted(values.items()):
        payload = canonical_bytes(value)
        (output / name).write_bytes(payload)
        files[name] = {"bytes": len(payload), "sha256": sha256_bytes(payload)}
    receipt = {
        "schema": "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_STAGE0_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "files": files,
        "aggregate_sha256": sha256_bytes(b"".join(name.encode("utf-8") + b"\0" + bytes.fromhex(details["sha256"]) for name, details in sorted(files.items()))),
        "result": decision,
        "actual_trials_added": 0,
        "validation_rows_opened": 0,
        "final_holdout_rows_opened": 0,
        "status": "PASS" if decision == "ADMIT_STAGE1_LOW_COST_ONLY" else "BLOCK",
    }
    receipt_payload = canonical_bytes(receipt)
    (output / "AIOS_FOREX_INTRADAY_OF_WEEK_USD_SETTLEMENT_FLOW_STAGE0_RECEIPT.json").write_bytes(receipt_payload)
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
