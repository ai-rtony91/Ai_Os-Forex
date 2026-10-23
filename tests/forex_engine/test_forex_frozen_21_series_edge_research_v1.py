from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from automation.forex_engine import forex_frozen_21_series_edge_research_v1 as subject


def candle(index: int, *, step: float = 0.0001, granularity: str = "M1", instrument: str = "EUR_USD") -> subject.Candle:
    mid = 1.1 + index * step
    spread = 0.0002
    at = datetime(2024, 1, 2, 10, tzinfo=timezone.utc) + timedelta(minutes=index)
    return subject.Candle(at, instrument, granularity, mid - spread / 2, mid + 0.0003 - spread / 2,
                          mid - 0.0003 - spread / 2, mid - spread / 2,
                          mid + spread / 2, mid + 0.0003 + spread / 2,
                          mid - 0.0003 + spread / 2, mid + spread / 2)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def frozen_fixture(tmp_path: Path) -> Path:
    root = tmp_path / subject.DATASET_ID
    source = root / "source_artifacts"
    payload = b"{}"
    artifact = source / "artifact.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    series = [
        {"instrument": pair, "granularity": granularity, "candle_count": 1}
        for pair in subject.EXPECTED_INSTRUMENTS for granularity in subject.EXPECTED_GRANULARITIES
    ]
    file_item = {"relative_path": "artifact.json", "bytes": len(payload), "sha256": digest, "role": "terminal_manifest"}
    files = [dict(file_item) for _ in range(14200)]
    inventory = {"dataset_id": subject.DATASET_ID, "dataset_sha256": subject.DATASET_SHA256,
                 "scope_fingerprint": subject.SCOPE_FINGERPRINT, "series_inventory": series, "file_inventory": files}
    validation = {"status": "PASS", "dataset_id": subject.DATASET_ID, "dataset_sha256": subject.DATASET_SHA256,
                  "source_state_sha256": subject.SOURCE_STATE_SHA256, "manifest_sha256": subject.MANIFEST_SHA256,
                  "scope_fingerprint": subject.SCOPE_FINGERPRINT, "series_complete": 21, "total_candle_count": 70822831}
    freeze = {"status": "PASS", "dataset_id": subject.DATASET_ID, "dataset_sha256": subject.DATASET_SHA256,
              "source_state_sha256": subject.SOURCE_STATE_SHA256, "manifest_sha256": subject.MANIFEST_SHA256,
              "scope_fingerprint": subject.SCOPE_FINGERPRINT}
    write_json(root / "AIOS_FOREX_HISTORICAL_DATASET_INVENTORY.json", inventory)
    write_json(root / "AIOS_FOREX_HISTORICAL_DATASET_VALIDATION_RECEIPT.json", validation)
    write_json(root / "AIOS_FOREX_HISTORICAL_DATASET_FREEZE_RECEIPT.json", freeze)
    return root


def test_candidate_registry_is_bounded_deterministic_and_covers_families_and_timeframes():
    first = subject.build_candidates()
    assert first == subject.build_candidates()
    assert len(first) == 24
    assert len({item.family for item in first}) == 8
    assert {item.granularity for item in first} == set(subject.EXPECTED_GRANULARITIES)
    assert all(item.directions == ("LONG", "SHORT") for item in first)


def test_contract_seals_holdout_and_predeclares_costs_and_reproduction():
    contract = subject.build_contract()
    assert contract["holdout_policy"] == "SEALED_AND_NOT_EVALUATED_IN_PHASE1"
    assert contract["splits"]["sealed_final_holdout"][0] == subject.VALIDATION_END
    assert contract["costs"]["base"]["spread"] == "RECORDED_BID_ASK_ONCE"
    assert "run_forex_frozen_21_series_edge_research_v1.py run" in contract["reproduction_command"]


def test_frozen_fixture_with_exact_identity_and_21_series_passes(tmp_path):
    result = subject.verify_frozen_dataset(frozen_fixture(tmp_path), verify_files=True)
    assert result["files_checked"] == 14200
    assert len(result["inventory"]["series_inventory"]) == 21


