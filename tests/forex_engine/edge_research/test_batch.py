"""Synthetic public-interface cycles; canonical memory and markets never used."""
import copy
import json
from datetime import timedelta
from pathlib import Path
import pytest

from automation.forex_engine.edge_research import batch, research, execution
from automation.forex_engine.edge_research.features import snapshots, utc
from automation.forex_engine import forex_edge_validation_pipeline_v1 as v
from automation.forex_engine import forex_edge_existence_controller_v1 as controller
from scripts.forex_delivery import run_forex_factor_common_component_momentum_stage0_v1 as publisher


def opportunities():
    combined = []
    for pair in ("EUR_USD", "GBP_USD"):
        rows = []
        for i in range(9):
            mid = dict(o=1.1, h=1.1002 if i != 8 else 1.102, l=1.0998, c=1.1)
            rows.append(dict(instrument=pair, complete=True, volume=2,
                timestamp=(utc("2024-01-03T12:00:00Z")+timedelta(minutes=5*i)).isoformat(),
                mid=mid, bid={k:x-.00005 for k,x in mid.items()}, ask={k:x+.00005 for k,x in mid.items()}))
        features = snapshots(pair, rows)
        for f in features: f.update(lower_band=1.099, upper_band=1.101, event_direction=0, rsi14=50)
        features[3]["event_direction"] = 1
        features[3]["rsi14"] = 71
        features[7]["event_direction"] = -1
        combined.extend(execution.opportunity_paths(pair, rows, features, .0001))
    return combined


def test_separate_portfolio_and_cash_reference():
    rows = opportunities()
    a = execution.portfolio(rows, 0, lambda *args: 1.)
    b = execution.portfolio(rows, 1, lambda *args: 1.)
    assert len(a["trades"]) == 4
    assert len(b["trades"]) == 2
    # Each long loses 0.00012 quote units per unit, size 250/0.00106.
    assert a["trades"][0]["pnl_usd"] == pytest.approx(-.00012*250/.00106)
    assert a["maximum_positions"] == b["maximum_positions"] == 2
    assert a["maximum_drawdown"] > 0
    assert a["net_pnl_usd"] < b["net_pnl_usd"] < 0


def test_conversion_paths_and_missing_quotes():
    paths = research.conversion_paths(["AUD_HKD", "AUD_USD"])
    assert paths["HKD"] == [("AUD_HKD", False), ("AUD_USD", True)]
    tables = {pair: {"time": [int(utc("2024-01-03T12:00:00Z").timestamp())], "bo": [bid], "ao": [ask], "bc": [bid], "ac": [ask]}
              for pair, bid, ask in (("AUD_HKD", 5., 5.01), ("AUD_USD", .64, .6401))}
    provider = research.quote_provider(tables, paths)
    assert provider("HKD", "2024-01-03T12:00:00Z", "OPEN", True) == pytest.approx(.64/5.01)
    assert provider("HKD", "2024-01-03T12:05:00Z", "CLOSE", False) == pytest.approx(.6401/5.)
    with pytest.raises(ValueError, match="CAUSAL_FX_CONVERSION_QUOTE_MISSING"):
        provider("HKD", "2024-01-03T12:05:00Z", "OPEN", True)


def test_checked_result_to_small_sample_next_question():
    cards = research.specifications(["EUR_USD", "GBP_USD"])
    result = research.measure_batch(opportunities(), {"EUR_USD": {}, "GBP_USD": {}}, cards, lambda *args: None, lambda: None)
    checked = research.checked_handoff(result, cards, {"entries": []}, {"synthetic.json": "a"*64})
    assert all(r["failure_class"] == "INSUFFICIENT_SAMPLE" for r in checked["review"]["reviews"])
    assert checked["next_state"] == "AWAITING_APPROVAL"
    assert checked["budget_remaining"] == 0
    assert checked["records"][0]["missing_gates"]
    assert "parameter_stability" not in checked["records"][0]["failed_gates"]
    assert not checked["review"]["execution_allowed"]


