"""Local PAPER_ONLY backtest runner for AI_OS Forex Engine v1 Sprint 3."""

from automation.forex_engine.analytics import ForexAnalytics
from automation.forex_engine.confidence import ConfidenceEngine
from automation.forex_engine.config import ForexEngineConfig
from automation.forex_engine.costs import CostApplicationModel, TradeCostAssumptions, apply_cost_to_pnl
from automation.forex_engine.market_data import load_fixture_candles, validate_candle_sequence
from automation.forex_engine.metrics import calculate_edge_metrics
from automation.forex_engine.models import (
    BacktestConfig,
    BacktestResult,
    BacktestTradeResult,
    Direction,
    EngineMode,
    ForexSignal,
)
from automation.forex_engine.paper_execution import PaperExecutionEngine
from automation.forex_engine.risk import RiskEngine
from automation.forex_engine.signal_rules import SPRINT_4_STRATEGY_NAME, generate_signals_from_candles
from automation.forex_engine.strategies import SUPERTREND_PULLBACK_V1, evaluate_supertrend_pullback


STOP_LOSS = "STOP_LOSS"
TAKE_PROFIT = "TAKE_PROFIT"
END_OF_BACKTEST = "END_OF_BACKTEST"


class BacktestEngine:
    def __init__(self, config, risk_engine, confidence_engine, journal_writer=None):
        self.config = config
        self.risk_engine = risk_engine
        self.confidence_engine = confidence_engine
        self.journal_writer = journal_writer
        self.paper_execution_engine = PaperExecutionEngine(config, risk_engine, journal_writer)

    def run_backtest(self, candles, backtest_config=None, signal_provider=None):
        if not candles:
            raise ValueError("Backtest candles must not be empty.")
        validate_candle_sequence(candles)

        limited_candles = list(candles)
        base_config = backtest_config or BacktestConfig(
            symbol=limited_candles[0].symbol,
            timeframe=limited_candles[0].timeframe,
            starting_balance_usd=self.config.starting_balance_usd,
        )
        if base_config.mode != EngineMode.PAPER_ONLY:
            raise ValueError("BacktestConfig mode must be PAPER_ONLY.")
        if base_config.max_candles is not None:
            limited_candles = limited_candles[: base_config.max_candles]
            validate_candle_sequence(limited_candles)

        paper_engine = PaperExecutionEngine(self.config, self.risk_engine, self.journal_writer)
        paper_engine.current_balance_usd = base_config.starting_balance_usd

        signals_generated = 0
        signals_accepted = 0
        signals_blocked = 0
        previous_candle = None

        for index, candle in enumerate(limited_candles):
            evaluate_open_trades_against_candle(paper_engine, candle)
            signals = self._signals_for_candle(
                limited_candles[: index + 1],
                candle,
                previous_candle,
                base_config,
                signal_provider,
            )
            previous_candle = candle
            for signal in signals:
                signals_generated += 1
                assessment = self.confidence_engine.score_signal(signal)
                if not assessment.allowed:
                    signals_blocked += 1
                    continue
                try:
                    paper_engine.submit_signal(signal, assessment)
                    signals_accepted += 1
                except ValueError:
                    signals_blocked += 1

        close_remaining_trades_at_end(paper_engine, limited_candles[-1])
        return build_backtest_result(
            backtest_config=base_config,
            candles_processed=len(limited_candles),
            signals_generated=signals_generated,
            signals_accepted=signals_accepted,
            signals_blocked=signals_blocked,
            paper_execution_engine=paper_engine,
        )

    def _signals_for_candle(self, candles_so_far, candle, previous_candle, backtest_config, signal_provider):
        if signal_provider:
            return signal_provider(candles_so_far, self.config)
        if backtest_config.strategy_name == "sprint_4_intraday_rules_v1":
            signals, _result = generate_signals_from_candles(candles_so_far, self.config)
            return signals
        signal = generate_demo_signal_from_candle(candle, previous_candle, self.config)
        return [signal] if signal is not None else []


def run_backtest(candles, backtest_config=None):
    config = ForexEngineConfig()
    engine = BacktestEngine(config, RiskEngine(config), ConfidenceEngine(config))
    return engine.run_backtest(candles, backtest_config)


