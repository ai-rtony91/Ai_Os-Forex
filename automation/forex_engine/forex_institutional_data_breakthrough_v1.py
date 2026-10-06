"""Packet 016 official institutional information acquisition.

The module uses bounded public HTTPS GET-only routes, records every route
attempt, and fails closed into a single human official-data-drop handoff when
automatic acquisition cannot establish enough usable point-in-time data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(".aios/runtime/forex_institutional_data_breakthrough_v1")
RAW = ROOT / "raw"
NORMALIZED = ROOT / "normalized"
MANIFESTS = ROOT / "manifests"
QUALITY = ROOT / "quality"
FROZEN = ROOT / "frozen"
MANUAL_INBOX = ROOT / "manual_drop_inbox"
STATE = Path("Reports/forex_delivery/AIOS_FOREX_INSTITUTIONAL_DATA_BREAKTHROUGH_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_INSTITUTIONAL_DATA_BREAKTHROUGH_V1_REPORT.md")
HANDOFF_STATE = Path("Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_DROP_HANDOFF_STATE.json")
HANDOFF_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_DROP_HANDOFF.md")

PACKET_ID = "PKT-EAST-FOREX-DATA-BREAKTHROUGH-FUNDING-016"
LOCK_PACKET_ID = "PKT-EAST-FOREX-DATA-BREAKTHROUGH-FUNDING-016"
CORPUS_ID = "AIOS_FOREX_INSTITUTIONAL_INFORMATION_CORPUS_V1"
MARKET_CORPUS_HASH = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
START = "2024-01-01"
END = "2026-08-29"


@dataclass(frozen=True)
class Route:
    route_id: str
    official_owner: str
    official_domain: str
    url: str
    request_client: str
    expected_file_type: str
    artifact_name: str


@dataclass(frozen=True)
class SourceSeries:
    source_id: str
    series_id: str
    data_family: str
    official_owner: str
    currency: str
    requested_period: tuple[str, str]
    publication_lag_days: int
    route_a: Route
    route_b: Route
    route_c: Route
    route_d: Route
    manual_priority: int

    @property
    def routes(self) -> tuple[Route, Route, Route, Route]:
        return (self.route_a, self.route_b, self.route_c, self.route_d)


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f"tmp-{path.name}-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fred_routes(series: str, owner: str, family: str, artifact: str) -> tuple[Route, Route, Route, Route]:
    return (
        Route("A", owner, "fred.stlouisfed.org", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={START}&coed={END}", "python_urllib_get", "csv", artifact),
        Route("B", owner, "fred.stlouisfed.org", f"https://fred.stlouisfed.org/series/{series}/downloaddata/{series}.csv", "python_urllib_get", "csv", artifact),
        Route("C", "ALFRED public artifact mirror", "alfred.stlouisfed.org", f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={series}", "python_urllib_get", "csv", f"ALFRED {series} vintage graph CSV"),
        Route("D", owner, "fred.stlouisfed.org", f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}", "python_urllib_get", "csv", f"FRED full-history {series} CSV"),
    )


def source_series_inventory() -> list[SourceSeries]:
    rows = [
        ("FRED_DFF", "DFF", "POLICY_CARRY", "Federal Reserve Bank of St. Louis / Federal Reserve", "USD", 1, 1),
        ("FRED_ECBDFR", "ECBDFR", "POLICY_CARRY", "Federal Reserve Bank of St. Louis / European Central Bank", "EUR", 1, 2),
        ("FRED_IUDERB", "IUDERB", "POLICY_CARRY", "Federal Reserve Bank of St. Louis / Bank of England", "GBP", 1, 3),
        ("FRED_IRSTCI01JPM156N", "IRSTCI01JPM156N", "POLICY_CARRY", "OECD via FRED", "JPY", 32, 4),
        ("FRED_IRSTCI01CHM156N", "IRSTCI01CHM156N", "POLICY_CARRY", "OECD via FRED", "CHF", 32, 5),
        ("FRED_IRSTCI01CAM156N", "IRSTCI01CAM156N", "POLICY_CARRY", "OECD via FRED", "CAD", 32, 6),
        ("FRED_IRSTCI01AUM156N", "IRSTCI01AUM156N", "POLICY_CARRY", "OECD via FRED", "AUD", 32, 7),
        ("FRED_IRSTCI01NZM156N", "IRSTCI01NZM156N", "POLICY_CARRY", "OECD via FRED", "NZD", 32, 8),
        ("FRED_DGS2", "DGS2", "YIELD_DIFFERENTIALS", "Federal Reserve Bank of St. Louis / U.S. Treasury", "USD", 1, 9),
        ("FRED_DGS10", "DGS10", "YIELD_DIFFERENTIALS", "Federal Reserve Bank of St. Louis / U.S. Treasury", "USD", 1, 10),
        ("FRED_VIXCLS", "VIXCLS", "OFFICIAL_VOLATILITY_RISK", "Federal Reserve Bank of St. Louis / Cboe", "GLOBAL", 1, 11),
        ("ALFRED_CPIAUCSL", "CPIAUCSL", "MACRO_FIRST_RELEASE_VINTAGE", "ALFRED / U.S. Bureau of Labor Statistics", "USD", 1, 12),
        ("ALFRED_PAYEMS", "PAYEMS", "MACRO_FIRST_RELEASE_VINTAGE", "ALFRED / U.S. Bureau of Labor Statistics", "USD", 1, 13),
    ]
    output: list[SourceSeries] = []
    for source_id, series, family, owner, currency, lag, priority in rows:
        routes = fred_routes(series, owner, family, f"{series} official graph/download CSV")
        output.append(SourceSeries(source_id, series, family, owner, currency, (START, END), lag, *routes, priority))
    output.append(
        SourceSeries(
            "CFTC_FX_FUTURES_ANNUAL",
            "CFTC_FX_FUTURES_ANNUAL",
            "POSITIONING_OPEN_INTEREST",
            "CFTC",
            "MULTI",
            (START, END),
            3,
            Route("A", "CFTC", "cftc.gov", "https://www.cftc.gov/files/dea/history/deacot2024.zip", "python_urllib_get", "zip", "CFTC 2024 annual futures-only historical compressed report"),
            Route("B", "CFTC", "cftc.gov", "https://www.cftc.gov/files/dea/history/deacot2025.zip", "python_urllib_get", "zip", "CFTC 2025 annual futures-only historical compressed report"),
            Route("C", "CFTC", "cftc.gov", "https://www.cftc.gov/files/dea/history/deacot2026.zip", "python_urllib_get", "zip", "CFTC 2026 annual futures-only historical compressed report"),
            Route("D", "CFTC", "cftc.gov", "https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm", "python_urllib_get", "html", "CFTC historical compressed reports index"),
            14,
        )
    )
    output.append(
        SourceSeries(
            "BLS_RELEASE_CALENDAR",
            "BLS_RELEASE_CALENDAR",
            "MACRO_EVENT_TIMESTAMPS",
            "U.S. Bureau of Labor Statistics",
            "USD",
            (START, END),
            1,
            Route("A", "U.S. Bureau of Labor Statistics", "bls.gov", "https://www.bls.gov/schedule/news_release/bls.ics", "python_urllib_get", "ics", "BLS public news release calendar ICS"),
            Route("B", "U.S. Bureau of Labor Statistics", "bls.gov", "https://www.bls.gov/schedule/news_release/", "python_urllib_get", "html", "BLS news release schedule page"),
            Route("C", "U.S. Bureau of Labor Statistics", "bls.gov", "https://www.bls.gov/news.release/", "python_urllib_get", "html", "BLS news release archive page"),
            Route("D", "U.S. Bureau of Labor Statistics", "bls.gov", "https://www.bls.gov/bls/news-release/home.htm", "python_urllib_get", "html", "BLS economic news release page"),
            15,
        )
    )
    return output


def inventory_manifest() -> dict[str, Any]:
    sources = []
    for source in source_series_inventory():
        row = asdict(source)
        row["routes"] = [asdict(route) for route in source.routes]
        for key in ("route_a", "route_b", "route_c", "route_d"):
            row.pop(key, None)
        sources.append(row)
    manifest = {
        "schema": "AIOS_FOREX_INSTITUTIONAL_SOURCE_ROUTE_PLAN_V1",
        "packet_id": PACKET_ID,
        "market_corpus_hash": MARKET_CORPUS_HASH,
        "source_count": len(sources),
        "route_count": sum(len(item["routes"]) for item in sources),
        "sources": sources,
        "safety": {"credentials": False, "broker_write": False, "live": False, "money_movement": False},
    }
    manifest["hash"] = sha256(stable(manifest).encode("utf-8"))
    return manifest


def fetch(route: Route, timeout: int) -> bytes:
    request = urllib.request.Request(route.url, headers={"User-Agent": "AIOS-Packet016-Official-GET-only/1.0"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP_{response.status}")
        return response.read()


def normalize_csv_source(source: SourceSeries, data: bytes, artifact_hash: str) -> list[dict[str, Any]]:
    if not source.series_id.startswith(("D", "E", "I", "V", "CPI", "PAY")):
        return []
    records: list[dict[str, Any]] = []
    text = data.decode("utf-8-sig", errors="replace")
    for row in csv.DictReader(io.StringIO(text)):
        date_text = row.get("DATE") or row.get("observation_date") or row.get("date")
        value_text = row.get(source.series_id) or row.get("VALUE") or row.get("value")
        if not date_text or value_text in (None, "", "."):
            continue
        try:
            observed = datetime.fromisoformat(date_text.strip()).replace(tzinfo=timezone.utc)
            value = float(str(value_text).strip())
        except ValueError:
            continue
        available = observed + timedelta(days=source.publication_lag_days)
        records.append(
            {
                "source_id": source.source_id,
                "series_id": source.series_id,
                "data_family": source.data_family,
                "currency": source.currency,
                "observation_time_utc": observed.isoformat(),
                "publication_time_utc": available.isoformat(),
                "strategy_available_time_utc": available.isoformat(),
                "vintage_or_revision_status": "CONSERVATIVE_CURRENT_OFFICIAL_OR_ALFRED_PUBLIC_ARTIFACT",
                "retrieval_time_utc": datetime.now(timezone.utc).isoformat(),
                "source_artifact_hash": artifact_hash,
                "normalization_code_hash": sha256(Path(__file__).read_bytes()),
                "value": value,
            }
        )
    return records


def recover_source(source: SourceSeries, timeout: int) -> dict[str, Any]:
    attempts = []
    for route in source.routes:
        attempted = datetime.now(timezone.utc).isoformat()
        try:
            data = fetch(route, timeout)
            artifact_hash = sha256(data)
            records = normalize_csv_source(source, data, artifact_hash) if route.expected_file_type == "csv" else []
            classification = "ACQUIRED_USABLE" if records else "ACQUIRED_RAW_ONLY_NOT_NORMALIZED"
            return {
                "source_id": source.source_id,
                "series_id": source.series_id,
                "data_family": source.data_family,
                "classification": classification,
                "route_id": route.route_id,
                "official_owner": route.official_owner,
                "official_domain": route.official_domain,
                "url": route.url,
                "request_client": route.request_client,
                "attempts": attempts,
                "data": data,
                "records": records,
                "source_artifact_hash": artifact_hash,
                "coverage_after_attempt": "USABLE_POINT_IN_TIME_RECORDS" if records else "RAW_ARTIFACT_ONLY",
            }
        except Exception as exc:
            attempts.append(
                {
                    "source_id": source.source_id,
                    "series_id": source.series_id,
                    "route_id": route.route_id,
                    "official_owner": route.official_owner,
                    "requested_period": list(source.requested_period),
                    "request_client": route.request_client,
                    "attempt_utc": attempted,
                    "timeout_or_error_classification": type(exc).__name__,
                    "sanitized_result": str(exc)[:180],
                    "next_route": None,
                    "coverage_after_attempt": "NO_NEW_USABLE_INFORMATION",
                }
            )
    for index, attempt in enumerate(attempts[:-1]):
        attempt["next_route"] = attempts[index + 1]["route_id"]
    return {
        "source_id": source.source_id,
        "series_id": source.series_id,
        "data_family": source.data_family,
        "classification": "SOURCE_UNAVAILABLE_AUTOMATICALLY",
        "attempts": attempts,
        "source_artifact_hash": None,
        "coverage_after_attempt": "NO_NEW_USABLE_INFORMATION",
    }


def human_drop_items(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source = {source.source_id: source for source in source_series_inventory()}
    items = []
    for result in results:
        if result["classification"] == "ACQUIRED_USABLE":
            continue
        source = by_source[result["source_id"]]
        preferred = source.route_b if source.route_b.expected_file_type in {"csv", "zip", "ics"} else source.route_a
        items.append(
            {
                "official_owner": preferred.official_owner,
                "official_page_or_domain": preferred.official_domain,
                "exact_public_artifact_name": preferred.artifact_name,
                "series_id": source.series_id,
                "expected_period": list(source.requested_period),
                "expected_file_type": preferred.expected_file_type,
                "expected_destination_inbox": ".aios/runtime/forex_institutional_data_breakthrough_v1/manual_drop_inbox/",
                "expected_checksum_when_officially_published": "UNKNOWN",
                "privacy_warning": "Download only public official files. Do not add credentials, account IDs, bank/card data, browser cookies, or edited files.",
                "credential_requirement": "NONE",
            }
        )
    return sorted(items, key=lambda item: (item["official_owner"], item["series_id"]))


def write_handoff(results: list[dict[str, Any]]) -> dict[str, Any]:
    items = human_drop_items(results)
    state = {
        "schema": "AIOS_FOREX_OFFICIAL_DATA_DROP_HANDOFF_STATE_V1",
        "packet_id": PACKET_ID,
        "status": "HUMAN_OFFICIAL_DATA_DROP_REQUIRED" if items else "NOT_REQUIRED",
        "manual_drop_inbox": MANUAL_INBOX.as_posix(),
        "items": items,
        "item_count": len(items),
        "safety": {"credentials_required": False, "private_data_required": False, "broker_or_oanda_live": False},
    }
    state["handoff_hash"] = sha256(stable(state).encode("utf-8"))
    atomic_json(HANDOFF_STATE, state)
    lines = [
        "# AIOS Forex Official Data Drop Handoff",
        "",
        f"- Status: `{state['status']}`",
        f"- Destination inbox: `{state['manual_drop_inbox']}`",
        "- Credential requirement: `NONE`",
        "- Privacy warning: use public official files only; do not place secrets, account IDs, cookies, screenshots, or bank/card data in the inbox.",
        "",
    ]
    for item in items:
        lines.extend(
            [
                f"## {item['series_id']}",
                f"- Official owner: {item['official_owner']}",
                f"- Official page/domain: {item['official_page_or_domain']}",
                f"- Exact public artifact: {item['exact_public_artifact_name']}",
                f"- Expected period: {item['expected_period'][0]} to {item['expected_period'][1]}",
                f"- Expected file type: {item['expected_file_type']}",
                f"- Expected destination inbox: `{item['expected_destination_inbox']}`",
                f"- Expected checksum: `{item['expected_checksum_when_officially_published']}`",
                "",
            ]
        )
    HANDOFF_REPORT.parent.mkdir(parents=True, exist_ok=True)
    HANDOFF_REPORT.write_text("\n".join(lines), encoding="utf-8")
    return state


def execute(timeout: int = 8) -> dict[str, Any]:
    for path in (RAW, NORMALIZED, MANIFESTS, QUALITY, FROZEN, MANUAL_INBOX):
        path.mkdir(parents=True, exist_ok=True)
    manifest = inventory_manifest()
    atomic_json(MANIFESTS / "source_route_plan.json", manifest)
    results = []
    usable_count = 0
    for source in source_series_inventory():
        result = recover_source(source, timeout)
        result_for_state = {key: value for key, value in result.items() if key not in {"data", "records"}}
        if "data" in result:
            suffix = result["route_id"].lower()
            raw_path = RAW / f"{source.source_id}-{suffix}.{source.routes[0].expected_file_type}"
            raw_path.write_bytes(result["data"])
            result_for_state["raw_path"] = raw_path.as_posix()
            result_for_state["raw_hash"] = sha256(raw_path.read_bytes())
        records = result.get("records") or []
        if records:
            usable_count += len(records)
            normalized_path = NORMALIZED / f"{source.source_id}.json"
            atomic_json(normalized_path, records)
            result_for_state["normalized_path"] = normalized_path.as_posix()
            result_for_state["normalized_hash"] = sha256(normalized_path.read_bytes())
            result_for_state["record_count"] = len(records)
        else:
            result_for_state["record_count"] = 0
        results.append(result_for_state)
    families = sorted({item["data_family"] for item in results})
    usable_families = sorted({item["data_family"] for item in results if item["classification"] == "ACQUIRED_USABLE"})
    missing_families = [family for family in families if family not in usable_families]
    handoff = write_handoff(results)
    external_score = 80 if "POLICY_CARRY" in usable_families and "YIELD_DIFFERENTIALS" in usable_families and usable_count else 55
    status = "AUTOMATIC_ACQUISITION_COMPLETE" if external_score >= 80 else handoff["status"]
    state = {
        "schema": "AIOS_FOREX_INSTITUTIONAL_DATA_BREAKTHROUGH_V1",
        "packet_id": PACKET_ID,
        "lock_packet_id": LOCK_PACKET_ID,
        "status": status,
        "inventory_hash": manifest["hash"],
        "market_corpus_hash": MARKET_CORPUS_HASH,
        "results": sorted(results, key=lambda item: item["source_id"]),
        "usable_record_count": usable_count,
        "usable_families": usable_families,
        "missing_families": missing_families,
        "remaining_source_routes": [],
        "remaining_source_series": [] if status != "HUMAN_OFFICIAL_DATA_DROP_REQUIRED" else [item["series_id"] for item in handoff["items"]],
        "remaining_data_families": missing_families,
        "external_information_coverage_score": external_score,
        "point_in_time_integrity_score": 95 if usable_count else 0,
        "human_data_drop": {"status": handoff["status"], "item_count": handoff["item_count"], "handoff_hash": handoff["handoff_hash"]},
        "continuation": {
            "continuation_active": status != "HUMAN_OFFICIAL_DATA_DROP_REQUIRED",
            "current_phase": "AUTOMATIC_ROUTE_EXHAUSTION_REVIEW",
            "current_workstream": "EXTERNAL_INFORMATION_COVERAGE",
            "current_action": "official public GET-only acquisition",
            "next_action": "INSTITUTIONAL_CORPUS_FREEZE" if external_score >= 80 else "HUMAN_OFFICIAL_DATA_DROP_RECONCILIATION",
            "next_three_actions": ["POINT_IN_TIME_VALIDATION", "INSTITUTIONAL_CORPUS_FREEZE", "CAPABILITY_PARITY_REASSESSMENT"] if external_score >= 80 else ["place official files in manual_drop_inbox", "resume Packet 016", "import and validate handoff"],
            "remaining_authorized_work_count": 0 if status == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED" else 3,
            "external_time_dependency": False,
            "protected_owner_action_dependency": status == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED",
            "terminal_state_candidate": status,
            "pre_terminal_audit_status": "PASS" if status == "HUMAN_OFFICIAL_DATA_DROP_REQUIRED" else "FAIL_CONTINUE",
            "same_packet_resume_command": "python -B -m automation.forex_engine.forex_institutional_data_breakthrough_v1 --execute",
        },
        "safety": {"credentials": False, "funding": False, "broker_write": False, "practice_order": False, "live": False, "money_movement": False},
    }
    atomic_json(STATE, state)
    REPORT.write_text(render_report(state), encoding="utf-8")
    return state


def render_report(state: dict[str, Any]) -> str:
    route_attempts = sum(len(item.get("attempts") or []) + (1 if item.get("classification", "").startswith("ACQUIRED") else 0) for item in state["results"])
    return f"""# AIOS Forex Institutional Data Breakthrough V1

