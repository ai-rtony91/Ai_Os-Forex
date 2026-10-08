$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$RequiredFiles = @(
    "aios/modules/trader/risk.py",
    "aios/modules/trader/trader.py",
    "aios/modules/trader/brokers/paper_broker.py",
    "aios/modules/trader/outcomes.py",
    "automation/trader/Test-AiOsTraderModuleV03RiskHardening.DRY_RUN.ps1"
)

foreach ($File in $RequiredFiles) {
    if (-not (Test-Path $File)) {
        throw "Missing required v0.3 file: $File"
    }
}

$PythonScript = @'
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))

from aios.modules.trader.config import TraderConfig
from aios.modules.trader.events import MarketBar, SignalEvent
from aios.modules.trader.trader import TraderEngine


class FixedSignalStrategy:
    def __init__(self, direction, quantity=1):
        self.direction = direction
        self.quantity = quantity

    def generate_signal(self, bar):
        return SignalEvent(
            symbol=bar.symbol,
            timeframe=bar.timeframe,
            timestamp=bar.timestamp,
            direction=self.direction,
            quantity=self.quantity,
            reason="v03_fixed_test_signal",
        )


def assert_blocked(decision, expected_reason):
    data = decision.to_dict()
    assert data["decision"] == "BLOCKED", data
    assert expected_reason in data["reason"], data["reason"]


def run_bar(engine, bar):
    return engine.on_bar(bar)


config = TraderConfig()
config.validate_safety()
assert config.live_execution_status == "BLOCKED"
assert config.execution_allowed is False

bad_bar_engine = TraderEngine(config=TraderConfig())
bad_bar = MarketBar("BAD", "1m", "2026-05-12T00:00:00Z", 100.0, 99.0, 98.0, 101.0, 1.0)
assert_blocked(run_bar(bad_bar_engine, bad_bar), "Bad MarketBar data")

cash_engine = TraderEngine(
    config=TraderConfig(starting_cash=50.0),
    strategy=FixedSignalStrategy("BUY_REVIEW", 1),
)
cash_bar = MarketBar("CASH", "1m", "2026-05-12T00:01:00Z", 100.0, 102.0, 99.0, 101.0, 1.0)
assert_blocked(run_bar(cash_engine, cash_bar), "Insufficient paper cash")

sell_missing_engine = TraderEngine(
    config=TraderConfig(),
    strategy=FixedSignalStrategy("SELL_REVIEW", 1),
)
sell_missing_bar = MarketBar("MISS", "1m", "2026-05-12T00:02:00Z", 100.0, 101.0, 89.0, 90.0, 1.0)
assert_blocked(run_bar(sell_missing_engine, sell_missing_bar), "Missing paper position")

sell_small_engine = TraderEngine(
    config=TraderConfig(max_position_size=5),
    strategy=FixedSignalStrategy("SELL_REVIEW", 2),
)
sell_small_engine.paper_broker.positions["SMALL"] = 1
sell_small_bar = MarketBar("SMALL", "1m", "2026-05-12T00:03:00Z", 100.0, 101.0, 89.0, 90.0, 1.0)
assert_blocked(run_bar(sell_small_engine, sell_small_bar), "Paper position is too small")

quantity_engine = TraderEngine(
    config=TraderConfig(max_position_size=1),
    strategy=FixedSignalStrategy("BUY_REVIEW", 2),
)
quantity_bar = MarketBar("QTY", "1m", "2026-05-12T00:04:00Z", 100.0, 102.0, 99.0, 101.0, 1.0)
assert_blocked(run_bar(quantity_engine, quantity_bar), "maximum position size")

open_position_engine = TraderEngine(
    config=TraderConfig(max_open_positions=1),
    strategy=FixedSignalStrategy("BUY_REVIEW", 1),
)
open_position_engine.paper_broker.positions["OPEN1"] = 1
open_position_bar = MarketBar("OPEN2", "1m", "2026-05-12T00:05:00Z", 100.0, 102.0, 99.0, 101.0, 1.0)
assert_blocked(run_bar(open_position_engine, open_position_bar), "Maximum open paper positions")

loss_engine = TraderEngine(
    config=TraderConfig(max_daily_loss=1.0),
    strategy=FixedSignalStrategy("BUY_REVIEW", 1),
)
loss_engine.paper_outcomes.outcomes.append(
    type(
        "Outcome",
        (),
        {"pnl": -1.0},
    )()
)
loss_bar = MarketBar("LOSS", "1m", "2026-05-12T00:06:00Z", 100.0, 102.0, 99.0, 101.0, 1.0)
assert_blocked(run_bar(loss_engine, loss_bar), "Daily paper loss")

ok_engine = TraderEngine(
    config=TraderConfig(starting_cash=1000.0),
    strategy=FixedSignalStrategy("BUY_REVIEW", 1),
)
ok_bar = MarketBar("OK", "1m", "2026-05-12T00:07:00Z", 100.0, 102.0, 99.0, 101.0, 1.0)
ok_decision = run_bar(ok_engine, ok_bar).to_dict()
assert ok_decision["decision"] == "BUY_REVIEW", ok_decision
assert ok_decision["paper_order"]["paper_only"] is True
assert ok_decision["paper_fill"]["paper_only"] is True
assert ok_decision["live_execution_status"] == "BLOCKED"

print("PASS: AIOS Trader Module v0.3 risk hardening DRY_RUN validation passed.")
'@

# Run from stdin; -B prevents Python from creating __pycache__ files.
$PythonScript | python -B -
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
