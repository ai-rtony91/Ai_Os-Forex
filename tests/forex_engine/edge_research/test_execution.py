from copy import deepcopy
from datetime import timedelta
import pytest
from automation.forex_engine.edge_research.features import snapshots, utc
from automation.forex_engine.edge_research.execution import (
    certify_executable_paths,
    entry_check,
    path_exit,
    opportunity_paths,
    quote_to_usd,
)


def fixture():
    rows = []
    for i in range(40):
        mid = dict(o=1.1, h=1.1002, l=1.0998, c=1.1)
        rows.append(dict(instrument="EUR_USD", complete=True, volume=2,
            timestamp=(utc("2024-01-03T12:00:00Z")+timedelta(minutes=5*i)).isoformat(),
            mid=mid, bid={k:v-.00005 for k,v in mid.items()}, ask={k:v+.00005 for k,v in mid.items()}))
    features = snapshots("EUR_USD", rows)
    for f in features:
        f.update(lower_band=1.099, upper_band=1.101, event_direction=0, rsi14=50)
    features[3]["event_direction"] = 1
    features[7]["event_direction"] = -1
    return rows, features


def test_side_cost_reference_and_shared_opportunities():
    rows, features = fixture()
    # First trade exits at the opposite open; second trade stops in that bar.
    # Both lifecycles must be complete even though this checks the first one.
    for side in ("bid", "ask", "mid"):
        rows[8][side]["h"] = 1.102
    features[7]["rsi14"] = 50
    result = opportunity_paths("EUR_USD", rows[:9], features[:9], .0001)
    path = result[0]["arms"][0]["path"]
    assert path["entry"] == pytest.approx(1.10006)
    assert path["initial_distance"] == pytest.approx(.00106)
    assert path["exit"]["index"] == 8
    assert path["quote_pnl"]["BASE"] == pytest.approx(-.00012)
    assert path["quote_pnl"]["STRESSED"] == pytest.approx(-.0002)
    assert path["quote_pnl"]["SEVERE_BUT_PLAUSIBLE"] == pytest.approx(-.0003)
    assert path["gross_quote_pnl"] == pytest.approx(0)
    assert result[0]["arms"][0] == result[0]["arms"][1]


def test_rsi_only_changes_selection_not_baseline():
    rows, features = fixture()
    assert entry_check(rows[4], features[3], .0001, True)[0] == "EXECUTED"
    features[3]["rsi14"] = 71
    assert entry_check(rows[4], features[3], .0001, True)[:2] == ("FILTERED", "RSI_THRESHOLD")
    assert entry_check(rows[4], features[3], .0001, False)[0] == "EXECUTED"
    features[3]["rsi14"] = 70
    assert entry_check(rows[4], features[3], .0001, True)[0] == "EXECUTED"
    features[3]["rsi14"] = None
    assert entry_check(rows[4], features[3], .0001, True)[1] == "RSI_WARMUP"


def test_cost_check_has_no_future_inputs_and_invalid_stops_fail():
    rows, features = fixture()
    before = entry_check(rows[4], features[3], .0001, False)
    rows[4]["ask"]["h"] = 10
    rows[4]["bid"]["l"] = .1
    assert entry_check(rows[4], features[3], .0001, False) == before
    features[3]["lower_band"] = 1.10001
    assert entry_check(rows[4], features[3], .0001, False)[1] == "INVALID_INITIAL_STOP"
    features[3]["lower_band"] = 1.0999
    assert entry_check(rows[4], features[3], .0001, False)[1] == "BASE_COST_CEILING"


def test_gap_stop_uses_worse_open_and_trailing_effective_next_bar():
    rows, features = fixture()
    rows[5]["bid"]["o"] = 1.098
    result = path_exit(rows, features, 4, 1, 1.099)
    assert result["reason"] == "GAP_STOP"
    assert result["price"] == 1.098
    rows, features = fixture()
    features[4]["lower_band"] = 1.1001
    result = path_exit(rows, features, 4, 1, 1.099)
    assert result["index"] == 5  # not applied earlier inside bar four
    assert result["price"] == pytest.approx(1.09995)


def test_short_stop_and_never_loosen():
    rows, features = fixture()
    features[4]["upper_band"] = 1.1005
    features[5]["upper_band"] = 1.102
    rows[6]["ask"]["h"] = 1.1006
    result = path_exit(rows, features, 4, -1, 1.101)
    assert result["index"] == 6
    assert result["price"] == 1.1005
    assert result["phase"] == "CLOSE_UNORDERED_INTRABAR"


def test_missing_open_path_is_invalid_not_favorable_fill():
    rows, features = fixture()
    del rows[5]
    del features[5]
    with pytest.raises(ValueError, match="UNRESOLVED_OPEN_POSITION_PRICE_GAP"):
        path_exit(rows, features, 4, 1, 1.099)


def test_rollover_forces_prior_exit_and_missing_deadline_blocks():
    rows, features = fixture()
    for i, row in enumerate(rows):
        row["timestamp"] = (utc("2024-01-03T21:20:00Z")+timedelta(minutes=5*i)).isoformat()
    for f in features: f["event_direction"] = 0
    assert path_exit(rows, features, 0, 1, 1.099)["time"] == utc("2024-01-03T21:30:00Z").isoformat()
    with pytest.raises(ValueError): path_exit(rows[:2], features[:2], 0, 1, 1.099)