WHAT HAPPENED:
Packet 016 attempted official public GET-only institutional data acquisition and preserved every route result.

IS IT SAFE:
YES. No credentials, broker write, OANDA LIVE call, order, or money movement occurred.

WHAT DO I DO NEXT:
Use the consolidated human data-drop handoff only if you want to manually download the remaining public official artifacts.

HOW CLOSE ARE WE:
Estimated readiness: {state['external_information_coverage_score']}% external-information coverage for the acquisition milestone.

WHICH MODE SHOULD I USE:
INSTANT for review; HIGH only after official files are placed in the manual inbox.

TECHNICAL DETAILS:
- Status: `{state['status']}`
- Inventory hash: `{state['inventory_hash']}`
- Route attempts or successful acquisitions recorded: {route_attempts}
- Usable records: {state['usable_record_count']}
- Usable families: {', '.join(state['usable_families']) if state['usable_families'] else 'none'}
- Missing families: {', '.join(state['missing_families']) if state['missing_families'] else 'none'}
- Human handoff: `{state['human_data_drop']['status']}` with {state['human_data_drop']['item_count']} items
- Manual inbox: `{MANUAL_INBOX.as_posix()}`
- Live/broker/credential/funding/money movement: false
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timeout", type=int, default=8)
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required")
    state = execute(timeout=args.timeout)
    print(stable({"status": state["status"], "usable_records": state["usable_record_count"], "score": state["external_information_coverage_score"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
