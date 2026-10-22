# AIOS Forex Practice History Human Handoff V1

WHAT HAPPENED:
The Human-only Practice acquisition helper now has R1 hardening for PowerShell HTTP 504 error records, bounded transient retries, atomic per-batch checkpoint/resume, and completed-artifact reuse. Current local evidence proves the resume point is still `GBP_CAD` batch 2, not `AUD_CAD`.

IS IT SAFE:
YES for the Codex repair. Codex did not request, read, print, hash, or persist the Practice token. No OANDA LIVE host, order endpoint, broker/account mutation, or money movement was used.

CURRENT PRACTICE HISTORY:
- intended instruments: 58
- complete instruments: 29
- completed instruments: AUD_CAD, AUD_CHF, AUD_HKD, AUD_JPY, AUD_NZD, AUD_SGD, AUD_USD, CAD_CHF, CAD_HKD, CAD_JPY, CAD_SGD, CHF_HKD, CHF_JPY, CHF_ZAR, EUR_AUD, EUR_CAD, EUR_CHF, EUR_CZK, EUR_GBP, EUR_HKD, EUR_HUF, EUR_JPY, EUR_NZD, EUR_PLN, EUR_SEK, EUR_SGD, EUR_USD, EUR_ZAR, GBP_AUD
- partial instrument: GBP_CAD
- last validated batch: GBP_CAD batch 1
- first missing batch: GBP_CAD batch 2
- first missing request start: 2005-10-10T23:00:00Z
- preserved candle count: 4,118,548
- completed-instrument candle count: 3,973,548
- partial/incomplete-instrument candle count: 145,000
- current manifest hash: 607db8eb44ce100f7f6587ed4e7282a1317e5438b680d6b4054bcfe13c9a03d4

504 ROOT CAUSE CLASSIFICATION:
Transient upstream/network failure plus a retry-classifier gap. The Human rerun correctly resumed at `GBP_CAD` batch 2, then another HTTP 504 escaped because this PowerShell failure shape can expose the status in the full error record text/details instead of only `Exception.Response.StatusCode`.

RETRY POLICY:
The helper retries only transient failures: HTTP 408, 425, 429, 500, 502, 503, 504, timeout, connection reset, temporary receive failure, and equivalent temporary receive messages. It now reads status from `Exception.Response`, `ErrorRecord.Exception.Response`, and sanitized error-record text/details; `Invoke-RestMethod` runs with `-ErrorAction Stop`. It uses bounded exponential backoff with jitter, honors safe `Retry-After`, and caps at 5 attempts per exact batch. HTTP 401/403 fail closed as credential/authorization failures. HTTP 404 fails closed as request/instrument contract failure. Malformed response fails closed after one clean retry.

CHECKPOINT/RESUME:
Every newly validated batch writes sanitized checkpoint metadata before the next request. `GBP_CAD` batch 1 predates the checkpoint repair, so no `GBP_CAD` checkpoint file exists yet; resume is derived deterministically from the validated `GBP_CAD.H1.json` artifact hash and last candle. Current evidence says the next Human run should reuse `AUD_CAD` through `GBP_AUD`, validate `GBP_CAD.H1.json`, and continue from `2005-10-10T23:00:00Z`.

FILES CHANGED:
- `scripts/forex_delivery/Acquire-AiOsOandaPracticeHistory.HUMAN_ONLY.ps1`
- `tests/forex_engine/test_oanda_practice_history_human_only_v1.py`
- `Reports/forex_delivery/AIOS_FOREX_PRACTICE_HISTORY_HUMAN_HANDOFF_V1.md`
- `Reports/forex_delivery/AIOS_FOREX_PRACTICE_HISTORY_HUMAN_HANDOFF_V1_STATE.json`
- `Reports/forex_delivery/AIOS_FOREX_ATTACK_TO_FINISH_V4_REPORT.md`
- `Reports/forex_delivery/AIOS_FOREX_ATTACK_TO_FINISH_V4_STATE.json`

VALIDATION:
- PowerShell parser: PASS
- Focused pytest: PASS, 15 passed
- Current artifact audit: PASS for 58 parseable local H1 artifacts; 29 complete to cutoff, 29 partial/incomplete
- Active lock scan: PASS, active lock count 0
- Secret boundary: PASS, no token was requested from Codex and helper keeps token runtime-only
- LIVE/order boundary: PASS, helper remains Practice host, GET-only, no order methods

HUMAN RESUME COMMAND:
```powershell
cd C:\Dev\Ai.Os
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\forex_delivery\Run-AiOsProfitabilityDataClosure.HUMAN_ONLY.ps1
```

ATTACK_TO_FINISH:
Resume Packet 026-PRO only after the Human-only wrapper finishes and the manifest validates 58/58. Do not claim Practice history complete until the Human run actually finishes all 58 instruments.

STATUS:
REPAIR_R1_PASS_WAITING_HUMAN_RERUN
