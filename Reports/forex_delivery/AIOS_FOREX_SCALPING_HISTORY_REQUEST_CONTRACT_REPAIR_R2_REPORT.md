# AIOS Forex Scalping History Request Contract Repair R2

- Packet: PKT-EAST-FOREX-SCALPING-HISTORY-REQUEST-CONTRACT-033-R2
- Parent: PKT-EAST-FOREX-ALL-TIMEFRAME-SCALPING-EDGE-033
- Status: SCALPING_HISTORY_REQUEST_CONTRACT_REPAIRED_WAITING_HUMAN
- Classification: OANDA_PRACTICE_CANDLE_REQUEST_CONTRACT_BUG

## Root Cause

The Human-only scalping-history helper built OANDA Practice candle requests with `from`, `to`, and `count` in the same paginated request. OANDA rejects that contract.

## Repair

- Request contract before: `from + to + count`.
- Request contract after: `from + count`.
- `ToUtc` remains a local exclusive stop boundary and is not sent on each paginated request.
- `CandlesPerRequest` is the accurate field name; `BatchCount` remains as a deprecated compatibility alias.
- Checkpoint resume is per instrument/granularity series.
- Completed series are reused from checkpoint instead of redownloaded.
- Partial series resume from the first missing cursor.

## Safety

- Practice host only.
- GET only.
- No order endpoint.
- No account mutation.
- No LIVE host.
- Token remains runtime-only and prompted as a SecureString.
- No token, account identifier, auth header value, or secret value is written to report/state artifacts.

## Validation

- PowerShell parser: PASS.
- Focused pytest: PASS, `7 passed`.
- Final JSON parse, diff check, secret scan, and live/order scan are recorded in the final Codex response after final validator execution.

## Stop Point

Stop at `HUMAN_SCALPING_TIMEFRAME_DATA_ACQUISITION_REQUIRED`.

Packet 033 must resume only after physical Human Practice history artifacts exist under `.aios/runtime/forex_scalping_history_human_inbox_v1/`.
