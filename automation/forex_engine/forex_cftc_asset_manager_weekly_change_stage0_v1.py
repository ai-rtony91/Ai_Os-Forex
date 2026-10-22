"""PKT-FOREX-035: no-market-outcome CFTC asset-manager change gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any


PACKET_ID = "PKT-FOREX-035"
STRATEGY_ID = "CFTC_ASSET_MANAGER_WEEKLY_CHANGE_RESPONSE_V1"
ACCESS_DATE = "2026-09-05"
INFORMATION_CORPUS_ID = "AIOS_FOREX_INFORMATION_CORPUS_V1"
INFORMATION_CORPUS_SHA256 = "57da729226ebd675d7c79f182510f0612fc2f93cd0f20a05abed64243163d854"
INFORMATION_MANIFEST_SHA256 = "eb3a29a609ffd358d2843447786b8725e0feb0d7708dafc8ec0055974b866d11"
CFTC_2024_SHA256 = "da38711d098adc7f796871572d394e2747711cc2237871eb8fc8b7b98c0fc122"
CFTC_2025_SHA256 = "61e167d144a0366e16cace4eb7518b4d618bc5c99d97b71ca3c9eb99c43bbbe0"
H1_CORPUS_ID = "AIOS_FOREX_MULTI_REGIME_CORPUS_V3"
H1_CORPUS_SHA256 = "4357f24113ba54b9a6f8d6a3d87860109ca7429dbbd627b20c3d5a30540c6b32"
EXPECTED_MECHANISM_FINGERPRINT = "e2565e2d94c7411c43f57dc3bbd2d6559f25991f9f07b852a5e447c7f02227d5"
PRIOR_ATTEMPTS = 1210
PRIOR_AFTER_COST_CANDIDATES = 158
DEVELOPMENT_START = datetime(2024, 7, 1, tzinfo=timezone.utc)
DEVELOPMENT_END = datetime(2025, 4, 1, tzinfo=timezone.utc)
VALIDATION_END = datetime(2026, 1, 1, tzinfo=timezone.utc)

COVERAGE_MAP = {
    "AUSTRALIAN DOLLAR": {"currency": "AUD", "pair": "AUD_USD", "positive_foreign_signal_pair_side": "LONG"},
    "BRITISH POUND": {"currency": "GBP", "pair": "GBP_USD", "positive_foreign_signal_pair_side": "LONG"},
    "CANADIAN DOLLAR": {"currency": "CAD", "pair": "USD_CAD", "positive_foreign_signal_pair_side": "SHORT"},
    "EURO FX": {"currency": "EUR", "pair": "EUR_USD", "positive_foreign_signal_pair_side": "LONG"},
    "JAPANESE YEN": {"currency": "JPY", "pair": "USD_JPY", "positive_foreign_signal_pair_side": "SHORT"},
    "MEXICAN PESO": {"currency": "MXN", "pair": "USD_MXN", "positive_foreign_signal_pair_side": "SHORT"},
    "NZ DOLLAR": {"currency": "NZD", "pair": "NZD_USD", "positive_foreign_signal_pair_side": "LONG"},
    "SO AFRICAN RAND": {"currency": "ZAR", "pair": "USD_ZAR", "positive_foreign_signal_pair_side": "SHORT"},
    "SWISS FRANC": {"currency": "CHF", "pair": "USD_CHF", "positive_foreign_signal_pair_side": "SHORT"},
}
EXCHANGE_SUFFIX = " - CHICAGO MERCANTILE EXCHANGE"
CURRENCY_TO_CONTRACT = {value["currency"]: market for market, value in COVERAGE_MAP.items()}
DIRECT_PAIRS = tuple(sorted(value["pair"] for value in COVERAGE_MAP.values()))
EXPECTED_CERTIFIED_PAIR_COUNT = 58
EXPECTED_ELIGIBLE_PAIR_COUNT = 33
VARIANTS = (
    "ORIGINAL_LONG_CONTINUATION",
    "EXACT_REVERSED_SHORT",
    "ORIGINAL_SHORT_CONTINUATION",
    "EXACT_REVERSED_LONG",
    "SYMMETRIC_BIDIRECTIONAL",
)
HOLDING_HOURS = (6, 12)
FOLD_ENDS = (
    datetime(2024, 8, 27, tzinfo=timezone.utc),
    datetime(2024, 10, 15, tzinfo=timezone.utc),
    datetime(2024, 11, 26, tzinfo=timezone.utc),
    datetime(2025, 1, 7, tzinfo=timezone.utc),
    datetime(2025, 2, 18, tzinfo=timezone.utc),
    DEVELOPMENT_END,
)

MECHANISM_DESCRIPTOR = {
    "costs": "EXECUTABLE_BID_ASK_PLUS_0_10_PIP_PER_SIDE_BASE_AND_0_50_PIP_PER_SIDE_STRESS",
    "cftc_contract_map": CURRENCY_TO_CONTRACT,
    "pair_mapping_rule": "AUDIT_ALL_58_THEN_USE_EVERY_PAIR_WITH_USD_NEUTRAL_OR_BOTH_NON_USD_LEGS_CFTC_MAPPED;PAIR_SIGNAL_EQUALS_BASE_Z_MINUS_QUOTE_Z",
    "expected_pair_counts": {"certified": EXPECTED_CERTIFIED_PAIR_COUNT, "eligible": EXPECTED_ELIGIBLE_PAIR_COUNT, "direct_usd": 9, "derived_cross": 24},
    "dataset": "FROZEN_CFTC_TFF_2024_2025_PLUS_CERTIFIED_58_PAIR_H1_PRE_2026",
    "direction_variants": list(VARIANTS),
    "entry": "MONDAY_07_UTC_H1_EXECUTABLE_OPEN",
    "exit": "6_OR_12_H1_TIME_EXIT_OR_1_5_ATR_STOP_NO_PROFIT_TARGET",
    "family": STRATEGY_ID,
    "feature": "26_REPORT_CAUSAL_ZSCORE_OF_WEEKLY_CHANGE_IN_ASSET_MANAGER_NET_DIVIDED_BY_OPEN_INTEREST_USING_ONLY_PRIOR_REPORTS_FOR_NORMALIZATION",
    "mechanism": "WEEKLY_CHANGE_IN_PUBLIC_TFF_ASSET_MANAGER_NET_POSITION_MAY_IMPOUND_PERSISTENT_INFORMATION_OR_TEMPORARY_HEDGING_PRESSURE",
    "portfolio": "EQUAL_EXECUTABLE_RISK_ACROSS_ALL_CAUSALLY_MAPPABLE_CERTIFIED_PAIRS;TOTAL_BASKET_RISK_0_25_PERCENT;PAIR_CAP_0_25_PERCENT_DIVIDED_BY_33;CURRENCY_GROSS_EXPOSURE_CAP_0_10_PERCENT",
}

REJECTED_FAMILIES = {
    "AIOS_FOREX_CFTC_CROWDING_UNWIND_PRICE_CONFIRMATION_REJECTION_V1.json": "36337f8f9fd6dd3f35b947abe57a27bbdef0dd73bd699651f29395b342d4f605",
    "AIOS_FOREX_CFTC_POSITIONING_ACCELERATION_PRICE_CONTINUATION_REJECTION_V1.json": "2b120c891b697c3929c44589d44d6723f24a7a31744decfc1eabce493129c8e2",
    "AIOS_FOREX_CFTC_PARTICIPANT_DIVERGENCE_PRICE_CONFIRMATION_REJECTION_V1.json": "c9c69f2b15c87a6234bf7c70e6f9c04c2ab2bd178f24f7bd7ec64f988cf93fc4",
    "AIOS_FOREX_CFTC_DEALER_INVENTORY_PRESSURE_REVERSAL_REJECTION_V1.json": "c752c2b986583c4460c01be3c092a803cbf4363e6405eb52a25c4216558f8dfb",
}

PROMOTION_RECEIPT_SHA256 = "345295f9ff2029424479a73b1601418ffa0ae2accce968396bd8fae5858caddc"
PROMOTION_AGGREGATE_SHA256 = "ba7a446a36a17c3497edd1d4efe500ac7768ba2d0733d6fe748380ff47e5d62c"
ROLLBACK_MANIFEST_SHA256 = "65e8c9d2eccead9ff57b0eca9897ee2c873fc61ee0e2a18693886b67cdc53821"


def canonical_bytes(value: Any, *, compact: bool = False) -> bytes:
    options = {"sort_keys": True, "ensure_ascii": True, "allow_nan": False}
    text = json.dumps(value, separators=(",", ":"), **options) if compact else json.dumps(value, indent=2, **options)
    return (text + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mechanism_fingerprint() -> str:
    value = sha256_bytes(canonical_bytes(MECHANISM_DESCRIPTOR, compact=True))
    if EXPECTED_MECHANISM_FINGERPRINT and value != EXPECTED_MECHANISM_FINGERPRINT:
        raise RuntimeError("MECHANISM_FINGERPRINT_MISMATCH")
    return value


def market_currency(coverage: str) -> str:
    for market, mapping in COVERAGE_MAP.items():
        if coverage == market + EXCHANGE_SUFFIX:
            return mapping["currency"]
    raise ValueError(f"UNMAPPED_OR_INELIGIBLE_CFTC_MARKET:{coverage}")


def positive_foreign_signal_pair_side(currency: str) -> tuple[str, int]:
    matches = [value for value in COVERAGE_MAP.values() if value["currency"] == currency]
    if len(matches) != 1:
        raise ValueError(f"UNMAPPED_OR_DUPLICATE_CURRENCY:{currency}")
    value = matches[0]
    return value["pair"], 1 if value["positive_foreign_signal_pair_side"] == "LONG" else -1


def pair_eligibility_rows(pair_names: list[str]) -> list[dict[str, Any]]:
    rows = []
    for pair in sorted(pair_names):
        base, quote = pair.split("_")
        base_contract = CURRENCY_TO_CONTRACT.get(base)
        quote_contract = CURRENCY_TO_CONTRACT.get(quote)
        eligible = (base == "USD" or base_contract is not None) and (quote == "USD" or quote_contract is not None)
        if eligible and "USD" in (base, quote):
            mapping_type = "DIRECT_USD_MAPPING"
        elif eligible:
            mapping_type = "DERIVED_CROSS_BASE_MINUS_QUOTE"
        else:
            mapping_type = "UNSUPPORTED"
        if not eligible:
            formula = "NONE"
        elif base == "USD":
            formula = f"0_MINUS_Z_{quote}"
        elif quote == "USD":
            formula = f"Z_{base}_MINUS_0"
        else:
            formula = f"Z_{base}_MINUS_Z_{quote}"
        missing = [currency for currency in (base, quote) if currency != "USD" and currency not in CURRENCY_TO_CONTRACT]
        rows.append({
            "pair": pair,
            "base_currency": base,
            "quote_currency": quote,
            "base_cftc_contract": base_contract or "NONE",
            "quote_cftc_contract": quote_contract or "NONE",
            "usd_treatment": "BASE_USD_NEUTRAL" if base == "USD" else ("QUOTE_USD_NEUTRAL" if quote == "USD" else "NO_USD_LEG"),
            "point_in_time_publication_lag": "FRIDAY_21_30_UTC_TO_NEXT_MONDAY_07_00_UTC" if eligible else "NOT_APPLICABLE",
            "mapping_formula": formula,
            "mapping_type": mapping_type,
            "eligible": eligible,
            "exclusion_reason": "NONE" if eligible else "MISSING_POINT_IN_TIME_CFTC_CONTRACT:" + ",".join(missing),
        })
    return rows


def eligible_pairs(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(row["pair"] for row in rows if row["eligible"])


def pair_signal_inventory(pair: str, inventories: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    base, quote = pair.split("_")
    base_by_decision = {} if base == "USD" else {item["decision"]: item for item in inventories[base]}
    quote_by_decision = {} if quote == "USD" else {item["decision"]: item for item in inventories[quote]}
    if base == "USD":
        decisions = set(quote_by_decision)
    elif quote == "USD":
        decisions = set(base_by_decision)
    else:
        decisions = set(base_by_decision) & set(quote_by_decision)
    values = []
    for decision in sorted(decisions):
        base_item = base_by_decision.get(decision)
        quote_item = quote_by_decision.get(decision)
        base_z = 0.0 if base == "USD" else base_item["zscore"]
        quote_z = 0.0 if quote == "USD" else quote_item["zscore"]
        source_items = [item for item in (base_item, quote_item) if item is not None]
        values.append({
            "pair": pair,
            "base_currency": base,
            "quote_currency": quote,
            "decision": decision,
            "source_available": max(item["source_available"] for item in source_items),
            "source_observation": max(item["source_observation"] for item in source_items),
            "base_zscore": base_z,
            "quote_zscore": quote_z,
            "pair_zscore": base_z - quote_z,
            "base_weekly_change": 0.0 if base == "USD" else base_item["weekly_change"],
            "quote_weekly_change": 0.0 if quote == "USD" else quote_item["weekly_change"],
            "pair_weekly_change": (0.0 if base == "USD" else base_item["weekly_change"]) - (0.0 if quote == "USD" else quote_item["weekly_change"]),
            "base_normalized_net": 0.0 if base == "USD" else base_item["normalized_net"],
            "quote_normalized_net": 0.0 if quote == "USD" else quote_item["normalized_net"],
            "pair_normalized_net": (0.0 if base == "USD" else base_item["normalized_net"]) - (0.0 if quote == "USD" else quote_item["normalized_net"]),
        })
    return values


def candidate_definitions() -> list[dict[str, Any]]:
    parent = mechanism_fingerprint()
    values = []
    for variant in VARIANTS:
        for holding in HOLDING_HOURS:
            definition = {
                "candidate_id": f"CFTC-AM-WC-{variant}-H{holding}",
                "variant": variant,
                "maximum_holding_h1": holding,
                "zscore_lookback_reports": 26,
                "stop_atr": 1.5,
                "take_profit": None,
            }
            values.append({
                **definition,
                "candidate_fingerprint": sha256_bytes(canonical_bytes({"mechanism_fingerprint": parent, "definition": definition}, compact=True)),
            })
    return values


def next_monday_07(available: datetime) -> datetime:
    available = available.astimezone(timezone.utc)
    candidate = available.replace(hour=7, minute=0, second=0, microsecond=0)
    candidate += timedelta(days=(7 - candidate.weekday()) % 7)
    if candidate <= available:
        candidate += timedelta(days=7)
    if candidate.weekday() != 0 or candidate.hour != 7 or candidate <= available:
        raise RuntimeError("DECISION_TIME_CONSTRUCTION_FAILED")
    return candidate


def causal_zscore(levels: list[float], current_index: int, lookback: int = 26) -> float:
    if current_index < lookback + 1 or current_index >= len(levels):
        raise ValueError("INSUFFICIENT_OR_INVALID_ZSCORE_INDEX")
    prior_changes = [levels[index] - levels[index - 1] for index in range(current_index - lookback, current_index)]
    current_change = levels[current_index] - levels[current_index - 1]
    deviation = pstdev(prior_changes)
    if deviation <= 0:
        raise ValueError("ZERO_PRIOR_CHANGE_DEVIATION")
    return (current_change - fmean(prior_changes)) / deviation


def fold_id(decision: datetime) -> int:
    if decision < DEVELOPMENT_START or decision >= DEVELOPMENT_END:
        raise ValueError("DECISION_OUTSIDE_DEVELOPMENT")
    for index, end in enumerate(FOLD_ENDS, start=1):
        if decision < end:
            return index
    raise RuntimeError("FOLD_ASSIGNMENT_FAILED")


def development_cftc_paths(repo_root: Path) -> tuple[tuple[Path, str], ...]:
    root = repo_root / ".aios/runtime/forex_information_corpus_v1/normalized"
    return ((root / "cftc_2024.json", CFTC_2024_SHA256), (root / "cftc_2025.json", CFTC_2025_SHA256))


def load_development_cftc(repo_root: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    corpus_root = repo_root / ".aios/runtime/forex_information_corpus_v1"
    manifest_path = corpus_root / "manifests/manifest.json"
    if sha256_file(manifest_path) != INFORMATION_MANIFEST_SHA256:
        raise RuntimeError("INFORMATION_MANIFEST_SHA256_MISMATCH")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["corpus_id"] != INFORMATION_CORPUS_ID or manifest["aggregate_hash"] != INFORMATION_CORPUS_SHA256:
        raise RuntimeError("INFORMATION_CORPUS_IDENTITY_MISMATCH")
    source_rows: list[dict[str, Any]] = []
    verified_sources = {}
    opened_paths = []
    for path, expected_hash in development_cftc_paths(repo_root):
        observed = sha256_file(path)
        if observed != expected_hash:
            raise RuntimeError(f"CFTC_SOURCE_HASH_MISMATCH:{path.name}")
        opened_paths.append(path.as_posix())
        verified_sources[path.name] = observed
        source_rows.extend(json.loads(path.read_text(encoding="utf-8")))
    if any("2026" in Path(path).name for path in opened_paths):
        raise RuntimeError("FINAL_HOLDOUT_CFTC_PATH_OPENED")
    histories: dict[str, list[dict[str, Any]]] = {value["currency"]: [] for value in COVERAGE_MAP.values()}
    eligible_coverages = {market + EXCHANGE_SUFFIX for market in COVERAGE_MAP}
    for row in source_rows:
        if row["coverage"] not in eligible_coverages:
            continue
        available = datetime.fromisoformat(row["available_to_strategy_utc"])
        if available >= DEVELOPMENT_END:
            continue
        currency = market_currency(row["coverage"])
        if row["open_interest"] <= 0 or min(row["asset_manager_long"], row["asset_manager_short"]) < 0:
            raise RuntimeError(f"INVALID_CFTC_POSITION_ROW:{currency}")
        histories[currency].append({
            "available": available,
            "observation": datetime.fromisoformat(row["observation_utc"]),
            "normalized_net": (row["asset_manager_long"] - row["asset_manager_short"]) / row["open_interest"],
        })
    for currency, values in histories.items():
        values.sort(key=lambda item: (item["available"], item["observation"]))
        if len(values) != len({item["observation"] for item in values}):
            raise RuntimeError(f"DUPLICATE_CFTC_OBSERVATION:{currency}")
    return histories, {
        "manifest_sha256": sha256_file(manifest_path),
        "verified_source_hashes": verified_sources,
        "opened_normalized_paths": opened_paths,
        "opened_normalized_artifact_count": len(opened_paths),
        "final_holdout_artifacts_opened": 0,
    }


def signal_inventory(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    levels = [row["normalized_net"] for row in history]
    values = []
    for current_index in range(27, len(history)):
        decision = next_monday_07(history[current_index]["available"])
        if decision < DEVELOPMENT_START or decision >= DEVELOPMENT_END:
            continue
        values.append({
            "decision": decision,
            "source_available": history[current_index]["available"],
            "source_observation": history[current_index]["observation"],
            "normalized_net": levels[current_index],
            "weekly_change": levels[current_index] - levels[current_index - 1],
            "zscore": causal_zscore(levels, current_index),
        })
    return values


def rejection_memory_audit(repo_root: Path) -> dict[str, Any]:
    prior_family_fingerprints = set()
    prior_candidate_fingerprints = set()
    records = []
    for name, expected_family in REJECTED_FAMILIES.items():
        path = repo_root / "Reports/forex_delivery" / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidates = payload.get("candidate_rows", {})
        candidate_fingerprints = {row["candidate_fingerprint"] for row in candidates.values()}
        valid = (
            payload.get("status") == "POSTMORTEM_COMPLETE_REJECTED"
            and payload.get("family_fingerprint") == expected_family
            and payload.get("candidate_count") == len(candidates) == len(candidate_fingerprints) == 12
        )
        if not valid:
            raise RuntimeError(f"REJECTION_MEMORY_INVALID:{name}")
        prior_family_fingerprints.add(expected_family)
        prior_candidate_fingerprints.update(candidate_fingerprints)
        records.append({
            "path": path.relative_to(repo_root).as_posix(),
            "sha256": sha256_file(path),
            "family": payload["family"],
            "family_fingerprint": expected_family,
            "candidate_fingerprint_count": len(candidate_fingerprints),
            "status": payload["status"],
        })
    current_candidates = {row["candidate_fingerprint"] for row in candidate_definitions()}
    collisions = sorted(current_candidates & prior_candidate_fingerprints)
    return {
        "rejected_family_count": len(prior_family_fingerprints),
        "rejected_candidate_fingerprint_count": len(prior_candidate_fingerprints),
        "records": records,
        "current_family_collision": mechanism_fingerprint() in prior_family_fingerprints,
        "current_candidate_collisions": collisions,
        "status": "PASS" if len(prior_family_fingerprints) == 4 and len(prior_candidate_fingerprints) == 48 and not collisions and mechanism_fingerprint() not in prior_family_fingerprints else "FAIL",
    }


def predecessor_promotion_audit(repo_root: Path) -> dict[str, Any]:
    root = repo_root / ".aios/staging/PKT_FOREX_019_022_R1/revision2"
    receipt_path = root / "PKT_FOREX_019_022_R1_CORRECTIVE_PROMOTION_RECEIPT.json"
    completion_path = root / "PKT_FOREX_019_022_R1_PROMOTION_COMPLETION.json"
    rollback_path = root / "prepromotion_rollback/ROLLBACK_MANIFEST.json"
    if sha256_file(receipt_path) != PROMOTION_RECEIPT_SHA256:
        raise RuntimeError("PREDECESSOR_PROMOTION_RECEIPT_MISMATCH")
    if sha256_file(rollback_path) != ROLLBACK_MANIFEST_SHA256:
        raise RuntimeError("PREDECESSOR_ROLLBACK_MANIFEST_MISMATCH")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
    packet_map = (
        ("CROWDING_UNWIND", "PKT019"),
        ("POSITIONING_ACCELERATION", "PKT020"),
        ("PARTICIPANT_DIVERGENCE", "PKT021"),
        ("DEALER_INVENTORY", "PKT022"),
    )
    rows = []
    for artifact in rollback["artifacts"]:
        destination = repo_root / artifact["canonical_destination"]
        packet = next(packet for token, packet in packet_map if token in destination.name)
        if ".aios/runtime/" in artifact["canonical_destination"]:
            source = root / packet / "promotion/runtime" / destination.name
        elif "REJECTION" in destination.name:
            source = root / packet / "promotion/rejection.json"
        else:
            source = root / packet / "promotion/report.md"
        canonical_payload = destination.read_bytes()
        staged_payload = source.read_bytes()
        rows.append({
            "canonical_destination": artifact["canonical_destination"],
            "canonical_sha256": sha256_bytes(canonical_payload),
            "staged_sha256": sha256_bytes(staged_payload),
            "bytes": len(canonical_payload),
            "byte_identical": canonical_payload == staged_payload,
        })
    aggregate_lines = [
        f"{row['canonical_destination']}:{row['canonical_sha256']}:{row['bytes']}"
        for row in sorted(rows, key=lambda item: item["canonical_destination"])
    ]
    aggregate = sha256_bytes("\n".join(aggregate_lines).encode("utf-8"))
    valid = (
        len(rows) == 32
        and len({row["canonical_destination"] for row in rows}) == 32
        and all(row["byte_identical"] for row in rows)
        and aggregate == PROMOTION_AGGREGATE_SHA256
        and receipt["aggregate_promotion_sha256"] == PROMOTION_AGGREGATE_SHA256
        and completion["canonical_aggregate_sha256"] == PROMOTION_AGGREGATE_SHA256
        and completion["canonical_artifact_count"] == 32
        and completion["rollback_manifest_sha256"] == ROLLBACK_MANIFEST_SHA256
    )
    return {
        "receipt_path": receipt_path.relative_to(repo_root).as_posix(),
        "receipt_sha256": sha256_file(receipt_path),
        "rollback_manifest_path": rollback_path.relative_to(repo_root).as_posix(),
        "rollback_manifest_sha256": sha256_file(rollback_path),
        "canonical_artifact_count": len(rows),
        "byte_identical_artifact_count": sum(row["byte_identical"] for row in rows),
        "mismatches": [row for row in rows if not row["byte_identical"]],
        "canonical_aggregate_sha256": aggregate,
        "status": "PASS" if valid else "FAIL",
    }


def build_source_registry() -> dict[str, Any]:
    common = {
        "claimed_performance": "UNVERIFIED_NOT_ACCEPTED_AS_EDGE_EVIDENCE",
        "source_code_exists": False,
        "existing_fingerprint_match": False,
        "aios_dataset_compatibility": "INDEPENDENT_POINT_IN_TIME_RECONSTRUCTION_REQUIRED_ON_FROZEN_CFTC_AND_CERTIFIED_H1_CORPORA",
    }
    return {
        "schema": "AIOS_FOREX_HYPOTHESIS_SOURCE_REGISTRY_SUPPLEMENT.v1",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "evidence_role": "HYPOTHESIS_INPUT_AND_COUNTEREVIDENCE_ONLY_NOT_EDGE_PROOF",
        "sources": [
            {
                **common,
                "source_id": "CFTC_TFF_EXPLANATORY_NOTES",
                "url": "https://www.cftc.gov/idc/groups/public/@commitmentsoftraders/documents/file/tfmexplanatorynotes.pdf",
                "title": "Traders in Financial Futures Explanatory Notes",
                "author_or_organization": "U.S. Commodity Futures Trading Commission",
                "publication_date": "2010",
                "access_date": ACCESS_DATE,
                "source_type": "OFFICIAL_DATA_DOCUMENTATION",
                "claimed_economic_mechanism": "ASSET_MANAGER_INSTITUTIONAL_CATEGORY_IDENTIFIES_LONG_HORIZON_INSTITUTIONAL_FUTURES_POSITIONING",
                "claimed_market_and_timeframe": "WEEKLY_FINANCIAL_FUTURES_POSITIONING",
                "exact_disclosed_rules": "CATEGORY_AND_REPORT_SEMANTICS_ONLY_NO_TRADING_RULE",
                "costs_included": False,
                "walk_forward_included": False,
                "license": "US_GOVERNMENT_PUBLIC_INFORMATION_NO_CODE_ADAPTED",
                "replication_risks": ["FUTURES_POSITIONING_IS_NOT_SPOT_ORDER_FLOW", "CATEGORY_AGGREGATION", "PUBLICATION_LAG"],
                "research_priority": "PRIMARY_DATA_SEMANTICS",
                "final_disposition": "ELIGIBLE_OFFICIAL_INPUT_NOT_EDGE_PROOF",
            },
            {
                **common,
                "source_id": "BIS_WORKING_PAPER_405_CUSTOMER_FLOWS",
                "url": "https://www.bis.org/publ/work405.pdf",
                "title": "Information flows in foreign exchange markets: dissecting customer currency trades",
                "author_or_organization": "Dagfinn Rime; Lucio Sarno; Elvira Sojli / Bank for International Settlements",
                "publication_date": "2013-03",
                "access_date": ACCESS_DATE,
                "source_type": "INSTITUTIONAL_RESEARCH_PAPER",
                "claimed_economic_mechanism": "LONG_TERM_INVESTMENT_MANAGER_FLOW_CAN_REFLECT_INFORMATION_OR_PRICE_PRESSURE",
                "claimed_market_and_timeframe": "CUSTOMER_FX_ORDER_FLOW_DAILY_TO_LONGER_HORIZONS",
                "exact_disclosed_rules": "ECONOMETRIC_EVIDENCE_ONLY_AIOS_DEFINES_AN_INDEPENDENT_WEEKLY_RULE",
                "costs_included": "NOT_A_RETAIL_EXECUTION_BACKTEST",
                "walk_forward_included": "NO_FORMAL_AIOS_EQUIVALENT",
                "license": "BIS_PUBLICATION_COPYRIGHT_NO_CODE_ADAPTED",
                "replication_risks": ["CUSTOMER_FLOW_DIFFERS_FROM_PUBLIC_FUTURES_POSITIONING", "NO_EXECUTABLE_RULE"],
                "research_priority": "MECHANISM_SUPPORT_WITH_CAUTION",
                "final_disposition": "ELIGIBLE_HYPOTHESIS_SUPPORT_UNVERIFIED",
            },
            {
                **common,
                "source_id": "FROOT_RAMADORAI_2002_INSTITUTIONAL_FLOWS",
                "url": "https://www.nber.org/papers/w9080",
                "title": "Currency Returns, Institutional Investor Flows, and Exchange Rate Fundamentals",
                "author_or_organization": "Kenneth A. Froot; Tarun Ramadorai / National Bureau of Economic Research",
                "publication_date": "2002-08",
                "access_date": ACCESS_DATE,
                "source_type": "ACADEMIC_WORKING_PAPER",
                "claimed_economic_mechanism": "INSTITUTIONAL_FLOWS_MAY_FORECAST_RETURNS_THROUGH_INFORMATION_OR_TRANSITORY_PRICE_PRESSURE",
                "claimed_market_and_timeframe": "INSTITUTIONAL_CURRENCY_FLOWS_MULTIPLE_HORIZONS",
                "exact_disclosed_rules": "ECONOMETRIC_EVIDENCE_ONLY_NOT_A_COMPLETE_TRADING_RULE",
                "costs_included": "NOT_A_RETAIL_EXECUTION_BACKTEST",
                "walk_forward_included": "NO_FORMAL_AIOS_EQUIVALENT",
                "license": "NBER_PAPER_COPYRIGHT_NO_CODE_ADAPTED",
                "replication_risks": ["PROPRIETARY_FLOW_PROXY", "OLD_SAMPLE", "PUBLIC_CFTC_PROXY_MISMATCH"],
                "research_priority": "MECHANISM_SUPPORT_AND_DIRECTIONAL_AMBIGUITY",
                "final_disposition": "JUSTIFIES_PAIRED_CONTINUATION_AND_EXACT_REVERSE_TEST",
            },
            {
                **common,
                "source_id": "KREMENS_SPECULATOR_RISK_PLACEBO",
                "url": "https://foster.uw.edu/wp-content/uploads/2019/10/Speculator-Risk-Betting-with-Price-Impact-in-Currency-Markets.pdf",
                "title": "Speculator Risk: Betting with Price Impact in Currency Markets",
                "author_or_organization": "Lukas Kremens",
                "publication_date": "2019",
                "access_date": ACCESS_DATE,
                "source_type": "ACADEMIC_WORKING_PAPER_COUNTEREVIDENCE",
                "claimed_economic_mechanism": "LEVERAGED_FUND_UNWINDS_CAN_AFFECT_CURRENCY_RISK_WHILE_INSTITUTIONAL_ASSET_MANAGER_POSITIONS_ARE_A_PLACEBO",
                "claimed_market_and_timeframe": "NINE_CURRENCIES_WEEKLY_CFTC_2006_TO_2017",
                "exact_disclosed_rules": "PAPER_REPORTS_ASSET_MANAGER_POSITIONS_DO_NOT_PREDICT_NEXT_WEEK_CURRENCY_EQUITY_RISK_EXPOSURES; THIS_IS_NOT_THE_SAME_RETURN_TARGET_BUT_IS_DIRECT_WEAK_PREDICTOR_COUNTEREVIDENCE",
                "costs_included": "ASK_BID_FOR_DIFFERENT_HEDGE_FUND_STRATEGY_NOT_ASSET_MANAGER_PLACEBO",
                "walk_forward_included": False,
                "license": "AUTHOR_WORKING_PAPER_COPYRIGHT_NO_CODE_ADAPTED",
                "replication_risks": ["TARGET_IS_RISK_EXPOSURE_NOT_DIRECT_H1_RETURN", "OLDER_SAMPLE", "ASSET_MANAGER_LEVEL_NOT_EXACT_CHANGE_ZSCORE"],
                "research_priority": "HIGH_COUNTEREVIDENCE",
                "final_disposition": "WEAK_PREDICTOR_PLACEBO_EVIDENCE_REQUIRES_FAST_FALSIFICATION_AND_NO_PARAMETER_RESCUE",
            },
            {
                **common,
                "source_id": "FXABSOLUTE_EDGE_GUIDE",
                "url": "https://fxabsolute.com/how-to-build-trading-edge",
                "title": "How to Build a Trading Edge in Forex",
                "author_or_organization": "FXAbsolute",
                "publication_date": "NOT_DISCLOSED",
                "access_date": ACCESS_DATE,
                "source_type": "COMMERCIAL_EDUCATIONAL_GUIDE",
                "claimed_economic_mechanism": "NONE",
                "claimed_market_and_timeframe": "GENERAL_FOREX_PROCESS",
                "exact_disclosed_rules": "PROCESS_GUIDANCE_ONLY_DEFINE_EXACT_RULES_RECORD_ALL_TRADES_AND_TEST_ACROSS_CONDITIONS",
                "costs_included": "NOT_SPECIFIED",
                "walk_forward_included": "PARTIAL_UNTOUCHED_DATA_GUIDANCE_NOT_FORMAL_WALK_FORWARD",
                "license": "NO_EXPLICIT_LICENSE_STATED_NO_CODE_ADAPTED",
                "replication_risks": ["COMMERCIAL_SOURCE", "MARKETING_CLAIMS_UNVERIFIED", "NO_STRATEGY_EDGE_EVIDENCE"],
                "research_priority": "PROCESS_GUIDANCE_ONLY",
                "final_disposition": "METHODOLOGY_ONLY_UNVERIFIED_NOT_EDGE_PROOF",
            },
        ],
        "unsupported_claims": [
            "NO_SOURCE_PROVES_AFTER_COST_PUBLIC_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_EXPECTANCY",
            "CONTINUATION_AND_REVERSAL_DIRECTIONS_ARE_BOTH_UNVERIFIED",
            "KREMENS_PLACEBO_EVIDENCE_TARGETS_RISK_EXPOSURE_NOT_THIS_EXACT_RETURN_RULE",
            "NO_EXTERNAL_RESULT_REPLACES_AIOS_WALK_FORWARD_COST_AND_HOLDOUT_VALIDATION",
        ],
        "status": "PASS_SOURCES_SUPPORT_AND_PLACEBO_COUNTEREVIDENCE_RECORDED",
    }


def grouping_inventory(pair_names: list[str], mapped_pairs: tuple[str, ...]) -> dict[str, Any]:
    directed = sorted([f"{pair}:BASE_TO_QUOTE" for pair in pair_names] + [f"{pair}:QUOTE_TO_BASE" for pair in pair_names])
    currencies = sorted({currency for pair in pair_names for currency in pair.split("_")})
    shared_base = {currency: sorted(pair for pair in pair_names if pair.startswith(currency + "_")) for currency in currencies}
    shared_quote = {currency: sorted(pair for pair in pair_names if pair.endswith("_" + currency)) for currency in currencies}
    currency_exposure = {currency: sorted(pair for pair in pair_names if currency in pair.split("_")) for currency in currencies}
    edges = {frozenset(pair.split("_")) for pair in pair_names}
    triangles = []
    for first_index, first in enumerate(currencies):
        for second_index in range(first_index + 1, len(currencies)):
            second = currencies[second_index]
            for third in currencies[second_index + 1:]:
                if all(frozenset(edge) in edges for edge in ((first, second), (first, third), (second, third))):
                    triangles.append([first, second, third])
    return {
        "certified_pair_count": len(pair_names),
        "individual_pairs": sorted(pair_names),
        "one_portfolio_all_cftc_eligible_pairs": list(mapped_pairs),
        "shared_base_groups": shared_base,
        "shared_quote_groups": shared_quote,
        "currency_exposure_groups": currency_exposure,
        "directed_pair_relationship_count": len(directed),
        "directed_pair_relationships": directed,
        "undirected_pair_relationship_count": len(pair_names),
        "valid_currency_triangles": triangles,
        "cross_sectional_cftc_eligible_pairs": list(mapped_pairs),
        "session_groups": ["MONDAY_07_UTC_ENTRY"],
        "volatility_and_regime_groups": "SUPPORTED_AS_REPORTING_DIMENSIONS_NOT_STAGE0_FILTERS",
        "synchronized_subminute_group": ["EUR_USD", "GBP_USD", "USD_JPY"],
        "subminute_scope": "SEPARATE_CERTIFIED_S5_S10_S15_S30_M1_M2_M4_CORPUS_NOT_USED_BY_THIS_WEEKLY_H1_MECHANISM",
        "major_minor_regional_grouping": "REQUIRES_EXPLICIT_MECHANISM_SPECIFIC_TAXONOMY_NOT_INVENTED",
        "duplicate_counting_control": "CANONICAL_PAIR_NAMES_AND_UNORDERED_TRIANGLE_EDGE_SETS",
    }


def build_capability_audit(pair_names: list[str], mapped_pairs: tuple[str, ...]) -> dict[str, Any]:
    capabilities = {
        "immutable_dataset_contracts": ["PRESENT", "Frozen corpus identities and hashes are enforced."],
        "dataset_hash_cache": ["MISSING_UNIFIED", "Repeated hashing costs compute but does not invalidate prior byte-verified results."],
        "pair_universe_enumerator": ["PARTIAL_PACKET_LOCAL", "This packet enumerates all 58; no shared factory service exists."],
        "pair_grouping_enumerator": ["PARTIAL_PACKET_LOCAL", "This packet enumerates groups and triangles without market scoring."],
        "cftc_currency_to_pair_mapper": ["PRESENT_PACKET_LOCAL", "Supports USD-neutral direct mappings and causal base-minus-quote crosses."],
        "causal_timeframe_builder": ["PARTIAL_FRAGMENTED", "Strategy engines implement local completed-candle builders; no single governed interface."],
        "cross_pair_synchronization": ["PARTIAL_SPECIALIZED", "Present in specialized engines but not shared across the factory."],
        "completed_candle_enforcement": ["PRESENT", "Certified manifests and strategy engines enforce completed observations."],
        "direction_inversion": ["PRESENT_PACKET_LOCAL", "Exact reverse candidates preserve opportunities, timestamps, holds, exits, costs, and folds."],
        "bid_ask_cost_accounting": ["PRESENT", "Executable bid and ask are required."],
        "slippage_and_financing": ["PARTIAL", "Slippage is modeled; financing is not applicable to this intraday-flat experiment."],
        "exposure_and_currency_concentration": ["PARTIAL_PACKET_LOCAL", "Stage 1 must enforce pair and currency caps across derived crosses."],
        "global_trial_ledger": ["PARTIAL_FRAGMENTED_COUNTS", "Cumulative counts are governed but not exposed through one append-only engine."],
        "duplicate_fingerprint_gate": ["PRESENT", "Family and candidate hashes are checked against cumulative rejection memory."],
        "chronological_splits_purging_embargo_walk_forward": ["PARTIAL_STRATEGY_SPECIFIC", "Available in packet engines; no unified interface."],
        "parameter_stability_cost_stress_regime_decomposition": ["PARTIAL_STRATEGY_SPECIFIC", "Available after Stage 1; not one shared component."],
        "random_and_no_trade_baselines": ["PRESENT_PACKET_LOCAL", "Both are mandatory and zero expectancy cannot pass."],
        "multiple_testing_correction": ["PARTIAL_FRAGMENTED", "Global counts are preserved; unified PBO/deflated-Sharpe service is missing."],
        "deterministic_reproduction": ["PRESENT", "Two isolated byte-identical runs are mandatory."],
        "compact_early_failure_artifacts": ["PRESENT", "Stage 1 is bounded and produces compact evidence."],
        "automatic_postmortems": ["PARTIAL_STRATEGY_SPECIFIC", "Failure artifacts exist but orchestration is not unified."],
        "checkpoint_and_resume": ["PRESENT", "Hash-verified packet checkpoints are used."],
        "champion_selection": ["MISSING_UNIFIED", "No candidate may be called an edge until a governed selector exists."],
        "cryptographic_holdout_sealing": ["PARTIAL", "Holdout paths and zero-access checks exist; a unified one-use service is absent."],
    }
    return {
        "schema": "AIOS_FOREX_RESEARCH_FACTORY_CAPABILITY_AUDIT.v1",
        "packet_id": PACKET_ID,
        "capabilities": {name: {"status": value[0], "effect": value[1]} for name, value in capabilities.items()},
        "pair_and_grouping_engine": grouping_inventory(pair_names, mapped_pairs),
        "previous_result_impact": "NO_PROVEN_INVALIDATION_FROM_THIS_READ_ONLY_CAPABILITY_AUDIT; THE NINE_PAIR RESULT REMAINS VALID_FOR_ITS_PREREGISTERED_SCOPE BUT IS_NOT_THE_MAXIMUM_CAUSAL_CFTC_UNIVERSE",
        "successor_repair_packet_required": True,
        "successor_repair_scope": [
            "shared immutable dataset hash cache",
            "shared pair universe and grouping interface",
            "shared causal timeframe-role builder",
            "append-only global actual-trial ledger with search-adjusted statistics",
            "unified champion selector and single-use cryptographic holdout gate",
        ],
        "write_action": "NONE_OUTSIDE_CURRENT_AUTHORIZED_PACKET",
        "status": "PASS_GAPS_RECORDED_FOR_ONE_CONSOLIDATED_SUCCESSOR_REPAIR_PACKET",
    }


def build_preregistration(mapped_pairs: tuple[str, ...], pair_totals: dict[str, int]) -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_STRATEGY_PREREGISTRATION.v1",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_mechanism_fingerprint": mechanism_fingerprint(),
        "strategy_mechanism_descriptor": MECHANISM_DESCRIPTOR,
        "economic_mechanism": "Long-horizon asset-manager changes may carry slowly incorporated information or temporary hedging pressure; paired continuation and exact reversal variants distinguish those explanations, while published placebo evidence makes this a strict fast falsification.",
        "dataset": {
            "information_id": INFORMATION_CORPUS_ID,
            "information_sha256": INFORMATION_CORPUS_SHA256,
            "h1_id": H1_CORPUS_ID,
            "h1_sha256": H1_CORPUS_SHA256,
            "development": "2024-07-01T00:00:00Z/2025-04-01T00:00:00Z",
            "validation": "2025-04-01T00:00:00Z/2026-01-01T00:00:00Z_UNOPENED_UNLESS_STAGE1_SURVIVOR",
            "final_holdout": "2026_ROWS_SEALED_SINGLE_USE",
            "revision_behavior": "FROZEN_ANNUAL_CFTC_ARCHIVES_ONLY_NO_LATER_REVISION_OR_LIVE_QUERY",
        },
        "pair_universe": list(mapped_pairs),
        "pair_universe_rule": "Use every development-eligible certified H1 pair whose base and quote are USD-neutral or mapped to frozen point-in-time CFTC contracts.",
        "timeframes": {"positioning_signal": "WEEKLY_TFF", "execution": "H1", "confirmation": "NONE"},
        "signal_calculation": "For each mapped non-USD currency, compute (asset-manager long minus short)/open interest. Z-score its current weekly change against exactly 26 prior weekly changes using population standard deviation and exclude the current change from normalization. Set USD factor to zero. Pair signal is base-currency z-score minus quote-currency z-score.",
        "entry_rules": {
            "time": "first Monday 07:00 UTC H1 executable open strictly after Friday 21:30 UTC availability",
            "long": "positive pair-z original long or negative pair-z exact-reversed long; executable ask plus base slippage",
            "short": "negative pair-z original short or positive pair-z exact-reversed short; executable bid minus base slippage",
        },
        "exit_rules": {
            "stop_loss": "1.5 ATR20 fixed at entry using only H1 candles completed before entry; long checks bid low and short checks ask high",
            "take_profit": "NONE",
            "time_exit": "6 or 12 completed H1 bars at executable bid/ask",
            "rollover": "NOT_APPLICABLE_ALL_POSITIONS_EXIT_BEFORE_21_55_UTC",
        },
        "direction_rules": {
            "variants": list(VARIANTS),
            "exact_reverse_identity": "same currency, pair, report, decision, entry, time exit, stop distance, size, spread, slippage, and fold with arithmetic opposite order side",
        },
        "position_sizing": "equal initial ATR risk across active eligible pairs, reduced deterministically where needed to meet the currency gross-exposure cap; total basket risk 0.25 percent",
        "risk_limits": {"maximum_pair_initial_risk_fraction": 0.0025 / len(mapped_pairs), "maximum_basket_initial_risk_fraction": 0.0025, "maximum_currency_gross_initial_risk_fraction": 0.001, "eligible_pair_count": len(mapped_pairs)},
        "session_restriction": "MONDAY_07_UTC_ENTRY_ONLY",
        "volatility_condition": "NONE_SIGNAL_FILTER; PRIOR_ATR20_ONLY_FOR_STOP_AND_SIZE",
        "regime_condition": "NONE; REPORT_TREND_RANGE_VOLATILITY_AND_SPREAD_REGIMES_WITHOUT_POST_HOC_FILTERING",
        "event_behavior": "NO_EVENT_FILTER; ECONOMIC_EVENT_PROXIMITY_RECORDED_WHEN CERTIFIED_POINT_IN_TIME_EVENT_DATA_EXISTS_ELSE_NOT_APPLICABLE",
        "cost_model": {
            "gross": "midpoint entry stop and exit without slippage",
            "base": "observed bid/ask plus 0.10 pip adverse slippage per side",
            "stress": "observed bid/ask plus 0.50 pip adverse slippage per side",
            "financing": "NOT_APPLICABLE_FLAT_BEFORE_ROLLOVER",
        },
        "parameter_grid": {"variants": list(VARIANTS), "holding_h1": list(HOLDING_HOURS), "candidate_count": 10, "fitted_parameters": 0},
        "chronological_folds": [
            {"fold": index, "score_end_exclusive": end.isoformat(), "purge": "NO_TRADE_MAY_CROSS_BOUNDARY", "embargo": "12_H1_HOURS"}
            for index, end in enumerate(FOLD_ENDS, start=1)
        ],
        "development_validation_boundary": "last development entry 2025-03-31T07:00Z exits by 19:00Z; validation begins 2025-04-07T07:00Z; purge any trade reaching 2025-04-01T00:00Z and embargo through 2025-04-01T12:00Z",
        "baselines": [
            "NO_TRADE_ZERO_EXPECTANCY",
            "MATCHED_DETERMINISTIC_RANDOM_DIRECTION_IDENTICAL_PAIR_TIMESTAMPS",
            "PRIOR_WEEK_H1_PRICE_ONLY_CONTINUATION_IDENTICAL_TIMESTAMPS",
            "PRIOR_WEEK_H1_PRICE_ONLY_REVERSAL_IDENTICAL_TIMESTAMPS",
            "RAW_UNSTANDARDIZED_ASSET_MANAGER_CHANGE_SIGN",
            "ASSET_MANAGER_NET_LEVEL_SIGN",
            "COST_FREE_GROSS",
            "BASE_AND_STRESS_COST",
        ],
        "stage1_rejection_gates": {
            "gross_expectancy_must_exceed_zero": True,
            "after_cost_expectancy_must_exceed_zero": True,
            "minimum_profit_factor": 1.05,
            "minimum_trades": 100,
            "maximum_drawdown_percent": 15.0,
            "minimum_positive_folds": 4,
            "minimum_contributing_pairs": 10,
            "minimum_contributing_currencies": 7,
            "must_beat_all_required_after_cost_baselines": True,
            "maximum_largest_pair_profit_share": 0.25,
            "maximum_largest_currency_profit_share": 0.35,
            "leakage": "PASS_REQUIRED",
        },
        "stage2_promotion_gates": {
            "after_cost_expectancy_must_exceed_zero": True,
            "minimum_profit_factor": 1.10,
            "minimum_trades": 200,
            "maximum_drawdown_percent": 10.0,
            "cost_stress": "PASS_REQUIRED",
            "parameter_stability": "PASS_REQUIRED",
            "pair_currency_regime_concentration": "PASS_REQUIRED",
            "multiple_testing": "GLOBAL_HISTORY_ADJUSTED_PASS_REQUIRED",
            "deterministic_two_run_reproduction": "BYTE_IDENTICAL_REQUIRED",
        },
        "journal_fields": [
            "strategy_id", "candidate_id", "instrument", "direction", "signal_timestamp", "entry_timestamp",
            "entry_price", "exit_timestamp", "exit_price", "stop_loss", "take_profit", "spread",
            "modeled_slippage", "gross_result_r", "net_result_r", "result_r", "entry_reason", "exit_reason",
            "session", "volatility_regime", "trend_range_regime", "economic_event_proximity", "filter_results",
        ],
        "multiple_testing": {"prior_actual_computational_attempt_lower_bound": PRIOR_ATTEMPTS, "prior_governed_after_cost_candidates": PRIOR_AFTER_COST_CANDIDATES, "stage0_increment": 0, "stage1_increment_if_executed": 10, "expected_after_stage1": {"attempts": PRIOR_ATTEMPTS + 10, "governed_after_cost_candidates": PRIOR_AFTER_COST_CANDIDATES + 10}, "selection_bias_control": "GLOBAL_HISTORY_SEARCH_ADJUSTED_PBO_OR_REPOSITORY_APPROVED_EQUIVALENT_REQUIRED_BEFORE_EDGE_CLAIM"},
        "expected_turnover": {"weeks": 38, "symmetric_max_pair_trades": pair_totals["causal_pair_signals"] - pair_totals["zero_pair_z"], "positive_pair_z_one_sided_opportunities": pair_totals["positive_pair_z"], "negative_pair_z_one_sided_opportunities": pair_totals["negative_pair_z"], "holding_hours": list(HOLDING_HOURS)},
        "reproduction_commands": [
            "python -B scripts/forex_delivery/run_forex_cftc_asset_manager_weekly_change_stage1_v1.py --output .aios/staging/PKT_FOREX_036/expansion58/run1",
            "python -B scripts/forex_delivery/run_forex_cftc_asset_manager_weekly_change_stage1_v1.py --output .aios/staging/PKT_FOREX_036/expansion58/run2",
        ],
        "preregistered_before_outcome_access": True,
        "status": "FROZEN_IF_STAGE0_ELIGIBLE",
    }


def run(repo_root: Path, output: Path) -> dict[str, Any]:
    completion_path = repo_root / ".aios/staging/PKT_FOREX_036/PKT_FOREX_036_COMPLETION.json"
    matrix_path = repo_root / ".aios/staging/PKT_FOREX_027/run1/AIOS_FOREX_AUTHORITATIVE_PAIR_TIMEFRAME_MATRIX_V1.json"
    if sha256_file(completion_path) != "c641f3d1b255f8f6a01e2a2e7739c780c78da6e9f09876b0dbacd3e365e31c50":
        raise RuntimeError("PRIOR_NINE_PAIR_COMPLETION_HASH_MISMATCH")
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    promotion_audit = predecessor_promotion_audit(repo_root)
    rejection_audit = rejection_memory_audit(repo_root)
    histories, source_verification = load_development_cftc(repo_root)
    inventories = {currency: signal_inventory(history) for currency, history in histories.items()}
    h1_rows = [row for row in matrix["rows"] if row["granularity"] == "H1" and row["development_eligibility"] is True]
    certified_pairs = sorted(row["pair"] for row in h1_rows)
    pair_map_rows = pair_eligibility_rows(certified_pairs)
    mapped_pairs = eligible_pairs(pair_map_rows)
    pair_inventories = {pair: pair_signal_inventory(pair, inventories) for pair in mapped_pairs}
    candidates = candidate_definitions()
    currency_signal_counts = {
        currency: {
            "source_reports_before_development_end": len(histories[currency]),
            "causal_signals": len(values),
            "positive_z": sum(item["zscore"] > 0 for item in values),
            "negative_z": sum(item["zscore"] < 0 for item in values),
            "zero_z": sum(item["zscore"] == 0 for item in values),
            "first_decision": min(item["decision"] for item in values).isoformat() if values else None,
            "last_decision": max(item["decision"] for item in values).isoformat() if values else None,
        }
        for currency, values in inventories.items()
    }
    pair_signal_counts = {
        pair: {
            "causal_signals": len(values),
            "positive_pair_z": sum(item["pair_zscore"] > 0 for item in values),
            "negative_pair_z": sum(item["pair_zscore"] < 0 for item in values),
            "zero_pair_z": sum(item["pair_zscore"] == 0 for item in values),
            "first_decision": min(item["decision"] for item in values).isoformat() if values else None,
            "last_decision": max(item["decision"] for item in values).isoformat() if values else None,
            "all_sources_strictly_before_decision": all(item["source_available"] < item["decision"] for item in values),
        }
        for pair, values in pair_inventories.items()
    }
    pair_totals = {
        "causal_pair_signals": sum(value["causal_signals"] for value in pair_signal_counts.values()),
        "positive_pair_z": sum(value["positive_pair_z"] for value in pair_signal_counts.values()),
        "negative_pair_z": sum(value["negative_pair_z"] for value in pair_signal_counts.values()),
        "zero_pair_z": sum(value["zero_pair_z"] for value in pair_signal_counts.values()),
    }
    decision_dates = sorted({item["decision"] for values in pair_inventories.values() for item in values})
    fold_counts = {str(index): sum(fold_id(date) == index for date in decision_dates) for index in range(1, 7)}
    map_counts = {
        "certified": len(pair_map_rows),
        "eligible": sum(row["eligible"] for row in pair_map_rows),
        "direct_usd": sum(row["mapping_type"] == "DIRECT_USD_MAPPING" for row in pair_map_rows),
        "derived_cross": sum(row["mapping_type"] == "DERIVED_CROSS_BASE_MINUS_QUOTE" for row in pair_map_rows),
        "excluded": sum(not row["eligible"] for row in pair_map_rows),
    }
    gates = {
        "predecessor_32_artifact_promotion_exact": promotion_audit["status"] == "PASS",
        "prior_nine_pair_stage1_preserved": completion.get("result") == "STAGE1_SURVIVOR_REQUIRES_STAGE2",
        "prior_trial_memory_preserved": completion.get("actual_computational_attempt_lower_bound_after") == PRIOR_ATTEMPTS and completion.get("governed_after_cost_candidates_after") == PRIOR_AFTER_COST_CANDIDATES,
        "four_family_failure_memory_complete": rejection_audit["status"] == "PASS",
        "distinct_mechanism_and_candidates": not rejection_audit["current_family_collision"] and not rejection_audit["current_candidate_collisions"],
        "information_corpus_exact": source_verification["manifest_sha256"] == INFORMATION_MANIFEST_SHA256,
        "only_2024_2025_cftc_artifacts_opened": source_verification["opened_normalized_artifact_count"] == 2 and source_verification["final_holdout_artifacts_opened"] == 0,
        "exact_nine_currency_histories": set(histories) == set(CURRENCY_TO_CONTRACT),
        "exact_58_pair_eligibility_map": map_counts["certified"] == 58 and len({row["pair"] for row in pair_map_rows}) == 58,
        "exact_33_eligible_9_direct_24_cross_25_excluded": map_counts == {"certified": 58, "eligible": 33, "direct_usd": 9, "derived_cross": 24, "excluded": 25},
        "all_58_h1_rows_native_certified_bid_ask": len(h1_rows) == 58 and all(row["availability"] == "NATIVE_CERTIFIED" and row["bid_available"] and row["ask_available"] and row["certification_status"] == "FROZEN_CERTIFIED_WITH_M5_OVERLAP_PASS" for row in h1_rows),
        "single_h1_corpus_identity": {row["dataset_sha256"] for row in h1_rows} == {H1_CORPUS_SHA256},
        "south_african_rand_exact_coverage_regression": market_currency("SO AFRICAN RAND" + EXCHANGE_SUFFIX) == "ZAR" and len(histories["ZAR"]) == 65,
        "all_33_pair_inventories_have_38_causal_weeks": len(pair_inventories) == 33 and all(value["causal_signals"] == 38 and value["all_sources_strictly_before_decision"] for value in pair_signal_counts.values()),
        "exact_development_pair_signal_capacity": pair_totals["causal_pair_signals"] == 1254 and sum(pair_totals[key] for key in ("positive_pair_z", "negative_pair_z", "zero_pair_z")) == 1254,
        "six_nonempty_folds_7_7_6_6_6_6": list(fold_counts.values()) == [7, 7, 6, 6, 6, 6],
        "exact_ten_candidate_fingerprints": len(candidates) == len({row["candidate_fingerprint"] for row in candidates}) == 10,
        "public_placebo_counterevidence_recorded": any(source["source_id"] == "KREMENS_SPECULATOR_RISK_PLACEBO" and source["final_disposition"].startswith("WEAK_PREDICTOR_PLACEBO") for source in build_source_registry()["sources"]),
        "market_price_rows_opened_zero": True,
        "returns_calculated_zero": True,
        "validation_price_rows_opened_zero": True,
        "final_holdout_rows_opened_zero": True,
    }
    decision = "ADMIT_STAGE1_LOW_COST_ONLY" if all(gates.values()) else "BLOCK_STAGE0"
    capacity = {
        "schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_STAGE0_CAPACITY.v2",
        "packet_id": PACKET_ID,
        "scope": "CORRECTIVE_MAXIMUM_CAUSAL_58_PAIR_UNIVERSE_AUDIT",
        "information_corpus": {"id": INFORMATION_CORPUS_ID, "sha256": INFORMATION_CORPUS_SHA256, **source_verification},
        "h1_corpus": {"id": H1_CORPUS_ID, "sha256": H1_CORPUS_SHA256},
        "predecessor_promotion_audit": promotion_audit,
        "pair_map_counts": map_counts,
        "eligible_pairs": list(mapped_pairs),
        "currency_signal_counts": currency_signal_counts,
        "pair_signal_counts": pair_signal_counts,
        "pair_totals": pair_totals,
        "fold_decision_counts": fold_counts,
        "gates": gates,
        "safety": {"market_price_rows_opened": 0, "returns_calculated": 0, "strategy_candidates_scored": 0, "validation_price_rows_opened": 0, "final_holdout_rows_opened": 0, "broker_access": False, "credentials_accessed": False, "orders": False},
        "status": decision,
    }
    duplicate = {
        "schema": "AIOS_FOREX_MECHANISM_DUPLICATE_DECISION.v2",
        "packet_id": PACKET_ID,
        "strategy_id": STRATEGY_ID,
        "strategy_mechanism_fingerprint": mechanism_fingerprint(),
        "rejection_memory_audit": rejection_audit,
        "decision": "DISTINCT_UNSCORED_ASSET_MANAGER_WEEKLY_CHANGE_WITH_CAUSAL_CROSS_PAIR_EXTENSION",
        "distinguishing_dimensions": {"mechanism": "persistent_information_or_temporary_hedging_pressure", "participant_class": "asset_manager_institutional", "signal_construction": "base_minus_quote_weekly_change_zscores_each_against_prior_26_changes", "entry": "Monday_07_UTC_after_publication", "exit": "6_or_12_H1_no_profit_target", "direction": "original_exact_reverse_and_symmetric", "conditioning": "none", "timeframe": "weekly_signal_H1_execution", "parameter_grid": "five_fixed_direction_variants_by_two_holds"},
        "prior_nine_pair_evidence": "PRESERVED_VALID_FOR_PREREGISTERED_DIRECT_USD_SCOPE_NOT_COUNTED_AS_FULL_58_PAIR_CFTC_SCREEN",
        "prohibited_repeats": ["ASSET_MANAGER_LEVEL_RESCUE", "LEVERAGED_FUND_CHANGE_RELABEL", "PARTICIPANT_DIVERGENCE_RELABEL", "DEALER_LEVEL_RELABEL", "POST_HOC_THRESHOLD", "POST_HOC_PAIR_DIRECTION_OR_FILTER_SELECTION", "PRICE_CONFIRMATION_ADDED_AFTER_RESULTS", "REMOVAL_OF_COSTS", "DELETION_OF_LOSING_TRADES"],
        "existing_governed_after_cost_candidates": PRIOR_AFTER_COST_CANDIDATES,
        "actual_computational_attempt_lower_bound": PRIOR_ATTEMPTS,
        "actual_trials_added": 0,
        "status": "PASS_TO_STAGE1_IF_CAPACITY_GATES_PASS",
    }
    pair_map = {"schema": "AIOS_FOREX_CFTC_PAIR_ELIGIBILITY_MAP.v1", "packet_id": PACKET_ID, "certified_pair_count": 58, "eligible_pair_count": 33, "rows": pair_map_rows, "status": "PASS" if map_counts == {"certified": 58, "eligible": 33, "direct_usd": 9, "derived_cross": 24, "excluded": 25} else "FAIL"}
    values = {
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_STAGE0_CAPACITY.json": capacity,
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_DUPLICATE_DECISION.json": duplicate,
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_HYPOTHESIS_SOURCES.json": build_source_registry(),
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_PAIR_ELIGIBILITY_MAP.json": pair_map,
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_PREREGISTRATION.json": build_preregistration(mapped_pairs, pair_totals),
        "AIOS_FOREX_RESEARCH_FACTORY_CAPABILITY_AUDIT.json": build_capability_audit(certified_pairs, mapped_pairs),
        "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_STAGE0_CONTRACT.json": {
            "schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_STAGE0_CONTRACT.v2",
            "packet_id": PACKET_ID,
            "scope": "CORRECTIVE_58_PAIR_ELIGIBILITY_AND_33_PAIR_STAGE1_FREEZE",
            "status": decision,
            "market_outcomes_scored": False,
            "actual_trials_added": 0,
            "actual_computational_attempt_lower_bound": PRIOR_ATTEMPTS,
            "governed_after_cost_candidates": PRIOR_AFTER_COST_CANDIDATES,
            "validation_price_evidence": "SEALED_NOT_OPENED",
            "final_holdout": "SEALED_NOT_OPENED",
        },
    }
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for name, value in sorted(values.items()):
        payload = canonical_bytes(value)
        (output / name).write_bytes(payload)
        files[name] = {"bytes": len(payload), "sha256": sha256_bytes(payload)}
    receipt = {
        "schema": "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_STAGE0_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "files": files,
        "aggregate_sha256": sha256_bytes(b"".join(name.encode("utf-8") + b"\0" + bytes.fromhex(details["sha256"]) for name, details in sorted(files.items()))),
        "result": decision,
        "actual_trials_added": 0,
        "validation_price_rows_opened": 0,
        "final_holdout_rows_opened": 0,
        "status": "PASS" if decision == "ADMIT_STAGE1_LOW_COST_ONLY" else "BLOCK",
    }
    receipt_payload = canonical_bytes(receipt)
    (output / "AIOS_FOREX_CFTC_ASSET_MANAGER_WEEKLY_CHANGE_STAGE0_RECEIPT.json").write_bytes(receipt_payload)
    return {"receipt_sha256": sha256_bytes(receipt_payload), **receipt}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.repo_root.resolve(), args.output.resolve())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
