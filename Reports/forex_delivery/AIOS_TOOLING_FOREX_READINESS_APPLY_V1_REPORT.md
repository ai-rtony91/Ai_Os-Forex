# AIOS Tooling Forex Readiness Apply V1 Report

## Summary
Operator tooling validation was repaired, stale test expectations were aligned to current repository authority, and the Forex live-trade chain was audited without broker access, credentials, live orders, push, merge, deploy, or runtime mutation.

## Canonical Contract Decision
The canonical dashboard/OANDA contract preserves the runtime-gated read-only bridge because repository authority already defines sanitized broker read-only evidence as a non-execution blocker-reduction input and explicitly states it does not authorize BUY, SELL, close, broker writes, secret reads, live execution, or LIVE_ARMABLE state. The dashboard remains display-only and the OANDA money-strip endpoint remains fail-closed unless runtime gating and runtime-only credential presence are supplied outside the repo.

Evidence:
- `docs/forex_delivery/AIOS_FOREX_READ_ONLY_EVIDENCE_APPROVAL_AND_RECONCILIATION_V1.md` allows sanitized OANDA read-only evidence to reduce future review blockers but not authorize live execution.
- `docs/forex_delivery/AIOS_LIVE_PREFLIGHT_EVIDENCE_BUNDLE_V1.md` requires final evidence while keeping `execution_requested`, `order_executed`, and `broker_call_performed` false.
- `RISK_POLICY.md` keeps live trading, broker execution, OANDA live order execution, credentials, and real orders blocked unless a current Single Live Micro-Trade Exception satisfies every gate.

## Files Changed
- `automation/bridge/aios_phase_bridge.py` repaired phase2 default arguments for focused tests while preserving CLI-provided output roots.
- `apps/dashboard/src/MinimalOperatorDashboard.jsx` surfaced display-only Forex truth labels without adding a fetch, broker call, order control, or credential path.
- `tests/orchestrator/test_forex_dashboard_truth_status.py` now tests the runtime-gated OANDA read-only bridge as the canonical fail-closed contract.
- `tests/orchestration/conftest.py` marks PowerShell-dependent orchestration tests as platform-blocked when neither `pwsh` nor Windows PowerShell is available.
- `tests/orchestration/test_aios_observe_spine_runner.py` and `tests/orchestration/test_aios_p2_enqueue_bridge.py` align stale expectations to the current pending/mismatched approval evidence state.

## Platform-Blocked Validation
PowerShell is not installed in this Linux container. PowerShell-dependent tests are skipped with an explicit message and remain required in the canonical Windows environment.

## Forex Live-Trade Blockers
Current repository evidence shows the first repository-approved live trade is still blocked by:
1. No current Human Owner-approved Single Live Micro-Trade Exception naming broker path, instrument, side, units/notional, maximum loss, daily cap, stop loss, order type, approval window, evidence bundle, arming step, and stop point.
2. Runtime-only credential entry must remain outside repo files and is not performed here.
3. Sanitized read-only OANDA evidence must be generated and approved for future live review.
4. Auto-exit live readiness remains a blocker.
5. Real trading-history writeback verification remains a blocker.
6. Live preflight evidence bundle must be ready with execution and broker-call flags false.
7. Protected live execution command package must be sealed separately.
8. Real runtime command outside Codex and stop-after-one-order procedure remain required.
9. Sanitized post-trade ledger, replay evidence, and closeout/review procedure remain required after any future approved attempt.

## Highest-Value Next Blocker
The highest-value bounded next blocker is sanitized read-only OANDA evidence approval and reconciliation because repository docs identify it as the step that can reduce account reachability, open-position reconciliation, daily P/L, and margin/risk blockers without authorizing execution.
