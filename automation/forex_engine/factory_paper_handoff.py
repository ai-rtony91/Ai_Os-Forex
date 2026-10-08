"""Offline connector from accepted research lineage to canonical paper review.

This is an engineering contract check, not a readiness authority or a runner.
The caller must supply a trusted verifier which independently rereads immutable
saved artifacts and accepted ledger entries, and verifies market provenance.
Hashes check consistency; they cannot establish that market evidence is genuine.
No verifier, prices, profitable metrics, freshness, or proof is supplied by default.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Callable

from . import proof_bundle_to_candidate_bridge as canonical_bridge
from . import optuna_campaign_budget as campaign_budget
from .paper_forward_simulator import paper_forward_summary, run_paper_forward_simulation
from .paper_risk_governor import evaluate_paper_trade_risk
from .paper_session_replay import build_paper_session_replay
from .risk_governor import evaluate_risk_preview
from .long_run_paper_supervisor import run_paper_supervisor_cycle
from .schema_contracts import Candle, MarketDataFixture, OrderIntent

ArtifactVerifier = Callable[[str, dict[str, Any], dict[str, Any] | None, Any], dict[str, Any]]
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_IDENTITY = ("candidate_id", "strategy", "pair", "direction")
_STABLE = ("contract_hash", "proposal_hash", "parameter_sha256", "cost_sha256", "risk_sha256",
           "implementation_sha256", "objective_sha256")
_PROVENANCE = {"fixture_only": False, "synthetic_only": False, "canned": False,
               "default_generated": False, "development_used": False, "selection_used": False,
               "untouched": True, "after_cost": True}
_DEVELOPMENT_MARKERS = ("fixture", "synthetic", "canned", "default", "development_only",
                        "development_used", "engineering_dry_run")
MIN_TRADES_PER_SIDE = 30
MIN_PROFIT_FACTOR = 1.10
MAX_DRAWDOWN = 0.10
MAX_FRESHNESS_HOURS = canonical_bridge.canonical_demo_review_evidence_bridge.DEFAULT_MAX_FRESHNESS_AGE_HOURS


def artifact_digest(value: Any) -> str:
    """Canonical JSON digest, also used by external immutable-artifact verifiers."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def _fresh(value: Any, now: datetime) -> bool:
    at = _time(value)
    return at is not None and 0 <= (now - at).total_seconds() <= MAX_FRESHNESS_HOURS * 3600


def _interval(value: Any) -> tuple[datetime, datetime] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    start, end = map(_time, value)
    return (start, end) if start is not None and end is not None and start < end else None


def _same_metrics(actual: Any, expected: dict[str, float]) -> bool:
    actual = _mapping(actual)
    return all(_number(actual.get(k)) and math.isclose(actual[k], v, abs_tol=1e-9,
                                                     rel_tol=1e-9) for k, v in expected.items())


