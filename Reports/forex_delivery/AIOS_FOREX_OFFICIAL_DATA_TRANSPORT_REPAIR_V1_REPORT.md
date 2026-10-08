# AIOS Forex Official Data Transport Repair V1

Packet: `PKT-EAST-FOREX-FULL-ATTACK-PRO-REPAIR-024`

Status: `HUMAN_DATA_ACQUISITION_REQUIRED`

## What changed

The official public-data helper was repaired from a single `Invoke-WebRequest` path into a bounded failover ladder:

1. PowerShell `Invoke-WebRequest`
2. `curl.exe`
3. .NET `HttpClient`

The helper now validates official HTTPS hosts, uses bounded attempts and timeouts, downloads to a temporary file first, validates nonempty/schema-compatible content, and only then promotes the artifact to the final inbox path.

## Failure classification

The observed failure is classified as `TRANSIENT_TRANSPORT_FAILURE`.

It is not an OANDA Practice token failure, an OANDA authentication failure, a Practice-history failure, a profitability-engine failure, or a LIVE failure.

## Smoke-test result

A bounded public GET smoke test exercised all three transports for the first official endpoint. Both sandbox and outside-sandbox execution failed transiently in this runtime. No final artifact or partial file was promoted.

That result leaves Human-side data closure as the correct next gate.

## Safety

- No credential was requested.
- No credential was read.
- No OANDA Practice request was made.
- No OANDA LIVE request was made.
- No order endpoint was used.
- No certificate validation bypass was added.
- No money movement was performed.

## Next Human action

Run exactly:

```powershell
cd C:\Dev\Ai.Os
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/forex_delivery/Run-AiOsProfitabilityDataClosure.HUMAN_ONLY.ps1
```

Return only the status lines requested by the packet. Do not paste any token or account value into Codex.
