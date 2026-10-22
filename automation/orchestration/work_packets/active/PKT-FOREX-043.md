CODEX-ONLY PROMPT
AI_OS EXECUTION TOKEN
AI_OS BOOTSTRAP REQUIRED

# PKT-FOREX-043 — Factor/Common-Component Momentum Stage-0 Preregistration

IDENTITY MARKER: PKT_FOREX_043_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0
SUPERVISOR IDENTITY: Codex East
PACKET ID: PKT-FOREX-043
PACKET NAME: Factor/Common-Component Momentum Stage-0 Preregistration
MODE: APPLY — STAGE 0 ONLY
ZONE: EAST
WORKER IDENTITY: EAST_OCC_80
LANE: FOREX_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0
WORKTREE: C:\Dev\Ai.Os
BRANCH: main, observed and preserved during preflight
LOCK ID: LOCK_EAST_FOREX_FACTOR_COMMON_COMPONENT_MOMENTUM_STAGE0_OCC80
APPROVAL AUTHORITY: Anthony, Human Owner, explicit PKT-FOREX-043 authorization

MISSION ID: MISSION-AIOS-001
MISSION NAME: AIOS Governed Self-Building Operating System
PROGRAM ID: PRG-FOREX-001
PROGRAM NAME: AIOS Forex Supervised Operational Validation Program V1
EPIC ID: EPC-FOREX-002
EPIC NAME: Strategy Intelligence V1
BUCKET ID: BKT-FOREX-003
BUCKET NAME: Strategy Validation V1

## Mission

Use the corrected PKT-FOREX-042 failure evidence to preregister a materially distinct, no-outcome experiment that separates fitted common currency movement from pair-specific residual movement and tests whether either contains forward information beyond the rejected simple pair-momentum representation.

## Allowed paths

- `automation/orchestration/work_packets/active/PKT-FOREX-043.md`
- `automation/forex_engine/forex_factor_common_component_momentum_stage0_v1.py`
- `scripts/forex_delivery/run_forex_factor_common_component_momentum_stage0_v1.py`
- `tests/forex_engine/test_forex_factor_common_component_momentum_stage0_v1.py`
- `.aios/staging/PKT_FOREX_043/`
- `.aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_GLOBAL_TRIAL_LEDGER_V1.jsonl`
- `.aios/runtime/forex_edge_validation_pipeline_v1/AIOS_FOREX_FINGERPRINT_INDEX_V1.json`
- `automation/orchestration/locks/FILE_LOCK_REGISTRY.json` only for the exact OCC80 claim/release lifecycle

## Forbidden paths and actions

All other paths are read-only. Do not open raw market outcomes, price-bearing replay caches, validation evidence, contaminated holdout evidence, brokers, credentials, Practice, PAPER, LIVE, orders, or money movement. Do not modify PKT-FOREX-039/042 evidence or scientific results. Do not add unrelated model families or parameter sweeps. Do not switch branches, reset, stash, clean unrelated work, stage, commit, push, merge, create a PR, deploy, or install packages.

## Frozen scientific contract

- Components: fitted `CURRENCY_COMMON_COMPONENT` and `PAIR_SPECIFIC_RESIDUAL` from synchronized native log returns.
- Graph: deterministic base-plus-one/quote-minus-one orientation, constrained least squares, currency strengths sum to zero, stable 58-pair native membership, and whole-timestamp exclusion for missing observations.
- Formation windows: `12`, `48`, and `288` completed M5 intervals.
- Forward measurement horizons: `3`, `12`, and `48` completed M5 intervals.
- Directions: economic direction and exact inverse on the same opportunities.
- New specifications: `36`; matched historical pair-momentum baselines: `18`; maximum later outcome cells: `54`.
- Normalization: causal sample standard deviation of the last `288` completed one-bar component returns; absolute signal threshold `1.0`.
- Baseline: corrected PKT-FOREX-039 Arm A normalized pair momentum with matching lookback, horizon, and direction.
- Comparisons: executed-event results, full synchronized population with unselected opportunities zero, and causal selection-count-matched baseline.
- Costs: PKT-FOREX-040 side-correct `GROSS/BASE/STRESSED/SEVERE_BUT_PLAUSIBLE`; no pooled-pip or frictionless profitability claim.
- Stage-0 promotion: proposed-unscored only. A later development screen is outcome-informed exploratory research and cannot independently confirm the hypothesis.
- Current validation provenance: `REUSED`; current holdout provenance: `CONTAMINATED`.
- Independent confirmation requires newly sealed observations strictly after `2026-08-29T03:50:00Z` or an independent certified dataset.

