# AIOS Forex Scalping History Request Contract Repair R3

- Packet: PKT-EAST-FOREX-PACKET033-FULL-ATTACK-CONTINUATION-R3
- Worker: EAST_OCC_01
- Lane: FOREX_PACKET033_FULL_ATTACK_CONTINUATION
- Status: SCALPING_HISTORY_REQUEST_CONTRACT_REPAIRED_WAITING_HUMAN
- Updated UTC: 2026-08-31T04:02:35Z

## Root Cause

The original Human-only OANDA Practice helper built paginated candle requests with `from`, `to`, and `count` together. OANDA rejects that contract.

## Request Contract

- Before: FROM_PLUS_TO_PLUS_COUNT_INVALID.
- After: FROM_PLUS_COUNT.
- Remote request sends: instrument path, granularity, price, from, count, includeFirst.
- Remote request does not send: overall ToUtc.
- Overall ToUtc is a local exclusive stop boundary.

## Pagination

- First request uses `from=overall FromUtc` and `includeFirst=true`.
- Later requests use `from=last accepted completed candle timestamp` and `includeFirst=false`.
- This avoids duplicate boundary candles without adding a fixed interval to the remote cursor across market gaps.
- Local completion uses the granularity interval boundary after the last accepted candle.

## Checkpoint / Resume

- Per-series checkpoint remains `AIOS_FOREX_SCALPING_HISTORY_CHECKPOINT.json`.
- Checkpoint now records scope fingerprint, helper SHA-256, batch ledger, artifact path, artifact SHA-256, accepted row counts, last accepted timestamp, next request cursor, and next local boundary.
- Completed series are reused without redownload.
- Partial series resume from the first missing request.
- Legacy R2 partial checkpoints migrate by using `last_candle_utc` as the next exclusive request cursor, preventing a one-candle skip.
- Legacy checkpoints without batch ledgers must still have matching batch files and candle counts before reuse.

## Retry / Fail Closed

- Retryable: 408, 425, 429, 500, 502, 503, 504, timeout, temporary transport, connection reset.
- Maximum attempts per request: 5 by default.
- Retry-After is honored when safely available.
- 401/403 fail closed as CREDENTIAL_OR_AUTHORIZATION_FAILURE.
- Other nonretryable 4xx fail closed as REQUEST_CONTRACT_FAILURE.

## WhatIf

WhatIf requires no credential, makes no HTTP request, and reports `candles_per_request`, `pagination_contract=FROM_PLUS_COUNT`, `to_sent_on_each_request=false`, `include_first_strategy`, retry status, atomic promotion status, scope fingerprint, and safety flags.

## Data-Volume / Request Estimate

For the R3 three-pair handoff from `2024-01-01T00:00:00Z` through exclusive `2026-08-30T00:00:00Z`, the calendar upper-bound estimate is 21 instrument/granularity series, about 108,125,280 possible completed bars before weekend/holiday gaps, and about 21,630 OANDA requests at 5,000 candles per request. Largest calendar upper-bound series is S5 at about 16,796,160 bars per pair and 3,360 requests per pair. This is an estimate only, not evidence of downloaded data.

## Safety

- Practice host only.
- GET only.
- No order endpoint.
- No account endpoint request.
- No LIVE host.
- Token is runtime-only SecureString and is not written to report/state/artifacts.
- Authorization header value is not printed.

## Validation Coverage

Focused pytest result: `19 passed`.

Focused pytest covers URI shape, local ToUtc boundary, FromUtc inclusion, ToUtc exclusion, includeFirst behavior, deterministic cursoring, weekend-gap-style cursoring, duplicate prevention, final data boundary, checkpoint resume, completed-series reuse, legacy missing-artifact failure, incompatible price-scope failure, artifact hash mismatch fail-closed, empty end-of-history partial stop, retryable HTTP classes, Retry-After, retry exhaustion, malformed response failure, 401/403 fail-closed, request-contract 4xx fail-closed, response identity validation, incomplete candle exclusion, out-of-order failure, duplicate failure, missing bid/ask/mid failure, unsupported granularity pre-credential failure, token non-exposure, LIVE/order impossibility, WhatIf no request/no credential, JSON parse, and PowerShell parse.

## Human Gate

Codex cannot enter the Human-only OANDA Practice token and did not contact OANDA. Packet 033 remains blocked until the Human runs the corrected acquisition command and physical artifacts exist under `.aios/runtime/forex_scalping_history_human_inbox_v1`.