def test_validation_v1_may_omit_dataset_id_when_hash_and_freeze_binding_match(tmp_path):
    root = frozen_fixture(tmp_path)
    path = root / "AIOS_FOREX_HISTORICAL_DATASET_VALIDATION_RECEIPT.json"
    document = json.loads(path.read_text())
    document.pop("dataset_id")
    write_json(path, document)
    assert subject.verify_frozen_dataset(root, verify_files=False)["files_checked"] == 14200


@pytest.mark.parametrize("field,value", [("dataset_sha256", "0" * 64), ("scope_fingerprint", "0" * 64)])
def test_frozen_identity_mismatch_blocks(tmp_path, field, value):
    root = frozen_fixture(tmp_path)
    path = root / "AIOS_FOREX_HISTORICAL_DATASET_INVENTORY.json"
    document = json.loads(path.read_text())
    document[field] = value
    write_json(path, document)
    with pytest.raises(subject.ResearchBlocked, match="MISMATCH"):
        subject.verify_frozen_dataset(root, verify_files=False)


def test_missing_series_blocks(tmp_path):
    root = frozen_fixture(tmp_path)
    path = root / "AIOS_FOREX_HISTORICAL_DATASET_INVENTORY.json"
    document = json.loads(path.read_text())
    document["series_inventory"].pop()
    write_json(path, document)
    with pytest.raises(subject.ResearchBlocked, match="CARDINALITY"):
        subject.verify_frozen_dataset(root, verify_files=False)


def test_altered_artifact_hash_blocks(tmp_path):
    root = frozen_fixture(tmp_path)
    (root / "source_artifacts" / "artifact.json").write_bytes(b"[]")
    with pytest.raises(subject.ResearchBlocked, match="HASH_MISMATCH"):
        subject.verify_frozen_dataset(root, verify_files=True)


def test_missing_artifact_blocks(tmp_path):
    root = frozen_fixture(tmp_path)
    (root / "source_artifacts" / "artifact.json").unlink()
    with pytest.raises(subject.ResearchBlocked, match="MISSING_OR_SIZE"):
        subject.verify_frozen_dataset(root, verify_files=False)


def test_signal_uses_completed_history_only_and_returns_direction():
    candidate = subject.build_candidates()[0]
    rows = [candle(index) for index in range(120)]
    assert subject.signal_for(candidate, rows) == "LONG"


def test_multi_timeframe_family_uses_completed_derived_higher_bars():
    candidate = next(item for item in subject.build_candidates() if item.family == "MULTI_TIMEFRAME_CONFIRMATION")
    rows = [candle(index, granularity=candidate.granularity) for index in range(candidate.slow_lookback * 4 + 10)]
    assert subject.signal_for(candidate, rows) == "LONG"


def test_next_candle_open_and_bid_ask_cost_are_used():
    candidate = replace(subject.build_candidates()[0], slow_lookback=3, lookback=2, max_holding_bars=2)
    rows = [candle(index) for index in range(12)]
    trades, count = subject.evaluate_series(rows, [candidate], slippage=0.00001, cost_case="base")
    assert count == 12
    assert all(item["entry_time"] > item["signal_time"] for item in trades)


def test_no_trade_can_cross_new_york_financing_boundary():
    entry = datetime(2024, 1, 2, 21, 59, tzinfo=timezone.utc)  # 16:59 New York in winter
    assert subject._crosses_new_york_rollover(entry, entry + timedelta(minutes=2))


def test_split_embargo_prevents_boundary_contamination():
    candidate = subject.build_candidates()[0]
    boundary = subject.parse_utc(subject.DEVELOPMENT_END)
    assert subject._eligible_signal_split(candidate, boundary - timedelta(seconds=1)) is None
    embargo = timedelta(seconds=subject.GRANULARITY_SECONDS[candidate.granularity] * (candidate.slow_lookback + candidate.max_holding_bars))
    assert subject._eligible_signal_split(candidate, boundary + embargo) == "phase1_validation"


def test_stressed_spread_adjustment_is_adverse():
    item = candle(1)
    assert subject._spread_extra(item, 1.5, "o") > 0
    assert subject._spread_extra(item, 1.0, "o") == 0


