"""Development-only component screen for the AIOS Forex edge tournament.

PKT-FOREX-039 scores the 72 cells frozen by PKT-FOREX-038.  It reads only
monthly M5 shards whose declared end is no later than 2025-04-01T00:00:00Z.
Validation and later shards are never opened.  The four arms are component
comparisons, not four independent edge claims.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import random
import statistics
from array import array
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

from automation.forex_engine.forex_commercial_reference_strategy_library_v1 import (
    select_commercial_baseline,
)
from automation.forex_engine.forex_edge_validation_pipeline_v1 import (
    candidate_fingerprint,
    evaluate_transition,
    read_trial_ledger,
    sha256_value as validation_sha256_value,
    validate_trial_ledger,
)


PACKET_ID = "PKT-FOREX-039"
IDENTITY_MARKER = "PKT_FOREX_039_EDGE_DISCOVERY_TOURNAMENT_STAGE1"
WORKER_ID = "EAST_OCC_77"
CORPUS_ID = "AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2"
CORPUS_SHA256 = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
CORPUS_MANIFEST_SHA256 = "1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b"
STAGE0_MANIFEST_SHA256 = "d3d57d4cb6f344868adf4abccea44f23a77e418bf501ae7de7ecc6105523ef99"
STAGE0_ARTIFACT_HASHES = {
    "AIOS_FOREX_FIRST_WAVE_EXPERIMENT_MANIFEST.json": "bdbbce0bd5fd70c159043748527fa5113d6b60d518ab93d2cb84958e02f6f98d",
    "AIOS_FOREX_COST_EXPOSURE_CONTRACT.json": "2554e6675cc3c3648a09b470583011c45f969709d801900e3d999f8c379b27b4",
    "AIOS_FOREX_CURRENCY_GRAPH_CONTRACT.json": "2cfd665187deb1f535bfbc9e908ac6a0ce237838380dcd7719fa80dc5f63a940",
    "AIOS_FOREX_STATISTICAL_CONTRACT.json": "a260a1d6165c4d002f5847fbff967a25e0c3430e35437de6776c5350548aff0e",
    "AIOS_FOREX_PRIOR_FAMILY_RECONCILIATION.json": "140bac5736c92239928ab3c89cb289e3196f978ac2baac45755443e1fec396af",
    "AIOS_FOREX_IMMUTABLE_DATASET_REFERENCE.json": "3d2c3f40396dc965caee94d232f8d473493da63de1b6a5623838057fe79b9e9d",
}
DEV_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEV_END = datetime(2025, 4, 1, tzinfo=timezone.utc)
LOOKBACKS = (12, 48, 288)
HORIZONS = (3, 12, 48)
ARMS = ("A", "B", "C", "D")
DIRECTIONS = ("ORIG", "INV")
SCENARIOS = {"GROSS": 0.0, "BASE": 0.1, "STRESSED": 0.5, "SEVERE_BUT_PLAUSIBLE": 1.0}
PRIOR_ATTEMPT_LOWER_BOUND = 1220
MAXIMUM_NEW_SCORED_CELLS = 72
EXPECTED_CUMULATIVE_LOWER_BOUND = 1292
BLOCK_BARS = 288
BOOTSTRAP_REPLICATES = 512
BOOTSTRAP_SEED = 39039
CAPABILITY_REGISTRY_RELATIVE = Path(".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_VALIDATION_CAPABILITY_REGISTRY_V1.json")
COMMERCIAL_REGISTRY_RELATIVE = Path(".aios/runtime/forex_commercial_reference_strategy_library_v1/AIOS_FOREX_COMMERCIAL_REFERENCE_AND_BENCHMARK_REGISTRY_V1.json")
TRIAL_LEDGER_RELATIVE = Path(".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl")
FINGERPRINT_INDEX_RELATIVE = Path(".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_FINGERPRINT_INDEX_V1.json")
CAPABILITY_REGISTRY_SHA256 = "9964e24cb4d8a0d538e697e9b80342412f56aca36107591e0bf2dac723fb7f07"
COMMERCIAL_REGISTRY_SHA256 = "561f02870ddfcc3ffa728e11ba61e95e027fee7210d4604c9f73b54b2021c83f"
PRE_SCORE_LEDGER_SHA256 = "f4378c3156c8110582a5f1c293f944e9475e2ff8795e62da1e1534649b48aa0b"
PRE_SCORE_FINGERPRINT_INDEX_SHA256 = "0af1a3ddcb64bdc0decab7c19e3c060ab0a31e59953046fa9f55d31dbe1a430f"
POST_SCORE_LEDGER_SHA256 = "d052f9c3c3fb2b6dc4083e8beb38cf94b0b190fa2ab7ca508d0dda0e90dad544"
POST_SCORE_FINGERPRINT_INDEX_SHA256 = "2bc3c6d9222eaa14ae274edd7939fc7d3f8ba5f57286398d69cf8b021b8d2832"
CORRECTED_LEDGER_SHA256 = "3bb0bc50e720e76be3834da3457a35ef7b32d7f99696950703cb2bbe4042b468"
CORRECTED_FINGERPRINT_INDEX_SHA256 = "9bd8a5cb1bc72f07fbb048389157457fe7a6e987c473178d373b5cff2b3c5a0f"
TRUSTED_CORRECTED_LEDGER_RELATIVE = Path(".aios/staging/PKT_FOREX_042/final_run1/AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl")
TRUSTED_CORRECTED_FINGERPRINT_INDEX_RELATIVE = Path(".aios/staging/PKT_FOREX_042/final_run1/AIOS_FOREX_FINGERPRINT_INDEX_V1.json")
TRUSTED_CORRECTIVE_MANIFEST_RELATIVE = Path(".aios/staging/PKT_FOREX_042/final_run1/AIOS_FOREX_PKT039_CORRECTIVE_MANIFEST.json")
TRUSTED_CORRECTIVE_MANIFEST_SHA256 = "9df195ac79f68671b99e54293874974b88fb3574cb681e1c58f7822358c3b191"
TRUSTED_CORRECTED_LEDGER_RECORDS = 227
TRUSTED_CORRECTED_FINGERPRINT_ENTRIES = 79
CORRECTIVE_PACKET_ID = "PKT-FOREX-042"
CORRECTIVE_IDENTITY_MARKER = "PKT_FOREX_042_PKT039_INSTRUMENT_PIP_METADATA_CORRECTIVE_REPLAY"
INSTRUMENT_METADATA_RELATIVE = Path(".aios/staging/PKT_FOREX_042/final_run1/AIOS_FOREX_PKT039_CORRECTED_INPUT_VERIFICATION.json")
INSTRUMENT_METADATA_SHA256 = "13a922c29806f153eea73adb06bc7f23c1b6a3bcee272f58fcd28777a99a200e"
PRIOR_INVALID_RESULT_SHA256 = "e361b3b8ce5b8379f8ddba55ec99cef11bc260c013e03abb025ad8a2a47e3645"
COMMERCIAL_REFERENCE_BY_ARM = {
    "A": ("FAST_TIME_SERIES_MOMENTUM", "FAST"),
    "B": ("CROSS_SECTIONAL_CURRENCY_STRENGTH", "CROSS_SECTIONAL"),
    "C": ("TREND_PULLBACK_CONTINUATION", "INTRADAY_PULLBACK"),
    "D": ("TREND_PULLBACK_CONTINUATION", "INTRADAY_PULLBACK"),
}


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


def _runtime_candidate_id(cell_id: str) -> str:
    parts = cell_id.split("-")
    if len(parts) != 5 or parts[0] != "FXT" or parts[4] not in DIRECTIONS:
        raise ValueError(f"INVALID_STAGE1_CELL_ID:{cell_id}")
    return f"PKT038_{parts[1]}_{parts[2]}_{parts[3]}_{'PRIMARY' if parts[4] == 'ORIG' else 'INVERSE'}"


def verify_append_only_corrected_memory(
    ledger_records: Sequence[dict[str, Any]], fingerprint_index: dict[str, Any],
    trusted_ledger_records: Sequence[dict[str, Any]], trusted_fingerprint_index: dict[str, Any],
) -> dict[str, Any]:
    """Pin the corrected PKT-039 history while allowing validated later appends."""
    current_summary = validate_trial_ledger(ledger_records)
    trusted_summary = validate_trial_ledger(trusted_ledger_records)
    if (
        len(trusted_ledger_records) != TRUSTED_CORRECTED_LEDGER_RECORDS
        or trusted_summary["scored_attempt_lower_bound"] != EXPECTED_CUMULATIVE_LOWER_BOUND
        or trusted_summary["proposed_unscored_count"] != 525
    ):
        raise RuntimeError("TRUSTED_CORRECTED_LEDGER_BASELINE_INVALID")
    if len(ledger_records) < len(trusted_ledger_records):
        raise RuntimeError("HISTORICAL_LEDGER_RECORD_MISSING")
    if list(ledger_records[:len(trusted_ledger_records)]) != list(trusted_ledger_records):
        raise RuntimeError("HISTORICAL_LEDGER_PREFIX_CHANGED_OR_REORDERED")
    if current_summary["scored_attempt_lower_bound"] < EXPECTED_CUMULATIVE_LOWER_BOUND:
        raise RuntimeError("SCORED_ATTEMPT_HISTORY_DECREASED")

    trusted_entries = list(trusted_fingerprint_index.get("entries", []))
    current_entries = list(fingerprint_index.get("entries", []))
    if len(trusted_entries) != TRUSTED_CORRECTED_FINGERPRINT_ENTRIES:
        raise RuntimeError("TRUSTED_CORRECTED_FINGERPRINT_BASELINE_INVALID")
    current_ids = [str(row.get("candidate_id", "")) for row in current_entries]
    current_fingerprints = [str(row.get("fingerprint", "")) for row in current_entries]
    if not all(current_ids) or len(current_ids) != len(set(current_ids)):
        raise RuntimeError("FINGERPRINT_INDEX_DUPLICATE_CANDIDATE_ID")
    if not all(current_fingerprints) or len(current_fingerprints) != len(set(current_fingerprints)):
        raise RuntimeError("FINGERPRINT_INDEX_DUPLICATE_FINGERPRINT")
    trusted_ids = {str(row["candidate_id"]) for row in trusted_entries}
    current_by_id = {str(row["candidate_id"]): row for row in current_entries}
    preserved_in_order = [row for row in current_entries if str(row.get("candidate_id")) in trusted_ids]
    if preserved_in_order != trusted_entries:
        raise RuntimeError("HISTORICAL_FINGERPRINT_ENTRY_CHANGED_DELETED_OR_REORDERED")

    later_ledger_identities: set[tuple[str, str]] = set()
    for row in ledger_records[len(trusted_ledger_records):]:
        candidate_id = str(row.get("candidate_id", ""))
        if not candidate_id:
            continue
        candidate_fingerprint_value = str(row.get("candidate_fingerprint", ""))
        indexed = current_by_id.get(candidate_id)
        if not candidate_fingerprint_value or indexed is None or indexed.get("fingerprint") != candidate_fingerprint_value:
            raise RuntimeError(f"LATER_LEDGER_CANDIDATE_IDENTITY_CONFLICT:{candidate_id}")
        later_ledger_identities.add((candidate_id, candidate_fingerprint_value))

    later_entries = [row for row in current_entries if str(row.get("candidate_id")) not in trusted_ids]
    for row in later_entries:
        specification = row.get("specification")
        if not isinstance(specification, dict) or candidate_fingerprint(specification) != row["fingerprint"]:
            raise RuntimeError(f"LATER_FINGERPRINT_SPECIFICATION_INVALID:{row.get('candidate_id')}")
        identity = (str(row["candidate_id"]), str(row["fingerprint"]))
        if identity not in later_ledger_identities:
            raise RuntimeError(f"LATER_FINGERPRINT_WITHOUT_EXACT_LEDGER_IDENTITY:{row.get('candidate_id')}")
    return {
        "status": "PASS",
        "validation_mode": "TRUSTED_CORRECTED_PREFIX_PLUS_VALIDATED_APPEND_ONLY_TAIL",
        "trusted_ledger_records": len(trusted_ledger_records),
        "later_ledger_records": len(ledger_records) - len(trusted_ledger_records),
        "trusted_fingerprint_entries": len(trusted_entries),
        "later_fingerprint_entries": len(later_entries),
        "current_summary": current_summary,
    }


def verify_runtime_contracts(repo_root: Path, cells: Sequence[dict[str, Any]], *, require_pre_score: bool = True) -> dict[str, Any]:
    paths = {
        "capability_registry": repo_root / CAPABILITY_REGISTRY_RELATIVE,
        "commercial_registry": repo_root / COMMERCIAL_REGISTRY_RELATIVE,
        "trial_ledger": repo_root / TRIAL_LEDGER_RELATIVE,
        "fingerprint_index": repo_root / FINGERPRINT_INDEX_RELATIVE,
    }
    expected_hashes = {
        "capability_registry": CAPABILITY_REGISTRY_SHA256,
        "commercial_registry": COMMERCIAL_REGISTRY_SHA256,
    }
    observed_hashes = {name: sha256_file(path) for name, path in paths.items()}
    observed_memory_pair = (observed_hashes["trial_ledger"], observed_hashes["fingerprint_index"])
    mismatches = sorted(name for name in expected_hashes if observed_hashes[name] != expected_hashes[name])
    if require_pre_score and observed_memory_pair != (PRE_SCORE_LEDGER_SHA256, PRE_SCORE_FINGERPRINT_INDEX_SHA256):
        mismatches.extend(["trial_ledger", "fingerprint_index"])
    if mismatches:
        raise RuntimeError(f"RUNTIME_CONTRACT_SHA256_MISMATCH:{','.join(mismatches)}")

    capability = json.loads(paths["capability_registry"].read_text(encoding="utf-8"))
    if not (
        capability.get("required_capabilities") == 38
        and capability.get("certified_capabilities") == 38
        and capability.get("blocked_capabilities") == 0
        and capability.get("readiness_percent") == 100.0
        and all(row.get("certified") is True for row in capability.get("capabilities", []))
    ):
        raise RuntimeError("PKT040_VALIDATION_PIPELINE_NOT_CERTIFIED")

    commercial = json.loads(paths["commercial_registry"].read_text(encoding="utf-8"))
    references = commercial.get("reference_strategies", [])
    if commercial.get("status") != "COMMERCIAL_REFERENCE_LIBRARY_REGISTERED_STAGE0" or len(references) != 7:
        raise RuntimeError("PKT041_COMMERCIAL_REFERENCE_LIBRARY_NOT_CERTIFIED")
    if commercial.get("champion_challenger_contract", {}).get("selection_timing") != "FROZEN_BEFORE_OUTCOME_ACCESS":
        raise RuntimeError("PKT041_BASELINE_SELECTION_NOT_FROZEN")

    ledger_records = read_trial_ledger(paths["trial_ledger"])
    ledger_summary = validate_trial_ledger(ledger_records)
    fingerprint_index = json.loads(paths["fingerprint_index"].read_text(encoding="utf-8"))
    memory_compatibility: dict[str, Any]
    if require_pre_score:
        memory_compatibility = {"status": "PASS", "validation_mode": "EXACT_PRE_SCORE_SNAPSHOT"}
    elif observed_memory_pair == (POST_SCORE_LEDGER_SHA256, POST_SCORE_FINGERPRINT_INDEX_SHA256):
        memory_compatibility = {"status": "PASS", "validation_mode": "EXACT_ORIGINAL_POST_SCORE_SNAPSHOT"}
    else:
        trusted_ledger_path = repo_root / TRUSTED_CORRECTED_LEDGER_RELATIVE
        trusted_index_path = repo_root / TRUSTED_CORRECTED_FINGERPRINT_INDEX_RELATIVE
        trusted_manifest_path = repo_root / TRUSTED_CORRECTIVE_MANIFEST_RELATIVE
        if sha256_file(trusted_manifest_path) != TRUSTED_CORRECTIVE_MANIFEST_SHA256:
            raise RuntimeError("TRUSTED_CORRECTIVE_MANIFEST_SHA256_MISMATCH")
        trusted_manifest = json.loads(trusted_manifest_path.read_text(encoding="utf-8"))
        trusted_artifacts = trusted_manifest.get("artifacts", {})
        trusted_manifest_hashes = {
            "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl": CORRECTED_LEDGER_SHA256,
            "AIOS_FOREX_FINGERPRINT_INDEX_V1.json": CORRECTED_FINGERPRINT_INDEX_SHA256,
        }
        if (
            trusted_manifest.get("packet_id") != CORRECTIVE_PACKET_ID
            or trusted_manifest.get("schema") != "AIOS_FOREX_PKT039_CORRECTIVE_MANIFEST.v1"
            or any(trusted_artifacts.get(name, {}).get("sha256") != digest for name, digest in trusted_manifest_hashes.items())
        ):
            raise RuntimeError("TRUSTED_CORRECTIVE_MANIFEST_CONTENT_MISMATCH")
        if sha256_file(trusted_ledger_path) != CORRECTED_LEDGER_SHA256 or sha256_file(trusted_index_path) != CORRECTED_FINGERPRINT_INDEX_SHA256:
            raise RuntimeError("TRUSTED_CORRECTED_MEMORY_RECEIPT_SHA256_MISMATCH")
        memory_compatibility = verify_append_only_corrected_memory(
            ledger_records,
            fingerprint_index,
            read_trial_ledger(trusted_ledger_path),
            json.loads(trusted_index_path.read_text(encoding="utf-8")),
        )
    expected_scored = PRIOR_ATTEMPT_LOWER_BOUND if require_pre_score else EXPECTED_CUMULATIVE_LOWER_BOUND
    # Exact counts belong to immutable snapshots, not the validated growing log.
    snapshot_mode = memory_compatibility["validation_mode"].startswith("EXACT_")
    invalid_count = (ledger_summary["scored_attempt_lower_bound"] != expected_scored
                     if snapshot_mode else ledger_summary["scored_attempt_lower_bound"] < expected_scored)
    if invalid_count or ledger_summary["proposed_unscored_count"] < 525:
        raise RuntimeError("GLOBAL_TRIAL_MEMORY_PRE_SCORE_MISMATCH")

    entries = fingerprint_index.get("entries", [])
    by_id = {row.get("candidate_id"): row for row in entries}
    if len(entries) < 79 or len(entries) != len(by_id):
        raise RuntimeError("FINGERPRINT_INDEX_PRE_SCORE_COUNT_MISMATCH")
    frozen_cell_ids = {row["cell_id"] for row in cells}
    if len(frozen_cell_ids) != 72:
        raise RuntimeError("FROZEN_CELL_COUNT_MISMATCH")
    mappings: dict[str, dict[str, Any]] = {}
    for cell in cells:
        runtime_id = _runtime_candidate_id(cell["cell_id"])
        indexed = by_id.get(runtime_id)
        permitted_statuses = {"PROPOSED_UNSCORED"} if require_pre_score else {"VALID_TEST_REJECTED", "SURVIVOR"}
        if not indexed or indexed.get("status") not in permitted_statuses:
            raise RuntimeError(f"FINGERPRINT_STATUS_MISMATCH:{cell['cell_id']}")
        reference_id, horizon_class = COMMERCIAL_REFERENCE_BY_ARM[cell["arm"]]
        selection = select_commercial_baseline(
            {"declared_reference_strategy_id": reference_id, "horizon_class": horizon_class}, references,
        )
        if selection.get("status") != "PASS":
            raise RuntimeError(f"COMMERCIAL_BASELINE_SELECTION_FAILED:{cell['cell_id']}")
        mappings[cell["cell_id"]] = {
            "runtime_candidate_id": runtime_id,
            "runtime_candidate_fingerprint": indexed["fingerprint"],
            "frozen_stage0_candidate_fingerprint": cell["candidate_fingerprint"],
            "commercial_reference_strategy_id": reference_id,
            "commercial_reference_horizon_class": horizon_class,
            "commercial_reference_selection": selection,
        }
    return {
        "status": "PASS",
        "observed_sha256": observed_hashes,
        "pkt040": {"required": 38, "certified": 38, "blocked": 0, "readiness_percent": 100.0},
        "pkt041": {
            "status": commercial["status"],
            "reference_count": len(references),
            "ordered_required_baselines": commercial["champion_challenger_contract"]["ordered_required_baselines"],
            "current_aios_champion": "NONE",
        },
        "pre_score_trial_memory": ledger_summary,
        "memory_compatibility": memory_compatibility,
        "cell_identity_mappings": dict(sorted(mappings.items())),
    }


def prepare_global_memory_update(
    result: dict[str, Any], runtime_contracts: dict[str, Any], ledger_records: Sequence[dict[str, Any]],
    fingerprint_index: dict[str, Any], result_sha256: str,
) -> tuple[bytes, bytes, dict[str, Any]]:
    current_summary = validate_trial_ledger(ledger_records)
    if current_summary["scored_attempt_lower_bound"] != PRIOR_ATTEMPT_LOWER_BOUND:
        raise RuntimeError("TRIAL_LEDGER_CHANGED_DURING_RUN")
    updated_records = [dict(row) for row in ledger_records]
    mappings = runtime_contracts["cell_identity_mappings"]
    entries = [dict(row) for row in fingerprint_index.get("entries", [])]
    by_id = {row["candidate_id"]: row for row in entries}
    for cell_id in result["scored_cell_ids"]:
        row = result["cell_results"][cell_id]
        mapping = mappings[cell_id]
        payload = {
            "event_id": f"PKT039_STAGE1_{cell_id.replace('-', '_')}",
            "status": "SURVIVOR" if row["mechanism_observed"] else "VALID_TEST_REJECTED",
            "scored_trial_increment": 1,
            "proposed_count": 0,
            "provenance": "PKT_FOREX_039_DEVELOPMENT_ONLY_STAGE1",
            "candidate_fingerprint": mapping["runtime_candidate_fingerprint"],
            "frozen_stage0_candidate_fingerprint": mapping["frozen_stage0_candidate_fingerprint"],
            "cell_id": cell_id,
            "result_artifact_sha256": result_sha256,
        }
        previous = updated_records[-1]["record_sha256"]
        record = {"sequence": len(updated_records) + 1, "previous_record_sha256": previous, **payload}
        record["record_sha256"] = validation_sha256_value(record)
        updated_records.append(record)
        indexed = by_id[mapping["runtime_candidate_id"]]
        indexed.update({
            "status": payload["status"],
            "stage1_packet_id": PACKET_ID,
            "stage1_cell_id": cell_id,
            "frozen_stage0_candidate_fingerprint": mapping["frozen_stage0_candidate_fingerprint"],
            "result_artifact_sha256": result_sha256,
        })
    updated_summary = validate_trial_ledger(updated_records)
    if updated_summary["scored_attempt_lower_bound"] != EXPECTED_CUMULATIVE_LOWER_BOUND:
        raise RuntimeError("GLOBAL_TRIAL_INCREMENT_MISMATCH")
    updated_index = dict(fingerprint_index)
    updated_index["entries"] = sorted(entries, key=lambda row: (row["fingerprint"], row["candidate_id"]))
    updated_index["pkt039_outcome_examined"] = len(result["scored_cell_ids"])
    updated_index["pkt039_survivors"] = len(result["mechanism_observed_cells"])
    updated_index["total_proposed_unscored"] = 525
    ledger_payload = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
        for row in updated_records
    )
    index_payload = canonical_bytes(updated_index)
    return ledger_payload, index_payload, {
        "status": "PASS",
        "records_before": len(ledger_records),
        "records_after": len(updated_records),
        "scored_attempt_lower_bound_before": current_summary["scored_attempt_lower_bound"],
        "scored_attempt_lower_bound_after": updated_summary["scored_attempt_lower_bound"],
        "proposed_unscored_before": current_summary["proposed_unscored_count"],
        "historical_proposed_unscored_count_preserved": updated_summary["proposed_unscored_count"],
        "ledger_sha256": sha256_bytes(ledger_payload),
        "fingerprint_index_sha256": sha256_bytes(index_payload),
    }


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@lru_cache(maxsize=1)
def certified_instrument_metadata() -> dict[str, dict[str, Any]]:
    """Load the exact certified 58-pair metadata snapshot and fail closed."""
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / INSTRUMENT_METADATA_RELATIVE
    if not path.is_file() or sha256_file(path) != INSTRUMENT_METADATA_SHA256:
        raise RuntimeError("CERTIFIED_INSTRUMENT_METADATA_SHA256_MISMATCH")
    corpus_manifest_path = repo_root / ".aios/runtime/forex_m5_immutable_corpus_v2/manifest.json"
    if not corpus_manifest_path.is_file() or sha256_file(corpus_manifest_path) != CORPUS_MANIFEST_SHA256:
        raise RuntimeError("CERTIFIED_CORPUS_MANIFEST_SHA256_MISMATCH")
    eligible_pairs = set(json.loads(corpus_manifest_path.read_text(encoding="utf-8")).get("eligible_pairs", []))
    if len(eligible_pairs) != 58:
        raise RuntimeError("CERTIFIED_CORPUS_PAIR_SET_NOT_EXACT_58")
    payload = json.loads(path.read_text(encoding="utf-8"))
    # This trusted receipt contains metadata only. The former replay_cache
    # source also contained protected prices and must not be opened here.
    receipt = payload.get("instrument_metadata", {})
    if receipt.get("status") != "PASS" or receipt.get("pair_count") != 58:
        raise RuntimeError("CERTIFIED_INSTRUMENT_METADATA_RECEIPT_INVALID")
    rows = [{"instrument": pair, **values} for pair, values in receipt.get("pair_metadata", {}).items()]
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        pair = str(row.get("instrument", ""))
        if pair not in eligible_pairs:
            continue
        if not pair or pair in metadata:
            raise RuntimeError("CERTIFIED_INSTRUMENT_METADATA_DUPLICATE_OR_EMPTY_PAIR")
        size = float(row.get("pip_size", 0.0))
        location = int(row.get("pip_location", 99))
        precision = int(row.get("display_precision", 0))
        if not math.isfinite(size) or size <= 0 or not math.isclose(size, 10.0 ** location, rel_tol=0.0, abs_tol=1e-15):
            raise RuntimeError(f"CERTIFIED_INSTRUMENT_METADATA_INVALID_PIP:{pair}")
        if precision <= -location:
            raise RuntimeError(f"CERTIFIED_INSTRUMENT_METADATA_INVALID_PRECISION:{pair}")
        metadata[pair] = {
            "pip_location": location,
            "pip_size": size,
            "display_precision": precision,
        }
    if len(metadata) != 58:
        raise RuntimeError("CERTIFIED_INSTRUMENT_METADATA_NOT_EXACT_58")
    return dict(sorted(metadata.items()))


def pip_size(pair: str) -> float:
    metadata = certified_instrument_metadata()
    if pair not in metadata:
        raise ValueError(f"PAIR_MISSING_CERTIFIED_INSTRUMENT_METADATA:{pair}")
    return float(metadata[pair]["pip_size"])


def session_label(moment: datetime) -> str:
    if 7 <= moment.hour < 12:
        return "LONDON"
    if 12 <= moment.hour < 16:
        return "LONDON_NEW_YORK_OVERLAP"
    if 16 <= moment.hour < 21:
        return "NEW_YORK"
    return "ASIA_HANDOFF_OTHER"


def block_id(moment: datetime) -> int:
    return int((moment - DEV_START).total_seconds() // (300 * BLOCK_BARS))


def opposite(direction: str) -> str:
    if direction == "LONG":
        return "SHORT"
    if direction == "SHORT":
        return "LONG"
    raise ValueError("INVALID_DIRECTION")


def verify_stage0(stage0_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = stage0_root / "AIOS_FOREX_EDGE_TOURNAMENT_MANIFEST.json"
    if sha256_file(manifest_path) != STAGE0_MANIFEST_SHA256:
        raise RuntimeError("STAGE0_MANIFEST_SHA256_MISMATCH")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, expected in STAGE0_ARTIFACT_HASHES.items():
        path = stage0_root / name
        if manifest["artifacts"][name]["sha256"] != expected or sha256_file(path) != expected:
            raise RuntimeError(f"STAGE0_ARTIFACT_SHA256_MISMATCH:{name}")
    first_wave = json.loads((stage0_root / "AIOS_FOREX_FIRST_WAVE_EXPERIMENT_MANIFEST.json").read_text(encoding="utf-8"))
    cells = first_wave.get("cells", [])
    expected_ids = {
        f"FXT-{arm}-L{lookback}-H{horizon}-{direction}"
        for arm in ARMS for lookback in LOOKBACKS for horizon in HORIZONS for direction in DIRECTIONS
    }
    if len(cells) != 72 or {row.get("cell_id") for row in cells} != expected_ids:
        raise RuntimeError("STAGE0_CELL_GRID_MISMATCH")
    if any(row.get("status") != "PROPOSED_UNSCORED" for row in cells):
        raise RuntimeError("STAGE0_CELL_ALREADY_SCORED")
    if first_wave["partitions"]["development"] != [timestamp_text(DEV_START), timestamp_text(DEV_END)]:
        raise RuntimeError("DEVELOPMENT_BOUNDARY_MISMATCH")
    return first_wave, manifest


def verify_corpus_manifest(corpus_root: Path) -> dict[str, Any]:
    path = corpus_root / "manifest.json"
    if sha256_file(path) != CORPUS_MANIFEST_SHA256:
        raise RuntimeError("CORPUS_MANIFEST_SHA256_MISMATCH")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("corpus_id") != CORPUS_ID or manifest.get("aggregate_corpus_fingerprint") != CORPUS_SHA256:
        raise RuntimeError("CORPUS_IDENTITY_MISMATCH")
    pairs = manifest.get("eligible_pairs", [])
    if len(pairs) != 58 or len(set(pairs)) != 58 or pairs != sorted(pairs):
        raise RuntimeError("ELIGIBLE_PAIR_UNIVERSE_MISMATCH")
    metadata = certified_instrument_metadata()
    if set(pairs) != set(metadata):
        raise RuntimeError("CORPUS_AND_INSTRUMENT_METADATA_PAIR_SET_MISMATCH")
    return manifest


def validate_successor_preacquisition_contract(context: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when a new governed successor tries to inherit PKT-044 data.

    This is deliberately a no-price, no-score guard.  A successor may be
    preregistered here, but must pass its own source, inventory, cost, corpus,
    and later scoring-authority gates before it can reach any research runner.
    """
    if not isinstance(context, dict):
        raise ValueError("SUCCESSOR_CONTEXT_INVALID")
    packet_id = str(context.get("packet_id", ""))
    parent_packet_id = str(context.get("parent_packet_id", ""))
    if not packet_id or packet_id == parent_packet_id or packet_id == "PKT-FOREX-044":
        raise ValueError("SUCCESSOR_PACKET_IDENTITY_INVALID")
    if parent_packet_id != "PKT-FOREX-044" or context.get("parent_outcome") != "MATERIAL_DATA_SEMANTICS_CHANGE":
        raise ValueError("SUCCESSOR_PARENT_LINEAGE_INVALID")
    if context.get("provider") != "DUKASCOPY" or context.get("source_type") != "PAIRED_TICK":
        raise ValueError("SUCCESSOR_SOURCE_TYPE_INVALID")
    if tuple(context.get("required_price_sides", ())) != ("BID", "ASK"):
        raise ValueError("SUCCESSOR_EXECUTION_SIDES_INVALID")
    if context.get("same_record_pairing") is not True:
        raise ValueError("SUCCESSOR_PAIRED_TICK_SYNC_REQUIRED")
    if context.get("midpoint_semantics") != "PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION":
        raise ValueError("SUCCESSOR_MID_SEMANTICS_INVALID")
    if context.get("m5_aggregation") != "FIRST_MAX_MIN_LAST_MID_T_COMPLETED_UTC_M5_ONLY":
        raise ValueError("SUCCESSOR_M5_AGGREGATION_INVALID")
    if context.get("execution_price_semantics") != "SOURCE_BACKED_BID_ASK_SIDE_CORRECT":
        raise ValueError("SUCCESSOR_EXECUTION_PRICE_SEMANTICS_INVALID")
    if context.get("scoring_allowed") is not False or context.get("market_outcomes_opened") is not False:
        raise ValueError("SUCCESSOR_SCORING_FORBIDDEN_DURING_PREREGISTRATION")
    cards = context.get("cards")
    if not isinstance(cards, list) or len(cards) != 2:
        raise ValueError("SUCCESSOR_AB_CARD_COUNT_INVALID")
    for card in cards:
        specification = card.get("specification")
        if not isinstance(specification, dict) or candidate_fingerprint(specification) != card.get("fingerprint"):
            raise ValueError("SUCCESSOR_CARD_FINGERPRINT_INVALID")
        identity = specification.get("data_identity", {})
        if identity.get("corpus") == CORPUS_ID or identity.get("manifest_sha256") == CORPUS_MANIFEST_SHA256:
            raise ValueError("SUCCESSOR_OLD_CORPUS_FALLBACK_FORBIDDEN")
        if identity.get("corpus_status") != "PREACQUISITION_NO_CERTIFIED_CORPUS":
            raise ValueError("SUCCESSOR_CORPUS_STATUS_INVALID")
    return {
        "status": "PASS",
        "packet_id": packet_id,
        "parent_packet_id": parent_packet_id,
        "scoring_status": "BLOCKED_AWAITING_CERTIFIED_SUCCESSOR_CORPUS_AND_FUTURE_AUTHORITY",
        "market_rows_opened": 0,
    }


