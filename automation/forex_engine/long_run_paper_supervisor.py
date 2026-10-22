from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from automation.forex_engine.market_data_normalizer import normalize_market_snapshot, _normalize_pair
from automation.forex_engine.strategy_candidates import generate_strategy_candidates
from automation.forex_engine.multi_trade_queue import build_multi_trade_queue
from automation.forex_engine.order_preview import build_order_preview
from automation.forex_engine.paper_fill_simulator import simulate_paper_fill
from automation.forex_engine.trade_lifecycle_manager import process_trade_update
from automation.forex_engine.balance_compounding import apply_closed_trade_to_balance
from automation.forex_engine.evidence_ledger import build_ledger_event
from automation.forex_engine.session_replay import build_session_replay

LONG_RUN_PAPER_MODE = "PAPER_ONLY"
LONG_RUN_ALLOWED = "allowed"
LONG_RUN_BLOCKED = "blocked"


class _RejectionReason:
    NONE = "none"
    INVALID_SESSION_CONFIG = "invalid_session_config"
    INVALID_MARKET_BATCH = "invalid_market_batch"
    NON_PAPER_MODE = "non_paper_mode"
    LIVE_TRADING_BLOCKED = "live_trading_blocked"
    NO_MARKET_DATA = "no_market_data"
    STALE_MARKET_DATA = "stale_market_data"
    RISK_HALT = "risk_halt"
    VALIDATION_FAILURE = "validation_failure"
    MAX_CYCLES_HIT = "max_cycles_hit"
    MAX_SESSION_TRADES_HIT = "max_session_trades_hit"
    MAX_SESSION_LOSS_HIT = "max_session_loss_hit"
    MISSING_REQUIRED_COMPONENT = "missing_required_component"
    EVIDENCE_PATH_INVALID = "evidence_path_invalid"


