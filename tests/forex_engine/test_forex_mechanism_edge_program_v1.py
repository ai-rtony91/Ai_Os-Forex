from datetime import datetime, timezone

from automation.forex_engine import forex_mechanism_edge_program_v1 as module


def test_protocol_corrects_standalone_veto():
    value = module.protocol()
    assert value["falsification_unit"] == "COMPLETE_CAUSAL_TRADING_HYPOTHESIS"
    assert value["candidate_cap"] == 48
    assert value["null_repetitions"] == 500


def test_registry_freezes_all_six_tracks_and_cap():
    registry = module.registry(False)
    assert len(registry) == 48
    assert {item.track for item in registry} == {1, 2, 3, 4, 5, 6}
    assert [sum(item.track == track for item in registry) for track in range(1, 7)] == [10, 8, 8, 8, 8, 6]


def test_unavailable_sources_do_not_block_independent_tracks():
    registry = module.registry(False)
    assert not any(item.data_eligible for item in registry if item.track in (1, 3))
    assert all(item.data_eligible for item in registry if item.track in (2, 4, 5, 6))


def test_complete_hypothesis_contains_required_contract():
    item = module.registry(True)[0]
    assert item.sources and item.availability_rule and item.direction_logic
    assert item.timeframe in {"H1", "H4", "D1"}
    assert item.stop_atr in {1.5, 2.0}
    assert item.target_r in {2.0, 3.0}
    assert item.risk == 0.0025


def test_folds_are_chronological_and_nonoverlapping():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, tzinfo=timezone.utc)
    folds = module.fold_windows((start, end))
    assert len(folds) == 8
    assert all(folds[index][1] == folds[index + 1][0] for index in range(7))


def test_validation_and_holdout_boundary_embargo():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 2, 1, tzinfo=timezone.utc)
    scored = module.embargoed_window((start, end))
    assert (scored[0] - start).days == 5
    assert scored[1] == end


def test_null_and_bootstrap_are_deterministic():
    trades = [{"r": value, "pair": "EUR_USD"} for value in (2.0, -1.0, 2.0, -1.0) * 20]
    assert module.null_campaign({"x": trades}, 20) == module.null_campaign({"x": trades}, 20)
    assert module.bootstrap(trades, 40) == module.bootstrap(trades, 40)


def test_ineligible_hypothesis_cannot_trade():
    item = next(value for value in module.registry(False) if not value.data_eligible)
    assert module.simulate({}, {}, item, (datetime.min.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)), "LONG") == []