def _has_development_source(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in _PROVENANCE and _PROVENANCE[key] is False and nested is not False:
                return True
            if key in {"source", "origin", "provider", "evidence_source", "source_kind", "source_type", "mode", "proof_level"}:
                if isinstance(nested, str) and any(marker in nested.lower() for marker in _DEVELOPMENT_MARKERS):
                    return True
            if _has_development_source(nested):
                return True
    elif isinstance(value, list):
        return any(_has_development_source(nested) for nested in value)
    return False


def _trusted(kind: str, artifact: dict[str, Any], ledger_entry: dict[str, Any] | None,
             global_ledger: Any, selection: dict[str, Any], verifier: ArtifactVerifier | None,
             blockers: list[str]) -> None:
    """Accept exact reread bindings only; status labels and boolean success fail."""
    receipt = artifact.get("accepted_receipt", artifact.get("actual_receipt"))
    try:
        verified = verifier(kind, artifact, ledger_entry, global_ledger) if callable(verifier) else None
        expected = {"artifact_sha256": artifact_digest(artifact),
                    "receipt_sha256": artifact_digest(receipt),
                    "ledger_entry_sha256": artifact_digest(ledger_entry) if ledger_entry else None,
                    "global_ledger_sha256": artifact_digest(global_ledger),
                    "frozen_selection_sha256": artifact_digest(selection),
                    "research_split_sha256": artifact_digest(selection.get("research_split")),
                    "source_verified": True, "input_verified": True,
                    "acceptance_verified": True, "immutable_artifact_verified": True,
                    "selection_frozen_verified": True, "split_verified": True}
        if kind != "research_artifact":
            expected["untouched_verified"] = True
        if not isinstance(verified, dict) or any(verified.get(k) != v or
                (type(v) is bool and verified.get(k) is not v) for k, v in expected.items()):
            blockers.append(f"{kind}_trusted_verification_failed")
    except Exception:
        # Do not echo external verifier exceptions: they may contain private paths/data.
        blockers.append(f"{kind}_trusted_verification_failed")


def _economics(kind: str, evidence: dict[str, Any], candidate: dict[str, Any],
               evaluation: tuple[datetime, datetime] | None, blockers: list[str]) -> dict[str, float]:
    result = _mapping(evidence.get("result"))
    trades = result.get("trades")
    starting = result.get("starting_equity")
    if not isinstance(trades, list) or not trades or not _number(starting) or starting <= 0:
        blockers.append(f"{kind}_missing_trade_economics")
        return {}
    ids, pnl = [], []
    equity = peak = starting
    max_drawdown = 0.0
    previous_at = None
    records = _mapping(evidence.get("input")).get("records", [])
    record_times = {row.get("timestamp") for row in records
                    if isinstance(row, dict) and isinstance(row.get("timestamp"), str)} if isinstance(records, list) else set()
    for trade in trades:
        trade = _mapping(trade)
        at = _time(trade.get("timestamp"))
        gross, cost, net = (trade.get(key) for key in ("gross_pnl", "cost", "net_pnl"))
        valid = (isinstance(trade.get("trade_id"), str) and bool(trade["trade_id"])
                 and trade.get("direction") == candidate.get("direction")
                 and isinstance(trade.get("timestamp"), str) and trade["timestamp"] in record_times and at is not None
                 and evaluation is not None and evaluation[0] <= at < evaluation[1]
                 and all(_number(n) for n in (gross, cost, net)) and cost >= 0
                 and math.isclose(gross - cost, net, abs_tol=1e-9))
        if not valid:
            blockers.append(f"{kind}_invalid_or_pre_cost_trade")
            continue
        if previous_at is not None and at <= previous_at:
            # Drawdown is path-dependent. Ambiguous or rearranged close order
            # cannot supply an authenticated equity path for this contract.
            blockers.append(f"{kind}_nonchronological_trade_evidence")
        previous_at = at
        ids.append(trade["trade_id"])
        pnl.append(net)
        equity += net
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)
    if len(ids) != len(set(ids)):
        blockers.append(f"{kind}_duplicate_trade_ids")
    if len(pnl) < MIN_TRADES_PER_SIDE:
        blockers.append(f"{kind}_insufficient_trades_per_side")
    gains = sum(n for n in pnl if n > 0)
    losses = -sum(n for n in pnl if n < 0)
    # No arbitrary finite replacement for an undefined all-winner profit factor.
    if not pnl or losses <= 0:
        blockers.append(f"{kind}_profit_factor_not_estimable")
        return {}
    metrics = {"sample_size": len(pnl), "expectancy": sum(pnl) / len(pnl),
               "profit_factor": gains / losses, "max_drawdown": max_drawdown,
               "win_rate": sum(n > 0 for n in pnl) / len(pnl)}
    if not _same_metrics(result.get("summary"), metrics):
        blockers.append(f"{kind}_contradictory_summary_metrics")
    if metrics["expectancy"] <= 0 or metrics["profit_factor"] < MIN_PROFIT_FACTOR or max_drawdown > MAX_DRAWDOWN:
        blockers.append(f"{kind}_after_cost_thresholds_failed")
    return metrics


