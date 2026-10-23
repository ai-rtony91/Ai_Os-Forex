from __future__ import annotations

from automation.forex_engine.forex_all_timeframe_scalping_gross_edge_v1 import run


def test_gross_edge_checkpoint_does_not_claim_search_exhaustion():
    state = run()
    assert state["search_family_exhausted"] is False
    assert state["replication_completed"] == 0
    assert state["paper_opened"] is False
