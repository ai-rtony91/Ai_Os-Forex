from datetime import datetime, timedelta, timezone

import pytest

from scripts.forex_delivery.run_forex_p1_eurusd_m5_capture_signal_loop_v1 import (
    HISTORY_PATH, INTERVAL_SECONDS, SIGNAL_PATH, run_cycle, run_loop,
)
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient

NOW = datetime(2026, 8, 6, 5, 30, tzinfo=timezone.utc)


def payload():
    candles = []
    for index in range(3):
        observed = NOW - timedelta(minutes=15 - index * 5)
        close = 1.1000 + index * 0.0007
        candles.append({
            "time": observed.isoformat().replace("+00:00", "Z"), "complete": True,
            "volume": 100 + index,
            "mid": {"o": str(close - 0.0002), "h": str(close + 0.0005),
                    "l": str(close - 0.0005), "c": str(close)},
        })
    return {"instrument": "EUR_USD", "granularity": "M5", "candles": candles}


def client(response=None, *, environment="practice"):
    value = OandaReadOnlyClient(api_token="test", account_id="", environment=environment)
    value.candles = lambda *_args, **_kwargs: response or payload()
    return value


def test_cycle_captures_then_evaluates_using_only_canonical_runtime_paths():
    writes = []
    result = run_cycle(client(), now=NOW, write=lambda path, text: writes.append((path, text)))
    assert [path for path, _text in writes] == [HISTORY_PATH, SIGNAL_PATH]
    assert result["status"] == "CAPTURED_AND_EVALUATED"
    assert result["candle_count"] == 3
    assert result["read_only"] is True
    assert result["broker_write_performed"] is False
    assert result["order_submission_allowed"] is False
    assert '"schema": "AIOS_P1_EURUSD_MARKET_HISTORY.v1"' in writes[0][1]
    assert '"schema": "AIOS_P1_EURUSD_SIGNAL_DECISION.v1"' in writes[1][1]


def test_loop_waits_exactly_five_minutes_between_cycles():
    sleeps = []
    calls = []
    results = run_loop(client(), cycles=3, sleep=sleeps.append,
                       cycle=lambda _client: calls.append(True) or {"status": "ok"})
    assert len(results) == 3
    assert len(calls) == 3
    assert sleeps == [INTERVAL_SECONDS, INTERVAL_SECONDS] == [300, 300]


@pytest.mark.parametrize("cycles", [0, -1, True])
def test_loop_requires_bounded_positive_cycle_count(cycles):
    with pytest.raises(ValueError, match="positive_cycle_count"):
        run_loop(client(), cycles=cycles)


def test_loop_rejects_non_practice_transport():
    with pytest.raises(ValueError, match="practice_environment"):
        run_cycle(client(environment="live"), now=NOW, write=lambda *_args: None)


def test_cycle_fails_closed_without_partial_writes():
    writes = []
    stale = payload()
    for candle in stale["candles"]:
        candle["time"] = "2020-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        run_cycle(client(stale), now=NOW, write=lambda *args: writes.append(args))
    assert writes == []
