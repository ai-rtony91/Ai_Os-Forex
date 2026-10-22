# AIOS Forex Profitability Data Closure Handoff V1

WHAT HAPPENED:
Packet 025 repaired the source contracts, downloaded BoE/CFTC official artifacts, and reduced the blocker to one BLS manual-download prerequisite plus one wrapper command.

IS IT SAFE:
WAIT. Run the wrapper only outside Codex. Enter the OANDA Practice token only into the Human-only masked PowerShell prompt. Do not paste the token into Codex.

WHAT DO I DO NEXT:
From `C:\Dev\Ai.Os`, perform this one consolidated session:

1. Manually save the BLS official release calendar to:

```text
.aios/runtime/forex_official_data_human_inbox/OFFICIAL_MACRO_RELEASE_SCHEDULES_BLS_RELEASE_CALENDAR.ics
```

2. Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/forex_delivery/Run-AiOsProfitabilityDataClosure.HUMAN_ONLY.ps1
```

3. Return only these status lines to Codex:

```text
PROFITABILITY_DATA_CLOSURE_COMPLETE=TRUE
OFFICIAL_DATA_READY=TRUE
PRACTICE_HISTORY_READY=TRUE
SECRET_VALUE_EXPOSED=FALSE
LIVE_HOST_CONTACTED=FALSE
ORDER_ATTEMPTED=FALSE
```

TECHNICAL DETAILS:
- Official source families: 3
- Expanded official download artifacts: 24
- Official acquired artifacts: 23
- Official missing artifacts: 1
- Manual official downloads: 1 (`BLS_RELEASE_CALENDAR.ics`)
- Intended pair universe: 68 pairs
- Official downloader SHA-256: `20d6415641f462200204deed92a49e16b80d011141f2a3fd68a77f642ee5f6fd`
- Wrapper SHA-256: `9d35f676f75078d02073463375ac6af6bb4fcd366ecd3cbbea7f3714a26b070e`
- Practice helper SHA-256: `1b75fe4414f202f277d4beaf3ddfa6f135917fc543c01d457bc882f69194a9d2`
- Practice host only: true
- LIVE host contacted: false
- order attempted: false
- funding attempted: false
- compounding enabled: false

STOP CONDITION:
Stop immediately if any command asks you to paste a token into Codex, prints an Authorization header, contacts an OANDA LIVE host, attempts any order, asks for money, or modifies broker/account state.
