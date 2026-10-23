from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from automation.forex_engine.forex_packet033_r5_continuation_v1 import (
    PREVIOUS_PRODUCTIVE_MINUTES,
    REQUESTED_TIMEFRAMES,
    acquisition_load_plan,
    audit_packet033_hypothesis_ledger,
    append_task_entry,
    audit_m30_macd_readiness,
    audit_packet_integrity,
    audit_technique_inventory_state,
    audit_timeframe_coverage_state,
    build_checkpoint,
    build_attack_state,
    build_r5_state,
    build_stop_proof,
    corpus_freeze_plan,
    empty_task_ledger,
    evaluate_gross_edge_gate,
    estimate_candles_by_granularity,
    finalist_forward_v13_readiness,
    first_incomplete_task,
    plan_compute_shards,
    productive_time_state,
    sha256_file,
    sha256_text,
    stable,
    task_statuses,
    validate_hypothesis_ledger,
    validate_physical_artifacts,
    validate_technique_fidelity,
    validate_timeframe_mapping,
    verify_task_ledger,
    write_authoritative_r5_outputs,
    write_checkpoint_bundle,
)


START = "2026-08-31T13:00:00Z"
END = "2026-08-31T13:01:00Z"


def _append(ledger, task_id: str, seconds: float = 60.0):
    if ledger.get("entries"):
        start = datetime.fromisoformat(ledger["entries"][-1]["ended_at_utc"].replace("Z", "+00:00"))
    else:
        start = datetime(2026, 8, 31, 13, tzinfo=timezone.utc)
    end = start + timedelta(seconds=seconds)
    return append_task_entry(
        ledger,
        task_id=task_id,
        status="COMPLETE",
        productive_seconds=seconds,
        evidence=[f"{task_id}:PASS"],
        started_at_utc=start.isoformat().replace("+00:00", "Z"),
        ended_at_utc=end.isoformat().replace("+00:00", "Z"),
    )


def _artifact_fixture(tmp_path: Path):
    artifact = tmp_path / "EUR_USD_S5.json"
    document = {
        "instrument": "EUR_USD",
        "granularity": "S5",
        "price": "MBA",
        "candles": [
            {"time": "2026-01-01T00:00:00Z", "complete": True, "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.1"}, "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.0"}, "ask": {"o": "1.2", "h": "1.3", "l": "1.1", "c": "1.2"}},
            {"time": "2026-01-01T00:00:05Z", "complete": True, "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.1"}, "bid": {"o": "1.0", "h": "1.1", "l": "0.9", "c": "1.0"}, "ask": {"o": "1.2", "h": "1.3", "l": "1.1", "c": "1.2"}},
        ],
    }
    artifact.write_text(json.dumps(document), encoding="utf-8")
    scope = {"instruments": ["EUR_USD"], "granularities": ["S5"], "price": "MBA"}
    manifest = {
        "scope": scope,
        "scope_fingerprint": sha256_text(stable(scope)),
        "series": [
            {
                "series_id": "EUR_USD.S5.MBA",
                "relative_path": artifact.name,
                "sha256": sha256_file(artifact),
                "instrument": "EUR_USD",
                "granularity": "S5",
                "price": "MBA",
                "from_utc": "2026-01-01T00:00:00Z",
                "to_utc": "2026-01-01T00:00:10Z",
            }
        ],
    }
    return artifact, document, manifest


def _timeframe_mapping():
    return {timeframe: {"source_kind": "NATIVE", "source_timeframes": [timeframe]} for timeframe in REQUESTED_TIMEFRAMES}


def _queue_state():
    queue = [
        {
            "queue_id": f"Q-{index}",
            "indicator_combination": "MACD",
            "timeframe": "M30",
            "direction": "LONG" if index < 2 else "SHORT",
            "trade_count": 5,
            "status": "QUEUED_FOR_FULL_REPLICATION",
        }
        for index in range(3)
    ]
    queue.extend({"queue_id": f"Q-{index}"} for index in range(3, 263))
    return {
        "packet032_hypotheses": 912,
        "queued_raw_positive_diagnostics": 263,
        "macd_m30_long_count": 2,
        "macd_m30_short_count": 1,
        "macd_m30_replication_neighborhood": {
            "macd_families": [[12, 26, 9]],
            "histogram_variants": ["histogram_sign"],
        },
        "queue": queue,
        "queue_hash": sha256_text(stable(queue)),
    }


