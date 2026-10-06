from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from automation.forex_engine.forex_p1_supervised_paper_campaign_v1 import (
    CampaignHalt, CampaignPaths, CampaignWait, LONG_RUN_LIMITS, MAX_OPEN_PAPER_POSITIONS,
    SAFETY_FLAGS, SUPERTREND_REJECTION_REASONS, TARGET_QUALIFYING_TRADES,
    WAIT_FOR_DATA, WAITING_FOR_NEXT_RUN, latest_paper_blocker_classification, run_campaign,
)
from automation.forex_engine.strategies import SUPERTREND_PULLBACK_V1
from scripts.forex_delivery import run_forex_p1_supervised_paper_campaign_v1 as runtime_script

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def paths(tmp_path: Path) -> CampaignPaths:
    return CampaignPaths(*(tmp_path / name for name in (
        "candidate.json", "ledger.json", "replay-state.json", "replay.md",
        "events.jsonl", "campaign-state.json", "campaign.md",
    )))


def trade(number: int, pnl: float = 10.0) -> dict:
    opened = datetime(2026, 8, 10, 10, tzinfo=timezone.utc) + timedelta(minutes=number * 2)
    closed = opened + timedelta(minutes=1)
    direction = "buy"
    return {
        "trade_id": f"campaign-{number:03d}", "evidence_type": "paper",
        "strategy_id": "strategy-c1", "instrument": "EUR_USD", "direction": direction,
        "entry_timestamp_utc": opened.isoformat(), "exit_timestamp_utc": closed.isoformat(),
        "entry_price": 1.1, "exit_price": 1.101 if pnl >= 0 else 1.099,
        "stop_price": 1.099, "target_price": 1.101, "quantity_or_units": 100,
        "realized_pl": pnl, "fees": 0, "risk_amount": 10,
        "exit_reason": "paper_target" if pnl >= 0 else "paper_stop",
        "entry_rationale": "fresh supervised paper strategy signal",
        "evidence_source": "long_run_paper_supervisor", "reviewed_by": "human_owner",
        "review_timestamp_utc": closed.isoformat(),
    }


def run(records, paths, **kwargs):
    output = io.StringIO()
    result = run_campaign(records, paths, repository_root=ROOT, output=output, **kwargs)
    return result, output.getvalue()


def active_session_payload(**overrides):
    payload = {
        "status": "ACTIVE",
        "candidate_id": "p1-runtime-test-candidate",
        "strategy_name": SUPERTREND_PULLBACK_V1,
        "instrument": "EUR_USD",
        "direction": "BUY",
        "entry_timestamp": "2026-08-18T13:39:24.520656351Z",
        "entry_price": 1.15834,
        "stop_price": 1.15693,
        "target_price": 1.16011,
        "units": 100,
    }
    payload.update(overrides)
    return payload


def test_active_runtime_session_projects_without_counting_a_trade(paths, tmp_path):
    active = tmp_path / "active.json"
    active.write_text(json.dumps(active_session_payload()), encoding="utf-8")
    state, _ = run([], paths, active_session_path=active)
    assert state["active_position_status"] == "ACTIVE"
    assert state["active_position"]["candidate_id"] == "p1-runtime-test-candidate"
    assert state["active_position"]["entry_timestamp_new_york"].startswith(
        "2026-08-18T09:39:24"
    )
    assert state["active_position"]["entry_timestamp_utc"].startswith(
        "2026-08-18T13:39:24"
    )
    assert state["accepted_qualifying_trades"] == 0
    assert "ACTIVE_POSITION_STATUS: ACTIVE" in paths.campaign_report.read_text()


def test_missing_closed_and_invalid_active_sessions_fail_closed(paths, tmp_path):
    missing, _ = run([], paths, active_session_path=tmp_path / "missing.json")
    assert missing["active_position_status"] == "NONE"
    closed = tmp_path / "closed.json"
    closed.write_text(json.dumps(active_session_payload(status="CLOSED")), encoding="utf-8")
    state, _ = run([], paths, active_session_path=closed)
    assert state["active_position_status"] == "NONE"
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(active_session_payload(target_price=None)), encoding="utf-8")
    with pytest.raises(ValueError, match="active_paper_session_incomplete"):
        run([], paths, active_session_path=invalid)


