import inspect
import json
from urllib.error import URLError

import pytest

from automation.forex_engine.oanda_practice_candle_history_transport_v1 import (
    HOST, PATH, TIMEOUT_SECONDS, CandleTransportError, OandaPracticeCandleHistoryTransportV1,
)


def payload(extra=None):
    value = {"instrument": "EUR_USD", "granularity": "M5", "candles": [
        {"time": "2026-08-06T00:00:00Z", "complete": True, "volume": 1,
         "mid": {"o": "1", "h": "1", "l": "1", "c": "1"}}]}
    if extra:
        value.update(extra)
    return json.dumps(value).encode()


class Response:
    def __init__(self, body=None, url=None): self.body, self.url, self.reads = body or payload(), url, 0
    def geturl(self): return self.url or f"https://{HOST}{PATH}?granularity=M5&price=M&count=50"
    def read(self): self.reads += 1; return self.body


class Opener:
    def __init__(self, response=None, error=None): self.response, self.error, self.calls = response or Response(), error, []
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error: raise self.error
        return self.response


def test_exact_fixed_get_contract_and_sanitized_result():
    opener = Opener()
    transport = OandaPracticeCandleHistoryTransportV1("secret", opener=opener)
    result = transport.fetch_eurusd_m5_midpoint_candles()
    request, timeout = opener.calls[0]
    assert request.method == "GET" and request.full_url.startswith(f"https://{HOST}{PATH}?")
    assert timeout == TIMEOUT_SECONDS == 10
    assert set(result) == {"instrument", "granularity", "candles"}
    assert result is not opener.response.body


@pytest.mark.parametrize("name", ["environment", "host", "path", "account_id", "instrument", "granularity", "price", "count", "timeout"])
def test_constructor_cannot_represent_alternate_capabilities(name):
    assert name not in inspect.signature(OandaPracticeCandleHistoryTransportV1).parameters


@pytest.mark.parametrize("name", ["request", "request_json", "pricing", "account", "positions", "trades", "orders", "transactions"])
def test_no_generic_or_private_endpoint_methods(name):
    assert not hasattr(OandaPracticeCandleHistoryTransportV1, name)


def test_failure_consumes_budget_and_never_retries():
    opener = Opener(error=URLError("secret"))
    transport = OandaPracticeCandleHistoryTransportV1("secret", opener=opener)
    with pytest.raises(CandleTransportError, match="failed"): transport.fetch_eurusd_m5_midpoint_candles()
    with pytest.raises(CandleTransportError, match="consumed"): transport.fetch_eurusd_m5_midpoint_candles()
    assert len(opener.calls) == 1 and "secret" not in repr(transport)


@pytest.mark.parametrize("url", [
    "https://api-fxtrade.oanda.com/v3/instruments/EUR_USD/candles?granularity=M5&price=M&count=50",
    f"https://{HOST}/v3/accounts/x?granularity=M5&price=M&count=50",
    f"https://{HOST}{PATH}?granularity=M1&price=M&count=50",
])
def test_final_url_mismatch_rejected_before_body_read(url):
    response = Response(url=url); transport = OandaPracticeCandleHistoryTransportV1("x", opener=Opener(response))
    with pytest.raises(CandleTransportError, match="final_url"): transport.fetch_eurusd_m5_midpoint_candles()
    assert response.reads == 0


@pytest.mark.parametrize("body,reason", [
    (b'{"instrument":"EUR_USD","instrument":"EUR_USD","granularity":"M5","candles":[]}', "duplicate"),
    (b'{"instrument":"EUR_USD","granularity":"M5","candles":[],"x":NaN}', "non_finite"),
    (payload({"account": {}}), "schema"),
])
def test_unsafe_json_rejected(body, reason):
    transport = OandaPracticeCandleHistoryTransportV1("x", opener=Opener(Response(body=body)))
    with pytest.raises(CandleTransportError, match=reason): transport.fetch_eurusd_m5_midpoint_candles()
