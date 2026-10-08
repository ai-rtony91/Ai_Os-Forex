CODEX-ONLY PROMPT

AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

IDENTITY MARKER: AI_OS_CODEX_APPLY_PACKET
SUPERVISOR IDENTITY: Anthony Human Owner
PACKET ID: PKT-FOREX-025
PACKET NAME: DST-Aware Session Inventory Cycle Stage-1 Screen
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_60
LANE: FOREX_SESSION_INVENTORY_CYCLE_STAGE1
WORKTREE: C:\Dev\Ai.Os
BRANCH: main

MISSION ID: MISSION-AIOS-001
MISSION NAME: AIOS Governed Self-Building Operating System
PROGRAM ID: PRG-FOREX-001
PROGRAM NAME: AIOS Forex Supervised Operational Validation Program V1
EPIC ID: EPC-FOREX-002
EPIC NAME: Strategy Intelligence V1
BUCKET ID: BKT-FOREX-003
BUCKET NAME: Strategy Validation V1

ALLOWED PATHS:
- automation/orchestration/work_packets/active/PKT-FOREX-025.md
- automation/forex_engine/forex_session_inventory_cycle_v1.py
- tests/forex_engine/test_forex_session_inventory_cycle_v1.py
- scripts/forex_delivery/run_forex_session_inventory_cycle_v1.py
- .aios/staging/PKT_FOREX_025/
- automation/orchestration/locks/FILE_LOCK_REGISTRY.json only through approved claim and release scripts

FORBIDDEN PATHS:
- AGENTS.md
- RISK_POLICY.md
- .git/
- .github/
- Reports/
- .aios/runtime/
- secrets/
- credentials/
- .env
- broker/
- oanda/
- live_trading/
- webhooks/
- every path not listed in ALLOWED PATHS

APPROVAL AUTHORITY: Anthony explicitly directed continuous bounded historical edge research. This packet reads frozen historical data and writes isolated staging artifacts only. Commit, push, merge, deployment, canonical promotion, final-holdout access, broker access, credentials, PAPER, Practice, LIVE, orders, collectors, and money movement remain unauthorized.

NO-REPOSITORY-PUBLISH AUTHORITY: Anthony explicitly requires no commit and no push. Merge and deployment are outside this packet.

PROTECTED ACTION RULE: Commit/push/merge need separate explicit approval. Canonical promotion, new protected write boundaries, and final-holdout execution also each require separate explicit Human Owner approval. Approval does not transfer between actions.

PREFLIGHT:
- require main branch without switching or cleaning unrelated work
- require registry SHA-256 a5455f70b657d89874d01f1e2a7db19cd22ec924f39a3f26dba09291950f3327
- require zero active locks
- require PKT-FOREX-024 completion SHA-256 abdb2f01307109a3f997461d062053a1327b29d1bdc3a6fd3f04864d60425f17
- claim exactly LOCK_EAST_FOREX_SESSION_INVENTORY_CYCLE_STAGE1_OCC60

MISSION:
Test whether recurring local-hours inventory demand creates a cost-resistant four-hour FX return cycle, distinct from rejected price breakout, reversal, momentum, pullback, and session-breakout rules.

OBJECTIVE:
Produce one deterministic Stage-1 accept-or-reject decision for five exact direction variants on chronological development data only, with full costs, baselines, global search adjustment, and no later-period access.

SOURCE HYPOTHESES:
- SNB-linked Ranaldo research on segmentation and time-of-day FX patterns
- Breedon and Ranaldo SNB working paper on intraday FX returns and order flow
- Sources are UNVERIFIED_HYPOTHESIS_SOURCE inputs, never proof of edge

EXACT EXPERIMENT:
- Certified M5 corpus fingerprint 44bad0bb22fa88771c824c2c91551fef7116a458d5d7fee7039f5f87c76dac6a.
- Development 2024-01-01 inclusive through 2025-04-01 exclusive; final holdout starts 2026-01-01 and remains sealed.
- Eligible currencies and IANA zones: JPY Asia/Tokyo; AUD Australia/Sydney; NZD Pacific/Auckland; EUR/GBP/CHF Europe/London; USD/CAD America/New_York.
- Eligible pairs are every frozen 58-pair member whose two currencies are mapped to different session zones. Same-zone pairs and unmapped currencies are excluded by the frozen eligibility rule.
- At the completed 08:00 local M5 bar for the base currency, original direction SHORT; at the completed 08:00 local M5 bar for the quote currency, original direction LONG.
- Entry is the next M5 executable open. Exit is first 2.0-ATR protective stop or the close of the 48th M5 holding bar. No take profit.
- Five candidates: ORIGINAL_LONG, EXACT_REVERSED_SHORT, ORIGINAL_SHORT, EXACT_REVERSED_LONG, and SYMMETRIC_BIDIRECTIONAL.
- Base costs are observed bid/ask plus 0.10 pip slippage per side; stress uses 0.50 pip per side; gross uses midpoint and zero slippage.
- Risk is 0.25 percent simulated equity at the stop. Enforce one pair, no shared currency, maximum five simultaneous positions.
- Exclude nonconsecutive paths, all 18-bar fold-boundary embargoes, and paths touching 21:45 through 22:15 UTC.
- Six chronological development folds.
- Preserve every accepted trade in deterministic gzip JSONL with the complete required journal fields.

BASELINES:
- no trade zero
- matched-frequency deterministic random direction
- exact reversed-direction candidates
- simple prior-completed-bar direction at the same event timestamps
- gross, base-cost, and stress-cost comparisons

STAGE-1 GATES:
- gross expectancy greater than zero
- net expectancy strictly greater than zero
- profit factor at least 1.10
- maximum drawdown no greater than 10 percent
- at least 200 trades, two pairs, six currencies, and four positive chronological folds
- stress expectancy greater than zero
- net expectancy beats no-trade, random-direction, and simple baselines
- pair and currency concentration each no greater than 50 percent
- symmetric candidate has at least 50 trades per direction
- leakage and accounting PASS
- Bonferroni and block-bootstrap adjusted lower expectancy bound over at least 1,179 actual attempts is positive

TRIAL ACCOUNTING:
- Valid completion adds exactly five actual candidates, moving the computational-attempt lower bound from 1,174 to 1,179.
- Baselines are fixed controls, not selected candidates.
- Implementation defects add zero trials and require unchanged repair and rerun.

FAILURE ROUTING:
- Preserve complete metrics, inverse comparisons, costs, break-even cost, folds, concentration, baselines, fingerprints, prohibited repeats, and next distinct hypothesis.
- Failed Stage-1 candidates do not open validation data.

VALIDATOR CHAIN:
- packet governance and completeness review
- focused pytest
- two isolated complete runs
- byte-identical names and bytes
- JSON and full gzip journal validation
- all opened partition hashes, timestamps, completed-candle entry, DST conversion, embargo, rollover, costs, exposure, baselines, trial count, postmortem, and sealed-holdout checks
- git diff --check and scoped readback
- lock-registry integrity

STOP POINT:
After valid deterministic Stage-1 completion, release only OCC60 and verify zero active locks. Continue to Stage 2 only for a full survivor; otherwise select the next distinct cluster. Never commit or push.

SAFE NEXT ACTION:
Claim OCC60, execute both isolated development runs, validate the truthful result, release OCC60, and continue from the updated rejection memory.

FINAL REPORT FORMAT:
Only VERIFIED EDGE FOUND, HUMAN APPROVAL REQUIRED, or a hash-verified RESUMABLE_EDGE_RESEARCH checkpoint caused by unavoidable platform/runtime termination.
