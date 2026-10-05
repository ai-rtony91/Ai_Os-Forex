# Research Control Plane Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the audit-found control-plane gaps before any paper-readiness or publishing decision.

**Architecture:** Keep the controller as a one-cycle, local, JSON-only process. Move checkpoint integrity into one canonical validator shared by the runner and watchdog; make paper promotion depend on an explicit evidence payload; and prove the bridge with fixture-only tests. CI runs the focused tests, but no scheduler, service, broker, data feed, credential, or order path is added.

**Tech Stack:** Python standard library, pytest, GitHub Actions YAML.

**Spec:** `docs/superpowers/specs/2026-10-05-24-7-forex-first-research-workflow-design.md`

## Global Constraints

- Preserve `live_authorization=False` on every code path.
- No network, broker, OANDA, credentials, scheduler, daemon, webhook, or order logic.
- `DRY_RUN` creates no files; `APPLY` writes only a checkpoint under the operating-system temporary directory.
- A malformed checkpoint must fail closed as `BLOCKED`; `NO_EDGE_IN_SCOPE` is informational only after canonical validation passes.
- A `PAPER` research stage is selectable only after the catalog-bound gate accepts caller-supplied claims; `PAPER_ELIGIBLE` is a routing result, not verified edge or paper readiness.
- Input and catalog bounds must reject excess work before routing.
- Do not modify root governance, risk policy, runtime, or existing paper-trading paths.

## Review Focus

- A digest-valid but schema-invalid no-edge checkpoint must wake rather than silently return `NO_WAKE`.
- A repeated empty `APPLY` invocation must not refresh completed-work progress.
- A `PAPER` selection without candidate-bound cost-adjusted metric claims must be rejected without live authority; source authenticity and metric recomputation remain later work.
- A repository or symlink-escaped output root must be rejected before any checkpoint write.
- The fixture-only runner-to-watchdog bridge must remain free of scheduling and external I/O.

---

### Task 1: Canonical checkpoint health and progress contract

**Files:**
- Modify: `automation/orchestration/research_campaign/aios_research_campaign.py`
- Modify: `automation/orchestration/watchdog/aios_deadman_watchdog.py`
- Modify: `tests/orchestration/test_aios_research_campaign.py`
- Modify: `tests/orchestration/test_aios_deadman_watchdog_campaign_health.py`

**Interfaces:**
- Produces: a public checkpoint validator that accepts a digest-bearing mapping and returns canonical payload data or raises `CampaignCheckpointError`.
- Consumes: `CampaignDecision.to_dict()` and canonical checkpoint fields.

- [x] **Step 1: Write failing checkpoint-health tests**

Add a rehashed malformed `NO_EDGE_IN_SCOPE` fixture missing a decision invariant and assert watchdog `BLOCKED`. Add a repeated-empty checkpoint test that asserts the original completed-work timestamp survives.

- [x] **Step 2: Run the focused tests to verify RED**

Run: `PYTHONPATH=/tmp/aios-pytest-runtime python -m pytest tests/orchestration/test_aios_deadman_watchdog_campaign_health.py tests/orchestration/test_aios_research_campaign.py -q`

Expected: FAIL because the current watchdog accepts the malformed no-edge state and the checkpoint builder refreshes progress.

- [x] **Step 3: Implement canonical validation and progress preservation**

Expose the existing strict checkpoint decision/history/digest validation and a
canonical checkpoint payload builder from `aios_research_campaign.py`. Consume
the validator from the watchdog before status branching. The payload builder must
preserve a previous `last_progress_utc` when no outcome is newly completed and
persist campaign freshness. Task 2 wires the runner to this new core interface.

- [x] **Step 4: Run the focused tests to verify GREEN**

Run the Step 2 command. Expected: PASS.

### Task 2: Evidence-bound paper promotion and sandbox bounds

**Files:**
- Modify: `automation/orchestration/research_campaign/aios_research_campaign.py`
- Modify: `automation/orchestration/research_campaign/aios_research_campaign_runner.py`
- Modify: `tests/orchestration/test_aios_research_campaign.py`
- Modify: `tests/orchestration/test_aios_research_campaign_runner.py`

**Interfaces:**
- Produces: `run_campaign_cycle(..., paper_evidence: Mapping[str, Any] | None = None)` and runner option `--paper-evidence-json`.
- Produces: bounded JSON reader and temporary-directory-only checkpoint writer.

- [x] **Step 1: Write failing paper-gate and containment tests**

Assert that a completed pre-paper lineage is rejected until a candidate-bound evidence payload passes, that qualifying evidence selects `PAPER`, and that a repository/symlink-escaped output root is blocked.

- [x] **Step 2: Run the focused tests to verify RED**

Run: `PYTHONPATH=/tmp/aios-pytest-runtime python -m pytest tests/orchestration/test_aios_research_campaign.py tests/orchestration/test_aios_research_campaign_runner.py -q`

Expected: FAIL because the existing router ignores paper evidence and accepts arbitrary output roots.

- [x] **Step 3: Implement gating, bounded checkpoint I/O, fail-closed parsing, and containment**

