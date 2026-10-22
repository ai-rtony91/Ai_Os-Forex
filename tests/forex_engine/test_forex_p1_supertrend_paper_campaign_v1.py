from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.forex_delivery.run_forex_p1_supertrend_paper_campaign_v1 import (
    ATR_PERIOD,
    CAMPAIGN_ID,
    MODE,
    MULTIPLIER,
    OUTPUT_NAMES,
    REQUIRED_QUALIFYING_TRADES,
    STRATEGY_NAME,
    run_supertrend_campaign,
    validate_supertrend_records,
)

ROOT = Path(__file__).resolve().parents[2]


def trade(number: int, *, week_offset: int = 0, pnl: float = 10.0) -> dict:
    opened = datetime(2026, 8, 3, 10, tzinfo=timezone.utc) + timedelta(
        weeks=week_offset, minutes=number * 2
    )
    closed = opened + timedelta(minutes=1)
    return {
        "trade_id": f"supertrend-{number:03d}",
        "evidence_type": "paper",
        "strategy_id": STRATEGY_NAME,
        "strategy_name": STRATEGY_NAME,
        "strategy_config": {"atr_period": ATR_PERIOD, "multiplier": MULTIPLIER},
        "mode": MODE,
        "paper_only": True,
        "instrument": "EUR_USD",
        "direction": "buy",
        "entry_timestamp_utc": opened.isoformat(),
        "exit_timestamp_utc": closed.isoformat(),
        "entry_price": 1.1000,
        "exit_price": 1.1010 if pnl >= 0 else 1.0990,
        "stop_price": 1.0990,
        "target_price": 1.1020,
        "quantity_or_units": 100,
        "realized_pl": pnl,
        "fees": 0,
        "risk_amount": 10,
        "exit_reason": "paper_target" if pnl >= 0 else "paper_stop",
        "entry_rationale": "canonical supertrend pullback paper fixture",
        "evidence_source": "offline_supertrend_replay_fixture",
        "reviewed_by": "human_owner",
        "review_timestamp_utc": closed.isoformat(),
        "broker_call_performed": False,
        "broker_write_performed": False,
        "practice_order_performed": False,
        "live_trade_performed": False,
        "money_movement_performed": False,
        "credentials_loaded": False,
        "credentials_persisted": False,
        "network_access_performed": False,
    }


def test_canonical_campaign_identity_and_dry_run_validation_do_not_write(tmp_path: Path):
    output_root = tmp_path / "must-not-exist"
    result = validate_supertrend_records([trade(1)])

    assert result["campaign_id"] == CAMPAIGN_ID
    assert result["strategy_name"] == STRATEGY_NAME == "supertrend_pullback_v1"
    assert result["atr_period"] == ATR_PERIOD == 3
    assert result["multiplier"] == MULTIPLIER == 2.0
    assert result["required_qualifying_trades"] == REQUIRED_QUALIFYING_TRADES == 30
    assert result["mode"] == MODE == "PAPER_ONLY"
    assert result["paper_only"] is True
    assert result["validation_status"] == "PASS"
    assert result["writes_performed"] == 0
    assert not output_root.exists()


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"strategy_name": "generic_p1", "strategy_id": "generic_p1"}, "canonical_strategy_name_required"),
        ({"strategy_config": {"atr_period": 10, "multiplier": 3.0}}, "canonical_atr_period_3_required"),
        ({"strategy_config": {"atr_period": 3, "multiplier": 3.0}}, "canonical_multiplier_2_required"),
        ({"paper_only": False}, "paper_only_true_required"),
        ({"live_trade_performed": True}, "forbidden_live_trade_performed"),
    ],
)
def test_noncanonical_or_executable_records_fail_closed(mutation: dict, reason: str):
    record = {**trade(1), **mutation}
    result = validate_supertrend_records([record])
    assert result["validation_status"] == "BLOCKED"
    assert any(reason in blocker for blocker in result["blockers"])


def test_invalid_records_create_no_campaign_outputs(tmp_path: Path):
    record = {**trade(1), "paper_only": False}
    output_root = tmp_path / "blocked"

    with pytest.raises(ValueError, match="supertrend_campaign_validation_blocked"):
        run_supertrend_campaign([record], output_root, repository_root=ROOT, output=io.StringIO())

    assert not output_root.exists()


def test_30_trade_campaign_and_weekly_evidence_are_dedicated_and_complete(tmp_path: Path):
    records = [
        trade(number, week_offset=0 if number <= 15 else 1, pnl=10.0 if number % 3 else -5.0)
        for number in range(1, 31)
    ]
    output_root = tmp_path / "supertrend-campaign"

    state = run_supertrend_campaign(
        records,
        output_root,
        repository_root=ROOT,
        output=io.StringIO(),
    )

    assert state["campaign_id"] == CAMPAIGN_ID
    assert state["strategy_name"] == STRATEGY_NAME
    assert state["qualifying_trades"] == state["accepted_qualifying_trades"] == 30
    assert state["required_qualifying_trades"] == 30
    assert state["thirty_trade_campaign_status"] == "COMPLETE"
    assert state["weekly_evidence_status"] == "COMPLETE"
    assert len(state["weekly_evidence"]) == 2
    assert sum(row["qualifying_trades"] for row in state["weekly_evidence"]) == 30
    assert state["active_position_status"] == "NONE"
    assert state["validation_status"] == "PASS"
    assert state["runtime_launch_status"] == "NOT_LAUNCHED"
    assert state["commit_status"] == "NO_REPO_ACTION_BY_CAMPAIGN"
    assert state["files_changed"] == []
    assert state["tests_run"] == []
    assert state["separate_from_generic_p1"] is True
    assert state["generic_p1_campaign_state_mutated"] is False

    ledger = json.loads((output_root / OUTPUT_NAMES["ledger"]).read_text(encoding="utf-8"))
    assert len(ledger["records"]) == 30
    assert all(record["strategy_id"] == STRATEGY_NAME for record in ledger["records"])
    assert not any(path.name.startswith("AIOS_FOREX_P1_30_TRADE") for path in output_root.iterdir())

    weekly = (output_root / OUTPUT_NAMES["weekly_report"]).read_text(encoding="utf-8")
    assert "QUALIFYING_TRADES: 30/30" in weekly
    assert "No runtime or broker action is authorized" in weekly


def test_campaign_runner_has_no_broker_network_credential_or_worker_import_path():
    source = (
        ROOT / "scripts/forex_delivery/run_forex_p1_supertrend_paper_campaign_v1.py"
    ).read_text(encoding="utf-8")
    forbidden_imports = (
        "OandaReadOnlyClient",
        "import requests",
        "from requests",
        "import urllib",
        "import subprocess",
        "import os",
        "import time",
    )
    assert all(value not in source for value in forbidden_imports)
