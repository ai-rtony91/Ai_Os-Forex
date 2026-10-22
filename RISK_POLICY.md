# AI_OS Risk Policy

## Purpose

This file is the canonical root safety and execution authority for AI_OS.

It defines the default safety posture, blocked execution boundaries, emergency-stop conditions, approval-gate doctrine, validation expectations, and fail-closed behavior for AI_OS development and operation.

This file does not replace `AGENTS.md` as agent-behavior authority and does not redefine workflow topology, launcher topology, or worker-lane structure.

## Canonical Authority Status

`RISK_POLICY.md` is root authority for AI_OS safety and execution boundaries.

Supporting security, audit, placement, and ownership documents may add detail, but they must not weaken this policy. If a supporting document conflicts with this file, the stricter safety rule applies until the conflict is resolved by explicit human approval.

## Default Risk Posture

AI_OS defaults to inspection before execution.

- DRY_RUN is the default mode.
- APPLY requires explicit human approval.
- Unknown risk is blocked until clarified.
- Authority mismatch is blocked until resolved.
- Branch, path, or repo identity mismatch is blocked until verified.
- Inspection must not automatically escalate into execution.
- Automation must not silently fall back to a less safe behavior.

## Absolute Execution Blocks

The following are blocked unless a future explicit, reviewed policy changes the project boundary:

- live trading.
- broker execution.
- OANDA live-host access, OANDA order execution, order-capable OANDA clients, and any non-GET OANDA or broker request.
- real webhook execution.
- real orders, including OANDA Practice orders, unless a separate explicit Human Owner-approved policy exception applies.
- broker credentials, account identifiers, API keys, tokens, passwords, private keys, recovery keys, or other secrets, except runtime-only in-memory OANDA Practice credentials used under the Bounded OANDA Practice Read-Only Market Data Exception below.
- destructive actions without explicit approval, including delete, move, rename, overwrite, reset, clean, and force push.
- runtime mutation without validation.
- hidden automation, startup tasks, scheduled tasks, or background execution paths.
- validation bypass.
- automatic escalation from a report, dashboard, terminal, queue, packet, or launcher into execution authority.

## Single Live Micro-Trade Exception

AI_OS is broker-capable by architecture, but paper simulation, backtesting, and supervised demo operation remain the default execution state. Live broker execution remains blocked unless the Single Live Micro-Trade Exception is active under this section and every required gate is satisfied.

This exception is a one-shot authority carveout for one explicitly approved live micro-trade only. It does not enable general live trading, broker execution, live routing, credential handling, dashboard trading controls, autonomous trading, or future trades.

The exception is inactive unless a current Human Owner approval names all of the following exactly:

- broker path.
- instrument.
- side.
- units or notional limit.
- maximum loss.
- daily loss cap.
- stop loss.
- order type.
- approval window.
- evidence bundle.
- arming step.
- stop point.

If any required field is missing, ambiguous, expired, or conflicts with current repo authority, the exception is `BLOCKED`.

The exception must preserve these execution limits:

- one order only.
- no retry loop.
- no autonomous re-entry.
- live mode defaults to false.
- explicit arming is required before the single approved order.
- kill switch is required and must be active before arming.
- daily loss cap is required and must be active before arming.
- broker sandbox or demo proof is required before any live arming.
- evidence bundle is required before and after the attempt.
- automatic hard stop after fill, rejection, error, timeout, or approval expiry.

Approval for this exception is non-transferable. Approval for one micro-trade does not approve future trades, broker setup, credential handling, commits, pushes, merges, deployment, dashboard changes, runtime changes, service changes, or any other protected action.

Validators, dashboard output, routers, queues, telemetry, reports, launchers, terminals, and generated evidence are evidence only. They cannot approve, arm, extend, retry, re-enter, or execute the exception.

Credentials, tokens, account identifiers, broker order IDs, live payloads, secret values, and private live execution data must never be printed, committed, logged, stored in repo files, included in prompts, included in reports, captured in screenshots, written to telemetry, or placed in fixtures. Evidence for this exception must be sanitized and must exclude secrets, broker credentials, private data, account data, and live execution payloads.

## Trading Lab Boundary

Trading Lab / Forex is broker-capable by architecture only behind governance. Paper simulation, backtesting, and supervised demo review remain the default execution state unless a separately approved governed exception satisfies this policy.

Allowed when explicitly scoped:

- paper simulation.
- backtesting.
- latency tracking.
- signal validation.
- paper route previews.
- local-only telemetry that does not collect secrets or live execution data.
- owner-approved OANDA Practice GET-only sanitized market-data retrieval under the bounded exception below.

Blocked:

- live broker connections.
- live order routing.
- real order placement.
- OANDA live-host clients, order-capable OANDA clients, non-GET broker methods, and live broker adapters.
- broker credentials or live account data, except runtime-only in-memory OANDA Practice credentials used under the bounded exception below.
- LLMs directly in live order execution paths.

### Bounded OANDA Practice Read-Only Market Data Exception

AIOS may use an explicitly Human Owner-approved OANDA Practice client for GET-only retrieval of sanitized Forex market data when the sole purpose is PAPER simulation, PAPER evidence collection, signal validation, or market-data freshness validation.

This exception permits runtime-only, in-memory loading of the OANDA Practice API token and Practice account identifier solely for the owner-started GET-only process. Those values must never be printed, logged, persisted, committed, included in prompts or reports, written to telemetry, exposed through exceptions or object representations, or retained outside process memory.

