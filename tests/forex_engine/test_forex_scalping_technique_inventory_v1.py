from __future__ import annotations

from automation.forex_engine.forex_scalping_technique_inventory_v1 import FAMILIES, build_inventory


def test_inventory_contains_twelve_major_families():
    assert set(FAMILIES) == set("ABCDEFGHIJKL")
    assert sum(len(v["techniques"]) for v in FAMILIES.values()) >= 70


def test_order_flow_family_requires_unavailable_special_data():
    state = build_inventory()
    family_l = [f for f in state["families"] if f["family_id"] == "L"][0]
    assert family_l["status"] == "INELIGIBLE_ORDER_FLOW_OR_SUBMINUTE_DATA_NOT_AVAILABLE"
