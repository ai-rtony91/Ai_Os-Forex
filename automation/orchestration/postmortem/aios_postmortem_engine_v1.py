"""AIOS post-mortem learning and bounded recovery engine, version 1.

This module only analyzes supplied evidence and writes optional reports.  It has
no authority to mutate Git, queues, workers, governance, trading, or production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

VERSION = "1.0"
REPORT_ROOT = Path("Reports/orchestration/postmortem")
DURABILITY_STATES = {"REMOTE_VERIFIED", "USER_VISIBLE_CAPSULE_VERIFIED", "AT_RISK"}
OUTCOMES = (
    "SUCCESS", "RECOVERED", "BLOCKED_GOVERNANCE", "BLOCKED_EXTERNAL",
    "REPOSITORY_STATE_MISMATCH", "DIRTY_WORKTREE", "ORIGIN_ABSENT",
    "ORIGIN_INCORRECT", "AUTHORIZATION_UNAVAILABLE", "LOCAL_COMMIT_AT_RISK",
    "MISSING_COMMIT", "MISSING_BRANCH", "WORKER_LEASE_EXPIRED",
    "WORKER_STILL_ACTIVE", "STALE_APPLICATION_LOCK", "GIT_LOCK_REVIEW_REQUIRED",
    "ORPHANED_APPLY", "DUPLICATE_APPLY", "PACKET_COLLISION", "MALFORMED_PACKET",
    "VALIDATION_FAILURE", "CI_FAILURE", "CORRUPT_STATE", "QUARANTINED",
    "UNSAFE_TO_CONTINUE",
)
NEXT_ACTION = {
    "SUCCESS": "CLOSE_AFTER_VERIFICATION", "RECOVERED": "RUN_VALIDATORS",
    "BLOCKED_GOVERNANCE": "REQUEST_HUMAN_OWNER_REVIEW",
    "BLOCKED_EXTERNAL": "WAIT_FOR_EXTERNAL_DEPENDENCY",
    "REPOSITORY_STATE_MISMATCH": "REVIEW_REPOSITORY_IDENTITY",
    "DIRTY_WORKTREE": "PRESERVE_AND_REVIEW_WORKTREE",
    "ORIGIN_ABSENT": "REQUEST_APPROVAL_TO_ADD_ORIGIN",
    "ORIGIN_INCORRECT": "REVIEW_REQUIRED",
    "AUTHORIZATION_UNAVAILABLE": "REQUEST_PUBLICATION_AUTHORIZATION",
    "LOCAL_COMMIT_AT_RISK": "PUBLISH_AND_VERIFY_COMMIT",
    "MISSING_COMMIT": "REVIEW_REQUIRED", "MISSING_BRANCH": "REVIEW_REQUIRED",
    "WORKER_LEASE_EXPIRED": "RECLAIM_WITH_BOUNDED_PLAYBOOK",
    "WORKER_STILL_ACTIVE": "WAIT_FOR_WORKER",
    "STALE_APPLICATION_LOCK": "RECLAIM_WITH_BOUNDED_PLAYBOOK",
    "GIT_LOCK_REVIEW_REQUIRED": "REVIEW_REQUIRED",
    "ORPHANED_APPLY": "RECONCILE_APPLY_EVIDENCE",
    "DUPLICATE_APPLY": "BLOCK_DUPLICATE_APPLY",
    "PACKET_COLLISION": "REVIEW_REQUIRED", "MALFORMED_PACKET": "REJECT_PACKET",
    "VALIDATION_FAILURE": "REPAIR_AND_RERUN_VALIDATORS",
    "CI_FAILURE": "INSPECT_REQUIRED_CI",
    "CORRUPT_STATE": "QUARANTINE_EVIDENCE", "QUARANTINED": "REVIEW_REQUIRED",
    "UNSAFE_TO_CONTINUE": "REVIEW_REQUIRED",
}
REQUIRED = (
    "event_id incident_id packet_id task_id run_id worker_identity supervisor_identity lane timestamp "
    "repository_identity worktree branch base_sha head_sha tree_sha worktree_state remote_state "
    "failing_stage sanitized_detection_signature evidence_references evidence_hashes "
    "outcome_classification root_cause_status verified_root_cause hypotheses recovery_attempts "
    "recovery_result validators_after_recovery durability_state lesson_status promotion_status "
    "next_safe_action"
).split()
SECRET_KEYS = re.compile(r"(?:password|passwd|secret|token|credential|api[_-]?key|account|broker_payload)", re.I)
HEX_HASH = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
EVIDENCE_TYPES = {"trade_execution", "signal", "market_condition", "campaign_runtime", "validation", "human_review"}
SIDES = {"BUY", "SELL"}
PATTERN_REQUIREMENTS = {
    "FALSE_FLIP": ({"flip_count", "bars_to_reversal"}, "signal"),
    "LOW_VOLATILITY_WHIPSAW": ({"atr", "atr_floor", "reversal_count"}, "market_condition"),
    "RAPID_REVERSAL": ({"reversal_count", "duration_seconds"}, "signal"),
    "MULTIPLIER_SENSITIVITY": ({"supertrend_multiplier", "comparison_multiplier"}, "signal"),
    "INSUFFICIENT_TREND_PERSISTENCE": ({"trend_bars", "minimum_trend_bars"}, "signal"),
    "WINNER_TREND_PERSISTENCE": ({"trend_bars", "minimum_trend_bars"}, "signal"),
    "FAVORABLE_VOLATILITY_REGIME": ({"atr", "atr_floor"}, "market_condition"),
}

TRANSITIONS = {
    "OBSERVED": {"EVIDENCE_CAPTURED", "QUARANTINED"},
    "EVIDENCE_CAPTURED": {"CLASSIFIED", "QUARANTINED"},
    "CLASSIFIED": {"LESSON_PROPOSED", "RECOVERY_PLANNED", "REVIEW_REQUIRED", "QUARANTINED"},
    "LESSON_PROPOSED": {"RECOVERY_PLANNED", "REVIEW_REQUIRED"},
    "RECOVERY_PLANNED": {"RECOVERABLE", "REVIEW_REQUIRED", "QUARANTINED"},
    "RECOVERABLE": {"RECOVERED", "REVIEW_REQUIRED"},
    "RECOVERED": {"VERIFIED", "REVIEW_REQUIRED", "QUARANTINED"},
    "VERIFIED": {"CLOSED"}, "REVIEW_REQUIRED": {"RECOVERY_PLANNED", "QUARANTINED"},
    "QUARANTINED": {"REVIEW_REQUIRED"}, "CLOSED": set(),
}

class ValidationError(ValueError): pass
class DuplicateEventError(ValidationError): pass

def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)

def evidence_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def _walk(value: Any, key: str = "") -> None:
    if SECRET_KEYS.search(key): raise ValidationError(f"secret-like field rejected: {key}")
    if isinstance(value, float) and not math.isfinite(value): raise ValidationError("non-finite value")
    if isinstance(value, Mapping):
        for k, v in value.items(): _walk(v, str(k))
    elif isinstance(value, list):
        for v in value: _walk(v, key)

def validate_event(event: Mapping[str, Any], seen_event_ids: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(event, Mapping): raise ValidationError("event must be an object")
    unknown = set(event) - set(REQUIRED)
    missing = set(REQUIRED) - set(event)
    if missing or unknown: raise ValidationError(f"schema fields missing={sorted(missing)} unknown={sorted(unknown)}")
    _walk(event)
    for field in ("event_id", "incident_id", "packet_id", "task_id", "run_id"):
        if not isinstance(event[field], str) or not IDENTIFIER.fullmatch(event[field]): raise ValidationError(f"invalid {field}")
    if seen_event_ids is not None and event["event_id"] in seen_event_ids: raise DuplicateEventError(event["event_id"])
    for field in ("evidence_references", "evidence_hashes", "hypotheses", "recovery_attempts", "validators_after_recovery"):
        if not isinstance(event[field], list) or len(event[field]) != len({canonical_json(x) for x in event[field]}):
            raise ValidationError(f"{field} must be a duplicate-free array")
    if any(not isinstance(x, str) or not HEX_HASH.fullmatch(x) for x in event["evidence_hashes"]): raise ValidationError("invalid evidence hash")
    if event["outcome_classification"] not in OUTCOMES: raise ValidationError("unsupported outcome")
    if event["durability_state"] not in DURABILITY_STATES: raise ValidationError("unsupported durability state")
    if event["remote_state"] == "LOCAL_ONLY" and event["durability_state"] != "AT_RISK": raise ValidationError("local-only work must be AT_RISK")
    if event["root_cause_status"] == "VERIFIED" and not event["verified_root_cause"]: raise ValidationError("verified cause missing")
    if event["root_cause_status"] != "VERIFIED" and event["verified_root_cause"] is not None: raise ValidationError("unverified cause presented as verified")
    p = Path(event["worktree"])
    if ".." in p.parts: raise ValidationError("path escape")
    try: datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    except (ValueError, AttributeError): raise ValidationError("invalid timestamp") from None
    result = deepcopy(dict(event))
    if seen_event_ids is not None: seen_event_ids.add(event["event_id"])
    return result

def validate_pattern(pattern: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the engine's closed, evidence-only pattern record."""
    required = {"schema_version", "signature", "incident_ids", "independent_incident_count",
                "duplicate_suppressed", "promotion_eligible", "human_owner_review_required", "authority"}
    if not isinstance(pattern, Mapping) or set(pattern) != required:
        raise ValidationError("pattern fields do not match the closed schema")
    _walk(pattern)
    incidents = pattern["incident_ids"]
    if pattern["schema_version"] != VERSION or pattern["authority"] != "OPERATIONAL_EVIDENCE_ONLY":
        raise ValidationError("unsupported pattern identity")
    if not isinstance(pattern["signature"], str) or not pattern["signature"]:
        raise ValidationError("invalid pattern signature")
    if not isinstance(incidents, list) or len(incidents) != len(set(incidents)):
        raise ValidationError("incident IDs must be a unique array")
    if pattern["independent_incident_count"] != len(incidents):
        raise ValidationError("incident count contradicts incident IDs")
    for field in ("duplicate_suppressed", "promotion_eligible", "human_owner_review_required"):
        if type(pattern[field]) is not bool: raise ValidationError(f"{field} must be boolean")
    if pattern["promotion_eligible"] and len(incidents) < 2:
        raise ValidationError("promotion requires two independent incidents")
    return deepcopy(dict(pattern))

