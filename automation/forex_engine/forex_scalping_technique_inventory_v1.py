"""Packet 033 mechanical scalping technique inventory."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


PACKET_ID = "PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033"
STATE = Path("Reports/forex_delivery/AIOS_FOREX_SCALPING_TECHNIQUE_INVENTORY_V1_STATE.json")
REPORT = Path("Reports/forex_delivery/AIOS_FOREX_SCALPING_TECHNIQUE_INVENTORY_V1_REPORT.md")


FAMILIES: dict[str, dict[str, Any]] = {
    "A": {"name": "TREND_PULLBACK_CONTINUATION", "techniques": ["A1_EMA_PULLBACK", "A2_EMA_RIBBON_PULLBACK", "A3_SUPERTREND_PULLBACK", "A4_MACD_CONTINUATION", "A5_ADX_DMI_CONTINUATION", "A6_HTF_LTF_PULLBACK"], "data": "OHLC_BID_ASK"},
    "B": {"name": "MOMENTUM_BREAKOUT", "techniques": ["B1_OPENING_RANGE_BREAKOUT", "B2_SESSION_RANGE_BREAKOUT", "B3_DONCHIAN_BREAKOUT", "B4_INSIDE_BAR_BREAKOUT", "B5_SQUEEZE_EXPANSION", "B6_MACD_ACCELERATION", "B7_SUPERTREND_FLIP", "B8_ADX_EXPANSION"], "data": "OHLC_BID_ASK"},
    "C": {"name": "RANGE_MEAN_REVERSION", "techniques": ["C1_BOLLINGER_REVERSION", "C2_KELTNER_REVERSION", "C3_RSI_REVERSION", "C4_STOCHASTIC_REVERSION", "C5_RSI_STOCHASTIC_CONFIRMATION", "C6_SESSION_VWAP_REVERSION", "C7_CAUSAL_RANGE_BOUNDARY_REVERSION", "C8_SHORT_HORIZON_REVERSAL"], "data": "OHLC_BID_ASK_RANGE_GATE"},
    "D": {"name": "VWAP_AVERAGE_PRICE_SCALPING", "techniques": ["D1_SESSION_VWAP_PULLBACK_CONTINUATION", "D2_SESSION_VWAP_MEAN_REVERSION", "D3_ANCHORED_VWAP_CAUSAL", "D4_VWAP_MACD_ADX_CONFIRMATION"], "data": "OHLC_PRICE_COUNT_PROXY"},
    "E": {"name": "PRICE_ACTION_MARKET_STRUCTURE", "techniques": ["E1_SWING_BREAK_RETEST", "E2_PRIOR_LEVEL_BOUNCE", "E3_PIVOT_REACTION", "E4_FALSE_BREAKOUT_REVERSAL", "E5_LIQUIDITY_SWEEP_PROXY", "E6_INSIDE_BAR", "E7_ENGULFING_BAR", "E8_PIN_BAR_PROXY", "E9_IMBALANCE_FVG_PROXY"], "data": "OHLC_BID_ASK"},
    "F": {"name": "SESSION_TIME_OF_DAY", "techniques": ["F1_ASIA_RANGE", "F2_LONDON_OPEN", "F3_NEW_YORK_OPEN", "F4_LONDON_NY_OVERLAP", "F5_OPENING_RANGE_30_60_90", "F6_SESSION_TRANSITION", "F7_DAY_OF_WEEK", "F8_MONTH_QUARTER_END", "F9_ROLLOVER_AVOIDANCE"], "data": "OHLC_BID_ASK_UTC_CALENDAR"},
    "G": {"name": "VOLATILITY_LIQUIDITY", "techniques": ["G1_ATR_PERCENTILE", "G2_RV_COMPRESSION_EXPANSION", "G3_SPREAD_PERCENTILE", "G4_SPREAD_COMPRESSION_IMPULSE", "G5_PRICE_COUNT_ACCELERATION_PROXY", "G6_VOL_NORMALIZED_BREAKOUT", "G7_VOL_NORMALIZED_PULLBACK", "G8_ABNORMAL_SPREAD_GAP_NO_TRADE"], "data": "OHLC_BID_ASK_SPREAD"},
    "H": {"name": "EVENT_DRIVEN_SCALPING", "techniques": ["H1_CB_CONTINUATION", "H2_CB_REVERSAL", "H3_BLS_BREAKOUT", "H4_BLS_FAILED_BREAKOUT", "H5_POST_RELEASE_SPREAD_NORMALIZATION", "H6_EVENT_RISK_ABSTENTION"], "data": "OFFICIAL_EVENT_TIMESTAMPS"},
    "I": {"name": "RELATIVE_STRENGTH_CROSS_SECTIONAL", "techniques": ["I1_CURRENCY_STRENGTH_RANK", "I2_STRONGEST_WEAKEST_PAIR", "I3_MOMENTUM_RANK", "I4_CARRY_POLICY_RANK", "I5_SHORT_HORIZON_CROSS_SECTIONAL_REVERSAL"], "data": "MULTIPAIR_SYNCHRONIZED_OHLC"},
    "J": {"name": "RELATIVE_VALUE_PAIR_SPREAD", "techniques": ["J1_ROLLING_RESIDUAL_REVERSION", "J2_CROSS_RATE_RESIDUAL", "J3_CURRENCY_FACTOR_RESIDUAL", "J4_TRIANGULAR_CONSISTENCY_RESIDUAL", "J5_CORRELATED_PAIR_DIVERGENCE"], "data": "SYNCHRONIZED_MULTI_LEG_BID_ASK"},
    "K": {"name": "MICROSTRUCTURE_PROXIES", "techniques": ["K1_MICRO_MOMENTUM_BURST", "K2_MICRO_REVERSAL", "K3_SPREAD_EXPECTED_MOVE_RATIO", "K4_PRICE_COUNT_ACCELERATION", "K5_MICRO_RANGE_BREAKOUT", "K6_MICRO_FALSE_BREAKOUT", "K7_SIGNAL_HALF_LIFE", "K8_LATENCY_SENSITIVITY"], "data": "SECOND_OR_SUBMINUTE_HISTORY"},
    "L": {"name": "ORDER_FLOW_DOM_FOOTPRINT", "techniques": ["ORDER_BOOK_IMBALANCE", "DEPTH_OF_MARKET_SCALPING", "FOOTPRINT_IMBALANCE", "CVD", "TAPE_FLOW", "VOLUME_PROFILE"], "data": "ORDER_BOOK_OR_TRADE_TAPE"},
}


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def build_inventory() -> dict[str, Any]:
    families = []
    for key, family in FAMILIES.items():
        eligible = family["data"] != "ORDER_BOOK_OR_TRADE_TAPE"
        if key == "K":
            eligible = False
        families.append(
            {
                "family_id": key,
                "name": family["name"],
                "technique_count": len(family["techniques"]),
                "techniques": family["techniques"],
                "mechanical_definition_required": True,
                "long_short_separate": True,
                "data_requirement": family["data"],
                "status": "CLASSIFIED_OHLC_SUPPORTED" if eligible else "INELIGIBLE_ORDER_FLOW_OR_SUBMINUTE_DATA_NOT_AVAILABLE",
                "behavior_fingerprint": sha256_text(stable(family)),
            }
        )
    state = {
        "schema": "AIOS_FOREX_SCALPING_TECHNIQUE_INVENTORY.v1",
        "packet_id": PACKET_ID,
        "status": "SCALPING_TECHNIQUE_INVENTORY_COMPLETE",
        "family_count": len(families),
        "technique_count": sum(f["technique_count"] for f in families),
        "all_major_supported_scalping_families_classified": True,
        "families": families,
        "inventory_hash": sha256_text(stable(families)),
    }
    atomic_json(STATE, state)
    lines = ["# AIOS Forex Scalping Technique Inventory V1", "", f"- Status: {state['status']}", f"- Families: {state['family_count']}", f"- Techniques: {state['technique_count']}", f"- Hash: {state['inventory_hash']}", ""]
    for fam in families:
        lines.append(f"- Family {fam['family_id']} {fam['name']}: {fam['status']}")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return state


if __name__ == "__main__":
    print(json.dumps(build_inventory(), indent=2, sort_keys=True))