def _techniques():
    return [
        {
            "technique_id": f"TECH-{index:03d}",
            "directions": ["LONG", "SHORT"],
            "objective_entry_rules": ["entry"],
            "objective_exit_rules": ["exit"],
            "controls": ["control"],
            "fingerprint": f"fp-{index}",
            "requires_order_flow": False,
        }
        for index in range(82)
    ]


def test_task_ledger_is_hash_chained_and_totals_productive_time():
    ledger = _append(empty_task_ledger(), "T01", 90)
    ledger = _append(ledger, "T02", 30)
    result = verify_task_ledger(ledger)
    assert result.passed
    time_state = productive_time_state(ledger)
    assert time_state["productive_minutes_cumulative"] == PREVIOUS_PRODUCTIVE_MINUTES + 2
    assert time_state["productive_minutes_remaining"] == 57.6


def test_task_ledger_rejects_tampering_and_duplicate_completion():
    ledger = _append(empty_task_ledger(), "T01")
    tampered = json.loads(json.dumps(ledger))
    tampered["entries"][0]["productive_seconds"] = 999
    assert not verify_task_ledger(tampered).passed
    with pytest.raises(ValueError, match="completed task cannot be appended twice"):
        _append(ledger, "T01")


def test_task_ledger_rejects_inflated_productive_time_and_overlap():
    with pytest.raises(ValueError, match="cannot exceed elapsed"):
        append_task_entry(
            empty_task_ledger(),
            task_id="T01",
            status="COMPLETE",
            productive_seconds=61,
            evidence=["test"],
            started_at_utc=START,
            ended_at_utc=END,
        )
    ledger = _append(empty_task_ledger(), "T01")
    with pytest.raises(ValueError, match="cannot overlap"):
        append_task_entry(
            ledger,
            task_id="T02",
            status="COMPLETE",
            productive_seconds=1,
            evidence=["test"],
            started_at_utc=START,
            ended_at_utc=END,
        )


def test_task_ledger_allows_blocked_task_to_reopen_and_complete():
    ledger = empty_task_ledger()
    for index in range(1, 9):
        ledger = _append(ledger, f"T{index:02d}")
    blocked_start = "2026-08-31T13:08:00Z"
    blocked_end = "2026-08-31T13:08:01Z"
    ledger = append_task_entry(
        ledger,
        task_id="T08",
        status="BLOCKED",
        productive_seconds=0,
        evidence=["P1 regression discovered"],
        started_at_utc=blocked_start,
        ended_at_utc=blocked_end,
    )
    ledger = _append(ledger, "T08", 120)
    assert verify_task_ledger(ledger).passed
    assert task_statuses(ledger)["T08"] == "COMPLETE"
    assert ledger["entries"][-1]["reopened_task_resolution"] is True


def test_task_ledger_rejects_structurally_valid_but_unsafe_entries():
    with pytest.raises(ValueError, match="out of order"):
        _append(empty_task_ledger(), "T02")
    with pytest.raises(ValueError, match="evidence"):
        append_task_entry(
            empty_task_ledger(),
            task_id="T01",
            status="COMPLETE",
            productive_seconds=1,
            evidence=[],
            started_at_utc=START,
            ended_at_utc=END,
        )
    with pytest.raises(ValueError, match="finite"):
        append_task_entry(
            empty_task_ledger(),
            task_id="T01",
            status="COMPLETE",
            productive_seconds=float("nan"),
            evidence=["test"],
            started_at_utc=START,
            ended_at_utc=END,
        )
    ledger = _append(empty_task_ledger(), "T01")
    tampered = json.loads(json.dumps(ledger))
    tampered["entries"][0]["status"] = "MAGIC"
    tampered["entries"][0]["entry_hash"] = sha256_text(stable({
        key: value for key, value in tampered["entries"][0].items() if key != "entry_hash"
    }))
    assert not verify_task_ledger(tampered).passed


