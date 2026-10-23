"""PKT-045 local preregistration: no AWS, corpus, score, or memory writer."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from automation.forex_engine import forex_control_baseline_rsi_filter_comparison_stage1_v1 as handoff
from automation.forex_engine import forex_edge_discovery_tournament_stage1_v1 as tournament
from automation.forex_engine import forex_edge_validation_pipeline_v1 as validation
from automation.forex_engine.edge_research import batch, dukascopy_acquisition, research


ROOT = Path(__file__).resolve().parents[3]
UTC = timezone.utc


def successor_context():
    return research.paired_tick_mid_successor_context(tuple(tournament.certified_instrument_metadata()))


def test_successor_has_distinct_data_semantics_and_only_rsi_changes():
    context = successor_context()
    checked = research.validate_paired_tick_mid_successor_context(context)
    assert checked["status"] == "PASS"
    assert context["packet_id"] == "PKT-FOREX-045"
    assert context["parent_packet_id"] == "PKT-FOREX-044"
    assert context["cards"][0]["fingerprint"] != context["cards"][1]["fingerprint"]
    baseline, challenger = (card["specification"] for card in context["cards"])
    changed = {key for key in set(baseline) | set(challenger) if baseline.get(key) != challenger.get(key)}
    assert changed == {"regime_filters"}
    assert baseline["regime_filters"]["rsi"] is None
    assert challenger["regime_filters"]["rsi"] == "WILDER14_LONG_LE70_SHORT_GE30_MISSING_FILTERED"
    assert baseline["data_identity"]["corpus"] != tournament.CORPUS_ID
    assert tournament.validate_successor_preacquisition_contract(context)["scoring_status"].startswith("BLOCKED")


def test_local_semantics_pass_does_not_claim_full_coverage_or_cost_eligibility():
    requirement = dukascopy_acquisition.SourceSemanticsRequirement(
        strategy_specification_id=research.PKT045_EXPERIMENT_ID,
        required_pair_count=58,
        required_price_sides=("BID", "ASK"),
        midpoint_semantics="PAIRED_TICK_MIDPOINT_THEN_M5_AGGREGATION",
        timestamp_granularity="TICK",
        candle_construction="PAIRED_TICKS_THEN_M5",
        activity_semantics="NOT_REQUIRED",
        preregistration_status="FROZEN",
    )
    gate = dukascopy_acquisition.evaluate_paired_tick_preacquisition_gate(
        requirement=requirement, mapped_pair_count=58, local_tick_proof_id="a" * 64, local_tick_proof_passed=True,
    )
    assert gate.semantic_contract_status == "PASS"
    assert gate.full_coverage_status == "UNVERIFIED_REQUIRES_EXACT_TICK_INVENTORY"
    assert gate.acquisition_status.startswith("BLOCKED_AWAITING")
    payload = dukascopy_acquisition.paired_tick_preacquisition_gate_payload(gate, requirement=requirement)
    assert payload["AWS_REQUESTS"] == 0
    assert payload["COST_GATE_STATUS"].startswith("NOT_RUN")


def test_expected_tick_plan_is_exact_and_no_availability_claim():
    pairs = tuple(tournament.certified_instrument_metadata())
    plan = dukascopy_acquisition.plan_paired_tick_inventory(
        pairs=pairs,
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2025, 4, 1, tzinfo=UTC),
    )
    assert plan.pair_count == 58
    assert plan.calendar_date_count == 456
    assert plan.total_expected_tick_object_count == 58 * 456
    payload = dukascopy_acquisition.paired_tick_inventory_plan_payload(plan)
    assert payload["INVENTORY_STATUS"] == "EXPECTED_KEYS_ONLY_NO_AWS_REQUESTS"
    assert payload["EXISTENCE_STATUS"].startswith("UNVERIFIED")
    assert payload["OBJECT_KEYS"][0].endswith("_ticks.bi5")


def test_preregistration_is_deterministic_and_preserves_canonical_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "PKT045_STAGING_RELATIVE", tmp_path)
    ledger = ROOT / tournament.TRIAL_LEDGER_RELATIVE
    index = ROOT / tournament.FINGERPRINT_INDEX_RELATIVE
    before_ledger, before_index = ledger.read_bytes(), index.read_bytes()
    output = tmp_path / "receipt"
    first = batch.preregister_pkt045(ROOT, output)
    second = batch.preregister_pkt045(ROOT, output)
    assert first == second
    assert first["status"] == "PASS_PREACQUISITION_ONLY"
    assert first["run1_sha256"] == first["run2_sha256"]
    assert batch.pkt045_status(ROOT, output)["execution_allowed"] is False
    assert ledger.read_bytes() == before_ledger
    assert index.read_bytes() == before_index


def test_preregistration_duplicate_check_is_read_only_and_blocks_registration():
    context = successor_context()
    source = {"entries": []}
    first = handoff.review_preregistered_successor(context, source)
    assert first["duplicate_status"] == "NO_EQUIVALENT_MEMORY_IDENTITY"
    assert first["market_trials_added"] == 0
    assert source == {"entries": []}
    duplicate = {"entries": [{"candidate_id": "PRIOR", "fingerprint": context["cards"][0]["fingerprint"]}]}
    second = handoff.review_preregistered_successor(context, duplicate)
    assert second["duplicate_status"] == "DUPLICATE_REJECTED"
    assert second["research_memory_mutation"] is False
    assert duplicate["entries"][0]["candidate_id"] == "PRIOR"


def test_successor_cannot_reach_pkt044_executor_or_old_corpus():
    context = successor_context()
    with pytest.raises(ValueError, match="SUCCESSOR_SCORING_REQUIRES_CERTIFIED"):
        batch.execute(ROOT, ROOT / ".aios/staging/PKT_FOREX_045/nonexistent", {"packet_id": context["packet_id"]}, {}, resume=False)
    altered = copy.deepcopy(context)
    altered["cards"][0]["specification"]["data_identity"]["corpus"] = tournament.CORPUS_ID
    altered["cards"][0]["fingerprint"] = validation.candidate_fingerprint(altered["cards"][0]["specification"])
    with pytest.raises(ValueError, match="OLD_CORPUS_FALLBACK"):
        tournament.validate_successor_preacquisition_contract(altered)


def test_preregistration_context_rejects_scoring_or_unsynchronized_source_semantics():
    context = successor_context()
    context["scoring_allowed"] = True
    with pytest.raises(ValueError, match="SCORING_ALLOWED_MISMATCH"):
        research.validate_paired_tick_mid_successor_context(context)
    context = successor_context()
    context["same_record_pairing"] = False
    with pytest.raises(ValueError, match="SAME_RECORD_PAIRING_MISMATCH"):
        research.validate_paired_tick_mid_successor_context(context)


def test_stage1_pre_inventory_guard_reuses_frozen_receipt_without_aws():
    pricing = dukascopy_acquisition.CostBasis(
        .005, .0004, .0004, .09,
        "https://aws.amazon.com/s3/pricing/?loc=ft", "2026-09-08T00:57:44Z", "NONE",
    )
    first = batch.pkt045_stage1_pre_inventory_cost_guard(ROOT, pricing=pricing)
    second = batch.pkt045_stage1_pre_inventory_cost_guard(ROOT, pricing=pricing)
    assert first == second
    assert first["PAIR_COUNT"] == 58
    assert first["PAIR_MONTH_PREFIX_COUNT"] == 870
    assert first["MAX_LIST_REQUESTS"] == 870
    assert first["CONSERVATIVE_INVENTORY_COST_USD"] == pytest.approx(.01435)
    assert first["COST_GATE"] == "PASS"
    assert first["AWS_REQUESTS_MADE"] == 0
    assert first["NO_ACQUISITION"] is True
    assert first["NO_SCORING"] is True
