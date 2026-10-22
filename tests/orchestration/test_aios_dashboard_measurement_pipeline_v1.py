import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[2] / "automation/orchestration/aios_dashboard_measurement_pipeline_v1.py"
SPEC = importlib.util.spec_from_file_location("measurement_pipeline", MODULE_PATH)
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


def test_acquisition_fingerprints_canonical_sources():
    result = pipeline.acquire_sources()
    assert result["phase"] == "A"
    assert len(result["sources"]) >= 6
    assert all(len(source.get("fingerprint_sha256", "")) == 64 for source in result["sources"] if source["parse_state"] == "VALID")


def test_source_rejects_duplicate_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    source = tmp_path / "duplicate.json"
    source.write_text('{"id": 1, "id": 2}')
    with pytest.raises(pipeline.DuplicateKeyError):
        pipeline.load_json_strict(source)


def test_source_rejects_non_finite_values(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    source = tmp_path / "bad.json"
    source.write_text('{"weight": NaN}')
    with pytest.raises(ValueError):
        pipeline.load_json_strict(source)


def test_normalization_measurement_completion_is_dimensioned():
    a = pipeline.acquire_sources()
    result = pipeline.normalize_requirements([
        {"id": "one", "weight": 1, "status": "VERIFIED_COMPLETE"},
        {"id": "two", "weight": 1, "status": "IMPLEMENTED_UNVALIDATED"},
    ], a)
    assert result["dimensions"]["engineering_implementation_pct"] == 100
    assert result["dimensions"]["validation_pct"] == 50


def test_denominator_is_blocked_by_duplicate_ids():
    a = pipeline.acquire_sources()
    result = pipeline.normalize_requirements([
        {"id": "same", "weight": 1, "status": "VERIFIED_COMPLETE"},
        {"id": "same", "weight": 1, "status": "VERIFIED_COMPLETE"},
    ], a)
    assert result["overall_status"] == "PARTIAL_INVENTORY"
    assert result["dimensions"]["overall_verified_completion_pct"] is None


def test_reconciliation_preserves_hash_chain():
    a = pipeline.acquire_sources()
    b = pipeline.normalize_requirements([], a)
    c = pipeline.reconcile(a, b)
    assert c["a_receipt_sha256"] == a["receipt_sha256"]
    assert c["b_receipt_sha256"] == b["receipt_sha256"]


def test_lock_concurrent_runner_is_busy(tmp_path):
    lock = tmp_path / "pipeline.lock"
    first = pipeline.acquire_lock(lock)
    assert first is not None
    assert pipeline.acquire_lock(lock) is None
    pipeline.release_lock(first, lock)


def test_atomic_write_preserves_valid_json(tmp_path):
    target = tmp_path / "projection.json"
    pipeline.atomic_json(target, {"state": "valid"})
    assert json.loads(target.read_text()) == {"state": "valid"}
