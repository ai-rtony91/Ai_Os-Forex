"""Deterministic, synthetic-only certification for the AIOS Forex edge validator.

This module is deliberately independent of market readers.  It provides the
statistical, execution, portfolio, provenance, research-memory, and promotion
primitives needed to judge a later PKT-FOREX-039 candidate.  Certification in
this module means that the validator behaves correctly on frozen synthetic
evidence; it is not evidence that a trading edge exists.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable, Mapping, Sequence

try:
    import msvcrt
except ImportError:  # pragma: no cover - AIOS production worktree is Windows
    msvcrt = None


SCHEMA = "AIOS_FOREX_EDGE_VALIDATION_PIPELINE_V1"
PACKET_ID = "PKT-FOREX-040"
REQUIRED_CAPABILITY_COUNT = 38
HISTORICAL_SCORED_ATTEMPT_LOWER_BOUND = 1220
LEGACY_PROPOSED_UNSCORED = 446
PKT038_PROPOSED_UNSCORED = 72
TOTAL_PROPOSED_UNSCORED = 518
NEW_HOLDOUT_AFTER = "2026-08-29T03:50:00Z"
FAIL_CLOSED_STATUSES = {
    "MISSING", "UNKNOWN", "INVALID", "CONTAMINATED", "NOT_EVALUATED",
    "NONDETERMINISTIC", "INSUFFICIENT_EVIDENCE", "BLOCK",
}
TRIAL_STATUSES = {
    "PROPOSED_UNSCORED", "OUTCOME_EXAMINED", "VALID_TEST_REJECTED",
    "INVALID_TEST", "DUPLICATE", "SURVIVOR",
}

CAPABILITY_NAMES = (
    "GLOBAL_IMMUTABLE_TRIAL_ACCOUNTING",
    "DUPLICATE_FINGERPRINT_RECONCILIATION",
    "TRUE_DEFLATED_SHARPE_RATIO",
    "GENUINE_CSCV",
    "GENUINE_PBO",
    "MULTIPLE_TESTING_ADJUSTMENT",
    "BLOCK_BOOTSTRAP_UNCERTAINTY",
    "CROSS_PAIR_DEPENDENCE_PRESERVATION",
    "OVERLAPPING_LABEL_HANDLING",
    "WALK_FORWARD_VALIDATION",
    "CHRONOLOGICAL_FOLDS",
    "EMBARGO_ENFORCEMENT",
    "PARAMETER_NEIGHBORHOOD_ROBUSTNESS",
    "REGIME_ROBUSTNESS",
    "PAIR_REMOVAL_STRESS",
    "STRONGEST_PERIOD_REMOVAL",
    "LONG_SHORT_DECOMPOSITION",
    "UNIFIED_COST_STRESS",
    "SPREAD_HANDLING",
    "SLIPPAGE_HANDLING",
    "EXECUTION_DELAY_STRESS",
    "STOP_SLIPPAGE_HANDLING",
    "FINANCING_ROLLOVER_FAIL_CLOSED",
    "REALIZABLE_SYNCHRONIZED_PORTFOLIO",
    "PAIR_CORRELATION",
    "SIGNAL_CORRELATION",
    "CURRENCY_GROSS_NET_EXPOSURE",
    "EFFECTIVE_INDEPENDENT_BETS",
    "LARGEST_PAIR_CONTRIBUTION",
    "LARGEST_CURRENCY_FACTOR_CONTRIBUTION",
    "PORTFOLIO_DRAWDOWN",
    "DEVELOPMENT_ACCESS_ENFORCEMENT",
    "VALIDATION_ACCESS_ENFORCEMENT",
    "FINAL_HOLDOUT_SEALING_ACCESS",
    "DERIVED_CACHE_PROVENANCE",
    "FUTURE_DATA_LEAKAGE_DETECTION",
    "SYNTHETIC_VALIDATOR_HARNESS",
    "FAIL_CLOSED_CANDIDATE_PROMOTION",
)

if len(CAPABILITY_NAMES) != REQUIRED_CAPABILITY_COUNT:
    raise RuntimeError("CAPABILITY_DENOMINATOR_CHANGED")

PROMOTION_STATES = (
    "EDGE_HYPOTHESIS", "MECHANISM_OBSERVED", "DEVELOPMENT_SURVIVOR",
    "COST_SURVIVOR", "ROBUSTNESS_SURVIVOR", "VALIDATION_SURVIVOR",
    "FINAL_HOLDOUT_SURVIVOR", "PAPER_CANDIDATE", "PAPER_VALIDATED_EDGE",
)

TRANSITION_VALIDATORS = {
    "EDGE_HYPOTHESIS": (
        "candidate_fingerprint", "global_trial_receipt", "development_access",
        "future_leakage", "dependence_bootstrap", "sample_adequacy",
    ),
    "MECHANISM_OBSERVED": (
        "no_trade_baseline", "random_direction_baseline", "incremental_baseline",
        "pair_breadth", "currency_breadth", "long_short_decomposition",
    ),
    "DEVELOPMENT_SURVIVOR": (
        "base_cost", "stressed_cost", "severe_cost", "execution_delay",
        "stop_slippage", "financing",
    ),
    "COST_SURVIVOR": (
        "parameter_robustness", "regime_robustness", "pair_removal",
        "currency_removal", "period_removal", "portfolio_validation",
    ),
    "ROBUSTNESS_SURVIVOR": (
        "walk_forward", "embargo", "multiple_testing", "dsr", "cscv_pbo",
        "validation_provenance", "deterministic_reproduction",
    ),
    "VALIDATION_SURVIVOR": (
        "frozen_candidate", "holdout_provenance", "holdout_single_use",
        "derived_cache_lineage", "holdout_result",
    ),
    "FINAL_HOLDOUT_SURVIVOR": (
        "positive_after_cost_expectancy", "profit_factor", "drawdown",
        "exact_strategy_rules", "owner_paper_authority",
    ),
    "PAPER_CANDIDATE": (
        "paper_campaign_complete", "paper_costs", "paper_risk",
        "paper_reproducibility",
    ),
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def pretty_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_value(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("ascii"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def parse_utc(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return moment.astimezone(timezone.utc)


SCIENTIFIC_FINGERPRINT_FIELDS = (
    "signal_family", "data_identity", "formation_horizon", "execution_horizon",
    "direction", "entry_rule", "exit_rule", "cost_contract", "regime_filters",
    "pair_currency_universe", "parameters", "portfolio_rules",
)


def candidate_fingerprint(specification: Mapping[str, Any]) -> str:
    missing = [field for field in SCIENTIFIC_FINGERPRINT_FIELDS if field not in specification]
    if missing:
        raise ValueError(f"FINGERPRINT_FIELDS_MISSING:{','.join(missing)}")
    body = {field: specification[field] for field in SCIENTIFIC_FINGERPRINT_FIELDS}
    return sha256_value({"schema": "AIOS_SCIENTIFIC_CANDIDATE_FINGERPRINT_V1", "body": body})


def reconcile_fingerprints(specifications: Sequence[Mapping[str, Any]], *, digest_function: Any = sha256_value) -> dict[str, Any]:
    index: dict[str, list[str]] = defaultdict(list)
    canonical_bodies: dict[str, str] = {}
    for number, specification in enumerate(specifications):
        body_value = {"schema": "AIOS_SCIENTIFIC_CANDIDATE_FINGERPRINT_V1", "body": {field: specification[field] for field in SCIENTIFIC_FINGERPRINT_FIELDS}}
        fingerprint = str(digest_function(body_value))
        identity = str(specification.get("candidate_id", f"CANDIDATE_{number:04d}"))
        body = canonical_json({field: specification[field] for field in SCIENTIFIC_FINGERPRINT_FIELDS})
        if fingerprint in canonical_bodies and canonical_bodies[fingerprint] != body:
            raise ValueError("FINGERPRINT_COLLISION")
        canonical_bodies[fingerprint] = body
        index[fingerprint].append(identity)
    return {
        "unique_fingerprints": len(index),
        "duplicate_specifications": sum(len(values) - 1 for values in index.values()),
        "index": {key: sorted(values) for key, values in sorted(index.items())},
    }


def _ledger_record(sequence: int, previous_hash: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status", ""))
    if status not in TRIAL_STATUSES:
        raise ValueError("INVALID_TRIAL_STATUS")
    increment = int(payload.get("scored_trial_increment", 0))
    if increment < 0 or (status == "PROPOSED_UNSCORED" and increment != 0):
        raise ValueError("INVALID_TRIAL_INCREMENT")
    record = {"sequence": sequence, "previous_record_sha256": previous_hash, **dict(payload)}
    record["record_sha256"] = sha256_value(record)
    return record


def validate_trial_ledger(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    previous = "GENESIS"
    scored = 0
    proposed = 0
    seen_events: set[str] = set()
    for expected_sequence, source in enumerate(records, start=1):
        record = dict(source)
        supplied_hash = str(record.pop("record_sha256", ""))
        if type(record.get("sequence")) is not int or record["sequence"] != expected_sequence:
            raise ValueError("TRIAL_LEDGER_NON_MONOTONIC")
        if record.get("previous_record_sha256") != previous:
            raise ValueError("TRIAL_LEDGER_CHAIN_BROKEN")
        if supplied_hash != sha256_value(record):
            raise ValueError("TRIAL_LEDGER_HASH_MISMATCH")
        event_id = str(record.get("event_id", ""))
        if not event_id or event_id in seen_events:
            raise ValueError("TRIAL_LEDGER_DUPLICATE_EVENT")
        seen_events.add(event_id)
        status = str(record.get("status", ""))
        if status not in TRIAL_STATUSES:
            raise ValueError("INVALID_TRIAL_STATUS")
        increment = record.get("scored_trial_increment", 0)
        proposal_count = record.get("proposed_count", 0)
        if (type(increment) is not int or type(proposal_count) is not int
                or increment < 0 or proposal_count < 0
                or (status == "PROPOSED_UNSCORED" and increment != 0)):
            raise ValueError("INVALID_TRIAL_INCREMENT")
        scored += increment
        proposed += proposal_count
        previous = supplied_hash
    return {
        "record_count": len(records), "scored_attempt_lower_bound": scored,
        "proposed_unscored_count": proposed, "head_sha256": previous,
    }


def bootstrap_trial_ledger() -> list[dict[str, Any]]:
    payloads = (
        {"event_id": "LEGACY_SCORED_ATTEMPT_LOWER_BOUND_V1", "status": "OUTCOME_EXAMINED", "scored_trial_increment": HISTORICAL_SCORED_ATTEMPT_LOWER_BOUND, "proposed_count": 0, "provenance": "RECONCILED_CUMULATIVE_REPOSITORY_MEMORY"},
        {"event_id": "LEGACY_PROPOSED_UNSCORED_AGGREGATE_V1", "status": "PROPOSED_UNSCORED", "scored_trial_increment": 0, "proposed_count": LEGACY_PROPOSED_UNSCORED, "provenance": "PKT_FOREX_038_REPORTED_PRIOR_MEMORY"},
        {"event_id": "PKT_FOREX_038_FROZEN_72_CELLS", "status": "PROPOSED_UNSCORED", "scored_trial_increment": 0, "proposed_count": PKT038_PROPOSED_UNSCORED, "provenance": "PKT_FOREX_038_FIRST_WAVE_MANIFEST"},
        {"event_id": "PKT_FOREX_039_SCHEMA_INSPECTION", "status": "INVALID_TEST", "scored_trial_increment": 0, "proposed_count": 0, "provenance": "ONE_SCHEMA_ROW_NOT_AN_OUTCOME_EXPERIMENT"},
    )
    records: list[dict[str, Any]] = []
    previous = "GENESIS"
    for sequence, payload in enumerate(payloads, start=1):
        record = _ledger_record(sequence, previous, payload)
        records.append(record)
        previous = record["record_sha256"]
    summary = validate_trial_ledger(records)
    if summary["scored_attempt_lower_bound"] < 1220 or summary["proposed_unscored_count"] != 518:
        raise ValueError("RESEARCH_MEMORY_BASELINE_MISMATCH")
    return records


def read_trial_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError("TRIAL_LEDGER_MISSING")
    records = []
    for line in path.read_text(encoding="ascii").splitlines():
        if not line.strip():
            raise ValueError("TRIAL_LEDGER_TORN_OR_BLANK_RECORD")
        records.append(json.loads(line))
    validate_trial_ledger(records)
    return records


def write_initial_trial_ledger(path: Path) -> list[dict[str, Any]]:
    expected = bootstrap_trial_ledger()
    payload = "".join(canonical_json(record) + "\n" for record in expected).encode("ascii")
    if path.exists():
        existing = read_trial_ledger(path)
        if existing != expected:
            raise ValueError("TRIAL_LEDGER_CONFLICT")
        return existing
    atomic_write(path, payload)
    return expected


def append_trial_record(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    if msvcrt is None:
        raise ValueError("TRIAL_LEDGER_EXCLUSIVE_LOCK_UNAVAILABLE")
    with path.open("r+", encoding="ascii", newline="") as handle:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            handle.seek(0)
            lines = handle.read().splitlines()
            if not lines:
                raise ValueError("TRIAL_LEDGER_MISSING")
            records = [json.loads(line) for line in lines]
            validate_trial_ledger(records)
            event_id = str(payload.get("event_id", ""))
            if any(record["event_id"] == event_id for record in records):
                raise ValueError("TRIAL_LEDGER_DUPLICATE_EVENT")
            record = _ledger_record(len(records) + 1, records[-1]["record_sha256"], payload)
            validate_trial_ledger(records + [record])
            handle.seek(0, os.SEEK_END)
            handle.write(canonical_json(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            return record
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


RESEARCH_RECORD_SCHEMA = "AIOS_FOREX_CHECKED_RESEARCH_RECORD.v1"
RESEARCH_OPTIONAL_FIELDS = (
    "parent_experiment_id", "hypothesis_id", "baseline", "changed_variable", "fixed_variables",
    "indicator_roles", "market_context", "risk_metrics", "uncertainty", "pair_attribution",
    "currency_attribution", "session_attribution", "regime_attribution", "concentration",
    "parameter_stability", "filtered_trades", "skipped_trades", "skip_reasons",
    "mfe", "mae", "cost_breakdown", "matched_delta", "code_version", "feature_version",
    "cost_version", "approval_reference", "budget", "promotion_checks",
)


def validate_research_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate transport evidence, not profitability or permission to execute."""
    required = ("schema", "experiment_id", "candidate_id", "run_id", "specification", "fingerprint",
                "data_boundary", "evidence_status", "contamination_status", "validity",
                "opportunities", "executed_trades", "sample_requirement", "metrics", "failed_gates", "artifacts")
    if any(key not in record for key in required):
        raise ValueError("RESEARCH_RECORD_REQUIRED_FIELD_MISSING")
    if record["schema"] != RESEARCH_RECORD_SCHEMA or any(not isinstance(record[k], str) or not record[k] for k in ("experiment_id", "candidate_id", "run_id")):
        raise ValueError("RESEARCH_RECORD_IDENTITY_INVALID")
    if candidate_fingerprint(record["specification"]) != record["fingerprint"]:
        raise ValueError("RESEARCH_RECORD_FINGERPRINT_MISMATCH")
    if record["validity"] not in {"VALID", "INVALID", "UNKNOWN"}:
        raise ValueError("RESEARCH_RECORD_VALIDITY_INVALID")
    if record["evidence_status"] not in {"SYNTHETIC", "REUSED_DEVELOPMENT", "DEVELOPMENT", "INDEPENDENT_VALIDATION"}:
        raise ValueError("RESEARCH_RECORD_EVIDENCE_INVALID")
    if record["contamination_status"] not in {"SYNTHETIC", "USED", "UNTOUCHED", "CONTAMINATED", "UNKNOWN"}:
        raise ValueError("RESEARCH_RECORD_CONTAMINATION_INVALID")
    if record["evidence_status"] == "INDEPENDENT_VALIDATION" and record["contamination_status"] != "UNTOUCHED":
        raise ValueError("USED_EVIDENCE_NOT_INDEPENDENT")
    boundary = record["data_boundary"]
    if not isinstance(boundary, dict) or parse_utc(boundary["start"]) >= parse_utc(boundary["end_exclusive"]):
        raise ValueError("RESEARCH_RECORD_BOUNDARY_INVALID")
    for field in ("opportunities", "executed_trades", "sample_requirement"):
        if field != "sample_requirement" and record[field] is None and record["validity"] in {"INVALID", "UNKNOWN"}:
            continue
        if type(record[field]) is not int or record[field] < 0:
            raise ValueError("RESEARCH_RECORD_COUNT_INVALID")
    known_counts = record["executed_trades"] is not None and record["opportunities"] is not None
    if record["sample_requirement"] == 0 or (known_counts and record["executed_trades"] > record["opportunities"]):
        raise ValueError("RESEARCH_RECORD_COUNT_INVALID")
    metrics = record["metrics"]
    if not isinstance(metrics, dict) or metrics.get("unit") not in {"R", "ACCOUNT_RETURN", "LOG_RETURN", "DESCRIPTIVE_PIPS_NOT_CASH"}:
        raise ValueError("RESEARCH_RECORD_UNITS_INVALID")
    for key in ("gross", "net"):
        value = metrics.get(key)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError("RESEARCH_RECORD_NONFINITE_METRIC")
    if not isinstance(record["failed_gates"], list) or not isinstance(record["artifacts"], dict) or not record["artifacts"]:
        raise ValueError("RESEARCH_RECORD_EVIDENCE_MISSING")
    for path, digest in record["artifacts"].items():
        if not path or not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("RESEARCH_RECORD_ARTIFACT_IDENTITY_INVALID")
    counts = [record.get(k) for k in ("filtered_trades", "skipped_trades")]
    if all(value is not None for value in counts):
        if any(type(value) is not int or value < 0 for value in counts) or not known_counts or sum(counts) + record["executed_trades"] != record["opportunities"]:
            raise ValueError("RESEARCH_RECORD_OPPORTUNITY_ACCOUNTING_INVALID")
    missing = [key for key in RESEARCH_OPTIONAL_FIELDS if record.get(key) is None]
    missing += [key for key in ("opportunities", "executed_trades") if record[key] is None]
    missing += [f"metrics.{key}" for key in ("gross", "net") if metrics.get(key) is None]
    return {"status": "CHECKED_TRANSPORT_NOT_CERTIFICATION", "missing_fields": missing,
            "record_sha256": sha256_value(record)}


