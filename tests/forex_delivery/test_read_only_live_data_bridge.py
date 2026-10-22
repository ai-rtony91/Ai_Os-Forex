from pathlib import Path
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from forex_delivery.read_only_live_data_bridge import (  # noqa: E402
    build_read_only_live_data_bridge_read_model,
    build_sanitized_report,
)


class FakeOandaClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def fetch_read_only_snapshot(self, *, instruments):
        assert instruments == ("EUR_USD",)
        return {
            "account_summary": {
                "account": {
                    "id": "101-222-333333-001",
                    "openPositionCount": 1,
                    "pendingOrderCount": 0,
                    "pl": "12.34",
                    "unrealizedPL": "-0.12",
                    "marginAvailable": "999.99",
                }
            },
            "open_positions": {
                "positions": [
                    {
                        "instrument": "EUR_USD",
                        "long": {"units": "10"},
                        "short": {"units": "0"},
                        "unrealizedPL": "-0.12",
                    }
                ]
            },
            "open_trades": {
                "trades": [
                    {
                        "id": "555",
                        "instrument": "EUR_USD",
                        "currentUnits": "10",
                        "price": "1.10000",
                        "openTime": "2026-06-19T12:00:00Z",
                    }
                ]
            },
            "pending_orders": {"orders": []},
            "pricing": {
                "prices": [
                    {
                        "instrument": "EUR_USD",
                        "time": "2026-06-19T12:01:00Z",
                        "bids": [{"price": "1.10000"}],
                        "asks": [{"price": "1.10020"}],
                    }
                ]
            },
            "transactions": {
                "transactions": [
                    {
                        "id": "999",
                        "type": "TRADE_CLOSE",
                        "instrument": "EUR_USD",
                        "units": "-10",
                        "pl": "1.23",
                        "time": "2026-06-19T12:02:00Z",
                        "orderID": "888",
                    }
                ]
            },
        }


def test_default_mode_is_read_only_blocked_fixture():
    model = build_read_only_live_data_bridge_read_model(
        env={},
        now_utc="2026-06-19T12:00:00Z",
    )

    assert model["source_type"] == "fixture"
    assert model["source_label"] == "FIXTURE_NOT_LIVE"
    assert model["read_only"] is True
    assert model["live_trading_allowed_from_this_data"] is False
    assert model["execution_readiness"]["LIVE_READY"] is False
    assert model["capabilities"]["broker_write_calls_allowed"] is False


def test_missing_credentials_do_not_crash_or_print_secret_values():
    env = {
        "AIOS_FOREX_READONLY_LIVE_ENABLE": "1",
        "AIOS_FOREX_BROKER": "oanda",
        "OANDA_API_TOKEN": "token=SHOULD_NOT_APPEAR",
    }

    model = build_read_only_live_data_bridge_read_model(
        env=env,
        now_utc="2026-06-19T12:00:00Z",
    )
    payload = json.dumps(model, sort_keys=True)

    assert model["source_label"] == "OANDA_READ_ONLY_BLOCKED"
    assert model["secret_status"]["OANDA_API_TOKEN_STATUS"] == "PRESENT"
    assert model["secret_status"]["OANDA_ACCOUNT_ID_STATUS"] == "MISSING"
    assert "SHOULD_NOT_APPEAR" not in payload
    assert "token=" not in payload.lower()
    assert model["execution_readiness"]["LIVE_READY"] is False


def test_aggregate_read_model_contains_required_source_fields():
    env = {
        "AIOS_FOREX_READONLY_LIVE_ENABLE": "1",
        "AIOS_FOREX_BROKER": "oanda",
        "OANDA_API_TOKEN": "runtime-token-value",
        "OANDA_ACCOUNT_ID": "101-222-333333-001",
        "OANDA_ENVIRONMENT": "practice",
    }

    model = build_read_only_live_data_bridge_read_model(
        env=env,
        client_factory=FakeOandaClient,
        now_utc="2026-06-19T12:00:00Z",
    )
    payload = json.dumps(model, sort_keys=True)

    for section_name in (
        "market",
        "broker_state",
        "positions",
        "risk_pl",
        "exit_readiness",
        "trading_history",
        "execution_readiness",
    ):
        section = model[section_name]
        assert section["source_type"] == "broker-live-read-only"
        assert section["freshness_utc"] == "2026-06-19T12:00:00Z"
        assert section["live_trading_allowed_from_this_data"] is False
        assert section["read_only"] is True
        assert "block_reason" in section

    assert model["broker_state"]["account_reachable"] is True
    assert model["positions"]["positions_reconciled"] is True
    assert model["risk_pl"]["daily_pl_available"] is True
    assert model["trading_history"]["trading_history_available"] is True
    assert model["execution_readiness"]["LIVE_READY"] is False
    assert "101-222-333333-001" not in payload
    assert "runtime-token-value" not in payload
    assert "orderID" not in payload
    assert '"id"' not in payload


def test_sanitized_report_contains_no_private_runtime_values():
    model = build_read_only_live_data_bridge_read_model(
        env={},
        now_utc="2026-06-19T12:00:00Z",
    )
    report = build_sanitized_report(model)

    assert "AIOS Forex Read-Only Live Data Bridge Dry Run V1" in report
    assert "LIVE_READY" in report
    assert "broker_write_calls_allowed" in report
    assert '"broker_write_calls_allowed": false' in report
    assert "secret" in report.lower()


def test_dashboard_exposes_bridge_status_without_browser_network_calls():
    dashboard_path = REPO_ROOT / "apps" / "dashboard" / "src" / "MinimalOperatorDashboard.jsx"
    source = dashboard_path.read_text(encoding="utf-8")

    assert "DISPLAY_ONLY" in source
    assert "EXEC OFF" in source
    assert "BROKER LOCKED" in source
    assert "trading execution stays locked" in source
    assert "ORDER CONTROL remains absent" in source
    for forbidden in ("fetch(", "XMLHttpRequest", "axios", "OANDA_API_TOKEN", "OANDA_ACCOUNT_ID"):
        assert forbidden not in source


def test_no_execution_write_method_call_appears_in_bridge_code():
    paths = [
        REPO_ROOT / "src" / "forex_delivery" / "read_only_live_data_bridge.py",
        REPO_ROOT / "automation" / "forex_engine" / "oanda_read_only_client.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)

    for forbidden in (
        "request_json(\"post\"",
        "request_json(\"put\"",
        "request_json(\"patch\"",
        "request_json(\"delete\"",
        "createorder",
        "cancelorder",
        "closetrade",
        "closeposition",
    ):
        assert forbidden not in combined