def test_memory_budget_idempotency_completion_and_broken_chain():
    cards = research.specifications(["EUR_USD", "GBP_USD"])
    original = v.bootstrap_trial_ledger()
    records, index = publisher.prepare_pkt044_publication(original, {"entries": []}, cards, "OUTCOME_EXAMINED", "a"*64)
    assert v.validate_trial_ledger(records)["scored_attempt_lower_bound"] == v.validate_trial_ledger(original)["scored_attempt_lower_bound"]+2
    assert publisher.prepare_pkt044_publication(records, index, cards, "OUTCOME_EXAMINED", "a"*64) == (records, index)
    completed, final_index = publisher.prepare_pkt044_publication(records, index, cards, "VALID_TEST_REJECTED", "b"*64)
    assert v.validate_trial_ledger(completed)["scored_attempt_lower_bound"] == v.validate_trial_ledger(records)["scored_attempt_lower_bound"]
    assert publisher.prepare_pkt044_publication(completed, final_index, cards, "VALID_TEST_REJECTED", "b"*64) == (completed, final_index)
    assert completed[:len(original)] == original
    with pytest.raises(ValueError, match="COMPLETION_CONFLICT"):
        publisher.prepare_pkt044_publication(completed, final_index, cards, "VALID_TEST_REJECTED", "c"*64)
    with pytest.raises(ValueError): publisher.prepare_pkt044_publication(records[:-1], index, cards, "OUTCOME_EXAMINED", "a"*64)
    broken = copy.deepcopy(records)
    broken[0]["status"] = "INVALID_TEST"
    with pytest.raises(ValueError): publisher.prepare_pkt044_publication(broken, index, cards, "OUTCOME_EXAMINED", "a"*64)
    altered = copy.deepcopy(cards)
    altered[0]["candidate_id"] = "THIRD_UNAPPROVED_STRATEGY"
    with pytest.raises(ValueError): publisher.prepare_pkt044_publication(completed, index, altered, "OUTCOME_EXAMINED", "a"*64)


def test_missing_permission_blocks_before_factory_call(monkeypatch, tmp_path):
    from automation.forex_engine import forex_high_throughput_edge_factory_v1 as factory
    monkeypatch.setattr(factory, "run_pkt044_batch", lambda *a, **kw: pytest.fail("unexpected execution"))
    with pytest.raises(ValueError, match="APPROVAL_REQUIRED"):
        controller.route_pkt044_research(tmp_path, tmp_path, {}, {}, approved=False)


