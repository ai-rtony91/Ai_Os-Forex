"""Finite local-only controller for one supervised P1 paper position."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from automation.forex_engine.forex_p1_supervised_paper_capture_replay_v1 import run_capture_replay
from automation.forex_engine.strategies import (
    classify_r_multiple,
    planned_reward_risk,
    realized_r_multiple,
)

VERSION = "forex_p1_supervised_paper_session_v1"
SNAPSHOT_SCHEMA = "AIOS_P1_SUPERVISED_PAPER_MARKET_SNAPSHOT.v1"
SUPPORTED_INSTRUMENTS = {"EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "USD_CHF", "NZD_USD"}
MAX_UNITS = 1_000_000
SAFETY_FLAGS = {
    "broker_call_performed": False, "broker_write_performed": False,
    "credentials_loaded": False, "account_access_performed": False,
    "order_submission_allowed": False, "order_modification_allowed": False,
    "order_close_allowed": False, "demo_execution_allowed": False,
    "live_execution_allowed": False, "money_movement_allowed": False,
    "margin_use_allowed": False, "scheduler_created": False,
    "daemon_created": False, "webhook_created": False,
    "continuous_execution_allowed": False,
}
NON_GENUINE = re.compile(r"(?i)\b(fixture|mock|synthetic|generated|backtest|narrative|example|private screenshot)\b")
PRIVATE_KEYS = re.compile(r"(?i)(password|secret|token|api[_ -]?key|transaction[_ -]?id|broker[_ -]?order[_ -]?id)")


def stable_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("explicit_utc_timestamp_required")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("invalid_utc_timestamp") from exc


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"invalid_{name}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_{name}") from exc
    if not math.isfinite(result):
        raise ValueError(f"non_finite_{name}")
    return result


def _reject_unsafe(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            safe_boolean = normalized in {"credentials_included", "account_identifier_included", "raw_payload_included"} and child is False
            if (PRIVATE_KEYS.search(normalized) or normalized in {"account_id", "account_identifier", "raw_payload", "raw_broker_payload", "broker_payload"}) and not safe_boolean:
                raise ValueError("secret_private_or_non_genuine_content_rejected")
            _reject_unsafe(child)
    elif isinstance(value, (list, tuple)):
        for child in value: _reject_unsafe(child)
    elif isinstance(value, str) and NON_GENUINE.search(value):
        raise ValueError("secret_private_or_non_genuine_content_rejected")


def validate_market_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    required = ("schema", "evidence_type", "provenance", "instrument", "observed_at_utc", "bid", "ask", "mid", "spread", "source_status", "stale_status", "read_only", "broker_write_performed", "credentials_included", "account_identifier_included", "raw_payload_included")
    if not isinstance(snapshot, Mapping) or any(key not in snapshot for key in required):
        raise ValueError("invalid_snapshot_schema")
    _reject_unsafe(snapshot)
    expected = {
        "schema": SNAPSHOT_SCHEMA, "evidence_type": "SANITIZED_READ_ONLY_MARKET_SNAPSHOT",
        "provenance": "GENUINE_OBSERVED_MARKET_DATA", "source_status": "VALID",
        "stale_status": "VALID", "read_only": True, "broker_write_performed": False,
        "credentials_included": False, "account_identifier_included": False,
        "raw_payload_included": False,
    }
    if any(snapshot.get(key) != value for key, value in expected.items()):
        raise ValueError("invalid_or_unsafe_snapshot_contract")
    if snapshot["instrument"] not in SUPPORTED_INSTRUMENTS:
        raise ValueError("unsupported_instrument")
    _utc(snapshot["observed_at_utc"])
    bid, ask, mid, spread = (_number(snapshot[name], name) for name in ("bid", "ask", "mid", "spread"))
    if bid <= 0 or ask <= 0 or ask < bid or not bid <= mid <= ask:
        raise ValueError("invalid_market_prices")
    if not math.isclose(spread, ask - bid, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("spread_mismatch")
    return {**dict(snapshot), "bid": bid, "ask": ask, "mid": mid, "spread": spread}


def _candidate(candidate: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    _reject_unsafe(candidate)
    false_flags = ("broker_call_performed", "broker_write_performed", "live_execution_allowed", "demo_execution_allowed", "order_submission_allowed", "credentials_included", "account_identifier_included")
    required = ("strategy_id", "candidate_id", "instrument", "direction", "units", "stop_price", "target_price", "risk_amount", "entry_rationale", "status", "sanitized", "current")
    if any(key not in candidate for key in required) or candidate.get("status") != "PAPER_ELIGIBLE" or candidate.get("sanitized") is not True or candidate.get("current") is not True or any(candidate.get(key, False) is not False for key in false_flags):
        raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    direction = str(candidate["direction"]).upper()
    if candidate["instrument"] != snapshot["instrument"] or direction not in {"BUY", "SELL"}:
        raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    strategy_id = str(candidate["strategy_id"]).strip()
    strategy_name = str(candidate.get("strategy_name") or strategy_id).strip()
    if not strategy_id or not strategy_name or strategy_name != strategy_id:
        raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    if str(candidate.get("mode", "PAPER_ONLY")).upper() != "PAPER_ONLY":
        raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    if candidate.get("paper_only", True) is not True:
        raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    strategy_config = candidate.get("strategy_config")
    if strategy_config is not None and not isinstance(strategy_config, Mapping):
        raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    units = candidate["units"]
    if isinstance(units, bool) or not isinstance(units, int) or not 0 < units <= MAX_UNITS:
        raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    stop, target, risk = (_number(candidate[name], name) for name in ("stop_price", "target_price", "risk_amount"))
    entry_price = snapshot["ask"] if direction == "BUY" else snapshot["bid"]
    if direction == "BUY":
        geometry_valid = stop < entry_price < target
    else:
        geometry_valid = target < entry_price < stop
    if not geometry_valid or risk <= 0:
        raise ValueError("NO_PAPER_TRADE_CANDIDATE")
    normalized = {
        **dict(candidate),
        "direction": direction,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "mode": "PAPER_ONLY",
        "paper_only": True,
        "stop_price": stop,
        "target_price": target,
        "risk_amount": risk,
    }
    if strategy_config is not None:
        normalized["strategy_config"] = dict(strategy_config)
    return normalized


def load_active_session(runtime_path: Path) -> dict[str, Any] | None:
    if not runtime_path.exists():
        return None
    value = json.loads(runtime_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid_active_session")
    status = value.get("status")
    if status == "ACTIVE":
        return value
    if status == "CLOSED":
        if value.get("schema") != "AIOS_P1_SUPERVISED_PAPER_SESSION.v1":
            raise ValueError("invalid_active_session")
        closed_at = value.get("closed_at_utc")
        closed_reason = value.get("closed_reason")
        if (
            not isinstance(closed_at, str)
            or not closed_at.endswith("Z")
            or not isinstance(closed_reason, str)
            or not closed_reason.strip()
        ):
            raise ValueError("invalid_active_session")
        for key in ("strategy_id", "strategy_name"):
            if key in value and (not isinstance(value[key], str) or not value[key].strip()):
                raise ValueError("invalid_active_session")
        return None
    raise ValueError("invalid_active_session")


def open_paper_session(snapshot: Mapping[str, Any], candidate: Mapping[str, Any], reviewer_identity: str, as_of_utc: str, runtime_path: Path) -> dict[str, Any]:
    snap = validate_market_snapshot(snapshot); item = _candidate(candidate, snap); _utc(as_of_utc)
    if not reviewer_identity.strip(): raise ValueError("owner_reviewer_required")
    direction = str(item["direction"]).upper()
    entry_price = snap["ask"] if direction == "BUY" else snap["bid"]
    if direction == "BUY":
        mfe_price = snap["bid"]
        mae_price = snap["bid"]
    else:
        mfe_price = snap["ask"]
        mae_price = snap["ask"]
    session = {
        "schema": "AIOS_P1_SUPERVISED_PAPER_SESSION.v1", "status": "ACTIVE",
        "strategy_id": item["strategy_id"], "strategy_name": item["strategy_name"],
        "mode": item["mode"], "paper_only": item["paper_only"],
        "candidate_id": item["candidate_id"],
        "instrument": snap["instrument"], "direction": direction, "units": item["units"],
        "entry_timestamp": snap["observed_at_utc"], "entry_price": entry_price,
        "stop_price": item["stop_price"], "target_price": item["target_price"],
        "risk_amount": item["risk_amount"], "entry_rationale": item["entry_rationale"],
        "owner_supervision_confirmed": True, "reviewer_identity": reviewer_identity,
        "opened_as_of_utc": as_of_utc, **SAFETY_FLAGS,
        "mfe_price": mfe_price, "mae_price": mae_price,
        "mfe_timestamp_utc": snap["observed_at_utc"],
        "mae_timestamp_utc": snap["observed_at_utc"],
    }
    if "strategy_config" in item:
        session["strategy_config"] = item["strategy_config"]
    active = load_active_session(runtime_path)
    if active:
        if active == session: return active
        raise ValueError("conflicting_active_session")
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(stable_json(session), encoding="utf-8")
    return session


def update_paper_session_extremes(snapshot: Mapping[str, Any], runtime_path: Path) -> dict[str, Any]:
    """Persist observed MFE/MAE inputs for the open session."""
    active = load_active_session(runtime_path)
    if not active:
        raise ValueError("no_active_session")
    snap = validate_market_snapshot(snapshot)
    if snap["instrument"] != active["instrument"]:
        raise ValueError("active_instrument_mismatch")
    direction = str(active.get("direction", "BUY")).upper()
    if direction == "BUY":
        favorable_price = snap["bid"]
        adverse_price = snap["bid"]
        better_favorable = lambda current, new: new > current
        better_adverse = lambda current, new: new < current
    else:
        favorable_price = snap["ask"]
        adverse_price = snap["ask"]
        better_favorable = lambda current, new: new < current
        better_adverse = lambda current, new: new > current
    mfe = float(active.get("mfe_price", favorable_price))
    mae = float(active.get("mae_price", adverse_price))
    if better_favorable(mfe, favorable_price):
        active["mfe_price"] = favorable_price
        active["mfe_timestamp_utc"] = snap["observed_at_utc"]
    if better_adverse(mae, adverse_price):
        active["mae_price"] = adverse_price
        active["mae_timestamp_utc"] = snap["observed_at_utc"]
    runtime_path.write_text(stable_json(active), encoding="utf-8")
    return active


def calculate_conservative_paper_result(session: Mapping[str, Any], closing_snapshot: Mapping[str, Any], fees: float = 0.0) -> dict[str, float]:
    direction = str(session.get("direction", "BUY")).upper()
    exit_price = _number(closing_snapshot["bid"] if direction == "BUY" else closing_snapshot["ask"], "exit_price")
    cost = _number(fees, "fees")
    if cost < 0: raise ValueError("invalid_fees")
    entry_price = _number(session["entry_price"], "entry_price")
    gross = round(((exit_price - entry_price) if direction == "BUY" else (entry_price - exit_price)) * int(session["units"]), 8)
    return {"entry_price": float(session["entry_price"]), "exit_price": exit_price, "gross_pl": gross, "fees": cost, "net_pl": round(gross - cost, 8)}


def build_completed_trade_record(session: Mapping[str, Any], closing_snapshot: Mapping[str, Any], exit_reason: str, reviewer_identity: str, review_utc: str, fees: float = 0.0) -> dict[str, Any]:
    snap = validate_market_snapshot(closing_snapshot)
    if snap["instrument"] != session["instrument"]: raise ValueError("closing_instrument_mismatch")
    if _utc(snap["observed_at_utc"]) <= _utc(session["entry_timestamp"]): raise ValueError("exit_must_follow_entry")
    if _utc(review_utc) < _utc(snap["observed_at_utc"]): raise ValueError("review_precedes_exit")
    result = calculate_conservative_paper_result(session, snap, fees)
    direction = str(session.get("direction", "BUY")).upper()
    base = {
        "strategy_id": session["strategy_id"],
        "strategy_name": session.get("strategy_name", session["strategy_id"]),
        "mode": session.get("mode", "PAPER_ONLY"),
        "paper_only": session.get("paper_only", True),
        "candidate_id": session["candidate_id"], "evidence_type": "paper",
        "instrument": session["instrument"], "direction": direction, "entry_timestamp_utc": session["entry_timestamp"],
        "exit_timestamp_utc": snap["observed_at_utc"], "entry_price": result["entry_price"], "exit_price": result["exit_price"],
        "stop_price": session["stop_price"], "target_price": session["target_price"], "quantity_or_units": session["units"],
        "realized_pl": result["net_pl"], "fees": result["fees"], "risk_amount": session["risk_amount"],
        "entry_rationale": session["entry_rationale"], "exit_reason": exit_reason, "evidence_source": "sanitized_supervised_paper_session",
        "reviewed_by": reviewer_identity, "review_timestamp_utc": review_utc,
    }
    if "strategy_config" in session:
        base["strategy_config"] = dict(session["strategy_config"])
    base["trade_id"] = "p1-session-" + hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()[:24]
    entry_time = _utc(session["entry_timestamp"])
    exit_time = _utc(snap["observed_at_utc"])
    risk = float(session["risk_amount"])
    units = int(session["units"])
    entry = float(result["entry_price"])
    if direction == "BUY":
        mfe_price = max(float(session.get("mfe_price", entry)), float(result["exit_price"]))
        mae_price = min(float(session.get("mae_price", entry)), float(result["exit_price"]))
    else:
        mfe_price = min(float(session.get("mfe_price", entry)), float(result["exit_price"]))
        mae_price = max(float(session.get("mae_price", entry)), float(result["exit_price"]))
    mfe_timestamp = session.get("mfe_timestamp_utc", session["entry_timestamp"])
    mae_timestamp = session.get("mae_timestamp_utc", session["entry_timestamp"])
    if (direction == "BUY" and float(result["exit_price"]) >= float(session.get("mfe_price", entry))) or (direction == "SELL" and float(result["exit_price"]) <= float(session.get("mfe_price", entry))):
        mfe_timestamp = snap["observed_at_utc"]
    if (direction == "BUY" and float(result["exit_price"]) <= float(session.get("mae_price", entry))) or (direction == "SELL" and float(result["exit_price"]) >= float(session.get("mae_price", entry))):
        mae_timestamp = snap["observed_at_utc"]
    mfe_r = round(((mfe_price - entry) if direction == "BUY" else (entry - mfe_price)) * units / risk, 8) if risk else None
    mae_r = round(((entry - mae_price) if direction == "BUY" else (mae_price - entry)) * units / risk, 8) if risk else None
    base.update({
        "holding_duration_seconds": round((exit_time - entry_time).total_seconds(), 6),
        "planned_reward_risk": planned_reward_risk(
            session["entry_price"], session["stop_price"], session["target_price"]
        ),
        "outcome_r": round(float(result["net_pl"]) / risk, 8) if risk else None,
        "realized_r": realized_r_multiple(result["net_pl"], risk),
        "roi_class": classify_r_multiple(result["net_pl"], risk),
        "mfe_price": mfe_price,
        "mae_price": mae_price,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "time_to_mfe_seconds": round((_utc(mfe_timestamp) - entry_time).total_seconds(), 6),
        "time_to_mae_seconds": round((_utc(mae_timestamp) - entry_time).total_seconds(), 6),
    })
    return base


def submit_completed_trade_to_p1_pipeline(record: Mapping[str, Any], paths: Mapping[str, Path], repository_root: Path) -> dict[str, Any]:
    candidate_path = paths["state"].with_suffix(".completed.tmp")
    candidate_path.parent.mkdir(parents=True, exist_ok=True); candidate_path.write_text(stable_json(record), encoding="utf-8")
    try:
        return run_capture_replay(candidate_path, paths["ledger"], paths["state"], paths["report"], paths["events"], repository_root=repository_root)
    finally:
        candidate_path.unlink(missing_ok=True)


def close_paper_session(snapshot: Mapping[str, Any], exit_reason: str, reviewer_identity: str, review_utc: str, runtime_path: Path, pipeline_paths: Mapping[str, Path], repository_root: Path) -> dict[str, Any]:
    session = load_active_session(runtime_path)
    if not session: raise ValueError("no_active_session")
    record = build_completed_trade_record(session, snapshot, exit_reason, reviewer_identity, review_utc)
    result = submit_completed_trade_to_p1_pipeline(record, pipeline_paths, repository_root)
    if result["accepted_records"] not in (0, 1): raise ValueError("pipeline_failed_closed")
    runtime_path.unlink(missing_ok=True)
    return {"completed_trade": record, "pipeline": result, **SAFETY_FLAGS}


def abort_paper_session(runtime_path: Path) -> dict[str, Any]:
    existed = runtime_path.exists(); runtime_path.unlink(missing_ok=True)
    return {"status": "ABORTED" if existed else "NO_ACTIVE_SESSION", "p1_credit": 0, **SAFETY_FLAGS}


def build_session_state(runtime_path: Path) -> dict[str, Any]:
    active = load_active_session(runtime_path)
    return {"version": VERSION, "session_controller_status": "READY", "active_session": active, "genuine_paper_trades_recorded": 0, **SAFETY_FLAGS}


def render_owner_report(state: Mapping[str, Any]) -> str:
    return "\n".join(["# AIOS P1 Supervised Paper Session V1", "", f"- Controller status: {state['session_controller_status']}", f"- Active session: {'YES' if state['active_session'] else 'NO'}", "- Genuine paper trades recorded during build: 0", "- Fixture P1 credit: 0", "", "No broker order or demo trade occurred. A future genuine observed session is required.", ""] + [f"- {key}: false" for key in SAFETY_FLAGS]) + "\n"
