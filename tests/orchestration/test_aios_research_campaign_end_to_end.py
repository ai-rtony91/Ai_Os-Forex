from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Any

from automation.orchestration.research_campaign.aios_research_campaign import (
    CampaignSpec,
    ExperimentOutcome,
    experiment_fingerprint,
)
from automation.orchestration.research_campaign.aios_research_campaign_runner import (
    BLOCKED_CAPABILITIES,
)

from automation.orchestration.watchdog.aios_deadman_watchdog import (
    evaluate_campaign_health,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_MODULE = "automation.orchestration.research_campaign.aios_research_campaign_runner"
NOW_TEXT = "2026-10-05T12:00:00Z"
NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)


def _experiment(experiment_id: str, parameter_fingerprint: str) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
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
        "parameter_fingerprint": parameter_fingerprint,
        "expected_evidence_version": "1",
    }


def _campaign_and_outcomes() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    campaign = {
        "campaign_id": "bridge-fixture-v1",
        "campaign_version": "1",
        "market_lanes": ["FOREX_EURUSD_PRIMARY", "CME_INDEX_FUTURES_COMPARISON"],
        "experiment_budget": 2,
        "edge_gates": {"min_oos_trade_count": 100},
        "freshness": {"progress_max_age_seconds": 600},
        "experiment_catalog": [
            _experiment("fixture-a", "parameters-a"),
            _experiment("fixture-b", "parameters-b"),
        ],
    }
    spec = CampaignSpec.from_dict(campaign)
    completed = spec.catalog[0]
    outcome = ExperimentOutcome.from_dict(
        {
            "experiment_fingerprint": experiment_fingerprint(completed),
            "stage": completed.stage,
            "status": "ADVANCE",
            "reason": "fixture-only completed research step",
            "evidence_version": completed.expected_evidence_version,
            "completed_at_utc": "2026-10-05T11:59:30Z",
        }
    )
    return campaign, [outcome.to_dict()]


def test_apply_checkpoint_is_accepted_by_watchdog_without_arming_capabilities(
    tmp_path: Path,
) -> None:
    campaign, outcomes = _campaign_and_outcomes()
    campaign_path = tmp_path / "campaign.json"
    outcomes_path = tmp_path / "outcomes.json"
    output_root = tmp_path / "checkpoint-output"
    campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
    outcomes_path.write_text(json.dumps(outcomes), encoding="utf-8")

    completed = subprocess.run(
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
            "--now-utc",
            NOW_TEXT,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    checkpoint_path = Path(result["checkpoint"]["path"])
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    health = evaluate_campaign_health(checkpoint, NOW, 600)

    assert result["mode"] == "APPLY"
    assert checkpoint_path.is_relative_to(output_root)
    assert health["status"] == "OK"
    assert health["reason"] == "campaign_progress_fresh"
    assert health["wake_class"] == "NO_WAKE"
    assert health["live_delivery_armed"] is False
    assert result["safety"]["blocked_capabilities"] == BLOCKED_CAPABILITIES
    assert result["safety"]["live_authorization"] is False
    assert result["decision"]["live_authorization"] is False