def test_checkpoint_selects_first_incomplete_and_token_pause():
    ledger = _append(empty_task_ledger(), "T01")
    checkpoint = build_checkpoint(
        ledger,
        current_lock="LOCK-A",
        human_artifacts_present=False,
        token_budget_pause=True,
    )
    assert first_incomplete_task(ledger) == "T02"
    assert checkpoint["status"] == "CODEX_TOKEN_BUDGET_PAUSE"
    assert checkpoint["same_packet_resume_required"] is True


def test_checkpoint_routes_to_human_only_after_all_pre_data_tasks():
    ledger = empty_task_ledger()
    for index in range(1, 16):
        ledger = _append(ledger, f"T{index:02d}")
    checkpoint = build_checkpoint(ledger, current_lock="LOCK-A", human_artifacts_present=False)
    assert checkpoint["first_incomplete_task"] == "P01"
    assert checkpoint["status"] == "WAITING_HUMAN_SCALPING_ARTIFACTS"


def test_physical_artifact_validator_accepts_valid_complete_series(tmp_path: Path):
    _, _, manifest = _artifact_fixture(tmp_path)
    result = validate_physical_artifacts(tmp_path, manifest)
    assert result.passed, result.errors
    assert result.evidence["series_count"] == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda artifact, document, manifest: manifest.update(scope_fingerprint="bad"), "scope fingerprint"),
        (lambda artifact, document, manifest: manifest["series"][0].update(sha256="bad"), "artifact hash"),
        (lambda artifact, document, manifest: manifest["series"][0].update(relative_path="../escape.json"), "escapes root"),
    ],
)
def test_physical_artifact_validator_fails_closed(tmp_path: Path, mutation, message: str):
    artifact, document, manifest = _artifact_fixture(tmp_path)
    mutation(artifact, document, manifest)
    result = validate_physical_artifacts(tmp_path, manifest)
    assert not result.passed
    assert any(message in error for error in result.errors)


def test_physical_artifact_validator_rejects_duplicates_gaps_and_incomplete(tmp_path: Path):
    artifact, document, manifest = _artifact_fixture(tmp_path)
    document["candles"] = [
        document["candles"][0],
        {**document["candles"][0]},
        {"time": "2026-01-01T00:00:15Z", "complete": False, "mid": {"o": 1, "h": 1, "l": 1, "c": 1}, "bid": {"o": 1, "h": 1, "l": 1, "c": 1}, "ask": {"o": 1, "h": 1, "l": 1, "c": 1}},
    ]
    artifact.write_text(json.dumps(document), encoding="utf-8")
    manifest["series"][0]["sha256"] = sha256_file(artifact)
    result = validate_physical_artifacts(tmp_path, manifest)
    assert not result.passed
    assert any("duplicate" in error for error in result.errors)
    assert any("incomplete" in error for error in result.errors)
    assert any("gap" in error for error in result.errors)


def test_physical_artifact_validator_rejects_nonfinite_sensitive_and_bad_identity(tmp_path: Path):
    artifact, document, manifest = _artifact_fixture(tmp_path)
    document["candles"][0]["mid"]["c"] = "NaN"
    document["candles"][0]["unexpected"] = "Bearer secret-value"
    artifact.write_text(json.dumps(document), encoding="utf-8")
    manifest["series"][0]["sha256"] = sha256_file(artifact)
    manifest["series"][0]["series_id"] = "WRONG"
    result = validate_physical_artifacts(tmp_path, manifest)
    assert not result.passed
    assert any("non-finite" in error for error in result.errors)
    assert any("secret" in error for error in result.errors)
    assert any("series identity" in error for error in result.errors)


