from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from automation.forex_engine import forex_commercial_reference_strategy_library_v1 as library
from automation.forex_engine.forex_edge_validation_pipeline_v1 import (
    SCIENTIFIC_FINGERPRINT_FIELDS,
    candidate_fingerprint,
    first_wave_fingerprint_index,
    pretty_json,
    validate_trial_ledger,
)


def _base_runtime(tmp_path: Path) -> tuple[Path, Path]:
    source_ledger = Path(".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl")
    source_index = Path(".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_FINGERPRINT_INDEX_V1.json")
    ledger = tmp_path / "ledger.jsonl"
    index = tmp_path / "index.json"
    ledger.write_bytes(source_ledger.read_bytes())
    index.write_bytes(source_index.read_bytes())
    return ledger, index


def test_seven_references_have_complete_separated_fields() -> None:
    references = library.reference_strategies()
    assert len(references) == 7
    assert len({row["REFERENCE_STRATEGY_ID"] for row in references}) == 7
    for row in references:
        assert all(field in row for field in library.REQUIRED_REFERENCE_FIELDS)
        assert row["PUBLIC_REFERENCE_RULE"]
        assert row["AIOS_ADAPTATION"]
        assert row["AIOS_UNTESTED_PARAMETER"]
        assert row["AIOS_ADAPTATION_STATUS"] == "PROPOSED_UNSCORED_REFERENCE_ONLY"
        assert set(row["SCIENTIFIC_SPECIFICATION"]) == set(SCIENTIFIC_FINGERPRINT_FIELDS)


def test_public_sources_are_reference_only_and_do_not_import_code() -> None:
    sources = library.public_sources()
    assert len(sources) >= 11
    assert all(row["use"] == "HYPOTHESIS_OR_PROCESS_REFERENCE_ONLY" for row in sources)
    assert all(row["performance_claim_use"] == "NOT_ACCEPTED_AS_AIOS_EVIDENCE" for row in sources)
    assert not any(row["code_imported"] for row in sources)


def test_reference_fingerprint_ignores_name_but_not_science() -> None:
    spec = library.reference_strategies()[0]["SCIENTIFIC_SPECIFICATION"]
    renamed = dict(spec)
    renamed["candidate_id"] = "COSMETIC_NEW_NAME"
    assert candidate_fingerprint(spec) == candidate_fingerprint(renamed)
    changed = dict(spec)
    changed["formation_horizon"] = "DIFFERENT"
    assert candidate_fingerprint(spec) != candidate_fingerprint(changed)


def test_benchmark_selection_is_declared_and_outcome_free() -> None:
    references = library.reference_strategies()
    candidate = {"declared_reference_strategy_id": "FAST_TIME_SERIES_MOMENTUM", "horizon_class": "FAST", "profit": 999999}
    result = library.select_commercial_baseline(candidate, references)
    assert result == {"status": "PASS", "reference_strategy_id": "FAST_TIME_SERIES_MOMENTUM", "selection_used_outcomes": False}
    assert library.select_commercial_baseline({}, references)["status"] == "BLOCK"
    assert library.select_commercial_baseline({"declared_reference_strategy_id": "FAST_TIME_SERIES_MOMENTUM", "horizon_class": "SLOW"}, references)["status"] == "BLOCK"


def test_incremental_value_requires_positive_and_better_after_cost_result() -> None:
    assert library.incremental_value({"after_cost_expectancy": .02, "risk_normalized_return": .5}, {"after_cost_expectancy": .01, "risk_normalized_return": .3})["status"] == "PASS"
    assert library.incremental_value({"after_cost_expectancy": 0, "risk_normalized_return": .5}, {"after_cost_expectancy": -.01, "risk_normalized_return": .3})["status"] == "FAIL"
    assert library.incremental_value({"after_cost_expectancy": .02}, {"after_cost_expectancy": .01})["status"] == "BLOCK"


def test_semantic_parity_pass_fail_and_block() -> None:
    spec = library.reference_strategies()[0]["SCIENTIFIC_SPECIFICATION"]
    assert library.semantic_parity({stage: spec for stage in library.STAGES})["status"] == "PASS"
    altered = {stage: dict(spec) for stage in library.STAGES}
    altered["PAPER"]["entry_rule"] = "CHANGED"
    assert library.semantic_parity(altered)["status"] == "FAIL"
    assert library.semantic_parity({"RESEARCH": spec})["status"] == "BLOCK"


def test_build_appends_seven_unscored_and_preserves_scored_lower_bound(tmp_path: Path) -> None:
    ledger, index = _base_runtime(tmp_path)
    built = library.build_registry(ledger, index)
    added = built["registry"]["research_memory"]["new_proposed_unscored"]
    assert added in {0, 7}
    assert built["final_summary"]["proposed_unscored_count"] == built["prior_summary"]["proposed_unscored_count"] + added
    assert built["final_summary"]["scored_attempt_lower_bound"] == built["prior_summary"]["scored_attempt_lower_bound"] >= 1220
    reference_events = [row for row in built["ledger"] if row["event_id"].startswith("PKT041_REFERENCE_")]
    assert len(reference_events) == 7
    assert all(row["scored_trial_increment"] == 0 and row["status"] == "PROPOSED_UNSCORED" for row in reference_events)
    assert validate_trial_ledger(built["ledger"])["record_count"] == len(built["ledger"])
    safety = built["registry"]["safety"]
    assert safety["development_market_rows_opened"] == safety["validation_rows_opened"] == safety["holdout_rows_opened"] == 0
    assert safety["pkt_forex_039_cells_scored"] == 0


