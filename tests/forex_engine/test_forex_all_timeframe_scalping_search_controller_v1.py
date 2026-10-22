from __future__ import annotations

from automation.forex_engine.forex_all_timeframe_scalping_search_controller_v1 import PACKET_ID, attack_state


def test_controller_packet_identity():
    assert PACKET_ID == "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033"


def test_human_data_gate_is_terminal_for_current_authorized_work():
    state = {"status": "HUMAN_SCALPING_TIMEFRAME_DATA_ACQUISITION_REQUIRED", "missing_timeframes_requiring_human_data": ["S5"]}
    attack = attack_state(state)
    assert attack["pre_terminal_audit_status"] == "PASS"
    assert attack["highest_priority_blocker"]["human_action_required"] is True
