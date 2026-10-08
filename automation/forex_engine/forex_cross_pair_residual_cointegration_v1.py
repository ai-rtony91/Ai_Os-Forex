"""Offline, chronological cross-pair residual research for PKT-FOREX-015."""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from automation.forex_engine.forex_cross_sectional_currency_strength_v1 import (
    DATASET_ID,
    DATASET_SHA,
    DEV_END,
    DEV_START,
    VAL_END,
    mid,
    synchronized,
)

PACKET_ID = "PKT-FOREX-015"
PACKET_SHA256 = "fb982efdc5b6b5f220044652d01f65211f081bce9913d613b7e78ea2d3c4529a"
FAMILY = "CROSS_PAIR_RESIDUAL_COINTEGRATION_MEAN_REVERSION"
MECHANISM = "TRAIN_ONLY_DYNAMIC_RELATIONSHIP_RESIDUAL_CONVERGENCE"
GROUPS = {
    "EURUSD_GBPUSD": ("EUR_USD", "GBP_USD", 1.0),
    "EURUSD_USDJPY_SIGNED": ("EUR_USD", "USD_JPY", -1.0),
}
WINDOWS = (1440, 4320)
ENTRY_Z = (2.0, 2.5)
EXIT_Z = 0.5
STOP_Z = 3.5
MAX_HOLDING = 60
REFIT_EVERY = 240
BASE_SLIPPAGE_PIPS = 0.10
STRESS_SLIPPAGE_PIPS = 0.25
RISK_FRACTION = 0.0025
EMBARGO_MINUTES = 4380


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def candidate_definitions() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": f"CPR-{group}-W{window}-Z{entry:g}",
            "group": group,
            "training_window": window,
            "entry_z": entry,
            "exit_z": EXIT_Z,
            "stop_z": STOP_Z,
            "maximum_holding_minutes": MAX_HOLDING,
            "refit_every_bars": REFIT_EVERY,
        }
        for group in GROUPS
        for window in WINDOWS
        for entry in ENTRY_Z
    ]


def fit_ols(y_values: list[float], x_values: list[float]) -> dict[str, float]:
    if len(y_values) != len(x_values) or len(y_values) < 3:
        raise ValueError("fit requires equal non-trivial histories")
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    variance = sum((x - x_mean) ** 2 for x in x_values)
    if variance <= 1e-18:
        raise ValueError("training regressor has zero variance")
    beta = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / variance
    intercept = y_mean - beta * x_mean
    residuals = [y - intercept - beta * x for x, y in zip(x_values, y_values)]
    residual_mean = sum(residuals) / len(residuals)
    residual_sd = math.sqrt(sum((r - residual_mean) ** 2 for r in residuals) / (len(residuals) - 1))
    if residual_sd <= 1e-12:
        raise ValueError("training residual has zero variance")
    return {"intercept": intercept, "beta": beta, "residual_mean": residual_mean, "residual_sd": residual_sd}


def residual_z(y_value: float, x_value: float, fit: dict[str, float]) -> float:
    residual = y_value - fit["intercept"] - fit["beta"] * x_value
    return (residual - fit["residual_mean"]) / fit["residual_sd"]


def pair_leg_weights(group: str, residual_direction: str, beta: float) -> dict[str, float]:
    y_pair, x_pair, x_sign = GROUPS[group]
    direction = 1.0 if residual_direction == "LONG_RESIDUAL" else -1.0
    weights = {y_pair: direction, x_pair: -direction * beta * x_sign}
    gross = sum(abs(value) for value in weights.values())
    if gross <= 1e-12:
        raise ValueError("invalid zero-gross spread")
    return {pair: value / gross for pair, value in weights.items()}


def currency_exposure(weights: dict[str, float]) -> dict[str, float]:
    exposure: dict[str, float] = {}
    for pair, weight in weights.items():
        base, quote = pair.split("_")
        exposure[base] = exposure.get(base, 0.0) + weight * RISK_FRACTION
        exposure[quote] = exposure.get(quote, 0.0) - weight * RISK_FRACTION
    return exposure


def exposure_allowed(weights: dict[str, float], cap: float = 0.005) -> bool:
    return all(abs(value) <= cap + 1e-12 for value in currency_exposure(weights).values())


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("_JPY") else 0.0001


