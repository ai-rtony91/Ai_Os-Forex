"""Stage-0 qualification for an OANDA price-update-count response hypothesis.

This module deliberately computes no forward return or strategy performance.
It reads only frozen M5 development partitions through 2025-03, verifies their
manifest hashes, audits the provider field, and emits a fixed preregistration.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import statistics
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_RESPONSE_STAGE0.v1"
PACKET_ID = "PKT-FOREX-029"
CORPUS_SHA256 = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
MANIFEST_SHA256 = "1bd01b32c634a72fa76cb06d9b3e4392c671465469f0d8f4aa90a022cca2ae7b"
DEVELOPMENT_START = "2024-01-01T00:00:00Z"
DEVELOPMENT_END = "2025-04-01T00:00:00Z"
HOLDOUT_START = "2026-01-01T00:00:00Z"
MIN_ELIGIBLE_PAIRS = 40
MIN_ELIGIBLE_CURRENCIES = 10
MIN_NONZERO_MAD_SHARE = 0.25


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> str:
    payload = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256_bytes(payload)


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def robust_history_observation(history: Iterable[float]) -> tuple[float, float]:
    values = list(history)
    center = statistics.median(values)
    mad = statistics.median(abs(value - center) for value in values)
    return center, 1.4826 * mad


def partition_is_development(artifact: dict[str, Any]) -> bool:
    return (
        artifact["start_utc"] >= DEVELOPMENT_START
        and artifact["end_utc"] <= DEVELOPMENT_END
        and artifact["path"].endswith(".jsonl.gz")
    )


def inspect_pair(
    *,
    repo_root: Path,
    corpus_root: Path,
    pair: str,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_timestamp: datetime | None = None
    seen_timestamps: set[str] = set()
    slot_history: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=8))
    records = 0
    complete_false = 0
    timestamp_errors = 0
    duplicate_timestamps = 0
    quote_errors = 0
    nonpositive_spreads = 0
    volume_errors = 0
    zero_volumes = 0
    min_volume: int | None = None
    max_volume: int | None = None
    history_windows = 0
    nonzero_mad_windows = 0
    observed_gap_count = 0
    partition_hash_failures: list[str] = []
    manifest_record_mismatches: list[str] = []

    for artifact in sorted(artifacts, key=lambda item: item["path"]):
        relative = Path(artifact["path"])
        path = corpus_root / relative
        actual_sha = sha256_file(path)
        if actual_sha != artifact["sha256"]:
            partition_hash_failures.append(relative.as_posix())
            continue

        partition_records = 0
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for raw_line in handle:
                row = json.loads(raw_line)
                partition_records += 1
                records += 1

                timestamp_text = row.get("timestamp")
                try:
                    timestamp = parse_utc(timestamp_text)
                except (AttributeError, TypeError, ValueError):
                    timestamp_errors += 1
                    continue
                if timestamp_text >= DEVELOPMENT_END or timestamp_text >= HOLDOUT_START:
                    timestamp_errors += 1
                if previous_timestamp is not None:
                    if timestamp <= previous_timestamp:
                        timestamp_errors += 1
                    if (timestamp - previous_timestamp).total_seconds() > 300:
                        observed_gap_count += 1
                previous_timestamp = timestamp
                if timestamp_text in seen_timestamps:
                    duplicate_timestamps += 1
                seen_timestamps.add(timestamp_text)

                if row.get("complete") is not True:
                    complete_false += 1
                if row.get("instrument") != pair:
                    quote_errors += 1

                valid_quotes = True
                for side in ("bid", "ask", "mid"):
                    quote = row.get(side)
                    if not isinstance(quote, dict):
                        valid_quotes = False
                        break
                    for field in ("o", "h", "l", "c"):
                        value = quote.get(field)
                        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                            valid_quotes = False
                            break
                if not valid_quotes:
                    quote_errors += 1
                else:
                    if row["ask"]["o"] <= row["bid"]["o"] or row["ask"]["c"] <= row["bid"]["c"]:
                        nonpositive_spreads += 1

                volume = row.get("volume")
                if not isinstance(volume, int) or isinstance(volume, bool) or volume < 0:
                    volume_errors += 1
                    continue
                if volume == 0:
                    zero_volumes += 1
                min_volume = volume if min_volume is None else min(min_volume, volume)
                max_volume = volume if max_volume is None else max(max_volume, volume)

                slot = timestamp.weekday() * 1440 + timestamp.hour * 60 + timestamp.minute
                history = slot_history[slot]
                if len(history) == 8:
                    history_windows += 1
                    _, scale = robust_history_observation(history)
                    if scale > 0.0:
                        nonzero_mad_windows += 1
                history.append(math.log1p(volume))

        if partition_records != artifact["records"]:
            manifest_record_mismatches.append(relative.as_posix())

    nonzero_mad_share = nonzero_mad_windows / history_windows if history_windows else 0.0
    eligible = all(
        (
            not partition_hash_failures,
            not manifest_record_mismatches,
            records >= 60_000,
            complete_false == 0,
            timestamp_errors == 0,
            duplicate_timestamps == 0,
            quote_errors == 0,
            nonpositive_spreads == 0,
            volume_errors == 0,
            min_volume is not None,
            max_volume is not None and max_volume > min_volume,
            history_windows > 0,
            nonzero_mad_share >= MIN_NONZERO_MAD_SHARE,
        )
    )
    return {
        "pair": pair,
        "eligible": eligible,
        "partition_count": len(artifacts),
        "partition_hash_failures": partition_hash_failures,
        "manifest_record_mismatches": manifest_record_mismatches,
        "records": records,
        "complete_false": complete_false,
        "timestamp_errors": timestamp_errors,
        "duplicate_timestamps": duplicate_timestamps,
        "quote_errors": quote_errors,
        "nonpositive_spreads": nonpositive_spreads,
        "volume_errors": volume_errors,
        "zero_volumes": zero_volumes,
        "min_volume": min_volume,
        "max_volume": max_volume,
        "observed_gap_count": observed_gap_count,
        "history_windows": history_windows,
        "nonzero_mad_windows": nonzero_mad_windows,
        "nonzero_mad_share": round(nonzero_mad_share, 12),
    }


def build_sources() -> dict[str, Any]:
    return {
        "schema": "AIOS_FOREX_HYPOTHESIS_SOURCE_REGISTRY_SUPPLEMENT.v1",
        "packet_id": PACKET_ID,
        "evidence_role": "HYPOTHESIS_INPUT_ONLY_NOT_EDGE_PROOF",
        "sources": [
            {
                "source_id": "OANDA_V20_INSTRUMENT_DEFINITIONS",
                "title": "Instrument definitions - Candlestick volume",
                "url": "https://developer.oanda.com/rest-live-v20/instrument-df/",
                "author_or_organization": "OANDA",
                "publication_date": "NOT_STATED",
                "access_date": "2026-09-05",
                "source_type": "OFFICIAL_PROVIDER_DOCUMENTATION",
                "exact_disclosed_rule": "Candlestick volume is the number of prices created during the time interval.",
                "license": "OANDA developer-site terms; no code adapted",
                "final_disposition": "SEMANTICS_CONTROL_ONLY",
            },
            {
                "source_id": "CESPA_GARGANO_RIDDIOUGH_SARNO_2022",
                "title": "Foreign Exchange Volume",
                "url": "https://www.repository.cam.ac.uk/items/6125f8ba-42ba-433a-8327-11c1b71e6729",
                "doi": "https://doi.org/10.1093/rfs/hhab095",
                "author_or_organization": "Giovanni Cespa, Antonio Gargano, Steven Riddiough, and Lucio Sarno",
                "publication_date": "2022",
                "access_date": "2026-09-05",
                "source_type": "PEER_REVIEWED_ARTICLE",
                "claimed_mechanism": "Unexpected CLS transaction volume conditions the sign and persistence of FX returns.",
                "costs_included": True,
                "walk_forward_included": False,
                "source_code_exists": False,
                "license": "Oxford University Press copyright; repository manuscript; no code license",
                "replication_risks": [
                    "CLS_TRANSACTION_VOLUME_IS_NOT_OANDA_PRICE_UPDATE_COUNT",
                    "NO_AIOS_STYLE_WALK_FORWARD",
                    "PROXY_RELATIONSHIP_UNVERIFIED"
                ],
                "final_disposition": "INDIRECT_MECHANISM_INPUT_ONLY_UNVERIFIED_PROXY",
            },
        ],
        "provider_field_name": "OANDA_PRICE_UPDATE_COUNT_PROXY",
        "prohibited_names": ["TRADED_VOLUME", "TRANSACTION_VOLUME", "NOTIONAL_VOLUME"],
        "status": "PASS_SEMANTICS_RECORDED_NO_EQUIVALENCE_CLAIM",
    }


def build_preregistration(eligible_pairs: list[str]) -> dict[str, Any]:
    folds = [
        ["2024-04-01T00:00:00Z", "2024-06-01T00:00:00Z"],
        ["2024-06-01T00:00:00Z", "2024-08-01T00:00:00Z"],
        ["2024-08-01T00:00:00Z", "2024-10-01T00:00:00Z"],
        ["2024-10-01T00:00:00Z", "2024-12-01T00:00:00Z"],
        ["2024-12-01T00:00:00Z", "2025-02-01T00:00:00Z"],
        ["2025-02-01T00:00:00Z", "2025-04-01T00:00:00Z"],
    ]
    candidates = []
    for threshold in (2.0, 3.0):
        for arm in ("CONTINUATION", "REVERSAL"):
            for holding_bars in (3, 6):
                descriptor = {
                    "arm": arm,
                    "holding_m5_bars": holding_bars,
                    "strategy": "ABNORMAL_OANDA_PRICE_UPDATE_COUNT_RESPONSE_V1",
                    "volume_z_min": threshold,
                }
                candidates.append({
                    "candidate_id": f"APU-{int(threshold)}-{arm}-{holding_bars}",
                    "candidate_fingerprint": sha256_bytes(canonical_bytes(descriptor)),
                    **descriptor,
                })
    family_descriptor = {
        "economic_mechanism": "Abnormally high quote-arrival intensity combined with a large signed price displacement may reveal either delayed information incorporation or temporary liquidity pressure.",
        "field": "OANDA_PRICE_UPDATE_COUNT_PROXY",
        "signal": "SAME_UTC_MINUTE_OF_WEEK_ROBUST_ABNORMALITY_X_SIGNED_M5_BODY",
        "strategy": "ABNORMAL_OANDA_PRICE_UPDATE_COUNT_RESPONSE_V1",
    }
    return {
        "schema": "AIOS_FOREX_STRATEGY_PREREGISTRATION.v1",
        "packet_id": PACKET_ID,
        "strategy_id": "ABNORMAL_OANDA_PRICE_UPDATE_COUNT_RESPONSE_V1",
        "strategy_mechanism_fingerprint": sha256_bytes(canonical_bytes(family_descriptor)),
        "economic_mechanism": family_descriptor["economic_mechanism"],
        "external_evidence_limit": "CLS transaction-volume results do not validate the OANDA price-update-count proxy.",
        "dataset": {
            "id": "AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2",
            "sha256": CORPUS_SHA256,
            "development_start": DEVELOPMENT_START,
            "development_end_exclusive": DEVELOPMENT_END,
            "validation_access": "PROHIBITED_IN_STAGE0_AND_STAGE1_UNLESS_A_SURVIVOR_EXISTS",
            "final_holdout_start": HOLDOUT_START,
            "final_holdout": "SEALED_SINGLE_USE",
        },
        "pair_universe": eligible_pairs,
        "timeframes": {"signal": "M5", "confirmation": "NONE"},
        "signal_calculation": {
            "activity": "x_t=log1p(OANDA_PRICE_UPDATE_COUNT_PROXY_t)",
            "history": "previous 8 completed observations for the same UTC minute-of-week, excluding t",
            "center": "median(history)",
            "scale": "1.4826*median(abs(history-median(history)))",
            "activity_z": "(x_t-center)/scale; no signal when scale<=0",
            "price_displacement": "abs(mid_close_t-mid_open_t)/ATR20_t_minus_1",
            "atr": "20 completed M5 true ranges ending at t-1; true range uses mid OHLC and prior mid close",
            "minimum_price_displacement_atr": 0.5,
            "completed_candle_only": True,
        },
        "entry_rules": {
            "continuation": "direction=sign(mid_close_t-mid_open_t)",
            "reversal": "direction=-sign(mid_close_t-mid_open_t)",
            "entry_time": "next available M5 candle open after signal t",
            "entry_price": "long at ask open; short at bid open; add 0.1 pip adverse slippage per side",
            "simultaneous_selection": "rank descending by activity_z, then displacement, then pair; greedily select at most 5 without shared currencies",
        },
        "exit_rules": {
            "stop_loss": "1.0 ATR20 from executable entry; long triggered by bid low, short by ask high",
            "take_profit": "NONE",
            "time_exit": "3 or 6 M5 bars at bid close for long or ask close for short",
            "same_bar_ambiguity": "STOP_FIRST_PESSIMISTIC",
        },
        "position_sizing": "risk 0.05 percent of current equity to the 1 ATR stop",
        "risk_limits": {
            "maximum_open_positions": 5,
            "maximum_total_initial_risk_percent": 0.25,
            "maximum_pair_positions": 1,
            "shared_currency_positions": 0,
        },
        "cost_model": {
            "base": "observed executable bid/ask plus 0.1 pip adverse slippage per side",
            "stress": "observed executable bid/ask plus 0.5 pip adverse slippage per side",
            "financing": "NOT_APPLICABLE_MAXIMUM_30_MINUTE_HOLD",
        },
        "parameter_grid": {
            "volume_z_min": [2.0, 3.0],
            "arm": ["CONTINUATION", "REVERSAL"],
            "holding_m5_bars": [3, 6],
            "candidate_count": 8,
        },
        "chronological_folds": [
            {"fold": index + 1, "score_start": bounds[0], "score_end_exclusive": bounds[1], "training": "all available development rows strictly before score_start"}
            for index, bounds in enumerate(folds)
        ],
        "purge_and_embargo": "6 M5 bars on both sides of every score boundary",
        "baselines": [
            "NO_TRADE_ZERO_EXPECTANCY",
            "DETERMINISTIC_RANDOM_DIRECTION_AT_IDENTICAL_TIMESTAMPS",
            "EXACT_PRICE_DISPLACEMENT_ONLY_CONTINUATION_AND_REVERSAL",
            "ACTIVITY_SHOCK_WITH_DETERMINISTIC_RANDOM_SIGN",
            "MATCHED_NON_SHOCK_SAME_UTC_MINUTE_OF_WEEK",
        ],
        "stage1_rejection_gates": {
            "gross_expectancy_must_exceed_zero": True,
            "after_cost_expectancy_must_exceed_zero": True,
            "minimum_profit_factor": 1.05,
            "minimum_trades": 100,
            "maximum_drawdown_percent": 15.0,
            "minimum_positive_folds": 4,
            "minimum_contributing_pairs": 10,
            "minimum_contributing_currencies": 5,
            "must_beat_all_baselines": True,
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
        "reproduction_command": "python scripts/forex_delivery/run_forex_abnormal_price_update_response_stage1_v1.py --output <isolated-output>",
        "candidates": candidates,
        "preregistered_before_outcome_access": True,
        "status": "FROZEN_IF_STAGE0_ELIGIBLE",
    }


def run(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    corpus_root = repo_root / ".aios/runtime/forex_m5_immutable_corpus_v2"
    manifest_path = corpus_root / "manifest.json"
    frozen_path = corpus_root / "FROZEN.json"
    if sha256_file(manifest_path) != MANIFEST_SHA256:
        raise RuntimeError("manifest SHA-256 mismatch")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if frozen.get("aggregate_corpus_fingerprint") != CORPUS_SHA256:
        raise RuntimeError("frozen corpus fingerprint mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("aggregate_corpus_fingerprint") != CORPUS_SHA256:
        raise RuntimeError("manifest corpus fingerprint mismatch")

    eligible_universe = sorted(manifest["eligible_pairs"])
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for artifact in manifest["artifacts"]:
        if artifact["instrument"] in eligible_universe and partition_is_development(artifact):
            selected[artifact["instrument"]].append(artifact)

    pair_quality = [
        inspect_pair(
            repo_root=repo_root,
            corpus_root=corpus_root,
            pair=pair,
            artifacts=selected[pair],
        )
        for pair in eligible_universe
    ]
    qualified_pairs = sorted(item["pair"] for item in pair_quality if item["eligible"])
    currencies = sorted({currency for pair in qualified_pairs for currency in pair.split("_")})
    rows_opened = sum(item["records"] for item in pair_quality)
    stage0_pass = len(qualified_pairs) >= MIN_ELIGIBLE_PAIRS and len(currencies) >= MIN_ELIGIBLE_CURRENCIES

    quality = {
        "schema": SCHEMA,
        "packet_id": PACKET_ID,
        "corpus_id": manifest["corpus_id"],
        "corpus_sha256": CORPUS_SHA256,
        "manifest_sha256": MANIFEST_SHA256,
        "inspection_window": {"start": DEVELOPMENT_START, "end_exclusive": DEVELOPMENT_END},
        "field_semantics": "OANDA_PRICE_UPDATE_COUNT_PROXY_NOT_TRADED_OR_NOTIONAL_VOLUME",
        "eligible_universe_count": len(eligible_universe),
        "qualified_pair_count": len(qualified_pairs),
        "qualified_currency_count": len(currencies),
        "minimum_pair_gate": MIN_ELIGIBLE_PAIRS,
        "minimum_currency_gate": MIN_ELIGIBLE_CURRENCIES,
        "qualified_pairs": qualified_pairs,
        "qualified_currencies": currencies,
        "pair_quality": pair_quality,
        "safety": {
            "development_rows_opened": rows_opened,
            "validation_rows_opened": 0,
            "final_holdout_rows_opened": 0,
            "forward_returns_calculated": 0,
            "strategy_candidates_scored": 0,
            "broker_access": False,
            "credentials_accessed": False,
            "orders": False,
        },
        "status": "PASS" if stage0_pass else "BLOCK",
    }
    sources = build_sources()
    preregistration = build_preregistration(qualified_pairs) if stage0_pass else {
        "schema": "AIOS_FOREX_STRATEGY_PREREGISTRATION.v1",
        "packet_id": PACKET_ID,
        "status": "NOT_ADMITTED_STAGE0_DATA_QUALITY_FAILURE",
        "candidates": [],
    }
    duplicate = {
        "schema": "AIOS_FOREX_MECHANISM_DUPLICATE_DECISION.v1",
        "packet_id": PACKET_ID,
        "strategy": "ABNORMAL_OANDA_PRICE_UPDATE_COUNT_RESPONSE_V1",
        "semantic_decision": "DISTINCT_WITH_MEDIUM_PROXY_RISK",
        "distinguishing_features": [
            "requires provider price-update-count abnormality",
            "requires interaction between activity shock and signed displacement",
            "tests exact continuation and reversal arms together",
            "does not use a session label as a filter",
            "does not rank synchronous cross-sectional returns",
        ],
        "blocked_cosmetic_forms": [
            "PURE_PRICE_VOLATILITY_BREAKOUT",
            "PURE_PRICE_REVERSAL",
            "SESSION_FILTERED_BREAKOUT_OR_REVERSAL",
            "TRADED_VOLUME_EQUIVALENCE_CLAIM",
        ],
        "existing_rejected_data_scored_families": 18,
        "existing_governed_after_cost_candidates": 127,
        "actual_computational_attempt_lower_bound": 1179,
        "status": "PASS_TO_STAGE1_IF_DATA_QUALITY_PASS",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, str] = {}
    for name, value in (
        ("AIOS_FOREX_ABNORMAL_PRICE_UPDATE_STAGE0_QUALITY_V1.json", quality),
        ("AIOS_FOREX_ABNORMAL_PRICE_UPDATE_HYPOTHESIS_SOURCES_V1.json", sources),
        ("AIOS_FOREX_ABNORMAL_PRICE_UPDATE_DUPLICATE_DECISION_V1.json", duplicate),
        ("AIOS_FOREX_ABNORMAL_PRICE_UPDATE_PREREGISTRATION_V1.json", preregistration),
    ):
        artifacts[name] = write_json(output_dir / name, value)
    receipt = {
        "schema": "AIOS_FOREX_STAGE0_RECEIPT.v1",
        "packet_id": PACKET_ID,
        "result": "STAGE0_PASS_EIGHT_CANDIDATES_PREREGISTERED" if stage0_pass else "STAGE0_BLOCK",
        "artifacts": [{"path": name, "sha256": artifacts[name]} for name in sorted(artifacts)],
        "qualified_pairs": len(qualified_pairs),
        "qualified_currencies": len(currencies),
        "candidate_count_preregistered": len(preregistration.get("candidates", [])),
        "actual_data_scored_candidates_added": 0,
        "actual_computational_attempt_lower_bound": 1179,
        "final_holdout_evaluations": 0,
        "final_holdout": "SEALED_NOT_OPENED",
        "status": "PASS" if stage0_pass else "BLOCK",
    }
    receipt_sha = write_json(output_dir / "AIOS_FOREX_ABNORMAL_PRICE_UPDATE_STAGE0_RECEIPT_V1.json", receipt)
    return {"receipt_sha256": receipt_sha, **receipt}


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