def test_campaign_reuses_long_run_limit_and_is_one_at_a_time(paths):
    assert TARGET_QUALIFYING_TRADES == LONG_RUN_LIMITS["max_session_trades"] == 30
    assert MAX_OPEN_PAPER_POSITIONS == 1
    observed = []
    def candidates():
        for number in range(1, 3):
            if paths.campaign_state.exists():
                observed.append(json.loads(paths.campaign_state.read_text())["active_position"])
            yield trade(number)
    state, _ = run(candidates(), paths)
    assert state["accepted_qualifying_trades"] == 2
    assert state["campaign_status"] == WAITING_FOR_NEXT_RUN
    assert state["stop_reason"] is None
    assert state["completed_utc"] is None
    assert state["active_position"] is None
    assert all(item is None for item in observed)


def test_stops_at_30_and_never_consumes_31st(paths):
    consumed = []
    def candidates():
        for number in range(1, 32):
            consumed.append(number)
            yield trade(number)
    state, output = run(candidates(), paths)
    assert state["stop_reason"] == "TARGET_REACHED"
    assert state["campaign_status"] == "COMPLETE"
    assert state["completed_utc"] is not None
    assert state["accepted_qualifying_trades"] == 30
    assert consumed == list(range(1, 31))
    assert "TRADE: 30/30" in output
    assert state["p1_status"] == "REQUIRE_MORE_EVIDENCE"


def test_30_supertrend_records_are_counted_in_a_separate_strategy_ledger(paths, tmp_path):
    generic_state, _ = run([trade(1)], paths)
    supertrend_paths = CampaignPaths(*(tmp_path / f"supertrend-{name}" for name in (
        "candidate.json", "ledger.json", "replay-state.json", "replay.md",
        "events.jsonl", "campaign-state.json", "campaign.md",
    )))
    records = [
        {
            **trade(number),
            "strategy_id": SUPERTREND_PULLBACK_V1,
            "strategy_name": SUPERTREND_PULLBACK_V1,
            "mode": "PAPER_ONLY",
            "paper_only": True,
            "strategy_config": {"atr_period": 3, "multiplier": 2.0},
        }
        for number in range(1, 31)
    ]

    supertrend_state, _ = run(
        records,
        supertrend_paths,
        qualifying_strategy_name=SUPERTREND_PULLBACK_V1,
    )
    supertrend_ledger = json.loads(supertrend_paths.ledger.read_text(encoding="utf-8"))
    generic_ledger = json.loads(paths.ledger.read_text(encoding="utf-8"))

    assert generic_state["accepted_qualifying_trades"] == len(generic_ledger["records"]) == 1
    assert supertrend_state["stop_reason"] == "TARGET_REACHED"
    assert supertrend_state["accepted_qualifying_trades"] == 30
    assert supertrend_state["strategy_qualifying_trade_counts"] == {
        SUPERTREND_PULLBACK_V1: 30,
    }
    assert len(supertrend_ledger["records"]) == 30
    assert all(
        record["strategy_name"] == SUPERTREND_PULLBACK_V1
        for record in supertrend_ledger["records"]
    )


def test_extra_r_classification_fields_do_not_change_qualifying_credit(paths):
    state, _ = run(
        [
            {
                **trade(1),
                "planned_reward_risk": 2.0,
                "realized_r": 2.0,
                "roi_class": "POSITIVE_R",
            }
        ],
        paths,
    )
    assert state["accepted_qualifying_trades"] == 1
    assert state["trade_results"][0]["realized_paper_pl"] == 10.0


def test_strategy_qualified_campaign_rejects_mixed_strategy_record(paths):
    state, _ = run(
        [trade(1)],
        paths,
        qualifying_strategy_name=SUPERTREND_PULLBACK_V1,
    )
    assert state["stop_reason"] == "STRATEGY_MISMATCH_REJECTED"
    assert state["accepted_qualifying_trades"] == 0
    assert state["rejected_records"] == 1
    assert not paths.ledger.exists()


def test_no_signal_preserves_count(paths):
    state, _ = run([], paths)
    persisted = json.loads(paths.campaign_state.read_text(encoding="utf-8"))
    report = paths.campaign_report.read_text(encoding="utf-8")

    assert state["campaign_status"] == WAITING_FOR_NEXT_RUN
    assert state["stop_reason"] is None
    assert state["completed_utc"] is None
    assert state["accepted_qualifying_trades"] == 0
    assert persisted["campaign_status"] == WAITING_FOR_NEXT_RUN
    assert persisted["stop_reason"] is None
    assert persisted["completed_utc"] is None
    assert "- CAMPAIGN_STATUS: WAITING_FOR_NEXT_RUN" in report
    assert "- STOP_REASON: NONE" in report
    assert "- COMPLETED_UTC: NONE" in report
    assert "current owner-bounded paper/demo campaign is active" not in report


