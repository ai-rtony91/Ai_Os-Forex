from automation.forex_engine import forex_family_adapter_repair_v3 as adapters


def test_all_families_use_same_public_entrypoint_for_positive_trace():
    for family_id in adapters.FAMILIES:
        spec = adapters.positive_spec(family_id)
        trace = adapters.run_family_adapter(spec)
        assert trace["adapter_id"] == spec.adapter_id
        assert trace["family_id"] == family_id
        assert trace["execution_core_id"]
        assert trace["cost_core_id"]
        assert trace["metric_core_id"]


def test_invalid_shortcuts_emit_family_specific_rejections():
    for family_id in adapters.FAMILIES:
        trace = adapters.run_family_adapter(adapters.negative_spec(family_id))
        rejected = [event for event in trace["events"] if event["event_type"] == "EVENT_REJECTED"]
        assert rejected
        assert rejected[0]["rejection_reason"] == adapters.INVALID_REASON_BY_FAMILY[family_id]
