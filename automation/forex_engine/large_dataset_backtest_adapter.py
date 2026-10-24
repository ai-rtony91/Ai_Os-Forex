"""Local PAPER_ONLY large-dataset backtest adapter scaffold for Sprint 14."""

import csv
from pathlib import Path

from automation.forex_engine.backtest import run_backtest
from automation.forex_engine.config import ForexEngineConfig
from automation.forex_engine.historical_data_readiness import HistoricalDataReadinessEngine
from automation.forex_engine.market_data import REQUIRED_COLUMNS, validate_candle, validate_candle_sequence
from automation.forex_engine.models import (
    BacktestConfig,
    Candle,
    CandleGroupKey,
    CandleGroupSummary,
    EngineMode,
    HistoricalDataReadinessStatus,
    LargeDatasetBacktestGroupResult,
    LargeDatasetBacktestReport,
    LargeDatasetBacktestStatus,
)


ADAPTER_MODE = "LARGE_DATASET_BACKTEST_ADAPTER_ONLY"
MINIMUM_BACKTEST_CANDLES_PER_GROUP = 20


class LargeDatasetBacktestAdapter:
    def __init__(self, config: ForexEngineConfig):
        self.config = config
        self.readiness_engine = HistoricalDataReadinessEngine(config)

    def load_validated_dataset(self, path) -> list[Candle]:
        local_path = self._local_path(path)
        readiness = self.readiness_engine.inspect_dataset(local_path)
        if readiness.readiness_status == HistoricalDataReadinessStatus.INVALID_DATASET:
            raise ValueError("Invalid local dataset cannot be adapted for backtest.")
        if readiness.readiness_status == HistoricalDataReadinessStatus.NEEDS_CLEANING:
            raise ValueError("Dataset needs cleaning before local backtest adaptation.")
        return self._load_candles(local_path)

    def group_candles(self, candles) -> dict[CandleGroupKey, list[Candle]]:
        grouped: dict[CandleGroupKey, list[Candle]] = {}
        for candle in candles:
            key = CandleGroupKey(candle.symbol, candle.timeframe)
            grouped.setdefault(key, []).append(candle)
        for key, group in grouped.items():
            group.sort(key=lambda item: item.timestamp)
            validate_candle_sequence(group)
        return dict(sorted(grouped.items(), key=lambda item: (item[0].symbol, item[0].timeframe)))

    def summarize_groups(self, grouped_candles) -> list[CandleGroupSummary]:
        summaries = []
        for key, candles in grouped_candles.items():
            warnings = []
            status = LargeDatasetBacktestStatus.READY_FOR_LOCAL_BACKTEST
            if len(candles) < MINIMUM_BACKTEST_CANDLES_PER_GROUP:
                status = LargeDatasetBacktestStatus.INSUFFICIENT_DATA
                warnings.append("Group has fewer than the minimum backtest candles.")
            summaries.append(
                CandleGroupSummary(
                    mode=EngineMode.PAPER_ONLY,
                    symbol=key.symbol,
                    timeframe=key.timeframe,
                    candle_count=len(candles),
                    first_timestamp=candles[0].timestamp if candles else "",
                    last_timestamp=candles[-1].timestamp if candles else "",
                    status=status,
                    warnings=warnings,
                    metadata={
                        "adapter_mode": ADAPTER_MODE,
                        "minimum_backtest_candles_per_group": MINIMUM_BACKTEST_CANDLES_PER_GROUP,
                    },
                )
            )
        return summaries

    def run_group_backtests(self, grouped_candles) -> list[LargeDatasetBacktestGroupResult]:
        results = []
        for key, candles in grouped_candles.items():
            warnings = []
            if len(candles) < MINIMUM_BACKTEST_CANDLES_PER_GROUP:
                results.append(
                    LargeDatasetBacktestGroupResult(
                        mode=EngineMode.PAPER_ONLY,
                        symbol=key.symbol,
                        timeframe=key.timeframe,
                        candle_count=len(candles),
                        backtest_status=LargeDatasetBacktestStatus.BACKTEST_SKIPPED,
                        trades_opened=0,
                        trades_closed=0,
                        net_pnl_usd=0.0,
                        win_rate_pct=0.0,
                        profit_factor=None,
                        warnings=["Group skipped because it has insufficient local candles."],
                        metadata={"adapter_mode": ADAPTER_MODE},
                    )
                )
                continue

            backtest_result = run_backtest(
                candles,
                BacktestConfig(
                    symbol=key.symbol,
                    timeframe=key.timeframe,
                    starting_balance_usd=self.config.starting_balance_usd,
                    strategy_name="sprint_3_demo_strategy",
                    mode=EngineMode.PAPER_ONLY,
                    metadata={"adapter_mode": ADAPTER_MODE},
                ),
            )
            results.append(
                LargeDatasetBacktestGroupResult(
                    mode=EngineMode.PAPER_ONLY,
                    symbol=key.symbol,
                    timeframe=key.timeframe,
                    candle_count=len(candles),
                    backtest_status=LargeDatasetBacktestStatus.BACKTEST_COMPLETED,
                    trades_opened=backtest_result.trades_opened,
                    trades_closed=backtest_result.trades_closed,
                    net_pnl_usd=backtest_result.net_pnl_usd,
                    win_rate_pct=backtest_result.win_rate_pct,
                    profit_factor=backtest_result.profit_factor,
                    warnings=warnings,
                    metadata={"adapter_mode": ADAPTER_MODE, "backtest_result": backtest_result},
                )
            )
        return results

    def build_backtest_report(self, path) -> LargeDatasetBacktestReport:
        local_path = self._local_path(path)
        readiness = self.readiness_engine.inspect_dataset(local_path)
        warnings = list(readiness.quality_score.warnings)
        grouped = {}
        group_summaries = []
        group_results = []

        if readiness.readiness_status == HistoricalDataReadinessStatus.INVALID_DATASET:
            adapter_status = LargeDatasetBacktestStatus.INVALID_DATASET
            recommendations = self._recommendations(adapter_status, group_summaries)
            return self._report(local_path, readiness, adapter_status, group_summaries, group_results, warnings, recommendations)

        candles = self._load_candles(local_path)
        grouped = self.group_candles(candles)
        group_summaries = self.summarize_groups(grouped)

        if readiness.readiness_status == HistoricalDataReadinessStatus.NEEDS_CLEANING:
            adapter_status = LargeDatasetBacktestStatus.NEEDS_CLEANING
            group_results = self._skipped_results(grouped, "Dataset needs cleaning before local backtest adaptation.")
        elif readiness.readiness_status == HistoricalDataReadinessStatus.INSUFFICIENT_DATA:
            adapter_status = LargeDatasetBacktestStatus.INSUFFICIENT_DATA
            group_results = self._skipped_results(grouped, "Dataset has insufficient rows for trusted local backtesting.")
        else:
            group_results = self.run_group_backtests(grouped)
            if any(result.backtest_status == LargeDatasetBacktestStatus.BACKTEST_COMPLETED for result in group_results):
                adapter_status = LargeDatasetBacktestStatus.BACKTEST_COMPLETED
            else:
                adapter_status = LargeDatasetBacktestStatus.INSUFFICIENT_DATA

        recommendations = self._recommendations(adapter_status, group_summaries)
        return self._report(local_path, readiness, adapter_status, group_summaries, group_results, warnings, recommendations)

    def format_backtest_report(self, report: LargeDatasetBacktestReport) -> str:
        lines = [
            "AI_OS Forex Engine v1 Sprint 14 Large Dataset Backtest Adapter Report",
            f"Mode: {report.mode}",
            f"Adapter mode: {report.metadata.get('adapter_mode', ADAPTER_MODE)}",
            f"Dataset: {report.dataset_name}",
            f"Readiness status: {report.readiness_status}",
            f"Adapter status: {report.adapter_status}",
            f"Groups detected: {report.group_count}",
            f"Total candles: {report.total_candles}",
        ]
        for result in report.group_results:
            lines.append(
                f"{result.symbol} {result.timeframe}: candles={result.candle_count}, "
                f"status={result.backtest_status}, trades_closed={result.trades_closed}, "
                f"net_pnl={result.net_pnl_usd:.2f}"
            )
        lines.append(f"Recommendations: {'; '.join(report.recommendations)}")
        lines.append("Safety note: Local large-dataset backtest adapter only; no broker/API/network/download/live execution path used.")
        return "\n".join(lines)

    def _load_candles(self, path) -> list[Candle]:
        candles = []
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(REQUIRED_COLUMNS):
                raise ValueError(f"CSV header must be: {','.join(REQUIRED_COLUMNS)}")
            for row in reader:
                candle = Candle(
                    symbol=row["symbol"],
                    timeframe=row["timeframe"],
                    timestamp=row["timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    source=str(path),
                )
                validate_candle(candle, self.config)
                candles.append(candle)
        if not candles:
            raise ValueError("Local dataset must contain at least one candle.")
        return candles

    def _skipped_results(self, grouped_candles, reason) -> list[LargeDatasetBacktestGroupResult]:
        return [
            LargeDatasetBacktestGroupResult(
                mode=EngineMode.PAPER_ONLY,
                symbol=key.symbol,
                timeframe=key.timeframe,
                candle_count=len(candles),
                backtest_status=LargeDatasetBacktestStatus.BACKTEST_SKIPPED,
                trades_opened=0,
                trades_closed=0,
                net_pnl_usd=0.0,
                win_rate_pct=0.0,
                profit_factor=None,
                warnings=[reason],
                metadata={"adapter_mode": ADAPTER_MODE},
            )
            for key, candles in grouped_candles.items()
        ]

    def _report(self, path, readiness, adapter_status, group_summaries, group_results, warnings, recommendations):
        total_candles = sum(group.candle_count for group in group_summaries)
        return LargeDatasetBacktestReport(
            mode=EngineMode.PAPER_ONLY,
            dataset_name=Path(path).name,
            readiness_status=readiness.readiness_status,
            adapter_status=adapter_status,
            group_count=len(group_summaries),
            total_candles=total_candles,
            groups=group_summaries,
            group_results=group_results,
            warnings=list(dict.fromkeys(warnings)),
            recommendations=list(dict.fromkeys(recommendations)),
            summary_note="Local LARGE_DATASET_BACKTEST_ADAPTER_ONLY scaffold. Results are PAPER_ONLY research, not live readiness.",
            metadata={
                "adapter_mode": ADAPTER_MODE,
                "readiness_manifest": readiness.manifest,
                "minimum_backtest_candles_per_group": MINIMUM_BACKTEST_CANDLES_PER_GROUP,
            },
        )

    def _recommendations(self, adapter_status, group_summaries):
        recommendations = []
        if adapter_status == LargeDatasetBacktestStatus.INVALID_DATASET:
            recommendations.append("Fix dataset schema or invalid rows before backtesting.")
        if adapter_status == LargeDatasetBacktestStatus.INSUFFICIENT_DATA:
            recommendations.append("Use larger local historical dataset before trusting results.")
        if adapter_status == LargeDatasetBacktestStatus.NEEDS_CLEANING:
            recommendations.append("Clean dataset warnings before broader PAPER_ONLY backtesting.")
        if adapter_status == LargeDatasetBacktestStatus.BACKTEST_COMPLETED:
            recommendations.append("Review results as PAPER_ONLY research; do not treat as live readiness.")
        if any(group.symbol == "XAUUSD" for group in group_summaries):
            recommendations.append("Review XAUUSD tick-value and volatility modeling before promotion.")
        recommendations.append("Keep adapter runs local; do not download market data in Sprint 14.")
        return recommendations

    def _local_path(self, path) -> Path:
        text = str(path).lower()
        if text.startswith("http://") or text.startswith("https://"):
            raise ValueError("Large dataset backtest adapter only accepts local file paths; URL paths are blocked.")
        local_path = Path(path)
        if not local_path.exists():
            raise ValueError(f"Local dataset not found: {local_path}")
        if not local_path.is_file():
            raise ValueError(f"Local dataset path must be a file: {local_path}")
        return local_path
