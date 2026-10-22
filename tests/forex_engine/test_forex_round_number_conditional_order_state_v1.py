from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone

import pytest

from automation.forex_engine import forex_round_number_conditional_order_state_v1 as research


def bar(timestamp: datetime, open_: float, high: float, low: float, close: float, spread: float = 0.0002) -> dict:
    half = spread / 2
    return {
        "timestamp": research.timestamp_text(timestamp),
        "instrument": "EUR_USD",
        "complete": True,
        "mid": {"o": open_, "h": high, "l": low, "c": close},
        "ask": {"o": open_ + half, "h": high + half, "l": low + half, "c": close + half},
        "bid": {"o": open_ - half, "h": high - half, "l": low - half, "c": close - half},
    }


def test_exact_ten_candidates_cover_two_branches_and_five_directions() -> None:
    definitions = research.candidate_definitions()
    assert len(definitions) == 10
    assert {row["branch"] for row in definitions} == set(research.BRANCH_HOLDS)
    assert {row["direction_variant"] for row in definitions} == set(research.DIRECTIONS)
    assert len({row["candidate_fingerprint"] for row in definitions}) == 10


def test_round_approach_detects_bounce_side_without_touching() -> None:
    row = bar(datetime(2024, 2, 1, tzinfo=timezone.utc), 1.1002, 1.1003, 1.10005, 1.10015)
    events = research.signal_events(1.1003, row, "EUR_USD", "ROUND_00_50")
    assert ("APPROACH_00_50_REVERSAL", "LONG", pytest.approx(1.1)) in events


def test_round_cross_requires_completed_close_beyond_level() -> None:
    crossed = bar(datetime(2024, 2, 1, tzinfo=timezone.utc), 1.0998, 1.1003, 1.0997, 1.1002)
    touched_not_crossed = bar(datetime(2024, 2, 1, tzinfo=timezone.utc), 1.0998, 1.1002, 1.0997, 1.1000)
    assert any(item[:2] == ("COMPLETED_CROSS_00_50_CONTINUATION", "LONG") for item in research.signal_events(1.0998, crossed, "EUR_USD", "ROUND_00_50"))
    assert not any(item[0] == "COMPLETED_CROSS_00_50_CONTINUATION" for item in research.signal_events(1.0998, touched_not_crossed, "EUR_USD", "ROUND_00_50"))


def test_shifted_control_uses_25_pip_offset() -> None:
    lower, upper = research.grid_neighbors(1.1026, 0.005, 0.0025)
    assert lower == pytest.approx(1.1025)
    assert upper == pytest.approx(1.1075)


def test_direction_variants_are_exact_pairs() -> None:
    event = {"original_direction": "LONG"}
    assert research.direction_for_variant(event, "ORIGINAL_LONG") == "LONG"
    assert research.direction_for_variant(event, "EXACT_REVERSED_SHORT") == "SHORT"
    assert research.direction_for_variant(event, "ORIGINAL_SHORT") is None
    assert research.direction_for_variant(event, "EXACT_REVERSED_LONG") is None
    assert research.direction_for_variant(event, "SYMMETRIC_BIDIRECTIONAL") == "LONG"


def test_next_bar_execution_and_cost_ordering() -> None:
    start = datetime(2024, 2, 1, 10, 0, tzinfo=timezone.utc)
    bars = [
        bar(start, 1.1000, 1.1002, 1.0998, 1.1001),
        bar(start + timedelta(minutes=5), 1.1001, 1.1005, 1.1000, 1.1004),
        bar(start + timedelta(minutes=10), 1.1004, 1.1007, 1.1003, 1.1006),
    ]
    gross = research.simulate_path("EUR_USD", bars, 0, 2, "LONG", 0.001, "gross")
    base = research.simulate_path("EUR_USD", bars, 0, 2, "LONG", 0.001, "base")
    stress = research.simulate_path("EUR_USD", bars, 0, 2, "LONG", 0.001, "stress")
    assert bars[1]["timestamp"] == "2024-02-01T10:05:00Z"
    assert gross[5] > base[5] > stress[5]


def test_no_trade_baseline_rejects_zero_and_negative_expectancy() -> None:
    other = {"expectancy_r": -1.0}
    for expectancy in (0.0, -0.000001):
        base = {"expectancy_r": expectancy}
        assert research.baseline_gate(base, other, other, other) is False


def test_metric_gates_are_strictly_after_cost() -> None:
    rows = [
        {"entry_timestamp": f"2024-01-{index + 1:02d}T00:00:00Z", "instrument": "EUR_USD", "direction": "LONG", "fold": index % 6, "net_result_r": value}
        for index, value in enumerate([1.0, -0.5, 1.0, -0.5, 1.0, -0.5])
    ]
    result = research.metrics(rows)
    assert result["trade_count"] == 6
    assert result["expectancy_r"] == pytest.approx(0.25)
    assert result["profit_factor"] == pytest.approx(2.0)


def test_deterministic_gzip_journal_preserves_rows() -> None:
    rows = [{"candidate_id": "A", "entry_timestamp": "2024-01-01T00:00:00Z", "instrument": "EUR_USD", "event_id": "E"}]
    first = research.journal_bytes(rows)
    second = research.journal_bytes(rows)
    assert first == second
    assert json.loads(gzip.decompress(first).decode("utf-8")) == rows[0]


def test_fold_embargo_and_rollover_are_fail_closed() -> None:
    boundary = research.fold_boundaries()[1]
    assert research.in_embargo(boundary)
    assert research.in_embargo(research.DEV_END - timedelta(minutes=5))
    assert research.fold_index(research.DEV_END) == -1
    assert research.interval_touches_rollover(
        datetime(2024, 1, 2, 21, 40, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 21, 50, tzinfo=timezone.utc),
    )


def test_contract_keeps_holdout_and_live_actions_out() -> None:
    assert research.DEV_END < research.HOLDOUT_START
    assert research.CUMULATIVE_ATTEMPT_LOWER_BOUND == research.PRIOR_ATTEMPT_LOWER_BOUND + 10
    assert research.NO_TRADE_EXPECTANCY_R == 0.0