def test_build_is_idempotent_after_promotion_shape(tmp_path: Path) -> None:
    ledger, index = _base_runtime(tmp_path)
    first = library.build_registry(ledger, index)
    ledger.write_text("".join(library.canonical_json(row) + "\n" for row in first["ledger"]), encoding="ascii")
    index.write_text(pretty_json(first["fingerprint_index"]), encoding="ascii")
    second = library.build_registry(ledger, index)
    assert second["final_summary"]["proposed_unscored_count"] == first["final_summary"]["proposed_unscored_count"]
    assert second["registry"]["research_memory"]["new_proposed_unscored"] == 0
    assert all(row["disposition"] == "DUPLICATE_OF_EXISTING_PROPOSED_SPECIFICATION" for row in second["registry"]["reference_dispositions"])


def test_two_stage0_runs_are_byte_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger, index = _base_runtime(tmp_path)
    monkeypatch.setattr(library, "verify_frozen_sources", lambda _root: {"status": "PASS", "checked": 7, "mismatches": []})
    first = tmp_path / "run1"
    second = tmp_path / "run2"
    library.write_stage0(first, ledger, index, Path("."))
    library.write_stage0(second, ledger, index, Path("."))
    comparison = library.compare_stage0(first, second)
    assert comparison["status"] == "PASS"
    assert comparison["byte_identical"] is True
    assert comparison["first_aggregate_sha256"] == comparison["second_aggregate_sha256"]


def test_promotion_is_append_only_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger, index = _base_runtime(tmp_path)
    monkeypatch.setattr(library, "verify_frozen_sources", lambda _root: {"status": "PASS", "checked": 7, "mismatches": []})
    output = tmp_path / "run"
    library.write_stage0(output, ledger, index, Path("."))
    registry = tmp_path / "runtime" / "registry.json"
    first = library.promote_stage0(output, registry, ledger, index)
    assert first["status"] == "PASS"
    assert first["new_proposed_unscored"] in {0, 7}
    assert library.promote_stage0(output, registry, ledger, index)["status"] == "PASS"
    assert validate_trial_ledger(library.read_trial_ledger(ledger))["proposed_unscored_count"] >= 525


def test_fingerprint_index_prior_entries_are_preserved(tmp_path: Path) -> None:
    ledger, index = _base_runtime(tmp_path)
    prior = json.loads(index.read_text(encoding="ascii"))
    built = library.build_registry(ledger, index)
    final = built["fingerprint_index"]
    for entry in prior["entries"]:
        assert entry in final["entries"]


def test_contracts_fail_closed() -> None:
    benchmark = library.champion_challenger_contract()
    assert benchmark["missing_applicable_reference"] == "BLOCK"
    assert benchmark["selection_timing"] == "FROZEN_BEFORE_OUTCOME_ACCESS"
    assert benchmark["public_precedent_proves_edge"] is False
    parity = library.research_to_production_parity_contract()
    assert parity["undeclared_difference"] == "BLOCK"
    assert parity["paper_authorized"] is parity["live_authorized"] is False
    assert len(library.BIAS_CHECK_REQUIREMENTS) == 11


def test_source_and_runner_have_no_market_or_network_reader() -> None:
    paths = [Path(library.__file__), Path("scripts/forex_delivery/run_forex_commercial_reference_strategy_library_v1.py")]
    forbidden_imports = {"pandas", "requests", "urllib", "oandapyV20"}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(forbidden_imports)
        text = path.read_text(encoding="utf-8").lower()
        assert "development.parquet" not in text
        assert "validation.parquet" not in text
        assert "holdout.parquet" not in text


def test_current_runtime_index_is_the_frozen_72_cell_baseline() -> None:
    current = json.loads(Path(".aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_FINGERPRINT_INDEX_V1.json").read_text(encoding="ascii"))
    frozen = first_wave_fingerprint_index()
    assert {row["fingerprint"] for row in frozen["entries"]}.issubset({row["fingerprint"] for row in current["entries"]})


def test_artifact_validation_rejects_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger, index = _base_runtime(tmp_path)
    monkeypatch.setattr(library, "verify_frozen_sources", lambda _root: {"status": "PASS", "checked": 7, "mismatches": []})
    output = tmp_path / "run"
    library.write_stage0(output, ledger, index, Path("."))
    assert library.validate_stage0_artifacts(output)["status"] == "PASS"
    registry = output / "AIOS_FOREX_COMMERCIAL_REFERENCE_AND_BENCHMARK_REGISTRY_V1.json"
    registry.write_bytes(registry.read_bytes() + b" ")
    with pytest.raises(ValueError, match="STAGE0_ARTIFACT_HASH_MISMATCH"):
        library.validate_stage0_artifacts(output)
