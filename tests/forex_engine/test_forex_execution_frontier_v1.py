from automation.forex_engine import forex_execution_frontier_v1 as wrapper


def test_execution_wrapper_exposes_execute():
    assert callable(wrapper.execute)
