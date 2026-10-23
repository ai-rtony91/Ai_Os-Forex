from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from automation.forex_engine.forex_cftc_participant_divergence_price_confirmation_v1 import (
    baseline_gate,
    build_participant_history,
    candidate_definitions,
    family_fingerprint,
    pair_signal,
    point_in_time_participant_scores,
)


def test_grid_is_exactly_twelve() -> None:
    rows = candidate_definitions()
    assert len(rows) == 12
    assert len({row["candidate_id"] for row in rows}) == 12
    assert {row["participant_divergence_threshold"] for row in rows} == {1.0, 1.5}
    assert {row["price_confirmation_lookback_h1"] for row in rows} == {6, 12, 24}
    assert {row["maximum_holding_h1"] for row in rows} == {6, 12}
    assert len(family_fingerprint()) == 64


@pytest.mark.parametrize("expectancy", [-0.01, 0.0])
def test_nonpositive_expectancy_never_passes_baseline(expectancy: float) -> None:
    assert not baseline_gate({"expectancy_r": expectancy}, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": -1}, {"expectancy_r": -1}, {"expectancy_r": -1})


def test_candidate_must_beat_every_ablation() -> None:
    validation = {"expectancy_r": 0.02}
    assert not baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": 0.03}, {"expectancy_r": -1}, {"expectancy_r": -1})
    assert not baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": -1}, {"expectancy_r": 0.03}, {"expectancy_r": -1})
    assert not baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": -1}, {"expectancy_r": -1}, {"expectancy_r": 0.03})
    assert baseline_gate(validation, {"expectancy_r": -1}, {"expectancy_r": 0.1}, {"expectancy_r": -1}, {"expectancy_r": -1}, {"expectancy_r": -1})


def test_divergence_requires_opposed_non_usd_participants() -> None:
    aligned = {"EUR": {"asset": 2.0, "leveraged": 1.0, "divergence": 1.0, "opposed": 0.0}, "USD": {"asset": 0.0, "leveraged": 0.0, "divergence": 0.0, "opposed": 1.0}}
    assert pair_signal("DIVERGENCE", "EUR", "USD", 0.01, aligned) is None
    opposed = {"EUR": {"asset": 2.0, "leveraged": -1.0, "divergence": 3.0, "opposed": 1.0}, "USD": aligned["USD"]}
    assert pair_signal("DIVERGENCE", "EUR", "USD", 0.01, opposed) == (3.0, 1)


def test_participant_scores_use_only_published_rows() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [{"available": start + timedelta(days=7 * index), "asset_manager_net": index * index / 1000, "leveraged_net": -index / 100} for index in range(21)]
    decision = rows[-2]["available"]
    scores, sources = point_in_time_participant_scores({"EUR": rows}, decision)
    assert "EUR" in scores
    assert datetime.fromisoformat(sources["EUR"]) <= decision


def test_history_preserves_both_participant_categories() -> None:
    row = {"coverage": "EURO FX - CHICAGO MERCANTILE EXCHANGE", "available_to_strategy_utc": "2024-01-05T21:30:00Z", "open_interest": 1000, "asset_manager_long": 300, "asset_manager_short": 100, "leveraged_long": 50, "leveraged_short": 250}
    history = build_participant_history([row])
    assert history["EUR"][0]["asset_manager_net"] == pytest.approx(0.2)
    assert history["EUR"][0]["leveraged_net"] == pytest.approx(-0.2)