def classify(facts: Mapping[str, Any]) -> dict[str, str]:
    rules = (
        ("corrupt_evidence", "CORRUPT_STATE"), ("duplicate_apply", "DUPLICATE_APPLY"),
        ("packet_collision", "PACKET_COLLISION"), ("git_index_lock_persistent", "GIT_LOCK_REVIEW_REQUIRED"),
        ("application_lock_expired", "STALE_APPLICATION_LOCK"), ("worker_active", "WORKER_STILL_ACTIVE"),
        ("worker_lease_expired", "WORKER_LEASE_EXPIRED"), ("dirty_worktree", "DIRTY_WORKTREE"),
        ("repository_mismatch", "REPOSITORY_STATE_MISMATCH"), ("origin_incorrect", "ORIGIN_INCORRECT"),
        ("origin_absent", "ORIGIN_ABSENT"), ("authorization_unavailable", "AUTHORIZATION_UNAVAILABLE"),
        ("missing_branch", "MISSING_BRANCH"), ("missing_commit", "MISSING_COMMIT"),
        ("local_commit_only", "LOCAL_COMMIT_AT_RISK"), ("orphaned_apply", "ORPHANED_APPLY"),
        ("validators_failed", "VALIDATION_FAILURE"), ("ci_failed", "CI_FAILURE"),
        ("recovered", "RECOVERED"), ("success", "SUCCESS"),
    )
    outcome = next((name for flag, name in rules if facts.get(flag) is True), "UNSAFE_TO_CONTINUE")
    return {"outcome_classification": outcome, "next_safe_action": NEXT_ACTION[outcome],
            "durability_state": "AT_RISK" if facts.get("local_commit_only") or not facts.get("remote_verified") else "REMOTE_VERIFIED"}