def generate_demo_signal_from_candle(candle, previous_candle, config):
    if previous_candle is None:
        return None
    if candle.close == previous_candle.close:
        return None

    candle_range = max(candle.high - candle.low, candle.close * 0.001)
    stop_distance = candle_range * 0.5
    target_distance = candle_range
    direction = Direction.BUY if candle.close > previous_candle.close else Direction.SELL
    if direction == Direction.BUY:
        stop_loss = candle.close - stop_distance
        take_profit = candle.close + target_distance
    else:
        stop_loss = candle.close + stop_distance
        take_profit = candle.close - target_distance

    return ForexSignal(
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        direction=direction,
        entry_price=candle.close,
        stop_loss=round(stop_loss, 5),
        take_profit=round(take_profit, 5),
        timestamp=candle.timestamp,
        strategy_name="sprint_3_demo_strategy",
        metadata={
            "source": "local_backtest_demo",
            "setup_quality": "demo",
            "session": "fixture",
            "warning": "demo strategy only",
        },
    )


def evaluate_open_trades_against_candle(paper_execution_engine, candle):
    closed = []
    for trade in list(paper_execution_engine.open_trades):
        close_price = None
        close_reason = None
        if trade.direction == Direction.BUY:
            if candle.low <= trade.stop_loss:
                close_price = trade.stop_loss
                close_reason = STOP_LOSS
            elif candle.high >= trade.take_profit:
                close_price = trade.take_profit
                close_reason = TAKE_PROFIT
        elif trade.direction == Direction.SELL:
            if candle.high >= trade.stop_loss:
                close_price = trade.stop_loss
                close_reason = STOP_LOSS
            elif candle.low <= trade.take_profit:
                close_price = trade.take_profit
                close_reason = TAKE_PROFIT

        if close_reason:
            trade.metadata["close_reason"] = close_reason
            closed.append(paper_execution_engine.close_trade(trade.trade_id, close_price, candle.timestamp))
    return closed


def close_remaining_trades_at_end(paper_execution_engine, last_candle):
    closed = []
    for trade in list(paper_execution_engine.open_trades):
        trade.metadata["close_reason"] = END_OF_BACKTEST
        closed.append(paper_execution_engine.close_trade(trade.trade_id, last_candle.close, last_candle.timestamp))
    return closed


def build_backtest_result(
    backtest_config,
    candles_processed,
    signals_generated,
    signals_accepted,
    signals_blocked,
    paper_execution_engine,
):
    summary = ForexAnalytics().summarize(
        backtest_config.starting_balance_usd,
        paper_execution_engine.current_balance_usd,
        paper_execution_engine.open_trades,
        paper_execution_engine.closed_trades,
    )
    trade_results = [
        BacktestTradeResult(
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            timeframe=trade.timeframe,
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_loss=trade.stop_loss,
            take_profit=trade.take_profit,
            exit_price=trade.exit_price,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            outcome=trade.outcome,
            pnl_usd=trade.pnl_usd,
            confidence_score=trade.confidence_score,
            close_reason=trade.metadata.get("close_reason", END_OF_BACKTEST),
            metadata=dict(trade.metadata),
        )
        for trade in paper_execution_engine.closed_trades
    ]
    return BacktestResult(
        mode=EngineMode.PAPER_ONLY,
        symbol=backtest_config.symbol,
        timeframe=backtest_config.timeframe,
        strategy_name=backtest_config.strategy_name,
        candles_processed=candles_processed,
        signals_generated=signals_generated,
        signals_accepted=signals_accepted,
        signals_blocked=signals_blocked,
        trades_opened=len(trade_results),
        trades_closed=len(trade_results),
        starting_balance_usd=backtest_config.starting_balance_usd,
        ending_balance_usd=paper_execution_engine.current_balance_usd,
        net_pnl_usd=summary.net_pnl_usd,
        win_rate_pct=summary.win_rate_pct,
        profit_factor=summary.profit_factor,
        max_drawdown_usd=summary.max_drawdown_usd,
        max_drawdown_pct=summary.max_drawdown_pct,
        results=trade_results,
        summary_note=summary.consistency_note,
    )


def run_backtest_for_fixture(symbol, timeframe, config):
    candles = load_fixture_candles(symbol, timeframe, config)
    engine = BacktestEngine(config, RiskEngine(config), ConfidenceEngine(config))
    backtest_config = BacktestConfig(
        symbol=symbol,
        timeframe=timeframe,
        starting_balance_usd=config.starting_balance_usd,
        mode=EngineMode.PAPER_ONLY,
    )
    return engine.run_backtest(candles, backtest_config)


