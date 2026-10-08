from decimal import Decimal
from pathlib import Path

from automation.forex_engine.forex_paper60_recovery_v2 import (
    audit_trades,
    file_manifest,
    manifest_fingerprint,
    target_causality,
)


def trade(direction="BUY", realized="-1", mfe="0.4"):
    buy = direction == "BUY"
    return {
        "trade_id": f"{direction}-1",
        "trade_direction": direction,
        "entry_price": "1.1000",
        "exit_price": "1.0990" if buy else "1.1010",
        "initial_stop": "1.0990" if buy else "1.1010",
        "target_price": "1.1100" if buy else "1.0980",
        "initial_risk_price": "0.0010",
        "realized_r": realized,
        "r_parity_valid": True,
        "mfe_r": mfe,
    }


def test_accounting_audit_accepts_direction_correct_r_parity():
    result = audit_trades([trade()], "BUY")
    assert result["accounting_pass"] is True
    assert result["unique_trade_ids"] == 1


def test_accounting_audit_detects_duplicate_and_cross_direction():
    trades = [trade(), trade()]
    result = audit_trades(trades, "SELL")
    assert result["accounting_pass"] is False
    assert result["duplicate_trade_ids"] == ["BUY-1"]
    assert result["direction_routing_errors"] == ["BUY-1", "BUY-1"]


def test_target_only_is_non_causal_when_no_trade_reaches_one_r():
    result = target_causality([trade(mfe="0.2"), {**trade(mfe="0.9"), "trade_id": "BUY-2"}])
    assert result["verdict"] == "NON_CAUSAL_FOR_OBSERVED_FAILURES"
    assert result["trades_reaching_each_target"]["1"] == 0


def test_manifest_is_deterministic(tmp_path: Path):
    (tmp_path / "a.txt").write_text("x", encoding="ascii")
    first = file_manifest(tmp_path)
    second = file_manifest(tmp_path)
    assert first == second
    assert manifest_fingerprint(first) == manifest_fingerprint(second)


def test_decimal_geometry_uses_exact_parity():
    result = audit_trades([trade(realized=str(Decimal("-1")))], "BUY")
    assert result["r_parity_errors"] == []