class PatternMemory:
    def __init__(self) -> None:
        self.events: dict[str, str] = {}; self.incidents: dict[str, dict[str, Any]] = {}
    def observe(self, event: Mapping[str, Any], *, safety_critical: bool = False) -> dict[str, Any]:
        valid = validate_event(event)
        digest = evidence_hash(valid)
        eid, iid, sig = valid["event_id"], valid["incident_id"], valid["sanitized_detection_signature"]
        if eid in self.events:
            if self.events[eid] != digest: raise ValidationError("mutable replay rejected")
            return self.pattern(sig, safety_critical=safety_critical, duplicate=True)
        self.events[eid] = digest
        if iid in self.incidents and self.incidents[iid]["digest"] != digest: raise ValidationError("contradictory incident replay")
        self.incidents.setdefault(iid, {"signature": sig, "digest": digest, "hashes": valid["evidence_hashes"]})
        return self.pattern(sig, safety_critical=safety_critical)
    def pattern(self, signature: str, *, safety_critical: bool = False, duplicate: bool = False) -> dict[str, Any]:
        matches = sorted(i for i, x in self.incidents.items() if x["signature"] == signature)
        eligible = len(matches) >= 2 and not safety_critical
        return validate_pattern({"schema_version": VERSION, "signature": signature, "incident_ids": matches,
                "independent_incident_count": len(matches), "duplicate_suppressed": duplicate,
                "promotion_eligible": eligible, "human_owner_review_required": safety_critical or eligible,
                "authority": "OPERATIONAL_EVIDENCE_ONLY"})