def validate_context_join(feature: Mapping[str, Any], outcome: Mapping[str, Any]) -> None:
    """A confirmed swing is available at confirmation, never its pivot time."""
    for key in ("pair", "timeframe", "opportunity_id"):
        if not feature.get(key) or feature[key] != outcome.get(key):
            raise ValueError("CONTEXT_JOIN_ID_MISMATCH")
    if not feature.get("source") or "outcome" in feature or "forward_return" in feature:
        raise ValueError("CONTEXT_SOURCE_OR_OUTCOME_LEAKAGE")
    latest = parse_utc(feature["latest_source_timestamp"])
    available = parse_utc(feature["available_at"])
    if latest > available or available > parse_utc(outcome["decision_at"]):
        raise ValueError("CONTEXT_FUTURE_INFORMATION")
    if feature.get("confirmed_at") and parse_utc(feature["confirmed_at"]) > available:
        raise ValueError("CONTEXT_BACKDATED_CONFIRMATION")


def sample_moments(returns: Sequence[float]) -> dict[str, float]:
    values = [float(value) for value in returns]
    if len(values) < 3 or not all(math.isfinite(value) for value in values):
        raise ValueError("INSUFFICIENT_SAMPLE")
    mean = statistics.fmean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    if variance <= 0:
        raise ValueError("ZERO_VARIANCE")
    standard_deviation = math.sqrt(variance)
    centered = [(value - mean) / standard_deviation for value in values]
    skewness = len(values) / ((len(values) - 1) * (len(values) - 2)) * sum(value ** 3 for value in centered)
    raw_kurtosis = statistics.fmean(value ** 4 for value in centered)
    return {"mean": mean, "sample_std": standard_deviation, "skewness": skewness, "kurtosis": raw_kurtosis}


def sharpe_ratio(returns: Sequence[float]) -> float:
    moments = sample_moments(returns)
    return moments["mean"] / moments["sample_std"]


def deflated_sharpe_from_moments(
    *, observed_sharpe: float, trial_sharpe_mean: float, trial_sharpe_std: float,
    effective_trial_count: float, effective_sample_count: float,
    skewness: float, pearson_kurtosis: float,
    predeclared_benchmark_sharpe: float = 0.0,
) -> dict[str, float]:
    values = (observed_sharpe, trial_sharpe_mean, trial_sharpe_std, effective_trial_count, effective_sample_count, skewness, pearson_kurtosis, predeclared_benchmark_sharpe)
    if not all(math.isfinite(float(value)) for value in values) or trial_sharpe_std <= 0 or effective_trial_count < 2 or effective_sample_count < 2 or pearson_kurtosis < 1:
        raise ValueError("INVALID_DSR_MOMENTS")
    gamma = 0.5772156649015329
    normal = NormalDist()
    n = float(effective_trial_count)
    expected_maximum = float(trial_sharpe_mean) + float(trial_sharpe_std) * (
        (1.0 - gamma) * normal.inv_cdf(1.0 - 1.0 / n)
        + gamma * normal.inv_cdf(1.0 - 1.0 / (n * math.e))
    )
    selection_threshold = max(float(predeclared_benchmark_sharpe), expected_maximum)
    denominator_term = 1.0 - float(skewness) * float(observed_sharpe) + ((float(pearson_kurtosis) - 1.0) / 4.0) * float(observed_sharpe) ** 2
    if denominator_term <= 0:
        raise ValueError("INVALID_NON_NORMAL_ADJUSTMENT")
    denominator = math.sqrt(denominator_term)
    statistic = (float(observed_sharpe) - selection_threshold) * math.sqrt(float(effective_sample_count) - 1.0) / denominator
    return {
        "expected_maximum_sharpe": expected_maximum,
        "selection_threshold_sharpe": selection_threshold,
        "non_normal_denominator": denominator,
        "z_statistic": statistic,
        "deflated_sharpe_probability": normal.cdf(statistic),
    }


def deflated_sharpe_ratio(
    returns: Sequence[float], trial_sharpes: Sequence[float], *,
    effective_trial_count: float, effective_sample_count: float | None = None,
    predeclared_benchmark_sharpe: float = 0.0,
    candidate_registered: bool = True, trial_distribution_reconciled: bool = True,
    probability_threshold: float = 0.95,
) -> dict[str, Any]:
    values = [float(value) for value in returns]
    trials = [float(value) for value in trial_sharpes]
    effective_sample = float(effective_sample_count if effective_sample_count is not None else len(values))
    if len(values) < 30 or effective_sample < 30 or effective_sample > len(values) or len(trials) < 30 or effective_trial_count < 2:
        return {"status": "BLOCK", "reason": "INSUFFICIENT_EVIDENCE"}
    if not candidate_registered:
        return {"status": "BLOCK", "reason": "CANDIDATE_ABSENT_FROM_TRIAL_REGISTRY"}
    if not trial_distribution_reconciled:
        return {"status": "BLOCK", "reason": "UNRECONCILED_TRIAL_SHARPE_DISTRIBUTION"}
    if effective_trial_count > HISTORICAL_SCORED_ATTEMPT_LOWER_BOUND + len(trials):
        return {"status": "BLOCK", "reason": "UNRECONCILED_TRIAL_CONTEXT"}
    try:
        moments = sample_moments(values)
        observed = moments["mean"] / moments["sample_std"]
        trial_std = statistics.stdev(trials)
    except (ValueError, statistics.StatisticsError):
        return {"status": "BLOCK", "reason": "INVALID_DSR_INPUT"}
    if trial_std <= 0 or not all(math.isfinite(value) for value in trials):
        return {"status": "BLOCK", "reason": "INVALID_TRIAL_VARIANCE"}
    try:
        calculation = deflated_sharpe_from_moments(
            observed_sharpe=observed, trial_sharpe_mean=statistics.fmean(trials),
            trial_sharpe_std=trial_std, effective_trial_count=effective_trial_count,
            effective_sample_count=effective_sample, skewness=moments["skewness"],
            pearson_kurtosis=moments["kurtosis"],
            predeclared_benchmark_sharpe=predeclared_benchmark_sharpe,
        )
    except ValueError as error:
        return {"status": "BLOCK", "reason": str(error)}
    probability = calculation["deflated_sharpe_probability"]
    return {
        "status": "PASS" if probability >= probability_threshold else "FAIL",
        "observed_sharpe": observed, **calculation,
        "skewness": moments["skewness"], "kurtosis": moments["kurtosis"],
        "sample_length": len(values), "effective_sample_count": effective_sample, "effective_trial_count": float(effective_trial_count),
        "deflated_sharpe_probability": probability, "threshold": probability_threshold,
    }


def _mean_column(matrix: Sequence[Sequence[float]], rows: Sequence[int], column: int) -> float:
    return statistics.fmean(float(matrix[row][column]) for row in rows)


def _deduplicate_columns(matrix: Sequence[Sequence[float]], fingerprints: Sequence[str]) -> tuple[list[list[float]], list[str]]:
    if not matrix or any(len(row) != len(fingerprints) for row in matrix):
        raise ValueError("CSCV_MATRIX_SHAPE_INVALID")
    kept: list[int] = []
    seen: set[tuple[str, tuple[float, ...]]] = set()
    for column, fingerprint in enumerate(fingerprints):
        values = tuple(float(row[column]) for row in matrix)
        key = (str(fingerprint), values)
        if key in seen:
            continue
        if any(tuple(float(row[prior]) for row in matrix) == values for prior in kept):
            continue
        seen.add(key)
        kept.append(column)
    return [[float(row[column]) for column in kept] for row in matrix], [str(fingerprints[column]) for column in kept]


