from __future__ import annotations

import json

from automation.forex_engine.forex_mtf_indicator_coverage_v1 import TIMEFRAMES, coverage_matrix, resolve_m5_artifact


def test_timeframe_universe_is_canonical_packet032_set():
    assert TIMEFRAMES == ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"]


def test_resolve_m5_artifact_anchors_relative_paths_to_frozen_root():
    resolved = resolve_m5_artifact("partitions/EUR_USD/example.jsonl.gz")
    assert ".aios" in str(resolved)
    assert "forex_m5_immutable_corpus_v2" in str(resolved)


def test_coverage_matrix_reports_every_timeframe_without_raw_artifacts():
    matrix = coverage_matrix()
    assert set(TIMEFRAMES).issubset(matrix)
    assert matrix["M1"]["eligible_for_development"] is False
    assert matrix["M5"]["source_artifact"] == "FROZEN_M5_CORPUS_V2"
    serialized = json.dumps(matrix)
    assert "token" not in serialized.lower()
    assert "account" not in serialized.lower()
