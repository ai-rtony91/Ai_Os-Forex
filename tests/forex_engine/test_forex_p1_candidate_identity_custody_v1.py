"""Synthetic engineering regressions; these records have no PAPER evidence credit."""
import json

import pytest

from automation.forex_engine import forex_p1_supervised_paper_session_v1 as session
from automation.forex_engine.forex_p1_supervised_paper_evidence_pipeline_v1 import run_pipeline


def produced_record(tmp_path, config):
    quote = {
        "schema": session.SNAPSHOT_SCHEMA,
        "evidence_type": "SANITIZED_READ_ONLY_MARKET_SNAPSHOT",
        "provenance": "GENUINE_OBSERVED_MARKET_DATA",
        "instrument": "EUR_USD", "observed_at_utc": "2026-08-06T10:00:00Z",
        "bid": 1.1, "ask": 1.1002, "mid": 1.1001, "spread": 0.0002,
        "source_status": "VALID", "stale_status": "VALID", "read_only": True,
        "broker_write_performed": False, "credentials_included": False,
        "account_identifier_included": False, "raw_payload_included": False,
    }
    candidate = {
        "strategy_id": "c1", "candidate_id": "candidate-custody-1",
        "instrument": "EUR_USD", "direction": "BUY", "units": 100,
        "stop_price": 1.099, "target_price": 1.102, "risk_amount": 0.12,
        "entry_rationale": "sanitized momentum review", "status": "PAPER_ELIGIBLE",
        "sanitized": True, "current": True, "live_execution_allowed": False,
        "order_submission_allowed": False,
    }
    if config is not None:
        candidate["strategy_config"] = config
    active = session.open_paper_session(
        quote, candidate, "reviewer", "2026-08-06T10:00:01Z", tmp_path / "active.json"
    )
    closing = {**quote, "observed_at_utc": "2026-08-06T10:05:00Z",
               "bid": 1.102, "ask": 1.1022, "mid": 1.1021}
    return session.build_completed_trade_record(
        active, closing, "paper_target", "reviewer", "2026-08-06T10:05:01Z"
    )


def capture(tmp_path, record):
    source = tmp_path / "input.json"
    ledger = tmp_path / "ledger.json"
    source.write_text(json.dumps([record]), encoding="utf-8")
    result = run_pipeline(source, ledger, tmp_path / "state.json", tmp_path / "report.md")
    return result, json.loads(ledger.read_text(encoding="utf-8"))["records"]


@pytest.mark.parametrize("config", [None, {"atr_period": 3, "multiplier": 2.0}])
def test_real_producer_to_serialized_ledger_retains_candidate_identity(tmp_path, config):
    record = produced_record(tmp_path, config)
    assert record["candidate_id"] == "candidate-custody-1"
    result, records = capture(tmp_path, record)
    assert result["accepted_records"] == 1
    saved = records[0]
    assert saved["candidate_id"] == record["candidate_id"]
    assert saved["trade_id"] == record["trade_id"]
    assert saved["strategy_id"] == record["strategy_id"]
    assert saved["evidence_source"] == record["evidence_source"]
    if config is None:
        assert "strategy_config" not in saved
    else:
        assert saved["strategy_config"] == config


def test_missing_historical_candidate_and_config_are_never_synthesized(tmp_path):
    record = produced_record(tmp_path, None)
    del record["candidate_id"]
    result, records = capture(tmp_path, record)
    assert result["accepted_records"] == 1  # Existing arithmetic acceptance is unchanged.
    assert result["ready_for_p2_review"] is False
    assert "candidate_id" not in records[0]
    assert "strategy_config" not in records[0]


def test_candidate_identity_does_not_bypass_existing_private_content_rejection(tmp_path):
    record = produced_record(tmp_path, None)
    record["candidate_id"] = "password=private-value"
    result, records = capture(tmp_path, record)
    assert result["accepted_records"] == 0
    assert records == []
    assert "secret_or_private_identifier_rejected" in result["rejections"][0]["reasons"]
