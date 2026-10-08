from datetime import datetime, timezone

from automation.forex_engine import forex_edge_existence_controller_v1 as c


def test_metric_and_cost_frontier_classification():
    assert c.metric([1.0, -1.0, 2.0])["expectancy"] == 0.66666667
    execution = {
        "candidate_rows": [
            {
                "candidate_id": "C1",
                "metrics": {
                    "layer_0": {"expectancy": 0.2},
                    "layer_4": {"expectancy": -0.1},
                },
            }
        ]
    }
    frontier = c.cost_frontier_from_execution(execution)
    assert frontier["cost_branch_supported"] is True
    assert frontier["rows"][0]["maximum_tolerable_cost_r"] == 0.2


def test_m5_data_sufficiency_requires_positive_information_for_extension(monkeypatch):
    monkeypatch.setattr(c, "read_json", lambda path: {"status": "FROZEN_VALID", "eligible_pair_count": 58, "total_records": 100})
    state = c.m5_data_sufficiency({"branch_supported": False})
    assert state["status"] == "CURRENT_M5_HISTORY_INSUFFICIENT_BUT_NO_POSITIVE_INFORMATION"
    assert state["human_m5_extension_required"] is False


def test_simulate_event_uses_frozen_entry_and_bid_ask(monkeypatch):
    t0 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(4):
        ts = (t0).replace(minute=i * 5).isoformat().replace("+00:00", "Z")
        rows.append(
            {
                "timestamp": ts,
                "bid": {"c": 1.0 + i * 0.001, "h": 1.0 + i * 0.0015, "l": 1.0 + i * 0.0005},
                "ask": {"c": 1.0002 + i * 0.001, "h": 1.0002 + i * 0.0015, "l": 1.0002 + i * 0.0005},
                "mid": {"c": 1.0001 + i * 0.001, "h": 1.0001 + i * 0.0015, "l": 1.0001 + i * 0.0005},
            }
        )
    monkeypatch.setattr(c, "_M5_CACHE", {"EUR_USD": rows})
    monkeypatch.setattr(c, "_M5_INDEX", {"EUR_USD": {row["timestamp"]: idx for idx, row in enumerate(rows)}})
    event = {
        "instrument_or_portfolio": "EUR_USD",
        "intended_execution_timestamp_utc": rows[1]["timestamp"],
        "direction": "LONG",
        "initial_stop": 0.001,
        "declared_exit_contract": "fixed_2r_control",
        "maximum_holding_horizon_bars": 2,
    }
    assert c.simulate_event(event, layer=0)["r"] >= c.simulate_event(event, layer=4)["r"]
