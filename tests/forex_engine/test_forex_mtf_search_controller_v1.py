from __future__ import annotations

from automation.forex_engine.forex_mtf_search_controller_v1 import PACKET_ID, attack_to_finish


def test_controller_packet_identity_is_packet032():
    assert PACKET_ID == "PKT-EAST-FOREX-MTF-GROSS-EDGE-DISCOVERY-032"


def test_attack_to_finish_terminal_no_edge_has_no_remaining_authorized_work():
    state = {"status": "NO_INDICATOR_GROSS_EDGE"}
    attack = attack_to_finish(state)
    assert attack["status"] == "NO_INDICATOR_GROSS_EDGE"
    assert attack["remaining_authorized_work_count"] == 0
    assert attack["pre_terminal_audit_status"] == "PASS"
