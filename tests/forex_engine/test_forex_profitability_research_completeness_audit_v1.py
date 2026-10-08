import importlib.util
from pathlib import Path


MODULE_PATH = Path("automation/forex_engine/forex_profitability_research_completeness_audit_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("audit_v1", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_packet026_completeness_audit_identifies_ten_candidate_underproduction():
    module = load_module()
    state = module.audit_completeness()

    assert state["status"] == "COMPLETE"
    assert state["planned_family_count"] > state["implemented_family_count"]
    assert state["candidates_scored"] == 10
    assert state["long_candidates"] == 5
    assert state["short_candidates"] == 5
    assert state["families_skipped"]


def test_terminal_state_valid_for_packet026_registry_only():
    module = load_module()
    completeness = module.audit_completeness()
    terminal = module.audit_terminal(completeness)

    assert terminal["status"] == "COMPLETE"
    assert terminal["verdict"] == "TERMINAL_STATE_VALID_FOR_PACKET026_REGISTRY_ONLY"
    assert terminal["architecture_expansion_required"] is True
    assert terminal["scorer_audit"]["common_defect_found"] is False


def test_rr_atlas_audit_keeps_breakeven_interpretation_separate():
    module = load_module()
    atlas = module.audit_atlas()

    assert atlas["status"] == "COMPLETE"
    assert atlas["idealized_zero_cost_breakeven"]["2R"] == 0.333333
    assert atlas["equivalent_to_fixed_full_win_loss_contract"] is False
    assert "diagnostic opportunity map" in atlas["interpretation"]
