from automation.forex_engine import forex_exit_capture_frontier_v1 as wrapper


def test_exit_wrapper_exposes_execute():
    assert callable(wrapper.execute)
