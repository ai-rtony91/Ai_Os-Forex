# 24/7 Forex-First Research Workflow — Phase 1 Execution Record

## Implemented scope

1. Immutable campaign, experiment, outcome, and decision contracts.
2. Stable SHA-256 fingerprints that ignore display IDs but retain real dimensions.
3. Fixed evidence scorecard and paper-only edge gate.
4. Deterministic routing with duplicate suppression, stage ordering, no-edge
   exhaustion, and pinned Forex and Futures comparison capability checks.
5. Atomic digest-verified sandbox checkpoint and idempotent resume.
6. Optional watchdog campaign-health inspection without changing default
   heartbeat-only behavior.
7. JSON-only bounded runner: `DRY_RUN` creates nothing; explicit local `APPLY`
   writes only one checkpoint.
8. A 100-cycle in-memory fixture proof with no duplicate fingerprint and no live
   authority.
9. A bounded one-cycle runner/watchdog bridge with a shared 1 MiB checkpoint
   limit, fail-closed handling for oversized and deeply nested JSON, pre-write
   evidence scoring, and checkpoint symlink rejection.

## Bounded verification

Run the relevant tests from the repository root:

```bash
python -m pytest \
  tests/orchestration/test_aios_research_campaign.py \
  tests/orchestration/test_aios_research_campaign_runner.py \
  tests/orchestration/test_aios_deadman_watchdog_campaign_health.py \
  tests/orchestration/test_aios_research_campaign_end_to_end.py \
  tests/orchestration/test_aios_autonomous_forex_research_pipeline.py \
  tests/orchestration/test_aios_autonomous_forex_research_runner.py \
  tests/orchestration/test_runtime_heartbeat_refresh.py \
  tests/orchestration/test_heartbeat_dirty_write_guard.py -q
git diff --check
```

The endurance proof is a pure in-memory test helper; it does not sleep, launch a
process, create a scheduler, contact a network service, or write outside pytest
temporary directories.

The PAPER gate validates caller-supplied metric claims and candidate identity;
it does not verify source artifacts or recompute performance. Its
`PAPER_ELIGIBLE` status permits a controller stage selection only. No real edge,
paper readiness, or live readiness has been established. Full-repository test
collection remains blocked by unrelated environment/repository collection
errors recorded in the validation report.

On 2026-10-05, the relevant controller, watchdog, end-to-end, Forex, and
heartbeat suite returned **105 passed, 12 skipped**. `git diff --check`, AST
parsing for 8 Python files, and CI workflow YAML parsing passed. The independent
working-tree review found no remaining Critical or Important issues. A prior
whole-repository collection attempt stopped with 5 errors: `jsonschema` is not
installed in the local collection environment, `aios.py` shadows the `aios/`
package for some tests, and two test files use a duplicate basename.

## Non-goals and handoff

This is a Phase 1 controller, not an activated 24/7 runtime. It cannot be
scheduled, daemonized, restarted, connected to a broker or data provider, or
used for paper/live trading under this plan. No MuleSoft component is needed for
this local, isolated control-plane phase.

Before planning Phase 2, require: passing controller/watchdog verification, a
manual bounded-endurance checkpoint proof, validated real Forex data/cost/feed
capability, validated Futures comparison data/cost/contract capability, and a distinct owner-approved packet for any scheduler or external
restart behavior.

## Market-fit assessment

The implementation keeps AIOS/Forex as the primary lane and CME index futures as
a comparison lane. This is a workflow choice, not a finding that Forex has a
proven edge. Futures offer exchange-defined contracts and explicit tick/fee
schedules but require licensed historical data and a distinct data integration.
Retail spot FX has a convenient practice API and long history, while quotes,
spreads, financing, and stream coverage remain provider-specific. The project
has no connected source or broker in either lane, so comparative cost-adjusted
out-of-sample reliability and paper-fill fidelity are unmeasured. Keep the dual
lane until both markets can run the same pinned-data, cost-adjusted,
out-of-sample and paper-evidence protocol.
