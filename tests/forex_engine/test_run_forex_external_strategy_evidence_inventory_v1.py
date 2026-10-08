import json
import sys

from scripts.forex_delivery import run_forex_external_strategy_evidence_inventory_v1 as runner


def test_runner_routes_exact_paths(monkeypatch, tmp_path, capsys):
    observed = {}
    monkeypatch.setattr(runner, "build_inventory", lambda path: observed.setdefault("source", path) or {})

    def fake_write(inventory, state, report, proposal, runtime):
        observed["write"] = (state, report, proposal, runtime)
        return {"status": "PASS"}

    monkeypatch.setattr(runner, "write_outputs", fake_write)
    args = ["runner", "run", "--report-root", str(tmp_path), "--state-path", str(tmp_path / "state"), "--report-path", str(tmp_path / "report"), "--proposal-path", str(tmp_path / "proposal"), "--runtime-root", str(tmp_path / "runtime")]
    monkeypatch.setattr(sys, "argv", args)
    assert runner.main() == 0
    assert observed["source"] == tmp_path
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