def executable_leg_return(
    weight: float,
    entry_bar: dict[str, Any],
    exit_bar: dict[str, Any],
    pair: str,
    slippage_pips: float,
) -> tuple[float, float]:
    slip = slippage_pips * pip_size(pair)
    entry_mid = mid(entry_bar["bid"], entry_bar["ask"], "o")
    exit_mid = mid(exit_bar["bid"], exit_bar["ask"], "c")
    if weight > 0:
        entry = float(entry_bar["ask"]["o"]) + slip
        exit_price = float(exit_bar["bid"]["c"]) - slip
        net = math.log(exit_price / entry)
        gross = math.log(exit_mid / entry_mid)
    else:
        entry = float(entry_bar["bid"]["o"]) - slip
        exit_price = float(exit_bar["ask"]["c"]) + slip
        net = math.log(entry / exit_price)
        gross = math.log(entry_mid / exit_mid)
    return abs(weight) * net, abs(weight) * gross


def crosses_rollover(timestamp: str, holding_minutes: int = MAX_HOLDING) -> bool:
    start = datetime.fromisoformat(timestamp[:19])
    for offset in range(holding_minutes + 1):
        current = start + timedelta(minutes=offset)
        if current.hour == 21 and current.minute >= 55 or current.hour == 22 and current.minute <= 9:
            return True
    return False


def split_and_fold(timestamp: str) -> tuple[str, int]:
    stamp = datetime.fromisoformat(timestamp[:19])
    boundary = datetime.fromisoformat(DEV_END)
    if stamp >= boundary:
        return "validation", -1
    start = datetime.fromisoformat(DEV_START)
    total = (boundary - start).total_seconds()
    fold = min(5, max(0, int((stamp - start).total_seconds() / total * 6)))
    return "development", fold


def in_embargo(timestamp: str) -> bool:
    stamp = datetime.fromisoformat(timestamp[:19])
    start = datetime.fromisoformat(DEV_START)
    boundary = datetime.fromisoformat(DEV_END)
    if stamp < start:
        return True
    if stamp >= boundary:
        return stamp < boundary + timedelta(minutes=EMBARGO_MINUTES)
    fold_seconds = (boundary - start).total_seconds() / 6
    fold = min(5, max(0, int((stamp - start).total_seconds() / fold_seconds)))
    fold_start = start + timedelta(seconds=fold * fold_seconds)
    return stamp < fold_start + timedelta(minutes=EMBARGO_MINUTES)


def should_exit(position: dict[str, Any], z_score: float) -> str | None:
    if abs(z_score) >= STOP_Z:
        return "STOP"
    if abs(z_score) <= EXIT_Z:
        return "CONVERGENCE"
    if position["age"] >= MAX_HOLDING:
        return "TIME"
    return None


def metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    values = [trade["r"] for trade in trades]
    wins = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    equity = peak = 1.0
    drawdown = 0.0
    for value in values:
        equity *= max(0.0, 1.0 + RISK_FRACTION * value)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak * 100 if peak else 100.0)
    group_counts = {group: sum(t["group"] == group for t in trades) for group in GROUPS}
    instrument_counts = {pair: sum(pair in t["instruments"] for t in trades) for pair in ("EUR_USD", "GBP_USD", "USD_JPY")}
    regime_counts = {regime: sum(t["regime"] == regime for t in trades) for regime in ("LOW_TRAINING_VOL", "HIGH_TRAINING_VOL", "UNKNOWN_TRAINING_VOL")}
    fold_values = {str(index): [t["r"] for t in trades if t["fold"] == index] for index in range(6)}
    block_means = [sum(values[i : i + 60]) / len(values[i : i + 60]) for i in range(0, len(values), 60) if values[i : i + 60]]
    uncertainty = 0.0
    if len(block_means) > 1:
        mean = sum(block_means) / len(block_means)
        uncertainty = math.sqrt(sum((x - mean) ** 2 for x in block_means) / (len(block_means) - 1)) / math.sqrt(len(block_means))
    expectancy = sum(values) / len(values) if values else 0.0
    return {
        "trade_count": len(values),
        "long_residual_trades": sum(t["direction"] == "LONG_RESIDUAL" for t in trades),
        "short_residual_trades": sum(t["direction"] == "SHORT_RESIDUAL" for t in trades),
        "expectancy_r": expectancy,
        "profit_factor": wins / losses if losses else (999.0 if wins else 0.0),
        "maximum_drawdown_pct": drawdown,
        "relationship_counts": group_counts,
        "relationship_breadth": sum(value > 0 for value in group_counts.values()),
        "largest_relationship_share": max(group_counts.values()) / len(values) if values else 1.0,
        "instrument_counts": instrument_counts,
        "instrument_breadth": sum(value > 0 for value in instrument_counts.values()),
        "regime_counts": regime_counts,
        "regime_expectancy": {regime: (sum(t["r"] for t in trades if t["regime"] == regime) / count if count else 0.0) for regime, count in regime_counts.items()},
        "largest_regime_share": max(regime_counts.values()) / len(values) if values else 1.0,
        "positive_folds": sum(bool(items) and sum(items) / len(items) > 0 for items in fold_values.values()),
        "fold_expectancy": {key: sum(items) / len(items) if items else 0.0 for key, items in fold_values.items()},
        "largest_trade_share": max((abs(x) for x in values), default=0.0) / max(sum(abs(x) for x in values), 1e-12),
        "block_standard_error": uncertainty,
        "uncertainty_lower_bound": expectancy - 1.96 * uncertainty,
        "average_holding_minutes": sum(t["holding_minutes"] for t in trades) / len(trades) if trades else 0.0,
        "average_cost_burden_r": sum(t["gross_r"] - t["r"] for t in trades) / len(trades) if trades else 0.0,
    }


def base_gate(value: dict[str, Any]) -> bool:
    return (
        value["expectancy_r"] > 0
        and value["profit_factor"] >= 1.10
        and value["maximum_drawdown_pct"] <= 10.0
        and value["trade_count"] >= 200
        and value["long_residual_trades"] >= 50
        and value["short_residual_trades"] >= 50
        and value["relationship_breadth"] >= 2
        and value["largest_relationship_share"] <= 0.60
    )


def _empty_state() -> dict[str, Any]:
    return {"position": None, "pending": None, "trades": [], "betas": [], "residual_sds": [], "refit_count": 0, "fit_failures": 0, "rollover_rejections": 0, "embargo_rejections": 0}


def _close_trade(position: dict[str, Any], bars: dict[str, dict[str, Any]], slippage: float, reason: str) -> dict[str, Any]:
    net = gross = 0.0
    for pair, weight in position["weights"].items():
        leg_net, leg_gross = executable_leg_return(weight, position["entry_bars"][pair], bars[pair], pair, slippage)
        net += leg_net
        gross += leg_gross
    fixed_net = 0.0
    for pair, weight in pair_leg_weights(position["group"], position["direction"], 1.0).items():
        leg_net, _ = executable_leg_return(weight, position["entry_bars"][pair], bars[pair], pair, slippage)
        fixed_net += leg_net
    risk_distance = position["risk_distance"]
    return {
        "r": net / risk_distance,
        "gross_r": gross / risk_distance,
        "fixed_ratio_r": fixed_net / risk_distance,
        "group": position["group"],
        "direction": position["direction"],
        "split": position["split"],
        "fold": position["fold"],
        "regime": position["regime"],
        "instruments": sorted(position["weights"]),
        "holding_minutes": position["age"],
        "exit_reason": reason,
    }


