from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from automation.forex_engine.forex_authoritative_data_matrix_v1 import (
    GRANULARITIES,
    INPUTS,
    build_matrix,
    sha256_file,
    write_outputs,
)


ROOT = Path(__file__).resolve().parents[2]


def matrix() -> dict:
    return build_matrix(ROOT)


def row(document: dict, pair: str, granularity: str) -> dict:
    return next(item for item in document["rows"] if item["pair"] == pair and item["granularity"] == granularity)


def test_exact_inputs_are_hash_pinned_and_metadata_only() -> None:
    assert len(INPUTS) == 7
    assert all(sha256_file(ROOT / path) == expected for path, expected in INPUTS.values())
    assert all("partitions/" not in path for path, _ in INPUTS.values())


def test_exact_68_by_14_matrix_is_unique_and_sorted() -> None:
    document = matrix()
    assert document["row_count"] == 68 * 14 == 952
    keys = [(item["pair"], GRANULARITIES.index(item["granularity"])) for item in document["rows"]]
    assert len(set((pair, index) for pair, index in keys)) == 952
    assert keys == sorted(keys)


def test_seconds_tick_and_high_frequency_scope_are_exact() -> None:
    document = matrix()
    assert document["seconds_data_available"] is True
    assert document["tick_data_available"] is False
    assert row(document, "EUR_USD", "S5")["availability"] == "NATIVE_CERTIFIED"
    assert row(document, "AUD_CAD", "S5")["availability"] == "ABSENT"
    assert row(document, "EUR_USD", "TICK")["development_eligibility"] is False
    assert row(document, "EUR_USD", "S1")["development_eligibility"] is False


def test_m5_raw_68_and_eligible_58_are_not_conflated() -> None:
    document = matrix()
    summary = document["native_scope_summary"]["m5"]
    assert summary["raw_pairs"] == 68
    assert summary["eligible_pairs"] == 58
    assert row(document, "AUD_CAD", "M5")["development_eligibility"] is True
    excluded = row(document, "EUR_DKK", "M5")
    assert excluded["availability"] == "NATIVE_RAW_PRESENT_INELIGIBLE"
    assert excluded["development_eligibility"] is False
    assert "BELOW_0.99" in excluded["exact_exclusion_reason"]


def test_derived_timeframes_are_never_claimed_native() -> None:
    document = matrix()
    for granularity in ("M10", "M15", "M30"):
        derived = row(document, "AUD_CAD", granularity)
        assert derived["native_or_derived"] == "DERIVED"
        assert derived["record_count"] is None
        assert derived["certification_status"] == "ELIGIBLE_IF_CAUSAL_COMPLETED_M5_RESAMPLER_VALIDATES"


def test_h1_scope_matches_58_pair_eligible_universe() -> None:
    document = matrix()
    h1 = [item for item in document["rows"] if item["granularity"] == "H1"]
    assert sum(item["development_eligibility"] for item in h1) == 58
    assert row(document, "AUD_CAD", "H1")["availability"] == "NATIVE_CERTIFIED"
    assert row(document, "EUR_DKK", "H1")["availability"] == "ABSENT"


def test_holdout_boundaries_remain_separate_and_unopened() -> None:
    document = matrix()
    assert row(document, "EUR_USD", "M1")["final_holdout_exclusion_boundary"] == "2026-02-16T14:24:00Z"
    assert row(document, "EUR_USD", "M5")["final_holdout_exclusion_boundary"] == "2026-01-01T00:00:00+00:00"
    assert document["safety"]["final_holdout_rows_opened"] == 0
    assert document["safety"]["strategy_trials_added"] == 0


def test_two_output_runs_are_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    a = write_outputs(ROOT, first)
    b = write_outputs(ROOT, second)
    assert a == b
    assert sorted(path.name for path in first.iterdir()) == sorted(path.name for path in second.iterdir())
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()
    receipt = json.loads((first / "AIOS_FOREX_AUTHORITATIVE_DATA_MATRIX_RECEIPT_V1.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"


def test_runner_imports_from_repo_root() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/forex_delivery/run_forex_authoritative_data_matrix_v1.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
