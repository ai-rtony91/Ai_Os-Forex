"""Packet 031 M5 predictive information surface wrapper."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine import forex_edge_existence_controller_v1 as controller


def execute() -> dict:
    state = controller.predictive_information_surface()
    controller.atomic_json(controller.INFO_STATE, state)
    controller.write_report(controller.INFO_REPORT, "AIOS Forex M5 Predictive Information Surface V1", state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    print(controller.stable({"status": execute()["status"], "branch_supported": execute()["branch_supported"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
