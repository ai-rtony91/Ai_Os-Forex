from automation.forex_engine import forex_oracle_feasibility_bound_v1 as wrapper


def test_oracle_wrapper_exposes_execute():
    assert callable(wrapper.execute)
