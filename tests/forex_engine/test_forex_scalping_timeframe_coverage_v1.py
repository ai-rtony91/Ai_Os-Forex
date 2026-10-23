from __future__ import annotations

from automation.forex_engine.forex_scalping_timeframe_coverage_v1 import REQUESTED, classify_timeframes


def test_requested_timeframe_set_contains_expansion():
    assert "S1" in REQUESTED
    assert "S45" in REQUESTED
    assert "M2" in REQUESTED
    assert "H2" in REQUESTED
    assert "MO6" in REQUESTED


def test_s1_and_s45_are_not_fabricated():
    matrix = classify_timeframes()
    assert matrix["S1"]["native_or_derived_status"] == "UNAVAILABLE_WITH_CURRENT_EVIDENCE"
    assert matrix["S45"]["native_or_derived_status"] == "UNAVAILABLE_WITH_CURRENT_EVIDENCE"
    assert matrix["MO6"]["native_or_derived_status"] == "DERIVED_FROM_VALID_LOWER_TIMEFRAME"
