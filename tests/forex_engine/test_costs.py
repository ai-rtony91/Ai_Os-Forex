import pytest

from automation.forex_engine.costs import (
    CostApplicationModel,
    TradeCostAssumptions,
    apply_cost_to_pnl,
    conservative_entry_price,
    conservative_exit_price,
    trade_cost_usd,
)
from automation.forex_engine.models import Direction


ASSUMPTIONS = TradeCostAssumptions(spread=0.0001, slippage=0.00005, commission_per_trade_usd=0.5)


def test_cost_1_long_raw_reference_exact_single_charge():
    assert apply_cost_to_pnl(10.0, 10_000, ASSUMPTIONS) == 7.5


def test_cost_2_short_raw_reference_is_symmetric():
    assert apply_cost_to_pnl(10.0, -10_000, ASSUMPTIONS) == 7.5


def test_cost_3_long_actual_bid_ask_does_not_charge_spread_again():
    assert apply_cost_to_pnl(10.0, 10_000, ASSUMPTIONS, CostApplicationModel.EXECUTABLE_BID_ASK) == 8.5


def test_cost_4_short_actual_bid_ask_is_symmetric():
    assert apply_cost_to_pnl(10.0, -10_000, ASSUMPTIONS, CostApplicationModel.EXECUTABLE_BID_ASK) == 8.5


def test_cost_5_commission_only_actual_bid_ask():
    assumptions = TradeCostAssumptions(spread=0.0001, slippage=0.0, commission_per_trade_usd=0.5)
    assert trade_cost_usd(10_000, assumptions, CostApplicationModel.EXECUTABLE_BID_ASK) == 0.5


def test_cost_6_zero_cost_preserves_raw_pnl():
    assert apply_cost_to_pnl(12.34, 10_000, TradeCostAssumptions(0, 0, 0)) == 12.34


def test_cost_7_mixed_double_charge_path_fails_closed():
    with pytest.raises(ValueError, match="cannot be combined"):
        apply_cost_to_pnl(10.0, 10_000, ASSUMPTIONS, prices_already_synthetically_adjusted=True)
    with pytest.raises(ValueError, match="Unknown or mixed"):
        apply_cost_to_pnl(10.0, 10_000, ASSUMPTIONS, "MIXED")


def test_cost_8_controlled_ten_thousand_unit_hand_calculation():
    assert trade_cost_usd(10_000, ASSUMPTIONS) == 2.5


def test_cost_9_known_two_r_gross_result_has_one_net_charge():
    assert apply_cost_to_pnl(200.0, 10_000, ASSUMPTIONS) == 197.5


def test_cost_10_known_minus_one_r_result_has_one_net_charge():
    assert apply_cost_to_pnl(-100.0, 10_000, ASSUMPTIONS) == -102.5


def test_cost_11_adjusted_fills_cannot_be_costed_again():
    long_entry = conservative_entry_price(Direction.BUY, 1.08, ASSUMPTIONS)
    long_exit = conservative_exit_price(Direction.BUY, 1.081, ASSUMPTIONS)
    assert long_entry == 1.0801
    assert long_exit == 1.0809
    with pytest.raises(ValueError, match="cannot be combined"):
        apply_cost_to_pnl(
            (long_exit - long_entry) * 10_000,
            10_000,
            ASSUMPTIONS,
            prices_already_synthetically_adjusted=True,
        )


def test_cost_12_source_prices_remain_unmutated():
    entry = 1.08
    exit_price = 1.081
    conservative_entry_price(Direction.BUY, entry, ASSUMPTIONS)
    conservative_exit_price(Direction.BUY, exit_price, ASSUMPTIONS)
    assert entry == 1.08
    assert exit_price == 1.081