def test_physical_artifact_validator_fails_closed_on_malformed_allowed_gap(tmp_path: Path):
    artifact, document, manifest = _artifact_fixture(tmp_path)
    document["candles"][1]["time"] = "2026-01-01T00:00:10Z"
    artifact.write_text(json.dumps(document), encoding="utf-8")
    manifest["series"][0]["sha256"] = sha256_file(artifact)
    manifest["series"][0]["to_utc"] = "2026-01-01T00:00:15Z"
    manifest["allowed_gaps"] = {"EUR_USD.S5.MBA": ["malformed"]}
    result = validate_physical_artifacts(tmp_path, manifest)
    assert not result.passed
    assert any("unexplained" in error for error in result.errors)


@pytest.mark.parametrize("payload", (b"[]", b"\xff\xfeinvalid"))
def test_physical_artifact_validator_fails_closed_on_nonobject_or_nonutf8_json(tmp_path: Path, payload: bytes):
    artifact, _, manifest = _artifact_fixture(tmp_path)
    artifact.write_bytes(payload)
    manifest["series"][0]["sha256"] = sha256_file(artifact)
    result = validate_physical_artifacts(tmp_path, manifest)
    assert not result.passed
    assert any("invalid JSON" in error or "root must be an object" in error for error in result.errors)


def test_physical_artifact_validator_accepts_exact_declared_market_gap(tmp_path: Path):
    artifact, document, manifest = _artifact_fixture(tmp_path)
    document["candles"][1]["time"] = "2026-01-01T00:00:10Z"
    artifact.write_text(json.dumps(document), encoding="utf-8")
    manifest["series"][0]["sha256"] = sha256_file(artifact)
    manifest["series"][0]["to_utc"] = "2026-01-01T00:00:15Z"
    manifest["allowed_gaps"] = {
        "EUR_USD.S5.MBA": [
            {"after_utc": "2026-01-01T00:00:00Z", "before_utc": "2026-01-01T00:00:10Z", "reason": "MARKET_CLOSED"}
        ]
    }
    result = validate_physical_artifacts(tmp_path, manifest)
    assert result.passed, result.errors
    assert any("declared MARKET_CLOSED gap" in warning for warning in result.warnings)


def test_corpus_freeze_rejects_timeframe_mapping_that_violates_derivation_rules(tmp_path: Path):
    _, _, manifest = _artifact_fixture(tmp_path)
    mapping = _timeframe_mapping()
    mapping["S1"] = {"source_kind": "DERIVED", "source_timeframes": ["S5"]}
    result = corpus_freeze_plan(tmp_path, manifest, mapping)
    assert not result.passed
    assert any("S1 cannot be derived" in error for error in result.errors)


def test_physical_artifact_validator_rejects_bad_quote_geometry(tmp_path: Path):
    artifact, document, manifest = _artifact_fixture(tmp_path)
    document["candles"][0]["bid"]["c"] = "1.5"
    artifact.write_text(json.dumps(document), encoding="utf-8")
    manifest["series"][0]["sha256"] = sha256_file(artifact)
    result = validate_physical_artifacts(tmp_path, manifest)
    assert not result.passed
    assert any("bid" in error for error in result.errors)


def test_corpus_freeze_plan_requires_complete_mapping_and_is_deterministic(tmp_path: Path):
    _, _, manifest = _artifact_fixture(tmp_path)
    mapping = _timeframe_mapping()
    first = corpus_freeze_plan(tmp_path, manifest, mapping)
    second = corpus_freeze_plan(tmp_path, manifest, mapping)
    assert first.passed
    assert first.evidence["aggregate_hash"] == second.evidence["aggregate_hash"]
    del mapping["S1"]
    assert not corpus_freeze_plan(tmp_path, manifest, mapping).passed


def test_timeframe_mapping_enforces_s1_s45_and_mo6_rules():
    mapping = _timeframe_mapping()
    assert validate_timeframe_mapping(mapping).passed
    mapping["S1"] = {"source_kind": "DERIVED", "source_timeframes": ["S5"]}
    mapping["S45"] = {"source_kind": "DERIVED", "source_timeframes": ["S5"], "source_seconds": 5, "alignment_seconds": 30}
    mapping["MO6"] = {"source_kind": "DERIVED", "source_timeframes": ["MN1"], "complete_source_candles": 5}
    result = validate_timeframe_mapping(mapping)
    assert not result.passed
    assert len(result.errors) == 3


