"""Tests for the offline Forex promotion pipeline module."""

from __future__ import annotations

import json
from pathlib import Path

from automation.forex_engine.forex_promotion_pipeline_v1 import (
    NEXT_ACTION_COLLECT_MISSING,
    PromotionDecision,
    PromotionGate,
    PromotionState,
    build_default_promotion_gates,
    build_next_codex_packet,
    build_owner_approval_card,
    build_promotion_checkpoint,
    build_report,
    build_state_payload,
    collect_available_promotion_evidence,
    evaluate_promotion_pipeline,
    evaluate_and_write_artifacts,
    DECISION_STATUS_BLOCKED,
    DECISION_STATUS_BROKER_REQUIRED,
    DECISION_STATUS_COMPLETE,
    DECISION_STATUS_GATE_SELECTED,
    DECISION_STATUS_OWNER_REQUIRED,
    DECISION_STATUS_READY_FOR_REVIEW,
    PIPELINE_ID,
    SAFETY_BOUNDARY,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("evidence", encoding="utf-8")


def _create_all_gate_evidence_paths(root: Path) -> list[Path]:
    relative_paths = (
        "Reports/forex_delivery/AIOS_FOREX_FLOW2_SUPERVISED_DEMO_EVIDENCE_COUNTDOWN_CAPTURE_V1_REPORT.md",
        "Reports/forex_delivery/AIOS_FOREX_PAPER_SESSION_SAMPLE_GENERATOR_V1_REPORT.md",
        "Reports/forex_delivery/AIOS_FOREX_PAPER_PROFITABILITY_EVALUATOR_V1_REPORT.md",
        "automation/forex_engine/walkforward_validation_harness.py",
        "Reports/forex_delivery/AIOS_FOREX_WALKFORWARD_VALIDATION_HARNESS_V1_REPORT.md",
        "automation/forex_engine/strategy_evaluation_harness.py",
        "Reports/forex_delivery/AIOS_FOREX_STRATEGY_EVALUATION_HARNESS_V1_REPORT.md",
        "Reports/forex_delivery/AIOS_FOREX_DEMO_READINESS_SPINE_V1_REPORT.md",
        "automation/forex_engine/paper_demo_broker_adapter.py",
        "Reports/forex_delivery/AIOS_FOREX_C1_DEMO_ORDER_INTENT_OWNER_APPROVAL_GATE_V1_REPORT.md",
        "Reports/forex_delivery/AIOS_FOREX_RISK_GOVERNOR_V1_REPORT.md",
        "Reports/forex_delivery/AIOS_FOREX_C1_RISK_POSITION_SIZING_REVIEW_V1_REPORT.md",
        "Reports/forex_delivery/AIOS_FOREX_BROKER_INTEGRATION_READINESS_FINAL_REVIEW_PACKET_J_V1.md",
        "Reports/forex_delivery/AIOS_FOREX_C1_SUPERVISED_DEMO_BROKER_ACCOUNT_READINESS_BRIDGE_V1_REPORT.md",
        "Reports/forex_delivery/AIOS_FOREX_ONE_SHOT_LIVE_MICRO_TRADE_ARMING_REVIEW_DRY_RUN_V1.md",
        "Reports/forex_delivery/AIOS_FOREX_FINAL_CLOSURE_AUDIT_LANE_V1_REPORT.md",
        "Reports/forex_delivery/AIOS_FOREX_PROMOTION_PIPELINE_V1_OWNER_APPROVAL_CARD.md",
    )
    paths = [root / rel for rel in relative_paths]
    for path in paths:
        _touch(path)
    return paths


def _state(
    *,
    pipeline_id: str = PIPELINE_ID,
    available_evidence: tuple[str, ...] = (),
    passed_gates: tuple[str, ...] = (),
    blocked_reasons: tuple[str, ...] = (),
    owner_approved: bool = False,
    broker_ready: bool = False,
) -> PromotionState:
    return PromotionState(
        pipeline_id=pipeline_id,
        available_evidence=available_evidence,
        passed_gates=passed_gates,
        blocked_reasons=blocked_reasons,
        owner_approved=owner_approved,
        broker_ready=broker_ready,
    )


def test_build_default_promotion_gates_order():
    gates = build_default_promotion_gates()
    assert tuple(gate.gate_id for gate in gates) == (
        "PAPER_EVIDENCE_SUFFICIENCY",
        "STRATEGY_VALIDATION_EVIDENCE",
        "DEMO_ENVIRONMENT_READINESS",
        "RISK_LIMIT_VERIFICATION",
        "BROKER_ACCOUNT_READINESS",
        "OWNER_APPROVAL_GATE",
        "LIVE_ARMING_REVIEW",
    )


def test_missing_evidence_selects_first_gate():
    state = _state()
    decision = evaluate_promotion_pipeline(
        state,
        gates=build_default_promotion_gates(),
        repo_root=Path("C:/tmp/empty-repo"),
    )
    assert decision.status == DECISION_STATUS_GATE_SELECTED
    assert decision.selected_gate_id == "PAPER_EVIDENCE_SUFFICIENCY"
    assert decision.missing_evidence
    assert decision.next_action == NEXT_ACTION_COLLECT_MISSING


def test_hard_blocker_returns_promotion_blocked():
    state = _state(blocked_reasons=("hard_blocker",))
    decision = evaluate_promotion_pipeline(
        state,
        gates=build_default_promotion_gates(),
        repo_root=Path("C:/tmp/empty-repo"),
    )
    assert decision.status == DECISION_STATUS_BLOCKED
    assert "hard_blocker" in decision.required_owner_actions


def test_broker_gate_requires_broker_readiness(tmp_path: Path):
    root = tmp_path
    _create_all_gate_evidence_paths(root=root)[:13]

    state = _state()
    decision = evaluate_promotion_pipeline(
        state,
        gates=build_default_promotion_gates(),
        repo_root=root,
    )
    assert decision.status == DECISION_STATUS_BROKER_REQUIRED
    assert decision.selected_gate_id == "BROKER_ACCOUNT_READINESS"


def test_human_gate_requires_owner_approval(tmp_path: Path):
    root = tmp_path
    _create_all_gate_evidence_paths(root=root)[:13]

    state = _state(owner_approved=False, broker_ready=True)
    decision = evaluate_promotion_pipeline(
        state,
        gates=build_default_promotion_gates(),
        repo_root=root,
    )
    assert decision.status == DECISION_STATUS_OWNER_REQUIRED
    assert decision.selected_gate_id == "OWNER_APPROVAL_GATE"



def test_evaluate_and_write_does_not_mark_owner_gate_passed_without_owner_approval(tmp_path: Path):
    root = tmp_path / "repo"
    _create_all_gate_evidence_paths(root=root)

    state, decision, _available = evaluate_and_write_artifacts(
        repo_root=root,
        state_path=tmp_path / "state.json",
        checkpoint_path=tmp_path / "checkpoint.md",
        owner_approval_card_path=tmp_path / "owner-card.md",
        next_codex_packet_path=tmp_path / "next-packet.md",
        report_path=tmp_path / "report.md",
        owner_approved=False,
        broker_ready=True,
    )

    assert decision.status == DECISION_STATUS_OWNER_REQUIRED
    assert decision.selected_gate_id == "OWNER_APPROVAL_GATE"
    assert "OWNER_APPROVAL_GATE" not in state.passed_gates
    checkpoint = (tmp_path / "checkpoint.md").read_text(encoding="utf-8")
    owner_section = checkpoint.split("- OWNER_APPROVAL_GATE:", 1)[1].split("- LIVE_ARMING_REVIEW:", 1)[0]
    assert "status: pending" in owner_section

def test_complete_when_all_gates_passed(tmp_path: Path):
    root = tmp_path
    _create_all_gate_evidence_paths(root=root)

    state = _state(owner_approved=True, broker_ready=True)
    decision = evaluate_promotion_pipeline(
        state,
        gates=build_default_promotion_gates(),
        repo_root=root,
    )
    assert decision.status == DECISION_STATUS_COMPLETE
    assert decision.next_action


def test_state_payload_is_json_safe():
    state = _state(
        available_evidence=("a", "b"),
        passed_gates=("g1", "g2"),
    )
    decision = PromotionDecision(
        status=DECISION_STATUS_READY_FOR_REVIEW,
        selected_gate_id="PAPER_EVIDENCE_SUFFICIENCY",
        next_action="OPEN",
        missing_evidence=("missing",),
        required_owner_actions=("resolve",),
        safety_boundary=SAFETY_BOUNDARY,
    )

    payload = build_state_payload(
        state=state,
        decision=decision,
        available_evidence=state.available_evidence,
    )
    roundtrip = json.loads(json.dumps(payload))
    assert isinstance(roundtrip["available_evidence"], list)
    assert isinstance(roundtrip["missing_evidence"], list)
    assert isinstance(roundtrip["required_owner_actions"], list)
    assert roundtrip["pipeline_id"] == PIPELINE_ID


def test_checkpoint_contains_safety_boundary():
    state = _state()
    decision = PromotionDecision(
        status=DECISION_STATUS_COMPLETE,
        selected_gate_id="",
        next_action="OPEN",
        missing_evidence=(),
        required_owner_actions=("no_action",),
        safety_boundary=SAFETY_BOUNDARY,
    )
    checkpoint = build_promotion_checkpoint(
        state=state,
        decision=decision,
        available_evidence=(),
    )
    assert SAFETY_BOUNDARY in checkpoint
    assert "## Next safe command" in checkpoint


def test_owner_approval_card_mentions_no_trade_authorization():
    state = _state(passed_gates=("PAPER_EVIDENCE_SUFFICIENCY",))
    decision = PromotionDecision(
        status=DECISION_STATUS_READY_FOR_REVIEW,
        selected_gate_id="OWNER_APPROVAL_GATE",
        next_action="OPEN",
        missing_evidence=(),
        required_owner_actions=("approve",),
        safety_boundary=SAFETY_BOUNDARY,
    )
    card = build_owner_approval_card(
        state=state,
        decision=decision,
        available_evidence=state.available_evidence,
    )
    assert "AIOS is not authorized to place trades from this packet." in card


def test_next_codex_packet_starts_with_codemarker_and_contains_required_sections():
    state = _state()
    decision = PromotionDecision(
        status=DECISION_STATUS_BROKER_REQUIRED,
        selected_gate_id="BROKER_ACCOUNT_READINESS",
        next_action="PREPARE_BROKER_READINESS_REVIEW",
        missing_evidence=(),
        required_owner_actions=("one",),
        safety_boundary=SAFETY_BOUNDARY,
    )
    packet = build_next_codex_packet(state=state, decision=decision)
    assert packet.startswith("CODEX-ONLY PROMPT")
    assert "AI_OS EXECUTION TOKEN" in packet
    assert "AI_OS BOOTSTRAP REQUIRED" in packet
    assert "IDENTITY MARKER" in packet
    assert "ALLOWED PATHS" in packet
    assert "FORBIDDEN PATHS" in packet
    assert "VALIDATOR CHAIN" in packet
    assert "STOP POINT" in packet
    assert "FINAL REPORT FORMAT" in packet


def test_source_has_no_forbidden_live_or_network_imports():
    source = Path("automation/forex_engine/forex_promotion_pipeline_v1.py").read_text(encoding="utf-8").lower()
    forbidden_tokens = (
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "import ccxt",
        "from ccxt",
        "place_order(",
        "execute_order(",
        "submit_order(",
        "live_trade",
    )
    for token in forbidden_tokens:
        assert token not in source


def test_evidence_detection_is_path_based(tmp_path: Path):
    root = tmp_path
    evidence_file = root / "Reports/forex_delivery/AIOS_FOREX_FLOW2_SUPERVISED_DEMO_EVIDENCE_COUNTDOWN_CAPTURE_V1_REPORT.md"
    _touch(evidence_file)
    _touch(root / "Reports/forex_delivery/AIOS_FOREX_PAPER_SESSION_SAMPLE_GENERATOR_V1_REPORT.md")

    available = collect_available_promotion_evidence(root)
    assert "flow2_evidence_countdown_complete" in available
    assert "paper_trade_sample_present" in available
    assert "daily_stop_policy_present" not in available
    assert "broker_readiness_checklist_present" not in available


def test_report_contains_expected_fields():
    state = _state()
    decision = PromotionDecision(
        status=DECISION_STATUS_READY_FOR_REVIEW,
        selected_gate_id="PAPER_EVIDENCE_SUFFICIENCY",
        next_action="OPEN",
        missing_evidence=(),
        required_owner_actions=("x",),
        safety_boundary=SAFETY_BOUNDARY,
    )
    report = build_report(state=state, decision=decision, available=state.available_evidence)
    assert "Safety boundary" in report
    assert "Available evidence" in report
