# Paper60 Supertrend Postmortem

## Measurement Integrity

No duplicates, direction contamination, stop/target inversion, or R-parity defect was found in the diagnostic first-30 slices. Canonical maximum drawdown is stored as running-equity peak-to-trough **R**, not percent; it cannot be compared directly with a 10-percent gate.

## LONG / Supertrend

All 30 diagnostic LONG trades lost; exits were {'SUPERTREND_STOP': 30}. MFE reached +0.5R in 0 trades, +1R in 0, and +2R in 0. The strongest supported cause is failure in the signal/entry/stop chain before target calibration. Exact false-trend, late-entry, and stop-placement attribution remains unknown because the preserved replay cache ends before the campaign.

## BUY 10R Target Verdict

`NON_CAUSAL_FOR_OBSERVED_FAILURES`. Recorded MFE does not prove intrabar stop/target ordering; no synthetic counterfactual fills were assigned.

## SHORT

SHORT remains a weak, uncertified edge: positive expectancy is insufficient because PF is below 1.10 and drawdown in R is excessive.
