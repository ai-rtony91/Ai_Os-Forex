"""Build sanitized C2 walk-forward/OOS harness evidence.

This module is local review-only. It does not contact brokers, read
credentials, access accounts, submit orders, start services, or grant trading
authority.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from automation.forex_engine.forex_110_c2_walkforward_oos_evidence_generation_v1 import (
    TARGET_CANDIDATE_ID,
)
from automation.forex_engine.walk_forward_oos_evidence_v1 import (
    WALK_FORWARD_OOS_READY,
    evaluate_walk_forward_oos_evidence,
)
from automation.forex_engine.walkforward_validation_harness import (
    validate_walkforward_strategy,
)


PACKET_ID = "PKT-FOREX-110-C2-REAL-WALKFORWARD-OOS-HARNESS-BUILD-V1"
ENGINE_VERSION = "forex_110_c2_real_walkforward_oos_harness_v1"

HARNESS_PROVEN = "PROVEN_REAL_WALKFORWARD_OOS_HARNESS"
HARNESS_BLOCKED = "BLOCKED_REAL_WALKFORWARD_OOS_HARNESS"

MINIMUM_WINDOWS = 6
MINIMUM_OOS_SEGMENTS = 4
MINIMUM_PASS_RATE = 0.75
MAX_ALLOWED_DRAWDOWN = 0.5
MAX_EVIDENCE_AGE_DAYS = 7

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


def build_default_c2_harness_input() -> dict[str, Any]:
    """Return deterministic local C2 review inputs for the harness."""

    return {
        "candidate": TARGET_CANDIDATE_ID,
        "strategy_name": "paper_long_run_supervisor_v2",
        "strategy_version": "c2-real-oos-v1",
        "walkforward_windows": [
            [0.62, -0.20, 0.48, 0.36, -0.14, 0.52, 0.31],
            [0.55, -0.18, 0.44, 0.39, -0.12, 0.47, 0.28],
            [0.58, -0.16, 0.41, 0.35, -0.10, 0.45, 0.30],
            [0.60, -0.22, 0.46, 0.33, -0.13, 0.50, 0.29],
            [0.57, -0.19, 0.43, 0.34, -0.11, 0.49, 0.27],
            [0.63, -0.21, 0.47, 0.37, -0.15, 0.51, 0.32],
        ],
        "oos_segments": [
            [0.44, -0.13, 0.36, 0.28, -0.08, 0.33],
            [0.42, -0.12, 0.34, 0.27, -0.09, 0.31],
            [0.45, -0.14, 0.35, 0.29, -0.10, 0.32],
            [0.43, -0.11, 0.33, 0.26, -0.08, 0.30],
        ],
        "evidence_age_days": 1,
    }


def run_c2_real_walkforward_oos_harness(
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate C2 walk-forward and OOS windows into a sanitized source state."""

    raw = dict(payload or build_default_c2_harness_input())
    # Match both automatic fallback and caller-supplied copies of the deterministic fixture.
    uses_default_fixture = not payload or _payload_matches_default_fixture(raw)
    candidate = str(raw.get("candidate") or "")
    strategy_name = str(raw.get("strategy_name") or "paper_long_run_supervisor_v2")
    strategy_version = str(raw.get("strategy_version") or "c2-real-oos-v1")
    walkforward_windows = _as_window_matrix(raw.get("walkforward_windows"))
    oos_segments = _as_window_matrix(raw.get("oos_segments"))
    evidence_age_days = _finite_float(raw.get("evidence_age_days"), MAX_EVIDENCE_AGE_DAYS)

    walkforward = validate_walkforward_strategy(
        strategy_name,
        strategy_version,
        validation_windows=len(walkforward_windows),
        window_trade_outcomes=walkforward_windows,
        minimum_windows=MINIMUM_WINDOWS,
        maximum_drawdown=MAX_ALLOWED_DRAWDOWN,
    )
    oos_results = [
        validate_walkforward_strategy(
            strategy_name,
            f"{strategy_version}-oos-{index:02d}",
            validation_windows=1,
            window_trade_outcomes=[segment],
            minimum_windows=1,
            maximum_drawdown=MAX_ALLOWED_DRAWDOWN,
        )
        for index, segment in enumerate(oos_segments, start=1)
    ]

    windows_total = int(walkforward.get("windows_evaluated", 0))
    windows_passed = int(walkforward.get("passing_windows", 0))
    oos_segments_total = len(oos_results)
    oos_segments_passed = sum(1 for result in oos_results if result.get("demo_candidate") is True)
    max_drawdown = max(
        [_finite_float(walkforward.get("aggregate_drawdown"))]
        + [_finite_float(result.get("aggregate_drawdown")) for result in oos_results]
    )

    summary = {
        "windows_total": windows_total,
        "windows_passed": windows_passed,
        "oos_segments_total": oos_segments_total,
        "oos_segments_passed": oos_segments_passed,
        "min_pass_rate": MINIMUM_PASS_RATE,
        "max_drawdown": max_drawdown,
        "max_allowed_drawdown": MAX_ALLOWED_DRAWDOWN,
        "sanitized": True,
        "evidence_age_days": evidence_age_days,
        "max_evidence_age_days": MAX_EVIDENCE_AGE_DAYS,
    }
    oos_evaluation = evaluate_walk_forward_oos_evidence(summary)
    candidate_alignment = "ALIGNED" if candidate == TARGET_CANDIDATE_ID else "BLOCKED_CANDIDATE_MISMATCH"
    blockers = _blockers(candidate_alignment, walkforward, oos_results, oos_evaluation)
    if uses_default_fixture:
        blockers = _dedupe([*blockers, "default walk-forward/OOS inputs are synthetic sample data"])
    # Numeric outcomes and caller labels cannot authenticate their own source.
    # This interface has no independent raw-receipt verifier; keep proof closed.
    blockers = _dedupe([*blockers, "source authenticity is not independently verified"])
    status = HARNESS_PROVEN if not blockers else HARNESS_BLOCKED

    return {
        "packet_id": PACKET_ID,
        "engine_version": ENGINE_VERSION,
        "candidate": candidate,
        "target_candidate_id": TARGET_CANDIDATE_ID,
        "candidate_alignment": candidate_alignment,
        "harness_status": status,
        "walkforward_oos_status": oos_evaluation.get("walk_forward_oos_status"),
        "source_authentication_status": "UNVERIFIED",
        "source_is_real_sanitized_local": status == HARNESS_PROVEN and not uses_default_fixture,
        "source_is_test_or_sample": uses_default_fixture,
        "source_classification": (
            "REAL_SANITIZED_LOCAL_HARNESS"
            if status == HARNESS_PROVEN and not uses_default_fixture
            else "BLOCKED"
        ),
        "windows_total": windows_total,
        "windows_passed": windows_passed,
        "oos_segments_total": oos_segments_total,
        "oos_segments_passed": oos_segments_passed,
        "min_pass_rate": MINIMUM_PASS_RATE,
        "max_drawdown": max_drawdown,
        "max_allowed_drawdown": MAX_ALLOWED_DRAWDOWN,
        "sanitized": True,
        "evidence_age_days": evidence_age_days,
        "max_evidence_age_days": MAX_EVIDENCE_AGE_DAYS,
        "walkforward_result": walkforward,
        "oos_segment_results": oos_results,
        "adapter_result": oos_evaluation,
        "blockers": blockers,
        "permissions": dict(PROTECTED_PERMISSION_FLAGS),
        **PROTECTED_PERMISSION_FLAGS,
        "next_safe_action": (
            "Rerun C2 source collection and sufficiency truth lock. Do not trade."
            if status == HARNESS_PROVEN
            else "Repair harness blockers before rerunning C2 source collection. Do not trade."
        ),
    }


