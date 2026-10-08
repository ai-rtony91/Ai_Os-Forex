from __future__ import annotations

from automation.forex_engine.forex_scalping_timeframe_corpus_v1 import run


def test_corpus_state_does_not_mutate_frozen_corpora():
    state = run()
    assert state["corpus_mutation_performed"] is False
    assert state["broker_or_live_api_work"] == "NO"
