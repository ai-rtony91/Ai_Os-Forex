import json
from datetime import datetime, timedelta, timezone

import pytest

from automation.forex_engine.oanda_practice_candle_history_transport_v1 import OandaPracticeCandleHistoryTransportV1
from scripts.forex_delivery.run_forex_p1_eurusd_m5_capture_signal_loop_v1 import HISTORY_PATH, SIGNAL_PATH, run_cycle, run_loop

NOW = datetime(2026, 8, 6, 5, 30, tzinfo=timezone.utc)


class Response:
    def geturl(self): return "https://api-fxpractice.oanda.com/v3/instruments/EUR_USD/candles?granularity=M5&price=M&count=50"
    def read(self):
        candles = []
        for index in range(3):
            at = NOW - timedelta(minutes=15-index*5)
            candles.append({"time": at.isoformat().replace("+00:00", "Z"), "complete": True, "volume": 10,
                "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.1"}})
        return json.dumps({"instrument": "EUR_USD", "granularity": "M5", "candles": candles}).encode()


class Opener:
    def __init__(self): self.calls = 0
    def open(self, request, timeout): self.calls += 1; return Response()


def client(): return OandaPracticeCandleHistoryTransportV1("test", opener=Opener())


def test_cycle_captures_then_evaluates_using_canonical_paths():
    writes = []
    result = run_cycle(client(), now=NOW, write=lambda path, text: writes.append((path, text)))
    assert [item[0] for item in writes] == [HISTORY_PATH, SIGNAL_PATH]
    assert result["status"] == "CAPTURED_AND_EVALUATED"
    assert result["broker_write_performed"] is False and result["order_submission_allowed"] is False


def test_exactly_one_cycle_without_sleep_or_retry():
    calls = []
    assert len(run_loop(client(), cycles=1, cycle=lambda _client: calls.append(1) or {})) == 1
    assert calls == [1]


@pytest.mark.parametrize("cycles", [0, 2, 3, -1, True])
def test_other_cycle_counts_rejected(cycles):
    with pytest.raises(ValueError, match="exactly_one"): run_loop(client(), cycles=cycles)
