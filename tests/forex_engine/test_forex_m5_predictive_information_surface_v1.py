from automation.forex_engine import forex_m5_predictive_information_surface_v1 as wrapper


def test_information_wrapper_exposes_execute():
    assert callable(wrapper.execute)
