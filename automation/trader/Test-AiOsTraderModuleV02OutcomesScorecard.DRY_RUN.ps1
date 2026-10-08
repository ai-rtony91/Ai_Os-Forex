$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$RequiredFiles = @(
    "aios/modules/trader/outcomes.py",
    "aios/modules/trader/scorecard.py",
    "automation/trader/Test-AiOsTraderModuleV02OutcomesScorecard.DRY_RUN.ps1"
)

foreach ($File in $RequiredFiles) {
    if (-not (Test-Path $File)) {
        throw "Missing required v0.2 file: $File"
    }
}

$PythonScript = @'
from dataclasses import asdict, is_dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))

from aios.modules.trader.backtest import BacktestEngine
from aios.modules.trader.config import TraderConfig
from aios.modules.trader.events import MarketBar
from aios.modules.trader.scorecard import build_paper_scorecard
from aios.modules.trader.trader import TraderEngine

config = TraderConfig()
config.validate_safety()
engine = TraderEngine(config=config)
bars = [
    MarketBar("TEST", "1m", "2026-05-12T00:00:00Z", 100.0, 102.0, 99.0, 101.0, 10.0),
    MarketBar("TEST", "1m", "2026-05-12T00:01:00Z", 101.0, 102.0, 97.0, 98.0, 11.0),
    MarketBar("TEST", "1m", "2026-05-12T00:02:00Z", 98.0, 101.0, 97.0, 100.0, 12.0),
    MarketBar("TEST", "1m", "2026-05-12T00:03:00Z", 100.0, 101.0, 94.0, 96.0, 13.0),
    MarketBar("TEST", "1m", "2026-05-12T00:04:00Z", 96.0, 99.0, 95.0, 98.0, 14.0),
]
summary = BacktestEngine(engine).run(bars)
outcomes = summary["paper_outcomes"]
scorecard = summary["scorecard"]

assert len(bars) >= 5
assert len(outcomes) >= 2
assert all(outcome["status"] == "CLOSED_PAPER" for outcome in outcomes)
assert all(outcome["paper_only"] is True for outcome in outcomes)
assert all(outcome["live_execution_status"] == "BLOCKED" for outcome in outcomes)
assert all(outcome["execution_allowed"] is False for outcome in outcomes)

required_metrics = {
    "total_trades",
    "paper_wins",
    "paper_losses",
    "win_rate",
    "average_win",
    "average_loss",
    "expectancy",
    "profit_factor",
    "max_drawdown",
    "starting_cash",
    "ending_cash",
    "blocked_decisions",
    "live_execution_status",
}
missing = required_metrics.difference(scorecard)
assert not missing, f"Missing scorecard metrics: {sorted(missing)}"
assert scorecard["paper_only"] is True
assert scorecard["live_execution_status"] == "BLOCKED"
assert scorecard["execution_allowed"] is False

manual_scorecard = build_paper_scorecard(outcomes, starting_cash=config.starting_cash)
assert manual_scorecard["total_trades"] == scorecard["total_trades"]

def flatten(value):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from flatten(item)
    elif isinstance(value, list):
        for item in value:
            yield from flatten(item)
    else:
        yield str(value)

forbidden = {
    "api_key",
    "webhook_url",
    "account_id",
    "real_order_id",
    "live_order",
    "oanda",
}
observed = {item.lower() for item in flatten({"summary": summary, "scorecard": scorecard})}
for term in forbidden:
    assert term not in observed, f"Forbidden live/API/webhook field found: {term}"

print("PASS: AIOS Trader Module v0.2 outcomes scorecard DRY_RUN validation passed.")
'@

# Run from stdin; -B prevents Python from creating __pycache__ files.
$PythonScript | python -B -
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
