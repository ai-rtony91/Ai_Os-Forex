from automation.forex_engine import forex_packet030_receipt_audit_v1 as wrapper


def test_receipt_wrapper_exposes_execute():
    assert callable(wrapper.execute)
