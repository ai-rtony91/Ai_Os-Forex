from __future__ import annotations

import json
from pathlib import Path

from automation.forex_engine.forex_autonomous_campaign_manager_v1 import (
    CAMPAIGN_ID,
    CampaignDecision,
    CampaignState,
    DECISION_STATUS_COMPLETE,
    DECISION_STATUS_STAGE_SELECTED,
    CampaignStage,
    build_campaign_checkpoint,
    build_default_forex_campaign_stages,
    build_next_codex_prompt,
    collect_campaign_state,
    build_final_repository_completion_snapshot,
    build_non_executing_pre_live_package,
    select_next_campaign_stage,
)


def test_default_stages_have_required_ids_and_order():
    stages = build_default_forex_campaign_stages()
    stage_ids = tuple(stage.stage_id for stage in stages)

    assert stage_ids == (
        "FLOW2_EVIDENCE_COUNTDOWN_LANDING",
        "LIVE_CAPABILITY_GOVERNANCE_GATE",
        "PROFIT_LOOP_ACCELERATION_GATE",
        "BROKER_DEMO_TO_LIVE_GATE_PREFLIGHT_MAP",
        "FINAL_OWNER_REPORT",
    )


def test_selects_first_incomplete_stage():
    state = CampaignState(
        campaign_id=CAMPAIGN_ID,
        current_branch="main",
        head="abc123",
        dirty_files=(),
        completed_stage_ids=("FLOW2_EVIDENCE_COUNTDOWN_LANDING",),
        active_stage_id="",
        hard_blockers=(),
    )

    decision = select_next_campaign_stage(state)

    assert decision.status == DECISION_STATUS_STAGE_SELECTED
    assert decision.selected_stage_id == "LIVE_CAPABILITY_GOVERNANCE_GATE"
    assert decision.next_action == "RUN_SELECTED_STAGE"


def test_continues_active_stage_when_not_completed():
    state = CampaignState(
        campaign_id=CAMPAIGN_ID,
        current_branch="main",
        head="abc123",
        dirty_files=(),
        completed_stage_ids=("FLOW2_EVIDENCE_COUNTDOWN_LANDING",),
        active_stage_id="LIVE_CAPABILITY_GOVERNANCE_GATE",
        hard_blockers=(),
    )
    decision = select_next_campaign_stage(state)

    assert decision.status == DECISION_STATUS_STAGE_SELECTED
    assert decision.selected_stage_id == "LIVE_CAPABILITY_GOVERNANCE_GATE"


def test_returns_complete_when_all_stages_done():
    all_stage_ids = tuple(stage.stage_id for stage in build_default_forex_campaign_stages())
    state = CampaignState(
        campaign_id=CAMPAIGN_ID,
        current_branch="main",
        head="abc123",
        dirty_files=(),
        completed_stage_ids=all_stage_ids,
        active_stage_id="",
        hard_blockers=(),
    )
    decision = select_next_campaign_stage(state)

    assert decision.status == DECISION_STATUS_COMPLETE
    assert decision.selected_stage_id == ""
    assert decision.next_action == "OPEN_FINAL_OWNER_REVIEW"


def test_blocks_on_hard_blockers():
    state = CampaignState(
        campaign_id=CAMPAIGN_ID,
        current_branch="main",
        head="abc123",
        dirty_files=(),
        completed_stage_ids=(),
        active_stage_id="",
        hard_blockers=("secret file detected",),
    )
    decision = select_next_campaign_stage(state)

    assert decision.status == "CAMPAIGN_BLOCKED"
    assert decision.next_action == "RESOLVE_CAMPAIGN_BLOCKERS"
    assert decision.blockers == ("secret file detected",)


def test_blocks_on_unknown_dirty_files():
    state = CampaignState(
        campaign_id=CAMPAIGN_ID,
        current_branch="main",
        head="abc123",
        dirty_files=("outside/unknown_file.py",),
        completed_stage_ids=(),
        active_stage_id="",
        hard_blockers=(),
    )
    decision = select_next_campaign_stage(state)

    assert decision.status == "CAMPAIGN_BLOCKED"
    assert decision.blockers == ("outside/unknown_file.py",)


