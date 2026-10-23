"""Frozen M5 compression/breakout research question and a pure feature seam.

These three finite implementations are engineering inventory. They create no
admission, score, data access or trading authority. Economic family novelty must
be resolved against retained range and compression studies by the history owner.
The native consumer supplies the existing bar guard and executable cost replay.
"""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import statistics


HANDLER = "supported_entry_development_v1"
HISTORY_ARCHIVE_PATHS = (
    ".aios/staging/supertrend_explorer_v9/SCOUT_V9_RESULTS.json",
    ".aios/staging/supertrend_explorer_v8/SCOUT_V8_RESULTS.json",
    ".aios/staging/supertrend_explorer_v7/SCOUT_V7_RESULTS.json",
    ".aios/staging/ea_hypothesis_range_scout_v1/SCOUT_V1_RESULTS.json",
    ".aios/staging/supertrend_explorer_v6/SCOUT_V6_RESULTS.json",
    ".aios/staging/PKT_AIOS_ADAPTIVE_WORKFORCE_001/post_acquisition_review_20260916/research_v5/campaign_r3/historical/run1/scientific_result.json",
)
PERIOD = {"warmup": "2024-01-01T00:00:00Z", "start": "2024-01-01T00:00:00Z",
          "end_exclusive": "2026-01-01T00:00:00Z"}