def test_metrics_calculate_expectancy_pf_drawdown_concentration_and_single_trade_removal():
    rows = [
        {"r": value, "exit_time": f"2024-01-0{index + 1}T00:00:00Z", "instrument": "EUR_USD" if index < 2 else "GBP_USD",
         "candidate_id": "X", "direction": "LONG" if index % 2 else "SHORT", "development_fold": index}
        for index, value in enumerate((2.0, 1.0, -1.0, 1.0, -0.5, 1.0))
    ]
    result = subject.metrics(rows)
    assert result["trade_count"] == 6
    assert result["profit_factor"] > 1.1
    assert result["maximum_drawdown_pct"] > 0
    assert result["largest_pair_share"] < 1
    assert result["expectancy_without_largest_trade_r"] > 0


def test_gate_rejects_inadequate_sample_and_pair_concentration():
    metric = {"trade_count": 199, "long_trades": 100, "short_trades": 99, "instrument_count": 1,
              "expectancy_r": 1, "profit_factor": 2, "maximum_drawdown_pct": 1,
              "largest_pair_share": 1, "expectancy_without_largest_trade_r": 1, "positive_development_folds": 6}
    passed, reasons = subject._gate(metric, require_folds=True)
    assert not passed
    assert "TRADE_COUNT_BELOW_200" in reasons and "PAIR_CONCENTRATION_ABOVE_60_PERCENT" in reasons


def test_gate_rejects_single_trade_dependence_and_too_few_positive_folds():
    metric = {"trade_count": 300, "long_trades": 150, "short_trades": 150, "instrument_count": 3,
              "expectancy_r": 0.1, "profit_factor": 1.2, "maximum_drawdown_pct": 4,
              "largest_pair_share": 0.4, "expectancy_without_largest_trade_r": 0, "positive_development_folds": 3}
    passed, reasons = subject._gate(metric, require_folds=True)
    assert not passed
    assert "SINGLE_TRADE_DEPENDENCE" in reasons and "FEWER_THAN_FOUR_POSITIVE_DEVELOPMENT_FOLDS" in reasons


def test_summary_requires_cost_stress_and_neighbor_stability():
    candidates = subject.build_candidates()[:3]
    results = subject.summarize_results(candidates, [])
    assert all(not item["phase1_pass"] for item in results.values())
    assert all("PARAMETER_NEIGHBOR_STABILITY_FAILED" in item["rejection_reasons"] for item in results.values())


def test_checkpoint_accepts_only_exact_identity():
    contract_hash = "a" * 64
    registry_hash = "b" * 64
    checkpoint = {"schema": f"{subject.SCHEMA}.checkpoint", "dataset_sha256": subject.DATASET_SHA256,
                  "source_state_sha256": subject.SOURCE_STATE_SHA256, "contract_sha256": contract_hash,
                  "candidate_registry_sha256": registry_hash, "completed_series": [], "aggregates": {}}
    assert subject._checkpoint_valid(checkpoint, contract_hash, registry_hash)
    checkpoint["dataset_sha256"] = "0" * 64
    assert not subject._checkpoint_valid(checkpoint, contract_hash, registry_hash)
    checkpoint["dataset_sha256"] = subject.DATASET_SHA256
    assert subject._checkpoint_identity_matches(checkpoint, contract_hash, registry_hash)


def test_compact_aggregates_merge_without_retaining_trade_rows():
    rows = [
        {"r": value, "exit_time": f"2024-01-0{index + 1}T00:00:00Z", "instrument": "EUR_USD",
         "candidate_id": "X", "direction": "LONG" if index % 2 else "SHORT", "development_fold": index,
         "cost_case": "base", "split": "development", "session": "LONDON", "regime": "NORMAL_VOLATILITY"}
        for index, value in enumerate((2.0, -1.0, 1.0))
    ]
    first = subject.aggregate_trades(rows)
    merged = {}
    subject.merge_aggregates(merged, first)
    subject.merge_aggregates(merged, first)
    metric = subject.metrics_from_aggregate(merged["X|base|development"])
    assert metric["trade_count"] == 6 and metric["expectancy_r"] > 0
    assert "trades" not in merged["X|base|development"]
    assert metric["direction_metrics"]["LONG"]["trade_count"] == 2
    assert metric["session_metrics"]["LONDON"]["trade_count"] == 6


