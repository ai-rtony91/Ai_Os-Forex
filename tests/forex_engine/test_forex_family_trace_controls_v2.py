from automation.forex_engine import forex_family_trace_controls_v2 as controls


def test_family_trace_controls_are_validator_derived():
    state = controls.execute_controls()
    assert state["family_count"] == 8
    assert state["producer_no_verdict_fields"] is True
    assert state["status"] == "TRACE_BACKED_FAMILY_CONTROLS_CERTIFIED"
    for row in state["rows"]:
        assert row["trace_backed_control_valid"] is True
        assert row["positive_control"]["validator_result"]["overall_valid"] is True
        assert all(item["validator_result"]["overall_valid"] for item in row["negative_controls"])
