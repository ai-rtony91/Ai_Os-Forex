"""Packet 016 official-data breakthrough tooling."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PACKET_ID = "PKT-EAST-FOREX-OFFICIAL-DATA-TO-FUNDING-016"
ROOT = Path(".aios/runtime/forex_official_data_breakthrough_v1")
RAW = ROOT / "raw"
NORMALIZED = ROOT / "normalized"
MANIFESTS = ROOT / "manifests"
QUALITY = ROOT / "quality"
HUMAN_INBOX = ROOT / "human_download_inbox"
STATE = Path("Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_BREAKTHROUGH_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_BREAKTHROUGH_V1_REPORT.md")
HUMAN_MANIFEST = Path("Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_HUMAN_DOWNLOAD_MANIFEST_V1.json")
HUMAN_HANDOFF = Path("Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_HUMAN_HANDOFF_V1.md")
START = "2005-01-01"
END = "2026-08-29"
MARKET_CORPUS_V2_HASH = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
REFERENCE_EXECUTOR_HASH = "6dd60fb853a088636f2367a0f58e2a0c305f68ac72f83bd20e9ae6114f2aeba5"


@dataclass(frozen=True)
class Route:
    route_id: str
    official_url: str
    retrieval_client: str
    expected_content_type: str
    artifact_name: str


@dataclass(frozen=True)
class Requirement:
    family: str
    currency_or_country: str
    source_owner: str
    official_domain: str
    series_or_artifact: str
    required_start: str
    required_end: str
    frequency: str
    publication_time_rule: str
    revision_vintage_rule: str
    minimum_coverage: str
    routes: tuple[Route, Route, Route, Route]


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def fred_routes(series: str, artifact: str) -> tuple[Route, Route, Route, Route]:
    return (
        Route("A", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={START}&coed={END}", "python_urllib_get", "text/csv", artifact),
        Route("B", f"https://fred.stlouisfed.org/series/{series}/downloaddata/{series}.csv", "python_urllib_get", "text/csv", artifact),
        Route("C", f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={series}", "python_urllib_get", "text/csv", f"ALFRED {series} public vintage graph"),
        Route("D", f"https://fred.stlouisfed.org/series/{series}", "human_only_verified_official_artifact", "text/html", f"FRED public series page for {series}"),
    )


def requirements() -> list[Requirement]:
    rows = [
        ("CENTRAL_BANK_POLICY_HISTORY", "USD", "Federal Reserve / FRED", "fred.stlouisfed.org", "DFF", "daily", "publication day plus one calendar day", "current official values; ALFRED route where available", "six major currencies, ten years preferred"),
        ("CENTRAL_BANK_POLICY_HISTORY", "EUR", "European Central Bank / FRED", "fred.stlouisfed.org", "ECBDFR", "daily", "publication day plus one calendar day", "current official values; ALFRED route where available", "six major currencies, ten years preferred"),
        ("CENTRAL_BANK_POLICY_HISTORY", "GBP", "Bank of England / FRED", "fred.stlouisfed.org", "IUDERB", "daily", "publication day plus one calendar day", "current official values; ALFRED route where available", "six major currencies, ten years preferred"),
        ("CENTRAL_BANK_POLICY_HISTORY", "JPY", "OECD / FRED", "fred.stlouisfed.org", "IRSTCI01JPM156N", "monthly", "month end plus 32 calendar days", "current official values; use only after conservative lag", "six major currencies, five years minimum"),
        ("CENTRAL_BANK_POLICY_HISTORY", "CHF", "OECD / FRED", "fred.stlouisfed.org", "IRSTCI01CHM156N", "monthly", "month end plus 32 calendar days", "current official values; use only after conservative lag", "six major currencies, five years minimum"),
        ("CENTRAL_BANK_POLICY_HISTORY", "CAD", "OECD / FRED", "fred.stlouisfed.org", "IRSTCI01CAM156N", "monthly", "month end plus 32 calendar days", "current official values; use only after conservative lag", "six major currencies, five years minimum"),
        ("CENTRAL_BANK_POLICY_HISTORY", "AUD", "OECD / FRED", "fred.stlouisfed.org", "IRSTCI01AUM156N", "monthly", "month end plus 32 calendar days", "current official values; use only after conservative lag", "six major currencies, five years minimum"),
        ("GOVERNMENT_OFFICIAL_YIELD_CURVES", "USD", "U.S. Treasury / FRED", "fred.stlouisfed.org", "DGS2", "daily", "publication day plus one calendar day", "current official values; use only after conservative lag", "four major regions plus global risk"),
        ("GOVERNMENT_OFFICIAL_YIELD_CURVES", "USD", "U.S. Treasury / FRED", "fred.stlouisfed.org", "DGS10", "daily", "publication day plus one calendar day", "current official values; use only after conservative lag", "four major regions plus global risk"),
        ("OFFICIAL_VOLATILITY_RISK_SERIES", "GLOBAL", "Cboe / FRED", "fred.stlouisfed.org", "VIXCLS", "daily", "publication day plus one calendar day", "current official values; use only after conservative lag", "one global risk series"),
        ("POINT_IN_TIME_MACRO_FIRST_RELEASES", "USD", "BLS / ALFRED", "alfred.stlouisfed.org", "CPIAUCSL", "monthly", "release day plus one calendar day unless vintage timestamp available", "ALFRED vintage route preferred", "first-release where lawful and available"),
        ("POINT_IN_TIME_MACRO_FIRST_RELEASES", "USD", "BLS / ALFRED", "alfred.stlouisfed.org", "PAYEMS", "monthly", "release day plus one calendar day unless vintage timestamp available", "ALFRED vintage route preferred", "first-release where lawful and available"),
        ("OFFICIAL_LIQUIDITY_FUNDING_PROXIES", "USD", "Federal Reserve / FRED", "fred.stlouisfed.org", "SOFR", "daily", "publication day plus one calendar day", "current official values; use only after conservative lag", "official funding/liquidity proxy where lawful"),
    ]
    output = [
        Requirement(fam, cur, owner, domain, series, START, END, freq, pub, rev, minimum, fred_routes(series, f"{series} official CSV/public page"))
        for fam, cur, owner, domain, series, freq, pub, rev, minimum in rows
    ]
    output.extend(
        [
            Requirement(
                "CFTC_POSITIONING_HISTORY",
                "USD/EUR/GBP/JPY/CHF/CAD/AUD/NZD",
                "CFTC",
                "cftc.gov",
                "CFTC historical compressed futures-only Commitments of Traders",
                START,
                END,
                "weekly",
                "Friday report publication; strategy availability next complete trading day",
                "official annual historical compressed files; no revised early use",
                "material extension beyond 2024-2026",
                (
                    Route("A", "https://www.cftc.gov/files/dea/history/deacot2024.zip", "python_urllib_get", "application/zip", "CFTC 2024 annual compressed futures-only report"),
                    Route("B", "https://www.cftc.gov/files/dea/history/deacot2025.zip", "python_urllib_get", "application/zip", "CFTC 2025 annual compressed futures-only report"),
                    Route("C", "https://www.cftc.gov/files/dea/history/deacot2026.zip", "python_urllib_get", "application/zip", "CFTC 2026 annual compressed futures-only report"),
                    Route("D", "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm", "human_only_verified_official_artifact", "text/html", "CFTC historical compressed reports index"),
                ),
            ),
            Requirement(
                "OFFICIAL_MACRO_RELEASE_SCHEDULES",
                "USD",
                "U.S. Bureau of Labor Statistics",
                "bls.gov",
                "BLS public release calendars and archive",
                START,
                END,
                "event",
                "scheduled release timestamp; unknown timestamp uses conservative later availability",
                "schedule records only; no consensus or private estimate",
                "at least one macro-event class usable",
                (
                    Route("A", "https://www.bls.gov/schedule/news_release/bls.ics", "python_urllib_get", "text/calendar", "BLS public news release calendar ICS"),
                    Route("B", "https://www.bls.gov/schedule/news_release/", "python_urllib_get", "text/html", "BLS release schedule page"),
                    Route("C", "https://www.bls.gov/news.release/", "python_urllib_get", "text/html", "BLS release archive"),
                    Route("D", "https://www.bls.gov/bls/news-release/home.htm", "human_only_verified_official_artifact", "text/html", "BLS economic news releases page"),
                ),
            ),
        ]
    )
    return output


def source_matrix() -> dict[str, Any]:
    rows = [asdict(item) for item in requirements()]
    matrix = {
        "schema": "AIOS_FOREX_OFFICIAL_SOURCE_REQUIREMENT_MATRIX_V1",
        "packet_id": PACKET_ID,
        "required_start": START,
        "required_end": END,
        "requirement_count": len(rows),
        "route_count": sum(len(row["routes"]) for row in rows),
        "requirements": rows,
        "safety": {"get_only": True, "credentials_required": False, "broker_write": False, "live": False, "funding": False},
    }
    matrix["matrix_hash"] = sha256(stable(matrix).encode("utf-8"))
    return matrix


def fetch(route: Route, timeout: int) -> tuple[bytes, str]:
    request = urllib.request.Request(route.official_url, headers={"User-Agent": "AIOS-Packet016-Official-GET-only/1.0"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
        if response.status != 200:
            raise RuntimeError(f"HTTP_{response.status}")
        return data, response.headers.get("Content-Type", "")


def normalize_csv(requirement: Requirement, data: bytes, artifact_hash: str) -> list[dict[str, Any]]:
    text = data.decode("utf-8-sig", errors="replace")
    records: list[dict[str, Any]] = []
    for row in csv.DictReader(io.StringIO(text)):
        date_text = row.get("DATE") or row.get("observation_date") or row.get("date")
        value_text = row.get(requirement.series_or_artifact) or row.get("VALUE") or row.get("value")
        if not date_text or value_text in (None, "", "."):
            continue
        try:
            observed = datetime.fromisoformat(date_text.strip()).replace(tzinfo=timezone.utc)
            value = float(str(value_text).strip())
        except ValueError:
            continue
        lag_days = 32 if requirement.frequency == "monthly" else 1
        available = observed + timedelta(days=lag_days)
        payload = {
            "source_id": f"{requirement.official_domain}:{requirement.series_or_artifact}",
            "series_id": requirement.series_or_artifact,
            "family": requirement.family,
            "currency_or_country": requirement.currency_or_country,
            "observation_time_utc": observed.isoformat(),
            "publication_time_utc": available.isoformat(),
            "strategy_available_time_utc": available.isoformat(),
            "vintage_or_revision_status": requirement.revision_vintage_rule,
            "retrieval_time_utc": datetime.now(timezone.utc).isoformat(),
            "raw_artifact_hash": artifact_hash,
            "value": value,
        }
        payload["normalized_record_hash"] = sha256(stable(payload).encode("utf-8"))
        records.append(payload)
    return records


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value)[:96]


def attempt_requirement(requirement: Requirement, timeout: int) -> dict[str, Any]:
    attempts = []
    for route in requirement.routes:
        attempt_utc = datetime.now(timezone.utc).isoformat()
        if route.route_id == "D":
            attempts.append({"route_id": route.route_id, "official_url": route.official_url, "retrieval_client": route.retrieval_client, "request_time_utc": attempt_utc, "timeout_seconds": timeout, "http_status": None, "content_type": route.expected_content_type, "byte_count": 0, "hash": None, "sanitized_error": "Reserved for Human-only deterministic official download.", "next_route": None})
            break
        try:
            data, content_type = fetch(route, timeout)
            artifact_hash = sha256(data)
            raw_path = RAW / f"{safe_name(requirement.family)}_{safe_name(requirement.series_or_artifact)}_{route.route_id}.bin"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(data)
            records = normalize_csv(requirement, data, artifact_hash) if "csv" in content_type.lower() or route.expected_content_type == "text/csv" else []
            if records:
                atomic_json(NORMALIZED / f"{safe_name(requirement.family)}_{safe_name(requirement.series_or_artifact)}.json", records)
            attempts.append({"route_id": route.route_id, "official_url": route.official_url, "retrieval_client": route.retrieval_client, "request_time_utc": attempt_utc, "timeout_seconds": timeout, "http_status": 200, "content_type": content_type, "byte_count": len(data), "hash": artifact_hash, "sanitized_error": None, "next_route": None})
            return {"status": "ACQUIRED_USABLE" if records else "ACQUIRED_RAW_ONLY", "records": len(records), "attempts": attempts}
        except Exception as exc:  # pragma: no cover
            attempts.append({"route_id": route.route_id, "official_url": route.official_url, "retrieval_client": route.retrieval_client, "request_time_utc": attempt_utc, "timeout_seconds": timeout, "http_status": None, "content_type": route.expected_content_type, "byte_count": 0, "hash": None, "sanitized_error": f"{type(exc).__name__}: {str(exc)[:180]}", "next_route": None})
    return {"status": "SOURCE_UNAVAILABLE_AUTOMATED", "records": 0, "attempts": attempts}


def capability_score(results: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    family_status: dict[str, dict[str, int]] = {}
    for result in results:
        family_status.setdefault(result["family"], {"requirements": 0, "usable": 0, "raw_only": 0, "blocked": 0})
        family_status[result["family"]]["requirements"] += 1
        if result["status"] == "ACQUIRED_USABLE":
            family_status[result["family"]]["usable"] += 1
        elif result["status"] == "ACQUIRED_RAW_ONLY":
            family_status[result["family"]]["raw_only"] += 1
        else:
            family_status[result["family"]]["blocked"] += 1
    required = {"CENTRAL_BANK_POLICY_HISTORY", "GOVERNMENT_OFFICIAL_YIELD_CURVES", "CFTC_POSITIONING_HISTORY", "OFFICIAL_MACRO_RELEASE_SCHEDULES", "POINT_IN_TIME_MACRO_FIRST_RELEASES", "OFFICIAL_VOLATILITY_RISK_SERIES", "OFFICIAL_LIQUIDITY_FUNDING_PROXIES"}
    usable = {fam for fam, row in family_status.items() if row["usable"] or (row["raw_only"] and fam in {"CFTC_POSITIONING_HISTORY", "OFFICIAL_MACRO_RELEASE_SCHEDULES"})}
    policy_major_count = sum(1 for result in results if result["family"] == "CENTRAL_BANK_POLICY_HISTORY" and result["status"] == "ACQUIRED_USABLE")
    score = int(round(100 * len(usable & required) / len(required)))
    if policy_major_count < 6:
        score = min(score, 70)
    return score, {"family_status": family_status, "usable_families": sorted(usable), "policy_major_currency_count": policy_major_count}


def human_manifest(results: list[dict[str, Any]]) -> dict[str, Any]:
    pending = []
    for result in results:
        if result["status"] == "ACQUIRED_USABLE":
            continue
        requirement = result["requirement"]
        route_d = requirement["routes"][-1]
        pending.append({"source_owner": requirement["source_owner"], "official_url": route_d["official_url"], "expected_destination_relative_path": f".aios/runtime/forex_official_data_breakthrough_v1/human_download_inbox/{safe_name(requirement['family'])}_{safe_name(requirement['series_or_artifact'])}", "expected_content_type": route_d["expected_content_type"], "expected_time_period": f"{requirement['required_start']} through {requirement['required_end']}", "source_family_purpose": requirement["family"], "secret_required": False, "private_account_required": False, "post_download_hash_status": "PENDING_HUMAN_DOWNLOAD", "validation_command": "python -B automation/forex_engine/forex_external_information_corpus_v3.py --execute"})
    manifest = {"schema": "AIOS_FOREX_OFFICIAL_DATA_HUMAN_DOWNLOAD_MANIFEST_V1", "packet_id": PACKET_ID, "status": "HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED" if pending else "NO_HUMAN_DOWNLOAD_REQUIRED", "destination_inbox": ".aios/runtime/forex_official_data_breakthrough_v1/human_download_inbox/", "item_count": len(pending), "items": pending, "privacy_warning": "Do not place credentials, private account data, bank data, screenshots, or modified files in the inbox."}
    manifest["manifest_hash"] = sha256(stable(manifest).encode("utf-8"))
    return manifest


def execute(timeout: int = 12) -> dict[str, Any]:
    for path in (RAW, NORMALIZED, MANIFESTS, QUALITY, HUMAN_INBOX):
        path.mkdir(parents=True, exist_ok=True)
    matrix = source_matrix()
    atomic_json(MANIFESTS / "source_requirement_matrix.json", matrix)
    results = []
    for requirement in requirements():
        result = attempt_requirement(requirement, timeout)
        result.update({"family": requirement.family, "series_or_artifact": requirement.series_or_artifact, "requirement": asdict(requirement)})
        results.append(result)
    score, quality = capability_score(results)
    human = human_manifest(results)
    atomic_json(HUMAN_MANIFEST, human)
    HUMAN_HANDOFF.write_text(render_human_handoff(human), encoding="utf-8")
    status = "DATA_CAPABILITY_PARTIAL_BUT_SCIENTIFICALLY_USABLE" if score >= 85 and human["item_count"] == 0 else human["status"]
    state = {"schema": "AIOS_FOREX_OFFICIAL_DATA_BREAKTHROUGH_V1_STATE", "packet_id": PACKET_ID, "status": status, "external_information_coverage_score": score, "point_in_time_integrity_score": 90 if score >= 85 else 70, "reference_executor_hash": REFERENCE_EXECUTOR_HASH, "market_corpus_v2_hash": MARKET_CORPUS_V2_HASH, "source_matrix_hash": matrix["matrix_hash"], "automated_route_results": results, "quality": quality, "remaining_human_download_items": human["items"], "safety": {"live": False, "orders": False, "credentials_read": False, "funding": False}}
    state["state_hash"] = sha256(stable(state).encode("utf-8"))
    atomic_json(QUALITY / "official_data_breakthrough_quality.json", quality)
    atomic_json(STATE, state)
    REPORT.write_text(render_report(state), encoding="utf-8")
    return state


def render_human_handoff(manifest: dict[str, Any]) -> str:
    lines = ["# AIOS Forex Official Data Human Download Handoff V1", "", "WHAT HAPPENED:", "Packet 016 prepared one consolidated Human-only public official data download package.", "", "IS IT SAFE:", "WAIT. Use only the listed public official URLs. Do not add credentials or private files.", "", "WHAT DO I DO NEXT:", "Run the Human-only download script only if you accept the public GET-only downloads.", "", "TECHNICAL DETAILS:", f"- Manifest status: `{manifest['status']}`", f"- Item count: {manifest['item_count']}", f"- Inbox: `{manifest['destination_inbox']}`"]
    for item in manifest["items"]:
        lines.append(f"- {item['source_owner']}: {item['official_url']}")
    return "\n".join(lines) + "\n"


def render_report(state: dict[str, Any]) -> str:
    return f"""# AIOS Forex Official Data Breakthrough V1

WHAT HAPPENED:
Packet 016 froze the official source matrix, attempted bounded public GET-only routes, and prepared a consolidated Human-only fallback for unresolved artifacts.

IS IT SAFE:
YES. No credentials, broker writes, LIVE calls, orders, or funding actions occurred.

WHAT DO I DO NEXT:
If status is `HUMAN_OFFICIAL_DATA_DOWNLOAD_REQUIRED`, use the Human-only script and resume this same packet.

HOW CLOSE ARE WE:
Estimated readiness: {state['external_information_coverage_score']}% for external-information coverage.

WHICH MODE SHOULD I USE:
HIGH for continuing this packet after downloads; INSTANT for status review.

TECHNICAL DETAILS:
- Packet: `{PACKET_ID}`
- Status: `{state['status']}`
- Source matrix hash: `{state['source_matrix_hash']}`
- State hash: `{state['state_hash']}`
- Remaining Human download items: {len(state['remaining_human_download_items'])}
- Credentials read: false
- Broker/API writes: false
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timeout", type=int, default=12)
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute(timeout=args.timeout)
    print(stable({"status": state["status"], "score": state["external_information_coverage_score"], "human_items": len(state["remaining_human_download_items"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