def test_no_signal_cycle_waits_without_evidence_or_count(paths):
    state, output = run([CampaignWait(1, 288), CampaignWait(2, 288)], paths)
    assert state["accepted_qualifying_trades"] == 0
    assert "latest_rejection_reason" not in state
    assert "rejection_reason_counts" not in state
    assert not paths.ledger.exists()
    assert "RUN AGE: " in output
    assert "NEXT CHECK ETA:" in output
    assert "NEXT CHECK IN:" in output
    assert "ACTIVE POSITION: NONE" in output
    assert output.count("ACTION: WAIT_FOR_NEXT_CYCLE") == 2
    assert "REJECTION REASON:" not in output
    assert "CYCLE: 2/288" in output


def test_supertrend_no_signal_reasons_are_persisted_counted_and_printed(paths):
    waits = [
        CampaignWait(
            1,
            3,
            rejection_reasons=(
                "pullback_not_confirmed",
                "volatility_filter_failed",
            ),
        ),
        CampaignWait(
            2,
            3,
            rejection_reasons=("pullback_not_confirmed",),
        ),
        CampaignHalt("OWNER_SESSION_CYCLE_LIMIT"),
    ]

    state, output = run(
        waits,
        paths,
        qualifying_strategy_name=SUPERTREND_PULLBACK_V1,
    )
    persisted = json.loads(paths.campaign_state.read_text(encoding="utf-8"))

    assert state["latest_rejection_reason"] == "pullback_not_confirmed"
    assert state["latest_rejection_reasons"] == ["pullback_not_confirmed"]
    assert state["rejection_reason_counts"] == {
        "pullback_not_confirmed": 2,
        "volatility_filter_failed": 1,
    }
    assert persisted["latest_rejection_reason"] == "pullback_not_confirmed"
    assert persisted["rejection_reason_counts"] == state["rejection_reason_counts"]
    assert "ACTION: WAIT_FOR_NEXT_CYCLE\nREJECTION REASON: pullback_not_confirmed\n" in output
    assert output.count("REJECTION REASON: pullback_not_confirmed") == 2
    assert "RUN AGE:" in output
    assert "NEXT CHECK ETA:" in output
    assert "NEXT CHECK IN:" in output
    assert state["campaign_status"] == "STOPPED"
    assert state["stop_reason"] == "OWNER_SESSION_CYCLE_LIMIT"
    assert state["completed_utc"] is not None
    assert state["accepted_qualifying_trades"] == 0
    assert not paths.ledger.exists()
    assert all(state[key] is False for key in SAFETY_FLAGS)


def test_campaign_wait_rejects_unknown_or_duplicate_reason_values():
    with pytest.raises(ValueError, match="unsupported_supertrend_rejection_reason"):
        CampaignWait(1, 1, rejection_reasons=("not_in_taxonomy",))
    with pytest.raises(ValueError, match="duplicate_supertrend_rejection_reason"):
        CampaignWait(
            1,
            1,
            rejection_reasons=("no_supertrend_flip", "no_supertrend_flip"),
        )
    assert len(SUPERTREND_REJECTION_REASONS) == 10


def test_rejection_telemetry_cannot_expand_into_default_campaign(paths):
    with pytest.raises(
        ValueError,
        match="supertrend_rejection_reason_requires_supertrend_campaign",
    ):
        run([
            CampaignWait(
                1,
                1,
                rejection_reasons=("unknown_no_signal",),
            )
        ], paths)
    assert not paths.campaign_state.exists()


