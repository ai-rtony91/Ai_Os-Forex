"""Conditional Packet 015 external information corpus freezer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from automation.forex_engine import forex_mechanism_information_corpus_v1 as support

ACQUISITION = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_ACQUISITION_V2_STATE.json")
ROOT = Path(".aios/runtime/forex_external_information_corpus_v2")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V2_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V2_REPORT.md")


def build(acquisition):
    successes = acquisition["successes"]
    if not successes:
        return {"schema": "AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V2_STATE", "corpus_id": "AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V2", "status": "NOT_CREATED_NO_NEW_USABLE_INFORMATION", "records": 0, "aggregate_hash": None, "frozen": False, "provenance": "Packet 013 CFTC remains read-only prior evidence", "gaps": len(acquisition["results"])}
    manifest = {"schema": "AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V2", "corpus_id": "AIOS_FOREX_EXTERNAL_INFORMATION_CORPUS_V2", "period": [support.START, support.END], "artifacts": successes, "records": sum(item.get("records", 0) for item in successes), "provenance": "official HTTPS GET-only", "gaps": len(acquisition["results"]) - len(successes)}
    manifest["aggregate_hash"] = support.sha(support.stable(manifest).encode())
    manifest.update({"status": "FROZEN_VALID", "frozen": True})
    return manifest


def execute():
    acquisition = json.loads(ACQUISITION.read_text(encoding="utf-8"))
    state = build(acquisition)
    if state["frozen"]:
        support.atomic_json(ROOT / "manifests/manifest.json", state)
        support.atomic_json(ROOT / "frozen/FROZEN.json", {"corpus_id": state["corpus_id"], "aggregate_hash": state["aggregate_hash"], "status": state["status"]})
    support.atomic_json(STATE, state)
    REPORT.write_text(f"# AIOS Forex External Information Corpus V2\n\n- Status: `{state['status']}`\n- Records: {state['records']}\n- Frozen: {str(state['frozen']).lower()}\n- Hash: `{state['aggregate_hash']}`\n", encoding="utf-8")
    return state


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--execute",action="store_true");args=parser.parse_args()
    if not args.execute:parser.error("--execute required")
    state=execute();print(support.stable({"status":state["status"],"records":state["records"]}));return 0


if __name__ == "__main__":raise SystemExit(main())