def test_atomic_json_replaces_complete_document(tmp_path):
    path = tmp_path / "receipt.json"
    subject.atomic_json(path, {"status": "PASS"})
    assert json.loads(path.read_text()) == {"status": "PASS"}
    assert not list(tmp_path.glob("*.tmp"))


def test_batch_reader_rejects_duplicate_cross_batch_timestamp(tmp_path):
    root = tmp_path / "source"
    series = root / "EUR_USD_M1"
    raw = {"complete": True, "volume": 1, "time": "2024-01-02T10:00:00Z",
           "bid": {"o": "1", "h": "1.1", "l": "0.9", "c": "1"},
           "ask": {"o": "1.01", "h": "1.11", "l": "0.91", "c": "1.01"}}
    for number in range(2):
        write_json(series / f"{number:06d}_EUR_USD_M1.json", {"instrument": "EUR_USD", "granularity": "M1", "candle_count": 1, "candles": [raw]})
    inventory = {"file_inventory": [
        {"role": "batch", "instrument": "EUR_USD", "granularity": "M1", "batch_number": number,
         "relative_path": f"EUR_USD_M1/{number:06d}_EUR_USD_M1.json"} for number in range(2)
    ]}
    with pytest.raises(subject.ResearchBlocked, match="ORDER_OR_DUPLICATE"):
        list(subject.iter_series({"inventory": inventory, "source_root": str(root)}, "EUR_USD", "M1"))


def test_batch_reader_rejects_pair_contamination(tmp_path):
    root = tmp_path / "source"
    path = root / "EUR_USD_M1" / "000000_EUR_USD_M1.json"
    write_json(path, {"instrument": "GBP_USD", "granularity": "M1", "candle_count": 0, "candles": []})
    inventory = {"file_inventory": [{"role": "batch", "instrument": "EUR_USD", "granularity": "M1",
                                      "batch_number": 0, "relative_path": "EUR_USD_M1/000000_EUR_USD_M1.json"}]}
    with pytest.raises(subject.ResearchBlocked, match="CONTAMINATION"):
        list(subject.iter_series({"inventory": inventory, "source_root": str(root)}, "EUR_USD", "M1"))


def test_candle_rejects_incomplete_and_negative_spread():
    raw = {"complete": False, "time": "2024-01-01T00:00:00Z", "bid": {}, "ask": {}}
    with pytest.raises(subject.ResearchBlocked, match="INCOMPLETE"):
        subject._candle(raw, "EUR_USD", "M1")
    raw = {"complete": True, "time": "2024-01-01T00:00:00Z",
           "bid": {"o": 2, "h": 2, "l": 2, "c": 2}, "ask": {"o": 1, "h": 1, "l": 1, "c": 1}}
    with pytest.raises(subject.ResearchBlocked, match="NEGATIVE_SPREAD"):
        subject._candle(raw, "EUR_USD", "M1")


def test_source_files_are_not_mutated_by_verification(tmp_path):
    root = frozen_fixture(tmp_path)
    path = root / "source_artifacts" / "artifact.json"
    before = (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
    subject.verify_frozen_dataset(root, verify_files=True)
    after = (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
    assert before == after


def test_module_has_no_network_broker_or_credential_imports():
    source = Path(subject.__file__).read_text(encoding="utf-8")
    assert "requests" not in source and "oandapy" not in source and "subprocess" not in source
    assert "OPENAI_API_KEY" not in source and "OANDA_TOKEN" not in source


def test_report_is_concise_and_truthful():
    text = subject._report({"status": "PHASE1_EXHAUSTED_NO_CANDIDATE", "dataset_id": subject.DATASET_ID,
                            "dataset_sha256": subject.DATASET_SHA256, "series_processed": 21,
                            "candles_streamed": 1, "candidate_count": 24, "survivor_count": 0})
    assert len(text.splitlines()) < 20
    assert "not proof of profit" in text
    assert "SEALED" in text
