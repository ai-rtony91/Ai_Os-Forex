CODEX-ONLY PROMPT
AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

# PKT-FOREX-042-R1 — PKT-042 Legacy Regression Repair

IDENTITY MARKER: PKT_FOREX_042_R1_LEGACY_REGRESSION_REPAIR
SUPERVISOR IDENTITY: Codex East
PACKET ID: PKT-FOREX-042-R1
PACKET NAME: PKT-042 Legacy Regression Repair
MODE: APPLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_79
LANE: FOREX_EDGE_DISCOVERY_TOURNAMENT_STAGE1_CORRECTIVE_R1
WORKTREE: C:\Dev\Ai.Os
BRANCH: main, observed during preflight and preserved
LOCK ID: LOCK_EAST_FOREX_EDGE_DISCOVERY_TOURNAMENT_STAGE1_CORRECTIVE_R1_OCC79
APPROVAL AUTHORITY: Anthony, Human Owner, explicit PKT-FOREX-042-R1 authorization

MISSION ID: MISSION-AIOS-001
MISSION NAME: AIOS Governed Self-Building Operating System
PROGRAM ID: PRG-FOREX-001
PROGRAM NAME: AIOS Forex Supervised Operational Validation Program V1
EPIC ID: EPC-FOREX-002
EPIC NAME: Strategy Intelligence V1
BUCKET ID: BKT-FOREX-003
BUCKET NAME: Strategy Validation V1

## Mission

Repair only the stale PKT-FOREX-039 frozen-hash expectations left by the authorized PKT-FOREX-042 correction. Re-run the two formerly blocked legacy regressions and the full relevant PKT-FOREX-038/039/040/041/042 regression chain without reopening market data or altering corrected scientific evidence.

## Preflight evidence

- Repository root: `C:\Dev\Ai.Os`.
- Branch: `main`; preserved without switching.
- PKT-FOREX-042 scientific aggregate SHA-256: `91d30e630c0c71c7f3c440ea84943b6931f423a3e781c1977d4f64565c5cd6f7`.
- Corrected artifact runs: byte-identical, 13 artifacts, zero mismatches.
- PKT-FOREX-038 isolation regression: `PASS` when its authorized packet-scoped temporary staging writes are permitted.
- Remaining regression failure: only the stale pre-correction PKT-FOREX-039 hash expectation.
- Active locks before claim: `0`.
- OCC79 canonical preview: collision-free and policy-block-free.

## Allowed paths

- `automation/orchestration/work_packets/active/PKT-FOREX-042-R1.md`
- `tests/forex_engine/test_forex_edge_validation_pipeline_v1.py`
- `automation/orchestration/locks/FILE_LOCK_REGISTRY.json` only for the exact OCC79 claim/release lifecycle
- Test-generated temporary artifacts only under `.aios/staging/PKT_FOREX_038/`

## Forbidden paths and actions

All other paths are read-only. Do not modify scientific source, PKT-FOREX-039, PKT-FOREX-042, canonical trial or fingerprint memory, corrected artifacts, candidate rules, outcomes, costs, thresholds, entries, exits, directions, graph rules, pullback rules, or classifications. Do not open market, validation, or holdout data. Do not access brokers, credentials, Practice, PAPER, LIVE, orders, or money movement. Do not switch branches, reset, stash, clean unrelated work, stage, commit, push, merge, create a PR, deploy, or install packages.

## Authoritative corrected hashes

- `automation/orchestration/work_packets/active/PKT-FOREX-039.md`: `69517621a5b1875d86c5490863f7bb6099942c6ba6e9e812bd647e03ec64944d`
- `automation/forex_engine/forex_edge_discovery_tournament_stage1_v1.py`: `7298f9169903b0a3a0fc48035a7e691a4e6a8b4930ed3695ed4f1561d8ff137b`
- `scripts/forex_delivery/run_forex_edge_discovery_tournament_stage1_v1.py`: `4832af379e30ab3525c208f197704069e8fe32abe3ddfad02adb5480aea940ab`

## Validator chain

1. Direct stale-hash regression.
2. Direct PKT-FOREX-038 isolation regression.
3. Complete relevant PKT-FOREX-038/039/040/041/042 regression chain.
4. Corrected two-run artifact comparison and aggregate-hash readback.
5. Canonical trial-ledger and fingerprint-index unchanged-hash readback.
6. AST, scoped diff, and `git diff --check` validation.
7. Exact OCC79 release, lock-registry integrity, and zero-active-lock verification.
8. No-market-read, no-new-score, no-commit, and no-push verification.

## Stop point

Stop after the stale-hash and isolation regressions pass, the full relevant chain passes, corrected scientific artifacts and research memory remain unchanged, OCC79 is released, registry integrity passes, active locks return to zero, and one exact approval sentence is prepared for the next Stage-0 edge-research packet. Do not execute the successor.

## Final report

Use the mandatory Owner View and successful APPLY report. Include packet and lock status, both legacy regressions, full regression result, access and trial counters, unchanged memory and scientific hashes, files changed, scoped diff, no-commit/no-push status, final PKT-FOREX-042 certification, and one exact successor approval sentence.

## Execution state

- Status: `COMPLETE_REGRESSION_CERTIFICATION_PENDING_LOCK_RELEASE`.
- OCC79: `ACTIVE_PENDING_FINAL_RELEASE`.
- Direct formerly blocked regressions: `2 passed`.
- Full relevant PKT-FOREX-038/039/040/041/042 regression chain: `87 passed`.
- PKT-FOREX-042 artifact aggregate: `91d30e630c0c71c7f3c440ea84943b6931f423a3e781c1977d4f64565c5cd6f7`; byte-identical: `TRUE`.
- Canonical trial-ledger SHA-256 unchanged: `3bb0bc50e720e76be3834da3457a35ef7b32d7f99696950703cb2bbe4042b468`.
- Canonical fingerprint-index SHA-256 unchanged: `9bd8a5cb1bc72f07fbb048389157457fe7a6e987c473178d373b5cff2b3c5a0f`.
- Market rows opened: `0`.
- Validation rows opened: `0`.
- Holdout rows opened: `0`.
- New scored-trial increment: `0`.
- Verified edge: `FALSE`.
- Commit: `NOT_PERFORMED`.
- Push: `NOT_PERFORMED`.
