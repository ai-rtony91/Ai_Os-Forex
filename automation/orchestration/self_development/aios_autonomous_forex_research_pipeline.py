"""Simulation-only autonomous Forex research pipeline for AIOS.

This pipeline is local, deterministic, and synthetic-fixture only. It never
connects to brokers, OANDA, live market data, webhooks, orders, secrets, .env,
or live Trading Lab execution paths.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from typing import Any

from automation.orchestration.self_development.aios_autonomy_run_ledger import (
    LedgerPathError,
    build_in_memory_ledger_reference,
    build_ledger_record,
    write_ledger_record,
)


SCHEMA = "AIOS_AUTONOMOUS_FOREX_RESEARCH_RUN_RESULT.v1"
APPROVAL = "APPROVED_LOCAL_FOREX_RESEARCH_ONLY"

MODES = {"DRY_RUN", "APPLY"}
RESEARCH_MODES = {
    "PLAN_ONLY",
    "BACKTEST_STUB",
    "REPLAY_STUB",
    "SOAK_STUB",
    "FULL_LOCAL_RESEARCH_STUB",
}
PAIRS = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD_SIM_ONLY"}
TIMEFRAMES = {"M1", "M5", "M15", "H1", "H4", "D1"}
PROTECTED_TEXT_TOKENS = {
    ".env",
    "secret",
    "secrets",
    "broker",
    "oanda",
    "live_trading",
    "forex_live",
    "trading_lab_live",
    "webhook",
    "order",
    "orders",
    "real_money",
    "live_data",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _normalized(value: Any) -> str:
    return _safe_str(value).upper().replace("-", "_").replace(" ", "_") or "UNKNOWN"


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = _safe_str(value).lower()
    if not text:
        return default
    return text in {"true", "1", "yes", "y", "on", "approved", "present"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = _safe_str(item)
        if key and key not in seen:
            result.append(key)
            seen.add(key)
    return result


def _protected_text_hits(values: list[Any]) -> list[str]:
    text = " ".join(_safe_str(value).lower() for value in values)
    return sorted(token for token in PROTECTED_TEXT_TOKENS if token in text)


def _safety(*, status: str, writes_ledger: bool = False, boundary_hits: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "writes_files": bool(writes_ledger),
        "writes_only_approved_run_ledger": bool(writes_ledger),
        "uses_synthetic_fixture_only": True,
        "uses_live_market_data": False,
        "uses_network": False,
        "starts_runtime": False,
        "launches_workers": False,
        "enables_scheduler": False,
        "starts_daemon": False,
        "mutates_queue": False,
        "mutates_locks": False,
        "mutates_approval": False,
        "mutates_registry": False,
        "writes_reports": False,
        "writes_telemetry": False,
        "writes_relay": False,
        "touches_secrets_or_env": False,
        "broker_or_live_trading": False,
        "protected_actions_blocked": True,
        "human_owner_required_before_live_trading": True,
        "valid_for_live_trading": False,
        "protected_boundary_hits": boundary_hits or [],
    }


def _repo_state(payload: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(payload.get("repo_state")) or {
        "branch": _safe_str(payload.get("branch")),
        "expected_branch": _safe_str(payload.get("expected_branch")),
        "dirty": False,
    }


def _research_plan(pair: str, timeframe: str, strategy_profile: str, backtest_window: str) -> dict[str, Any]:
    return {
        "plan_id": f"{pair}_{timeframe}_{strategy_profile}_SYNTHETIC_PLAN",
        "pair": pair,
        "timeframe": timeframe,
        "strategy_profile": strategy_profile,
        "backtest_window": backtest_window,
        "steps": [
            "Validate simulation-only constraints.",
            "Run deterministic synthetic backtest stub.",
            "Run deterministic synthetic replay stub.",
            "Run bounded synthetic soak cycles.",
            "Keep valid_for_live_trading false until a separately approved live-readiness packet exists.",
        ],
        "live_trading_blocked": True,
    }


def _synthetic_r_values(pair: str, timeframe: str) -> list[float]:
    seed = (sum(ord(char) for char in f"{pair}:{timeframe}") % 5) / 10
    base = [0.8, -0.35, 0.45, 0.25, -0.2, 0.6, -0.4, 0.3, 0.15, -0.1]
    return [round(value + (seed if index % 3 == 0 else 0), 3) for index, value in enumerate(base)]


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return round(abs(max_drawdown), 4)


def _backtest(pair: str, timeframe: str, strategy_profile: str) -> dict[str, Any]:
    values = _synthetic_r_values(pair, timeframe)
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value <= 0]
    trade_count = len(values)
    return {
        "trade_count": trade_count,
        "win_rate": round(len(wins) / trade_count, 4),
        "loss_rate": round(len(losses) / trade_count, 4),
        "gross_return_sim": round(sum(values), 4),
        "max_drawdown_sim": _max_drawdown(values),
        "average_r_multiple_sim": round(sum(values) / trade_count, 4),
        "notes": f"Synthetic deterministic backtest stub for {pair} {timeframe} {strategy_profile}.",
        "valid_for_live_trading": False,
    }


def _replay(pair: str, timeframe: str, strategy_profile: str) -> dict[str, Any]:
    values = _synthetic_r_values(pair, timeframe)
    return {
        "events_replayed": len(values) * 3,
        "decision_points": len(values),
        "mismatches": 0,
        "replay_status": "PASS",
        "notes": f"Synthetic deterministic replay stub for {pair} {timeframe} {strategy_profile}.",
        "valid_for_live_trading": False,
    }


def _soak(pair: str, timeframe: str, cycles: int) -> dict[str, Any]:
    cycles_requested = max(1, min(cycles, 20))
    passed = cycles_requested
    return {
        "cycles_requested": cycles,
        "cycles_completed": cycles_requested,
        "passed_cycles": passed,
        "failed_cycles": 0,
        "stability_status": "PASS",
        "stop_reason": "COMPLETED_SYNTHETIC_SOAK",
        "notes": f"Synthetic bounded soak for {pair} {timeframe}; cycles capped at 20.",
        "valid_for_live_trading": False,
    }


def _empty_backtest(reason: str = "") -> dict[str, Any]:
    return {
        "trade_count": 0,
        "win_rate": 0.0,
        "loss_rate": 0.0,
        "gross_return_sim": 0.0,
        "max_drawdown_sim": 0.0,
        "average_r_multiple_sim": 0.0,
        "notes": reason,
        "valid_for_live_trading": False,
    }


def _empty_replay(reason: str = "") -> dict[str, Any]:
    return {
        "events_replayed": 0,
        "decision_points": 0,
        "mismatches": 0,
        "replay_status": "NOT_RUN",
        "notes": reason,
        "valid_for_live_trading": False,
    }


def _empty_soak(reason: str = "") -> dict[str, Any]:
    return {
        "cycles_requested": 0,
        "cycles_completed": 0,
        "passed_cycles": 0,
        "failed_cycles": 0,
        "stability_status": "NOT_RUN",
        "stop_reason": reason,
        "valid_for_live_trading": False,
    }


def _write_or_reference_ledger(payload: dict[str, Any], record: dict[str, Any], write_ledger: bool) -> dict[str, Any]:
    if not write_ledger:
        return build_in_memory_ledger_reference(
            run_id=record["run_id"],
            mode=record["mode"],
            task_type=record["task_type"],
            status=record["status"],
            generated_utc=record["generated_utc"],
            stop_reason=record["stop_reason"],
            next_safe_action=record["next_safe_action"],
            result_summary=record["result_summary"],
        )
    return write_ledger_record(
        payload.get("output_root"),
        record,
        repo_root=payload.get("repo_root"),
    )


def build_autonomous_forex_research_run_result(payload: dict[str, Any]) -> dict[str, Any]:
    generated_utc = _safe_str(payload.get("generated_utc") or _now())
    mode = _normalized(payload.get("mode") or "DRY_RUN")
    research_mode = _normalized(payload.get("research_mode") or "PLAN_ONLY")
    pair = _normalized(payload.get("pair") or "EURUSD")
    timeframe = _normalized(payload.get("timeframe") or "M5")
    strategy_profile = _normalized(payload.get("strategy_profile") or "BASELINE_CONFLUENCE")
    backtest_window = _normalized(payload.get("backtest_window") or "SYNTHETIC_30D")
    soak_cycles = _int_value(payload.get("soak_cycles"), 3)
    max_runtime_minutes = _int_value(payload.get("max_runtime_minutes"), 30)
    approval = _safe_str(payload.get("human_owner_research_approval"))
    stop_conditions: list[str] = []
    missing: list[str] = []

    boundary_hits = _protected_text_hits([research_mode, pair, timeframe, strategy_profile, backtest_window, payload.get("research_plan")])
    if mode not in MODES:
        stop_conditions.append("INVALID_MODE")
    if research_mode not in RESEARCH_MODES:
        stop_conditions.append("INVALID_RESEARCH_MODE")
    if pair not in PAIRS:
        stop_conditions.append("INVALID_PAIR")
    if timeframe not in TIMEFRAMES:
        stop_conditions.append("INVALID_TIMEFRAME")
    if max_runtime_minutes < 1 or max_runtime_minutes > 240:
        stop_conditions.append("MAX_RUNTIME_OUT_OF_RANGE")
    if soak_cycles < 1 or soak_cycles > 20:
        stop_conditions.append("SOAK_CYCLES_OUT_OF_RANGE")
    if boundary_hits:
        stop_conditions.append("PROTECTED_LIVE_OR_SECRET_BOUNDARY")
    if mode == "APPLY" and approval != APPROVAL:
        missing.append("human_owner_research_approval")
        stop_conditions.append("HUMAN_OWNER_RESEARCH_APPROVAL_MISSING")

    blocked = bool(stop_conditions)
    safety_status = "BLOCKED" if blocked else "PASS"
    next_safe_action = "Continue simulation-only Forex research with synthetic fixtures."
    if "HUMAN_OWNER_RESEARCH_APPROVAL_MISSING" in stop_conditions:
        next_safe_action = "Obtain APPROVED_LOCAL_FOREX_RESEARCH_ONLY before APPLY simulation research."
    elif "PROTECTED_LIVE_OR_SECRET_BOUNDARY" in stop_conditions:
        next_safe_action = "Stop and wake Human Owner; remove broker/live/OANDA/webhook/order/secrets boundary."
    elif blocked:
        next_safe_action = "Correct research mode, pair, timeframe, soak, or runtime inputs before continuing."

    plan = _research_plan(pair, timeframe, strategy_profile, backtest_window) if not blocked or research_mode == "PLAN_ONLY" else {}
    backtest = _empty_backtest("Not run for this research mode.")
    replay = _empty_replay("Not run for this research mode.")
    soak = _empty_soak("Not run for this research mode.")

    if not blocked:
        if research_mode in {"BACKTEST_STUB", "FULL_LOCAL_RESEARCH_STUB"}:
            backtest = _backtest(pair, timeframe, strategy_profile)
        if research_mode in {"REPLAY_STUB", "FULL_LOCAL_RESEARCH_STUB"}:
            replay = _replay(pair, timeframe, strategy_profile)
        if research_mode in {"SOAK_STUB", "FULL_LOCAL_RESEARCH_STUB"}:
            soak = _soak(pair, timeframe, soak_cycles)

    write_ledger = _bool(payload.get("write_ledger"), default=False) and mode == "APPLY" and not blocked
    ledger_record = build_ledger_record(
        run_id=f"forex_{research_mode.lower()}_{pair.lower()}_{timeframe.lower()}_{generated_utc.replace(':', '').replace('-', '')}",
        mode=mode,
        task_type=f"FOREX_{research_mode}",
        status="PASS" if not blocked else "BLOCKED",
        generated_utc=generated_utc,
        safety=_safety(status=safety_status, writes_ledger=False, boundary_hits=boundary_hits),
        stop_reason=";".join(stop_conditions),
        next_safe_action=next_safe_action,
        result_summary={
            "research_mode": research_mode,
            "pair": pair,
            "timeframe": timeframe,
            "valid_for_live_trading": False,
        },
    )
    try:
        ledger = _write_or_reference_ledger(payload, ledger_record, write_ledger)
    except LedgerPathError as exc:
        stop_conditions.append("LEDGER_OUTPUT_ROOT_BLOCKED")
        safety_status = "BLOCKED"
        next_safe_action = f"Use an approved run ledger output root. {exc}"
        ledger = {"written": False, "error": str(exc), "safety": _safety(status="BLOCKED", writes_ledger=False)}

    return {
        "schema": SCHEMA,
        "mode": mode,
        "generated_utc": generated_utc,
        "repo_state": _repo_state(payload),
        "research_mode": research_mode,
        "pair": pair,
        "timeframe": timeframe,
        "strategy_profile": strategy_profile,
        "approval_state": {
            "human_owner_research_approval_required_for_apply": True,
            "human_owner_research_approval_present": approval == APPROVAL,
            "required_value": APPROVAL,
            "missing_requirements": _dedupe(missing),
        },
        "data_source": "SYNTHETIC_LOCAL_FIXTURE_ONLY",
        "synthetic_fixture_notice": "Synthetic deterministic fixtures only. No live market data, broker, OANDA, webhook, orders, secrets, or .env access.",
        "research_plan": plan,
        "backtest_result": backtest,
        "replay_result": replay,
        "soak_result": soak,
        "safety": _safety(
            status=safety_status,
            writes_ledger=bool(ledger.get("written")),
            boundary_hits=boundary_hits,
        ),
        "run_ledger": ledger,
        "stop_conditions": _dedupe(stop_conditions),
        "next_safe_action": next_safe_action,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run AIOS autonomous Forex research simulation pipeline.")
    parser.add_argument("--payload-base64", default="")
    args = parser.parse_args()
    if args.payload_base64:
        payload_text = base64.b64decode(args.payload_base64.encode("ascii")).decode("utf-8")
    else:
        # Decode the wire bytes independently of the host's console/code page.
        # Accept a BOM from older UTF-8 callers without weakening JSON parsing.
        payload_text = sys.stdin.buffer.read().decode("utf-8-sig")
    result = build_autonomous_forex_research_run_result(json.loads(payload_text))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["safety"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