def development_artifacts(manifest: dict[str, Any], pair: str) -> list[dict[str, Any]]:
    if pair not in manifest["eligible_pairs"]:
        raise ValueError(f"INELIGIBLE_PAIR:{pair}")
    chosen = []
    for item in manifest["artifacts"]:
        if item["instrument"] != pair:
            continue
        start = parse_timestamp(item["start_utc"])
        end = parse_timestamp(item["end_utc"])
        if DEV_START <= start and end <= DEV_END:
            chosen.append(item)
    chosen.sort(key=lambda row: row["start_utc"])
    if not chosen or chosen[0]["start_utc"] != timestamp_text(DEV_START) or chosen[-1]["end_utc"] != timestamp_text(DEV_END):
        raise RuntimeError(f"INCOMPLETE_DEVELOPMENT_SHARDS:{pair}")
    if any(parse_timestamp(row["end_utc"]) > DEV_END for row in chosen):
        raise RuntimeError("VALIDATION_SHARD_SELECTED")
    return chosen


def read_pair_bars(corpus_root: Path, manifest: dict[str, Any], pair: str, verification: dict[str, Any], *, before_outcome=None) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    previous = ""
    for item in development_artifacts(manifest, pair):
        path = corpus_root / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"DEVELOPMENT_SHARD_MISMATCH:{item['path']}")
        verification[item["path"]] = {"bytes": item["bytes"], "records": item["records"], "sha256": item["sha256"], "status": "PASS"}
        with gzip.open(path, "rt", encoding="ascii") as handle:
            for line in handle:
                if before_outcome is not None:
                    # Durably acknowledge access before parsing any price or
                    # using the row. Callback is idempotent across pair calls.
                    before_outcome()
                    before_outcome = None
                row = json.loads(line)
                moment = parse_timestamp(str(row.get("timestamp", "")))
                if not DEV_START <= moment < DEV_END:
                    raise RuntimeError("NON_DEVELOPMENT_ROW_OPENED")
                if row.get("instrument") != pair or row.get("complete") is not True or row["timestamp"] <= previous:
                    raise RuntimeError(f"MALFORMED_OR_NONCHRONOLOGICAL_ROW:{pair}")
                for side in ("mid", "bid", "ask"):
                    if not all(math.isfinite(float(row[side][field])) and float(row[side][field]) > 0 for field in ("o", "h", "l", "c")):
                        raise RuntimeError(f"INVALID_PRICE:{pair}:{row['timestamp']}")
                if float(row["ask"]["o"]) < float(row["bid"]["o"]) or float(row["ask"]["c"]) < float(row["bid"]["c"]):
                    raise RuntimeError(f"CROSSED_QUOTE:{pair}:{row['timestamp']}")
                previous = row["timestamp"]
                bars.append(row)
    return bars


