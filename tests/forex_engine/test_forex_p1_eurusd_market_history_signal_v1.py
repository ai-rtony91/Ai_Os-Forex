import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from automation.forex_engine.forex_p1_eurusd_market_history_signal_v1 import (
    HISTORY_SCHEMA, build_signal_state, derive_stop_target, resolve_canonical_signal_rules,
    stable_json, validate_market_history, validate_signal_decision,
)
from automation.forex_engine.position_sizing import calculate_position_size
from scripts.forex_delivery.run_forex_p1_eurusd_market_history_signal_v1 import load_json, main

NOW = datetime(2026, 8, 6, 5, 30, tzinfo=timezone.utc)


def history(closes=(1.1000, 1.1007, 1.1014), *, provenance="TEST_FIXTURE"):
    candles = []
    for index, close in enumerate(closes):
        observed = NOW - timedelta(minutes=5 * (len(closes) - 1 - index))
        candles.append({"observed_at_utc": observed.isoformat().replace("+00:00", "Z"), "open": close - 0.0002,
                        "high": close + 0.0005, "low": close - 0.0005, "close": close, "volume": 100 + index, "complete": True})
    return {"schema": HISTORY_SCHEMA, "evidence_type": "SANITIZED_CANDLE_HISTORY", "provenance": provenance,
            "broker_label": "OANDA", "environment": "PRACTICE", "instrument": "EUR_USD", "granularity": "M5",
            "requested_count": len(candles), "returned_count": len(candles), "first_observed_at_utc": candles[0]["observed_at_utc"],
            "last_observed_at_utc": candles[-1]["observed_at_utc"], "candles": candles, "source_status": "VALID", "stale_status": "VALID",
            "read_only": True, "complete": True, "broker_write_performed": False, "credentials_persisted": False,
            "account_identifier_included": False, "raw_payload_included": False, "order_submission_allowed": False,
            "demo_execution_allowed": False, "live_execution_allowed": False, "money_movement_allowed": False}


def validated(value=None): return validate_market_history(value or history(), now=NOW, allow_fixture=True)
def decision(value=None): return build_signal_state(validated(value), generated_at_utc="2026-08-06T05:30:00Z")


def history_with_latest_timestamp(latest: datetime):
    value = history()
    for index, candle in enumerate(value["candles"]):
        observed = latest - timedelta(minutes=5 * (len(value["candles"]) - 1 - index))
        candle["observed_at_utc"] = observed.isoformat().replace("+00:00", "Z")
    value["first_observed_at_utc"] = value["candles"][0]["observed_at_utc"]
    value["last_observed_at_utc"] = value["candles"][-1]["observed_at_utc"]
    return value


def test_missing_history():
    with pytest.raises(ValueError, match="market_history_required"): validate_market_history(None)


def test_malformed_json_and_duplicate_keys_and_nonfinite(tmp_path):
    for text, match in (("{", "Expecting"), ('{"a":1,"a":2}', "duplicate JSON key"), ('{"a":NaN}', "non-finite JSON")):
        path = tmp_path / "input.json"; path.write_text(text)
        with pytest.raises((ValueError, json.JSONDecodeError), match=match): load_json(path)


def test_wrong_instrument_and_fixture_has_zero_runtime_credit():
    value = history(); value["instrument"] = "GBP_USD"
    with pytest.raises(ValueError, match="invalid_or_unsafe"): validated(value)
    with pytest.raises(ValueError, match="genuine_observed"): validate_market_history(history(), now=NOW)


def test_stale_and_insufficient_history():
    value = history()
    for candle, stamp in zip(value["candles"], ("2026-08-06T04:50:00Z", "2026-08-06T04:55:00Z", "2026-08-06T05:00:00Z")): candle["observed_at_utc"] = stamp
    value["first_observed_at_utc"] = value["candles"][0]["observed_at_utc"]; value["last_observed_at_utc"] = value["candles"][-1]["observed_at_utc"]
    with pytest.raises(ValueError, match="stale_history"): validated(value)
    assert decision(history((1.1, 1.1001)))["status"] == "REQUIRE_MORE_HISTORY"


def test_latest_completed_m5_candle_is_fresh_at_its_completion_time():
    value = history_with_latest_timestamp(NOW - timedelta(minutes=5))
    assert validated(value)["last_observed_at_utc"] == value["last_observed_at_utc"]


def test_latest_completed_m5_candle_is_fresh_at_allowance_boundary():
    value = history_with_latest_timestamp(NOW - timedelta(minutes=10))
    assert validated(value)["last_observed_at_utc"] == value["last_observed_at_utc"]