LONG_RUN_REJECTION_REASONS = {
    _RejectionReason.NONE,
    _RejectionReason.INVALID_SESSION_CONFIG,
    _RejectionReason.INVALID_MARKET_BATCH,
    _RejectionReason.NON_PAPER_MODE,
    _RejectionReason.LIVE_TRADING_BLOCKED,
    _RejectionReason.NO_MARKET_DATA,
    _RejectionReason.STALE_MARKET_DATA,
    _RejectionReason.RISK_HALT,
    _RejectionReason.VALIDATION_FAILURE,
    _RejectionReason.MAX_CYCLES_HIT,
    _RejectionReason.MAX_SESSION_TRADES_HIT,
    _RejectionReason.MAX_SESSION_LOSS_HIT,
    _RejectionReason.MISSING_REQUIRED_COMPONENT,
    _RejectionReason.EVIDENCE_PATH_INVALID,
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    if isinstance(value, tuple):
        return list(value)
    return []


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _is_paper_only_mode(value: Any) -> bool:
    return _safe_bool(value is None or value == LONG_RUN_PAPER_MODE or (isinstance(value, str) and value.upper() == "PAPER_ONLY"))


def _safe_is_evidence_path_valid(evidence_path: Optional[str]) -> bool:
    if not evidence_path:
        return True
    if not isinstance(evidence_path, str):
        return False
    if evidence_path.startswith(("/", "\\")) or ":" in evidence_path:
        return False
    if ".." in evidence_path:
        return False
    return True


def _build_event(
    event_type: str,
    session_id: str,
    payload: Optional[Dict[str, Any]],
    parent_event_id: Optional[str] = None,
    timestamp: Optional[float] = None,
    evidence_path: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = build_ledger_event(
        event_type=event_type,
        payload=payload or {},
        session_id=session_id,
        timestamp=timestamp,
        evidence_path=evidence_path,
        metadata=(metadata or {}),
    )
    if parent_event_id is not None:
        base["parent_event_id"] = parent_event_id
    return base


def _safety_payload() -> Dict[str, Any]:
    return {
        "paper_only": True,
        "broker": False,
        "live_trading": False,
        "credentials": False,
        "real_orders": False,
        "network_access": False,
    }


def _heartbeat(session_id: str, cycle_number: int, cycle_id: str) -> Dict[str, Any]:
    return {
        "paper_only": True,
        "mode": LONG_RUN_PAPER_MODE,
        "session_id": session_id,
        "cycle_id": cycle_id,
        "cycle_number": cycle_number,
        "timestamp": time.time(),
        "status": "paper_only_supervisor_heartbeat",
    }


@dataclass
class _CycleLimits:
    max_cycles: int = 1
    max_session_trades: int = 0
    max_session_trades_specified: bool = False
    max_session_loss: float = 0.0
    stale_cutoff_seconds: int = 0
    kill_switch: bool = False
    preview_enabled: bool = True


def _resolve_limits(limits: Optional[Any]) -> _CycleLimits:
    if limits is None:
        return _CycleLimits()
    if isinstance(limits, dict):
        return _CycleLimits(
            max_cycles=_as_int(limits.get("max_cycles"), 1),
            max_session_trades=_as_int(limits.get("max_session_trades"), 0),
            max_session_trades_specified="max_session_trades" in limits,
            max_session_loss=_as_float(limits.get("max_session_loss"), 0.0),
            stale_cutoff_seconds=_as_int(limits.get("stale_market_data_seconds"), 0),
            kill_switch=_safe_bool(limits.get("kill_switch_active")),
            preview_enabled=_safe_bool(limits.get("require_order_previews") is not False),
        )
    return _CycleLimits()


def _safe_get_trade_status(trade: Any) -> str:
    if hasattr(trade, "status"):
        return str(getattr(trade, "status"))
    if isinstance(trade, dict):
        return str(trade.get("status", ""))
    return ""


def _safe_trade_fields(trade: Any) -> Dict[str, Any]:
    if hasattr(trade, "__dict__"):
        payload = dict(getattr(trade, "__dict__"))
    elif isinstance(trade, dict):
        payload = dict(trade)
    else:
        payload = {}
    return payload


def _safe_candidate_ok(candidate: Dict[str, Any]) -> bool:
    if not isinstance(candidate, dict):
        return False
    if not _safe_bool(candidate.get("pair")):
        return False
    if candidate.get("direction") not in {"buy", "sell"}:
        return False
    return True


def _extract_account_state(account_state: Optional[Any]) -> Dict[str, Any]:
    if account_state is None:
        return {
            "starting_balance": 0.0,
            "current_balance": 0.0,
            "cash_balance": 0.0,
            "equity": 0.0,
            "realized_pnl": 0.0,
            "trade_count": 0,
            "session_count": 0,
            "daily_loss_used": 0.0,
            "open_risk": 0.0,
        }
    if hasattr(account_state, "__dict__"):
        return dict(account_state.__dict__)
    if isinstance(account_state, dict):
        return dict(account_state)
    return {
        "starting_balance": _as_float(getattr(account_state, "starting_balance", 0.0)),
        "current_balance": _as_float(getattr(account_state, "current_balance", 0.0)),
        "cash_balance": _as_float(getattr(account_state, "cash_balance", 0.0)),
        "equity": _as_float(getattr(account_state, "equity", 0.0)),
        "realized_pnl": _as_float(getattr(account_state, "realized_pnl", 0.0)),
        "trade_count": _as_int(getattr(account_state, "trade_count", 0)),
        "session_count": _as_int(getattr(account_state, "session_count", 0)),
        "daily_loss_used": _as_float(getattr(account_state, "daily_loss_used", 0.0)),
        "open_risk": _as_float(getattr(account_state, "open_risk", 0.0)),
    }


def _pick_timestamp(event_like: Any) -> Optional[float]:
    if isinstance(event_like, dict):
        if event_like.get("timestamp") is not None:
            return _as_float(event_like.get("timestamp"), None)
    return None


def run_paper_supervisor_cycle(
    market_batch,
    account_state: Optional[Any] = None,
    open_trades: Optional[Any] = None,
    closed_trades: Optional[Any] = None,
    session_state: Optional[Any] = None,
    limits: Optional[Any] = None,
    timestamp: Optional[float] = None,
    evidence_path: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = dict(metadata or {})
    now_timestamp = time.time() if timestamp is None else _as_float(timestamp)
    if not _safe_is_evidence_path_valid(evidence_path):
        return {
            "allowed": False,
            "decision": LONG_RUN_BLOCKED,
            "blocked_reason": _RejectionReason.EVIDENCE_PATH_INVALID,
            "blocked_reasons": [_RejectionReason.EVIDENCE_PATH_INVALID],
            "warnings": [],
            "paper_only": True,
            "mode": LONG_RUN_PAPER_MODE,
            "session_id": str((session_state or {}).get("session_id", "session-1")),
            "cycle_id": "",
            "cycle_number": _as_int((session_state or {}).get("cycle_number"), 1),
            "normalized_market_count": 0,
            "candidate_count": 0,
            "selected_count": 0,
            "rejected_count": 0,
            "previews_created": 0,
            "fills_created": 0,
            "trades_opened": 0,
            "trades_closed": 0,
            "balance_updates": 0,
            "ledger_events": [],
            "replay_summary": {},
            "account_state_before": _extract_account_state(account_state),
            "account_state_after": _extract_account_state(account_state),
            "open_trades": [],
            "closed_trades": _as_list(closed_trades),
            "heartbeat": {"status": "blocked", "mode": LONG_RUN_PAPER_MODE, "paper_only": True},
            "stop_conditions": [_RejectionReason.EVIDENCE_PATH_INVALID],
            "safety": _safety_payload(),
            "next_safe_action": "Use a relative evidence path and rerun the cycle.",
            "metadata": metadata,
        }

    if isinstance(market_batch, (str, bytes, dict)):
        return _invalid_failure(
            "market_batch",
            _RejectionReason.INVALID_MARKET_BATCH,
            session_state=session_state,
            evidence_path=evidence_path,
            metadata=metadata,
            timestamp=now_timestamp,
            account_state=account_state,
            open_trades=_as_list(open_trades),
            closed_trades=_as_list(closed_trades),
        )

    if not isinstance(market_batch, Iterable):
        return _invalid_failure(
            "market_batch",
            _RejectionReason.INVALID_MARKET_BATCH,
            session_state=session_state,
            evidence_path=evidence_path,
            metadata=metadata,
            timestamp=now_timestamp,
            account_state=account_state,
            open_trades=_as_list(open_trades),
        closed_trades=_as_list(closed_trades),
    )

    account_snapshot = _extract_account_state(account_state)
    if (
        account_snapshot.get("current_balance", 0.0) < 0
        or account_snapshot.get("starting_balance", 0.0) < 0
        or account_snapshot.get("cash_balance", 0.0) < 0
        or account_snapshot.get("equity", 0.0) < 0
    ):
        return _invalid_failure(
            "account_state",
            _RejectionReason.VALIDATION_FAILURE,
            session_state=session_state,
            evidence_path=evidence_path,
            metadata=metadata,
            timestamp=now_timestamp,
            account_state=account_snapshot,
            open_trades=_as_list(open_trades),
            closed_trades=_as_list(closed_trades),
        )

    market_snapshots = list(market_batch)
    if not market_snapshots:
        return _invalid_failure(
            "market_batch",
            _RejectionReason.NO_MARKET_DATA,
            session_state=session_state,
            evidence_path=evidence_path,
            metadata=metadata,
            timestamp=now_timestamp,
            account_state=account_state,
            open_trades=_as_list(open_trades),
            closed_trades=_as_list(closed_trades),
        )

    mode = LONG_RUN_PAPER_MODE
    if mode != LONG_RUN_PAPER_MODE:
        return _invalid_failure(
            "session_config",
            _RejectionReason.NON_PAPER_MODE,
            session_state=session_state,
            evidence_path=evidence_path,
            metadata=metadata,
            timestamp=now_timestamp,
            account_state=account_state,
            open_trades=_as_list(open_trades),
            closed_trades=_as_list(closed_trades),
        )

    live_mode = metadata.get("mode")
    if isinstance(live_mode, str) and live_mode.lower() in {"live", "live_demo", "broker"}:
        return _invalid_failure(
            "session_config",
            _RejectionReason.LIVE_TRADING_BLOCKED,
            session_state=session_state,
            evidence_path=evidence_path,
            metadata=metadata,
            timestamp=now_timestamp,
            account_state=account_state,
            open_trades=_as_list(open_trades),
            closed_trades=_as_list(closed_trades),
            stop_conditions=[_RejectionReason.LIVE_TRADING_BLOCKED],
        )

    cfg = _resolve_limits(limits)
    max_cycles = _as_int(cfg.max_cycles, 1)
    session_cfg = _as_list(getattr(session_state, "events", None)) if session_state else []
    cycle_number = _as_int(session_state.get("cycle_number"), 1) if isinstance(session_state, dict) else _as_int(getattr(session_state, "cycle_number", 1))
    if cycle_number > max_cycles:
        return _invalid_failure(
            "session_config",
            _RejectionReason.MAX_CYCLES_HIT,
            session_state=session_state,
            evidence_path=evidence_path,
            metadata=metadata,
            timestamp=now_timestamp,
            account_state=account_state,
            open_trades=_as_list(open_trades),
            closed_trades=_as_list(closed_trades),
            stop_conditions=[_RejectionReason.MAX_CYCLES_HIT],
        )

    cycle_id = hashlib.sha1(
        f"{session_state.get('session_id', 'session-1') if isinstance(session_state, dict) else 'session-1'}-{cycle_number}-{now_timestamp}".encode(
            "utf-8"
        )
    ).hexdigest()[:12]

    warnings: List[str] = []
    stop_conditions: List[str] = []
    ledger_events: List[Dict[str, Any]] = []
    normalized_snapshots: List[Dict[str, Any]] = []
    market_by_pair: Dict[str, Dict[str, Any]] = {}
    candidate_count = 0
    selected_count = 0
    rejected_count = 0
    previews_created = 0
    fills_created = 0
    trades_opened = 0
    trades_closed = 0
    balance_updates = 0

    selected_candidates: List[Dict[str, Any]] = []
    session_id = str(session_state.get("session_id", "session-1")) if isinstance(session_state, dict) else "session-1"
    account_before = _extract_account_state(account_state)
    all_open = _as_list(open_trades)
    all_closed = _as_list(closed_trades)

    if cfg.kill_switch:
        stop_conditions.append("kill_switch_active")
        return {
            "allowed": False,
            "decision": LONG_RUN_BLOCKED,
            "blocked_reason": _RejectionReason.VALIDATION_FAILURE,
            "blocked_reasons": stop_conditions,
            "warnings": warnings,
            "paper_only": True,
            "mode": LONG_RUN_PAPER_MODE,
            "session_id": session_id,
            "cycle_id": cycle_id,
            "cycle_number": cycle_number,
            "normalized_market_count": len(normalized_snapshots),
            "candidate_count": candidate_count,
            "selected_count": selected_count,
            "rejected_count": rejected_count,
            "previews_created": previews_created,
            "fills_created": fills_created,
            "trades_opened": trades_opened,
            "trades_closed": trades_closed,
            "balance_updates": balance_updates,
            "ledger_events": ledger_events,
            "replay_summary": build_session_replay(ledger_events, session_id=session_id, evidence_path=evidence_path, metadata=metadata),
            "account_state_before": account_before,
            "account_state_after": account_before,
            "open_trades": all_open,
            "closed_trades": all_closed,
            "heartbeat": _heartbeat(session_id, cycle_number, cycle_id),
            "stop_conditions": stop_conditions,
            "safety": _safety_payload(),
            "next_safe_action": "Resolve kill_switch or wait for next manual cycle.",
            "metadata": metadata,
        }

    # Enforce stops before creating any new paper intent or fill. A blocked
    # return after the fill loop cannot undo a simulated position already made.
    initial_stop = None
    if (cfg.max_session_trades_specified and cfg.max_session_trades >= 0
            and len(all_open) + len(all_closed) >= cfg.max_session_trades):
        initial_stop = _RejectionReason.MAX_SESSION_TRADES_HIT
    if cfg.max_session_loss > 0 and account_before.get("starting_balance", 0.0) > 0:
        baseline = account_before["starting_balance"]
        if max(0.0, baseline - account_before.get("current_balance", baseline)) >= cfg.max_session_loss:
            initial_stop = initial_stop or _RejectionReason.MAX_SESSION_LOSS_HIT
    if initial_stop is not None:
        # Entry limits halt new exposure. Existing positions still receive their
        # normal stop/target updates from fresh validated market snapshots.
        stop_conditions.append(initial_stop)
        warnings.append(initial_stop)

    for raw_snapshot in market_snapshots:
        norm_result = normalize_market_snapshot(
            raw_snapshot,
            limits=(
                limits.get("market_limits")
                if isinstance(limits, dict)
                else None
            ),
            now_timestamp=now_timestamp,
            evidence_path=evidence_path,
            metadata=metadata,
        )
        norm_allowed = norm_result.get("allowed", False)
        norm_warnings = norm_result.get("warnings", [])
        if isinstance(norm_warnings, list):
            warnings.extend(norm_warnings)

        if not norm_allowed:
            blocked_reason = norm_result.get("blocked_reason", _RejectionReason.STALE_MARKET_DATA)
            stop_event = {
                "cycle_id": cycle_id,
                "pair": norm_result.get("pair"),
                "index": len(normalized_snapshots),
            }
            ledger_events.append(
                _build_event(
                    "market_data_rejected",
                    session_id=session_id,
                    payload=stop_event,
                    timestamp=now_timestamp,
                    evidence_path=evidence_path,
                    metadata=metadata,
                )
            )
            if blocked_reason in {
                _RejectionReason.STALE_MARKET_DATA,
                _RejectionReason.LIVE_TRADING_BLOCKED,
                _RejectionReason.INVALID_MARKET_BATCH,
            }:
                stop_conditions.append(_RejectionReason.STALE_MARKET_DATA)
                return {
                    "allowed": False,
                    "decision": LONG_RUN_BLOCKED,
                    "blocked_reason": _RejectionReason.STALE_MARKET_DATA,
                    "blocked_reasons": stop_conditions,
                    "warnings": warnings,
                    "paper_only": True,
                    "mode": LONG_RUN_PAPER_MODE,
                    "session_id": session_id,
                    "cycle_id": cycle_id,
                    "cycle_number": cycle_number,
                    "normalized_market_count": len(normalized_snapshots),
                    "candidate_count": candidate_count,
                    "selected_count": selected_count,
                    "rejected_count": rejected_count,
                    "previews_created": previews_created,
                    "fills_created": fills_created,
                    "trades_opened": trades_opened,
                    "trades_closed": trades_closed,
                    "balance_updates": balance_updates,
                    "ledger_events": ledger_events,
                    "replay_summary": build_session_replay(ledger_events, session_id=session_id, evidence_path=evidence_path, metadata=metadata),
                    "account_state_before": account_before,
                    "account_state_after": account_before,
                    "open_trades": all_open,
                    "closed_trades": all_closed,
                    "heartbeat": _heartbeat(session_id, cycle_number, cycle_id),
                    "stop_conditions": stop_conditions,
                    "safety": _safety_payload(),
                    "next_safe_action": "Feed fresh normalized snapshots and rerun the cycle.",
                    "metadata": metadata,
                }

            rejected_count += 1
            continue
        normalized = norm_result.get("normalized_for_strategy") or norm_result
        normalized_snapshots.append(normalized)
        if norm_result.get("pair"):
            normalized_pair = _normalize_pair(norm_result.get("pair"))
            quote = norm_result.get("normalized_for_preview") or norm_result
            market_by_pair[normalized_pair] = dict(quote)

    for normalized in normalized_snapshots:
        if initial_stop is not None:
            break
        strategy_result = generate_strategy_candidates(
            normalized,
            now_timestamp=now_timestamp,
            evidence_path=evidence_path,
            metadata=metadata,
        )
        if strategy_result.get("allowed", False):
            candidates = strategy_result.get("candidates", [])
            candidate_count += len(candidates)
            queue_result = build_multi_trade_queue(
                strategy_result,
                account_state=account_state,
                open_trades=all_open,
                closed_trades=all_closed,
                limits=limits,
                now_timestamp=now_timestamp,
                evidence_path=evidence_path,
                metadata=metadata,
            )
            selected = queue_result.get("selected_candidates") or []
            rejected = queue_result.get("rejected_candidates") or []
            selected_count += len(selected)
            rejected_count += len(rejected)
            selected_candidates.extend(selected)
        else:
            warnings.extend(_as_list(strategy_result.get("warnings")))

    if selected_candidates:
        for candidate in selected_candidates:
            if (cfg.max_session_trades_specified and cfg.max_session_trades >= 0
                    and len(all_open) + len(all_closed) >= cfg.max_session_trades):
                stop_conditions.append(_RejectionReason.MAX_SESSION_TRADES_HIT)
                warnings.append("max_session_trades_hit")
                break
            if not _safe_candidate_ok(candidate):
                warnings.append("candidate_invalid")
                rejected_count += 1
                continue
            preview = build_order_preview(
                candidate,
                account_state=account_state,
                open_trades=all_open,
                closed_trades=all_closed,
                limits=limits,
                timestamp=now_timestamp,
                evidence_path=evidence_path,
                metadata=metadata,
            )
            if not preview.get("allowed", False):
                if preview.get("blocked_reason") == _RejectionReason.VALIDATION_FAILURE:
                    stop_conditions.append(_RejectionReason.RISK_HALT)
                    warnings.append("risk_or_validation_block")
                rejected_count += 1
                continue
            previews_created += 1
            ledger_events.append(
                _build_event(
                    "preview_created",
                    session_id=session_id,
                    payload={
                        "cycle_id": cycle_id,
                        "preview_id": preview.get("preview_id"),
                        "pair": preview.get("pair"),
                        "direction": preview.get("direction"),
                    },
                    timestamp=now_timestamp,
                    evidence_path=evidence_path,
                    metadata=metadata,
                )
            )
            quote = market_by_pair.get(_normalize_pair(preview.get("pair") or candidate.get("pair")))
            if quote is None:
                rejected_count += 1
                warnings.append("missing_pair_quote_for_fill")
                continue
            fill_result = simulate_paper_fill(
                preview,
                market_state=quote,
                fill_config=(limits.get("fill_config") if isinstance(limits, dict) else None),
                timestamp=now_timestamp,
                evidence_path=evidence_path,
                metadata=metadata,
            )
            if not fill_result.get("allowed", False):
                rejected_count += 1
                continue
            fill_trade = fill_result.get("trade") or fill_result.get("filled_trade") or fill_result
            fills_created += 1
            all_open.append(fill_trade)
            trades_opened += 1
            ledger_events.append(
                _build_event(
                    "paper_trade_opened",
                    session_id=session_id,
                    payload=_safe_trade_fields(fill_trade),
                    timestamp=_pick_timestamp(fill_result) or now_timestamp,
                    evidence_path=evidence_path,
                    metadata=metadata,
                )
            )
            if fill_result.get("decision") == LONG_RUN_BLOCKED:
                stop_conditions.append(_RejectionReason.RISK_HALT)
                warnings.append("fill_blocked")

    # lifecycle updates for open trades when price allows close conditions
    updated_open: List[Any] = []
    for trade in list(all_open):
        status = _safe_get_trade_status(trade)
        if status not in {"opened", "active"}:
            continue
        quote = market_by_pair.get(_normalize_pair(_safe_trade_fields(trade).get("pair")))
        if quote is None:
            updated_open.append(trade)
            warnings.append("missing_pair_quote_for_existing_trade")
            continue
        process_result = process_trade_update(
            trade,
            price_update=quote,
            timestamp=now_timestamp,
            evidence_path=evidence_path,
            metadata=metadata,
        )
        if not process_result.get("allowed", False):
            updated_open.append(trade)
            continue
        closed = bool(process_result.get("closed", False))
        if closed:
            updated_trade = process_result.get("trade") or trade
            all_closed.append(updated_trade)
            trades_closed += 1
            all_open = [o for o in all_open if o is not trade]
            ledger_events.append(
                _build_event(
                    "paper_trade_closed",
                    session_id=session_id,
                    payload=_safe_trade_fields(updated_trade),
                    timestamp=_pick_timestamp(process_result) or now_timestamp,
                    evidence_path=evidence_path,
                    metadata=metadata,
                )
            )
            balance_result = apply_closed_trade_to_balance(
                account_before,
                process_result,
                limits=limits,
                evidence_path=evidence_path,
                metadata=metadata,
            )
            if balance_result.get("allowed", False):
                account_before = {
                    **account_before,
                    **balance_result.get("account_state_after", {}),
                    "paper_only": True,
                    "mode": LONG_RUN_PAPER_MODE,
                }
                balance_updates += 1
                ledger_events.append(
                    _build_event(
                        "balance_updated",
                        session_id=session_id,
                        payload=balance_result.get("account_state_after", {}),
                        timestamp=now_timestamp,
                        evidence_path=evidence_path,
                        metadata=metadata,
                    )
                )

    # risk halt check from any component
    if (
        cfg.max_session_trades_specified
        and cfg.max_session_trades >= 0
        and (len(all_open) + len(all_closed)) >= cfg.max_session_trades
    ):
        stop_conditions.append(_RejectionReason.MAX_SESSION_TRADES_HIT)
        warnings.append("max_session_trades_hit")

    if cfg.max_session_loss > 0 and account_before.get("starting_balance", 0.0) > 0:
        baseline = account_before.get("starting_balance", 0.0)
        drawdown = max(0.0, baseline - account_before.get("current_balance", baseline))
        if drawdown >= cfg.max_session_loss:
            stop_conditions.append(_RejectionReason.MAX_SESSION_LOSS_HIT)
            warnings.append("max_session_loss_hit")

    if not normalized_snapshots:
        return _invalid_failure(
            "market_batch",
            _RejectionReason.NO_MARKET_DATA,
            session_state=session_state,
            evidence_path=evidence_path,
            metadata=metadata,
            timestamp=now_timestamp,
            account_state=account_before,
            open_trades=all_open,
            closed_trades=all_closed,
            stop_conditions=stop_conditions,
        )

    replay_summary = build_session_replay(
        ledger_events,
        session_id=session_id,
        evidence_path=evidence_path,
        metadata=metadata,
    )

    return {
        "allowed": True if not stop_conditions else False,
        "decision": LONG_RUN_ALLOWED if not stop_conditions else LONG_RUN_BLOCKED,
        "blocked_reason": _RejectionReason.NONE if not stop_conditions else stop_conditions[0],
        "blocked_reasons": stop_conditions,
        "warnings": warnings,
        "paper_only": True,
        "mode": LONG_RUN_PAPER_MODE,
        "session_id": session_id,
        "cycle_id": cycle_id,
        "cycle_number": cycle_number,
        "normalized_market_count": len(normalized_snapshots),
        "candidate_count": candidate_count,
        "selected_count": selected_count,
        "rejected_count": rejected_count,
        "previews_created": previews_created,
        "fills_created": fills_created,
        "trades_opened": trades_opened,
        "trades_closed": trades_closed,
        "balance_updates": balance_updates,
        "ledger_events": ledger_events,
        "replay_summary": replay_summary,
        "account_state_before": _extract_account_state(account_state),
        "account_state_after": account_before,
        "open_trades": all_open,
        "closed_trades": all_closed,
        "heartbeat": _heartbeat(session_id, cycle_number, cycle_id),
        "stop_conditions": stop_conditions,
        "safety": _safety_payload(),
        "next_safe_action": (
            "Review warnings and continue running paper supervisor cycle."
            if not stop_conditions
            else "Resolve stop conditions and rerun cycle."
        ),
        "metadata": metadata,
    }


def summarize_paper_supervisor_session(
    cycle_results: Any,
    session_id: Optional[str] = None,
    evidence_path: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = dict(metadata or {})
    if not _safe_is_evidence_path_valid(evidence_path):
        return {
            "allowed": False,
            "decision": LONG_RUN_BLOCKED,
            "blocked_reason": _RejectionReason.EVIDENCE_PATH_INVALID,
            "blocked_reasons": [_RejectionReason.EVIDENCE_PATH_INVALID],
            "warnings": [],
            "paper_only": True,
            "mode": LONG_RUN_PAPER_MODE,
            "session_id": session_id or "session-1",
            "cycle_count": 0,
            "cycle_ids": [],
            "total_normalized_market_count": 0,
            "total_candidates": 0,
            "total_selected": 0,
            "total_rejected": 0,
            "total_previews": 0,
            "total_fills": 0,
            "total_opened": 0,
            "total_closed": 0,
            "total_balance_updates": 0,
            "ledger_events": [],
            "replay_summary": {},
            "safety": _safety_payload(),
            "next_safe_action": "Use a valid relative evidence path.",
            "metadata": metadata,
        }

    results = _as_list(cycle_results)
    filtered = [r for r in results if isinstance(r, dict)]
    if session_id is not None:
        filtered = [r for r in filtered if r.get("session_id") == session_id]

    session_identifier = session_id or (filtered[0].get("session_id") if filtered else "session-1")
    cycle_ids: List[str] = []
    totals = {
        "normalized_market_count": 0,
        "candidate_count": 0,
        "selected_count": 0,
        "rejected_count": 0,
        "previews_created": 0,
        "fills_created": 0,
        "trades_opened": 0,
        "trades_closed": 0,
        "balance_updates": 0,
    }
    all_ledger: List[Dict[str, Any]] = []

    for cycle in filtered:
        cycle_ids.append(str(cycle.get("cycle_id", "")))
        totals["normalized_market_count"] += _as_int(cycle.get("normalized_market_count"), 0)
        totals["candidate_count"] += _as_int(cycle.get("candidate_count"), 0)
        totals["selected_count"] += _as_int(cycle.get("selected_count"), 0)
        totals["rejected_count"] += _as_int(cycle.get("rejected_count"), 0)
        totals["previews_created"] += _as_int(cycle.get("previews_created"), 0)
        totals["fills_created"] += _as_int(cycle.get("fills_created"), 0)
        totals["trades_opened"] += _as_int(cycle.get("trades_opened"), 0)
        totals["trades_closed"] += _as_int(cycle.get("trades_closed"), 0)
        totals["balance_updates"] += _as_int(cycle.get("balance_updates"), 0)
        all_ledger.extend(_as_list(cycle.get("ledger_events")))

    replay_summary = build_session_replay(
        all_ledger,
        session_id=session_identifier,
        evidence_path=evidence_path,
        metadata=metadata,
    )

    return {
        "allowed": True,
        "decision": LONG_RUN_ALLOWED,
        "blocked_reason": _RejectionReason.NONE,
        "blocked_reasons": [],
        "warnings": [],
        "paper_only": True,
        "mode": LONG_RUN_PAPER_MODE,
        "session_id": session_identifier,
        "cycle_count": len(cycle_ids),
        "cycle_ids": cycle_ids,
        "total_normalized_market_count": totals["normalized_market_count"],
        "total_candidates": totals["candidate_count"],
        "total_selected": totals["selected_count"],
        "total_rejected": totals["rejected_count"],
        "total_previews": totals["previews_created"],
        "total_fills": totals["fills_created"],
        "total_opened": totals["trades_opened"],
        "total_closed": totals["trades_closed"],
        "total_balance_updates": totals["balance_updates"],
        "ledger_events": all_ledger,
        "replay_summary": replay_summary,
        "safety": _safety_payload(),
        "next_safe_action": "Continue paper-run cycle and review replay summary trends.",
        "metadata": metadata,
    }


def _invalid_failure(
    _target: str,
    reason: str,
    *,
    session_state: Optional[Any],
    evidence_path: Optional[str],
    metadata: Dict[str, Any],
    timestamp: float,
    account_state: Optional[Any] = None,
    open_trades: Optional[List[Any]] = None,
    closed_trades: Optional[List[Any]] = None,
    stop_conditions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    session_id = str(session_state.get("session_id", "session-1")) if isinstance(session_state, dict) else "session-1"
    return {
        "allowed": False,
        "decision": LONG_RUN_BLOCKED,
        "blocked_reason": reason,
        "blocked_reasons": stop_conditions or [reason],
        "warnings": [f"{_target}_invalid"],
        "paper_only": True,
        "mode": LONG_RUN_PAPER_MODE,
        "session_id": session_id,
        "cycle_id": "",
        "cycle_number": _as_int(session_state.get("cycle_number"), 1) if isinstance(session_state, dict) else 1,
        "normalized_market_count": 0,
        "candidate_count": 0,
        "selected_count": 0,
        "rejected_count": 0,
        "previews_created": 0,
        "fills_created": 0,
        "trades_opened": 0,
        "trades_closed": 0,
        "balance_updates": 0,
        "ledger_events": [],
        "replay_summary": {},
        "account_state_before": _extract_account_state(account_state),
        "account_state_after": _extract_account_state(account_state),
        "open_trades": open_trades or [],
        "closed_trades": closed_trades or [],
        "heartbeat": {
            "status": "blocked",
            "mode": LONG_RUN_PAPER_MODE,
            "paper_only": True,
            "session_id": session_id,
            "cycle_id": "",
        },
        "stop_conditions": stop_conditions or [reason],
        "safety": _safety_payload(),
        "next_safe_action": "Fix validation failures and rerun with normalized inputs.",
        "metadata": metadata,
    }
