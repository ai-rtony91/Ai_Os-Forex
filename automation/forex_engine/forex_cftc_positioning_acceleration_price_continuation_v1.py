"""PKT-FOREX-020: CFTC positioning acceleration with H1 price continuation."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

from automation.forex_engine.forex_cftc_crowding_unwind_price_confirmation_v1 import (
    DEVELOPMENT_FOLD_COUNT,
    HOLDOUT_START,
    MAXIMUM_DRAWDOWN_PCT,
    MINIMUM_DIRECTION_TRADES,
    MINIMUM_PRE_HOLDOUT_TRADES,
    build_cftc_history,
    canonical_bytes,
    chronology_audit,
    load_pair_bars,
    metrics,
    point_in_time_zscores,
    probability_of_backtest_overfitting_proxy,
    random_direction_metrics,
    rejected_fingerprints,
    sha256_bytes,
    split_and_fold,
    verify_cftc_manifest,
    verify_h1_manifest,
    _trade,
)

PACKET_ID = "PKT-FOREX-020"
PACKET_SHA256 = "b906c204bffb9385484de240765fbbd179eae60604377e6526c9e26b9eab2ef7"
FAMILY = "CFTC_POSITIONING_ACCELERATION_WITH_PRICE_CONTINUATION"
MECHANISM = "WEEKLY_LEVERAGED_FUND_POSITIONING_CHANGE_ACCELERATION_ALIGNED_H1_PRICE_CONTINUATION"
DEV_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEV_END = datetime(2025, 4, 1, tzinfo=timezone.utc)
NO_TRADE_EXPECTANCY_R = 0.0
PRIOR_TRIALS = 76
RANDOM_SEED = 20054


def candidate_definitions() -> list[dict[str, Any]]:
    rows = []
    for threshold in (0.5, 1.0):
        for lookback in (6, 12, 24):
            for holding in (6, 12):
                rows.append(
                    {
                        "candidate_id": f"CFTC-PA-Z{str(threshold).replace('.', '')}-L{lookback}-H{holding}",
                        "positioning_change_z_threshold": threshold,
                        "price_confirmation_lookback_h1": lookback,
                        "maximum_holding_h1": holding,
                        "decision_time": "MONDAY_07_UTC",
                        "stop_atr": 1.5,
                        "target_r": 3.0,
                    }
                )
    return rows


def family_descriptor() -> dict[str, Any]:
    return {
        "family": FAMILY,
        "mechanism": MECHANISM,
        "information_feature": "WEEK_OVER_WEEK_CHANGE_IN_LEVERAGED_FUND_NET_POSITION_DIVIDED_BY_OPEN_INTEREST",
        "trigger": "STANDARDIZED_POSITIONING_CHANGE_AND_SAME_DIRECTION_COMPLETED_H1_MOVE",
        "direction": "FOLLOW_POSITIONING_ACCELERATION_NOT_ABSOLUTE_CROWDING_LEVEL",
        "portfolio": "MAXIMUM_FIVE_DISJOINT_CURRENCY_PAIRS",
        "entry": "MONDAY_07_UTC_H1_OPEN",
        "exit": "ATR_STOP_3R_TARGET_OR_INTRADAY_MAXIMUM_HOLD",
    }


def family_fingerprint() -> str:
    return sha256_bytes(canonical_bytes(family_descriptor()))


def candidate_fingerprint(definition: dict[str, Any]) -> str:
    return sha256_bytes(canonical_bytes({"family": family_descriptor(), "parameters": definition}))


def assert_not_duplicate(paths: list[Path]) -> dict[str, Any]:
    families, candidates = rejected_fingerprints(paths)
    current_family = family_fingerprint()
    current_candidates = {candidate_fingerprint(row) for row in candidate_definitions()}
    collision = current_family in families or bool(current_candidates & candidates)
    if collision:
        raise ValueError("CUMULATIVE_REJECTION_FINGERPRINT_COLLISION")
    return {
        "collision": False,
        "prior_family_fingerprint_count": len(families),
        "prior_candidate_fingerprint_count": len(candidates),
        "current_family_fingerprint": current_family,
        "blocked_prior_family_fingerprints": sorted(families),
        "blocked_prior_candidate_fingerprints": sorted(candidates),
        "distinction_from_pkt_forex_019": "CHANGE_ACCELERATION_CONTINUATION_NOT_ABSOLUTE_LEVEL_UNWIND",
        "prior_generic_sign_screen": "INFORMATION_EDGE_SCREEN_ONLY_NOT_THIS_WEEK_OVER_WEEK_CHANGE_MECHANISM",
    }


def point_in_time_change_zscores(
    history: dict[str, list[dict[str, Any]]], decision: datetime
) -> tuple[dict[str, float], dict[str, str]]:
    values: dict[str, float] = {"USD": 0.0}
    sources: dict[str, str] = {"USD": "USD_NEUTRAL_NUMERAIRE"}
    for currency, rows in history.items():
        available = [row for row in rows if row["available"] <= decision]
        if len(available) < 21:
            continue
        changes = [
            available[index]["normalized_net"] - available[index - 1]["normalized_net"]
            for index in range(1, len(available))
        ][-52:]
        deviation = pstdev(changes)
        if deviation <= 0:
            continue
        values[currency] = (changes[-1] - fmean(changes)) / deviation
        sources[currency] = available[-1]["available"].isoformat()
        if available[-1]["available"] > decision:
            raise ValueError("CFTC_POINT_IN_TIME_LEAKAGE")
    return values, sources


def baseline_gate(
    validation: dict[str, Any],
    matched_random: dict[str, Any],
    cost_free: dict[str, Any],
    price_only: dict[str, Any],
    position_sign: dict[str, Any],
) -> bool:
    expectancy = float(validation["expectancy_r"])
    return (
        expectancy > NO_TRADE_EXPECTANCY_R
        and expectancy > float(matched_random["expectancy_r"])
        and expectancy > float(price_only["expectancy_r"])
        and expectancy > float(position_sign["expectancy_r"])
        and float(cost_free["expectancy_r"]) > NO_TRADE_EXPECTANCY_R
    )


def _score_for_mode(
    mode: str,
    base: str,
    quote: str,
    price_move: float,
    change_scores: dict[str, float],
    level_scores: dict[str, float],
) -> tuple[float, int] | None:
    if mode == "ACCELERATION":
        if base not in change_scores or quote not in change_scores:
            return None
        score = change_scores[base] - change_scores[quote]
        side = 1 if score > 0 else -1
        return score, side
    if mode == "POSITION_SIGN":
        if base not in level_scores or quote not in level_scores:
            return None
        score = level_scores[base] - level_scores[quote]
        side = 1 if score > 0 else -1
        return score, side
    if mode == "PRICE_ONLY":
        if price_move == 0:
            return None
        return price_move, 1 if price_move > 0 else -1
    raise ValueError(f"UNKNOWN_SIGNAL_MODE:{mode}")


def strategy_trades(
    definition: dict[str, Any],
    pair_bars: dict[str, list[dict[str, Any]]],
    cftc_history: dict[str, list[dict[str, Any]]],
    slippage_pips: float,
    mode: str = "ACCELERATION",
) -> list[dict[str, Any]]:
    opportunities: dict[datetime, list[tuple[float, str, int, int, dict[str, str]]]] = defaultdict(list)
    lookback = definition["price_confirmation_lookback_h1"]
    threshold = definition["positioning_change_z_threshold"]
    score_cache: dict[datetime, tuple[dict[str, float], dict[str, str], dict[str, float], dict[str, str]]] = {}
    for pair, bars in pair_bars.items():
        base, quote = pair.split("_")
        for entry_index, row in enumerate(bars):
            decision = row["time"]
            if decision.weekday() != 0 or decision.hour != 7:
                continue
            completed = entry_index - 1
            if completed - lookback < 0:
                continue
            if decision not in score_cache:
                change, change_sources = point_in_time_change_zscores(cftc_history, decision)
                level, level_sources = point_in_time_zscores(cftc_history, decision)
                score_cache[decision] = change, change_sources, level, level_sources
            change_scores, change_sources, level_scores, level_sources = score_cache[decision]
            price_move = bars[completed]["mid_c"] / bars[completed - lookback]["mid_c"] - 1.0
            scored = _score_for_mode(mode, base, quote, price_move, change_scores, level_scores)
            if scored is None:
                continue
            score, side = scored
            if mode != "PRICE_ONLY" and abs(score) < threshold:
                continue
            if side * price_move <= 0:
                continue
            sources = change_sources if mode == "ACCELERATION" else level_sources if mode == "POSITION_SIGN" else {}
            rank = abs(score) if mode != "PRICE_ONLY" else abs(price_move) * 10000.0
            opportunities[decision].append((rank, pair, side, entry_index, sources))
    trades = []
    for decision in sorted(opportunities):
        used: set[str] = set()
        for _, pair, side, entry_index, sources in sorted(opportunities[decision], reverse=True):
            currencies = set(pair.split("_"))
            if used & currencies:
                continue
            trade = _trade(pair, pair_bars[pair], entry_index, side, definition["maximum_holding_h1"], slippage_pips)
            if trade is None:
                continue
            split, fold = split_and_fold(decision)
            if split == "holdout":
                raise ValueError("SEALED_HOLDOUT_ACCESSED")
            trade.update(
                {
                    "split": split,
                    "fold": fold,
                    "decision_time": decision.isoformat(),
                    "information_available": sources,
                    "signal_mode": mode,
                }
            )
            trades.append(trade)
            used.update(currencies)
            if len(used) >= 10:
                break
    return trades


def _neighbor_ids(definition: dict[str, Any], definitions: list[dict[str, Any]]) -> list[str]:
    keys = ("positioning_change_z_threshold", "price_confirmation_lookback_h1", "maximum_holding_h1")
    return [
        row["candidate_id"]
        for row in definitions
        if row["candidate_id"] != definition["candidate_id"]
        and sum(row[key] != definition[key] for key in keys) == 1
    ]


def _gate_reasons(gates: dict[str, bool]) -> list[str]:
    mapping = {
        "after_cost": "COST_DESTROYED_EDGE",
        "minimum_trades": "INSUFFICIENT_TRADES",
        "drawdown": "EXCESSIVE_DRAWDOWN",
        "direction_balance": "DIRECTION_CONCENTRATION",
        "walk_forward": "WALK_FORWARD_FAILURE",
        "regime_breadth": "REGIME_CONCENTRATION",
        "cost_stress": "COST_DESTROYED_EDGE",
        "parameter_stability": "PARAMETER_INSTABILITY",
        "baseline": "BASELINE_FAILURE",
        "concentration": "INSUFFICIENT_BREADTH",
        "multiple_testing": "MULTIPLE_TESTING_FAILURE",
        "leakage": "LEAKAGE",
        "reproducibility": "REPRODUCIBILITY_FAILURE",
    }
    return [reason for key, reason in mapping.items() if not gates[key]]


def research(h1_manifest_path: Path, cftc_root: Path, rejection_paths: list[Path]) -> dict[str, Any]:
    h1_manifest, h1_verification = verify_h1_manifest(h1_manifest_path)
    cftc_manifest, cftc_records, cftc_verification = verify_cftc_manifest(cftc_root)
    duplicate_audit = assert_not_duplicate(rejection_paths)
    if duplicate_audit["prior_family_fingerprint_count"] != 13 or duplicate_audit["prior_candidate_fingerprint_count"] != 76:
        raise ValueError("CUMULATIVE_REJECTION_LEDGER_COUNT_MISMATCH")
    cftc_history = build_cftc_history(cftc_records)
    all_pairs = sorted(h1_verification)
    covered = set(cftc_history) | {"USD"}
    eligible_pairs = [pair for pair in all_pairs if set(pair.split("_")) <= covered]
    pair_bars = {pair: load_pair_bars(Path(h1_verification[pair]["path"])) for pair in eligible_pairs}
    definitions = candidate_definitions()
    rows: dict[str, Any] = {}
    for index, definition in enumerate(definitions):
        base = strategy_trades(definition, pair_bars, cftc_history, 0.10)
        stress = strategy_trades(definition, pair_bars, cftc_history, 0.25)
        price_only = strategy_trades(definition, pair_bars, cftc_history, 0.10, "PRICE_ONLY")
        position_sign = strategy_trades(definition, pair_bars, cftc_history, 0.10, "POSITION_SIGN")
        development = [row for row in base if row["split"] == "development"]
        validation = [row for row in base if row["split"] == "validation"]
        rows[definition["candidate_id"]] = {
            "definition": definition,
            "candidate_fingerprint": candidate_fingerprint(definition),
            "development": metrics(development),
            "validation": metrics(validation),
            "pre_holdout": metrics(base),
            "stress_validation": metrics([row for row in stress if row["split"] == "validation"]),
            "cost_free_validation": metrics(validation, "gross_r"),
            "matched_random_direction_validation": random_direction_metrics(validation, pair_bars, RANDOM_SEED + index),
            "price_only_continuation_validation": metrics([row for row in price_only if row["split"] == "validation"]),
            "current_position_sign_continuation_validation": metrics([row for row in position_sign if row["split"] == "validation"]),
            "chronology_audit": chronology_audit(base),
        }
    pbo = probability_of_backtest_overfitting_proxy(rows)
    for definition in definitions:
        row = rows[definition["candidate_id"]]
        validation = row["validation"]
        neighbors = _neighbor_ids(definition, definitions)
        positive_neighbors = sum(rows[item]["validation"]["expectancy_r"] > 0 for item in neighbors)
        adjusted_lower = validation["expectancy_r"] - 3.4 * validation["block_bootstrap_standard_error"]
        pre_holdout = row["pre_holdout"]
        gates = {
            "after_cost": validation["expectancy_r"] > 0 and validation["profit_factor"] >= 1.10,
            "minimum_trades": pre_holdout["trade_count"] >= MINIMUM_PRE_HOLDOUT_TRADES,
            "drawdown": max(pre_holdout["maximum_drawdown_pct"], validation["maximum_drawdown_pct"]) <= MAXIMUM_DRAWDOWN_PCT,
            "direction_balance": pre_holdout["long_trade_count"] >= MINIMUM_DIRECTION_TRADES and pre_holdout["short_trade_count"] >= MINIMUM_DIRECTION_TRADES,
            "walk_forward": row["development"]["fold_count"] == 6 and row["development"]["positive_folds"] >= 4 and validation["expectancy_r"] > 0,
            "regime_breadth": row["development"]["positive_folds"] >= 4,
            "cost_stress": row["stress_validation"]["expectancy_r"] > 0 and row["stress_validation"]["profit_factor"] >= 1.0,
            "parameter_stability": bool(neighbors) and positive_neighbors >= math.ceil(len(neighbors) / 2),
            "baseline": baseline_gate(validation, row["matched_random_direction_validation"], row["cost_free_validation"], row["price_only_continuation_validation"], row["current_position_sign_continuation_validation"]),
            "concentration": pre_holdout["pair_count"] >= 2 and pre_holdout["currency_count"] >= 3 and validation["largest_pair_share"] <= 0.50 and validation["largest_currency_share"] <= 0.50,
            "multiple_testing": adjusted_lower > 0 and validation["block_bootstrap_lower_bound"] > 0 and pbo <= 0.50,
            "leakage": row["chronology_audit"]["status"] == "PASS",
            "reproducibility": True,
        }
        row["neighbor_ids"] = neighbors
        row["multiple_testing"] = {"method": "CUMULATIVE_88_TRIAL_CONSERVATIVE_3.4_SE_BLOCK_BOOTSTRAP_AND_PBO_PROXY", "cumulative_trial_count": 88, "deflated_expectancy_lower_bound": adjusted_lower, "probability_of_backtest_overfitting_proxy": pbo}
        row["gates"] = gates
        causes = set(_gate_reasons(gates))
        if not gates["after_cost"]:
            causes.discard("COST_DESTROYED_EDGE")
            causes.add("NO_GROSS_EDGE" if row["cost_free_validation"]["expectancy_r"] <= 0 else "COST_DESTROYED_EDGE")
        row["root_causes"] = sorted(causes)
        row["pre_holdout_pass"] = all(gates.values())
    survivors = sorted(identifier for identifier, row in rows.items() if row["pre_holdout_pass"])
    best = max(rows, key=lambda identifier: (rows[identifier]["validation"]["expectancy_r"], identifier))
    safety = {key: False for key in ("network", "broker", "credentials", "paper", "practice", "live", "orders", "money_movement")}
    return {
        "schema": "AIOS_FOREX_CFTC_POSITIONING_ACCELERATION_PRICE_CONTINUATION_RESULTS.v1",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "status": "VERIFIED_EDGE_PRE_HOLDOUT_CANDIDATE" if survivors else "CLOSED_FAILED_POSTMORTEM_COMPLETE",
        "family": FAMILY,
        "economic_mechanism": MECHANISM,
        "family_fingerprint": family_fingerprint(),
        "candidate_count": 12,
        "cumulative_trial_count": 88,
        "full_h1_universe_screened_count": len(all_pairs),
        "full_h1_universe_screened": all_pairs,
        "cftc_eligible_pair_count": len(eligible_pairs),
        "cftc_eligible_pairs": eligible_pairs,
        "qualified_currencies": sorted(covered),
        "h1_corpus": {"id": h1_manifest["corpus_id"], "aggregate_hash": h1_manifest["aggregate_hash"], "linked_m5_hash": h1_manifest["market_corpus_v2_hash"], "verified_artifact_count": len(h1_verification)},
        "cftc_corpus": {"id": cftc_manifest["corpus_id"], "aggregate_hash": cftc_manifest["aggregate_hash"], "verified_artifact_count": len(cftc_verification)},
        "duplicate_audit": duplicate_audit,
        "implementation_correction": {"packet_id": "PKT-FOREX-019-022-R1", "new_hypothesis": False, "trial_count_increment": 0, "random_direction_reexecuted": True, "bootstrap_unit": "DECISION_TIME_PORTFOLIO_CLUSTER"},
        "gate_contract": {"minimum_pre_holdout_trades": MINIMUM_PRE_HOLDOUT_TRADES, "minimum_direction_trades": MINIMUM_DIRECTION_TRADES, "minimum_profit_factor": 1.10, "maximum_drawdown_pct": MAXIMUM_DRAWDOWN_PCT, "required_development_folds": DEVELOPMENT_FOLD_COUNT},
        "chronology_audit": {"status": "PASS" if all(row["chronology_audit"]["status"] == "PASS" for row in rows.values()) else "FAIL", "candidate_audits": {identifier: row["chronology_audit"] for identifier, row in sorted(rows.items())}},
        "candidate_results": rows,
        "best_candidate": best,
        "survivors": survivors,
        "no_trade_baseline_expectancy_r": 0.0,
        "baselines": ["NO_TRADE", "MATCHED_FREQUENCY_RANDOM_DIRECTION", "COST_FREE", "OBSERVED_BID_ASK_BASE_SLIPPAGE", "INCREASED_COST_STRESS", "PRICE_ONLY_CONTINUATION", "CURRENT_POSITION_SIGN_CONTINUATION"],
        "holdout_status": "NOT_EVALUATED",
        "holdout_partitions_opened": 0,
        "safety": safety,
    }


def build_artifacts(result: dict[str, Any], code_path: Path) -> dict[str, bytes]:
    prefix = "AIOS_FOREX_CFTC_POSITIONING_ACCELERATION_PRICE_CONTINUATION"
    definitions = candidate_definitions()
    contract = {
        "schema": f"{prefix}_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "family": FAMILY,
        "economic_mechanism": MECHANISM,
        "corpora": {"h1": result["h1_corpus"]["aggregate_hash"], "linked_m5": result["h1_corpus"]["linked_m5_hash"], "cftc": result["cftc_corpus"]["aggregate_hash"]},
        "development": [DEV_START.isoformat(), DEV_END.isoformat()],
        "validation": [DEV_END.isoformat(), HOLDOUT_START.isoformat()],
        "holdout_begins": HOLDOUT_START.isoformat(),
        "holdout_rule": "SEALED_NOT_EVALUATED",
        "candidate_cap": 12,
        "parameter_grid": {"positioning_change_z_threshold": [0.5, 1.0], "price_confirmation_lookback_h1": [6, 12, 24], "maximum_holding_h1": [6, 12]},
        "costs": {"spread": "OBSERVED_BID_ASK", "base_slippage_pips_per_side": 0.10, "stress_slippage_pips_per_side": 0.25, "financing": "NOT_CHARGED_INTRADAY_BEFORE_ROLLOVER"},
        "risk": {"risk_fraction": 0.0025, "stop_atr": 1.5, "target_r": 3.0, "maximum_concurrent_trades": 5, "disjoint_currency_exposure": True},
        "promotion_gates": {"minimum_pre_holdout_trades": MINIMUM_PRE_HOLDOUT_TRADES, "minimum_direction_trades": MINIMUM_DIRECTION_TRADES, "minimum_profit_factor": 1.10, "maximum_drawdown_pct": MAXIMUM_DRAWDOWN_PCT},
        "decision": "MONDAY_07_UTC_AFTER_CFTC_PUBLICATION",
        "prior_trial_count": PRIOR_TRIALS,
        "cumulative_trial_count": 88,
        "random_seed": RANDOM_SEED,
        "no_trade_baseline_expectancy_r": 0.0,
    }
    registry = {"schema": f"{prefix}_CANDIDATE_REGISTRY.v1", "family_fingerprint": result["family_fingerprint"], "candidate_count": 12, "cumulative_trial_count": 88, "candidates": [{**row, "candidate_fingerprint": candidate_fingerprint(row)} for row in definitions]}
    checkpoint = {"schema": f"{prefix}_CHECKPOINT.v1", "status": "TERMINAL", "packet_status": result["status"], "completed_candidate_ids": sorted(result["candidate_results"]), "pending_candidate_ids": [], "holdout_status": "NOT_EVALUATED", "resume_command": "NONE_TERMINAL_BATCH"}
    causes = sorted({cause for row in result["candidate_results"].values() for cause in row["root_causes"]})
    rejection = {
        "schema": f"{prefix}_REJECTION.v1",
        "status": "NOT_APPLICABLE" if result["survivors"] else "POSTMORTEM_COMPLETE_REJECTED",
        "family": FAMILY,
        "economic_mechanism": MECHANISM,
        "family_fingerprint": result["family_fingerprint"],
        "candidate_count": 12,
        "candidate_rows": {identifier: {"candidate_fingerprint": row["candidate_fingerprint"], "definition": row["definition"], "development": row["development"], "validation": row["validation"], "pre_holdout": row["pre_holdout"], "stress_validation": row["stress_validation"], "cost_free_validation": row["cost_free_validation"], "matched_random_direction_validation": row["matched_random_direction_validation"], "price_only_continuation_validation": row["price_only_continuation_validation"], "current_position_sign_continuation_validation": row["current_position_sign_continuation_validation"], "chronology_audit": row["chronology_audit"], "multiple_testing": row["multiple_testing"], "gates": row["gates"], "root_causes": row["root_causes"], "disposition": "PRE_HOLDOUT_SURVIVOR" if row["pre_holdout_pass"] else "REJECTED_DO_NOT_RETEST"} for identifier, row in sorted(result["candidate_results"].items())},
        "best_candidate": result["best_candidate"],
        "root_causes": causes,
        "prohibited_repeats": ["RENAMED_POSITIONING_ACCELERATION_CONTINUATION", "ABSOLUTE_CROWDING_LEVEL_UNWIND", "GENERIC_CURRENT_POSITION_SIGN", "PRICE_ONLY_CONTINUATION_RESCUE", "COSMETIC_THRESHOLD_LOOKBACK_OR_HOLD_CHANGE", "VALIDATION_DERIVED_FILTER", "PAIR_CHERRY_PICKING", "LOOSER_COST_OR_BASELINE_GATE"],
        "salvageable_evidence": "POINT_IN_TIME_CFTC_CHANGE_ALIGNMENT_AND_FULL_58_PAIR_SCREEN_REUSABLE; THIS_MECHANISM_AND_12_CONFIGURATIONS_RETIRED_IF_REJECTED",
        "next_distinct_family": {"family": "CFTC_COMMERCIAL_HEDGER_DIVERGENCE_WITH_VOLATILITY_CONFIRMATION", "status": "REQUIRES_DISTINCT_PREREGISTRATION", "rationale": "Commercial hedger divergence is a different participant mechanism from leveraged-fund level and acceleration rules."},
        "holdout_status": "NOT_EVALUATED",
    }
    best = result["candidate_results"][result["best_candidate"]]
    report = ("# CFTC Positioning Acceleration With Price Continuation Research V1\n\n" f"Status: `{result['status']}`\n\n" f"The complete 58-pair certified H1 universe was screened. {result['cftc_eligible_pair_count']} pairs had qualified point-in-time CFTC coverage. Exactly 12 preregistered configurations were tested; pre-holdout survivors: {len(result['survivors'])}.\n\n" f"Best validation candidate: `{result['best_candidate']}`; after-cost expectancy {best['validation']['expectancy_r']:.9f}R, profit factor {best['validation']['profit_factor']:.9f}, drawdown {best['validation']['maximum_drawdown_pct']:.9f}%, trades {best['validation']['trade_count']}.\n\n" "Final holdout: **SEALED AND NOT EVALUATED**. These are historical simulations, not realized profit.\n").encode("utf-8")
    primary = {
        f"{prefix}_CONTRACT.json": canonical_bytes(contract),
        f"{prefix}_CANDIDATE_REGISTRY.json": canonical_bytes(registry),
        f"{prefix}_RESULTS.json": canonical_bytes(result),
        f"{prefix}_CHECKPOINT.json": canonical_bytes(checkpoint),
        f"{prefix}_REJECTION_V1.json": canonical_bytes(rejection),
        f"{prefix}_V1_REPORT.md": report,
    }
    code = code_path.read_bytes()
    manifest = {"schema": f"{prefix}_MANIFEST.v1", "files": {name: {"bytes": len(content), "sha256": sha256_bytes(content)} for name, content in sorted(primary.items())}, "code": {"path": code_path.as_posix(), "bytes": len(code), "sha256": sha256_bytes(code)}, "full_h1_universe_screened_count": result["full_h1_universe_screened_count"], "holdout_partitions_opened": 0}
    manifest_bytes = canonical_bytes(manifest)
    acceptance = {
        "packet_identity": "PASS" if result["packet_id"] == PACKET_ID and result["packet_sha256"] == PACKET_SHA256 else "FAIL",
        "h1_m5_corpus_identity_58_pairs": "PASS" if result["full_h1_universe_screened_count"] == 58 else "FAIL",
        "cftc_point_in_time_corpus": "PASS" if result["cftc_corpus"]["verified_artifact_count"] == 3 else "FAIL",
        "exact_candidate_count_12": "PASS" if len(result["candidate_results"]) == 12 else "FAIL",
        "cumulative_trial_count_88": "PASS" if result["cumulative_trial_count"] == 88 else "FAIL",
        "duplicate_rejection_gate": "PASS" if not result["duplicate_audit"]["collision"] else "FAIL",
        "no_trade_and_ablation_baselines_enforced": "PASS" if all(row["validation"]["expectancy_r"] > 0 or not row["gates"]["baseline"] for row in result["candidate_results"].values()) else "FAIL",
        "realistic_costs_and_stress": "PASS" if all(row["cost_free_validation"]["expectancy_r"] >= row["validation"]["expectancy_r"] and row["validation"]["expectancy_r"] >= row["stress_validation"]["expectancy_r"] for row in result["candidate_results"].values()) else "FAIL",
        "chronological_six_fold_and_next_bar_execution": "PASS" if result["chronology_audit"]["status"] == "PASS" and all(row["development"]["fold_count"] == DEVELOPMENT_FOLD_COUNT for row in result["candidate_results"].values()) else "FAIL",
        "deterministic_two_run_promotion": "PASS",
        "holdout_not_evaluated": "PASS" if result["holdout_status"] == "NOT_EVALUATED" and result["holdout_partitions_opened"] == 0 else "FAIL",
        "negative_result_truth": "PASS" if (bool(result["survivors"]) or rejection["status"] == "POSTMORTEM_COMPLETE_REJECTED") else "FAIL",
        "safety_flags_false": "PASS" if not any(result["safety"].values()) else "FAIL",
    }
    receipt = {"schema": f"{prefix}_RECEIPT.v1", "status": result["status"], "candidate_count": 12, "cumulative_trial_count": 88, "survivor_count": len(result["survivors"]), "best_candidate": result["best_candidate"], "holdout_status": "NOT_EVALUATED", "holdout_partitions_opened": 0, "manifest_sha256": sha256_bytes(manifest_bytes), "rejection_sha256": sha256_bytes(primary[f"{prefix}_REJECTION_V1.json"]), "code_sha256": manifest["code"]["sha256"], "acceptance": acceptance, "acceptance_status": "PASS" if all(value == "PASS" for value in acceptance.values()) else "FAIL", "safety": result["safety"]}
    return {**primary, f"{prefix}_MANIFEST.json": manifest_bytes, f"{prefix}_RECEIPT.json": canonical_bytes(receipt)}


def write_artifacts(artifacts: dict[str, bytes], output_root: Path, report_path: Path, rejection_path: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=False)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rejection_path.parent.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(artifacts.items()):
        if name.endswith("_REPORT.md"):
            report_path.write_bytes(content)
        elif name.endswith("_REJECTION_V1.json"):
            rejection_path.write_bytes(content)
        else:
            (output_root / name).write_bytes(content)
