from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_p1_eurusd_m5_history_capture_v1 import (
    GENUINE_PROVENANCE, HISTORY_KEYS, RUNTIME_PATH, build_canonical_history_artifact,
    build_capture_state, extract_canonical_completed_candles, resolve_canonical_practice_transport,
    validate_canonical_history_artifact, validate_runtime_capture_request,
)
from automation.forex_engine.forex_p1_eurusd_market_history_signal_v1 import validate_market_history
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient
from automation.forex_engine.oanda_practice_candle_history_transport_v1 import OandaPracticeCandleHistoryTransportV1


def stamp(minutes: int) -> str:
    return (datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def raw_candle(minutes: int, *, complete: bool = True, volume: int = 10, **mid):
    prices = {"o": "1.1000", "h": "1.1010", "l": "1.0990", "c": "1.1005"}
    prices.update(mid)
    return {"time": stamp(minutes), "complete": complete, "volume": volume, "mid": prices}


def payload(*candles):
    return {"instrument": "EUR_USD", "granularity": "M5",
            "candles": list(candles or (raw_candle(10), raw_candle(5), raw_candle(1)))}


def artifact():
    return build_canonical_history_artifact(extract_canonical_completed_candles(payload()), requested_count=50)


def request(**changes):
    values = {"owner_local_runtime": True, "environment": "practice", "instrument": "EUR_USD",
              "granularity": "M5", "count": 50, "output": RUNTIME_PATH}
    values.update(changes)
    return validate_runtime_capture_request(**values)


def test_canonical_client_discovery_and_practice_only():
    client = OandaPracticeCandleHistoryTransportV1(api_token="x", opener=object())
    assert resolve_canonical_practice_transport(client) is client
    with pytest.raises(ValueError, match="dedicated"):
        resolve_canonical_practice_transport(OandaReadOnlyClient(api_token="x", account_id="", environment="practice"))


@pytest.mark.parametrize("changes,reason", [
    ({"owner_local_runtime": False}, "owner_local"), ({"environment": "live"}, "practice"),
    ({"instrument": "GBP_USD"}, "EUR_USD"), ({"granularity": "M1"}, "M5"),
    ({"count": 2}, "equal_50"), ({"count": 501}, "equal_50"),
    ({"output": ".aios/runtime/other.json"}, "canonical_runtime"),
])
def test_runtime_request_fail_closed(changes, reason):
    with pytest.raises(ValueError, match=reason):
        request(**changes)


def test_runtime_request_accepts_exact_contract():
    assert request()["count"] == 50


def test_completed_extraction_discards_incomplete_and_uses_canonical_fields():
    candles = extract_canonical_completed_candles(payload(raw_candle(10), raw_candle(7, complete=False), raw_candle(5), raw_candle(1)))
    assert len(candles) == 3
    assert set(candles[0]) == {"observed_at_utc", "open", "high", "low", "close", "volume", "complete"}
    assert "time" not in candles[0] and "mid" not in candles[0]


def test_official_oanda_response_shape_is_accepted():
    assert len(extract_canonical_completed_candles(payload())) == 3


@pytest.mark.parametrize("change,reason", [
    ({"instrument": None}, "raw_payload"),
    ({"granularity": None}, "raw_payload"),
    ({"candles": None}, "raw_payload"),
    ({"instrument": "GBP_USD"}, "EUR_USD"),
    ({"granularity": "M1"}, "M5"),
    ({"extra": "rejected"}, "raw_payload"),
])
def test_official_oanda_response_contract_fails_closed(change, reason):
    response = payload()
    if next(iter(change.values())) is None:
        response.pop(next(iter(change)))
    else:
        response.update(change)
    with pytest.raises(ValueError, match=reason):
        extract_canonical_completed_candles(response)


def test_fewer_than_three_completed_candles_rejected():
    with pytest.raises(ValueError, match="REQUIRE_MORE_HISTORY"):
        extract_canonical_completed_candles(payload(raw_candle(5), raw_candle(1)))


@pytest.mark.parametrize("candles,reason", [
    ((raw_candle(5), raw_candle(5), raw_candle(1)), "duplicate"),
    ((raw_candle(1), raw_candle(5), raw_candle(10)), "unsorted"),
    (({**raw_candle(10), "time": "not-utc"}, raw_candle(5), raw_candle(1)), "utc"),
    ((raw_candle(10, o="NaN"), raw_candle(5), raw_candle(1)), "open"),
    ((raw_candle(10, h="Infinity"), raw_candle(5), raw_candle(1)), "high"),
    ((raw_candle(10, l="0"), raw_candle(5), raw_candle(1)), "low"),
    ((raw_candle(10, o="1.2000"), raw_candle(5), raw_candle(1)), "geometry"),
    ((raw_candle(10, volume=-1), raw_candle(5), raw_candle(1)), "volume"),
])
def test_invalid_candles_rejected(candles, reason):
    with pytest.raises(ValueError, match=reason):
        extract_canonical_completed_candles(payload(*candles))


def test_extra_raw_fields_and_private_identifiers_rejected():
    candle = raw_candle(10)
    candle["transactionID"] = "secret"
    with pytest.raises(ValueError, match="fields"):
        extract_canonical_completed_candles(payload(candle, raw_candle(5), raw_candle(1)))
    with pytest.raises(ValueError, match="raw_payload"):
        extract_canonical_completed_candles({**payload(), "accountID": "secret"})


def test_artifact_exactly_matches_canonical_contract_and_validator():
    history = artifact()
    assert set(history) == HISTORY_KEYS
    assert history["schema"] == "AIOS_P1_EURUSD_MARKET_HISTORY.v1"
    assert history["evidence_type"] == "SANITIZED_CANDLE_HISTORY"
    assert history["provenance"] == GENUINE_PROVENANCE
    assert validate_canonical_history_artifact(history)["returned_count"] == 3


def test_stale_history_rejected():
    old = "2020-01-01T00:00:00Z"
    candles = [{"time": old, "complete": True, "volume": 1,
                "mid": {"o": "1", "h": "1", "l": "1", "c": "1"}} for _ in range(3)]
    for index, candle in enumerate(candles):
        candle["time"] = f"2020-01-01T00:{index:02d}:00Z"
    with pytest.raises(ValueError, match="stale"):
        validate_canonical_history_artifact(build_canonical_history_artifact(
            extract_canonical_completed_candles(payload(*candles)), requested_count=3))


def test_fixture_and_synthetic_receive_zero_genuine_credit():
    history = artifact()
    history["provenance"] = "TEST_FIXTURE"
    assert validate_market_history(history, allow_fixture=True)["provenance"] != GENUINE_PROVENANCE
    history["provenance"] = "SYNTHETIC"
    with pytest.raises(ValueError, match="genuine"):
        validate_market_history(history, allow_fixture=True)


def test_build_state_protected_runtime_flags_are_false():
    state = build_capture_state(generated_at_utc=stamp(0), repository_root=str(ROOT), branch="work", head="abc")
    for key in ("genuine_history_captured", "genuine_history_consumed", "genuine_signal_generated",
                "candidate_generated", "paper_session_opened", "broker_call_performed",
                "credentials_loaded", "credentials_persisted", "broker_write_performed",
                "demo_order_performed", "live_order_performed", "money_movement_performed"):
        assert state[key] is False


def test_cli_default_preflight_is_offline_and_does_not_write(tmp_path):
    runtime = ROOT / RUNTIME_PATH
    before = runtime.stat().st_mtime_ns if runtime.exists() else None
    result = subprocess.run([sys.executable, "scripts/forex_delivery/run_forex_p1_eurusd_m5_history_capture_v1.py"],
                            cwd=ROOT, text=True, capture_output=True, check=True, env={})
    output = json.loads(result.stdout)
    assert output == {"capture_requires_owner_local_runtime": True, "credentials_loaded": False,
                      "environment": "practice", "granularity": "M5", "instrument": "EUR_USD",
                      "network_used": False, "runtime_write_performed": False, "status": "READY"}
    assert (runtime.stat().st_mtime_ns if runtime.exists() else None) == before


def test_handoff_has_exact_paths_and_no_placeholders():
    result = subprocess.run([sys.executable, "scripts/forex_delivery/run_forex_p1_eurusd_m5_history_capture_v1.py", "print-owner-handoff"],
                            cwd=ROOT, text=True, capture_output=True, check=True)
    text = result.stdout
    assert "C:\\Dev\\Ai_Os" in text and RUNTIME_PATH in text
    assert "<" not in text and ">" not in text and "TODO" not in text and "TBD" not in text
    assert "market_history_signal_v1.py evaluate" in text


def test_no_execution_features_exist_in_capture_component():
    source = (ROOT / "automation/forex_engine/forex_p1_eurusd_m5_history_capture_v1.py").read_text()
    for forbidden in ("submit_order", "generate_candidate", "open_session", "schedule", "webhook"):
        assert forbidden not in source