def test_practice_data_unavailable_is_recorded_as_wait_for_data(paths):
    observed_at = "2026-08-10T10:30:00Z"
    state, output = run([
        CampaignWait(
            1,
            2,
            action=WAIT_FOR_DATA,
            observed_at_utc=observed_at,
            rejection_reasons=("data_unavailable",),
        ),
        CampaignHalt("OWNER_SESSION_CYCLE_LIMIT"),
    ], paths, qualifying_strategy_name=SUPERTREND_PULLBACK_V1)
    persisted = json.loads(paths.campaign_state.read_text(encoding="utf-8"))

    assert state["stop_reason"] == "OWNER_SESSION_CYCLE_LIMIT"
    assert state["stop_reason"] != "PRACTICE_DATA_UNAVAILABLE"
    assert state["campaign_status"] == "STOPPED"
    assert state["completed_utc"] is not None
    assert state["data_unavailable_count"] == 1
    assert state["last_data_unavailable_utc"] == observed_at
    assert state["last_action"] == WAIT_FOR_DATA
    assert persisted["data_unavailable_count"] == 1
    assert persisted["last_action"] == WAIT_FOR_DATA
    assert "ACTION: WAIT_FOR_DATA" in output
    assert latest_paper_blocker_classification(state) == "DATA_UNAVAILABLE"
    assert "LATEST_BLOCKER_CLASSIFICATION: DATA_UNAVAILABLE" in paths.campaign_report.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("waits", "expected_classification", "expected_latest_reason"),
    [
        (
            [
                CampaignWait(
                    1,
                    2,
                    action=WAIT_FOR_DATA,
                    observed_at_utc="2026-08-10T10:30:00Z",
                    rejection_reasons=("data_unavailable",),
                ),
                CampaignHalt("OWNER_SESSION_CYCLE_LIMIT"),
            ],
            "DATA_UNAVAILABLE",
            "data_unavailable",
        ),
        (
            [
                CampaignWait(
                    1,
                    2,
                    rejection_reasons=("pullback_not_confirmed",),
                ),
                CampaignHalt("OWNER_SESSION_CYCLE_LIMIT"),
            ],
            "MARKET_NOT_ELIGIBLE",
            "pullback_not_confirmed",
        ),
        (
            [
                CampaignWait(
                    1,
                    2,
                    rejection_reasons=("volatility_filter_failed",),
                ),
                CampaignHalt("OWNER_SESSION_CYCLE_LIMIT"),
            ],
            "MARKET_NOT_ELIGIBLE",
            "volatility_filter_failed",
        ),
        (
            [
                CampaignWait(
                    1,
                    2,
                    rejection_reasons=("pullback_not_confirmed",),
                ),
                CampaignWait(
                    2,
                    2,
                    action=WAIT_FOR_DATA,
                    observed_at_utc="2026-08-10T10:35:00Z",
                    rejection_reasons=("data_unavailable",),
                ),
                CampaignHalt("OWNER_SESSION_CYCLE_LIMIT"),
            ],
            "DATA_UNAVAILABLE",
            "data_unavailable",
        ),
    ],
)
def test_latest_paper_blocker_classification_distinguishes_wait_for_data_from_market_rejection(
    waits, expected_classification, expected_latest_reason, paths
):
    state, _ = run(
        waits,
        paths,
        qualifying_strategy_name=SUPERTREND_PULLBACK_V1,
    )
    report = paths.campaign_report.read_text(encoding="utf-8")

    assert latest_paper_blocker_classification(state) == expected_classification
    assert state["latest_rejection_reason"] == expected_latest_reason
    assert f"LATEST_BLOCKER_CLASSIFICATION: {expected_classification}" in report
    assert "HISTORICAL_SIGNAL_REJECTIONS:" in report


@pytest.mark.parametrize(("kwargs", "reason"), [
    ({"kill_switch_active": True}, "KILL_SWITCH_ACTIVE"),
    ({"risk_halt_active": True}, "RISK_HALT"),
])
def test_pretrade_halts(paths, kwargs, reason):
    state, _ = run([trade(1)], paths, **kwargs)
    assert state["stop_reason"] == reason
    assert state["campaign_status"] == "STOPPED"
    assert state["completed_utc"] is not None
    assert state["accepted_qualifying_trades"] == 0


def test_owner_cancellation_remains_terminal(paths):
    def candidates():
        yield trade(1)
        raise KeyboardInterrupt

    state, _ = run(candidates(), paths)

    assert state["campaign_status"] == "STOPPED"
    assert state["stop_reason"] == "OWNER_CANCELLATION"
    assert state["completed_utc"] is not None
    assert state["accepted_qualifying_trades"] == 1


