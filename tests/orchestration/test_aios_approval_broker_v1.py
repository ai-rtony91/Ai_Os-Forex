import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from automation.orchestration.aios_approval_broker_v1 import (
    BUNDLE_ORDER,
    EXPECTED_BUNDLE_PHASES,
    ApprovalBroker,
    ApprovalBrokerError,
    load_manifest,
    validate_manifest,
)

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def decision(
    bundle_id="OWNER-BUNDLE-2-DEVICE-IDENTITY",
    *,
    receipt_id="receipt-001",
    phases=None,
    outcome="APPROVE",
    expires_at="2026-08-10T12:00:00Z",
):
    return {
        "receipt_id": receipt_id,
        "bundle_id": bundle_id,
        "phases": list(phases or EXPECTED_BUNDLE_PHASES[bundle_id]),
        "decision": outcome,
        "authority_source": "external-owner-authority-v1",
        "issued_at": "2026-08-09T11:00:00Z",
        "expires_at": expires_at,
    }


def test_manifest_resolves_exactly_17_phases():
    assert [p["phase_id"] for p in load_manifest()["phases"]] == list(range(1, 18))


def test_autonomous_phases_continue_without_queueing_owner_bundle():
    broker = ApprovalBroker()
    for phase_id in (1, 12, 13):
        result = broker.prepare_phase(phase_id)
        assert result == {
            "phase_id": phase_id,
            "status": "CONTINUE_AUTONOMOUSLY",
            "owner_bundle": None,
            "protected_action_blocked": False,
            "continue_unblocked_preparation": True,
            "blocked_scope": None,
        }


def test_protected_phase_prepares_behind_only_its_transition_gate():
    result = ApprovalBroker().prepare_phase(4)
    assert result["status"] == "PREPARE_BEHIND_GATE"
    assert result["protected_action_blocked"] is True
    assert result["continue_unblocked_preparation"] is True
    assert result["blocked_scope"] == "PROTECTED_TRANSITION_ONLY"


def test_device_phases_consolidate_to_one_item():
    queue = ApprovalBroker().build_queue([9, 4, 5])
    assert len(queue["pending_approvals"]) == 1
    assert queue["pending_approvals"][0]["bundle_id"] == BUNDLE_ORDER[1]
    assert queue["pending_approvals"][0]["phases"] == [4, 5, 9]


def test_all_protected_phases_make_exactly_four_deterministic_items():
    protected = [p for phases in EXPECTED_BUNDLE_PHASES.values() for p in phases]
    forward = ApprovalBroker().build_queue(protected)
    reverse = ApprovalBroker().build_queue(reversed(protected))
    assert [item["bundle_id"] for item in forward["pending_approvals"]] == list(BUNDLE_ORDER)
    assert forward == reverse
    assert len(forward["pending_approvals"]) == 4
    assert forward["continue_unblocked_preparation"] is True
    assert all(item["protected_action_blocked"] for item in forward["pending_approvals"])


@pytest.mark.parametrize(
    ("verifier", "problem"),
    [
        (None, "no trusted verifier"),
        (lambda record: False, "verifier rejected"),
    ],
)
def test_unverified_approval_is_blocked(verifier, problem):
    result = ApprovalBroker(verifier=verifier).prepare_phase(
        4, [decision()], now=NOW
    )
    assert result["status"] == "BLOCKED"
    assert any(problem in item for item in result["problems"])


def test_verifier_exception_is_blocked():
    def broken_verifier(record):
        raise RuntimeError("external verifier unavailable")

    result = ApprovalBroker(verifier=broken_verifier).prepare_phase(
        4, [decision()], now=NOW
    )
    assert result["status"] == "BLOCKED"
    assert "raised an exception" in result["problems"][0]


