import json
import sys

from scripts.forex_delivery import run_forex_currency_factor_regime_allocation_v1 as runner


def test_runner_requires_all_bounded_arguments(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["runner", "run"])
    try:
        runner.main()
    except SystemExit as exc:
        assert exc.code == 2


def test_runner_routes_exact_paths(monkeypatch, tmp_path, capsys):
    dataset = tmp_path / "dataset"
    packet = tmp_path / "packet.txt"
    predecessor = tmp_path / "predecessor.json"
    output = tmp_path / "out"
    report = tmp_path / "report.md"
    rejection = tmp_path / "rejection.json"
    observed = {}

    def fake_research(dataset_root, packet_path, predecessor_path):
        observed["research"] = (dataset_root, packet_path, predecessor_path)
        return {"status": "CLOSED_FAILED_POSTMORTEM_COMPLETE"}

    def fake_write(result, output_root, report_path, rejection_path, code_path):
        observed["write"] = (result, output_root, report_path, rejection_path, code_path)
        return {"status": result["status"]}

    monkeypatch.setattr(runner, "research", fake_research)
    monkeypatch.setattr(runner, "write_outputs", fake_write)
    monkeypatch.setattr(sys, "argv", ["runner", "run", "--dataset-root", str(dataset), "--packet-path", str(packet), "--predecessor-rejection", str(predecessor), "--output-root", str(output), "--report-path", str(report), "--rejection-path", str(rejection)])
    assert runner.main() == 0
    assert observed["research"] == (dataset, packet, predecessor)
    assert observed["write"][1:4] == (output, report, rejection)
    assert json.loads(capsys.readouterr().out)["status"] == "CLOSED_FAILED_POSTMORTEM_COMPLETE"
