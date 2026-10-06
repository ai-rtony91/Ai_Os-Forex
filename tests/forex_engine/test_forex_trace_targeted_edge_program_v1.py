from automation.forex_engine import forex_trace_targeted_edge_program_v1 as targeted


def test_targeted_registry_caps_and_freezes_m5_candidates():
    candidates = targeted.build_targeted_registry(["M5_DAY_TRADING_MTF", "EXIT_CAPTURE"])

    assert len(candidates) <= 32
    assert sum(1 for row in candidates if row["branch"] == "M5_DAY_TRADING_MTF") == 20
    assert all(row["behavior_fingerprint"] for row in candidates)
    assert {row["direction"] for row in candidates} == {"LONG", "SHORT"}


def test_optional_branch_requires_diagnostic_support():
    assert targeted.choose_optional_branch({"family_results": {}}, {"class_counts": {}}) is None
    assert targeted.choose_optional_branch(
        {"family_results": {"A_TIME_SERIES_MOMENTUM": "FAMILY_REGIME_OR_GATE_CONDITIONAL"}},
        {"class_counts": {}},
    ) == "REGIME_ROUTER"
    assert targeted.choose_optional_branch(
        {"family_results": {}},
        {"class_counts": {"TARGET_UNREACHABLE_OR_EXIT_CAPTURE_FAILURE": 8}},
    ) == "EXIT_CAPTURE"
