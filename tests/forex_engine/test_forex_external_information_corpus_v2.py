from automation.forex_engine import forex_external_information_corpus_v2 as module


def test_no_duplicate_corpus_when_no_new_data():
    state = module.build({"successes": [], "results": [{"source_id": "x"}]})
    assert state["status"] == "NOT_CREATED_NO_NEW_USABLE_INFORMATION"
    assert state["frozen"] is False


def test_new_data_creates_hashed_freeze_contract():
    state = module.build({"successes": [{"source_id": "x", "records": 2, "normalized_hash": "a"}], "results": [{"source_id": "x"}]})
    assert state["status"] == "FROZEN_VALID"
    assert state["aggregate_hash"]
