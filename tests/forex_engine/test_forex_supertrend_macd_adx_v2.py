from __future__ import annotations

from automation.forex_engine.forex_supertrend_macd_adx_v2 import PACKET_ID, fidelity_state_v2


def test_v2_wraps_packet033_identity():
    state = fidelity_state_v2()
    assert PACKET_ID.endswith("033")
    assert state["schema"].endswith(".v2")
    assert state["status"] == "SUPERTREND_MACD_ADX_V2_REUSED_VERIFIED_V1_CORE"
