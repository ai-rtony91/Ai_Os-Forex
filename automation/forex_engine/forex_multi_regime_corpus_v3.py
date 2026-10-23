"""Packet 021 multi-regime market Corpus V3 gate.

Codex never reads OANDA Practice credentials. This module freezes only from
sanitized Human-produced artifacts placed in the packet inbox. If those
artifacts are absent, it produces the formal Human Practice acquisition gate.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine.forex_official_data_breakthrough_v1 import PACKET_ID, atomic_json, sha256, stable

PACKET_ID = "PKT-EAST-FOREX-FULL-ATTACK-PROFITABILITY-022"
CORPUS_ID = "AIOS_FOREX_MULTI_REGIME_CORPUS_V3"
ROOT = Path(".aios/runtime/forex_multi_regime_corpus_v3")
PRACTICE_INBOX = Path(".aios/runtime/forex_practice_history_human_inbox")
M5_ROOT = Path(".aios/runtime/forex_m5_immutable_corpus_v2")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_MULTI_REGIME_CORPUS_V3_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_MULTI_REGIME_CORPUS_V3_REPORT.md")
COVERAGE_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PAIR_COVERAGE_MATRIX_V3.json")
COVERAGE_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_PAIR_COVERAGE_MATRIX_V3.md")
MARKET_V2_STATE = Path("Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_V2_STATE.json")
MARKET_V2_HASH = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


def instrument_from_practice_path(path: Path) -> str:
    if path.name.endswith(".H1.json"):
        return path.name[: -len(".H1.json")]
    return path.stem


def intended_universe() -> list[str]:
    state = read_json(MARKET_V2_STATE)
    coverage = state.get("quality_reconciliation", {}).get("coverage")
    if isinstance(coverage, dict) and coverage:
        return sorted(str(item) for item in coverage)
    for key in ("attempted_pairs", "intended_universe", "pairs"):
        value = state.get(key)
        if isinstance(value, list) and value:
            return [str(item) for item in value]
    return ["EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD", "EUR_GBP", "EUR_JPY", "GBP_JPY", "AUD_JPY", "CAD_JPY", "CHF_JPY", "NZD_JPY"]


def sanitized_artifacts() -> list[dict[str, Any]]:
    artifacts = []
    if not PRACTICE_INBOX.exists():
        return artifacts
    for path in sorted(PRACTICE_INBOX.glob("*.json")):
        if path.name.endswith(".manifest.json"):
            continue
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        candles = data.get("candles", [])
        complete = [item for item in candles if item.get("complete") is True]
        artifacts.append(
            {
                "path": path.as_posix(),
                "sha256": sha256(path.read_bytes()),
                "instrument": data.get("instrument") or instrument_from_practice_path(path),
                "candle_count": len(candles),
                "complete_count": len(complete),
                "first_time": complete[0].get("time") if complete else None,
                "last_time": complete[-1].get("time") if complete else None,
            }
        )
    return artifacts


def plan_development_partition_slice(manifest: dict[str, Any], source_root: Path, *,
                                     pairs: list[str], start_utc: str, end_utc: str,
                                     holdout_start_utc: str) -> dict[str, Any]:
    """Select physically separate development partitions before any price I/O.

    Never use the mixed H1 inbox, even for its prefix or hash. This extends the
    existing data owner; it does not acquire data, run research or admit trades.
    A partition crossing the requested or holdout boundary is not opened.
    """
    import hashlib
    start, end, holdout = (parse_time(v) for v in (start_utc, end_utc, holdout_start_utc))
    if None in (start, end, holdout) or not start < end <= holdout:
        raise ValueError("DEVELOPMENT_SLICE_BOUNDARY_INVALID")
    if not pairs or len(pairs) != len(set(pairs)):
        raise ValueError("DEVELOPMENT_PAIR_SET_INVALID")
    root = Path(source_root).resolve()
    selected, seen = [], set()
    for item in manifest.get("artifacts", []):
        if item.get("instrument") not in pairs:
            continue
        first, last = (parse_time(item.get(k)) for k in ("start_utc", "end_utc"))
        if first is None or last is None or first >= last:
            raise ValueError("PARTITION_METADATA_BOUNDARY_INVALID")
        if first < start or last > end or last > holdout:
            continue
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root / "partitions") or not path.name.endswith(".jsonl.gz"):
            raise ValueError("DEVELOPMENT_PARTITION_PATH_INVALID")
        if (path.parent.name != item["instrument"] or path.name != first.strftime("%Y-%m")+".jsonl.gz"
                or first.day != 1 or first.time() != datetime.min.time()
                or last != (first.replace(day=28)+timedelta(days=4)).replace(day=1)):
            raise ValueError("DEVELOPMENT_PARTITION_MONTH_IDENTITY_INVALID")
        key = (item["instrument"], first.isoformat(), last.isoformat())
        if key in seen or any(r["path"] == str(path) for r in selected):
            raise ValueError("DUPLICATE_DEVELOPMENT_PARTITION")
        pin = item.get("sha256", "")
        if len(pin) != 64 or any(c not in "0123456789abcdef" for c in pin):
            raise ValueError("DEVELOPMENT_PARTITION_PIN_INVALID")
        seen.add(key)
        selected.append({"pair":item["instrument"], "path":str(path), "sha256":pin,
                         "start_utc":first.isoformat(), "end_utc":last.isoformat(), "records":item["records"]})
    selected.sort(key=lambda r:(r["pair"], r["start_utc"]))
    for pair in pairs:
        rows = [r for r in selected if r["pair"] == pair]
        if (not rows or parse_time(rows[0]["start_utc"]) != start or parse_time(rows[-1]["end_utc"]) != end
                or any(a["end_utc"] != z["start_utc"] for a,z in zip(rows,rows[1:]))):
            raise ValueError("DEVELOPMENT_PARTITION_COVERAGE_INCOMPLETE")
    plan = {"schema":"AIOS_DEVELOPMENT_PARTITION_SLICE_PLAN_V1", "source_root":str(root),
            "pairs":sorted(pairs), "start_utc":start.isoformat(), "end_exclusive":end.isoformat(),
            "holdout_start_utc":holdout.isoformat(), "partitions":selected,
            "source_corpus_fingerprint":manifest.get("aggregate_corpus_fingerprint"),
            "mixed_source_access":False, "market_scoring_authorized":False}
    plan["plan_sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return plan


def certify_development_partition_slice(plan: dict[str, Any], output_root: Path, *, checkpoint=None) -> dict[str, Any]:
    """Verify only the admitted containers; produce a reference slice and quotes.

    Existing immutable partitions remain single copies. Monthly close snapshots
    are data preparation, not returns, strategy scores or executable financing.
    Unexpected gaps remain explicit blockers for positions open through them.
    """
    import hashlib
    import math
    from automation.forex_engine.forex_historical_dataset_verifier_freezer_v1 import _price_component_valid, _bid_ask_valid
    claimed = plan.get("plan_sha256")
    calculated = hashlib.sha256(json.dumps({k:v for k,v in plan.items() if k != "plan_sha256"},
                               sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    if claimed != calculated:
        raise ValueError("DEVELOPMENT_SLICE_PLAN_CHANGED")
    start, end, holdout = (parse_time(plan[k]) for k in ("start_utc", "end_exclusive", "holdout_start_utc"))
    if None in (start,end,holdout) or not start < end <= holdout or plan.get("mixed_source_access") is not False:
        raise ValueError("DEVELOPMENT_SLICE_BOUNDARY_INVALID")
    # Recheck every entry, including a caller-edited plan, before opening any.
    root = Path(plan["source_root"]).resolve()
    if not plan["pairs"] or len(plan["pairs"]) != len(set(plan["pairs"])):
        raise ValueError("DEVELOPMENT_PAIR_SET_INVALID")
    seen = set()
    for item in plan["partitions"]:
        path = Path(item["path"]).resolve()
        a,z = parse_time(item["start_utc"]),parse_time(item["end_utc"])
        if (not path.is_relative_to(root/"partitions") or not path.name.endswith(".jsonl.gz")
                or a is None or z is None or not start <= a < z <= end <= holdout or item["pair"] not in plan["pairs"]
                or path.parent.name != item["pair"] or path.name != a.strftime("%Y-%m")+".jsonl.gz"
                or a.day != 1 or a.time() != datetime.min.time()
                or z != (a.replace(day=28)+timedelta(days=4)).replace(day=1)
                or type(item["records"]) is not int or item["records"] <= 0
                or not isinstance(item["sha256"],str) or len(item["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in item["sha256"])):
            raise ValueError("DEVELOPMENT_SLICE_ENTRY_INVALID")
        if path in seen:raise ValueError("DUPLICATE_DEVELOPMENT_PARTITION")
        seen.add(path)
    for pair in plan["pairs"]:
        rows = sorted((r for r in plan["partitions"] if r["pair"] == pair),key=lambda r:r["start_utc"])
        if (not rows or parse_time(rows[0]["start_utc"]) != start or parse_time(rows[-1]["end_utc"]) != end
                or any(a["end_utc"] != z["start_utc"] for a,z in zip(rows,rows[1:]))):
            raise ValueError("DEVELOPMENT_PARTITION_COVERAGE_INCOMPLETE")
    output = Path(output_root).resolve()
    if output == root or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("IMMUTABLE_SOURCE_OUTPUT_OVERLAP")
    if output.exists() and any(output.iterdir()):
        raise ValueError("DEVELOPMENT_SLICE_OUTPUT_EXISTS")
    output.mkdir(parents=True,exist_ok=True)
    proofs, snapshots, previous = [], {}, {}
    for item in plan["partitions"]:
        if checkpoint is not None:checkpoint()
        path = Path(item["path"])
        def file_hash():
            with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()
        if file_hash() != item["sha256"]:
            raise ValueError("DEVELOPMENT_PARTITION_HASH_CHANGED")
        pair = item["pair"]; count = 0; unexplained = 0; max_gap = 0.; first_stamp = None
        with gzip.open(path,"rt",encoding="ascii") as stream:
            for line in stream:
                row = json.loads(line); stamp = parse_time(row.get("timestamp"))
                if stamp is None or not parse_time(item["start_utc"]) <= stamp < parse_time(item["end_utc"]) or stamp >= holdout:
                    raise ValueError("DEVELOPMENT_ROW_OUTSIDE_CERTIFIED_PARTITION")
                if row.get("instrument") != pair or row.get("complete") is not True:
                    raise ValueError("DEVELOPMENT_ROW_IDENTITY_INVALID")
                try:
                    numbers = [float(row[side][k]) for side in ("bid","ask","mid") for k in ("o","h","l","c")]
                except (KeyError,TypeError,ValueError):
                    raise ValueError("DEVELOPMENT_QUOTE_GEOMETRY_INVALID") from None
                if (any(not math.isfinite(v) or v<=0 for v in numbers)
                        or not all(_price_component_valid(row.get(side)) for side in ("bid","ask","mid"))
                        or not _bid_ask_valid(row)):
                    raise ValueError("DEVELOPMENT_QUOTE_GEOMETRY_INVALID")
                prior = previous.get(pair)
                if prior is not None:
                    if stamp <= prior:raise ValueError("DEVELOPMENT_ROWS_NOT_CHRONOLOGICAL")
                    minutes = (stamp-prior).total_seconds()/60
                    if minutes != 5:
                        max_gap = max(max_gap,minutes)
                        # Existing owner closure predicate is retained. A
                        # non-closure gap is recorded, never interpolated.
                        if not is_market_close_gap(prior,stamp,minutes/60):unexplained += 1
                previous[pair] = stamp
                first_stamp = first_stamp or stamp; count += 1
                month = stamp.strftime("%Y-%m")
                snapshots[(pair,month)] = {"pair":pair,"month":month,"completed_bar_open_utc":stamp.isoformat(),
                        "quote_available_at_utc":(stamp+timedelta(minutes=5)).isoformat(),
                        "bid_close":float(row["bid"]["c"]),"ask_close":float(row["ask"]["c"]),
                        "mid_close":float(row["mid"]["c"]),"source_partition_sha256":item["sha256"],
                        "forward_quote":None,"financing":None,"excess_return":None,"value_signal":None}
                if count%1024 == 0 and checkpoint is not None:checkpoint()
        if count != item["records"] or count == 0 or file_hash() != item["sha256"]:
            raise ValueError("DEVELOPMENT_PARTITION_COUNT_OR_HASH_CHANGED")
        proofs.append({**item,"observed_records":count,"first_timestamp":first_stamp.isoformat(),
                       "last_timestamp":previous[pair].isoformat(),"unexpected_gaps":unexplained,"maximum_gap_minutes":max_gap})
    quotes = {"schema":"AIOS_DEVELOPMENT_MONTHLY_QUOTES_V1","rows":[snapshots[k] for k in sorted(snapshots)],
              "market_scoring":False,"funding_inputs_not_fabricated":True}
    atomic_json(output/"MONTHLY_QUOTES.json",quotes)
    with (output/"MONTHLY_QUOTES.json").open("rb") as stream:quotes_sha = hashlib.file_digest(stream,"sha256").hexdigest()
    receipt = {"schema":"AIOS_CERTIFIED_DEVELOPMENT_REFERENCE_SLICE_V1", "data_owner":str(Path(__file__).resolve()),
        "plan_sha256":claimed,"start_utc":plan["start_utc"],"end_exclusive":plan["end_exclusive"],
        "holdout_start_utc":plan["holdout_start_utc"],"pairs":plan["pairs"],"partitions":proofs,
        "certified_development_only":True,"raw_prices_duplicated":False,"mixed_H1_files_opened":0,
        "holdout_files_opened":0,"holdout_hashes_computed":0,"market_calls":0,
        "total_records_verified":sum(p["observed_records"] for p in proofs),
        "unexpected_gaps_preserved":sum(p["unexpected_gaps"] for p in proofs),
        "monthly_quotes_path":str(output/"MONTHLY_QUOTES.json"),"monthly_quotes_sha256":quotes_sha,
        "monthly_execution_admitted":False,"financing_contract_complete":False,"forward_excess_return_contract_complete":False,
        "value_contract_complete":False,"monthly_scout_admitted":False,"paper":False,"live":False}
    atomic_json(output/"DEVELOPMENT_ONLY_MANIFEST.json",receipt)
    if read_json(output/"DEVELOPMENT_ONLY_MANIFEST.json") != receipt:
        raise ValueError("DEVELOPMENT_SLICE_READBACK_CHANGED")
    return receipt


def validate_development_financing_table(table: dict[str, Any], *, day: str,
                                         pairs: list[str], holdout_start_utc: str) -> dict[str, Any]:
    """Validate a dated public table without inventing forwards or funding.

    Published charges are already daily charges for the published units. The
    settlement-day count is retained as metadata; never multiply it again.
    This table alone does not certify account-specific execution costs.
    """
    import math
    if not pairs or len(pairs) != len(set(pairs)):
        raise ValueError("DEVELOPMENT_FINANCING_PAIR_SET_INVALID")
    stamp = parse_time(table.get("timestamp"))
    holdout = parse_time(holdout_start_utc)
    if (stamp is None or holdout is None or stamp >= holdout
            or stamp.astimezone(timezone.utc).strftime("%Y-%m-%d") != day
            or table.get("divisionId") != 1 or table.get("tradingGroupId") != 1):
        raise ValueError("DEVELOPMENT_FINANCING_DATE_OR_DIVISION_INVALID")
    required = {pair.replace("_","/") for pair in pairs}
    rows = {}
    for row in table.get("financingRates",[]):
        instrument = row.get("instrument")
        if instrument not in required:continue
        if instrument in rows:raise ValueError("DEVELOPMENT_FINANCING_DUPLICATE")
        try:
            values = {k:float(row[k]) for k in ("longCharge","shortCharge","longRate","shortRate")}
        except (KeyError,ValueError,TypeError):
            raise ValueError("DEVELOPMENT_FINANCING_VALUES_INVALID") from None
        if (not all(math.isfinite(v) for v in values.values()) or row.get("currency") != "USD"
                or type(row.get("units")) is not int or row["units"] <= 0
                or type(row.get("days")) is not int or not 0 <= row["days"] <= 10):
            raise ValueError("DEVELOPMENT_FINANCING_VALUES_INVALID")
        rows[instrument] = {"pair":instrument.replace("/","_"),"day":day,"published_at_utc":stamp.isoformat(),
            "account_currency":"USD","published_units":row["units"],"settlement_days":row["days"],
            **values,"charges_already_daily":True,"forward_quote_verified":False}
    if set(rows) != required:raise ValueError("DEVELOPMENT_FINANCING_PAIR_COVERAGE_INCOMPLETE")
    return {"schema":"AIOS_DEVELOPMENT_PUBLIC_FINANCING_TABLE_V1","day":day,
        "published_at_utc":stamp.isoformat(),"divisionId":1,"tradingGroupId":1,
        "rows":[rows[k] for k in sorted(rows)],"market_scoring":False,"forward_contract_complete":False,
        "publication_timezone_execution_verified":False,"account_specific_execution_admitted":False}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    if "." in text:
        prefix, suffix = text.split(".", 1)
        if "+" in suffix:
            fraction, zone = suffix.split("+", 1)
            text = f"{prefix}.{fraction[:6]}+{zone}"
        elif "-" in suffix:
            fraction, zone = suffix.split("-", 1)
            text = f"{prefix}.{fraction[:6]}-{zone}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def hour_key(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def price(candle: dict[str, Any], side: str, key: str) -> float | None:
    try:
        return float(candle.get(side, {}).get(key))
    except (TypeError, ValueError):
        return None


def is_market_close_gap(start: datetime, end: datetime, gap_hours: float) -> bool:
    if gap_hours <= 1.5:
        return False
    if start.weekday() == 4 and end.weekday() in {6, 0} and gap_hours <= 75:
        return True
    return start.weekday() == 5 or end.weekday() == 6


def validate_practice_artifact(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "instrument": instrument_from_practice_path(path),
        "path": path.as_posix(),
        "sha256": sha256(path.read_bytes()) if path.exists() else None,
        "parse_error": None,
        "granularity": None,
        "complete_count": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "years_covered": 0.0,
        "missing_interval_count": 0,
        "largest_unexplained_open_market_gap_hours": 0.0,
        "duplicate_count": 0,
        "bid_ask_available": False,
        "mid_available": False,
        "spread": {"min": None, "median": None, "mean": None, "max": None},
        "ohlc_geometry_failures": 0,
        "bid_ask_order_failures": 0,
        "data_quality_pass": False,
    }
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - sanitized class only
        result["parse_error"] = type(exc).__name__
        return result
    result["instrument"] = str(data.get("instrument") or instrument_from_practice_path(path))
    result["granularity"] = data.get("granularity")
    times: list[datetime] = []
    seen: set[str] = set()
    spreads: list[float] = []
    for candle in data.get("candles", []):
        if candle.get("complete") is not True:
            continue
        raw_time = str(candle.get("time"))
        parsed = parse_time(raw_time)
        if parsed:
            times.append(parsed)
        if raw_time in seen:
            result["duplicate_count"] += 1
        seen.add(raw_time)
        result["bid_ask_available"] = result["bid_ask_available"] or (isinstance(candle.get("bid"), dict) and isinstance(candle.get("ask"), dict))
        result["mid_available"] = result["mid_available"] or isinstance(candle.get("mid"), dict)
        for side in ("bid", "ask", "mid"):
            values = [price(candle, side, key) for key in ("o", "h", "l", "c")]
            if any(item is None for item in values):
                result["ohlc_geometry_failures"] += 1
                continue
            open_price, high, low, close = values
            if high < max(open_price, close, low) or low > min(open_price, close, high):
                result["ohlc_geometry_failures"] += 1
        bid_close = price(candle, "bid", "c")
        ask_close = price(candle, "ask", "c")
        if bid_close is not None and ask_close is not None:
            if bid_close > ask_close:
                result["bid_ask_order_failures"] += 1
            else:
                spreads.append(ask_close - bid_close)
    times = sorted(times)
    result["complete_count"] = len(times)
    if times:
        result["first_timestamp"] = times[0].isoformat()
        result["last_timestamp"] = times[-1].isoformat()
        result["years_covered"] = round((times[-1] - times[0]).total_seconds() / (365.25 * 24 * 3600), 4)
        largest = 0.0
        missing = 0
        for before, after in zip(times, times[1:]):
            gap_hours = (after - before).total_seconds() / 3600
            if gap_hours > 1.5:
                missing += max(1, int(round(gap_hours)) - 1)
                if not is_market_close_gap(before, after, gap_hours):
                    largest = max(largest, gap_hours)
        result["missing_interval_count"] = missing
        result["largest_unexplained_open_market_gap_hours"] = round(largest, 4)
    if spreads:
        ordered = sorted(spreads)
        result["spread"] = {
            "min": ordered[0],
            "median": ordered[len(ordered) // 2],
            "mean": sum(ordered) / len(ordered),
            "max": ordered[-1],
        }
    result["data_quality_pass"] = (
        result["complete_count"] > 0
        and result["duplicate_count"] == 0
        and result["bid_ask_available"] is True
        and result["ohlc_geometry_failures"] == 0
        and result["bid_ask_order_failures"] == 0
    )
    return result


def build_pair_coverage_matrix() -> dict[str, Any]:
    universe = intended_universe()
    market_v2 = read_json(MARKET_V2_STATE)
    prior_coverage = market_v2.get("quality_reconciliation", {}).get("coverage", {})
    prior_gaps = market_v2.get("quality_reconciliation", {}).get("classified_provider_gaps", {})
    prior_eligible = set(str(item) for item in market_v2.get("eligible_pairs", []))
    manifest = read_json(PRACTICE_INBOX / "practice_history.manifest.json")
    manifest_items = {str(item.get("instrument")): item for item in manifest.get("items", []) if item.get("instrument")}
    files = {instrument_from_practice_path(path): path for path in PRACTICE_INBOX.glob("*.json") if not path.name.endswith(".manifest.json")} if PRACTICE_INBOX.exists() else {}
    rows = []
    for instrument in universe:
        path = files.get(instrument)
        if path:
            metrics = validate_practice_artifact(path)
            manifest_item = manifest_items.get(instrument, {})
            hash_match = bool(manifest_item.get("sha256") == metrics.get("sha256")) if manifest_item.get("sha256") else False
            quality_pass = bool(metrics["data_quality_pass"] and instrument in manifest_items and hash_match)
            state = "ELIGIBLE_FULL_HISTORY" if quality_pass and metrics["years_covered"] >= 9.5 else "ELIGIBLE_PARTIAL_HISTORY" if quality_pass else "INELIGIBLE_BAD_DATA"
            reason = None if state.startswith("ELIGIBLE") else "Practice H1 artifact failed schema, manifest, hash, chronology, OHLC, duplicate, or bid/ask validation."
            row = {
                "instrument": instrument,
                "state": state,
                "granularity": metrics["granularity"],
                "first_timestamp": metrics["first_timestamp"],
                "last_timestamp": metrics["last_timestamp"],
                "years_covered": metrics["years_covered"],
                "h1_candle_count": metrics["complete_count"],
                "missing_interval_count": metrics["missing_interval_count"],
                "largest_unexplained_open_market_gap_hours": metrics["largest_unexplained_open_market_gap_hours"],
                "duplicate_count": metrics["duplicate_count"],
                "bid_ask_available": metrics["bid_ask_available"],
                "mid_available": metrics["mid_available"],
                "spread": metrics["spread"],
                "data_quality_pass": quality_pass,
                "research_eligibility": state.startswith("ELIGIBLE"),
                "exclusion_reason": reason,
                "artifact_hash": metrics["sha256"],
                "manifest_member": instrument in manifest_items,
                "manifest_hash_match": hash_match,
                "prior_m5_coverage": prior_coverage.get(instrument),
                "prior_m5_classified_provider_gaps": prior_gaps.get(instrument),
            }
        else:
            row = {
                "instrument": instrument,
                "state": "INELIGIBLE_INSUFFICIENT_HISTORY",
                "granularity": "H1",
                "first_timestamp": None,
                "last_timestamp": None,
                "years_covered": 0.0,
                "h1_candle_count": 0,
                "missing_interval_count": None,
                "largest_unexplained_open_market_gap_hours": None,
                "duplicate_count": None,
                "bid_ask_available": False,
                "mid_available": False,
                "spread": {"min": None, "median": None, "mean": None, "max": None},
                "data_quality_pass": False,
                "research_eligibility": False,
                "exclusion_reason": "No Human-supplied H1 Practice artifact exists for this intended pair; prior M5 eligibility was %s." % ("PASS" if instrument in prior_eligible else "FAIL"),
                "artifact_hash": None,
                "manifest_member": False,
                "manifest_hash_match": False,
                "prior_m5_coverage": prior_coverage.get(instrument),
                "prior_m5_classified_provider_gaps": prior_gaps.get(instrument),
            }
        rows.append(row)
    eligible = [row for row in rows if row["research_eligibility"]]
    available = [row for row in rows if row["h1_candle_count"]]
    state = {
        "schema": "AIOS_FOREX_PAIR_COVERAGE_MATRIX_V3",
        "packet_id": "PKT-EAST-FOREX-POST-HUMAN-DATA-CONTINUATION-026",
        "status": "COMPLETE" if rows else "NO_INTENDED_UNIVERSE",
        "intended_pair_count": len(rows),
        "data_available_pair_count": len(available),
        "research_eligible_pair_count": len(eligible),
        "excluded_pair_count": len(rows) - len(eligible),
        "research_eligible_pairs": [row["instrument"] for row in eligible],
        "excluded_pairs": [{"instrument": row["instrument"], "state": row["state"], "reason": row["exclusion_reason"]} for row in rows if not row["research_eligibility"]],
        "manifest_safety": {
            "method": manifest.get("method"),
            "endpoint": manifest.get("endpoint"),
            "live": manifest.get("live"),
            "orders": manifest.get("orders"),
            "secret_written": manifest.get("secret_written"),
            "header_written": manifest.get("header_written"),
        },
        "rows": rows,
    }
    state["aggregate_hash"] = sha256(stable(state).encode("utf-8"))
    return state


def h1_practice_map(path: Path) -> dict[str, dict[str, dict[str, float]]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    output: dict[str, dict[str, dict[str, float]]] = {}
    for candle in data.get("candles", []):
        if candle.get("complete") is not True:
            continue
        raw_time = str(candle.get("time"))
        parsed = parse_time(raw_time)
        if not parsed:
            continue
        output[hour_key(parsed)] = {
            side: {key: float(candle[side][key]) for key in ("o", "h", "l", "c")}
            for side in ("bid", "ask", "mid")
            if isinstance(candle.get(side), dict)
        }
    return output


def derive_m5_to_h1(instrument: str, start: datetime, end: datetime) -> dict[str, dict[str, dict[str, float]]]:
    folder = M5_ROOT / "partitions" / instrument
    buckets: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    if not folder.exists():
        return {}
    month = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    end_month = datetime(end.year, end.month, 1, tzinfo=timezone.utc)
    while month <= end_month:
        path = folder / f"{month:%Y-%m}.jsonl.gz"
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    record = json.loads(line)
                    parsed = parse_time(str(record.get("timestamp")))
                    if not parsed or parsed < start or parsed > end:
                        continue
                    buckets[parsed.replace(minute=0, second=0, microsecond=0)].append(record)
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    derived: dict[str, dict[str, dict[str, float]]] = {}
    for hour, records in buckets.items():
        records = sorted(records, key=lambda item: item.get("timestamp", ""))
        if len(records) < 6:
            continue
        side_data: dict[str, dict[str, float]] = {}
        for side in ("bid", "ask", "mid"):
            side_records = [record[side] for record in records if isinstance(record.get(side), dict)]
            if not side_records:
                continue
            side_data[side] = {
                "o": float(side_records[0]["o"]),
                "h": max(float(item["h"]) for item in side_records),
                "l": min(float(item["l"]) for item in side_records),
                "c": float(side_records[-1]["c"]),
            }
        if side_data:
            derived[hour_key(hour)] = side_data
    return derived


def run_overlap_validation(eligible_pairs: list[str]) -> dict[str, Any]:
    rows = []
    total_compared = 0
    total_mismatches = 0
    for instrument in eligible_pairs:
        h1_path = PRACTICE_INBOX / f"{instrument}.H1.json"
        path = h1_path if h1_path.exists() else PRACTICE_INBOX / f"{instrument}.json"
        practice = h1_practice_map(path)
        times = sorted(parse_time(item) for item in practice if parse_time(item))
        if not times:
            rows.append({"instrument": instrument, "status": "FAIL", "overlap_hours": 0, "mismatch_count": 0, "max_abs_difference": None})
            continue
        derived = derive_m5_to_h1(instrument, times[0], times[-1])
        overlap = sorted(set(practice) & set(derived))
        mismatches = 0
        max_diff = 0.0
        for timestamp in overlap:
            for side in ("bid", "ask", "mid"):
                for key in ("o", "h", "l", "c"):
                    left = practice[timestamp].get(side, {}).get(key)
                    right = derived[timestamp].get(side, {}).get(key)
                    if left is None or right is None:
                        continue
                    diff = abs(left - right)
                    max_diff = max(max_diff, diff)
                    if diff > 0.0002:
                        mismatches += 1
        total_compared += len(overlap)
        total_mismatches += mismatches
        rows.append(
            {
                "instrument": instrument,
                "status": "PASS" if overlap and mismatches == 0 else "FAIL",
                "overlap_hours": len(overlap),
                "mismatch_count": mismatches,
                "max_abs_difference": max_diff if overlap else None,
            }
        )
    failed = [row for row in rows if row["status"] != "PASS"]
    return {
        "status": "PASS" if rows and not failed else "FAIL",
        "pair_count": len(rows),
        "failed_pair_count": len(failed),
        "total_overlap_hours": total_compared,
        "total_mismatches": total_mismatches,
        "tolerance": 0.0002,
        "failed_pairs": [row["instrument"] for row in failed],
        "rows": rows,
    }


def execute() -> dict[str, Any]:
    for folder in ("raw", "normalized", "manifests", "quality", "frozen"):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    coverage = build_pair_coverage_matrix()
    universe = [row["instrument"] for row in coverage["rows"]]
    artifacts = sanitized_artifacts()
    eligible_pairs = coverage["research_eligible_pairs"]
    overlap = run_overlap_validation(eligible_pairs) if eligible_pairs else {"status": "NOT_RUN", "reason": "No eligible Practice artifacts."}
    frozen = len(eligible_pairs) >= 1 and overlap["status"] == "PASS"
    state = {
        "schema": "AIOS_FOREX_MULTI_REGIME_CORPUS_V3_STATE",
        "packet_id": "PKT-EAST-FOREX-POST-HUMAN-DATA-CONTINUATION-026",
        "corpus_id": CORPUS_ID,
        "status": "FROZEN_VALID" if frozen else "OVERLAP_VALIDATION_FAILED" if eligible_pairs else "HUMAN_PRACTICE_DATA_ACQUISITION_REQUIRED",
        "frozen": frozen,
        "target_start": "2005-01-01T00:00:00Z",
        "frozen_end": max((row["last_timestamp"] for row in coverage["rows"] if row["research_eligibility"] and row["last_timestamp"]), default=None),
        "target_granularities": ["H1", "H4", "D1", "W1"],
        "target_universe_count": len(universe),
        "target_universe": universe,
        "research_eligible_universe": eligible_pairs,
        "sanitized_artifacts": artifacts,
        "pair_coverage_state_hash": coverage["aggregate_hash"],
        "pair_coverage_counts": {
            "intended": coverage["intended_pair_count"],
            "available": coverage["data_available_pair_count"],
            "eligible": coverage["research_eligible_pair_count"],
            "excluded": coverage["excluded_pair_count"],
        },
        "market_corpus_v2_hash": MARKET_V2_HASH,
        "overlap_validation": overlap,
        "capability_score": 0 if not eligible_pairs else min(90, int(100 * len(eligible_pairs) / max(1, len(universe)))),
        "blocker": "Human-only OANDA Practice GET-only acquisition is required; Codex must not receive the Practice token or authorization header." if not frozen else None,
        "safety": {"credentials_read": False, "practice_orders": False, "live": False, "broker_write": False, "funding": False},
    }
    state["aggregate_hash"] = sha256(stable(state).encode("utf-8"))
    atomic_json(ROOT / "manifests" / "manifest.json", state)
    atomic_json(ROOT / "quality" / "multi_regime_quality.json", state["overlap_validation"])
    atomic_json(COVERAGE_STATE, coverage)
    atomic_json(STATE, state)
    COVERAGE_REPORT.write_text(render_coverage_report(coverage), encoding="utf-8")
    REPORT.write_text(render_report(state), encoding="utf-8")
    return state


def render_report(state: dict[str, Any]) -> str:
    return f"""# AIOS Forex Multi-Regime Corpus V3