def _operations(evidence: dict[str, Any], metrics: dict[str, float], now: datetime,
                blockers: list[str]) -> None:
    result = _mapping(evidence.get("result"))
    operations = _mapping(result.get("operations"))
    trades = result.get("trades")
    if (not operations or not metrics or not isinstance(trades, list)
            or not _number(result.get("starting_equity"))
            or any(not isinstance(t, dict) or not _number(t.get("net_pnl")) for t in trades)):
        blockers.append("paper_validation_missing_or_invalid_operational_evidence")
        return
    risk_policy = _mapping(evidence.get("risk_policy"))
    probes = operations.get("risk_probes")
    required = {"safe": None, "stop": "stop_required", "daily_loss": "max_daily_loss_hit", "stale": "stale_data"}
    seen = set()
    if isinstance(probes, list):
        for probe in probes:
            probe = _mapping(probe)
            label = probe.get("label")
            if not isinstance(label, str) or label not in required or label in seen:
                blockers.append("paper_validation_invalid_risk_probe")
                continue
            seen.add(label)
            try:
                at = probe.get("now_timestamp")
                if not _number(at) or not 0 <= now.timestamp() - at <= MAX_FRESHNESS_HOURS * 3600:
                    blockers.append("paper_validation_stale_or_future_risk_probe")
                observed = _mapping(probe.get("observed_result"))
                actual = evaluate_paper_trade_risk(probe["candidate"], probe["account_state"], [],
                                                   risk_policy, probe["now_timestamp"])
                if probe.get("limits") != risk_policy or actual != observed or (
                    actual["risk_passed"] is not (label == "safe")
                    or (required[label] is not None and required[label] not in actual["rejection_reasons"])
                ):
                    blockers.append("paper_validation_risk_probe_mismatch")
            except (KeyError, TypeError, ValueError, OverflowError):
                blockers.append("paper_validation_invalid_risk_probe")
    if seen != set(required):
        blockers.append("paper_validation_missing_risk_probes")

    kill = _mapping(operations.get("kill_switch"))
    try:
        observed = _mapping(kill.get("observed_result"))
        actual = evaluate_risk_preview(kill["preview"], account_state=kill["account_state"],
                                       now_timestamp=kill["now_timestamp"])
        if (kill["account_state"].get("kill_switch_active") is not True
                or not _fresh(kill.get("now_timestamp"), now)
                or actual != observed or actual["allowed"] is not False
                or "kill_switch_active" not in actual["blocked_reasons"]
                or type(kill.get("fills_created")) is not int or kill["fills_created"] != 0):
            blockers.append("paper_validation_kill_switch_not_proven_before_fill")
    except (KeyError, TypeError, ValueError, OverflowError):
        blockers.append("paper_validation_kill_switch_not_proven_before_fill")

    trade_ids = [trade.get("trade_id") for trade in trades if isinstance(trade, dict)]
    ending = result.get("starting_equity", 0) + sum(t.get("net_pnl", 0) for t in trades if isinstance(t, dict))
    restart = _mapping(operations.get("restart"))
    before, after = (_mapping(restart.get(key)) for key in ("before_state", "after_state"))
    if (not before or before != after or before.get("trade_ids") != trade_ids
            or before.get("pending_jobs") != [] or not _number(before.get("ending_equity"))
            or not math.isclose(before["ending_equity"], ending, abs_tol=1e-9)
            or restart.get("before_state_sha256") != artifact_digest(before)
            or restart.get("after_state_sha256") != artifact_digest(after)
            or restart.get("duplicate_trade_ids") != [] or restart.get("redispatched_job_ids") != []):
        blockers.append("paper_validation_restart_reentry_or_state_mismatch")
    obs = _mapping(operations.get("observability"))
    events = obs.get("events")
    try:
        replay = build_paper_session_replay(events, result["starting_equity"], ending)
        closes = [e["payload"] for e in events if e.get("event_type") == "paper_trade_closed"]
        closed_ids = [e["trade_id"] for e in closes]
        if (not isinstance(operations.get("session_id"), str) or not operations["session_id"]
                or obs.get("session_id") != operations["session_id"] or not _fresh(obs.get("heartbeat_at"), now)
                or obs.get("trade_event_ids") != trade_ids or obs.get("replayed_trade_ids") != trade_ids
                or closed_ids != trade_ids or replay != obs.get("replay")
                or any(not _number(event.get("realized_pl")) or not math.isclose(event["realized_pl"], trade["net_pnl"], abs_tol=1e-9)
                       for event, trade in zip(closes, trades))
                or not math.isclose(replay["realized_pl"], ending - result["starting_equity"], abs_tol=1e-9)
                or replay["closed_trade_count"] != metrics.get("sample_size")
                or replay["missing_evidence_warnings"]):
            blockers.append("paper_validation_observability_or_replay_mismatch")
    except (KeyError, TypeError, ValueError, AttributeError):
        blockers.append("paper_validation_observability_or_replay_mismatch")


