# AI_OS Product Roadmap

Status: canonical summary extracted from legacy `docs/AI_OS`

## Purpose

This roadmap summarizes product and platform direction from legacy `docs/AI_OS` roadmap, dashboard, product, productization, orchestration, and trading-related planning docs. It does not claim these ideas are implemented.

## Current Direction

AI_OS is a local-first guided operating environment with human-controlled AI assistance.

Near-term product focus:

- clean repo structure,
- compact canonical docs,
- safe orchestration,
- dashboard visibility,
- Trading Lab / Forex broker-readiness progression,
- validation and governance before automation expansion.

## Dashboard Direction

The dashboard should become an operator control center, not a cluttered marketing surface.

Near-term direction:

- preserve useful doctrine from legacy dashboard drafts in compact canonical docs,
- keep `apps/dashboard` separate from legacy planning docs,
- define a small read-only dashboard data contract before wiring more UI,
- show system status, validator state, protected-file warnings, blocked-action warnings, and next safe action,
- show work packets, approvals, worker status, and commit package recommendations only from approved local/canonical sources,
- keep controls read-only until separately approved,
- prefer fixture/local data before real adapters,
- archive legacy dashboard draft swarms only after extraction and reference checks.

Medium-term operator control center direction:

- command-center layout with stable status, work, safety, telemetry, and assistance panels,
- validator-first display logic,
- Trading Lab / Forex readiness visibility,
- local telemetry and work-intelligence panels,
- mobile-readable status stack,
- restrained theme system with clear PASS/WARN/FAIL/BLOCKED/UNKNOWN states.

Blocked until architecture review:

- dashboard-triggered APPLY actions,
- live AI assistant integration,
- external API/database integrations,
- account integrations,
- deployment/publishing automation,
- broker/OANDA/live trading visibility or execution,
- real webhook execution.

## Operator Control Center Direction

The operator flow should reduce copy/paste and confusion while preserving human approval.

Needed capabilities:

- goal intake,
- work packet generation,
- Codex prompt generation,
- approval inbox draft,
- validator recommendation,
- clean-state reminder,
- next safe command.

## Worker Orchestration Direction

Worker orchestration should converge on one controlled system:

- packets,
- worker registry,
- approvals,
- validators,
- commit packages,
- clean-state gates,
- operator status.

It should not become multiple independent brains.

## Documentation Cleanup Direction

`docs/AI_OS` should be reduced from a 770-file legacy planning swarm into compact canonical docs under:

- `docs/architecture`,
- `docs/workflows`,
- `docs/governance`,
- `docs/infrastructure`,
- `docs/security`,
- `docs/roadmap`,
- `docs/concepts`,
- `docs/audits`.

Legacy docs should be archived only after useful doctrine is extracted.

## Trading Lab Direction

Trading Lab is a governed proving ground for paper simulation, backtesting, supervised demo review, broker-readiness evidence, and risk-controlled progression.

Allowed direction:

- strategy planning,
- backtesting,
- paper signal review,
- latency tracking,
- risk controls,
- evidence and reporting.

Blocked direction:

- broker login,
- OANDA/live API execution,
- real webhooks,
- real orders,
- LLMs in live order execution paths.

## Near-Term Next Steps

1. Human review of these canonical summaries.
2. Complete dashboard summary extraction and decide whether a compact dashboard data-contract spec is needed.
3. Archive or retire legacy `docs/AI_OS/dashboard` drafts only after reference checks.
4. Separate review for dispatcher and orchestration docs.
5. Promote security and governance docs into canonical locations.
6. Continue orchestration cleanup for v1 examples and direct display dependencies.

## Human-Review Items

- Whether dashboard docs describe current implementation or future product direction.
- Whether productization should stay roadmap-only.
- Which Trading Lab docs belong under active product roadmap versus archive.
- How soon to introduce automation beyond documentation and operator runners.

## Permanent Guiding Milestone — Owner Direction 2026-11-06

Build and prove a reliable, owner-controlled AIOS workflow that develops, tests, and safely operates a Forex system until it earns its first verified dollar, without risking real money until you explicitly approve it.

This is the owner's lasting guiding milestone for the project until the owner explicitly revises it. Status: OPEN / NOT PROVEN. It adds direction without erasing prior goals, accepted results, failed evidence, counters, budgets, deadlines, claims, checkpoints or owner pauses. This roadmap defines direction; AGENTS.md, RISK_POLICY.md, current contracts and required protected-action approvals still govern execution. The owner can stop the workflow. A goal statement, successful test, technical review or saved checkpoint is not financial-action authority.

Progress must prove the actual BOSS -> MAIN -> named worker/reviewer -> MAIN workflow: verified starts, saved exact results, acknowledged independent decisions, governed integration and the next eligible action. Reuse the existing controller, owners and accepted work. Preserve stop and recovery behavior, and reconcile uncertain outcomes without replay. Private fixtures, prepared source and documentation are engineering progress, not proof of an operating autonomous system.

Forex development must retain genuine data, strategy validation, costs, risk controls, original scientific failures and independent evidence. Complete eligible engineering and paper preparation without implying live readiness. Real-money risk remains blocked unless the owner explicitly approves the exact action under all applicable existing gates. This milestone grants no broker access, credentials, live orders, money movement, repeated attempts or expanded resource authority.

The first verified dollar requires independently reviewed, sanitized evidence of actual realized net earnings of at least one US dollar after recorded costs, consistent with the existing [broker-verified profit-proof milestone](../trading_lab/FOREX_BROKER_VERIFIED_LIVE_PROFIT_PROOF_MILESTONE_V1.md). Preserve the PnL currency and document any required conversion evidence; unresolved costs, attribution or currency evidence keep the claim unproven. Demo, paper, simulated, unrealized, gross or manually asserted profits do not establish this final earnings claim. Obtain the existing owner-governed approval before any real-money attempt and review its outcome before any repeat. Do not upload secrets or private broker/account records.

Profit is uncertain and is not guaranteed. A first verified dollar would not establish a durable trading edge, reliable future income, unrestricted live permission or permission to ignore an owner stop. Report progress against both workflow reliability and genuine earnings evidence; never substitute a convenient passing test count or sample for the full milestone.
