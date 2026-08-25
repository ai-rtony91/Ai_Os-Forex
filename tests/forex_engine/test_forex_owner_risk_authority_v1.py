from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from automation.forex_engine import forex_owner_risk_authority_v1 as authority


ROOT = Path(__file__).resolve().parents[2]


def test_direct_launch_bootstrap_imports_with_script_directory_only() -> None:
    script = ROOT / "automation/forex_engine/forex_owner_risk_authority_v1.py"
    probe = """
import runpy
import sys
from pathlib import Path

script = Path(sys.argv[1]).resolve()
repo_root = script.parents[2]
script_directory = script.parent
sys.path[:] = [str(script_directory)] + [
    entry
    for entry in sys.path
    if entry
    and Path(entry).resolve() not in {repo_root, script_directory}
]
runpy.run_path(str(script), run_name="__direct_launch_regression__")
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", probe, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "ModuleNotFoundError" not in completed.stderr
    assert "ImportError" not in completed.stderr


def _paper_hashes() -> dict[str, str]:
    return {
        "runtime": authority._sha256_file(authority.PAPER30_RUNTIME_PATH),
        "ledger": authority._sha256_file(authority.PAPER30_LEDGER_PATH),
        "state": authority._sha256_file(authority.PAPER30_STATE_PATH),
    }


def test_owner_authority_values_are_exact_and_safe() -> None:
    assert authority.MAX_RISK_PER_TRADE_PERCENT == 1.0
    assert authority.MAX_DAILY_LOSS_PERCENT == 2.0
    assert authority.MAX_OPEN_RISK_PERCENT == 1.0
    assert authority.MAX_OPEN_TRADES == 1
    assert authority.MAX_DRAWDOWN_PERCENT == 5.0
    assert authority.MAX_SPREAD_PIPS == 3.0
    assert authority.AUTHORITY.paper_only is True
    assert authority.AUTHORITY.live_enabled is False
    assert authority.AUTHORITY.broker_writes is False


@pytest.mark.parametrize("equity,expected", [(1_000, 20.0), (10_000, 200.0), (25_000, 500.0)])
def test_daily_loss_budget_scales_with_equity(equity: float, expected: float) -> None:
    assert authority.daily_loss_budget(equity) == expected
    assert authority.evaluate_daily_loss(equity, expected - 0.01)["blocked"] is False
    assert authority.evaluate_daily_loss(equity, expected)["blocked_reason"] == "max_daily_loss_hit"
    assert authority.evaluate_daily_loss(equity, expected + 0.01)["blocked"] is True


def test_open_risk_and_single_trade_limit_fail_closed() -> None:
    assert authority.open_risk_budget(10_000) == 100.0
    assert authority.evaluate_open_risk(10_000, 0, 50)["blocked"] is False
    assert authority.remaining_open_risk_capacity(10_000, 50) == 50.0
    at_limit = authority.evaluate_open_risk(10_000, 100, 0.01)
    assert "max_open_risk_hit" in at_limit["blocked_reasons"]
    second = authority.evaluate_open_risk(10_000, 25, 25, active_trade_count=1)
    assert "max_open_trades_hit" in second["blocked_reasons"]


def test_risk_derived_notional_is_deterministic_and_bounded() -> None:
    first = authority.derive_risk_position(10_000, "EUR_USD", 1.1, 1.095)
    second = authority.derive_risk_position(10_000, "EUR/USD", 1.1, 1.095)
    assert first == second
    assert first["policy"] == authority.MAX_PAIR_EXPOSURE_POLICY
    assert first["calculated_initial_risk"] == 100.0
    assert first["calculated_initial_risk"] <= first["risk_budget"]
    assert first["broker_leverage_used"] is False
    with pytest.raises(ValueError, match="INVALID_STOP_DISTANCE"):
        authority.derive_risk_position(10_000, "EUR_USD", 1.1, 1.1)


def test_spread_normalization_is_instrument_specific() -> None:
    non_jpy = authority.evaluate_spread("EUR_USD", 0.0003)
    jpy = authority.evaluate_spread("USD_JPY", 0.03)
    assert non_jpy["spread_pips"] == 3.0 and non_jpy["blocked"] is False
    assert jpy["spread_pips"] == 3.0 and jpy["blocked"] is False
    assert non_jpy["pip_size"] == 0.0001
    assert jpy["pip_size"] == 0.01
    assert authority.evaluate_spread("EUR_USD", 0.00031)["blocked_reason"] == "spread_too_high"
    assert authority.evaluate_spread("USD_JPY", 0.031)["blocked_reason"] == "spread_too_high"


def test_kill_switch_procedures_complete_declaration_gate_only() -> None:
    proof = authority.kill_switch_readiness_proof()
    assert proof["credential_revoke_path_declared"] is True
    assert proof["notification_path_declared"] is True
    assert proof["actual_credential_revoked"] is False
    assert proof["external_notification_sent"] is False
    assert proof["result"]["kill_switch_status"] == "KILL_SWITCH_READY"
    assert proof["result"]["safety"]["credentials_accessed"] is False
    assert proof["result"]["safety"]["network_access"] is False


def test_risk_map_and_readiness_recalculation_are_honest() -> None:
    risk_map = authority.canonical_risk_map()
    assert risk_map["MAX_DAILY_LOSS"]["status"] == "PROVEN"
    assert risk_map["MAX_OPEN_RISK"]["status"] == "PROVEN"
    assert risk_map["MAX_PAIR_EXPOSURE"]["status"] == "PROVEN_POLICY"
    assert risk_map["MAX_SPREAD"]["unit"] == "PIPS_INSTRUMENT_NORMALIZED"
    assert risk_map["LOSS_STREAK_LIMIT"]["status"] == "NOT_APPLICABLE"
    readiness = authority.recalculate_readiness(authority._load_previous_readiness())
    assert readiness["readiness_gate_count"] == 27
    assert readiness["readiness_pass_count_after"] == 19
    assert readiness["readiness_fail_count_after"] == 0
    assert readiness["readiness_pending_count_after"] == 8
    assert readiness["live_readiness_score_after"] == 0.6
    assert set(readiness["live_readiness_blockers_after"]) == {
        "human_approval_missing",
        "paper_evidence_insufficient",
        "demo_evidence_insufficient",
    }
    assert readiness["live_readiness_review"]["allowed"] is False


def test_no_credential_or_account_value_and_no_execution_capability() -> None:
    payload = {
        "authority": authority.asdict(authority.AUTHORITY),
        "kill_switch": authority.kill_switch_readiness_proof(),
        "risk_map": authority.canonical_risk_map(),
    }
    encoded = json.dumps(payload, allow_nan=False).lower()
    assert "authorization:" not in encoded
    assert "bearer " not in encoded
    assert "account-id" not in encoded
    assert authority.AUTHORITY.live_enabled is False
    assert authority.AUTHORITY.broker_writes is False


def test_synthetic_proof_passes_without_network_or_broker() -> None:
    proof = authority.synthetic_proof()
    assert proof["proof_pass"] is True
    source = authority.Path(authority.__file__).read_text(encoding="utf-8")
    assert "requests" not in source
    assert "urllib" not in source
    assert "Oanda" not in source


def test_paper30_state_and_forward_count_remain_unchanged() -> None:
    before = _paper_hashes()
    state, ledger = authority._load_paper30_state()
    assert state["strategy_config_sha256"] == authority.PAPER30_STRATEGY_CONFIG_SHA256
    assert authority._forward_count(ledger) == 0
    assert _paper_hashes() == before