def test_bounded_restart_repairs_trade_state_and_report_evidence(paths):
    qualifying_trade = {
        **trade(1, -0.11),
        "strategy_id": SUPERTREND_PULLBACK_V1,
        "strategy_name": SUPERTREND_PULLBACK_V1,
        "mode": "PAPER_ONLY",
        "paper_only": True,
        "strategy_config": {"atr_period": 3, "multiplier": 2.0},
    }
    first_state, _ = run(
        [
            qualifying_trade,
            CampaignWait(
                1,
                2,
                rejection_reasons=("pullback_not_confirmed",),
            ),
            CampaignHalt("OWNER_SESSION_CYCLE_LIMIT"),
        ],
        paths,
        qualifying_strategy_name=SUPERTREND_PULLBACK_V1,
    )
    broken_state = {
        **first_state,
        "campaign_status": "RUNNING",
        "stop_reason": None,
        "completed_utc": None,
        "current_trade_number": 0,
        "last_trade": None,
        "trade_results": [],
    }
    paths.campaign_state.write_text(
        json.dumps(broken_state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    state, _ = run(
        [
            CampaignWait(
                1,
                1,
                rejection_reasons=("volatility_filter_failed",),
            )
        ],
        paths,
        qualifying_strategy_name=SUPERTREND_PULLBACK_V1,
    )
    persisted = json.loads(paths.campaign_state.read_text(encoding="utf-8"))
    report = paths.campaign_report.read_text(encoding="utf-8")
    pnl_section = report.split("## PAPER_PNL_BY_TRADE", 1)[1].split(
        "All results are local PAPER P/L.",
        1,
    )[0]

    assert state["campaign_status"] == WAITING_FOR_NEXT_RUN
    assert state["stop_reason"] is None
    assert state["completed_utc"] is None
    assert state["accepted_qualifying_trades"] == 1
    assert state["current_trade_number"] == 1
    assert state["last_trade"] == state["trade_results"][-1]
    assert len(state["trade_results"]) == 1
    assert state["p1_status"] == "INSUFFICIENT_SAMPLE"
    assert state["latest_rejection_reason"] == "volatility_filter_failed"
    assert state["rejection_reason_counts"] == {
        "pullback_not_confirmed": 1,
        "volatility_filter_failed": 1,
    }
    assert persisted["trade_results"] == state["trade_results"]
    assert "- campaign-001: -0.11 PAPER P/L" in pnl_section
    assert "- NONE" not in pnl_section


def test_stale_market_data_halt_is_propagated(paths):
    state, _ = run([CampaignHalt("STALE_MARKET_DATA")], paths)
    assert state["stop_reason"] == "STALE_MARKET_DATA"
    assert state["accepted_qualifying_trades"] == 0


def test_duplicate_and_malformed_evidence_stop_fail_closed(paths):
    duplicate, _ = run([trade(1), trade(1)], paths)
    assert duplicate["stop_reason"] == "DUPLICATE_TRADE_ID_REJECTED"
    assert duplicate["accepted_qualifying_trades"] == 1
    other_paths = CampaignPaths(*(paths.campaign_state.parent / f"bad-{index}" for index in range(7)))
    malformed = trade(2)
    del malformed["strategy_id"]
    rejected, _ = run([malformed], other_paths)
    assert rejected["stop_reason"] == "EVIDENCE_VALIDATION_FAILED"
    assert rejected["rejected_records"] == 1


def test_metrics_progression_and_session_loss(paths):
    state, output = run([trade(1, -4), trade(2, -3), trade(3, 10)], paths, maximum_session_loss=7)
    assert state["stop_reason"] == "MAXIMUM_SESSION_LOSS_HIT"
    assert state["net_pl"] == -7
    assert state["profit_factor"] == 0
    assert state["maximum_drawdown"] == 7
    assert state["consecutive_losses"] == 2
    assert state["expectancy"] == -3.5
    assert "REALIZED PAPER P/L: -3.0" in output
    assert "MAX DRAWDOWN: 7.0" in output


def test_all_persisted_safety_flags_are_false(paths):
    state, _ = run([trade(1)], paths)
    persisted = json.loads(paths.campaign_state.read_text())
    assert all(state[key] is False and persisted[key] is False for key in SAFETY_FLAGS)
    assert not paths.candidate.exists()


def test_parser_defaults_to_sprint4_with_demo_flag_false():
    args = runtime_script.parser().parse_args([])
    assert args.signal_source == "sprint-4"
    assert args.supertrend_paper_demo_only is False
    assert args.output_root == runtime_script.REPORTS


def test_parser_accepts_supertrend_with_demo_gate():
    args = runtime_script.parser().parse_args([
        "--signal-source",
        "supertrend",
        "--supertrend-paper-demo-only",
    ])
    assert args.signal_source == "supertrend"
    assert args.supertrend_paper_demo_only is True


def test_explicit_supertrend_output_root_routes_every_artifact_outside_reports(
    tmp_path: Path,
):
    runtime_root = (
        tmp_path / ".aios" / "runtime" / "forex_p1_supertrend_paper_sessions"
    )

    paths = runtime_script.campaign_paths_for_signal_source(
        "supertrend", runtime_root
    )

    assert all(
        path.parent == runtime_root
        for path in (
            paths.candidate,
            paths.ledger,
            paths.replay_state,
            paths.replay_report,
            paths.event_log,
            paths.campaign_state,
            paths.campaign_report,
        )
    )
    assert all(
        runtime_script.REPORTS not in path.parents
        for path in (
            paths.candidate,
            paths.ledger,
            paths.replay_state,
            paths.replay_report,
            paths.event_log,
            paths.campaign_state,
            paths.campaign_report,
        )
    )


def test_parser_rejects_unsupported_signal_source():
    with pytest.raises(SystemExit):
        runtime_script.parser().parse_args(["--signal-source", "invalid"])


def test_main_rejects_supertrend_without_demo_confirmation_before_credentials(monkeypatch, capsys):
    monkeypatch.setattr(
        runtime_script,
        "_runtime_environment_value",
        lambda *_args: (_ for _ in ()).throw(AssertionError("credential access attempted")),
    )
    monkeypatch.setattr(
        runtime_script,
        "OandaReadOnlyClient",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("broker client constructed")),
    )
    monkeypatch.setattr(
        runtime_script,
        "completed_paper_records",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not launch")),
    )
    monkeypatch.setattr(
        runtime_script,
        "run_campaign",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not launch")),
    )
    assert runtime_script.main(["--owner-local-runtime", "--signal-source", "supertrend"]) == 2
    assert "supertrend_paper_demo_only_confirmation_required" in capsys.readouterr().out


def test_main_rejects_demo_confirmation_for_non_supertrend_source_before_credentials(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        runtime_script,
        "_runtime_environment_value",
        lambda *_args: (_ for _ in ()).throw(AssertionError("credential access attempted")),
    )
    monkeypatch.setattr(
        runtime_script,
        "OandaReadOnlyClient",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("broker client constructed")),
    )
    monkeypatch.setattr(
        runtime_script,
        "completed_paper_records",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not launch")),
    )
    monkeypatch.setattr(
        runtime_script,
        "run_campaign",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not launch")),
    )
    assert runtime_script.main([
        "--owner-local-runtime",
        "--signal-source",
        "sprint-4",
        "--supertrend-paper-demo-only",
    ]) == 2
    assert "supertrend_paper_demo_only_requires_supertrend_source" in capsys.readouterr().out


def test_main_default_supervised_path_is_unmodified(monkeypatch):
    captured = {}

    def fake_records(*_args, **kwargs):
        captured["signal_source"] = kwargs["signal_source"]
        captured["runtime_path"] = kwargs["runtime_path"]
        captured["cycles"] = kwargs["cycles"]
        return iter(())

    def fake_campaign(_candidates, paths, **_kwargs):
        captured["campaign_paths"] = paths
        return {"stop_reason": "OWNER_SESSION_CYCLE_LIMIT"}

    monkeypatch.setattr(runtime_script, "OandaReadOnlyClient", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime_script, "_runtime_environment_value", lambda *_args: "value")
    monkeypatch.setattr(runtime_script, "completed_paper_records", fake_records)
    monkeypatch.setattr(runtime_script, "run_campaign", fake_campaign)
    assert runtime_script.main(["--owner-local-runtime", "--reviewer", "Human Owner Anthony", "--cycles", "288"]) == 0
    assert captured["signal_source"] == "sprint-4"
    assert captured["runtime_path"] == runtime_script.SUPERVISED_PRACTICE_SESSION_PATH
    assert captured["cycles"] == 288
    assert captured["campaign_paths"].campaign_state.parent == runtime_script.REPORTS
