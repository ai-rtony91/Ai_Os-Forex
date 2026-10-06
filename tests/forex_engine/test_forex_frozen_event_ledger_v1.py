from automation.forex_engine import forex_frozen_event_ledger_v1 as wrapper


def test_ledger_wrapper_exposes_execute():
    assert callable(wrapper.execute)
