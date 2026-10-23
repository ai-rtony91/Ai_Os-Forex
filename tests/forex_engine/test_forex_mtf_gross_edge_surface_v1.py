from __future__ import annotations

from automation.forex_engine.forex_mtf_gross_edge_surface_v1 import (
    MAX_FIRST_PASS_HYPOTHESES,
    hypothesis_grid,
    resample,
    score_records,
)


def test_hypothesis_grid_is_bounded_and_contains_required_ablations():
    grid = hypothesis_grid()
    assert len(grid) <= MAX_FIRST_PASS_HYPOTHESES
    combos = {item["combo"] for item in grid}
    assert {"ST", "MACD", "ADX", "ST+MACD", "ST+ADX", "MACD+ADX", "ST+MACD+ADX"}.issubset(combos)
    assert len({item["hypothesis_id"] for item in grid}) == len(grid)


def test_resample_uses_completed_source_rows_without_synthesizing_missing_bars():
    rows = []
    for index in range(6):
        rows.append(
            {
                "time": __import__("datetime").datetime(2026, 1, 1, 0, index * 5, tzinfo=__import__("datetime").timezone.utc),
                "timestamp": f"2026-01-01T00:{index * 5:02d}:00Z",
                "open": 1.0 + index,
                "high": 2.0 + index,
                "low": 0.5 + index,
                "close": 1.5 + index,
                "bid_close": 1.4 + index,
                "ask_close": 1.6 + index,
                "spread": 0.2,
                "complete": True,
            }
        )
    out = resample(rows, 15)
    assert len(out) == 2
    assert out[0]["open"] == rows[0]["open"]
    assert out[0]["close"] == rows[2]["close"]
    assert out[1]["close"] == rows[5]["close"]


def test_score_records_reports_fold_and_breadth_controls():
    records = [
        {"r": 0.2, "instrument": f"P{i % 4}", "year": 2020 + (i % 4), "event_index": i, "spread_r": 0.01, "mfe_r": 0.3, "mae_r": 0.1}
        for i in range(80)
    ]
    metrics = score_records(records)
    assert metrics["trades"] == 80
    assert metrics["gross_expectancy"] > 0
    assert metrics["pair_count"] == 4
    assert metrics["positive_fold_share"] == 1
