from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

import automation.orchestration.research_campaign.aios_research_campaign_runner as runner_module


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_MODULE = "automation.orchestration.research_campaign.aios_research_campaign_runner"


def _campaign_payload() -> dict[str, Any]:
    return {
        "campaign_id": "forex-first-v1",
        "campaign_version": "1",
        "market_lanes": ["FOREX_EURUSD_PRIMARY", "CME_INDEX_FUTURES_COMPARISON"],
        "experiment_budget": 1,
        "edge_gates": {"min_oos_trade_count": 100},
        "freshness": {"progress_max_age_seconds": 600},
        "experiment_catalog": [
            {
                "experiment_id": "fixture-cheap-screen",
                "market_lane": "FOREX_EURUSD_PRIMARY",
                "strategy_family": "MOMENTUM",
                "instrument": "EUR_USD",
                "session_window": "LONDON_NY_OVERLAP",
                "stage": "CHEAP_SCREEN",
                "data_capability": {
                    "pinned": True,
                    "source_id": "fixture-forex",
                    "contract_definition_id": "EURUSD-2026",
                    "calendar_id": "forex-eurusd",
                    "pip_value": 10.0,
                    "cost_model_id": "fixture-costs-v1",
                },
                "cost_scenario": "BASELINE",
                "parameter_fingerprint": "fixture-v1",
                "expected_evidence_version": "1",
            }
        ],
    }


