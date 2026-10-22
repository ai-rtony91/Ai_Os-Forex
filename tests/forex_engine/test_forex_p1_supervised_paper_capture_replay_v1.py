from __future__ import annotations

import json
from pathlib import Path

import pytest

from automation.forex_engine.forex_p1_supervised_paper_capture_replay_v1 import (
    SAFETY_FLAGS,
    deterministic_trade_id,
    run_capture_replay,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def candidate(evidence_type: str = "paper") -> dict:
    return {
        "evidence_type": evidence_type,
        "strategy_id": "strategy-c1",
        "instrument": "EUR_USD",
        "direction": "buy",
        "entry_timestamp_utc": "2026-08-01T10:00:00Z",
        "exit_timestamp_utc": "2026-08-01T11:00:00Z",
        "entry_price": 1.1,
        "exit_price": 1.101,
        "stop_price": 1.099,
        "target_price": 1.101,
        "quantity_or_units": 100,
        "realized_pl": 10,
        "fees": 1,
        "risk_amount": 10,
        "entry_rationale": "bounded paper review",
        "exit_reason": "target",
        "evidence_source": "sanitized_local_review",
        "reviewed_by": "human_owner",
        "review_timestamp_utc": "2026-08-01T12:00:00Z",
    }


@pytest.fixture
def paths(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    return tuple(tmp_path / name for name in ("input.json", "ledger.json", "state.json", "report.md", "events.jsonl"))


def run(paths, payload, repository_root: Path):
    paths[0].write_text(json.dumps(payload), encoding="utf-8")
    return run_capture_replay(*paths, repository_root=repository_root)


@pytest.mark.parametrize("evidence_type", ["paper", "supervised_demo"])
def test_valid_candidate_is_captured_and_replayed(paths, evidence_type):
    result = run(paths, candidate(evidence_type), REPOSITORY_ROOT)
    assert result["accepted_records"] == result["qualifying_trade_count"] == 1
    assert result["replay_status"] == "CANONICAL_P1_EVALUATOR_COMPLETE"
    assert result["replay_metrics"]["net_pl"] == 10


def test_generated_id_and_replay_are_deterministic(paths):
    record = candidate()
    expected = deterministic_trade_id(record)
    first = run(paths, record, REPOSITORY_ROOT)
    first_ledger = json.loads(paths[1].read_text())
    second = run(paths, record, REPOSITORY_ROOT)
    assert first_ledger["records"][0]["trade_id"] == expected
    assert second["duplicate_records"] == 1
    assert second["replay_metrics"] == first["replay_metrics"]
    assert len(json.loads(paths[1].read_text())["records"]) == 1


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"strategy_id": None}, "missing_strategy_id"),
        ({"exit_timestamp_utc": "2026-08-01T09:00:00Z"}, "invalid_timestamp_order"),
        ({"realized_pl": float("nan")}, "non_finite_or_invalid_realized_pl"),
        ({"raw_broker_payload": {"price": 1}}, "raw_broker_payload_rejected"),
        ({"account_id": "private"}, "secret_or_private_identifier_rejected"),
        ({"api_key": "private"}, "secret_or_private_identifier_rejected"),
        ({"order_id": "private"}, "secret_or_private_identifier_rejected"),
        ({"evidence_type": "live"}, "unsupported_evidence_type"),
    ],
)
def test_invalid_candidates_fail_closed_with_exact_reason(paths, mutation, reason):
    record = candidate()
    record.update(mutation)
    result = run(paths, record, REPOSITORY_ROOT)
    assert result["accepted_records"] == 0
    assert reason in result["rejections"][0]["reasons"]


def test_evaluator_trigger_metadata_and_all_flags_false(monkeypatch, paths):
    import automation.forex_engine.forex_p1_supervised_paper_evidence_pipeline_v1 as pipeline

    original = pipeline.evaluate_strategy_evidence
    calls = []

    def tracked(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "evaluate_strategy_evidence", tracked)
    result = run(paths, candidate(), REPOSITORY_ROOT)
    assert len(calls) == 2
    event = json.loads(paths[4].read_text().splitlines()[0])
    assert event["packet_id"].startswith("AIOS-P1-")
    for output in (result, json.loads(paths[1].read_text()), json.loads(paths[2].read_text())):
        assert all(output[key] is False for key in SAFETY_FLAGS)
    report = paths[3].read_text()
    assert all(f"{key}: false" in report for key in SAFETY_FLAGS)


def test_empty_input_runs_one_bounded_cycle(paths):
    result = run(paths, [], REPOSITORY_ROOT)
    assert result["input_records"] == result["accepted_records"] == 0
    assert result["p1_status_after"] == "NO_EVIDENCE"


def test_more_than_one_candidate_is_rejected(paths):
    paths[0].write_text(json.dumps([candidate(), candidate()]), encoding="utf-8")
    with pytest.raises(ValueError, match="one_bounded_candidate_required"):
        run_capture_replay(*paths, repository_root=REPOSITORY_ROOT)
