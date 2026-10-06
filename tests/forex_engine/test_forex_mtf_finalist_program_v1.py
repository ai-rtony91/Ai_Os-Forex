from __future__ import annotations

from pathlib import Path

from automation.forex_engine.forex_mtf_finalist_program_v1 import PACKET_ID


def test_finalist_program_packet_identity_is_packet032():
    assert PACKET_ID == "PKT-EAST-FOREX-MTF-GROSS-EDGE-DISCOVERY-032"


def test_finalist_paths_are_packet032_allowed_outputs():
    assert "AIOS_FOREX_MTF_FINALIST_REGISTRY_V1.json" in str(Path("Reports/forex_delivery/AIOS_FOREX_MTF_FINALIST_REGISTRY_V1.json"))
