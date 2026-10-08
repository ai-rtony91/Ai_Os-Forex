# AIOS Forex Scalping Timeframe Coverage V1

- Status: SCALPING_TIMEFRAMES_CLASSIFIED
- Unavailable: S1, S5, S10, S15, S30, S45, M1, M2, M4
- Coverage hash: 3de374cbd8f16e292cf187bafc268ce561dbe9a6726a795da86fe1a60651ab00

| TF | Status | Provider native | Dev | Reason |
|---|---|---:|---:|---|
| S1 | UNAVAILABLE_WITH_CURRENT_EVIDENCE | False | False | OANDA candle granularity list does not include S1; no tick/S1 historical source is frozen locally. |
| S5 | UNAVAILABLE_WITH_CURRENT_EVIDENCE | True | False | No current frozen local artifact at required granularity or valid lower timeframe for exact construction. |
| S10 | UNAVAILABLE_WITH_CURRENT_EVIDENCE | True | False | No current frozen local artifact at required granularity or valid lower timeframe for exact construction. |
| S15 | UNAVAILABLE_WITH_CURRENT_EVIDENCE | True | False | No current frozen local artifact at required granularity or valid lower timeframe for exact construction. |
| S30 | UNAVAILABLE_WITH_CURRENT_EVIDENCE | True | False | No current frozen local artifact at required granularity or valid lower timeframe for exact construction. |
| S45 | UNAVAILABLE_WITH_CURRENT_EVIDENCE | False | False | S45 is not provider-native and requires valid S5/S15 history; no such frozen local artifact exists. |
| M1 | UNAVAILABLE_WITH_CURRENT_EVIDENCE | True | False | No current frozen local artifact at required granularity or valid lower timeframe for exact construction. |
| M2 | UNAVAILABLE_WITH_CURRENT_EVIDENCE | True | False | No current frozen local artifact at required granularity or valid lower timeframe for exact construction. |
| M4 | UNAVAILABLE_WITH_CURRENT_EVIDENCE | True | False | No current frozen local artifact at required granularity or valid lower timeframe for exact construction. |
| M5 | NATIVE_PROVIDER_GRANULARITY | True | True |  |
| M10 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| M15 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| M30 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| H1 | NATIVE_PROVIDER_GRANULARITY | True | True |  |
| H2 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| H3 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| H4 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| H6 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| H8 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| H12 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| D1 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| W1 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| MN1 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | True | True |  |
| MO6 | DERIVED_FROM_VALID_LOWER_TIMEFRAME | False | True |  |