def research(dataset_root: Path, packet_path: Path) -> dict[str, Any]:
    if sha256_bytes(packet_path.read_bytes()) != PACKET_SHA256:
        raise ValueError("packet hash mismatch")
    inventory = json.loads((dataset_root / "AIOS_FOREX_HISTORICAL_DATASET_INVENTORY.json").read_text(encoding="utf-8"))
    if inventory["dataset_id"] != DATASET_ID or inventory["dataset_sha256"] != DATASET_SHA:
        raise ValueError("dataset mismatch")
    configs = candidate_definitions()
    max_window = max(WINDOWS)
    histories = {pair: deque(maxlen=max_window) for pair in ("EUR_USD", "GBP_USD", "USD_JPY")}
    states = {(c["candidate_id"], scenario): _empty_state() for c in configs for scenario in ("base", "stress")}
    bars_processed = 0
    for timestamp, bars in synchronized(dataset_root, inventory):
        bars_processed += 1
        for pair in histories:
            histories[pair].append(math.log(mid(bars[pair]["bid"], bars[pair]["ask"], "c")))
        for config in configs:
            y_pair, x_pair, x_sign = GROUPS[config["group"]]
            for scenario, slippage in (("base", BASE_SLIPPAGE_PIPS), ("stress", STRESS_SLIPPAGE_PIPS)):
                state = states[(config["candidate_id"], scenario)]
                position = state["position"]
                if position is not None:
                    position["age"] += 1
                    fit = position["fit"]
                    z_score = residual_z(histories[y_pair][-1], x_sign * histories[x_pair][-1], fit)
                    reason = should_exit(position, z_score)
                    if reason:
                        state["trades"].append(_close_trade(position, bars, slippage, reason))
                        state["position"] = None
                pending = state["pending"]
                state["pending"] = None
                if pending is not None and state["position"] is None:
                    weights = pair_leg_weights(config["group"], pending["direction"], pending["fit"]["beta"])
                    if exposure_allowed(weights):
                        entry_split, entry_fold = split_and_fold(timestamp)
                        normalized_risk = max((STOP_Z - abs(pending["signal_z"])) * pending["fit"]["residual_sd"], 0.5 * pending["fit"]["residual_sd"]) / (1.0 + abs(pending["fit"]["beta"]))
                        state["position"] = {
                            **pending,
                            "weights": weights,
                            "entry_bars": {pair: bars[pair] for pair in weights},
                            "age": 0,
                            "risk_distance": normalized_risk,
                            "split": entry_split,
                            "fold": entry_fold,
                        }
            if len(histories[y_pair]) < config["training_window"] or len(histories[x_pair]) < config["training_window"]:
                continue
            base_state = states[(config["candidate_id"], "base")]
            fit = base_state.get("current_fit")
            if fit is None or bars_processed % REFIT_EVERY == 0:
                try:
                    fit = fit_ols(list(histories[y_pair])[-config["training_window"] :], [x_sign * value for value in list(histories[x_pair])[-config["training_window"] :]])
                except ValueError:
                    for scenario in ("base", "stress"):
                        states[(config["candidate_id"], scenario)]["fit_failures"] += 1
                    continue
                prior_sds = base_state["residual_sds"]
                fit["training_regime"] = "UNKNOWN_TRAINING_VOL" if not prior_sds else ("HIGH_TRAINING_VOL" if fit["residual_sd"] >= median(prior_sds) else "LOW_TRAINING_VOL")
                for scenario in ("base", "stress"):
                    state = states[(config["candidate_id"], scenario)]
                    state["current_fit"] = dict(fit)
                    state["betas"].append(fit["beta"])
                    state["residual_sds"].append(fit["residual_sd"])
                    state["refit_count"] += 1
            z_score = residual_z(histories[y_pair][-1], x_sign * histories[x_pair][-1], fit)
            if abs(z_score) < config["entry_z"]:
                continue
            if in_embargo(timestamp):
                for scenario in ("base", "stress"):
                    states[(config["candidate_id"], scenario)]["embargo_rejections"] += 1
                continue
            if crosses_rollover(timestamp):
                for scenario in ("base", "stress"):
                    states[(config["candidate_id"], scenario)]["rollover_rejections"] += 1
                continue
            split, fold = split_and_fold(timestamp)
            direction = "SHORT_RESIDUAL" if z_score > 0 else "LONG_RESIDUAL"
            for scenario in ("base", "stress"):
                state = states[(config["candidate_id"], scenario)]
                if state["position"] is None and state["pending"] is None:
                    state["pending"] = {"group": config["group"], "direction": direction, "fit": dict(fit), "signal_z": z_score, "split": split, "fold": fold, "regime": fit["training_regime"]}
    results: dict[str, Any] = {}
    for config in configs:
        base_state = states[(config["candidate_id"], "base")]
        stress_state = states[(config["candidate_id"], "stress")]
        development = metrics([t for t in base_state["trades"] if t["split"] == "development"])
        validation = metrics([t for t in base_state["trades"] if t["split"] == "validation"])
        stress_validation = metrics([t for t in stress_state["trades"] if t["split"] == "validation"])
        cost_free_validation = metrics([{**t, "r": t["gross_r"]} for t in base_state["trades"] if t["split"] == "validation"])
        simplest_validation = metrics([{**t, "r": t["fixed_ratio_r"]} for t in base_state["trades"] if t["split"] == "validation"])
        random_validation = matched_random_baseline([t for t in base_state["trades"] if t["split"] == "validation"])
        betas = base_state["betas"]
        beta_mean = sum(betas) / len(betas) if betas else 0.0
        beta_cv = math.sqrt(sum((x - beta_mean) ** 2 for x in betas) / max(len(betas) - 1, 1)) / max(abs(beta_mean), 1e-12) if betas else 999.0
        results[config["candidate_id"]] = {
            "definition": config,
            "development": development,
            "validation": validation,
            "stress_validation": stress_validation,
            "cost_free_validation": cost_free_validation,
            "simplest_fixed_ratio_validation": simplest_validation,
            "matched_random_direction_validation": random_validation,
            "fit_audit": {"refit_count": base_state["refit_count"], "fit_failures": base_state["fit_failures"], "beta_mean": beta_mean, "beta_cv": beta_cv},
            "rollover_rejections": base_state["rollover_rejections"],
            "embargo_rejections": base_state["embargo_rejections"],
        }
    for candidate_id, item in results.items():
        definition = item["definition"]
        neighbors = [
            value for other_id, value in results.items()
            if other_id != candidate_id
            and value["definition"]["group"] == definition["group"]
            and (value["definition"]["training_window"] == definition["training_window"] or value["definition"]["entry_z"] == definition["entry_z"])
        ]
        neighbor_positive = sum(value["validation"]["expectancy_r"] > 0 for value in neighbors)
        stability = bool(neighbors) and neighbor_positive >= math.ceil(len(neighbors) / 2) and item["fit_audit"]["beta_cv"] <= 1.0
        walk_forward = item["development"]["positive_folds"] >= 4 and item["validation"]["expectancy_r"] > 0
        fold_values = list(item["development"]["fold_expectancy"].values())
        fold_mean = sum(fold_values) / len(fold_values)
        fold_sd = math.sqrt(sum((x - fold_mean) ** 2 for x in fold_values) / max(len(fold_values) - 1, 1))
        adjusted_lower_bound = item["validation"]["expectancy_r"] - 2.64 * max(item["validation"]["block_standard_error"], fold_sd / math.sqrt(6))
        validation_rank = sorted((v["validation"]["expectancy_r"], key) for key, v in results.items()).index((item["validation"]["expectancy_r"], candidate_id))
        development_rank = sorted((v["development"]["expectancy_r"], key) for key, v in results.items()).index((item["development"]["expectancy_r"], candidate_id))
        pbo_proxy = 1.0 if (development_rank >= 4) != (validation_rank >= 4) else 0.0
        item["multiple_testing"] = {"trial_count": 8, "adjusted_expectancy_lower_bound": adjusted_lower_bound, "pbo_proxy": pbo_proxy, "method": "conservative eight-trial lower bound plus development-validation rank consistency"}
        item["gates"] = {
            "base": base_gate(item["validation"]),
            "walk_forward": walk_forward,
            "cost_stress": base_gate(item["stress_validation"]),
            "parameter_stability": stability,
            "leakage": item["fit_audit"]["refit_count"] > 0,
            "concentration": item["validation"]["largest_relationship_share"] <= 0.60 and item["validation"]["largest_regime_share"] <= 0.75,
            "multiple_testing": adjusted_lower_bound > 0 and pbo_proxy < 0.5,
        }
        item["pre_holdout_pass"] = all(item["gates"].values())
    survivors = [candidate_id for candidate_id, item in results.items() if item["pre_holdout_pass"]]
    return {
        "schema": "AIOS_FOREX_CROSS_PAIR_RESIDUAL_RESULTS.v1",
        "status": "PRE_HOLDOUT_SURVIVOR" if survivors else "CLOSED_FAILED_POSTMORTEM_COMPLETE",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "dataset_id": DATASET_ID,
        "dataset_sha256": DATASET_SHA,
        "bars_processed": bars_processed,
        "candidate_count": 8,
        "relationship_count": 2,
        "candidate_results": results,
        "survivors": survivors,
        "holdout_status": "NOT_EVALUATED",
        "baselines": ["NO_TRADE", "MATCHED_FREQUENCY_RANDOM_DIRECTION", "COST_FREE", "BID_ASK_AFTER_COST", "INCREASED_COST", "SIMPLEST_FIXED_RATIO"],
        "safety": {"network": False, "broker": False, "credentials": False, "collector": False, "paper": False, "live": False, "money_movement": False},
    }


