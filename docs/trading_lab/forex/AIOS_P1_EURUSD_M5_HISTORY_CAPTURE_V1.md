# AIOS P1 EUR_USD M5 History Capture V1

## Purpose

This component reuses `OandaReadOnlyClient` for one explicit, owner-local, GET-only OANDA Practice candle request. It does not run by default and never uses the live endpoint.

## Canonical contract

- Endpoint: `/v3/instruments/EUR_USD/candles`
- Schema: `AIOS_P1_EURUSD_MARKET_HISTORY.v1`
- Evidence type: `SANITIZED_CANDLE_HISTORY`
- Runtime file: `.aios/runtime/forex_market_history/EUR_USD_latest.json`
- Candle fields: `observed_at_utc`, `open`, `high`, `low`, `close`, `volume`, `complete`
- Freshness: the final completed candle must be no more than 300 seconds old.
- Count: 3 through 500; owner handoff requests 50.

No new schema or translation layer is used. Incomplete candles and the raw OANDA midpoint object are discarded. The canonical validator rejects stale, malformed, duplicate, unordered, non-finite, or unsafe history.

## Safety boundary

Codex made no OANDA request and loaded no credentials. Capture is one-shot, Practice-only, and writes atomically to the runtime-only path. It does not evaluate a signal, generate a candidate, open a paper session, place an order, poll, schedule itself, persist credentials, or move money.

## ASUS PowerShell handoff

```powershell
Set-Location 'C:\Dev\Ai_Os'
python --version
if ([string]::IsNullOrWhiteSpace($env:OANDA_API_TOKEN)) { throw 'OANDA_API_TOKEN is not present in this process.' }
Write-Host 'OANDA Practice token is present; its value will not be printed.'
python scripts/forex_delivery/run_forex_p1_eurusd_m5_history_capture_v1.py preflight
python scripts/forex_delivery/run_forex_p1_eurusd_m5_history_capture_v1.py capture --owner-local-runtime --environment practice --instrument EUR_USD --granularity M5 --count 50 --output .aios/runtime/forex_market_history/EUR_USD_latest.json
python scripts/forex_delivery/run_forex_p1_eurusd_m5_history_capture_v1.py validate --output .aios/runtime/forex_market_history/EUR_USD_latest.json
Write-Host '.aios/runtime/forex_market_history/EUR_USD_latest.json'
$now = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
Write-Host "python scripts/forex_delivery/run_forex_p1_eurusd_market_history_signal_v1.py evaluate --history .aios/runtime/forex_market_history/EUR_USD_latest.json --output .aios/runtime/forex_signals/EUR_USD_P1_current.json --as-of-utc $now"
Write-Host 'Capture places no order, generates no signal or candidate, and opens no paper session.'
```

The command printed after capture is the existing canonical offline signal-evaluation command. Run it separately only after capture validation succeeds.