def test_latest_completed_m5_candle_is_rejected_after_allowance():
    value = history_with_latest_timestamp(NOW - timedelta(minutes=10, seconds=1))
    with pytest.raises(ValueError, match="stale_history"):
        validated(value)


def test_future_m5_candle_is_rejected():
    value = history_with_latest_timestamp(NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="stale_history"):
        validated(value)


def test_duplicate_unsorted_and_invalid_ohlc():
    value = history(); value["candles"][1]["observed_at_utc"] = value["candles"][0]["observed_at_utc"]
    with pytest.raises(ValueError, match="duplicate"): validated(value)
    value = history(); value["candles"][0], value["candles"][1] = value["candles"][1], value["candles"][0]
    value["first_observed_at_utc"] = value["candles"][0]["observed_at_utc"]
    with pytest.raises(ValueError, match="unsorted"): validated(value)
    value = history(); value["candles"][0]["high"] = value["candles"][0]["low"]
    with pytest.raises(ValueError, match="invalid_ohlc"): validated(value)


def test_valid_buy_stop_target_rr_and_position_sizing_compatibility():
    item = decision(); assert item["status"] == "BUY" and item["direction"] == "BUY"
    assert item["stop_price"] < item["entry_reference"] < item["target_price"] and item["reward_to_risk"] == 2.0
    sized = calculate_position_size({"pair": "EURUSD", "direction": "buy", "entry_price": item["entry_reference"],
                                     "stop_loss": item["stop_price"], "paper_only": True, "risk_dollars": 1})
    assert sized["allowed"] is True and sized["safety"]["network_access"] is False


def test_no_signal_regime_and_volatility_rejections():
    assert decision(history((1.1014, 1.1007, 1.1000)))["status"] == "NO_SIGNAL"
    assert decision(history((1.1000, 1.1001, 1.1000)))["status"] == "REGIME_REJECTED"
    low = history((1.10000, 1.10005, 1.10010))
    for candle in low["candles"]: candle["low"] = candle["close"] - 0.00005; candle["high"] = candle["close"] + 0.00005; candle["open"] = candle["close"]
    assert decision(low)["status"] == "RISK_REJECTED"
    high = history((1.100, 1.105, 1.110))
    for candle in high["candles"]: candle["low"] = candle["close"] - 0.005; candle["high"] = candle["close"] + 0.005; candle["open"] = candle["close"]
    assert decision(high)["status"] == "RISK_REJECTED"


def test_invalid_stop_and_reward_to_risk_fail_closed():
    value = history((1.1002, 1.1001, 1.1000))
    for candle in value["candles"]: candle["low"] = 1.1000; candle["open"] = candle["close"]
    with pytest.raises(ValueError, match="invalid_stop_distance"): derive_stop_target(validated(value))
    item = decision(); item["reward_to_risk"] = 1.5
    with pytest.raises(ValueError, match="invalid_reward_to_risk"): validate_signal_decision(item)


def test_deterministic_id_idempotence_and_conflicting_evidence():
    assert decision() == decision() and decision()["signal_id"] == decision()["signal_id"]
    value = history(); value["source_status"] = "CONFLICT"
    with pytest.raises(ValueError, match="invalid_or_unsafe"): validated(value)


def test_no_candidate_session_network_credentials_or_permissions():
    item = decision()
    assert "candidate" not in item and "session" not in item
    for key in ("broker_call_performed", "credentials_loaded", "account_access_performed", "order_submission_allowed",
                "demo_execution_allowed", "live_execution_allowed", "money_movement_allowed"):
        assert item[key] is False


def test_rules_state_report_and_cli_preflight_are_deterministic(capsys):
    rules = resolve_canonical_signal_rules(); assert rules["minimum_candles"] == 3 and rules["granularity"] == "M5"
    assert stable_json(decision()) == stable_json(decision())
    assert main(["preflight"]) == 0
    output = json.loads(capsys.readouterr().out); assert output == {"credentials_loaded": False, "granularity": "M5", "instrument": "EUR_USD", "minimum_candles": 3, "network_used": False, "status": "READY_FOR_READ_ONLY_HISTORY_CAPTURE_PACKET", "writes_performed": False}


def test_timing_compatibility_and_signal_validation():
    item = decision(); datetime.fromisoformat(item["generated_at_utc"].replace("Z", "+00:00")); assert validate_signal_decision(copy.deepcopy(item)) == item
