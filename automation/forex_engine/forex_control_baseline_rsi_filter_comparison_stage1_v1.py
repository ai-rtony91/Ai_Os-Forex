"""PKT044 checked-summary handoff. No price reader, scoring, or authority writer.

This is the no-market amendment interface, not the unfinished RSI market runner.
Existing validation owns fingerprints, record rules and promotion gates.
"""
from __future__ import annotations

import copy
import math
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from automation.forex_engine import forex_edge_validation_pipeline_v1 as validation


PROMOTION_REQUIREMENTS = (
    "cost_stress", "parameter_stability", "period_stability", "portfolio_risk", "breadth",
    "concentration", "matched_baseline", "leakage", "multiple_search", "reproduction",
)


def classify(record: Mapping[str, Any]) -> dict[str, Any]:
    checked = validation.validate_research_record(record)
    gross, net = record["metrics"].get("gross"), record["metrics"].get("net")
    failures = record["failed_gates"]
    if record["validity"] == "INVALID":
        category, action = "INVALID_TEST", "REPAIR_MEASUREMENT"
    elif record["validity"] != "VALID":
        category, action = "INSUFFICIENT_SAMPLE", "NO_JUSTIFIED_NEXT_TEST"
    elif record["executed_trades"] == 0:
        category, action = "NO_EXECUTION", "REPAIR_MEASUREMENT"
    elif record["executed_trades"] < record["sample_requirement"] or gross is None or net is None:
        category, action = "INSUFFICIENT_SAMPLE", "REQUEST_MISSING_MEASUREMENT"
    elif "concentration" in failures:
        category, action = "CONCENTRATED", "TEST_PAIR_GROUP"
    elif "regime" in failures:
        category, action = "REGIME_DEPENDENT", "TEST_REGIME"
    elif "parameter_stability" in failures:
        category, action = "FRAGILE", "STOP_BRANCH"
    elif gross > 0 and net <= 0:
        category, action = "COST_DESTROYED_EDGE", "INVESTIGATE_COSTS"
    elif net <= 0:
        category, action = "DEAD", "STOP_BRANCH"
    elif "matched_baseline" in failures:
        category, action = "BASELINE_INFERIOR", "STOP_BRANCH"
    else:
        checks = record.get("promotion_checks") or {}
        complete = not failures and all(checks.get(key) == "PASS" for key in PROMOTION_REQUIREMENTS)
        # Pooled pip summaries are not portfolio evidence. Positive alone is not a near-miss.
        complete = complete and record["metrics"]["unit"] != "DESCRIPTIVE_PIPS_NOT_CASH"
        category = "PRELIMINARY_SURVIVOR" if complete else "GROSS_ONLY"
        action = "FREEZE_PRELIMINARY_SURVIVOR" if complete else "REQUEST_MISSING_MEASUREMENT"
    return {"candidate_id": record["candidate_id"], "fingerprint": record["fingerprint"],
            "failure_class": category, "action": action, "classification_scope": "TESTED_CONFIGURATION_ONLY",
            "validity": record["validity"], "missing_fields": checked["missing_fields"],
            "parent_evidence_sha256": checked["record_sha256"], "failed_gates": list(failures),
            "gross": gross, "net": net, "unit": record["metrics"]["unit"],
            "cost_drag": gross - net if gross is not None and net is not None else None,
            "attribution": {key: record.get(key) for key in ("pair_attribution", "currency_attribution", "session_attribution", "regime_attribution")},
            "descriptive_only": True, "promotion_allowed": False,
            "descendants_blocked": record["validity"] != "VALID",
            "lesson": f"{category}: applies only to this specification and evidence; no independent edge claim.",
            "do_not_repeat": record["fingerprint"] if category in {"DEAD", "BASELINE_INFERIOR"} else None}


PROPOSAL_FIELDS = (
    "parent_candidate_id", "parent_evidence_sha256", "finding", "question", "difference",
    "changed_variable", "fixed_variables", "baseline", "data_required", "data_status",
    "information_gain", "trial_cost", "compute_cost", "rejection_condition", "stop_condition",
    "authority_required", "specification",
)