Approved runtime-only credential presence is not itself an emergency-stop condition. Exposure, persistence, unapproved access, wrong-environment use, live-host use, non-GET use, order capability, private-data leakage, or authority mismatch remains an immediate fail-closed condition.

This exception grants no broker execution authority, order authority, position-mutation authority, account-mutation authority, live-host authority, money-movement authority, autonomous-execution authority, deployment authority, scheduler authority, or future-trade authority. Read-only market data is evidence input only and never execution authority.

Any OANDA client capable of non-GET methods, order submission, order modification, order cancellation, position mutation, account mutation, live-host access, or money movement remains prohibited unless a separate explicit Human Owner-approved policy exception applies.

## Secrets / Credentials / Private Data

Secrets, credentials, and private data must not be committed, persisted, exposed in generated reports, or embedded in scripts.

The bounded OANDA Practice read-only exception permits approved runtime-only credential presence in process memory; it does not permit credential or private account-data persistence or disclosure.

Sensitive data includes:

- API keys, tokens, passwords, private keys, SSH keys, OAuth secrets, recovery keys, and `.env` contents.
- broker account identifiers, live account data, live market execution data, order details, or live order path data.
- browser profile paths, credential stores, private user data, and screenshots containing private data.

Any suspected sensitive-data exposure, persistence, unapproved access, or private-data leakage must fail closed as `BLOCKED` until human review and verified evidence clarify the path forward.

## Approval Gate Doctrine

Explicit human approval is required before:

- APPLY.
- protected root file edits.
- execution-behavior changes.
- runtime, dashboard, telemetry, trading, broker, webhook, deployment, or CI/security workflow changes.
- modifying secret-handling behavior.
- destructive actions.
- staging, committing, pushing, merging, releasing, or deploying.

Approval must identify the intended files, intended change, validation expectation, and stop point. Broad or ambiguous approval does not authorize unrelated execution.

## Emergency Stop Conditions

Stop immediately and report when any of the following are detected:

- suspected secret, credential, private data, broker data, or live execution data exposure, persistence, or unapproved access.
- live trading, broker execution, OANDA live-host use, non-GET OANDA use, OANDA order capability, real webhook execution, or a real order path.
- use of OANDA Practice credentials or private account data outside the Bounded OANDA Practice Read-Only Market Data Exception.
- unapproved runtime mutation.
- unapproved destructive action.
- protected file edit without explicit approval.
- branch, path, repo identity, or authority mismatch.
- MISMATCH evidence, INVALID DATA, or unknown critical facts.
- failed validation.
- silent fallback, hidden automation, scheduled task, startup task, or unexpected background execution path.

Emergency stop means no further execution, no launcher continuation, no worker continuation, no commit, and no push until the operator approves the next safe step.

## Validation Before Mutation

Validation is mandatory before mutation.

- Inspect current authority and target files before editing.
- Run the scoped validators requested by the task.
- Run `git diff --check` when files change.
- Validate JSON parses when JSON files change.
- Validate PowerShell parses when PowerShell files change.
- Do not mutate runtime state, trading state, dashboard state, telemetry state, or worker state without explicit scope and validation.

Passing validation does not approve commit, push, merge, deployment, or execution.

## Fail-Closed Rules

AI_OS must fail closed when safety, authority, or execution state is uncertain.

Fail closed on:

- unknown risk.
- authority mismatch.
- branch, path, repo, or lane mismatch.
- missing approval.
- missing validation.
- suspected sensitive data.
- hidden execution behavior.
- stale or conflicting instructions.
- unsafe fallback behavior.

The safe result is `BLOCKED`, `REVIEW`, or `INVALID DATA` until the operator provides a clear next action.

## Audit And Evidence Expectations

Security-relevant actions should leave enough evidence to reconstruct what happened.

Evidence should distinguish:

- DRY_RUN from APPLY.
- requested action from approved action.
- validation command from validation result.
- rejected or blocked action from completed action.
- trading/broker blocked action from normal workflow output.

Audit evidence must not contain secrets, broker credentials, private data, or live execution data.

## Supporting Authority References

These documents support this root policy with implementation detail:

- `AGENTS.md` - agent operating behavior and protected-action rules.
- `README.md` - AI_OS front-door context, project boundary, and Trading Lab / Forex default-execution-state statement.
- `docs/security/approval-model.md` - approval workflow details.
- `docs/security/threat-model.md` - threat categories and required security controls.
- `docs/security/secret-prevention.md` - secret-handling procedures.
- `docs/security/audit-logging.md` - audit event and evidence expectations.
- `docs/security/PRIVACY_CREDENTIAL_EXCLUSION_CHECKLIST.md` - canonical privacy and credential exclusion checklist.
- `docs/AI_OS/governance/AIOS_FILE_PLACEMENT_RULES.md` - placement and blocked implementation boundaries.
- `docs/AI_OS/governance/AIOS_REPO_FOLDER_OWNERSHIP_MAP.md` - folder ownership and risk boundaries.

## Non-Authority / Draft References

Draft, legacy, generated, archived, or planning documents are evidence only unless explicitly promoted by a future approved AI_OS workflow.

Draft risk-control and governance matrices may inform future updates, but they do not authorize execution, weaken this policy, activate live trading, approve broker connectivity, approve secrets handling, approve runtime mutation, or replace root authority.

## Last Verified

Updated on 2026-08-10 for AI_OS active repo authority on branch `main`. Historical AI_OS V2 terminology is migration context only.
