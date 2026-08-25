"""Reconcile existing Forex risk authority without creating new policy.

This module is an evidence-only audit.  It ranks current repository sources,
proves the existing paper-only risk governor with synthetic inputs, and leaves
unknown numeric limits unresolved for the Human Owner.  It cannot connect to a
broker, submit an order, read credentials, or mutate PAPER30 state.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine import forex_live_readiness_hardening_v1 as hardening  # noqa: E402
from automation.forex_engine.risk_governor import (  # noqa: E402
    COOLDOWN_AFTER_LOSS_REASON,
    DUPLICATE_SETUP_REASON,
    EXCESSIVE_RISK_PER_TRADE_REASON,
    KILL_SWITCH_ACTIVE_REASON,
    MAX_DAILY_LOSS_HIT_REASON,
    MAX_OPEN_RISK_HIT_REASON,
    MAX_OPEN_TRADES_HIT_REASON,
    MAX_PAIR_EXPOSURE_HIT_REASON,
    SPREAD_TOO_HIGH_REASON,
    STALE_MARKET_DATA_REASON,
    RISK_GOVERNOR_MODE,
    evaluate_risk_preview,
)


PACKET_ID = "PKT-EAST-FOREX-RISK-AUTHORITY-CLOSURE-019"
LOCK_ID = "LOCK_EAST_FOREX_LIVE_READINESS_RESEARCH_EAST_OCC_01"
PAPER30_STRATEGY_CONFIG_SHA256 = hardening.PAPER30_STRATEGY_CONFIG_SHA256
PAPER30_RUNTIME_PATH = hardening.PAPER30_RUNTIME_PATH
PAPER30_LEDGER_PATH = hardening.PAPER30_LEDGER_PATH
PAPER30_STATE_PATH = hardening.PAPER30_STATE_PATH
PACKET018A_RESULT_PATH = (
    ROOT
    / "Reports/forex_delivery/AIOS_FOREX_LIVE_READINESS_BLOCKER_CLOSURE_V1_RESULTS.json"
)
RESULT_PATH = ROOT / "Reports/forex_delivery/AIOS_FOREX_RISK_AUTHORITY_CLOSURE_V1_RESULTS.json"

RISK_AUTHORITY_CONFLICT = "RISK_AUTHORITY_CONFLICT"
RISK_AUTHORITY_VALIDATION_FAILED = "RISK_AUTHORITY_VALIDATION_FAILED"

CONTROLS = (
    "MAX_RISK_PER_TRADE",
    "MAX_DAILY_LOSS",
    "MAX_OPEN_RISK",
    "MAX_OPEN_TRADES",
    "MAX_PAIR_EXPOSURE",
    "MAX_SPREAD",
    "MAX_DRAWDOWN",
    "LOSS_STREAK_LIMIT",
    "COOLDOWN_AFTER_LOSS",
    "KILL_SWITCH",
)

AUTHORITY_LEVELS = {
    1: "RISK_POLICY_EXPLICIT",
    2: "DELEGATED_CANONICAL_GOVERNANCE_OR_RISK_SPECIFICATION",
    3: "CANONICAL_PRODUCTION_GRADE_CONFIGURATION_OR_CODE",
    4: "VALIDATED_CANONICAL_REPORT",
    5: "TEST_OR_EXAMPLE_NON_AUTHORITY",
    6: "LEGACY_OR_GENERATED_EVIDENCE_NON_AUTHORITY",
}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(RISK_AUTHORITY_VALIDATION_FAILED)
    if isinstance(value, Mapping):
        for nested in value.values():
            _assert_finite(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_finite(nested)


def source_contract_proof() -> dict[str, Any]:
    """Verify that the ranked values still exist in their current sources."""

    markers = {
        ROOT / "RISK_POLICY.md": (
            "daily loss cap is required and must be active before arming",
            "kill switch is required and must be active before arming",
        ),
        ROOT / "automation/forex_engine/risk_governor.py": (
            "max_risk_per_trade_pct: float = 1.0",
            "max_daily_loss: float = 0.0",
            "max_open_risk: float = 0.0",
            "max_open_trades: int = 1",
            "max_pair_exposure: float = 0.0",
            "max_spread: float = 0.0",
            "max_data_age_seconds: float = 300.0",
            "cooldown_after_loss_seconds: float = 0.0",
        ),
        ROOT / "automation/forex_engine/risk_management.py": (
            "WEEKLY_DRAWDOWN_THRESHOLD_PCT = 5.0",
            "pause_after_consecutive_losses",
        ),
        ROOT / "automation/forex_engine/live_readiness_review.py": (
            '"maximum_drawdown_pct": _number(raw.get("maximum_drawdown_pct"), 5.0)',
        ),
        ROOT / "automation/forex_engine/forex_basket_risk_exposure_governor_v1.py": (
            "max_risk_per_trade <= 0 or max_risk_per_trade > 0.01",
            "max_daily_loss <= 0 or max_daily_loss > 0.03",
        ),
        ROOT / "docs/orchestration/AIOS_FOREX_RISK_GOVERNOR.md": (
            "`max_risk_per_trade_pct=1.0`",
            "`max_daily_loss=0.0` (disabled unless provided in limits/account)",
            "`max_open_trades=1`",
            "`max_data_age_seconds=300`",
        ),
    }
    checked: list[dict[str, Any]] = []
    for path, required in markers.items():
        source = path.read_text(encoding="utf-8")
        missing = [marker for marker in required if marker not in source]
        checked.append(
            {
                "source_path": path.relative_to(ROOT).as_posix(),
                "required_marker_count": len(required),
                "missing_marker_count": len(missing),
            }
        )
        if missing:
            raise ValueError(RISK_AUTHORITY_VALIDATION_FAILED)
    return {"source_contract_proven": True, "sources": checked}


def authority_candidates() -> list[dict[str, Any]]:
    """Return all discovered values, including explicitly non-authoritative ones."""

    return [
        _candidate("MAX_RISK_PER_TRADE", 1.0, "PERCENT", "automation/forex_engine/risk_governor.py:RiskGovernorLimits", "CANONICAL_CODE_DEFAULT", 3, "CURRENT", "IMPLEMENTED", "EXACT_ACTIVE"),
        _candidate("MAX_RISK_PER_TRADE", 0.01, "ACCOUNT_FRACTION", "automation/forex_engine/forex_basket_risk_exposure_governor_v1.py", "IMPLEMENTED_CEILING", 3, "CURRENT", "IMPLEMENTED", "CONSTRAINT_ONLY"),
        _candidate("MAX_RISK_PER_TRADE", 1.0, "PERCENT", "Reports/forex_delivery/AIOS_FOREX_SPRINT2B_RISK_BUDGET_SPEC_V1_REPORT.md", "PLANNING_DEFAULT", 6, "LEGACY_OR_GENERATED", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("MAX_RISK_PER_TRADE", 1.0, "PERCENT", "tests/forex_engine/test_risk_governor.py", "TEST_FIXTURE", 5, "CURRENT", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("MAX_DAILY_LOSS", None, "OWNER_SUPPLIED_CAP", "RISK_POLICY.md:Single Live Micro-Trade Exception", "REQUIRED_WITHOUT_VALUE", 1, "CURRENT", "DOCUMENTED", "REQUIRED_NO_VALUE"),
        _candidate("MAX_DAILY_LOSS", 0.0, "ACCOUNT_CURRENCY", "automation/forex_engine/risk_governor.py:RiskGovernorLimits", "DISABLED_DEFAULT", 3, "CURRENT", "IMPLEMENTED", "DISABLED_DEFAULT"),
        _candidate("MAX_DAILY_LOSS", 0.03, "ACCOUNT_FRACTION", "automation/forex_engine/forex_basket_risk_exposure_governor_v1.py", "IMPLEMENTED_CEILING", 3, "CURRENT", "IMPLEMENTED", "CONSTRAINT_ONLY"),
        _candidate("MAX_DAILY_LOSS", 3.0, "PERCENT", "Reports/forex_delivery/AIOS_FOREX_SPRINT2B_RISK_BUDGET_SPEC_V1_REPORT.md", "PLANNING_DEFAULT", 6, "LEGACY_OR_GENERATED", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("MAX_DAILY_LOSS", 250.0, "USD", "automation/forex_engine/demo_trade_risk_gate_v1.py:build_sample_valid_risk_input", "SAMPLE_FIXTURE", 5, "CURRENT", "IMPLEMENTED", "NON_AUTHORITY"),
        _candidate("MAX_DAILY_LOSS", 100.0, "USD", "tests/forex_engine/test_risk_governor.py", "TEST_FIXTURE", 5, "CURRENT", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("MAX_OPEN_RISK", 0.0, "ACCOUNT_CURRENCY", "automation/forex_engine/risk_governor.py:RiskGovernorLimits", "DISABLED_DEFAULT", 3, "CURRENT", "IMPLEMENTED", "DISABLED_DEFAULT"),
        _candidate("MAX_OPEN_RISK", 3.0, "PERCENT", "Reports/forex_delivery/AIOS_FOREX_SPRINT2B_RISK_BUDGET_SPEC_V1_REPORT.md", "PLANNING_DEFAULT", 6, "LEGACY_OR_GENERATED", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("MAX_OPEN_RISK", 1000.0, "USD", "tests/forex_engine/test_risk_governor.py", "TEST_FIXTURE", 5, "CURRENT", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("MAX_OPEN_TRADES", 1, "COUNT", "automation/forex_engine/risk_governor.py:RiskGovernorLimits", "CANONICAL_CODE_DEFAULT", 3, "CURRENT", "IMPLEMENTED", "EXACT_ACTIVE"),
        _candidate("MAX_OPEN_TRADES", 1, "COUNT", "docs/orchestration/AIOS_FOREX_RISK_GOVERNOR.md", "CANONICAL_IMPLEMENTATION_DOCUMENTATION", 3, "CURRENT", "DOCUMENTED", "CORROBORATING"),
        _candidate("MAX_OPEN_TRADES", 1, "COUNT", "Reports/forex_delivery/AIOS_FOREX_SPRINT2B_RISK_BUDGET_SPEC_V1_REPORT.md", "PLANNING_DEFAULT", 6, "LEGACY_OR_GENERATED", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("MAX_PAIR_EXPOSURE", 0.0, "QUOTE_CURRENCY_NOTIONAL", "automation/forex_engine/risk_governor.py:RiskGovernorLimits", "DISABLED_DEFAULT", 3, "CURRENT", "IMPLEMENTED", "DISABLED_DEFAULT"),
        _candidate("MAX_PAIR_EXPOSURE", 2.0, "PERCENT", "Reports/forex_delivery/AIOS_FOREX_SPRINT2B_RISK_BUDGET_SPEC_V1_REPORT.md", "PLANNING_DEFAULT", 6, "LEGACY_OR_GENERATED", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("MAX_PAIR_EXPOSURE", 1000.0, "QUOTE_CURRENCY_NOTIONAL", "tests/forex_engine/test_risk_governor.py", "TEST_FIXTURE", 5, "CURRENT", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("MAX_SPREAD", 0.0, "PRICE_DISTANCE", "automation/forex_engine/risk_governor.py:RiskGovernorLimits", "DISABLED_DEFAULT", 3, "CURRENT", "IMPLEMENTED", "DISABLED_DEFAULT"),
        _candidate("MAX_SPREAD", 0.001, "PRICE_DISTANCE", "tests/forex_engine/test_risk_governor.py", "TEST_FIXTURE", 5, "CURRENT", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("MAX_SPREAD", 1.5, "UNSPECIFIED_SAMPLE_UNIT", "automation/forex_engine/demo_trade_risk_gate_v1.py:build_sample_valid_risk_input", "SAMPLE_FIXTURE", 5, "CURRENT", "IMPLEMENTED", "NON_AUTHORITY"),
        _candidate("MAX_DRAWDOWN", 5.0, "PERCENT", "automation/forex_engine/risk_management.py:WEEKLY_DRAWDOWN_THRESHOLD_PCT", "CANONICAL_CODE_CONSTANT", 3, "CURRENT", "IMPLEMENTED", "EXACT_ACTIVE"),
        _candidate("MAX_DRAWDOWN", 5.0, "PERCENT", "automation/forex_engine/live_readiness_review.py:_limits", "CANONICAL_REVIEW_DEFAULT", 3, "CURRENT", "IMPLEMENTED", "EXACT_ACTIVE"),
        _candidate("MAX_DRAWDOWN", 10.0, "PERCENT", "Reports/forex_delivery/AIOS_FOREX_SPRINT2B_RISK_BUDGET_SPEC_V1_REPORT.md", "PLANNING_DEFAULT", 6, "LEGACY_OR_GENERATED", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("LOSS_STREAK_LIMIT", None, "CONSECUTIVE_LOSSES", "automation/forex_engine/risk_management.py:ForexEngineConfig.pause_after_consecutive_losses", "EXTERNAL_CONFIGURATION_REFERENCE", 3, "CURRENT", "IMPLEMENTED", "OPTIONAL_NO_VALUE"),
        _candidate("LOSS_STREAK_LIMIT", 3, "CONSECUTIVE_LOSSES", "tests/forex_engine/test_forex_live_readiness_hardening_v1.py", "TEST_FIXTURE", 5, "CURRENT", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("COOLDOWN_AFTER_LOSS", 0.0, "SECONDS", "automation/forex_engine/risk_governor.py:RiskGovernorLimits", "DISABLED_DEFAULT", 3, "CURRENT", "IMPLEMENTED", "OPTIONAL_DISABLED"),
        _candidate("COOLDOWN_AFTER_LOSS", 120.0, "SECONDS", "tests/forex_engine/test_risk_governor.py", "TEST_FIXTURE", 5, "CURRENT", "DOCUMENTED", "NON_AUTHORITY"),
        _candidate("KILL_SWITCH", True, "BOOLEAN_REQUIRED", "RISK_POLICY.md:Single Live Micro-Trade Exception", "ROOT_POLICY_REQUIREMENT", 1, "CURRENT", "DOCUMENTED", "EXACT_ACTIVE"),
        _candidate("KILL_SWITCH", True, "BOOLEAN_INPUT", "automation/forex_engine/risk_governor.py", "CANONICAL_FAIL_CLOSED_IMPLEMENTATION", 3, "CURRENT", "IMPLEMENTED", "CORROBORATING"),
    ]


def _candidate(
    risk_control: str,
    value: Any,
    unit: str,
    source_path: str,
    source_type: str,
    authority_level: int,
    current_or_legacy: str,
    implemented_or_documented: str,
    authority_kind: str,
) -> dict[str, Any]:
    return {
        "risk_control": risk_control,
        "value": value,
        "unit": unit,
        "source_path": source_path,
        "source_type": source_type,
        "authority_level": authority_level,
        "authority_level_name": AUTHORITY_LEVELS[authority_level],
        "current_or_legacy": current_or_legacy,
        "implemented_or_documented": implemented_or_documented,
        "authority_kind": authority_kind,
    }


def analyze_authority_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Rank exact active values and fail closed on same-control disagreement."""

    grouped = {control: [] for control in CONTROLS}
    for raw in candidates:
        item = dict(raw)
        control = item.get("risk_control")
        if control not in grouped:
            raise ValueError(RISK_AUTHORITY_VALIDATION_FAILED)
        grouped[control].append(item)

    inventory: dict[str, Any] = {}
    conflict_count = 0
    for control, items in grouped.items():
        authoritative = [
            item
            for item in items
            if item.get("authority_level") in {1, 2, 3, 4}
            and item.get("current_or_legacy") == "CURRENT"
            and item.get("authority_kind") == "EXACT_ACTIVE"
        ]
        distinct = {
            (json.dumps(item.get("value"), sort_keys=True), str(item.get("unit")))
            for item in authoritative
        }
        conflict = len(distinct) > 1
        conflict_count += int(conflict)
        inventory[control] = {
            "candidate_count": len(items),
            "value_candidate_count": sum(item.get("value") is not None for item in items),
            "authoritative_value_count": len(authoritative),
            "conflict_present": conflict,
            "candidates": copy.deepcopy(items),
        }
    if conflict_count:
        raise ValueError(RISK_AUTHORITY_CONFLICT)
    return {
        "controls": inventory,
        "risk_authority_conflict_count": 0,
        "authority_hierarchy": copy.deepcopy(AUTHORITY_LEVELS),
        "tests_examples_create_authority": False,
    }