def review_batch(records: Sequence[Mapping[str, Any]], fingerprint_index: Mapping[str, Any],
                 proposals: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Pure planner: checked input yields a bounded recommendation, never execution."""
    if not records or len(proposals) > 3:
        raise ValueError("HANDOFF_EMPTY_OR_PROPOSAL_BUDGET_EXCEEDED")
    ids = [row["candidate_id"] for row in records]
    if len(ids) != len(set(ids)):
        raise ValueError("HANDOFF_DUPLICATE_CANDIDATE")
    reviews = [classify(row) for row in records]
    by_id = {row["candidate_id"]: row for row in reviews}
    source_by_id = {row["candidate_id"]: row for row in records}
    entries = fingerprint_index.get("entries")
    if not isinstance(entries, list):
        raise ValueError("HANDOFF_MEMORY_MISSING")
    known = {row["fingerprint"] for row in entries}
    if len(known) != len(entries) or len({row["candidate_id"] for row in entries}) != len(entries):
        raise ValueError("HANDOFF_MEMORY_DUPLICATE_IDENTITY")
    checked_proposals = []
    for proposal in proposals:
        if any(key not in proposal or proposal[key] is None for key in PROPOSAL_FIELDS):
            raise ValueError("PROPOSAL_CONTRACT_INCOMPLETE")
        parent = by_id.get(proposal["parent_candidate_id"])
        if parent is None or proposal["parent_evidence_sha256"] != parent["parent_evidence_sha256"]:
            raise ValueError("PROPOSAL_PARENT_EVIDENCE_MISMATCH")
        if type(proposal["trial_cost"]) is not int or proposal["trial_cost"] <= 0:
            raise ValueError("PROPOSAL_TRIAL_COST_INVALID")
        original = source_by_id[proposal["parent_candidate_id"]]["specification"]
        changed = {key for key in set(original) | set(proposal["specification"])
                   if original.get(key) != proposal["specification"].get(key)}
        if changed != {proposal["changed_variable"]} or "cost_contract" in changed:
            raise ValueError("PROPOSAL_NOT_ONE_CONTROLLED_CHANGE")
        fixed = {key: value for key, value in original.items() if key not in changed}
        if proposal["fixed_variables"] != fixed:
            raise ValueError("PROPOSAL_FIXED_CONTROL_MISMATCH")
        fingerprint = validation.candidate_fingerprint(proposal["specification"])
        status = "DUPLICATE_REJECTED" if fingerprint in known else "AWAITING_APPROVAL"
        if parent["descendants_blocked"]:
            status = "BLOCKED_INVALID_PARENT"
        known.add(fingerprint)
        checked_proposals.append({**copy.deepcopy(proposal), "fingerprint": fingerprint,
                                  "status": status, "outcome_informed": True})
    # Evidence quality/repair comes first. Return is deliberately absent from ranking.
    priority = {"REPAIR_MEASUREMENT": 0, "REQUEST_MISSING_MEASUREMENT": 1,
                "FREEZE_PRELIMINARY_SURVIVOR": 2, "INVESTIGATE_COSTS": 3}
    ordered = sorted(reviews, key=lambda row: (priority.get(row["action"], 4), row["candidate_id"]))
    preferred = ordered[0]
    proposals_ranked = sorted(checked_proposals, key=lambda row: (
        row["status"] != "AWAITING_APPROVAL", row["trial_cost"], row["fingerprint"]))
    next_action = {"action": preferred["action"], "parent_candidate_id": preferred["candidate_id"],
                   "evidence": preferred["parent_evidence_sha256"],
                   "reason": preferred["lesson"], "authority_required": "SEPARATE_APPROVED_PACKET"}
    if preferred["action"] == "INVESTIGATE_COSTS":
        next_action["question"] = "Can one separately preregistered holding-horizon change produce movement large enough to survive unchanged realistic costs?"
        next_action["fixed_control"] = "Keep the original result, costs and risk limits; do not score until exact changed rules are approved."
    eligible = [row for row in proposals_ranked if row["status"] == "AWAITING_APPROVAL"]
    if eligible and preferred["action"] not in {"REPAIR_MEASUREMENT", "REQUEST_MISSING_MEASUREMENT"}:
        next_action.update(action="PREREGISTER_NEW_HYPOTHESIS", proposal_fingerprint=eligible[0]["fingerprint"])
    return {"schema": "AIOS_FOREX_RESEARCH_HANDOFF.v1", "reviews": reviews,
            "proposals": proposals_ranked, "selected_next_action": next_action,
            "next_state": "AWAITING_APPROVAL", "execution_allowed": False,
            "market_trials_added": 0, "verified_edge": False,
            "memory_lookup_sha256": validation.sha256_value(fingerprint_index)}


def review_preregistered_successor(context: Mapping[str, Any], fingerprint_index: Mapping[str, Any]) -> dict[str, Any]:
    """Read-only duplicate and routing check for an unscored successor packet.

    Unlike ``review_batch``, this function accepts no outcome record.  Its only
    possible route is an approval boundary for later source inventory,
    certification, and scoring authority.  It never registers an idea or
    changes the canonical fingerprint index.
    """
    if not isinstance(context, Mapping) or context.get("scoring_allowed") is not False:
        raise ValueError("PREREGISTRATION_CONTEXT_INVALID_OR_SCORING_ENABLED")
    cards = context.get("cards")
    if not isinstance(cards, list) or len(cards) != 2:
        raise ValueError("PREREGISTRATION_AB_CARD_COUNT_INVALID")
    entries = fingerprint_index.get("entries")
    if not isinstance(entries, list):
        raise ValueError("PREREGISTRATION_MEMORY_MISSING")
    known_ids = {row.get("candidate_id") for row in entries}
    known_fingerprints = {row.get("fingerprint") for row in entries}
    if len(known_ids) != len(entries) or len(known_fingerprints) != len(entries):
        raise ValueError("PREREGISTRATION_MEMORY_DUPLICATE_IDENTITY")
    cards_by_id = {card.get("candidate_id"): card for card in cards}
    if len(cards_by_id) != len(cards) or any(not card.get("candidate_id") for card in cards):
        raise ValueError("PREREGISTRATION_CANDIDATE_IDENTITY_INVALID")
    if len({card.get("fingerprint") for card in cards}) != len(cards):
        raise ValueError("PREREGISTRATION_FINGERPRINT_DUPLICATE")
    reviewed = []
    for candidate_id, card in sorted(cards_by_id.items()):
        fingerprint = card.get("fingerprint")
        if not isinstance(card.get("specification"), Mapping) or validation.candidate_fingerprint(card["specification"]) != fingerprint:
            raise ValueError("PREREGISTRATION_FINGERPRINT_INVALID")
        collision = candidate_id in known_ids or fingerprint in known_fingerprints
        reviewed.append({
            "candidate_id": candidate_id,
            "fingerprint": fingerprint,
            "status": "DUPLICATE_REJECTED" if collision else "PREPARED_UNREGISTERED",
            "research_memory_mutation": False,
        })
    duplicate = any(row["status"] == "DUPLICATE_REJECTED" for row in reviewed)
    return {
        "schema": "AIOS_FOREX_SUCCESSOR_PREREGISTRATION_HANDOFF_V1",
        "packet_id": context.get("packet_id"),
        "experiment_id": context.get("experiment_id"),
        "parent_packet_id": context.get("parent_packet_id"),
        "cards": reviewed,
        "duplicate_status": "DUPLICATE_REJECTED" if duplicate else "NO_EQUIVALENT_MEMORY_IDENTITY",
        "selected_next_action": {
            "action": "NO_NEW_PACKET_IF_DUPLICATE" if duplicate else "REQUEST_TICK_INVENTORY_COST_CERTIFICATION_AND_SCORING_AUTHORITY",
            "reason": "No market outcome was opened; PKT-045 remains pre-acquisition and unscored.",
            "authority_required": "SEPARATE_OWNER_APPROVED_ACQUISITION_CERTIFICATION_AND_SCORING_PACKET",
        },
        "next_state": "AWAITING_APPROVAL",
        "execution_allowed": False,
        "market_trials_added": 0,
        "research_memory_mutation": False,
        "verified_edge": False,
        "memory_lookup_sha256": validation.sha256_value(fingerprint_index),
    }


def compare_matched_opportunities(baseline: Mapping[str, Any], challenger: Mapping[str, Any],
                                  changed_field: str) -> dict[str, Any]:
    """Compare already measured opportunities. Not a capital-constrained portfolio."""
    for key in ("data_identity", "data_boundary", "cost_version", "risk_version", "fill_version", "unit"):
        if key not in baseline or baseline[key] != challenger.get(key):
            raise ValueError("COMPARISON_CONTROL_MISMATCH")
    differing = {key for key in set(baseline["specification"]) | set(challenger["specification"])
                 if baseline["specification"].get(key) != challenger["specification"].get(key)}
    if differing != {changed_field}:
        raise ValueError("COMPARISON_NOT_ONE_CHANGE")
    def outcomes(arm):
        rows = arm["opportunities"]
        by_id = {row["id"]: row for row in rows}
        if len(rows) != len(by_id) or not rows:
            raise ValueError("COMPARISON_OPPORTUNITY_ID_INVALID")
        for row in rows:
            if row["status"] not in {"EXECUTED", "FILTERED", "SKIPPED"}:
                raise ValueError("COMPARISON_DISPOSITION_INVALID")
            if row["status"] == "EXECUTED" and (type(row.get("net")) not in (int, float) or not math.isfinite(row["net"])):
                raise ValueError("COMPARISON_OUTCOME_MISSING")
            if row["status"] != "EXECUTED" and (row.get("net") is not None or not row.get("reason")):
                raise ValueError("COMPARISON_SKIPPED_OUTCOME_INVALID")
        return by_id
    left, right = outcomes(baseline), outcomes(challenger)
    if left.keys() != right.keys() or any(left[k]["decision_at"] != right[k]["decision_at"] for k in left):
        raise ValueError("COMPARISON_OPPORTUNITY_MISMATCH")
    def summarize(rows):
        values = [row["net"] for row in rows.values() if row["status"] == "EXECUTED"]
        return {"executed": len(values), "filtered": sum(row["status"] == "FILTERED" for row in rows.values()),
                "skipped": sum(row["status"] == "SKIPPED" for row in rows.values()),
                "per_executed": math.fsum(values) / len(values) if values else None,
                "per_original_opportunity": math.fsum(values) / len(rows)}
    a, b = summarize(left), summarize(right)
    return {"baseline": a, "challenger": b, "matched_delta": b["per_original_opportunity"] - a["per_original_opportunity"],
            "uncertainty": None, "uncertainty_status": "REQUIRES_ALIGNED_TIME_BLOCKS",
            "portfolio_status": "NOT_EVALUATED_REQUIRES_SEPARATE_REALIZABLE_SIMULATION", "unit": baseline["unit"]}


def replay_completed_summary(repo_root: Path) -> dict[str, Any]:
    """Adapt only the trusted PKT042 summary files; never read its price journal."""
    from automation.forex_engine import forex_edge_discovery_tournament_stage1_v1 as tournament
    from automation.forex_engine import forex_edge_discovery_tournament_stage0_v1 as stage0
    from automation.forex_engine import forex_factor_common_component_momentum_stage0_v1 as factor

    contracts = tournament.verify_runtime_contracts(repo_root, stage0.first_wave_manifest()["cells"], require_pre_score=False)
    folder = (repo_root / tournament.TRUSTED_CORRECTIVE_MANIFEST_RELATIVE).parent
    manifest = json.loads((repo_root / tournament.TRUSTED_CORRECTIVE_MANIFEST_RELATIVE).read_text(encoding="utf-8"))
    names = ("AIOS_FOREX_PKT039_CORRECTED_RESULTS.json", "AIOS_FOREX_PKT039_CORRECTED_FAILURE_SYNTHESIS.json",
             "AIOS_FOREX_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0_PREREGISTRATION.json", "AIOS_FOREX_SCIENTIFIC_SEARCH_LINEAGE.json")
    inputs, hashes = {}, {}
    for name in names:
        path = folder / name
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("SUMMARY_INPUT_RESOURCE_LIMIT")
        payload = path.read_bytes()
        digest = validation.sha256_bytes(payload)
        if digest != manifest["artifacts"][name]["sha256"]:
            raise ValueError("SUMMARY_ARTIFACT_HASH_MISMATCH")
        inputs[name] = json.loads(payload)
        hashes[path.relative_to(repo_root).as_posix()] = digest
    result, synthesis, saved_successor, lineage = (inputs[name] for name in names)
    if (result.get("outcome_cells_replayed") != 72 or result.get("verified_edge") is not False
            or synthesis.get("cell_count") != 72):
        raise ValueError("SUMMARY_BATCH_IDENTITY_MISMATCH")
    # Reuse the existing producer and require agreement with its trusted saved output.
    if tournament.successor_preregistration(synthesis) != saved_successor:
        raise ValueError("SUMMARY_SUCCESSOR_REPRODUCTION_MISMATCH")
    index = json.loads((repo_root / tournament.FINGERPRINT_INDEX_RELATIVE).read_text(encoding="utf-8"))
    indexed = {row["candidate_id"]: row for row in index["entries"]}
    records = []
    for cell_id, row in sorted(result["cell_results"].items()):
        identity = tournament._runtime_candidate_id(cell_id)
        entry = indexed[identity]
        metrics = row["metrics"]
        record = {field: None for field in validation.RESEARCH_OPTIONAL_FIELDS}
        record.update(schema=validation.RESEARCH_RECORD_SCHEMA, experiment_id="PKT-FOREX-042",
            parent_experiment_id="PKT-FOREX-039", candidate_id=identity, run_id="PKT042_CORRECTED_FINAL_RUN1",
            specification=entry["specification"], fingerprint=entry["fingerprint"],
            data_boundary={"start": "2024-01-01T00:00:00Z", "end_exclusive": "2025-04-01T00:00:00Z"},
            evidence_status="REUSED_DEVELOPMENT", contamination_status="USED", validity="VALID",
            opportunities=metrics["population_count"], executed_trades=metrics["executed_count"], sample_requirement=200,
            metrics={"gross": metrics["gross_mean_pips"], "net": metrics["base_after_cost_mean_pips"], "unit": "DESCRIPTIVE_PIPS_NOT_CASH"},
            failed_gates=[key for key, value in row["stage1_gates"].items() if value is not True], artifacts=hashes,
            uncertainty=metrics.get("base_95pct_synchronized_block_bootstrap_interval_pips"),
            pair_attribution=metrics.get("pair_decomposition"), currency_attribution=metrics.get("currency_decomposition"),
            session_attribution=metrics.get("session_decomposition"), regime_attribution=metrics.get("volatility_decomposition"),
            skip_reasons=metrics.get("dispositions"), source_failure_class=tournament._taxonomy(row),
            evidence_limits=["NO_CASH_PORTFOLIO", "REUSED_DEVELOPMENT", "MFE_MAE_UNAVAILABLE", "FILTERED_VS_SKIPPED_SPLIT_UNAVAILABLE"])
        records.append(record)
    handoff = review_batch(records, index)
    prior_factor = next(row for row in index["entries"] if row.get("packet_id") == "PKT-FOREX-043")
    cards = factor.build_edge_cards(prior_factor["specification"]["pair_currency_universe"])
    known = {entry["fingerprint"] for entry in index["entries"]}
    duplicate_ids = [card["HYPOTHESIS_ID"] for card in cards if card["CANDIDATE_FINGERPRINT"] in known]
    if len(duplicate_ids) != 36:
        raise ValueError("COMPLETED_FACTOR_REGISTRATION_NOT_FOUND")
    handoff.update(records=records, input_hashes=hashes, lineage=lineage,
        recorded_taxonomy=synthesis["taxonomy_counts"], recorded_lessons=synthesis.get("what_the_failures_taught"),
        existing_successor={"hypothesis": saved_successor["selected_hypothesis"], "duplicate_ids": duplicate_ids,
                            "status": "ALREADY_REGISTERED_DO_NOT_REREGISTER", "new_proposals": 0},
        selected_next_action={"action": "NO_JUSTIFIED_NEXT_TEST", "reason": "Existing successor is already registered; pending PKT044 comparison must be frozen and completed under separate scoring authority, not duplicated.",
                              "required_packet": "PKT-FOREX-044", "authority_required": "EXECUTION_RULE_FREEZE_AND_SCORING_SCOPE_CHECK"},
        memory_summary=contracts["pre_score_trial_memory"], market_rows_opened=0,
        validation_rows_opened=0, holdout_rows_opened=0)
    return handoff