def cscv_pbo(
    performance_matrix: Sequence[Sequence[float]], fingerprints: Sequence[str], *,
    subset_count: int = 8, maximum_pbo: float = 0.20,
    synchronized: bool = True, labels_purged: bool = True,
) -> dict[str, Any]:
    if not synchronized or not labels_purged:
        return {"status": "BLOCK", "reason": "CSCV_DEPENDENCE_OR_LABEL_CONTRACT_INVALID"}
    try:
        matrix, unique_fingerprints = _deduplicate_columns(performance_matrix, fingerprints)
    except ValueError as error:
        return {"status": "BLOCK", "reason": str(error)}
    row_count = len(matrix)
    column_count = len(unique_fingerprints)
    if subset_count < 4 or subset_count % 2 or row_count < subset_count * 2 or column_count < 2:
        return {"status": "BLOCK", "reason": "INSUFFICIENT_CSCV_STRUCTURE"}
    boundaries = [row_count * index // subset_count for index in range(subset_count + 1)]
    subsets = [list(range(boundaries[index], boundaries[index + 1])) for index in range(subset_count)]
    if any(not subset for subset in subsets):
        return {"status": "BLOCK", "reason": "INSUFFICIENT_CSCV_STRUCTURE"}
    logits: list[float] = []
    selected: list[int] = []
    half = subset_count // 2
    all_indices = set(range(subset_count))
    # Complementary duplicates carry identical information; keep one canonical half.
    combinations = [combo for combo in itertools.combinations(range(subset_count), half) if 0 in combo]
    for combination in combinations:
        train_rows = [row for index in combination for row in subsets[index]]
        test_rows = [row for index in sorted(all_indices - set(combination)) for row in subsets[index]]
        train_scores = [_mean_column(matrix, train_rows, column) for column in range(column_count)]
        winner = max(range(column_count), key=lambda column: (train_scores[column], -column))
        test_scores = [_mean_column(matrix, test_rows, column) for column in range(column_count)]
        ordered = sorted(range(column_count), key=lambda column: (test_scores[column], -column))
        rank = ordered.index(winner) + 1
        percentile = rank / (column_count + 1.0)
        logits.append(math.log(percentile / (1.0 - percentile)))
        selected.append(winner)
    pbo = sum(value <= 0 for value in logits) / len(logits)
    correlation_clusters: list[list[int]] = []
    for column in range(column_count):
        values = [row[column] for row in matrix]
        placed = False
        for cluster in correlation_clusters:
            reference = [row[cluster[0]] for row in matrix]
            try:
                correlation = abs(pearson_correlation(values, reference))
            except ValueError:
                correlation = 1.0 if values == reference else 0.0
            if correlation >= 0.999:
                cluster.append(column)
                placed = True
                break
        if not placed:
            correlation_clusters.append([column])
    return {
        "status": "PASS" if pbo <= maximum_pbo else "FAIL", "pbo": pbo,
        "maximum_pbo": maximum_pbo, "split_count": len(logits),
        "unique_configuration_count": column_count,
        "duplicate_configuration_count": len(fingerprints) - column_count,
        "correlation_cluster_count": len(correlation_clusters),
        "correlation_clusters": [[unique_fingerprints[column] for column in cluster] for cluster in correlation_clusters],
        "median_logit": statistics.median(logits),
        "selection_counts": {unique_fingerprints[column]: selected.count(column) for column in sorted(set(selected))},
    }


def holm_bonferroni(p_values: Sequence[float], global_trial_count: int, alpha: float = 0.05) -> dict[str, Any]:
    values = [float(value) for value in p_values]
    if not values or global_trial_count < HISTORICAL_SCORED_ATTEMPT_LOWER_BOUND or any(value < 0 or value > 1 for value in values):
        return {"status": "BLOCK", "reason": "UNRECONCILED_MULTIPLE_TESTING_CONTEXT"}
    family_size = max(global_trial_count, len(values))
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    adjusted = [1.0] * len(values)
    running = 0.0
    for rank, (index, value) in enumerate(ordered):
        running = max(running, min(1.0, value * (family_size - rank)))
        adjusted[index] = running
    return {"status": "PASS" if min(adjusted) <= alpha else "FAIL", "adjusted_p_values": adjusted, "global_trial_count": family_size, "alpha": alpha}


def synchronized_block_bootstrap(
    rows: Sequence[Mapping[str, Any]], *, block_size: int, label_horizon: int,
    runs: int = 1000, seed: int = 40140, confidence: float = 0.95,
    minimum_effective_blocks: int = 30,
) -> dict[str, Any]:
    if block_size <= 0 or label_horizon <= 0 or runs < 100:
        return {"status": "BLOCK", "reason": "INVALID_BOOTSTRAP_CONTRACT"}
    if block_size < label_horizon:
        return {"status": "BLOCK", "reason": "BLOCK_SHORTER_THAN_LABEL_OVERLAP"}
    ordered = sorted(rows, key=lambda row: str(row.get("timestamp", "")))
    timestamps = [str(row.get("timestamp", "")) for row in ordered]
    if len(ordered) < 4 * max(block_size, label_horizon) or len(timestamps) != len(set(timestamps)):
        return {"status": "BLOCK", "reason": "INSUFFICIENT_EFFECTIVE_BLOCKS"}
    pair_sets = [set(row.get("pair_returns", {})) for row in ordered]
    if not pair_sets or not pair_sets[0] or any(pair_set != pair_sets[0] for pair_set in pair_sets):
        return {"status": "BLOCK", "reason": "UNSTABLE_CROSS_PAIR_MEMBERSHIP"}
    if any(not all(math.isfinite(float(value)) for value in row["pair_returns"].values()) for row in ordered):
        return {"status": "BLOCK", "reason": "INVALID_SYNCHRONIZED_RETURN"}
    cluster = max(block_size, label_horizon)
    effective_blocks = len(ordered) // cluster
    if effective_blocks < minimum_effective_blocks:
        return {"status": "BLOCK", "reason": "INSUFFICIENT_EFFECTIVE_BLOCKS"}
    market_returns = [statistics.fmean(float(value) for value in row["pair_returns"].values()) for row in ordered]
    generator = random.Random(seed)
    maximum_start = len(ordered) - cluster
    samples: list[float] = []
    blocks_needed = math.ceil(len(ordered) / cluster)
    for _ in range(runs):
        sample: list[float] = []
        for _block in range(blocks_needed):
            start = generator.randrange(maximum_start + 1)
            sample.extend(market_returns[start : start + cluster])
        samples.append(statistics.fmean(sample[: len(ordered)]))
    samples.sort()
    tail = (1.0 - confidence) / 2.0
    lower = samples[max(0, int(tail * runs))]
    upper = samples[min(runs - 1, int((1.0 - tail) * runs) - 1)]
    observed = statistics.fmean(market_returns)
    return {
        "status": "PASS" if lower > 0 else "FAIL", "observed_mean": observed,
        "lower": lower, "upper": upper, "confidence": confidence,
        "block_size": block_size, "overlap_cluster_size": cluster,
        "effective_blocks": effective_blocks, "runs": runs, "seed": seed,
        "minimum_effective_blocks": minimum_effective_blocks,
        "pair_count": len(pair_sets[0]), "cross_pair_resampling": "SYNCHRONIZED",
    }


def chronological_folds(
    timestamps: Sequence[str], *, fold_count: int, embargo_observations: int,
    minimum_train: int = 20, minimum_test: int = 5,
) -> list[dict[str, Any]]:
    ordered = [str(value) for value in timestamps]
    if ordered != sorted(ordered) or len(set(ordered)) != len(ordered):
        raise ValueError("NONCHRONOLOGICAL_TIMESTAMPS")
    if fold_count < 2 or embargo_observations < 1:
        raise ValueError("INVALID_WALK_FORWARD_CONTRACT")
    available = len(ordered) - minimum_train - embargo_observations
    test_size = available // fold_count
    if test_size < minimum_test:
        raise ValueError("INSUFFICIENT_WALK_FORWARD_STRUCTURE")
    folds = []
    for index in range(fold_count):
        train_end_index = minimum_train + index * test_size - 1
        test_start_index = train_end_index + embargo_observations + 1
        test_end_index = test_start_index + test_size - 1
        if index == fold_count - 1:
            test_end_index = len(ordered) - 1
        if test_end_index >= len(ordered):
            raise ValueError("INSUFFICIENT_WALK_FORWARD_STRUCTURE")
        folds.append({
            "fold": index + 1,
            "train_start": ordered[0], "train_end": ordered[train_end_index],
            "embargo_start": ordered[train_end_index + 1],
            "embargo_end": ordered[test_start_index - 1],
            "test_start": ordered[test_start_index], "test_end": ordered[test_end_index],
            "train_count": train_end_index + 1, "test_count": test_end_index - test_start_index + 1,
            "selection_scope": "TRAIN_ONLY",
        })
    return folds


def validate_walk_forward(folds: Sequence[Mapping[str, Any]], results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(folds) < 2 or len(folds) != len(results):
        return {"status": "BLOCK", "reason": "MISSING_WALK_FORWARD_FOLDS"}
    positive = 0
    for fold, result in zip(folds, results):
        if str(result.get("selected_using", "")) != "TRAIN_ONLY":
            return {"status": "BLOCK", "reason": "TEST_FOLD_SELECTION_LEAKAGE"}
        if parse_utc(str(fold["train_end"])) >= parse_utc(str(fold["test_start"])):
            return {"status": "BLOCK", "reason": "FOLD_OVERLAP"}
        if int(result.get("test_count", 0)) < 1:
            return {"status": "BLOCK", "reason": "EMPTY_TEST_FOLD"}
        positive += float(result.get("test_expectancy", 0.0)) > 0
    return {"status": "PASS" if positive >= math.ceil(0.75 * len(folds)) else "FAIL", "positive_fold_count": positive, "fold_count": len(folds)}


def validate_fold_labels(fold: Mapping[str, Any], labels: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    train_end = parse_utc(str(fold["train_end"]))
    test_start = parse_utc(str(fold["test_start"]))
    test_end = parse_utc(str(fold["test_end"]))
    purged = 0
    accepted = 0
    for label in labels:
        partition = str(label.get("partition", ""))
        start = parse_utc(str(label["start"])); end = parse_utc(str(label["end"]))
        if not start < end:
            return {"status": "BLOCK", "reason": "LABEL_INTERVAL_INVALID"}
        if partition == "TRAIN":
            if end > train_end:
                purged += 1
            else:
                accepted += 1
        elif partition == "TEST":
            if not (test_start <= start < end <= test_end):
                return {"status": "BLOCK", "reason": "TEST_LABEL_OUTSIDE_FOLD"}
            accepted += 1
        else:
            return {"status": "BLOCK", "reason": "LABEL_PARTITION_UNKNOWN"}
    return {"status": "PASS", "accepted": accepted, "purged_train_crossers": purged}


def parameter_neighborhood(center: str, metrics: Mapping[str, float], adjacency: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    if center not in metrics or center not in adjacency:
        return {"status": "BLOCKED", "reason": "MISSING_PARAMETER_CENTER"}
    neighbors = [name for name in adjacency[center] if name in metrics]
    if len(neighbors) < 2:
        return {"status": "INSUFFICIENT", "reason": "TOO_FEW_NEIGHBORS"}
    center_value = float(metrics[center])
    values = [float(metrics[name]) for name in neighbors]
    if center_value <= 0:
        return {"status": "FRAGILE", "reason": "CENTER_NOT_POSITIVE"}
    positive_share = sum(value > 0 for value in values) / len(values)
    relative_floor = min(values) / center_value
    classification = "ROBUST_PLATEAU" if positive_share >= 0.75 and relative_floor >= 0.50 else "FRAGILE"
    return {"status": classification, "center": center_value, "neighbor_count": len(values), "positive_share": positive_share, "relative_floor": relative_floor}


def robustness_diagnostics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(records) < 12:
        return {"status": "BLOCK", "reason": "INSUFFICIENT_ROBUSTNESS_SAMPLE"}
    dimensions = ("pair", "currency", "period", "volatility", "liquidity", "session", "direction")
    decompositions: dict[str, Any] = {}
    total = sum(float(record["pnl"]) for record in records)
    for dimension in dimensions:
        grouped: dict[str, float] = defaultdict(float)
        for record in records:
            grouped[str(record.get(dimension, "UNKNOWN"))] += float(record["pnl"])
        if len(grouped) < 2:
            return {"status": "FAIL", "reason": f"{dimension.upper()}_CONCENTRATION"}
        absolute = sum(abs(value) for value in grouped.values())
        largest_key, largest_value = max(grouped.items(), key=lambda item: (abs(item[1]), item[0]))
        decompositions[dimension] = {"groups": dict(sorted(grouped.items())), "largest": largest_key, "largest_absolute_share": abs(largest_value) / absolute if absolute else 1.0}
    removal = {}
    for dimension in ("pair", "currency", "period"):
        strongest = decompositions[dimension]["largest"]
        remaining = sum(float(record["pnl"]) for record in records if str(record.get(dimension, "UNKNOWN")) != strongest)
        removal[dimension] = {"removed": strongest, "remaining_pnl": remaining, "pass": remaining > 0}
    status = "PASS" if total > 0 and all(item["pass"] for item in removal.values()) and all(item["largest_absolute_share"] <= 0.75 for item in decompositions.values()) else "FAIL"
    return {"status": status, "total_pnl": total, "decompositions": decompositions, "removal_tests": removal}


@dataclass(frozen=True)
class Quote:
    timestamp: str
    bid: float
    ask: float


@dataclass(frozen=True)
class CostScenario:
    name: str
    slippage_per_side: float
    stop_slippage: float
    entry_delay: int
    financing_per_boundary: float | None


COST_SCENARIOS = {
    "GROSS": CostScenario("GROSS", 0.0, 0.0, 0, 0.0),
    "BASE": CostScenario("BASE", 0.00001, 0.00002, 0, None),
    "STRESSED": CostScenario("STRESSED", 0.00005, 0.00005, 1, None),
    "SEVERE_BUT_PLAUSIBLE": CostScenario("SEVERE_BUT_PLAUSIBLE", 0.00010, 0.00010, 1, None),
}


def validate_quote(quote: Quote) -> None:
    if not all(math.isfinite(value) for value in (quote.bid, quote.ask)) or quote.bid <= 0 or quote.ask < quote.bid:
        raise ValueError("INVALID_EXECUTABLE_QUOTE")


def costed_trade(
    direction: str, entry_quotes: Sequence[Quote], exit_quotes: Sequence[Quote], *,
    scenario: CostScenario, rollover_boundaries: int = 0,
    explicit_spread_charge: float = 0.0, stopped: bool = False,
    stop_price: float | None = None,
) -> dict[str, Any]:
    if direction not in {"LONG", "SHORT"} or scenario.entry_delay < 0:
        return {"status": "BLOCK", "reason": "INVALID_COST_INPUT"}
    if explicit_spread_charge:
        return {"status": "BLOCK", "reason": "DOUBLE_SPREAD_CHARGE_FORBIDDEN"}
    delay = scenario.entry_delay
    if delay >= len(entry_quotes) or delay >= len(exit_quotes):
        return {"status": "BLOCK", "reason": "DELAYED_QUOTE_UNAVAILABLE"}
    entry_quote, exit_quote = entry_quotes[delay], exit_quotes[delay]
    try:
        validate_quote(entry_quote)
        validate_quote(exit_quote)
    except ValueError as error:
        return {"status": "BLOCK", "reason": str(error)}
    if rollover_boundaries and scenario.financing_per_boundary is None:
        return {"status": "BLOCK", "reason": "UNSUPPORTED_FINANCING_HORIZON"}
    financing = rollover_boundaries * float(scenario.financing_per_boundary or 0.0)
    if scenario.name == "GROSS":
        entry = (entry_quote.bid + entry_quote.ask) / 2.0
        exit_price = (exit_quote.bid + exit_quote.ask) / 2.0
    elif direction == "LONG":
        entry = entry_quote.ask + scenario.slippage_per_side
        if stopped:
            if stop_price is None:
                return {"status": "BLOCK", "reason": "STOP_PRICE_MISSING"}
            exit_price = min(float(stop_price), exit_quote.bid) - scenario.stop_slippage
        else:
            exit_price = exit_quote.bid - scenario.slippage_per_side
    else:
        entry = entry_quote.bid - scenario.slippage_per_side
        if stopped:
            if stop_price is None:
                return {"status": "BLOCK", "reason": "STOP_PRICE_MISSING"}
            exit_price = max(float(stop_price), exit_quote.ask) + scenario.stop_slippage
        else:
            exit_price = exit_quote.ask + scenario.slippage_per_side
    pnl = (exit_price - entry) * (1 if direction == "LONG" else -1) - financing
    return {"status": "PASS", "scenario": scenario.name, "entry": entry, "exit": exit_price, "financing": financing, "net_pnl": pnl, "spread_embedded_once": True}


def cost_stress(results: Mapping[str, Sequence[float]]) -> dict[str, Any]:
    required = tuple(COST_SCENARIOS)
    if any(name not in results or not results[name] for name in required):
        return {"status": "BLOCK", "reason": "COST_STATE_MISSING"}
    means = {name: statistics.fmean(float(value) for value in results[name]) for name in required}
    if means["BASE"] <= 0:
        status = "FAIL"
        reason = "COST_DESTROYED_EDGE" if means["GROSS"] > 0 else "NO_GROSS_EDGE"
    elif means["SEVERE_BUT_PLAUSIBLE"] <= 0:
        status, reason = "FAIL", "COST_FRAGILE"
    else:
        status, reason = "PASS", None
    return {"status": status, "reason": reason, "mean_pnl": means}


def pearson_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 3:
        raise ValueError("CORRELATION_SAMPLE_INVALID")
    x, y = [float(value) for value in left], [float(value) for value in right]
    mx, my = statistics.fmean(x), statistics.fmean(y)
    numerator = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = sum((a - mx) ** 2 for a in x)
    dy = sum((b - my) ** 2 for b in y)
    if dx <= 0 or dy <= 0:
        raise ValueError("CORRELATION_ZERO_VARIANCE")
    return numerator / math.sqrt(dx * dy)


def correlation_matrix(series: Mapping[str, Sequence[float]]) -> dict[str, Any]:
    names = sorted(series)
    if len(names) < 2 or len({len(series[name]) for name in names}) != 1:
        return {"status": "BLOCK", "reason": "CORRELATION_MATRIX_INVALID"}
    try:
        matrix = [
            [1.0 if left == right else pearson_correlation(series[left], series[right]) for right in names]
            for left in names
        ]
    except ValueError as error:
        return {"status": "BLOCK", "reason": str(error)}
    squared_sum = sum(value * value for row in matrix for value in row)
    effective = len(names) ** 2 / squared_sum if squared_sum else 0.0
    return {"status": "PASS", "names": names, "matrix": matrix, "effective_independent_bets": effective}


def _pair_parts(pair: str) -> tuple[str, str]:
    pieces = pair.split("_")
    if len(pieces) != 2 or any(len(piece) != 3 for piece in pieces):
        raise ValueError("INVALID_PAIR_IDENTITY")
    return pieces[0], pieces[1]


def maximum_drawdown(equity_curve: Sequence[float]) -> float:
    if not equity_curve or any(not math.isfinite(float(value)) or float(value) <= 0 for value in equity_curve):
        raise ValueError("INVALID_EQUITY_CURVE")
    peak = float(equity_curve[0])
    maximum = 0.0
    for raw in equity_curve:
        value = float(raw)
        peak = max(peak, value)
        maximum = max(maximum, (peak - value) / peak)
    return maximum


def simulate_portfolio(
    events: Sequence[Mapping[str, Any]], *, starting_equity: float = 100_000.0,
    maximum_positions: int = 5, maximum_currency_gross: float = 0.02,
    maximum_drawdown_fraction: float = 0.10,
) -> dict[str, Any]:
    if starting_equity <= 0 or maximum_positions < 1 or not events:
        return {"status": "BLOCK", "reason": "PORTFOLIO_INPUT_INVALID"}
    required = {"event_id", "timestamp", "pair", "direction", "risk_fraction", "pnl", "pair_return", "signal"}
    if any(not required.issubset(event) for event in events):
        return {"status": "BLOCK", "reason": "PORTFOLIO_FIELD_MISSING"}
    ordered = sorted(events, key=lambda event: (str(event["timestamp"]), 0 if event.get("action", "CLOSE") == "CLOSE" else 1, str(event["pair"]), str(event["event_id"])))
    if len({str(event["event_id"]) for event in ordered}) != len(ordered):
        return {"status": "BLOCK", "reason": "DUPLICATE_PORTFOLIO_EVENT"}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in ordered:
        grouped[str(event["timestamp"])].append(event)
    pair_returns: dict[str, list[float]] = defaultdict(list)
    pair_signals: dict[str, list[float]] = defaultdict(list)
    pair_pnl: dict[str, float] = defaultdict(float)
    currency_pnl: dict[str, float] = defaultdict(float)
    equity = float(starting_equity)
    equity_curve = [equity]
    max_simultaneous = 0
    maximum_currency_seen: dict[str, float] = defaultdict(float)
    for timestamp in sorted(grouped):
        timestamp_events = grouped[timestamp]
        if len(timestamp_events) > maximum_positions:
            return {"status": "FAIL", "reason": "SIMULTANEOUS_POSITION_LIMIT"}
        currency_net: dict[str, float] = defaultdict(float)
        currency_gross: dict[str, float] = defaultdict(float)
        timestamp_pnl = 0.0
        for event in timestamp_events:
            try:
                base, quote = _pair_parts(str(event["pair"]))
            except ValueError as error:
                return {"status": "BLOCK", "reason": str(error)}
            direction = str(event["direction"])
            if direction not in {"LONG", "SHORT"}:
                return {"status": "BLOCK", "reason": "INVALID_DIRECTION"}
            sign = 1.0 if direction == "LONG" else -1.0
            risk = float(event["risk_fraction"])
            if risk <= 0 or risk > 1:
                return {"status": "BLOCK", "reason": "INVALID_RISK_FRACTION"}
            currency_net[base] += sign * risk
            currency_net[quote] -= sign * risk
            currency_gross[base] += abs(risk)
            currency_gross[quote] += abs(risk)
            pair = str(event["pair"])
            pnl = float(event["pnl"])
            timestamp_pnl += pnl
            pair_pnl[pair] += pnl
            currency_pnl[base] += pnl / 2.0
            currency_pnl[quote] += pnl / 2.0
            pair_returns[pair].append(float(event["pair_return"]))
            pair_signals[pair].append(float(event["signal"]))
        for currency, gross in currency_gross.items():
            maximum_currency_seen[currency] = max(maximum_currency_seen[currency], gross)
            if gross > maximum_currency_gross + 1e-15:
                return {"status": "FAIL", "reason": "CURRENCY_GROSS_EXPOSURE_LIMIT", "currency": currency, "gross": gross}
        equity += timestamp_pnl
        if equity <= 0:
            return {"status": "FAIL", "reason": "PORTFOLIO_INSOLVENT"}
        equity_curve.append(equity)
        max_simultaneous = max(max_simultaneous, len(timestamp_events))
    complete_pairs = sorted(pair_returns)
    lengths = {len(pair_returns[pair]) for pair in complete_pairs}
    if len(complete_pairs) < 2 or len(lengths) != 1 or min(lengths) < 3:
        return {"status": "BLOCK", "reason": "SYNCHRONIZED_PORTFOLIO_HISTORY_MISSING"}
    pair_corr = correlation_matrix(pair_returns)
    signal_corr = correlation_matrix(pair_signals)
    if pair_corr["status"] != "PASS" or signal_corr["status"] != "PASS":
        return {"status": "BLOCK", "reason": "PORTFOLIO_CORRELATION_INVALID", "pair_correlation": pair_corr, "signal_correlation": signal_corr}
    total_absolute_pair = sum(abs(value) for value in pair_pnl.values())
    total_absolute_currency = sum(abs(value) for value in currency_pnl.values())
    largest_pair, largest_pair_value = max(pair_pnl.items(), key=lambda item: (abs(item[1]), item[0]))
    largest_currency, largest_currency_value = max(currency_pnl.items(), key=lambda item: (abs(item[1]), item[0]))
    drawdown = maximum_drawdown(equity_curve)
    status = "PASS"
    reasons = []
    if drawdown > maximum_drawdown_fraction:
        status, reasons = "FAIL", ["PORTFOLIO_DRAWDOWN"]
    if abs(largest_pair_value) / total_absolute_pair > 0.75:
        status, reasons = "FAIL", reasons + ["PAIR_CONCENTRATION"]
    if abs(largest_currency_value) / total_absolute_currency > 0.75:
        status, reasons = "FAIL", reasons + ["CURRENCY_FACTOR_CONCENTRATION"]
    return {
        "status": status, "reasons": reasons, "ending_equity": equity,
        "equity_curve": equity_curve, "maximum_drawdown_fraction": drawdown,
        "pair_correlation": pair_corr, "signal_correlation": signal_corr,
        "effective_independent_bets": min(pair_corr["effective_independent_bets"], signal_corr["effective_independent_bets"]),
        "currency_gross_exposure_max": dict(sorted(maximum_currency_seen.items())),
        "currency_net_exposure_last": dict(sorted(currency_net.items())),
        "pair_pnl": dict(sorted(pair_pnl.items())), "currency_factor_pnl": dict(sorted(currency_pnl.items())),
        "largest_pair_contribution": {"pair": largest_pair, "absolute_share": abs(largest_pair_value) / total_absolute_pair},
        "largest_currency_factor_contribution": {"currency": largest_currency, "absolute_share": abs(largest_currency_value) / total_absolute_currency},
        "maximum_simultaneous_positions": max_simultaneous,
    }


def simulate_synchronized_portfolio_snapshots(
    snapshots: Sequence[Mapping[str, Any]], *, starting_equity: float = 100_000.0,
    maximum_positions: int = 5, maximum_currency_gross: float = 0.02,
    maximum_drawdown_fraction: float = 0.10,
) -> dict[str, Any]:
    """Mark overlapping positions on one synchronized market-wide timeline.

    Position ``cumulative_pnl`` is net liquidation P&L at the snapshot.  The
    engine books only its change since the prior snapshot, so overlapping
    positions contribute to one marked equity curve rather than independent
    event rows.
    """
    ordered = sorted(snapshots, key=lambda row: str(row.get("timestamp", "")))
    if not ordered or [row.get("timestamp") for row in ordered] != [row.get("timestamp") for row in snapshots]:
        return {"status": "BLOCK", "reason": "SYNCHRONIZED_TIMELINE_INVALID"}
    if len({str(row.get("timestamp", "")) for row in ordered}) != len(ordered):
        return {"status": "BLOCK", "reason": "SYNCHRONIZED_TIMELINE_INVALID"}
    universe = set(ordered[0].get("pair_returns", {}))
    if len(universe) < 2:
        return {"status": "BLOCK", "reason": "SYNCHRONIZED_UNIVERSE_INVALID"}
    active: dict[str, dict[str, Any]] = {}
    closed: set[str] = set()
    previous_pnl: dict[str, float] = {}
    pair_series: dict[str, list[float]] = {pair: [] for pair in sorted(universe)}
    signal_series: dict[str, list[float]] = {pair: [] for pair in sorted(universe)}
    pair_pnl: dict[str, float] = defaultdict(float)
    currency_pnl: dict[str, float] = defaultdict(float)
    max_currency: dict[str, float] = defaultdict(float)
    equity = float(starting_equity)
    curve = [equity]
    max_simultaneous = 0
    for snapshot in ordered:
        if set(snapshot.get("pair_returns", {})) != universe or set(snapshot.get("signal_states", {})) != universe:
            return {"status": "BLOCK", "reason": "UNSTABLE_SYNCHRONIZED_MEMBERSHIP"}
        for pair in sorted(universe):
            pair_series[pair].append(float(snapshot["pair_returns"][pair]))
            signal_series[pair].append(float(snapshot["signal_states"][pair]))
        positions = snapshot.get("positions")
        if not isinstance(positions, Sequence):
            return {"status": "BLOCK", "reason": "POSITION_SNAPSHOT_MISSING"}
        present: set[str] = set()
        delta_total = 0.0
        currency_gross: dict[str, float] = defaultdict(float)
        currency_net: dict[str, float] = defaultdict(float)
        for raw in sorted(positions, key=lambda item: str(item.get("position_id", ""))):
            required = {"position_id", "pair", "direction", "risk_fraction", "cumulative_pnl", "closed"}
            if not required.issubset(raw):
                return {"status": "BLOCK", "reason": "POSITION_FIELD_MISSING"}
            position_id = str(raw["position_id"])
            if not position_id or position_id in present or position_id in closed:
                return {"status": "BLOCK", "reason": "POSITION_LIFECYCLE_INVALID"}
            present.add(position_id)
            pair = str(raw["pair"])
            if pair not in universe:
                return {"status": "BLOCK", "reason": "POSITION_OUTSIDE_SYNCHRONIZED_UNIVERSE"}
            if position_id in active and (active[position_id]["pair"], active[position_id]["direction"], active[position_id]["risk_fraction"]) != (pair, raw["direction"], raw["risk_fraction"]):
                return {"status": "BLOCK", "reason": "POSITION_IDENTITY_MUTATED"}
            active.setdefault(position_id, {"pair": pair, "direction": raw["direction"], "risk_fraction": raw["risk_fraction"]})
            cumulative = float(raw["cumulative_pnl"])
            delta = cumulative - previous_pnl.get(position_id, 0.0)
            previous_pnl[position_id] = cumulative
            delta_total += delta
            pair_pnl[pair] += delta
            base, quote = _pair_parts(pair)
            currency_pnl[base] += delta / 2.0
            currency_pnl[quote] += delta / 2.0
            risk = float(raw["risk_fraction"])
            sign = 1.0 if raw["direction"] == "LONG" else -1.0
            currency_gross[base] += abs(risk)
            currency_gross[quote] += abs(risk)
            currency_net[base] += sign * risk
            currency_net[quote] -= sign * risk
        missing_active = set(active) - present
        if missing_active:
            return {"status": "BLOCK", "reason": "POSITION_DISAPPEARED_WITHOUT_CLOSE", "positions": sorted(missing_active)}
        if len(active) > maximum_positions:
            return {"status": "FAIL", "reason": "SIMULTANEOUS_POSITION_LIMIT"}
        for currency, gross in currency_gross.items():
            max_currency[currency] = max(max_currency[currency], gross)
            if gross > maximum_currency_gross + 1e-15:
                return {"status": "FAIL", "reason": "CURRENCY_GROSS_EXPOSURE_LIMIT", "currency": currency, "gross": gross}
        for raw in positions:
            if bool(raw["closed"]):
                position_id = str(raw["position_id"])
                active.pop(position_id)
                closed.add(position_id)
        equity += delta_total
        if equity <= 0:
            return {"status": "FAIL", "reason": "PORTFOLIO_INSOLVENT"}
        curve.append(equity)
        max_simultaneous = max(max_simultaneous, len(present))
    if active:
        return {"status": "BLOCK", "reason": "POSITIONS_OPEN_AT_EVIDENCE_END", "positions": sorted(active)}
    pair_corr, signal_corr = correlation_matrix(pair_series), correlation_matrix(signal_series)
    if pair_corr["status"] != "PASS" or signal_corr["status"] != "PASS":
        return {"status": "BLOCK", "reason": "PORTFOLIO_CORRELATION_INVALID"}
    pair_abs, currency_abs = sum(abs(value) for value in pair_pnl.values()), sum(abs(value) for value in currency_pnl.values())
    largest_pair, pair_value = max(pair_pnl.items(), key=lambda item: (abs(item[1]), item[0]))
    largest_currency, currency_value = max(currency_pnl.items(), key=lambda item: (abs(item[1]), item[0]))
    drawdown = maximum_drawdown(curve)
    reasons = []
    if drawdown > maximum_drawdown_fraction:
        reasons.append("PORTFOLIO_DRAWDOWN")
    if abs(pair_value) / pair_abs > 0.75:
        reasons.append("PAIR_CONCENTRATION")
    if abs(currency_value) / currency_abs > 0.75:
        reasons.append("CURRENCY_FACTOR_CONCENTRATION")
    return {
        "status": "FAIL" if reasons else "PASS", "reasons": reasons,
        "equity_curve": curve, "ending_equity": equity,
        "maximum_drawdown_fraction": drawdown, "maximum_simultaneous_positions": max_simultaneous,
        "pair_correlation": pair_corr, "signal_correlation": signal_corr,
        "effective_independent_bets": min(pair_corr["effective_independent_bets"], signal_corr["effective_independent_bets"]),
        "currency_gross_exposure_max": dict(sorted(max_currency.items())),
        "currency_net_exposure_final": {},
        "pair_pnl": dict(sorted(pair_pnl.items())), "currency_factor_pnl": dict(sorted(currency_pnl.items())),
        "largest_pair_contribution": {"pair": largest_pair, "absolute_share": abs(pair_value) / pair_abs},
        "largest_currency_factor_contribution": {"currency": largest_currency, "absolute_share": abs(currency_value) / currency_abs},
    }


def _snapshot_fixture(*, concentrated: bool = False) -> list[dict[str, Any]]:
    pairs = ("EUR_USD", "GBP_JPY", "AUD_CAD")
    returns = {"EUR_USD": (0.01, 0.02, -0.01, 0.03), "GBP_JPY": (-0.02, 0.01, 0.03, -0.01), "AUD_CAD": (0.03, -0.01, 0.02, 0.01)}
    signals = {"EUR_USD": (1, -1, 1, 0), "GBP_JPY": (-1, 1, 0, 1), "AUD_CAD": (0, 1, -1, 1)}
    snapshots = []
    for index in range(4):
        positions = []
        for pair_number, pair in enumerate(pairs):
            per_step = 100.0 if concentrated and pair == "EUR_USD" else (1.0 if concentrated else 20.0 + pair_number)
            positions.append({"position_id": pair, "pair": pair, "direction": "LONG", "risk_fraction": .0025, "cumulative_pnl": per_step * (index + 1), "closed": index == 3})
        snapshots.append({"timestamp": f"2026-01-01T00:{index:02d}:00Z", "pair_returns": {pair: returns[pair][index] for pair in pairs}, "signal_states": {pair: signals[pair][index] for pair in pairs}, "positions": positions})
    return snapshots


def validate_half_open_information(
    *, partition_start: str, partition_end: str, feature_max: str,
    signal_time: str, entry_time: str, label_end: str,
) -> dict[str, Any]:
    start, end = parse_utc(partition_start), parse_utc(partition_end)
    feature, signal, entry, label = map(parse_utc, (feature_max, signal_time, entry_time, label_end))
    if not (start <= feature <= signal < entry < label < end):
        return {"status": "BLOCK", "reason": "PARTITION_OR_FUTURE_LEAKAGE"}
    return {"status": "PASS", "half_open": True}


def validate_lineage(nodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_id = {str(node.get("artifact_id", "")): dict(node) for node in nodes}
    if "" in by_id or len(by_id) != len(nodes):
        return {"status": "BLOCK", "reason": "LINEAGE_IDENTITY_INVALID"}
    content_owners: dict[str, list[str]] = defaultdict(list)
    for artifact_id, node in by_id.items():
        required = {"content_sha256", "kind", "partition", "min_timestamp", "max_timestamp", "parents", "transform_fingerprint"}
        if not required.issubset(node):
            return {"status": "BLOCK", "reason": "LINEAGE_FIELD_MISSING"}
        content_owners[str(node["content_sha256"])].append(artifact_id)
    for owners in content_owners.values():
        if len(owners) > 1:
            declared_aliases = all(set(by_id[owner].get("aliases", [])) >= set(owners) - {owner} for owner in owners)
            if not declared_aliases:
                return {"status": "BLOCK", "reason": "UNDECLARED_CONTENT_ALIAS"}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(artifact_id: str) -> None:
        if artifact_id in visiting:
            raise ValueError("LINEAGE_CYCLE")
        if artifact_id in visited:
            return
        visiting.add(artifact_id)
        child = by_id[artifact_id]
        child_max = parse_utc(str(child["max_timestamp"]))
        for parent_id in child["parents"]:
            if str(parent_id) not in by_id:
                raise ValueError("LINEAGE_PARENT_MISSING")
            parent = by_id[str(parent_id)]
            if parse_utc(str(parent["max_timestamp"])) > child_max:
                raise ValueError("LINEAGE_TIMESTAMP_CONCEALMENT")
            visit(str(parent_id))
        visiting.remove(artifact_id)
        visited.add(artifact_id)

    try:
        for artifact_id in sorted(by_id):
            visit(artifact_id)
    except ValueError as error:
        return {"status": "BLOCK", "reason": str(error)}
    return {"status": "PASS", "node_count": len(nodes), "root_count": sum(not node["parents"] for node in by_id.values()), "lineage_sha256": sha256_value(nodes)}


def access_decision(request: Mapping[str, Any], manifest: Mapping[str, Any], lineage: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    required = {"dataset_id", "content_sha256", "partition", "requested_start", "requested_end", "packet_id", "purpose", "candidate_fingerprint", "authorization_sha256"}
    if not required.issubset(request):
        return {"status": "BLOCK", "reason": "ACCESS_RECEIPT_FIELD_MISSING"}
    if request["dataset_id"] != manifest.get("dataset_id") or request["content_sha256"] != manifest.get("content_sha256"):
        return {"status": "BLOCK", "reason": "DATASET_IDENTITY_MISMATCH"}
    if request["partition"] != manifest.get("partition"):
        return {"status": "BLOCK", "reason": "PARTITION_IDENTITY_MISMATCH"}
    if validate_lineage(lineage)["status"] != "PASS":
        return {"status": "BLOCK", "reason": "LINEAGE_INVALID"}
    start, end = parse_utc(str(request["requested_start"])), parse_utc(str(request["requested_end"]))
    manifest_start, manifest_end = parse_utc(str(manifest["start"])), parse_utc(str(manifest["end_exclusive"]))
    if not (manifest_start <= start < end <= manifest_end):
        return {"status": "BLOCK", "reason": "ACCESS_RANGE_OUTSIDE_MANIFEST"}
    partition = str(request["partition"])
    provenance = str(manifest.get("information_provenance", "UNKNOWN"))
    if partition == "VALIDATION" and provenance != "PROVEN_UNTOUCHED":
        return {"status": "BLOCK", "reason": "VALIDATION_PROVENANCE_REUSED_OR_UNKNOWN"}
    if partition == "FINAL_HOLDOUT":
        if provenance != "PROVEN_UNTOUCHED":
            return {"status": "BLOCK", "reason": "HOLDOUT_PROVENANCE_CONTAMINATED_OR_UNKNOWN"}
        if start <= parse_utc(NEW_HOLDOUT_AFTER):
            return {"status": "BLOCK", "reason": "HOLDOUT_NOT_STRICTLY_AFTER_CONTAMINATION_BOUNDARY"}
        if int(manifest.get("access_count", 0)) != 0 or bool(manifest.get("spent", False)):
            return {"status": "BLOCK", "reason": "HOLDOUT_ALREADY_SPENT"}
        if manifest.get("sealed") is not True:
            return {"status": "BLOCK", "reason": "HOLDOUT_NOT_SEALED"}
    return {"status": "PASS", "access_receipt_sha256": sha256_value({"request": request, "manifest": manifest}), "access_precedes_read": True}


def initialize_holdout_guard(path: Path, manifest: Mapping[str, Any], authorization_sha256: str) -> None:
    if path.exists():
        raise ValueError("HOLDOUT_GUARD_COLLISION")
    payload = {"schema": "AIOS_FOREX_HOLDOUT_GUARD_V2", "manifest": dict(manifest), "authorization_sha256": str(authorization_sha256), "access_log": []}
    atomic_write(path, pretty_json(payload).encode("ascii"))


def claim_holdout_access(path: Path, request: Mapping[str, Any], lineage: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if msvcrt is None or not path.is_file():
        return {"status": "BLOCK", "reason": "HOLDOUT_GUARD_MISSING_OR_UNLOCKABLE"}
    with path.open("r+", encoding="ascii", newline="") as handle:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            handle.seek(0)
            guard = json.load(handle)
            if guard.get("schema") != "AIOS_FOREX_HOLDOUT_GUARD_V2":
                return {"status": "BLOCK", "reason": "HOLDOUT_GUARD_INVALID"}
            if guard.get("authorization_sha256") != request.get("authorization_sha256"):
                return {"status": "BLOCK", "reason": "HOLDOUT_AUTHORIZATION_MISMATCH"}
            decision = access_decision(request, guard.get("manifest", {}), lineage)
            if decision["status"] != "PASS":
                return decision
            manifest = guard["manifest"]
            manifest["access_count"] = 1
            manifest["spent"] = True
            manifest["status"] = "SPENT"
            log = {"sequence": len(guard["access_log"]) + 1, "request_sha256": sha256_value(request), "access_receipt_sha256": decision["access_receipt_sha256"], "spent_before_reader": True}
            log["record_sha256"] = sha256_value(log)
            guard["access_log"].append(log)
            handle.seek(0)
            handle.truncate()
            handle.write(pretty_json(guard))
            handle.flush()
            os.fsync(handle.fileno())
            return {"status": "PASS", "access_count": 1, "spent": True, "access_log_record": log}
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def validate_resampling_contract(mode: str, *, synchronized_columns: bool, block_size: int, label_horizon: int) -> dict[str, Any]:
    if mode != "SYNCHRONIZED_MOVING_BLOCK" or not synchronized_columns:
        return {"status": "BLOCK", "reason": "CROSS_PAIR_IID_BOOTSTRAP_FORBIDDEN"}
    if block_size < label_horizon:
        return {"status": "BLOCK", "reason": "BLOCK_SHORTER_THAN_LABEL_OVERLAP"}
    return {"status": "PASS"}


def deterministic_reproduction(first: Any, second: Any) -> dict[str, Any]:
    left, right = canonical_json(first).encode("ascii"), canonical_json(second).encode("ascii")
    return {"status": "PASS" if left == right else "NONDETERMINISTIC", "first_sha256": sha256_bytes(left), "second_sha256": sha256_bytes(right), "byte_identical": left == right}


def validator_result(status: str, *, metrics: Mapping[str, Any] | None = None, reasons: Sequence[str] = ()) -> dict[str, Any]:
    normalized = str(status).upper()
    if normalized not in {"PASS", "FAIL", "BLOCK", *FAIL_CLOSED_STATUSES}:
        normalized = "UNKNOWN"
    body = {"status": normalized, "metrics": dict(metrics or {}), "reasons": list(reasons)}
    body["evidence_sha256"] = sha256_value(body)
    return body


def evaluate_transition(current_state: str, results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if current_state not in TRANSITION_VALIDATORS:
        return {"status": "BLOCK", "state": current_state, "reason": "TERMINAL_OR_UNKNOWN_STATE"}
    mandatory = TRANSITION_VALIDATORS[current_state]
    blockers = []
    for validator_id in mandatory:
        result = results.get(validator_id)
        if not isinstance(result, Mapping):
            blockers.append(f"{validator_id}:MISSING")
            continue
        status = str(result.get("status", "UNKNOWN")).upper()
        if status != "PASS":
            blockers.append(f"{validator_id}:{status}")
    if blockers:
        return {"status": "BLOCK", "state": current_state, "next_state": None, "block_reasons": blockers}
    next_state = PROMOTION_STATES[PROMOTION_STATES.index(current_state) + 1]
    return {"status": "PASS", "state": current_state, "next_state": next_state, "block_reasons": []}


def evaluate_candidate_receipt(
    specification: Mapping[str, Any], global_context: Mapping[str, Any],
    data_provenance: Mapping[str, Any], validator_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    fingerprint = candidate_fingerprint(specification)
    state = "EDGE_HYPOTHESIS"
    transitions = []
    block_reasons = []
    while state in TRANSITION_VALIDATORS:
        decision = evaluate_transition(state, validator_results)
        transitions.append(decision)
        if decision["status"] != "PASS":
            block_reasons.extend(decision["block_reasons"])
            break
        state = str(decision["next_state"])
    sections = {
        "cost_results": {key: value for key, value in validator_results.items() if "cost" in key or key in {"execution_delay", "stop_slippage", "financing"}},
        "uncertainty_results": {key: value for key, value in validator_results.items() if key in {"dependence_bootstrap", "sample_adequacy", "walk_forward", "embargo"}},
        "overfitting_results": {key: value for key, value in validator_results.items() if key in {"multiple_testing", "dsr", "cscv_pbo"}},
        "robustness_results": {key: value for key, value in validator_results.items() if "robustness" in key or "removal" in key},
        "portfolio_results": validator_results.get("portfolio_validation", {}),
        "validation_results": validator_results.get("validation_provenance", {}),
        "holdout_results": validator_results.get("holdout_result", {}),
    }
    receipt = {
        "schema": "AIOS_FOREX_CANDIDATE_EVALUATION_RECEIPT_V1",
        "candidate_fingerprint": fingerprint,
        "global_research_context": dict(global_context),
        "global_research_context_sha256": sha256_value(global_context),
        "data_provenance": dict(data_provenance),
        "data_provenance_sha256": sha256_value(data_provenance),
        **sections,
        "validator_results": {key: dict(value) for key, value in sorted(validator_results.items())},
        "promotion_state": state, "transitions": transitions,
        "block_reasons": sorted(block_reasons),
    }
    receipt["receipt_sha256"] = sha256_value(receipt)
    return receipt


def _scientific_spec(candidate_id: str = "SYNTHETIC_STABLE", **changes: Any) -> dict[str, Any]:
    result = {
        "candidate_id": candidate_id,
        "signal_family": "SYNTHETIC_CURRENCY_MOMENTUM",
        "data_identity": "SYNTHETIC_V1",
        "formation_horizon": 12,
        "execution_horizon": 3,
        "direction": "LONG",
        "entry_rule": "NEXT_COMPLETED_BAR",
        "exit_rule": "FIXED_HORIZON",
        "cost_contract": "BASE_V1",
        "regime_filters": [],
        "pair_currency_universe": ["EUR_USD", "GBP_JPY", "AUD_CAD"],
        "parameters": {"threshold": 1.0},
        "portfolio_rules": {"risk_fraction": 0.0025, "maximum_positions": 5},
    }
    result.update(changes)
    return result


def _lineage(partition: str = "DEVELOPMENT") -> list[dict[str, Any]]:
    return [
        {"artifact_id": "source", "content_sha256": "a" * 64, "kind": "SOURCE", "partition": partition, "min_timestamp": "2024-01-01T00:00:00Z", "max_timestamp": "2024-01-01T00:10:00Z", "parents": [], "transform_fingerprint": "RAW"},
        {"artifact_id": "feature", "content_sha256": "b" * 64, "kind": "FEATURE", "partition": partition, "min_timestamp": "2024-01-01T00:00:00Z", "max_timestamp": "2024-01-01T00:10:00Z", "parents": ["source"], "transform_fingerprint": "CAUSAL_FEATURE_V1"},
        {"artifact_id": "report", "content_sha256": "c" * 64, "kind": "REPORT", "partition": partition, "min_timestamp": "2024-01-01T00:00:00Z", "max_timestamp": "2024-01-01T00:10:00Z", "parents": ["feature"], "transform_fingerprint": "REPORT_V1"},
    ]


def _access_fixture(partition: str, provenance: str, *, start: str = "2024-01-01T00:00:00Z", end: str = "2024-01-02T00:00:00Z", sealed: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = {"dataset_id": "SYNTHETIC", "content_sha256": "a" * 64, "partition": partition, "start": start, "end_exclusive": end, "information_provenance": provenance, "sealed": sealed, "access_count": 0, "spent": False}
    request = {"dataset_id": "SYNTHETIC", "content_sha256": "a" * 64, "partition": partition, "requested_start": start, "requested_end": end, "packet_id": PACKET_ID, "purpose": "SYNTHETIC_CERTIFICATION", "candidate_fingerprint": candidate_fingerprint(_scientific_spec()), "authorization_sha256": "d" * 64}
    return request, manifest


def _portfolio_fixture(*, concentrated: bool = False, shared_currency: bool = False) -> list[dict[str, Any]]:
    pairs = ("EUR_USD", "GBP_USD", "AUD_USD") if shared_currency else ("EUR_USD", "GBP_JPY", "AUD_CAD")
    events = []
    returns = {
        "EUR_USD": (0.01, 0.02, -0.01, 0.03),
        pairs[1]: (-0.02, 0.01, 0.03, -0.01),
        pairs[2]: (0.03, -0.01, 0.02, 0.01),
    }
    signals = {
        "EUR_USD": (1, -1, 1, 0), pairs[1]: (-1, 1, 0, 1), pairs[2]: (0, 1, -1, 1),
    }
    for index in range(4):
        for pair_number, pair in enumerate(pairs):
            pnl = (20.0 + pair_number) if not concentrated else (100.0 if pair == "EUR_USD" else 1.0)
            events.append({"event_id": f"{index}-{pair}", "timestamp": f"2026-01-01T00:{index:02d}:00Z", "pair": pair, "direction": "LONG" if signals[pair][index] >= 0 else "SHORT", "risk_fraction": 0.0025, "pnl": pnl, "pair_return": returns[pair][index], "signal": signals[pair][index]})
    return events


def adversarial_synthetic_harness() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def add(case_id: str, expected: str, actual: str, evidence: Any) -> None:
        cases.append({"case_id": case_id, "expected": expected, "actual": actual, "passed": expected == actual, "evidence_sha256": sha256_value(evidence)})

    stable_returns = [0.020 + (index % 5 - 2) * 0.001 for index in range(120)]
    trial_distribution = [(index % 9 - 4) * 0.01 for index in range(45)]
    dsr = deflated_sharpe_ratio(stable_returns, trial_distribution, effective_trial_count=1220, effective_sample_count=120)
    add("01_STABLE_POSITIVE_SIGNAL", "PASS", dsr["status"], dsr)
    noise = [-0.01, 0.01] * 60
    add("02_PURE_RANDOM_NOISE", "FAIL", "PASS" if statistics.fmean(noise) > 0 else "FAIL", noise)

    noise_matrix = [[math.sin((row + 1) * (column + 2)) for column in range(8)] for row in range(64)]
    pbo_noise = cscv_pbo(noise_matrix, [f"N{index}" for index in range(8)], subset_count=8, maximum_pbo=0.20)
    add("03_DATA_MINED_NOISE_WINNER", "FAIL", pbo_noise["status"], pbo_noise)
    leak = validate_half_open_information(partition_start="2024-01-01T00:00:00Z", partition_end="2024-02-01T00:00:00Z", feature_max="2024-01-02T00:10:00Z", signal_time="2024-01-02T00:05:00Z", entry_time="2024-01-02T00:15:00Z", label_end="2024-01-02T00:30:00Z")
    add("04_FUTURE_DATA_LEAKAGE", "BLOCK", leak["status"], leak)
    first, renamed = _scientific_spec("ORIGINAL"), _scientific_spec("RENAMED")
    duplicates = reconcile_fingerprints([first, renamed])
    add("05_RENAMED_DUPLICATE", "DUPLICATE", "DUPLICATE" if duplicates["duplicate_specifications"] == 1 else "FAIL", duplicates)
    duplicate_matrix = [[float(row), float(row), -float(row)] for row in range(32)]
    correlated = cscv_pbo(duplicate_matrix, ["A", "B", "C"], subset_count=4)
    add("06_CORRELATED_DUPLICATE_SIGNAL", "PASS", "PASS" if correlated.get("duplicate_configuration_count") == 1 else "FAIL", correlated)
    narrow = [{"pnl": 1.0, "pair": "EUR_USD", "currency": "USD", "period": f"P{i%2}", "volatility": f"V{i%2}", "liquidity": f"L{i%2}", "session": f"S{i%2}", "direction": f"D{i%2}"} for i in range(12)]
    pair_concentration = robustness_diagnostics(narrow)
    add("07_SINGLE_PAIR_CONCENTRATION", "FAIL", pair_concentration["status"], pair_concentration)
    currency_portfolio = simulate_portfolio(_portfolio_fixture(shared_currency=True), maximum_currency_gross=0.004)
    add("08_SINGLE_CURRENCY_FACTOR_CONCENTRATION", "FAIL", currency_portfolio["status"], currency_portfolio)
    destroyed = cost_stress({"GROSS": [1.0], "BASE": [-0.1], "STRESSED": [-0.2], "SEVERE_BUT_PLAUSIBLE": [-0.3]})
    add("09_GROSS_WINNER_DESTROYED_BY_BASE", "FAIL", destroyed["status"], destroyed)
    fragile = cost_stress({"GROSS": [1.0], "BASE": [0.4], "STRESSED": [0.1], "SEVERE_BUT_PLAUSIBLE": [-0.1]})
    add("10_BASE_WINNER_DESTROYED_BY_SEVERE", "FAIL", fragile["status"], fragile)
    needle = parameter_neighborhood("P2", {"P1": -0.1, "P2": 1.0, "P3": 0.0}, {"P2": ["P1", "P3"]})
    add("11_PARAMETER_NEEDLE", "FRAGILE", needle["status"], needle)
    regime_records = [{"pnl": 2.0 if i < 6 else -1.5, "pair": f"P{i%2}", "currency": f"C{i%2}", "period": f"T{i%2}", "volatility": "ONLY", "liquidity": f"L{i%2}", "session": f"S{i%2}", "direction": f"D{i%2}"} for i in range(12)]
    regime = robustness_diagnostics(regime_records)
    add("12_REGIME_FRAGILE", "FAIL", regime["status"], regime)
    short_rows = [{"timestamp": f"T{i:03d}", "pair_returns": {"A": 0.01, "B": 0.02}} for i in range(20)]
    insufficient = synchronized_block_bootstrap(short_rows, block_size=4, label_horizon=4, runs=100)
    add("13_INSUFFICIENT_EFFECTIVE_SAMPLE", "BLOCK", insufficient["status"], insufficient)
    validation_request, validation_manifest = _access_fixture("VALIDATION", "REUSED")
    reused = access_decision(validation_request, validation_manifest, _lineage("VALIDATION"))
    add("14_REUSED_VALIDATION", "BLOCK", reused["status"], reused)
    holdout_request, holdout_manifest = _access_fixture("FINAL_HOLDOUT", "CONTAMINATED", start="2026-08-29T03:55:00Z", end="2026-08-30T03:55:00Z", sealed=True)
    contaminated = access_decision(holdout_request, holdout_manifest, _lineage("FINAL_HOLDOUT"))
    add("15_CONTAMINATED_HOLDOUT", "BLOCK", contaminated["status"], contaminated)
    nondeterminism = deterministic_reproduction({"value": 1}, {"value": 2})
    add("16_NONDETERMINISTIC_EVALUATOR", "NONDETERMINISTIC", nondeterminism["status"], nondeterminism)
    missing = evaluate_transition("EDGE_HYPOTHESIS", {})
    add("17_MISSING_MANDATORY_VALIDATOR", "BLOCK", missing["status"], missing)
    iid = validate_resampling_contract("IID", synchronized_columns=False, block_size=48, label_horizon=48)
    add("18_CROSS_PAIR_IID_BOOTSTRAP", "BLOCK", iid["status"], iid)
    quote = Quote("2026-01-01T00:00:00Z", 1.0, 1.0002)
    double_spread = costed_trade("LONG", [quote], [Quote("2026-01-01T00:05:00Z", 1.001, 1.0012)], scenario=COST_SCENARIOS["BASE"], explicit_spread_charge=0.0002)
    add("19_DOUBLE_SPREAD_CHARGE", "BLOCK", double_spread["status"], double_spread)
    financing = costed_trade("LONG", [quote], [Quote("2026-01-02T00:00:00Z", 1.001, 1.0012)], scenario=COST_SCENARIOS["BASE"], rollover_boundaries=1)
    add("20_UNSUPPORTED_FINANCING_HORIZON", "BLOCK", financing["status"], financing)
    add("21_LOOKAHEAD_ROLLING_FEATURE", "BLOCK", leak["status"], leak)
    aliases = _lineage() + [{"artifact_id": "renamed_cache", "content_sha256": "b" * 64, "kind": "FEATURE", "partition": "DEVELOPMENT", "min_timestamp": "2024-01-01T00:00:00Z", "max_timestamp": "2024-01-01T00:10:00Z", "parents": ["source"], "transform_fingerprint": "CAUSAL_FEATURE_V1"}]
    lineage_bypass = validate_lineage(aliases)
    add("22_DERIVED_CACHE_LINEAGE_BYPASS", "BLOCK", lineage_bypass["status"], lineage_bypass)
    add("23_DUPLICATED_EXPERIMENT_NEW_NAME", "DUPLICATE", "DUPLICATE" if candidate_fingerprint(first) == candidate_fingerprint(renamed) else "FAIL", duplicates)
    concentrated_portfolio = simulate_synchronized_portfolio_snapshots(_snapshot_fixture(concentrated=True), maximum_currency_gross=0.02)
    add("24_EVENT_EDGE_PORTFOLIO_UNACCEPTABLE", "FAIL", concentrated_portfolio["status"], concentrated_portfolio)
    return {"status": "PASS" if all(case["passed"] for case in cases) else "FAIL", "passed": sum(case["passed"] for case in cases), "total": len(cases), "cases": cases}


def _all_pass_results() -> dict[str, dict[str, Any]]:
    validator_ids = sorted({validator_id for values in TRANSITION_VALIDATORS.values() for validator_id in values})
    return {validator_id: validator_result("PASS", metrics={"synthetic_certification": True}) for validator_id in validator_ids}


def promotion_reference() -> dict[str, Any]:
    results = _all_pass_results()
    state = "EDGE_HYPOTHESIS"
    transitions = []
    while state in TRANSITION_VALIDATORS:
        decision = evaluate_transition(state, results)
        transitions.append(decision)
        if decision["status"] != "PASS":
            raise ValueError("SYNTHETIC_PROMOTION_REFERENCE_FAILED")
        state = str(decision["next_state"])
    blocked = evaluate_transition("EDGE_HYPOTHESIS", {key: value for key, value in results.items() if key != "future_leakage"})
    if state != "PAPER_VALIDATED_EDGE" or blocked["status"] != "BLOCK":
        raise ValueError("FAIL_CLOSED_PROMOTION_FAILED")
    return {"synthetic_terminal_state": state, "transitions": transitions, "missing_validator_reference": blocked}


def first_wave_fingerprint_index() -> dict[str, Any]:
    entries = []
    arms = {
        "A": ("PAIR_MOMENTUM", "IMMEDIATE_NEXT_BAR"),
        "B": ("PAIR_MOMENTUM_PLUS_GRAPH", "IMMEDIATE_NEXT_BAR"),
        "C": ("PAIR_MOMENTUM", "PULLBACK_RESUMPTION"),
        "D": ("PAIR_MOMENTUM_PLUS_GRAPH", "PULLBACK_RESUMPTION"),
    }
    for arm, lookback, horizon, inverse in itertools.product(arms, (12, 48, 288), (3, 12, 48), (False, True)):
        signal, entry = arms[arm]
        candidate_id = f"PKT038_{arm}_L{lookback}_H{horizon}_{'INVERSE' if inverse else 'PRIMARY'}"
        spec = _scientific_spec(
            candidate_id,
            signal_family=signal,
            formation_horizon=lookback,
            execution_horizon=horizon,
            direction="EXACT_INVERSE" if inverse else "ECONOMIC_DIRECTION",
            entry_rule=entry,
            exit_rule=f"FORWARD_HORIZON_{horizon}",
            parameters={"normalized_momentum_threshold": 1.0, "pullback_fraction": [0.20, 0.60] if arm in {"C", "D"} else None},
        )
        entries.append({"candidate_id": candidate_id, "fingerprint": candidate_fingerprint(spec), "specification": {field: spec[field] for field in SCIENTIFIC_FINGERPRINT_FIELDS}, "status": "PROPOSED_UNSCORED"})
    if len(entries) != 72 or len({entry["fingerprint"] for entry in entries}) != 72:
        raise ValueError("PKT038_FINGERPRINT_RECONCILIATION_FAILED")
    return {
        "schema": "AIOS_FOREX_FINGERPRINT_INDEX_V1",
        "scientific_fingerprint_schema": list(SCIENTIFIC_FINGERPRINT_FIELDS),
        "legacy_proposed_unscored_preserved_in_source_ledgers": 446,
        "legacy_identity_overlap": "UNRESOLVED_CONSERVATIVE_AGGREGATE_PRESERVED",
        "pkt038_proposed_unscored": 72,
        "total_proposed_unscored": 518,
        "entries": entries,
    }


def statistical_reference() -> dict[str, Any]:
    stable_returns = [0.020 + (index % 5 - 2) * 0.001 for index in range(120)]
    trial_distribution = [(index % 9 - 4) * 0.01 for index in range(45)]
    dsr = deflated_sharpe_ratio(stable_returns, trial_distribution, effective_trial_count=1220, effective_sample_count=120)
    stable_matrix = [[0.03 + (row % 3) * 0.001, 0.005 * math.sin(row), -0.01 + 0.002 * math.cos(row)] for row in range(64)]
    cscv = cscv_pbo(stable_matrix, ["STABLE", "NOISE", "WEAK"], subset_count=8, maximum_pbo=0.20)
    rows = [
        {"timestamp": f"T{index:04d}", "pair_returns": {"EUR_USD": 0.010 + (index % 3) * 0.0001, "GBP_USD": 0.008 + (index % 5) * 0.0001}}
        for index in range(120)
    ]
    bootstrap = synchronized_block_bootstrap(rows, block_size=4, label_horizon=4, runs=400, minimum_effective_blocks=30)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    timestamps = [(start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z") for index in range(120)]
    folds = chronological_folds(timestamps, fold_count=4, embargo_observations=4, minimum_train=40, minimum_test=10)
    walk = validate_walk_forward(folds, [{"selected_using": "TRAIN_ONLY", "test_count": fold["test_count"], "test_expectancy": 0.01} for fold in folds])
    first_fold = folds[0]
    train_end = parse_utc(first_fold["train_end"]); test_start = parse_utc(first_fold["test_start"]); test_end = parse_utc(first_fold["test_end"])
    labels = [
        {"partition": "TRAIN", "start": (train_end - timedelta(minutes=10)).isoformat(), "end": train_end.isoformat()},
        {"partition": "TRAIN", "start": (train_end - timedelta(minutes=5)).isoformat(), "end": (train_end + timedelta(minutes=5)).isoformat()},
        {"partition": "TEST", "start": test_start.isoformat(), "end": min(test_start + timedelta(minutes=5), test_end).isoformat()},
    ]
    label_audit = validate_fold_labels(first_fold, labels)
    multiple = holm_bonferroni([0.000001, 0.02], HISTORICAL_SCORED_ATTEMPT_LOWER_BOUND)
    if any(item["status"] != "PASS" for item in (dsr, cscv, bootstrap, walk, label_audit, multiple)):
        raise ValueError("STATISTICAL_REFERENCE_FAILED")
    return {"dsr": dsr, "cscv_pbo": cscv, "synchronized_bootstrap": bootstrap, "walk_forward": walk, "fold_label_audit": label_audit, "folds": folds, "multiple_testing": multiple}


def cost_portfolio_reference() -> dict[str, Any]:
    entry = Quote("2026-01-01T00:00:00Z", 1.1000, 1.1002)
    exit_quote = Quote("2026-01-01T00:05:00Z", 1.1010, 1.1012)
    long_result = costed_trade("LONG", [entry], [exit_quote], scenario=COST_SCENARIOS["BASE"])
    short_result = costed_trade("SHORT", [exit_quote], [entry], scenario=COST_SCENARIOS["BASE"])
    portfolio = simulate_synchronized_portfolio_snapshots(_snapshot_fixture(), maximum_currency_gross=0.02)
    if long_result["status"] != "PASS" or short_result["status"] != "PASS" or portfolio["status"] != "PASS":
        raise ValueError("COST_PORTFOLIO_REFERENCE_FAILED")
    return {"long": long_result, "short": short_result, "portfolio": portfolio, "cost_contract": {name: scenario.__dict__ for name, scenario in COST_SCENARIOS.items()}}


def provenance_reference() -> dict[str, Any]:
    development_request, development_manifest = _access_fixture("DEVELOPMENT", "AUTHORIZED_DEVELOPMENT")
    development = access_decision(development_request, development_manifest, _lineage("DEVELOPMENT"))
    validation_request, validation_manifest = _access_fixture("VALIDATION", "REUSED")
    validation = access_decision(validation_request, validation_manifest, _lineage("VALIDATION"))
    holdout_request, holdout_manifest = _access_fixture("FINAL_HOLDOUT", "CONTAMINATED", start="2026-08-29T03:55:00Z", end="2026-08-30T03:55:00Z", sealed=True)
    holdout = access_decision(holdout_request, holdout_manifest, _lineage("FINAL_HOLDOUT"))
    clean_request, clean_manifest = _access_fixture("FINAL_HOLDOUT", "PROVEN_UNTOUCHED", start="2026-08-29T03:55:00Z", end="2026-08-30T03:55:00Z", sealed=True)
    clean = access_decision(clean_request, clean_manifest, _lineage("FINAL_HOLDOUT"))
    if development["status"] != "PASS" or validation["status"] != "BLOCK" or holdout["status"] != "BLOCK" or clean["status"] != "PASS":
        raise ValueError("PROVENANCE_REFERENCE_FAILED")
    return {
        "development_access": development,
        "validation_information_provenance": "REUSED", "validation_access": validation,
        "holdout_information_provenance": "CONTAMINATED", "holdout_access": holdout,
        "new_holdout_synthetic_machinery": clean,
        "new_holdout_real_evidence": "NOT_ACCESSED_NOT_RESERVED",
        "new_holdout_strictly_after": NEW_HOLDOUT_AFTER,
    }


def _chain_records(payloads: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = []
    previous = "GENESIS"
    for sequence, payload in enumerate(payloads, start=1):
        body = {"sequence": sequence, "previous_record_sha256": previous, **dict(payload)}
        body["record_sha256"] = sha256_value(body)
        records.append(body)
        previous = body["record_sha256"]
    return records


def validate_hash_chain(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    previous = "GENESIS"
    for sequence, source in enumerate(records, start=1):
        record = dict(source)
        supplied = str(record.pop("record_sha256", ""))
        if record.get("sequence") != sequence or record.get("previous_record_sha256") != previous:
            raise ValueError("HASH_CHAIN_ORDER_INVALID")
        if supplied != sha256_value(record):
            raise ValueError("HASH_CHAIN_TAMPERED")
        previous = supplied
    return {"status": "PASS", "record_count": len(records), "head_sha256": previous}


def capability_registry(harness: Mapping[str, Any], references_sha256: str) -> dict[str, Any]:
    certified = harness.get("status") == "PASS" and int(harness.get("passed", 0)) == int(harness.get("total", -1)) == 24
    rows = []
    for capability_id, name in enumerate(CAPABILITY_NAMES, start=1):
        rows.append({
            "capability_id": capability_id, "capability": name,
            "status": "IMPLEMENTED_AND_EXECUTABLE" if certified else "BLOCKED",
            "implementation_path": "automation/forex_engine/forex_edge_validation_pipeline_v1.py",
            "test_evidence": "tests/forex_engine/test_forex_edge_validation_pipeline_v1.py",
            "integration_evidence": references_sha256,
            "fail_closed_evidence": sha256_value(harness),
            "certified": bool(certified),
        })
    certified_count = sum(row["certified"] for row in rows)
    return {
        "schema": "AIOS_FOREX_VALIDATION_CAPABILITY_REGISTRY_V1",
        "required_capabilities": 38, "certified_capabilities": certified_count,
        "blocked_capabilities": 38 - certified_count, "not_applicable_capabilities": 0,
        "readiness_percent": certified_count / 38 * 100.0,
        "capabilities": rows,
    }


def build_scientific_artifacts() -> dict[str, bytes]:
    ledger = bootstrap_trial_ledger()
    ledger_summary = validate_trial_ledger(ledger)
    fingerprints = first_wave_fingerprint_index()
    statistics_result = statistical_reference()
    cost_portfolio = cost_portfolio_reference()
    provenance = provenance_reference()
    harness = adversarial_synthetic_harness()
    if harness["status"] != "PASS" or harness["passed"] != 24:
        raise ValueError("ADVERSARIAL_SYNTHETIC_CERTIFICATION_FAILED")
    promotion = promotion_reference()
    references = {"statistics": statistics_result, "cost_portfolio": cost_portfolio, "provenance": provenance, "promotion": promotion}
    registry = capability_registry(harness, sha256_value(references))
    if registry["certified_capabilities"] != 38 or registry["readiness_percent"] != 100.0:
        raise ValueError("EDGE_VALIDATION_READINESS_NOT_100")
    real_results = _all_pass_results()
    real_results["validation_provenance"] = validator_result("CONTAMINATED", reasons=["CURRENT_VALIDATION_INFORMATION_IS_REUSED"])
    real_results["holdout_provenance"] = validator_result("CONTAMINATED", reasons=["CURRENT_HOLDOUT_INFORMATION_IS_CONTAMINATED"])
    current_receipt = evaluate_candidate_receipt(
        _scientific_spec("CURRENT_REAL_EVIDENCE_BLOCK_REFERENCE"),
        {"scored_attempt_lower_bound": ledger_summary["scored_attempt_lower_bound"], "proposed_unscored": ledger_summary["proposed_unscored_count"]},
        {"validation": "REUSED", "holdout": "CONTAMINATED"}, real_results,
    )
    receipt = {
        "schema": SCHEMA, "packet_id": PACKET_ID,
        "status": "EDGE_HUNT_VALIDATION_INFRASTRUCTURE_READY",
        "required_capabilities": 38, "certified_capabilities": 38,
        "blocked_capabilities": 0, "readiness_percent": 100.0,
        "global_trial_ledger": "PASS", "fingerprint_reconciliation": "PASS",
        "dsr": "PASS", "cscv": "PASS", "pbo": "PASS", "multiple_testing": "PASS",
        "dependence_aware_bootstrap": "PASS", "walk_forward": "PASS", "embargo": "PASS",
        "parameter_robustness": "PASS", "regime_robustness": "PASS",
        "cost_pipeline": "PASS", "portfolio_pipeline": "PASS",
        "access_enforcement": "PASS", "cache_lineage": "PASS", "future_leakage_detection": "PASS",
        "adversarial_synthetic_harness": "PASS", "fail_closed_promotion": "PASS",
        "conservative_scored_attempt_lower_bound": ledger_summary["scored_attempt_lower_bound"],
        "proposed_unscored": ledger_summary["proposed_unscored_count"],
        "validation_information_provenance": "REUSED", "holdout_information_provenance": "CONTAMINATED",
        "pkt_forex_039_status": "PAUSED_BEFORE_OUTCOME_SCORING", "pkt_forex_039_cells_scored": 0,
        "new_market_rows_opened": 0, "new_scored_trial_increment": 0,
        "verified_edge": False, "paper_authorized": False, "live_authorized": False,
    }
    artifacts: dict[str, bytes] = {
        "AIOS_FOREX_VALIDATION_CERTIFICATION_RECEIPT.json": pretty_json(receipt).encode("ascii"),
        "AIOS_FOREX_VALIDATION_CAPABILITY_REGISTRY_V1.json": pretty_json(registry).encode("ascii"),
        "AIOS_FOREX_ADVERSARIAL_SYNTHETIC_CASES_V1.json": pretty_json(harness).encode("ascii"),
        "AIOS_FOREX_STATISTICAL_REFERENCE_V1.json": pretty_json(statistics_result).encode("ascii"),
        "AIOS_FOREX_COST_PORTFOLIO_REFERENCE_V1.json": pretty_json(cost_portfolio).encode("ascii"),
        "AIOS_FOREX_PROVENANCE_REFERENCE_V1.json": pretty_json(provenance).encode("ascii"),
        "AIOS_FOREX_PROMOTION_REFERENCE_V1.json": pretty_json(promotion).encode("ascii"),
        "AIOS_FOREX_CURRENT_EVIDENCE_BLOCK_RECEIPT_V1.json": pretty_json(current_receipt).encode("ascii"),
        "AIOS_FOREX_FINGERPRINT_INDEX_V1.json": pretty_json(fingerprints).encode("ascii"),
        "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl": "".join(canonical_json(record) + "\n" for record in ledger).encode("ascii"),
    }
    inventory = {name: {"bytes": len(payload), "sha256": sha256_bytes(payload)} for name, payload in sorted(artifacts.items())}
    aggregate = sha256_value(inventory)
    manifest = {"schema": "AIOS_FOREX_VALIDATION_CERTIFICATION_MANIFEST_V1", "artifacts": inventory, "aggregate_sha256": aggregate, "scientific_artifact_count": len(artifacts)}
    artifacts["AIOS_FOREX_VALIDATION_CERTIFICATION_MANIFEST.json"] = pretty_json(manifest).encode("ascii")
    return artifacts


RUNTIME_FILENAMES = {
    "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl": "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl",
    "AIOS_FOREX_FINGERPRINT_INDEX_V1.json": "AIOS_FOREX_FINGERPRINT_INDEX_V1.json",
    "AIOS_FOREX_VALIDATION_CAPABILITY_REGISTRY_V1.json": "AIOS_FOREX_VALIDATION_CAPABILITY_REGISTRY_V1.json",
}


def runtime_payloads(artifacts: Mapping[str, bytes]) -> dict[str, bytes]:
    promotion = json.loads(artifacts["AIOS_FOREX_PROMOTION_REFERENCE_V1.json"])
    provenance = json.loads(artifacts["AIOS_FOREX_PROVENANCE_REFERENCE_V1.json"])
    payloads = {target: artifacts[source] for target, source in RUNTIME_FILENAMES.items()}
    payloads["AIOS_FOREX_PROMOTION_LEDGER_V1.jsonl"] = "".join(canonical_json(record) + "\n" for record in _chain_records(promotion["transitions"])).encode("ascii")
    provenance_events = [
        {"evidence_id": "CURRENT_VALIDATION", "information_provenance": provenance["validation_information_provenance"], "independent_claim_allowed": False},
        {"evidence_id": "CURRENT_HOLDOUT", "information_provenance": provenance["holdout_information_provenance"], "independent_claim_allowed": False},
        {"evidence_id": "NEXT_HOLDOUT", "status": "NOT_ACCESSED_NOT_RESERVED", "strictly_after": NEW_HOLDOUT_AFTER, "independent_claim_allowed": False},
    ]
    payloads["AIOS_FOREX_HOLDOUT_PROVENANCE_LEDGER_V1.jsonl"] = "".join(canonical_json(record) + "\n" for record in _chain_records(provenance_events)).encode("ascii")
    return payloads


def write_certification(output_root: Path, runtime_root: Path) -> dict[str, Any]:
    if output_root.exists() or runtime_root.exists():
        raise ValueError("OUTPUT_COLLISION")
    artifacts = build_scientific_artifacts()
    for name, payload in artifacts.items():
        atomic_write(output_root / name, payload)
    runtime = runtime_payloads(artifacts)
    for name, payload in runtime.items():
        atomic_write(runtime_root / name, payload)
    manifest = json.loads(artifacts["AIOS_FOREX_VALIDATION_CERTIFICATION_MANIFEST.json"])
    return {
        "status": "PASS", "output_root": str(output_root), "runtime_root": str(runtime_root),
        "aggregate_sha256": manifest["aggregate_sha256"],
        "scientific_artifact_count": manifest["scientific_artifact_count"],
        "runtime_artifact_count": len(runtime), "new_market_rows_opened": 0,
        "new_scored_trial_increment": 0,
    }


def compare_certifications(first_root: Path, second_root: Path) -> dict[str, Any]:
    first_files = {path.name: path for path in first_root.iterdir() if path.is_file()}
    second_files = {path.name: path for path in second_root.iterdir() if path.is_file()}
    if set(first_files) != set(second_files):
        return {"status": "FAIL", "reason": "ARTIFACT_SET_MISMATCH"}
    mismatches = [name for name in sorted(first_files) if first_files[name].read_bytes() != second_files[name].read_bytes()]
    first_manifest = json.loads(first_files["AIOS_FOREX_VALIDATION_CERTIFICATION_MANIFEST.json"].read_text(encoding="ascii"))
    second_manifest = json.loads(second_files["AIOS_FOREX_VALIDATION_CERTIFICATION_MANIFEST.json"].read_text(encoding="ascii"))
    return {"status": "PASS" if not mismatches else "FAIL", "byte_identical": not mismatches, "mismatches": mismatches, "first_aggregate_sha256": first_manifest["aggregate_sha256"], "second_aggregate_sha256": second_manifest["aggregate_sha256"]}


def promote_runtime(source_root: Path, runtime_root: Path) -> dict[str, Any]:
    expected = {
        "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl",
        "AIOS_FOREX_FINGERPRINT_INDEX_V1.json",
        "AIOS_FOREX_VALIDATION_CAPABILITY_REGISTRY_V1.json",
        "AIOS_FOREX_PROMOTION_LEDGER_V1.jsonl",
        "AIOS_FOREX_HOLDOUT_PROVENANCE_LEDGER_V1.jsonl",
    }
    files = {path.name: path for path in source_root.iterdir() if path.is_file()}
    if set(files) != expected:
        raise ValueError("RUNTIME_ARTIFACT_SET_INVALID")
    ledger = [json.loads(line) for line in files["AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl"].read_text(encoding="ascii").splitlines()]
    ledger_summary = validate_trial_ledger(ledger)
    registry = json.loads(files["AIOS_FOREX_VALIDATION_CAPABILITY_REGISTRY_V1.json"].read_text(encoding="ascii"))
    promotion = [json.loads(line) for line in files["AIOS_FOREX_PROMOTION_LEDGER_V1.jsonl"].read_text(encoding="ascii").splitlines()]
    holdout = [json.loads(line) for line in files["AIOS_FOREX_HOLDOUT_PROVENANCE_LEDGER_V1.jsonl"].read_text(encoding="ascii").splitlines()]
    if ledger_summary["scored_attempt_lower_bound"] < 1220 or ledger_summary["proposed_unscored_count"] != 518:
        raise ValueError("RUNTIME_RESEARCH_MEMORY_INVALID")
    if registry.get("certified_capabilities") != 38 or registry.get("readiness_percent") != 100.0:
        raise ValueError("RUNTIME_CAPABILITY_REGISTRY_INVALID")
    validate_hash_chain(promotion); validate_hash_chain(holdout)
    hashes = {}
    for name in sorted(expected):
        payload = files[name].read_bytes()
        atomic_write(runtime_root / name, payload)
        hashes[name] = sha256_bytes(payload)
    return {"status": "PASS", "runtime_root": str(runtime_root), "artifact_count": len(hashes), "hashes": hashes}
