# AIOS P1 EUR_USD Market-History Signal V1 Report

- Blocker closed: a canonical sanitized candle-history-to-signal decision boundary now exists.
- Rules reused: `signal_rules.py` Sprint 4 strategy identity and `regime.py` classification thresholds.
- Required history: at least 3 completed, fresh, unique, ordered EUR_USD M5 candles.
- Regime: three-candle close change versus half the average range.
- Volatility: average range divided by average close; only `NORMAL_VOLATILITY` passes.
- Stop/target: last close, three-candle lowest low, and exactly 2:1 reward-to-risk.
- BUY: only an uptrend with normal volatility and valid price ordering.
- NO_SIGNAL: a valid successful downtrend result; it creates no candidate.
- Candidate boundary: candidate generation and paper-session opening are not implemented here.
- Later history path: `.aios/runtime/forex_market_history/EUR_USD_latest.json`.
- Next packet: `AIOS-P1-EURUSD-READ-ONLY-M5-HISTORY-CAPTURE-V1`.
- Build evidence: fixtures only; zero runtime eligibility credit.
- Safety: no network, broker call, credentials, account access, orders, demo/live execution, or money movement.
