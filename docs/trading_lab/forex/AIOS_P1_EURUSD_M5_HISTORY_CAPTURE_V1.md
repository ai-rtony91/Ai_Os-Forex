# AIOS P1 EUR_USD M5 History Capture V1

## Protected capability

`AIOS_OANDA_PRACTICE_CANDLE_HISTORY_TRANSPORT.v1` is a physically separate,
Practice-only transport. Its sole representable request is one HTTPS `GET` to
`api-fxpractice.oanda.com/v3/instruments/EUR_USD/candles` with `granularity=M5`,
`price=M`, and `count=50`. The timeout is exactly 10 seconds, the request budget
is one attempted request, retries are zero, and redirects or changed final URLs
are rejected.

The transport has no environment, host, path, account ID, or generic request
input. It exposes no current-pricing, account, position, trade, transaction, or
order capability. It does not use or authorize `OandaReadOnlyClient`.

## Owner-session approval

Capture requires a repository-local, non-symlink approval below
`.aios/runtime/forex_authorizations/` using the exact schema
`AIOS_OANDA_PRACTICE_CANDLE_SESSION_APPROVAL.v1`. The approval binds the Human
Owner, packet ID, fixed endpoint and request values, canonical output path, and
`AFTER_ONE_SANITIZED_WRITE_OR_FAILURE` stop point. Its explicit UTC window may
not exceed 15 minutes and must be current. Unknown, duplicate, non-finite, or
sensitive fields fail closed. Validators cannot create or extend approval.

Only owner-started capture mode reads `OANDA_API_TOKEN`; it neither reports nor
persists the token. No account ID is read or accepted. The response is decoded
with duplicate-key and non-finite rejection, strict allowlists at every object
boundary, and canonical candle validation before atomic publication. Raw broker
payloads, headers, and private metadata are never returned or persisted. Output
is limited to the ignored runtime path
`.aios/runtime/forex_market_history/EUR_USD_latest.json`.

## One-shot boundary and exclusions

The file historically named “loop” now accepts exactly one cycle. It performs no
sleep, wait, retry, continuation, background work, or paper-session opening. The
repair does not authorize current pricing, account endpoints, snapshot capture,
capture-and-open, supervised paper-session opening, demo or live orders, order
mutation, money movement, or broker access during tests. Fake responses are used
for tests.

`RISK_POLICY.md` remains unchanged. Capture remains blocked until a later Tier 4
protected-policy review and separate Human Owner policy approval.
