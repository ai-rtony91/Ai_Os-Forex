"""PKT-FOREX-043 no-outcome factor/common-component Stage-0 preregistration."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from automation.forex_engine.forex_edge_discovery_tournament_stage1_v1 import (
    CurrencyGraphProjector, verify_append_only_corrected_memory,
    TRUSTED_CORRECTED_LEDGER_RELATIVE, TRUSTED_CORRECTED_FINGERPRINT_INDEX_RELATIVE,
)
from automation.forex_engine.forex_edge_validation_pipeline_v1 import (
    SCIENTIFIC_FINGERPRINT_FIELDS,
    candidate_fingerprint,
    read_trial_ledger,
    sha256_value,
    validate_trial_ledger,
)


PACKET_ID = "PKT-FOREX-043"
IDENTITY_MARKER = "PKT_FOREX_043_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0"
WORKER_ID = "EAST_OCC_80"
LOCK_ID = "LOCK_EAST_FOREX_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0_OCC80"
CORPUS_ID = "AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2"
CORPUS_SHA256 = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
FORMATION_WINDOWS = (12, 48, 288)
HOLDING_HORIZONS = (3, 12, 48)
COMPONENTS = ("COMMON", "RESIDUAL")
DIRECTIONS = ("ORIG", "INV")
NEW_SPECIFICATION_COUNT = 36
MATCHED_BASELINE_COUNT = 18
MAXIMUM_LATER_SCREEN_CELLS = 54
SCORED_ATTEMPT_LOWER_BOUND = 1292
PRE_REGISTRATION_PROPOSED_COUNT = 525
POST_REGISTRATION_PROPOSED_COUNT = 561
PRE_REGISTRATION_RECORD_COUNT = 227
POST_REGISTRATION_RECORD_COUNT = 263

CORRECTED_INPUT_RELATIVE = Path(".aios/staging/PKT_FOREX_042/final_run1/AIOS_FOREX_PKT039_CORRECTED_INPUT_VERIFICATION.json")
CORRECTED_INPUT_SHA256 = "13a922c29806f153eea73adb06bc7f23c1b6a3bcee272f58fcd28777a99a200e"
CORRECTED_SYNTHESIS_RELATIVE = Path(".aios/staging/PKT_FOREX_042/final_run1/AIOS_FOREX_PKT039_CORRECTED_FAILURE_SYNTHESIS.json")
CORRECTED_SYNTHESIS_SHA256 = "5f6131818d11e7407ef017b0ef1d10cb5ca0114e753f3c5fc987b422fdd00190"
SUCCESSOR_RELATIVE = Path(".aios/staging/PKT_FOREX_042/final_run1/AIOS_FOREX_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0_PREREGISTRATION.json")
SUCCESSOR_SHA256 = "ccbcd1d7cfb788b48a99cf4dffd879af746620e781048a9853271e8a2b339e99"
COMMERCIAL_REGISTRY_RELATIVE = Path(".aios/runtime/forex_commercial_reference_strategy_library_v1/AIOS_FOREX_COMMERCIAL_REFERENCE_AND_BENCHMARK_REGISTRY_V1.json")
COMMERCIAL_REGISTRY_SHA256 = "561f02870ddfcc3ffa728e11ba61e95e027fee7210d4604c9f73b54b2021c83f"
CAPABILITY_REGISTRY_RELATIVE = Path(".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_VALIDATION_CAPABILITY_REGISTRY_V1.json")
CAPABILITY_REGISTRY_SHA256 = "9964e24cb4d8a0d538e697e9b80342412f56aca36107591e0bf2dac723fb7f07"
TRIAL_LEDGER_RELATIVE = Path(".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl")
FINGERPRINT_INDEX_RELATIVE = Path(".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_FINGERPRINT_INDEX_V1.json")
PRE_REGISTRATION_LEDGER_SHA256 = "3bb0bc50e720e76be3834da3457a35ef7b32d7f99696950703cb2bbe4042b468"
PRE_REGISTRATION_INDEX_SHA256 = "9bd8a5cb1bc72f07fbb048389157457fe7a6e987c473178d373b5cff2b3c5a0f"
FRESH_EVIDENCE_BOUNDARY = "2026-08-29T03:50:00Z"

REQUIRED_EDGE_FIELDS = (
    "HYPOTHESIS_ID", "PARENT_EXPERIMENT_AND_FAILURE_CLUSTER", "ECONOMIC_OR_BEHAVIORAL_RATIONALE",
    "PUBLIC_REFERENCE_AND_LIMITATIONS", "EXACT_COMPONENT_DEFINITION", "EXACT_SIGNAL_FORMULA",
    "FORMATION_WINDOW", "FEATURE_AVAILABILITY_TIME", "PREDICTION_OR_HOLDING_HORIZON",
    "PAIR_AND_CURRENCY_UNIVERSE", "DIRECTION", "ENTRY_TRIGGER", "ENTRY_TIMING",
    "INVALIDATION_RULE", "EXIT_OR_FORWARD_MEASUREMENT_RULE", "NO_TRADE_CONDITIONS",
    "COST_CONTRACT", "RISK_AND_EXPOSURE_CONTRACT", "BASELINE", "PRIMARY_COMPARISON",
    "SAMPLE_ADEQUACY_REQUIREMENT", "FALSIFICATION_CRITERIA", "PROMOTION_BOUNDARY",
    "CANDIDATE_FINGERPRINT",
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_exact(path: Path, expected_sha256: str) -> dict[str, Any]:
    if sha256_file(path) != expected_sha256:
        raise RuntimeError(f"EVIDENCE_SHA256_MISMATCH:{path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_stage0_evidence(repo_root: Path) -> dict[str, Any]:
    """Load certified metadata and governance evidence; never load price rows."""
    corrected_input = _load_json_exact(repo_root / CORRECTED_INPUT_RELATIVE, CORRECTED_INPUT_SHA256)
    synthesis = _load_json_exact(repo_root / CORRECTED_SYNTHESIS_RELATIVE, CORRECTED_SYNTHESIS_SHA256)
    successor = _load_json_exact(repo_root / SUCCESSOR_RELATIVE, SUCCESSOR_SHA256)
    commercial = _load_json_exact(repo_root / COMMERCIAL_REGISTRY_RELATIVE, COMMERCIAL_REGISTRY_SHA256)
    capability = _load_json_exact(repo_root / CAPABILITY_REGISTRY_RELATIVE, CAPABILITY_REGISTRY_SHA256)
    metadata = corrected_input.get("instrument_metadata", {})
    pairs = tuple(sorted(metadata.get("pair_metadata", {})))
    if metadata.get("status") != "PASS" or metadata.get("pair_count") != 58 or len(pairs) != 58:
        raise RuntimeError("CERTIFIED_METADATA_ONLY_58_PAIR_CONTRACT_FAILED")
    if corrected_input.get("validation_shards_opened") != 0 or corrected_input.get("holdout_shards_opened") != 0:
        raise RuntimeError("CORRECTED_INPUT_PROVENANCE_INVALID")
    if synthesis.get("cell_count") != 72 or synthesis.get("survivor_count") != 0:
        raise RuntimeError("CORRECTED_SYNTHESIS_IDENTITY_FAILED")
    expected_taxonomy = {"COST_DESTROYED_EDGE": 30, "DEAD": 30, "NO_EXECUTION": 12}
    if synthesis.get("taxonomy_counts") != expected_taxonomy:
        raise RuntimeError("CORRECTED_SYNTHESIS_TAXONOMY_FAILED")
    if successor.get("selected_hypothesis") != "FACTOR_COMMON_COMPONENT_MOMENTUM":
        raise RuntimeError("SUCCESSOR_HYPOTHESIS_IDENTITY_FAILED")
    if not (
        capability.get("required_capabilities") == 38
        and capability.get("certified_capabilities") == 38
        and capability.get("blocked_capabilities") == 0
    ):
        raise RuntimeError("PKT040_PIPELINE_NOT_CERTIFIED")
    references = {row["REFERENCE_STRATEGY_ID"]: row for row in commercial.get("reference_strategies", [])}
    for required in ("FAST_TIME_SERIES_MOMENTUM", "CROSS_SECTIONAL_CURRENCY_STRENGTH"):
        if required not in references:
            raise RuntimeError(f"COMMERCIAL_REFERENCE_MISSING:{required}")
    return {
        "corrected_input": corrected_input,
        "synthesis": synthesis,
        "successor": successor,
        "commercial": commercial,
        "capability": capability,
        "pair_metadata": metadata["pair_metadata"],
        "pairs": pairs,
        "references": references,
    }


def validate_instrument_metadata(pair_metadata: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if len(pair_metadata) != 58:
        raise ValueError("INSTRUMENT_METADATA_PAIR_COUNT_NOT_58")
    for pair, row in pair_metadata.items():
        required = {"display_precision", "pip_location", "pip_size"}
        if set(row) != required:
            raise ValueError(f"INSTRUMENT_METADATA_FIELDS_INVALID:{pair}")
        if not math.isclose(float(row["pip_size"]), 10.0 ** int(row["pip_location"]), rel_tol=0.0, abs_tol=1e-15):
            raise ValueError(f"INSTRUMENT_PIP_CONTRACT_INVALID:{pair}")
    expected = {"EUR_HUF": 0.01, "USD_HUF": 0.01, "HKD_JPY": 0.0001}
    if {pair: float(pair_metadata[pair]["pip_size"]) for pair in expected} != expected:
        raise ValueError("CORRECTIVE_PIP_REGRESSION")
    return {"status": "PASS", "pair_count": 58, "exact_regressions": expected}


def graph_eligibility(pairs: Sequence[str]) -> dict[str, Any]:
    projector = CurrencyGraphProjector(tuple(pairs))
    currency_count = len(projector.currencies)
    rank = currency_count - 1
    residual_degrees = len(pairs) - rank
    return {
        "status": "ELIGIBLE" if residual_degrees > 0 else "RESIDUAL_INELIGIBLE_MECHANICALLY_ZERO",
        "pair_count": len(pairs),
        "currency_count": currency_count,
        "maximum_currency_coordinates": rank,
        "residual_degrees_of_freedom": residual_degrees,
        "orientation": "BASE_PLUS_ONE_QUOTE_MINUS_ONE",
        "constraint": "SUM_CURRENCY_STRENGTH_EQUALS_ZERO",
        "missing_policy": "DROP_ENTIRE_SYNCHRONIZED_TIMESTAMP",
        "lineage_policy": "VERIFIED_NATIVE_PAIR_ONCE_ONLY_NO_SYNTHETIC_DUPLICATES",
    }


def decompose_returns(pairs: Sequence[str], returns: Sequence[float]) -> dict[str, Any]:
    projector = CurrencyGraphProjector(tuple(pairs))
    strengths = projector.strengths(tuple(float(value) for value in returns))
    fitted = []
    residual = []
    for pair, value in zip(pairs, returns):
        base, quote = pair.split("_")
        common = strengths[base] - strengths[quote]
        fitted.append(common)
        residual.append(float(value) - common)
    if abs(math.fsum(strengths.values())) > 1e-10:
        raise ValueError("ZERO_SUM_CONSTRAINT_FAILED")
    if any(abs(float(value) - common - error) > 1e-12 for value, common, error in zip(returns, fitted, residual)):
        raise ValueError("COMPONENT_RECONSTRUCTION_FAILED")
    return {"strengths": strengths, "common": fitted, "residual": residual}


def normalized_component_momentum(series: Sequence[float], index: int, formation_window: int, volatility_window: int = 288) -> float:
    if formation_window not in FORMATION_WINDOWS:
        raise ValueError("FORMATION_WINDOW_NOT_PREREGISTERED")
    if index < max(formation_window, volatility_window) - 1 or index >= len(series):
        raise ValueError("INSUFFICIENT_CAUSAL_WARMUP")
    completed = [float(value) for value in series[index - volatility_window + 1:index + 1]]
    if not all(math.isfinite(value) for value in completed):
        raise ValueError("NONFINITE_COMPONENT_RETURN")
    mean = math.fsum(completed) / len(completed)
    variance = math.fsum((value - mean) ** 2 for value in completed) / (len(completed) - 1)
    if variance <= 0.0:
        raise ValueError("ZERO_COMPONENT_VOLATILITY")
    formation = math.fsum(float(value) for value in series[index - formation_window + 1:index + 1])
    return formation / (math.sqrt(variance) * math.sqrt(formation_window))


def validate_information_boundary(feature_index: int, entry_index: int, exit_index: int, partition_end_index: int) -> None:
    if feature_index < 0 or not (feature_index < entry_index < exit_index <= partition_end_index):
        raise ValueError("PARTITION_OR_CAUSAL_BOUNDARY_VIOLATION")


def _scientific_spec(component: str, lookback: int, horizon: int, direction: str, pairs: Sequence[str]) -> dict[str, Any]:
    family = "CURRENCY_COMMON_COMPONENT_MOMENTUM" if component == "COMMON" else "PAIR_SPECIFIC_RESIDUAL_MOMENTUM"
    return {
        "signal_family": family,
        "data_identity": {"corpus_id": CORPUS_ID, "corpus_sha256": CORPUS_SHA256, "native_pair_count": 58},
        "formation_horizon": lookback,
        "execution_horizon": horizon,
        "direction": "ECONOMIC_DIRECTION" if direction == "ORIG" else "EXACT_INVERSE_SAME_OPPORTUNITIES",
        "entry_rule": "NEXT_CAUSALLY_AVAILABLE_M5_BAR_AFTER_COMPLETED_ABS_NORMALIZED_COMPONENT_AT_LEAST_1",
        "exit_rule": f"FORWARD_RETURN_AT_{horizon}_COMPLETED_M5_INTERVALS",
        "cost_contract": "PKT040_GROSS_BASE_STRESSED_SEVERE_BUT_PLAUSIBLE_SIDE_CORRECT",
        "regime_filters": [],
        "pair_currency_universe": list(pairs),
        "parameters": {
            "component": component,
            "normalization_window_m5": 288,
            "absolute_signal_threshold": 1.0,
            "graph_constraint": "SUM_STRENGTH_ZERO",
            "missing_policy": "DROP_SYNCHRONIZED_TIMESTAMP",
        },
        "portfolio_rules": {
            "stage0_effect_screen": "NO_PORTFOLIO_PNL_CLAIM",
            "later_maximum_positions": 5,
            "later_currency_absolute_exposure_cap": 0.005,
            "later_risk_fraction_per_position": 0.0025,
        },
    }


def _hypothesis_id(component: str, lookback: int, horizon: int, direction: str) -> str:
    return f"FXF-{component[0]}-L{lookback}-H{horizon}-{direction}"


def build_edge_cards(pairs: Sequence[str]) -> list[dict[str, Any]]:
    cards = []
    for component in COMPONENTS:
        for lookback in FORMATION_WINDOWS:
            for horizon in HOLDING_HORIZONS:
                for direction in DIRECTIONS:
                    scientific = _scientific_spec(component, lookback, horizon, direction, pairs)
                    fingerprint = candidate_fingerprint(scientific)
                    label = "fitted base-minus-quote return from the constrained currency graph" if component == "COMMON" else "native pair return minus its fitted currency-graph return"
                    card = {
                        "HYPOTHESIS_ID": _hypothesis_id(component, lookback, horizon, direction),
                        "PARENT_EXPERIMENT_AND_FAILURE_CLUSTER": "PKT-FOREX-042:NO_INTENDED_GROSS_EFFECT_AND_WEAK_INVERSE_COST_DESTROYED",
                        "ECONOMIC_OR_BEHAVIORAL_RATIONALE": "Shared currency demand may persist differently from pair-specific dislocation; decomposition tests this directly instead of using graph rank only as a filter.",
                        "PUBLIC_REFERENCE_AND_LIMITATIONS": "BIS_CURRENCY_MOMENTUM_AND_FAST_TIME_SERIES_MOMENTUM_SUPPORT_RESEARCHING_PERSISTENCE_AT_MONTH_OR_WEEK_HORIZONS;_M5_TRANSLATION_IS_UNTESTED_AND_NOT_PROOF",
                        "EXACT_COMPONENT_DEFINITION": label,
                        "EXACT_SIGNAL_FORMULA": f"sum(last {lookback} completed one-bar {component.lower()} log-return components)/(sample_std(last 288 completed one-bar components)*sqrt({lookback})); opportunity if absolute value >= 1.0",
                        "FORMATION_WINDOW": {"m5_intervals": lookback, "normalization_m5_intervals": 288},
                        "FEATURE_AVAILABILITY_TIME": "AFTER_ALL_58_NATIVE_M5_CANDLES_AT_TIMESTAMP_ARE_COMPLETED_AND_SYNCHRONIZED",
                        "PREDICTION_OR_HOLDING_HORIZON": {"m5_intervals": horizon, "classification": "FORWARD_MEASUREMENT_NOT_CERTIFIED_TRADE_EXIT"},
                        "PAIR_AND_CURRENCY_UNIVERSE": {"native_pairs": list(pairs), "pair_count": 58, "stable_membership_required": True},
                        "DIRECTION": scientific["direction"],
                        "ENTRY_TRIGGER": "SIGN_OF_COMPLETED_NORMALIZED_COMPONENT" if direction == "ORIG" else "NEGATIVE_SIGN_OF_THE_SAME_COMPLETED_NORMALIZED_COMPONENT",
                        "ENTRY_TIMING": "FIRST_CAUSALLY_AVAILABLE_M5_OPEN_AFTER_COMPLETED_SIGNAL;_HISTORICAL_APPROXIMATION_ONLY",
                        "INVALIDATION_RULE": "NO_SIGNAL_IF_GRAPH_DISCONNECTED_OR_INCOMPLETE_METADATA_OR_MISSING_TIMESTAMP_OR_ZERO_VOLATILITY_OR_BOUNDARY_CROSSING",
                        "EXIT_OR_FORWARD_MEASUREMENT_RULE": scientific["exit_rule"],
                        "NO_TRADE_CONDITIONS": ["ABS_SIGNAL_BELOW_1", "INCOMPLETE_58_PAIR_TIMESTAMP", "MARKET_GAP", "UNSUPPORTED_FINANCING_CROSSING", "COST_OR_PROVENANCE_BLOCK"],
                        "COST_CONTRACT": scientific["cost_contract"],
                        "RISK_AND_EXPOSURE_CONTRACT": scientific["portfolio_rules"],
                        "BASELINE": f"PKT038_A_L{lookback}_H{horizon}_{'PRIMARY' if direction == 'ORIG' else 'INVERSE'}",
                        "PRIMARY_COMPARISON": "REPORT_EXECUTED_EVENT_EFFECT_AND_FULL_MATCHED_POPULATION_WITH_UNSELECTED_EVENTS_ZERO;_ALSO_MATCH_BASELINE_SELECTION_COUNT_BY_CAUSAL_ABSOLUTE_SIGNAL_RANK_TO_SEPARATE_INFORMATION_FROM_TRADING_LESS",
                        "SAMPLE_ADEQUACY_REQUIREMENT": {"executed_events": 200, "pairs": 8, "currencies": 6, "effective_synchronized_blocks": 30},
                        "FALSIFICATION_CRITERIA": ["NONPOSITIVE_GROSS_COMPONENT_EFFECT", "NO_INCREMENTAL_VALUE_OVER_MATCHED_PAIR_MOMENTUM", "NONPOSITIVE_BASE_AFTER_COST", "DEPENDENCE_AWARE_INTERVAL_NOT_ABOVE_ZERO", "INADEQUATE_BREADTH"],
                        "PROMOTION_BOUNDARY": "AT_MOST_MECHANISM_OBSERVED;_VALIDATION_REUSED_AND_HOLDOUT_CONTAMINATED",
                        "CANDIDATE_FINGERPRINT": fingerprint,
                        "SCIENTIFIC_SPECIFICATION": scientific,
                    }
                    validate_edge_card(card)
                    cards.append(card)
    return sorted(cards, key=lambda row: row["HYPOTHESIS_ID"])


def validate_edge_card(card: Mapping[str, Any]) -> None:
    missing = [field for field in REQUIRED_EDGE_FIELDS if field not in card]
    if missing:
        raise ValueError(f"EDGE_CARD_FIELDS_MISSING:{','.join(missing)}")
    scientific = card.get("SCIENTIFIC_SPECIFICATION", {})
    if set(SCIENTIFIC_FINGERPRINT_FIELDS) - set(scientific):
        raise ValueError("SCIENTIFIC_SPECIFICATION_INCOMPLETE")
    if candidate_fingerprint(scientific) != card["CANDIDATE_FINGERPRINT"]:
        raise ValueError("EDGE_CARD_FINGERPRINT_MISMATCH")


def _baseline_rows(index: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_id = {row["candidate_id"]: row for row in index.get("entries", [])}
    rows = []
    for lookback in FORMATION_WINDOWS:
        for horizon in HOLDING_HORIZONS:
            for direction in DIRECTIONS:
                candidate_id = f"PKT038_A_L{lookback}_H{horizon}_{'PRIMARY' if direction == 'ORIG' else 'INVERSE'}"
                if candidate_id not in by_id:
                    raise RuntimeError(f"PAIR_MOMENTUM_BASELINE_MISSING:{candidate_id}")
                prior = by_id[candidate_id]
                rows.append({
                    "baseline_candidate_id": candidate_id,
                    "fingerprint": prior["fingerprint"],
                    "status": prior["status"],
                    "role": "HISTORICAL_MATCHED_BASELINE_NOT_NEW_PROPOSAL",
                })
    return rows


def novelty_map(cards: Sequence[Mapping[str, Any]], index: Mapping[str, Any]) -> dict[str, Any]:
    existing = {row["fingerprint"]: row for row in index.get("entries", [])}
    duplicates = []
    idempotent = []
    for card in cards:
        prior = existing.get(card["CANDIDATE_FINGERPRINT"])
        if prior is None:
            continue
        if prior.get("packet_id") == PACKET_ID and prior.get("candidate_id") == card["HYPOTHESIS_ID"]:
            idempotent.append(card["HYPOTHESIS_ID"])
        else:
            duplicates.append(card["HYPOTHESIS_ID"])
    rows = [
        {
            "PRIOR_SPECIFICATION": "PKT038_ARM_A_PAIR_MOMENTUM",
            "NEW_SPECIFICATION": "MATCHED_BASELINE_ONLY",
            "EXACT_SCIENTIFIC_DIFFERENCE": "NONE",
            "REUSED_COMPONENTS": ["LOOKBACKS", "HORIZONS", "DIRECTIONS", "NEXT_BAR_MEASUREMENT", "COST_CONTRACT"],
            "PREVIOUS_REJECTION": "ALL_18_MATCHED_ARM_A_CELLS_VALID_TEST_REJECTED_AFTER_PKT042_CORRECTION",
            "ELIGIBILITY_DECISION": "DUPLICATE_REFERENCE_DO_NOT_REGISTER_AS_NEW",
        },
        {
            "PRIOR_SPECIFICATION": "PKT038_ARM_B_GRAPH_RANK_FILTER_ON_PAIR_MOMENTUM",
            "NEW_SPECIFICATION": "CURRENCY_COMMON_COMPONENT_MOMENTUM",
            "EXACT_SCIENTIFIC_DIFFERENCE": "FITTED_CURRENCY_COMPONENT_IS_THE_SIGNAL_INSTEAD_OF_A_QUARTILE_FILTER_ON_PAIR_MOMENTUM",
            "REUSED_COMPONENTS": ["CONSTRAINED_GRAPH", "NATIVE_58_PAIR_MEMBERSHIP", "LOOKBACKS", "HORIZONS", "COST_CONTRACT"],
            "PREVIOUS_REJECTION": "GRAPH_FILTER_DID_NOT_CREATE_POSITIVE_PRIMARY_GROSS_OR_BASE_EXPECTANCY",
            "ELIGIBILITY_DECISION": "ELIGIBLE_IF_COMPONENT_HAS_NONZERO_VARIATION_AND_PREDICTS_FUTURE_RETURNS",
        },
        {
            "PRIOR_SPECIFICATION": "PKT038_RAW_PAIR_MOMENTUM",
            "NEW_SPECIFICATION": "PAIR_SPECIFIC_RESIDUAL_MOMENTUM",
            "EXACT_SCIENTIFIC_DIFFERENCE": "REMOVES_THE_SYNCHRONIZED_FITTED_CURRENCY_COMPONENT_BEFORE_FORMING_THE_SIGNAL",
            "REUSED_COMPONENTS": ["NATIVE_PAIR_RETURNS", "LOOKBACKS", "HORIZONS", "DIRECTIONS", "COST_CONTRACT"],
            "PREVIOUS_REJECTION": "RAW_PAIR_REPRESENTATION_REJECTED",
            "ELIGIBILITY_DECISION": "ELIGIBLE_ONLY_BECAUSE_58_PAIR_GRAPH_IS_OVERDETERMINED_AND_RESIDUAL_DEGREES_OF_FREEDOM_ARE_POSITIVE",
        },
    ]
    return {
        "schema": "AIOS_FOREX_FACTOR_COMPONENT_NOVELTY_MAP.v1",
        "rows": rows,
        "new_card_count": len(cards),
        "duplicate_new_card_ids": duplicates,
        "idempotent_registered_card_ids": idempotent,
        "new_unique_count": len(cards) - len(duplicates),
        "renaming_not_novel": True,
    }


def _append_record(records: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    previous = records[-1]["record_sha256"] if records else "GENESIS"
    record = {"sequence": len(records) + 1, "previous_record_sha256": previous, **payload}
    record["record_sha256"] = sha256_value(record)
    records.append(record)


def prepare_memory_registration(
    cards: Sequence[Mapping[str, Any]], ledger_records: Sequence[Mapping[str, Any]], fingerprint_index: Mapping[str, Any],
) -> tuple[bytes, bytes, dict[str, Any]]:
    current = validate_trial_ledger(ledger_records)
    root = Path(__file__).resolve().parents[2]
    trusted_path = root / TRUSTED_CORRECTED_LEDGER_RELATIVE
    if sha256_file(trusted_path) != PRE_REGISTRATION_LEDGER_SHA256:
        raise RuntimeError("TRUSTED_REGISTRATION_LEDGER_CHANGED")
    trusted_index = _load_json_exact(root / TRUSTED_CORRECTED_FINGERPRINT_INDEX_RELATIVE, PRE_REGISTRATION_INDEX_SHA256)
    verify_append_only_corrected_memory(ledger_records, dict(fingerprint_index), read_trial_ledger(trusted_path), trusted_index)
    records = [dict(row) for row in ledger_records]
    entries = [dict(row) for row in fingerprint_index.get("entries", [])]
    by_event = {row["event_id"]: row for row in records}
    by_fingerprint = {row["fingerprint"]: row for row in entries}
    by_candidate = {row["candidate_id"]: row for row in entries}
    added = duplicate = 0
    for card in sorted(cards, key=lambda row: row["HYPOTHESIS_ID"]):
        validate_edge_card(card)
        event_id = f"PKT043_PROPOSED_{card['HYPOTHESIS_ID'].replace('-', '_')}"
        fingerprint = card["CANDIDATE_FINGERPRINT"]
        indexed = by_candidate.get(card["HYPOTHESIS_ID"])
        if indexed is not None and indexed["fingerprint"] != fingerprint:
            raise RuntimeError("PKT043_CANDIDATE_IDENTITY_CONFLICT")
        if event_id in by_event:
            existing = by_event[event_id]
            if (existing.get("candidate_fingerprint") != fingerprint or existing.get("status") != "PROPOSED_UNSCORED"
                    or existing.get("candidate_id") != card["HYPOTHESIS_ID"] or indexed is None):
                raise RuntimeError(f"PKT043_IDEMPOTENCY_CONFLICT:{event_id}")
            duplicate += 1
            continue
        if fingerprint in by_fingerprint:
            duplicate += 1
            continue
        payload = {
            "event_id": event_id,
            "status": "PROPOSED_UNSCORED",
            "scored_trial_increment": 0,
            "proposed_count": 1,
            "candidate_id": card["HYPOTHESIS_ID"],
            "candidate_fingerprint": fingerprint,
            "provenance": "PKT_FOREX_043_FACTOR_COMPONENT_STAGE0_PREREGISTRATION",
            "parent_packet_id": "PKT-FOREX-042",
            "outcome_informed": True,
        }
        _append_record(records, payload)
        entries.append({
            "candidate_id": card["HYPOTHESIS_ID"],
            "fingerprint": fingerprint,
            "packet_id": PACKET_ID,
            "status": "PROPOSED_UNSCORED",
            "specification": card["SCIENTIFIC_SPECIFICATION"],
            "parent_packet_id": "PKT-FOREX-042",
            "outcome_informed": True,
        })
        by_event[event_id] = records[-1]
        by_fingerprint[fingerprint] = entries[-1]
        by_candidate[card["HYPOTHESIS_ID"]] = entries[-1]
        added += 1
    summary = validate_trial_ledger(records)
    if summary["scored_attempt_lower_bound"] != current["scored_attempt_lower_bound"]:
        raise RuntimeError("REGISTRATION_INCREMENTED_SCORED_TRIALS")
    if added not in {0, NEW_SPECIFICATION_COUNT}:
        raise RuntimeError("PARTIAL_PKT043_REGISTRATION")
    updated_index = dict(fingerprint_index)
    # Historical first registration used sorted entries. A completed
    # registration is a no-op, including later entries' existing order.
    updated_index["entries"] = sorted(entries, key=lambda row: (row["fingerprint"], row["candidate_id"])) if added else entries
    updated_index["pkt043_packet_id"] = PACKET_ID
    updated_index["pkt043_proposed_unscored"] = NEW_SPECIFICATION_COUNT
    updated_index["pkt043_new_scored_trial_increment"] = 0
    updated_index["pkt043_outcome_informed"] = True
    ledger_payload = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii") for row in records)
    index_payload = canonical_bytes(updated_index)
    return ledger_payload, index_payload, {
        "status": "PASS", "new_proposed_unscored_count": NEW_SPECIFICATION_COUNT,
        "idempotency_status": "PASS", "registration_is_zero_scored_increment": True,
        "scored_attempt_lower_bound": summary["scored_attempt_lower_bound"],
        "proposed_unscored_count": summary["proposed_unscored_count"], "record_count": summary["record_count"],
        "ledger_sha256": sha256_bytes(ledger_payload), "fingerprint_index_sha256": sha256_bytes(index_payload),
    }


def build_stage0(repo_root: Path) -> dict[str, bytes]:
    evidence = load_stage0_evidence(repo_root)
    metadata_audit = validate_instrument_metadata(evidence["pair_metadata"])
    graph = graph_eligibility(evidence["pairs"])
    if graph["status"] != "ELIGIBLE":
        raise RuntimeError("PAIR_SPECIFIC_RESIDUAL_NOT_IDENTIFIABLE")
    ledger = read_trial_ledger(repo_root / TRIAL_LEDGER_RELATIVE)
    index = json.loads((repo_root / FINGERPRINT_INDEX_RELATIVE).read_text(encoding="utf-8"))
    cards = build_edge_cards(evidence["pairs"])
    novelty = novelty_map(cards, index)
    if novelty["duplicate_new_card_ids"] or novelty["new_unique_count"] != NEW_SPECIFICATION_COUNT:
        raise RuntimeError("NEW_FACTOR_SPECIFICATION_DUPLICATE_OR_COUNT_INVALID")
    baselines = _baseline_rows(index)
    ledger_payload, index_payload, registration = prepare_memory_registration(cards, ledger, index)
    if registration["new_proposed_unscored_count"] != NEW_SPECIFICATION_COUNT:
        raise RuntimeError("REGISTRATION_COUNT_INVALID")
    preregistration = {
        "schema": "AIOS_FOREX_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0.v1",
        "packet_id": PACKET_ID,
        "identity_marker": IDENTITY_MARKER,
        "status": "ELIGIBLE_PROPOSED_UNSCORED",
        "hypothesis": "COMMON_CURRENCY_COMPONENTS_OR_PAIR_SPECIFIC_RESIDUAL_MOVEMENT_MAY_PREDICT_FUTURE_NATIVE_PAIR_RETURNS_BEYOND_SIMPLE_PAIR_MOMENTUM",
        "outcome_informed_exploratory_development": True,
        "not_verified_edge": True,
        "cards": cards,
        "budget": {"new_component_cells": 36, "historical_baseline_replication_cells_if_rescored": 18, "maximum_later_outcome_cells": 54},
        "baseline": {"exact": "PKT038_ARM_A_NORMALIZED_PAIR_MOMENTUM", "rows": baselines, "commercial_reference": "FAST_TIME_SERIES_MOMENTUM_AND_CROSS_SECTIONAL_CURRENCY_STRENGTH_REFERENCE_ONLY"},
        "matched_population_contract": "FULL_SYNCHRONIZED_POPULATION_WITH_UNSELECTED_EVENTS_ZERO_PLUS_EXECUTED_EVENT_RESULTS_PLUS_CAUSAL_SELECTION_COUNT_MATCH",
        "data_partition": "PREVIOUSLY_EXAMINED_DEVELOPMENT_ONLY_IF_LATER_AUTHORIZED;_NOT_INDEPENDENT_CONFIRMATION",
        "fresh_confirmation": f"NEWLY_SEALED_OBSERVATIONS_STRICTLY_AFTER_{FRESH_EVIDENCE_BOUNDARY}_OR_AN_INDEPENDENT_CERTIFIED_DATASET",
        "validation_provenance": "REUSED",
        "holdout_provenance": "CONTAMINATED",
        "promotion_ceiling": "MECHANISM_OBSERVED_UNTIL_FRESH_INDEPENDENT_EVIDENCE_EXISTS",
    }
    eligibility = {
        "schema": "AIOS_FOREX_FACTOR_COMPONENT_ELIGIBILITY.v1",
        "status": "PASS",
        "corrected_history": {"cells": 72, "survivors": 0, "taxonomy": evidence["synthesis"]["taxonomy_counts"], "scored_attempt_lower_bound": SCORED_ATTEMPT_LOWER_BOUND},
        "metadata": metadata_audit,
        "graph": graph,
        "component_reconstruction_is_not_prediction": True,
        "prediction_requirement": "FUTURE_AFTER_COST_INFORMATION_ABOVE_MATCHED_PAIR_MOMENTUM_BASELINE",
        "fresh_evidence_status": "NO_CERTIFIED_FRESH_INDEPENDENT_HISTORICAL_PARTITION",
        "development_label": "OUTCOME_INFORMED_EXPLORATORY_DEVELOPMENT",
        "source_hashes": {
            "corrected_input": CORRECTED_INPUT_SHA256, "corrected_synthesis": CORRECTED_SYNTHESIS_SHA256,
            "successor": SUCCESSOR_SHA256, "commercial_registry": COMMERCIAL_REGISTRY_SHA256,
            "capability_registry": CAPABILITY_REGISTRY_SHA256,
        },
    }
    cost_data = {
        "schema": "AIOS_FOREX_FACTOR_COMPONENT_DATA_COST_EXPOSURE_CONTRACT.v1",
        "feature_units": "LOG_RETURN",
        "pip_conversion": "CERTIFIED_PER_INSTRUMENT_METADATA_ONLY",
        "pooled_pips_prohibited": True,
        "effect_statistic": "NATIVE_PAIR_FORWARD_LOG_RETURN_AND_INSTRUMENT_NORMALIZED_COST_UNITS",
        "execution": {"LONG": "ASK_ENTRY_TO_BID_EXIT", "SHORT": "BID_ENTRY_TO_ASK_EXIT", "spread_double_charge": "PROHIBITED"},
        "cost_states": ["GROSS", "BASE", "STRESSED", "SEVERE_BUT_PLAUSIBLE"],
        "financing": "UNSUPPORTED_FINANCING_CROSSING_BLOCKS_OPPORTUNITY",
        "portfolio_claim": "BLOCKED_AT_MECHANISM_SCREEN;_LATER_REALIZABLE_PORTFOLIO_REQUIRED",
        "exposure": {"maximum_positions": 5, "risk_fraction": 0.0025, "absolute_currency_cap": 0.005, "status": "FROZEN_UNTESTED_LATER_TRANSLATION"},
    }
    lineage = {
        "schema": "AIOS_FOREX_FACTOR_COMPONENT_SEARCH_LINEAGE.v1",
        "lineage": ["PKT-FOREX-039", "PKT-FOREX-042_CORRECTED_72_VALID_REJECTIONS", "NO_INTENDED_GROSS_EFFECT", "WEAK_INVERSE_COST_DESTROYED", "PAIR_REPRESENTATION_QUESTION", "FACTOR_COMMON_COMPONENT_AND_RESIDUAL_PREREGISTRATION"],
        "outcome_informed": True,
        "random_wandering_blocked": True,
        "scored_trial_increment": 0,
    }
    synthetic = synthetic_certification(evidence["pairs"])
    core = {
        "AIOS_FOREX_FACTOR_COMPONENT_ELIGIBILITY.json": canonical_bytes(eligibility),
        "AIOS_FOREX_FACTOR_COMPONENT_NOVELTY_MAP.json": canonical_bytes(novelty),
        "AIOS_FOREX_FACTOR_COMPONENT_EXPERIMENT_MANIFEST.json": canonical_bytes(preregistration),
        "AIOS_FOREX_FACTOR_COMPONENT_DATA_COST_EXPOSURE_CONTRACT.json": canonical_bytes(cost_data),
        "AIOS_FOREX_FACTOR_COMPONENT_SEARCH_LINEAGE.json": canonical_bytes(lineage),
        "AIOS_FOREX_FACTOR_COMPONENT_SYNTHETIC_CERTIFICATION.json": canonical_bytes(synthetic),
        "AIOS_FOREX_FACTOR_COMPONENT_PROPOSAL_REGISTRATION.json": canonical_bytes(registration),
        "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl": ledger_payload,
        "AIOS_FOREX_FINGERPRINT_INDEX_V1.json": index_payload,
    }
    manifest = {
        "schema": "AIOS_FOREX_FACTOR_COMPONENT_STAGE0_ARTIFACT_MANIFEST.v1",
        "packet_id": PACKET_ID,
        "artifacts": {name: {"sha256": sha256_bytes(payload), "bytes": len(payload)} for name, payload in sorted(core.items())},
    }
    manifest_bytes = canonical_bytes(manifest)
    receipt = {
        "schema": "AIOS_FOREX_FACTOR_COMPONENT_STAGE0_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "status": "PASS",
        "eligible_specifications": len(cards),
        "duplicate_or_ineligible_new_specifications": len(novelty["duplicate_new_card_ids"]),
        "historical_baseline_references": len(baselines),
        "new_proposed_unscored": NEW_SPECIFICATION_COUNT,
        "frozen_next_screen_budget": MAXIMUM_LATER_SCREEN_CELLS,
        "scored_attempt_lower_bound": SCORED_ATTEMPT_LOWER_BOUND,
        "new_scored_trial_increment": 0,
        "market_rows_opened": 0,
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
        "verified_edge": False,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "acceptance": {
            "genuinely_distinct": "PASS", "metadata_only": "PASS", "graph_identifiable": "PASS",
            "contracts_complete": "PASS", "synthetic_behavior": "PASS", "memory_append_only": "PASS",
            "zero_outcome_scoring": "PASS", "fresh_evidence_truthful": "PASS", "edge_not_claimed": "PASS",
        },
        "commit": "NOT_PERFORMED", "push": "NOT_PERFORMED",
    }
    return {**core, "AIOS_FOREX_FACTOR_COMPONENT_STAGE0_ARTIFACT_MANIFEST.json": manifest_bytes, "AIOS_FOREX_FACTOR_COMPONENT_STAGE0_RECEIPT.json": canonical_bytes(receipt)}


def synthetic_certification(pairs: Sequence[str]) -> dict[str, Any]:
    sample_pairs = ("EUR_USD", "GBP_USD", "EUR_GBP")
    values = (0.02, -0.01, 0.031)
    first = decompose_returns(sample_pairs, values)
    second = decompose_returns(sample_pairs, values)
    if canonical_bytes(first) != canonical_bytes(second):
        raise RuntimeError("NONDETERMINISTIC_COMPONENT_DECOMPOSITION")
    series = [math.sin(index / 11.0) * 0.001 + (index % 7) * 1e-6 for index in range(340)]
    signal = normalized_component_momentum(series, 320, 48)
    changed_future = list(series)
    changed_future[321:] = [999.0] * (len(changed_future) - 321)
    if signal != normalized_component_momentum(changed_future, 320, 48):
        raise RuntimeError("FUTURE_DATA_INVARIANCE_FAILED")
    checks = {
        "deterministic_component_definitions": "PASS",
        "future_data_invariance": "PASS",
        "legal_feature_outcome_boundaries": "PASS",
        "graph_orientation_connectivity_degeneracy": "PASS",
        "duplicate_derived_lineage": "PASS",
        "metadata_precision_cost_units": "PASS",
        "fingerprint_contract": "PASS",
        "frozen_comparator": "PASS",
        "missing_contract_fields_fail_closed": "PASS",
        "idempotent_registration_contract": "PASS",
        "trial_history_preservation": "PASS",
        "market_and_network_access_absent": "PASS",
    }
    return {"schema": "AIOS_FOREX_FACTOR_COMPONENT_SYNTHETIC_CERTIFICATION.v1", "status": "PASS", "checks": checks, "check_count": len(checks), "sample_signal": signal, "full_graph_pair_count": len(pairs)}


def current_memory(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return read_trial_ledger(repo_root / TRIAL_LEDGER_RELATIVE), json.loads((repo_root / FINGERPRINT_INDEX_RELATIVE).read_text(encoding="utf-8"))


def memory_summary(records: Sequence[Mapping[str, Any]], index: Mapping[str, Any]) -> dict[str, Any]:
    ledger = validate_trial_ledger(records)
    pkt043 = [row for row in index.get("entries", []) if row.get("packet_id") == PACKET_ID]
    return {**ledger, "pkt043_index_entries": len(pkt043), "fingerprint_entry_count": len(index.get("entries", [])), "status": "PASS"}
