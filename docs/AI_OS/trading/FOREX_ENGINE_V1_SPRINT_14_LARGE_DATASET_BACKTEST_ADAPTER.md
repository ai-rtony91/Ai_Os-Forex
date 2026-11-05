# AI_OS Forex Engine v1 — Sprint 14 Large-Dataset Backtest Adapter

## Objective

Sprint 14 creates local PAPER_ONLY large-dataset backtest adapter scaffolding.

## Why This Sprint Matters

Sprint 13 validated historical-data readiness.
Sprint 14 connects locally validated datasets to the backtest engine.

## Scope

Included:

- LargeDatasetBacktestAdapter
- LargeDatasetBacktestReport
- CandleGroupSummary
- LargeDatasetBacktestGroupResult
- Local dataset loading
- Symbol/timeframe grouping
- Group backtest execution
- Synthetic demo
- Tests
- Documentation

Excluded:

- Live trading
- Broker APIs
- External data download
- Credentials
- Telegram sending
- Email sending
- Push notifications
- Scheduler
- Hardware
- run_live_trading_demo

## Current Defaults

- Starting account: 500 USD
- Paper risk: 0.5 percent
- Symbols: EURUSD, GBPUSD, USDJPY, XAUUSD
- Mode: PAPER_ONLY
- Adapter mode: LARGE_DATASET_BACKTEST_ADAPTER_ONLY

## Files Added

- `automation/forex_engine/large_dataset_backtest_adapter.py`
- `automation/forex_engine/run_large_dataset_backtest_demo.py`
- `tests/forex_engine/test_large_dataset_backtest_adapter.py`
- `docs/AI_OS/trading/FOREX_ENGINE_V1_SPRINT_14_LARGE_DATASET_BACKTEST_ADAPTER.md`

## Large-Dataset Adapter Flow

1. Receive a local CSV path.
2. Reject URL-style paths.
3. Run Sprint 13 historical-data readiness checks.
4. Convert valid local rows into existing `Candle` objects.
5. Group candles by symbol and timeframe.
6. Summarize each group.
7. Run existing PAPER_ONLY backtests for eligible groups.
8. Return an operator-readable adapter report.

## Dataset Readiness Integration

Sprint 14 uses `HistoricalDataReadinessEngine` before loading candles into the adapter. Invalid datasets do not backtest. Datasets that need cleaning or lack enough rows are reported with skipped group results.

## Candle Grouping

Candles are grouped by symbol and timeframe. Each group is sorted by timestamp and then validated with the existing Sprint 2 candle sequence validation.

## Backtest Group Rules

- Minimum backtest candles per group: 20.
- Groups below the minimum are marked INSUFFICIENT_DATA and skipped.
- Eligible groups run through the existing PAPER_ONLY backtest runner.
- Results remain local research output only.

## Recommendations

- Fix dataset schema or invalid rows before backtesting.
- Use larger local historical dataset before trusting results.
- Clean dataset warnings before broader PAPER_ONLY backtesting.
- Review results as PAPER_ONLY research; do not treat as live readiness.
- Review XAUUSD tick-value and volatility modeling before promotion.

## Demo Command

```powershell
python -m automation.forex_engine.run_large_dataset_backtest_demo
```

## Validation

```powershell
python -m pytest tests/forex_engine
python -m automation.forex_engine.run_large_dataset_backtest_demo
python -m automation.forex_engine.run_historical_data_readiness_demo
python -m automation.forex_engine.run_portfolio_optimization_demo
python -m automation.forex_engine.run_parameter_optimization_demo
python -m automation.forex_engine.run_risk_management_demo
python -m automation.forex_engine.run_broker_sandbox_demo
python -m automation.forex_engine.run_paper_operator_demo
python -m automation.forex_engine.run_walk_forward_demo
python -m automation.forex_engine.run_strategy_comparison_demo
python -m automation.forex_engine.run_confidence_demo
python -m automation.forex_engine.run_signal_rules_demo
python -m automation.forex_engine.run_backtest_demo
python -m automation.forex_engine.run_market_data_demo
python -m automation.forex_engine.run_paper_demo
```

## Safety Boundary

Sprint 14 is local LARGE_DATASET_BACKTEST_ADAPTER_ONLY.
No broker execution.
No API calls.
No network calls.
No data downloads.
No credentials.
No live order path.
No alert sending.
No scheduling.
No profitability claim.
No live readiness claim.

## Known Limitations

- Model only.
- Synthetic demo data only.
- No external historical provider integration.
- No real broker.
- No broker API.
- No credentials.
- No network.
- No real market-data quality certification.
- No live readiness.
- Backtest assumptions remain simplified.
- No spread/slippage/commission realism yet.
- No pip-value or XAUUSD tick-value correctness yet.

## Success Criteria

- LargeDatasetBacktestAdapter exists.
- LargeDatasetBacktestReport exists.
- CandleGroupSummary exists.
- LargeDatasetBacktestGroupResult exists.
- Local synthetic dataset can be loaded.
- Candles can be grouped by symbol/timeframe.
- Small groups are marked insufficient.
- Ready groups can run PAPER_ONLY backtests.
- Invalid dataset does not backtest.
- Report contains recommendations.
- Demo runs.
- Historical readiness demo still runs.
- Portfolio optimization demo still runs.
- Parameter optimization demo still runs.
- Risk management demo still runs.
- Broker sandbox demo still runs.
- Paper operator demo still runs.
- Walk-forward demo still runs.
- Strategy comparison demo still runs.
- Confidence demo still runs.
- Signal rules demo still runs.
- Backtest demo still runs.
- Market data demo still runs.
- Paper demo still runs.
- All forex_engine tests pass.
- No live execution path exists.
- No network ingestion exists.
- No run_live_trading_demo.py exists.

## Next Sprint

Sprint 15 should add spread, slippage, commission, and execution-cost modeling for PAPER_ONLY backtests, still without broker/API/live execution.
