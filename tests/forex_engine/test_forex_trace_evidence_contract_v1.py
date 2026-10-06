import pytest

from automation.forex_engine import forex_trace_evidence_contract_v1 as contract


def test_trace_producer_rejects_verdict_like_fields():
    with pytest.raises(ValueError):
        contract.make_event(1, "RUN_END", verdict="PASS")


def test_trace_contract_state_has_no_producer_verdict():
    state = contract.contract_state()
    assert state["producer_writes_verdict"] is False
    assert "verdict" in state["producer_forbidden_keys"]