def test_repository_timeframe_coverage_schema_enforces_special_mappings():
    matrix = {
        timeframe: {
            "Development_eligible": False,
            "completed_bar_integrity": False,
            "native_or_derived_status": "UNAVAILABLE_WITH_CURRENT_EVIDENCE",
            "source": "NONE",
        }
        for timeframe in REQUESTED_TIMEFRAMES
    }
    matrix["MO6"] = {
        "Development_eligible": True,
        "completed_bar_integrity": True,
        "native_or_derived_status": "DERIVED_FROM_VALID_LOWER_TIMEFRAME",
        "source": "SIX_COMPLETE_CONSECUTIVE_MN1_CANDLES_JAN_JUN_JUL_DEC",
    }
    state = {
        "requested_timeframes": list(REQUESTED_TIMEFRAMES),
        "timeframes": matrix,
        "all_requested_timeframes_classified": True,
        "unavailable_timeframes": ["S1", "S45"],
        "coverage_hash": "hash",
    }
    assert audit_timeframe_coverage_state(state).passed
    state["timeframes"]["S1"]["source"] = "DERIVED_FROM_S5"
    assert not audit_timeframe_coverage_state(state).passed


def test_packet_integrity_proves_912_263_2_1_82_without_promotion():
    queue_state = _queue_state()
    packet033 = {
        "queued_packet032_positive_diagnostics": 263,
        "macd_m30_long_queued": 2,
        "macd_m30_short_queued": 1,
        "finalist_status": "NO_FINALISTS_TO_VALIDATE",
    }
    result = audit_packet_integrity(queue_state, packet033, {"technique_count": 82})
    assert result.passed, result.errors
    queue_state["queue"][1]["queue_id"] = queue_state["queue"][0]["queue_id"]
    assert not audit_packet_integrity(queue_state, packet033, {"technique_count": 82}).passed


def test_technique_fidelity_requires_objective_directional_contracts():
    techniques = _techniques()
    assert validate_technique_fidelity(techniques).passed
    techniques[0]["directions"] = ["BOTH"]
    techniques[1]["objective_entry_rules"] = []
    techniques[2]["requires_order_flow"] = True
    assert len(validate_technique_fidelity(techniques).errors) == 3


def test_repository_technique_inventory_schema_proves_82_unique_mechanical_ids():
    techniques = [f"TECH-{index:03d}" for index in range(82)]
    families = []
    for index in range(12):
        start = index * 7
        selected = techniques[start : start + 7] if index < 11 else techniques[start:]
        family = {
            "family_id": chr(ord("A") + index),
            "techniques": selected,
            "mechanical_definition_required": True,
            "long_short_separate": True,
            "data_requirement": "ORDER_BOOK_OR_TRADE_TAPE" if index == 11 else "OHLC_BID_ASK",
            "status": "INELIGIBLE_ORDER_FLOW_OR_SUBMINUTE_DATA_NOT_AVAILABLE" if index == 11 else "CLASSIFIED_OHLC_SUPPORTED",
            "behavior_fingerprint": "a" * 64,
        }
        families.append(family)
    inventory = {
        "family_count": 12,
        "technique_count": 82,
        "families": families,
        "inventory_hash": sha256_text(stable(families)),
    }
    contracts = [
        {
            "technique_id": technique,
            "directions": ["LONG", "SHORT"],
            "objective_entry_rules": ["completed-bar entry"],
            "objective_exit_rules": ["completed-bar exit"],
            "controls": ["spread gate"],
            "data_requirement": "ORDER_BOOK_OR_TRADE_TAPE" if technique in techniques[-5:] else "OHLC_BID_ASK",
            "data_eligible": False if technique in techniques[-5:] else True,
            "fingerprint": "c" * 64,
        }
        for technique in techniques
    ]
    fidelity = {
        "mechanical": True,
        "causal_completed_bar_only": True,
        "subjective_chart_drawing": False,
        "order_book_claims": False,
        "centralized_volume_claims": False,
        "code_fingerprint": "b" * 64,
        "technique_contracts": contracts,
        "contract_registry_hash": sha256_text(stable(contracts)),
    }
    assert audit_technique_inventory_state(inventory, fidelity).passed
    inventory["families"][0]["long_short_separate"] = False
    assert not audit_technique_inventory_state(inventory, fidelity).passed


