import argparse
import json
import sys

import pytest

from scripts.forex_delivery import run_forex_cross_sectional_short_horizon_reversal_v1 as runner


def test_runner_requires_exact_arguments(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["runner", "run"])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


def test_runner_refuses_output_collision(tmp_path):
    output = tmp_path / "runtime"
    output.mkdir()
    (output / "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CONTRACT.json").write_text("existing", encoding="utf-8")
    destinations = runner.artifact_destinations(output, tmp_path / "report.md", tmp_path / "rejection.json")
    with pytest.raises(FileExistsError, match="OUTPUT_COLLISION"):
        runner.require_absent(destinations)


def test_artifact_comparison_detects_and_accepts_bytes():
    runner.compare_artifacts({"a": b"x"}, {"a": b"x"})
    with pytest.raises(ValueError, match="BYTE_MISMATCH"):
        runner.compare_artifacts({"a": b"x"}, {"a": b"y"})


def test_execute_runs_twice_then_promotes(monkeypatch, tmp_path):
    observed = {"research": 0}
    artifacts = {
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CONTRACT.json": b"{}\n",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CANDIDATE_REGISTRY.json": b"{}\n",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RESULTS.json": b"{}\n",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_CHECKPOINT.json": b"{}\n",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_MANIFEST.json": b"{}\n",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RECEIPT.json": json.dumps({"status": "CLOSED_FAILED_POSTMORTEM_COMPLETE", "acceptance_status": "PASS", "candidate_count": 12, "survivor_count": 0, "best_candidate": "x", "holdout_status": "NOT_EVALUATED"}).encode(),
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_V1_REPORT.md": b"report\n",
        "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_REJECTION_V1.json": b"{}\n",
    }

    def fake_research(*_args, **_kwargs):
        observed["research"] += 1
        return {}

    monkeypatch.setattr(runner, "research", fake_research)
    monkeypatch.setattr(runner, "build_artifacts", lambda *_args: dict(artifacts))
    stage = tmp_path / "stage"
    stage.mkdir()
    monkeypatch.setattr(runner.tempfile, "mkdtemp", lambda **_kwargs: str(stage))
    args = argparse.Namespace(corpus_root=tmp_path / "corpus", output_root=tmp_path / "out", report_path=tmp_path / "report.md", rejection_path=tmp_path / "rejection.json", rejection_source=[], max_timestamps=10)
    result = runner.execute(args)
    assert observed["research"] == 2 and result["deterministic_artifact_count"] == 8
    assert (tmp_path / "out" / "AIOS_FOREX_CROSS_SECTIONAL_SHORT_HORIZON_REVERSAL_RECEIPT.json").is_file()