def test_campaign_decision_to_dict_is_json_safe():
    decision = CampaignDecision(
        status=DECISION_STATUS_STAGE_SELECTED,
        selected_stage_id="FLOW2_EVIDENCE_COUNTDOWN_LANDING",
        next_action="RUN_SELECTED_STAGE",
        blockers=("blocker",),
        allowed_paths=("a", "b"),
        validators=("check",),
    )
    payload = decision.to_dict()
    json_text = json.dumps(payload)
    parsed = json.loads(json_text)

    assert isinstance(parsed["blockers"], list)
    assert isinstance(parsed["allowed_paths"], list)
    assert isinstance(parsed["validators"], list)
    assert parsed["selected_stage_id"] == "FLOW2_EVIDENCE_COUNTDOWN_LANDING"


def test_checkpoint_includes_required_parts():
    state = CampaignState(
        campaign_id=CAMPAIGN_ID,
        current_branch="main",
        head="abc123",
        dirty_files=(),
        completed_stage_ids=(),
        active_stage_id="",
        hard_blockers=(),
    )
    decision = select_next_campaign_stage(state)
    checkpoint = build_campaign_checkpoint(decision=decision, state=state)

    assert "# AIOS Forex Autonomy Checkpoint" in checkpoint
    assert "Campaign ID: AIOS_FOREX_AUTONOMY_FINISHER_V4" in checkpoint
    assert "Selected stage:" in checkpoint
    assert "Safety boundary" in checkpoint


def test_prompt_starts_with_codex_marker():
    state = collect_campaign_state()
    decision = select_next_campaign_stage(state)
    prompt = build_next_codex_prompt(decision=decision, state=state)

    assert prompt.startswith("CODEX-ONLY PROMPT")
    assert "AI_OS EXECUTION TOKEN" in prompt
    assert "AI_OS BOOTSTRAP REQUIRED" in prompt


def test_prompt_contains_required_markers():
    state = collect_campaign_state()
    decision = select_next_campaign_stage(state)
    prompt = build_next_codex_prompt(decision=decision, state=state)

    required_markers = [
        "IDENTITY MARKER",
        "ALLOWED PATHS",
        "FORBIDDEN PATHS",
        "APPROVAL AUTHORITY",
        "VALIDATOR CHAIN",
        "STOP POINT",
        "FINAL REPORT FORMAT",
    ]
    for marker in required_markers:
        assert marker in prompt


def test_no_forbidden_imports_or_live_execution_logic():
    source = Path("automation/forex_engine/forex_autonomous_campaign_manager_v1.py").read_text(encoding="utf-8")
    forbidden_tokens = [
        "import ccxt",
        "from ccxt import",
        "import requests",
        "from requests import",
        "import httpx",
        "from httpx import",
        "import oandapy",
        "from oandapy",
        "place_order(",
        "submit_order(",
        "execute_order(",
        "create_order(",
        "send_order(",
        "live_trade",
    ]

    lowered = source.lower()
    for token in forbidden_tokens:
        assert token not in lowered


def test_state_file_default_snapshot_has_expected_fields():
    state = collect_campaign_state()
    sample = {
        "campaign_id": state.campaign_id,
        "current_branch": state.current_branch,
        "head": state.head,
        "dirty_files": list(state.dirty_files),
        "completed_stage_ids": list(state.completed_stage_ids),
        "active_stage_id": state.active_stage_id,
        "hard_blockers": list(state.hard_blockers),
    }

    payload = json.dumps(sample)
    loaded = json.loads(payload)

    assert loaded["campaign_id"] == CAMPAIGN_ID
    assert isinstance(loaded["dirty_files"], list)
    assert isinstance(loaded["completed_stage_ids"], list)


def test_final_repository_completion_snapshot_separates_external_blockers():
    snapshot = build_final_repository_completion_snapshot()

    assert snapshot["repository_fixable_completion_percent"] == 100
    assert snapshot["repository_fixable_blockers_remaining"] == []
    assert "current_broker_account_evidence" in snapshot["external_evidence_blockers"]
    assert "broker_connectivity" in snapshot["broker_runtime_blockers"]
    assert snapshot["autonomy_safety_flags"]["live_execution_allowed"] is False
    assert snapshot["autonomy_safety_flags"]["order_placement_allowed"] is False
    assert snapshot["profitability_proven"] is False
    assert snapshot["withdrawal_proven"] is False
    assert snapshot["next_generated_packet"].startswith("CODEX-ONLY PROMPT")


def test_pre_live_package_is_non_executing_and_sealed():
    package = build_non_executing_pre_live_package()

    assert package["package_status"] == "SEALED_FOR_OWNER_REVIEW_ONLY"
    for value in package["required_flags"].values():
        assert value is False
    assert "protected_one_shot_command_package_sealed" in package["artifacts"]
    assert "first_realized_profitable_withdrawable_dollar_evidence_contract" in package["artifacts"]
