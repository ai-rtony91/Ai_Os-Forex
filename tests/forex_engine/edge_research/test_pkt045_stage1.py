"""PKT-045 Stage 1 routing and pre-score safety checks."""

from pathlib import Path
import json

import pytest

from automation.forex_engine.edge_research import batch
from scripts.forex_delivery import run_forex_control_baseline_rsi_filter_comparison_stage1_v1 as runner


def stage_root() -> Path:
    return Path(__file__).resolve().parents[3] / ".aios/staging/PKT_FOREX_045/stage1_occ84"


def test_stage1_scoring_commands_require_the_stage1_approval_flag():
    with pytest.raises(ValueError, match="EXPLICIT_PKT045_STAGE1_PERMISSION_REQUIRED"):
        runner.dispatch("acquire-pkt045-stage1", stage_root(), approved_pkt045_stage1=False)


def test_stage1_status_is_read_only_and_reports_no_score_before_acquisition():
    status = batch.pkt045_stage1_status(Path(__file__).resolve().parents[3], stage_root())
    assert status["packet_id"] == "PKT-FOREX-045"
    assert status["scoring_allowed"] is False
    assert status["market_trials_added"] == 0


def test_stage1_runner_exposes_bounded_resume_commands():
    assert "acquire-pkt045-stage1" in runner.__doc__ or hasattr(batch, "acquire_pkt045_stage1")
    assert hasattr(batch, "certify_pkt045_stage1")


def test_run_pkt045_stage1_transitions_without_an_owner_prompt(tmp_path, monkeypatch):
    root = tmp_path
    output = root / ".aios/staging/PKT_FOREX_045/stage1_occ84"
    output.mkdir(parents=True)

    def fake_acquire(_root, stage):
        receipt = stage / "receipts/PKT045_STAGE1_RAW_ACQUISITION_RECEIPT.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({"complete": True}), encoding="utf-8")
        return {"complete": True, "completed_objects": 2, "total_objects": 2}

    def fake_certify(_root, stage):
        receipt = stage / "certification/PKT045_STAGE1_CERTIFICATION_RECEIPT.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        payload = {"EXECUTABLE_DATA_CERTIFICATION": "PASS", "PAIR_COUNT": 58}
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(batch, "acquire_pkt045_stage1", fake_acquire)
    monkeypatch.setattr(batch, "certify_pkt045_stage1", fake_certify)

    result = batch.run_pkt045_stage1(root, output)

    assert result["PHASE"] == "CERTIFY"
    assert result["STATUS"] == "PASS"
    assert result["NEXT_PHASE"] == "RUN_FROZEN_AB"
    phases = json.loads((output / "checkpoints/phase_state.json").read_text(encoding="utf-8"))
    assert phases["NEXT_PHASE"] == "RUN_FROZEN_AB"
