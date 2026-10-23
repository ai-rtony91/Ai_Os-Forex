from automation.forex_engine import forex_m5_data_sufficiency_audit_v1 as wrapper


def test_sufficiency_wrapper_exposes_execute():
    assert callable(wrapper.execute)
