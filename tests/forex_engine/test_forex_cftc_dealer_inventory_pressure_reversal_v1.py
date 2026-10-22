from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from automation.forex_engine.forex_cftc_dealer_inventory_pressure_reversal_v1 import (
    baseline_gate,
    build_dealer_history,
    candidate_definitions,
    family_descriptor,
    family_fingerprint,
    pair_signal,
    point_in_time_scores,
)


def test_grid_is_exactly_twelve() -> None:
    rows = candidate_definitions()
    assert len(rows) == 12
    assert len({row["candidate_id"] for row in rows}) == 12
    assert {row["dealer_z_threshold"] for row in rows} == {0.75, 1.25}
    assert {row["price_confirmation_lookback_h1"] for row in rows} == {6, 12, 24}
    assert {row["maximum_holding_h1"] for row in rows} == {6, 12}
    assert len(family_fingerprint()) == 64


def test_category_is_not_mislabelled() -> None:
    descriptor = family_descriptor()
    assert descriptor["category"] == "CFTC_DEALER_INTERMEDIARY_NOT_COMMERCIAL_HEDGER_OR_CUSTOMER_FLOW"


@pytest.mark.parametrize("expectancy", [-0.01, 0.0])
def test_nonpositive_expectancy_never_passes_baseline(expectancy: float) -> None:
    assert not baseline_gate({"expectancy_r": expectancy}, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": -1}, {"expectancy_r": -1}, {"expectancy_r": -1})


def test_candidate_must_beat_every_ablation() -> None:
    validation = {"expectancy_r": 0.02}
    assert not baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": 0.03}, {"expectancy_r": -1}, {"expectancy_r": -1})
    assert not baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": -1}, {"expectancy_r": 0.03}, {"expectancy_r": -1})
    assert not baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": -1}, {"expectancy_r": -1}, {"expectancy_r": 0.03})
    assert baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": -1}, {"expectancy_r": -1}, {"expectancy_r": -1})


def test_dealer_signal_is_opposite_inventory() -> None:
    scores = {"EUR": {"dealer": 2.0, "leveraged": -1.0}, "USD": {"dealer": 0.0, "leveraged": 0.0}}
    assert pair_signal("DEALER_CONFIRMED", "EUR", "USD", -0.01, scores) == (2.0, -1)
    assert pair_signal("LEVERAGED_CROWDING", "EUR", "USD", 0.01, scores) == (-1.0, 1)


def test_scores_use_only_available_reports() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [{"available": start + timedelta(days=7 * index), "dealer_net": index * index / 1000, "leveraged_net": -index / 100} for index in range(21)]
    decision = rows[-2]["available"]
    scores, sources = point_in_time_scores({"EUR": rows}, decision)
    assert "EUR" in scores
    assert datetime.fromisoformat(sources["EUR"]) <= decision


def test_history_preserves_dealer_and_leveraged_categories() -> None:
    row = {"coverage": "EURO FX - CHICAGO MERCANTILE EXCHANGE", "available_to_strategy_utc": "2024-01-05T21:30:00Z", "open_interest": 1000, "dealer_long": 300, "dealer_short": 100, "leveraged_long": 50, "leveraged_short": 250}
    history = build_dealer_history([row])
    assert history["EUR"][0]["dealer_net"] == pytest.approx(0.2)
    assert history["EUR"][0]["leveraged_net"] == pytest.approx(-0.2)
