"""Fail-closed proof-bundle to candidate review bridge.

Only explicit caller evidence is consumed. Missing data never invokes a fixture
producer or supplies profitable economics, proof success, or a freshness clock.
"""
from __future__ import annotations

import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import canonical_demo_review_evidence_bridge

PacketResult = Dict[str, Any]
PACKET_ID = "AIOS_FOREX_PROOF_BUNDLE_TO_CANDIDATE_BRIDGE_V1"
DEMO_REVIEW_READY = canonical_demo_review_evidence_bridge.DEMO_REVIEW_READY
PAPER_CONTINUE = canonical_demo_review_evidence_bridge.PAPER_CONTINUE
REJECTED = canonical_demo_review_evidence_bridge.REJECTED
BLOCKED_INCOMPLETE_EVIDENCE = canonical_demo_review_evidence_bridge.BLOCKED_INCOMPLETE_EVIDENCE

SAFETY_DEFAULTS = {
    "paper_only": True,
    "broker_connected": False,
    "credentials_used": False,
    "account_id_present": False,
    "network_used": False,
    "order_execution": False,
    "demo_trading": False,
    "live_trading": False,
    "live_trading_authorized": False,
}

# Existing P1 intake uses these equivalent declarations at its source boundary.
P1_DENIED_FLAGS = (
    "broker_call_performed", "broker_write_performed", "credentials_loaded",
    "account_access_performed", "order_submission_allowed", "order_modification_allowed",
    "order_close_allowed", "live_execution_allowed", "money_movement_allowed",
    "scheduler_created", "daemon_created", "webhook_created", "network_access",
)

# Explicit statuses supported by the canonical evidence contract. Numbers,
# arbitrary nonempty strings, and mappings without a result are never success.
PASS_STATUSES = frozenset({"TRUE", "PASS", "PASSED", "OK", "READY", "COMPLETE", "COMPLETED", "GREEN"})
PROOF_RESULT_FIELDS = ("status", "passed", "value", "pass", "valid", "approved", "confirmed", "ready")
IDENTITY_FIELDS = {
    "candidate_id": ("candidate_id", "selected_candidate_id", "journey_selected_candidate_id", "bundle_selected_candidate_id"),
    "strategy": ("strategy", "strategy_name", "selected_strategy", "journey_selected_strategy", "bundle_selected_strategy"),
    "pair": ("pair", "symbol", "selected_pair", "journey_selected_pair", "bundle_selected_pair"),
    "direction": ("direction", "selected_direction", "journey_selected_direction", "bundle_selected_direction"),
}