def build_hypothesis(hypothesis_id: str, proposed_cause: str, supporting: Iterable[str], contradicting: Iterable[str], proposed_test: str, test_status: str) -> dict[str, Any]:
    support, contradict = sorted(set(supporting)), sorted(set(contradicting))
    passed = test_status == "PASSED" and bool(support) and not contradict
    return {"hypothesis_id": hypothesis_id, "proposed_cause": proposed_cause,
            "supporting_incidents": support, "contradicting_incidents": contradict,
            "proposed_test": proposed_test, "test_status": test_status,
            "confidence_level": "VERIFIED" if passed else "UNVERIFIED",
            "promotion_eligible": passed, "rejection_reason": None if passed else "BOUNDED_TEST_NOT_PASSED_OR_CONTRADICTED"}

def learn(event: Mapping[str, Any]) -> dict[str, Any]:
    valid = validate_event(event)
    verified = valid["root_cause_status"] == "VERIFIED"
    return {"schema_version": VERSION, "lesson_status": "PROPOSED_OPERATIONAL_LESSON",
            "authority": "EVIDENCE_NOT_GOVERNANCE", "detection_signature": valid["sanitized_detection_signature"],
            "verified_root_cause": valid["verified_root_cause"] if verified else None,
            "root_cause_status": valid["root_cause_status"], "evidence_hashes": sorted(valid["evidence_hashes"]),
            "recovery_attempts": valid["recovery_attempts"], "recovery_result": valid["recovery_result"],
            "prevention_guidance": "Apply the bounded recovery action and rerun named validators.",
            "governance_promotion": "SEPARATE_HUMAN_OWNER_APPROVAL_REQUIRED"}

def transition(current: str, target: str) -> dict[str, Any]:
    if current == target: return {"state": current, "changed": False}
    if current not in TRANSITIONS or target not in TRANSITIONS[current]: raise ValidationError(f"invalid transition {current}->{target}")
    return {"state": target, "changed": True}

def validate_evidence_items(items: Any) -> list[dict[str, Any]]:
    """Return sanitized typed evidence without allowing cross-type inference."""
    if not isinstance(items, list): raise ValidationError("evidence must be an array")
    result = []
    for item in items:
        if not isinstance(item, Mapping) or set(item) - {"evidence_type", "reference", "evidence_hash", "source"}:
            raise ValidationError("malformed evidence item")
        if item.get("evidence_type") not in EVIDENCE_TYPES: raise ValidationError("unsupported evidence type")
        if not isinstance(item.get("reference"), str) or not item["reference"]: raise ValidationError("evidence reference required")
        if not isinstance(item.get("evidence_hash"), str) or not HEX_HASH.fullmatch(item["evidence_hash"]): raise ValidationError("evidence hash required")
        if item.get("source") is not None and not isinstance(item["source"], str): raise ValidationError("invalid evidence source")
        _walk(item); result.append(dict(item))
    return sorted(result, key=lambda x: (x["evidence_type"], x["reference"], x["evidence_hash"]))

def _finite_number(value: Any, field: str, *, required: bool = False) -> float | None:
    if value is None and not required: return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value): raise ValidationError(f"invalid {field}")
    return float(value)

