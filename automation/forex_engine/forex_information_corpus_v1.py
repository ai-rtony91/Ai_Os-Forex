"""Build immutable point-in-time information corpus for Packet 013.

Official public HTTPS GET only. No credentials, broker endpoints, or mutations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(".aios/runtime/forex_information_corpus_v1")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_INFORMATION_CORPUS_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_INFORMATION_CORPUS_V1_REPORT.md")
START = "2024-01-01"
END = "2026-08-29"
MARKET_HASH = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
PACKET = "PKT-EAST-FOREX-INFORMATION-EDGE-TO-FUNDING-013"

FRED_SERIES = {
    "DFF": ("A_POLICY_CARRY", "USD", "Federal Reserve Bank of St. Louis / Board of Governors", 1),
    "ECBDFR": ("A_POLICY_CARRY", "EUR", "Federal Reserve Bank of St. Louis / European Central Bank", 1),
    "IUDERB": ("A_POLICY_CARRY", "GBP", "Federal Reserve Bank of St. Louis / Bank of England", 1),
    "IRSTCI01JPM156N": ("A_POLICY_CARRY", "JPY", "Federal Reserve Bank of St. Louis / OECD", 32),
    "IRSTCI01CHM156N": ("A_POLICY_CARRY", "CHF", "Federal Reserve Bank of St. Louis / OECD", 32),
    "IRSTCI01CAM156N": ("A_POLICY_CARRY", "CAD", "Federal Reserve Bank of St. Louis / OECD", 32),
    "IRSTCI01AUM156N": ("A_POLICY_CARRY", "AUD", "Federal Reserve Bank of St. Louis / OECD", 32),
    "IRSTCI01NZM156N": ("A_POLICY_CARRY", "NZD", "Federal Reserve Bank of St. Louis / OECD", 32),
    "VIXCLS": ("D_GLOBAL_RISK_LIQUIDITY", "GLOBAL", "Federal Reserve Bank of St. Louis / CBOE", 1),
    "DGS2": ("D_GLOBAL_RISK_LIQUIDITY", "USD", "Federal Reserve Bank of St. Louis / U.S. Treasury", 1),
    "DGS10": ("D_GLOBAL_RISK_LIQUIDITY", "USD", "Federal Reserve Bank of St. Louis / U.S. Treasury", 1),
}
CFTC_URLS = {
    year: f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
    for year in (2024, 2025, 2026)
}


def stable(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def inventory():
    sources = []
    for series, (family, coverage, owner, delay) in FRED_SERIES.items():
        sources.append({
            "source_id": f"FRED_{series}", "family": family, "source_owner": owner,
            "official_domain": "fred.stlouisfed.org", "dataset": series, "coverage": coverage,
            "retrieval": "HTTPS_GET_CSV", "new_credential_required": False,
            "revision_behavior": "Policy/rate series may receive corrections; conservative availability delay applied.",
            "vintage_availability": "No historical vintage endpoint used",
            "publication_delay_days": delay, "point_in_time_usable": True,
            "terms_status": "OFFICIAL_PUBLIC_DOWNLOAD", "license_status": "SOURCE_TERMS_APPLY",
        })
    for year, url in CFTC_URLS.items():
        sources.append({
            "source_id": f"CFTC_FINANCIAL_FUTURES_{year}", "family": "B_CFTC_POSITIONING",
            "source_owner": "U.S. Commodity Futures Trading Commission", "official_domain": "cftc.gov",
            "dataset": Path(url).name, "coverage": "Supported financial futures contracts",
            "retrieval": "HTTPS_GET_ZIP_CSV", "new_credential_required": False,
            "revision_behavior": "Historical annual archive; source corrections remain possible",
            "vintage_availability": "Annual historical archive", "publication_delay_days": 3,
            "point_in_time_usable": True, "terms_status": "OFFICIAL_PUBLIC_DOWNLOAD",
            "license_status": "U.S. GOVERNMENT PUBLIC DATA",
        })
    sources.extend([
        {"source_id": "OFFICIAL_MACRO_FIRST_RELEASES", "family": "C_MACRO_EVENT_STATE", "source_owner": "Multiple national statistical agencies", "official_domain": "multiple", "dataset": "first-release macro vintages", "coverage": "USD/EUR/GBP/JPY/CHF/CAD/AUD/NZD", "retrieval": "NOT_ACQUIRED", "new_credential_required": False, "revision_behavior": "Material revisions", "vintage_availability": "No single credential-free reproducible archive frozen", "publication_delay_days": None, "point_in_time_usable": False, "reason": "Historical first-release timestamps and vintages unavailable under one bounded official interface", "terms_status": "SOURCE_SPECIFIC", "license_status": "SOURCE_SPECIFIC"},
        {"source_id": "CORPUS_V2_LONG_HORIZON", "family": "E_LONG_HORIZON", "source_owner": "AIOS frozen OANDA Practice corpus", "official_domain": "local-frozen", "dataset": "AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2", "coverage": "58 eligible FX pairs", "retrieval": "LOCAL_READ_ONLY", "new_credential_required": False, "revision_behavior": "Immutable", "vintage_availability": "Frozen", "publication_delay_days": 0, "point_in_time_usable": True, "terms_status": "EXISTING_APPROVED_EVIDENCE", "license_status": "INTERNAL_SANITIZED"},
    ])
    frozen = {"schema": "AIOS_FOREX_INFORMATION_SOURCE_INVENTORY_V1", "frozen_utc": datetime.now(timezone.utc).isoformat(), "sources": sources}
    frozen["hash"] = sha_bytes(stable(sources).encode())
    return frozen


def fetch(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": "AIOS-Packet013-GET-only/1.0"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP_{response.status}")
        return response.read()


def normalize_fred(series, data, metadata):
    family, coverage, _, delay = metadata
    text = data.decode("utf-8-sig")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        date_text = row.get("DATE") or row.get("observation_date")
        value_text = row.get(series)
        if not date_text or value_text in (None, "", "."):
            continue
        observed = datetime.fromisoformat(date_text).replace(tzinfo=timezone.utc)
        available = observed + timedelta(days=delay)
        rows.append({
            "source_id": f"FRED_{series}", "family": family, "coverage": coverage,
            "observation_utc": observed.isoformat(), "published_utc": available.isoformat(),
            "available_to_strategy_utc": available.isoformat(), "revision_or_vintage_id": "DOWNLOAD_2026-08-29",
            "value": float(value_text), "source_hash": sha_bytes(data),
        })
    return rows


def acquire_job(kind, key, url, metadata=None):
    raw = fetch(url)
    if kind == "FRED":
        raw_path = ROOT / "raw" / f"fred_{key}.csv"
        records = normalize_fred(key, raw, metadata)
        normalized_path = ROOT / "normalized" / f"fred_{key}.json"
        source_id = f"FRED_{key}"
    else:
        raw_path = ROOT / "raw" / Path(url).name
        records = normalize_cftc(key, raw)
        normalized_path = ROOT / "normalized" / f"cftc_{key}.json"
        source_id = f"CFTC_FINANCIAL_FUTURES_{key}"
    raw_path.write_bytes(raw)
    atomic_json(normalized_path, records)
    return artifact(raw_path, normalized_path, source_id, len(records))


def normalize_cftc(year, data):
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if not name.lower().endswith((".txt", ".csv")):
                continue
            text = archive.read(name).decode("latin-1")
            for row in csv.DictReader(io.StringIO(text)):
                normalized = {key.strip(): value for key, value in row.items() if key}
                date_text = normalized.get("Report_Date_as_YYYY-MM-DD") or normalized.get("As_of_Date_In_Form_YYMMDD")
                if not date_text:
                    continue
                try:
                    observed = datetime.fromisoformat(date_text).replace(tzinfo=timezone.utc)
                except ValueError:
                    observed = datetime.strptime(date_text, "%y%m%d").replace(tzinfo=timezone.utc)
                # COT positions are Tuesday observations published no earlier than Friday.
                available = observed + timedelta(days=3, hours=21, minutes=30)
                market = normalized.get("Market_and_Exchange_Names") or normalized.get("Market_and_Exchange_Names") or "UNKNOWN"
                rows.append({
                    "source_id": f"CFTC_FINANCIAL_FUTURES_{year}", "family": "B_CFTC_POSITIONING",
                    "coverage": market.strip(), "observation_utc": observed.isoformat(),
                    "published_utc": available.isoformat(), "available_to_strategy_utc": available.isoformat(),
                    "revision_or_vintage_id": f"ANNUAL_ARCHIVE_{year}", "source_hash": sha_bytes(data),
                    "dealer_long": number(normalized, "Dealer_Positions_Long_All"),
                    "dealer_short": number(normalized, "Dealer_Positions_Short_All"),
                    "asset_manager_long": number(normalized, "Asset_Mgr_Positions_Long_All"),
                    "asset_manager_short": number(normalized, "Asset_Mgr_Positions_Short_All"),
                    "leveraged_long": number(normalized, "Lev_Money_Positions_Long_All"),
                    "leveraged_short": number(normalized, "Lev_Money_Positions_Short_All"),
                    "open_interest": number(normalized, "Open_Interest_All"),
                })
    return rows


def number(row, key):
    value = (row.get(key) or "").replace(",", "").strip()
    try:
        return int(value)
    except ValueError:
        return None


def acquire():
    for subroot in ("raw", "normalized", "manifests", "quality", "frozen"):
        (ROOT / subroot).mkdir(parents=True, exist_ok=True)
    source_inventory = inventory()
    atomic_json(ROOT / "manifests/source_inventory.json", source_inventory)
    artifacts = []
    failures = []
    jobs = [("FRED", series, f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={START}&coed={END}", metadata) for series, metadata in FRED_SERIES.items()]
    jobs += [("CFTC", year, url, None) for year, url in CFTC_URLS.items()]
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="packet013-get") as executor:
        future_jobs = {executor.submit(acquire_job, *job): job for job in jobs}
        for future in as_completed(future_jobs):
            kind, key, _, _ = future_jobs[future]
            source_id = f"FRED_{key}" if kind == "FRED" else f"CFTC_FINANCIAL_FUTURES_{key}"
            try:
                artifacts.append(future.result())
            except Exception as exc:
                failures.append({"source_id": source_id, "error_class": type(exc).__name__, "sanitized_error": str(exc)[:160]})
    artifacts.sort(key=lambda item: item["source_id"])
    failures.sort(key=lambda item: item["source_id"])
    manifest = {"schema": "AIOS_FOREX_INFORMATION_CORPUS_V1", "corpus_id": "AIOS_FOREX_INFORMATION_CORPUS_V1", "period": [START, END], "market_corpus_hash": MARKET_HASH, "source_inventory_hash": source_inventory["hash"], "artifacts": artifacts, "failures": failures}
    manifest["aggregate_hash"] = sha_bytes(stable(artifacts).encode())
    atomic_json(ROOT / "manifests/manifest.json", manifest)
    frozen = {"corpus_id": manifest["corpus_id"], "aggregate_hash": manifest["aggregate_hash"], "manifest_hash": sha_bytes((ROOT / "manifests/manifest.json").read_bytes()), "status": "FROZEN_VALID" if artifacts else "NO_ELIGIBLE_EXTERNAL_DATA"}
    atomic_json(ROOT / "frozen/FROZEN.json", frozen)
    state = {**manifest, "packet_id": PACKET, "lock_id": "AIOS-LOCK-f1b2dccc1a1c40c98ec4af8c9012de39", "freeze": frozen, "continuation_active": True, "current_phase": "INFORMATION_CORPUS_FREEZE", "current_action": "freeze complete", "next_action": "INFORMATION_FAMILY_FALSIFICATION", "next_three_actions": ["MARKET_ALIGNMENT", "FAMILY_A_CARRY_POLICY", "FAMILY_B_COT_POSITIONING"], "remaining_authorized_work_count": 12, "alternate_safe_actions": ["FAMILY_D_GLOBAL_RISK_LIQUIDITY", "FAMILY_E_LONG_HORIZON_RELATIVE_VALUE_MOMENTUM"], "terminal_state_candidate": None, "pre_terminal_audit_status": "FAIL_CONTINUE", "same_packet_resume_command": "python -B -m automation.forex_engine.forex_information_edge_program_v1 --execute", "safety": {"credentials": False, "broker_write": False, "live": False, "money_movement": False}}
    atomic_json(STATE, state)
    REPORT.write_text(f"# AIOS Forex Information Corpus V1\n\n- Status: `{frozen['status']}`\n- Sources acquired: {len(artifacts)}\n- Failures: {len(failures)}\n- Aggregate hash: `{manifest['aggregate_hash']}`\n- Credentials: false\n- Broker/LIVE: false\n", encoding="utf-8")
    return state


def artifact(raw_path, normalized_path, source_id, records):
    return {"source_id": source_id, "raw_path": raw_path.as_posix(), "raw_hash": sha_bytes(raw_path.read_bytes()), "normalized_path": normalized_path.as_posix(), "normalized_hash": sha_bytes(normalized_path.read_bytes()), "records": records}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--acquire", action="store_true")
    args = parser.parse_args()
    if args.inventory:
        value = inventory()
        atomic_json(ROOT / "manifests/source_inventory.json", value)
        print(stable({"inventory_hash": value["hash"], "sources": len(value["sources"])}))
        return 0
    if args.acquire:
        value = acquire()
        print(stable({"status": value["freeze"]["status"], "artifacts": len(value["artifacts"]), "failures": len(value["failures"])}))
        return 0
    parser.error("--inventory or --acquire required")


INTELLIGENCE_CONTRACT_V1 = "FX_POINT_IN_TIME_INTELLIGENCE_V1"
INTELLIGENCE_KINDS_V1 = frozenset({"NEWS", "CPI", "JOBS", "GDP", "PMI", "POLICY_RATE",
    "CENTRAL_BANK_SPEECH", "MARKET_RATE", "GEOPOLITICAL", "EMERGENCY_POLICY", "FINANCIAL_STRESS"})


def intelligence_utc_v1(value):
    """Require explicit offset. Ambiguous local clocks cannot be guessed."""
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("INTELLIGENCE_TIME_INVALID")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("INTELLIGENCE_TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


def calendar_utc_v1(local_time, zone, fold=None, *, zone_data=None):
    """DST gaps fail; DST folds require an explicit 0/1 choice."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    local = datetime.fromisoformat(local_time)
    if local.tzinfo is not None:
        raise ValueError("CALENDAR_LOCAL_TIME_REQUIRED")
    if fold is not None and (type(fold) is not int or fold not in (0, 1)):
        raise ValueError("CALENDAR_FOLD_INVALID")
    try:
        tz = ZoneInfo(zone) if zone_data is None else zone_data
    except ZoneInfoNotFoundError:
        raise ValueError("CALENDAR_TIMEZONE_DATA_UNAVAILABLE") from None
    if not isinstance(tz, ZoneInfo) or tz.key != zone:
        raise ValueError("CALENDAR_TIMEZONE_CONTRACT_MISMATCH")
    candidates = [local.replace(tzinfo=tz, fold=n) for n in (0, 1)]
    valid = [c for c in candidates if c.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) == local]
    if not valid:
        raise ValueError("CALENDAR_DST_GAP")
    if len({c.utcoffset() for c in valid}) > 1 and fold not in (0, 1):
        raise ValueError("CALENDAR_DST_FOLD_REQUIRED")
    return candidates[0 if fold is None else fold].astimezone(timezone.utc).isoformat()


