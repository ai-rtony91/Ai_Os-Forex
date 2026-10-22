from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from automation.forex_engine.oanda_read_only_client import (  # noqa: E402
    OandaReadOnlyClient,
    PRACTICE_BASE_URL,
    ReadOnlyMethodRejected,
)
from automation.forex_engine.read_only_live_data_sanitizer import (  # noqa: E402
    sanitize_account_summary,
    sanitize_tree,
    source_fields,
)


def test_oanda_client_rejects_any_method_other_than_get():
    client = OandaReadOnlyClient(
        api_token="runtime-token",
        account_id="101-222-333333-001",
        opener=lambda *_args, **_kwargs: None,
    )

    for method in ("POST", "PUT", "PATCH", "DELETE", "post"):
        with pytest.raises(ReadOnlyMethodRejected):
            client.request_json(method, "/v3/accounts/ignored")


def test_oanda_client_repr_masks_runtime_values():
    client = OandaReadOnlyClient(
        api_token="runtime-token",
        account_id="101-222-333333-001",
    )

    text = repr(client)
    assert "runtime-token" not in text
    assert "101-222-333333-001" not in text
    assert "MASKED" in text


def test_candles_uses_get_instrument_path_and_bounded_query():
    observed = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self): return b'{"candles": []}'

    def opener(request, **_kwargs):
        observed["url"] = request.full_url
        observed["method"] = request.get_method()
        return Response()

    client = OandaReadOnlyClient(api_token="runtime-token", account_id="private", opener=opener)
    assert client.candles("EUR_USD", granularity="M5", count=50) == {"candles": []}
    assert observed["method"] == "GET"
    assert observed["url"].startswith(PRACTICE_BASE_URL + "/v3/instruments/EUR_USD/candles?")
    assert "granularity=M5" in observed["url"] and "count=50" in observed["url"] and "price=M" in observed["url"]
    assert "private" not in observed["url"]


def test_observation_candles_uses_get_and_accepts_501():
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"candles": []}'

    def opener(request, **_kwargs):
        observed["url"] = request.full_url
        observed["method"] = request.get_method()
        return Response()

    client = OandaReadOnlyClient(api_token="runtime-token", account_id="private", opener=opener)
    assert client.observation_candles("EUR_USD", granularity="M5", count=501) == {"candles": []}
    assert observed["method"] == "GET"
    assert observed["url"].startswith(PRACTICE_BASE_URL + "/v3/instruments/EUR_USD/candles?")
    assert "granularity=M5" in observed["url"] and "count=501" in observed["url"] and "price=M" in observed["url"]
    assert "private" not in observed["url"]


def test_observation_candles_accepts_mba_price_component():
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"candles": []}'

    def opener(request, **_kwargs):
        observed["url"] = request.full_url
        return Response()

    client = OandaReadOnlyClient(api_token="runtime-token", account_id="private", opener=opener)
    assert client.observation_candles("EUR_USD", granularity="M5", count=501, price="MBA") == {"candles": []}
    assert "price=MBA" in observed["url"]


@pytest.mark.parametrize("kwargs", [
    {"instrument": "GBP_USD", "granularity": "M5", "count": 50},
    {"instrument": "EUR_USD", "granularity": "M1", "count": 50},
    {"instrument": "EUR_USD", "granularity": "M5", "count": 2},
    {"instrument": "EUR_USD", "granularity": "M5", "count": 501},
])
def test_candles_rejects_unsupported_requests(kwargs):
    client = OandaReadOnlyClient(api_token="runtime-token", account_id="private")
    with pytest.raises(ValueError):
        client.candles(**kwargs)


@pytest.mark.parametrize("kwargs", [
    {"instrument": "GBPUSD", "granularity": "M5", "count": 50},
    {"instrument": "EUR_USD", "granularity": "M4", "count": 50},
    {"instrument": "EUR_USD", "granularity": "M5", "count": 4},
    {"instrument": "EUR_USD", "granularity": "M5", "count": 502},
    {"instrument": "EUR_USD", "granularity": "M5", "count": 50, "price": "X"},
])
def test_observation_candles_rejects_unsupported_requests(kwargs):
    client = OandaReadOnlyClient(api_token="runtime-token", account_id="private")
    with pytest.raises(ValueError):
        client.observation_candles(**kwargs)


def test_legacy_candles_still_rejects_501():
    client = OandaReadOnlyClient(api_token="runtime-token", account_id="private")
    with pytest.raises(ValueError):
        client.candles("EUR_USD", granularity="M5", count=501)


def test_oanda_client_has_no_write_methods():
    client = OandaReadOnlyClient(api_token="runtime-token", account_id="private")
    for method_name in ("post", "put", "patch", "delete"):
        assert not hasattr(client, method_name)


def test_sanitizer_masks_account_and_strips_order_transaction_identifiers():
    raw = {
        "account": {
            "id": "101-222-333333-001",
            "accountID": "101-222-333333-001",
            "orders": [
                {
                    "orderID": "123",
                    "transactionID": "456",
                    "instrument": "EUR_USD",
                }
            ],
            "authorization": "Bearer SHOULD_NOT_APPEAR",
        }
    }

    sanitized = sanitize_tree(raw)
    text = str(sanitized)

    assert "101-222-333333-001" not in text
    assert "SHOULD_NOT_APPEAR" not in text
    assert "orderID" not in text
    assert "transactionID" not in text
    assert sanitized["account"]["accountID"] == "MASKED_ACCOUNT_ID"


def test_sanitize_account_summary_returns_safe_readiness_fields():
    context = source_fields(
        source_type="broker-live-read-only",
        source_label="OANDA_READ_ONLY_SANITIZED",
        freshness_utc="2026-06-19T12:00:00Z",
        stale_status="VALID",
        block_reason="read-only",
    )

    summary = sanitize_account_summary(
        {
            "account": {
                "id": "101-222-333333-001",
                "openPositionCount": 2,
                "pendingOrderCount": 1,
                "pl": "3.21",
                "unrealizedPL": "-0.10",
                "marginAvailable": "500.00",
            }
        },
        broker_mode="practice",
        freshness_utc="2026-06-19T12:00:00Z",
        source_context=context,
    )

    assert summary["account_reachable"] is True
    assert summary["open_positions_reconciled"] is True
    assert summary["pending_orders_reconciled"] is True
    assert summary["daily_pl_available"] is True
    assert summary["margin_risk_available"] is True
    assert "101-222-333333-001" not in str(summary)