def test_compute_shards_are_deterministic_single_writer_and_reusable():
    first = plan_compute_shards(["M30", "M5"], ["MACD", "ADX"], ["LONG", "SHORT"], ["TIER1"])
    second = plan_compute_shards(["M5", "M30"], ["ADX", "MACD"], ["SHORT", "LONG"], ["TIER1"])
    assert first["progress_hash"] == second["progress_hash"]
    assert first["planned_shard_count"] == 8
    assert first["silent_sample_reduction"] is False
    shard = first["shards"][0]
    reused = plan_compute_shards(
        [shard["timeframe"]], [shard["technique_id"]], [shard["direction"]], [shard["pair_tier"]],
        completed={shard["shard_id"]: shard["shard_hash"]},
    )
    assert reused["shards"][0]["status"] == "REUSE_COMPLETE"


def test_hypothesis_ledger_preserves_negative_results_and_trials():
    ledger = {
        "append_only": True,
        "negative_results_preserved": True,
        "effective_trial_count": 3,
        "hypotheses": [
            {"hypothesis_id": "H1", "status": "NO_EDGE"},
            {"hypothesis_id": "H2", "status": "PASS"},
        ],
    }
    result = validate_hypothesis_ledger(ledger)
    assert result.passed
    assert result.evidence["negative_count"] == 1
    ledger["effective_trial_count"] = 1
    assert not validate_hypothesis_ledger(ledger).passed


def test_packet033_hypothesis_schema_reconciles_queued_and_attempted_trials():
    entries = [
        {"hypothesis_id": "H1", "result": "QUEUED_NOT_EXECUTED_DATA_GATE"},
        {"hypothesis_id": "H2", "result": "NO_EDGE"},
    ]
    ledger = {
        "entries": entries,
        "effective_trials": 1,
        "total_attempted": 1,
        "hidden_trials_possible": False,
        "screen": {"attempted": 1},
        "full_replication": {"attempted": 0},
        "interactions": {"attempted": 0},
        "ledger_hash": sha256_text(stable(entries)),
    }
    assert audit_packet033_hypothesis_ledger(ledger).passed
    ledger["hidden_trials_possible"] = True
    assert not audit_packet033_hypothesis_ledger(ledger).passed


def test_gross_edge_gate_separates_positive_and_negative_fixtures():
    positive = {
        "sample_size": 100,
        "fold_count": 5,
        "positive_fold_share": 0.8,
        "pair_count": 6,
        "max_pair_share": 0.3,
        "parameter_neighbor_pass_count": 3,
        "gross_expectancy": 0.1,
        "gross_profit_factor": 1.2,
        "direction": "LONG",
        "multiple_testing_route": "REQUIRED",
    }
    assert evaluate_gross_edge_gate(positive).passed
    negative = {**positive, "sample_size": 5, "max_pair_share": 0.9, "gross_expectancy": -0.1}
    assert not evaluate_gross_edge_gate(negative).passed


def test_m30_macd_readiness_preserves_clues_as_unpromoted():
    state = _queue_state()
    result = audit_m30_macd_readiness(state)
    assert result.passed, result.errors
    state["queue"][0]["status"] = "FINALIST"
    assert not audit_m30_macd_readiness(state).passed


def test_finalist_readiness_rejects_invented_downstream_evidence():
    state = {"long_gross_edge": False, "short_gross_edge": False, "forward_opened": False, "v13_opened": False, "paper_opened": False}
    assert finalist_forward_v13_readiness(state).passed
    state["forward_opened"] = True
    assert not finalist_forward_v13_readiness(state).passed


