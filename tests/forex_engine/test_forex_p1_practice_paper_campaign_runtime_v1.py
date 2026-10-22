from __future__ import annotations

import json
import os
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import automation.forex_engine.forex_p1_practice_paper_campaign_runtime_v1 as runtime
from automation.forex_engine.forex_p1_supervised_paper_campaign_v1 import CampaignHalt, CampaignWait
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient

NOW = datetime(2026, 8, 10, 10, 30, tzinfo=timezone.utc)


def _write_legacy_lock(
    path, *, pid=101, owner="legacy-owner", heartbeat=NOW, status="ACTIVE"
):
    path.write_text(
        json.dumps(
            {
                "schema": runtime.SUPER_TREND_LOCK_SCHEMA,
                "status": status,
                "owner": owner,
                "pid": pid,
                "heartbeat_at_utc": runtime._stamp(heartbeat),
            }
        ),
        encoding="utf-8",
    )


def candles():
    result = []
    for index in range(3):
        stamp = NOW - timedelta(minutes=15 - index * 5)
        close = 1.1000 + index * 0.0007
        result.append({
            "time": stamp.isoformat().replace("+00:00", "Z"), "complete": True,
            "volume": 100 + index,
            "mid": {"o": str(close - .0002), "h": str(close + .0005),
                    "l": str(close - .0005), "c": str(close)},
        })
    return {"instrument": "EUR_USD", "granularity": "M5", "candles": result}


def pricing(price: float, stamp: datetime = NOW):
    return {"prices": [{"instrument": "EUR_USD", "time": stamp.isoformat().replace("+00:00", "Z"),
                         "bids": [{"price": str(price)}], "asks": [{"price": str(price + .0002)}]}]}


def client(prices):
    item = OandaReadOnlyClient(api_token="runtime-only", account_id="runtime-only", environment="practice")
    item.candles = lambda *_args, **_kwargs: candles()
    values = iter(prices)
    item.pricing = lambda *_args, **_kwargs: next(values)
    return item


def test_runtime_opens_then_closes_one_paper_position(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "build_signal_state", lambda *_args, **_kwargs: {
        "status": "BUY", "signal_id": "canonical-signal", "strategy_id": "sprint-4",
        "stop_price": 1.099, "target_price": 1.102,
    })
    moments = iter([
        NOW, NOW, NOW + timedelta(minutes=5), NOW + timedelta(minutes=5),
    ])
    records = list(runtime.completed_paper_records(
        client([pricing(1.1000), pricing(1.1021, NOW + timedelta(minutes=5))]),
        cycles=2, reviewer_identity="Anthony", runtime_path=tmp_path / "active.json",
        now=lambda: next(moments), sleep=lambda _seconds: None,
    ))
    assert len([item for item in records if isinstance(item, dict)]) == 1
    assert records[0]["evidence_type"] == "paper"
    assert records[0]["realized_pl"] > 0
    assert isinstance(records[-1], CampaignHalt)
    closed = json.loads((tmp_path / "active.json").read_text(encoding="utf-8"))
    assert closed["status"] == "CLOSED"
    assert closed["closed_reason"] == "paper_target"


def test_runtime_close_uses_a_review_timestamp_not_cycle_start(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "build_signal_state", lambda *_args, **_kwargs: {
        "status": "BUY", "signal_id": "canonical-signal", "strategy_id": "sprint-4",
        "stop_price": 1.099, "target_price": 1.102,
    })
    review_time = NOW + timedelta(minutes=10)
    moments = iter([NOW, NOW, NOW + timedelta(minutes=5), NOW + timedelta(minutes=5)])
    monkeypatch.setattr(runtime, "_utc_now", lambda: review_time)
    records = list(runtime.completed_paper_records(
        client([pricing(1.1000), pricing(1.1021, NOW + timedelta(minutes=5))]),
        cycles=2, reviewer_identity="Anthony", runtime_path=tmp_path / "active.json",
        now=lambda: next(moments), sleep=lambda _seconds: None,
    ))
    closes = [item for item in records if isinstance(item, dict)]
    assert len(closes) == 1
    assert closes[0]["review_timestamp_utc"] == runtime._stamp(review_time)
    assert closes[0]["exit_timestamp_utc"].endswith("Z")


