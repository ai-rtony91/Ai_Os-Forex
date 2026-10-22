import importlib.util
from pathlib import Path


MODULE_PATH = Path("automation/forex_engine/forex_next_generation_edge_program_v1.py")


def load_module():
    spec = importlib.util.spec_from_file_location("nextgen_v1", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_registry_covers_all_architecture_families_and_stays_under_cap():
    module = load_module()
    registry = module.build_registry()

    assert len(registry) <= 64
    assert len(registry) == 32
    assert {candidate["family"] for candidate in registry} == set(module.ARCHITECTURE_FAMILIES)
    assert len({candidate["behavior_fingerprint"] for candidate in registry}) == len(registry)
    assert {candidate["direction"] for candidate in registry} == {"LONG", "SHORT"}


def test_metric_profit_factor_and_drawdown_are_deterministic():
    module = load_module()
    result = module.metric([1.0, -0.5, 2.0, -1.0])

    assert result["trades"] == 4
    assert result["net_r"] == 1.5
    assert result["expectancy"] == 0.375
    assert result["profit_factor"] == 2.0
    assert result["max_drawdown_r"] == 1.0


def test_program_is_local_file_research_only():
    text = MODULE_PATH.read_text(encoding="utf-8")

    network_and_process_markers = ["requests.", "Invoke-WebRequest", "curl.exe", "subprocess", "Start-Process"]
    for marker in network_and_process_markers:
        assert marker not in text
    assert "PRACTICE_INBOX" in text
    assert "OFFICIAL_INBOX" in text
