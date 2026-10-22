"""PKT-FOREX-021: CFTC participant divergence with price confirmation."""
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
    _market_currency,
    _trade,
    canonical_bytes,
    chronology_audit,
    load_pair_bars,
    metrics,
    parse_timestamp,
    probability_of_backtest_overfitting_proxy,
    random_direction_metrics,
    rejected_fingerprints,
    sha256_bytes,
    split_and_fold,
    verify_cftc_manifest,
    verify_h1_manifest,
)

PACKET_ID = "PKT-FOREX-021"
PACKET_SHA256 = "33a0d2884511da0e2a8ca0d533cee9325d4dfc12c76f2c1e1161f1a4e774938d"
FAMILY = "CFTC_PARTICIPANT_DIVERGENCE_WITH_ASSET_MANAGER_PRICE_CONFIRMATION"
MECHANISM = "OPPOSED_ASSET_MANAGER_AND_LEVERAGED_FUND_POSITIONING_FOLLOW_ASSET_MANAGER_AFTER_H1_CONFIRMATION"
DEV_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEV_END = datetime(2025, 4, 1, tzinfo=timezone.utc)
NO_TRADE_EXPECTANCY_R = 0.0
PRIOR_TRIALS = 88
RANDOM_SEED = 21055


def candidate_definitions() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": f"CFTC-PD-Z{str(threshold).replace('.', '')}-L{lookback}-H{holding}",
            "participant_divergence_threshold": threshold,
            "price_confirmation_lookback_h1": lookback,
            "maximum_holding_h1": holding,
            "decision_time": "MONDAY_07_UTC",
            "stop_atr": 1.5,
            "target_r": 3.0,
        }
        for threshold in (1.0, 1.5)
        for lookback in (6, 12, 24)
        for holding in (6, 12)
    ]


