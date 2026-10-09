"""Synthetic metadata and rejecting IO sentinels; no real price data or scoring."""
from copy import deepcopy
import json

import pytest

from automation.forex_engine import forex_mtf_gross_edge_surface_v1 as surface

BLOCKER = "INDEPENDENT_CRITICAL_GAP_CLASSIFICATION_NOT_VERIFIED"


@pytest.fixture
def metadata(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    value = {
        "status": "EXTERNAL_DATA_BLOCKED",
        "eligible_pairs": ["SYNTHETIC_PAIR"],
        "artifacts": [{"instrument": "SYNTHETIC_PAIR", "path": "SYNTHETIC_ONLY.gz"}],
    }
    path.write_text(json.dumps(value))
    monkeypatch.setattr(surface, "M5_STATE", path)
    monkeypatch.setattr(surface, "ROW_CACHE", {})

    def forbidden(*args, **kwargs):
        raise AssertionError("price_io_coverage_or_scoring_reached_before_admission")

    monkeypatch.setattr(surface, "resolve_m5_artifact", forbidden)
    monkeypatch.setattr(surface.gzip, "open", forbidden)
    monkeypatch.setattr(surface, "coverage_matrix", forbidden)
    monkeypatch.setattr(surface, "evaluate_hypothesis", forbidden)
    monkeypatch.setattr(surface.p27, "load_h1", forbidden)
    return path, value


@pytest.mark.parametrize("case", ["retained_pairs", "artifact_fallback", "self_asserted_valid", "missing_manifest"])
def test_pair_scope_rejects_unverified_metadata(metadata, case):
    path, value = metadata
    if case == "artifact_fallback":
        value.pop("eligible_pairs")
    if case == "self_asserted_valid":
        value.update(status="FROZEN_VALID", critical_gap_classification_verified=True,
                     unclassified_critical_gaps=0, proof_sha256="a" * 64)
    if case == "missing_manifest":
        path.unlink()
    else:
        path.write_text(json.dumps(value))
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(ValueError, match="^" + BLOCKER + "$"):
        surface.pair_universe()
    assert (path.read_bytes() if path.exists() else None) == before


@pytest.mark.parametrize("cached", [False, True])
def test_direct_m5_loader_denies_before_artifact_or_cached_rows(metadata, cached):
    if cached:
        surface.ROW_CACHE[("M5_RAW", "SYNTHETIC_PAIR")] = [{"synthetic_cache_sentinel": True}]
    before = deepcopy(surface.ROW_CACHE)
    with pytest.raises(ValueError, match="^" + BLOCKER + "$"):
        surface.load_m5_rows("SYNTHETIC_PAIR")
    assert surface.ROW_CACHE == before


@pytest.mark.parametrize("timeframe", ["M5", "M15", "M30"])
@pytest.mark.parametrize("cached", [False, True])
def test_candle_entry_denies_unverified_native_and_derived_cache(metadata, timeframe, cached):
    if cached:
        surface.ROW_CACHE[(timeframe, "SYNTHETIC_PAIR")] = [{"synthetic_cache_sentinel": True}]
    before = deepcopy(surface.ROW_CACHE)
    with pytest.raises(ValueError, match="^" + BLOCKER + "$"):
        surface.candles_for("SYNTHETIC_PAIR", timeframe)
    assert surface.ROW_CACHE == before


def test_surface_entry_denies_before_directory_coverage_prices_or_scoring(metadata, tmp_path, monkeypatch):
    root = tmp_path / "not_created"
    monkeypatch.setattr(surface, "ROOT", root)
    with pytest.raises(ValueError, match="^" + BLOCKER + "$"):
        surface.run_surface()
    assert not root.exists()
