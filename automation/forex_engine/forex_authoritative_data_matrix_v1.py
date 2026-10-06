"""Metadata-only authoritative Forex pair-by-granularity matrix for PKT-FOREX-027."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-FOREX-027"
SCHEMA = "AIOS_FOREX_AUTHORITATIVE_PAIR_TIMEFRAME_MATRIX.v1"
GRANULARITIES = ("TICK", "S1", "S5", "S10", "S15", "S30", "M1", "M2", "M4", "M5", "M10", "M15", "M30", "H1")
HIGH_FREQUENCY = frozenset(("S5", "S10", "S15", "S30", "M1", "M2", "M4"))
DERIVED_M5 = frozenset(("M10", "M15", "M30"))

INPUTS = {
    "high_frequency_validation": (
        ".aios/runtime/forex_historical_dataset_freezes_v1/pending/AIOS_FOREX_HISTORICAL_DATASET_VALIDATION_RECEIPT.json",
        "78d3236d37c1585e6b946ca05b250a3bfae72c163b6e0e9b4bdcef2bc9c541b6",
    ),
    "high_frequency_contract": (
        ".aios/runtime/forex_frozen_21_series_edge_research_v1/AIOS_FOREX_PHASE1_RESEARCH_CONTRACT.json",
        "ebf61ce23360076ab9e86b83b32ee62dae63fa51cfc91f25b31976e2321fd3a7",
    ),
    "m5_manifest": (
        ".aios/runtime/forex_m5_immutable_corpus_v2/manifest.json",
        "1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b",
    ),
    "m5_frozen": (
        ".aios/runtime/forex_m5_immutable_corpus_v2/FROZEN.json",
        "961031d7e5f16586d49a5168d33530e08e97240213bc2a93ee66ea32ce93adb7",
    ),
    "m5_holdout_contract": (
        ".aios/runtime/forex_cross_sectional_short_horizon_reversal_v1/AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CONTRACT.json",
        "3ead0ab467f18687e7e013518c305cf1b8a5c8a6cffd27fc53954a47794481dd",
    ),
    "h1_manifest": (
        ".aios/runtime/forex_multi_regime_corpus_v3/manifests/manifest.json",
        "f784867978464aee59f4b3377eca013237378fd8c3a61c068f8c111ce6451d32",
    ),
    "pair_coverage": (
        "Reports/forex_delivery/AIOS_FOREX_PAIR_COVERAGE_MATRIX_V3.json",
        "5e96a1a4867eedf37c3d0b0d9ab2fa36b96b55aba48af93500a75b8bd3683328",
    ),
}


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


def _load_inputs(repo_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    loaded: dict[str, Any] = {}
    inventory: list[dict[str, Any]] = []
    for name, (relative, expected) in sorted(INPUTS.items()):
        path = repo_root / relative
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"INPUT_HASH_MISMATCH:{name}:{actual}")
        loaded[name] = json.loads(path.read_text(encoding="utf-8"))
        inventory.append({"name": name, "path": relative, "sha256": actual})
    return loaded, inventory


def _set_hash(items: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_bytes(items))


def _empty_row(pair: str, granularity: str) -> dict[str, Any]:
    base, quote = pair.split("_")
    return {
        "pair": pair,
        "base_currency": base,
        "quote_currency": quote,
        "granularity": granularity,
        "availability": "ABSENT",
        "native_or_derived": "ABSENT",
        "source": None,
        "source_path": None,
        "source_sha256": None,
        "dataset_id": None,
        "dataset_sha256": None,
        "pair_artifact_set_sha256": None,
        "start_timestamp": None,
        "end_timestamp": None,
        "timestamp_semantics": None,
        "record_count": 0,
        "partition_count": 0,
        "bid_available": False,
        "ask_available": False,
        "mid_available": False,
        "historical_spread_available": False,
        "completed_candles_enforced": False,
        "missing_intervals": None,
        "duplicate_intervals": None,
        "out_of_order_records": None,
        "certification_status": "ABSENT",
        "development_eligibility": False,
        "walk_forward_eligibility": False,
        "final_holdout_exclusion_boundary": None,
        "final_holdout_status": "NOT_APPLICABLE",
        "exact_exclusion_reason": None,
    }


def build_matrix(repo_root: Path) -> dict[str, Any]:
    data, input_inventory = _load_inputs(repo_root)
    receipt = data["high_frequency_validation"]
    hf_contract = data["high_frequency_contract"]
    m5 = data["m5_manifest"]
    m5_frozen = data["m5_frozen"]
    m5_contract = data["m5_holdout_contract"]
    h1 = data["h1_manifest"]
    coverage = data["pair_coverage"]

    if receipt.get("status") != "PASS" or receipt.get("series_complete") != 21:
        raise ValueError("HIGH_FREQUENCY_RECEIPT_NOT_CERTIFIED")
    if m5.get("status") != "FROZEN_VALID" or m5_frozen.get("status") != "FROZEN_VALID":
        raise ValueError("M5_CORPUS_NOT_FROZEN_VALID")
    if h1.get("status") != "FROZEN_VALID" or coverage.get("status") != "COMPLETE":
        raise ValueError("H1_OR_PAIR_COVERAGE_NOT_VALID")

    pairs = sorted(row["instrument"] for row in coverage["rows"])
    if len(pairs) != 68 or len(set(pairs)) != 68:
        raise ValueError("INTENDED_PAIR_UNIVERSE_NOT_EXACTLY_68")

    hf_series = {(row["instrument"], row["granularity"]): row for row in receipt["series_inventory"]}
    hf_files: dict[tuple[str, str], list[dict[str, str]]] = {}
    for item in receipt["file_inventory"]:
        key = (item.get("instrument"), item.get("granularity"))
        if item.get("role") == "batch" and key in hf_series:
            hf_files.setdefault(key, []).append({"path": item["relative_path"], "sha256": item["sha256"]})
    hf_gaps: dict[tuple[str, str], int] = {}
    for item in receipt["legitimate_closure_gaps"]:
        key = (item["instrument"], item["granularity"])
        hf_gaps[key] = hf_gaps.get(key, 0) + int(item["missing_steps"])

    m5_artifacts: dict[str, list[dict[str, Any]]] = {pair: [] for pair in pairs}
    for item in m5["artifacts"]:
        m5_artifacts[item["instrument"]].append(item)
    m5_eligible = set(m5["eligible_pairs"])
    h1_artifacts = {item["instrument"]: item for item in h1["sanitized_artifacts"]}
    coverage_rows = {item["instrument"]: item for item in coverage["rows"]}
    hf_holdout = hf_contract["splits"]["sealed_final_holdout"][0]
    m5_holdout = m5_contract["holdout_begins"]

    rows: list[dict[str, Any]] = []
    for pair in pairs:
        for granularity in GRANULARITIES:
            row = _empty_row(pair, granularity)
            if granularity in {"TICK", "S1"}:
                row["exact_exclusion_reason"] = f"NO_CERTIFIED_{granularity}_DATASET_FOUND_IN_AUTHORITATIVE_METADATA_SOURCE_SET"
            elif granularity in HIGH_FREQUENCY:
                series = hf_series.get((pair, granularity))
                if series is None:
                    row["exact_exclusion_reason"] = "CERTIFIED_HIGH_FREQUENCY_SCOPE_LIMITED_TO_EUR_USD_GBP_USD_USD_JPY"
                else:
                    artifacts = sorted(hf_files[(pair, granularity)], key=lambda item: item["path"])
                    row.update({
                        "availability": "NATIVE_CERTIFIED",
                        "native_or_derived": "NATIVE",
                        "source": "CERTIFIED_21_SERIES_HIGH_FREQUENCY_CORPUS",
                        "source_path": INPUTS["high_frequency_validation"][0],
                        "source_sha256": INPUTS["high_frequency_validation"][1],
                        "dataset_id": hf_contract["dataset_id"],
                        "dataset_sha256": hf_contract["dataset_sha256"],
                        "pair_artifact_set_sha256": _set_hash(artifacts),
                        "start_timestamp": series["first_candle_utc"],
                        "end_timestamp": series["last_candle_utc"],
                        "timestamp_semantics": "EXACT_FIRST_AND_LAST_COMPLETED_CANDLE",
                        "record_count": int(series["candle_count"]),
                        "partition_count": int(series["batch_count"]),
                        "bid_available": True,
                        "ask_available": True,
                        "mid_available": False,
                        "historical_spread_available": True,
                        "completed_candles_enforced": True,
                        "missing_intervals": {"legitimate_closure_missing_steps": hf_gaps.get((pair, granularity), 0), "unexplained": 0},
                        "duplicate_intervals": 0,
                        "out_of_order_records": 0,
                        "certification_status": "FROZEN_CERTIFIED",
                        "development_eligibility": True,
                        "walk_forward_eligibility": True,
                        "final_holdout_exclusion_boundary": hf_holdout,
                        "final_holdout_status": "SEALED_NOT_OPENED_BY_MATRIX",
                        "exact_exclusion_reason": None,
                    })
            elif granularity == "M5" or granularity in DERIVED_M5:
                artifacts = sorted(m5_artifacts[pair], key=lambda item: item["path"])
                eligible = pair in m5_eligible
                coverage_value = float(m5["quality_reconciliation"]["coverage"][pair])
                gap_count = int(m5["quality_reconciliation"]["classified_provider_gaps"][pair])
                pair_hash = _set_hash([{"path": item["path"], "sha256": item["sha256"]} for item in artifacts])
                if granularity == "M5":
                    row.update({
                        "availability": "NATIVE_CERTIFIED" if eligible else "NATIVE_RAW_PRESENT_INELIGIBLE",
                        "native_or_derived": "NATIVE",
                        "source": "AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2",
                        "source_path": INPUTS["m5_manifest"][0],
                        "source_sha256": INPUTS["m5_manifest"][1],
                        "dataset_id": m5["corpus_id"],
                        "dataset_sha256": m5["aggregate_corpus_fingerprint"],
                        "pair_artifact_set_sha256": pair_hash,
                        "start_timestamp": min(item["start_utc"] for item in artifacts),
                        "end_timestamp": max(item["end_utc"] for item in artifacts),
                        "timestamp_semantics": "PARTITION_REQUEST_BOUNDARIES_FROM_METADATA_NOT_PRICE_ROWS",
                        "record_count": sum(int(item["records"]) for item in artifacts),
                        "partition_count": len(artifacts),
                        "bid_available": True,
                        "ask_available": True,
                        "mid_available": True,
                        "historical_spread_available": True,
                        "completed_candles_enforced": True,
                        "missing_intervals": {"classified_provider_gaps": gap_count, "unclassified_critical_gaps": 0},
                        "duplicate_intervals": sum(int(item["quality"]["duplicate_timestamps"]) for item in artifacts),
                        "out_of_order_records": sum(0 if item["quality"]["chronological"] else 1 for item in artifacts),
                        "certification_status": "FROZEN_CERTIFIED" if eligible else "RAW_PRESENT_FAILED_99_PERCENT_OPEN_MARKET_COVERAGE_GATE",
                        "development_eligibility": eligible,
                        "walk_forward_eligibility": eligible,
                        "final_holdout_exclusion_boundary": m5_holdout,
                        "final_holdout_status": "SEALED_NOT_OPENED_BY_MATRIX" if eligible else "INELIGIBLE",
                        "exact_exclusion_reason": None if eligible else f"M5_OPEN_MARKET_COVERAGE_{coverage_value:.12f}_BELOW_0.99_WITH_{gap_count}_CLASSIFIED_PROVIDER_GAPS",
                    })
                else:
                    row.update({
                        "availability": "DERIVABLE_ON_DEMAND" if eligible else "DERIVABLE_FROM_RAW_BUT_BASE_INELIGIBLE",
                        "native_or_derived": "DERIVED",
                        "source": "CAUSAL_CLOSED_M5_RESAMPLING_CAPABILITY",
                        "source_path": INPUTS["m5_manifest"][0],
                        "source_sha256": INPUTS["m5_manifest"][1],
                        "dataset_id": m5["corpus_id"],
                        "dataset_sha256": m5["aggregate_corpus_fingerprint"],
                        "pair_artifact_set_sha256": pair_hash,
                        "start_timestamp": min(item["start_utc"] for item in artifacts),
                        "end_timestamp": max(item["end_utc"] for item in artifacts),
                        "timestamp_semantics": "SOURCE_M5_PARTITION_BOUNDARIES_DERIVED_ROWS_NOT_MATERIALIZED",
                        "record_count": None,
                        "partition_count": len(artifacts),
                        "bid_available": True,
                        "ask_available": True,
                        "mid_available": True,
                        "historical_spread_available": True,
                        "completed_candles_enforced": True,
                        "missing_intervals": {"source_m5_classified_provider_gaps": gap_count, "derived_count_not_materialized": True},
                        "duplicate_intervals": 0,
                        "out_of_order_records": 0,
                        "certification_status": "ELIGIBLE_IF_CAUSAL_COMPLETED_M5_RESAMPLER_VALIDATES" if eligible else "BASE_M5_INELIGIBLE",
                        "development_eligibility": eligible,
                        "walk_forward_eligibility": eligible,
                        "final_holdout_exclusion_boundary": m5_holdout,
                        "final_holdout_status": "SEALED_NOT_OPENED_BY_MATRIX" if eligible else "INELIGIBLE",
                        "exact_exclusion_reason": None if eligible else "SOURCE_M5_PAIR_FAILED_RESEARCH_ELIGIBILITY",
                    })
            elif granularity == "H1":
                artifact = h1_artifacts.get(pair)
                pair_state = coverage_rows[pair]
                if artifact is None:
                    row["source"] = "AIOS_FOREX_MULTI_REGIME_CORPUS_V3"
                    row["source_path"] = INPUTS["h1_manifest"][0]
                    row["source_sha256"] = INPUTS["h1_manifest"][1]
                    row["dataset_id"] = h1["corpus_id"]
                    row["dataset_sha256"] = h1["aggregate_hash"]
                    row["certification_status"] = "ABSENT_FROM_FROZEN_H1_CORPUS"
                    row["exact_exclusion_reason"] = pair_state["exclusion_reason"]
                else:
                    row.update({
                        "availability": "NATIVE_CERTIFIED",
                        "native_or_derived": "NATIVE",
                        "source": "AIOS_FOREX_MULTI_REGIME_CORPUS_V3",
                        "source_path": INPUTS["h1_manifest"][0],
                        "source_sha256": INPUTS["h1_manifest"][1],
                        "dataset_id": h1["corpus_id"],
                        "dataset_sha256": h1["aggregate_hash"],
                        "pair_artifact_set_sha256": artifact["sha256"],
                        "start_timestamp": artifact["first_time"],
                        "end_timestamp": artifact["last_time"],
                        "timestamp_semantics": "EXACT_FIRST_AND_LAST_COMPLETED_CANDLE",
                        "record_count": int(artifact["candle_count"]),
                        "partition_count": 1,
                        "bid_available": bool(pair_state["bid_ask_available"]),
                        "ask_available": bool(pair_state["bid_ask_available"]),
                        "mid_available": bool(pair_state["mid_available"]),
                        "historical_spread_available": bool(pair_state["bid_ask_available"]),
                        "completed_candles_enforced": int(artifact["complete_count"]) == int(artifact["candle_count"]),
                        "missing_intervals": {"coverage_matrix_missing_interval_count": int(pair_state["missing_interval_count"])},
                        "duplicate_intervals": int(pair_state["duplicate_count"]),
                        "out_of_order_records": 0,
                        "certification_status": "FROZEN_CERTIFIED_WITH_M5_OVERLAP_PASS",
                        "development_eligibility": True,
                        "walk_forward_eligibility": True,
                        "final_holdout_exclusion_boundary": m5_holdout,
                        "final_holdout_status": "SEALED_NOT_OPENED_BY_MATRIX",
                        "exact_exclusion_reason": None,
                    })
            rows.append(row)

    rows.sort(key=lambda item: (item["pair"], GRANULARITIES.index(item["granularity"])))
    if len(rows) != 952 or len({(row["pair"], row["granularity"]) for row in rows}) != 952:
        raise ValueError("PAIR_GRANULARITY_MATRIX_CARDINALITY_FAILURE")

    matrix = {
        "schema": SCHEMA,
        "packet_id": PACKET_ID,
        "status": "PASS_METADATA_ONLY_AUTHORITATIVE_MATRIX",
        "input_inventory": input_inventory,
        "input_manifest_sha256": _set_hash(input_inventory),
        "intended_pair_count": 68,
        "granularity_count": len(GRANULARITIES),
        "row_count": len(rows),
        "seconds_data_available": True,
        "tick_data_available": False,
        "native_scope_summary": {
            "high_frequency": {"pairs": 3, "series": 21, "records": int(receipt["total_candle_count"]), "granularities": sorted(HIGH_FREQUENCY)},
            "m5": {"raw_pairs": len(m5_artifacts), "eligible_pairs": len(m5_eligible), "partitions": len(m5["artifacts"]), "records": int(m5["total_records"])},
            "h1": {"eligible_pairs": len(h1_artifacts), "records": sum(int(item["candle_count"]) for item in h1_artifacts.values())},
            "derived_not_native": sorted(DERIVED_M5),
            "absent": ["TICK", "S1"],
        },
        "holdout_scopes": {
            "certified_21_series": {"boundary": hf_holdout, "status": "SEALED_NOT_OPENED_BY_MATRIX"},
            "m5_and_h1": {"boundary": m5_holdout, "status": "SEALED_NOT_OPENED_BY_MATRIX"},
        },
        "stale_conflicts": [
            {"path": "Reports/forex_delivery/AIOS_FOREX_MTF_TIMEFRAME_COVERAGE_V1_STATE.json", "disposition": "SUPERSEDED_BY_LATER_21_SERIES_PASS_RECEIPT"},
            {"path": "Reports/forex_delivery/AIOS_FOREX_SCALPING_TIMEFRAME_COVERAGE_V1_STATE.json", "disposition": "SUPERSEDED_BY_LATER_21_SERIES_PASS_RECEIPT"},
            {"path": "Reports/forex_delivery/AIOS_FOREX_SCALPING_TIMEFRAME_CORPUS_V1_STATE.json", "disposition": "SUPERSEDED_BY_LATER_21_SERIES_PASS_RECEIPT"},
        ],
        "safety": {
            "metadata_files_opened": len(input_inventory),
            "market_rows_opened": 0,
            "validation_rows_opened": 0,
            "final_holdout_rows_opened": 0,
            "strategy_trials_added": 0,
            "broker_access": False,
            "credentials_accessed": False,
            "orders": False,
        },
        "rows": rows,
    }
    return matrix


def summary_for(matrix: dict[str, Any]) -> dict[str, Any]:
    rows = matrix["rows"]
    by_granularity = []
    for granularity in GRANULARITIES:
        selected = [row for row in rows if row["granularity"] == granularity]
        by_granularity.append({
            "granularity": granularity,
            "native_present_pairs": sum(row["native_or_derived"] == "NATIVE" for row in selected),
            "derived_pairs": sum(row["native_or_derived"] == "DERIVED" for row in selected),
            "research_eligible_pairs": sum(bool(row["development_eligibility"]) for row in selected),
            "records": sum(int(row["record_count"] or 0) for row in selected),
        })
    return {
        "schema": "AIOS_FOREX_AUTHORITATIVE_DATA_MATRIX_SUMMARY.v1",
        "packet_id": PACKET_ID,
        "status": "PASS",
        "matrix_schema": matrix["schema"],
        "row_count": matrix["row_count"],
        "pair_count": matrix["intended_pair_count"],
        "granularity_count": matrix["granularity_count"],
        "by_granularity": by_granularity,
        "holdout_scopes": matrix["holdout_scopes"],
        "safety": matrix["safety"],
    }


def write_outputs(repo_root: Path, output_root: Path) -> dict[str, Any]:
    matrix = build_matrix(repo_root)
    summary = summary_for(matrix)
    output_root.mkdir(parents=True, exist_ok=True)
    matrix_path = output_root / "AIOS_FOREX_AUTHORITATIVE_PAIR_TIMEFRAME_MATRIX_V1.json"
    summary_path = output_root / "AIOS_FOREX_AUTHORITATIVE_DATA_MATRIX_SUMMARY_V1.json"
    matrix_path.write_bytes(pretty_bytes(matrix))
    summary_path.write_bytes(pretty_bytes(summary))
    artifacts = [
        {"name": matrix_path.name, "bytes": matrix_path.stat().st_size, "sha256": sha256_file(matrix_path)},
        {"name": summary_path.name, "bytes": summary_path.stat().st_size, "sha256": sha256_file(summary_path)},
    ]
    receipt = {
        "schema": "AIOS_FOREX_AUTHORITATIVE_DATA_MATRIX_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "status": "PASS",
        "artifacts": artifacts,
        "artifact_aggregate_sha256": _set_hash(artifacts),
        "input_manifest_sha256": matrix["input_manifest_sha256"],
        "row_count": matrix["row_count"],
        "strategy_trials_added": 0,
        "final_holdout_opened": False,
    }
    receipt_path = output_root / "AIOS_FOREX_AUTHORITATIVE_DATA_MATRIX_RECEIPT_V1.json"
    receipt_path.write_bytes(pretty_bytes(receipt))
    return receipt