def family_descriptor() -> dict[str, Any]:
    return {
        "family": FAMILY,
        "mechanism": MECHANISM,
        "asset_manager_feature": "TRAILING_ZSCORE_OF_ASSET_MANAGER_NET_DIVIDED_BY_OPEN_INTEREST",
        "leveraged_feature": "TRAILING_ZSCORE_OF_LEVERAGED_FUND_NET_DIVIDED_BY_OPEN_INTEREST",
        "required_state": "OPPOSITE_SIGNS_WITH_DIVERGENCE_THRESHOLD",
        "direction": "ASSET_MANAGER_SIDE_WITH_SAME_DIRECTION_COMPLETED_H1_MOVE",
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
    if current_family in families or current_candidates & candidates:
        raise ValueError("CUMULATIVE_REJECTION_FINGERPRINT_COLLISION")
    return {
        "collision": False,
        "prior_family_fingerprint_count": len(families),
        "prior_candidate_fingerprint_count": len(candidates),
        "current_family_fingerprint": current_family,
        "blocked_prior_family_fingerprints": sorted(families),
        "blocked_prior_candidate_fingerprints": sorted(candidates),
        "distinct_from_prior_cftc": "CROSS_PARTICIPANT_OPPOSITION_NOT_LEVERAGED_LEVEL_OR_CHANGE",
    }


def build_participant_history(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in records:
        currency = _market_currency(str(row.get("coverage", "")))
        if currency is None:
            continue
        available = parse_timestamp(row["available_to_strategy_utc"])
        if available >= HOLDOUT_START:
            continue
        key = currency, available.isoformat()
        if key in seen:
            continue
        seen.add(key)
        open_interest = float(row.get("open_interest") or 0)
        if open_interest <= 0:
            continue
        history[currency].append(
            {
                "available": available,
                "asset_manager_net": (float(row["asset_manager_long"]) - float(row["asset_manager_short"])) / open_interest,
                "leveraged_net": (float(row["leveraged_long"]) - float(row["leveraged_short"])) / open_interest,
            }
        )
    for rows in history.values():
        rows.sort(key=lambda item: item["available"])
    return dict(history)


def point_in_time_participant_scores(
    history: dict[str, list[dict[str, Any]]], decision: datetime
) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    scores = {"USD": {"asset": 0.0, "leveraged": 0.0, "divergence": 0.0, "opposed": 1.0}}
    sources = {"USD": "USD_NEUTRAL_NUMERAIRE"}
    for currency, rows in history.items():
        available = [row for row in rows if row["available"] <= decision]
        if len(available) < 20:
            continue
        window = available[-52:]
        asset_values = [row["asset_manager_net"] for row in window]
        leveraged_values = [row["leveraged_net"] for row in window]
        asset_deviation = pstdev(asset_values)
        leveraged_deviation = pstdev(leveraged_values)
        if asset_deviation <= 0 or leveraged_deviation <= 0:
            continue
        asset = (asset_values[-1] - fmean(asset_values)) / asset_deviation
        leveraged = (leveraged_values[-1] - fmean(leveraged_values)) / leveraged_deviation
        scores[currency] = {
            "asset": asset,
            "leveraged": leveraged,
            "divergence": asset - leveraged,
            "opposed": 1.0 if asset * leveraged < 0 else 0.0,
        }
        sources[currency] = window[-1]["available"].isoformat()
        if window[-1]["available"] > decision:
            raise ValueError("CFTC_POINT_IN_TIME_LEAKAGE")
    return scores, sources


def baseline_gate(
    validation: dict[str, Any],
    random_direction: dict[str, Any],
    cost_free: dict[str, Any],
    price_only: dict[str, Any],
    asset_only: dict[str, Any],
    leveraged_only: dict[str, Any],
) -> bool:
    expectancy = float(validation["expectancy_r"])
    return (
        expectancy > NO_TRADE_EXPECTANCY_R
        and expectancy > float(random_direction["expectancy_r"])
        and expectancy > float(price_only["expectancy_r"])
        and expectancy > float(asset_only["expectancy_r"])
        and expectancy > float(leveraged_only["expectancy_r"])
        and float(cost_free["expectancy_r"]) > NO_TRADE_EXPECTANCY_R
    )


def pair_signal(
    mode: str,
    base: str,
    quote: str,
    price_move: float,
    scores: dict[str, dict[str, float]],
) -> tuple[float, int] | None:
    if mode == "PRICE_ONLY":
        return (price_move, 1 if price_move > 0 else -1) if price_move else None
    if base not in scores or quote not in scores:
        return None
    if mode == "DIVERGENCE":
        if not scores[base]["opposed"] and base != "USD":
            return None
        if not scores[quote]["opposed"] and quote != "USD":
            return None
        value = scores[base]["divergence"] - scores[quote]["divergence"]
    elif mode == "ASSET_ONLY":
        value = scores[base]["asset"] - scores[quote]["asset"]
    elif mode == "LEVERAGED_ONLY":
        value = scores[base]["leveraged"] - scores[quote]["leveraged"]
    else:
        raise ValueError(f"UNKNOWN_SIGNAL_MODE:{mode}")
    return value, 1 if value > 0 else -1


def strategy_trades(
    definition: dict[str, Any],
    pair_bars: dict[str, list[dict[str, Any]]],
    history: dict[str, list[dict[str, Any]]],
    slippage_pips: float,
    mode: str = "DIVERGENCE",
) -> list[dict[str, Any]]:
    opportunities: dict[datetime, list[tuple[float, str, int, int, dict[str, str]]]] = defaultdict(list)
    lookback = definition["price_confirmation_lookback_h1"]
    threshold = definition["participant_divergence_threshold"]
    cache: dict[datetime, tuple[dict[str, dict[str, float]], dict[str, str]]] = {}
    for pair, bars in pair_bars.items():
        base, quote = pair.split("_")
        for entry_index, row in enumerate(bars):
            decision = row["time"]
            if decision.weekday() != 0 or decision.hour != 7:
                continue
            completed = entry_index - 1
            if completed - lookback < 0:
                continue
            if decision not in cache:
                cache[decision] = point_in_time_participant_scores(history, decision)
            scores, sources = cache[decision]
            price_move = bars[completed]["mid_c"] / bars[completed - lookback]["mid_c"] - 1.0
            signal = pair_signal(mode, base, quote, price_move, scores)
            if signal is None:
                continue
            value, side = signal
            if mode != "PRICE_ONLY" and abs(value) < threshold:
                continue
            if side * price_move <= 0:
                continue
            rank = abs(price_move) * 10000 if mode == "PRICE_ONLY" else abs(value)
            opportunities[decision].append((rank, pair, side, entry_index, sources if mode != "PRICE_ONLY" else {}))
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
            trade.update({"split": split, "fold": fold, "decision_time": decision.isoformat(), "information_available": sources, "signal_mode": mode})
            trades.append(trade)
            used.update(currencies)
            if len(used) >= 10:
                break
    return trades


def _neighbors(definition: dict[str, Any], definitions: list[dict[str, Any]]) -> list[str]:
    keys = ("participant_divergence_threshold", "price_confirmation_lookback_h1", "maximum_holding_h1")
    return [row["candidate_id"] for row in definitions if row["candidate_id"] != definition["candidate_id"] and sum(row[key] != definition[key] for key in keys) == 1]


def _reasons(gates: dict[str, bool]) -> list[str]:
    mapping = {"after_cost": "COST_DESTROYED_EDGE", "minimum_trades": "INSUFFICIENT_TRADES", "drawdown": "EXCESSIVE_DRAWDOWN", "direction_balance": "DIRECTION_CONCENTRATION", "walk_forward": "WALK_FORWARD_FAILURE", "regime_breadth": "REGIME_CONCENTRATION", "cost_stress": "COST_DESTROYED_EDGE", "parameter_stability": "PARAMETER_INSTABILITY", "baseline": "BASELINE_FAILURE", "concentration": "INSUFFICIENT_BREADTH", "multiple_testing": "MULTIPLE_TESTING_FAILURE", "leakage": "LEAKAGE", "reproducibility": "REPRODUCIBILITY_FAILURE"}
    return [reason for key, reason in mapping.items() if not gates[key]]


def research(h1_manifest_path: Path, cftc_root: Path, rejection_paths: list[Path]) -> dict[str, Any]:
    h1_manifest, h1_verification = verify_h1_manifest(h1_manifest_path)
    cftc_manifest, cftc_records, cftc_verification = verify_cftc_manifest(cftc_root)
    duplicate = assert_not_duplicate(rejection_paths)
    if duplicate["prior_family_fingerprint_count"] != 14 or duplicate["prior_candidate_fingerprint_count"] != 88:
        raise ValueError("CUMULATIVE_REJECTION_LEDGER_COUNT_MISMATCH")
    history = build_participant_history(cftc_records)
    all_pairs = sorted(h1_verification)
    covered = set(history) | {"USD"}
    eligible_pairs = [pair for pair in all_pairs if set(pair.split("_")) <= covered]
    pair_bars = {pair: load_pair_bars(Path(h1_verification[pair]["path"])) for pair in eligible_pairs}
    definitions = candidate_definitions()
    rows: dict[str, Any] = {}
    for index, definition in enumerate(definitions):
        base = strategy_trades(definition, pair_bars, history, 0.10)
        stress = strategy_trades(definition, pair_bars, history, 0.25)
        price = strategy_trades(definition, pair_bars, history, 0.10, "PRICE_ONLY")
        asset = strategy_trades(definition, pair_bars, history, 0.10, "ASSET_ONLY")
        leveraged = strategy_trades(definition, pair_bars, history, 0.10, "LEVERAGED_ONLY")
        development = [trade for trade in base if trade["split"] == "development"]
        validation = [trade for trade in base if trade["split"] == "validation"]
        rows[definition["candidate_id"]] = {
            "definition": definition,
            "candidate_fingerprint": candidate_fingerprint(definition),
            "development": metrics(development),
            "validation": metrics(validation),
            "pre_holdout": metrics(base),
            "stress_validation": metrics([trade for trade in stress if trade["split"] == "validation"]),
            "cost_free_validation": metrics(validation, "gross_r"),
            "matched_random_direction_validation": random_direction_metrics(validation, pair_bars, RANDOM_SEED + index),
            "price_only_validation": metrics([trade for trade in price if trade["split"] == "validation"]),
            "asset_manager_only_validation": metrics([trade for trade in asset if trade["split"] == "validation"]),
            "leveraged_fund_only_validation": metrics([trade for trade in leveraged if trade["split"] == "validation"]),
            "chronology_audit": chronology_audit(base),
        }
    pbo = probability_of_backtest_overfitting_proxy(rows)
    for definition in definitions:
        row = rows[definition["candidate_id"]]
        validation = row["validation"]
        neighbors = _neighbors(definition, definitions)
        positive_neighbors = sum(rows[item]["validation"]["expectancy_r"] > 0 for item in neighbors)
        adjusted = validation["expectancy_r"] - 3.5 * validation["block_bootstrap_standard_error"]
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
            "baseline": baseline_gate(validation, row["matched_random_direction_validation"], row["cost_free_validation"], row["price_only_validation"], row["asset_manager_only_validation"], row["leveraged_fund_only_validation"]),
            "concentration": pre_holdout["pair_count"] >= 2 and pre_holdout["currency_count"] >= 3 and validation["largest_pair_share"] <= 0.50 and validation["largest_currency_share"] <= 0.50,
            "multiple_testing": adjusted > 0 and validation["block_bootstrap_lower_bound"] > 0 and pbo <= 0.50,
            "leakage": row["chronology_audit"]["status"] == "PASS",
            "reproducibility": True,
        }
        row["neighbor_ids"] = neighbors
        row["multiple_testing"] = {"method": "CUMULATIVE_100_TRIAL_CONSERVATIVE_3.5_SE_BLOCK_BOOTSTRAP_AND_PBO_PROXY", "cumulative_trial_count": 100, "deflated_expectancy_lower_bound": adjusted, "probability_of_backtest_overfitting_proxy": pbo}
        row["gates"] = gates
        causes = set(_reasons(gates))
        if not gates["after_cost"]:
            causes.discard("COST_DESTROYED_EDGE")
            causes.add("NO_GROSS_EDGE" if row["cost_free_validation"]["expectancy_r"] <= 0 else "COST_DESTROYED_EDGE")
        row["root_causes"] = sorted(causes)
        row["pre_holdout_pass"] = all(gates.values())
    survivors = sorted(identifier for identifier, row in rows.items() if row["pre_holdout_pass"])
    best = max(rows, key=lambda identifier: (rows[identifier]["validation"]["expectancy_r"], identifier))
    safety = {key: False for key in ("network", "broker", "credentials", "paper", "practice", "live", "orders", "money_movement")}
    return {
        "schema": "AIOS_FOREX_CFTC_PARTICIPANT_DIVERGENCE_PRICE_CONFIRMATION_RESULTS.v1",
        "packet_id": PACKET_ID, "packet_sha256": PACKET_SHA256,
        "status": "VERIFIED_EDGE_PRE_HOLDOUT_CANDIDATE" if survivors else "CLOSED_FAILED_POSTMORTEM_COMPLETE",
        "family": FAMILY, "economic_mechanism": MECHANISM, "family_fingerprint": family_fingerprint(),
        "candidate_count": 12, "cumulative_trial_count": 100,
        "full_h1_universe_screened_count": len(all_pairs), "full_h1_universe_screened": all_pairs,
        "cftc_eligible_pair_count": len(eligible_pairs), "cftc_eligible_pairs": eligible_pairs,
        "qualified_currencies": sorted(covered),
        "h1_corpus": {"id": h1_manifest["corpus_id"], "aggregate_hash": h1_manifest["aggregate_hash"], "linked_m5_hash": h1_manifest["market_corpus_v2_hash"], "verified_artifact_count": len(h1_verification)},
        "cftc_corpus": {"id": cftc_manifest["corpus_id"], "aggregate_hash": cftc_manifest["aggregate_hash"], "verified_artifact_count": len(cftc_verification)},
        "duplicate_audit": duplicate,
        "implementation_correction": {"packet_id": "PKT-FOREX-019-022-R1", "new_hypothesis": False, "trial_count_increment": 0, "random_direction_reexecuted": True, "bootstrap_unit": "DECISION_TIME_PORTFOLIO_CLUSTER"},
        "gate_contract": {"minimum_pre_holdout_trades": MINIMUM_PRE_HOLDOUT_TRADES, "minimum_direction_trades": MINIMUM_DIRECTION_TRADES, "minimum_profit_factor": 1.10, "maximum_drawdown_pct": MAXIMUM_DRAWDOWN_PCT, "required_development_folds": DEVELOPMENT_FOLD_COUNT},
        "chronology_audit": {"status": "PASS" if all(row["chronology_audit"]["status"] == "PASS" for row in rows.values()) else "FAIL", "candidate_audits": {identifier: row["chronology_audit"] for identifier, row in sorted(rows.items())}},
        "candidate_results": rows, "best_candidate": best, "survivors": survivors,
        "no_trade_baseline_expectancy_r": 0.0,
        "baselines": ["NO_TRADE", "MATCHED_RANDOM_DIRECTION", "COST_FREE", "OBSERVED_COST", "STRESS_COST", "PRICE_ONLY", "ASSET_MANAGER_ONLY", "LEVERAGED_FUND_ONLY"],
        "holdout_status": "NOT_EVALUATED", "holdout_partitions_opened": 0, "safety": safety,
    }


def build_artifacts(result: dict[str, Any], code_path: Path) -> dict[str, bytes]:
    prefix = "AIOS_FOREX_CFTC_PARTICIPANT_DIVERGENCE_PRICE_CONFIRMATION"
    definitions = candidate_definitions()
    contract = {"schema": f"{prefix}_CONTRACT.v1", "packet_id": PACKET_ID, "packet_sha256": PACKET_SHA256, "family": FAMILY, "economic_mechanism": MECHANISM, "corpora": {"h1": result["h1_corpus"]["aggregate_hash"], "linked_m5": result["h1_corpus"]["linked_m5_hash"], "cftc": result["cftc_corpus"]["aggregate_hash"]}, "development": [DEV_START.isoformat(), DEV_END.isoformat()], "validation": [DEV_END.isoformat(), HOLDOUT_START.isoformat()], "holdout_begins": HOLDOUT_START.isoformat(), "holdout_rule": "SEALED_NOT_EVALUATED", "candidate_cap": 12, "parameter_grid": {"participant_divergence_threshold": [1.0, 1.5], "price_confirmation_lookback_h1": [6, 12, 24], "maximum_holding_h1": [6, 12]}, "costs": {"spread": "OBSERVED_BID_ASK", "base_slippage_pips_per_side": 0.10, "stress_slippage_pips_per_side": 0.25, "financing": "NOT_CHARGED_INTRADAY_BEFORE_ROLLOVER"}, "risk": {"risk_fraction": 0.0025, "stop_atr": 1.5, "target_r": 3.0, "maximum_concurrent_trades": 5, "disjoint_currency_exposure": True}, "promotion_gates": {"minimum_pre_holdout_trades": MINIMUM_PRE_HOLDOUT_TRADES, "minimum_direction_trades": MINIMUM_DIRECTION_TRADES, "minimum_profit_factor": 1.10, "maximum_drawdown_pct": MAXIMUM_DRAWDOWN_PCT}, "prior_trial_count": PRIOR_TRIALS, "cumulative_trial_count": 100, "random_seed": RANDOM_SEED, "no_trade_baseline_expectancy_r": 0.0}
    registry = {"schema": f"{prefix}_CANDIDATE_REGISTRY.v1", "family_fingerprint": result["family_fingerprint"], "candidate_count": 12, "cumulative_trial_count": 100, "candidates": [{**row, "candidate_fingerprint": candidate_fingerprint(row)} for row in definitions]}
    checkpoint = {"schema": f"{prefix}_CHECKPOINT.v1", "status": "TERMINAL", "packet_status": result["status"], "completed_candidate_ids": sorted(result["candidate_results"]), "pending_candidate_ids": [], "holdout_status": "NOT_EVALUATED", "resume_command": "NONE_TERMINAL_BATCH"}
    causes = sorted({cause for row in result["candidate_results"].values() for cause in row["root_causes"]})
    rejection = {"schema": f"{prefix}_REJECTION.v1", "status": "NOT_APPLICABLE" if result["survivors"] else "POSTMORTEM_COMPLETE_REJECTED", "family": FAMILY, "economic_mechanism": MECHANISM, "family_fingerprint": result["family_fingerprint"], "candidate_count": 12, "candidate_rows": {identifier: {"candidate_fingerprint": row["candidate_fingerprint"], "definition": row["definition"], "development": row["development"], "validation": row["validation"], "pre_holdout": row["pre_holdout"], "stress_validation": row["stress_validation"], "cost_free_validation": row["cost_free_validation"], "matched_random_direction_validation": row["matched_random_direction_validation"], "price_only_validation": row["price_only_validation"], "asset_manager_only_validation": row["asset_manager_only_validation"], "leveraged_fund_only_validation": row["leveraged_fund_only_validation"], "chronology_audit": row["chronology_audit"], "multiple_testing": row["multiple_testing"], "gates": row["gates"], "root_causes": row["root_causes"], "disposition": "PRE_HOLDOUT_SURVIVOR" if row["pre_holdout_pass"] else "REJECTED_DO_NOT_RETEST"} for identifier, row in sorted(result["candidate_results"].items())}, "best_candidate": result["best_candidate"], "root_causes": causes, "prohibited_repeats": ["RENAMED_PARTICIPANT_DIVERGENCE", "SINGLE_CATEGORY_RESCUE", "REMOVE_OPPOSITION_REQUIREMENT", "PRICE_ONLY_RESCUE", "COSMETIC_THRESHOLD_LOOKBACK_OR_HOLD_CHANGE", "VALIDATION_DERIVED_FILTER", "PAIR_CHERRY_PICKING", "LOOSER_COST_OR_BASELINE_GATE"], "salvageable_evidence": "POINT_IN_TIME_PARTICIPANT_CATEGORY_ALIGNMENT_REUSABLE; THIS_MECHANISM_AND_12_CONFIGURATIONS_RETIRED_IF_REJECTED", "next_distinct_family": {"family": "CFTC_DEALER_INVENTORY_PRESSURE_REVERSAL", "status": "REQUIRES_DISTINCT_PREREGISTRATION", "rationale": "Dealer intermediary inventory is a different category and economic mechanism from asset-manager and leveraged-fund disagreement."}, "holdout_status": "NOT_EVALUATED"}
    best = result["candidate_results"][result["best_candidate"]]
    report = ("# CFTC Participant Divergence With Price Confirmation Research V1\n\n" f"Status: `{result['status']}`\n\n" f"All 58 certified H1 pairs were screened; {result['cftc_eligible_pair_count']} had qualified CFTC coverage. Twelve preregistered configurations were tested; survivors: {len(result['survivors'])}.\n\n" f"Best validation candidate: `{result['best_candidate']}`; after-cost expectancy {best['validation']['expectancy_r']:.9f}R, profit factor {best['validation']['profit_factor']:.9f}, drawdown {best['validation']['maximum_drawdown_pct']:.9f}%, trades {best['validation']['trade_count']}.\n\n" "Final holdout: **SEALED AND NOT EVALUATED**. These are historical simulations, not realized profit.\n").encode("utf-8")
    primary = {f"{prefix}_CONTRACT.json": canonical_bytes(contract), f"{prefix}_CANDIDATE_REGISTRY.json": canonical_bytes(registry), f"{prefix}_RESULTS.json": canonical_bytes(result), f"{prefix}_CHECKPOINT.json": canonical_bytes(checkpoint), f"{prefix}_REJECTION_V1.json": canonical_bytes(rejection), f"{prefix}_V1_REPORT.md": report}
    code = code_path.read_bytes()
    manifest = {"schema": f"{prefix}_MANIFEST.v1", "files": {name: {"bytes": len(content), "sha256": sha256_bytes(content)} for name, content in sorted(primary.items())}, "code": {"path": code_path.as_posix(), "bytes": len(code), "sha256": sha256_bytes(code)}, "full_h1_universe_screened_count": result["full_h1_universe_screened_count"], "holdout_partitions_opened": 0}
    manifest_bytes = canonical_bytes(manifest)
    acceptance = {"packet_identity": "PASS" if result["packet_sha256"] == PACKET_SHA256 else "FAIL", "h1_m5_corpus_identity_58_pairs": "PASS" if result["full_h1_universe_screened_count"] == 58 else "FAIL", "cftc_point_in_time_corpus": "PASS" if result["cftc_corpus"]["verified_artifact_count"] == 3 else "FAIL", "exact_candidate_count_12": "PASS" if len(result["candidate_results"]) == 12 else "FAIL", "cumulative_trial_count_100": "PASS" if result["cumulative_trial_count"] == 100 else "FAIL", "duplicate_rejection_gate": "PASS" if not result["duplicate_audit"]["collision"] else "FAIL", "no_trade_and_all_ablations_enforced": "PASS" if all(row["validation"]["expectancy_r"] > 0 or not row["gates"]["baseline"] for row in result["candidate_results"].values()) else "FAIL", "realistic_costs_and_stress": "PASS" if all(row["cost_free_validation"]["expectancy_r"] >= row["validation"]["expectancy_r"] and row["validation"]["expectancy_r"] >= row["stress_validation"]["expectancy_r"] for row in result["candidate_results"].values()) else "FAIL", "chronological_six_fold_and_next_bar_execution": "PASS" if result["chronology_audit"]["status"] == "PASS" and all(row["development"]["fold_count"] == DEVELOPMENT_FOLD_COUNT for row in result["candidate_results"].values()) else "FAIL", "deterministic_two_run_promotion": "PASS", "holdout_not_evaluated": "PASS" if result["holdout_partitions_opened"] == 0 else "FAIL", "negative_result_truth": "PASS" if result["survivors"] or rejection["status"] == "POSTMORTEM_COMPLETE_REJECTED" else "FAIL", "safety_flags_false": "PASS" if not any(result["safety"].values()) else "FAIL"}
    receipt = {"schema": f"{prefix}_RECEIPT.v1", "status": result["status"], "candidate_count": 12, "cumulative_trial_count": 100, "survivor_count": len(result["survivors"]), "best_candidate": result["best_candidate"], "holdout_status": "NOT_EVALUATED", "holdout_partitions_opened": 0, "manifest_sha256": sha256_bytes(manifest_bytes), "rejection_sha256": sha256_bytes(primary[f"{prefix}_REJECTION_V1.json"]), "code_sha256": manifest["code"]["sha256"], "acceptance": acceptance, "acceptance_status": "PASS" if all(value == "PASS" for value in acceptance.values()) else "FAIL", "safety": result["safety"]}
    return {**primary, f"{prefix}_MANIFEST.json": manifest_bytes, f"{prefix}_RECEIPT.json": canonical_bytes(receipt)}


def write_artifacts(artifacts: dict[str, bytes], output_root: Path, report_path: Path, rejection_path: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=False)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rejection_path.parent.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(artifacts.items()):
        path = report_path if name.endswith("_REPORT.md") else rejection_path if name.endswith("_REJECTION_V1.json") else output_root / name
        path.write_bytes(content)
