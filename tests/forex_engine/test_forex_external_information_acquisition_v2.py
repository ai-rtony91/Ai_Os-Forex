from automation.forex_engine import forex_external_information_acquisition_v2 as module


def test_inventory_has_distinct_bounded_routes():
    plan = module.inventory()
    routed = [source for source in plan["sources"] if source["routes"]]
    assert len(routed) == 11
    assert all(len(source["routes"]) == len(set(source["routes"])) == 3 for source in routed)


def test_unavailable_macro_families_are_not_called_negative_edge():
    unrouted = [source for source in module.inventory()["sources"] if not source["routes"]]
    assert len(unrouted) == 2
    assert all(source["classification"] == "UNTESTABLE_WITH_CURRENT_LAWFUL_PUBLIC_DATA" for source in unrouted)


def test_fetch_dependency_is_get_only():
    assert "GET" in module.prior.fetch.__code__.co_consts
