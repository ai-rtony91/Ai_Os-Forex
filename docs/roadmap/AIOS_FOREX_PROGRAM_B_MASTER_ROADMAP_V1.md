# AIOS Forex Program B Master Roadmap V1

## Authority and scope

- Roadmap schema: `AIOS_PROGRAM_ROADMAP_CONTINUITY.v1`
- Mission: `MISSION-AIOS-CONTINUITY-001` — AIOS Master Roadmap Continuity Governance
- Program: `PROGRAM-AIOS-GOVERNANCE-ROADMAP-001` — AIOS Roadmap Persistence and Return-to-Path Control
- Tracked Forex program: `PRG-FOREX-001` — AIOS Forex Supervised Operational Validation Program
- Current continuity epic: `EPIC-AIOS-ROADMAP-CONTINUITY-001`
- Current continuity bucket: `BUCKET-AIOS-ROADMAP-CONTINUITY-001`
- Status vocabulary: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `DEFERRED`, `COMPLETE`, `SUPERSEDED`

This is the single canonical Forex Program B dependency roadmap. It is
planning and return-to-path authority only. `AGENTS.md`, `RISK_POLICY.md`,
the Strategic Campaign Registry, and current runtime evidence retain their
existing authority boundaries.

## Verified state

- Last verified UTC: `2026-08-18T15:24:58Z`
- Last verified main SHA: `dcff1d34ffa353d24f070eee2f537930b3a07a2c`
- Canonical repository: `ai-rtony91/Ai_Os`
- Current live mode: PAPER only; no LIVE or broker write authority.
- Current campaign evidence: active EUR_USD BUY session, 100 units, 0/30 qualifying closed trades.
- Current runtime evidence: cycle 62, `PAPER_SESSION_HELD`, `duplicate_position_guard`.

Runtime evidence is not replaced by this roadmap. If it conflicts with a
roadmap status, current evidence wins and the roadmap must be reconciled.

## Ordered dependency path

| Order | Bucket | Status | Dependency and evidence | Next condition |
|---:|---|---|---|---|
| 1 | Program B Bucket 1 — State and persistent monitor | COMPLETE | Persistent monitor merged in PR #1414, merge SHA `156172e7d813cac5e054fbf1280085c3ff0e75de` | Do not rerun without new evidence. |
| 2 | Program B Bucket 2 — Trade accounting integrity / open-hold-close path | COMPLETE | Repair merged in PR #1416, merge SHA `73d519dd7aca747d0b8f88cf277068a421211215`; focused accounting/evidence tests passed and current PAPER runtime is flat/resumable. | Do not rerun without new evidence. |
| 3 | Program B Bucket 3 — 30 genuine qualifying PAPER trades | BLOCKED | Active session is safely flat/resumable but qualifying count is `0/30`; depends on Bucket 2. | Resume the campaign after Bucket 2 completion. |
| 4 | Program B Bucket 4 — Continuous Post-Mortem and shadow learning | NOT_STARTED | Depends on resolved closed-trade evidence from Bucket 3. | Begin after sufficient genuine closed trades exist. |
| 5 | Program B Bucket 5 — 30-trade formal decision gate | NOT_STARTED | Depends on Bucket 3 and Bucket 4 evidence. | Begin after the 30-trade evidence set is complete. |

## Deferred strategy work

After Bucket 5, preserve this order unless the Human Owner explicitly
reprioritizes it:

1. opportunity-capture and false-negative/filter-value analysis;
2. bullish continuation breakout;
3. bullish retest/reclaim;
4. H1/M5 confirmation;
5. RSI contextual confirmation;
6. adaptive-volatility research;
7. entry-quality scoring;
8. small-profit exits;
9. break-even, trailing, and time-stop research;
10. session/regime optimization;
11. chronological walk-forward paper-candidate promotion;
12. governed expectancy, Profit Factor, drawdown, and spread/slippage gates;
13. extend 30 to 50 trades if evidence remains weak.

## Deferred release engineering

Only after the paper evidence gates pass, preserve this downstream order:

1. credential/runtime gate and owner arming;
2. governed live micro-trade and protected entry/exit receipts;
3. realized P/L reconciliation and Post-Mortem;
4. repeatability, rolling ledger, SOS/kill-switch, and calendar/news protection;
5. capital buckets, withdrawal readiness, and final LIVE release review.

These items do not authorize LIVE trading, broker writes, credential access,
money movement, or capital compounding.

## Preserved downstream items

Multi-pair expansion after EUR_USD evidence, future SHORT support under
separate approval, economic-calendar integration, spread/slippage controls,
governed risk sizing, daily drawdown protection, broker-state reconciliation,
idempotency, and capital allocation/compounding architecture remain deferred
until their dependencies are proven.

## Interruption and return protocol

Every interruption records:

```text
PATH_CLASS: MASTER_PATH | SIDE_JOB | RECOVERY | MAINTENANCE | RESEARCH
RETURN_TO_PROGRAM: PRG-FOREX-001
RETURN_TO_EPIC: EPC-FOREX-002
RETURN_TO_BUCKET: BKT-FOREX-002
```

At side-job completion, read this roadmap, verify current evidence, skip
completed buckets, and return to the first valid unfinished dependency. For
the current verified state, that return point is **Program B Bucket 3 — 30
genuine qualifying PAPER trades**. Bucket 2 is complete; the resolver must
not reopen it without new evidence.

Human Owner reprioritization overrides this automatic return point. Missing
return coordinates require roadmap inspection; they must never be guessed.

Legacy continuity notes are preserved for testability and audit traceability:

- historical snapshots may still mention that return point is **Program B Bucket 2**;
- in the current verified state, the automatic return to Bucket 3 remains the
  active dependency resolution path.
