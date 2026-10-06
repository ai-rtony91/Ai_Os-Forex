from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from automation.forex_engine.forex_cftc_positioning_acceleration_price_continuation_v1 import (
    baseline_gate,
    candidate_definitions,
    family_fingerprint,
    point_in_time_change_zscores,
    _score_for_mode,
)


def test_grid_is_exactly_twelve_and_distinct() -> None:
    rows = candidate_definitions()
    assert len(rows) == 12
    assert len({row["candidate_id"] for row in rows}) == 12
    assert {row["positioning_change_z_threshold"] for row in rows} == {0.5, 1.0}
    assert {row["price_confirmation_lookback_h1"] for row in rows} == {6, 12, 24}
    assert {row["maximum_holding_h1"] for row in rows} == {6, 12}
    assert len(family_fingerprint()) == 64


@pytest.mark.parametrize("expectancy", [-0.01, 0.0])
def test_nonpositive_expectancy_never_passes_baseline(expectancy: float) -> None:
    assert not baseline_gate(
        {"expectancy_r": expectancy},
        {"expectancy_r": -1.0},
        {"expectancy_r": 0.1},
        {"expectancy_r": -1.0},
        {"expectancy_r": -1.0},
    )


def test_information_strategy_must_beat_both_ablations() -> None:
    validation = {"expectancy_r": 0.02}
    assert not baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": 0.03}, {"expectancy_r": -1})
    assert not baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": -1}, {"expectancy_r": 0.03})
    assert baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": -1}, {"expectancy_r": -1})


def test_acceleration_direction_follows_change_not_level() -> None:
    scored = _score_for_mode("ACCELERATION", "EUR", "USD", 0.01, {"EUR": -2.0, "USD": 0.0}, {"EUR": 3.0, "USD": 0.0})
    assert scored == (-2.0, -1)
    level = _score_for_mode("POSITION_SIGN", "EUR", "USD", 0.01, {"EUR": -2.0, "USD": 0.0}, {"EUR": 3.0, "USD": 0.0})
    assert level == (3.0, 1)


def test_change_zscore_uses_only_available_rows() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(22):
        rows.append({"available": start + timedelta(days=7 * index), "normalized_net": index * index / 1000.0})
    decision = rows[-2]["available"]
    scores, sources = point_in_time_change_zscores({"EUR": rows}, decision)
    assert "EUR" in scores
    assert datetime.fromisoformat(sources["EUR"]) <= decision


def test_price_confirmation_rejects_opposite_direction_by_contract() -> None:
    score, side = _score_for_mode("ACCELERATION", "EUR", "USD", -0.01, {"EUR": 2.0, "USD": 0.0}, {})
    assert score == 2.0
    assert side * -0.01 < 0