def _evidence(kind: str, payload: dict[str, Any], candidate: dict[str, Any], stable: dict[str, Any],
              now: datetime, verifier: ArtifactVerifier | None, blockers: list[str]) -> dict[str, float]:
    evidence = _mapping(payload.get(kind))
    if not evidence:
        blockers.append(f"missing_{kind}")
        return {}
    phase = "confirmation" if kind == "independent_proof" else "paper_validation"
    binding, job, result, source, inputs = (_mapping(evidence.get(k)) for k in ("binding", "job", "result", "source", "input"))
    if evidence.get("schema") != "AIOS_FACTORY_EVIDENCE_V1" or evidence.get("kind") != kind:
        blockers.append(f"{kind}_invalid_evidence_contract")
    if _has_development_source(evidence):
        blockers.append(f"{kind}_development_or_canned_source")
    safety_gaps = canonical_bridge._source_safety_gaps(evidence)
    blockers.extend(f"{kind}_unsafe_{gap}" for gap in safety_gaps)
    for field, expected in _PROVENANCE.items():
        if _mapping(evidence.get("provenance")).get(field) is not expected:
            blockers.append(f"{kind}_invalid_provenance_{field}")
    for name in _STABLE:
        if not _hash(binding.get(name)) or binding.get(name) != stable.get(name):
            blockers.append(f"{kind}_frozen_{name}_mismatch")
    expected_digests = {"parameter_sha256": artifact_digest(evidence.get("parameters")),
                        "source_sha256": artifact_digest(source), "input_sha256": artifact_digest(inputs),
                        "data_sha256": artifact_digest(inputs.get("records")),
                        "split_sha256": artifact_digest(evidence.get("split")),
                        "cost_sha256": artifact_digest(evidence.get("cost_model")),
                        "risk_sha256": artifact_digest(evidence.get("risk_policy")),
                        "spec_sha256": artifact_digest(job)}
    if any(binding.get(k) != v for k, v in expected_digests.items()):
        blockers.append(f"{kind}_source_input_spec_binding_mismatch")
    if (evidence.get("candidate") != candidate or job.get("candidate") != candidate or result.get("candidate") != candidate
            or job.get("phase") != phase or result.get("phase") != phase or inputs.get("phase") != phase
            or not isinstance(job.get("job_id"), str) or not job["job_id"] or result.get("job_id") != job["job_id"]
            or result.get("binding") != binding or job.get("binding") != {k: v for k, v in binding.items() if k != "spec_sha256"}):
        blockers.append(f"{kind}_candidate_job_result_binding_mismatch")
    if (not isinstance(source.get("origin"), str)
            or source["origin"] not in {"owner_verified_market_capture", "licensed_market_history"}
            or source.get("fixture_only") is not False or source.get("pair") != candidate.get("pair")
            or source.get("data_sha256") != binding.get("data_sha256")
            or not _fresh(source.get("captured_at"), now) or not _fresh(result.get("captured_at"), now)):
        blockers.append(f"{kind}_unverified_or_stale_market_source")
    split = _mapping(evidence.get("split"))
    selection = _mapping(payload.get("selection"))
    research_split = _mapping(selection.get("research_split"))
    development, evaluation = (_interval(split.get(k)) for k in ("development", "evaluation"))
    if development is None or evaluation is None or development[1] > evaluation[0]:
        blockers.append(f"{kind}_development_overlap_or_invalid_split")
    if split.get("development") != research_split.get("development") or (
            kind == "independent_proof" and split.get("evaluation") != research_split.get("holdout")):
        blockers.append(f"{kind}_frozen_research_split_mismatch")
    frozen = _time(_mapping(payload.get("selection")).get("frozen_at"))
    started, captured = _time(job.get("started_at")), _time(result.get("captured_at"))
    if frozen is None or started is None or captured is None or not frozen <= started <= captured <= now:
        blockers.append(f"{kind}_selection_not_frozen_before_evaluation")
    records = inputs.get("records")
    timestamps = []
    if isinstance(records, list):
        for row in records:
            row = _mapping(row)
            at = _time(row.get("timestamp"))
            if at is None or at > now or evaluation is None or not evaluation[0] <= at < evaluation[1] or not _number(row.get("close")) or row["close"] <= 0:
                blockers.append(f"{kind}_invalid_input_record")
            elif timestamps and at <= timestamps[-1]:
                blockers.append(f"{kind}_input_records_not_unique_ordered")
            if at is not None:
                timestamps.append(at)
    if not isinstance(records, list) or len(records) < MIN_TRADES_PER_SIDE:
        blockers.append(f"{kind}_insufficient_observed_input")
    risk = _mapping(evidence.get("risk_policy"))
    if (not all(_number(risk.get(k)) and risk[k] > 0 for k in ("max_risk_percent", "max_daily_loss", "max_data_age_seconds"))
            or risk.get("max_risk_percent", math.inf) > 2 or risk.get("max_data_age_seconds", math.inf) > 300
            or type(risk.get("max_open_trades")) is not int or risk["max_open_trades"] < 1):
        blockers.append(f"{kind}_missing_or_weakened_risk_policy")
    receipt = _mapping(evidence.get("accepted_receipt"))
    expected = {"job_id": job.get("job_id"), "phase": phase, "status": "ACCEPTED",
                "spec_sha256": binding.get("spec_sha256"), "input_sha256": binding.get("input_sha256"),
                "source_sha256": binding.get("source_sha256"), "result_sha256": artifact_digest(result)}
    if any(receipt.get(k) != v for k, v in expected.items()) or not _hash(receipt.get("journal_sha256")):
        blockers.append(f"{kind}_accepted_result_receipt_mismatch")
    ledger = payload.get("global_ledger")
    matching = [row for row in ledger if isinstance(row, dict) and row.get("job_id") == job.get("job_id")] if isinstance(ledger, list) else []
    ledger_entry = matching[0] if len(matching) == 1 and matching[0] == receipt else None
    if ledger_entry is None:
        blockers.append(f"{kind}_global_ledger_missing_or_conflicting")
    _trusted(kind, evidence, ledger_entry, ledger, selection, verifier, blockers)
    metrics = _economics(kind, evidence, candidate, evaluation, blockers)
    if kind == "paper_validation":
        _operations(evidence, metrics, now, blockers)
    return metrics


