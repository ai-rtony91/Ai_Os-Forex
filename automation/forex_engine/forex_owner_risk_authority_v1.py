"""Owner-approved, paper-only Forex risk authority and deterministic proof."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import copy
import hashlib
import json
import math
import subprocess
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from automation.forex_engine.live_kill_switch_readiness_engine import (
    STATUS_READY,
    evaluate_live_kill_switch_readiness,
)
from automation.forex_engine.live_readiness_review import review_live_readiness
from automation.forex_engine.risk_governor import (
    MAX_DAILY_LOSS_HIT_REASON,
    MAX_OPEN_RISK_HIT_REASON,
    MAX_OPEN_TRADES_HIT_REASON,
    evaluate_risk_preview,
)


ROOT = REPO_ROOT
PACKET_ID = "PKT-EAST-FOREX-OWNER-RISK-AUTHORITY-020"
LOCK_ID = "LOCK_EAST_FOREX_LIVE_READINESS_RESEARCH_EAST_OCC_01"
RESULT_PATH = ROOT / "Reports/forex_delivery/AIOS_FOREX_OWNER_RISK_AUTHORITY_V1_RESULTS.json"
PREVIOUS_READINESS_PATH = ROOT / "Reports/forex_delivery/AIOS_FOREX_LIVE_READINESS_BLOCKER_CLOSURE_V1_RESULTS.json"
PAPER30_RUNTIME_PATH = ROOT / "automation/forex_engine/forex_frozen_candidate_paper30_v1.py"
PAPER30_LEDGER_PATH = ROOT / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_LEDGER.json"
PAPER30_STATE_PATH = ROOT / ".aios/runtime/forex_frozen_candidate_paper30_v1/AIOS_FOREX_PAPER30_STATE.json"

PAPER30_STRATEGY_CONFIG_SHA256 = "13b96b3e227a2b5873ba5916a4987cf571868626339d1a89e2cd6e0e25bd1435"
MAX_RISK_PER_TRADE_PERCENT = 1.0
MAX_DAILY_LOSS_PERCENT = 2.0
MAX_OPEN_RISK_PERCENT = 1.0
MAX_OPEN_TRADES = 1
MAX_DRAWDOWN_PERCENT = 5.0
MAX_PAIR_EXPOSURE_POLICY = "RISK_DERIVED_FROM_1_PERCENT_ACCOUNT_EQUITY_AND_INITIAL_STOP_DISTANCE"
MAX_SPREAD_PIPS = 3.0
SPREAD_PRICE_NORMALIZATION_REQUIRED = True
KILL_SWITCH_CREDENTIAL_REVOKE_PATH = "GOVERNED_OPERATOR_BROKER_TOKEN_REVOCATION_PROCEDURE"
KILL_SWITCH_NOTIFICATION_PATH = "SANITIZED_LOCAL_AIOS_HUMAN_OWNER_ALERT"

OWNER_AUTHORITY_SOURCE = "HUMAN_OWNER_APPROVAL_PACKET_020"
PREEXISTING_AUTHORITY_SOURCE = "PREEXISTING_PROVEN_AUTHORITY"
OWNER_RISK_AUTHORITY_VALIDATION_FAILED = "OWNER_RISK_AUTHORITY_VALIDATION_FAILED"


@dataclass(frozen=True)
class OwnerRiskAuthority:
    max_risk_per_trade_percent: float = MAX_RISK_PER_TRADE_PERCENT
    max_daily_loss_percent: float = MAX_DAILY_LOSS_PERCENT
    max_open_risk_percent: float = MAX_OPEN_RISK_PERCENT
    max_open_trades: int = MAX_OPEN_TRADES
    max_drawdown_percent: float = MAX_DRAWDOWN_PERCENT
    max_pair_exposure_policy: str = MAX_PAIR_EXPOSURE_POLICY
    max_spread_pips: float = MAX_SPREAD_PIPS
    spread_price_normalization_required: bool = SPREAD_PRICE_NORMALIZATION_REQUIRED
    paper_only: bool = True
    live_enabled: bool = False
    broker_writes: bool = False


AUTHORITY = OwnerRiskAuthority()


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name}_INVALID")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}_INVALID") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name}_INVALID")
    return number


def _nonnegative_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name}_INVALID")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}_INVALID") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name}_INVALID")
    return number


def daily_loss_budget(account_equity: Any) -> float:
    return round(_positive_number(account_equity, "ACCOUNT_EQUITY") * MAX_DAILY_LOSS_PERCENT / 100.0, 10)


def open_risk_budget(account_equity: Any) -> float:
    return round(_positive_number(account_equity, "ACCOUNT_EQUITY") * MAX_OPEN_RISK_PERCENT / 100.0, 10)


def remaining_open_risk_capacity(account_equity: Any, current_open_risk: Any) -> float:
    used = _nonnegative_number(current_open_risk, "CURRENT_OPEN_RISK")
    return round(max(0.0, open_risk_budget(account_equity) - used), 10)


def _valid_preview(*, dollar_risk: float, spread: float = 0.0) -> dict[str, Any]:
    return {
        "pair": "EUR-USD",
        "direction": "buy",
        "entry_price": 1.1000,
        "stop_loss": 1.0950,
        "take_profit": 1.1100,
        "units": 1000,
        "dollar_risk": dollar_risk,
        "percent_risk": 0.5,
        "spread": spread,
        "paper_only": True,
        "mode": "PAPER_ONLY",
        "data_timestamp": "2026-08-22T12:00:00Z",
    }


def evaluate_daily_loss(
    account_equity: Any,
    cumulative_loss: Any,
    applicable_protected_loss: Any = 0.0,
) -> dict[str, Any]:
    equity = _positive_number(account_equity, "ACCOUNT_EQUITY")
    used = _nonnegative_number(cumulative_loss, "CUMULATIVE_LOSS")
    protected = _nonnegative_number(applicable_protected_loss, "APPLICABLE_PROTECTED_LOSS")
    budget = daily_loss_budget(equity)
    result = evaluate_risk_preview(
        _valid_preview(dollar_risk=protected),
        account_state={"equity": equity, "daily_loss_used": used},
        limits={
            "max_risk_per_trade_pct": MAX_RISK_PER_TRADE_PERCENT,
            "max_daily_loss": budget,
            "max_open_trades": MAX_OPEN_TRADES,
        },
        now_timestamp="2026-08-22T12:00:00Z",
    )
    blocked = MAX_DAILY_LOSS_HIT_REASON in result["blocked_reasons"]
    return {
        "allowed_by_daily_loss_gate": not blocked,
        "blocked": blocked,
        "blocked_reason": MAX_DAILY_LOSS_HIT_REASON if blocked else "none",
        "budget": budget,
        "loss_after": round(used + protected, 10),
        "trading_day_reset": "EXPLICIT_AUTHORITATIVE_NEXT_TRADING_DAY_BOUNDARY_ONLY",
    }


def evaluate_open_risk(
    account_equity: Any,
    current_open_risk: Any,
    proposed_initial_risk: Any,
    *,
    active_trade_count: int = 0,
) -> dict[str, Any]:
    equity = _positive_number(account_equity, "ACCOUNT_EQUITY")
    current = _nonnegative_number(current_open_risk, "CURRENT_OPEN_RISK")
    proposed = _positive_number(proposed_initial_risk, "PROPOSED_INITIAL_RISK")
    if isinstance(active_trade_count, bool) or not isinstance(active_trade_count, int) or active_trade_count < 0:
        raise ValueError("ACTIVE_TRADE_COUNT_INVALID")
    budget = open_risk_budget(equity)
    open_trades = [
        {
            "pair": f"PAIR_{index}",
            "direction": "buy",
            "status": "active",
            "units": 1,
            "entry_price": 1,
        }
        for index in range(active_trade_count)
    ]
    preview = _valid_preview(dollar_risk=proposed)
    preview["percent_risk"] = proposed / equity * 100.0
    result = evaluate_risk_preview(
        preview,
        account_state={"equity": equity, "open_risk": current},
        open_trades=open_trades,
        limits={
            "max_risk_per_trade_pct": MAX_RISK_PER_TRADE_PERCENT,
            "max_open_risk": budget,
            "max_open_trades": MAX_OPEN_TRADES,
        },
        now_timestamp="2026-08-22T12:00:00Z",
    )
    relevant = [
        reason
        for reason in result["blocked_reasons"]
        if reason in {MAX_OPEN_RISK_HIT_REASON, MAX_OPEN_TRADES_HIT_REASON}
    ]
    return {
        "allowed_by_open_risk_gates": not relevant,
        "blocked": bool(relevant),
        "blocked_reasons": relevant,
        "budget": budget,
        "open_risk_after": round(current + proposed, 10),
        "remaining_capacity_before": remaining_open_risk_capacity(equity, current),
        "max_open_trades": MAX_OPEN_TRADES,
    }


def normalize_instrument(instrument: Any) -> str:
    normalized = str(instrument).strip().upper().replace("/", "_").replace("-", "_")
    if "_" not in normalized and len(normalized) == 6:
        normalized = normalized[:3] + "_" + normalized[3:]
    parts = normalized.split("_")
    if len(parts) != 2 or any(len(part) != 3 or not part.isalpha() for part in parts):
        raise ValueError("INSTRUMENT_FORMAT_UNSUPPORTED")
    return normalized


def pip_size_for_instrument(instrument: Any) -> float:
    quote = normalize_instrument(instrument).split("_")[1]
    return 0.01 if quote == "JPY" else 0.0001


def spread_price_distance_to_pips(instrument: Any, spread_price_distance: Any) -> float:
    spread = _nonnegative_number(spread_price_distance, "SPREAD_PRICE_DISTANCE")
    return round(spread / pip_size_for_instrument(instrument), 10)


def evaluate_spread(instrument: Any, spread_price_distance: Any) -> dict[str, Any]:
    normalized = normalize_instrument(instrument)
    pips = spread_price_distance_to_pips(normalized, spread_price_distance)
    blocked = pips > MAX_SPREAD_PIPS + 1e-9
    return {
        "instrument": normalized,
        "pip_size": pip_size_for_instrument(normalized),
        "spread_price_distance": float(spread_price_distance),
        "spread_pips": pips,
        "max_spread_pips": MAX_SPREAD_PIPS,
        "blocked": blocked,
        "blocked_reason": "spread_too_high" if blocked else "none",
    }


def derive_risk_position(
    account_equity: Any,
    instrument: Any,
    entry_price: Any,
    initial_stop: Any,
) -> dict[str, Any]:
    equity = _positive_number(account_equity, "ACCOUNT_EQUITY")
    entry = _positive_number(entry_price, "ENTRY_PRICE")
    stop = _positive_number(initial_stop, "INITIAL_STOP")
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        raise ValueError("INVALID_STOP_DISTANCE")
    normalized = normalize_instrument(instrument)
    budget = open_risk_budget(equity)
    units = budget / stop_distance
    calculated_initial_risk = units * stop_distance
    if calculated_initial_risk > budget + 1e-8:
        raise ValueError("RISK_DERIVATION_EXCEEDS_BUDGET")
    return {
        "instrument": normalized,
        "account_equity": equity,
        "risk_budget": round(budget, 10),
        "risk_budget_percent": MAX_OPEN_RISK_PERCENT,
        "entry_price": entry,
        "initial_stop": stop,
        "stop_distance_price": round(stop_distance, 10),
        "stop_distance_pips": round(stop_distance / pip_size_for_instrument(normalized), 10),
        "units": round(units, 10),
        "risk_derived_notional": round(units * entry, 10),
        "calculated_initial_risk": round(calculated_initial_risk, 10),
        "policy": MAX_PAIR_EXPOSURE_POLICY,
        "broker_leverage_used": False,
    }


def kill_switch_metadata() -> dict[str, bool]:
    return {
        "kill_switch_declared": True,
        "manual_operator_stop_declared": True,
        "max_daily_loss_stop_declared": True,
        "max_drawdown_stop_declared": True,
        "emergency_disable_declared": True,
        "credential_revoke_path_declared": True,
        "audit_logging_declared": True,
        "notification_path_declared": True,
        "operator_override_declared": True,
        "paper_only_review": True,
    }


def kill_switch_readiness_proof() -> dict[str, Any]:
    result = evaluate_live_kill_switch_readiness(kill_switch_metadata())
    return {
        "credential_revoke_path": KILL_SWITCH_CREDENTIAL_REVOKE_PATH,
        "notification_path": KILL_SWITCH_NOTIFICATION_PATH,
        "credential_revoke_path_declared": True,
        "notification_path_declared": True,
        "actual_credential_revoked": False,
        "external_notification_sent": False,
        "result": result,
        "proof_pass": result["kill_switch_status"] == STATUS_READY and result["kill_switch_ready"] is True,
    }


def canonical_risk_map() -> dict[str, dict[str, Any]]:
    def entry(status: str, value: Any, unit: str, source: str, implementation: str) -> dict[str, Any]:
        return {
            "status": status,
            "value": value,
            "unit": unit,
            "authority_source": source,
            "implementation_source": implementation,
            "synthetic_test_available": status in {"PROVEN", "PROVEN_POLICY"},
        }

    owner = "docs/trading_lab/forex/AIOS_FOREX_OWNER_RISK_AUTHORITY_V1.md"
    return {
        "MAX_RISK_PER_TRADE": entry("PROVEN", 1.0, "PERCENT_ACCOUNT_EQUITY", PREEXISTING_AUTHORITY_SOURCE, "automation/forex_engine/risk_governor.py"),
        "MAX_DAILY_LOSS": entry("PROVEN", 2.0, "PERCENT_ACCOUNT_EQUITY", owner, "automation/forex_engine/risk_governor.py"),
        "MAX_OPEN_RISK": entry("PROVEN", 1.0, "PERCENT_ACCOUNT_EQUITY", owner, "automation/forex_engine/risk_governor.py"),
        "MAX_OPEN_TRADES": entry("PROVEN", 1, "COUNT", PREEXISTING_AUTHORITY_SOURCE, "automation/forex_engine/risk_governor.py"),
        "MAX_PAIR_EXPOSURE": entry("PROVEN_POLICY", MAX_PAIR_EXPOSURE_POLICY, "RISK_DERIVED", owner, __file__),
        "MAX_SPREAD": entry("PROVEN", 3.0, "PIPS_INSTRUMENT_NORMALIZED", owner, __file__),
        "MAX_DRAWDOWN": entry("PROVEN", 5.0, "PERCENT", PREEXISTING_AUTHORITY_SOURCE, "automation/forex_engine/risk_management.py"),
        "KILL_SWITCH": entry("PROVEN", "PROCEDURAL_DECLARATIONS_COMPLETE", "BOOLEAN_CONTROL_SET", owner, "automation/forex_engine/live_kill_switch_readiness_engine.py"),
        "LOSS_STREAK_LIMIT": entry("NOT_APPLICABLE", None, "CONSECUTIVE_LOSSES", PREEXISTING_AUTHORITY_SOURCE, "automation/forex_engine/risk_management.py"),
        "COOLDOWN_AFTER_LOSS": entry("NOT_APPLICABLE", None, "SECONDS", PREEXISTING_AUTHORITY_SOURCE, "automation/forex_engine/risk_governor.py"),
    }


def _load_previous_readiness() -> dict[str, Any]:
    payload = json.loads(PREVIOUS_READINESS_PATH.read_text(encoding="utf-8"))
    if (
        payload.get("packet_id") != "PKT-EAST-FOREX-LIVE-READINESS-BLOCKER-CLOSURE-018A"
        or payload.get("readiness_gate_count") != 27
        or payload.get("readiness_pass_count_after") != 17
        or payload.get("readiness_fail_count_after") != 0
        or payload.get("readiness_pending_count_after") != 10
    ):
        raise ValueError(OWNER_RISK_AUTHORITY_VALIDATION_FAILED)
    return payload


def recalculate_readiness(previous: Mapping[str, Any]) -> dict[str, Any]:
    matrix = copy.deepcopy(dict(previous.get("reevaluated_readiness_matrix", {})))
    if len(matrix) != 27:
        raise ValueError(OWNER_RISK_AUTHORITY_VALIDATION_FAILED)
    matrix["DAILY_LOSS_STOP"] = {
        "status": "PASS",
        "blocker": None,
        "evidence": canonical_risk_map()["MAX_DAILY_LOSS"],
        "next_safe_action": "retain_owner_approved_two_percent_daily_entry_stop",
    }
    kill_proof = kill_switch_readiness_proof()
    matrix["KILL_SWITCH"] = {
        "status": "PASS",
        "blocker": None,
        "evidence": kill_proof,
        "next_safe_action": "retain_procedural_kill_switch_readiness_and_human_control",
    }
    counts = {
        status: sum(gate.get("status") == status for gate in matrix.values())
        for status in ("PASS", "FAIL", "PENDING", "NOT_YET_EVALUABLE")
    }
    if sum(counts.values()) != 27:
        raise ValueError(OWNER_RISK_AUTHORITY_VALIDATION_FAILED)

    live_review = review_live_readiness(
        {"allowed": False, "demo_promotion_ready": False},
        {"allowed": False, "mode": "DEMO_RUN_PLAN_ONLY"},
        {"allowed": True, "matched": True, "match_score": 1.0, "mode": "DEMO_RECONCILIATION_ONLY"},
        {},
        {},
        {"max_drawdown_pct": 0.0, "risk_failures": []},
        {"verified": True},
        human_approval=False,
        limits={"maximum_drawdown_pct": MAX_DRAWDOWN_PERCENT},
        metadata={"owner_risk_authority": PACKET_ID},
    )
    expected_blockers = {
        "human_approval_missing",
        "paper_evidence_insufficient",
        "demo_evidence_insufficient",
    }
    if set(live_review["blocked_reasons"]) != expected_blockers or live_review["allowed"] is not False:
        raise ValueError(OWNER_RISK_AUTHORITY_VALIDATION_FAILED)
    return {
        "matrix": matrix,
        "status_counts": counts,
        "readiness_gate_count": 27,
        "readiness_pass_count_before": 17,
        "readiness_pass_count_after": counts["PASS"],
        "readiness_fail_count_after": counts["FAIL"],
        "readiness_pending_count_after": counts["PENDING"] + counts["NOT_YET_EVALUABLE"],
        "live_readiness_score_before": 0.4,
        "live_readiness_score_after": live_review["readiness_score"],
        "live_readiness_blockers_after": live_review["blocked_reasons"],
        "live_readiness_review": live_review,
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_paper30_state() -> tuple[dict[str, Any], dict[str, Any]]:
    state = json.loads(PAPER30_STATE_PATH.read_text(encoding="utf-8"))
    ledger = json.loads(PAPER30_LEDGER_PATH.read_text(encoding="utf-8"))
    if (
        state.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256
        or ledger.get("strategy_config_sha256") != PAPER30_STRATEGY_CONFIG_SHA256
        or ledger.get("schema") != "AIOS_FOREX_FROZEN_CANDIDATE_PAPER30_V1"
        or not isinstance(ledger.get("trades"), list)
    ):
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")
    return state, ledger


def _forward_count(ledger: Mapping[str, Any]) -> int:
    records = ledger.get("trades")
    if not isinstance(records, list):
        raise ValueError("PAPER30_LEDGER_SCHEMA_UNSUPPORTED")
    return sum(
        1
        for record in records
        if isinstance(record, Mapping)
        and record.get("qualifying") is True
        and record.get("exit_timestamp_utc")
        and record.get("realized_r") is not None
    )


def synthetic_proof() -> dict[str, Any]:
    daily = {
        "equity_10000_below": evaluate_daily_loss(10_000, 199.99),
        "equity_10000_at": evaluate_daily_loss(10_000, 200.0),
        "equity_10000_above": evaluate_daily_loss(10_000, 201.0),
        "equity_25000_at": evaluate_daily_loss(25_000, 500.0),
    }
    open_risk = {
        "zero": evaluate_open_risk(10_000, 0.0, 50.0),
        "half": evaluate_open_risk(10_000, 50.0, 49.99),
        "at": evaluate_open_risk(10_000, 100.0, 0.01),
        "above": evaluate_open_risk(10_000, 101.0, 0.01),
        "second_trade": evaluate_open_risk(10_000, 50.0, 25.0, active_trade_count=1),
    }
    spread = {
        "non_jpy_at": evaluate_spread("EUR_USD", 0.0003),
        "non_jpy_above": evaluate_spread("EUR_USD", 0.00031),
        "jpy_at": evaluate_spread("USD_JPY", 0.03),
        "jpy_above": evaluate_spread("USD_JPY", 0.031),
    }
    position = derive_risk_position(10_000, "EUR_USD", 1.1, 1.095)
    kill = kill_switch_readiness_proof()
    passed = (
        daily["equity_10000_below"]["blocked"] is False
        and daily["equity_10000_at"]["blocked_reason"] == MAX_DAILY_LOSS_HIT_REASON
        and daily["equity_10000_above"]["blocked"] is True
        and daily["equity_25000_at"]["blocked"] is True
        and open_risk["zero"]["blocked"] is False
        and open_risk["half"]["remaining_capacity_before"] == 50.0
        and MAX_OPEN_RISK_HIT_REASON in open_risk["at"]["blocked_reasons"]
        and MAX_OPEN_RISK_HIT_REASON in open_risk["above"]["blocked_reasons"]
        and MAX_OPEN_TRADES_HIT_REASON in open_risk["second_trade"]["blocked_reasons"]
        and spread["non_jpy_at"]["blocked"] is False
        and spread["jpy_at"]["blocked"] is False
        and spread["non_jpy_above"]["blocked_reason"] == "spread_too_high"
        and spread["jpy_above"]["blocked_reason"] == "spread_too_high"
        and position["calculated_initial_risk"] <= position["risk_budget"]
        and kill["proof_pass"] is True
    )
    return {
        "proof_pass": passed,
        "daily_loss": daily,
        "open_risk": open_risk,
        "spread": spread,
        "position_exposure": position,
        "kill_switch": kill,
    }


def _assert_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("NONFINITE_RESULT")
    if isinstance(value, Mapping):
        for nested in value.values():
            _assert_finite(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_finite(nested)


def build_report() -> dict[str, Any]:
    invariant_paths = {
        "paper30_runtime": PAPER30_RUNTIME_PATH,
        "paper30_ledger": PAPER30_LEDGER_PATH,
        "paper30_state": PAPER30_STATE_PATH,
    }
    pre_hashes = {name: _sha256_file(path) for name, path in invariant_paths.items()}
    state, ledger = _load_paper30_state()
    forward_pre = _forward_count(ledger)
    if forward_pre != 0:
        raise ValueError("PAPER30_STRATEGY_STATE_MISMATCH")

    proof = synthetic_proof()
    if not proof["proof_pass"]:
        raise ValueError(OWNER_RISK_AUTHORITY_VALIDATION_FAILED)
    risk_map = canonical_risk_map()
    if any(item["status"] == "MISSING_AUTHORITY" for item in risk_map.values()):
        classification = "OWNER_RISK_AUTHORITY_PARTIAL_BLOCKERS_REMAIN"
    else:
        classification = "OWNER_RISK_AUTHORITY_ESTABLISHED_FORWARD_EVIDENCE_PENDING"
    readiness = recalculate_readiness(_load_previous_readiness())

    post_hashes = {name: _sha256_file(path) for name, path in invariant_paths.items()}
    state_post, ledger_post = _load_paper30_state()
    forward_post = _forward_count(ledger_post)
    unchanged = (
        pre_hashes == post_hashes
        and state == state_post
        and ledger == ledger_post
        and forward_pre == forward_post == 0
    )
    if not unchanged:
        raise ValueError("PAPER30_FORWARD_STATE_CHANGED")

    source_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = {
        "packet_id": PACKET_ID,
        "lock_id": LOCK_ID,
        "source_head": source_head,
        "owner_risk_authority": asdict(AUTHORITY),
        "paper30_strategy_config_sha256": PAPER30_STRATEGY_CONFIG_SHA256,
        "canonical_risk_map": risk_map,
        "max_pair_exposure_policy": MAX_PAIR_EXPOSURE_POLICY,
        "max_spread_pips": MAX_SPREAD_PIPS,
        "kill_switch_credential_revoke_path_status": "PROCEDURE_AUTHORITY_PROVEN",
        "kill_switch_notification_path_status": "LOCAL_SANITIZED_ALERT_AUTHORITY_PROVEN",
        "kill_switch_status": proof["kill_switch"]["result"]["kill_switch_status"],
        "risk_configuration_complete": all(
            item["status"] in {"PROVEN", "PROVEN_POLICY", "NOT_APPLICABLE"}
            for item in risk_map.values()
        ),
        "synthetic_proof": proof,
        "readiness_recalculation": readiness,
        "readiness_pass_count_before": readiness["readiness_pass_count_before"],
        "readiness_pass_count_after": readiness["readiness_pass_count_after"],
        "readiness_fail_count_after": readiness["readiness_fail_count_after"],
        "readiness_pending_count_after": readiness["readiness_pending_count_after"],
        "live_readiness_score_before": readiness["live_readiness_score_before"],
        "live_readiness_score_after": readiness["live_readiness_score_after"],
        "live_readiness_blockers_after": readiness["live_readiness_blockers_after"],
        "paper30_invariant_pre_sha256": pre_hashes,
        "paper30_invariant_post_sha256": post_hashes,
        "forward_paper30_count_pre": forward_pre,
        "forward_paper30_count_post": forward_post,
        "paper30_forward_state_unchanged": unchanged,
        "human_live_approval": False,
        "live_execution_enabled": False,
        "broker_writes": False,
        "network_calls": False,
        "broker_calls": False,
        "practice_orders": False,
        "live_orders": False,
        "money_movement": False,
        "credentials_accessed": False,
        "credentials_persisted": False,
        "account_identifiers_persisted": False,
        "audit_execution_count": 1,
        "status": classification,
    }
    _assert_finite(report)
    json.dumps(report, sort_keys=True, allow_nan=False)
    return report


def run() -> dict[str, Any]:
    report = build_report()
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({"status": result["status"], "result_path": str(RESULT_PATH)}))