def test_acquisition_plan_is_practice_get_only_and_checkpointed():
    plan = acquisition_load_plan(
        instruments=["EUR_USD", "GBP_USD"],
        granularities=["S5", "M1"],
        estimated_candles_per_series=10_001,
        candles_per_request=5_000,
    )
    assert plan["series_count"] == 4
    assert plan["estimated_request_count"] == 12
    assert plan["pacing_policy"] == "SINGLE_IN_FLIGHT_FIXED_MINIMUM_INTERVAL"
    assert plan["estimated_minimum_request_duration_seconds"] == 6
    assert plan["practice_get_only"] is True
    assert plan["orders_allowed"] is False
    assert plan["resume_from_first_incomplete_series"] is True
    assert "<" not in plan["plan_command"]
    assert "-WhatIfOnly" in plan["plan_command"]
    assert "-WhatIfOnly" not in plan["acquisition_command"]


def test_acquisition_estimate_scales_each_granularity_from_exact_interval():
    estimates = estimate_candles_by_granularity(
        "2026-01-01T00:00:00Z",
        "2026-01-08T00:00:00Z",
        ["S5", "M1"],
        market_open_ratio=5 / 7,
    )
    assert estimates["S5"] == 86_400
    assert estimates["M1"] == 7_200
    plan = acquisition_load_plan(
        instruments=["EUR_USD", "GBP_USD"],
        granularities=["S5", "M1"],
        estimated_candles_per_series=estimates,
        candles_per_request=5_000,
    )
    assert plan["estimated_requests_by_granularity"] == {"M1": 4, "S5": 36}
    assert plan["estimated_request_count"] == 40


def test_acquisition_plan_rejects_empty_or_noncanonical_series_inputs():
    with pytest.raises(ValueError, match="at least one"):
        acquisition_load_plan(
            instruments=[],
            granularities=["S5"],
            estimated_candles_per_series=100,
            candles_per_request=50,
        )
    with pytest.raises(ValueError, match="canonical"):
        acquisition_load_plan(
            instruments=["EUR_USD'; Write-Output pwned; '"],
            granularities=["S5"],
            estimated_candles_per_series=100,
            candles_per_request=50,
        )
    with pytest.raises(ValueError, match="unsupported"):
        acquisition_load_plan(
            instruments=["EUR_USD"],
            granularities=["S6"],
            estimated_candles_per_series=100,
            candles_per_request=50,
        )
    with pytest.raises(ValueError, match="pacing"):
        acquisition_load_plan(
            instruments=["EUR_USD"],
            granularities=["S5"],
            estimated_candles_per_series=100,
            candles_per_request=50,
            minimum_request_interval_seconds=0,
        )


def test_acquisition_plan_quotes_output_root_and_rounds_estimates_up():
    estimates = estimate_candles_by_granularity(
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:06Z",
        ["S5"],
        market_open_ratio=1.0,
    )
    assert estimates == {"S5": 2}
    plan = acquisition_load_plan(
        instruments=["EUR_USD"],
        granularities=["S5"],
        estimated_candles_per_series=estimates,
        candles_per_request=50,
        output_root="safe'root",
    )
    assert "-OutputRoot 'safe''root'" in plan["plan_command"]


def test_stop_proof_fails_while_independent_tasks_or_audits_remain():
    ledger = _append(empty_task_ledger(), "T01")
    checkpoint = build_checkpoint(ledger, current_lock="LOCK-A", human_artifacts_present=False)
    stop_proof = build_stop_proof(
        checkpoint,
        {"T06": {"status": "FAIL"}},
        active_compute_shard_count=2,
        compute_shard_evidence="fixture-active-shards",
    )
    assert stop_proof["stop_allowed"] is False
    assert stop_proof["repairable_p0_p1_count"] == 1
    assert stop_proof["active_compute_shard_count"] == 2
    assert stop_proof["alternate_safe_actions"] == ["CONTINUE_T02"]


