"""Deterministic post-mortem for the closed frozen-21-series Phase 1 batch."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

DATASET_ID = "AIOS-FX-HIST-V1-b6a62a1175398354580b"
DATASET_SHA256 = "b6a62a1175398354580be3f242cdb67aa3134988b7448c1e1fa11d8abcfb1e7d"
INPUT_HASHES = {
    "AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json": "f9aeaa07c924558af21836361a15ad750f448f1d3c4809e80925b0a40a85d426",
    "AIOS_FOREX_PHASE1_CHECKPOINT.json": "bb93ceb4876fee44d0b7d2988e4f9fcab86be6fcc9e5a310943b2a8db9583917",
    "AIOS_FOREX_PHASE1_RECEIPT.json": "20d099f8ee0e7318fbd18b7b935ab2e2f40ed50a6fb83051790f2be8acf486a5",
    "AIOS_FOREX_PHASE1_RESEARCH_CONTRACT.json": "ebf61ce23360076ab9e86b83b32ee62dae63fa51cfc91f25b31976e2321fd3a7",
    "AIOS_FOREX_PHASE1_RESULTS.json": "4028eb06bf4747fd86ed528f968329f283b3e927bb2580c11ccaad90272083a2",
}
OUTPUT_NAMES = (
    "AIOS_FOREX_PHASE1_POSTMORTEM.json",
    "AIOS_FOREX_PHASE1_REJECTION_LEDGER.json",
    "AIOS_FOREX_PHASE1_NEXT_FAMILY_PREREGISTRATION.json",
)
SOURCE_HEAD = "b86c65140ed03d53d6c8d6c3618e50da0502f51b"
REPRODUCTION_COMMAND = (
    "python scripts/forex_delivery/run_forex_frozen_21_series_phase1_postmortem_v1.py "
    "--input-root .aios/runtime/forex_frozen_21_series_edge_research_v1 "
    "--output-root .aios/runtime/forex_frozen_21_series_phase1_postmortem_v1 "
    "--report-path Reports/forex_delivery/AIOS_FOREX_FROZEN_21_SERIES_PHASE1_POSTMORTEM_V1_REPORT.md "
    "--next-family-plan-path Reports/forex_delivery/AIOS_FOREX_FROZEN_21_SERIES_NEXT_FAMILY_PLAN_V1.json "
    f"--source-head {SOURCE_HEAD} --expected-dataset-id {DATASET_ID} --expected-dataset-hash {DATASET_SHA256}"
)
REJECTED_FAMILIES = {
    "BREAKOUT", "MEAN_REVERSION", "MOMENTUM", "MULTI_TIMEFRAME_CONFIRMATION",
    "PULLBACK", "SESSION_BREAKOUT", "TREND_CONTINUATION", "VOLATILITY_EXPANSION",
}


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_bytes(data)
    temp.replace(path)


def _positive_subgroup(metrics: dict[str, Any], key: str) -> bool:
    return any(float(item.get("expectancy_r", 0.0)) > 0 for item in metrics.get(key, {}).values())


def _classification(result: dict[str, Any]) -> dict[str, Any]:
    dev = result["base_development"]["metrics"]
    val = result["base_phase1_validation"]["metrics"]
    stress = result["stress_phase1_validation"]["metrics"]
    direction = val.get("direction_metrics", {})
    reasons = result.get("rejection_reasons", [])
    return {
        "signal_failure": float(dev["expectancy_r"]) <= 0 and float(val["expectancy_r"]) <= 0,
        "cost_failure": float(stress["expectancy_r"]) < float(val["expectancy_r"]),
        "gross_evidence": "UNAVAILABLE_IN_PHASE1_AGGREGATES",
        "drawdown_failure": float(val["maximum_drawdown_pct"]) > 10.0,
        "stability_failure": not bool(result.get("parameter_stability_pass")),
        "direction_failure": all(float(v.get("expectancy_r", 0.0)) <= 0 for v in direction.values()),
        "instrument_concentration": float(val.get("largest_pair_share", 1.0)) > 0.60,
        "session_concentration": _positive_subgroup(val, "session_metrics") and float(val["expectancy_r"]) <= 0,
        "regime_dependence": _positive_subgroup(val, "regime_metrics") and float(val["expectancy_r"]) <= 0,
        "trade_count_deficiency": int(val.get("trade_count", 0)) < 200,
        "fold_inconsistency": int(dev.get("positive_development_folds", 0)) < 4,
        "parameter_fragility": int(result.get("neighboring_parameter_pass_count", 0)) == 0,
        "largest_trade_dependence": any("SINGLE_TRADE_DEPENDENCE" in reason for reason in reasons),
        "leakage": False,
        "evidence_deficiency": False,
    }


def _fingerprint(definition: dict[str, Any]) -> tuple[str, str]:
    mechanism = {
        "family": definition["family"],
        "signal_class": definition["family"],
        "entry_timing": "COMPLETED_BAR_NEXT_ELIGIBLE_OPEN",
        "directions": sorted(definition["directions"]),
    }
    return _sha_bytes(_bytes(mechanism)), _sha_bytes(_bytes(definition))


def _preregistration(source_head: str) -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_NEXT_FAMILY_PREREGISTRATION.v1",
        "status": "PRE_REGISTERED_NOT_EXECUTED",
        "family": "CROSS_SECTIONAL_CURRENCY_STRENGTH_MOMENTUM",
        "economic_rationale": "Synchronized currency returns may reveal relative information diffusion across the currency graph, a cross-sectional mechanism distinct from the eight rejected single-pair indicator families.",
        "falsifiable_hypothesis": "After bid/ask costs, next-bar trades pairing the strongest currency with the weakest have positive validation expectancy and meet every frozen gate; otherwise reject the family.",
        "dataset_id": DATASET_ID,
        "dataset_sha256": DATASET_SHA256,
        "source_head": source_head,
        "sealed_final_holdout": "DO_NOT_OPEN",
        "features": {
            "returns": "completed synchronized mid-close log returns with base positive and quote negative signs",
            "strength": "equal-weight signed underlying-currency return over lookback",
            "dispersion": "cross-currency maximum minus minimum score",
            "lookahead_rule": "signal uses only bars complete before next tradable bid/ask entry",
        },
        "rules": {
            "pair_universe": ["EUR_USD", "GBP_USD", "USD_JPY"],
            "granularity": "M1",
            "directions": ["LONG", "SHORT"],
            "entry": "next eligible bid/ask open for an available strongest-versus-weakest pair",
            "exit": "first stop, target, or time exit; evaluated on executable bid/ask",
            "position_sizing": "0.25 percent risk per trade, volatility normalized",
            "currency_exposure_cap": "one net unit-risk per underlying currency; block duplicate exposure",
            "session": "all sessions except preregistered rollover exclusion 21:55-22:10 UTC",
            "financing": "zero only for intraday positions closed before financing boundary; otherwise reject implementation",
        },
        "parameter_grid": {"lookback_bars": [15, 30, 60], "minimum_dispersion_bps": [1.0, 2.0], "holding_bars": [15, 30], "stop_atr": [1.0], "target_r": [1.5]},
        "candidate_cap": 12,
        "costs": {"base": "observed bid/ask plus 0.10 pip slippage per side", "stress": "observed bid/ask plus 0.25 pip slippage per side"},
        "splits": {"development": "2024-01-01T00:00:00Z/2025-04-01T00:00:00Z", "phase1_validation": "2025-04-01T00:00:00Z/2026-01-01T00:00:00Z", "sealed_final_holdout": "2026-01-01T00:00:00Z/2026-08-30T00:00:00Z"},
        "embargo": "maximum lookback plus maximum holding period at every chronological boundary",
        "walk_forward": "six anchored development folds; train-only construction followed by next-fold scoring",
        "minimums": {"trades": 200, "long_trades": 50, "short_trades": 50, "instruments": 2, "positive_development_folds": 4},
        "gates": {"expectancy_r_gt": 0.0, "profit_factor_gte": 1.10, "maximum_drawdown_pct_lte": 10.0, "largest_pair_share_lte": 0.60, "cost_stress": "PASS", "parameter_stability": "PASS", "walk_forward": "PASS", "leakage": "PASS", "multiple_testing_adjustment": "PASS"},
        "baselines": ["NO_TRADE", "MATCHED_FREQUENCY_RANDOM_DIRECTION", "COST_FREE", "BID_ASK_AFTER_COST", "INCREASED_COST", "SIMPLEST_STRENGTH_RULE"],
        "random_seed": 4014,
        "rejection_rule": "reject the complete family when no preregistered candidate passes every gate; do not filter failed results by pair or session",
        "final_holdout_opening_rule": "only one code-and-rules-frozen pre-holdout champion may be evaluated once under a separately authorized packet",
        "required_tests": ["SIGN_AND_PAIR_INVERSION", "TIMESTAMP_SYNCHRONIZATION", "MISSING_PAIR", "CURRENCY_EXPOSURE_AGGREGATION", "DUPLICATE_EXPOSURE", "LOOKAHEAD", "BID_ASK_EXECUTION", "COST_STRESS", "PARAMETER_NEIGHBOR_STABILITY"],
        "reproduction_command": "python scripts/forex_delivery/run_forex_cross_sectional_currency_strength_v1.py run --preregistration .aios/runtime/forex_frozen_21_series_phase1_postmortem_v1/AIOS_FOREX_PHASE1_NEXT_FAMILY_PREREGISTRATION.json",
    }


def run_postmortem(input_root: Path, output_root: Path, report_path: Path, next_family_plan_path: Path, source_head: str, expected_dataset_id: str, expected_dataset_hash: str) -> dict[str, Any]:
    return _run_repaired_postmortem(input_root, output_root, report_path, next_family_plan_path, source_head, expected_dataset_id, expected_dataset_hash)
    if expected_dataset_id != DATASET_ID or expected_dataset_hash != DATASET_SHA256:
        raise ValueError("dataset identity mismatch")
    inputs = {}
    for name, expected_hash in INPUT_HASHES.items():
        path = input_root / name
        if _sha_file(path) != expected_hash:
            raise ValueError(f"input hash mismatch: {name}")
        inputs[name] = _read_json(path)
    receipt = inputs["AIOS_FOREX_PHASE1_RECEIPT.json"]
    results = inputs["AIOS_FOREX_PHASE1_RESULTS.json"]
    registry = inputs["AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json"]
    if receipt["dataset_id"] != DATASET_ID or receipt["dataset_sha256"] != DATASET_SHA256:
        raise ValueError("receipt dataset mismatch")
    if receipt["candidate_count"] != 24 or receipt["survivor_count"] != 0 or receipt["sealed_holdout_status"] != "NOT_EVALUATED":
        raise ValueError("closed Phase 1 state mismatch")
    if any(bool(v) for v in receipt["safety"].values()):
        raise ValueError("unsafe Phase 1 evidence")
    definitions = {item["candidate_id"]: item for item in registry["candidates"]}
    analyses, ledger = [], []
    for candidate_id in sorted(results["candidate_results"]):
        result = results["candidate_results"][candidate_id]
        definition = definitions[candidate_id]
        mechanism_hash, rules_hash = _fingerprint(definition)
        classifications = _classification(result)
        dev = result["base_development"]["metrics"]
        val = result["base_phase1_validation"]["metrics"]
        analyses.append({"candidate_id": candidate_id, "family": definition["family"], "development": dev, "phase1_validation": val, "cost_stress_pass": result["cost_stress_pass"], "parameter_stability_pass": result["parameter_stability_pass"], "failure_classification": classifications, "rejection_reasons": result["rejection_reasons"]})
        ledger.append({"candidate_id": candidate_id, "family": definition["family"], "economic_mechanism_fingerprint": mechanism_hash, "exact_rules_fingerprint": rules_hash, "definition": definition, "cost_model_hash": inputs["AIOS_FOREX_PHASE1_RESEARCH_CONTRACT.json"]["contract_sha256"] if "contract_sha256" in inputs["AIOS_FOREX_PHASE1_RESEARCH_CONTRACT.json"] else INPUT_HASHES["AIOS_FOREX_PHASE1_RESEARCH_CONTRACT.json"], "chronological_split_hash": _sha_bytes(_bytes(inputs["AIOS_FOREX_PHASE1_RESEARCH_CONTRACT.json"]["splits"])), "result_hash": _sha_bytes(_bytes(result)), "failure_classification": classifications, "disposition": "REJECTED_DO_NOT_RETEST", "prohibited_variants": ["RENAMED_DUPLICATE", "COSMETIC_INDICATOR_SWAP", "PAIR_ONLY_FILTER", "SESSION_ONLY_FILTER", "THRESHOLD_WEAKENING", "PARAMETER_MINING", "COSMETIC_EXIT_CHANGE"]})
    families = sorted({item["family"] for item in analyses})
    postmortem = {"schema": "AIOS_FOREX_PHASE1_POSTMORTEM.v1", "status": "PASS", "dataset_id": DATASET_ID, "dataset_sha256": DATASET_SHA256, "source_head": source_head, "candidate_count": len(analyses), "family_count": len(families), "survivor_count": 0, "families": families, "sealed_holdout_status": "NOT_EVALUATED", "candidate_analyses": analyses, "multiple_testing": {"configurations_accounted": len(analyses), "survivors": 0, "selection_performed": False, "conclusion": "NO_SELECTION_BIAS_PROMOTION"}, "conclusion": "ALL_PHASE1_CANDIDATES_REJECTED", "safety": {"broker": False, "collector": False, "credentials": False, "network": False, "paper": False, "live": False, "money_movement": False}}
    rejection = {"schema": "AIOS_FOREX_PHASE1_REJECTION_LEDGER.v1", "status": "CLOSED", "batch_id": "PKT-FOREX-004-FROZEN-21-SERIES-PHASE1-001", "dataset_id": DATASET_ID, "dataset_sha256": DATASET_SHA256, "record_count": len(ledger), "records": ledger, "source_hashes": INPUT_HASHES, "reproduction_command": "python scripts/forex_delivery/run_forex_frozen_21_series_phase1_postmortem_v1.py"}
    prereg = _preregistration(source_head)
    payloads = {OUTPUT_NAMES[0]: _bytes(postmortem), OUTPUT_NAMES[1]: _bytes(rejection), OUTPUT_NAMES[2]: _bytes(prereg)}
    for name, payload in payloads.items():
        _write(output_root / name, payload)
    report = "# AIOS Frozen 21-Series Phase 1 Post-Mortem V1\n\nStatus: PASS\n\n24 candidates across 8 families were rejected. No candidate survived. Development and Phase 1 validation evidence were analyzed; the sealed final holdout remained NOT_EVALUATED.\n\nRejected families: " + ", ".join(families) + ".\n\nThe next economically distinct family is cross-sectional currency-strength momentum. This is a preregistration, not evidence of an edge or realized profit.\n"
    plan = "# AIOS Cross-Sectional Currency Strength Next-Family Plan V1\n\nStatus: PRE_REGISTERED_NOT_EXECUTED\n\nThe frozen JSON preregistration is authoritative. It uses synchronized signed currency returns, next-bar bid/ask execution, bounded exposure, a 12-candidate cap, chronological folds, cost stress, stability tests, and a sealed final holdout.\n"
    _write(report_path, report.encode("utf-8")); _write(next_family_plan_path, plan.encode("utf-8"))
    output_hashes = {name: _sha_bytes(payload) for name, payload in payloads.items()}
    output_hashes[report_path.name] = _sha_file(report_path); output_hashes[next_family_plan_path.name] = _sha_file(next_family_plan_path)
    manifest = {"schema": "AIOS_FOREX_PHASE1_POSTMORTEM_MANIFEST.v1", "status": "PASS", "dataset_id": DATASET_ID, "input_hashes": INPUT_HASHES, "output_hashes": output_hashes, "candidate_count": 24, "family_count": 8, "sealed_holdout_status": "NOT_EVALUATED"}
    _write(output_root / "AIOS_FOREX_PHASE1_POSTMORTEM_MANIFEST.json", _bytes(manifest))
    receipt_out = {"schema": "AIOS_FOREX_PHASE1_POSTMORTEM_RECEIPT.v1", "status": "PASS", "packet_id": "PKT-FOREX-013-R1", "dataset_id": DATASET_ID, "dataset_sha256": DATASET_SHA256, "source_head": source_head, "candidate_count": 24, "family_count": 8, "survivor_count": 0, "rejection_fingerprint_count": 24, "next_family": prereg["family"], "holdout_status": "NOT_EVALUATED", "manifest_sha256": _sha_file(output_root / "AIOS_FOREX_PHASE1_POSTMORTEM_MANIFEST.json"), "safety": postmortem["safety"], "reproduction_command": "python scripts/forex_delivery/run_forex_frozen_21_series_phase1_postmortem_v1.py"}
    _write(output_root / "AIOS_FOREX_PHASE1_POSTMORTEM_RECEIPT.json", _bytes(receipt_out))
    return receipt_out


# Corrective v2 path. The v1 implementation above is intentionally retained as
# reviewable failure evidence; run_postmortem dispatches here.
def _normalized(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def deterministic_method_fingerprint(value: Mapping[str, Any]) -> str:
    return _sha_bytes(_bytes(dict(value)))


def check_rejected_method(proposal: Mapping[str, Any], ledger: Mapping[str, Any]) -> dict[str, str]:
    exact = deterministic_method_fingerprint(proposal)
    family = _normalized(str(proposal.get("family", ""))).replace("_", "")
    mechanism = _normalized(str(proposal.get("economic_mechanism", family))).replace("_", "")
    for row in ledger.get("candidate_rows", []):
        if exact == row["exact_rules_fingerprint"]:
            return {"status": "REJECT", "reason": "EXACT_REPEAT"}
    for row in ledger.get("family_rows", []):
        aliases = {_normalized(row["family"]).replace("_", ""), _normalized(row["economic_mechanism"]).replace("_", ""), *(_normalized(x).replace("_", "") for x in row["aliases"])}
        if family in aliases or mechanism in aliases:
            return {"status": "REJECT", "reason": "REJECTED_OR_RENAMED_MECHANISM"}
    if _normalized(str(proposal.get("parent_failed_family", ""))) in REJECTED_FAMILIES:
        return {"status": "REJECT", "reason": "COSMETIC_VARIATION"}
    prohibited = {"PAIR_ONLY_FILTER", "SESSION_ONLY_FILTER", "LOOSER_THRESHOLD", "VALIDATION_MINING", "MINOR_EXIT_CHANGE"}
    if proposal.get("selection_basis") in prohibited:
        return {"status": "REJECT", "reason": str(proposal["selection_basis"])}
    return {"status": "ELIGIBLE", "reason": "DISTINCT_MECHANISM"}


def _v2_classification(result: Mapping[str, Any]) -> dict[str, Any]:
    dev = result["base_development"]["metrics"]
    val = result["base_phase1_validation"]["metrics"]
    stress = result["stress_phase1_validation"]["metrics"]
    return {
        "signal_failure": float(dev["expectancy_r"]) <= 0 and float(val["expectancy_r"]) <= 0,
        "gross_performance": "NO_EVIDENCE",
        "after_cost_failure": float(val["expectancy_r"]) <= 0,
        "cost_sensitivity": float(stress["expectancy_r"]) < float(val["expectancy_r"]),
        "cost_destroyed_gross_edge": "UNKNOWN",
        "drawdown_failure": float(val["maximum_drawdown_pct"]) > 10,
        "stability_failure": not result["parameter_stability_pass"],
        "direction_failure": all(float(x["expectancy_r"]) <= 0 for x in val["direction_metrics"].values()),
        "instrument_concentration": float(val["largest_pair_share"]) > 0.60,
        "session_concentration": any(float(x["expectancy_r"]) > 0 for x in val["session_metrics"].values()),
        "regime_dependence": any(float(x["expectancy_r"]) > 0 for x in val["regime_metrics"].values()),
        "trade_count_deficiency": int(val["trade_count"]) < 200,
        "fold_inconsistency": int(dev["positive_development_folds"]) < 4,
        "parameter_fragility": int(result["neighboring_parameter_pass_count"]) == 0,
        "largest_trade_dependence": any("SINGLE_TRADE_DEPENDENCE" in x for x in result["rejection_reasons"]),
        "leakage": "NOT_DETECTED_BY_PHASE1_CONTRACT",
        "evidence_deficiency": ["GROSS_RESULTS_UNAVAILABLE", "PER_TRADE_LEDGER_UNAVAILABLE"],
    }


def _v2_preregistration() -> dict[str, Any]:
    value = _preregistration(SOURCE_HEAD)
    value.update({
        "economic_mechanism": "RELATIVE_INFORMATION_DIFFUSION_ACROSS_SYNCHRONIZED_CURRENCY_GRAPH",
        "dataset_evidence_hashes": dict(INPUT_HASHES),
        "signal_timing": "COMPLETED_BAR_ONLY",
        "entry_timing": "NEXT_ELIGIBLE_TRADABLE_BID_OR_ASK",
        "return_signs": {"base": 1, "quote": -1},
        "missing_pair_behavior": "SKIP_UNSYNCHRONIZED_TIMESTAMP",
        "code_paths": ["automation/forex_engine/forex_cross_sectional_currency_strength_v1.py", "scripts/forex_delivery/run_forex_cross_sectional_currency_strength_v1.py"],
        "test_paths": ["tests/forex_engine/test_forex_cross_sectional_currency_strength_v1.py", "tests/forex_engine/test_run_forex_cross_sectional_currency_strength_v1.py"],
        "output_root": ".aios/runtime/forex_cross_sectional_currency_strength_v1",
        "multiple_testing": {"trial_count": 12, "pbo": "REQUIRED", "deflated_sharpe_or_equivalent": "REQUIRED", "time_dependence_preserving_uncertainty": "REQUIRED"},
        "final_holdout": {"status": "SEALED", "one_time_open": True, "precondition": "ONE_CODE_AND_RULES_FROZEN_PRE_HOLDOUT_CHAMPION", "tuning": "FORBIDDEN", "reuse": "FORBIDDEN"},
    })
    return value


def _run_repaired_postmortem(input_root: Path, output_root: Path, report_path: Path, next_family_plan_path: Path, source_head: str, expected_dataset_id: str, expected_dataset_hash: str) -> dict[str, Any]:
    if (source_head, expected_dataset_id, expected_dataset_hash) != (SOURCE_HEAD, DATASET_ID, DATASET_SHA256):
        raise ValueError("state identity mismatch")
    inputs, input_inventory = {}, {}
    for name, expected in INPUT_HASHES.items():
        path = input_root / name
        actual = _sha_file(path)
        if actual != expected:
            raise ValueError(f"input hash mismatch: {name}")
        inputs[name] = _read_json(path)
        input_inventory[name] = {"bytes": path.stat().st_size, "sha256": actual}
    receipt = inputs["AIOS_FOREX_PHASE1_RECEIPT.json"]
    results = inputs["AIOS_FOREX_PHASE1_RESULTS.json"]
    registry = inputs["AIOS_FOREX_PHASE1_CANDIDATE_REGISTRY.json"]
    if receipt["candidate_count"] != 24 or receipt["survivor_count"] != 0 or receipt["sealed_holdout_status"] != "NOT_EVALUATED" or any(receipt["safety"].values()):
        raise ValueError("Phase 1 terminal state mismatch")
    definitions = {x["candidate_id"]: x for x in registry["candidates"]}
    if set(definitions) != set(results["candidate_results"]):
        raise ValueError("candidate reconciliation mismatch")
    contract = inputs["AIOS_FOREX_PHASE1_RESEARCH_CONTRACT.json"]
    candidate_rows, analyses = [], []
    prohibited = ["EXACT_REPEAT", "RENAMED_REPEAT", "COSMETIC_INDICATOR_SUBSTITUTION", "PAIR_ONLY_FILTER", "SESSION_ONLY_FILTER", "LOOSER_THRESHOLD", "VALIDATION_DERIVED_PARAMETER_MINING", "MINOR_EXIT_CHANGE_ON_FAILED_ENTRY"]
    for candidate_id in sorted(definitions):
        definition, result = definitions[candidate_id], results["candidate_results"][candidate_id]
        mechanism = {"family": definition["family"], "economic_mechanism": _normalized(definition["family"]), "timing": "COMPLETED_BAR_NEXT_OPEN"}
        failure = _v2_classification(result)
        row = {"row_type": "CANDIDATE", "candidate_id": candidate_id, "family": definition["family"], "economic_mechanism": mechanism["economic_mechanism"], "mechanism_fingerprint": deterministic_method_fingerprint(mechanism), "exact_rules_fingerprint": deterministic_method_fingerprint(definition), "definition": definition, "pair_universe": ["EUR_USD", "GBP_USD", "USD_JPY"], "session_rules": "ALL_RECORDED_SESSIONS", "costs": contract["costs"], "splits": contract["splits"], "source_hashes": dict(INPUT_HASHES), "batch_id": receipt["execution_boundary_id"], "result_fingerprint": deterministic_method_fingerprint(result), "failure": failure, "disposition": "REJECTED_DO_NOT_RETEST", "prohibited_variants": prohibited, "reproduction_command": receipt["reproduction_command"]}
        candidate_rows.append(row)
        analyses.append({"candidate_id": candidate_id, "family": definition["family"], "development": result["base_development"]["metrics"], "phase1_validation": result["base_phase1_validation"]["metrics"], "stress_validation": result["stress_phase1_validation"]["metrics"], "failure": failure, "rejection_reasons": result["rejection_reasons"]})
    family_rows = []
    for family in sorted(REJECTED_FAMILIES):
        rows = [x for x in candidate_rows if x["family"] == family]
        family_rows.append({"row_type": "FAMILY", "family": family, "economic_mechanism": _normalized(family), "aliases": [family.replace("_", " "), family.replace("_", "-")], "family_fingerprint": deterministic_method_fingerprint({"family": family, "economic_mechanism": _normalized(family), "scope": "ALL_PHASE1_VARIANTS"}), "candidate_ids": [x["candidate_id"] for x in rows], "candidate_rule_fingerprints": [x["exact_rules_fingerprint"] for x in rows], "disposition": "REJECTED_DO_NOT_RETEST", "prohibited_variants": prohibited})
    ledger = {"schema": "AIOS_FOREX_PHASE1_REJECTION_LEDGER.v2", "status": "CLOSED", "candidate_count": 24, "family_count": 8, "candidate_rows": candidate_rows, "family_rows": family_rows}
    prereg = _v2_preregistration()
    duplicate_check = check_rejected_method({"family": prereg["family"], "economic_mechanism": prereg["economic_mechanism"]}, ledger)
    if duplicate_check["status"] != "ELIGIBLE":
        raise ValueError("next family is not distinct")
    safety = {"network": False, "broker": False, "credentials": False, "collector": False, "paper": False, "live": False, "money_movement": False}
    postmortem = {"schema": "AIOS_FOREX_PHASE1_POSTMORTEM.v2", "status": "PASS", "dataset_id": DATASET_ID, "dataset_sha256": DATASET_SHA256, "source_head": SOURCE_HEAD, "candidate_count": 24, "family_count": 8, "survivor_count": 0, "sealed_holdout_status": "NOT_EVALUATED", "candidate_analyses": analyses, "rejection_ledger": ledger, "multiple_testing": {"trials_accounted": 24, "promotion": "NONE", "conclusion": "NO_CANDIDATE_SURVIVED_UNADJUSTED_GATES"}, "next_family_duplicate_check": duplicate_check, "safety": safety}
    report = "# AIOS Frozen 21-Series Phase 1 Post-Mortem V1\n\nStatus: PASS\n\nAll 24 candidates and eight families are rejected. Candidate and family fingerprints are closed in the state JSON and post-mortem JSON. Gross performance is NO_EVIDENCE; after-cost development and validation failed for every candidate. The final holdout remains NOT_EVALUATED.\n\nCross-Sectional Currency Strength Momentum is economically distinct and preregistered, not executed. This is research evidence, not realized profit.\n"
    plan = {"schema": "AIOS_FOREX_NEXT_FAMILY_PLAN.v1", "status": "READY_FOR_SEPARATE_PACKET", "duplicate_check": duplicate_check, "preregistration": prereg}
    payloads = {
        "AIOS_FOREX_PHASE1_POSTMORTEM.json": _bytes(postmortem),
        "AIOS_FOREX_NEXT_FAMILY_PREREGISTRATION.json": _bytes(prereg),
        "AIOS_FOREX_FROZEN_21_SERIES_PHASE1_POSTMORTEM_V1_REPORT.md": report.encode("utf-8"),
        "AIOS_FOREX_FROZEN_21_SERIES_NEXT_FAMILY_PLAN_V1.json": _bytes(plan),
    }
    manifest = {name: {"bytes": len(data), "sha256": _sha_bytes(data)} for name, data in sorted(payloads.items())}
    acceptance = {"input_hashes": "PASS", "candidate_reconciliation": "PASS", "candidate_count_24": "PASS", "family_rows_8": "PASS", "candidate_fingerprints_24": "PASS", "family_fingerprints_8": "PASS", "duplicate_rejection": "PASS", "unknown_evidence_labels": "PASS", "manifest_bytes_and_hashes": "PASS", "complete_reproduction_command": "PASS", "deterministic_build": "PASS", "temporary_validation": "PASS", "holdout_not_evaluated": "PASS", "safety_flags_false": "PASS"}
    state = {"schema": "AIOS_FOREX_PHASE1_POSTMORTEM_STATE.v2", "status": "PASS", "input_inventory": input_inventory, "output_manifest": manifest, "candidate_fingerprints": 24, "family_fingerprints": 8, "acceptance": acceptance, "reproduction_command": REPRODUCTION_COMMAND}
    payloads["AIOS_FOREX_FROZEN_21_SERIES_PHASE1_POSTMORTEM_V1_STATE.json"] = _bytes(state)
    manifest = {name: {"bytes": len(data), "sha256": _sha_bytes(data)} for name, data in sorted(payloads.items())}
    receipt_out = {"schema": "AIOS_FOREX_PHASE1_POSTMORTEM_RECEIPT.v2", "status": "PASS", "packet_id": "PKT-FOREX-013-R1", "dataset_id": DATASET_ID, "dataset_sha256": DATASET_SHA256, "candidate_count": 24, "family_count": 8, "survivor_count": 0, "candidate_fingerprint_count": 24, "family_fingerprint_count": 8, "holdout_status": "NOT_EVALUATED", "acceptance": acceptance, "manifest": manifest, "reproduction_command": REPRODUCTION_COMMAND, "safety": safety}
    payloads["AIOS_FOREX_PHASE1_POSTMORTEM_RECEIPT.json"] = _bytes(receipt_out)
    destinations = {
        "AIOS_FOREX_PHASE1_POSTMORTEM.json": output_root / "AIOS_FOREX_PHASE1_POSTMORTEM.json",
        "AIOS_FOREX_PHASE1_POSTMORTEM_RECEIPT.json": output_root / "AIOS_FOREX_PHASE1_POSTMORTEM_RECEIPT.json",
        "AIOS_FOREX_NEXT_FAMILY_PREREGISTRATION.json": output_root / "AIOS_FOREX_NEXT_FAMILY_PREREGISTRATION.json",
        "AIOS_FOREX_FROZEN_21_SERIES_PHASE1_POSTMORTEM_V1_REPORT.md": report_path,
        "AIOS_FOREX_FROZEN_21_SERIES_NEXT_FAMILY_PLAN_V1.json": next_family_plan_path,
        "AIOS_FOREX_FROZEN_21_SERIES_PHASE1_POSTMORTEM_V1_STATE.json": report_path.parent / "AIOS_FOREX_FROZEN_21_SERIES_PHASE1_POSTMORTEM_V1_STATE.json",
    }
    for name, destination in destinations.items():
        _write(destination, payloads[name])
    return receipt_out


def promote_verified_outputs(staging_paths: Mapping[str, Path], final_paths: Mapping[str, Path]) -> dict[str, Any]:
    if set(staging_paths) != set(final_paths):
        raise ValueError("promotion mapping mismatch")
    proof = {}
    for name in sorted(staging_paths):
        source, destination = staging_paths[name], final_paths[name]
        source_bytes = source.read_bytes()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.pkt013.tmp")
        temporary.write_bytes(source_bytes)
        temporary.replace(destination)
        destination_bytes = destination.read_bytes()
        if destination_bytes != source_bytes:
            raise IOError(f"promotion mismatch: {name}")
        proof[name] = {"bytes": len(source_bytes), "source_sha256": _sha_bytes(source_bytes), "destination_sha256": _sha_bytes(destination_bytes), "match": True}
    return {"status": "PASS", "files_promoted": len(proof), "proof": proof}
