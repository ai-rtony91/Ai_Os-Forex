from __future__ import annotations

from automation.forex_engine.forex_all_timeframe_scalping_finalist_v1 import PACKET_ID


def test_finalist_packet_identity():
    assert PACKET_ID.endswith("033")