def check_factory_paper_handoff(payload: dict[str, Any] | None = None, *,
                                artifact_verifier: ArtifactVerifier | None = None,
                                now: datetime | None = None) -> dict[str, Any]:
    """Check explicit evidence and call the existing canonical review authority.

    ``artifact_verifier(kind, artifact, ledger_entry, global_ledger)`` is a required external
    trust boundary. It must independently reread frozen saved bytes and accepted
    journal/ledger state, authenticate observed source provenance, then return
    the exact artifact, receipt, ledger-entry, global-ledger, frozen-selection and
    research-split digests enforced by ``_trusted``. It must verify frozen
    selection/split provenance and that confirmation and paper evidence were
    untouched by tuning or selection. Never echo supplied claims. The selection
    includes the original ``research_split={development, holdout}``, pinned by
    the actual S6 artifact's split_sha256; this is not an adapter-created split.
    Development receipts are lineage only. Each selected side needs >=30 actual
    after-cost confirmation trades and >=30 paper trades, expectancy >0,
    profit factor >=1.10, drawdown <=10%, chronological unambiguous trade-close
    timestamps, and operational paper proofs.
    The returned engineering verdict does not authorize paper or broker orders.
    """
    blockers: list[str] = []
    try:
        data = json.loads(json.dumps(payload, allow_nan=False)) if isinstance(payload, dict) else {}
    except (ValueError, TypeError, RecursionError):
        data = {}
        blockers.append("malformed_or_nonfinite_handoff_payload")
    current = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None:
        blockers.append("timezone_aware_validation_clock_required")
        current = datetime.now(timezone.utc)
    current = current.astimezone(timezone.utc)
    if not callable(artifact_verifier):
        blockers.append("trusted_artifact_verifier_required")
    selection = _mapping(data.get("selection"))
    candidate = _mapping(selection.get("candidate"))
    if any(not isinstance(candidate.get(k), str) or not candidate[k].strip() for k in _IDENTITY) or candidate.get("direction") not in {"buy", "sell"}:
        blockers.append("selected_candidate_identity_required")
    research = _mapping(data.get("research_artifact"))
    stable = _mapping(research.get("binding"))
    receipt = _mapping(research.get("actual_receipt"))
    verified = _mapping(research.get("verified_result"))
    proposal = _mapping(research.get("proposal"))
    search_receipt = _mapping(research.get("search_receipt"))
    reservation = _mapping(research.get("reservation"))
    if (research.get("schema") != "AIOS_OPTUNA_S6_RECEIPT_V1"
            or research.get("classification") != "ACCEPTED_DEVELOPMENT_USED_NOT_INDEPENDENT_EDGE"
            or search_receipt.get("phase") != "development"
            or any(not _hash(stable.get(k)) for k in _STABLE)
            or any(not _hash(stable.get(k)) for k in ("spec_sha256", "economic_sha256", "identity_sha256", "input_sha256",
                "data_sha256", "rules_sha256", "cost_risk_sha256", "split_sha256", "source_sha256", "source_closure_sha256",
                "scope_sha256", "parameter_bindings_sha256"))
            or stable.get("split_sha256") != artifact_digest(selection.get("research_split"))
            or _interval(_mapping(selection.get("research_split")).get("development")) is None
            or _interval(_mapping(selection.get("research_split")).get("holdout")) is None
            or not isinstance(selection.get("parameters"), dict) or not selection["parameters"]
            or stable.get("parameter_sha256") != artifact_digest(selection.get("parameters"))
            or any(research.get(k) is not False for k in ("verified_edge", "paper_ready", "live_ready"))
            or set(receipt) != campaign_budget._RECEIPT_FIELDS or receipt.get("status") != "ACCEPTED"
            or any(receipt.get(k) != stable.get(k) for k in ("proposal_hash", "spec_sha256", "economic_sha256", "input_sha256", "source_sha256", "scope_sha256"))
            or receipt.get("job_id") != stable.get("identity_sha256")
            or any(not isinstance(receipt.get(k), str) or not receipt[k] for k in ("receipt_id", "core_run_id", "core_unit_id", "core_attempt_id"))
            or not _hash(receipt.get("output_sha256")) or verified.get("actual_receipt") != receipt
            or verified.get("classification") != research.get("classification") or verified.get("fixture_only") is not False
            or any(not _hash(verified.get(k)) for k in ("result_sha256", "accepted_journal_sha256"))
            or type(verified.get("sample_count")) is not int or verified["sample_count"] < 1
            or not _number(verified.get("objective"))
            or proposal.get("params") != selection.get("parameters")
            or any(proposal.get(k) != stable.get(k) for k in ("contract_hash", "proposal_hash"))
            or proposal.get("proposal_hash") != artifact_digest([proposal.get("contract_hash"), proposal.get("params")])
            or search_receipt.get("contract_hash") != stable.get("contract_hash")
            or search_receipt.get("proposal_hash") != stable.get("proposal_hash")
            or search_receipt.get("cost_adjusted") is not True or search_receipt.get("status") != "COMPLETE"
            or search_receipt.get("sample_count") != verified.get("sample_count")
            or search_receipt.get("objective") != verified.get("objective")
            or search_receipt.get("evidence_sha256") != artifact_digest(verified)
            or _mapping(search_receipt.get("metrics")).get("fixture_only") is not False
            or _mapping(search_receipt.get("metrics")).get("trade_count") != verified.get("sample_count")
            or reservation.get("state") != "STARTED" or reservation.get("noncanonical_copy") is not False
            or reservation.get("authorized_to_evaluate") is not True
            or reservation.get("request") != {k: receipt.get(k) for k in campaign_budget._REQUEST_FIELDS}
            or type(research.get("market_evaluator_calls")) is not int
            or research["market_evaluator_calls"] != receipt.get("physical_calls")
            or research["market_evaluator_calls"] < 1):
        blockers.append("accepted_frozen_development_lineage_required")
    _trusted("research_artifact", research, None, data.get("global_ledger"), selection, artifact_verifier, blockers)
    independent = _evidence("independent_proof", data, candidate, stable, current, artifact_verifier, blockers)
    paper = _evidence("paper_validation", data, candidate, stable, current, artifact_verifier, blockers)
    proof_binding = _mapping(_mapping(data.get("independent_proof")).get("binding"))
    paper_binding = _mapping(_mapping(data.get("paper_validation")).get("binding"))
    if proof_binding and (proof_binding.get("input_sha256") == stable.get("input_sha256")
                          or proof_binding.get("input_sha256") == paper_binding.get("input_sha256")
                          or proof_binding.get("data_sha256") == paper_binding.get("data_sha256")):
        blockers.append("independent_input_reused_for_development_or_paper")
    independent_split = _interval(_mapping(_mapping(data.get("independent_proof")).get("split")).get("evaluation"))
    paper_split = _interval(_mapping(_mapping(data.get("paper_validation")).get("split")).get("evaluation"))
    if independent_split and paper_split and independent_split[1] > paper_split[0]:
        blockers.append("paper_validation_must_follow_independent_confirmation")
    bundle = _mapping(data.get("proof_bundle"))
    if _mapping(bundle.get("candidate")) and any(_mapping(bundle["candidate"]).get(k) != candidate.get(k) for k in _IDENTITY):
        blockers.append("canonical_candidate_identity_mismatch")
    if paper and not _same_metrics(_mapping(bundle.get("candidate")), paper):
        blockers.append("canonical_candidate_metrics_mismatch")
    # Preserve provenance without treating expected rejected operational probes
    # as blockers on the candidate. Full artifacts were independently checked.
    canonical_payload = dict(bundle)
    for kind in ("independent_proof", "paper_validation"):
        artifact = _mapping(data.get(kind))
        canonical_payload[f"factory_{kind}_provenance"] = {
            "provenance": artifact.get("provenance"), "source": artifact.get("source"),
            **{k: artifact[k] for k in ("mode", "fixture_only", "synthetic_only") if k in artifact}}
    reviewed = canonical_bridge.run_proof_bundle_to_candidate_bridge(write_reports=False,
                                                                    proof_bundle_payload=canonical_payload)
    canonical_verdict = reviewed["candidate_bridge_verdict"]
    if canonical_verdict != canonical_bridge.DEMO_REVIEW_READY:
        blockers.extend(f"canonical_{b}" for b in reviewed["remaining_blockers"])
        blockers.append("canonical_review_not_ready")
    blockers = list(dict.fromkeys(blockers))
    return {"schema": "AIOS_FACTORY_PAPER_HANDOFF_CHECK_V1", "mode": "OFFLINE_EVIDENCE_CHECK",
            "status": "ENGINEERING_HANDOFF_CHECK_PASSED" if not blockers else "BLOCKED_MISSING_OR_INVALID_EVIDENCE",
            "engineering_handoff_passed": not blockers, "blockers": blockers,
            "selected_candidate": candidate, "independent_metrics": independent, "paper_metrics": paper,
            "canonical_candidate_verdict": canonical_verdict,
            "canonical_review": reviewed, "paper_ready": False, "live_ready": False,
            "execution_allowed": False, "broker_authority": False,
            "next_safe_action": "Submit verified evidence to the existing owner review gate." if not blockers
            else "Collect matching immutable independent and operational paper evidence; no execution is authorized."}


