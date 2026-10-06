"""Packet 031 Packet 030 receipt audit wrapper."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_edge_existence_controller_v1 as controller


def execute() -> dict:
    state = controller.packet030_receipt_audit()
    controller.atomic_json(controller.RECEIPT_STATE, state)
    controller.write_report(controller.RECEIPT_REPORT, "AIOS Forex Packet 030 Receipt Audit V1", state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    print(controller.stable({"status": execute()["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