def test_real_publisher_wrapper_on_synthetic_trusted_baseline(tmp_path, monkeypatch):
    """Exercise the transaction wrapper without opening protected staging evidence.

    The publisher needs a historical prefix to prove append-only behavior.  A
    self-contained signed-in-test baseline covers that transaction behavior
    without reading the real PKT-042 validation/holdout-adjacent staging tree.
    """
    from scripts.forex_delivery import run_forex_control_baseline_rsi_filter_comparison_stage1_v1 as runner
    from automation.forex_engine import forex_edge_discovery_tournament_stage1_v1 as memory
    root = tmp_path
    ledger_bytes = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
        for row in v.bootstrap_trial_ledger()
    )
    index_bytes = b'{"entries":[]}'
    for relative, payload in (
        (batch.data.TRIAL_LEDGER_RELATIVE, ledger_bytes),
        (batch.data.FINGERPRINT_INDEX_RELATIVE, index_bytes),
        (batch.data.TRUSTED_CORRECTED_LEDGER_RELATIVE, ledger_bytes),
        (batch.data.TRUSTED_CORRECTED_FINGERPRINT_INDEX_RELATIVE, index_bytes),
    ):
        target = root/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    registry = {"locks": [{
        "status": "ACTIVE",
        "lock_id": "LOCK_EAST_FOREX_CONTROL_BASELINE_RSI_FILTER_COMPARISON_STAGE1_OCC82",
        "worker_id": "EAST_OCC_82",
        "packet_id": "PKT-FOREX-044",
        "expires_at_utc": "2030-01-01T00:00:00Z",
        "claimed_paths": [
            ".aios/staging/PKT_FOREX_044",
            ".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl",
            ".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_FINGERPRINT_INDEX_V1.json",
        ],
    }]}
    target = root/"automation/orchestration/locks/FILE_LOCK_REGISTRY.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(registry))
    source = root/".aios/staging/PKT_FOREX_044/synthetic_publication"
    source.mkdir(parents=True)
    metadata = {
        "EUR_USD": {"pip_location": -4, "pip_size": 0.0001, "display_precision": 5},
        "GBP_USD": {"pip_location": -4, "pip_size": 0.0001, "display_precision": 5},
    }
    cards = research.specifications(sorted(metadata))
    digest = batch.save_new(source/"contract.json", {"cards": cards})
    monkeypatch.setattr(memory, "certified_instrument_metadata", lambda: metadata)
    monkeypatch.setattr(memory, "verify_runtime_contracts", lambda *args, **kwargs: {"status": "PASS"})
    def verify_synthetic_prefix(records, index, trusted_records, trusted_index):
        assert records[:len(trusted_records)] == trusted_records
        assert index["entries"][:len(trusted_index["entries"])] == trusted_index["entries"]
        return {"status": "PASS", "validation_mode": "SYNTHETIC_TEST_PREFIX"}
    monkeypatch.setattr(memory, "verify_append_only_corrected_memory", verify_synthetic_prefix)
    monkeypatch.setattr(publisher, "REPO_ROOT", root)
    monkeypatch.setattr(runner, "ROOT", root)
    recovery_count = [0]
    def synthetic_recovery_dir(*, prefix, dir):
        recovery = source / f"recovery_{recovery_count[0]}"
        recovery_count[0] += 1
        recovery.mkdir()
        return str(recovery)
    monkeypatch.setattr(publisher.tempfile, "mkdtemp", synthetic_recovery_dir)
    before = (root/batch.data.TRIAL_LEDGER_RELATIVE).read_bytes()
    first = publisher.publish_pkt044(source, cards, "OUTCOME_EXAMINED", digest)
    second = publisher.publish_pkt044(source, cards, "OUTCOME_EXAMINED", digest)
    assert first["changed"] is True and second["changed"] is False
    assert (root/batch.data.TRIAL_LEDGER_RELATIVE).read_bytes().startswith(before)
    assert first["scored_attempt_lower_bound"] == v.validate_trial_ledger([json.loads(x) for x in before.splitlines()])["scored_attempt_lower_bound"]+2
    invalid_digest = batch.save_new(source/"invalid_test.json", {"validity": "INVALID_TEST", "reason": "SYNTHETIC_MISSING_PATH"})
    invalid = publisher.publish_pkt044(source, cards, "INVALID_TEST", invalid_digest)
    repeated = publisher.publish_pkt044(source, cards, "INVALID_TEST", invalid_digest)
    assert invalid["changed"] and not repeated["changed"]
    assert invalid["scored_attempt_lower_bound"] == first["scored_attempt_lower_bound"]
    correction_parent = {"correction_id": "MEASUREMENT_AVAILABILITY_R1", "parent_root": "synthetic"}
    monkeypatch.setattr(batch, "verify_correction_parent", lambda ignored_root, ignored_cards: correction_parent)
    correction = source/"correction"
    correction.mkdir()
    correction_digest = batch.save_new(correction/"contract.json", {
        "cards": cards, "measurement_correction": correction_parent})
    protected = (root/batch.data.TRIAL_LEDGER_RELATIVE).read_bytes()
    index_before = (root/batch.data.FINGERPRINT_INDEX_RELATIVE).read_bytes()
    corrected = publisher.publish_pkt044(correction, cards, "OUTCOME_EXAMINED", correction_digest)
    assert corrected["changed"] and corrected["scored_attempt_lower_bound"] == first["scored_attempt_lower_bound"]
    assert not publisher.publish_pkt044(correction, cards, "OUTCOME_EXAMINED", correction_digest)["changed"]
    invalid_records = research.invalid_handoff(cards, {"contract.json": correction_digest}, ValueError("SYNTHETIC_EXECUTABLE_GAP"))
    corrected_invalid_digest = batch.save_new(correction/"invalid_test.json", {"records": invalid_records})
    corrected_invalid = publisher.publish_pkt044(correction, cards, "INVALID_TEST", corrected_invalid_digest)
    assert corrected_invalid["scored_attempt_lower_bound"] == first["scored_attempt_lower_bound"]
    assert not publisher.publish_pkt044(correction, cards, "INVALID_TEST", corrected_invalid_digest)["changed"]
    assert (root/batch.data.TRIAL_LEDGER_RELATIVE).read_bytes().startswith(protected)
    assert (root/batch.data.FINGERPRINT_INDEX_RELATIVE).read_bytes() == index_before


