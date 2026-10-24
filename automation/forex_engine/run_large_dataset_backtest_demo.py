"""Run the AI_OS Forex Engine v1 Sprint 14 large-dataset backtest adapter demo."""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from automation.forex_engine.config import ForexEngineConfig, validate_config
from automation.forex_engine.historical_data_readiness import HistoricalDataReadinessEngine
from automation.forex_engine.large_dataset_backtest_adapter import ADAPTER_MODE, LargeDatasetBacktestAdapter


def build_demo_report(config=None):
    config = config or ForexEngineConfig()
    validate_config(config)
    output_dir = Path("automation/forex_engine/runtime/large_dataset_backtest_demo")
    dataset_path = HistoricalDataReadinessEngine(config).generate_synthetic_dataset(output_dir, row_count=1000)
    return LargeDatasetBacktestAdapter(config).build_backtest_report(dataset_path)


def main() -> int:
    config = ForexEngineConfig()
    report = build_demo_report(config)
    groups = ", ".join(f"{group.symbol} {group.timeframe}" for group in report.groups)

    print("AI_OS Forex Engine v1 Sprint 14 Large Dataset Backtest Adapter Demo")
    print(f"Mode: {config.mode}")
    print(f"Adapter mode: {ADAPTER_MODE}")
    print("Data source: generated local synthetic historical dataset only")
    print(f"Dataset rows: {report.metadata['readiness_manifest'].row_count}")
    print(f"Rows loaded: {report.total_candles}")
    print(f"Groups detected: {groups}")
    print(f"Readiness status: {report.readiness_status}")
    print(f"Backtest adapter status: {report.adapter_status}")
    for result in report.group_results:
        print(
            f"{result.symbol} {result.timeframe}: candles={result.candle_count}, "
            f"backtest_status={result.backtest_status}, trades_closed={result.trades_closed}, "
            f"net_pnl={result.net_pnl_usd:.2f}"
        )
    print(f"Recommendations: {'; '.join(report.recommendations)}")
    print("Safety note: Local large-dataset backtest adapter only; no broker/API/network/download/live execution path used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