def build_report_markdown(result: Mapping[str, Any]) -> str:
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
    result["harness_status"] = HARNESS_BLOCKED
    result["walkforward_oos_status"] = "UNVERIFIED_DIAGNOSTIC"

    lines = [
        "# AIOS Forex 110 C2 Real Walk-Forward OOS Harness V1",
        "",
        f"Packet ID: `{result.get('packet_id', PACKET_ID)}`",
        f"Harness status: `{result.get('harness_status')}`",
        f"Candidate: `{result.get('candidate')}`",
        f"Candidate alignment: `{result.get('candidate_alignment')}`",
        f"Walk-forward/OOS status: `{result.get('walkforward_oos_status')}`",
        "",
        "## Sanitized Evidence Fields",
    ]
    for field in (
        "windows_total",
        "windows_passed",
        "oos_segments_total",
        "oos_segments_passed",
        "min_pass_rate",
        "max_drawdown",
        "max_allowed_drawdown",
        "sanitized",
        "evidence_age_days",
        "max_evidence_age_days",
    ):
        lines.append(f"- {field}: `{result.get(field)}`")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in result.get("blockers") or ["none"])
    lines.extend(["", "## Permission Locks"])
    for key, value in (result.get("permissions") or {}).items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.extend(["", "## Next Safe Action", str(result.get("next_safe_action", "")), ""])
    return "\n".join(lines)


def build_source_markdown(result: Mapping[str, Any]) -> str:
    """Refuse proof export until an independent source verifier exists."""

    # Historical and caller-supplied result labels cannot authenticate evidence.
    raise ValueError(
        "source markdown requires proven harness evidence; "
        "independent source verifier is unavailable"
    )



def _payload_matches_default_fixture(raw: Mapping[str, Any]) -> bool:
    default = build_default_c2_harness_input()
    return all(raw.get(key) == value for key, value in default.items())

def _as_window_matrix(value: Any) -> list[list[Any]]:
    if not isinstance(value, list):
        return []
    matrix: list[list[Any]] = []
    for item in value:
        matrix.append(item if isinstance(item, list) else [item])
    return matrix


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return round(parsed, 8) if math.isfinite(parsed) else default


def _blockers(
    candidate_alignment: str,
    walkforward: Mapping[str, Any],
    oos_results: list[Mapping[str, Any]],
    oos_evaluation: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if candidate_alignment != "ALIGNED":
        blockers.append("candidate is not aligned to C2 target")
    if int(walkforward.get("windows_evaluated", 0)) < MINIMUM_WINDOWS:
        blockers.append("insufficient walk-forward windows")
    if int(walkforward.get("passing_windows", 0)) < MINIMUM_WINDOWS:
        blockers.append("insufficient passing walk-forward windows")
    if len(oos_results) < MINIMUM_OOS_SEGMENTS:
        blockers.append("insufficient OOS segments")
    if sum(1 for result in oos_results if result.get("demo_candidate") is True) < MINIMUM_OOS_SEGMENTS:
        blockers.append("insufficient passing OOS segments")
    if oos_evaluation.get("walk_forward_oos_status") != WALK_FORWARD_OOS_READY:
        blockers.extend(str(item) for item in oos_evaluation.get("blockers", []))
    return _dedupe(blockers)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


__all__ = [
    "HARNESS_BLOCKED",
    "HARNESS_PROVEN",
    "PACKET_ID",
    "TARGET_CANDIDATE_ID",
    "build_default_c2_harness_input",
    "build_report_markdown",
    "build_source_markdown",
    "run_c2_real_walkforward_oos_harness",
]
