from datetime import datetime, timezone

from automation.forex_engine.forex_information_edge_program_v1 import (
    Candidate,
    daily_rows,
    development_gate,
    folds,
    latest_available,
    null_campaign,
    report_text,
)


def candle(day, hour, close=1.0):
    stamp = datetime(2024, 1, day, hour, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    price = {"o": close, "h": close + 0.01, "l": close - 0.01, "c": close}
    return {"timestamp": stamp, "instrument": "EUR_USD", "volume": 1, "mid": dict(price), "bid": dict(price), "ask": dict(price)}


def test_daily_aggregation_uses_only_complete_input_rows():
    rows = daily_rows([candle(1, 0), candle(1, 12, 1.1), candle(2, 0, 1.2)])
    assert len(rows) == 2
    assert rows[0]["mid"]["c"] == 1.1


def test_latest_information_never_uses_future_publication():
    records = [(datetime(2024, 1, 5, tzinfo=timezone.utc), 1), (datetime(2024, 1, 12, tzinfo=timezone.utc), 2)]
    assert latest_available(records, datetime(2024, 1, 10, tzinfo=timezone.utc)) == 1


def test_eight_chronological_folds_are_adjacent():
    window = (datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 9, tzinfo=timezone.utc))
    value = folds(window)
    assert len(value) == 8
    assert all(left[1] == right[0] for left, right in zip(value, value[1:]))


def test_development_gate_rejects_low_sample():
    result = {"trades": 49, "expectancy_r": 1, "profit_factor": 2, "net_r": 2, "max_drawdown_pct": 1, "pair_count": 20, "largest_pair_share": 0.1}
    assert not development_gate(result, [])


def test_registry_null_is_deterministic():
    trades = [{"r": 1 if index % 3 else -1} for index in range(100)]
    assert null_campaign({"candidate": trades}, 20) == null_campaign({"candidate": trades}, 20)


def test_candidate_contract_is_transparent_and_bounded():
    candidate = Candidate("B-01", "B_CFTC_POSITIONING", "COT_CONTINUATION", 0.1, 1.5, 2.0, 10)
    assert candidate.target_r == 2.0


def test_terminal_report_preserves_credential_and_funding_boundaries():
    state = {"status": "INFORMATION_EDGE_NOT_FOUND", "information_corpus_hash": "i", "market_hash": "m", "feature_hash": "f", "candidate_count": 0, "registry_hash": "r", "development_passers": [], "validation": {}, "finalists": [], "registry_null": {"repetitions": 500}, "family_screening": {"B_CFTC_POSITIONING": {"samples": 1, "mean_signed_future_atr": -0.1, "positive_folds": 1}, "D_GLOBAL_RISK_LIQUIDITY": {"samples": 1, "mean_signed_future_atr": 0.0, "positive_folds": 1}, "E_LONG_HORIZON": {"samples": 1, "mean_signed_future_atr": -0.1, "positive_folds": 1}}, "current_phase": "TERMINAL_REPORT", "current_action": "done", "next_action": "NONE", "remaining_authorized_work_count": 0, "terminal_state_candidate": "INFORMATION_EDGE_NOT_FOUND", "pre_terminal_audit_status": "PASS", "same_packet_resume_command": "NONE"}
    report = report_text(state)
    assert "do not enter credentials or fund OANDA" in report
    assert "Compounding enabled: false" in report