Score and evaluate the explicit paper-evidence payload before selecting `PAPER`; return a non-waking rejection when it fails. Wire runner resume/checkpoint persistence to the Task 1 payload builder. Enforce finite catalog/budget and JSON size limits. Resolve the output path under the OS temporary directory and reject its root, repository/current roots, and escapes before calling the atomic writer.

- [x] **Step 4: Run the focused tests to verify GREEN**

Run the Step 2 command. Expected: PASS.

### Task 3: Fixture-only end-to-end proof and CI gate

**Files:**
- Create: `tests/orchestration/test_aios_research_campaign_end_to_end.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `automation/orchestration/watchdog/README.md`

**Interfaces:**
- Consumes: the JSON-only runner, checkpoint contract, and optional watchdog campaign inspection.
- Produces: a CI-enforced fixture-only proof with no runtime activation.

- [x] **Step 1: Write failing end-to-end test**

Use temporary JSON fixtures to run one `APPLY` controller cycle, inspect the emitted checkpoint with the watchdog, and assert a fresh canonical `OK` result with all blocked capabilities unchanged.

- [x] **Step 2: Run the end-to-end test to verify RED**

Run: `PYTHONPATH=/tmp/aios-pytest-runtime python -m pytest tests/orchestration/test_aios_research_campaign_end_to_end.py -q`

Expected: FAIL until the canonical contract and runner input/output bridge are complete.

- [x] **Step 3: Add focused CI coverage and documentation**

Install `requirements-test.txt` in a dedicated CI step and run the Forex-first research-controller, watchdog, autonomous Forex research, and heartbeat guard test modules. Document that the runner-to-watchdog proof is one-shot, fixture-only, and neither a scheduler nor paper-order launch.

- [x] **Step 4: Run the full focused research suite**

Run: `PYTHONPATH=/tmp/aios-pytest-runtime python -m pytest tests/orchestration/test_aios_research_campaign.py tests/orchestration/test_aios_research_campaign_runner.py tests/orchestration/test_aios_deadman_watchdog_campaign_health.py tests/orchestration/test_aios_research_campaign_end_to_end.py -q`

Expected: PASS.

### Task 4: Whole-lane validation and protected publishing handoff

**Files:**
- Modify: `docs/superpowers/plans/2026-10-05-24-7-forex-first-research-workflow.md`
- Modify: `.superpowers/sdd/2026-10-05-24-7-forex-first-research-workflow/progress.md`

- [x] **Step 1: Run quality and regression checks**

Run: `git diff --check` and the existing relevant orchestration suite, including the runtime heartbeat tests.

- [x] **Step 2: Update the execution record**

Record validated hardening results and any baseline full-suite collection issue without claiming that an edge, paper trading, or live authority exists.

- [x] **Step 3: Request review and protected-action classification**

Prepare exact changed-file, validator, and PR evidence. Do not stage, commit, push, create a PR, merge, sync main, register a scheduler, or activate a runtime without the corresponding current-session approval marker.

## Validation addendum — 2026-10-05

- The runner, checkpoint loader/writer, and watchdog reader now enforce the same 1 MiB JSON ceiling; deep JSON nesting returns a structured blocked/malformed outcome.
- Evidence scoring runs before any APPLY checkpoint write, ignores non-string evidence categories safely, and checkpoint symlinks are rejected before reading.
- Repository and symlink-root tests use only temporary paths or in-process guards; they do not create or delete fixed paths in the repository.
- At this earlier checkpoint the PAPER gate still trusted supplied metric claims. This limitation is partly superseded by the continuation below; source authentication, actual paper execution and readiness remain unverified.
- The earlier relevant suite returned **105 passed, 12 skipped**. `git diff --check`, AST parsing for 8 Python files, and CI workflow YAML parsing passed.
- Independent review found no remaining Critical or Important issues. No commit, push, PR, scheduler, broker, data connection, or order path was activated.

## Verified continuation — 2026-10-05

Base: `815b18a6a03823e33db78a2f920870ce6e2af235`, independently checked against
GitHub `main`. Local branch: `codex/research-evidence-hardening-20261005` in
`/workspace/scratch/b68f2f42f060/aios-controller`. Existing uncommitted controller
work was preserved into this separate checkout; original work was not changed.

- Scientific rejection, approved budget exhaustion, incomplete validation scope,
  and completed research now have distinct terminal decisions. A completed
  candidate cannot hide another incomplete/unvisited lineage.
- Supplied history cannot exceed the approved budget, skip predecessor stages,
  reverse stage completion times, or complete in the future. UTC checks preserve
  fractional seconds. Duplicate catalog display IDs cannot skip the PAPER gate.
- PAPER research routing now requires trade receipts and recalculates positive
  OOS/stressed expectancy, profit factors, sample count and closed-trade drawdown
  after costs. Wrong candidate/source/model bindings, duplicates, invalid costs,
  selection/window overlap, and private unknown/nested fields fail closed.
- APPLY refuses stale active or future saved progress. An exclusive checkpoint
  writer lock, revision comparison and append-only history guards prevent stale
  or concurrent callers from replacing newer outcomes/evidence.
- All four JSON reader paths use one bounded regular-file reader with nonblocking
  open and descriptor validation; FIFO/directory/replacement-race fixtures return
  promptly instead of hanging an unattended controller.
- Project test collection was repaired with importlib test loading and a lazy
  `aios` package marker that preserves callable root-command compatibility
  without loading or starting the master runtime on ordinary imports. CI now
  checks project collection and the eight focused workflow modules.
- Final focused CI command: **155 passed, 12 skipped** (PowerShell unavailable).
  Project collection: **17,380 tests, zero collection errors**. Relevant package,
  trader/sweep/scorer/runtime checks: **44 passed**. AST, YAML, JSON and diff
  checks passed.
- Bounded fixture exercise completed **100 unique rejected experiments and 101
  checkpoint writes**, with zero duplicates, truthful no-edge termination and
  matching non-waking watchdog output. DRY_RUN wrote no checkpoint. This was an
  engineering proof with synthetic fixtures, not a market experiment or soak.
- Independent reviewer reran the focused suite and found no remaining Critical
  or Important defect within the bounded offline lane.

Whole-project validation remains red. The bare suite stopped at ten existing
`services/python_supervisor/test_autonomy_bridge.py` failures. A separate
`tests/` run stopped at ten existing dashboard/Windows-path assertion failures
after **11,929 passed and 871 skipped**. All twenty observed failures were
reproduced on the unchanged original; the runs stopped at their failure cap, so
the total remaining failure count is unknown. Test-generated report changes
were restored in the isolated checkout; generated `.tmp` output is excluded
from the work scope.

At that checkpoint, no stage, commit, push, PR or merge had been performed.
The PowerShell protected-action helper could not run in this environment;
remote CI and skipped Windows checks remained unverified.

Source authenticity, future receipt availability without an evaluation clock,
independent holdout use, replication/walk-forward claims, true marked-to-market
risk, actual paper fills and recovery remain Phase 2 evidence work. The system
has no verified new edge, paper readiness or live readiness. Brokers,
credentials, schedulers, daemons, workers and orders remain disabled.

Keep Forex primary for existing engineering fit; compare CME index futures only
with matched frozen data, dates, costs and risk. Richer order-book data does not
establish a more profitable strategy. The next integration gate is baseline
failure treatment plus verified Windows/protected-action/remote-CI evidence,
followed by a separately scoped authenticated local replay-evidence bridge.

## Publication preparation — 2026-10-05

The owner explicitly requested that the reviewed work be saved to GitHub,
the local repository and the laptop. The protected-action specification
requires a gate review; it describes the PowerShell runner as a helper that
can provide evidence, rather than the only permitted review mechanism.
Publication therefore uses a clearly labeled manual exact-scope gate review,
with the owner's actual instruction recorded; it does not claim that the
PowerShell helper ran or invent literal approval markers.

The package remains limited to the 15 reviewed controller, watchdog, package,
test, CI and design/plan files. Generated `.tmp` output and unrelated work are
excluded. Main merge still requires actual passing PR checks and clean
mergeability. The laptop cannot be synced while Desktop Commander is offline.

Release review found that Ubuntu provides `pwsh` while the three existing
PowerShell-dependent test modules invoke `powershell`. CI now runs those 12
tests in a separate Windows job, with an explicit executable check and exit
propagation. The Windows job gives the already checked-out commit a local
branch name because the legacy runner assumes a named branch; it preserves
the exact PR test commit rather than following a moving head ref. The other
five focused modules and complete test collection remain in the Ubuntu job.
Local platform-routing validation passed, and all 155 executable focused
tests passed again; the 12 PowerShell tests remain pending actual Windows CI.

### Laptop validation before publication

Desktop Commander subsequently reconnected. The exact reviewed commit was
transferred in a SHA-256-verified Git bundle into a separate laptop worktree at
`C:\Dev\Ai.Os.worktrees\research-evidence-hardening-20261005`. The existing
`C:\Dev\Ai.Os` main checkout contains unrelated unsaved work and was preserved.

The default pytest scratch directory on the laptop is inaccessible. A new,
previously absent release-specific `--basetemp` avoids that old directory without
changing permissions or deleting existing files. Three security-test fixtures
also required Windows symbolic-link privileges that this process does not have.
Fixture creation now skips only Windows error 1314; other errors still fail.
Basic temp/repository-root rejection is tested separately, and production path
guards are unchanged. Linux still exercises all three symlink containment tests.

The final focused suite passed **156 tests, 12 skipped** on Linux and **160 tests,
8 skipped** on the laptop. Windows skips comprise unavailable Unix features and
the three symbolic-link fixtures; they are not counted as verified Windows
symlink behavior. The actual protected-action runner self-test script passed
**13 of 13** on Windows without mutation. Complete Windows collection before
the extra split guard test loaded **17,390 tests** without errors. Remote PR
checks and main merge remain pending; no trading or unattended runtime was armed.
