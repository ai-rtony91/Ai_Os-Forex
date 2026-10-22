from datetime import datetime, timezone

from automation.forex_engine import forex_mechanism_information_corpus_v1 as module


def test_recovery_plan_is_frozen_and_bounded():
    plan = module.routes()
    assert len(plan["sources"]) == 11
    assert all(1 <= len(source["routes"]) <= 3 for source in plan["sources"])
    assert all(route.startswith("https://fred.stlouisfed.org/") for source in plan["sources"] for route in source["routes"])


def test_normalization_applies_conservative_availability():
    raw = b"DATE,DFF\n2024-01-02,5.33\n"
    row = module.normalize("DFF", raw, "USD", 1)[0]
    assert datetime.fromisoformat(row["strategy_available_time"]) > datetime.fromisoformat(row["observation_time"])
    assert row["retrieval_hash"] == module.sha(raw)


def test_get_only_source_boundary():
    assert "GET" in module.fetch.__code__.co_consts


def test_stable_hash_is_deterministic():
    assert module.sha(module.stable({"b": 2, "a": 1}).encode()) == module.sha(module.stable({"a": 1, "b": 2}).encode())
