"""Packet 031 frozen event ledger wrapper."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_edge_existence_controller_v1 as controller


def execute() -> dict:
    state = controller.build_event_ledger()
    controller.atomic_json(controller.LEDGER_STATE, state)
    controller.write_report(controller.LEDGER_REPORT, "AIOS Forex Frozen Event Ledger V1", state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute()
    print(controller.stable({"status": state["status"], "accepted_entry_count": state["accepted_entry_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