def test_runtime_cycle_telemetry_carries_r_classification_fields(monkeypatch, tmp_path):
    captured = []

    def record_cycle(_path, record):
        captured.append(record)

    monkeypatch.setattr(runtime, "append_cycle_record", record_cycle)
    monkeypatch.setattr(runtime, "_utc_now", lambda: NOW + timedelta(minutes=5))
    monkeypatch.setattr(runtime, "build_signal_state", lambda *_args, **_kwargs: {
        "status": "BUY", "signal_id": "canonical-signal", "strategy_id": "sprint-4",
        "stop_price": 1.099, "target_price": 1.102,
    })
    moments = iter([
        NOW, NOW + timedelta(minutes=5), NOW + timedelta(minutes=5), NOW + timedelta(minutes=5),
    ])
    list(runtime.completed_paper_records(
        client([pricing(1.1000), pricing(1.1021, NOW + timedelta(minutes=5))]),
        cycles=2, reviewer_identity="Anthony", runtime_path=tmp_path / "active.json",
        now=lambda: next(moments), sleep=lambda _seconds: None, telemetry_output_root=tmp_path,
    ))
    close_records = [item for item in captured if item.get("cycle_action") == "PAPER_SESSION_CLOSE"]
    assert len(close_records) == 1
    close = close_records[0]
    assert close["paper_session_event"] == "CLOSE"
    assert close["exit_reason"] == "paper_target"
    assert close["risk_amount"] > 0
    assert close["planned_reward_risk"] == pytest.approx(1.5)
    assert close["realized_paper_pl"] > 0
    assert close["realized_r"] == pytest.approx(close["realized_paper_pl"] / close["risk_amount"])
    assert close["roi_class"] == "POSITIVE_R"


def test_no_signal_stops_without_manufacturing_trade(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "build_signal_state", lambda *_args, **_kwargs: {"status": "NO_SIGNAL"})
    result = list(runtime.completed_paper_records(
        client([pricing(1.1), pricing(1.1)]), cycles=2, reviewer_identity="Anthony",
        runtime_path=tmp_path / "active.json", now=lambda: NOW, sleep=lambda _seconds: None,
    ))
    assert result == [CampaignWait(1, 2), CampaignWait(2, 2), CampaignHalt("OWNER_SESSION_CYCLE_LIMIT")]
    assert not (tmp_path / "active.json").exists()


def test_multiple_no_signals_can_be_followed_by_valid_paper_trade(monkeypatch, tmp_path):
    decisions = iter([
        {"status": "NO_SIGNAL"}, {"status": "NO_SIGNAL"},
        {"status": "BUY", "signal_id": "later-signal", "strategy_id": "sprint-4",
         "stop_price": 1.099, "target_price": 1.102},
        {"status": "NO_SIGNAL"},
    ])
    monkeypatch.setattr(runtime, "build_signal_state", lambda *_args, **_kwargs: next(decisions))
    moments = iter([
        NOW, NOW, NOW, NOW, NOW, NOW,
        NOW + timedelta(minutes=5), NOW + timedelta(minutes=5),
    ])
    prices = [pricing(1.1), pricing(1.1), pricing(1.1)] + [
        pricing(1.1021, NOW + timedelta(minutes=5))
    ]
    result = list(runtime.completed_paper_records(
        client(prices), cycles=4, reviewer_identity="Anthony",
        runtime_path=tmp_path / "active.json", now=lambda: next(moments),
        sleep=lambda _seconds: None,
    ))
    assert result[:2] == [CampaignWait(1, 4), CampaignWait(2, 4)]
    assert result[2]["evidence_type"] == "paper"
    assert result[2]["realized_pl"] > 0
    assert result[-1] == CampaignHalt("OWNER_SESSION_CYCLE_LIMIT")