def test_trusted_approval_authorizes_exact_bundle_without_executing_it():
    result = ApprovalBroker(verifier=lambda record: True).prepare_phase(
        4, [decision()], now=NOW
    )
    assert result["status"] == "RESUME_AUTHORIZED"
    assert result["approved_phases"] == [4, 5, 9]
    assert result["downstream_execution"] == "REMAINS_GOVERNED_BY_RECEIVING_COMPONENT"


@pytest.mark.parametrize(
    "phases",
    ([4, 5], [4, 5, 9, 17]),
)
def test_partial_or_cross_bundle_phase_decision_is_blocked(phases):
    result = ApprovalBroker(verifier=lambda record: True).prepare_phase(
        4, [decision(phases=phases)], now=NOW
    )
    assert result["status"] == "BLOCKED"
    assert "exactly match bundle" in result["problems"][0]


def test_duplicate_receipt_id_fails_all_decisions_closed():
    decisions = [
        decision(receipt_id="same"),
        decision(
            "OWNER-BUNDLE-3-RUNTIME-SECRETS",
            receipt_id="same",
        ),
    ]
    queue = ApprovalBroker(verifier=lambda record: True).build_queue(
        [4, 14], decisions, now=NOW
    )
    assert queue["generated_status"] == "BLOCKED"
    assert queue["resumable_phases"] == []
    assert "duplicate receipt ID" in queue["problems"][0]


def test_expired_approval_returns_expired():
    result = ApprovalBroker(verifier=lambda record: True).prepare_phase(
        4, [decision(expires_at="2026-08-09T11:30:00Z")], now=NOW
    )
    assert result["status"] == "EXPIRED"


def test_trusted_rejection_returns_rejected():
    result = ApprovalBroker(verifier=lambda record: True).prepare_phase(
        4, [decision(outcome="REJECT")], now=NOW
    )
    assert result["status"] == "REJECTED"


def test_unknown_decision_is_blocked():
    result = ApprovalBroker(verifier=lambda record: True).prepare_phase(
        4, [decision(outcome="MAYBE")], now=NOW
    )
    assert result["status"] == "BLOCKED"
    assert "unknown decision" in result["problems"][0]


def test_queue_is_sanitized_and_validates_against_v1_schema():
    queue = ApprovalBroker().build_queue([4, 5, 9, 14, 15, 16])
    encoded = json.dumps(queue).lower()
    for forbidden in (
        '"token"',
        '"password"',
        '"private_key"',
        '"phone_number"',
        '"account_id"',
        '"raw_payload"',
    ):
        assert forbidden not in encoded
    schema_path = Path("schemas/orchestration/aios_approval_broker_queue_v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert set(queue) == set(schema["required"])
    assert queue["schema"] == schema["properties"]["schema"]["const"]
    assert queue["mode"] == schema["properties"]["mode"]["const"]
    assert queue["generated_status"] in schema["properties"]["generated_status"]["enum"]
    pending_schema = schema["$defs"]["pendingApproval"]
    bundle_ids = set(schema["$defs"]["bundleId"]["enum"])
    for item in queue["pending_approvals"]:
        assert set(item) == set(pending_schema["required"])
        assert item["bundle_id"] in bundle_ids
        assert all(1 <= phase <= 17 for phase in item["phases"])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda manifest: manifest.update(schema="wrong"),
        lambda manifest: manifest["phases"].pop(),
        lambda manifest: manifest["phases"].append(dict(manifest["phases"][0])),
        lambda manifest: manifest["phases"][0].update(phase_id=18),
        lambda manifest: manifest["phases"][1].update(owner_bundle="UNKNOWN"),
    ],
)
def test_invalid_manifest_structures_fail_closed(mutation):
    manifest = json.loads(json.dumps(load_manifest()))
    mutation(manifest)
    with pytest.raises(ApprovalBrokerError):
        validate_manifest(manifest)


def test_invalid_decision_shape_is_blocked():
    malformed = decision()
    del malformed["authority_source"]
    result = ApprovalBroker(verifier=lambda record: True).prepare_phase(
        4, [malformed], now=NOW
    )
    assert result["status"] == "BLOCKED"
