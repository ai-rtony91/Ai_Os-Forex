from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from automation.orchestration.self_development.aios_autonomous_forex_research_pipeline import (
    APPROVAL,
    SCHEMA,
    build_autonomous_forex_research_run_result,
)


def _payload(**overrides: object) -> dict:
    payload = {
        "generated_utc": "2026-06-13T00:00:00Z",
        "repo_state": {
            "branch": "feature/approved-autonomy-worker-launch-forex-research-v1",
            "expected_branch": "feature/approved-autonomy-worker-launch-forex-research-v1",
            "dirty": False,
        },
        "mode": "DRY_RUN",
        "human_owner_research_approval": APPROVAL,
        "research_mode": "PLAN_ONLY",
        "pair": "EURUSD",
        "timeframe": "M5",
        "strategy_profile": "BASELINE_CONFLUENCE",
        "backtest_window": "SYNTHETIC_30D",
        "soak_cycles": 3,
        "max_runtime_minutes": 30,
        "write_ledger": False,
    }
    payload.update(overrides)
    return payload


def _result(**overrides: object) -> dict:
    return build_autonomous_forex_research_run_result(_payload(**overrides))


def test_missing_human_owner_research_approval_blocks_apply() -> None:
    result = _result(mode="APPLY", human_owner_research_approval="")

    assert result["schema"] == SCHEMA
    assert result["safety"]["status"] == "BLOCKED"
    assert "HUMAN_OWNER_RESEARCH_APPROVAL_MISSING" in result["stop_conditions"]
    assert "human_owner_research_approval" in result["approval_state"]["missing_requirements"]


def test_plan_only_returns_plan_without_live_data() -> None:
    result = _result(research_mode="PLAN_ONLY")

    assert result["research_plan"]["live_trading_blocked"] is True
    assert result["data_source"] == "SYNTHETIC_LOCAL_FIXTURE_ONLY"
    assert result["safety"]["uses_live_market_data"] is False


def test_backtest_stub_uses_synthetic_deterministic_data() -> None:
    one = _result(research_mode="BACKTEST_STUB")
    two = _result(research_mode="BACKTEST_STUB")

    assert one["backtest_result"] == two["backtest_result"]
    assert one["backtest_result"]["trade_count"] == 10
    assert one["backtest_result"]["valid_for_live_trading"] is False


def test_replay_stub_uses_synthetic_deterministic_data() -> None:
    result = _result(research_mode="REPLAY_STUB")

    assert result["replay_result"]["replay_status"] == "PASS"
    assert result["replay_result"]["events_replayed"] > 0
    assert result["replay_result"]["valid_for_live_trading"] is False


def test_soak_stub_runs_bounded_cycles() -> None:
    result = _result(research_mode="SOAK_STUB", soak_cycles=3)

    assert result["soak_result"]["cycles_requested"] == 3
    assert result["soak_result"]["cycles_completed"] == 3
    assert result["soak_result"]["stability_status"] == "PASS"


def test_full_local_research_stub_runs_sequence() -> None:
    result = _result(research_mode="FULL_LOCAL_RESEARCH_STUB")

    assert result["research_plan"]
    assert result["backtest_result"]["trade_count"] == 10
    assert result["replay_result"]["replay_status"] == "PASS"
    assert result["soak_result"]["cycles_completed"] == 3


def test_invalid_pair_blocks() -> None:
    result = _result(pair="BTCUSD")

    assert result["safety"]["status"] == "BLOCKED"
    assert "INVALID_PAIR" in result["stop_conditions"]


def test_invalid_timeframe_blocks() -> None:
    result = _result(timeframe="M2")

    assert result["safety"]["status"] == "BLOCKED"
    assert "INVALID_TIMEFRAME" in result["stop_conditions"]


def test_live_oanda_broker_webhook_or_order_request_blocks() -> None:
    for token in ("oanda", "broker", "webhook", "orders", "live_trading", "secret", ".env"):
        result = _result(strategy_profile=f"BASELINE_{token}")
        assert result["safety"]["status"] == "BLOCKED"
        assert "PROTECTED_LIVE_OR_SECRET_BOUNDARY" in result["stop_conditions"]


def test_valid_for_live_trading_is_always_false() -> None:
    result = _result(research_mode="FULL_LOCAL_RESEARCH_STUB")

    assert result["safety"]["valid_for_live_trading"] is False
    assert result["backtest_result"]["valid_for_live_trading"] is False
    assert result["replay_result"]["valid_for_live_trading"] is False
    assert result["soak_result"]["valid_for_live_trading"] is False


def test_no_secrets_env_network_or_broker_calls() -> None:
    safety = _result(research_mode="FULL_LOCAL_RESEARCH_STUB")["safety"]

    assert safety["touches_secrets_or_env"] is False
    assert safety["uses_network"] is False
    assert safety["broker_or_live_trading"] is False


def test_apply_writes_only_run_ledger_when_approved(tmp_path: Path) -> None:
    result = _result(
        mode="APPLY",
        research_mode="FULL_LOCAL_RESEARCH_STUB",
        output_root=str(tmp_path / "ledger"),
        repo_root=str(tmp_path),
        write_ledger=True,
    )

    assert result["safety"]["status"] == "PASS"
    assert result["run_ledger"]["written"] is True
    assert result["safety"]["writes_only_approved_run_ledger"] is True


@pytest.mark.parametrize("wire_encoding", ["utf-8", "utf-8-sig"])
def test_cli_decodes_utf8_payload_independently_of_process_locale(wire_encoding: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    pipeline = repo_root / "automation/orchestration/self_development/aios_autonomous_forex_research_pipeline.py"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    env["PYTHONIOENCODING"] = "ascii"
    payload_bytes = json.dumps(_payload(strategy_profile="CAFÉ"), ensure_ascii=False).encode(wire_encoding)

    result = subprocess.run(
        [sys.executable, str(pipeline)],
        cwd=repo_root,
        input=payload_bytes,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode("ascii", errors="replace")
    parsed = json.loads(result.stdout)
    assert parsed["strategy_profile"] == "CAFÉ"
    assert parsed["run_ledger"]["written"] is False
    assert parsed["safety"]["valid_for_live_trading"] is False
