# 24/7 Forex-First Research Workflow — Phase 1 Design

## Purpose

Phase 1 is a local, deterministic control plane for evidence-producing research.
It prioritizes AIOS/Forex research through EUR/USD and retains CME index futures as a comparison lane. It
does not claim an edge from a single backtest and it does not enable trading.

## Fixed campaign contract

- Exactly two lanes: `FOREX_EURUSD_PRIMARY` and `CME_INDEX_FUTURES_COMPARISON`.
- A finite, fingerprinted experiment catalog with a positive approved budget.
- Each experiment binds market lane, strategy, instrument, session/window, cost
  scenario, parameters, expected evidence version, and data capability.
- Required stages: `CHEAP_SCREEN`, `COST`, `WALK_FORWARD`, `TRUE_OOS`,
  `STRESS`, `REPLICATION`, and `PAPER`.
- Forex candidates require a pinned data capability with source, calendar,
  positive pip value, and cost-model identifiers. Futures comparison candidates
  require source, contract, calendar, positive tick value, and cost-model
  identifiers. Without pinned lane-specific capability, the controller returns a
  lane-specific data capability block; it never fabricates market evidence.
- The controller never repeats a completed fingerprint. Scientific rejection
  prunes its later stages and returns `NO_EDGE_IN_SCOPE` only after viable scope
  is exhausted. A spent work budget or passing lineage missing later validation
  returns `BUDGET_EXHAUSTED`. Fully completed research returns
  `RESEARCH_COMPLETE` for review, with no trading authority or readiness claim.
- Supplied outcomes must fit the approved budget, follow passing predecessor
  stages in time, and cannot be completed after the explicit UTC routing clock.
  Timestamp checks preserve fractional seconds.

## Evidence and promotion

The fixed 100-point evidence model is: data 10, backtest/replay 10, costs 10,
strategy discovery 10, out-of-sample 15, market/time transfer 10, stress 10,
paper validation 10, execution/recovery 5, risk 5, and live micro 5.

Only evidence with a known category, source ID, version, and `PASS` status earns
points. Engineering and edge-evidence meters are independently normalized; live
readiness is their lower value. Neither meter grants live authority.

`PAPER_ELIGIBLE` requires all of the following from a known `PAPER`-stage
catalog fingerprint and its exact expected evidence version: positive OOS and stressed
expectancy, profit factor after costs of at least 1.10, maximum drawdown no more
than 10%, configured minimum OOS trade count, and passing walk-forward,
replication, nearby-parameter, and profit-concentration checks. It is a research
promotion only, not a paper-trade launch or live approval.

The gate also requires a bounded closed-trade receipt with candidate-bound
source and cost-model IDs, dataset checksum, one currency and initial equity,
a selection freeze before the OOS window, and unique chronologically ordered
trades inside that window. Each trade supplies gross P&L and separate base and
stress costs; stress costs cannot be below base costs. Expectancy, profit factor,
sample count, and closed-trade drawdown are recalculated from those records.
Unknown or nested receipt fields are rejected before checkpoint persistence.
Metric claims cannot override failed recalculated metrics.

Identifiers/checksums are bindings, not source authentication. Actual input
bytes, future receipt availability, independent holdout use, walk-forward and
replication claims, open-position drawdown, fill realism and actual paper
performance remain unverified. Gate output explicitly sets
`source_authentication_verified=false` and `paper_readiness_verified=false`.

The controller must apply this gate before it selects a `PAPER` experiment. A
missing or failing evidence payload is a non-waking research rejection, never a
paper launch. The runner must return the evidence score and gate result so the
decision is reviewable; neither result may grant live authority.

## State and watchdog

Checkpoint state is local sandbox evidence only. It is atomically written,
digest-verified, identity/version-bound, and fails closed when corrupt or changed.
Writers use an exclusive temporary checkpoint lock, check the loaded revision,
and preserve all previously completed outcomes. A conflicting writer fails
closed without waiting, stealing a lock, overwriting newer state, or restarting
anything. An abandoned lock requires explicit recovery; no automatic expiry is
assumed. APPLY rejects stale active or future persisted state before any write.
The same canonical checkpoint validation must be used by the runner and watchdog:
an incomplete or internally inconsistent `NO_EDGE_IN_SCOPE` checkpoint is
`BLOCKED`, not informational. `last_progress_utc` represents a completed
experiment only and must not be refreshed by a repeated empty controller attempt.
The campaign freshness budget is persisted in the checkpoint and can only be
tightened, never loosened, by watchdog configuration.

Checkpoint output is confined to a resolved descendant of the operating system
temporary directory. The repository root, current directory, temp root itself,
and any symlink escape are rejected. Campaign JSON inputs and the finite catalog
have explicit size and count limits before routing.
The existing dead-man watchdog may read a checkpoint only when explicitly given a
path. It remains detect-only. Missing, malformed, stale, duplicate, or empty
active campaign state is `BLOCKED`; `NO_EDGE_IN_SCOPE` is informational and does
not wake an operator. `BUDGET_EXHAUSTED` and `RESEARCH_COMPLETE` are also
informational. Future progress remains blocked even for terminal decisions.

## Phase 1 hard boundary

Phase 1 is **not** a scheduled 24/7 runtime. It has no scheduler, daemon,
restart, worker launch, queue/lock/approval mutation, network/CME acquisition,
broker/OANDA/API access, orders, money movement, secrets, webhooks, external
notifications, commits, pushes, or live trading. `APPLY` is limited to a
caller-provided local sandbox checkpoint; `DRY_RUN` writes nothing.

The release proof is a fixture-only one-cycle integration test from runner to
checkpoint to watchdog. It does not register a scheduler, start a service, use a
network source, access credentials, or create paper/live orders. CI must execute
the focused controller and watchdog tests in addition to Python syntax checks.

## Phase 2 entry conditions

Phase 2 may be planned only after all controller and watchdog tests pass, a
manual bounded-endurance run produces valid checkpoints, the Forex data/cost
capability is selected and validated, comparison data/cost/contract capability
is separately validated when evaluating futures, and a separate owner-approved
packet scopes any external restart or scheduler behavior. A market winner
requires matched real data, costs, risk and independent tests; API availability
or an engineering test count does not establish profitability.
