"""PKT-044 prerequisite: scored research additions must preserve old checks.

Only metadata and research-memory copies are used; no market reader runs.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from automation.forex_engine import forex_edge_discovery_tournament_stage0_v1 as stage0
from automation.forex_engine import forex_edge_discovery_tournament_stage1_v1 as memory
from automation.forex_engine import forex_control_baseline_rsi_filter_comparison_stage1_v1 as handoff
from automation.forex_engine import forex_edge_validation_pipeline_v1 as pipeline
from automation.forex_engine.forex_edge_validation_pipeline_v1 import candidate_fingerprint, sha256_value, validate_trial_ledger


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def copied_memory_with_two_scores(tmp_path):
    """Reproduce the exact next-append blocker without canonical writes."""
    if os.name == "nt":
        tmp_path = Path("\\\\?\\" + str(tmp_path.resolve()))
    relatives = [
        memory.TRIAL_LEDGER_RELATIVE, memory.FINGERPRINT_INDEX_RELATIVE,
        memory.CAPABILITY_REGISTRY_RELATIVE, memory.COMMERCIAL_REGISTRY_RELATIVE,
        memory.TRUSTED_CORRECTED_LEDGER_RELATIVE,
        memory.TRUSTED_CORRECTED_FINGERPRINT_INDEX_RELATIVE,
        memory.TRUSTED_CORRECTIVE_MANIFEST_RELATIVE,
    ]
    for relative in relatives:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    ledger_path = tmp_path / memory.TRIAL_LEDGER_RELATIVE
    index_path = tmp_path / memory.FINGERPRINT_INDEX_RELATIVE
    original_ledger_bytes = ledger_path.read_bytes()
    records = memory.read_trial_ledger(ledger_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    original_entries = copy.deepcopy(index["entries"])
    cells = stage0.first_wave_manifest()["cells"]
    assert memory.verify_runtime_contracts(tmp_path, cells, require_pre_score=False)["status"] == "PASS"
    additions = []
    for number in range(2):
        # Distinct artificial specifications, never scored or registered.
        specification = copy.deepcopy(original_entries[-1]["specification"])
        specification["signal_family"] = f"SYNTHETIC_APPEND_COMPATIBILITY_{number}"
        identity = f"TEST_ONLY_PKT044_APPEND_{number}"
        fingerprint = candidate_fingerprint(specification)
        payload = {
            "sequence": len(records) + 1,
            "previous_record_sha256": records[-1]["record_sha256"],
            "event_id": identity,
            "candidate_id": identity,
            "candidate_fingerprint": fingerprint,
            "status": "VALID_TEST_REJECTED",
            "scored_trial_increment": 1,
            "proposed_count": 0,
            "provenance": "SYNTHETIC_TEST_COPY_ONLY_NO_MARKET_SCORING",
        }
        payload["record_sha256"] = sha256_value(payload)
        records.append(payload)
        additions.append(payload)
        index["entries"].append({
            "candidate_id": identity, "fingerprint": fingerprint,
            "specification": specification, "status": "VALID_TEST_REJECTED",
        })
    ledger_path.write_bytes(original_ledger_bytes + b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        for row in additions
    ))
    index_path.write_bytes(memory.canonical_bytes(index))
    assert ledger_path.read_bytes().startswith(original_ledger_bytes)
    assert index["entries"][:-2] == original_entries
    assert validate_trial_ledger(records)["scored_attempt_lower_bound"] == validate_trial_ledger(records[:-2])["scored_attempt_lower_bound"] + 2
    trusted_records = memory.read_trial_ledger(tmp_path / memory.TRUSTED_CORRECTED_LEDGER_RELATIVE)
    trusted_index = json.loads((tmp_path / memory.TRUSTED_CORRECTED_FINGERPRINT_INDEX_RELATIVE).read_text(encoding="utf-8"))
    assert memory.verify_append_only_corrected_memory(records, index, trusted_records, trusted_index)["status"] == "PASS"
    return tmp_path, cells, records, index


def test_valid_two_scored_additions_preserve_historical_runtime_contract(copied_memory_with_two_scores):
    tmp_path, cells, _, _ = copied_memory_with_two_scores
    # The lower-level integrity checks pass. This higher-level count pin must
    # also permit valid later scores while protecting the historical snapshot.
    snapshot = memory.verify_runtime_contracts(tmp_path, cells, require_pre_score=False)
    assert snapshot["pre_score_trial_memory"] == validate_trial_ledger(memory.read_trial_ledger(tmp_path / memory.TRIAL_LEDGER_RELATIVE))


def test_completed_factor_registration_is_idempotent_after_later_scores(copied_memory_with_two_scores):
    from automation.forex_engine import forex_factor_common_component_momentum_stage0_v1 as factor

    _, _, records, index = copied_memory_with_two_scores
    prior_factor = next(row for row in index["entries"] if row.get("packet_id") == "PKT-FOREX-043")
    cards = factor.build_edge_cards(prior_factor["specification"]["pair_currency_universe"])
    original = copy.deepcopy((records, index))
    ledger_bytes, _, receipt = factor.prepare_memory_registration(cards, records, index)
    assert [json.loads(line) for line in ledger_bytes.decode("ascii").splitlines()] == records
    assert receipt["scored_attempt_lower_bound"] == validate_trial_ledger(records)["scored_attempt_lower_bound"]
    assert (records, index) == original


@pytest.mark.parametrize("count,status,increment", [(7, "VALID_TEST_REJECTED", 1), (19, "PROPOSED_UNSCORED", 0)])
def test_growth_beyond_next_two(copied_memory_with_two_scores, count, status, increment):
    from automation.forex_engine import forex_factor_common_component_momentum_stage0_v1 as factor
    root, cells, records, index = copied_memory_with_two_scores
    before = validate_trial_ledger(records)
    for number in range(count):
        spec = copy.deepcopy(index["entries"][-1]["specification"])
        spec["signal_family"] = f"GROWTH_{status}_{number}"
        candidate_id = f"GROWTH_{status}_{number}"
        fingerprint = candidate_fingerprint(spec)
        memory._append_trial_record(records, {"event_id": candidate_id, "candidate_id": candidate_id,
            "candidate_fingerprint": fingerprint, "status": status,
            "scored_trial_increment": increment, "proposed_count": 1 - increment})
        index["entries"].append({"candidate_id": candidate_id, "fingerprint": fingerprint,
                                  "specification": spec, "status": status})
    (root / memory.TRIAL_LEDGER_RELATIVE).write_bytes(b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii") for row in records))
    (root / memory.FINGERPRINT_INDEX_RELATIVE).write_bytes(memory.canonical_bytes(index))
    result = memory.verify_runtime_contracts(root, cells, require_pre_score=False)
    assert result["pre_score_trial_memory"]["scored_attempt_lower_bound"] == before["scored_attempt_lower_bound"] + count * increment
    prior = next(row for row in index["entries"] if row.get("packet_id") == "PKT-FOREX-043")
    cards = factor.build_edge_cards(prior["specification"]["pair_currency_universe"])
    first = factor.prepare_memory_registration(cards, records, index)
    second = factor.prepare_memory_registration(cards, [json.loads(line) for line in first[0].splitlines()], json.loads(first[1]))
    assert first == second


@pytest.mark.parametrize("damage", ["index_missing", "ledger_missing", "candidate_conflict", "history_changed", "history_reordered"])
def test_factor_rejects_partial_or_damaged_memory(copied_memory_with_two_scores, damage):
    from automation.forex_engine import forex_factor_common_component_momentum_stage0_v1 as factor
    _, _, records, index = copied_memory_with_two_scores
    prior = next(row for row in index["entries"] if row.get("packet_id") == "PKT-FOREX-043")
    cards = factor.build_edge_cards(prior["specification"]["pair_currency_universe"])
    if damage == "index_missing":
        index["entries"].pop()
    elif damage == "ledger_missing":
        records.pop()
    elif damage == "candidate_conflict":
        index["entries"][-1]["candidate_id"] = index["entries"][0]["candidate_id"]
    elif damage == "history_changed":
        records[0]["provenance"] = "CHANGED"
    else:
        records[0], records[1] = records[1], records[0]
    with pytest.raises((ValueError, RuntimeError)):
        factor.prepare_memory_registration(cards, records, index)


@pytest.mark.parametrize("field,value", [("scored_trial_increment", 0.5), ("scored_trial_increment", True), ("proposed_count", -1), ("sequence", 1.5)])
def test_invalid_numeric_record_rules_fail(copied_memory_with_two_scores, field, value):
    _, _, records, _ = copied_memory_with_two_scores
    records[-1][field] = value
    records[-1].pop("record_sha256")
    records[-1]["record_sha256"] = sha256_value(records[-1])
    with pytest.raises(ValueError):
        validate_trial_ledger(records)


def research_record():
    spec = pipeline._scientific_spec()
    return {"schema": pipeline.RESEARCH_RECORD_SCHEMA, "experiment_id": "SYNTHETIC_ONLY",
            "candidate_id": "SYNTHETIC_CONTROL", "run_id": "TEST_1", "specification": spec,
            "fingerprint": candidate_fingerprint(spec),
            "data_boundary": {"start": "2024-01-01T00:00:00Z", "end_exclusive": "2024-02-01T00:00:00Z"},
            "evidence_status": "SYNTHETIC", "contamination_status": "SYNTHETIC", "validity": "VALID",
            "opportunities": 400, "executed_trades": 250, "sample_requirement": 200,
            "filtered_trades": 100, "skipped_trades": 50, "metrics": {"unit": "R", "gross": 0.2, "net": -0.1},
            "failed_gates": ["cost"], "artifacts": {"synthetic_fixture": "a" * 64}}


def proposal(record):
    spec = copy.deepcopy(record["specification"])
    spec["execution_horizon"] = "SYNTHETIC_NEW_HORIZON"
    return {"parent_candidate_id": record["candidate_id"], "parent_evidence_sha256": sha256_value(record),
            "finding": "Gross positive; unchanged costs erase it", "question": "Does the reviewed alternative horizon survive costs?",
            "difference": "One holding horizon, not reduced costs", "changed_variable": "execution_horizon",
            "fixed_variables": {k: v for k, v in record["specification"].items() if k != "execution_horizon"},
            "baseline": record["fingerprint"], "data_required": "same synthetic fixture", "data_status": "SYNTHETIC",
            "information_gain": "Separate movement horizon from execution cost", "trial_cost": 1,
            "compute_cost": "BOUNDED_SYNTHETIC", "rejection_condition": "No matched improvement after unchanged costs",
            "stop_condition": "One preregistered comparison", "authority_required": "NEW_OWNER_APPROVED_PACKET",
            "specification": spec}


def test_cost_failure_full_handoff_and_duplicate_gate():
    record = research_record()
    proposed = proposal(record)
    result = handoff.review_batch([record], {"entries": []}, [proposed])
    assert result["reviews"][0]["failure_class"] == "COST_DESTROYED_EDGE"
    assert result["proposals"][0]["status"] == "AWAITING_APPROVAL"
    assert result["selected_next_action"]["action"] == "PREREGISTER_NEW_HYPOTHESIS"
    assert result["execution_allowed"] is False
    assert result["market_trials_added"] == 0
    duplicate = {"entries": [{"candidate_id": "PRIOR_REJECTION", "fingerprint": candidate_fingerprint(proposed["specification"])}]}
    repeated = handoff.review_batch([record], duplicate, [proposed])
    assert repeated["proposals"][0]["status"] == "DUPLICATE_REJECTED"
    assert repeated["selected_next_action"]["action"] == "INVESTIGATE_COSTS"


def test_invalid_run_blocks_descendants_and_requests_repair():
    record = research_record()
    record["validity"] = "INVALID"
    result = handoff.review_batch([record], {"entries": []}, [proposal(record)])
    assert result["reviews"][0]["failure_class"] == "INVALID_TEST"
    assert result["reviews"][0]["descendants_blocked"] is True
    assert result["proposals"][0]["status"] == "BLOCKED_INVALID_PARENT"
    assert result["selected_next_action"]["action"] == "REPAIR_MEASUREMENT"


@pytest.mark.parametrize("executed,category", [(0, "NO_EXECUTION"), (40, "INSUFFICIENT_SAMPLE")])
def test_no_execution_and_small_sample_are_not_dead(executed, category):
    record = research_record()
    record.update(executed_trades=executed, filtered_trades=None, skipped_trades=None)
    assert handoff.classify(record)["failure_class"] == category


@pytest.mark.parametrize("gate,category", [("concentration", "CONCENTRATED"), ("regime", "REGIME_DEPENDENT"), ("parameter_stability", "FRAGILE")])
def test_attribution_failures_cannot_promote(gate, category):
    record = research_record()
    record["failed_gates"] = [gate]
    assert handoff.classify(record)["failure_class"] == category
    assert handoff.classify(record)["promotion_allowed"] is False


def test_dead_is_configuration_scoped_and_stops_branch():
    record = research_record()
    record["metrics"]["gross"] = -0.01
    result = handoff.review_batch([record], {"entries": []})
    assert result["selected_next_action"]["action"] == "STOP_BRANCH"
    assert result["reviews"][0]["classification_scope"] == "TESTED_CONFIGURATION_ONLY"


def test_missing_evidence_near_miss_and_survivor_gates():
    record = research_record()
    record["metrics"]["net"] = 0.1
    record["failed_gates"] = []
    record["near_miss_status"] = "ROBUST_NEAR_MISS"
    assert handoff.classify(record)["failure_class"] != "PRELIMINARY_SURVIVOR"
    record["promotion_checks"] = dict.fromkeys(handoff.PROMOTION_REQUIREMENTS, "PASS")
    result = handoff.review_batch([record], {"entries": []})
    assert result["reviews"][0]["failure_class"] == "PRELIMINARY_SURVIVOR"
    assert result["next_state"] == "AWAITING_APPROVAL"
    assert result["execution_allowed"] is False
    record["metrics"]["unit"] = "DESCRIPTIVE_PIPS_NOT_CASH"
    assert handoff.classify(record)["failure_class"] != "PRELIMINARY_SURVIVOR"
    record.pop("artifacts")
    with pytest.raises(ValueError, match="MISSING"):
        handoff.classify(record)


def test_used_holdout_never_becomes_independent_confirmation():
    record = research_record()
    record.update(evidence_status="INDEPENDENT_VALIDATION", contamination_status="CONTAMINATED")
    with pytest.raises(ValueError, match="NOT_INDEPENDENT"):
        handoff.review_batch([record], {"entries": []})


def test_determinism_budget_parent_evidence_and_one_change():
    record = research_record()
    original = copy.deepcopy(record)
    first = handoff.review_batch([record], {"entries": []}, [proposal(record)])
    assert first == handoff.review_batch([record], {"entries": []}, [proposal(record)])
    assert record == original
    with pytest.raises(ValueError, match="BUDGET"):
        handoff.review_batch([record], {"entries": []}, [proposal(record)] * 4)
    bad = proposal(record)
    bad["parent_evidence_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="PARENT_EVIDENCE"):
        handoff.review_batch([record], {"entries": []}, [bad])
    bad = proposal(record)
    bad["specification"]["cost_contract"] = "CHEAPER"
    with pytest.raises(ValueError, match="ONE_CONTROLLED_CHANGE"):
        handoff.review_batch([record], {"entries": []}, [bad])


def test_context_join_blocks_future_or_backdated_swing():
    feature = {"pair": "EUR_USD", "timeframe": "M5", "opportunity_id": "one", "source": "SYNTHETIC",
               "latest_source_timestamp": "2024-01-01T12:00:00Z", "available_at": "2024-01-01T12:00:00Z"}
    outcome = {"pair": "EUR_USD", "timeframe": "M5", "opportunity_id": "one", "decision_at": "2024-01-01T12:00:00Z"}
    pipeline.validate_context_join(feature, outcome)
    feature["confirmed_at"] = "2024-01-01T12:05:00Z"
    with pytest.raises(ValueError, match="BACKDATED"):
        pipeline.validate_context_join(feature, outcome)
    feature.pop("confirmed_at")
    feature["latest_source_timestamp"] = "2024-01-01T12:05:00Z"
    with pytest.raises(ValueError, match="FUTURE"):
        pipeline.validate_context_join(feature, outcome)


def test_matched_comparison_counts_original_opportunities_and_no_fake_portfolio():
    baseline = {"data_identity": "SYNTHETIC", "data_boundary": "FIXED", "cost_version": "FIXED", "risk_version": "FIXED",
                "fill_version": "FIXED", "unit": "R", "specification": {"signal": "fixed", "filter": None},
                "opportunities": [{"id": "one", "decision_at": "fixed1", "status": "EXECUTED", "net": 1.0},
                                  {"id": "two", "decision_at": "fixed2", "status": "EXECUTED", "net": -0.5}]}
    challenger = copy.deepcopy(baseline)
    challenger["specification"]["filter"] = "RSI14_70_30"
    challenger["opportunities"][1].update(status="FILTERED", net=None, reason="RSI_FILTER")
    result = handoff.compare_matched_opportunities(baseline, challenger, "filter")
    assert result["baseline"]["per_executed"] == 0.25
    assert result["challenger"]["per_executed"] == 1
    assert result["challenger"]["per_original_opportunity"] == 0.5
    assert result["matched_delta"] == 0.25
    assert result["uncertainty"] is None
    assert result["portfolio_status"].startswith("NOT_EVALUATED")
    challenger["cost_version"] = "CHEAPER"
    with pytest.raises(ValueError, match="CONTROL_MISMATCH"):
        handoff.compare_matched_opportunities(baseline, challenger, "filter")


def runner_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("pkt044_runner", ROOT / "scripts/forex_delivery/run_forex_control_baseline_rsi_filter_comparison_stage1_v1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_save_once_resume_conflict_and_resource_limit(tmp_path, monkeypatch):
    runner = runner_module()
    monkeypatch.setattr(runner, "ALLOWED_ROOT", tmp_path)
    output = tmp_path / "handoff"
    payload = handoff.review_batch([research_record()], {"entries": []})
    with pytest.raises(ValueError, match="STORAGE_LIMIT"):
        runner.save_once(output, payload, max_bytes=1)
    first = runner.save_once(output, payload)
    original = (output / "handoff.json").read_bytes()
    assert runner.save_once(output, payload) == first
    assert (output / "handoff.json").read_bytes() == original
    with pytest.raises(ValueError, match="CONFLICT"):
        runner.save_once(output, {**payload, "changed": True})
    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "handoff.json").write_bytes(original)
    with pytest.raises(ValueError, match="PARTIAL_OUTPUT"):
        runner.save_once(partial, payload)
    assert runner.save_once(tmp_path / "resumed_new_folder", payload) == first


def test_writer_permission_and_collision_fail_closed():
    from datetime import datetime, timezone
    runner = runner_module()
    lock = {"status": "ACTIVE", "lock_id": runner.LOCK_ID, "worker_id": "EAST_OCC_82", "packet_id": "PKT-FOREX-044",
            "expires_at_utc": "2030-01-01T00:00:00Z", "claimed_paths": [".aios/staging/PKT_FOREX_044"]}
    output = ROOT / ".aios/staging/PKT_FOREX_044/synthetic_writer"
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    runner.check_writer({"locks": [lock]}, output, now)
    with pytest.raises(ValueError, match="MISSING_OR_EXPIRED"):
        runner.check_writer({"locks": []}, output, now)
    other = {**lock, "worker_id": "OTHER", "lock_id": "OTHER"}
    with pytest.raises(ValueError, match="OVERLAPPING"):
        runner.check_writer({"locks": [lock, other]}, output, now)


def test_completed_summary_handoff_all_cells_and_existing_successor():
    first = handoff.replay_completed_summary(ROOT)
    second = handoff.replay_completed_summary(ROOT)
    assert first == second
    assert len(first["reviews"]) == len(first["records"]) == 72
    assert first["recorded_taxonomy"] == {"COST_DESTROYED_EDGE": 30, "DEAD": 30, "NO_EXECUTION": 12}
    assert len(first["existing_successor"]["duplicate_ids"]) == 36
    assert first["existing_successor"]["new_proposals"] == 0
    assert first["next_state"] == "AWAITING_APPROVAL"
    assert first["market_rows_opened"] == first["market_trials_added"] == 0


def test_factor_publisher_idempotent_after_later_scores(copied_memory_with_two_scores, monkeypatch):
    """Exercise the real wrapper, using copied canonical paths only."""
    import importlib.util
    root, _, _, _ = copied_memory_with_two_scores
    spec = importlib.util.spec_from_file_location("pkt043_publisher_copy", ROOT / "scripts/forex_delivery/run_forex_factor_common_component_momentum_stage0_v1.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    source = root / "publisher_fixture"
    source.mkdir()
    monkeypatch.setattr(runner, "REPO_ROOT", root)
    monkeypatch.setattr(runner, "ALLOWED_ROOT", source.parent)
    for relative in (memory.TRIAL_LEDGER_RELATIVE, memory.FINGERPRINT_INDEX_RELATIVE):
        (source / relative.name).write_bytes((root / relative).read_bytes())
    # Identical staged/current bytes require a no-write successful repeat,
    # even when valid later strategies raised the global scored count.
    result = runner.promote_memory(source)
    assert result["status"] == "PASS"
    assert result["idempotent"] is True
    assert result["changed"] is False


def publisher_fixture(copied_memory, monkeypatch, growth=0):
    import importlib.util
    from automation.forex_engine import forex_factor_common_component_momentum_stage0_v1 as factor
    root, _, _, original_index = copied_memory
    spec = importlib.util.spec_from_file_location("pkt043_publisher_cases", ROOT / "scripts/forex_delivery/run_forex_factor_common_component_momentum_stage0_v1.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    source = root / "publisher_cases"
    source.mkdir()
    monkeypatch.setattr(runner, "REPO_ROOT", root)
    monkeypatch.setattr(runner, "ALLOWED_ROOT", source.parent)
    records = memory.read_trial_ledger(root / memory.TRUSTED_CORRECTED_LEDGER_RELATIVE)
    index = json.loads((root / memory.TRUSTED_CORRECTED_FINGERPRINT_INDEX_RELATIVE).read_text(encoding="utf-8"))
    for number in range(growth):
        scientific = copy.deepcopy(original_index["entries"][-1]["specification"])
        scientific["signal_family"] = f"PUBLISHER_GROWTH_{number}"
        fingerprint = candidate_fingerprint(scientific)
        identity = f"PUBLISHER_GROWTH_{number}"
        factor._append_record(records, {"event_id": identity, "candidate_id": identity,
            "candidate_fingerprint": fingerprint, "status": "VALID_TEST_REJECTED",
            "scored_trial_increment": 1, "proposed_count": 0})
        index["entries"].append({"candidate_id": identity, "fingerprint": fingerprint,
                                 "specification": scientific, "status": "VALID_TEST_REJECTED"})
    before_ledger = b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii") for row in records)
    before_index = memory.canonical_bytes(index)
    (root / memory.TRIAL_LEDGER_RELATIVE).write_bytes(before_ledger)
    (root / memory.FINGERPRINT_INDEX_RELATIVE).write_bytes(before_index)
    prior_factor = next(row for row in original_index["entries"] if row.get("packet_id") == "PKT-FOREX-043")
    cards = factor.build_edge_cards(prior_factor["specification"]["pair_currency_universe"])
    target_ledger, target_index, _ = factor.prepare_memory_registration(cards, records, index)
    (source / memory.TRIAL_LEDGER_RELATIVE.name).write_bytes(target_ledger)
    (source / memory.FINGERPRINT_INDEX_RELATIVE.name).write_bytes(target_index)
    return runner, root, source, before_ledger, before_index, target_ledger, target_index


@pytest.mark.parametrize("growth", [0, 7])
def test_publisher_registers_only_frozen_proposals_after_lawful_growth(copied_memory_with_two_scores, monkeypatch, growth):
    runner, root, source, before, _, target, target_index = publisher_fixture(copied_memory_with_two_scores, monkeypatch, growth)
    initial_count = validate_trial_ledger([json.loads(line) for line in before.splitlines()])["scored_attempt_lower_bound"]
    result = runner.promote_memory(source)
    assert result["changed"] is True
    assert result["scored_attempt_lower_bound"] == initial_count
    assert (root / memory.TRIAL_LEDGER_RELATIVE).read_bytes() == target
    assert (root / memory.FINGERPRINT_INDEX_RELATIVE).read_bytes() == target_index
    repeated = runner.promote_memory(source)
    assert repeated["idempotent"] is True
    assert repeated["new_scored_trial_increment"] == 0
    assert len(list(source.glob("memory_publication_*"))) == 1


def test_publisher_interrupted_pair_preserves_recovery_evidence(copied_memory_with_two_scores, monkeypatch):
    runner, root, source, before, before_index, target, _ = publisher_fixture(copied_memory_with_two_scores, monkeypatch, 7)
    def fail_index(*args):
        raise OSError("SYNTHETIC_INTERRUPTION_BETWEEN_FILES")
    monkeypatch.setattr(runner, "atomic_write", fail_index)
    with pytest.raises(RuntimeError, match="INTERRUPTED_REQUIRES_RECOVERY"):
        runner.promote_memory(source)
    assert (root / memory.TRIAL_LEDGER_RELATIVE).read_bytes() == target
    assert (root / memory.FINGERPRINT_INDEX_RELATIVE).read_bytes() == before_index
    recovery = next(source.glob("memory_publication_*"))
    assert (recovery / "before_ledger.jsonl").read_bytes() == before
    assert (recovery / "before_index.json").read_bytes() == before_index
    intent = json.loads((recovery / "intent.json").read_bytes())
    assert intent["before_ledger_sha256"] == pipeline.sha256_bytes(before)
    assert intent["target_ledger_sha256"] == pipeline.sha256_bytes(target)
    with pytest.raises(RuntimeError, match="PAIR_INVALID_REQUIRES_RECOVERY"):
        runner.promote_memory(source)
    assert len(list(source.glob("memory_publication_*"))) == 1
    assert (root / memory.TRIAL_LEDGER_RELATIVE).read_bytes() == target


@pytest.mark.parametrize("damage", ["prior_index", "staged_score", "deleted_history"])
def test_publisher_rejects_unapproved_or_damaged_staging_before_writes(copied_memory_with_two_scores, monkeypatch, damage):
    from automation.forex_engine import forex_factor_common_component_momentum_stage0_v1 as factor
    runner, root, source, before, before_index, _, _ = publisher_fixture(copied_memory_with_two_scores, monkeypatch)
    staged_path = source / memory.TRIAL_LEDGER_RELATIVE.name
    if damage == "prior_index":
        staged_index_path = source / memory.FINGERPRINT_INDEX_RELATIVE.name
        value = json.loads(staged_index_path.read_bytes())
        value["entries"][0]["status"] = "SURVIVOR"
        staged_index_path.write_bytes(memory.canonical_bytes(value))
    else:
        records = [json.loads(line) for line in staged_path.read_bytes().splitlines()]
        if damage == "deleted_history":
            records.pop(0)
        else:
            factor._append_record(records, {"event_id": "UNAPPROVED_SCORE", "status": "OUTCOME_EXAMINED",
                                           "scored_trial_increment": 1, "proposed_count": 0})
        staged_path.write_bytes(b"".join((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii") for row in records))
    with pytest.raises((RuntimeError, ValueError)):
        runner.promote_memory(source)
    assert (root / memory.TRIAL_LEDGER_RELATIVE).read_bytes() == before
    assert (root / memory.FINGERPRINT_INDEX_RELATIVE).read_bytes() == before_index
    assert list(source.glob("memory_publication_*")) == []


def test_publisher_excludes_concurrent_writer(copied_memory_with_two_scores, monkeypatch):
    runner, root, source, before, before_index, _, _ = publisher_fixture(copied_memory_with_two_scores, monkeypatch)
    with (root / memory.TRIAL_LEDGER_RELATIVE).open("r+b") as held:
        runner.msvcrt.locking(held.fileno(), runner.msvcrt.LK_NBLCK, 1)
        try:
            with pytest.raises(OSError):
                runner.promote_memory(source)
        finally:
            held.seek(0)
            runner.msvcrt.locking(held.fileno(), runner.msvcrt.LK_UNLCK, 1)
    assert (root / memory.TRIAL_LEDGER_RELATIVE).read_bytes() == before
    assert (root / memory.FINGERPRINT_INDEX_RELATIVE).read_bytes() == before_index