def test_r5_and_attack_states_preserve_resume_and_safety_evidence():
    ledger = _append(empty_task_ledger(), "T01")
    plan = acquisition_load_plan(
        instruments=["EUR_USD"],
        granularities=["S5"],
        estimated_candles_per_series=100,
        candles_per_request=50,
    )
    state = build_r5_state(
        ledger,
        current_lock="LOCK-A",
        human_artifacts_present=False,
        audits={"T06": {"status": "PASS"}},
        acquisition_plan=plan,
    )
    assert state["safety"]["live_order"] is False
    assert state["state_hash"]
    attack = build_attack_state({"request_contract_repair": {"status": "PASS"}}, state)
    assert attack["request_contract_repair"]["status"] == "PASS"
    assert attack["stop_point"] == "T02"


def test_checkpoint_bundle_writes_parseable_consistent_json(tmp_path: Path):
    ledger = _append(empty_task_ledger(), "T01")
    checkpoint = write_checkpoint_bundle(tmp_path, ledger, current_lock="LOCK-A", human_artifacts_present=False)
    assert checkpoint["first_incomplete_task"] == "T02"
    for name in (
        "AIOS_FOREX_PACKET033_R5_TASK_LEDGER.json",
        "AIOS_FOREX_PACKET033_R5_PRODUCTIVE_TIME_LEDGER.json",
        "AIOS_FOREX_PACKET033_R5_CHECKPOINT_STATE.json",
    ):
        assert json.loads((tmp_path / name).read_text(encoding="utf-8"))


def test_authoritative_output_router_reconciles_canonical_inputs_in_isolation(tmp_path: Path):
    source_reports = Path(__file__).parents[2] / "Reports" / "forex_delivery"
    target_reports = tmp_path / "Reports" / "forex_delivery"
    target_reports.mkdir(parents=True)
    inputs = (
        "AIOS_FOREX_PACKET032_REPLICATION_QUEUE_V1_STATE.json",
        "AIOS_FOREX_ALL_TIMEFRAME_SCALPING_SEARCH_V1_STATE.json",
        "AIOS_FOREX_SCALPING_TECHNIQUE_INVENTORY_V1_STATE.json",
        "AIOS_FOREX_SCALPING_TECHNIQUE_FIDELITY_V1_STATE.json",
        "AIOS_FOREX_SCALPING_TIMEFRAME_COVERAGE_V1_STATE.json",
        "AIOS_FOREX_ALL_TIMEFRAME_SCALPING_HYPOTHESIS_LEDGER_V1.json",
        "AIOS_FOREX_SCALPING_HISTORY_HUMAN_HANDOFF_V1_STATE.json",
        "AIOS_FOREX_ATTACK_TO_FINISH_V11_STATE.json",
    )
    for name in inputs:
        shutil.copyfile(source_reports / name, target_reports / name)
    attack_path = target_reports / "AIOS_FOREX_ATTACK_TO_FINISH_V11_STATE.json"
    prior_attack = json.loads(attack_path.read_text(encoding="utf-8"))
    prior_attack["fixture_prior_evidence"] = {"status": "PASS"}
    attack_path.write_text(json.dumps(prior_attack), encoding="utf-8")

    ledger = empty_task_ledger()
    for task_id in [f"T{index:02d}" for index in range(1, 16)]:
        ledger = _append(ledger, task_id, seconds=240.0)

    state = write_authoritative_r5_outputs(tmp_path, ledger, current_lock="LOCK-A")
    persisted = json.loads((target_reports / "AIOS_FOREX_PACKET033_R5_STATE.json").read_text(encoding="utf-8"))
    unhashed = {key: value for key, value in persisted.items() if key != "state_hash"}
    assert persisted == state
    assert persisted["state_hash"] == sha256_text(stable(unhashed))
    assert persisted["checkpoint"]["one_hour_requirement_status"] == "SATISFIED"
    assert persisted["stop_proof"]["stop_allowed"] is True
    assert persisted["human_artifact_status"] == "ABSENT_WAITING_HUMAN"
    assert persisted["acquisition_plan"]["estimated_requests_by_granularity"]
    attack = json.loads((target_reports / "AIOS_FOREX_ATTACK_TO_FINISH_V11_STATE.json").read_text(encoding="utf-8"))
    assert attack["fixture_prior_evidence"]["status"] == "PASS"
    assert attack["remaining_authorized_work_count"] == 0
