from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_PATH = (
    REPO_ROOT
    / "docs"
    / "trading_lab"
    / "AIOS_FOREX_BUILDER_BROKER_PAPER_ADAPTER_IMPLEMENTATION_PACKET_V1.md"
)


def test_packet_document_exists() -> None:
    assert PACKET_PATH.exists()


def test_packet_has_required_identity_and_governance_sections() -> None:
    text = PACKET_PATH.read_text(encoding="utf-8")

    required_phrases = (
        "Packet ID: PKT-AIOS-BROKER-PAPER-ADAPTER-IMPLEMENTATION-V1",
        "Mission ID: MISSION-AIOS-001",
        "Program ID: PRG-FOREX-001",
        "Epic ID: EPC-FOREX-004",
        "Bucket ID: BKT-FOREX-008",
        "Objective",
        "Scope",
        "Non-scope",
        "Existing Interfaces",
        "Proposed Adapter Contract",
        "Safety Controls",
        "Paper-Only Boundary",
        "Evidence / Receipt Contract",
        "Failure / Rollback Behavior",
        "Required Tests",
        "Acceptance Criteria",
        "Human Owner Approval Checkpoint",
        "Implementation Sequence",
        "Post-Implementation Validation Gate",
        "Explicit Live-Execution Statement",
    )

    for phrase in required_phrases:
        assert phrase in text


def test_packet_reuses_existing_broker_paper_interfaces() -> None:
    text = PACKET_PATH.read_text(encoding="utf-8")

    required_interfaces = (
        "broker_paper_adapter_stub_contract",
        "broker_paper_dryrun_intent_ledger",
        "broker_paper_dryrun_risk_governor",
        "broker_paper_dryrun_replay_harness",
        "broker_paper_dryrun_replay_evidence_gate",
        "broker_paper_adapter_plan_approval_gate",
        "broker_paper_sandbox_readiness",
        "schema_contracts",
        "next_action_engine",
        "long_only_supervisor_broker_proof_adapter_v1",
        "oanda_long_only_broker_proof_intake_v1",
    )

    for interface_name in required_interfaces:
        assert interface_name in text


def test_packet_keeps_live_execution_blocked_and_paper_only() -> None:
    text = PACKET_PATH.read_text(encoding="utf-8").lower()

    required_boundaries = (
        "paper/demo-only broker interaction",
        "paper_only: true",
        "live_execution_allowed: false",
        "live_broker_writes_allowed: false",
        "live_orders_allowed: false",
        "approval of this packet does not authorize live execution",
        "approval of this packet does not authorize live broker writes",
        "approval of this packet does not authorize the 30-trade campaign",
    )

    for boundary in required_boundaries:
        assert boundary in text


def test_packet_names_receipt_chain_and_fail_closed_behavior() -> None:
    text = PACKET_PATH.read_text(encoding="utf-8")

    required_receipt_terms = (
        "Intent receipt",
        "Submission receipt",
        "Acknowledgement receipt",
        "Rejection receipt",
        "Error receipt",
        "Final state receipt",
        "intent -> submission -> acknowledgement/rejection/error -> final state",
        "fail closed",
        "paper/demo verification",
        "BUY",
        "SHORT",
        "LONG",
    )

    for term in required_receipt_terms:
        assert term in text


def test_packet_routes_to_long_form_validation_after_implementation() -> None:
    text = PACKET_PATH.read_text(encoding="utf-8")

    assert "FOREX-LONG-RUN-PAPER-SUPERVISOR" in text
    assert "RUN_PAPER_LONG_FORM_VALIDATION_CYCLE" in text
    assert "This validation comes after the adapter implementation is complete and verified." in text
