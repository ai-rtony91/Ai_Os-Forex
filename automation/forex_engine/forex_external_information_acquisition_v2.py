"""Packet 015 bounded multi-route official information acquisition."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from automation.forex_engine import forex_mechanism_information_corpus_v1 as prior

ROOT = Path(".aios/runtime/forex_external_information_acquisition_v2")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_ACQUISITION_V2_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_ACQUISITION_V2_REPORT.md")
PACKET = "PKT-EAST-FOREX-FULL-SPECTRUM-FUNDING-015"
LOCK = "AIOS-LOCK-8505e053699e4e73b8f484781efd3463"


def inventory():
    sources = []
    for series, (currency, delay) in prior.SERIES.items():
        sources.append({
            "source_id": f"FRED_{series}", "family": "POLICY_CARRY" if series not in {"VIXCLS", "DGS2", "DGS10"} else "RISK_VOLATILITY",
            "currency": currency, "delay_days": delay, "routes": [
                f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={prior.START}&coed={prior.END}",
                f"https://fred.stlouisfed.org/series/{series}/downloaddata/{series}.csv",
                f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}",
            ], "point_in_time_rule": "conservative publication delay", "new_credential_required": False,
        })
    sources += [
        {"source_id": "OFFICIAL_MACRO_SCHEDULE_ARCHIVE", "family": "MACRO_EVENT_TIMING", "routes": [], "classification": "UNTESTABLE_WITH_CURRENT_LAWFUL_PUBLIC_DATA", "reason": "No reproducible credential-free point-in-time historical schedule archive established"},
        {"source_id": "OFFICIAL_FIRST_RELEASE_VINTAGES", "family": "MACRO_FIRST_RELEASE", "routes": [], "classification": "UNTESTABLE_WITH_CURRENT_LAWFUL_PUBLIC_DATA", "reason": "No bounded multi-country first-release vintage archive established"},
    ]
    value = {"schema": "AIOS_FOREX_EXTERNAL_SOURCE_ROUTE_INVENTORY_V2", "sources": sources}
    value["hash"] = prior.sha(prior.stable(value).encode())
    return value


def recover(source):
    attempts = []
    if not source["routes"]:
        return {"source_id": source["source_id"], "family": source["family"], "classification": source["classification"], "attempts": [], "reason": source["reason"]}
    for position, url in enumerate(source["routes"], 1):
        attempted = datetime.now(timezone.utc).isoformat()
        try:
            data = prior.fetch(url, timeout=20)
            series = source["source_id"][5:]
            records = prior.normalize(series, data, source["currency"], source["delay_days"])
            if not records:
                raise ValueError("NO_NORMALIZED_RECORDS")
            return {"source_id": source["source_id"], "family": source["family"], "classification": "ACQUIRED", "route": position, "url": url, "attempts": attempts, "data": data, "records": records}
        except Exception as exc:
            attempts.append({"route": position, "attempt_utc": attempted, "error_class": type(exc).__name__, "sanitized_error": str(exc)[:120], "next_route": position + 1 if position < len(source["routes"]) else None})
    return {"source_id": source["source_id"], "family": source["family"], "classification": "SOURCE_UNAVAILABLE", "attempts": attempts}


def execute():
    plan = inventory()
    ROOT.mkdir(parents=True, exist_ok=True)
    prior.atomic_json(ROOT / "source_route_inventory.json", plan)
    results = []
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="packet015-get") as pool:
        futures = [pool.submit(recover, source) for source in plan["sources"]]
        for future in as_completed(futures):
            results.append(future.result())
    successes = []
    for result in results:
        if result["classification"] != "ACQUIRED":
            continue
        raw = ROOT / "raw" / f"{result['source_id']}.csv"
        normalized = ROOT / "normalized" / f"{result['source_id']}.json"
        raw.parent.mkdir(parents=True, exist_ok=True)
        normalized.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(result.pop("data"))
        prior.atomic_json(normalized, result.pop("records"))
        result.update({"raw_path": raw.as_posix(), "normalized_path": normalized.as_posix(), "raw_hash": prior.sha(raw.read_bytes()), "normalized_hash": prior.sha(normalized.read_bytes()), "point_in_time_valid": True})
        successes.append(result)
    results.sort(key=lambda item: item["source_id"])
    state = {"schema": "AIOS_FOREX_EXTERNAL_INFORMATION_ACQUISITION_V2", "packet_id": PACKET, "lock_id": LOCK, "inventory_hash": plan["hash"], "results": results, "successes": successes, "remaining_source_routes": [], "remaining_data_families": [], "status": "ACQUISITION_COMPLETE", "safety": {"credentials": False, "broker_write": False, "live": False}}
    prior.atomic_json(STATE, state)
    REPORT.write_text(f"# AIOS Forex External Information Acquisition V2\n\n- Status: `ACQUISITION_COMPLETE`\n- Sources: {len(results)}\n- Newly acquired: {len(successes)}\n- Unavailable or untestable: {len(results)-len(successes)}\n- Inventory hash: `{plan['hash']}`\n- GET-only: true\n", encoding="utf-8")
    return state


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true"); args = parser.parse_args()
    if not args.execute: parser.error("--execute required")
    state = execute(); print(prior.stable({"status": state["status"], "successes": len(state["successes"])})); return 0


if __name__ == "__main__": raise SystemExit(main())
