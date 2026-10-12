"""Generate C2 persistent profitability period evidence for Forex 110.

This module is local-only and review-only. It reads sanitized repo-local C2
walk-forward/OOS harness evidence and creates no broker, credential, demo,
live, order, money, commit, push, PR, merge, or background authority.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from automation.forex_engine.forex_110_c2_walkforward_oos_evidence_generation_v1 import (
    TARGET_CANDIDATE_ID,
)
from automation.forex_engine.forex_110_c2_real_walkforward_oos_harness_v1 import (
    HARNESS_PROVEN,
)
from automation.forex_engine.forex_110_profit_evidence_truth_lock_v1 import (
    run_profit_evidence_truth_lock,
)


PACKET_ID = "PKT-FOREX-110-PERSISTENT-PROFITABILITY-PERIOD-EVIDENCE-GENERATION-V1"
ENGINE_VERSION = "forex_110_persistent_profitability_period_evidence_v1"

DEFAULT_REPORT_ROOT = Path("Reports/forex_delivery")
HARNESS_STATE_NAME = "AIOS_FOREX_110_C2_REAL_WALKFORWARD_OOS_HARNESS_V1_STATE.json"
SOURCE_NAME = "AIOS_FOREX_110_PERSISTENT_PROFITABILITY_PERIOD_SOURCE_V1.md"

PERIOD_EVIDENCE_PROVEN = "PROVEN_PERSISTENT_PROFITABILITY_PERIODS"
PERIOD_EVIDENCE_BLOCKED = "BLOCKED_INSUFFICIENT_PROFITABLE_PERIODS"
PERIOD_EVIDENCE_SAMPLE_TEST_ONLY = "SAMPLE_TEST_ONLY"
PERIOD_EVIDENCE_MISSING_SOURCE = "BLOCKED_MISSING_C2_PERIOD_SOURCE"
PERIOD_EVIDENCE_UNVERIFIED = "BLOCKED_UNVERIFIED_C2_PERIOD_SOURCE"

MIN_CLOSED_TRADE_COUNT = 30
MIN_EXPECTANCY = 0.0
MIN_PROFIT_FACTOR = 1.1
MIN_PROFITABLE_PERIODS = 3

PROTECTED_PERMISSION_FLAGS = {
    "next_demo_trade_allowed": False,
    "broker_action_allowed": False,
    "real_money_allowed": False,
    "compounding_allowed": False,
    "bank_movement_allowed": False,
    "live_trading_allowed": False,
    "credential_access_allowed": False,
    "order_submission_allowed": False,
    "owner_approval_created": False,
}


def run_persistent_profitability_period_evidence(
    report_root: str | Path = DEFAULT_REPORT_ROOT,
) -> dict[str, Any]:
    """Return persistent period evidence state from the local C2 harness."""

    root = Path(report_root)
    harness_path = root / HARNESS_STATE_NAME
    harness = _read_json(harness_path)
    base_result = _base_result(root)
    base_result["c2_period_source_found"] = bool(harness)

    if not harness:
        return _blocked_result(
            base_result,
            PERIOD_EVIDENCE_MISSING_SOURCE,
            "REAL_LOCAL_DETERMINISTIC_SOURCE_NOT_FOUND",
            ["C2 real walk-forward/OOS harness state was not found"],
        )

    if harness.get("source_is_test_or_sample") is True:
        return _blocked_result(
            base_result,
            PERIOD_EVIDENCE_SAMPLE_TEST_ONLY,
            "SAMPLE_TEST_ONLY",
            ["C2 period source is marked test or sample"],
            source_is_test_or_sample=True,
        )

    if harness.get("harness_status") != HARNESS_PROVEN:
        return _blocked_result(
            base_result,
            PERIOD_EVIDENCE_MISSING_SOURCE,
            "BLOCKED_C2_HARNESS_NOT_PROVEN",
            ["C2 harness is not proven"],
        )

    if harness.get("candidate") != TARGET_CANDIDATE_ID or harness.get("candidate_alignment") != "ALIGNED":
        return _blocked_result(
            base_result,
            PERIOD_EVIDENCE_MISSING_SOURCE,
            "BLOCKED_CANDIDATE_MISMATCH",
            ["C2 candidate is not aligned"],
        )

    if harness.get("source_is_real_sanitized_local") is not True or harness.get("sanitized") is not True:
        return _blocked_result(
            base_result,
            PERIOD_EVIDENCE_MISSING_SOURCE,
            "BLOCKED_UNSANITIZED_C2_SOURCE",
            ["C2 source is not marked real sanitized local"],
        )

    periods = _profitable_periods_from_harness(harness)
    summary = _period_summary(harness, periods)
    missing_periods = max(0, MIN_PROFITABLE_PERIODS - int(summary["consecutive_profitable_periods"]))
    # A saved harness label and profitable numeric windows do not authenticate
    # original market data, fills, costs or independent replay. No verifier is
    # connected here; retain the arithmetic as diagnostics without exporting proof.

    result = {
        **base_result,
        "period_evidence_status": PERIOD_EVIDENCE_UNVERIFIED,
        "evidence_source_classification": "DIAGNOSTIC_UNVERIFIED_C2_PERIOD_SOURCE",
        "c2_period_source_generated": False,
        "source_path": "NONE",
        "source_is_test_or_sample": False,
        "source_is_real_sanitized_local": False,
        "consecutive_profitable_periods": summary["consecutive_profitable_periods"],
        "min_profitable_periods": summary["min_profitable_periods"],
        "missing_profitable_periods": missing_periods,
        "expectancy": summary["expectancy"],
        "profit_factor": summary["profit_factor"],
        "max_drawdown": summary["max_drawdown"],
        "closed_trade_count": summary["closed_trade_count"],
        "blockers": [
            "NO_INDEPENDENT_VERIFIER_CONNECTED",
            *(["profitable periods are below threshold"] if missing_periods else []),
        ],
        "source_authentication_status": "UNVERIFIED",
        "required_proof_fields": summary,
        "attack_to_finish": {
            **_attack_to_finish(False, missing_periods),
            "exact_blocker": "candidate source, trade receipts, costs and independent replay are unverified",
            "missing_evidence_field": "independent_source_verification",
            "stop_condition": "source authenticity remains unverified",
        },
        "next_safe_action": (
            "Provide independently verified candidate-bound source, trades and costs "
            "through the existing evidence owner. Do not trade."
        ),
    }
    return _attach_truth_lock(result, root)


def build_source_markdown(result: Mapping[str, Any]) -> str:
    """Build the consumable persistent profitability source report."""

    # Caller-supplied and historical result labels cannot authenticate a source.
    raise ValueError(
        "source markdown requires proven persistent period evidence; "
        "independent source verifier is unavailable"
    )


def build_report_markdown(result: Mapping[str, Any]) -> str:
    """Build an operator-readable period evidence report."""

    # Rendering a historical or caller-supplied label is not source verification.
    result = dict(result)
    result["source_authentication_status"] = "UNVERIFIED"
    result["source_is_real_sanitized_local"] = False
    result["permissions"] = dict(PROTECTED_PERMISSION_FLAGS)
    result["blockers"] = list(dict.fromkeys([
        *(result.get("blockers") or []), "NO_INDEPENDENT_VERIFIER_CONNECTED"
    ]))
    result["next_safe_action"] = (
        "Provide independently verified candidate-bound source, trades and costs "
        "through the existing evidence owner. Do not trade."
    )
    if result.get("period_evidence_status") == PERIOD_EVIDENCE_PROVEN:
        result["period_evidence_status"] = PERIOD_EVIDENCE_UNVERIFIED
    if result.get("evidence_source_classification") == "REAL_SANITIZED_LOCAL_C2_PERIOD_SOURCE":
        result["evidence_source_classification"] = "DIAGNOSTIC_UNVERIFIED_C2_PERIOD_SOURCE"
    result["c2_period_source_generated"] = False
    result["profit_truth_lock_status_after_rerun"] = "BLOCKED"
    result["profit_proof_status_after_rerun"] = "BLOCKED"
    result["persistent_profitability_status_after_rerun"] = "UNVERIFIED_DIAGNOSTIC"
    result["profit_persistence_unlocked"] = False
    result["attack_to_finish"] = {
        **dict(result.get("attack_to_finish") or {}),
        "blocker_id": "MISSING_SOURCE_AUTHENTICITY",
        "blocker_status": "BLOCKED",
        "exact_blocker": "candidate source, trade receipts, costs and independent replay are unverified",
        "missing_evidence_field": "independent_source_verification",
        "stop_condition": "source authenticity remains unverified",
    }

    lines = [
        "# AIOS Forex 110 Persistent Profitability Period Evidence V1",
        "",
        f"Packet ID: `{result.get('packet_id', PACKET_ID)}`",
        f"Period evidence status: `{result.get('period_evidence_status')}`",
        f"Evidence source classification: `{result.get('evidence_source_classification')}`",
        f"C2 period source found: `{str(result.get('c2_period_source_found')).lower()}`",
        f"C2 period source generated: `{str(result.get('c2_period_source_generated')).lower()}`",
        f"Source path: `{result.get('source_path')}`",
        f"Consecutive profitable periods: `{result.get('consecutive_profitable_periods')}`",
        f"Minimum profitable periods: `{result.get('min_profitable_periods')}`",
        f"Missing profitable periods: `{result.get('missing_profitable_periods')}`",
        f"Profit truth lock status after rerun: `{result.get('profit_truth_lock_status_after_rerun')}`",
        f"Profit proof status after rerun: `{result.get('profit_proof_status_after_rerun')}`",
        f"Persistent profitability status after rerun: `{result.get('persistent_profitability_status_after_rerun')}`",
        f"Profit persistence unlocked: `{str(result.get('profit_persistence_unlocked')).lower()}`",
        "",
        "## Permission Locks",
    ]
    for key, value in (result.get("permissions") or {}).items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in result.get("blockers") or ["none"])
    lines.extend(["", "## ATTACK_TO_FINISH"])
    for key, value in (result.get("attack_to_finish") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Next Safe Action", str(result.get("next_safe_action", "")), ""])
    return "\n".join(lines)


def _profitable_periods_from_harness(harness: Mapping[str, Any]) -> list[dict[str, Any]]:
    periods: list[dict[str, Any]] = []
    for row in (harness.get("walkforward_result") or {}).get("window_results") or []:
        profitability = row.get("profitability_result") or {}
        metrics = profitability.get("metrics") or {}
        profitable = (
            row.get("window_passed") is True
            and profitability.get("profitability_ready") is True
            and _float(profitability.get("expectancy_per_trade")) > MIN_EXPECTANCY
            and _float(profitability.get("profit_factor")) >= MIN_PROFIT_FACTOR
        )
        if not profitable:
            continue
        periods.append(
            {
                "window_id": row.get("window_number"),
                "expectancy": _float(profitability.get("expectancy_per_trade")),
                "profit_factor": _float(profitability.get("profit_factor")),
                "max_drawdown": _float(profitability.get("max_drawdown")),
                "closed_trades": int(_float(row.get("total_trades") or metrics.get("total_trades"))),
                "gross_profit": _float(metrics.get("gross_profit")),
                "gross_loss": _float(metrics.get("gross_loss")),
                "promotion_status": "PROFIT_OBJECTIVE_READY",
                "blocker_reasons": "none",
            }
        )
    return periods


def _period_summary(harness: Mapping[str, Any], periods: list[dict[str, Any]]) -> dict[str, Any]:
    total_trades = sum(int(period["closed_trades"]) for period in periods)
    gross_profit = sum(_float(period.get("gross_profit")) for period in periods)
    gross_loss = sum(_float(period.get("gross_loss")) for period in periods)
    weighted_expectancy = (
        sum(_float(period["expectancy"]) * int(period["closed_trades"]) for period in periods) / total_trades
        if total_trades
        else 0.0
    )
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
    max_drawdown = max((_float(period["max_drawdown"]) for period in periods), default=0.0)
    return {
        "closed_trade_count": total_trades,
        "min_closed_trade_count": MIN_CLOSED_TRADE_COUNT,
        "expectancy": round(weighted_expectancy, 8),
        "min_expectancy": MIN_EXPECTANCY,
        "profit_factor": round(profit_factor, 8),
        "min_profit_factor": MIN_PROFIT_FACTOR,
        "max_drawdown": max_drawdown,
        "max_allowed_drawdown": _float(harness.get("max_allowed_drawdown")),
        "consecutive_profitable_periods": _profitable_streak(harness, periods),
        "min_profitable_periods": MIN_PROFITABLE_PERIODS,
        "after_costs": False,
        "cost_verification_status": "UNVERIFIED",
        "expectancy_unit": "USD_DIAGNOSTIC",
        "sanitized": True,
        "evidence_age_days": _float(harness.get("evidence_age_days")),
        "max_evidence_age_days": _float(harness.get("max_evidence_age_days")),
    }


def _profitable_streak(harness: Mapping[str, Any], periods: list[dict[str, Any]]) -> int:
    passing = {period["window_id"] for period in periods}
    longest = streak = 0
    for row in (harness.get("walkforward_result") or {}).get("window_results") or []:
        streak = streak + 1 if row.get("window_number") in passing else 0
        longest = max(longest, streak)
    return longest


def _attach_truth_lock(result: dict[str, Any], root: Path) -> dict[str, Any]:
    truth_lock = run_profit_evidence_truth_lock(root)
    result["profit_truth_lock_status_after_rerun"] = truth_lock.get("truth_lock_status")
    result["profit_proof_status_after_rerun"] = truth_lock.get("profit_proof_status")
    result["persistent_profitability_status_after_rerun"] = truth_lock.get(
        "persistent_profitability_status"
    )
    result["profit_persistence_unlocked"] = (
        truth_lock.get("persistent_profitability_status") == "PERSISTENT_PROFITABILITY_READY"
        and truth_lock.get("profit_proof_status") == "PROVEN"
    )
    result["source_authentication_status"] = truth_lock.get("source_authentication_status", "UNVERIFIED")
    result["blockers"] = list(dict.fromkeys([
        *(result.get("blockers") or []), *(truth_lock.get("blockers") or []),
    ]))
    return result


def _blocked_result(
    base_result: dict[str, Any],
    status: str,
    classification: str,
    blockers: list[str],
    *,
    source_is_test_or_sample: bool = False,
) -> dict[str, Any]:
    result = {
        **base_result,
        "period_evidence_status": status,
        "evidence_source_classification": classification,
        "c2_period_source_generated": False,
        "source_path": "NONE",
        "source_is_test_or_sample": source_is_test_or_sample,
        "source_is_real_sanitized_local": False,
        "consecutive_profitable_periods": 0,
        "min_profitable_periods": MIN_PROFITABLE_PERIODS,
        "missing_profitable_periods": MIN_PROFITABLE_PERIODS,
        "expectancy": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "closed_trade_count": 0,
        "blockers": blockers,
        "required_proof_fields": {},
        "attack_to_finish": _attack_to_finish(False, MIN_PROFITABLE_PERIODS),
        "next_safe_action": "Provide real sanitized local C2 period evidence. Do not trade.",
    }
    return _attach_truth_lock(result, Path(base_result["report_root"]))


def _base_result(root: Path) -> dict[str, Any]:
    return {
        "packet_id": PACKET_ID,
        "engine_version": ENGINE_VERSION,
        "report_root": root.as_posix(),
        "target_candidate_id": TARGET_CANDIDATE_ID,
        "c2_period_source_found": False,
        "permissions": dict(PROTECTED_PERMISSION_FLAGS),
        **PROTECTED_PERMISSION_FLAGS,
    }


def _attack_to_finish(proven: bool, missing_periods: int) -> dict[str, str]:
    return {
        "blocker_id": "NO_BLOCKER" if proven else "MISSING_EVIDENCE_FIELD",
        "blocker_status": "PROVEN" if proven else "BLOCKED",
        "exact_blocker": "NONE"
        if proven
        else f"persistent profitability period proof is short by {missing_periods} periods",
        "canonical_owner_file": "automation/forex_engine/profitability_evidence_intake_v1.py",
        "test_file": "tests/forex_engine/test_forex_110_persistent_profitability_period_evidence_v1.py",
        "runner_script": "scripts/forex_delivery/run_forex_110_persistent_profitability_period_evidence_v1.py",
        "missing_evidence_field": "NONE" if proven else "consecutive_profitable_periods",
        "unlock_status_required": "PROVEN",
        "next_packet_name": "NONE" if proven else "PKT-FOREX-110-COLLECT-ADDITIONAL-PROFITABLE-PERIODS-V1",
        "owner_action_required": "NONE",
        "stop_condition": "NONE" if proven else "insufficient profitable periods",
        "no_bloat_guard": "Reuse existing profitability intake and do not create duplicate profit-proof authority.",
    }


def _read_json(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, Mapping) else {}


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


__all__ = [
    "ENGINE_VERSION",
    "PACKET_ID",
    "PERIOD_EVIDENCE_BLOCKED",
    "PERIOD_EVIDENCE_MISSING_SOURCE",
    "PERIOD_EVIDENCE_UNVERIFIED",
    "PERIOD_EVIDENCE_PROVEN",
    "PERIOD_EVIDENCE_SAMPLE_TEST_ONLY",
    "SOURCE_NAME",
    "build_report_markdown",
    "build_source_markdown",
    "run_persistent_profitability_period_evidence",
]
