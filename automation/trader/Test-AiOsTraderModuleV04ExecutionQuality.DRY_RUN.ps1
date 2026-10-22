$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$RequiredFiles = @(
    "aios/modules/trader/execution_quality.py",
    "aios/modules/trader/events.py",
    "aios/modules/trader/brokers/paper_broker.py",
    "aios/modules/trader/trader.py",
    "aios/modules/trader/backtest.py",
    "aios/modules/trader/scorecard.py",
    "automation/trader/Test-AiOsTraderModuleV04ExecutionQuality.DRY_RUN.ps1"
)

foreach ($File in $RequiredFiles) {
    if (-not (Test-Path $File)) {
        throw "Missing required v0.4 file: $File"
    }
}

$PriorValidators = @(
    "automation/trader/Test-AiOsTraderModuleSafety.DRY_RUN.ps1",
    "automation/trader/Test-AiOsTraderModuleV02OutcomesScorecard.DRY_RUN.ps1",
    "automation/trader/Test-AiOsTraderModuleV03RiskHardening.DRY_RUN.ps1"
)

foreach ($Validator in $PriorValidators) {
    $Output = powershell -NoProfile -File $Validator
    if ($LASTEXITCODE -ne 0) {
        throw "Prior validator failed: $Validator"
    }
    if (-not (($Output -join "`n") -match "^PASS:")) {
        throw "Prior validator did not report PASS: $Validator"
    }
}

$PythonScript = @'
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))

from aios.modules.trader.backtest import BacktestEngine
from aios.modules.trader.config import TraderConfig
from aios.modules.trader.events import MarketBar
from aios.modules.trader.execution_quality import build_execution_quality_metrics
from aios.modules.trader.trader import TraderEngine

config = TraderConfig()
config.validate_safety()
assert config.live_broker_enabled is False
assert config.external_routing_enabled is False
engine = TraderEngine(config=config)
bars = [
    MarketBar("EQ", "1m", "2026-05-12T00:00:00Z", 100.0, 102.0, 99.0, 101.0, 10.0),
    MarketBar("EQ", "1m", "2026-05-12T00:01:00Z", 101.0, 102.0, 97.0, 98.0, 11.0),
    MarketBar("EQ", "1m", "2026-05-12T00:02:00Z", 98.0, 101.0, 97.0, 100.0, 12.0),
    MarketBar("EQ", "1m", "2026-05-12T00:03:00Z", 100.0, 101.0, 94.0, 96.0, 13.0),
    MarketBar("EQ", "1m", "2026-05-12T00:04:00Z", 96.0, 99.0, 95.0, 98.0, 14.0),
]
summary = BacktestEngine(engine).run(bars)
scorecard = summary["scorecard"]
execution_records = summary["execution_records"]
standalone_metrics = build_execution_quality_metrics(execution_records)

assert execution_records, "Expected paper execution records"
required_metrics = {
    "paper_slippage",
    "expected_fill_price",
    "actual_paper_fill_price",
    "spread_estimate",
    "fill_latency_ms",
    "rejected_order_count",
    "risk_block_count",
    "average_paper_slippage",
    "execution_quality_score",
}
missing = required_metrics.difference(scorecard)
assert not missing, f"Missing v0.4 execution quality metrics: {sorted(missing)}"

for record in execution_records:
    assert record["paper_only"] is True
    assert "expected_fill_price" in record
    assert "actual_paper_fill_price" in record
    assert "paper_slippage" in record
    assert "spread_estimate" in record
    assert "fill_latency_ms" in record

assert isinstance(scorecard["paper_slippage"], list)
assert scorecard["rejected_order_count"] == 0
assert scorecard["risk_block_count"] >= 0
assert scorecard["average_paper_slippage"] == 0.0
assert 0.0 <= scorecard["execution_quality_score"] <= 100.0
assert standalone_metrics["execution_quality_score"] == 100.0
assert scorecard["paper_only"] is True
assert scorecard["live_execution_status"] == "BLOCKED"
assert scorecard["execution_allowed"] is False
assert config.live_execution_status == "BLOCKED"
assert config.execution_allowed is False
assert config.live_broker_enabled is False
assert config.external_routing_enabled is False

forbidden = {
    "api_key",
    "webhook_url",
    "account_id",
    "real_order_id",
    "live_order",
    "broker_api",
    "oanda",
}
observed = str(summary).lower()
for term in forbidden:
    assert term not in observed, f"Forbidden live/API/webhook field found: {term}"

print("PASS: AIOS Trader Module v0.4 execution quality DRY_RUN validation passed.")
'@

# Run from stdin; -B prevents Python from creating __pycache__ files.
$PythonScript | python -B -
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