def _normalize_proof_payload(proof_bundle_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(proof_bundle_payload, dict):
        return {}
    try:
        # Evidence is a JSON contract. Cycles and non-JSON metadata are malformed.
        json.dumps(proof_bundle_payload)
        return deepcopy(proof_bundle_payload)
    except (TypeError, ValueError, RecursionError):
        return {}


def closed_proof_blockers(before_blockers: list[str], after_blockers: list[str]) -> list[str]:
    return sorted(set(before_blockers or []) - set(after_blockers or []))


def _proof_passed(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().upper() in PASS_STATUSES
    if isinstance(raw, dict):
        results = [raw[key] for key in PROOF_RESULT_FIELDS if key in raw]
        results.extend(_nested_proof_results(raw.get("evidence")))
        return bool(results) and all(_proof_passed(result) for result in results)
    return False


def _nested_proof_results(value: Any) -> list[Any]:
    if isinstance(value, dict):
        results = [value[key] for key in PROOF_RESULT_FIELDS if key in value]
        for nested in value.values():
            results.extend(_nested_proof_results(nested))
        return results
    if isinstance(value, list):
        return [result for nested in value for result in _nested_proof_results(nested)]
    return []


def _finite_number(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _freshness_passed(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    statuses = [raw[key] for key in PROOF_RESULT_FIELDS if key in raw]
    if statuses and not all(_proof_passed(status) for status in statuses):
        return False
    ages = []
    if "age_hours" in raw:
        ages.append(_finite_number(raw["age_hours"]))
    now = datetime.now(timezone.utc)
    for key in ("timestamp", "as_of", "captured_at", "at"):
        if key not in raw:
            continue
        timestamp = raw[key]
        if not isinstance(timestamp, str):
            return False
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return False
        if parsed.tzinfo is None:
            return False
        try:
            ages.append((now - parsed.astimezone(timezone.utc)).total_seconds() / 3600)
        except (ValueError, OverflowError):
            return False
    maximum_age = canonical_demo_review_evidence_bridge.DEFAULT_MAX_FRESHNESS_AGE_HOURS
    return bool(ages) and all(age is not None and 0 <= age <= maximum_age for age in ages)


def _proof_sources(payload: dict[str, Any]) -> tuple[dict[str, list[Any]], list[str]]:
    sources = {name: [] for name in canonical_demo_review_evidence_bridge.PROOF_FIELDS}
    blockers = []
    proofs = payload.get("proofs", {})
    if not isinstance(proofs, dict):
        blockers.append("malformed_proofs")
        proofs = {}
    candidate = payload.get("candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    candidate_proofs = candidate.get("proofs", {})
    if not isinstance(candidate_proofs, dict):
        blockers.append("malformed_candidate_proofs")
        candidate_proofs = {}
    for name, aliases in canonical_demo_review_evidence_bridge.PROOF_ALIASES.items():
        status_aliases = tuple(f"{alias}_status" for alias in aliases)
        for container in (proofs, payload, candidate, candidate_proofs):
            sources[name].extend(container[key] for key in (*aliases, *status_aliases) if key in container)
    records = payload.get("proof_records", [])
    if not isinstance(records, list):
        return sources, [*blockers, "malformed_proof_records"]
    for record in records:
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("proof_type"), str)
            or record["proof_type"] not in sources
        ):
            blockers.append("malformed_proof_record")
            continue
        sources[record["proof_type"]].append(record)
    return sources, blockers


def build_enriched_candidate(proof_bundle_payload: Dict[str, Any]) -> Dict[str, Any]:
    candidate = proof_bundle_payload.get("candidate")
    if not isinstance(candidate, dict) or not candidate:
        return {}
    sources, _ = _proof_sources(proof_bundle_payload)
    enriched = {
        "candidate_id": candidate.get("candidate_id", candidate.get("id")),
        "strategy": candidate.get("strategy", candidate.get("strategy_name")),
        "pair": candidate.get("pair", candidate.get("symbol")),
        "direction": candidate.get("direction"),
    }
    for key, aliases in canonical_demo_review_evidence_bridge.METRIC_ALIASES.items():
        enriched[key] = next((candidate[alias] for alias in aliases if alias in candidate), None)
    for name, values in sources.items():
        check = _freshness_passed if name == "freshness" else _proof_passed
        passed = bool(values) and all(check(value) for value in values)
        enriched[f"{name}_proof"] = deepcopy(values[0]) if name == "freshness" and passed else passed
    return enriched


def _identity_value(field: str, value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or value.strip().lower() == "unknown":
        return None
    normalized = value.strip()
    if field == "direction":
        return {"buy": "buy", "long": "buy", "sell": "sell", "short": "sell"}.get(normalized.lower())
    return normalized.upper() if field == "pair" else normalized


def _identity_blockers(payload: Any, identity: dict[str, Any]) -> list[str]:
    blockers = []
    if isinstance(payload, dict):
        for field, aliases in IDENTITY_FIELDS.items():
            for key in aliases:
                if key in payload and _identity_value(field, payload[key]) != _identity_value(field, identity.get(field)):
                    blockers.append(f"contradictory_{field}")
        for value in payload.values():
            blockers.extend(_identity_blockers(value, identity))
    elif isinstance(payload, list):
        for value in payload:
            blockers.extend(_identity_blockers(value, identity))
    return blockers


def _list_blockers(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        return [f"malformed_{key}"]
    return value


def _metric_value(field: str, value: Any) -> Any:
    if field not in {"walk_forward_status", "paper_evidence_status", "mitigation_status"}:
        return _finite_number(value)
    if not isinstance(value, str):
        return None
    status = value.strip().lower().replace("-", "_")
    allowed = {
        "walk_forward_status": {"pass", "passed", "pass_strong", "pass_stable", "ready"},
        "paper_evidence_status": {"pass", "passed", "ready"},
        "mitigation_status": {"pass", "passed", "ready", "mitigated", "not_worse", "unchanged", "stable"},
    }
    return "pass" if status in allowed[field] else None


def _metric_blockers(candidate: dict[str, Any]) -> list[str]:
    blockers = []
    for field, aliases in canonical_demo_review_evidence_bridge.METRIC_ALIASES.items():
        values = [_metric_value(field, candidate[alias]) for alias in aliases if alias in candidate]
        if not values or any(value is None for value in values):
            blockers.append(f"missing_or_invalid_{field}")
        elif any(value != values[0] for value in values[1:]):
            blockers.append(f"contradictory_{field}")
        if values and values[0] is not None:
            value = values[0]
            if field in {"max_drawdown", "win_rate"} and not 0 <= value <= 1:
                blockers.append(f"invalid_fraction_{field}")
    return blockers


def _source_claim_blockers(value: Any) -> list[str]:
    blockers = []
    if isinstance(value, dict):
        for key in ("source_blockers", "candidate_blockers", "blockers", "blocked_reasons"):
            blockers.extend(_list_blockers(value, key))
        accepted = {
            "source_candidate_verdict": {DEMO_REVIEW_READY, PAPER_CONTINUE},
            "candidate_verdict": {DEMO_REVIEW_READY, PAPER_CONTINUE},
            "source_review_chain_status": {"REVIEW_CHAIN_REVIEW_READY"},
            "review_chain_status": {"REVIEW_CHAIN_REVIEW_READY"},
            "source_journey_final_verdict": {"REVIEW_READY"},
            "journey_final_verdict": {"REVIEW_READY"},
        }
        for key, statuses in accepted.items():
            if key in value and (not isinstance(value[key], str) or value[key] not in statuses):
                blockers.append(f"failed_or_invalid_{key}")
        for nested in value.values():
            blockers.extend(_source_claim_blockers(nested))
    elif isinstance(value, list):
        for nested in value:
            blockers.extend(_source_claim_blockers(nested))
    return blockers


def _source_safety_gaps(value: Any) -> list[str]:
    gaps = []
    if isinstance(value, dict):
        if "safety" in value and not isinstance(value["safety"], dict):
            gaps.append("malformed_safety")
        if "is_safe" in value and value["is_safe"] is not True:
            gaps.append("source_is_not_safe")
        if "safety_gaps" in value and (not isinstance(value["safety_gaps"], list) or value["safety_gaps"]):
            gaps.append("declared_source_safety_gaps")
        for key, required in {**SAFETY_DEFAULTS, **dict.fromkeys(P1_DENIED_FLAGS, False)}.items():
            if key in value and value[key] is not required:
                gaps.append(key)
        for nested in value.values():
            gaps.extend(_source_safety_gaps(nested))
    elif isinstance(value, list):
        for nested in value:
            gaps.extend(_source_safety_gaps(nested))
    return _dedupe(gaps)


def _development_blockers(value: Any) -> list[str]:
    """Preserve development provenance through nested candidate/proof adapters."""
    blockers = []
    if isinstance(value, dict):
        for key in ("fixture_only", "synthetic_only", "uses_synthetic_fixture_only"):
            if key in value and value[key] is not False:
                blockers.append(f"development_evidence_{key}")
        mode = value.get("mode")
        if isinstance(mode, str) and (
            mode.strip().upper() == "ENGINEERING_DRY_RUN"
            or mode.strip().upper().endswith("DEVELOPMENT_ONLY")
        ):
            blockers.append("development_evidence_mode")
        if value.get("edge_status") == "UNPROVEN":
            blockers.append("independent_edge_unproven")
        if value.get("proof_level") == "DEVELOPMENT_USED_NOT_INDEPENDENT_EDGE":
            blockers.append("development_evidence_proof_level")
        evidence_source = value.get("evidence_source")
        if isinstance(evidence_source, str) and any(marker in evidence_source.lower() for marker in ("synthetic", "fixture")):
            blockers.append("development_evidence_source")
        for nested in value.values():
            blockers.extend(_development_blockers(nested))
    elif isinstance(value, list):
        for nested in value:
            blockers.extend(_development_blockers(nested))
    return blockers


def run_proof_bundle_to_candidate_bridge(
    write_reports: bool = True, proof_bundle_payload: dict | None = None
) -> PacketResult:
    """Review one explicit bundle; this function never loads another producer."""
    payload = _normalize_proof_payload(proof_bundle_payload)
    blockers = [] if isinstance(proof_bundle_payload, dict) and proof_bundle_payload else ["missing_or_malformed_proof_bundle"]
    proof_status = payload.get("proof_bundle_status", "PROOF_BUNDLE_INCOMPLETE")
    if proof_status != "PROOF_BUNDLE_COMPLETE":
        blockers.append("proof_bundle_not_complete")
    candidate = payload.get("candidate")
    if not isinstance(candidate, dict) or not candidate:
        blockers.append("missing_or_malformed_candidate")
        candidate = {}
    enriched = build_enriched_candidate(payload)
    for field in IDENTITY_FIELDS:
        if _identity_value(field, enriched.get(field)) is None:
            blockers.append(f"missing_or_invalid_{field}")
    blockers.extend(_identity_blockers(payload, enriched))
    if "id" in candidate and _identity_value("candidate_id", candidate["id"]) != _identity_value("candidate_id", enriched.get("candidate_id")):
        blockers.append("contradictory_candidate_id")
    blockers.extend(_development_blockers(payload))
    blockers.extend(_metric_blockers(candidate))
    sources, proof_format_blockers = _proof_sources(payload)
    blockers.extend(proof_format_blockers)
    for name, values in sources.items():
        check = _freshness_passed if name == "freshness" else _proof_passed
        if not values or not all(check(value) for value in values):
            blockers.append("stale_freshness_or_missing" if name == "freshness" else f"missing_{name}_proof")
    for field in ("expectancy", "profit_factor", "max_drawdown", "win_rate", "sample_size"):
        value = _finite_number(enriched.get(field))
        if value is None or (field == "sample_size" and (value < 0 or not value.is_integer())):
            blockers.append(f"missing_or_invalid_{field}")
            if enriched:
                enriched[field] = None
    blockers.extend(_source_claim_blockers(payload))

    source_safety = payload.get("safety", {})
    safety_gaps = _source_safety_gaps(payload)
    if not isinstance(source_safety, dict):
        source_safety = {}
    safety = {
        **SAFETY_DEFAULTS,
        **{key: payload[key] for key in SAFETY_DEFAULTS if key in payload},
        **source_safety,
    }
    safety["live_trading_authorized"] = False
    safety.update({"is_safe": not safety_gaps, "safety_gaps": safety_gaps})
    blockers.extend(f"unsafe_{key}" for key in safety_gaps)

    reviewed = canonical_demo_review_evidence_bridge.build_review_bundle(enriched)
    blockers = _dedupe([*blockers, *reviewed.get("blockers", [])])
    verdict = BLOCKED_INCOMPLETE_EVIDENCE if blockers else reviewed["verdict"]
    next_action = "Collect explicit matching candidate and proof evidence; no execution is authorized." if blockers else reviewed["next_safe_action"]
    canonical = {
        **reviewed,
        "candidate": deepcopy(candidate),
        "verdict": verdict,
        "blockers": blockers,
        "safety_gaps": safety_gaps,
        "next_safe_action": next_action,
    }
    result: PacketResult = {
        "mode": "LOCAL_APPLY",
        "packet_id": PACKET_ID,
        "safety": safety,
        "selected_candidate_id": enriched.get("candidate_id"),
        "selected_strategy": enriched.get("strategy"),
        "selected_direction": enriched.get("direction"),
        "source_proof_bundle_status": proof_status,
        "source_candidate_verdict": payload.get("source_candidate_verdict"),
        "candidate_bridge_verdict": verdict,
        "proof_bundle_ready_for_candidate_bridge": verdict == DEMO_REVIEW_READY,
        "enriched_candidate": enriched,
        "canonical_review_bundle": canonical,
        "closed_blockers": closed_proof_blockers(
            [f"missing_{name}_proof" for name in ("replay", "reconciliation", "rollback", "demo_validation")],
            blockers,
        ) if candidate else [],
        "remaining_blockers": blockers,
        "strategy_quality_gaps": [reason for reason in blockers if reason in {"walk_forward_failed", "paper_evidence_not_ready", "mitigation_worsened"}],
        "demo_contract_gaps": [reason for reason in blockers if reason == "missing_demo_validation_contract"],
        "review_package_gaps": [reason for reason in blockers if reason in {"missing_one_shot_exception_package", "missing_live_review_readiness_certificate"}],
        "human_review_gaps": [reason for reason in blockers if reason in {"missing_human_review_ready", "missing_live_readiness_candidate"}],
        "safety_gaps": safety_gaps,
        "next_safe_action": next_action,
        "live_trading_authorized": False,
    }
    if write_reports:
        result["report_path"] = write_report(result)
    return result


def write_report(payload: dict) -> Path:
    report_dir = Path("Reports/forex_delivery")
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "proof_bundle_to_candidate_bridge_report.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _dedupe(values: List[str]) -> List[str]:
    return list(dict.fromkeys(values))