def test_288_no_signal_cycles_are_bounded(monkeypatch, tmp_path):
    def no_signal_capture(*_args, **kwargs):
        assert callable(kwargs.get("pricing_now"))
        return {"status": "NO_SIGNAL"}, {"ask": 1.1}

    monkeypatch.setattr(runtime, "_capture", no_signal_capture)
    sleeps = []
    result = list(runtime.completed_paper_records(
        client([]), cycles=288, reviewer_identity="Anthony",
        runtime_path=tmp_path / "active.json", now=lambda: NOW, sleep=sleeps.append,
    ))
    assert len([item for item in result if isinstance(item, CampaignWait)]) == 288
    assert result[-1] == CampaignHalt("OWNER_SESSION_CYCLE_LIMIT")
    assert len(sleeps) == 287


@pytest.mark.parametrize(("callback", "reason"), [
    ("owner_cancelled", "OWNER_CANCELLATION"),
    ("kill_switch_active", "KILL_SWITCH_ACTIVE"),
    ("risk_halt_active", "RISK_HALT"),
])
def test_runtime_control_halts_are_immediate(tmp_path, callback, reason):
    kwargs = {callback: lambda: True}
    result = list(runtime.completed_paper_records(
        client([]), cycles=288, reviewer_identity="Anthony",
        runtime_path=tmp_path / "active.json", sleep=lambda _seconds: None, **kwargs,
    ))
    assert result == [CampaignHalt(reason)]


def test_practice_data_failure_halts_fail_closed(monkeypatch, tmp_path):
    def unavailable_capture(*_args, **kwargs):
        assert callable(kwargs.get("pricing_now"))
        raise runtime.OandaReadOnlyClientError("NETWORK_ERROR_SANITIZED")

    monkeypatch.setattr(runtime, "_capture", unavailable_capture)
    result = list(runtime.completed_paper_records(
        client([]), cycles=1, reviewer_identity="Anthony",
        runtime_path=tmp_path / "active.json", now=lambda: NOW,
        sleep=lambda _seconds: None,
    ))
    waits = [item for item in result if isinstance(item, CampaignWait)]
    assert waits == [CampaignWait(
        1,
        1,
        action=runtime.WAIT_FOR_DATA,
        observed_at_utc=runtime._stamp(NOW),
        rejection_reasons=("data_unavailable",),
    )]
    assert result[-1] == CampaignHalt("OWNER_SESSION_CYCLE_LIMIT")
    assert not any(isinstance(item, dict) for item in result)


def test_stale_data_waits_and_campaign_remains_bounded(tmp_path):
    stale_now = NOW + timedelta(hours=1)
    result = list(runtime.completed_paper_records(
        client([pricing(1.1)]), cycles=1, reviewer_identity="Anthony",
        runtime_path=tmp_path / "active.json", now=lambda: stale_now, sleep=lambda _seconds: None,
    ))
    assert result == [CampaignWait(
        1, 1, action=runtime.WAIT_FOR_DATA,
        observed_at_utc=runtime._stamp(stale_now),
        rejection_reasons=("stale_history",),
    ), CampaignHalt("OWNER_SESSION_CYCLE_LIMIT")]