def canonical_risk_map(
    analysis: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve only exact active values; disabled defaults remain missing."""

    if analysis is None:
        analysis = analyze_authority_candidates(authority_candidates())
    if analysis.get("risk_authority_conflict_count") != 0:
        raise ValueError(RISK_AUTHORITY_CONFLICT)

    return {
        "MAX_RISK_PER_TRADE": _map_entry("PROVEN", 1.0, "PERCENT", "automation/forex_engine/risk_governor.py:RiskGovernorLimits", "automation/forex_engine/risk_governor.py:evaluate_risk_preview", True),
        "MAX_DAILY_LOSS": _map_entry("MISSING_AUTHORITY", None, "ACCOUNT_CURRENCY", "RISK_POLICY.md requires an owner-supplied daily loss cap but defines no number", "automation/forex_engine/risk_governor.py:evaluate_risk_preview", True),
        "MAX_OPEN_RISK": _map_entry("MISSING_AUTHORITY", None, "ACCOUNT_CURRENCY", "automation/forex_engine/risk_governor.py default 0.0 disables the control", "automation/forex_engine/risk_governor.py:evaluate_risk_preview", True),
        "MAX_OPEN_TRADES": _map_entry("PROVEN", 1, "COUNT", "automation/forex_engine/risk_governor.py:RiskGovernorLimits", "automation/forex_engine/risk_governor.py:evaluate_risk_preview", True),
        "MAX_PAIR_EXPOSURE": _map_entry("MISSING_AUTHORITY", None, "QUOTE_CURRENCY_NOTIONAL", "automation/forex_engine/risk_governor.py default 0.0 disables the control", "automation/forex_engine/risk_governor.py:evaluate_risk_preview", True),
        "MAX_SPREAD": _map_entry("MISSING_AUTHORITY", None, "PRICE_DISTANCE", "automation/forex_engine/risk_governor.py default 0.0 disables the control", "automation/forex_engine/risk_governor.py:evaluate_risk_preview", True),
        "MAX_DRAWDOWN": _map_entry("PROVEN", 5.0, "PERCENT", "automation/forex_engine/risk_management.py and automation/forex_engine/live_readiness_review.py", "automation/forex_engine/risk_management.py and automation/forex_engine/live_readiness_review.py", True),
        "LOSS_STREAK_LIMIT": _map_entry("NOT_APPLICABLE", None, "CONSECUTIVE_LOSSES", "No root or canonical governor authority makes loss streak mandatory", "automation/forex_engine/risk_management.py supports caller configuration", True),
        "COOLDOWN_AFTER_LOSS": _map_entry("NOT_APPLICABLE", 0.0, "SECONDS", "automation/forex_engine/risk_governor.py explicitly disables cooldown at 0.0", "automation/forex_engine/risk_governor.py:evaluate_risk_preview", True),
        "KILL_SWITCH": _map_entry("PROVEN", True, "BOOLEAN_REQUIRED", "RISK_POLICY.md:Single Live Micro-Trade Exception", "automation/forex_engine/risk_governor.py:evaluate_risk_preview", True),
    }


def _map_entry(
    status: str,
    value: Any,
    unit: str,
    authority_source: str,
    implementation_source: str,
    synthetic_test_available: bool,
) -> dict[str, Any]:
    return {
        "status": status,
        "value": value,
        "unit": unit,
        "authority_source": authority_source,
        "implementation_source": implementation_source,
        "synthetic_test_available": synthetic_test_available,
    }


def _base_preview() -> dict[str, Any]:
    return {
        "pair": "EURUSD",
        "direction": "buy",
        "entry_price": 1.1,
        "stop_loss": 1.09,
        "take_profit": 1.12,
        "units": 100.0,
        "dollar_risk": 50.0,
        "percent_risk": 0.5,
        "paper_only": True,
        "mode": RISK_GOVERNOR_MODE,
        "status": "candidate",
    }


def _has_reason(result: Mapping[str, Any], reason: str) -> bool:
    return result.get("allowed") is False and reason in result.get("blocked_reasons", [])


def risk_governor_synthetic_proof() -> dict[str, Any]:
    """Prove governor behavior; fixture thresholds never become authority."""

    base = _base_preview()
    account = {"equity": 10000.0, "daily_loss_used": 0.0, "open_risk": 0.0}
    now = "2026-08-22T12:10:00+00:00"

    per_trade_equal = evaluate_risk_preview(
        {**base, "dollar_risk": 100.0, "percent_risk": 1.0},
        account_state=account,
        limits={"max_risk_per_trade_pct": 1.0},
        now_timestamp=now,
    )
    per_trade_excess = evaluate_risk_preview(
        {**base, "dollar_risk": 101.0, "percent_risk": 1.01},
        account_state=account,
        limits={"max_risk_per_trade_pct": 1.0},
        now_timestamp=now,
    )

    daily_below = evaluate_risk_preview(
        {**base, "dollar_risk": 49.0, "percent_risk": 0.49},
        account_state={**account, "daily_loss_used": 50.0},
        limits={"max_daily_loss": 100.0},
        now_timestamp=now,
    )
    daily_at = evaluate_risk_preview(
        base,
        account_state={**account, "daily_loss_used": 50.0},
        limits={"max_daily_loss": 100.0},
        now_timestamp=now,
    )
    daily_beyond = evaluate_risk_preview(
        {**base, "dollar_risk": 51.0, "percent_risk": 0.51},
        account_state={**account, "daily_loss_used": 50.0},
        limits={"max_daily_loss": 100.0},
        now_timestamp=now,
    )

    open_risk = evaluate_risk_preview(
        base,
        account_state={**account, "open_risk": 60.0},
        limits={"max_open_risk": 100.0},
        now_timestamp=now,
    )
    other_open = {
        "pair": "GBPUSD",
        "direction": "buy",
        "status": "active",
        "units": 100.0,
        "entry_price": 1.2,
    }
    open_trades = evaluate_risk_preview(
        base,
        account_state=account,
        open_trades=[other_open],
        limits={"max_open_trades": 1},
        now_timestamp=now,
    )
    pair_exposure = evaluate_risk_preview(
        {**base, "units": 1000.0},
        account_state=account,
        limits={"max_pair_exposure": 1000.0},
        now_timestamp=now,
    )
    spread = evaluate_risk_preview(
        {**base, "spread": 0.002},
        account_state=account,
        limits={"max_spread": 0.001},
        now_timestamp=now,
    )
    stale = evaluate_risk_preview(
        {**base, "data_timestamp": "2026-08-22T12:04:59+00:00"},
        account_state=account,
        limits={"max_data_age_seconds": 300.0},
        now_timestamp=now,
    )
    recent_loss = {
        "outcome": "LOSS",
        "status": "closed",
        "closed_timestamp": "2026-08-22T12:09:30+00:00",
    }
    cooldown = evaluate_risk_preview(
        base,
        account_state=account,
        closed_trades=[recent_loss],
        limits={"cooldown_after_loss_seconds": 120.0},
        now_timestamp=now,
    )
    same_open = {**other_open, "pair": "EURUSD", "status": "previewed"}
    duplicate = evaluate_risk_preview(
        base,
        account_state=account,
        open_trades=[same_open],
        limits={"max_open_trades": 10, "duplicate_setup_block": True},
        now_timestamp=now,
    )
    kill = evaluate_risk_preview(
        base,
        account_state={**account, "kill_switch_active": True},
        now_timestamp=now,
    )

    scenarios = {
        "per_trade_equal_boundary_allowed": per_trade_equal["allowed"] is True,
        "per_trade_excess_rejected": _has_reason(per_trade_excess, EXCESSIVE_RISK_PER_TRADE_REASON),
        "daily_loss_below_threshold_allowed": daily_below["allowed"] is True,
        "daily_loss_at_threshold_rejected": _has_reason(daily_at, MAX_DAILY_LOSS_HIT_REASON),
        "daily_loss_beyond_threshold_rejected": _has_reason(daily_beyond, MAX_DAILY_LOSS_HIT_REASON),
        "max_open_risk_rejected": _has_reason(open_risk, MAX_OPEN_RISK_HIT_REASON),
        "max_open_trades_rejected": _has_reason(open_trades, MAX_OPEN_TRADES_HIT_REASON),
        "max_pair_exposure_rejected": _has_reason(pair_exposure, MAX_PAIR_EXPOSURE_HIT_REASON),
        "spread_rejected": _has_reason(spread, SPREAD_TOO_HIGH_REASON),
        "stale_market_data_rejected": _has_reason(stale, STALE_MARKET_DATA_REASON),
        "cooldown_after_loss_rejected": _has_reason(cooldown, COOLDOWN_AFTER_LOSS_REASON),
        "duplicate_setup_rejected": _has_reason(duplicate, DUPLICATE_SETUP_REASON),
        "kill_switch_rejected": _has_reason(kill, KILL_SWITCH_ACTIVE_REASON),
    }
    return {
        "proof_pass": all(scenarios.values()),
        "scenarios": scenarios,
        "daily_loss_fixture_value_creates_authority": False,
        "unresolved_limit_fixture_values_create_authority": False,
        "paper_only": True,
        "network_calls": False,
        "broker_calls": False,
        "live_execution_enabled": False,
    }


def load_packet018a_result(path: Path = PACKET018A_RESULT_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("packet_id")
        != "PKT-EAST-FOREX-LIVE-READINESS-BLOCKER-CLOSURE-018A"
        or payload.get("readiness_gate_count") != 27
        or payload.get("readiness_pass_count_after") != 17
        or payload.get("readiness_fail_count_after") != 0
        or payload.get("readiness_pending_count_after") != 10
    ):
        raise ValueError(RISK_AUTHORITY_VALIDATION_FAILED)
    return payload


def recalculate_readiness(
    previous: Mapping[str, Any], risk_map: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """Recalculate only risk gates; future evidence and approval stay untouched."""

    matrix = copy.deepcopy(dict(previous.get("reevaluated_readiness_matrix", {})))
    if set(matrix) != set(hardening.READINESS_GATES) or len(matrix) != 27:
        raise ValueError(RISK_AUTHORITY_VALIDATION_FAILED)

    matrix["MAX_DRAWDOWN_STOP"]["status"] = "PASS"
    matrix["MAX_DRAWDOWN_STOP"]["evidence"] = {
        "status": risk_map["MAX_DRAWDOWN"]["status"],
        "value": risk_map["MAX_DRAWDOWN"]["value"],
        "unit": risk_map["MAX_DRAWDOWN"]["unit"],
        "authority_source": risk_map["MAX_DRAWDOWN"]["authority_source"],
    }
    matrix["DAILY_LOSS_STOP"]["status"] = "PENDING"
    matrix["DAILY_LOSS_STOP"]["blocker"] = "authoritative_numeric_daily_loss_threshold_missing"
    matrix["DAILY_LOSS_STOP"]["evidence"] = copy.deepcopy(risk_map["MAX_DAILY_LOSS"])
    matrix["KILL_SWITCH"]["status"] = "PENDING"
    matrix["KILL_SWITCH"]["blocker"] = [
        "credential_revoke_path_authority_missing",
        "notification_path_authority_missing",
    ]
    matrix["KILL_SWITCH"]["evidence"] = {
        "control_authority": copy.deepcopy(risk_map["KILL_SWITCH"]),
        "operational_declarations_complete": False,
    }

    counts = {
        status: sum(gate.get("status") == status for gate in matrix.values())
        for status in ("PASS", "FAIL", "PENDING", "NOT_YET_EVALUABLE")
    }
    if sum(counts.values()) != 27:
        raise ValueError(RISK_AUTHORITY_VALIDATION_FAILED)

    risk_failures_before = list(
        previous.get("live_readiness_review", {})
        .get("metadata", {})
        .get("risk_failures", [])
    )
    risk_failures_after = [
        "daily_loss_authoritative_value_missing",
        "max_open_risk_authoritative_value_missing",
        "max_pair_exposure_authoritative_value_missing",
        "max_spread_authoritative_value_missing",
        "kill_switch_credential_revoke_path_missing",
        "kill_switch_notification_path_missing",
    ]
    return {
        "matrix": matrix,
        "status_counts": counts,
        "readiness_pass_count_before": 17,
        "readiness_pass_count_after": counts["PASS"],
        "readiness_pending_count_before": 10,
        "readiness_pending_count_after": counts["PENDING"] + counts["NOT_YET_EVALUABLE"],
        "readiness_fail_count_before": 0,
        "readiness_fail_count_after": counts["FAIL"],
        "risk_failures_before": risk_failures_before,
        "risk_failures_after": risk_failures_after,
        "loss_streak_configuration_failure_removed_as_optional": (
            "loss_streak_threshold_not_configured" in risk_failures_before
            and "loss_streak_threshold_not_configured" not in risk_failures_after
        ),
        "paper_evidence_blocker_preserved": matrix["PAPER_EVIDENCE"]["status"] != "PASS",
        "demo_evidence_blocker_preserved": "demo_evidence_insufficient"
        in previous.get("live_readiness_blockers_after", []),
        "human_approval_blocker_preserved": matrix["HUMAN_APPROVAL"]["status"] != "PASS",
    }


def owner_risk_values_required(
    risk_map: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    items = [
        _owner_item("MAX_DAILY_LOSS", "ACCOUNT_CURRENCY", "Required by RISK_POLICY.md before any future live micro-trade review", True, "automation/forex_engine/forex_basket_risk_exposure_governor_v1.py defines a percentage ceiling only"),
        _owner_item("MAX_OPEN_RISK", "ACCOUNT_CURRENCY", "Existing governor support is disabled at 0.0 until configured", True, None),
        _owner_item("MAX_PAIR_EXPOSURE", "QUOTE_CURRENCY_NOTIONAL", "Existing governor support is disabled at 0.0 until configured", True, None),
        _owner_item("MAX_SPREAD", "PRICE_DISTANCE", "Existing governor support is disabled at 0.0 until configured", True, None),
        _owner_item("KILL_SWITCH_CREDENTIAL_REVOKE_PATH", "GOVERNED_PATH_DECLARATION", "Kill-switch readiness requires an explicit credential-revocation path", True, None),
        _owner_item("KILL_SWITCH_NOTIFICATION_PATH", "GOVERNED_PATH_DECLARATION", "Kill-switch readiness requires an explicit notification path", True, None),
    ]
    missing_controls = {
        name for name, item in risk_map.items() if item.get("status") == "MISSING_AUTHORITY"
    }
    if not {"MAX_DAILY_LOSS", "MAX_OPEN_RISK", "MAX_PAIR_EXPOSURE", "MAX_SPREAD"}.issubset(
        missing_controls
    ):
        raise ValueError(RISK_AUTHORITY_VALIDATION_FAILED)
    return items


def _owner_item(
    control_name: str,
    required_unit: str,
    why_required: str,
    current_implementation_support: bool,
    safe_range_source_if_authoritatively_defined: str | None,
) -> dict[str, Any]:
    return {
        "control_name": control_name,
        "required_unit": required_unit,
        "why_required": why_required,
        "current_implementation_support": current_implementation_support,
        "safe_range_source_if_authoritatively_defined": safe_range_source_if_authoritatively_defined,
    }


def build_report() -> dict[str, Any]:
    invariant_paths = {
        "paper30_runtime": PAPER30_RUNTIME_PATH,
        "paper30_ledger": PAPER30_LEDGER_PATH,
        "paper30_state": PAPER30_STATE_PATH,
    }
    pre_hashes = {name: _sha256_file(path) for name, path in invariant_paths.items()}
    ledger = json.loads(PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    state = json.loads(PAPER30_STATE_PATH.read_text(encoding="utf-8"))
    forward_pre = len(hardening.qualifying_forward_records(ledger))
    if forward_pre != 0 or state.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")

    source_proof = source_contract_proof()
    candidates = authority_candidates()
    analysis = analyze_authority_candidates(candidates)
    risk_map = canonical_risk_map(analysis)
    governor_proof = risk_governor_synthetic_proof()
    if not governor_proof["proof_pass"]:
        raise ValueError(RISK_AUTHORITY_VALIDATION_FAILED)
    previous = load_packet018a_result()
    readiness = recalculate_readiness(previous, risk_map)
    owner_required = owner_risk_values_required(risk_map)

    post_hashes = {name: _sha256_file(path) for name, path in invariant_paths.items()}
    ledger_post = json.loads(PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    forward_post = len(hardening.qualifying_forward_records(ledger_post))
    unchanged = pre_hashes == post_hashes and forward_pre == forward_post == 0
    if not unchanged:
        raise ValueError("PAPER30_FORWARD_STATE_CHANGED")

    classification = (
        "RISK_AUTHORITY_OWNER_VALUES_REQUIRED"
        if owner_required
        else "RISK_AUTHORITY_RESOLVED_FORWARD_EVIDENCE_PENDING"
    )
    source_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    result = {
        "packet_id": PACKET_ID,
        "lock_id": LOCK_ID,
        "source_head": source_head,
        "paper30_strategy_config_sha256": PAPER30_STRATEGY_CONFIG_SHA256,
        "source_contract_proof": source_proof,
        "authority_candidates": candidates,
        "authority_analysis": analysis,
        "canonical_risk_map": risk_map,
        "max_risk_per_trade_status": risk_map["MAX_RISK_PER_TRADE"]["status"],
        "max_risk_per_trade_value": risk_map["MAX_RISK_PER_TRADE"]["value"],
        "max_risk_per_trade_unit": risk_map["MAX_RISK_PER_TRADE"]["unit"],
        "max_daily_loss_status": risk_map["MAX_DAILY_LOSS"]["status"],
        "max_daily_loss_value": risk_map["MAX_DAILY_LOSS"]["value"],
        "max_daily_loss_unit": risk_map["MAX_DAILY_LOSS"]["unit"],
        "max_open_risk_status": risk_map["MAX_OPEN_RISK"]["status"],
        "max_open_risk_value": risk_map["MAX_OPEN_RISK"]["value"],
        "max_open_trades_status": risk_map["MAX_OPEN_TRADES"]["status"],
        "max_open_trades_value": risk_map["MAX_OPEN_TRADES"]["value"],
        "max_pair_exposure_status": risk_map["MAX_PAIR_EXPOSURE"]["status"],
        "max_pair_exposure_value": risk_map["MAX_PAIR_EXPOSURE"]["value"],
        "max_spread_status": risk_map["MAX_SPREAD"]["status"],
        "max_spread_value": risk_map["MAX_SPREAD"]["value"],
        "max_drawdown_status": risk_map["MAX_DRAWDOWN"]["status"],
        "max_drawdown_value": risk_map["MAX_DRAWDOWN"]["value"],
        "max_drawdown_authority_proven": risk_map["MAX_DRAWDOWN"]["status"] == "PROVEN",
        "loss_streak_control_required": False,
        "loss_streak_limit_status": risk_map["LOSS_STREAK_LIMIT"]["status"],
        "loss_streak_limit_value": risk_map["LOSS_STREAK_LIMIT"]["value"],
        "cooldown_control_required": False,
        "cooldown_status": risk_map["COOLDOWN_AFTER_LOSS"]["status"],
        "risk_authority_conflict_count": analysis["risk_authority_conflict_count"],
        "daily_loss_limit_found": risk_map["MAX_DAILY_LOSS"]["status"] == "PROVEN",
        "daily_loss_owner_decision_required": risk_map["MAX_DAILY_LOSS"]["status"] == "MISSING_AUTHORITY",
        "per_trade_risk_owner_decision_required": risk_map["MAX_RISK_PER_TRADE"]["status"] != "PROVEN",
        "owner_risk_values_required": owner_required,
        "risk_governor_synthetic_proof": governor_proof,
        "risk_governor_synthetic_proof_pass": governor_proof["proof_pass"],
        "readiness_recalculation": readiness,
        "readiness_pass_count_before": readiness["readiness_pass_count_before"],
        "readiness_pass_count_after": readiness["readiness_pass_count_after"],
        "readiness_pending_count_before": readiness["readiness_pending_count_before"],
        "readiness_pending_count_after": readiness["readiness_pending_count_after"],
        "readiness_fail_count_before": readiness["readiness_fail_count_before"],
        "readiness_fail_count_after": readiness["readiness_fail_count_after"],
        "risk_failures_before": readiness["risk_failures_before"],
        "risk_failures_after": readiness["risk_failures_after"],
        "paper30_invariant_pre_sha256": pre_hashes,
        "paper30_invariant_post_sha256": post_hashes,
        "paper30_forward_state_unchanged": unchanged,
        "forward_paper30_count_pre": forward_pre,
        "forward_paper30_count_post": forward_post,
        "human_live_approval": False,
        "live_execution_enabled": False,
        "network_calls": False,
        "broker_calls": False,
        "practice_orders": False,
        "live_orders": False,
        "broker_writes": False,
        "money_movement": False,
        "credentials_accessed": False,
        "audit_execution_count": 1,
        "risk_authority_classification": classification,
        "status": classification,
    }
    _assert_finite(result)
    json.dumps(result, sort_keys=True, allow_nan=False)
    return result


def run() -> dict[str, Any]:
    result = build_report()
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    report = run()
    print(json.dumps({"status": report["status"], "result_path": str(RESULT_PATH)}))
