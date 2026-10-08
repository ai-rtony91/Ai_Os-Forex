# AIOS Forex Official Data Human Handoff V1

WHAT HAPPENED:
Packet 025 repaired stale/wrong official source contracts, downloaded BoE/CFTC official artifacts, and isolated one BLS manual-download requirement.

IS IT SAFE:
WAIT. Use only public official download pages. Do not paste credentials, cookies, account data, bank data, or screenshots into Codex or the repo inbox.

WHAT DO I DO NEXT:
Complete this one data-closure session from `C:\Dev\Ai.Os`:

1. In a normal browser, open `https://www.bls.gov/schedule/news_release/`.
2. Download the official BLS release-calendar ICS from `https://www.bls.gov/schedule/news_release/bls.ics`.
3. Save it exactly here:

```text
.aios/runtime/forex_official_data_human_inbox/OFFICIAL_MACRO_RELEASE_SCHEDULES_BLS_RELEASE_CALENDAR.ics
```

4. Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/forex_delivery/Run-AiOsProfitabilityDataClosure.HUMAN_ONLY.ps1
```

TECHNICAL DETAILS:
- Central bank policy source: Bank of England `IUDBEDR` CSV, already downloaded and validated.
- CFTC source: `deacot2005.zip` through `deacot2026.zip`, already downloaded and validated.
- BLS source: official `bls.ics`, manual browser download required because automated probes received a BLS bot-policy Access Denied page.
- Official acquired artifacts: 23/24.
- Official missing artifacts: 1/24.
- Official inbox: `.aios/runtime/forex_official_data_human_inbox/`
- Manifest: `Reports/forex_delivery/AIOS_FOREX_OFFICIAL_DATA_HUMAN_DOWNLOAD_MANIFEST_V1.json`
- No credentials are required for official public data.
- No unofficial mirrors are authorized.
- No TLS/certificate bypass is authorized.

STOP CONDITION:
Stop and report if BLS does not let you download the ICS file in a normal browser, or if the wrapper prints anything indicating LIVE host contact, order attempt, credential exposure, or broker mutation.