def normalize_trade(record: Mapping[str, Any]) -> dict[str, Any]:
    """Extract supplied trade facts; absent optional facts remain unproven."""
    if not isinstance(record, Mapping): raise ValidationError("trade must be an object")
    required = ("trade_id", "status", "instrument", "side", "entry_timestamp", "exit_timestamp", "entry_price", "exit_price", "realized_pnl", "evidence")
    missing = [x for x in required if x not in record]
    if missing: raise ValidationError(f"missing trade fields: {missing}")
    if not isinstance(record["trade_id"], str) or not IDENTIFIER.fullmatch(record["trade_id"]): raise ValidationError("invalid trade ID")
    if record["status"] != "CLOSED":
        raise ValidationError("OPEN" if record["status"] == "OPEN" else "UNPROVEN_CLOSED_STATE")
    if record.get("qualifies") is False: raise ValidationError("NONQUALIFYING")
    if record["side"] not in SIDES or not isinstance(record["instrument"], str) or not record["instrument"]: raise ValidationError("malformed trade identity")
    entry = datetime.fromisoformat(str(record["entry_timestamp"]).replace("Z", "+00:00")); exit_ = datetime.fromisoformat(str(record["exit_timestamp"]).replace("Z", "+00:00"))
    if exit_ < entry: raise ValidationError("exit precedes entry")
    evidence = validate_evidence_items(record["evidence"])
    if not any(x["evidence_type"] == "trade_execution" for x in evidence): raise ValidationError("MISSING_REQUIRED_EVIDENCE")
    realized = _finite_number(record["realized_pnl"], "realized_pnl", required=True); fees = _finite_number(record.get("fees"), "fees")
    optional = ("signal_trigger", "strategy", "supertrend_period", "supertrend_multiplier", "stop_loss", "take_profit", "market_condition")
    normalized = {"trade_id": record["trade_id"], "instrument": record["instrument"], "side": record["side"],
        "entry_timestamp": record["entry_timestamp"], "exit_timestamp": record["exit_timestamp"],
        "entry_price": _finite_number(record["entry_price"], "entry_price", required=True), "exit_price": _finite_number(record["exit_price"], "exit_price", required=True),
        "realized_pnl": realized, "fees": fees, "net_pnl": realized - (fees or 0.0), "duration": (exit_ - entry).total_seconds(),
        "evidence_references": [x["reference"] for x in evidence], "evidence_hashes": [x["evidence_hash"] for x in evidence], "evidence": evidence}
    normalized.update({x: record.get(x) for x in optional}); normalized["metrics"] = deepcopy(record.get("metrics", {}))
    normalized["qualification_status"] = "QUALIFYING"
    return normalized

def qualify_trades(records: Any) -> dict[str, Any]:
    if not isinstance(records, list): raise ValidationError("trades must be an array")
    accepted, rejected, seen = [], [], set()
    for index, record in enumerate(records):
        trade_id = record.get("trade_id") if isinstance(record, Mapping) else None
        if trade_id in seen: rejected.append({"trade_id": trade_id, "reason": "DUPLICATE"}); continue
        try:
            trade = normalize_trade(record); seen.add(trade["trade_id"]); accepted.append(trade)
        except (ValidationError, ValueError, TypeError) as exc:
            reason = str(exc) if str(exc) in {"OPEN", "NONQUALIFYING", "UNPROVEN_CLOSED_STATE", "MISSING_REQUIRED_EVIDENCE"} else "MALFORMED"
            rejected.append({"trade_id": trade_id or f"INDEX:{index}", "reason": reason})
    return {"qualifying": accepted, "rejected": rejected}

def performance_statistics(trades: list[Mapping[str, Any]]) -> dict[str, Any]:
    ids = [x.get("trade_id") for x in trades]
    if len(ids) != len(set(ids)): raise ValidationError("duplicate qualifying trades")
    pnl = [_finite_number(x.get("net_pnl"), "net_pnl", required=True) for x in trades]
    wins, losses, breakeven = [x for x in pnl if x > 0], [x for x in pnl if x < 0], [x for x in pnl if x == 0]
    cumulative, equity, peak, drawdown = 0.0, [], 0.0, 0.0
    for value in pnl:
        cumulative += value; equity.append(cumulative); peak = max(peak, cumulative); drawdown = max(drawdown, peak - cumulative)
    total, gross_profit, gross_loss = len(pnl), sum(wins), abs(sum(losses))
    return {"total_trades": total, "wins": len(wins), "losses": len(losses), "breakeven": len(breakeven),
        "win_rate": len(wins) / total if total else None, "average_win": sum(wins) / len(wins) if wins else None,
        "average_loss": sum(losses) / len(losses) if losses else None, "gross_profit": gross_profit, "gross_loss": gross_loss,
        "net_pnl": sum(pnl), "profit_factor": gross_profit / gross_loss if gross_loss else (None if not gross_profit else "INFINITE"),
        "expectancy": sum(pnl) / total if total else None, "cumulative_pnl": equity, "max_drawdown": drawdown}

