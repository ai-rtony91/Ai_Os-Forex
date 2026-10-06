"""Packet 014 mechanism information corpus.

This module performs bounded, official HTTPS GET-only recovery and freezes a
new manifest.  It never contacts a broker and never handles credentials.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(".aios/runtime/forex_mechanism_information_corpus_v1")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_MECHANISM_INFORMATION_CORPUS_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_MECHANISM_INFORMATION_CORPUS_V1_REPORT.md")
PACKET = "PKT-EAST-FOREX-EARNED-FUNDING-READINESS-014"
LOCK = "AIOS-LOCK-6af0248af6484987a503d6c6026f211e"
MARKET_HASH = "44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a"
P13_INFO_HASH = "57da729226ebd675d7c79f182510f0612fc2f93cd0f20a05abed64243163d854"
START, END = "2024-01-01", "2026-08-29"

SERIES = {
    "DFF": ("USD", 1), "ECBDFR": ("EUR", 1), "IUDERB": ("GBP", 1),
    "IRSTCI01JPM156N": ("JPY", 32), "IRSTCI01CHM156N": ("CHF", 32),
    "IRSTCI01CAM156N": ("CAD", 32), "IRSTCI01AUM156N": ("AUD", 32),
    "IRSTCI01NZM156N": ("NZD", 32), "VIXCLS": ("GLOBAL", 1),
    "DGS2": ("USD", 1), "DGS10": ("USD", 1),
}


def stable(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


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


def routes():
    output = []
    for series, (currency, delay) in SERIES.items():
        output.append({
            "source_id": f"FRED_{series}", "currency": currency, "delay_days": delay,
            "routes": [
                f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={START}&coed={END}",
                f"https://fred.stlouisfed.org/series/{series}/downloaddata/{series}.csv",
            ],
            "official_domain": "fred.stlouisfed.org", "method": "HTTPS_GET_ONLY",
            "point_in_time_rule": "observation plus conservative publication delay",
        })
    frozen = {"schema": "AIOS_FOREX_MECHANISM_SOURCE_RECOVERY_V1", "sources": output}
    frozen["hash"] = sha(stable(output).encode())
    return frozen


def fetch(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": "AIOS-Packet014-GET-only/1.0"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP_{response.status}")
        return response.read()


def normalize(series, data, currency, delay):
    records = []
    for row in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
        date_text = row.get("DATE") or row.get("observation_date")
        value_text = row.get(series) or row.get("VALUE")
        if not date_text or value_text in (None, "", "."):
            continue
        observed = datetime.fromisoformat(date_text).replace(tzinfo=timezone.utc)
        available = observed + timedelta(days=delay)
        records.append({
            "source_id": f"FRED_{series}", "currency": currency,
            "observation_time": observed.isoformat(), "publication_time": available.isoformat(),
            "strategy_available_time": available.isoformat(),
            "vintage_id_or_revision_status": "CONSERVATIVE_DELAY_CURRENT_OFFICIAL_HISTORY",
            "value": float(value_text), "retrieval_hash": sha(data),
        })
    return records


def recover_source(source):
    attempts = []
    for position, url in enumerate(source["routes"], 1):
        try:
            data = fetch(url)
            records = normalize(source["source_id"][5:], data, source["currency"], source["delay_days"])
            if not records:
                raise ValueError("NO_NORMALIZED_RECORDS")
            return {"source": source, "route": position, "url": url, "data": data, "records": records, "attempts": attempts}
        except Exception as exc:
            attempts.append({"route": position, "error_class": type(exc).__name__, "sanitized_error": str(exc)[:120]})
    return {"source": source, "attempts": attempts, "unavailable": True}


def execute():
    for name in ("raw", "normalized", "manifests", "quality", "frozen"):
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    plan = routes()
    atomic_json(ROOT / "manifests/source_recovery_plan.json", plan)
    successes, failures = [], []
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="packet014-get") as executor:
        futures = {executor.submit(recover_source, source): source for source in plan["sources"]}
        for future in as_completed(futures):
            result = future.result()
            source = result["source"]
            if result.get("unavailable"):
                failures.append({"source_id": source["source_id"], "attempts": result["attempts"], "classification": "SOURCE_UNAVAILABLE"})
                continue
            series = source["source_id"][5:]
            raw_path = ROOT / "raw" / f"{series}.csv"
            normalized_path = ROOT / "normalized" / f"{series}.json"
            raw_path.write_bytes(result["data"])
            atomic_json(normalized_path, result["records"])
            successes.append({
                "source_id": source["source_id"], "currency": source["currency"],
                "route": result["route"], "records": len(result["records"]),
                "raw_hash": sha(raw_path.read_bytes()), "normalized_hash": sha(normalized_path.read_bytes()),
                "raw_path": raw_path.as_posix(), "normalized_path": normalized_path.as_posix(),
                "point_in_time_valid": True,
            })
    successes.sort(key=lambda item: item["source_id"])
    failures.sort(key=lambda item: item["source_id"])
    inherited = {
        "source_id": "PACKET013_CFTC_2024_2026", "records": 9808,
        "aggregate_hash": P13_INFO_HASH, "mode": "READ_ONLY_REFERENCE",
        "point_in_time_rule": "Tuesday observation available Friday 21:30 UTC",
    }
    manifest = {
        "schema": "AIOS_FOREX_MECHANISM_INFORMATION_CORPUS_V1", "packet_id": PACKET,
        "corpus_id": "AIOS_FOREX_MECHANISM_INFORMATION_CORPUS_V1", "period": [START, END],
        "market_corpus_hash": MARKET_HASH, "packet013_information_hash": P13_INFO_HASH,
        "source_recovery_plan_hash": plan["hash"], "successes": successes, "failures": failures,
        "inherited_point_in_time_sources": [inherited],
    }
    manifest["aggregate_hash"] = sha(stable({"successes": successes, "failures": failures, "inherited": inherited}).encode())
    atomic_json(ROOT / "manifests/manifest.json", manifest)
    frozen = {"corpus_id": manifest["corpus_id"], "aggregate_hash": manifest["aggregate_hash"], "status": "FROZEN_VALID", "manifest_hash": sha((ROOT / "manifests/manifest.json").read_bytes())}
    atomic_json(ROOT / "frozen/FROZEN.json", frozen)
    state = {**manifest, "freeze": frozen, "lock_id": LOCK, "current_phase": "MECHANISM_CORPUS_FREEZE", "next_action": "HYPOTHESIS_PROTOCOL_FREEZE", "safety": {"credentials": False, "broker_write": False, "live": False, "money_movement": False}}
    atomic_json(STATE, state)
    REPORT.write_text(
        "# AIOS Forex Mechanism Information Corpus V1\n\n"
        f"- Status: `{frozen['status']}`\n- Official sources recovered: {len(successes)}\n"
        f"- Sources unavailable after distinct routes: {len(failures)}\n- Packet 013 CFTC records referenced: 9,808\n"
        f"- Aggregate hash: `{manifest['aggregate_hash']}`\n- Broker/LIVE: false\n", encoding="utf-8")
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute required")
    result = execute()
    print(stable({"status": result["freeze"]["status"], "successes": len(result["successes"]), "failures": len(result["failures"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
