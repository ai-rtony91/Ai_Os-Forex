from __future__ import annotations

from automation.forex_engine.forex_packet032_replication_queue_v1 import priority


def test_macd_m30_is_priority_one():
    row = {"indicator_family": "MACD", "context_timeframe": "M30", "metrics": {"gross_expectancy": 1, "gross_pf": 2}}
    assert priority(row) == 1


def test_non_positive_is_not_priority_two():
    row = {"indicator_family": "ADX", "context_timeframe": "H1", "metrics": {"gross_expectancy": -1, "gross_pf": 0.8}}
    assert priority(row) == 9