@pytest.mark.parametrize("reason", ["stale_history", "stale_snapshot"])
def test_transient_stale_data_continues_and_records_sanitized_cycle(
    monkeypatch, tmp_path, reason
):
    outcomes = iter([ValueError(reason), ({"status": "NO_SIGNAL"}, {"bid": 1.1, "ask": 1.1002})])

    def injected_capture(*_args, **_kwargs):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(runtime, "_capture", injected_capture)
    result = list(runtime.completed_paper_records(
        client([]), cycles=2, reviewer_identity="Anthony",
        runtime_path=tmp_path / "active.json", now=lambda: NOW,
        sleep=lambda _seconds: None,
    ))
    assert result[0].action == runtime.WAIT_FOR_DATA
    assert result[0].rejection_reason == reason
    assert result[1].action == "WAIT_FOR_NEXT_CYCLE"
    assert result[-1] == CampaignHalt("OWNER_SESSION_CYCLE_LIMIT")
    lines = (tmp_path / "AIOS_FOREX_SUPERTREND_CYCLE_PROVENANCE.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(lines) == 2
    assert all("api_token" not in line and "account_id" not in line for line in lines)


def test_runtime_is_practice_get_only_and_safety_flags_false():
    state = runtime.runtime_safety_state()
    assert state["environment"] == "PRACTICE"
    assert state["http_methods"] == ["GET"]
    assert state["maximum_open_paper_positions"] == 1
    assert all(value is False for key, value in state.items() if key.endswith("performed") or key.endswith("persisted"))


def test_live_transport_and_unbounded_cycles_are_rejected(tmp_path):
    live = OandaReadOnlyClient(api_token="x", account_id="x", environment="live")
    with pytest.raises(ValueError, match="practice_environment"):
        list(runtime.completed_paper_records(live, cycles=1, reviewer_identity="Anthony", runtime_path=tmp_path/"x", sleep=lambda _: None))
    with pytest.raises(ValueError, match="positive_cycle"):
        list(runtime.completed_paper_records(client([]), cycles=0, reviewer_identity="Anthony", runtime_path=tmp_path/"x", sleep=lambda _: None))


def test_resolve_signal_source_preserves_default_source():
    assert runtime.resolve_signal_source() == runtime.SPRINT_4_SIGNAL_SOURCE


def test_resolve_signal_source_requires_supertrend_gate_for_supertrend_source():
    with pytest.raises(ValueError, match="supertrend_paper_demo_only_confirmation_required"):
        runtime.resolve_signal_source(runtime.SUPERTREND_SIGNAL_SOURCE)


def test_resolve_signal_source_accepts_supertrend_with_demo_gate():
    assert runtime.resolve_signal_source(
        runtime.SUPERTREND_SIGNAL_SOURCE,
        supertrend_paper_demo_only=True,
    ) == runtime.SUPERTREND_SIGNAL_SOURCE


def test_resolve_signal_source_rejects_unknown_source():
    with pytest.raises(ValueError, match="unsupported_signal_source"):
        runtime.resolve_signal_source("invalid")


def test_supertrend_lock_acquisition_and_release_in_tmp_directory(tmp_path):
    lock_path = tmp_path / "isolated.supertrend.paper.runtime.lock"
    first = NOW
    assert runtime._read_lock_record(lock_path) is None
    owner = runtime._acquire_supertrend_lock(
        lock_path,
        now=first,
        pid=101,
        process_start_identity="pid-101",
        host_identity="test-host",
        boot_identity="boot-a",
        process_start_reader=lambda target: f"pid-{target}",
    )
    assert owner is not None
    assert lock_path.exists()
    try:
        record = runtime._read_lock_record(lock_path)
        assert record is not None
        assert record["status"] == "ACTIVE"
        assert record["pid"] == 101
    finally:
        runtime._release_supertrend_lock(lock_path, owner)
    assert not lock_path.exists()


def test_supertrend_lock_touches_heartbeat_for_owned_lock(tmp_path):
    lock_path = tmp_path / "isolated.supertrend.paper.runtime.lock"
    owner = runtime._acquire_supertrend_lock(
        lock_path,
        now=NOW,
        pid=101,
        process_start_identity="pid-101",
        host_identity="test-host",
        boot_identity="boot-a",
        process_start_reader=lambda target: f"pid-{target}",
    )
    assert owner is not None
    try:
        assert runtime._touch_supertrend_lock(
            lock_path,
            owner,
            now=NOW + timedelta(minutes=1),
        ) is True
        record = runtime._read_lock_record(lock_path)
        assert record is not None
        assert record["heartbeat_at_utc"] == runtime._stamp(NOW + timedelta(minutes=1))
    finally:
        runtime._release_supertrend_lock(lock_path, owner)


def test_supertrend_lock_release_only_removes_owned_lock(tmp_path):
    lock_path = tmp_path / "isolated.supertrend.paper.runtime.lock"
    owner = runtime._acquire_supertrend_lock(
        lock_path,
        now=NOW,
        pid=101,
        process_start_identity="pid-101",
        host_identity="test-host",
        boot_identity="boot-a",
        process_start_reader=lambda target: f"pid-{target}",
    )
    assert owner is not None
    wrong_owner = replace(owner, lock_id=str(uuid.uuid4()))
    assert runtime._release_supertrend_lock(lock_path, wrong_owner) is False
    assert lock_path.exists()
    assert runtime._release_supertrend_lock(lock_path, owner) is True


def test_supertrend_lock_double_acquire_returns_false_for_active_lock(tmp_path):
    lock_path = tmp_path / "isolated.supertrend.paper.runtime.lock"
    owner = runtime._acquire_supertrend_lock(
        lock_path,
        now=NOW,
        pid=101,
        process_start_identity="pid-101",
        host_identity="test-host",
        boot_identity="boot-a",
        process_start_reader=lambda target: f"pid-{target}",
    )
    assert owner is not None
    try:
        original_record = runtime._read_lock_record(lock_path)
        assert original_record is not None
        assert runtime._acquire_supertrend_lock(
            lock_path,
            now=NOW,
            pid=202,
            process_start_identity="pid-202",
            host_identity="test-host",
            boot_identity="boot-a",
            process_start_reader=lambda target: f"pid-{target}",
        ) is None
        assert runtime._read_lock_record(lock_path) == original_record
    finally:
        runtime._release_supertrend_lock(lock_path, owner)


def test_legacy_live_owner_remains_blocking(tmp_path):
    lock_path = tmp_path / "isolated.supertrend.paper.runtime.lock"
    _write_legacy_lock(lock_path)

    assert runtime._acquire_supertrend_lock(
        lock_path,
        now=NOW,
        pid=202,
        process_start_identity="pid-202",
        host_identity="test-host",
        boot_identity="boot-a",
        process_start_reader=lambda _pid: "legacy-live",
    ) is None
    assert runtime._read_lock_record(lock_path)["owner"] == "legacy-owner"


def test_legacy_dead_owner_is_recovered_and_upgraded(tmp_path):
    lock_path = tmp_path / "isolated.supertrend.paper.runtime.lock"
    _write_legacy_lock(lock_path, heartbeat=NOW - timedelta(hours=1))

    def missing(_pid):
        raise ProcessLookupError

    owner = runtime._acquire_supertrend_lock(
        lock_path,
        now=NOW,
        pid=202,
        process_start_identity="pid-202",
        host_identity="test-host",
        boot_identity="boot-a",
        process_start_reader=missing,
    )
    assert owner is not None
    try:
        record = runtime._read_lock_record(lock_path)
        assert record is not None
        assert set(record) == {
            "schema",
            "version",
            "status",
            "lock_id",
            "pid",
            "process_start_identity",
            "host_identity",
            "boot_identity",
            "acquired_at_utc",
            "heartbeat_at_utc",
            "expires_at_utc",
            "campaign_identity",
            "source_fingerprint",
        }
        assert record["pid"] == 202
    finally:
        runtime._release_supertrend_lock(lock_path, owner)


def test_malformed_legacy_lock_remains_blocked(tmp_path):
    lock_path = tmp_path / "isolated.supertrend.paper.runtime.lock"
    _write_legacy_lock(lock_path, status="INACTIVE")

    with pytest.raises(ValueError, match="RUNTIME_LOCK_METADATA_INVALID"):
        runtime._acquire_supertrend_lock(
            lock_path,
            now=NOW,
            pid=202,
            process_start_identity="pid-202",
            host_identity="test-host",
            boot_identity="boot-a",
            process_start_reader=lambda _pid: "legacy-live",
        )
    assert lock_path.exists()


def test_upgraded_legacy_lock_can_be_read_repeatedly(tmp_path):
    lock_path = tmp_path / "isolated.supertrend.paper.runtime.lock"
    _write_legacy_lock(lock_path, heartbeat=NOW - timedelta(hours=1))

    def missing(_pid):
        raise ProcessLookupError

    owner = runtime._acquire_supertrend_lock(
        lock_path,
        now=NOW,
        pid=202,
        process_start_identity="pid-202",
        host_identity="test-host",
        boot_identity="boot-a",
        process_start_reader=missing,
    )
    assert owner is not None
    try:
        first = runtime._read_lock_record(lock_path)
        second = runtime._read_lock_record(lock_path)
        assert first == second
        assert first["lock_id"] == owner.lock_id
    finally:
        runtime._release_supertrend_lock(lock_path, owner)


def test_legacy_lock_cannot_be_released_by_replacement_owner(tmp_path):
    lock_path = tmp_path / "isolated.supertrend.paper.runtime.lock"
    _write_legacy_lock(lock_path)
    replacement = runtime.RuntimeLockOwnership(
        schema=runtime.SUPER_TREND_LOCK_SCHEMA,
        lock_id=str(uuid.uuid4()),
        pid=202,
        process_start_identity="pid-202",
        host_identity="test-host",
        boot_identity="boot-a",
        campaign_identity=runtime.SUPER_TREND_LOCK_CAMPAIGN_IDENTITY,
        source_fingerprint="a" * 64,
    )

    assert runtime._release_supertrend_lock(lock_path, replacement) is False
    assert lock_path.exists()


def test_supertrend_inner_lock_exception_path_releases_owner(monkeypatch, tmp_path):
    lock_path = tmp_path / "isolated.supertrend.paper.runtime.lock"
    owner = runtime.RuntimeLockOwnership(
        schema=runtime.SUPER_TREND_LOCK_SCHEMA,
        lock_id=str(uuid.uuid4()),
        pid=101,
        process_start_identity="pid-101",
        host_identity="test-host",
        boot_identity="boot-a",
        campaign_identity=runtime.SUPER_TREND_LOCK_CAMPAIGN_IDENTITY,
        source_fingerprint="a" * 64,
    )
    released = []
    monkeypatch.setattr(runtime, "_acquire_supertrend_lock", lambda *_args, **_kwargs: owner)
    monkeypatch.setattr(
        runtime,
        "_release_supertrend_lock",
        lambda path, selected: released.append((path, selected)) or True,
    )
    monkeypatch.setattr(runtime, "_touch_supertrend_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        runtime,
        "_capture",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("SANITIZED_CAPTURE_FAILURE")),
    )
    with pytest.raises(RuntimeError, match="SANITIZED_CAPTURE_FAILURE"):
        list(
            runtime.completed_paper_records(
                client([]),
                cycles=1,
                reviewer_identity="Anthony",
                runtime_path=tmp_path / "active.json",
                runtime_lock_path=lock_path,
                now=lambda: NOW,
                sleep=lambda _seconds: None,
                signal_source=runtime.SUPERTREND_SIGNAL_SOURCE,
                supertrend_paper_demo_only=True,
            )
        )
    assert released == [(lock_path, owner)]


def test_supertrend_inner_lock_preserves_practice_get_only_boundary():
    state = runtime.runtime_safety_state(
        runtime.SUPERTREND_SIGNAL_SOURCE,
        supertrend_paper_demo_only=True,
    )
    assert state["environment"] == "PRACTICE"
    assert state["http_methods"] == ["GET"]
    assert state["broker_write_performed"] is False
    assert state["practice_order_performed"] is False
    assert state["live_trade_performed"] is False
