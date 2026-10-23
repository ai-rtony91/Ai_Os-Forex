"""Packet 028 family-specific control-harness audit.

This file intentionally does not mark family controls PASS. Packet 027 did not
provide executable family-specific positive/negative control harnesses, so the
safe result is a repair requirement before any current adapter can support a
final negative family conclusion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-EAST-FOREX-RESEARCH-FIDELITY-EDGE-CLOSURE-028"
ROOT = Path(".aios/runtime/forex_family_falsifiability_controls_v1")
FIDELITY_STATE = Path("Reports/forex_delivery/AIOS_FOREX_PACKET027_FAMILY_FIDELITY_AUDIT_V1_STATE.json")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_FAMILY_FALSIFIABILITY_CONTROLS_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_FAMILY_FALSIFIABILITY_CONTROLS_V1_REPORT.md")


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}


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


def required_control_spec(row: dict[str, Any]) -> dict[str, Any]:
    family = row["family"]
    return {
        "family": family,
        "current_adapter_verdict": row["verdict"],
        "positive_control_status": "NOT_EXECUTED_CURRENT_ADAPTER_HARNESS_MISSING",
        "negative_control_status": "NOT_EXECUTED_CURRENT_ADAPTER_HARNESS_MISSING",
        "repair_required": True,
        "reason": "Packet 027 did not include an executable family-specific positive/negative control harness for this adapter. No PASS is claimed.",
        "fidelity_reason": row["reason"],
    }


def execute() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    fidelity = read_json(FIDELITY_STATE)
    rows = [required_control_spec(row) for row in fidelity.get("rows", [])]
    state = {
        "schema": "AIOS_FOREX_FAMILY_FALSIFIABILITY_CONTROLS_V1_STATE",
        "packet_id": PACKET_ID,
        "status": "RESEARCH_FIDELITY_REPAIR_REQUIRED",
        "family_count": len(rows),
        "positive_controls_passed": 0,
        "negative_controls_passed": 0,
        "repair_required_families": [row["family"] for row in rows],
        "rows": rows,
    }
    state["state_hash"] = sha256_text(stable(state))
    atomic_json(STATE, state)
    atomic_json(ROOT / "controls_state.json", state)
    REPORT.write_text(
        f"# AIOS Forex Family Falsifiability Controls V1\n\nStatus: `{state['status']}`\n\nNo current family adapter controls were marked PASS.\n",
        encoding="utf-8",
    )
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required")
    state = execute()
    print(stable({"status": state["status"], "repair_required_families": state["repair_required_families"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
