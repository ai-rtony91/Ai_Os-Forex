# AIOS P1 EUR_USD Market-History Signal V1

## Purpose

This contract closes the missing boundary between sanitized, genuinely observed candle history and later candidate construction. It does not capture data, create a candidate, open a paper session, or execute an order.

## Canonical rules

The evaluator imports the existing `sprint_4_intraday_trend_follow_v1` identity and calls the existing regime assessment. Its canonical input is at least **3 completed EUR_USD M5 candles** in strictly increasing UTC order. The three-candle regime compares close movement with half the average candle range. Average range divided by average close must fall between the existing low (`0.0003`) and high (`0.0020`) volatility thresholds.

A BUY requires `TRENDING_UP` and `NORMAL_VOLATILITY`. Its entry reference is the last close, its stop is the lowest low of the last three candles, and its target is exactly twice the positive stop distance above entry. Ranging is `REGIME_REJECTED`; disallowed volatility is `RISK_REJECTED`; a downtrend is the successful `NO_SIGNAL` result. Insufficient input is `REQUIRE_MORE_HISTORY`.

## Runtime boundary

Only a later, separately approved read-only history-capture packet may write `.aios/runtime/forex_market_history/EUR_USD_latest.json`. A future one-shot evaluation may write `.aios/runtime/forex_signals/EUR_USD_P1_current.json`. Fixture evidence has no genuine runtime eligibility. This build consumes no genuine history and generates no genuine signal.

The next packet is **AIOS-P1-EURUSD-READ-ONLY-M5-HISTORY-CAPTURE-V1**. It must govern read-only Practice history capture, sanitization, freshness, and runtime-only credentials without enabling orders.

## Safety

All broker writes, account access, credential persistence, candidate generation, session opening, demo/live execution, order submission, and money movement remain false. A BUY is only evidence that may be reviewed by a later packet; it is not `PAPER_ELIGIBLE` by itself.
