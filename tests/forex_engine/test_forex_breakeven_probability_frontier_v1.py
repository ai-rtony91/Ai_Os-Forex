from automation.forex_engine import forex_breakeven_probability_frontier_v1 as wrapper


def test_breakeven_wrapper_exposes_execute():
    assert callable(wrapper.execute)