WHAT HAPPENED:
Packet 021 evaluated sanitized Human-produced OANDA Practice history artifacts and kept Codex outside the credential boundary.

IS IT SAFE:
YES. No OANDA LIVE call, Practice order, broker write, credential read, or funding action occurred.

WHAT DO I DO NEXT:
Do not paste credentials into Codex. Run the consolidated Human data package outside Codex, then resume Packet 021.

HOW CLOSE ARE WE:
Estimated readiness: {state['capability_score']}% for multi-regime market Corpus V3.

WHICH MODE SHOULD I USE:
PRO if designing a safe Human-only OANDA Practice market-data acquisition lane; INSTANT for status review.

TECHNICAL DETAILS:
- Corpus ID: `{CORPUS_ID}`
- Status: `{state['status']}`
- Frozen: {str(state['frozen']).lower()}
- Target universe count: {state['target_universe_count']}
- Pair coverage: intended={state['pair_coverage_counts']['intended']}, available={state['pair_coverage_counts']['available']}, eligible={state['pair_coverage_counts']['eligible']}, excluded={state['pair_coverage_counts']['excluded']}
- Overlap validation: {state['overlap_validation']['status']}
- Aggregate hash: `{state['aggregate_hash']}`
- Blocker: {state['blocker']}
"""


def render_coverage_report(state: dict[str, Any]) -> str:
    exclusions = "\n".join(f"- {item['instrument']}: {item['state']} - {item['reason']}" for item in state["excluded_pairs"]) or "- None"
    return f"""# AIOS Forex Pair Coverage Matrix V3

WHAT HAPPENED:
Packet 026 classified every intended Forex pair against Human-supplied OANDA Practice H1 artifacts.

IS IT SAFE:
YES. Validation used local sanitized Practice artifacts only. No OANDA request, credential read, order, LIVE call, or broker mutation occurred.

WHAT DO I DO NEXT:
If an excluded pair should be recoverable, rerun only that missing Human Practice partition through the Human-only helper.

HOW CLOSE ARE WE:
Estimated readiness: {state['research_eligible_pair_count']} / {state['intended_pair_count']} pairs eligible for the V3 research corpus.

WHICH MODE SHOULD I USE:
PRO for corpus/research continuation; INSTANT for status review.

TECHNICAL DETAILS:
- Intended pair count: {state['intended_pair_count']}
- Data available pair count: {state['data_available_pair_count']}
- Research eligible pair count: {state['research_eligible_pair_count']}
- Excluded pair count: {state['excluded_pair_count']}
- Aggregate hash: `{state['aggregate_hash']}`

## Exclusions
{exclusions}
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute()
    print(stable({"status": state["status"], "frozen": state["frozen"], "capability_score": state["capability_score"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