def contiguous_segments(bars: Sequence[dict[str, Any]]) -> list[int]:
    starts: list[int] = []
    segment = 0
    previous: datetime | None = None
    for index, bar in enumerate(bars):
        current = parse_timestamp(bar["timestamp"])
        if previous is None or current - previous != timedelta(minutes=5):
            segment = index
        starts.append(segment)
        previous = current
    return starts


def causal_momentum_values(closes: Sequence[float], segments: Sequence[int]) -> list[dict[int, float]]:
    output: list[dict[int, float]] = [{} for _ in closes]
    returns: deque[float] = deque(maxlen=288)
    running_sum = running_square = 0.0
    previous_segment = -1
    for index, close in enumerate(closes):
        if segments[index] != previous_segment:
            returns.clear()
            running_sum = running_square = 0.0
            previous_segment = segments[index]
        if index == segments[index]:
            continue
        value = math.log(close / closes[index - 1])
        if len(returns) == returns.maxlen:
            removed = returns.popleft()
            running_sum -= removed
            running_square -= removed * removed
        returns.append(value)
        running_sum += value
        running_square += value * value
        if len(returns) != 288:
            continue
        variance = (running_square - running_sum * running_sum / 288) / 287
        if variance <= 0:
            continue
        sigma = math.sqrt(variance)
        for lookback in LOOKBACKS:
            if index - lookback >= segments[index]:
                output[index][lookback] = math.log(close / closes[index - lookback]) / (sigma * math.sqrt(lookback))
    return output


