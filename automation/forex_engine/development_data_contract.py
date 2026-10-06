"""Pure translation of the existing certified EUR/USD development metadata.

This module never opens prices, acquires data, evaluates a strategy, or creates
owner admission. Current acquisition code documents a request design; it is
not proof that a historical partition was acquired with those exact settings.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import PureWindowsPath
from typing import Any, Mapping

SCHEMA = "AIOS_SPOT_M5_DEVELOPMENT_METADATA_CONTRACT_V1"
MANIFEST_SHA256 = "ab40a9fc6c2abb1c9dfe1065afb072b8483d00ada693a708d0ea92c6aa901313"
GAP_AUDIT_SHA256 = "f0b7463f3f31829bed853ba49e10bda1c7588117d26ce384a6d6f3d26ac75b66"
DATA_SHA256 = "f7c800a8acceb39802268fd63222f1d0a243b165cda8e4f9fdb974f9dc0060cf"
COST_SHA256 = "91bad7c25a63ab05022ae71d6b243597bb2703a3525ac4b1f27b4ad2aaacc314"
RISK_SHA256 = "9fef759672fc9daf1ccd632daba927e74454f1871a36c76e023af9ff31fa6ac4"
COST_RISK_SHA256 = "57552fbe6fe3b1b7394c08e349a956e0119f7745ae3af3bee426ee73a93046fd"
EXECUTION_POLICY = "CONTIGUOUS_M5_STOP_FIRST_NO_ROLLOVER_NO_INTERPOLATION"
GAP_POLICY = "RESET_ANY_GAP_NO_PLANNED_PATH_CROSSING"
PERIOD = {"start": "2024-01-01T00:00:00Z", "warmup": "2024-01-01T00:00:00Z",
          "end_exclusive": "2026-01-01T00:00:00Z"}
PARTITION_ROOT = PureWindowsPath(
    r"C:\Dev\Ai.Os\.aios\runtime\forex_m5_immutable_corpus_v2\partitions\EUR_USD")
SOURCE_ROLES = frozenset(("acquisition_v2", "normalizer_v1", "development_owner", "execution_helpers"))
FROZEN_RISK = {"account_currency": "USD", "sizing": "FIXED_INITIAL_EQUITY",
               "fraction": 0.0005, "basket_fraction": 0.0025, "notional_multiple": 2.0,
               "minimum_units": 1, "initial_equity_usd": 100000.0}
FROZEN_COSTS = {
    "BASE": {"slippage_pips_per_side": 0.1, "commission_usd_per_million_per_side": 35.0,
             "label": "DECLARED_RESEARCH_SCENARIO"},
    "STRESSED": {"slippage_pips_per_side": 0.5, "commission_usd_per_million_per_side": 52.5,
                 "label": "DECLARED_RESEARCH_SCENARIO"},
    "SEVERE_BUT_PLAUSIBLE": {"slippage_pips_per_side": 1.0, "commission_usd_per_million_per_side": 70.0,
                           "label": "DECLARED_RESEARCH_SCENARIO"},
}
GATES = {"minimum_trades": 200, "positive_all_costs": True, "stressed_pf": 1.10,
         "maximum_dd": 0.10, "unknown_outcomes": 0, "minimum_positive_blocks": 3,
         "positive_top5_removed": True, "positive_november_removed": True,
         "positive_largest_block_removed": True, "beat_opposite_control": True}
UNCERTAINTY = {"unit": "SHARED_UTC_WEEK", "method": "PERCENTILE_CLUSTER_BOOTSTRAP",
               "samples": 1000, "seed": 97, "minimum_events": 30, "lower_95_above_zero": True}
UNSUPPORTED_DOMAINS = ["SPOT_HELD_ACROSS_ROLLOVER", "SPOT_MONTHLY", "FORWARD_MONTHLY",
                       "TICK_DEPTH_OR_LIQUIDITY_EXECUTION"]
NONAUTHORITY_FLAGS = ("admission_authority", "authorized_to_score", "registered", "signed",
                      "paper_ready", "live_ready")
REQUEST_GAPS = [
    "owner_accepted_sanitized_upstream_receipt_bound_to_each_of_24_partition_hashes",
    "historical_acquisition_source_hash_and_actual_request_windows",
    "actual_http_method_provider_host_endpoint_granularity_and_MBA_components",
    "actual_smooth_false_and_includeFirst_settings",
    "effective_alignment_timezone_daily_alignment_and_weekly_alignment",
    "UTC_bar_start_semantics_and_response_retrieval_time_status_binding",
]


EFFECTIVE_EXECUTION = {
            "entry_rule": "NEXT_M5_OPEN_AFTER_SIGNAL_CLOSE", "hold_bars": 6,
            "stop_atr": 1.0, "target": None, "gap_policy": GAP_POLICY,
            "signal_warmup_bars": 289, "signal_support_minutes": 1445,
            "signal_price_convention": "COMPONENT_WISE_BID_ASK_MEAN",
            "native_mid_components": "PRESENT_IN_CERTIFIED_ROWS_NO_EXACT_MID_MEAN_ASSERTION",
            "spread_accounting": "EMBEDDED_ONCE_IN_SIDE_CORRECT_BID_ASK_FILLS",
            "long_entry_side": "ASK_OPEN", "short_entry_side": "BID_OPEN",
            "long_exit_side": "BID", "short_exit_side": "ASK",
            "stop_policy": "GAP_OPEN_STOP_ELSE_INTRABAR_STOP_FIRST_PESSIMISTIC",
            "quarantine_support": "ALL_SIGNAL_SUPPORT_THROUGH_PLANNED_END",
            "financing_exit_local_time": "16:30", "calendar_timezone": "America/New_York",
            "planned_end_comparison": "STRICTLY_BEFORE",
            "planned_end_bounds": ["PINNED_EXISTING_FINANCING_EXIT", "DEVELOPMENT_END_EXCLUSIVE"],
            "session_policy": "PINNED_EXISTING_NO_ENTRY_AT_EVERY_PLANNED_M5_OPEN",
            "quote_to_account_conversion": 1.0, "account_currency": "USD",
            "cost_role": "DECLARED_RESEARCH_SCENARIOS",
        }


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _pin(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _utc(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("AWARE_DEVELOPMENT_TIMESTAMP_REQUIRED")
    return moment.astimezone(timezone.utc)


def _numbers(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return all(type(mapping.get(k)) in (int, float) and math.isfinite(mapping[k]) for k in keys)


def _validate_cost_risk(costs: Mapping[str, Any], risk: Mapping[str, Any]) -> None:
    if (costs != FROZEN_COSTS or any(not _numbers(c, ("slippage_pips_per_side",
            "commission_usd_per_million_per_side")) for c in costs.values()) or digest(costs) != COST_SHA256):
        raise ValueError("FROZEN_COST_SCENARIOS_CHANGED")
    if (risk != FROZEN_RISK or not _numbers(risk, ("fraction", "basket_fraction",
            "notional_multiple", "initial_equity_usd")) or type(risk.get("minimum_units")) is not int
            or digest(risk) != RISK_SHA256):
        raise ValueError("FROZEN_RISK_CHANGED")


def _validate_shards(partitions: list[Mapping[str, Any]], shards: list[Mapping[str, Any]]) -> None:
    if len(partitions) != 24 or len(shards) != 24:
        raise ValueError("DEVELOPMENT_PARTITION_COVERAGE_INCOMPLETE")
    for index, (part, shard) in enumerate(zip(partitions, shards)):
        year, month = 2024 + index // 12, index % 12 + 1
        first = datetime(year, month, 1, tzinfo=timezone.utc)
        end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1, tzinfo=timezone.utc)
        path = PARTITION_ROOT / f"{year}-{month:02d}.jsonl.gz"
        if (part.get("pair") != "EUR_USD" or PureWindowsPath(part.get("path", "")) != path
                or _utc(part["start_utc"]) != first or _utc(part["end_utc"]) != end
                or not _pin(part.get("sha256")) or type(part.get("records")) is not int
                or part["records"] <= 0 or part.get("observed_records") != part["records"]
                or not first <= _utc(part["first_timestamp"]) <= _utc(part["last_timestamp"]) < end):
            raise ValueError("DEVELOPMENT_PARTITION_ALLOWLIST_CHANGED")
        if shard != {k: part[k] for k in ("pair", "path", "sha256")}:
            raise ValueError("DEVELOPMENT_SHARD_PIN_CHANGED")


def _validate_quarantine(intervals: list[Mapping[str, Any]]) -> None:
    if not isinstance(intervals, list) or len(intervals) != 126:
        raise ValueError("QUARANTINE_COVERAGE_CHANGED")
    previous_end = None
    for interval in intervals:
        if set(interval) != {"pair", "start", "end_exclusive"} or interval["pair"] != "EUR_USD":
            raise ValueError("QUARANTINE_INTERVAL_INVALID")
        first, end = _utc(interval["start"]), _utc(interval["end_exclusive"])
        if (not _utc(PERIOD["start"]) <= first < end <= _utc(PERIOD["end_exclusive"])
                or (previous_end is not None and first < previous_end)):
            raise ValueError("QUARANTINE_INTERVAL_INVALID")
        previous_end = end


def translate_development_metadata(
    readback: Mapping[str, Any], draft: Mapping[str, Any], *,
    expected_readback_digest: str, expected_draft_digest: str,
    expected_source_pins: Mapping[str, Mapping[str, str]],
    consumer_source_sha256: str, catalog_sha256: str, signal_warmup_bars: int = 289,
) -> dict[str, Any]:
    """Validate exact observed metadata and return unsigned compiler fields.

    Expected digests are supplied by the existing source/input binding owner.
    A successful translation proves internal identity and scope consistency,
    never upstream authenticity, untouched confirmation or owner admission.
    No verified input-contract flags are copied from the old blocked job.
    """
    if (not _pin(expected_readback_digest) or not _pin(expected_draft_digest)
            or digest(readback) != expected_readback_digest or digest(draft) != expected_draft_digest):
        raise ValueError("METADATA_INPUT_IDENTITY_CHANGED")
    if type(signal_warmup_bars) is not int or signal_warmup_bars != 289:
        raise ValueError("EXACT_RETAINED_SIGNAL_SUPPORT_REQUIRED")
    if not _pin(consumer_source_sha256) or not _pin(catalog_sha256):
        raise ValueError("EXACT_CONSUMER_AND_CATALOG_PINS_REQUIRED")
    if readback.get("schema") != "AIOS_DEVELOPMENT_METADATA_READBACK_V1":
        raise ValueError("DEVELOPMENT_READBACK_SCHEMA_REQUIRED")
    boundary = readback.get("boundary", {})
    if (any(type(boundary.get(k)) is not int or boundary[k] != 0 for k in
            ("price_files_opened", "price_files_hashed", "holdout_files_opened",
             "holdout_files_hashed", "market_calls", "files_written"))
            or boundary.get("original_sqlite_opened") is not False
            or boundary.get("credentials_accessed") is not False):
        raise ValueError("METADATA_ONLY_BOUNDARY_REQUIRED")
    manifest, audit = readback["manifest"], readback["gap_audit"]
    header = manifest["header"]
    if (manifest.get("sha256") != MANIFEST_SHA256
            or draft["certified_development_manifest"].get("sha256") != MANIFEST_SHA256
            or manifest.get("path") != draft["certified_development_manifest"].get("path")
            or header.get("schema") != "AIOS_CERTIFIED_DEVELOPMENT_REFERENCE_SLICE_V1"
            or header.get("certified_development_only") is not True
            or any(type(header.get(k)) is not int or header[k] != 0 for k in
                   ("holdout_files_opened", "holdout_hashes_computed", "mixed_H1_files_opened", "market_calls"))
            or _utc(header["start_utc"]) != _utc(PERIOD["start"])
            or _utc(header["end_exclusive"]) != _utc(PERIOD["end_exclusive"])
            or _utc(header["holdout_start_utc"]) != _utc(PERIOD["end_exclusive"])):
        raise ValueError("DEVELOPMENT_ISOLATION_REQUIRED")
    if (set(expected_source_pins) != SOURCE_ROLES
            or readback.get("source_pins") != expected_source_pins
            or any(not _pin(v.get("sha256")) or not v.get("path") for v in expected_source_pins.values())):
        raise ValueError("DEVELOPMENT_SOURCE_PIN_CHANGED")
    scope = draft["scope"]
    if (draft.get("input_profile") != "SPOT_M5" or scope.get("pairs") != ["EUR_USD"]
            or scope.get("period") != PERIOD or scope.get("stage") != "DEVELOPMENT_SCREEN"
            or scope.get("execution_policy") != EXECUTION_POLICY
            or scope.get("daily_pair_trade_limit") != 1 or scope.get("maximum_positions") != 1
            or type(scope.get("daily_pair_trade_limit")) is not int
            or type(scope.get("maximum_positions")) is not int
            or scope.get("baselines") != ["NO_TRADE", "SAME_EVENTS_OPPOSITE_DIRECTION"]
            or type(scope.get("physical_call_reservation")) is not int
            or scope.get("physical_call_reservation") != 6
            or scope.get("pip_size") != 0.0001 or scope.get("spread_limit_pips") != 2.0):
        raise ValueError("EXACT_DEVELOPMENT_EXECUTION_SCOPE_REQUIRED")
    parts, shards = manifest["partitions"], draft["price_shards"]
    _validate_shards(parts, shards)
    quarantine = draft["quarantine_intervals"]
    _validate_quarantine(quarantine)
    gap = audit["metadata"]
    if (audit.get("sha256") != GAP_AUDIT_SHA256
            or draft["gap_audit"].get("sha256") != GAP_AUDIT_SHA256
            or audit.get("path") != draft["gap_audit"].get("path")
            or audit["quarantine_intervals"] != quarantine
            or gap.get("gap_policy") != GAP_POLICY or gap.get("scoring") is not False
            or gap.get("holdout_reads") != 0 or gap.get("market_calls") != 0):
        raise ValueError("QUARANTINE_AUDIT_CHANGED")
    if (gap.get("rows_validated") != sum(p["observed_records"] for p in parts)
            or gap.get("shards") != parts or len(gap.get("discontinuities", [])) != len(quarantine)
            or [{k: q[k] for k in ("pair", "start", "end_exclusive")}
                for q in gap["discontinuities"]] != quarantine):
        raise ValueError("GAP_AUDIT_COVERAGE_CHANGED")
    costs, risk = draft["existing_declared_costs"], draft["existing_bounded_risk"]
    _validate_cost_risk(costs, risk)
    data_hash = digest({"shards": shards, "quarantine_intervals": quarantine})
    cost_risk_hash = digest({"costs": costs, "risk": risk})
    pins = draft["existing_contract_hashes"]
    if (data_hash != DATA_SHA256 or pins.get("data_hash") != DATA_SHA256
            or pins.get("compiler_required_data_sha256") != DATA_SHA256
            or cost_risk_hash != COST_RISK_SHA256 or pins.get("cost_risk_hash") != COST_RISK_SHA256
            or pins.get("compiler_required_cost_risk_sha256") != COST_RISK_SHA256
            or pins.get("cost_sha256") != COST_SHA256 or pins.get("risk_sha256") != RISK_SHA256):
        raise ValueError("FROZEN_DATA_OR_COST_RISK_IDENTITY_CHANGED")
    fields = {k: copy.deepcopy(scope[k]) for k in (
        "pairs", "period", "stage", "execution_policy", "daily_pair_trade_limit",
        "maximum_positions", "pip_size", "spread_limit_pips", "baselines")}
    fields.update(price_shards=copy.deepcopy(shards), quarantine_intervals=copy.deepcopy(quarantine),
                  costs=copy.deepcopy(costs), risk=copy.deepcopy(risk),
                  data_hash=data_hash, cost_risk_hash=cost_risk_hash,
                  development_manifest_sha256=MANIFEST_SHA256,
                  gap_audit_path=audit["path"], gap_audit_sha256=GAP_AUDIT_SHA256,
                  gates=copy.deepcopy(GATES), uncertainty=copy.deepcopy(UNCERTAINTY),
                  source_hash=consumer_source_sha256,
                  dependence_protocol="ALL_PAIRS_SHARED_UTC_WEEK_BOOTSTRAP_NO_BAR_INDEPENDENCE_CLAIM")
    result = {
        "schema": SCHEMA, "status": "METADATA_COMPLETE_REQUIRES_EXISTING_OWNER_ADMISSION",
        "input_profile": "SPOT_M5", "readback_digest": expected_readback_digest,
        "draft_digest": expected_draft_digest, "catalog_sha256": catalog_sha256,
        "source_pins": copy.deepcopy(expected_source_pins), "execution_fields": fields,
        "metadata_evidence": {
            "manifest_path": manifest["path"], "manifest_sha256": MANIFEST_SHA256,
            "gap_audit_path": audit["path"], "gap_audit_sha256": GAP_AUDIT_SHA256,
            "observed_records": sum(p["observed_records"] for p in parts),
            "certified_complete_bar_quote_geometry": "EXISTING_DEVELOPMENT_OWNER_CERTIFICATE",
            "partition_rows_reopened_or_rehashed": False,
        },
        "effective_execution": copy.deepcopy(EFFECTIVE_EXECUTION),
        "request_provenance": {
            "status": "SOURCE_CODE_ONLY_NO_HISTORICAL_REQUEST_RECEIPTS",
            "observed_current_source_request": {
                "http_method": "GET", "environment": "practice",
                "endpoint_family": "/v3/instruments/{pair}/candles",
                "granularity": "M5", "price_components": ["M", "B", "A"],
                "smooth": False, "include_first": True,
                "source_sha256": expected_source_pins["acquisition_v2"]["sha256"],
            },
            "historical_request_settings_verified": False,
            "fresh_http_receipts_required_by_existing_development_validator": False,
            "effective_alignment_timezone": None, "effective_daily_alignment": None,
            "effective_weekly_alignment": None, "missing": list(REQUEST_GAPS),
        },
        "historical_costs_verified": False, "financing_contract_complete": False,
        "tick_depth_contract_complete": False, "unsupported_domains": list(UNSUPPORTED_DOMAINS),
        "governing_development_contract": {
            "certificate_owner_source": copy.deepcopy(expected_source_pins["development_owner"]),
            "native_validation_functions": ["development_supertrend_inputs_v1",
                "validate_supertrend_development_spec_v1", "validate_execution_spec"],
            "development_data_evidence": "EXISTING_CERTIFIED_MANIFEST_AND_EXACT_GAP_AUDIT",
            "development_cost_evidence": "EXACT_DECLARED_THREE_RESEARCH_SCENARIOS",
            "historical_broker_tariffs_required_for_this_development_domain": False,
            "tick_depth_required_for_this_OHLC_development_domain": False,
            "held_financing_required_when_exact_no_rollover_rule_is_enforced": False,
        },
        "stage_readiness": {
            "development": {"data_cost_metadata_complete": True,
                "supported_input_domain": "CERTIFIED_SPOT_M5_DEVELOPMENT_NO_ROLLOVER",
                "new_matching_owner_admission_required": True, "authorized_to_score": False},
            "paper": {"ready": False, "independent_strategy_proof_accepted": False,
                "broker_execution_fidelity_verified": False, "effective_dated_broker_costs_verified": False},
            "live": {"ready": False, "live_execution_adapter_admitted": False},
        },
        "limitations": ["HISTORICAL_PER_SHARD_REQUEST_SETTINGS_NOT_REVALIDATED",
            "CURRENT_ACQUISITION_SOURCE_IS_NOT_A_HISTORICAL_HTTP_RECEIPT",
            "DECLARED_RESEARCH_COSTS_ARE_NOT_VERIFIED_HISTORICAL_BROKER_TARIFFS",
            "OHLC_STOP_FIRST_MODEL_HAS_NO_TICK_DEPTH_OR_EXACT_INTRABAR_ORDER_PROOF"],
        "blockers": ["EXACT_CATALOG_HISTORY_ADMISSION",
                     "EXISTING_SOURCE_IMPORT_CLOSURE_AND_MATCHING_OWNER_SCOPE",
                     "EXISTING_ORIGINAL_INTEGRITY_STOP_DISPOSITION",
                     "CANONICAL_TRIAL_AND_BUDGET_BINDING"],
        **{flag: False for flag in NONAUTHORITY_FLAGS},
        "market_calls": 0, "evaluator_calls": 0, "new_reservations": 0,
    }
    validate_development_metadata_contract(result, expected_digest=digest(result))
    return result


def validate_development_metadata_contract(contract: Mapping[str, Any], *, expected_digest: str) -> None:
    """Check a bound translation without changing its owner or provenance role."""
    if not _pin(expected_digest) or digest(contract) != expected_digest or contract.get("schema") != SCHEMA:
        raise ValueError("DEVELOPMENT_CONTRACT_IDENTITY_CHANGED")
    if (any(contract.get(flag) is not False for flag in NONAUTHORITY_FLAGS)
            or any(type(contract.get(k)) is not int or contract[k] != 0 for k in
                   ("market_calls", "evaluator_calls", "new_reservations"))
            or contract.get("historical_costs_verified") is not False
            or contract.get("financing_contract_complete") is not False
            or contract.get("tick_depth_contract_complete") is not False):
        raise ValueError("NONAUTHORITATIVE_METADATA_REQUIRED")
    fields = contract["execution_fields"]
    execution = contract["effective_execution"]
    if (fields.get("pairs") != ["EUR_USD"] or fields.get("period") != PERIOD
            or fields.get("execution_policy") != EXECUTION_POLICY
            or fields.get("pip_size") != 0.0001 or fields.get("spread_limit_pips") != 2.0
            or fields.get("maximum_positions") != 1 or fields.get("daily_pair_trade_limit") != 1
            or fields.get("stage") != "DEVELOPMENT_SCREEN" or "contracts" in fields
            or fields.get("gates") != GATES or fields.get("uncertainty") != UNCERTAINTY
            or digest(execution) != digest(EFFECTIVE_EXECUTION)
            or type(fields.get("maximum_positions")) is not int
            or type(fields.get("daily_pair_trade_limit")) is not int
            or fields.get("baselines") != ["NO_TRADE", "SAME_EVENTS_OPPOSITE_DIRECTION"]
            or execution.get("entry_rule") != "NEXT_M5_OPEN_AFTER_SIGNAL_CLOSE"
            or execution.get("financing_exit_local_time") != "16:30"
            or execution.get("planned_end_comparison") != "STRICTLY_BEFORE"
            or execution.get("signal_warmup_bars") != 289 or execution.get("signal_support_minutes") != 1445
            or execution.get("hold_bars") != 6 or execution.get("stop_atr") != 1.0
            or execution.get("target") is not None or execution.get("gap_policy") != GAP_POLICY
            or execution.get("signal_price_convention") != "COMPONENT_WISE_BID_ASK_MEAN"):
        raise ValueError("EXACT_DEVELOPMENT_EXECUTION_CONTRACT_REQUIRED")
    _validate_quarantine(fields["quarantine_intervals"])
    _validate_cost_risk(fields["costs"], fields["risk"])
    if (fields.get("data_hash") != DATA_SHA256 or digest({
            "shards": fields["price_shards"], "quarantine_intervals": fields["quarantine_intervals"]}) != DATA_SHA256
            or fields.get("cost_risk_hash") != COST_RISK_SHA256
            or digest({"costs": fields["costs"], "risk": fields["risk"]}) != COST_RISK_SHA256):
        raise ValueError("FROZEN_DATA_OR_COST_RISK_IDENTITY_CHANGED")
    provenance = contract["request_provenance"]
    if (provenance.get("historical_request_settings_verified") is not False
            or provenance.get("status") != "SOURCE_CODE_ONLY_NO_HISTORICAL_REQUEST_RECEIPTS"
            or provenance.get("missing") != REQUEST_GAPS
            or provenance.get("fresh_http_receipts_required_by_existing_development_validator") is not False
            or any(provenance.get(k) is not None for k in ("effective_alignment_timezone",
                "effective_daily_alignment", "effective_weekly_alignment"))
            or contract.get("unsupported_domains") != UNSUPPORTED_DOMAINS):
        raise ValueError("SOURCE_OBSERVATION_IS_NOT_UPSTREAM_PROVENANCE")
    readiness = contract.get("stage_readiness", {})
    if (readiness.get("development", {}).get("data_cost_metadata_complete") is not True
            or readiness["development"].get("new_matching_owner_admission_required") is not True
            or readiness["development"].get("authorized_to_score") is not False
            or readiness.get("paper", {}).get("ready") is not False
            or readiness.get("live", {}).get("ready") is not False
            or "SANITIZED_UPSTREAM_REQUEST_PROVENANCE" in contract.get("blockers", [])):
        raise ValueError("STAGE_SPECIFIC_EXISTING_OWNER_BOUNDARY_REQUIRED")


COMMON_CONTRACT_KEYS = ("pair_conversion", "risk_units", "execution_paths", "costs",
                        "rollover", "quarantine", "stage2_gates", "dependence_uncertainty")
NATIVE_PROPOSAL_SHA256 = "39122b5df2b2190ffbc5e3daa74fc4638274364cd7aa466601719df7dbf8b191"
ORIGINAL_INCOMPLETE_HISTORY_SHA256 = "da1371f123bb90a11b21b947a371d3fff772344bb0ee6e3642b44de4d69eb58e"
EXISTING_COMMON_SCOPE = "Credential-free development admission only; no independent proof or market authority"


def project_existing_common_development_contracts(
    native_readback: Mapping[str, Any], development_contract: Mapping[str, Any], *,
    expected_native_readback_digest: str, expected_contract_digest: str,
) -> dict[str, Any]:
    """Retain scoped native component records only after exact invariant checks.

    The original verification flags and evidence maps are copied verbatim.
    They verify existing bounded development components, not a new FXH02
    signal design, selection history, source adoption or scoring permission.
    The retired R17 macro input contract is explicitly excluded.
    """
    if (not _pin(expected_native_readback_digest)
            or digest(native_readback) != expected_native_readback_digest
            or native_readback.get("schema") != "AIOS_EXISTING_DEVELOPMENT_COMMON_CONTRACT_READBACK_V1"):
        raise ValueError("EXISTING_COMMON_READBACK_IDENTITY_CHANGED")
    validate_development_metadata_contract(development_contract, expected_digest=expected_contract_digest)
    original = native_readback.get("original_proposed_job", {})
    old = original.get("fields", {})
    new = development_contract["execution_fields"]
    if (original.get("sha256") != NATIVE_PROPOSAL_SHA256 or not original.get("path")
            or old.get("handler") != "supertrend_development_v1"
            or PureWindowsPath(original["path"]) != PureWindowsPath(new["gap_audit_path"]).with_name("PROPOSED_JOB.json")):
        raise ValueError("EXISTING_NATIVE_DEVELOPMENT_PROPOSAL_REQUIRED")
    boundary = native_readback.get("boundary", {})
    if (any(type(boundary.get(k)) is not int or boundary[k] != 0 for k in
            ("price_files_opened", "price_files_hashed", "holdout_files_opened", "holdout_files_hashed",
             "market_calls", "files_written")) or boundary.get("credentials_accessed") is not False
            or boundary.get("original_sqlite_opened") is not False):
        raise ValueError("METADATA_ONLY_BOUNDARY_REQUIRED")
    unchanged = ("stage", "pairs", "period", "data_hash", "cost_risk_hash",
                 "development_manifest_sha256", "gap_audit_path", "gap_audit_sha256",
                 "risk", "costs", "gates", "uncertainty", "dependence_protocol",
                 "execution_policy", "baselines", "maximum_positions", "daily_pair_trade_limit",
                 "pip_size", "spread_limit_pips")
    numeric_encoding_differences = []
    for key in unchanged:
        if key in ("pip_size", "spread_limit_pips"):
            if not _numbers(old, (key,)) or old[key] != new[key]:
                raise ValueError("COMMON_DEVELOPMENT_SCOPE_CHANGED:" + key)
            if digest(old[key]) != digest(new[key]):
                numeric_encoding_differences.append({"field": key,
                    "native_original_value_digest": digest(old[key]),
                    "current_frozen_value_digest": digest(new[key]),
                    "finite_nonboolean_economics_equal": True})
            continue
        if key in ("risk", "costs"):
            numeric_valid = (isinstance(old.get(key), dict) and old[key] == new[key])
            if key == "risk" and numeric_valid:
                numeric_valid = (_numbers(old[key], ("fraction", "basket_fraction", "notional_multiple",
                                    "initial_equity_usd")) and type(old[key].get("minimum_units")) is int)
            elif key == "costs" and numeric_valid:
                numeric_valid = all(_numbers(c, ("slippage_pips_per_side",
                                      "commission_usd_per_million_per_side")) for c in old[key].values())
            if not numeric_valid:
                raise ValueError("COMMON_DEVELOPMENT_SCOPE_CHANGED:" + key)
            if digest(old[key]) != digest(new[key]):
                numeric_encoding_differences.append({"field": key,
                    "native_original_value_digest": digest(old[key]),
                    "current_frozen_value_digest": digest(new[key]),
                    "finite_nonboolean_economics_equal": True})
            continue
        if key not in old or digest(old[key]) != digest(new[key]):
            raise ValueError("COMMON_DEVELOPMENT_SCOPE_CHANGED:" + key)
    old_rules = old.get("rules", {})
    for key in ("hold_bars", "stop_atr", "target", "entry_rule", "gap_policy"):
        if key == "stop_atr" and _numbers(old_rules, (key,)) and old_rules[key] == development_contract["effective_execution"][key]:
            if digest(old_rules[key]) != digest(development_contract["effective_execution"][key]):
                numeric_encoding_differences.append({"field": "rules.stop_atr",
                    "native_original_value_digest": digest(old_rules[key]),
                    "current_frozen_value_digest": digest(development_contract["effective_execution"][key]),
                    "finite_nonboolean_economics_equal": True})
            continue
        if key not in old_rules or digest(old_rules[key]) != digest(development_contract["effective_execution"][key]):
            raise ValueError("COMMON_EXECUTION_RULE_CHANGED:" + key)
    records = old.get("contracts", {})
    original_evidence_map = {new["gap_audit_path"]: GAP_AUDIT_SHA256,
        str(PureWindowsPath(original["path"]).with_name("HISTORY_ADMISSION.json")): ORIGINAL_INCOMPLETE_HISTORY_SHA256}
    common = {}
    record_identities = {}
    for key in COMMON_CONTRACT_KEYS:
        record = records.get(key, {})
        pins = record.get("evidence_hashes")
        if (record.get("verified") is not True or record.get("scope") != EXISTING_COMMON_SCOPE
                or not isinstance(pins, dict) or not pins or any(not _pin(h) for h in pins.values())
                or pins != original_evidence_map):
            raise ValueError("EXISTING_COMMON_COMPONENT_RECORD_REQUIRED:" + key)
        # Preserve the original UNKNOWN_HISTORY evidence pin as provenance.
        # It does not become complete FXH02 selection history.
        common[key] = copy.deepcopy(record)
        record_identities[key] = digest(record)
    history_record = records.get("selection_history", {})
    if history_record.get("verified") is not False:
        raise ValueError("OLD_SELECTION_HISTORY_MUST_REMAIN_UNVERIFIED")
    inherited = {
        "pair_conversion": ["EUR_USD_QUOTES_IN_USD", "USD_ACCOUNT_CONVERSION_ONE"],
        "risk_units": ["EXACT_FIXED_INITIAL_EQUITY_RISK_AND_NOTIONAL_CAPS", "SAME_POSITION_AND_DAILY_CAPS"],
        "execution_paths": ["SAME_SIDE_CORRECT_NEXT_OPEN_FILL_AND_STOP_FIRST_PRIMITIVES", "SAME_SIX_BAR_ATR_ONE_HOLD"],
        "costs": ["IDENTICAL_DECLARED_THREE_COST_SCENARIOS", "SPREAD_EMBEDDED_ONCE"],
        "rollover": ["SAME_PINNED_NATIVE_SESSION_AND_FINANCING_EXIT", "STRICT_PLANNED_END_EXCLUSION"],
        "quarantine": ["IDENTICAL_CERTIFIED_SHARDS_AND_126_TIMESTAMP_QUARANTINES", "NO_GAP_INTERPOLATION"],
        "stage2_gates": ["IDENTICAL_EXISTING_GATE_POLICY", "NO_STAGE2_PASS_OR_PROMOTION_CLAIM"],
        "dependence_uncertainty": ["SAME_SHARED_UTC_WEEK_BOOTSTRAP_PARAMETERS", "NO_BAR_OR_TRADE_INDEPENDENCE_CLAIM"],
    }
    return {
        "schema": "AIOS_EXISTING_COMMON_DEVELOPMENT_CONTRACT_REUSE_V1",
        "status": "EXACT_COMMON_COMPONENT_RECORDS_RETAINED_REQUIRES_EXISTING_OWNER_SOURCE_SCOPE",
        "native_proposal_source_pin": {"path": original["path"], "sha256": original["sha256"]},
        "native_readback_digest": expected_native_readback_digest,
        "development_contract_digest": expected_contract_digest,
        "common_input_contracts": common, "original_record_digests": record_identities,
        "inherited_component_scope": inherited,
        "checked_unchanged_fields": list(unchanged),
        "numeric_encoding_differences": numeric_encoding_differences,
        "old_proposal_reactivated": False,
        "new_contracts_required": ["price_signal_design", "selection_history"],
        "new_source_deltas_requiring_matching_owner_scope": [
            "NEW_FXH02_DERIVED_MIDPOINT_SIGNAL_DESIGN_AND_ALL_THREE_CATALOG_MEMBERS",
            "SIGNAL_SUPPORT_AND_QUARANTINE_GUARD_EXTENDED_FROM_46_TO_289_PRIOR_BARS",
            "EXACT_CURRENT_CONSUMER_FILL_FAILURE_AND_SAVED_COMPARISON_SOURCE",
        ],
        "excluded_old_signal_record": {
            "reason": "OLD_SUPERTREND_SIGNAL_DESIGN_DOES_NOT_VERIFY_FXH02",
            "original_record_digest": digest(records["price_signal_design"]),
            "reused": False,
        },
        "excluded_old_selection_record": {
            "reason": "OLD_UNKNOWN_HISTORY_DOES_NOT_CERTIFY_NEW_CATALOG",
            "original_record_digest": digest(history_record),
            "original_verified": False, "reused": False,
        },
        "unrelated_macro_contract": {
            "source_pin": {k: native_readback["current_root_input_contract"][k] for k in ("path", "sha256")},
            "scope": native_readback["current_root_input_contract"]["scope"],
            "reused": False,
        },
        "authority_granted": False, "signed": False, "authorized_to_score": False,
        "new_reservations": 0, "market_calls": 0, "paper_ready": False, "live_ready": False,
    }