## Validator chain

1. Authority, repository state, corrected-source hashes, research-memory integrity, and zero-lock preflight.
2. Canonical OCC80 preview and exact claim.
3. Metadata-only 58-pair and exact `EUR_HUF`/`USD_HUF`/`HKD_JPY` precision validation.
4. Novelty, fingerprint, graph identifiability, contract completeness, boundary, and no-market-access tests.
5. Focused PKT-FOREX-043 synthetic tests and applicable PKT-FOREX-038/039/040/041/042 regressions.
6. Two isolated deterministic Stage-0 runs and byte-for-byte artifact comparison.
7. Append-only 36-proposal registration, zero scored-trial increment, and idempotent re-registration verification.
8. Canonical memory readback, artifact manifest/receipt/hash validation, scoped diff, and `git diff --check`.
9. Exact OCC80 release, lock-registry integrity, zero-active-lock, no-commit, and no-push verification.

## Stop point

Stop after all 36 eligible specifications are frozen and registered once as proposed-unscored, the maximum 54-cell later screen is frozen, two Stage-0 runs reproduce byte-for-byte, canonical research memory preserves the 1,292 scored-attempt lower bound, no market/validation/holdout rows are opened, OCC80 is released, and one exact minimum Stage-1 scoring approval sentence is prepared. Do not score under this authority.

## Final report

Use the mandatory Owner View and successful APPLY report. Include hypothesis, novelty, eligibility/duplicate counts, proposed count, screen budget, baseline, evidence status, tests, reproduction hashes, idempotency, memory and access counters, prior-evidence preservation, lock status, exact files, no-commit/no-push, and one exact successor approval sentence.

## Execution state

- Status: `STAGE0_ARTIFACTS_AND_REGISTRATION_COMPLETE_REGRESSION_INTEGRATION_BLOCKED`.
- OCC80: `ACTIVE_PENDING_BLOCKED_RELEASE`.
- Eligible genuinely distinct specifications: `36`; duplicate or ineligible new specifications: `0`.
- Historical matched pair-momentum baselines: `18`; frozen maximum later screen: `54` cells.
- Stage-0 reproduction aggregate SHA-256: `5793d495145e9d56d5c4bb0c40ab9d310264a24bedd3d1ce3136921b08fd1ed4`; byte-identical: `TRUE`.
- Focused synthetic tests: `14 passed`.
- Applicable chain before canonical registration: `100 passed`, `1` previously certified out-of-scope staging test deselected.
- Canonical proposal registration: `36` appended once; second promotion was idempotent; scored-attempt lower bound remained `1292`.
- Canonical ledger SHA-256: `5101414160c7d803a820786d69818dc575bed549205ef5661a7fb54958248d20`.
- Canonical fingerprint-index SHA-256: `6df7c2a7a1b1b301a3f43179542b228eda20492a5094cc486a2ba0195776f078`.
- Post-registration regression: `97 passed`, `3 failed`, `1 deselected`; all three failures are the legacy PKT-FOREX-039 whole-global-memory hash pin rejecting the authorized append-only PKT-FOREX-043 registration.
- Blocker: repairing the extensibility contract requires separately authorized edits to PKT-FOREX-039 source/tests and the PKT-FOREX-040 hash-pinning regression. The 36 proposals and scientific artifacts remain valid proposed-unscored evidence and must not be erased.
- Verified edge: `FALSE`.
- Market rows opened: `0`.
- Validation rows opened: `0`.
- Holdout rows opened: `0`.
- New scored-trial increment: `0`.
- Commit: `NOT_PERFORMED`.
- Push: `NOT_PERFORMED`.
