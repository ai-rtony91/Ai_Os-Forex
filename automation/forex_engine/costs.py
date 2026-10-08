"""Single-charge PAPER_ONLY transaction-cost contract."""

from dataclasses import dataclass
from enum import Enum

from automation.forex_engine.models import Direction


@dataclass(frozen=True)
class TradeCostAssumptions:
    spread: float = 0.00010
    slippage: float = 0.00005
    commission_per_trade_usd: float = 0.0


class CostApplicationModel(str, Enum):
    RAW_REFERENCE_EXPLICIT_COST = "RAW_REFERENCE_EXPLICIT_COST"
    EXECUTABLE_BID_ASK = "EXECUTABLE_BID_ASK"


def _validated_model(model):
    try:
        return CostApplicationModel(model)
    except ValueError as exc:
        raise ValueError("Unknown or mixed transaction-cost model.") from exc


def conservative_entry_price(direction, raw_price, assumptions=TradeCostAssumptions()):
    adjustment = assumptions.spread / 2 + assumptions.slippage
    if direction == Direction.BUY:
        return round(raw_price + adjustment, 10)
    if direction == Direction.SELL:
        return round(raw_price - adjustment, 10)
    raise ValueError("Direction must be BUY or SELL.")


def conservative_exit_price(direction, raw_price, assumptions=TradeCostAssumptions()):
    adjustment = assumptions.spread / 2 + assumptions.slippage
    if direction == Direction.BUY:
        return round(raw_price - adjustment, 10)
    if direction == Direction.SELL:
        return round(raw_price + adjustment, 10)
    raise ValueError("Direction must be BUY or SELL.")


def trade_cost_usd(
    position_size_units,
    assumptions=TradeCostAssumptions(),
    model=CostApplicationModel.RAW_REFERENCE_EXPLICIT_COST,
):
    selected = _validated_model(model)
    spread_cost = assumptions.spread if selected == CostApplicationModel.RAW_REFERENCE_EXPLICIT_COST else 0.0
    per_unit_cost = spread_cost + (2 * assumptions.slippage)
    return round(abs(position_size_units) * per_unit_cost + assumptions.commission_per_trade_usd, 2)


def apply_cost_to_pnl(
    raw_pnl_usd,
    position_size_units,
    assumptions=TradeCostAssumptions(),
    model=CostApplicationModel.RAW_REFERENCE_EXPLICIT_COST,
    *,
    prices_already_synthetically_adjusted=False,
):
    if prices_already_synthetically_adjusted:
        raise ValueError("Synthetic fill adjustments cannot be combined with explicit P&L cost deduction.")
    return round(raw_pnl_usd - trade_cost_usd(position_size_units, assumptions, model), 2)


def cost_assumption_summary(
    assumptions=TradeCostAssumptions(),
    model=CostApplicationModel.RAW_REFERENCE_EXPLICIT_COST,
):
    selected = _validated_model(model)
    return {
        "spread": assumptions.spread,
        "slippage": assumptions.slippage,
        "commission_per_trade_usd": assumptions.commission_per_trade_usd,
        "fill_policy": selected.value,
        "spread_deducted_by_cost_helper": selected == CostApplicationModel.RAW_REFERENCE_EXPLICIT_COST,
        "mode": "PAPER_ONLY",
    }