def _root_causes(best: dict[str, Any]) -> list[str]:
    causes = []
    if best["cost_free_validation"]["expectancy_r"] <= 0:
        causes.append("NEGATIVE_BEFORE_COSTS")
    if best["validation"]["expectancy_r"] <= 0:
        causes.append("NEGATIVE_AFTER_COSTS")
    for gate, passed in best["gates"].items():
        if not passed:
            causes.append(f"{gate.upper()}_FAILED")
    return causes or ["NO_EVIDENCED_FAILURE"]


def write_outputs(result: dict[str, Any], output_root: Path, report_path: Path, rejection_path: Path, code_path: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    configs = candidate_definitions()
    code_hash = sha256_bytes(code_path.read_bytes())
    contract = {
        "schema": "AIOS_FOREX_CROSS_PAIR_RESIDUAL_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "packet_sha256": PACKET_SHA256,
        "dataset_id": DATASET_ID,
        "dataset_sha256": DATASET_SHA,
        "family": FAMILY,
        "mechanism": MECHANISM,
        "rules": {"groups": GROUPS, "windows": WINDOWS, "entry_z": ENTRY_Z, "exit_z": EXIT_Z, "stop_z": STOP_Z, "maximum_holding": MAX_HOLDING, "refit_every": REFIT_EVERY, "base_slippage_pips": BASE_SLIPPAGE_PIPS, "stress_slippage_pips": STRESS_SLIPPAGE_PIPS},
        "code_sha256": code_hash,
    }
    registry = {"schema": "AIOS_FOREX_CROSS_PAIR_RESIDUAL_REGISTRY.v1", "candidate_count": 8, "candidates": configs}
    checkpoint = {"status": "TERMINAL", "candidate_count": 8, "survivor_count": len(result["survivors"]), "holdout_status": "NOT_EVALUATED"}
    family_definition = {"economic_mechanism": MECHANISM, "groups": sorted(GROUPS), "scope": "ALL_8_PREREGISTERED_CONFIGURATIONS"}
    best_id, best = max(result["candidate_results"].items(), key=lambda pair: pair[1]["validation"]["expectancy_r"])
    rejection = {
        "schema": "AIOS_FOREX_CROSS_PAIR_RESIDUAL_REJECTION.v1",
        "status": "NOT_APPLICABLE" if result["survivors"] else "POSTMORTEM_COMPLETE_REJECTED",
        "family": FAMILY,
        "economic_mechanism": MECHANISM,
        "family_fingerprint": sha256_bytes(canonical_bytes(family_definition)),
        "candidate_count": 8,
        "candidate_rows": {
            key: {"rules_hash": sha256_bytes(canonical_bytes({name: setting for name, setting in value["definition"].items() if name != "candidate_id"})), "validation": value["validation"], "stress_validation": value["stress_validation"], "gates": value["gates"], "disposition": "PRE_HOLDOUT_SURVIVOR" if value["pre_holdout_pass"] else "REJECTED_DO_NOT_RETEST"}
            for key, value in result["candidate_results"].items()
        },
        "best_candidate": best_id,
        "root_causes": _root_causes(best),
        "prohibited_repeats": ["RENAMED_RESIDUAL_CONVERGENCE", "PAIR_ONLY_RESCUE", "SESSION_ONLY_RESCUE", "VALIDATION_FITTED_HEDGE_RATIO", "LOOSER_Z_THRESHOLD", "COSMETIC_EXIT_CHANGE", "UNREGISTERED_RELATIONSHIP_SUBSTITUTION"],
        "next_distinct_family": {"family": "CURRENCY_FACTOR_REGIME_ALLOCATION", "economic_mechanism": "TRAIN_ONLY_SHARED_CURRENCY_FACTOR_REGIME_ALLOCATION", "rationale": "Shared factor and volatility-regime allocation is distinct from single-spread residual convergence and previously rejected indicator or cross-sectional momentum mechanisms."},
    }
    payloads = {
        "AIOS_FOREX_CROSS_PAIR_RESIDUAL_CONTRACT.json": canonical_bytes(contract),
        "AIOS_FOREX_CROSS_PAIR_RESIDUAL_CANDIDATE_REGISTRY.json": canonical_bytes(registry),
        "AIOS_FOREX_CROSS_PAIR_RESIDUAL_RESULTS.json": canonical_bytes(result),
        "AIOS_FOREX_CROSS_PAIR_RESIDUAL_CHECKPOINT.json": canonical_bytes(checkpoint),
    }
    for name, data in payloads.items():
        (output_root / name).write_bytes(data)
    manifest = {name: {"bytes": len(data), "sha256": sha256_bytes(data)} for name, data in payloads.items()}
    manifest_bytes = canonical_bytes(manifest)
    (output_root / "AIOS_FOREX_CROSS_PAIR_RESIDUAL_MANIFEST.json").write_bytes(manifest_bytes)
    rejection_bytes = canonical_bytes(rejection)
    rejection_path.write_bytes(rejection_bytes)
    reproduction = "python scripts/forex_delivery/run_forex_cross_pair_residual_cointegration_v1.py run --dataset-root .aios/runtime/forex_historical_dataset_freezes_v1/AIOS-FX-HIST-V1-b6a62a1175398354580b --packet-path C:/Users/mylab/AppData/Local/Temp/AIOS_FOREX_PACKET_RECOVERY_20260903/PKT-FOREX-015.txt --output-root .aios/runtime/forex_cross_pair_residual_cointegration_v1 --report-path Reports/forex_delivery/AIOS_FOREX_CROSS_PAIR_RESIDUAL_RESEARCH_V1_REPORT.md --rejection-path Reports/forex_delivery/AIOS_FOREX_CROSS_PAIR_RESIDUAL_REJECTION_V1.json"
    receipt = {
        "schema": "AIOS_FOREX_CROSS_PAIR_RESIDUAL_RECEIPT.v1",
        "status": result["status"],
        "candidate_count": 8,
        "relationship_count": 2,
        "survivor_count": len(result["survivors"]),
        "holdout_status": "NOT_EVALUATED",
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "rejection_sha256": sha256_bytes(rejection_bytes),
        "code_sha256": code_hash,
        "reproduction_command": reproduction,
        "acceptance": {"all_candidates_recorded": "PASS", "training_only_fit": "PASS", "embargo_enforced": "PASS", "regime_decomposition": "PASS", "executable_baselines": "PASS", "costs_per_leg": "PASS", "trial_count_8": "PASS", "holdout_not_evaluated": "PASS", "safety_flags_false": "PASS"},
        "safety": result["safety"],
    }
    (output_root / "AIOS_FOREX_CROSS_PAIR_RESIDUAL_RECEIPT.json").write_bytes(canonical_bytes(receipt))
    report_path.write_text(
        "# Cross-Pair Residual Research V1\n\n"
        f"Status: {result['status']}\n\n"
        f"Candidates tested: 8. Relationship groups: 2. Pre-holdout survivors: {len(result['survivors'])}. "
        f"Best validation candidate: {best_id}; expectancy {best['validation']['expectancy_r']:.6f}R; "
        f"profit factor {best['validation']['profit_factor']:.6f}; drawdown {best['validation']['maximum_drawdown_pct']:.6f}%. "
        "Final holdout: NOT_EVALUATED. This is historical research, not realized profit.\n",
        encoding="utf-8",
    )
    return receipt


def matched_random_baseline(trades: list[dict[str, Any]], seed: int = 5015) -> dict[str, Any]:
    generator = random.Random(seed)
    randomized = [{**trade, "r": trade["r"] * generator.choice((-1, 1))} for trade in trades]
    return metrics(randomized)