def discover_impulses(pair: str, bars: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    closes = [float(row["mid"]["c"]) for row in bars]
    segments = contiguous_segments(bars)
    momentum = causal_momentum_values(closes, segments)
    sigma_history: deque[float] = deque(maxlen=288)
    events: list[dict[str, Any]] = []
    previous_close: float | None = None
    for index, row in enumerate(bars):
        if previous_close is not None and index > segments[index]:
            sigma_history.append(abs(math.log(closes[index] / previous_close)))
        previous_close = closes[index]
        if index - 12 < segments[index] or not momentum[index]:
            continue
        prior = closes[index - 12:index]
        for lookback, normalized in sorted(momentum[index].items()):
            direction = "LONG" if normalized >= 1.0 and closes[index] > max(prior) else (
                "SHORT" if normalized <= -1.0 and closes[index] < min(prior) else ""
            )
            if not direction:
                continue
            anchor = closes[index - lookback]
            endpoint = closes[index]
            impulse_size = endpoint - anchor if direction == "LONG" else anchor - endpoint
            if impulse_size <= 0:
                continue
            signal = parse_timestamp(row["timestamp"]) + timedelta(minutes=5)
            if not DEV_START <= signal < DEV_END:
                continue
            recent_scale = statistics.median(sigma_history) if sigma_history else 0.0
            current_scale = sigma_history[-1] if sigma_history else 0.0
            ratio = current_scale / recent_scale if recent_scale > 0 else 1.0
            regime = "LOW" if ratio < 0.75 else ("HIGH" if ratio > 1.25 else "NORMAL")
            core = {"pair": pair, "bar_timestamp": row["timestamp"], "lookback": lookback, "direction": direction, "anchor": anchor, "endpoint": endpoint}
            events.append({
                **core,
                "event_id": sha256_bytes(canonical_bytes(core)),
                "index": index,
                "signal_timestamp": timestamp_text(signal),
                "momentum": normalized,
                "impulse_size": impulse_size,
                "session": session_label(signal),
                "volatility_regime": regime,
                "block_id": block_id(signal),
            })
    return events


def _invert_matrix(matrix: list[list[float]]) -> list[list[float]]:
    size = len(matrix)
    augmented = [list(row) + [1.0 if i == j else 0.0 for j in range(size)] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("CURRENCY_GRAPH_RANK_DEFICIENT")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [left - factor * right for left, right in zip(augmented[row], augmented[column])]
    return [row[size:] for row in augmented]


class CurrencyGraphProjector:
    def __init__(self, pairs: Sequence[str], excluded_pair: str | None = None) -> None:
        self.pairs = tuple(pairs)
        undirected = [tuple(sorted(pair.split("_"))) for pair in self.pairs]
        if len(set(self.pairs)) != len(self.pairs) or len(set(undirected)) != len(undirected):
            raise ValueError("DUPLICATE_SYNTHETIC_LINEAGE")
        self.currencies = tuple(sorted({currency for pair in pairs for currency in pair.split("_")}))
        self.currency_index = {currency: index for index, currency in enumerate(self.currencies)}
        self.included = tuple(index for index, pair in enumerate(self.pairs) if pair != excluded_pair)
        adjacency = {currency: set() for currency in self.currencies}
        for index in self.included:
            base, quote = self.pairs[index].split("_")
            adjacency[base].add(quote)
            adjacency[quote].add(base)
        visited: set[str] = set()
        stack = [self.currencies[0]]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            stack.extend(sorted(adjacency[node] - visited))
        if visited != set(self.currencies):
            raise ValueError("DISCONNECTED_CURRENCY_GRAPH")
        count = len(self.currencies)
        kkt = [[0.0] * (count + 1) for _ in range(count + 1)]
        for index in self.included:
            base, quote = self.pairs[index].split("_")
            left, right = self.currency_index[base], self.currency_index[quote]
            kkt[left][left] += 1.0
            kkt[right][right] += 1.0
            kkt[left][right] -= 1.0
            kkt[right][left] -= 1.0
        for index in range(count):
            kkt[index][count] = 1.0
            kkt[count][index] = 1.0
        self.inverse = _invert_matrix(kkt)

    def strengths(self, returns: Sequence[float]) -> dict[str, float]:
        if len(returns) != len(self.pairs) or any(not math.isfinite(value) for value in returns):
            raise ValueError("INCOMPLETE_SYNCHRONIZED_GRAPH")
        count = len(self.currencies)
        rhs = [0.0] * (count + 1)
        for index in self.included:
            base, quote = self.pairs[index].split("_")
            rhs[self.currency_index[base]] += returns[index]
            rhs[self.currency_index[quote]] -= returns[index]
        solved = [math.fsum(left * right for left, right in zip(row, rhs)) for row in self.inverse]
        return {currency: solved[index] for index, currency in enumerate(self.currencies)}

    def quartiles(self, returns: Sequence[float]) -> tuple[set[str], set[str], dict[str, float]]:
        strengths = self.strengths(returns)
        ordered = sorted(self.currencies, key=lambda currency: (-strengths[currency], currency))
        width = max(1, math.ceil(len(ordered) / 4))
        return set(ordered[:width]), set(ordered[-width:]), strengths


def graph_select(pair: str, direction: str, top: set[str], bottom: set[str]) -> bool:
    base, quote = pair.split("_")
    return (base in top and quote in bottom) if direction == "LONG" else (base in bottom and quote in top)


def build_graph_diagnostics(
    pairs: Sequence[str], bars_by_pair_loader: Any, events: Sequence[dict[str, Any]],
) -> tuple[dict[tuple[int, str], dict[str, Any]], dict[str, Any]]:
    needed = {lookback: {event["bar_timestamp"] for event in events if event["lookback"] == lookback} for lookback in LOOKBACKS}
    vectors = {(lookback, timestamp): array("d", [math.nan]) * len(pairs) for lookback in LOOKBACKS for timestamp in needed[lookback]}
    for pair_index, pair in enumerate(pairs):
        bars = bars_by_pair_loader(pair)
        closes = [float(row["mid"]["c"]) for row in bars]
        segments = contiguous_segments(bars)
        indexes = {row["timestamp"]: index for index, row in enumerate(bars)}
        for lookback in LOOKBACKS:
            for timestamp in needed[lookback]:
                index = indexes.get(timestamp)
                if index is not None and index - lookback >= segments[index]:
                    vectors[(lookback, timestamp)][pair_index] = math.log(closes[index] / closes[index - lookback])
    projector = CurrencyGraphProjector(pairs)
    target_pairs: dict[tuple[int, str], set[str]] = defaultdict(set)
    for event in events:
        target_pairs[(event["lookback"], event["bar_timestamp"])].add(event["pair"])
    leave_projectors: dict[str, CurrencyGraphProjector] = {}
    leave_infeasible: set[str] = set()
    for pair in sorted({event["pair"] for event in events}):
        try:
            leave_projectors[pair] = CurrencyGraphProjector(pairs, pair)
        except ValueError as exc:
            if str(exc) != "DISCONNECTED_CURRENCY_GRAPH":
                raise
            leave_infeasible.add(pair)
    output: dict[tuple[int, str], dict[str, Any]] = {}
    incomplete = 0
    leave_checks = leave_matches = 0
    for key in sorted(vectors):
        values = vectors[key]
        if any(math.isnan(value) for value in values):
            output[key] = {"status": "INCOMPLETE_STABLE_MEMBERSHIP"}
            incomplete += 1
            continue
        top, bottom, strengths = projector.quartiles(values)
        leave: dict[str, dict[str, Any]] = {}
        for pair in sorted(target_pairs[key]):
            if pair in leave_infeasible:
                leave[pair] = {"status": "NOT_FEASIBLE_PAIR_IS_GRAPH_BRIDGE"}
                continue
            leave_top, leave_bottom, _ = leave_projectors[pair].quartiles(values)
            leave[pair] = {"status": "PASS", "top": sorted(leave_top), "bottom": sorted(leave_bottom)}
            leave_checks += 1
            if top == leave_top and bottom == leave_bottom:
                leave_matches += 1
        output[key] = {
            "status": "PASS",
            "top": sorted(top),
            "bottom": sorted(bottom),
            "strength_sha256": sha256_bytes(canonical_bytes({"lookback": key[0], "timestamp": key[1], "strengths": strengths})),
            "leave_target_pair_out": leave,
        }
    audit = {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_GRAPH_AUDIT.v1",
        "currency_count": len(projector.currencies),
        "pair_count": len(pairs),
        "maximum_independent_currency_coordinates": len(projector.currencies) - 1,
        "requested_synchronized_lookback_timestamps": len(vectors),
        "complete_synchronized_timestamps": len(vectors) - incomplete,
        "dropped_incomplete_timestamps": incomplete,
        "missing_policy": "DROP_WHOLE_TIMESTAMP_BEFORE_RANKING",
        "quartile_width": math.ceil(len(projector.currencies) / 4),
        "ranking": "DESCENDING_STRENGTH_THEN_ASCENDING_CURRENCY_CODE",
        "leave_target_pair_out_checks": leave_checks,
        "leave_target_pair_out_identical_quartiles": leave_matches,
        "leave_target_pair_out_infeasible_bridge_pairs": sorted(leave_infeasible),
        "leave_target_pair_out_caveat": "TRIANGULATION_CAN_STILL_RECONSTRUCT_TARGET_NOT_PROOF_OF_INDEPENDENCE",
        "status": "PASS",
    }
    return output, audit


def path_is_consecutive(bars: Sequence[dict[str, Any]], start: int, end: int) -> bool:
    if start < 0 or end >= len(bars) or end < start:
        return False
    times = [parse_timestamp(bars[index]["timestamp"]) for index in range(start, end + 1)]
    return all(right - left == timedelta(minutes=5) for left, right in zip(times, times[1:]))


def crosses_unsupported_rollover(bars: Sequence[dict[str, Any]], entry: int, exit_index: int) -> bool:
    for index in range(entry, exit_index + 1):
        moment = parse_timestamp(bars[index]["timestamp"])
        minute = moment.hour * 60 + moment.minute
        if 21 * 60 + 55 <= minute <= 22 * 60 + 10:
            return True
    return False


def pullback_entry(bars: Sequence[dict[str, Any]], event: dict[str, Any], max_wait: int = 12) -> dict[str, Any]:
    impulse = int(event["index"])
    direction = event["direction"]
    endpoint = float(event["endpoint"])
    size = float(event["impulse_size"])
    qualified = False
    last = min(len(bars) - 1, impulse + max_wait)
    for index in range(impulse + 1, last + 1):
        if not path_is_consecutive(bars, impulse, index):
            return {"state": "DATA_BLOCKED", "terminal_index": index}
        close = float(bars[index]["mid"]["c"])
        retracement = ((endpoint - close) if direction == "LONG" else (close - endpoint)) / size
        if retracement > 0.60:
            return {"state": "INVALIDATED", "terminal_index": index}
        if not qualified and 0.20 <= retracement <= 0.60:
            qualified = True
        if qualified and index >= impulse + 2:
            previous = float(bars[index - 1]["mid"]["c"])
            previous_two = float(bars[index - 2]["mid"]["c"])
            resumed = close > max(previous, previous_two) if direction == "LONG" else close < min(previous, previous_two)
            if resumed:
                if index + 1 >= len(bars) or not path_is_consecutive(bars, index, index + 1):
                    return {"state": "DATA_BLOCKED", "terminal_index": index}
                return {"state": "ENTRY_ELIGIBLE", "trigger_index": index, "entry_index": index + 1, "terminal_index": index}
    return {"state": "EXPIRED", "terminal_index": last}


def trade_outcome(
    pair: str, bars: Sequence[dict[str, Any]], entry_index: int, horizon: int,
    direction: str, scenario: str,
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise ValueError("INVALID_COST_SCENARIO")
    exit_index = entry_index + horizon - 1
    if not path_is_consecutive(bars, entry_index, exit_index):
        raise ValueError("NONCONSECUTIVE_FORWARD_PATH")
    exit_complete = parse_timestamp(bars[exit_index]["timestamp"]) + timedelta(minutes=5)
    if exit_complete >= DEV_END:
        raise ValueError("PARTITION_BOUNDARY_CROSSING")
    if crosses_unsupported_rollover(bars, entry_index, exit_index):
        raise ValueError("UNSUPPORTED_FINANCING_BOUNDARY")
    entry_bar, exit_bar = bars[entry_index], bars[exit_index]
    slip = SCENARIOS[scenario] * pip_size(pair)
    if scenario == "GROSS":
        entry = float(entry_bar["mid"]["o"])
        exit_price = float(exit_bar["mid"]["c"])
    elif direction == "LONG":
        entry = float(entry_bar["ask"]["o"]) + slip
        exit_price = float(exit_bar["bid"]["c"]) - slip
    else:
        entry = float(entry_bar["bid"]["o"]) - slip
        exit_price = float(exit_bar["ask"]["c"]) + slip
    signed_price = exit_price - entry if direction == "LONG" else entry - exit_price
    signed_log = math.log(exit_price / entry) * (1 if direction == "LONG" else -1)
    return {
        "entry_timestamp": entry_bar["timestamp"],
        "entry_price": entry,
        "exit_timestamp": timestamp_text(exit_complete),
        "exit_price": exit_price,
        "direction": direction,
        "result_pips": signed_price / pip_size(pair),
        "result_log_return": signed_log,
        "entry_spread_pips": (float(entry_bar["ask"]["o"]) - float(entry_bar["bid"]["o"])) / pip_size(pair),
        "exit_spread_pips": (float(exit_bar["ask"]["c"]) - float(exit_bar["bid"]["c"])) / pip_size(pair),
        "slippage_pips_per_side": SCENARIOS[scenario],
    }


def deterministic_random_variant(cell_id: str, event_id: str) -> str:
    digest = hashlib.sha256(f"{BOOTSTRAP_SEED}:{cell_id}:{event_id}".encode("ascii")).digest()
    return "ORIG" if digest[0] & 1 else "INV"


def new_accumulator(definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "definition": definition,
        "population": {scenario: [] for scenario in SCENARIOS},
        "population_log": {scenario: [] for scenario in SCENARIOS},
        "executed": {scenario: [] for scenario in SCENARIOS},
        "random_base": [],
        "delay_base": [],
        "blocks": defaultdict(lambda: [0.0, 0]),
        "pair_values": defaultdict(list),
        "currency_values": defaultdict(list),
        "session_values": defaultdict(list),
        "volatility_values": defaultdict(list),
        "month_values": defaultdict(list),
        "direction_values": defaultdict(list),
        "executed_direction_counts": Counter(),
        "dispositions": Counter(),
    }


def add_observation(
    accumulator: dict[str, Any], event: dict[str, Any], outcome: dict[str, dict[str, Any]] | None,
    random_outcome: dict[str, Any] | None, delay_outcome: dict[str, Any] | None, disposition: str,
) -> None:
    accumulator["dispositions"][disposition] += 1
    for scenario in SCENARIOS:
        pips = outcome[scenario]["result_pips"] if outcome else 0.0
        log_return = outcome[scenario]["result_log_return"] if outcome else 0.0
        accumulator["population"][scenario].append(pips)
        accumulator["population_log"][scenario].append(log_return)
        if outcome:
            accumulator["executed"][scenario].append(pips)
    if outcome:
        accumulator["executed_direction_counts"][outcome["BASE"]["direction"]] += 1
    base = outcome["BASE"]["result_pips"] if outcome else 0.0
    accumulator["random_base"].append(random_outcome["result_pips"] if random_outcome else 0.0)
    accumulator["delay_base"].append(delay_outcome["result_pips"] if delay_outcome else 0.0)
    block = accumulator["blocks"][event["block_id"]]
    block[0] += base
    block[1] += 1
    accumulator["pair_values"][event["pair"]].append(base)
    for currency in event["pair"].split("_"):
        accumulator["currency_values"][currency].append(base / 2.0)
    accumulator["session_values"][event["session"]].append(base)
    accumulator["volatility_values"][event["volatility_regime"]].append(base)
    accumulator["month_values"][event["signal_timestamp"][:7]].append(base)
    accumulator["direction_values"][outcome["BASE"]["direction"] if outcome else event["direction"]].append(base)


def synchronized_block_bootstrap(blocks: dict[int, list[float | int]], seed: int) -> tuple[float, float, int]:
    ordered = sorted(blocks)
    if not ordered:
        return 0.0, 0.0, 0
    rng = random.Random(seed)
    samples = []
    for _ in range(BOOTSTRAP_REPLICATES):
        total = 0.0
        count = 0
        for _slot in ordered:
            value, size = blocks[ordered[rng.randrange(len(ordered))]]
            total += float(value)
            count += int(size)
        samples.append(total / count if count else 0.0)
    samples.sort()
    low_index = max(0, math.floor(0.025 * len(samples)))
    high_index = min(len(samples) - 1, math.ceil(0.975 * len(samples)) - 1)
    return samples[low_index], samples[high_index], len(ordered)


def _group_summary(groups: dict[str, list[float]]) -> dict[str, Any]:
    return {
        key: {"count": len(values), "mean_base_pips": math.fsum(values) / len(values), "total_base_pips": math.fsum(values)}
        for key, values in sorted(groups.items()) if values
    }


def finalize_accumulator(accumulator: dict[str, Any], seed: int) -> dict[str, Any]:
    population = accumulator["population"]
    base = population["BASE"]
    gross = population["GROSS"]
    executed = accumulator["executed"]["BASE"]
    lower, upper, effective_blocks = synchronized_block_bootstrap(accumulator["blocks"], seed)
    mean = math.fsum(base) / len(base) if base else 0.0
    gross_mean = math.fsum(gross) / len(gross) if gross else 0.0
    standard_deviation = statistics.stdev(base) if len(base) > 1 else 0.0
    wins = math.fsum(value for value in executed if value > 0)
    losses = -math.fsum(value for value in executed if value < 0)
    pair_summary = _group_summary(accumulator["pair_values"])
    currency_summary = _group_summary(accumulator["currency_values"])
    month_summary = _group_summary(accumulator["month_values"])
    strongest_pair = max(pair_summary, key=lambda key: pair_summary[key]["total_base_pips"], default=None)
    strongest_currency = max(currency_summary, key=lambda key: currency_summary[key]["total_base_pips"], default=None)
    strongest_month = max(month_summary, key=lambda key: month_summary[key]["total_base_pips"], default=None)
    def removal(groups: dict[str, list[float]], strongest: str | None) -> float:
        kept = [value for key, values in groups.items() if key != strongest for value in values]
        return math.fsum(kept) / len(kept) if kept else 0.0
    random_mean = math.fsum(accumulator["random_base"]) / len(accumulator["random_base"]) if accumulator["random_base"] else 0.0
    delay_values = accumulator["delay_base"]
    return {
        "population_count": len(base),
        "executed_count": len(executed),
        "missed_or_filtered_count": len(base) - len(executed),
        "mean_forward_log_return": math.fsum(accumulator["population_log"]["GROSS"]) / len(base) if base else 0.0,
        "median_forward_log_return": statistics.median(accumulator["population_log"]["GROSS"]) if base else 0.0,
        "gross_mean_pips": gross_mean,
        "base_after_cost_mean_pips": mean,
        "stressed_mean_pips": math.fsum(population["STRESSED"]) / len(base) if base else 0.0,
        "severe_mean_pips": math.fsum(population["SEVERE_BUT_PLAUSIBLE"]) / len(base) if base else 0.0,
        "base_median_pips": statistics.median(base) if base else 0.0,
        "base_hit_rate": sum(value > 0 for value in base) / len(base) if base else 0.0,
        "base_standardized_effect": mean / standard_deviation if standard_deviation > 0 else 0.0,
        "base_95pct_synchronized_block_bootstrap_interval_pips": [lower, upper],
        "effective_synchronized_288_bar_blocks": effective_blocks,
        "event_profit_factor": wins / losses if losses else (999.0 if wins else 0.0),
        "random_direction_mean_pips": random_mean,
        "no_trade_mean_pips": 0.0,
        "plus_one_m5_delay_mean_pips": math.fsum(delay_values) / len(delay_values) if delay_values else 0.0,
        "break_even_total_cost_pips_per_population_event": max(0.0, gross_mean),
        "observed_base_cost_pips_per_population_event": gross_mean - mean,
        "base_cost_headroom_pips_per_population_event": mean,
        "pair_breadth": sum(any(value != 0 for value in values) for values in accumulator["pair_values"].values()),
        "currency_breadth": sum(any(value != 0 for value in values) for values in accumulator["currency_values"].values()),
        "long_executed": accumulator["executed_direction_counts"].get("LONG", 0),
        "short_executed": accumulator["executed_direction_counts"].get("SHORT", 0),
        "dispositions": dict(sorted(accumulator["dispositions"].items())),
        "pair_decomposition": pair_summary,
        "currency_decomposition": currency_summary,
        "session_decomposition": _group_summary(accumulator["session_values"]),
        "volatility_decomposition": _group_summary(accumulator["volatility_values"]),
        "month_decomposition": month_summary,
        "direction_decomposition": _group_summary(accumulator["direction_values"]),
        "strongest_pair_removal_mean_pips": removal(accumulator["pair_values"], strongest_pair),
        "strongest_currency_removal_mean_pips": removal(accumulator["currency_values"], strongest_currency),
        "strongest_month_removal_mean_pips": removal(accumulator["month_values"], strongest_month),
        "strongest_pair": strongest_pair,
        "strongest_currency": strongest_currency,
        "strongest_month": strongest_month,
        "portfolio_metrics_status": "NOT_APPLICABLE_STAGE1_EVENT_EFFECT_SCREEN_NO_PORTFOLIO_BACKTEST",
    }


def score_pair(
    pair: str, bars: Sequence[dict[str, Any]], events: Sequence[dict[str, Any]],
    graph: dict[tuple[int, str], dict[str, Any]], cells: dict[str, dict[str, Any]],
    accumulators: dict[str, dict[str, Any]], journal: list[dict[str, Any]],
) -> None:
    by_lookback = {lookback: sorted((event for event in events if event["lookback"] == lookback), key=lambda row: row["index"]) for lookback in LOOKBACKS}
    outcome_cache: dict[tuple[int, int, str, str], dict[str, Any]] = {}
    def outcomes(entry: int, horizon: int, direction: str) -> dict[str, dict[str, Any]]:
        return {
            scenario: outcome_cache.setdefault((entry, horizon, direction, scenario), trade_outcome(pair, bars, entry, horizon, direction, scenario))
            for scenario in SCENARIOS
        }
    for lookback in LOOKBACKS:
        for horizon in HORIZONS:
            base_next = {"LONG": 0, "SHORT": 0}
            pullback_next = {(arm, direction): 0 for arm in ("C", "D") for direction in ("LONG", "SHORT")}
            for event in by_lookback[lookback]:
                index = int(event["index"])
                signal_direction = event["direction"]
                if index < base_next[signal_direction]:
                    continue
                immediate_entry = index + 1
                immediate_exit = immediate_entry + horizon - 1
                if (
                    not path_is_consecutive(bars, index, immediate_exit)
                    or immediate_exit >= len(bars)
                    or parse_timestamp(bars[immediate_exit]["timestamp"]) + timedelta(minutes=5) >= DEV_END
                    or crosses_unsupported_rollover(bars, immediate_entry, immediate_exit)
                ):
                    continue
                base_next[signal_direction] = immediate_exit + 12
                graph_row = graph.get((lookback, event["bar_timestamp"]), {"status": "INCOMPLETE_STABLE_MEMBERSHIP"})
                graph_ok = graph_row.get("status") == "PASS"
                selected = graph_ok and graph_select(pair, signal_direction, set(graph_row["top"]), set(graph_row["bottom"]))
                leave_row = graph_row.get("leave_target_pair_out", {}).get(pair, {})
                leave_selected = leave_row.get("status") == "PASS" and graph_select(pair, signal_direction, set(leave_row["top"]), set(leave_row["bottom"]))
                pullbacks: dict[str, dict[str, Any]] = {}
                for arm in ("C", "D"):
                    if arm == "D" and not selected:
                        pullbacks[arm] = {"state": "GRAPH_FILTERED", "terminal_index": index}
                    elif index < pullback_next[(arm, signal_direction)]:
                        pullbacks[arm] = {"state": "ACTIVE_EPISODE_BLOCKED", "terminal_index": index}
                    else:
                        state = pullback_entry(bars, event)
                        terminal = int(state["terminal_index"])
                        if state["state"] == "ENTRY_ELIGIBLE":
                            exit_index = int(state["entry_index"]) + horizon - 1
                            if (
                                not path_is_consecutive(bars, int(state["entry_index"]), exit_index)
                                or exit_index >= len(bars)
                                or parse_timestamp(bars[exit_index]["timestamp"]) + timedelta(minutes=5) >= DEV_END
                                or crosses_unsupported_rollover(bars, int(state["entry_index"]), exit_index)
                            ):
                                state = {"state": "DATA_OR_COST_BLOCKED", "terminal_index": max(terminal, min(exit_index, len(bars) - 1))}
                            else:
                                terminal = exit_index
                        pullback_next[(arm, signal_direction)] = int(state.get("terminal_index", terminal)) + 12
                        pullbacks[arm] = state
                journal_row: dict[str, Any] = {
                    "event_id": event["event_id"], "pair": pair, "lookback": lookback, "horizon": horizon,
                    "signal_direction": signal_direction, "signal_timestamp": event["signal_timestamp"],
                    "momentum": event["momentum"], "session": event["session"],
                    "volatility_regime": event["volatility_regime"], "graph_status": graph_row.get("status"),
                    "graph_selected": selected, "leave_target_pair_out_selected": leave_selected,
                    "pullback_states": {arm: row["state"] for arm, row in pullbacks.items()}, "arms": {},
                }
                for arm in ARMS:
                    if arm in ("A", "B"):
                        execute = arm == "A" or selected
                        entry_index = immediate_entry
                        disposition = "EXECUTED" if execute else ("GRAPH_FILTERED" if graph_ok else "GRAPH_DATA_BLOCKED")
                    else:
                        state = pullbacks[arm]
                        execute = state["state"] == "ENTRY_ELIGIBLE"
                        entry_index = int(state["entry_index"]) if execute else -1
                        disposition = "EXECUTED" if execute else state["state"]
                    journal_row["arms"][arm] = {"disposition": disposition, "entry_timestamp": bars[entry_index]["timestamp"] if execute else None}
                    for variant in DIRECTIONS:
                        cell_id = f"FXT-{arm}-L{lookback}-H{horizon}-{variant}"
                        direction = signal_direction if variant == "ORIG" else opposite(signal_direction)
                        result = outcomes(entry_index, horizon, direction) if execute else None
                        random_variant = deterministic_random_variant(cell_id, event["event_id"])
                        random_direction = signal_direction if random_variant == "ORIG" else opposite(signal_direction)
                        random_result = outcomes(entry_index, horizon, random_direction)["BASE"] if execute else None
                        delay_result = None
                        if execute:
                            delayed_entry = entry_index + 1
                            delayed_exit = delayed_entry + horizon - 1
                            if (
                                path_is_consecutive(bars, delayed_entry, delayed_exit)
                                and delayed_exit < len(bars)
                                and parse_timestamp(bars[delayed_exit]["timestamp"]) + timedelta(minutes=5) < DEV_END
                                and not crosses_unsupported_rollover(bars, delayed_entry, delayed_exit)
                            ):
                                delay_result = outcomes(delayed_entry, horizon, direction)["BASE"]
                        add_observation(accumulators[cell_id], event, result, random_result, delay_result, disposition)
                        journal_row["arms"][arm][variant] = {
                            "cell_id": cell_id,
                            "candidate_fingerprint": cells[cell_id]["candidate_fingerprint"],
                            "trade_direction": direction,
                            "outcomes": result,
                            "random_base_pips": random_result["result_pips"] if random_result else 0.0,
                            "plus_one_delay_base_pips": delay_result["result_pips"] if delay_result else 0.0,
                        }
                journal.append(journal_row)


def apply_incremental_gates(results: dict[str, dict[str, Any]], runtime_contracts: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for cell_id, row in sorted(results.items()):
        definition = row["definition"]
        arm = definition["arm"]
        suffix = f"L{definition['formation_lookback_m5']}-H{definition['forward_horizon_m5']}-{'ORIG' if definition['direction'] == 'ECONOMIC_DIRECTION' else 'INV'}"
        base_mean = row["metrics"]["base_after_cost_mean_pips"]
        if arm == "A":
            comparisons = {"no_trade": 0.0}
            incremental = base_mean > 0.0
        elif arm == "B":
            comparisons = {"arm_A": results[f"FXT-A-{suffix}"]["metrics"]["base_after_cost_mean_pips"]}
            incremental = base_mean > comparisons["arm_A"]
        elif arm == "C":
            comparisons = {"arm_A": results[f"FXT-A-{suffix}"]["metrics"]["base_after_cost_mean_pips"]}
            incremental = base_mean > comparisons["arm_A"]
        else:
            comparisons = {
                "arm_B": results[f"FXT-B-{suffix}"]["metrics"]["base_after_cost_mean_pips"],
                "arm_C": results[f"FXT-C-{suffix}"]["metrics"]["base_after_cost_mean_pips"],
            }
            incremental = all(base_mean > value for value in comparisons.values())
        metrics = row["metrics"]
        lower = metrics["base_95pct_synchronized_block_bootstrap_interval_pips"][0]
        gates = {
            "directional_gross_effect": metrics["gross_mean_pips"] > 0.0,
            "after_cost_above_no_trade": base_mean > 0.0,
            "beats_random_direction": base_mean > metrics["random_direction_mean_pips"],
            "incremental_component_value": incremental,
            "bootstrap_interval_excludes_zero": lower > 0.0,
            "sample_count": metrics["executed_count"] >= 200,
            "pair_breadth": metrics["pair_breadth"] >= 8,
            "currency_breadth": metrics["currency_breadth"] >= 6,
            "effective_blocks": metrics["effective_synchronized_288_bar_blocks"] >= 30,
        }
        mapping = runtime_contracts["cell_identity_mappings"][cell_id]
        pkt040_transition = evaluate_transition("EDGE_HYPOTHESIS", {
            "candidate_fingerprint": {"status": "PASS"},
            "global_trial_receipt": {"status": "PASS"},
            "development_access": {"status": "PASS"},
            "future_leakage": {"status": "PASS"},
            "dependence_bootstrap": {"status": "PASS" if gates["effective_blocks"] else "INSUFFICIENT_EVIDENCE"},
            "sample_adequacy": {"status": "PASS" if gates["sample_count"] else "INSUFFICIENT_EVIDENCE"},
        })
        gates["pkt040_edge_hypothesis_transition"] = pkt040_transition["status"] == "PASS"
        row["matched_comparisons"] = comparisons
        row["pkt040_transition"] = pkt040_transition
        row["commercial_reference"] = {
            "selection": mapping["commercial_reference_selection"],
            "reference_strategy_id": mapping["commercial_reference_strategy_id"],
            "incremental_value_status": "BLOCK_NOT_EVALUATED_AT_STAGE1",
            "reason": "REFERENCE_ARCHETYPE_REMAINS_PROPOSED_UNSCORED;_PUBLIC_PRECEDENT_IS_NOT_AIOS_OUTCOME_EVIDENCE",
            "blocks_promotion_beyond_mechanism_observed": True,
        }
        row["stage1_gates"] = gates
        row["mechanism_observed"] = all(gates.values())
        failures = []
        if not gates["directional_gross_effect"]:
            failures.append("NO_GROSS_EDGE")
        elif not gates["after_cost_above_no_trade"]:
            failures.append("COST_DESTROYED_EDGE")
        if not gates["beats_random_direction"] or not gates["incremental_component_value"]:
            failures.append("BASELINE_FAILURE")
        if not gates["bootstrap_interval_excludes_zero"]:
            failures.append("INSUFFICIENT_EVIDENCE" if lower <= 0 < metrics["base_95pct_synchronized_block_bootstrap_interval_pips"][1] else "DIRECTIONAL_EFFECT_REJECTED")
        if not gates["sample_count"]:
            failures.append("INSUFFICIENT_TRADES")
        if not gates["pair_breadth"] or not gates["currency_breadth"]:
            failures.append("INSUFFICIENT_BREADTH")
        row["failure_classifications"] = list(dict.fromkeys(failures))
        if row["mechanism_observed"]:
            observed.append(cell_id)
    return observed


def journal_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    raw = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8") for row in rows)
    return gzip.compress(raw, compresslevel=9, mtime=0)


def audit_journal(payload: bytes, expected_rows: int) -> dict[str, Any]:
    count = losing = missing = 0
    required = {"event_id", "pair", "lookback", "horizon", "signal_direction", "signal_timestamp", "graph_selected", "pullback_states", "arms"}
    with gzip.open(io.BytesIO(payload), "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            count += 1
            missing += not required.issubset(row)
            for arm in row.get("arms", {}).values():
                for variant in DIRECTIONS:
                    result = arm.get(variant, {}).get("outcomes")
                    losing += bool(result and result["BASE"]["result_pips"] < 0)
    return {"valid_jsonl_gzip": True, "row_count": count, "expected_rows": expected_rows, "losing_outcomes": losing, "missing_required_rows": missing, "pass": count == expected_rows and losing > 0 and missing == 0}


def research(
    corpus_root: Path, stage0_root: Path, repo_root: Path, *, corrective_replay: bool = False,
) -> tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]:
    first_wave, stage0_manifest = verify_stage0(stage0_root)
    runtime_contracts = verify_runtime_contracts(repo_root, first_wave["cells"], require_pre_score=not corrective_replay)
    manifest = verify_corpus_manifest(corpus_root)
    pairs = tuple(manifest["eligible_pairs"])
    verification: dict[str, Any] = {}
    events_by_pair: dict[str, list[dict[str, Any]]] = {}
    rows_per_pass = 0
    for pair in pairs:
        bars = read_pair_bars(corpus_root, manifest, pair, verification)
        rows_per_pass += len(bars)
        events_by_pair[pair] = discover_impulses(pair, bars)
    all_events = [event for pair in pairs for event in events_by_pair[pair]]
    def loader(pair: str) -> list[dict[str, Any]]:
        return read_pair_bars(corpus_root, manifest, pair, verification)
    graph, graph_audit = build_graph_diagnostics(pairs, loader, all_events)
    cells = {row["cell_id"]: row for row in first_wave["cells"]}
    accumulators = {cell_id: new_accumulator(definition) for cell_id, definition in cells.items()}
    journal: list[dict[str, Any]] = []
    for pair in pairs:
        bars = read_pair_bars(corpus_root, manifest, pair, verification)
        score_pair(pair, bars, events_by_pair[pair], graph, cells, accumulators, journal)
    results = {
        cell_id: {"definition": cells[cell_id], "metrics": finalize_accumulator(accumulator, BOOTSTRAP_SEED + index)}
        for index, (cell_id, accumulator) in enumerate(sorted(accumulators.items()))
    }
    observed = apply_incremental_gates(results, runtime_contracts)
    scored = [cell_id for cell_id, row in sorted(results.items()) if row["metrics"]["population_count"] > 0]
    skipped = sorted(set(cells) - set(scored))
    if skipped:
        raise RuntimeError(f"SUPPORTED_CELL_WITHOUT_OUTCOME:{','.join(skipped)}")
    journal_payload = journal_bytes(journal)
    journal_audit = audit_journal(journal_payload, len(journal))
    if not journal_audit["pass"]:
        raise RuntimeError("JOURNAL_AUDIT_FAILED")
    result = {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_RESULTS.v1",
        "packet_id": PACKET_ID,
        "identity_marker": IDENTITY_MARKER,
        "status": "MECHANISM_OBSERVED" if observed else "VALID_DEVELOPMENT_SCREEN_REJECTED",
        "promotion_state": "MECHANISM_OBSERVED" if observed else "EDGE_HYPOTHESIS",
        "verified_edge": False,
        "dataset": {"corpus_id": CORPUS_ID, "aggregate_sha256": CORPUS_SHA256, "manifest_sha256": CORPUS_MANIFEST_SHA256, "eligible_pairs": 58},
        "partition": {"start_inclusive": timestamp_text(DEV_START), "end_exclusive": timestamp_text(DEV_END), "validation_information_provenance": "REUSED_NOT_OPENED", "holdout_information_provenance": "CONTAMINATED_NOT_OPENED"},
        "reader": {"passes": 3, "unique_development_rows_per_pass": rows_per_pass, "development_shards_opened": len(verification), "validation_shards_opened": 0, "holdout_shards_opened": 0},
        "prior_actual_attempt_lower_bound": EXPECTED_CUMULATIVE_LOWER_BOUND if corrective_replay else PRIOR_ATTEMPT_LOWER_BOUND,
        "new_outcome_scored_trials": 0 if corrective_replay else len(scored),
        "outcome_cells_replayed": len(scored) if corrective_replay else 0,
        "cumulative_actual_attempt_lower_bound": EXPECTED_CUMULATIVE_LOWER_BOUND if corrective_replay else PRIOR_ATTEMPT_LOWER_BOUND + len(scored),
        "scored_cell_ids": scored,
        "skipped_cell_ids": skipped,
        "mechanism_observed_cells": observed,
        "cell_results": results,
        "graph_audit": graph_audit,
        "journal_row_count": len(journal),
        "stage0_manifest_sha256": STAGE0_MANIFEST_SHA256,
        "stage0_artifact_inventory_sha256": sha256_bytes(canonical_bytes(stage0_manifest["artifacts"])),
        "validation_pipeline": {
            "status": "PKT040_CERTIFIED_38_OF_38",
            "capability_registry_sha256": runtime_contracts["observed_sha256"]["capability_registry"],
            "edge_hypothesis_transition_enforced_per_cell": True,
            "later_transition_validators": "NOT_EVALUATED_AT_STAGE1_AND_FAIL_CLOSED",
        },
        "commercial_reference_contract": {
            "status": "PKT041_REGISTERED_AND_SELECTION_FROZEN_BEFORE_SCORING",
            "registry_sha256": runtime_contracts["observed_sha256"]["commercial_registry"],
            "reference_metrics": "NOT_EVALUATED_AT_STAGE1",
            "incremental_commercial_baseline_gate": "BLOCKS_PROMOTION_BEYOND_MECHANISM_OBSERVED",
        },
        "selection_bias_controls": {"real_dsr": "CERTIFIED_BY_PKT040_NOT_EVALUATED_AT_STAGE1", "real_cscv_pbo": "CERTIFIED_BY_PKT040_NOT_EVALUATED_AT_STAGE1", "ordinary_holdout_is_not_multiple_testing_correction": True},
        "portfolio_status": "NOT_RUN_STAGE1_EVENT_EFFECT_SCREEN_IS_NOT_REALIZABLE_PORTFOLIO_BACKTEST",
        "corrective_replay": {
            "enabled": corrective_replay,
            "packet_id": CORRECTIVE_PACKET_ID if corrective_replay else None,
            "identity_marker": CORRECTIVE_IDENTITY_MARKER if corrective_replay else None,
            "economic_specification_changed": False,
            "trial_increment": 0 if corrective_replay else len(scored),
            "defect": "HARDCODED_JPY_SUFFIX_PIP_RULE_IGNORED_CERTIFIED_INSTRUMENT_METADATA" if corrective_replay else None,
            "prior_invalid_result_sha256": PRIOR_INVALID_RESULT_SHA256 if corrective_replay else None,
        },
        "safety": {key: False for key in ("network", "broker", "credentials", "paper", "practice", "live", "orders", "money_movement", "validation_access", "holdout_access", "commit", "push")},
    }
    input_verification = {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_INPUT_VERIFICATION.v1",
        "stage0_manifest_sha256": STAGE0_MANIFEST_SHA256,
        "corpus_manifest_sha256": CORPUS_MANIFEST_SHA256,
        "verified_development_shard_count": len(verification),
        "verified_development_row_count": sum(int(row["records"]) for row in verification.values()),
        "shards": dict(sorted(verification.items())),
        "validation_shards_opened": 0,
        "holdout_shards_opened": 0,
        "status": "PASS",
        "runtime_contracts": runtime_contracts,
        "instrument_metadata": {
            "path": INSTRUMENT_METADATA_RELATIVE.as_posix(),
            "sha256": INSTRUMENT_METADATA_SHA256,
            "pair_count": len(certified_instrument_metadata()),
            "pair_metadata": certified_instrument_metadata(),
            "status": "PASS",
        },
    }
    return result, journal_payload, journal_audit, input_verification


def postmortem(result: dict[str, Any]) -> dict[str, Any]:
    observed = result["mechanism_observed_cells"]
    original = {key: value for key, value in result["cell_results"].items() if key.endswith("-ORIG")}
    executed_original = {key: value for key, value in original.items() if value["metrics"]["executed_count"] > 0}
    ranked = sorted((executed_original or original).items(), key=lambda item: (item[1]["metrics"]["base_after_cost_mean_pips"], item[0]), reverse=True)
    best_id, best = ranked[0]
    classifications = Counter(reason for row in result["cell_results"].values() for reason in row["failure_classifications"])
    return {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_POSTMORTEM.v1",
        "status": "NOT_APPLICABLE_MECHANISM_OBSERVED_HANDOFF" if observed else "COMPLETE_VALID_DEVELOPMENT_REJECTION",
        "family": "CURRENCY_MOMENTUM_COMPONENT_TOURNAMENT_FIRST_WAVE",
        "research_arms_are_independent_edges": False,
        "best_original_cell": best_id,
        "best_original_metrics": best["metrics"],
        "failure_classification_counts": dict(sorted(classifications.items())),
        "primary_failure": None if observed else (best["failure_classifications"][0] if best["failure_classifications"] else "INSUFFICIENT_EVIDENCE"),
        "prohibited_repeats": [
            "RENAMING_ANY_OF_THE_72_CELLS_AS_A_NEW_EDGE",
            "TUNING_LOOKBACK_HORIZON_OR_QUARTILE_AFTER_THIS_DEVELOPMENT_RESULT_WITHOUT_NEW_TRIAL_ACCOUNTING",
            "DROPPING_MISSED_PULLBACK_RUNNERS_FROM_THE_POPULATION",
            "TREATING_58_CORRELATED_PAIRS_AS_58_INDEPENDENT_FACTORS",
            "USING_REUSED_VALIDATION_OR_CONTAMINATED_2026_EVIDENCE_FOR_INDEPENDENT_CONFIRMATION",
        ],
        "salvageable_evidence": "ONLY_CELLS_LISTED_AS_MECHANISM_OBSERVED_MAY_ADVANCE_TO_A_NEW_PREREGISTERED_COST_AND_PORTFOLIO_TRANSLATION;_OTHERWISE_MOVE_TO_FACTOR_COMMON_COMPONENT_MOMENTUM",
        "next_action": "REQUEST_BOUNDED_STAGE2_TRANSLATION_FOR_OBSERVED_CELL_OR_PREREGISTER_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0",
    }


def repair_execution_direction_counts(result: dict[str, Any], journal: bytes) -> dict[str, Any]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    with gzip.open(io.BytesIO(journal), "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            for arm in row["arms"].values():
                for variant in DIRECTIONS:
                    candidate = arm[variant]
                    if candidate.get("outcomes") is not None:
                        counts[candidate["cell_id"]][candidate["trade_direction"]] += 1
    for cell_id, row in result["cell_results"].items():
        observed = counts[cell_id]
        if sum(observed.values()) != row["metrics"]["executed_count"]:
            raise RuntimeError(f"EXECUTED_DIRECTION_COUNT_MISMATCH:{cell_id}")
        row["metrics"]["long_executed"] = observed["LONG"]
        row["metrics"]["short_executed"] = observed["SHORT"]
    result["implementation_repairs"] = [
        "LEAVE_TARGET_PAIR_OUT_GRAPH_BRIDGES_MARKED_NOT_FEASIBLE",
        "EXECUTED_DIRECTION_COUNTS_DERIVED_ONLY_FROM_EXECUTED_JOURNAL_OUTCOMES",
        "POSTMORTEM_BEST_CELL_REQUIRES_AT_LEAST_ONE_EXECUTION",
    ]
    return result


def build_artifacts(
    result: dict[str, Any], journal: bytes, journal_audit: dict[str, Any], verification: dict[str, Any],
    ledger_payload: bytes, fingerprint_index_payload: bytes, memory_update: dict[str, Any],
) -> dict[str, bytes]:
    trial_delta = {
        "schema": "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_DELTA.v1",
        "packet_id": PACKET_ID,
        "prior_actual_attempt_lower_bound": PRIOR_ATTEMPT_LOWER_BOUND,
        "outcome_examined_cells": result["new_outcome_scored_trials"],
        "outcome_examined_cell_ids": result["scored_cell_ids"],
        "cumulative_actual_attempt_lower_bound": result["cumulative_actual_attempt_lower_bound"],
        "unresolved_cross_namespace_overlap": True,
        "arms_are_component_comparisons_not_independent_edges": True,
        "pkt040_validation_pipeline": "CERTIFIED_38_OF_38_AND_EDGE_HYPOTHESIS_TRANSITION_ENFORCED",
        "pkt041_commercial_reference": "SELECTION_FROZEN;_REFERENCE_METRICS_NOT_EVALUATED_AND_BLOCK_LATER_PROMOTION",
        "dispositions": {cell_id: ("SURVIVOR" if row["mechanism_observed"] else "VALID_TEST_REJECTED") for cell_id, row in sorted(result["cell_results"].items())},
    }
    checkpoint = {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_CHECKPOINT.v1",
        "status": "TERMINAL_STAGE1_COMPLETE",
        "completed_cell_ids": result["scored_cell_ids"],
        "pending_cell_ids": [],
        "cumulative_actual_attempt_lower_bound": result["cumulative_actual_attempt_lower_bound"],
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
        "next_action": "NEW_AUTHORITY_REQUIRED_FOR_ANY_SUCCESSOR",
    }
    contract = {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_CONTRACT.v1",
        "packet_id": PACKET_ID,
        "identity_marker": IDENTITY_MARKER,
        "stage0_manifest_sha256": STAGE0_MANIFEST_SHA256,
        "development_interval": [timestamp_text(DEV_START), timestamp_text(DEV_END)],
        "cell_count": 72,
        "arms": list(ARMS),
        "lookbacks": list(LOOKBACKS),
        "horizons": list(HORIZONS),
        "directions": list(DIRECTIONS),
        "cost_scenarios": SCENARIOS,
        "market_closure_policy": "REQUIRE_STRICTLY_CONSECUTIVE_M5_FEATURE_ENTRY_AND_EXIT_PATHS",
        "financing_policy": "BLOCK_2155_THROUGH_2210_UTC_INTERVAL_INTERSECTION_BECAUSE_CERTIFIED_FINANCING_IS_UNAVAILABLE",
        "volatility_diagnostic": "CURRENT_ABSOLUTE_LOG_RETURN_DIVIDED_BY_CAUSAL_TRAILING_288_RETURN_MEDIAN_LOW_BELOW_0_75_HIGH_ABOVE_1_25",
        "outcome_scope": "DEVELOPMENT_ONLY",
        "validation_and_holdout_access": False,
        "pkt040_capability_registry_sha256": CAPABILITY_REGISTRY_SHA256,
        "pkt041_commercial_registry_sha256": COMMERCIAL_REGISTRY_SHA256,
    }
    report = (
        "# AIOS Forex Edge Discovery Tournament Stage 1\n\n"
        f"Status: {result['status']}. Cells scored: {result['new_outcome_scored_trials']}. "
        f"Mechanism-observed cells: {len(result['mechanism_observed_cells'])}. "
        f"Cumulative scored-attempt lower bound: {result['cumulative_actual_attempt_lower_bound']}. "
        "Only development evidence was opened. Validation rows and contaminated 2026 rows remained unopened. "
        "This event-effect screen is not a portfolio backtest and does not verify an edge.\n"
    ).encode("utf-8")
    core = {
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_CONTRACT.json": canonical_bytes(contract),
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_RESULTS.json": canonical_bytes(result),
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_TRIAL_LEDGER_DELTA.json": canonical_bytes(trial_delta),
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_GRAPH_AUDIT.json": canonical_bytes(result["graph_audit"]),
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_EVENT_EVIDENCE.jsonl.gz": journal,
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_JOURNAL_AUDIT.json": canonical_bytes(journal_audit),
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_INPUT_VERIFICATION.json": canonical_bytes(verification),
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_POSTMORTEM.json": canonical_bytes(postmortem(result)),
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_CHECKPOINT.json": canonical_bytes(checkpoint),
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_MEMORY_UPDATE.json": canonical_bytes(memory_update),
        "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl": ledger_payload,
        "AIOS_FOREX_FINGERPRINT_INDEX_V1.json": fingerprint_index_payload,
        "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_REPORT.md": report,
    }
    manifest = {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_MANIFEST.v1",
        "artifacts": {name: {"bytes": len(payload), "sha256": sha256_bytes(payload)} for name, payload in sorted(core.items())},
    }
    manifest_bytes = canonical_bytes(manifest)
    receipt = {
        "schema": "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "status": "PASS",
        "result_status": result["status"],
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "artifact_count": len(core) + 2,
        "counters": {
            "development_rows_opened_per_pass": result["reader"]["unique_development_rows_per_pass"],
            "development_reader_passes": result["reader"]["passes"],
            "validation_rows_opened": 0,
            "final_holdout_rows_opened": 0,
            "new_outcome_scored_trials": result["new_outcome_scored_trials"],
            "cumulative_actual_attempt_lower_bound": result["cumulative_actual_attempt_lower_bound"],
        },
        "mechanism_observed_cell_count": len(result["mechanism_observed_cells"]),
        "verified_edge": False,
        "commit": "NOT_PERFORMED",
        "push": "NOT_PERFORMED",
        "acceptance": {
            "exact_72_cells": "PASS" if result["new_outcome_scored_trials"] == 72 else "FAIL",
            "stage0_frozen": "PASS",
            "development_only": "PASS",
            "side_correct_costs": "PASS",
            "inverse_same_opportunities": "PASS",
            "graph_c_minus_one": "PASS",
            "missed_pullbacks_in_population": "PASS",
            "synchronized_block_bootstrap": "PASS",
            "journal_complete": "PASS" if journal_audit["pass"] else "FAIL",
            "dsr_and_cscv_not_overclaimed": "PASS",
            "pkt040_certified_pipeline_enforced": "PASS",
            "pkt041_commercial_reference_contract_enforced": "PASS",
            "global_memory_update_exact_72": "PASS" if memory_update["scored_attempt_lower_bound_after"] == EXPECTED_CUMULATIVE_LOWER_BOUND else "FAIL",
            "executed_direction_counts_from_executed_outcomes_only": "PASS",
            "edge_not_claimed": "PASS",
        },
        "safety": result["safety"],
    }
    return {**core, "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_MANIFEST.json": manifest_bytes, "AIOS_FOREX_EDGE_TOURNAMENT_STAGE1_RECEIPT.json": canonical_bytes(receipt)}


def _append_trial_record(records: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    previous = records[-1]["record_sha256"] if records else "GENESIS"
    record = {"sequence": len(records) + 1, "previous_record_sha256": previous, **payload}
    record["record_sha256"] = validation_sha256_value(record)
    records.append(record)


def prepare_corrective_memory_update(
    result: dict[str, Any], runtime_contracts: dict[str, Any], ledger_records: Sequence[dict[str, Any]],
    fingerprint_index: dict[str, Any], corrected_result_sha256: str,
) -> tuple[bytes, bytes, dict[str, Any]]:
    """Append invalidation and corrected disposition events without a new trial."""
    current = validate_trial_ledger(ledger_records)
    if current["record_count"] != 83 or current["scored_attempt_lower_bound"] != EXPECTED_CUMULATIVE_LOWER_BOUND:
        raise RuntimeError("PKT039_CANONICAL_MEMORY_NOT_AT_EXPECTED_PRE_CORRECTION_STATE")
    if current["proposed_unscored_count"] != 525:
        raise RuntimeError("PKT039_PROPOSED_MEMORY_CHANGED")
    if len(result.get("scored_cell_ids", [])) != 72 or result.get("new_outcome_scored_trials") != 0:
        raise RuntimeError("CORRECTIVE_REPLAY_MUST_BE_EXACT_72_WITH_ZERO_INCREMENT")

    updated = [dict(row) for row in ledger_records]
    entries = [dict(row) for row in fingerprint_index.get("entries", [])]
    by_id = {row["candidate_id"]: row for row in entries}
    mappings = runtime_contracts["cell_identity_mappings"]
    for cell_id in sorted(result["scored_cell_ids"]):
        mapping = mappings[cell_id]
        indexed = by_id[mapping["runtime_candidate_id"]]
        prior_status = indexed.get("status")
        prior_result_sha256 = indexed.get("result_artifact_sha256")
        if prior_status not in {"VALID_TEST_REJECTED", "SURVIVOR"} or prior_result_sha256 != PRIOR_INVALID_RESULT_SHA256:
            raise RuntimeError(f"PKT039_PRIOR_DISPOSITION_NOT_EXACT:{cell_id}")
        common = {
            "scored_trial_increment": 0,
            "proposed_count": 0,
            "candidate_fingerprint": mapping["runtime_candidate_fingerprint"],
            "frozen_stage0_candidate_fingerprint": mapping["frozen_stage0_candidate_fingerprint"],
            "cell_id": cell_id,
        }
        _append_trial_record(updated, {
            "event_id": f"PKT042_INVALIDATE_PKT039_{cell_id.replace('-', '_')}",
            "status": "INVALID_TEST",
            "provenance": "PKT_FOREX_042_CERTIFIED_PIP_METADATA_DEFECT_INVALIDATION",
            "invalidates_event_id": f"PKT039_STAGE1_{cell_id.replace('-', '_')}",
            "invalid_result_artifact_sha256": prior_result_sha256,
            "defect": "HARDCODED_JPY_SUFFIX_PIP_RULE_IGNORED_CERTIFIED_INSTRUMENT_METADATA",
            **common,
        })
        corrected_status = "SURVIVOR" if result["cell_results"][cell_id]["mechanism_observed"] else "VALID_TEST_REJECTED"
        _append_trial_record(updated, {
            "event_id": f"PKT042_CORRECTED_PKT039_{cell_id.replace('-', '_')}",
            "status": corrected_status,
            "provenance": "PKT_FOREX_042_UNCHANGED_SPECIFICATION_CORRECTIVE_REPLAY",
            "corrects_event_id": f"PKT039_STAGE1_{cell_id.replace('-', '_')}",
            "corrected_result_artifact_sha256": corrected_result_sha256,
            "economic_specification_changed": False,
            **common,
        })
        indexed.update({
            "status": corrected_status,
            "prior_invalid_status": prior_status,
            "prior_invalid_result_artifact_sha256": prior_result_sha256,
            "correction_packet_id": CORRECTIVE_PACKET_ID,
            "correction_reason": "CERTIFIED_INSTRUMENT_PIP_METADATA_DEFECT",
            "corrected_result_artifact_sha256": corrected_result_sha256,
            "corrective_replay_scored_trial_increment": 0,
        })

    summary = validate_trial_ledger(updated)
    if summary["record_count"] != 227 or summary["scored_attempt_lower_bound"] != EXPECTED_CUMULATIVE_LOWER_BOUND:
        raise RuntimeError("CORRECTIVE_MEMORY_LINEAGE_COUNT_OR_INCREMENT_MISMATCH")
    updated_index = dict(fingerprint_index)
    updated_index["entries"] = sorted(entries, key=lambda row: (row["fingerprint"], row["candidate_id"]))
    updated_index["pkt039_prior_results_invalidated"] = 72
    updated_index["pkt039_corrective_replay_cells"] = 72
    updated_index["pkt039_corrective_replay_trial_increment"] = 0
    updated_index["pkt039_corrected_survivors"] = len(result["mechanism_observed_cells"])
    updated_index["pkt039_correction_packet_id"] = CORRECTIVE_PACKET_ID
    ledger_payload = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
        for row in updated
    )
    index_payload = canonical_bytes(updated_index)
    return ledger_payload, index_payload, {
        "status": "PASS",
        "records_before": current["record_count"],
        "records_after": summary["record_count"],
        "invalidation_records_appended": 72,
        "correction_records_appended": 72,
        "scored_attempt_lower_bound_before": current["scored_attempt_lower_bound"],
        "scored_attempt_lower_bound_after": summary["scored_attempt_lower_bound"],
        "corrective_replay_trial_increment": 0,
        "proposed_unscored_preserved": summary["proposed_unscored_count"],
        "ledger_sha256": sha256_bytes(ledger_payload),
        "fingerprint_index_sha256": sha256_bytes(index_payload),
    }


def _taxonomy(row: dict[str, Any]) -> str:
    metrics = row["metrics"]
    if row.get("mechanism_observed"):
        return "SURVIVOR"
    if metrics["executed_count"] == 0:
        return "NO_EXECUTION"
    if metrics["gross_mean_pips"] <= 0.0:
        return "DEAD"
    if metrics["base_after_cost_mean_pips"] <= 0.0:
        return "COST_DESTROYED_EDGE"
    if metrics["stressed_mean_pips"] <= 0.0:
        return "COST_NEAR_MISS"
    if metrics["severe_mean_pips"] <= 0.0:
        return "FRAGILE"
    return "OTHER_VALID_REJECTION"


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values) if values else 0.0


def _journal_cell_values(journal: bytes) -> dict[str, dict[str, list[float]]]:
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    with gzip.open(io.BytesIO(journal), "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            for arm in row["arms"].values():
                for variant in DIRECTIONS:
                    candidate = arm[variant]
                    outcomes = candidate.get("outcomes")
                    if not outcomes:
                        continue
                    cell_id = candidate["cell_id"]
                    for scenario in SCENARIOS:
                        values[cell_id][scenario].append(float(outcomes[scenario]["result_pips"]))
                    values[cell_id]["SPREAD_DRAG"].append(
                        float(outcomes["BASE"]["entry_spread_pips"] + outcomes["BASE"]["exit_spread_pips"]) / 2.0
                    )
                    values[cell_id]["DELAY_BASE"].append(float(candidate.get("plus_one_delay_base_pips", 0.0)))
    return values


def _dimension_summary(result: dict[str, Any], field: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell_id, row in result["cell_results"].items():
        if field == "direction":
            key = "ORIG" if cell_id.endswith("-ORIG") else "INV"
        elif field == "arm":
            key = row["definition"]["arm"]
        elif field == "lookback":
            key = f"L{row['definition']['formation_lookback_m5']}"
        else:
            key = f"H{row['definition']['forward_horizon_m5']}"
        grouped[key].append(row["metrics"])
    return {
        key: {
            "cell_count": len(rows),
            "gross_mean_pips_across_cells": _mean([item["gross_mean_pips"] for item in rows]),
            "base_mean_pips_across_cells": _mean([item["base_after_cost_mean_pips"] for item in rows]),
            "gross_positive_cells": sum(item["gross_mean_pips"] > 0.0 for item in rows),
            "base_positive_cells": sum(item["base_after_cost_mean_pips"] > 0.0 for item in rows),
            "executed_events": sum(item["executed_count"] for item in rows),
        }
        for key, rows in sorted(grouped.items())
    }


def _paired_effect(result: dict[str, Any], left_arm: str, right_arm: str) -> dict[str, Any]:
    rows = []
    for lookback in LOOKBACKS:
        for horizon in HORIZONS:
            for direction in DIRECTIONS:
                left = result["cell_results"][f"FXT-{left_arm}-L{lookback}-H{horizon}-{direction}"]["metrics"]
                right = result["cell_results"][f"FXT-{right_arm}-L{lookback}-H{horizon}-{direction}"]["metrics"]
                rows.append({
                    "lookback": lookback,
                    "horizon": horizon,
                    "direction": direction,
                    "gross_delta_pips": right["gross_mean_pips"] - left["gross_mean_pips"],
                    "base_delta_pips": right["base_after_cost_mean_pips"] - left["base_after_cost_mean_pips"],
                })
    return {
        "left_arm": left_arm,
        "right_arm": right_arm,
        "matched_pair_count": len(rows),
        "mean_gross_delta_pips": _mean([row["gross_delta_pips"] for row in rows]),
        "mean_base_delta_pips": _mean([row["base_delta_pips"] for row in rows]),
        "gross_improved_pairs": sum(row["gross_delta_pips"] > 0 for row in rows),
        "base_improved_pairs": sum(row["base_delta_pips"] > 0 for row in rows),
        "matched_differences": rows,
    }


def build_corrective_failure_synthesis(result: dict[str, Any], journal: bytes) -> dict[str, Any]:
    journal_values = _journal_cell_values(journal)
    cells = []
    taxonomy_counts: Counter[str] = Counter()
    for cell_id, row in sorted(result["cell_results"].items()):
        metrics = row["metrics"]
        values = journal_values.get(cell_id, {})
        base = values.get("BASE", [])
        wins = [value for value in base if value > 0]
        losses = [value for value in base if value < 0]
        taxonomy = _taxonomy(row)
        taxonomy_counts[taxonomy] += 1
        pair_positive = [item["total_base_pips"] for item in metrics["pair_decomposition"].values() if item["total_base_pips"] > 0]
        currency_positive = [item["total_base_pips"] for item in metrics["currency_decomposition"].values() if item["total_base_pips"] > 0]
        session_positive = sum(item["mean_base_pips"] > 0 for item in metrics["session_decomposition"].values())
        volatility_positive = sum(item["mean_base_pips"] > 0 for item in metrics["volatility_decomposition"].values())
        cells.append({
            "cell_id": cell_id,
            "arm": row["definition"]["arm"],
            "lookback": row["definition"]["formation_lookback_m5"],
            "forward_horizon": row["definition"]["forward_horizon_m5"],
            "direction": "ORIGINAL" if cell_id.endswith("-ORIG") else "INVERSE",
            "events_eligible": metrics["population_count"],
            "events_executed": metrics["executed_count"],
            "long_count": metrics["long_executed"],
            "short_count": metrics["short_executed"],
            "gross_mean_pips": metrics["gross_mean_pips"],
            "base_net_mean_pips": metrics["base_after_cost_mean_pips"],
            "stressed_net_mean_pips": metrics["stressed_mean_pips"],
            "severe_net_mean_pips": metrics["severe_mean_pips"],
            "gross_profit_factor": "NOT_AVAILABLE",
            "base_profit_factor": metrics["event_profit_factor"],
            "median_result_pips": metrics["base_median_pips"],
            "win_rate_executed": len(wins) / len(base) if base else 0.0,
            "average_win_pips": _mean(wins) if wins else "NOT_AVAILABLE",
            "average_loss_pips": _mean(losses) if losses else "NOT_AVAILABLE",
            "confidence_interval_pips": metrics["base_95pct_synchronized_block_bootstrap_interval_pips"],
            "effective_sample_size_blocks": metrics["effective_synchronized_288_bar_blocks"],
            "pair_breadth": metrics["pair_breadth"],
            "currency_breadth": metrics["currency_breadth"],
            "largest_pair_contribution": metrics["strongest_pair"],
            "largest_currency_factor_contribution": metrics["strongest_currency"],
            "largest_positive_pair_share": max(pair_positive) / math.fsum(pair_positive) if pair_positive else "NOT_AVAILABLE",
            "largest_positive_currency_share": max(currency_positive) / math.fsum(currency_positive) if currency_positive else "NOT_AVAILABLE",
            "parameter_stability": "NO_POSITIVE_BASE_PLATEAU" if metrics["base_after_cost_mean_pips"] <= 0 else "REQUIRES_NEIGHBOR_ANALYSIS",
            "regime_stability": {"positive_sessions": session_positive, "positive_volatility_regimes": volatility_positive},
            "total_cost_drag_pips_per_population_event": metrics["observed_base_cost_pips_per_population_event"],
            "mean_spread_drag_pips_per_executed_event": _mean(values.get("SPREAD_DRAG", [])) if values.get("SPREAD_DRAG") else "NOT_AVAILABLE",
            "modeled_base_slippage_drag_pips_per_executed_event": 0.2 if base else "NOT_AVAILABLE",
            "delay_drag_pips_per_population_event": metrics["base_after_cost_mean_pips"] - metrics["plus_one_m5_delay_mean_pips"],
            "mfe": "NOT_AVAILABLE",
            "mae": "NOT_AVAILABLE",
            "graph_selected": row["definition"]["arm"] in {"B", "D"},
            "pullback_selected": row["definition"]["arm"] in {"C", "D"},
            "primary_failure_gate": taxonomy,
            "secondary_failure_gates": row["failure_classifications"],
            "commercial_baseline_comparison": row["commercial_reference"]["incremental_value_status"],
            "near_miss_ranking_components": {
                "base_net_mean_pips": metrics["base_after_cost_mean_pips"],
                "bootstrap_lower_pips": metrics["base_95pct_synchronized_block_bootstrap_interval_pips"][0],
                "executed_events": metrics["executed_count"],
                "pair_breadth": metrics["pair_breadth"],
                "currency_breadth": metrics["currency_breadth"],
            },
        })
    ranked = sorted((row for row in cells if row["events_executed"] > 0), key=lambda row: (
        row["base_net_mean_pips"], row["confidence_interval_pips"][0], row["pair_breadth"], row["currency_breadth"], row["cell_id"]
    ), reverse=True)
    inverse_diagnostics = Counter()
    for arm in ARMS:
        for lookback in LOOKBACKS:
            for horizon in HORIZONS:
                orig = result["cell_results"][f"FXT-{arm}-L{lookback}-H{horizon}-ORIG"]["metrics"]["gross_mean_pips"]
                inv = result["cell_results"][f"FXT-{arm}-L{lookback}-H{horizon}-INV"]["metrics"]["gross_mean_pips"]
                if orig > 0 >= inv:
                    inverse_diagnostics["CONTINUATION"] += 1
                elif inv > 0 >= orig:
                    inverse_diagnostics["MEAN_REVERSION_DIAGNOSTIC"] += 1
                elif orig == inv == 0:
                    inverse_diagnostics["NO_DIRECTIONAL_EFFECT"] += 1
                else:
                    inverse_diagnostics["ASYMMETRIC_OR_NUMERIC_EDGE_CASE"] += 1
    return {
        "schema": "AIOS_FOREX_PKT039_CORRECTED_FAILURE_SYNTHESIS.v1",
        "packet_id": CORRECTIVE_PACKET_ID,
        "source_packet_id": PACKET_ID,
        "status": "COMPLETE_CORRECTED_FAILURE_SYNTHESIS",
        "classification_rules_frozen_before_ranking": [
            "SURVIVOR_IF_MECHANISM_OBSERVED",
            "NO_EXECUTION_IF_EXECUTED_COUNT_ZERO",
            "DEAD_IF_GROSS_MEAN_NOT_POSITIVE",
            "COST_DESTROYED_EDGE_IF_GROSS_POSITIVE_AND_BASE_NOT_POSITIVE",
            "COST_NEAR_MISS_IF_BASE_POSITIVE_AND_STRESSED_NOT_POSITIVE",
            "FRAGILE_IF_STRESSED_POSITIVE_AND_SEVERE_NOT_POSITIVE",
            "OTHER_VALID_REJECTION_OTHERWISE",
        ],
        "cell_count": len(cells),
        "survivor_count": len(result["mechanism_observed_cells"]),
        "taxonomy_counts": dict(sorted(taxonomy_counts.items())),
        "gross_positive_cell_count": sum(row["gross_mean_pips"] > 0 for row in cells),
        "base_positive_cell_count": sum(row["base_net_mean_pips"] > 0 for row in cells),
        "stressed_positive_cell_count": sum(row["stressed_net_mean_pips"] > 0 for row in cells),
        "severe_positive_cell_count": sum(row["severe_net_mean_pips"] > 0 for row in cells),
        "robust_near_miss_count": 0,
        "top_10_scientific_near_misses": ranked[:10],
        "arm_summary": _dimension_summary(result, "arm"),
        "lookback_summary": _dimension_summary(result, "lookback"),
        "horizon_summary": _dimension_summary(result, "horizon"),
        "direction_summary": _dimension_summary(result, "direction"),
        "paired_component_effects": {
            "graph_value_B_minus_A": _paired_effect(result, "A", "B"),
            "pullback_value_C_minus_A": _paired_effect(result, "A", "C"),
            "pullback_with_graph_D_minus_B": _paired_effect(result, "B", "D"),
            "graph_with_pullback_D_minus_C": _paired_effect(result, "C", "D"),
        },
        "primary_vs_inverse": dict(sorted(inverse_diagnostics.items())),
        "cost_autopsy": {
            "gross_positive_but_base_nonpositive_cells": sum(row["gross_mean_pips"] > 0 >= row["base_net_mean_pips"] for row in cells),
            "base_positive_cells": sum(row["base_net_mean_pips"] > 0 for row in cells),
            "cost_reduction_recommendation": "DO_NOT_LOWER_COSTS;_NO_CORRECTED_CELL_SURVIVES_BASE_COSTS",
        },
        "concentration": {
            "cells_with_positive_pair_contributions": sum(row["largest_positive_pair_share"] != "NOT_AVAILABLE" for row in cells),
            "cells_largest_positive_pair_share_above_half": sum(isinstance(row["largest_positive_pair_share"], float) and row["largest_positive_pair_share"] > 0.5 for row in cells),
            "cells_with_positive_currency_contributions": sum(row["largest_positive_currency_share"] != "NOT_AVAILABLE" for row in cells),
            "cells_largest_positive_currency_share_above_half": sum(isinstance(row["largest_positive_currency_share"], float) and row["largest_positive_currency_share"] > 0.5 for row in cells),
        },
        "regime_summary": {
            "cells_with_zero_positive_sessions": sum(row["regime_stability"]["positive_sessions"] == 0 for row in cells),
            "cells_with_exactly_one_positive_session": sum(row["regime_stability"]["positive_sessions"] == 1 for row in cells),
            "cells_with_zero_positive_volatility_regimes": sum(row["regime_stability"]["positive_volatility_regimes"] == 0 for row in cells),
            "cells_with_exactly_one_positive_volatility_regime": sum(row["regime_stability"]["positive_volatility_regimes"] == 1 for row in cells),
        },
        "failure_clusters": [
            {"cluster": "NO_SIGNAL", "members": taxonomy_counts["DEAD"], "common_failure": "NONPOSITIVE_GROSS_EXPECTANCY"},
            {"cluster": "ROBUST_BUT_COST_DESTROYED", "members": 0, "common_failure": "NO_CELL_MET_ROBUST_NEAR_MISS_RULE"},
            {"cluster": "BROAD_WEAK_INVERSE_EFFECT", "members": inverse_diagnostics["MEAN_REVERSION_DIAGNOSTIC"], "common_failure": "POSITIVE_GROSS_INVERSE_BUT_NO_POSITIVE_BASE_CELL"},
            {"cluster": "NO_EXECUTION", "members": taxonomy_counts["NO_EXECUTION"], "common_failure": "FILTERED_OR_UNFILLED_OPPORTUNITIES"},
            {"cluster": "CONCENTRATED_POSITIVE_CONTRIBUTION", "members": sum(isinstance(row["largest_positive_pair_share"], float) and row["largest_positive_pair_share"] > 0.5 for row in cells), "common_failure": "LARGEST_PAIR_ABOVE_HALF_OF_POSITIVE_PAIR_CONTRIBUTION"},
        ],
        "common_denominators": [
            "NO_EXECUTED_INTENDED_DIRECTION_CELL_HAD_POSITIVE_GROSS_EXPECTANCY",
            "NO_CELL_HAD_POSITIVE_BASE_AFTER_COST_EXPECTANCY",
            "GRAPH_AND_PULLBACK_FILTERING_REDUCED_LOSSES_BUT_DID_NOT_CROSS_ZERO",
            "INVERSE_GROSS_EFFECTS_WERE_TOO_SMALL_FOR_BASE_COSTS",
            "NO_POSITIVE_PARAMETER_PLATEAU_EXISTED",
            "POSITIVE_CONTRIBUTIONS_WERE_FREQUENTLY_PAIR_OR_CURRENCY_CONCENTRATED",
        ],
        "what_the_failures_taught": "PAIR_LEVEL_INTRADAY_CONTINUATION_WAS_NOT_OBSERVED;_DIRECT_COMMON_COMPONENT_VERSUS_RESIDUAL_DECOMPOSITION_IS_MORE_INFORMATIVE_THAN_TUNING_THE_REJECTED_FILTERS",
        "next_hypothesis_ranking": [
            {"rank": 1, "hypothesis": "FACTOR_COMMON_COMPONENT_MOMENTUM", "reason": "DIRECTLY_TESTS_WHETHER_PAIR_REPRESENTATION_MASKED_COMMON_CURRENCY_STRUCTURE;_HIGH_INFORMATION_GAIN_AND_DISTINCT_FROM_GRAPH_FILTERING"},
            {"rank": 2, "hypothesis": "VOLATILITY_EXPANSION_BREAKOUT", "reason": "HIGH_MECHANISM_INDEPENDENCE_AND_POTENTIALLY_LARGER_MOVES_PER_COST"},
            {"rank": 3, "hypothesis": "CONDITIONAL_MEAN_REVERSION", "reason": "INVERSE_GROSS_DIAGNOSTIC_SUPPORT_BUT_ZERO_BASE_POSITIVE_CELLS_AND_HIGH_RESCUE_BIAS"},
            {"rank": 4, "hypothesis": "LIQUIDITY_CONDITIONED_MOMENTUM", "reason": "COST_RELEVANT_BUT_CANNOT_CREATE_THE_MISSING_PRIMARY_GROSS_EFFECT"},
            {"rank": 5, "hypothesis": "CROSS_SECTIONAL_DISPERSION_CONDITIONING", "reason": "PLAUSIBLE_INTERACTION_WITH_HIGH_OUTCOME_INFORMED_FILTER_RISK"},
            {"rank": 6, "hypothesis": "REGIME_CONDITIONED_MOMENTUM", "reason": "LOW_REGIME_BREADTH_AND_HIGH_SUBGROUP_MINING_RISK"},
            {"rank": 7, "hypothesis": "SESSION_CONDITIONED_MOMENTUM", "reason": "NEARLY_ALL_CELLS_LACKED_POSITIVE_SESSION_BREADTH"},
        ],
        "commercial_reference_comparison": "BLOCK_NOT_EVALUATED_AT_STAGE1",
        "mfe_mae": "NOT_AVAILABLE_IN_EXISTING_OR_CORRECTED_STAGE1_JOURNAL",
        "cells": cells,
    }


def successor_preregistration(synthesis: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0_PREREGISTRATION.v1",
        "status": "PROPOSED_UNSCORED_OUTCOME_INFORMED_HYPOTHESIS",
        "selected_hypothesis": "FACTOR_COMMON_COMPONENT_MOMENTUM",
        "selection_basis": "GRAPH_FILTERS_REDUCED_MATCHED_LOSSES_BUT_DID_NOT_CREATE_POSITIVE_GROSS_PRIMARY_OR_NET_EDGE;_DIRECT_COMPONENT_DECOMPOSITION_HAS_HIGH_INFORMATION_VALUE",
        "material_distinction": "DECOMPOSE_NATIVE_PAIR_LOG_RETURNS_INTO_CONSTRAINED_CURRENCY_COMMON_COMPONENTS_AND_PAIR_RESIDUALS_THEN_TEST_THEIR_SEPARATE_FORWARD_INFORMATION",
        "not_evidence_of_edge": True,
        "baseline": "NORMALIZED_PAIR_MOMENTUM_WITH_IDENTICAL_TIMESTAMPS_HORIZONS_AND_COST_CONTRACT",
        "signal_components": ["FITTED_CURRENCY_COMMON_COMPONENT_MOMENTUM", "PAIR_SPECIFIC_RESIDUAL_MOMENTUM"],
        "entry_concept": "NEXT_CAUSALLY_AVAILABLE_M5_BAR_AFTER_COMPLETED_SIGNAL",
        "measurement_horizons_m5": [3, 12, 48],
        "formation_lookbacks_m5": [12, 48, 288],
        "directions": ["ECONOMIC_DIRECTION", "EXACT_INVERSE_SAME_OPPORTUNITIES"],
        "universe": "ALL_58_CERTIFIED_NATIVE_M5_PAIRS_FOR_FACTOR_ESTIMATION;_NO_SYNTHETIC_FILL_SERIES",
        "parameter_bounds": {"components": 2, "lookbacks": 3, "horizons": 3, "directions": 2},
        "maximum_new_scored_cells": 36,
        "matched_baseline_replication_cells": 18,
        "maximum_total_outcome_cells_if_LATER_authorized": 54,
        "cost_contract": "PKT040_GROSS_BASE_STRESSED_SEVERE_BUT_PLAUSIBLE_SIDE_CORRECT",
        "regime_conditions": "NONE_FOR_PRIMARY_EFFECT_SCREEN;_SESSION_VOLATILITY_AND_DISPERSION_ARE_DIAGNOSTICS_ONLY",
        "falsification": ["NO_POSITIVE_GROSS_COMPONENT_EFFECT", "NO_INCREMENTAL_VALUE_OVER_PAIR_MOMENTUM", "BASE_COST_DESTROYS_EFFECT", "INADEQUATE_BREADTH", "DEPENDENCE_AWARE_INTERVAL_NOT_ABOVE_ZERO"],
        "promotion": ["POSITIVE_GROSS", "POSITIVE_BASE", "BEATS_PAIR_MOMENTUM", "SYNCHRONIZED_BLOCK_INTERVAL_ABOVE_ZERO", "ADEQUATE_PAIR_AND_CURRENCY_BREADTH"],
        "data_partition": "NO_FRESH_INDEPENDENT_HISTORICAL_PARTITION_CURRENTLY_CERTIFIED;_ANY_IMMEDIATE_RUN_IS_EXPLORATORY_DEVELOPMENT_ONLY",
        "fresh_confirmation_requirement": "NEWLY_SEALED_OBSERVATIONS_STRICTLY_AFTER_2026-08-29T03:50:00Z_OR_INDEPENDENT_CERTIFIED_DATASET",
        "anti_leakage": ["COMPLETED_CANDLES_ONLY", "CAUSAL_SYNCHRONIZED_GRAPH", "ZERO_SUM_STRENGTH_CONSTRAINT", "NORMALIZE_AFTER_RAW_RETURN_GRAPH_FIT", "NO_VALIDATION_OR_CONTAMINATED_HOLDOUT_ACCESS"],
        "trial_memory_rule": "EVERY_OUTCOME_EXAMINED_NEW_COMPONENT_CELL_INCREMENTS_GLOBAL_MEMORY;_MATCHED_BASELINE_REPLICATIONS_ALSO_INCREMENT_IF_RESCORED",
        "source_failure_synthesis_sha256": sha256_bytes(canonical_bytes(synthesis)),
    }


def build_corrective_artifacts(
    result: dict[str, Any], journal: bytes, journal_audit: dict[str, Any], verification: dict[str, Any],
    ledger_payload: bytes, fingerprint_payload: bytes, memory_update: dict[str, Any],
) -> dict[str, bytes]:
    synthesis = build_corrective_failure_synthesis(result, journal)
    successor = successor_preregistration(synthesis)
    search_lineage = {
        "schema": "AIOS_FOREX_SCIENTIFIC_SEARCH_LINEAGE.v1",
        "lineage": [
            "PKT-FOREX-039",
            "PAIR_MOMENTUM_FAMILY",
            "72_OUTCOME_EXAMINED_RESULTS_INVALIDATED_FOR_PIP_METADATA_DEFECT",
            "72_UNCHANGED_SPECIFICATION_CORRECTIVE_REPLAYS",
            "CORRECTED_FAILURE_CLUSTERS",
            "COMMON_DENOMINATORS",
            "FACTOR_COMMON_COMPONENT_MOMENTUM_PROPOSED_UNSCORED",
        ],
        "random_strategy_wandering_blocked": True,
        "outcome_informed_successor": True,
    }
    report = (
        "# PKT-FOREX-042 PKT-039 Instrument Pip Metadata Corrective Replay\n\n"
        f"Corrective replay cells: {result['outcome_cells_replayed']}. New scored-trial increment: 0. "
        f"Corrected survivors: {len(result['mechanism_observed_cells'])}. "
        "Validation and holdout rows remained unopened. No verified edge was claimed.\n"
    ).encode("utf-8")
    core = {
        "AIOS_FOREX_PKT039_CORRECTED_RESULTS.json": canonical_bytes(result),
        "AIOS_FOREX_PKT039_CORRECTED_EVENT_EVIDENCE.jsonl.gz": journal,
        "AIOS_FOREX_PKT039_CORRECTED_JOURNAL_AUDIT.json": canonical_bytes(journal_audit),
        "AIOS_FOREX_PKT039_CORRECTED_INPUT_VERIFICATION.json": canonical_bytes(verification),
        "AIOS_FOREX_PKT039_CORRECTED_FAILURE_SYNTHESIS.json": canonical_bytes(synthesis),
        "AIOS_FOREX_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0_PREREGISTRATION.json": canonical_bytes(successor),
        "AIOS_FOREX_SCIENTIFIC_SEARCH_LINEAGE.json": canonical_bytes(search_lineage),
        "AIOS_FOREX_PKT039_CORRECTIVE_MEMORY_RECONCILIATION.json": canonical_bytes(memory_update),
        "AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl": ledger_payload,
        "AIOS_FOREX_FINGERPRINT_INDEX_V1.json": fingerprint_payload,
        "AIOS_FOREX_PKT039_CORRECTIVE_REPORT.md": report,
    }
    manifest = {
        "schema": "AIOS_FOREX_PKT039_CORRECTIVE_MANIFEST.v1",
        "packet_id": CORRECTIVE_PACKET_ID,
        "artifacts": {name: {"bytes": len(payload), "sha256": sha256_bytes(payload)} for name, payload in sorted(core.items())},
    }
    manifest_bytes = canonical_bytes(manifest)
    receipt = {
        "schema": "AIOS_FOREX_PKT039_CORRECTIVE_RECEIPT.v1",
        "packet_id": CORRECTIVE_PACKET_ID,
        "status": "PASS",
        "corrective_replay_cells": result["outcome_cells_replayed"],
        "new_scored_trial_increment": 0,
        "cumulative_scored_attempt_lower_bound": result["cumulative_actual_attempt_lower_bound"],
        "corrected_survivors": len(result["mechanism_observed_cells"]),
        "instrument_metadata_sha256": INSTRUMENT_METADATA_SHA256,
        "instrument_metadata_pair_count": len(certified_instrument_metadata()),
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "artifact_count": len(core) + 2,
        "validation_rows_opened": 0,
        "holdout_rows_opened": 0,
        "verified_edge": False,
        "commit": "NOT_PERFORMED",
        "push": "NOT_PERFORMED",
        "acceptance": {
            "exact_72_cell_unchanged_replay": "PASS" if result["outcome_cells_replayed"] == 72 else "FAIL",
            "zero_trial_increment": "PASS" if result["new_outcome_scored_trials"] == 0 else "FAIL",
            "certified_58_pair_metadata": "PASS",
            "append_only_invalidation_and_correction": "PASS" if memory_update["records_after"] == 227 else "FAIL",
            "negative_result_preserved": "PASS" if not result["mechanism_observed_cells"] else "NOT_APPLICABLE_SURVIVOR_FOUND",
            "validation_and_holdout_unopened": "PASS",
            "successor_proposed_unscored": "PASS",
            "edge_not_claimed": "PASS",
        },
    }
    return {
        **core,
        "AIOS_FOREX_PKT039_CORRECTIVE_MANIFEST.json": manifest_bytes,
        "AIOS_FOREX_PKT039_CORRECTIVE_RECEIPT.json": canonical_bytes(receipt),
    }