def classify_trade_patterns(trade: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics, pnl = trade.get("metrics", {}), trade.get("net_pnl")
    output = []
    evidence_types = {x.get("evidence_type") for x in trade.get("evidence", []) if isinstance(x, Mapping)}
    for name, (required, required_evidence_type) in PATTERN_REQUIREMENTS.items():
        present = isinstance(metrics, Mapping) and required <= set(metrics)
        typed = present and all(isinstance(metrics[x], (int, float)) and not isinstance(metrics[x], bool) and math.isfinite(metrics[x]) for x in required)
        evidenced = required_evidence_type in evidence_types
        proven = typed and evidenced
        matched = False
        if proven:
            if name == "FALSE_FLIP": matched = metrics["flip_count"] >= 1 and metrics["bars_to_reversal"] <= 2
            elif name == "LOW_VOLATILITY_WHIPSAW": matched = metrics["atr"] < metrics["atr_floor"] and metrics["reversal_count"] >= 2
            elif name == "RAPID_REVERSAL": matched = metrics["reversal_count"] >= 2 and metrics["duration_seconds"] <= 300
            elif name == "MULTIPLIER_SENSITIVITY": matched = metrics["supertrend_multiplier"] != metrics["comparison_multiplier"]
            elif name == "INSUFFICIENT_TREND_PERSISTENCE": matched = metrics["trend_bars"] < metrics["minimum_trend_bars"] and pnl is not None and pnl < 0
            elif name == "WINNER_TREND_PERSISTENCE": matched = metrics["trend_bars"] >= metrics["minimum_trend_bars"] and pnl is not None and pnl > 0
            elif name == "FAVORABLE_VOLATILITY_REGIME": matched = metrics["atr"] >= metrics["atr_floor"] and pnl is not None and pnl > 0
        reason = None if proven and matched else ("MISSING_METRICS" if not present else "MALFORMED_METRICS" if not typed else "MISSING_TYPED_EVIDENCE" if not evidenced else "CONDITION_NOT_MET")
        output.append({"pattern": name, "status": "PROVEN" if proven and matched else "NOT_PROVEN", "reason": reason,
            "required_evidence_type": required_evidence_type, "supporting_trade_id": trade.get("trade_id") if proven and matched else None})
    return output

def recommend_experiments(trades: list[Mapping[str, Any]], minimum_support: int = 2) -> list[dict[str, Any]]:
    if not isinstance(minimum_support, int) or minimum_support < 1: raise ValidationError("invalid recommendation threshold")
    mapping = {"MULTIPLIER_SENSITIVITY": "SUPERTREND_MULTIPLIER", "LOW_VOLATILITY_WHIPSAW": "ATR_VOLATILITY_FLOOR",
        "FALSE_FLIP": "CONFIRMATION_BAR", "RAPID_REVERSAL": "POST_FLIP_COOLDOWN", "INSUFFICIENT_TREND_PERSISTENCE": "TREND_PERSISTENCE"}
    support: dict[str, list[Mapping[str, Any]]] = {x: [] for x in mapping}
    for trade in trades:
        for pattern in classify_trade_patterns(trade):
            if pattern["status"] == "PROVEN" and pattern["pattern"] in support: support[pattern["pattern"]].append(trade)
    ranked = sorted(support.items(), key=lambda x: (-len(x[1]), x[0])); result = []
    for pattern, items in ranked:
        if not items: continue
        eligible = len(items) >= minimum_support
        result.append({"experiment_class": mapping[pattern], "observed_pattern": pattern,
            "supporting_trade_ids": sorted(x["trade_id"] for x in items),
            "supporting_evidence_refs": sorted({r for x in items for r in x["evidence_references"]}),
            "proposed_test": f"Run a bounded paper experiment for {mapping[pattern]} without changing runtime parameters.",
            "evidence_status": "ELIGIBLE" if eligible else "BLOCKED_BELOW_THRESHOLD", "authority": "ANALYSIS_ONLY"})
        if len(result) == 3: break
    return result

def progress_accounting(*, software_complete: float, qualifying_trade_ids: list[str] | None, evidence_items: list[Mapping[str, Any]] | None = None,
                        analyzed_trade_ids: list[str] | None = None, target_trades: int = 30, **untrusted_flags: Any) -> dict[str, Any]:
    if target_trades <= 0 or not 0 <= software_complete <= 100: raise ValidationError("invalid progress input")
    evidence = validate_evidence_items(evidence_items or [])
    types = {x["evidence_type"] for x in evidence}
    campaign_proven = {"campaign_runtime", "validation"} <= types
    ids_valid = isinstance(qualifying_trade_ids, list) and len(qualifying_trade_ids) == len(set(qualifying_trade_ids))
    qualifying: int | str = len(qualifying_trade_ids) if campaign_proven and ids_valid else "NOT_PROVEN"
    evidence_progress = min(100.0, qualifying / target_trades * 100) if isinstance(qualifying, int) else "NOT_PROVEN"
    analyzed = set(analyzed_trade_ids or [])
    analysis_proven = isinstance(qualifying, int) and set(qualifying_trade_ids or []) <= analyzed
    analysis: float | str = evidence_progress if analysis_proven else "NOT_PROVEN"
    release: float | str = min(software_complete, evidence_progress, analysis) if isinstance(evidence_progress, float) and isinstance(analysis, float) else "NOT_PROVEN"
    return {"software_complete": software_complete, "evidence_complete": evidence_progress, "trade_analysis_complete": analysis,
        "release_ready": release, "qualifying_trades": qualifying, "target_trades": target_trades}

def validate_analysis_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the closed top-level structure emitted by :func:`analyze_trades`."""
    required = {"trade_records", "qualification_results", "performance_statistics", "losing_patterns",
                "winning_patterns", "recommendations", "progress"}
    if not isinstance(result, Mapping) or set(result) != required: raise ValidationError("analysis result fields do not match closed contract")
    if not isinstance(result["trade_records"], list) or not isinstance(result["qualification_results"], list): raise ValidationError("invalid trade collections")
    trade_fields = {"trade_id", "instrument", "side", "entry_timestamp", "exit_timestamp", "entry_price", "exit_price",
        "signal_trigger", "strategy", "supertrend_period", "supertrend_multiplier", "stop_loss", "take_profit", "realized_pnl",
        "fees", "net_pnl", "duration", "market_condition", "evidence_references", "evidence_hashes", "qualification_status", "classification"}
    for trade in result["trade_records"]:
        if not isinstance(trade, Mapping) or set(trade) != trade_fields or trade["qualification_status"] != "QUALIFYING": raise ValidationError("malformed normalized trade")
        for field in ("entry_price", "exit_price", "realized_pnl", "net_pnl", "duration"):
            _finite_number(trade[field], field, required=True)
        if trade["fees"] is not None: _finite_number(trade["fees"], "fees", required=True)
        if not isinstance(trade["classification"], list): raise ValidationError("missing trade classifications")
    allowed_rejections = {"OPEN", "NONQUALIFYING", "UNPROVEN_CLOSED_STATE", "MALFORMED", "DUPLICATE", "MISSING_REQUIRED_EVIDENCE"}
    if any(not isinstance(x, Mapping) or set(x) != {"trade_id", "reason"} or x["reason"] not in allowed_rejections for x in result["qualification_results"]): raise ValidationError("malformed qualification result")
    stats = result["performance_statistics"]
    if not isinstance(stats, Mapping) or set(stats) != {"total_trades", "wins", "losses", "breakeven", "win_rate", "average_win", "average_loss", "gross_profit", "gross_loss", "net_pnl", "profit_factor", "expectancy", "cumulative_pnl", "max_drawdown"}: raise ValidationError("malformed statistics")
    if stats["total_trades"] != len(result["trade_records"]): raise ValidationError("statistics contradict trade records")
    if not isinstance(result["recommendations"], list) or len(result["recommendations"]) > 3: raise ValidationError("malformed recommendations")
    for recommendation in result["recommendations"]:
        if not isinstance(recommendation, Mapping) or recommendation.get("authority") != "ANALYSIS_ONLY" or not recommendation.get("supporting_trade_ids") or not recommendation.get("supporting_evidence_refs"): raise ValidationError("malformed recommendation")
    progress = result["progress"]
    if not isinstance(progress, Mapping) or set(progress) != {"software_complete", "evidence_complete", "trade_analysis_complete", "release_ready", "qualifying_trades", "target_trades"} or progress["target_trades"] != 30: raise ValidationError("malformed progress")
    if progress["evidence_complete"] != "NOT_PROVEN" and progress["qualifying_trades"] == "NOT_PROVEN": raise ValidationError("progress lacks evidence proof")
    _walk(result)
    return deepcopy(dict(result))

def analyze_trades(records: Any, *, minimum_recommendation_support: int = 2, campaign_evidence: list[Mapping[str, Any]] | None = None, **untrusted_flags: Any) -> dict[str, Any]:
    qualified = qualify_trades(records); trades = qualified["qualifying"]; stats = performance_statistics(trades)
    patterns = {x["trade_id"]: classify_trade_patterns(x) for x in trades}
    losing, winning = {}, {}
    for trade in trades:
        target = winning if trade["net_pnl"] > 0 else losing
        for p in patterns[trade["trade_id"]]:
            if p["status"] == "PROVEN":
                item = target.setdefault(p["pattern"], {"pattern": p["pattern"], "frequency": 0, "pnl_impact": 0.0})
                item["frequency"] += 1; item["pnl_impact"] += trade["net_pnl"]
    trade_fields = ("trade_id", "instrument", "side", "entry_timestamp", "exit_timestamp", "entry_price", "exit_price", "signal_trigger", "strategy", "supertrend_period", "supertrend_multiplier", "stop_loss", "take_profit", "realized_pnl", "fees", "net_pnl", "duration", "market_condition", "evidence_references", "evidence_hashes", "qualification_status")
    result = {"trade_records": [{**{k: x.get(k) for k in trade_fields}, "classification": patterns[x["trade_id"]]} for x in trades],
        "performance_statistics": stats, "qualification_results": qualified["rejected"],
        "losing_patterns": sorted(losing.values(), key=lambda x: (-x["frequency"], x["pnl_impact"], x["pattern"])),
        "winning_patterns": sorted(winning.values(), key=lambda x: (-x["frequency"], -x["pnl_impact"], x["pattern"])),
        "recommendations": recommend_experiments(trades, minimum_recommendation_support),
        "progress": progress_accounting(software_complete=100.0, qualifying_trade_ids=[x["trade_id"] for x in trades],
            evidence_items=campaign_evidence, analyzed_trade_ids=[x["trade_id"] for x in trades])}
    return validate_analysis_result(result)

class PostmortemEngine:
    def __init__(self) -> None: self.seen_event_ids: set[str] = set(); self.patterns = PatternMemory()
    def analyze(self, event: Mapping[str, Any]) -> dict[str, Any]: return validate_event(event, self.seen_event_ids)
    def classify(self, facts: Mapping[str, Any]) -> dict[str, str]: return classify(facts)
    def learn(self, event: Mapping[str, Any]) -> dict[str, Any]: return learn(event)
    def plan(self, facts: Mapping[str, Any]) -> dict[str, str]: return classify(facts)
    def verify(self, facts: Mapping[str, Any]) -> dict[str, Any]: return {"verified": bool(facts.get("validators_passed") and facts.get("evidence_intact")), "state": "VERIFIED" if facts.get("validators_passed") and facts.get("evidence_intact") else "REVIEW_REQUIRED"}
    def close(self, state: str) -> dict[str, Any]: return transition(state, "CLOSED")
    def analyze_trades(self, records: Any, **kwargs: Any) -> dict[str, Any]: return analyze_trades(records, **kwargs)

def _safe_output(path: str) -> Path:
    candidate = Path(path)
    resolved_root = (Path.cwd() / REPORT_ROOT).resolve()
    resolved = (Path.cwd() / candidate).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents: raise ValidationError("output path outside approved report root")
    return resolved

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("analyze", "classify", "learn", "plan", "verify", "close")); parser.add_argument("input"); parser.add_argument("--output")
    args = parser.parse_args(argv); data = json.loads(Path(args.input).read_text(encoding="utf-8")); engine = PostmortemEngine()
    result = getattr(engine, args.command)(data if args.command != "close" else str(data["state"]))
    rendered = canonical_json(result) + "\n"
    if args.output:
        output = _safe_output(args.output); output.parent.mkdir(parents=True, exist_ok=True); output.write_text(rendered, encoding="utf-8")
    else: print(rendered, end="")
    return 0

if __name__ == "__main__": raise SystemExit(main())
