"""Deterministic evidence bridge for forex paper-to-demo review readiness.

This module converts heterogeneous candidate/evidence inputs into a single
deterministic review bundle used by downstream dashboard/report consumers.
It is paper-only and intentionally does not perform I/O or network calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional


Verdict = str


DEMO_REVIEW_READY = "DEMO_REVIEW_READY"
PAPER_CONTINUE = "PAPER_CONTINUE"
REJECTED = "REJECTED"
BLOCKED_INCOMPLETE_EVIDENCE = "BLOCKED_INCOMPLETE_EVIDENCE"


DEFAULT_MAX_FRESHNESS_AGE_HOURS = 30


METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "expectancy": ("expectancy", "expected_value", "paper_expectancy"),
    "profit_factor": ("profit_factor", "pf"),
    "win_rate": ("win_rate", "winrate"),
    "max_drawdown": ("max_drawdown", "drawdown"),
    "sample_size": ("sample_size", "total_trades", "trades"),
    "walk_forward_status": ("walk_forward_status", "walkforward_status"),
    "paper_evidence_status": ("paper_evidence_status", "paper_evidence"),
    "mitigation_status": ("mitigation_status", "mitigation"),
}


PROOF_FIELDS = (
    "replay",
    "reconciliation",
    "kill_switch",
    "rollback",
    "risk",
    "demo_validation",
    "freshness",
)

PROOF_ALIASES: dict[str, tuple[str, ...]] = {
    "replay": ("replay", "replay_proof", "session_replay"),
    "reconciliation": ("reconciliation", "reconciliation_proof", "recon"),
    "kill_switch": ("kill_switch", "kill_switch_proof", "killswitch", "kill-switch"),
    "rollback": ("rollback", "rollback_proof", "roll_back"),
    "risk": ("risk", "risk_proof", "risk_evidence"),
    "demo_validation": ("demo_validation", "demo_validation_proof", "demo"),
    "freshness": ("freshness", "freshness_proof", "evidence_freshness", "evidence_age"),
}

def _first_match(data: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    for key in aliases:
        if key in data:
            return data[key]
    lowered = {str(k).lower().replace(" ", "_"): v for k, v in data.items()}
    for key in aliases:
        normalized_key = key.lower().replace("-", "_").replace(" ", "_")
        if normalized_key in lowered:
            return lowered[normalized_key]
    return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {"true", "pass", "passed", "ok", "ready", "complete", "completed", "green"}:
            return True
        if normalized in {"false", "fail", "failed", "reject", "blocked", "red"}:
            return False
    if isinstance(value, Mapping):
        for candidate in ("passed", "pass", "valid", "approved", "confirmed", "ready"):
            if candidate in value:
                return _truthy(value[candidate])
        return bool(value)
    return bool(value)


def _normalize_proof(value: Any, *, freshness_window_hours: float, now: Optional[datetime] = None) -> dict[str, Any]:
    if value is None:
        return {"status": False, "evidence": None, "reason": "missing"}

    if isinstance(value, bool):
        return {"status": bool(value), "evidence": value, "reason": None if value else "explicit_false"}

    if isinstance(value, str):
        status = _truthy(value)
        return {"status": status, "evidence": {"raw": value}, "reason": None if status else "explicit_false"}

    if isinstance(value, Mapping):
        if "freshness" in value or "age_hours" in value or "timestamp" in value:
            parsed = _normalize_freshness(value, freshness_window_hours=freshness_window_hours, now=now)
            return {
                "status": parsed["status"],
                "evidence": value,
                "reason": parsed.get("reason"),
            }

        status = _truthy(value)
        return {"status": status, "evidence": value, "reason": None if status else "explicit_false"}

    return {"status": bool(value), "evidence": value, "reason": None if bool(value) else "explicit_false"}


def _to_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(s)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _normalize_freshness(value: Mapping[str, Any], *, freshness_window_hours: float, now: Optional[datetime] = None) -> dict[str, Any]:
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if "age_hours" in value:
        age = _coerce_float(value.get("age_hours"))
        if age is None:
            return {"status": False, "evidence": value, "reason": "invalid_age"}
        if age <= freshness_window_hours:
            return {"status": True, "evidence": value, "reason": None}
        return {"status": False, "evidence": value, "reason": f"freshness_stale_{age}h"}

    if "timestamp" in value or "as_of" in value or "captured_at" in value or "at" in value:
        raw_time = value.get("timestamp", value.get("as_of", value.get("captured_at", value.get("at"))))
        parsed = _to_datetime(raw_time)
        if parsed is None:
            return {"status": False, "evidence": value, "reason": "invalid_timestamp"}
        age_hours = (current_time - parsed.astimezone(timezone.utc)).total_seconds() / 3600.0
        if age_hours <= freshness_window_hours:
            return {"status": True, "evidence": value, "reason": None}
        return {"status": False, "evidence": value, "reason": f"freshness_stale_{age_hours:.4f}h"}
    return {"status": False, "evidence": value, "reason": "missing_timestamp"}


@dataclass(frozen=True)
class BridgeThresholds:
    min_expectancy: float = 0.0
    min_profit_factor: float = 1.1
    max_drawdown: float = 0.12
    min_sample_size: int = 30
    min_win_rate: float = 0.40
    require_walk_forward_pass: bool = True
    require_mitigation_not_worse: bool = True
    require_all_proofs: bool = True
    max_freshness_age_hours: int = DEFAULT_MAX_FRESHNESS_AGE_HOURS


def _normalize_metric(value: Mapping[str, Any], key: str) -> Optional[float | int | str | bool]:
    aliases = METRIC_ALIASES.get(key)
    if not aliases:
        return None
    raw = _first_match(value, aliases)
    if raw is None:
        return None
    if key in {"walk_forward_status", "paper_evidence_status", "mitigation_status"}:
        return str(raw)
    return _coerce_float(raw) if key != "sample_size" else (
        None if _coerce_float(raw) is None else int(_coerce_float(raw) or 0)
    )


def _normalize_candidate_identity(candidate: Mapping[str, Any]) -> tuple[str, str, str, str]:
    candidate_id = str(candidate.get("candidate_id", candidate.get("id", "") or "unknown"))
    strategy = str(candidate.get("strategy", candidate.get("strategy_name", "")) or "unknown")
    pair = str(candidate.get("pair", candidate.get("symbol", "") or "unknown"))
    direction = str(candidate.get("direction", "") or "unknown")
    direction = direction.strip().lower().replace("_", "-") if direction else "unknown"
    return candidate_id, strategy, pair, direction


def _proof_key_matches(candidate: Mapping[str, Any], proof_name: str) -> bool:
    aliases = {
        "walk_forward": ("walk_forward", "walk_forward_status", "walk_forward_proof", "walkforward_status"),
        "paper_evidence": ("paper_evidence", "paper_evidence_status", "paper_evidence_proof"),
        "mitigation": ("mitigation", "mitigation_status"),
    }
    lookup = [proof_name] + list(aliases.get(proof_name, ()))
    return any(key in candidate for key in lookup)


def _walk_forward_status(value: Any, thresholds: BridgeThresholds) -> tuple[str, str]:
    status = str(value).strip().lower().replace("-", "_")
    status = re.sub(r"\\s+", "_", status)
    if status in {"pass", "passed", "pass_strong", "pass_stable", "ready"}:
        return "pass", ""
    if status in {"warn", "warning", "marginal", "partial", "weak", "greenish"}:
        return "warn", "walk-forward evidence marginal"
    if status in {"blocked", "fail", "failed", "red", "material_fail"}:
        return "fail", "walk-forward evidence materially failed"
    if status in {"unknown", "", "none", "pending"}:
        return "pending", "walk-forward evidence not finalized"
    return "fail", f"walk-forward evidence status unrecognized:{status}"


def build_review_bundle(
    candidate: Mapping[str, Any],
    thresholds: BridgeThresholds | None = None,
) -> dict[str, Any]:
    config = thresholds or BridgeThresholds()

    candidate_id, strategy, pair, direction = _normalize_candidate_identity(candidate)
    metrics: dict[str, Any] = {
        "expectancy": _normalize_metric(candidate, "expectancy"),
        "profit_factor": _normalize_metric(candidate, "profit_factor"),
        "max_drawdown": _normalize_metric(candidate, "max_drawdown"),
        "win_rate": _normalize_metric(candidate, "win_rate"),
        "sample_size": _normalize_metric(candidate, "sample_size"),
        "walk_forward_status": _normalize_metric(candidate, "walk_forward_status"),
        "paper_evidence_status": _normalize_metric(candidate, "paper_evidence_status"),
        "mitigation_status": _normalize_metric(candidate, "mitigation_status"),
    }

    proof_values = {
        key: _first_match(candidate, aliases)
        for key, aliases in PROOF_ALIASES.items()
    }

    proofs = {
        key: _normalize_proof(
            value,
            freshness_window_hours=float(config.max_freshness_age_hours),
            now=datetime.now(timezone.utc),
        )
        for key, value in proof_values.items()
    }

    # Ensure all PROOF_FIELDS exist in normalized output.
    for proof_key in PROOF_FIELDS:
        proofs.setdefault(proof_key, _normalize_proof(None, freshness_window_hours=float(config.max_freshness_age_hours), now=datetime.now(timezone.utc)))

    wf_status_norm, wf_msg = _walk_forward_status(metrics["walk_forward_status"] or "", config)
    walk_forward_pass = wf_status_norm == "pass"
    if metrics["walk_forward_status"] is not None:
        metrics["walk_forward_status"] = wf_status_norm if wf_status_norm != "" else metrics["walk_forward_status"]

    legacy_metric_complete = all(
        metrics.get(key) is not None
        for key in (
            "expectancy",
            "profit_factor",
            "max_drawdown",
            "win_rate",
            "sample_size",
            "walk_forward_status",
        )
    )

    metric_reject_blockers: list[str] = []
    proof_blockers: list[str] = []
    continuation_blockers: list[str] = []

    expectancy = metrics["expectancy"]
    profit_factor = metrics["profit_factor"]
    max_drawdown = metrics["max_drawdown"]
    sample_size = metrics["sample_size"]
    win_rate = metrics["win_rate"]
    paper_evidence_status = metrics["paper_evidence_status"]
    mitigation_status = metrics["mitigation_status"]
    sample_depth_sufficient = sample_size is not None and int(sample_size) >= config.min_sample_size
    sample_depth_insufficient = sample_size is not None and int(sample_size) < config.min_sample_size

    if metrics["walk_forward_status"] is None:
        metric_reject_blockers.append("missing_walk_forward_status")

    if sample_size is None:
        metric_reject_blockers.append("missing_sample_size")

    for proof_key in PROOF_FIELDS:
        status = proofs.get(proof_key, {}).get("status", False)
        if proof_key == "freshness":
            if not status:
                proof_blockers.append("stale_freshness_or_missing")
        elif not status:
            proof_blockers.append(f"missing_{proof_key}_proof")

    # Reject blockers from deterministic thresholds only after sample depth is sufficient.
    if sample_depth_sufficient:
        if expectancy is None:
            metric_reject_blockers.append("missing_expectancy")
        elif expectancy <= config.min_expectancy:
            metric_reject_blockers.append("negative_or_zero_expectancy")

        if profit_factor is None:
            metric_reject_blockers.append("missing_profit_factor")
        elif profit_factor < config.min_profit_factor:
            metric_reject_blockers.append("profit_factor_below_minimum")

        if max_drawdown is None:
            metric_reject_blockers.append("missing_max_drawdown")
        elif max_drawdown > config.max_drawdown:
            metric_reject_blockers.append("excessive_drawdown")

        if win_rate is None:
            metric_reject_blockers.append("missing_win_rate")
        elif win_rate < config.min_win_rate:
            metric_reject_blockers.append("low_win_rate")

    if _proof_key_matches(candidate, "paper_evidence") and paper_evidence_status is None:
        proof_blockers.append("missing_paper_evidence_status")
    elif isinstance(paper_evidence_status, str) and paper_evidence_status.strip().lower() not in {"pass", "passed", "ready"}:
        continuation_blockers.append("paper_evidence_not_ready")

    if _proof_key_matches(candidate, "mitigation") and mitigation_status is None:
        continuation_blockers.append("missing_mitigation_status")
    elif config.require_mitigation_not_worse and isinstance(mitigation_status, str):
        if mitigation_status.strip().lower() in {"worse", "regression", "declining", "failed"}:
            continuation_blockers.append("mitigation_worsened")

    if sample_depth_insufficient:
        continuation_blockers.append("insufficient_sample")

    if config.require_walk_forward_pass and not walk_forward_pass:
        if wf_status_norm == "warn":
            continuation_blockers.append("walk_forward_warning_not_ready")
        elif wf_status_norm == "pending":
            continuation_blockers.append("walk_forward_pending")
        else:
            metric_reject_blockers.append("walk_forward_failed")

    if config.require_all_proofs and proof_blockers:
        verdict: Verdict = BLOCKED_INCOMPLETE_EVIDENCE
        next_safe_action = "Collect missing/valid proofs and refresh stale evidence before rerunning review."
        return {
            "candidate_id": candidate_id,
            "strategy": strategy,
            "pair": pair,
            "direction": direction,
            "verdict": verdict,
            "blockers": proof_blockers + metric_reject_blockers + continuation_blockers,
            "next_safe_action": next_safe_action,
            "metrics": metrics,
            "proofs": proofs,
            "thresholds": asdict(config),
            "walk_forward": wf_status_norm,
            "walk_forward_detail": wf_msg,
        }

    if metric_reject_blockers:
        verdict = REJECTED
        if metric_reject_blockers == ["missing_expectancy"]:
            verdict = BLOCKED_INCOMPLETE_EVIDENCE
            next_safe_action = "Collect missing expectation evidence and rerun review."
        elif metric_reject_blockers == ["missing_profit_factor"]:
            verdict = BLOCKED_INCOMPLETE_EVIDENCE
            next_safe_action = "Collect missing profit-factor evidence and rerun review."
        elif metric_reject_blockers == ["missing_max_drawdown"]:
            verdict = BLOCKED_INCOMPLETE_EVIDENCE
            next_safe_action = "Collect missing drawdown evidence and rerun review."
        else:
            next_safe_action = "Reject candidate and re-optimize candidate metrics."
        return {
            "candidate_id": candidate_id,
            "strategy": strategy,
            "pair": pair,
            "direction": direction,
            "verdict": verdict,
            "blockers": proof_blockers + metric_reject_blockers + continuation_blockers,
            "next_safe_action": next_safe_action,
            "metrics": metrics,
            "proofs": proofs,
            "thresholds": asdict(config),
            "walk_forward": wf_status_norm,
            "walk_forward_detail": wf_msg,
        }

    if sample_depth_sufficient and expectancy is not None and expectancy <= 0:
        verdict = REJECTED
        next_safe_action = "Reject candidate and route to strategy re-optimization."
    elif sample_depth_sufficient and profit_factor is not None and profit_factor < config.min_profit_factor:
        verdict = REJECTED
        next_safe_action = "Re-optimize candidate metrics; profit factor below threshold."
    elif sample_depth_sufficient and max_drawdown is not None and max_drawdown > config.max_drawdown:
        verdict = REJECTED
        next_safe_action = "Reject candidate and reduce risk profile; drawdown exceeds cap."
    elif wf_status_norm == "fail":
        verdict = REJECTED
        next_safe_action = "Reject candidate until walk-forward failure is resolved."
    elif sample_size is None:
        verdict = PAPER_CONTINUE
        next_safe_action = "Run more paper trades to establish minimum sample size."
    elif int(sample_size) < config.min_sample_size:
        verdict = PAPER_CONTINUE
        next_safe_action = "Gather additional paper evidence until sample_size meets minimum."
    elif wf_status_norm == "warn":
        verdict = PAPER_CONTINUE
        next_safe_action = "Strengthen walk-forward stability before promotion consideration."
    elif (
        expectancy is not None
        and expectancy > config.min_expectancy
        and not proof_blockers
        and walk_forward_pass
        and (sample_size is None or int(sample_size) >= config.min_sample_size)
        and (win_rate is None or float(win_rate) >= config.min_win_rate)
    ):
        verdict = DEMO_REVIEW_READY
        next_safe_action = "Prepare demo-review packet with consolidated proof bundle."
    else:
        verdict = PAPER_CONTINUE
        next_safe_action = "Increase evidence maturity or fix weak proof gates."

    # Safety net: any negative expectancy or clear loss gate remains rejected once
    # sample depth is sufficient enough to make the metric statistically meaningful.
    if sample_depth_sufficient and expectancy is not None and expectancy <= 0 and verdict != REJECTED:
        verdict = REJECTED
        next_safe_action = "Reject candidate due to non-positive expectancy."

    return {
        "candidate_id": candidate_id,
        "strategy": strategy,
        "pair": pair,
        "direction": direction,
        "verdict": verdict,
        "blockers": proof_blockers + metric_reject_blockers + continuation_blockers,
        "next_safe_action": next_safe_action,
        "metrics": metrics,
        "proofs": proofs,
        "thresholds": asdict(config),
        "walk_forward": wf_status_norm,
        "walk_forward_detail": wf_msg,
    }


def has_demo_ready(candidate: Mapping[str, Any], thresholds: BridgeThresholds | None = None) -> bool:
    """Return True when candidate verdict is `DEMO_REVIEW_READY`."""
    return build_review_bundle(candidate, thresholds)["verdict"] == DEMO_REVIEW_READY