@pytest.mark.parametrize("interrupt", [False, True, "memory", "time", "storage", "net_gap"])
def test_actual_batch_two_runs_resume_and_no_duplicate_publication(tmp_path, monkeypatch, interrupt):
    root = tmp_path
    output = root/"batch"
    output.mkdir()
    cards = research.specifications(["EUR_USD", "GBP_USD"])
    contract = {"packet_id": "PKT-FOREX-044", "worker": "EAST_OCC_82", "cards": cards, "code_identity": {},
                "budget": {"new_scored_specifications": 2, "memory_bytes": 1024**3, "output_bytes": 1024**3, "seconds": 60}}
    resource = {"memory": "memory_bytes", "time": "seconds", "storage": "output_bytes"}.get(interrupt)
    if resource: contract["budget"][resource] = -1
    batch.save_new(output/"contract.json", contract)
    registry_path = root/"automation/orchestration/locks/FILE_LOCK_REGISTRY.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{}")
    index_path = root/batch.data.FINGERPRINT_INDEX_RELATIVE
    index_path.parent.mkdir(parents=True)
    index_path.write_text('{"entries":[]}')
    from scripts.forex_delivery import run_forex_control_baseline_rsi_filter_comparison_stage1_v1 as runner
    monkeypatch.setattr(runner, "check_writer", lambda *args: None)
    monkeypatch.setattr(batch, "code_identity", lambda path: {})
    monkeypatch.setattr(batch, "resident_bytes", lambda: 1000)
    calls = []
    def prepare(corpus, manifest, progress, before_outcome, check_limits):
        calls.append("prepare")
        before_outcome()
        if interrupt == "net_gap":
            raise execution.PricePathUnavailable("UNRESOLVED_OPEN_POSITION_PRICE_GAP", midpoint=False, pair="EUR_USD")
        if interrupt and len(calls) == 2:
            raise KeyboardInterrupt("synthetic interruption after first complete run")
        return opportunities(), {"EUR_USD": {}, "GBP_USD": {}}, {}
    monkeypatch.setattr(research, "prepare_inputs", prepare)
    memory = [v.bootstrap_trial_ledger(), {"entries": []}]
    def publish(source, incoming, phase, evidence):
        memory[:] = publisher.prepare_pkt044_publication(*memory, incoming, phase, evidence)
        return v.validate_trial_ledger(memory[0])
    monkeypatch.setattr(publisher, "publish_pkt044", publish)
    manifest = {"eligible_pairs": ["EUR_USD", "GBP_USD"]}
    if interrupt == "net_gap":
        with pytest.raises(ValueError, match="UNRESOLVED_OPEN_POSITION_PRICE_GAP"):
            controller.route_pkt044_research(root, output, contract, manifest, approved=True)
        invalid = json.loads((output/"invalid_test.json").read_bytes())
        assert all(r["executed_trades"] is None and r["validity"] == "INVALID" for r in invalid["records"])
        assert invalid["review"]["selected_next_action"]["action"] == "REPAIR_MEASUREMENT"
        assert all(r["descendants_blocked"] for r in invalid["review"]["reviews"])
        assert batch.status(output)["publication"]["scored_attempt_lower_bound"] == v.validate_trial_ledger(v.bootstrap_trial_ledger())["scored_attempt_lower_bound"]+2
        return
    if resource:
        with pytest.raises(ValueError, match="BATCH_.*_LIMIT"):
            controller.route_pkt044_research(root, output, contract, manifest, approved=True)
        assert calls == []
        assert memory[0] == v.bootstrap_trial_ledger()
        assert batch.status(output)["state"] == "BLOCKED"
        with pytest.raises(ValueError, match="BLOCKED_BATCH_REQUIRES_DIAGNOSIS"):
            controller.route_pkt044_research(root, output, contract, manifest, approved=True, resume=True)
        return
    if interrupt:
        with pytest.raises(KeyboardInterrupt):
            controller.route_pkt044_research(root, output, contract, manifest, approved=True)
        assert batch.status(output)["state"] == "RUNNING"
        assert v.validate_trial_ledger(memory[0])["scored_attempt_lower_bound"] == v.validate_trial_ledger(v.bootstrap_trial_ledger())["scored_attempt_lower_bound"]+2
    result = controller.route_pkt044_research(root, output, contract, manifest, approved=True, resume=interrupt)
    assert result["state"] == "BATCH_COMPLETE"
    assert result["budget_remaining"] == 0
    assert calls == ["prepare"]*(3 if interrupt else 2)
    count = len(memory[0])
    assert controller.route_pkt044_research(root, output, contract, manifest, approved=True, resume=True) == result
    assert len(memory[0]) == count
    assert calls == ["prepare"]*(3 if interrupt else 2)
    # Completed fixture result is consumed through the same checked planner a
    # second time, without additional market scoring or a planner self-approval.
    checked = json.loads((output/"handoff.json").read_bytes())
    second = research.handoff.review_batch(checked["records"], memory[1])
    assert second["next_state"] == "AWAITING_APPROVAL" and not second["execution_allowed"]
    (output/"run1/scientific_result.json").write_text("{}")
    with pytest.raises(ValueError, match="ARTIFACT_CHANGED"): batch.status(output)