RULES = {"hold_bars": 6, "stop_atr": 1.0, "target": None,
         "entry_rule": "NEXT_M5_OPEN_AFTER_SIGNAL_CLOSE", "warmup_bars": 289,
         "gap_policy": "RESET_ANY_GAP_NO_PLANNED_PATH_CROSSING",
         "range_bars": 12, "compression_bars": 12, "reference_bars": 288,
         "atr_bars": 20, "atr_method": "LAGGED_SIMPLE_MEAN_TRUE_RANGE",
         "signal_rule": "STRICT_COMPLETED_CLOSE_OUTSIDE_LAGGED_RANGE"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def question_descriptor_v1():
    return {
        "schema": "AIOS_SUPPORTED_ENTRY_QUESTION_V1", "question_id": "FXH02",
        "economic_family": "CONDITIONAL_INFORMATION_DIFFUSION_RANGE_BREAKOUT",
        "economic_question": "Does lagged true-range compression improve net continuation after a completed M5 close breaks a preceding 12-bar range?",
        "feature_rules": {"range_bars": 12, "compression_bars": 12, "reference_bars": 288,
                          "true_range": "MAX_HIGH_MINUS_LOW_ABS_HIGH_MINUS_PREVIOUS_CLOSE_ABS_LOW_MINUS_PREVIOUS_CLOSE",
                          "compression": "MEAN_TR_T_MINUS_12_THROUGH_T_MINUS_1_OVER_MEDIAN_TR_T_MINUS_288_THROUGH_T_MINUS_1",
                          "reference_includes_compression_window": True,
                          "range": "MAX_HIGH_MIN_LOW_T_MINUS_12_THROUGH_T_MINUS_1",
                          "signal": "STRICT_COMPLETED_MID_CLOSE_ABOVE_HIGH_OR_BELOW_LOW",
                          "atr": "SIMPLE_MEAN_TR_T_MINUS_20_THROUGH_T_MINUS_1",
                          "signal_bar_excluded_from_range_compression_and_atr": True,
                          "zero_reference_or_atr": "REJECT_NOT_FORWARD_FILL",
                          "mid": "ARITHMETIC_BID_ASK_OHLC_MIDPOINT",
                          "availability": "BAR_OPEN_PLUS_FIVE_MINUTES",
                          "warmup_bars": 289, "gap_reset": "EVERY_NON_M5_TIMESTAMP_BREAK"},
        "execution_rules": deepcopy(RULES),
        "finite_compression_ratio_max": [None, .5, .75],
        "baseline": "INDEX_0_IDENTICAL_UNGATED_RANGE_BREAKOUT",
        "controls": ["NO_TRADE", "SAME_EVENTS_OPPOSITE_DIRECTION", "FULL_CATALOG_UNGATED_BREAKOUT"],
        "matched_execution": "SAME_NATIVE_TRADE_PATH_RISK_COSTS_SESSION_AND_DAILY_CAPS_ALL_ARMS",
        "comparison": "FULL_STRATEGY_NET_USD_AND_SHARED_UTC_WEEK_DIFFERENCES_DISCLOSE_OPPORTUNITY_CAP_EFFECTS",
        "selection": "ALL_THREE_PREFROZEN_MEMBERS_AND_OPPOSITE_ARMS_COUNT_BEFORE_RESULT_SELECTION",
        "scientific_limits": "DEVELOPMENT_USED_NOT_INDEPENDENT_EDGE; NO_PRIOR_STUDY_CLOSURE_OR_NOVELTY_IS_INFERRED",
        "status": "DRAFT_UNADMITTED", "owner_certified_novelty": False,
    }


class FrozenEntryCatalog:
    """Ordinal inventory is immutable; an ordinal is never novelty evidence."""
    @property
    def descriptor(self):
        return question_descriptor_v1()

    @property
    def descriptor_sha256(self):
        return digest(self.descriptor)

    def __len__(self):
        return 3

    def spec_at(self, index):
        if type(index) is not int or not 0 <= index < 3:
            raise ValueError("SUPPORTED_ENTRY_CATALOG_INDEX")
        descriptor = self.descriptor
        mechanism = {"family": descriptor["economic_family"],
                     "question": descriptor["economic_question"],
                     "feature_rules": descriptor["feature_rules"]}
        implementation = {"schema": "LAGGED_COMPRESSION_CLOSE_BREAKOUT_V1",
                          "role": "UNGATED_BREAKOUT_CONTROL" if index == 0 else "COMPRESSION_FILTERED_CANDIDATE",
                          "compression_ratio_max": descriptor["finite_compression_ratio_max"][index],
                          "rules": deepcopy(RULES)}
        return {"catalog_index": index, "catalog_sha256": self.descriptor_sha256,
                "question_sha256": digest(descriptor), "mechanism": mechanism,
                "mechanism_sha256": digest(mechanism), "implementation": implementation,
                "implementation_sha256": digest(implementation)}


def supported_entry_catalog_v1():
    return FrozenEntryCatalog()


def job_metadata_v1(index):
    item = supported_entry_catalog_v1().spec_at(index)
    return {"handler": HANDLER, "stage": "DEVELOPMENT_SCREEN", "identity_version": 2,
            "pairs": ["EUR_USD"], "period": deepcopy(PERIOD), "rules": deepcopy(RULES),
            "rules_hash": digest(RULES), "catalog_index": index,
            "catalog_sha256": item["catalog_sha256"], "question_sha256": item["question_sha256"],
            "mechanism_fingerprint": item["mechanism_sha256"],
            "implementation_fingerprint": item["implementation_sha256"],
            "configuration_count": 2, "internal_configuration_exposure": 2,
            "physical_call_reservation": 6, "maximum_positions": 1, "daily_pair_trade_limit": 1,
            "dependence_protocol": "ALL_PAIRS_SHARED_UTC_WEEK_BOOTSTRAP_NO_BAR_INDEPENDENCE_CLAIM"}


def validate_supported_entry_job_metadata_v1(spec):
    if type(spec) is not dict:
        raise ValueError("SUPPORTED_ENTRY_FROZEN_JOB_METADATA")
    expected = job_metadata_v1(spec.get("catalog_index"))
    # JSON equality alone equates True with 1; bind exact JSON bytes too.
    if any(k not in spec or digest(spec[k]) != digest(v) for k, v in expected.items()):
        raise ValueError("SUPPORTED_ENTRY_FROZEN_JOB_METADATA")
    return supported_entry_catalog_v1().spec_at(spec["catalog_index"])


def validate_supported_entry_jobs_v1(jobs):
    """Pure whole-catalog metadata check; never reads any referenced inputs."""
    if type(jobs) not in (list, tuple) or len(jobs) != 3 or [s.get("catalog_index") for s in jobs] != [0, 1, 2]:
        raise ValueError("SUPPORTED_ENTRY_FULL_ORDERED_CATALOG_REQUIRED")
    for spec in jobs:
        validate_supported_entry_job_metadata_v1(spec)
    shared = ("data_hash", "cost_risk_hash", "source_hash", "risk", "costs", "time_blocks",
              "pip_size", "spread_limit_pips", "execution_policy", "quarantine_intervals", "price_shards",
              "development_manifest_sha256", "gap_audit_sha256", "contracts", "supported_entry_source_pins")
    first = jobs[0]
    for key in shared:
        if key not in first or first[key] is None or first[key] in ("", [], {}):
            raise ValueError("SUPPORTED_ENTRY_SHARED_CONTRACT_REQUIRED:" + key)
        if any(key not in s or digest(s[key]) != digest(first[key]) for s in jobs):
            raise ValueError("SUPPORTED_ENTRY_MATCHED_SHARED_CONTRACT_REQUIRED:" + key)
    for key in ("data_hash", "cost_risk_hash", "source_hash", "development_manifest_sha256", "gap_audit_sha256"):
        value = first[key]
        if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("SUPPORTED_ENTRY_EXACT_CONTRACT_HASH_REQUIRED:" + key)
    contracts = first["contracts"]
    for key in ("price_signal_design", "pair_conversion", "risk_units", "execution_paths", "costs",
                "rollover", "quarantine", "stage2_gates", "dependence_uncertainty", "selection_history"):
        record = contracts.get(key) if isinstance(contracts, dict) else None
        if (type(record) is not dict or record.get("verified") is not True or
                not isinstance(record.get("evidence_hashes"), dict) or not record["evidence_hashes"] or
                any(type(h) is not str or len(h) != 64 or any(c not in "0123456789abcdef" for c in h)
                    for h in record["evidence_hashes"].values())):
            raise ValueError("SUPPORTED_ENTRY_VERIFIED_CONTRACT_REQUIRED:" + key)
    return {"catalog_sha256": supported_entry_catalog_v1().descriptor_sha256,
            "ordered_catalog_indices": [0, 1, 2], "configuration_exposure": 6,
            "physical_call_reservation": 18, "admission_granted": False}


def _exact_sha(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def history_metadata_reference_allowed_v1(path):
    if type(path) is not str or not path:
        return False
    normalized = path.replace("\\", "/").lower()
    basename = normalized.rsplit("/", 1)[-1].rstrip(" .").split(":", 1)[0]
    raw_names = {p.rsplit("/", 1)[-1].lower() for p in HISTORY_ARCHIVE_PATHS}
    return basename not in raw_names


def validate_supported_entry_history_inventory_v1(record, inventory):
    """Bind owner dispositions to a complete, unchanged metadata projection.

    The inventory remains UNKNOWN_HISTORY and has no admission power. Its six
    omitted archives require exact owner coverage and an actual closure basis;
    differing names, source bytes or timeframe labels cannot certify novelty.
    """
    if type(inventory) is not dict or inventory.get("schema") != "AIOS_SELECTION_HISTORY_METADATA_PROJECTION_V1":
        raise ValueError("SUPPORTED_ENTRY_EXACT_HISTORY_INVENTORY_REQUIRED")
    calculated = digest({k: v for k, v in inventory.items() if k != "projection_sha256"})
    if (inventory.get("projection_sha256") != calculated or record.get("history_inventory_sha256") != calculated or
            inventory.get("native_admission") is not False or inventory.get("coverage_complete") is not False or
            inventory.get("status") != "UNKNOWN_HISTORY" or inventory.get("enumeration_errors") != [] or
            inventory.get("read_errors") != [] or inventory.get("unaccounted_selected_metadata_count") != 0):
        raise ValueError("SUPPORTED_ENTRY_HISTORY_INVENTORY_DIGEST_OR_CENSUS_INCOMPLETE")
    source = inventory.get("source", {})
    if (type(source) is not dict or set(source) != {"path", "sha256"} or
            type(source["path"]) is not str or not source["path"] or not _exact_sha(source["sha256"]) or
            record.get("metadata_census_source") != source):
        raise ValueError("SUPPORTED_ENTRY_EXACT_METADATA_CENSUS_REQUIRED")
    archives = inventory.get("archives")
    if (type(archives) is not list or len(archives) != 6 or any(type(a) is not dict for a in archives) or
            {a.get("path") for a in archives} != set(HISTORY_ARCHIVE_PATHS)):
        raise ValueError("SUPPORTED_ENTRY_EXACT_SIX_HISTORY_ARCHIVES_REQUIRED")
    denominator = inventory.get("denominator", {})
    counts = (inventory.get("source_path_count"), inventory.get("unique_content_count"),
              denominator.get("enumerated"), denominator.get("selected"), denominator.get("input_content_records"))
    if (any(type(n) is not int or n < 0 for n in counts) or
            counts[0]+6 != counts[3] or counts[2] < counts[3] or counts[1] != counts[4]):
        raise ValueError("SUPPORTED_ENTRY_WHOLE_METADATA_CENSUS_DENOMINATOR_REQUIRED")
    dispositions = record.get("archive_dispositions")
    if type(dispositions) is not dict or set(dispositions) != set(HISTORY_ARCHIVE_PATHS):
        raise ValueError("SUPPORTED_ENTRY_EXACT_SIX_OWNER_DISPOSITIONS_REQUIRED")
    if type(record.get("economic_disposition_basis")) is not str or not record["economic_disposition_basis"].strip():
        raise ValueError("SUPPORTED_ENTRY_ACTUAL_PRECLOSED_DOMAIN_REVIEW_BASIS_REQUIRED")
    evidence = {}
    for archive in archives:
        disposition = dispositions[archive["path"]]
        if (not _exact_sha(archive.get("sha256")) or type(archive.get("definition_count")) is not int or
                archive["definition_count"] <= 0 or not _exact_sha(archive.get("definition_projection_sha256")) or
                type(disposition) is not dict or
                disposition.get("declared_archive_sha256") != archive["sha256"] or
                type(disposition.get("definition_count")) is not int or disposition["definition_count"] != archive["definition_count"] or
                disposition.get("definition_projection_sha256") != archive["definition_projection_sha256"] or
                disposition.get("owner_reviewed") is not True or
                disposition.get("coverage_status") != "OWNER_CERTIFIED_COMPLETE" or
                disposition.get("trade_equivalence_status") != "DISTINCT_FROM_SUPPORTED_CATALOG" or
                disposition.get("terminal_closure_disposition") not in {
                    "OUTSIDE_PREDECLARED_CLOSURE_SCOPE", "NO_TERMINAL_CLOSURE_IN_REVIEWED_SCOPE"} or
                disposition.get("not_parameter_rescue") is not True or
                type(disposition.get("review_basis")) is not str or not disposition["review_basis"].strip()):
            raise ValueError("SUPPORTED_ENTRY_ARCHIVE_IDENTITY_OR_OWNER_CLOSURE_DISPOSITION_REQUIRED")
        refs = disposition.get("evidence_hashes")
        if (type(refs) is not dict or not refs or
                any(type(path) is not str or not path or not _exact_sha(pin) for path, pin in refs.items())):
            raise ValueError("SUPPORTED_ENTRY_CLOSURE_REVIEW_EVIDENCE_REQUIRED")
        for path, pin in refs.items():
            if not history_metadata_reference_allowed_v1(path):
                raise ValueError("SUPPORTED_ENTRY_RAW_HISTORY_ARCHIVE_REFERENCE_FORBIDDEN")
            if path in evidence and evidence[path] != pin:
                raise ValueError("SUPPORTED_ENTRY_CLOSURE_EVIDENCE_IDENTITY_CONFLICT")
            evidence[path] = pin
    return {"history_inventory_sha256": calculated, "metadata_census_source": deepcopy(source),
            "review_evidence_hashes": evidence, "admission_granted": False}


def _utc(value):
    if type(value) is not str:
        raise ValueError("SUPPORTED_ENTRY_AWARE_M5_TIMESTAMP")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("SUPPORTED_ENTRY_AWARE_M5_TIMESTAMP") from None
    if result.tzinfo is None:
        raise ValueError("SUPPORTED_ENTRY_AWARE_M5_TIMESTAMP")
    result = result.astimezone(timezone.utc)
    if result.second or result.microsecond or result.minute % 5:
        raise ValueError("SUPPORTED_ENTRY_AWARE_M5_TIMESTAMP")
    return result


def _validate_row(row, pair):
    if (type(row) is not dict or row.get("instrument") != pair or row.get("pair", pair) != pair or
            row.get("complete") is not True or row.get("granularity", "M5") != "M5" or
            row.get("smooth", False) is not False or row.get("smoothed", False) is not False):
        raise ValueError("SUPPORTED_ENTRY_COMPLETE_UNSMOOTHED_PAIR_M5_REQUIRED")
    stamp = _utc(row.get("timestamp"))
    if "available_at" in row and _utc(row["available_at"]) != stamp + timedelta(minutes=5):
        raise ValueError("SUPPORTED_ENTRY_CLOSED_BAR_AVAILABILITY")
    for side in ("bid", "ask", "mid"):
        prices = row.get(side)
        if (type(prices) is not dict or set(prices) != {"o", "h", "l", "c"} or
                any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in prices.values()) or
                not prices["l"] <= min(prices["o"], prices["c"]) <= max(prices["o"], prices["c"]) <= prices["h"]):
            raise ValueError("SUPPORTED_ENTRY_FINITE_POSITIVE_OHLC_REQUIRED")
    for key in ("o", "h", "l", "c"):
        if row["ask"][key] < row["bid"][key]:
            raise ValueError("SUPPORTED_ENTRY_CROSSED_QUOTES")
    return stamp


def true_range(bar, previous_close):
    return max(bar["h"] - bar["l"], abs(bar["h"] - previous_close), abs(bar["l"] - previous_close))


def candidate_features(pair, rows, candidate, *, validate_bar=None):
    """Only in-memory completed inputs; excludes t from every lagged feature.

    A signal is available at t's close even if its next executable bar is absent.
    Native trade_path rejects that absence. Gap reset requires 289 new bars;
    no historical continuity or bar completion is fabricated.
    """
    if pair != "EUR_USD":
        raise ValueError("SUPPORTED_ENTRY_PAIR_OUTSIDE_FROZEN_SCOPE")
    if type(rows) is not list or (validate_bar is not None and not callable(validate_bar)):
        raise TypeError("SUPPORTED_ENTRY_ROWS_AND_EXISTING_BAR_VALIDATOR_REQUIRED")
    catalog = supported_entry_catalog_v1()
    if type(candidate) is not dict or candidate != catalog.spec_at(candidate.get("catalog_index")) or digest(candidate) != digest(catalog.spec_at(candidate.get("catalog_index"))):
        raise ValueError("SUPPORTED_ENTRY_FROZEN_CATALOG_MEMBER")
    threshold = candidate["implementation"]["compression_ratio_max"]
    previous_stamp, previous_close = None, None
    history, ranges = deque(maxlen=289), deque(maxlen=288)
    features, suppressed, segments, gaps = [], Counter(), 0, 0
    for index, row in enumerate(rows):
        if validate_bar is not None:
            validate_bar(row, pair)
        stamp = _validate_row(row, pair)
        if previous_stamp is not None and stamp <= previous_stamp:
            raise ValueError("SUPPORTED_ENTRY_ORDER_OR_DUPLICATE")
        if previous_stamp is None or stamp != previous_stamp + timedelta(minutes=5):
            if previous_stamp is not None:
                gaps += 1
            segments += 1
            history.clear(); ranges.clear(); previous_close = None
        # Provider-native mid OHLC is independently reported/rounded. Derive
        # the declared feature midpoint, retain the original row for execution.
        midpoint = {k: row["bid"][k]/2 + row["ask"][k]/2 for k in ("o", "h", "l", "c")}
        # All windows in this branch end at t-1; t is appended afterwards.
        if len(history) == 289 and len(ranges) == 288:
            recent = list(ranges)[-12:]
            median = statistics.median(ranges)
            atr = statistics.fmean(list(ranges)[-20:])
            if median <= 0 or atr <= 0:
                suppressed["ZERO_REFERENCE_OR_ATR"] += 1
            else:
                ratio = statistics.fmean(recent)/median
                box = list(history)[-12:]
                high = max(r["mid"]["h"] for r in box)
                low = min(r["mid"]["l"] for r in box)
                close = midpoint["c"]
                direction = 1 if close > high else -1 if close < low else 0
                if direction and (threshold is None or ratio <= threshold):
                    available = (stamp + timedelta(minutes=5)).isoformat()
                    week = stamp.date() - timedelta(days=stamp.weekday())
                    features.append({"event_id": "FXH02_SHARED_WEEK_" + week.isoformat(), "pair": pair,
                                     "signal_open": row["timestamp"], "available_at": available,
                                     "publication_available_at": available, "entry_index": index+1,
                                     "direction": direction, "atr": atr, "signal_row": deepcopy(row),
                                     "body_atr": abs(close-midpoint["o"])/atr,
                                     "compression_ratio": ratio, "range_high": high, "range_low": low,
                                     "feature_as_of_index": index-1, "context_start": history[0]["timestamp"],
                                     "context_sha256": digest(list(history))})
                elif direction:
                    suppressed["COMPRESSION_FILTER"] += 1
                else:
                    suppressed["NO_STRICT_CLOSE_BREAKOUT"] += 1
        else:
            suppressed["WARMUP"] += 1
        if previous_close is not None:
            ranges.append(true_range(midpoint, previous_close))
        history.append({"timestamp": row["timestamp"], "mid": midpoint})
        previous_close, previous_stamp = midpoint["c"], stamp
    return features, [{"kind": "FXH02_LAGGED_ENTRY_FEATURE_ACCOUNTING_V1",
                       "catalog_index": candidate["catalog_index"],
                       "implementation_fingerprint": candidate["implementation_sha256"],
                       "signals": len(features), "segments": segments, "gap_reset_count": gaps,
                       "suppressed": dict(suppressed), "warmup_bars": 289,
                       "inference_unit": "SHARED_UTC_WEEK_NOT_INDEPENDENT_BARS",
                       "market_admitted": False, "market_calls": 0, "measured_profitability": None}]