def normalize_intelligence_v1(raw, source):
    """Versioned contract; legacy current-vintage corpus is never auto-admitted.

    Text is bounded inert evidence. Economic surprise has no assumed FX sign.
    Admission is a separate source-owner decision, including licensing/coverage.
    """
    import math
    allowed = {"event_id", "version_id", "vintage", "kind", "event_at", "publication_at", "first_seen_at",
        "available_at", "expires_at", "status", "currencies", "horizon_seconds", "uncertainty",
        "headline", "story_id", "direction", "confidence", "quality", "actual", "forecast",
        "forecast_available_at", "revision", "scheduled_at", "evidence_digest"}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError("INTELLIGENCE_FIELDS_NOT_ALLOWLISTED")
    if not source.get("admitted") or not source.get("license") or not source.get("coverage"):
        raise ValueError("INTELLIGENCE_SOURCE_NOT_ADMITTED")
    def label(value, maximum=128):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError("INTELLIGENCE_LABEL_INVALID")
        return value
    row = {k: label(raw[k]) for k in ("event_id", "version_id", "vintage", "kind")}
    if row["kind"] not in INTELLIGENCE_KINDS_V1:
        raise ValueError("INTELLIGENCE_KIND_NOT_ALLOWLISTED")
    row.update(contract=INTELLIGENCE_CONTRACT_V1, source_id=label(source["source_id"]),
               source_url=label(source["url"], 512), license=label(source["license"]),
               source_scope=label(source["coverage"]))
    times = {key: intelligence_utc_v1(raw[key]) for key in (
        "event_at", "publication_at", "first_seen_at", "available_at", "expires_at")}
    if times["available_at"] < max(times["publication_at"], times["first_seen_at"]) or times["expires_at"] <= times["available_at"]:
        raise ValueError("INTELLIGENCE_CAUSAL_CLOCK_INVALID")
    row.update({key: value.isoformat() for key, value in times.items()})
    status = raw.get("status", "ACTIVE")
    quality = raw.get("quality", "UNKNOWN")
    if status not in {"ACTIVE", "CANCELLED", "RESCHEDULED"} or quality not in {"KNOWN", "UNKNOWN", "MISSING", "STALE", "CONFLICT"}:
        raise ValueError("INTELLIGENCE_STATE_INVALID")
    currencies = raw["currencies"]
    if not isinstance(currencies, list) or not 1 <= len(currencies) <= 8 or len(set(currencies)) != len(currencies) or any(
            not isinstance(c, str) or len(c) != 3 or not c.isalpha() or c != c.upper() for c in currencies):
        raise ValueError("INTELLIGENCE_CURRENCY_INVALID")
    horizon = raw["horizon_seconds"]
    if type(horizon) is not int or not 1 <= horizon <= 31536000:
        raise ValueError("INTELLIGENCE_HORIZON_INVALID")
    direction = raw.get("direction", {})
    if not isinstance(direction, dict) or set(direction) - set(currencies) or any(
            type(v) not in (int, float) or not math.isfinite(v) or not -1 <= v <= 1 for v in direction.values()):
        raise ValueError("INTELLIGENCE_DIRECTION_INVALID")
    confidence = raw.get("confidence")
    if confidence is not None and (type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
        raise ValueError("INTELLIGENCE_CONFIDENCE_INVALID")
    headline = raw.get("headline", "")
    if not isinstance(headline, str) or len(headline) > 512:
        raise ValueError("INTELLIGENCE_PAYLOAD_TOO_LARGE")
    uncertainty = label(raw.get("uncertainty", "UNCALIBRATED"))
    story_id = label(raw.get("story_id") or sha_bytes(" ".join(headline.lower().split()).encode()))
    row.update(status=status, quality=quality, currencies=sorted(currencies), horizon_seconds=horizon,
        direction=direction, confidence=confidence, uncertainty=uncertainty, headline=headline, story_id=story_id,
        revision=raw.get("revision", 0), scheduled_at=None, surprise=None)
    if type(row["revision"]) is not int or not 0 <= row["revision"] <= 100000:
        raise ValueError("INTELLIGENCE_REVISION_INVALID")
    if raw.get("scheduled_at"):
        row["scheduled_at"] = intelligence_utc_v1(raw["scheduled_at"]).isoformat()
    if "actual" in raw:
        actual = raw["actual"]
        if type(actual) not in (float, int) or not math.isfinite(actual):
            raise ValueError("INTELLIGENCE_ACTUAL_INVALID")
        row["actual"] = actual
        if "forecast" in raw:
            forecast = raw["forecast"]
            if type(forecast) not in (float, int) or not math.isfinite(forecast) or not raw.get("forecast_available_at"):
                raise ValueError("INTELLIGENCE_FORECAST_INVALID")
            forecast_time = intelligence_utc_v1(raw["forecast_available_at"])
            if forecast_time >= times["event_at"] or forecast_time > times["available_at"]:
                raise ValueError("INTELLIGENCE_HINDSIGHT_FORECAST")
            row.update(forecast=forecast, forecast_available_at=forecast_time.isoformat(), surprise=actual-forecast)
    supplied = raw.get("evidence_digest")
    if supplied is not None and (not isinstance(supplied, str) or len(supplied) != 64 or any(c not in "0123456789abcdef" for c in supplied)):
        raise ValueError("INTELLIGENCE_DIGEST_INVALID")
    row["evidence_digest"] = supplied or sha_bytes(stable(raw).encode())
    row["identity_sha256"] = sha_bytes(stable(row).encode())
    return row


class IntelligenceCacheV1:
    """Bounded immutable feature cache, not a new state owner or data admission."""
    def __init__(self, events, sources, max_events=4096):
        if type(max_events) is not int or not 1 <= max_events <= 4096 or len(events) > max_events or not 1 <= len(sources) <= 32:
            raise ValueError("INTELLIGENCE_CACHE_LIMIT")
        if any(not isinstance(e, dict) or e.get("source_id") not in sources for e in events):
            raise ValueError("INTELLIGENCE_SOURCE_NOT_ADMITTED")
        rows = [normalize_intelligence_v1({k: v for k, v in event.items() if k != "source_id"}, sources[event["source_id"]]) for event in events]
        identities = {}
        for row in rows:
            key = (row["source_id"], row["event_id"], row["version_id"])
            if key in identities and identities[key] != row["identity_sha256"]:
                raise ValueError("INTELLIGENCE_VERSION_CONFLICT")
            identities[key] = row["identity_sha256"]
        self._rows = tuple(sorted({r["identity_sha256"]: r for r in rows}.values(),
                                 key=lambda r: (r["available_at"], r["identity_sha256"])))
        self.identity = sha_bytes(stable(self._rows).encode())

    def as_of(self, decision_at, pair, horizon_seconds, kinds=None):
        at = intelligence_utc_v1(decision_at)
        parts = pair.split("_")
        if len(parts) != 2 or parts[0] == parts[1] or any(len(c) != 3 for c in parts):
            raise ValueError("INTELLIGENCE_PAIR_INVALID")
        if type(horizon_seconds) is not int or horizon_seconds < 1:
            raise ValueError("INTELLIGENCE_QUERY_HORIZON_INVALID")
        if kinds is not None and (not isinstance(kinds, (tuple, list)) or not set(kinds) <= INTELLIGENCE_KINDS_V1):
            raise ValueError("INTELLIGENCE_QUERY_KIND_INVALID")
        visible = [r for r in self._rows if intelligence_utc_v1(r["available_at"]) <= at and set(r["currencies"]) & set(parts)
                   and (kinds is None or r["kind"] in kinds)]
        latest = {}
        for r in visible:
            key = (r["source_id"], r["event_id"])
            latest[key] = r
        live = [r for r in latest.values() if r["status"] != "CANCELLED" and intelligence_utc_v1(r["expires_at"]) > at
                and r["horizon_seconds"] >= horizon_seconds]
        # Explicit syndication IDs: one story contributes once, contradictory copies stay visible as CONFLICT.
        dedup = {}
        for r in live:
            key = (r["story_id"], r["vintage"], r["kind"])
            if key in dedup and (dedup[key]["direction"] != r["direction"] or dedup[key]["quality"] != r["quality"]):
                return {"state": "CONFLICT", "direction": None, "confidence": None, "uncertainty": "CONFLICTING_SYNDICATION",
                        "evidence_count": len(live), "pair": pair, "decision_at": at.isoformat()}
            dedup.setdefault(key, r)
        live = list(dedup.values())
        currencies = {}
        for currency in parts:
            evidence = [r for r in live if currency in r["currencies"]]
            values = [r["direction"][currency] for r in evidence if r["quality"] == "KNOWN" and currency in r["direction"]]
            conflict = bool(values) and min(values) < 0 < max(values)
            state = "CONFLICT" if conflict or any(r["quality"] == "CONFLICT" for r in evidence) else (
                "KNOWN" if values and all(r["quality"] == "KNOWN" for r in evidence) else
                "UNKNOWN" if evidence else "STALE" if any(currency in r["currencies"] for r in latest.values()) else "MISSING")
            currencies[currency] = {"state": state, "direction": sum(values)/len(values) if state == "KNOWN" else None,
                "confidence": None, "uncertainty": "UNCALIBRATED", "horizon_seconds": horizon_seconds,
                "evidence": sorted(r["evidence_digest"] for r in evidence),
                "latest_available_at": max((r["available_at"] for r in evidence), default=None),
                "vintages": sorted({r["vintage"] for r in evidence})}
        known = all(c["state"] == "KNOWN" for c in currencies.values())
        state = "KNOWN" if known else "CONFLICT" if any(c["state"] == "CONFLICT" for c in currencies.values()) else (
            "STALE" if any(c["state"] == "STALE" for c in currencies.values()) else "MISSING" if not live else "UNKNOWN")
        scheduled = [intelligence_utc_v1(r["scheduled_at"]) for r in live if r["scheduled_at"] and r["status"] != "CANCELLED"]
        return {"state": state, "direction": (currencies[parts[0]]["direction"]-currencies[parts[1]]["direction"])/2 if known else None,
            "confidence": None, "uncertainty": "UNCALIBRATED", "currency_context": currencies,
            "event_proximity_seconds": min((abs((t-at).total_seconds()) for t in scheduled), default=None),
            "alerts": sorted({r["kind"] for r in live if r["kind"] in {"GEOPOLITICAL", "EMERGENCY_POLICY", "FINANCIAL_STRESS"}}),
            "evidence_count": len(live), "evidence_identity": sha_bytes(stable(sorted(r["identity_sha256"] for r in live)).encode()),
            "decision_at": at.isoformat(), "pair": pair, "orders_allowed": False}


def intelligence_model_v1(headline, provenance, adapter=None):
    """Optional offline model is data, never authority. No model confidence is fabricated."""
    if not isinstance(headline, str) or len(headline) > 512:
        raise ValueError("INTELLIGENCE_PAYLOAD_TOO_LARGE")
    required = {"model", "model_version", "prompt_sha256", "training_cutoff", "historical_clean_oos"}
    if set(provenance) != required or provenance["historical_clean_oos"] is not False:
        raise ValueError("INTELLIGENCE_MODEL_PROVENANCE_INVALID")
    if any(not isinstance(provenance[k], str) or not 1 <= len(provenance[k]) <= 128 for k in required-{"historical_clean_oos"}) or (
            len(provenance["prompt_sha256"]) != 64 or any(c not in "0123456789abcdef" for c in provenance["prompt_sha256"])):
        raise ValueError("INTELLIGENCE_MODEL_PROVENANCE_INVALID")
    base = {"state": "UNKNOWN", "confidence": None, "direction": None, "uncertainty": "UNCALIBRATED",
            "provenance": dict(provenance), "input_sha256": sha_bytes(headline.encode()), "orders_allowed": False}
    if adapter is None:
        tokens = set(headline.lower().split())
        positive, negative = bool(tokens & {"strengthens", "rises", "expands"}), bool(tokens & {"weakens", "falls", "contracts"})
        base.update(label="MIXED" if positive and negative else "POSITIVE_TEXT" if positive else "NEGATIVE_TEXT" if negative else "UNKNOWN_TEXT",
                    classifier="DETERMINISTIC_LEXICON_V1")
        # Text tone is deliberately not currency direction.
    else:
        try:
            output = adapter(headline)
            if not isinstance(output, dict) or set(output) != {"label"} or output["label"] not in {"POSITIVE_TEXT", "NEGATIVE_TEXT", "MIXED", "UNKNOWN_TEXT"}:
                raise ValueError("MODEL_OUTPUT_INVALID")
            base.update(output)
        except Exception:
            base.update(label="UNKNOWN_TEXT", failure_code="OPTIONAL_MODEL_UNAVAILABLE")
    base["output_sha256"] = sha_bytes(stable(base).encode())
    return base


def intelligence_request_v1(request, provider, now, last_request_at=None, calls_in_window=0):
    """Validate a proposed adapter call; performs no networking, retries or fallback."""
    from urllib.parse import urlparse
    if set(request) != {"type", "url", "timeout_seconds", "max_bytes"} or request["type"] not in provider["request_types"]:
        raise ValueError("INTELLIGENCE_REQUEST_NOT_ALLOWLISTED")
    url = urlparse(request["url"])
    if url.scheme != "https" or url.hostname not in provider["hosts"] or url.username or url.password or url.query or url.fragment:
        raise ValueError("INTELLIGENCE_PROVIDER_NOT_ALLOWLISTED")
    if not 0 < request["timeout_seconds"] <= 10 or not 1 <= request["max_bytes"] <= 65536:
        raise ValueError("INTELLIGENCE_REQUEST_LIMIT")
    at = intelligence_utc_v1(now)
    if calls_in_window >= provider["max_calls_per_window"] or (last_request_at and
            (at-intelligence_utc_v1(last_request_at)).total_seconds() < provider["minimum_interval_seconds"]):
        return {"state": "RATE_LIMITED", "fallback_allowed": False}
    return {"state": "PREPARED_ONLY", "method": "GET", "fallback_allowed": False, "request": dict(request)}


def intelligence_retry_v1(status):
    return "BOUNDED_BACKOFF" if status in {408, 429, 500, 502, 503, 504} else "OWNER_ACCESS_REQUIRED" if status in {401, 403} else "DO_NOT_RETRY"


if __name__ == "__main__":
    raise SystemExit(main())
