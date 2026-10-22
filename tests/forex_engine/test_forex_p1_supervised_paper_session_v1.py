from __future__ import annotations

import json
from pathlib import Path

import pytest

import automation.forex_engine.forex_p1_supervised_paper_session_v1 as module


def snapshot(**changes):
    value = {"schema": module.SNAPSHOT_SCHEMA, "evidence_type": "SANITIZED_READ_ONLY_MARKET_SNAPSHOT", "provenance": "GENUINE_OBSERVED_MARKET_DATA", "instrument": "EUR_USD", "observed_at_utc": "2026-08-06T10:00:00Z", "bid": 1.1, "ask": 1.1002, "mid": 1.1001, "spread": 0.0002, "source_status": "VALID", "stale_status": "VALID", "read_only": True, "broker_write_performed": False, "credentials_included": False, "account_identifier_included": False, "raw_payload_included": False}
    value.update(changes); return value


def candidate(**changes):
    value = {"strategy_id": "c1", "candidate_id": "candidate-1", "instrument": "EUR_USD", "direction": "BUY", "units": 100, "stop_price": 1.099, "target_price": 1.102, "risk_amount": 0.12, "entry_rationale": "sanitized momentum review", "status": "PAPER_ELIGIBLE", "sanitized": True, "current": True, "live_execution_allowed": False, "order_submission_allowed": False}
    value.update(changes); return value


def sell_candidate(**changes):
    value = {"strategy_id": "c1", "candidate_id": "candidate-sell-1", "instrument": "EUR_USD", "direction": "SELL", "units": 100, "stop_price": 1.1015, "target_price": 1.0985, "risk_amount": 0.12, "entry_rationale": "sanitized momentum review", "status": "PAPER_ELIGIBLE", "sanitized": True, "current": True, "live_execution_allowed": False, "order_submission_allowed": False}
    value.update(changes); return value


def open_one(path: Path):
    return module.open_paper_session(snapshot(), candidate(), "Anthony", "2026-08-06T10:01:00Z", path)


def open_sell_one(path: Path):
    return module.open_paper_session(
        snapshot(bid=1.1002, ask=1.1004, mid=1.1003),
        sell_candidate(),
        "Anthony",
        "2026-08-06T10:01:00Z",
        path,
    )

def test_valid_snapshot(): assert module.validate_market_snapshot(snapshot())["ask"] == 1.1002


@pytest.mark.parametrize("change", [
    {"schema": "bad"}, {"provenance": "fixture"}, {"provenance": "synthetic"}, {"stale_status": "STALE"},
    {"bid": float("nan")}, {"ask": 1.0}, {"mid": 2.0}, {"password": "hidden"}, {"account_id": "hidden"},
    {"raw_payload": {}}, {"instrument": "BTC_USD"}, {"spread": 3}, {"observed_at_utc": "2026-01-01"},
])
def test_invalid_snapshots(change):
    with pytest.raises(ValueError): module.validate_market_snapshot(snapshot(**change))


@pytest.mark.parametrize("change", [
    {"instrument": "GBP_USD"}, {"status": "WATCH"}, {"live_execution_allowed": True},
    {"units": 0}, {"units": 1_000_001}, {"sanitized": False}, {"current": False},
])
def test_invalid_candidates(tmp_path, change):
    with pytest.raises(ValueError, match="NO_PAPER_TRADE_CANDIDATE"):
        module.open_paper_session(snapshot(), candidate(**change), "Anthony", "2026-08-06T10:01:00Z", tmp_path / "active.json")


def test_valid_sell_candidate_opens(tmp_path):
    session = open_sell_one(tmp_path / "active.json")
    assert session["direction"] == "SELL"
    assert session["entry_price"] == pytest.approx(1.1002)
    assert session["mfe_price"] == pytest.approx(1.1004)
    assert session["mae_price"] == pytest.approx(1.1004)


@pytest.mark.parametrize(
    "change",
    [
        {"stop_price": 1.1000, "target_price": 1.1020},
    ],
)
def test_invalid_sell_candidates(tmp_path, change):
    with pytest.raises(ValueError, match="NO_PAPER_TRADE_CANDIDATE"):
        module.open_paper_session(
            snapshot(bid=1.1002, ask=1.1004, mid=1.1003),
            sell_candidate(**change),
            "Anthony",
            "2026-08-06T10:01:00Z",
            tmp_path / "active.json",
        )


def test_valid_sell_candidate_geometry_accepts_bid_entry_between_target_and_stop(tmp_path):
    session = module.open_paper_session(
        snapshot(bid=1.1002, ask=1.1004, mid=1.1003),
        sell_candidate(stop_price=1.1010, target_price=1.1000),
        "Anthony",
        "2026-08-06T10:01:00Z",
        tmp_path / "active.json",
    )
    assert session["direction"] == "SELL"
    assert session["entry_price"] == pytest.approx(1.1002)
    assert session["target_price"] == pytest.approx(1.1000)
    assert session["stop_price"] == pytest.approx(1.1010)


