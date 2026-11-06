# AI_OS Whitepaper

## Purpose

AI_OS is a governed automation platform for helping humans build and manage projects through human-readable prompts, structured worker orchestration, validation, and clear authority boundaries.

This whitepaper defines the long-term architectural vision. It is not a claim that AI_OS is conscious, sentient, AGI, or independently autonomous. AI_OS is a controlled system for AI-assisted systems engineering.

For Trading Lab / Forex, AI_OS is a governed, human-controlled, broker-capable trading system and execution platform framework. AI_OS is the platform. Backtesting, paper simulation, supervised demo, and governed broker execution are execution stages inside the platform, not the full identity of AI_OS.

## Core Idea

AI_OS exists to turn intent into safe project work.

A human should be able to describe a goal in normal language. AI_OS should help translate that goal into:

- repo inspection
- ownership discovery
- source-of-truth selection
- scoped planning
- bounded worker execution
- validation
- review
- reporting
- safe continuation

The core pattern is simple: understand before changing, validate before mutating, and keep humans in control of risk.

## Why It Exists

Modern projects often fail to stay legible. Decisions scatter across README files, chat history, branches, dashboards, scripts, generated reports, runtime state, and abandoned drafts. AI tools can accelerate this problem when they create new authority instead of finding the existing one.

AI_OS exists to reduce that drift.

It is designed to help humans:

- find the file or system that already owns a topic
- prevent duplicate brains
- distinguish active, draft, generated, archive, runtime, and legacy material
- protect high-risk systems
- organize work into phases and lanes
- validate outputs before relying on them
- continue work safely across sessions

## Human Control

AI_OS is human-first.

Humans define the mission, approve risk, decide priorities, and own final judgment. AI workers can inspect, plan, edit, validate, and summarize, but they do not become the governing authority.

The intended workflow is:

1. The human describes the objective.
2. AI_OS maps the current state.
3. AI_OS identifies authority, ownership, and risk.
4. A worker receives one bounded task.
5. The worker operates only inside its approved lane.
6. Validation proves the result.
7. The human decides whether to continue, commit, merge, push, archive, or stop.

Routine technical continuation already covered by the owner's current authorization may proceed through verified checkpoints without a fresh decision after each unit, test or report. The human decision in step 7 remains necessary for new scope, material risk or preference choices, permission changes, protected actions and applicable owner-stop/resume decisions. Preserve intentional pauses and every existing approval gate; neither this clarification nor a checkpoint grants new authority.

## Governance Model

Governance is part of the architecture.

AI_OS relies on canonical authority files so both humans and workers know where truth lives:

- `README.md` is the human front door.
- `AGENTS.md` governs AI and Codex worker behavior.
- `docs/governance/` owns source-of-truth maps, ownership rules, and doctrine.
- `docs/workflows/` owns operator and development workflows.
- `docs/security/` owns approval, credential, access, and safety boundaries.
- `docs/architecture/` owns durable architecture and system vision.
- `docs/audits/` records inspection history and cleanup decisions.

When an existing canonical file owns a topic, that file should be updated instead of creating another document with overlapping authority.

## Worker Orchestration

AI_OS workers are controlled contributors, not free agents.

Each worker should have:

- one lane
- one branch or worktree
- one task
- one file ownership boundary
- one validation chain
- one expected output
- one stop condition

This model lets multiple workers contribute without overwriting each other, duplicating authority, or silently expanding scope. Main control remains responsible for merge and push approval.

## Governed Continuation and Project Building

