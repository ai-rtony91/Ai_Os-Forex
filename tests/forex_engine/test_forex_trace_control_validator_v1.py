from automation.forex_engine import forex_family_adapter_repair_v3 as adapters
from automation.forex_engine import forex_trace_control_validator_v1 as validator


MUTATIONS = [
    "future_feature_timestamp",
    "source_available_after_decision",
    "invalid_entry_boundary",
    "long_entry_bid",
    "short_entry_ask",
    "omitted_cost",
    "double_cost",
    "altered_realized_r",
    "altered_metric_summary",
    "duplicated_event_id",
    "duplicated_trade_id",
    "changed_adapter_code_hash",
    "changed_execution_core_identity",
    "changed_cost_core_identity",
    "changed_metric_core_identity",
    "changed_direction_after_base_event",
    "nondeterministic_rerun_trace",
    "future_official_release",
    "pre_release_event_entry",
    "incomplete_multileg_fill",
]


def test_validator_accepts_valid_trace_from_adapter():
    spec = adapters.positive_spec("B_CROSS_SECTIONAL_FACTOR")
    trace = adapters.run_family_adapter(spec)
    result = validator.validate_trace(trace, spec.__dict__ | {"adapter_code_hash": adapters.adapter_code_hash()}, adapters.run_family_adapter(spec))
    assert result["overall_valid"] is True
    assert result["recomputed_metrics"]["trade_count"] == 1


def test_validator_rejects_required_mutations():
    spec = adapters.positive_spec("D_RELATIVE_VALUE")
    trace = adapters.run_family_adapter(spec)
    for mutation in MUTATIONS:
        mutated = validator.mutate_trace(trace, mutation)
        result = validator.validate_trace(mutated, spec.__dict__ | {"adapter_code_hash": adapters.adapter_code_hash()}, trace)
        assert result["overall_valid"] is False, mutation