def test_open_and_identical_open_are_idempotent(tmp_path):
    path = tmp_path / "active.json"; first = open_one(path); second = open_one(path)
    assert first == second and first["entry_price"] == snapshot()["ask"]


def test_conflicting_open_fails(tmp_path):
    path = tmp_path / "active.json"; open_one(path)
    with pytest.raises(ValueError, match="conflicting_active_session"):
        module.open_paper_session(snapshot(), candidate(candidate_id="different"), "Anthony", "2026-08-06T10:01:00Z", path)


def test_load_active_session_returns_none_for_valid_closed_tombstone(tmp_path):
    path = tmp_path / "active.json"
    path.write_text(
        json.dumps({
            "schema": "AIOS_P1_SUPERVISED_PAPER_SESSION.v1",
            "status": "CLOSED",
            "closed_at_utc": "2026-08-19T15:14:32.562095Z",
            "closed_reason": "paper_target",
            "strategy_id": "supertrend_pullback_v1",
            "strategy_name": "supertrend_pullback_v1",
        }),
        encoding="utf-8",
    )
    assert module.load_active_session(path) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "CLOSED", "closed_reason": "paper_target"},
        {
            "schema": "AIOS_P1_SUPERVISED_PAPER_SESSION.v1",
            "status": "CLOSED",
            "closed_at_utc": "2026-08-19T15:14:32.562095Z",
        },
        {
            "schema": "AIOS_P1_SUPERVISED_PAPER_SESSION.v1",
            "status": "CLOSED",
            "closed_at_utc": "2026-08-19T15:14:32.562095Z",
            "closed_reason": "",
        },
        {
            "schema": "AIOS_P1_SUPERVISED_PAPER_SESSION.v1",
            "status": "ARCHIVED",
            "closed_at_utc": "2026-08-19T15:14:32.562095Z",
            "closed_reason": "paper_target",
        },
    ],
)
def test_load_active_session_rejects_malformed_or_unknown_tombstones(tmp_path, payload):
    path = tmp_path / "active.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid_active_session"):
        module.load_active_session(path)


def test_close_without_active_fails(tmp_path):
    with pytest.raises(ValueError, match="no_active_session"):
        module.close_paper_session(snapshot(), "target", "Anthony", "2026-08-06T11:01:00Z", tmp_path/"x", {}, Path.cwd())


def test_timestamp_and_instrument_close_validation(tmp_path):
    session = open_one(tmp_path/"active.json")
    with pytest.raises(ValueError, match="exit_must_follow_entry"): module.build_completed_trade_record(session, snapshot(), "target", "Anthony", "2026-08-06T11:00:00Z")
    with pytest.raises(ValueError, match="closing_instrument_mismatch"): module.build_completed_trade_record(session, snapshot(instrument="GBP_USD", observed_at_utc="2026-08-06T11:00:00Z"), "target", "Anthony", "2026-08-06T11:01:00Z")
    record = module.build_completed_trade_record(session, snapshot(observed_at_utc="2026-08-06T11:00:00Z"), "target", "Anthony", "2026-08-06T11:00:00Z")
    assert record["review_timestamp_utc"] == "2026-08-06T11:00:00Z"
    assert record["exit_timestamp_utc"] == "2026-08-06T11:00:00Z"


def test_conservative_ask_to_bid_result_ignores_mid(tmp_path):
    session = open_one(tmp_path/"active.json"); closing = snapshot(observed_at_utc="2026-08-06T11:00:00Z", bid=1.101, ask=1.1014, mid=1.1012, spread=.0004)
    result = module.calculate_conservative_paper_result(session, closing)
    assert result["entry_price"] == 1.1002 and result["exit_price"] == 1.101 and result["net_pl"] == pytest.approx(.08)


def test_conservative_sell_ask_to_bid_result_uses_ask_exit(tmp_path):
    session = open_sell_one(tmp_path/"active.json")
    closing = snapshot(observed_at_utc="2026-08-06T11:00:00Z", bid=1.0992, ask=1.0994, mid=1.0993, spread=.0002)
    result = module.calculate_conservative_paper_result(session, closing)
    assert result["entry_price"] == pytest.approx(1.1002)
    assert result["exit_price"] == pytest.approx(1.0994)
    assert result["net_pl"] == pytest.approx(.08)


