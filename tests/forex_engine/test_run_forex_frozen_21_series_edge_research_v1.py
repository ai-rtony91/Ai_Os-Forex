from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path("scripts/forex_delivery/run_forex_frozen_21_series_edge_research_v1.py")


def load_script():
    spec = importlib.util.spec_from_file_location("phase1_cli", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_cli_requires_subcommand():
    module = load_script()
    try:
        module.parser().parse_args([])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("CLI accepted a missing command")


def test_cli_returns_two_for_bounded_block(monkeypatch, tmp_path, capsys):
    module = load_script()

    def blocked(**_kwargs):
        raise module.ResearchBlocked("EXACT_TEST_BLOCKER")

    monkeypatch.setattr(module, "run_phase1", blocked)
    code = module.main(["run", "--dataset-root", str(tmp_path), "--output-root", str(tmp_path / "output")])
    assert code == 2
    assert '"status": "BLOCKED"' in capsys.readouterr().out


def test_cli_outputs_bounded_success_summary(monkeypatch, tmp_path, capsys):
    module = load_script()
    monkeypatch.setattr(module, "run_phase1", lambda **_kwargs: {
        "status": "PHASE1_EXHAUSTED_NO_CANDIDATE", "dataset_id": "D", "dataset_sha256": "H",
        "series_processed": 21, "candles_streamed": 10, "candidate_count": 24,
        "survivor_count": 0, "survivors": [], "sealed_holdout_status": "NOT_EVALUATED",
    })
    code = module.main(["run", "--dataset-root", str(tmp_path), "--output-root", str(tmp_path / "output")])
    output = capsys.readouterr().out
    assert code == 0 and "candidate_results" not in output and "PHASE1_EXHAUSTED_NO_CANDIDATE" in output