def run_synthetic_paper_wiring_smoke(*, research_artifact: dict[str, Any] | None = None,
                                    now: datetime | None = None) -> dict[str, Any]:
    """Bounded in-memory smoke of real risk/simulator/replay code on synthetic data.

    This intentionally supplies no trusted verifier or market-proof artifacts.
    It cannot convert successful engineering wiring into actual paper readiness.
    """
    current = now if now is not None else datetime.now(timezone.utc)
    timestamp = current.timestamp()
    candidate = {"symbol": "EURUSD", "direction": "buy", "entry": 1.1, "stop": 1.09,
                 "target": 1.12, "risk_percent": 1.0, "spread": 0.0001, "timestamp": timestamp}
    limits = {"max_risk_percent": 1.0, "max_daily_loss": 100.0, "max_open_trades": 1,
              "max_spread": 0.001, "max_data_age_seconds": 300.0}
    checks = {"safe": evaluate_paper_trade_risk(candidate, {}, [], limits, timestamp),
              "stop": evaluate_paper_trade_risk({**candidate, "stop": None}, {}, [], limits, timestamp),
              "daily_loss": evaluate_paper_trade_risk(candidate, {"daily_loss": 100.0}, [], limits, timestamp),
              "stale": evaluate_paper_trade_risk({**candidate, "timestamp": timestamp - 301}, {}, [], limits, timestamp)}
    kill = evaluate_risk_preview({"pair": "EURUSD", "direction": "buy", "entry_price": 1.1,
        "stop_loss": 1.09, "take_profit": 1.12, "units": 1000.0, "dollar_risk": 10.0,
        "percent_risk": 1.0, "data_timestamp": current.isoformat(), "paper_only": True},
        account_state={"current_balance": 1000.0, "kill_switch_active": True}, now_timestamp=current)
    killed_supervisor = run_paper_supervisor_cycle(
        [{"pair": "EURUSD", "bid": 1.1, "ask": 1.1001, "timestamp": timestamp}],
        account_state={"starting_balance": 1000.0, "current_balance": 1000.0,
                       "cash_balance": 1000.0, "equity": 1000.0},
        session_state={"session_id": "synthetic-kill-smoke", "cycle_number": 1},
        limits={"kill_switch_active": True, "max_cycles": 1}, timestamp=timestamp,
        metadata={"fixture_only": True, "mode": "ENGINEERING_DRY_RUN"})
    fixture = MarketDataFixture("synthetic-handoff-smoke", "EURUSD", "1m", "clearly synthetic engineering fixture",
        [Candle(current.isoformat(), 1.1, 1.102, 1.099, 1.101, source="synthetic fixture") for _ in range(2)])
    intents = [OrderIntent(f"synthetic-{side}", "synthetic-signal", "EURUSD", side, 1000.0, 1.1, 1.09, 1.12)
               for side in ("BUY", "SELL")] if checks["safe"]["risk_passed"] else []
    entries = run_paper_forward_simulation(intents, fixture)
    summary = paper_forward_summary(entries)
    events = [{"event_type": "candidate_created", "payload": {}, "paper_only": True}]
    for entry in entries:
        events.extend([{"event_type": "paper_trade_closed", "payload": {"trade_id": entry.ledger_id,
                         "realized_pl": entry.simulated_pnl_usd}, "paper_only": True},
                       {"event_type": "balance_updated", "payload": {}, "paper_only": True}])
    replay = build_paper_session_replay(events, 1000.0, 1000.0)
    handoff = check_factory_paper_handoff({"research_artifact": research_artifact,
        "paper_validation": {"mode": "ENGINEERING_DRY_RUN", "fixture_only": True, "result": summary}}, now=current)
    return {"mode": "ENGINEERING_DRY_RUN", "fixture_only": True, "synthetic_only": True,
            "risk_checks": checks, "kill_check": kill, "killed_supervisor": killed_supervisor,
            "simulation": summary, "replay": replay,
            "kill_switch_fills_created": killed_supervisor["fills_created"], "handoff": handoff, "paper_ready": False,
            "live_ready": False, "execution_allowed": False,
            "actual_call_path": ["paper_risk_governor.evaluate_paper_trade_risk",
                                 "risk_governor.evaluate_risk_preview",
                                 "long_run_paper_supervisor.run_paper_supervisor_cycle",
                                 "paper_forward_simulator.run_paper_forward_simulation",
                                 "paper_session_replay.build_paper_session_replay",
                                 "proof_bundle_to_candidate_bridge.run_proof_bundle_to_candidate_bridge"]}
