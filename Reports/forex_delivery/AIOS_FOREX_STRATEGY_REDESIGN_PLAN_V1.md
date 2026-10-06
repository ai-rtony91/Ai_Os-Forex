# Forex Strategy Redesign Plan V1

## Failed Assumptions

- Two-close Supertrend confirmation plus the existing stop path did not produce viable LONG entries in the failed sample.
- A 10R BUY target was unreachable, but target calibration was downstream of the observed failure because no LONG reached +1R.
- Slightly positive SHORT expectancy did not survive PF and drawdown gates.
- The available replay cache cannot independently validate changes against the later campaign period.

## Next Architecture Direction

Acquire a broad, immutable M5 candle corpus spanning multiple market regimes and the approved pair universe. Freeze its provenance before research. Reconstruct signals candle-by-candle with bid/ask spread, completed-candle enforcement, and deterministic same-candle precedence. Test a small ranked set of trend-age, persistence, pullback-quality, volatility-regime, and structure-based stop hypotheses using a single chronological 50/25/25 split. Open the holdout once, promote only if PF >= 1.10, expectancy > 0, canonical percent drawdown <= 10%, adequate direction-specific trade count, contribution diversity, and parameter-neighborhood stability all pass.

Do not create Paper v2 until that evidence exists.