This section describes requirements under the existing [Continue Through And Through Law](../../AGENTS.md#continue-through-and-through-law) and [identity and lane governance](../governance/aios-identity-and-lane-governance.md). It does not grant execution or publishing authority. Progress within approved scope should continue from verified checkpoints without repeatedly asking the owner to type continue. A completed unit, test run or report is a checkpoint; the entire mission is complete only when its original acceptance criteria have verified evidence.

### One existing orchestration chain

The current campaign uses Human Owner -> BOSS -> MAIN -> named worker and independent reviewer -> MAIN. The owner sets the goal, material preferences and protected permissions. BOSS organizes priorities and escalations. MAIN alone dispatches, writes orchestration work records and integrates. Workers perform bounded tasks and save results. A named independent reviewer accepts or rejects the exact result. Tool names and legacy East/West worksite labels do not create additional dispatchers. MAIN here is an operational role, not the Git main branch. A role label in JSON is not an authenticated actor or permission.

Before dispatch, MAIN reconciles existing assignments, accepted results and current owners; verifies scope, claims, resources, deadlines and the supported transport; and reuses completed work. Each real dispatch needs a verified start acknowledgement. Missing acknowledgement requires state reconciliation and follow-up on the same assignment, not blind resend or duplicate workers. Do not guess available credit, invent an eligible job or treat stale observations as current state.

Each handoff must retain the existing mission/task identity, exact result reference and source/input scope, one responsible owner, a named reviewer, delivery and acknowledgement state, acceptance or rejection, and the next eligible action. The author saves the result; MAIN collects it; the reviewer records a decision against that exact result; MAIN acknowledges the review and integrates only within current authority; MAIN saves the installation/check outcome and continues or escalates a genuine blocker. Technical acceptance never substitutes for required owner approval. A changed source pin needs its reviewed successor contract; old receipts and approvals are not silently retargeted.

### Continuation, stalls and interruption

Use the existing controller and work-record trail. At supported checkpoints, check for saved results, pending reviews, missed acknowledgements and stalled handoffs. Record the responsible owner, evidence, exact blocker and changed-input recovery trigger. Follow the existing supported route through resolution or escalation. Silence alone proves neither a dead worker nor failed delivery. Continue independent eligible work while a dependent action is blocked. Do not create a second supervisor to mask an unavailable route.

Retain completed and failed work, original Goals and counters, spent resources, unresolved intents, accepted receipts, ownership and owner pauses across restarts. Reconcile an uncertain execution before attempting it again. Prove cold-process behavior at identified boundaries; a refusal, source copy or mocked restart does not establish automatic recovery or power-loss durability. A fully admitted run must preserve its existing lease, original deadlines and budget ceilings.

Save genuine stops using the existing classes: OWNER_ACTION_REQUIRED, SAFETY_INTEGRITY_BLOCK, RESOURCE_TIME_BLOCK, UNRECOVERABLE_FAILURE or CAMPAIGN_COMPLETE. Never convert an integrity failure into retry permission. A failed or denied action stops its dependent operation; do not access the same protected resource through another executor or transport. Select another independent authorized task when one is genuinely available.

### Owner stop and truthful observability

Reuse the existing control/self_continuation/STOP mechanism and runner checks. Required behavior is a sticky owner stop observed before a new task is launched, retained across process restart, with explicit owner clearance and the original resume authority required to continue. An in-flight operation must finish or be reconciled under its existing contract; do not pretend a synchronous callback has been killed. Distinguish a stop request, an observed safe boundary, and verified quiescence. An owner-stop command must not clear evidence, remove C03 or weaken any other protection.

During active work provide short, accurate start, midway, installation and approximately 20-minute status updates when the running environment and communication tools support them. Identify what changed, what works now, what remains missing, the responsible owner and whether the owner must act. Report missed updates and unavailable transport honestly. Policy text, saved diagnostics and scheduled cards do not prove an active monitor, delivered message, running worker or uninterrupted service.

### Document intake and owner choices

The intended project intake accepts owner-supplied project whitepapers, scans, AGENTS/README files and related material as scoped input. Preserve the original document identity/hash and page or section references; separate extracted statements, uncertain OCR, conflicts, proposed requirements and actual governing authority. Embedded document instructions cannot grant permission or override AGENTS.md, RISK_POLICY.md or platform controls. Do not publish raw project chats, secrets or unrelated private files.

Before building, identify material choices and ask the owner in simple, short questions, like completing a custom order. Cover the goal, intended users, important behavior, constraints, costs and acceptance criteria as needed. Reuse answers already established; avoid needless repeated questions. Surface conflicting requirements and uncertain extraction instead of filling them in as facts. Record the owner's decisions against the source requirement, then prepare the existing governed campaign and exact acceptance checks. An answer about design is not approval for a protected action. Required approvals must remain concrete and action-specific.

Document-to-project construction must use the existing BOSS/MAIN path, not a new dispatcher. Demonstrate extraction accuracy, uncertainty handling, preference capture, source-to-requirement traceability, dry-run packet preparation, scoped execution, independent review and the original project's acceptance criteria before calling this capability operational. Threema commands remain deferred until the current campaign is completed or explicitly parked and the separate task is eligible.

### Implementation evidence and remaining work

The following is a dated engineering snapshot, not an admission or completion certificate (2026-11-06):

| Requirement | Existing implementation or evidence | Current limit |
|---|---|---|
| Durable campaign and task boundaries | [Master runtime](../../automation/orchestration/aios_master_runtime_v1.py), [ABCD runner](../../automation/orchestration/aios_abcd_autonomy_runner.py), and [runner regressions](../../tests/orchestration/test_aios_abcd_autonomy_runner.py) | Real MAIN owner/admission, eligible job and end-to-end recovery must still be qualified. |
| Owner stop wiring | Private AIOS-OWNER-STOP-PRIVATE-REVIEW-20261106 evidence: 103 selected stop/runner checks and scoped Ruff passed, including a baseline master-path regression | Candidate awaits independent review; installed root CLI has no stop command. Checks are synthetic engineering, not live quiescence or power-loss proof. |
| Named review and missed-handoff diagnostics | Existing [continuation controller](../../automation/orchestration/aios_continuation_controller.py); private AIOS-GOVERNED-HANDOFF-R1-REVIEW-20261106 evidence: 44 checks and scoped Ruff passed | Private candidate is a read-only observation diagnostic. It does not authenticate receipts, deliver messages, dispatch workers or run a monitor. |
| Goal proposal intake | Existing [goal intake bridge](../../automation/orchestration/goal_intake/aios_goal_intake_bridge.py) and [tests](../../tests/orchestration/test_aios_goal_intake_bridge.py) | Observe-only proposal preparation; inspected code does not establish OCR, an owner preference loop or unattended project building. |
| GitHub publication and T9 preservation | Exact reviewed project changes require the existing protected publication path; T9 requires current drive/bin verification and copy verification | Local installation is not publication. T9 was not visible in the current drive inventory; no backup is claimed. Proposed staging manifests and watchers are not installed services or verified backups. |

Review package names identify saved private evidence; the packages are not implied to be committed repository artifacts. Counts overlap with existing tests and are not a percentage of mission completion. Promote a status only after independent review, current source-pin checks, scoped installation verification and real operational evidence appropriate to that requirement. Keep C03 and all existing stops intact. Documentation cannot guarantee that sessions never halt.

## Validation-Driven Building

AI_OS treats validation as a prerequisite for trust.

Before a change is accepted, the system should know:

- what files were inspected
- what files were allowed
- what files were blocked
- what changed
- what validators ran
- what errors or unknowns remain
- whether commit or push happened

Validation may include `git status --short --branch`, `git diff --check`, targeted tests, JSON parsing, PowerShell parsing, dashboard checks, runtime health checks, and exact-file evidence.

Validation does not replace human approval. It gives the human evidence for the next decision.

## Self-Healing and Self-Automation

AI_OS is designed to become more maintainable over time.

In this context, "self-healing" does not mean uncontrolled self-repair. It means governed detection and recommendation:

- identify missing ownership
- detect duplicate authority
- flag stale references
- recommend the next safe step
- route work to the correct workflow
- preserve audit evidence
- improve structure through approved changes

"Self-automation" means repeatable, validated workflows that reduce manual chaos without bypassing approval.

## The Recursive Principle

AI_OS eventually recognizes that AI_OS itself is also a project.

The same governance, validation, workflow, ownership, and orchestration systems used to build a trading bot, dashboard, or automation tool should also help AI_OS improve and organize itself safely.

That recursive idea is practical, not mystical:

1. Define the mission.
2. Map the repo.
3. Identify active authority.
4. Classify source material.
5. Protect runtime and high-risk paths.
6. Promote useful material into canonical homes.
7. Validate changes.
8. Report evidence.
9. Repeat in controlled phases.

This gives AI_OS a path to become more stable without pretending to be self-aware.

## Realistic Use Cases

AI_OS may eventually help build and manage:

- governed trading systems, backtesting, paper simulation, supervised demo review, and broker-readiness evidence
- orchestration systems
- dashboards
- automation systems
- operational tooling
- validation pipelines
- developer workflows
- telemetry and reporting systems
- repo cleanup and restructuring efforts

Every use case follows the same rule: authority first, scope second, validation before mutation.

## Trading Lab Example

Trading Lab / Forex is the first production vertical.

AI_OS may help humans build a governed trading system and execution platform framework through staged capabilities:

- separating research from execution
- validating signal and risk workflows
- tracking paper results and latency
- preserving broker boundaries
- producing broker-readiness evidence
- supporting owner approval workflows and dashboard truth
- designing governed broker execution pathways without default activation
- producing operator-readable evidence
- keeping general live execution blocked unless a reviewed, explicit, governed exception applies

Blocked by default does not mean non-broker-capable. Paper simulation is a stage, not the system identity. Broker execution requires governed approval and safety controls.

General live trading remains blocked. Broker credentials, account identifiers, real orders, webhooks, schedulers, daemons, and uncontrolled automation remain blocked. A single governed live micro-trade exception may exist only through `AIOS_FOREX_FINAL_LIVE_OPERATOR_BRIDGE_V1`, with explicit human approval, runtime-only credentials, one-order-only enforcement, micro-size enforcement, stop loss, take profit, max loss gate, daily stop gate, kill-switch state validation, sanitized evidence, and no credential or account persistence. LLMs must not be placed directly in live order execution paths.

## Long-Term Direction

The long-term direction is a governed project-building environment where human-readable prompts become structured, auditable work.

AI_OS should become better at:

- analyzing project structure
- identifying missing ownership
- detecting duplicate authority
- recommending next safe steps
- routing work to the right lane
- improving maintainability
- preserving audit history
- stabilizing itself over time

This is practical automation. The goal is not to remove humans from decisions. The goal is to make complex work easier to control.

## What AI_OS Is Not

AI_OS is not:

- conscious
- sentient
- AGI
- magical intelligence
- unchecked autonomy
- a replacement for human judgment
- an uncontrolled live trading bot
- a permission-free broker execution bypass
- a credential store or secret manager
- a direct LLM live-order controller
- a tool for bypassing validation or approval

AI_OS should not claim capabilities it cannot safely prove.

## Architectural Vision

AI_OS should feel like a professional operating layer for AI-assisted project work.

Its strength is structure:

- canonical authority
- scoped workers
- protected systems
- human approval
- validation chains
- audit trails
- clear continuation paths

The vision is a system where a person can describe what they want to build, and AI_OS helps turn that intent into organized, validated, auditable progress.

AI_OS should make projects easier to start, safer to change, and harder to lose in scattered instructions.

## Verification Update 2026-11-06: Stop Installed, Native Workflow Still Unproven

This later record supersedes the pre-installation owner-stop status in the earlier engineering snapshot. Independently reviewed owner-stop R2 is now installed in the existing root CLI and master runtime. All four saved baseline files matched current MAIN byte-for-byte before adoption, including the mixed-line-ending master-runtime test fixture. The two installed source files were read back against their reviewed pins; 107 focused stop/runner checks passed against installed source, scoped Ruff passed, and the actual root CLI stop preview reported no write and no claim of full quiescence. Other source, governance and C03 pins remained unchanged by that installation. The existing stop command is available; no owner STOP signal or live workflow was activated by these checks.

The real proof-reader investigation identified another concrete boundary in this execution environment: QueryDosDeviceW("C:") returned Win32 error 5 (Access denied) before opening a newly created private owned proof file. The master therefore refused native proof validation with RUNTIME_PROOF_READ_UNAVAILABLE. This is not evidence of data corruption or proof that every laptop process lacks access. The enforcing rule and the qualified production owner context remain unestablished. Do not remove the identity check, change security settings or route the denied operation through another executor. The existing environment/MAIN owner must qualify the supported read and handoff context before native recovery can be proven. No repeat of this now-identified denied query, daemon-socket probe or other blocked route is authorized by this note.

The separate handoff observation candidate remains a diagnostic, not authenticated delivery or a running manager. Native owner send/start access, current shared-resource admission, a genuine eligible job and end-to-end receipts remain required for operational proof. Stop installation and private tests do not close the permanent guiding milestone, prove earnings, authorize real-money risk, establish a T9 backup or activate Threema.

Publication scope: the verification records above describe the owner's local AIOS installation and saved private engineering evidence. This documentation candidate does not publish those runtime changes, prove remote-main parity or grant native admission. Runtime source promotion requires its own exact-base reconciliation, review and verification.