def _run_runner(
    tmp_path: Path,
    *arguments: str,
    campaign_payload: dict[str, Any] | None = None,
    outcomes: list[dict[str, Any]] | None = None,
    paper_evidence: dict[str, Any] | None = None,
    outcomes_raw_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    campaign_path = tmp_path / "campaign.json"
    outcomes_path = tmp_path / "outcomes.json"
    campaign_path.write_text(
        json.dumps(campaign_payload if campaign_payload is not None else _campaign_payload()),
        encoding="utf-8",
    )
    outcomes_path.write_text(
        outcomes_raw_text if outcomes_raw_text is not None else json.dumps(outcomes or []),
        encoding="utf-8",
    )
    runner_arguments = list(arguments)
    if paper_evidence is not None:
        evidence_path = tmp_path / "paper_evidence.json"
        evidence_path.write_text(json.dumps(paper_evidence), encoding="utf-8")
        runner_arguments.extend(["--paper-evidence-json", str(evidence_path)])
    return subprocess.run(
        [
            sys.executable,
            "-m",
            RUNNER_MODULE,
            "--campaign-json",
            str(campaign_path),
            "--outcomes-json",
            str(outcomes_path),
            *runner_arguments,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_dry_run_is_json_only_and_does_not_create_output_root(tmp_path: Path) -> None:
    output_root = tmp_path / "out"

    result = _run_runner(
        tmp_path, "--mode", "DRY_RUN", "--output-root", str(output_root)
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["mode"] == "DRY_RUN"
    assert result.stderr == ""
    assert not output_root.exists()


def test_apply_requires_explicit_sandbox_root_and_writes_only_checkpoint(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "out"

    result = _run_runner(tmp_path, "--mode", "APPLY", "--output-root", str(output_root))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["checkpoint"]["written"] is True
    assert Path(payload["checkpoint"]["path"]).is_relative_to(output_root)
    assert sorted(path.name for path in output_root.iterdir()) == [
        "campaign_checkpoint.json"
    ]


def test_apply_refuses_to_overwrite_checkpoint_for_a_changed_campaign(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "out"
    first = _run_runner(tmp_path, "--mode", "APPLY", "--output-root", str(output_root))
    assert first.returncode == 0

    campaign_path = tmp_path / "campaign.json"
    changed = json.loads(campaign_path.read_text(encoding="utf-8"))
    changed["campaign_version"] = "changed"
    campaign_path.write_text(json.dumps(changed), encoding="utf-8")
    outcomes_path = tmp_path / "outcomes.json"
    second = subprocess.run(
        [
            sys.executable,
            "-m",
            RUNNER_MODULE,
            "--campaign-json",
            str(campaign_path),
            "--outcomes-json",
            str(outcomes_path),
            "--mode",
            "APPLY",
            "--output-root",
            str(output_root),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert second.returncode == 2
    assert json.loads(second.stdout)["status"] == "BLOCKED"
    assert "campaign" in json.loads(second.stdout)["reason"]


def test_apply_accepts_a_strict_extension_of_persisted_history(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    first = _run_runner(tmp_path, "--mode", "APPLY", "--output-root", str(output_root))
    assert first.returncode == 0

    campaign = _campaign_payload()
    experiment = campaign["experiment_catalog"][0]
    fingerprint = hashlib.sha256(
        json.dumps(
            {key: value for key, value in experiment.items() if key != "experiment_id"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    (tmp_path / "outcomes.json").write_text(
        json.dumps(
            [
                {
                    "experiment_fingerprint": fingerprint,
                    "stage": "CHEAP_SCREEN",
                    "status": "ADVANCE",
                    "reason": "fixture",
                    "evidence_version": "1",
                    "completed_at_utc": "2026-10-05T12:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )
    second = subprocess.run(
        [
            sys.executable,
            "-m",
            RUNNER_MODULE,
            "--campaign-json",
            str(tmp_path / "campaign.json"),
            "--outcomes-json",
            str(tmp_path / "outcomes.json"),
            "--mode",
            "APPLY",
            "--output-root",
            str(output_root),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert second.returncode == 0
    assert json.loads(second.stdout)["checkpoint"]["written"] is True


def _paper_campaign_payload_and_outcomes() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    stages = [
        "CHEAP_SCREEN",
        "COST",
        "WALK_FORWARD",
        "TRUE_OOS",
        "STRESS",
        "REPLICATION",
        "PAPER",
    ]
    catalog = []
    for stage in stages:
        candidate = _campaign_payload()["experiment_catalog"][0].copy()
        candidate["experiment_id"] = f"runner-paper-{stage.lower()}"
        candidate["stage"] = stage
        candidate["parameter_fingerprint"] = "runner-paper-lineage-v1"
        catalog.append(candidate)
    outcomes = []
    for candidate in catalog[:-1]:
        fingerprint_payload = {
            key: value for key, value in candidate.items() if key != "experiment_id"
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        outcomes.append(
            {
                "experiment_fingerprint": fingerprint,
                "stage": candidate["stage"],
                "status": "ADVANCE",
                "reason": "fixture",
                "evidence_version": candidate["expected_evidence_version"],
                "completed_at_utc": "2026-10-05T12:00:00Z",
            }
        )
    payload = _campaign_payload()
    payload["experiment_catalog"] = catalog
    payload["experiment_budget"] = len(catalog)
    return payload, outcomes


def test_paper_evidence_is_candidate_bound_and_never_grants_live_authority(
    tmp_path: Path,
) -> None:
    campaign, outcomes = _paper_campaign_payload_and_outcomes()
    paper_candidate = campaign["experiment_catalog"][-1]
    fingerprint_payload = {
        key: value for key, value in paper_candidate.items() if key != "experiment_id"
    }
    paper_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    evidence = {
        "candidate_fingerprint": paper_fingerprint,
        "evidence_version": paper_candidate["expected_evidence_version"],
        "positive_oos_expectancy": True,
        "positive_stressed_expectancy": True,
        "profit_factor_after_costs": 1.10,
        "max_drawdown_pct": 10.0,
        "oos_trade_count": 100,
        "walk_forward_stable": True,
        "replication_stable": True,
        "nearby_parameter_stable": True,
        "no_profit_concentration": True,
        "performance_evidence": {
            "source_id": "fixture-forex",
            "cost_model_id": "fixture-costs-v1",
            "dataset_sha256": "a" * 64,
            "currency": "USD",
            "initial_equity": 10_000,
            "selection_frozen_at_utc": "2025-12-31T00:00:00Z",
            "oos_start_utc": "2026-01-01T00:00:00Z",
            "oos_end_utc": "2026-02-01T00:00:00Z",
            "trades": [
                {
                    "trade_id": str(index),
                    "closed_at_utc": "2026-01-02T00:00:00Z",
                    "gross_pnl": 3 if index % 2 == 0 else -1,
                    "base_cost": 0.2,
                    "stress_cost": 0.5,
                }
                for index in range(100)
            ],
        },
        "evidence": [
            {
                "category": "oos_validation",
                "source_id": "private-fixture-source",
                "version": "v1",
                "status": "PASS",
            }
        ],
    }

    result = _run_runner(
        tmp_path,
        "--mode",
        "DRY_RUN",
        campaign_payload=campaign,
        outcomes=outcomes,
        paper_evidence=evidence,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"]["status"] == "ADVANCE"
    assert payload["decision"]["next_experiment"]["stage"] == "PAPER"
    assert payload["paper_edge_gate"]["status"] == "PAPER_ELIGIBLE"
    assert payload["paper_edge_gate"]["live_authorization"] is False
    assert payload["evidence_score"]["live_authorization"] is False
    assert "private-fixture-source" not in json.dumps(payload["evidence_score"])
    assert payload["safety"]["live_authorization"] is False


def test_paper_gate_rejects_missing_or_wrong_evidence_without_waking(
    tmp_path: Path,
) -> None:
    campaign, outcomes = _paper_campaign_payload_and_outcomes()
    result = _run_runner(
        tmp_path,
        "--mode",
        "DRY_RUN",
        campaign_payload=campaign,
        outcomes=outcomes,
        paper_evidence={"candidate_fingerprint": "wrong"},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"]["status"] == "REJECT"
    assert payload["decision"]["reason"] == "PAPER_EDGE_GATE_REJECTED"
    assert payload["decision"]["sos_wake_required"] is False
    assert payload["paper_edge_gate"]["status"] == "REJECT"


def test_apply_validates_evidence_score_before_checkpoint_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from automation.orchestration.research_campaign.aios_research_campaign import (
        CampaignValidationError,
    )

    campaign, outcomes = _paper_campaign_payload_and_outcomes()
    candidate = campaign["experiment_catalog"][-1]
    fingerprint = hashlib.sha256(
        json.dumps(
            {key: value for key, value in candidate.items() if key != "experiment_id"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    evidence = {
        "candidate_fingerprint": fingerprint,
        "evidence_version": candidate["expected_evidence_version"],
        "positive_oos_expectancy": True,
        "positive_stressed_expectancy": True,
        "profit_factor_after_costs": 1.2,
        "max_drawdown_pct": 5,
        "oos_trade_count": 150,
        "walk_forward_stable": True,
        "replication_stable": True,
        "nearby_parameter_stable": True,
        "no_profit_concentration": True,
    }

    def fail_scoring(*args: Any, **kwargs: Any) -> Any:
        raise CampaignValidationError("invalid evidence score")

    def forbidden_write(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("checkpoint write happened before score validation")

    monkeypatch.setattr(runner_module, "score_evidence", fail_scoring)
    monkeypatch.setattr(runner_module, "write_checkpoint", forbidden_write)
    with pytest.raises(runner_module.RunnerInputError, match="invalid evidence score"):
        runner_module.run_once(
            campaign,
            outcomes,
            "APPLY",
            str(tmp_path / "checkpoint-output"),
            "2026-10-05T12:00:00Z",
            evidence,
        )


def test_apply_rejects_repository_output_root_before_creating_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_io(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("repository output root reached checkpoint I/O")

    monkeypatch.setattr(runner_module, "load_checkpoint", unexpected_io)
    monkeypatch.setattr(runner_module, "write_checkpoint", unexpected_io)
    with pytest.raises(runner_module.RunnerInputError, match="temporary directory"):
        runner_module.run_once(
            _campaign_payload(), [], "APPLY", str(REPO_ROOT), "2026-10-05T12:00:00Z"
        )


def test_runner_rejects_json_input_over_one_mib_before_parsing(
    tmp_path: Path,
) -> None:
    result = _run_runner(
        tmp_path,
        outcomes_raw_text="[] " + " " * (1024 * 1024),
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "BLOCKED"
    assert "1 MiB" in json.loads(result.stdout)["reason"]


def test_runner_rejects_deeply_nested_json_without_traceback(tmp_path: Path) -> None:
    nested = "[" * 10_000 + "0" + "]" * 10_000
    result = _run_runner(tmp_path, outcomes_raw_text=nested)

    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "BLOCKED"
    assert result.stderr == ""


def test_runner_api_blocks_deeply_nested_campaign_mapping() -> None:
    campaign = _campaign_payload()
    campaign["edge_gates"]["unused"] = [[[[[[[[[[0]]]]]]]]]]
    for _ in range(1_500):
        campaign["edge_gates"]["unused"] = [campaign["edge_gates"]["unused"]]

    with pytest.raises(runner_module.RunnerInputError):
        runner_module.run_once(
            campaign, [], "DRY_RUN", None, "2026-10-05T12:00:00Z"
        )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs are unavailable")
def test_runner_rejects_a_regular_input_replaced_by_fifo_during_open(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text("{}", encoding="utf-8")
    script = """
import os
import sys
from pathlib import Path
from automation.orchestration.research_campaign.aios_research_campaign_runner import (
    RunnerInputError, _read_json,
)
input_path = Path(sys.argv[1])
original_open = os.open
def replace_before_open(path, flags, *args, **kwargs):
    if Path(path) == input_path:
        input_path.unlink()
        os.mkfifo(input_path)
    return original_open(path, flags, *args, **kwargs)
os.open = replace_before_open
try:
    _read_json(str(input_path), "test input")
except RunnerInputError as error:
    assert "regular file" in str(error)
    print("BLOCKED")
else:
    raise AssertionError("replacement FIFO input unexpectedly accepted")
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", script, str(input_path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("runner blocked after its regular input was replaced by a FIFO")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "BLOCKED"


def test_repeated_empty_apply_preserves_the_original_progress_timestamp(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "checkpoint-output"
    first = _run_runner(
        tmp_path,
        "--mode",
        "APPLY",
        "--output-root",
        str(output_root),
        "--now-utc",
        "2026-10-05T12:00:00Z",
    )
    assert first.returncode == 0
    checkpoint_path = output_root / "campaign_checkpoint.json"
    first_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    second = _run_runner(
        tmp_path,
        "--mode",
        "APPLY",
        "--output-root",
        str(output_root),
        "--now-utc",
        "2026-10-05T12:05:00Z",
    )

    assert second.returncode == 0
    second_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert second_checkpoint["last_progress_utc"] == first_checkpoint["last_progress_utc"]


@pytest.mark.parametrize("supply_new_outcome", [False, True])
def test_apply_refuses_stale_active_checkpoint_without_changing_saved_history(
    tmp_path: Path, supply_new_outcome: bool
) -> None:
    campaign, history = _paper_campaign_payload_and_outcomes()
    output_root = tmp_path / "checkpoint-output"
    first = runner_module.run_once(
        campaign, history[:1], "APPLY", str(output_root), "2026-10-05T12:00:00Z"
    )
    checkpoint_path = Path(first["checkpoint"]["path"])
    saved_bytes = checkpoint_path.read_bytes()
    supplied = []
    if supply_new_outcome:
        supplied = history[:2]
        supplied[-1]["completed_at_utc"] = "2026-10-05T12:10:01Z"

    with pytest.raises(runner_module.RunnerInputError, match="progress_stale"):
        runner_module.run_once(
            campaign, supplied, "APPLY", str(output_root), "2026-10-05T12:10:01Z"
        )

    assert checkpoint_path.read_bytes() == saved_bytes
    assert sorted(path.name for path in output_root.iterdir()) == [
        "campaign_checkpoint.json"
    ]


@pytest.mark.parametrize("terminal", [False, True])
def test_apply_refuses_future_checkpoint_without_overwriting_it(
    tmp_path: Path, terminal: bool
) -> None:
    campaign, history = _paper_campaign_payload_and_outcomes()
    if terminal:
        history[0]["status"] = "REJECT"
    history[0]["completed_at_utc"] = "2026-10-05T12:00:01Z"
    output_root = tmp_path / "checkpoint-output"
    first = runner_module.run_once(
        campaign, history[:1], "APPLY", str(output_root), "2026-10-05T12:00:01Z"
    )
    checkpoint_path = Path(first["checkpoint"]["path"])
    saved_bytes = checkpoint_path.read_bytes()

    with pytest.raises(runner_module.RunnerInputError, match="future_timestamp"):
        runner_module.run_once(
            campaign, [], "APPLY", str(output_root), "2026-10-05T12:00:00Z"
        )

    assert checkpoint_path.read_bytes() == saved_bytes


def test_stale_rejected_catalog_remains_informational_on_apply_resume(
    tmp_path: Path,
) -> None:
    campaign = _campaign_payload()
    _, history = _paper_campaign_payload_and_outcomes()
    history[0]["status"] = "REJECT"
    history[0]["experiment_fingerprint"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in campaign["experiment_catalog"][0].items() if key != "experiment_id"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    output_root = tmp_path / "checkpoint-output"
    runner_module.run_once(
        campaign, history[:1], "APPLY", str(output_root), "2026-10-05T12:00:00Z"
    )

    resumed = runner_module.run_once(
        campaign, [], "APPLY", str(output_root), "2026-10-06T12:00:00Z"
    )

    assert resumed["decision"]["status"] == "NO_EDGE_IN_SCOPE"
    assert resumed["decision"]["sos_wake_required"] is False


@pytest.mark.parametrize("existing_checkpoint", [False, True])
def test_apply_cannot_replace_evidence_written_after_its_checkpoint_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing_checkpoint: bool
) -> None:
    from automation.orchestration.research_campaign.aios_research_campaign import (
        CampaignSpec,
        build_checkpoint,
        run_campaign_cycle,
    )

    campaign = _campaign_payload()
    spec = CampaignSpec.from_dict(campaign)
    now = "2026-10-05T12:00:00Z"
    output_root = tmp_path / "checkpoint-output"
    if existing_checkpoint:
        runner_module.run_once(campaign, [], "APPLY", str(output_root), now)
    write_checkpoint = runner_module.write_checkpoint
    competing_evidence = {
        "evidence": [{
            "category": "cost_model",
            "source_id": "newer-fixture-evidence",
            "version": "1",
            "status": "PASS",
        }]
    }
    competing_payload = build_checkpoint(
        spec,
        [],
        run_campaign_cycle(spec, [], now, competing_evidence),
        now,
        paper_evidence=competing_evidence,
    )

    def competing_write(root: Path, payload: dict[str, Any], **kwargs: Any) -> Path:
        write_checkpoint(root, competing_payload)
        return write_checkpoint(root, payload, **kwargs)

    monkeypatch.setattr(runner_module, "write_checkpoint", competing_write)

    with pytest.raises(runner_module.RunnerInputError, match="revision"):
        runner_module.run_once(campaign, [], "APPLY", str(output_root), now)

    saved = json.loads((output_root / "campaign_checkpoint.json").read_text(encoding="utf-8"))
    assert saved["routing_context"]["route_inputs"]["paper_evidence"]["evidence"][0]["source_id"] == "newer-fixture-evidence"
    assert sorted(path.name for path in output_root.iterdir()) == [
        "campaign_checkpoint.json"
    ]


def test_apply_rejects_symlink_escape_before_creating_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symlink_root = tmp_path / "symlink-output"
    symlink_root.symlink_to(REPO_ROOT, target_is_directory=True)

    def unexpected_io(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("symlink escape reached checkpoint I/O")

    monkeypatch.setattr(runner_module, "load_checkpoint", unexpected_io)
    monkeypatch.setattr(runner_module, "write_checkpoint", unexpected_io)
    try:
        with pytest.raises(runner_module.RunnerInputError):
            runner_module.run_once(
                _campaign_payload(),
                [],
                "APPLY",
                str(symlink_root),
                "2026-10-05T12:00:00Z",
            )
    finally:
        symlink_root.unlink(missing_ok=True)


def test_apply_rejects_checkpoint_file_symlink_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root = tmp_path / "checkpoint-output"
    output_root.mkdir()
    target = tmp_path / "external-checkpoint.json"
    target.write_text("{}", encoding="utf-8")
    (output_root / "campaign_checkpoint.json").symlink_to(target)

    def unexpected_io(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("checkpoint symlink reached read or write")

    monkeypatch.setattr(runner_module, "load_checkpoint", unexpected_io)
    monkeypatch.setattr(runner_module, "write_checkpoint", unexpected_io)
    with pytest.raises(runner_module.RunnerInputError, match="must not be a symlink"):
        runner_module.run_once(
            _campaign_payload(),
            [],
            "APPLY",
            str(output_root),
            "2026-10-05T12:00:00Z",
        )