def run_supertrend_edge_backtest(
    candles,
    starting_balance_usd=500.0,
    risk_per_trade_usd=5.0,
    cost_assumptions=TradeCostAssumptions(),
):
    """Run local PAPER_ONLY Supertrend edge research with conservative costs."""
    if not candles:
        raise ValueError("Supertrend edge backtest candles must not be empty.")
    validate_candle_sequence(candles)
    source_candles = list(candles)
    trades = []
    no_trade_reasons = []
    index = 0
    while index < len(source_candles):
        window = source_candles[: index + 1]
        if len(window) < 5:
            index += 1
            continue
        result = evaluate_supertrend_pullback(window)
        if not result["accepted"]:
            no_trade_reasons.extend(result["no_trade_reasons"])
            index += 1
            continue
        signal = result["signal"]
        risk_distance = abs(signal.entry_price - signal.stop_loss)
        if risk_distance <= 0:
            no_trade_reasons.append("NO_TRADE: invalid_risk_distance")
            index += 1
            continue
        position_size_units = risk_per_trade_usd / risk_distance
        entry_price = signal.entry_price
        exit_index, exit_price, close_reason = _find_supertrend_exit(source_candles, index + 1, signal)
        if exit_index is None:
            exit_index = len(source_candles) - 1
            exit_price = source_candles[-1].close
            close_reason = END_OF_BACKTEST
        raw_pnl = _raw_pnl(signal.direction, entry_price, exit_price, position_size_units)
        pnl = apply_cost_to_pnl(
            raw_pnl,
            position_size_units,
            cost_assumptions,
            CostApplicationModel.RAW_REFERENCE_EXPLICIT_COST,
        )
        trades.append(
            {
                "strategy_name": SUPERTREND_PULLBACK_V1,
                "symbol": signal.symbol,
                "timeframe": signal.timeframe,
                "direction": signal.direction,
                "entry_price": round(entry_price, 5),
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit,
                "exit_price": round(exit_price, 5),
                "opened_at": signal.timestamp,
                "closed_at": source_candles[exit_index].timestamp,
                "close_reason": close_reason,
                "position_size_units": position_size_units,
                "pnl_usd": pnl,
                "r_multiple": round(pnl / risk_per_trade_usd, 4) if risk_per_trade_usd else 0.0,
            }
        )
        index = max(exit_index + 1, index + 1)
    metrics = calculate_edge_metrics(trades, starting_balance_usd, no_trade_reasons)
    return {
        "mode": EngineMode.PAPER_ONLY,
        "strategy_name": SUPERTREND_PULLBACK_V1,
        "symbol": source_candles[0].symbol,
        "timeframe": source_candles[0].timeframe,
        "candles_processed": len(source_candles),
        "trades": trades,
        "metrics": metrics,
        "no_trade_reasons": no_trade_reasons,
        "cost_assumptions": {
            "spread": cost_assumptions.spread,
            "slippage": cost_assumptions.slippage,
            "commission_per_trade_usd": cost_assumptions.commission_per_trade_usd,
        },
        "summary_note": "PAPER_ONLY Supertrend edge candidate research; no live readiness or earnings claim.",
    }


def _find_supertrend_exit(candles, start_index, signal):
    for index in range(start_index, len(candles)):
        candle = candles[index]
        if signal.direction == Direction.BUY:
            if candle.low <= signal.stop_loss:
                return index, signal.stop_loss, STOP_LOSS
            if candle.high >= signal.take_profit:
                return index, signal.take_profit, TAKE_PROFIT
        if signal.direction == Direction.SELL:
            if candle.high >= signal.stop_loss:
                return index, signal.stop_loss, STOP_LOSS
            if candle.low <= signal.take_profit:
                return index, signal.take_profit, TAKE_PROFIT
    return None, None, None


def _raw_pnl(direction, entry_price, exit_price, position_size_units):
    if direction == Direction.BUY:
        return (exit_price - entry_price) * position_size_units
    if direction == Direction.SELL:
        return (entry_price - exit_price) * position_size_units
    raise ValueError("Direction must be BUY or SELL.")
