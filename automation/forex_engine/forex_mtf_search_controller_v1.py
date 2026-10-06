"""Packet 032 end-to-end local research controller.

Runs only the authorized research phases up to the point earned by evidence.
It preserves Packet 031 and never opens broker/PAPER/LIVE/downstream gates
without the required research proof.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any
import argparse

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine.forex_mtf_finalist_program_v1 import run_finalist_program
from automation.forex_engine.forex_mtf_gross_edge_surface_v1 import run_surface
from automation.forex_engine.forex_mtf_indicator_coverage_v1 import run as run_coverage
from automation.forex_engine.forex_supertrend_macd_adx_v1 import fidelity_state


PACKET_ID = "PKT-EAST-FOREX-MTF-GROSS-EDGE-DISCOVERY-032"
SCHEMA = "AIOS_FOREX_MTF_SEARCH_CONTROLLER.v1"
INDICATOR_STATE = Path("Reports/forex_delivery/AIOS_FOREX_SUPERTREND_MACD_ADX_FIDELITY_V1_STATE.json")
INDICATOR_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_SUPERTREND_MACD_ADX_FIDELITY_V1_REPORT.md")
STATE = Path("Reports/forex_delivery/AIOS_FOREX_MTF_SEARCH_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_MTF_SEARCH_V1_REPORT.md")
ATTACK_STATE = Path("Reports/forex_delivery/AIOS_FOREX_ATTACK_TO_FINISH_V10_STATE.json")
ATTACK_REPORT = Path("Reports/forex_delivery/AIOS_FOREX_ATTACK_TO_FINISH_V10_REPORT.md")
PACKET031_STATE = Path("Reports/forex_delivery/AIOS_FOREX_EDGE_EXISTENCE_CONTROLLER_V1_STATE.json")


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


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


def write_indicator_outputs() -> dict[str, Any]:
    state = fidelity_state()
    atomic_json(INDICATOR_STATE, state)
    lines = [
        "# AIOS Forex Supertrend MACD ADX Fidelity V1",
        "",
        f"- Packet: {PACKET_ID}",
        f"- Status: {state['status']}",
        f"- Indicator code hash: {state['indicator_code_hash']}",
        "- Completed-candle calculations only: YES",
        "- Broker/API/live work: NO",
        "",
        "## Implemented indicators",
        "",
        "- SUPERTREND: Wilder ATR, carried bands, causal trend transitions.",
        "- MACD: deterministic EMA fast/slow line, signal line, histogram.",
        "- ADX: true range, +/-DM, smoothed +/-DI, DX, ADX.",
    ]
    INDICATOR_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return state


def attack_to_finish(controller_state: dict[str, Any]) -> dict[str, Any]:
    status = controller_state["status"]
    closed = {
        "P0-001": "TIMEFRAME_DATA_COVERAGE_AUDITED",
        "P0-002": "INDICATOR_FIDELITY_IMPLEMENTED",
        "P0-003": "PARAMETER_FAMILIES_FROZEN",
        "P0-004": "GROSS_EDGE_SURFACE_COMPLETE",
        "P0-005": "HYPOTHESIS_LEDGER_COMPLETE",
    }
    if status in {"NO_INDICATOR_GROSS_EDGE", "SEARCH_FAMILY_EXHAUSTED_NO_ROBUST_EDGE"}:
        highest = {
            "blocker_id": "P0-006",
            "priority": "P0",
            "phase": "GROSS_EDGE_GATE",
            "status": "TERMINAL_UNRESOLVABLE",
            "exact_blocker": "No robust bidirectional gross-edge survivor earned cost/exit/Validation/PAPER continuation.",
            "next_action": "Preserve evidence; do not open downstream gates without a materially new authorized hypothesis.",
            "can_codex_resolve": False,
            "human_action_required": False,
            "external_time_required": False,
        }
        remaining = 0
        terminal = status
    else:
        highest = {
            "blocker_id": "P0-007",
            "priority": "P0",
            "phase": "FULL_SEARCH_MULTIPLE_TESTING",
            "status": "OPEN",
            "exact_blocker": "Gross survivor requires full search-family null campaigns before finalist Validation.",
            "next_action": "Run full search-family null campaigns under a follow-on authorized compute block.",
            "can_codex_resolve": True,
            "human_action_required": False,
            "external_time_required": False,
        }
        remaining = 1
        terminal = "VALIDATION_BLOCKED"
    state = {
        "schema": "AIOS_FOREX_ATTACK_TO_FINISH.v10",
        "packet_id": PACKET_ID,
        "status": terminal,
        "closed_blockers": closed,
        "highest_priority_blocker": highest,
        "remaining_authorized_work_count": remaining,
        "pre_terminal_audit_status": "PASS" if remaining == 0 else "FAIL_CONTINUE",
        "same_packet_resume_command": "Re-run Packet 032-PRO from C:\\Dev\\Ai.Os after new authorized evidence or compute gate.",
    }
    atomic_json(ATTACK_STATE, state)
    ATTACK_REPORT.write_text(
        "\n".join(
            [
                "# AIOS Forex Attack To Finish V10",
                "",
                f"- Packet: {PACKET_ID}",
                f"- Status: {state['status']}",
                f"- Remaining authorized work count: {remaining}",
                f"- Highest blocker: {highest['blocker_id']} {highest['status']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return state


def run_controller() -> dict[str, Any]:
    packet031 = read_json(PACKET031_STATE)
    coverage = run_coverage()
    indicator = write_indicator_outputs()
    surface = run_surface()
    finalist = run_finalist_program()
    if surface["status"] == "NO_INDICATOR_GROSS_EDGE":
        status = "NO_INDICATOR_GROSS_EDGE"
    elif surface["status"] == "SEARCH_FAMILY_EXHAUSTED_NO_ROBUST_EDGE":
        status = "SEARCH_FAMILY_EXHAUSTED_NO_ROBUST_EDGE"
    elif finalist["status"] == "VALIDATION_BLOCKED_SEARCH_NULL_REQUIRED":
        status = "VALIDATION_BLOCKED"
    else:
        status = surface["status"]
    state = {
        "schema": SCHEMA,
        "packet_id": PACKET_ID,
        "status": status,
        "packet031_preserved": packet031.get("status") == "NO_CAUSAL_EDGE_BRANCH_JUSTIFIED",
        "packet031_state_hash": sha256_text(stable(packet031)) if packet031 else None,
        "coverage_status": coverage["status"],
        "indicator_status": indicator["status"],
        "surface_status": surface["status"],
        "hypotheses_tested": surface["hypotheses_tested"],
        "gross_screen_survivors": surface["gross_screen_survivors"],
        "finalist_status": finalist["status"],
        "bootstrap_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "forward_opened": False,
        "v12_opened": False,
        "paper_opened": False,
        "live_opened": False,
        "funding_opened": False,
        "compounding_opened": False,
        "state_hash": "",
    }
    state["state_hash"] = sha256_text(stable({k: v for k, v in state.items() if k != "state_hash"}))
    atomic_json(STATE, state)
    attack = attack_to_finish(state)
    write_report(state, attack)
    return state


def finalize_existing() -> dict[str, Any]:
    """Finalize controller state from already-generated Packet 032 phase states.

    This is a controller-owned resume path, not an external state fabrication
    shortcut.  It fails closed if any required phase state is absent.
    """
    required = [
        Path("Reports/forex_delivery/AIOS_FOREX_MTF_TIMEFRAME_COVERAGE_V1_STATE.json"),
        INDICATOR_STATE,
        Path("Reports/forex_delivery/AIOS_FOREX_MTF_GROSS_EDGE_SURFACE_V1_STATE.json"),
        Path("Reports/forex_delivery/AIOS_FOREX_MTF_FINALIST_PROGRAM_V1_STATE.json"),
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"Cannot finalize Packet 032; missing required phase state(s): {missing}")
    coverage = read_json(required[0])
    indicator = read_json(INDICATOR_STATE)
    surface = read_json(required[2])
    finalist = read_json(required[3])
    packet031 = read_json(PACKET031_STATE)
    if surface.get("status") == "NO_INDICATOR_GROSS_EDGE":
        status = "NO_INDICATOR_GROSS_EDGE"
    elif surface.get("status") == "SEARCH_FAMILY_EXHAUSTED_NO_ROBUST_EDGE":
        status = "SEARCH_FAMILY_EXHAUSTED_NO_ROBUST_EDGE"
    elif finalist.get("status") == "VALIDATION_BLOCKED_SEARCH_NULL_REQUIRED":
        status = "VALIDATION_BLOCKED"
    else:
        status = str(surface.get("status", "VALIDATION_BLOCKED"))
    state = {
        "schema": SCHEMA,
        "packet_id": PACKET_ID,
        "status": status,
        "packet031_preserved": packet031.get("status") == "NO_CAUSAL_EDGE_BRANCH_JUSTIFIED",
        "packet031_state_hash": sha256_text(stable(packet031)) if packet031 else None,
        "coverage_status": coverage.get("status"),
        "indicator_status": indicator.get("status"),
        "surface_status": surface.get("status"),
        "hypotheses_tested": surface.get("hypotheses_tested"),
        "gross_screen_survivors": surface.get("gross_screen_survivors"),
        "finalist_status": finalist.get("status"),
        "bootstrap_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "forward_opened": False,
        "v12_opened": False,
        "paper_opened": False,
        "live_opened": False,
        "funding_opened": False,
        "compounding_opened": False,
        "state_hash": "",
    }
    state["state_hash"] = sha256_text(stable({k: v for k, v in state.items() if k != "state_hash"}))
    atomic_json(STATE, state)
    attack = attack_to_finish(state)
    write_report(state, attack)
    return state


def write_report(state: dict[str, Any], attack: dict[str, Any]) -> None:
    lines = [
        "# AIOS Forex MTF Search V1",
        "",
        f"- Packet: {PACKET_ID}",
        f"- Status: {state['status']}",
        f"- Packet 031 preserved: {state['packet031_preserved']}",
        f"- Hypotheses tested: {state['hypotheses_tested']}",
        f"- Gross screen survivors: {state['gross_screen_survivors']}",
        "- Validation/Holdout/Forward/V12/PAPER/LIVE/funding/compounding opened: NO",
        "",
        "## Gate result",
        "",
        f"- Coverage: {state['coverage_status']}",
        f"- Indicator fidelity: {state['indicator_status']}",
        f"- Surface: {state['surface_status']}",
        f"- Finalist program: {state['finalist_status']}",
        f"- Highest blocker: {attack['highest_priority_blocker']['exact_blocker']}",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize-existing", action="store_true")
    args = parser.parse_args()
    result = finalize_existing() if args.finalize_existing else run_controller()
    print(json.dumps(result, indent=2, sort_keys=True))