def test_gross_coverage_does_not_summarize_favorable_available_subset():
    result = research.measures([5., None, 1.])
    assert result["count"] == 3 and result["missing_count"] == 1
    assert result["available_count"] == 2
    assert result["expectancy"] is None and result["profit_factor"] is None


def test_invalid_counts_remain_unknown_but_valid_counts_are_required():
    cards = research.specifications(["EUR_USD", "GBP_USD"])
    records = research.invalid_handoff(cards, {"synthetic.json": "a"*64}, ValueError("MISSING_PATH"))
    checked = v.validate_research_record(records[0])
    assert "executed_trades" in checked["missing_fields"]
    records[0]["validity"] = "VALID"
    with pytest.raises(ValueError, match="COUNT_INVALID"): v.validate_research_record(records[0])


def test_correction_preserves_original_attempts_and_is_idempotent():
    cards = research.specifications(["EUR_USD", "GBP_USD"])
    records, index = publisher.prepare_pkt044_publication(v.bootstrap_trial_ledger(), {"entries": []}, cards, "OUTCOME_EXAMINED", "a"*64)
    records, index = publisher.prepare_pkt044_publication(records, index, cards, "INVALID_TEST", "b"*64)
    old = copy.deepcopy(records)
    corrected, corrected_index = publisher.prepare_pkt044_publication(records, index, cards, "OUTCOME_EXAMINED", "c"*64, correction_id=batch.CORRECTION_ID)
    assert corrected[:len(old)] == old and corrected_index == index
    assert v.validate_trial_ledger(corrected)["scored_attempt_lower_bound"] == v.validate_trial_ledger(old)["scored_attempt_lower_bound"]
    assert all(r["corrects_event_id"].endswith(":INVALID_TEST") for r in corrected[len(old):])
    assert publisher.prepare_pkt044_publication(corrected, index, cards, "OUTCOME_EXAMINED", "c"*64, correction_id=batch.CORRECTION_ID) == (corrected, index)
    with pytest.raises(ValueError, match="CORRECTION_PARENT_MISSING"):
        publisher.prepare_pkt044_publication(v.bootstrap_trial_ledger(), {"entries": []}, cards, "OUTCOME_EXAMINED", "c"*64, correction_id=batch.CORRECTION_ID)
    with pytest.raises(ValueError, match="CORRECTION_NOT_APPROVED"):
        publisher.prepare_pkt044_publication(old, index, cards, "OUTCOME_EXAMINED", "c"*64, correction_id="ANOTHER_RESEARCH_JOB")


def test_correction_parent_is_trusted_not_reset_from_current_bytes(tmp_path):
    actual = Path(__file__).resolve().parents[3]
    cards = json.loads((actual/batch.PARENT_ROOT/"contract.json").read_bytes())["cards"]
    parent = tmp_path/batch.PARENT_ROOT
    parent.mkdir(parents=True)
    for name in ("contract.json", "invalid_test.json"):
        (parent/name).write_bytes((actual/batch.PARENT_ROOT/name).read_bytes())
    assert batch.verify_correction_parent(tmp_path, cards)["new_strategy_specifications"] == 0
    altered = copy.deepcopy(cards)
    altered[0]["specification"]["parameters"]["atr"] = 5
    with pytest.raises(ValueError, match="CHANGED_ECONOMIC"):
        batch.verify_correction_parent(tmp_path, altered)
    (parent/"invalid_test.json").write_text("{}")
    with pytest.raises(ValueError, match="PARENT_EVIDENCE_CHANGED"):
        batch.verify_correction_parent(tmp_path, cards)