def test_side_correct_cash_conversion():
    quotes = {"USD_JPY": lambda stamp: (150., 150.02), "GBP_USD": lambda stamp: (1.25, 1.2502)}
    assert quote_to_usd("JPY", "known_time", quotes) == pytest.approx(1/150.02)
    assert quote_to_usd("JPY", "known_time", quotes, positive=False) == pytest.approx(1/150)
    assert quote_to_usd("GBP", "known_time", quotes) == 1.25
    assert quote_to_usd("USD", "known_time", quotes) == 1
    with pytest.raises(ValueError): quote_to_usd("CHF", "known_time", quotes)


def test_development_end_forces_fixed_exit_and_no_new_entries():
    rows, features = fixture()
    for i, row in enumerate(rows):
        row["timestamp"] = (utc("2025-03-31T23:40:00Z")+timedelta(minutes=5*i)).isoformat()
    for f in features: f["event_direction"] = 0
    result = path_exit(rows, features, 0, 1, 1.099)
    assert result["time"] == utc("2025-03-31T23:55:00Z").isoformat()
    assert result["reason"] == "SCHEDULED_EXIT"
    features[1].update(event_direction=1, feature_available_at=rows[2]["timestamp"])
    assert entry_check(rows[2], features[1], .0001, False)[1] == "CALENDAR_OR_BOUNDARY_NO_ENTRY"


def test_gap_stop_precedes_scheduled_exit_and_includes_adverse_slip():
    rows, features = fixture()
    for i, row in enumerate(rows):
        row["timestamp"] = (utc("2024-01-03T21:20:00Z")+timedelta(minutes=5*i)).isoformat()
    for f in features: f["event_direction"] = 0
    rows[2]["bid"]["o"] = 1.098
    result = path_exit(rows, features, 0, 1, 1.099)
    assert result["reason"] == "GAP_STOP"
    assert result["price"] == 1.098


def test_rsi_short_threshold_and_gap_entry():
    rows, features = fixture()
    features[3].update(event_direction=-1, rsi14=30)
    assert entry_check(rows[4], features[3], .0001, True)[0] == "EXECUTED"
    features[3]["rsi14"] = 29.99
    assert entry_check(rows[4], features[3], .0001, True)[1] == "RSI_THRESHOLD"
    rows[4]["timestamp"] = rows[5]["timestamp"]
    assert entry_check(rows[4], features[3], .0001, False)[1] == "NO_CONTIGUOUS_CAUSAL_ENTRY"


def test_unavailable_midpoint_preserves_real_exit_and_opportunity():
    rows, features = fixture()
    for f in features[4:]: f["event_direction"] = 0
    # Executable bid hits the stop before the gap; midpoint has not hit it.
    rows[4]["bid"]["l"] = 1.0989
    del rows[5]
    del features[5]
    results = opportunity_paths("EUR_USD", rows, features, .0001)
    assert len(results) == 1
    for arm in results[0]["arms"]:
        assert arm["status"] == "EXECUTED"
        assert arm["path"]["exit"]["reason"] == "STOP"
        assert arm["path"]["gross_r"] is None
        assert arm["path"]["gross_quote_pnl"] is None
        assert arm["path"]["gross_exit"] is None
        assert arm["path"]["gross_unavailable"]["reason"] == "UNRESOLVED_OPEN_POSITION_PRICE_GAP"
        assert arm["net"] < -1


def test_executable_gap_still_invalidates_entire_comparison():
    rows, features = fixture()
    del rows[5]
    del features[5]
    with pytest.raises(ValueError, match="UNRESOLVED_OPEN_POSITION_PRICE_GAP"):
        opportunity_paths("EUR_USD", rows, features, .0001)


def test_pre_score_availability_finds_open_position_gap_without_calculating_returns():
    rows, features = fixture()
    for item in features[4:]:
        item["event_direction"] = 0
    del rows[5]
    del features[5]
    result = certify_executable_paths(
        "EUR_USD", rows, features, .0001,
        candidate_ids=("PKT045_A", "PKT045_B"),
    )
    assert result["OUTCOME_EXPOSURE"] == "FROZEN_EXECUTION_AVAILABILITY_ONLY_NO_PNL_OR_RANKING"
    assert result["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS"]
    assert result["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS"][0]["REASON"] == "UNRESOLVED_OPEN_POSITION_PRICE_GAP"


def test_pre_score_availability_keeps_rsi_filter_as_a_normal_no_entry_not_a_data_repair():
    rows, features = fixture()
    for item in features[4:]:
        item["event_direction"] = 0
    features[3]["rsi14"] = 71
    # The baseline still enters, so give its executable path a genuine stop
    # before the synthetic fixture ends.  The challenger remains a normal RSI
    # filter skip rather than a data-path failure.
    rows[5]["bid"]["l"] = 1.0989
    result = certify_executable_paths(
        "EUR_USD", rows, features, .0001,
        candidate_ids=("PKT045_A", "PKT045_B"),
    )
    assert not result["UNRESOLVED_REQUIRED_EXECUTABLE_PATHS"]
    assert result["ATTEMPTED_ENTRIES"]["PKT045_A"] == 1
    assert result["ATTEMPTED_ENTRIES"]["PKT045_B"] == 0
    assert result["NORMAL_SKIPS"]["PKT045_B"]["RSI_THRESHOLD"] == 1


def test_unexpected_diagnostic_defect_is_not_hidden(monkeypatch):
    from automation.forex_engine.edge_research import execution
    rows, features = fixture()
    original = execution.path_exit
    def broken(*args, **kwargs):
        if kwargs.get("midpoint"): raise ValueError("UNEXPECTED_CALCULATION_DEFECT")
        return original(*args, **kwargs)
    monkeypatch.setattr(execution, "path_exit", broken)
    with pytest.raises(ValueError, match="UNEXPECTED_CALCULATION_DEFECT"):
        opportunity_paths("EUR_USD", rows, features, .0001)
