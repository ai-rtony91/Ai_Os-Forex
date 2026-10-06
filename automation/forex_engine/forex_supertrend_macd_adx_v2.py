"""Packet 033 v2 wrapper for deterministic Supertrend/MACD/ADX."""
from __future__ import annotations

from automation.forex_engine.forex_supertrend_macd_adx_v1 import adx, atr, ema, fidelity_state, macd, module_hash, supertrend


PACKET_ID = "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033"


def fidelity_state_v2() -> dict:
    state = fidelity_state()
    state["packet_id"] = PACKET_ID
    state["schema"] = "AIOS_FOREX_SUPERTREND_MACD_ADX.v2"
    state["status"] = "SUPERTREND_MACD_ADX_V2_REUSED_VERIFIED_V1_CORE"
    state["v1_core_hash"] = module_hash()
    return state
