$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$RequiredFiles = @(
    "aios/modules/trader/__init__.py",
    "aios/modules/trader/config.py",
    "aios/modules/trader/events.py",
    "aios/modules/trader/market_data.py",
    "aios/modules/trader/risk.py",
    "aios/modules/trader/trader.py",
    "aios/modules/trader/backtest.py",
    "aios/modules/trader/strategies/__init__.py",
    "aios/modules/trader/strategies/base.py",
    "aios/modules/trader/strategies/supertrend_permission.py",
    "aios/modules/trader/brokers/__init__.py",
    "aios/modules/trader/brokers/paper_broker.py"
)

foreach ($File in $RequiredFiles) {
    if (-not (Test-Path $File)) {
        throw "Missing required trader module file: $File"
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
from aios.modules.trader.trader import TraderEngine

config = TraderConfig()
assert config.mode == "paper_only"
assert config.live_execution_status == "BLOCKED"
assert config.execution_allowed is False
assert config.broker_status == "PAPER_ONLY"
assert config.external_routing_enabled is False
assert config.api_keys_required is False
assert config.leverage_enabled is False
assert config.margin_enabled is False
assert config.options_enabled is False
assert config.live_broker_enabled is False
config.validate_safety()

engine = TraderEngine(config=config)
bar = MarketBar(
    symbol="TEST",
    timeframe="1m",
    timestamp="2026-05-12T00:00:00Z",
    open=100.0,
    high=102.0,
    low=99.0,
    close=101.0,
    volume=10.0,
)
decision = engine.on_bar(bar)
decision_dict = decision.to_dict()

if decision_dict.get("paper_order") is not None:
    assert decision_dict["paper_order"]["paper_only"] is True
if decision_dict.get("paper_fill") is not None:
    assert decision_dict["paper_fill"]["paper_only"] is True

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
    "broker_api",
    "external_routing",
}

objects_to_check = [
    config,
    decision_dict,
    engine.paper_broker.positions,
    [fill.to_dict() for fill in engine.paper_broker.fills],
]
observed = {item.lower() for obj in objects_to_check for item in flatten(obj)}
for term in forbidden:
    assert term not in observed, f"Forbidden live/broker field found: {term}"

bars = [
    MarketBar("TEST", "1m", "2026-05-12T00:01:00Z", 101.0, 103.0, 100.0, 102.0, 11.0),
    MarketBar("TEST", "1m", "2026-05-12T00:02:00Z", 102.0, 104.0, 101.0, 103.0, 12.0),
    MarketBar("TEST", "1m", "2026-05-12T00:03:00Z", 103.0, 105.0, 102.0, 104.0, 13.0),
]
backtest = BacktestEngine(TraderEngine(config=TraderConfig()))
summary = backtest.run(bars)
assert summary["total_bars"] == 3
assert summary["total_paper_orders"] >= 1
assert summary["total_paper_fills"] >= 1
assert summary["live_execution_status"] == "BLOCKED"

print("PASS: AIOS Trader Module v0.1 safety DRY_RUN validation passed.")
'@

# Run from stdin; -B prevents Python from creating __pycache__ files.
$PythonScript | python -B -
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