def test_completed_trade_has_canonical_shape(tmp_path):
    session = open_one(tmp_path/"active.json"); closing = snapshot(observed_at_utc="2026-08-06T11:00:00Z")
    record = module.build_completed_trade_record(session, closing, "owner close", "Anthony", "2026-08-06T11:01:00Z")
    assert set(module.__dict__["run_capture_replay"].__globals__["run_pipeline"].__globals__["REQUIRED_FIELDS"]) <= set(record)
    assert record["evidence_type"] == "paper"


def test_close_preserves_paper_excursion_and_holding_metrics(tmp_path):
    runtime = tmp_path / "active.json"
    open_one(runtime)
    module.update_paper_session_extremes(
        snapshot(observed_at_utc="2026-08-06T10:30:00Z", bid=1.1010,
                 ask=1.1012, mid=1.1011), runtime
    )
    record = module.build_completed_trade_record(
        module.load_active_session(runtime),
        snapshot(observed_at_utc="2026-08-06T11:00:00Z", bid=1.1015,
                 ask=1.1017, mid=1.1016),
        "target", "Anthony", "2026-08-06T11:01:00Z"
    )
    assert record["holding_duration_seconds"] == 3600.0
    assert record["mfe_price"] == 1.1015
    assert record["mfe_r"] > 0
    assert record["mae_price"] == 1.1
    assert record["mae_r"] > 0
    assert record["outcome_r"] > 0
    assert record["planned_reward_risk"] == pytest.approx(1.5)
    assert record["realized_r"] == pytest.approx(record["outcome_r"])
    assert record["roi_class"] == "POSITIVE_R"


def test_close_preserves_sell_excursion_and_holding_metrics(tmp_path):
    runtime = tmp_path / "active.json"
    open_sell_one(runtime)
    module.update_paper_session_extremes(
        snapshot(observed_at_utc="2026-08-06T10:30:00Z", bid=1.0998,
                 ask=1.1000, mid=1.0999), runtime
    )
    record = module.build_completed_trade_record(
        module.load_active_session(runtime),
        snapshot(observed_at_utc="2026-08-06T11:00:00Z", bid=1.0990,
                 ask=1.0992, mid=1.0991),
        "target", "Anthony", "2026-08-06T11:01:00Z"
    )
    assert record["direction"] == "SELL"
    assert record["mfe_price"] == 1.0992
    assert record["mfe_r"] > 0
    assert record["mae_price"] == 1.1004
    assert record["mae_r"] > 0
    assert record["outcome_r"] > 0
    assert record["planned_reward_risk"] == pytest.approx(1.3076923076923077)
    assert record["realized_r"] == pytest.approx(record["outcome_r"])
    assert record["roi_class"] == "POSITIVE_R"


def test_abort_has_zero_credit_and_flags_false(tmp_path):
    path = tmp_path/"active.json"; open_one(path); result = module.abort_paper_session(path)
    assert result["p1_credit"] == 0 and not path.exists() and all(result[key] is False for key in module.SAFETY_FLAGS)


def test_close_calls_canonical_capture_and_evaluator(monkeypatch, tmp_path):
    runtime = tmp_path/"active.json"; open_one(runtime); calls=[]
    def capture(*args, **kwargs): calls.append((args, kwargs)); return {"accepted_records": 1, "replay_status": "CANONICAL_P1_EVALUATOR_COMPLETE"}
    monkeypatch.setattr(module, "run_capture_replay", capture)
    paths={key: tmp_path/name for key,name in {"ledger":"l.json","state":"s.json","report":"r.md","events":"e.jsonl"}.items()}
    result=module.close_paper_session(snapshot(observed_at_utc="2026-08-06T11:00:00Z"), "target", "Anthony", "2026-08-06T11:01:00Z", runtime, paths, Path.cwd())
    assert len(calls)==1 and result["pipeline"]["replay_status"].endswith("EVALUATOR_COMPLETE") and not runtime.exists()


def test_empty_state_report_contains_all_protections(tmp_path):
    state=module.build_session_state(tmp_path/"none.json"); report=module.render_owner_report(state)
    assert state["active_session"] is None and state["genuine_paper_trades_recorded"] == 0
    assert all(state[key] is False and f"{key}: false" in report for key in module.SAFETY_FLAGS)


def test_stable_json_rejects_nonfinite():
    with pytest.raises(ValueError): module.stable_json({"x": float("nan")})


def test_runner_source_has_no_network_or_broker_client():
    source=(Path(__file__).parents[2]/"scripts/forex_delivery/run_forex_p1_supervised_paper_session_v1.py").read_text()
    assert "requests" not in source and "socket" not in source and "oanda" not in source.lower()


def test_timing_metadata_forecast_compatible():
    path=Path(__file__).parents[2]/"Reports/orchestration/AIOS_CODEX_TASK_DELIVERY_METADATA_V1.json"
    if path.exists():
        data=json.loads(path.read_text()); assert isinstance(data, (dict, list))
