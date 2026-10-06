# AIOS Forex Official Source Contract Repair V1

WHAT HAPPENED:
Packet 025 repaired the official-data source contract instead of adding another HTTP client.

IS IT SAFE:
YES. Only public official endpoints were inspected; no credentials, LIVE calls, orders, funding, TLS bypass, anti-bot bypass, or unofficial mirrors were used.

WHAT DO I DO NEXT:
Download the BLS release calendar manually from the official BLS site, place it in the inbox path below, then run the one data-closure wrapper.

HOW CLOSE ARE WE:
Estimated readiness: 18% for bidirectional paper profitability certification. The current blocker is still data acquisition, not profitability proof.

WHICH MODE SHOULD I USE:
PRO.

TECHNICAL DETAILS:

PREFLIGHT:
- Worktree: `C:\Dev\Ai.Os`
- Branch: `main`
- HEAD: `b86c65140ed03d53d6c8d6c3618e50da0502f51b`
- Origin: `https://github.com/ai-rtony91/Ai_Os-Forex.git`
- Origin relation: ahead 7
- Active lock: `AIOS-LOCK-8ed298e6fcff4f1b86d023c342ab74ca`

NETWORK BASELINE:
- Human-reported WinHTTP proxy: DIRECT / NO PROXY
- Human-reported env proxy: none set
- Human-reported FRED TCP 443: PASS
- Human-reported FRED homepage curl: HTTP 200
- Codex sandbox curl: invalid for site diagnosis because it attempted unavailable proxy `127.0.0.1`
- Escalated exact-route probes: completed against public official endpoints only

SOURCE CONTRACT DIAGNOSIS:
- `CENTRAL_BANK_POLICY_HISTORY`: configured FRED `IUDERB` route is stale/invalid. Exact FRED page and CSV probes returned HTTP 404. Repaired to Bank of England `IUDBEDR` CSV.
- `CFTC_POSITIONING_HISTORY`: configured route was an HTML index, not the exact compressed archive. Repaired to `deacot{year}.zip` annual official files for 2005-2026.
- `OFFICIAL_MACRO_RELEASE_SCHEDULES`: BLS `bls.ics` is the correct official calendar artifact, but automated retrieval returned an explicit BLS Access Denied/bot-policy HTML page. Classified as Human manual official download required.

CENTRAL BANK POLICY SOURCE:
- Terminal source status: `OFFICIAL_ROUTE_REPLACED_WITH_CURRENT_OFFICIAL_ROUTE`
- Official owner: Bank of England
- Identifier: `IUDBEDR`
- Expected format/schema: CSV with `DATE,IUDBEDR`
- Current route: `https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/2005&Dateto=now&SeriesCodes=IUDBEDR&UsingCodes=Y&CSVF=TN`

CFTC SOURCE:
- Terminal source status: `OFFICIAL_ROUTE_REPLACED_WITH_CURRENT_OFFICIAL_ROUTE`
- Official owner: CFTC
- Identifier: `CFTC_FUTURES_ONLY_DEACOT_2005_2026`
- Expected format/schema: ZIP archive, `PK` signature
- Current route template: `https://www.cftc.gov/files/dea/history/deacot{year}.zip`
- Years checked by HEAD: 2005 through 2026, all HTTP 200 / `application/zip`

BLS SOURCE:
- Terminal source status: `HUMAN_MANUAL_OFFICIAL_DOWNLOAD_REQUIRED`
- Official owner: U.S. Bureau of Labor Statistics
- Identifier: `BLS_RELEASE_CALENDAR`
- Expected format/schema: ICS calendar with `BEGIN:VCALENDAR`
- Official page: `https://www.bls.gov/schedule/news_release/`
- Direct artifact: `https://www.bls.gov/schedule/news_release/bls.ics`
- Manual drop path: `.aios/runtime/forex_official_data_human_inbox/OFFICIAL_MACRO_RELEASE_SCHEDULES_BLS_RELEASE_CALENDAR.ics`

OFFICIAL DATA CLOSURE:
- BoE CSV downloaded and validated with header `DATE,IUDBEDR`.
- CFTC annual compressed files `deacot2005.zip` through `deacot2026.zip` downloaded and validated by ZIP signature.
- BLS requires manual browser download from the official provider before the wrapper can validate/reuse it.
- Current official acquired artifacts: 23/24.
- Current official missing artifacts: 1/24.

HUMAN MANUAL DOWNLOADS:
1. Open `https://www.bls.gov/schedule/news_release/`.
2. Download the official release calendar ICS from `https://www.bls.gov/schedule/news_release/bls.ics`.
3. Save it exactly as `.aios/runtime/forex_official_data_human_inbox/OFFICIAL_MACRO_RELEASE_SCHEDULES_BLS_RELEASE_CALENDAR.ics`.
4. Do not place screenshots, cookies, browser profiles, credentials, bank data, or edited files in the inbox.

PRACTICE HISTORY:
- Still requires Human-only OANDA Practice GET-only execution.
- Codex must not see the Practice token or Authorization header.
- No LIVE host, Practice orders, LIVE orders, broker/account mutation, funding, or compounding are authorized.

PROFITABILITY MILESTONE:
- `BIDIRECTIONAL_PAPER_PROFITABILITY_CERTIFIED`: FAIL / NOT REACHED.

CONTINUATION AUDIT:
- Highest-priority remaining blocker: Human data acquisition.
- Codex-resolvable P0/P1 source-contract repair work in this packet: complete.
- Alternate safe Codex actions before Human data: exhausted.
- Pre-terminal audit status: PASS for Human data gate.

STATUS:
`HUMAN_DATA_ACQUISITION_REQUIRED`
